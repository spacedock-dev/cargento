from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

from cargento_runtime import aggregate, diagnostics
from cargento_runtime import io as runtime_io
from cargento_runtime.collectors import antigravity as agy_collector
from cargento_runtime.collectors import cursor as cursor_collector
from cargento_runtime.collectors import goose as goose_collector
from cargento_runtime.collectors import opencode as opencode_collector

from .support import (
    SERVER_PATH,
    STORE_OVERRIDES,
    RuntimeTestCase,
    collect,
    collect_claude,
    config_patch,
    diagnose,
    make_runtime,
    runtime,
    state_of,
    store_patch,
)


class SqliteCollectorTest(RuntimeTestCase):
    def test_goose_tool_response_is_not_a_user_prompt(self) -> None:
        self.assertFalse(
            goose_collector._user_prompt(
                [{"type": "toolResponse", "toolResult": {"status": "success"}}]
            )
        )
        self.assertTrue(goose_collector._user_prompt([{"type": "text", "text": "hello"}]))

    @staticmethod
    def _opencode_db(
        path: Path,
        rows: list[tuple[Any, ...]],
        *,
        with_archived: bool = True,
        messages: list[tuple[Any, ...]] | None = None,
    ) -> None:
        archived = ", time_archived INTEGER" if with_archived else ""
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TABLE session (id TEXT, parent_id TEXT, directory TEXT,"
            f" title TEXT, time_updated INTEGER{archived})"
        )
        placeholders = ", ".join("?" * (6 if with_archived else 5))
        con.executemany(
            f"INSERT INTO session VALUES ({placeholders})",  # noqa: S608 — literal "?" only
            rows,
        )
        con.execute(
            "CREATE TABLE session_message (session_id TEXT, type TEXT,"
            " time_created INTEGER, data TEXT)"
        )
        if messages:
            con.executemany("INSERT INTO session_message VALUES (?, ?, ?, ?)", messages)
        con.commit()
        con.close()

    def test_an_archived_session_does_not_ghost_as_working(self) -> None:
        # Archiving bumps time_updated, so an archived session would otherwise
        # read as active the moment it was filed away. Mutation-checked:
        # dropping the time_archived skip passed the whole suite.
        now = time.time()
        millis = int(now * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            self._opencode_db(
                Path(tmp) / "opencode.db",
                [
                    ("live", None, "/w/live", "Live", millis, None),
                    ("filed", None, "/w/filed", "Filed", millis, millis),
                ],
            )
            with store_patch(OPENCODE_DATA=str(tmp)):
                config, state = runtime()
                rows = opencode_collector.collect(config, state, now, 24, True)

        self.assertEqual(["live"], [row["sid"] for row in rows])

    def test_a_store_without_time_archived_still_reads(self) -> None:
        # OpenCode added the column, and an older store must not read as empty.
        # Mutation-checked: narrowing the fallback's exception passed the suite.
        now = time.time()
        millis = int(now * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            self._opencode_db(
                Path(tmp) / "opencode.db",
                [("old", None, "/w/old", "Old schema", millis)],
                with_archived=False,
            )
            with store_patch(OPENCODE_DATA=str(tmp)):
                config, state = runtime()
                rows = opencode_collector.collect(config, state, now, 24, True)

        self.assertEqual(["old"], [row["sid"] for row in rows])

    def test_fresh_child_sessions_become_the_parents_subagents(self) -> None:
        # Mutation-checked: dropping the child titles passed the whole suite.
        now = time.time()
        millis = int(now * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            self._opencode_db(
                Path(tmp) / "opencode.db",
                [
                    ("parent", None, "/w/proj", "Parent", millis, None),
                    ("kid", "parent", "/w/proj", "researcher", millis, None),
                ],
            )
            with store_patch(OPENCODE_DATA=str(tmp)):
                config, state = runtime()
                rows = opencode_collector.collect(config, state, now, 24, True)

        self.assertEqual(1, len(rows), "a child must not become its own row")
        # DRC-4117 grew each element into an object. `model` is present and
        # None: OpenCode records no model, and that is a different fact from
        # "this child runs whatever its parent runs".
        self.assertEqual([{"name": "researcher", "model": None}], rows[0]["subagents"])
        self.assertEqual("working", rows[0]["state"])

    def test_a_broken_session_query_is_recorded_as_a_store_error(self) -> None:
        # Collectors swallow their failures, so a corrupt store reads as an idle
        # machine unless the error reaches diagnostics. Mutation-checked:
        # dropping record_store_error passed the whole suite.
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "opencode.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE unrelated (x INTEGER)")  # no session table
            con.commit()
            con.close()
            with store_patch(OPENCODE_DATA=str(tmp)):
                config, state = runtime()

                self.assertEqual([], opencode_collector.collect(config, state, now, 24, True))
                self.assertIn(str(db), state.store_errors)

    def test_a_real_store_yields_nothing_when_sqlite3_is_missing(self) -> None:
        # The guard only matters when a store EXISTS and sqlite3 does not; with
        # no store the empty glob hides it. Mutation-checked: removing the guard
        # passed the whole suite.
        now = time.time()
        millis = int(now * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            self._opencode_db(
                Path(tmp) / "opencode.db",
                [("s1", None, "/w/proj", "Work", millis, None)],
            )
            with store_patch(OPENCODE_DATA=str(tmp)):
                config, state = runtime()
                self.assertEqual(
                    ["s1"],
                    [r["sid"] for r in opencode_collector.collect(config, state, now, 24, True)],
                )
                with mock.patch.object(
                    runtime_io, "SQLITE_IMPORT_ERROR", "No module named '_sqlite3'"
                ):
                    self.assertFalse(opencode_collector.discover(config, state))
                    self.assertEqual([], opencode_collector.collect(config, state, now, 24, True))

    def test_opencode_show_all_returns_every_session(self) -> None:
        now = time.time()
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

            with store_patch(OPENCODE_DATA=str(tmp)):
                config, state = runtime()
                everything = opencode_collector.collect(config, state, now, 24, True)
                windowed = opencode_collector.collect(config, state, now, 24, False)

        self.assertEqual(250, len(everything))  # previously capped at 200
        self.assertEqual(0, len(windowed))

    def _cursor_store(
        self,
        tmp: Path,
        sid: str,
        rows: list[Any],
        blobs: dict[str, bytes] | None = None,
        meta_json: dict[str, Any] | None = None,
    ) -> None:
        db = tmp / "chats" / "hash1" / sid / "store.db"
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(str(db))
        try:
            con.execute("CREATE TABLE meta (value BLOB)")
            for row in rows:
                payload = json.dumps(row)
                # Cursor hex-encodes the JSON in some versions; cover that one.
                con.execute("INSERT INTO meta VALUES (?)", (payload.encode().hex(),))
            # Omitted entirely when there are no blobs, because that is the
            # shape a store on an older schema has, and "no such table" must
            # read as "no model here", not as a broken store.
            if blobs is not None:
                con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
                con.executemany("INSERT INTO blobs VALUES (?, ?)", list(blobs.items()))
            con.commit()
        finally:
            con.close()
        # The sibling file the real store keeps beside store.db, written only
        # when asked: one live agent directory — the subagent's — has none, so
        # its absence is a shape a store really has and not a lazy fixture.
        if meta_json is not None:
            (db.parent / "meta.json").write_text(json.dumps(meta_json, separators=(",", ":")))

    @staticmethod
    def _cursor_message(model: str | None, text: str = "hi") -> bytes:
        """One message blob, with or without the model Cursor records on it."""
        payload: dict[str, Any] = {"role": "assistant", "content": [{"type": "text", "text": text}]}
        if model is not None:
            payload["providerOptions"] = {"cursor": {"modelName": model}}
        return json.dumps(payload, separators=(",", ":")).encode()

    # One tool-call contract, keyed by its own `toolCallId`, with the five keys
    # the capture's `pending-record-shape` arm enumerated. The values are
    # deliberately loud rather than plausible: three of these keys can carry a
    # tool name, and a test that used realistic ones could not tell "the reader
    # never touched them" from "the reader published something innocuous".
    CURSOR_CONTRACT_ID = "call_" + "f" * 80
    CURSOR_CONTRACT: ClassVar[dict[str, Any]] = {
        "allowedToolNames": ["NEVER-RENDER-ALLOWED"],
        "isDynamic": False,
        "outerToolName": "NEVER-RENDER-OUTER",
        "toolCallId": CURSOR_CONTRACT_ID,
        "toolIdentifier": "NEVER-RENDER-IDENTIFIER",
    }

    @classmethod
    def _cursor_pending(cls, *, waiting: bool, started_ms: int | None = None) -> bytes:
        """One carrier blob, in the shape the store holds it while a gate stands.

        Not a JSON object. The capture measured the carrier as a length-prefixed
        binary frame with the payload inside it, which is the whole reason the
        reader matches on bytes: a brace-first parse of this blob finds nothing.
        The frame header here stands in for that prefix rather than reproducing
        Cursor's protobuf exactly — what the test needs is that byte 0 is not
        `{`.

        ``waiting`` picks between the two states the same three keys wear. An
        answered call keeps `pendingToolCallStartedAtMs` and empties the
        contracts map, which is measured (`a1-approve`:
        `pending_started_ms_present_after_answer` true beside
        `pending_contract_entries_after_answer` 0) and is why the stamp cannot
        be the discriminator.
        """
        payload: dict[str, Any] = {"modelProviderMessageId": "msg-1"}
        if started_ms is not None:
            payload["pendingToolCallStartedAtMs"] = started_ms
        payload["pendingToolExecutionContracts"] = (
            {cls.CURSOR_CONTRACT_ID: cls.CURSOR_CONTRACT} if waiting else {}
        )
        body = json.dumps(payload, separators=(",", ":")).encode()
        return b"\x0a" + len(body).to_bytes(4, "big") + body

    @staticmethod
    def _cursor_chat(messages: list[bytes], trailer: bytes = b"") -> tuple[str, dict[str, bytes]]:
        """(root blob id, the blobs table) for a chat holding ``messages``.

        Shaped like the real store rather than conveniently: blob ids are the
        sha256 of the blob's own bytes, and the root blob is the flat, ordered
        list of child ids, each framed as protobuf field 1 (`0a 20 <32 bytes>`).
        ``trailer`` appends raw bytes past that list, which is how a stray frame
        inside message text reaches the parser.
        """
        pairs = [(hashlib.sha256(m).hexdigest(), m) for m in messages]
        root = b"".join(b"\x0a\x20" + bytes.fromhex(i) for i, _ in pairs) + trailer
        root_id = hashlib.sha256(root).hexdigest()
        return root_id, {root_id: root, **dict(pairs)}

    def _collect_cursor(
        self,
        tmp: Path,
        *,
        now: float | None = None,
        window_hours: float = 24,
        show_all: bool = True,
    ) -> list[dict[str, Any]]:
        """The Cursor rows one chats root publishes.

        ``now`` is a parameter rather than always the wall clock because the
        liveness gate is a comparison against it: the abandoned-store case is
        built by reading a store that was written seconds ago from a clock 29.4
        hours later, which is the measured arrangement without a sleep or an
        ``os.utime`` race in it.
        """
        with (
            store_patch(CURSOR_CHATS=str(tmp / "chats")),
            mock.patch.dict(STORE_OVERRIDES, {"cursor.chats": [str(tmp / "chats")]}),
        ):
            config, state = runtime()
            sessions: list[dict[str, Any]] = cursor_collector.collect(
                config, state, time.time() if now is None else now, window_hours, show_all
            )
            return sessions

    def test_cursor_metadata_is_memoized_until_the_store_changes(self) -> None:
        # The meta table is stable, so a memo hit must not reopen the store on
        # every five-second refresh. Asserting the returned value is not enough:
        # the double-checked lock inside _meta returns the cached value even
        # with the outer memo gone, so this counts store opens instead.
        #
        # The model is memoized with the title and the workspace, and that is
        # what keeps its two blob lookups off every refresh: it costs a read
        # only when the store has moved, which is exactly when it can have
        # changed.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "w" / "proj"
            workspace.mkdir(parents=True)
            root_id, blobs = self._cursor_chat([self._cursor_message("vega")])
            self._cursor_store(
                root,
                "aaaa1111",
                [
                    {
                        "name": "Some title",
                        "workspacePath": str(workspace),
                        "latestRootBlobId": root_id,
                    }
                ],
                blobs,
            )
            self.assertEqual(1, len(self._collect_cursor(root)))

            config, state = runtime()
            db = next(iter(state.cursor_metadata_cache))
            mtime = state.cursor_metadata_cache[db][0]

            # The parent edge and the child's label ride a third cache entry, on
            # the same mtime: without one, a five-second refresh would reopen
            # every store just to re-read an id that cannot have changed.
            self.assertEqual(
                (mtime, "", ""),
                state_of().cursor_metadata_cache[cursor_collector._subagent_key(db)],
            )

            opens: list[str] = []
            real_open = runtime_io.open_sqlite_read_only

            def counting_open(path: str, st: Any) -> Any:
                opens.append(path)
                return real_open(path, st)

            with mock.patch.object(runtime_io, "open_sqlite_read_only", counting_open):
                self.assertEqual(
                    ("Some title", str(workspace), "vega", "", "", None),
                    cursor_collector._meta(config, state, db, mtime),
                )
                self.assertEqual([], opens, "a memo hit reopened the store")

                # A changed mtime invalidates the memo, so the store is read.
                self.assertEqual(
                    ("Some title", str(workspace), "vega", "", "", None),
                    cursor_collector._meta(config, state, db, mtime + 1),
                )
                self.assertEqual([db], opens)

    def test_cursor_publishes_the_model_of_its_newest_message(self) -> None:
        # DRC-4117. The model lives on the message blobs, not in a column, and
        # the root blob's child list is the only chronology the store has: ids
        # are content-addressed sha256 and `blobs` has no timestamp, so the
        # newest message is the last child and nothing else can say which it is.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_id, blobs = self._cursor_chat(
                [
                    self._cursor_message("last-week-model"),
                    self._cursor_message(None, text="a tool result"),
                    self._cursor_message("vega"),
                ]
            )
            self._cursor_store(
                root, "sess-model", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            sessions = self._collect_cursor(root)

        self.assertEqual(1, len(sessions))
        # Verbatim: `vega` is Cursor's own codename, and mapping it to a
        # marketing name would be the page inventing a reading the store never
        # made.
        self.assertEqual("vega", sessions[0]["model"])
        self.assertEqual("chat", sessions[0]["title"])

    def test_cursor_walks_past_a_child_id_that_belongs_to_no_blob(self) -> None:
        # The child list is found by scanning for `0a 20` frames, so a stray
        # pair inside message text yields a plausible 64-hex id that no row
        # carries. The walk starts at the newest end, so that bogus id is tried
        # FIRST; it has to miss on the primary key and cost one probe, not the
        # session's model.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_id, blobs = self._cursor_chat(
                [self._cursor_message("vega")], trailer=b"\x0a\x20" + b"\xff" * 32
            )
            self._cursor_store(
                root, "sess-stray", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            sessions = self._collect_cursor(root)

        self.assertEqual("vega", sessions[0]["model"])

    def test_cursor_keeps_its_title_when_the_store_has_no_blobs_table(self) -> None:
        # The failure that costs the most: a store on a schema without `blobs`
        # raises `no such table`, and routing that through the store-error path
        # would withdraw the title and the workspace along with the model. They
        # are separate readings, and only the one that failed may be withdrawn.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "git" / "recce" / "cargento"
            workspace.mkdir(parents=True)
            self._cursor_store(
                root,
                "sess-old",
                [
                    {
                        "name": "refactor the parser",
                        "workspacePath": str(workspace),
                        "latestRootBlobId": "a" * 64,
                    }
                ],
            )
            sessions = self._collect_cursor(root)
            errors = dict(state_of().store_errors)

        self.assertEqual("refactor the parser", sessions[0]["title"])
        self.assertEqual("recce/cargento", sessions[0]["project"])
        self.assertIsNone(sessions[0]["model"])
        self.assertEqual(
            [], [p for p in errors if "sess-old" in p], "a missing table is not a fault"
        )

    def test_cursor_reports_no_model_when_the_blobs_do_not_read_as_text(self) -> None:
        # Every meta payload carries a `blobEncryptionKey`, so some Cursor build
        # almost certainly encrypts the blobs. There the field simply is not
        # found, and the session must report no model rather than anything else
        # — and the key in the store is never used to go looking.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_id, blobs = self._cursor_chat([bytes(range(256)) * 4])
            self._cursor_store(
                root, "sess-enc", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            sessions = self._collect_cursor(root)

        self.assertIsNone(sessions[0]["model"])

    def test_cursor_reports_no_model_rather_than_an_old_one_past_the_walk_cap(self) -> None:
        # The walk is bounded so a long conversation cannot pull tens of
        # kilobytes per refresh. Falling off the end of that budget reports no
        # model, which is honest; reaching further back for one would report the
        # model of a message that is not the current one.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = runtime()
            depth = config.cursor_model_probe_blobs + 2
            messages = [self._cursor_message("vega")]
            messages += [self._cursor_message(None, text=f"turn {i}") for i in range(depth)]
            root_id, blobs = self._cursor_chat(messages)
            self._cursor_store(
                root, "sess-deep", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            sessions = self._collect_cursor(root)

        self.assertIsNone(sessions[0]["model"])

    def test_cursor_publishes_the_newest_model_past_the_root_child_cap(self) -> None:
        # DRC-4117. The child list is capped, and the cap used to keep the ids
        # it met FIRST — the oldest end of a list that runs oldest first. Past
        # `cursor_root_children` the probe window then never moved again: the
        # model of message ~63 was published as the model of a chat that had
        # since switched, rendered exactly like a live reading, and re-derived
        # identically on every refresh so it could never self-correct. Every
        # tool result is its own child, so the cap is about 16 assistant turns.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = runtime()
            before = config.cursor_root_children + 20
            messages = [
                self._cursor_message("last-week-model", text=f"turn {i}") for i in range(before)
            ]
            messages.append(self._cursor_message("vega"))
            root_id, blobs = self._cursor_chat(messages)
            self._cursor_store(
                root, "sess-long", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            sessions = self._collect_cursor(root)

        self.assertEqual("vega", sessions[0]["model"])

    def test_cursor_reads_the_newest_children_of_a_root_past_the_byte_cap(self) -> None:
        # Same freeze one level down: the root itself is read under
        # `cursor_blob_bytes`, and its newest children are at its END, so a head
        # read would hand back the oldest window and pin the answer there for
        # good. It is read from the tail instead. The re-sync can land mid-frame
        # and invent an id; that id is at the OLD end of the window and misses
        # on the primary key like any other stray frame.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with config_patch(cursor_blob_bytes=512), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = [
                self._cursor_message("last-week-model", text="older"),
                self._cursor_message(None, text="a tool result"),
                self._cursor_message("vega"),
            ]
            pairs = [(hashlib.sha256(m).hexdigest(), m) for m in real]
            # Filler ids for messages whose blobs have been pruned. No byte is
            # 0x0a or 0x20, so no filler id can fake a frame boundary.
            filler = [bytes([100 + (i % 90)]) * 32 for i in range(37)]
            root_blob = b"".join(b"\x0a\x20" + f for f in filler) + b"".join(
                b"\x0a\x20" + bytes.fromhex(i) for i, _ in pairs
            )
            self.assertGreater(len(root_blob), 512, "the root has to outrun the cap")
            root_id = hashlib.sha256(root_blob).hexdigest()
            self._cursor_store(
                root,
                "sess-wide",
                [{"name": "chat", "latestRootBlobId": root_id}],
                {root_id: root_blob, **dict(pairs)},
            )
            sessions = self._collect_cursor(root)

        self.assertEqual("vega", sessions[0]["model"])

    def test_cursor_reads_past_a_turn_with_ten_tool_results_in_flight(self) -> None:
        # The probe depth is a measurement, not a round number. Across three
        # live stores the longest run of consecutive non-assistant children
        # between two assistant messages is five — one turn with five tool
        # results in flight — which a six-deep window clears by exactly nothing.
        # The depth carries twice that run, so a turn this deep still reports
        # the model of the assistant message before it instead of a dash.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = [self._cursor_message("vega")]
            messages += [self._cursor_message(None, text=f"tool {i}") for i in range(10)]
            root_id, blobs = self._cursor_chat(messages)
            self._cursor_store(
                root, "sess-busy", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            sessions = self._collect_cursor(root)

        self.assertEqual("vega", sessions[0]["model"])

    def test_cursor_reports_no_model_past_a_blob_it_could_not_read_whole(self) -> None:
        # `providerOptions` is not anchored near the head of a blob: on the live
        # stores it sits 676–6,042 bytes in, sometimes as the last top-level key
        # of the message, so where it lands tracks how long the message ran. A
        # blob cut off at `cursor_blob_bytes` is therefore a message whose model
        # was NOT read, which is a different fact from a message carrying no
        # model — and reaching past it would hand the card the previous
        # message's model dressed as the current one.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with config_patch(cursor_blob_bytes=512), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_id, blobs = self._cursor_chat(
                [
                    self._cursor_message("last-week-model"),
                    self._cursor_message("vega", text="x" * 4096),
                ]
            )
            self._cursor_store(
                root, "sess-cut", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            sessions = self._collect_cursor(root)

        self.assertIsNone(sessions[0]["model"])

    def test_cursor_bounds_the_model_string_it_publishes(self) -> None:
        # A model name is vendor text on its way to the DOM. It is bounded here
        # so no page has to trust its length, and stripped of control characters
        # for the same reason every other untrusted string is.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_id, blobs = self._cursor_chat([self._cursor_message("v" * 60)])
            self._cursor_store(
                root, "sess-long", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            long_rows = self._collect_cursor(root)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_id, blobs = self._cursor_chat(
                [b'{"providerOptions":{"cursor":{"modelName":"a\tb"}}}']
            )
            self._cursor_store(
                root, "sess-ctrl", [{"name": "chat", "latestRootBlobId": root_id}], blobs
            )
            control_rows = self._collect_cursor(root)

        self.assertEqual("v" * 40, long_rows[0]["model"])
        self.assertEqual("a b", control_rows[0]["model"])

    def test_cursor_ignores_the_model_picker_setting(self) -> None:
        # `lastUsedModel` sits in the same meta payload and reads "default" on
        # two of three live sessions — it is the picker, not a measurement.
        # Publishing it would render a session as running a model literally
        # named "default", which is indistinguishable from a real reading.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_store(root, "sess-pick", [{"name": "chat", "lastUsedModel": "default"}])
            sessions = self._collect_cursor(root)

        self.assertIsNone(sessions[0]["model"])

    def test_cursor_reports_its_workspace_instead_of_the_harness_name(self) -> None:
        # DRC-3963. Cursor rows were hardcoded to "cursor", so every Cursor
        # session in every repository shared one label.
        if not runtime_io.sqlite_available():
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

    def test_cursor_reads_its_project_from_the_sibling_meta_json(self) -> None:
        # DRC-4118. Measured: the decoded `meta` payload of three live stores
        # holds agentId, blobEncryptionKey, createdAt, isRunEverything,
        # latestRootBlobId, mode and name — none of the six `_CURSOR_CWD_KEYS`
        # spellings — so every Cursor row fell back to the harness name. The
        # working directory is in the sibling meta.json the collector never
        # opened.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "git" / "recce" / "cargento"
            workspace.mkdir(parents=True)
            self._cursor_store(
                root,
                "sess-sibling",
                [{"agentId": "sess-sibling", "name": "chat", "mode": "agent"}],
                meta_json={
                    "schemaVersion": 1,
                    "cwd": str(workspace),
                    "title": "chat",
                    "createdAtMs": 1,
                    "updatedAtMs": 2,
                    "hasConversation": True,
                },
            )
            rows = self._collect_cursor(root)

        self.assertEqual(1, len(rows))
        self.assertEqual("recce/cargento", rows[0]["project"])

    def _cursor_subagent_meta(self, parent: str, type_name: str = "cursor-guide") -> dict[str, Any]:
        """The `subagentInfo` shape measured on the live subagent store.

        Both ids are the same there — nothing on this machine nests deeper than
        one level — and `name` is the generic literal Cursor writes for every
        child, which is why `typeName` is the label worth publishing.
        """
        return {
            "agentId": "child",
            "name": "New Agent",
            "subagentInfo": {
                "parentAgentId": parent,
                "rootParentAgentId": parent,
                "toolCallId": "call-x",
                "typeName": type_name,
            },
        }

    def test_cursor_folds_a_subagent_under_the_parent_its_meta_names(self) -> None:
        # DRC-4118. Cursor subagents kept their own store under the same
        # workspace hash and were published as peer top-level rows. The edge is
        # measured, not inferred: `subagentInfo.rootParentAgentId` names an agent
        # DIRECTORY, and a Cursor sid IS that directory name, so it is exactly
        # the sid another row publishes. The child sorts before the parent in the
        # glob, which is why the fold cannot be done in one pass.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent_root, parent_blobs = self._cursor_chat([self._cursor_message("vega")])
            child_root, child_blobs = self._cursor_chat([self._cursor_message("vega", "sub")])
            self._cursor_store(
                root,
                "child-1",
                [{**self._cursor_subagent_meta("parent-1"), "latestRootBlobId": child_root}],
                child_blobs,
            )
            self._cursor_store(
                root,
                "parent-1",
                [{"name": "Fix the login bug", "latestRootBlobId": parent_root}],
                parent_blobs,
            )
            rows = self._collect_cursor(root)

        self.assertEqual(["parent-1"], [r["sid"] for r in rows], "a child must not be a peer row")
        self.assertEqual([{"name": "cursor-guide", "model": "vega"}], rows[0]["subagents"])
        self.assertEqual("running 1 subagent", rows[0]["state_detail"])

    def test_cursor_shows_a_subagent_model_that_differs_from_its_parent(self) -> None:
        # SYNTHETIC fixture: `vega` is the only model value present anywhere in
        # the live Cursor stores, so a differing parent/child pair is fabricated
        # rather than measured. The payload has to carry both readings whatever
        # they are, since the page shows a child's model only where the two are
        # known and unequal, and that rule cannot fire on a value the collector
        # never published.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent_root, parent_blobs = self._cursor_chat([self._cursor_message("vega")])
            child_root, child_blobs = self._cursor_chat([self._cursor_message("last-week-model")])
            self._cursor_store(
                root,
                "child-2",
                [{**self._cursor_subagent_meta("parent-2"), "latestRootBlobId": child_root}],
                child_blobs,
            )
            self._cursor_store(
                root, "parent-2", [{"name": "chat", "latestRootBlobId": parent_root}], parent_blobs
            )
            rows = self._collect_cursor(root)

        self.assertEqual("vega", rows[0]["model"])
        self.assertEqual(
            [{"name": "cursor-guide", "model": "last-week-model"}], rows[0]["subagents"]
        )

    def test_cursor_publishes_a_subagent_whose_parent_is_not_present(self) -> None:
        # A parent id that names no store here promotes the child instead of
        # folding it. Dropping it would be an invisible failure: the reader
        # cannot tell "folded under its parent" from "lost".
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_store(root, "orphan-1", [self._cursor_subagent_meta("deleted-parent")])
            rows = self._collect_cursor(root)

        self.assertEqual(["orphan-1"], [r["sid"] for r in rows])
        self.assertEqual([], rows[0]["subagents"])

    def test_cursor_ignores_a_subagent_info_that_names_itself(self) -> None:
        # An edge that cannot be true must cost the row nothing: not nested under
        # itself, not dropped.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_store(root, "self-1", [self._cursor_subagent_meta("self-1")])
            rows = self._collect_cursor(root)

        self.assertEqual(["self-1"], [r["sid"] for r in rows])
        self.assertEqual([], rows[0]["subagents"])

    def test_cursor_keeps_a_parent_working_while_only_its_child_writes(self) -> None:
        # The parent's own store is quiet for an hour while the child writes, so
        # without absorbing the subtree the card would read Idle beside a
        # subagent that is generating. `own_activity` keeps the parent-alone
        # reading, which is what absorbing would otherwise throw away.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_store(root, "child-3", [self._cursor_subagent_meta("parent-3")])
            self._cursor_store(root, "parent-3", [{"name": "long workflow"}])
            parent_db = root / "chats" / "hash1" / "parent-3" / "store.db"
            quiet = time.time() - 3600
            os.utime(parent_db, (quiet, quiet))
            rows = self._collect_cursor(root)

        self.assertEqual(["parent-3"], [r["sid"] for r in rows])
        self.assertEqual("working", rows[0]["state"])
        self.assertGreater(rows[0]["last_activity"], rows[0]["own_activity"])
        self.assertAlmostEqual(quiet, rows[0]["own_activity"], delta=2.0)

    def test_cursor_keeps_its_row_when_the_sibling_meta_json_is_absent_or_unreadable(self) -> None:
        # The failure that would cost the most. An absent or unreadable meta.json
        # means NO WORKSPACE, never a FAILED STORE: one live agent directory has
        # none at all, and routing the miss through record_store_error would badge
        # the harness and withdraw the title and the model of every Cursor row.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        rows_by_case: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for case in ("absent", "not json", "cwd that is gone"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                root_id, blobs = self._cursor_chat([self._cursor_message("vega")])
                meta_json = None
                if case == "cwd that is gone":
                    meta_json = {"cwd": str(root / "deleted" / "checkout"), "title": "chat"}
                self._cursor_store(
                    root,
                    "sess-nometa",
                    [{"name": "refactor the parser", "latestRootBlobId": root_id}],
                    blobs,
                    meta_json=meta_json,
                )
                if case == "not json":
                    (root / "chats" / "hash1" / "sess-nometa" / "meta.json").write_text("{oops")
                rows_by_case[case] = self._collect_cursor(root)[0]
                errors += [p for p in dict(state_of().store_errors) if "sess-nometa" in p]

        for case, row in rows_by_case.items():
            self.assertEqual("cursor", row["project"], case)
            self.assertEqual("refactor the parser", row["title"], case)
            self.assertEqual("vega", row["model"], case)
        self.assertEqual([], errors, "a store with no meta.json is not a broken store")

    def test_cursor_rejects_a_meta_value_that_is_not_a_real_directory(self) -> None:
        # The key spellings are inferred from the VS Code lineage, not observed,
        # and in that family "workspace" routinely holds a .code-workspace FILE
        # while workspaceStorage/<hash> paths are everywhere. Either would give
        # a confident wrong label, which is worse than the harness name.
        if not runtime_io.sqlite_available():
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
        if not runtime_io.sqlite_available():
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
        if not runtime_io.sqlite_available():
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
        if not runtime_io.sqlite_available():
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
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_store(root, "sess-num", [{"name": 42, "title": "Fix the login bug"}])
            sessions = self._collect_cursor(root)

        self.assertEqual("Fix the login bug", sessions[0]["title"])

    def test_cursor_without_a_workspace_path_keeps_the_harness_name(self) -> None:
        now = time.time()
        if not runtime_io.sqlite_available():
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
                store_patch(CURSOR_CHATS=str(Path(tmp) / "chats")),
                mock.patch.dict(STORE_OVERRIDES, {"cursor.chats": [str(Path(tmp) / "chats")]}),
            ):
                config, state = runtime()
                sessions = cursor_collector.collect(config, state, now, 24, True)

        self.assertEqual("cursor", sessions[0]["project"])

    def test_cursor_sessions_discovered_with_title(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            chat = Path(tmp) / "ws1" / "33334444-bbbb"
            chat.mkdir(parents=True)
            con = sqlite3.connect(chat / "store.db")
            con.execute("CREATE TABLE meta (value TEXT)")
            hex_json = json.dumps({"name": "My Refactor Chat"}).encode().hex()
            con.execute("INSERT INTO meta VALUES (?)", (hex_json,))
            con.commit()
            con.close()

            with store_patch(CURSOR_CHATS=str(tmp)):
                config, state = runtime()
                sessions = cursor_collector.collect(config, state, now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual("working", sessions[0]["state"])
        self.assertEqual("My Refactor Chat", sessions[0]["title"])

    def _cursor_gate_store(self, root: Path, sid: str, carriers: list[bytes]) -> None:
        """A chat store with ``carriers`` appended after its message blobs.

        The carriers are not children of `latestRootBlobId`, and that is the
        arrangement rather than a shortcut: the capture's `store-ordering` arm
        found one readable store whose root id was not in the table at all, so a
        reader that reached the pending record by widening the existing
        meta-root-children walk would miss it there. They go in last so their
        rowids are the highest, which is the only order handle the schema has.
        """
        root_id, blobs = self._cursor_chat([self._cursor_message("vega")])
        for carrier in carriers:
            blobs[hashlib.sha256(carrier).hexdigest()] = carrier
        self._cursor_store(root, sid, [{"name": "Gated", "latestRootBlobId": root_id}], blobs)

    def test_cursor_memoizes_the_gate_on_the_same_mtime_as_the_rest(self) -> None:
        # The gate read is a scan where the model read is two indexed lookups, so
        # it is the one that most needs an idle session to cost nothing: without
        # the memo every Cursor store is scanned on every five-second refresh.
        # Counting store opens rather than comparing values, because `_meta`'s
        # double-checked lock returns the cached tuple even with the outer memo
        # gone.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        started = now - 45
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "aaaa1111",
                [self._cursor_pending(waiting=True, started_ms=int(started * 1000))],
            )
            self.assertEqual("needs_input", self._collect_cursor(root, now=now)[0]["state"])

            config, state = runtime()
            db = next(key for key in state.cursor_metadata_cache if key.endswith("store.db"))
            mtime = state.cursor_metadata_cache[db][0]
            opens: list[str] = []
            real_open = runtime_io.open_sqlite_read_only

            def counting_open(path: str, st: Any) -> Any:
                opens.append(path)
                return real_open(path, st)

            with mock.patch.object(runtime_io, "open_sqlite_read_only", counting_open):
                memoized = cursor_collector._meta(config, state, db, mtime)
                self.assertEqual([], opens, "a memo hit reopened the store")
                self.assertAlmostEqual(started, float(memoized[5] or 0), places=2)
                # A new blob moves the store, which is exactly when the answer
                # can have arrived, so a changed mtime must re-read.
                cursor_collector._meta(config, state, db, mtime + 1)
                self.assertEqual([db], opens)

    def test_cursor_finds_the_gate_when_the_store_keeps_its_blobs_as_text(self) -> None:
        # The column is declared BLOB and every store measured stores bytes, but
        # SQLite types values and not columns, so a build that wrote the frame as
        # text would keep it as text. That matters for more than the decode: the
        # scan is `instr(data, :key)` with a bytes needle, and if a text value
        # and a blob needle did not compare the reader would find nothing at all
        # on such a store, silently. Measured here rather than assumed.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        started = now - 60
        carrier = self._cursor_pending(waiting=True, started_ms=int(started * 1000))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_id, blobs = self._cursor_chat([self._cursor_message("vega")])
            self._cursor_store(root, "aaaa1111", [{"latestRootBlobId": root_id}], blobs)
            db = root / "chats" / "hash1" / "aaaa1111" / "store.db"
            con = sqlite3.connect(str(db))
            try:
                con.execute(
                    "INSERT INTO blobs VALUES (?, ?)",
                    (hashlib.sha256(carrier).hexdigest(), carrier.decode("latin-1")),
                )
                con.commit()
            finally:
                con.close()
            rows = self._collect_cursor(root, now=now)

        self.assertEqual("needs_input", rows[0]["state"])
        self.assertAlmostEqual(started, float(rows[0]["blocked_since"]), places=2)

    def test_cursor_reports_a_standing_gate_as_needs_input(self) -> None:
        # DRC-4202. `pendingToolExecutionContracts` non-empty on the newest blob
        # by rowid is a person being asked something, and the stamp beside it is
        # when they started waiting -- measured across four interactive
        # allowlist-mode sessions in
        # docs/captures/cursor/pending-tool-call-2026.08.11-macos.jsonl.
        #
        # 110.2 seconds is the a1-approve arm's own reading, and it is past
        # `working_threshold_sec`; the store's mtime is not, because the fixture
        # was written a moment ago. So this also pins the precedence: the row is
        # inside the working window and must still read Needs input, for the
        # reason Copilot's does (docs/design-needs-input.md N-2).
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        started = now - 110.2
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "aaaa1111",
                [self._cursor_pending(waiting=True, started_ms=int(started * 1000))],
            )
            rows = self._collect_cursor(root, now=now)

        self.assertEqual(1, len(rows))
        self.assertEqual("needs_input", rows[0]["state"])
        self.assertAlmostEqual(started, float(rows[0]["blocked_since"]), places=2)
        self.assertEqual("permission request, waiting 1m", rows[0]["state_detail"])

    def test_cursor_never_publishes_what_the_contract_names(self) -> None:
        # The contract entry carries `outerToolName`, `toolIdentifier` and
        # `allowedToolNames`, any of which can be a tool or a command. None of
        # them may reach a rendered field: the row's detail is the popup body
        # (`aggregate._wait_popup_body`), so a value read here is a value on a
        # desktop notification. Asserted over the whole serialized row rather
        # than over `state_detail`, because the title and the project are on the
        # same card.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "aaaa1111",
                [self._cursor_pending(waiting=True, started_ms=int((now - 30) * 1000))],
            )
            rows = self._collect_cursor(root, now=now)

        self.assertEqual("needs_input", rows[0]["state"])
        self.assertNotIn("NEVER-RENDER", json.dumps(rows[0]))
        self.assertNotIn(self.CURSOR_CONTRACT_ID, json.dumps(rows[0]))
        # The banner text itself, composed the way the application composes it,
        # since that is the surface DRC-4192 pointed at every harness.
        self.assertNotIn("NEVER-RENDER", aggregate._wait_popup_body(rows[0]))

    def test_cursor_reads_an_answered_gate_as_nobody_waiting(self) -> None:
        # The stamp survives the answer and the map is emptied, so a reader that
        # took `pendingToolCallStartedAtMs` for the discriminator -- which is the
        # field the originating issue named -- would report every session that
        # ever stood at a gate as waiting forever.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "aaaa1111",
                [self._cursor_pending(waiting=False, started_ms=int((now - 30) * 1000))],
            )
            rows = self._collect_cursor(root, now=now)

        self.assertEqual(1, len(rows))
        self.assertEqual("working", rows[0]["state"])
        self.assertIsNone(rows[0]["blocked_since"])

    def test_cursor_takes_the_newest_carrier_by_rowid_and_not_any_of_them(self) -> None:
        # The store is append-only and content-addressed: the blob that stood at
        # the gate is still there after the answer, so "any blob carries a
        # non-empty map" is a wait that never ends. Both directions are asserted,
        # because a reader that simply preferred an empty map wherever it found
        # one would pass the first half and fail the second.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        old_ms, new_ms = int((now - 300) * 1000), int((now - 40) * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "answered1",
                [
                    self._cursor_pending(waiting=True, started_ms=old_ms),
                    self._cursor_pending(waiting=False, started_ms=old_ms),
                ],
            )
            self._cursor_gate_store(
                root,
                "standing1",
                [
                    self._cursor_pending(waiting=False, started_ms=old_ms),
                    self._cursor_pending(waiting=True, started_ms=new_ms),
                ],
            )
            rows = {row["sid"]: row for row in self._collect_cursor(root, now=now)}

        self.assertEqual("working", rows["answered1"]["state"])
        self.assertEqual("needs_input", rows["standing1"]["state"])
        self.assertAlmostEqual(new_ms / 1000, float(rows["standing1"]["blocked_since"]), places=2)

    def test_cursor_re_reads_a_gate_whose_first_read_never_returned(self) -> None:
        # The gate read is memoized on the store's mtime, and a standing gate is
        # the last write the store gets -- the capture's false-positive control
        # found abandoned stores still at a gate 29.4 hours after their last
        # write. So an mtime a gate has frozen never moves again while the human
        # is waiting, and a value cached against it is cached for the whole life
        # of the wait. A query that raised returned no value at all: caching the
        # `None` the exception handler leaves behind hides that gate until the
        # human answers, which is when the wait is over.
        #
        # One `database is locked` on the first call only. That is the real
        # window: the refresh right after the gate-opening write, when Cursor's
        # writer is active and `open_sqlite_read_only`'s busy timeout can expire.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        started = now - 60
        real_pending = cursor_collector._pending_since
        reads: list[str] = []

        def locked_once(con: Any) -> float | None:
            reads.append("read")
            if len(reads) == 1:
                raise sqlite3.OperationalError("database is locked")
            return real_pending(con)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "aaaa1111",
                [self._cursor_pending(waiting=True, started_ms=int(started * 1000))],
            )
            with mock.patch.object(cursor_collector, "_pending_since", locked_once):
                first = self._collect_cursor(root, now=now)
                # The store is not touched between the two, so its mtime is the
                # one the failed read would have been cached against.
                second = self._collect_cursor(root, now=now)

        self.assertNotEqual("needs_input", first[0]["state"])
        self.assertEqual(2, len(reads), "the failed read was memoized as no gate")
        self.assertEqual("needs_input", second[0]["state"])
        self.assertAlmostEqual(started, float(second[0]["blocked_since"]), places=2)

    def test_cursor_takes_the_last_carrier_inside_one_blob(self) -> None:
        # Newest-by-rowid picks the blob; inside it the same rule has to hold,
        # because a blob is bytes appended in order too. Both directions, since a
        # reader that preferred whichever state it liked would pass one half:
        # answered-then-standing must read as a wait, standing-then-answered must
        # not, and the stamp published must be the one beside the carrier that
        # won rather than the first in the window.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        old_ms, new_ms = int((now - 40000) * 1000), int((now - 40) * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "standing1",
                [
                    self._cursor_pending(waiting=False, started_ms=old_ms)
                    + self._cursor_pending(waiting=True, started_ms=new_ms)
                ],
            )
            self._cursor_gate_store(
                root,
                "answered1",
                [
                    self._cursor_pending(waiting=True, started_ms=old_ms)
                    + self._cursor_pending(waiting=False, started_ms=new_ms)
                ],
            )
            rows = {row["sid"]: row for row in self._collect_cursor(root, now=now)}

        self.assertEqual("needs_input", rows["standing1"]["state"])
        self.assertAlmostEqual(new_ms / 1000, float(rows["standing1"]["blocked_since"]), places=2)
        self.assertEqual("working", rows["answered1"]["state"])

    def test_cursor_does_not_take_a_neighbours_stamp_for_the_gates(self) -> None:
        # The window opens 4096 bytes before the key, so anything inside it that
        # spells `pendingToolCallStartedAtMs` is a candidate -- and searching
        # forwards from the start of the window takes the object furthest from
        # the carrier. A gate 40 seconds old renders as eleven hours that way,
        # and sorts eleven hours wrong in the attention queue. The stamp nearest
        # the carrier's own key is the one that rides with it.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        started = now - 40
        neighbour = json.dumps(
            {"pendingToolCallStartedAtMs": int((now - 40000) * 1000)}, separators=(",", ":")
        ).encode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "aaaa1111",
                [
                    b"\x0a"
                    + len(neighbour).to_bytes(4, "big")
                    + neighbour
                    + self._cursor_pending(waiting=True, started_ms=int(started * 1000))
                ],
            )
            rows = self._collect_cursor(root, now=now)

        self.assertEqual("needs_input", rows[0]["state"])
        self.assertAlmostEqual(started, float(rows[0]["blocked_since"]), places=2)
        self.assertEqual("permission request, waiting 40s", rows[0]["state_detail"])

    def test_cursor_drops_a_gate_stamp_the_store_cannot_have_written(self) -> None:
        # A real gate's stamp rides the write that froze the store, so the two
        # are the same moment give or take the hook that ran first. A reading
        # from long before the store's last write is therefore not this
        # conversation's current state -- it is a stamp donated by another object
        # in the window, or bytes that merely spell the field, the way a message
        # quoting a store record does -- and publishing it is a red row and a
        # desktop popup carrying a wait nobody believes. Nothing retires such a
        # row on its own: the blob that produced it stays the newest carrier for
        # as long as the store exists.
        #
        # The control arm is the second half: the same fixture with the stamp
        # beside the store's own write does raise the wait, so the negative is a
        # property of the gap and not of the shape.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "quoted1",
                [self._cursor_pending(waiting=True, started_ms=int((now - 378 * 86400) * 1000))],
            )
            self._cursor_gate_store(
                root,
                "real1",
                [self._cursor_pending(waiting=True, started_ms=int((now - 40) * 1000))],
            )
            rows = {row["sid"]: row for row in self._collect_cursor(root, now=now)}

        self.assertEqual(2, len(rows), "the row itself must survive; only the wait is dropped")
        self.assertNotEqual("needs_input", rows["quoted1"]["state"])
        self.assertIsNone(rows["quoted1"]["blocked_since"])
        self.assertEqual("needs_input", rows["real1"]["state"])

    def test_cursor_does_not_publish_a_gate_a_dead_session_left_behind(self) -> None:
        # The liveness gate, and the measurement behind it: of ten readable
        # stores no arm of the probe had driven, 2 read as waiting 29.4 hours
        # after their process exited. A session abandoned at a gate stays pending
        # in the store forever, so without this the board carries permanent red
        # rows -- and since DRC-4192 a desktop notification with each.
        #
        # The control arm is the point of the second half. The same store, read
        # at its own clock, does raise the wait, so this fixture could have
        # produced the positive and the negative is a property of the age.
        if not runtime_io.sqlite_available():
            self.skipTest("sqlite3 unavailable")
        abandoned = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._cursor_gate_store(
                root,
                "aaaa1111",
                [self._cursor_pending(waiting=True, started_ms=int(abandoned * 1000))],
            )
            live = self._collect_cursor(root, now=abandoned + 30)
            # `show_all`, because the default window would drop the row before
            # the gate was ever consulted and prove nothing about the gate.
            stale = self._collect_cursor(root, now=abandoned + 29.4 * 3600, show_all=True)

        self.assertEqual("needs_input", live[0]["state"])
        self.assertEqual(1, len(stale), "the row itself must survive; only the wait is dropped")
        self.assertNotEqual("needs_input", stale[0]["state"])
        self.assertIsNone(stale[0]["blocked_since"])

    @staticmethod
    def _goose_db(path: Path, sid: str, description: str, stamp: str) -> None:
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TABLE sessions (id TEXT, description TEXT,"
            " working_dir TEXT, updated_at TEXT, session_type TEXT,"
            " parent_session_id TEXT, archived_at TEXT)"
        )
        con.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?)",
            (sid, description, "/w/proj", stamp, None, None, None),
        )
        con.execute(
            "CREATE TABLE messages (session_id TEXT, role TEXT,"
            " created_timestamp INTEGER, content_json TEXT)"
        )
        con.execute(
            "CREATE TABLE usage_ledger (session_id TEXT,"
            " created_timestamp INTEGER, output_tokens INTEGER)"
        )
        con.commit()
        con.close()

    def test_every_candidate_goose_database_is_scanned(self) -> None:
        # Goose moved its store between XDG and two Windows AppData locations,
        # so the resolver keeps several candidates and all of them are read.
        # Mutation-checked: scanning only the first candidate passed the suite.
        now = time.time()
        stamp = datetime.fromtimestamp(now - 10, UTC).strftime("%Y-%m-%d %H:%M:%S")
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "one.db", Path(tmp) / "two.db"
            self._goose_db(first, "from-first", "First store", stamp)
            self._goose_db(second, "from-second", "Second store", stamp)
            with (
                store_patch(GOOSE_DB=str(first)),
                mock.patch.dict(STORE_OVERRIDES, {"goose.db": [str(first), str(second)]}),
            ):
                config, state = runtime()
                rows = goose_collector.collect(config, state, now, 24, True)

        self.assertEqual({"from-first", "from-second"}, {row["sid"] for row in rows})

    def test_goose_sessions_from_shared_db(self) -> None:
        now = time.time()
        stamp = datetime.fromtimestamp(now - 10, UTC).strftime("%Y-%m-%d %H:%M:%S")
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

            with store_patch(GOOSE_DB=str(db)):
                config, state = runtime()
                sessions = goose_collector.collect(config, state, now, 24, False)

        self.assertEqual(1, len(sessions))  # subagent/infra/archived filtered
        s = sessions[0]
        self.assertEqual("working", s["state"])
        self.assertEqual("w/gooseproj", s["project"])  # DRC-3963: <parent>/<basename>
        self.assertEqual("Fix flaky tests", s["title"])
        self.assertEqual("add retries", s["last_prompt"])
        self.assertEqual([{"name": "helper", "model": None}], s["subagents"])
        self.assertEqual(100, s["rate_per_min"])  # 1000 tokens / 10 min window


