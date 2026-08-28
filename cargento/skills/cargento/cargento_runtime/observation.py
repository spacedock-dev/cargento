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

## Why an outstanding ask forces collections

`AskRegistry.pending` is both what renders an ask's card and what expires it, so
until `_due` knew about asks a question raised with no browser tab open never
appeared, never expired and never released its slot. `_due` therefore treats an
unresolved ask as a reason to collect on its own, and `note_ask` pulls that
collection forward to the registration instead of the next tick. The registry
sweeps on registration too, so neither half depends on the other.

## What this phase does not do

An `input_requested` is exempt from the coalescing delay, and now really is:
`_record` sets `_urgent` for a needs-input overlay and `_due` honours it. It was
documented here for two phases before anything implemented it, which was
invisible because `event_coalesce_sec` is 0.1 and `collect_memo_sec` is 2.5, so
the window it skips was 4% of the wait.

It still respects the collection floor, so a permission alert publishes at the
next allowed collection instant: measured at 2864 ms worst case, against 177 ms
when the floor is already open, and against the 5 second poll it replaced.

Publishing an overlay-only revision would remove even that, and the design
describes it, but it means retaining a live collection rather than the bytes
retained today, and that is a larger change than the earlier note here suggested.
The accurate obstacle, since the wrong one was named for two phases:

- `assign_display_ids` is *not* it. It derives `session["session"]` from `sid`
  every time and never from its own previous output, so it is idempotent over a
  fixed row set and re-running it is safe.
- `events.apply_patch` is. It overwrites `state`, `state_detail`, `active`,
  `blocked_since`, `acquisition` and `finished_at` in place with no unpatched
  base kept, so the collector's own values are gone and an expiring overlay
  cannot be undone.
- Two things would also have to be redone per republish: the Claude collector
  writes clock-derived `elapsed_h` and `updated_ago` into the task dicts embedded
  in a row, and `collect()` both sorts on `state` and counts its summary from
  already-patched rows.

`scripts/bench_event_latency.py` measures what the floor actually costs, so that
trade is decided by a number rather than by this paragraph.

## How each overlay kind retires

Stated together because handling two of the three and forgetting the third is the
defect this table exists to prevent. Twice now a kind has been given a retirement
rule one ticket at a time (DRC-4097, then DRC-4101), and both times the gap was
found from a screenshot rather than from a test.

| Kind | Deadline | Retired by activity |
| -- | -- | -- |
| Working | `overlay_working_ttl_sec` after its event | n/a — the state activity implies |
| Needs input | none: a real wait outlasts any timeout | `own_activity`, the parent alone |
| Idle | none: a stop is a fact, not a guess | `session_activity`, the whole tree |

The completion mark is in the table's spirit but not in the ledger: `_finished`
holds the last stop per session outside `_overlays`, because `session_ended` pops
that ledger whole and a `claude -p` run's stop and exit arrive together. It is
retired by an overlay saying the session is working or waiting, by the reducer's
`session_activity` guard on the way to the row, and by a collection that stops
producing the row at all — the third being its only bound, since no event ends it.

The two activity rules differ because the questions differ. A wait ends when the
*parent* moves, since the parent is what a human answers; a background agent
writing says nothing about whether anyone replied. Idleness ends when *anything
under the session* moves, since a running subagent proves the session is not idle
however long its parent transcript has been parked — which is what a long
workflow looks like from here, and what made a session generating 4,000 tokens a
minute publish as Idle.

Both guards are one-sided on purpose: they suppress an overlay, never invent one.
An unreported activity stamp arrives as 0 and leaves the overlay standing, so a
harness whose collector fills neither field keeps the event path authoritative
rather than losing its alerts to a field it never sets.
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from typing import TYPE_CHECKING, Any

from cargento_runtime import events as runtime_events
from cargento_runtime import git_status as runtime_git
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

# `_dirty` is keyed by harness, and this is the one key that is not a harness: a
# registered ask is a fact about this runtime rather than about any store. The
# generation maps are only ever compared against each other, key for key, so a
# synthetic key rides them safely. The asterisk is what keeps it from ever
# colliding with a harness id.
ASK_GENERATION = "*ask"


