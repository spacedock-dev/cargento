#!/usr/bin/env python3
"""The answer key for "does each drift level mean the same thing every time".

DRC-4692 validates the two level functions of DEC-26 against recorded Claude Code sessions. The
owner marks the level each case should get BEFORE any rule is scored against it, and the marks'
digest is committed first, because a mark written after seeing an output is agreement, not a mark.
This follows `mark_abstention.py` and `score_abstention.py`, and keeps their split:

    levels_cases.py --build SPEC   freeze cases from recorded transcripts, under ~/.cargento
    levels_cases.py                mark the unmarked ones, one level per source per case
    levels_cases.py --report       how far through the key you are; scores nothing
    levels_cases.py --score        run both functions against the marks, write the summary

The spec is a local file the owner writes, one entry per case: its kind from the closed set
below, the transcript it is drawn from, an optional `until` (a Unix time; the transcript is cut
there, which is how 74c70a30's failed-check case is frozen before the second turn DRC-4673 gave
it), the intent as a separate yardstick, how many later directions stand unsettled, and an
optional stored reading for the analysis source. Nothing is defaulted: an entry missing the intent
or the direction count is refused, because a default there is the author's thumb on the case.

The cases carry recorded check lines and written paths, so they stay under `~/.cargento`, never in
the repository. What is committed is the marks' digest (`docs/drift-levels/marks-digest.json`) and
the scored summary (`docs/drift-levels/results.json`): case ids, kinds, marks, levels, reason
tokens and outcomes, and never a session id, a path, a command, the intent's words, a fact id or
model prose. SECURITY.md's abstention-check section names this second committed half.

Scoring calls no model. Both functions are pure over the frozen facts, so `--score` spends nothing
and can be re-run; it refuses a pass when the marks no longer hash to the committed digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKILL = os.path.join(_ROOT, "cargento", "skills", "cargento")


def _runtime() -> tuple[Any, Any, Any]:
    """(config, project_context, levels), reached the way `mark_abstention` reaches `reading`.

    Deferred for the reason given there: `scripts` is on mypy's path and a package to the tests,
    and a top-level runtime import makes this module resolvable under two names.
    """
    if _SKILL not in sys.path:
        sys.path.insert(0, _SKILL)
    from cargento_runtime import config, levels, project_context  # noqa: PLC0415

    return config, project_context, levels


HOME = os.environ.get("CARGENTO_HOME") or os.path.expanduser("~/.cargento")
SUBDIR = "drift-levels"
DIGEST_PATH = os.path.join(_ROOT, "docs", "drift-levels", "marks-digest.json")
RESULTS_PATH = os.path.join(_ROOT, "docs", "drift-levels", "results.json")

# The case kinds DRC-4692 and its case map name. Closed, because the kind is
# copied into the committed summary and a hand-typed value must not be.
KINDS = (
    "failed-check",
    "check-not-recorded",
    "pass-then-write",
    "own-account-only",
    "intent-names-no-folder",
    "draft-unsaved",
    "work-left-out",
    "later-direction",
    "other",
)

# One key per level, and no key for "the same as last time".
KEYS = {
    "n": "none_or_low",
    "m": "medium",
    "h": "high",
    "e": "extreme",
    "x": "not_enough",
    "d": "no_live_level",
}
LABELS = {
    "none_or_low": "None or low",
    "medium": "Medium",
    "high": "High",
    "extreme": "Extreme",
    "not_enough": "Not enough recorded yet",
    "no_live_level": "No live level (Save your intent to see a live estimate)",
}

MATCH = "match"
CAUTIOUS = "more-cautious"
FAILED = "failed"
VERDICT_PASSED = "passed"
VERDICT_FAILED = "failed"
VERDICT_STALE = "stale"
VERDICT_UNMARKED = "unmarked"

_SCALE = ("none_or_low", "medium", "high", "extreme")
# An analysis has no "no live level": that answers only a draft, on the live side.
ANALYSIS_LEVELS = frozenset(LABELS) - {"no_live_level"}
VERDICT_REFUSED = "refused"


def _paths(home: str) -> dict[str, str]:
    base = os.path.join(home, SUBDIR)
    return {
        "dir": base,
        "cases": os.path.join(base, "cases.json"),
        "marks": os.path.join(base, "marks.json"),
        "sha": os.path.join(base, "marks.sha256"),
        "readings": os.path.join(base, "readings.json"),
    }


def digest(body: Any) -> str:
    """A canonical hash of a JSON body, binding marks to the cases the marker saw."""
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def case_id(sid: str, until: float | None, kind: str) -> str:
    """Stable over identity, cut and kind, and nothing readable.

    One session stands for more than one case (3f4e7b30 is both a check with no
    recorded result and work left out), so the kind and the cut are part of it.
    """
    return hashlib.sha256(f"claude|{sid}|{until}|{kind}".encode()).hexdigest()[:16]


def _write(path: str, body: Any) -> None:
    """Atomically and private: these files name sessions."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(body, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _load(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            body = json.load(handle)
    except (OSError, ValueError):
        return {}
    return body if isinstance(body, dict) else {}


