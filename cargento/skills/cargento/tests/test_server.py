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
import unicodedata
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import mock

if TYPE_CHECKING:
    from collections.abc import Iterator

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


def protobuf_varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def protobuf_bytes_field(number: int, value: bytes) -> bytes:
    return protobuf_varint((number << 3) | 2) + protobuf_varint(len(value)) + value


def protobuf_int_field(number: int, value: int) -> bytes:
    return protobuf_varint(number << 3) + protobuf_varint(value)


def write_antigravity_metadata(path: Path, blob: bytes) -> None:
    with contextlib.closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE trajectory_metadata_blob (id TEXT PRIMARY KEY, data BLOB)")
        connection.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (blob,))
        connection.commit()


class PageJsHarness(unittest.TestCase):
    """Runs the dashboard page's real JS under node against a stub DOM.

    Shared by every test that asserts on page *behaviour* rather than on the
    text of ``PAGE``: string assertions rot silently, executed ones do not.
    """

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

    def _run_page_js(self, checks: str, prelude: str = "") -> Any:
        """`prelude` runs before the page script, for globals the page reads at
        load time (localStorage) or feature-detects (navigator.clipboard)."""
        match = re.search(r"<script>\n(.*?)</script>", dashboard.PAGE, re.DOTALL)
        assert match is not None
        script = match.group(1)
        with tempfile.TemporaryDirectory() as tmp:
            js = Path(tmp) / "page_test.js"
            # Checks run inside an async IIFE so they can await the async
            # stubs (permission settles on a microtask, as in a browser).
            # Explicit UTF-8 both ways: the page carries glyphs outside Latin-1,
            # and on Windows the default is the locale codec (cp1252), which
            # raises instead of running the check. node speaks UTF-8.
            js.write_text(
                self.PAGE_JS_STUBS
                + prelude
                + script
                + "\n;(async () => {\n"
                + checks
                + "\n})();\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [shutil.which("node") or "node", str(js)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        self.assertEqual(0, proc.returncode, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])


class CargentoServerTest(PageJsHarness):
    def setUp(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()
            dashboard._last_state.clear()
            dashboard._hook_generation.clear()
        with dashboard._cache_lock:
            dashboard._meta_cache.clear()
            dashboard._cwd_cache.clear()
            dashboard._cursor_meta_cache.clear()
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
        self.assertEqual("recce/bridge", sessions[0]["project"])  # DRC-3963: <parent>/<basename>
        self.assertEqual("show my assigned issues", sessions[0]["title"])
        self.assertEqual("working", sessions[0]["state"])

    def test_antigravity_cache_primary_workspace_beats_added_directories(self) -> None:
        now = dashboard.time.time()
        session_ids = (
            "deadbeef-a01e-46f8-9286-60493c4c0e7e",
            "deadbeef-b01e-46f8-9286-60493c4c0e7e",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "antigravity-cli"
            conversations = root / "conversations"
            logs = root / "log"
            cache = root / "cache" / "last_conversations.json"
            conversations.mkdir(parents=True)
            logs.mkdir()
            cache.parent.mkdir()
            for session_id in session_ids:
                write_antigravity_metadata(
                    conversations / f"{session_id}.db",
                    protobuf_bytes_field(6, session_id.encode()),
                )
            cache.write_text(json.dumps({"/work/acme/proj": session_ids[1]}))
            (logs / "cli-1.log").write_text(
                "workspaceDirs=[/work/acme/proj /work/shared/lib] "
                f"appDataDir={root} cascadeManager=true\n"
                f"Created conversation {session_ids[0]}\n"
                f"Created conversation {session_ids[1]}\n"
            )

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(logs)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LAST_CONVERSATIONS", str(cache)),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual(2, len(sessions))
        self.assertEqual({"acme/proj"}, {session["project"] for session in sessions})
        dashboard.assign_display_ids(sessions)
        self.assertEqual(2, len({session["session"] for session in sessions}))
        self.assertTrue(all(len(session["session"]) > 8 for session in sessions))

    def test_antigravity_unusable_cache_workspace_does_not_block_log_fallback(self) -> None:
        now = dashboard.time.time()
        session_id = "c38d2d70-a01e-46f8-9286-60493c4c0e7e"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "antigravity-cli"
            conversations = root / "conversations"
            logs = root / "log"
            cache = root / "cache" / "last_conversations.json"
            conversations.mkdir(parents=True)
            logs.mkdir()
            cache.parent.mkdir()
            write_antigravity_metadata(
                conversations / f"{session_id}.db",
                protobuf_bytes_field(6, session_id.encode()),
            )
            cache.write_text(json.dumps({"relative/path": session_id}))
            (logs / "cli-1.log").write_text(
                "workspaceDirs=[/work/fallback/solo] "
                f"appDataDir={root} cascadeManager=true\n"
                f"Created conversation {session_id}\n"
            )

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(logs)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LAST_CONVERSATIONS", str(cache)),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual("fallback/solo", sessions[0]["project"])

    def test_antigravity_stale_log_can_anchor_active_workspace_context(self) -> None:
        now = dashboard.time.time()
        active_sid = "11111111-a01e-46f8-9286-60493c4c0e7e"
        cached_sid = "22222222-b01e-46f8-9286-60493c4c0e7e"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "antigravity-cli"
            conversations = root / "conversations"
            logs = root / "log"
            cache = root / "cache" / "last_conversations.json"
            conversations.mkdir(parents=True)
            logs.mkdir()
            cache.parent.mkdir()
            for session_id in (active_sid, cached_sid):
                write_antigravity_metadata(
                    conversations / f"{session_id}.db",
                    protobuf_bytes_field(6, session_id.encode()),
                )
            cache.write_text(json.dumps({"/work/acme/proj": cached_sid}))
            workspace = (
                "workspaceDirs=[/work/acme/proj /work/shared/lib] "
                f"appDataDir={root} cascadeManager=true\n"
            )
            stale_log = logs / "cli-old.log"
            stale_log.write_text(workspace + f"Created conversation {cached_sid}\n")
            (logs / "cli-current.log").write_text(
                workspace + f"Created conversation {active_sid}\n"
            )
            stale = now - (25 * 3600)
            os.utime(stale_log, (stale, stale))
            os.utime(conversations / f"{cached_sid}.db", (stale, stale))

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(logs)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LAST_CONVERSATIONS", str(cache)),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual([active_sid], [session["sid"] for session in sessions])
        self.assertEqual("acme/proj", sessions[0]["project"])

    def test_antigravity_stale_log_can_anchor_an_additional_context(self) -> None:
        now = dashboard.time.time()
        active_sid = "33333333-a01e-46f8-9286-60493c4c0e7e"
        cached_sid = "44444444-b01e-46f8-9286-60493c4c0e7e"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "antigravity-cli"
            logs = root / "log"
            cache = root / "cache" / "last_conversations.json"
            logs.mkdir(parents=True)
            cache.parent.mkdir()
            cache.write_text(json.dumps({"/work/acme/proj": cached_sid}))
            stale_context = (
                "workspaceDirs=[/work/acme/proj /work/shared/lib] "
                f"appDataDir={root} cascadeManager=true\n"
            )
            other_context = (
                "workspaceDirs=[/work/acme/proj /work/other/lib] "
                f"appDataDir={root} cascadeManager=true\n"
            )
            stale_log = logs / "cli-old.log"
            stale_log.write_text(stale_context + f"Created conversation {cached_sid}\n")
            (logs / "cli-current.log").write_text(
                stale_context
                + f"Created conversation {active_sid}\n"
                + other_context
                + f"Created conversation {cached_sid}\n"
            )
            stale = now - (25 * 3600)
            os.utime(stale_log, (stale, stale))

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(logs)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LAST_CONVERSATIONS", str(cache)),
            ):
                metadata = dashboard.antigravity_session_metadata(now, 24, False)

        self.assertEqual("/work/acme/proj", metadata[active_sid]["cwd"])
        self.assertEqual("/work/acme/proj", metadata[cached_sid]["cwd"])

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

    def test_antigravity_subagents_are_folded_under_parent(self) -> None:
        now = dashboard.time.time()
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"

        parent_blob = protobuf_bytes_field(6, parent_sid.encode())
        sub_blob = protobuf_bytes_field(5, parent_sid.encode()) + protobuf_bytes_field(
            8, protobuf_bytes_field(2, b"Research Auditor")
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "antigravity-cli"
            conversations = root / "conversations"
            logs = root / "log"
            conversations.mkdir(parents=True)
            logs.mkdir(parents=True)

            for sid, blob in [(parent_sid, parent_blob), (sub_sid, sub_blob)]:
                write_antigravity_metadata(conversations / f"{sid}.db", blob)

            (logs / "cli-1.log").write_text(
                f"workspaceDirs=[/tmp/test-project] appDataDir=/tmp\n"
                f"Streaming conversation {parent_sid}\n"
                'HandleUserInput called with text: "Inspect codebase"\n'
                f"Forwarding user message to conversation {parent_sid}\n"
            )

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(logs)),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(root / "cache" / "last_conversations.json"),
                ),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual(parent_sid, sessions[0]["sid"])
        self.assertEqual(["Research Auditor"], sessions[0]["subagents"])

    def test_antigravity_folded_subagent_rate_reaches_parent(self) -> None:
        now = dashboard.time.time()
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"

        with tempfile.TemporaryDirectory() as tmp:
            conversations = Path(tmp)
            write_antigravity_metadata(
                conversations / f"{parent_sid}.db",
                protobuf_bytes_field(6, parent_sid.encode()),
            )
            sub_path = conversations / f"{sub_sid}.db"
            write_antigravity_metadata(
                sub_path,
                protobuf_bytes_field(5, parent_sid.encode())
                + protobuf_bytes_field(8, protobuf_bytes_field(2, b"Research Auditor")),
            )
            timestamp = protobuf_int_field(1, int(now - 30))
            usage = protobuf_int_field(3, 600)
            step = protobuf_bytes_field(1, timestamp) + protobuf_bytes_field(9, usage)
            with contextlib.closing(sqlite3.connect(sub_path)) as connection:
                connection.execute(
                    "CREATE TABLE steps ("
                    "idx INTEGER PRIMARY KEY, step_type INTEGER, status INTEGER, metadata BLOB)"
                )
                connection.execute("INSERT INTO steps VALUES (1, 15, 3, ?)", (step,))
                connection.commit()

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(conversations / "logs")),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(conversations / "last_conversations.json"),
                ),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual([parent_sid], [session["sid"] for session in sessions])
        self.assertEqual(60, sessions[0]["rate_per_min"])

    def test_antigravity_nested_subagent_activity_reaches_root(self) -> None:
        now = dashboard.time.time()
        root_sid = "11111111-1111-1111-1111-111111111111"
        child_sid = "22222222-2222-2222-2222-222222222222"
        grandchild_sid = "33333333-3333-3333-3333-333333333333"

        with tempfile.TemporaryDirectory() as tmp:
            conversations = Path(tmp)
            write_antigravity_metadata(
                conversations / f"{root_sid}.db",
                protobuf_bytes_field(6, root_sid.encode()),
            )
            write_antigravity_metadata(
                conversations / f"{child_sid}.db",
                protobuf_bytes_field(5, root_sid.encode())
                + protobuf_bytes_field(8, protobuf_bytes_field(2, b"Parent Worker")),
            )
            grandchild_path = conversations / f"{grandchild_sid}.db"
            write_antigravity_metadata(
                grandchild_path,
                protobuf_bytes_field(5, child_sid.encode())
                + protobuf_bytes_field(8, protobuf_bytes_field(2, b"Nested Auditor")),
            )
            grandchild_mtime = os.path.getmtime(grandchild_path)
            stale = now - (25 * 3600)
            for sid in (root_sid, child_sid):
                os.utime(conversations / f"{sid}.db", (stale, stale))

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(conversations / "logs")),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(conversations / "last_conversations.json"),
                ),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual([root_sid], [session["sid"] for session in sessions])
        self.assertEqual(["Nested Auditor"], sessions[0]["subagents"])
        self.assertEqual("working", sessions[0]["state"])
        self.assertEqual("running 1 subagent", sessions[0]["state_detail"])
        self.assertEqual(grandchild_mtime, sessions[0]["last_activity"])

    def test_antigravity_future_wal_does_not_hide_fresh_store(self) -> None:
        now = dashboard.time.time()
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "conversation.db"
            database.touch()
            os.utime(database, (now, now))
            wal = Path(f"{database}-wal")
            wal.write_bytes(b"\0" * 33)
            future = now + dashboard.FUTURE_SKEW_TOLERANCE_SEC + 60
            os.utime(wal, (future, future))

            mtime = dashboard.antigravity_store_mtime(str(database), now)

        self.assertEqual(now, mtime)

    def test_antigravity_empty_wal_does_not_invent_activity(self) -> None:
        now = dashboard.time.time()
        database_mtime = now - dashboard.WORKING_THRESHOLD_SEC - 1
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "conversation.db"
            database.touch()
            os.utime(database, (database_mtime, database_mtime))
            wal = Path(f"{database}-wal")
            wal.touch()
            os.utime(wal, (now, now))

            mtime = dashboard.antigravity_store_mtime(str(database), now)

        self.assertEqual(database_mtime, mtime)

    def test_antigravity_stale_subagents_do_not_get_running_pills(self) -> None:
        now = dashboard.time.time()
        parent_sid = "11111111-1111-1111-1111-111111111111"
        fresh_sid = "22222222-2222-2222-2222-222222222222"
        stale_sid = "33333333-3333-3333-3333-333333333333"
        parent_blob = protobuf_bytes_field(6, parent_sid.encode())

        with tempfile.TemporaryDirectory() as tmp:
            conversations = Path(tmp)
            write_antigravity_metadata(conversations / f"{parent_sid}.db", parent_blob)
            for sid, label in (
                (fresh_sid, b"Fresh Auditor"),
                (stale_sid, b"Finished Auditor"),
            ):
                blob = protobuf_bytes_field(5, parent_sid.encode()) + protobuf_bytes_field(
                    8, protobuf_bytes_field(2, label)
                )
                write_antigravity_metadata(conversations / f"{sid}.db", blob)
            stale = now - dashboard.WORKING_THRESHOLD_SEC - 1
            os.utime(conversations / f"{stale_sid}.db", (stale, stale))

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(conversations / "logs")),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(conversations / "last_conversations.json"),
                ),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual(["Fresh Auditor"], sessions[0]["subagents"])
        self.assertEqual("running 1 subagent", sessions[0]["state_detail"])

    def test_antigravity_skips_unrelated_stale_metadata_stores(self) -> None:
        now = dashboard.time.time()
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"
        unrelated_sid = "33333333-3333-3333-3333-333333333333"

        with tempfile.TemporaryDirectory() as tmp:
            conversations = Path(tmp)
            write_antigravity_metadata(
                conversations / f"{parent_sid}.db",
                protobuf_bytes_field(6, parent_sid.encode()),
            )
            write_antigravity_metadata(
                conversations / f"{sub_sid}.db",
                protobuf_bytes_field(5, parent_sid.encode()),
            )
            write_antigravity_metadata(
                conversations / f"{unrelated_sid}.db",
                protobuf_bytes_field(6, unrelated_sid.encode()),
            )
            stale = now - (25 * 3600)
            for sid in (parent_sid, unrelated_sid):
                os.utime(conversations / f"{sid}.db", (stale, stale))

            inspected: list[str] = []
            real_session_info = dashboard.antigravity_session_info

            def inspect(path: str, sid: str) -> dict[str, Any]:
                inspected.append(sid)
                result: dict[str, Any] = real_session_info(path, sid)
                return result

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(conversations / "logs")),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(conversations / "last_conversations.json"),
                ),
                mock.patch.object(dashboard, "antigravity_session_info", side_effect=inspect),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual({parent_sid, sub_sid}, set(inspected))
        self.assertEqual([parent_sid], [session["sid"] for session in sessions])

    def test_antigravity_running_subagent_precedes_parent_tool_action(self) -> None:
        now = dashboard.time.time()
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"

        with tempfile.TemporaryDirectory() as tmp:
            conversations = Path(tmp)
            parent_path = conversations / f"{parent_sid}.db"
            write_antigravity_metadata(parent_path, protobuf_bytes_field(6, parent_sid.encode()))
            step = protobuf_bytes_field(1, protobuf_int_field(1, int(now))) + protobuf_bytes_field(
                31, b"Parent tool action"
            )
            with contextlib.closing(sqlite3.connect(parent_path)) as connection:
                connection.execute(
                    "CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, metadata BLOB)"
                )
                connection.execute(
                    "INSERT INTO steps VALUES (1, 21, ?)",
                    (step,),
                )
                connection.commit()
            write_antigravity_metadata(
                conversations / f"{sub_sid}.db",
                protobuf_bytes_field(5, parent_sid.encode())
                + protobuf_bytes_field(8, protobuf_bytes_field(2, b"Research Auditor")),
            )

            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(conversations / "logs")),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(conversations / "last_conversations.json"),
                ),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual("running 1 subagent", sessions[0]["state_detail"])

    def test_antigravity_blank_subagent_label_uses_session_prefix(self) -> None:
        now = dashboard.time.time()
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"

        with tempfile.TemporaryDirectory() as tmp:
            conversations = Path(tmp)
            write_antigravity_metadata(
                conversations / f"{parent_sid}.db",
                protobuf_bytes_field(6, parent_sid.encode()),
            )
            write_antigravity_metadata(
                conversations / f"{sub_sid}.db",
                protobuf_bytes_field(5, parent_sid.encode())
                + protobuf_bytes_field(8, protobuf_bytes_field(2, b"\x00\n")),
            )
            with (
                mock.patch.object(dashboard, "ANTIGRAVITY_CONVERSATIONS_DIR", str(conversations)),
                mock.patch.object(dashboard, "ANTIGRAVITY_LOG_DIR", str(conversations / "logs")),
                mock.patch.object(
                    dashboard,
                    "ANTIGRAVITY_LAST_CONVERSATIONS",
                    str(conversations / "last_conversations.json"),
                ),
            ):
                sessions = dashboard.collect_antigravity(now, 24, False)

        self.assertEqual(["subagent 22222222"], sessions[0]["subagents"])

    def test_antigravity_session_info_uses_decodable_fallback_fields(self) -> None:
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"
        blob = (
            protobuf_bytes_field(5, b"\xff")
            + protobuf_bytes_field(6, parent_sid.encode())
            + protobuf_bytes_field(
                8,
                protobuf_bytes_field(2, b"\xff") + protobuf_bytes_field(1, b"reviewer"),
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{sub_sid}.db"
            write_antigravity_metadata(path, blob)
            info = dashboard.antigravity_session_info(str(path), sub_sid)

        self.assertEqual(parent_sid, info["parent_id"])
        self.assertEqual("reviewer", info["subagent_label"])

    def test_antigravity_session_info_skips_blank_role_for_type_name(self) -> None:
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"
        blob = protobuf_bytes_field(5, parent_sid.encode()) + protobuf_bytes_field(
            8,
            protobuf_bytes_field(2, b" \t") + protobuf_bytes_field(1, b"reviewer"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{sub_sid}.db"
            write_antigravity_metadata(path, blob)
            info = dashboard.antigravity_session_info(str(path), sub_sid)

        self.assertEqual(parent_sid, info["parent_id"])
        self.assertEqual("reviewer", info["subagent_label"])

    def test_antigravity_session_info_falls_back_for_clean_wal_store(self) -> None:
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"
        blob = protobuf_bytes_field(5, parent_sid.encode()) + protobuf_bytes_field(
            8, protobuf_bytes_field(2, b"Research Auditor")
        )
        plain = mock.MagicMock(spec=sqlite3.Connection)
        plain.execute.side_effect = sqlite3.OperationalError("unable to open database file")
        immutable = mock.MagicMock(spec=sqlite3.Connection)
        immutable.execute.return_value.fetchone.return_value = (blob,)
        with mock.patch.object(
            dashboard.sqlite3,
            "connect",
            side_effect=(plain, immutable),
        ) as connect:
            with dashboard._cache_lock:
                dashboard._store_errors.clear()
            info = dashboard.antigravity_session_info("/tmp/session.db", sub_sid)

        self.assertEqual(parent_sid, info["parent_id"])
        self.assertEqual("Research Auditor", info["subagent_label"])
        self.assertEqual(2, connect.call_count)
        self.assertIn("immutable=1", connect.call_args_list[1].args[0])
        self.assertNotIn("/tmp/session.db", dashboard._store_errors)
        plain.close.assert_called_once_with()
        immutable.close.assert_called_once_with()

    def test_antigravity_session_info_does_not_bypass_live_wal(self) -> None:
        connection = mock.MagicMock(spec=sqlite3.Connection)
        connection.execute.side_effect = sqlite3.OperationalError("database is locked")
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(dashboard.sqlite3, "connect", return_value=connection) as connect,
        ):
            database = Path(tmp) / "session.db"
            Path(f"{database}-wal").write_bytes(b"\0" * 33)
            info = dashboard.antigravity_session_info(str(database), "session")

        self.assertEqual({"parent_id": None, "subagent_label": None}, info)
        self.assertEqual(1, connect.call_count)
        connection.close.assert_called_once_with()

    def test_antigravity_session_info_reads_closed_wal_store(self) -> None:
        parent_sid = "11111111-1111-1111-1111-111111111111"
        sub_sid = "22222222-2222-2222-2222-222222222222"
        blob = protobuf_bytes_field(5, parent_sid.encode()) + protobuf_bytes_field(
            8, protobuf_bytes_field(2, b"Research Auditor")
        )
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "session.db"
            with contextlib.closing(sqlite3.connect(database)) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    "CREATE TABLE trajectory_metadata_blob (id TEXT PRIMARY KEY, data BLOB)"
                )
                connection.execute(
                    "INSERT INTO trajectory_metadata_blob VALUES ('main', ?)",
                    (blob,),
                )
                connection.commit()
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            for sidecar in (Path(f"{database}-wal"), Path(f"{database}-shm")):
                with contextlib.suppress(FileNotFoundError):
                    sidecar.unlink()

            info = dashboard.antigravity_session_info(str(database), sub_sid)

        self.assertEqual(parent_sid, info["parent_id"])
        self.assertEqual("Research Auditor", info["subagent_label"])

    def test_antigravity_session_info_returns_empty_after_both_readers_fail(self) -> None:
        plain = mock.MagicMock(spec=sqlite3.Connection)
        plain.execute.side_effect = sqlite3.OperationalError("database is locked")
        immutable = mock.MagicMock(spec=sqlite3.Connection)
        immutable.execute.side_effect = sqlite3.OperationalError("database is malformed")
        with mock.patch.object(
            dashboard.sqlite3,
            "connect",
            side_effect=(plain, immutable),
        ) as connect:
            info = dashboard.antigravity_session_info("/tmp/session.db", "session")

        self.assertEqual({"parent_id": None, "subagent_label": None}, info)
        self.assertEqual(2, connect.call_count)
        plain.close.assert_called_once_with()
        immutable.close.assert_called_once_with()

    def test_protobuf_fields_rejects_non_blob_payloads_before_conversion(self) -> None:
        with self.assertRaisesRegex(TypeError, "bytes-like"):
            next(dashboard.protobuf_fields(8))

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

    def test_entity_slugs_elide_in_the_middle_not_the_tail(self) -> None:
        """Entity slugs in one workflow share a long prefix and differ only at
        the end, so tail truncation rendered two different entities as the same
        string. The full value stays available as a title attribute."""
        self.assertIn("function sdSlug(slug)", dashboard.PAGE)
        self.assertIn('title="${esc(ent.slug)}">${esc(sdSlug(ent.slug))}', dashboard.PAGE)

        node = shutil.which("node")
        if node is None:
            self.skipTest("node not installed; CI runs this branch")
        js = "\n".join(re.findall(r"<script[^>]*>\n?(.*?)</script>", dashboard.PAGE, re.DOTALL))
        # Just the helper and its constants. Taking the whole prefix would drag
        # in top-level browser globals (`location`) that node does not have.
        source = re.search(r"const SD_SLUG_MAX = .*?\n}\n", js, re.DOTALL)
        assert source is not None, "sdSlug and its constants moved"
        # Run the real function rather than restating its arithmetic here.
        probe = (
            source.group(0) + "\nconst cases = ['drc-3832',"
            " 'datarecce-recce-cloud-infra-pr-1573',"
            " 'datarecce-recce-cloud-infra-pr-1587'];\n"
            "console.log(JSON.stringify(cases.map(sdSlug)));\n"
        )
        with tempfile.TemporaryDirectory() as holder:
            script = Path(holder) / "probe.mjs"
            script.write_text(probe, encoding="utf-8")
            # Explicit UTF-8 both ways. node reads and writes UTF-8; `text=True`
            # alone decodes through the locale codec, so on Windows (cp1252) the
            # ellipsis comes back as "â€¦" — three characters, which fails both
            # the "elided" and the width assertion below for a reason that has
            # nothing to do with the code under test.
            proc = subprocess.run(
                [node, str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=True,
            )
        short, first, second = json.loads(proc.stdout)

        self.assertEqual("drc-3832", short)  # under the cap, untouched
        self.assertNotEqual(first, second)  # the whole point
        for rendered, full in ((first, "…-pr-1573"), (second, "…-pr-1587")):
            self.assertTrue(rendered.endswith(full[1:]), rendered)
            self.assertIn("…", rendered)
            self.assertLessEqual(len(rendered), 22)

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
        # Exactly one layer may notify per transition
        # (design decision D-3 in docs/design-cross-platform.md).
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

    def test_antigravity_activity_does_not_report_recovered_reader_error(self) -> None:
        now = dashboard.time.time()
        timestamp = protobuf_int_field(1, int(now - 30))
        usage = protobuf_int_field(3, 500)
        metadata = protobuf_bytes_field(1, timestamp) + protobuf_bytes_field(9, usage)
        plain = mock.MagicMock(spec=sqlite3.Connection)
        plain.execute.side_effect = sqlite3.OperationalError("unable to open database file")
        immutable = mock.MagicMock(spec=sqlite3.Connection)
        immutable.execute.return_value.fetchall.return_value = [(15, metadata)]

        with dashboard._cache_lock:
            dashboard._store_errors.clear()
        with mock.patch.object(
            dashboard.sqlite3,
            "connect",
            side_effect=(plain, immutable),
        ):
            activity = dashboard.antigravity_step_activity("/tmp/clean-wal.db", now)

        self.assertEqual(50, activity["rate_per_min"])
        self.assertNotIn("/tmp/clean-wal.db", dashboard._store_errors)
        plain.close.assert_called_once_with()
        immutable.close.assert_called_once_with()

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

    def test_uuidv7_sessions_started_together_get_distinct_display_ids(self) -> None:
        # DRC-3962. Codex ids are UUIDv7: the first 48 bits are a millisecond
        # timestamp, so a fan-out launched in one directory shares its leading
        # hex. Truncating the display id to 8 chars rendered four distinct
        # sessions as the same harness, project and id — one session, seen
        # four times. Observed live: 019fa752-a888…, -a889…, -a88d…, -a8a7….
        sessions = [
            dashboard.base_session("codex", f"019fa752-a88{tail}-7fe3-a529-ebd8042771c{i}", "p")
            for i, tail in enumerate(("8", "9", "d"))
        ]
        dashboard.assign_display_ids(sessions)
        shown = [s["session"] for s in sessions]

        self.assertEqual(len(shown), len(set(shown)))
        # The full id stays intact for keying; only the display id grows.
        self.assertEqual("019fa752-a888-7fe3-a529-ebd8042771c0", sessions[0]["sid"])

    def test_display_ids_widen_only_for_the_harness_that_collides(self) -> None:
        # Expanding every id because one pair collides would churn the whole
        # UI. The other harness's ids must be long enough to *show* whether
        # they were truncated: an 8-char sid is unaffected by any width, so a
        # test using one cannot tell per-harness widening from global.
        sessions = [
            dashboard.base_session("gemini", "aaaa1111-cccc-4444-8888-000000000001", "p"),
            dashboard.base_session("gemini", "bbbb2222-dddd-4444-8888-000000000002", "p"),
            dashboard.base_session("codex", "019fa752-a888-7fe3-a529-ebd8042771c1", "p"),
            dashboard.base_session("codex", "019fa752-a889-73a3-88ba-d362c54a1ae6", "p"),
        ]
        dashboard.assign_display_ids(sessions)

        # Gemini's ids already differ at 8 chars, so they stay at the floor
        # even though Codex in the same snapshot had to widen.
        self.assertEqual(["aaaa1111", "bbbb2222"], [s["session"] for s in sessions[:2]])
        codex = [s["session"] for s in sessions[2:]]
        self.assertEqual(len(codex), len(set(codex)))
        self.assertTrue(all(len(c) > 8 for c in codex))

    def test_a_colliding_fan_out_does_not_widen_unrelated_projects(self) -> None:
        # A four-agent fan-out started in the same millisecond needs 16 to 18
        # characters to separate. Grouping by harness alone would hand that
        # width to every other Codex row, including a lone session in an
        # unrelated worktree that was never ambiguous.
        sessions = [
            dashboard.base_session("codex", "019fa752-a888-7fe3-a529-ebd8042771c1", "recce/infra"),
            dashboard.base_session("codex", "019fa752-a889-73a3-88ba-d362c54a1ae6", "recce/infra"),
            dashboard.base_session("codex", "019fa752-a88d-7d23-978a-a8d2d2584c3b", "recce/infra"),
            dashboard.base_session("codex", "019fa752-a8a7-71f1-ac29-fd97c876c5e3", "recce/other"),
        ]
        dashboard.assign_display_ids(sessions)

        # The lone row in the other worktree keeps the floor.
        self.assertEqual("019fa752", sessions[3]["session"])
        colliding = [s["session"] for s in sessions[:3]]
        self.assertEqual(len(colliding), len(set(colliding)))

    def test_display_ids_ignore_collisions_across_different_harnesses(self) -> None:
        # Two harnesses can hand out the same id without either row being
        # ambiguous: the harness badge already separates them.
        shared = "019fa752-a888-7fe3-a529-ebd8042771c1"
        sessions = [
            dashboard.base_session("codex", shared, "p"),
            dashboard.base_session("gemini", shared, "p"),
        ]
        dashboard.assign_display_ids(sessions)

        self.assertEqual(["019fa752", "019fa752"], [s["session"] for s in sessions])

    def test_collect_widens_colliding_display_ids_end_to_end(self) -> None:
        # The widening is only worth anything if collect() actually applies
        # it: deleting the call leaves every unit test green.
        now = dashboard.time.time()
        iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        sids = (
            "019fa752-a888-7fe3-a529-ebd8042771c1",
            "019fa752-a889-73a3-88ba-d362c54a1ae6",
        )
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "codex" / "2026" / "07" / "28"
            rollout.mkdir(parents=True)
            for sid in sids:
                (rollout / f"rollout-2026-07-28T09-36-23-{sid}.jsonl").write_text(
                    json.dumps(
                        {
                            "timestamp": iso,
                            "type": "session_meta",
                            "payload": {"id": sid, "cwd": "/w/proj", "source": "exec"},
                        }
                    )
                    + "\n"
                )
            with (
                mock.patch.object(dashboard, "CODEX_SESSIONS_DIR", str(Path(tmp) / "codex")),
                mock.patch.dict(
                    dashboard.STORE_ROOTS, {"codex.sessions": [str(Path(tmp) / "codex")]}
                ),
            ):
                data = dashboard.collect(24, False)

        codex = [s for s in data["sessions"] if s["harness"] == "codex"]
        self.assertEqual(2, len(codex))
        shown = [s["session"] for s in codex]
        self.assertEqual(len(shown), len(set(shown)), f"collect() left ambiguous ids: {shown}")

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

    def test_identical_sids_do_not_widen_display_ids_forever(self) -> None:
        # Two rows with the same sid cannot be told apart by widening, so the
        # widening must not fire at all: it terminates, and it leaves the id
        # short rather than pointlessly expanding both to the full uuid.
        sessions = [
            dashboard.base_session("codex", "019fa752-a888-7fe3-a529-ebd8042771c1", "p"),
            dashboard.base_session("codex", "019fa752-a888-7fe3-a529-ebd8042771c1", "p"),
        ]
        dashboard.assign_display_ids(sessions)

        self.assertEqual(["019fa752"] * 2, [s["session"] for s in sessions])

    def test_claude_and_codex_agree_on_one_directory(self) -> None:
        # DRC-3963. The reported case: one worktree, two harnesses, two
        # different project strings — Claude showed the whole encoded path
        # ("git-spacedock-research-spacedock-subspace") while Codex showed a
        # bare basename. Same directory has to read the same on every row.
        now = dashboard.time.time()
        home = "/Users/cl"
        cwd = f"{home}/git/spacedock-research/spacedock/subspace"
        iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        encoded = dashboard.encoded_home_prefix(cwd)  # Claude's projects/ dir name
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / encoded
            project_dir.mkdir(parents=True)
            (project_dir / "aaaa1111-0000-0000-0000-000000000000.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": iso,
                        "cwd": cwd,
                        "message": {"role": "user", "content": "hi"},
                    }
                )
                + "\n"
            )
            rollout = Path(tmp) / "codex" / "2026" / "07" / "28"
            rollout.mkdir(parents=True)
            sid = "019f855d-aaaa-7000-8000-000000000001"
            (rollout / f"rollout-2026-07-28T09-36-23-{sid}.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": iso,
                        "type": "session_meta",
                        "payload": {"id": sid, "cwd": cwd, "source": "exec"},
                    }
                )
                + "\n"
            )
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
                mock.patch.object(dashboard, "CODEX_SESSIONS_DIR", str(Path(tmp) / "codex")),
                mock.patch.dict(
                    dashboard.STORE_ROOTS,
                    {
                        "claude.projects": [str(Path(tmp) / "projects")],
                        "claude.tasks": [str(Path(tmp) / "no-tasks")],
                        "codex.sessions": [str(Path(tmp) / "codex")],
                    },
                ),
                mock.patch.object(dashboard, "HOME", home),
                mock.patch.object(dashboard, "HOME_PREFIX", dashboard.encoded_home_prefix(home)),
            ):
                claude = dashboard.collect_claude(now, 24, False)
                codex = dashboard.collect_codex(now, 24, False)

        self.assertEqual(1, len(claude))
        self.assertEqual(1, len(codex))
        self.assertEqual("spacedock/subspace", claude[0]["project"])
        self.assertEqual(claude[0]["project"], codex[0]["project"])

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

    def _cursor_store(self, tmp: Path, sid: str, rows: list[Any]) -> None:
        db = tmp / "chats" / "hash1" / sid / "store.db"
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(str(db))
        try:
            con.execute("CREATE TABLE meta (value BLOB)")
            for row in rows:
                payload = json.dumps(row)
                # Cursor hex-encodes the JSON in some versions; cover that one.
                con.execute("INSERT INTO meta VALUES (?)", (payload.encode().hex(),))
            con.commit()
        finally:
            con.close()

    def _collect_cursor(self, tmp: Path) -> list[dict[str, Any]]:
        with (
            mock.patch.object(dashboard, "CURSOR_CHATS", str(tmp / "chats")),
            mock.patch.dict(dashboard.STORE_ROOTS, {"cursor.chats": [str(tmp / "chats")]}),
        ):
            sessions: list[dict[str, Any]] = dashboard.collect_cursor(
                dashboard.time.time(), 24, True
            )
            return sessions

    def test_cursor_reports_its_workspace_instead_of_the_harness_name(self) -> None:
        # DRC-3963. Cursor rows were hardcoded to "cursor", so every Cursor
        # session in every repository shared one label.
        if not dashboard.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "git" / "spacedock" / "subspace"
            workspace.mkdir(parents=True)
            self._cursor_store(
                root,
                "sess-1",
                [{"name": "refactor the parser", "workspacePath": str(workspace)}],
            )
            sessions = self._collect_cursor(root)

        self.assertEqual(1, len(sessions))
        self.assertEqual("spacedock/subspace", sessions[0]["project"])
        self.assertEqual("refactor the parser", sessions[0]["title"])

    def test_cursor_rejects_a_meta_value_that_is_not_a_real_directory(self) -> None:
        # The key spellings are inferred from the VS Code lineage, not observed,
        # and in that family "workspace" routinely holds a .code-workspace FILE
        # while workspaceStorage/<hash> paths are everywhere. Either would give
        # a confident wrong label, which is worse than the harness name.
        if not dashboard.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a_file = root / "mono.code-workspace"
            a_file.write_text("{}")
            self._cursor_store(root, "sess-file", [{"workspace": str(a_file)}])
            file_rows = self._collect_cursor(root)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_store(
                root, "sess-gone", [{"workspacePath": str(root / "workspaceStorage" / "9f2a3b")}]
            )
            missing_rows = self._collect_cursor(root)

        self.assertEqual("cursor", file_rows[0]["project"])
        self.assertEqual("cursor", missing_rows[0]["project"])

    def test_cursor_accepts_the_file_uri_spelling(self) -> None:
        # file:// is the canonical serialization in the VS Code family.
        # Rejecting it makes the whole read a silent no-op that looks exactly
        # like "Cursor records no workspace".
        if not dashboard.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "git" / "spacedock" / "subspace"
            workspace.mkdir(parents=True)
            self._cursor_store(
                root, "sess-uri", [{"workspacePath": workspace.as_uri(), "name": "n"}]
            )
            sessions = self._collect_cursor(root)

        self.assertEqual("spacedock/subspace", sessions[0]["project"])

    def test_cursor_prefers_the_best_trusted_key_across_rows(self) -> None:
        # The payload may spread keys across meta rows. First-row-wins would
        # let a low-trust "folder" in row 1 beat "workspacePath" in row 2, so
        # the ranking in _CURSOR_CWD_KEYS has to survive the row order.
        if not dashboard.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decoy = root / "exports" / "nightly-dump"
            decoy.mkdir(parents=True)
            real = root / "git" / "recce" / "cargento"
            real.mkdir(parents=True)
            self._cursor_store(
                root,
                "sess-order",
                [{"folder": str(decoy)}, {"workspacePath": str(real), "name": "real chat"}],
            )
            sessions = self._collect_cursor(root)

        self.assertEqual("recce/cargento", sessions[0]["project"])

    def test_cursor_finds_a_workspace_past_the_first_few_meta_rows(self) -> None:
        # A key/value table has no guaranteed order, and the old LIMIT was
        # tuned when only the title was being looked for.
        if not dashboard.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "git" / "spacedock" / "subspace"
            workspace.mkdir(parents=True)
            filler: list[Any] = [{"unrelated": i} for i in range(8)]
            self._cursor_store(root, "sess-late", [*filler, {"workspacePath": str(workspace)}])
            sessions = self._collect_cursor(root)

        self.assertEqual("spacedock/subspace", sessions[0]["project"])

    def test_cursor_title_survives_a_non_string_name(self) -> None:
        # A numeric "name" is truthy, so an `or` chain picks it and then the
        # isinstance guard discards a perfectly good "title" alongside it.
        if not dashboard.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_store(root, "sess-num", [{"name": 42, "title": "Fix the login bug"}])
            sessions = self._collect_cursor(root)

        self.assertEqual("Fix the login bug", sessions[0]["title"])

    def test_cursor_without_a_workspace_path_keeps_the_harness_name(self) -> None:
        now = dashboard.time.time()
        if not dashboard.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "chats" / "hash1" / "sess-2" / "store.db"
            db.parent.mkdir(parents=True)
            con = sqlite3.connect(str(db))
            try:
                con.execute("CREATE TABLE meta (value BLOB)")
                con.execute("INSERT INTO meta VALUES (?)", (json.dumps({"name": "n"}),))
                con.commit()
            finally:
                con.close()
            with (
                mock.patch.object(dashboard, "CURSOR_CHATS", str(Path(tmp) / "chats")),
                mock.patch.dict(
                    dashboard.STORE_ROOTS, {"cursor.chats": [str(Path(tmp) / "chats")]}
                ),
            ):
                sessions = dashboard.collect_cursor(now, 24, True)

        self.assertEqual("cursor", sessions[0]["project"])

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
        self.assertEqual("w/gooseproj", s["project"])  # DRC-3963: <parent>/<basename>
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
        self.assertEqual("w/droidproj", s["project"])  # DRC-3963: <parent>/<basename>
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