class SqliteDiagnosticTest(unittest.TestCase):
    NOW = 1_700_000_000.0

    def test_a_corrupt_database_is_reported_by_diagnose(self) -> None:
        # Collectors swallow SQLite failures so one broken store cannot take
        # the dashboard down — which made --diagnose call a corrupt database a
        # healthy store with no sessions.
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "sessions.db"
            broken.write_text("definitely not a database")
            with (
                mock.patch.dict(STORE_OVERRIDES, {"goose.db": [str(broken)]}),
                store_patch(GOOSE_DB=str(broken)),
            ):
                report = diagnose(24)

        self.assertIn(str(broken), report["store_errors"])
        self.assertIn("not a database", report["store_errors"][str(broken)])
        self.assertIn("failed to open", diagnostics.render_diagnosis(report))

    def test_diagnose_reports_this_runs_store_errors_not_accumulated_ones(self) -> None:
        # store_errors is process-lifetime state, so a long-running dashboard
        # accumulates every store that ever failed. --diagnose exists to answer
        # "what is broken now", and a store fixed an hour ago must not still be
        # listed. Mutation-checked: dropping the clear passed the whole suite.
        _, state = runtime()
        stale = "/nonexistent/store/fixed-an-hour-ago.db"
        with state.cache_lock:
            state.store_errors[stale] = "DatabaseError: file is not a database"
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "sessions.db"
            broken.write_text("definitely not a database")
            with (
                mock.patch.dict(STORE_OVERRIDES, {"goose.db": [str(broken)]}),
                store_patch(GOOSE_DB=str(broken)),
            ):
                report = diagnose(24)

        self.assertIn(str(broken), report["store_errors"], "this run's failure must be reported")
        self.assertNotIn(stale, report["store_errors"])

    def test_query_failures_are_recorded_not_just_connection_failures(self) -> None:
        # A file that opens as a database but fails every query is the common
        # corruption shape; only the connect path was being recorded.
        with tempfile.TemporaryDirectory() as tmp:
            antigravity = Path(tmp) / "conv.db"
            antigravity.write_bytes(b"not a database")
            cursor = Path(tmp) / "store.db"
            cursor.write_bytes(b"also not a database")

            with state_of().cache_lock:
                state_of().store_errors.clear()
            config, state = runtime()
            agy_collector._step_activity(config, state, str(antigravity), self.NOW)
            self.assertIn(str(antigravity), state_of().store_errors)

            config, state = runtime()
            with state.cache_lock:
                state.store_errors.clear()
            self.assertEqual(
                (None, "", None, "", "", None),
                cursor_collector._meta(config, state, str(cursor), 1.0),
            )
            self.assertIn(str(cursor), state.store_errors)
            # A title the query never returned must not be cached as "no title".
            self.assertNotIn(str(cursor), state.cursor_metadata_cache)


