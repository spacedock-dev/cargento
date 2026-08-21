from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import claude_data, notifications, records, spacedock
from cargento_runtime import io as runtime_io
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime.collectors import claude as claude_collector

from . import support
from .support import (
    RuntimeTestCase,
    cfg,
    collect,
    collect_claude,
    config_patch,
    make_runtime,
    runtime,
    state_of,
    store_patch,
)


class ClaudeDataBoundTest(unittest.TestCase):
    """Every bounded read stops where the configuration says it does.

    Each fixture puts a usable record immediately before the bound and another
    immediately after it, so a test cannot pass by reading either everything or
    nothing.
    """

    def test_the_cwd_per_line_cap_truncates_a_long_record(self) -> None:
        # A single record longer than the per-line cap is read only up to it, so
        # a cwd hiding past the cap must not be found. Mutation-checked:
        # removing the cap passed the whole suite.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "long.jsonl"
            padded = {"type": "user", "pad": "x" * 400, "cwd": "/w/beyond"}
            path.write_text(json.dumps(padded) + "\n")
            config, state = make_runtime(claude_cwd_line_bytes=64)

            self.assertEqual("", claude_data.session_cwd(config, state, str(path)))

            wide, wide_state = make_runtime(claude_cwd_line_bytes=100_000)
            self.assertEqual("/w/beyond", claude_data.session_cwd(wide, wide_state, str(path)))

    def test_the_cwd_line_count_cap_stops_at_the_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "many.jsonl"
            filler = json.dumps({"type": "assistant"})
            inside = json.dumps({"type": "user", "cwd": "/w/inside"})
            beyond = json.dumps({"type": "user", "cwd": "/w/beyond"})
            path.write_text(f"{filler}\n{inside}\n{filler}\n{beyond}\n")
            # Two lines reaches the record before the bound, never the one after.
            config, state = make_runtime(claude_cwd_scan_lines=2)

            self.assertEqual("/w/inside", claude_data.session_cwd(config, state, str(path)))

    def test_the_agent_scan_line_cap_stops_at_the_bound(self) -> None:
        # Mutation-checked: dropping the line cap passed the whole suite.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.jsonl"
            filler = json.dumps({"type": "assistant"})
            beyond = json.dumps({"type": "agent-name", "agentName": "reviewer"})
            path.write_text(f"{filler}\n{filler}\n{beyond}\n")
            capped, capped_state = make_runtime(claude_agent_scan_lines=2)
            wide, wide_state = make_runtime(claude_agent_scan_lines=10)

            self.assertEqual(
                (False, "", ""), claude_data.agent_identity(capped, capped_state, str(path))
            )
            self.assertEqual(
                (False, "reviewer", ""), claude_data.agent_identity(wide, wide_state, str(path))
            )

    def test_a_hook_transcript_outside_the_projects_tree_is_refused(self) -> None:
        # The hook payload names its own transcript path, so containment is what
        # stops it naming an arbitrary file. Mutation-checked: dropping the
        # check passed the whole suite.
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects" / "-w-proj"
            projects.mkdir(parents=True)
            prefix = "abcdef12"
            record = json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}})
            inside = projects / f"{prefix}-0000-0000-0000-000000000000.jsonl"
            inside.write_text(record + "\n")
            outside = Path(tmp) / f"{prefix}-0000-0000-0000-000000000000.jsonl"
            outside.write_text(record + "\n")

            with store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")):
                config, state = runtime()

                self.assertTrue(claude_data.hook_user_event(config, state, str(inside), prefix)[0])
                self.assertEqual(
                    (False, None),
                    claude_data.hook_user_event(config, state, str(outside), prefix),
                )


