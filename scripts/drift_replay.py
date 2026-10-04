#!/usr/bin/env python3
"""Replay recorded pushback sessions through Cargento's drift detectors, against the owner's marks.

The golden key is `tests/annotated_sessions/<sid>/annotation.md`: where the person pushed back, what
the agent did that drifted, and why. The data is the session log: the redacted copy under
`tests/raw_sessions/<sid>/` (gitignored, made by `scripts/redact_session.py`), or the original under
`~/.claude/projects` with `--source original`. The ruling and the procedure are in
[docs/drift-replay/README.md](docs/drift-replay/README.md#the-order-cases-blind-marks-digest-runs-score).

Modes, in the order the README requires:

    --build      cut points from the annotations and the logs: every pushback, a sampled set of
                 ordinary turn stops, and a stop before each drift and after each fix
    (no flag)    blind marking: one screen per cut, shuffled, with no annotation and no output
    --reconcile  the annotation's proposal beside each blind mark; every disagreement is decided
    --report     how far through the key you are
    --live       tier 2: the live estimate and Steer back at every cut (no model, no spend)
    --read       tier 3: Analyze at every cut, charged on this tool's own ledger; with --tag (and
                 --case ID or ID:ARM to narrow it) into read-<tag>.json, leaving read.json alone
    --score      the outcome table, written to docs/drift-replay/results.json (results-<tag>.json
                 with --tag), with a claims-truth section once claim marks are committed
    --claims-export  every claims flag the reads raised, one item per cut and claimed message, for
                 marking; no detector, arm or result is in it
    --claims-mark    mark each item: was the claim true, and could the person see it at the time

Everything that names a session, a cut or a word stays under `$CARGENTO_HOME/drift-replay/`. The
repository receives a marks digest and a summary keyed by salted case ids, nothing else.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import glob
import hashlib
import json
import os
import random
import re
import secrets
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import levels_cases as lc  # noqa: E402 - scripts/ is put on the path just above

try:
    import fcntl
except ImportError:  # Windows: no advisory lock, so the cap holds for one run at a time there
    fcntl = None  # type: ignore[assignment]

HAS_LOCK = fcntl is not None

HOME = os.environ.get("CARGENTO_HOME") or os.path.expanduser("~/.cargento")
SUBDIR = "drift-replay"
FIXTURES = os.path.join(_ROOT, "tests", "raw_sessions")
ANNOTATIONS = os.path.join(_ROOT, "tests", "annotated_sessions")
DIGEST_PATH = os.path.join(_ROOT, "docs", "drift-replay", "marks-digest.json")
CLAIM_DIGEST_PATH = os.path.join(_ROOT, "docs", "drift-replay", "claim-marks-digest.json")
RESULTS_PATH = os.path.join(_ROOT, "docs", "drift-replay", "results.json")
ORIGINALS = os.path.expanduser("~/.claude/projects")
# Pinned under the operator's own home, not CARGENTO_HOME: moving the home must not reset the spend.
LEDGER_PATH = os.path.expanduser("~/.cargento/drift-replay/spend.json")

# Ordinary turn stops sampled per session as negatives, and the seed that picks them, so a rebuild
# picks the same stops. Eight per session gives about thirty, the size the review asked for.
NEGATIVES_PER_SESSION = 8
SAMPLE_SEED = 20261003

# What the blind screen asks, and the closed set a mark is.
DRIFT = {"y": "drift", "n": "no-drift", "u": "unclear"}
CLASSES = {
    "c": "communication",
    "s": "status-claim",
    "p": "scope-or-plan",
    "d": "defect",
    "o": "other",
}
ROLES = ("pushback", "ordinary", "before-drift", "after-fix")
CONTEXT_MESSAGES = 8
CONTEXT_CHARS = 700

_KIND_ROWS = {
    "You asked": "ask",
    "Claude did": "did",
    "Claude drifted": "drift",
    "You proposed": "propose",
    "You pushed back": "push",
}
_PART_RE = re.compile(r"^## (\d+) · ")
_ROW_RE = re.compile(r"^\| (You asked|Claude did|Claude drifted|You proposed|You pushed back) \|")
_REF_RE = re.compile(r"(?<![\w#])#(\d+)\b")
_SKIP_PREFIXES = ("[Request interrupted", "Caveat:", "Another Claude session")
_SKIP_MARKERS = ("teammate-message", "task-notification")
_COMMAND_RE = re.compile(
    r"<command-name>(/[^<]+)</command-name>.*?<command-args>(.*?)</command-args>", re.DOTALL
)


def _paths(home: str) -> dict[str, str]:
    base = os.path.join(home, SUBDIR)
    return {
        "dir": base,
        "cases": os.path.join(base, "cases.json"),
        "marks": os.path.join(base, "marks.json"),
        "sha": os.path.join(base, "marks.sha256"),
        "salt": os.path.join(base, "salt"),
        "live": os.path.join(base, "live.json"),
        "read": os.path.join(base, "read.json"),
        "plan": os.path.join(base, "plan.json"),
        "current": os.path.join(base, "current-intents.json"),
        "claim_items": os.path.join(base, "claim-items.json"),
        "claim_marks": os.path.join(base, "claim-marks.json"),
    }


def _ts(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _records(path: str) -> Iterable[dict[str, Any]]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield record


# --- The conversation, numbered the way tests/README.md says ------------------------------------


@dataclass
class Message:
    """One numbered message: a typed one, or every reply text between two typed ones, joined."""

    role: str
    at: float
    text: str
    uuids: list[str] = field(default_factory=list)


def _typed(record: Mapping[str, Any]) -> str | None:  # noqa: PLR0911 - one return per excluded kind
    """The words a person typed in this record, or None when it is not a typed message."""
    if record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain"):
        return None
    if record.get("isCompactSummary"):
        return None
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = "\n".join(
            str(b.get("text") or "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    if not isinstance(content, str):
        return None
    text = content.strip()
    command = _COMMAND_RE.match(text)
    if command:
        return f"{command.group(1)} {command.group(2)}".strip()
    if not text or text.startswith("<") or text.startswith(_SKIP_PREFIXES):
        return None
    head = text[:300]
    if "This session is being continued" in text[:200] or any(m in head for m in _SKIP_MARKERS):
        return None
    return re.sub(r"</?pasted_content[^>]*>", "", text)


def conversation(path: str, until: float | None = None) -> list[Message]:  # noqa: C901
    """The session's top-level conversation, numbered: the `#N` the annotations use.

    With `until`, only records stamped at or before it are read. A reply that runs on past a turn
    stop (a background task can wake the agent with no typed message) is one numbered message, so
    filtering whole messages by their first record would show a screen text written after its cut.
    """
    found: list[Message] = []
    pending: Message | None = None
    for record in _records(path):
        if record.get("isSidechain"):
            continue
        at = _ts(record.get("timestamp"))
        if until is not None and at is not None and at > until:
            continue
        typed = _typed(record)
        if typed is not None and at is not None:
            if pending is not None:
                found.append(pending)
                pending = None
            found.append(Message("you", at, typed, [str(record.get("uuid") or "")]))
            continue
        if record.get("type") != "assistant" or at is None:
            continue
        for block in (record.get("message") or {}).get("content") or []:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and str(block.get("text") or "").strip()
            ):
                if pending is None:
                    pending = Message("claude", at, "", [])
                pending.text = (pending.text + "\n\n" + block["text"].strip()).strip()
                pending.uuids.append(str(record.get("uuid") or ""))
    if pending is not None:
        found.append(pending)
    return found


def turn_stops(path: str) -> list[float]:
    """Every top-level `stop_hook_summary`: the moments a turn ended and the person could reply."""
    return sorted(
        at
        for record in _records(path)
        if record.get("type") == "system"
        and record.get("subtype") == "stop_hook_summary"
        and not record.get("isSidechain")
        and (at := _ts(record.get("timestamp"))) is not None
    )


# --- The key, read from the committed annotations -----------------------------------------------


@dataclass
class Event:
    """One pushback: its message, the drift rows since the last one in its part, its episode."""

    part: int
    push: int
    drift: list[int]
    episode: int
    first: bool


def events(annotation: str) -> list[Event]:
    """Every pushback in an annotation, in order, with the drift that led to it.

    A pushback with no drift row of its own since the last one in its part ("keep an eye on this")
    continues that episode, so only the first pushback of each episode counts toward catches.
    """
    found: list[Event] = []
    part, episode = 0, 0
    pending: list[int] = []
    for line in annotation.splitlines():
        heading = _PART_RE.match(line)
        if heading:
            part, pending = int(heading.group(1)), []
            continue
        if line.startswith("## "):
            part, pending = 0, []
            continue
        row = _ROW_RE.match(line)
        if not row or not part:
            continue
        kind = _KIND_ROWS[row.group(1)]
        refs = [int(n) for n in _REF_RE.findall(line.rsplit("|", 2)[-2])]
        if kind == "drift":
            pending.extend(n for n in refs if n not in pending)
        elif kind == "push" and refs:
            continues = not pending and bool(found) and found[-1].part == part
            if not continues:
                episode += 1
            found.append(Event(part, refs[0], list(pending), episode, first=not continues))
            pending = []
    return found


@dataclass
class Part:
    """One annotated part: the message that opened it, and the goal written afterwards."""

    opening: int | None
    goal: str
    refs: list[int] = field(default_factory=list)


_GOAL_RE = re.compile(r"^\*\*Goal:\*\* (.+)$")


def parts(annotation: str) -> dict[int, Part]:
    """Each part's first ask or proposal (the person's own words) and its hindsight goal."""
    found: dict[int, Part] = {}
    part = 0
    for line in annotation.splitlines():
        heading = _PART_RE.match(line)
        if heading:
            part = int(heading.group(1))
            found[part] = Part(None, "")
            continue
        if line.startswith("## "):
            part = 0
            continue
        if not part:
            continue
        goal = _GOAL_RE.match(line)
        if goal and not found[part].goal:
            found[part].goal = goal.group(1).strip()
        row = _ROW_RE.match(line)
        if row:
            refs = [int(n) for n in _REF_RE.findall(line.rsplit("|", 2)[-2])]
            found[part].refs.extend(refs)
            if (
                _KIND_ROWS[row.group(1)] in {"ask", "propose"}
                and found[part].opening is None
                and refs
            ):
                found[part].opening = refs[0]
    return found


def _opening(part: Part, messages: list[Message]) -> int | None:
    """A part's first typed, non-command message: a part can open on a drift row."""
    typed = [
        n
        for n in part.refs
        if n < len(messages) and messages[n].role == "you" and not messages[n].text.startswith("/")
    ]
    return min(typed) if typed else None


