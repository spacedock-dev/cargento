"""The four drift levels, from two sources, each over its own named evidence.

[DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn)
rules the levels None or low, Medium, High and Extreme, a floor per source for the first, and
"Not enough recorded yet" whenever the evidence is too little. Two pure functions, neither calling a
model and neither storing anything (item 6):

- `live_level` reads layer 1's published `tool_report` facts and full-scan counts
  ([DEC-23](docs/design-reading-a-session.md#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work))
  beside the reader's saved intent. Over an unsaved draft it has no level at all.
- `analysis_level` reads a stored reading's per-line results, and the same facts only to learn what
  each citation points at.

Both return the named evidence behind the level, as closed reason tokens and the fact ids behind
them, so a page can say why without writing its own rule. These are the starting definitions
DRC-4692 validates against the owner's marks, not a measured result: where the ruling left a
choice, each one here goes the withholding way, because the failure class the ruling accepts
is a level that reads safe when little is seen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import reading

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

NONE_OR_LOW = "none_or_low"
MEDIUM = "medium"
HIGH = "high"
EXTREME = "extreme"
NOT_ENOUGH = "not_enough"
NO_LIVE_LEVEL = "no_live_level"
LEVELS = (NONE_OR_LOW, MEDIUM, HIGH, EXTREME, NOT_ENOUGH, NO_LIVE_LEVEL)
# The drift scale proper, least to most. "Not enough" and "no live level" are
# not on it: they are what a source says instead of a level.
DRIFT_SCALE = (NONE_OR_LOW, MEDIUM, HIGH, EXTREME)

SOURCE_LIVE = "live"
SOURCE_ANALYSIS = "analysis"
# Each source's own line (the ruling's items 1 and 6). The live line is the live
# estimate's alone; the analysis line carries its time, which the page formats.
LIVE_SOURCE_LINE = "Live estimate: reads checks and file paths, not what your intent says."
ANALYSIS_SOURCE_LINE = (
    "From the analysis at {time}: each line of your intent against the checks and messages"
    " it cited."
)

# Why a level is what it is: a closed token set, so a page maps each to a
# sentence it owns and no producer prose reaches it through this field.
REASON_DRAFT_UNSAVED = "draft-unsaved"
REASON_FAILED_CHECK = "failed-check"
REASON_PASS_THEN_WRITE = "pass-then-write"  # noqa: S105 - a reason token
REASON_SOME_OUTSIDE = "writes-outside-folders"
REASON_MOST_OUTSIDE = "most-writes-outside-folders"
REASON_NO_FOLDER = "intent-names-no-folder"
REASON_NO_PASSING_CHECK = "no-passing-check"
REASON_CHECK_NOT_RECORDED = "check-not-recorded"
REASON_BACKGROUND_RUN = "background-run"
REASON_CHANGING_COMMAND = "command-after-pass"
REASON_LATER_DIRECTION = "later-direction"
REASON_UNLISTED = "entries-not-listed"
REASON_FLOOR_MET = "floor-met"
REASON_NO_READING = "no-reading"
REASON_NO_OUTCOME_LINE = "no-outcome-line"
REASON_DEPARTURE = "departure"
REASON_LINE_NOT_SHOWN = "line-not-shown-by-a-check"
REASON_READING_MALFORMED = "reading-malformed"
REASON_SCAN_INCOMPLETE = "scan-incomplete"
REASONS = (
    REASON_DRAFT_UNSAVED,
    REASON_FAILED_CHECK,
    REASON_PASS_THEN_WRITE,
    REASON_SOME_OUTSIDE,
    REASON_MOST_OUTSIDE,
    REASON_NO_FOLDER,
    REASON_NO_PASSING_CHECK,
    REASON_CHECK_NOT_RECORDED,
    REASON_BACKGROUND_RUN,
    REASON_CHANGING_COMMAND,
    REASON_LATER_DIRECTION,
    REASON_UNLISTED,
    REASON_FLOOR_MET,
    REASON_NO_READING,
    REASON_NO_OUTCOME_LINE,
    REASON_DEPARTURE,
    REASON_LINE_NOT_SHOWN,
    REASON_READING_MALFORMED,
    REASON_SCAN_INCOMPLETE,
)

_NOT_RECORDED = "not-recorded"
_WRITE_SUBJECT = "write"


@dataclass(frozen=True)
class Evidence:
    """What both sources may read of one Claude Code session.

    `facts` are its `tool_report` facts as published, `scan` the full-scan
    counts published beside them (`sources.work.tool_reports`), and
    `unsettled_directions` how many later directions the reader has not
    settled. Every figure about checks comes from `scan`; `facts` hold at
    most twelve entries and give times and paths only (the record's item 4).
    """

    facts: tuple[Mapping[str, Any], ...]
    scan: Mapping[str, Any]
    unsettled_directions: int
    cwd: str = ""


@dataclass(frozen=True)
class Intent:
    """The reader's intent as the live estimate sees it: saved or only drafted."""

    saved: bool
    goal: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Level:
    """One source's level, and the named evidence behind it.

    `writes_outside` and `writes_total` are `None` when the folder signal is
    not used, so a share is never read as 0% where no folder was named.
    """

    level: str
    source: str
    reasons: tuple[str, ...]
    cites: tuple[str, ...] = ()
    writes_outside: int | None = None
    writes_total: int | None = None
    computed_at: float | None = None

    @property
    def source_line(self) -> str:
        return LIVE_SOURCE_LINE if self.source == SOURCE_LIVE else ANALYSIS_SOURCE_LINE


# A path-shaped word: one or more `/`-joined parts. A URL is refused before
# this runs. A word of two or more parts names a folder, as a trailing `/` and
# a leading `./` do; a last part with a dot names its folder instead, unless a
# trailing `/` marks the word itself as the folder (`.github/`). Only a closed
# list of prose pairs is refused (DRC-4692, V1): refusing every unmarked
# multi-part word made "only touch web/app" name nothing and read lower.
_PATH_WORD = re.compile(r"^(?:\./)?[\w.-]+(?:/[\w.-]+)*/?$")
_PROSE = frozenset(
    {
        "and/or",
        "either/or",
        "client/server",
        "input/output",
        "read/write",
        "true/false",
        "yes/no",
        "on/off",
        "before/after",
    }
)
_TRIM = "`'\"()[]{}<>,;:!?"


def _folder_of(word: str, *, explicit: bool = False) -> str:
    """The folder one path-shaped word names, or empty.

    `explicit` is a word that was an absolute path inside the working
    directory, which names a folder even when one part is left of it.
    """
    marked = word.endswith("/")
    parts = [part for part in word.split("/") if part and part != "."]
    if not parts or ".." in parts:
        return ""
    if not marked:
        if "." in parts[-1]:
            parts = parts[:-1]
        elif len(parts) < 2 and not word.startswith("./") and not explicit:
            return ""
    return "/".join(parts)


def named_folders(intent: Intent, cwd: str = "") -> tuple[str, ...]:
    """The folders the intent names, without a trailing slash.

    `server/`, `.github/`, `./web`, `src/components` and `web/app` name
    themselves, and `src/retry.py` names `src`. An absolute path inside the
    working directory is read relative to it (L9); one outside it stays
    absolute, so no relative written path is ever inside it. A bare word, a
    URL, `~` and the prose pairs in `_PROSE` name none.
    """
    base = cwd.rstrip("/")
    found: set[str] = set()
    for text in (intent.goal, *intent.lines):
        for raw in str(text).split():
            word = raw.strip(_TRIM)
            word = word if word.endswith("/") else word.rstrip(".")
            if "/" not in word or "://" in word or word.startswith("~"):
                continue
            if word.lower() in _PROSE:
                continue
            absolute, explicit = word.startswith("/"), False
            if absolute and base and word.startswith(base + "/"):
                word, absolute, explicit = word[len(base) + 1 :], False, True
            if not _PATH_WORD.match(word.lstrip("/")):
                continue
            folder = _folder_of(word.lstrip("/") if absolute else word, explicit=explicit)
            if folder:
                found.add(f"/{folder}" if absolute else folder)
    return tuple(sorted(found))


def inside(path: str, folders: Iterable[str]) -> bool:
    """Whether a written path is one of the folders or below one."""
    return any(path == folder or path.startswith(f"{folder}/") for folder in folders)


# Every count the rules read. A scan missing one reads "Not enough recorded
# yet", never zero (L6): layer 1 always writes them all, so a missing key is a
# scan from somewhere else.
SCAN_KEYS = (
    "failed",
    "passed",
    "not_recorded",
    "background",
    "written_paths",
    "outside_paths",
    "more",
    "last_changing_command_at",
)


def scan_complete(scan: Mapping[str, Any]) -> bool:
    return all(key in scan for key in SCAN_KEYS)


def _count(scan: Mapping[str, Any], key: str) -> int:
    value = scan.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _at(fact: Mapping[str, Any]) -> float | None:
    value = fact.get("at")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _checks(evidence: Evidence) -> list[Mapping[str, Any]]:
    return [f for f in evidence.facts if f.get("subject") == reading.CHECK_SUBJECT]


def _writes(evidence: Evidence) -> list[Mapping[str, Any]]:
    return [f for f in evidence.facts if f.get("subject") == _WRITE_SUBJECT]


def _ids(facts: Iterable[Mapping[str, Any]]) -> list[str]:
    return [str(f.get("fact_id")) for f in facts if f.get("fact_id")]


def _ordered(ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ids))


