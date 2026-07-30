from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

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
                sessions = dashboard.collect_copilot(now, 24, False)

        self.assertEqual(1, len(sessions))
        s = sessions[0]
        self.assertEqual("working", s["state"])
        self.assertEqual("w/myproj", s["project"])  # DRC-3963: <parent>/<basename>
        self.assertEqual("fix the login bug", s["last_prompt"])
        self.assertEqual(["researcher"], s["subagents"])