def _inside(path: str, root: str) -> bool:
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _intent_ok(intent: Any) -> bool:
    return (
        isinstance(intent, dict)
        and isinstance(intent.get("saved"), bool)
        and isinstance(intent.get("goal"), str)
        and isinstance(intent.get("lines"), list)
        and all(isinstance(line, str) for line in intent["lines"])
    )


def _count_ok(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _refusal(entry: Any) -> str:
    """Why a spec entry cannot be a case, or empty. Nothing is defaulted."""
    if not isinstance(entry, dict):
        return "not an object"
    transcript = entry.get("transcript")
    until = entry.get("until", False)
    checks = (
        (entry.get("kind") in KINDS, f"kind must be one of {', '.join(KINDS)}"),
        (
            isinstance(transcript, str) and os.path.isfile(transcript),
            "transcript must name a recorded Claude Code .jsonl file",
        ),
        (
            until is None or _number(until) is not None,
            "until must be a Unix time, or null for the whole transcript",
        ),
        (
            _intent_ok(entry.get("intent")),
            "intent must carry saved (true or false), goal and lines",
        ),
        (
            _count_ok(entry.get("unsettled_directions")),
            "unsettled_directions must be a count, written by hand",
        ),
        (
            "reading" not in entry,
            "a reading is attached after the marks are committed, with --attach-readings",
        ),
    )
    return next((why for holds, why in checks if not holds), "")


def _cut(source: str, until: float, into: str) -> str:
    """The transcript as it stood at `until`: every record timed after it dropped.

    A call made before the cut whose result arrived after it then reads as no
    recorded result, which is what the session showed at that moment.
    """
    _config, project_context, _levels = _runtime()
    path = os.path.join(into, "cut.jsonl")
    with (
        open(source, encoding="utf-8", errors="replace") as reader,
        open(path, "w", encoding="utf-8") as writer,
    ):
        for line in reader:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            at = project_context._record_timestamp(record)  # noqa: SLF001 - the scan's own clock
            if at is not None and at <= until:
                writer.write(line if line.endswith("\n") else line + "\n")
    return path


def _freeze(config: Any, entry: Mapping[str, Any], scratch: str) -> dict[str, Any]:
    """Layer 1's published facts and full-scan counts, exactly as the runtime builds them."""
    _config, project_context, _levels = _runtime()
    source = str(entry["transcript"])
    sid = pathlib.Path(source).stem
    until = _number(entry["until"])
    path = _cut(source, until, scratch) if until is not None else source
    rows, scan = project_context.claude_tool_reports(config, path, sid)
    facts = [
        project_context._semantic_fact_from_event(row, row["kind"], "tool_report", "")  # noqa: SLF001
        for row in rows
    ]
    captured = until if until is not None else max((float(r["at"]) for r in rows), default=None)
    cwd = next((str(r["cwd"]) for r in _records(path) if isinstance(r.get("cwd"), str)), "")
    intent = entry["intent"]
    return {
        "id": case_id(sid, until, str(entry["kind"])),
        "kind": entry["kind"],
        "harness": "claude",
        "sid": sid,
        "transcript": source,
        "until": until,
        "captured_at": captured,
        "facts": facts,
        "scan": dict(scan),
        "intent": {
            "saved": intent["saved"],
            "goal": intent["goal"],
            "lines": list(intent["lines"]),
        },
        "unsettled_directions": entry["unsettled_directions"],
        "cwd": cwd,
    }


def _records(path: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                found.append(record)
    return found


def _config() -> Any:
    config_mod, _project_context, _levels = _runtime()
    return config_mod.build_runtime_config(
        environ=os.environ,
        platform_name=sys.platform,
        os_name=os.name,
        launcher_path=pathlib.Path(_SKILL, "server.py"),
    )


def build(spec_path: str | os.PathLike[str], *, home: str, repo_root: str, say: Any) -> int:
    """Freeze every spec entry into `<home>/drift-levels/cases.json`."""
    paths = _paths(home)
    if _inside(paths["dir"], repo_root):
        say(f"{paths['dir']} is inside the repository. The cases name sessions and stay local.")
        say("Set CARGENTO_HOME outside it, or leave it unset for ~/.cargento.")
        return 2
    spec = _load(str(spec_path))
    entries = spec.get("cases") if spec.get("v") == 1 else None
    if not isinstance(entries, list) or not entries:
        say(f"No cases in {spec_path}: it wants {{'v': 1, 'cases': [...]}}.")
        return 1
    refused = [(n, _refusal(e)) for n, e in enumerate(entries, 1)]
    refused = [(n, why) for n, why in refused if why]
    for number, why in refused:
        say(f"  case {number}: {why}")
    if refused:
        say("Nothing was written.")
        return 1
    config = _config()
    with tempfile.TemporaryDirectory(dir=_ensure(paths["dir"])) as scratch:
        cases = [_freeze(config, entry, scratch) for entry in entries]
    ids = [case["id"] for case in cases]
    if len(set(ids)) != len(ids):
        say("Two entries are the same case (session, cut and kind). Nothing was written.")
        return 1
    held = _load(paths["marks"]).get("marks") or {}
    orphans = [k for k in held if k not in set(ids)]
    if orphans:
        say(f"{len(orphans)} existing marks name cases this build does not include.")
        say("Move the marks aside first; a build never deletes them.")
        return 1
    _write(paths["cases"], {"v": 1, "cases": cases})
    kinds = sorted({str(c["kind"]) for c in cases})
    say(f"Built {len(cases)} cases ({', '.join(kinds)}) at {paths['cases']}.")
    say("It stays on this machine and is never committed.")
    return 0


def _ensure(path: str) -> str:
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _show(case: Mapping[str, Any], position: str, say: Any) -> None:
    """One self-contained screen: the intent, the frozen record, and nothing the rules concluded."""
    captured = _number(case.get("captured_at")) or 0.0
    intent = case.get("intent") or {}
    say("\n" + "=" * 72)
    say(f"  {position}   case {case['id']}   kind: {case['kind']}")
    state = "SAVED" if intent.get("saved") else "DRAFTED, NEVER SAVED"
    say(f"\n  INTENT ({state})\n    Goal: {_clip(intent.get('goal'), 200)}")
    for number, line in enumerate(intent.get("lines") or [], 1):
        say(f"    {number}. {_clip(line, 200)}")
    if not intent.get("lines"):
        say("    (no expected-outcome line)")
    say(f"  Unsettled later directions: {case.get('unsettled_directions')}")
    say("\n  RECORDED CHECKS AND WRITES (seconds before the cut)")
    for fact in case.get("facts") or []:
        ago = captured - (_number(fact.get("at")) or captured)
        if fact.get("subject") == "check":
            extra = ", passed before a later change" if fact.get("before_last_change") else ""
            extra += (
                ", a command after it may have changed files" if fact.get("changed_after") else ""
            )
            line = _clip(fact.get("summary"), 90)
            say(f"    -{ago:6.0f}s  check  {fact.get('result')}{extra}: {line}")
        else:
            say(f"    -{ago:6.0f}s  wrote  {_clip(fact.get('summary'), 90)}")
    scan = case.get("scan") or {}
    counts = ("passed", "failed", "not_recorded", "background", "written_paths", "outside_paths")
    say("  Full scan: " + ", ".join(f"{k} {scan.get(k, 0)}" for k in counts))
    changed = _number(scan.get("last_changing_command_at"))
    if changed is not None:
        say(f"  Last shell command that may change files: {captured - changed:.0f}s before the cut")


def _ask(ask: Any, prompt: str) -> str | None:
    """One level, no default. None means stop; "skip" skips this case."""
    while True:
        try:
            reply = str(ask(prompt)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if reply in KEYS:
            return KEYS[reply]
        if reply in {"s", "skip"}:
            return "skip"
        if reply in {"q", "quit"}:
            return None


_MENU = (
    "    n None or low   m Medium   h High   e Extreme   x Not enough recorded yet\n"
    "    d No live level   s skip   q stop\n    > "
)


def _question(source: str) -> str:
    if source == "live":
        return (
            "\n  What should the LIVE ESTIMATE say here? It reads checks and file paths,\n"
            "  not what the intent says.\n" + _MENU
        )
    return (
        "\n  And what should an ANALYSIS read, taking each line of the intent against\n"
        "  this evidence? (No reading is shown: it is attached after the marks.)\n" + _MENU
    )


def _marks(body: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = body.get("marks")
    return {
        k: v
        for k, v in (raw.items() if isinstance(raw, dict) else ())
        if isinstance(v, dict)
        and v.get("live") in LABELS
        and (v.get("analysis") is None or v.get("analysis") in ANALYSIS_LEVELS)
    }


def _publish_digest(
    paths: Mapping[str, str], digest_path: str, cases: int, marked: int, *, cases_digest: str
) -> str:
    """Hash the marks as written, beside them and in the committable file."""
    with open(paths["marks"], "rb") as handle:
        sha = hashlib.sha256(handle.read()).hexdigest()
    with open(paths["sha"], "w", encoding="utf-8") as handle:
        handle.write(f"{sha}  marks.json\n")
    body = {
        "v": 1,
        "marks_digest": sha,
        "cases_digest": cases_digest,
        "cases": cases,
        "marked": marked,
    }
    os.makedirs(os.path.dirname(digest_path), exist_ok=True)
    with open(digest_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(body, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return sha


def _scored_marker(paths: Mapping[str, str], cases_digest: str) -> str:
    """Where a score of this case set is remembered, outside the repository (V2)."""
    return os.path.join(paths["dir"], f"scored-{cases_digest}.json")


def _repo_path(path: str, repo_root: str) -> str:
    """`path` as git names it in a `<rev>:<path>` argument: relative, with forward slashes.

    `os.path.relpath` answers with backslashes on Windows, and git reads a
    backslash in `HEAD:docs\\x.json` as part of the name. That reading of the
    windows-latest failures in test_levels_cases is inferred, not observed there.
    """
    return pathlib.PurePath(
        os.path.relpath(os.path.realpath(path), os.path.realpath(repo_root))
    ).as_posix()


def _history_blobs(repo_root: str, relative: str) -> list[dict[str, Any]]:
    """Every version of one file git has ever held, on any ref, deleted ones included."""
    shas = (_git(repo_root, "log", "--all", "--format=%H", "--", relative) or "").split()
    found = []
    for sha in shas:
        blob = _git(repo_root, "show", f"{sha}:{relative}")
        try:
            body = json.loads(blob) if blob is not None else None
        except ValueError:
            body = None
        if isinstance(body, dict):
            found.append(body)
    return found


def _marking_closed(
    paths: Mapping[str, str], repo_root: str, digest_path: str, results_path: str, bound: str
) -> str:
    """Why this case set can no longer be marked, or empty.

    A result seen closes the key however the files that showed it were
    removed: the local marker survives deleting the result and the marks, and
    git history survives deleting the marker. A marks digest already committed
    for this case set closes it too, since the digest is committed once.
    """
    if os.path.exists(results_path):
        return f"{results_path} exists, so a score has been seen"
    if os.path.exists(_scored_marker(paths, bound)):
        return "this case set has been scored on this machine"
    for path, what in ((results_path, "a result"), (digest_path, "a marks digest")):
        for body in _history_blobs(repo_root, _repo_path(path, repo_root)):
            if body.get("cases_digest") == bound or (
                path == results_path and "cases_digest" not in body
            ):
                return f"git history already holds {what} for it"
    return ""


def mark(
    *,
    home: str,
    digest_path: str,
    results_path: str,
    repo_root: str,
    ask: Any = input,
    say: Any = print,
) -> int:
    """Ask the owner for each unmarked case's level, per source, and write the key.

    Refused once any result exists: a mark written after a result is agreement.
    """
    paths = _paths(home)
    body = _load(paths["cases"])
    cases = body.get("cases") if isinstance(body.get("cases"), list) else None
    if not cases:
        say(f"No cases at {paths['cases']}. Run --build first.")
        return 1
    saved = _load(paths["marks"])
    entries = _marks(saved)
    bound = digest(body)
    closed = _marking_closed(paths, repo_root, digest_path, results_path, bound)
    if closed:
        say(f"Marking is closed for this case set: {closed}. Nothing was changed.")
        return 1
    if entries and saved.get("cases_digest") != bound:
        say("These marks belong to a different case set. Nothing was changed.")
        return 1
    todo = [c for c in cases if c.get("id") not in entries]
    if not todo:
        say(f"All {len(cases)} cases are marked.")
        return 0
    say(f"{len(todo)} of {len(cases)} left. Say what each level SHOULD read, not what it does.")
    _mark_cases(todo, entries, ask, say)
    if not entries:
        say("Nothing marked.")
        return 0
    _write(paths["marks"], {"v": 1, "cases_digest": bound, "marks": entries})
    sha = _publish_digest(paths, digest_path, len(cases), len(entries), cases_digest=bound)
    left = len(cases) - len(entries)
    say(f"\nSaved {len(entries)} marks, {left} left. sha256 {sha}")
    say(f"Commit {digest_path} before any score is run.")
    return 0


def _mark_cases(
    todo: list[dict[str, Any]], entries: dict[str, dict[str, Any]], ask: Any, say: Any
) -> None:
    """One screen per case; stops, keeping what was marked, at the first `q`."""
    for index, case in enumerate(todo, 1):
        _show(case, f"{index}/{len(todo)}", say)
        live = _ask(ask, _question("live"))
        if live is None:
            return
        if live == "skip":
            continue
        analysis: str | None = None
        if (case.get("intent") or {}).get("lines"):
            analysis = _ask(ask, _question("analysis"))
            if analysis is None:
                return
            if analysis == "skip":
                continue
            if analysis == "no_live_level":
                say("  No live level answers a draft only; this case's analysis is not marked.")
                continue
        else:
            say("  The intent has no outcome line, so there is no analysis level to mark.")
        entries[str(case["id"])] = {"live": live, "analysis": analysis}


def judge(got: str, marked: str) -> str:
    """Whether a level meets the owner's mark: the same, or more cautious.

    More cautious means it reassures less. A higher drift level is more
    cautious than a lower one, and "Not enough recorded yet" is more cautious
    than "None or low" only: said of a case marked Medium or above, it hides the
    drift the owner saw. "None or low" on a case marked anything else fails.
    "No live level" answers only a draft and is met only by itself.
    """
    if got == marked:
        return MATCH
    if "no_live_level" in (got, marked):
        return FAILED
    if got == "none_or_low":
        return FAILED
    if got == "not_enough":
        return CAUTIOUS if marked == "none_or_low" else FAILED
    if marked == "not_enough":
        return CAUTIOUS
    return CAUTIOUS if _SCALE.index(got) > _SCALE.index(marked) else FAILED


def _git(repo_root: str, *args: str) -> str | None:
    """Git's answer, or None when the repository cannot give one."""
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", repo_root, *args],  # noqa: S607 - the operator's git on PATH
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else None


class Committed:
    """The marks digest as committed, the commit that holds it, and when it was made."""

    def __init__(self, marks_digest: str, commit: str, committed_at: float) -> None:
        self.marks_digest = marks_digest
        self.commit = commit
        self.committed_at = committed_at


def committed_digest(repo_root: str, digest_path: str) -> Committed | str:
    """Read from HEAD, never from the working copy the marker rewrites (T2); why not, if not."""
    relative = _repo_path(digest_path, repo_root)
    blob = _git(repo_root, "show", f"HEAD:{relative}")
    if blob is None:
        return "the marks digest is not committed"
    try:
        with open(digest_path, encoding="utf-8") as handle:
            working = handle.read()
    except OSError:
        working = ""
    # Compared by line: a Windows checkout may hold CRLF where the blob holds LF.
    if working.splitlines() != blob.splitlines():
        return "the working copy of the marks digest differs from the committed one"
    log = (_git(repo_root, "log", "-1", "--format=%H %ct", "--", relative) or "").split()
    try:
        body = json.loads(blob)
    except ValueError:
        return "the committed marks digest is not JSON"
    if len(log) != 2 or not isinstance(body, dict) or not isinstance(body.get("marks_digest"), str):
        return "the committed marks digest cannot be read"
    return Committed(body["marks_digest"], log[0], float(log[1]))


def _marks_sha(paths: Mapping[str, str]) -> str:
    try:
        with open(paths["marks"], "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return ""


def _admit(config: Any, value: Any) -> Any:
    """A reading the store would keep, or None: the store's own validator, not a copy of it."""
    if _SKILL not in sys.path:
        sys.path.insert(0, _SKILL)
    from cargento_runtime import annotations  # noqa: PLC0415

    return annotations._assessment(value, config.annotation_text_cap_chars)  # noqa: SLF001


def attach_readings(
    spec_path: str | os.PathLike[str],
    *,
    home: str,
    repo_root: str,
    digest_path: str,
    now: float,
    say: Any = print,
) -> int:
    """Add readings after the marks, stamped with the committed digest they came after (T1)."""
    paths = _paths(home)
    committed = committed_digest(repo_root, digest_path)
    if isinstance(committed, str):
        say(f"Refused: {committed}. Mark, commit the digest, then attach readings.")
        return 1
    if committed.marks_digest != _marks_sha(paths):
        say("Refused: the local marks no longer hash to the committed digest.")
        return 1
    # Only the committed marks' cases (V4): the marks hash to the committed
    # digest, checked above, so these are exactly the committed ones.
    cases = set(_marks(_load(paths["marks"])))
    raw = _load(str(spec_path))
    readings = raw.get("readings") if raw.get("v") == 1 else None
    if not isinstance(readings, dict) or not readings:
        say(f"No readings in {spec_path}: it wants {{'v': 1, 'readings': {{case id: reading}}}}.")
        return 1
    config = _config()
    problems = []
    for key, value in readings.items():
        admitted = _admit(config, value) if key in cases else None
        read_at = _number(value.get("read_at")) if isinstance(value, dict) else None
        if key not in cases:
            problems.append(f"{key}: not a case in the committed marks")
        elif admitted is None:
            problems.append(f"{key}: the annotation store would refuse this reading")
        elif read_at is None or read_at <= committed.committed_at:
            problems.append(f"{key}: made before the marks digest was committed")
    for problem in problems:
        say(f"  {problem}")
    if problems:
        say("Nothing was attached.")
        return 1
    _write(
        paths["readings"],
        {
            "v": 1,
            "marks_digest": committed.marks_digest,
            "digest_commit": committed.commit,
            "attached_at": now,
            "readings": readings,
        },
    )
    say(f"Attached {len(readings)} readings under digest commit {committed.commit[:12]}.")
    return 0


def _reading_for(
    case: Mapping[str, Any], attached: Mapping[str, Any], committed: Committed, config: Any
) -> tuple[Any, str]:
    """The reading to score for a case, or a refusal token (T1 item 5), or neither."""
    if "reading" in case:
        return None, "reading-in-cases"
    value = (attached.get("readings") or {}).get(str(case["id"]))
    if value is None:
        return None, ""
    if (
        attached.get("marks_digest") != committed.marks_digest
        or attached.get("digest_commit") != committed.commit
    ):
        return None, "other-digest"
    read_at = _number(value.get("read_at")) if isinstance(value, dict) else None
    if read_at is None or read_at <= committed.committed_at:
        return None, "predates-marks"
    admitted = _admit(config, value)
    return (admitted, "") if admitted is not None else (None, "malformed")


def _level_row(level: Any, marked: str) -> dict[str, Any]:
    return {
        "level": level.level,
        "reasons": list(level.reasons),
        "outcome": judge(level.level, marked),
    }


def _score_case(
    levels: Any, case: Mapping[str, Any], marked: Mapping[str, Any], reading: tuple[Any, str]
) -> dict[str, Any]:
    intent = case.get("intent") or {}
    lines = tuple(str(x) for x in intent.get("lines") or ())
    evidence = levels.Evidence(
        facts=tuple(case.get("facts") or ()),
        scan=case.get("scan") or {},
        unsettled_directions=int(case.get("unsettled_directions") or 0),
        cwd=str(case.get("cwd") or ""),
    )
    live = levels.live_level(
        evidence,
        levels.Intent(
            saved=intent.get("saved") is True, goal=str(intent.get("goal") or ""), lines=lines
        ),
    )
    value, refusal = reading
    analysis: dict[str, Any] | None = None
    if refusal:
        analysis = {"level": None, "reasons": [], "outcome": f"refused:{refusal}"}
    elif value is not None and marked.get("analysis"):
        level = levels.analysis_level(value, evidence, outcome_lines=len(lines))
        analysis = _level_row(level, str(marked["analysis"]))
    return {
        "kind": case["kind"] if case.get("kind") in KINDS else "other",
        "marks": {"live": marked["live"], "analysis": marked.get("analysis")},
        "live": _level_row(live, str(marked["live"])),
        "analysis": analysis,
    }


def score(
    *,
    home: str,
    repo_root: str,
    digest_path: str,
    results_path: str,
    now: float,
    say: Any = print,
) -> int:
    """Both functions against the marks; the summary holds expectations and results only.

    Writes nothing when the marks do not hash to the committed digest, or when any
    case is unmarked (T3, T4): a level written for either can be read, then marked.
    """
    _config_mod, _project_context, levels = _runtime()
    paths = _paths(home)
    body = _load(paths["cases"])
    cases = body.get("cases") if isinstance(body.get("cases"), list) else []
    if not cases:
        say(f"No cases at {paths['cases']}. Run --build first.")
        return 1
    saved = _load(paths["marks"])
    entries = _marks(saved)
    committed = committed_digest(repo_root, digest_path)
    if isinstance(committed, str):
        say(f"Not scored: {committed}. Nothing was written.")
        return 1
    if committed.marks_digest != _marks_sha(paths) or saved.get("cases_digest") != digest(body):
        say("Not scored: the marks do not hash to the committed digest. Nothing was written.")
        return 1
    unmarked = [c for c in cases if str(c.get("id")) not in entries]
    if unmarked:
        say(f"Not scored: {len(unmarked)} cases are unmarked. Nothing was written.")
        return 1
    attached = _load(paths["readings"])
    config = _config()
    rows = {
        str(case["id"]): _score_case(
            levels,
            case,
            entries[str(case["id"])],
            _reading_for(case, attached, committed, config),
        )
        for case in cases
    }
    outcomes = [
        row[source]["outcome"]
        for row in rows.values()
        for source in ("live", "analysis")
        if row[source] is not None
    ]
    if any(o.startswith("refused:") for o in outcomes):
        verdict = VERDICT_REFUSED
    elif FAILED in outcomes:
        verdict = VERDICT_FAILED
    else:
        verdict = VERDICT_PASSED
    counts = {o: outcomes.count(o) for o in (MATCH, CAUTIOUS, FAILED)}
    counts["refused"] = sum(o.startswith("refused:") for o in outcomes)
    counts["no_reading"] = sum(
        1 for key, row in rows.items() if row["analysis"] is None and entries[key].get("analysis")
    )
    summary = {
        "v": 1,
        "cases_digest": digest(body),
        "scored_at": now,
        "marks_digest": committed.marks_digest,
        "digest_commit": committed.commit,
        "verdict": verdict,
        "counts": counts,
        "cases": rows,
    }
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    _write(
        _scored_marker(paths, digest(body)),
        {"v": 1, "cases_digest": digest(body), "scored_at": now, "digest_commit": committed.commit},
    )
    say(f"Drift levels scored: {verdict}. {counts}")
    return 0 if verdict == VERDICT_PASSED else 1


def report(*, home: str, say: Any = print) -> int:
    paths = _paths(home)
    cases = _load(paths["cases"]).get("cases") or []
    if not cases:
        say("No cases built yet.")
        return 1
    entries = _marks(_load(paths["marks"]))
    say(f"{sum(1 for c in cases if c.get('id') in entries)} of {len(cases)} marked.")
    for source in ("live", "analysis"):
        spread: dict[str, int] = {}
        for value in entries.values():
            if value.get(source):
                spread[value[source]] = spread.get(value[source], 0) + 1
        say(f"  {source:9} " + ", ".join(f"{LABELS[k]} {n}" for k, n in sorted(spread.items())))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze, mark and score drift-level cases.")
    parser.add_argument("--build", metavar="SPEC", help="freeze the cases a local spec names")
    parser.add_argument("--report", action="store_true", help="how far through the key you are")
    parser.add_argument(
        "--attach-readings", metavar="SPEC", help="add readings after the digest is committed"
    )
    parser.add_argument("--score", action="store_true", help="run both functions; calls no model")
    args = parser.parse_args(argv)
    chosen = (args.build, args.report, args.attach_readings, args.score)
    if sum(map(bool, chosen)) > 1:
        print("Run one of --build, --report, --attach-readings and --score at a time.")
        return 2
    import time  # noqa: PLC0415

    if args.build:
        return build(args.build, home=HOME, repo_root=_ROOT, say=print)
    if args.report:
        return report(home=HOME)
    if args.attach_readings:
        return attach_readings(
            args.attach_readings,
            home=HOME,
            repo_root=_ROOT,
            digest_path=DIGEST_PATH,
            now=time.time(),
        )
    if args.score:
        return score(
            home=HOME,
            repo_root=_ROOT,
            digest_path=DIGEST_PATH,
            results_path=RESULTS_PATH,
            now=time.time(),
        )
    return mark(home=HOME, digest_path=DIGEST_PATH, results_path=RESULTS_PATH, repo_root=_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
