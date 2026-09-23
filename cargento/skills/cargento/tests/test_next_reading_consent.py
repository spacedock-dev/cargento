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
nextData.reading_disclosure = "Sends your goal and evidence to OpenAI and spends Codex capacity.";
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
            out["first"]["html"].index("Sends your goal"),
            out["first"]["html"].index("Allow and check"),
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
