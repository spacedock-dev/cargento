# ruff: noqa: INP001 -- standalone, test-only contributor fixture
"""Run the real development CLI with genuine capabilities and inert native focus.

This helper is a browser-test seam, never the normal pnpm dev entry point.
Only the event/focus opt-outs are lifted; model/usage/data-root admission and
all real HTTP capability/origin checks still apply. No terminal can be raised.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cargento/skills/cargento"))

from cargento_runtime import cli, observation

_VALIDATE = cli.validate_frontend_args


def fixture_capabilities(parser: Any, args: Any) -> None:
    _VALIDATE(parser, args)
    if args.frontend_dev_manifest is None:
        parser.error("capability fixture requires an owned development startup ticket")
    args.no_events = False
    args.no_focus = False


class InertObservation(observation.Observation):
    def raise_focus(self, _target: Any, *, runner: Any = None) -> bool:
        del runner
        return False


if __name__ == "__main__":
    cli.validate_frontend_args = fixture_capabilities
    cli.observation.Observation = InertObservation
    raise SystemExit(cli.main())