@dataclass
class _Folders:
    outside: int
    total: int
    unlisted: int
    cites: list[str]


def _folder_share(evidence: Evidence, folders: tuple[str, ...]) -> _Folders:
    """Writes outside the named folders, counted from the full scan.

    A write outside the working directory is outside every folder, since it
    has no relative path to compare. A write the listing dropped cannot be
    placed either, so it counts as outside (L2): a lower bound reported as
    the share would let the cap on listed entries lower the level.
    """
    scan = evidence.scan
    listed = _writes(evidence)
    outside_listed = [f for f in listed if not inside(str(f.get("summary") or ""), folders)]
    beyond_cwd = _count(scan, "outside_paths")
    total = _count(scan, "written_paths") + beyond_cwd
    unlisted = max(0, _count(scan, "written_paths") - len(listed))
    return _Folders(
        outside=len(outside_listed) + beyond_cwd + unlisted,
        total=total,
        unlisted=unlisted,
        cites=_ids(outside_listed),
    )


def live_level(evidence: Evidence, intent: Intent) -> Level:
    """The live estimate: model-free, over the recorded checks and written paths.

    Medium: a pass is followed by writes, or some writes fall outside the
    named folders. High: the latest run of any check failed, or most writes
    fall outside them. Extreme: both of High's conditions. Otherwise the floor
    of the ruling's item 1 decides between None or low and Not enough recorded yet.
    A later direction and a changing shell command only ever block the floor.
    """
    if not intent.saved:
        return Level(NO_LIVE_LEVEL, SOURCE_LIVE, (REASON_DRAFT_UNSAVED,))
    scan = evidence.scan
    checks = _checks(evidence)
    failed = [f for f in checks if f.get("result") == reading.RESULT_FAILED]
    passes = [f for f in checks if f.get("result") == reading.RESULT_PASSED]
    aged = [f for f in passes if f.get("before_last_change") is True]

    folders = named_folders(intent, evidence.cwd)
    share = _folder_share(evidence, folders) if folders else None
    some_outside = share is not None and share.outside > 0
    most_outside = share is not None and share.outside * 2 > share.total

    # A listed failure the counts miss still reads High (L6).
    failing = _count(scan, "failed") > 0 or bool(failed)
    signals: tuple[tuple[str, bool, list[str]], ...] = (
        (REASON_FAILED_CHECK, failing, _ids(failed)),
        (REASON_MOST_OUTSIDE, most_outside, share.cites if share else []),
        (REASON_SOME_OUTSIDE, some_outside and not most_outside, share.cites if share else []),
        (REASON_PASS_THEN_WRITE, bool(aged), _ids(aged)),
        (REASON_NO_FOLDER, share is None, []),
        (REASON_UNLISTED, share is not None and share.unlisted > 0, []),
    )
    reasons = [reason for reason, holds, _ in signals if holds]
    cites = [fid for _, holds, ids in signals if holds for fid in ids]

    high = [failing, most_outside]
    if all(high):
        level = EXTREME
    elif any(high):
        level = HIGH
    elif aged or some_outside:
        level = MEDIUM
    else:
        blockers = _live_floor_blockers(evidence, passes)
        reasons.extend(blockers or [REASON_FLOOR_MET])
        cites.extend(_ids(passes))
        level = NOT_ENOUGH if blockers else NONE_OR_LOW
    return Level(
        level,
        SOURCE_LIVE,
        tuple(reasons),
        _ordered(cites),
        writes_outside=share.outside if share is not None else None,
        writes_total=share.total if share is not None else None,
    )


