# ruff: noqa: INP001 -- standalone, test-only contributor fixture
"""Run the real CLI over a synthetic board with every session state the Sessions screen draws.

Only the collectors are replaced. The CLI, HTTP guard, page selection, snapshot code, answer
route, ask registry and capability checks are the real ones, so the same helper serves the
legacy page and the React page and a differential run compares like with like. Nothing here
reads a harness store, starts a terminal or calls a provider: models and usage stay off, and the
one native action a session could cause (raising a terminal) is inert.

What the board holds, by design rather than by accident:

- one sid under two harnesses, a sid with colons, a session with no project label, two sessions
  that publish one label (a collision), and a unicode title;
- a working session with workers (one beneath another) and tasks, a blocked one holding an exact
  request, a Spacedock session holding another (its answer is the captain's), an idle one, one
  that stopped with uncommitted work, one with an observed end that still says "working", one
  read by scanning, one with a source gap, one that launched work nobody has seen finish, and
  one on a long turn with a failing tool loop;
- a harness whose store cannot be read, so its absence is stated and not read as "no sessions".

The asks live in the real registry and are kept alive for the run, so a test can answer one
through the real `/api/answer` route and watch it leave the board.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "cargento/skills/cargento"))
sys.path.insert(0, str(HERE))

from cargento_runtime import aggregate, asks, cli, observation, sessions, state  # noqa: E402

STARTED = time.time()
ENDED = STARTED - 90


def _row(harness: str, sid: str, project: str, **fields: Any) -> sessions.Session:
    row = sessions.base_session(harness, sid, project)
    row.update({"last_activity": STARTED, **fields})
    return row


CLAUDE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "sid": "live-work",
        "project": "alpha/app",
        "title": "Retry the queue",
        "state": "working",
        "state_detail": "generating",
        "active": True,
        "rate_per_min": 1234,
        "resume_id": "live-work",
        "first_prompt": "Make the retry queue drain in order",
        "first_prompt_at": STARTED - 600,
        "instruction": {
            "label": "asked",
            "text": "Drain the retry queue in order",
            "at": STARTED - 300,
        },
        "tasks": [
            {"id": "1", "subject": "Write the failing test", "status": "completed"},
            {"id": "2", "subject": "Fix the drain order", "status": "in_progress"},
            {"id": "3", "subject": "Run the suite", "status": "pending"},
        ],
        "subagents": [
            {"name": "lead", "active": True, "state": "working", "started_at": STARTED - 240},
            {
                "name": "child",
                "active": True,
                "state": "working",
                "parent": "lead",
                "started_at": STARTED - 100,
            },
            {"name": "finished", "active": False, "state": "idle", "started_at": STARTED - 900},
        ],
        "subagents_omitted": 2,
        "session_output_tokens": 48210,
        "turn_output_tokens": 1500,
        "turn": {"elapsed_h": "4m", "eta_h": "2m", "long": False},
    },
    {
        "sid": "gate-open",
        "project": "alpha/app",
        "title": "Needs a decision",
        "state": "needs_input",
        "state_detail": "waiting on a permission prompt",
        "blocked_since": STARTED - 140,
        "focusable": True,
        "resume_id": "gate-open",
        "instruction": {"label": "agent", "text": "Choose how to continue", "at": STARTED - 60},
    },
    {
        "sid": "shared-sid",
        "project": "alpha/app",
        "title": "Shared sid under claude",
        "state": "idle",
        "last_activity": STARTED - 3000,
    },
    {
        "sid": "ended-still-working",
        "project": "beta/api",
        "title": "Ended but still says working",
        "state": "working",
        "active": True,
        "ended_at": ENDED,
        "dirty": True,
        "changed": 3,
    },
    {
        "sid": "stopped-dirty",
        "project": "beta/api",
        "title": "Stopped with uncommitted work",
        "state": "idle",
        "finished_at": STARTED - 500,
        "dirty": True,
        "changed": 2,
        "last_activity": STARTED - 500,
    },
    {
        "sid": "long-turn",
        "project": "gamma",
        "title": "A long turn and a failing loop",
        "state": "working",
        "active": True,
        "turn": {"elapsed_h": "41m", "long": True},
        "loop": {
            "errors": 3,
            "failures": 5,
            "tool": "mcp__claude_ai_Slack__send_message",
            "barren": False,
        },
    },
    {
        "sid": "delegated",
        "project": "gamma",
        "title": "Launched work nobody saw finish",
        "state": "idle",
        "last_activity": STARTED - 2400,
        "delegated_launches": 2,
        "delegated_unpaired": 1,
        "delegated_latest_launch_at": STARTED - 2600,
        "delegated_last_activity_at": STARTED - 2500,
        "delegated_quiet_since": STARTED - 2400,
        "delegated_visibility": "partial",
    },
    {
        "sid": "unicode-title",
        "project": "ünï/çødé",
        "title": 'Ünï ✓ <b>not markup</b> & "quotes"',
        "state": "idle",
        "last_activity": STARTED - 4000,
    },
    {
        "sid": "spacedock-asked",
        "project": "delta",
        "title": "A captain's question",
        "state": "idle",
        "last_activity": STARTED - 20,
        "spacedock": {"workflows": [{"goal": "Ship the workflow", "stage": "build"}]},
    },
)

CODEX_ROWS: tuple[dict[str, Any], ...] = (
    {
        "sid": "shared-sid",
        "project": "alpha/app",
        "title": "Shared sid under codex",
        "state": "idle",
        "last_activity": STARTED - 3100,
    },
    {
        "sid": "colon:sid",
        "project": "beta/api",
        "title": None,
        "last_prompt": "A prompt with no title",
        "state": "idle",
        "last_activity": STARTED - 3200,
    },
    {
        "sid": "no-project",
        "project": "",
        "title": "No project label",
        "state": "idle",
        "last_activity": STARTED - 3300,
    },
    {
        "sid": "scan-only",
        "project": "delta",
        "title": "Read by scanning",
        "state": "idle",
        "acquisition": "scan-only",
        "last_activity": STARTED - 3400,
    },
    {
        "sid": "source-gap",
        "project": "delta",
        "title": "Part of its store was unreadable",
        "state": "idle",
        "source_gaps": ["block state", "token accounting"],
        "last_activity": STARTED - 3500,
    },
    {
        "sid": "idle-recent",
        "project": "alpha/app",
        "title": "Idle and recent",
        "state": "idle",
        "last_activity": STARTED - 10,
    },
)

# The exact requests: harness, session id, question, options. Kept alive for the run
# (see `_keep_alive`).
ASKS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "claude",
        "gate-open",
        "alpha/app",
        "Approve the retry plan?",
        ("Yes, run it", "No, stop", "Ask me later"),
    ),
    ("claude", "spacedock-asked", "delta", "Ship the stage?", ("Ship", "Hold")),
)


def collect(harness: str, rows: tuple[dict[str, Any], ...]) -> Any:
    def run(*_args: Any, **_kwargs: Any) -> list[sessions.Session]:
        out = []
        for spec in rows:
            fields = dict(spec)
            out.append(_row(harness, fields.pop("sid"), fields.pop("project"), **fields))
        return out

    return run


def unreadable(*_args: Any, **_kwargs: Any) -> list[sessions.Session]:
    raise OSError("the store is not readable")


def fixture_harnesses(**_kwargs: Any) -> tuple[aggregate.HarnessSpec, ...]:
    return (
        aggregate.HarnessSpec(
            "claude",
            "Claude Code",
            lambda *_: True,
            collect("claude", CLAUDE_ROWS),
            reports_needs_input=True,
            reports_rate=True,
        ),
        aggregate.HarnessSpec(
            "codex",
            "Codex",
            lambda *_: True,
            collect("codex", CODEX_ROWS),
            reports_needs_input=True,
        ),
        aggregate.HarnessSpec("pi", "Pi", lambda *_: True, unreadable),
    )


_VALIDATE = cli.validate_frontend_args


def lift_opt_outs(parser: Any, args: Any) -> None:
    """Keep every real check, lifting only the ask route and the capability the board needs."""
    _VALIDATE(parser, args)
    args.no_ask = False
    args.no_events = False
    args.no_focus = False


class InertObservation(observation.Observation):
    def raise_focus(self, _target: Any, *, runner: Any = None) -> bool:
        del runner
        return False


def register_asks(runtime: state.RuntimeState) -> None:
    pending = []
    for harness, sid, project, question, options in ASKS:
        ask = asks.PendingAsk(
            harness=harness,
            session_id=sid,
            project=project,
            question=question,
            options=options,
            created=time.time(),
        )
        if runtime.asks.register(ask, limit=16, deadline=300.0, retention=60.0):
            pending.append(ask)

    def keep_alive() -> None:
        # The deadline is five minutes and a browser run can be longer; an unresolved ask is
        # simply renewed.
        while True:
            time.sleep(30)
            now = time.time()
            for ask in pending:
                if not ask.resolved:
                    ask.created = now

    threading.Thread(target=keep_alive, daemon=True).start()


_BUILD = state.build_runtime_state


def build_with_asks(config: Any, *, started: float) -> state.RuntimeState:
    runtime = _BUILD(config, started=started)
    register_asks(runtime)
    return runtime


if __name__ == "__main__":
    cli.aggregate.default_harnesses = fixture_harnesses
    cli.validate_frontend_args = lift_opt_outs
    cli.observation.Observation = InertObservation
    cli.runtime_state.build_runtime_state = build_with_asks
    raise SystemExit(cli.main())
