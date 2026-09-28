"""The live drift estimate for one Claude Code session, replayed without a model (DRC-4696).

Items 2 to 6 of
[DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn).
`levels.live_level` is the estimate; this module feeds it. It replays the session's calls through
the same tally `project_context.claude_tool_reports` publishes from, one call at a time, and asks
for the level after every call that can move it, so the level now is the one the published record
gives and "Rose from <level> at #<n>" is recomputed from the same record on every request. Nothing
is stored, no model or process is started, and no file is written.

The route publishes the answer on the focused session's project context only (`http_api`), never
on a Sessions row, in history, or in the reading route's own context, which is what the unasked
lane reads (items 3 and 5). Whether the reader has the switch on is never sent to the server
(item 4), so this runs for the focused session whenever it has a saved intent.

It reads `project_context`'s tally through its private names rather than a new public function:
DRC-4666's freeze stamped a digest of that file, and any edit to it demotes every frozen case
(DRC-4731), so the file stays as it is until the scored run is committed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import correction, levels
from . import project_context as pc

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from .config import RuntimeConfig

HARNESSES = frozenset({"claude"})
# The calls whose arrival can move the level: a write, or a shell command. A
# read, a search or a subagent launch never changes the tally.
_MOVING_TOOLS = frozenset({*pc._WRITE_TOOLS, "Bash"})  # noqa: SLF001
# `entries` adds each latest run's result to these counters every time it is
# called, so a replay that asks after every call puts them back each time.
_ENTRY_COUNTERS = ("failed", "passed", "not_recorded")


def saved_intent(row: Mapping[str, Any]) -> levels.Intent:
    """The saved words on the row, or an unsaved intent where no revision holds any."""
    revision = row.get("annotation_revision")
    goal = str(row.get("annotation_goal") or "")
    lines = tuple(
        text for k in range(1, 7) if (text := str(row.get(f"annotation_line_{k}") or "")).strip()
    )
    saved = (
        isinstance(revision, int)
        and not isinstance(revision, bool)
        and revision > 0
        and bool(goal.strip() or lines)
    )
    return levels.Intent(saved=saved, goal=goal, lines=lines)


def _cwd(records: Iterable[Mapping[str, Any]]) -> str:
    return next((str(r["cwd"]) for r in records if isinstance(r.get("cwd"), str)), "")


def _published(tally: Any, sid: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The tally's entries and scan as `claude_tool_reports` would publish them now."""
    kept = {key: tally.scan[key] for key in _ENTRY_COUNTERS}
    rows = tally.entries(sid)
    scan = dict(tally.scan)
    tally.scan.update(kept)
    return rows, scan


def _fact(row: Mapping[str, Any]) -> dict[str, Any]:
    return pc._semantic_fact_from_event(dict(row), str(row["kind"]), "tool_report", "")  # noqa: SLF001


def for_session(
    config: RuntimeConfig,
    row: Mapping[str, Any],
    transcript_path: str,
    facts: Iterable[Any],
    *,
    floor: float | None,
    now: float,
) -> dict[str, Any]:
    """The live level for one session now, and where it last rose from.

    `facts` is the session's published record, read for its later directions
    only; `floor` is `annotations.direction_floor` for the saved words.
    """
    harness, sid = str(row.get("harness") or ""), str(row.get("sid") or "")
    intent = saved_intent(row)
    revision = row.get("annotation_revision")
    answer: dict[str, Any] = {
        "harness": harness,
        "sid": sid,
        "revision": revision if isinstance(revision, int) and not isinstance(revision, bool) else 0,
        "computed_at": now,
        "rose_from": None,
        "rose_at": None,
    }
    if not intent.saved:
        # Over an unsaved draft there is no live level (item 2), and nothing is read.
        level = levels.live_level(levels.Evidence((), {}, 0), intent)
        return {**answer, "level": level.level, "reasons": list(level.reasons)}
    records = pc._work_records(config, transcript_path)  # noqa: SLF001
    evidence = levels.Evidence(
        (), {}, correction.unsettled_directions(row, facts, floor=floor), _cwd(records)
    )
    tally = pc._ToolReportTally(pc._tool_result_blocks(records))  # noqa: SLF001

    def level_now() -> tuple[levels.Level, list[dict[str, Any]]]:
        rows, scan = _published(tally, sid)
        now_facts = tuple(_fact(r) for r in rows)
        found = levels.live_level(
            levels.Evidence(now_facts, scan, evidence.unsettled_directions, evidence.cwd), intent
        )
        return found, rows

    steps: list[tuple[str, str]] = []
    current, rows = level_now()
    steps.append(("", current.level))
    for call in pc._claude_tool_uses(records):  # noqa: SLF001
        tally.add(*call)
        if call[3] in _MOVING_TOOLS:
            current, rows = level_now()
            steps.append((call[2], current.level))
    rose = levels.rose_from([level for _, level in steps])
    answer.update(level=current.level, reasons=list(current.reasons))
    if rose is not None:
        call_id = steps[rose[1]][0]
        # The entry the page numbers: the check or write that call left in the record
        # now. A call whose entry a later one replaced has none, and then no sentence
        # is published rather than one pointing at another entry.
        mine = sorted(
            (r for r in rows if r.get("record_id") == call_id),
            key=lambda r: r.get("subject") != "check",
        )
        if mine:
            answer.update(rose_from=rose[0], rose_at=_fact(mine[0])["fact_id"])
    return answer
