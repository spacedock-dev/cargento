"""Steer back's correction, composed without a model (DRC-4681).

Item 7 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
fixes the fields: the goal, each outcome line with its state, and the cited entries' times. The
owner approved the template on 2026-09-28 as exact text, and ruled that the server writes each
entry as a placeholder the page fills with "#n" from its own numbering or drops, because a number
is recomputed on the page and never stored (item 11). So nothing here reads a summary, a command, a
check name, tool output, a reading's detail or a message's words: a fact contributes its time and
its id, and the id travels only inside a placeholder.

`compose` is pure. The route hands it the session's published row, its observed record and the
later-direction floor (`annotations.direction_floor`), and it answers the parts or why there are
none. A line's state is re-derived from the stored reading against the record as it stands now,
with the page's rules for whether a verdict survives (`nextCockpitReadingCriterion`), so the text
never claims a departure the panel beside it has demoted.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from . import copied_corrections, reading

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

# The route's own cap, so a correction this composes is always one the copy route accepts.
CAP_CHARS = copied_corrections.CORRECTION_CAP_CHARS
# Claude Code only, as the copy route is: a correction offered where a paste cannot be recognised
# coming back would count as the reader's own words.
HARNESSES = copied_corrections.HARNESSES

TOO_LONG = "This correction would be longer than 2,000 characters. Shorten a line of your intent."
REASON_NOTHING = "nothing"
REASON_TOO_LONG = "too-long"

# What a placeholder can become on the page: " (#n in Cargento)" for the first number drawn and
# " (#n)" after it. Counted at six digits, so the page's text never passes the cap whatever it
# numbers; a correction within a few characters of 2,000 is refused slightly early instead.
FIRST_NUMBER_MAX_CHARS = len(" (#999999 in Cargento)")
NUMBER_MAX_CHARS = len(" (#999999)")

_DEPARTED = "departed"
_CONSISTENT = "consistent"
_NOT_SHOWN = "not-shown"

Part = str | dict[str, str]


def clock_text(at: float) -> str:
    """Hours and minutes on this machine's clock, the page's `nextSessionClock`."""
    return time.strftime("%H:%M", time.localtime(at))


def _placeholder(fact: Mapping[str, Any]) -> dict[str, str]:
    return {"entry": str(fact.get("fact_id") or "")}


def _own(row: Mapping[str, Any], facts: Iterable[Any]) -> list[dict[str, Any]]:
    """This session's facts that carry an id, in the page's order: time, then id."""
    who = {"harness": row.get("harness"), "sid": row.get("sid")}
    own = [
        f
        for f in facts
        if isinstance(f, dict) and f.get("fact_id") and f.get("source_session") == who
    ]
    return sorted(
        own, key=lambda f: (reading.valid_prompt_time(f.get("at")) or 0.0, str(f["fact_id"]))
    )


def _as_evidence(fact: Mapping[str, Any], harness: str) -> dict[str, Any]:
    """A published fact in the names `reading.check_supports` and `demonstrates_work` read."""
    work = reading.WORK_EVIDENCE_BY_HARNESS.get(harness, frozenset())
    return {
        **fact,
        "stale": fact.get("before_last_change") is True,
        "work": str(fact.get("type") or "") in work,
    }


def _later_directions(facts: list[dict[str, Any]], floor: float | None) -> list[dict[str, Any]]:
    """The reader's own messages after the words, the page's `nextCockpitLaterDirections`."""
    if floor is None:
        return []
    return [
        f
        for f in facts
        if f.get("type") == "user_message"
        and reading.author_of(f) == reading.AUTHOR_PERSON
        and (at := reading.valid_prompt_time(f.get("at"))) is not None
        and at > floor
    ]


def _unsettled(row: Mapping[str, Any], later: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The later directions the reader has not settled with Keep."""
    settled = reading.valid_prompt_time(row.get("annotation_settled_through"))
    return [
        f
        for f in later
        if settled is None or (reading.valid_prompt_time(f.get("at")) or 0.0) > settled
    ]


def unsettled_directions(
    row: Mapping[str, Any], facts: Iterable[Any], *, floor: float | None
) -> int:
    """How many later directions stand unsettled, by the rule `compose` steers from.

    The live estimate's `unsettled_directions` (DRC-4696), so the two never
    disagree about whether a direction is still open.
    """
    return len(_unsettled(row, _later_directions(_own(row, facts), floor)))


def _failed_checks(facts: list[dict[str, Any]], window: float) -> list[dict[str, Any]]:
    """Checks whose latest run failed with its result in the words' evidence window."""
    return [
        f
        for f in facts
        if f.get("type") == reading.TOOL_REPORT_TYPE
        and f.get("subject") == reading.CHECK_SUBJECT
        and f.get("result") == reading.RESULT_FAILED
        and (at := reading.evidence_at(f)) is not None
        and at > 0
        and at >= window
        and reading.valid_prompt_time(f.get("at")) is not None
    ]


