# ruff: noqa: INP001 -- standalone, test-only contributor fixture
"""Run the real CLI over a synthetic board with what the Console, Decisions and Course tabs draw.

Only the collectors, the source of the workflow stage conditions, the history file and the terminal
adapter are replaced. The CLI, HTTP guard, page selection, snapshot code, history lane,
stage-condition store and its `/api/tripwire` route, ask registry and interaction registry are the
real ones, so a browser proof reads what a reader's page would. Nothing here reads a harness
store, starts a terminal, calls a provider or fetches a quota: a model and the usage fetch stay off,
and the one native action a session could cause (raising a terminal) is inert.

What the board holds, by design rather than by accident:

- `alpha/app`: a working session with a token rate, a session blocked on an exact request (with a
  resume command), a Spacedock session, and the synthetic terminal's session. Its stored history is
  long enough that the delegation figure is known, with working, gated and idle spans.
- `beta/api`: two idle sessions whose stored history contains no working time, so the delegation
  figure is withheld rather than drawn as zero.
- one quota provider with a 5-hour and a weekly window, and one workflow stage source whose sessions
  are two of `alpha/app`'s, so the Course tab's conditions narrow with the selected session.
- the project context of `terminal_backend`: directions, a dispatch, a stage transition and a
  recorded decision, so the Decisions tab has rows to filter.
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
sys.path.insert(0, str(HERE.parent / "e2e" / "support"))

import terminal_backend as terminal  # noqa: E402
from cargento_runtime import (  # noqa: E402
    aggregate,
    asks,
    cli,
    history,
    observation,
    project_context,
    sessions,
    state,
    tripwires,
)

STARTED = time.time()
HOUR = 3600.0
ALPHA = "alpha/app"
BETA = "beta/api"


def _row(harness: str, sid: str, project: str, **fields: Any) -> sessions.Session:
    row = sessions.base_session(harness, sid, project)
    row.update({"last_activity": STARTED, **fields})
    return row


CLAUDE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "sid": "live-work",
        "project": ALPHA,
        "title": "Retry the queue",
        "state": "working",
        "state_detail": "generating",
        "active": True,
        "rate_per_min": 1234,
        "resume_id": "live-work",
        "subagents": [
            {"name": "lead", "active": True, "state": "working", "started_at": STARTED - 240},
            {
                "name": "child",
                "active": True,
                "state": "working",
                "parent": "lead",
                "started_at": STARTED - 100,
            },
        ],
    },
    {
        "sid": "gate-open",
        "project": ALPHA,
        "title": "Needs a decision",
        "state": "needs_input",
        "state_detail": "waiting on a permission prompt",
        "blocked_since": STARTED - 140,
        "focusable": True,
        "resume_id": "gate-open",
    },
    {
        "sid": "workflow-run",
        "project": ALPHA,
        "title": "Workflow session",
        "state": "idle",
        "last_activity": STARTED - 30,
    },
    {
        "sid": "beta-idle",
        "project": BETA,
        "title": "Beta idle",
        "state": "idle",
        "last_activity": STARTED - 4000,
    },
)

CODEX_ROWS: tuple[dict[str, Any], ...] = (
    {
        "sid": terminal.TERMINAL_SID,
        "project": ALPHA,
        "title": "Synthetic terminal session",
        "state": "idle",
        "resume_id": "term-1",
        "last_activity": STARTED - 20,
    },
    {
        "sid": "beta-codex",
        "project": BETA,
        "title": "Beta codex idle",
        "state": "idle",
        "last_activity": STARTED - 4100,
    },
)

ASKS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("claude", "gate-open", ALPHA, "Approve the retry plan?", ("Yes, run it", "No, stop")),
)

# Each entry: hours before the start of the run, harness, sid, project, state. The last record of a
# session closes its span, so the figure covers the time two sessions were observed together.
TIMELINE: tuple[tuple[float, str, str, str, str], ...] = (
    (13.0, "claude", "live-work", ALPHA, "working"),
    (13.0, "codex", terminal.TERMINAL_SID, ALPHA, "idle"),
    (12.0, "claude", "gate-open", ALPHA, "idle"),
    (10.0, "codex", terminal.TERMINAL_SID, ALPHA, "working"),
    (9.5, "codex", terminal.TERMINAL_SID, ALPHA, "idle"),
    (9.0, "claude", "live-work", ALPHA, "idle"),
    (8.0, "claude", "live-work", ALPHA, "working"),
    (6.0, "claude", "gate-open", ALPHA, "needs_input"),
    (5.5, "claude", "gate-open", ALPHA, "working"),
    (5.0, "claude", "gate-open", ALPHA, "idle"),
    (1.0, "claude", "live-work", ALPHA, "idle"),
    (4.0, "claude", "beta-idle", BETA, "idle"),
    (3.9, "codex", "beta-codex", BETA, "idle"),
)

SOURCE_ID = "ab" * 32


def collect(harness: str, rows: tuple[dict[str, Any], ...]) -> Any:
    def run(*_args: Any, **_kwargs: Any) -> list[sessions.Session]:
        out = []
        for spec in rows:
            fields = dict(spec)
            out.append(_row(harness, fields.pop("sid"), fields.pop("project"), **fields))
        return out

    return run


def quota(_config: Any, _state: Any, now: float, _window_hours: float) -> list[dict[str, Any]]:
    """Two windows, one of them partly spent, each on its own clock."""
    return [
        {
            "harness": "claude",
            "state": "ok",
            "asOf": now,
            "fiveH": {"pct": 34, "windowSec": 18000, "resetAt": now + 9000},
            "week": {"pct": 82, "windowSec": 604800, "resetAt": now + 3 * 86400},
        }
    ]


def fixture_harnesses(**_kwargs: Any) -> tuple[aggregate.HarnessSpec, ...]:
    return (
        aggregate.HarnessSpec(
            "claude",
            "Claude Code",
            lambda *_: True,
            collect("claude", CLAUDE_ROWS),
            reports_needs_input=True,
            reports_rate=True,
            usage=quota,
        ),
        aggregate.HarnessSpec(
            "codex",
            "Codex",
            lambda *_: True,
            collect("codex", CODEX_ROWS),
            reports_needs_input=True,
        ),
    )


def stage_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One workflow whose sessions are two of `alpha/app`'s: the card follows the selection."""
    members = [
        {"harness": row["harness"], "sid": row["sid"], "label": row.get("title") or row["sid"]}
        for row in rows
        if row["sid"] in {"live-work", "workflow-run"}
    ]
    return [
        {
            "id": SOURCE_ID,
            "workflow": "Ship the queue",
            "goal": "Drain the retry queue",
            "stages": ["intake", "build", "review", "done"],
            "generation": "generation-1",
            "entities": [
                {
                    "slug": "task-1",
                    "stage": "build",
                    "source_written_at": STARTED - 100.0,
                    "observed_at": STARTED - 90.0,
                }
            ],
            "evaluated": 1,
            "partial": False,
            "ambiguous": False,
            "sessions": members,
        }
    ]


