# ruff: noqa: INP001 -- standalone, test-only contributor fixture
"""The shell's synthetic board with the real focus capability and an inert native raise.

Composes two existing helpers without changing either: the board rows come from
`support/fixture_backend.py` (every collection stamps `last_activity`, so each read of the real
backend is a real data change), and the capability and inert raise come from
`../test/dev_capability_backend.py`. The CLI, HTTP guard, capability and origin checks are the real
ones; no terminal can be raised and no model or usage call is made.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "support"))
sys.path.insert(0, str(HERE.parent / "test"))

import dev_capability_backend as capability  # noqa: E402
import fixture_backend as board  # noqa: E402
from cargento_runtime import cli  # noqa: E402

if __name__ == "__main__":
    cli.aggregate.default_harnesses = board.fixture_harnesses
    cli.validate_frontend_args = capability.fixture_capabilities
    cli.observation.Observation = capability.InertObservation
    raise SystemExit(cli.main())