def _live_floor_blockers(evidence: Evidence, passes: list[Mapping[str, Any]]) -> list[str]:
    """Every clause of the live floor that does not hold, in the ruling's order."""
    scan = evidence.scan
    blockers: list[str] = []
    if not scan_complete(scan):
        blockers.append(REASON_SCAN_INCOMPLETE)
    passed = _count(scan, "passed")
    if not passed:
        # Zero is too little: at least one check whose latest run passed.
        blockers.append(REASON_NO_PASSING_CHECK)
    if _count(scan, "not_recorded"):
        blockers.append(REASON_CHECK_NOT_RECORDED)
    if _count(scan, "background"):
        # A check only ever launched in the background is neither listed nor
        # counted (the check record's item 1), so the launch count is the one sign of it.
        # A background server launch withholds the floor too; that is the
        # cautious side of a count that cannot tell the two apart.
        blockers.append(REASON_BACKGROUND_RUN)
    if passed > len(passes) or any(_at(f) is None for f in passes):
        blockers.append(REASON_UNLISTED)
    changed_at = scan.get("last_changing_command_at")
    pass_times = [t for t in (_at(f) for f in passes) if t is not None]
    # Layer 1 orders the call's own segments (`changed_after`); across calls a
    # tie in recorded time is read as a change, since it cannot say which ran
    # first (L1).
    later = (
        isinstance(changed_at, (int, float))
        and not isinstance(changed_at, bool)
        and bool(pass_times)
        and changed_at >= min(pass_times)
    )
    if later or any(f.get("changed_after") is not False for f in passes):
        blockers.append(REASON_CHANGING_COMMAND)
    if evidence.unsettled_directions > 0:
        blockers.append(REASON_LATER_DIRECTION)
    return blockers


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