class ClaudeCollectorTest(RuntimeTestCase):
    def test_load_tasks_supports_current_and_legacy_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "12345678-abcd-ef00-1234-567890abcdef"
            legacy = root / "session-abcdef12"
            current.mkdir()
            legacy.mkdir()
            (current / "1.json").write_text(
                json.dumps({"id": "1", "subject": "Current", "status": "pending"})
            )
            (legacy / "2.json").write_text(
                json.dumps({"id": "2", "subject": "Legacy", "status": "completed"})
            )

            with store_patch(TASKS_DIR=str(root)):
                tasks = claude_collector.load_tasks(runtime()[0])

        self.assertEqual({"12345678", "abcdef12"}, set(tasks))
        self.assertEqual("Current", tasks["12345678"][0]["subject"])
        self.assertEqual("Legacy", tasks["abcdef12"][0]["subject"])

    def test_hook_user_event_accepts_matching_project_transcript(self) -> None:
        session_id = "12345678-0000-0000-0000-000000000000"
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project = projects / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "user-before-hook",
                        "message": {"content": "run the command"},
                    }
                )
                + "\n"
            )
            with store_patch(PROJECTS_DIR=str(projects)):
                config, state = runtime()
                found, user_event = claude_data.hook_user_event(
                    config, state, str(transcript), session_id[:8]
                )

        self.assertTrue(found)
        self.assertEqual("user-before-hook", user_event)

    def test_new_user_event_clears_hook_without_comparing_clocks(self) -> None:
        _config, state = runtime()
        with state_of().hook_lock:
            state_of().hook_notifications["12345678"] = {
                "ts": 10_000.0,
                "message": "permission",
                "user_event": "before",
            }

        self.assertIsNotNone(notifications.current_hook(state, "12345678", "before", 0.0))
        self.assertIsNone(notifications.current_hook(state, "12345678", "after", 0.0))
        self.assertNotIn("12345678", state_of().hook_notifications)

    def test_untimestamped_user_record_clears_hook_notification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "12345678-session.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "before",
                        "message": {"content": "approve"},
                    }
                )
                + "\n"
            )
            config, state = runtime()
            before = claude_data.analyze_transcript(config, state, str(transcript))[
                "last_user_event"
            ]
            with state_of().hook_lock:
                state_of().hook_notifications["12345678"] = {
                    "ts": 10_000.0,
                    "message": "permission",
                    "user_event": before,
                }
            with transcript.open("a") as output:
                output.write(
                    json.dumps(
                        {
                            "type": "user",
                            "message": {"content": "continue without a timestamp"},
                        }
                    )
                    + "\n"
                )
            config, state = runtime()
            after = claude_data.analyze_transcript(config, state, str(transcript))[
                "last_user_event"
            ]

        self.assertNotEqual(before, after)
        self.assertIsNone(notifications.current_hook(state, "12345678", after, 0.0))

    def test_assistant_only_tail_does_not_change_hook_user_event(self) -> None:
        records = [
            {
                "type": "user",
                "uuid": "user-before-hook",
                "message": {"content": "approve"},
            },
            {
                "type": "assistant",
                "message": {"content": "x" * (cfg().tail_bytes + 100)},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "12345678-session.jsonl"
            transcript.write_text("\n".join(json.dumps(record) for record in records) + "\n")
            config, state = runtime()
            user_event = claude_data.analyze_transcript(config, state, str(transcript))[
                "last_user_event"
            ]

        self.assertEqual("user-before-hook", user_event)

    def test_answer_result_after_tail_boundary_does_not_leave_question_open(self) -> None:
        question = {
            "type": "assistant",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "question-1",
                        "name": "AskUserQuestion",
                        "input": {},
                    }
                ],
            },
        }
        answer = {
            "type": "user",
            "timestamp": "2026-01-01T00:10:00+00:00",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "question-1"}],
            },
        }
        # The only possible split in append-only JSONL puts the older
        # tool_use outside the tail and its later answer inside it. The answer
        # cannot age out before the question that precedes it.
        filler = {"type": "assistant", "message": {"content": "x" * cfg().tail_bytes}}
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            transcript.write_text(
                "\n".join(json.dumps(record) for record in (question, filler, answer)) + "\n"
            )
            config, state = runtime()
            info = claude_data.analyze_transcript(config, state, str(transcript))

        self.assertIsNone(info["pending_input_tool"])

    def test_transcript_mtime_alone_does_not_clear_newer_hook(self) -> None:
        now = time.time()
        event_time = datetime.fromtimestamp(now - 10, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            tasks = Path(tmp) / "tasks"
            project = projects / "sample"
            project.mkdir(parents=True)
            tasks.mkdir()
            transcript = project / "12345678-session.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": event_time,
                        "message": {"content": []},
                    }
                )
                + "\n"
            )
            with state_of().hook_lock:
                state_of().hook_notifications["12345678"] = {
                    "ts": now - 1,
                    "message": "permission",
                }

            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(tasks)),
                mock.patch.object(notifications, "notify_mac"),
            ):
                sessions = collect_claude(now, 24, False)

        # Fresh activity now takes display precedence (the hook only
        # surfaces once the session goes quiet) — but the property this test
        # protects still holds: mtime alone must NOT clear the stored hook.
        self.assertEqual("working", sessions[0]["state"])
        self.assertIn("12345678", state_of().hook_notifications)

    def test_claude_agent_identity_reads_only_a_bounded_prefix(self) -> None:
        record = json.dumps(
            {
                "type": "user",
                "agentName": "reviewer",
                "teamName": "session-12345678",
            }
        )
        source = mock.mock_open(read_data=(record + "\n" + ("x" * 100_000)).encode())
        runtime_pair = runtime()
        with (
            mock.patch("builtins.open", source),
            mock.patch.object(os.path, "getsize", return_value=1_000_000),
            mock.patch.object(support, "runtime", return_value=runtime_pair),
        ):
            config, state = runtime_pair
            identity = claude_data.agent_identity(config, state, "/fake/transcript.jsonl")

        self.assertEqual((True, "reviewer", "12345678"), identity)
        source().read.assert_called_once_with(runtime_pair[0].claude_agent_scan_bytes)

    def test_claude_agent_identity_drops_a_partial_final_prefix_record(self) -> None:
        apparent_record = b'{"agentName":"reviewer","teamName":"session-badbad00"}'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.jsonl"
            path.write_bytes(apparent_record + b"-continued-without-newline")
            with (
                config_patch(claude_agent_scan_bytes=len(apparent_record)),
                config_patch(claude_agent_cache_negative_min_bytes=len(apparent_record) * 10),
            ):
                config, state = runtime()
                identity = claude_data.agent_identity(config, state, str(path))

        self.assertEqual((False, "", ""), identity)

    def test_transient_agent_identity_read_failure_is_not_negative_cached(self) -> None:
        record = json.dumps(
            {
                "type": "user",
                "agentName": "reviewer",
                "teamName": "session-12345678",
            }
        )
        source = mock.mock_open(read_data=(record + "\n").encode())
        runtime_pair = runtime()
        path = "/fake/transient-agent.jsonl"
        with (
            mock.patch(
                "builtins.open",
                side_effect=[PermissionError("temporarily locked"), source.return_value],
            ),
            mock.patch.object(
                os.path,
                "getsize",
                return_value=runtime_pair[0].claude_agent_cache_negative_min_bytes,
            ),
            mock.patch.object(support, "runtime", return_value=runtime_pair),
        ):
            config, state = runtime_pair
            self.assertEqual((False, "", ""), claude_data.agent_identity(config, state, path))
            self.assertNotIn(path, state_of().agent_class_cache)
            self.assertEqual(
                (True, "reviewer", "12345678"),
                claude_data.agent_identity(config, state, path),
            )

    def test_transient_agent_setting_read_failure_is_not_negative_cached(self) -> None:
        record = json.dumps({"agentSetting": spacedock.SPACEDOCK_ENSIGN})
        source = mock.mock_open(read_data=(record + "\n").encode())
        runtime_pair = runtime()
        path = "/fake/transient-setting.jsonl"
        with (
            mock.patch(
                "builtins.open",
                side_effect=[PermissionError("temporarily locked"), source.return_value],
            ),
            mock.patch.object(
                os.path,
                "getsize",
                return_value=runtime_pair[0].claude_agent_cache_negative_min_bytes,
            ),
            mock.patch.object(support, "runtime", return_value=runtime_pair),
        ):
            config, state = runtime_pair
            self.assertEqual("", claude_data.agent_setting(config, state, path))
            self.assertNotIn(path, state.spacedock_role_cache)
            self.assertEqual(
                spacedock.SPACEDOCK_ENSIGN,
                claude_data.agent_setting(config, state, path),
            )

    def test_claude_cwd_uses_independent_line_and_count_caps(self) -> None:
        first = json.dumps({"ignored": "x" * 100})
        target = json.dumps({"cwd": "/wanted/project"})
        first_line = (first + "\n").encode()
        payload = first_line + (target + "\n").encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_bytes(payload)
            short_scan = Path(tmp) / "short-scan.jsonl"
            short_scan.write_bytes(payload)
            self.assertEqual(payload, path.read_bytes())
            self.assertEqual(payload, short_scan.read_bytes())
            with (
                config_patch(claude_cwd_scan_lines=2),
                config_patch(claude_cwd_line_bytes=len(first_line)),
            ):
                config, state = runtime()
                self.assertEqual(
                    "/wanted/project", claude_data.session_cwd(config, state, str(path))
                )
            with (
                config_patch(claude_cwd_scan_lines=1),
                config_patch(claude_cwd_line_bytes=len(first_line)),
            ):
                config, state = runtime()
                self.assertEqual("", claude_data.session_cwd(config, state, str(short_scan)))

    def test_configured_agent_transcript_remains_a_top_level_session(self) -> None:
        now = time.time()
        timestamp = datetime.fromtimestamp(now - 5, UTC).isoformat()
        session_id = "c0ffee25-0000-0000-0000-000000000000"
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project = projects / "sample"
            project.mkdir(parents=True)
            tasks = Path(tmp) / "tasks"
            tasks.mkdir()
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in (
                        {
                            "type": "agent-name",
                            "agentName": spacedock.SPACEDOCK_ENSIGN,
                            "agentSetting": spacedock.SPACEDOCK_ENSIGN,
                        },
                        {
                            "type": "user",
                            "sessionId": session_id,
                            "timestamp": timestamp,
                            "message": {"role": "user", "content": "run the workflow"},
                        },
                    )
                )
                + "\n"
            )
            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(tasks)),
            ):
                sessions = collect_claude(now, 24, False)
                config, state = runtime()
                classified_as_subagent = claude_data.prefix_is_agent(config, state, session_id[:8])

        self.assertEqual([session_id[:8]], [session["session"] for session in sessions])
        self.assertFalse(classified_as_subagent)
        self.assertEqual(
            {"role": "ensign", "workflows": []},
            sessions[0]["spacedock"],
        )

    def test_young_agent_identity_can_gain_a_parent_relation(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "young-agent.jsonl"
            transcript.write_text(
                json.dumps({"type": "agent-name", "agentName": "reviewer"}) + "\n"
            )

            self.assertEqual(
                (False, "reviewer", ""),
                claude_data.agent_identity(config, state, str(transcript)),
            )

            with transcript.open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "type": "user",
                            "teamName": "session-12345678",
                        }
                    )
                    + "\n"
                )

            self.assertEqual(
                (True, "reviewer", "12345678"),
                claude_data.agent_identity(config, state, str(transcript)),
            )

    def test_young_agent_identity_can_gain_a_name_after_parent_relation(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "young-agent.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "teamName": "session-12345678",
                    }
                )
                + "\n"
            )

            self.assertEqual(
                (True, "", "12345678"),
                claude_data.agent_identity(config, state, str(transcript)),
            )
            self.assertNotIn(str(transcript), state_of().agent_class_cache)

            with transcript.open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "type": "agent-name",
                            "agentName": "reviewer",
                        }
                    )
                    + "\n"
                )

            self.assertEqual(
                (True, "reviewer", "12345678"),
                claude_data.agent_identity(config, state, str(transcript)),
            )

    def test_parent_relation_without_agent_name_is_still_a_subagent(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "unnamed-agent.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "teamName": "session-12345678",
                    }
                )
                + "\n"
            )

            self.assertEqual(
                (True, "", "12345678"),
                claude_data.agent_identity(config, state, str(transcript)),
            )

    def test_claude_agent_negative_cache_waits_for_conclusive_prefix(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "young.jsonl"
            transcript.write_text("{}\n")
            self.assertEqual(
                (False, "", ""),
                claude_data.agent_identity(config, state, str(transcript)),
            )
            self.assertNotIn(str(transcript), state_of().agent_class_cache)

            transcript.write_text("{}\n" * 50)
            self.assertEqual(
                (False, "", ""),
                claude_data.agent_identity(config, state, str(transcript)),
            )

        self.assertIn(str(transcript), state_of().agent_class_cache)

    def test_claude_title_prefers_newest_ai_title_outside_tail(self) -> None:
        records = [
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:00Z",
                "message": {"content": "stale first prompt"},
            },
            {"type": "ai-title", "aiTitle": "Older generated title"},
            {"type": "ai-title", "aiTitle": "Current generated title"},
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:01Z",
                "message": {"content": "x" * (cfg().tail_bytes + 100)},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            transcript.write_text("\n".join(json.dumps(record) for record in records) + "\n")
            config, state = runtime()
            info = claude_data.analyze_transcript(config, state, str(transcript))

        self.assertEqual("Current generated title", info["title"])

    def test_claude_title_falls_back_to_first_user_prompt(self) -> None:
        records = [
            {"type": "system", "timestamp": "2026-01-01T00:00:00Z"},
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:01Z",
                "message": {"content": "First useful prompt\nwith details"},
            },
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:02Z",
                "message": {"content": "Later prompt"},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            transcript.write_text("\n".join(json.dumps(record) for record in records) + "\n")
            config, state = runtime()
            info = claude_data.analyze_transcript(config, state, str(transcript))

        self.assertEqual("First useful prompt", info["title"])

    def test_legacy_claude_agent_files_are_not_top_level_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            tasks = Path(tmp) / "tasks"
            project = projects / "sample"
            project.mkdir(parents=True)
            tasks.mkdir()
            (project / "agent-abcd.jsonl").write_text("{}\n")
            (project / "12345678-session.jsonl").write_text("{}\n")

            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(tasks)),
            ):
                sessions = collect_claude(time.time(), 24, True)

        self.assertEqual(["12345678"], [session["session"] for session in sessions])

    def test_modern_subagent_transcripts_fold_into_parent_session(self) -> None:
        # Harness >= 2.x writes subagent transcripts as ordinary top-level
        # <uuid>.jsonl files whose records carry agentName and
        # teamName "session-<parent prefix>". They must NOT surface as
        # standalone sessions; they attach to the parent as named running
        # subagents, keep it working, and contribute to its output rate.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        stale_iso = datetime.fromtimestamp(now - 600, UTC).isoformat()
        parent_id = "aaaa1111-0000-0000-0000-000000000000"
        child_id = "bbbb2222-0000-0000-0000-000000000000"
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            parent_fp = proj / f"{parent_id}.jsonl"
            parent_fp.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": parent_id,
                        "timestamp": stale_iso,
                        "message": {"role": "user", "content": "build the feature"},
                    }
                )
                + "\n"
            )
            child_fp = proj / f"{child_id}.jsonl"
            child_fp.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": child_id,
                        "agentName": "spark-reviewer",
                        "teamName": f"session-{parent_id[:8]}",
                        "timestamp": iso,
                        "message": {"role": "user", "content": "review the sparkline"},
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": child_id,
                        "agentName": "spark-reviewer",
                        "teamName": f"session-{parent_id[:8]}",
                        "timestamp": iso,
                        "message": {
                            "role": "assistant",
                            "content": [],
                            "usage": {"output_tokens": 500},
                        },
                    }
                )
                + "\n"
            )
            # Parent quiet for 10 minutes; child fresh.
            old = now - 600
            os.utime(parent_fp, (old, old))
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
            ):
                sessions = collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))
        parent = sessions[0]
        self.assertEqual(parent_id[:8], parent["session"])
        self.assertEqual("working", parent["state"])
        self.assertEqual([{"name": "spark-reviewer", "model": None}], parent["subagents"])
        self.assertGreater(parent["rate_per_min"], 0)

    def test_a_quiet_child_transcript_stops_counting_as_a_running_subagent(self) -> None:
        # A child that has gone quiet is finished work, not running work: it must
        # drop off the parent's subagent pills and stop holding it in Working.
        # The parent still stays in the window, because a child write is real
        # activity even when it is too old to read as running.
        # Mutation-checked: dropping the child freshness filter passed the suite.
        now = time.time()
        stale_iso = datetime.fromtimestamp(now - 600, UTC).isoformat()
        parent_id = "aaaa1111-0000-0000-0000-000000000000"
        child_id = "bbbb2222-0000-0000-0000-000000000000"
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            parent_fp = proj / f"{parent_id}.jsonl"
            parent_fp.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": parent_id,
                        "timestamp": stale_iso,
                        "message": {"role": "user", "content": "build the feature"},
                    }
                )
                + "\n"
            )
            child_fp = proj / f"{child_id}.jsonl"
            child_fp.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": child_id,
                        "agentName": "spark-reviewer",
                        "teamName": f"session-{parent_id[:8]}",
                        "timestamp": stale_iso,
                        "message": {"role": "user", "content": "review the sparkline"},
                    }
                )
                + "\n"
            )
            old = now - 600
            os.utime(parent_fp, (old, old))
            os.utime(child_fp, (old, old))
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
            ):
                sessions = collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions), "the child must still not be a standalone session")
        parent = sessions[0]
        self.assertEqual(parent_id[:8], parent["session"])
        self.assertEqual([], parent["subagents"])
        self.assertEqual("idle", parent["state"])
        self.assertTrue(parent["active"], "a child write keeps the session in the window")

    def test_load_tasks_coerces_malformed_field_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "12345678-abcd-ef00-1234-567890abcdef"
            root.mkdir(parents=True)
            (root / "1.json").write_text(
                json.dumps({"id": "1", "subject": {"nested": True}, "activeForm": 42, "status": 7})
            )
            (root / "2.json").write_text(json.dumps(["not", "a", "task"]))

            with store_patch(TASKS_DIR=str(tmp)):
                tasks = claude_collector.load_tasks(runtime()[0])

        rows = tasks["12345678"]
        self.assertEqual(1, len(rows))  # the non-dict record is skipped
        task = rows[0]
        self.assertEqual("(untitled)", task["subject"])
        self.assertEqual("", task["activeForm"])
        self.assertEqual("pending", task["status"])
        # The concatenation that previously raised TypeError must work.
        self.assertEqual("(untitled)…", (task["activeForm"] or task["subject"]) + "…")

    def test_claude_subagents_tolerate_malformed_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sess = Path(tmp) / "abc.jsonl"
            sess.write_text("{}\n")
            sub = Path(tmp) / "abc" / "subagents"
            sub.mkdir(parents=True)
            (sub / "agent-1.jsonl").write_text("{}\n")
            (sub / "agent-1.meta.json").write_text('{"name":42,"description":7}')
            (sub / "agent-2.jsonl").write_text("{}\n")
            (sub / "agent-2.meta.json").write_text("42")  # non-dict meta

            agents = claude_collector.load_subagents(runtime()[0], str(sess), time.time())

        # Both agents survive with the fallback label instead of TypeError.
        self.assertEqual(["subagent", "subagent"], [a["label"] for a in agents])

    def test_a_quiet_subagent_transcript_is_not_a_running_subagent(self) -> None:
        # "Running" is inferred from mtime, and a subagent pill is the reason a
        # parent session reads Working. Without the freshness filter a session
        # would list every subagent it ever ran and never leave Working.
        # Mutation-checked: dropping the filter passed the whole suite.
        now = 1_700_000_000.0
        config = runtime()[0]
        with tempfile.TemporaryDirectory() as tmp:
            sess = Path(tmp) / "abc.jsonl"
            sess.write_text("{}\n")
            sub = Path(tmp) / "abc" / "subagents"
            sub.mkdir(parents=True)
            for name, age in (("agent-live", 5.0), ("agent-quiet", 600.0)):
                path = sub / f"{name}.jsonl"
                path.write_text("{}\n")
                (sub / f"{name}.meta.json").write_text(json.dumps({"name": name}))
                os.utime(path, (now - age, now - age))

            agents = claude_collector.load_subagents(config, str(sess), now)

        self.assertGreater(600.0, config.working_threshold_sec, "the quiet agent must be stale")
        self.assertEqual(["agent-live"], [a["label"] for a in agents])

    def test_workflow_subagents_count_as_running_subagents(self) -> None:
        # Workflow fan-outs write one directory deeper than a plain Task
        # subagent: subagents/workflows/<run-id>/agent-*.jsonl. Both layouts
        # are the same thing to the dashboard — work the session is doing.
        with tempfile.TemporaryDirectory() as tmp:
            sess = Path(tmp) / "abc.jsonl"
            sess.write_text("{}\n")
            plain = Path(tmp) / "abc" / "subagents"
            plain.mkdir(parents=True)
            (plain / "agent-1.jsonl").write_text("{}\n")
            (plain / "agent-1.meta.json").write_text('{"name":"plain-task"}')
            run = plain / "workflows" / "wf_506d8d41-ba5"
            run.mkdir(parents=True)
            (run / "agent-2.jsonl").write_text("{}\n")
            (run / "agent-2.meta.json").write_text('{"name":"review:bugs"}')
            # The run's bookkeeping file sits beside its agents and is not one.
            (run / "journal.jsonl").write_text("{}\n")

            agents = claude_collector.load_subagents(runtime()[0], str(sess), time.time())

        self.assertEqual({"plain-task", "review:bugs"}, {a["label"] for a in agents})

    def test_workflow_agents_keep_a_quiet_parent_working(self) -> None:
        # The live 5cb7c95e case: the main loop is parked awaiting a background
        # workflow, so its transcript goes quiet while ten workflow agents burn
        # tokens. The session read Idle with its task list hidden.
        now = time.time()
        session_id = "5cb7c95e-0000-0000-0000-000000000000"
        stale = now - 400  # well past working_threshold_sec
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": datetime.fromtimestamp(stale, UTC).isoformat(),
                        "message": {"role": "user", "content": "fan the detectors out"},
                    }
                )
                + "\n"
            )
            os.utime(transcript, (stale, stale))
            run = project / session_id / "subagents" / "workflows" / "wf_506d8d41-ba5"
            run.mkdir(parents=True)
            agent = run / "agent-a88a43dd9.jsonl"
            agent.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": datetime.fromtimestamp(now - 5, UTC).isoformat(),
                        "message": {
                            "role": "assistant",
                            "content": [],
                            "usage": {"output_tokens": 3000},
                        },
                    }
                )
                + "\n"
            )
            (run / "agent-a88a43dd9.meta.json").write_text('{"name":"detect:backend"}')
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
            ):
                session = collect_claude(now, 24, False)[0]

        self.assertEqual("working", session["state"])
        self.assertEqual([{"name": "detect:backend", "model": None}], session["subagents"])
        # The agent's output is the session's output — a parent that reads
        # Working at 0 tok/min is the same blind spot in the rate panel.
        self.assertGreater(session["rate_per_min"], 0)

    def test_a_finished_loop_is_still_published_after_the_session_goes_quiet(self) -> None:
        # The whole point of the top-level field. `turn` is None for anything
        # that is not working, so a loop signal carried there would vanish the
        # moment the failures stopped — which is when the human walks back to
        # the machine and asks what happened.
        now = time.time()
        session_id = "10000000-0000-0000-0000-000000000000"
        quiet = now - 600  # past the working threshold, inside the 24h window
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            lines = [
                {
                    "type": "user",
                    "timestamp": datetime.fromtimestamp(quiet - 60, UTC).isoformat(),
                    "message": {"role": "user", "content": "run the suite"},
                }
            ]
            for i in range(4):
                lines.append(
                    {
                        "type": "assistant",
                        "timestamp": datetime.fromtimestamp(quiet - 50 + i * 10, UTC).isoformat(),
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "tool_use", "id": f"t{i}", "name": "Bash"}],
                        },
                    }
                )
                lines.append(
                    {
                        "type": "user",
                        "timestamp": datetime.fromtimestamp(quiet - 45 + i * 10, UTC).isoformat(),
                        "message": {
                            "role": "user",
                            "content": [
                                {"type": "tool_result", "tool_use_id": f"t{i}", "is_error": True}
                            ],
                        },
                    }
                )
            transcript.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
            os.utime(transcript, (quiet, quiet))
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
            ):
                session = collect_claude(now, 24, False)[0]

        self.assertNotEqual("working", session["state"])
        self.assertIsNone(session["turn"])
        self.assertEqual({"errors": 4, "tool": "Bash"}, session["loop"])

    def test_workflow_agent_activity_holds_a_session_in_the_window(self) -> None:
        # last_activity drives both the freshness window and the "idle 23h"
        # age. A stale parent whose workflow agents wrote a minute ago has to
        # count as a minute old, or a long run ages out of the dashboard.
        now = time.time()
        session_id = "d0d0d0d0-0000-0000-0000-000000000000"
        ancient = now - 30 * 3600  # older than the 24h window
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text("{}\n")
            os.utime(transcript, (ancient, ancient))
            run = project / session_id / "subagents" / "workflows" / "wf_1"
            run.mkdir(parents=True)
            agent = run / "agent-1.jsonl"
            agent.write_text("{}\n")
            recent = now - 300  # quiet enough not to read Working
            os.utime(agent, (recent, recent))
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
            ):
                sessions = collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertAlmostEqual(recent, sessions[0]["last_activity"], delta=2)

    def test_claude_session_cwd_reads_the_head_and_retries_when_absent(self) -> None:
        # The cwd drives every Claude project label.
        with tempfile.TemporaryDirectory() as tmp:
            late = Path(tmp) / "late.jsonl"
            filler = "\n".join(json.dumps({"type": "x", "n": i}) for i in range(60))
            late.write_text(filler + "\n" + json.dumps({"type": "user", "cwd": "/w/late"}) + "\n")
            # Past the 50-line scan bound: not found, and not cached as a miss.
            config, state = runtime()
            self.assertEqual("", claude_data.session_cwd(config, state, str(late)))
            self.assertNotIn(str(late), state_of().cwd_cache)

            early = Path(tmp) / "early.jsonl"
            early.write_text("{}\n")
            config, state = runtime()
            self.assertEqual("", claude_data.session_cwd(config, state, str(early)))
            # A miss must not be cached, or a transcript whose head is written
            # before its first cwd record keeps the fallback label forever.
            early.write_text(json.dumps({"type": "user", "cwd": "/w/early"}) + "\n")
            config, state = runtime()
            self.assertEqual("/w/early", claude_data.session_cwd(config, state, str(early)))

            missing = Path(tmp) / "gone.jsonl"
            config, state = runtime()
            self.assertEqual("", claude_data.session_cwd(config, state, str(missing)))

    def test_claude_project_falls_back_when_transcript_has_no_cwd(self) -> None:
        # A transcript head can be written before any record carries cwd. The
        # encoded directory name is lossy (Claude replaces every separator
        # with "-", so it cannot be split back apart), so the documented
        # fallback stays whole rather than guessing at a split.
        now = time.time()
        home = "/Users/cl"
        encoded = f"{runtime_sessions.encoded_home_prefix(home)}-git-spacedock-subspace"
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / encoded
            project_dir.mkdir(parents=True)
            (project_dir / "bbbb2222-0000-0000-0000-000000000000.jsonl").write_text("{}\n")
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
                config_patch(home=home),
            ):
                sessions = collect_claude(now, 24, False)

        self.assertEqual("git-spacedock-subspace", sessions[0]["project"])