class SqliteOptionalTest(unittest.TestCase):
    """sqlite3 is an optional stdlib module; minimal builds ship without it."""

    @contextlib.contextmanager
    def without_sqlite(self) -> Any:
        with mock.patch.object(runtime_io, "SQLITE_IMPORT_ERROR", "No module named '_sqlite3'"):
            yield

    def test_db_backed_collectors_return_empty_instead_of_raising(self) -> None:
        with self.without_sqlite():
            self.assertFalse(runtime_io.sqlite_available())
            now = 1_700_000_000.0
            config, state = runtime()
            collectors: tuple[tuple[str, Any], ...] = (
                ("opencode", lambda: opencode_collector.collect(config, state, now, 24, False)),
                ("cursor", lambda: cursor_collector.collect(config, state, now, 24, False)),
                ("goose", lambda: goose_collector.collect(config, state, now, 24, False)),
                (
                    "antigravity",
                    lambda: agy_collector.collect(config, state, now, 24, False),
                ),
            )
            for name, run in collectors:
                with self.subTest(collector=name):
                    self.assertEqual([], run())

    def test_db_backed_harnesses_are_not_advertised_as_discovered(self) -> None:
        # Reporting "discovered" for a store we cannot open would show the
        # harness as present but permanently empty.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "opencode.db"
            db.write_bytes(b"")
            with (
                self.without_sqlite(),
                store_patch(OPENCODE_DATA=str(tmp)),
                store_patch(GOOSE_DB=str(db)),
            ):
                found = {h["key"]: h["discovered"] for h in collect(24, False)["harnesses"]}

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
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
            ):
                sessions = collect_claude(now, 24, False)

        self.assertEqual(1, len(sessions))


