"""Prompt adoption changes the baseline clock, not the observed directions."""

from . import test_next_sessions
from .next_harness import NextPageJsHarness


class PromptAdoptionPageTest(NextPageJsHarness):
    def run_page(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\n" + checks, test_next_sessions.NextSessionsBehaviorTest.FIXTURE
        )

    def test_first_prompt_floor_keeps_a_later_direction_open(self) -> None:
        out = self.run_page("""
const entries=[{type:'user_message',at:20,text:'Later direction'}];
console.log(JSON.stringify(nextCockpitConflictCandidates({at:30,goal_source:'first-prompt',goal_source_at:10},entries).length));
""")
        self.assertEqual(1, out)

    def test_the_prompt_select_carries_its_own_focus_key_per_session(self) -> None:
        """A native select has no open state a redraw could restore, so the lane it needs is
        focus: the select keeps its place by the session's own goal key (owner, 2026-10-02)."""
        out = self.run_page("""
nextData.annotate=true;
const session={harness:'claude',sid:'one',instruction:{label:'asked',text:'Latest prompt',at:20},first_prompt:'First prompt',first_prompt_at:10};
nextCockpitContexts.set('demo\\nclaude:one',{data:{prompt_choices:[{fact_id:'p1',at:10,text:'First prompt',cut:false}]},revision:0});
nextRoute={view:'session',project:'demo',harness:'claude',session:'one'};
const one=nextIntentPromptSelect(session);
console.log(JSON.stringify({one,other:nextIntentPromptSelect({...session,sid:'two'})}));
""")
        assert isinstance(out, dict)
        self.assertIn('data-next-focus="held:claude:one:goal:prompt"', out["one"])
        self.assertNotIn("data-next-cockpit-disclosure", out["one"])
        # Another session's select would carry its own key; this one offers no choices.
        self.assertNotIn("held:claude:one", out["other"])

    def test_goalless_check_posts_the_exact_prompt_and_time(self) -> None:
        out = self.run_page("""
nextData.annotate=true;nextData.reading_check='accepted';
nextData.reading={consent:true,reason:'',tool_output:{codex:['OpenAI']}};
const session=nextData.sessions[0];session.harness='claude';session.annotation_goal='';session.annotation_line_1='';
session.instruction={label:'asked',text:'Build the parser',at:10};
const posts=[];__fetchImpl=async(url,init)=>{if(init&&init.method==='POST')posts.push(JSON.parse(init.body));return {ok:true,json:async()=>init?{ok:true,produced:true}:nextData};};
await nextCockpitAskForReading(session,null);
console.log(JSON.stringify(posts));
""")
        self.assertIsInstance(out, list)
        assert isinstance(out, list)
        self.assertEqual(1, len(out))
        self.assertEqual("latest-prompt", out[0]["adopt"])
        self.assertEqual("Build the parser", out[0]["expected_prompt"])
        self.assertEqual(10, out[0]["expected_prompt_at"])

    def test_retained_adopted_words_are_not_labelled_typed(self) -> None:
        out = self.run_page("""
const row={goal:'Build parser',goal_source:'first-prompt',goal_source_at:10,at:30,revision:1,revision_count:1};
console.log(JSON.stringify({intent:nextIntentSources(row,null,true),revision:nextProjectRevisionLine(row)}));
""")
        assert isinstance(out, dict)
        self.assertIn("from your prompt", out["intent"])
        self.assertNotIn("Typed goal", out["intent"])
        self.assertNotIn("typed", out["revision"])

    def test_non_user_sources_and_missing_times_offer_nothing_to_adopt(self) -> None:
        out = self.run_page("""
nextData.annotate=true;
const cases=[
 {harness:'claude',instruction:{label:'agent',text:'Agent goal',at:10}},
 {harness:'claude',instruction:{label:'earlier',text:'Earlier goal',at:10}},
 {harness:'claude',goal:'Observer goal'},
 {harness:'claude',spacedock:{workflows:[{goal:'Workflow goal'}]}},
 {harness:'codex',title:'yes',prompt_states_work:false,prompt_at:10},
 {harness:'codex',title:'Build parser',prompt_states_work:true,prompt_at:null}
];
console.log(JSON.stringify(cases.map(row=>({candidate:nextPromptCandidate(row),
 menu:nextIntentPromptSelect(row)}))));
""")
        assert isinstance(out, list)
        for row in out[:-1]:
            self.assertIsNone(row["candidate"])
        # A prompt with no time is a candidate no adoption can name.
        self.assertIsNone(out[-1]["candidate"]["at"])
        # The menu lists only what the server published, and nothing was.
        self.assertEqual([""] * len(out), [row["menu"] for row in out])

    def test_old_reading_keeps_its_adopted_evidence_label_after_a_typed_edit(self) -> None:
        out = self.run_page("""
const raw={revision_read:1,revision_read_at:30,goal_source:'first-prompt',goal_source_at:10,
 criteria:{goal:{clause:'Original prompt'},output:{clause:''}}};
const shape=nextCockpitReadingShape(raw,{revision:5,at:90,goal:'New typed goal'},[], '',false);
console.log(JSON.stringify(nextCockpitReadingBaseline(shape)));
""")
        self.assertIn("GOAL FROM YOUR PROMPT", str(out))
        self.assertIn("saved", str(out))
        self.assertNotIn("New typed goal", str(out))

    def test_allow_keeps_the_prompt_shown_by_the_first_press(self) -> None:
        out = self.run_page("""
nextData.annotate=true;nextData.reading_check='accepted';nextData.reading={consent:false,reason:'consent-required'};
const session=nextData.sessions[0];session.harness='claude';session.annotation_goal='';session.annotation_line_1='';
session.instruction={label:'asked',text:'Build the original parser',at:10};
await nextCockpitAskForReading(session,null);
session.instruction={label:'asked',text:'Build a different parser',at:20};
const posts=[];__fetchImpl=async(url,init)=>{if(init&&init.method==='POST')posts.push(JSON.parse(init.body));return {ok:true,json:async()=>init?{ok:true,produced:true}:nextData};};
await nextCockpitAskForReading(session,null,true);
console.log(JSON.stringify(posts));
""")
        assert isinstance(out, list)
        self.assertEqual("Build the original parser", out[0]["expected_prompt"])
        self.assertEqual(10, out[0]["expected_prompt_at"])

    def test_revoked_consent_keeps_adoption_through_allow_and_rejects_changed_prompt(self) -> None:
        out = self.run_page("""
nextData.annotate=true;nextData.reading_check='accepted';nextData.reading={consent:true,reason:'',tool_output:{codex:['OpenAI']}};
const session=nextData.sessions[0];session.annotation_goal='';session.annotation_line_1='';
session.instruction={label:'asked',text:'Build original parser',at:10};
const posts=[];
__fetchImpl=async(url,init)=>{
 if(!init)return {ok:true,json:async()=>nextData};
 posts.push(JSON.parse(init.body));
 return posts.length===1
  ? {ok:false,status:403,json:async()=>({ok:false,produced:false,reading:{consent:false,reason:'consent-required',used:0,limit:12,retry_at:null}})}
  : {ok:false,status:422,json:async()=>({ok:false,produced:false,adoption_refused:true})};
};
await nextCockpitAskForReading(session,null);
const confirmation=nextCockpitReadingControl(session,nextCockpitAnnotation(session),null);
session.instruction={label:'asked',text:'Build changed parser',at:20};
await nextCockpitAskForReading(session,null,true);
console.log(JSON.stringify({posts,confirmation,after:nextCockpitReadingControl(session,nextCockpitAnnotation(session),null)}));
""")
        assert isinstance(out, dict)
        self.assertIn("Allow and analyze", out["confirmation"])
        self.assertEqual("latest-prompt", out["posts"][1].get("adopt"))
        self.assertEqual("Build original parser", out["posts"][1].get("expected_prompt"))
        self.assertEqual(10, out["posts"][1].get("expected_prompt_at"))
        self.assertIn("The prompt or saved goal changed", out["after"])
        self.assertNotIn("Reading received", out["after"])
