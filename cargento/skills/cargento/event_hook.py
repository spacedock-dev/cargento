#!/usr/bin/env python3
"""Forward one command-hook lifecycle event to a running Cargento.

Serves every harness whose hooks are *hook-shaped*: a fresh process per event,
one JSON payload on stdin, a `hook_event_name` naming what happened. Claude Code
and Codex both are, and Codex's `hooks.json` turned out to accept the same schema
as Claude's `settings.json` hooks, PascalCase event names included. Antigravity is
not: its status line pushes a state snapshot rather than an event, so it has its
own adapter in `statusline_hook.py`.

Separate from `notify_hook.py` on purpose. That script forwards a needs-input
notification to `/api/notify`, which is unauthenticated and sets one harness's
side state; this one posts general lifecycle events to `/api/events/<harness>`,
which requires this run's capability because a forged `session_ended` could
suppress a permission alert and a looped `turn_started` could mask a blocked
session. Different power, different door. The transport guards are shared, so a
proxy or redirect fix lands in one place.

Usage, with the harness first and an optional port second:

    python3 <skill-dir>/event_hook.py claude       # macOS, Linux, WSL, Git Bash
    python  <skill-dir>\\event_hook.py codex 9999  # Windows, non-default port

The harness is an argument rather than sniffed from the payload. Two harnesses
send the same field names, so a payload cannot say which one it came from, and
guessing would post one harness's events to the other's route.

## What it sends, and what it refuses to send

Only the nine allowlisted envelope fields, built field by field from the native
payload. The prompt, the tool name, the tool input and output, and every other
native field are dropped here rather than at the server, so they are never put
on a socket at all.

`Notification` is deliberately **not** mapped. A generic or actionable Claude
notification stays standing hook state under today's precedence via
`notify_hook.py`, because Claude Code can emit an input-waiting notification for
a session that then carries on running. Promoting it to an authoritative
permission overlay would make that transient state hard to clear.
`PermissionRequest` is different: it is explicit, so it maps to
`input_requested` and is cleared only by positive evidence.

`PreCompact` is not mapped either. Suppressing collection during a rewrite window
needs a server-side rewrite-in-progress state that does not exist yet; without it
the honest thing is to reconcile after the fact, which is what `PostCompact`
does.

Always exits 0. A hook that fails must never disturb the agent it reports on, and
"the dashboard is not running" is an ordinary state rather than an error.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from typing import Any

# The envelope version this adapter writes. An adapter lives in user-owned
# configuration and is not upgraded when Cargento is, so a server may see this
# value long after the server itself moved on; it answers `event-incompatible`
# rather than ignoring the event.
ENVELOPE_VERSION = 1

DEFAULT_PORT = 4553
MAX_PAYLOAD_BYTES = 1 << 20

# Native hook name to the normalized vocabulary, per harness. A name absent from
# a harness's table is not forwarded: the table is the whole of what this adapter
# claims to understand for that harness, and the server would refuse an unknown
# name anyway.
CLAUDE_EVENTS = {
    "SessionStart": "session_started",
    "SessionEnd": "session_ended",
    "UserPromptSubmit": "turn_started",
    "Stop": "turn_stopped",
    "PermissionRequest": "input_requested",
    "PostToolUse": "store_changed",
    "SubagentStart": "subagent_started",
    "SubagentStop": "subagent_stopped",
    "TaskCompleted": "tasks_changed",
    "PostCompact": "reconcile_required",
}

# Codex. Measured from a real `codex exec` turn rather than read off a page: the
# five names below all fired, once each, in the order
# UserPromptSubmit -> PreToolUse -> PostToolUse -> Stop with SessionStart outside
# the turn. `PreToolUse` is deliberately absent even though it fires: it means a
# tool is about to run, which `PostToolUse` reports better once the store has
# actually changed, and forwarding both would double every tool call for no gain.
#
# Codex documents subagent and permission hooks as well, and its config records
# `subagent_start`, `subagent_stop` and `pre_tool_use` state keys. They are absent
# here because the captured turn used no subagent and needed no permission, so
# their payload shape is unmeasured. They go in when a capture shows them.
CODEX_EVENTS = {
    "SessionStart": "session_started",
    "UserPromptSubmit": "turn_started",
    "Stop": "turn_stopped",
    "PostToolUse": "store_changed",
    "PostCompact": "reconcile_required",
}

EVENTS_BY_HARNESS = {
    "claude": CLAUDE_EVENTS,
    "codex": CODEX_EVENTS,
}


def _shared() -> Any:
    """The transport guards from `notify_hook`, which ships beside this file.

    Imported rather than copied so the loopback check, the proxy suppression and
    the redirect refusal have one implementation. Returns None if it cannot be
    reached, and the caller then does nothing at all.
    """
    with contextlib.suppress(Exception):
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import notify_hook  # noqa: PLC0415 — resolved relative to this file at runtime

        return notify_hook
    return None


def state_file(port: int) -> str:
    """Where the serving process published this run's capability."""
    home = os.environ.get("CARGENTO_HOME") or os.path.join(os.path.expanduser("~"), ".cargento")
    return os.path.join(home, f"cargento-{port}.json")


