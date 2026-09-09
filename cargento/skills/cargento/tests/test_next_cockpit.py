from __future__ import annotations

import shutil
import unittest

from .next_harness import NextPageJsHarness, storage_prelude


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextCockpitCompositionTest(NextPageJsHarness):
    FIXTURE = """
location.hash = "#n=project:cargento";
__els.app = {innerHTML: ""};
const __dashboard = {
  generated: 105, rate_window_sec: 600, window_hours: 24,
  summary: {working: 1, needs_input: 0},
  harnesses: [{key: "codex", label: "Codex"}, {key:"pi", label:"Pi"},
    {key:"claude", label:"Claude"}],
  sessions: [{sid: "focus-1", harness: "codex", project: "cargento",
    project_key: "spacedock-research/cargento", state: "working", active: true,
    last_activity: 104, title: "Shape project cockpit", subagent_hierarchy: [
      {name:"Banach", observer_sid:"child-b", depth:1,
        assignment:"Fix the completion guard", assignment_status:"structured dispatch artifact",
        workflow_entity:"project-cockpit", workflow_stage:"shaping",
        workflow_binding:"/repo/.spacedock/explore", work_item_id:"workflow:project-cockpit"},
      {name:"Copernicus", observer_sid:"child-c", depth:1,
        assignment:"Fix dispatch authority", assignment_status:"structured dispatch artifact",
        workflow_entity:"project-cockpit", workflow_stage:"shaping",
        workflow_binding:"/repo/.spacedock/explore", work_item_id:"workflow:project-cockpit"}
    ], subagents: []},
    {sid:"pi-idle", harness:"pi", project:"cargento",
      project_key:"spacedock-research/cargento", state:"idle", active:true,
      last_activity:99, title:"Pi result", last_output:"Pi finished", subagents:[]},
    {sid:"claude-idle", harness:"claude", project:"cargento",
      project_key:"spacedock-research/cargento", state:"idle", active:true,
      last_activity:98, title:"Claude result", last_output:"Claude finished", subagents:[]}]
};
const __task = "workflow:project-cockpit";
const __semantic = {facts: [
  {fact_id:"fo-a", at:104, type:"user_message", summary:"Newest direction",
    source_session:{harness:"codex", sid:"focus-1"},
    evidence:{source:"root transcript", confidence:"exact"}},
  {fact_id:"task-a", at:103, type:"prepared_dispatch", summary:"Dispatch cockpit",
    source_session:{harness:"codex", sid:"focus-1"}, work_item_id:__task,
    evidence:{source:"dispatch artifact", confidence:"exact"}},
  {fact_id:"fo-b", at:102, type:"user_message", summary:"Correct the lane order",
    source_session:{harness:"codex", sid:"focus-1"},
    evidence:{source:"root transcript", confidence:"exact"}},
  {fact_id:"task-b", at:101, type:"stage_transition", stage:"shaping",
    summary:"Shaping cockpit", work_item_id:__task,
    evidence:{source:"workflow state", confidence:"exact"}},
  {fact_id:"gate-a", at:100, type:"gate_decision", source_kind:"gate",
    summary:"project-cockpit · review · approve", scope:"project", by:"person:captain",
    decision:"approve", stage:"review", application_state:"consumed",
    target_stage:"shaping", work_item_id:__task,
    evidence:{source:"entity gate", confidence:"exact"}}
], work_items:[{work_item_id:__task, label:"project-cockpit", kind:"workflow_item"}],
relations:[{type:"dispatches_to", from:"fo:codex:focus-1",
  to:`task:${__task}`, evidence_ref:"task-a", confidence:"exact"}], projections:{
  operator_intents:[
    {projection_id:"intent-a", at:104, summary:"Newest direction", derived_from:"fo-a"},
    {projection_id:"intent-b", at:102, summary:"Correct the lane order", derived_from:"fo-b"}
  ], steering_episodes:[], trail_heads:[{work_item_id:__task, status:"current stage",
    stage:"shaping", latest_meaningful_event:"task-b"}],
  command_attention:[],command_attention_coverage:{state:"complete",scanned:3,total:3,
    omitted:0,source:"bounded active-session final-output scan"},
  activity:{nodes:[{kind:"work", at:103, work_item_ids:[__task]}]}}};
__fetchImpl = async url => ({ok: true, json: async () =>
  String(url).startsWith("/api/project-context")
    ? {semantic: __semantic, child_assignments: [], observers: []}
    : __dashboard});
"""

    def run_fixture(self, checks: str, *, storage: dict[str, str] | None = None) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude(storage or {}) + self.FIXTURE,
        )

    FOCUS_DOM = r"""
let controls = [];
const decode = text => text.replace(/&quot;/g, '"').replace(/&amp;/g, "&");
__els.app = {
  get innerHTML(){ return this.html || ""; },
  set innerHTML(html){
    this.html = html;
    document.activeElement = null;
    controls = [...html.matchAll(/<(button|a|textarea)\b([^>]*)>/g)].map(match => {
      const attrs = Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)]
        .map(attr => [attr[1], decode(attr[2])]));
      const dataset = Object.fromEntries(Object.entries(attrs).filter(([key]) => key.startsWith("data-"))
        .map(([key, value]) => [key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), value]));
      return {dataset, tagName:match[1].toUpperCase(), value:"", attrs,
        getAttribute(name){ return attrs[name] || null; },
        focus(){ document.activeElement = this; },
        closest(selector){ return selector === "[data-next-cockpit-action]" && dataset.nextCockpitAction ? this : null; }};
    });
  },
  querySelectorAll(selector){
    return selector === "[data-next-focus]" ? controls.filter(control => control.dataset.nextFocus) : [];
  }
};
renderNext();
"""

    def test_tab_arrow_navigation_keeps_focus_for_consecutive_keys(self) -> None:
        out = self.run_fixture(
            self.FOCUS_DOM
            + """
controls.find(control => control.dataset.nextCockpitAction === "tab" && control.dataset.arg === "now").focus();
const states = [];
for(let index = 0; index < 2; index++){
  __fire("keydown", {target:document.activeElement,key:"ArrowRight",preventDefault(){}});
  states.push({tab:nextRoute.tab,focused:document.activeElement?.dataset.arg || null});
}
console.log(JSON.stringify(states));
"""
        )
        self.assertEqual(
            [{"tab": "course", "focused": "course"}, {"tab": "decisions", "focused": "decisions"}],
            out,
        )

    def test_scope_link_focus_survives_live_refresh(self) -> None:
        out = self.run_fixture(
            self.FOCUS_DOM
            + """
controls.find(control => control.dataset.nextCockpitScope === "codex:focus-1").focus();
await refreshNext();
console.log(JSON.stringify(document.activeElement?.dataset.nextCockpitScope || null));
"""
        )
        self.assertEqual("codex:focus-1", out)

    def test_opening_human_context_moves_focus_to_the_editor(self) -> None:
        out = self.run_fixture(
            self.FOCUS_DOM
            + """
const edit = controls.find(control => control.dataset.nextCockpitAction === "memo-edit");
edit.focus();
__fire("click", {target:edit,preventDefault(){}});
console.log(JSON.stringify({tag:document.activeElement?.tagName || null,
  key:document.activeElement?.dataset.nextCockpitMemoKey || null,expected:edit.dataset.arg}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual("TEXTAREA", out["tag"])
        self.assertEqual(out["expected"], out["key"])

    def test_console_screen_survives_navigation_away_and_back(self) -> None:
        out = self.run_fixture("""
const original = {textContent:"Delivered terminal output"};
let screen = original;
const getElement = document.getElementById;
document.getElementById = id => id === "pc-terminal-screen" ? screen : getElement(id);
projectTerminal = {dispose(){}};
projectTerminalKey = projectTerminalOpenKey = "codex:focus-1";
nextCockpitBeforeRender();
screen = null;
nextCockpitAfterRender();
nextCockpitBeforeRender();
screen = {textContent:"Loading the local terminal renderer.",replaceWith(node){ screen = node; }};
nextCockpitAfterRender();
console.log(JSON.stringify({same:screen === original,text:screen.textContent}));
""")
        self.assertEqual({"same": True, "text": "Delivered terminal output"}, out)

    def test_working_root_prevents_no_execution_claim(self) -> None:
        out = self.run_fixture("""
__dashboard.sessions = __dashboard.sessions.slice(0, 1);
__dashboard.sessions[0].subagent_hierarchy = [];
__semantic.facts = [];
__semantic.projections = {command_attention:[],command_attention_coverage:{
  state:"complete",scanned:1,total:1,omitted:0}};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")
        assert isinstance(out, str)
        self.assertNotIn("No execution observed", out)
        self.assertIn("Codex · working", out)

    def test_assignment_direction_remains_available_in_latest_evidence(self) -> None:
        out = self.run_fixture("""
__semantic.facts = [{fact_id:"direction",type:"user_message",at:104,
  summary:"Fix the completion guard",intent_promoted:true,
  source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"root transcript",confidence:"exact"}}];
__semantic.projections = {};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")
        assert isinstance(out, str)
        self.assertIn("Exact operator direction", out)
        self.assertNotIn("Actionable direction not captured", out)
        self.assertIn("Direction shown in assignment", out)

    def test_decision_rows_and_counts_include_unknown_authors_without_claiming_captain(
        self,
    ) -> None:
        out = self.run_fixture("""
__semantic.facts.push({...__semantic.facts.find(f => f.type === "gate_decision"),
  fact_id:"unknown-author",at:101,by:"",decision:"hold",summary:"Pending hold",
  application_state:"pending"});
nextRoute = {view:"project",project:"cargento",tab:"decisions"};
renderNext();
console.log(JSON.stringify({counts:nextCockpitCaptainDecisionCounts(__semantic),
  html:__els.app.innerHTML}));
""")
        assert isinstance(out, dict)
        self.assertEqual({"pending": 1, "unknown": 0, "superseded": 0, "applied": 1}, out["counts"])
        self.assertIn("Decision author not published", out["html"])
        self.assertIn("pending 1", out["html"])
        self.assertNotIn("CAPTAIN DECISIONS", out["html"])

    def test_session_scoped_now_discloses_project_wide_contents(self) -> None:
        out = self.run_fixture("""
nextRoute = {view:"project",project:"cargento",focus:"claude:claude-idle",tab:"now"};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML.slice(
  __els.app.innerHTML.indexOf('<section class="next-cockpit-panel"'))));
""")
        assert isinstance(out, str)
        self.assertIn("Now remains project-wide", out)
        self.assertIn("Shape project cockpit", out)

    def test_empty_course_and_decisions_keep_history_window(self) -> None:
        out = self.run_fixture("""
__semantic.facts = [];
__semantic.projections = {};
__semantic.history = {events:[],event_count:0,window_sec:86400,persisted:true};
const views = {};
for(const tab of ["course","decisions"]){
  nextRoute = {view:"project",project:"cargento",tab};
  renderNext();
  views[tab] = __els.app.innerHTML.slice(
    __els.app.innerHTML.indexOf('<section class="next-cockpit-panel"'));
}
console.log(JSON.stringify(views));
""")
        assert isinstance(out, dict)
        for tab, html in out.items():
            with self.subTest(tab=tab):
                self.assertIn("last 24 hours", html)

    def test_missing_plan_attachment_and_discovery_explanations_reach_now(self) -> None:
        out = self.run_fixture("""
__dashboard.sessions = __dashboard.sessions.slice(0,1);
__dashboard.sessions[0].spacedock = {role:"first-officer",workflows:[]};
for(const entry of nextCockpitContexts.values())
  entry.data.workflow_discovery = {state:"none",workflows:[]};