class ClaudeModelTest(RuntimeTestCase):
    """The model a Claude session and its subagents report.

    Three states, never two: a measured model, and no model reported, are
    different facts and stay distinguishable all the way to the page. Nothing
    here may infer a model from anything other than an assistant record that
    names one.
    """

    PARENT = "aaaa1111-0000-0000-0000-000000000000"
    CHILD = "bbbb2222-0000-0000-0000-000000000000"

    @staticmethod
    def _write(path: Path, records_out: list[dict[str, Any]]) -> None:
        path.write_text("\n".join(json.dumps(r) for r in records_out) + "\n")

    def _assistant(self, **fields: Any) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": []}
        for key in ("model", "usage"):
            if key in fields:
                message[key] = fields.pop(key)
        return {"type": "assistant", "message": message, **fields}

    def _analyze(self, records_out: list[dict[str, Any]]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            self._write(path, records_out)
            config, state = runtime()
            return claude_data.analyze_transcript(config, state, str(path))

    def test_the_synthetic_sentinel_is_never_published_as_a_model(self) -> None:
        # One top-level transcript in five has "<synthetic>" as its newest
        # assistant model: Claude's marker for a record it wrote locally, without
        # the request reaching the API. Published, it renders exactly like a real
        # model name. Rejected by VALUE, because the isApiErrorMessage flag that
        # sits beside it is falsy on some synthetic records — a flag gate leaks
        # the sentinel. When it is all a transcript has, the answer is None.
        info = self._analyze(
            [
                self._assistant(model="<synthetic>", isApiErrorMessage=True),
                self._assistant(model="<synthetic>", isApiErrorMessage=False),
                self._assistant(model="<synthetic>"),
            ]
        )

        self.assertIsNone(info["model"])
        self.assertIsNone(info["model_sidechain"])

    def test_a_synthetic_tail_does_not_withdraw_a_measured_model(self) -> None:
        # A cancellation or an error banner lands after the last real turn. It
        # says nothing about which model the session is on, so it must not
        # overwrite the reading the turns before it earned.
        info = self._analyze(
            [
                self._assistant(model="claude-opus-5"),
                self._assistant(model="<synthetic>", isApiErrorMessage=False),
            ]
        )

        self.assertEqual("claude-opus-5", info["model"])

    def test_the_newest_assistant_model_wins_a_mid_session_switch(self) -> None:
        # Newest-wins, not first-wins: a session that switched plan mid-run is
        # on the model of its most recent turn. Transcripts do not carry stray
        # background models, so the newest value is the session's own.
        info = self._analyze(
            [
                self._assistant(model="claude-fable-5"),
                self._assistant(model="claude-opus-5"),
            ]
        )

        self.assertEqual("claude-opus-5", info["model"])

    def test_a_sidechain_record_lands_in_the_sidechain_half(self) -> None:
        # isSidechain INVERTS between a session and its children: a subagent's
        # own transcript flags every assistant record as a sidechain, so its
        # model lands in `model_sidechain` and the session half stays empty.
        # `child_model` reads the two in that order, which is why a child is
        # measured at all.
        info = self._analyze([self._assistant(model="claude-fable-5", isSidechain=True)])

        self.assertIsNone(info["model"])
        self.assertEqual("claude-fable-5", info["model_sidechain"])
        self.assertEqual("claude-fable-5", claude_collector.child_model(info))

    def test_child_model_never_falls_back_to_the_parent(self) -> None:
        # An unread child publishes None. Borrowing the parent's model would make
        # "the same model as its parent" indistinguishable from "not measured",
        # which is the one distinction this ticket exists to keep.
        self.assertIsNone(claude_collector.child_model(None))
        self.assertIsNone(claude_collector.child_model({}))
        self.assertIsNone(claude_collector.child_model({"model": None, "model_sidechain": None}))
        self.assertEqual("claude-opus-5", claude_collector.child_model({"model": "claude-opus-5"}))

    def test_a_model_string_is_bounded_and_stripped_of_control_characters(self) -> None:
        # Untrusted vendor text on its way to the DOM. Bounded at the only door
        # it comes through, so no caller can forget.
        cap = runtime_sessions.MODEL_CAP_CHARS
        info = self._analyze([self._assistant(model="m\u0007odel" + "x" * (cap * 3))])

        model = info["model"]
        assert model is not None
        self.assertEqual(cap, len(model))
        self.assertTrue(model.startswith("m odel"), model)

    def test_a_non_string_model_field_reports_no_model(self) -> None:
        # Untyped JSON: a number, an object or an empty string is not a reading.
        for value in (42, {"name": "opus"}, ["opus"], "", "   ", None):
            with self.subTest(value=value):
                self.assertIsNone(claude_data.model_reported(value))

    def test_a_session_and_its_subagent_publish_their_own_models(self) -> None:
        # End to end, on the modern layout: the parent's model comes from its own
        # non-sidechain records, the child's from its own sidechain ones, and the
        # child's rides beside its label rather than replacing it.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        stale_iso = datetime.fromtimestamp(now - 600, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            parent_fp = proj / f"{self.PARENT}.jsonl"
            self._write(
                parent_fp,
                [
                    {
                        "type": "user",
                        "sessionId": self.PARENT,
                        "timestamp": stale_iso,
                        "message": {"role": "user", "content": "build the feature"},
                    },
                    self._assistant(
                        model="claude-opus-5",
                        sessionId=self.PARENT,
                        timestamp=stale_iso,
                    ),
                ],
            )
            child_fp = proj / f"{self.CHILD}.jsonl"
            self._write(
                child_fp,
                [
                    {
                        "type": "user",
                        "sessionId": self.CHILD,
                        "agentName": "spark-reviewer",
                        "teamName": f"session-{self.PARENT[:8]}",
                        "timestamp": iso,
                        "message": {"role": "user", "content": "review the sparkline"},
                    },
                    self._assistant(
                        model="claude-fable-5",
                        isSidechain=True,
                        sessionId=self.CHILD,
                        agentName="spark-reviewer",
                        teamName=f"session-{self.PARENT[:8]}",
                        timestamp=iso,
                        usage={"output_tokens": 500},
                    ),
                ],
            )
            old = now - 600
            os.utime(parent_fp, (old, old))
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
            ):
                sessions = collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))
        parent = sessions[0]
        self.assertEqual("claude-opus-5", parent["model"])
        self.assertEqual(
            [{"name": "spark-reviewer", "model": "claude-fable-5"}], parent["subagents"]
        )

    def test_a_legacy_workflow_agent_publishes_the_model_from_its_own_file(self) -> None:
        # The other layout: agent-*.jsonl beneath the session directory, named by
        # a sibling .meta.json. Same rule, and a session whose own transcript
        # names no model still reports None rather than borrowing the child's.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            run = proj / self.PARENT / "subagents"
            run.mkdir(parents=True)
            self._write(
                proj / f"{self.PARENT}.jsonl",
                [
                    {
                        "type": "user",
                        "sessionId": self.PARENT,
                        "timestamp": iso,
                        "message": {"role": "user", "content": "detect the backend"},
                    }
                ],
            )
            agent_fp = run / "agent-a88a43dd9.jsonl"
            self._write(
                agent_fp,
                [
                    self._assistant(
                        model="claude-fable-5",
                        isSidechain=True,
                        timestamp=iso,
                        usage={"output_tokens": 500},
                    )
                ],
            )
            (run / "agent-a88a43dd9.meta.json").write_text('{"name":"detect:backend"}')
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
            ):
                session = collect_claude(now, 24, False)[0]

        self.assertIsNone(session["model"], "the parent named no model of its own")
        self.assertEqual(
            [{"name": "detect:backend", "model": "claude-fable-5"}], session["subagents"]
        )

    def test_an_unmeasured_subagent_publishes_a_null_model_beside_its_name(self) -> None:
        # `model` is always present on a subagent element, null meaning not read.
        # A missing key would leave the page unable to tell the two apart.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            run = proj / self.PARENT / "subagents"
            run.mkdir(parents=True)
            self._write(
                proj / f"{self.PARENT}.jsonl",
                [
                    {
                        "type": "user",
                        "sessionId": self.PARENT,
                        "timestamp": iso,
                        "message": {"role": "user", "content": "detect the backend"},
                    }
                ],
            )
            self._write(
                run / "agent-a88a43dd9.jsonl",
                [self._assistant(model="<synthetic>", isSidechain=True, timestamp=iso)],
            )
            (run / "agent-a88a43dd9.meta.json").write_text('{"name":"detect:backend"}')
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
            ):
                session = collect_claude(now, 24, False)[0]

        self.assertEqual([{"name": "detect:backend", "model": None}], session["subagents"])

    def test_load_subagents_without_analyses_publishes_no_model(self) -> None:
        # The callers outside a collection hand no `models` map over. They must
        # get an explicit null rather than a missing key or a guess.
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / self.PARENT / "subagents"
            run.mkdir(parents=True)
            transcript = Path(tmp) / f"{self.PARENT}.jsonl"
            transcript.write_text("{}\n")
            (run / "agent-1.jsonl").write_text("{}\n")
            config, _state = runtime()

            agents = claude_collector.load_subagents(config, str(transcript), now)

        self.assertEqual([None], [a["model"] for a in agents])