def capability(port: int, harness: str) -> str | None:
    """This run's token for `harness`, or None if there is nothing to read.

    None is an ordinary answer: no dashboard running, an older dashboard that
    publishes no capabilities, or one started with --no-events. In every case
    this adapter simply does not post, which costs the agent one file read.
    """
    try:
        with open(state_file(port), "rb") as handle:
            data = json.loads(handle.read(65_536) or b"null")
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    tokens = data.get("capabilities")
    if not isinstance(tokens, dict):
        return None
    token = tokens.get(harness)
    return token if isinstance(token, str) and token else None


def envelope(payload: dict[str, Any], harness: str = "claude") -> dict[str, Any] | None:
    """Build the allowlisted envelope, or None if this hook is not forwarded.

    Built field by field from an allowlist rather than by deleting known-bad keys
    from a copy. A native payload that grows a field would otherwise start
    carrying it, and the field most likely to be added to an agent hook is the
    one carrying the user's text. Codex's payloads carry `prompt`, `tool_input`,
    `tool_response` and `last_assistant_message`, all of which this drops.
    """
    names = EVENTS_BY_HARNESS.get(harness)
    if names is None:
        return None
    native = payload.get("hook_event_name")
    name = names.get(native) if isinstance(native, str) else None
    if name is None:
        return None
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    event: dict[str, Any] = {
        "v": ENVELOPE_VERSION,
        "event": name,
        "session_id": session_id.strip(),
    }
    for source, field in (
        ("cwd", "cwd"),
        ("transcript_path", "transcript_path"),
        ("agent_id", "subagent_id"),
    ):
        value = payload.get(source)
        if isinstance(value, str) and value.strip():
            event[field] = value.strip()
    return event


def read_event(raw: bytes, harness: str = "claude") -> dict[str, Any] | None:
    """Parse stdin into an envelope, or None if there is nothing to forward."""
    try:
        payload = json.loads(raw or b"{}")
    except (ValueError, RecursionError):
        # RecursionError as well as ValueError: deeply nested JSON blows the
        # decoder's stack, and an escaping exception is the one thing this script
        # promises never to do.
        return None
    if not isinstance(payload, dict):
        return None
    return envelope(payload, harness)


def main(argv: list[str]) -> int:
    # An unknown harness needs no check here: `envelope` has no table for it and
    # returns None, so the guard below already covers it. A second check would be
    # a branch no test could distinguish from its absence.
    harness = argv[1] if len(argv) > 1 else "claude"
    port = DEFAULT_PORT
    if len(argv) > 2:
        with contextlib.suppress(ValueError):
            port = int(argv[2])
    try:
        raw = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES)
    except (OSError, ValueError, AttributeError):
        return 0  # no stdin: run interactively, or a harness that closes it
    # Checked in order, cheapest first: parse before reading a file, and read the
    # file before importing anything. Doing nothing is the common case, because
    # most sessions run with no dashboard listening at all.
    event = read_event(raw, harness)
    if event is None:
        return 0
    token = capability(port, harness)
    if token is None:
        return 0
    shared = _shared()
    if shared is None:
        return 0
    # Last-resort guard, as in notify_hook: forward() handles every failure it
    # expects, and this catches the ones it does not, because a raising hook
    # surfaces as an error inside the very session it is reporting on.
    with contextlib.suppress(Exception):
        shared.forward(
            f"http://127.0.0.1:{port}/api/events/{harness}",
            json.dumps(event, separators=(",", ":")).encode(),
            headers={"X-Cargento-Capability": token},
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
