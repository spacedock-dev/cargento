"""Qualification errors stay useful and private, with every attempt charged."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cargento/skills/cargento"))
import abstention_ledger
import score_abstention
from cargento_runtime import reading

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig


class QualificationDiagnostics(unittest.TestCase):
    def test_a_failed_launch_keeps_an_identity_bound_private_error_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = types.SimpleNamespace(
                state_dir=root / "state", claude_reading_model="claude-sonnet-5-5"
            )
            secret = "private prompt sk-ant-api03-should-never-be-recorded"  # noqa: S105 - synthetic leak needle

            def runner(_argv: Any, **kwargs: Any) -> Any:
                kwargs["stdout"].write(b"Not logged in. Please run /login. " + secret.encode())
                return types.SimpleNamespace(returncode=1)

            model = reading.ClaudeReadingModel(
                cast("RuntimeConfig", cfg), runner=runner, binary_resolver=lambda _: "/fake/claude"
            )
            paths = tuple(
                str(root / f"never-{n}.json") for n in range(abstention_ledger.MAX_GRANTS)
            )
            with mock.patch.multiple(
                abstention_ledger,
                CONTINUATION_PATHS=paths,
                CLAUDE_SUMMARY_PATH=str(root / "never-summary.json"),
            ):
                ledger = abstention_ledger.Ledger(
                    str(root / "ledger.json"),
                    producer="claude",
                    cap=28,
                    marks_digest="a" * 64,
                    inputs_digest="b" * 64,
                    cases_digest="c" * 64,
                )
                charged = score_abstention._Charged(ledger, "d" * 16, model)
                charged.diagnostics_path = str(root / "diagnostics")
                self.assertEqual(("", "failed"), charged(secret, output_cap_bytes=8192))
                self.assertEqual(1, ledger.used())
                receipt = root / "diagnostics" / f"{charged.charge_id}.json"
                self.assertTrue(receipt.is_file(), "failed launch must retain its actual reason")
                value = json.loads(receipt.read_bytes())
                self.assertEqual(charged.charge_id, value["charge_id"])
                self.assertEqual("login-required", value["diagnostic"]["reason"])
                self.assertEqual(1, value["diagnostic"]["returncode"])
                self.assertNotIn(secret, receipt.read_text())
                if os.name != "nt":
                    self.assertEqual(0o600, receipt.stat().st_mode & 0o777)
                    self.assertEqual(0o700, receipt.parent.stat().st_mode & 0o777)

    def test_an_unprivate_diagnostic_directory_refuses_before_spending(self) -> None:

        if os.name == "nt":
            self.skipTest("POSIX private permission modes")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = types.SimpleNamespace(
                state_dir=root / "state", claude_reading_model="claude-sonnet-5-5"
            )
            calls: list[str] = []

            def runner(_argv: Any, **_kwargs: Any) -> Any:
                calls.append("launched")
                return types.SimpleNamespace(returncode=0)

            model = reading.ClaudeReadingModel(
                cast("RuntimeConfig", cfg), runner=runner, binary_resolver=lambda _: "/fake/claude"
            )
            paths = tuple(
                str(root / f"never-{n}.json") for n in range(abstention_ledger.MAX_GRANTS)
            )
            with mock.patch.multiple(
                abstention_ledger,
                CONTINUATION_PATHS=paths,
                CLAUDE_SUMMARY_PATH=str(root / "never-summary.json"),
            ):
                ledger = abstention_ledger.Ledger(
                    str(root / "ledger.json"),
                    cap=28,
                    producer="claude",
                    marks_digest="a" * 64,
                    inputs_digest="b" * 64,
                    cases_digest="c" * 64,
                )
                diagnostic_dir = root / "diagnostics"
                diagnostic_dir.mkdir(mode=0o755)
                diagnostic_dir.chmod(0o755)
                charged = score_abstention._Charged(
                    ledger, "d" * 16, model, diagnostics_path=str(diagnostic_dir)
                )
                with self.assertRaises(abstention_ledger.LedgerError):
                    charged("private prompt", output_cap_bytes=8192)
                self.assertEqual([], calls)
                self.assertEqual(0, ledger.used())

    def test_an_unwritable_private_directory_refuses_before_spending(self) -> None:

        if os.name == "nt":
            self.skipTest("POSIX private permission modes")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = types.SimpleNamespace(
                state_dir=root / "state", claude_reading_model="claude-sonnet-5-5"
            )
            calls: list[str] = []

            def runner(_argv: Any, **_kwargs: Any) -> Any:
                calls.append("launched")
                return types.SimpleNamespace(returncode=0)

            model = reading.ClaudeReadingModel(
                cast("RuntimeConfig", cfg), runner=runner, binary_resolver=lambda _: "/fake/claude"
            )
            paths = tuple(
                str(root / f"never-{n}.json") for n in range(abstention_ledger.MAX_GRANTS)
            )
            with mock.patch.multiple(
                abstention_ledger,
                CONTINUATION_PATHS=paths,
                CLAUDE_SUMMARY_PATH=str(root / "never-summary.json"),
            ):
                ledger = abstention_ledger.Ledger(
                    str(root / "ledger.json"),
                    cap=28,
                    producer="claude",
                    marks_digest="a" * 64,
                    inputs_digest="b" * 64,
                    cases_digest="c" * 64,
                )
                diagnostic_dir = root / "diagnostics"
                diagnostic_dir.mkdir(mode=0o500)
                diagnostic_dir.chmod(0o500)
                charged = score_abstention._Charged(
                    ledger, "d" * 16, model, diagnostics_path=str(diagnostic_dir)
                )
                with self.assertRaises(abstention_ledger.LedgerError):
                    charged("private prompt", output_cap_bytes=8192)
                diagnostic_dir.chmod(0o700)
                self.assertEqual([], calls)
                self.assertEqual(0, ledger.used())

    def test_a_denied_write_probe_refuses_before_spending(self) -> None:

        if os.name == "nt":
            self.skipTest("POSIX private permission modes")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = types.SimpleNamespace(
                state_dir=root / "state", claude_reading_model="claude-sonnet-5-5"
            )
            calls: list[str] = []

            def runner(_argv: Any, **_kwargs: Any) -> Any:
                calls.append("launched")
                return types.SimpleNamespace(returncode=0)

            model = reading.ClaudeReadingModel(
                cast("RuntimeConfig", cfg), runner=runner, binary_resolver=lambda _: "/fake/claude"
            )
            paths = tuple(
                str(root / f"never-{n}.json") for n in range(abstention_ledger.MAX_GRANTS)
            )
            with mock.patch.multiple(
                abstention_ledger,
                CONTINUATION_PATHS=paths,
                CLAUDE_SUMMARY_PATH=str(root / "never-summary.json"),
            ):
                ledger = abstention_ledger.Ledger(
                    str(root / "ledger.json"),
                    cap=28,
                    producer="claude",
                    marks_digest="a" * 64,
                    inputs_digest="b" * 64,
                    cases_digest="c" * 64,
                )
                diagnostic_dir = root / "diagnostics"
                diagnostic_dir.mkdir(mode=0o700)
                diagnostic_dir.chmod(0o700)
                charged = score_abstention._Charged(
                    ledger, "d" * 16, model, diagnostics_path=str(diagnostic_dir)
                )
                real_mkstemp = tempfile.mkstemp

                def denied_probe(*args: Any, **kwargs: Any) -> Any:
                    if Path(kwargs.get("dir", "/")) == diagnostic_dir:
                        raise PermissionError("synthetic denied ACL")
                    return real_mkstemp(*args, **kwargs)

                with (
                    mock.patch.object(tempfile, "mkstemp", side_effect=denied_probe),
                    self.assertRaises(abstention_ledger.LedgerError),
                ):
                    charged("private prompt", output_cap_bytes=8192)
                diagnostic_dir.chmod(0o700)
                self.assertEqual([], calls)
                self.assertEqual(0, ledger.used())

    def test_an_error_receipt_cannot_replace_an_existing_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            charged = score_abstention._Charged(
                mock.Mock(), "d" * 16, mock.Mock(), diagnostics_path=str(root / "diagnostics")
            )
            charged.diagnostic = {"reason": "unknown"}
            charged._write_diagnostic("a" * 32, "b" * 64)
            receipt = root / "diagnostics" / ("a" * 32 + ".json")
            before = receipt.read_bytes()
            charged.diagnostic = {"reason": "login-required"}
            with self.assertRaises(abstention_ledger.LedgerError):
                charged._write_diagnostic("a" * 32, "b" * 64)
            self.assertEqual(before, receipt.read_bytes())
