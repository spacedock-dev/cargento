from __future__ import annotations

import pathlib
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
// Given: the Now tab has keyboard focus in the focusable cockpit DOM.
controls.find(control => control.dataset.nextCockpitAction === "tab" && control.dataset.arg === "now").focus();
const states = [];

// When: advance through the tabs with consecutive ArrowRight keys.
for(let index = 0; index < 2; index++){
  __fire("keydown", {target:document.activeElement,key:"ArrowRight",preventDefault(){}});
  states.push({tab:nextRoute.tab,focused:document.activeElement?.dataset.arg || null});
}
console.log(JSON.stringify(states));
"""
        )

        # Then
        self.assertEqual(
            [{"tab": "course", "focused": "course"}, {"tab": "decisions", "focused": "decisions"}],
            out,
        )

    def test_scope_link_focus_survives_live_refresh(self) -> None:
        out = self.run_fixture(
            self.FOCUS_DOM
            + """
// Given: the exact Codex scope link has focus.
controls.find(control => control.dataset.nextCockpitScope === "codex:focus-1").focus();

// When: refresh the dashboard.
await refreshNext();
console.log(JSON.stringify(document.activeElement?.dataset.nextCockpitScope || null));
"""
        )

        # Then
        self.assertEqual("codex:focus-1", out)

    def test_opening_human_context_moves_focus_to_the_editor(self) -> None:
        out = self.run_fixture(
            self.FOCUS_DOM
            + """
// Given: the human-context edit control has focus.
const edit = controls.find(control => control.dataset.nextCockpitAction === "memo-edit");
edit.focus();