class ClaudeReviewFixTest(unittest.TestCase):
    def test_a_non_dict_message_does_not_kill_the_claude_collector(self) -> None:
        # {"type":"user","message":"a string"} is valid JSON, and the string is
        # truthy — so `record.get("message") or {}` returned it and the next
        # .get() raised, taking the whole collector down for that refresh.
        # Exercised end to end: the helpers alone missed analyze_transcript,
        # which is the path every active session goes through.
        now = 1_700_000_000.0
        malformed = [
            {"type": "user", "message": "not-an-object"},
            {"type": "assistant", "message": 42},
            {"type": "user", "message": ["a", "list"]},
            {"type": "message", "message": "droid-shaped"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / "abcdef12-0000-0000-0000-000000000000.jsonl"
            transcript.write_text("\n".join(json.dumps(r) for r in malformed) + "\n")
            os.utime(transcript, (now, now))

            config, state = runtime()
            self.assertIsNone(claude_data.session_title(config, state, str(transcript)))
            self.assertEqual({}, records.message_dict({"message": "str"}))
            self.assertEqual({}, records.message_dict("not-a-record"))
            self.assertEqual({"a": 1}, records.message_dict({"message": {"a": 1}}))

            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
            ):
                sessions = collect_claude(now, 24, False)  # must not raise
                everything = collect(24, True)

        self.assertEqual(1, len(sessions))
        claude = next(h for h in everything["harnesses"] if h["key"] == "claude")
        self.assertIsNone(claude["error"], "collector errored on a malformed record")


class ClaudeGlobTest(unittest.TestCase):
    HOSTILE = "A [Contractor]"

    def test_claude_sessions_survive_a_metacharacter_in_the_projects_root(self) -> None:
        now = 1_700_000_000.0
        session_id = "abcdef12-3456-7890-abcd-ef1234567890"
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / self.HOSTILE / "projects"
            project = projects / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "u1",
                        "timestamp": "2023-11-14T22:13:20+00:00",
                        "message": {"content": "hostile path prompt"},
                    }
                )
                + "\n"
            )
            os.utime(transcript, (now, now))
            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
            ):
                sessions = collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual("hostile path prompt", sessions[0]["title"])