class SqliteTrulyAbsentTest(unittest.TestCase):
    """Patching the flag leaves sqlite3 imported, so it cannot catch an unbound
    name. This imports the runtime in a subprocess where the module genuinely
    fails to import."""

    SCRIPT = """
import builtins, importlib.util, sys
from pathlib import Path
real_import = builtins.__import__
def blocked(name, *a, **k):
    if name == "sqlite3" or name.startswith("sqlite3."):
        raise ImportError("No module named 'sqlite3'")
    return real_import(name, *a, **k)
builtins.__import__ = blocked
sys.modules.pop("sqlite3", None)
sys.path.insert(0, str(Path({path!r}).parent))
# The runtime package is what must import without sqlite3. Importing the CLI
# reaches every module the dashboard needs; the database-backed collectors are
# named separately because nothing else imports them. All under the block.
from cargento_runtime import cli
from cargento_runtime import diagnostics as diagnostics_module
from cargento_runtime import io as runtime_io
from cargento_runtime.collectors import cursor as cursor_collector
from cargento_runtime.collectors import antigravity as agy_collector
from cargento_runtime.collectors import goose as goose_collector
from cargento_runtime.collectors import opencode as opencode_collector
builtins.__import__ = real_import
assert not runtime_io.sqlite_available(), "sqlite_available() should be False"
now = 1_700_000_000.0
import argparse, dataclasses, os, tempfile
from types import MappingProxyType


def runtime_for(**roots):
    args = cli.build_parser().parse_args([])
    config, state = cli.build_runtime(args, started=now)
    if roots:
        merged = dict(config.store_roots)
        merged.update({{key: (value,) for key, value in roots.items()}})
        config = dataclasses.replace(config, store_roots=MappingProxyType(merged))
    return config, state


cfg, st = runtime_for()
for name, mod in (("opencode", opencode_collector), ("cursor", cursor_collector),
                  ("goose", goose_collector)):
    assert mod.collect(cfg, st, now, 24, True) == [], name
# Antigravity is discovered from store mtime and CLI logs, so it survives
# without sqlite3 — only its rate and ETA degrade. Give it a real store so
# this exercises the database-backed path instead of an empty glob.
ag = tempfile.mkdtemp()
os.makedirs(os.path.join(ag, "conversations"))
store = os.path.join(ag, "conversations", "conv-1.db")
open(store, "wb").write(b"not a database")
os.utime(store, (now, now))
cfg2, st2 = runtime_for(**{{"antigravity.root": ag}})
found_ag = agy_collector.collect(cfg2, st2, now, 24, True)
assert len(found_ag) == 1, found_ag
assert found_ag[0]["rate_per_min"] == 0, "rate should degrade to zero"
assert found_ag[0]["turn"] is None, "no ETA without the database"
application = cli.build_application(cfg, st)
data = application.collect(show_all=True)   # full pass, including discovery
found = {{h["key"]: h["discovered"] for h in data["harnesses"]}}
assert found["opencode"] is False and found["goose"] is False and found["cursor"] is False
report = diagnostics_module.diagnose(cli.build_application(*runtime_for()))
assert report["sqlite"]["available"] is False
# A version string here would read as a working sqlite3 in a bug report.
assert report["sqlite"]["version"] is None, report["sqlite"]
assert report["sqlite"]["error"], "the import error is what explains the absence"
rendered = diagnostics_module.render_diagnosis(report)
assert "UNAVAILABLE" in rendered, rendered.splitlines()[:6]
# The shipped entry point still runs: --diagnose is the recovery command a user
# reaches for when a harness is missing, and it must work without sqlite3.
assert cli.main(["--diagnose", "--json"]) == 0
print("OK")
"""

    def test_server_imports_and_runs_without_sqlite3(self) -> None:
        script = self.SCRIPT.format(path=str(SERVER_PATH))
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=60, check=False
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK", result.stdout)


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
                self.assertEqual(expected, runtime_io.sqlite_ro_uri(path, windows=False))

    def test_posix_double_slash_root_gets_an_empty_authority(self) -> None:
        # "//dir" would otherwise parse as the URI authority "dir".
        self.assertEqual(
            "file:////dir/x.db",
            runtime_io.sqlite_ro_uri("//dir/x.db", windows=False)[: -len("?mode=ro")],
        )

    def test_windows_paths_use_sqlite_drive_letter_form(self) -> None:
        # SQLite only recognizes a drive letter as "/X:/...".
        self.assertEqual(
            "file:/C:/Users/a/x.db?mode=ro",
            runtime_io.sqlite_ro_uri(r"C:\Users\a\x.db", windows=True),
        )
        self.assertEqual(
            "file:/C:/Users/a%25b/x.db?mode=ro",
            runtime_io.sqlite_ro_uri(r"C:\Users\a%b\x.db", windows=True),
        )

    def test_windows_unc_paths_keep_an_empty_authority(self) -> None:
        # "//server/share" would parse as the authority "server"; SQLite only
        # accepts an empty or "localhost" authority.
        self.assertEqual(
            "file:////server/share/x.db?mode=ro",
            runtime_io.sqlite_ro_uri(r"\\server\share\x.db", windows=True),
        )

    def test_immutable_flag_is_opt_in(self) -> None:
        self.assertEqual(
            "file:/data/x.db?mode=ro&immutable=1",
            runtime_io.sqlite_ro_uri("/data/x.db", immutable=True, windows=False),
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
                    con = sqlite3.connect(runtime_io.sqlite_ro_uri(str(path)), uri=True)
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

            with store_patch(OPENCODE_DATA=str(data)):
                config, state = runtime()
                sessions = opencode_collector.collect(config, state, now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual("Percent", sessions[0]["title"])

    def test_open_sqlite_read_only_rejects_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.db"
            seed = sqlite3.connect(path)
            seed.execute("CREATE TABLE t(x)")
            seed.commit()
            seed.close()
            _, state = make_runtime()

            connection = runtime_io.open_sqlite_read_only(str(path), state)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("INSERT INTO t VALUES (1)")
            finally:
                connection.close()

    def test_open_failure_records_only_on_the_supplied_state(self) -> None:
        _, untouched = make_runtime()
        _, supplied = make_runtime()
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "missing" / "store.db")
            with self.assertRaises(sqlite3.OperationalError):
                runtime_io.open_sqlite_read_only(missing, supplied)

        self.assertEqual({}, untouched.store_errors)
        self.assertIn(missing, supplied.store_errors)
        self.assertIn("OperationalError", supplied.store_errors[missing])