// When: click the edit control.
__fire("click", {target:edit,preventDefault(){}});
console.log(JSON.stringify({tag:document.activeElement?.tagName || null,
  key:document.activeElement?.dataset.nextCockpitMemoKey || null,expected:edit.dataset.arg}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual("TEXTAREA", out["tag"])
        self.assertEqual(out["expected"], out["key"])

    def test_console_screen_survives_navigation_away_and_back(self) -> None:
        out = self.run_fixture("""
// Given: the console owns a mounted terminal screen.
const original = {textContent:"Delivered terminal output"};
let screen = original;
const getElement = document.getElementById;
document.getElementById = id => id === "pc-terminal-screen" ? screen : getElement(id);
projectTerminal = {dispose(){}};
projectTerminalKey = projectTerminalOpenKey = "codex:focus-1";

// When: navigate away from the console and back through its render lifecycle.
nextCockpitBeforeRender();
screen = null;
nextCockpitAfterRender();
nextCockpitBeforeRender();
screen = {textContent:"Loading the local terminal renderer.",replaceWith(node){ screen = node; }};
nextCockpitAfterRender();
console.log(JSON.stringify({same:screen === original,text:screen.textContent}));
""")

        # Then
        self.assertEqual({"same": True, "text": "Delivered terminal output"}, out)

    def test_working_root_prevents_no_execution_claim(self) -> None:
        out = self.run_fixture("""
// Given: one working root has no children or semantic activity.
__dashboard.sessions = __dashboard.sessions.slice(0, 1);
__dashboard.sessions[0].subagent_hierarchy = [];
__semantic.facts = [];
__semantic.projections = {command_attention:[],command_attention_coverage:{
  state:"complete",scanned:1,total:1,omitted:0}};

// When: redraw the cockpit.
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")

        # Then
        assert isinstance(out, str)
        self.assertNotIn("No execution observed", out)
        self.assertIn("Codex · working", out)

    def test_assignment_direction_remains_available_in_latest_evidence(self) -> None:
        out = self.run_fixture("""
// Given: the latest direction repeats the active assignment.
__semantic.facts = [{fact_id:"direction",type:"user_message",at:104,
  summary:"Fix the completion guard",intent_promoted:true,
  source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"root transcript",confidence:"exact"}}];
__semantic.projections = {};

// When: redraw the cockpit.
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")

        # Then
        assert isinstance(out, str)
        self.assertIn("Exact operator direction", out)
        self.assertNotIn("Actionable direction not captured", out)
        self.assertIn("Direction shown in assignment", out)

    def test_decision_rows_and_counts_include_unknown_authors_without_claiming_captain(
        self,
    ) -> None:
        out = self.run_fixture("""
// Given: a pending decision has an unknown author.
__semantic.facts.push({...__semantic.facts.find(f => f.type === "gate_decision"),
  fact_id:"unknown-author",at:101,by:"",decision:"hold",summary:"Pending hold",
  application_state:"pending"});
nextRoute = {view:"project",project:"cargento",tab:"decisions"};

// When: render the Decisions tab and its counts.
renderNext();
console.log(JSON.stringify({counts:nextCockpitCaptainDecisionCounts(__semantic),
  html:__els.app.innerHTML}));
""")

        # Then
        assert isinstance(out, dict)
        self.assertEqual({"pending": 1, "unknown": 0, "superseded": 0, "applied": 1}, out["counts"])
        self.assertIn("Decision author not published", out["html"])
        self.assertIn("pending 1", out["html"])
        self.assertNotIn("CAPTAIN DECISIONS", out["html"])

    def test_a_counted_unbound_decision_is_reachable_in_decisions(self) -> None:
        out = self.run_fixture(r"""
__semantic.facts.push({fact_id:"unbound-decision",at:104,type:"decision",
  source_kind:"decision",summary:"Hold for operator review",scope:"session",
  source_session:{harness:"codex",sid:"focus-1"},work_item_id:null,
  decision:"hold",application_state:"pending",
  evidence:{source:"synthetic recorded decision",confidence:"exact"}});
nextRoute = {view:"project",project:"cargento",tab:"decisions"};
renderNext();
console.log(JSON.stringify({html:__els.app.innerHTML,
  rows:[...__els.app.innerHTML.matchAll(/data-event-id="([^"]+)"/g)].map(row=>row[1])}));
""")
        assert isinstance(out, dict)
        self.assertIn("pending 1", out["html"])
        self.assertIn("consumed/applied 1", out["html"])
        self.assertEqual(["unbound-decision", "gate-a"], out["rows"])

    def test_the_typed_words_render_above_the_goal_the_harness_published(self) -> None:
        # DRC-4509. STATED GOAL is a list, not a field: the reader's words are
        # their own rows with their own tags, never merged into the harness's
        # line, because the two are different claims.
        out = self.run_fixture(r"""
__dashboard.sessions[0].annotation_goal = "Ship the cockpit";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "A merged PR";
__dashboard.sessions[0].annotation_output_why = "";
__dashboard.sessions[0].annotation_revision = 2;
__dashboard.sessions[0].annotation_revision_count = 2;
__dashboard.sessions[0].annotation_at = 104;
__dashboard.sessions[0].annotation_binding_why = "Bound by an eight-character identity prefix.";

nextRoute = {view:"project",project:"cargento",focus:"codex:focus-1",tab:"now"};
renderNext();
console.log(JSON.stringify({html:__els.app.innerHTML}));
""")
        assert isinstance(out, dict)
        html = out["html"]
        self.assertIn("YOUR WORDS \u00b7 GOAL", html)
        self.assertIn("Ship the cockpit", html)
        self.assertIn("A merged PR", html)
        self.assertIn("DERIVED FROM THE HARNESS", html)
        self.assertIn("revision 2 of 2", html)
        # The binding is reported rather than assumed exact.
        self.assertIn("eight-character identity prefix", html)
        # The harness published no goal here, so its row keeps its absence
        # styling rather than being dressed as a value because it sits in a list.
        self.assertIn(
            'next-project-value--absent next-project-goal-text">'
            "No assignment or workflow goal published",
            html,
        )

    def test_the_derived_row_says_when_the_directive_was_observed(self) -> None:
        # DRC-4509. A typed row carries its time through the revision line; the
        # derived row carried a source and nothing else, so a reader could not
        # tell a directive from four minutes ago from one from four hours ago.
        out = self.run_fixture(r"""
__dashboard.sessions[0].instruction = {label:"asked", text:"Ship the cockpit", at:45};
__dashboard.sessions[0].annotation_goal = "Ship the cockpit";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 104;
__dashboard.sessions[0].annotation_binding_why = "";

nextRoute = {view:"project",project:"cargento",focus:"codex:focus-1",tab:"now"};
renderNext();
const withTime = __els.app.innerHTML;

// And: a project whose goal comes from a workflow, which publishes no time.
__dashboard.sessions[0].instruction = null;
__dashboard.sessions[0].spacedock = {workflows:[{goal:"Survey the layout"}]};
renderNext();
console.log(JSON.stringify({withTime, withoutTime:__els.app.innerHTML}));
""")
        assert isinstance(out, dict)
        self.assertIn("codex · latest assignment · observed 1m ago", out["withTime"])
        # An absence states its reason rather than leaving the row looking
        # freshly observed.
        self.assertIn(
            "Spacedock · workflow goal · observation time not published",
            out["withoutTime"],
        )

    def test_a_session_with_no_typed_words_shows_the_harness_goal_alone(self) -> None:
        # No rows, no tags, and nothing implying the reader typed something.
        out = self.run_fixture(r"""
nextRoute = {view:"project",project:"cargento",focus:"codex:focus-1",tab:"now"};
renderNext();
console.log(JSON.stringify({html:__els.app.innerHTML}));
""")
        assert isinstance(out, dict)
        self.assertNotIn("YOUR WORDS", out["html"])
        self.assertNotIn("DERIVED FROM THE HARNESS", out["html"])

    def test_a_rendered_decision_is_not_duplicated_by_its_steering_link(self) -> None:
        out = self.run_fixture(r"""
__semantic.facts.push({fact_id:"linked-decision",at:104,type:"decision",
  source_kind:"decision",summary:"Hold for operator review",scope:"session",
  source_session:{harness:"codex",sid:"focus-1"},work_item_id:__task,
  decision:"hold",application_state:"pending",
  evidence:{source:"synthetic recorded decision",confidence:"exact"}});
__semantic.projections.steering_episodes.push({episode_id:"linked",intent_id:"intent-a",
  adaptation_fact:"linked-decision",confidence:"structural"});
nextRoute = {view:"project",project:"cargento",tab:"decisions"};
renderNext();
console.log(JSON.stringify({html:__els.app.innerHTML,
  rows:[...__els.app.innerHTML.matchAll(/data-event-id="([^"]+)"/g)].map(row=>row[1])}));
""")
        assert isinstance(out, dict)
        self.assertIn("pending 1", out["html"])
        self.assertIn("consumed/applied 1", out["html"])
        self.assertEqual(["linked-decision", "gate-a"], out["rows"])

    def test_session_scoped_now_discloses_project_wide_contents(self) -> None:
        out = self.run_fixture("""
// Given: a Claude session is selected on Now.
nextRoute = {view:"project",project:"cargento",focus:"claude:claude-idle",tab:"now"};

// When: render the selected scope.
renderNext();
console.log(JSON.stringify(__els.app.innerHTML.slice(
  __els.app.innerHTML.indexOf('<section class="next-cockpit-panel"'))));
""")

        # Then
        assert isinstance(out, str)
        self.assertIn("Now remains project-wide", out)
        self.assertIn("Shape project cockpit", out)

    def test_empty_course_and_decisions_keep_history_window(self) -> None:
        out = self.run_fixture("""
// Given: Course and Decisions have no facts in a published 24-hour window.
__semantic.facts = [];
__semantic.projections = {};
__semantic.history = {events:[],event_count:0,window_sec:86400,persisted:true};
const views = {};
for(const tab of ["course","decisions"]){
  nextRoute = {view:"project",project:"cargento",tab};

  // When: render each empty history tab.
  renderNext();
  views[tab] = __els.app.innerHTML.slice(
    __els.app.innerHTML.indexOf('<section class="next-cockpit-panel"'));
}
console.log(JSON.stringify(views));
""")

        # Then
        assert isinstance(out, dict)
        for tab, html in out.items():
            with self.subTest(tab=tab):
                self.assertIn("last 24 hours", html)

    def test_missing_plan_attachment_and_discovery_explanations_reach_now(self) -> None:
        out = self.run_fixture("""
// Given: an attached first officer exposes no plan and discovery finds no workflows.
__dashboard.sessions = __dashboard.sessions.slice(0,1);
__dashboard.sessions[0].spacedock = {role:"first-officer",workflows:[]};
for(const entry of nextCockpitContexts.values())
  entry.data.workflow_discovery = {state:"none",workflows:[]};
__semantic.facts = [];
__semantic.work_items = [];
__semantic.projections = {};

// When: redraw the cockpit.
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")

        # Then
        assert isinstance(out, str)
        self.assertIn(
            "A first-officer attachment was observed, but it exposed no current plan", out
        )
        self.assertIn(
            "Spacedock project discovery observed no commissioned workflow directories", out
        )

    def test_zero_completed_tasks_retain_published_progress_in_course(self) -> None:
        out = self.run_fixture("""
// Given: three tracked tasks are pending and zero are done.
__dashboard.sessions = __dashboard.sessions.slice(0,1);
__dashboard.sessions[0].tasks = ["alpha","beta","gamma"].map(subject => ({subject,status:"pending"}));
__dashboard.sessions[0].total = 3;
__dashboard.sessions[0].done = 0;
nextRoute = {view:"project",project:"cargento",tab:"course"};

// When: render Course.
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")

        # Then
        assert isinstance(out, str)
        self.assertIn("0 of 3 done", out)
        self.assertIn("No completed tracked tasks in this payload", out)

    def test_scope_navigation_keeps_the_title_when_activity_is_published(self) -> None:
        out = self.run_fixture(
            """
// Given: the root publishes both a title and current activity.
__dashboard.sessions[0].state_detail = "running Bash";

// When: redraw the scope navigation.
renderNext();
const html = __els.app.innerHTML;
console.log(JSON.stringify(html.slice(html.indexOf('<nav class="next-cockpit-scope-tree"'),
  html.indexOf('</nav>', html.indexOf('<nav class="next-cockpit-scope-tree"')))));
"""
        )

        # Then
        assert isinstance(out, str)
        self.assertIn("Codex", out)
        self.assertIn("Shape project cockpit", out)
        self.assertNotIn("running Bash", out)

    def test_a_missing_title_is_named_in_scope_navigation(self) -> None:
        out = self.run_fixture(
            """
// Given: the root has activity but no title.
__dashboard.sessions[0].title = null;
__dashboard.sessions[0].state_detail = "running Bash";

// When: redraw the scope navigation.
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )

        # Then
        assert isinstance(out, str)
        self.assertIn("Session title not published", out)

    def test_course_names_missing_evidence_without_an_empty_disclosure(self) -> None:
        out = self.run_fixture(
            """
// Given: a Course direction lacks source, confidence, and fact identity.
__semantic.facts = [{type:"user_message",summary:"Check source evidence",at:104,
  intent_promoted:true}];
__semantic.projections = {};
nextRoute = {view:"project",project:"cargento",tab:"course"};

// When: render Course.
renderNext();
console.log(JSON.stringify(__els.app.innerHTML.slice(
  __els.app.innerHTML.indexOf('<section class="next-cockpit-panel"'))));
"""
        )

        # Then
        assert isinstance(out, str)
        self.assertIn("Evidence source not published", out)
        self.assertIn("Evidence confidence not published", out)
        self.assertIn("Fact identity not published", out)
        self.assertNotIn('<details class="next-course-evidence"', out)

    def test_unmeasured_delegation_keeps_the_shared_models_reason(self) -> None:
        out = self.run_fixture(
            """
// Given: the Console route uses the shared delegation model.
nextRoute = {view:"project",project:"cargento",tab:"console"};

// When: render Console.
renderNext();
console.log(JSON.stringify({html:__els.app.innerHTML,
  reason:nextCurrentObserved().projects[0].delegation.noteText}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertIn("no figure yet", out["html"])
        self.assertIn(out["reason"], out["html"])
        self.assertEqual(1, out["html"].count("data-next-delegation-withheld"))

    def test_briefing_names_missing_readings_before_any_disclosure(self) -> None:
        out = self.run_fixture(
            """
// Given: the fixture has no directions, results, or child assignments.
__semantic.facts = [];
__semantic.projections = {};
for(const session of __dashboard.sessions){
  delete session.last_output;
  session.subagent_hierarchy = [];
}

// When: redraw the briefing.
renderNext();
const html = __els.app.innerHTML;
const briefing = html.slice(html.indexOf('<section class="next-cockpit-recovery"'),
  html.indexOf('<nav class="next-cockpit-tabs"'));
console.log(JSON.stringify(briefing.replace(/<details[^>]*>[\\s\\S]*?<\\/details>/g,"")));
"""
        )

        # Then
        assert isinstance(out, str)
        self.assertIn("Assignment evidence not published", out)
        self.assertIn("Actionable direction not captured", out)
        self.assertIn("Session result not captured", out)
        self.assertIn("Captain attention unavailable", out)
        self.assertIn("project context coverage unavailable", out)

    def test_a_result_does_not_hide_the_missing_direction_reading(self) -> None:
        out = self.run_fixture(
            """
// Given: an exact result is present without an actionable direction.
__semantic.facts = [{type:"result",summary:"Root finished",work_item_id:__task,at:104,
  evidence:{source:"root transcript",confidence:"exact"}}];

// When: redraw the briefing.
renderNext();
const html = __els.app.innerHTML;
console.log(JSON.stringify(html.slice(html.indexOf('<section class="next-cockpit-recovery"'),
  html.indexOf('<nav class="next-cockpit-tabs"'))));
"""
        )

        # Then
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
// Given: the fixture publishes an instruction, an ended session, and a workflow.
__dashboard.sessions[0].instruction = {label:"asked",text:"Ship <the cockpit>"};
__dashboard.sessions[1].ended_at = 100;
__dashboard.sessions[0].spacedock = {workflows:[{workflow:"cockpit",goal:"Build cockpit",
  stages:["review"],entities:[{slug:"cockpit",stage:"review",live:true}]}]};
const views = {};
for(const tab of ["now", "course", "decisions", "console"]){
  nextRoute = nextRouteFromFragment("#n=project:cargento:" + tab);

  // When: render each cockpit tab.
  renderNext();
  const html = __els.app.innerHTML;
  views[tab] = {briefing:html.slice(html.indexOf('<section class="next-cockpit-recovery"'),
    html.indexOf('<nav class="next-cockpit-tabs"')),
    panel:html.slice(html.indexOf('<section class="next-cockpit-panel"'))};
}
console.log(JSON.stringify(views));
"""
        )

        # Then
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
// Given: each waiting-state variant is viewed across tabs and scopes.
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

      // When: render the selected waiting-session view.
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

        # Then
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
// Given: the rendered baseline has an unowned ask shared by two harnesses.
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

// When: redraw the exactly owned ask without semantic context.
renderNext();
const group = nextProjectGroups().find(g => g.label === "cargento");
console.log(JSON.stringify({withoutOwner,needsWithoutOwner,withOwner:__els.app.innerHTML,
  needsWithOwner:nextCockpitProjectNeeds(group)}));
"""
        )

        # Then
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
// Given: the working root has an end timestamp.
__dashboard.sessions[0].ended_at = 100;

// When: redraw the cockpit and read its recovery execution.
renderNext();
const group = nextProjectGroups()[0];
const briefing = nextCockpitRecoveryBriefing(group, null, {semantic:__semantic}, []);
console.log(JSON.stringify({active:briefing.active,children:briefing.children.active,
  execution:nextCockpitRecoveryExecution(group, briefing),html:__els.app.innerHTML}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual("No active sessions or exact assignments observed", out["active"])
        self.assertEqual([], out["children"])
        self.assertNotIn("Codex · working", out["execution"])
        self.assertNotIn('data-next-going-on="focus-1"', out["html"])
        self.assertIn('data-next-outcome="focus-1"', out["html"])

    def test_upstream_project_detail_hosts_focus_semantics_and_no_duplicate_shell(self) -> None:
        out = self.run_fixture(
            """
// Given: the Course route is selected in the shared project fixture.
nextRoute = nextRouteFromFragment("#n=project:cargento:course");

// When: render Course and settle context requests.
renderNext();
await __settle();await __settle();
const html = __els.app.innerHTML;
const rows = [...html.matchAll(/<article class="next-course-episode"[\\s\\S]*?<\\/article>/g)]
  .map(match => match[0]);
console.log(JSON.stringify({html, rows}));
"""
        )

        # Then
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
// Given: Claude publishes one finished and one active teammate.
const session = __dashboard.sessions[0];
session.harness = "claude";
session.subagent_hierarchy = null;
session.subagents = [
  {name:"Finished teammate",active:false,parent:null},
  {name:"Live teammate",active:true,parent:null,assignment:"Check the merged cockpit"}
];

// When: redraw the cockpit and settle its context.
renderNext();
await __settle();
const group = nextProjectGroups()[0];
console.log(JSON.stringify({html:__els.app.innerHTML,
  briefing:nextCockpitRecoveryBriefing(group).text}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertNotIn("Finished teammate · active", out["html"])
        self.assertNotIn("inspect Finished teammate assignment", out["html"])
        self.assertIn("Live teammate · active", out["html"])
        self.assertNotIn("Finished teammate", out["briefing"])
        self.assertIn("Live teammate", out["briefing"])

    def test_task_subject_and_four_tabs_own_one_operator_question_each(self) -> None:
        # Given: the shared project fixture includes two assigned workers and a workflow stage.
        # When: render the default cockpit.
        out = self.run_fixture(
            """
const html = __els.app.innerHTML;
const tabs = [...html.matchAll(/<button[^>]*role="tab"[^>]*>[\\s\\S]*?<\\/button>/g)]
  .map(match => match[0]);
const panel = (html.match(/<section[^>]*role="tabpanel"[\\s\\S]*?<\\/section>/) || [""])[0];
console.log(JSON.stringify({html,tabs,panel}));
"""
        )

        # Then
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
// Given: captain authorization and FO recovery are both pending.
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

// When: redraw Now with that context.
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

        # Then
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
// Given: the exact Codex session route is selected.
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1");

// When: render the session view and settle its context.
renderNext();await __settle();await __settle();
const html=__els.app.innerHTML;
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
const task=(recovery.match(/<div data-next-cockpit-task[\\s\\S]*?<\\/div>/)||[""])[0];
const switcher=(html.match(/<details class="next-cockpit-scope-switcher"[\\s\\S]*?<\\/details>/)||[""])[0];
console.log(JSON.stringify({html,recovery,task,switcher}));
"""
        )

        # Then
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
// Given: Course contains facts with project, session, and unknown provenance.
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

// When: render Course and settle its context.
renderNext();await __settle();await __settle();await __settle();
const html=__els.app.innerHTML;
const rows=[...html.matchAll(/<article class="next-course-episode"[\\s\\S]*?<\\/article>/g)]
  .map(match=>match[0]);
const directions=[...html.matchAll(/<article class="next-course-direction"[\\s\\S]*?<\\/article>/g)]
  .map(match=>match[0]);
console.log(JSON.stringify({html,rows,directions}));
"""
        )

        # Then
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
// Given: a direction and result have an exact task binding and a steering episode.
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.find(fact=>fact.fact_id==="fo-a").work_item_id=__task;
semantic.facts.push({fact_id:"paired-result",at:106,type:"result",summary:"Layout corrected",
  detail:"Fixed and live on port 8766.\\n\\nCheckpoint: `abc1234`.",
  source_session:{harness:"codex",sid:"focus-1"},work_item_id:__task,
  evidence:{source:"assistant result",confidence:"exact"}});
semantic.projections.steering_episodes=[{episode_id:"pair-a",intent_id:"intent-a",
  adaptation_fact:"paired-result",confidence:"structural"}];

// When: render Course.
const html=nextCockpitCourse(nextProjectGroups()[0],semantic,[]);
const primary=(html.match(/<article class="next-course-episode"[\\s\\S]*?<\\/article>/g)||[])
  .find(row=>row.includes("Layout corrected"))||"";
const other=(html.match(/<details class="next-course-directions"[\\s\\S]*?<\\/details>/)||[""])[0];
console.log(JSON.stringify({html,primary,other}));
"""
        )

        # Then
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
// Given: sixteen exact directions have no associated course change.
const facts=Array.from({length:16},(_,index)=>({fact_id:`direction-${index+1}`,
  at:index+1,type:"user_message",intent_promoted:true,summary:`Direction ${index+1}`,
  source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"root transcript",confidence:"exact"}}));
const semantic={facts,work_items:[],relations:[],projections:{
  operator_intents:facts.map((fact,index)=>({projection_id:`intent-${index+1}`,
    at:fact.at,summary:fact.summary,derived_from:fact.fact_id})),
  steering_episodes:[],trail_heads:[]}};

// When: render Course.
const html=nextCockpitCourse(nextProjectGroups()[0],semantic,[]);
const primary=[...html.matchAll(/<article class="next-course-episode"/g)].length;
console.log(JSON.stringify({html,primary}));
"""
        )

        # Then
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
// Given: completed work has been rendered on Now.
const claude=__dashboard.sessions.find(session=>session.harness==="claude");
claude.tasks=[{status:"completed",subject:"Verify accepted project cockpit"}];
renderNext();await __settle();
const now=__els.app.innerHTML;

// When: navigate to Course and render it.
nextRoute=nextRouteFromFragment("#n=project:cargento:course");
renderNext();await __settle();await __settle();
console.log(JSON.stringify({now,course:__els.app.innerHTML}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertNotIn("Verify accepted project cockpit", out["now"])
        self.assertIn("Verify accepted project cockpit", out["course"])
        self.assertIn('data-next-project-activity="done"', out["course"])

    def test_decisions_use_fact_scope_not_selected_session(self) -> None:
        out = self.run_fixture(
            """
// Given: project and session decisions coexist while Pi is selected.
nextCockpitContexts.clear();
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts.push({fact_id:"session-decision",at:100.5,type:"gate_decision",
  source_kind:"gate",scope:"session",by:"person:captain",decision:"hold",stage:"review",
  application_state:"pending",work_item_id:__task,
  source_session:{harness:"pi",sid:"pi-idle"},
  evidence:{source:"session gate",confidence:"exact"}});
__fetchImpl=async()=>({ok:true,json:async()=>({semantic,child_assignments:[],observers:[]})});
nextRoute=nextRouteFromFragment("#n=project:cargento:pi%3Api-idle:decisions");

// When: render Decisions and settle its context.
renderNext();await __settle();await __settle();await __settle();
const rows=[...__els.app.innerHTML.matchAll(/<article class="pc-graph-row[\\s\\S]*?<\\/article>/g)]
  .map(match=>match[0]);
console.log(JSON.stringify({rows,html:__els.app.innerHTML}));
"""
        )

        # Then
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
// Given: the Console has rendered at project scope.
nextRoute=nextRouteFromFragment("#n=project:cargento:console");
renderNext();await __settle();
const project=__els.app.innerHTML;

// When: navigate to the exact Codex session Console.
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1:console");
renderNext();await __settle();
const session=__els.app.innerHTML;
console.log(JSON.stringify({project,session}));
"""
        )

        # Then
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
// Given: a session Course permalink has been parsed and rendered.
const parsed = nextRouteFromFragment("#n=project:cargento:pi%3Api-idle:course");
const roundTrip = nextFragmentForRoute(parsed);
nextRoute = parsed;
renderNext();
await __settle();await __settle();
const course = __els.app.innerHTML;
const target = {dataset:{nextCockpitAction:"tab",arg:"course"},
  closest(selector){ return selector === "[data-next-cockpit-action]" ? this : null; }};

// When: press ArrowRight on its Course tab.
__fire("keydown", {target,key:"ArrowRight",preventDefault(){}});
const afterKey = __els.app.innerHTML;
console.log(JSON.stringify({parsed,roundTrip,course,afterKey,hash:location.hash}));
"""
        )

        # Then
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
// Given: the selected Console has resolved its exact registered terminal origin.
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

// When: click Open terminal.
__fire("click", {target:open,preventDefault(){}});
const opened = __els.app.innerHTML;
console.log(JSON.stringify({pending,available,opened}));
"""
        )

        # Then
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
// Given: the selected terminal has each refusal or lookup failure in turn.
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

  // When: render Console and settle the origin lookup.
  renderNext();
  views.pending = __els.app.innerHTML;
  await __settle(); await __settle();
  views[reason] = __els.app.innerHTML;
}
console.log(JSON.stringify(views));
"""
        )

        # Then
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
// Given: the terminal has either zero indices or missing coordinates.
const session = __dashboard.sessions[0];
const views = [];
projectTerminalOpenKey = "codex:focus-1";
for(const origin of [{session_name:"Pane <one>",window_index:0,pane_index:0},{}]){
  projectTerminalBySession[projectTerminalOpenKey] = {state:"registered",data:{origin}};

  // When: render the registered terminal surface.
  views.push(projectTerminalSurface(session));
}
console.log(JSON.stringify(views));
"""
        )

        # Then
        assert isinstance(out, list)
        self.assertIn("Pane &lt;one&gt;:0.0", out[0])
        self.assertIn("Tmux session name not published.", out[1])
        self.assertIn("Window index not published.", out[1])
        self.assertIn("Pane index not published.", out[1])
        self.assertNotIn("tmux:?.?", out[1])

    def test_substrate_empty_history_names_its_published_window_and_filter(self) -> None:
        out = self.run_fixture(
            """
// Given: empty history has each published window and filter combination.
const views = {};
for(const [name,history,mode] of [["day",{window_sec:86400},"all"],
    ["short",{window_sec:5400},"decisions"],["unknown",{},"all"],
    ["active",{window_sec:86400},"active"]]){

  // When: render the semantic timeline for that case.
  views[name] = projectSemanticTimeline(__dashboard,
    {facts:[],work_items:[],projections:{},history},[],null,[],{mode});
}
console.log(JSON.stringify(views));
"""
        )

        # Then
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
// Given: the terminal assets are unloaded and the DOM records inserted nodes.
const cases = [];
for(const failure of ["script", "link", "none"]){
  projectTerminalXtermPromise = null;
  delete window.Terminal;
  const nodes = [];
  document.querySelector = () => null;
  document.createElement = tag => ({tag,dataset:{},remove(){}});
  document.head = {append(node){nodes.push(node);}};

  // When: load the local assets with each simulated load outcome.
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

        # Then
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
// Given: the evidence registry has one lane and missing or explicit source fields.
const lane = {key:"fo:codex:focus-1",kind:"fo",label:"Codex",index:0,events:[]};
const registry = {lanes:[lane]};

// When: render the evidence surfaces for those records.
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

        # Then
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
// Given: facts and operator intents have no event times.
const model = JSON.parse(JSON.stringify(__semantic));
model.facts.forEach(fact => delete fact.at);
model.projections.operator_intents.forEach(intent => delete intent.at);
const registry = projectLaneRegistry(model,[],null,__dashboard.sessions);
const events = projectGlobalEvents(model,registry,null);

// When: render history and its evidence readings.
console.log(JSON.stringify({html:projectSemanticTimeline(__dashboard,model,[],null,
  __dashboard.sessions,{mode:"all"}),span:projectHistorySpan(events),
  partial:projectGlobalEventDetails({kind:"decision",fact:{target_stage:"review"}},
    {kind:"fo",events:[]})}));
"""
        )

        # Then
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
// Given: Course has exact results, a derived change, and proposed future text.
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

// When: render Course and settle its context.
renderNext();
await __settle();await __settle();await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML}));
"""
        )

        # Then
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
        # Given: the shared fixture contains active and idle sessions from three harnesses.
        # When: render the default project scope.
        out = self.run_fixture(
            """
const html = __els.app.innerHTML;
console.log(JSON.stringify({html, query:[...nextCockpitContexts.keys()]}));
"""
        )

        # Then
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
        # Given: two workers have exact assignments under the Codex root.
        # When: render the default project briefing.
        out = self.run_fixture(
            """
const html = __els.app.innerHTML;
const task = (html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/) || [""])[0];
console.log(JSON.stringify({html, task}));
"""
        )

        # Then
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
// Given: an active child has no assignment.
const group=nextProjectGroups()[0];
group.sessions[0].subagent_hierarchy=[{name:"Unbound",observer_sid:"child-x",depth:1}];

// When: render active delegation.
const html=nextCockpitActiveDelegation(group,{semantic:__semantic});
console.log(JSON.stringify({html}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertIn("assignment unavailable", out["html"])
        self.assertIn("Unbound", out["html"])
        self.assertIn("assignment source unavailable", out["html"])

    def test_missing_task_identity_keeps_exact_working_activity_without_invention(self) -> None:
        out = self.run_fixture(
            """
// Given: a working root and child have no task identity or published title.
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

// When: render the project cockpit.
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

        # Then
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
// Given: focused facts have opaque labels and project context has canonical labels.
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

// When: render focused Decisions and settle both context requests.
renderNext();
await __settle();await __settle();await __settle();
const html=__els.app.innerHTML;
console.log(JSON.stringify({html,requests:[...nextCockpitContexts.keys()]}));
"""
        )

        # Then
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
// Given: the exact Pi session permalink is selected.
nextRoute = nextRouteFromFragment("#n=project:cargento:pi%3Api-idle");

// When: render the focused cockpit.
renderNext();
await __settle();
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({html, focus:nextCockpitFocusedSession(nextProjectGroups()[0]) &&
  sessKey(nextCockpitFocusedSession(nextProjectGroups()[0]))}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertEqual("pi:pi-idle", out["focus"])
        self.assertIn('data-next-cockpit-scope="pi:pi-idle"', out["html"])
        self.assertIn('data-next-cockpit-scope="pi:pi-idle" aria-current="page"', out["html"])
        self.assertIn('data-arg="decisions"', out["html"])

    def test_stale_exact_session_permalink_never_falls_back_to_project_scope(self) -> None:
        out = self.run_fixture(
            """
// Given: the permalink names a session absent from the payload.
nextData.sessions=nextData.sessions.filter(session=>sessKey(session)!=="pi:pi-idle");
nextRoute=nextRouteFromFragment("#n=project:cargento:pi%3Api-idle:course");

// When: render the stale session route.
renderNext();await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML,route:nextFragmentForRoute(nextRoute)}));
"""
        )

        # Then
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
// Given: the project Decisions route is selected.
nextRoute = nextRouteFromFragment("#n=project:cargento:decisions");

// When: render Decisions and settle its context.
renderNext();
await __settle();await __settle();
const html = __els.app.innerHTML;
const rows = [...html.matchAll(/<article class="pc-graph-row[\\s\\S]*?<\\/article>/g)]
  .map(match => match[0]);
console.log(JSON.stringify({html, rows}));
"""
        )

        # Then
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
// Given: one gate has each application state in turn.
const lane = {kind:"task", label:"project-cockpit"};
const sentence = application_state => projectGlobalEventSentence({kind:"decision", fact:{
  type:"gate_decision", by:"person:captain", decision:"approve", stage:"review",
  target_stage:"shaping", application_state
}}, lane);

