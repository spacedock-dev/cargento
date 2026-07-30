from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import records
from cargento_runtime import sessions as runtime_sessions

from .fixtures import (
    protobuf_bytes_field,
    protobuf_int_field,
    write_antigravity_metadata,
)
from .support import LegacyDashboardTestCase, dashboard, make_config, make_runtime


class GeminiAntigravityCollectorTest(LegacyDashboardTestCase):
    def test_record_fingerprint_is_stable_and_bounded(self) -> None:
        self.assertEqual(
            records.record_fingerprint({"a": 1, "b": 2}),
            records.record_fingerprint({"b": 2, "a": 1}),
        )
        self.assertEqual(16, len(records.record_fingerprint({"payload": "x" * 10_000})))

    def test_gemini_snapshot_expansion_keeps_only_records(self) -> None:
        first = {"type": "user", "content": "one"}
        second = {"type": "gemini", "content": "two"}
        snapshot = {"$set": {"messages": [first, "bad", second]}}

        self.assertEqual((first, second), records.gemini_records(snapshot))
        self.assertEqual((first,), records.gemini_records(first))

    def test_incremental_snapshot_returns_only_appended_records(self) -> None:
        first = {"type": "user", "content": "one"}
        second = {"type": "gemini", "content": "two"}
        third = {"type": "user", "content": "three"}
        state = {"gemini_snapshot_count": 0, "gemini_snapshot_tail": None}

        self.assertEqual(
            (first, second),
            records.incremental_gemini_records(
                {"$set": {"messages": [first, second]}},
                state,
            ),
        )
        self.assertEqual(
            (),
            records.incremental_gemini_records(
                {"$set": {"messages": [first, second]}},
                state,
            ),
        )
        self.assertEqual(
            (third,),
            records.incremental_gemini_records(
                {"$set": {"messages": [first, second, third]}},
                state,
            ),
        )

    def test_antigravity_head_keeps_partial_tail_without_a_line_cap(self) -> None:
        complete = [f"line-{index}" for index in range(40)]
        prefix = ("\n".join(complete) + "\npartial").encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cli.log"
            path.write_bytes(prefix + b"-continued")
            with mock.patch.object(
                dashboard,
                "ANTIGRAVITY_LOG_HEAD_BYTES",
                len(prefix),
            ):
                lines = dashboard.antigravity_log_head_lines(str(path))

        self.assertEqual([*complete, "partial"], lines)

    def test_antigravity_combined_read_uses_one_runtime_snapshot(self) -> None:
        first_runtime = make_runtime(
            antigravity_log_head_bytes=13,
            tail_bytes=10,
        )
        second_runtime = make_runtime(
            antigravity_log_head_bytes=5,
            tail_bytes=10,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cli.log"
            path.write_bytes(b"first-header\nmiddle\nlast-tail\n")
            with mock.patch.object(
                dashboard,
                "_legacy_runtime",
                side_effect=[first_runtime, second_runtime],
            ) as legacy_runtime:
                lines = dashboard.antigravity_log_lines(str(path))

        self.assertEqual(["first-header", "last-tail", ""], lines)
        self.assertEqual(1, legacy_runtime.call_count)

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
        self.assertEqual([(records.parse_ts("2026-01-01T00:00:05Z"), 42)], info["usage_events"])
        self.assertEqual([5.0], turns["durations"])
        self.assertEqual(records.parse_ts("2026-01-01T00:00:10Z"), turns["turn_start"])

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
        runtime_sessions.assign_display_ids(make_config(), sessions)
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
