from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .support import LegacyDashboardTestCase, dashboard


class DroidCollectorTest(LegacyDashboardTestCase):
    def test_droid_sessions_from_project_transcripts(self) -> None:
        now = dashboard.time.time()
        iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "proj-x" / "d1d2d3d4.jsonl"
            fp.parent.mkdir(parents=True)
            fp.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_start",
                                "id": "d1d2d3d4",
                                "sessionTitle": "Ship feature",
                                "cwd": "/w/droidproj",
                            }
                        ),
                        json.dumps(
                            {
                                "type": "message",
                                "timestamp": iso,
                                "message": {
                                    "role": "user",
                                    "content": [{"type": "text", "text": "ship it"}],
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )

            with mock.patch.object(dashboard, "FACTORY_PROJECTS", str(tmp)):
                sessions = dashboard.collect_droid(now, 24, False)

        self.assertEqual(1, len(sessions))
        s = sessions[0]
        self.assertEqual("working", s["state"])
        self.assertEqual("w/droidproj", s["project"])  # DRC-3963: <parent>/<basename>
        self.assertEqual("Ship feature", s["title"])
        self.assertEqual("ship it", s["last_prompt"])


class DroidReviewFixTest(unittest.TestCase):
    NOW = 1_700_000_000.0

    def test_a_future_record_does_not_mask_a_fresh_mtime(self) -> None:
        # max(event_ts, mtime) picks the implausible one — a future timestamp
        # is by definition the largest — so rejecting it discarded the good
        # evidence too and an actively-written session read Idle.
        future_iso = "2023-11-15T00:00:00+00:00"  # a day ahead of NOW
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            transcript = project / "s.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "message",
                        "timestamp": future_iso,
                        "message": {"role": "user", "content": "hi"},
                    }
                )
                + "\n"
            )
            os.utime(transcript, (self.NOW, self.NOW))  # written right now
            with mock.patch.object(dashboard, "FACTORY_PROJECTS", str(tmp)):
                fresh = dashboard.collect_droid(self.NOW, 24, False)
                os.utime(transcript, (self.NOW - 100_000, self.NOW - 100_000))
                stale = dashboard.collect_droid(self.NOW, 24, True)

        self.assertEqual("working", fresh[0]["state"], "fresh mtime was masked")
        self.assertEqual("idle", stale[0]["state"], "future record invented activity")


class DroidVerificationFixTest(unittest.TestCase):
    NOW = 1_700_000_000.0
    FUTURE = NOW + 86_400

    def test_a_future_main_file_does_not_mask_a_fresh_subagent(self) -> None:
        # Codex and Gemini collapsed main and subagent mtimes with max() before
        # the freshness test, so a skewed parent hid a genuinely running child.
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2023" / "11" / "14"
            day.mkdir(parents=True)
            main = day / "rollout-main.jsonl"
            main.write_text(
                json.dumps({"type": "session_meta", "payload": {"id": "S", "cwd": "/w"}}) + "\n"
            )
            os.utime(main, (self.FUTURE, self.FUTURE))
            child = day / "rollout-child.jsonl"
            child.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "K",
                            "thread_source": "subagent",
                            "source": {"subagent": {"thread_spawn": {"parent_thread_id": "S"}}},
                            "agent_nickname": "reviewer",
                        },
                    }
                )
                + "\n"
            )
            os.utime(child, (self.NOW, self.NOW))
            with (
                mock.patch.dict(dashboard.STORE_ROOTS, {"codex.sessions": [str(tmp)]}),
                mock.patch.object(dashboard, "CODEX_SESSIONS_DIR", str(tmp)),
            ):
                sessions = dashboard.collect_codex(self.NOW, 24, True)

        self.assertEqual("working", sessions[0]["state"])
        self.assertEqual(["reviewer"], sessions[0]["subagents"])
        self.assertLessEqual(sessions[0]["last_activity"], self.NOW, "skewed mtime displayed")


class CodexPathTest(unittest.TestCase):
    def test_codex_agent_label_uses_the_basename_on_either_separator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout-1.jsonl"
            rollout.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "sess-1",
                            "thread_source": "subagent",
                            "agent_path": "/home/u/agents/reviewer.md",
                        },
                    }
                )
                + "\n"
            )
            self.assertEqual("reviewer.md", dashboard.codex_meta(str(rollout))["agent_label"])

    @unittest.skipUnless(os.name == "nt", "os.path is ntpath only on Windows")
    def test_codex_agent_label_splits_windows_separators(self) -> None:
        # The POSIX case above passes under the old rsplit("/") too, so it
        # could not catch the bug it was written for. Only ntpath splits "\\".
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout-2.jsonl"
            rollout.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "s2",
                            "thread_source": "subagent",
                            "agent_path": r"C:\Users\j\agents\reviewer.md",
                        },
                    }
                )
                + "\n"
            )
            self.assertEqual("reviewer.md", dashboard.codex_meta(str(rollout))["agent_label"])