class SubagentGlobCostTest(RuntimeTestCase):
    """One subagent scan per session, not two.

    The parent transcript and the subagent transcripts are all real files, so
    these fail if handing the listing over changes which subagents are found.
    """

    def _fixture(self, root: str, *names: str) -> str:
        """A parent transcript plus ``names`` under its ``subagents/`` layout."""
        parent = Path(root) / "abcd1234-session.jsonl"
        parent.write_text("{}\n", encoding="utf-8")
        sub = Path(root) / "abcd1234-session" / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        for name in names:
            (sub / name).write_text("{}\n", encoding="utf-8")
        return str(parent)

    def test_load_subagents_accepts_a_precomputed_listing(self) -> None:
        config = runtime()[0]
        now = time.time()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-worker.jsonl")

            found = claude_collector.agent_transcripts(parent)
            self.assertTrue(found, "fixture must produce at least one subagent transcript")

            with mock.patch.object(
                claude_collector,
                "agent_transcripts",
                side_effect=AssertionError("globbed again"),
            ):
                agents = claude_collector.load_subagents(config, parent, now, found=found)

            self.assertEqual(["subagent"], [a["label"] for a in agents])

    def test_precomputed_and_self_scanned_results_are_identical(self) -> None:
        config = runtime()[0]
        now = time.time()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl", "agent-b.jsonl")

            self.assertEqual(
                claude_collector.load_subagents(config, parent, now),
                claude_collector.load_subagents(
                    config, parent, now, found=claude_collector.agent_transcripts(parent)
                ),
            )

    def test_absent_session_directory_is_not_globbed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            parent = Path(root) / "abcd1234-session.jsonl"
            parent.write_text("{}\n", encoding="utf-8")
            # No sibling "abcd1234-session/" directory: the common case for a
            # historical session that never ran a subagent.
            with mock.patch.object(
                runtime_io,
                "glob_under",
                side_effect=AssertionError("globbed a directory that does not exist"),
            ):
                self.assertEqual([], claude_collector.agent_transcripts(str(parent)))

    def test_present_session_directory_is_still_globbed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            found = claude_collector.agent_transcripts(parent)
            self.assertEqual(["agent-a.jsonl"], [os.path.basename(p) for p, _ in found])