@dataclass
class _LineTally:
    """What a reading's rows say, row by row, before a level is chosen."""

    by_id: Mapping[str, Mapping[str, Any]]
    window: float | None = None
    departed: bool = False
    aged: bool = False
    not_shown: int = 0
    cites: list[str] = field(default_factory=list)
    shown: list[str] = field(default_factory=list)

    def read(self, row: Mapping[str, Any], *, outcome_line: bool) -> None:
        result, why = row.get("result"), row.get("why") or ""
        if result == reading.RESULT_DEPARTURE:
            self.departed = True
            self.cites.extend(_cites(row))
            return
        if not outcome_line:
            # The Goal may rest on the session's own account (the ruling's item 1).
            return
        cited = [self.by_id[c] for c in _cites(row) if c in self.by_id]
        passes = [f for f in cited if f.get("result") == reading.RESULT_PASSED]
        # A cited pass aged now, or said to have aged when read, is a pass
        # followed by a change, whatever `why` the reading stored (L5).
        stale = [
            f
            for f in passes
            if f.get("before_last_change") is True or f.get("changed_after") is True
        ]
        if stale or why == reading.WHY_CHANGED_AFTER_CHECK:
            self.aged = True
            self.cites.extend(_ids(stale or passes))
            self.not_shown += 1
            return
        # A pass shows a line only inside the reading's window, as
        # `reading.check_supports` requires (V5); one with no time cannot.
        inside_window = [
            f
            for f in passes
            if (at := _at(f)) is not None and (self.window is None or at >= self.window)
        ]
        if result == reading.RESULT_CONSISTENT and not why and inside_window:
            self.shown.extend(_ids(inside_window))
        else:
            self.not_shown += 1


