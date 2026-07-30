from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from cargento_runtime.collectors import copilot as copilot_collector

from .support import LegacyDashboardTestCase, dashboard


class CopilotCollectorTest(LegacyDashboardTestCase):
    def test_copilot_sessions_are_discovered_and_analyzed(self) -> None:
        now = dashboard.time.time()
        iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
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

            with mock.patch.object(dashboard, "COPILOT_DIR", str(tmp)):
                config, state = dashboard._legacy_runtime()
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
        now = dashboard.time.time()
        iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            self._events(Path(tmp), "history-session-state", "33334444-bbbb", iso, "old session")
            with mock.patch.object(dashboard, "COPILOT_DIR", str(tmp)):
                config, state = dashboard._legacy_runtime()

                self.assertTrue(copilot_collector.discover(config, state))
                sessions = copilot_collector.collect(config, state, now, 24, False)

        self.assertEqual(["33334444-bbbb"], [s["sid"] for s in sessions])
        self.assertEqual("old session", sessions[0]["last_prompt"])

    def test_a_uuid_in_both_stores_reads_from_the_newer_file(self) -> None:
        # The same uuid can exist in both stores after a migration. The newest
        # file wins, so a stale copy cannot mask live activity. Mutation-checked:
        # preferring the older file passed the whole suite.
        now = dashboard.time.time()
        fresh_iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        stale_iso = dashboard.datetime.fromtimestamp(now - 9000, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            sid = "55556666-cccc"
            old = self._events(Path(tmp), "history-session-state", sid, stale_iso, "stale prompt")
            new = self._events(Path(tmp), "session-state", sid, fresh_iso, "live prompt")
            os.utime(old, (now - 9000, now - 9000))
            os.utime(new, (now - 5, now - 5))
            with mock.patch.object(dashboard, "COPILOT_DIR", str(tmp)):
                config, state = dashboard._legacy_runtime()
                sessions = copilot_collector.collect(config, state, now, 24, True)

        self.assertEqual(1, len(sessions), "one uuid must yield one row")
        self.assertEqual("live prompt", sessions[0]["last_prompt"])

    def test_the_cwd_falls_back_to_the_first_line_metadata(self) -> None:
        # An idle session is not analyzed, so its project label can only come
        # from the cached first-line metadata. Mutation-checked: dropping that
        # fallback passed the whole suite and every idle row read "copilot".
        now = dashboard.time.time()
        stale = now - 100_000  # outside the 24-hour window
        iso = dashboard.datetime.fromtimestamp(stale, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            events = self._events(Path(tmp), "session-state", "77778888-dddd", iso, "old work")
            os.utime(events, (stale, stale))
            with mock.patch.object(dashboard, "COPILOT_DIR", str(tmp)):
                config, state = dashboard._legacy_runtime()
                sessions = copilot_collector.collect(config, state, now, 24, True)

        self.assertEqual(1, len(sessions))
        self.assertFalse(sessions[0]["active"], "fixture must be outside the window")
        self.assertEqual("w/p", sessions[0]["project"])
