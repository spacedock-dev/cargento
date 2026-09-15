"""Execute the shipped Pi subscriber, not a second envelope implementation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from typing import Any

from cargento_runtime import events, observation, sessions

from . import SKILL_DIR, support
from .next_harness import NextPageJsHarness

SESSION = "abcdef12-3456-7890-abcd-ef1234567890"


@unittest.skipUnless(shutil.which("node"), "node not available")
class PiExtensionTest(unittest.TestCase):
    def run_adapter(self, action: str) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as directory:
            code = (
                """
import {createServer} from 'node:http';
import {writeFile, unlink} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const messages = [], callbacks = {};
const server = createServer((req,res) => {
  let raw=''; req.on('data',chunk=>raw+=chunk);
  req.on('end',()=>{messages.push({path:req.url, token:req.headers['x-cargento-capability'],
    body:JSON.parse(raw)}); res.end('{}');});
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
process.env.CARGENTO_PORT=String(server.address().port);
const state=process.env.CARGENTO_HOME+'/cargento-'+process.env.CARGENTO_PORT+'.json';
await writeFile(state,JSON.stringify({capabilities:{pi:'a'.repeat(64)}}));
const adapter=await import(pathToFileURL(process.argv[1]));
adapter.default({on:(name,fn)=>callbacks[name]=fn});
const ctx={sessionManager:{getSessionId:()=> 'abcdef12-3456-7890-abcd-ef1234567890'}};
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const emit=(name,kind='select',extra={})=>callbacks[name]({type:name,reason:'ui_prompt',kind,
  title:'private title', answer:'private answer',cwd:'/private/path',...extra},ctx);
"""
                + action
                + """
await pause(150);
console.log(JSON.stringify({messages, subscriptions:Object.keys(callbacks)}));
server.closeAllConnections(); await new Promise(resolve=>server.close(resolve));
"""
            )
            result = subprocess.run(
                [
                    str(shutil.which("node")),
                    "--input-type=module",
                    "-e",
                    code,
                    str(SKILL_DIR / "pi_extension.js"),
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                env={**os.environ, "CARGENTO_HOME": directory},
            )
            self.assertEqual(0, result.returncode, result.stderr)
            return json.loads(result.stdout)  # type: ignore[no-any-return]

    def test_measured_pair_for_all_five_kinds_omits_native_contents(self) -> None:
        result = self.run_adapter("""
for(const kind of ['select','confirm','input','editor','custom']) {
  emit('ui_prompt_start',kind); await pause(50);
  emit('ui_prompt_end',kind); await pause(50);
}
""")
        self.assertEqual(["ui_prompt_start", "ui_prompt_end"], result["subscriptions"])
        messages = result["messages"]
        self.assertEqual(10, len(messages))
        for index, message in enumerate(messages):
            self.assertEqual("/api/events/pi", message["path"])
            self.assertEqual("a" * 64, message["token"])
            body = message["body"]
            self.assertEqual(SESSION, body["session_id"])
            self.assertEqual("input_resolved" if index % 2 else "input_requested", body["event"])
            self.assertEqual(
                {"v", "event", "session_id", "timestamp", "source_instance_id", "source_sequence"},
                set(body),
            )
            self.assertEqual(index + 1, body["source_sequence"])
            parsed = events.parse(
                "pi",
                body,
                arrival_seq=index + 1,
                config=support.make_config(),
                now=support.SERVER_STARTED,
            )
            self.assertIsInstance(parsed, events.Event)
            assert isinstance(parsed, events.Event)
            self.assertEqual(SESSION, parsed.sid)
            overlay = events.overlay_for(parsed, config=support.make_config())
            assert overlay is not None
            patch = events.reduce_overlays([overlay], now=support.SERVER_STARTED)
            self.assertEqual("working" if index % 2 else "needs_input", patch["state"])

    def test_invalid_native_kind_identity_and_reason_do_not_send(self) -> None:
        result = self.run_adapter("""
emit('ui_prompt_start','trust');
emit('ui_prompt_start','select',{reason:'other'});
emit('ui_prompt_start','select',{type:'unknown'});
for(const id of ['', '../../private', '-'.repeat(36), 'a'.repeat(36), null]) {
  ctx.sessionManager.getSessionId=()=>id; emit('ui_prompt_start');
}
""")
        self.assertEqual([], result["messages"])

    def test_missing_malformed_oversized_and_disabled_state_do_not_send(self) -> None:
        result = self.run_adapter("""
await unlink(state); emit('ui_prompt_start'); await pause(30);
for(const value of ['invalid', '{}', 'null', ' '.repeat(65537),
  JSON.stringify({capabilities:{pi:'bad\\nheader'}}),
  JSON.stringify({capabilities:{opencode:'a'.repeat(64)}})]) {
  await writeFile(state,value); emit('ui_prompt_start'); await pause(30);
}
""")
        self.assertEqual([], result["messages"])

    def test_delayed_end_cannot_overtake_later_start(self) -> None:
        result = self.run_adapter("""
server.removeAllListeners('request');
server.on('request',(req,res)=>{let raw=''; req.on('data',c=>raw+=c);
  req.on('end',()=>{messages.push(JSON.parse(raw)); setTimeout(()=>res.end('{}'),80);});});
emit('ui_prompt_start'); await pause(110);
emit('ui_prompt_end'); emit('ui_prompt_start'); await pause(220);
""")
        self.assertEqual(
            ["input_requested", "input_resolved", "input_requested"],
            [item["event"] for item in result["messages"]],
        )
        self.assertEqual([1, 2, 3], [item["source_sequence"] for item in result["messages"]])

    def test_hanging_endpoint_bounds_burst_and_never_awaits_ui_callback(self) -> None:
        result = self.run_adapter("""
server.removeAllListeners('request');
server.on('request',(req,_res)=>{let raw=''; req.on('data',c=>raw+=c);
  req.on('end',()=>messages.push(JSON.parse(raw)));});
if(emit('ui_prompt_start') !== undefined) throw Error('UI callback awaited transport');
await pause(50);
for(let i=0;i<1000;i++) { emit('ui_prompt_end'); emit('ui_prompt_start'); }
emit('ui_prompt_end'); await pause(1100);
""")
        self.assertEqual(
            ["input_requested", "input_resolved"], [item["event"] for item in result["messages"]]
        )

    def test_stale_capability_response_is_not_retried_or_redirected(self) -> None:
        result = self.run_adapter("""
server.removeAllListeners('request');
server.on('request',(req,res)=>{messages.push(req.url);
  res.writeHead(403,{Location:'http://192.0.2.1/never'}); res.end();});
emit('ui_prompt_start'); await pause(650);
""")
        self.assertEqual(["/api/events/pi"], result["messages"])


class PiPublicationTest(support.RuntimeTestCase):
    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_person_sees_the_observed_wait_duration_in_the_sessions_row(self) -> None:
        app = support.build_app()
        now = support.SERVER_STARTED
        coordinator = observation.Observation(app, clock=lambda: now)
        app.overlays = coordinator
        self.assertEqual(
            "accepted",
            coordinator.submit(
                "pi",
                {
                    "v": 1,
                    "event": "input_requested",
                    "session_id": SESSION,
                },
            ),
        )
        row = sessions.base_session("pi", SESSION, "controlled")
        app._apply_overlays([row], now=now + 95)
        result = NextPageJsHarness()._run_page_js(
            f"const source={json.dumps(row)};"
            f"const session=nextObservedSession(source,[],{{reports_needs_input:true}},{now + 95},1);"
            "console.log(JSON.stringify({html:nextOperationsObservedRow(session,source,new Map(),[],false)}));"
        )
        self.assertIn("Waiting for input · 1m", result["html"])
        coordinator.submit("pi", {"v": 1, "event": "input_resolved", "session_id": SESSION})
        row = sessions.base_session("pi", SESSION, "controlled")
        app._apply_overlays([row], now=now)
        self.assertIsNone(row["state_detail"])

    def test_absent_disabled_and_restarted_reporter_are_unknown(self) -> None:
        app = support.build_app()
        now = support.SERVER_STARTED
        for harness in ("pi", "opencode"):
            for attached in (False, True):
                with self.subTest(harness=harness, attached=attached):
                    app.overlays = (
                        observation.Observation(app, clock=lambda: now) if attached else None
                    )
                    row = sessions.base_session(harness, SESSION, "controlled")
                    app._apply_overlays([row], now=now)
                    self.assertIn("block state", row["source_gaps"])

    def test_accepted_pi_pair_earns_coverage_but_heartbeat_does_not(self) -> None:
        app = support.build_app()
        now = support.SERVER_STARTED
        coordinator = observation.Observation(app, clock=lambda: now)
        app.overlays = coordinator
        for native, blocked, known in (
            ("store_changed", False, False),
            ("input_requested", True, True),
            ("input_resolved", False, True),
        ):
            self.assertEqual(
                "accepted",
                coordinator.submit(
                    "pi",
                    {
                        "v": 1,
                        "event": native,
                        "session_id": SESSION,
                    },
                ),
            )
            row = sessions.base_session("pi", SESSION, "controlled")
            app._apply_overlays([row], now=now)
            self.assertEqual(blocked, row["state"] == "needs_input")
            self.assertEqual(known, "block state" not in row["source_gaps"])
        app.overlays = observation.Observation(app, clock=lambda: now)
        row = sessions.base_session("pi", SESSION, "controlled")
        app._apply_overlays([row], now=now)
        self.assertIn("block state", row["source_gaps"])