def _well_formed(criteria: Any, outcome_lines: int) -> bool:
    """Every row an object, every key a constraint of this intent, no line missing (L4).

    A reading the page would refuse whole is refused here too, rather than
    leveled from whichever rows happened to parse.
    """
    if not isinstance(criteria, dict) or not all(isinstance(v, dict) for v in criteria.values()):
        return False
    keys = set(criteria) - {reading.CONSTRAINT_GOAL}
    wanted = set(reading.constraints_for(["x"] * outcome_lines)) - {reading.CONSTRAINT_GOAL}
    legacy = outcome_lines == 1 and keys == {reading.CONSTRAINT_OUTPUT}
    if keys != wanted and not legacy:
        return False
    return all("result" not in row or row["result"] in reading.RESULTS for row in criteria.values())


def analysis_level(
    reading_row: Mapping[str, Any] | None, evidence: Evidence, *, outcome_lines: int
) -> Level:
    """The analysis level, derived from a stored reading's per-line results.

    `outcome_lines` is how many outcome lines the intent it read holds, so a
    line the reading did not answer is seen as missing. No model call and no
    new model output: each line's stored result, and what its citations point
    at in `evidence.facts`. A citation that is not a tool-reported check there
    (a message, the agent's own account) never shows an outcome line, so it
    never reaches the floor.

    Zero outcome lines is too little whatever the Goal says (L7). Medium: a
    departure, or a line whose cited pass was followed by a change. High: a
    failed check in the evidence window, cited or not, where a check with no
    time counts as inside it (L3). A failed check outside the window still
    blocks the floor. Never Extreme: that needs both of High's conditions, and
    the other one, most writes outside the named folders, is the live
    estimate's to read. An analysis reads each line against its citations and
    no folder, so a starting definition that reached Extreme here would be one
    nobody ruled.
    """
    if not reading_row:
        return Level(NOT_ENOUGH, SOURCE_ANALYSIS, (REASON_NO_READING,))
    computed_at = _number(reading_row.get("read_at"))
    if outcome_lines < 1:
        return Level(
            NOT_ENOUGH, SOURCE_ANALYSIS, (REASON_NO_OUTCOME_LINE,), computed_at=computed_at
        )
    criteria = reading_row.get("criteria")
    if not _well_formed(criteria, outcome_lines):
        return Level(
            NOT_ENOUGH, SOURCE_ANALYSIS, (REASON_READING_MALFORMED,), computed_at=computed_at
        )
    rows: Mapping[str, Mapping[str, Any]] = criteria if isinstance(criteria, dict) else {}
    window = _number(reading_row.get("window_start"))
    tally = _LineTally(
        {str(f.get("fact_id")): f for f in evidence.facts if f.get("fact_id")}, window
    )
    for name, row in rows.items():
        tally.read(row, outcome_line=reading.is_outcome_line(name))

    failed = [f for f in _checks(evidence) if f.get("result") == reading.RESULT_FAILED]
    in_window = [f for f in failed if window is None or (_at(f) or window) >= window]
    # A failure the counts hold and the listing dropped has no time to place.
    unplaced = _count(evidence.scan, "failed") > len(failed)
    reasons = [
        reason
        for reason, holds in (
            (REASON_FAILED_CHECK, failed or unplaced),
            (REASON_DEPARTURE, tally.departed),
            (REASON_PASS_THEN_WRITE, tally.aged),
        )
        if holds
    ]
    cites = [*_ids(in_window or failed), *tally.cites]
    if in_window or unplaced:
        level = HIGH
    elif tally.departed or tally.aged:
        level = MEDIUM
    else:
        blockers = [
            reason
            for reason, holds in (
                (REASON_SCAN_INCOMPLETE, not scan_complete(evidence.scan)),
                (REASON_LINE_NOT_SHOWN, tally.not_shown),
                (REASON_LATER_DIRECTION, evidence.unsettled_directions > 0),
            )
            if holds
        ]
        if failed and REASON_FAILED_CHECK not in blockers:
            blockers.insert(0, REASON_FAILED_CHECK)
        reasons.extend(r for r in (blockers or [REASON_FLOOR_MET]) if r not in reasons)
        cites.extend(tally.shown)
        level = NOT_ENOUGH if blockers or failed else NONE_OR_LOW
    return Level(level, SOURCE_ANALYSIS, tuple(reasons), _ordered(cites), computed_at=computed_at)


def _cites(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("cites")
    return (
        [str(c) for c in raw if isinstance(c, str) and c] if isinstance(raw, (list, tuple)) else []
    )
