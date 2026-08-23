#!/usr/bin/env python3
"""Record harness lifecycle events as shape, to answer the adapter-semantics gate.

Phase 2 of the event-driven plan may not publish an overlay transition without
fixtures proving what an event *means*, how many of it arrive per turn, and in
what order. None of that can be looked up: it has to be observed from real
sessions. This is the observer.

Two modes, with the harness named first on the record path exactly as
`event_hook.py` takes it:

    capture_hook.py claude          read one hook payload on stdin, append a line
    capture_hook.py gemini
    --report                        summarise every capture, per harness
    --install --harness gemini      write a merged settings file, never over yours

The harness is an argument rather than sniffed from the payload, for the same
reason `event_hook.py` takes one: Claude Code and Gemini CLI send the same field
names, so a payload cannot say which harness produced it. What differs per
harness is the event vocabulary, the settings file, and the pair of names that
bounds one turn.

## What it records, and what it refuses to

Shape, and one enum. Each line carries the event name, the session prefix, a
salted digest of the working directory, the sorted top-level keys the payload
carried, the tool name where there is one, how long this hook itself took, and
-- on `Notification` only -- the `notification_type` value. That one field is a
closed vocabulary the harness picks from rather than text anyone wrote, which
puts it in the same class as the tool name: see `shape_of`.

It never records a prompt, a tool argument, a tool result, a message, a file
path, or a transcript path. Those are the fields the plan's allowlist exists to
exclude, and a research tool that captured them would be a worse leak than the
thing it is researching, because it writes to disk and accumulates.

The working directory is digested rather than dropped because telling two
concurrent sessions apart is the whole point of an ordering study, and a digest
does that without recording where anyone works. The salt is per capture file, so
a digest cannot be compared against a rainbow table of common paths.

## Why it records its own duration

The same gate requires each synchronous shim to fit one end-to-end p99 hook
budget. A hook that measures itself gives that number directly, per OS, from real
sessions rather than from a benchmark loop.

## Why it cannot disturb a session

Claude Code runs hooks synchronously for some events, so a slow or failing hook
is felt by the user. This exits 0 on every path, writes with a single append, and
never imports anything outside the standard library. If the capture directory is
unwritable it gives up silently, exactly as `notify_hook.py` does.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, NamedTuple

# 2 adds the `harness` field. Version 1 lines stay readable: they were all Claude
# captures, because Claude was the only harness this script served, so a line
# without a harness is read as one.
FORMAT_VERSION = 2
LEGACY_HARNESS = "claude"
DEFAULT_DIR = Path.home() / ".cargento" / "captures"
MAX_PAYLOAD_BYTES = 1_000_000
# Tool names are recorded because cardinality per turn is meaningless without
# knowing whether ten PreToolUse events were ten different tools or one in a
# loop. A name is not an argument and not a result.
TOOL_NAME_KEYS = ("tool_name", "toolName", "tool")
SESSION_KEYS = ("session_id", "sessionId")
# Never recorded, under any spelling. Listed so the refusal is auditable rather
# than implied by the absence of code.
NEVER_RECORD = (
    "prompt",
    "message",
    "tool_input",
    "toolInput",
    "tool_response",
    "toolResponse",
    "content",
    "transcript_path",
    "transcriptPath",
    "cwd",
)


def capture_dir() -> Path:
    return Path(os.environ.get("CARGENTO_CAPTURE_DIR") or DEFAULT_DIR)


def _slug(harness: str) -> str:
    """A harness name reduced to what is safe in a filename.

    The harness reaches this script from a hook command, which is user-owned
    configuration, so it is not trusted to be a bare word. Anything outside the
    allowed set becomes a hyphen rather than a path separator or a traversal.
    """
    kept = "".join(char if char.isalnum() or char in "-_" else "-" for char in harness[:40])
    return kept.strip("-") or "unknown"


def salt_for(directory: Path) -> str:
    """A per-capture-file salt, created once and reused.

    Without a salt a digest of a working directory is guessable: the set of
    plausible project paths on one machine is small. With one, the digest tells
    sessions apart and nothing else.
    """
    path = directory / "salt"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    salt = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(salt, encoding="utf-8")
    except OSError:
        return ""  # unwritable: fall back to an unsalted, still-truncated digest
    return salt


def digest(value: str, salt: str) -> str:
    if not value:
        return ""
    return hashlib.sha256((salt + value).encode("utf-8", "replace")).hexdigest()[:12]


def shape_of(
    payload: dict[str, Any], *, event: str, salt: str, elapsed_ms: float, harness: str = "claude"
) -> dict[str, Any]:
    """One capture line: what happened, not what was said."""
    session = ""
    for key in SESSION_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate:
            # The eight-character prefix, which is what the collectors key on.
            # Recording the full identifier would add nothing an ordering study
            # can use and would make the capture worth protecting.
            session = candidate[:8]
            break
    tool = ""
    for key in TOOL_NAME_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate:
            tool = candidate[:60]
            break
    # The one payload VALUE this recorder keeps, and only on `Notification`.
    #
    # It is a closed vocabulary the harness picks from, never text a person or a
    # model wrote, so it is the same class of fact as `tool` above: a name, not an
    # argument. And it is the field every classification in `notifications.py`
    # branches on, so a capture that omitted it could prove a `Notification`
    # arrived and nothing about whether the adapter reads it correctly -- which is
    # the entire question DRC-4135 was filed to answer.
    #
    # `message` is deliberately NOT recorded beside it. That one is prose, it is
    # what the notification actually says, and on a permission prompt it names the
    # command being approved.
    notification_type = ""
    if event == "Notification":
        candidate = payload.get("notification_type")
        if isinstance(candidate, str):
            notification_type = candidate[:60]
    cwd = payload.get("cwd")
    return {
        "v": FORMAT_VERSION,
        "at": round(time.time(), 3),
        # Recorded rather than inferred from the filename, so two harnesses
        # captured on one machine stay separable after the files are merged, and
        # so `--report` can pick each one's turn boundaries without being told.
        "harness": harness[:40],
        "event": event[:60],
        "session": session,
        "project": digest(cwd, salt) if isinstance(cwd, str) else "",
        # Sorted, so a shape can be compared across runs. Keys only: this is the
        # record of which fields a harness sends, which is exactly what an
        # adapter has to be written against.
        "keys": sorted(k[:60] for k in payload if isinstance(k, str)),
        "tool": tool,
        # Absent rather than empty off the Notification path, so a reader cannot
        # mistake "this event carries no type" for "the type was blank".
        **({"notification_type": notification_type} if event == "Notification" else {}),
        "hook_ms": round(elapsed_ms, 3),
        "os": os.name,
    }


def record(argv: list[str], *, started: float) -> int:
    """Append one event. Every failure path returns 0.

    Invoked as `capture_hook.py <harness> [<EventName>]`, the harness first, the
    same order `event_hook.py` uses. The event name is a fallback only: every
    harness captured so far names its own event in the payload.
    """
    harness = argv[1] if len(argv) > 1 else LEGACY_HARNESS
    event = argv[2] if len(argv) > 2 else ""
    try:
        raw = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES)
    except (OSError, ValueError, AttributeError):
        return 0  # no stdin: run interactively, or a harness that closes it
    try:
        payload = json.loads(raw or b"{}")
    except (ValueError, RecursionError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    # The harness names its own event; argv is the fallback for one that does not.
    for key in ("hook_event_name", "hookEventName"):
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate:
            event = candidate
            break
    if not event:
        event = "unknown"

    directory = capture_dir()
    salt = salt_for(directory)
    elapsed = (time.perf_counter() - started) * 1000
    line = shape_of(payload, event=event, salt=salt, elapsed_ms=elapsed, harness=harness)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Per harness as well as per day: one file per harness keeps a capture
        # reviewable on its own before it is vendored into `docs/captures/`.
        target = directory / f"{_slug(harness)}-{time.strftime('%Y%m%d')}.jsonl"
        # One append, opened and closed. Concurrent hooks are separate processes,
        # and an append under the platform buffer size does not interleave.
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, separators=(",", ":")) + "\n")
    except OSError:
        return 0  # unwritable capture directory is not the session's problem
    return 0


def load_captures(directory: Path) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    try:
        files = sorted(directory.glob("*.jsonl"))
    except OSError:
        return lines
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
            except ValueError:
                continue  # a torn line from a killed hook is not fatal
            if isinstance(entry, dict):
                lines.append(entry)
    return lines


def turns_for(entries: list[dict[str, Any]], *, start: str, end: str) -> list[list[str]]:
    """Event names between a prompt and its stop, per session, in arrival order.

    Grouped per session because two concurrent sessions interleave in one capture
    file, and a global ordering would invent transitions neither one made.
    """
    per_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in sorted(entries, key=lambda e: e.get("at") or 0):
        per_session[str(entry.get("session") or "")].append(entry)
    turns: list[list[str]] = []
    for events in per_session.values():
        current: list[str] | None = None
        for entry in events:
            name = str(entry.get("event") or "")
            if name == start:
                if current:
                    turns.append(current)  # a prompt with no stop still tells us something
                current = [name]
                continue
            if current is None:
                continue
            current.append(name)
            if name == end:
                turns.append(current)
                current = None
        if current:
            turns.append(current)
    return turns


def turn_report(entries: list[dict[str, Any]]) -> list[str]:
    """Cardinality and ordering per harness, each against its own turn boundary.

    Split per harness because the pair of names that bounds a turn is part of a
    harness's vocabulary. Measuring every harness against Claude's pair is how a
    Gemini capture of four complete turns reported "no complete turn".
    """
    by_harness: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        name = entry.get("harness")
        by_harness[str(name) if isinstance(name, str) and name else LEGACY_HARNESS].append(entry)

    lines: list[str] = []
    for harness in sorted(by_harness):
        start, end = harness_for(harness).turn
        turns = turns_for(by_harness[harness], start=start, end=end)
        if not turns:
            lines.append(f"No complete {start}-to-{end} turn captured yet for {harness}.")
            continue
        lengths = [len(turn) for turn in turns]
        lines.append(f"Complete turns observed for {harness}: {len(turns)}")
        lines.append(
            f"  events per turn: min {min(lengths)}, median "
            f"{statistics.median(lengths)}, max {max(lengths)}"
        )
        lines.append("  most common orderings:")
        shapes = Counter(" -> ".join(turn) for turn in turns)
        lines.extend(f"    {count:4}x {shape}" for shape, count in shapes.most_common(5))
    return lines


def report(directory: Path) -> str:
    entries = load_captures(directory)
    if not entries:
        return (
            f"No captures in {directory}.\n"
            "Install the hook (see --install) and use the harness normally; "
            "come back once a few sessions have run."
        )
    out: list[str] = [f"{len(entries)} events from {directory}", ""]

    counts = Counter(str(e.get("event") or "") for e in entries)
    out.append("Event cardinality, total:")
    for name, count in counts.most_common():
        out.append(f"  {name:24} {count}")
    out.append("")

    keys_by_event: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        keys = entry.get("keys")
        if isinstance(keys, list):
            keys_by_event[str(entry.get("event") or "")].update(str(k) for k in keys)
    out.append("Payload shape per event, which is what an adapter is written against:")
    out.extend(
        f"  {name:24} {', '.join(sorted(keys_by_event[name]))}" for name in sorted(keys_by_event)
    )
    out.append("")

    out.extend(turn_report(entries))
    out.append("")

    costs = sorted(
        float(e["hook_ms"]) for e in entries if isinstance(e.get("hook_ms"), (int, float))
    )
    if costs:

        def pct(fraction: float) -> float:
            return costs[min(len(costs) - 1, int(len(costs) * fraction))]

        by_os = Counter(str(e.get("os") or "?") for e in entries)
        platforms = ", ".join(f"{k}={v}" for k, v in by_os.items())
        out.append(f"Hook self-cost, the p99 budget the gate asks for ({platforms}):")
        out.append(
            f"  p50 {pct(0.50):.2f} ms   p95 {pct(0.95):.2f} ms   p99 {pct(0.99):.2f} ms   "
            f"max {costs[-1]:.2f} ms"
        )
        out.append("  This is the hook's own work only. It excludes interpreter startup,")
        out.append("  which scripts/bench_collect.py measures separately and which dominates.")
    return "\n".join(out)


CAPTURE_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "TaskCompleted",
    "PreCompact",
    "PostCompact",
    "Stop",
    "SessionEnd",
)

# Gemini CLI's whole documented vocabulary, all eleven, because the point of a
# capture is to find out which of them fire and how often. Its names are its own:
# `BeforeAgent` and `AfterAgent` bound a turn where Claude uses `UserPromptSubmit`
# and `Stop`.
GEMINI_CAPTURE_EVENTS = (
    "SessionStart",
    "BeforeAgent",
    "BeforeModel",
    "BeforeToolSelection",
    "AfterModel",
    "BeforeTool",
    "AfterTool",
    "Notification",
    "PreCompress",
    "AfterAgent",
    "SessionEnd",
)


class Harness(NamedTuple):
    """What differs per harness when capturing and reporting."""

    events: tuple[str, ...]
    # The pair that bounds one turn. Ordering and cardinality are reported between
    # them, so a wrong pair reports "no complete turn" rather than a wrong number.
    turn: tuple[str, str]
    # The user-level settings file whose `hooks` object the capture merges into.
    # Gemini's home is the *parent* of its `.gemini` directory, matching what
    # `cargento_runtime/config.py` does with the same variable.
    settings_env: str
    settings_dir: tuple[str, ...]


HARNESSES = {
    "claude": Harness(
        events=CAPTURE_EVENTS,
        turn=("UserPromptSubmit", "Stop"),
        settings_env="CLAUDE_CONFIG_DIR",
        settings_dir=(),
    ),
    "gemini": Harness(
        events=GEMINI_CAPTURE_EVENTS,
        turn=("BeforeAgent", "AfterAgent"),
        settings_env="GEMINI_CLI_HOME",
        settings_dir=(".gemini",),
    ),
}
DEFAULT_HOME = {"claude": ".claude", "gemini": ".gemini"}


def harness_for(name: str) -> Harness:
    return HARNESSES.get(name, HARNESSES["claude"])


def settings_path(harness: str = "claude") -> Path:
    """Where `harness` keeps its settings, honouring the documented override."""
    spec = harness_for(harness)
    base = os.environ.get(spec.settings_env)
    root = Path(base).joinpath(*spec.settings_dir) if base else Path.home() / DEFAULT_HOME[harness]
    return root / "settings.json"


def hook_command(harness: str = "claude") -> str:
    return f'python3 "{Path(__file__).resolve()}" {harness}'


def merge_hooks(
    settings: dict[str, Any], command: str, events: tuple[str, ...] = CAPTURE_EVENTS
) -> tuple[dict[str, Any], dict[str, str]]:
    """Add the capture hook to `events`, leaving every existing hook alone.

    Additive per event: a new matcher group is appended rather than merged into
    an existing one. Claude Code runs every group whose matcher matches, so
    appending cannot disturb a hook that is already there, while editing a group
    in place could. `matcher: ""` matches everything, which is the shape the
    existing entries use.

    Idempotent: an event that already runs this exact command is left untouched,
    so running this twice does not double-record.

    Returns the merged settings and what happened per event, so the caller can
    report it rather than claiming success blindly.
    """
    merged = json.loads(json.dumps(settings))  # deep copy: never mutate the input
    hooks = merged.get("hooks")
    if not isinstance(hooks, dict):
        # Absent is normal. A non-object here is a settings file Claude Code
        # would reject anyway, so replacing it is the honest move, but say so.
        hooks = {}
    merged["hooks"] = hooks
    actions: dict[str, str] = {}
    for event in events:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            groups = [] if groups is None else [groups]
        already = any(
            isinstance(group, dict)
            and any(
                isinstance(entry, dict) and entry.get("command") == command
                for entry in (group.get("hooks") or [])
                if isinstance(group.get("hooks"), list)
            )
            for group in groups
        )
        if already:
            actions[event] = "already present"
            hooks[event] = groups
            continue
        groups = [*groups, {"matcher": "", "hooks": [{"type": "command", "command": command}]}]
        hooks[event] = groups
        actions[event] = "added" if len(groups) > 1 else "added (first hook for this event)"
    return merged, actions


def install(source: Path | None = None, harness: str = "claude") -> str:
    """Write a merged settings file beside the real one, and never over it.

    A merged copy rather than an edit in place, because a settings file is the
    user's and a research tool has no business rewriting it. The caller reads the
    result, and swaps it in if they agree.

    Both harnesses captured so far take the same `hooks` object in the same
    `settings.json` shape, so only the event list, the path and the harness
    argument differ.
    """
    events = harness_for(harness).events
    settings_file = source or settings_path(harness)
    output = settings_file.with_name("settings_with_hooks.json")
    command = hook_command(harness)

    existing: dict[str, Any] = {}
    note = ""
    if settings_file.exists():
        try:
            loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return (
                f"Could not read {settings_file}: {exc}\n"
                "Nothing was written. Fix the file, or pass --settings with another path."
            )
        if isinstance(loaded, dict):
            existing = loaded
        else:
            return (
                f"{settings_file} does not contain a JSON object, so there is nothing to "
                "merge into. Nothing was written."
            )
    else:
        note = f"No settings file at {settings_file}, so this is a fresh one.\n"

    merged, actions = merge_hooks(existing, command, events)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return f"Could not write {output}: {exc}"

    added = [e for e, a in actions.items() if a.startswith("added")]
    present = [e for e, a in actions.items() if a == "already present"]
    kept = sorted(k for k in existing if k != "hooks")
    untouched = sorted(
        event
        for event in (existing.get("hooks") or {})
        if isinstance(existing.get("hooks"), dict) and event not in events
    )

    lines = [note + f"Wrote {output}", ""]
    lines.append(f"Capture hook added to {len(added)} event(s):")
    lines.append("  " + ", ".join(added) if added else "  none")
    if present:
        lines.append(f"Already had it, left alone: {', '.join(present)}")
    lines.append("")
    lines.append("Your existing configuration is carried over untouched:")
    lines.append(f"  {len(kept)} top-level key(s) kept: {', '.join(kept) or 'none'}")
    existing_hooks = existing.get("hooks")
    if isinstance(existing_hooks, dict) and existing_hooks:
        lines.append(
            f"  {len(existing_hooks)} event(s) already had hooks; the capture hook is appended "
            "as an extra group rather than replacing them"
        )
    if untouched:
        lines.append(f"  events with hooks that this does not touch: {', '.join(untouched)}")
    lines += [
        "",
        "Read it, and if it looks right:",
        f"  cp {settings_file} {settings_file.with_suffix('.json.bak')}",
        f"  mv {output} {settings_file}",
        "",
        f"Captures land in {capture_dir()} and record shape only: no prompts, tool",
        "arguments, tool output, or paths. To stop, remove the appended groups.",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    started = time.perf_counter()
    # Parsed only when asked for, so the record path stays a straight line: a
    # hook runs on the user's critical path and argparse is not free.
    if len(argv) > 1 and argv[1] in {"--report", "--install", "--help", "-h"}:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--report", action="store_true", help="summarise captures")
        parser.add_argument(
            "--install",
            action="store_true",
            help="write settings_with_hooks.json beside your settings, merged",
        )
        parser.add_argument("--settings", default=None, help="settings.json to merge into")
        parser.add_argument("--dir", default=None, help="capture directory")
        parser.add_argument(
            "--harness",
            default="claude",
            choices=sorted(HARNESSES),
            help="which harness to install the capture hook for",
        )
        args = parser.parse_args(argv[1:])
        directory = Path(args.dir) if args.dir else capture_dir()
        if args.install:
            print(install(Path(args.settings) if args.settings else None, args.harness))
        else:
            print(report(directory))
        return 0
    return record(argv, started=started)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
