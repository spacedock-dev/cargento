from __future__ import annotations

import contextlib
import email.message
import errno
import glob
import http.client
import http.server
import importlib.util
import io
import json
import ntpath
import os
import random
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("cargento_server", SERVER_PATH)
assert SPEC is not None
assert SPEC.loader is not None
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)

HOOK_PATH = SERVER_PATH.parent / "notify_hook.py"
HOOK_SPEC = importlib.util.spec_from_file_location("cargento_notify_hook", HOOK_PATH)
assert HOOK_SPEC is not None
assert HOOK_SPEC.loader is not None
dashboard_hook = importlib.util.module_from_spec(HOOK_SPEC)
HOOK_SPEC.loader.exec_module(dashboard_hook)


class CargentoServerTest(unittest.TestCase):
    def setUp(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()
            dashboard._last_state.clear()
            dashboard._hook_generation.clear()
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

    def test_cross_site_request_boundary(self) -> None:
        # Chrome labels *any* navigation whose initiator was another origin
        # "cross-site" — including a user clicking a link to the dashboard.
        # Rejecting those returned 403 for an ordinary way to open the page
        # (found by loading it in a real browser). Serving a top-level
        # document navigation is safe: the initiator cannot read a
        # cross-origin document. Everything that *can* read stays blocked.
        navigation = {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        cases = [
            # (method, path, headers, expected status, why)
            ("GET", "/", {"Sec-Fetch-Site": "cross-site", **navigation}, 200, "link to page"),
            (
                "GET",
                "/api/data",
                {"Sec-Fetch-Site": "cross-site", **navigation},
                200,
                "link to api",
            ),
            ("GET", "/", {"Sec-Fetch-Site": "none", **navigation}, 200, "typed/bookmarked"),
            ("GET", "/api/data", {"Sec-Fetch-Site": "same-origin"}, 200, "the page's own poll"),
            # Readable by the initiator — must stay blocked.
            (
                "GET",
                "/api/data",
                {
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                },
                403,
                "cross-site fetch",
            ),
            (
                "GET",
                "/",
                {
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "iframe",
                },
                403,
                "framed by another site",
            ),
            (
                "GET",
                "/api/data",
                {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example", **navigation},
                403,
                "cross-origin Origin header",
            ),
            # A cross-site form submission is also a "navigation", so POST
            # must never take the relaxed path.
            (
                "POST",
                "/api/notify",
                {"Sec-Fetch-Site": "cross-site", **navigation},
                403,
                "cross-site form POST",
            ),
            ("GET", "/", {"Host": "evil.example"}, 403, "DNS rebinding"),
        ]
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            for method, path, headers, expected, why in cases:
                with self.subTest(why=why):
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                    body = b'{"session_id":"x"}' if method == "POST" else None
                    conn.request(method, path, body=body, headers=headers)
                    response = conn.getresponse()
                    self.assertEqual(expected, response.status)
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
// Notification stub: records what the page would have raised, with a
// permission value tests can set. Defined here so every page test runs with a
// browser-notification-capable environment, as a real browser would.
let __notifications = [];
let __notifyPermission = "default";
function Notification(title, opts){ __notifications.push(Object.assign({title}, opts)); }
Object.defineProperty(Notification, "permission", {get: () => __notifyPermission});
// Settles on a later microtask, as the real API does: a synchronous stub let
// code that re-renders immediately (before permission resolves) pass.
Notification.requestPermission = cb => Promise.resolve().then(() => {
  __notifyPermission = "granted";
  if(cb) cb("granted");
  return "granted";
});
const __settle = () => new Promise(r => setImmediate(r));
"""

    def _run_page_js(self, checks: str) -> Any:
        match = re.search(r"<script>\n(.*?)</script>", dashboard.PAGE, re.DOTALL)
        assert match is not None
        script = match.group(1)
        with tempfile.TemporaryDirectory() as tmp:
            js = Path(tmp) / "page_test.js"
            # Checks run inside an async IIFE so they can await the async
            # stubs (permission settles on a microtask, as in a browser).
            js.write_text(
                self.PAGE_JS_STUBS + script + "\n;(async () => {\n" + checks + "\n})();\n"
            )
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
    def test_browser_notifications_fire_only_on_transitions_the_server_missed(self) -> None:
        # Exactly one layer may notify per transition (plan decision D-3).
        checks = """
__els.app = {innerHTML:""};
const blocked = {
  harness:"claude", session:"12345678", sid:"12345678", project:"proj",
  title:null, last_prompt:"", state:"needs_input", state_detail:"open question",
  active:true, last_activity:100, blocked_since:970, rate_per_min:0,
  total:0, done:0, open:0, progress_pct:0, eta_h:null, turn:null,
  subagents:[], tasks:[]
};
const idle = {...blocked, state:"idle", state_detail:"awaiting your message"};
const payload = (sessions, native) => ({
  generated:1000, window_hours:24, show_all:false, native_notify:native,
  harnesses:[], sessions,
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:1,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
});
const reset = perm => {
  __notifications = []; __notifyPermission = perm;
  notifyState = new Map(); notifyPrimed = false;
};
const out = {};

// The server already popped natively: the page must stay silent.
reset("granted");
render(payload([idle], "osascript"));
render(payload([blocked], "osascript"));
out.nativeOwnsIt = __notifications.length;

// No native backend (Linux/Windows today): the page notifies.
reset("granted");
render(payload([idle], ""));
render(payload([blocked], ""));
out.browserFired = __notifications.length;
out.body = __notifications[0] && __notifications[0].body;
out.tag = __notifications[0] && __notifications[0].tag;

// Still blocked on later refreshes: notify on the transition, not repeatedly.
render(payload([blocked], ""));
render(payload([blocked], ""));
out.noRepeat = __notifications.length;

// Cleared, then blocked again: that is a new transition.
render(payload([idle], ""));
render(payload([blocked], ""));
out.refired = __notifications.length;

// A session already blocked when the page opens must not pop on first paint.
reset("granted");
render(payload([blocked], ""));
out.primed = __notifications.length;

// Permission not granted: record state, raise nothing.
reset("default");
render(payload([idle], ""));
render(payload([blocked], ""));
out.ungranted = __notifications.length;

// Inactive sessions are outside the window and never notify.
reset("granted");
render(payload([{...idle, active:false}], ""));
render(payload([{...blocked, active:false}], ""));
out.inactive = __notifications.length;
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(0, out["nativeOwnsIt"], "would double-notify on macOS")
        self.assertEqual(1, out["browserFired"])
        self.assertEqual("[proj] open question", out["body"])
        self.assertEqual("claude:12345678", out["tag"])
        self.assertEqual(1, out["noRepeat"], "notified again while already blocked")
        self.assertEqual(2, out["refired"])
        self.assertEqual(0, out["primed"], "popped for a pre-existing block on first paint")
        self.assertEqual(0, out["ungranted"])
        self.assertEqual(0, out["inactive"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_notification_permission_control_reflects_state(self) -> None:
        checks = """
__els.app = {innerHTML:""};
const payload = native => ({
  generated:1000, window_hours:24, show_all:false, native_notify:native,
  harnesses:[], sessions:[],
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:0,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
});
const out = {};
__notifyPermission = "default"; out.prompt = notifyControl(payload(""));
__notifyPermission = "denied";  out.denied = notifyControl(payload(""));
__notifyPermission = "granted"; out.granted = notifyControl(payload(""));
__notifyPermission = "default"; out.native  = notifyControl(payload("osascript"));

// Granting re-renders so the button disappears without a reload.
__notifyPermission = "default";
render(payload(""));
out.buttonBefore = __els.app.innerHTML.includes("Enable notifications");
requestNotifyPermission();
out.buttonWhilePending = __els.app.innerHTML.includes("Enable notifications");
await __settle(); await __settle();
out.buttonAfter = __els.app.innerHTML.includes("Enable notifications");
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertIn("Enable notifications", out["prompt"])
        self.assertIn("notifications blocked", out["denied"])
        self.assertEqual("", out["granted"], "no control once permission is granted")
        self.assertEqual("", out["native"], "server owns popups; no control needed")
        self.assertTrue(out["buttonBefore"])
        self.assertTrue(out["buttonWhilePending"], "must not clear before permission settles")
        self.assertFalse(out["buttonAfter"], "control should clear after granting")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_page_works_without_the_notification_api(self) -> None:
        # Older or locked-down browsers expose no Notification constructor.
        checks = """
__els.app = {innerHTML:""};
Notification = undefined;
const d = {
  generated:1000, window_hours:24, show_all:false, native_notify:"",
  harnesses:[], sessions:[],
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:0,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
};
render(d);
requestNotifyPermission();
console.log(JSON.stringify({
  permission: notifyPermission(), control: notifyControl(d), rendered: !!__els.app.innerHTML
}));
"""
        out = self._run_page_js(checks)
        self.assertEqual("unsupported", out["permission"])
        self.assertEqual("", out["control"])
        self.assertTrue(out["rendered"])

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


class ReverseLinesTest(unittest.TestCase):
    """Replaces the reverse mmap scans. A mapped region whose file is truncated
    underneath it raises SIGBUS on POSIX (uncatchable) and blocks the writer's
    truncate on Windows; these are transcripts a live agent may rotate."""

    def write(self, tmp: str, text: str) -> str:
        path = Path(tmp) / "t.jsonl"
        # write_bytes, not write_text: Windows text mode translates "\n" to
        # "\r\n", and these tests assert on exact byte boundaries. Harnesses
        # write LF transcripts, which is what this reproduces.
        path.write_bytes(text.encode())
        return str(path)

    def read_back(self, path: str, **kwargs: Any) -> list[str]:
        return [raw.decode() for raw in dashboard.reverse_lines(path, **kwargs)]

    def test_yields_lines_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a\nb\nc\n")
            self.assertEqual(["", "c", "b", "a"], self.read_back(path))

    def test_file_without_a_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a\nb\nc")
            self.assertEqual(["c", "b", "a"], self.read_back(path))

    def test_empty_and_missing_files_yield_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([], self.read_back(self.write(tmp, "")))
            self.assertEqual([], self.read_back(str(Path(tmp) / "absent.jsonl")))

    def test_lines_spanning_chunk_boundaries_are_reassembled(self) -> None:
        # The whole risk of chunked reverse reading: a record split across two
        # reads must come back intact. Forced with a chunk far smaller than the
        # lines, at several sizes so no single alignment can hide a bug.
        lines = [f"{i:04d}-" + "x" * (i % 37) for i in range(200)]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "\n".join(lines) + "\n")
            for chunk in (1, 2, 3, 7, 64, 1000):
                with (
                    self.subTest(chunk=chunk),
                    mock.patch.object(dashboard, "REVERSE_CHUNK_BYTES", chunk),
                ):
                    got = [line for line in self.read_back(path) if line]
                    self.assertEqual(list(reversed(lines)), got)

    def test_contains_filter_never_hides_a_matching_line(self) -> None:
        # The filter tests whole chunks, so a match split across a chunk
        # boundary is exactly what could go missing. Sweep every alignment.
        with tempfile.TemporaryDirectory() as tmp:
            for offset in range(40):
                text = "x" * offset + "\nfiller\nNEEDLE-here\nfiller\n"
                path = self.write(tmp, text)
                for chunk in (1, 2, 3, 5, 8, 13):
                    with (
                        self.subTest(offset=offset, chunk=chunk),
                        mock.patch.object(dashboard, "REVERSE_CHUNK_BYTES", chunk),
                    ):
                        got = [
                            raw.decode()
                            for raw in dashboard.reverse_lines(path, contains=b"NEEDLE")
                            if b"NEEDLE" in raw
                        ]
                        self.assertEqual(["NEEDLE-here"], got)

    def test_contains_filter_matches_the_unfiltered_walk(self) -> None:
        lines = [f"rec{i}" + ("-TARGET" if i % 97 == 0 else "") for i in range(500)]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "\n".join(lines) + "\n")
            for chunk in (4, 16, 256):
                with (
                    self.subTest(chunk=chunk),
                    mock.patch.object(dashboard, "REVERSE_CHUNK_BYTES", chunk),
                ):
                    unfiltered = [r for r in dashboard.reverse_lines(path) if b"TARGET" in r]
                    filtered = [
                        r
                        for r in dashboard.reverse_lines(path, contains=b"TARGET")
                        if b"TARGET" in r
                    ]
                    self.assertEqual(unfiltered, filtered)
                    self.assertEqual(6, len(filtered))

    def test_matches_a_trivial_reference_across_the_input_space(self) -> None:
        # The strongest guarantee available: compare against slice/split/reverse
        # over a generated corpus, at every chunk size, end_pos and max_bytes.
        # This is what caught the list-accumulation rewrite being correct.
        def reference(data: bytes, stop: int, max_bytes: int | None) -> list[bytes]:
            floor = 0 if max_bytes is None else max(0, stop - max_bytes)
            window = data[floor:stop] if floor else data[:stop]
            out = list(reversed(window.split(b"\n")))
            if floor:
                return out[:-1]  # oldest is a fragment when the walk is bounded
            return [] if stop == 0 else out

        rng = random.Random(11)
        alphabet = [b"a", b"bb", b"", b"NEEDLE", b"xNEEDLEy", b"c" * 40]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f"
            for _ in range(60):
                data = b"\n".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
                if rng.random() < 0.5:
                    data += b"\n"
                path.write_bytes(data)
                size = len(data)
                for stop in {size, max(0, size // 2), max(0, size - 1), 0}:
                    for max_bytes in (None, 3, 10):
                        for chunk in (1, 2, 5, 4096):
                            with mock.patch.object(dashboard, "REVERSE_CHUNK_BYTES", chunk):
                                got = list(
                                    dashboard.reverse_lines(str(path), stop, max_bytes=max_bytes)
                                )
                            if got != reference(data, stop, max_bytes):
                                self.fail(
                                    f"data={data!r} stop={stop} max_bytes={max_bytes} "
                                    f"chunk={chunk}: {got} != {reference(data, stop, max_bytes)}"
                                )

    def test_the_contains_filter_never_hides_a_line(self) -> None:
        # The filter tests each chunk and the completed line rather than a
        # joined buffer, so a match spanning chunks is the risk.
        rng = random.Random(12)
        alphabet = [b"a", b"bb", b"", b"NEEDLE", b"xNEEDLEy", b"c" * 40]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f"
            for _ in range(60):
                data = b"\n".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))
                path.write_bytes(data + rng.choice([b"\n", b""]))
                for chunk in (1, 2, 3, 5, 17, 4096):
                    with mock.patch.object(dashboard, "REVERSE_CHUNK_BYTES", chunk):
                        plain = [r for r in dashboard.reverse_lines(str(path)) if b"NEEDLE" in r]
                        filtered = [
                            r
                            for r in dashboard.reverse_lines(str(path), contains=b"NEEDLE")
                            if b"NEEDLE" in r
                        ]
                    self.assertEqual(plain, filtered, f"chunk={chunk} data={data!r}")

    def test_crlf_transcripts_still_parse(self) -> None:
        # Harnesses write LF, but a transcript can pick up CRLF by being copied
        # through a Windows tool. Lines split on "\n" keep a trailing "\r";
        # that must not change what the readers extract.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "crlf.jsonl"
            path.write_bytes(
                b"\r\n".join(
                    [
                        json.dumps({"type": "ai-title", "aiTitle": "CRLF title"}).encode(),
                        json.dumps({"type": "user", "uuid": "u-crlf"}).encode(),
                    ]
                )
                + b"\r\n"
            )
            self.assertEqual("CRLF title", dashboard.claude_session_title(str(path)))
            self.assertEqual("u-crlf", dashboard.claude_last_user_event(str(path)))

    def test_end_pos_limits_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "aaa\nbbb\nccc\n")
            self.assertEqual(["", "bbb", "aaa"], self.read_back(path, end_pos=8))

    def test_max_bytes_drops_the_oldest_partial_line(self) -> None:
        # Stopping mid-file means the oldest line reached is probably a
        # fragment, so it is discarded rather than parsed as a record.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "aaaa\nbbbb\ncccc\n")
            self.assertEqual(["", "cccc"], self.read_back(path, max_bytes=6))

    def test_a_file_truncated_mid_scan_stops_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "\n".join(f"line{i}" for i in range(500)) + "\n")
            with mock.patch.object(dashboard, "REVERSE_CHUNK_BYTES", 16):
                walker = dashboard.reverse_lines(path)
                next(walker)
                Path(path).write_bytes(b"")  # writer rotates the transcript
                remaining = list(walker)  # must not raise
        self.assertIsInstance(remaining, list)

    def test_a_line_ending_exactly_at_end_pos_is_yielded(self) -> None:
        # Where the reverse and forward halves of scan_turns meet. The forward
        # pass resumes at the same offset, and a forward read starting on a
        # newline never sees the record that newline terminates — so the
        # reverse pass has to yield it. The previous mmap reader searched
        # rfind("\n", 0, end_pos), which excluded that byte and dropped the
        # record from both halves.
        #
        # Note this does not make the split lossless in general: a record
        # straddling the split offset is still missed by both halves. That is a
        # pre-existing limit of the bounded scan, unchanged by this PR.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "first\nsecond\nthird\n")
            split = len("first\nsecond")  # the newline terminating "second"
            self.assertEqual(b"\n", Path(path).read_bytes()[split : split + 1])
            got = [raw.decode() for raw in dashboard.reverse_lines(path, split) if raw]
        self.assertEqual(["second", "first"], got)

    def test_title_and_user_event_still_scan_the_whole_file(self) -> None:
        # Both readers look past the bounded activity tail, which is why they
        # walk backward at all rather than reusing read_tail().
        filler = [json.dumps({"type": "assistant", "message": {}}) for _ in range(400)]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(
                tmp,
                "\n".join(
                    [
                        json.dumps({"type": "ai-title", "aiTitle": "Old title"}),
                        json.dumps({"type": "user", "uuid": "u-old"}),
                        *filler,
                        json.dumps({"type": "ai-title", "aiTitle": "Newest title"}),
                        json.dumps({"type": "user", "uuid": "u-new"}),
                        *filler,
                    ]
                )
                + "\n",
            )
            with mock.patch.object(dashboard, "REVERSE_CHUNK_BYTES", 128):
                self.assertEqual("Newest title", dashboard.claude_session_title(path))
                self.assertEqual("u-new", dashboard.claude_last_user_event(path))


class StoreRootsTest(unittest.TestCase):
    """resolve_store_roots is pure, so every platform's layout is checked here
    regardless of which runner is executing."""

    POSIX_HOME = "/home/u"
    WIN_HOME = r"C:\Users\j"
    WIN_ENV: ClassVar[dict[str, str]] = {
        "LOCALAPPDATA": r"C:\Users\j\AppData\Local",
        "APPDATA": r"C:\Users\j\AppData\Roaming",
    }

    def resolve(
        self, platform_name: str, environ: dict[str, str], home: str
    ) -> dict[str, list[str]]:
        roots: dict[str, list[str]] = dashboard.resolve_store_roots(
            platform_name=platform_name, environ=environ, home=home
        )
        return roots

    def test_posix_defaults_are_unchanged(self) -> None:
        # These are the paths that work today; a regression here silently
        # blinds the dashboard on the platform it was built for.
        roots = self.resolve("darwin", {}, self.POSIX_HOME)
        self.assertEqual(["/home/u/.claude/projects"], roots["claude.projects"])
        self.assertEqual(["/home/u/.claude/tasks"], roots["claude.tasks"])
        self.assertEqual(["/home/u/.codex/sessions"], roots["codex.sessions"])
        self.assertEqual(["/home/u/.gemini/tmp"], roots["gemini.tmp"])
        self.assertEqual(["/home/u/.copilot"], roots["copilot.root"])
        self.assertEqual(["/home/u/.cursor/chats"], roots["cursor.chats"])
        self.assertEqual(["/home/u/.factory/projects"], roots["droid.projects"])
        self.assertEqual(["/home/u/.local/share/opencode"], roots["opencode.data"])
        self.assertEqual(["/home/u/.local/share/goose/sessions/sessions.db"], roots["goose.db"])

    def test_xdg_data_home_is_honored(self) -> None:
        roots = self.resolve("linux", {"XDG_DATA_HOME": "/xdg"}, self.POSIX_HOME)
        self.assertEqual(["/xdg/opencode"], roots["opencode.data"])
        self.assertEqual(["/xdg/goose/sessions/sessions.db"], roots["goose.db"])

    def test_windows_uses_native_separators_and_app_data(self) -> None:
        roots = self.resolve("win32", dict(self.WIN_ENV), self.WIN_HOME)
        self.assertEqual([r"C:\Users\j\.claude\projects"], roots["claude.projects"])
        # App-data locations are searched in addition to the XDG-style one.
        self.assertIn(r"C:\Users\j\AppData\Local\opencode\data", roots["opencode.data"])
        self.assertIn(
            r"C:\Users\j\AppData\Roaming\Block\goose\data\sessions\sessions.db",
            roots["goose.db"],
        )

    def test_candidates_are_deduplicated(self) -> None:
        # On Windows the XDG-style default and the explicit ~/.local/share
        # entry are the same path; it must not be scanned twice.
        roots = self.resolve("win32", dict(self.WIN_ENV), self.WIN_HOME)
        for key, candidates in roots.items():
            with self.subTest(key=key):
                folded = [ntpath.normcase(c) for c in candidates]
                self.assertEqual(len(folded), len(set(folded)))

    def test_documented_env_overrides_are_authoritative(self) -> None:
        roots = self.resolve(
            "linux",
            {
                "CLAUDE_CONFIG_DIR": "/opt/cc",
                "CODEX_HOME": "/opt/cx",
                "COPILOT_HOME": "/opt/cp",
            },
            self.POSIX_HOME,
        )
        # Only the override is searched — a relocated store must never fall
        # back to a stale default.
        self.assertEqual(["/opt/cc/projects"], roots["claude.projects"])
        self.assertEqual(["/opt/cc/tasks"], roots["claude.tasks"])
        self.assertEqual(["/opt/cx/sessions"], roots["codex.sessions"])
        self.assertEqual(["/opt/cp"], roots["copilot.root"])

    def test_gemini_cli_home_names_a_parent_directory(self) -> None:
        # Documented behavior: the CLI creates ".gemini" *inside* the value.
        roots = self.resolve("linux", {"GEMINI_CLI_HOME": "/opt/g"}, self.POSIX_HOME)
        self.assertEqual(["/opt/g/.gemini/tmp"], roots["gemini.tmp"])
        self.assertEqual(["/opt/g/.gemini/antigravity-cli"], roots["antigravity.root"])

    def test_blank_env_values_fall_back_to_defaults(self) -> None:
        roots = self.resolve("linux", {"CLAUDE_CONFIG_DIR": "   "}, self.POSIX_HOME)
        self.assertEqual(["/home/u/.claude/projects"], roots["claude.projects"])

    def test_a_patched_constant_suppresses_the_other_candidates(self) -> None:
        # The override seam: pointing a constant at a fixture must scan that
        # and nothing else, or a test could pick up a real store on the box.
        with mock.patch.object(dashboard, "OPENCODE_DATA", "/fixture"):
            self.assertEqual(
                ["/fixture"], dashboard.store_roots("opencode.data", dashboard.OPENCODE_DATA)
            )
        # Unpatched, the full candidate list is used.
        self.assertEqual(
            dashboard.STORE_ROOTS["opencode.data"],
            dashboard.store_roots("opencode.data", dashboard.OPENCODE_DATA),
        )

    def test_sessions_from_two_candidate_roots_are_merged(self) -> None:
        now = 1_700_000_000.0
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a", Path(tmp) / "b"
            for root, sid in ((first, "11111111"), (second, "22222222")):
                (root / "proj").mkdir(parents=True)
                transcript = root / "proj" / f"{sid}-0000-0000-0000-000000000000.jsonl"
                transcript.write_text(json.dumps({"type": "user", "uuid": "u"}) + "\n")
                os.utime(transcript, (now, now))
            with (
                mock.patch.dict(
                    dashboard.STORE_ROOTS,
                    {"claude.projects": [str(first), str(second)]},
                ),
                mock.patch.object(dashboard, "PROJECTS_DIR", str(first)),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
            ):
                sessions = dashboard.collect_claude(now, 24, False)

        self.assertEqual({"11111111", "22222222"}, {s["session"] for s in sessions})


class DiagnoseTest(unittest.TestCase):
    def test_report_names_every_candidate_and_what_was_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            (projects / "proj").mkdir(parents=True)
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "absent")),
            ):
                report = dashboard.diagnose(24)

        claude = report["stores"]["claude.projects"]["candidates"]
        self.assertEqual("directory", claude[0]["kind"])
        self.assertTrue(claude[0]["readable"])
        # A missing store is reported as missing, not omitted — the whole point
        # is distinguishing "looked and found nothing" from "never looked".
        self.assertEqual("missing", report["stores"]["claude.tasks"]["candidates"][0]["kind"])
        self.assertEqual(sys.platform, report["platform"])
        self.assertIn("available", report["sqlite"])

    @unittest.skipIf(os.name == "nt", "POSIX permission bits; Windows uses ACLs")
    def test_an_unreadable_store_is_distinguished_from_a_missing_one(self) -> None:
        # The distinction that matters on Windows, where Defender, EDR, and
        # OneDrive hydration all produce transient permission failures: a store
        # that exists but cannot be read must not look like an absent harness.
        with tempfile.TemporaryDirectory() as tmp:
            locked = Path(tmp) / "locked"
            locked.mkdir()
            locked.chmod(0o000)
            try:
                report = dashboard.candidate_report(str(locked))
            finally:
                locked.chmod(0o700)  # or TemporaryDirectory cannot clean up

        self.assertEqual("directory", report["kind"])
        self.assertFalse(report["readable"])
        self.assertIn("PermissionError", report["error"])
        self.assertNotEqual("missing", report["kind"])

    def test_rendering_is_ascii_only(self) -> None:
        # This output gets pasted into issues from consoles whose encoding we
        # do not control.
        text = dashboard.render_diagnosis(dashboard.diagnose(24))
        text.encode("ascii")  # must not raise
        self.assertIn("Stores searched", text)
        self.assertIn("Harnesses", text)

    def test_json_report_is_serializable(self) -> None:
        json.dumps(dashboard.diagnose(24))  # must not raise

    def test_env_overrides_are_surfaced(self) -> None:
        with mock.patch.dict(os.environ, {"CODEX_HOME": "/opt/cx"}):
            report = dashboard.diagnose(24)
        self.assertEqual("/opt/cx", report["env"]["CODEX_HOME"])


class HostAndSocketTest(unittest.TestCase):
    def test_host_header_forms_that_are_all_loopback(self) -> None:
        # rsplit(":", 1) mangled the bracketed IPv6 form into "[:" and never
        # folded case, so both were rejected as non-local.
        for value in (
            "127.0.0.1",
            "127.0.0.1:4553",
            "localhost",
            "LOCALHOST",
            "LocalHost:4553",
            "[::1]",
            "[::1]:4553",
            "::1",
        ):
            with self.subTest(host=value):
                self.assertIn(dashboard.normalize_host(value), dashboard.Handler.LOCAL_HOSTS)

    def test_host_header_forms_that_are_not_loopback(self) -> None:
        for value in (
            "",
            "evil.example",
            "evil.example:4553",
            "127.0.0.1.evil.example",
            "[",
            "[]",
            "192.168.1.5",
            # Only a port may follow a bracketed literal. Ignoring the rest
            # made "[::1]evil.example" reduce to "::1" and pass as loopback.
            "[::1]evil.example",
            "[::1]xyz:99",
            "[::1].",
            "[::1]:notaport",
            # Unbracketed authorities need the same port validation, or
            # "localhost:evil.example" reduces to "localhost".
            "localhost:evil.example",
            "127.0.0.1:evil.example",
            "localhost:",
        ):
            with self.subTest(host=value):
                self.assertNotIn(dashboard.normalize_host(value), dashboard.Handler.LOCAL_HOSTS)

    def test_reuse_address_is_off_only_on_windows(self) -> None:
        # POSIX: SO_REUSEADDR just bypasses TIME_WAIT, so restarts work.
        # Windows: it lets a second process bind an already-bound port.
        self.assertTrue(dashboard.reuse_address_allowed("posix"))
        self.assertFalse(dashboard.reuse_address_allowed("nt"))

    def test_bind_errors_explain_themselves(self) -> None:
        in_use = OSError(errno.EADDRINUSE, "Address already in use")
        self.assertIn("already in use", dashboard.bind_error_message(in_use, 4553))
        self.assertIn("4553", dashboard.bind_error_message(in_use, 4553))
        denied = OSError(errno.EACCES, "Permission denied")
        self.assertIn("not permitted", dashboard.bind_error_message(denied, 4553))
        other = OSError(errno.EINVAL, "Invalid argument")
        self.assertIn("cannot bind", dashboard.bind_error_message(other, 4553))

    def test_windows_error_codes_are_recognized(self) -> None:
        # winerror, not errno, is what Windows populates. 10013 is also what an
        # in-use port reports once SO_EXCLUSIVEADDRUSE is set.
        for winerror, expected in ((10048, "already in use"), (10013, "not permitted")):
            with self.subTest(winerror=winerror):
                exc = OSError()
                exc.winerror = winerror  # type: ignore[attr-defined]
                self.assertIn(expected, dashboard.bind_error_message(exc, 4553))

    def test_server_binds_and_serves(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            conn.request("GET", "/api/data")
            response = conn.getresponse()
            self.assertEqual(200, response.status)
            response.read()
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


class NotifyHookTest(unittest.TestCase):
    """The forwarder replaces a curl one-liner that only worked in POSIX shells."""

    HOOK = str(HOOK_PATH)

    def run_hook(self, payload: bytes, url: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.HOOK, *([url] if url else [])],
            input=payload.decode(),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_payload_reaches_a_running_server(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{httpd.server_port}/api/notify"
        try:
            with mock.patch.object(dashboard, "notify_mac"):
                result = self.run_hook(
                    json.dumps(
                        {
                            "session_id": "abcd1234-0000-0000-0000-000000000000",
                            "message": "Claude needs permission",
                            "notification_type": "permission_prompt",
                        }
                    ).encode(),
                    url,
                )
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertEqual(0, result.returncode, result.stderr)
        # The server recorded the hook, which is the whole point of the script.
        self.assertIn("abcd1234", dashboard._hook_notifs)

    def test_never_fails_the_agent_that_invoked_it(self) -> None:
        # A hook that exits non-zero disturbs the session it reports on, and
        # "no dashboard running" is an ordinary state.
        cases = {
            "no server listening": (b'{"session_id":"x"}', "http://127.0.0.1:9/api/notify"),
            "malformed json": (b"{not json", None),
            "empty stdin": (b"", None),
            "not an object": (b"[1,2,3]", None),
        }
        for why, (payload, url) in cases.items():
            with self.subTest(why=why):
                self.assertEqual(0, self.run_hook(payload, url).returncode)

    def test_refuses_to_forward_off_loopback(self) -> None:
        # The script is wired into lifecycle hooks and sees prompts and session
        # ids; an edited settings file must not turn it into an exfiltration
        # path. A prefix check (startswith "http://localhost") accepted several
        # of these — the host is parsed instead.
        for url in (
            "https://evil.example/collect",
            "http://10.0.0.5:4553/api/notify",
            "file:///etc/passwd",
            "http://localhost.evil.com/collect",
            "http://127.0.0.1.evil.com/collect",
            "http://localhost@evil.com/collect",
            "http://[::1]@evil.com/collect",
            "https://127.0.0.1/collect",  # https is not what the server speaks
            "",
        ):
            with self.subTest(url=url):
                self.assertFalse(dashboard_hook.is_loopback_url(url))
                self.assertFalse(dashboard_hook.forward(url, b"{}"))

    def test_accepts_every_loopback_spelling(self) -> None:
        for url in (
            "http://127.0.0.1:4553/api/notify",
            "http://localhost:9999/api/notify",
            "http://[::1]:4553/api/notify",
        ):
            with self.subTest(url=url):
                self.assertTrue(dashboard_hook.is_loopback_url(url))

    def test_an_http_proxy_cannot_carry_the_payload_off_the_machine(self) -> None:
        # urllib's default opener honours http_proxy/HTTP_PROXY, which is
        # routine in corporate environments. A POST to 127.0.0.1 was handed to
        # the proxy instead, carrying prompts and session ids off the machine
        # and defeating the loopback check entirely.
        proxied: list[bytes] = []

        class Proxy(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                proxied.append(self.rfile.read(length))
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch.dict(
                os.environ,
                {
                    "http_proxy": f"http://127.0.0.1:{httpd.server_port}",
                    "HTTP_PROXY": f"http://127.0.0.1:{httpd.server_port}",
                },
            ):
                # Port 9 (discard) is not listening, so anything the proxy
                # receives can only have come from proxy routing.
                delivered = dashboard_hook.forward(
                    "http://127.0.0.1:9/api/notify", b'{"secret":"prompt text"}'
                )
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertEqual([], proxied, "payload was routed through the proxy")
        self.assertFalse(delivered)

    def test_does_not_follow_a_redirect_off_the_machine(self) -> None:
        # urllib follows redirects by default, and 307/308 preserve method and
        # body — so a hostile listener on the loopback port could otherwise
        # bounce the payload off this machine, defeating the check above.
        received: list[str] = []

        class Redirector(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                received.append(self.path)
                self.send_response(307)
                self.send_header("Location", "https://evil.example/collect")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirector)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_port}/api/notify"
            delivered = dashboard_hook.forward(url, b'{"session_id":"x"}')
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertEqual(["/api/notify"], received, "first request should still be sent")
        self.assertFalse(delivered, "a refused redirect must not report success")


class ReviewFixTest(unittest.TestCase):
    """Regressions found by the adversarial review passes on PR #7."""

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

    def test_the_same_session_in_two_stores_yields_one_row(self) -> None:
        # Scanning every candidate root can find a session left behind by a
        # migration twice; the DB-backed collectors append per store.
        rows = [
            {**dashboard.base_session("opencode", "same", "p"), "last_activity": 10.0},
            {**dashboard.base_session("opencode", "same", "p"), "last_activity": 99.0},
            {**dashboard.base_session("goose", "same", "p"), "last_activity": 5.0},
        ]
        merged = dashboard.dedupe_sessions(rows)
        self.assertEqual(2, len(merged), "duplicate session id was not merged")
        opencode = next(r for r in merged if r["harness"] == "opencode")
        self.assertEqual(99.0, opencode["last_activity"], "kept the staler copy")

    def test_a_corrupt_database_is_reported_by_diagnose(self) -> None:
        # Collectors swallow SQLite failures so one broken store cannot take
        # the dashboard down — which made --diagnose call a corrupt database a
        # healthy store with no sessions.
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "sessions.db"
            broken.write_text("definitely not a database")
            with (
                mock.patch.dict(dashboard.STORE_ROOTS, {"goose.db": [str(broken)]}),
                mock.patch.object(dashboard, "GOOSE_DB", str(broken)),
            ):
                report = dashboard.diagnose(24)

        self.assertIn(str(broken), report["store_errors"])
        self.assertIn("not a database", report["store_errors"][str(broken)])
        self.assertIn("failed to open", dashboard.render_diagnosis(report))

    @unittest.skipIf(os.name == "nt", "POSIX permission bits; Windows uses ACLs")
    def test_an_unreadable_parent_reports_inaccessible_not_missing(self) -> None:
        # isdir()/isfile() swallow OSError and return False, so a candidate
        # under a locked parent looked simply absent.
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "locked"
            (parent / "inner").mkdir(parents=True)
            parent.chmod(0o000)
            try:
                report = dashboard.candidate_report(str(parent / "inner"))
            finally:
                parent.chmod(0o700)

        self.assertEqual("inaccessible", report["kind"])
        self.assertIn("PermissionError", report["error"])

    def test_candidate_report_survives_a_listable_but_unreadable_directory(self) -> None:
        # Platform-independent: the Windows failure mode is an ACL or a
        # Defender lock, which surfaces as listdir raising, not as a mode bit.
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(dashboard.os, "scandir", side_effect=PermissionError("locked")),
        ):
            report = dashboard.candidate_report(tmp)
        self.assertEqual("directory", report["kind"])
        self.assertFalse(report["readable"])
        self.assertIn("PermissionError", report["error"])

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
            self.assertEqual({}, dashboard.message_dict({"message": "str"}))
            self.assertEqual({}, dashboard.message_dict("not-a-record"))
            self.assertEqual({"a": 1}, dashboard.message_dict({"message": {"a": 1}}))

            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
            ):
                sessions = dashboard.collect_claude(now, 24, False)  # must not raise
                everything = dashboard.collect(24, True)

        self.assertEqual(1, len(sessions))
        claude = next(h for h in everything["harnesses"] if h["key"] == "claude")
        self.assertIsNone(claude["error"], "collector errored on a malformed record")

    def test_reverse_lines_stays_linear_on_one_long_record(self) -> None:
        # chunk + carry per chunk made this quadratic: a 64 MB single-line
        # transcript took 0.9s, and large tool results do produce such records.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "long.jsonl"
            timings = []
            for megabytes in (4, 16):
                path.write_bytes(b"x" * (megabytes * 1024 * 1024))
                start = time.perf_counter()
                list(dashboard.reverse_lines(str(path)))
                timings.append(time.perf_counter() - start)
        # Quadratic would be ~16x for 4x the bytes. Linear is ~4x; allow 8x for
        # a loaded CI runner while still failing a quadratic regression.
        self.assertLess(timings[1], max(timings[0], 0.005) * 8, f"non-linear: {timings}")

    def test_env_paths_are_not_stripped(self) -> None:
        # Trailing whitespace is legal in a POSIX path, and XDG_DATA_HOME was
        # honoured before this resolver existed — stripping it would move an
        # existing store out from under a macOS or Linux user.
        roots = dashboard.resolve_store_roots(
            platform_name="darwin", environ={"XDG_DATA_HOME": "/data/Agent Data "}, home="/h"
        )
        self.assertEqual("/data/Agent Data /opencode", roots["opencode.data"][0])
        # Whitespace-only still counts as unset.
        blank = dashboard.resolve_store_roots(
            platform_name="darwin", environ={"XDG_DATA_HOME": "   "}, home="/h"
        )
        self.assertEqual("/h/.local/share/opencode", blank["opencode.data"][0])

    def test_a_page_on_another_local_port_cannot_post(self) -> None:
        # Every port on this machine is the same *site*, so Sec-Fetch-Site says
        # "same-site" for a page served from another local port. A hostname-only
        # Origin check trusted it, and text/plain is CORS-safelisted so no
        # preflight would have stopped the request.
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_port
        cases = [
            (f"http://127.0.0.1:{port}", 200, "the dashboard's own page"),
            (f"http://localhost:{port}", 200, "same port, other spelling"),
            ("http://localhost:9999", 403, "another local dev server"),
            ("http://127.0.0.1:9999", 403, "another local port"),
            ("http://localhost", 403, "port 80"),
            ("https://evil.example", 403, "remote origin"),
        ]
        try:
            for origin, expected, why in cases:
                with self.subTest(why=why):
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    conn.request(
                        "POST",
                        "/api/notify",
                        body=b'{"session_id":"aaaaaaaa"}',
                        headers={"Origin": origin, "Content-Type": "text/plain"},
                    )
                    response = conn.getresponse()
                    self.assertEqual(expected, response.status)
                    response.read()
                    conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_exclusive_port_option_is_requested_before_bind(self) -> None:
        # Clearing SO_REUSEADDR stops Cargento hijacking someone else's port;
        # SO_EXCLUSIVEADDRUSE is what stops anyone hijacking Cargento's. Only
        # meaningful if it is applied before bind().
        order: list[str] = []
        real_setsockopt = socket.socket.setsockopt
        real_bind = socket.socket.bind

        def traced_setsockopt(self: Any, level: int, option: int, value: Any) -> Any:
            order.append(f"setsockopt:{option}")
            return real_setsockopt(self, level, option, value)

        def traced_bind(self: Any, address: Any) -> Any:
            order.append("bind")
            return real_bind(self, address)

        with (
            mock.patch.object(socket.socket, "setsockopt", traced_setsockopt),
            mock.patch.object(socket.socket, "bind", traced_bind),
            mock.patch.object(socket, "SO_EXCLUSIVEADDRUSE", 0xFFFB, create=True),
            # The fake option number is rejected by the OS; that path warns,
            # which is correct behaviour but noise in the test output.
            mock.patch.object(dashboard, "diag"),
        ):
            httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
            httpd.server_close()

        self.assertIn("setsockopt:65531", order)
        self.assertEqual("bind", order[-1], "options must be set before bind()")
        self.assertLess(order.index("setsockopt:65531"), order.index("bind"))


class VerificationFixTest(unittest.TestCase):
    """Regressions found by the adversarial pass that tried to refute the fixes."""

    NOW = 1_700_000_000.0
    FUTURE = NOW + 86_400

    def test_newest_plausible_ignores_skew(self) -> None:
        self.assertEqual(self.NOW, dashboard.newest_plausible(self.NOW, (self.FUTURE, self.NOW)))
        self.assertEqual(0.0, dashboard.newest_plausible(self.NOW, (self.FUTURE,)))
        self.assertEqual(0.0, dashboard.newest_plausible(self.NOW, ()))

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

    def test_a_skewed_duplicate_does_not_win_deduplication(self) -> None:
        # Ranking by raw last_activity let a clock-skewed migrated copy beat the
        # live one — the very problem rejecting future timestamps is for.
        good = {**dashboard.base_session("opencode", "same", "p"), "state": "working"}
        good["last_activity"] = dashboard.newest_plausible(self.NOW, (self.NOW,))
        skewed = {**dashboard.base_session("opencode", "same", "p"), "state": "idle"}
        skewed["last_activity"] = dashboard.newest_plausible(self.NOW, (self.FUTURE,))
        for order in ([good, skewed], [skewed, good]):
            with self.subTest(order=[s["state"] for s in order]):
                self.assertEqual("working", dashboard.dedupe_sessions(order)[0]["state"])

    def test_origin_with_an_implicit_default_port(self) -> None:
        # Browsers omit the port when it is the scheme default, so
        # "http://localhost" is legitimate for a server on port 80.
        handler = dashboard.Handler.__new__(dashboard.Handler)
        handler.headers = email.message.Message()
        handler.headers["Host"] = "localhost"
        handler.headers["Origin"] = "http://localhost"
        handler.server = mock.Mock(server_port=80)
        self.assertTrue(handler._local_ok())
        handler.server = mock.Mock(server_port=4553)
        self.assertFalse(handler._local_ok())

    @unittest.skipIf(os.name == "nt", "POSIX symlinks and FIFOs")
    def test_special_files_are_not_reported_as_readable_stores(self) -> None:
        # stat() follows symlinks, so a dangling one looked absent, and every
        # non-directory looked like a readable regular file.
        with tempfile.TemporaryDirectory() as tmp:
            dangling = Path(tmp) / "dangling"
            dangling.symlink_to(Path(tmp) / "nowhere")
            fifo = Path(tmp) / "pipe"
            os.mkfifo(fifo)
            self.assertEqual("broken symlink", dashboard.candidate_report(str(dangling))["kind"])
            self.assertEqual("special file", dashboard.candidate_report(str(fifo))["kind"])

    def test_query_failures_are_recorded_not_just_connection_failures(self) -> None:
        # A file that opens as a database but fails every query is the common
        # corruption shape; only the connect path was being recorded.
        with tempfile.TemporaryDirectory() as tmp:
            antigravity = Path(tmp) / "conv.db"
            antigravity.write_bytes(b"not a database")
            cursor = Path(tmp) / "store.db"
            cursor.write_bytes(b"also not a database")

            with dashboard._cache_lock:
                dashboard._store_errors.clear()
            dashboard.antigravity_step_activity(str(antigravity), self.NOW)
            self.assertIn(str(antigravity), dashboard._store_errors)

            with dashboard._cache_lock:
                dashboard._store_errors.clear()
            self.assertIsNone(dashboard._cursor_title(str(cursor), 1.0))
            self.assertIn(str(cursor), dashboard._store_errors)
            # A title the query never returned must not be cached as "no title".
            self.assertNotIn(str(cursor), dashboard._cursor_title_cache)


class MalformedRecordTest(unittest.TestCase):
    """Every harness payload is untyped JSON read off disk. `x.get("k") or {}`
    is not a guard: any truthy non-dict passes the `or` and the next .get()
    raises, killing the collector for that refresh."""

    HOSTILE: ClassVar[list[Any]] = [5, "str", [1, 2], {"k": "v"}, None, True]
    PLACEHOLDER = "__HOSTILE__"

    def substitute(self, template: Any, value: Any) -> Any:
        if template == self.PLACEHOLDER:
            return value
        if isinstance(template, dict):
            return {k: self.substitute(v, value) for k, v in template.items()}
        if isinstance(template, list):
            return [self.substitute(v, value) for v in template]
        return template

    def templates(self) -> list[tuple[str, Any, list[dict[str, Any]]]]:
        hostile = self.PLACEHOLDER
        return [
            (
                "claude",
                dashboard.analyze_transcript,
                [
                    {"type": "assistant", "message": {"usage": hostile, "content": hostile}},
                    {"type": "user", "message": {"content": hostile}},
                    {"type": "assistant", "message": hostile},
                    {"type": "last-prompt", "lastPrompt": hostile},
                ],
            ),
            (
                "codex",
                dashboard.analyze_codex_transcript,
                [
                    {"type": "event_msg", "payload": hostile},
                    {"type": "event_msg", "payload": {"type": "token_count", "info": hostile}},
                    {
                        "type": "event_msg",
                        "payload": {"type": "token_count", "info": {"last_token_usage": hostile}},
                    },
                    {"type": "event_msg", "payload": {"type": "user_message", "message": hostile}},
                    {
                        "type": "response_item",
                        "payload": {"type": "function_call", "name": hostile},
                    },
                ],
            ),
            (
                "gemini",
                dashboard.analyze_gemini_transcript,
                [
                    {"type": "gemini", "toolCalls": hostile, "tokens": hostile},
                    {"type": "user", "content": hostile},
                    {"$set": hostile},
                    {"$set": {"messages": hostile}},
                ],
            ),
            (
                "copilot",
                dashboard.analyze_copilot_events,
                [
                    {"type": "session.start", "data": hostile},
                    {"type": "session.start", "data": {"context": hostile}},
                    {"type": "user.message", "data": hostile},
                    {"type": "subagent.started", "data": hostile},
                ],
            ),
            (
                "droid",
                dashboard.analyze_droid_transcript,
                [
                    {"type": "message", "message": hostile},
                    {"type": "message", "message": {"role": "user", "content": hostile}},
                    {"type": "message", "message": {"role": "assistant", "content": hostile}},
                ],
            ),
        ]

    def test_no_analyzer_raises_on_a_hostile_nested_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            for harness, analyzer, templates in self.templates():
                for template in templates:
                    for value in self.HOSTILE:
                        record = self.substitute(template, value)
                        path.write_text(json.dumps(record) + "\n")
                        with self.subTest(harness=harness, record=json.dumps(record)[:70]):
                            analyzer(str(path))  # must not raise

    def test_typed_accessors(self) -> None:
        not_dicts: list[Any] = [5, "str", [1, 2], None, True]
        for value in not_dicts:
            self.assertEqual({}, dashboard.as_dict(value))
            self.assertEqual({}, dashboard.message_dict({"message": value}))
        self.assertEqual({"a": 1}, dashboard.as_dict({"a": 1}))
        self.assertEqual({"a": 1}, dashboard.message_dict({"message": {"a": 1}}))
        self.assertEqual({}, dashboard.message_dict("not-a-record"))
        not_lists: list[Any] = [5, "str", {"k": 1}, None, True]
        for value in not_lists:
            self.assertEqual([], dashboard.as_list(value))
        self.assertEqual([1, 2], dashboard.as_list([1, 2]))


class HookOrderingTest(unittest.TestCase):
    def setUp(self) -> None:
        # This class does not inherit CargentoServerTest's shared reset, and
        # these tests mutate process-wide hook state.
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_state.clear()
            dashboard._hook_generation.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()

    def test_session_end_is_not_undone_by_a_slow_notification(self) -> None:
        # Notification handling does transcript lookups outside the lock. A
        # SessionEnd arriving during one used to be silently overwritten when
        # the notification committed its now-stale state.
        started = threading.Event()
        release = threading.Event()

        def slow_lookup(_prefix: str) -> bool:
            started.set()
            release.wait(timeout=5)
            return False

        def request(payload: dict[str, Any]) -> Any:
            handler = dashboard.Handler.__new__(dashboard.Handler)
            body = json.dumps(payload).encode()
            handler.headers = {"Content-Length": str(len(body))}
            handler.path = "/api/notify"
            handler.rfile = io.BytesIO(body)
            handler._local_ok = lambda **_kw: True
            handler._send = lambda *_a, **_k: None
            return handler

        session = "deadbeef-0000-0000-0000-000000000000"
        with (
            mock.patch.object(dashboard, "claude_prefix_is_agent", slow_lookup),
            mock.patch.object(dashboard, "notify_mac"),
        ):
            notification = request(
                {
                    "session_id": session,
                    "hook_event_name": "Notification",
                    "notification_type": "permission_prompt",
                    "message": "permission",
                }
            )
            thread = threading.Thread(target=notification.do_POST)
            thread.start()
            self.assertTrue(started.wait(timeout=5))
            request({"session_id": session, "hook_event_name": "SessionEnd"}).do_POST()
            release.set()
            thread.join(timeout=5)

        self.assertEqual({}, dashboard._hook_notifs, "SessionEnd was undone")

    def test_session_end_during_a_collection_neither_blocks_nor_pops(self) -> None:
        # The POST-side generation guard does not help a collection that
        # already read the hook. Without re-checking, an exited session was
        # still announced as blocked and burned the global popup cooldown.
        now = 1_700_000_000.0
        prefix = "abcdef12"
        with dashboard._lock:
            dashboard._hook_notifs[prefix] = {"ts": now, "message": "permission"}
        popups: list[Any] = []
        original = dashboard.current_hook

        def session_ends_mid_collection(pfx: str, event: str | None, ts: float) -> Any:
            hook = original(pfx, event, ts)
            with dashboard._lock:  # SessionEnd lands exactly here
                dashboard._hook_notifs.pop(pfx, None)
                dashboard._last_state.pop(pfx, None)
                dashboard._hook_generation[pfx] = dashboard._hook_generation.get(pfx, 0) + 1
            return hook

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / f"{prefix}-0000-0000-0000-000000000000.jsonl"
            transcript.write_text(json.dumps({"type": "user", "uuid": "u"}) + "\n")
            os.utime(transcript, (now - 200, now - 200))  # quiet, so the hook decides
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
                mock.patch.object(dashboard, "current_hook", session_ends_mid_collection),
                mock.patch.object(dashboard, "notify_mac", lambda *a: popups.append(a)),
            ):
                sessions = dashboard.collect_claude(now, 24, True)

        self.assertEqual("idle", sessions[0]["state"], "exited session shown as blocked")
        self.assertEqual([], popups, "popped for a session that had already ended")

    def _collect_with_session_end_injected(
        self, *, at: str, records: list[dict[str, Any]], standing_hook: bool
    ) -> tuple[str, int]:
        """Run collect_claude with a SessionEnd landing at ``at``."""
        now = 1_700_000_000.0
        prefix = "abcdef12"
        if standing_hook:
            with dashboard._lock:
                dashboard._hook_notifs[prefix] = {"ts": now, "message": "permission"}
        popups: list[Any] = []

        def end_session() -> None:
            with dashboard._lock:
                dashboard._hook_notifs.pop(prefix, None)
                dashboard._last_state.pop(prefix, None)
                dashboard._hook_generation[prefix] = dashboard._hook_generation.get(prefix, 0) + 1

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / f"{prefix}-0000-0000-0000-000000000000.jsonl"
            transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            os.utime(transcript, (now - 300, now - 300))  # quiet, so state is decided above

            patches: dict[str, Any] = {"notify_mac": lambda *a: popups.append(a)}
            if at == "analyze":
                real_analyze = dashboard.analyze_transcript

                def analyze(path: str) -> Any:
                    end_session()
                    return real_analyze(path)

                patches["analyze_transcript"] = analyze
            elif at == "popup":
                real_popup = dashboard.maybe_popup

                def popup(*args: Any, **kwargs: Any) -> None:
                    end_session()
                    real_popup(*args, **kwargs)

                patches["maybe_popup"] = popup

            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
                mock.patch.multiple(dashboard, **patches),
            ):
                sessions = dashboard.collect_claude(now, 24, True)
        return sessions[0]["state"], len(popups)

    ASK_USER_QUESTION: ClassVar[list[dict[str, Any]]] = [
        {
            "type": "assistant",
            "timestamp": "2023-11-14T00:00:00+00:00",
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "AskUserQuestion"}]},
        }
    ]
    PLAIN_USER: ClassVar[list[dict[str, Any]]] = [{"type": "user", "uuid": "u"}]

    def test_session_end_during_analysis_clears_a_transcript_detected_block(self) -> None:
        # The guard was sampled after analyze_transcript, which is the slow
        # part, and did not cover transcript-detected needs-input at all — so
        # an unanswered AskUserQuestion in a session the user had quit stayed
        # on screen and popped.
        state, popups = self._collect_with_session_end_injected(
            at="analyze", records=self.ASK_USER_QUESTION, standing_hook=False
        )
        self.assertEqual("idle", state)
        self.assertEqual(0, popups)

    def test_session_end_at_popup_time_suppresses_the_popup(self) -> None:
        # Checking the generation in the caller left a window before
        # maybe_popup took the lock. The state is a snapshot and may still read
        # blocked until the next refresh, but the popup is irreversible and
        # must not fire for a session that has exited.
        _state, popups = self._collect_with_session_end_injected(
            at="popup", records=self.PLAIN_USER, standing_hook=True
        )
        self.assertEqual(0, popups)

    def test_a_standing_hook_still_blocks_and_pops_when_nothing_races(self) -> None:
        state, popups = self._collect_with_session_end_injected(
            at="none", records=self.PLAIN_USER, standing_hook=True
        )
        self.assertEqual("needs_input", state)
        self.assertEqual(1, popups)

    def _race_against_slow_notification(self, second: dict[str, Any]) -> dict[str, Any]:
        """Start an actionable Notification, land ``second`` mid-flight."""
        started = threading.Event()
        release = threading.Event()

        def slow_lookup(_prefix: str) -> bool:
            started.set()
            release.wait(timeout=5)
            return False

        def request(payload: dict[str, Any]) -> Any:
            handler = dashboard.Handler.__new__(dashboard.Handler)
            body = json.dumps(payload).encode()
            handler.headers = {"Content-Length": str(len(body))}
            handler.path = "/api/notify"
            handler.rfile = io.BytesIO(body)
            handler._local_ok = lambda **_kw: True
            handler._send = lambda *_a, **_k: None
            return handler

        session = "deadbeef-0000-0000-0000-000000000000"
        first = request(
            {
                "session_id": session,
                "hook_event_name": "Notification",
                "notification_type": "permission_prompt",
                "message": "NEEDS PERMISSION",
            }
        )
        with (
            mock.patch.object(dashboard, "claude_prefix_is_agent", slow_lookup),
            mock.patch.object(dashboard, "notify_mac"),
        ):
            thread = threading.Thread(target=first.do_POST)
            thread.start()
            self.assertTrue(started.wait(timeout=5))
            with mock.patch.object(dashboard, "claude_prefix_is_agent", lambda _: False):
                request(second).do_POST()
            release.set()
            thread.join(timeout=5)
        return dict(dashboard._hook_notifs)

    def test_a_clearing_notification_does_not_drop_a_racing_permission_prompt(self) -> None:
        # Only SessionEnd means "this session is gone". agent_completed and
        # idle_prompt end one alert, not the session — invalidating on those
        # dropped an actionable prompt that merely overlapped a clearing one,
        # losing a real "Claude is blocked" signal.
        for kind in ("agent_completed", "idle_prompt", "elicitation_complete"):
            with self.subTest(kind=kind):
                self.setUp()
                survived = self._race_against_slow_notification(
                    {
                        "session_id": "deadbeef-0000-0000-0000-000000000000",
                        "hook_event_name": "Notification",
                        "notification_type": kind,
                        "message": "done",
                    }
                )
                self.assertIn("deadbeef", survived, f"{kind} dropped a permission prompt")

    def test_session_end_still_supersedes_a_racing_notification(self) -> None:
        survived = self._race_against_slow_notification(
            {"session_id": "deadbeef-0000-0000-0000-000000000000", "hook_event_name": "SessionEnd"}
        )
        self.assertEqual({}, survived, "SessionEnd was undone")

    def test_an_unraced_notification_still_records(self) -> None:
        session = "cafebabe-0000-0000-0000-000000000000"
        handler = dashboard.Handler.__new__(dashboard.Handler)
        body = json.dumps(
            {
                "session_id": session,
                "hook_event_name": "Notification",
                "notification_type": "permission_prompt",
                "message": "permission",
            }
        ).encode()
        handler.headers = {"Content-Length": str(len(body))}
        handler.path = "/api/notify"
        handler.rfile = io.BytesIO(body)
        handler._local_ok = lambda **_kw: True
        handler._send = lambda *_a, **_k: None
        with (
            mock.patch.object(dashboard, "claude_prefix_is_agent", lambda _: False),
            mock.patch.object(dashboard, "notify_mac"),
        ):
            handler.do_POST()
        self.assertIn("cafebabe", dashboard._hook_notifs)


