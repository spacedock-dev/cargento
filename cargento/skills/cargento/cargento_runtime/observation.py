"""The single lane between events, deadlines, the probe and collection.

Above `aggregate`, `events` and `snapshot`, and the only thing in the runtime
that starts a thread. It owns four jobs that have no other home:

- the overlay ledger and the pending map, both bounded, because everything in
  them arrived from outside;
- the dirty generations that say a harness needs re-reading, and the floor that
  says how often it is allowed to be re-read;
- one collection lane, so a synchronous GET, a coalesced event burst and the
  periodic tick can never run collectors concurrently;
- worker lifecycle, including construction that starts nothing so a coordinator
  built before a fork is not inherited half-running.

## Why the floor survives the events

Coalescing bounds how long a burst waits. It sets no floor on how often the
stores are read, and the 2.5-second memo is the only rate limiter Cargento has
ever had. A ten-agent fan-out emitting lifecycle events continuously would
otherwise drive roughly 6.7 full collections per second against a ceiling of
0.4. So the first dirty event schedules collection at the later of the
coalescing deadline and the harness's next allowed collection time, and later
events in the burst merge into that pending state rather than pulling it in.

## What the probe is allowed to do here

The probe can skip a periodic collection when nothing on disk moved. It has one
documented false negative: a session older than the activity window becoming
active again is invisible to it. So a probe-negative tick is only ever allowed
to skip, never to satisfy, and an unconditional collection still runs at
`reconcile_interval_sec` regardless of what the probe says. That bounds the
false negative to one reconciliation interval instead of forever, which is the
whole reason the probe was allowed near the live path.

## What this phase does not do

An `input_requested` is exempt from the coalescing delay but still respects the
collection floor, so a permission alert publishes at the next allowed collection
instant rather than instantly. Publishing an overlay-only revision without
collecting would be faster, and the design describes it, but it means
re-serializing a retained collection whose session dicts the collectors mutate
during row construction. Making those retained results genuinely immutable is
its own change. Until then the worst case is the floor, which is still better
than the poll it replaces.
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from typing import TYPE_CHECKING, Any

from cargento_runtime import events as runtime_events
from cargento_runtime import io as runtime_io
from cargento_runtime import probe as runtime_probe

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from cargento_runtime.aggregate import Application
    from cargento_runtime.config import RuntimeConfig

# One overlay per kind per session, so the ledger cannot grow with traffic. The
# reducer is last-writer-wins per kind, so an older overlay of the same kind
# could never have changed the outcome, and dropping it is not an eviction
# policy that can lose a live alert. Subagent overlays key on the child id as
# well, because two children are two facts rather than one superseding the other.
OverlayKey = tuple[str, str | None]
SessionKey = tuple[str, str]


class Observation:
    """One process's event coordinator. Construct freely; `start` spawns.

    Every mutable field is guarded by `_lock`, which is also the condition the
    worker sleeps on, so an arriving event both records itself and wakes the
    worker under one acquisition.
    """

    def __init__(
        self,
        application: Application,
        *,
        clock: Callable[[], float] = time.time,
        diagnostic_sink: Callable[[str], None] = print,
    ) -> None:
        self.application = application
        self.config: RuntimeConfig = application.config
        self.clock = clock
        self.diagnostic_sink = diagnostic_sink
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._worker: threading.Thread | None = None
        # An Event rather than a bool, for the same reason `_stream_forever`
        # checks `client.closed` after its wait: a plain attribute checked before
        # a wait reads to the type checker as a value that cannot change inside
        # the body, and the whole point is that `stop` lands while this thread is
        # asleep. A method call cannot be narrowed that way.
        self._stop = threading.Event()
        # The server's own ordering. Minted here under the ingress lock, never
        # read from a payload: a hook that could choose its own arrival_seq could
        # choose its place in the reducer's order.
        self._arrival_seq = 0
        # This run's ingress secret. Generated per process and never written to
        # disk: what goes into the state file is one derived token per harness,
        # so a token leaked out of one adapter's configuration cannot be used to
        # post another harness's events. It dies with the process, which is what
        # makes it a per-run capability rather than a stored credential.
        self._secret = secrets.token_bytes(32)
        # Per-source token bucket. A route is not authentication and a token is
        # not a rate limit: a compromised or looping adapter holds a valid token
        # by definition, so the ceiling has to be independent of it.
        self._budget: dict[str, tuple[float, float]] = {}
        self._overlays: dict[SessionKey, dict[OverlayKey, runtime_events.Overlay]] = {}
        # sid -> (first seen, attempts). An event whose session no collection has
        # produced yet waits here. It never renders and never creates a row.
        self._pending: dict[SessionKey, tuple[float, int]] = {}
        self._dirty: dict[str, int] = {}
        self._collected: dict[str, int] = {}
        self._last_collect_at = 0.0
        self._last_reconcile_at = 0.0
        self._coalesce_until: float | None = None
        self._probe_stamp: runtime_probe.Stamp | None = None
        self.counters: dict[str, int] = {}

    # ---- the per-run, per-source capability ------------------------------

    def capability(self, harness: str) -> str:
        """This run's token for one harness. Derived, so nothing extra is stored.

        Per source rather than per run, because a single shared token would mean
        that reading any one adapter's configuration bought the ability to post
        as every harness. HMAC over the harness name with a per-process secret
        gives one token per source from one thing to keep.
        """
        return hmac.new(self._secret, harness.encode(), "sha256").hexdigest()

    def capabilities(self) -> dict[str, str]:
        """Every registered source's token, for the state file to publish."""
        return {
            harness: self.capability(harness) for harness in runtime_events.IDENTITY_NORMALIZERS
        }

    def authorized(self, harness: str, presented: str | None) -> bool:
        """Whether a caller proved it holds this harness's capability.

        `compare_digest`, not `==`: a short-circuiting comparison leaks the
        length of the shared prefix, and this is a value an attacker can retry
        against as fast as loopback allows.

        The `isascii` guard is load-bearing rather than defensive. `compare_digest`
        raises TypeError when either string holds a character above 127, and
        `http.client` decodes header bytes as latin-1, so a single high byte in the
        header would otherwise raise inside the handler rather than being refused.
        The token is hex, so nothing legitimate is turned away.
        """
        if not presented or not presented.isascii():
            return False
        return hmac.compare_digest(self.capability(harness), presented)

    def within_budget(self, harness: str) -> bool:
        """Whether this source may spend one more event now.

        A token bucket rather than a fixed window, so a hook that legitimately
        emits four events for one turn is not refused for arriving together,
        while a loop is still held to the average.
        """
        ceiling = float(self.config.event_burst_max)
        refill = self.config.event_rate_per_sec
        now = self.clock()
        with self._lock:
            tokens, last = self._budget.get(harness, (ceiling, now))
            tokens = min(ceiling, tokens + (now - last) * refill)
            if tokens < 1.0:
                self._budget[harness] = (tokens, now)
                self._bump("reject.rate")
                return False
            self._budget[harness] = (tokens - 1.0, now)
            return True

    # ---- ingress side, called on handler threads -------------------------

    def submit(self, harness: str, payload: Mapping[str, Any]) -> str:
        """Validate, record and wake. Returns the outcome for the response body.

        Deliberately short. Nothing here reads a transcript, queries SQLite or
        waits on a collection: an event handler acknowledges, and the coordinator
        does the work. The reporting shim treats every outcome as success, so the
        string is for diagnostics rather than for control flow in the hook.
        """
        with self._lock:
            self._arrival_seq += 1
            seq = self._arrival_seq
        event = runtime_events.parse(
            harness,
            payload,
            arrival_seq=seq,
            config=self.config,
            now=self.clock(),
        )
        if isinstance(event, runtime_events.Rejected):
            with self._lock:
                self._bump(f"reject.{event.reason}")
            return event.reason
        return self._record(event)

    def _record(self, event: runtime_events.Event) -> str:
        overlay = runtime_events.overlay_for(event, config=self.config)
        key: SessionKey = (event.harness, event.sid)
        now = self.clock()
        with self._lock:
            self._bump(f"event.{event.event}")
            if runtime_events.retires_overlays(event):
                # Non-destructive: the ledger for this session goes, the row does
                # not. Only a collector may decide a session is gone.
                self._overlays.pop(key, None)
                self._pending.pop(key, None)
                self._bump("retired")
            elif overlay is not None:
                self._remember(key, overlay)
            if runtime_events.requires_reconcile(event):
                # Force the next pass to be a real collection rather than one the
                # probe may skip: a rewritten transcript is not repaired by
                # replaying overlays over a cached read.
                self._last_reconcile_at = 0.0
                self._probe_stamp = None
            self._dirty[event.harness] = self._dirty.get(event.harness, 0) + 1
            deadline = now + self.config.event_coalesce_sec
            if self._coalesce_until is None:
                # Fixed, not sliding. A sliding window never closes under a
                # sustained burst, and the board would stop updating entirely.
                self._coalesce_until = deadline
            self._wake.notify_all()
        return "accepted"

    def _remember(self, key: SessionKey, overlay: runtime_events.Overlay) -> None:
        """Record an overlay, bounded by kind rather than by an eviction queue."""
        ledger = self._overlays.get(key)
        if ledger is None:
            if len(self._overlays) >= self.config.event_overlay_max_sessions:
                # Refuse rather than evict. Evicting the oldest session's ledger
                # to make room would clear whichever permission alert happened to
                # be oldest, which is the one most likely to still be waiting.
                self._bump("overlay.refused")
                return
            ledger = {}
            self._overlays[key] = ledger
        slot: OverlayKey = (overlay.kind, overlay.subagent_id)
        existing = ledger.get(slot)
        if existing is not None and existing.arrival_seq > overlay.arrival_seq:
            # A reordered delivery of something already superseded. Keeping the
            # newer one is what makes the reducer idempotent under at-least-once.
            self._bump("overlay.stale")
            return
        ledger[slot] = overlay

    def _bump(self, name: str) -> None:
        """Count something, under `_lock`. Diagnostics only, never control flow."""
        self.counters[name] = self.counters.get(name, 0) + 1

    # ---- the overlay source aggregate reads -----------------------------

    def overlays_for(self, harness: str, sid: str) -> list[runtime_events.Overlay]:
        """Live overlays for one collected row, or an empty list."""
        with self._lock:
            ledger = self._overlays.get((harness, sid))
            return list(ledger.values()) if ledger else []

    def note_rows(self, keys: set[SessionKey]) -> None:
        """Tell the ledger which rows a collection actually produced.

        This is how a pending event resolves. An overlay for a session no
        collection has produced cannot render, so it waits here to be attached by
        a later collection, and expires with a counter if none ever comes. That
        preserves a first-session permission prompt without letting a forged or
        mistyped id invent a session.
        """
        now = self.clock()
        with self._lock:
            for key in list(self._overlays):
                if key in keys:
                    self._pending.pop(key, None)
                    continue
                first_seen, attempts = self._pending.get(key, (now, 0))
                if now - first_seen >= self.config.event_pending_ttl_sec:
                    self._overlays.pop(key, None)
                    self._pending.pop(key, None)
                    self._bump("pending.expired")
                elif len(self._pending) < self.config.event_pending_max or key in self._pending:
                    self._pending[key] = (first_seen, attempts + 1)
                else:
                    self._bump("pending.refused")

    # ---- worker lifecycle -----------------------------------------------

    def start(self) -> None:
        """Spawn the coordinator. Called after the last fork, never at assembly."""
        if self._worker is not None:
            return
        self._worker = threading.Thread(target=self._run, name="cargento-observe", daemon=True)
        self._worker.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        """Stop and join, in that order, and tolerate never having started.

        The flag is set before the notify and both happen under the lock, so a
        worker about to sleep cannot miss the wake and settle in for a full
        interval after being asked to stop.
        """
        with self._lock:
            self._stop.set()
            self._wake.notify_all()
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            with self._wake:
                if self._stop.is_set():
                    return
                self._wake.wait(self._sleep_for())
                if self._stop.is_set():
                    return
                due, reason = self._due()
            if due:
                self._collect(reason)

    def _sleep_for(self) -> float:
        """How long to sleep, under `_lock`.

        The periodic tick is the shorter bound while a stream is connected. A
        pending coalesce is shorter still. Neither is allowed to be zero: a wait
        of zero with nothing to do is a busy loop.
        """
        period = self.config.stream_producer_interval_sec
        if self._coalesce_until is not None:
            period = min(period, max(0.001, self._coalesce_until - self.clock()))
        return period

    def _due(self) -> tuple[bool, str]:
        """Whether to collect now, and why. Called under `_lock`.

        The floor gates both paths. It is the store-protection guarantee, so it
        may not be a derived side effect of the coalescing window.
        """
        now = self.clock()
        if now - self._last_collect_at < self.config.collect_memo_sec:
            return False, ""
        dirty = any(self._dirty.get(key, 0) != self._collected.get(key, 0) for key in self._dirty)
        if dirty and (self._coalesce_until is None or now >= self._coalesce_until):
            return True, "event"
        if self.application.state.streams.count and (
            now - self._last_collect_at >= self.config.stream_producer_interval_sec
        ):
            return True, "tick"
        return False, ""

    def _collect(self, reason: str) -> None:
        """Run one collection outside the lock, then reconcile the bookkeeping.

        A failure is swallowed and retried on the next pass, exactly as the
        producer this replaces did: the per-harness failure boundary already
        reports the cause, and a coordinator that died on one bad read would
        leave every connected dashboard frozen with no indication why.
        """
        with self._lock:
            observed = dict(self._dirty)
            self._coalesce_until = None
        now = self.clock()
        if reason == "tick" and not self._worth_collecting(now):
            with self._lock:
                self._last_collect_at = now
                self._bump("skipped.probe")
            return
        try:
            self.application.collect_json(show_all=False)
        except Exception as exc:  # noqa: BLE001 (a bad read must not stop the loop)
            runtime_io.diag(f"Cargento: coordinator collection failed: {exc}", self.diagnostic_sink)
            return
        finally:
            with self._lock:
                self._last_collect_at = self.clock()
        with self._lock:
            self._bump(f"collected.{reason}")
            # Only the generations captured before the read are marked done. A
            # harness whose generation moved during the collection stays dirty,
            # because a store_changed hint cannot be recovered by replaying
            # overlays over a read that predates it.
            self._collected.update(observed)

    def _worth_collecting(self, now: float) -> bool:
        """Whether a periodic tick has to read the stores.

        Only ever used to skip. The probe's false negative means a probe-negative
        answer is not proof that nothing changed, so the unconditional
        reconciliation below is what bounds it.
        """
        if now - self._last_reconcile_at >= self.config.reconcile_interval_sec:
            self._last_reconcile_at = now
            self._probe_stamp = runtime_probe.stamp(self.config)
            return True
        current = runtime_probe.stamp(self.config)
        moved = runtime_probe.changed(self._probe_stamp, current)
        self._probe_stamp = current
        return moved