class PromptTitleTest(unittest.TestCase):
    """A session with no generated title falls back to its first prompt, and
    the harness wraps some prompts in markup. Measured over 248 real
    transcripts, 138 titles rendered as raw tags before this."""

    def test_a_slash_command_reads_as_the_command(self) -> None:
        prompt = (
            "<command-name>/plugin</command-name>\n"
            "            <command-message>plugin</command-message>\n"
            "            <command-args></command-args>"
        )

        self.assertEqual("/plugin", dashboard.prompt_title(prompt))

    def test_a_command_keeps_its_arguments(self) -> None:
        prompt = (
            "<command-message>recce-dev:claude-code-review</command-message>\n"
            "<command-name>/recce-dev:claude-code-review</command-name>\n"
            "<command-args>https://example.test/pr/1 and fix the findings</command-args>"
        )

        self.assertEqual(
            "/recce-dev:claude-code-review https://example.test/pr/1 and fix the findings",
            dashboard.prompt_title(prompt),
        )

    def test_a_wrapped_payload_shows_its_content_not_the_envelope(self) -> None:
        """The single most common case in the wild: 113 of the 138."""
        prompt = (
            '<teammate-message teammate_id="team-lead">\n'
            "Read the dispatch file and start the review\n"
            "</teammate-message>"
        )

        self.assertEqual(
            "Read the dispatch file and start the review", dashboard.prompt_title(prompt)
        )

    def test_an_ordinary_prompt_is_left_alone(self) -> None:
        self.assertEqual(
            "Fix the flaky Windows test",
            dashboard.prompt_title("Fix the flaky Windows test\nsecond line ignored"),
        )

    def test_markup_with_no_content_yields_nothing(self) -> None:
        # Better to fall through to another signal than to title a card "<>".
        for empty in ("<local-command-stdout></local-command-stdout>", "<a></a>", "   ", ""):
            with self.subTest(prompt=empty):
                self.assertIsNone(dashboard.prompt_title(empty))

    def test_the_title_is_bounded(self) -> None:
        self.assertLessEqual(len(dashboard.prompt_title("x " * 400, limit=10) or ""), 11)

    def test_absolute_paths_collapse_to_their_basename(self) -> None:
        self.assertEqual(
            "Round 3 review of PR #268 (repo pendulum-of-despair)",
            dashboard.prompt_title(
                "Round 3 review of PR #268 (repo /Users/jane/repos/pendulum-of-despair)"
            ),
        )

    def test_urls_and_relative_paths_survive_whole(self) -> None:
        """The repo and PR number in a link are the informative part, and a
        relative path names a file the reader can actually find."""
        for text in (
            "Review https://github.com/spacedock-dev/bridge/pull/77 fully",
            "In bridge, read internal/server/server.go and its siblings",
            "Research how Goose works (github.com/block/goose)",
        ):
            with self.subTest(text=text):
                self.assertEqual(text, dashboard.prompt_title(text))

    def test_truncation_lands_on_a_word_boundary(self) -> None:
        prompt = "Take your time and tell all subagents the same"
        title = dashboard.prompt_title(prompt, limit=30)

        assert title is not None
        self.assertTrue(title.endswith("…"), title)
        self.assertFalse(title.rstrip("…").endswith(" "), title)
        # A word was not cut in half. Compare against the prompt's WORDS: against
        # the bare string this passes on "su", a substring of "subagents", so it
        # could not fail for the mistake it exists to catch.
        self.assertIn(title.rstrip("…").split()[-1], prompt.split())

    def test_short_slashy_text_is_not_treated_as_a_path(self) -> None:
        """Only long paths eat the title budget, and short slash-runs are
        usually not paths at all. `^/api/v1/users$` collapsed to `^users$`
        before the length floor existed."""
        for text in (
            "Match the regex ^/api/v1/users$ in the router",
            "cd ~/repos/cargento && make test",
            "Serve /a/b from the CDN",
        ):
            with self.subTest(text=text):
                self.assertEqual(text, dashboard.prompt_title(text))

    def test_a_clip_does_not_end_on_an_orphaned_combining_mark(self) -> None:
        # The base character it belongs to was cut away, so it would render
        # against the ellipsis instead.
        decomposed = unicodedata.normalize("NFD", "é") * 60
        orphaned = [
            limit
            for limit in range(3, 60)
            if (kept := dashboard.clip(decomposed, limit).rstrip("…"))
            and unicodedata.combining(kept[-1])
        ]

        self.assertEqual([], orphaned)

    def test_a_hard_cut_does_not_leave_dangling_punctuation(self) -> None:
        # One long token has no boundary to fall back to, and ".…" reads as a
        # typo rather than as truncation.
        self.assertEqual("aaaa…", dashboard.clip("aaaa.bbbbbbbbbbbb", limit=5))

    def test_the_path_floor_is_a_boundary_not_a_vibe(self) -> None:
        # Mutation-checked: `<` vs `<=` on SD_MIN_COLLAPSED_PATH survived the
        # suite, so the exact cutover is pinned here.
        def path_of_length(total: int) -> str:
            return "/" + "a" * (total - 4) + "/bc"  # 1 + (total - 4) + 3

        floor = dashboard.SD_MIN_COLLAPSED_PATH
        just_under, just_over = path_of_length(floor - 1), path_of_length(floor)

        self.assertEqual((floor - 1, floor), (len(just_under), len(just_over)))
        self.assertEqual(just_under, dashboard.shorten_paths(just_under), "collapsed below floor")
        self.assertEqual("bc", dashboard.shorten_paths(just_over), "not collapsed at floor")