class NativeNotifierTest(unittest.TestCase):
    """Pure in platform_name, so both branches run on every runner rather than
    only the host's (design decision D-4)."""

    def test_backend_per_platform(self) -> None:
        self.assertEqual("osascript", dashboard.native_notifier("darwin"))
        # No native backend yet on these — that is Phase 6. Until then the
        # empty string tells the page to raise the notification itself.
        for platform_name in ("linux", "win32", "freebsd14", "cygwin"):
            with self.subTest(platform=platform_name):
                self.assertEqual("", dashboard.native_notifier(platform_name))

    def test_notify_mac_is_a_no_op_without_a_backend(self) -> None:
        with (
            mock.patch.object(dashboard.sys, "platform", "linux"),
            mock.patch.object(dashboard.subprocess, "run") as run,
        ):
            dashboard.notify_mac("title", "message")
        run.assert_not_called()

    def test_api_data_reports_who_owns_popups(self) -> None:
        # The page reads this to decide whether to notify; if it went missing,
        # macOS would double-notify and Linux would notify not at all.
        with mock.patch.object(dashboard.sys, "platform", "darwin"):
            self.assertEqual("osascript", dashboard.collect(24, False)["native_notify"])
        with mock.patch.object(dashboard.sys, "platform", "win32"):
            self.assertEqual("", dashboard.collect(24, False)["native_notify"])


