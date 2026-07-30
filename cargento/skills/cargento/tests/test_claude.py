from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cargento_runtime import records

from .support import LegacyDashboardTestCase, dashboard


class ClaudeCollectorTest(LegacyDashboardTestCase):
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

            with mock.patch.object(dashboard, "TASKS_DIR", str(root)):
                tasks = dashboard.load_tasks()

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
            with mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)):
                found, user_event = dashboard.claude_hook_user_event(
                    str(transcript), session_id[:8]
                )

        self.assertTrue(found)
        self.assertEqual("user-before-hook", user_event)

    def test_new_user_event_clears_hook_without_comparing_clocks(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs["12345678"] = {
                "ts": 10_000.0,
                "message": "permission",
                "user_event": "before",
            }

        self.assertIsNotNone(dashboard.current_hook("12345678", "before", 0.0))
        self.assertIsNone(dashboard.current_hook("12345678", "after", 0.0))
        self.assertNotIn("12345678", dashboard._hook_notifs)

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
            before = dashboard.analyze_transcript(str(transcript))["last_user_event"]
            with dashboard._lock:
                dashboard._hook_notifs["12345678"] = {
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
            after = dashboard.analyze_transcript(str(transcript))["last_user_event"]

        self.assertNotEqual(before, after)
        self.assertIsNone(dashboard.current_hook("12345678", after, 0.0))

    def test_assistant_only_tail_does_not_change_hook_user_event(self) -> None:
        records = [
            {
                "type": "user",
                "uuid": "user-before-hook",
                "message": {"content": "approve"},
            },
            {
                "type": "assistant",
                "message": {"content": "x" * (dashboard.TAIL_BYTES + 100)},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "12345678-session.jsonl"
            transcript.write_text("\n".join(json.dumps(record) for record in records) + "\n")
            user_event = dashboard.analyze_transcript(str(transcript))["last_user_event"]

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
        filler = {"type": "assistant", "message": {"content": "x" * dashboard.TAIL_BYTES}}
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            transcript.write_text(
                "\n".join(json.dumps(record) for record in (question, filler, answer)) + "\n"
            )
            info = dashboard.analyze_transcript(str(transcript))

        self.assertIsNone(info["pending_input_tool"])

    def test_transcript_mtime_alone_does_not_clear_newer_hook(self) -> None:
        now = dashboard.time.time()
        event_time = dashboard.datetime.fromtimestamp(now - 10, dashboard.UTC).isoformat()
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
            with dashboard._lock:
                dashboard._hook_notifs["12345678"] = {
                    "ts": now - 1,
                    "message": "permission",
                }

            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)),
                mock.patch.object(dashboard, "TASKS_DIR", str(tasks)),
                mock.patch.object(dashboard, "notify_mac"),
            ):
                sessions = dashboard.collect_claude(now, 24, False)

        # Fresh activity now takes display precedence (the hook only
        # surfaces once the session goes quiet) — but the property this test
        # protects still holds: mtime alone must NOT clear the stored hook.
        self.assertEqual("working", sessions[0]["state"])
        self.assertIn("12345678", dashboard._hook_notifs)

    def test_claude_agent_identity_reads_only_a_bounded_prefix(self) -> None:
        record = json.dumps(
            {
                "type": "user",
                "agentName": "reviewer",
                "teamName": "session-12345678",
            }
        )
        source = mock.mock_open(read_data=(record + "\n" + ("x" * 100_000)).encode())
        runtime = dashboard._legacy_runtime()
        with (
            mock.patch("builtins.open", source),
            mock.patch.object(dashboard.os.path, "getsize", return_value=1_000_000),
            mock.patch.object(dashboard, "_legacy_runtime", return_value=runtime),
        ):
            identity = dashboard.claude_agent_identity("/fake/transcript.jsonl")

        self.assertEqual((True, "reviewer", "12345678"), identity)
        source().read.assert_called_once_with(runtime[0].claude_agent_scan_bytes)

    def test_claude_agent_identity_drops_a_partial_final_prefix_record(self) -> None:
        apparent_record = b'{"agentName":"reviewer","teamName":"session-badbad00"}'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.jsonl"
            path.write_bytes(apparent_record + b"-continued-without-newline")
            with (
                mock.patch.object(dashboard, "_AGENT_SCAN_BYTES", len(apparent_record)),
                mock.patch.object(
                    dashboard,
                    "_AGENT_CACHE_NEGATIVE_MIN_BYTES",
                    len(apparent_record) * 10,
                ),
            ):
                identity = dashboard.claude_agent_identity(str(path))

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
        runtime = dashboard._legacy_runtime()
        path = "/fake/transient-agent.jsonl"
        with (
            mock.patch(
                "builtins.open",
                side_effect=[PermissionError("temporarily locked"), source.return_value],
            ),
            mock.patch.object(
                dashboard.os.path,
                "getsize",
                return_value=runtime[0].claude_agent_cache_negative_min_bytes,
            ),
            mock.patch.object(dashboard, "_legacy_runtime", return_value=runtime),
        ):
            self.assertEqual((False, "", ""), dashboard.claude_agent_identity(path))
            self.assertNotIn(path, dashboard._agent_class_cache)
            self.assertEqual(
                (True, "reviewer", "12345678"),
                dashboard.claude_agent_identity(path),
            )

    def test_transient_agent_setting_read_failure_is_not_negative_cached(self) -> None:
        record = json.dumps({"agentSetting": dashboard.SPACEDOCK_ENSIGN})
        source = mock.mock_open(read_data=(record + "\n").encode())
        runtime = dashboard._legacy_runtime()
        path = "/fake/transient-setting.jsonl"
        with (
            mock.patch(
                "builtins.open",
                side_effect=[PermissionError("temporarily locked"), source.return_value],
            ),
            mock.patch.object(
                dashboard.os.path,
                "getsize",
                return_value=runtime[0].claude_agent_cache_negative_min_bytes,
            ),
            mock.patch.object(dashboard, "_legacy_runtime", return_value=runtime),
        ):
            self.assertEqual("", dashboard.claude_agent_setting(path))
            self.assertNotIn(path, dashboard._sd_role_cache)
            self.assertEqual(
                dashboard.SPACEDOCK_ENSIGN,
                dashboard.claude_agent_setting(path),
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
                mock.patch.object(dashboard, "_CWD_SCAN_LINES", 2),
                mock.patch.object(dashboard, "CLAUDE_CWD_LINE_BYTES", len(first_line)),
            ):
                self.assertEqual("/wanted/project", dashboard.claude_session_cwd(str(path)))
            with (
                mock.patch.object(dashboard, "_CWD_SCAN_LINES", 1),
                mock.patch.object(dashboard, "CLAUDE_CWD_LINE_BYTES", len(first_line)),
            ):
                self.assertEqual("", dashboard.claude_session_cwd(str(short_scan)))

    def test_configured_agent_transcript_remains_a_top_level_session(self) -> None:
        now = dashboard.time.time()
        timestamp = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
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
                            "agentName": dashboard.SPACEDOCK_ENSIGN,
                            "agentSetting": dashboard.SPACEDOCK_ENSIGN,
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
                mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)),
                mock.patch.object(dashboard, "TASKS_DIR", str(tasks)),
            ):
                sessions = dashboard.collect_claude(now, 24, False)
                classified_as_subagent = dashboard.claude_prefix_is_agent(session_id[:8])

        self.assertEqual([session_id[:8]], [session["session"] for session in sessions])
        self.assertFalse(classified_as_subagent)
        self.assertEqual(
            {"role": "ensign", "workflows": []},
            sessions[0]["spacedock"],
        )

    def test_young_agent_identity_can_gain_a_parent_relation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "young-agent.jsonl"
            transcript.write_text(
                json.dumps({"type": "agent-name", "agentName": "reviewer"}) + "\n"
            )

            self.assertEqual(
                (False, "reviewer", ""),
                dashboard.claude_agent_identity(str(transcript)),
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
                dashboard.claude_agent_identity(str(transcript)),
            )

    def test_young_agent_identity_can_gain_a_name_after_parent_relation(self) -> None:
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
                dashboard.claude_agent_identity(str(transcript)),
            )
            self.assertNotIn(str(transcript), dashboard._agent_class_cache)

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
                dashboard.claude_agent_identity(str(transcript)),
            )

    def test_parent_relation_without_agent_name_is_still_a_subagent(self) -> None:
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
                dashboard.claude_agent_identity(str(transcript)),
            )

    def test_claude_agent_negative_cache_waits_for_conclusive_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "young.jsonl"
            transcript.write_text("{}\n")
            self.assertEqual(
                (False, "", ""),
                dashboard.claude_agent_identity(str(transcript)),
            )
            self.assertNotIn(str(transcript), dashboard._agent_class_cache)

            transcript.write_text("{}\n" * 50)
            self.assertEqual(
                (False, "", ""),
                dashboard.claude_agent_identity(str(transcript)),
            )

        self.assertIn(str(transcript), dashboard._agent_class_cache)

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
                "message": {"content": "x" * (dashboard.TAIL_BYTES + 100)},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            transcript.write_text("\n".join(json.dumps(record) for record in records) + "\n")
            info = dashboard.analyze_transcript(str(transcript))

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
            info = dashboard.analyze_transcript(str(transcript))

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
                mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)),
                mock.patch.object(dashboard, "TASKS_DIR", str(tasks)),
            ):
                sessions = dashboard.collect_claude(dashboard.time.time(), 24, True)

        self.assertEqual(["12345678"], [session["session"] for session in sessions])

    def test_modern_subagent_transcripts_fold_into_parent_session(self) -> None:
        # Harness >= 2.x writes subagent transcripts as ordinary top-level
        # <uuid>.jsonl files whose records carry agentName and
        # teamName "session-<parent prefix>". They must NOT surface as
        # standalone sessions; they attach to the parent as named running
        # subagents, keep it working, and contribute to its output rate.
        now = dashboard.time.time()
        iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        stale_iso = dashboard.datetime.fromtimestamp(now - 600, dashboard.UTC).isoformat()
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
            dashboard.os.utime(parent_fp, (old, old))
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                sessions = dashboard.collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))
        parent = sessions[0]
        self.assertEqual(parent_id[:8], parent["session"])
        self.assertEqual("working", parent["state"])
        self.assertEqual(["spark-reviewer"], parent["subagents"])
        self.assertGreater(parent["rate_per_min"], 0)

    def test_load_tasks_coerces_malformed_field_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "12345678-abcd-ef00-1234-567890abcdef"
            root.mkdir(parents=True)
            (root / "1.json").write_text(
                json.dumps({"id": "1", "subject": {"nested": True}, "activeForm": 42, "status": 7})
            )
            (root / "2.json").write_text(json.dumps(["not", "a", "task"]))

            with mock.patch.object(dashboard, "TASKS_DIR", str(tmp)):
                tasks = dashboard.load_tasks()

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

            agents = dashboard.load_claude_subagents(str(sess), dashboard.time.time())

        # Both agents survive with the fallback label instead of TypeError.
        self.assertEqual(["subagent", "subagent"], [a["label"] for a in agents])

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

            agents = dashboard.load_claude_subagents(str(sess), dashboard.time.time())

        self.assertEqual({"plain-task", "review:bugs"}, {a["label"] for a in agents})

    def test_workflow_agents_keep_a_quiet_parent_working(self) -> None:
        # The live 5cb7c95e case: the main loop is parked awaiting a background
        # workflow, so its transcript goes quiet while ten workflow agents burn
        # tokens. The session read Idle with its task list hidden.
        now = dashboard.time.time()
        session_id = "5cb7c95e-0000-0000-0000-000000000000"
        stale = now - 400  # well past WORKING_THRESHOLD_SEC
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": dashboard.datetime.fromtimestamp(
                            stale, dashboard.UTC
                        ).isoformat(),
                        "message": {"role": "user", "content": "fan the detectors out"},
                    }
                )
                + "\n"
            )
            dashboard.os.utime(transcript, (stale, stale))
            run = project / session_id / "subagents" / "workflows" / "wf_506d8d41-ba5"
            run.mkdir(parents=True)
            agent = run / "agent-a88a43dd9.jsonl"
            agent.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": dashboard.datetime.fromtimestamp(
                            now - 5, dashboard.UTC
                        ).isoformat(),
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
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                session = dashboard.collect_claude(now, 24, False)[0]

        self.assertEqual("working", session["state"])
        self.assertEqual(["detect:backend"], session["subagents"])
        # The agent's output is the session's output — a parent that reads
        # Working at 0 tok/min is the same blind spot in the rate panel.
        self.assertGreater(session["rate_per_min"], 0)

    def test_workflow_agent_activity_holds_a_session_in_the_window(self) -> None:
        # last_activity drives both the freshness window and the "idle 23h"
        # age. A stale parent whose workflow agents wrote a minute ago has to
        # count as a minute old, or a long run ages out of the dashboard.
        now = dashboard.time.time()
        session_id = "d0d0d0d0-0000-0000-0000-000000000000"
        ancient = now - 30 * 3600  # older than the 24h window
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text("{}\n")
            dashboard.os.utime(transcript, (ancient, ancient))
            run = project / session_id / "subagents" / "workflows" / "wf_1"
            run.mkdir(parents=True)
            agent = run / "agent-1.jsonl"
            agent.write_text("{}\n")
            recent = now - 300  # quiet enough not to read Working
            dashboard.os.utime(agent, (recent, recent))
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                sessions = dashboard.collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertAlmostEqual(recent, sessions[0]["last_activity"], delta=2)

    def test_claude_session_cwd_reads_the_head_and_retries_when_absent(self) -> None:
        # The cwd drives every Claude project label, and none of its
        # behaviour was pinned: the scan bound, and the deliberate choice not
        # to cache a miss so a transcript that gains a cwd is picked up.
        with tempfile.TemporaryDirectory() as tmp:
            late = Path(tmp) / "late.jsonl"
            filler = "\n".join(json.dumps({"type": "x", "n": i}) for i in range(60))
            late.write_text(filler + "\n" + json.dumps({"type": "user", "cwd": "/w/late"}) + "\n")
            # Past the 50-line scan bound: not found, and not cached as a miss.
            self.assertEqual("", dashboard.claude_session_cwd(str(late)))
            self.assertNotIn(str(late), dashboard._cwd_cache)

            early = Path(tmp) / "early.jsonl"
            early.write_text("{}\n")
            self.assertEqual("", dashboard.claude_session_cwd(str(early)))
            # A miss must not be cached, or a transcript whose head is written
            # before its first cwd record keeps the fallback label forever.
            early.write_text(json.dumps({"type": "user", "cwd": "/w/early"}) + "\n")
            self.assertEqual("/w/early", dashboard.claude_session_cwd(str(early)))

            missing = Path(tmp) / "gone.jsonl"
            self.assertEqual("", dashboard.claude_session_cwd(str(missing)))

    def test_claude_project_falls_back_when_transcript_has_no_cwd(self) -> None:
        # A transcript head can be written before any record carries cwd. The
        # encoded directory name is lossy (Claude replaces every separator
        # with "-", so it cannot be split back apart), so the documented
        # fallback stays whole rather than guessing at a split.
        now = dashboard.time.time()
        home = "/Users/cl"
        encoded = f"{dashboard.encoded_home_prefix(home)}-git-spacedock-subspace"
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / encoded
            project_dir.mkdir(parents=True)
            (project_dir / "bbbb2222-0000-0000-0000-000000000000.jsonl").write_text("{}\n")
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
                mock.patch.object(dashboard, "HOME", home),
                mock.patch.object(dashboard, "HOME_PREFIX", dashboard.encoded_home_prefix(home)),
            ):
                sessions = dashboard.collect_claude(now, 24, False)

        self.assertEqual("git-spacedock-subspace", sessions[0]["project"])


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

            self.assertIsNone(dashboard.claude_session_title(str(transcript)))
            self.assertEqual({}, records.message_dict({"message": "str"}))
            self.assertEqual({}, records.message_dict("not-a-record"))
            self.assertEqual({"a": 1}, records.message_dict({"message": {"a": 1}}))

            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
            ):
                sessions = dashboard.collect_claude(now, 24, False)  # must not raise
                everything = dashboard.collect(24, True)

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
                mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
            ):
                sessions = dashboard.collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual("hostile path prompt", sessions[0]["title"])
