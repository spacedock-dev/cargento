"""Check an annotated session against what you asked for, without being asked.

The implementation
[DEC-18](docs/design-reading-a-session.md#dec-18-an-unasked-reading-is-permitted-and-gated-on-delivery-first)
permits. Off by default, evaluated on an observed state change rather than per
turn, raising only a departure, delivered through the notification lane, and
bounded per session and per day.

An orchestrator rather than a leaf, and deliberately not a method on
`Application`: it reaches `reading` for the producer, `project_context` for the
evidence, `annotations` for the baseline, `departures` for the record and
`notifications` for the raise, and `aggregate` imports none of those last two
halves today. Keeping it here is what stops the application growing an edge to
`project_context` for one feature.

## Why it never runs on the collection thread

Each reading is a `codex` subprocess at `reasoning_effort=max`. `consider` is
called from inside a collection, does only dictionary work, and hands the
reading to a worker, exactly as `quota.request_fetch` hands a network read to
one. A collection that blocked on this would freeze every connected dashboard
for minutes.

One reading in flight for the whole board, not one per session. The ruling says
to measure the real rate on a real board before choosing the cap, and a board with
forty annotated sessions crossing a state boundary together would otherwise
start forty subprocesses at once. The bound is deliberately the most cautious
one that still makes progress.

## Why the caps render rather than pass quietly

The ruling's second amendment. The reader is by construction not present, so
"nothing departed" and "nothing was checked" must never render alike, and an
exhausted cap is the second of those wearing the first's clothes. `departures`
owns the four sentences so this module cannot word them a fifth way.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

from . import annotations as annotation_store
from . import departures, notifications
from . import io as runtime_io
from . import project_context as runtime_project_context
from . import reading as runtime_reading
from . import state as runtime_state

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from .config import RuntimeConfig
    from .state import RuntimeState

# The lane name this writes into the delivery record, beside `gate`, `ask` and
# `hook`. A value rather than a shape change, which is what DRC-4540 built the
# record for.
LANE = "departure"

# The window the per-day cap counts over, owned by `departures` because the
# sentence that reports a spent day cap is chosen there and read by three
# surfaces. Re-exported under the old name, which the lane and its tests use.
DAY_SEC = departures.DAY_SEC


def _spawn(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="cargento-unasked", daemon=True).start()


class Lane:
    """The unasked reading lane, attached only when the switch is on.

    Constructed inert. `consider` is the only entry point the collection calls,
    and it starts at most one worker per call.
    """

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        popup_notifier: Callable[[str, str], str | None],
        diagnostic_sink: Callable[[str], None] = print,
        clock: Callable[[], float] = time.time,
        harness_label: Callable[[str], str] | None = None,
        produce: Callable[..., tuple[runtime_reading.Assessment | None, str, bool]] | None = None,
        facts_for: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
        spawn: Callable[[Callable[[], None]], None] = _spawn,
    ) -> None:
        self.config = config
        self.popup_notifier = popup_notifier
        self.diagnostic_sink = diagnostic_sink
        self.clock = clock
        # The registry's own display label. Without it the banner says the
        # collector key, so a row badged Antigravity produced a notification
        # headed `antigravity`, where every other popup on this board says what
        # the board says.
        self.harness_label = harness_label or (lambda key: key)
        # Injected so a test can assert on the ABSENCE of a subprocess, which is
        # the first acceptance criterion and cannot be asserted against a
        # function that decides for itself whether to run one.
        self.produce = produce or runtime_reading.produce
        self.facts_for = facts_for or self._facts
        self.spawn = spawn

    def consider(
        self,
        state: RuntimeState,
        rows: Sequence[Mapping[str, Any]],
        entries: Sequence[annotation_store.Annotation],
        *,
        now: float,
    ) -> None:
        """Note every row's state, and start at most one reading.

        Every row's state is recorded whether or not it is a candidate, and
        that is load bearing: an unannotated session that is annotated later
        must not read as a change the moment the annotation lands, and a session
        held off by a cap must not bank its change and fire the instant the cap
        clears.
        """
        # Read at most once per collection, and only once a candidate has been
        # found. `_claim` used to read it per row, which is a file read per row
        # per collection on a board where most rows are not candidates at all.
        stored: tuple[departures.Check, ...] | None = None
        # Two gates and they are not the same rule, which is why both stay.
        # `started` is one reading per COLLECTION and holds structurally: the
        # loop stops offering after the first. The in-flight slot is one reading
        # at a TIME and holds across collections. Relying on the slot alone was
        # tried and is wrong: it is released when the worker finishes, so the
        # guarantee would rest on a `codex` subprocess outliving this loop,
        # which is true today and is not a property of this function. Measured
        # with a synchronous worker, twenty candidate rows started twenty
        # readings.
        started = False
        for row in rows:
            harness = str(row.get("harness") or "")
            sid = str(row.get("sid") or "")
            if not harness or not sid:
                continue
            key = f"{harness}:{sid}"
            changed = self._note(state, key, str(row.get("state") or ""))
            if started or not changed:
                continue
            entry = annotation_store.find(entries, harness, sid)
            if entry is None or not entry.get("revisions"):
                continue
            if stored is None:
                stored = departures.load(self.config)
            if not self._claim(state, key, stored, now=now):
                continue
            started = True

            def work(
                row: Mapping[str, Any] = row,
                entry: annotation_store.Annotation = entry,
                key: str = key,
            ) -> None:
                # Bound as defaults rather than closed over, for the reason
                # `quota.request_fetch` binds its vendor that way: a closure
                # would see the loop's last row.
                self._run(state, row, entry, key, now)

            try:
                self.spawn(work)
            except Exception as exc:  # noqa: BLE001 (a thread that will not start is not a raise)
                # The slot is taken before the worker exists, so a `spawn` that
                # throws would hold it for the life of the process and the lane
                # would go silent in a way that reads exactly like a board with
                # nothing to raise. This runs inside a collection, so it must
                # not propagate either.
                self._release(state, key)
                runtime_io.diag(
                    f"Cargento: could not start the unasked reading for {key}: {exc}",
                    self.diagnostic_sink,
                )

    def _note(self, state: RuntimeState, key: str, session_state: str) -> bool:
        """Record this row's state and say whether it differs from the last.

        A row seen for the first time is NOT a change. The board restarts, and
        treating every row of the first collection as a transition would check
        the whole board at once on a boot nobody asked for.
        """
        with state.unasked_lock:
            previous = state.unasked_seen.get(key)
            runtime_state.bounded_put(
                state.unasked_seen, key, session_state, limit=self.config.max_cache_entries
            )
            return previous is not None and previous != session_state

    def _claim(
        self,
        state: RuntimeState,
        key: str,
        stored: Sequence[departures.Check],
        *,
        now: float,
    ) -> bool:
        """Take the board's one reading slot, or say why not.

        Every gate is checked BEFORE the subprocess, for `reading.produce`'s
        reason: a gate that answers after spending the reader's capacity has not
        held.

        The in-flight set is one reading at a TIME, across collections. One
        reading per collection is `consider`'s own flag, for the reason stated
        there: the two are different rules and the slot alone does not give the
        second.
        """
        harness, _, sid = key.partition(":")
        # CHECKS, not raises. Counting raises bounds nothing, because a healthy
        # board raises nothing: measured on that version, five sessions ran 480
        # `codex` subprocesses in a simulated day against a daily cap of 12.
        mine, today = departures.counts(stored, harness, sid, since=now - DAY_SEC)
        with state.unasked_lock:
            if state.unasked_inflight:
                return False
            if now - state.unasked_last.get(key, 0.0) < self.config.unasked_session_floor_sec:
                return False
            if mine >= self.config.unasked_session_cap:
                return False
            if today >= self.config.unasked_daily_cap:
                return False
            state.unasked_inflight.add(key)
            runtime_state.bounded_put(
                state.unasked_last, key, now, limit=self.config.max_cache_entries
            )
        # The producer's own per-session slot, taken AFTER this lane's gates and
        # released in `_run`. Without it a reader pressing `Ask for a reading`
        # while an unasked one runs starts a second subprocess on one session,
        # which is the thing that slot exists to refuse. Taken outside the lock
        # because it is a different lock.
        if not runtime_reading.claim(self.config, key):
            self._release(state, key)
            return False
        return True

    def _release(self, state: RuntimeState, key: str) -> None:
        """Give both slots back. Called on every exit path the claim reached."""
        with state.unasked_lock:
            state.unasked_inflight.discard(key)
        runtime_reading.release(self.config, key)

    def _facts(
        self, state: RuntimeState, row: Mapping[str, Any], now: float
    ) -> Sequence[Mapping[str, Any]]:  # pragma: no cover - exercised through the lane
        """The observed record this reading reads, the way `/api/reading` gets it."""
        context = runtime_project_context.collect(
            self.config,
            state,
            [dict(row)],
            str(row.get("project_key") or row.get("project") or ""),
            now=now,
            refresh=False,
            focus=(str(row.get("harness")), str(row.get("sid"))),
            model_consent=False,
        )
        semantic = context.get("semantic") if isinstance(context, dict) else None
        facts = semantic.get("facts", []) if isinstance(semantic, dict) else []
        return list(facts) if isinstance(facts, list) else []

    def _run(
        self,
        state: RuntimeState,
        row: Mapping[str, Any],
        entry: annotation_store.Annotation,
        key: str,
        now: float,
    ) -> None:
        """One reading, off the collection thread, and the raise it may earn."""
        try:
            self._read_and_raise(state, row, entry, now)
        except Exception as exc:  # noqa: BLE001 (a bad reading must not kill the lane)
            runtime_io.diag(
                f"Cargento: unasked reading failed for {key}: {exc}", self.diagnostic_sink
            )
        finally:
            self._release(state, key)

    def _read_and_raise(
        self,
        state: RuntimeState,
        row: Mapping[str, Any],
        entry: annotation_store.Annotation,
        now: float,
    ) -> None:
        assessment, _why, _spent = self.produce(
            self.config,
            row,
            entry["revisions"],
            self.facts_for(state, row, now),
            now=now,
            stamp_text=f"unasked check at {time.strftime('%H:%M', time.localtime(now))}",
            model=runtime_reading.CodexReadingModel(self.config),
        )
        if assessment is None:
            # A withheld reading spent nothing: `produce` refuses before the
            # subprocess. Recording a check here would count a spend that did
            # not happen against the reader's cap.
            return
        raised = self._departures(assessment, row, now)
        # The check is recorded whether or not it found anything, because it
        # spent a subprocess either way and that is what the caps bound. A check
        # that raised nothing is one row with an empty constraint, which is also
        # what lets the board say THIS session was looked at.
        landed = departures.record(
            self.config,
            raised or [self._check(assessment, row, now)],
            diagnostic_sink=self.diagnostic_sink,
        )
        if not raised:
            # The ruling refuses to tell the reader unasked that nothing
            # departed: an unasked reassurance is the output the evidence-floor
            # ruling called most damaging. The board says it on return, where
            # they came looking.
            return
        if not landed:
            # Raised nowhere rather than raised and unreviewable. A banner
            # saying a departure was found, over a board that has no record of
            # one and says nothing departed, is the board contradicting its own
            # alert. The write already logged why it failed.
            runtime_io.diag(
                "Cargento: a departure was found and could not be recorded, so it was not "
                "raised; the board would have contradicted the notification",
                self.diagnostic_sink,
            )
            return
        self._raise(row, raised, now)

    def _check(
        self, assessment: runtime_reading.Assessment, row: Mapping[str, Any], now: float
    ) -> departures.Check:
        """The row for a reading that raised nothing: the spend, and its baseline."""
        return {
            "harness": str(row.get("harness") or ""),
            "sid": str(row.get("sid") or ""),
            "at": now,
            "constraint": "",
            "clause": "",
            "reading": "",
            "evidence": "",
            "revision": assessment["revision_read"],
            "cutoff": now,
            "cutoff_text": str(assessment.get("cutoff") or ""),
            "withdrawn": False,
        }

    def _departures(
        self,
        assessment: runtime_reading.Assessment,
        row: Mapping[str, Any],
        now: float,
    ) -> list[departures.Check]:
        """Only the criteria that departed, with the baseline each rested on.

        The baseline is recorded here rather than re-derived, which is the
        ruling's first amendment: by the time this is read the annotation may be
        at a later revision and the window has moved.
        """
        out: list[departures.Check] = []
        for name, criterion in assessment["criteria"].items():
            if criterion.get("result") != runtime_reading.RESULT_DEPARTURE:
                continue
            out.append(
                {
                    "harness": str(row.get("harness") or ""),
                    "sid": str(row.get("sid") or ""),
                    "at": now,
                    "constraint": name,
                    "clause": str(criterion.get("clause") or ""),
                    "reading": str(criterion.get("detail") or ""),
                    "evidence": ", ".join(criterion.get("cites") or ()),
                    "revision": assessment["revision_read"],
                    # The moment the reading ran, which is when the record it
                    # read WAS the record. `Assessment.cutoff` is prose for the
                    # page ("12 entries, 3 by you"), so parsing it as a number
                    # returned 0 on every real reading and the amendment's
                    # cutoff was never actually recorded.
                    "cutoff": now,
                    "cutoff_text": str(assessment.get("cutoff") or ""),
                    # Set by `departures.withdraw` when the reader clears the
                    # words this read, never by the lane.
                    "withdrawn": False,
                }
            )
        return out

    def _raise(
        self, row: Mapping[str, Any], raised: Sequence[departures.Check], now: float
    ) -> None:
        """One banner per reading, not one per departure.

        A reading that departed on both Goal and Expected Output is one thing
        that happened, and two banners about it would read as two events.
        """
        label = self.harness_label(str(row.get("harness") or ""))
        first = raised[0]
        # The constraint first and the model's sentence after. `notify_mac`
        # bounds the body and `safe_text` keeps the HEAD, so a reading long
        # enough to be clipped loses its tail rather than its subject. The
        # reading first published a sentence cut mid-claim under a title saying
        # the session may be going off track.
        detail = (
            f"{first['constraint']}: {first['reading']}"
            if len(raised) == 1
            else f"{len(raised)} constraints departed, including {first['constraint']}"
        )
        outcome = self.popup_notifier(notifications.departure_title(label), detail)
        notifications.record_outcome(
            self.config, first["harness"], first["sid"], LANE, outcome, now
        )


def published(
    config: RuntimeConfig,
    stored: Sequence[departures.Check],
    row: Mapping[str, Any],
    *,
    now: float,
) -> dict[str, Any]:
    """What one session's row says about unasked checks.

    Whether this session was checked is read from the store PER SESSION rather
    than from the lane's existence. It used to be board-wide, so a session with
    no annotation at all, or one the lane had never reached, rendered "Cargento
    has checked this session and found nothing to raise" on the strength of the
    switch being on. That is the one sentence this feature must never get wrong,
    because the reader was not there to know which of the two they are looking
    at.

    The four sentences are `departures`', not this module's, so the board cannot
    word an exhausted cap one way here and another way on the review surface.
    """
    harness = str(row.get("harness") or "")
    sid = str(row.get("sid") or "")
    return {
        "departures": departures.published(stored, harness, sid),
        "departure_why": departures.why(config, stored, harness, sid, now=now),
        # Whether the list above is a measurement at all. It is `[]` both for a
        # session nobody read and for one that was read and had nothing to
        # raise, and the review surface counts it: a session the lane had never
        # reached rendered a departure figure of 0 under the sentence saying it
        # had not been checked. `departures.checked` is the same test the
        # sentence uses, so the figure and the sentence cannot disagree.
        "departure_checked": departures.checked(stored, harness, sid),
    }