def _reading_window(assessment: Mapping[str, Any]) -> float:
    """Where the reading's window opened, as the page derives it (`nextCockpitReadingShape`)."""
    stored = reading.valid_prompt_time(assessment.get("window_start"))
    if stored is not None:
        return stored
    field = (
        "goal_source_at"
        if assessment.get("goal_source") in reading.PROMPT_SOURCES
        else "revision_read_at"
    )
    return reading.valid_prompt_time(assessment.get(field)) or 0.0


class _Rows:
    """A stored reading of the current words, read against the record as it stands now."""

    def __init__(
        self,
        assessment: Mapping[str, Any],
        facts: list[dict[str, Any]],
        harness: str,
        *,
        unsettled: bool,
        lines_judged: bool,
    ) -> None:
        criteria = assessment.get("criteria")
        self.criteria: Mapping[str, Any] = criteria if isinstance(criteria, dict) else {}
        self.window = _reading_window(assessment)
        self.by_id = {str(f["fact_id"]): _as_evidence(f, harness) for f in facts}
        self.unsettled = unsettled
        self.lines_judged = lines_judged

    def state(self, name: str) -> tuple[str, dict[str, Any] | None]:
        """One constraint's state and the entry its time is read from."""
        row = self.criteria.get(name)
        # A stored `why` the page knows explains only a row its own rules already left
        # unverifiable, so it never demotes one here; one it does not know reads as unreadable
        # and demotes the row, as `nextCockpitReadingCriterion` does (injection F4).
        why = row.get("why") if isinstance(row, dict) else None
        if (
            self.unsettled
            or not isinstance(row, dict)
            or set(row) - set(reading.CRITERION_KEYS)
            or (why and (not isinstance(why, str) or why not in reading.WHY_TOKENS))
        ):
            return _NOT_SHOWN, None
        result = row.get("result")
        if result not in {reading.RESULT_DEPARTURE, reading.RESULT_CONSISTENT}:
            return _NOT_SHOWN, None
        raw = row.get("cites")
        cites = [
            self.by_id[c]
            for c in (raw if isinstance(raw, list) else [])
            if isinstance(c, str) and c in self.by_id
        ]
        cites = [
            f
            for f in cites
            if (at := reading.evidence_at(f) or 0.0) >= self.window
            and not (self.window > 0 and at <= 0)
        ]
        if not cites or {reading.author_of(f) for f in cites} == {reading.AUTHOR_DERIVED}:
            return _NOT_SHOWN, None
        line = reading.is_outcome_line(name) or name == reading.CONSTRAINT_OUTPUT
        if line and not self.lines_judged:
            return _NOT_SHOWN, None
        timed = [f for f in cites if reading.valid_prompt_time(f.get("at")) is not None]
        if result == reading.RESULT_DEPARTURE:
            standing = [
                f
                for f in timed
                if reading.check_supports(f, result, self.window)
                and (not line or reading.demonstrates_work(f))
            ]
            return (_DEPARTED, standing[0]) if standing else (_NOT_SHOWN, None)
        # "As the tool reported" is the only consistent form the template has, and on an
        # outcome line it is the only one the page lets stand (item 6).
        reported = [
            f
            for f in timed
            if f.get("type") == reading.TOOL_REPORT_TYPE
            and reading.check_supports(f, result, self.window)
            and reading.demonstrates_work(f)
        ]
        return (_CONSISTENT, reported[0]) if reported and line else (_NOT_SHOWN, None)


def _saved_lines(row: Mapping[str, Any]) -> list[tuple[int, str]]:
    lines = []
    for k in range(1, reading.MAX_OUTCOME_LINES + 1):
        text = str(row.get(f"annotation_line_{k}") or "")
        if text.strip():
            lines.append((k, text))
    return lines


def _current_rows(
    row: Mapping[str, Any], facts: list[dict[str, Any]], *, unsettled: bool, lines_judged: bool
) -> _Rows | None:
    """The stored reading, only while it read the words saved now."""
    assessment = row.get("annotation_assessment")
    if not isinstance(assessment, dict) or set(assessment) - set(reading.ASSESSMENT_KEYS):
        return None
    read, current = assessment.get("revision_read"), row.get("annotation_revision")
    if isinstance(read, bool) or not isinstance(read, int) or read != current:
        return None
    return _Rows(
        assessment,
        facts,
        str(row.get("harness") or ""),
        unsettled=unsettled,
        lines_judged=lines_judged,
    )