// When: derive its decision sentence.
console.log(JSON.stringify({
  consumed:sentence("consumed"), applied:sentence("applied"),
  pending:sentence("pending"), unspent:sentence("unspent"),
  superseded:sentence("superseded"), unknown:sentence(undefined)
}));
"""
        )

        # Then
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
// Given: a collaboration envelope is explicitly excluded from intent promotion.
const semantic = JSON.parse(JSON.stringify(__semantic));
semantic.facts.push({fact_id:"injected",at:106,type:"user_message",
  summary:"Message Type: MESSAGE Sender: /root Payload: keep working",
  intent_promoted:false,source_session:{harness:"codex",sid:"focus-1"},
  evidence:{source:"injected collaboration envelope",confidence:"exact"}});
const registry = projectLaneRegistry(semantic, [], null, __dashboard.sessions);

// When: derive the global events and their sentences.
const events = projectGlobalEvents(semantic, registry, null);
console.log(JSON.stringify({
  ids:events.map(event => event.eventId),
  sentences:events.map(event => projectGlobalEventSentence(event,
    registry.laneByKey.get(event.lane.key)))
}));
"""
        )

        # Then
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
// Given: captain decisions include a duplicate, older decisions, and an FO decision.
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

// When: render project status.
console.log(JSON.stringify({html:nextCockpitProjectStatus(nextProjectGroups()[0], semantic)}));
"""
        )

        # Then
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
// Given: exact captain authorization coexists with FO recovery conditions.
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

// When: derive command attention and render the recovery strip.
const items = nextCockpitCommandAttention(group, observation);
console.log(JSON.stringify({items,html:nextCockpitRecoveryStrip(group, observation, items)}));
""",
        )

        # Then
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
// Given: the captain-attention scan omits one of 65 active sessions.
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention=[];
semantic.projections.command_attention_coverage={state:"incomplete",scanned:64,total:65,
  omitted:1,source:"bounded active-session final-output scan"};
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: derive attention and render Needs you.
const items=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({items,html:nextCockpitNeedsYou(items)}));
"""
        )

        # Then
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
// Given: fresh direction, result, decision, and browser memos are in context.
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

// When: redraw the cockpit briefing.
renderNext();
const html=__els.app.innerHTML;
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
console.log(JSON.stringify({html,recovery,strip:html.indexOf("next-cockpit-recovery"),
  tabs:html.indexOf("next-cockpit-tabs"),tabCount:(html.match(/role="tab"/g)||[]).length,
  copyCount:(html.match(/data-next-cockpit-action="copy-briefing"/g)||[]).length}));
"""
        )

        # Then
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
// Given: an active child has a name but no assignment evidence.
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_hierarchy=[{name:"Hooke",observer_sid:"child-hooke",depth:1,
  assignment:null,assignment_status:"unavailable"}];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});