def _spawn_thread(run: Callable[[], None]) -> None:
    """One daemon thread per probe, matching `quota._spawn_thread`.

    A pool would bound the thread count, and it is not worth one here: the probe
    fires on `session_ended` only, at most once per edge, and the timeout bounds
    how long each lives.
    """
    threading.Thread(target=run, name="cargento-git-probe", daemon=True).start()


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
        # (harness, sid) -> the stamp of the last stop observed for it. Outside
        # `_overlays` on purpose: `session_ended` pops that ledger whole, and for
        # `claude -p` the stop and the exit arrive back to back, so a mark held
        # there is destroyed milliseconds after the only sessions this answers
        # for have finished (DRC-4035). Narrowing what `session_ended` retires
        # was the alternative, and it is worse: the event covers `/clear` as well
        # as exit, so a cleared session would read finished forever.
        self._finished: dict[SessionKey, float] = {}
        # (harness, sid) -> the last end-of-session git reading for it. Outside
        # `_overlays` for the same reason `_finished` is: `session_ended` pops that
        # ledger whole, and `session_ended` is the only edge that produces one of
        # these, so a reading held there would be destroyed by the very event that
        # earned it. Absent means not probed, which is what the row publishes, and
        # `_mark_finished` retires an entry alongside the stop mark it belongs to:
        # a session working or waiting again has a tree the reading no longer
        # describes, and the reducer's own clears lapse with the overlay that
        # carries them while a reading does not.
        self._git: dict[SessionKey, runtime_git.GitStatus] = {}
        # Injected so the tests can drive the edge without a repository, and so a
        # probe can be made to block on demand: AC3's oracle is that `submit`
        # returns while this is still running.
        self._git_prober: Callable[[str], runtime_git.GitStatus | None] = self._probe_git
        self._spawn: Callable[[Callable[[], None]], None] = _spawn_thread
        # sid -> (first seen, attempts). An event whose session no collection has
        # produced yet waits here. It never renders and never creates a row.
        self._pending: dict[SessionKey, tuple[float, int]] = {}
        self._dirty: dict[str, int] = {}
        self._collected: dict[str, int] = {}
        self._last_collect_at = 0.0
        self._last_reconcile_at = 0.0
        self._coalesce_until: float | None = None
        # Set by a needs-input overlay, cleared by the collection that carries it.
        # A permission alert is the one transition a person is actively waiting on,
        # so it does not wait out a window whose whole purpose is to batch the
        # events nobody is watching.
        self._urgent = False
        # The last revision this coordinator's own collection produced. A
        # repeat means the application's floor served the read from bytes it
        # serialized before the event arrived.
        self._last_revision: tuple[float, int] | None = None
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
        probe_cwd: str | None = None
        with self._lock:
            self._bump(f"event.{event.event}")
            if runtime_events.retires_overlays(event):
                # Non-destructive: the ledger for this session goes, the row does
                # not. Only a collector may decide a session is gone.
                self._overlays.pop(key, None)
                self._pending.pop(key, None)
                self._bump("retired")
                if self.config.git_probe_enabled and event.cwd:
                    # Noted here and dispatched below, once the lock is released.
                    probe_cwd = event.cwd
            elif overlay is not None:
                self._remember(key, overlay)
                self._mark_finished(key, overlay)
            if runtime_events.requires_reconcile(event):
                # Force the next pass to be a real collection rather than one the
                # probe may skip: a rewritten transcript is not repaired by
                # replaying overlays over a cached read.
                self._last_reconcile_at = 0.0
                self._probe_stamp = None
            self._dirty[event.harness] = self._dirty.get(event.harness, 0) + 1
            if overlay is not None and overlay.kind == runtime_events.OVERLAY_NEEDS_INPUT:
                # The exemption this module's docstring has always claimed, and
                # which nothing implemented until it was measured for DRC-4092.
                # It bypasses the coalescing window only. The floor still gates
                # the collection, because the floor is the store-protection
                # guarantee and may not become a derived side effect.
                self._urgent = True
            deadline = now + self.config.event_coalesce_sec
            if self._coalesce_until is None:
                # Fixed, not sliding. A sliding window never closes under a
                # sustained burst, and the board would stop updating entirely.
                self._coalesce_until = deadline
            self._wake.notify_all()
        if probe_cwd is not None:
            # Off this thread AND outside the lock, and both halves are load-bearing.
            # `submit` is reached from `http_api`'s request handler on a
            # ThreadingHTTPServer thread, behind the hook client's 2 s timeout, and
            # `git status` on a large tree routinely exceeds that. Run inline it would
            # hold the coordinator lock for the probe's duration, stalling every other
            # event and the collection loop, and hold the harness's own SessionEnd
            # hook open past its timeout. Dispatching from inside the `with` block
            # above would fix only the second of those.
            cwd = probe_cwd
            self._spawn(lambda: self._probe_and_mark(key, cwd))
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

    def _mark_finished(self, key: SessionKey, overlay: runtime_events.Overlay) -> None:
        """Remember, or forget, the stop this session last had observed.

        A subagent overlay is neither. A child transition says nothing about
        whether the parent's turn ended, and the reducer's activity guard already
        retires the mark when anything under the session writes.
        """
        if overlay.kind in {runtime_events.OVERLAY_WORKING, runtime_events.OVERLAY_NEEDS_INPUT}:
            self._finished.pop(key, None)
            # And the reading taken at that stop, for the same reason: it
            # describes a tree this session has since resumed over. The reducer
            # nulls the pair while such an overlay is live, but the overlay
            # lapses and the reading would outlive it — so the retirement has to
            # happen where the mark's does rather than only at render time.
            self._git.pop(key, None)
            return
        if overlay.kind != runtime_events.OVERLAY_IDLE:
            return
        if key not in self._finished and len(self._finished) >= (
            self.config.event_overlay_max_sessions
        ):
            # Refused rather than evicted, for the reason `_remember` gives: this
            # is bounded by the same cap and a mark is worth less than the alert
            # an eviction would drop, so it does not get to make room either.
            self._bump("finished.refused")
            return
        # max, not assignment: delivery is at-least-once and possibly reordered,
        # so a redelivered older stop must not pull the mark backwards.
        self._finished[key] = max(self._finished.get(key, 0.0), overlay.at)

    def _probe_git(self, cwd: str) -> runtime_git.GitStatus | None:
        """The real probe, bound to this run's timeout. Replaced wholesale in tests."""
        return runtime_git.probe(cwd, timeout_sec=self.config.git_probe_timeout_sec)

    def _probe_and_mark(self, key: SessionKey, cwd: str) -> None:
        """Run one probe off-thread, then take the lock only to record two scalars.

        The catch is blind for the reason `quota` gives at its own boundary: this
        runs on a thread nobody joins, so an escaping exception would be printed by
        the interpreter and lost. No reading is worth a diagnostic either, because
        anything git raises here can carry a path in its text.
        """
        try:
            result = self._git_prober(cwd)
        except Exception:  # noqa: BLE001 — a raising probe must not kill its own thread
            with self._lock:
                self._bump("git.failed")
            return
        if result is None:
            return
        with self._lock:
            self._mark_git(key, result)

    def _mark_git(self, key: SessionKey, result: runtime_git.GitStatus) -> None:
        """Record a reading, refusing rather than evicting at the same cap.

        Bounded by `event_overlay_max_sessions` for the reason `_remember` gives:
        evicting somebody else's reading to make room would drop whichever happened
        to be oldest, and a reading does not get to cost an alert.
        """
        if key not in self._git and len(self._git) >= self.config.event_overlay_max_sessions:
            self._bump("git.refused")
            return
        self._git[key] = result

    def git_for(self, harness: str, sid: str) -> runtime_git.GitStatus | None:
        """This row's end-of-session git reading, or None if it was never probed.

        None is the whole of the disclosure and it covers every cause: a harness
        whose adapter maps no session-end event, `--no-git`, a directory that is not
        a repository, an event with no `cwd`, git absent from PATH, a probe that
        timed out, and a session observed working or waiting since the end that
        produced the reading — `_mark_finished` retires the reading there, with the
        stop mark it belongs to. `acquisition` cannot see any of them — it separates
        adapter-less harnesses from the rest, and Codex and Antigravity have adapters
        and still never reach this.
        """
        with self._lock:
            return self._git.get((harness, sid))

    def finished_at(self, harness: str, sid: str) -> float:
        """When this row's turn last stopped, or 0.0 if no stop was ever seen.

        0.0 means "not observed", never "did not finish": the six harnesses with
        no event adapter can never earn a value here, which is what the row's
        `acquisition` marker discloses instead.
        """
        with self._lock:
            return self._finished.get((harness, sid), 0.0)

    def note_ask(self) -> None:
        """A session registered a question. Bring the next collection forward.

        The card is drawn by a collection and by nothing else, so without this
        the register route's only wake path was the revision some later
        collection happened to publish. Measured before this existed: 3.2 s
        under `--no-events`, where `lifecycle.run_producer` is running, and 18.2
        to 22.3 s on the default build, where what eventually noticed was the
        page's own 20-second fallback poll. `docs/design-ask-lane.md` records the
        earlier decision not to add this seam, and why that reasoning was wrong.

        Called from a handler thread, and it must be called once the registry has
        let go: this takes `_lock`, and `_due` reads the registry while holding
        `_lock`, so the order is `_lock` then the registry lock and never the
        other way. A caller still holding a registry lock here would be the one
        thing that closes that cycle. `_due` and `AskRegistry` carry the same
        note.
        """
        with self._lock:
            # A generation rather than a flag, for the reason `_record` uses one:
            # `_collect` retires only the generations it captured before its read,
            # so an ask registered during a collection stays dirty instead of
            # being marked done against a payload that predates it.
            self._dirty[ASK_GENERATION] = self._dirty.get(ASK_GENERATION, 0) + 1
            # The same reason `reconcile_required` clears it: a session that has
            # just stopped to ask a person something has been working, and the
            # pass that renders its card should be a real read of the stores
            # rather than one the probe is allowed to skip.
            self._last_reconcile_at = 0.0
            self._wake.notify_all()

    def _bump(self, name: str) -> None:
        """Count something, under `_lock`. Diagnostics only, never control flow."""
        self.counters[name] = self.counters.get(name, 0) + 1

    # ---- the overlay source aggregate reads -----------------------------

    def overlays_for(self, harness: str, sid: str) -> list[runtime_events.Overlay]:
        """Live overlays for one collected row, or an empty list."""
        with self._lock:
            ledger = self._overlays.get((harness, sid))
            return list(ledger.values()) if ledger else []

    def ledger_report(self) -> dict[str, Any]:
        """Every live overlay, flattened, for `/api/overlays`.

        Read-only, and it publishes the reducer's inputs rather than a verdict.
        Why it exists, how to read it, and what `counters` disambiguates are in
        docs/design-needs-input.md (N-5).

        `time_gate_open` is `Overlay.applies`, named for what it is because
        `applies` on the wire reads as "this overlay won", which it does not
        mean: ordering and the activity guards both run after this.

        Carries no session content: a collector key, a kind, three timestamps,
        and a hook-supplied subagent id capped at ingress, all of which
        `/api/data` already publishes per row.
        """
        with self._lock:
            # Inside, unlike `_record`: this returns `now` and values computed
            # from it, so they have to be one instant.
            now = self.clock()
            rows = [
                row
                for _key, ledger in sorted(self._overlays.items())
                for row in runtime_events.overlay_rows(ledger.values(), now=now)
            ]
            pending = sorted(f"{harness}/{sid}" for harness, sid in self._pending)
            counters = dict(self.counters)
            arrival_seq = self._arrival_seq
        return {
            "now": now,
            "arrival_seq": arrival_seq,
            "overlays": rows,
            "pending_rows": pending,
            "counters": counters,
        }

    def drop_counters(self) -> dict[str, int]:
        """The counters that mean an envelope arrived and left no overlay.

        The whole set would work and would also carry `event.*`, which moves on
        every hook and would swamp the comparison a dispute record is kept for.
        """
        with self._lock:
            return {
                name: count
                for name, count in self.counters.items()
                if name.startswith(("reject.", "overlay.", "pending.")) or name == "retired"
            }

    def note_rows(self, keys: set[SessionKey]) -> None:
        """Tell the ledger which rows a collection actually produced.

        This is how a pending event resolves. An overlay for a session no
        collection has produced cannot render, so it waits here to be attached by
        a later collection, and expires with a counter if none ever comes. That
        preserves a first-session permission prompt without letting a forged or
        mistyped id invent a session.

        It is also the only bound on the completion marks, which no event
        retires: a mark for a session no longer collected and holding no overlay
        can never render again, so it goes. Holding it while an overlay is still
        pending is what stops a collection already in flight when the stop
        arrived from dropping the mark of a session it had not yet seen.
        """
        now = self.clock()
        with self._lock:
            for key in [k for k in self._finished if k not in keys and k not in self._overlays]:
                del self._finished[key]
            for key in [k for k in self._git if k not in keys and k not in self._overlays]:
                del self._git[key]
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
        if dirty and (self._urgent or self._coalesce_until is None or now >= self._coalesce_until):
            return True, "event"
        # An outstanding ask is its own reason to collect. `AskRegistry.pending`
        # is what renders the card and what sweeps the table, and a dashboard
        # with no browser tab open has neither a dirty generation nor a stream to
        # ride on: the lane wedged shut on exactly the long unattended run it
        # exists for. `count` is unresolved only, so an answered ask waiting for
        # its poller does not hold this open.
        #
        # Rate-limited by the floor above and by nothing else. Gating it on
        # `stream_producer_interval_sec`, as the tick below is, would delay the
        # first render of a fresh ask by up to that interval, which is the
        # latency this seam exists to remove.
        #
        # The registry lock is taken here, under `_lock`. That is the only
        # direction it ever runs: nothing in `asks` calls into this class, and
        # `note_ask` is called after `register` has returned.
        if self.application.state.asks.count:
            return True, "ask"
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
            # Cleared here rather than after the read, so a needs-input overlay
            # that arrives *during* this collection still forces the next one:
            # this read may have started before its event was recorded.
            self._urgent = False
        now = self.clock()
        if reason == "tick" and not self._worth_collecting(now):
            with self._lock:
                self._last_collect_at = now
                self._bump("skipped.probe")
            return
        try:
            # The revision, not the body: comparing it is how this tells a real
            # collection from one the application's own floor satisfied, and it
            # needs no access to the snapshot the application owns.
            revision, _ = self.application.collect_json(show_all=False)
        except Exception as exc:  # noqa: BLE001 (a bad read must not stop the loop)
            runtime_io.diag(f"Cargento: coordinator collection failed: {exc}", self.diagnostic_sink)
            return
        finally:
            with self._lock:
                self._last_collect_at = self.clock()
        reused = revision == self._last_revision
        self._last_revision = revision
        if reused:
            # The floor is enforced twice, by two clocks: this coordinator's
            # `_last_collect_at` and the application's own snapshot age. A fresh
            # coordinator has never collected, so its floor is open while the
            # application's is not, and `collect_json` then returns the revision it
            # published *before* this event existed. Marking the generation done
            # here would retire the event against a read that predates it, and
            # nothing would republish: measured for DRC-4092, a permission alert
            # arriving in that gap never rendered at all until an unrelated event
            # or a five-second stream tick came along.
            #
            # So leave it dirty. `_last_collect_at` is already advanced above, so
            # the retry is one floor away rather than a spin, and the wake is
            # scheduled for exactly then: `_sleep_for` consults only
            # `_coalesce_until`, so without this the worker would sleep a whole
            # `stream_producer_interval_sec` and the retry would land at five
            # seconds rather than at the floor. Measured at 5.2 s before this line
            # existed and 2.5 s after it.
            with self._lock:
                self._bump("reused.floor")
                self._coalesce_until = self._last_collect_at + self.config.collect_memo_sec
            return
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