class DurationAndEpochTest(unittest.TestCase):
    """`fmt_duration` and `norm_epoch` render on every card and had no tests at
    all. Mutation-checked: each boundary below fails a real off-by-one that the
    suite previously missed."""

    def test_each_unit_changes_at_its_own_boundary(self) -> None:
        # The second either side of every cutover, because `<` vs `<=` here is
        # the difference between a card reading "60m" and "1h 0m".
        for seconds, expected in (
            (0, "0s"),
            (59, "59s"),
            (60, "1m"),
            (3599, "59m"),
            (3600, "1h 0m"),
            (3661, "1h 1m"),
            (86399, "23h 59m"),
            (86400, "1d 0h"),
            (90061, "1d 1h"),
        ):
            with self.subTest(seconds=seconds):
                self.assertEqual(expected, dashboard.fmt_duration(seconds))

    def test_an_unknown_or_impossible_duration_renders_a_dash(self) -> None:
        # A negative duration means the clock moved, not that work took
        # negative time, so the card must decline to state one.
        for bad in (None, -1, -0.5, -86400):
            with self.subTest(seconds=bad):
                self.assertEqual("–", dashboard.fmt_duration(bad))

    def test_millisecond_timestamps_are_detected_by_magnitude(self) -> None:
        """Harness stores mix seconds and milliseconds. Guessing wrong puts a
        session in 1970 or 55000 AD, and it silently reads as never-active."""
        self.assertEqual(1_700_000_000, dashboard.norm_epoch(1_700_000_000))
        self.assertEqual(1_700_000_000.0, dashboard.norm_epoch(1_700_000_000_000))
        # The cutover itself: 1e12 is seconds, one above it is milliseconds.
        self.assertEqual(1e12, dashboard.norm_epoch(1e12))
        self.assertAlmostEqual(1e9, dashboard.norm_epoch(1e12 + 1), places=0)

    def test_a_task_shorter_than_the_floor_does_not_licence_an_estimate(self) -> None:
        """The skill body promises "no estimate" until a session has a completed
        task that took at least 30s, so a burst of instant tasks cannot imply a
        confident ETA. Mutation-checked: `>=` vs `>` on that floor survived.

        The rule is exercised through `load_tasks` rather than through real
        files because `created` comes from `st_birthtime`, which Linux does not
        have. On that runner it degrades to mtime, every task looks
        zero-length, and a file-based fixture would assert nothing.
        """
        now = 1_700_000_000.0

        def tasks(took: float) -> dict[str, list[dict[str, Any]]]:
            return {
                "abcd1234": [
                    {
                        "id": "1",
                        "subject": "done",
                        "activeForm": "",
                        "status": "completed",
                        "created": now - took,
                        "updated": now,
                    },
                    {
                        "id": "2",
                        "subject": "still open",
                        "activeForm": "",
                        "status": "pending",
                        "created": now - 10,
                        "updated": now,
                    },
                ]
            }

        with tempfile.TemporaryDirectory() as empty:
            observed = {}
            for took in (29, 30, 60):
                with (
                    mock.patch.object(dashboard, "load_tasks", lambda t=took: tasks(t)),
                    mock.patch.object(dashboard, "PROJECTS_DIR", empty),
                ):
                    observed[took] = dashboard.collect_claude(now, 24, True)[0]["eta_h"]

        self.assertIsNone(observed[29], "29s of evidence is not enough for an ETA")
        # One open task times the 30s average.
        self.assertEqual("30s", observed[30])
        self.assertEqual("1m", observed[60])

    def test_a_missing_or_nonsense_timestamp_is_not_activity(self) -> None:
        # 0 is the "no timestamp" sentinel every freshness check treats as
        # ancient. Returning the raw value instead would date a session to 1970
        # and, for a negative, to before it.
        nonsense: list[Any] = [0, -5, "1700000000", None, [], {}]
        for bad in nonsense:
            with self.subTest(value=bad):
                self.assertEqual(0, dashboard.norm_epoch(bad))


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
        # Matching primary means "no override", so every candidate is searched.
        # Asserting against STORE_ROOTS itself would be circular, since
        # `store_roots` returns that list and both sides would move together.
        # The candidates are patched to literals instead, which also makes the
        # multi-root case run on every platform: on macOS the real table holds
        # exactly one candidate per key, so the distinction is invisible there.
        with mock.patch.dict(dashboard.STORE_ROOTS, {"opencode.data": ["/head", "/legacy"]}):
            self.assertEqual(["/head", "/legacy"], dashboard.store_roots("opencode.data", "/head"))
            self.assertEqual(["/fixture"], dashboard.store_roots("opencode.data", "/fixture"))

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

    def test_json_report_survives_a_round_trip_intact(self) -> None:
        """`--diagnose --json` is what a user pastes into an issue, so the
        contract is that it round-trips and still carries the fields that make
        it diagnostic. "Did not raise" would also be satisfied by `{}`."""
        report = dashboard.diagnose(24)

        self.assertEqual(report, json.loads(json.dumps(report)))
        self.assertLessEqual(
            {"platform", "python", "executable", "home", "env", "stores", "harnesses"},
            set(report),
        )
        # Every registered harness is accounted for, present or not: a missing
        # row is indistinguishable from a harness that was never checked.
        self.assertEqual(
            {key for key, *_ in dashboard.HARNESSES},
            {h["key"] for h in report["harnesses"]},
        )
        for harness in report["harnesses"]:
            with self.subTest(harness=harness["key"]):
                self.assertLessEqual({"key", "label", "discovered", "error"}, set(harness))

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
        #
        # Best-of-three per size, because a single sample is what made this
        # flaky on the Windows runner: one slow read reported a 9.0x ratio for
        # 4x the bytes on code that really scales at ~4x. The minimum is the
        # least contaminated estimate, and a quadratic regression cannot hide
        # in it.
        #
        # 16/64 MB rather than 4/16 so the measured time clears the floor below
        # on every runner. The floor stops a fast machine's near-zero baseline
        # from collapsing the budget into the noise, but it also caps
        # sensitivity: the comparison only fails a quadratic regression while
        # timings[0] > floor / 2, so the floor has to stay well under a real
        # measurement rather than replace it.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "long.jsonl"
            timings = []
            for megabytes in (16, 64):
                path.write_bytes(b"x" * (megabytes * 1024 * 1024))
                samples = []
                for _ in range(3):
                    start = time.perf_counter()
                    list(dashboard.reverse_lines(str(path)))
                    samples.append(time.perf_counter() - start)
                timings.append(min(samples))
        # Quadratic would be ~16x for 4x the bytes. Linear is ~4x; allow 8x for
        # a loaded CI runner while still failing a quadratic regression.
        self.assertLess(timings[1], max(timings[0], 0.01) * 8, f"non-linear: {timings}")

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
            self.assertEqual((None, ""), dashboard._cursor_meta(str(cursor), 1.0))
            self.assertIn(str(cursor), dashboard._store_errors)
            # A title the query never returned must not be cached as "no title".
            self.assertNotIn(str(cursor), dashboard._cursor_meta_cache)


