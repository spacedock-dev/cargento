# ruff: noqa: INP001 -- standalone, test-only contributor fixture
"""The shell's synthetic board with one synthetic, read-only terminal the browser test can drive.

The real CLI, HTTP guard, page selection, interaction registry and output-only WebSocket are the
real ones. Only two things are replaced: the board's collectors (`e2e/support/fixture_backend.py`,
plus one extra session that owns the terminal) and the terminal adapter, which starts no tmux, no
PTY and no child process. Its output comes from a control file the test appends to, so a test
decides exactly when and what the "pane" prints; nothing else can reach the stream.

The control file is `<CARGENTO_HOME>/terminal-fixture/control.ndjson`, one JSON object per line:
`{"text": "..."}` prints that text to the pane, `{"disconnect": true}` drops the read-only stream.
`CARGENTO_HOME` is the isolated scratch the dev supervisor (or the test) already owns, so the file
is created, read and removed with it.

The project context answers with one fixed semantic model (facts, a work item, a dispatch relation,
directions and a gate decision), so the timeline has events to filter and fold. Only the `semantic`
object is replaced; the route, its guards, its bounds and its page filter are the real ones.

Every session of the board except the terminal's own answers the registration lookup with
`session-mismatch`, and a server started without this helper answers 404 (bridge disabled), which
together cover the registered, refused and disabled readings.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "cargento/skills/cargento"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "e2e" / "support"))

import fixture_backend as board  # noqa: E402
import installed_backend  # noqa: E402
from cargento_runtime import cli, interaction_prototype, project_context  # noqa: E402

# The one session the terminal registers for. The registry names it
# `codex:disposable-tmux-origin:<n>`, so the board has to publish a session with exactly that sid.
TERMINAL_SID = "disposable-tmux-origin:1"
TERMINAL_PROJECT = "gamma/term"

board.ROWS = (
    *board.ROWS,
    ("codex", TERMINAL_SID, TERMINAL_PROJECT, "Synthetic terminal session", "idle", True, 0),
)


FOCUS = {"harness": "codex", "sid": TERMINAL_SID}
TASK = "workflow:project-cockpit"


def _evidence(source: str) -> dict[str, str]:
    return {"source": source, "confidence": "exact"}


def _direction(index: int, at: int, summary: str) -> dict[str, Any]:
    return {
        "fact_id": f"dir-{index}",
        "at": at,
        "type": "user_message",
        "summary": summary,
        "source_session": FOCUS,
        "evidence": _evidence("root transcript"),
    }


# Eight distinct directions, newest first: five are primary, three fold into "Earlier meaningful".
DIRECTIONS = [
    "Make the lane order follow the newest direction",
    "Correct the dispatch authority wording",
    "Keep the timeline read-only",
    "Show recorded decisions without the noise",
    "Fold older directions into a band",
    "Name the project in every disclosure key",
    "Restore the filter after a reload",
    "Keep the terminal output only",
]

SEMANTIC: dict[str, Any] = {
    "facts": [
        *[
            _direction(index, 1_899_999_000 - index * 3600, text)
            for index, text in enumerate(DIRECTIONS)
        ],
        {
            "fact_id": "task-a",
            "at": 1_899_998_900,
            "type": "prepared_dispatch",
            "summary": "Dispatch cockpit",
            "source_session": FOCUS,
            "work_item_id": TASK,
            "evidence": _evidence("dispatch artifact"),
        },
        {
            "fact_id": "task-b",
            "at": 1_899_998_800,
            "type": "stage_transition",
            "stage": "shaping",
            "summary": "Shaping cockpit",
            "work_item_id": TASK,
            "evidence": _evidence("workflow state"),
        },
        {
            "fact_id": "gate-a",
            "at": 1_899_998_700,
            "type": "gate_decision",
            "source_kind": "gate",
            "summary": "project-cockpit · review · approve",
            "scope": "project",
            "by": "person:captain",
            "decision": "approve",
            "stage": "review",
            "application_state": "consumed",
            "target_stage": "shaping",
            "work_item_id": TASK,
            "evidence": _evidence("entity gate"),
        },
    ],
    "work_items": [{"work_item_id": TASK, "label": "project-cockpit", "kind": "workflow_item"}],
    "relations": [
        {
            "type": "dispatches_to",
            "from": f"fo:codex:{TERMINAL_SID}",
            "to": f"task:{TASK}",
            "evidence_ref": "task-a",
            "confidence": "exact",
        }
    ],
    "projections": {
        "operator_intents": [
            {
                "projection_id": f"intent-{index}",
                "at": 1_899_999_000 - index * 3600,
                "summary": text,
                "derived_from": f"dir-{index}",
            }
            for index, text in enumerate(DIRECTIONS)
        ],
        "steering_episodes": [],
        "trail_heads": [
            {
                "work_item_id": TASK,
                "status": "current stage",
                "stage": "shaping",
                "latest_meaningful_event": "task-b",
            }
        ],
        "activity": {"nodes": [{"kind": "work", "at": 1_899_998_900, "work_item_ids": [TASK]}]},
    },
    "history": {"window_sec": 86400, "events": []},
}


def control_path() -> Path:
    return Path(os.environ["CARGENTO_HOME"]) / "terminal-fixture" / "control.ndjson"


class ControlledTerminal(installed_backend.SyntheticTerminal):
    """The installed smoke's synthetic terminal, with output a test controls."""

    def __init__(self, api: Any) -> None:
        super().__init__(api)
        self.path = control_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"")
        self.reader: threading.Thread | None = None

    def start_read_only_stream(self, origin: Any, output: Any, disconnected: Any) -> None:
        self.output, self.disconnected = output, disconnected
        output(origin.pane_id, "Synthetic read-only terminal ready\r\n")
        if self.reader is None:
            self.reader = threading.Thread(target=self.follow, args=(origin,), daemon=True)
            self.reader.start()

    def follow(self, origin: Any) -> None:
        offset = 0
        while not self.stop_event.wait(0.03):
            try:
                data = self.path.read_bytes()
            except OSError:
                continue
            end = data.rfind(b"\n") + 1
            if end <= offset:
                continue
            for line in data[offset:end].splitlines():
                offset += len(line) + 1
                command = json.loads(line)
                if command.get("disconnect"):
                    self.stop_read_only_stream()
                elif isinstance(command.get("text"), str) and self.output is not None:
                    self.output(origin.pane_id, command["text"])

    def capture(self, origin: Any) -> str:
        self.inspect(origin)
        return "Synthetic read-only terminal ready\r\n"

    def stop(self) -> None:
        super().stop()
        if self.reader is not None:
            self.reader.join(2)


def attach_terminal(server: Any) -> None:
    prototype = interaction_prototype.InteractionPrototype(
        ControlledTerminal(interaction_prototype), lease_sec=3
    )
    server.interaction_prototype = prototype
    session = f"codex:{TERMINAL_SID}"

    def register() -> None:
        # `resolve_session` starts the synthetic client, which registers over HTTP once the server
        # is serving; ask until the registry says it holds the lease.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if prototype.resolve_session(server.server_port, session).get("state") == "registered":
                return
            time.sleep(0.05)

    threading.Thread(target=register, daemon=True).start()


_BUILD = cli.build_server
_COLLECT = project_context.collect


def collect(*args: Any, **kwargs: Any) -> dict[str, Any]:
    result = _COLLECT(*args, **kwargs)
    result["semantic"] = {**result.get("semantic", {}), **SEMANTIC}
    return result


def build_server(*args: Any, **kwargs: Any) -> Any:
    server = _BUILD(*args, **kwargs)
    attach_terminal(server)
    return server


if __name__ == "__main__":
    cli.aggregate.default_harnesses = board.fixture_harnesses
    cli.build_server = build_server
    project_context.collect = collect
    raise SystemExit(cli.main())
