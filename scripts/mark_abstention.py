#!/usr/bin/env python3
"""The answer key for "does a reading know when to say I can't tell".

DEC-17's evaluation needs expected answers written down BEFORE the producer is
pointed at them. A mark written after seeing an output is agreement, not a
mark. This collects those answers. The captain accepted the recorded case review
as sufficient to enable readings on 2026-09-14; scoring remains a separate act.

    mark_abstention.py --build      assemble cases from the live board
    mark_abstention.py              mark the unmarked ones, one call each
    mark_abstention.py --report     progress, and the spread of what is marked
    mark_abstention.py --freeze F   freeze a format 5 packet from the spec in F

## What a case has to put on screen, and why two versions of this failed

Twice, and both times for the same reason: the questions turned on something the
display did not show.

v1 drew cases from the history store, which keeps five fields per observation by
a deliberate allowlist. Every case rendered as a harness and a poll count. Four
identical rows in a row, fifty four questions, and a key marked unanimously
because there was nothing to tell the cases apart.

v2 moved to the live board and showed session metadata: a directive fragment, a
turn percentage, a state. Better, and still wrong. A reading does not read
metadata. It reads the **ledger** -- the `project_context` facts for that
session, filtered to the ones carrying a type, a source and a summary. Two of
six cases still rendered byte identical. The complaint was the same complaint.

So this version fetches the ledger per case and shows it. The question "can it
judge this" is operationally "does that ledger hold anything citable", and that
number is now on screen.

## Three properties, each a decision rather than a preference

**The marker is not the author.** Whoever wrote the producer must not write the
key, or the key records what the code already does. The tool refuses to guess a
mark, has no default, and has no "mark the rest like that one".

**A question with a fixed answer is not asked.** The Expected Output constraint
is only ever put to the model when the record it reads holds work evidence
(`reading.asks_output`), and this tool never grants tool output, so that is a
Pi session with a demonstrated work result. Asking it about any other session is
asking the marker to transcribe a constant, and half of v2's prompts did exactly
that. This reads the producer's own predicate over the case's ledger to know
which cases to skip. That is the producer's **contract**, not its output, and
the two are not the same thing: a tool that knows which questions are asked
cannot thereby agree with an answer.

**A mark is keyed on identity, never on position.** v2 hashed the row's index in
the board's session list. The board reorders on every state change, so a rebuild
silently re-attached answers to different sessions -- measured, four of six. The
key is now a hash of `(harness, sid)`, which is stable, and still carries no
session identity into the file that gets committed.

## What a scorer has to do, written down so it is not discovered later

The two constraints below live in this file, not in the annotation store. A
producer handed a session with no stored revision refuses it outright with
`nothing-typed`, before any evidence is read. So `score_abstention.py` hands
`reading.produce` these two lines as a **synthetic revision**, per case, as an
argument: nothing is written to `cargento-annotations.json`, no reading count
moves, and the Intent log stays the reader's. The first draft of this paragraph
had the scorer write and clear a store revision instead; `produce` takes
`revisions` as a parameter, so that was a write for nothing, and a write into
a file that is the reader's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, TypeGuard

import abstention_ledger

_SKILL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cargento", "skills", "cargento"
)


def _reading() -> Any:
    """The producer's CONTRACT, reached the way every sibling script reaches it.

    Deferred rather than imported at the top, because `scripts` is on mypy's
    path as well as being a package to the tests, and a module-level runtime
    import makes this file resolvable under two names. `bench_collect.py` does
    the same thing for the same reason.

    What is read is which constraints are asked and which entry types count as
    work, never a produced reading. A tool that knows the questions cannot
    thereby agree with an answer; one that can see outputs can.
    """
    if _SKILL not in sys.path:
        sys.path.insert(0, _SKILL)
    from cargento_runtime import reading  # noqa: PLC0415

    return reading


HOME = os.environ.get("CARGENTO_HOME") or os.path.expanduser("~/.cargento")
CASES_PATH = os.path.join(HOME, "abstention-cases.json")
MARKS_PATH = os.path.join(HOME, "abstention-marks.json")

# The same pair against every case. Held constant so the evidence is the only
# thing that varies; a per-case goal is the obvious place for the author's thumb.
GOAL = "Finish the work this session was started for."
OUTPUT = "Something I can check: a diff, a test run, or a file I can open."

# Format 5 (DRC-4666): each case carries its own intent, a goal and the outcome
# lines a reader would save, and a Claude Code case carries its checks frozen
# as they stood at the capture. The constant pair above cannot pose a line a
# passing test does not cover, which is the class DEC-23 left standing.
FORMAT_INTENT = 5
# When a case's intent counts as typed, unless it names its own time: before
# every session end, for the reason `score_abstention.YARDSTICK_AT` gives.
INTENT_AT = 1.0
# A frozen case the machine's own records do not vouch for: scored, and never
# counted toward the recorded floor (DRC-4666 review, F4).
ORIGIN_SYNTHETIC = "synthetic"
# Where a recorded session's words can come from. A transcript anywhere else
# was written by somebody, not recorded by the harness.
CLAUDE_PROJECTS_ROOT = os.path.join(abstention_ledger.real_home(), ".claude", "projects")
# Where the freeze reads the dashboard's own history and ends: the store the
# lifecycle was observed into, never the packet's directory.
STORE_HOME = os.path.join(abstention_ledger.real_home(), ".cargento")

# Cases per (harness, end shape), so the corpus spreads instead of filling up
# with whichever harness ran most today. v2 had this constant and no bucketing,
# which is how a six case corpus came to be six Claude sessions in one state.
PER_BUCKET = 3


def cases_digest(body: dict[str, Any]) -> str:
    """Bind replay marks to the evidence and yardstick the marker saw."""
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def is_intent_packet(body: dict[str, Any]) -> bool:
    return body.get("v") == FORMAT_INTENT


def _epoch(value: Any) -> TypeGuard[float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value  # noqa: PLR0124 - NaN is the one value unequal to itself
        and 0 < value < float("inf")
    )


def case_revision(case: dict[str, Any]) -> dict[str, Any]:
    """A format 5 case's intent as the one revision `reading.produce` reads.

    Handed in as an argument, never written to the store, as the yardstick is.
    """
    raw = case.get("intent")
    intent: dict[str, Any] = raw if isinstance(raw, dict) else {}
    revision: dict[str, Any] = {
        "n": 1,
        "at": intent["at"] if _epoch(intent.get("at")) else INTENT_AT,
        "goal": str(intent.get("goal") or ""),
        "lines": list(intent.get("lines") or []),
    }
    for key in ("window_start", "goal_source", "goal_source_at"):
        if key in intent:
            revision[key] = intent[key]
    return revision


def case_lines(case: dict[str, Any]) -> tuple[str, ...]:
    return tuple(_reading().outcome_lines(case_revision(case)))


def case_constraints(body: dict[str, Any], case: dict[str, Any]) -> tuple[str, ...]:
    """What is marked and scored for this case: goal and output, or goal and each line."""
    if is_intent_packet(body):
        return tuple(_reading().constraints_for(case_lines(case)))
    return ("goal", "output")


def case_checks(
    body: dict[str, Any], case: dict[str, Any]
) -> tuple[dict[str, str] | None, frozenset[tuple[str, str]]]:
    """The frozen tails and changed-after pairs, or None where no check is read.

    Only a format 5 Claude Code case carries checks, because only that harness
    publishes them and only this packet froze them at the capture.
    """
    if not is_intent_packet(body) or case.get("harness") != "claude":
        return None, frozenset()
    raw = case.get("tool_output")
    frozen: dict[str, Any] = raw if isinstance(raw, dict) else {}
    tails = frozen.get("tails")
    pairs = frozen.get("changed_after")
    return (
        {str(k): str(v) for k, v in tails.items()} if isinstance(tails, dict) else {},
        frozenset(
            (str(pair[0]), str(pair[1]))
            for pair in pairs or ()
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        )
        if isinstance(pairs, list)
        else frozenset(),
    )


def case_ledger(body: dict[str, Any], case: dict[str, Any]) -> tuple[Any, ...]:
    """The frozen ledger the producer will read, checks included where frozen."""
    tails, changed = case_checks(body, case)
    return tuple(
        _reading().build_ledger(
            case.get("producer_facts") or [],
            str(case.get("harness") or ""),
            str(case.get("sid") or ""),
            tool_output=tails,
            changed_after=changed,
        )
    )


def _get(url: str, timeout: int = 30) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed loopback
        return json.loads(response.read().decode("utf-8"))


def _text(value: Any) -> str:
    """The row publishes several of these as an object carrying a label."""
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return str(value or "")


_TRANSCRIPTS: dict[str, str] | None = None


def _transcript_index() -> dict[str, str]:
    """Walk the Claude project tree once, not once per case.

    Measured: walking it per case took the build past two minutes on this
    machine, because the tree is large and every case paid for the whole of it.
    """
    global _TRANSCRIPTS  # noqa: PLW0603 - a process-lifetime index, built once
    if _TRANSCRIPTS is not None:
        return _TRANSCRIPTS
    index: dict[str, str] = {}
    root = CLAUDE_PROJECTS_ROOT
    try:
        for base, _dirs, names in os.walk(root):
            for name in names:
                if name.endswith(".jsonl"):
                    index.setdefault(name[:8], os.path.join(base, name))
    except OSError:
        pass
    _TRANSCRIPTS = index
    return index


def _first_ask(harness: str, sid: str) -> str:
    """What the session was started for, in the reader's own words.

    The board publishes `instruction`, which is `directives[-1]` -- the LATEST
    usable directive, not the opening one. For a long session that is some
    mid-flight command: one case rendered as "commit and push once tests pass"
    for a session whose purpose was finding a quick-win issue, which left the
    marker judging a sentence with no context. DRC-4509 records the same
    distinction from the other side.

    Stops at the first real user turn rather than reading the file, because
    these transcripts run to megabytes and only the opening ask is wanted.
    """
    if harness != "claude":
        return ""
    path = _transcript_index().get(sid[:8])
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") != "user":
                    continue
                content = (record.get("message") or {}).get("content")
                text = (
                    content
                    if isinstance(content, str)
                    else " ".join(
                        b.get("text", "")
                        for b in content or []
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                )
                text = " ".join(str(text).split())
                # A skill body, a caveat banner and an interrupt notice all
                # arrive as user turns and none of them is something asked.
                skip = ("<", "Caveat:", "[Request interrupted", "Base directory")
                if text and not text.startswith(skip):
                    return text
    except OSError:
        return ""
    return ""


def _case_id(harness: str, sid: str) -> str:
    """A stable key over identity, and nothing readable.

    Not the position, which was v2's fatal defect. Not the state, which moves.
    The marks file is the half that gets committed, and a session id in it would
    publish which of the reader's sessions were used, so it is hashed. The cases
    file keeps the identity and stays on this machine.
    """
    return hashlib.sha256(f"{harness}|{sid}".encode()).hexdigest()[:16]


def _end_shape(row: dict[str, Any]) -> str:
    """How this session ended, in the producer's own three-way distinction."""
    if row.get("ended_at"):
        return "session end observed"
    if str(row.get("state") or "") not in {"idle", "ended"}:
        return "still running"
    if row.get("finished_at"):
        return "a turn stopped, no session end"
    return "went quiet, no end observed"


