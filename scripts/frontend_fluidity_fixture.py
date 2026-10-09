#!/usr/bin/env python3
"""Owned, synthetic data for the React page's fluidity measurement (no harness subprocesses).

This is the pre-React baseline's fixture, byte for byte in what it publishes, served with the
assembled React page instead of the legacy one. It reuses `frontend_baseline_fixture` rather than
copying it, so the 5/50/250 cohorts, the row shape, the titles and the empty/unavailable states are
the baseline's own and a difference in a measurement cannot come from a difference in the data.
Two names are rebound while the baseline's `Fixture` is built: the runtime config says
`frontend="react"` (so `/api/data` publishes the React build identity the page checks) and the page
is the integrity-checked React document. Nothing about the baseline module changes, so the pre-React
receipt's source bindings stay true.

The JSON-lines stdin channel changes fixtures without adding a production HTTP API. Stdout carries
only readiness and control acknowledgements; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import frontend_baseline_fixture as baseline
from cargento_runtime.config import build_runtime_config  # path set by the baseline import
from cargento_runtime.web.page import load_frontend_page

# The ports the migration may bind. The baseline's own 4571..4599 range also holds ports other
# dashboards run on, so the React measurement narrows it rather than inheriting it.
ALLOWED_PORTS = (*range(4581, 4587), 4594, 4595, *range(4597, 4600))


def validate_port(value: int) -> int:
    if type(value) is not int or value not in ALLOWED_PORTS:
        msg = "fluidity port must be in 4581..4586, 4594, 4595 or 4597..4599"
        raise ValueError(msg)
    return baseline.validate_port(value)


def build_fixture(scratch: Path) -> baseline.Fixture:
    """The baseline's `Fixture`, built over the React document and a React runtime config."""
    with (
        mock.patch.object(
            baseline,
            "build_runtime_config",
            functools.partial(build_runtime_config, frontend="react"),
        ),
        mock.patch.object(baseline, "load_page", lambda: load_frontend_page("react")),
    ):
        return baseline.Fixture(scratch)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4581)
    parser.add_argument("--cohort", choices=baseline.COHORTS, default="small")
    parser.add_argument("--state", choices=baseline.STATES, default="healthy")
    args = parser.parse_args()
    try:
        validate_port(args.port)
    except ValueError as error:
        parser.error(str(error))
    with tempfile.TemporaryDirectory(prefix="cargento-fluidity-") as scratch:
        fixture = build_fixture(Path(scratch))
        fixture.configure(cohort=args.cohort, state=args.state, sequence=1)
        with fixture.server(args.port) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            print(
                json.dumps(
                    {
                        "ready": True,
                        "port": args.port,
                        "frontend": fixture.application.config.frontend,
                        **fixture.describe(),
                    }
                ),
                flush=True,
            )
            try:
                for line in sys.stdin:
                    try:
                        body = fixture.control(json.loads(line))
                        print(json.dumps({"ack": True, **body}), flush=True)
                    except (ValueError, TypeError) as exc:
                        print(json.dumps({"error": str(exc)}), flush=True)
            finally:
                server.shutdown()
                worker.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
