# ruff: noqa: INP001 -- standalone, test-only contributor fixture
"""Run the real CLI over the Console board with a quota provider and model offer a test can steer.

Everything the capacity and consent proofs need to see is steered from one control file and counted
in one event log, both under `<CARGENTO_HOME>/capacity-fixture/`, which the supervisor (or the test)
owns:

- `control.json`: `{"windows": "full" | "reordered" | "fewer" | "none", "observer": "enabled" |
  "disabled" | "absent" | "no-disclosure"}`. Read on every call, so a test changes the board between
  two polls.
- `events.ndjson`: one JSON object per line. `usage_fetch` is a `/api/data?usage=1` request that
  reached the application, and `model_call` is a project-context request that carried the
  observer-model consent.

Nothing here reads a credential, calls a vendor or calls a model. The quota provider is a function
over fixed numbers. The usage fetch the server would start on `usage=1` is replaced by a recorder
that starts nothing, so a page that asks for it is observable and harmless. The real project
context is always collected WITHOUT the model consent, so even a request that carried it reaches no
model: the fixture only answers it with a canned goal and counts it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "cargento/skills/cargento"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "e2e" / "support"))

import console_backend as board  # noqa: E402
from cargento_runtime import aggregate, cli, project_context, state  # noqa: E402

DISCLOSURE = (
    "Send redacted transcript excerpts to the fixture reader for a goal summary? "
    "Nothing leaves this machine in the test."
)
GOAL = "Retry the queue until it drains"
DAY = 86400.0
_LOCK = threading.Lock()


def _folder() -> Path:
    return Path(os.environ["CARGENTO_HOME"]) / "capacity-fixture"


def control() -> dict[str, str]:
    try:
        raw = json.loads((_folder() / "control.json").read_text())
    except (OSError, ValueError):
        raw = {}
    return {"windows": "full", "observer": "enabled", **raw} if isinstance(raw, dict) else {}


def record(event: str, **fields: Any) -> None:
    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    with _LOCK, (folder / "events.ndjson").open("a") as out:
        out.write(json.dumps({"event": event, **fields}) + "\n")


def _window(
    pct: int, length: float | None, reset_in: float | None, now: float, **extra: Any
) -> dict[str, Any]:
    window: dict[str, Any] = {"pct": pct, **extra}
    if length is not None:
        window["windowSec"] = length
    if reset_in is not None:
        window["resetAt"] = now + reset_in
    return window


def quota(_config: Any, _state: Any, now: float, _window_hours: float) -> list[dict[str, Any]]:
    """Windows on their own clocks: a measured zero, no clock, a spent budget and sub-limits."""
    mode = control()["windows"]
    if mode == "none":
        return []
    claude: dict[str, Any] = {
        "harness": "claude",
        "state": "ok",
        "asOf": now - 20,
        "fiveH": _window(
            95 if mode == "reordered" else 34,
            18000,
            9000,
            now,
            recent={"pctPerMin": 0.01, "samples": 3, "spanSec": 1800},
        ),
        "week": _window(
            82,
            7 * DAY,
            3 * DAY,
            now,
            recent={"pctPerMin": 0, "samples": 4, "spanSec": 3600},
        ),
        "models": [{"label": "Opus", "pct": 71}, {"label": "Sonnet", "pct": 0}],
    }
    if mode == "fewer":
        # One vendor, and its third window publishes no clock at all.
        return [{**claude, "month": _window(40, None, None, now)}]
    return [
        claude,
        {
            "harness": "cursor",
            "state": "ok",
            "asOf": now - 20,
            "fiveH": _window(100, 18000, 6000, now),
            "month": _window(40, None, None, now),
        },
        {
            "harness": "codex",
            "state": "ok",
            "asOf": None,
            # Slower and later when reordered, so the budget ends after the weekly claude row's.
            "fiveH": _window(5 if mode == "reordered" else 20, 18000, 12000, now),
            "week": _window(30, 7 * DAY, 4 * DAY, now),
        },
    ]


def fixture_harnesses(**_kwargs: Any) -> tuple[aggregate.HarnessSpec, ...]:
    # The claude provider raises `usage_fetch` as a real credential-fetching one does.
    return (
        aggregate.HarnessSpec(
            "claude",
            "Claude Code",
            lambda *_: True,
            board.collect("claude", board.CLAUDE_ROWS),
            reports_needs_input=True,
            reports_rate=True,
            usage=quota,
            usage_is_fetch=True,
        ),
        aggregate.HarnessSpec(
            "codex",
            "Codex",
            lambda *_: True,
            board.collect("codex", board.CODEX_ROWS),
            reports_needs_input=True,
        ),
    )


def request_usage_fetch(_self: Any) -> bool:
    record("usage_fetch")
    return False


_COLLECT = project_context.collect


def collect(*args: Any, **kwargs: Any) -> dict[str, Any]:
    consented = bool(kwargs.pop("model_consent", False))
    result = _COLLECT(*args, **kwargs, model_consent=False)
    mode = control()["observer"]
    offer = {"enabled": True, "max_prompt_bytes": 16384, "disclosure": DISCLOSURE}
    if mode == "absent":
        result.pop("observer_model", None)
    elif mode == "disabled":
        result["observer_model"] = {**offer, "enabled": False}
    elif mode == "no-disclosure":
        result["observer_model"] = {**offer, "disclosure": ""}
    else:
        result["observer_model"] = offer
    focus = kwargs.get("focus")
    if consented and focus is not None:
        record("model_call", harness=focus[0], sid=focus[1])
        rows = [
            row
            for row in result.get("observers", [])
            if (row.get("harness"), row.get("sid")) != focus
        ]
        rows.append(
            {"harness": focus[0], "sid": focus[1], "goal": GOAL, "model": {"status": "fixture"}}
        )
        result["observers"] = rows
    return result


_BUILD = state.build_runtime_state


def build_seeded(config: Any, *, started: float) -> state.RuntimeState:
    board.seed_history(config)
    runtime = _BUILD(config, started=started)
    board.register_asks(runtime)
    return runtime


if __name__ == "__main__":
    cli.aggregate.default_harnesses = fixture_harnesses
    cli.validate_frontend_args = board.lift_opt_outs
    cli.observation.Observation = board.InertObservation
    cli.runtime_state.build_runtime_state = build_seeded
    aggregate.Application.request_usage_fetch = request_usage_fetch
    project_context.collect = collect
    raise SystemExit(cli.main())