class TextIoTest(unittest.TestCase):
    def test_task_json_is_read_as_utf8_regardless_of_locale(self) -> None:
        # The locale default is cp1252 on Windows, which mojibakes this subject
        # and raises on the bytes that code page leaves undefined.
        subject = "Ship the café ☕ feature"
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "abcdef12-0000-0000-0000-000000000000"
            session.mkdir()
            (session / "1.json").write_text(
                json.dumps({"id": "1", "subject": subject, "status": "pending"}),
                encoding="utf-8",
            )
            with mock.patch.object(dashboard, "TASKS_DIR", str(tmp)):
                tasks = dashboard.load_tasks()

        self.assertEqual([subject], [t["subject"] for t in tasks["abcdef12"]])

    def test_undecodable_task_file_is_skipped_not_raised(self) -> None:
        # UnicodeDecodeError is a ValueError but not a JSONDecodeError, so the
        # original handler let it escape and error the whole Claude collector.
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "abcdef12-0000-0000-0000-000000000000"
            session.mkdir()
            (session / "1.json").write_bytes(b'{"subject": "\xff\xfe bad utf-8"}')
            (session / "2.json").write_text(
                json.dumps({"id": "2", "subject": "good", "status": "pending"}),
                encoding="utf-8",
            )
            with mock.patch.object(dashboard, "TASKS_DIR", str(tmp)):
                tasks = dashboard.load_tasks()

        self.assertEqual(["good"], [t["subject"] for t in tasks["abcdef12"]])

    def test_diag_survives_an_unencodable_stream(self) -> None:
        class AsciiOnly(io.TextIOBase):
            def __init__(self) -> None:
                self.written: list[str] = []

            def write(self, s: str) -> int:
                s.encode("ascii")  # raises UnicodeEncodeError like a redirected log
                self.written.append(s)
                return len(s)

        stream = AsciiOnly()
        with contextlib.redirect_stdout(stream):
            dashboard.diag("collector error: café ☕")
        self.assertIn("caf\\xe9", "".join(stream.written))

    def test_diag_never_raises_on_a_closed_stream(self) -> None:
        closed = io.StringIO()
        closed.close()
        with contextlib.redirect_stdout(closed):
            dashboard.diag("anything")  # must not raise

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


