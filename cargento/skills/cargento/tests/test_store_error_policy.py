from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import diagnostics
from cargento_runtime import io as runtime_io
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime.collectors import opencode as opencode_collector

from . import test_copilot as copilot_fixtures
from . import test_sqlite_collectors as sqlite_fixtures
from .support import RuntimeTestCase, collect, diagnose, make_runtime, state_of, store_patch


class CopilotUsageDiagnosticTest(RuntimeTestCase):
    @staticmethod
    def _store(root: Path) -> Path:
        now = time.time()
        copilot_fixtures.write_events(
            root,
            "session-state",
            "aaaabbbb-1111",
            datetime.fromtimestamp(now - 5, UTC).isoformat(),
            "fixture prompt",
        )
        copilot_fixtures.write_ledger(root, [("aaaabbbb-1111", 2_000_000_000, now - 60)])
        return root / "session-store.db"

    def _published(self, *, healthy: bool = False, query_failed: bool = False) -> None:
        payload = collect(show_all=True)
        rows = [row for row in payload["sessions"] if row["harness"] == "copilot"]
        self.assertEqual(["aaaabbbb-1111"], [row["sid"] for row in rows])
        self.assertEqual("fixture prompt", rows[0]["last_prompt"])
        self.assertEqual("2.00 AIU" if healthy else None, rows[0]["consumption"])
        if healthy:
            self.assertIsNotNone(rows[0]["model"])
        else:
            self.assertIsNone(rows[0]["model"])
        self.assertEqual(
            [runtime_sessions.UNREAD_TOKENS] if query_failed else [], rows[0]["source_gaps"]
        )
        harness = next(h for h in payload["harnesses"] if h["key"] == "copilot")
        self.assertIsNone(harness["error"])
        self.assertNotIn("store_errors", payload)

    def _diagnostic(self, database: Path, expected: str) -> None:
        report = diagnose()
        self.assertEqual(expected, report["store_errors"].get(str(database)))
        self.assertEqual(expected, state_of().store_errors.get(str(database)))
        self.assertIn(expected, diagnostics.render_diagnosis(report))

    def test_missing_table_and_corruption_keep_their_actual_causes(self) -> None:
        cases = (
            ("missing table", "OperationalError: no such table: assistant_usage_events"),
            ("corrupt file", "DatabaseError: file is not a database"),
        )
        for case, expected in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                database = self._store(Path(tmp))
                if case == "missing table":
                    connection = sqlite3.connect(database)
                    connection.execute("DROP TABLE assistant_usage_events")
                    connection.close()
                else:
                    database.write_bytes(bytes(512))
                with store_patch(COPILOT_DIR=tmp):
                    self._published(query_failed=True)
                    self._diagnostic(database, expected)

    def test_non_sqlite_usage_failures_keep_rows_and_record_the_real_exception(self) -> None:
        for boundary in ("open", "query"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as tmp:
                database = self._store(Path(tmp))
                fault = AttributeError(f"fixture {boundary} broke")
                connection = mock.Mock()
                connection.execute.side_effect = fault
                with (
                    store_patch(COPILOT_DIR=tmp),
                    mock.patch.object(
                        runtime_io,
                        "open_sqlite_read_only",
                        side_effect=fault if boundary == "open" else None,
                        return_value=connection,
                    ),
                ):
                    self._published(query_failed=boundary == "query")
                    self._diagnostic(database, f"AttributeError: fixture {boundary} broke")

    def test_permission_denied_open_remains_diagnosed(self) -> None:
        if os.name == "nt" or os.geteuid() == 0:
            self.skipTest("requires enforced POSIX read permissions")
        with tempfile.TemporaryDirectory() as tmp:
            database = self._store(Path(tmp))
            database.chmod(0o000)
            try:
                with store_patch(COPILOT_DIR=tmp):
                    self._published()
                    self._diagnostic(database, "OperationalError: unable to open database file")
            finally:
                database.chmod(0o600)

    def test_healthy_usage_keeps_figures_and_empty_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._store(Path(tmp))
            with store_patch(COPILOT_DIR=tmp):
                self._published(healthy=True)
                self.assertEqual({}, diagnose()["store_errors"])


class StoreErrorFormatterTest(RuntimeTestCase):
    def test_message_limit_applies_to_sqlite_and_other_exception_classes(self) -> None:
        _, state = make_runtime()
        for error_type in (sqlite3.OperationalError, ValueError, AttributeError):
            for size in (0, 20, 1023, 1024, 1025, 100_000):
                with self.subTest(error_type=error_type.__name__, size=size):
                    message = "測" * size
                    runtime_io.record_store_error(state, "/fixture.db", error_type(message))
                    actual = state.store_errors["/fixture.db"]
                    prefix = f"{error_type.__name__}: "
                    self.assertTrue(actual.startswith(prefix))
                    body = actual[len(prefix) :]
                    self.assertLessEqual(len(body), 1024)
                    if size <= 1024:
                        self.assertEqual(message, body)
                    else:
                        self.assertEqual("測" * 1009 + "... [truncated]", body)

    def test_entry_count_bound_survives_message_clipping(self) -> None:
        _, state = make_runtime(max_cache_entries=2)
        for path in ("first.db", "second.db", "third.db"):
            runtime_io.record_store_error(state, path, ValueError("x" * 100_000))
        self.assertEqual(["second.db", "third.db"], list(state.store_errors))
        self.assertTrue(all(len(value) <= 1036 for value in state.store_errors.values()))

    def test_long_row_error_is_bounded_in_diagnosis_and_stays_out_of_payload(self) -> None:
        millis = int((time.time() - 10) * 1000)
        messages, parts = sqlite_fixtures.SqliteCollectorTest._opencode_turn(
            "broken", millis, "fixture prompt"
        )
        fault = ValueError("PROMPT_START:" + "x" * 100_000 + ":PROMPT_END")
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "opencode.db"
            sqlite_fixtures.SqliteCollectorTest._opencode_db(
                database,
                [
                    ("before", None, "/w/proj", "Before", millis + 1, None),
                    ("broken", None, "/w/proj", "Broken", millis, None),
                    ("after", None, "/w/proj", "After", millis - 1, None),
                ],
                messages=messages,
                parts=parts,
            )
            with (
                store_patch(OPENCODE_DATA=tmp),
                mock.patch.object(opencode_collector, "_prompt_from_parts", side_effect=fault),
            ):
                payload = collect(show_all=True)
                rows = [row for row in payload["sessions"] if row["harness"] == "opencode"]
                self.assertCountEqual(["before", "after"], [row["sid"] for row in rows])
                harness = next(h for h in payload["harnesses"] if h["key"] == "opencode")
                self.assertIsNone(harness["error"])
                self.assertNotIn("store_errors", payload)
                self.assertNotIn("PROMPT_START", str(payload))
                report: dict[str, Any] = diagnose()
                cached = state_of().store_errors[str(database)]
                self.assertEqual(cached, report["store_errors"][str(database)])
                self.assertLessEqual(len(cached), 1036)
                self.assertTrue(cached.startswith("ValueError: PROMPT_START:"))
                self.assertTrue(cached.endswith("... [truncated]"))
                rendered = diagnostics.render_diagnosis(report)
                self.assertIn(cached, rendered)
                self.assertNotIn("PROMPT_END", rendered)
                self.assertNotIn("x" * 1025, rendered)