def _ledger(port: int, row: dict[str, Any]) -> dict[str, Any]:
    """What a reading would actually have to cite for this session.

    `facts` is the ledger the producer would hold and `citable` the subset a
    reading can build a claim on, which are `produce`'s two refusals in order.
    `work_results` is the subset that demonstrates work rather than describing
    a request, which is what the Expected Output constraint needs.

    Both numbers come from the producer's own `build_ledger` and `_citable`
    rather than a second copy of their rules, because a second copy drifted:
    this counted a fact citable on `type` and `summary` alone, where rule 3
    also needs a named evidence source, and it scoped the list with
    `fact["sid"]` -- a key `project_context` does not write, so the filter
    admitted every fact the endpoint returned for the project. Both errors run
    the same way, toward a screen that says there is evidence where the
    producer will find none, and a case marked judge on that screen is refused
    before the model and counts for neither side.
    """
    project = str(row.get("project_key") or row.get("project") or "")
    harness, sid = str(row.get("harness") or ""), str(row.get("sid") or "")
    blank = {"facts": 0, "citable": 0, "work_results": 0, "reached": False}
    if not project:
        return blank
    query = urllib.parse.urlencode({"project": project, "session": f"{harness}:{sid}"})
    try:
        body = _get(f"http://127.0.0.1:{port}/api/project-context?{query}")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return blank
    reading = _reading()
    facts = ((body or {}).get("semantic") or {}).get("facts") or []
    # The endpoint answers for the focused session and for its children and
    # the project-scoped facts they share a work item with, so the scoping is
    # the producer's to do, not this tool's to assume.
    mine = reading.build_ledger(facts, harness, sid)
    citable = [entry for entry in mine if reading._citable(entry)]  # noqa: SLF001 - see above
    work = [entry for entry in citable if reading.demonstrates_work(entry)]
    return {
        "facts": len(mine),
        "citable": len(citable),
        "work_results": len(work),
        "reached": True,
    }


