from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from cargento_runtime.collectors import copilot as copilot_collector

from .support import (
    RuntimeTestCase,
    runtime,
    store_patch,
)


class CopilotCollectorTest(RuntimeTestCase):
    def test_copilot_sessions_are_discovered_and_analyzed(self) -> None:
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "session-state" / "11112222-aaaa" / "events.jsonl"
            events.parent.mkdir(parents=True)
            events.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session.start",
                                "timestamp": iso,
                                "data": {"context": {"cwd": "/w/myproj"}},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "user.message",
                                "timestamp": iso,
                                "data": {"text": "fix the login bug"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "subagent.started",
                                "timestamp": iso,
                                "data": {"id": "a1", "name": "researcher"},
                            }
                        ),
                    ]
                )
                + "\n"
            )

            with store_patch(COPILOT_DIR=str(tmp)):
                config, state = runtime()
                sessions = copilot_collector.collect(config, state, now, 24, False)

        self.assertEqual(1, len(sessions))
        s = sessions[0]
        self.assertEqual("working", s["state"])
        self.assertEqual("w/myproj", s["project"])  # DRC-3963: <parent>/<basename>
        self.assertEqual("fix the login bug", s["last_prompt"])
        self.assertEqual(["researcher"], s["subagents"])

    @staticmethod
    def _events(root: Path, base: str, sid: str, iso: str, prompt: str) -> Path:
        events = root / base / sid / "events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        events.write_text(
            json.dumps(
                {"type": "session.start", "timestamp": iso, "data": {"context": {"cwd": "/w/p"}}}
            )
            + "\n"
            + json.dumps({"type": "user.message", "timestamp": iso, "data": {"text": prompt}})
            + "\n"
        )
        return events

    def test_the_legacy_history_store_is_discovered_and_collected(self) -> None:
        # Copilot moved its sessions between two directories, and the older one
        # is assumed to share the <uuid>/events.jsonl layout. Mutation-checked:
        # dropping history-session-state made those sessions invisible AND
        # undiscoverable, and passed the whole suite.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            self._events(Path(tmp), "history-session-state", "33334444-bbbb", iso, "old session")
            with store_patch(COPILOT_DIR=str(tmp)):
                config, state = runtime()

                self.assertTrue(copilot_collector.discover(config, state))
                sessions = copilot_collector.collect(config, state, now, 24, False)

        self.assertEqual(["33334444-bbbb"], [s["sid"] for s in sessions])
        self.assertEqual("old session", sessions[0]["last_prompt"])

    def test_a_uuid_in_both_stores_reads_from_the_newer_file(self) -> None:
        # The same uuid can exist in both stores after a migration. The newest
        # file wins, so a stale copy cannot mask live activity. Mutation-checked:
        # preferring the older file passed the whole suite.
        now = time.time()
        fresh_iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        stale_iso = datetime.fromtimestamp(now - 9000, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            sid = "55556666-cccc"
            old = self._events(Path(tmp), "history-session-state", sid, stale_iso, "stale prompt")
            new = self._events(Path(tmp), "session-state", sid, fresh_iso, "live prompt")
            os.utime(old, (now - 9000, now - 9000))
            os.utime(new, (now - 5, now - 5))
            with store_patch(COPILOT_DIR=str(tmp)):
                config, state = runtime()
                sessions = copilot_collector.collect(config, state, now, 24, True)

        self.assertEqual(1, len(sessions), "one uuid must yield one row")
        self.assertEqual("live prompt", sessions[0]["last_prompt"])

    def test_the_cwd_falls_back_to_the_first_line_metadata(self) -> None:
        # An idle session is not analyzed, so its project label can only come
        # from the cached first-line metadata. Mutation-checked: dropping that
        # fallback passed the whole suite and every idle row read "copilot".
        now = time.time()
        stale = now - 100_000  # outside the 24-hour window
        iso = datetime.fromtimestamp(stale, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            events = self._events(Path(tmp), "session-state", "77778888-dddd", iso, "old work")
            os.utime(events, (stale, stale))
            with store_patch(COPILOT_DIR=str(tmp)):
                config, state = runtime()
                sessions = copilot_collector.collect(config, state, now, 24, True)

        self.assertEqual(1, len(sessions))
        self.assertFalse(sessions[0]["active"], "fixture must be outside the window")
        self.assertEqual("w/p", sessions[0]["project"])


class CopilotUsageTest(RuntimeTestCase):
    """Copilot's consumption tile: real spend, no limit, windowed on row time."""

    @staticmethod
    def _store(root: Path, rows: list[tuple[int, float]]) -> None:
        """A session-store.db carrying (nano_aiu, epoch) usage rows."""
        root.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(root / "session-store.db")
        con.execute(
            "CREATE TABLE assistant_usage_events ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,"
            " model TEXT, total_nano_aiu INTEGER, created_at TEXT)"
        )
        con.executemany(
            "INSERT INTO assistant_usage_events (session_id, model, total_nano_aiu, created_at)"
            " VALUES ('s', 'gpt-5.6-terra', ?, ?)",
            [(nano, datetime.fromtimestamp(when, UTC).isoformat()) for nano, when in rows],
        )
        con.commit()
        con.close()
        # discover() needs a session-state dir to consider the harness present.
        (root / "session-state" / "abcd").mkdir(parents=True, exist_ok=True)

    def test_aiu_rows_sum_into_one_used_entry(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            # 0.39 AIU + 16.21 AIU, the two models this account actually used.
            self._store(root, [(393_690_000, now - 600), (16_213_200_000, now - 60)])
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                entries = copilot_collector.usage(config, state, now, 24)

        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual("copilot", entry["harness"])
        self.assertEqual("ok", entry["state"])
        self.assertEqual("16.61 AIU", entry["used"])
        # asOf is the newest contributing row, not the collection time.
        self.assertEqual(int(now - 60), entry["asOf"])
        # Consumption has no limit, so it must never claim a window gauge.
        self.assertNotIn("fiveH", entry)
        self.assertNotIn("week", entry)

    def test_rows_outside_the_window_are_excluded(self) -> None:
        # The figure answers "in the last window_hours", so old spend must not
        # inflate it. Without this the number would drift with how much history
        # happened to be retained.
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            self._store(root, [(9_000_000_000, now - 8 * 3600), (1_000_000_000, now - 60)])
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                inside = copilot_collector.usage(config, state, now, 24)
                narrow = copilot_collector.usage(config, state, now, 1)

        self.assertEqual("10.00 AIU", inside[0]["used"])
        self.assertEqual("1.00 AIU", narrow[0]["used"])

    def test_no_rows_in_the_window_publishes_nothing(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            self._store(root, [(5_000_000_000, now - 48 * 3600)])
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                self.assertEqual([], copilot_collector.usage(config, state, now, 24))

    def test_a_missing_or_schemaless_store_is_a_miss_not_an_error(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            (root / "session-state" / "abcd").mkdir(parents=True)
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                # No database file at all.
                self.assertEqual([], copilot_collector.usage(config, state, now, 24))
                # A database with no usage table: schema drift, not a crash.
                con = sqlite3.connect(root / "session-store.db")
                con.execute("CREATE TABLE sessions (id TEXT)")
                con.commit()
                con.close()
                self.assertEqual([], copilot_collector.usage(config, state, now, 24))

    def test_malformed_rows_are_skipped_without_poisoning_the_sum(self) -> None:
        now = time.time()
        stamp = datetime.fromtimestamp(now - 60, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            self._store(root, [(2_000_000_000, now - 60)])
            con = sqlite3.connect(root / "session-store.db")
            con.executemany(
                "INSERT INTO assistant_usage_events (session_id, model, total_nano_aiu, created_at)"
                " VALUES ('s', 'm', ?, ?)",
                [
                    (None, stamp),  # null amount
                    ("not a number", stamp),  # wrong type
                    (-5_000_000_000, stamp),  # negative
                    (1_000_000_000, "not a timestamp"),  # unparseable time
                ],
            )
            con.commit()
            con.close()
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                entries = copilot_collector.usage(config, state, now, 24)

        # Only the one well-formed row counts.
        self.assertEqual("2.00 AIU", entries[0]["used"])
