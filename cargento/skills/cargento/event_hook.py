#!/usr/bin/env python3
"""Forward one Claude Code lifecycle hook to a running Cargento as an event.

Separate from `notify_hook.py` on purpose. That script forwards a needs-input
notification to `/api/notify`, which is unauthenticated and sets one harness's
side state; this one posts general lifecycle events to `/api/events/claude`,
which requires this run's capability because a forged `session_ended` could
suppress a permission alert and a looped `turn_started` could mask a blocked
session. Different power, different door. The transport guards are shared, so a
proxy or redirect fix lands in one place.

Usage in ~/.claude/settings.json:

    python3 <skill-dir>/event_hook.py            # macOS, Linux, WSL, Git Bash
    python  <skill-dir>\\event_hook.py           # Windows

Pass a port as the first argument to target a non-default instance.

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

# Native Claude hook name to the normalized vocabulary. A name absent here is
# not forwarded: this table is the whole of what this adapter claims to
# understand, and the server would refuse an unknown name anyway.
EVENT_NAMES = {
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


def envelope(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build the allowlisted envelope, or None if this hook is not forwarded.

    Built field by field from an allowlist rather than by deleting known-bad keys
    from a copy. A native payload that grows a field would otherwise start
    carrying it, and the field most likely to be added to an agent hook is the
    one carrying the user's text.
    """
    native = payload.get("hook_event_name")
    name = EVENT_NAMES.get(native) if isinstance(native, str) else None
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


def read_event(raw: bytes) -> dict[str, Any] | None:
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
    return envelope(payload)


def main(argv: list[str]) -> int:
    port = DEFAULT_PORT
    if len(argv) > 1:
        with contextlib.suppress(ValueError):
            port = int(argv[1])
    try:
        raw = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES)
    except (OSError, ValueError, AttributeError):
        return 0  # no stdin: run interactively, or a harness that closes it
    # Checked in order, cheapest first: parse before reading a file, and read the
    # file before importing anything. Doing nothing is the common case, because
    # most sessions run with no dashboard listening at all.
    event = read_event(raw)
    if event is None:
        return 0
    token = capability(port, "claude")
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
            f"http://127.0.0.1:{port}/api/events/claude",
            json.dumps(event, separators=(",", ":")).encode(),
            headers={"X-Cargento-Capability": token},
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