// When: derive attention and render recovery.
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({attention,
  briefing:nextCockpitRecoveryBriefing(group,null,observation,attention),
  html:nextCockpitRecoveryStrip(group,observation,attention)}));
"""
        )

        # Then
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
// Given: two children have returned without result evidence.
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_events=[
  {at:110,kind:"subagent_complete",name:"Hooke",source:"Codex child rollout lifecycle"},
  {at:112,kind:"subagent_complete",name:"Harvey",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});

// When: derive attention and render recovery.
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({attention,
  briefing:nextCockpitRecoveryBriefing(group,null,observation,attention),
  html:nextCockpitRecoveryStrip(group,observation,attention)}));
"""
        )

        # Then
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
// Given: the shared context includes the bounded attention-scan source.
const group=nextProjectGroups()[0];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});

// When: build the copyable briefing and rendered strip.
const briefing=nextCockpitRecoveryBriefing(group,null,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )

        # Then
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("bounded active-session final-output scan", value)
        self.assertIn("FO CONTINUES", out["html"])

    def test_failed_refresh_marks_retained_exact_facts_stale(self) -> None:
        out = self.run_fixture(
            """
// Given: retained direction and result facts belong to a failed context refresh.
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

// When: build the briefing and rendered strip.
const briefing=nextCockpitRecoveryBriefing(group,null,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation)}));
"""
        )

        # Then
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("stale cached", value.casefold())
            self.assertIn("Cached direction", value)
            self.assertIn("Cached result", value)
        self.assertNotIn("LATEST EXACT</span>", out["html"])

    def test_command_attention_sorts_captain_before_fo_independent_of_payload_order(self) -> None:
        out = self.run_fixture(
            """
// Given: the payload lists FO recovery before captain authorization.
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention=[
  {owner:"FO",kind:"recovery",label:"Verify system state",question:"Verify system state",
    evidence:{source:"workflow",confidence:"exact"}},
  {owner:"CAPTAIN",kind:"authorization",label:"Choose the route",question:"Choose the route",
    evidence:{source:"captain gate",confidence:"exact"}}
];
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: derive and render command attention.
const items=nextCockpitCommandAttention(group,observation);
const html=nextCockpitRecoveryAttention(group,observation,items);
console.log(JSON.stringify({items,html}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertEqual("CAPTAIN", out["items"][0]["owner"])
        self.assertTrue(all(row["owner"] == "FO" for row in out["items"][1:]))
        self.assertLess(out["html"].index("CAPTAIN ·"), out["html"].index("FO ·"))

    def test_recovery_excludes_non_promotable_acknowledgment_from_actionable_direction(
        self,
    ) -> None:
        out = self.run_fixture(
            """
// Given: an actionable direction precedes an unpromoted acknowledgment.
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

// When: build the briefing and rendered strip.
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )

        # Then
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("Verify the live candidate", value)
            self.assertNotIn("great.", value)
        self.assertIn("LATEST ACTIONABLE DIRECTION", out["html"])

    def test_recovery_assignment_prefers_substantive_root_work_over_later_mechanism(self) -> None:
        out = self.run_fixture(
            """
// Given: substantive root work precedes a mechanism correction and acknowledgment.
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

// When: build the briefing and rendered strip.
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({briefing,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )

        # Then
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
// Given: working sessions have a recoverable directive and no child gaps.
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

// When: derive attention and render recovery.
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({attention,
  html:nextCockpitRecoveryStrip(group,observation,attention)}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertIn("Restart 5-round review loop", out["html"])
        self.assertFalse(
            any(row["owner"] == "FO" and "assignment" in row["label"] for row in out["attention"])
        )

    def test_named_missing_child_handoff_gets_one_concrete_fo_inspection(self) -> None:
        out = self.run_fixture(
            """
// Given: Harvey returned with an assignment but no handoff result.
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_events=[
  {at:112,kind:"subagent_complete",name:"Harvey",assignment:"Review the mirror",
    source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: derive and render command attention.
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({attention,
  html:nextCockpitRecoveryAttention(group,observation,attention)}));
"""
        )

        # Then
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
// Given: current workers have complete attention coverage.
const group=nextProjectGroups()[0];
for(const session of group.sessions){
  session.state="working";session.last_activity=nextData.generated;
  session.subagent_hierarchy=[];session.subagent_events=[];
}
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: render authority for no action, FO inspection, and captain authorization.
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

        # Then
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
// Given: captain requests carry four distinct kinds.
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

// When: derive and render command attention.
const items=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({items,html:nextCockpitRecoveryAttention(group,observation,items)}));
"""
        )

        # Then
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
// Given: Harvey is active without assignment evidence.
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_hierarchy=[{name:"Harvey",observer_sid:"child-h",depth:1}];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: derive and render command attention.
const items=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({items,html:nextCockpitRecoveryAttention(group,observation,items)}));
"""
        )

        # Then
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
// Given: two captain requests precede three FO actions.
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

// When: render the authority cell.
console.log(JSON.stringify({html:nextCockpitRecoveryAttention(group,observation,items)}));
"""
        )

        # Then
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
// Given: a recorded hold has produced FO application attention.
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

// When: derive attention for the fresh captain question.
const freshItems=nextCockpitCommandAttention(group,observation);
const fresh=nextCockpitRecoveryAttention(group,observation,freshItems);
console.log(JSON.stringify({pendingItems,pending,freshItems,fresh}));
"""
        )

        # Then
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
// Given: missing stage linkage permits current work in the baseline strip.
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

// When: render the stage link required for the named dispatch step.
const blocked=nextCockpitRecoveryStrip(group,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({continues,blocked}));
"""
        )

        # Then
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
// Given: the baseline execution has a fresh returned child.
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

// When: render execution for the old return.
const stale=nextCockpitRecoveryExecution(group,
  nextCockpitRecoveryBriefing(group,null,observation,[]));
console.log(JSON.stringify({fresh,stale}));
"""
        )

        # Then
        assert isinstance(out, dict)

        fresh_primary = out["fresh"].split("<details", maxsplit=1)[0]
        stale_primary = out["stale"].split("<details", maxsplit=1)[0]
        self.assertNotIn("22s", fresh_primary)
        self.assertIn("22s", out["fresh"])
        self.assertIn("stale", stale_primary)

    def test_returned_handoff_unavailable_is_inline_and_commands_recovery(self) -> None:
        out = self.run_fixture(
            """
// Given: one root has a returned child without handoff evidence.
const group=nextProjectGroups()[0];
group.sessions=[group.sessions[0]];
group.sessions[0].subagent_hierarchy=[];
group.sessions[0].subagent_events=[{at:112,kind:"subagent_complete",name:"Harvey",
  source:"Codex child rollout lifecycle"}];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: derive attention and render execution and command.
const attention=nextCockpitCommandAttention(group,observation);
const briefing=nextCockpitRecoveryBriefing(group,null,observation,attention);
console.log(JSON.stringify({attention,
  execution:nextCockpitRecoveryExecution(group,briefing),
  command:nextCockpitRecoveryAttention(group,observation,attention)}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertTrue(any(row["label"] == "recover Harvey handoff" for row in out["attention"]))
        self.assertIn("Harvey · returned · handoff unavailable", out["execution"])
        self.assertIn("INSPECT · recover Harvey handoff", out["command"])

    def test_recovery_cells_put_situation_before_command_with_four_truths_inline(self) -> None:
        out = self.run_fixture(
            """
// Given: a root directive, missing stage link, and returned child need recovery.
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

// When: derive attention and render the recovery strip.
const attention=nextCockpitCommandAttention(group,observation);
const html=nextCockpitRecoveryStrip(group,observation,attention);
const primary=html.replace(/<details[^>]*>[\\s\\S]*?<\\/details>/g,"");
console.log(JSON.stringify({html,primary}));
"""
        )

        # Then
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
// Given: one idle root has complete coverage and no child activity.
const group=nextProjectGroups()[0];
group.sessions=[group.sessions[0]];
group.sessions[0].state="idle";
group.sessions[0].subagent_hierarchy=[];group.sessions[0].subagent_events=[];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.projections.command_attention_coverage={state:"complete",scanned:1,total:1,
  omitted:0,source:"bounded attention scan"};
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: render recovery without pending attention.
const html=nextCockpitRecoveryStrip(group,observation,[]);
const primary=html.replace(/<details[^>]*>[\\s\\S]*?<\\/details>/g,"");
console.log(JSON.stringify({primary}));
"""
        )

        # Then
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
        # Given: the shared project fixture has the default cockpit utilities.
        # When: render the project header and briefing.
        out = self.run_fixture(
            """
const html=__els.app.innerHTML;
const header=(html.match(/<header class="next-header">[\\s\\S]*?<\\/header>/)||[""])[0];
const recovery=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
const beforeMenu=header.split('<details class="next-menu"',1)[0];
console.log(JSON.stringify({html,header,recovery,beforeMenu}));
"""
        )

        # Then
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
// Given: the root has attributable output and newer peer results are unrelated.
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

// When: build the briefing and rendered strip.
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )

        # Then
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("Linked root result", value)
            self.assertNotIn("Unrelated Pi output", value)
            self.assertNotIn("Unrelated semantic result", value)

    def test_ancient_returned_child_is_qualified_stale(self) -> None:
        out = self.run_fixture(
            """
// Given: Harvey returned long before the payload clock.
const group=nextProjectGroups()[0];
nextData.generated=1000;
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_events=[
  {at:1,kind:"subagent_complete",name:"Harvey",assignment:"Review mirror",
    result:"Review returned",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: build the briefing and render execution.
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryExecution(group,briefing)}));
"""
        )

        # Then
        assert isinstance(out, dict)

        for value in (out["text"], out["html"]):
            self.assertIn("Harvey · returned", value)
            self.assertIn("stale", value)

    def test_recovery_uses_attributable_session_output_when_semantic_result_is_absent(
        self,
    ) -> None:
        out = self.run_fixture(
            """
// Given: the root has attributable output but no semantic result.
const group=nextProjectGroups()[0];
group.sessions[0].last_output="Candidate verification completed\\n\\nDetailed verification transcript";
group.sessions[0].last_activity=120;
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts=semantic.facts.filter(fact=>fact.type!=="result");
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};
nextCockpitContexts.set(nextCockpitContextKey(group,null),{data:observation,
  revision:nextData.generated});

// When: build the briefing and rendered strip.
const briefing=nextCockpitRecoveryBriefing(group,null,observation,[]);
console.log(JSON.stringify({text:briefing.text,
  html:nextCockpitRecoveryStrip(group,observation,[])}));
"""
        )

        # Then
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
// Given: FO attention contains a missing handoff followed by source verification.
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

// When: render recovery attention.
const html=nextCockpitRecoveryAttention(group,observation,items);
console.log(JSON.stringify({items,html}));
"""
        )

        # Then
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
        # Given: the shared project fixture has assignments and active execution.
        # When: render the recovery briefing.
        out = self.run_fixture(
            """
const recovery=(__els.app.innerHTML.match(
  /<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<nav class="next-cockpit-tabs")/)||[""])[0];
console.log(JSON.stringify({recovery}));
"""
        )

        # Then
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
// Given: one child is active and another returned, both with missing evidence.
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

// When: render the recovery strip with its owned actions.
const html=nextCockpitRecoveryStrip(group,observation,
  nextCockpitCommandAttention(group,observation));
