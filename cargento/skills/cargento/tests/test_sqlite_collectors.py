from __future__ import annotations

import contextlib
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
from typing import Any
from unittest import mock

from cargento_runtime import diagnostics
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
        self.assertEqual(["researcher"], rows[0]["subagents"])
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
            store_patch(CURSOR_CHATS=str(tmp / "chats")),
            mock.patch.dict(STORE_OVERRIDES, {"cursor.chats": [str(tmp / "chats")]}),
        ):
            config, state = runtime()
            sessions: list[dict[str, Any]] = cursor_collector.collect(
                config, state, time.time(), 24, True
            )
            return sessions

    def test_cursor_metadata_is_memoized_until_the_store_changes(self) -> None:
        # The meta table is stable, so a memo hit must not reopen the store on
        # every five-second refresh. Asserting the returned value is not enough:
        # the double-checked lock inside _meta returns the cached value even
        # with the outer memo gone, so this counts store opens instead.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "w" / "proj"
            workspace.mkdir(parents=True)
            self._cursor_store(
                root, "aaaa1111", [{"name": "Some title", "workspacePath": str(workspace)}]
            )
            self.assertEqual(1, len(self._collect_cursor(root)))

            config, state = runtime()
            db = next(iter(state.cursor_metadata_cache))
            mtime = state.cursor_metadata_cache[db][0]

            opens: list[str] = []
            real_open = runtime_io.open_sqlite_read_only

            def counting_open(path: str, st: Any) -> Any:
                opens.append(path)
                return real_open(path, st)

            with mock.patch.object(runtime_io, "open_sqlite_read_only", counting_open):
                self.assertEqual(
                    ("Some title", str(workspace)),
                    cursor_collector._meta(config, state, db, mtime),
                )
                self.assertEqual([], opens, "a memo hit reopened the store")

                # A changed mtime invalidates the memo, so the store is read.
                self.assertEqual(
                    ("Some title", str(workspace)),
                    cursor_collector._meta(config, state, db, mtime + 1),
                )
                self.assertEqual([db], opens)

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
        self.assertEqual(["helper"], s["subagents"])
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
            self.assertEqual((None, ""), cursor_collector._meta(config, state, str(cursor), 1.0))
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