class SqliteOptionalTest(unittest.TestCase):
    """sqlite3 is an optional stdlib module; minimal builds ship without it."""

    @contextlib.contextmanager
    def without_sqlite(self) -> Any:
        with mock.patch.object(dashboard, "SQLITE_IMPORT_ERROR", "No module named '_sqlite3'"):
            yield

    def test_db_backed_collectors_return_empty_instead_of_raising(self) -> None:
        with self.without_sqlite():
            self.assertFalse(dashboard.sqlite_available())
            for collector in (
                dashboard.collect_opencode,
                dashboard.collect_cursor,
                dashboard.collect_goose,
                dashboard.collect_antigravity,
            ):
                with self.subTest(collector=collector.__name__):
                    self.assertEqual([], collector(1_700_000_000.0, 24, False))

    def test_db_backed_harnesses_are_not_advertised_as_discovered(self) -> None:
        # Reporting "discovered" for a store we cannot open would show the
        # harness as present but permanently empty.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "opencode.db"
            db.write_bytes(b"")
            with (
                self.without_sqlite(),
                mock.patch.object(dashboard, "OPENCODE_DATA", str(tmp)),
                mock.patch.object(dashboard, "GOOSE_DB", str(db)),
            ):
                found = {
                    h["key"]: h["discovered"] for h in dashboard.collect(24, False)["harnesses"]
                }

        self.assertFalse(found["opencode"])
        self.assertFalse(found["goose"])

    def test_jsonl_harnesses_still_work_without_sqlite(self) -> None:
        now = 1_700_000_000.0
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            (projects / "-w-proj").mkdir(parents=True)
            transcript = projects / "-w-proj" / "aabbccdd-0000-0000-0000-000000000000.jsonl"
            transcript.write_text(json.dumps({"type": "user", "uuid": "u1"}) + "\n")
            os.utime(transcript, (now, now))
            with (
                self.without_sqlite(),
                mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
            ):
                sessions = dashboard.collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))