console.log(JSON.stringify({html}));
"""
        )

        # Then
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
// Given: the semantic context contains no gate decisions.
const group=nextProjectGroups()[0];
const semantic=JSON.parse(JSON.stringify(__semantic));
semantic.facts=semantic.facts.filter(fact=>fact.type!=="gate_decision");
const observation={semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: render the recovery strip.
const recovery=nextCockpitRecoveryStrip(group,observation,[]);
console.log(JSON.stringify({recovery}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertNotIn("<span>DECISIONS</span>", out["recovery"])
        self.assertNotIn("No captain decisions observed", out["recovery"])

    def test_execution_groups_plain_child_rows_under_one_root(self) -> None:
        out = self.run_fixture(
            """
// Given: one root has both an active child and a returned child.
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_hierarchy=[{name:"Ohm",observer_sid:"child-ohm",depth:1}];
group.sessions[0].subagent_events=[
  {at:112,kind:"subagent_complete",name:"Harvey",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: render the recovery strip.
const html=nextCockpitRecoveryStrip(group,observation,
  nextCockpitCommandAttention(group,observation));
const execution=html.slice(html.indexOf("EXECUTION"),html.indexOf("LATEST EVIDENCE"));
console.log(JSON.stringify({execution}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertEqual(1, out["execution"].count("Codex · working"))
        self.assertIn("Ohm · active", out["execution"])
        self.assertIn("Harvey · returned", out["execution"])
        self.assertNotIn("next-scope-cue", out["execution"])
        self.assertNotIn("SESSION", out["execution"])

    def test_returned_child_primary_hides_identifiers_and_discloses_evidence(self) -> None:
        out = self.run_fixture(
            """
// Given: Harvey returned without assignment or result evidence.
const group=nextProjectGroups()[0];
for(const session of group.sessions){session.subagent_hierarchy=[];session.subagent_events=[];}
group.sessions[0].subagent_events=[
  {at:112,kind:"subagent_complete",name:"Harvey",source:"Codex child rollout lifecycle"}
];
const observation={semantic:__semantic,workflow_discovery:{state:"observed"},sources:{}};

// When: render the recovery strip.
const html=nextCockpitRecoveryStrip(group,observation,
  nextCockpitCommandAttention(group,observation));
const start=html.indexOf("Harvey · returned");
const disclosure=html.indexOf("<details",start);
const end=html.indexOf("</details>",disclosure);
console.log(JSON.stringify({primary:html.slice(start,disclosure),
  evidence:html.slice(disclosure,end)}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertNotIn("assignment/result missing", out["primary"])
        self.assertNotIn("codex:focus-1", out["primary"])
        self.assertIn("Evidence", out["evidence"])
        self.assertIn("assignment unavailable", out["evidence"])
        self.assertIn("result unavailable", out["evidence"])
        self.assertIn("codex:focus-1", out["evidence"])

    def test_mounted_briefing_subtracts_duplicate_now_cards(self) -> None:
        # Given: the shared project fixture mounts the default Now briefing.
        # When: render the cockpit.
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

        # Then
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
// Given: idle sessions have a prepared dispatch but no current stage.
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

// When: derive the task, attention, and active-work readings.
const task=nextCockpitTaskSubject(observation);
const attention=nextCockpitCommandAttention(group,observation);
console.log(JSON.stringify({task,attention,active:nextCockpitRecoveryActive(group)}));
"""
        )

        # Then
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
// Given: browser memos and exact facts are mounted with a recording clipboard.
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

// When: click Copy briefing and settle the clipboard write.
__fire("click",{target,preventDefault(){}});
await __settle();await __settle();
console.log(JSON.stringify({copied:__copied,html:__els.app.innerHTML,before,
  after:__fetchCalls.length,copyCount:(__els.app.innerHTML.match(
    /data-next-cockpit-action="copy-briefing"/g)||[]).length}));
""",
            storage=storage,
        )

        # Then
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
// Given: the project memo is restored from storage in the project view.
const project=__els.app.innerHTML;

// When: navigate to the exact Pi session and render it.
nextRoute=nextRouteFromFragment("#n=project:cargento:pi%3Api-idle");
renderNext();await __settle();await __settle();
console.log(JSON.stringify({project,session:__els.app.innerHTML}));
""",
            storage={key: "Remember the accepted cockpit"},
        )

        # Then
        assert isinstance(out, dict)

        self.assertIn("Remember the accepted cockpit", out["project"])
        self.assertNotIn("<textarea", out["project"])
        self.assertNotIn("Remember the accepted cockpit", out["session"])
        self.assertIn('data-scope-owner="pi:pi-idle"', out["session"])

    def test_next_bundle_keeps_steer_local_and_terminal_input_absent(self) -> None:
        out = self.run_fixture(
            """
// Given: the shared bundle exposes local steering and terminal functions.
// When: inspect the rendered steer, terminal functions, and page markup.
console.log(JSON.stringify({
  steer: nextProjectSteer("cargento", {steers:[]}),
  terminalPower: projectTerminalMount.toString(),
  originPath: projectTerminalLookup.toString(),
  parts: __els.app.innerHTML
}));
"""
        )

        # Then
        assert isinstance(out, dict)

        self.assertIn("STEER · LOCAL ONLY", out["steer"])
        self.assertIn("disableStdin:true", out["terminalPower"])
        self.assertIn("/api/interaction/origin", out["originPath"])
        self.assertNotIn("/api/interaction/input", out["parts"])
        self.assertNotIn("/api/interaction/control", out["parts"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitHeldToTabTest(NextPageJsHarness):
    """DRC-4508's input surface: two fields, at session scope, in the cockpit.

    The store, the endpoint and the read-only rows already ship. This is the
    place a person types into, and the acceptance criterion it carries is that
    a session with neither field renders an absence with its reason rather
    than a blank or a placeholder.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE
    # A DOM stub whose `closest` answers any `[data-*]` selector from the
    # element's own dataset. `NextCockpitCompositionTest.FOCUS_DOM` answers
    # only the action selector, which is right for the tests that use it and
    # cannot see a textarea's own input hook.
    FOCUS_DOM = r"""
let controls = [];
let spans = [];
const decode = text => text.replace(/&quot;/g, '"').replace(/&amp;/g, "&");
const camel = name => name.replace(/^data-/, "").replace(/-([a-z])/g,
  (_, letter) => letter.toUpperCase());
// Every replacement is counted. A keystroke that redraws is the defect this
// class exists to hold shut, and counting is how the test sees one.
__els.renders = 0;
__els.app = {
  get innerHTML(){ return this.html || ""; },
  set innerHTML(html){
    this.html = html;
    __els.renders += 1;
    document.activeElement = null;
    controls = [...html.matchAll(/<(button|a|textarea)\b([^>]*)>/g)].map(match => {
      const attrs = Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)]
        .map(attr => [attr[1], decode(attr[2])]));
      const dataset = Object.fromEntries(Object.entries(attrs)
        .filter(([key]) => key.startsWith("data-")).map(([key, value]) => [camel(key), value]));
      return {dataset, tagName:match[1].toUpperCase(), value:"", attrs, hidden:"hidden" in attrs,
        getAttribute(name){ return attrs[name] || null; },
        focus(){ document.activeElement = this; },
        closest(selector){
          // The field container the input handler reaches for, synthesised
          // from the kind the element already carries. Without it the handler
          // returns early and a redraw put back into it would go unseen.
          if(selector === "[data-next-cockpit-held-field]"){
            const kind = dataset.nextCockpitHeldKind || dataset.arg;
            return kind === undefined ? null : {
              querySelector(inner){
                if(inner === "[data-next-cockpit-held-count]"){
                  return spans.find(span => span.dataset.nextCockpitHeldCount === kind) || null;
                }
                const action = /action="([a-z-]+)"/.exec(inner);
                return action ? controls.find(control =>
                  control.dataset.nextCockpitAction === action[1] &&
                  control.dataset.arg === kind) || null : null;
              }};
          }
          const bare = /^\[(data-[\w-]+)\]$/.exec(selector);
          return bare && dataset[camel(bare[1])] !== undefined ? this : null;
        }};
    });
    spans = [...html.matchAll(/<span\b([^>]*)>([^<]*)</g)].map(match => {
      const attrs = Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)]
        .map(attr => [attr[1], decode(attr[2])]));
      return {textContent: decode(match[2]), dataset: Object.fromEntries(
        Object.entries(attrs).filter(([key]) => key.startsWith("data-"))
          .map(([key, value]) => [camel(key), value]))};
    });
  },
  querySelectorAll(selector){
    return selector === "[data-next-focus]" ? controls.filter(control => control.dataset.nextFocus) : [];
  }
};
renderNext();
"""
    ANNOTATED = """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "Capture every screen with live sessions";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = 2;
__dashboard.sessions[0].annotation_revision_count = 2;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";

"""

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    def test_the_tab_and_its_fields_exist_only_at_session_scope(self) -> None:
        out = self.run_fixture(
            self.ANNOTATED
            + """
const seen = {};
for(const focus of [null, "codex:focus-1"]){
  navigateNext({view:"project", project:"cargento", focus, tab:focus ? "held-to" : "now"});
  await __settle();
  const html = __els.app.innerHTML;
  seen[focus || "project"] = {
    tab: html.includes('data-arg="held-to"'),
    asked: html.includes("WHAT YOU ASKED FOR"),

    goal: html.includes("Capture every screen with live sessions"),
    revision: html.includes("revision 2 of 2"),
    absence: html.includes("No expected output typed."),
    counters: (html.match(/data-next-cockpit-held-count="[a-z]+"/g) || []).length,
    clears: (html.match(/data-next-cockpit-action="held-clear" data-arg="[a-z]+">/g) || []).length,
    saves: (html.match(/data-next-cockpit-action="held-save" data-arg="[a-z]+">/g) || []).length,
  };
}
// The memo cell is asked directly, with a briefing that has something to show:
// with both notes unset and the task known it renders nothing at either scope,
// which would make the scope rule untestable through the page.
const group = nextProjectGroups().find(candidate => candidate.label === "cargento");
const briefing = {...nextCockpitRecoveryBriefing(group), outcome:"Ship the cockpit"};
seen.memo = {
  project: nextCockpitRecoveryMemoCell(group, null, briefing).length > 0,
  session: nextCockpitRecoveryMemoCell(group, nextCockpitFocusedSession(group),
    briefing).length > 0,
};
console.log(JSON.stringify(seen));
"""
        )

        # Then
        assert isinstance(out, dict)
        project, session = out["project"], out["codex:focus-1"]
        self.assertFalse(project["tab"])
        self.assertFalse(project["asked"])
        self.assertTrue(session["tab"])
        self.assertTrue(session["asked"])
        # The memo cell moves to project scope in the same commit that adds
        # these two fields: four typed fields on one session-scope page, at two
        # bounds and two save semantics, is the collision this avoids.
        self.assertEqual({"project": True, "session": False}, out["memo"])
        # What was typed, and the named reason for what was not.
        self.assertTrue(session["goal"])
        self.assertTrue(session["revision"])
        self.assertTrue(session["absence"])
        self.assertEqual(2, session["counters"])
        # `clear` only where there is text; `save` only where the draft differs
        # from what is saved, and nothing has been typed yet.
        self.assertEqual(1, session["clears"])
        self.assertEqual(0, session["saves"])

    def test_an_unannotated_session_states_both_reasons_and_offers_no_clear(self) -> None:
        out = self.run_fixture(
            """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_goal_why = "No goal typed for this session.";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
__dashboard.sessions[0].annotation_at = null;
__dashboard.sessions[0].annotation_binding_why = "";

navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  goalWhy: html.includes("No goal typed for this session."),
  outputWhy: html.includes("No expected output typed."),
  clears: (html.match(/data-next-cockpit-action="held-clear" data-arg="[a-z]+">/g) || []).length,
  revision: html.includes("No revision saved yet"),
  counts: [...html.matchAll(/data-next-cockpit-held-count="[a-z]+">([^<]*)</g)].map(m => m[1]),
}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertTrue(out["goalWhy"])
        self.assertTrue(out["outputWhy"])
        self.assertEqual(0, out["clears"])
        self.assertTrue(out["revision"])
        self.assertEqual(["0/240", "0/240"], out["counts"])

    def test_a_keystroke_updates_the_draft_and_does_not_redraw(self) -> None:
        """The live defect, and the reason the memo lane beside this one does
        not redraw either.

        A first version called `renderNext` from the input handler. Measured in
        a browser against a real session: the field is a new element after the
        replacement and the named-focus lane restores the caret a beat late, so
        typing " and green" put "neerg dna" in front of the saved value. The
        counter and the two controls are updated in place instead.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const before = __els.renders;
const input = controls.find(control => control.dataset.nextCockpitHeldKind === "output");
input.value = "Six screenshots";
__fire("input", {target:input});
await __settle();
const field = input.closest("[data-next-cockpit-held-field]");
console.log(JSON.stringify({
  redraws: __els.renders - before,
  draft: nextCockpitHeldDrafts.get("held:codex:focus-1:output"),
  // Updated in place, which is the whole of what replaces the redraw.
  liveCount: field.querySelector("[data-next-cockpit-held-count]").textContent,
  liveSave: field.querySelector('[data-next-cockpit-action="held-save"]').hidden,
  liveClear: field.querySelector('[data-next-cockpit-action="held-clear"]').hidden,
  // What the field renders from that draft, on the next redraw the reader
  // does cause. Both controls exist either way; only their hidden state moves.
  next: (() => { renderNext();
    const html = __els.app.innerHTML;
    return {
      count: (html.match(/data-next-cockpit-held-count="output">([^<]*)</) || [])[1],
      save: /data-next-cockpit-action="held-save" data-arg="output">/.test(html),
      clear: /data-next-cockpit-action="held-clear" data-arg="output">/.test(html),
      // The saved value rides on each field, because the handler compares
      // against it without a payload to hand. Both are read: the untouched
      // one carries the store's text, the edited one carries the empty string
      // it was saved with, and a save control appears only where they differ.
      saved: [...html.matchAll(/data-next-cockpit-held-saved="([^"]*)"/g)].map(m => m[1]),
    }; })(),
}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual(0, out["redraws"])
        self.assertEqual("Six screenshots", out["draft"])
        self.assertEqual("15/240", out["liveCount"])
        self.assertFalse(out["liveSave"])
        self.assertFalse(out["liveClear"])
        self.assertEqual("15/240", out["next"]["count"])
        self.assertTrue(out["next"]["save"])
        self.assertTrue(out["next"]["clear"])
        self.assertEqual(["Capture every screen with live sessions", ""], out["next"]["saved"])

    def test_escape_puts_the_saved_value_back(self) -> None:
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const input = controls.find(control => control.dataset.nextCockpitHeldKind === "output");
input.value = "Six screenshots";
__fire("input", {target:input});
renderNext();
const typed = __els.app.innerHTML;

// When: Escape on the field the draft belongs to. This one redraws, because
// it is a discrete action rather than a keystroke.
__fire("keydown", {target:input, key:"Escape", preventDefault(){}});
await __settle();
const reverted = __els.app.innerHTML;
console.log(JSON.stringify({
  typedSaves: (typed.match(/data-next-cockpit-action="held-save" data-arg="[a-z]+">/g) || []).length,
  typedCount: (typed.match(/data-next-cockpit-held-count="output">([^<]*)</) || [])[1],
  typedClears: (typed.match(/data-next-cockpit-action="held-clear" data-arg="[a-z]+">/g) || []).length,
  revertedSaves: (reverted.match(/data-next-cockpit-action="held-save" data-arg="[a-z]+">/g) || []).length,
  revertedCount: (reverted.match(/data-next-cockpit-held-count="output">([^<]*)</) || [])[1],
  draft: nextCockpitHeldDrafts.has("held:codex:focus-1:output"),
}));
"""
        )

        # Then: one save, for the field that changed, and a live counter.
        assert isinstance(out, dict)
        self.assertEqual(1, out["typedSaves"])
        self.assertEqual("15/240", out["typedCount"])
        self.assertEqual(2, out["typedClears"])
        # Escape drops the draft rather than writing the saved value into it,
        # so the render reads the store and the save goes away with it.
        self.assertEqual(0, out["revertedSaves"])
        self.assertEqual("0/240", out["revertedCount"])
        self.assertFalse(out["draft"])

    def test_a_save_the_store_could_not_write_says_so(self) -> None:
        """Finding A, raised by all three reviewing harnesses.

        `/api/annotate` answers `persisted` honestly, and the page read only
        `ok`. A write that never reached disk showed "Saved as a new revision."
        and the very next collection reloaded the store and took the words out
        of the box. The comment justifying that claimed the store said so
        itself; nothing on screen said anything.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + """
let persisted = true;
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => String(url) === "/api/annotate"
  ? {ok:true, status:200, json: async () => ({ok:true, persisted, revision:2, revision_count:2})}
  : upstream(url, init);
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const save = kind => __fire("click", {target:controls.find(control =>
  control.dataset.nextCockpitAction === "held-save" && control.dataset.arg === kind),
  preventDefault(){}});
const type = (kind, value) => {
  const input = controls.find(control => control.dataset.nextCockpitHeldKind === kind);
  input.value = value;
  __fire("input", {target:input});
};
const cue = () => (__els.app.innerHTML
  .match(/class="next-cockpit-held-cue">([^<]*)</) || [])[1];

// Given: the store cannot be written.
persisted = false;
type("output", "Six screenshots");
await __settle();
save("output");
await __settle();
const unwritable = cue();

