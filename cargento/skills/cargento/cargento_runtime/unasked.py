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

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from .config import RuntimeConfig
    from .state import RuntimeState

# The lane name this writes into the delivery record, beside `gate`, `ask` and
# `hook`. A value rather than a shape change, which is what DRC-4540 built the
# record for.
LANE = "departure"

# The window the per-day cap counts over. Rolling rather than calendar, because
# the reader this exists for walked away at an arbitrary hour: a midnight reset
# would hand a whole fresh allowance to a board nobody is watching, and a
# calendar day would need a timezone this runtime does not otherwise carry.
DAY_SEC = 86_400.0


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
        produce: Callable[..., tuple[runtime_reading.Assessment | None, str, bool]] | None = None,
        facts_for: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
        spawn: Callable[[Callable[[], None]], None] = _spawn,
    ) -> None:
        self.config = config
        self.popup_notifier = popup_notifier
        self.diagnostic_sink = diagnostic_sink
        self.clock = clock
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
        stored: tuple[departures.Departure, ...] | None = None
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

            self.spawn(work)

    def _note(self, state: RuntimeState, key: str, session_state: str) -> bool:
        """Record this row's state and say whether it differs from the last.

        A row seen for the first time is NOT a change. The board restarts, and
        treating every row of the first collection as a transition would check
        the whole board at once on a boot nobody asked for.
        """
        with state.unasked_lock:
            previous = state.unasked_seen.get(key)
            state.unasked_seen[key] = session_state
            return previous is not None and previous != session_state

    def _claim(
        self,
        state: RuntimeState,
        key: str,
        stored: Sequence[departures.Departure],
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
            state.unasked_last[key] = now
            return True

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
            with state.unasked_lock:
                state.unasked_inflight.discard(key)

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
            return
        raised = self._departures(assessment, row, now)
        if not raised:
            # A reading that departed from nothing is not a raise, and the
            # ruling refuses to tell the reader so unasked: an unasked
            # reassurance is the output the evidence-floor ruling called most
            # damaging. The board says it on
            # return, where they came looking.
            return
        departures.record(self.config, raised, diagnostic_sink=self.diagnostic_sink)
        self._raise(row, raised, now)

    def _departures(
        self,
        assessment: runtime_reading.Assessment,
        row: Mapping[str, Any],
        now: float,
    ) -> list[departures.Departure]:
        """Only the criteria that departed, with the baseline each rested on.

        `revision_read` and `cutoff` come off the assessment rather than being
        re-derived, which is the ruling's first amendment: by the time this is read
        the annotation may be at a later revision and the window has moved.
        """
        out: list[departures.Departure] = []
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
                    "cutoff": _cutoff(assessment),
                }
            )
        return out

    def _raise(
        self, row: Mapping[str, Any], raised: Sequence[departures.Departure], now: float
    ) -> None:
        """One banner per reading, not one per departure.

        A reading that departed on both Goal and Expected Output is one thing
        that happened, and two banners about it would read as two events.
        """
        label = str(row.get("harness_label") or row.get("harness") or "")
        first = raised[0]
        detail = (
            f"{first['constraint']}: {first['reading']}"
            if len(raised) == 1
            else f"{len(raised)} constraints departed, including {first['constraint']}"
        )
        outcome = self.popup_notifier(notifications.departure_title(label), detail)
        notifications.record_outcome(
            self.config, first["harness"], first["sid"], LANE, outcome, now
        )


def _cutoff(assessment: runtime_reading.Assessment) -> float:
    """The reading's evidence cutoff as an epoch, or 0 when it published none.

    `Assessment.cutoff` is the rendered string the page shows. 0 means the
    reading carried no machine-readable cutoff, and the render says the window
    is unknown rather than inventing one.
    """
    raw = assessment.get("cutoff")
    try:
        return float(raw) if raw not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def published(
    config: RuntimeConfig,
    stored: Sequence[departures.Departure],
    row: Mapping[str, Any],
    *,
    now: float,
    checked: bool,
) -> dict[str, Any]:
    """What one session's row says about unasked checks.

    The four sentences are `departures`', not this module's, so the board cannot
    word an exhausted cap one way here and another way on the review surface.
    """
    harness = str(row.get("harness") or "")
    sid = str(row.get("sid") or "")
    mine, today = departures.counts(stored, harness, sid, since=now - DAY_SEC)
    rows = departures.published(stored, harness, sid)
    if today >= config.unasked_daily_cap:
        why = departures.DAY_EXHAUSTED
    elif mine >= config.unasked_session_cap:
        why = departures.SESSION_EXHAUSTED
    elif not checked:
        why = departures.NEVER_CHECKED
    elif rows:
        why = ""
    else:
        why = departures.NOTHING_DEPARTED
    return {"departures": rows, "departure_why": why}
