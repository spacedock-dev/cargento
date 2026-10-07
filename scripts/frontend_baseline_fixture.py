#!/usr/bin/env python3
"""Owned, synthetic data for the production frontend baseline (no harness subprocesses).

The JSON-lines stdin channel changes fixtures without adding a production HTTP API.
Stdout contains only readiness/control acknowledgements; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "cargento" / "skills" / "cargento"
sys.path.insert(0, str(SKILL))
from cargento_runtime.aggregate import Application, HarnessSpec  # noqa: E402 - skill runtime path
from cargento_runtime.cli import inject_focus_capability  # noqa: E402 - skill runtime path
from cargento_runtime.config import build_runtime_config  # noqa: E402 - skill runtime path
from cargento_runtime.http_api import CargentoHTTPServer  # noqa: E402 - skill runtime path
from cargento_runtime.sessions import base_session  # noqa: E402 - skill runtime path
from cargento_runtime.state import build_runtime_state  # noqa: E402 - skill runtime path
from cargento_runtime.web.page import load_page  # noqa: E402 - skill runtime path

COHORTS = {"small": 5, "median": 50, "large": 250}
STATES = ("healthy", "empty", "unavailable")
NOW = 1_900_000_000.0
PROJECT = "baseline-project"
CURRENT_SESSION = {"harness": "claude", "sid": "b0000000", "project": PROJECT}


def validate_port(value: int) -> int:
    if type(value) is not int or not 4571 <= value <= 4599:
        raise ValueError("baseline port must be in 4571..4599")
    return value


class FixtureApplication(Application):
    def __init__(self, fixture: Fixture, *args: Any, **kwargs: Any) -> None:
        self.fixture = fixture
        super().__init__(*args, **kwargs)

    def collect(self, *, show_all: bool, notify: bool = True) -> dict[str, Any]:
        # Preserve the production signature but never emit a native notification.
        del notify
        with self.fixture.lock:
            payload = super().collect(show_all=show_all, notify=False)
            payload["baseline_fixture"] = self.fixture.describe()
            return payload


class Fixture:
    def __init__(self, scratch: Path) -> None:
        self.lock = threading.RLock()
        self.cohort = "small"
        self.status = "healthy"
        self.sequence = 0
        self.diagnostics: list[str] = []
        scratch = scratch.resolve()
        scratch.mkdir(parents=True, exist_ok=True)
        config = build_runtime_config(
            environ={
                "HOME": str(scratch),
                "USERPROFILE": str(scratch),
                "CARGENTO_HOME": str(scratch / "state"),
            },
            platform_name=sys.platform,
            os_name=os.name,
            launcher_path=SKILL / "server.py",
            port=4571,
            spacedock_enabled=False,
            tripwires_enabled=False,
            usage_fetch_enabled=False,
            model_calls_disabled=True,
            git_probe_enabled=False,
            focus_enabled=False,
            irreversible_enabled=False,
            ask_enabled=False,
            reach_enabled=False,
            quiet_hours_enabled=False,
            history_enabled=False,
        )
        state = build_runtime_state(config, started=NOW)
        harness = HarnessSpec("claude", "Claude Code", lambda *_: True, self._rows)
        self.application = FixtureApplication(
            self,
            config,
            state,
            (harness,),
            native_notifier=lambda _: "disabled",
            popup_notifier=lambda *_: None,
            diagnostic_sink=self.diagnostics.append,
            clock=lambda: NOW,
        )
        self.assembled_page = load_page()
        # Match the production assembly seam with focus disabled: no capability.
        self.page = inject_focus_capability(self.assembled_page, "")

    def configure(self, *, cohort: str, state: str, sequence: int) -> dict[str, Any]:
        with self.lock:
            if cohort not in COHORTS or state not in STATES:
                raise ValueError("unknown synthetic cohort/state")
            if type(sequence) is not int or sequence <= self.sequence:
                raise ValueError("sequence must be an increasing integer")
            self.cohort, self.status, self.sequence = cohort, state, sequence
            description = self.describe()
        # Use the production invalidation seam, outside the fixture lock. Control
        # acknowledgements occur after invalidation, so the next HTTP GET is fresh.
        self.application.snapshot.clear()
        return description

    def describe(self) -> dict[str, Any]:
        return {
            "cohort": self.cohort,
            "state": self.status,
            "sequence": self.sequence,
            "session_count": COHORTS[self.cohort] if self.status == "healthy" else 0,
            "current_session": CURRENT_SESSION,
            "marker": f"Baseline {self.sequence}",
            "page_sha256": hashlib.sha256(self.page).hexdigest(),
            "page_bytes": len(self.page),
            "assembled_page_sha256": hashlib.sha256(self.assembled_page).hexdigest(),
            "assembled_page_bytes": len(self.assembled_page),
        }

    def _rows(self, *_: Any) -> list[dict[str, Any]]:
        if self.status == "unavailable":
            raise OSError("synthetic store unavailable")
        if self.status == "empty":
            return []
        rows = []
        for index in range(COHORTS[self.cohort]):
            row = base_session("claude", f"b{index:07x}", PROJECT)
            row.update(
                title=f"Baseline {self.sequence} session {index + 1:03d}",
                first_prompt="Implement the synthetic baseline task.",
                last_prompt="Keep the editor draft while refreshing the session list.",
                prompt_at=NOW - 10,
                first_prompt_at=NOW - 60,
                last_activity=NOW - index,
                own_activity=NOW - index,
                started_at=NOW - 120,
                model="synthetic-no-model",
                active=index % 3 == 0,
                state="working" if index % 3 == 0 else "idle",
            )
            rows.append(row)
        return rows

    def server(self, port: int) -> CargentoHTTPServer:
        return CargentoHTTPServer(("127.0.0.1", validate_port(port)), self.application, self.page)

    def control(self, command: Any) -> dict[str, Any]:
        if not isinstance(command, dict) or set(command) != {"cohort", "state", "sequence"}:
            raise ValueError("control requires only cohort, state and sequence")
        return self.configure(**command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4571)
    parser.add_argument("--cohort", choices=COHORTS, default="small")
    parser.add_argument("--state", choices=STATES, default="healthy")
    args = parser.parse_args()
    validate_port(args.port)
    with tempfile.TemporaryDirectory(prefix="cargento-baseline-") as scratch:
        fixture = Fixture(Path(scratch))
        fixture.configure(cohort=args.cohort, state=args.state, sequence=1)
        with fixture.server(args.port) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            print(json.dumps({"ready": True, "port": args.port, **fixture.describe()}), flush=True)
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