def _width(parts: list[Part]) -> int:
    placeholders = sum(1 for part in parts if not isinstance(part, str))
    text = sum(len(part) for part in parts if isinstance(part, str))
    if not placeholders:
        return text
    return text + FIRST_NUMBER_MAX_CHARS + NUMBER_MAX_CHARS * (placeholders - 1)


def _joined(lines: list[list[Part]]) -> list[Part]:
    """The lines as one list of parts, adjacent text merged."""
    parts: list[Part] = []
    for index, line in enumerate(lines):
        for part in [*line] if index == 0 else ["\n", *line]:
            if isinstance(part, str) and parts and isinstance(parts[-1], str):
                parts[-1] += part
            else:
                parts.append(part)
    return parts


def _body(
    lines: list[tuple[int, str]], rows: _Rows | None, at: Callable[[Mapping[str, Any]], str]
) -> list[tuple[str, list[Part]]]:
    """One bullet per saved line, with its state and the placeholder its time rests on."""
    body: list[tuple[str, list[Part]]] = []
    for k, text in lines:
        name = reading.outcome_line(k)
        if rows is not None and name not in rows.criteria and len(lines) == 1:
            name = reading.CONSTRAINT_OUTPUT
        state, cited = rows.state(name) if rows is not None else (_NOT_SHOWN, None)
        if state == _DEPARTED and cited is not None:
            body.append((state, [f"- {text}: departed at {at(cited)}", _placeholder(cited)]))
        elif state == _CONSISTENT and cited is not None:
            said: list[Part] = [
                f"- {text}: consistent with {at(cited)}",
                _placeholder(cited),
                ", as the tool reported",
            ]
            body.append((state, said))
        else:
            body.append((_NOT_SHOWN, [f"- {text}: nothing recorded shows this yet"]))
    return body


def _tail(
    failed: list[dict[str, Any]],
    later: list[dict[str, Any]],
    at: Callable[[Mapping[str, Any]], str],
) -> list[list[Part]]:
    """The latest failed check, the latest later direction, and the closing request."""
    tail: list[list[Part]] = []
    if failed:
        latest = max(failed, key=lambda f: reading.valid_prompt_time(f.get("at")) or 0.0)
        tail.append([f"A check failed at {at(latest)}", _placeholder(latest), "."])
    if later:
        tail.append([f"I gave a later direction at {at(later[-1])}", _placeholder(later[-1]), "."])
    tail.append(["Please continue from here."])
    return tail


def compose(
    row: Mapping[str, Any],
    facts: Iterable[Any],
    *,
    floor: float | None,
    lines_judged: bool,
    clock: Callable[[float], str] = clock_text,
) -> dict[str, Any]:
    """The correction for one session, or why there is none.

    `lines_judged` is whether this harness's route can carry the checks a
    verdict on an outcome line rests on: where it cannot, the page demotes
    every such verdict (`nextReadingOutputLimit`), and so does this.

    `{"ok": True, "parts": [...]}`, each part text or `{"entry": fact_id}`;
    `{"ok": False, "reason": "nothing"}` with nothing to steer from; or the
    too-long refusal with its sentence.
    """
    own = _own(row, facts)
    goal = str(row.get("annotation_goal") or "")
    lines = _saved_lines(row)
    if not goal.strip() and not lines:
        return {"ok": False, "reason": REASON_NOTHING}
    later = _later_directions(own, floor)
    unsettled = bool(_unsettled(row, later))
    window = reading.valid_prompt_time(row.get("annotation_window_start")) or 0.0
    failed = _failed_checks(own, window)
    rows = _current_rows(row, own, unsettled=unsettled, lines_judged=lines_judged)

    def at(fact: Mapping[str, Any]) -> str:
        return clock(reading.valid_prompt_time(fact.get("at")) or 0.0)

    body = _body(lines, rows, at)
    departed = any(state == _DEPARTED for state, _ in body) or (
        rows is not None and rows.state(reading.CONSTRAINT_GOAL)[0] == _DEPARTED
    )
    if not departed and not failed and not later:
        return {"ok": False, "reason": REASON_NOTHING}
    head: list[list[Part]] = [[f"Back to my goal: {goal}"]] if goal.strip() else []
    tail = _tail(failed, later, at)

    def assemble() -> list[Part]:
        opening: list[Part] = ["Where it stands against what I expect:"]
        middle: list[list[Part]] = [opening, *(line for _, line in body)]
        return _joined([*head, *(middle if body else []), *tail])

    parts = assemble()
    # The consistent lines go first, the last of them first, and nothing is ever cut short.
    while _width(parts) > CAP_CHARS:
        consistent = [i for i, (state, _) in enumerate(body) if state == _CONSISTENT]
        if not consistent:
            return {"ok": False, "reason": REASON_TOO_LONG, "why": TOO_LONG}
        del body[consistent[-1]]
        parts = assemble()
    return {"ok": True, "parts": parts}
