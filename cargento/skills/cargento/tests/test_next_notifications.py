from __future__ import annotations

import shutil
import unittest
from typing import Any

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextNotificationBehaviorTest(NextPageJsHarness):
    def test_repeated_quiet_crossings_wait_ten_minutes_without_delaying_questions(self) -> None:
        out = self._run_page_js(
            """
let now = 0;
Date.now = () => now;
__notifyPermission = "granted";
const row = (state, sid = "s1", harness = "claude") => ({
  harness, sid, project: "repo", state, active: state !== "idle"
});
const send = (seconds, sessions, asks = []) => {
  now = seconds * 1000;
  nextSyncNotifications({native_notify: "", sessions, ask: true, asks,
    harnesses: [{key: "claude", label: "Claude"}]});
  return __notifications.length;
};
const counts = [];
counts.push(send(0, [row("working")]));
counts.push(send(0, [row("idle")]));
counts.push(send(100, [row("working")]));
counts.push(send(200, [row("idle")]));
counts.push(send(300, [row("working")]));
counts.push(send(400, [row("idle")]));
counts.push(send(599, [row("working")]));
counts.push(send(599.999, [row("idle")]));
counts.push(send(600, [row("idle")])); // Suppressed edges still update observed state.
counts.push(send(600, [row("working")]));
counts.push(send(600, [row("idle")])); // Inclusive boundary after a new crossing.
send(601, [row("working")]);
send(602, [row("needs_input")], [{id: "ask", question: "Ship?", harness: "claude"}]);
const questions = __notifications.slice(2).map(n => n.title);
send(603, [row("working"), row("working", "s2"), row("working", "s1", "codex")]);
send(604, [row("idle"), row("idle", "s2"), row("idle", "s1", "codex")]);
const separate = __notifications.slice(4).map(n => n.tag);
send(605, []);
send(606, [row("working")]);
send(607, [row("idle")]);
console.log(JSON.stringify({counts, questions, separate, final: __notifications.length}));
"""
        )
        self.assertEqual([0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2], out["counts"])
        self.assertEqual(["Claude is waiting on you", "Claude is asking you"], out["questions"])
        self.assertEqual(["claude:s2", "codex:s1"], out["separate"])
        self.assertEqual(6, out["final"])

    def test_an_unissued_quiet_nudge_does_not_start_the_repeat_floor(self) -> None:
        out = self._run_page_js(
            """
Date.now = () => 1000000;
const send = (state, native = "") => nextSyncNotifications({native_notify: native,
  sessions: [{harness: "claude", sid: "unissued", state, active: state !== "idle"}], asks: []});
__notifyPermission = "denied";
send("working"); send("idle");
__notifyPermission = "granted";
send("working", "osascript"); send("idle", "osascript");
const realNotification = Notification;
Notification = function(){ throw new Error("permission revoked"); };
Notification.permission = "granted";
send("working"); send("idle");
Notification = realNotification;
send("working"); send("idle");
send("working"); send("idle");
console.log(JSON.stringify(__notifications.map(n => n.title)));
"""
        )
        self.assertEqual(["claude has gone quiet"], out)

    def test_browser_notifications_cover_gate_transitions_the_server_missed(self) -> None:
        out = self._run_page_js(
            """
const blocked = {
  harness:"claude", sid:"12345678", project:"proj", state:"needs_input",
  state_detail:"open question", active:true
};
const idle = {...blocked, state:"idle", state_detail:"awaiting your message"};
const payload = (sessions, native) => ({
  native_notify:native, harnesses:[{key:"claude", label:"Claude"}], sessions,
  asks:[], ask:true
});
const reset = permission => {
  __notifications = []; __notifyPermission = permission;
  nextNotifyState = new Map(); nextNotifyPrimed = false; nextNotifiedAsks = new Set();
  nextQuietNudgedAt.clear();
};
const out = {};

reset("granted");
nextSyncNotifications(payload([idle], "osascript"));
nextSyncNotifications(payload([blocked], "osascript"));
out.nativeOwnsIt = __notifications.length;

reset("granted");
nextSyncNotifications(payload([idle], ""));
nextSyncNotifications(payload([blocked], ""));
out.browserFired = __notifications.length;
out.title = __notifications[0] && __notifications[0].title;
out.body = __notifications[0] && __notifications[0].body;
out.tag = __notifications[0] && __notifications[0].tag;
nextSyncNotifications(payload([blocked], ""));
out.noRepeat = __notifications.length;
nextSyncNotifications(payload([idle], ""));
nextSyncNotifications(payload([blocked], ""));
out.refired = __notifications.length;

reset("granted");
nextSyncNotifications(payload([blocked], ""));
out.primed = __notifications.length;
console.log(JSON.stringify(out));
"""
        )

        self.assertEqual(0, out["nativeOwnsIt"])
        self.assertEqual(1, out["browserFired"])
        self.assertEqual("Claude is waiting on you", out["title"])
        self.assertEqual("[proj] open question", out["body"])
        self.assertEqual("claude:12345678", out["tag"])
        self.assertEqual(1, out["noRepeat"])
        self.assertEqual(2, out["refired"])
        self.assertEqual(0, out["primed"])

    def test_a_browser_nudge_lands_when_a_working_session_falls_quiet(self) -> None:
        # The transition the native lane already popups for on macOS, through
        # Claude's own `idle_prompt`. A reader on Linux or Windows has no native
        # backend, so before this the working→idle edge raised nothing at all and
        # they had to keep looking at the tab.
        out = self._run_page_js(
            """
const working = {
  harness:"claude", sid:"12345678", project:"proj", state:"working",
  state_detail:"generating…", active:true
};
const quiet = {...working, state:"idle", state_detail:"awaiting your message"};
const blocked = {...working, state:"needs_input", state_detail:"open question"};
const payload = (sessions, native) => ({
  native_notify:native, harnesses:[{key:"claude", label:"Claude Code"}], sessions,
  asks:[], ask:true
});
const reset = permission => {
  __notifications = []; __notifyPermission = permission;
  nextNotifyState = new Map(); nextNotifyPrimed = false; nextNotifiedAsks = new Set();
  nextQuietNudgedAt.clear();
};
const out = {};

reset("granted");
nextSyncNotifications(payload([working], ""));
out.nothingForWorking = __notifications.length;
nextSyncNotifications(payload([quiet], ""));
out.fired = __notifications.length;
out.title = __notifications[0] && __notifications[0].title;
out.body = __notifications[0] && __notifications[0].body;
out.tag = __notifications[0] && __notifications[0].tag;
nextSyncNotifications(payload([quiet], ""));
out.noRepeat = __notifications.length;

reset("granted");
nextSyncNotifications(payload([working], "osascript"));
nextSyncNotifications(payload([quiet], "osascript"));
out.nativeOwnsIt = __notifications.length;

// A first sighting of an idle session is not a transition anyone watched.
reset("granted");
nextSyncNotifications(payload([quiet], ""));
nextSyncNotifications(payload([quiet], ""));
out.firstSighting = __notifications.length;

// An answered question is not a nudge: the reader has just been there.
reset("granted");
nextSyncNotifications(payload([blocked], ""));
const afterGate = __notifications.length;
nextSyncNotifications(payload([quiet], ""));
out.gateToQuiet = __notifications.length - afterGate;

// The instrumented shape, and the one a default install actually takes: a
// `turn_stopped` overlay publishes state idle with state_detail null and
// active FALSE, and both shipped hook manifests declare `Stop`. This is also
// the only arm that exercises edge.detail, since state_detail is null here.
reset("granted");
nextSyncNotifications(payload([working], ""));
nextSyncNotifications(payload([{...quiet, state_detail:null, active:false}], ""));
out.instrumented = __notifications.length;
out.instrumentedTitle = __notifications[0] && __notifications[0].title;
out.instrumentedBody = __notifications[0] && __notifications[0].body;

// An inactive row still needs a `working` sighting first: a first sighting of
// an idle, inactive row is nobody's transition.
reset("granted");
nextSyncNotifications(payload([{...quiet, active:false}], ""));
nextSyncNotifications(payload([{...quiet, active:false}], ""));
out.inactiveFirstSighting = __notifications.length;
console.log(JSON.stringify(out));
"""
        )

        self.assertEqual(0, out["nothingForWorking"])
        self.assertEqual(1, out["fired"])
        self.assertEqual("Claude Code has gone quiet", out["title"])
        self.assertEqual("[proj] awaiting your message", out["body"])
        self.assertEqual("claude:12345678", out["tag"])
        self.assertEqual(1, out["noRepeat"])
        self.assertEqual(0, out["nativeOwnsIt"])
        self.assertEqual(0, out["firstSighting"])
        self.assertEqual(0, out["gateToQuiet"])
        self.assertEqual(1, out["instrumented"])
        self.assertEqual("Claude Code has gone quiet", out["instrumentedTitle"])
        # From edge.detail, not state_detail: the idle overlay patch nulls it.
        self.assertEqual("[proj] awaiting your message", out["instrumentedBody"])
        self.assertEqual(0, out["inactiveFirstSighting"])

    def test_browser_notifications_cover_arriving_asks_once(self) -> None:
        out = self._run_page_js(
            """
const ask = id => ({
  id, harness:"claude", project:"repo/proj", question:"Ship it?", options:["yes", "no"]
});
const payload = (asks, native) => ({
  native_notify:native, harnesses:[{key:"claude", label:"Claude"}], sessions:[],
  asks, ask:true
});
const reset = permission => {
  __notifications = []; __notifyPermission = permission;
  nextNotifyState = new Map(); nextNotifyPrimed = false; nextNotifiedAsks = new Set();
  nextQuietNudgedAt.clear();
};
const out = {};

reset("granted");
nextSyncNotifications(payload([ask("a1")], "osascript"));
out.nativeOwnsIt = __notifications.length;

reset("granted");
nextSyncNotifications(payload([ask("a1")], ""));
out.firstPaint = __notifications.length;
out.title = __notifications[0] && __notifications[0].title;
out.body = __notifications[0] && __notifications[0].body;
out.tag = __notifications[0] && __notifications[0].tag;
nextSyncNotifications(payload([ask("a1")], ""));
out.noRepeat = __notifications.length;
nextSyncNotifications(payload([ask("a1"), ask("a2")], ""));
out.second = __notifications.length;
out.secondTag = __notifications[1] && __notifications[1].tag;

reset("granted");
nextSyncNotifications(payload([ask("b1"), ask("b2")], ""));
out.burst = __notifications.length;
out.burstTitle = __notifications[0] && __notifications[0].title;
console.log(JSON.stringify(out));
"""
        )

        self.assertEqual(0, out["nativeOwnsIt"])
        self.assertEqual(1, out["firstPaint"])
        self.assertEqual("Claude is asking you", out["title"])
        self.assertEqual("Ship it? · repo/proj", out["body"])
        self.assertEqual("cargento-ask:a1", out["tag"])
        self.assertEqual(1, out["noRepeat"])
        self.assertEqual(2, out["second"])
        self.assertEqual("cargento-ask:a2", out["secondTag"])
        self.assertEqual(1, out["burst"])
        self.assertEqual("2 questions are waiting for your answer", out["burstTitle"])

    def test_notification_permission_control_reflects_state(self) -> None:
        out = self._run_page_js(
            """
const payload = native => ({
  native_notify:native, harnesses:[], sessions:[], asks:[], ask:true,
  summary:{working:0, needs_input:0}
});
const out = {};
__notifyPermission = "default"; out.prompt = nextNotifyControl(payload(""));
__notifyPermission = "denied"; out.denied = nextNotifyControl(payload(""));
__notifyPermission = "granted"; out.granted = nextNotifyControl(payload(""));
__notifyPermission = "default"; out.native = nextNotifyControl(payload("osascript"));

nextData = payload("");
renderNext();
out.buttonBefore = __els.app.innerHTML.includes("Enable notifications");
nextRequestNotifyPermission();
out.buttonWhilePending = __els.app.innerHTML.includes("Enable notifications");
await __settle(); await __settle();
out.buttonAfter = __els.app.innerHTML.includes("Enable notifications");
console.log(JSON.stringify(out));
""",
            '__els.app = {innerHTML: "", querySelectorAll(){ return []; }, '
            "insertAdjacentElement(){}};\n",
        )

        self.assertIn("Enable notifications", out["prompt"])
        self.assertIn("notifications blocked", out["denied"])
        self.assertEqual("", out["granted"])
        self.assertEqual("", out["native"])
        self.assertTrue(out["buttonBefore"])
        self.assertTrue(out["buttonWhilePending"])
        self.assertFalse(out["buttonAfter"])

    def test_page_works_without_the_notification_api(self) -> None:
        out = self._run_page_js(
            """
Notification = undefined;
const payload = {native_notify:"", harnesses:[], sessions:[], asks:[], ask:true};
nextData = payload;
renderNext();
nextRequestNotifyPermission();
console.log(JSON.stringify({
  permission:nextNotifyPermission(), control:nextNotifyControl(payload),
  rendered:!!__els.app.innerHTML
}));
""",
            '__els.app = {innerHTML: "", querySelectorAll(){ return []; }, '
            "insertAdjacentElement(){}};\n",
        )

        self.assertEqual("unsupported", out["permission"])
        self.assertEqual("", out["control"])
        self.assertTrue(out["rendered"])


