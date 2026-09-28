"""The live drift estimate for one Claude Code session, replayed without a model (DRC-4696).

Items 2 to 6 of
[DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn).
`levels.live_level` is the estimate; this module feeds it. It replays the session's calls through
the same tally `project_context.claude_tool_reports` publishes from, one call at a time, and asks
for the level after each of the last `LIVE_REPLAY_STEPS` calls that can move it, so the level now
is the one the published record gives and "Rose from <level> at #<n>" comes from the same record.
The replay is held in this process's memory until the transcript or the words change; nothing is
written, and no model or process is started.

The route publishes the answer on the focused session's project context only (`http_api`), never
on a Sessions row, in history, or in the reading route's own context, which is what the unasked
lane reads (items 3 and 5). Whether the reader has the switch on is never sent to the server
(item 4), so this runs for the focused session whenever it has a saved intent.

It reads `project_context`'s tally through its private names rather than a new public function:
DRC-4666's freeze stamped a digest of that file, and any edit to it demotes every frozen case
(DRC-4731), so the file stays as it is until the scored run is committed.
"""

from __future__ import annotations

import dataclasses
import threading
from collections import OrderedDict
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
# How many of the latest moving calls the level is asked after. Each ask
# re-derives the entries from the whole tally, so an unbounded replay grew
# about cubically: 24 s for a 3,000-call transcript of targeted checks, and
# 212 s for 5,000 (review of d2854fc1, F1). A turn rarely makes more than a
# few dozen writes and shell calls, so 64 still finds a rise inside the last
# turns, and a rise older than that is withheld rather than guessed at.
LIVE_REPLAY_STEPS = 64
# One replay per session and set of words, kept in this process only. A request
# that finds the transcript unchanged reads nothing; one that finds it grown
# asks only after the calls it has not seen, because the transcript is append
# only and a step's level depends on no later call. A handful of entries covers
# the sessions a reader has open; beyond that the oldest goes.
_CACHE_ENTRIES = 16


@dataclasses.dataclass
class _Replayed:
    signature: tuple[int, int]
    # Each moving call read, in order, with its result or None. A call whose
    # mark differs, including a result that arrived since, changes its own
    # step and every one after it; the steps before it stand.
    marks: list[tuple[Any, ...]]
    # The level after each moving call by its position, and -1 for before the first.
    steps: dict[int, str]
    # The level, its reasons and where it rose; and the whole answer last published.
    found: dict[str, Any]
    published: dict[str, Any] = dataclasses.field(default_factory=dict)


_cache: OrderedDict[tuple[Any, ...], _Replayed] = OrderedDict()
_cache_lock = threading.Lock()


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


def _published(
    tally: pc._ToolReportTally,
    sid: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The tally's entries and scan as `claude_tool_reports` would publish them now.

    `entries` adds to the scan every time it is called, so the whole scan is put
    back afterwards rather than a list of the counters it touches today, which
    went stale silently when one was missed (review of d2854fc1, F2).
    """
    kept = dict(tally.scan)
    rows = tally.entries(sid)
    scan = dict(tally.scan)
    tally.scan.clear()
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
    unsettled = correction.unsettled_directions(row, facts, floor=floor)
    raw = pc._transcript_signature(transcript_path)  # noqa: SLF001
    if raw is None:
        return {**answer, **_replay(config, transcript_path, sid, intent, unsettled, None).found}
    signature = (raw["size"], raw["mtime_ns"])
    key = (transcript_path, harness, sid, answer["revision"], intent.goal, intent.lines, unsettled)
    with _cache_lock:
        previous = _cache.get(key)
        if previous is not None:
            _cache.move_to_end(key)
    if previous is not None and previous.signature == signature:
        return dict(previous.published)
    replayed = _replay(config, transcript_path, sid, intent, unsettled, previous)
    replayed.signature = signature
    replayed.published = {**answer, **replayed.found}
    with _cache_lock:
        _cache[key] = replayed
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_ENTRIES:
            _cache.popitem(last=False)
    return dict(replayed.published)


def _reusable(previous: _Replayed | None, marks: list[tuple[Any, ...]]) -> int:
    """How many leading steps of `previous` still stand for the calls read now."""
    valid = 0
    for old, new in zip(previous.marks if previous is not None else [], marks, strict=False):
        if old != new:
            break
        valid += 1
    return valid


def _replay(
    config: RuntimeConfig,
    transcript_path: str,
    sid: str,
    intent: levels.Intent,
    unsettled: int,
    previous: _Replayed | None,
) -> _Replayed:
    """The level now and where it rose, over the last `LIVE_REPLAY_STEPS` moving calls."""
    records = pc._work_records(config, transcript_path)  # noqa: SLF001
    cwd = _cwd(records)
    results = pc._tool_result_blocks(records)  # noqa: SLF001
    tally = pc._ToolReportTally(results)  # noqa: SLF001
    calls = [call for call in pc._claude_tool_uses(records) if call[3] in _MOVING_TOOLS]  # noqa: SLF001
    ids = [call[2] for call in calls]
    found_results = [results.get(call_id) for call_id in ids]
    marks = [
        (*call, None if got is None else (got.at, got.block))
        for call, got in zip(calls, found_results, strict=True)
    ]
    valid = _reusable(previous, marks)
    if previous is not None and valid == len(marks) == len(previous.marks):
        # No new moving call and no late result: the tally is as it was.
        return dataclasses.replace(previous, found=dict(previous.found))
    first = max(0, len(calls) - LIVE_REPLAY_STEPS)
    kept = previous.steps if previous is not None and valid else {}
    steps = {p: level for p, level in kept.items() if first - 1 <= p < valid}
    rows: list[dict[str, Any]] = []

    def level_now(position: int) -> levels.Level:
        nonlocal rows
        rows, scan = _published(tally, sid)
        now_facts = tuple(_fact(r) for r in rows)
        found = levels.live_level(levels.Evidence(now_facts, scan, unsettled, cwd), intent)
        steps[position] = found.level
        return found

    # The first step is the level before the window, so a run of the current
    # level that reaches back past it reads as no rise (`rose_from`'s start 0).
    current = level_now(-1) if first == 0 and -1 not in steps else None
    for position, call in enumerate(calls):
        tally.add(*call)
        if position >= first - 1 and position not in steps:
            current = level_now(position)
    if current is None:
        # Not reached: the last moving call is always read afresh here. Typed only.
        current = level_now(-1)
    window = [steps[p] for p in range(first - 1, len(calls))]
    rose = levels.rose_from(window)
    found: dict[str, Any] = {"level": current.level, "reasons": list(current.reasons)}
    if rose is not None:
        call_id = ids[first - 1 + rose[1]]
        # The entry the page numbers: the check or write that call left in the record
        # now. A call whose entry a later one replaced has none, and then no sentence
        # is published rather than one pointing at another entry.
        mine = sorted(
            (r for r in rows if r.get("record_id") == call_id),
            key=lambda r: r.get("subject") != "check",
        )
        if mine:
            found.update(rose_from=rose[0], rose_at=_fact(mine[0])["fact_id"])
    return _Replayed((0, 0), marks, steps, found)
