from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import cli
from cargento_runtime import io as runtime_io

from . import test_sqlite_collectors as sqlite_fixtures
from .fixtures import protobuf_bytes_field, write_antigravity_metadata
from .next_harness import NextPageJsHarness
from .support import SERVER_PATH, runtime, store_patch
from .test_gemini_antigravity import _generation_blob, _write_antigravity_generations


class CollectorSourceGapsTest(NextPageJsHarness):
    NOW = 1_700_000_000.0
    SID = "11111111-1111-1111-1111-111111111111"

    def _collect(self, harness: str, root: Path) -> dict[str, Any]:
        key = "ANTIGRAVITY_CLI_DIR" if harness == "antigravity" else "OPENCODE_DATA"
        with store_patch(**{key: str(root)}):
            config, state = runtime()
            return cli.build_application(config, state, clock=lambda: self.NOW).collect(
                show_all=True
            )

    def _row(self, payload: dict[str, Any], harness: str) -> dict[str, Any]:
        rows = [row for row in payload["sessions"] if row["harness"] == harness]
        self.assertEqual(1, len(rows))
        badge = next(row for row in payload["harnesses"] if row["key"] == harness)
        self.assertTrue(badge["discovered"])
        self.assertIsNone(badge["error"])
        return dict(rows[0])

    def _notice(self, payload: dict[str, Any], expected: str | None) -> None:
        html = self._run_page_js(
            f"nextData = {json.dumps(payload)};\nconsole.log(JSON.stringify(nextSessionsView()));"
        )
        if expected is None:
            self.assertNotIn("Source not fully read", html)
        else:
            self.assertIn(f"Source not fully read: {expected}", html)

    def _antigravity_store(self, root: Path, *, parent: str | None = None) -> Path:
        directory = root / "conversations"
        directory.mkdir(exist_ok=True)
        path = directory / f"{self.SID if parent is None else 'child'}.db"
        identity = protobuf_bytes_field(6, self.SID.encode())
        if parent is not None:
            identity = protobuf_bytes_field(5, parent.encode())
        write_antigravity_metadata(path, identity)
        with contextlib.closing(sqlite3.connect(path)) as con:
            con.execute("CREATE TABLE steps (idx INTEGER, step_type INTEGER, metadata BLOB)")
            con.commit()
        os.utime(path, (self.NOW, self.NOW))
        return path

    def test_antigravity_model_failures_disclose_without_losing_identity_or_activity(self) -> None:
        for arm in ("missing", "invalid", "null", "empty_blob", "empty_table", "valid"):
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = self._antigravity_store(root)
                if arm != "missing":
                    blobs = {
                        "invalid": [b"not a model tail"],
                        "empty_blob": [b""],
                        "valid": [_generation_blob(b"Gemini 3.6 Flash (High)")],
                    }.get(arm, [])
                    _write_antigravity_generations(path, blobs)
                    if arm == "null":
                        with contextlib.closing(sqlite3.connect(path)) as con:
                            con.execute("INSERT INTO gen_metadata VALUES (0, NULL)")
                            con.commit()
                logs = root / "log"
                logs.mkdir()
                log = logs / "cli-1.log"
                log.write_text(
                    f"workspaceDirs=[/work/acme/proj] appDataDir={root}\n"
                    f"Created conversation {self.SID}\n"
                    'HandleUserInput called with text: "keep this prompt"\n'
                    f"Forwarding user message to conversation {self.SID}\n",
                    encoding="utf-8",
                )
                os.utime(log, (self.NOW, self.NOW))
                os.utime(path, (self.NOW, self.NOW))
                payload = self._collect("antigravity", root)
                row = self._row(payload, "antigravity")
                self.assertEqual("acme/proj", row["project"])
                self.assertEqual("keep this prompt", row["last_prompt"])
                self.assertEqual(0, row["rate_per_min"])
                self.assertTrue(row["active"])
                self.assertEqual(
                    "Gemini 3.6 Flash (High)" if arm == "valid" else None, row["model"]
                )
                healthy = arm in ("empty_table", "valid")
                self.assertEqual([] if healthy else ["model"], row["source_gaps"])
                self._notice(payload, None if healthy else "model")

    def test_antigravity_blob_io_failures_keep_the_model_gap(self) -> None:
        real_connect = runtime_io.sqlite_module.connect
        for operation in ("seek", "read"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = self._antigravity_store(root)
                _write_antigravity_generations(path, [_generation_blob(b"Gemini")])
                os.utime(path, (self.NOW, self.NOW))

                def connect(*args: Any, failed_operation: str = operation, **kwargs: Any) -> Any:
                    con = real_connect(*args, **kwargs)
                    wrapped = mock.MagicMock(wraps=con)

                    def blobopen(*args: Any, **kwargs: Any) -> Any:
                        blob = con.blobopen(*args, **kwargs)
                        wrapped_blob = mock.MagicMock(wraps=blob)
                        wrapped_blob.__len__.return_value = len(blob)
                        getattr(wrapped_blob, failed_operation).side_effect = OSError(
                            "blob read failed"
                        )
                        return wrapped_blob

                    wrapped.blobopen.side_effect = blobopen
                    return wrapped

                with mock.patch.object(runtime_io.sqlite_module, "connect", side_effect=connect):
                    payload = self._collect("antigravity", root)
                row = self._row(payload, "antigravity")
                self.assertIsNone(row["model"])
                self.assertEqual(["model"], row["source_gaps"])

    def test_antigravity_child_model_failure_is_not_the_parents_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._antigravity_store(root)
            _write_antigravity_generations(path, [_generation_blob(b"Gemini")])
            os.utime(path, (self.NOW, self.NOW))
            self._antigravity_store(root, parent=self.SID)
            payload = self._collect("antigravity", root)
            row = self._row(payload, "antigravity")
            self.assertEqual(self.SID, row["sid"])
            self.assertEqual("Gemini", row["model"])
            self.assertEqual([], row["source_gaps"])
            self.assertEqual(1, len(row["subagents"]))
            self.assertIsNone(row["subagents"][0]["model"])
            self._notice(payload, None)

    def test_opencode_unread_roles_disclose_with_or_without_an_older_prompt(self) -> None:
        for raw in ("{", "[]", "{}", '{"role":"future"}', '{"role":[]}'):
            for older in (False, True):
                with self.subTest(raw=raw, older=older), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    millis = int(self.NOW * 1000)
                    messages, parts = (
                        sqlite_fixtures.SqliteCollectorTest._opencode_turn(
                            "s1", millis - 60_000, "old prompt"
                        )
                        if older
                        else ([], [])
                    )
                    messages.append(("bad", "s1", millis - 1000, millis - 1000, raw))
                    sqlite_fixtures.SqliteCollectorTest._opencode_db(
                        root / "opencode.db",
                        [("s1", None, "/work/acme/proj", "identity survives", millis, None)],
                        messages=messages,
                        parts=parts,
                    )
                    payload = self._collect("opencode", root)
                    row = self._row(payload, "opencode")
                    self.assertEqual("identity survives", row["title"])
                    self.assertEqual("old prompt" if older else "", row["last_prompt"])
                    self.assertEqual(older, row["turn"] is not None)
                    self.assertEqual(["message history"], row["source_gaps"])
                    self._notice(payload, "message history")

    def test_opencode_recognized_messages_remain_gap_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            millis = int(self.NOW * 1000)
            messages, parts = sqlite_fixtures.SqliteCollectorTest._opencode_turn(
                "s1", millis - 60_000, "new prompt", model="gpt-5.6"
            )
            sqlite_fixtures.SqliteCollectorTest._opencode_db(
                root / "opencode.db",
                [("s1", None, "/work/acme/proj", "healthy", millis, None)],
                messages=messages,
                parts=parts,
            )
            payload = self._collect("opencode", root)
            row = self._row(payload, "opencode")
            self.assertEqual("new prompt", row["last_prompt"])
            self.assertEqual("gpt-5.6", row["model"])
            self.assertEqual([], row["source_gaps"])
            self._notice(payload, None)

    def test_an_unknown_role_does_not_extend_a_measured_opencode_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            millis = int(self.NOW * 1000)
            messages, parts = sqlite_fixtures.SqliteCollectorTest._opencode_turn(
                "s1", millis - 200_000, "old prompt"
            )
            messages.append(("bad", "s1", millis - 100_000, millis - 100_000, "{}"))
            newest, newest_parts = sqlite_fixtures.SqliteCollectorTest._opencode_turn(
                "s1", millis - 20_000, "current prompt", suffix="new"
            )
            sqlite_fixtures.SqliteCollectorTest._opencode_db(
                root / "opencode.db",
                [("s1", None, "/work/acme/proj", "healthy", millis, None)],
                messages=messages + newest,
                parts=parts + newest_parts,
            )
            row = self._row(self._collect("opencode", root), "opencode")
            self.assertEqual("current prompt", row["last_prompt"])
            self.assertIsNone(row["turn"]["eta_h"])
            self.assertEqual(["message history"], row["source_gaps"])

    def test_runtime_without_sqlite_discloses_only_attempted_activity_reads(self) -> None:
        script = """
import builtins, dataclasses, json, sys
from pathlib import Path
root, launcher, absent, now = sys.argv[1:]
real_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == "sqlite3" or name.startswith("sqlite3."):
        raise ImportError("No module named '_sqlite3'")
    return real_import(name, *args, **kwargs)
if absent == "yes":
    builtins.__import__ = blocked
sys.path.insert(0, str(Path(launcher).parent))
from cargento_runtime import cli, config, diagnostics, io, state
cfg = config.build_runtime_config(environ={"HOME": root}, launcher_path=Path(launcher),
                                  platform_name="linux", os_name="posix")
cfg = dataclasses.replace(cfg, store_roots={"antigravity.root": (root,)})
st = state.build_runtime_state(cfg, started=float(now))
app = cli.build_application(cfg, st, clock=lambda: float(now))
payload = app.collect(show_all=True)
report = diagnostics.diagnose(app)
print(json.dumps({"payload": payload, "sqlite": report["sqlite"],
                  "module_absent": io.sqlite_module is None,
                  "imported": "sqlite3" in sys.modules}))
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._antigravity_store(root)
            _write_antigravity_generations(path, [])
            os.utime(path, (self.NOW, self.NOW))
            historical = path.with_name("historical.db")
            historical.write_bytes(path.read_bytes())
            with contextlib.closing(sqlite3.connect(historical)) as con:
                con.execute(
                    "UPDATE trajectory_metadata_blob SET data = ?",
                    (protobuf_bytes_field(6, b"historical"),),
                )
                con.commit()
            os.utime(historical, (self.NOW - 172_800, self.NOW - 172_800))
            for absent in (False, True):
                with self.subTest(absent=absent):
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-B",
                            "-c",
                            script,
                            tmp,
                            str(SERVER_PATH),
                            "yes" if absent else "no",
                            str(self.NOW),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    output = json.loads(result.stdout)
                    self.assertEqual(absent, output["module_absent"])
                    self.assertEqual(not absent, output["imported"])
                    self.assertEqual(not absent, output["sqlite"]["available"])
                    if absent:
                        self.assertIsNone(output["sqlite"]["version"])
                        self.assertIn("_sqlite3", output["sqlite"]["error"])
                    payload = output["payload"]
                    badge = next(h for h in payload["harnesses"] if h["key"] == "antigravity")
                    self.assertTrue(badge["discovered"])
                    self.assertIsNone(badge["error"])
                    rows = {row["sid"]: row for row in payload["sessions"]}
                    self.assertEqual({self.SID, "historical"}, rows.keys())
                    active = rows[self.SID]
                    self.assertTrue(active["active"])
                    self.assertEqual(0, active["rate_per_min"])
                    self.assertIsNone(active["turn"])
                    expected = ["message history", "model", "token accounting"] if absent else []
                    self.assertEqual(expected, active["source_gaps"])
                    self.assertFalse(rows["historical"]["active"])
                    self.assertEqual(["model"] if absent else [], rows["historical"]["source_gaps"])
                    self._notice(
                        payload, "message history, model, token accounting" if absent else None
                    )
