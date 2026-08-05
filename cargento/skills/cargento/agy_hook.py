#!/usr/bin/env python3
"""Forward one Antigravity lifecycle hook to a running Cargento.

Antigravity's third input contract, and the reason this is not folded into
`event_hook.py`. Three things differ from a Claude or Codex hook, and each one
would be a silent bug if assumed away:

1. **The payload is camelCase.** Antigravity encodes with protojson, so the id is
   `conversationId`, not `session_id`. An adapter reading `session_id` would find
   nothing and post nothing, successfully.
2. **A hook must print a JSON object on stdout.** Not a status line, not an empty
   string: a JSON object. `PostToolUse` and the flat events expect `{}`.
3. **`PreToolUse` output can gate the tool.** Its result may carry a `decision` of
   `allow`, `deny`, `ask` or `force_ask`. A reporting hook that emitted a
   malformed or opinionated object there could block the user's tool calls. This
   script therefore prints exactly `{}` and never anything else, on every path
   including every failure path.

## What is verified, and what is taken from the documentation

Verified by running `agy plugin validate` against a copy: Antigravity loads a
plugin's hooks from a **root `hooks.json`**, and it accepts the mixed schema the
guide describes, reporting `hooks: 5 processed`. `PreToolUse` and `PostToolUse`
are grouped under a `matcher`; `PreInvocation`, `PostInvocation` and `Stop` are
flat lists of handlers.

Taken from the guide embedded in the `agy` binary: the payload keys, that
`conversationId` is present on every hook, and the stdout contract. The hooks
could not be made to fire under `agy --print`, so cardinality and ordering are
**unmeasured**, and that is why the mapping below is as small as it is.

## Why so little is mapped

The design's rule for this harness is that its hooks are model, tool and
execution-loop hints, not asserted user-turn boundaries: `PreInvocation` may run
before each model call and one user turn may contain several invocations. Without
a capture proving cardinality, mapping `PreInvocation` to `turn_started` or
`Stop` to `turn_stopped` risks flapping a row mid-turn.

So this sends only `store_changed`, which claims nothing about what the agent is
doing and merely tells the coordinator the store probably moved. Antigravity's
Working and Idle state comes from the status line instead, where `agent_state`
*was* measured. The division is deliberate: hooks give freshness, the status line
gives state, and the hooks are the half that installs with the plugin.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from typing import Any

# Must match the server's accepted envelope range. See event_hook.py.
ENVELOPE_VERSION = 1

DEFAULT_PORT = 4553
MAX_PAYLOAD_BYTES = 1 << 20
HARNESS = "antigravity"

# Every hook whose arrival means the store probably moved. Deliberately not a
# state assertion: see the module docstring. `PreToolUse` and `PreInvocation` are
# absent because nothing has happened yet when they fire, and `Stop` is absent
# because its cardinality is unmeasured.
STORE_CHANGED_HOOKS = frozenset({"PostToolUse", "PostInvocation"})

# The one thing this script prints, on every path. See point 3 above.
EMPTY_RESULT = "{}"


def _shared() -> Any:
    """The transport guards from `notify_hook`, which ships beside this file."""
    with contextlib.suppress(Exception):
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import notify_hook  # noqa: PLC0415 — resolved relative to this file at runtime

        return notify_hook
    return None


def capability(port: int) -> str | None:
    """This run's Antigravity token, or None if there is nothing to read."""
    home = os.environ.get("CARGENTO_HOME") or os.path.join(os.path.expanduser("~"), ".cargento")
    try:
        with open(os.path.join(home, f"cargento-{port}.json"), "rb") as handle:
            data = json.loads(handle.read(65_536) or b"null")
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    tokens = data.get("capabilities")
    if not isinstance(tokens, dict):
        return None
    token = tokens.get(HARNESS)
    return token if isinstance(token, str) and token else None


def conversation_id(payload: dict[str, Any]) -> str | None:
    """The id the Antigravity collector keys on, from a camelCase payload.

    `conversationId` is documented as present on every hook payload. The
    environment variable is the fallback, because the `agy` binary sets
    `ANTIGRAVITY_CONVERSATION_ID` for hook processes and a payload that changed
    shape would otherwise take the adapter out entirely.

    The length check is the same one `statusline_hook.py` applies, and for the
    same measured reason: the id is the 36-character stem of a real
    `conversations/<id>.db`, and it is blank before a conversation exists.
    """
    for value in (payload.get("conversationId"), os.environ.get("ANTIGRAVITY_CONVERSATION_ID")):
        if isinstance(value, str) and len(value.strip()) == 36:
            return value.strip()
    return None


def envelope(hook: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """The allowlisted envelope for this hook, or None if it says nothing.

    Built field by field. Antigravity's payloads carry `transcriptPath`,
    `artifactDirectoryPath` and `workspacePaths`; none of them is in the server's
    allowlist under those names, so none is forwarded.
    """
    if hook not in STORE_CHANGED_HOOKS:
        return None
    sid = conversation_id(payload)
    if sid is None:
        return None
    event: dict[str, Any] = {
        "v": ENVELOPE_VERSION,
        "event": "store_changed",
        "session_id": sid,
    }
    paths = payload.get("workspacePaths")
    if isinstance(paths, list) and paths and isinstance(paths[0], str) and paths[0].strip():
        # The server treats cwd as a matching hint and never echoes it.
        event["cwd"] = paths[0].strip()
    return event


def main(argv: list[str]) -> int:
    hook = argv[1] if len(argv) > 1 else ""
    port = DEFAULT_PORT
    if len(argv) > 2:
        with contextlib.suppress(ValueError):
            port = int(argv[2])
    payload: Any = {}
    try:
        payload = json.loads(sys.stdin.buffer.read(MAX_PAYLOAD_BYTES) or b"{}")
    except (OSError, ValueError, AttributeError, RecursionError):
        payload = {}
    if isinstance(payload, dict):
        with contextlib.suppress(Exception):
            _post(hook, payload, port)
    # Printed last and unconditionally. A hook that prints anything else here can
    # gate the user's tool calls, so there is exactly one thing this script says.
    print(EMPTY_RESULT)
    return 0


def _post(hook: str, payload: dict[str, Any], port: int) -> None:
    event = envelope(hook, payload)
    if event is None:
        return
    token = capability(port)
    if token is None:
        return
    shared = _shared()
    if shared is None:
        return
    shared.forward(
        f"http://127.0.0.1:{port}/api/events/{HARNESS}",
        json.dumps(event, separators=(",", ":")).encode(),
        headers={"X-Cargento-Capability": token},
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