class SqliteTrulyAbsentTest(unittest.TestCase):
    """Patching the flag leaves sqlite3 imported, so it cannot catch an unbound
    name. This imports server.py in a subprocess where the module genuinely
    fails to import."""

    SCRIPT = """
import builtins, importlib.util, sys
real_import = builtins.__import__
def blocked(name, *a, **k):
    if name == "sqlite3" or name.startswith("sqlite3."):
        raise ImportError("No module named 'sqlite3'")
    return real_import(name, *a, **k)
builtins.__import__ = blocked
sys.modules.pop("sqlite3", None)
spec = importlib.util.spec_from_file_location("srv", {path!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)          # must not raise
builtins.__import__ = real_import
assert not m.sqlite_available(), "sqlite_available() should be False"
now = 1_700_000_000.0
for fn in (m.collect_opencode, m.collect_cursor, m.collect_goose):
    assert fn(now, 24, True) == [], fn.__name__
# Antigravity is discovered from store mtime and CLI logs, so it survives
# without sqlite3 — only its rate and ETA degrade. Give it a real store so
# this exercises the database-backed path instead of an empty glob.
import os, tempfile
ag = tempfile.mkdtemp()
open(os.path.join(ag, "conv-1.db"), "wb").write(b"not a database")
m.ANTIGRAVITY_CONVERSATIONS_DIR = ag
m.STORE_ROOTS["antigravity.root"] = [ag]
found_ag = m.collect_antigravity(now, 24, True)
assert len(found_ag) == 1, found_ag
assert found_ag[0]["rate_per_min"] == 0, "rate should degrade to zero"
assert found_ag[0]["turn"] is None, "no ETA without the database"
data = m.collect(24, True)          # full pass, including discovery predicates
found = {{h["key"]: h["discovered"] for h in data["harnesses"]}}
assert found["opencode"] is False and found["goose"] is False and found["cursor"] is False
report = m.diagnose(24)             # --diagnose must work too
assert report["sqlite"]["available"] is False
m.render_diagnosis(report)
print("OK")
"""

    def test_server_imports_and_runs_without_sqlite3(self) -> None:
        script = self.SCRIPT.format(path=str(SERVER_PATH))
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=60, check=False
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK", result.stdout)


