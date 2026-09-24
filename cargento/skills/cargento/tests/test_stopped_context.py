"""A Claude Code session that stopped a turn keeps its checks and files (DRC-4705).

On a machine with Cargento's hooks installed, a `Stop` becomes an idle overlay, and that overlay
sets `active: False` to mean "no turn running" (`events.reduce_overlays`). The project context
read the same field as "outside the window" and dropped the row, so about three seconds after
the stop every check the session ran and every file it wrote left the page and the reading.
These tests stop a real fixture session through the overlay path and ask what the reader still
sees.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from cargento_runtime import events, http_api, observer, project_context, reading
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

from .test_claude_checks import INFO, SHORT, SID, START, Transcript

NEIGHBOUR = "7b2d0f18-0000-4000-8000-000000000002"
NOW = START.timestamp() + 3600


class _StoppedSessionCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        cwd = root / "work" / "billing"
        cwd.mkdir(parents=True)
        projects = root / "claude" / "projects" / "-work-billing"
        self.config = build_runtime_config(
            environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=root / "server.py",
            store_root_overrides={"claude.projects": str(root / "claude" / "projects")},
        )
        patcher = mock.patch.object(observer.CodexGoalModel, "__call__", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        stopped = Transcript(cwd)
        stopped.prompt("Add retry with backoff to the webhook handler.")
        stopped.write(str(cwd / "src" / "retry.js"))
        stopped.bash("node --test 2>&1 | tail -3", f"{INFO} tests 5\n{INFO} pass 5", is_error=False)
        stopped.save(projects / f"{SID}.jsonl")

        neighbour = Transcript(cwd)
        neighbour.prompt("Tighten the invoice rounding.")
        neighbour.bash("python3 -m pytest tests", "1 failed, 4 passed in 0.31s", is_error=True)
        for row in neighbour.rows:
            row["sessionId"] = NEIGHBOUR
        neighbour.save(projects / f"{NEIGHBOUR}.jsonl")

    @staticmethod
    def row(sid: str) -> dict[str, Any]:
        return {
            "project": "billing",
            "harness": "claude",
            "sid": sid,
            "state": "working",
            "last_activity": NOW - 30,
            "active": True,
        }

    def stopped_row(self) -> dict[str, Any]:
        """The row after a `Stop` hook, once the idle dwell has passed."""
        stop = events.Event(
            harness="claude",
            event="turn_stopped",
            sid=SHORT,
            session_id=SID,
            timestamp=NOW - 10,
            arrival_seq=1,
        )
        overlay = events.overlay_for(stop, config=self.config)
        assert overlay is not None
        row = self.row(SHORT)
        events.apply_patch(
            row,
            events.reduce_overlays(
                [overlay], now=NOW - 10 + self.config.overlay_idle_dwell_sec + 0.5
            ),
        )
        # The overlay really said what the page reads it as, or this proves nothing.
        self.assertEqual(
            ("idle", False, events.ACQUISITION_EVENT),
            (row["state"], row["active"], row["acquisition"]),
        )
        return row

    def collect(self, rows: list[dict[str, Any]], focus: str) -> dict[str, Any]:
        state = build_runtime_state(self.config, started=NOW)
        return project_context.collect(
            self.config, state, rows, "billing", now=NOW, focus=("claude", focus)
        )

    @staticmethod
    def reports(context: dict[str, Any], sid: str) -> list[tuple[str, str]]:
        return sorted(
            (fact["subject"], fact["summary"])
            for fact in context["semantic"]["facts"]
            if fact.get("type") == "tool_report" and fact["source_session"]["sid"] == sid
        )


class ASessionThatStoppedATurnKeepsItsChecksTest(_StoppedSessionCase):
    def test_the_focused_record_still_holds_the_check_it_ran_and_the_file_it_wrote(self) -> None:
        context = self.collect([self.stopped_row(), self.row(NEIGHBOUR[:8])], SHORT)
        kinds = {event["kind"] for event in context["events"] if event.get("sid") == SHORT}
        self.assertIn("check_run", kinds)
        self.assertEqual(
            [("check", "node --test 2>&1"), ("write", "src/retry.js")],
            self.reports(context, SHORT),
        )

    def test_a_neighbouring_sessions_record_is_the_same_whether_or_not_it_stopped(self) -> None:
        neighbour = NEIGHBOUR[:8]
        running = self.collect([self.row(SHORT), self.row(neighbour)], neighbour)
        stopped = self.collect([self.stopped_row(), self.row(neighbour)], neighbour)
        self.assertTrue(self.reports(running, neighbour))
        self.assertEqual(self.reports(running, neighbour), self.reports(stopped, neighbour))

    def test_the_reading_route_reads_the_stopped_sessions_check(self) -> None:
        row = self.stopped_row()
        state = build_runtime_state(self.config, started=NOW)
        handler = SimpleNamespace(
            server=SimpleNamespace(
                application=SimpleNamespace(config=self.config, state=state, clock=lambda: NOW)
            )
        )
        facts = http_api._RequestHandler._session_facts(handler, row)  # type: ignore[arg-type]
        prompts: list[str] = []

        def model(prompt: str, **_kw: Any) -> tuple[str, str]:
            prompts.append(prompt)
            return "{}", "ok"

        assessment, why, _spent = reading.produce(
            self.config,
            row,
            [{"n": 1, "at": NOW - 5, "window_start": NOW - 3600, "goal": "add retry", "lines": ()}],
            facts,
            now=NOW,
            stamp_text="read",
            model=model,
            tool_output=reading.ToolOutput(destination="Anthropic", label="Claude Code"),
            read_lines=True,
            admit_turn_stop=True,
        )
        self.assertEqual("", why)
        assert assessment is not None
        self.assertEqual(reading.SCOPE_LAST_TURN, assessment["scope"])
        self.assertIn("node --test", prompts[0])


class EveryProjectContextGateKeepsTheStoppedSessionTest(_StoppedSessionCase):
    """The same predicate at the other two sites that read `active` as the window."""

    def test_the_attention_scan_still_reads_the_stopped_session(self) -> None:
        scanned, _status = project_context._attention_context_sessions(
            [self.stopped_row()], "billing"
        )
        self.assertEqual([SHORT], [row["sid"] for row in scanned])

    def test_the_peer_gate_scan_still_reads_the_stopped_session(self) -> None:
        asked: list[str] = []

        def resolve(_config: Any, _state: Any, _harness: str, sid: str) -> None:
            asked.append(sid)

        state = build_runtime_state(self.config, started=NOW)
        with mock.patch.object(observer, "resolve_transcript", resolve):
            project_context._project_peer_gate_context(
                self.config,
                state,
                [self.stopped_row(), self.row(NEIGHBOUR[:8])],
                "billing",
                ("claude", NEIGHBOUR[:8]),
            )
        self.assertEqual([SHORT], asked)

    def test_a_row_out_of_the_window_is_still_left_out(self) -> None:
        # Neither a live turn nor a hook-stopped one: the collector's own reading stands.
        aged = {**self.row(SHORT), "active": False, "state": "idle"}
        scanned, _status = project_context._attention_context_sessions([aged], "billing")
        self.assertEqual([], scanned)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