// And: a run where it can.
persisted = true;
type("output", "Six screenshots again");
await __settle();
save("output");
await __settle();
console.log(JSON.stringify({unwritable, written: cue()}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual(
            "Saved for this run only. The store could not be written, so these words "
            "will be gone at the next refresh.",
            out["unwritable"],
        )
        self.assertEqual("Saved as a new revision.", out["written"])

    def test_a_draft_typed_while_the_save_was_open_is_not_reverted(self) -> None:
        # Finding raised by Codex. The success handler dropped the draft
        # unconditionally, so a reader who kept typing watched their newer
        # instruction be replaced by the one they had just sent.
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + """
let release;
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => {
  if(String(url) !== "/api/annotate") return upstream(url, init);
  await new Promise(resolve => { release = resolve; });
  return {ok:true, status:200, json: async () =>
    ({ok:true, persisted:true, revision:2, revision_count:2})};
};
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const input = () => controls.find(control => control.dataset.nextCockpitHeldKind === "output");
const type = value => { const box = input(); box.value = value; __fire("input", {target:box}); };

// Given: the reader saves, then keeps typing while the request is open.
type("Six screenshots");
await __settle();
__fire("click", {target:controls.find(control =>
  control.dataset.nextCockpitAction === "held-save" && control.dataset.arg === "output"),
  preventDefault(){}});
type("Six screenshots, one per screen");

// When: the save lands.
release();
await __settle();
console.log(JSON.stringify({
  draft: nextCockpitHeldDrafts.get("held:codex:focus-1:output"),
}));
"""
        )

        # Then: the newer instruction stands.
        assert isinstance(out, dict)
        self.assertEqual("Six screenshots, one per screen", out["draft"])

    def test_the_revision_line_never_prints_an_impossible_pair(self) -> None:
        """Finding B, raised by all three harnesses.

        `revision` is a save counter that keeps climbing so a dropped revision
        reads as dropped; `revision_count` is how many the store's bound keeps.
        Read as "N of M" the pair goes impossible the moment they diverge.
        """
        out = self.run_fixture(
            self.ANNOTATED
            + """
const lines = () => {
  const html = __els.app.innerHTML;
  return {
    header: (html.match(/class="next-cockpit-held-revision">([^<]*)</) || [])[1],
    rows: [...html.matchAll(/class="next-project-goal-source">([^<]*)</g)].map(m => m[1]),
  };
};
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const within = lines();
__dashboard.sessions[0].annotation_revision = 20;
__dashboard.sessions[0].annotation_revision_count = 16;
renderNext();
const past = lines();
console.log(JSON.stringify({within, past}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual("revision 2 of 2", out["within"]["header"])
        self.assertEqual("revision 20, 16 kept · older revisions dropped", out["past"]["header"])
        # And the same sentence wherever it renders, not three spellings.
        for line in out["past"]["rows"]:
            with self.subTest(row=line):
                self.assertNotIn(" of 16", line)

    def test_an_absence_reason_gives_way_to_what_is_being_typed(self) -> None:
        # The sentence answers "why is this empty", and it read the server
        # value alone, so "No goal typed for this session." rendered directly
        # under the sentence the reader was in the middle of writing.
        out = self.run_fixture(
            self.FOCUS_DOM
            + """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_goal_why = "No goal typed for this session.";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
__dashboard.sessions[0].annotation_binding_why = "Bound by an eight-character prefix.";
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const empty = __els.app.innerHTML;
const box = controls.find(control => control.dataset.nextCockpitHeldKind === "goal");
box.value = "Ship the cockpit";
__fire("input", {target:box});
renderNext();
console.log(JSON.stringify({
  emptyShowsReason: empty.includes("No goal typed for this session."),
  // The binding caveat is a claim about words. With none typed there are none.
  emptyShowsBinding: empty.includes("eight-character prefix"),
  typedShowsReason: __els.app.innerHTML.includes("No goal typed for this session."),
  typedShowsOtherReason: __els.app.innerHTML.includes("No expected output typed."),
}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertTrue(out["emptyShowsReason"])
        self.assertFalse(out["emptyShowsBinding"])
        self.assertFalse(out["typedShowsReason"])
        # The other field is still empty, so its reason stays.
        self.assertTrue(out["typedShowsOtherReason"])

    def test_the_work_evidence_keeps_each_entry_type_and_states_its_limit(self) -> None:
        """DRC-4509. What the record lets a reader inspect, beside their words.

        No judgement and no model: the rows are the payload's own facts with
        the payload's own type strings, and the reader makes the comparison.
        """
        out = self.run_fixture(
            self.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
const block = html.slice(html.indexOf('data-next-cockpit-work'));
console.log(JSON.stringify({
  rows: [...block.matchAll(/data-next-cockpit-work-type="([^"]+)"/g)].map(m => m[1]),
  sources: [...block.matchAll(/class="next-cockpit-work-source">([^<]*)</g)].map(m => m[1]),
  limit: (block.match(/class="next-cockpit-work-limit">([^<]*)</) || [])[1],
  heading: html.includes("OBSERVED RECORD"),
  mix: (html.match(/class="next-cockpit-work-mix">([^<]*)</) || [])[1],
}));
"""
        )

        # Then: the fact's own type, never a relabelling. Nothing here is
        # called a decision, because none of these sources records one.
        assert isinstance(out, dict)
        self.assertTrue(out["heading"])
        self.assertEqual(["user_message", "prepared_dispatch", "user_message"], out["rows"])
        # The heading names the record, and this line says what is in it: on
        # Claude and Codex every entry can be a direction the reader gave, and
        # the old WORK EVIDENCE heading read those back as the agent's work.
        self.assertEqual(
            "3 entries · 2 directions you gave · 1 observed of what it did.", out["mix"]
        )
        self.assertEqual(
            ["root transcript · exact", "dispatch artifact · exact", "root transcript · exact"],
            out["sources"],
        )
        # The limit is unconditional on every harness but Pi, and it is the
        # half a reader cannot infer: an absent row reads as "no work" unless
        # the page says the path that would have found it was never taken.
        self.assertEqual(
            "Codex publishes no demonstrated work results. Cargento reads those "
            "on Pi alone, so nothing above is an inspected file, test or "
            "deliverable.",
            out["limit"],
        )

    def test_the_absence_says_which_absence_it_is(self) -> None:
        """Finding C, the review's only blocker, raised by Codex and two lenses.

        "No entry in the observed record names this session" is a claim ABOUT
        a record. The block printed it while the fetch was in flight, after
        the fetch had failed, and for a session the server said in the same
        payload it had not scanned. Three different facts wearing one
        sentence, and the least true of them read as the most reassuring.
        """
        out = self.run_fixture(
            self.ANNOTATED
            + """
const absence = () => (__els.app.innerHTML
  .match(/class="next-cockpit-work-absent">([^<]*)</) || [])[1];
const route = () => navigateNext({view:"project", project:"cargento",
  focus:"claude:claude-idle", tab:"held-to"});

// Given: the project context has not come back yet.
const contexts = new Map(nextCockpitContexts);
nextCockpitContexts.clear();
route();
renderNext();
const unread = absence();

// And: it came back an error.
nextCockpitContexts.clear();
for(const [key] of contexts) nextCockpitContexts.set(key, {data:null, revision:1, error:true});
renderNext();
const failed = absence();

// And: it came back, but the server says it scanned only some sessions.
nextCockpitContexts.clear();
for(const [key, entry] of contexts){
  const data = JSON.parse(JSON.stringify(entry.data));
  data.semantic.projections.command_attention_coverage =
    {state:"incomplete", scanned:3, total:5, omitted:2, source:"bounded scan"};
  nextCockpitContexts.set(key, {data, revision:entry.revision});
}
renderNext();
const partial = absence();

// And: it came back complete, and really names nothing.
nextCockpitContexts.clear();
for(const [key, entry] of contexts) nextCockpitContexts.set(key, entry);
renderNext();
console.log(JSON.stringify({unread, failed, partial, empty: absence()}));
"""
        )

        # Then: four different facts, four different sentences.
        assert isinstance(out, dict)
        self.assertEqual(
            "The observed record for this session has not been read yet.", out["unread"]
        )
        self.assertEqual(
            "The observed record could not be read, so nothing here says what this "
            "session has been doing.",
            out["failed"],
        )
        self.assertEqual(
            "This session was outside the observed-record scan, which covered 3 of the "
            "sessions in this project and left 2 out. Its record is unread rather than empty.",
            out["partial"],
        )
        self.assertEqual("No entry in the observed record names this session.", out["empty"])
        self.assertEqual(4, len({out["unread"], out["failed"], out["partial"], out["empty"]}))

    def test_a_model_paraphrase_does_not_wear_the_register_of_a_published_line(self) -> None:
        # Finding I, raised by Codex and a lens. `actor_claim` is the string
        # the runtime computes to say who derived a snapshot, and making it
        # honest was the first fix on this branch. Dropping it at the render
        # undid that.
        out = self.run_fixture(
            self.ANNOTATED
            + """
__semantic.facts.push({fact_id:"snap", at:106, type:"observer_snapshot",
  summary:"The session appears to be capturing screens",
  actor_claim:"model-derived observer snapshot", scope:"session",
  source_session:{harness:"codex", sid:"focus-1"},
  evidence:{source:"observer sidecar", confidence:"derived"}});
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  derived: (html.match(/class="next-cockpit-work-derived">([^<]*)</) || [])[1],
  claimShown: html.includes("model-derived observer snapshot"),
  // A published line keeps the mono register beside it.
  published: (html.match(/class="next-cockpit-work-summary">([^<]*)</) || [])[1],
  mix: (html.match(/class="next-cockpit-work-mix">([^<]*)</) || [])[1],
}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual("The session appears to be capturing screens", out["derived"])
        self.assertTrue(out["claimShown"])
        # A published line keeps mono, and it is not the paraphrase.
        self.assertTrue(out["published"])
        self.assertNotEqual(out["derived"], out["published"])
        self.assertIn("1 model-derived", out["mix"])

    def test_a_long_record_is_bounded_and_says_what_it_left_out(self) -> None:
        # Measured against a real session: 26 facts in one project, 7 naming
        # one session after eleven hours, and nothing upstream caps them. A
        # tab that grows without limit is one nobody scrolls, and a cap nobody
        # is told about reads as the whole record.
        out = self.run_fixture(
            self.ANNOTATED
            + """
for(let n = 0; n < 40; n++){
  __semantic.facts.push({fact_id:`bulk-${n}`, at:200 + n, type:"user_message",
    summary:`Direction ${n}`, source_session:{harness:"codex", sid:"focus-1"},
    evidence:{source:"root transcript", confidence:"exact"}});
}
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  rows: (html.match(/data-next-cockpit-work-type=/g) || []).length,
  // Oldest first inside the window, so the rows read forward.
  first: (html.match(/class="next-cockpit-work-summary">([^<]*)</) || [])[1],
  last: [...html.matchAll(/class="next-cockpit-work-summary">([^<]*)</g)].pop()[1],
  dropped: (html.match(/class="next-cockpit-work-dropped">([^<]*)</) || [])[1],
}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual(20, out["rows"])
        self.assertEqual("Direction 20", out["first"])
        self.assertEqual("Direction 39", out["last"])
        self.assertEqual("Showing the 20 most recent of 43 observed entries.", out["dropped"])

    def test_a_session_the_record_says_nothing_about_says_so(self) -> None:
        out = self.run_fixture(
            self.ANNOTATED
            + """
// Given: a session no semantic fact names.
navigateNext({view:"project", project:"cargento", focus:"claude:claude-idle", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  rows: (html.match(/data-next-cockpit-work-type=/g) || []).length,
  absent: (html.match(/class="next-cockpit-work-absent">([^<]*)</) || [])[1],
  limit: (html.match(/class="next-cockpit-work-limit">([^<]*)</) || [])[1],
}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual(0, out["rows"])
        self.assertEqual("No entry in the observed record names this session.", out["absent"])
        self.assertIn("Claude publishes no demonstrated work results.", out["limit"])

    def test_saving_sends_only_the_field_that_changed_and_keeps_a_refusal(self) -> None:
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + """
const posts = [];
let refuse = false;
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => {
  if(String(url) !== "/api/annotate") return upstream(url, init);
  posts.push(JSON.parse(init.body));
  // The shape `/api/annotate` actually answers with, not one invented here:
  // an earlier version of this stub agreed with the page rather than with the
  // server, and the page was reading a key the server never sends.
  return refuse ? {ok:false, status:503, json: async () => ({})}
    : {ok:true, status:200, json: async () =>
      ({ok:true, persisted:true, revision:3, revision_count:3})};
};
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const type = (kind, value) => {
  const input = controls.find(control => control.dataset.nextCockpitHeldKind === kind);
  input.value = value;
  __fire("input", {target:input});
};
const save = kind => __fire("click", {target:controls.find(control =>
  control.dataset.nextCockpitAction === "held-save" && control.dataset.arg === kind),
  preventDefault(){}});

// When: type into Expected Output alone and save it.
type("output", "Six screenshots");
await __settle();
save("output");
await __settle();

// And: a save the server refuses.
refuse = true;
type("goal", "A different goal");
await __settle();
save("goal");
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({posts,
  kept: html.includes("A different goal"),
  cue: html.includes("Not saved. The server refused the write"),
  stillOffersSave: (html.match(/data-next-cockpit-action="held-save" data-arg="[a-z]+">/g) || []).length}));
"""
        )

        # Then: the untouched field goes as null, which is "leave it alone" at
        # the endpoint, so a stale draft of one cannot overwrite the other.
        assert isinstance(out, dict)
        self.assertEqual(
            [
                {
                    "harness": "codex",
                    "sid": "focus-1",
                    "goal": None,
                    "output": "Six screenshots",
                },
                {
                    "harness": "codex",
                    "sid": "focus-1",
                    "goal": "A different goal",
                    "output": None,
                },
            ],
            out["posts"],
        )
        # A refused write keeps what was typed. Losing it to report the failure
        # is the one outcome worse than the failure.
        self.assertTrue(out["kept"])
        self.assertTrue(out["cue"])
        self.assertEqual(1, out["stillOffersSave"])

    def test_the_reading_has_three_states_and_the_control_waits_on_a_check(self) -> None:
        """DRC-4511. Nothing typed, the model off, and the offer itself."""
        out = self.run_fixture(
            """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.reading_check = "not-run";
const read = () => {
  const html = __els.app.innerHTML;
  const block = html.slice(html.indexOf('class="next-cockpit-reading"'));
  return {
    text: (block.match(/class="next-cockpit-reading-why">([^<]*)</) || [])[1],
    control: block.includes('data-next-cockpit-action="reading-ask"'),
    disabled: /data-next-cockpit-action="reading-ask"[^>]*disabled/.test(block),
    departures: html.includes("DEPARTURES RAISED TO YOU"),
  };
};

// Given: nothing typed.
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_goal_why = "No goal typed for this session.";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
__dashboard.sessions[0].annotation_at = null;
__dashboard.sessions[0].annotation_binding_why = "";

navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const empty = read();

// And: words typed, with the observer model unread for this project.
__dashboard.sessions[0].annotation_goal = "Ship the cockpit";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";

renderNext();
const unread = read();

// And: the model enabled, which is the offer.
const key = nextCockpitContextKey(nextProjectGroups().find(g => g.label === "cargento"),
  nextCockpitFocusedSession(nextProjectGroups().find(g => g.label === "cargento")));
const entry = nextCockpitContexts.get(key);
entry.data = Object.assign({}, entry.data, {observer_model:{enabled:true, disclosure:"x"}});
renderNext();
const offered = read();

// And: the check recorded as passed, which is the only thing that enables it.
__dashboard.reading_check = "passed";
renderNext();
const enabled = read();
console.log(JSON.stringify({empty, unread, offered, enabled}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual(
            "Nothing has been typed for this session, so there is nothing to read it against.",
            out["empty"]["text"],
        )
        self.assertFalse(out["empty"]["control"])
        self.assertIn("Observer model availability has not been read", out["unread"]["text"])
        self.assertFalse(out["unread"]["control"])
        # The offer states what a reading may and may not read, before the
        # control rather than after it.
        self.assertIn("never a verification that the work was done", out["offered"]["text"])
        self.assertTrue(out["offered"]["control"])
        self.assertTrue(out["offered"]["disabled"])
        # Enablement reads the recorded result, not a constant.
        self.assertTrue(out["enabled"]["control"])
        self.assertFalse(out["enabled"]["disabled"])
        # No reading, so no departures block: an empty one would imply a
        # reading had run and raised nothing.
        self.assertFalse(out["offered"]["departures"])

    def test_a_reading_that_read_an_older_revision_says_so(self) -> None:
        out = self.run_fixture(
            """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "do not change the board";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = 2;
__dashboard.sessions[0].annotation_revision_count = 2;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";
// Not a published field: nothing produces a reading, so the backend declares
// none and the renderer reads whatever a producer would put here.
__dashboard.sessions[0].annotation_assessment = {
  revision_read:1, stamp:"observer model · consented at 13:36",
  cutoff:"Evidence stops at 13:22.",
  criteria:{goal:{result:"departure", detail:"Two turns edited the board.", cites:["fo-a"]}}
};

navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  stale: (html.match(/class="next-cockpit-reading-stale">([^<]*)</) || [])[1],
  stamp: (html.match(/class="next-cockpit-reading-stamp">([^<]*)</) || [])[1],
  stamps: (html.match(/class="next-cockpit-reading-stamp"/g) || []).length,
  result: (html.match(/class="next-cockpit-reading-result">([^<]*)</) || [])[1],
  departures: html.includes("DEPARTURES RAISED TO YOU"),
  cutoff: html.includes("Evidence stops at 13:22."),
}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual(
            "This reading read revision 1. Revision 2 is current, so it does not describe "
            "what you are asking for now.",
            out["stale"],
        )
        # One stamp, in the header, rather than one per block.
        self.assertEqual(1, out["stamps"])
        self.assertEqual("observer model · consented at 13:36", out["stamp"])
        self.assertEqual("departure", out["result"])
        self.assertTrue(out["departures"])
        self.assertTrue(out["cutoff"])

    def test_no_field_is_offered_when_the_store_is_off(self) -> None:
        out = self.run_fixture(
            """
// Given: --no-annotations, so the payload carries no capability at all.
delete __dashboard.annotate;
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  tab: html.includes('data-arg="held-to"'),
  inputs: (html.match(/data-next-cockpit-held-key/g) || []).length,
  reason: html.includes("Annotations are off for this run"),
}));
"""
        )

        # Then: the tab still parses from a bookmarked link, and it carries
        # the reason instead of a field whose every save would answer 503.
        assert isinstance(out, dict)
        self.assertTrue(out["tab"])
        self.assertEqual(0, out["inputs"])
        self.assertTrue(out["reason"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitReadingShapeTest(NextPageJsHarness):
    """DEC-17's seven rules, one case each (DRC-4511 AC4).

    Asserted against source-shaped fixtures rather than against expected
    judgements, because there is no producer to judge and DEC-17 refuses a
    rubric validated on fixtures the same pass wrote. What these hold is that
    the three worst outputs cannot be rendered: the word "met", a departure
    citing nothing, and a deliverable claim on a harness with no work
    evidence.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE
    ENTRIES = """
const entries = [
  {id:"u1", type:"user_message", by:"", source:"root transcript · exact"},
  {id:"a1", type:"result", by:"", source:"dispatch artifact · exact"},
  {id:"g1", type:"gate_decision", by:"person:captain", source:"entity gate · exact"},
  {id:"empty", type:"", by:"", source:""}
];
const annotation = {goal:"do not change the board", output:"six screenshots"};
const shape = (criteria, limit) => nextCockpitReadingShape({criteria}, annotation, entries,
  limit || "");
const results = (criteria, limit) => Object.fromEntries(
  shape(criteria, limit).criteria.map(row => [row.key, row.result]));
"""

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    def test_rule_1_a_result_outside_the_closed_set_becomes_not_verifiable(self) -> None:
        out = self.run_fixture(
            self.ENTRIES
            + """
console.log(JSON.stringify({
  met: results({goal:{result:"met", cites:["u1"]}, output:{result:"met", cites:["u1"]}}),
  invented: results({goal:{result:"mostly on track", cites:["u1"]}}),
  closed: NEXT_READING_RESULTS,
}));
"""
        )
        assert isinstance(out, dict)
        unverifiable = "not verifiable from available evidence"
        self.assertEqual({"goal": unverifiable, "output": unverifiable}, out["met"])
        self.assertEqual(unverifiable, out["invented"]["goal"])
        self.assertEqual(
            ["departure", "consistent with the evidence read", unverifiable], out["closed"]
        )

    def test_rule_2_absent_or_unparseable_output_falls_to_not_verifiable(self) -> None:
        out = self.run_fixture(
            self.ENTRIES
            + """
console.log(JSON.stringify({
  missing: results({}),
  garbage: results({goal:"a string, not a row", output:[]}),
  noReading: nextCockpitReadingShape(null, annotation, entries, "").criteria.map(r => r.result),
  why: shape({}).criteria[0].why,
}));
"""
        )
        assert isinstance(out, dict)
        unverifiable = "not verifiable from available evidence"
        self.assertEqual({"goal": unverifiable, "output": unverifiable}, out["missing"])
        self.assertEqual({"goal": unverifiable, "output": unverifiable}, out["garbage"])
        self.assertEqual([unverifiable, unverifiable], out["noReading"])
        self.assertEqual(
            "The reading did not return a usable result for this constraint.", out["why"]
        )

    def test_rule_3_a_departure_needs_a_citation_that_resolves(self) -> None:
        out = self.run_fixture(
            self.ENTRIES
            + """
console.log(JSON.stringify({
  none: results({goal:{result:"departure", detail:"It drifted."}}),
  unknownId: results({goal:{result:"departure", cites:["nothing-here"]}}),
  // An entry the page holds but that names no type or source is not a
  // resolvable citation either.
  blankEntry: results({goal:{result:"departure", cites:["empty"]}}),
  resolvable: results({goal:{result:"departure", cites:["u1"]}}),
  // A `consistent` resting on nothing is demoted by the same rule.
  emptyConsistent: results({goal:{result:"consistent with the evidence read"}}),
  why: shape({goal:{result:"departure"}}).criteria[0].why,
  departures: shape({goal:{result:"departure", cites:["u1"]}}).departures.length,
}));
"""
        )
        assert isinstance(out, dict)
        unverifiable = "not verifiable from available evidence"
        self.assertEqual(unverifiable, out["none"]["goal"])
        self.assertEqual(unverifiable, out["unknownId"]["goal"])
        self.assertEqual(unverifiable, out["blankEntry"]["goal"])
        self.assertEqual("departure", out["resolvable"]["goal"])
        self.assertEqual(unverifiable, out["emptyConsistent"]["goal"])
        self.assertEqual(
            "Nothing resolvable was cited, so there is no entry to read this against.",
            out["why"],
        )
        self.assertEqual(1, out["departures"])

    def test_rule_4_the_word_met_cannot_reach_the_page(self) -> None:
        out = self.run_fixture(
            self.ENTRIES
            + """
// Every reachable result string, rendered, plus a producer trying to say met.
const html = [
  {goal:{result:"met", cites:["u1"]}},
  {goal:{result:"departure", detail:"met the wrong thing", cites:["u1"]}},
  {goal:{result:"consistent with the evidence read", cites:["u1"]}},
].map(criteria => shape(criteria).criteria.map(nextCockpitReadingCriterionRow).join("")).join("");
console.log(JSON.stringify({
  // The detail is the producer's prose and is escaped, not filtered: the rule
  // is about the RESULT, which is only ever one of three constants.
  resultStrings: [...html.matchAll(/class="next-cockpit-reading-result">([^<]*)</g)]
    .map(m => m[1]),
}));
"""
        )
        assert isinstance(out, dict)
        # Two rows per case, goal then output. The output row has no producer
        # entry in any of the three, so it lands on the fallback each time.
        unverifiable = "not verifiable from available evidence"
        self.assertEqual(
            [
                unverifiable,
                unverifiable,
                "departure",
                unverifiable,
                "consistent with the evidence read",
                unverifiable,
            ],
            out["resultStrings"],
        )
        for value in out["resultStrings"]:
            with self.subTest(result=value):
                self.assertNotEqual("met", value)

    def test_rule_5_a_stated_limit_is_never_a_consistent(self) -> None:
        out = self.run_fixture(
            self.ENTRIES
            + """
const limit = nextCockpitWorkEvidenceLimit("codex");
const rows = shape({goal:{result:"consistent with the evidence read", cites:["u1"]},
  output:{result:"departure", cites:["u1"]}}, limit).criteria;
console.log(JSON.stringify({
  limited: Object.fromEntries(rows.map(row => [row.key, row.result])),
  // Mutually exclusive per row: it states its evidence or states its limit.
  evidence: Object.fromEntries(rows.map(row => [row.key, row.evidence])),
  limits: Object.fromEntries(rows.map(row => [row.key, row.limit])),
  why: rows.find(row => row.key === "output").why,
}));
"""
        )
        assert isinstance(out, dict)
        unverifiable = "not verifiable from available evidence"
        # The limit is what `_work_evidence` would have supplied, which is
        # deliverables. It bears on Expected Output and not on Goal: a
        # transcript is exactly the evidence a change of direction leaves.
        self.assertEqual(
            {"goal": "consistent with the evidence read", "output": unverifiable},
            out["limited"],
        )
        self.assertEqual(
            {"goal": ["user_message · root transcript · exact"], "output": []}, out["evidence"]
        )
        self.assertEqual("", out["limits"]["goal"])
        self.assertIn("publishes no demonstrated work results", out["limits"]["output"])
        # The limit has its own row. Setting `why` to the same string printed
        # the identical sentence twice, the second prefixed `limit ·`.
        self.assertEqual("", out["why"])

    def test_rule_6_the_two_constraints_stay_separate_and_name_themselves(self) -> None:
        out = self.run_fixture(
            self.ENTRIES
            + """
const one = nextCockpitReadingShape({criteria:{goal:{result:"departure", cites:["u1"]}}},
  {goal:"do not change the board", output:""}, entries, "");
console.log(JSON.stringify({
  both: shape({}).criteria.map(row => [row.key, row.label, row.clause]),
  goalOnly: one.criteria.map(row => row.key),
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(
            [
                ["goal", "TYPED GOAL", "do not change the board"],
                ["output", "EXPECTED OUTPUT", "six screenshots"],
            ],
            out["both"],
        )
        # A constraint nobody typed is not read, rather than read and passed.
        self.assertEqual(["goal"], out["goalOnly"])

    def test_rule_7_is_asymmetric_on_who_wrote_the_evidence(self) -> None:
        out = self.run_fixture(
            self.ENTRIES
            + """
const assistant = ["a1"];
const person = ["u1"];
const gate = ["g1"];
console.log(JSON.stringify({
  // Expected Output on self-report alone: nothing but not verifiable.
  outputAssistant: results({output:{result:"departure", cites:assistant}}),
  outputConsistent: results({output:{result:"consistent with the evidence read",
    cites:assistant}}),
  outputPerson: results({output:{result:"departure", cites:person}}),
  // Goal keeps a departure on the agent's own narration.
  goalAssistant: results({goal:{result:"departure", cites:assistant}}),
  // And a consistent resting only on it says so.
  narration: shape({goal:{result:"consistent with the evidence read",
    cites:assistant}}).criteria[0].narration,
  corroborated: shape({goal:{result:"consistent with the evidence read",
    cites:person}}).criteria[0].narration,
  // A gate decision counts as a person's only where the source records one.
  gateIsPerson: shape({output:{result:"departure", cites:gate}}).criteria
    .find(row => row.key === "output").result,
  why: shape({output:{result:"departure", cites:assistant}}).criteria
    .find(row => row.key === "output").why,
}));
"""
        )
        assert isinstance(out, dict)
        unverifiable = "not verifiable from available evidence"
        self.assertEqual(unverifiable, out["outputAssistant"]["output"])
        self.assertEqual(unverifiable, out["outputConsistent"]["output"])
        self.assertEqual("departure", out["outputPerson"]["output"])
        self.assertEqual("departure", out["goalAssistant"]["goal"])
        self.assertEqual("Rests on the agent's own account alone.", out["narration"])
        self.assertEqual("", out["corroborated"])
        self.assertEqual("departure", out["gateIsPerson"])
        self.assertEqual(
            "Every entry cited here was written by the agent, which is not evidence "
            "that the requested output exists.",
            out["why"],
        )


class CockpitTabsAreOneDecisionTest(unittest.TestCase):
    """The tab set is about to depend on scope, so it may be decided once.

    Thirteen sites read the tab list and six of them are the keyboard wrap
    alone. A wrap computed over a list the nav did not render is what sends a
    reader to a tab that is not on their screen, and nothing in the suite would
    have said so, because at one scope the two lists agree.
    """

    WEB = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"

    def test_the_tab_list_is_read_through_one_function(self) -> None:
        stray = []
        for name in ("next-boot.js", "next-cockpit.js"):
            owner = ""
            for number, line in enumerate(
                (self.WEB / name).read_text(encoding="utf-8").splitlines(), start=1
            ):
                if line.startswith("function "):
                    owner = line[len("function ") :].split("(", 1)[0]
                if "NEXT_PROJECT_TABS" not in line:
                    continue
                # The declaration and the one reader are the whole allowance.
                if line.startswith("const NEXT_PROJECT_TABS") or owner == "nextCockpitTabs":
                    continue
                stray.append(f"{name}:{number} ({owner or 'top level'})")
        self.assertEqual([], stray, "these read the tab list instead of nextCockpitTabs")


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitTabKeyboardWrapTest(NextPageJsHarness):
    FIXTURE = NextCockpitCompositionTest.FIXTURE
    FOCUS_DOM = NextCockpitCompositionTest.FOCUS_DOM

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    def test_the_wrap_reaches_exactly_the_tabs_the_nav_rendered(self) -> None:
        out = self.run_fixture(
            self.FOCUS_DOM
            + """
// Given: the cockpit at project scope, and again with one session focused.
const scopes = {};
for(const focus of [null, "codex:focus-1", "codex:gone"]){
  navigateNext({view:"project", project:"cargento", focus, tab:"now"});
  await __settle();
  const html = __els.app.innerHTML;
  const start = html.indexOf('<nav class="next-cockpit-tabs"');
  const rendered = start < 0 ? []
    : [...html.slice(start).matchAll(/data-next-cockpit-action="tab" data-arg="([a-z-]+)"/g)]
      .map(match => match[1]);

  // When: walk right once per rendered tab, starting from the first.
  const walked = [];
  if(rendered.length){
    controls.find(control => control.dataset.arg === rendered[0]).focus();
    for(let step = 0; step < rendered.length; step++){
      __fire("keydown", {target:document.activeElement, key:"ArrowRight", preventDefault(){}});
      walked.push(nextRoute.tab || "now");
    }
  }
  scopes[focus || "project"] = {rendered, walked};
}
console.log(JSON.stringify(scopes));
"""
        )

        # Then: the walk visits every rendered tab in order and comes back.
        assert isinstance(out, dict)
        self.assertEqual(3, len(out))
        for scope, seen in out.items():
            with self.subTest(scope=scope):
                rendered = seen["rendered"]
                self.assertEqual(rendered[1:] + rendered[:1], seen["walked"])
        # The two scopes no longer hold the same tabs, which is what the walk
        # above exists to survive: `Held to` is session scope only, so a wrap
        # computed over the project list would skip it on the reader's screen.
        self.assertEqual(["now", "course", "decisions", "console"], out["project"]["rendered"])
        self.assertEqual(
            ["now", "course", "decisions", "console", "held-to"],
            out["codex:focus-1"]["rendered"],
        )
        # A route whose focus names no session in the payload draws the stale
        # filter surface instead of a cockpit, so it has no tabs to disagree
        # about. Asserted rather than assumed: it is the reason the empty case
        # above is legal.
        self.assertEqual([], out["codex:gone"]["rendered"])


if __name__ == "__main__":
    unittest.main()