class ClockSkewTest(unittest.TestCase):
    # A future timestamp satisfies every `now - ts <= threshold` test, so before
    # age()/is_fresh() a clock-skewed store pinned its session to Working
    # permanently and kept feeding its tokens into the output rate.
    NOW = 1_700_000_000.0
    SKEW = 86_400.0  # a day ahead, e.g. a WSL2 guest clock after host suspend

    def test_an_implausibly_future_timestamp_is_rejected(self) -> None:
        self.assertIsNone(dashboard.age(self.NOW, self.NOW + self.SKEW))
        self.assertEqual(10.0, dashboard.age(self.NOW, self.NOW - 10))

    def test_sampling_noise_is_clamped_rather_than_rejected(self) -> None:
        # stat() and the collection clock are read microseconds apart, and
        # coarse filesystems round upward — a small overshoot is not skew.
        jitter = dashboard.FUTURE_SKEW_TOLERANCE_SEC / 2
        self.assertEqual(0.0, dashboard.age(self.NOW, self.NOW + jitter))
        self.assertTrue(dashboard.is_fresh(self.NOW, self.NOW + jitter, 1))

    def test_a_future_timestamp_does_not_read_as_activity(self) -> None:
        # The whole point: negative ages used to pass every threshold test.
        self.assertFalse(
            dashboard.is_fresh(self.NOW, self.NOW + self.SKEW, dashboard.WORKING_THRESHOLD_SEC)
        )

    def test_future_dated_tokens_do_not_inflate_the_output_rate(self) -> None:
        info = {"usage_events": [(self.NOW + self.SKEW, 5000)]}
        self.assertEqual(0, dashboard.rate_from(info, self.NOW))

    def test_a_future_dated_turn_start_yields_no_eta(self) -> None:
        scan = {"turn_start": self.NOW + self.SKEW, "durations": [60.0]}
        self.assertIsNone(dashboard.turn_progress(scan, "working", self.NOW))

    def test_a_future_dated_transcript_does_not_read_as_working(self) -> None:
        session_id = "beefcafe-1111-2222-3333-444455556666"
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project = projects / "-w-skewed"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(json.dumps({"type": "user", "uuid": "u1"}) + "\n")
            future = self.NOW + self.SKEW
            os.utime(transcript, (future, future))
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
            ):
                # A day-ahead mtime previously made `now - mtime` negative, so
                # the session reported "working" for the whole day of skew.
                sessions = dashboard.collect_claude(self.NOW, 24, True)

        self.assertEqual(1, len(sessions))
        self.assertEqual("idle", sessions[0]["state"])


class GlobUnderTest(unittest.TestCase):
    # A legal directory name on every supported platform — deliberately not
    # using "*" or "?", which Windows forbids in filenames. Interpolated into a
    # glob pattern, "[...]" is a character class that matches nothing, so
    # discovery returned zero sessions with no error at all.
    HOSTILE = "A [Contractor]"

    def test_metacharacters_in_the_root_are_treated_literally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / self.HOSTILE
            (root / "sub").mkdir(parents=True)
            (root / "sub" / "found.jsonl").write_text("{}\n")

            self.assertEqual([], glob.glob(str(root / "*" / "*.jsonl")))  # the old behavior
            self.assertEqual(
                [str(root / "sub" / "found.jsonl")], dashboard.glob_under(str(root), "*", "*.jsonl")
            )

    def test_results_are_sorted_for_deterministic_tie_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("c.jsonl", "a.jsonl", "b.jsonl"):
                (Path(tmp) / name).write_text("{}\n")
            found = [Path(p).name for p in dashboard.glob_under(str(tmp), "*.jsonl")]
        self.assertEqual(["a.jsonl", "b.jsonl", "c.jsonl"], found)

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

    def test_notify_session_id_cannot_inject_a_glob_pattern(self) -> None:
        # The prefix reaches this glob straight from a POST body, so it must be
        # escaped rather than interpreted.
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            (projects / "proj").mkdir(parents=True)
            (projects / "proj" / "aaaaaaaa.jsonl").write_text(
                json.dumps({"type": "user", "agentName": "worker", "teamName": "session-bbbbbbbb"})
                + "\n"
            )
            with mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)):
                self.assertFalse(dashboard.claude_prefix_is_agent("[a-z]*"))
                self.assertTrue(dashboard.claude_prefix_is_agent("aaaaaaaa"))


