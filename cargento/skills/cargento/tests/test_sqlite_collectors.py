from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import io as runtime_io

from .support import SERVER_PATH, LegacyDashboardTestCase, dashboard, make_runtime


class SqliteCollectorTest(LegacyDashboardTestCase):
    def test_goose_tool_response_is_not_a_user_prompt(self) -> None:
        self.assertFalse(
            dashboard.goose_user_prompt(
                [{"type": "toolResponse", "toolResult": {"status": "success"}}]
            )
        )
        self.assertTrue(dashboard.goose_user_prompt([{"type": "text", "text": "hello"}]))

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
        now = dashboard.time.time()
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
                mock.patch.object(dashboard, "CURSOR_CHATS", str(Path(tmp) / "chats")),
                mock.patch.dict(
                    dashboard.STORE_ROOTS, {"cursor.chats": [str(Path(tmp) / "chats")]}
                ),
            ):
                sessions = dashboard.collect_cursor(now, 24, True)

        self.assertEqual("cursor", sessions[0]["project"])

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
                mock.patch.dict(dashboard.STORE_ROOTS, {"goose.db": [str(broken)]}),
                mock.patch.object(dashboard, "GOOSE_DB", str(broken)),
            ):
                report = dashboard.diagnose(24)

        self.assertIn(str(broken), report["store_errors"])
        self.assertIn("not a database", report["store_errors"][str(broken)])
        self.assertIn("failed to open", dashboard.render_diagnosis(report))

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


class SqliteOptionalTest(unittest.TestCase):
    """sqlite3 is an optional stdlib module; minimal builds ship without it."""

    @contextlib.contextmanager
    def without_sqlite(self) -> Any:
        with mock.patch.object(runtime_io, "SQLITE_IMPORT_ERROR", "No module named '_sqlite3'"):
            yield

    def test_db_backed_collectors_return_empty_instead_of_raising(self) -> None:
        with self.without_sqlite():
            self.assertFalse(runtime_io.sqlite_available())
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
from pathlib import Path
real_import = builtins.__import__
def blocked(name, *a, **k):
    if name == "sqlite3" or name.startswith("sqlite3."):
        raise ImportError("No module named 'sqlite3'")
    return real_import(name, *a, **k)
builtins.__import__ = blocked
sys.modules.pop("sqlite3", None)
sys.path.insert(0, str(Path({path!r}).parent))
spec = importlib.util.spec_from_file_location("srv", {path!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)          # must not raise
builtins.__import__ = real_import
assert not m.runtime_io.sqlite_available(), "sqlite_available() should be False"
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

            with mock.patch.object(dashboard, "OPENCODE_DATA", str(data)):
                sessions = dashboard.collect_opencode(now, 24, False)

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