class SubagentListingCacheTest(RuntimeTestCase):
    """A session directory whose subagent tree has not moved is listed once.

    Keyed on directory mtimes rather than on a freshness window, because a
    workflow that runs for hours parks its parent transcript and keeps writing
    only to subagent files. Dropping old prefixes would lose those sessions.
    """

    def _fixture(self, root: str, *names: str) -> str:
        """A parent transcript plus ``names`` under its ``subagents/`` layout."""
        parent = os.path.join(root, "abcd1234-session.jsonl")
        Path(parent).write_text("{}\n", encoding="utf-8")
        sub = os.path.join(root, "abcd1234-session", "subagents")
        os.makedirs(sub, exist_ok=True)
        for name in names:
            Path(os.path.join(sub, name)).write_text("{}\n", encoding="utf-8")
        return parent

    def test_second_call_with_unchanged_mtime_does_not_glob(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            first = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertTrue(first)
            with mock.patch.object(
                runtime_io,
                "glob_under",
                side_effect=AssertionError("re-globbed an unchanged directory"),
            ):
                second = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertEqual(first, second)

    def test_a_new_subagent_file_invalidates_the_entry(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            first = claude_collector.agent_transcripts(parent, config=config, state=state)
            sub = os.path.join(root, "abcd1234-session", "subagents")
            # Force a distinct directory mtime: a coarse filesystem timestamp
            # would otherwise make this test pass or fail on timing alone.
            Path(os.path.join(sub, "agent-b.jsonl")).write_text("{}\n", encoding="utf-8")
            os.utime(sub, (time.time() + 5, time.time() + 5))
            second = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 2)

    def test_a_reused_listing_carries_the_current_file_mtime(self) -> None:
        """A cache hit restates the mtimes; only the glob is skipped.

        Appending to a subagent transcript moves no directory mtime, so an
        entry that served cached mtimes would freeze a running subagent at the
        moment it was first seen and read Idle from then on.
        """
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            claude_collector.agent_transcripts(parent, config=config, state=state)
            agent = os.path.join(root, "abcd1234-session", "subagents", "agent-a.jsonl")
            moved = time.time() + 30
            os.utime(agent, (moved, moved))
            with mock.patch.object(
                runtime_io,
                "glob_under",
                side_effect=AssertionError("re-globbed an unchanged directory"),
            ):
                again = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertEqual([(agent, moved)], again)

    def test_without_state_the_behaviour_is_uncached(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            self.assertEqual(
                claude_collector.agent_transcripts(parent),
                claude_collector.agent_transcripts(parent),
            )

    def test_a_parked_parent_keeps_its_subagent_activity(self) -> None:
        """The regression this cache design exists to avoid.

        The parent transcript is hours old; only the subagent file is fresh. The
        session must still report its subagent activity.
        """
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            stale = time.time() - 6 * 3600
            os.utime(parent, (stale, stale))
            found = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertEqual(len(found), 1)
            self.assertGreater(found[0][1], stale)


class SubagentWorkflowCacheTest(RuntimeTestCase):
    """The nested layout invalidates too, from the moment a run exists.

    A workflow run directory is created a beat before its first agent
    transcript, and a file appearing inside it moves no other directory's
    mtime. An entry cached in that window has to expire anyway, or every agent
    of that run stays invisible for the life of the process and its parked
    parent ages out of the window entirely.
    """

    def _fixture(self, root: str) -> tuple[str, str]:
        """A parent transcript and one empty workflow run directory."""
        parent = os.path.join(root, "abcd1234-session.jsonl")
        Path(parent).write_text("{}\n", encoding="utf-8")
        run = os.path.join(root, "abcd1234-session", "subagents", "workflows", "wf_1")
        os.makedirs(run)
        # Every real run directory holds a journal, which no glob pattern
        # matches: the directory is non-empty and the listing is still empty.
        Path(os.path.join(run, "journal.jsonl")).write_text("{}\n", encoding="utf-8")
        return parent, run

    def _names(self, found: list[tuple[str, float]]) -> list[str]:
        return sorted(os.path.basename(path) for path, _ in found)

    def _park(self, directory: str) -> None:
        """Age a directory's mtime before it is first listed.

        The signal under test is a real file creation moving a real directory
        mtime, so nothing here forges the change itself. Parking the starting
        value a minute back is only what keeps a filesystem with coarse
        timestamps from reporting the before and after as the same instant.
        """
        parked = time.time() - 60
        os.utime(directory, (parked, parked))

    def test_the_first_agent_in_a_known_empty_run_directory_is_seen(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent, run = self._fixture(root)
            self._park(run)
            self.assertEqual(
                [], claude_collector.agent_transcripts(parent, config=config, state=state)
            )

            Path(os.path.join(run, "agent-alpha.jsonl")).write_text("{}\n", encoding="utf-8")

            self.assertEqual(
                ["agent-alpha.jsonl"],
                self._names(claude_collector.agent_transcripts(parent, config=config, state=state)),
            )

    def test_a_replacement_agent_in_a_known_run_directory_is_seen(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent, run = self._fixture(root)
            first = os.path.join(run, "agent-alpha.jsonl")
            Path(first).write_text("{}\n", encoding="utf-8")
            self._park(run)
            self.assertEqual(
                ["agent-alpha.jsonl"],
                self._names(claude_collector.agent_transcripts(parent, config=config, state=state)),
            )

            os.remove(first)
            Path(os.path.join(run, "agent-beta.jsonl")).write_text("{}\n", encoding="utf-8")

            self.assertEqual(
                ["agent-beta.jsonl"],
                self._names(claude_collector.agent_transcripts(parent, config=config, state=state)),
            )

    def test_a_run_directory_created_after_the_first_listing_is_seen(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = os.path.join(root, "abcd1234-session.jsonl")
            Path(parent).write_text("{}\n", encoding="utf-8")
            os.makedirs(os.path.join(root, "abcd1234-session", "subagents"))
            self.assertEqual(
                [], claude_collector.agent_transcripts(parent, config=config, state=state)
            )

            run = os.path.join(root, "abcd1234-session", "subagents", "workflows", "wf_2")
            os.makedirs(run)
            Path(os.path.join(run, "agent-alpha.jsonl")).write_text("{}\n", encoding="utf-8")

            self.assertEqual(
                ["agent-alpha.jsonl"],
                self._names(claude_collector.agent_transcripts(parent, config=config, state=state)),
            )

    def test_a_transcript_written_during_the_glob_is_not_cached_away(self) -> None:
        """The stamp has to be taken before the listing, never after it.

        A stamp taken after the glob records the directory move the new
        transcript caused as already accounted for, so the listing that missed
        it looks current and is served for the life of the process.
        """
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = os.path.join(root, "abcd1234-session.jsonl")
            Path(parent).write_text("{}\n", encoding="utf-8")
            sub = os.path.join(root, "abcd1234-session", "subagents")
            os.makedirs(sub)
            Path(os.path.join(sub, "agent-a.jsonl")).write_text("{}\n", encoding="utf-8")
            self._park(sub)
            late = os.path.join(sub, "agent-b.jsonl")
            real_glob = runtime_io.glob_under

            def racing(base: str, *pattern: str) -> list[str]:
                listed = real_glob(base, *pattern)
                if not os.path.exists(late):
                    Path(late).write_text("{}\n", encoding="utf-8")
                return listed

            with mock.patch.object(runtime_io, "glob_under", side_effect=racing):
                claude_collector.agent_transcripts(parent, config=config, state=state)

            self.assertEqual(
                ["agent-a.jsonl", "agent-b.jsonl"],
                self._names(claude_collector.agent_transcripts(parent, config=config, state=state)),
            )


class SubagentScanCountTest(RuntimeTestCase):
    """The collector itself scans a session's subagents once per collection.

    Both of the call site's guarantees are load-bearing and neither is visible
    from ``agent_transcripts`` alone: handing the listing to
    ``load_subagents`` is what makes it one scan instead of two, and passing
    the runtime is what lets the second collection skip the glob.
    """

    def test_one_collection_costs_one_scan_and_the_next_costs_none(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project = projects / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / "abcd1234-3456-7890-abcd-ef1234567890.jsonl"
            transcript.write_text("{}\n", encoding="utf-8")
            sess_dir = project / "abcd1234-3456-7890-abcd-ef1234567890"
            (sess_dir / "subagents").mkdir(parents=True)
            (sess_dir / "subagents" / "agent-a.jsonl").write_text("{}\n", encoding="utf-8")
            real_glob = runtime_io.glob_under
            scans: list[str] = []

            def counting(base: str, *pattern: str) -> list[str]:
                if base == str(sess_dir):
                    scans.append(os.path.join(base, *pattern))
                return real_glob(base, *pattern)

            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
                mock.patch.object(runtime_io, "glob_under", side_effect=counting),
            ):
                first = collect_claude(now, 24, False)
                after_one = len(scans)
                second = collect_claude(now, 24, False)

        self.assertEqual(1, len(first), "fixture must produce exactly one session")
        self.assertEqual(1, len(second))
        self.assertEqual(
            len(claude_collector.SUBAGENT_GLOBS),
            after_one,
            f"one collection should list the subagent tree once, listed: {scans}",
        )
        self.assertEqual(after_one, len(scans), "an unchanged tree was listed again")


class OwnActivityTest(RuntimeTestCase):
    """`own_activity` is the session's own transcript and nothing below it.

    `last_activity` folds in every subagent and task write on purpose, so a
    parent parked on a long workflow does not age out of the window. That makes
    it useless for the one question the overlay reducer asks: has the human
    answered, or is a background agent simply writing while the prompt is still
    open (DRC-4097). The two fields must come apart here, or the reducer's guard
    is reading the subtree under another name.
    """

    def _store(self, root: Path, *, parent_at: float, agent_at: float) -> Path:
        projects = root / "projects"
        project = projects / "-w-proj"
        project.mkdir(parents=True)
        parent = project / "12345678-1111-2222-3333-444444444444.jsonl"
        parent.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": datetime.fromtimestamp(parent_at, UTC).isoformat(),
                    "message": {"content": []},
                }
            )
            + "\n"
        )
        os.utime(parent, (parent_at, parent_at))
        agent = project / "99999999-1111-2222-3333-444444444444.jsonl"
        agent.write_text(
            json.dumps(
                {
                    "type": "user",
                    "agentName": "reviewer",
                    "teamName": "session-12345678",
                    "timestamp": datetime.fromtimestamp(agent_at, UTC).isoformat(),
                    "message": {"content": "x"},
                }
            )
            + "\n"
        )
        os.utime(agent, (agent_at, agent_at))
        return projects

    def test_a_fresh_subagent_moves_last_activity_and_leaves_own_activity_alone(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            projects = self._store(Path(tmp), parent_at=now - 600, agent_at=now - 5)
            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
                mock.patch.object(notifications, "notify_mac"),
            ):
                sessions = collect_claude(now, 24, False)

        parent = next(s for s in sessions if s["sid"].startswith("12345678"))
        self.assertAlmostEqual(now - 5, parent["last_activity"], delta=1.0)
        self.assertAlmostEqual(now - 600, parent["own_activity"], delta=1.0)
        self.assertLess(parent["own_activity"], parent["last_activity"])

    def test_own_activity_follows_the_parent_transcript_when_it_is_the_fresher(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            projects = self._store(Path(tmp), parent_at=now - 5, agent_at=now - 600)
            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
                mock.patch.object(notifications, "notify_mac"),
            ):
                sessions = collect_claude(now, 24, False)

        parent = next(s for s in sessions if s["sid"].startswith("12345678"))
        self.assertAlmostEqual(now - 5, parent["own_activity"], delta=1.0)

    def _store_with_trailing_bookkeeping(
        self, root: Path, *, assistant_at: float, bookkeeping_at: float
    ) -> Path:
        """A parent transcript whose newest record is not the agent speaking."""
        projects = root / "projects"
        project = projects / "-w-proj"
        project.mkdir(parents=True)
        parent = project / "12345678-1111-2222-3333-444444444444.jsonl"
        parent.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": datetime.fromtimestamp(assistant_at, UTC).isoformat(),
                    "message": {"content": []},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "queue-operation",
                    "timestamp": datetime.fromtimestamp(bookkeeping_at, UTC).isoformat(),
                }
            )
            + "\n"
        )
        os.utime(parent, (bookkeeping_at, bookkeeping_at))
        return projects

    def test_a_bookkeeping_write_does_not_move_own_activity(self) -> None:
        """Only the agent speaking moves `own_activity`, not any write at all.

        A background task completing appends `queue-operation` and `attachment`
        records to the *parent* transcript while a question is still open on
        screen. Those are not the human answering, but they move the file's
        mtime, and the reducer's wait guard reads `own_activity` as "the agent
        resumed, so the wait is over". Keyed on mtime, one background task
        completing retired a live gate for the whole rest of its life — the
        session read `working` while it sat blocked, and `Needs you` said 0.
        """
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            projects = self._store_with_trailing_bookkeeping(
                Path(tmp), assistant_at=now - 600, bookkeeping_at=now - 5
            )
            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
                mock.patch.object(notifications, "notify_mac"),
            ):
                sessions = collect_claude(now, 24, False)

        parent = next(s for s in sessions if s["sid"].startswith("12345678"))
        self.assertAlmostEqual(now - 600, parent["own_activity"], delta=1.0)


