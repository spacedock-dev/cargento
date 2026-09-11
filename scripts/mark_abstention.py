#!/usr/bin/env python3
"""The answer key for "does a reading know when to say I can't tell".

DEC-17 gates the `Ask for a reading` control on a check nobody can run yet,
because the check needs expected answers written down BEFORE the producer is
ever pointed at them. A mark written after seeing an output is agreement, not a
mark. This is the thing that collects them.

    mark_abstention.py --build      assemble cases from the live board
    mark_abstention.py              mark the unmarked ones, one call each
    mark_abstention.py --report     progress, and the spread of what is marked

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
is only ever put to the model on a harness that publishes a demonstrated work
result, which today is Pi alone. Asking it about a Claude session is asking the
marker to transcribe a constant, and half of v2's prompts did exactly that. This
reads `reading.WORK_EVIDENCE_HARNESSES` to know which cases to skip. That is the
producer's **contract**, not its output, and the two are not the same thing: a
tool that knows which questions are asked cannot thereby agree with an answer.

**A mark is keyed on identity, never on position.** v2 hashed the row's index in
the board's session list. The board reorders on every state change, so a rebuild
silently re-attached answers to different sessions -- measured, four of six. The
key is now a hash of `(harness, sid)`, which is stable, and still carries no
session identity into the file that gets committed.

## What a scorer has to do, written down so it is not discovered later

The two constraints below live in this file, not in the annotation store. A
producer handed a session with no stored revision refuses it outright with
`nothing-typed`, before any evidence is read. So a scorer must, per case, write
these two lines as a revision for that `(harness, sid)`, call the producer, and
clear them again. It must not leave them behind: they are a yardstick, not the
reader's words, and the Intent log is the reader's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

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

# Cases per (harness, end shape), so the corpus spreads instead of filling up
# with whichever harness ran most today. v2 had this constant and no bucketing,
# which is how a six case corpus came to be six Claude sessions in one state.
PER_BUCKET = 3


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
    root = os.path.expanduser("~/.claude/projects")
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

    `citable` is the count a reading can build a claim on: rule 3 needs a
    resolvable citation, and an entry with no type, source or summary resolves
    to nothing. `work_results` is the subset that demonstrates work rather than
    describing a request, which is what the Expected Output constraint needs.
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
    facts = ((body or {}).get("semantic") or {}).get("facts") or []
    mine = [f for f in facts if str(f.get("sid") or "") in {sid, ""}]
    citable = [f for f in mine if f.get("type") and f.get("summary")]
    work = [f for f in citable if str(f.get("type") or "") in _reading().WORK_EVIDENCE_TYPES]
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
                # The Expected Output constraint is only ever put to the model
                # where a demonstrated work result exists. Elsewhere the answer
                # is fixed by the ruling and asking for it wastes the marker.
                "asks_output": harness in _reading().WORK_EVIDENCE_HARNESSES,
            }
        )

    cases = _bucket(cases)
    print(f"Fetching the evidence ledger for {len(cases)} sessions.")
    for case in cases:
        case.update(_ledger(port, {"project_key": case["project"], **case}))

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


def _write(path: str, body: dict[str, Any]) -> None:
    """Atomically, because this file is somebody's evening.

    v2 truncated in place: a Ctrl-C between `open` and `dump` left a zero length
    file and the next run died on it with no backup.
    """
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
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
        if isinstance(v, dict) and isinstance(v.get("goal"), str) and "output" in v
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


def mark() -> int:
    body = _load(CASES_PATH)
    cases = body.get("cases") if isinstance(body.get("cases"), list) else None
    if not cases:
        print(f"No cases at {CASES_PATH}. Run --build first.")
        return 1
    entries = _marks(_load(MARKS_PATH))

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
        _show(case, f"{index}/{len(todo)}")
        goal = _ask(_question(case))
        if goal is None:
            break
        if goal == "skip":
            continue
        if case.get("asks_output"):
            out = _ask(
                "\n  And could it say whether a checkable deliverable came out,\n"
                "  a diff, a test run, a file you can open?\n    [y/n/s/q] "
            )
            if out is None:
                break
            if out == "skip":
                continue
        else:
            # Not asked, and saying so is the point. The constraint is never put
            # to the model on a harness that publishes no work result, so the
            # answer is the ruling's rather than the marker's.
            out = "abstain"
            print("  The OUTPUT question is not asked here: this harness records no")
            print("  demonstrated work result, so the ruling already fixes the answer.")
        entries[case["id"]] = {"goal": goal, "output": out}
        done += 1

    _write(MARKS_PATH, {"v": 2, "marks": entries})
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
    for column in ("goal", "output"):
        judge = sum(1 for k, v in entries.items() if k in live and v[column] == "judge")
        held = sum(1 for k in entries if k in live)
        print(f"  {column:7} {judge} judge, {held - judge} abstain")
    _warn_if_unanimous({k: v for k, v in entries.items() if k in live}, cases)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect the abstention answer key.")
    parser.add_argument("--build", action="store_true", help="assemble cases from the live board")
    parser.add_argument("--port", type=int, default=4553, help="the dashboard port to read")
    parser.add_argument("--force", action="store_true", help="rebuild even if it orphans marks")
    parser.add_argument("--report", action="store_true", help="how far through the key you are")
    parser.add_argument("--reset", action="store_true", help="discard the marks and start over")
    args = parser.parse_args(argv)
    if args.build and args.reset:
        print("--build and --reset together are ambiguous. Run them one at a time.")
        return 2
    if args.reset:
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