# --- Cases ---------------------------------------------------------------------------------------


def _cases(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    found = body.get("cases")
    return [c for c in found if isinstance(c, dict)] if isinstance(found, list) else []


def _salt(paths: Mapping[str, str]) -> str:
    """A local secret, so a committed case id cannot be recomputed from a session id and a time."""
    try:
        with open(paths["salt"], encoding="utf-8") as handle:
            value = handle.read().strip()
    except OSError:
        value = ""
    if not value:
        value = secrets.token_hex(16)
        os.makedirs(paths["dir"], mode=0o700, exist_ok=True)
        descriptor = os.open(paths["salt"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value + "\n")
    return value


def case_id(salt: str, sid: str, cut: float) -> str:
    return hashlib.sha256(f"{salt}|claude|{sid}|{cut:.6f}".encode()).hexdigest()[:16]


def _transcript(sid: str, source: str) -> str:
    if source == "original":
        found = glob.glob(os.path.join(ORIGINALS, "*", f"{sid}.jsonl"))
        return found[0] if found else ""
    path = os.path.join(FIXTURES, sid, f"{sid}.jsonl")
    return path if os.path.exists(path) else ""


def _before(stops: list[float], at: float) -> float | None:
    earlier = [s for s in stops if s < at]
    return earlier[-1] if earlier else None


def _after(stops: list[float], at: float) -> float | None:
    later = [s for s in stops if s > at]
    return later[0] if later else None


def session_cases(sid: str, source: str, salt: str) -> list[dict[str, Any]]:  # noqa: C901
    """Every cut for one session, each with its roles. Nothing here is shown while marking."""
    path = _transcript(sid, source)
    annotation_path = os.path.join(ANNOTATIONS, sid, "annotation.md")
    if not path or not os.path.exists(annotation_path):
        return []
    with open(annotation_path, encoding="utf-8") as handle:
        key = events(handle.read())
    messages = conversation(path)
    stops = turn_stops(path)
    by_cut: dict[float, dict[str, Any]] = {}

    def add(cut: float | None, role: str, **extra: Any) -> None:
        if cut is None:
            return
        case = by_cut.setdefault(
            cut,
            {"id": case_id(salt, sid, cut), "sid": sid, "cut": cut, "roles": [], "events": []},
        )
        if role not in case["roles"]:
            case["roles"].append(role)
        if extra:
            case["events"].append(extra)

    pushes: set[float] = set()
    spans: list[tuple[float, float]] = []
    episode_drift: dict[int, list[int]] = {}
    for event in key:
        if event.push >= len(messages) or messages[event.push].role != "you":
            continue
        push_at = messages[event.push].at
        pushes.add(push_at)
        # A drift row may also cite a later message as evidence; only what came before counts here.
        event.drift = [n for n in event.drift if n < len(messages) and messages[n].at < push_at]
        if event.drift:
            episode_drift.setdefault(event.episode, event.drift)
        drift = episode_drift.get(event.episode, [])
        if drift:
            spans.append((min(messages[n].at for n in drift), push_at))
        add(
            _before(stops, push_at),
            "pushback",
            part=event.part,
            push=event.push,
            drift=event.drift,
            episode_drift=drift,
            episode=event.episode,
            first=event.first,
        )
        if event.first and event.drift:
            drift_at = min(messages[n].at for n in event.drift)
            add(_before(stops, drift_at), "before-drift")
        fix = next((m for m in messages if m.at > push_at and m.role == "claude"), None)
        if event.first and fix is not None:
            add(_after(stops, fix.at - 1e-6), "after-fix")
    typed = [m.at for m in messages if m.role == "you"]
    ordinary = [
        s
        for s in stops
        if s not in by_cut
        and not any(t > s and t in pushes and not _between(stops, s, t) for t in typed)
        # A stop between the drift and its pushback is neither a pushback nor ordinary.
        and not any(start <= s < end for start, end in spans)
    ]
    rng = random.Random(f"{SAMPLE_SEED}|{sid}")  # noqa: S311 - a reproducible sample, not a secret
    for cut in sorted(rng.sample(ordinary, min(NEGATIVES_PER_SESSION, len(ordinary)))):
        add(cut, "ordinary")
    return sorted(by_cut.values(), key=lambda c: c["cut"])


def _between(stops: list[float], start: float, end: float) -> bool:
    """Whether another turn stop falls strictly between two moments."""
    return any(start < s < end for s in stops)


def _home_refusal(home: str) -> str:
    """Why this home may not hold the check's files: they name sessions and must stay out of git."""
    where = os.path.realpath(os.path.join(home, SUBDIR))
    root = os.path.realpath(_ROOT)
    if sys.platform == "darwin":  # a default macOS volume ignores case, so the guard must too
        where, root = where.lower(), root.lower()
    if lc._inside(where, root):  # noqa: SLF001 - the sibling's guard
        return (
            "CARGENTO_HOME is inside the repository; these files name sessions. Nothing was done."
        )
    return ""


def build(*, home: str, source: str, say: Callable[[str], Any] = print) -> int:
    paths = _paths(home)
    if _home_refusal(home):
        say(_home_refusal(home))
        return 1
    salt = _salt(paths)
    sids = sorted(
        os.path.basename(d) for d in glob.glob(os.path.join(ANNOTATIONS, "*")) if os.path.isdir(d)
    )
    cases: list[dict[str, Any]] = []
    for sid in sids:
        found = session_cases(sid, source, salt)
        if not found:
            say(f"  {sid[:8]}: no log for --source {source}; left out")
        cases.extend(found)
    body = {"v": 1, "source": source, "cases": cases}
    lc._write(paths["cases"], body)  # noqa: SLF001 - the sibling tool's private writer, shared on purpose
    roles: dict[str, int] = {}
    for case in cases:
        for role in case["roles"]:
            roles[role] = roles.get(role, 0) + 1
    say(
        f"Built {len(cases)} cuts over {len(sids)} sessions: "
        + ", ".join(f"{k} {v}" for k, v in sorted(roles.items()))
    )
    say(f"Cases at {paths['cases']} (local, private). Next: mark them blind.")
    return 0


# --- Blind marking -------------------------------------------------------------------------------


def _clip(text: str, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def _screen(case: Mapping[str, Any], source: str, position: str, say: Callable[[str], Any]) -> None:
    """The session up to the cut and nothing after it: no annotation, role or detector output."""
    path = _transcript(str(case["sid"]), source)
    messages = conversation(path, until=float(case["cut"]))
    say("\n" + "=" * 76)
    say(
        f"  {position}   session {str(case['sid'])[:8]}   "
        f"cut at a turn stop, {len(messages)} messages in"
    )
    opening = next((m for m in messages if m.role == "you" and not m.text.startswith("/")), None)
    if opening is not None:
        say(f"\n  YOUR OPENING MESSAGE\n    {_clip(opening.text, 400)}")
    say(f"\n  THE LAST {CONTEXT_MESSAGES} MESSAGES BEFORE THE CUT")
    for message in messages[-CONTEXT_MESSAGES:]:
        who = "YOU   " if message.role == "you" else "CLAUDE"
        stamp = datetime.datetime.fromtimestamp(message.at, datetime.UTC).strftime("%m-%d %H:%M")
        say(f"\n  [{who} {stamp}] {_clip(message.text, CONTEXT_CHARS)}")


def _ask(ask: Callable[[str], Any], prompt: str, choices: Mapping[str, str]) -> str | None:
    """One answer from a closed set, no default; None stops, "skip" skips."""
    while True:
        try:
            reply = str(ask(prompt)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if reply in choices:
            return choices[reply]
        if reply in {"s", "skip"}:
            return "skip"
        if reply in {"q", "quit"}:
            return None


_DRIFT_PROMPT = (
    "\n  By this point, had the agent drifted from what you wanted?\n"
    "    y yes   n no   u unclear   s skip   q stop\n    > "
)
_CLASS_PROMPT = (
    "  What kind?  c communication (unclear, too long, buried)\n"
    "              s status claim (said done or running)\n"
    "              p scope or plan (did less or other than asked)\n"
    "              d defect in what it built   o other\n    > "
)


def _load_marks(paths: Mapping[str, str], bound: str) -> dict[str, dict[str, Any]] | None:
    saved = lc._load(paths["marks"])  # noqa: SLF001 - shared loader
    marks = saved.get("marks") if isinstance(saved.get("marks"), dict) else {}
    if marks and saved.get("cases_digest") != bound:
        return None
    return {k: v for k, v in (marks or {}).items() if isinstance(v, dict)}


def mark(*, home: str, ask: Callable[[str], Any] = input, say: Callable[[str], Any] = print) -> int:
    """Blind marks, one shuffled screen per cut. Closed once any run has produced an output."""
    paths = _paths(home)
    body = lc._load(paths["cases"])  # noqa: SLF001
    cases = _cases(body)
    if not cases:
        say(f"No cases at {paths['cases']}. Run --build first.")
        return 1
    bound = lc.digest(body)
    closed = _closed(paths, bound)
    if closed:
        say(f"Marking is closed: {closed}. Nothing was changed.")
        return 1
    marks = _load_marks(paths, bound)
    if marks is None:
        say("These marks belong to a different case set. Nothing was changed.")
        return 1
    todo = [c for c in cases if c["id"] not in marks]
    random.Random(f"{SAMPLE_SEED}|order").shuffle(todo)  # noqa: S311 - a fixed order, not a secret
    say(f"{len(todo)} of {len(cases)} cuts left. Answer from what you see; nothing else is shown.")
    for index, case in enumerate(todo, 1):
        _screen(case, str(body.get("source") or "fixtures"), f"{index}/{len(todo)}", say)
        drift = _ask(ask, _DRIFT_PROMPT, DRIFT)
        if drift is None:
            break
        if drift == "skip":
            continue
        kind = None
        if drift == "drift":
            kind = _ask(ask, _CLASS_PROMPT, CLASSES)
            if kind is None:
                break
            if kind == "skip":
                continue
        marks[case["id"]] = {"blind": {"drift": drift, "class": kind}}
        _save_marks(paths, bound, marks, len(cases))
    say(f"\n{len(marks)} of {len(cases)} marked. Run --reconcile when every cut is marked.")
    return 0


def _save_marks(paths: Mapping[str, str], bound: str, marks: Mapping[str, Any], cases: int) -> str:
    lc._write(paths["marks"], {"v": 1, "cases_digest": bound, "marks": dict(marks)})  # noqa: SLF001
    with open(paths["marks"], "rb") as handle:
        sha = hashlib.sha256(handle.read()).hexdigest()
    final = sum(1 for m in marks.values() if isinstance(m, dict) and m.get("final"))
    os.makedirs(os.path.dirname(DIGEST_PATH), exist_ok=True)
    with open(DIGEST_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {
                "v": 1,
                "marks_digest": sha,
                "cases_digest": bound,
                "cases": cases,
                "marked": len(marks),
                "final": final,
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    return sha


def _proposal(case: Mapping[str, Any]) -> dict[str, Any]:
    """What the annotations imply at this cut: drift where a pushback followed, none elsewhere."""
    if "pushback" in case.get("roles", []):
        return {"drift": "drift", "class": None}
    return {"drift": "no-drift", "class": None}


def reconcile(
    *, home: str, ask: Callable[[str], Any] = input, say: Callable[[str], Any] = print
) -> int:
    """After every cut is marked blind: show the annotation's proposal and decide each disagreement.

    The 2026-09-28 rule: a mark the owner has not agreed to is not written, and a disagreement is
    shown rather than smoothed. Both the blind answer and the final one are kept.
    """
    paths = _paths(home)
    body = lc._load(paths["cases"])  # noqa: SLF001
    cases = _cases(body)
    bound = lc.digest(body)
    marks = _load_marks(paths, bound) or {}
    if not cases or len(marks) < len(cases):
        say(f"{len(marks)} of {len(cases)} cuts are marked blind. Finish the blind pass first.")
        return 1
    closed = _closed(paths, bound)
    if closed:
        say(f"Marking is closed: {closed}. Nothing was changed.")
        return 1
    for case in cases:
        entry = marks[case["id"]]
        if entry.get("final"):
            continue
        blind, proposed = entry["blind"], _proposal(case)
        if blind["drift"] == proposed["drift"]:
            entry["final"] = dict(blind)
            continue
        _screen(case, str(body.get("source") or "fixtures"), "disagreement", say)
        said = (
            "you pushed back right after this cut"
            if proposed["drift"] == "drift"
            else "no pushback came right after this cut"
        )
        say(f"\n  Your blind answer: {blind['drift']}.  The annotations: {said}.")
        drift = _ask(ask, _DRIFT_PROMPT, DRIFT)
        if drift in {None, "skip"}:
            break
        kind = blind.get("class")
        if drift == "drift" and not kind:
            kind = _ask(ask, _CLASS_PROMPT, CLASSES)
            if kind in {None, "skip"}:
                break
        entry["final"] = {
            "drift": drift,
            "class": kind if drift == "drift" else None,
            "disagreed": True,
        }
        _save_marks(paths, bound, marks, len(cases))
    sha = _save_marks(paths, bound, marks, len(cases))
    final = sum(1 for m in marks.values() if m.get("final"))
    say(f"\n{final} of {len(cases)} final. sha256 {sha}")
    if final == len(cases):
        say(f"Commit {_shown(DIGEST_PATH)} before --live, --read or --score.")
    return 0


def _closed(paths: Mapping[str, str], bound: str) -> str:
    """Why marking is closed, or empty: once an output exists, a mark is agreement."""
    for key in ("live", "read"):
        if os.path.exists(paths[key]):
            return f"{paths[key]} exists, so an output has been produced"
    if not _in_repository(DIGEST_PATH):
        return ""  # a file outside the repository has no git history to close it
    return lc._marking_closed(  # noqa: SLF001
        {**lc._paths(os.path.dirname(paths["dir"])), "dir": paths["dir"]},  # noqa: SLF001
        _ROOT,
        DIGEST_PATH,
        RESULTS_PATH,
        bound,
    )


def _shown(path: str) -> str:
    """A path as the operator types it: relative to the repository where git can name it."""
    return os.path.relpath(path, _ROOT) if _in_repository(path) else path


def _in_repository(path: str) -> bool:
    """Whether git can name this path; on Windows a path on another drive has no relative form."""
    try:
        return lc._inside(path, _ROOT)  # noqa: SLF001
    except ValueError:
        return False


def report(*, home: str, say: Callable[[str], Any] = print) -> int:
    paths = _paths(home)
    body = lc._load(paths["cases"])  # noqa: SLF001
    cases = _cases(body)
    marks = _load_marks(paths, lc.digest(body)) or {}
    final = sum(1 for m in marks.values() if m.get("final"))
    say(f"{len(cases)} cuts; {len(marks)} marked blind; {final} final.")
    return 0


# --- Replay: the cut, the facts, the intent arms --------------------------------------------------

# The Analyze tier's spend, on this tool's own fixed-path ledger: authorized by the owner on
# 2026-10-03 at 240 calls ("I authorize the spend for the analyze tier"), and raised to 440 on
# 2026-10-04 for the re-run with the adopted and current intent arms.
MAX_CALLS = 440
ARMS = ("realistic", "part", "hindsight", "adopted", "current")
_SETTLE_EXTRA = 1.0


def _runtime() -> tuple[Any, Any, Any, Any, Any]:
    """(config, project_context, live_estimate, correction, reading), as levels_cases does."""
    _config_mod, project_context, _levels = lc._runtime()  # noqa: SLF001
    from cargento_runtime import correction, live_estimate, reading  # noqa: PLC0415

    return lc._config(), project_context, live_estimate, correction, reading  # noqa: SLF001


def _cut_file(project_context: Any, source: str, target: str, until: float) -> bool:
    """Every record of one log timed at or before `until`; the file's mtime its last kept record."""
    kept, last = 0, None
    with (
        open(source, encoding="utf-8", errors="replace") as reader,
        open(target, "w", encoding="utf-8") as writer,
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
                kept, last = kept + 1, at
    if not kept or last is None:
        os.remove(target)
        return False
    os.utime(target, (last, last))
    return True


def cut_session(project_context: Any, transcript: str, sid: str, until: float, into: str) -> str:
    """The parent AND its subagents as they stood at `until`.

    A first spike linked the uncut subagent directory, so it read subagent records from after the
    cut; the board at that moment could not have. Children are cut the same way and dated by their
    last kept record, because the board reads them newest first against its byte budget.
    """
    os.makedirs(into, exist_ok=True)
    target = os.path.join(into, f"{sid}.jsonl")
    _cut_file(project_context, transcript, target, until)
    children = os.path.join(os.path.dirname(transcript), sid, "subagents")
    for child in glob.glob(os.path.join(children, "**", "*.jsonl"), recursive=True):
        out = os.path.join(into, sid, "subagents", os.path.relpath(child, children))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        _cut_file(project_context, child, out, until)
    return target


@dataclass
class Intent:
    """One intent arm: the goal and lines saved, when, the window they open, and their source."""

    arm: str
    goal: str
    at: float
    lines: tuple[str, ...] = ()
    window_start: float | None = None
    source: str = ""

    def revision(self) -> dict[str, Any]:
        """The saved revision a press would read, as `reading.produce` takes it."""
        body: dict[str, Any] = {
            "n": 1,
            "at": self.at,
            "goal": self.goal,
            "lines": list(self.lines),
            "window_start": self.window_start if self.window_start is not None else self.at,
        }
        if self.source:
            body.update(goal_source=self.source, goal_source_at=self.at)
        return body


def intents(
    case: Mapping[str, Any],
    messages: list[Message],
    annotation: str,
    current: Mapping[str, Any] | None = None,
) -> list[Intent]:
    """The arms, built only from words dated before the cut, but for hindsight.

    realistic: the person's opening prompt, saved once when it was typed, as typed words.
    adopted: the same prompt adopted with "Use your prompt", so the producer may read it whole.
    part: the message that opened the annotated part holding this cut, when it precedes the cut.
    hindsight: the goal the annotation wrote afterwards, an upper bound and never a headline.
    current: a goal and outcome lines drafted, blind, from the person's own messages before the
    cut, as a person keeping their intent up to date would (`current-intents.json`).
    """
    cut = float(case["cut"])
    typed = [m for m in messages if m.role == "you" and not m.text.startswith("/") and m.at <= cut]
    found: list[Intent] = []
    if typed:
        found.append(Intent("realistic", typed[0].text[:240], typed[0].at))
        found.append(Intent("adopted", typed[0].text[:240], typed[0].at, source="first-prompt"))
    drafted = (current or {}).get(str(case["id"]))
    if isinstance(drafted, dict) and str(drafted.get("goal") or "").strip():
        found.append(
            Intent(
                "current",
                str(drafted["goal"])[:240],
                float(drafted["at"]),
                tuple(str(line)[:240] for line in drafted.get("lines") or ())[:6],
                window_start=float(drafted.get("window_start") or drafted["at"]),
            )
        )
    found_parts = parts(annotation)
    pushed = [
        int(e["part"]) for e in case.get("events") or () if isinstance(e, dict) and "part" in e
    ]
    # A pushback cut belongs to its own annotated part; any other cut to the part open at its time.
    owner = found_parts.get(pushed[0]) if pushed else _part_of(cut, messages, found_parts)
    if owner is not None:
        opening = _opening(owner, messages)
        if opening is not None and opening < len(messages) and messages[opening].at <= cut:
            found.append(Intent("part", messages[opening].text[:240], messages[opening].at))
        if owner.goal and typed:
            start = (
                messages[opening].at
                if opening is not None and opening < len(messages)
                else typed[0].at
            )
            found.append(Intent("hindsight", owner.goal[:240], min(start, cut)))
    return found


def _part_of(cut: float, messages: list[Message], found: Mapping[int, Part]) -> Part | None:
    """The annotated part whose opening is the latest one at or before the cut."""
    best: tuple[float, Part] | None = None
    for part in found.values():
        opening = _opening(part, messages)
        if opening is None:
            continue
        at = messages[opening].at
        if at <= cut and (best is None or at > best[0]):
            best = (at, part)
    return best[1] if best else None


def facts_at(
    config: Any, project_context: Any, path: str, sid: str, cut: float
) -> tuple[list[dict[str, Any]], Any]:
    """The facts a board would have published for this session at the cut, and the press reads."""
    rows, _scan = project_context.claude_tool_reports(config, path, sid)
    checks = [
        project_context._semantic_fact_from_event(row, row["kind"], "tool_report", "")  # noqa: SLF001
        for row in rows
    ]
    # The board publishes the bounded tail it reads, not the whole file (mark_abstention does the
    # same); `path` is already cut, so its tail is what the board held at that moment.
    _whole, tail = project_context.frozen_claude_user_messages(config, path, sid, until=cut)
    said: list[dict[str, Any]] = []
    agent = getattr(project_context, "frozen_claude_agent_messages", None)
    if callable(agent):
        found = agent(config, path, sid, until=cut)
        said = list(found[1] if isinstance(found, tuple) else found)
    press = project_context.claude_check_press(config, path)
    return [*checks, *tail, *said], press


def _row(sid: str, intent: Intent, cut: float) -> dict[str, Any]:
    return {
        "harness": "claude",
        "sid": sid,
        "state": "idle",
        "finished_at": cut,
        "ended_at": None,
        "annotation_revision": 1,
        "annotation_goal": intent.goal,
        "annotation_window_start": intent.window_start
        if intent.window_start is not None
        else intent.at,
        **{f"annotation_line_{k}": line for k, line in enumerate(intent.lines, 1)},
    }


def _cites_after(
    cites: Iterable[str], facts: Iterable[Mapping[str, Any]], start: float | None
) -> bool:
    """Whether any cited fact is dated at or after the drift began."""
    if start is None:
        return False
    when: dict[str, float] = {
        str(f.get("fact_id")): float(f["at"])
        for f in facts
        if isinstance(f, Mapping) and isinstance(f.get("at"), int | float)
    }
    return any(c in when and when[c] >= start for c in cites)


def _cause_at(level: Mapping[str, Any], facts: Iterable[Mapping[str, Any]]) -> float | None:
    """When what raised the live level happened: the rise it names, else the latest failed check.

    `rose_at` names the fact a rise came from, but only inside the last 64 calls; a failure latched
    from earlier names none, and the failed check is then what holds the level up.
    """
    dated = {str(f.get("fact_id")): f for f in facts if isinstance(f, Mapping)}
    rose = dated.get(str(level.get("rose_at") or ""))
    if rose is not None and isinstance(rose.get("at"), int | float):
        return float(rose["at"])
    failed = [
        float(f["at"])
        for f in facts
        if isinstance(f, Mapping)
        and f.get("subject") == "check"
        and f.get("result") == "failed"
        and isinstance(f.get("at"), int | float)
    ]
    return max(failed) if failed else None


def _drift_start(case: Mapping[str, Any], messages: list[Message]) -> float | None:
    """When the drift behind this cut's first-of-episode pushback began, if it is a pushback."""
    starts = [
        messages[n].at
        for event in case.get("events") or ()
        for n in (event.get("drift") or event.get("episode_drift") or ())
        if n < len(messages)
    ]
    return min(starts) if starts else None


def _steer(
    correction: Any, row: Mapping[str, Any], facts: list[dict[str, Any]], floor: float
) -> dict[str, Any]:
    composed = correction.compose(row, facts, floor=floor, lines_judged=True)
    entries = [
        p["entry"] for p in composed.get("parts") or () if isinstance(p, dict) and "entry" in p
    ]
    return {"offered": bool(composed.get("ok")), "cites": entries, "reason": composed.get("reason")}


def live(*, home: str, source: str | None = None, say: Callable[[str], Any] = print) -> int:
    """Tier 2, free and deterministic: the live estimate and Steer back at every cut and arm."""
    paths = _paths(home)
    body = lc._load(paths["cases"])  # noqa: SLF001
    refusal = _run_refusal(paths, body)
    if refusal:
        say(refusal)
        return 1
    config, project_context, live_estimate, correction, _reading = _runtime()
    src = source or str(body.get("source") or "fixtures")
    out: dict[str, Any] = {}
    current = lc._load(paths["current"]).get("intents") or {}  # noqa: SLF001
    scratch = os.path.join(paths["dir"], "scratch")
    for case in body["cases"]:
        sid, cut = str(case["sid"]), float(case["cut"])
        transcript = _transcript(sid, src)
        if not transcript:
            continue
        messages = conversation(transcript)
        with open(os.path.join(ANNOTATIONS, sid, "annotation.md"), encoding="utf-8") as handle:
            annotation = handle.read()
        here = os.path.join(scratch, case["id"])
        path = cut_session(project_context, transcript, sid, cut, here)
        try:
            facts, _press = facts_at(config, project_context, path, sid, cut)
        except Exception as error:  # noqa: BLE001 - an apparatus refusal is an outcome, not a crash
            out[case["id"]] = {"refused": type(error).__name__}
            continue
        start = _drift_start(case, messages)
        arms: dict[str, Any] = {}
        for intent in intents(case, messages, annotation, current):
            row = _row(sid, intent, cut)
            level = live_estimate.for_session(
                config, row, path, facts, floor=intent.at, now=cut + _SETTLE_EXTRA
            )
            steer = _steer(correction, row, facts, intent.at)
            arms[intent.arm] = {
                "level": level.get("level"),
                "reasons": list(level.get("reasons") or ()),
                "steer": steer["offered"],
                "steer_after_drift": _cites_after(steer["cites"], facts, start),
                "cause_at": _cause_at(level, facts),
            }
        out[case["id"]] = {"arms": arms}
        _remove_tree(here)
    lc._write(paths["live"], {"v": 1, "source": src, "cases": out})  # noqa: SLF001
    say(f"Live estimate and Steer back at {len(out)} cuts, written to {paths['live']} (local).")
    return 0


def _remove_tree(path: str) -> None:
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    if os.path.isdir(path):
        os.rmdir(path)


def _run_refusal(paths: Mapping[str, str], body: Mapping[str, Any]) -> str:
    """Why a run may not start: the marks must be final and their digest committed first."""
    cases = _cases(body)
    if not cases:
        return f"No cases at {paths['cases']}. Run --build first."
    marks = _load_marks(paths, lc.digest(body)) or {}
    final = sum(1 for m in marks.values() if m.get("final"))
    if final < len(cases):
        return f"{final} of {len(cases)} cuts have a final mark. Mark blind and --reconcile first."
    if not _in_repository(DIGEST_PATH):
        return "Refused: the marks digest is not inside the repository, so it cannot be committed."
    committed = lc.committed_digest(_ROOT, DIGEST_PATH)
    if isinstance(committed, str):
        return f"Refused: {committed}. Commit {_shown(DIGEST_PATH)} first."
    with open(paths["marks"], "rb") as handle:
        if hashlib.sha256(handle.read()).hexdigest() != committed.marks_digest:
            return "Refused: the local marks no longer hash to the committed digest."
    return ""


# --- Tier 3: Analyze, charged ---------------------------------------------------------------


class LedgerError(Exception):
    """The ledger exists and cannot be read: refuse rather than start counting again."""


class Ledger:
    """A fixed-path count of Analyze calls for this check, capped at MAX_CALLS.

    Every charge holds an exclusive lock across its read and write, so concurrent runs cannot both
    take the last call. A ledger that exists and will not parse refuses every charge rather than
    reading as empty, and `floor` (the charged calls `read.json` records) keeps a deleted ledger
    from resetting the count.
    """

    def __init__(self, path: str, cap: int = MAX_CALLS, floor: int = 0) -> None:
        self.path = path
        self.cap = cap
        self.floor = floor

    def calls(self) -> list[dict[str, Any]]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                body = json.load(handle)
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as error:
            message = f"the spend ledger at {self.path} cannot be read"
            raise LedgerError(message) from error
        found = body.get("calls") if isinstance(body, dict) else None
        if not isinstance(found, list):
            message = f"the spend ledger at {self.path} is not a ledger"
            raise LedgerError(message)
        return [c for c in found if isinstance(c, dict)]

    def used(self) -> int:
        return max(len(self.calls()), self.floor)

    def charge(self, key: str) -> bool:
        """Record a call before it is made; False when the cap is reached."""
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        with open(self.path + ".lock", "a", encoding="utf-8") as lock:
            if fcntl is not None:
                fcntl.flock(lock, fcntl.LOCK_EX)
            calls = self.calls()
            if max(len(calls), self.floor) >= self.cap:
                return False
            calls.append({"key": key, "at": datetime.datetime.now(datetime.UTC).isoformat()})
            lc._write(self.path, {"v": 1, "cap": self.cap, "calls": calls})  # noqa: SLF001
            self.floor = max(self.floor, len(calls))
        return True


class _Charged:
    """The model `produce` calls, charging the ledger first; a withheld case never reaches it."""

    def __init__(self, inner: Any, ledger: Ledger | None, key: str) -> None:
        self.unavailable_reason = str(getattr(inner, "unavailable_reason", "model-unavailable"))
        self.inner = inner
        self.ledger = ledger
        self.key = key
        self.charged = False
        self.capped = False
        self.sent = False

    def available(self) -> bool:
        return bool(getattr(self.inner, "available", lambda: True)())

    def __call__(self, prompt: str, *, output_cap_bytes: int) -> tuple[str, str]:
        if self.ledger is None:
            # A dry run: measured by the stub, never charged.
            return self._send(prompt, output_cap_bytes)
        if not self.ledger.charge(self.key):
            self.capped = True
            return "", "cancelled"
        self.charged = True
        return self._send(prompt, output_cap_bytes)

    def _send(self, prompt: str, output_cap_bytes: int) -> tuple[str, str]:
        self.sent = True
        raw, status = self.inner(prompt, output_cap_bytes=output_cap_bytes)
        return str(raw), str(status)


_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_MIN_PREFIX = 8


def _tagged(paths: Mapping[str, str], tag: str) -> tuple[str, str]:
    """The read output and the plan a run tag names; the untagged pair without one."""
    if not tag:
        return paths["read"], paths["plan"]
    return (
        os.path.join(paths["dir"], f"read-{tag}.json"),
        os.path.join(paths["dir"], f"plan-{tag}.json"),
    )


def _tag_refusal(tag: str) -> str:
    """A tag names files beside the cases, so it is a short plain word or nothing."""
    if tag and not _TAG_RE.match(tag):
        return "Refused: a run tag is up to 32 lowercase letters, digits and hyphens."
    return ""


def _read_files(paths: Mapping[str, str]) -> list[str]:
    """Every read output, the untagged one first: what the ledger's floor and the claims count."""
    tagged = sorted(glob.glob(os.path.join(paths["dir"], "read-*.json")))
    return [paths["read"], *tagged]


def _selection(
    body: Mapping[str, Any], chosen: Iterable[str], arms: tuple[str, ...]
) -> tuple[list[str], str]:
    """`ID` or `ID:ARM` selectors as sorted `id:arm` pairs, or why they cannot be read.

    An ID may be a unique prefix of at least eight characters; a bare one takes every arm given.
    """
    ids = [str(c["id"]) for c in _cases(body)]
    pairs: set[str] = set()
    for selector in chosen:
        wanted, _sep, arm = selector.partition(":")
        if arm and arm not in ARMS:
            return [], f"Refused: {arm!r} is not an arm."
        found = [
            i for i in ids if i == wanted or (len(wanted) >= _MIN_PREFIX and i.startswith(wanted))
        ]
        if len(found) != 1:
            return [], f"Refused: {wanted!r} names {len(found)} cases, not one."
        pairs.update(f"{found[0]}:{a}" for a in ((arm,) if arm else arms))
    return sorted(pairs), ""


def _read_refusal(
    paths: Mapping[str, str],
    body: Mapping[str, Any],
    tag: str,
    cases: tuple[str, ...],
    arms: tuple[str, ...],
) -> tuple[list[str], str]:
    """The `id:arm` pairs a read selects, or why it may not start."""
    refusal = _run_refusal(paths, body) or _tag_refusal(tag)
    if refusal:
        return [], refusal
    if cases and not tag:
        return [], "Refused: a narrowed read needs --tag, so it never writes into read.json."
    return _selection(body, cases, arms)


def read(  # noqa: PLR0911 - one return per refusal, each before anything is sent
    *,
    home: str,
    source: str | None = None,
    dry_run: bool = False,
    arms: tuple[str, ...] = ARMS,
    say: Callable[[str], Any] = print,
    tag: str = "",
    cases: tuple[str, ...] = (),
) -> int:
    """Tier 3: one Analyze reading per cut and arm, through the verified Claude Code CLI.

    `--dry-run` runs the producer to the model with a stub that sends nothing and prints the call
    count; nothing is charged and no file is written.

    `tag` writes to `read-<tag>.json` with its own `plan-<tag>.json`, so an earlier run's
    `read.json` is never touched, and `cases` narrows it to those cuts (each `ID` or `ID:ARM`).
    The ledger, its cap and the plan rules are the same for a tagged run.
    """
    paths = _paths(home)
    body = lc._load(paths["cases"])  # noqa: SLF001
    selection, refusal = _read_refusal(paths, body, tag, cases, arms)
    if refusal:
        say(refusal)
        return 1
    read_path, plan_path = _tagged(paths, tag)
    config, _project_context, _live, _correction, reading = _runtime()
    import score_abstention  # noqa: PLC0415 - the verified, pinned CLI the qualification uses
    from cargento_runtime import reading_route  # noqa: PLC0415

    destination = reading_route.destination("claude")
    if not dry_run and destination != reading_route.VENDORS["claude"]:
        say(
            "Refused: the reading call would reach "
            f"{destination or 'an unnamed host'}, not Anthropic."
        )
        return 2
    done = lc._load(read_path).get("cases") or {}  # noqa: SLF001
    # Every read file's charged calls: neither a deleted ledger nor a tagged run resets the count.
    charged = sum(
        1
        for path in _read_files(paths)
        for entry in (lc._load(path).get("cases") or {}).values()  # noqa: SLF001
        if isinstance(entry, dict)
        for arm in entry.values()
        if isinstance(arm, dict) and arm.get("charged")
    )
    ledger = Ledger(LEDGER_PATH, floor=charged)
    try:
        ledger.used()
    except LedgerError as error:
        say(f"Refused: {error}. Nothing was sent.")
        return 2
    src = source or str(body.get("source") or "fixtures")
    bound = lc.digest(body)
    if not dry_run:
        plan = lc._load(plan_path)  # noqa: SLF001
        room = ledger.cap - ledger.used()
        if (
            plan.get("cases_digest") != bound
            or sorted(plan.get("arms") or ()) != sorted(arms)
            or (plan.get("selection") or []) != selection
        ):
            say(
                "Run --read --dry-run first, with the same --arm, --tag and --case choices: "
                "it records the plan."
            )
            return 1
        if int(plan.get("calls") or 0) > room:
            say(
                f"Refused: the plan needs {plan.get('calls')} calls and the ledger has {room} "
                "left. Narrow it with --arm."
            )
            return 1
    with contextlib.ExitStack() as stack:
        verified = None if dry_run else stack.enter_context(score_abstention.verify_claude_binary())
        inner: Any = (
            lc._Spy()  # noqa: SLF001 - the sibling's prompt-measuring stub
            if verified is None
            else reading.ClaudeReadingModel(
                config,
                binary_resolver=score_abstention.PinnedClaude(verified.path, verified.identity),
            )
        )
        try:
            calls = _read_cases(
                body,
                {**paths, "read": read_path},
                inner,
                ledger,
                done,
                src,
                arms,
                dry_run=dry_run,
                say=say,
                selection=frozenset(selection),
            )
        finally:
            _remove_tree(os.path.join(paths["dir"], "scratch-read"))
        if calls < 0:
            return 0
    if dry_run:
        plan = {"v": 1, "cases_digest": bound, "arms": list(arms), "calls": calls}
        if selection:
            plan["selection"] = selection
        lc._write(plan_path, plan)  # noqa: SLF001
    say(
        f"{'Would make' if dry_run else 'Made'} {abs(calls)} calls; "
        f"ledger {ledger.used()} of {ledger.cap}."
    )
    return 0


def _read_cases(  # noqa: PLR0913 - every input of one pass, named
    body: Mapping[str, Any],
    paths: Mapping[str, str],
    inner: Any,
    ledger: Ledger,
    done: dict[str, Any],
    src: str,
    arms: tuple[str, ...],
    *,
    dry_run: bool,
    say: Callable[[str], Any],
    selection: frozenset[str] = frozenset(),
) -> int:
    """One reading per cut and arm; the number of calls, negative when the cap stopped the pass.

    A non-empty `selection` of `id:arm` pairs reads only those.
    """
    config, project_context, _live, _correction, reading = _runtime()
    from cargento_runtime import observer, reading_route  # noqa: PLC0415

    scratch = os.path.join(paths["dir"], "scratch-read")
    current = lc._load(paths["current"]).get("intents") or {}  # noqa: SLF001
    calls = 0
    for case in body["cases"]:
        if selection and not any(pair.startswith(f"{case['id']}:") for pair in selection):
            continue
        sid, cut = str(case["sid"]), float(case["cut"])
        transcript = _transcript(sid, src)
        if not transcript:
            continue
        messages = conversation(transcript)
        with open(os.path.join(ANNOTATIONS, sid, "annotation.md"), encoding="utf-8") as handle:
            annotation = handle.read()
        here = os.path.join(scratch, case["id"])
        path = cut_session(project_context, transcript, sid, cut, here)
        try:
            facts, press = facts_at(config, project_context, path, sid, cut)
        except Exception as error:  # noqa: BLE001
            done.setdefault(case["id"], {})["refused"] = type(error).__name__
            continue
        for intent in intents(case, messages, annotation, current):
            if (
                intent.arm not in arms
                or (done.get(case["id"]) or {}).get(intent.arm)
                or (selection and f"{case['id']}:{intent.arm}" not in selection)
            ):
                continue
            tool_output = reading.ToolOutput(
                destination=reading_route.VENDORS["claude"],
                label=reading_route.LABELS["claude"],
                tails=press.tails,
                changed_after=press.changed_after,
                read_incomplete=press.read_incomplete,
                # The listing's cap leaving out a pass or a write, as the press reads it.
                unlisted=press.unlisted,
            )
            model = _Charged(inner, None if dry_run else ledger, f"{case['id']}|{intent.arm}")
            assessment, why, _spent = reading.produce(
                config,
                _row(sid, intent, cut),
                [intent.revision()],
                facts,
                now=cut + float(getattr(config, "reading_settle_sec", 8.0)) + _SETTLE_EXTRA,
                stamp_text=f"{observer.CLAUDE_READING_MODEL} · drift replay",
                model=model,
                tool_output=tool_output,
                read_lines=True,
                # The press sends the agent's words (owner ruling, 2026-10-03); a replay that left
                # them out would measure a producer the board no longer ships.
                read_agent_words=True,
                admit_turn_stop=True,
            )
            calls += 1 if model.sent else 0
            if model.capped:
                say("The ledger cap is reached; this call was not made and is not recorded.")
                return -calls
            if dry_run:
                continue
            entry = done.setdefault(case["id"], {})
            entry[intent.arm] = {
                "withheld": why or "",
                "charged": model.charged,
                "assessment": assessment,
                "facts": {
                    str(f.get("fact_id")): {"at": f.get("at"), "type": f.get("type")}
                    for f in facts
                    if f.get("fact_id")
                },
            }
            lc._write(paths["read"], {"v": 1, "source": src, "cases": done})  # noqa: SLF001
            if ledger.used() >= ledger.cap:
                say("The ledger cap is reached; stopping.")
                return -calls
        _remove_tree(here)
    return calls


# --- Score --------------------------------------------------------------------------------

BINS_DRIFT = (
    "relevant-flag",
    "irrelevant-flag",
    "unattributed-flag",
    "echo",
    "withheld",
    "reassured",
    "refused",
)
BINS_QUIET = ("false-alarm", "quiet", "withheld", "refused")


def _live_bin(arm: Mapping[str, Any] | None, *, drifted: bool, start: float | None) -> str:
    """One live outcome. A flag is relevant when what raised it happened after the drift began."""
    if not arm:
        return "refused"
    level = arm.get("level")
    if level in {"medium", "high", "extreme"}:
        if not drifted:
            return "false-alarm"
        cause = arm.get("cause_at")
        if start is None or not isinstance(cause, int | float):
            return "unattributed-flag"
        return "relevant-flag" if cause >= start else "irrelevant-flag"
    if level == "none_or_low":
        return "reassured" if drifted else "quiet"
    return "withheld"


# Reasons the apparatus failed, as opposed to the producer choosing to abstain.
APPARATUS = frozenset(
    {
        "cancelled-unsent",
        "model-unavailable",
        "claude-unavailable",
        "model-failed",
        "unstopped",
        "interrupted",
        "job-unrecorded",
        "record-error",
        "no-record-reader",
    }
)


# The claims constraint's own result for a claim nothing recorded shows; a flag like a departure.
UNSUPPORTED = "not shown by the record"
CLAIMS = "claims"


def _contradicting(name: str, criterion: Mapping[str, Any], facts: Mapping[str, Any]) -> list[str]:
    """The cites a departed criterion rests on, less the claim itself on a claims departure.

    A claims departure cites the agent's message making the claim beside what contradicts it; the
    claim is the cited agent messages at or before the earliest one (measured on the second run,
    this alone flips one judged catch to an echo). An `unsupported` cites only the claim, so it is
    left whole and is never an echo.
    """
    cites = [str(c) for c in criterion.get("cites") or ()]
    if name != CLAIMS or criterion.get("result") != "departure":
        return cites
    said = [
        float((facts.get(c) or {}).get("at") or 0.0)
        for c in cites
        if (facts.get(c) or {}).get("type") == "agent_message"
    ]
    if not said:
        return cites
    claimed = min(said)
    return [
        c
        for c in cites
        if (facts.get(c) or {}).get("type") != "agent_message"
        or float((facts.get(c) or {}).get("at") or 0.0) > claimed
    ]


def _departed_bin(
    name: str,
    criterion: Mapping[str, Any],
    facts: Mapping[str, Any],
    start: float | None,
) -> str:
    """One departed criterion's outcome on a drift cut, judged on its own cites."""
    cites = _contradicting(name, criterion, facts)
    if cites and all((facts.get(c) or {}).get("type") == "user_message" for c in cites):
        return "echo"
    if start is None:
        return "unattributed-flag"
    dated = [{"fact_id": k, "at": v.get("at")} for k, v in facts.items()]
    return "relevant-flag" if _cites_after(cites, dated, start) else "irrelevant-flag"


def _read_bin(  # noqa: PLR0911 - one return per outcome
    entry: Mapping[str, Any] | None,
    *,
    drifted: bool,
    start: float | None,
    only: str = "",
) -> str:
    """One reading's outcome. A departure resting only on the person's own messages is an echo.

    Each departed criterion is judged on its own cites, and the reading takes the best of them in
    `BINS_DRIFT` order: one criterion citing the agent's work does not lift another resting on the
    person's words alone out of being an echo, nor the other way round.
    """
    if not entry:
        return "refused"
    withheld = str(entry.get("withheld") or "")
    if withheld:
        return (
            "refused" if withheld in APPARATUS or withheld.startswith("oversized") else "withheld"
        )
    criteria = (entry.get("assessment") or {}).get("criteria") or {}
    if only == "intent":
        criteria = {k: v for k, v in criteria.items() if k != CLAIMS}
    elif only == CLAIMS:
        criteria = {k: v for k, v in criteria.items() if k == CLAIMS}
        if not criteria:
            return "not-asked"
    departed = [
        (name, c)
        for name, c in criteria.items()
        if isinstance(c, dict) and c.get("result") in {"departure", UNSUPPORTED}
    ]
    facts = {
        k: v if isinstance(v, dict) else {"at": v} for k, v in (entry.get("facts") or {}).items()
    }
    if departed:
        if not drifted:
            return "false-alarm"
        return min(
            (_departed_bin(name, c, facts, start) for name, c in departed),
            key=BINS_DRIFT.index,
        )
    consistent = any(
        isinstance(c, dict) and str(c.get("result", "")).startswith("consistent")
        for c in criteria.values()
    )
    if consistent:
        return "reassured" if drifted else "quiet"
    return "withheld"


def _population(case: Mapping[str, Any], *, drifted: bool) -> str:
    """The table row a cut counts in: only an episode's first pushback counts as a catch."""
    if not drifted:
        return "no-drift"
    pushes = [e for e in case.get("events") or () if isinstance(e, dict)]
    if pushes and not any(e.get("first") for e in pushes):
        return "drift-persistence"
    return "drift"


# --- Claims, marked true or false rather than by pushback ---------------------------------------
#
# A pushback mark credits a claims flag only when the person pushed back, so an early warning
# scores as a false alarm and a true claim the person could not see the support for scores as a
# catch for the wrong reason. Each flagged claim is marked on two questions instead.

ANSWERS = {"y": "yes", "n": "no", "u": "unclear"}
CLAIM_AFTER_MESSAGES = 40
CLAIM_TEXT_CHARS = 2000
_TRUE_PROMPT = (
    "\n  Was this claim true when it was made, judged from the whole session?\n"
    "    y yes   n no   u unclear   s skip   q stop\n    > "
)
_VISIBLE_PROMPT = (
    "  Did anything the person could see in the session at that time show it?\n"
    "    y yes   n no   u unclear   s skip   q stop\n    > "
)
_REASON_PROMPT = "  One line: why?\n    > "


@dataclass(frozen=True)
class ClaimFlag:
    """One claims flag a reading raised: where, on which arm, and the message making the claim."""

    case: str
    arm: str
    result: str
    fact: str
    at: float


def claim_flags(readings: Mapping[str, Any]) -> list[ClaimFlag]:
    """Every claims `departure` or `not shown by the record`, with the cited claim it names.

    The claim is the earliest agent message the verdict cites; a flag citing none cannot be marked.
    """
    found: list[ClaimFlag] = []
    for case_id, entry in sorted(readings.items()):
        for arm, reading in sorted((entry or {}).items()) if isinstance(entry, dict) else ():
            if not isinstance(reading, dict):
                continue
            criteria = (reading.get("assessment") or {}).get("criteria") or {}
            claims = criteria.get(CLAIMS) if isinstance(criteria, dict) else None
            if not isinstance(claims, dict) or claims.get("result") not in {
                "departure",
                UNSUPPORTED,
            }:
                continue
            facts = reading.get("facts") or {}
            said = [
                (float(facts[c].get("at") or 0.0), str(c))
                for c in claims.get("cites") or ()
                if isinstance(facts.get(c), dict) and facts[c].get("type") == "agent_message"
            ]
            if said:
                at, fact = min(said)
                found.append(ClaimFlag(case_id, arm, str(claims["result"]), fact, at))
    return found


def claim_item_id(salt: str, case: str, fact: str) -> str:
    """Salted like a case id: one item per cut and claimed message, whichever arms flagged it."""
    return hashlib.sha256(f"{salt}|claim|{case}|{fact}".encode()).hexdigest()[:16]


def _claim_message(messages: list[Message], at: float) -> int | None:
    """The numbered message holding the agent's record stamped `at`: the latest reply begun then."""
    found = [i for i, m in enumerate(messages) if m.role == "claude" and m.at <= at + 1e-6]
    return found[-1] if found else None


def export_claims(*, home: str, say: Callable[[str], Any] = print) -> int:
    """Every claims flag across the reads, one item per cut and claimed message, for marking.

    An item says where the claim is and nothing about what raised it: no arm, no detector, no
    result. It is written to `claim-items.json` beside the cases, in a fixed shuffled order.
    """
    paths = _paths(home)
    body = lc._load(paths["cases"])  # noqa: SLF001
    by_case = {str(c["id"]): c for c in _cases(body)}
    src = str(body.get("source") or "fixtures")
    salt = _salt(paths)
    items: dict[str, dict[str, Any]] = {}
    conversations: dict[str, list[Message]] = {}
    for path in _read_files(paths):
        for flag in claim_flags(lc._load(path).get("cases") or {}):  # noqa: SLF001
            case = by_case.get(flag.case)
            if case is None:
                continue
            sid = str(case["sid"])
            if sid not in conversations:
                log = _transcript(sid, src)
                conversations[sid] = conversation(log) if log else []
            item_id = claim_item_id(salt, flag.case, flag.fact)
            items[item_id] = {
                "id": item_id,
                "case": flag.case,
                "sid": sid,
                "cut": float(case["cut"]),
                "claim_at": flag.at,
                "claim_message": _claim_message(conversations[sid], flag.at),
            }
    ordered = sorted(items.values(), key=lambda item: item["id"])
    random.Random(f"{SAMPLE_SEED}|claims").shuffle(ordered)  # noqa: S311 - a fixed order
    lc._write(paths["claim_items"], {"v": 1, "items": ordered})  # noqa: SLF001
    say(f"{len(ordered)} claims to mark, at {paths['claim_items']} (local, private).")
    say("Next: --claims-mark. Each screen shows the claim and what came after it, nothing else.")
    return 0


def _claim_screen(
    item: Mapping[str, Any], source: str, position: str, say: Callable[[str], Any]
) -> None:
    """The claim, what came before it, and the session after it: never what flagged it."""
    messages = conversation(_transcript(str(item["sid"]), source))
    n = item.get("claim_message")
    say("\n" + "=" * 76)
    say(f"  {position}   claim {item['id']}   session {str(item['sid'])[:8]}")
    if not isinstance(n, int) or not 0 <= n < len(messages):
        say("\n  The claim's message is not in this log. Answer u, or skip.")
        return

    def stamp(at: float) -> str:
        return datetime.datetime.fromtimestamp(at, datetime.UTC).strftime("%m-%d %H:%M")

    for message in messages[max(0, n - CONTEXT_MESSAGES) : n]:
        who = "YOU   " if message.role == "you" else "CLAUDE"
        say(f"\n  [{who} {stamp(message.at)}] {_clip(message.text, CONTEXT_CHARS)}")
    say(f"\n  THE CLAIM, #{n} at {stamp(messages[n].at)}")
    say(f"    {_clip(messages[n].text, CLAIM_TEXT_CHARS)}")
    say(f"\n  AFTER IT (the reading's cut was at {stamp(float(item['cut']))})")
    for message in messages[n + 1 : n + 1 + CLAIM_AFTER_MESSAGES]:
        who = "YOU   " if message.role == "you" else "CLAUDE"
        say(f"\n  [{who} {stamp(message.at)}] {_clip(message.text, CONTEXT_CHARS)}")


def _save_claim_marks(paths: Mapping[str, str], marks: Mapping[str, Any], items: int) -> str:
    lc._write(paths["claim_marks"], {"v": 1, "marks": dict(marks)})  # noqa: SLF001
    with open(paths["claim_marks"], "rb") as handle:
        sha = hashlib.sha256(handle.read()).hexdigest()
    os.makedirs(os.path.dirname(CLAIM_DIGEST_PATH), exist_ok=True)
    with open(CLAIM_DIGEST_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {"v": 1, "marks_digest": sha, "items": items, "marked": len(marks)},
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    return sha


def _valid_claim_mark(mark: Any) -> bool:
    return (
        isinstance(mark, dict)
        and mark.get("true") in ANSWERS.values()
        and mark.get("visible") in ANSWERS.values()
        and isinstance(mark.get("reason"), str)
    )


def mark_claims(
    *, home: str, ask: Callable[[str], Any] = input, say: Callable[[str], Any] = print
) -> int:
    """Two answers and a reason per exported claim, saved to `claim-marks.json` with its digest.

    Marks written by hand into `claim-marks.json` are kept; a run with nothing left to mark
    rewrites the digest from them.
    """
    paths = _paths(home)
    body = lc._load(paths["cases"])  # noqa: SLF001
    items = [i for i in lc._load(paths["claim_items"]).get("items") or () if isinstance(i, dict)]  # noqa: SLF001
    if not items:
        say(f"No claims at {paths['claim_items']}. Run --claims-export first.")
        return 1
    saved = lc._load(paths["claim_marks"]).get("marks") or {}  # noqa: SLF001
    marks = {k: v for k, v in saved.items() if _valid_claim_mark(v)}
    todo = [item for item in items if item["id"] not in marks]
    say(f"{len(todo)} of {len(items)} claims left. Judge from the session; nothing else is shown.")
    for index, item in enumerate(todo, 1):
        _claim_screen(item, str(body.get("source") or "fixtures"), f"{index}/{len(todo)}", say)
        true = _ask(ask, _TRUE_PROMPT, ANSWERS)
        if true is None:
            break
        if true == "skip":
            continue
        visible = _ask(ask, _VISIBLE_PROMPT, ANSWERS)
        if visible is None:
            break
        if visible == "skip":
            continue
        try:
            reason = " ".join(str(ask(_REASON_PROMPT)).split())
        except (EOFError, KeyboardInterrupt):
            break
        marks[item["id"]] = {"true": true, "visible": visible, "reason": reason}
        _save_claim_marks(paths, marks, len(items))
    sha = _save_claim_marks(paths, marks, len(items))
    say(f"\n{len(marks)} of {len(items)} claims marked. sha256 {sha}")
    say(f"Commit {_shown(CLAIM_DIGEST_PATH)} before --score reads them.")
    return 0


def claim_outcome(result: str, mark: Mapping[str, Any] | None) -> str:
    """Whether a claims flag was right, on the claim's own marks.

    A departure says the record contradicts the claim: right when the claim was false. "Not shown
    by the record" says nothing read shows it: right when it was false, or when nothing the person
    could see showed it.
    """
    if not mark:
        return "unmarked"
    true, visible = mark.get("true"), mark.get("visible")
    if result == "departure":
        return {"no": "right", "yes": "wrong"}.get(str(true), "unclear")
    if true == "no" or visible == "no":
        return "right"
    return "wrong" if true == "yes" and visible == "yes" else "unclear"


def claims_truth(
    paths: Mapping[str, str], readings: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    """The claims-truth section, or why there is none ("" when no claim marks exist)."""
    if not os.path.exists(paths["claim_marks"]):
        return {}, ""
    if not _in_repository(CLAIM_DIGEST_PATH):
        return {}, "the claim marks digest is not inside the repository"
    committed = lc.committed_digest(_ROOT, CLAIM_DIGEST_PATH)
    if isinstance(committed, str):
        return {}, committed.replace("marks digest", "claim marks digest")
    with open(paths["claim_marks"], "rb") as handle:
        if hashlib.sha256(handle.read()).hexdigest() != committed.marks_digest:
            return {}, "the local claim marks no longer hash to the committed digest"
    marks = lc._load(paths["claim_marks"]).get("marks") or {}  # noqa: SLF001
    salt = _salt(paths)
    counts: dict[str, dict[str, dict[str, int]]] = {}
    items: dict[str, dict[str, str]] = {}
    for flag in claim_flags(readings):
        item_id = claim_item_id(salt, flag.case, flag.fact)
        outcome = claim_outcome(flag.result, marks.get(item_id))
        tally = counts.setdefault(flag.arm, {}).setdefault(
            flag.result, dict.fromkeys(("right", "wrong", "unclear", "unmarked"), 0)
        )
        tally[outcome] += 1
        items.setdefault(item_id, {})[flag.arm] = outcome
    return {"marks_digest": committed.marks_digest, "counts": counts, "items": items}, ""


def _scored_read(
    paths: Mapping[str, str], tag: str
) -> tuple[dict[str, Any], Callable[[str, str], bool], str]:
    """The readings a score reads, whether its plan chose a cut and arm, and where it writes."""
    read_path, plan_path = _tagged(paths, tag)
    plan = lc._load(plan_path)  # noqa: SLF001
    read_arms = set(plan.get("arms") or ())
    chosen = set(plan.get("selection") or ())

    def planned(case_id: str, arm: str) -> bool:
        return f"{case_id}:{arm}" in chosen if chosen else arm in read_arms

    results_path = (
        os.path.join(os.path.dirname(RESULTS_PATH), f"results-{tag}.json") if tag else RESULTS_PATH
    )
    return lc._load(read_path).get("cases") or {}, planned, results_path  # noqa: SLF001


def score(*, home: str, say: Callable[[str], Any] = print, tag: str = "") -> int:
    """The outcome table per detector and arm, on final marks; counts and salted ids only.

    A `tag` scores `read-<tag>.json` into `results-<tag>.json`, leaving `results.json` as it is;
    a cut and arm its plan did not select is `not-run`.
    """
    paths = _paths(home)
    body = lc._load(paths["cases"])  # noqa: SLF001
    refusal = _run_refusal(paths, body) or _tag_refusal(tag)
    if refusal:
        say(refusal)
        return 1
    readings, planned, results_path = _scored_read(paths, tag)
    marks = _load_marks(paths, lc.digest(body)) or {}
    lived = lc._load(paths["live"]).get("cases") or {}  # noqa: SLF001
    per_case: dict[str, Any] = {}
    table: dict[str, dict[str, int]] = {}
    for case in body["cases"]:
        final = (marks.get(case["id"]) or {}).get("final") or {}
        drift = final.get("drift")
        if drift not in {"drift", "no-drift"}:
            continue
        drifted = drift == "drift"
        first = any(e.get("first") for e in case.get("events") or ())
        log = _transcript(str(case["sid"]), str(body.get("source") or "fixtures"))
        messages = conversation(log) if log else []
        start = _drift_start(case, messages)
        row: dict[str, Any] = {
            "mark": drift,
            "class": final.get("class"),
            "roles": case["roles"],
            "first": first,
        }
        live_case = lived.get(case["id"]) or {}
        for arm in ARMS:
            live_arm = (live_case.get("arms") or {}).get(arm)
            if live_arm is None and "refused" not in live_case:
                continue  # no words for this arm before the cut: not a case for it
            reading = (readings.get(case["id"]) or {}).get(arm)
            unread = reading is None and not planned(case["id"], arm)
            outcomes = {
                "live": _live_bin(live_arm, drifted=drifted, start=start),
                "steer": "offered" if live_arm and live_arm.get("steer") else "not-offered",
                "analyze": "not-run"
                if unread
                else _read_bin(reading, drifted=drifted, start=start),
                "intent": "not-run"
                if unread
                else _read_bin(reading, drifted=drifted, start=start, only="intent"),
                "claims": "not-run"
                if unread
                else _read_bin(reading, drifted=drifted, start=start, only=CLAIMS),
            }
            row[arm] = outcomes
            for detector, outcome in outcomes.items():
                key = f"{arm}|{detector}|{_population(case, drifted=drifted)}"
                table.setdefault(key, {})
                table[key][outcome] = table[key].get(outcome, 0) + 1
        per_case[case["id"]] = row
    summary = {
        "v": 1,
        "marks_digest": lc.committed_digest(_ROOT, DIGEST_PATH).marks_digest,  # type: ignore[union-attr]
        "cases_digest": lc.digest(body),
        "counts": table,
        "cases": per_case,
    }
    truth, why = claims_truth(paths, readings)
    if truth:
        summary["claims_truth"] = truth
    elif why:
        say(f"No claims-truth section: {why}.")
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    for key in sorted(table):
        say(f"  {key:40} " + ", ".join(f"{k} {v}" for k, v in sorted(table[key].items())))
    say(f"Written to {_shown(results_path)}: counts and salted case ids only.")
    return 0


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911 - one return per mode
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--build", action="store_true")
    group.add_argument("--reconcile", action="store_true")
    group.add_argument("--report", action="store_true")
    group.add_argument("--live", action="store_true")
    group.add_argument("--read", action="store_true")
    group.add_argument("--score", action="store_true")
    group.add_argument("--claims-export", action="store_true")
    group.add_argument("--claims-mark", action="store_true")
    parser.add_argument("--source", choices=("fixtures", "original"), default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--arm", action="append", choices=ARMS)
    parser.add_argument("--tag", default="")
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args(argv)
    refusal = _home_refusal(HOME)
    if refusal:
        print(refusal)
        return 1
    if args.live:
        return live(home=HOME, source=args.source)
    if args.read:
        return read(
            home=HOME,
            source=args.source,
            dry_run=args.dry_run,
            arms=tuple(args.arm or ARMS),
            tag=args.tag,
            cases=tuple(args.case),
        )
    if args.score:
        return score(home=HOME, tag=args.tag)
    if args.claims_export:
        return export_claims(home=HOME)
    if args.claims_mark:
        return mark_claims(home=HOME)
    if args.build:
        return build(home=HOME, source=args.source or "fixtures")
    if args.reconcile:
        return reconcile(home=HOME)
    if args.report:
        return report(home=HOME)
    return mark(home=HOME)


if __name__ == "__main__":
    raise SystemExit(main())
