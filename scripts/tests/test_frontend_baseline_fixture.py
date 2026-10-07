"""Synthetic frontend fixtures use the real application without external services."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import frontend_baseline_fixture as baseline


class BaselineFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="cargento-baseline-test-")
        self.addCleanup(self.scratch.cleanup)
        self.fixture = baseline.Fixture(Path(self.scratch.name))

    def test_real_schema_sizes_identity_and_isolation(self) -> None:
        for sequence, (cohort, expected) in enumerate(
            {"small": 5, "median": 50, "large": 250}.items(), 1
        ):
            with self.subTest(cohort=cohort):
                self.fixture.configure(cohort=cohort, state="healthy", sequence=sequence)
                data = self.fixture.application.collect(show_all=True)
                self.assertEqual(expected, len(data["sessions"]))
                self.assertEqual(expected, data["baseline_fixture"]["session_count"])
                self.assertEqual("b0000000", data["baseline_fixture"]["current_session"]["sid"])
                self.assertTrue(
                    all(row["title"].startswith(f"Baseline {sequence}") for row in data["sessions"])
                )
                self.assertTrue(
                    all("tasks" in row and "subagents" in row for row in data["sessions"])
                )
        config = self.fixture.application.config
        self.assertTrue(config.model_calls_disabled)
        self.assertFalse(config.usage_fetch_enabled)
        self.assertFalse(config.focus_enabled)
        self.assertFalse(config.history_enabled)
        self.assertTrue(
            config.state_dir.resolve().is_relative_to(Path(self.scratch.name).resolve())
        )

    def test_empty_and_unavailable_are_different_production_states(self) -> None:
        self.fixture.configure(cohort="small", state="empty", sequence=2)
        empty = self.fixture.application.collect(show_all=True)
        self.fixture.configure(cohort="small", state="unavailable", sequence=3)
        unavailable = self.fixture.application.collect(show_all=True)
        self.assertEqual([], empty["sessions"])
        self.assertEqual([], unavailable["sessions"])
        self.assertIsNone(empty["harnesses"][0]["error"])
        self.assertIsNotNone(unavailable["harnesses"][0]["error"])

    def test_controls_are_strict_and_sequence_monotonic(self) -> None:
        for command in (
            {"cohort": "real", "state": "healthy", "sequence": 1},
            {"cohort": "small", "state": "online", "sequence": 1},
            {"cohort": "small", "state": "healthy", "sequence": True},
            {"cohort": "small", "state": "healthy", "sequence": 0},
        ):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.fixture.control(command)
        self.fixture.configure(cohort="small", state="healthy", sequence=1)
        with self.assertRaises(ValueError):
            self.fixture.configure(cohort="small", state="healthy", sequence=1)
        for port in (4553, 4563, 4567, 4570, 4600):
            with self.subTest(port=port), self.assertRaises(ValueError):
                baseline.validate_port(port)

    def test_fixture_command_help_and_rejects_owner_port(self) -> None:
        executable = str(Path(baseline.__file__))
        help_result = subprocess.run(
            [sys.executable, executable, "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        result = subprocess.run(
            [sys.executable, executable, "--port", "4553"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("4571..4599", result.stderr)
        self.assertNotIn('"ready"', result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_node_command_help_and_rejects_owner_port_before_launch(self) -> None:
        executable = str(Path(baseline.__file__).with_name("frontend_baseline.mjs"))
        node = shutil.which("node")
        assert node is not None
        help_result = subprocess.run(
            [node, executable, "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        result = subprocess.run(
            [
                node,
                executable,
                "--output",
                str(Path(self.scratch.name) / "unused.json"),
                "--chrome",
                "never-launched",
                "--port",
                "4553",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("4571..4599", result.stderr)
        self.assertFalse((Path(self.scratch.name) / "unused.json").exists())

    def test_actual_http_page_and_data_and_busy_port_refusal(self) -> None:
        # This listener is ours, and proves the fixture never steals a busy port.
        with socket.socket() as occupied:
            for port in range(4571, 4600):
                try:
                    occupied.bind(("127.0.0.1", port))
                    occupied.listen()
                    break
                except OSError:
                    continue
            else:
                self.skipTest("no spare baseline port")
            with self.assertRaises(OSError):
                self.fixture.server(port)
        server = self.fixture.server(port)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        self.fixture.configure(cohort="small", state="healthy", sequence=1)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/data", timeout=2) as response:
            data = json.load(response)
        self.assertEqual(1, data["baseline_fixture"]["sequence"])
        self.fixture.configure(cohort="median", state="healthy", sequence=2)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/data", timeout=2) as response:
            data = json.load(response)
        self.assertEqual(2, data["baseline_fixture"]["sequence"])
        self.assertEqual(50, len(data["sessions"]))
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            self.assertEqual(self.fixture.page, response.read())
        self.assertEqual(64, len(self.fixture.describe()["page_sha256"]))


if __name__ == "__main__":
    unittest.main()