class MalformedRecordTest(unittest.TestCase):
    """Every harness payload is untyped JSON read off disk. `x.get("k") or {}`
    is not a guard: any truthy non-dict passes the `or` and the next .get()
    raises, killing the collector for that refresh."""

    HOSTILE: ClassVar[list[Any]] = [5, "str", [1, 2], {"k": "v"}, None, True]
    PLACEHOLDER = "__HOSTILE__"
    # One record per harness that the analyzer really does parse, used to prove
    # a hostile neighbour did not leave it unable to read anything else.
    WELL_FORMED: ClassVar[dict[str, dict[str, Any]]] = {
        "claude": {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"content": [{"type": "text", "text": "hello"}]},
        },
        "codex": {"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}},
        "gemini": {"type": "user", "content": "hello"},
        "copilot": {"type": "user.message", "data": {"content": "hello"}},
        "droid": {"type": "user", "message": {"content": "hello"}},
    }

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

    def test_a_hostile_record_neither_raises_nor_poisons_the_analyzer(self) -> None:
        """The contract is that one bad record does not take a collector
        offline, so surviving the record is only half of it: the analyzer must
        still parse the good records around it. "Did not raise" would also pass
        an analyzer that bailed out and returned nothing from then on.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            for harness, analyzer, templates in self.templates():
                for template in templates:
                    for value in self.HOSTILE:
                        record = self.substitute(template, value)
                        with self.subTest(harness=harness, record=json.dumps(record)[:70]):
                            path.write_text(json.dumps(record) + "\n")
                            result = analyzer(str(path))

                            self.assertIsInstance(
                                result, dict, "a collector cannot use a non-dict result"
                            )
                            # The same analyzer, on the same file, with the bad
                            # record followed by a well-formed one.
                            path.write_text(
                                json.dumps(record) + "\n" + json.dumps(self.WELL_FORMED[harness])
                            )

                            self.assertIsInstance(analyzer(str(path)), dict)

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
    only the host's (design decision D-4 in docs/design-cross-platform.md)."""

    def test_backend_per_platform(self) -> None:
        self.assertEqual("osascript", dashboard.native_notifier("darwin"))
        # No native backend yet on these (tracked in
        # docs/plans/native-notifications.md). Until then the
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

    def test_a_closed_stream_costs_one_line_not_the_diagnostics(self) -> None:
        """Losing stdout mid-run must not raise, and must not leave the writer
        broken either. "Did not raise" alone would pass an implementation that
        silently stopped writing for the rest of the process."""
        closed = io.StringIO()
        closed.close()
        with contextlib.redirect_stdout(closed):
            dashboard.diag("swallowed")

        recovered = io.StringIO()
        with contextlib.redirect_stdout(recovered):
            dashboard.diag("written after the failure")

        self.assertEqual("written after the failure\n", recovered.getvalue())

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
store = os.path.join(ag, "conv-1.db")
open(store, "wb").write(b"not a database")
os.utime(store, (now, now))
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

    def test_project_from_cwd_is_parent_over_basename(self) -> None:
        # DRC-3963. Bare basename collapses every checkout named "subspace"
        # into one label, so the contract is the last two path segments.
        # home and windows are injected (D-4) so this runner exercises both
        # platforms rather than only its own.
        posix = [
            ("/Users/cl/git/spacedock-research/spacedock/subspace", "spacedock/subspace"),
            ("/Users/cl/repos/recce/cargento", "recce/cargento"),
            # Trailing separators are noise, not a segment.
            ("/Users/cl/repos/recce/cargento/", "recce/cargento"),
            # Outside home, one segment below root has no parent to show.
            ("/srv", "srv"),
            # A path under home is labelled relative to it, so the account
            # name never reaches a row. project_label() strips the same
            # prefix; the two must agree on this directory.
            ("/Users/cl/foo", "foo"),
            # Backslash is a legal POSIX filename character, so it must not
            # split a segment here (docs/design-cross-platform.md).
            ("/srv/my\\proj", "srv/my\\proj"),
            # Unusable input degrades to "" so each collector can apply its
            # own harness-name fallback.
            ("", ""),
            ("/", ""),
            ("relative/path", ""),
            ("..", ""),
            ("/Users/cl/repos/..", ""),
        ]
        for cwd, expected in posix:
            with self.subTest(cwd=cwd, platform="posix"):
                self.assertEqual(
                    expected, dashboard.project_from_cwd(cwd, home="/Users/cl", windows=False)
                )

        windows = [
            (r"C:\Users\cl\git\spacedock\subspace", "spacedock/subspace"),
            # Windows accepts either separator spelling for the same path.
            ("C:/Users/cl/git/spacedock/subspace", "spacedock/subspace"),
            (r"C:\proj", "proj"),
            (r"C:\Users\cl\foo", "foo"),
            (r"relative\path", ""),
        ]
        for cwd, expected in windows:
            with self.subTest(cwd=cwd, platform="windows"):
                self.assertEqual(
                    expected,
                    dashboard.project_from_cwd(cwd, home=r"C:\Users\cl", windows=True),
                )

    def test_project_from_cwd_names_the_home_directory_in_any_spelling(self) -> None:
        # project_label() renders a session started in $HOME as "(home)".
        # On Windows the same directory can be recorded with either separator
        # and either case, and all of those spellings are one directory.
        self.assertEqual(
            "(home)", dashboard.project_from_cwd("/Users/cl", home="/Users/cl", windows=False)
        )
        self.assertEqual(
            "(home)", dashboard.project_from_cwd("/Users/cl/", home="/Users/cl", windows=False)
        )
        # A sibling whose name merely starts with the home path is not home.
        self.assertEqual(
            "Users/clXYZ",
            dashboard.project_from_cwd("/Users/clXYZ", home="/Users/cl", windows=False),
        )
        for spelling in (r"C:\Users\jared", "C:/Users/jared", r"c:\users\JARED", "C:/Users/Jared/"):
            with self.subTest(spelling=spelling):
                self.assertEqual(
                    "(home)",
                    dashboard.project_from_cwd(spelling, home=r"C:\Users\jared", windows=True),
                )

    def test_project_from_cwd_agrees_with_project_label_under_home(self) -> None:
        # The whole point of DRC-3963 is that one directory reads the same on
        # every row. The cwd path and the encoded-name fallback are the two
        # ways a label is produced, so they have to produce the same string.
        home = "/Users/cl"
        for cwd in ("/Users/cl/foo", "/Users/cl/git/spacedock/subspace"):
            with self.subTest(cwd=cwd):
                encoded = dashboard.encoded_home_prefix(cwd)
                prefix = dashboard.encoded_home_prefix(home)
                from_cwd = dashboard.project_from_cwd(cwd, home=home, windows=False)
                from_name = dashboard.project_label(encoded, prefix)
                # The encoded name cannot be split back into segments, so it
                # keeps its hyphens; what must agree is that neither leaks the
                # account name.
                self.assertNotIn("cl", from_cwd.split("/")[0])
                self.assertEqual(
                    from_name.replace("-", "/").split("/")[-1], from_cwd.split("/")[-1]
                )

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


