"""First-press reading permission is independent of goal-summary permission."""

from __future__ import annotations

from . import test_next_sessions
from .next_harness import NextPageJsHarness


class ReadingConsentPageTest(NextPageJsHarness):
    FIXTURE = test_next_sessions.NextSessionsBehaviorTest.FIXTURE

    def render(self, checks: str) -> object:
        return self._run_page_js("await __settle();\nawait __settle();\n" + checks, self.FIXTURE)

    def test_first_press_asks_then_allow_posts_once_and_off_revokes(self) -> None:
        out = self.render("""
nextData.annotate = true;
nextData.reading_check = "accepted";
nextData.reading = {consent:false,reason:"consent-required",used:0,limit:12};
nextData.sessions[0].annotation_goal = "Ship the parser";
nextData.sessions[0].annotation_revision = 1;
const session = nextData.sessions[0];
const posts = [];
__fetchImpl = async (url,init) => {
 if(init && init.method === "POST"){
  const body = JSON.parse(init.body); posts.push({url,body});
  return {ok:true,json:async()=>body.consent === "off"
   ? {ok:true,produced:false,reading:{consent:false,reason:"consent-required",used:1,limit:12}}
   : {ok:true,produced:true}};
 }
 return {ok:true,json:async()=>nextData};
};
await nextCockpitAskForReading(session, {enabled:false});
const first = {posts:posts.length,html:nextCockpitReadingControl(session,nextCockpitAnnotation(session),null)};
await nextCockpitAskForReading(session, {enabled:false}, true);
const second = posts.slice();
await nextCockpitReadingOff();
console.log(JSON.stringify({first,second,posts,policy:nextData.reading}));
""")
        assert isinstance(out, dict)
        self.assertEqual(0, out["first"]["posts"])
        self.assertLess(
            # The server's route for this Claude Code row names its receiver.
            out["first"]["html"].index("so Codex reads this session"),
            out["first"]["html"].index("Allow and analyze"),
        )
        self.assertEqual(1, len(out["second"]))
        self.assertIs(True, out["second"][0]["body"]["allow"])
        self.assertEqual("/api/reading", out["second"][0]["url"])
        self.assertEqual("off", out["posts"][1]["body"]["consent"])
        self.assertFalse(out["policy"]["consent"])

    def test_off_switch_refusal_and_reentry_absence_are_true_without_departures(self) -> None:
        out = self.render("""
nextData.annotate = true;
nextData.reading_check = "accepted";
nextData.reading = {consent:true,reason:"run-disabled",used:0,limit:12};
nextData.unasked_off_reason = "run-disabled";
const session = nextData.sessions[0];
session.annotation_goal = "Ship parser";
navigateNext({view:"session",project:session.project,harness:session.harness,session:session.sid});
console.log(JSON.stringify({html:__els.app.innerHTML,lane:nextCockpitUnaskedPart(session)}));
""")
        assert isinstance(out, dict)
        self.assertIn("--no-harness-usage", out["lane"])
        self.assertNotIn("Start with --unasked-readings", out["lane"])
        self.assertIn("Terminal raise: off for this run", out["html"])
        self.assertEqual(1, out["html"].count("Terminal raise: off for this run"))
        self.assertNotIn("Start with --observer-model", out["html"])

    def test_policy_refusal_renders_once_and_clears_when_policy_recovers(self) -> None:
        out = self.render("""
nextData.annotate = true;
nextData.reading_check = "accepted";
const session = nextData.sessions[0];
session.annotation_goal = "Ship parser";
session.annotation_revision = 1;
const results = [];
for(const [reason,status,refusal] of [
 ["daily-cap",429,"The daily reading limit is reached."],
 ["store-unavailable",503,"Reading permission or its daily budget could not be read or saved."]
]){
 nextCockpitReadingRequests.clear();
 nextData.reading = {consent:true,reason:"",used:11,limit:12,tool_output:{codex:["OpenAI"]}};
 const refusedPolicy = reason === "daily-cap"
  ? {consent:true,reason,used:12,limit:12,retry_at:1800000000}
  : {consent:false,reason,used:0,limit:12,retry_at:null};
 __fetchImpl = async () => ({ok:false,status,json:async()=>({ok:false,produced:false,reading:refusedPolicy})});
 await nextCockpitAskForReading(session,null);
 const refused = nextCockpitReadingControl(session,nextCockpitAnnotation(session),null,false);
 nextData.reading = {consent:true,reason:"",used:0,limit:12,tool_output:{codex:["OpenAI"]}};
 const recovered = nextCockpitReadingControl(session,nextCockpitAnnotation(session),null,false);
 results.push({reason,count:refused.split(esc(refusal)).length-1,
  announced:refused.includes('role="status"'),stale:recovered.includes(esc(refusal)),
  disabled:recovered.includes('aria-disabled="true"'),primary:recovered.includes('next-action--primary')});
}
console.log(JSON.stringify(results));
""")
        assert isinstance(out, list)
        for result in out:
            with self.subTest(reason=result["reason"]):
                self.assertEqual(1, result["count"])
                self.assertTrue(result["announced"])
                self.assertFalse(result["stale"])
                self.assertFalse(result["disabled"])
                self.assertFalse(result["primary"])

    def test_consent_revoked_elsewhere_returns_press_to_allow_without_stale_message(self) -> None:
        out = self.render("""
nextData.annotate = true;
nextData.reading_check = "accepted";
nextData.reading = {consent:true,reason:"",used:0,limit:12,tool_output:{codex:["OpenAI"]}};
const session = nextData.sessions[0];
session.annotation_goal = "Ship parser";
session.annotation_revision = 1;
__fetchImpl = async () => ({ok:false,status:403,json:async()=>({ok:false,produced:false,
 reading:{consent:false,reason:"consent-required",used:0,limit:12}})});
await nextCockpitAskForReading(session,null);
const refused = nextCockpitReadingControl(session,nextCockpitAnnotation(session),null);
nextData.reading = {consent:true,reason:"",used:0,limit:12,tool_output:{codex:["OpenAI"]}};
const recovered = nextCockpitReadingControl(session,nextCockpitAnnotation(session),null);
console.log(JSON.stringify({refused,recovered}));
""")
        assert isinstance(out, dict)
        self.assertIn("Allow and analyze", out["refused"])
        self.assertNotIn("Readings are off", out["recovered"])
        self.assertNotIn("Allow and analyze", out["recovered"])