class BrowserLaneReportTest(NextPageJsHarness):
    """DEC-19's report, and the three things it must not do.

    The byte pins notice any edit to this file; they cannot tell a report that
    names no session from one that does, or a self-healing resend from a
    heartbeat. This is the test that can.
    """

    def _report(self, script: str) -> dict[str, Any]:
        out = self._run_page_js(
            """
__fetchImpl = () => Promise.resolve({ok:true, json:() => Promise.resolve({ok:true})});
let __gen = 1000;
const payload = lane => ({
  native_notify:"", harnesses:[], sessions:[], asks:[], ask:true,
  browser_lane:lane, generated:(__gen += 10), summary:{working:0, needs_input:0}
});
const out = {};
"""
            + script
            + """
out.calls = __fetchCalls.filter(call => String(call[0]) === "/api/lane").map(call =>
  JSON.parse(String((call[1] || {}).body || "null")));
console.log(JSON.stringify(out));
""",
            '__els.app = {innerHTML: "", querySelectorAll(){ return []; }, '
            "insertAdjacentElement(){}};\n",
        )
        assert isinstance(out, dict)
        return out

    def test_a_granted_tab_reports_once_and_stops_when_the_payload_agrees(self) -> None:
        out = self._report(
            """
__notifyPermission = "granted";
nextSyncNotifications(payload(false));
await __settle();
nextSyncNotifications(payload(true));
await __settle();
nextSyncNotifications(payload(true));
await __settle();
"""
        )

        self.assertEqual(1, len(out["calls"]))
        self.assertEqual({"supported": True, "permission": "granted"}, out["calls"][0])

    def test_the_report_names_no_session(self) -> None:
        # The route refuses one with a 400. This is the other half: the page
        # must not send one, or every reader sees a refusal in the console.
        out = self._report(
            """
__notifyPermission = "granted";
nextSyncNotifications(payload(false));
await __settle();
"""
        )

        for key in ("sid", "session", "session_id", "harness", "resume_id"):
            with self.subTest(key=key):
                self.assertNotIn(key, out["calls"][0])

    def test_a_tab_without_permission_reports_nothing(self) -> None:
        # Only a working lane is a report. A tab saying it has none would say
        # nothing true about a board other tabs may be watching.
        out = self._report(
            """
__notifyPermission = "denied";
nextSyncNotifications(payload(false));
await __settle();
__notifyPermission = "default";
nextSyncNotifications(payload(false));
await __settle();
"""
        )

        self.assertEqual([], out["calls"])

    def test_a_payload_that_forgets_the_lane_is_reported_to_again(self) -> None:
        # The restart case, without a heartbeat and without a boot token: the
        # page has a lane and the payload says none has been reported, so the
        # disagreement is what resends.
        out = self._report(
            """
__notifyPermission = "granted";
nextSyncNotifications(payload(false));
await __settle();
nextSyncNotifications(payload(true));
await __settle();
nextSyncNotifications(payload(false));
await __settle();
"""
        )

        self.assertEqual(2, len(out["calls"]))

    def test_many_renders_of_one_collection_report_once(self) -> None:
        # The defect: the page renders many times per collection, and the
        # server's answer cannot appear until the next payload, so gating only
        # on `browser_lane` made every render between the post and that payload
        # post again. Same payload object, three renders.
        out = self._report(
            """
__notifyPermission = "granted";
const one = payload(false);
nextSyncNotifications(one);
await __settle();
nextSyncNotifications(one);
await __settle();
nextSyncNotifications(one);
await __settle();
"""
        )

        self.assertEqual(1, len(out["calls"]))

    def test_a_payload_with_no_lane_key_at_all_does_not_report_forever(self) -> None:
        # What the server used to publish: the key lived on the rows and not at
        # the top of the payload, so `payload.browser_lane` read `undefined` on
        # every poll and the page reported on every one of them.
        out = self._report(
            """
__notifyPermission = "granted";
for(let i = 0; i < 6; i++){
  const p = payload(false);
  delete p.browser_lane;
  nextSyncNotifications(p);
  await __settle();
}
"""
        )

        self.assertLessEqual(len(out["calls"]), 3)

    def test_a_server_that_never_accepts_the_report_is_given_up_on(self) -> None:
        out = self._report(
            """
__fetchImpl = () => Promise.resolve({ok:false, status:500});
__notifyPermission = "granted";
for(let i = 0; i < 10; i++){
  nextSyncNotifications(payload(false));
  await __settle();
}
"""
        )

        self.assertEqual(3, len(out["calls"]))