__semantic.facts = [];
__semantic.work_items = [];
__semantic.projections = {};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")
        assert isinstance(out, str)
        self.assertIn(
            "A first-officer attachment was observed, but it exposed no current plan", out
        )
        self.assertIn(
            "Spacedock project discovery observed no commissioned workflow directories", out
        )

    def test_zero_completed_tasks_retain_published_progress_in_course(self) -> None:
        out = self.run_fixture("""
__dashboard.sessions = __dashboard.sessions.slice(0,1);
__dashboard.sessions[0].tasks = ["alpha","beta","gamma"].map(subject => ({subject,status:"pending"}));
__dashboard.sessions[0].total = 3;
__dashboard.sessions[0].done = 0;
nextRoute = {view:"project",project:"cargento",tab:"course"};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")
        assert isinstance(out, str)
        self.assertIn("0 of 3 done", out)
        self.assertIn("No completed tracked tasks in this payload", out)

    def test_scope_navigation_keeps_the_title_when_activity_is_published(self) -> None:
        out = self.run_fixture(
            """
__dashboard.sessions[0].state_detail = "running Bash";
renderNext();
const html = __els.app.innerHTML;
console.log(JSON.stringify(html.slice(html.indexOf('<nav class="next-cockpit-scope-tree"'),
  html.indexOf('</nav>', html.indexOf('<nav class="next-cockpit-scope-tree"')))));
"""
        )
        assert isinstance(out, str)
        self.assertIn("Codex", out)
        self.assertIn("Shape project cockpit", out)
        self.assertNotIn("running Bash", out)

    def test_a_missing_title_is_named_in_scope_navigation(self) -> None:
        out = self.run_fixture(
            """
__dashboard.sessions[0].title = null;
__dashboard.sessions[0].state_detail = "running Bash";
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(out, str)
        self.assertIn("Session title not published", out)

    def test_course_names_missing_evidence_without_an_empty_disclosure(self) -> None:
        out = self.run_fixture(
            """
__semantic.facts = [{type:"user_message",summary:"Check source evidence",at:104,
  intent_promoted:true}];
__semantic.projections = {};
nextRoute = {view:"project",project:"cargento",tab:"course"};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML.slice(
  __els.app.innerHTML.indexOf('<section class="next-cockpit-panel"'))));
"""
        )
        assert isinstance(out, str)
        self.assertIn("Evidence source not published", out)
        self.assertIn("Evidence confidence not published", out)
        self.assertIn("Fact identity not published", out)
        self.assertNotIn('<details class="next-course-evidence"', out)

    def test_unmeasured_delegation_keeps_the_shared_models_reason(self) -> None:
        out = self.run_fixture(
            """
nextRoute = {view:"project",project:"cargento",tab:"console"};
renderNext();
console.log(JSON.stringify({html:__els.app.innerHTML,
  reason:nextCurrentObserved().projects[0].delegation.noteText}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("no figure yet", out["html"])
        self.assertIn(out["reason"], out["html"])
        self.assertEqual(1, out["html"].count("data-next-delegation-withheld"))

    def test_briefing_names_missing_readings_before_any_disclosure(self) -> None:
        out = self.run_fixture(
            """
__semantic.facts = [];
__semantic.projections = {};
for(const session of __dashboard.sessions){
  delete session.last_output;
  session.subagent_hierarchy = [];
}
renderNext();
const html = __els.app.innerHTML;
const briefing = html.slice(html.indexOf('<section class="next-cockpit-recovery"'),
  html.indexOf('<nav class="next-cockpit-tabs"'));
console.log(JSON.stringify(briefing.replace(/<details[^>]*>[\\s\\S]*?<\\/details>/g,"")));
"""
        )
        assert isinstance(out, str)
        self.assertIn("Assignment evidence not published", out)
        self.assertIn("Actionable direction not captured", out)
        self.assertIn("Session result not captured", out)
        self.assertIn("Captain attention unavailable", out)
        self.assertIn("project context coverage unavailable", out)

    def test_a_result_does_not_hide_the_missing_direction_reading(self) -> None:
        out = self.run_fixture(
            """
__semantic.facts = [{type:"result",summary:"Root finished",work_item_id:__task,at:104,
  evidence:{source:"root transcript",confidence:"exact"}}];
renderNext();
const html = __els.app.innerHTML;
console.log(JSON.stringify(html.slice(html.indexOf('<section class="next-cockpit-recovery"'),
  html.indexOf('<nav class="next-cockpit-tabs"'))));
"""
        )
        assert isinstance(out, str)
        self.assertIn("LATEST EXACT RESULT", out)
        self.assertIn("Root finished", out)
        self.assertIn("Actionable direction not captured", out)

    def test_scope_and_evidence_stay_open_through_a_redraw(self) -> None:
        out = self.run_fixture(
            """
let markup = __els.app.innerHTML;
let disclosures = [];
__els.app.querySelectorAll = selector =>
  selector === "[data-next-cockpit-disclosure]" ? disclosures : [];
Object.defineProperty(__els.app, "innerHTML", {
  get: () => markup,
  set: value => {
    markup = value;
    disclosures = [...value.matchAll(/data-next-cockpit-disclosure="([^"]+)"/g)]
      .map(match => ({key:match[1],open:false,
        getAttribute: () => match[1],querySelector: () => ({setAttribute(){}})}));
  }
});
__els.app.innerHTML = markup;
const selected = disclosures.filter(row => /\\n(?:scope|attention)$/.test(row.key));
selected.forEach(row => {row.open = true;});
renderNext();
const afterOpen = disclosures.filter(row => /\\n(?:scope|attention)$/.test(row.key));
const kept = afterOpen.map(row => row.open);
afterOpen.forEach(row => {row.open = false;});
renderNext();
console.log(JSON.stringify({kept,
  closed:disclosures.filter(row => /\\n(?:scope|attention)$/.test(row.key)).map(row => row.open)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual([True, True], out["kept"])
        self.assertEqual([False, False], out["closed"])

    def test_v2_surfaces_mount_in_their_cockpit_panels_once(self) -> None:
        out = self.run_fixture(
            """
__dashboard.sessions[0].instruction = {label:"asked",text:"Ship <the cockpit>"};
__dashboard.sessions[1].ended_at = 100;
__dashboard.sessions[0].spacedock = {workflows:[{workflow:"cockpit",goal:"Build cockpit",
  stages:["review"],entities:[{slug:"cockpit",stage:"review",live:true}]}]};
const views = {};
for(const tab of ["now", "course", "decisions", "console"]){
  nextRoute = nextRouteFromFragment("#n=project:cargento:" + tab);
  renderNext();
  const html = __els.app.innerHTML;
  views[tab] = {briefing:html.slice(html.indexOf('<section class="next-cockpit-recovery"'),
    html.indexOf('<nav class="next-cockpit-tabs"')),
    panel:html.slice(html.indexOf('<section class="next-cockpit-panel"'))};
}
console.log(JSON.stringify(views));
"""
        )
        assert isinstance(out, dict)
        for tab, view in out.items():
            with self.subTest(tab=tab):
                self.assertIn("Ship &lt;the cockpit&gt;", view["briefing"])
                self.assertIn("codex · latest assignment", view["briefing"])
                self.assertIn("2 of 3 sessions publish no goal.", view["briefing"])
                self.assertEqual(1, view["briefing"].count('class="next-project-goal"'))
                self.assertEqual(
                    tab == "now", 'data-next-project-activity="going-on"' in view["panel"]
                )
                self.assertEqual(
                    tab == "now", 'data-next-project-activity="ended"' in view["panel"]
                )
                self.assertEqual(tab == "course", "OBSERVED STATE CHANGES" in view["panel"])
                self.assertEqual(tab == "console", "data-next-project-rail" in view["panel"])
        self.assertIn("no estimate left · no confidence", out["now"]["panel"])
        self.assertIn("HOW THINGS ENDED", out["now"]["panel"])
        self.assertIn("git:", out["now"]["panel"])
        self.assertIn("Other directions (2)", out["course"]["panel"])
        for panel in ("delegation", "waiting", "capacity", "tripwires"):
            self.assertEqual(1, out["console"]["panel"].count(f'data-next-rail-panel="{panel}"'))
        self.assertNotIn("DELEGATION ·", out["console"]["panel"])
        self.assertIn("data-next-cockpit-console-status", out["console"]["panel"])

    def test_waiting_session_never_leaves_command_and_console_both_silent(self) -> None:
        out = self.run_fixture(
            """
document.querySelector = () => ({getAttribute: () => "test-capability"});
const waiting = __dashboard.sessions[1];
Object.assign(waiting, {harness:"codex", title:"Waiting <peer>",
  focusable:true, resume_id:"resume-peer"});
const views = [];
for(const kind of ["state", "ask", "harnessless-ask"]){
  waiting.state = kind === "state" ? "needs_input" : "idle";
  __dashboard.ask = true;
  __dashboard.asks = kind === "state" ? [] : [{session_id:"pi-idle",question:"Ship peer?",
    ...(kind === "ask" ? {harness:"codex"} : {})}];
  for(const focus of ["", ":session:codex%3Afocus-1"]){
    for(const tab of ["now", "course", "decisions", "console"]){
      nextRoute = {view:"project",project:"cargento",tab,
        focus:focus ? "codex:focus-1" : null};
      renderNext();
      const html = __els.app.innerHTML;
      const briefing = html.slice(html.indexOf('<section class="next-cockpit-recovery"'),
        html.indexOf('<nav class="next-cockpit-tabs"'));
      views.push({kind,tab,focus,command:briefing.slice(briefing.indexOf('<span>COMMAND</span>')),
        panel:html.slice(html.indexOf('<section class="next-cockpit-panel"'))});
    }
  }
}
console.log(JSON.stringify(views));
"""
        )
        assert isinstance(out, list)
        for view in out:
            with self.subTest(kind=view["kind"], tab=view["tab"], focus=view["focus"]):
                command = view["command"]
                self.assertIn("Waiting &lt;peer&gt;", command)
                self.assertIn('data-next-raise-session="pi-idle"', command)
                self.assertIn('data-next-raise-harness="codex"', command)
                self.assertIn('data-next-copy-command="codex resume resume-peer"', command)
                self.assertIn('aria-label="Raise the terminal this session is running in"', command)
                self.assertNotIn("Captain not needed", command)
                if view["tab"] == "console":
                    self.assertIn('data-next-wait-session="pi-idle"', view["panel"])
                if view["kind"] != "state":
                    self.assertIn("Ship peer?", command)

    def test_waiting_controls_share_cues_across_briefing_console_and_redraw(self) -> None:
        out = self.run_fixture(
            """
Object.assign(__dashboard.sessions[0], {state:"needs_input",focusable:true,resume_id:"resume-one"});
document.querySelector = () => ({getAttribute: () => "test-capability"});
let now = 100000;
Date.now = () => now;
nextRememberControlState(nextControlStateKey("raise", "codex", "focus-1"), "sent");
nextRememberControlState(nextControlStateKey("command", "codex", "focus-1"), "copied");
nextRoute = nextRouteFromFragment("#n=project:cargento:console");
now += 20000;
renderNext();
const kept = __els.app.innerHTML;
now += 10000;
renderNext();
console.log(JSON.stringify({kept,expired:__els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(2, out["kept"].count('data-next-raise-state="sent"'))
        self.assertEqual(2, out["kept"].count('data-next-copy-state="copied"'))
        self.assertNotIn("data-next-raise-state=", out["expired"])
        self.assertNotIn("data-next-copy-state=", out["expired"])

    def test_waiting_summary_uses_exact_model_ownership_without_semantic_context(self) -> None:
        out = self.run_fixture(
            """
__dashboard.sessions = [
  {sid:"shared",harness:"codex",project:"cargento",state:"idle",title:"Ambiguous Codex"},
  {sid:"shared",harness:"claude",project:"cargento",state:"idle",title:"Ambiguous Claude"},
  {sid:"ended",harness:"codex",project:"cargento",state:"needs_input",ended_at:100},
  {sid:"foreign",harness:"codex",project:"elsewhere",state:"needs_input"}
];
__dashboard.ask = true;
__dashboard.asks = [{session_id:"shared",question:"Unowned question"}];
nextRoute = nextRouteFromFragment("#n=project:cargento:console");
renderNext();
const withoutOwner = __els.app.innerHTML;
const needsWithoutOwner = nextCockpitProjectNeeds(nextProjectGroups().find(g => g.label === "cargento"));
__dashboard.asks[0].harness = "claude";
nextCockpitContexts.clear();
renderNext();
const group = nextProjectGroups().find(g => g.label === "cargento");
console.log(JSON.stringify({withoutOwner,needsWithoutOwner,withOwner:__els.app.innerHTML,
  needsWithOwner:nextCockpitProjectNeeds(group)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(0, out["needsWithoutOwner"])
        self.assertNotIn("data-next-cockpit-waiting", out["withoutOwner"])
        self.assertNotIn("data-next-wait-session=", out["withoutOwner"])
        self.assertEqual(1, out["needsWithOwner"])
        command = out["withOwner"].split("<span>COMMAND</span>")[1].split("<nav")[0]
        self.assertIn("data-next-cockpit-waiting", command)
        self.assertIn("Ambiguous Claude", command)
        self.assertNotIn("Ambiguous Codex", command)
        self.assertIn("Unowned question", command)
        self.assertIn("Captain attention unavailable", command)

    def test_ended_working_session_does_not_remain_in_recovery_execution(self) -> None:
        out = self.run_fixture(
            """
__dashboard.sessions[0].ended_at = 100;
renderNext();
const group = nextProjectGroups()[0];
const briefing = nextCockpitRecoveryBriefing(group, null, {semantic:__semantic}, []);
console.log(JSON.stringify({active:briefing.active,children:briefing.children.active,
  execution:nextCockpitRecoveryExecution(group, briefing),html:__els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual("No active sessions or exact assignments observed", out["active"])
        self.assertEqual([], out["children"])
        self.assertNotIn("Codex · working", out["execution"])
        self.assertNotIn('data-next-going-on="focus-1"', out["html"])
        self.assertIn('data-next-outcome="focus-1"', out["html"])

    def test_upstream_project_detail_hosts_focus_semantics_and_no_duplicate_shell(self) -> None:
        out = self.run_fixture(
            """
nextRoute = nextRouteFromFragment("#n=project:cargento:course");
renderNext();
await __settle();await __settle();
const html = __els.app.innerHTML;
const rows = [...html.matchAll(/<article class="next-course-episode"[\\s\\S]*?<\\/article>/g)]
  .map(match => match[0]);
console.log(JSON.stringify({html, rows}));
"""
        )
        assert isinstance(out, dict)
        html = out["html"]

        self.assertIn('data-next-project-detail="cargento"', html)
        self.assertIn('data-next-cockpit-panel="course"', html)
        self.assertIn("Other directions (2)", html)
        self.assertIn("Project cockpit · State change", html)
        self.assertIn(">Add human context</button>", html)
        self.assertNotIn("Outcome &amp; Focus", html)
        self.assertNotIn("SEMANTIC TIMELINE", html)
        self.assertNotIn('data-next-cockpit-action="graph-mode"', html)
        self.assertNotIn('data-calm="project-graph-mode"', html)
        self.assertEqual(2, len(out["rows"]))
        self.assertNotIn("pc-project-tabs", html)
        self.assertNotIn("Other project sessions", html)
        self.assertNotIn("Evidence / limits", html)
        self.assertNotIn("data-branch-edge=", html)
        self.assertNotIn("data-merge-edge=", html)

    def test_finished_teammates_are_not_active_work_or_assignment_gaps(self) -> None:
        out = self.run_fixture(
            """
const session = __dashboard.sessions[0];
session.harness = "claude";
session.subagent_hierarchy = null;
session.subagents = [
  {name:"Finished teammate",active:false,parent:null},
  {name:"Live teammate",active:true,parent:null,assignment:"Check the merged cockpit"}
];
renderNext();
await __settle();
const group = nextProjectGroups()[0];
console.log(JSON.stringify({html:__els.app.innerHTML,
  briefing:nextCockpitRecoveryBriefing(group).text}));
"""
        )
        assert isinstance(out, dict)
        self.assertNotIn("Finished teammate · active", out["html"])
        self.assertNotIn("inspect Finished teammate assignment", out["html"])
        self.assertIn("Live teammate · active", out["html"])
        self.assertNotIn("Finished teammate", out["briefing"])
        self.assertIn("Live teammate", out["briefing"])

    def test_task_subject_and_four_tabs_own_one_operator_question_each(self) -> None:
        out = self.run_fixture(
            """
const html = __els.app.innerHTML;
const tabs = [...html.matchAll(/<button[^>]*role="tab"[^>]*>[\\s\\S]*?<\\/button>/g)]
  .map(match => match[0]);
const panel = (html.match(/<section[^>]*role="tabpanel"[\\s\\S]*?<\\/section>/) || [""])[0];
console.log(JSON.stringify({html,tabs,panel}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn(
            "<span>ASSIGNMENT</span><strong>Project cockpit · Shaping</strong>", out["html"]
        )
        self.assertNotIn("data-next-cockpit-task-subject", out["html"])
        self.assertEqual(4, len(out["tabs"]))
        for label in ("Now", "Course", "Decisions", "Console"):
            self.assertTrue(any(f">{label}</button>" in tab for tab in out["tabs"]))
        self.assertTrue(
            any('aria-selected="true"' in tab and ">Now</button>" in tab for tab in out["tabs"])
        )
        self.assertEqual(1, out["html"].count('role="tabpanel"'))
        self.assertIn('data-next-cockpit-panel="now"', out["html"])
        self.assertIn(">Add human context</button>", out["html"])
        self.assertIn("FO INSPECTING", out["html"])
        self.assertIn("Banach · active", out["html"])
        self.assertNotIn("Show project plan", out["html"])
        self.assertNotIn("CURRENT FOCUS · DERIVED", out["html"])
        self.assertNotIn('data-next-project-section="plan"', out["html"])
        self.assertNotIn('data-next-project-section="going-on"', out["html"])
        self.assertNotIn("data-next-delegation", out["html"])
        self.assertNotIn("SEMANTIC TIMELINE", out["html"])
        self.assertNotIn('data-semantic-kind="decision"', out["html"])
        self.assertNotIn("EXACT SESSION TERMINAL", out["html"])
        self.assertNotIn('data-next-project-section="workstream"', out["html"])

    def test_now_is_a_calm_command_briefing_not_the_old_dashboard(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention=[
  {projection_id:"captain-auth",at:110,owner:"CAPTAIN",kind:"push_pr",
    label:"the shaped project cockpit",question:"Approve pushing this candidate?",
    evidence:{source:"exact assistant authorization request",confidence:"exact"}},
  {projection_id:"fo-recovery",at:109,owner:"FO",kind:"recovery",
    label:"Retry workflow discovery",question:"Retry workflow discovery",
    evidence:{source:"project workflow discovery",confidence:"exact"}}
];
const observation={semantic,workflow_discovery:{state:"error",reason:"timed out"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,revision:105});
renderNext();
const html=__els.app.innerHTML;
const panel=(html.match(/<section class="next-cockpit-panel"[\\s\\S]*<\\/section>/)||[""])[0];
const mirror=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
const visible=mirror
  .replace(/<details(?![^>]*\\bopen\\b)[^>]*>[\\s\\S]*?<\\/details>/g," ")
  .replace(/<[^>]+>/g," ").replace(/&[^;]+;/g," ")
  .replace(/\\s+/g," ").trim();
console.log(JSON.stringify({html,panel,mirror,visible,visibleWords:visible ? visible.split(" ").length : 0,
  primary:(html.match(/data-next-cockpit-primary/g)||[]).length}));
"""
        )
        assert isinstance(out, dict)
        panel = out["panel"]

        pre_correction_visible_words = 197
        self.assertLess(out["visibleWords"], pre_correction_visible_words)
        self.assertLessEqual(out["visibleWords"], 100)
        self.assertEqual(0, out["primary"])
        self.assertIn("Project cockpit · Shaping", out["mirror"])
        self.assertIn("Approve pushing this candidate?", out["mirror"])
        self.assertIn("Fix the completion guard", out["mirror"])
        self.assertNotIn("Add human context", out["mirror"])
        self.assertNotIn('data-next-cockpit-action="memo-edit"', out["mirror"])
        for old_surface in (
            "Latest decisions",
            "CURRENT FOCUS · DERIVED",
            "COMPLETED RESULT",
            'data-next-project-section="plan"',
            "data-next-delegation",
            "STEER · LOCAL ONLY",
            "GUARDRAILS · LOCAL ONLY",
            "<textarea",
        ):
            self.assertNotIn(old_surface, panel)
        self.assertIn("Retry workflow discovery", out["visible"])
        self.assertIn("Retry workflow discovery", out["visible"])
        self.assertNotIn("System details", out["mirror"])
        self.assertIn("Retry workflow discovery", out["mirror"])

    def test_scope_tree_and_memos_share_project_session_marker_grammar(self) -> None:
        out = self.run_fixture(
            """
const project=__els.app.innerHTML;
const narrowest={
  same:nextCockpitFactSetScope([
    {type:"result",source_session:{harness:"codex",sid:"focus-1"}},
    {type:"user_message",source_session:{harness:"codex",sid:"focus-1"}}]),
  mixed:nextCockpitFactSetScope([
    {type:"result",source_session:{harness:"codex",sid:"focus-1"}},
    {type:"result",source_session:{harness:"pi",sid:"pi-idle"}}]),
  unknown:nextCockpitFactSetScope([
    {type:"result",source_session:{harness:"codex",sid:"focus-1"}},
    {type:"result"}])
};
nextRoute=nextRouteFromFragment("#n=project:cargento:pi%3Api-idle");
renderNext();
await __settle();await __settle();
const session=__els.app.innerHTML;
console.log(JSON.stringify({project,session,narrowest}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn(
            'data-next-cockpit-scope="project" aria-current="page" data-scope-kind="project"',
            out["project"],
        )
        self.assertIn('class="next-scope-marker next-scope-marker--square"', out["project"])
        self.assertIn('class="next-scope-cue next-scope-cue--project"', out["project"])
        self.assertIn(">PROJECT</strong>", out["project"])
        self.assertIn('data-scope-owner="project"', out["project"])
        self.assertIn('data-scope-owner="pi:pi-idle"', out["session"])
        self.assertIn('class="next-scope-marker next-scope-marker--round"', out["session"])
        self.assertIn('class="next-scope-cue next-scope-cue--session"', out["session"])
        self.assertIn(">SESSION</strong>", out["session"])
        self.assertEqual("session", out["narrowest"]["same"]["kind"])
        self.assertEqual("project", out["narrowest"]["mixed"]["kind"])
        self.assertEqual("unknown", out["narrowest"]["unknown"]["kind"])
        self.assertNotIn('data-parent-session="codex:focus-1"', out["project"])
        self.assertIn("source session codex:focus-1", out["project"])
        self.assertIn('data-scope-owner="codex:focus-1"', out["project"])

    def test_selected_session_keeps_project_briefing_ownership_explicit(self) -> None:
        out = self.run_fixture(
            """
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1");
renderNext();await __settle();await __settle();
const html=__els.app.innerHTML;
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
const task=(recovery.match(/<div data-next-cockpit-task[\\s\\S]*?<\\/div>/)||[""])[0];
const switcher=(html.match(/<details class="next-cockpit-scope-switcher"[\\s\\S]*?<\\/details>/)||[""])[0];
console.log(JSON.stringify({html,recovery,task,switcher}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("Viewing session · Codex · working", out["html"])
        self.assertIn('data-next-cockpit-viewing-session="codex:focus-1"', out["html"])
        self.assertIn("<span>ASSIGNMENT</span>", out["task"])
        self.assertNotIn('data-scope-kind="project"', out["task"])
        self.assertNotIn(">SESSION</strong>", out["task"])
        self.assertNotIn('data-parent-session="codex:focus-1"', out["recovery"])
        self.assertIn("source session codex:focus-1", out["recovery"])
        self.assertNotIn(">SESSION</strong>", out["recovery"])
        self.assertIn("Viewing session · Codex · working", out["switcher"])
        self.assertIn("Change scope", out["switcher"])
        self.assertIn('data-next-cockpit-scope="project"', out["switcher"])
        self.assertIn('data-next-cockpit-scope="codex:focus-1"', out["switcher"])

    def test_course_interleaves_project_session_and_unknown_provenance_cues(self) -> None:
        out = self.run_fixture(
            """
nextCockpitContexts.clear();
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.push(
  {fact_id:"unknown-input",at:101.5,type:"user_message",intent_promoted:true,
    summary:"Unattributed operator note",evidence:{source:"source unavailable",confidence:"unknown"}},
  {fact_id:"review-result",at:102.5,type:"result",summary:"Review synthesis returned",
    detail:"Review changed the course:\\n- Keep scope visible.",
    source_session:{harness:"codex",sid:"focus-1"},work_item_id:__task,
    evidence:{source:"assistant final answer",confidence:"exact"}}
);
__fetchImpl=async()=>({ok:true,json:async()=>({semantic,child_assignments:[],observers:[]})});
nextRoute=nextRouteFromFragment("#n=project:cargento:course");
renderNext();await __settle();await __settle();await __settle();
const html=__els.app.innerHTML;
const rows=[...html.matchAll(/<article class="next-course-episode"[\\s\\S]*?<\\/article>/g)]
  .map(match=>match[0]);
const directions=[...html.matchAll(/<article class="next-course-direction"[\\s\\S]*?<\\/article>/g)]
  .map(match=>match[0]);
console.log(JSON.stringify({html,rows,directions}));
"""
        )
        assert isinstance(out, dict)

        session_rows = [row for row in out["directions"] if "Newest direction" in row]
        project_rows = [row for row in out["rows"] if "Shaping cockpit" in row]
        unknown_rows = [row for row in out["directions"] if "Unattributed operator note" in row]
        derived_rows = [row for row in out["rows"] if "DERIVED COURSE CHANGE" in row]
        self.assertEqual(1, len(session_rows))
        self.assertIn('data-scope-kind="session"', session_rows[0])
        self.assertEqual(1, len(project_rows))
        self.assertIn('data-scope-kind="project"', project_rows[0])
        self.assertEqual(1, len(unknown_rows))
        self.assertIn('data-scope-kind="unknown"', unknown_rows[0])
        self.assertIn("SCOPE UNKNOWN", unknown_rows[0])
        self.assertEqual(1, len(derived_rows))
        self.assertIn('data-scope-kind="session"', derived_rows[0])
        self.assertIn("DERIVED COURSE CHANGE", derived_rows[0])

    def test_paired_direction_stays_with_its_change_and_is_not_duplicated(self) -> None:
        out = self.run_fixture(
            """
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.find(fact=>fact.fact_id==="fo-a").work_item_id=__task;
semantic.facts.push({fact_id:"paired-result",at:106,type:"result",summary:"Layout corrected",
  detail:"Fixed and live on port 8766.\\n\\nCheckpoint: `abc1234`.",
  source_session:{harness:"codex",sid:"focus-1"},work_item_id:__task,
  evidence:{source:"assistant result",confidence:"exact"}});
semantic.projections.steering_episodes=[{episode_id:"pair-a",intent_id:"intent-a",
  adaptation_fact:"paired-result",confidence:"structural"}];
const html=nextCockpitCourse(nextProjectGroups()[0],semantic,[]);
const primary=(html.match(/<article class="next-course-episode"[\\s\\S]*?<\\/article>/g)||[])
  .find(row=>row.includes("Layout corrected"))||"";
const other=(html.match(/<details class="next-course-directions"[\\s\\S]*?<\\/details>/)||[""])[0];
console.log(JSON.stringify({html,primary,other}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("Newest direction", out["primary"])
        self.assertIn("Layout corrected", out["primary"])
        self.assertIn("assistant result", out["primary"])
        self.assertNotIn("Newest direction", out["other"])
        self.assertEqual(1, out["html"].count("Newest direction"))

    def test_course_pairing_requires_ordered_exact_task_binding_and_meaningful_change(self) -> None:
        out = self.run_fixture(
            """
const courseCase=(direction,result,workItems=[])=>{
  const semantic={facts:[direction,result],work_items:[
    {work_item_id:__task,label:"project-cockpit",kind:"workflow_item"},...workItems],
    relations:[],projections:{operator_intents:[{projection_id:"intent",at:direction.at,
      summary:direction.summary,derived_from:direction.fact_id}],steering_episodes:[{
      episode_id:"pair",intent_id:"intent",adaptation_fact:result.fact_id,
      confidence:"structural"}],trail_heads:[]}};
  const html=nextCockpitCourse(nextProjectGroups()[0],semantic,[]);
  return {html,primary:(html.match(/<article class="next-course-episode"/g)||[]).length,
    other:(html.match(/<article class="next-course-direction"/g)||[]).length};
};
const direction={fact_id:"direction",at:100,type:"user_message",intent_promoted:true,
  summary:"Keep the exact task boundary",work_item_id:__task,
  source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"root transcript",confidence:"exact"}};
const unbound=courseCase(direction,{fact_id:"generic",at:101,type:"result",
  summary:"Ordinary worker returned",source_session:{harness:"codex",sid:"child"},
  evidence:{source:"ordinary child result",confidence:"exact"}});
const inverted=courseCase({...direction,at:103},{fact_id:"stage-before",at:102,
  type:"stage_transition",stage:"review",summary:"Review stage",work_item_id:__task,
  evidence:{source:"workflow state",confidence:"exact"}});
const otherTask="workflow:other";
const mismatched=courseCase(direction,{fact_id:"other-stage",at:104,
  type:"stage_transition",stage:"review",summary:"Other review stage",work_item_id:otherTask,
  evidence:{source:"workflow state",confidence:"exact"}},[
    {work_item_id:otherTask,label:"other-task",kind:"workflow_item"}]);
const positive=courseCase(direction,{fact_id:"exact-stage",at:105,
  type:"stage_transition",stage:"review",summary:"Exact review stage",work_item_id:__task,
  evidence:{source:"workflow state",confidence:"exact"}});
console.log(JSON.stringify({unbound,inverted,mismatched,positive}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(
            {"primary": 0, "other": 1}, {key: out["unbound"][key] for key in ("primary", "other")}
        )
        for key in ("inverted", "mismatched"):
            self.assertEqual(1, out[key]["primary"])
            self.assertEqual(1, out[key]["other"])
            self.assertNotIn("<b>Direction</b>", out[key]["html"])
        self.assertEqual(1, out["positive"]["primary"])
        self.assertEqual(0, out["positive"]["other"])
        self.assertIn("<b>Direction</b>", out["positive"]["html"])

    def test_sixteen_exact_directions_fold_when_no_course_change_is_observed(self) -> None:
        out = self.run_fixture(
            """
const facts=Array.from({length:16},(_,index)=>({fact_id:`direction-${index+1}`,
  at:index+1,type:"user_message",intent_promoted:true,summary:`Direction ${index+1}`,
  source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"root transcript",confidence:"exact"}}));
const semantic={facts,work_items:[],relations:[],projections:{
  operator_intents:facts.map((fact,index)=>({projection_id:`intent-${index+1}`,
    at:fact.at,summary:fact.summary,derived_from:fact.fact_id})),
  steering_episodes:[],trail_heads:[]}};
const html=nextCockpitCourse(nextProjectGroups()[0],semantic,[]);
const primary=[...html.matchAll(/<article class="next-course-episode"/g)].length;
console.log(JSON.stringify({html,primary}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(0, out["primary"])
        self.assertIn("No source-backed course changes observed", out["html"])
        self.assertIn("Other directions (16)", out["html"])
        self.assertIn("<details", out["html"])
        for number in range(1, 17):
            self.assertEqual(1, out["html"].count(f"Direction {number}<"))
        self.assertLess(out["html"].index("Direction 1<"), out["html"].index("Direction 16<"))

    def test_completed_tracked_work_lives_only_in_course(self) -> None:
        out = self.run_fixture(
            """
const claude=__dashboard.sessions.find(session=>session.harness==="claude");
claude.tasks=[{status:"completed",subject:"Verify accepted project cockpit"}];
renderNext();await __settle();
const now=__els.app.innerHTML;
nextRoute=nextRouteFromFragment("#n=project:cargento:course");
renderNext();await __settle();await __settle();
console.log(JSON.stringify({now,course:__els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        self.assertNotIn("Verify accepted project cockpit", out["now"])
        self.assertIn("Verify accepted project cockpit", out["course"])
        self.assertIn('data-next-project-activity="done"', out["course"])

    def test_decisions_use_fact_scope_not_selected_session(self) -> None:
        out = self.run_fixture(
            """
nextCockpitContexts.clear();
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.push({fact_id:"session-decision",at:100.5,type:"gate_decision",
  source_kind:"gate",scope:"session",by:"person:captain",decision:"hold",stage:"review",
  application_state:"pending",work_item_id:__task,
  source_session:{harness:"pi",sid:"pi-idle"},
  evidence:{source:"session gate",confidence:"exact"}});
__fetchImpl=async()=>({ok:true,json:async()=>({semantic,child_assignments:[],observers:[]})});
nextRoute=nextRouteFromFragment("#n=project:cargento:pi%3Api-idle:decisions");
renderNext();await __settle();await __settle();await __settle();
const rows=[...__els.app.innerHTML.matchAll(/<article class="pc-graph-row[\\s\\S]*?<\\/article>/g)]
  .map(match=>match[0]);
console.log(JSON.stringify({rows,html:__els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        project_rows = [row for row in out["rows"] if 'data-action="approved"' in row]
        session_rows = [row for row in out["rows"] if 'data-action="held"' in row]
        self.assertEqual(1, len(project_rows))
        self.assertIn('data-scope-kind="project"', project_rows[0])
        self.assertIn(">PROJECT</strong>", project_rows[0])
        self.assertEqual(1, len(session_rows))
        self.assertIn('data-scope-kind="session"', session_rows[0])
        self.assertIn(">SESSION</strong>", session_rows[0])

    def test_console_names_session_scope_and_project_root_stays_non_session(self) -> None:
        out = self.run_fixture(
            """
nextRoute=nextRouteFromFragment("#n=project:cargento:console");
renderNext();await __settle();
const project=__els.app.innerHTML;
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1:console");
renderNext();await __settle();
const session=__els.app.innerHTML;
console.log(JSON.stringify({project,session}));
"""
        )
        assert isinstance(out, dict)

        project_panel = out["project"][out["project"].index('data-next-cockpit-panel="console"') :]
        session_panel = out["session"][out["session"].index('data-next-cockpit-panel="console"') :]
        self.assertIn('data-scope-kind="project"', project_panel)
        self.assertIn(">PROJECT</strong>", project_panel)
        self.assertNotIn('data-scope-kind="session"', project_panel)
        self.assertIn('data-scope-kind="session"', session_panel)
        self.assertIn(">SESSION</strong>", session_panel)
        self.assertIn("STEER · LOCAL ONLY", project_panel)
        self.assertIn("<h2>TRIPWIRES</h2>", project_panel)
        self.assertIn("local only · nothing enforces these", project_panel)
        self.assertIn("data-next-delegation", project_panel)
        self.assertIn("STEER · LOCAL ONLY", session_panel)
        self.assertIn("Raw project status", project_panel)
        self.assertNotIn("Latest decisions", project_panel)

    def test_local_tab_permalink_and_arrow_keys_preserve_project_session_route(self) -> None:
        out = self.run_fixture(
            """
const parsed = nextRouteFromFragment("#n=project:cargento:pi%3Api-idle:course");
const roundTrip = nextFragmentForRoute(parsed);
nextRoute = parsed;
renderNext();
await __settle();await __settle();
const course = __els.app.innerHTML;
const target = {dataset:{nextCockpitAction:"tab",arg:"course"},
  closest(selector){ return selector === "[data-next-cockpit-action]" ? this : null; }};
__fire("keydown", {target,key:"ArrowRight",preventDefault(){}});
const afterKey = __els.app.innerHTML;
console.log(JSON.stringify({parsed,roundTrip,course,afterKey,hash:location.hash}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual("pi:pi-idle", out["parsed"]["focus"])
        self.assertEqual("course", out["parsed"]["tab"])
        self.assertEqual("#n=project:cargento:pi%3Api-idle:course", out["roundTrip"])
        self.assertIn('data-next-cockpit-panel="course"', out["course"])
        self.assertIn('aria-selected="true" tabindex="0">Course</button>', out["course"])
        self.assertIn('data-next-cockpit-panel="decisions"', out["afterKey"])
        self.assertEqual("#n=project:cargento:pi%3Api-idle:decisions", out["hash"])

    def test_console_waits_for_origin_lookup_then_opens_read_only_terminal(self) -> None:
        out = self.run_fixture(
            """
__fetchImpl = async url => String(url).startsWith("/api/interaction/origin")
  ? ({ok:true,json:async()=>({state:"registered",origin:{session_name:"Cargento",
      window_index:1,pane_index:1},origin_id_hint:"origin-1"})})
  : ({ok:true,json:async()=>({semantic:__semantic,child_assignments:[],observers:[]})});
nextRoute = nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1:console");
renderNext();
const pending = __els.app.innerHTML;
await __settle();
const available = __els.app.innerHTML;
const open = {dataset:{nextCockpitAction:"terminal-open",arg:"codex:focus-1"},
  closest(selector){ return selector === "[data-next-cockpit-action]" ? this : null; }};
__fire("click", {target:open,preventDefault(){}});
const opened = __els.app.innerHTML;
console.log(JSON.stringify({pending,available,opened}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn('data-next-cockpit-panel="console"', out["pending"])
        self.assertNotIn("Open terminal", out["pending"])
        self.assertIn("Open terminal", out["available"])
        self.assertIn("EXACT SESSION TERMINAL", out["available"])
        self.assertIn("read-only", out["opened"])
        self.assertIn('aria-label="Read-only terminal output"', out["opened"])
        for html in out.values():
            self.assertNotIn("CURRENT FOCUS · DERIVED", html)
            self.assertNotIn("Project cockpit · User direction", html)
            self.assertNotIn('data-semantic-kind="decision"', html)

    def test_terminal_absence_explains_registration_and_preserves_the_server_reason(self) -> None:
        out = self.run_fixture(
            """
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1:console");
const views = {};
for(const reason of ["unregistered-origin", "stale-registration", "origin-disconnected",
    "session-mismatch", "new-<refusal>", "disabled", "failed"]){
  delete projectTerminalBySession["codex:focus-1"];
  __fetchImpl = async () => {
    if(reason === "failed") throw new Error("offline");
    return {ok:reason !== "disabled",status:reason === "disabled" ? 404 : 200,
      json:async()=>({state:"refused",reason})};
  };
  renderNext();
  views.pending = __els.app.innerHTML;
  await __settle(); await __settle();
  views[reason] = __els.app.innerHTML;
}
console.log(JSON.stringify(views));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("Checking terminal registration for this exact session.", out["pending"])
        self.assertIn("Terminal not registered for this session.", out["unregistered-origin"])
        self.assertIn("--interaction-origin-session", out["unregistered-origin"])
        self.assertIn("--interaction-origin-registration-file", out["unregistered-origin"])
        self.assertIn("inside the tmux pane for this exact session", out["unregistered-origin"])
        self.assertIn("Terminal registration has expired.", out["stale-registration"])
        self.assertIn("The registered tmux pane is disconnected.", out["origin-disconnected"])
        self.assertIn(
            "The registered terminal belongs to another session.", out["session-mismatch"]
        )
        self.assertIn("new-&lt;refusal&gt;", out["new-<refusal>"])
        self.assertIn("The terminal bridge is disabled on this server.", out["disabled"])
        self.assertIn("Terminal registration could not be checked", out["failed"])
        for html in out.values():
            self.assertIn("EXACT SESSION TERMINAL", html)
            self.assertNotIn("Open terminal", html)

    def test_terminal_identity_keeps_zero_indices_and_names_missing_coordinates(self) -> None:
        out = self.run_fixture(
            """
const session = __dashboard.sessions[0];
const views = [];
projectTerminalOpenKey = "codex:focus-1";
for(const origin of [{session_name:"Pane <one>",window_index:0,pane_index:0},{}]){
  projectTerminalBySession[projectTerminalOpenKey] = {state:"registered",data:{origin}};
  views.push(projectTerminalSurface(session));
}
console.log(JSON.stringify(views));
"""
        )
        assert isinstance(out, list)
        self.assertIn("Pane &lt;one&gt;:0.0", out[0])
        self.assertIn("Tmux session name not published.", out[1])
        self.assertIn("Window index not published.", out[1])
        self.assertIn("Pane index not published.", out[1])
        self.assertNotIn("tmux:?.?", out[1])

    def test_substrate_empty_history_names_its_published_window_and_filter(self) -> None:
        out = self.run_fixture(
            """
const views = {};
for(const [name,history,mode] of [["day",{window_sec:86400},"all"],
    ["short",{window_sec:5400},"decisions"],["unknown",{},"all"],
    ["active",{window_sec:86400},"active"]]){
  views[name] = projectSemanticTimeline(__dashboard,
    {facts:[],work_items:[],projections:{},history},[],null,[],{mode});
}
console.log(JSON.stringify(views));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("No semantic events observed in the last 24 hours.", out["day"])
        self.assertIn("No decisions observed in the last 90 minutes.", out["short"])
        self.assertIn("The semantic history window was not published.", out["unknown"])
        self.assertIn(
            "No semantic events for active work observed in the last 24 hours.", out["active"]
        )
        for html in out.values():
            self.assertIn('class="pc-substrate-empty"', html)

    def test_terminal_assets_load_from_loopback_and_name_either_local_load_failure(self) -> None:
        out = self.run_fixture(
            """
const cases = [];
for(const failure of ["script", "link", "none"]){
  projectTerminalXtermPromise = null;
  delete window.Terminal;
  const nodes = [];
  document.querySelector = () => null;
  document.createElement = tag => ({tag,dataset:{},remove(){}});
  document.head = {append(node){nodes.push(node);}};
  const loaded = projectTerminalLoadXterm().then(()=>"loaded",error=>error.message);
  await __settle();
  for(const node of nodes){
    if(node.tag === failure && node.onerror) node.onerror();
    else if(node.onload){
      if(node.tag === "script") window.Terminal = function(){};
      node.onload();
    }
  }
  cases.push({failure,result:await loaded,nodes});
}
console.log(JSON.stringify(cases));
"""
        )
        assert isinstance(out, list)
        for case in out:
            assets = {node["tag"]: node for node in case["nodes"]}
            self.assertEqual("/assets/xterm.js", assets["script"]["src"])
            self.assertEqual("/assets/xterm.css", assets["link"]["href"])
            for node in assets.values():
                self.assertNotIn("integrity", node)
                self.assertNotIn("crossOrigin", node)
            if case["failure"] == "none":
                self.assertEqual("loaded", case["result"])
            else:
                self.assertIn("Console cannot open because the local terminal", case["result"])
                self.assertIn("did not load.", case["result"])

    def test_substrate_evidence_names_missing_readings_and_separates_source_strings(self) -> None:
        out = self.run_fixture(
            """
const lane = {key:"fo:codex:focus-1",kind:"fo",label:"Codex",index:0,events:[]};
const registry = {lanes:[lane]};
console.log(JSON.stringify({
  absent:projectGlobalEventDetails({kind:"decision",fact:{}},lane),
  present:projectGlobalEventDetails({kind:"result",fact:{at:100,
    evidence:{source:"Transcript <exact>",confidence:"exact"}}},lane),
  row:projectGraphRow(__dashboard,null,"event",registry,lane,"An observed event"),
  fact:projectFactEvidence({},"missing"),
  span:projectHistorySpan([])
}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("Decision author not published.", out["absent"])
        self.assertIn("Decision stage not published.", out["absent"])
        for key in ("absent", "fact"):
            self.assertIn("Evidence source not published.", out[key])
            self.assertIn("Evidence confidence not published.", out[key])
            self.assertIn("Event time not published.", out[key])
        self.assertIn('<span class="pc-source">Transcript &lt;exact&gt;</span>', out["present"])
        self.assertIn("Event time not published.", out["row"])
        self.assertNotIn("<time></time>", out["row"])
        self.assertEqual("Observed span not measured: no event times published.", out["span"])

    def test_substrate_does_not_turn_a_missing_event_time_into_epoch_history(self) -> None:
        out = self.run_fixture(
            """
const model = JSON.parse(JSON.stringify(__semantic));
model.facts.forEach(fact => delete fact.at);
model.projections.operator_intents.forEach(intent => delete intent.at);
const registry = projectLaneRegistry(model,[],null,__dashboard.sessions);
const events = projectGlobalEvents(model,registry,null);
console.log(JSON.stringify({html:projectSemanticTimeline(__dashboard,model,[],null,
  __dashboard.sessions,{mode:"all"}),span:projectHistorySpan(events),
  partial:projectGlobalEventDetails({kind:"decision",fact:{target_stage:"review"}},
    {kind:"fo",events:[]})}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("Event time not published.", out["html"])
        self.assertNotIn("ago</time>", out["html"])
        self.assertEqual("Observed span not measured: no event times published.", out["span"])
        self.assertIn("Decision stage not published.", out["partial"])
        self.assertNotIn("> → review<", out["partial"])
        self.assertIn('<span class="pc-source">Newest direction</span>', out["html"])

    def test_terminal_follow_keeps_short_output_visible_above_unused_rows(self) -> None:
        out = self.run_fixture(
            """
const viewport = {scrollHeight:392,clientHeight:340,scrollTop:0};
__els["pc-terminal-viewport"] = viewport;
projectTerminal = {rows:20,buffer:{active:{cursorY:2}},element:{querySelector:()=>({
  getBoundingClientRect:()=>({height:380})})}};
projectTerminalBindViewport();
const short = viewport.scrollTop;
viewport.onscroll();
const follows = projectTerminalFollowLive;
projectTerminal.buffer.active.cursorY = 19;
projectTerminalScrollToLive();
const bottom = viewport.scrollTop;
viewport.scrollTop = 20;
viewport.onscroll();
console.log(JSON.stringify({short,follows,bottom,paused:!projectTerminalFollowLive}));
"""
        )
        self.assertEqual({"short": 0, "follows": True, "bottom": 52, "paused": True}, out)

    def test_course_is_task_first_source_labeled_and_omits_future_history(self) -> None:
        out = self.run_fixture(
            """
nextCockpitContexts.clear();
const semantic = JSON.parse(JSON.stringify(__semantic));
semantic.facts.push(
  {fact_id:"review-result",at:102.5,type:"result",summary:"Review synthesis returned",
    detail:"Review changed the course:\\n- Show task ownership, not lifecycle noise.\\n" +
      "- Separate project overview from session evidence.\\n\\nFuture — proposed, not dispatched",
    source_session:{harness:"codex",sid:"focus-1"},work_item_id:__task,
    evidence:{source:"assistant final_answer followed by terminal turn state",confidence:"exact"}},
  {fact_id:"live-result",at:102.4,type:"result",summary:"Fixed and live on port 8766.",
    detail:"Fixed and live on port 8766.\\n\\nCheckpoint: `179a80d`.",
    source_session:{harness:"codex",sid:"focus-1"},work_item_id:__task,
    evidence:{source:"assistant final_answer followed by terminal turn state",confidence:"exact"}}
);
__fetchImpl = async url => ({ok:true,json:async() => ({semantic,
  child_assignments:[{name:"Banach",workItemId:__task,source:"structured assignment"}],
  observers:[]})});
nextRoute = nextRouteFromFragment("#n=project:cargento:course");
renderNext();
await __settle();await __settle();await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        html = out["html"]

        self.assertIn('data-next-cockpit-panel="course"', html)
        self.assertIn("Other directions (2)", html)
        self.assertIn("EXACT DIRECTION", html)
        self.assertIn("Project cockpit · State change", html)
        self.assertIn("EXACT STATE CHANGE", html)
        self.assertIn("Project cockpit · Result", html)
        self.assertIn("EXACT RESULT", html)
        self.assertIn("Project cockpit · Course change", html)
        self.assertIn("DERIVED COURSE CHANGE", html)
        self.assertIn("Show task ownership, not lifecycle noise.", html)
        self.assertIn("Separate project overview from session evidence.", html)
        self.assertIn("Banach", html)
        self.assertIn("<details", html[: html.index("Banach")])
        self.assertNotIn("Future", html)
        self.assertNotIn("proposed, not dispatched", html)
        self.assertIn("179a80d", html)
        self.assertIn("<span>ASSIGNMENT</span><strong>Project cockpit · Shaping</strong>", html)
        self.assertNotIn("CURRENT FOCUS · DERIVED", html)

    def test_defaults_to_all_sessions_and_links_every_idle_peer(self) -> None:
        out = self.run_fixture(
            """
const html = __els.app.innerHTML;
console.log(JSON.stringify({html, query:[...nextCockpitContexts.keys()]}));
"""
        )
        assert isinstance(out, dict)
        html = out["html"]

        self.assertIn('class="next-cockpit-scope-tree"', html)
        self.assertIn('data-next-cockpit-scope="project" aria-current="page"', html)
        self.assertNotIn("All sessions", html)
        self.assertNotIn('role="tablist" aria-label="Project sessions"', html)
        self.assertIn("Codex", html)
        self.assertIn("Pi", html)
        self.assertIn("Claude", html)
        self.assertIn("pi-idle", html)
        self.assertIn("claude-idle", html)
        self.assertIn("#n=project:cargento:pi%3Api-idle", html)
        self.assertTrue(any(key.endswith("\n") for key in out["query"]))

    def test_all_sessions_aggregates_exact_running_workers_with_parent_and_task(self) -> None:
        out = self.run_fixture(
            """
const html = __els.app.innerHTML;
const task = (html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/) || [""])[0];
console.log(JSON.stringify({html, task}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("Banach", out["task"])
        self.assertIn("Copernicus", out["task"])
        self.assertIn("EXECUTION", out["task"])
        self.assertIn("Codex · working", out["task"])
        self.assertIn("Fix the completion guard", out["task"])
        self.assertIn("Fix dispatch authority", out["task"])
        self.assertNotIn("Project cockpit · 2 active assignments", out["task"])
        self.assertIn('data-work-item="workflow:project-cockpit"', out["task"])
        self.assertNotIn('data-parent-session="codex:focus-1"', out["task"])
        self.assertIn("source session codex:focus-1", out["task"])

    def test_active_work_does_not_promote_an_unassigned_child(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
group.sessions[0].subagent_hierarchy=[{name:"Unbound",observer_sid:"child-x",depth:1}];
const html=nextCockpitActiveDelegation(group,{semantic:__semantic});
console.log(JSON.stringify({html}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("assignment unavailable", out["html"])
        self.assertIn("Unbound", out["html"])
        self.assertIn("assignment source unavailable", out["html"])

    def test_missing_task_identity_keeps_exact_working_activity_without_invention(self) -> None:
        out = self.run_fixture(
            """
nextData.sessions=[{sid:"focus-1",harness:"codex",project:"cargento",
  project_key:"spacedock-research/cargento",state:"working",active:true,
  last_activity:104,title:null,state_detail:"running 1 subagent",
  subagent_hierarchy:[{name:"Unbound",observer_sid:"child-x",depth:1}],subagents:[{}]}];
const group=nextProjectGroups()[0];
const observation={semantic:{facts:[],work_items:[],relations:[],projections:{
  trail_heads:[],command_attention:[]}},child_assignments:[],observers:[]};
nextCockpitContexts.clear();nextCockpitRequests.clear();
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,revision:nextData.generated});
nextRoute=nextRouteFromFragment("#n=project:cargento");
renderNext();await __settle();await __settle();
const html=__els.app.innerHTML;
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
const task=(recovery.match(/<div data-next-cockpit-task[\\s\\S]*?<\\/div>/)||[""])[0];
const scope=(html.match(/<nav class="next-cockpit-scope-tree"[\\s\\S]*?<\\/nav>/)||[""])[0];
const panel=(html.match(/<section class="next-cockpit-panel"[\\s\\S]*<\\/section>/)||[""])[0];
const visible=panel.replace(/<details(?![^>]*\\bopen\\b)[^>]*>[\\s\\S]*?<\\/details>/g," ")
  .replace(/<[^>]+>/g," ").replace(/&[^;]+;/g," ").replace(/\\s+/g," ").trim();
console.log(JSON.stringify({html,recovery,task,scope,visibleWords:visible?visible.split(" ").length:0,
  primary:(html.match(/data-next-cockpit-primary/g)||[]).length}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(0, out["primary"])
        self.assertLessEqual(out["visibleWords"], 48)
        self.assertIn("ASSIGNMENT", out["task"])
        self.assertIn("<strong>Not observed</strong>", out["task"])
        self.assertNotIn(">PROJECT</strong>", out["task"])
        self.assertNotIn("data-work-item", out["task"])
        for invention in (
            "CURRENT TASK",
            "Project work",
            "State unavailable",
            "Current task is active",
        ):
            self.assertNotIn(invention, out["html"])
        self.assertIn("Unbound · active", out["recovery"])
        self.assertIn("assignment unavailable", out["recovery"])
        self.assertIn("inspect Unbound assignment", out["recovery"])
        self.assertEqual("", out["scope"])

    def test_session_switcher_is_below_header_and_outcome_first(self) -> None:
        out = self.run_fixture(
            """
const html = __els.app.innerHTML;
const nav = (html.match(/<nav class="next-cockpit-scope-tree"[\\s\\S]*?<\\/nav>/) || [""])[0];
console.log(JSON.stringify({
  header:html.indexOf('class="next-project-detail-header"'),
  nav:html.indexOf('class="next-cockpit-scope-tree"'),
  plan:html.indexOf('data-next-cockpit-plan-details'),
  html, sessionNav:nav
}));
"""
        )
        assert isinstance(out, dict)

        self.assertLess(out["header"], out["nav"])
        self.assertEqual(-1, out["plan"])
        self.assertLess(out["nav"], out["html"].index('class="next-cockpit-tabs"'))
        self.assertIn(
            '<strong class="next-cockpit-scope-name">Codex</strong>'
            '<span class="next-cockpit-scope-state">working</span>',
            out["sessionNav"],
        )
        self.assertIn("<small>Shape project cockpit</small>", out["sessionNav"])
        self.assertNotIn("<strong>Shape project cockpit", out["sessionNav"])

    def test_focus_keeps_project_status_and_canonical_labels_from_all_context(self) -> None:
        out = self.run_fixture(
            """
nextCockpitContexts.clear();
const focused = {facts:[
  {fact_id:"task-focus",at:110,type:"prepared_dispatch",summary:"Opaque dispatch",
    source_session:{harness:"pi",sid:"pi-idle"},work_item_id:__task,
    evidence:{source:"dispatch artifact",confidence:"exact"}},
  {fact_id:"gate-focus",at:109,type:"gate_decision",source_kind:"gate",
    summary:"opaque-id · review · approve",scope:"project",by:"person:captain",
    decision:"approve",stage:"review",application_state:"consumed",target_stage:"shaping",
    work_item_id:__task,evidence:{source:"entity gate",confidence:"exact"}}
],work_items:[{work_item_id:__task,label:"opaque-id",kind:"workflow_item"}],
relations:[],projections:{operator_intents:[],steering_episodes:[],trail_heads:[
  {work_item_id:__task,status:"prepared",latest_meaningful_event:"task-focus"}],
activity:{nodes:[{kind:"work",at:110,work_item_ids:[__task]}]}}};
__fetchImpl = async url => ({ok:true,json:async() => ({
  semantic:String(url).includes("session=") ? focused : __semantic,
  child_assignments:[],observers:[]
})});
nextRoute = nextRouteFromFragment("#n=project:cargento:pi%3Api-idle:decisions");
renderNext();
await __settle();await __settle();await __settle();
const html=__els.app.innerHTML;
console.log(JSON.stringify({html,requests:[...nextCockpitContexts.keys()]}));
"""
        )
        assert isinstance(out, dict)

        self.assertTrue(any(key.endswith("\n") for key in out["requests"]))
        self.assertTrue(any(key.endswith("\npi:pi-idle") for key in out["requests"]))
        self.assertIn('data-object="Project cockpit"', out["html"])
        self.assertNotIn('data-object="Opaque id"', out["html"])
        self.assertIn('data-scope-kind="project"', out["html"])
        self.assertIn(">PROJECT</strong>", out["html"])
        self.assertIn(
            "<span>ASSIGNMENT</span><strong>Project cockpit · Shaping</strong>", out["html"]
        )
        self.assertIn('data-next-cockpit-panel="decisions"', out["html"])
        self.assertNotIn("PROJECT OVERVIEW", out["html"])
        self.assertNotIn("All events", out["html"])

    def test_session_permalink_selects_exact_focus_and_decisions_filter_is_present(self) -> None:
        out = self.run_fixture(
            """
nextRoute = nextRouteFromFragment("#n=project:cargento:pi%3Api-idle");
renderNext();
await __settle();
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({html, focus:nextCockpitFocusedSession(nextProjectGroups()[0]) &&
  sessKey(nextCockpitFocusedSession(nextProjectGroups()[0]))}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual("pi:pi-idle", out["focus"])
        self.assertIn('data-next-cockpit-scope="pi:pi-idle"', out["html"])
        self.assertIn('data-next-cockpit-scope="pi:pi-idle" aria-current="page"', out["html"])
        self.assertIn('data-arg="decisions"', out["html"])

    def test_stale_exact_session_permalink_never_falls_back_to_project_scope(self) -> None:
        out = self.run_fixture(
            """
nextData.sessions=nextData.sessions.filter(session=>sessKey(session)!=="pi:pi-idle");
nextRoute=nextRouteFromFragment("#n=project:cargento:pi%3Api-idle:course");
renderNext();await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML,route:nextFragmentForRoute(nextRoute)}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual("#n=project:cargento:pi%3Api-idle:course", out["route"])
        self.assertIn("Session filter is outside this payload window", out["html"])
        self.assertIn('href="#n=project:cargento:course"', out["html"])
        self.assertIn("View project root", out["html"])
        self.assertNotIn("data-next-cockpit-memos", out["html"])
        self.assertNotIn('data-next-cockpit-panel="course"', out["html"])

    def test_decisions_view_preserves_canonical_metadata_and_compacts_scan_line(self) -> None:
        out = self.run_fixture(
            """
nextRoute = nextRouteFromFragment("#n=project:cargento:decisions");
renderNext();
await __settle();await __settle();
const html = __els.app.innerHTML;
const rows = [...html.matchAll(/<article class="pc-graph-row[\\s\\S]*?<\\/article>/g)]
  .map(match => match[0]);
console.log(JSON.stringify({html, rows}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(1, len(out["rows"]))
        self.assertIn('data-semantic-kind="decision"', out["rows"][0])
        self.assertIn('data-actor="You"', out["rows"][0])
        self.assertIn('data-action="approved"', out["rows"][0])
        self.assertIn('data-object="Project cockpit"', out["rows"][0])
        self.assertIn('data-result="review → shaping"', out["rows"][0])
        self.assertIn("<strong>Approved</strong> Project cockpit · applied", out["rows"][0])
        self.assertIn(
            '<div class="pc-source"><b>Decision mechanics</b> · review → shaping · applied</div>',
            out["rows"][0],
        )
        self.assertIn("data-next-cockpit-decision-summary", out["html"])
        self.assertIn("Decision application · consumed/applied 1", out["html"])

    def test_gate_application_state_controls_completed_transition_wording(self) -> None:
        out = self.run_fixture(
            """
const lane = {kind:"task", label:"project-cockpit"};
const sentence = application_state => projectGlobalEventSentence({kind:"decision", fact:{
  type:"gate_decision", by:"person:captain", decision:"approve", stage:"review",
  target_stage:"shaping", application_state
}}, lane);
console.log(JSON.stringify({
  consumed:sentence("consumed"), applied:sentence("applied"),
  pending:sentence("pending"), unspent:sentence("unspent"),
  superseded:sentence("superseded"), unknown:sentence(undefined)
}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual("review → shaping", out["consumed"]["result"])
        self.assertEqual("review → shaping", out["applied"]["result"])
        self.assertEqual(
            "review · decision recorded · pending application", out["pending"]["result"]
        )
        self.assertEqual(
            "review · decision recorded · pending application", out["unspent"]["result"]
        )
        self.assertEqual("review · decision superseded", out["superseded"]["result"])
        self.assertEqual(
            "review · decision recorded · application unknown", out["unknown"]["result"]
        )

    def test_unpromoted_user_fact_never_becomes_a_you_direction(self) -> None:
        out = self.run_fixture(
            """
const semantic = JSON.parse(JSON.stringify(__semantic));
semantic.facts.push({fact_id:"injected",at:106,type:"user_message",
  summary:"Message Type: MESSAGE Sender: /root Payload: keep working",
  intent_promoted:false,source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"injected collaboration envelope",confidence:"exact"}});
const registry = projectLaneRegistry(semantic, [], null, __dashboard.sessions);
const events = projectGlobalEvents(semantic, registry, null);
console.log(JSON.stringify({
  ids:events.map(event => event.eventId),
  sentences:events.map(event => projectGlobalEventSentence(event,
    registry.laneByKey.get(event.lane.key)))
}));
"""
        )
        assert isinstance(out, dict)

        self.assertNotIn("injected", out["ids"])
        self.assertFalse(
            any(
                row["actor"] == "You"
                and row["action"] == "directed"
                and "Message Type" in row["result"]
                for row in out["sentences"]
            )
        )

    def test_project_status_reports_exact_attention_and_collapses_older_captain_decisions(
        self,
    ) -> None:
        out = self.run_fixture(
            """
const facts = [
  {fact_id:"new",at:50,type:"gate_decision",by:"person:captain",decision:"approve",
    stage:"ideation",application_state:"consumed",target_stage:"implementation",work_item_id:"workflow:a"},
  {fact_id:"dupe",at:49,type:"gate_decision",by:"person:captain",decision:"approve",
    stage:"ideation",application_state:"consumed",target_stage:"implementation",work_item_id:"workflow:a"},
  {fact_id:"second",at:48,type:"gate_decision",by:"person:captain",decision:"revise",
    stage:"review",application_state:"pending",target_stage:"shaping",work_item_id:"workflow:b"},
  {fact_id:"third",at:47,type:"gate_decision",by:"person:captain",decision:"hold",
    stage:"validation",application_state:"superseded",target_stage:"validation",work_item_id:"workflow:c"},
  {fact_id:"fo",at:60,type:"gate_decision",by:"agent:first-officer",decision:"approve",
    stage:"validation",target_stage:"done",work_item_id:"workflow:d"}
];
const semantic = {facts, work_items:[
  {work_item_id:"workflow:a",label:"alpha"},{work_item_id:"workflow:b",label:"beta"},
  {work_item_id:"workflow:c",label:"gamma"},{work_item_id:"workflow:d",label:"delta"}
]};
console.log(JSON.stringify({html:nextCockpitProjectStatus(nextProjectGroups()[0], semantic)}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("No gate or ask observed", out["html"])
        self.assertEqual(1, out["html"].count("Alpha · ideation → implementation"))
        self.assertIn("Beta · review · decision recorded · pending application", out["html"])
        self.assertIn("1 older decision", out["html"])
        self.assertIn("Gamma · validation · decision superseded", out["html"])
        self.assertNotIn("Delta", out["html"])

    def test_project_plan_is_after_the_briefing_and_closed_by_default(self) -> None:
        out = self.run_fixture(
            """
const group = nextProjectGroups()[0];
const observation = {semantic:__semantic, workflow_discovery:{state:"observed",workflows:[
  {workflow:"dev",goal:"Discovered workflow outcome",stages:["build"]}
]}};
nextCockpitContexts.set(nextCockpitContextKey(group, null), {data:observation, revision:105});
renderNext();
const discovered = __els.app.innerHTML;
nextCockpitContexts.set(nextCockpitContextKey(group, null), {
  data:{semantic:__semantic,workflow_discovery:{state:"none",workflows:[]}}, revision:105});
renderNext();
console.log(JSON.stringify({discovered,absent:__els.app.innerHTML}));
""",
        )
        assert isinstance(out, dict)

        self.assertLess(
            out["discovered"].index(">Add human context</button>"),
            out["discovered"].index("data-next-cockpit-plan-details"),
        )
        self.assertIn("<summary>Show project plan</summary>", out["discovered"])
        self.assertIn("Discovered workflow outcome", out["discovered"])
        self.assertNotIn("Outcome not recorded", out["absent"])

    def test_recovery_attention_orders_actionable_conditions_and_decision_counts(self) -> None:
        out = self.run_fixture(
            """
const group = nextProjectGroups()[0];
group.sessions[0].state = "needs_input";
const semantic = JSON.parse(JSON.stringify(__semantic));
semantic.facts.push(
  {fact_id:"pending",at:106,type:"gate_decision",by:"person:captain",
    application_state:"pending",work_item_id:__task},
  {fact_id:"unknown",at:105,type:"gate_decision",by:"person:captain",
    work_item_id:__task},
  {fact_id:"retry",at:104,type:"prepared_dispatch",source_kind:"prepared_dispatch",
    work_item_id:"workflow:retry"},
  {fact_id:"retry-again",at:103,type:"prepared_dispatch",source_kind:"prepared_dispatch",
    work_item_id:"workflow:retry"}
);
semantic.projections.trail_heads.push({work_item_id:"workflow:retry",status:"prepared",
  dispatch_count:2,latest_meaningful_event:"retry"});
const observation = {semantic,workflow_discovery:{state:"error",reason:"timed out"},
  sources:{observer:{unavailable:[]}}};
console.log(JSON.stringify({html:nextCockpitRecoveryStrip(group, observation)}));
""",
        )
        assert isinstance(out, dict)
        html = out["html"]

        self.assertLess(
            html.index("inspect Codex input request"), html.index("refresh workflow discovery")
        )
        self.assertLess(
            html.index("refresh workflow discovery"), html.index("inspect assignment return")
        )
        self.assertLess(html.index("inspect assignment return"), html.index("inspect idle owner"))
        self.assertNotIn("pending 1", html)
        self.assertNotIn("unknown 1", html)
        self.assertNotIn("consumed/applied 1", html)
        self.assertNotIn("<span>DECISIONS</span>", html)
        self.assertNotIn("decision application", html)
        self.assertNotIn("blocker", html.casefold())

    def test_command_attention_leads_with_exact_authorization_and_assigns_fo_recovery(self) -> None:
        out = self.run_fixture(
            """
const group = nextProjectGroups()[0];
const semantic = JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention = [{projection_id:"auth",at:109,
  owner:"CAPTAIN",kind:"push_pr",label:"The completion-guard error names the failing sub-check",
  question:"Approve pushing this candidate and creating the PR?",
  evidence:{source:"assistant final_answer followed by terminal turn state",confidence:"exact"}}];
semantic.facts.push({fact_id:"pending",at:108,type:"gate_decision",by:"person:captain",
  application_state:"pending",work_item_id:__task});
semantic.projections.trail_heads.push({work_item_id:"workflow:return",status:"prepared",
  dispatch_count:2,latest_meaningful_event:"return"});
const observation = {semantic,workflow_discovery:{state:"error",reason:"timed out"},sources:{}};
const items = nextCockpitCommandAttention(group, observation);
console.log(JSON.stringify({items,html:nextCockpitRecoveryStrip(group, observation, items)}));
""",
        )
        assert isinstance(out, dict)

        self.assertEqual("CAPTAIN", out["items"][0]["owner"])
        self.assertEqual(
            "Approve pushing this candidate and creating the PR?", out["items"][0]["label"]
        )
        self.assertTrue(all(row["owner"] == "FO" for row in out["items"][1:]))
        self.assertIn("assistant final_answer followed by terminal turn state", out["html"])
        self.assertIn("exact", out["html"])
        self.assertLess(out["html"].index("CAPTAIN ·"), out["html"].index("FO ·"))

    def test_incomplete_attention_coverage_suppresses_nothing_needs_you(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention=[];
semantic.projections.command_attention_coverage={state:"incomplete",scanned:64,total:65,
  omitted:1,source:"bounded active-session final-output scan"};
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const items=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({items,html:nextCockpitNeedsYou(items)}));
"""
        )
        assert isinstance(out, dict)

        self.assertTrue(
            any(
                row["owner"] == "FO"
                and row["kind"] == "coverage_inspection"
                and row["label"] == "complete captain-attention scan"
                for row in out["items"]
            )
        )
        self.assertIn("Captain-attention coverage incomplete", out["html"])
        self.assertNotIn("Nothing needs you", out["html"])

    def test_attention_empty_state_requires_authoritative_complete_context(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const key=nextCockpitContextKey(group,null);
const semantic=JSON.parse(JSON.stringify(__semantic));
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.clear();nextCockpitRequests.set(key,nextData.generated);
const loading=nextCockpitCommandAttention(group,null);
nextCockpitRequests.clear();nextCockpitContexts.set(key,{data:observation,
  revision:nextData.generated,error:true});
const failed=nextCockpitCommandAttention(group,observation);
const missingObservation={semantic:{facts:[],work_items:[],projections:{command_attention:[]}},
  workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(key,{data:missingObservation,revision:nextData.generated});
const missing=nextCockpitCommandAttention(group,missingObservation);
semantic.projections.command_attention_coverage={state:"incomplete",scanned:64,total:65,
  omitted:1,source:"bounded active-session final-output scan"};
nextCockpitContexts.set(key,{data:observation,revision:nextData.generated});
const incomplete=nextCockpitCommandAttention(group,observation);
semantic.projections.command_attention_coverage={state:"complete",scanned:3,total:3,
  omitted:0,source:"bounded active-session final-output scan"};
const complete=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({loading,failed,missing,incomplete,complete,
  loadingHtml:nextCockpitNeedsYou(loading),failedHtml:nextCockpitNeedsYou(failed),
  missingHtml:nextCockpitNeedsYou(missing),incompleteHtml:nextCockpitNeedsYou(incomplete),
  completeHtml:nextCockpitNeedsYou(complete),
  completeRecovery:nextCockpitRecoveryAttention(group,observation,complete)}));
"""
        )
        assert isinstance(out, dict)

        for key in ("loading", "failed", "missing"):
            guard = [row for row in out[key] if row["kind"] == "coverage_inspection"]
            self.assertEqual("refresh captain-attention scan", guard[0]["label"])
            self.assertIn("Captain attention unavailable", out[f"{key}Html"])
            self.assertNotIn("Nothing needs you", out[f"{key}Html"])
        self.assertTrue(
            any(row["label"] == "complete captain-attention scan" for row in out["incomplete"])
        )
        self.assertNotIn("Nothing needs you", out["incompleteHtml"])
        self.assertEqual([], [row for row in out["complete"] if row["owner"] == "CAPTAIN"])
        self.assertIn("Nothing needs you", out["completeHtml"])
        self.assertIn("Coverage complete", out["completeRecovery"])
        self.assertIn("3 of 3 active sessions", out["completeRecovery"])

    def test_recovery_briefing_is_mounted_above_tabs_with_observed_handoff(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.push(
  {fact_id:"latest-direction",at:111,type:"user_message",summary:"Keep exact recovery",
    source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}},
  {fact_id:"latest-result",at:112,type:"result",summary:"Checkpoint c510e61 is live",
    source_session:{harness:"codex",sid:"focus-1"},work_item_id:__task,
    evidence:{source:"assistant final",confidence:"exact"}},
  {fact_id:"pending-decision",at:113,type:"gate_decision",by:"person:captain",
    application_state:"pending",work_item_id:__task}
);
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitMemoDrafts.set(nextCockpitMemoKey(group,null,"outcome"),"Recover after a crash");
nextCockpitMemoDrafts.set(nextCockpitMemoKey(group,null,"focus"),"Verify authoritative state");
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});
renderNext();
const html=__els.app.innerHTML;
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
console.log(JSON.stringify({html,recovery,strip:html.indexOf("next-cockpit-recovery"),
  tabs:html.indexOf("next-cockpit-tabs"),tabCount:(html.match(/role="tab"/g)||[]).length,
  copyCount:(html.match(/data-next-cockpit-action="copy-briefing"/g)||[]).length}));
"""
        )
        assert isinstance(out, dict)

        self.assertGreaterEqual(out["strip"], 0)
        self.assertLess(out["strip"], out["tabs"])
        self.assertEqual(4, out["tabCount"])
        self.assertEqual(1, out["copyCount"])
        for text in (
            "Recover after a crash",
            "Verify authoritative state",
            "Banach · active",
            "Copernicus · active",
            "Project cockpit · Shaping",
            "Keep exact recovery",
            "Checkpoint c510e61 is live",
            "Coverage complete",
        ):
            self.assertIn(text, out["recovery"])

    def test_recovery_preserves_active_child_with_unavailable_assignment(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_hierarchy=[{name:"Hooke",observer_sid:"child-hooke",depth:1,
  assignment:null,assignment_status:"unavailable"}];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({attention,
  briefing:nextCockpitRecoveryBriefing(group,null,observation,attention),
  html:nextCockpitRecoveryStrip(group,observation,attention)}));
"""
        )
        assert isinstance(out, dict)

        for text in ("Hooke", "active", "assignment unavailable", "codex:focus-1"):
            self.assertIn(text, out["html"])
            self.assertIn(text, out["briefing"]["text"])
        self.assertTrue(
            any(
                row["owner"] == "FO" and row["label"] == "inspect Hooke assignment"
                for row in out["attention"]
            )
        )

    def test_recovery_preserves_bounded_latest_return_with_unavailable_result(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_events=[
  {at:110,kind:"subagent_complete",name:"Hooke",source:"Codex child rollout lifecycle"},
  {at:112,kind:"subagent_complete",name:"Harvey",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({attention,
  briefing:nextCockpitRecoveryBriefing(group,null,observation,attention),
  html:nextCockpitRecoveryStrip(group,observation,attention)}));
"""
        )
        assert isinstance(out, dict)

        for text in (
            "Harvey",
            "returned",
            "assignment unavailable",
            "result unavailable",
            "codex:focus-1",
        ):
            self.assertIn(text, out["html"])
            self.assertIn(text, out["briefing"]["text"])
        self.assertNotIn("Hooke", out["html"])
        self.assertTrue(
            any(
                row["owner"] == "FO" and "recover Harvey handoff" in row["label"]
                for row in out["attention"]
            )
        )

    def test_copy_briefing_names_bounded_attention_coverage_source(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});
const briefing=nextCockpitRecoveryBriefing(group,null,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("bounded active-session final-output scan", value)
        self.assertIn("FO CONTINUES", out["html"])

    def test_failed_refresh_marks_retained_exact_facts_stale(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.push(
  {fact_id:"cached-direction",at:111,type:"user_message",summary:"Cached direction",
    source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}},
  {fact_id:"cached-result",at:112,type:"result",summary:"Cached result",
    source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"assistant final",confidence:"exact"}}
);
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated,error:true});
const briefing=nextCockpitRecoveryBriefing(group,null,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation)}));
"""
        )
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("stale cached", value.casefold())
            self.assertIn("Cached direction", value)
            self.assertIn("Cached result", value)
        self.assertNotIn("LATEST EXACT</span>", out["html"])

    def test_command_attention_sorts_captain_before_fo_independent_of_payload_order(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention=[
  {owner:"FO",kind:"recovery",label:"Verify system state",question:"Verify system state",
    evidence:{source:"workflow",confidence:"exact"}},
  {owner:"CAPTAIN",kind:"authorization",label:"Choose the route",question:"Choose the route",
    evidence:{source:"captain gate",confidence:"exact"}}
];
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const items=nextCockpitCommandAttention(group,observation);
const html=nextCockpitRecoveryAttention(group,observation,items);
console.log(JSON.stringify({items,html}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual("CAPTAIN", out["items"][0]["owner"])
        self.assertTrue(all(row["owner"] == "FO" for row in out["items"][1:]))
        self.assertLess(out["html"].index("CAPTAIN ·"), out["html"].index("FO ·"))

    def test_recovery_excludes_non_promotable_acknowledgment_from_actionable_direction(
        self,
    ) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.push(
  {fact_id:"actionable",at:111,type:"user_message",summary:"Verify the live candidate",
    intent_promoted:true,source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}},
  {fact_id:"ack",at:112,type:"user_message",summary:"great.",intent_promoted:false,
    source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}}
);
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("Verify the live candidate", value)
            self.assertNotIn("great.", value)
        self.assertIn("LATEST ACTIONABLE DIRECTION", out["html"])

    def test_recovery_assignment_prefers_substantive_root_work_over_later_mechanism(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.trail_heads=[];
semantic.facts=semantic.facts.filter(fact=>fact.type!=="user_message");
semantic.facts.push(
  {fact_id:"substantive",at:110,type:"user_message",summary:"restart 5-round review loop",
    intent_promoted:true,source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}},
  {fact_id:"mechanism",at:111,type:"user_message",
    summary:"this is not codex's builtin browser, but playwright-chrome",
    intent_promoted:true,source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}},
  {fact_id:"ack",at:112,type:"user_message",summary:"great.",intent_promoted:false,
    source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}}
);
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({briefing,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )
        assert isinstance(out, dict)

        for value in (out["briefing"]["text"], out["html"]):
            self.assertIn("Restart 5-round review loop", value)
            self.assertIn("Exact operator direction", value)
            self.assertIn("Stage link missing · current work can continue", value)
            self.assertNotIn("playwright-chrome", value)
            self.assertNotIn("task, outcome, stage, done condition", value)

    def test_deterministic_assignment_recovery_does_not_create_fo_verification(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){
  session.state="working";session.last_activity=nextData.generated;
  session.subagent_hierarchy=[];session.subagent_events=[];
}
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.trail_heads=[];
semantic.facts=semantic.facts.filter(fact=>fact.type!=="user_message");
semantic.facts.push({fact_id:"substantive",at:110,type:"user_message",
  summary:"restart 5-round review loop",intent_promoted:true,
  source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"root transcript",confidence:"exact"}});
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({attention,
  html:nextCockpitRecoveryStrip(group,observation,attention)}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("Restart 5-round review loop", out["html"])
        self.assertFalse(
            any(row["owner"] == "FO" and "assignment" in row["label"] for row in out["attention"])
        )

    def test_named_missing_child_handoff_gets_one_concrete_fo_inspection(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_events=[
  {at:112,kind:"subagent_complete",name:"Harvey",assignment:"Review the mirror",
    source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({attention,
  html:nextCockpitRecoveryAttention(group,observation,attention)}));
"""
        )
        assert isinstance(out, dict)

        harvey = [row for row in out["attention"] if "Harvey" in row["label"]]
        self.assertEqual(1, len(harvey))
        self.assertEqual("FO", harvey[0]["owner"])
        self.assertEqual("inspect Harvey handoff", harvey[0]["label"])
        self.assertNotIn("verify Harvey", out["html"])

    def test_explicit_captain_request_is_exact_and_empty_scan_is_named(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention=[
  {owner:"CAPTAIN",kind:"authorization",label:"route label",
    question:"Choose whether to ship checkpoint abc1234.",
    evidence:{source:"captain gate",confidence:"exact"}},
  {owner:"FO",kind:"recovery",label:"inspect observer",
    evidence:{source:"observer",confidence:"exact"}}
];
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const attention=nextCockpitCommandAttention(group,observation);
semantic.projections.command_attention=[];
const empty=nextCockpitRecoveryAttention(group,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({attention,
  html:nextCockpitRecoveryAttention(group,observation,attention),empty}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual("Choose whether to ship checkpoint abc1234.", out["attention"][0]["label"])
        self.assertLess(out["html"].index("CAPTAIN ·"), out["html"].index("FO ·"))
        self.assertIn("FO INSPECTING", out["empty"])

    def test_authority_cell_has_one_of_three_explicit_states(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){
  session.state="working";session.last_activity=nextData.generated;
  session.subagent_hierarchy=[];session.subagent_events=[];
}
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const continues=nextCockpitRecoveryAttention(group,observation,[]);
const inspecting=nextCockpitRecoveryAttention(group,observation,[
  {owner:"FO",kind:"recovery",label:"inspect Harvey handoff",
    evidence:{source:"child lifecycle",confidence:"exact"}}
]);
const needed=nextCockpitRecoveryAttention(group,observation,[
  {owner:"CAPTAIN",kind:"authorization",label:"Approve checkpoint abc1234?",
    question:"Approve checkpoint abc1234?",evidence:{source:"exact request",confidence:"exact"}}
]);
console.log(JSON.stringify({continues,inspecting,needed}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn('data-next-cockpit-authority-state="fo-continues"', out["continues"])
        self.assertIn("FO CONTINUES", out["continues"])
        self.assertNotIn("captain request", out["continues"].casefold())
        self.assertIn('data-next-cockpit-authority-state="fo-inspecting"', out["inspecting"])
        self.assertIn("FO INSPECTING", out["inspecting"])
        self.assertIn('data-next-cockpit-authority-state="captain-needed"', out["needed"])
        self.assertIn("CAPTAIN NEEDED", out["needed"])

    def test_captain_attention_preserves_kind_and_renders_compact_verbs(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention=[
  {owner:"CAPTAIN",kind:"authorization",question:"Approve checkpoint?",
    evidence:{source:"request",confidence:"exact"}},
  {owner:"CAPTAIN",kind:"ask",question:"What evidence is required?",
    evidence:{source:"ask",confidence:"exact"}},
  {owner:"CAPTAIN",kind:"choice",question:"Choose deck or ledger.",
    evidence:{source:"gate",confidence:"exact"}},
  {owner:"CAPTAIN",kind:"revision",question:"Revise the scope statement?",
    evidence:{source:"review",confidence:"exact"}}
];
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const items=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({items,html:nextCockpitRecoveryAttention(group,observation,items)}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(
            ["authorization", "ask", "choice", "revision"],
            [row["kind"] for row in out["items"] if row["owner"] == "CAPTAIN"],
        )
        for verb in ("AUTHORIZE", "ANSWER", "CHOOSE", "REVISE"):
            self.assertIn(verb, out["html"])

    def test_source_unavailable_is_fo_inspection_evidence_not_an_actor(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_hierarchy=[{name:"Harvey",observer_sid:"child-h",depth:1}];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const items=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({items,html:nextCockpitRecoveryAttention(group,observation,items)}));
"""
        )
        assert isinstance(out, dict)

        self.assertFalse(any(row["owner"] == "SOURCE" for row in out["items"]))
        self.assertTrue(
            any(
                row["owner"] == "FO" and row["label"] == "inspect Harvey assignment"
                for row in out["items"]
            )
        )
        self.assertIn("FO INSPECTING", out["html"])
        self.assertNotIn("SOURCE ·", out["html"])

    def test_authority_cell_shows_all_captain_one_fo_and_discloses_remainder(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const items=[
  {owner:"CAPTAIN",kind:"authorization",label:"Approve A?",question:"Approve A?",
    evidence:{source:"a",confidence:"exact"}},
  {owner:"CAPTAIN",kind:"choice",label:"Choose B.",question:"Choose B.",
    evidence:{source:"b",confidence:"exact"}},
  {owner:"FO",kind:"recovery",label:"inspect first",evidence:{source:"one",confidence:"exact"}},
  {owner:"FO",kind:"recovery",label:"inspect second",evidence:{source:"two",confidence:"exact"}},
  {owner:"FO",kind:"recovery",label:"inspect third",evidence:{source:"three",confidence:"exact"}}
];
console.log(JSON.stringify({html:nextCockpitRecoveryAttention(group,observation,items)}));
"""
        )
        assert isinstance(out, dict)

        primary = out["html"].split("<details", maxsplit=1)[0]
        self.assertIn("Approve A?", primary)
        self.assertIn("Choose B.", primary)
        self.assertIn("inspect first", primary)
        self.assertNotIn("inspect second", primary)
        self.assertNotIn("inspect third", primary)
        self.assertIn("2 more FO actions", out["html"])

    def test_failed_and_incomplete_coverage_are_fo_inspecting_not_captain_needed(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const key=nextCockpitContextKey(group,null);
const semantic=JSON.parse(JSON.stringify(__semantic));
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(key,{data:observation,revision:nextData.generated,error:true});
const failedItems=nextCockpitCommandAttention(group,observation);
const failed=nextCockpitRecoveryAttention(group,observation,failedItems);
nextCockpitContexts.set(key,{data:observation,revision:nextData.generated});
semantic.projections.command_attention_coverage={state:"incomplete",scanned:2,total:3,
  omitted:1,source:"bounded attention scan"};
const incompleteItems=nextCockpitCommandAttention(group,observation);
const incomplete=nextCockpitRecoveryAttention(group,observation,incompleteItems);
console.log(JSON.stringify({failedItems,failed,incompleteItems,incomplete}));
"""
        )
        assert isinstance(out, dict)

        for key in ("failed", "incomplete"):
            self.assertIn("FO INSPECTING", out[key])
            self.assertNotIn("CAPTAIN NEEDED", out[key])
        for key in ("failedItems", "incompleteItems"):
            self.assertFalse(any(row["owner"] == "SOURCE" for row in out[key]))

    def test_pending_decision_is_fo_application_until_a_fresh_question_exists(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention=[
  {owner:"CAPTAIN",kind:"hold",label:"Hold recorded",
    evidence:{source:"decision history",confidence:"exact"}}
];
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const pendingItems=nextCockpitCommandAttention(group,observation);
const pending=nextCockpitRecoveryAttention(group,observation,pendingItems);
semantic.projections.command_attention=[
  {owner:"CAPTAIN",kind:"revision",label:"Revision requested",
    question:"Revise the assignment boundary?",
    evidence:{source:"fresh review question",confidence:"exact"}}
];
const freshItems=nextCockpitCommandAttention(group,observation);
const fresh=nextCockpitRecoveryAttention(group,observation,freshItems);
console.log(JSON.stringify({pendingItems,pending,freshItems,fresh}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual([], [row for row in out["pendingItems"] if row["owner"] == "CAPTAIN"])
        self.assertTrue(
            any(
                row["owner"] == "FO" and "apply recorded hold" in row["label"]
                for row in out["pendingItems"]
            )
        )
        self.assertIn("FO INSPECTING", out["pending"])
        self.assertIn("CAPTAIN NEEDED", out["fresh"])
        self.assertIn("REVISE", out["fresh"])

    def test_stage_link_copy_states_only_proven_operational_effect(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.trail_heads=[];
semantic.facts=semantic.facts.filter(fact=>fact.type!=="user_message");
semantic.facts.push({fact_id:"direction",at:110,type:"user_message",
  summary:"restart 5-round review loop",intent_promoted:true,
  source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"root transcript",confidence:"exact"}});
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const continues=nextCockpitRecoveryStrip(group,observation,[]);
semantic.projections.command_attention=[{owner:"FO",kind:"stage_link_required",
  label:"link stage",blocked_step:"dispatch reviewer",
  evidence:{source:"workflow handoff",confidence:"exact"}}];
const blocked=nextCockpitRecoveryStrip(group,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({continues,blocked}));
"""
        )
        assert isinstance(out, dict)

        continues_task = out["continues"].split("MISSING / NEXT ACTION", maxsplit=1)[0]
        blocked_task = out["blocked"].split("MISSING / NEXT ACTION", maxsplit=1)[0]
        self.assertIn("Stage link missing · current work can continue", continues_task)
        self.assertIn("Stage link required before dispatch reviewer", blocked_task)
        self.assertNotIn("Workflow stage not linked", out["continues"])
        self.assertNotIn("Workflow stage not linked", out["blocked"])
        self.assertNotIn(
            "Exact operator direction", continues_task.split("<details", maxsplit=1)[0]
        )

    def test_fresh_return_age_moves_to_evidence_while_stale_age_remains_primary(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
nextData.generated=1000;
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
group.sessions[0].subagent_events=[{at:978,kind:"subagent_complete",name:"Harvey",
  assignment:"Review mirror",result:"Returned",source:"lifecycle"}];
const fresh=nextCockpitRecoveryExecution(group,
  nextCockpitRecoveryBriefing(group,null,observation,[]));
group.sessions[0].subagent_events=[{at:1,kind:"subagent_complete",name:"Harvey",
  assignment:"Review mirror",result:"Returned",source:"lifecycle"}];
const stale=nextCockpitRecoveryExecution(group,
  nextCockpitRecoveryBriefing(group,null,observation,[]));
console.log(JSON.stringify({fresh,stale}));
"""
        )
        assert isinstance(out, dict)

        fresh_primary = out["fresh"].split("<details", maxsplit=1)[0]
        stale_primary = out["stale"].split("<details", maxsplit=1)[0]
        self.assertNotIn("22s", fresh_primary)
        self.assertIn("22s", out["fresh"])
        self.assertIn("stale", stale_primary)

    def test_returned_handoff_unavailable_is_inline_and_commands_recovery(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
group.sessions=[group.sessions[0]];
group.sessions[0].subagent_hierarchy=[];
group.sessions[0].subagent_events=[{at:112,kind:"subagent_complete",name:"Harvey",
  source:"Codex child rollout lifecycle"}];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const attention=nextCockpitCommandAttention(group,observation);
const briefing=nextCockpitRecoveryBriefing(group,null,observation,attention);
console.log(JSON.stringify({attention,
  execution:nextCockpitRecoveryExecution(group,briefing),
  command:nextCockpitRecoveryAttention(group,observation,attention)}));
"""
        )
        assert isinstance(out, dict)

        self.assertTrue(any(row["label"] == "recover Harvey handoff" for row in out["attention"]))
        self.assertIn("Harvey · returned · handoff unavailable", out["execution"])
        self.assertIn("INSPECT · recover Harvey handoff", out["command"])

    def test_recovery_cells_put_situation_before_command_with_four_truths_inline(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
group.sessions=[group.sessions[0]];
group.sessions[0].subagent_hierarchy=[];
group.sessions[0].subagent_events=[{at:112,kind:"subagent_complete",name:"Harvey",
  source:"Codex child rollout lifecycle"}];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.trail_heads=[];
semantic.facts=semantic.facts.filter(fact=>fact.type!=="user_message");
semantic.facts.push({fact_id:"direction",at:110,type:"user_message",
  summary:"restart 5-round review loop",intent_promoted:true,
  source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"root transcript",confidence:"exact"}});
semantic.projections.command_attention_coverage={state:"complete",scanned:1,total:1,
  omitted:0,source:"bounded attention scan"};
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const attention=nextCockpitCommandAttention(group,observation);
const html=nextCockpitRecoveryStrip(group,observation,attention);
const primary=html.replace(/<details[^>]*>[\\s\\S]*?<\\/details>/g,"");
console.log(JSON.stringify({html,primary}));
"""
        )
        assert isinstance(out, dict)

        positions = [
            out["primary"].index(label) for label in ("ASSIGNMENT", "EXECUTION", "COMMAND")
        ]
        self.assertEqual(sorted(positions), positions)
        for truth in (
            "Restart 5-round review loop",
            "Stage link missing · current work can continue",
            "Codex · working",
            "Harvey · returned · handoff unavailable",
            "FO INSPECTING",
            "INSPECT · recover Harvey handoff",
            "Captain not needed",
        ):
            self.assertIn(truth, out["primary"])

    def test_idle_fo_continues_collapses_to_two_truthful_handoff_lines(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
group.sessions=[group.sessions[0]];
group.sessions[0].state="idle";
group.sessions[0].subagent_hierarchy=[];group.sessions[0].subagent_events=[];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention_coverage={state:"complete",scanned:1,total:1,
  omitted:0,source:"bounded attention scan"};
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const html=nextCockpitRecoveryStrip(group,observation,[]);
const primary=html.replace(/<details[^>]*>[\\s\\S]*?<\\/details>/g,"");
console.log(JSON.stringify({primary}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("FO CONTINUES · Continue current assignment", out["primary"])
        self.assertIn("No execution observed · Captain not needed", out["primary"])
        self.assertNotIn("Codex · working", out["primary"])

    def test_single_session_collapses_scope_while_multi_session_keeps_permalinks(self) -> None:
        out = self.run_fixture(
            """
const multi=__els.app.innerHTML;
nextData.sessions=[nextData.sessions[0]];
nextRoute=nextRouteFromFragment("#n=project:cargento");renderNext();
await __settle();await __settle();
const single=__els.app.innerHTML;
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1");renderNext();
await __settle();await __settle();
console.log(JSON.stringify({multi,single,selected:__els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn('class="next-cockpit-scope-tree"', out["multi"])
        self.assertIn('data-next-cockpit-scope="pi:pi-idle"', out["multi"])
        self.assertNotIn('class="next-cockpit-scope-tree"', out["single"])
        self.assertIn("next-cockpit-shell--single", out["single"])
        self.assertNotIn('class="next-cockpit-scope-tree"', out["selected"])
        self.assertIn("Viewing session · Codex · working", out["selected"])
        self.assertIn("PROJECT RECOVERY BRIEFING", out["selected"])

    def test_empty_plan_and_context_are_conditionally_subtracted(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const exact={semantic:__semantic,workflow_discovery:{state:"observed",workflows:[]},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:exact,revision:nextData.generated});
renderNext();const quiet=__els.app.innerHTML;
const discovered={semantic:__semantic,workflow_discovery:{state:"observed",workflows:[
  {workflow:"dev",goal:"Discovered plan",stages:["build"]}]},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:discovered,revision:nextData.generated});
renderNext();const planned=__els.app.innerHTML;
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.trail_heads=[];semantic.work_items=[];
semantic.projections.command_attention_coverage={state:"incomplete",scanned:2,total:3,omitted:1,
  source:"bounded attention scan"};
const unknown={semantic,workflow_discovery:{state:"none",workflows:[]},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:unknown,revision:nextData.generated});
renderNext();const incomplete=__els.app.innerHTML;
console.log(JSON.stringify({quiet,planned,incomplete}));
"""
        )
        assert isinstance(out, dict)

        self.assertNotIn("Show project plan", out["quiet"])
        self.assertNotIn("+ Add human context · this browser", out["quiet"])
        self.assertIn('data-next-cockpit-action="memo-edit"', out["quiet"])
        self.assertIn("Show project plan", out["planned"])
        self.assertIn("Discovered plan", out["planned"])
        self.assertIn("+ Add human context · this browser", out["incomplete"])

    def test_project_utilities_demote_copy_global_count_and_duplicate_breadcrumb(self) -> None:
        out = self.run_fixture(
            """
const html=__els.app.innerHTML;
const header=(html.match(/<header class="next-header">[\\s\\S]*?<\\/header>/)||[""])[0];
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
const beforeMenu=header.split('<details class="next-menu"',1)[0];
console.log(JSON.stringify({html,header,recovery,beforeMenu}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn('data-next-cockpit-action="copy-briefing"', out["header"])
        self.assertNotIn('data-next-cockpit-action="copy-briefing"', out["recovery"])
        self.assertNotIn("All projects", out["beforeMenu"])
        self.assertIn("All projects", out["header"])
        self.assertNotIn("spacedock-research/cargento", out["header"])
        self.assertEqual(1, out["html"].count('class="next-project-detail-name"'))
        self.assertNotIn("&gt; </span><span>cargento</span>", out["header"])

    def test_result_fallback_requires_same_session_affinity(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
group.sessions[0].last_output="Linked root result";group.sessions[0].last_activity=110;
group.sessions[1].last_output="Unrelated Pi output";group.sessions[1].last_activity=120;
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.trail_heads=[];
semantic.facts=semantic.facts.filter(fact=>!['user_message','result'].includes(fact.type));
semantic.facts.push(
  {fact_id:"substantive",at:109,type:"user_message",summary:"restart 5-round review loop",
    intent_promoted:true,source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}},
  {fact_id:"unrelated-result",at:121,type:"result",summary:"Unrelated semantic result",
    source_session:{harness:"pi",sid:"pi-idle"},
    evidence:{source:"assistant final",confidence:"exact"}}
);
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("Linked root result", value)
            self.assertNotIn("Unrelated Pi output", value)
            self.assertNotIn("Unrelated semantic result", value)

    def test_ancient_returned_child_is_qualified_stale(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
nextData.generated=1000;
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_events=[
  {at:1,kind:"subagent_complete",name:"Harvey",assignment:"Review mirror",
    result:"Review returned",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryExecution(group,briefing)}));
"""
        )
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("Harvey · returned", value)
            self.assertIn("stale", value)

    def test_recovery_uses_attributable_session_output_when_semantic_result_is_absent(
        self,
    ) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
group.sessions[0].last_output="Candidate verification completed\\n\\nDetailed verification transcript";
group.sessions[0].last_activity=120;
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts=semantic.facts.filter(fact=>fact.type!=="result");
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("Candidate verification completed", value)
            self.assertIn("latest session result", value.casefold())
        self.assertIn("codex:focus-1", out["text"])
        self.assertIn("session output; semantic result not captured", out["text"])
        self.assertIn("Detailed verification transcript", out["text"])
        start = out["html"].index("LATEST ACTIONABLE DIRECTION")
        disclosure = out["html"].find("<details", start)
        self.assertGreater(disclosure, start)
        primary = out["html"][start:disclosure]
        evidence = out["html"][disclosure : out["html"].index("</details>", disclosure)]
        self.assertNotIn("codex:focus-1", primary)
        self.assertNotIn("Detailed verification transcript", primary)
        self.assertIn("Evidence", evidence)
        self.assertIn("codex:focus-1", evidence)
        self.assertIn("session output; semantic result not captured", evidence)

    def test_recovery_promotes_first_fo_action_when_captain_is_empty(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){
  session.state="working";session.last_activity=1000;
  session.subagent_hierarchy=[];session.subagent_events=[];
}
group.sessions[0].subagent_events=[
  {at:112,kind:"subagent_complete",name:"Hooke",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const items=nextCockpitCommandAttention(group,observation);
items.push({owner:"FO",label:"verify source refresh",
  evidence:{source:"context",confidence:"exact"}});
const html=nextCockpitRecoveryAttention(group,observation,items);
console.log(JSON.stringify({items,html}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual("recover Hooke handoff", out["items"][0]["label"])
        self.assertLess(
            out["html"].index("FO INSPECTING"),
            out["html"].index("INSPECT · recover Hooke handoff"),
        )
        self.assertIn("FO · attention · verify source refresh", out["html"])
        self.assertIn("bounded active-session final-output scan", out["html"])

    def test_empty_recovery_memos_collapse_to_one_add_context_action(self) -> None:
        out = self.run_fixture(
            """
const html=__els.app.innerHTML;
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
console.log(JSON.stringify({recovery,
  memoEdits:(recovery.match(/data-next-cockpit-action="memo-edit"/g)||[]).length}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(0, out["memoEdits"])
        self.assertNotIn("Add human context", out["recovery"])

    def test_recovery_reading_order_puts_assignment_action_and_execution_first(self) -> None:
        out = self.run_fixture(
            """
const recovery=(__els.app.innerHTML.match(
  /<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
console.log(JSON.stringify({recovery}));
"""
        )
        assert isinstance(out, dict)

        ordered = [
            "ASSIGNMENT",
            "EXECUTION",
            "COMMAND",
            "FO INSPECTING",
            "LATEST EVIDENCE",
        ]
        positions = [out["recovery"].index(label) for label in ordered]
        self.assertEqual(sorted(positions), positions)

    def test_missing_child_evidence_is_consolidated_into_owned_actions(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){
  session.state="idle";session.subagent_hierarchy=[];session.subagent_events=[];
}
group.sessions[0].state="working";
group.sessions[0].subagent_hierarchy=[{name:"Ohm",observer_sid:"child-ohm",depth:1}];
group.sessions[0].subagent_events=[
  {at:112,kind:"subagent_complete",name:"Harvey",source:"Codex child rollout lifecycle"}
];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.trail_heads=[];
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const html=nextCockpitRecoveryStrip(group,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({html}));
"""
        )
        assert isinstance(out, dict)

        self.assertNotIn("task, outcome, stage, done condition", out["html"])
        self.assertIn("FO INSPECTING", out["html"])
        self.assertIn("inspect Ohm assignment", out["html"])
        self.assertIn("recover Harvey handoff", out["html"])
        execution = (
            out["html"].split("EXECUTION", maxsplit=1)[1].split("LATEST EVIDENCE", maxsplit=1)[0]
        )
        self.assertNotIn("assignment missing", execution)
        self.assertNotIn("assignment/result missing", execution)

    def test_optional_memo_is_subordinate_and_edit_on_demand(self) -> None:
        out = self.run_fixture(
            """
const recovery=(__els.app.innerHTML.match(
  /<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
console.log(JSON.stringify({recovery,
  edits:(recovery.match(/data-next-cockpit-action="memo-edit"/g)||[]).length}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("LATEST EVIDENCE", out["recovery"])
        self.assertNotIn("Add human context", out["recovery"])
        self.assertEqual(0, out["edits"])
        self.assertNotIn("OUTCOME / FOCUS · THIS BROWSER", out["recovery"])

    def test_empty_decisions_are_subtracted_from_recovery_primary_cells(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts=semantic.facts.filter(fact=>fact.type!=="gate_decision");
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const recovery=nextCockpitRecoveryStrip(group,observation,[]);
console.log(JSON.stringify({recovery}));
"""
        )
        assert isinstance(out, dict)

        self.assertNotIn("<span>DECISIONS</span>", out["recovery"])
        self.assertNotIn("No captain decisions observed", out["recovery"])

    def test_execution_groups_plain_child_rows_under_one_root(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_hierarchy=[{name:"Ohm",observer_sid:"child-ohm",depth:1}];
group.sessions[0].subagent_events=[
  {at:112,kind:"subagent_complete",name:"Harvey",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const html=nextCockpitRecoveryStrip(group,observation,
  nextCockpitCommandAttention(group,observation));
const execution=html.slice(html.indexOf("EXECUTION"),html.indexOf("LATEST EVIDENCE"));
console.log(JSON.stringify({execution}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(1, out["execution"].count("Codex · working"))
        self.assertIn("Ohm · active", out["execution"])
        self.assertIn("Harvey · returned", out["execution"])
        self.assertNotIn("next-scope-cue", out["execution"])
        self.assertNotIn("SESSION", out["execution"])

    def test_returned_child_primary_hides_identifiers_and_discloses_evidence(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_events=[
  {at:112,kind:"subagent_complete",name:"Harvey",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
const html=nextCockpitRecoveryStrip(group,observation,
  nextCockpitCommandAttention(group,observation));
const start=html.indexOf("Harvey · returned");
const disclosure=html.indexOf("<details",start);
const end=html.indexOf("</details>",disclosure);
console.log(JSON.stringify({primary:html.slice(start,disclosure),
  evidence:html.slice(disclosure,end)}));
"""
        )
        assert isinstance(out, dict)

        self.assertNotIn("assignment/result missing", out["primary"])
        self.assertNotIn("codex:focus-1", out["primary"])
        self.assertIn("Evidence", out["evidence"])
        self.assertIn("assignment unavailable", out["evidence"])
        self.assertIn("result unavailable", out["evidence"])
        self.assertIn("codex:focus-1", out["evidence"])

    def test_mounted_briefing_subtracts_duplicate_now_cards(self) -> None:
        out = self.run_fixture(
            """
const html=__els.app.innerHTML;
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
const panel=html.slice(html.indexOf('data-next-cockpit-panel="now"'));
console.log(JSON.stringify({html,recovery,panel,
  recoveryCount:(html.match(/class="next-cockpit-recovery"/g)||[]).length,
  memoEdits:(recovery.match(/data-next-cockpit-action="memo-edit"/g)||[]).length}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(1, out["recoveryCount"])
        self.assertEqual(0, out["memoEdits"])
        for duplicate in (
            "data-next-cockpit-memos",
            'class="next-cockpit-needs"',
            "data-next-cockpit-active-delegation",
            "Outcome &amp; Focus",
            "<h2>Needs you</h2>",
            "<h2>Active work</h2>",
        ):
            self.assertNotIn(duplicate, out["panel"])
        self.assertIn("INSPECT · inspect idle owner", out["recovery"])

    def test_prepared_trail_is_fo_follow_up_not_current_task(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.state="idle";session.subagent_hierarchy=[];}
const semantic={facts:[{fact_id:"prepared",at:100,type:"prepared_dispatch",
  summary:"Prepare recovery",work_item_id:__task,
  evidence:{source:"dispatch artifact",confidence:"exact"}}],
  work_items:[{work_item_id:__task,label:"project-cockpit",kind:"workflow_item"}],
  projections:{trail_heads:[{work_item_id:__task,status:"prepared",stage:"shaping",
    latest_meaningful_event:"prepared"}],command_attention:[],
    command_attention_coverage:{state:"complete",scanned:3,total:3,omitted:0,
      source:"bounded active-session final-output scan"}}};
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
const task=nextCockpitTaskSubject(observation);
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({task,attention,active:nextCockpitRecoveryActive(group)}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("WORKFLOW TASK", out["task"])
        self.assertIn("Not observed", out["task"])
        self.assertNotIn("CURRENT TASK", out["task"])
        self.assertTrue(
            any(
                row["owner"] == "FO" and "inspect assignment return" in row["label"]
                for row in out["attention"]
            )
        )
        self.assertEqual("No active sessions or exact assignments observed", out["active"])

    def test_copy_briefing_exports_browser_memos_and_exact_observed_payload_only(self) -> None:
        storage = {
            "cargento.cockpit.memo.v2:spacedock-research%2Fcargento:project:outcome": (
                "Recover operator context"
            ),
            "cargento.cockpit.memo.v2:spacedock-research%2Fcargento:project:focus": (
                "Check exact handoff"
            ),
        }
        out = self.run_fixture(
            """
let __copied="";
navigator.clipboard={writeText:async value=>{__copied=String(value);}};
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.push(
  {fact_id:"copy-direction",at:111,type:"user_message",summary:"Copy this direction",
    source_session:{harness:"codex",sid:"focus-1"},
    evidence:{source:"root transcript",confidence:"exact"}},
  {fact_id:"copy-result",at:112,type:"result",summary:"Copy this exact result",
    source_session:{harness:"codex",sid:"focus-1"},work_item_id:__task,
    evidence:{source:"assistant final",confidence:"exact"}}
);
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});
renderNext();
const before=__fetchCalls.length;
const target={dataset:{nextCockpitAction:"copy-briefing"},
  closest(selector){return selector==="[data-next-cockpit-action]"?this:null;}};
__fire("click",{target,preventDefault(){}});
await __settle();await __settle();
console.log(JSON.stringify({copied:__copied,html:__els.app.innerHTML,before,
  after:__fetchCalls.length,copyCount:(__els.app.innerHTML.match(
    /data-next-cockpit-action="copy-briefing"/g)||[]).length}));
""",
            storage=storage,
        )
        assert isinstance(out, dict)

        self.assertEqual(out["before"], out["after"])
        self.assertEqual(1, out["copyCount"])
        self.assertIn("Copied", out["html"])
        for text in (
            "Project: cargento",
            "Outcome (browser-local): Recover operator context",
            "Focus (browser-local): Check exact handoff",
            "Active: 1 active session · 2 exact assignments",
            "Latest actionable direction: Copy this direction",
            "Latest exact result: Copy this exact result",
            "Decisions: consumed/applied 1",
            "Attention coverage: Coverage complete · 3 of 3 active sessions",
        ):
            self.assertIn(text, out["copied"])
        self.assertNotIn("undefined", out["copied"])

    def test_human_outcome_and_focus_autosave_per_exact_scope(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const projectOutcome=nextCockpitMemoKey(group,null,"outcome");
const projectFocus=nextCockpitMemoKey(group,null,"focus");
const pi=group.sessions.find(session=>sessKey(session)==="pi:pi-idle");
const sessionOutcome=nextCockpitMemoKey(group,pi,"outcome");
const edit=(key,kind,value)=>({value,dataset:{nextCockpitMemoKey:key,nextCockpitMemoKind:kind},
  closest(selector){ return selector === "[data-next-cockpit-memo-input]" ? this : null; }});
__fire("input",{target:edit(projectOutcome,"outcome","Ship calm scope navigation")});
__fire("input",{target:edit(projectFocus,"focus","Review project truth")});
__fire("input",{target:edit(sessionOutcome,"outcome","Inspect Pi evidence")});
const action=(name,key)=>({dataset:{nextCockpitAction:name,arg:key},
  closest(selector){ return selector === "[data-next-cockpit-action]" ? this : null; }});
__fire("click",{target:action("memo-edit",projectFocus),preventDefault(){}});
const project=nextCockpitMemoFields(group,null,__semantic);
const session=nextCockpitMemoFields(group,pi,__semantic);
__fire("click",{target:action("memo-done",""),preventDefault(){}});
const closed=nextCockpitMemoFields(group,null,__semantic);
console.log(JSON.stringify({projectOutcome,projectFocus,sessionOutcome,store:__store,
  project,session,closed}));
"""
        )
        assert isinstance(out, dict)

        self.assertNotEqual(out["projectOutcome"], out["sessionOutcome"])
        self.assertEqual("Ship calm scope navigation", out["store"][out["projectOutcome"]])
        self.assertEqual("Review project truth", out["store"][out["projectFocus"]])
        self.assertEqual("Inspect Pi evidence", out["store"][out["sessionOutcome"]])
        self.assertIn("OUTCOME", out["project"])
        self.assertIn("FOCUS", out["project"])
        self.assertIn("Saved in this browser", out["project"])
        self.assertEqual(1, out["project"].count("<textarea"))
        self.assertNotIn("<textarea", out["closed"])
        self.assertIn("This browser only", out["closed"])
        self.assertNotIn("DERIVED", out["project"])
        self.assertNotIn("Ship calm scope navigation", out["session"])
        self.assertNotIn("Review project truth", out["session"])

    def test_memos_use_normalized_project_identity_and_survive_storage_failure(self) -> None:
        out = self.run_fixture(
            """
const group=nextProjectGroups()[0];
const alias={label:"worktrees/cargento-copy",sessions:group.sessions};
const normalized=nextCockpitMemoKey(group,null,"focus");
const aliased=nextCockpitMemoKey(alias,null,"focus");
localStorage.getItem=()=>{throw new Error("blocked")};
localStorage.setItem=()=>{throw new Error("blocked")};
const corruptKey=nextCockpitMemoKey(group,null,"outcome");
nextCockpitMemoDrafts.set(corruptKey,{not:"text"});
const input={value:"x".repeat(700),dataset:{nextCockpitMemoKey:corruptKey,
  nextCockpitMemoKind:"outcome"},closest(selector){
  return selector === "[data-next-cockpit-memo-input]" ? this : null; }};
__fire("input",{target:input});
nextCockpitMemoEditingKey=corruptKey;
console.log(JSON.stringify({normalized,aliased,value:nextCockpitReadMemo(corruptKey),
  html:nextCockpitMemoFields(group,null,__semantic)}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(out["normalized"], out["aliased"])
        self.assertEqual(500, len(out["value"]))
        self.assertIn("Browser storage unavailable", out["html"])
        self.assertIn("OUTCOME", out["html"])
        self.assertEqual(1, out["html"].count("<textarea"))
        self.assertNotIn("DERIVED", out["html"])

    def test_memo_reload_restores_only_the_exact_selected_scope(self) -> None:
        key = "cargento.cockpit.memo.v2:spacedock-research%2Fcargento:project:outcome"
        out = self.run_fixture(
            """
const project=__els.app.innerHTML;
nextRoute=nextRouteFromFragment("#n=project:cargento:pi%3Api-idle");
renderNext();await __settle();await __settle();
console.log(JSON.stringify({project,session:__els.app.innerHTML}));
""",
            storage={key: "Remember the accepted cockpit"},
        )
        assert isinstance(out, dict)

        self.assertIn("Remember the accepted cockpit", out["project"])
        self.assertNotIn("<textarea", out["project"])
        self.assertNotIn("Remember the accepted cockpit", out["session"])
        self.assertIn('data-scope-owner="pi:pi-idle"', out["session"])

    def test_next_bundle_keeps_steer_local_and_terminal_input_absent(self) -> None:
        out = self.run_fixture(
            """
console.log(JSON.stringify({
  steer: nextProjectSteer("cargento", {steers:[]}),
  terminalPower: projectTerminalMount.toString(),
  originPath: projectTerminalLookup.toString(),
  parts: __els.app.innerHTML
}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("STEER · LOCAL ONLY", out["steer"])
        self.assertIn("disableStdin:true", out["terminalPower"])
        self.assertIn("/api/interaction/origin", out["originPath"])
        self.assertNotIn("/api/interaction/input", out["parts"])
        self.assertNotIn("/api/interaction/control", out["parts"])


if __name__ == "__main__":
    unittest.main()
