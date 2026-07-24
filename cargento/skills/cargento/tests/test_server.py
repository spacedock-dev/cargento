from __future__ import annotations

import contextlib
import http.client
import importlib.util
import io
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest import mock

SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("cargento_server", SERVER_PATH)
assert SPEC is not None
assert SPEC.loader is not None
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class CargentoServerTest(unittest.TestCase):
    def setUp(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()
            dashboard._last_state.clear()
        with dashboard._cache_lock:
            dashboard._meta_cache.clear()
            dashboard._cursor_title_cache.clear()
            dashboard._agent_class_cache.clear()
            dashboard._claude_title_cache.clear()
            dashboard._claude_user_event_cache.clear()
        with dashboard._scan_lock:
            dashboard._turn_scan.clear()
        with dashboard._collect_memo_lock:
            dashboard._collect_memo.clear()
        # No test may fire a real macOS popup ("[sample] permission" spam
        # during dev runs). Tests asserting popups use their own nested patch.
        notify_patcher = mock.patch.object(dashboard, "notify_mac")
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)

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

    def test_codex_meta_extracts_parent_thread_id(self) -> None:
        record = {
            "type": "session_meta",
            "payload": {
                "id": "child-thread",
                "thread_source": "subagent",
                "agent_nickname": "reviewer",
                "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent-thread"}}},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            path.write_text(json.dumps(record) + "\n")
            meta = dashboard.codex_meta(str(path))

        self.assertTrue(meta["subagent"])
        self.assertEqual("child-thread", meta["session_id"])
        self.assertEqual("parent-thread", meta["parent_session_id"])

    def test_gemini_set_snapshot_updates_summary_and_turns(self) -> None:
        messages = [
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:00Z",
                "content": "first prompt",
            },
            {
                "type": "gemini",
                "timestamp": "2026-01-01T00:00:05Z",
                "tokens": {"output": 42},
            },
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:10Z",
                "content": "resumed prompt",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-test.jsonl"
            path.write_text(
                json.dumps({"$set": {"messages": messages[:2]}})
                + "\n"
                + json.dumps({"$set": {"messages": messages}})
                + "\n"
            )

            info = dashboard.analyze_gemini_transcript(str(path))
            turns = dashboard.scan_turns(str(path), "gemini")

        self.assertEqual("resumed prompt", info["last_prompt"])
        self.assertEqual("resumed prompt", info["title"])
        self.assertEqual([(dashboard.parse_ts("2026-01-01T00:00:05Z"), 42)], info["usage_events"])
        self.assertEqual([5.0], turns["durations"])
        self.assertEqual(dashboard.parse_ts("2026-01-01T00:00:10Z"), turns["turn_start"])

    def test_large_repeated_gemini_snapshot_does_not_churn_dedup_cache(self) -> None:
        messages = [
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:00Z",
                "content": "first",
            },
            {
                "type": "gemini",
                "timestamp": "2026-01-01T00:00:05Z",
                "content": "answer",
            },
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:10Z",
                "content": "second",
            },
            {
                "type": "gemini",
                "timestamp": "2026-01-01T00:00:15Z",
                "content": "answer",
            },
        ]
        snapshot = json.dumps({"$set": {"messages": messages}})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-test.jsonl"
            path.write_text(snapshot + "\n" + snapshot + "\n")
            with mock.patch.object(dashboard, "GEMINI_SEEN_ENTRIES", 2):
                turns = dashboard.scan_turns(str(path), "gemini")

        self.assertEqual([5.0], turns["durations"])

    def test_antigravity_sessions_are_discovered_and_collected(self) -> None:
        now = dashboard.time.time()
        session_id = "c38d2d70-a01e-46f8-9286-60493c4c0e7e"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "antigravity-cli"
            conversations = root / "conversations"
            logs = root / "log"
            legacy = Path(tmp) / "legacy-gemini"
            conversations.mkdir(parents=True)
            logs.mkdir()
            legacy.mkdir()
            (conversations / f"{session_id}.db").write_bytes(b"SQLite fixture")
            (logs / "cli-20260723_141844.log").write_text(
                "I0723 14:18:44.913145 server.go:237] Creating CLI server "
                "backend: product=antigravity "
                "workspaceDirs=[/Users/test/repos/recce/bridge] "
                f"appDataDir={root} cascadeManager=true\n"
                "I0723 14:19:32.952541 server.go:917] Created conversation "
                f"{session_id}\n"
                "I0723 14:47:19.285802 input_loop.go:34] HandleUserInput "
                'called with text: "show my assigned issues"\n'
                "I0723 14:47:19.285967 conversation_manager.go:499] "
                f"Forwarding user message to conversation {session_id} "
                "(items=1, media=0)\n"
            )

            with (
                mock.patch.object(dashboard, "GEMINI_TMP", str(legacy)),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_CONVERSATIONS_DIR",
                    str(conversations),
                    create=True,
                ),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(logs), create=True),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(root / "cache" / "last_conversations.json"),
                    create=True,
                ),
            ):
                gemini = next(h for h in dashboard.HARNESSES if h[0] == "gemini")
                discovered = gemini[2]()
                sessions = dashboard.collect_gemini(now, 24, False)

        self.assertTrue(discovered)
        self.assertEqual(1, len(sessions))
        self.assertEqual("gemini", sessions[0]["harness"])
        self.assertEqual(session_id[:8], sessions[0]["session"])
        self.assertEqual("bridge", sessions[0]["project"])
        self.assertEqual("show my assigned issues", sessions[0]["title"])
        self.assertEqual("working", sessions[0]["state"])

    def test_antigravity_steps_supply_rate_action_and_turn_progress(self) -> None:
        now = dashboard.time.time()
        session_id = "c38d2d70-a01e-46f8-9286-60493c4c0e7e"

        def varint(value: int) -> bytes:
            encoded = bytearray()
            while value > 0x7F:
                encoded.append((value & 0x7F) | 0x80)
                value >>= 7
            encoded.append(value)
            return bytes(encoded)

        def int_field(number: int, value: int) -> bytes:
            return varint(number << 3) + varint(value)

        def bytes_field(number: int, value: bytes) -> bytes:
            return varint((number << 3) | 2) + varint(len(value)) + value

        def step_metadata(
            epoch: float,
            output_tokens: int | None = None,
            summary: str | None = None,
            action: str | None = None,
        ) -> bytes:
            timestamp = int_field(1, int(epoch))
            metadata = bytes_field(1, timestamp)
            if output_tokens is not None:
                usage = int_field(3, output_tokens)
                metadata += bytes_field(9, usage)
            if summary:
                metadata += bytes_field(30, summary.encode())
            if action:
                metadata += bytes_field(31, action.encode())
            return metadata

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "antigravity-cli"
            conversations = root / "conversations"
            logs = root / "log"
            legacy = Path(tmp) / "legacy-gemini"
            conversations.mkdir(parents=True)
            logs.mkdir()
            legacy.mkdir()
            database = conversations / f"{session_id}.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE steps ("
                "idx INTEGER PRIMARY KEY, step_type INTEGER, status INTEGER, "
                "metadata BLOB)"
            )
            rows = [
                (1, 14, 3, step_metadata(now - 180)),
                (2, 15, 3, step_metadata(now - 160, output_tokens=200)),
                (3, 15, 3, step_metadata(now - 130, output_tokens=300)),
                (4, 14, 3, step_metadata(now - 60)),
                (5, 15, 3, step_metadata(now - 50, output_tokens=600)),
                (
                    6,
                    21,
                    3,
                    step_metadata(
                        now - 40,
                        summary="Run project report",
                        action="Running project report",
                    ),
                ),
                (7, 15, 3, step_metadata(now - 10, output_tokens=400)),
            ]
            connection.executemany(
                "INSERT INTO steps (idx, step_type, status, metadata) VALUES (?, ?, ?, ?)",
                rows,
            )
            connection.commit()
            connection.close()
            (logs / "cli-20260723_141844.log").write_text(
                "I0723 14:18:44.913145 server.go:237] Creating CLI server "
                "backend: product=antigravity "
                "workspaceDirs=[/Users/test/repos/recce/bridge] "
                f"appDataDir={root} cascadeManager=true\n"
                "I0723 14:19:32.952541 server.go:917] Created conversation "
                f"{session_id}\n"
                "I0723 14:47:19.285802 input_loop.go:34] HandleUserInput "
                'called with text: "show my assigned issues"\n'
                "I0723 14:47:19.285967 conversation_manager.go:499] "
                f"Forwarding user message to conversation {session_id} "
                "(items=1, media=0)\n"
            )

            with (
                mock.patch.object(dashboard, "GEMINI_TMP", str(legacy)),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_CONVERSATIONS_DIR",
                    str(conversations),
                ),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(logs)),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(root / "cache" / "last_conversations.json"),
                ),
            ):
                sessions = dashboard.collect_gemini(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual(150, sessions[0]["rate_per_min"])
        self.assertEqual("Running project report", sessions[0]["state_detail"])
        self.assertEqual("1m", sessions[0]["turn"]["elapsed_h"])

    def test_notify_endpoint_accepts_valid_non_object_and_deep_json(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        bodies = [
            json.dumps({"session_id": "12345678", "message": "before\u0000after"}).encode(),
            b"[1,2,3]",
            b"null",
            b'"text"',
            (b"[" * 1200) + b"0" + (b"]" * 1200),
        ]
        try:
            with mock.patch.object(dashboard, "notify_mac") as notify:
                for body in bodies:
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
                    conn.request(
                        "POST",
                        "/api/notify",
                        body=body,
                        headers={"Content-Type": "application/json"},
                    )
                    response = conn.getresponse()
                    self.assertEqual(200, response.status)
                    self.assertEqual(b'{"ok":true}', response.read())
                    conn.close()
            self.assertNotIn("\x00", notify.call_args.args[1])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

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

    def test_cross_site_fetch_metadata_is_rejected(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            conn.request("GET", "/api/data", headers={"Sec-Fetch-Site": "cross-site"})
            response = conn.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_popup_caches_are_bounded_and_globally_rate_limited(self) -> None:
        with (
            mock.patch.object(dashboard, "MAX_CACHE_ENTRIES", 2),
            # session2 lands inside the 15s global floor and is dropped;
            # session3 lands after it and fires.
            mock.patch.object(dashboard.time, "time", side_effect=[100.0, 101.0, 120.0]),
            mock.patch.object(dashboard, "notify_mac") as notify,
        ):
            dashboard.maybe_popup("session1", "needs_input", "one")
            dashboard.maybe_popup("session2", "needs_input", "two")
            dashboard.maybe_popup("session3", "needs_input", "three")

        self.assertEqual(2, notify.call_count)
        self.assertLessEqual(len(dashboard._last_state), 2)
        self.assertLessEqual(len(dashboard._last_popup), 2)

    def test_metadata_cache_is_safe_under_concurrent_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meta.jsonl"
            path.write_text(json.dumps({"value": "ok"}) + "\n")

            def read() -> Any:
                return dashboard.first_line_meta(
                    str(path), lambda value: {"value": value.get("value")}
                )

            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(lambda _: read(), range(100)))

        self.assertTrue(all(result == {"value": "ok"} for result in results))
        self.assertEqual(1, len(dashboard._meta_cache))

    def test_goose_tool_response_is_not_a_user_prompt(self) -> None:
        self.assertFalse(
            dashboard.goose_user_prompt(
                [{"type": "toolResponse", "toolResult": {"status": "success"}}]
            )
        )
        self.assertTrue(dashboard.goose_user_prompt([{"type": "text", "text": "hello"}]))

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
        with (
            mock.patch("builtins.open", source),
            mock.patch.object(dashboard.os.path, "getsize", return_value=1_000_000),
        ):
            identity = dashboard.claude_agent_identity("/fake/transcript.jsonl")

        self.assertEqual((True, "reviewer", "12345678"), identity)
        source().read.assert_called_once_with(dashboard._AGENT_SCAN_BYTES)

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

    def test_codex_subagent_usage_is_added_after_own_start_boundary(self) -> None:
        now = dashboard.time.time()

        def timestamp(offset: float) -> str:
            iso = dashboard.datetime.fromtimestamp(now + offset, dashboard.UTC).isoformat()
            return str(iso)

        parent_id = "11111111-1111-1111-1111-111111111111"
        child_id = "22222222-2222-2222-2222-222222222222"
        parent_meta = {
            "type": "session_meta",
            "payload": {"id": parent_id, "cwd": "/tmp/project"},
        }
        child_meta = {
            "type": "session_meta",
            "payload": {
                "id": child_id,
                "thread_source": "subagent",
                "agent_nickname": "worker",
                "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent_id}}},
            },
        }

        def token_record(offset: float, output_tokens: int) -> dict[str, Any]:
            return {
                "type": "event_msg",
                "timestamp": timestamp(offset),
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"output_tokens": output_tokens}},
                },
            }

        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026" / "01" / "01"
            day.mkdir(parents=True)
            parent = day / "rollout-parent.jsonl"
            child = day / "rollout-child.jsonl"
            parent.write_text(
                "\n".join(json.dumps(record) for record in [parent_meta, token_record(-10, 100)])
                + "\n"
            )
            child.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        child_meta,
                        token_record(-30, 900),
                        {
                            "type": "event_msg",
                            "timestamp": timestamp(-20),
                            "payload": {
                                "type": "task_started",
                                "started_at": now - 20,
                            },
                        },
                        token_record(-10, 900),
                    ]
                )
                + "\n"
            )

            with mock.patch.object(dashboard, "CODEX_SESSIONS_DIR", str(Path(tmp))):
                sessions = dashboard.collect_codex(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual(100, sessions[0]["rate_per_min"])
        self.assertEqual(["worker"], sessions[0]["subagents"])

    def test_large_transcript_recovers_turn_start_before_bounded_tail(self) -> None:
        prompt_time = "2026-01-01T00:00:00Z"
        prompt = {
            "type": "user",
            "timestamp": prompt_time,
            "message": {"content": "long request"},
        }
        events = [
            {
                "type": "assistant",
                "timestamp": f"2026-01-01T00:00:{second:02d}Z",
                "message": {"content": "x" * 40},
            }
            for second in range(1, 20)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.jsonl"
            path.write_text("\n".join(json.dumps(record) for record in [prompt, *events]) + "\n")
            with mock.patch.object(dashboard, "TURN_SCAN_MAX_BYTES", 200):
                turns = dashboard.scan_turns(str(path), "claude")

        self.assertEqual(dashboard.parse_ts(prompt_time), turns["turn_start"])

    def test_large_append_recovers_new_turn_start_from_skipped_delta(self) -> None:
        first_time = "2026-01-01T00:00:00Z"
        second_time = "2026-01-01T00:01:00Z"
        first_prompt = {
            "type": "user",
            "timestamp": first_time,
            "message": {"content": "first"},
        }
        second_prompt = {
            "type": "user",
            "timestamp": second_time,
            "message": {"content": "second"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "growing.jsonl"
            path.write_text(json.dumps(first_prompt) + "\n")
            with mock.patch.object(dashboard, "TURN_SCAN_MAX_BYTES", 200):
                dashboard.scan_turns(str(path), "claude")
                with path.open("a") as output:
                    output.write(json.dumps(second_prompt) + "\n")
                    for second in range(1, 20):
                        output.write(
                            json.dumps(
                                {
                                    "type": "assistant",
                                    "timestamp": (f"2026-01-01T00:01:{second:02d}Z"),
                                    "message": {"content": "x" * 40},
                                }
                            )
                            + "\n"
                        )
                turns = dashboard.scan_turns(str(path), "claude")

        self.assertEqual(dashboard.parse_ts(second_time), turns["turn_start"])

    def test_collect_json_single_flights_concurrent_cold_requests(self) -> None:
        calls: list[tuple[float, bool]] = []
        calls_lock = threading.Lock()

        def fake_collect(window_hours: float, show_all: bool) -> dict[str, Any]:
            with calls_lock:
                calls.append((window_hours, show_all))
            dashboard.time.sleep(0.02)
            return {"window_hours": window_hours, "show_all": show_all}

        with mock.patch.object(dashboard, "collect", fake_collect):
            with ThreadPoolExecutor(max_workers=12) as pool:
                bodies = list(pool.map(lambda _: dashboard.collect_json(24, False), range(24)))
            alternate = dashboard.collect_json(24, True)

        self.assertEqual(1, calls.count((24, False)))
        self.assertEqual(1, calls.count((24, True)))
        self.assertEqual(1, len(set(bodies)))
        self.assertNotEqual(bodies[0], alternate)
        self.assertEqual(2, len(dashboard._collect_memo))

    def test_collector_failure_is_exposed_in_harness_status(self) -> None:
        def fail(*_args: object) -> list[dict[str, Any]]:
            raise RuntimeError("broken store")

        harnesses = [("test", "Test", lambda: True, fail)]
        with (
            mock.patch.object(dashboard, "HARNESSES", harnesses),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = dashboard.collect(24, False)

        self.assertTrue(result["harnesses"][0]["discovered"])
        self.assertEqual("RuntimeError: broken store", result["harnesses"][0]["error"])

    def test_page_marks_repeated_refresh_failures_as_stalled(self) -> None:
        self.assertIn('id="live-status"', dashboard.PAGE)
        self.assertIn("window.__refreshFailures < 2", dashboard.PAGE)
        self.assertIn("stalled · last update", dashboard.PAGE)
        self.assertIn("console.error", dashboard.PAGE)
        self.assertIn("latestSettledRefresh", dashboard.PAGE)
        self.assertIn("sequence < latestSettledRefresh", dashboard.PAGE)

    def test_output_rate_rows_use_hoverable_harness_badges(self) -> None:
        self.assertIn(
            '<span class="rrow-badge">${badge(r.key, true)}</span>',
            dashboard.PAGE,
        )

    def test_page_ships_trailing_rate_sparklines(self) -> None:
        # Overall + per-session trailing sparklines: client-side ring buffers
        # over a 5-minute window, rendered as SVG in the rate tile and cards.
        self.assertIn("SPARK_WINDOW_SEC = 300", dashboard.PAGE)
        self.assertIn("const rateHistory = []", dashboard.PAGE)
        self.assertIn("const sessRateHistory = new Map()", dashboard.PAGE)
        self.assertIn("function recordRates", dashboard.PAGE)
        self.assertIn("function sparkSVG", dashboard.PAGE)
        self.assertIn('class="spark-wrap"', dashboard.PAGE)
        self.assertIn('class="rate-spark"', dashboard.PAGE)
        # Buffers only grow on fresh payloads and drop points past the window.
        self.assertIn("recordRates(data)", dashboard.PAGE)
        self.assertIn("arr.shift()", dashboard.PAGE)

    def test_base_session_exposes_full_sid_and_truncated_display_id(self) -> None:
        s = dashboard.base_session("gemini", "session-abcdef123", "proj")
        self.assertEqual("session-", s["session"])  # display stays 8 chars
        self.assertEqual("session-abcdef123", s["sid"])  # identity stays full

    # Functional DOM/window stubs for executing the page script under node:
    # listeners are captured so tests can fire synthetic events, and
    # getElementById serves whatever elements a test registers in __els.
    PAGE_JS_STUBS = """
const __listeners = {};
const __els = {};
const __fire = (type, ev) => (__listeners[type] || []).forEach(f => f(ev));
// Deterministic viewer clock: sparkline points are stamped with Date.now()
// at receipt, so tests pin it and advance it explicitly via __setNow.
let __nowSec = 1000;
const __setNow = s => { __nowSec = s; };
Date.now = () => __nowSec * 1000;
const location = {search: ""};
const document = {
  addEventListener(type, fn){ (__listeners[type] = __listeners[type] || []).push(fn); },
  getElementById(id){ return __els[id] || null; },
  createElement(){ return {textContent: "", style: {}, appendChild(){}}; },
  createTextNode(){ return {textContent: ""}; },
  activeElement: null,
  hidden: false,
  title: ""
};
const window = {addEventListener(type, fn){
  (__listeners["window:" + type] = __listeners["window:" + type] || []).push(fn); }};
const fetch = () => new Promise(() => {});
const setInterval = () => 0;
"""

    def _run_page_js(self, checks: str) -> Any:
        match = re.search(r"<script>\n(.*?)</script>", dashboard.PAGE, re.DOTALL)
        assert match is not None
        script = match.group(1)
        with tempfile.TemporaryDirectory() as tmp:
            js = Path(tmp) / "page_test.js"
            js.write_text(self.PAGE_JS_STUBS + script + checks)
            proc = subprocess.run(
                [shutil.which("node") or "node", str(js)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(0, proc.returncode, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_sparkline_buffers_behave_correctly(self) -> None:
        # Execute the page's actual JS (ring buffers + SVG generation) under
        # node with a minimal DOM stub, and assert on observable behavior.
        checks = """
const out = {};
{
  const arr = [];
  for(let t = 0; t <= 400; t += 5) pushPoint(arr, t, t);
  pushPoint(arr, 400, 999); // same-timestamp replay must be ignored
  out.pruned = {len: arr.length, first: arr[0].t,
                last: arr[arr.length-1].t, lastV: arr[arr.length-1].v};
}
{
  // Two live sessions whose display ids truncate identically must not
  // share one buffer (Gemini "session-*" fallback ids all become
  // "session-" after display truncation).
  recordRates({generated: 1000, summary: {rate_per_min: 14}, sessions: [
    {harness:"gemini", session:"session-", sid:"session-aaaa", rate_per_min:5},
    {harness:"gemini", session:"session-", sid:"session-bbbb", rate_per_min:9}]});
  const a = sessRateHistory.get("gemini:session-aaaa");
  const b = sessRateHistory.get("gemini:session-bbbb");
  out.aliasing = {buffers: sessRateHistory.size,
                  a: a && a[0] && a[0].v, b: b && b[0] && b[0].v};
  __setNow(1005);
  recordRates({generated: 1005, summary: {rate_per_min: 6}, sessions: [
    {harness:"gemini", session:"session-", sid:"session-aaaa", rate_per_min:6}]});
  const a2 = sessRateHistory.get("gemini:session-aaaa") || [];
  out.dropped = {buffers: sessRateHistory.size, aLen: a2.length};
}
{
  // Points carry the VIEWER's clock: a skewed/lagging server `generated`
  // must not shift timestamps, and a replayed `generated` records nothing.
  __setNow(1010);
  recordRates({generated: 999111, summary: {rate_per_min: 3}, sessions: []});
  const last = rateHistory[rateHistory.length-1];
  const lenBefore = rateHistory.length;
  __setNow(1011);
  recordRates({generated: 999111, summary: {rate_per_min: 4}, sessions: []});
  out.clock = {t: last.t, v: last.v, replayDropped: rateHistory.length === lenBefore};
}
{
  const pts = [{t:900, v:0}, {t:950, v:50}, {t:1000, v:100}];
  const svg = sparkSVG(pts, 1000, 100, 46, true);
  const nums = (svg.match(/-?\\d+(\\.\\d+)?/g) || []).map(Number);
  out.svg = {hasLine: svg.includes("<polyline"),
             finite: nums.length > 0 && nums.every(Number.isFinite),
             single: !sparkSVG([{t:1000, v:1}], 1000, 100, 46, true)
                       .includes("<polyline")};
}
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        # 300s window over t=0..400 step 5 keeps t=100..400; duplicate dropped.
        self.assertEqual({"len": 61, "first": 100, "last": 400, "lastV": 400}, out["pruned"])
        self.assertEqual({"buffers": 2, "a": 5, "b": 9}, out["aliasing"])
        # Departed session-bbbb is pruned; session-aaaa accumulates.
        self.assertEqual({"buffers": 1, "aLen": 2}, out["dropped"])
        # Viewer-clock stamping: server said 999111, viewer clock said 1010.
        self.assertEqual({"t": 1010, "v": 3, "replayDropped": True}, out["clock"])
        self.assertEqual({"hasLine": True, "finite": True, "single": True}, out["svg"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_needs_input_ui_uses_block_anchor_and_displayed_count(self) -> None:
        checks = """
__els.app = {innerHTML:""};
const activeNeed = {
  harness:"claude", session:"12345678", sid:"12345678", project:"sample",
  title:null, last_prompt:"Fallback prompt", state:"needs_input",
  state_detail:"permission needed", active:true, last_activity:100,
  blocked_since:970, rate_per_min:0, total:0, done:0, open:0,
  progress_pct:0, eta_h:null, turn:null, subagents:[], tasks:[]
};
const inactiveNeed = {...activeNeed, sid:"old", session:"old", active:false};
const data = {
  generated:1000, window_hours:24, show_all:true, harnesses:[],
  summary:{needs_input:99, working:0, rate_per_min:0, active_sessions:1,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0},
  sessions:[activeNeed, inactiveNeed]
};
const row = needRow(data, activeNeed);
render(data);
console.log(JSON.stringify({
  rowUsesPrompt: row.includes("Fallback prompt"),
  rowUsesAnchor: row.includes(">30s<"),
  title: document.title,
  shownNeeds: (__els.app.innerHTML.match(/class="need"/g) || []).length
}));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            {
                "rowUsesPrompt": True,
                "rowUsesAnchor": True,
                "title": "(1!) Cargento",
                "shownNeeds": 1,
            },
            out,
        )

    def _post_notify(self, port: int, body: dict[str, Any]) -> bytes:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request(
            "POST",
            "/api/notify",
            body=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        self.assertEqual(200, response.status)
        data = response.read()
        conn.close()
        return data

    def test_notify_from_subagent_session_is_suppressed(self) -> None:
        # Subagent sessions emit Notification-hook events too (permission
        # prompts inside agents); they must not raise popups or hook state.
        now = dashboard.time.time()
        child_id = "cccc3333-0000-0000-0000-000000000000"
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            (proj / f"{child_id}.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "agentName": "helper",
                        "teamName": "session-aaaa1111",
                        "timestamp": dashboard.datetime.fromtimestamp(
                            now, dashboard.UTC
                        ).isoformat(),
                        "message": {"role": "user", "content": "x"},
                    }
                )
                + "\n"
            )
            httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with (
                    mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                    mock.patch.object(dashboard, "notify_mac") as notify,
                ):
                    data = self._post_notify(
                        httpd.server_port,
                        {"session_id": child_id, "message": "permission"},
                    )
                self.assertIn(b"suppressed", data)
                notify.assert_not_called()
                with dashboard._lock:
                    self.assertNotIn(child_id[:8], dashboard._hook_notifs)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_notify_repeated_identical_message_popups_once(self) -> None:
        # Claude re-emits the same notification while a session stays blocked;
        # only the first within the suppression window may popup. A different
        # message from the same session still pops.
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def expire_cooldowns() -> None:
            with dashboard._lock:
                dashboard._last_popup["fedcba98"] = dashboard.time.time() - 120
                dashboard._last_popup["_global"] = dashboard.time.time() - 120

        try:
            with mock.patch.object(dashboard, "notify_mac") as notify:
                self._post_notify(
                    httpd.server_port,
                    {"session_id": "fedcba98", "message": "permission needed"},
                )
                self.assertEqual(1, notify.call_count)
                expire_cooldowns()
                self._post_notify(
                    httpd.server_port,
                    {"session_id": "fedcba98", "message": "permission needed"},
                )
                self.assertEqual(1, notify.call_count)  # identical: suppressed
                expire_cooldowns()
                self._post_notify(
                    httpd.server_port,
                    {"session_id": "fedcba98", "message": "open question"},
                )
                self.assertEqual(2, notify.call_count)  # new message: pops
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_hook_without_marker_clears_on_newer_parsed_event(self) -> None:
        # Payloads without transcript_path (the documented curl simulation,
        # older Claude Code versions) get no user-event marker; they must
        # fall back to the parsed-timestamp rule instead of sticking forever.
        with dashboard._lock:
            dashboard._hook_notifs["cafe1234"] = {"ts": 1000.0, "message": "hi"}
        self.assertIsNotNone(dashboard.current_hook("cafe1234", None, 999.0))
        self.assertIsNone(dashboard.current_hook("cafe1234", None, 1001.0))
        with dashboard._lock:
            self.assertNotIn("cafe1234", dashboard._hook_notifs)

    def test_hook_does_not_mark_actively_working_session_blocked(self) -> None:
        # Claude Code emits "waiting for your input" notifications for
        # sessions that keep running via background tasks (live case
        # 936f2c2b). While the transcript still receives events, the session
        # reads Working; the hook only surfaces once the session goes quiet.
        now = dashboard.time.time()
        session_id = "dddd4444-0000-0000-0000-000000000000"

        def transcript(last_offset: float) -> str:
            iso_new = dashboard.datetime.fromtimestamp(now - last_offset, dashboard.UTC).isoformat()
            return (
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": session_id,
                        "uuid": "u-1",
                        "timestamp": dashboard.datetime.fromtimestamp(
                            now - 900, dashboard.UTC
                        ).isoformat(),
                        "message": {"role": "user", "content": "kick off reviews"},
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "system",
                        "sessionId": session_id,
                        "timestamp": iso_new,
                        "content": "background shell event",
                    }
                )
                + "\n"
            )

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            fp = proj / f"{session_id}.jsonl"

            def collect_with(last_offset: float) -> dict[str, Any]:
                fp.write_text(transcript(last_offset))
                with dashboard._lock:
                    dashboard._hook_notifs[session_id[:8]] = {
                        "ts": now - 60,
                        "message": "Claude is waiting for your input",
                        "user_event": "u-1",  # marker unchanged: hook uncleared
                    }
                with (
                    mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                    mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
                ):
                    sessions = dashboard.collect_claude(now, 24, False)
                return next(s for s in sessions if s["session"] == session_id[:8])

            fresh = collect_with(5)  # events still flowing -> working
            self.assertEqual("working", fresh["state"])
            # NOTE: os.utime so mtime matches the stale story
            fp.write_text(transcript(600))
            old = now - 600
            dashboard.os.utime(fp, (old, old))
            with dashboard._lock:
                dashboard._hook_notifs[session_id[:8]] = {
                    "ts": now - 60,
                    "message": "Claude is waiting for your input",
                    "user_event": "u-1",
                }
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                sessions = dashboard.collect_claude(now, 24, False)
            quiet = next(s for s in sessions if s["session"] == session_id[:8])
            self.assertEqual("needs_input", quiet["state"])

    def test_idle_nudge_pops_but_never_marks_session_blocked(self) -> None:
        # Claude Code emits "Claude is waiting for your input" after EVERY
        # completed turn. That is the dashboard's own definition of idle —
        # it may popup once as a nudge but must never flip a session to
        # needs_input. Permission prompts (different message) still do.
        now = dashboard.time.time()
        session_id = "ffff6666-0000-0000-0000-000000000000"
        old_iso = dashboard.datetime.fromtimestamp(now - 600, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            fp = proj / f"{session_id}.jsonl"
            fp.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": session_id,
                        "uuid": "u-1",
                        "timestamp": old_iso,
                        "message": {"role": "user", "content": "do the thing"},
                    }
                )
                + "\n"
            )
            old = now - 600
            dashboard.os.utime(fp, (old, old))
            httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with (
                    mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                    mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
                    mock.patch.object(dashboard, "notify_mac") as notify,
                ):
                    # Idle nudge: pops once, no blocked state, no stored hook.
                    self._post_notify(
                        httpd.server_port,
                        {
                            "session_id": session_id,
                            "message": "Claude is waiting for your input",
                            "transcript_path": str(fp),
                        },
                    )
                    self.assertEqual(1, notify.call_count)
                    with dashboard._lock:
                        self.assertNotIn(session_id[:8], dashboard._hook_notifs)
                    sessions = dashboard.collect_claude(now, 24, False)
                    target = next(s for s in sessions if s["session"] == session_id[:8])
                    self.assertEqual("idle", target["state"])

                    # A permission prompt still blocks when the session is quiet.
                    self._post_notify(
                        httpd.server_port,
                        {
                            "session_id": session_id,
                            "message": "Claude needs your permission to use Bash",
                            "transcript_path": str(fp),
                        },
                    )
                    sessions = dashboard.collect_claude(now, 24, False)
                    target = next(s for s in sessions if s["session"] == session_id[:8])
                    self.assertEqual("needs_input", target["state"])
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_structured_notification_type_overrides_message_text(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch.object(dashboard, "notify_mac") as notify:
                # Informational notifications neither block nor claim that
                # Claude is waiting on the human.
                self._post_notify(
                    httpd.server_port,
                    {
                        "session_id": "aaaa1111",
                        "hook_event_name": "Notification",
                        "notification_type": "auth_success",
                        "message": "Authentication successful",
                    },
                )
                self.assertEqual(0, notify.call_count)
                self.assertNotIn("aaaa1111", dashboard._hook_notifs)

                # Structured idle type wins even when the message is a
                # version/localization variant that lacks the old prefix, and
                # clears any older standing prompt for this session.
                with dashboard._lock:
                    dashboard._hook_notifs["bbbb2222"] = {
                        "ts": dashboard.time.time() - 60,
                        "message": "older permission prompt",
                    }
                    dashboard._last_state["bbbb2222"] = "needs_input"
                self._post_notify(
                    httpd.server_port,
                    {
                        "session_id": "bbbb2222",
                        "hook_event_name": "Notification",
                        "notification_type": "idle_prompt",
                        "message": "Your agent has finished its turn",
                    },
                )
                self.assertEqual(1, notify.call_count)
                self.assertNotIn("bbbb2222", dashboard._hook_notifs)
                self.assertNotIn("bbbb2222", dashboard._last_state)

                with dashboard._lock:
                    dashboard._last_popup["_global"] = dashboard.time.time() - 120

                # Structured permission type also wins over misleading text.
                self._post_notify(
                    httpd.server_port,
                    {
                        "session_id": "cccc3333",
                        "hook_event_name": "Notification",
                        "notification_type": "permission_prompt",
                        "message": "Claude is waiting for your input to approve Bash",
                    },
                )
                self.assertEqual(2, notify.call_count)
                self.assertIn("cccc3333", dashboard._hook_notifs)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_notification_disposition_covers_documented_types(self) -> None:
        expected = {
            "idle_prompt": (False, True),
            "permission_prompt": (True, True),
            "auth_success": (False, False),
            "elicitation_dialog": (True, True),
            "elicitation_complete": (False, False),
            "elicitation_response": (False, False),
            "agent_needs_input": (True, True),
            "agent_completed": (False, False),
        }
        for notification_type, disposition in expected.items():
            with self.subTest(notification_type=notification_type):
                self.assertEqual(
                    disposition,
                    dashboard.notification_disposition(notification_type, "variant text"),
                )

    def test_elicitation_completion_clears_dialog_hook(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs["feed1234"] = {
                "ts": dashboard.time.time() - 30,
                "message": "MCP input requested",
            }
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            self._post_notify(
                httpd.server_port,
                {
                    "session_id": "feed1234",
                    "hook_event_name": "Notification",
                    "notification_type": "elicitation_complete",
                    "message": "MCP elicitation completed",
                },
            )
            with dashboard._lock:
                self.assertNotIn("feed1234", dashboard._hook_notifs)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_session_end_hook_clears_standing_permission_state(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs["deadbeef"] = {
                "ts": dashboard.time.time() - 60,
                "message": "permission needed",
            }
            dashboard._last_state["deadbeef"] = "needs_input"
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            data = self._post_notify(
                httpd.server_port,
                {
                    "session_id": "deadbeef-0000-0000-0000-000000000000",
                    "hook_event_name": "SessionEnd",
                    "reason": "prompt_input_exit",
                },
            )
            self.assertIn(b'"cleared":"session_end"', data)
            with dashboard._lock:
                self.assertNotIn("deadbeef", dashboard._hook_notifs)
                self.assertNotIn("deadbeef", dashboard._last_state)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_hook_block_uses_hook_time_and_inactive_sessions_are_idle(self) -> None:
        now = dashboard.time.time()
        session_id = "abcd1234-0000-0000-0000-000000000000"
        event_time = dashboard.datetime.fromtimestamp(now - 600, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "user-before-hook",
                        "timestamp": event_time,
                        "message": {"role": "user", "content": "run it"},
                    }
                )
                + "\n"
            )
            old = now - 600
            dashboard.os.utime(transcript, (old, old))
            hook_time = now - 45
            with dashboard._lock:
                dashboard._hook_notifs[session_id[:8]] = {
                    "ts": hook_time,
                    "message": "permission needed",
                    "user_event": "user-before-hook",
                }
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                active = dashboard.collect_claude(now, 24, False)[0]
                inactive = dashboard.collect_claude(now, 0.1, True)[0]

        self.assertEqual("needs_input", active["state"])
        self.assertEqual(hook_time, active["blocked_since"])
        self.assertEqual("idle", inactive["state"])

    def test_transcript_open_question_outranks_fresh_activity(self) -> None:
        now = dashboard.time.time()
        session_id = "face9999-0000-0000-0000-000000000000"
        question_time = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": question_time,
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
                )
                + "\n"
            )
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                session = dashboard.collect_claude(now, 24, False)[0]

        self.assertEqual("needs_input", session["state"])
        self.assertEqual(dashboard.parse_ts(question_time), session["blocked_since"])

    def test_background_task_flap_lifecycle_end_to_end(self) -> None:
        # Full lifecycle of the live 936f2c2b case, through the real notify
        # endpoint: a turn ends into background work, Claude re-emits
        # "waiting for your input" hooks, background events keep the
        # transcript active. The session must read Working steadily (no
        # needs_input flapping), clear the hook when the session self-resumes
        # with a new user record, and only surface needs_input once the
        # session is genuinely quiet with a standing hook.
        now = dashboard.time.time()
        session_id = "eeee5555-0000-0000-0000-000000000000"

        def iso(age: float) -> str:
            return str(dashboard.datetime.fromtimestamp(now - age, dashboard.UTC).isoformat())

        def user_rec(uuid: str, age: float, text: str) -> str:
            return (
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": session_id,
                        "uuid": uuid,
                        "timestamp": iso(age),
                        "message": {"role": "user", "content": text},
                    }
                )
                + "\n"
            )

        def system_rec(age: float) -> str:
            return (
                json.dumps(
                    {
                        "type": "system",
                        "sessionId": session_id,
                        "timestamp": iso(age),
                        "content": "background shell event",
                    }
                )
                + "\n"
            )

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            fp = proj / f"{session_id}.jsonl"
            patches = (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            )
            httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with patches[0], patches[1]:

                    def post_hook() -> None:
                        # Permission-kind message: idle nudges never block at
                        # all (see test_idle_nudge_pops_but_never_marks_...).
                        self._post_notify(
                            httpd.server_port,
                            {
                                "session_id": session_id,
                                "message": "Claude needs your permission to use Bash",
                                "transcript_path": str(fp),
                            },
                        )

                    def state() -> str:
                        result = dashboard.collect_claude(now, 24, False)
                        return str(
                            next(s for s in result if s["session"] == session_id[:8])["state"]
                        )

                    # Turn ended; hook fires; background events keep flowing.
                    fp.write_text(user_rec("u-1", 300, "review the PRs") + system_rec(50))
                    post_hook()
                    self.assertEqual("working", state())

                    # More background events + a RE-POSTED identical hook:
                    # still working, poll after poll — no flapping.
                    fp.write_text(
                        user_rec("u-1", 300, "review the PRs") + system_rec(50) + system_rec(20)
                    )
                    post_hook()
                    self.assertEqual("working", state())
                    self.assertEqual("working", state())

                    # Background work completes; the session self-resumes with
                    # a NEW user record (task notification): hook must CLEAR.
                    fp.write_text(
                        user_rec("u-1", 300, "review the PRs")
                        + system_rec(50)
                        + user_rec("u-2", 10, "task-notification: reviews done")
                    )
                    self.assertEqual("working", state())
                    with dashboard._lock:
                        self.assertNotIn(session_id[:8], dashboard._hook_notifs)

                    # Final turn ends for real: standing hook + genuinely
                    # quiet transcript (old record timestamps AND old mtime)
                    # -> blocked on the human.
                    fp.write_text(
                        user_rec("u-1", 900, "review the PRs")
                        + system_rec(700)
                        + user_rec("u-2", 600, "task-notification: reviews done")
                    )
                    old = now - 600
                    dashboard.os.utime(fp, (old, old))
                    post_hook()
                    self.assertEqual("needs_input", state())
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_turn_clock_reanchors_after_quiet_gap(self) -> None:
        # Time blocked on a human (permission prompt, AskUserQuestion, sleep)
        # writes nothing to the transcript. A quiet gap longer than
        # TURN_GAP_RESET_SEC inside a turn must re-anchor the elapsed clock at
        # the post-gap event instead of billing the wait as generation time.
        base = 1_784_000_000.0

        def iso(offset: float) -> str:
            return str(dashboard.datetime.fromtimestamp(base + offset, dashboard.UTC).isoformat())

        records = [
            {
                "type": "user",
                "timestamp": iso(0),
                "message": {"role": "user", "content": "start the work"},
            },
            {
                "type": "assistant",
                "timestamp": iso(20),
                "message": {"role": "assistant", "content": []},
            },
            {
                "type": "assistant",
                "timestamp": iso(40),
                "message": {"role": "assistant", "content": []},
            },
            # 45-minute wait on the human, then generation resumes.
            {
                "type": "assistant",
                "timestamp": iso(40 + 2700),
                "message": {"role": "assistant", "content": []},
            },
            {
                "type": "assistant",
                "timestamp": iso(70 + 2700),
                "message": {"role": "assistant", "content": []},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            scan = dashboard.scan_turns(str(path), "claude")

        assert scan is not None
        # Clock re-anchored at the post-gap record, not the original prompt.
        self.assertEqual(base + 40 + 2700, scan["turn_start"])
        # The pre-gap active segment is banked as a finished duration.
        self.assertIn(40.0, scan["durations"])

    def test_local_command_output_is_not_a_turn_start(self) -> None:
        rec = {
            "type": "user",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": "<local-command-stdout>ok</local-command-stdout>",
            },
        }
        self.assertIsNone(dashboard._turn_signal(rec, "claude"))
        caveat = {
            "type": "user",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": "<local-command-caveat>x</local-command-caveat>",
            },
        }
        self.assertIsNone(dashboard._turn_signal(caveat, "claude"))

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

    def test_long_turn_warning_uses_styled_tooltip_not_native_title(self) -> None:
        # The (!) icon must use the app's styled tooltip (fast, themed), not
        # the native title attribute (multi-second hover delay).
        self.assertNotIn('class="lwarn" title=', dashboard.PAGE)
        self.assertIn('<span class="ltip">', dashboard.PAGE)
        self.assertIn('class="lwarn" tabindex="0"', dashboard.PAGE)
        self.assertIn(".lwarn:hover .ltip", dashboard.PAGE)
        self.assertIn("transition-delay:.2s", dashboard.PAGE)

    def test_page_restores_sparkline_hover_and_focus_after_render(self) -> None:
        # render() replaces #app's innerHTML every poll; the hover crosshair
        # and keyboard focus on the rate sparkline must be restored after.
        self.assertIn("sparkPointer", dashboard.PAGE)
        self.assertIn("restoreSparkState", dashboard.PAGE)
        self.assertIn("restoreSparkState(sparkFocused, savedPointer)", dashboard.PAGE)
        self.assertIn("preventScroll", dashboard.PAGE)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_sparkline_hover_lifecycle_across_renders_and_window_exit(self) -> None:
        # Behavioral coverage for the interaction layer: hover shows on
        # pointermove, survives a full render() DOM swap, is CLEARED when the
        # pointer leaves the window (no in-document pointermove fires), stays
        # cleared on later renders, and keyboard focus is restored.
        checks = """
const out = {};
const wrap = {
  id: "spark-main",
  dataset: {now: "1000"},
  style: {},
  closest(sel){ return sel === "#spark-main" ? this : null; },
  getBoundingClientRect(){
    return {left: 0, top: 0, right: 100, bottom: 46, width: 100, height: 46};
  },
  focus(){ document.activeElement = this; __fire("focusin", {target: this}); }
};
const tip = {style: {}, appendChild(){}};
const xline = {style: {}, parentElement: wrap};
__els["spark-main"] = wrap; __els["spark-tip"] = tip; __els["spark-x"] = xline;
__els["app"] = {innerHTML: ""};
pushPoint(rateHistory, 995, 100);
pushPoint(rateHistory, 1000, 200);
const d = {generated: 1000, window_hours: 24, show_all: false, harnesses: [],
           summary: {needs_input: 0, working: 0, rate_per_min: 200,
                     total_tasks: 0, open_tasks: 0, progress_pct: 0,
                     total_done: 0},
           sessions: []};
__fire("pointermove", {target: wrap, clientX: 50, clientY: 20});
out.hoverShown = tip.style.opacity == 1;
render(d);
out.restoredAfterRender = tip.style.opacity == 1;
__fire("mouseout", {relatedTarget: null});   // pointer left the window
out.clearedOnExit = tip.style.opacity == 0 && sparkPointer === null;
render(d);
out.staysHiddenAfterRender = tip.style.opacity == 0;
wrap.focus();
render(d);
out.focusRestored = document.activeElement === wrap && tip.style.opacity == 1;
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            {
                "hoverShown": True,
                "restoredAfterRender": True,
                "clearedOnExit": True,
                "staysHiddenAfterRender": True,
                "focusRestored": True,
            },
            out,
        )

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

    def test_read_tail_keeps_first_record_when_window_starts_on_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_bytes(b"aaaa\nbbbb\ncccc\n")  # 15 bytes

            # Window of 10 starts right after the newline at offset 4:
            # "bbbb" is a complete record and must be kept.
            with mock.patch.object(dashboard, "TAIL_BYTES", 10):
                aligned = dashboard.read_tail(str(path))
            # Window of 9 starts mid-"bbbb": the partial line must drop.
            with mock.patch.object(dashboard, "TAIL_BYTES", 9):
                misaligned = dashboard.read_tail(str(path))

        self.assertEqual(["bbbb", "cccc", ""], aligned)
        self.assertEqual(["cccc", ""], misaligned)

    def test_opencode_show_all_returns_every_session(self) -> None:
        now = dashboard.time.time()
        stale = int((now - 48 * 3600) * 1000)  # outside the 24h window
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "opencode.db"
            con = sqlite3.connect(db)
            con.execute(
                "CREATE TABLE session (id TEXT, parent_id TEXT, directory TEXT,"
                " title TEXT, time_updated INTEGER, time_archived INTEGER)"
            )
            con.executemany(
                "INSERT INTO session VALUES (?, NULL, '/w', ?, ?, NULL)",
                [(f"ses_{i:04d}", f"Session {i}", stale - i) for i in range(250)],
            )
            con.commit()
            con.close()

            with mock.patch.object(dashboard, "OPENCODE_DATA", str(tmp)):
                everything = dashboard.collect_opencode(now, 24, True)
                windowed = dashboard.collect_opencode(now, 24, False)

        self.assertEqual(250, len(everything))  # previously capped at 200
        self.assertEqual(0, len(windowed))

    def test_antigravity_activity_sees_uncheckpointed_wal_frames(self) -> None:
        now = dashboard.time.time()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "live.db"
            writer = sqlite3.connect(db)
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute(
                "CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER,"
                " status INTEGER, metadata BLOB)"
            )
            writer.commit()

            def step_metadata(epoch: float, output_tokens: int) -> bytes:
                def varint(value: int) -> bytes:
                    encoded = bytearray()
                    while value > 0x7F:
                        encoded.append((value & 0x7F) | 0x80)
                        value >>= 7
                    encoded.append(value)
                    return bytes(encoded)

                timestamp = varint(1 << 3) + varint(int(epoch))
                metadata = varint((1 << 3) | 2) + varint(len(timestamp)) + timestamp
                usage = varint(3 << 3) + varint(output_tokens)
                metadata += varint((9 << 3) | 2) + varint(len(usage)) + usage
                return metadata

            writer.execute(
                "INSERT INTO steps VALUES (1, 15, 3, ?)",
                (step_metadata(now - 30, 500),),
            )
            writer.commit()  # committed to the WAL; not yet checkpointed
            try:
                activity = dashboard.antigravity_step_activity(str(db), now)
            finally:
                writer.close()

        # An immutable=1-only reader misses these frames (rate stays 0).
        self.assertEqual(50, activity["rate_per_min"])

    def test_codex_meta_tolerates_malformed_payload_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            non_dict = Path(tmp) / "rollout-a.jsonl"
            non_dict.write_text('{"payload":42}\n')
            bad_fields = Path(tmp) / "rollout-b.jsonl"
            bad_fields.write_text(
                json.dumps(
                    {
                        "payload": {
                            "id": "s1",
                            "agent_nickname": 7,
                            "agent_path": 42,
                            "source": "not-a-dict",
                        }
                    }
                )
                + "\n"
            )

            meta_a = dashboard.codex_meta(str(non_dict))
            meta_b = dashboard.codex_meta(str(bad_fields))

        self.assertIsNone(meta_a["session_id"])
        self.assertFalse(meta_a["subagent"])
        self.assertEqual("s1", meta_b["session_id"])
        self.assertIsNone(meta_b["agent_label"])
        self.assertIsNone(meta_b["parent_session_id"])

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
        self.assertEqual("myproj", s["project"])
        self.assertEqual("fix the login bug", s["last_prompt"])
        self.assertEqual(["researcher"], s["subagents"])

    def test_cursor_sessions_discovered_with_title(self) -> None:
        now = dashboard.time.time()
        with tempfile.TemporaryDirectory() as tmp:
            chat = Path(tmp) / "ws1" / "33334444-bbbb"
            chat.mkdir(parents=True)
            con = sqlite3.connect(chat / "store.db")
            con.execute("CREATE TABLE meta (value TEXT)")
            hex_json = json.dumps({"name": "My Refactor Chat"}).encode().hex()
            con.execute("INSERT INTO meta VALUES (?)", (hex_json,))
            con.commit()
            con.close()

            with mock.patch.object(dashboard, "CURSOR_CHATS", str(tmp)):
                sessions = dashboard.collect_cursor(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual("working", sessions[0]["state"])
        self.assertEqual("My Refactor Chat", sessions[0]["title"])

    def test_goose_sessions_from_shared_db(self) -> None:
        now = dashboard.time.time()
        stamp = dashboard.datetime.fromtimestamp(now - 10, dashboard.UTC).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "sessions.db"
            con = sqlite3.connect(db)
            con.execute(
                "CREATE TABLE sessions (id TEXT, description TEXT,"
                " working_dir TEXT, updated_at TEXT, session_type TEXT,"
                " parent_session_id TEXT, archived_at TEXT)"
            )
            con.executemany(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,?)",
                [
                    ("g1", "Fix flaky tests", "/w/gooseproj", stamp, None, None, None),
                    ("g2", "helper", "/w", stamp, "subagent", "g1", None),
                    ("g3", "infra", "/w", stamp, "terminal", None, None),
                    ("g4", "old", "/w", stamp, None, None, stamp),  # archived
                ],
            )
            con.execute(
                "CREATE TABLE messages (session_id TEXT, role TEXT,"
                " created_timestamp INTEGER, content_json TEXT)"
            )
            con.execute(
                "INSERT INTO messages VALUES ('g1', 'user', ?, ?)",
                (int(now - 20), json.dumps([{"type": "text", "text": "add retries"}])),
            )
            con.execute(
                "CREATE TABLE usage_ledger (session_id TEXT,"
                " created_timestamp INTEGER, output_tokens INTEGER)"
            )
            con.execute("INSERT INTO usage_ledger VALUES ('g1', ?, 1000)", (int(now - 60),))
            con.commit()
            con.close()

            with mock.patch.object(dashboard, "GOOSE_DB", str(db)):
                sessions = dashboard.collect_goose(now, 24, False)

        self.assertEqual(1, len(sessions))  # subagent/infra/archived filtered
        s = sessions[0]
        self.assertEqual("working", s["state"])
        self.assertEqual("gooseproj", s["project"])
        self.assertEqual("Fix flaky tests", s["title"])
        self.assertEqual("add retries", s["last_prompt"])
        self.assertEqual(["helper"], s["subagents"])
        self.assertEqual(100, s["rate_per_min"])  # 1000 tokens / 10 min window

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
        self.assertEqual("droidproj", s["project"])
        self.assertEqual("Ship feature", s["title"])
        self.assertEqual("ship it", s["last_prompt"])


if __name__ == "__main__":
    unittest.main()
