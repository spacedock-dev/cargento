from __future__ import annotations

import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextNotificationBehaviorTest(NextPageJsHarness):
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
