"""Launch records are observations, never proof that a process is running."""

from __future__ import annotations

import datetime as dt
import json
import unittest
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from cargento_runtime import levels, live_estimate, project_context, reading, records
from cargento_runtime.state import build_runtime_state

from .test_claude_checks import START, ClaudeChecksTestCase
from .test_levels import check, evidence, intent, scan
from .test_live_estimate import saved_row


class DelegatedWorkLaunchFacts(ClaudeChecksTestCase):
    def launches(self) -> list[dict[str, Any]]:
        return [row for row in self.read()[0] if row["kind"] == "background_launch"]

    def test_shell_background_forms_have_timed_facts(self) -> None:
        for command, extra in [
            ("worker", {"run_in_background": True}),
            ("nohup worker &", {}),
            ("worker &", {}),
        ]:
            with self.subTest(command=command):
                self.session.bash(command, "", **extra)
        self.assertEqual(3, len(self.launches()))
        self.assertTrue(all(row["at"] > 0 for row in self.launches()))
        self.assertTrue(all(row["subject"] == "launch" for row in self.launches()))

    def test_agent_and_monitor_launch_without_publishing_the_task(self) -> None:
        for tool in ("Agent", "Monitor"):
            self.session.call(tool, {"run_in_background": True, "prompt": "PRIVATE_TASK_WORDS"})
        self.assertEqual(2, len(self.launches()))
        self.assertNotIn("PRIVATE_TASK_WORDS", str(self.launches()))

    def test_completed_notification_pairs_by_tool_id(self) -> None:
        call = self.session.bash(
            "worker", "Command running in background with ID: b1", run_in_background=True
        )
        self.session._entry(
            "user",
            [
                {
                    "type": "text",
                    "text": f"<task-notification><task-id>b1</task-id><tool-use-id>{call}</tool-use-id><status>completed</status><summary>PRIVATE_OUTPUT</summary></task-notification>",
                }
            ],
        )
        launch = self.launches()[0]
        self.assertIsNotNone(launch["completed_at"])
        self.assertGreater(launch["completed_at"], launch["at"])
        self.assertEqual(0, self.read()[1]["background_unpaired"])
        self.assertNotIn("PRIVATE_OUTPUT", str(launch))

    def test_running_task_output_does_not_complete_a_launch(self) -> None:
        self.session.bash("worker", run_in_background=True)
        read = self.session.call("TaskOutput", {"task_id": "b1"})
        self.session.result(
            read, "PRIVATE_OUTPUT", tool_use_result={"task": {"id": "b1", "status": "running"}}
        )
        self.assertEqual(1, self.read()[1]["background_unpaired"])

    def test_notification_is_not_a_person_direction(self) -> None:
        self.assertTrue(
            records.injected_prompt(
                "<task-notification><status>completed</status></task-notification>", "claude"
            )
        )

    def test_launch_summary_has_absence_and_quiet_threshold(self) -> None:
        self.session.bash("worker &")
        self.session.save(self.path)
        result = project_context.delegated_work_published(
            self.config, str(self.path), own_activity=0, now=10**10
        )
        self.assertEqual(1, result["delegated_unpaired"])
        self.assertIsNotNone(result["delegated_quiet_since"])
        self.assertEqual("unattributed", result["delegated_visibility"])

    def test_notification_pairs_task_id_from_launch_result(self) -> None:
        call = self.session.call("Bash", {"command": "worker", "run_in_background": True})
        self.session.result(call, "Started", tool_use_result={"backgroundTaskId": "b1"})
        self.session._entry(
            "user",
            [
                {
                    "type": "text",
                    "text": "<task-notification><task-id>b1</task-id><status>completed</status></task-notification>",
                }
            ],
        )
        self.assertEqual(0, self.read()[1]["background_unpaired"])

    def test_terminal_task_output_pairs_but_does_not_publish_output(self) -> None:
        call = self.session.call("Bash", {"command": "worker", "run_in_background": True})
        self.session.result(call, "Started", tool_use_result={"backgroundTaskId": "b1"})
        read = self.session.call("TaskOutput", {"task_id": "b1"})
        self.session.result(
            read, "PRIVATE_OUTPUT", tool_use_result={"task": {"id": "b1", "status": "completed"}}
        )
        self.assertEqual(0, self.read()[1]["background_unpaired"])
        self.assertNotIn("PRIVATE_OUTPUT", str(self.launches()))

    def test_unrelated_notification_cannot_complete_a_launch(self) -> None:
        self.session.bash("worker &")
        self.session._entry(
            "user",
            [
                {
                    "type": "text",
                    "text": "<task-notification><task-id>different</task-id><status>completed</status></task-notification>",
                }
            ],
        )
        self.assertEqual(1, self.read()[1]["background_unpaired"])

    def test_rejected_agent_is_no_launch(self) -> None:
        call = self.session.call("Agent", {"run_in_background": True})
        self.session.result(call, "Rejected", is_error=True)
        self.assertEqual([], self.launches())

    def test_nohup_alone_is_not_a_background_launch(self) -> None:
        self.session.bash("nohup worker")
        self.assertEqual([], self.launches())

    def test_summary_is_measured_zero_only_when_a_transcript_was_read(self) -> None:
        self.session.save(self.path)
        measured = project_context.delegated_work_published(
            self.config, str(self.path), own_activity=0, now=10**10
        )
        absent = project_context.delegated_work_published(
            self.config, None, own_activity=0, now=10**10
        )
        self.assertEqual(0, measured["delegated_launches"])
        self.assertIsNone(absent["delegated_launches"])

    def test_summary_timer_advances_without_rescanning(self) -> None:
        self.session.bash("worker &")
        self.session.save(self.path)
        state = build_runtime_state(self.config, started=0)
        activity = self.launches()[0]["at"] + 10
        before = project_context.delegated_work_published(
            self.config, str(self.path), own_activity=activity, now=activity + 1799, state=state
        )
        after = project_context.delegated_work_published(
            self.config, str(self.path), own_activity=activity, now=activity + 1800, state=state
        )
        self.assertIsNone(before["delegated_quiet_since"])
        self.assertEqual(activity, after["delegated_quiet_since"])
        self.assertEqual(1, len(state.delegated_work_cache))

    def test_a_later_person_turn_does_not_raise_last_turn_quiet(self) -> None:
        self.session.bash("worker &")
        self.session.prompt("Start a separate task.")
        self.session.save(self.path)
        row = project_context.delegated_work_published(
            self.config, str(self.path), own_activity=0, now=10**10
        )
        self.assertIsNone(row["delegated_quiet_since"])

    def test_failed_read_does_not_publish_a_measured_zero(self) -> None:
        row = project_context.delegated_work_published(
            self.config, str(self.path), own_activity=0, now=10**10
        )
        self.assertIsNone(row["delegated_launches"])
        self.assertEqual("partial", row["delegated_visibility"])

    def test_no_more_flag_is_invented_by_completed_launches(self) -> None:
        for _index in range(13):
            call = self.session.bash("worker &")
            self.session._entry(
                "user",
                [
                    {
                        "type": "text",
                        "text": f"<task-notification><tool-use-id>{call}</tool-use-id><status>completed</status></task-notification>",
                    }
                ],
            )
        self.assertEqual(0, self.read()[1]["more"])

    def test_semantic_fact_keeps_launch_times_and_count(self) -> None:
        self.session.bash("worker &")
        source = self.launches()[0]
        fact = project_context._semantic_fact_from_event(
            source, "background_launch", "tool_report", ""
        )
        self.assertEqual("tool_report", fact["type"])
        self.assertEqual(1, fact["count"])
        self.assertEqual(source["last_activity_at"], fact["last_activity_at"])

    def test_launch_is_never_sent_as_model_evidence_of_work(self) -> None:
        self.session.bash("worker &")
        source = self.launches()[0]
        fact = project_context._semantic_fact_from_event(
            source, "background_launch", "tool_report", ""
        )
        self.assertEqual(
            (), reading.build_ledger([fact], "claude", self.path.stem[:8], tool_output={})
        )

    def test_agent_notification_result_is_terminal_without_status(self) -> None:
        call = self.session.call("Agent", {"run_in_background": True})
        self.session.result(call, "Started", tool_use_result={"agentId": "a1"})
        self.session._entry(
            "user",
            [
                {
                    "type": "text",
                    "text": "<task-notification><task-id>a1</task-id><result>PRIVATE_OUTPUT</result></task-notification>",
                }
            ],
        )
        self.assertEqual(0, self.read()[1]["background_unpaired"])
        self.assertNotIn("PRIVATE_OUTPUT", str(self.launches()))

    def test_named_child_activity_is_used_without_its_words(self) -> None:
        call = self.session.call("Agent", {"run_in_background": True})
        self.session.result(call, "Started", tool_use_result={"agentId": "a1"})
        self.session.save(self.path)
        child = self.path.with_suffix("") / "subagents" / "agent-a1.jsonl"
        child.parent.mkdir(parents=True)
        at = START + dt.timedelta(minutes=10)
        child.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "agentId": "a1",
                    "isSidechain": True,
                    "timestamp": at.isoformat(),
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "PRIVATE_CHILD_WORDS"}],
                    },
                }
            )
            + "\n"
        )
        state = build_runtime_state(self.config, started=0)
        row = project_context.delegated_work_published(
            self.config, str(self.path), own_activity=0, now=at.timestamp() + 60, state=state
        )
        self.assertEqual(at.timestamp(), row["delegated_last_activity_at"])
        self.assertIsNone(row["delegated_quiet_since"])
        self.assertEqual("linked", row["delegated_visibility"])
        self.assertNotIn("PRIVATE_CHILD_WORDS", str(row))

    def test_live_replay_refreshes_a_notification_with_no_new_call(self) -> None:
        call = self.session.bash("worker &")
        self.session.bash("pytest", "2 passed")
        self.session.save(self.path)
        before = live_estimate.for_session(
            self.config, saved_row(), str(self.path), [], floor=None, now=10**10
        )
        self.assertIn(levels.REASON_BACKGROUND_RUN, before["reasons"])
        self.session._entry(
            "user",
            [
                {
                    "type": "text",
                    "text": f"<task-notification><tool-use-id>{call}</tool-use-id><status>completed</status></task-notification>",
                }
            ],
        )
        self.session.save(self.path)
        after = live_estimate.for_session(
            self.config, saved_row(), str(self.path), [], floor=None, now=10**10
        )
        self.assertNotIn(levels.REASON_BACKGROUND_RUN, after["reasons"])

    def child_rows(self, name: str, rows: list[dict[str, Any]]) -> Path:
        child = self.path.with_suffix("") / "subagents" / name
        child.parent.mkdir(parents=True, exist_ok=True)
        child.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        return child

    def notification(self, call_id: str, *, sidechain: bool) -> dict[str, Any]:
        return {
            "type": "user",
            "isSidechain": sidechain,
            "timestamp": (START + dt.timedelta(minutes=2)).isoformat(),
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"<task-notification><tool-use-id>{call_id}</tool-use-id><status>completed</status></task-notification>",
                    }
                ],
            },
        }

    def test_collector_supplied_compaction_cannot_replace_parent_launch(self) -> None:
        self.session.bash("worker &")
        self.session.save(self.path)
        copied = dict(self.session.rows[1], isSidechain=True)
        child = self.child_rows("agent-acompact-example.jsonl", [copied])
        row = project_context.delegated_work_published(
            self.config, str(self.path), own_activity=0, now=10**10, child_paths=[str(child)]
        )
        self.assertEqual(1, row["delegated_launches"])
        self.assertEqual(1, row["delegated_unpaired"])
        self.assertIsNotNone(row["delegated_quiet_since"])

    def test_child_own_completion_retires_only_its_launch(self) -> None:
        call = self.session.bash("worker &")
        self.session.save(self.path)
        copied = dict(self.session.rows[1], isSidechain=True)
        self.child_rows("agent-acde.jsonl", [copied, self.notification(call, sidechain=True)])
        tally = project_context._claude_tally(self.config, str(self.path))
        self.assertEqual(2, len(tally.launches))
        self.assertEqual(1, tally.scan["background_unpaired"])
        self.assertIsNone(tally.launches[call]["completed_at"])

    def test_sibling_completion_cannot_complete_another_stream(self) -> None:
        call = self.session.bash("worker &")
        copied = dict(self.session.rows[1], isSidechain=True)
        self.session.rows = self.session.rows[:1]
        self.session.save(self.path)
        self.child_rows("agent-acde.jsonl", [copied, self.notification(call, sidechain=True)])
        self.child_rows("agent-bcde.jsonl", [copied])
        tally = project_context._claude_tally(self.config, str(self.path))
        self.assertEqual(2, len(tally.launches))
        self.assertEqual(1, tally.scan["background_unpaired"])

    def test_child_rejected_result_cannot_reject_parent_launch(self) -> None:
        call = self.session.call("Agent", {"run_in_background": True})
        copied = dict(self.session.rows[1], isSidechain=True)
        self.session.result(call, "Rejected", is_error=True)
        rejected = dict(self.session.rows[2], isSidechain=True)
        self.session.rows = self.session.rows[:2]
        self.session.save(self.path)
        self.child_rows("agent-acde.jsonl", [copied, rejected])
        tally = project_context._claude_tally(self.config, str(self.path))
        self.assertEqual(1, len(tally.launches))
        self.assertIn(call, tally.launches)

    def test_child_launch_completion_clears_the_floor(self) -> None:
        call = self.session.bash("worker &")
        copied = dict(self.session.rows[1], isSidechain=True)
        self.session.rows = self.session.rows[:1]
        self.session.save(self.path)
        self.child_rows("agent-acde.jsonl", [copied, self.notification(call, sidechain=True)])
        self.assertEqual(0, self.read()[1]["background_unpaired"])

    def test_child_terminal_task_output_uses_its_own_metadata(self) -> None:
        call = self.session.call("Bash", {"command": "worker", "run_in_background": True})
        self.session.result(call, "Started", tool_use_result={"backgroundTaskId": "b1"})
        read = self.session.call("TaskOutput", {"task_id": "b1"})
        self.session.result(
            read, "PRIVATE_OUTPUT", tool_use_result={"task": {"id": "b1", "status": "completed"}}
        )
        child = [dict(row, isSidechain=True) for row in self.session.rows[1:]]
        self.session.rows = self.session.rows[:1]
        self.session.save(self.path)
        self.child_rows("agent-acde.jsonl", child)
        self.assertEqual(0, self.read()[1]["background_unpaired"])
        self.assertNotIn("PRIVATE_OUTPUT", str(self.launches()))

    def test_child_late_completion_refreshes_live_cache(self) -> None:
        call = self.session.bash("worker &")
        copied = dict(self.session.rows[1], isSidechain=True)
        self.session.rows = self.session.rows[:1]
        self.session.bash("pytest", "2 passed")
        self.session.save(self.path)
        child = self.child_rows("agent-acde.jsonl", [copied])
        before = live_estimate.for_session(
            self.config, saved_row(), str(self.path), [], floor=None, now=10**10
        )
        self.assertIn(levels.REASON_BACKGROUND_RUN, before["reasons"])
        child.write_text(
            child.read_text() + json.dumps(self.notification(call, sidechain=True)) + "\n"
        )
        after = live_estimate.for_session(
            self.config, saved_row(), str(self.path), [], floor=None, now=10**10
        )
        self.assertNotIn(levels.REASON_BACKGROUND_RUN, after["reasons"])

    def test_parent_sidechain_notification_is_not_parent_completion(self) -> None:
        call = self.session.bash("worker &")
        self.session.rows.append(self.notification(call, sidechain=True))
        self.assertEqual(1, self.read()[1]["background_unpaired"])


class DelegatedWorkFloor(unittest.TestCase):
    def test_completed_launch_does_not_block_the_floor(self) -> None:
        facts = evidence(
            [check("c1", 100, "passed")], scan(passed=1, background=1, background_unpaired=0)
        )
        self.assertNotIn(
            levels.REASON_BACKGROUND_RUN, levels.live_level(facts, intent("Tests pass")).reasons
        )

    def test_unpaired_launch_blocks_the_floor(self) -> None:
        facts = evidence(
            [check("c1", 100, "passed")], scan(passed=1, background=1, background_unpaired=1)
        )
        self.assertIn(
            levels.REASON_BACKGROUND_RUN, levels.live_level(facts, intent("Tests pass")).reasons
        )