class SqliteUriTest(unittest.TestCase):
    """Both platform branches are exercised on every runner via ``windows=``."""

    def test_posix_paths_escape_sqlite_reserved_characters(self) -> None:
        # SQLite percent-decodes the path portion and treats ? and # as
        # delimiters, so these three must not survive literally.
        cases = {
            "/data/plain.db": "file:/data/plain.db?mode=ro",
            "/data/a%41b.db": "file:/data/a%2541b.db?mode=ro",
            "/data/q?h.db": "file:/data/q%3Fh.db?mode=ro",
            "/data/f#g.db": "file:/data/f%23g.db?mode=ro",
            "/data/we ird.db": "file:/data/we%20ird.db?mode=ro",
            # A backslash is a legal POSIX filename character and must be
            # escaped, never treated as a separator.
            "/data/a\\b.db": "file:/data/a%5Cb.db?mode=ro",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(expected, dashboard.sqlite_ro_uri(path, windows=False))

    def test_posix_double_slash_root_gets_an_empty_authority(self) -> None:
        # "//dir" would otherwise parse as the URI authority "dir".
        self.assertEqual(
            "file:////dir/x.db",
            dashboard.sqlite_ro_uri("//dir/x.db", windows=False)[: -len("?mode=ro")],
        )

    def test_windows_paths_use_sqlite_drive_letter_form(self) -> None:
        # SQLite only recognizes a drive letter as "/X:/...".
        self.assertEqual(
            "file:/C:/Users/a/x.db?mode=ro",
            dashboard.sqlite_ro_uri(r"C:\Users\a\x.db", windows=True),
        )
        self.assertEqual(
            "file:/C:/Users/a%25b/x.db?mode=ro",
            dashboard.sqlite_ro_uri(r"C:\Users\a%b\x.db", windows=True),
        )

    def test_windows_unc_paths_keep_an_empty_authority(self) -> None:
        # "//server/share" would parse as the authority "server"; SQLite only
        # accepts an empty or "localhost" authority.
        self.assertEqual(
            "file:////server/share/x.db?mode=ro",
            dashboard.sqlite_ro_uri(r"\\server\share\x.db", windows=True),
        )

    def test_immutable_flag_is_opt_in(self) -> None:
        self.assertEqual(
            "file:/data/x.db?mode=ro&immutable=1",
            dashboard.sqlite_ro_uri("/data/x.db", immutable=True, windows=False),
        )

    def test_reserved_characters_open_a_real_database(self) -> None:
        # End-to-end on the host platform: before this builder existed, the "%"
        # path failed to open with "unable to open database file".
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a%41b.db", "we ird.db", "f#g.db"):
                path = Path(tmp) / name
                seed = sqlite3.connect(str(path))
                seed.execute("CREATE TABLE t(x)")
                seed.execute("INSERT INTO t VALUES (7)")
                seed.commit()
                seed.close()
                with self.subTest(name=name):
                    con = sqlite3.connect(dashboard.sqlite_ro_uri(str(path)), uri=True)
                    try:
                        self.assertEqual((7,), con.execute("SELECT x FROM t").fetchone())
                    finally:
                        con.close()

    def test_collectors_read_stores_whose_path_has_a_percent(self) -> None:
        # The regression that matters: a store under a directory containing "%"
        # must still produce sessions rather than silently disappearing.
        now = 1_700_000_000.0
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "100%pure"
            data.mkdir()
            db = data / "opencode.db"
            con = sqlite3.connect(str(db))
            con.execute(
                "CREATE TABLE session (id TEXT, parent_id TEXT, directory TEXT, "
                "title TEXT, time_updated INTEGER, time_archived INTEGER)"
            )
            con.execute(
                "INSERT INTO session VALUES ('s1', NULL, '/w/proj', 'Percent', ?, NULL)",
                (int(now * 1000),),
            )
            con.execute(
                "CREATE TABLE session_message (session_id TEXT, type TEXT, "
                "time_created INTEGER, data TEXT)"
            )
            con.commit()
            con.close()

            with mock.patch.object(dashboard, "OPENCODE_DATA", str(data)):
                sessions = dashboard.collect_opencode(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual("Percent", sessions[0]["title"])


# ---------------------------------------------------------------------------
# Behavioural contract suite.
#
# Written from expectation rather than derived from a bug: for every harness,
# state what the dashboard must do, then assert it. These run natively on each
# CI runner, so the same contract is checked against real macOS, Linux and
# Windows filesystem semantics.

STORE_CONSTANTS = (
    "PROJECTS_DIR",
    "TASKS_DIR",
    "CODEX_SESSIONS_DIR",
    "GEMINI_TMP",
    "ANTIGRAVITY_CLI_DIR",
    "ANTIGRAVITY_CONVERSATIONS_DIR",
    "ANTIGRAVITY_LOG_DIR",
    "ANTIGRAVITY_LAST_CONVERSATIONS",
    "COPILOT_DIR",
    "OPENCODE_DATA",
    "CURSOR_CHATS",
    "GOOSE_DB",
    "FACTORY_PROJECTS",
)


def _iso(when: float) -> str:
    return datetime.fromtimestamp(when, tz=UTC).isoformat()


def _jsonl(path: Path, records: list[dict[str, Any]], when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    os.utime(path, (when, when))


def _sqlite(path: Path, statements: list[tuple[str, tuple[Any, ...]]], when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    try:
        for sql, params in statements:
            con.execute(sql, params)
        con.commit()
    finally:
        con.close()
    os.utime(path, (when, when))


def build_claude(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    projects = root / "projects"
    _jsonl(
        projects / "-w-proj" / f"{sid}.jsonl",
        [
            {"type": "user", "uuid": "u1", "timestamp": _iso(when), "message": {"content": title}},
            {
                "type": "assistant",
                "timestamp": _iso(when),
                "message": {"usage": {"output_tokens": 10}, "content": []},
            },
        ],
        when,
    )
    return {"PROJECTS_DIR": str(projects), "TASKS_DIR": str(root / "tasks")}


def build_codex(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "2024" / "01" / "02" / "rollout-1.jsonl",
        [
            {
                "type": "session_meta",
                "timestamp": _iso(when),
                "payload": {"id": sid, "cwd": "/w/proj"},
            },
            {
                "type": "event_msg",
                "timestamp": _iso(when),
                "payload": {"type": "user_message", "message": title},
            },
        ],
        when,
    )
    return {"CODEX_SESSIONS_DIR": str(root)}


def build_gemini(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "proj" / "chats" / f"session-{sid}.jsonl",
        [
            {"sessionId": sid, "kind": "main", "directories": ["/w/proj"]},
            {"type": "user", "timestamp": _iso(when), "content": title},
        ],
        when,
    )
    return {"GEMINI_TMP": str(root)}


def build_antigravity(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    conversations = root / "conversations"
    _sqlite(
        conversations / f"{sid}.db",
        [("CREATE TABLE steps (idx INTEGER, step_type INTEGER, metadata BLOB)", ())],
        when,
    )
    cache = root / "cache" / "last_conversations.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({f"/w/{title}": sid}), encoding="utf-8")
    return {
        "ANTIGRAVITY_CONVERSATIONS_DIR": str(conversations),
        "ANTIGRAVITY_LOG_DIR": str(root / "log"),
        "ANTIGRAVITY_LAST_CONVERSATIONS": str(cache),
    }


def build_copilot(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "session-state" / sid / "events.jsonl",
        [
            {
                "type": "session.start",
                "timestamp": _iso(when),
                "data": {"context": {"cwd": "/w/proj"}},
            },
            {"type": "user.message", "timestamp": _iso(when), "data": {"text": title}},
        ],
        when,
    )
    return {"COPILOT_DIR": str(root)}


def build_opencode(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _sqlite(
        root / "opencode.db",
        [
            (
                "CREATE TABLE session (id TEXT, parent_id TEXT, directory TEXT, title TEXT, time_updated INTEGER, time_archived INTEGER)",
                (),
            ),
            (
                "INSERT INTO session VALUES (?, NULL, '/w/proj', ?, ?, NULL)",
                (sid, title, int(when * 1000)),
            ),
            (
                "CREATE TABLE session_message (session_id TEXT, type TEXT, time_created INTEGER, data TEXT)",
                (),
            ),
            (
                "INSERT INTO session_message VALUES (?, 'user', ?, ?)",
                (sid, int(when * 1000), json.dumps({"text": title})),
            ),
        ],
        when,
    )
    return {"OPENCODE_DATA": str(root)}


def build_cursor(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _sqlite(
        root / "w" / sid / "store.db",
        [
            ("CREATE TABLE meta (value TEXT)", ()),
            ("INSERT INTO meta VALUES (?)", (json.dumps({"name": title}).encode().hex(),)),
        ],
        when,
    )
    return {"CURSOR_CHATS": str(root)}


def build_goose(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    stamp = datetime.fromtimestamp(when, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    database = root / "sessions.db"
    _sqlite(
        database,
        [
            (
                "CREATE TABLE sessions (id TEXT, description TEXT, working_dir TEXT, updated_at TEXT, session_type TEXT, parent_session_id TEXT, archived_at TEXT)",
                (),
            ),
            (
                "INSERT INTO sessions VALUES (?, ?, '/w/proj', ?, NULL, NULL, NULL)",
                (sid, title, stamp),
            ),
            (
                "CREATE TABLE messages (session_id TEXT, role TEXT, created_timestamp INTEGER, content_json TEXT)",
                (),
            ),
            (
                "CREATE TABLE usage_ledger (session_id TEXT, created_timestamp INTEGER, output_tokens INTEGER)",
                (),
            ),
        ],
        when,
    )
    return {"GOOSE_DB": str(database)}


def build_droid(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "proj" / f"{sid}.jsonl",
        [
            {
                "type": "session_start",
                "id": sid,
                "sessionTitle": title,
                "cwd": "/w/proj",
                "timestamp": _iso(when),
            },
            {
                "type": "message",
                "timestamp": _iso(when),
                "message": {"role": "user", "content": title},
            },
        ],
        when,
    )
    return {"FACTORY_PROJECTS": str(root)}


# (harness key reported in /api/data, fixture builder, store files to corrupt)
HARNESSES: tuple[tuple[str, Any], ...] = (
    ("claude", build_claude),
    ("codex", build_codex),
    ("gemini", build_gemini),
    ("gemini", build_antigravity),
    ("copilot", build_copilot),
    ("opencode", build_opencode),
    ("cursor", build_cursor),
    ("goose", build_goose),
    ("droid", build_droid),
)


class HarnessContractTest(unittest.TestCase):
    """One behavioural contract, asserted against every harness.

    The rest of the suite grew out of specific bugs, so it covers Claude deeply
    and the other seven thinly. This states what the dashboard must do and
    checks all of them, on whichever OS the runner is.
    """

    NOW = 1_700_000_000.0
    SID = "abcdef12-3456-7890-abcd-ef1234567890"
    TITLE = "Investigate the failing build"

    def collect(self, build: Any, *, when: float, subdir: str = "store") -> dict[str, Any]:
        """Build one harness's store in isolation and run a full collection."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            # Point every store at an empty directory first, so a harness
            # installed on the developer's machine cannot leak into the result.
            patches: dict[str, str] = {name: str(empty / name) for name in STORE_CONSTANTS}
            patches.update(build(Path(tmp) / subdir, when, self.SID, self.TITLE))
            with contextlib.ExitStack() as stack:
                for name, value in patches.items():
                    stack.enter_context(mock.patch.object(dashboard, name, value))
                stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                stack.enter_context(mock.patch.object(dashboard.time, "time", lambda: self.NOW))
                collected: dict[str, Any] = dashboard.collect(24, show_all=True)
                return collected

    def sessions_for(self, data: dict[str, Any], key: str) -> list[dict[str, Any]]:
        return [s for s in data["sessions"] if s["harness"] == key]

    def test_a_fresh_store_is_discovered_and_reads_working(self) -> None:
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW)
                harness = next(h for h in data["harnesses"] if h["key"] == key)
                self.assertTrue(harness["discovered"], "store present but not discovered")
                self.assertIsNone(harness["error"])
                sessions = self.sessions_for(data, key)
                self.assertEqual(1, len(sessions), f"expected one session, got {sessions}")
                self.assertEqual("working", sessions[0]["state"])

    def test_a_stale_store_reads_idle_but_still_appears(self) -> None:
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW - 7200)
                sessions = self.sessions_for(data, key)
                self.assertEqual(1, len(sessions))
                self.assertEqual("idle", sessions[0]["state"])

    def test_an_absent_store_is_not_discovered_and_is_not_an_error(self) -> None:
        # "No harness here" and "harness broken" must never look the same.
        data = self.collect(lambda *_a: {}, when=self.NOW)
        for harness in data["harnesses"]:
            with self.subTest(harness=harness["key"]):
                self.assertFalse(harness["discovered"])
                self.assertIsNone(harness["error"])
        self.assertEqual([], data["sessions"])

    def test_a_future_dated_store_does_not_read_working(self) -> None:
        # A clock-skewed store must not invent activity, on any harness.
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW + 86_400)
                for session in self.sessions_for(data, key):
                    self.assertNotEqual("working", session["state"])
                    self.assertEqual(0, session["rate_per_min"])

    def test_one_session_in_two_candidate_roots_yields_one_row(self) -> None:
        # De-duplication has to be wired into collect(), not merely available:
        # scanning every candidate root is what makes a migrated store appear
        # twice, and only the full pass can collapse it.
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            first, second = Path(tmp) / "one", Path(tmp) / "two"
            build_opencode(first, self.NOW, self.SID, self.TITLE)
            build_opencode(second, self.NOW - 60, self.SID, self.TITLE)
            patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
            patches["OPENCODE_DATA"] = str(first)
            with contextlib.ExitStack() as stack:
                for name, value in patches.items():
                    stack.enter_context(mock.patch.object(dashboard, name, value))
                # primary == candidates[0], so the whole list is scanned.
                stack.enter_context(
                    mock.patch.dict(
                        dashboard.STORE_ROOTS,
                        {"opencode.data": [str(first), str(second)]},
                    )
                )
                stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                stack.enter_context(mock.patch.object(dashboard.time, "time", lambda: self.NOW))
                data = dashboard.collect(24, show_all=True)

        opencode = [s for s in data["sessions"] if s["harness"] == "opencode"]
        self.assertEqual(1, len(opencode), f"duplicate rows: {opencode}")
        self.assertEqual(self.NOW, opencode[0]["last_activity"], "kept the staler copy")
        self.assertEqual(1, data["summary"]["active_sessions"])

    def test_a_corrupt_store_never_breaks_the_collector(self) -> None:
        # Every store file replaced with junk: the harness may vanish or report
        # an error, but collection must complete and the others must survive.
        for key, build in HARNESSES:
            with (
                self.subTest(harness=key, fixture=build.__name__),
                tempfile.TemporaryDirectory() as tmp,
            ):
                empty = Path(tmp) / "empty"
                empty.mkdir()
                patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
                store = Path(tmp) / "store"
                patches.update(build(store, self.NOW, self.SID, self.TITLE))
                for path in store.rglob("*"):
                    if path.is_file():
                        path.write_bytes(b"\x00\xff not a valid store at all \xfe")
                with contextlib.ExitStack() as stack:
                    for name, value in patches.items():
                        stack.enter_context(mock.patch.object(dashboard, name, value))
                    stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                    data = dashboard.collect(24, show_all=True)  # must not raise
                self.assertIsInstance(data["sessions"], list)


class HostilePathContractTest(unittest.TestCase):
    """Store paths users really have. Every character here is legal on macOS,
    Linux and Windows; the ones Windows forbids (<>:"/\\|?*) are excluded so the
    same contract runs on all three."""

    NOW = 1_700_000_000.0
    SID = "abcdef12-3456-7890-abcd-ef1234567890"
    HOSTILE = (
        "A [Contractor]",  # glob character class
        "100% pure",  # SQLite URI percent-decoding
        "Ünïcode Café",  # non-ASCII
        "a#b",  # URI fragment
        "with space",
        "it's & more",
        "plus+equals=sign",
        "semi;colon,comma",
        "dollar$at@tilde~",
        "brace{s}paren(s)",
    )

    def test_every_harness_survives_a_hostile_store_path(self) -> None:
        for component in self.HOSTILE:
            for key, build in HARNESSES:
                with self.subTest(path=component, harness=key, fixture=build.__name__):
                    with tempfile.TemporaryDirectory() as tmp:
                        empty = Path(tmp) / "empty"
                        empty.mkdir()
                        patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
                        patches.update(
                            build(Path(tmp) / component / "store", self.NOW, self.SID, "T")
                        )
                        with contextlib.ExitStack() as stack:
                            for name, value in patches.items():
                                stack.enter_context(mock.patch.object(dashboard, name, value))
                            stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                            stack.enter_context(
                                mock.patch.object(dashboard.time, "time", lambda: self.NOW)
                            )
                            data = dashboard.collect(24, show_all=True)
                    found = [s for s in data["sessions"] if s["harness"] == key]
                    self.assertEqual(1, len(found), f"{key} lost its session under {component!r}")


class OperatingSystemExpectationTest(unittest.TestCase):
    """What Cargento should do per OS, stated as expectations rather than
    derived from bugs. Every case is exercised on every runner by passing the
    platform in, so Linux CI checks the Windows behaviour too."""

    def test_project_labels_shorten_on_every_platform(self) -> None:
        # Claude encodes the working directory into the projects/ directory
        # name. Replacing only "/" did nothing to a Windows home, so every
        # Claude row there showed the whole encoded path instead of a project.
        cases = [
            ("/Users/jared", "-Users-jared-repos-cargento", "repos-cargento"),
            ("/home/u", "-home-u-work-my-repo", "work-my-repo"),
            (r"C:\Users\jared", "C--Users-jared-repos-cargento", "repos-cargento"),
            (r"C:\Users\jared", "C--Users-jared", "(home)"),
            # Unknown encoding must degrade to showing the name, never crash.
            ("/Users/jared", "-somewhere-else", "somewhere-else"),
        ]
        for home, encoded, expected in cases:
            with self.subTest(home=home, encoded=encoded):
                prefix = dashboard.encoded_home_prefix(home)
                self.assertEqual(expected, dashboard.project_label(encoded, prefix))

    def test_task_age_degrades_to_mtime_without_birthtime(self) -> None:
        # Linux, and Windows before Python 3.12, expose no st_birthtime. The
        # documented consequence is that completed-task ages come from mtime;
        # it must degrade, not raise.
        now = 1_700_000_000.0
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "abcdef12-0000-0000-0000-000000000000"
            session.mkdir()
            (session / "1.json").write_text(
                json.dumps({"id": "1", "subject": "task", "status": "completed"}),
                encoding="utf-8",
            )
            os.utime(session / "1.json", (now, now))

            real_stat = os.stat

            class NoBirthtime:
                """A stat result with birthtime removed, as on ext4."""

                def __init__(self, wrapped: Any) -> None:
                    self._wrapped = wrapped

                def __getattr__(self, name: str) -> Any:
                    if name == "st_birthtime":
                        raise AttributeError(name)
                    return getattr(self._wrapped, name)

            with (
                mock.patch.object(dashboard, "TASKS_DIR", str(tmp)),
                mock.patch.object(dashboard.os, "stat", lambda p: NoBirthtime(real_stat(p))),
            ):
                tasks = dashboard.load_tasks()

        task = tasks["abcdef12"][0]
        self.assertEqual(now, task["created"], "created should fall back to mtime")
        self.assertEqual(now, task["updated"])

    def test_notification_ownership_per_platform(self) -> None:
        # Exactly one layer notifies. macOS has a native backend, so the page
        # must stay silent there; the others have none yet, so the page owns it.
        self.assertEqual("osascript", dashboard.native_notifier("darwin"))
        for platform_name in ("linux", "win32", "cygwin", "freebsd14"):
            with self.subTest(platform=platform_name):
                self.assertEqual("", dashboard.native_notifier(platform_name))

    def test_port_sharing_policy_per_platform(self) -> None:
        # POSIX: SO_REUSEADDR only bypasses TIME_WAIT, so restarts work.
        # Windows: it lets another process bind an already-bound port.
        self.assertTrue(dashboard.reuse_address_allowed("posix"))
        self.assertFalse(dashboard.reuse_address_allowed("nt"))

    def test_store_locations_per_platform(self) -> None:
        posix = dashboard.resolve_store_roots(platform_name="darwin", environ={}, home="/Users/u")
        linux = dashboard.resolve_store_roots(
            platform_name="linux", environ={"XDG_DATA_HOME": "/xdg"}, home="/home/u"
        )
        windows = dashboard.resolve_store_roots(
            platform_name="win32",
            environ={
                "LOCALAPPDATA": r"C:\Users\j\AppData\Local",
                "APPDATA": r"C:\Users\j\AppData\Roaming",
            },
            home=r"C:\Users\j",
        )
        # Dot-directories under $HOME on every platform.
        self.assertEqual(["/Users/u/.claude/projects"], posix["claude.projects"])
        self.assertEqual([r"C:\Users\j\.claude\projects"], windows["claude.projects"])
        # XDG only where XDG applies.
        self.assertEqual(["/xdg/opencode"], linux["opencode.data"])
        self.assertEqual(["/xdg/goose/sessions/sessions.db"], linux["goose.db"])
        # Windows searches app-data in addition, never instead.
        self.assertIn(r"C:\Users\j\AppData\Local\opencode\data", windows["opencode.data"])
        self.assertIn(
            r"C:\Users\j\AppData\Roaming\Block\goose\data\sessions\sessions.db",
            windows["goose.db"],
        )
        # Every platform's paths use that platform's separator.
        for key, roots in windows.items():
            with self.subTest(key=key):
                self.assertTrue(all("/" not in r for r in roots), roots)
        for key, roots in posix.items():
            with self.subTest(key=key):
                self.assertTrue(all("\\" not in r for r in roots), roots)


class DocumentationMatchesCodeTest(unittest.TestCase):
    """Reviewers found documentation describing behaviour the code no longer
    had, twice. These assert the claims against the implementation."""

    SKILL = (SERVER_PATH.parent / "SKILL.md").read_text(encoding="utf-8")

    def posix_roots(self) -> dict[str, list[str]]:
        roots: dict[str, list[str]] = dashboard.resolve_store_roots(
            platform_name="darwin", environ={}, home="/HOME"
        )
        return roots

    def test_documented_store_paths_are_the_ones_searched(self) -> None:
        # Every "~/..." path in the data-source list must be a real default.
        documented = {
            "~/" + match
            for match in re.findall(r"`~/([\w./*<>-]+?)[`/]", self.SKILL)
            if not match.startswith(".claude/settings")
        }
        searched = {
            root.replace("/HOME", "~") for roots in self.posix_roots().values() for root in roots
        }
        for path in sorted(documented):
            with self.subTest(documented=path):
                self.assertTrue(
                    any(
                        root.startswith(path.rstrip("/")) or path.startswith(root)
                        for root in searched
                    ),
                    f"SKILL.md documents {path} but nothing searches it: {sorted(searched)}",
                )

    def test_documented_env_overrides_are_the_ones_honoured(self) -> None:
        documented = {
            name
            for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "GEMINI_CLI_HOME", "COPILOT_HOME")
            if f"`{name}`" in self.SKILL
        }
        self.assertEqual(set(dashboard.STORE_ENV_VARS), documented)
        # And each one actually redirects its store.
        for name, key, expected in (
            ("CLAUDE_CONFIG_DIR", "claude.projects", "/opt/x/projects"),
            ("CODEX_HOME", "codex.sessions", "/opt/x/sessions"),
            ("GEMINI_CLI_HOME", "gemini.tmp", "/opt/x/.gemini/tmp"),
            ("COPILOT_HOME", "copilot.root", "/opt/x"),
        ):
            with self.subTest(env=name):
                roots = dashboard.resolve_store_roots(
                    platform_name="linux", environ={name: "/opt/x"}, home="/HOME"
                )
                self.assertEqual([expected], roots[key])

    def test_the_documented_python_floor_matches_the_tooling(self) -> None:
        self.assertIn("Python 3.11+", self.SKILL)
        pyproject = (SERVER_PATH.parents[3] / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('python_version = "3.11"', pyproject)
        self.assertIn('target-version = "py311"', pyproject)

    def test_documented_urls_use_the_address_the_server_binds(self) -> None:
        # The listener is IPv4-only, so "localhost" can resolve to ::1 and fail.
        self.assertNotIn("http://localhost:4553", self.SKILL)
        self.assertIn("http://127.0.0.1:4553", self.SKILL)


if __name__ == "__main__":
    unittest.main()