_VALIDATE = cli.validate_frontend_args


def lift_opt_outs(parser: Any, args: Any) -> None:
    """Keep every real check, lifting only the lanes this board needs."""
    _VALIDATE(parser, args)
    for name in ("no_ask", "no_events", "no_focus", "no_history", "no_tripwires", "no_spacedock"):
        setattr(args, name, False)


class InertObservation(observation.Observation):
    def raise_focus(self, _target: Any, *, runner: Any = None) -> bool:
        del runner
        return False


def seed_history(config: Any) -> None:
    kept: tuple[history.Observation, ...] = ()
    for hours, harness, sid, project, session_state in sorted(TIMELINE, reverse=True):
        at = STARTED - hours * HOUR
        row = _row(harness, sid, project, state=session_state, last_activity=at)
        kept, _changed = history.appended(
            kept,
            [row],
            now=STARTED,
            retention_sec=config.history_retention_sec,
            max_bytes=config.history_max_bytes,
        )
    history.save(config, kept)


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
        # The deadline is five minutes and a browser run can be longer; an open ask is renewed.
        while True:
            time.sleep(30)
            now = time.time()
            for ask in pending:
                if not ask.resolved:
                    ask.created = now

    threading.Thread(target=keep_alive, daemon=True).start()


_BUILD = state.build_runtime_state


def build_seeded(config: Any, *, started: float) -> state.RuntimeState:
    seed_history(config)
    runtime = _BUILD(config, started=started)
    register_asks(runtime)
    return runtime


if __name__ == "__main__":
    cli.aggregate.default_harnesses = fixture_harnesses
    cli.validate_frontend_args = lift_opt_outs
    cli.observation.Observation = InertObservation
    cli.runtime_state.build_runtime_state = build_seeded
    cli.build_server = terminal.build_server
    project_context.collect = terminal.collect
    tripwires.sources_from_sessions = stage_sources
    raise SystemExit(cli.main())