class SpacedockParserTest(unittest.TestCase):
    """Pure parsers, so every branch runs on every OS runner (decision D-4)."""

    DEBUG_FLYWHEEL: ClassVar[list[str]] = [
        "intake",
        "reproduce",
        "discover",
        "hypothesize",
        "verify",
        "fix-and-harden",
        "uat",
        "closed",
    ]

    def frontmatter(self, body: str) -> list[str]:
        lines: list[str] = dashboard.sd_frontmatter_lines(body)
        return lines

    def test_stage_names_read_document_order_past_sibling_blocks(self) -> None:
        """`transitions:` and a nested `decision:` must not leak into the spine."""
        body = (
            "---\n"
            "commissioned-by: spacedock@0.22.0\n"
            "state: .spacedock-state\n"
            "stages:\n"
            "  defaults:\n"
            "    worktree: false\n"
            "  states:\n"
            "    - name: intake\n"
            "      initial: true\n"
            "    - name: review\n"
            "    - name: fix-and-harden\n"
            "      worktree: true\n"
            "    - name: escalated\n"
            "      gate: true\n"
            "      decision:\n"
            "        field: verdict\n"
            "        options:\n"
            "          - {label: Close, value: CLOSED, handoff: fo}\n"
            "    - name: posted\n"
            "      terminal: true\n"
            "  transitions:\n"
            "    - from: review\n"
            "      to: intake\n"
            "      label: needs rework\n"
            "---\n"
            "# Prose\n"
        )
        lines = self.frontmatter(body)

        self.assertEqual("spacedock@0.22.0", dashboard.sd_scalar(lines, "commissioned-by"))
        self.assertEqual(
            ["intake", "review", "fix-and-harden", "escalated", "posted"],
            dashboard.sd_stage_names(lines),
        )
        # The initial and terminal flags belong to the item they are nested
        # under, and `gate:`/`worktree:`/the decision options are not flags.
        self.assertEqual(
            [("intake", True, False), ("posted", False, True)],
            [
                (entry["name"], entry["initial"], entry["terminal"])
                for entry in dashboard.sd_stage_entries(lines)
                if entry["initial"] or entry["terminal"]
            ],
        )

    def test_stage_flags_accept_yamls_true_ish_spellings(self) -> None:
        body = (
            "---\n"
            "stages:\n"
            "  states:\n"
            "    - name: intake\n"
            '      initial: "true"\n'
            "    - name: review\n"
            "      terminal: false\n"
            "    - name: posted\n"
            "      terminal: yes\n"
            "---\n"
        )

        self.assertEqual(
            [("intake", True, False), ("review", False, False), ("posted", False, True)],
            [
                (e["name"], e["initial"], e["terminal"])
                for e in dashboard.sd_stage_entries(self.frontmatter(body))
            ],
        )

    def test_frontmatter_requires_a_closed_leading_fence(self) -> None:
        for label, body in [
            ("no fence", "# Just prose\n"),
            ("unterminated", "---\nstages:\n"),
            ("prose first", "intro\n---\nstages:\n---\n"),
        ]:
            with self.subTest(case=label):
                self.assertEqual([], self.frontmatter(body))

    def test_stage_names_refuse_shapes_the_scanner_cannot_model(self) -> None:
        """An unmodellable construct must render no strip, never a wrong one."""
        cases = {
            "flow sequence": "stages:\n  states: [intake, review]\n",
            "no states block": "stages:\n  defaults:\n    worktree: false\n",
            "stages absent": "state: .spacedock-state\n",
            "illegal name": "stages:\n  states:\n    - name: Intake_Bad\n",
            "flow item": "stages:\n  states:\n    - {name: intake}\n    - name: review\n",
            "single char name": "stages:\n  states:\n    - name: x\n",
            "duplicate name": "stages:\n  states:\n    - name: review\n    - name: review\n",
        }
        for label, block in cases.items():
            with self.subTest(case=label):
                lines = ("---\n" + block + "---\n").split("\n")[1:-2]
                self.assertEqual([], dashboard.sd_stage_names(lines))

    def test_workers_are_attributed_to_a_known_slug(self) -> None:
        """Cycle markers appear on either side of the stage, and a slug may end
        in a cycle-shaped token of its own — so the slug must be known, never
        guessed off the name."""
        slugs = ["case-7", "verify-the-thing", "case-7-r3"]
        cases = [
            ("spacedock-ensign-case-7-uat", ("case-7", "uat", "")),
            ("spacedock-ensign-case-7-fix-and-harden", ("case-7", "fix-and-harden", "")),
            ("spacedock-ensign-case-7-cycle2-verify", ("case-7", "verify", "cycle2")),
            ("spacedock-ensign-case-7-verify-c2", ("case-7", "verify", "c2")),
            ("spacedock-ensign-case-7-verify-pass2b", ("case-7", "verify", "pass2b")),
            # A slug ending in a cycle-shaped token is one entity, not a retry of
            # a shorter slug: longest-slug-first keeps them apart.
            ("spacedock-ensign-case-7-r3-verify", ("case-7-r3", "verify", "")),
            # A slug containing a stage name survives intact.
            ("spacedock-ensign-verify-the-thing-uat", ("verify-the-thing", "uat", "")),
        ]
        for name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    expected,
                    dashboard.sd_attribute_worker(name, slugs, self.DEBUG_FLYWHEEL),
                )

    def test_workers_are_rejected_rather_than_mis_attributed(self) -> None:
        slugs = ["case-7"]
        for label, name in [
            ("not an ensign", "some-other-agent-uat"),
            ("slug unknown to this workflow", "spacedock-ensign-case-9-uat"),
            ("no known stage", "spacedock-ensign-case-7-shipit"),
            ("real content beside the stage", "spacedock-ensign-case-7-uat-extra"),
        ]:
            with self.subTest(case=label):
                self.assertIsNone(dashboard.sd_attribute_worker(name, slugs, self.DEBUG_FLYWHEEL))

    def test_boot_records_require_tool_result_provenance(self) -> None:
        """Boot output is command output. Conversation text that merely contains
        an envelope must not be able to nominate a path for Cargento to open."""
        envelope = (
            '{"command":"boot","id_style":"slug",'
            '"dispatchable":[{"slug":"drc-1","current":"review","next":"disposition"}],'
            '"definition_dir":"/w/one","entity_dir":"/w/one"}'
        )

        def line(block_type: str) -> bytes:
            return json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [{"type": block_type, "content": "=== BOOT ===\n" + envelope}]
                    },
                }
            ).encode()

        records = dashboard.sd_boot_records(line("tool_result"))

        self.assertEqual(1, len(records))
        self.assertEqual("/w/one", records[0]["definition_dir"])
        self.assertEqual({"drc-1": "review"}, dashboard.sd_boot_entities(records, "/w/one"))
        self.assertEqual(["/w/one"], dashboard.sd_workflow_dirs(records))
        # Same bytes, ordinary text block: no provenance, no record.
        self.assertEqual([], dashboard.sd_boot_records(line("text")))
        self.assertEqual([], dashboard.sd_boot_records(b'{"not":"jsonl definition_dir"}'))

    def test_boot_scan_is_bounded_against_decoy_candidates(self) -> None:
        """Every unbalanced candidate used to rescan to the end of the blob."""
        decoys = '{"command"' * 40_000
        payload = json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "content": decoys + " definition_dir"}]
                },
            }
        ).encode()
        started = time.monotonic()

        self.assertEqual([], dashboard.sd_boot_records(payload))

        self.assertLess(time.monotonic() - started, 1.0)

    def test_workflow_dirs_reject_relative_and_nul_paths(self) -> None:
        records = [
            {"command": "boot", "definition_dir": "docs/spacedock/rel"},
            {"command": "boot", "definition_dir": "/abs/ok"},
            {"command": "boot", "definition_dir": "/abs/ok"},
            {"command": "boot", "definition_dir": ""},
        ]

        self.assertEqual(["/abs/ok"], dashboard.sd_workflow_dirs(records))


