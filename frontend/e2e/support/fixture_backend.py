# ruff: noqa: INP001 -- standalone, test-only contributor fixture
"""Run the real CLI over a fixed synthetic board, for the shell's browser tests.

The two harnesses publish rows that exercise the route grammar: one sid carried by both
harnesses, a sid with a colon, a session whose project label is empty, and a session with no
published title. Only the collectors are replaced. The CLI, HTTP guard, page selection and
snapshot code are the real ones, so the same helper serves the legacy page and the React page
and a differential run compares like with like. Nothing here reads a harness store, starts a
terminal or calls a provider.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "cargento/skills/cargento"))

from cargento_runtime import aggregate, cli, sessions

# Fixed at start, so the board's revision does not move on its own and a test can tell a read it
# caused from one the stream announced.
STARTED = time.time()

# Columns: harness, sid, project, title, state, active, subagent count.
ROWS: tuple[tuple[str, str, str, str | None, str, bool, int], ...] = (
    ("claude", "shared-sid", "alpha/app", "Alpha shared claude", "working", True, 2),
    ("codex", "shared-sid", "alpha/app", "Alpha shared codex", "idle", False, 0),
    ("claude", "colon:sid", "beta/api", None, "needs_input", False, 1),
    ("codex", "bare-project-sid", "", "No project label", "idle", False, 0),
    ("codex", "beta-working", "beta/api", "Beta working", "working", True, 0),
)


def collect(harness: str) -> Any:
    def run(*_args: Any, **_kwargs: Any) -> list[sessions.Session]:
        rows = []
        for row_harness, sid, project, title, state, active, subagents in ROWS:
            if row_harness != harness:
                continue
            row = sessions.base_session(harness, sid, project)
            row.update(
                title=title,
                state=state,
                active=active,
                last_activity=STARTED,
                subagents=[
                    {"name": f"helper-{index}", "active": True, "state": "working"}
                    for index in range(subagents)
                ],
            )
            rows.append(row)
        return rows

    return run


def fixture_harnesses(**_kwargs: Any) -> tuple[aggregate.HarnessSpec, ...]:
    return tuple(
        aggregate.HarnessSpec(
            name,
            name.title(),
            lambda *_: True,
            collect(name),
            reports_needs_input=True,
        )
        for name in ("claude", "codex")
    )


if __name__ == "__main__":
    cli.aggregate.default_harnesses = fixture_harnesses
    raise SystemExit(cli.main())
