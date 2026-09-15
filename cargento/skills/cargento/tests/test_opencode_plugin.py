"""Exercise the shipped passive callback and its real loopback transport."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cargento_runtime import events

from . import support

PLUGIN = support.SERVER_PATH.parent / "opencode_plugin.js"
SID = "ses_" + "a" * 26
OTHER = "ses_" + "a" * 25 + "b"
TOKEN = "test-capability"  # noqa: S105 — local test sentinel
NODE = shutil.which("node")
RUNNER = r"""
import {readFileSync, writeFileSync, unlinkSync} from "node:fs";
import {pathToFileURL} from "node:url";
const input = JSON.parse(readFileSync(0, "utf8"));
const module = await import(pathToFileURL(input.plugin));
const hooks = await module.CargentoPlugin({});
const times = [];
for (const step of input.steps) {
  if ("state" in step) {
    if (step.state === null) { try { unlinkSync(input.state); } catch {} }
    else writeFileSync(input.state, typeof step.state === "string" ? step.state : JSON.stringify(step.state));
  }
  const start = performance.now();
  await hooks.event({event: step.event});
  times.push(performance.now() - start);
  await new Promise(resolve => setTimeout(resolve, step.delay ?? 60));
}
await new Promise(resolve => setTimeout(resolve, input.settle ?? 350));
process.stdout.write(JSON.stringify({hooks: Object.keys(hooks), times}));
"""


def native(kind: str, request: str = "req-one", sid: str = SID) -> dict[str, Any]:
    return {
        "type": kind,
        "properties": {
            "sessionID": sid,
            "id": request,
            "requestID": request,
            "reply": "once",
            "metadata": {"command": "secret-command"},
            "patterns": ["private-path"],
        },
    }


@unittest.skipUnless(NODE, "node is required to exercise the JavaScript adapter")
class OpenCodePluginTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.records: list[dict[str, Any]] = []
        records = self.records
        self.response_delay = 0.0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                records.append(
                    {
                        "path": self.path,
                        "token": self.headers.get("X-Cargento-Capability"),
                        "body": json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                    }
                )
                time.sleep(owner.response_delay)
                self.send_response(204)
                self.end_headers()

            def log_message(self, _format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port
        self.state = self.home / f"cargento-{self.port}.json"
        self.state.write_text(json.dumps({"capabilities": {"opencode": TOKEN}}))

    def run_plugin(self, steps: list[dict[str, Any]], **options: Any) -> dict[str, Any]:
        self.assertTrue(PLUGIN.is_file(), "the per-project OpenCode adapter is not shipped")
        plugin = self.home / "plugin.mjs"
        shutil.copyfile(PLUGIN, plugin)
        payload = {"plugin": str(plugin), "state": str(self.state), "steps": steps, **options}
        runner = self.home / "runner.mjs"
        runner.write_text(RUNNER)
        result = subprocess.run(
            [str(NODE), str(runner)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={**os.environ, "CARGENTO_HOME": str(self.home), "CARGENTO_PORT": str(self.port)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        observed: dict[str, Any] = json.loads(result.stdout)
        return observed

    def test_a_parent_permission_wait_clears_only_after_its_last_answer(self) -> None:
        result = self.run_plugin(
            [
                {"event": native("permission.asked")},
                {"event": native("permission.asked")},
                {"event": native("permission.asked", "req-two")},
                {"event": native("permission.replied", "unknown")},
                {"event": native("session.status")},
                {"event": native("permission.replied")},
                {"event": native("permission.replied", "req-two")},
                {"event": native("permission.replied", "req-two")},
            ]
        )
        self.assertEqual(["event"], result["hooks"])
        self.assertEqual(
            ["input_requested", "input_resolved"], [r["body"]["event"] for r in self.records]
        )
        self.assertEqual({"/api/events/opencode"}, {r["path"] for r in self.records})
        for record in self.records:
            self.assertEqual(TOKEN, record["token"])
            self.assertEqual({"v", "event", "session_id"}, set(record["body"]))
            self.assertEqual(SID, record["body"]["session_id"])
        self.assertNotIn("secret-command", json.dumps(self.records))

    def test_two_whole_ids_sharing_a_prefix_reach_distinct_overlay_keys(self) -> None:
        self.run_plugin(
            [
                {"event": native("permission.asked")},
                {"event": native("permission.asked", sid=OTHER)},
                {"event": native("permission.replied")},
            ]
        )
        config = support.make_config()
        ledger = []
        for seq, record in enumerate(self.records):
            parsed = events.parse(
                "opencode", record["body"], arrival_seq=seq + 1, config=config, now=1000
            )
            self.assertIsInstance(parsed, events.Event)
            assert isinstance(parsed, events.Event)
            ledger.append(events.overlay_for(parsed, config=config))
        for sid, expected in ((SID, "working"), (OTHER, "needs_input")):
            rows = [o for o in ledger if o is not None and o.sid == sid]
            self.assertEqual(expected, events.reduce_overlays(rows, now=1000)["state"])

    def test_invalid_ids_cannot_reach_a_session(self) -> None:
        for sid in ("../" + SID, SID[:-1], SID + "a", "ses_" + "é" * 26, "ses_" + "a" * 25 + "/"):
            with self.subTest(sid=sid):
                self.assertIsNone(events.normalize_session_id("opencode", sid))