class SpacedockReadContractTest(unittest.TestCase):
    """The one project read Cargento performs, and its refusals."""

    README = (
        "---\n"
        "commissioned-by: spacedock@0.22.0\n"
        "state: .spacedock-state\n"
        "stages:\n"
        "  states:\n"
        "    - name: intake\n"
        "      initial: true\n"
        "    - name: review\n"
        "    - name: posted\n"
        "      terminal: true\n"
        "---\n"
    )

    def setUp(self) -> None:
        with dashboard._cache_lock:
            dashboard._sd_workflow_cache.clear()
            dashboard._sd_boot_cache.clear()
            dashboard._sd_role_cache.clear()
            dashboard._sd_entity_cache.clear()

    def workflow(self, body: str | None = None) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="cargento-sd-")
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "wf"
        root.mkdir()
        if body is not None:
            (root / "README.md").write_text(body, encoding="utf-8")
        return root

    def entity(self, state: Path, slug: str, status: str, *, folder: bool = False) -> Path:
        state.mkdir(exist_ok=True)
        body = f'---\nid:\ntitle: "a thing"\nstatus: {status}\n---\n\n# report\n'
        if folder:
            (state / slug).mkdir()
            path = state / slug / "index.md"
        else:
            path = state / f"{slug}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_commissioned_readme_yields_its_ordered_stages(self) -> None:
        root = self.workflow(self.README)

        self.assertEqual(
            {
                "name": "wf",
                "stages": ["intake", "review", "posted"],
                "resting": ["intake", "posted"],
            },
            dashboard.sd_read_workflow(str(root)),
        )

    def test_uncommissioned_or_absent_readme_yields_nothing(self) -> None:
        cases = [
            ("absent", None),
            ("not commissioned", "---\nstages:\n  states:\n    - name: intake\n---\n"),
            ("commissioned but no stages", "---\ncommissioned-by: spacedock@1.0.0\n---\n"),
        ]
        for label, body in cases:
            with self.subTest(case=label):
                self.assertIsNone(dashboard.sd_read_workflow(str(self.workflow(body))))

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlink")
    def test_a_symlinked_readme_is_refused_not_followed(self) -> None:
        root = self.workflow(None)
        target = root.parent / "elsewhere.md"
        target.write_text(self.README, encoding="utf-8")
        try:
            (root / "README.md").symlink_to(target)
        except OSError:  # pragma: no cover - Windows without the privilege
            self.skipTest("symlink creation not permitted")

        self.assertIsNone(dashboard.sd_read_workflow(str(root)))

    def test_only_frontmatter_is_read_however_long_the_body(self) -> None:
        root = self.workflow(self.README + ("prose line\n" * 40_000))

        result = dashboard.sd_read_workflow(str(root))

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(["intake", "review", "posted"], result["stages"])

    def test_session_workflows_prefer_live_workers_then_boot_entities(self) -> None:
        root = self.workflow(self.README)
        boot = [
            {
                "command": "boot",
                "definition_dir": str(root),
                "dispatchable": [
                    {"slug": "drc-1", "current": "review"},
                    {"slug": "drc-2", "current": "intake"},
                    {"slug": "drc-3", "current": "not-a-stage"},
                ],
            }
        ]

        strips = dashboard.sd_session_workflows(
            boot, ["spacedock-ensign-drc-1-posted"], time.time(), 3600
        )

        self.assertEqual(1, len(strips))
        self.assertEqual(["intake", "review", "posted"], strips[0]["stages"])
        # The live worker wins for drc-1 (posted, not the booted review) and is
        # marked live; drc-3 is dropped because its stage is not declared.
        self.assertEqual(
            [("drc-1", "posted", True), ("drc-2", "intake", False)],
            [(e["slug"], e["stage"], e["live"]) for e in strips[0]["entities"]],
        )

    def test_entity_state_anchors_a_first_officer_that_booted_an_empty_queue(self) -> None:
        """The regression this whole path exists for. A first officer that boots
        before any entity is intaken reports `dispatchable: []` for the rest of
        the session; without the state directory there is no slug to anchor the
        live worker on, and the workflow renders no strip at all."""
        root = self.workflow(self.README)
        state = root / ".spacedock-state"
        self.entity(state, "drc-7", "intake")  # queued, not moving
        self.entity(state, "drc-8", "review")  # moving, no live worker
        self.entity(state, "drc-9", "posted")  # finished
        self.entity(state, "pr-42", "review")  # the live worker's entity
        boot = [
            {
                "command": "boot",
                "definition_dir": str(root),
                "entity_dir": str(state),
                "entity_dir_present": "false",
                "dispatchable": [],
            }
        ]

        strips = dashboard.sd_session_workflows(
            boot, ["spacedock-ensign-pr-42-posted"], time.time(), 3600
        )

        self.assertEqual(1, len(strips))
        # pr-42 is live and at the worker's stage, not the file's; drc-8 is in
        # flight; drc-7 (initial) and drc-9 (terminal) are resting, not moving.
        self.assertEqual(
            [("pr-42", "posted", True), ("drc-8", "review", False)],
            [(e["slug"], e["stage"], e["live"]) for e in strips[0]["entities"]],
        )

    def test_entity_state_is_read_newest_first_in_both_file_shapes(self) -> None:
        root = self.workflow(self.README)
        state = root / ".spacedock-state"
        older = self.entity(state, "drc-1", "review")
        newer = self.entity(state, "drc-2", "review", folder=True)
        os.utime(older, (1_700_000_000, 1_700_000_000))
        os.utime(newer, (1_700_000_100, 1_700_000_100))

        self.assertEqual(
            [("drc-2", "review"), ("drc-1", "review")],
            dashboard.sd_read_entities(
                str(state), ["intake", "review", "posted"], 1_700_000_200, 3600
            ),
        )

    def test_entity_state_refuses_everything_that_is_not_an_entity(self) -> None:
        root = self.workflow(self.README)
        state = root / ".spacedock-state"
        self.entity(state, "drc-1", "review")
        # Spacedock retires finished entities into _archive/, operators leave
        # reports beside the state, and a stage the workflow never declared
        # cannot be placed on the spine.
        self.entity(state / "_archive", "drc-0", "review")
        (state / "REVIEW-REPORT-DRC-1.md").write_text(
            "---\nstatus: review\n---\n", encoding="utf-8"
        )
        (state / "notes.txt").write_text("---\nstatus: review\n---\n", encoding="utf-8")
        self.entity(state, "drc-2", "not-a-declared-stage")
        self.entity(state, "drc-3", "")

        self.assertEqual(
            [("drc-1", "review")],
            dashboard.sd_read_entities(
                str(state), ["intake", "review", "posted"], time.time(), 3600
            ),
        )

    def test_entity_files_report_a_stat_that_identifies_the_file(self) -> None:
        """`scandir` caches a stat, and on Windows that cached result reports
        st_ino and st_dev as zero — which can never match the fstat of an open
        descriptor, so every entity file would be refused on that platform
        alone. Reproduced here by simulating the cached stat, because a POSIX
        runner cannot otherwise see it."""
        root = self.workflow(self.README)
        state = root / ".spacedock-state"
        self.entity(state, "drc-1", "review")
        real_scandir = os.scandir

        class WindowsLikeEntry:
            def __init__(self, entry: os.DirEntry[str]) -> None:
                self.name, self.path = entry.name, entry.path
                self._entry = entry

            def is_dir(self, *, follow_symlinks: bool = True) -> bool:
                return self._entry.is_dir(follow_symlinks=follow_symlinks)

            def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
                real = self._entry.stat(follow_symlinks=follow_symlinks)
                fields = list(real)
                fields[1] = 0  # st_ino
                fields[2] = 0  # st_dev
                # Only the identity fields are zeroed. The nanosecond times
                # have to be carried through the extended dict or they come
                # back as None and the failure under test is masked by a
                # TypeError in the sort.
                return os.stat_result(
                    fields,
                    {
                        "st_atime_ns": real.st_atime_ns,
                        "st_mtime_ns": real.st_mtime_ns,
                        "st_ctime_ns": real.st_ctime_ns,
                    },
                )

        @contextlib.contextmanager
        def windows_like_scandir(path: str) -> Iterator[list[WindowsLikeEntry]]:
            with real_scandir(path) as entries:
                yield [WindowsLikeEntry(entry) for entry in entries]

        with mock.patch.object(dashboard.os, "scandir", windows_like_scandir):
            found = dashboard.sd_entity_files(str(state))
            self.assertEqual(1, len(found))
            _, path, info = found[0]
            self.assertEqual(
                (os.stat(path).st_dev, os.stat(path).st_ino),
                (info.st_dev, info.st_ino),
            )
            self.assertEqual(
                [("drc-1", "review")],
                dashboard.sd_read_entities(
                    str(state), ["intake", "review", "posted"], time.time(), 3600
                ),
            )

    def test_entity_state_older_than_the_window_is_history_not_work(self) -> None:
        """A first officer discovers every workflow in the project. One retired
        months ago still has entities frozen mid-pipeline."""
        root = self.workflow(self.README)
        state = root / ".spacedock-state"
        stale = self.entity(state, "drc-1", "review")
        os.utime(stale, (1_700_000_000, 1_700_000_000))

        self.assertEqual(
            [],
            dashboard.sd_read_entities(
                str(state), ["intake", "review", "posted"], 1_700_000_000 + 90_000, 86_400
            ),
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlink")
    def test_a_symlinked_entity_file_is_refused_not_followed(self) -> None:
        root = self.workflow(self.README)
        state = root / ".spacedock-state"
        target = self.entity(state, "drc-1", "review")
        try:
            (state / "drc-2.md").symlink_to(target)
        except OSError:  # pragma: no cover - Windows without the privilege
            self.skipTest("symlink creation not permitted")

        self.assertEqual(
            [("drc-1", "review")],
            dashboard.sd_read_entities(
                str(state), ["intake", "review", "posted"], time.time(), 3600
            ),
        )

    def test_entity_frontmatter_is_reread_only_when_the_file_changes(self) -> None:
        root = self.workflow(self.README)
        state = root / ".spacedock-state"
        path = self.entity(state, "drc-1", "review")
        stages = ["intake", "review", "posted"]
        now = time.time()

        reads: list[str] = []
        real = dashboard.sd_read_frontmatter

        def counting(p: str, limit: int, expect: os.stat_result) -> list[str]:
            reads.append(p)
            lines: list[str] = real(p, limit, expect)
            return lines

        with mock.patch.object(dashboard, "sd_read_frontmatter", counting):
            dashboard.sd_read_entities(str(state), stages, now, 3600)
            dashboard.sd_read_entities(str(state), stages, now, 3600)
            self.assertEqual(1, len(reads))
            self.entity(state, "drc-1", "posted")
            os.utime(path, (now + 1, now + 1))
            self.assertEqual(
                [("drc-1", "posted")],
                dashboard.sd_read_entities(str(state), stages, now + 2, 3600),
            )
        self.assertEqual(2, len(reads))

    def test_the_entity_dir_is_taken_from_boot_and_must_be_absolute(self) -> None:
        records = [
            {"command": "boot", "definition_dir": "/w", "entity_dir": "relative/state"},
            {"command": "boot", "definition_dir": "/other", "entity_dir": "/other/state"},
            {"command": "boot", "definition_dir": "/w", "entity_dir": "/w/state"},
            {"command": "boot", "definition_dir": "/w", "entity_dir": 17},
        ]

        self.assertEqual("/w/state", dashboard.sd_boot_entity_dir(records, "/w"))
        self.assertEqual("/other/state", dashboard.sd_boot_entity_dir(records, "/other"))
        self.assertEqual("", dashboard.sd_boot_entity_dir(records, "/absent"))

    def test_a_failed_wrap_does_not_leak_the_descriptor(self) -> None:
        """os.fdopen leaves the fd open when it raises, and this runs every
        refresh — a leak here exhausts the descriptor table."""
        root = self.workflow(self.README)
        opened: list[int] = []
        real_open = os.open

        def counting_open(*args: object, **kwargs: object) -> int:
            descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
            opened.append(descriptor)
            return descriptor

        with (
            mock.patch.object(os, "open", counting_open),
            mock.patch.object(os, "fdopen", side_effect=OSError("boom")),
        ):
            self.assertIsNone(dashboard.sd_read_workflow(str(root)))

        self.assertEqual(1, len(opened))
        with self.assertRaises(OSError):
            os.fstat(opened[0])

    def test_no_workflow_no_strip(self) -> None:
        now = time.time()
        self.assertEqual([], dashboard.sd_session_workflows([], [], now, 3600))
        self.assertEqual(
            [],
            dashboard.sd_session_workflows(
                [{"command": "boot", "definition_dir": "/nonexistent/wf"}], [], now, 3600
            ),
        )

    def test_a_workflow_with_no_state_directory_still_costs_no_walk(self) -> None:
        root = self.workflow(self.README)
        boot = [
            {
                "command": "boot",
                "definition_dir": str(root),
                "entity_dir": str(root / ".spacedock-state"),
                "dispatchable": [],
            }
        ]

        self.assertEqual([], dashboard.sd_session_workflows(boot, [], time.time(), 3600))


class CalmModeTest(PageJsHarness):
    """The calm display mode and the switch between it and the regular view.

    Calm mode renders the same ``/api/data`` payload as a dense ledger. These
    execute the page's real JS: every assertion is about what the page does
    with a payload, not about the text of ``PAGE``.
    """

    # Globals the page reads at load (localStorage) or feature-detects
    # (navigator.clipboard), plus a hand-fired setTimeout so the transient
    # "copied" label clears deterministically instead of after a real 1.4s.
    @staticmethod
    def prelude(saved: str | None = None, *, clipboard: str = "none") -> str:
        seed = "{}" if saved is None else json.dumps({"cargento.displayMode": saved})
        clip = {
            "none": "const navigator = {};",
            "ok": (
                "let __wrote = [];\nconst navigator = {clipboard: {writeText(s){"
                " __wrote.push(s); return Promise.resolve(); }}};"
            ),
            "denied": (
                "const navigator = {clipboard: {writeText(){"
                ' return Promise.reject(new Error("denied")); }}};'
            ),
        }[clipboard]
        return f"""
let __store = {seed};
const localStorage = {{
  getItem(k){{ return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; }},
  setItem(k, v){{ __store[k] = String(v); }}
}};
{clip}
let __timers = [];
const setTimeout = fn => {{ __timers.push(fn); return __timers.length; }};
const __tick = () => {{ const t = __timers; __timers = []; t.forEach(f => f()); }};
"""

    # A payload builder shared by the checks below. `mk` fills in every field
    # base_session() ships so a test only states what it is exercising.
    FIXTURE = """
let __focused = null;
// Every [data-calm] control in the rendered markup, as something that answers
// getAttribute() and focus() the way a real element would.
const __controls = () => [...__els.app.innerHTML.matchAll(
    /data-calm="([^"]*)"(?: data-arg="([^"]*)")?/g)].map(m => ({
  getAttribute: a => a === "data-calm" ? m[1]
    : (a === "data-arg" ? (m[2] === undefined ? null : m[2]) : null),
  focus(){ __focused = m[1] + ":" + (m[2] === undefined ? "" : m[2]); }
}));
__els.app = {innerHTML: "", className: "", querySelectorAll: () => __controls()};
let __scrollTop = 0;
let __revealed = 0;
// Selector-aware on purpose: a stub that answers every selector makes
// "the cursor was scrolled into view" pass even when the page asked for the
// wrong element, or for nothing at all.
__els["cm-body"] = {
  get scrollTop(){ return __scrollTop; }, set scrollTop(v){ __scrollTop = v; },
  querySelector(sel){
    if(sel !== ".cm-row.focus") return null;
    if(!__els.app.innerHTML.includes('class="cm-row focus')) return null;
    return {scrollIntoView(){ __revealed++; }};
  }
};
const mk = o => Object.assign({
  harness: "claude", session: "1234abcd", sid: "1234abcd", project: "repo/proj",
  title: null, last_prompt: "", state: "idle", state_detail: "awaiting your message",
  active: false, last_activity: 99000, rate_per_min: 0, total: 0, done: 0, open: 0,
  progress_pct: 0, eta_h: null, turn: null, subagents: [], tasks: [], spacedock: null
}, o);
const payload = sessions => ({
  generated: 100000, window_hours: 24, show_all: false, native_notify: "osascript",
  harnesses: [{key: "claude", label: "Claude Code", discovered: true, error: null},
              {key: "codex", label: "Codex", discovered: false, error: null}],
  summary: {needs_input: 1, working: 1, rate_per_min: 1234, active_sessions: 2,
            open_tasks: 1, progress_pct: 50, total_tasks: 2, total_done: 1},
  sessions
});
const blocked = mk({sid: "aaa1", session: "aaa1", title: "Approve deploy?",
  state: "needs_input", active: true, last_activity: 99700, blocked_since: 99700,
  state_detail: "open question (AskUserQuestion), waiting 5m"});
const busy = mk({sid: "bbb2", session: "bbb2", harness: "codex", project: "repo/other",
  title: "Migrate warehouse sync", state: "working", active: true,
  state_detail: "running Bash", last_activity: 99990, rate_per_min: 2010,
  turn: {elapsed_h: "20m", eta_h: "39m", pct: 34, long: true},
  subagents: ["Final whole-branch review"], last_prompt: "migrate the sync",
  tasks: [{status: "completed", subject: "Map every call site", activeForm: null},
          {status: "in_progress", subject: "Convert chain", activeForm: "Converting chain"},
          {status: "pending", subject: "Re-run suite", activeForm: null}]});
const quiet = mk({sid: "ccc3", session: "ccc3", title: "Old thing", last_activity: 90000});
const board = () => payload([blocked, busy, quiet]);
const rows = () => (__els.app.innerHTML.match(/class="cm-row/g) || []).length;
// A row is identified by (harness, sid) — the same pair sessKey() builds.
const K = (harness, sid) => harness + ":" + sid;
"""

    def run_calm(self, checks: str, *, saved: str = "calm", clipboard: str = "none") -> Any:
        return self._run_page_js(
            self.FIXTURE + checks, prelude=self.prelude(saved, clipboard=clipboard)
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_display_switch_persists_and_is_bound_to_c_in_both_modes(self) -> None:
        checks = """
const out = {};
out.startedCalm = displayMode;                    // seeded from localStorage
render(board());
out.calmClass = __els.app.className;
out.calmFrame = __els.app.innerHTML.includes("cm-frame");
out.switchShown = __els.app.innerHTML.includes('data-calm="mode" data-arg="calm"' +
  ' aria-pressed="true"');

// `c` leaves calm, and the switch is still there to come back with.
__fire("keydown", {key: "c", target: {}, preventDefault(){}});
out.afterKey = displayMode;
out.stored = __store["cargento.displayMode"];
out.regularClass = __els.app.className;
out.regularKeepsSwitch = __els.app.innerHTML.includes('class="modebar"');
out.regularKeepsTiles = __els.app.innerHTML.includes('class="tile"');
out.noFrameInRegular = !__els.app.innerHTML.includes("cm-frame");

// ...and back again, this time by clicking the segment.
calmAction("mode", "calm");
out.clickedBack = displayMode;
out.storedBack = __store["cargento.displayMode"];

// A value neither mode is ignored rather than blanking the page.
calmAction("mode", "sideways");
out.rejectsJunk = displayMode;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual("calm", out["startedCalm"], "saved mode not honoured on load")
        self.assertEqual("wrap calm", out["calmClass"])
        self.assertTrue(out["calmFrame"])
        self.assertTrue(out["switchShown"])
        self.assertEqual("regular", out["afterKey"], "`c` did not leave calm mode")
        self.assertEqual("regular", out["stored"], "the switch was not persisted")
        self.assertEqual("wrap", out["regularClass"])
        self.assertTrue(out["regularKeepsSwitch"], "no way back to calm from regular")
        self.assertTrue(out["regularKeepsTiles"], "regular mode lost its hero tiles")
        self.assertTrue(out["noFrameInRegular"])
        self.assertEqual("calm", out["clickedBack"])
        self.assertEqual("calm", out["storedBack"])
        self.assertEqual("calm", out["rejectsJunk"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_page_still_loads_when_storage_is_unavailable(self) -> None:
        # Private browsing and sandboxed contexts throw on localStorage access.
        checks = """
__els.app = {innerHTML: "", className: ""};
const d = {generated: 1000, window_hours: 24, show_all: false, native_notify: "",
  harnesses: [], sessions: [],
  summary: {needs_input: 0, working: 0, rate_per_min: 0, active_sessions: 0,
            open_tasks: 0, progress_pct: 0, total_tasks: 0, total_done: 0}};
render(d);
setDisplayMode("calm");
console.log(JSON.stringify({
  mode: displayMode, rendered: __els.app.innerHTML.includes("cm-frame")}));
"""
        # No prelude at all: neither localStorage nor navigator exists.
        out = self._run_page_js(checks)
        self.assertEqual("calm", out["mode"], "storage failure blocked the switch")
        self.assertTrue(out["rendered"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_ledger_lists_every_session_exactly_once(self) -> None:
        # A ledger that silently drops a session is worse than no ledger.
        checks = """
const out = {};
render(board());
const h = __els.app.innerHTML;
out.rows = rows();
out.perSession = [K("claude", "aaa1"), K("codex", "bbb2"), K("claude", "ccc3")]
  .map(k => (h.match(new RegExp('data-arg="' + k + '"', "g")) || []).length);
out.note = h.includes("showing all 3");
out.footer = h.includes("3 sessions · 1 harnesses · 1,234 tok/min");
out.legend = [h.includes("1 needs you"), h.includes("1 working"), h.includes("1 idle")];
// Column values come straight from the payload.
out.doing = h.includes("open question (AskUserQuestion), waiting 5m");
// Only the project may be truncated; the session id identifies the row.
out.where = h.includes('class="cm-proj">repo/other</span><span class="cm-sess">· bbb2<');
out.metrics = ["5m wait", "2,010 /m", "2h 46m idle"].map(m => h.includes(m));
// Signal bar only for a working session with a turn percentage.
out.bars = (h.match(/class="cm-track"/g) || []).length;
out.barWidth = h.includes("width:34%");
// An unrecognised state is still a row, in the idle bucket.
render(payload([mk({sid: "z", session: "z", state: "banana"})]));
out.unknownState = rows();
out.unknownIdle = __els.app.innerHTML.includes("1 idle");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(3, out["rows"])
        # Each row carries its sid twice: the row itself and its `copy id` button.
        self.assertEqual([2, 2, 2], out["perSession"])
        self.assertTrue(out["note"])
        self.assertTrue(out["footer"], "footer counts disagree with the payload")
        self.assertEqual([True, True, True], out["legend"])
        self.assertTrue(out["doing"])
        self.assertTrue(out["where"])
        self.assertEqual([True, True, True], out["metrics"])
        self.assertEqual(1, out["bars"], "only a working turn should draw a signal bar")
        self.assertTrue(out["barWidth"])
        self.assertEqual(1, out["unknownState"], "a state the page does not know dropped a row")
        self.assertTrue(out["unknownIdle"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_flags_use_only_signals_the_payload_carries(self) -> None:
        # The design fixture also flagged "stalled" and "failed". The server has
        # no detector for either, so calm mode must not invent them.
        checks = """
const out = {};
render(board());
calmAction("open", "claude:aaa1");
calmAction("open", "codex:bbb2");
calmAction("open", "claude:ccc3");
const each = k => { calmAction("open", k); const h = __els.app.innerHTML;
  calmAction("open", k); return h; };
const hb = each(K("claude", "aaa1")), hw = each(K("codex", "bbb2")),
      hq = each(K("claude", "ccc3"));
out.blockedFlag = hb.includes(">your call<");
out.blockedWhy = hb.includes("Blocked on you for 5m");
out.longFlag = hw.includes(">long turn<");
out.longWhy = hw.includes("This request is running long (or estimated to).");
out.staleFlag = hq.includes(">stale<");
out.staleWhy = hq.includes("No activity for 2h 46m");
out.noInvented = !/&gt;stalled&lt;|>stalled<|>failed</.test(hb + hw + hq);
// A working session inside the long-turn threshold carries no flag.
render(payload([mk({sid: "s", session: "s", state: "working", active: true,
  last_activity: 99999, turn: {elapsed_h: "2m", eta_h: "3m", pct: 40, long: false}})]));
out.shortTurnUnflagged = !__els.app.innerHTML.includes('class="cm-flag"');
out.flagChipZero = __els.app.innerHTML.includes("◆ 0 flagged");
// An idle session inside the stale threshold carries no flag either.
render(payload([mk({sid: "t", session: "t", last_activity: 99000})]));
out.freshIdleUnflagged = !__els.app.innerHTML.includes('class="cm-flag"');
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["blockedFlag"])
        self.assertTrue(out["blockedWhy"])
        self.assertTrue(out["longFlag"])
        self.assertTrue(out["longWhy"], "calm mode reworded the long-turn signal")
        self.assertTrue(out["staleFlag"])
        self.assertTrue(out["staleWhy"])
        self.assertTrue(out["noInvented"], "flagged a signal the payload cannot support")
        self.assertTrue(out["shortTurnUnflagged"])
        self.assertTrue(out["flagChipZero"])
        self.assertTrue(out["freshIdleUnflagged"])

    def test_the_long_turn_wording_has_exactly_one_source(self) -> None:
        # The ⚠️ tooltip and the calm flag explanation are the same sentence;
        # two copies is how they drift apart.
        self.assertIn("const LONG_TURN_NOTE =", dashboard.PAGE)
        self.assertEqual(
            1,
            dashboard.PAGE.count("This request is running long (or estimated to)."),
            "the long-turn sentence is duplicated instead of shared",
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_filters_and_orderings_agree_with_the_counts_they_advertise(self) -> None:
        checks = """
const out = {};
render(board());
// Attention order puts the blocker first, then the warning, then the quiet row.
const order = h => [...h.matchAll(/data-arg="[a-z]+:(aaa1|bbb2|ccc3)" role="button"/g)]
  .map(m => m[1]);
out.attention = order(__els.app.innerHTML);
calmAction("sort", "recent");
out.recent = order(__els.app.innerHTML);
out.recentPressed = __els.app.innerHTML.includes('data-arg="recent" aria-pressed="true"');
calmAction("sort", "repo");
out.repoDividers = (__els.app.innerHTML.match(/class="cm-div"/g) || []).length;
out.repoLabels = ["repo/other", "repo/proj"].map(p =>
  __els.app.innerHTML.indexOf('cm-div-k">' + p));
out.repoRows = rows();
calmAction("sort", "attention");

// A legend chip filters to its own bucket and reports the narrowing.
calmAction("open", "codex:bbb2");
calmCursorKey = "codex:bbb2";
calmAction("state", "needs");
out.filterResetsRow = [calmOpenKey, calmCursorKey];
out.needsOnly = [rows(), __els.app.innerHTML.includes("showing 1 of 3")];
out.clearOffered = __els.app.innerHTML.includes('data-calm="clear"');
calmAction("state", "needs");
out.chipIsAToggle = [calmStateOnly, rows()];

// The flagged chip narrows to flagged rows; every board row is flagged here.
calmAction("open", "codex:bbb2");
calmAction("flag", null);
out.flagFilterResetsRow = [calmOpenKey, calmCursorKey];
out.flagged = [calmFlagOnly, rows()];
calmAction("clear", null);
out.cleared = [calmFlagOnly, calmStateOnly, rows()];

// A filter that matches nothing offers its own way out.
render(payload([busy]));
calmAction("state", "idle");
const empty = __els.app.innerHTML;
out.emptyState = empty.includes("Nothing matches this filter")
  && empty.includes("Show all 1");
out.emptyHasNoRows = rows();
calmAction("clear", null);
out.recovered = rows();

// No sessions at all is a different message, with the window and the escape.
render(payload([]));
out.noData = __els.app.innerHTML.includes("No session activity in the last 24h")
  && __els.app.innerHTML.includes('href="?all=1"');
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(["aaa1", "bbb2", "ccc3"], out["attention"])
        self.assertEqual(["bbb2", "aaa1", "ccc3"], out["recent"], "recent order is not by age")
        self.assertTrue(out["recentPressed"])
        self.assertEqual(2, out["repoDividers"])
        self.assertLess(out["repoLabels"][0], out["repoLabels"][1], "repo groups not sorted")
        self.assertEqual(3, out["repoRows"], "grouping lost a row")
        self.assertEqual([None, None], out["filterResetsRow"], "a filter left a row expanded")
        self.assertEqual([None, None], out["flagFilterResetsRow"])
        self.assertEqual([1, True], out["needsOnly"])
        self.assertTrue(out["clearOffered"])
        self.assertEqual([None, 3], out["chipIsAToggle"])
        self.assertEqual([True, 3], out["flagged"])
        self.assertEqual([False, None, 3], out["cleared"])
        self.assertTrue(out["emptyState"])
        self.assertEqual(0, out["emptyHasNoRows"])
        self.assertEqual(1, out["recovered"])
        self.assertTrue(out["noData"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_row_order_does_not_churn_between_polls(self) -> None:
        # A row that swaps places under the cursor is worse than a row in the
        # wrong place. Every ordering has to be a function of things that do not
        # change while the reader is reading: collect() makes the same call.
        checks = """
const out = {};
// Eight sessions with ages spread across minute boundaries, plus three that
// are actively generating (their last_activity advances with every poll).
const many = [];
for(let i = 0; i < 8; i++){
  many.push(mk({sid: "idle-" + i, session: "idle-" + i,
    project: "repo/p" + (i % 3), last_activity: 100000 - 59 - i * 61}));
}
for(let i = 0; i < 3; i++){
  many.push(mk({sid: "work-" + i, session: "work-" + i, state: "working",
    active: true, project: "repo/p" + (i % 3), last_activity: 99990 + i,
    rate_per_min: 100 * i}));
}
// What a real poll looks like: a generating session wrote at some arbitrary
// moment since the last poll, so its age jitters; and collect() re-sorts the
// array server-side, so the client may not lean on the payload's own order.
const LAG = [[1, 4, 2], [3, 1, 4], [0, 3, 1], [4, 2, 3], [2, 0, 4], [1, 3, 0], [3, 4, 1]];
const at = (t, k) => {
  const lag = LAG[k % LAG.length];
  const sessions = many.map(s => s.state === "working"
    ? {...s, last_activity: t - lag[Number(s.sid.slice(-1))]} : s);
  // Reverse on alternate polls: payload order must not decide row order.
  return {...payload(k % 2 ? sessions.slice().reverse() : sessions), generated: t};
};
const snap = () => [...__els.app.innerHTML.matchAll(
    /data-arg="[a-z]+:([a-z]+-\\d)" role/g)].map(m => m[1]);

for(const sort of ["attention", "recent", "repo"]){
  calmAction("sort", sort);
  render(at(100000, 0));
  const first = snap();
  // Six more polls, five seconds apart: enough for several rows to tick over a
  // whole minute and for every working row to have written again.
  const same = [];
  for(let k = 1; k <= 6; k++){
    render(at(100000 + k * 5, k));
    same.push(snap().join() === first.join());
  }
  out[sort] = {rows: first.length, stable: same.every(Boolean), order: first};
}
// A session that genuinely goes quiet is allowed — and expected — to move.
calmAction("sort", "attention");
render(at(100000, 0));
const before = snap();
const next = at(100010, 2);
render({...next, sessions: next.sessions.map(s =>
  s.sid === "work-1" ? {...s, state: "idle", active: false, last_activity: 90000} : s)});
out.realChangeMoves = snap().join() !== before.join();
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        for sort in ("attention", "recent", "repo"):
            with self.subTest(sort=sort):
                self.assertEqual(11, out[sort]["rows"], "a row went missing")
                self.assertTrue(
                    out[sort]["stable"],
                    f"{sort} order churned between polls: {out[sort]['order']}",
                )
        # Working rows sort ahead of idle ones under both attention and recent.
        self.assertEqual(
            ["work-0", "work-1", "work-2"], out["attention"]["order"][:3], "working rows not first"
        )
        self.assertEqual(["work-0", "work-1", "work-2"], out["recent"]["order"][:3])
        # Idle rows stay in most-recent-first order.
        self.assertEqual(["idle-0", "idle-1", "idle-2", "idle-3"], out["attention"]["order"][3:7])
        self.assertTrue(out["realChangeMoves"], "a session that changed state did not move")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_expanded_row_shows_what_the_regular_card_shows(self) -> None:
        checks = """
const out = {};
const sd = {role: "first-officer", workflows: [{workflow: "wf", stages: ["a", "b"],
  entities: [{slug: "ent", stage: "b", live: true, cycle: "c1"}]}]};
render(payload([Object.assign({}, busy, {spacedock: sd})]));
out.collapsedFirst = !__els.app.innerHTML.includes("cm-exp");
calmAction("open", "codex:bbb2");
const h = __els.app.innerHTML;
out.expanded = h.includes("cm-exp");
out.caret = h.includes('class="cm-caret">–<');
out.ariaExpanded = h.includes('aria-expanded="true"');
out.turn = h.includes("20m elapsed · ~39m left (est)") && h.includes("34%");
out.subagent = h.includes("Final whole-branch review");
out.prompt = h.includes("migrate the sync");
// Tasks: in-progress first and shown by its activeForm, completed last.
out.taskNote = h.includes("tasks · 1 of 3 done");
out.taskOrder = ["Converting chain…", "Re-run suite", "Map every call site"]
  .map(t => h.indexOf(t));
out.spacedock = h.includes("spacedock wf") && h.includes("first officer");
out.meta = h.includes("session bbb2") && h.includes("Claude");
// Collapsing again, and only one row open at a time.
calmAction("open", "codex:bbb2");
out.collapsed = !__els.app.innerHTML.includes("cm-exp");
render(board());
calmAction("open", "claude:aaa1");
calmAction("open", "codex:bbb2");
out.onlyOneOpen = (__els.app.innerHTML.match(/class="cm-exp"/g) || []).length;
// A turn with no percentage draws no bar and says so in words.
render(payload([mk({sid: "n", session: "n", state: "working", active: true,
  last_activity: 99999, turn: {elapsed_h: "9m", eta_h: null, pct: null, long: false}})]));
calmAction("open", "claude:n");
out.noPct = !__els.app.innerHTML.includes("cm-turn-pct")
  && __els.app.innerHTML.includes("9m elapsed · running longer than recent turns");
// A session with nothing extra expands to just its identity line.
render(payload([quiet]));
calmAction("open", "claude:ccc3");
const bare = __els.app.innerHTML;
out.bare = [bare.includes("cm-exp"), bare.includes("cm-tasks"),
            bare.includes("cm-subs"), bare.includes("session ccc3")];
// The title doubles as the prompt here, so it is not quoted twice.
out.noEchoedPrompt = !bare.includes("cm-quote");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["collapsedFirst"], "rows should start collapsed")
        self.assertTrue(out["expanded"])
        self.assertTrue(out["caret"])
        self.assertTrue(out["ariaExpanded"])
        self.assertTrue(out["turn"])
        self.assertTrue(out["subagent"])
        self.assertTrue(out["prompt"])
        self.assertTrue(out["taskNote"])
        self.assertEqual(sorted(out["taskOrder"]), out["taskOrder"], "task order is wrong")
        self.assertNotIn(-1, out["taskOrder"])
        self.assertTrue(out["spacedock"], "the Spacedock strip is missing from calm mode")
        self.assertTrue(out["meta"])
        self.assertTrue(out["collapsed"])
        self.assertEqual(1, out["onlyOneOpen"])
        self.assertTrue(out["noPct"])
        self.assertEqual([True, False, False, True], out["bare"])
        self.assertTrue(out["noEchoedPrompt"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_hostile_session_text_cannot_reach_the_dom_as_markup(self) -> None:
        # Titles, prompts, task subjects and subagent names all come from files
        # a project can write. Calm mode builds HTML strings, so every one of
        # them has to go through esc().
        checks = """
const bad = '<img src=x onerror=alert(1)>"><b>';
render(payload([mk({sid: bad, session: bad, project: bad, title: bad,
  state: "working", active: true, state_detail: bad, last_prompt: "p " + bad,
  last_activity: 99999, subagents: [bad], harness: bad,
  turn: {elapsed_h: bad, eta_h: bad, pct: 50, long: true},
  tasks: [{status: "pending", subject: bad, activeForm: bad}]})]));
calmAction("open", "claude:" + bad);
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  noTag: !h.includes("<img") && !h.includes("<b>"),
  escaped: h.includes("&lt;img src=x onerror=alert(1)&gt;"),
  attrsClosed: !h.includes('title=""><b>'),
  rows: rows()
}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["noTag"], "hostile session text reached the DOM as markup")
        self.assertTrue(out["escaped"])
        self.assertTrue(out["attrsClosed"], "hostile text broke out of an attribute")
        self.assertEqual(1, out["rows"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_keyboard_drives_the_ledger(self) -> None:
        checks = """
const out = {};
let __prevented = 0;
const key = (k, target) => { const before = __prevented;
  __fire("keydown", {key: k, target: target || {}, preventDefault(){ __prevented++; }});
  return __prevented - before; };
render(board());
out.cursorStartsAtTop = __els.app.innerHTML.includes('class="cm-row focus"');
key("j"); out.down1 = calmCursorKey;
key("j"); out.down2 = calmCursorKey;
key("j"); out.clampsAtBottom = calmCursorKey;
key("k"); out.up = calmCursorKey;
key("ArrowUp"); out.arrowUp = calmCursorKey;
key("ArrowUp"); out.clampsAtTop = calmCursorKey;
key("Enter"); out.enterOpens = calmOpenKey;
key(" "); out.spaceCloses = calmOpenKey;
key("f"); out.fFilters = calmFlagOnly;
key("Escape"); out.escapeClears = [calmFlagOnly, calmStateOnly, calmOpenKey];
// Moving the cursor brings it into view; a plain poll does not yank the list.
__revealed = 0;
key("j"); out.revealedOnMove = __revealed;
render(lastData); out.revealedOnPoll = __revealed;
// Keys the ledger does not own are left alone.
key("j", {tagName: "TEXTAREA"}); out.textareaSafe = calmCursorKey;
key("q"); out.unknownKeySafe = calmCursorKey;
// The browser scrolls on Space and the arrows unless the page says otherwise.
out.prevented = [key(" "), key("ArrowDown"), key("ArrowUp"), key("q")];
key(" ");  // leave nothing expanded for the checks below
// A modifier means the chord belongs to the browser or the OS, not to us.
const mode0 = displayMode;
out.modifiersIgnored = ["metaKey", "ctrlKey", "altKey"].map(mod => {
  __fire("keydown", {key: "c", [mod]: true, target: {}, preventDefault(){}});
  return displayMode === mode0;   // checked per modifier: two toggles cancel out
});
// Enter belongs to whatever focusable thing has focus, such as the empty
// state's "Show all sessions" link.
render(payload([]));
const link = {tagName: "A", closest: () => ({})};
out.linkKeepsEnter = key("Enter", link) === 0;
render(board());
// Nothing to move to is not an error, and nothing opens.
render(payload([]));
key("j"); key("Enter");
out.emptySafe = [calmOpenKey, __els.app.innerHTML.includes("cm-empty")];
// Ledger keys stay in the ledger: `j` in regular mode must not move a cursor.
setDisplayMode("regular");
render(board());
calmCursorKey = null;
key("j"); out.regularIgnoresJ = calmCursorKey;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["cursorStartsAtTop"], "no keyboard cursor on first paint")
        self.assertEqual("codex:bbb2", out["down1"])
        self.assertEqual("claude:ccc3", out["down2"])
        self.assertEqual("claude:ccc3", out["clampsAtBottom"], "cursor ran off the end")
        self.assertEqual("codex:bbb2", out["up"])
        self.assertEqual("claude:aaa1", out["arrowUp"])
        self.assertEqual("claude:aaa1", out["clampsAtTop"], "cursor ran off the start")
        self.assertEqual("claude:aaa1", out["enterOpens"])
        self.assertIsNone(out["spaceCloses"])
        self.assertTrue(out["fFilters"])
        self.assertEqual([False, None, None], out["escapeClears"])
        self.assertEqual(1, out["revealedOnMove"])
        self.assertEqual(1, out["revealedOnPoll"], "a poll scrolled the list on its own")
        self.assertEqual("codex:bbb2", out["textareaSafe"], "stole a key from a text field")
        self.assertEqual("codex:bbb2", out["unknownKeySafe"])
        self.assertEqual(
            [1, 1, 1, 0], out["prevented"], "the browser would scroll as well as the ledger"
        )
        self.assertEqual(
            [True, True, True],
            out["modifiersIgnored"],
            "a modifier chord (cmd/ctrl/alt + c) toggled the display mode",
        )
        self.assertTrue(out["linkKeepsEnter"], "swallowed Enter from a focused link")
        self.assertEqual([None, True], out["emptySafe"])
        self.assertIsNone(out["regularIgnoresJ"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_five_second_poll_does_not_disturb_the_view(self) -> None:
        # render() replaces #app wholesale. Everything the reader set has to
        # survive that: the open row, the cursor, the filters, the scroll.
        checks = """
const out = {};
render(board());
calmAction("sort", "recent");
calmAction("state", "work");
calmAction("open", "codex:bbb2");
calmCursorKey = "codex:bbb2";
__scrollTop = 137;
render(board());
const h = __els.app.innerHTML;
out.scroll = __scrollTop;
out.openKept = h.includes("cm-exp");
out.cursorKept = h.includes('class="cm-row focus open"');
out.sortKept = h.includes('data-arg="recent" aria-pressed="true"');
out.filterKept = calmStateOnly;
// Re-filtering, though, is a new list: keeping the old offset would drop the
// reader into the middle of rows they have not seen.
__scrollTop = 137;
calmAction("clear", null);
out.scrollResetOnFilter = __scrollTop;
__scrollTop = 137;
calmAction("sort", "repo");
out.scrollResetOnSort = __scrollTop;
// A session that disappears must not leave the cursor stranded.
calmAction("sort", "attention");
calmCursorKey = "nope:gone";
render(board());
out.strandedCursor = (__els.app.innerHTML.match(/class="cm-row focus/g) || []).length;
// The stall indicator the refresh loop writes into exists in calm mode too.
out.liveIds = __els.app.innerHTML.includes('id="live-dot"')
  && __els.app.innerHTML.includes('id="live-status"');
out.notifyControlPlaced = calmLedger(Object.assign(board(), {native_notify: ""}))
  .includes("Enable notifications");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(137, out["scroll"], "the poll reset the ledger scroll")
        self.assertTrue(out["openKept"], "the poll collapsed the open row")
        self.assertTrue(out["cursorKept"], "the poll lost the keyboard cursor")
        self.assertTrue(out["sortKept"])
        self.assertEqual("work", out["filterKept"])
        self.assertEqual(0, out["scrollResetOnFilter"], "a re-filter kept a stale scroll offset")
        self.assertEqual(0, out["scrollResetOnSort"], "a re-sort kept a stale scroll offset")
        self.assertEqual(1, out["strandedCursor"], "cursor vanished with its session")
        self.assertTrue(out["liveIds"], "calm mode cannot show a stalled refresh")
        self.assertTrue(out["notifyControlPlaced"], "no way to grant notifications in calm mode")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_two_harnesses_sharing_a_session_id_stay_two_rows(self) -> None:
        # dedupe_sessions keys on (harness, sid), so the same sid CAN reach the
        # page twice on different harnesses. The rest of the page already
        # treats that pair as identity (sessKey, the notification map); keying
        # the ledger on a bare sid would expand both rows at once and leave the
        # cursor unable to tell them apart.
        checks = """
const out = {};
const clash = "019fa752";
render(payload([
  mk({sid: clash, session: clash, harness: "claude", project: "repo/a", title: "Claude one"}),
  mk({sid: clash, session: clash, harness: "codex", project: "repo/b", title: "Codex one"})]));
out.bothRows = rows();
calmAction("open", K("claude", clash));
const h = __els.app.innerHTML;
out.onlyOneExpanded = (h.match(/class="cm-exp"/g) || []).length;
out.expandedTheRightOne = h.indexOf("Claude one") < h.indexOf("cm-exp")
  && h.indexOf("cm-exp") < h.indexOf("Codex one");
out.cursorIsScoped = calmCursorKey;
// j must step from one to the other, not sit still.
__fire("keydown", {key: "j", target: {}, preventDefault(){}});
out.moved = calmCursorKey;
// And the clipboard still gets the bare session id, not the row key.
calmAction("copy", K("codex", clash));
await __settle();
out.copied = __wrote;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks, clipboard="ok")
        self.assertEqual(2, out["bothRows"], "two harnesses collapsed into one row")
        self.assertEqual(1, out["onlyOneExpanded"], "one click expanded both rows")
        self.assertTrue(out["expandedTheRightOne"])
        self.assertEqual("claude:019fa752", out["cursorIsScoped"])
        self.assertEqual("codex:019fa752", out["moved"], "the cursor could not tell them apart")
        self.assertEqual(["019fa752"], out["copied"], "copied the row key instead of the id")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_unexpected_status_or_harness_cannot_render_undefined(self) -> None:
        # Every plain object inherits truthy `constructor` and `toString` from
        # Object.prototype, so a lookup like TABLE[x.status] || FALLBACK skips
        # its own fallback for those keys and paints `undefined` as both the
        # glyph and the CSS colour.
        checks = """
render(payload([mk({sid: "p", session: "p", harness: "constructor",
  state: "working", active: true, last_activity: 99999, rate_per_min: 5,
  tasks: [{status: "constructor", subject: "poisoned", activeForm: null},
          {status: "toString", subject: "also poisoned", activeForm: null},
          {status: "in_progress", subject: "real one", activeForm: "Working"}]})]));
calmAction("open", K("constructor", "p"));
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  noUndefined: !h.includes("undefined"),
  rows: rows(),
  tasksRendered: (h.match(/class="cm-task"/g) || []).length,
  realTaskFirst: h.indexOf("Working…") < h.indexOf("poisoned")}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["noUndefined"], "an inherited key rendered as undefined")
        self.assertEqual(1, out["rows"])
        self.assertEqual(3, out["tasksRendered"], "a poisoned status dropped a task row")
        self.assertTrue(out["realTaskFirst"], "inherited keys broke the task ordering")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_keyboard_focus_survives_the_poll(self) -> None:
        # The ledger's controls are real focusable buttons, and render() throws
        # the focused one away every five seconds. Without this, tabbing to a
        # control and pressing it is a race against the refresh.
        checks = """
const out = {};
render(board());
const find = act => __controls().find(c => c.getAttribute("data-calm") === act);
// Focus a control that carries an argument, and one that does not.
document.activeElement = __controls().find(c =>
  c.getAttribute("data-calm") === "copy" &&
  c.getAttribute("data-arg") === K("claude", "aaa1"));
__focused = null;
render(board());
out.withArg = __focused;
document.activeElement = find("flag");
__focused = null;
render(board());
out.withoutArg = __focused;
// A control that is gone after the payload changed must not steal focus.
document.activeElement = __controls().find(c =>
  c.getAttribute("data-arg") === K("claude", "ccc3"));
__focused = null;
render(payload([blocked]));
out.departed = __focused;
// Focus outside the ledger is left alone.
document.activeElement = {getAttribute: () => null};
__focused = null;
render(board());
out.untracked = __focused;
document.activeElement = null;
__focused = null;
render(board());
out.noFocus = __focused;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual("copy:claude:aaa1", out["withArg"], "focus was lost across the poll")
        self.assertEqual("flag:", out["withoutArg"])
        self.assertIsNone(out["departed"], "focus jumped to an unrelated control")
        self.assertIsNone(out["untracked"], "stole focus from outside the ledger")
        self.assertIsNone(out["noFocus"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_harness_that_reports_no_rate_does_not_read_as_zero(self) -> None:
        # Copilot, OpenCode, Cursor and Droid never populate rate_per_min, and
        # the regular view omits the meter rather than printing a zero. Calm
        # mode printing "0 /m" would make the two modes disagree.
        checks = """
render(payload([
  mk({sid: "cp", session: "cp", harness: "copilot", state: "working", active: true,
      last_activity: 99999, rate_per_min: 0}),
  mk({sid: "cl", session: "cl", state: "working", active: true,
      last_activity: 99999, rate_per_min: 1200})]));
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  zero: h.includes(">0 /m<"), dash: h.includes(">—<"), real: h.includes(">1,200 /m<")}));
"""
        out = self.run_calm(checks)
        self.assertFalse(out["zero"], 'printed a fabricated "0 /m" for a rate-less harness')
        self.assertTrue(out["dash"])
        self.assertTrue(out["real"], "lost the rate for a harness that does report one")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_copy_id_reports_what_the_clipboard_actually_did(self) -> None:
        checks = """
const out = {};
render(board());
calmAction("copy", "claude:aaa1");
await __settle();
out.wrote = __wrote;
out.label = __els.app.innerHTML.includes(">copied<");
out.otherRowsUnchanged = (__els.app.innerHTML.match(/>id</g) || []).length;
__tick();
out.reverts = !__els.app.innerHTML.includes(">copied<");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks, clipboard="ok")
        self.assertEqual(["aaa1"], out["wrote"], "copy id wrote the wrong value")
        self.assertTrue(out["label"], "no feedback that the id was copied")
        self.assertEqual(2, out["otherRowsUnchanged"])
        self.assertTrue(out["reverts"], "the copied label never clears")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_copy_id_never_claims_a_copy_the_browser_refused(self) -> None:
        # An unfocused document or a non-secure context rejects the write. A
        # confident "copied" there costs the reader the id they wanted.
        checks = """
render(board());
calmAction("copy", "claude:aaa1");
await __settle(); await __settle();
const h = __els.app.innerHTML;
console.log(JSON.stringify({lied: h.includes(">copied<"), told: h.includes(">blocked<")}));
"""
        denied = self.run_calm(checks, clipboard="denied")
        self.assertFalse(denied["lied"], "claimed a copy the clipboard rejected")
        self.assertTrue(denied["told"])
        # And with no Clipboard API at all.
        absent = self.run_calm(checks)
        self.assertFalse(absent["lied"])
        self.assertTrue(absent["told"])

    def test_every_css_variable_the_page_uses_is_declared(self) -> None:
        # A `var(--typo)` renders as nothing at all and no linter here sees it.
        style = re.search(r"<style>(.*?)</style>", dashboard.PAGE, re.DOTALL)
        assert style is not None
        declared = set(re.findall(r"(--[\w-]+)\s*:", style.group(1)))
        used = set(re.findall(r"var\((--[\w-]+)", dashboard.PAGE))
        self.assertEqual(set(), used - declared, "page uses CSS variables nothing declares")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_column_headers_share_the_scrollers_width(self) -> None:
        # Headers and rows lay out on the same grid. As a SIBLING of the
        # scrolling body the header keeps the full frame width while the rows
        # lose the scrollbar's, and the whole delta lands in the one flexible
        # track, so every label from `where` rightward sits off its data. Only
        # invisible where scrollbars are overlays, which is to say only on the
        # machine this was built on.
        checks = """
render(board());
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  nested: h.includes('<div class="cm-body" id="cm-body"><div class="cm-head">'),
  headings: h.includes("<span>where</span>")}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["nested"], "the column headers are outside the scroll container")
        self.assertTrue(out["headings"])
        self.assertIn(".cm-head{position:sticky;top:0;", dashboard.PAGE)

    def test_a_focused_quick_action_can_actually_be_seen(self) -> None:
        # The row's quick action lives in a container held at opacity:0 until
        # hover. Ancestor opacity composites the whole subtree as a group, so a
        # focused child cannot make itself visible — the row has to. Without
        # this the ledger has one invisible tab stop per row.
        self.assertIn(".cm-row:focus-within .cm-q{opacity:1}", dashboard.PAGE)

    def test_no_control_drops_its_focus_ring_without_replacing_it(self) -> None:
        style = re.search(r"<style>(.*?)</style>", dashboard.PAGE, re.DOTALL)
        assert style is not None
        rules = re.findall(r"\n\s*([^\n{]*:focus-visible[^\n{]*)\{([^}]*)\}", style.group(1))
        self.assertGreater(len(rules), 4, "focus-visible rules disappeared; is the regex stale?")
        for selector, body in rules:
            with self.subTest(selector=selector.strip()):
                if "outline:none" in body:
                    self.assertIn(
                        "box-shadow",
                        body,
                        "removes the browser focus ring and puts nothing in its place",
                    )

    def test_the_calm_palette_has_a_dark_counterpart(self) -> None:
        # Calm mode adds surfaces and a second flag tone. Declaring them only
        # in the light block leaves a light-on-light ledger after dark.
        dark = re.search(
            r"@media \(prefers-color-scheme:dark\)\{(.*?)\n  \}", dashboard.PAGE, re.DOTALL
        )
        assert dark is not None
        for name in ("--sunk", "--line2", "--accent-ink", "--warn", "--warnink"):
            with self.subTest(token=name):
                self.assertIn(name, dark.group(1))


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