def _signature(case: dict[str, Any]) -> tuple[Any, ...]:
    """What makes two cases the same question.

    Measured: cases 19 and 20 of a 23 case run rendered byte identical -- same
    harness, no ask, no directive, no facts, no end -- and were asked as two
    separate questions. A marker answering the same screen twice is being
    charged twice for one judgement.
    """
    barren = not case.get("asked_for") and not case["citable"]
    return (
        # A session with no recorded ask and no citable fact is the same
        # question on every harness: should the board speak about something it
        # recorded nothing of. Keeping the harness split it into four screens
        # that differed only by a name in the header.
        "" if barren else case["harness"],
        bool(case.get("asked_for")),
        bool(case.get("directive")),
        case["end_shape"],
        case["citable"] > 0,
        case["work_results"] > 0,
    )


def _dedupe(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One case per distinct question."""
    seen: set[tuple[Any, ...]] = set()
    kept = []
    for case in cases:
        signature = _signature(case)
        if signature in seen:
            continue
        seen.add(signature)
        case["stands_for"] = sum(1 for other in cases if _signature(other) == signature)
        kept.append(case)
    return kept


def _bucket(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Take PER_BUCKET of each (harness, end shape), so the corpus spreads."""
    seen: dict[tuple[str, str], int] = {}
    kept = []
    for case in cases:
        key = (str(case["harness"]), str(case["end_shape"]))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= PER_BUCKET:
            kept.append(case)
    return kept


def build(port: int, *, force: bool = False) -> int:
    """Draw cases from the live board and enrich each with its ledger.

    `all=1` matters. Without it the board returns only what ran inside
    `window_hours`, which is a day, and the corpus is then whatever happened
    today. The sessions that have actually ended -- the ones a final reading
    turns on -- are mostly older than that.
    """
    existing = _load(MARKS_PATH)
    held = dict(existing.get("marks") or {}) if existing else {}

    try:
        payload = _get(f"http://127.0.0.1:{port}/api/data?all=1")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        print(f"Could not read the board on port {port}: {error}")
        print("Start the dashboard first, then run this again.")
        return 1

    rows = payload.get("sessions") or []
    if not rows:
        print(f"The board on port {port} returned no sessions, so there is no corpus.")
        print("Nothing was written. Start the dashboard where your sessions are.")
        return 1

    cases: list[dict[str, Any]] = []
    for row in rows:
        harness, sid = str(row.get("harness") or ""), str(row.get("sid") or "")
        if not harness or not sid:
            continue
        cases.append(
            {
                "id": _case_id(harness, sid),
                "harness": harness,
                "sid": sid,
                "project": row.get("project"),
                "title": row.get("title"),
                "asked_for": _first_ask(harness, sid),
                "directive": _text(row.get("instruction")) or _text(row.get("last_prompt")),
                "state": row.get("state"),
                "end_shape": _end_shape(row),
                "acquisition": row.get("acquisition") or "events",
                "annotated": bool(row.get("annotation_revision")),
            }
        )

    cases = _bucket(cases)
    print(f"Fetching the evidence ledger for {len(cases)} sessions.")
    for case in cases:
        case.update(_ledger(port, {"project_key": case["project"], **case}))
        # The Expected Output constraint is only ever put to the model where
        # the ledger holds work evidence. Elsewhere the answer is fixed by the
        # ruling and asking for it wastes the marker.
        case["asks_output"] = bool(case.get("work_results"))

    unique = _dedupe(cases)
    dropped = len(cases) - len(unique)
    cases = unique

    orphans = [k for k in held if k not in {c["id"] for c in cases}]
    if orphans and not force:
        print(f"\n{len(orphans)} existing marks name sessions this build does not include.")
        print("Rebuilding would leave them pointing at nothing. Re-run with --force")
        print("to rebuild anyway; the marks themselves are never deleted by a build.")
        return 1

    _write(CASES_PATH, {"v": 3, "goal": GOAL, "output": OUTPUT, "cases": cases})

    shapes = {c["end_shape"] for c in cases}
    harnesses = {c["harness"] for c in cases}
    with_facts = sum(1 for c in cases if c["citable"])
    print(f"\nBuilt {len(cases)} cases: {len(harnesses)} harnesses, {len(shapes)} end shapes.")
    if dropped:
        print(f"  {dropped} were dropped as the same question asked twice.")
    print(f"  {with_facts} carry citable evidence, {len(cases) - with_facts} carry none.")
    print(f"  {sum(1 for c in cases if c['asks_output'])} can be asked the OUTPUT question.")
    # Proportional, not merely non-zero. Measured: a 21 case corpus where one
    # case carried evidence and twenty did not passed a `not in {0, len}` test
    # and was still twenty near identical screens. A dimension that splits one
    # from twenty does not separate a producer that abstains from one that
    # never does.
    thin = min(with_facts, len(cases) - with_facts) < max(2, len(cases) // 5)
    if len(shapes) < 2 or thin:
        print("\n  This corpus does not vary in what the questions turn on, so a key")
        print("  marked against it cannot fail a producer that never abstains.")
        print("  It wants sessions that ended and sessions that did not, and some")
        print("  with recorded evidence and some without.")
    print(f"\nWritten to {CASES_PATH} (stays on this machine, never committed).")
    return 0


def _runtime_config() -> Any:
    """The runtime config the dashboard would build here, for the freeze's reads."""
    _reading()
    from cargento_runtime import config  # noqa: PLC0415 - see `_reading`

    return config.build_runtime_config(
        environ=os.environ,
        platform_name=sys.platform,
        os_name=os.name,
        launcher_path=pathlib.Path(_SKILL, "server.py"),
    )


def _session_facts(port: int, project: str, harness: str, sid: str) -> list[dict[str, Any]] | None:
    query = urllib.parse.urlencode({"project": project, "session": f"{harness}:{sid}"})
    try:
        body = _get(f"http://127.0.0.1:{port}/api/project-context?{query}")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    facts = ((body or {}).get("semantic") or {}).get("facts") or []
    return [fact for fact in facts if isinstance(fact, dict)]


class FreezeError(ValueError):
    """Why a spec entry cannot become a recorded case. Closed words, no session text."""


def _inside(path: str, root: str) -> bool:
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real.startswith(base + os.sep)


def _transcript_is_the_session(path: str, sid: str) -> bool:
    """Whether every record in it names this session, and at least one does."""
    seen = False
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                named = record.get("sessionId") if isinstance(record, dict) else None
                if named is None:
                    continue
                if not isinstance(named, str) or not named.startswith(sid):
                    return False
                seen = True
    except OSError:
        return False
    return seen and len(sid) >= 8


def _same(a: Any, b: Any) -> bool:
    return _epoch(a) and _epoch(b) and abs(float(a) - float(b)) < 1e-3


def _lifecycle_recorded(
    snapshot: dict[str, Any],
    captured: float,
    observations: Any,
    ends: Any,
) -> bool:
    """Whether the dashboard's own stores observed the lifecycle the spec claims.

    A running row needs a `working` observation at the capture itself; an end
    needs the ends store's stamp; a turn stop needs an `idle` observation at
    the stop. Anything else is hand-typed.
    """
    key = (snapshot["harness"], snapshot["sid"])
    mine = [
        o for o in observations if isinstance(o, dict) and (o.get("harness"), o.get("sid")) == key
    ]
    if snapshot.get("ended_at") is not None:
        return any(
            isinstance(e, dict)
            and (e.get("harness"), e.get("sid")) == key
            and _same(e.get("at"), snapshot["ended_at"])
            for e in ends
        )
    if snapshot.get("state") == "working":
        return any(
            o.get("state") == "working" and _same(o.get("last_activity"), captured) for o in mine
        )
    if snapshot.get("state") == "idle" and snapshot.get("finished_at") is not None:
        return any(
            o.get("state") == "idle" and _same(o.get("last_activity"), snapshot["finished_at"])
            for o in mine
        )
    return False


def _frozen_checks(
    config: Any, entry: dict[str, Any], sid: str, captured: float, unconfirmed: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """A Claude Code case's checks as they stood, noting what the transcript cannot vouch for."""
    transcript = str(entry.get("transcript") or _transcript_index().get(sid[:8]) or "")
    if not transcript or not os.path.isfile(transcript):
        raise FreezeError("no-transcript")
    if not _inside(transcript, CLAUDE_PROJECTS_ROOT):
        unconfirmed.append("transcript-outside-projects")
    if not _transcript_is_the_session(transcript, sid):
        unconfirmed.append("transcript-other-session")
    from cargento_runtime import project_context  # noqa: PLC0415 - see `_reading`

    checks, press = project_context.frozen_claude_checks(config, transcript, sid, until=captured)
    return checks, {
        "tails": dict(press.tails),
        "changed_after": sorted([list(pair) for pair in press.changed_after]),
    }


def provenance(
    case: dict[str, Any], *, observations: Any, ends: Any, index: dict[str, str]
) -> list[str]:
    """Why a frozen case cannot be called recorded, from the machine's own records.

    The freeze's checks, repeated at score time, because the packet is
    hand-editable and the scorer read `origin` as written (V2). `index` maps a
    Claude Code sid's first eight characters to its transcript, as
    `_transcript_index` builds it from `CLAUDE_PROJECTS_ROOT`.
    """
    snapshot = case.get("row_snapshot")
    captured = case.get("captured_at")
    if not isinstance(snapshot, dict) or not _epoch(captured):
        return ["lifecycle-unconfirmed"]
    reasons: list[str] = []
    if not _lifecycle_recorded(snapshot, float(captured), observations, ends):
        reasons.append("lifecycle-unconfirmed")
    if case.get("harness") == "claude":
        sid = str(case.get("sid") or "")
        transcript = index.get(sid[:8])
        if not transcript:
            reasons.append("transcript-missing")
        else:
            if not _inside(transcript, CLAUDE_PROJECTS_ROOT):
                reasons.append("transcript-outside-projects")
            if not _transcript_is_the_session(transcript, sid):
                reasons.append("transcript-other-session")
    return reasons


def make_vouch(*, observations: Any, ends: Any, index: dict[str, str]) -> Any:
    """`provenance` bound to one set of records, for the scorer to call per case."""

    def vouch(case: Any) -> list[str]:
        return provenance(dict(case), observations=observations, ends=ends, index=index)

    return vouch


def machine_vouch(store_home: str) -> Any:
    """`make_vouch` over this machine's history, ends and Claude Code transcripts."""
    observations, ends = _observed_stores(store_home)
    return make_vouch(observations=observations, ends=ends, index=_transcript_index())


def freeze_case(
    config: Any,
    entry: dict[str, Any],
    facts: list[dict[str, Any]],
    *,
    observations: Any = (),
    ends: Any = (),
) -> dict[str, Any]:
    """One recorded case, frozen as the session stood at `captured_at`.

    The case is `recorded` only when the machine vouches for it: a Claude Code
    transcript inside `CLAUDE_PROJECTS_ROOT` whose records name this session,
    and a lifecycle the dashboard's history or ends store observed
    (`observations`, `ends`). Anything short of that is `synthetic`, with the
    reasons listed in `unconfirmed`, and never counts toward the floor.

    Facts are kept only where dated at or before the capture. A Claude Code
    check is never one of them: its latest run, earlier failure and later
    change are computed over the whole transcript, so it is rebuilt from the
    transcript as it stood (`project_context.frozen_claude_checks`), with the
    output tails and changed-after pairs a press at that moment carried.

    A row may be a recorded history `working` observation, which is how a
    Codex case exists at all: Codex has no session-end hook and is never read
    at a turn stop (DRC-4666, decisions of 2026-09-24).
    """
    harness, sid = str(entry.get("harness") or ""), str(entry.get("sid") or "")
    at = entry.get("captured_at")
    if not harness or not sid:
        raise FreezeError("no-identity")
    if not _epoch(at):
        raise FreezeError("bad-captured-at")
    captured = float(at)
    raw_row = entry.get("row")
    row: dict[str, Any] = raw_row if isinstance(raw_row, dict) else {}
    snapshot = {
        "harness": harness,
        "sid": sid,
        "state": row.get("state"),
        "finished_at": row.get("finished_at"),
        "ended_at": row.get("ended_at"),
    }
    settle = float(config.reading_settle_sec)
    for field in ("ended_at", "finished_at"):
        stamp = snapshot[field]
        if stamp is not None and (not _epoch(stamp) or captured < float(stamp) + settle):
            raise FreezeError("captured-before-settled")
    intent = entry.get("intent")
    if not isinstance(intent, dict) or not case_lines({"intent": intent}):
        raise FreezeError("no-outcome-line")
    kept = [
        fact
        for fact in facts
        if isinstance(fact.get("source_session"), dict)
        and (fact["source_session"].get("harness"), fact["source_session"].get("sid"))
        == (harness, sid)
        and fact.get("type") != _reading().TOOL_REPORT_TYPE
        and _epoch(fact.get("at"))
        and fact["at"] <= captured
    ]
    unconfirmed: list[str] = []
    if not _lifecycle_recorded(snapshot, captured, observations, ends):
        unconfirmed.append("lifecycle-unconfirmed")
    case: dict[str, Any] = {
        "id": _case_id(harness, sid),
        "harness": harness,
        "sid": sid,
        "origin": "recorded",
        "project": entry.get("project"),
        "title": entry.get("title"),
        "captured_at": captured,
        "row_snapshot": snapshot,
        "intent": intent,
    }
    if harness == "claude":
        checks, case["tool_output"] = _frozen_checks(config, entry, sid, captured, unconfirmed)
        kept.extend(checks)
    case["producer_facts"] = kept
    case["unconfirmed"] = unconfirmed
    if unconfirmed:
        case["origin"] = ORIGIN_SYNTHETIC
    return case


def _observed_stores(store_home: str) -> tuple[Any, Any]:
    """The dashboard's history observations and session ends, read from `store_home`."""
    _reading()
    from cargento_runtime import config as config_mod  # noqa: PLC0415 - see `_reading`
    from cargento_runtime import ends, history  # noqa: PLC0415 - see `_reading`

    config = config_mod.build_runtime_config(
        environ={**os.environ, "CARGENTO_HOME": store_home},
        platform_name=sys.platform,
        os_name=os.name,
        launcher_path=pathlib.Path(_SKILL, "server.py"),
    )
    return history.load(config)[0], ends.load(config)


def freeze(port: int, spec_path: str, *, force: bool = False, store_home: str = "") -> int:
    """Write a format 5 packet from a spec of recorded moments. Spends nothing.

    The spec is local and hand-written: per case the harness, sid, project,
    `captured_at`, the recorded `row` lifecycle, the `intent` and, for Claude
    Code, optionally the transcript path.
    """
    spec = _load(spec_path)
    entries = spec.get("cases") if isinstance(spec.get("cases"), list) else []
    if not entries:
        print(f"No cases in {spec_path}.")
        return 1
    if _marks(_load(MARKS_PATH)) and not force:
        print("Marks already exist here and would belong to a different packet.")
        print("Use a fresh CARGENTO_HOME, or --force to write the packet anyway.")
        return 1
    config = _runtime_config()
    observations, ends = _observed_stores(store_home or STORE_HOME)
    cases: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            print(f"Case {index}: not an object")
            return 1
        facts = _session_facts(
            port, str(entry.get("project") or ""), str(entry.get("harness")), str(entry.get("sid"))
        )
        if facts is None:
            print(f"Case {index}: the board on port {port} did not answer for it")
            return 1
        try:
            cases.append(freeze_case(config, entry, facts, observations=observations, ends=ends))
        except FreezeError as error:
            print(f"Case {index}: {error}")
            return 1
    _write(CASES_PATH, {"v": FORMAT_INTENT, "cases": cases})
    synthetic = sum(1 for case in cases if case["origin"] == ORIGIN_SYNTHETIC)
    print(f"Froze {len(cases)} cases into {CASES_PATH} (stays on this machine).")
    if synthetic:
        print(f"  {synthetic} are synthetic: the machine's records do not vouch for them.")
    return 0


def _write(path: str, body: dict[str, Any]) -> None:
    """Atomically, because this file is somebody's evening.

    v2 truncated in place: a Ctrl-C between `open` and `dump` left a zero length
    file and the next run died on it with no backup.
    """
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    # Its own temporary file: two runs sharing one `.tmp` crashed in review.
    descriptor, tmp = tempfile.mkstemp(prefix=".write-", suffix=".tmp", dir=os.path.dirname(path))
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _load(path: str) -> dict[str, Any]:
    """Never a traceback. This reads files a person can edit or interrupt."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            body = json.load(handle)
    except (OSError, ValueError) as error:
        print(f"Could not read {path}: {error}")
        return {}
    if not isinstance(body, dict):
        print(f"{path} is not an object, so it is not one of ours. Ignoring it.")
        return {}
    return body


def _marks(body: dict[str, Any]) -> dict[str, Any]:
    """Only the entries that carry both columns. A half written one is not a mark."""
    raw = body.get("marks")
    if not isinstance(raw, dict):
        return {}
    return {
        k: v
        for k, v in raw.items()
        if isinstance(v, dict)
        and isinstance(v.get("goal"), str)
        and ("output" in v or "line_1" in v)
    }


def _ask(prompt: str) -> str | None:
    """One call, no default. Returns None if the marker wants to stop."""
    while True:
        try:
            reply = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if reply in {"y", "yes"}:
            return "judge"
        if reply in {"n", "no"}:
            return "abstain"
        if reply in {"s", "skip"}:
            return "skip"
        if reply in {"q", "quit"}:
            return None
        print("  y = it should judge, n = it should refuse, s = skip, q = stop")


def _short(text: str, limit: int) -> str:
    """Cut at a word boundary, and say that it was cut.

    A mid-word cut reads as a typo and a silent one reads as the whole ask.
    """
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " ..."


def _headline(case: dict[str, Any]) -> str:
    """The ask, reduced to something a question can carry.

    A pasted plan is hundreds of words and its first line is a preamble, so the
    first sentence is taken where there is one and the derived title otherwise.
    """
    asked = " ".join(str(case.get("asked_for") or "").split())
    if not asked:
        return str(case.get("title") or "what you asked")
    first = asked.split(". ")[0]
    return _short(first if 12 <= len(first) <= 110 else asked, 110)


def _show(case: dict[str, Any], position: str) -> None:
    """One self contained screen: what was asked, what is recorded, the question.

    The question used to name a GOAL defined once in a header, which by case 20
    was far off the top of the terminal. A marker cannot judge against a
    sentence they cannot see, so the ask is restated on every screen, in the
    session's own words rather than a constant.
    """
    asked = str(case.get("asked_for") or "")
    latest = str(case.get("directive") or "")
    print("\n" + "=" * 72)
    stands = case.get("stands_for") or 1
    also = f"   (this shape covers {stands} sessions)" if stands > 1 else ""
    print(f"  {position}   {case['harness']} - {case.get('project') or 'no project'}{also}")

    print("\n  YOU ASKED IT TO")
    if asked:
        print(f"    {_short(asked, 260)}")
    elif case.get("title"):
        print(f"    {case['title']}   (a title Cargento derived; the ask was not recorded)")
    else:
        print("    nothing Cargento managed to record")
    if latest and latest[:60] != asked[:60]:
        print(f"\n  LAST TOLD\n    {_short(latest, 180)}")

    print("\n  WHAT CARGENTO HAS TO GO ON")
    if not case.get("reached"):
        print("    the evidence ledger could not be read")
    elif case["citable"]:
        print(
            f"    {case['citable']} citable facts, {case['work_results']} of them showing work done"
        )
    else:
        print("    nothing. no facts it could cite.")
    print(f"    {case['end_shape']}")


def _question(case: dict[str, Any]) -> str:
    """The question, naming both answers in plain words.

    "Can it judge whether this met the GOAL" asks about a capability in the
    abstract. This asks what the board should say, which is the thing being
    marked.
    """
    tail = "    y = it has enough to answer    n = it must say it cannot tell\n    [y/n/s/q] "
    if not case.get("asked_for"):
        return (
            "\n  Cargento never recorded what this session was asked for.\n"
            "  Should it still say whether the session did it?\n" + tail
        )
    return (
        f"\n  You want to know: did it {_headline(case)}\n"
        "  Should Cargento answer that, or say it cannot tell?\n" + tail
    )


def _show_intent_case(body: dict[str, Any], case: dict[str, Any], position: str) -> None:
    """A format 5 screen: the case's own intent, then the frozen record, checks included."""
    revision = case_revision(case)
    print("\n" + "=" * 72)
    print(f"  {position}   {case['harness']} - {case.get('title') or case['id']}")
    print(f"  Recorded lifecycle: {_reading().end_kind(case.get('row_snapshot') or {})}")
    print(f"  Captured at: {case.get('captured_at')}")
    if case.get("asked_for"):
        print(f"  Opening request (review context): {_short(case['asked_for'], 260)}")
    print(f"\n  GOAL: {revision['goal']}")
    for k, line in enumerate(revision["lines"], 1):
        text = line.get("text") if isinstance(line, dict) else line
        source = line.get("source") if isinstance(line, dict) else ""
        print(f"  OUTCOME LINE {k}: {text}" + (f"   ({source})" if source else ""))
    print("  FROZEN PRODUCER LEDGER (review excerpts are not model evidence)")
    ledger = case_ledger(body, case)
    for entry in ledger:
        flags = [
            word
            for word, on in (
                ("changed after", entry.get("changed_after") is True),
                ("stale", entry.get("stale") is True),
            )
            if on
        ]
        more = f"  [{', '.join(flags)}]" if flags else ""
        print(f"    {entry['id']} | {entry['type']} | {entry['source']} | {entry['summary']}{more}")
        if entry.get("tail"):
            print(f"        output tail: {entry['tail']}")
    if not any(_reading().demonstrates_work(entry) for entry in ledger):
        print("    no check or written file in this record")


def _show_mark_case(body: dict[str, Any], case: dict[str, Any], position: str) -> None:
    if is_intent_packet(body):
        _show_intent_case(body, case, position)
        return
    if body.get("v") != 4:
        _show(case, position)
        return
    print("\n" + "=" * 72)
    print(f"  {position}   {case['harness']} - {case.get('title') or case['id']}")
    print(f"  Recorded lifecycle: {_reading().end_kind(case.get('row_snapshot') or {})}")
    if case.get("asked_for"):
        print(f"  Opening request (review context): {_short(case['asked_for'], 260)}")
    print(f"\n  GOAL YARDSTICK: {body.get('goal') or ''}")
    print(f"  OUTPUT YARDSTICK: {body.get('output') or ''}")
    print("  FROZEN PRODUCER LEDGER (review excerpts are not model evidence)")
    for entry in _reading().build_ledger(
        case.get("producer_facts") or [], case["harness"], case["sid"]
    ):
        print(f"    {entry['id']} | {entry['type']} | {entry['source']} | {entry['summary']}")


def _mark_question(body: dict[str, Any], case: dict[str, Any], constraint: str) -> str:
    if is_intent_packet(body):
        revision = case_revision(case)
        if constraint == "goal":
            what = f"this goal: {revision['goal']}"
        else:
            k = int(constraint.rsplit("_", 1)[1])
            what = f"outcome line {k}: {case_lines(case)[k - 1]}"
        return (
            f"\n  Against {what}\n"
            "  Should Cargento answer from the frozen record, or say it cannot tell?\n"
            "    y = it has enough to answer    n = it must say it cannot tell\n    [y/n/s/q] "
        )
    if body.get("v") == 4:
        return (
            f"\n  Against this {constraint} yardstick: {body.get(constraint) or ''}\n"
            "  Should Cargento answer from the frozen ledger, or say it cannot tell?\n"
            "    y = it has enough to answer    n = it must say it cannot tell\n    [y/n/s/q] "
        )
    if constraint == "goal":
        return _question(case)
    return (
        "\n  And could it say whether a checkable deliverable came out,\n"
        "  a diff, a test run, a file you can open?\n    [y/n/s/q] "
    )


def _mark_asks_output(body: dict[str, Any], case: dict[str, Any]) -> bool:
    """The producer's own predicate, over the ledger it will read.

    A format 5 Claude Code case's ledger carries its frozen checks, as the
    scorer's press does; every other ledger holds none.
    """
    if is_intent_packet(body):
        text = " ".join(case_lines(case))
        return bool(_reading().asks_output(text, case_ledger(body, case)))
    if body.get("v") == 4:
        ledger = _reading().build_ledger(
            case.get("producer_facts") or [], case["harness"], case["sid"]
        )
        return bool(_reading().asks_output(str(body.get("output") or ""), ledger))
    return bool(case.get("asks_output"))


def _bound_marks(body: dict[str, Any], entries: dict[str, Any]) -> dict[str, Any]:
    if is_intent_packet(body):
        return {"v": 4, "marks": entries, "cases_digest": cases_digest(body)}
    if body.get("v") == 4:
        return {"v": 3, "marks": entries, "cases_digest": cases_digest(body)}
    return {"v": 2, "marks": entries}


def _mark_one(body: dict[str, Any], case: dict[str, Any]) -> dict[str, str] | None:
    """One case's answers, {} when skipped, None when the marker stopped."""
    names = case_constraints(body, case)
    answers: dict[str, str] = {}
    goal = _ask(_mark_question(body, case, "goal"))
    if goal is None or goal == "skip":
        return None if goal is None else {}
    answers["goal"] = goal
    if _mark_asks_output(body, case):
        for name in names[1:]:
            got = _ask(_mark_question(body, case, name))
            if got is None or got == "skip":
                return None if got is None else {}
            answers[name] = got
        return answers
    # Not asked, and saying so is the point. The constraint is never put to the
    # model where the record holds no work evidence, so the answer is the
    # ruling's rather than the marker's.
    answers.update(dict.fromkeys(names[1:], "abstain"))
    print("  The outcome question is not asked here: this record shows no check or")
    print("  demonstrated work result, so the ruling already fixes the answer.")
    return answers


def _ledger_refusal() -> bool:
    """True, having said why, once the qualification has charged any call.

    A mark written after an output was seen is agreement, not a mark, so the
    key is frozen from the first charge (review, F1). An unreadable ledger
    counts as charged: fail closed.
    """
    committed = abstention_ledger.committed_chain(abstention_ledger.CLAUDE_SUMMARY_PATH)
    if not abstention_ledger.has_calls(abstention_ledger.LEDGER_PATH) and not (
        committed and committed.get("calls")
    ):
        return False
    print("The spend ledger already holds a call, so the answer key is frozen.")
    print("Marks cannot be written or discarded after anything has been spent.")
    return True


def mark() -> int:
    if _ledger_refusal():
        return 1
    body = _load(CASES_PATH)
    cases = body.get("cases") if isinstance(body.get("cases"), list) else None
    if not cases:
        print(f"No cases at {CASES_PATH}. Run --build first.")
        return 1
    saved = _load(MARKS_PATH)
    entries = _marks(saved)
    replay = body.get("v") in (4, FORMAT_INTENT)
    digest = cases_digest(body)
    if replay and entries and saved.get("cases_digest") != digest:
        print("These marks belong to a different or unfrozen case set. Nothing was changed.")
        print(
            "Keep that key with its original cases; use a separate CARGENTO_HOME for this packet."
        )
        return 1

    todo = [c for c in cases if c.get("id") not in entries]
    if not todo:
        print(f"All {len(cases)} cases are marked. Nothing to do.")
        _warn_if_unanimous(entries, cases)
        return 0

    print(f"\n{len(todo)} of {len(cases)} left. y, n, s to skip, q to stop and keep what you did.")
    print("\nEach screen restates what that session was asked, so you never have to")
    print("scroll back. You are saying what Cargento SHOULD be able to say about it,")
    print("not what it currently does.")

    done = 0
    for index, case in enumerate(todo, 1):
        _show_mark_case(body, case, f"{index}/{len(todo)}")
        answers = _mark_one(body, case)
        if answers is None:
            break
        if not answers:
            continue
        entries[case["id"]] = answers
        done += 1

    _write(MARKS_PATH, _bound_marks(body, entries))
    _warn_if_unanimous(entries, cases)

    left = len([c for c in cases if c.get("id") not in entries])
    print(f"\nSaved {done} this round. {len(entries)} marked, {left} left.")
    print("Run it again when you have a minute." if left else "That is the whole key.")
    return 0


def _warn_if_unanimous(entries: dict[str, Any], cases: list[dict[str, Any]]) -> None:
    """Say so when a column that COULD have varied did not.

    Per column, and never about the OUTPUT column on a corpus that cannot vary
    it: warning about an answer the ruling fixed punishes the marker for being
    right. v2 did that, and then told them to delete the key.
    """
    if len(entries) < 8:
        return
    askable = {c["id"] for c in cases if c.get("asks_output")}
    columns = [("goal", set(entries)), ("output", askable & set(entries))]
    for column, scope in columns:
        if len(scope) < 8:
            continue
        answers = {entries[k][column] for k in scope}
        if len(answers) == 1:
            print(f"\n  Every case that could vary was marked {answers.pop()!r} on {column}.")
            print("  A column that answers one way throughout cannot fail a producer")
            print("  that never abstains. Look at whether the cases differ in what")
            print("  that question turns on. The marks already given are not the problem.")


def report() -> int:
    body = _load(CASES_PATH)
    cases = body.get("cases") if isinstance(body.get("cases"), list) else []
    if not cases:
        print("No cases built yet.")
        return 1
    entries = _marks(_load(MARKS_PATH))
    live = {c["id"] for c in cases}
    orphans = [k for k in entries if k not in live]
    print(f"{len(entries) - len(orphans)} of {len(cases)} marked.")
    if orphans:
        print(f"  {len(orphans)} marks name sessions no longer in the case set.")
    columns = ("goal", "lines") if is_intent_packet(body) else ("goal", "output")
    for column in columns:
        answers = [
            answer
            for k, v in entries.items()
            if k in live
            for name, answer in v.items()
            if name == column or (column == "lines" and name.startswith("line_"))
        ]
        judge = answers.count("judge")
        print(f"  {column:7} {judge} judge, {len(answers) - judge} abstain")
    _warn_if_unanimous({k: v for k, v in entries.items() if k in live}, cases)
    return 0


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911 - one exit per mode
    parser = argparse.ArgumentParser(description="Collect the abstention answer key.")
    parser.add_argument("--build", action="store_true", help="assemble cases from the live board")
    parser.add_argument("--port", type=int, default=4553, help="the dashboard port to read")
    parser.add_argument("--force", action="store_true", help="rebuild even if it orphans marks")
    parser.add_argument("--report", action="store_true", help="how far through the key you are")
    parser.add_argument("--reset", action="store_true", help="discard the marks and start over")
    parser.add_argument("--freeze", metavar="SPEC", help="freeze a format 5 packet from a spec")
    parser.add_argument(
        "--store-home", default=STORE_HOME, help="where the dashboard's history and ends live"
    )
    args = parser.parse_args(argv)
    if args.freeze:
        return freeze(args.port, args.freeze, force=args.force, store_home=args.store_home)
    if args.build and args.reset:
        print("--build and --reset together are ambiguous. Run them one at a time.")
        return 2
    if args.reset:
        if _ledger_refusal():
            return 1
        if os.path.exists(MARKS_PATH):
            os.remove(MARKS_PATH)
            print(f"Discarded {MARKS_PATH}. The cases are untouched.")
        else:
            print("No marks to discard.")
        return 0
    if args.build:
        return build(args.port, force=args.force)
    if args.report:
        return report()
    return mark()


if __name__ == "__main__":
    raise SystemExit(main())