class InputSummaryTest(unittest.TestCase):
    """What an open gate is asking, reduced to one bounded line. DRC-4015."""

    @staticmethod
    def _block(name: str, payload: Any) -> dict[str, Any]:
        return {"type": "tool_use", "id": "q-1", "name": name, "input": payload}

    def test_a_question_is_summarised_as_the_question(self) -> None:
        summary = claude_data.input_summary(
            self._block(
                "AskUserQuestion",
                {"questions": [{"header": "Auth", "question": "Which auth method?"}]},
            ),
            limit=160,
        )
        self.assertEqual("Which auth method?", summary)

    def test_several_questions_name_the_first_and_count_the_rest(self) -> None:
        summary = claude_data.input_summary(
            self._block(
                "AskUserQuestion",
                {"questions": [{"question": "Which one?"}, {"question": "And then?"}]},
            ),
            limit=160,
        )
        self.assertEqual("Which one? (+1 more)", summary)

    def test_a_plan_is_reduced_to_its_first_line(self) -> None:
        # Option B of three: a plan runs to thousands of words, and its first
        # line is its title in practice. A row is not where a document goes.
        plan = "# Rewrite the collector\n\nStep one, do the thing.\n" + ("x" * 5_000)
        summary = claude_data.input_summary(self._block("ExitPlanMode", {"plan": plan}), limit=160)
        self.assertEqual("Rewrite the collector", summary)

    def test_a_plan_that_opens_with_furniture_skips_to_the_line_that_names_it(self) -> None:
        # A plan can open with a blank line, a fence or a bullet, and none of
        # those name it. "```, waiting 2m" is a worse row than the tool's name.
        for opening in ("\n\n# Real title\nbody", "```\nReal title\nbody", "- Real title\nbody"):
            with self.subTest(opening=opening.split("\n")[0] or "(blank)"):
                summary = claude_data.input_summary(
                    self._block("ExitPlanMode", {"plan": opening}), limit=160
                )
                self.assertEqual("Real title", summary)

    def test_every_summary_is_capped(self) -> None:
        long_question = "y" * 400
        for block in (
            self._block("AskUserQuestion", {"questions": [{"question": long_question}]}),
            self._block("ExitPlanMode", {"plan": long_question}),
        ):
            self.assertEqual(40, len(claude_data.input_summary(block, limit=40)))

    def test_control_characters_do_not_reach_a_row(self) -> None:
        # A transcript is a file Cargento does not write, and this text lands in
        # the DOM.
        summary = claude_data.input_summary(
            self._block("AskUserQuestion", {"questions": [{"question": "we\x00ird\nthing"}]}),
            limit=160,
        )
        self.assertNotIn("\x00", summary)
        self.assertNotIn("\n", summary)

    def test_a_shape_that_is_not_there_summarises_to_nothing(self) -> None:
        # The record reaches disk on no schedule and its shape is Claude Code's
        # rather than something this repo pins, so absent has to be ordinary.
        payloads: list[dict[str, Any]] = [
            {},
            {"questions": []},
            {"questions": "not a list"},
            {"plan": None},
        ]
        for payload in payloads:
            for name in ("AskUserQuestion", "ExitPlanMode"):
                self.assertEqual(
                    "", claude_data.input_summary(self._block(name, payload), limit=160)
                )

    def test_a_pending_question_carries_its_text_through_the_transcript_read(self) -> None:
        record = {
            "type": "assistant",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "message": {
                "role": "assistant",
                "content": [
                    self._block(
                        "AskUserQuestion", {"questions": [{"question": "Force push to main?"}]}
                    )
                ],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            transcript.write_text(json.dumps(record) + "\n")
            config, state = runtime()
            info = claude_data.analyze_transcript(config, state, str(transcript))
        self.assertEqual("Force push to main?", info["pending_input_tool"]["asks"])


class QuestionOnTheRowTest(RuntimeTestCase):
    """The seam between the parse and the row, which nothing else covers."""

    def _row(self, tmp: str, payload: Any) -> dict[str, Any]:
        projects = Path(tmp) / "projects"
        project = projects / "-w-proj"
        project.mkdir(parents=True)
        transcript = project / "abcdef12-0000-0000-0000-000000000000.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": datetime.fromtimestamp(time.time() - 120, UTC).isoformat(),
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "q-1",
                                "name": "AskUserQuestion",
                                "input": payload,
                            }
                        ],
                    },
                }
            )
            + "\n"
        )
        with (
            store_patch(PROJECTS_DIR=str(projects)),
            store_patch(TASKS_DIR=str(projects / "tasks")),
        ):
            sessions = collect()["sessions"]
        return next(s for s in sessions if s["sid"].startswith("abcdef12"))

    def test_the_question_reaches_the_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            row = self._row(tmp, {"questions": [{"question": "Force push to main?"}]})
        self.assertEqual("needs_input", row["state"])
        self.assertTrue(
            row["state_detail"].startswith("Force push to main?, waiting"),
            row["state_detail"],
        )

    def test_a_record_carrying_no_question_keeps_the_old_wording(self) -> None:
        # The record reaches disk on no schedule and its shape is Claude Code's,
        # so absent has to read as ordinary rather than as an empty row.
        with tempfile.TemporaryDirectory() as tmp:
            row = self._row(tmp, {})
        self.assertEqual("needs_input", row["state"])
        self.assertTrue(
            row["state_detail"].startswith("open question (AskUserQuestion), waiting"),
            row["state_detail"],
        )
