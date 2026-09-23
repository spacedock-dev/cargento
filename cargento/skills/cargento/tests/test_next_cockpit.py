from __future__ import annotations

import itertools
import json
import pathlib
import re
import shutil
import subprocess
import unittest
from typing import Any, ClassVar, cast

from cargento_runtime import annotations as annotation_store
from cargento_runtime import departures
from cargento_runtime.web import page as frontend_page

from . import css_cascade
from .js_literals import emitted_strings, reading_why_sentences
from .next_harness import NextPageJsHarness, published_routes, storage_prelude

# The joiner `projectGraphModeScope` builds its storage key with. Written as
# an escape rather than inline, so a reader sees a separator rather than an
# invisible byte, and so an editor cannot silently eat it.
NUL_CHAR = "\u0000"

# One standing raise from the unasked lane, for a test that needs the lane-off
# departures section drawn. With the lane off and nothing on record the section
# is absent (DRC-4543); a raise on record keeps it, whichever way the switch is
# set (DRC-4559).
STANDING_RAISE = (
    '__dashboard.sessions[0].departures = [{constraint:"TYPED GOAL",'
    ' clause:"do not change the board while capturing",'
    ' reading:"Two turns edited the running board.", evidence:"e1", revision:2,'
    ' cutoff:100, at:101, follow_up:""}];\n'
    '__dashboard.sessions[0].departure_why = "";\n'
)


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextCockpitCompositionTest(NextPageJsHarness):
    FIXTURE = (
        """
location.hash = "#n=project:cargento";
__els.app = {innerHTML: ""};
const __dashboard = {
  reading_routes: """
        + published_routes("codex", "pi", "claude")
        + """,
  reading:{consent:true, reason:"", used:0, limit:12},
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
    )

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

    def test_stage_conditions_are_reachable_in_course_and_empty_projects(self) -> None:
        out = self.run_fixture("""
const id = "a".repeat(64);
__dashboard.tripwires = {enabled:true, error:"", sources:[{id, workflow:"review-flow",
  goal:"Review work", stages:["build","review"], evaluated:1, partial:false,
  entities:[{slug:"task",stage:"build",source:"entity-state",source_written_at:100,observed_at:105}],
  sessions:[{harness:"codex",sid:"focus-1",label:"Shape project cockpit"}]}], rules:[]};
nextData = __dashboard;
nextRoute = {view:"project",project:"cargento",tab:"course"};
renderNext();
const course = __els.app.innerHTML;
__dashboard.sessions = [];
__dashboard.tripwires.sources = [];
__dashboard.tripwires.rules = [{id,workflow:"review-flow",stage:"review",revision:"b".repeat(32),
  state:"armed",why:"Workflow stage source unavailable; saved condition is suspended.",available:false}];
nextRoute = {view:"projects"};
renderNext();
console.log(JSON.stringify({course,projects:__els.app.innerHTML}));
""")
        assert isinstance(out, dict)
        self.assertIn("Alert once when an observed entity enters", out["course"])
        self.assertIn('data-stage-action="save"', out["course"])
        self.assertIn("review-flow", out["projects"])
        self.assertIn('data-stage-action="remove"', out["projects"])

    def test_removed_stage_remains_visibly_unavailable_and_off_switch_is_explicit(self) -> None:
        out = self.run_fixture("""
const id = "a".repeat(64);
const source = {id,workflow:"flow",goal:"",generation:"current",stages:["build","done"],
  entities:[],sessions:[{harness:"codex",sid:"focus-1",label:"source"}]};
const rule = {id,workflow:"flow",stage:"review",revision:"b".repeat(32),state:"armed",available:false};
__dashboard.tripwires = {enabled:true,source_enabled:true,rules:[rule],sources:[source]};
nextData = __dashboard;
const saved = nextStageConditions();
nextStageDrafts.set(id,"removed-draft");
const draft = nextStageConditions();
nextStageDrafts.set(id,"build");
const valid = nextStageConditions();
__dashboard.tripwires = {enabled:true,source_enabled:false,rules:[rule],sources:[]};
const off = nextStageConditions();
__dashboard.tripwires.rules = [];
const empty = nextStageConditions();
nextRoute = {view:"attention"}; renderNext();
console.log(JSON.stringify({saved,draft,valid,off,empty,attention:__els.app.innerHTML}));
""")
        assert isinstance(out, dict)
        self.assertIn(
            '<option value="review" selected disabled>review (unavailable)</option>', out["saved"]
        )
        self.assertIn('<option value="removed-draft" selected disabled>', out["draft"])
        for key in ("saved", "draft"):
            self.assertRegex(out[key], r'data-stage-action="save"[^>]+ disabled')
        self.assertNotRegex(out["valid"], r'data-stage-action="save"[^>]+ disabled')
        for key in ("off", "empty"):
            self.assertIn("Project reads are off (--no-spacedock)", out[key])
        self.assertNotIn('data-next-open="C1"', out["attention"])
        self.assertNotIn('data-next-open="C4"', out["attention"])

    def test_stage_save_restores_focus_after_success_and_error_without_stealing(self) -> None:
        dom = (
            self.FOCUS_DOM.replace("(button|a|textarea)", "(button|a|textarea|select)")
            .replace(
                'return {dataset, tagName:match[1].toUpperCase(), value:"", attrs,',
                'return {dataset, tagName:match[1].toUpperCase(), value:"", attrs, disabled:/ disabled/.test(match[2]),',
            )
            .replace(
                "focus(){ document.activeElement = this; },",
                "focus(){ if(!this.disabled) document.activeElement = this; },",
            )
            .replace(
                'closest(selector){ return selector === "[data-next-cockpit-action]" && dataset.nextCockpitAction ? this : null; }',
                'closest(selector){ return selector === "[data-stage-action]" && dataset.stageAction ? this : null; }',
            )
        )
        out = self.run_fixture(
            """
const id = "a".repeat(64);
__dashboard.tripwires = {enabled:true,error:"",rules:[],sources:[{id,workflow:"flow",goal:"",generation:"current",
  stages:["build","review"],entities:[],sessions:[{harness:"codex",sid:"focus-1",label:"source"}]}]};
nextData = __dashboard;
nextRoute = {view:"project",project:"cargento",tab:"course"};
"""
            + dom
            + """
const seen = [];
for(const kind of ["success","error","moved"]){
  renderNext();
  const button = controls.find(c => c.dataset.stageAction === "save");
  button.focus();
  let resolve;
  __fetchImpl = url => String(url) === "/api/tripwire" ? new Promise(r => {resolve=r;}) :
    Promise.resolve({ok:true,json:async()=>__dashboard});
  __fire("click",{target:button,preventDefault(){}});
  let requested = "";
  if(kind === "moved"){
    __fire("pointerdown",{target:document.body});
    const other = controls.find(c => c.dataset.nextFocus && !c.dataset.nextFocus.startsWith("stage:"));
    requested = other.dataset.nextFocus;
    other.focus();
  }
  resolve({ok:kind !== "error",json:async()=>({ok:kind !== "error",error:"Could not save test condition."})});
  await __settle(); await __settle();
  seen.push({kind,requested,focus:document.activeElement && document.activeElement.dataset.nextFocus,
    cue:nextStageCues.get(id)});
}
console.log(JSON.stringify(seen));
"""
        )
        assert isinstance(out, list)
        self.assertEqual(
            ["stage:" + "a" * 64 + ":save"] * 2 + [out[2]["requested"]],
            [row["focus"] for row in out],
        )
        self.assertEqual(
            ["Saved.", "Could not save test condition.", "Saved."], [row["cue"] for row in out]
        )

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
        self.assertNotIn("Actionable direction not observed", out)
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
        # And the sentence is about THIS session, not the project: the
        # derived row used to borrow whichever sibling moved most recently.
        self.assertIn(
            'next-project-value--absent next-project-goal-text">This session published no goal',
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

    def test_the_derived_row_is_the_focused_sessions_own_directive(self) -> None:
        """Finding D, raised independently by Antigravity, Codex and a lens.

        `nextObservedProject` picks the goal of whichever session moved most
        recently. Rendered beside one session's typed words that is another
        session's directive under DERIVED FROM THE HARNESS, and the apparent
        disagreement reads as a departure when the two concern different work.
        """
        out = self.run_fixture(
            r"""
// Given: the focused session asked for one thing, a more recently active
// sibling for another.
__dashboard.sessions[0].instruction = {label:"asked", text:"Shape the cockpit", at:40};
__dashboard.sessions[0].last_activity = 90;
__dashboard.sessions[0].annotation_goal = "Shape the cockpit";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";
__dashboard.sessions[1].instruction = {label:"asked", text:"Migrate the database", at:95};
__dashboard.sessions[1].last_activity = 104;

const read = () => {
  const html = __els.app.innerHTML;
  const block = html.slice(html.indexOf('class="next-project-goal"'));
  const rows = [...block.matchAll(
    /goal-tag">([^<]*)<\/span><span class="[^"]*next-project-goal-text">([^<]*)</g)];
  return {rows: rows.map(m => [m[1], m[2]]),
    gap: /class="next-project-goal-gap">([^<]*)</.exec(block)};
};

nextRoute = {view:"project",project:"cargento",focus:"codex:focus-1",tab:"now"};
renderNext();
const focused = read();
nextRoute = {view:"project",project:"cargento",tab:"now"};
renderNext();
const project = read();
console.log(JSON.stringify({focused: focused.rows, focusedGap: Boolean(focused.gap),
  projectGap: Boolean(project.gap)}));
"""
        )

        # Then: the derived row is this session's directive, never the sibling's.
        assert isinstance(out, dict)
        self.assertEqual(
            [
                ["YOUR WORDS · GOAL", "Shape the cockpit"],
                ["DERIVED FROM THE HARNESS", "Shape the cockpit"],
            ],
            out["focused"],
        )
        # And the project-wide "N of M sessions publish no goal" count belongs
        # to the project's render, not beside one session's words.
        self.assertFalse(out["focusedGap"])
        self.assertTrue(out["projectGap"])

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
        # Folded into the tab lede by DRC-4608. It was its own paragraph with no
        # rule in the sheet, so it rendered unstyled under this one.
        self.assertIn("It stays project-wide, including activity from other sessions.", out)
        self.assertNotIn("next-cockpit-scope-note", out)
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
        self.assertNotIn("Assignment evidence not published", out)
        self.assertIn("Not observed", out)
        self.assertIn("Actionable direction not observed", out)
        self.assertIn("Session result not observed", out)
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
        self.assertIn("Actionable direction not observed", out)

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
        # The label is followed by its derived cue on the tabs that carry one,
        # so each is bound to the start of its own button's content rather than
        # to the close tag. Mutating the label or the button still breaks this;
        # adding a cue after the label does not.
        for label in ("Now", "Course", "Decisions", "Console"):
            self.assertTrue(
                any(
                    re.search(rf">{label}(?:<span class=\"next-cockpit-tab-cue|</button>)", tab)
                    for tab in out["tabs"]
                )
            )
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
// Stop at the briefing's own close, not at the last section before the tabs.
// DRC-4595 moved the steer composer into the project chrome as a sibling
// <section> in that gap, and a lookahead anchored only on the tabs nav
// swallowed it -- charging a control's 26 words to the briefing's word budget.
const mirror=(html.match(/<section class="next-cockpit-recovery"[\\s\\S]*?<\\/section>(?=<section class="next-control|<nav class="next-cockpit-tabs")/)||[""])[0];
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
            "GUARDRAILS · LOCAL ONLY",
            "<textarea",
        ):
            self.assertNotIn(old_surface, panel)
        # DRC-4595 moved the composer to the chrome, which made "absent from
        # this panel" true of every panel and of no arrangement in particular.
        # Re-pointed at the pair, so the assertion still measures a placement:
        # out of the panel, and present once in the shell around it.
        assert isinstance(panel, str)
        self.assertNotIn("STEER · LOCAL ONLY", panel)
        self.assertEqual(1, str(out["html"]).count("STEER · LOCAL ONLY"))
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
        # A session row keeps the marker and the connector rule, which carry the
        # kind without words, and keeps the word itself in its accessible name.
        # The full cue block stays on the project row and at the ten other sites
        # that emit one; printing it on every session row was the repetition the
        # rail was rebuilt to remove.
        self.assertIn('<span class="next-visually-hidden">SESSION</span>', out["session"])
        self.assertNotIn(
            'class="next-scope-cue next-scope-cue--session"',
            (out["session"].split('class="next-cockpit-scope-tree"')[1] or "").split("</nav>")[0],
        )
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
        self.assertIn("<h2>TRIPWIRES</h2>", project_panel)
        self.assertIn("local only · nothing enforces these", project_panel)
        self.assertIn("data-next-delegation", project_panel)
        # The composer is no longer the last child of TRIPWIRES. Re-pointed at
        # where it went rather than deleted: it renders once per route, in the
        # chrome, at both project and session scope.
        for scope, shell, panel in (
            ("project", str(out["project"]), project_panel),
            ("session", str(out["session"]), session_panel),
        ):
            with self.subTest(scope=scope):
                self.assertEqual(1, shell.count("STEER · LOCAL ONLY"))
                self.assertNotIn("STEER · LOCAL ONLY", panel)
        self.assertIn("Raw project status", project_panel)
        self.assertNotIn("Latest decisions", project_panel)

    # --- DRC-4595: operations first, and the composer out of TRIPWIRES -------

    CONSOLE_SETUP = 'class="next-cockpit-console-setup"'

    def _console(self, extra: str = "") -> dict[str, object]:
        """Render the session-scoped Console and hand back the shell and panel."""
        out = self.run_fixture(
            """
nextCockpitContexts.clear();
"""
            + extra
            + """
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1:console");
renderNext();await __settle();await __settle();
const shell=__els.app.innerHTML;
console.log(JSON.stringify({shell,
  panel:shell.slice(shell.indexOf('data-next-cockpit-panel="console"'))}));
"""
        )
        assert isinstance(out, dict)
        return out

    def test_console_puts_the_operations_rail_ahead_of_the_setup_disclosure(self) -> None:
        """AC-1. Today the rail is emitted last, at next-cockpit.js:3402.

        The disclosure's POSITION was the whole assertion, and its position is
        not what the criterion is about. Hoisting `nextCockpitConsoleStatus`
        above the rail -- literally this criterion's own Falsified-by condition
        -- left `rail < setup` true, so AC-1 stayed green, the whole cockpit
        module stayed green, and the live rail offset moved 111.5px -> 174.5px,
        breaking AC-8 by 55px. A criterion whose named falsifier passes is not a
        verified criterion.

        So every part of the setup block is held behind the rail, not just the
        `<details>` that wraps them. `console-status` is the one that moved.
        """
        panel = str(self._console()["panel"])

        scope = panel.index("next-cockpit-scope")
        rail = panel.index("data-next-project-rail")
        setup = panel.index(self.CONSOLE_SETUP)
        self.assertLess(scope, rail)
        self.assertLess(rail, setup)
        self.assertEqual(1, panel.count(self.CONSOLE_SETUP))
        # Nothing the disclosure exists to hide may precede the rail, and the
        # status must still be INSIDE it rather than merely after it.
        status = panel.index("data-next-cockpit-console-status")
        self.assertLess(rail, status, "setup content was hoisted above the operations rail")
        self.assertLess(setup, status, "the raw status left the setup disclosure")
        shut = panel.index("</details>", setup)
        self.assertLess(status, shut, "the raw status is no longer inside the setup disclosure")

    def test_the_scope_header_and_the_project_prompt_stay_out_of_the_disclosure(self) -> None:
        """AC-2. Collapsing the prompt would leave project scope with no way in."""
        out = self.run_fixture(
            """
nextCockpitContexts.clear();
nextRoute=nextRouteFromFragment("#n=project:cargento:console");
renderNext();await __settle();await __settle();
const shell=__els.app.innerHTML;
console.log(JSON.stringify({panel:shell.slice(
  shell.indexOf('data-next-cockpit-panel="console"'))}));
"""
        )
        assert isinstance(out, dict)
        panel = str(out["panel"])

        setup = panel.index(self.CONSOLE_SETUP)
        self.assertLess(panel.index("next-cockpit-scope"), setup)
        prompt = "Select one exact session to open its read-only console."
        self.assertIn(prompt, panel)
        self.assertLess(panel.index(prompt), setup)
        self.assertNotIn(prompt, panel[setup:])

    def test_the_setup_summary_reads_the_flags_and_an_enabled_capability_leaves_it(self) -> None:
        """AC-3. Derived from the flags, never from whether a body came back.

        `nextCockpitTerminal` returns "" with no focus and
        `nextCockpitConsoleStatus` returns "" with no sessions, so a summary
        read off the rendered body would report an enabled bridge as off.
        """
        out = self.run_fixture(
            r"""
nextCockpitContexts.clear();
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1:console");
renderNext();await __settle();await __settle();
const group=nextProjectGroups().find(g=>g.label==="cargento");
const focus=nextCockpitFocusedSession(group);
const entry=nextCockpitContexts.get(nextCockpitContextKey(group,focus));
// The setup disclosure nests the console-status <details>, so the matching
// close tag is found by depth rather than by the first "</details>".
const read=()=>{
  const html=__els.app.innerHTML;
  const panel=html.slice(html.indexOf('data-next-cockpit-panel="console"'));
  const open=panel.lastIndexOf("<details",panel.indexOf('class="next-cockpit-console-setup"'));
  let depth=0,shut=open;
  for(const token of panel.slice(open).matchAll(/<details|<\/details>/g)){
    depth+=token[0]==="<details"?1:-1;
    if(depth===0){ shut=open+token.index; break; }
  }
  const body=panel.slice(open,shut);
  return {summary:(panel.slice(open).match(/<summary>([^<]*)<\/summary>/)||[])[1]||"",
    insideOff:body.includes("Observer model is disabled for this run"),
    insideOn:body.includes("data-next-observer-consent"),
    presentOff:panel.includes("Observer model is disabled for this run"),
    present:panel.includes("data-next-observer-consent")};
};
entry.data=Object.assign({},entry.data,{observer_model:{enabled:false}});
renderNext();const off=read();
entry.data=Object.assign({},entry.data,{observer_model:{enabled:true,disclosure:"x"}});
renderNext();const on=read();
console.log(JSON.stringify({off,on}));
"""
        )
        assert isinstance(out, dict)
        off = out["off"]
        on = out["on"]
        assert isinstance(off, dict)
        assert isinstance(on, dict)

        self.assertIn("observer model off", off["summary"])
        self.assertIn("observer model on", on["summary"])
        self.assertIn("terminal bridge off", off["summary"])
        # Off: the section is rendered, and it is inside the disclosure.
        self.assertTrue(off["presentOff"])
        self.assertTrue(off["insideOff"])
        # On: the section is rendered, and it has left the disclosure.
        self.assertTrue(on["present"])
        self.assertFalse(on["insideOn"])

    def test_the_steer_composer_is_built_once_in_the_chrome(self) -> None:
        """AC-4. One construction path, reused rather than retyped.

        The composer's index is ABOVE the tab list because the issue's solution
        puts the call in `nextProjectCockpit` immediately before
        `nextCockpitTabList()`. AC-4 as drafted says "below", which contradicts
        that sentence; the solution paragraph governs, and the point either
        reading shares -- out of the panel, out of TRIPWIRES -- is asserted too.
        """
        out = self._console()
        shell = str(out["shell"])
        panel = str(out["panel"])

        self.assertEqual(1, shell.count("data-next-steer-form"))
        self.assertEqual(1, shell.count("data-next-steer>"))
        self.assertNotIn("data-next-steer", panel)
        guardrails = shell.index("data-next-guardrails")
        self.assertLess(shell.index("data-next-steer>"), guardrails)
        self.assertLess(shell.index("data-next-steer>"), shell.index('role="tablist"'))
        for attribute in (
            "data-next-steer-form",
            'data-next-draft="steer"',
            "data-next-controls-project=",
            'data-next-focus="steer-draft:',
            'maxlength="500"',
        ):
            with self.subTest(attribute=attribute):
                self.assertIn(attribute, shell)

    def test_the_second_composer_construction_path_is_gone(self) -> None:
        """AC-4's other half: "renders once" is unprovable while a second
        builder stands. `nextProjectControls` has no caller in `web/`."""
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        sources = [path.read_text(encoding="utf-8") for path in sorted(web.glob("*.js"))]
        joined = "\n".join(sources)
        self.assertNotIn("nextProjectControls", joined)
        self.assertEqual(2, joined.count("nextProjectSteer("))

    def test_the_composer_warns_before_the_first_keystroke(self) -> None:
        """AC-5. Today the sentence exists only in the post-submit receipt."""
        out = self.run_fixture(
            """
console.log(JSON.stringify({steer:nextProjectSteer("cargento",{steers:[]})}));
"""
        )
        assert isinstance(out, dict)
        steer = str(out["steer"])

        self.assertIn("Cargento has no write path into a session.", steer)
        self.assertIn("kept in this browser tab", steer)
        self.assertNotIn("next-steer-receipt", steer)
        self.assertIn("Draft a next step — kept in this tab only", steer)
        self.assertNotIn("Tell this project what to do next", steer)
        self.assertIn('class="next-steer-caveat"', steer)

        styles = (
            pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"
        ).read_text(encoding="utf-8")
        rule = re.search(r"\.next-steer-caveat\{([^}]*)\}", styles)
        assert rule is not None
        # `--fs-sentence` was renamed `--fs-body` at the same 15px.
        self.assertIn("var(--fs-body)", rule.group(1))
        self.assertNotIn("var(--fs-label)", rule.group(1))
        self.assertRegex(rule.group(1), r"line-height:|var\(--fs-body\)/")
        self.assertNotIn("var(--mono)", rule.group(1))

    def test_the_setup_disclosure_survives_a_redraw(self) -> None:
        """AC-6. A bare `<details>` snaps shut on every poll."""
        panel = str(self._console()["panel"])

        setup = panel.index(self.CONSOLE_SETUP)
        tag = panel[panel.rindex("<details", 0, setup) : panel.index(">", setup) + 1]
        self.assertIn("data-next-cockpit-disclosure=", tag)
        key = re.search(r'data-next-cockpit-disclosure="([^"]*)"', tag)
        assert key is not None
        self.assertIn("cargento", key.group(1))
        self.assertIn("console-setup", key.group(1))

    def test_the_promoted_submit_uses_the_plain_control_primitive(self) -> None:
        """AC-7, re-measured. Triage wrote this as not-yet-assessable because
        `.next-action` did not exist; DRC-4590 has since defined it, so the
        criterion is assessed against the real primitive rather than a fallback.
        """
        out = self.run_fixture(
            """
console.log(JSON.stringify({steer:nextProjectSteer("cargento",{steers:[]})}));
"""
        )
        assert isinstance(out, dict)
        submit = re.search(r'<button type="submit"[^>]*>', str(out["steer"]))
        assert submit is not None
        self.assertIn('class="next-action"', submit.group(0))
        self.assertNotIn("next-action--primary", submit.group(0))

        styles = (
            pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".next-action{", styles)
        self.assertIn(".next-action--primary{", styles)

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
        # Course carries a derived cue after its label, so the close tag is no
        # longer adjacent; selection, roving tabindex and label still are.
        self.assertIn('aria-selected="true" tabindex="0">Course<span', out["course"])
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

    def test_the_registration_recipe_is_two_steps_behind_a_redraw_safe_disclosure(self) -> None:
        """DRC-4591 AC-1 and AC-2 on the `pc-` surface.

        The recipe rendered as one paragraph of running prose in which both
        flags wrap. It is now a numbered two-step list behind
        `projectDisclosure`, whose open state survives a redraw -- a bare
        `<details>` would snap shut on every live payload, losing the reader's
        place mid-command.
        """
        out = self.run_fixture(
            """
nextRoute=nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1:console");
delete projectTerminalBySession["codex:focus-1"];
__fetchImpl = async () => ({ok:true,status:200,
  json:async()=>({state:"refused",reason:"unregistered-origin"})});
renderNext();
await __settle(); await __settle();
const closed = __els.app.innerHTML;
// Open it the way a click does, then redraw.
projectDisclosureOpenBySession.set("codex:focus-1\\nterminal-registration", true);
renderNext();
await __settle();
console.log(JSON.stringify({closed, reopened: __els.app.innerHTML}));
"""
        )

        assert isinstance(out, dict)
        closed, reopened = out["closed"], out["reopened"]
        assert isinstance(closed, str) and isinstance(reopened, str)
        # AC-1: a closed <details> still contributes its body to innerHTML, so
        # every load-bearing fragment of the recipe is still on the page.
        self.assertIn("How to register a terminal", closed)
        self.assertIn('data-pc-disclosure="terminal-registration"', closed)
        self.assertIn("pc-substrate-steps", closed)
        for fragment in (
            "--interaction-origin-session harness:sid",
            "--interaction-origin-registration-file PATH",
            "inside the tmux pane for this exact session with that file",
            "Output is read-only.",
        ):
            with self.subTest(fragment=fragment[:40]):
                self.assertIn(fragment, closed)
        # Two steps, not one paragraph -- counted inside the list, because the
        # rest of the Console tab carries list items of its own.
        steps = re.search(r'<ol class="pc-substrate-steps">([\s\S]*?)</ol>', closed)
        assert steps is not None, "the recipe did not render as a list"
        self.assertEqual(2, steps.group(1).count("<li>"))
        # AC-2: the open state is the board's own persisted one, and it survives
        # the redraw. Falsified by a bare <details>, which carries no
        # data-pc-disclosure and so is never restored.
        self.assertNotIn(' open data-pc-disclosure="terminal-registration"', closed)
        self.assertIn(' open data-pc-disclosure="terminal-registration"', reopened)

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
        # 48 before the per-tab lede, which is 17 words of deliberate prose
        # naming what the panel holds. Raised by that sentence and no further.
        self.assertLessEqual(out["visibleWords"], 65)
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
        # Two lines, title first. The whole line-1 sequence is pinned, so a
        # change that puts the harness back above the title fails here rather
        # than passing on a looser match.
        self.assertIn(
            '<span class="next-cockpit-scope-mark" aria-hidden="true">'
            '<i class="next-scope-marker next-scope-marker--round"></i></span>'
            '<span class="next-visually-hidden">SESSION</span>'
            '<span class="next-cockpit-scope-title" title="Shape project cockpit">'
            "Shape project cockpit</span>",
            out["sessionNav"],
        )
        self.assertIn(
            '<span class="next-cockpit-scope-meta">Codex \u00b7 '
            '<span class="next-cockpit-scope-state next-cockpit-scope-state--working">'
            '<span class="next-project-dot next-project-tone--unknown next-project-dot--working"'
            ' role="img" aria-label="working"></span>working</span>',
            out["sessionNav"],
        )
        self.assertLess(
            out["sessionNav"].index('class="next-cockpit-scope-title" title="Shape project'),
            out["sessionNav"].index('class="next-cockpit-scope-meta">Codex'),
        )
        self.assertNotIn("<small>Shape project cockpit</small>", out["sessionNav"])

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
        # "All events" is the renderer's own filter button, deliberately
        # re-exposed. What must not leak is the all-events VIEW: the panel is
        # still on decisions and that button is still unpressed.
        self.assertIn('data-graph-mode="decisions"', out["html"])
        self.assertIn("<h2>RECORDED DECISIONS</h2>", out["html"])
        self.assertIn('data-arg="all" class="" aria-pressed="false"', out["html"])

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
        self.assertIn("session output; semantic result not published", out["text"])
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
        self.assertIn("session output; semantic result not published", evidence)

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
class LegacyProjectGraphFilterTest(NextPageJsHarness):
    """DRC-4609. The legacy view's own `Decisions` button selected `Active`.

    `projectSemanticTimeline` builds its filter over all of
    `PROJECT_GRAPH_MODES`, so the legacy view has always rendered three buttons.
    `projectAction` collapsed everything that was not `"all"` to `"active"`, so
    the third mode was unreachable from the surface that offers it and the only
    feedback a reader got was the wrong button lighting up.

    The cockpit's own `graph-mode` arm accepts all three and always has, which
    is why this never showed there. Both now go through `projectSetGraphMode`,
    the one place that validates.
    """

    # The composition fixture by reference rather than by inheritance: a
    # subclass would re-run all 126 of that class's tests for three of its own.
    def run_fixture(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + NextCockpitCompositionTest.FIXTURE,
        )

    def test_pressing_decisions_on_the_legacy_view_selects_decisions(self) -> None:
        out = self.run_fixture(
            """
// Given: the legacy project view, on its default mode.
const before = projectResolveGraphMode({});

// When: the Decisions button of the timeline filter is pressed.
projectAction("project-graph-mode", "decisions");
const after = projectResolveGraphMode({});
const html = projectSemanticTimeline(__dashboard, __semantic, [], null, [],
  {mode: after});
console.log(JSON.stringify({before, after, html}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual("active", out["before"])
        self.assertEqual("decisions", out["after"])
        html = str(out["html"])
        # The mode reaches the rendered timeline, not just the stored value.
        self.assertIn('data-graph-mode="decisions"', html)
        # And the button a reader pressed is the one that lights up. Asserted on
        # the pair rather than on `aria-pressed="true"` alone, which would pass
        # with Active still pressed somewhere else in the same strip.
        self.assertIn('data-arg="decisions" class="selected" aria-pressed="true"', html)
        self.assertIn('data-arg="active" class="" aria-pressed="false"', html)

    def test_an_argument_outside_the_three_modes_changes_nothing_and_redraws_nothing(
        self,
    ) -> None:
        """The falsifier for the fix as well as for the defect.

        A dispatcher that simply passed `arg` through would satisfy the test
        above and substitute silently on anything else. `projectSetGraphMode`
        returns false on a value it will not take, and this asserts the return
        is actually read: a redraw on a press that changed nothing is the same
        wrong answer one step quieter.
        """
        out = self.run_fixture(
            """
// Given: a mode deliberately chosen, and a counter on every redraw.
projectAction("project-graph-mode", "decisions");
let draws = 0;
const __app = __els.app;
__els.app = {get innerHTML(){ return __app.innerHTML; },
  set innerHTML(html){ draws++; __app.innerHTML = html; }};

// When: the dispatcher is handed an argument outside the three modes.
const handled = projectAction("project-graph-mode", "everything");
console.log(JSON.stringify({handled, draws, mode: projectResolveGraphMode({})}));
"""
        )

        assert isinstance(out, dict)
        # Still handled -- the action is ours, the argument is not a mode.
        self.assertTrue(out["handled"])
        self.assertEqual("decisions", out["mode"])
        self.assertEqual(0, out["draws"])

    def test_the_cockpits_own_filter_still_takes_all_three(self) -> None:
        """The third acceptance line: the arm that was already correct stays so."""
        out = self.run_fixture(
            """
// When: each of the three modes is set through the shared guarded setter.
const taken = {};
for(const mode of PROJECT_GRAPH_MODES){
  taken[mode] = projectSetGraphMode(mode) && projectResolveGraphMode({});
}
console.log(JSON.stringify({taken, refused: projectSetGraphMode("decision")}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual({"active": "active", "all": "all", "decisions": "decisions"}, out["taken"])
        self.assertFalse(out["refused"])


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
// Paragraphs, because the absence sentence is one and the input handler hides
// it in place. Parsed with their `hidden` attribute so a test can tell the
// renderer's state from the handler's.
let paras = [];
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
        // Attributes the handler writes land in `attrs`, the same place the
        // parsed ones do, so a test cannot tell a handler's write from the
        // renderer's -- which is the point: a control the renderer drew inert
        // and a control the handler made inert are the same control.
        setAttribute(name, value){ attrs[name] = String(value); },
        removeAttribute(name){ delete attrs[name]; },
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
                if(inner === "[data-next-cockpit-held-absent]"){
                  return paras.find(para => para.dataset.nextCockpitHeldAbsent === kind) || null;
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
    paras = [...html.matchAll(/<p\b([^>]*)>([^<]*)</g)].map(match => {
      const attrs = Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)]
        .map(attr => [attr[1], decode(attr[2])]));
      return {textContent: decode(match[2]), hidden: /(^|\s)hidden(\s|$)/.test(match[1]),
        id: attrs.id || "",
        dataset: Object.fromEntries(Object.entries(attrs)
          .filter(([key]) => key.startsWith("data-")).map(([key, value]) => [camel(key), value]))};
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
    drift: html.includes("data-next-session-drift"),
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
        # A Held to link now opens the session page, whose drift block holds the
        # fields; the strip offers no tab for them (DRC-4639).
        self.assertFalse(session["tab"])
        self.assertTrue(session["drift"])
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

    def test_a_pasted_line_break_collapses_in_the_box_not_silently_at_the_store(self) -> None:
        """DRC-4533's newline item, taken as a product call: the fields are one line.

        `records.safe_text` already collapsed a run of control characters into
        one space before the store saw anything, so a pasted line break was
        gone at the save while the box still showed it and the cue said "Saved
        as a new revision." under text the store never held. The box now shows
        what will be stored.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const before = __els.renders;
const box = controls.find(control => control.dataset.nextCockpitHeldKind === "output");
box.value = "ship it\\n\\nand the doc";
__fire("input", {target:box});
await __settle();
const field = box.closest("[data-next-cockpit-held-field]");
console.log(JSON.stringify({
  box: box.value,
  draft: nextCockpitHeldDrafts.get("held:codex:focus-1:output"),
  count: field.querySelector("[data-next-cockpit-held-count]").textContent,
  redraws: __els.renders - before,
}));
"""
        )
        assert isinstance(out, dict)
        # What the reader sees is what the store will hold: one space, not two
        # newlines. The write-back on the input element is what makes it visible.
        self.assertEqual("ship it and the doc", out["box"])
        self.assertEqual("ship it and the doc", out["draft"])
        # 19 characters, not 20: the count is against the collapsed value, so
        # the box and the store cannot disagree at the cap either.
        self.assertEqual("19/240", out["count"])
        # And it is still the lane that does not redraw on a keystroke.
        self.assertEqual(0, out["redraws"])

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
// The box, because the cue is only honest if the words are where it says.
const keptDraft = nextCockpitHeldDrafts.get("held:codex:focus-1:output");

// And: a run where it can.
persisted = true;
type("output", "Six screenshots again");
await __settle();
save("output");
await __settle();
console.log(JSON.stringify({unwritable, keptDraft, written: cue(),
  clearedDraft: nextCockpitHeldDrafts.has("held:codex:focus-1:output")}));
"""
        )

        # Then
        assert isinstance(out, dict)
        # The wording says what already happened rather than what will. Codex
        # walked this on the re-check: the handler calls `refreshNext()` on
        # the line after the cue, and every collection reloads the store from
        # disk, so the refresh the old sentence warned about had already run
        # by the time the reader could read the warning.
        self.assertEqual(
            "Not stored. The store could not be written, so the refresh has already "
            "dropped these words, and they are still in the box.",
            out["unwritable"],
        )
        self.assertEqual("Six screenshots", out["keptDraft"])
        self.assertEqual("Saved as a new revision.", out["written"])
        self.assertFalse(out["clearedDraft"])

    DISCARD_WITH_REPLY = """
let reply = {ok:true, persisted:true, outcome:"stored", revision:null, revision_count:0};
let posted = [];
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => {
  if(String(url) !== "/api/annotate") return upstream(url, init);
  const body = JSON.parse(String(init && init.body || "{}"));
  posted.push(body);
  /* The board the route leaves behind, and not the one the press started
     from. `annotations.clear` drops the entry and `published` then answers
     `revision_count` 0, so a fixture that kept 2 would hold a state no server
     can produce -- and it is exactly the state the success sentence used to
     be rendered under. */
  if(body.clear === true && reply.outcome === "stored"){
    __dashboard.sessions[0].annotation_revision = null;
    __dashboard.sessions[0].annotation_revision_count = 0;
  }
  return {ok:true, status:200, json: async () => reply};
};
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const discardControl = () => controls.find(control =>
  control.dataset.nextCockpitAction === "held-discard");
const press = () => __fire("click", {target:discardControl(), preventDefault(){}});
/* The reader reading the armed sentence, which is what the second press is
   supposed to follow. The harness clock stands still unless a test moves it,
   so a deliberate second press has to say so; two presses with the clock where
   it was are a double-click, and the control refuses one. */
const dwell = () => __setNow(__nowSec + 2);
const cue = () => (__els.app.innerHTML
  .match(/class="next-cockpit-held-cue">([^<]*)</) || [])[1];
"""

    def test_the_discard_control_appears_only_where_there_is_something_to_discard(self) -> None:
        """DRC-4561. The endpoint's act is per annotation, so the control is too."""
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const withRevisions = __els.app.innerHTML;
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
renderNext();
await __settle();
const without = __els.app.innerHTML;
console.log(JSON.stringify({
  present: (withRevisions.match(/data-next-cockpit-action="held-discard"/g) || []).length,
  label: (withRevisions.match(
    /data-next-cockpit-action="held-discard"[^>]*>([^<]*)</) || [])[1],
  why: withRevisions.includes("Discarding everything is the other act."),
  clearLabel: (withRevisions.match(
    /data-next-cockpit-action="held-clear"[^>]*>([^<]*)</) || [])[1],
  absent: (without.match(/data-next-cockpit-action="held-discard"/g) || []).length,
}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(1, out["present"])
        self.assertEqual("discard everything", out["label"])
        self.assertTrue(out["why"])
        # And the per-field control keeps its own name, which is the half of
        # this the design draws and the half that already shipped.
        self.assertEqual("clear", out["clearLabel"])
        self.assertEqual(0, out["absent"])

    def test_the_first_press_writes_nothing_and_the_second_one_discards(self) -> None:
        """DRC-4561. Arm then confirm, on the one control and with no dialog.

        The bundle has never had a confirmation dialog and this must not be the
        first; the same block already ships a deliberate two-step for the
        weaker act.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + f"const __armedSentence = {json.dumps(annotation_store.DISCARD_ARMED)};\n"
            + self.DISCARD_WITH_REPLY
            + """
press();
await __settle();
const armed = {posts: posted.length, html: __els.app.innerHTML,
  label: (__els.app.innerHTML.match(
    /data-next-cockpit-action="held-discard"[^>]*>([^<]*)</) || [])[1]};
dwell();
press();
await __settle();
console.log(JSON.stringify({armed: {posts: armed.posts, label: armed.label,
  says: armed.html.includes("Press it again to discard."),
  scope: armed.html.includes(__armedSentence),
  withdrawal: armed.html.includes("will quote them any more")},
  posts: posted, cue: cue()}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(0, out["armed"]["posts"])
        self.assertNotEqual("discard everything", out["armed"]["label"])
        self.assertTrue(out["armed"]["says"])
        # What the confirmation says before the act, and not only that there is
        # one. SKILL.md tells a reader the board names what it will delete and
        # what it will withdraw between the presses; nothing but this held that
        # sentence to being true. Both halves: the published sentence is what
        # renders, and the withdrawal is named in it.
        self.assertTrue(out["armed"]["scope"])
        self.assertTrue(out["armed"]["withdrawal"])
        self.assertEqual([{"harness": "codex", "sid": "focus-1", "clear": True}], out["posts"])
        self.assertEqual(annotation_store.DISCARD_STORED, out["cue"])

    def test_one_gesture_cannot_arm_and_confirm(self) -> None:
        """The commonest slip on a button is the one that deletes the records.

        The listener is delegated on `document` and `renderNext` is
        synchronous, so the replacement button carries the same action at the
        same coordinates before the second click of a double-click is
        dispatched: two presses with nothing read between them discarded every
        revision, the stored reading and the quotations. Key-repeat on a
        focused button is the same sequence.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + self.DISCARD_WITH_REPLY
            + """
// No settle and no dwell between them: this is one double-click.
press();
press();
await __settle();
const gesture = {posts: posted.length, armed: nextCockpitHeldStates.has(
  "held:codex:focus-1:discard"), cue: cue() || null};
// And the control is not dead — it confirms once the reader has had time to
// read what the second press does.
dwell();
press();
await __settle();
console.log(JSON.stringify({gesture, posts: posted.length, cue: cue()}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(0, out["gesture"]["posts"])
        self.assertIsNone(out["gesture"]["cue"])
        # Still armed rather than disarmed: a slip must not silently undo the
        # deliberate press that preceded it.
        self.assertIs(True, out["gesture"]["armed"])
        self.assertEqual(1, out["posts"])
        self.assertEqual(annotation_store.DISCARD_STORED, out["cue"])

    def test_the_sentence_after_the_act_survives_the_state_the_act_leaves(self) -> None:
        """DRC-4561. The block is gated on there being something to discard.

        A landed discard deletes the entry, so the next payload publishes
        `revision_count` 0 and the gate closes over the very sentence that says
        what just happened. The offer goes with the entry; the account of what
        became of it does not.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + self.DISCARD_WITH_REPLY
            + """
press();
await __settle();
dwell();
press();
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({cue: cue(), count: __dashboard.sessions[0].annotation_revision_count,
  offers: (html.match(/data-next-cockpit-action="held-discard"/g) || []).length,
  why: html.includes("Discarding everything is the other act.")}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(0, out["count"])
        self.assertEqual(annotation_store.DISCARD_STORED, out["cue"])
        self.assertEqual(0, out["offers"])
        self.assertFalse(out["why"])

    def test_a_discard_the_departure_store_outlived_does_not_claim_otherwise(self) -> None:
        """DRC-4561. The one thing the categorical sentence cannot promise.

        `departures.withdraw` answers False on a store it could not write, and
        the annotation is gone by then either way. The reply carries that
        second answer so the board can say the quotations stayed rather than
        redrawing them under a sentence saying nothing quotes those words.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + self.DISCARD_WITH_REPLY
            + """
reply = {ok:true, persisted:true, outcome:"stored", revision:null, revision_count:0,
  withdrew:false};
press();
await __settle();
dwell();
press();
await __settle();
console.log(JSON.stringify({cue: cue(),
  drafts: nextCockpitHeldDrafts.has("held:codex:focus-1:goal")}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(annotation_store.DISCARD_UNWITHDRAWN, out["cue"])
        # The annotation went, so its drafts go with it: this is a landed
        # discard that only half reached the other store.
        self.assertFalse(out["drafts"])

    def test_a_reply_without_the_withdrawal_answer_keeps_the_sentence_it_had(self) -> None:
        """A server older than this page omits the field, and absent is not False."""
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + self.DISCARD_WITH_REPLY
            + """
press();
await __settle();
dwell();
press();
await __settle();
console.log(JSON.stringify({cue: cue()}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(annotation_store.DISCARD_STORED, out["cue"])

    def test_a_discard_that_did_not_land_says_the_words_and_the_raises_stand(self) -> None:
        """Neither failure may wear a save cue: there is no box and no draft."""
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + self.DISCARD_WITH_REPLY
            + """
reply = {ok:true, persisted:false, outcome:"refused", revision:null, revision_count:0};
press();
await __settle();
dwell();
press();
await __settle();
const refused = cue();
reply = {ok:true, persisted:false, outcome:"unwritable", revision:null, revision_count:0};
dwell();
press();
await __settle();
dwell();
press();
await __settle();
console.log(JSON.stringify({refused, unwritable: cue()}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(annotation_store.DISCARD_REFUSED, out["refused"])
        self.assertEqual(annotation_store.DISCARD_UNWRITABLE, out["unwritable"])

    def test_escape_on_the_armed_control_disarms_it_rather_than_navigating(self) -> None:
        """The hazard the arm introduces, fixed in the same change.

        `next-chrome.js` excuses only input, select and textarea from its
        Escape handler, so Escape on a focused button navigated the reader out
        of the cockpit with the arm still stamped in a Map that outlives the
        navigation.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + self.DISCARD_WITH_REPLY
            + """
press();
await __settle();
const target = discardControl();
__fire("keydown", {key:"Escape", target, preventDefault(){}});
await __settle();
console.log(JSON.stringify({view: nextRoute.view, tab: nextRoute.tab,
  armed: nextCockpitHeldStates.has("held:codex:focus-1:discard"),
  label: (__els.app.innerHTML.match(
    /data-next-cockpit-action="held-discard"[^>]*>([^<]*)</) || [])[1],
  posts: posted.length}));
"""
        )

        assert isinstance(out, dict)
        # Still on the page it was pressed on, which is the session page since
        # Held to merged into it (DRC-4639).
        self.assertEqual("session", out["view"])
        self.assertIsNone(out.get("tab"))
        self.assertFalse(out["armed"])
        self.assertEqual("discard everything", out["label"])
        self.assertEqual(0, out["posts"])

    def test_pressing_clear_empties_the_draft_and_offers_the_save(self) -> None:
        """The untested half of the shipped `clear`: nothing pressed it.

        It is what the walk measured — the box empties, the save after it
        writes an empty revision, and everything raised against the old words
        keeps quoting them. Pinned so the two acts cannot quietly converge.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
__fire("click", {target:controls.find(control =>
  control.dataset.nextCockpitAction === "held-clear" && control.dataset.arg === "goal"),
  preventDefault(){}});
await __settle();
console.log(JSON.stringify({
  draft: nextCockpitHeldDrafts.get("held:codex:focus-1:goal"),
  saves: (__els.app.innerHTML.match(
    /data-next-cockpit-action="held-save" data-arg="goal">/g) || []).length,
}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual("", out["draft"])
        self.assertEqual(1, out["saves"])

    SAVE_WITH_REPLY = """
let reply = {ok:true, persisted:true, outcome:"stored", revision:2, revision_count:2};
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => String(url) === "/api/annotate"
  ? {ok:true, status:200, json: async () => reply}
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
"""

    def test_an_unchanged_save_does_not_claim_a_new_revision(self) -> None:
        """DRC-4543. The store mints nothing for a repeat of the last revision.

        The reply carried `persisted:true` with `revision_count` unchanged, and
        the page read the bit alone, so it said "Saved as a new revision."
        over a save that had minted none. Reached from a second dashboard's
        save between this one's render and press, or a scripted POST, which
        is why the reply is stubbed here as the cue tests beside it do.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + self.SAVE_WITH_REPLY
            + """
reply = {ok:true, persisted:true, outcome:"unchanged", revision:2, revision_count:2};
type("output", "Six screenshots");
await __settle();
save("output");
await __settle();
console.log(JSON.stringify({cue: cue(),
  kept: nextCockpitHeldDrafts.has("held:codex:focus-1:output")}));
"""
        )
        assert isinstance(out, dict)
        self.assertNotEqual("Saved as a new revision.", out["cue"])
        self.assertEqual(
            "Already stored. These words match the saved revision, so no new revision was minted.",
            out["cue"],
        )
        # The words are on disk, so the draft has nothing left to protect.
        self.assertFalse(out["kept"])

    def test_a_refused_save_wears_the_refusal_sentence_not_the_lost_write_one(self) -> None:
        """DRC-4543. A refusal is not a failed write.

        Forced live on 2026-09-12: a save the store refused rendered "Not
        stored. The store could not be written..." while the store's mtime did
        not move. Nothing was written and nothing was lost; the sentence was
        false on both counts. The refusal sentence already exists for the
        HTTP refusals and is as true of a store refusal.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + self.SAVE_WITH_REPLY
            + """
reply = {ok:true, persisted:false, outcome:"refused", revision:2, revision_count:2};
type("output", "Six screenshots");
await __settle();
save("output");
await __settle();
console.log(JSON.stringify({cue: cue(),
  draft: nextCockpitHeldDrafts.get("held:codex:focus-1:output") || null}));
"""
        )
        assert isinstance(out, dict)
        # The whole sentence, because both cues end "still in the box" and a
        # substring test could not tell them apart.
        self.assertEqual(
            "Not saved. The server refused the write, and your words are still in the box.",
            out["cue"],
        )
        self.assertEqual("Six screenshots", out["draft"])

    def test_the_two_landing_outcomes_are_read_from_the_token_not_the_bit(self) -> None:
        """DRC-4543 review T2. Two rows of the token map were bound by nothing.

        The `persisted` fallback beside the lookup answers `stored` and
        `unwritable` the same way the map does, so a wrong sentence on either
        of them shipped green: mutating `stored` to the unwritable cue made a
        successful save claim a lost write and keep the draft, and the module
        stayed OK. Every other cue test here stubs a reply with no `outcome`
        at all, which is the fallback and not the map. These two carry the
        token.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + self.SAVE_WITH_REPLY
            + """
reply = {ok:true, persisted:true, outcome:"stored", revision:2, revision_count:2};
type("output", "Six screenshots");
await __settle();
save("output");
await __settle();
const stored = {cue: cue(),
  kept: nextCockpitHeldDrafts.has("held:codex:focus-1:output")};

reply = {ok:true, persisted:false, outcome:"unwritable", revision:2, revision_count:2};
type("output", "Six screenshots and a log");
await __settle();
save("output");
await __settle();
console.log(JSON.stringify({stored, unwritable: {cue: cue(),
  draft: nextCockpitHeldDrafts.get("held:codex:focus-1:output") || null}}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual("Saved as a new revision.", out["stored"]["cue"])
        # The words are on disk, so the draft has nothing left to protect.
        self.assertFalse(out["stored"]["kept"])
        self.assertEqual(
            "Not stored. The store could not be written, so the refresh has already "
            "dropped these words, and they are still in the box.",
            out["unwritable"]["cue"],
        )
        self.assertEqual("Six screenshots and a log", out["unwritable"]["draft"])

    def test_the_saved_cue_expires_and_the_map_stays_bounded(self) -> None:
        # Finding R. The cue was unstamped, so it survived every redraw and a
        # navigation away and back: a reader returning hours later read
        # "Saved as a new revision." as though they had just pressed it.
        out = self.run_fixture(
            self.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const key = "held:codex:focus-1:goal";
const cue = () => (__els.app.innerHTML
  .match(/class="next-cockpit-held-cue">([^<]*)</) || [])[1];

nextCockpitHeldMark(key, "saved");
renderNext();
const fresh = cue();

// Wind the stamp back past the window the row controls next door use.
const held = nextCockpitHeldStates.get(key);
nextCockpitHeldStates.set(key, {kind: held.kind, at: held.at - NEXT_CONTROL_STATE_TTL_MS - 1});
renderNext();
const stale = cue();

// And the map is bounded, like every other module-level map here.
for(let n = 0; n < 40; n++) nextCockpitHeldMark(`held:codex:focus-1:k${n}`, "saved");
console.log(JSON.stringify({fresh, stale: stale === undefined ? null : stale,
  size: nextCockpitHeldStates.size, ttl: NEXT_CONTROL_STATE_TTL_MS}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual("Saved as a new revision.", out["fresh"])
        self.assertIsNone(out["stale"])
        self.assertEqual(30_000, out["ttl"])
        self.assertLessEqual(out["size"], 16)

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
        # The reader's words carry their own time now, so the typed row and
        # the derived row beside it can be put in order.
        self.assertRegex(out["within"]["header"], r"^revision 2 of 2 \u00b7 typed \d+[smhd]")
        self.assertRegex(
            out["past"]["header"],
            r"^revision 20, 16 kept \u00b7 typed \d+[smhd].* \u00b7 older revisions dropped$",
        )
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
  // Rendered and hidden, not omitted: a keystroke does not redraw, so the
  // paragraph has to be an element the input handler can reach.
  typedHidesReason: /<p class="next-cockpit-held-absent" [^>]*data-next-cockpit-held-absent="goal" hidden>/
    .test(__els.app.innerHTML),
  typedShowsOtherReason: /data-next-cockpit-held-absent="output">No expected output typed\\./
    .test(__els.app.innerHTML),
}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertTrue(out["emptyShowsReason"])
        self.assertFalse(out["emptyShowsBinding"])
        self.assertTrue(out["typedHidesReason"])
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

/* And: it came back, but the scan that produces these facts did not reach
   this session. That is `sources.work.omitted`, which names the sessions
   `_analysis_context_sessions` bounded out at MAX_PROJECT_OBSERVERS.

   It is NOT `command_attention_coverage`, which this test set and the block
   read for one round of the review: that is a separate sweep over active
   sessions' final output, bounded at 64 rather than 3, so the state resolved
   to "empty" for exactly the sessions the sentence was written for. Codex
   caught it on the verification round by omitting three real sessions and
   watching the board still say the record named nothing. */
nextCockpitContexts.clear();
for(const [key, entry] of contexts){
  const data = JSON.parse(JSON.stringify(entry.data));
  data.sources = {observer:{live:3}, work:{omitted:[
    {harness:"claude", sid:"claude-idle"}, {harness:"pi", sid:"pi-idle"}]}};
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
// A real payload stamps `actor_claim` on every fact, and on most types it IS
// the evidence source. Measured on a live board: every `user_message` carried
// actor_claim === evidence.source, and appending it printed the clause twice.
for(const fact of __semantic.facts){
  fact.actor_claim = (fact.evidence || {}).source || "";
}
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
  // A claim the source line already carries is not repeated beside it.
  sources: [...html.matchAll(/class="next-cockpit-work-source">([^<]*)</g)].map(m => m[1]),
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
        for line in out["sources"]:
            with self.subTest(source=line):
                halves = line.split(" · ")
                self.assertEqual(len(halves), len(set(halves)), "a repeated clause")
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

    def test_a_reading_press_shows_progress_and_survives_redraws(self) -> None:
        out = self.run_fixture(r"""
__dashboard.reading_check = "accepted";
__dashboard.annotate = true;
const session = __dashboard.sessions[0];
// The gate reads the published annotation, which is where the renderer
// gets its copy too, so the fixture has to carry the same words as the
// literal below rather than only the literal.
session.annotation_goal = "ship it";
const annotation = {goal:"ship it", reading_count:0};
const control = () => nextCockpitReadingControl(session, annotation, {enabled:true});
const releases = [];
let calls = 0;
const upstream = __fetchImpl;
__fetchImpl = (url, init) => String(url) === "/api/reading"
  ? (calls++, new Promise(resolve => { releases.push(resolve); })) : upstream(url, init);
const pending = nextCockpitAskForReading(session, {enabled:true});
await __settle();
renderNext();
const during = control();
const duplicate = nextCockpitAskForReading(session, {enabled:true});
const other = nextCockpitReadingControl(__dashboard.sessions[1], annotation, {enabled:true});
for(const release of releases) release({ok:true, json:async()=>({ok:true, produced:true, reason:""})});
await Promise.all([pending, duplicate]);
console.log(JSON.stringify({during, other, after:control(), calls}));
""")
        assert isinstance(out, dict)
        self.assertIn("Checking for drift", out["during"])
        self.assertIn("0 model requests recorded", out["during"])
        self.assertRegex(out["during"], r'reading-ask"[^>]*disabled')
        self.assertNotIn("Checking for drift", out["other"])
        self.assertEqual(1, out["calls"])
        self.assertIn("Reading received", out["after"])
        self.assertNotRegex(out["after"], r'reading-ask"[^>]*disabled')

    def test_a_reading_press_reports_refusal_and_failure_without_retrying(self) -> None:
        out = self.run_fixture(r"""
__dashboard.reading_check = "accepted";
__dashboard.annotate = true;
const session = __dashboard.sessions[0];
session.annotation_goal = "ship it";
const annotation = {goal:"ship it", reading_count:0, reading_withheld:"No end was observed."};
const upstream = __fetchImpl;
const outcomes = [];
let calls = 0;
for(const reply of [
  {ok:true, json:async()=>({ok:true, produced:false, reason:"turn-stop"})},
  {ok:false, status:409}, {ok:false, status:503},
  {ok:true, json:async()=>({ok:false})}, null
]){
  __fetchImpl = async (url, init) => {
    if(String(url) !== "/api/reading") return upstream(url, init);
    calls++;
    if(reply === null) throw new Error("network down");
    return reply;
  };
  await nextCockpitAskForReading(session, {enabled:true});
  renderNext();
  outcomes.push(nextCockpitReadingControl(session, annotation, {enabled:true}));
}
console.log(JSON.stringify({outcomes,calls}));
""")
        assert isinstance(out, dict)
        self.assertEqual(5, out["calls"])
        self.assertIn("No new reading was produced", out["outcomes"][0])
        self.assertIn("already in progress", out["outcomes"][1])
        for html in out["outcomes"][2:]:
            self.assertIn("Could not confirm the reading", html)
            self.assertIn("not been retried", html)
        for html in out["outcomes"]:
            self.assertNotIn("No reading has been asked for", html)
            self.assertIn('role="status"', html)

    def test_a_retained_reading_never_offers_a_new_one_while_the_model_is_unavailable(self) -> None:
        out = self.run_fixture(
            """
__dashboard.annotate = true;
__dashboard.reading_check = "accepted";
Object.assign(__dashboard.sessions[0], {
  annotation_goal:"do not change the board", annotation_output:"",
  annotation_revision:1, annotation_revision_count:1, annotation_at:100,
  annotation_assessment:{revision_read:1, scope:"mid-flight",
    scope_text:"This covers only the work so far.",
    criteria:{goal:{result:"consistent with the evidence read", detail:"", cites:["fo-a"]}}}
});
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const group = nextProjectGroups().find(g => g.label === "cargento");
const key = nextCockpitContextKey(group, nextCockpitFocusedSession(group));
const entry = nextCockpitContexts.get(key);
const states = [null, {consent:true,reason:"run-disabled"}, {consent:true,reason:""}].map(policy => {
  __dashboard.reading = policy;
  renderNext();
  const html = __els.app.innerHTML;
  return {
    retained:html.includes("This covers only the work so far."),
    disabled:/data-next-cockpit-action="reading-ask"[^>]*disabled/.test(html),
    unread:html.includes("Reading availability has not been read"),
    off:html.includes("Model calls are off for this run"),
  };
});
console.log(JSON.stringify(states));
"""
        )
        assert isinstance(out, list)
        self.assertTrue(all(state["retained"] for state in out))
        self.assertEqual([True, True, False], [state["disabled"] for state in out])
        self.assertTrue(out[0]["unread"])
        self.assertTrue(out[1]["off"])

    def test_the_reading_has_three_states_and_the_control_waits_on_a_check(self) -> None:
        """DRC-4511. Nothing typed, the model off, and the offer itself."""
        out = self.run_fixture(
            """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.reading_check = "not-run";
const read = () => {
  const html = __els.app.innerHTML;
  const block = html.slice(html.indexOf('class="next-session-drift-check"'));
  const reading = html.slice(html.indexOf('class="next-cockpit-reading"'));
  return {
    text: (reading.match(/class="next-cockpit-reading-why"[^>]*>([^<]*)</) || [])[1],
    // The refusal by its id rather than by being first. The offer paragraph
    // now precedes it in every state, because the control renders in all of
    // them, and "the first reason paragraph" stopped naming the reason.
    reason: (block.match(
      /class="next-cockpit-reading-why" id="next-cockpit-reading-refused"[^>]*>([^<]*)</
      ) || [])[1],
    control: block.includes('data-next-cockpit-action="reading-ask"'),
    disabled: /data-next-cockpit-action="reading-ask"[^>]*aria-disabled="true"/.test(block),
    // The bare attribute the browser acts on, kept apart from the aria one:
    // a single check for "disabled" matches both spellings and so cannot
    // witness which of the two shipped.
    bare: /data-next-cockpit-action="reading-ask"[^>]*\\sdisabled[=>\\s]/.test(block),
    departures: html.includes("DEPARTURES RAISED TO YOU"),
    said: block.includes("never a verification that the work was done"),
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

// And: words typed, with reading permission unread.
__dashboard.reading = null;
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

// And: reading permission available, which is the offer.
__dashboard.reading = {consent:true,reason:""};
const key = nextCockpitContextKey(nextProjectGroups().find(g => g.label === "cargento"),
  nextCockpitFocusedSession(nextProjectGroups().find(g => g.label === "cargento")));
const entry = nextCockpitContexts.get(key);
entry.data = Object.assign({}, entry.data, {observer_model:{enabled:true, disclosure:"x"}});
renderNext();
const offered = read();

// A scored pass or the captain's accepted case review enables it.
__dashboard.reading_check = "passed";
renderNext();
const enabled = read();
__dashboard.reading_check = "accepted";
renderNext();
const accepted = read();
__dashboard.reading_check = "unknown";
renderNext();
const unknown = read();
console.log(JSON.stringify({empty, unread, offered, enabled, accepted, unknown}));
"""
        )

        # Then
        assert isinstance(out, dict)
        self.assertEqual(
            "Nothing has been typed for this session, so there is nothing to read it against. "
            "Save a goal above to check for drift.",
            out["empty"]["reason"],
        )
        # The control renders in every reason state now, inert and carrying
        # the sentence that says why (DRC-4588). It used to be deleted here,
        # which took the tab's only verb off the page in the two states a
        # newcomer is most likely to arrive in.
        self.assertTrue(out["empty"]["control"])
        self.assertTrue(out["empty"]["disabled"])
        self.assertIn("Reading availability has not been read", out["unread"]["reason"])
        self.assertTrue(out["unread"]["control"])
        self.assertTrue(out["unread"]["disabled"])
        # The offer states what a reading may and may not read. That it is
        # never a verification is said once, by the route's disclosure beside
        # the control (DRC-4650), rather than again in the offer.
        self.assertIn("account of the evidence on this page", out["offered"]["text"])
        self.assertTrue(out["offered"]["said"])
        self.assertTrue(out["offered"]["control"])
        self.assertTrue(out["offered"]["disabled"])
        # Enablement reads the recorded result, not a constant.
        self.assertTrue(out["enabled"]["control"])
        self.assertFalse(out["enabled"]["disabled"])
        self.assertTrue(out["accepted"]["control"])
        self.assertFalse(out["accepted"]["disabled"])
        self.assertTrue(out["unknown"]["disabled"])
        # No reading, the unasked lane off and nothing on record: no departures
        # section at all, which is the DRC-4543 ruling restored on the session
        # page. A panel about a check nobody turned on is noise.
        self.assertFalse(out["offered"]["departures"])
        self.assertFalse(out["empty"]["departures"])
        # And no state uses the bare attribute, in either direction: it would
        # take the control out of the tab order and silence the description
        # that carries the reason.
        for state in ("empty", "unread", "offered", "enabled", "accepted", "unknown"):
            with self.subTest(state=state):
                self.assertFalse(out[state]["bare"])

    def test_the_block_names_the_session_its_words_are_bound_to(self) -> None:
        # Two sessions publishing one title are indistinguishable in the scope
        # rail, and this block said nothing about which of them it was binding
        # to. The harness and session id are what the store keys on.
        out = self.run_fixture(
            self.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
console.log(JSON.stringify({bound: (__els.app.innerHTML
  .match(/class="next-cockpit-held-bound">([^<]*)</) || [])[1]}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual("codex:focus-1", out["bound"])

    def test_how_it_landed_draws_the_two_axes_the_derivation_computes(self) -> None:
        """Finding E, raised by all three harnesses.

        Journey step 3 turns on whether Cargento has evidence the session
        ended. `nextObservedLanding` derived it and nothing consumed it, so a
        reader in this tab could not see whether it did.
        """
        out = self.run_fixture(
            self.ANNOTATED
            + r"""
const read = () => {
  const html = __els.app.innerHTML;
  const block = html.slice(html.indexOf('class="next-cockpit-landed"'));
  return {
    cards: [...block.matchAll(/landed-label">([^<]*)<\/span><span class="([^"]*)">([^<]*)</g)]
      .map(m => [m[1], m[3], m[2].includes("--absent")]),
    note: (block.match(/class="next-cockpit-landed-note">([^<]*)</) || [])[1],
    // DRC-4591 deleted the duplicate aside. What survives is the single
    // footer, which is what the claim was always for.
    axes: block.includes("Neither card implies the other."),
    duplicate: block.includes("two axes, read separately"),
    provisional: html.includes("This covers only the work so far"),
  };
};

// Given: a session still running.
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const running = read();

// And: the same session, observed to have ended with uncommitted work.
__dashboard.sessions[0].ended_at = 104;
__dashboard.sessions[0].dirty = true;
__dashboard.sessions[0].changed = 3;
renderNext();
console.log(JSON.stringify({running, ended: read()}));
"""
        )

        # Then: two cards, never one verdict, and the end axis moves with the
        # evidence while the claim axis does not follow it.
        assert isinstance(out, dict)
        self.assertTrue(out["running"]["axes"])
        self.assertFalse(out["running"]["duplicate"])
        self.assertEqual(
            [
                ["END EVIDENCE", "No stop or end observed while the session is running", True],
                ["WHO CLAIMS IT FINISHED", "Nothing has claimed this session finished", True],
            ],
            out["running"]["cards"],
        )
        self.assertEqual(
            [
                ["END EVIDENCE", "A session end was observed", False],
                ["WHO CLAIMS IT FINISHED", "The agent reported it finished", False],
            ],
            out["ended"]["cards"],
        )
        # The independent-evidence limit rides with the claim card.
        self.assertIn("3 changed entries were observed", out["ended"]["note"])

    def test_a_reading_before_the_end_says_what_it_covers(self) -> None:
        # Journey step 3: "If it offers one earlier at your request, it says
        # that this covers only the work so far." Nothing said it, anywhere.
        out = self.run_fixture(
            """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "do not change the board";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";
__dashboard.sessions[0].annotation_assessment = {revision_read:1,
  scope:"mid-flight",
  scope_text:"This covers only the work so far. The session is still running, so nothing " +
    "here is a reading of how it ended.",
  criteria:{goal:{result:"departure", detail:"It drifted.", cites:["fo-a"]}}};
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const running = __els.app.innerHTML.includes("This covers only the work so far");
__dashboard.sessions[0].ended_at = 104;
renderNext();
console.log(JSON.stringify({running, ended:
  __els.app.innerHTML.includes("This covers only the work so far")}));
"""
        )

        # Then: said while it runs, and STILL said once the session ends,
        # because the sentence is the reading's own and a reading describes
        # the moment it was taken. Keying it on the live row meant a stored
        # mid-flight reading silently started claiming to cover an ending it
        # never saw, the instant the session stopped.
        assert isinstance(out, dict)
        self.assertTrue(out["running"])
        self.assertTrue(out["ended"])

    def test_the_reading_shows_the_words_it_actually_read(self) -> None:
        """DRC-4512. Naming the revision is not showing what it said.

        The amber line says a reading is historical. It does not let the reader
        see WHAT it read, and a reading of revision 1 rendered beside today's
        revision 3 invites the reader to assume the words are the ones on
        screen. The text was always on the wire as the criterion's clause; what
        was missing was somewhere to read it and when it was typed.
        """
        out = self.run_fixture(
            """
const session = {harness:"codex", sid:"focus-1", state:"idle", ended_at:200};
const model = {enabled:true};
const entries = [{id:"u1", type:"user_message", by:"person", source:"root transcript"}];
const annotation = {goal:"the goal as it stands now", output:"", revision:3,
  revision_count:3, at:300, reading_count:1,
  assessment:{revision_read:1, revision_read_at:100, stamp:"a-model - read at 10:00",
    cutoff:"", scope:"final", scope_text:"",
    ended_at_read:200,
    criteria:{
      goal:{result:"consistent with the evidence read", cites:[], detail:"",
        clause:"the goal as it was when the reading ran"},
      output:{result:"not verifiable from available evidence", cites:[], detail:"", clause:""}}}};
const html = nextCockpitReading(session, annotation, entries, model, null, false,
  {state:"read", entries:entries});
console.log(JSON.stringify({
  html,
  // The words the reading actually read, verbatim.
  showsRead: html.includes("the goal as it was when the reading ran"),
  // Still names the revision, because the disclosure does not replace the line.
  stale: html.includes("This reading read revision 1"),
  // And says when that revision was typed, which is the one datum that was
  // genuinely absent from the payload.
  // The rendered duration, not the word "typed": that word appears in both
  // branches of the summary and in the clause-absent sentence, so asserting
  // it could not fail. A mutation of revision_read_at survived the whole
  // suite before this.
  // The fixture clock is 105 and the revision was typed at 100, so this is
  // five seconds and it is deterministic.
  typedAt: html.includes("typed 5s ago"),
  // A disclosure rather than always-open prose: the reading block is already
  // long and this is reference, not the reading.
  disclosure: (html.match(/<details/g) || []).length,
}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["showsRead"], out["html"])
        self.assertTrue(out["stale"])
        self.assertTrue(out["typedAt"])
        self.assertGreaterEqual(out["disclosure"], 1)

    def test_a_reading_with_no_typed_at_states_the_absence(self) -> None:
        """A reading stored before `revision_read_at` existed reads back None.

        The absence states its reason rather than blanking, which is the rule
        every other field on this surface follows.
        """
        out = self.run_fixture(
            """
const session = {harness:"codex", sid:"focus-1", state:"idle", ended_at:200};
const model = {enabled:true};
const entries = [{id:"u1", type:"user_message", by:"person", source:"root transcript"}];
const annotation = {goal:"now", output:"", revision:2, revision_count:2, at:300,
  reading_count:1,
  assessment:{revision_read:1, revision_read_at:null, stamp:"a-model - read at 10:00",
    cutoff:"", scope:"final", scope_text:"", ended_at_read:200,
    criteria:{
      goal:{result:"consistent with the evidence read", cites:[], detail:"", clause:"then"},
      output:{result:"not verifiable from available evidence", cites:[], detail:"", clause:""}}}};
const html = nextCockpitReading(session, annotation, entries, model, null, false,
  {state:"read", entries:entries});
console.log(JSON.stringify({html, saysWhen: html.includes("when it was typed was not recorded")}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["saysWhen"], out["html"])

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
// Settled, so the baseline block is closed and this test measures the stale
// line rather than the suppression. Without it the fixture's own user_message
// facts at 102 and 104 are later directions against an annotation stamped 100,
// and the departure is correctly demoted - which is a different test's job.
__dashboard.sessions[0].annotation_settled_at = 300;
__dashboard.sessions[0].annotation_settled_through = 300;
__dashboard.sessions[0].annotation_settled_revision = 2;
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

        # Then: a bookmarked Held to link still parses, onto the session page,
        # and it carries the reason instead of a field whose every save would
        # answer 503.
        assert isinstance(out, dict)
        self.assertFalse(out["tab"])
        self.assertEqual(0, out["inputs"])
        self.assertTrue(out["reason"])

    def test_both_absence_explanations_read_as_sentences_not_header_labels(self) -> None:
        """DRC-4587 AC-2. `docs/design-next-ui.md` already rules that an absence
        explanation is a sentence and loses to the sentence floor; both of these
        were drawn at 10px mono inside an `<h2>`'s own `<header>`, where no size
        change alone can reach them.
        """
        out = self.run_fixture(
            self.ANNOTATED
            + r"""
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
const headers = [...html.matchAll(/<header>([\s\S]*?)<\/header>/g)].map(m => m[1]).join("|");
console.log(JSON.stringify({
  revisionInHeader: headers.includes("next-cockpit-held-revision"),
  revisionPresent: html.includes('class="next-cockpit-held-revision"'),
  // DRC-4591 deleted the aside this rule was written for. Its surviving half
  // is the footer under the cards, which is a `reading-why` and is measured
  // by that selector's own rule below.
  axesPresent: html.includes('class="next-cockpit-landed-axes"'),
  landedFooter: html.includes(
    '<p class="next-cockpit-reading-why">Neither card implies the other.'),
}));
"""
        )

        # Then: both still render, and neither is a child of a `<header>` any
        # more, so each can carry the sentence tier without dragging its `<h2>`
        # label with it.
        assert isinstance(out, dict)
        self.assertTrue(out["revisionPresent"])
        self.assertFalse(out["revisionInHeader"])
        self.assertFalse(out["axesPresent"])
        self.assertTrue(out["landedFooter"])

        # And the register they are drawn in is the sentence one, not a label
        # bumped to 15px while keeping mono -- the falsifier AC-2 names.
        styles = (
            pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"
        ).read_text(encoding="utf-8")
        for cls in ("next-cockpit-held-revision", "next-cockpit-reading-why"):
            with self.subTest(rule=cls):
                rule = next(line for line in styles.split("\n") if line.startswith("." + cls + "{"))
                self.assertIn("var(--sans)", rule)
                # `--fs-sentence` was renamed `--fs-body` at the same 15px; the
                # tier being asserted is the one a sentence is drawn in, and the
                # label tier below it is `--fs-label`.
                self.assertIn("var(--fs-body)", rule)
                self.assertNotIn("var(--fs-label)", rule)
                self.assertNotIn("var(--mono)", rule)

    # ---- DRC-4588 --------------------------------------------------------
    # The tab's three-step chain loses its third control in exactly the state
    # a newcomer lands in, and the fix that makes the control reachable is the
    # one that lets a press through: `aria-disabled` restores the click the
    # browser's `disabled` was suppressing, so the handler gates below ship
    # with the attribute rather than after it.
    UNTOUCHED = """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.reading_check = "accepted";
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_goal_why = "No goal typed for this session.";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "No expected output typed.";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
__dashboard.sessions[0].annotation_at = null;
__dashboard.sessions[0].annotation_binding_why = "";
"""

    # The reading block as the page actually assembles it, so a test cannot
    # pass against the control called directly while the caller still returns
    # before reaching it.
    READ_BLOCK = r"""
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const block = (__els.app.innerHTML.match(
  /<div class="next-session-drift-check">[\s\S]*?<section class="next-cockpit-reading">[\s\S]*?<\/section>/) || [""])[0];
"""

    NOTHING_TYPED = (
        "Nothing has been typed for this session, so there is nothing to read it against."
    )

    def test_an_untouched_session_is_still_offered_the_tab_s_only_verb(self) -> None:
        """DRC-4588 AC-1. One early return deleted four things together --
        the button, the offer, the sending disclosure and the request counter
        -- in the one state a reader who has typed nothing is looking at."""
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.UNTOUCHED
            + self.READ_BLOCK
            + r"""
console.log(JSON.stringify({
  ask: (block.match(/data-next-cockpit-action="reading-ask"/g) || []).length,
  offer: block.includes("account of the evidence on this page"),
  disclosure: block.includes("Codex reads this Codex session.") && block.includes("OpenAI"),
  counter: /\d+ model requests? recorded for this session\./.test(block),
}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(1, out["ask"])
        self.assertTrue(out["offer"])
        self.assertTrue(out["disclosure"])
        self.assertTrue(out["counter"])

    def test_the_empty_sentence_moves_after_the_button_instead_of_replacing_it(self) -> None:
        """DRC-4588 AC-2. The control recomputes the same reason and prints it
        itself, so deleting the caller's copy moves the sentence rather than
        losing it -- and printing both would be the duplication this guards."""
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.UNTOUCHED
            + self.READ_BLOCK
            + f"const sentence = {json.dumps(self.NOTHING_TYPED)};\n"
            + r"""
const buttonAt = block.indexOf('data-next-cockpit-action="reading-ask"');
console.log(JSON.stringify({
  count: block.split(sentence).length - 1,
  buttonAt,
  afterButton: block.indexOf(sentence) > buttonAt,
  extended: block.includes(sentence + " Save a goal above to check for drift."),
}));
"""
        )

        assert isinstance(out, dict)
        # Exactly once: the caller's copy is gone and the control's is the only
        # one left. Two would mean the early return was deleted without noticing
        # that the control prints the reason too.
        self.assertEqual(1, out["count"])
        # Named before the ordering claim, because "after the button" is
        # satisfied by a missing button too -- which is the state this issue
        # exists to end, and would make the assertion below a tautology.
        self.assertGreater(out["buttonAt"], -1)
        self.assertTrue(out["afterButton"])
        # Verbatim, with the next step appended rather than the sentence
        # rewritten -- the server refuses `/api/reading` with these same words.
        self.assertTrue(out["extended"])

    def test_the_request_counter_reads_the_published_count(self) -> None:
        """DRC-4588 AC-3. The figure has to come from `reading_count`, and the
        state that proves it is the untouched one, where the counter was not
        rendered at all before this change."""
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.UNTOUCHED
            + r"""
const read = () => {
  const block = (__els.app.innerHTML.match(
    /<div class="next-session-drift-check">[\s\S]*?<section class="next-cockpit-reading">[\s\S]*?<\/section>/) || [""])[0];
  const found = (block.match(/(\d+) model requests? recorded for this session\./) || [])[1];
  return found === undefined ? null : found;
};
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const none = read();
__dashboard.sessions[0].annotation_reading_count = 3;
renderNext();
const three = read();
console.log(JSON.stringify({none, three}));
"""
        )

        assert isinstance(out, dict)
        # A fixture carrying 3 renders 3, and an untouched session renders 0.
        # A hard-coded figure, or one read off a different field, moves one of
        # these two and not the other.
        self.assertEqual("0", out["none"])
        self.assertEqual("3", out["three"])

    def test_a_refused_reading_is_reachable_and_spends_nothing(self) -> None:
        """DRC-4588 AC-4. `aria-disabled` is what keeps the control in the tab
        order and lets its reason be announced -- and it is also what restores
        the click, so the handler gate is half of this change rather than a
        refinement of it."""
        out = self.run_fixture(
            self.FOCUS_DOM
            + r"""
__dashboard.reading_check = "accepted";
__dashboard.annotate = true;
const session = __dashboard.sessions[0];
const annotation = {goal:"", output:"", reading_count:0};
const model = {enabled:true};
const refused = nextCockpitReadingControl(session, annotation, model);
let calls = 0;
const upstream = __fetchImpl;
__fetchImpl = (url, init) => {
  if(String(url) === "/api/reading") calls += 1;
  return upstream(url, init);
};
await nextCockpitAskForReading(session, model);
const after = nextCockpitReadingControl(session, annotation, model);
console.log(JSON.stringify({refused, after, calls}));
"""
        )

        assert isinstance(out, dict)
        refused = out["refused"]
        assert isinstance(refused, str)
        # The aria spelling, and NOT the bare attribute. `disabled` takes the
        # control out of the tab order and silences its `aria-describedby`;
        # the regex the file already carries at the progress test matches both
        # spellings and so cannot witness either direction.
        self.assertRegex(refused, r'reading-ask"[^>]*\saria-disabled="true"')
        self.assertNotRegex(refused, r'reading-ask"[^>]*\sdisabled[=>\s]')
        # The description is wired to the paragraph that carries the reason,
        # by id rather than by proximity.
        described = re.search(r'reading-ask"[^>]*aria-describedby="([^"]+)"', refused)
        self.assertIsNotNone(described)
        assert described is not None
        self.assertIn(f'id="{described.group(1)}"', refused)
        self.assertIn(self.NOTHING_TYPED, refused)
        # And the press the attribute now permits reaches no network at all.
        # Without the gate this is 1, and each one spends the reader's own
        # model capacity from a state the page calls unavailable.
        self.assertEqual(0, out["calls"])
        after = out["after"]
        assert isinstance(after, str)
        self.assertRegex(after, r'role="status"[^>]*>[^<]*Nothing has been typed')

    def test_the_save_control_is_present_and_inert_rather_than_absent(self) -> None:
        """DRC-4588 AC-5. A keyboard reader tabbing the empty form met no save
        control at all, because it was emitted `hidden`. The keystroke path is
        the one a renderer-only fix misses: it clears the attribute in place,
        without a redraw."""
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.UNTOUCHED
            + r"""
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const saveTag = () => (__els.app.innerHTML.match(
  /<button[^>]*data-next-cockpit-action="held-save" data-arg="goal"[^>]*>/) || [""])[0];
const clearTag = () => (__els.app.innerHTML.match(
  /<button[^>]*data-next-cockpit-action="held-clear" data-arg="goal"[^>]*>/) || [""])[0];
const saveControl = () => controls.find(control =>
  control.dataset.nextCockpitAction === "held-save" && control.dataset.arg === "goal");
const resting = saveTag();
const restingClear = clearTag();
const absentTag = (__els.app.innerHTML.match(
  /<p class="next-cockpit-held-absent" id="[^"]*" data-next-cockpit-held-absent="goal"[^>]*>/) || [""])[0];
// A press while inert, before anything is typed.
let posts = 0;
const upstream = __fetchImpl;
__fetchImpl = (url, init) => {
  if(String(url) === "/api/annotate") posts += 1;
  return upstream(url, init);
};
__fire("click", {target:saveControl(), preventDefault(){}});
await __settle();
// Then a keystroke, which does not redraw: the handler has to reach the
// element already on the page.
const before = __els.renders;
const box = controls.find(control => control.dataset.nextCockpitHeldKind === "goal");
box.value = "Ship the cockpit";
__fire("input", {target:box});
const typed = saveControl();
console.log(JSON.stringify({
  resting, restingClear, absentTag, posts, redrew: __els.renders !== before,
  typedAria: typed.attrs["aria-disabled"] || null, typedHidden: typed.hidden,
  typedDescribedBy: typed.attrs["aria-describedby"] || null,
}));
"""
        )

        assert isinstance(out, dict)
        resting = out["resting"]
        assert isinstance(resting, str)
        # Present, and inert by the attribute that keeps it in the tab order.
        self.assertNotEqual("", resting)
        self.assertNotRegex(resting, r"\shidden[=>\s]")
        self.assertIn('aria-disabled="true"', resting)
        # And it says WHY, which `hidden` never had to: the control was off the
        # page entirely, so there was nobody to tell. `aria-disabled` puts it in
        # the tab order, and a reader who reaches it would otherwise hear only
        # that it is dimmed. The pointer resolves to the sentence on the page.
        described = re.search(r'aria-describedby="([^"]+)"', resting)
        self.assertIsNotNone(described)
        assert described is not None
        absent_tag = out["absentTag"]
        assert isinstance(absent_tag, str)
        self.assertIn(f'id="{described.group(1)}"', absent_tag)
        # `clear` keeps `hidden`: there is nothing to clear and nothing to
        # explain, so an inert control there would be noise rather than an
        # affordance.
        resting_clear = out["restingClear"]
        assert isinstance(resting_clear, str)
        self.assertRegex(resting_clear, r"\shidden[=>\s]")
        # The press the attribute permits reaches no endpoint.
        self.assertEqual(0, out["posts"])
        # And a keystroke clears the attribute in place rather than the
        # `hidden` property, which is the path :3430 takes on every keystroke
        # and the one a renderer-only fix would leave writing the wrong field.
        self.assertFalse(out["redrew"])
        self.assertIsNone(out["typedAria"])
        self.assertFalse(out["typedHidden"])
        # The description goes with the state it explains. Left behind, it
        # describes a live control by the sentence saying its field is empty.
        self.assertIsNone(out["typedDescribedBy"])

    def test_a_refusal_never_outlives_the_state_it_describes(self) -> None:
        """DRC-4588 AC-2 and AC-4 at the point they interact.

        The press must leave a `role="status"` message giving the reason, and
        the sentence must render exactly once. Storing the refusal as a message
        satisfies the first and breaks the second, because the control already
        prints that same sentence as the paragraph the button is described by.
        And a stored refusal nothing clears outlives the state it describes: the
        reader does what the sentence asks, the button enables, and the sentence
        underneath still says nothing has been typed. That is the board stating
        an absence that is no longer true, beside a control contradicting it,
        which is the defect this milestone exists to remove.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.UNTOUCHED
            + r"""
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
// The observer model read, so the only reason left is the one being tested.
const group = nextProjectGroups().find(g => g.label === "cargento");
const ctx = nextCockpitContexts.get(
  nextCockpitContextKey(group, nextCockpitFocusedSession(group)));
ctx.data = Object.assign({}, ctx.data, {observer_model:{enabled:true, disclosure:"x"}});
renderNext();
const block = () => (__els.app.innerHTML.match(
  /<div class="next-session-drift-check">[\s\S]*?<section class="next-cockpit-reading">[\s\S]*?<\/section>/) || [""])[0];
const sentence = "Nothing has been typed for this session, so there is nothing to read it against.";
const count = () => block().split(sentence).length - 1;
const before = count();
// The press `aria-disabled` now permits.
__fire("click", {target:controls.find(c =>
  c.dataset.nextCockpitAction === "reading-ask"), preventDefault(){}});
await __settle();
const afterPress = count();
const statuses = (block().match(/role="status"/g) || []).length;
// And then the reader does exactly what the sentence told them to do.
__dashboard.sessions[0].annotation_goal = "Ship the cockpit";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
renderNext();
const afterSave = count();
const stillRefused = /data-next-cockpit-action="reading-ask"[^>]*aria-disabled/.test(block());
// The lane itself, not only what it renders. With the dedupe in place a stale
// refusal is invisible, so a render-only assertion passes while the entry
// lives forever -- measured: removing the clear left every rendered assertion
// here green. The next render path added for stored messages would bring the
// defect straight back.
const lingering = nextCockpitReadingRequests.has(sessKey(__dashboard.sessions[0]));
console.log(JSON.stringify({before, afterPress, statuses, afterSave, stillRefused, lingering}));
"""
        )

        assert isinstance(out, dict)
        self.assertEqual(1, out["before"])
        # AC-2 holds across the press: announced, not printed twice.
        self.assertEqual(1, out["afterPress"])
        # AC-4 still holds: the press leaves a live-region message.
        self.assertGreaterEqual(out["statuses"], 1)
        # And the sentence goes when the state it describes goes. Without a
        # clear this is 1, sitting under a button that is no longer refused.
        self.assertEqual(0, out["afterSave"])
        self.assertFalse(out["stillRefused"])
        # And the entry is gone from the lane, not merely unrendered.
        self.assertFalse(out["lingering"])

    # ---- DRC-4590, extended by DRC-4603 -----------------------------------
    #
    # DRC-4603 is the product question DRC-4590 filed rather than answered:
    # what IS the main action of `Now`, `Course`, `Decisions` and `Console`?
    # Ruled 2026-09-22: **all four deliberately have none**, and the reason is
    # per tab rather than one reason four times. Each is the kind of control the
    # tab renders, which is why this is checked rather than written down:
    #
    #   now        navigation only. Every control is a card that routes to a
    #              session view. A selection is not an act, on the same
    #              reasoning that excludes the tab strip itself.
    #   course     disclosure only. The panel's own control opens and closes
    #              the change list. The tripwire Save/Rearm/Remove buttons are
    #              real acts, but they are per-tripwire ROW controls -- there
    #              are three per card and N cards -- so none of them is "the
    #              main action of this tab", and marking one would promise a
    #              singular the markup cannot keep.
    #   decisions  selection only. The three-button graph filter chooses which
    #              events to show; it changes the view, not the session.
    #   console    the only act in the panel is the tripwire add, and DRC-4590's
    #              own acceptance forbids marking either it or the steer submit.
    #              Everything else on the tab is consent or navigation.
    #
    # `held-to` kept its one primary, "Ask for a reading", until DRC-4639 merged
    # it into the session page. There the rule is "at most one primary; none
    # while a question is open without a raise" (DEC-20, which amends this
    # ruling): "Check for drift" holds it on an unblocked session, no answer
    # option is ever emphasised, and a blocked session with no raise on offer
    # has none. The per-tab count below is extended with both session-page
    # states rather than replaced.
    #
    # The ruling is BOUND rather than narrated. A zero is what a tab with no
    # controls at all scores and what a tab whose controls were all deleted
    # scores, so the count below cannot tell a deliberate none from an empty
    # panel. `test_the_four_tabs_without_a_primary_render_no_act_to_mark`
    # classifies what each of the four actually renders, so a tab that gains a
    # genuine act reds and the ruling is re-made rather than inherited.
    NO_PRIMARY_TABS: ClassVar[tuple[str, ...]] = ("now", "course", "decisions", "console")

    # Each kind is a reason a control is not a candidate for its tab's main
    # action, keyed by the attribute that carries the behaviour rather than by
    # the label, because a label is the part that gets rewritten. The last two
    # are excused by a ruling rather than by their kind, and say whose.
    CONTROL_KINDS: ClassVar[dict[str, str]] = {
        "navigation": "data-next-route",
        "disclosure": "aria-expanded",
        "selection": "aria-pressed",
        # DRC-4590's AC-2 forbids marking this one by name.
        "forbidden-by-4590": "next-guardrail-add",
        # An answer about what Cargento may read, given once. Not a thing a
        # reader comes back to a tab to do.
        "consent": "data-next-usage-answer",
        # Consent plus one gated act. See DRC-4603's ruling in the test below.
        "gated-act": "data-next-observer-action",
    }

    @classmethod
    def _kind(cls, markup: str) -> str | None:
        return next((name for name, mark in cls.CONTROL_KINDS.items() if mark in markup), None)

    def test_one_tab_of_five_carries_a_primary_and_the_rest_carry_none(self) -> None:
        """DRC-4590 AC-2, narrowed at triage to the one target that exists.

        The issue as filed asked for exactly one primary per tab, naming "Open
        this session" for three tabs and a registration-copy control for a
        fourth. Three of those do not exist as controls and the fourth does not
        exist at all: `Course` and `Decisions` emit no `<button>`, `Now` emits
        only navigation cards, and `Console`'s two controls are the steer submit
        and the tripwire add, which this criterion forbids marking. So four tabs
        have nothing to mark, and what each tab's main action should BE is a
        product question filed as its own issue rather than answered here.

        DRC-4603 answered it: none of the four, each for its own reason. The
        expectation is unchanged and this test is extended rather than replaced,
        which is that issue's own acceptance. The comment above carries the
        ruling and the test below carries the part of it that can go stale.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + r"""
__dashboard.reading_check = "accepted";
const counts = {};
const primaries = () => [...__els.app.innerHTML.matchAll(
  /<button\b[^>]*next-action--primary[^>]*>/g)].map(match => match[0]);
for(const tab of ["now", "course", "decisions", "console"]){
  navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab});
  await __settle();
  counts[tab] = (__els.app.innerHTML.match(/next-action--primary/g) || []).length;
}
// The retired Held to slug, and the session page it now opens.
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
counts["held-to"] = (__els.app.innerHTML.match(/next-action--primary/g) || []).length;
const onSession = primaries();
// Blocked on the reader: an exact request with options on the page.
__dashboard.ask = true;
__dashboard.sessions[0].state = "needs_input";
__dashboard.asks = [{id:"ask-1", harness:"codex", session_id:"focus-1", project:"cargento",
  question:"Ship it?", options:["Yes", "Not yet"]}];
await refreshNext();
await __settle();
counts["session-blocked"] = (__els.app.innerHTML.match(/next-action--primary/g) || []).length;
const onBlocked = primaries();
// The two Console controls the criterion names, read from their own emitters
// rather than from whichever tab happens to render them.
const steer = nextProjectSteer("cargento", {steers:[]});
const tripwire = nextProjectGuardrailAdd("cargento", {adding:false});
console.log(JSON.stringify({counts, steer, tripwire, onSession, onBlocked}));
"""
        )

        assert isinstance(out, dict)
        # Counted per surface and not as a page total: a total asserts nothing
        # about WHERE the primary landed, and would pass with a stray one on
        # Console and none on the session page.
        self.assertEqual(
            {
                "now": 0,
                "course": 0,
                "decisions": 0,
                "console": 0,
                "held-to": 1,
                "session-blocked": 0,
            },
            out["counts"],
        )
        # Which control holds it: the check on an unblocked session, and nothing
        # on one blocked on the reader with no raise on offer (DEC-20).
        on_session = cast("list[str]", out["onSession"])
        self.assertIn('data-next-cockpit-action="reading-ask"', on_session[0])
        self.assertEqual([], out["onBlocked"])
        self.assertNotIn("next-action--primary", out["steer"])
        self.assertNotIn("next-action--primary", out["tripwire"])
        # The four tab zeros above are the ruling, so name them from the one
        # place that holds it. A tab quietly dropped from either list would
        # otherwise stop being asserted about. The blocked session page's zero
        # is DEC-20's, not this ruling's, so it is set aside by name.
        self.assertEqual(
            set(self.NO_PRIMARY_TABS),
            {tab for tab, count in cast("dict[str, int]", out["counts"]).items() if count == 0}
            - {"session-blocked"},
        )

    def test_the_four_tabs_without_a_primary_render_no_act_to_mark(self) -> None:
        """DRC-4603 AC-1: the reason each of the four has none, checked.

        Every control these four panels render is a navigation, a disclosure, a
        selection, or the one act DRC-4590's acceptance explicitly forbids
        marking. That is the ruling; an unclassified control means the tab has
        gained something that could BE its main action, and the ruling has to be
        made again rather than inherited.

        Classified on the attribute that carries the behaviour rather than on
        the label, because a label is the part that gets rewritten. Measured on
        the tree this landed against: `now` 1 control, `course` 1,
        `decisions` 3, `console` 1 -- and `held-to`, excluded here, 8.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + r"""
__dashboard.reading_check = "accepted";
const perTab = {};
for(const tab of """
            + repr(list(self.NO_PRIMARY_TABS)).replace("'", '"')
            + r"""){
  navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab});
  await __settle();
  const html = __els.app.innerHTML;
  // The panel only. The tab strip, the steer composer and the recovery strip
  // are cockpit chrome drawn above every tab, so counting them would attribute
  // one surface's controls to all five.
  const panel = (html.match(/<section class="next-cockpit-panel"[\s\S]*$/) || [""])[0];
  perTab[tab] = [...panel.matchAll(/<(?:button|form)\b([^>]*)>/g)].map(one => one[1]);
}
console.log(JSON.stringify(perTab));
"""
        )

        assert isinstance(out, dict)
        seen: dict[str, set[str]] = {}
        for tab in self.NO_PRIMARY_TABS:
            rendered = cast("list[str]", out[tab])
            self.assertTrue(rendered, f"the {tab} panel rendered no controls at all")
            for markup in rendered:
                kind = self._kind(markup)
                self.assertIsNotNone(
                    kind,
                    f"{tab} renders a control that is none of {sorted(self.CONTROL_KINDS)}, so it "
                    f"may be this tab's main action and DRC-4603's ruling needs re-making: {markup}",
                )
                seen.setdefault(tab, set()).add(cast("str", kind))
        # And the classifier is discriminating rather than matching everything:
        # three different kinds are in play across the four tabs.
        self.assertGreaterEqual(len({kind for kinds_ in seen.values() for kind in kinds_}), 3)

    def test_the_console_controls_the_fixture_does_not_reach_are_ruled_on_too(self) -> None:
        """The same ruling, over the Console controls that need an answered board.

        **Found on a live board, not here.** The walk before this landed showed
        `Console` rendering `Read my quota` and `No thanks`, two controls the
        composition fixture does not reach because it publishes no
        `usage_fetch`. The sweep above classified them as nothing at all, which
        is a universal claim over a set nobody enumerated -- the regression class
        this repository has shipped before.

        So they are read from their own emitters, which is the method DRC-4590's
        own criterion already used for the steer submit and the tripwire add:
        a control's kind is a fact about the control, not about whether one
        fixture happens to render it.
        """
        out = self.run_fixture(
            self.FOCUS_DOM
            + self.ANNOTATED
            + r"""
const payload = {...__dashboard, usage_fetch: true};
const group = {label: "cargento", sessions: __dashboard.sessions};
const focus = {harness: "codex", sid: "focus-1"};
// The controls read the FETCHED project context, not the group, so the entry is
// seeded rather than passed: an emitter reached through the wrong door renders
// its unavailable branch and the assertions below pass over nothing.
nextCockpitContexts.set(nextCockpitContextKey(group, focus), {
  revision: __dashboard.generated,
  data: {observers: [],
    observer_model: {enabled: true, disclosure: "A model reads this session."}},
});
localStorage.removeItem(NEXT_OBSERVER_CONSENT_KEY);
const emitted = {
  consentUnanswered: nextUsageDisclosure(payload),
  observerUnanswered: nextObserverModelControls(group, focus),
};
// The granted branch is where the one recurring act lives, so it has to be
// rendered rather than reasoned about.
localStorage.setItem(NEXT_OBSERVER_CONSENT_KEY, "granted");
emitted.observerGranted = nextObserverModelControls(group, focus);
localStorage.setItem(NEXT_USAGE_CONSENT_KEY, "granted");
emitted.usageSwitch = nextUsageSwitch(payload);
console.log(JSON.stringify(emitted));
"""
        )

        assert isinstance(out, dict)
        markup = "".join(str(value) for value in out.values())
        self.assertIn("data-next-usage-answer", markup, "the quota consent controls did not render")
        self.assertIn("data-next-observer-action", markup, "the observer controls did not render")
        # The granted branch specifically, because that is the one carrying the
        # recurring act. Without this the classifier is only ever shown consent
        # controls and the `gated-act` ruling below asserts nothing.
        self.assertIn("Summarize this session", str(out["observerGranted"]))
        self.assertIn("Turn off", str(out["usageSwitch"]))
        # No primary reaches Console through any of them, which is the ruling.
        self.assertNotIn("next-action--primary", markup)
        # And each one classifies, so none is an unruled candidate for the tab's
        # main action. `Summarize this session` is the interesting one: it is a
        # real recurring act rather than a consent, and it is excused as
        # `gated-act` because it exists only where the operator started the
        # server with --observer-model, focused exactly one session, and granted
        # consent. An action most readers never see is not the tab's main one.
        for one in re.findall(r"<button\b[^>]*>", markup):
            self.assertIsNotNone(
                self._kind(one),
                f"a Console control is unruled, so DRC-4603 needs re-making: {one}",
            )


class AnAbsenceNeverRendersLargerThanItsValueTest(unittest.TestCase):
    """Three pairs DRC-4592 and DRC-4597 added, carried across from a table that
    no longer exists.

    Both branches appended these to `AnAbsenceNeverOutranksTheValueItReplacesTest`
    when it was a flat table of CSS selector pairs. It was rewritten on the way
    in to resolve DOM paths through the cascade, and narrowed to the absences
    raised to the sentence tier -- which these are not, so they no longer fit
    it. The property they asserted is still true and still worth holding, so it
    is held here instead of being dropped on a technicality.

    Declared size rather than resolved, because that is what the pairs were
    written to state: each absence restates its value's size in its own rule so
    the two cannot drift apart. A pair that stops declaring a size belongs in
    the cascade test above, not here, and the `NO RULE` failure says so.

    One pair that belongs here by type is deliberately NOT here. DELEGATION's
    figure against the withheld string that replaces it -- 32px against 16px,
    both literal, both separate selectors, neither raised -- lives in
    `AnAbsentVariantBorrowsItsSizeFromTheValueItReplacesTest` instead. It is
    kept beside that class's stamp assertions because it exists precisely to
    show they are not sufficient: the stamp constrains only the absent VARIANT
    and says nothing about the base rule it sits on, so the absence can be
    raised to any size at all and every stamp assertion stays green. Measured
    at 40px against the 32px figure. Filing it here by type would put it where
    a reader looking for it would find it, and take it away from the reader
    about to make the mistake.
    """

    PAIRS = (
        # The tab cue's figure against the two marks that stand in for it.
        (".next-cockpit-tab-cue", ".next-cockpit-tab-cue--pending"),
        (".next-cockpit-tab-cue", ".next-cockpit-tab-cue--unobserved"),
        # DRC-4597's rail card: the session title against the caption beneath it.
        (".next-cockpit-scope-title", ".next-cockpit-scope-meta"),
    )

    tokens: dict[str, float]
    bodies: dict[str, str]

    @classmethod
    def setUpClass(cls) -> None:
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        cls.tokens, rules = css_cascade.load(web / "styles.css")
        cls.bodies = {}
        for selector, body, _order in rules:
            if selector.strip() in {s for pair in cls.PAIRS for s in pair}:
                cls.bodies[selector.strip()] = body

    def size(self, selector: str) -> float:
        body = self.bodies.get(selector)
        self.assertIsNotNone(body, f"{selector} declares no rule of its own")
        assert body is not None
        declared = css_cascade.declared_size(body, self.tokens)
        self.assertIsNotNone(declared, f"{selector} declares no size of its own")
        assert declared is not None
        return declared

    def test_no_absence_declares_a_larger_size_than_the_value_it_replaces(self) -> None:
        for value, absence in self.PAIRS:
            with self.subTest(value=value, absence=absence):
                self.assertLessEqual(self.size(absence), self.size(value))


class TheCaptainNeededInkStepSurvivesTest(unittest.TestCase):
    """DRC-4589 trap 1, which nothing else in this suite catches.

    `.next-cockpit-authority>span` takes its colour from the per-state rules,
    which are the same (0,1,1) specificity and sit earlier in the sheet, so the
    state that needs the captain reads brighter than the two that do not. The
    override block further down sets that selector's font and letter-spacing
    and deliberately sets NO colour: a colour tidied into it would win on source
    order and silently retire the whole step, leaving every state one ink.

    Resolved through the cascade rather than read off the block, because the
    defect is precisely that the block a reader would check looks fine.
    """

    tokens: dict[str, float]
    rules: list[tuple[str, str, int]]

    @classmethod
    def setUpClass(cls) -> None:
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        cls.tokens, cls.rules = css_cascade.load(web / "styles.css")

    def ink(self, state: str) -> str:
        path = [_node("div", "next-cockpit-authority", state), _node("span")]
        winning = []
        for selector, body, order in self.rules:
            try:
                specificity = css_cascade.matches(path, selector)
            except css_cascade.UnsupportedSelectorError:
                continue
            if specificity is None:
                continue
            declared = re.search(r"(?:^|;)\s*color:\s*([^;]+)", body)
            if declared:
                winning.append((specificity, order, declared.group(1).strip()))
        self.assertNotEqual([], winning, f"no rule colours the {state} chip")
        winning.sort()
        return winning[-1][2]

    def test_the_state_that_needs_the_captain_does_not_share_its_ink(self) -> None:
        needed = self.ink("next-cockpit-authority--captain-needed")
        for quiet in (
            "next-cockpit-authority--fo-inspecting",
            "next-cockpit-authority--fo-continues",
        ):
            with self.subTest(state=quiet):
                self.assertNotEqual(needed, self.ink(quiet))


class WithheldTitleKeepsTheAbsenceInkTest(unittest.TestCase):
    """A withheld session title must not resolve to the ink a published one gets.

    Size is not the only way an absence can outrank the value it replaces, and
    colour is the channel that went wrong here. DRC-4597 moved
    `data-next-withheld` off a `<small>` and onto
    `span.next-cockpit-scope-title`; that class declares `color:var(--ink)` at
    (0,1,0), the same specificity as the bare `[data-next-withheld]` rule and
    later in the sheet, so the bare rule lost and an absent title rendered in
    full ink -- byte-identical to a real one. Two rule-counting tests passed
    over it, because neither resolved the pair.

    Asserted as inequality against the present branch rather than against a
    named token, so it keeps holding if the register is ever repointed.
    """

    tokens: dict[str, float]
    rules: list[tuple[str, str, int]]

    @classmethod
    def setUpClass(cls) -> None:
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        cls.tokens, cls.rules = css_cascade.load(web / "styles.css")

    def ink(self, withheld: bool) -> str:
        path = [
            _node("div", "next-cockpit-scope-tree"),
            _node("a"),
            _node("span", "next-cockpit-scope-line"),
            _node(
                "span",
                "next-cockpit-scope-title",
                attrs=("data-next-withheld",) if withheld else (),
            ),
        ]
        winning = []
        for selector, body, order in self.rules:
            try:
                specificity = css_cascade.matches(path, selector)
            except css_cascade.UnsupportedSelectorError:
                continue
            if specificity is None:
                continue
            declared = re.search(r"(?:^|;)\s*color:\s*([^;]+)", body)
            if declared:
                winning.append((specificity, order, declared.group(1).strip()))
        self.assertNotEqual([], winning, "no rule colours the scope title at all")
        winning.sort()
        return winning[-1][2]

    def test_a_withheld_title_does_not_resolve_to_the_present_title_ink(self) -> None:
        self.assertNotEqual(self.ink(withheld=True), self.ink(withheld=False))

    def test_a_withheld_title_resolves_through_the_absence_register(self) -> None:
        self.assertEqual("var(--ink-absence)", self.ink(withheld=True))


def _node(tag: str, *classes: str, attrs: tuple[str, ...] = ()) -> dict[str, object]:
    return {"tag": tag, "classes": set(classes), "attrs": set(attrs)}


# `next-project.js:396` wraps the cockpit in `.next-cockpit-content`. Leaving it
# out is not cosmetic: a rule qualified by it outranks one that is not, so a
# fixture without it resolves a DOM the application never builds.
_CONTENT = [_node("div", "next-cockpit-content")]


class AnAbsenceNeverOutranksTheValueItReplacesTest(unittest.TestCase):
    """DRC-4587. A stated absence must never render larger than the fact it
    stands in for: "you can tell a label from its answer, a figure from a gap".

    **This asserts only what the pull request claims.** Each pair is listed below
    with the value it is drawn against. Enumerating them exhaustively is the
    whole claim; the wider class of sub-floor absences is DRC-4602's, and nothing
    here asserts anything about it. One inversion this guard cannot see is
    tracked as DRC-4607: a value that declares no size of its own and inherits
    one, drawn against an absence that declares a larger one.

    Three earlier versions of this guard passed over the defect they were named
    for, and the shape of each failure is why this one is written as it is. One
    compared a value against its absence and could not see both move together.
    One built a DOM the application never renders. One checked an absence's size
    without its value, and so asserted an inversion as correct. **An absence is
    only ever read beside the value it replaces.**
    """

    # (name, emitter, absence path, the value it is drawn against).
    #
    # The entry that stood here was `two axes, read separately`, and DRC-4591
    # deleted that span as a duplicate of the footer under the same cards. It was
    # replaced rather than dropped, because removing it silently would have left
    # this tuple empty and the loop below green over nothing.
    #
    # It also did not fail when the class went. `css_cascade.resolve` walks up
    # the path and inherits, so with the rule gone the absence still resolved to
    # 15.0 off the section and compared equal to its value. That is this class's
    # own second failure shape, "one built a DOM the application never renders",
    # reproduced in the test named for it: a path is only evidence while the
    # emitter still builds it, and no resolver can tell you that it does.
    # `test_the_retired_axes_span_stays_retired` below is what holds that half.
    RAISED_ABSENCES = (
        (
            "landing card value",
            "next-cockpit.js nextCockpitLanded",
            [
                *_CONTENT,
                _node("section", "next-cockpit-landed"),
                _node("div", "next-cockpit-landed-cards"),
                _node("div", "next-cockpit-landed-card"),
                _node(
                    "span",
                    "next-cockpit-landed-value",
                    "next-cockpit-landed-value--absent",
                ),
            ],
            [
                *_CONTENT,
                _node("section", "next-cockpit-landed"),
                _node("div", "next-cockpit-landed-cards"),
                _node("div", "next-cockpit-landed-card"),
                _node("span", "next-cockpit-landed-value"),
            ],
        ),
    )

    css: str
    tokens: dict[str, float]
    rules: list[tuple[str, str, int]]

    @classmethod
    def setUpClass(cls) -> None:
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        cls.tokens, cls.rules = css_cascade.load(web / "styles.css")
        cls.cockpit_js = (web / "next-cockpit.js").read_text(encoding="utf-8")

    cockpit_js: str

    def size(self, path: list[dict[str, object]]) -> float:
        resolved = css_cascade.resolve(path, self.tokens, self.rules)
        self.assertIsNotNone(resolved, f"no size resolves for {path}")
        assert resolved is not None
        return resolved

    def test_every_absence_this_change_raises_is_read_beside_its_value(self) -> None:
        for name, emitter, absence_path, value_path in self.RAISED_ABSENCES:
            with self.subTest(absence=name):
                absence, value = self.size(absence_path), self.size(value_path)
                self.assertGreaterEqual(
                    value,
                    absence,
                    f'"{name}" ({emitter}): absence {absence}px against value {value}px, '
                    "so the absence outranks the fact it replaces",
                )

    def test_the_retired_axes_span_stays_retired(self) -> None:
        """DRC-4591 AC-4: `two axes, read separately` appears nowhere in the runtime.

        A resolver cannot notice that an emitter stopped building a path, so a
        restored span would rejoin the page with no rule of its own and no entry
        above holding it against a value. Both halves are checked, because
        leaving the rule behind is how a later revert finds a selector waiting
        for it.

        "Nowhere in the runtime" was verified against two files,
        `next-cockpit.js` and `styles.css`, which is the criterion's own word
        checked over the two places the author happened to look. Widened to the
        whole-file walk `RuntimeDecisionCitationsTest` makes -- every `.py`,
        `.js`, `.css` and `.html` under `cargento_runtime` -- because the span
        could return through any of them and the sentence promises all of them.
        The count is asserted too: a walk that reaches no file passes a
        `assertNotIn` loop over nothing.
        """
        runtime = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime"
        scanned = sorted(
            source
            for source in runtime.rglob("*")
            if source.suffix in {".py", ".js", ".css", ".html"} and source.is_file()
        )
        # The bundle is ~40 files; a floor well under it catches a walk that
        # silently reaches nothing without pinning a number that a new module
        # would move.
        self.assertGreater(len(scanned), 20, "the runtime walk found almost no files")
        for source in scanned:
            body = source.read_text(encoding="utf-8")
            with self.subTest(source=source.name):
                self.assertNotIn("two axes, read separately", body)
                self.assertNotIn("next-cockpit-landed-axes", body)

    def test_the_revision_slot_cannot_invert_because_one_class_carries_both(self) -> None:
        """The other raised absence has no value to be read beside.

        `nextCockpitHeldTo` fills one span from a chain: a discard stamp, then a
        revision line, then "No revision saved yet". Value and absence are the
        same element with the same class, so they resolve identically whatever
        the tier is. That is a stronger guarantee than a comparison, and it
        holds only while the chain stays in one assignment, which is what this
        asserts.
        """
        chain = (
            "nextAnnotationDiscardStamp(annotation) ||\n"
            '    nextProjectRevisionLine(annotation) || "No revision saved yet"'
        )
        self.assertIn(chain, self.cockpit_js)
        emitted = re.findall(r'class="next-cockpit-held-revision"', self.cockpit_js)
        self.assertEqual(
            1,
            len(emitted),
            "the revision slot is emitted more than once, so the chain may have split",
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitReadingShapeTest(NextPageJsHarness):
    """DEC-17's seven rules, one case each (DRC-4511 AC4).

    Asserted against source-shaped fixtures rather than against expected
    judgements. A producer exists, but no judgement of it is validated yet:
    DEC-17's abstention check has not run, and the ruling refuses a rubric
    validated on fixtures the same pass wrote. So these hold the shape rather
    than the verdict, which is that the three worst outputs cannot be
    rendered: the word "met", a departure citing nothing, and a deliverable
    claim resting on evidence that demonstrates no work.
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

    def test_a_reading_reports_the_revision_it_read_not_the_one_typed_since(self) -> None:
        """Finding F, raised by Antigravity.

        The shape filtered and clauseed on the CURRENT annotation. A reading
        of revision 1 therefore displayed revision 2's text as the clause it
        judged, and a constraint cleared since dropped its row and its
        departure with it, after which the block rendered "The reading raised
        no departure from the revision it read" about a revision whose
        departure had just been deleted.
        """
        out = self.run_fixture(
            self.ENTRIES
            + """
// A reading of revision 1 that found a departure on the expected output.
// `a1` and not `u1`: an Expected Output verdict needs an entry that
// DEMONSTRATES work since rule 7 was re-keyed, and the reader's own request
// is not one. This test is about clauses and revisions, so it cites the
// entry that lets it be about those.
const reading = {revision_read:1, criteria:{
  output:{result:"departure", clause:"six screenshots", detail:"Three exist.", cites:["a1"]}}};
// Revision 2 cleared that field and changed the goal.
const now = {goal:"a different goal", output:"", revision:2};
const read = nextCockpitReadingShape(reading, now, entries, "");
const row = key => read.criteria.find(candidate => candidate.key === key);
console.log(JSON.stringify({
  keys: read.criteria.map(candidate => candidate.key),
  clause: row("output").clause,
  result: row("output").result,
  departures: read.departures.length,
  // The goal row has no entry in this reading and its clause must not be
  // today's text presented as what a past reading judged.
  goalClause: row("goal").clause,
  goalClauseKnown: row("goal").clauseKnown,
}));
"""
        )

        # Then: the cleared constraint keeps its row, its clause and its
        # departure, all as the reading read them.
        assert isinstance(out, dict)
        self.assertIn("output", out["keys"])
        self.assertEqual("six screenshots", out["clause"])
        self.assertEqual("departure", out["result"])
        self.assertEqual(1, out["departures"])
        # And a constraint the reading did not carry does not borrow today's
        # words: that would be the historical reading describing the current
        # request, which the amber line beside it exists to deny.
        self.assertFalse(out["goalClauseKnown"])
        self.assertEqual(
            "the words of the revision this reading read are not retained", out["goalClause"]
        )

    def test_a_stored_reason_renders_where_this_page_derives_none(self) -> None:
        """DRC-4544 item 3, the renderer half.

        The page re-derives every rule over the entries it holds, and that
        derivation stays authoritative. What it cannot derive is why a row the
        producer already marked `not verifiable` was marked so: a constraint
        never put to the model looks exactly like a model that said
        `unverifiable`, and until now the limit row came from TODAY's harness
        rather than from the reading. The stored token fills only the gap the
        page's own derivation leaves.
        """
        out = self.run_fixture(
            self.ENTRIES
            + """
const unv = "not verifiable from available evidence";
const rows = (criteria, limit) =>
  shape(criteria, limit).criteria.map(nextCockpitReadingCriterionRow).join("");
const row = (key, why, limit) => rows(
    {[key]: {result: unv, cites: [], detail: "", clause: "typed words", why}}, limit)
  .split('<div class="next-cockpit-reading-row">').filter(Boolean)
  .find(r => r.includes(key === "output" ? "EXPECTED OUTPUT" : "TYPED GOAL"));
console.log(JSON.stringify({
  notAsked: row("output", "not-asked", ""),
  unreadable: row("goal", "unreadable", ""),
  // The shape `resolve` actually writes for rule 2, measured 2026-09-12:
  // `why` set and no `result` key at all, because rule 2's fallback is an
  // absent result rather than a present one. Held here as well as above,
  // because the row with `result` present is a shape the producer cannot
  // emit for this token, and it is the only one the case above proves.
  producerUnreadable: rows({goal: {cites: [], detail: "", clause: "typed words",
    why: "unreadable"}}, "").split('<div class="next-cockpit-reading-row">').filter(Boolean)
    .find(r => r.includes("TYPED GOAL")),
  uncited: row("goal", "uncited", ""),
  stands: row("goal", "", ""),
  liveLimitWins: row("output", "not-asked", "Codex publishes no demonstrated work results."),
  future: row("goal", "a-token-from-the-future", ""),
  liveRulesWin: shape({goal: {result: "departure", cites: ["u1"], detail: "drifted",
    clause: "x", why: "uncited"}}).criteria[0].result,
  sentence: NEXT_READING_NOT_ASKED,
  storedUnreadable: NEXT_READING_STORED_WHY["unreadable"],
}));
"""
        )
        assert isinstance(out, dict)
        malformed = "The reading did not return a usable result for this constraint."
        # A stored limit draws the limit row, in the limit's own register.
        self.assertIn("limit · ", out["notAsked"])
        self.assertIn(out["sentence"], out["notAsked"])
        self.assertNotIn('class="next-cockpit-reading-why"', out["notAsked"])
        # The two rule-2 and rule-3 reasons render the sentences the page owns.
        self.assertIn(malformed, out["unreadable"])
        # And on the shape the producer writes, the same sentence arrives from
        # the page's own rule 2 rather than from the stored token, which is why
        # a rule-2 row needs no limit slot.
        self.assertIn(malformed, out["producerUnreadable"])
        self.assertNotIn("limit · ", out["producerUnreadable"])
        # The two routes must not drift apart. A rule-2 row reaches the page by
        # whichever arm sees it first, and a distinct sentence behind the token
        # would make the same stored row read two ways depending on that.
        self.assertEqual(malformed, out["storedUnreadable"])
        self.assertIn("Nothing resolvable was cited", out["uncited"])
        # A result that stands carries no reason and no limit: the pair above
        # binds on the sentence, because this row has neither.
        self.assertNotIn(malformed, out["stands"])
        self.assertNotIn('class="next-cockpit-reading-why"', out["stands"])
        self.assertNotIn("limit · ", out["stands"])
        # Today's limit wins over the stored one where both exist.
        self.assertIn("Codex publishes no demonstrated work results.", out["liveLimitWins"])
        self.assertNotIn(out["sentence"], out["liveLimitWins"])
        # A token this build does not know is the unknown-key asymmetry one
        # level down: not readable, and said so.
        self.assertIn(malformed, out["future"])
        # And the live rules stay authoritative: a stored reason never
        # overrides a result the page derived from evidence it holds.
        self.assertEqual("departure", out["liveRulesWin"])

    def test_rule_4_the_word_met_cannot_reach_the_page(self) -> None:
        out = self.run_fixture(
            self.ENTRIES
            + """
// Every reachable result string, rendered, plus a producer trying to say met.
const html = [
  {goal:{result:"met", cites:["u1"]}},
  {goal:{result:"departure", detail:"met the wrong thing", cites:["u1"]}},
  // `a1`: a `consistent` citing only the reader's own request is circular
  // and demotes now. This case exists to show the third result string
  // rendering, so it cites something that corroborates.
  {goal:{result:"consistent with the evidence read", cites:["a1"]}},
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
const rows = shape({goal:{result:"consistent with the evidence read", cites:["a1"]},
  output:{result:"departure", cites:["a1"]}}, limit).criteria;
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
            {"goal": ["result · dispatch artifact · exact"], "output": []}, out["evidence"]
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

    def test_rule_7_asks_whether_an_entry_shows_work_not_who_typed_it(self) -> None:
        """Amended 2026-09-10: the test is demonstrated work, not authorship.

        As written, rule 7 keyed the Expected Output verdict on WHO wrote a
        cited entry, and that inverted its own reason. The reason is that
        self-report is not evidence of a deliverable -- and a REQUEST is not
        evidence of one either, so citing the reader's own words licensed a
        verdict about her own deliverable while citing the actual work result
        demoted. Seven adversaries found it; the captain re-keyed it.
        """
        out = self.run_fixture(
            self.ENTRIES
            + """
const shows = ["a1"];      // type `result`: an entry that demonstrates work
const asked = ["u1"];      // the reader's own request
const gate = ["g1"];       // a person's gate decision, but not work
console.log(JSON.stringify({
  outputOnWork: results({output:{result:"departure", cites:shows}}),
  outputConsistentOnWork: results({output:{result:"consistent with the evidence read",
    cites:shows}}),
  outputOnRequest: results({output:{result:"departure", cites:asked}}),
  outputOnGate: shape({output:{result:"departure", cites:gate}}).criteria
    .find(row => row.key === "output").result,
  // Goal keeps a departure on the agent's own narration.
  goalOnAgent: results({goal:{result:"departure", cites:shows}}),
  // A goal `consistent` resting only on the agent says so...
  narration: shape({goal:{result:"consistent with the evidence read",
    cites:shows}}).criteria[0].narration,
  // ...and one resting only on the reader's own request is circular.
  goalConsistentOnRequest: shape({goal:{result:"consistent with the evidence read",
    cites:asked}}).criteria[0].result,
  why: shape({output:{result:"departure", cites:asked}}).criteria
    .find(row => row.key === "output").why,
}));
"""
        )
        assert isinstance(out, dict)
        unverifiable = "not verifiable from available evidence"
        # An entry that shows work carries a verdict about the deliverable.
        self.assertEqual("departure", out["outputOnWork"]["output"])
        self.assertEqual(
            "consistent with the evidence read", out["outputConsistentOnWork"]["output"]
        )
        # The reader's own request does not, whoever typed it, and neither
        # does a person's gate decision: neither shows the thing exists.
        self.assertEqual(unverifiable, out["outputOnRequest"]["output"])
        self.assertEqual(unverifiable, out["outputOnGate"])
        # Goal is unchanged: a stated change of direction is exactly what the
        # agent's own account is good for.
        self.assertEqual("departure", out["goalOnAgent"]["goal"])
        self.assertEqual("Rests on the agent's own account alone.", out["narration"])
        # But agreeing with the request is agreeing with yourself.
        self.assertEqual(unverifiable, out["goalConsistentOnRequest"])


class CockpitTabsAreOneDecisionTest(unittest.TestCase):
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
        # Both scopes hold the same four tabs since Held to merged into the
        # session page (DRC-4639). The walk still reads the rendered set rather
        # than the list, so a session-scope tab added later cannot be skipped.
        self.assertEqual(["now", "course", "decisions", "console"], out["project"]["rendered"])
        self.assertEqual(
            ["now", "course", "decisions", "console"],
            out["codex:focus-1"]["rendered"],
        )
        # A route whose focus names no session in the payload draws the stale
        # filter surface instead of a cockpit, so it has no tabs to disagree
        # about. Asserted rather than assumed: it is the reason the empty case
        # above is legal.
        self.assertEqual([], out["codex:gone"]["rendered"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitBaselineConflictTest(NextPageJsHarness):
    """DRC-4508's baseline-conflict block, and the departure it suppresses.

    The block DETECTS that a later direction exists and refuses to say whether
    it conflicts. Deciding that is a reading of two prose strings, which DEC-15
    refused and DEC-18 permits only behind preconditions that are not met, so
    the reader settles it and the reading is demoted until they do.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    # The fixture's own facts: user_message fo-a at 104 and fo-b at 102 for
    # codex:focus-1, so an annotation stamped 100 has two later directions and
    # one stamped 200 has none.
    def held(self, *, at: float, settled: str = "", assessment: str = "") -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            f"""
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "do not change the board";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = {at};
__dashboard.sessions[0].annotation_binding_why = "";
{settled}
{assessment}
navigateNext({{view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"}});
await __settle();
const html = __els.app.innerHTML;
const block = (html.match(
  /<section class="next-cockpit-conflict">[\\s\\S]*?<\\/section>/) || [""])[0];
console.log(JSON.stringify({{
  block,
  rows: (block.match(/class="next-cockpit-conflict-row"/g) || []).length,
  settle: (block.match(/data-arg="([0-9.]+)"/) || [])[1] || "",
  result: (html.match(/class="next-cockpit-reading-result">([^<]*)</) || [])[1] || "",
}}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    ASSESSMENT = """
__dashboard.sessions[0].annotation_assessment = {revision_read:1, criteria:{
  goal:{result:"departure", detail:"It changed the board.", cites:["fo-a"]}}};
"""

    def test_nothing_typed_renders_no_block_at_all(self) -> None:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_at = null;
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
console.log(JSON.stringify({has: __els.app.innerHTML.includes('class="next-cockpit-conflict"')}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        # No baseline, so no question about one. It falls out of the layout
        # rather than needing a rule.
        self.assertFalse(out["has"])

    def test_a_later_direction_is_counted_and_shown_without_being_judged(self) -> None:
        out = self.held(at=100)

        block = out["block"]
        assert isinstance(block, str)
        self.assertIn("2 directions you gave after you saved the words above", block)
        self.assertEqual(2, out["rows"])
        # Detected, not judged. The block must never claim the later direction
        # conflicts, because nothing here can read that.
        self.assertIn("Nothing here decides whether it changes what you are asking for", block)
        # On the visible text, not the markup. DEC-20 labels the block
        # "Conflict to settle", knowing it breaks DEC-16's no-conflict sentence:
        # the label puts a question and records no finding. So the word appears
        # once, as that label, and nowhere else -- no sentence says Cargento
        # found one, because nothing here can read that.
        visible = re.sub(r"<[^>]*>", " ", block).lower()
        self.assertEqual(1, visible.count("conflict"))
        self.assertIn("conflict to settle", visible)
        # Both choices, and the honest note about the one that mints nothing.
        self.assertIn("The baseline still applies", block)
        self.assertIn("Retype the baseline", block)
        self.assertIn("Retyping clears this only if the words change", block)

    def test_the_settle_choice_carries_the_moment_the_reader_was_shown(self) -> None:
        out = self.held(at=100)
        # The newest candidate's own time, not the clock: the mark has to be
        # the moment they actually looked at.
        self.assertEqual("104", out["settle"])

    def settled_with(self, reply: str) -> dict[str, Any]:
        """Press `The baseline still applies` against a stubbed reply, then
        read the conflict block the handler's own refresh redrew."""
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + CockpitHeldToTabTest.FOCUS_DOM
            + f"""
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "do not change the board";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";
const upstream = __fetchImpl;
let posted = null;
__fetchImpl = async (url, init) => {{
  if(String(url) !== "/api/annotate") return upstream(url, init);
  posted = JSON.parse(init.body);
  return {{ok:true, status:200, json: async () => ({reply})}};
}};
navigateNext({{view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"}});
await __settle();
__fire("click", {{target:controls.find(control =>
  control.dataset.nextCockpitAction === "conflict-settle"), preventDefault(){{}}}});
await __settle();
await __settle();
const html = __els.app.innerHTML;
const block = (html.match(
  /<section class="next-cockpit-conflict">[\\s\\S]*?<\\/section>/) || [""])[0];
console.log(JSON.stringify({{
  posted,
  open: block.includes("you gave after you saved the words above"),
  cue: (block.match(/class="next-cockpit-conflict-cue">([^<]*)</) || [])[1] || "",
  heldCues: (html.match(/class="next-cockpit-held-cue"/g) || []).length,
}}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_a_settle_that_did_not_persist_says_so(self) -> None:
        """DRC-4543. The settle handler read `ok` alone and drew no cue.

        A settle whose write did not persist left the block open with no
        reason: the mark was set in this process, the handler's own refresh
        reloaded the store from disk and dropped it, and the block reopened
        looking exactly as it had before the press. Worded about what has
        already happened, because that refresh has run by the time the
        reader can read the sentence (the save cue's lesson, above).
        """
        unwritable = self.settled_with(
            '{ok:true, persisted:false, outcome:"unwritable", revision:1, revision_count:1}'
        )
        refused = self.settled_with(
            '{ok:true, persisted:false, outcome:"refused", revision:1, revision_count:1}'
        )
        stored = self.settled_with(
            '{ok:true, persisted:true, outcome:"stored", revision:1, revision_count:1}'
        )

        # The press reached the endpoint with the moment the reader was shown.
        self.assertEqual(104, unwritable["posted"]["settle_through"])
        self.assertTrue(unwritable["open"])
        self.assertEqual(
            "Not settled. The store could not be written, so the mark has already been "
            "dropped and the question below still stands.",
            unwritable["cue"],
        )
        self.assertTrue(refused["open"])
        self.assertEqual(
            "Not settled. The store refused the mark, so the question below still stands as "
            "it did.",
            refused["cue"],
        )
        # A settle that landed says nothing here: the block's own settled
        # sentence is the report, drawn from the store on the next payload.
        self.assertEqual("", stored["cue"])
        # And the cue stays inside the block, so the held fields' cue regexes
        # above still read the field cue and never this one.
        self.assertEqual(0, stored["heldCues"] + unwritable["heldCues"])

    def settled_twice(self, first: str, second: str) -> dict[str, Any]:
        """Press `The baseline still applies` twice against two stubbed
        replies, and read the block the handler's own refresh redrew after
        the second press. The second reply is a settle the store took, and
        the payload comes back settled, which is what a reader sees once one
        lands."""
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + CockpitHeldToTabTest.FOCUS_DOM
            + f"""
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "do not change the board";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";
const upstream = __fetchImpl;
let reply = {first};
__fetchImpl = async (url, init) => {{
  if(String(url) !== "/api/annotate") return upstream(url, init);
  return {{ok:true, status:200, json: async () => reply}};
}};
navigateNext({{view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"}});
await __settle();
const press = () => {{
  const control = controls.find(candidate =>
    candidate.dataset.nextCockpitAction === "conflict-settle");
  if(control) __fire("click", {{target:control, preventDefault(){{}}}});
  return Boolean(control);
}};
const first_pressed = press();
await __settle();
await __settle();
reply = {second};
__dashboard.sessions[0].annotation_settled_at = 200;
__dashboard.sessions[0].annotation_settled_through = 104;
__dashboard.sessions[0].annotation_settled_revision = 1;
const second_pressed = press();
await __settle();
await __settle();
const html = __els.app.innerHTML;
const block = (html.match(
  /<section class="next-cockpit-conflict">[\\s\\S]*?<\\/section>/) || [""])[0];
console.log(JSON.stringify({{
  pressed: [first_pressed, second_pressed],
  cue: (block.match(/class="next-cockpit-conflict-cue">([^<]*)</) || [])[1] || "",
  settled: block.includes("You settled this"),
}}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_a_settle_that_landed_clears_the_cue_the_failed_press_left(self) -> None:
        """DRC-4543 review T1. The failure cue outlived the failure.

        The handler marked the lane on failure and neither marked nor
        cleared it on success, so a cue saying the mark had been dropped sat
        for the lane's whole TTL directly above the block's own `You settled
        this ... ago`. The block then said both that the settlement was not
        stored and that it was, which is the class of lie the settle cue was
        added to remove.
        """
        out = self.settled_twice(
            '{ok:true, persisted:false, outcome:"unwritable", revision:1, revision_count:1}',
            '{ok:true, persisted:true, outcome:"stored", revision:1, revision_count:1}',
        )

        self.assertEqual([True, True], out["pressed"])
        # The second press landed, so the block reads as settled ...
        self.assertTrue(out["settled"])
        # ... and says nothing about a mark that was dropped.
        self.assertEqual("", out["cue"])

    def test_a_later_direction_demotes_a_departure_rather_than_filtering_it(self) -> None:
        open_case = self.held(at=100, assessment=self.ASSESSMENT)
        settled = self.held(
            at=100,
            assessment=self.ASSESSMENT,
            settled="__dashboard.sessions[0].annotation_settled_through = 300;\n"
            "__dashboard.sessions[0].annotation_settled_at = 300;\n"
            "__dashboard.sessions[0].annotation_settled_revision = 1;\n",
        )

        # Demoted in the row, not filtered from the departures list: filtering
        # would leave the word `departure` rendered above it, which is the
        # drift verdict DRC-4511 forbids.
        self.assertEqual("not verifiable from available evidence", open_case["result"])
        self.assertEqual("departure", settled["result"])

    def test_a_settled_baseline_says_when_and_against_which_revision(self) -> None:
        out = self.held(
            at=100,
            settled="__dashboard.sessions[0].annotation_settled_through = 300;\n"
            "__dashboard.sessions[0].annotation_settled_at = 300;\n"
            "__dashboard.sessions[0].annotation_settled_revision = 1;\n",
        )

        block = out["block"]
        assert isinstance(block, str)
        self.assertIn("You settled this", block)
        self.assertIn("against revision 1", block)
        # And it says the question can come back.
        self.assertIn("A direction given after that will raise it again", block)

    def test_nothing_said_since_is_not_the_same_as_nothing_read(self) -> None:
        quiet = self.held(at=200)

        block = quiet["block"]
        assert isinstance(block, str)
        self.assertIn("Nothing you have said since you saved these words", block)
        self.assertNotIn("unknown, not none", block)

    def test_an_unread_record_says_unknown_rather_than_none_and_still_demotes(self) -> None:
        """The three-state distinction the record block already draws.

        The block must not read an unread record as a quiet one. Checked here
        because a reader is owed the difference, and because the review of this
        design asked whether the two halves of the tab could disagree: the
        block saying "unread" while the reading still carried a departure.

        They cannot, and the reason is worth stating rather than assuming. It
        is not this gate. With the context never fetched `entries` is empty, so
        there are no candidates and the baseline gate stays shut; what demotes
        the departure is DEC-17's rule 3, because a citation resolves against
        the entries the page holds and there are none. The gate is for a record
        that WAS read and holds a later direction. Two rules, one outcome, and
        neither is doing the other's job.
        """
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "do not change the board";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_assessment = {revision_read:1, criteria:{
  goal:{result:"departure", detail:"It changed the board.", cites:["fo-a"]}}};
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
// The context never came back, which is the state the record block already
// separates from an empty one.
nextCockpitContexts.clear();
renderNext();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  block: (html.match(/<section class="next-cockpit-conflict">[\\s\\S]*?<\\/section>/) || [""])[0],
  result: (html.match(/class="next-cockpit-reading-result">([^<]*)</) || [])[1] || "",
}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        block = out["block"]
        assert isinstance(block, str)
        self.assertIn("has not been read yet", block)
        self.assertIn("unknown, not none", block)
        # And the departure does not stand on a record nobody read.
        self.assertEqual("not verifiable from available evidence", out["result"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitADiscardLeavesARecordOnTheTabTest(NextPageJsHarness):
    """DRC-4565. The Held to tab after the thirty second cue has lapsed.

    Measured on the walk: the block was character-for-character the block a
    session nobody ever typed against gets -- "No revision saved yet", "No goal
    typed for this session.", "No expected output typed." -- with no cue and no
    control. Three states rendering as two, which is the failure this milestone
    has shipped four times.
    """

    FIXTURE = CockpitHeldToTabTest.FIXTURE
    FOCUS_DOM = CockpitHeldToTabTest.FOCUS_DOM

    # The row exactly as `annotations.published` renders a discard record,
    # written out rather than derived so a change to the store that stopped
    # publishing one of these keys fails a test rather than quietly rendering
    # `undefined`.
    DISCARDED = (
        """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
__dashboard.sessions[0].annotation_at = null;
__dashboard.sessions[0].annotation_binding_why = "";
// Sixty seconds before the fixture's `generated`, which is twice the cue's
// own lifetime: the whole point is what the block says once the cue is gone.
__dashboard.sessions[0].annotation_discarded_at = __dashboard.generated - 60;
"""
        f"__dashboard.sessions[0].annotation_goal_why = "
        f"{json.dumps(annotation_store.DISCARDED_GOAL)};\n"
        f"__dashboard.sessions[0].annotation_output_why = "
        f"{json.dumps(annotation_store.DISCARDED_OUTPUT)};\n"
        f"__dashboard.sessions[0].annotation_discarded_why = "
        f"{json.dumps(annotation_store.DISCARD_RECORD)};\n"
        f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
    )

    # The same session with nothing ever typed against it, which is the block
    # the discarded one must not be mistaken for.
    NEVER = (
        """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
__dashboard.sessions[0].annotation_at = null;
__dashboard.sessions[0].annotation_binding_why = "";
__dashboard.sessions[0].annotation_discarded_at = null;
__dashboard.sessions[0].annotation_discarded_why = "";
"""
        f"__dashboard.sessions[0].annotation_goal_why = "
        f"{json.dumps(annotation_store.NO_GOAL_TYPED)};\n"
        f"__dashboard.sessions[0].annotation_output_why = "
        f"{json.dumps(annotation_store.NO_OUTPUT_TYPED)};\n"
        f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
    )

    OPEN = r"""
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
/* The words' section and the caveats on them, which render below the reading
   since the check moved onto the first screen (DRC-4639). */
const caveatsAt = html.indexOf('<div class="next-session-drift-caveats">');
const held = (html.match(
  /<section class="next-cockpit-held">[\s\S]*?<\/section>/) || [""])[0] +
  (caveatsAt === -1 ? "" :
    html.slice(caveatsAt, html.indexOf('<section class="next-cockpit-departures"', caveatsAt)));
const reading = (html.match(
  /<div class="next-session-drift-check">[\s\S]*?<section class="next-cockpit-reading">[\s\S]*?<\/section>/) || [""])[0];
console.log(JSON.stringify({
  held, reading,
  heldText: held.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim(),
  readingText: reading.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim(),
  /* The whole tab and not the two sections. A contradiction is a property of
     what is on screen together, and the record and the raise that quotes the
     discarded words render in different sections: the test named for that
     property was scraping only the first and could not see the second. */
  pageText: __els.app.innerHTML.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim(),
  ask: (html.match(/data-next-cockpit-action="reading-ask"/g) || []).length,
  discardControl: (html.match(/data-next-cockpit-action="held-discard"/g) || []).length,
}));
"""

    def _open(self, annotation: str, extra: str = "") -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + self.FOCUS_DOM
            + annotation
            + extra
            + self.OPEN,
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_the_block_says_a_discard_happened_and_when(self) -> None:
        """AC5. Long after the cue, on a freshly loaded page."""
        out = self._open(self.DISCARDED)

        text = out["heldText"]
        assert isinstance(text, str)
        self.assertIn(annotation_store.DISCARD_RECORD, text)
        self.assertIn("discarded 1m ago", text)

    def test_the_block_never_reads_as_a_session_nobody_typed_against(self) -> None:
        """AC5's other half, and the one the walk measured: the two blocks were
        the same characters apart from the session id."""
        discarded = self._open(self.DISCARDED)["heldText"]
        never = self._open(self.NEVER)["heldText"]
        assert isinstance(discarded, str)
        assert isinstance(never, str)

        self.assertNotEqual(never, discarded)
        self.assertIn(annotation_store.NO_GOAL_TYPED, never)
        self.assertNotIn(annotation_store.NO_GOAL_TYPED, discarded)
        self.assertNotIn(annotation_store.NO_OUTPUT_TYPED, discarded)
        self.assertIn("No revision saved yet", never)
        self.assertNotIn("No revision saved yet", discarded)
        # And nothing on the never-typed block invents a discard.
        self.assertNotIn(annotation_store.DISCARD_RECORD, never)
        self.assertNotIn("discarded", never)

    def test_the_record_is_not_gated_on_an_offer_to_discard_again(self) -> None:
        """The control is withheld, because `revision_count` is 0 and there is
        nothing left to discard. The ACCOUNT is not: gating it on the offer is
        how the only sentence about a landed discard came to render for the two
        failures alone."""
        out = self._open(self.DISCARDED)

        self.assertEqual(0, out["discardControl"])
        text = out["heldText"]
        assert isinstance(text, str)
        self.assertIn(annotation_store.DISCARD_RECORD, text)

    def test_the_record_and_a_standing_raise_do_not_contradict(self) -> None:
        """AC6. The half-landed discard: `departures.withdraw` failed, so a
        raise below still quotes the words the record says are gone. The walk
        could not force this state; the build owes it a test."""
        standing = """
__dashboard.unasked = true;
__dashboard.sessions[0].departure_checked = true;
__dashboard.sessions[0].departures = [{
  constraint: "TYPED GOAL", clause: "do not change the board while capturing",
  reading: "Two turns edited the running board.", revision: 2,
  at: __dashboard.generated - 600, cutoff: __dashboard.generated - 600,
  cutoff_text: "Read 4 of 4 entries in the observed record.",
  evidence: "turn transcript"}];
"""
        out = self._open(self.DISCARDED, standing)

        text = out["heldText"]
        assert isinstance(text, str)
        self.assertIn(annotation_store.DISCARD_RECORD, text)
        self.assertIn(annotation_store.DISCARD_RECORD_STANDING, text)
        # The property the name claims, read off the whole tab. The raise
        # quotes the discarded clause about twelve hundred characters below the
        # record, in a section this test used not to scrape, so the two
        # sentences above could both be present while the page as a whole said
        # the words were gone and then printed them.
        page = out["pageText"]
        assert isinstance(page, str)
        self.assertIn("do not change the board while capturing", page)
        # "kept here" is what makes the record and the quotation consistent.
        # An unqualified claim is the contradiction, and it is also false about
        # session history, which keeps its own copy of the same two fields.
        self.assertNotIn("None of it is kept:", page)
        self.assertIn("None of it is kept here:", page)

    def test_a_discard_whose_raises_went_says_nothing_about_a_standing_one(self) -> None:
        """The boring outcome. A sentence printed on every discard would be
        the same overclaim in the other direction."""
        out = self._open(self.DISCARDED)

        text = out["heldText"]
        assert isinstance(text, str)
        self.assertNotIn(annotation_store.DISCARD_RECORD_STANDING, text)

    def test_the_reading_block_names_the_discard_rather_than_nothing_typed(self) -> None:
        """AC7. The two states rendered one sentence each, and the claim that
        survives is which sentence: a discarded session says the discard
        sentence and not "nothing typed"."""
        discarded = self._open(self.DISCARDED)
        never = self._open(self.NEVER)

        said = discarded["readingText"]
        absent = never["readingText"]
        assert isinstance(said, str)
        assert isinstance(absent, str)
        self.assertIn(annotation_store.DISCARD_SENTENCES["unreadable"].split(", so")[0], said)
        self.assertNotIn("Nothing has been typed for this session", said)
        self.assertIn("Nothing has been typed for this session", absent)
        # These two read 0 until DRC-4588, under a comment saying the withheld
        # offer was what made the sentence load-bearing rather than decoration.
        # What superseded it: the control now renders refused, with this very
        # sentence bound to it through `aria-describedby`. The sentence is what
        # the control is described BY, so it explains the button rather than
        # competing with it for the reader's attention -- and withholding the
        # button was costing the reader the one affordance the tab exists for
        # in the two states they are most likely to arrive in. The claim above
        # is untouched and is the one AC7 was really making: the discarded row
        # says the discard sentence and not "nothing typed".
        self.assertEqual(1, discarded["ask"])
        self.assertEqual(1, never["ask"])


class CockpitHeldReEntryTest(NextPageJsHarness):
    """DRC-4509 AC4 and DRC-4511 AC3, carried to where DRC-4642 put the way back.

    The route back was always reachable and its limits were not. The Held to
    tab's re-entry block stated them; that tab merged into the session page
    (DRC-4639), and the controls now sit beside each departure with their limits
    said once for the departures section. One session is the whole subject
    there, so a raise that silently does not render would read as "no limit"
    rather than as "not this session".
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    # The capability is read through document.querySelector, not off a payload
    # field, so a test that sets a field measures nothing. Copied from
    # test_next_attention.FOCUS_META_PRELUDE.
    FOCUS_ON = """
document.querySelector = selector => selector === 'meta[name="cargento-focus"]'
  ? {getAttribute: name => (name === "content" ? "0a1b2c3d" : null)}
  : null;
"""

    ANNOTATED = """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "Ship the cockpit";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";
__dashboard.sessions[0].departures = [{constraint:"TYPED GOAL", clause:"Ship the cockpit",
  reading:"It changed the board.", revision:1, at:100, cutoff:100}];
"""

    def render(self, extra: str, *, harness: str = "codex") -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + self.ANNOTATED
            + extra
            + "navigateNext({view:'session', project:'cargento', harness:"
            + json.dumps(harness)
            + ", session:'focus-1'});\n"
            + """
await __settle();
const html = __els.app.innerHTML;
const section = (html.match(
  /<section class="next-cockpit-departures">[\\s\\S]*?<\\/section>/) || [""])[0];
console.log(JSON.stringify({
  note: [...html.matchAll(/class="next-departure-reentry-why"[^>]*>([^<]*)</g)]
    .map(match => match[1]).join(" "),
  rows: (section.match(/data-next-departure-reentry/g) || []).length,
  section,
  offLine: NEXT_FOCUS_OFF_LINE,
}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_a_reachable_terminal_says_so_and_says_what_a_raise_does_not_do(self) -> None:
        out = self.render(
            self.FOCUS_ON
            + "__dashboard.sessions[0].focusable = true;\n"
            + '__dashboard.sessions[0].resume_id = "abc123";\n'
        )
        section = out["section"]
        assert isinstance(section, str)
        # Both controls beside the departure, whatever the session's state.
        self.assertEqual(1, out["rows"])
        self.assertIn('data-next-copy-command="codex resume abc123"', section)
        self.assertIn("data-next-raise-session=", section)
        # A raise is not a window manager, and the hedge matches the one the
        # status line already uses after a raise is sent.
        self.assertIn("its window may still be behind others", out["note"])
        # Nothing is missing, so nothing is said about a missing command.
        self.assertNotIn("re-entry command", out["note"])

    def test_no_reported_terminal_is_a_different_sentence_from_the_run_being_off(self) -> None:
        absent = self.render(self.FOCUS_ON)
        off = self.render("__dashboard.sessions[0].focusable = true;\n")

        # Capability on, this session not focusable: about the session.
        self.assertIn("No terminal was reported for this session", absent["note"])
        self.assertNotIn("off for this run", absent["note"])
        # No capability at all: about the run, in the words Attention uses.
        self.assertIn(off["offLine"], off["note"])
        self.assertNotIn("No terminal was reported", off["note"])
        self.assertEqual("Terminal raise: off for this run.", off["offLine"])

    def test_a_harness_with_no_resume_command_says_so_rather_than_saying_nothing(self) -> None:
        # `pi` is not in NEXT_RESUME_COMMANDS; `codex` is, so an absent id
        # there is a different fact. `nextResumeCommand` collapses both to "".
        never = self.render(
            self.FOCUS_ON + '__dashboard.sessions[0].harness = "pi";\n', harness="pi"
        )
        this_run = self.render(self.FOCUS_ON)

        self.assertIn("publishes no re-entry command", never["note"])
        self.assertIn("no usable id this run", this_run["note"])
        self.assertNotIn("no usable id this run", never["note"])

    def test_every_branch_of_the_way_back_draws_a_different_shape(self) -> None:
        """Three raise branches against two re-entry arms, asserted to DIFFER.

        Carried from the retired re-entry block's matrix, which collapsed twice:
        once by exercising one arm, then by six copies of one arm when the
        capability stub did not answer `getAttribute` as the page reads it.
        Guarding each case cannot see six identical cases, so the six shapes
        are compared to each other.
        """
        cases = {
            "capability-off/no-resume": ("", "pi"),
            "capability-off/resume": ("", "codex"),
            "focusable/no-resume": ("focusable", "pi"),
            "focusable/resume": ("focusable", "codex"),
            "no-terminal/no-resume": ("unfocusable", "pi"),
            "no-terminal/resume": ("unfocusable", "codex"),
        }
        shapes: dict[str, tuple[bool, bool, str]] = {}
        for name, (focus_mode, harness) in cases.items():
            with self.subTest(branch=name):
                setup = f"__dashboard.sessions[0].harness = {json.dumps(harness)};\n"
                setup += '__dashboard.sessions[0].resume_id = "abc123";\n'
                if focus_mode:
                    setup += self.FOCUS_ON + (
                        "__dashboard.sessions[0].focusable = "
                        f"{'true' if focus_mode == 'focusable' else 'false'};\n"
                    )
                out = self.render(setup, harness=harness)
                section = out["section"]
                assert isinstance(section, str)
                shapes[name] = (
                    "data-next-copy-command=" in section,
                    "data-next-raise-session=" in section,
                    str(out["note"]),
                )
                # Every branch says something: a control, a limit, or both.
                self.assertTrue(any(shapes[name][:2]) or shapes[name][2])
        self.assertEqual(6, len(set(shapes.values())), shapes)
        # The resume command follows the harness, never the raise branch.
        for name, shape in shapes.items():
            with self.subTest(resume=name):
                self.assertEqual(name.endswith("/resume"), shape[0])
                self.assertEqual(name.startswith("focusable/"), shape[1])

    def test_a_session_with_no_departure_still_states_reentry_limits(self) -> None:
        out = self.render("__dashboard.sessions[0].departures = [];\n")
        # A missing departure must not hide the session's re-entry limits.
        self.assertIn("Terminal raise: off for this run", out["note"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitRecheckFindingsTest(NextPageJsHarness):
    """The defects Codex found on the verification round of the journey review.

    Every one of these is a surface the review's own fixes created or exposed,
    which is why they are held here rather than folded into the classes that
    hold the nineteen: a fix that introduces a defect is the failure mode the
    re-check exists to catch, and a test filed beside the original finding
    would read as though the original had regressed.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    def test_a_citation_resolves_against_every_entry_not_the_displayed_window(self) -> None:
        """The display bound was silently a citation bound.

        `nextCockpitWorkSource` slices to the newest rows for readability, and
        the same slice was handed to the reading. A departure citing a fact
        older than the window therefore stopped resolving as the session grew,
        was demoted to `not verifiable`, and the block then printed "The
        reading raised no departure from the revision it read" about a
        departure the payload still held.
        """
        out = self.run_fixture(
            """
const old = {id:"cited-early", type:"user_message", by:"", source:"root transcript · exact"};
const filler = Array.from({length: NEXT_COCKPIT_WORK_ROWS + 1}, (_, i) =>
  ({id:`later-${i}`, type:"result", by:"", source:"dispatch artifact · exact"}));
const all = [old, ...filler];
const window = all.slice(-NEXT_COCKPIT_WORK_ROWS);
const annotation = {goal:"do not change the board", output:"six screenshots"};
const reading = {criteria:{goal:{result:"departure", detail:"It changed the board.",
  cites:["cited-early"]}}};
console.log(JSON.stringify({
  windowed: nextCockpitReadingShape(reading, annotation, window, "").departures.length,
  full: nextCockpitReadingShape(reading, annotation, all, "").departures.length,
  // The window is genuinely smaller, so the test is not asserting on a slice
  // that happens to hold everything.
  windowHolds: window.some(entry => entry.id === "cited-early"),
}));
"""
        )
        assert isinstance(out, dict)
        self.assertFalse(out["windowHolds"])
        self.assertEqual(1, out["full"])
        # The point of the fix is upstream of this function: the shape is
        # correct for whatever it is given, and the caller must give it all.
        self.assertEqual(0, out["windowed"])

    def test_the_work_source_publishes_the_full_set_beside_the_displayed_one(self) -> None:
        """The caller's half of the citation fix."""
        out = self.run_fixture(
            """
const facts = Array.from({length: NEXT_COCKPIT_WORK_ROWS + 5}, (_, i) => ({
  fact_id:`f-${i}`, at:100 + i, type:"result", summary:`row ${i}`,
  source_session:{harness:"codex", sid:"focus-1"},
  evidence:{source:"dispatch artifact", confidence:"exact"}}));
const group = nextProjectGroups().find(candidate => candidate.label === "cargento");
const session = group.sessions.find(row => row.sid === "focus-1");
nextCockpitContexts.set(nextCockpitContextKey(group, session),
  {data:{semantic:{facts, projections:{}}}});
const source = nextCockpitWorkSource(group, session);
console.log(JSON.stringify({
  shown: source.entries.length,
  all: source.all.length,
  total: source.total,
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(20, out["shown"])
        self.assertEqual(25, out["all"])
        self.assertEqual(25, out["total"])

    def test_the_rendered_tab_resolves_a_citation_older_than_the_window(self) -> None:
        """The caller's half, walked the way a reader meets it.

        The two halves fail independently: the shape can be correct for what
        it is given while the tab hands it the twenty rows it draws, which is
        what a session simply has to outgrow. So this renders the real tab
        against a session with more facts than the window and a reading that
        cites the oldest of them.
        """
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + CockpitHeldToTabTest.FOCUS_DOM
            + """
const older = Array.from({length: NEXT_COCKPIT_WORK_ROWS + 4}, (_, i) => ({
  fact_id:`later-${i}`, at:200 + i, type:"result", summary:`row ${i}`,
  source_session:{harness:"codex", sid:"focus-1"},
  evidence:{source:"dispatch artifact", confidence:"exact"}}));
__semantic.facts = [
  {fact_id:"cited-early", at:1, type:"user_message", summary:"Do not change the board",
   source_session:{harness:"codex", sid:"focus-1"},
   evidence:{source:"root transcript", confidence:"exact"}},
  ...older,
];
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "do not change the board";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";
__dashboard.sessions[0].annotation_assessment = {revision_read:1, criteria:{
  goal:{result:"departure", detail:"It changed the board.", cites:["cited-early"]}}};
await refreshNext();
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
await __settle();
const html = __els.app.innerHTML;
const departures = (html.match(
  /<section class="next-cockpit-departures">[\\s\\S]*?<\\/section>/) || [""])[0];
console.log(JSON.stringify({
  departures,
  // The cited fact really is outside the drawn window, or this proves nothing.
  windowed: html.includes("Showing the 20 most recent of 25 observed entries."),
  citedRowDrawn: html.includes("Zeta the earliest direction"),
}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        self.assertTrue(out["windowed"])
        self.assertFalse(out["citedRowDrawn"])
        self.assertIn("It changed the board.", out["departures"])
        self.assertNotIn("raised no departure", out["departures"])

    def test_a_turn_stop_withholds_a_reading_and_says_why(self) -> None:
        """Replaces the qualifier test. The ruling changed underneath it.

        The captain ruled on 2026-09-10 that an ending with no supported end
        evidence gets NO reading at all -- not a provisional one. A turn stop
        is not a session end, so the producer withholds and the page renders
        the reason it chose from a closed set. This used to render a full
        reading with "This covers only the work so far" appended, which is
        exactly the provisional reading the ruling refuses.

        A RUNNING session is a different thing and keeps its reading: it
        claims no finality, so there is nothing to withhold.
        """
        out = self.run_fixture(
            """
const session = {harness:"codex", sid:"focus-1", state:"idle"};
const model = {enabled:true};
const entries = [{id:"u1", type:"user_message", by:"", source:"root transcript · exact"}];
const withheld = {goal:"do not change the board", revision:1, reading_count:1,
  reading_withheld:"A turn stop was observed and no session end was, so there is no end " +
    "for a reading to rest on. Nothing partial is offered instead."};
// The lane on, so the departures section draws and says no reading was made.
nextData.unasked = true;
const html = nextCockpitReading(session, withheld, entries, model, null, false,
  {state:"read", entries:entries});
console.log(JSON.stringify({
  html,
  says: html.includes("no end for a reading to rest on"),
  // No verdict of any kind: the result element is the only place the three
  // sentences can appear.
  results: (html.match(/class="next-cockpit-reading-result"/g) || []).length,
  // The control stays on the page, so the reader can ask again.
  control: html.includes('data-next-cockpit-action="reading-ask"'),
  count: html.includes("1 model request recorded"),
  // And the departures block says no reading was made, rather than that a
  // reading raised nothing.
  noReading: html.includes("No reading has been made"),
  noDeparture: html.includes("raised no departure"),
  // The landing axis is untouched: this narrows what the READING does and
  // must not quietly rewrite what HOW IT LANDED says.
  landing: {
    stop: nextObservedLanding({state:"idle", harness:"codex"}, false, true),
    end: nextObservedLanding({state:"idle", harness:"codex"}, true, false),
  },
}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["says"])
        self.assertEqual(0, out["results"], "a withheld reading drew a verdict")
        self.assertTrue(out["control"], "the reader cannot ask again")
        self.assertTrue(out["count"], "the press that produced nothing was not counted")
        self.assertTrue(out["noReading"])
        self.assertFalse(out["noDeparture"], "a withheld reading claimed nothing departed")
        self.assertTrue(out["landing"]["stop"]["endKnown"])
        self.assertTrue(out["landing"]["end"]["endKnown"])

    def test_a_derived_snapshot_of_the_goal_is_not_counted_as_observed_work(self) -> None:
        """Finding S's other half, which the fix for it created.

        `modelDerived` is `actor_claim` starting `model-derived`, and
        `_OBSERVER_ACTOR_CLAIMS` publishes two other strings for the same kind
        of row: a deterministic derivation and one whose derivation was never
        recorded. Both are paraphrases of the goal, and both fell into the
        bucket the line calls "observed of what it did".
        """
        out = self.run_fixture(
            """
const mix = entries => nextCockpitWorkMix(entries);
console.log(JSON.stringify({
  deterministic: mix([{type:"observer_snapshot", by:"",
    actorClaim:"deterministically derived observer snapshot", modelDerived:false}]),
  unrecorded: mix([{type:"observer_snapshot", by:"",
    actorClaim:"observer snapshot, derivation not recorded", modelDerived:false}]),
  model: mix([{type:"observer_snapshot", by:"",
    actorClaim:"model-derived observer snapshot", modelDerived:true}]),
  // A person's gate decision is a direction, and rule 7 already says so.
  gate: mix([{type:"gate_decision", by:"person:captain", modelDerived:false}]),
  work: mix([{type:"result", by:"", modelDerived:false}]),
}));
"""
        )
        assert isinstance(out, dict)
        # The zero is stated rather than dropped: "0 observed of what it did"
        # beside a count of directions is the sentence finding S asked for,
        # and hiding it would put the reader back where they started.
        for case in ("deterministic", "unrecorded", "model"):
            with self.subTest(case=case):
                self.assertIn("0 observed of what it did", out[case])
        self.assertIn("derived summary of this session", out["deterministic"])
        self.assertIn("derived summary of this session", out["unrecorded"])
        self.assertIn("1 model-derived", out["model"])
        self.assertIn("1 direction you gave", out["gate"])
        self.assertIn("0 observed of what it did", out["gate"])
        self.assertIn("1 observed of what it did", out["work"])

    def test_the_board_explaining_a_missing_clause_does_not_wear_the_readers_register(
        self,
    ) -> None:
        """The stylesheet states the rule this violated, two lines above it.

        `.next-cockpit-reading-clause` is mono because it holds words a person
        typed. The fallback sentence is the board saying those words were not
        retained, and it was rendered into the same span, so the explanation
        looked like the quotation it was standing in for. `clauseKnown` was
        computed for exactly this and never read.
        """
        out = self.run_fixture(
            """
const row = clause => nextCockpitReadingCriterionRow(nextCockpitReadingCriterion(
  "goal", "TYPED GOAL", clause, {result:"consistent with the evidence read", cites:["u1"]},
  [{id:"u1", type:"user_message", by:"", source:"root transcript · exact"}], ""));
console.log(JSON.stringify({
  known: row("do not change the board"),
  absent: row(""),
}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn('class="next-cockpit-reading-clause"', out["known"])
        self.assertIn("do not change the board", out["known"])
        self.assertIn("are not retained", out["absent"])
        self.assertNotIn('class="next-cockpit-reading-clause"', out["absent"])
        self.assertIn("next-cockpit-reading-clause-absent", out["absent"])

    def test_a_reading_with_no_departure_still_states_its_cutoff(self) -> None:
        """The cutoff was rendered inside a departure row and nowhere else.

        A reading that raised nothing is exactly the one whose cutoff a reader
        needs, because "nothing was raised" is only worth as much as the
        evidence it was raised against.
        """
        out = self.run_fixture(
            """
const shape = departures => ({departures, cutoff:"read to 2026-09-10T04:00Z",
  criteria:[], revisionRead:1, stamp:""});
console.log(JSON.stringify({
  none: nextCockpitDepartures(shape([])),
  one: nextCockpitDepartures(shape([{label:"TYPED GOAL", clause:"c", clauseKnown:true,
    detail:"It drifted.", result:"departure", evidence:["user_message · root transcript"]}])),
}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("read to 2026-09-10T04:00Z", out["none"])
        self.assertIn("raised no departure", out["none"])
        self.assertIn("read to 2026-09-10T04:00Z", out["one"])
        # Once per block, not once per row: the cutoff is a property of the
        # reading, and repeating it beside every departure said one fact twice.
        self.assertEqual(1, out["one"].count("read to 2026-09-10T04:00Z"))

    def test_two_sessions_a_reader_cannot_tell_apart_are_labelled_apart(self) -> None:
        """Finding Q's remainder: the scope rail is how a reader reaches one.

        Same harness, same state, same title renders byte-identical rows. The
        session key is in the href and in a data attribute, neither of which
        is on screen, so the reader picks one of two indistinguishable links
        and finds out which by reading the tab that opens.
        """
        out = self.run_fixture(
            """
const group = {label:"cargento", sessions:[
  {harness:"codex", sid:"twin-a", state:"working", title:"Shape project cockpit"},
  {harness:"codex", sid:"twin-b", state:"working", title:"Shape project cockpit"},
  {harness:"claude", sid:"alone", state:"idle", title:"Only one of these"}
]};
const html = nextCockpitScopeLinks(group, null);
// Only what a reader can see: the href and the data attributes carry the
// session key already, and asserting on those passes without the fix.
const visible = html.replace(/<[^>]*>/g, "\\n");
console.log(JSON.stringify({visible, rows: html.split("</a>").length - 1}));
"""
        )
        assert isinstance(out, dict)
        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertEqual(4, out["rows"])
        self.assertIn("twin-a", visible)
        self.assertIn("twin-b", visible)
        # The session nothing can be confused with is not made noisier for it.
        self.assertNotIn("alone", visible)

    def test_scope_links_order_working_sessions_above_idle_with_live_indicators(self) -> None:
        """Working sessions show below the project line but above idle sessions with a pulsing dot."""
        out = self.run_fixture(
            r"""
const group = {label:"cargento", sessions:[
  {harness:"claude", sid:"c1", state:"idle", title:"Idle Claude session 1"},
  {harness:"claude", sid:"c2", state:"idle", title:"Idle Claude session 2"},
  {harness:"codex", sid:"w1", state:"working", title:"Working Codex session", tone:"want"},
  {harness:"codex", sid:"i1", state:"idle", title:"Idle Codex session"}
]};
const html = nextCockpitScopeLinks(group, null);
const links = Array.from(html.matchAll(/<a\s+([^>]+)>([\s\S]*?)<\/a>/g)).map(m => {
  const attrs = m[1];
  const body = m[2];
  const scope = (attrs.match(/data-next-cockpit-scope="([^"]+)"/) || [])[1];
  const kind = (attrs.match(/data-scope-kind="([^"]+)"/) || [])[1];
  const working = (attrs.match(/data-next-working="([^"]+)"/) || [])[1] || null;
  const hasDot = body.includes("next-project-dot--working");
  const dotTone = (body.match(/next-project-tone--(\w+)/) || [])[1] || null;
  // Read out of the meta line rather than from whatever follows it. The old
  // form required the state span to abut a <small>, which yielded "" into an
  // assertEqual the moment the card changed shape.
  const metaAt = body.indexOf('class="next-cockpit-scope-meta">');
  const meta = metaAt < 0 ? "" : body.slice(body.indexOf(">", metaAt) + 1);
  const stateAt = meta.indexOf('class="next-cockpit-scope-state');
  const state = stateAt < 0 ? "" : meta.slice(meta.indexOf(">", stateAt) + 1)
    .replace(/<[^>]+>/g, "").split("\u00b7")[0].trim();
  return {scope, kind, working, hasDot, dotTone, state};
});
console.log(JSON.stringify({scopes: links}));
"""
        )
        assert isinstance(out, dict)
        scopes = out["scopes"]
        self.assertEqual(5, len(scopes))
        self.assertEqual("project", scopes[0]["scope"])
        self.assertEqual("project", scopes[0]["kind"])
        self.assertEqual("codex:w1", scopes[1]["scope"])
        self.assertEqual("session", scopes[1]["kind"])
        self.assertEqual("true", scopes[1]["working"])
        self.assertTrue(scopes[1]["hasDot"])
        self.assertEqual("want", scopes[1]["dotTone"])
        self.assertEqual("working", scopes[1]["state"])
        for idle in scopes[2:]:
            self.assertEqual("session", idle["kind"])
            self.assertIsNone(idle["working"])
            self.assertFalse(idle["hasDot"])
            self.assertEqual("idle", idle["state"])

    def test_the_absence_sentence_goes_as_soon_as_the_box_stops_being_empty(self) -> None:
        """Finding L's remainder, in the one lane that does not redraw.

        The renderer already drops "No expected output typed." once a draft
        exists, and a comment above it says so. But a keystroke deliberately
        does not redraw, and the handler updated the counter and the two
        controls and nothing else, so the sentence sat under the reader's own
        half-typed words until something unrelated forced a replacement.
        """
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + CockpitHeldToTabTest.FOCUS_DOM
            + CockpitHeldToTabTest.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const input = controls.find(control => control.dataset.nextCockpitHeldKind === "output");
const field = input.closest("[data-next-cockpit-held-field]");
const absent = () => field.querySelector("[data-next-cockpit-held-absent]");
const before = {text: absent() && absent().textContent, hidden: absent() && absent().hidden};
const before_renders = __els.renders;
input.value = "Six screen";
__fire("input", {target:input});
await __settle();
const typing = {hidden: absent().hidden, redraws: __els.renders - before_renders};
// And back, because a reader who deletes what they typed is owed the answer
// to "why is this empty" again.
input.value = "";
__fire("input", {target:input});
await __settle();
console.log(JSON.stringify({before, typing, cleared: absent().hidden}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        self.assertEqual("No expected output typed.", out["before"]["text"])
        self.assertFalse(out["before"]["hidden"])
        self.assertTrue(out["typing"]["hidden"])
        # In place, not by redrawing: the redraw is the defect this lane was
        # built to avoid, and hiding the paragraph must not reintroduce it.
        self.assertEqual(0, out["typing"]["redraws"])
        self.assertFalse(out["cleared"])

    def test_a_session_the_fact_scan_skipped_is_unread_rather_than_empty(self) -> None:
        """Finding C's remainder: the state read the wrong scan's coverage.

        `sources.work.omitted` names the sessions bounded out of the scan that
        produces these facts, at MAX_PROJECT_OBSERVERS. The block consulted
        `command_attention_coverage` instead, which is a different sweep over
        active sessions' final output, capped at 64. A session omitted from
        the first is almost never omitted from the second, so the state
        resolved to "empty" for exactly the sessions it was written for, and
        the board said "No entry in the observed record names this session"
        about a session it had never read.
        """
        out = self._run_page_js(
            """await __settle();
await __settle();
const group = nextProjectGroups().find(candidate => candidate.label === "cargento");
const session = group.sessions.find(row => row.sid === "focus-1");
const probe = sources => {
  nextCockpitContexts.set(nextCockpitContextKey(group, session),
    {data:{semantic:{facts:[], projections:{command_attention_coverage:
      {scanned:64, total:64, omitted:0}}}, sources}});
  const source = nextCockpitWorkSource(group, session);
  return {state: source.state, absence: nextCockpitWorkAbsence(source)};
};
console.log(JSON.stringify({
  omitted: probe({observer:{live:3}, work:{omitted:[
    {harness:"codex", sid:"focus-1"}, {harness:"pi", sid:"pi-idle"}]}}),
  scanned: probe({observer:{live:3}, work:{omitted:[{harness:"pi", sid:"pi-idle"}]}}),
  // The wrong scan says nothing was left out, and used to be the only voice.
  noSources: probe(undefined),
}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        self.assertEqual("partial", out["omitted"]["state"])
        self.assertIn("outside the observed-record scan", out["omitted"]["absence"])
        self.assertEqual("empty", out["scanned"]["state"])
        self.assertEqual(
            "No entry in the observed record names this session.", out["scanned"]["absence"]
        )
        self.assertEqual("empty", out["noSources"]["state"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitHeldDraftSurvivesAnUnwritableStoreTest(NextPageJsHarness):
    """Finding A's remainder: `persisted:false` still destroyed the words.

    `annotations.annotate` sets `state.annotations` before it writes, so an
    unwritable store leaves the revision in this process only. Every
    collection calls `annotation_store.refresh`, which reloads the file and
    drops it, and the save handler calls `refreshNext()` on the next line. So
    the cue promising the words would be "gone at the next refresh" was
    describing a refresh the page had already started, after it had dropped
    the draft that was the only remaining copy.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    def test_an_unpersisted_save_keeps_the_draft_and_a_persisted_one_clears_it(self) -> None:
        out = self.run_fixture(
            """
const key = nextCockpitHeldKey({harness:"codex", sid:"focus-1"}, "goal");
const attempt = async persisted => {
  nextCockpitHeldDrafts.set(key, "hold it to what I asked");
  // Only the annotate call answers; the refresh the handler starts next is
  // left to fail into refreshNext's own catch, so this test measures the save
  // path rather than a payload it would have to invent.
  __fetchImpl = url => String(url).includes("/api/annotate")
    ? Promise.resolve({ok:true, json: async () => ({ok:true, persisted})})
    : Promise.resolve({ok:false, status:503, json: async () => ({})});
  await nextCockpitHeldSave({harness:"codex", sid:"focus-1"}, "goal");
  return {
    kept: nextCockpitHeldDrafts.has(key),
    draft: nextCockpitHeldDrafts.get(key) || "",
    cue: nextCockpitHeldCue(key),
  };
};
const unpersisted = await attempt(false);
const persisted = await attempt(true);
console.log(JSON.stringify({unpersisted, persisted}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["unpersisted"]["kept"])
        self.assertEqual("hold it to what I asked", out["unpersisted"]["draft"])
        self.assertIn("still in the box", out["unpersisted"]["cue"])
        self.assertFalse(out["persisted"]["kept"])
        self.assertEqual("Saved as a new revision.", out["persisted"]["cue"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class AStoreRefusedReadingIsNotAnUnpressedSessionTest(NextPageJsHarness):
    """DRC-4545's second half, on the block that renders both sentences.

    `readings` survives a reading `_assessment` refuses whole, so the block
    said "1 reading asked for on this session" above "No reading has been
    made, so nothing has been raised" with no account of the difference.
    """

    # Its own runner rather than a subclass of a concrete test case: inheriting
    # that class re-ran its hundred and twelve tests under this name.
    FIXTURE = NextCockpitCompositionTest.FIXTURE

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    def test_the_block_names_the_refusal_rather_than_offering_a_first_press(self) -> None:
        out = self.run_fixture(
            """
const session = {harness:"codex", sid:"focus-1", state:"idle"};
const model = {enabled:true};
const annotation = {goal:"ship it", output:"", revision:1, revision_count:1, at:100,
  reading_count:1, reading_refused:true, assessment:null};
const html = nextCockpitReading(session, annotation, [], model, null, false,
  {state:"read", entries:[]});
console.log(JSON.stringify({
  html,
  names: html.includes("could not read it, so nothing from it is shown"),
  count: html.includes("1 model request recorded"),
}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["names"], out["html"])
        self.assertTrue(out["count"])

    def test_a_session_nobody_pressed_on_is_not_told_a_reading_was_refused(self) -> None:
        out = self.run_fixture(
            """
const session = {harness:"codex", sid:"focus-1", state:"idle"};
const model = {enabled:true};
const annotation = {goal:"ship it", output:"", revision:1, revision_count:1, at:100,
  reading_count:0, reading_refused:false, assessment:null};
const html = nextCockpitReading(session, annotation, [], model, null, false,
  {state:"read", entries:[]});
console.log(JSON.stringify({html, names: html.includes("could not read it")}));
"""
        )
        assert isinstance(out, dict)
        self.assertFalse(out["names"], out["html"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitDepartureReviewTest(NextPageJsHarness):
    """DRC-4514: what was raised while you were away, where you review it.

    The section titled DEPARTURES RAISED TO YOU used to show only the departures
    of a reader-requested reading, which is a collection nothing on a shipped
    board can produce. The departures actually raised to the reader — the unasked
    lane's — appeared one route away on the session page and nowhere here. What
    is asserted below is the rendered sentence, and where two surfaces show one
    fact, that they render the same characters.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    DEPARTURE = (
        '{constraint:"TYPED GOAL", clause:"do not change the board while capturing",'
        ' reading:"Two turns edited the running board\'s markup between captures.",'
        ' evidence:"turn transcript · Codex", revision:2, cutoff:100, at:101,'
        ' follow_up:"No later check has read this session, so what happened after this '
        'raise is not recorded here."}'
    )

    def review(self, setup: str) -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "__dashboard.annotate = true;\n__dashboard.annotate_cap = 240;\n"
            + setup
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
const block = (html.match(
  /<section class="next-cockpit-departures">[\\s\\S]*?<\\/section>/) || [""])[0];
console.log(JSON.stringify({
  html, block,
  visible: block.replace(/<[^>]*>/g, " ").replace(/\\s+/g, " ").trim(),
  shared: nextUnaskedDepartureBody(__dashboard.sessions[0]),
  onSession: nextSessionView("cargento", "codex", "focus-1"),
}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_a_raised_departure_is_reachable_from_the_section_that_names_them(self) -> None:
        out = self.review(
            f"__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertIn("TYPED GOAL", out["visible"])
        self.assertIn("do not change the board while capturing", out["visible"])
        self.assertIn("Two turns edited the running board", out["visible"])
        self.assertIn("read against revision 2", out["visible"])
        self.assertIn("evidence to", out["visible"])
        # The sentence the section used to print over two standing departures.
        self.assertNotIn("No reading has been made, so nothing has been raised.", out["html"])

    def test_a_raised_departure_renders_cutoff_text_when_present(self) -> None:
        """DRC-4562. The producer's account of how far evidence went is rendered
        beside the evidence line on departure rows."""
        departure_with_cutoff = (
            '{constraint:"TYPED GOAL", clause:"keep tests green",'
            ' reading:"Test failed.",'
            ' evidence:"tests/test_foo.py", revision:1, cutoff:100, at:101,'
            ' cutoff_text:"Read 14 entries, 9 of them the session\'s own account",'
            ' follow_up:""}'
        )
        out = self.review(
            "__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{departure_with_cutoff}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )
        self.assertIn("Read 14 entries", out["visible"])
        self.assertIn("9 of them the session", out["visible"])

    def test_a_raise_whose_baseline_did_not_survive_says_so_here_too(self) -> None:
        out = self.review(
            "__dashboard.unasked = true;\n"
            '__dashboard.sessions[0].departures = [{constraint:"TYPED GOAL", clause:"",'
            ' reading:"went elsewhere", evidence:"", revision:0, cutoff:0, at:101,'
            ' follow_up:""}];\n'
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertIn("the revision it read is not on record", out["visible"])
        self.assertIn("the evidence window is not on record", out["visible"])

    def test_the_switch_is_what_decides_whether_anything_watches(self) -> None:
        """AC1b. The claim was unconditional and false under the switch."""
        on = self.review(
            f"__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )
        # Off, with a raise standing: the one lane-off state that draws the section.
        off = self.review(
            "delete __dashboard.unasked;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertIn("Nothing watches for a departure on its own", off["visible"])
        self.assertNotIn("Nothing watches for a departure on its own", on["visible"])

    def test_the_lane_off_says_the_record_stands_beside_the_rows_it_stands_on(self) -> None:
        """DRC-4559. Off is a fact about the flag, not about the record."""
        out = self.review(
            "delete __dashboard.unasked;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertIn(
            "The checks that run while you were away are off for this run, so nothing new "
            "is being checked. What was already raised is still on record.",
            out["visible"],
        )
        # The rows themselves, and the standing sentence about the present
        # beside them rather than instead of them.
        self.assertIn("TYPED GOAL", out["visible"])
        self.assertIn("do not change the board while capturing", out["visible"])
        self.assertIn("Nothing watches for a departure on its own", out["visible"])

    def test_the_lane_off_figure_counts_the_rows_it_drew_and_never_an_empty_list(self) -> None:
        """The first Measured Invariant, on the branch this issue adds.

        A length read off `session.departures` is a number on every row,
        because `base_session` declares the list empty on all of them. Only a
        list with something in it is a measurement.
        """
        drawn = self.review(
            "delete __dashboard.unasked;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        values = re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', drawn["block"])
        self.assertEqual(["not published", "1", "3", "3", "2"], values)

    def test_a_check_with_no_words_behind_it_renders_the_never_checked_sentence(self) -> None:
        """DRC-4560, the rendered half, against the producer's own constants.

        The producer choice is asserted in `test_unasked` and at the
        `/api/annotations` boundary; this is the other half — that the sentence
        the producer picks is the sentence the tab prints, and that the
        contradicting one is nowhere on the screen. Injected from the Python
        constants rather than retyped, so the two cannot drift.
        """
        out = self.review(
            "__dashboard.unasked = true;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            "__dashboard.sessions[0].departures = [];\n"
            "__dashboard.sessions[0].departure_checked = false;\n"
            '__dashboard.sessions[0].annotation_goal = "";\n'
            "__dashboard.sessions[0].annotation_goal_why = "
            f"{json.dumps('No goal typed for this session.')};\n"
            "__dashboard.sessions[0].departure_why = "
            f"{json.dumps(departures.NEVER_CHECKED)};\n"
        )

        self.assertIn(departures.NEVER_CHECKED, out["visible"])
        self.assertNotIn(departures.NOTHING_DEPARTED, out["visible"])
        # And no figure beside a sentence saying nothing was read.
        values = re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', out["block"])
        self.assertEqual(["not published", "not published", "3", "3", "2"], values)

    def test_a_raise_read_against_a_superseded_revision_says_so_here_too(self) -> None:
        """DRC-4563. The comparison the reading block makes inches above these rows.

        The second half re-asserts the one-body invariant under the new
        setup: the current revision has to be read from the session row inside
        the shared function, because a value handed in by either caller would
        let the two surfaces print different characters.
        """
        out = self.review(
            "__dashboard.unasked = true;\n"
            "__dashboard.sessions[0].annotation_revision = 3;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertIn(
            "This raise read revision 2. Revision 3 is current, so it does not describe "
            "what you are asking for now.",
            out["visible"],
        )
        # The needle binds: an empty shared body would satisfy the two
        # substring checks below without either surface rendering a row.
        self.assertIn("TYPED GOAL", out["shared"])
        self.assertIn(out["shared"], out["block"])
        self.assertIn(out["shared"], out["onSession"])

    def test_the_two_surfaces_print_the_same_characters_for_one_raise(self) -> None:
        """AC1c. One body, two frames, rather than two renderings of one fact."""
        out = self.review(
            f"__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertIn("TYPED GOAL", out["shared"])
        self.assertIn(out["shared"], out["block"])
        self.assertIn(out["shared"], out["onSession"])

    def test_each_of_the_four_absence_sentences_is_printed_verbatim(self) -> None:
        """AC1c. A spent cap must not be worded one way here and another there."""
        for sentence in (
            (
                "Cargento has not checked this session against what you asked for. Nothing "
                "here says whether it would have found anything."
            ),
            (
                "Cargento has checked this session against what you asked for and found "
                "nothing to raise."
            ),
            (
                "This session has reached its limit of unasked checks, so no further check "
                "will run on it. That is a limit being spent, not a session found to be on "
                "track."
            ),
            (
                "This board has reached its limit of unasked checks for the day, so no "
                "further check will run on any session. That is a limit being spent, not a "
                "board found to be on track."
            ),
        ):
            with self.subTest(sentence=sentence[:32]):
                out = self.review(
                    "__dashboard.unasked = true;\n"
                    "__dashboard.sessions[0].departures = [];\n"
                    f"__dashboard.sessions[0].departure_why = {json.dumps(sentence)};\n"
                )

                self.assertIn(sentence, out["visible"])
                self.assertIn(out["shared"], out["onSession"])

    def test_delivery_renders_beside_the_departure_it_is_about(self) -> None:
        """AC1d. A raise and what became of it were two blocks and two counts."""
        out = self.review(
            f"__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
            "__dashboard.sessions[0].delivery_departure = {delivery_raises: 2,"
            ' delivery_outcome: "handed-over",'
            " delivery_why: \"Handed to this machine's notification service, which accepted"
            ' it.", delivery_mixed: true, delivery_mixed_why: "Earlier raises about this '
            'session did not all end the same way as this one.",'
            ' delivery_binding_why: "Matched on an eight-character identity prefix.",'
            ' browser_lane_why: "No dashboard tab has reported a notification lane."};\n'
        )

        self.assertIn("which accepted it.", out["visible"])
        self.assertIn("did not all end the same way", out["visible"])
        self.assertIn("eight-character identity prefix", out["visible"])
        self.assertIn("No dashboard tab has reported a notification lane.", out["visible"])
        # And the page adds no verdict of its own beside the sentences it got.
        self.assertNotIn("you saw", out["block"])

    def test_a_departure_with_no_raise_on_record_says_so_rather_than_nothing(self) -> None:
        """AC1d. Silence there reads as a raise the reader ignored."""
        out = self.review(
            f"__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
            "__dashboard.sessions[0].delivery_departure = {delivery_raises: 0,"
            ' delivery_none_why: "No notification raise about this session is on record, so '
            'nothing here says one was attempted."};\n'
        )

        self.assertIn("No notification raise about this session is on record", out["visible"])

    def test_no_row_turns_the_board_wide_lane_flag_into_a_claim_about_it(self) -> None:
        """AC1e. `browser_lane` is board-wide; only its per-raise sentence rides."""
        out = self.review(
            f"__dashboard.unasked = true;\n"
            "__dashboard.browser_lane = false;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
            "__dashboard.sessions[0].delivery_departure = {delivery_raises: 1,"
            ' delivery_outcome: "no-lane", delivery_why: "This platform has no notification '
            'backend in this build.", browser_lane_why: "No dashboard tab has reported a '
            "notification lane. A tab that opens sends a report and a tab that closes sends "
            'none, so this says nothing about whether the page raised one."};\n'
        )

        self.assertIn("so this says nothing about whether the page raised one.", out["visible"])
        # Nothing stronger, and nothing about this session's own lane.
        self.assertNotIn("no notification lane in this browser", out["visible"].lower())

    def test_the_counts_are_labelled_lines_and_never_a_ratio(self) -> None:
        """AC4. Twelve quiet checks and two raises is a departure figure of two."""
        out = self.review(
            f"__dashboard.unasked = true;\n"
            "__dashboard.delivery_counts = {raises: 2, attempted: 2, handed_over: 1};\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE},"
            ' {constraint:"EXPECTED OUTPUT", clause:"", reading:"and again", evidence:"",'
            ' revision:2, cutoff:100, at:102, follow_up:""}];\n'
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        values = re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', out["block"])
        self.assertEqual(["not published", "2", "2", "2", "1"], values)
        # No ratio, no percentage, and no further figure composed from these.
        self.assertNotIn("%", out["visible"])
        self.assertNotIn(" of 2", out["visible"])

    def test_a_figure_the_payload_does_not_carry_states_its_absence(self) -> None:
        # The shared contract's first rule: never a zero standing in for a
        # number nobody published.
        out = self.review(
            f"__dashboard.unasked = true;\n"
            "__dashboard.delivery_counts = {raises: 3};\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        values = re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', out["block"])
        self.assertEqual(["not published", "1", "3", "not published", "not published"], values)

    def test_the_departure_figure_is_absent_rather_than_zero_when_nothing_watches(self) -> None:
        """The one figure that was exempt from the rule the test above states.

        `base_session` declares `departures` at `[]` on every row whether or not
        the lane ran, so a length read off it is always a number. Measured on a
        default board: "Departures raised about this session 0" printed directly
        under "Nothing watches for a departure on its own".
        """
        out = self.review(
            "delete __dashboard.unasked;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
        )

        # Since the DRC-4543 ruling was restored on the session page, nothing on record with
        # the switch off draws no section at all, so no figure of any kind can stand in for one.
        self.assertEqual("", out["block"])
        self.assertNotIn("next-cockpit-count-value", out["html"])
        self.assertNotIn("raised 0", out["html"])

    def test_a_session_the_lane_never_read_gets_no_departure_figure(self) -> None:
        """The same rule as the lane-off case, one layer in.

        Walked on a board with the switch on and this session never checked:
        "Departures the checks run while you were away raised 0" printed four
        lines under "Cargento has not checked this session against what you
        asked for". Both sentences were about the same session and only one of
        them was a measurement.
        """
        out = self.review(
            "__dashboard.unasked = true;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            "__dashboard.sessions[0].departures = [];\n"
            "__dashboard.sessions[0].departure_checked = false;\n"
            '__dashboard.sessions[0].departure_why = "Cargento has not checked this session '
            "against what you asked for. Nothing here says whether it would have found "
            'anything.";\n'
        )

        values = re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', out["block"])
        self.assertEqual(["not published", "not published", "3", "3", "2"], values)
        self.assertIn("Cargento has not checked this session", out["visible"])
        self.assertNotIn("Departures the checks run while you were away raised 0", out["visible"])

    def test_a_session_the_lane_read_and_found_nothing_in_gets_a_zero(self) -> None:
        """The case where the figure is a measurement, and 0 is the right one."""
        out = self.review(
            "__dashboard.unasked = true;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            "__dashboard.sessions[0].departures = [];\n"
            "__dashboard.sessions[0].departure_checked = true;\n"
            '__dashboard.sessions[0].departure_why = "Cargento has checked this session '
            'against what you asked for and found nothing to raise.";\n'
        )

        values = re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', out["block"])
        self.assertEqual(["not published", "0", "3", "3", "2"], values)

    def test_each_figure_counts_the_rows_its_own_part_rendered(self) -> None:
        """The shared contract's second rule, and the DRC-4453 defect class.

        The section renders two collections under one heading. One figure
        counting one of them read "Departures raised about this session 1" under
        two rendered rows, and read 0 under a rendered row when the only
        departure came from the reading.
        """
        setup = (
            '__dashboard.sessions[0].annotation_goal = "do not change the board while '
            'capturing";\n'
            '__dashboard.sessions[0].annotation_goal_why = "";\n'
            '__dashboard.sessions[0].annotation_output = "";\n'
            '__dashboard.sessions[0].annotation_output_why = "";\n'
            "__dashboard.sessions[0].annotation_revision = 1;\n"
            "__dashboard.sessions[0].annotation_revision_count = 1;\n"
            "__dashboard.sessions[0].annotation_at = 200;\n"
            '__dashboard.sessions[0].annotation_binding_why = "";\n'
            "__dashboard.sessions[0].annotation_assessment = {revision_read:1, criteria:{"
            ' goal:{result:"departure", detail:"It changed the board mid-capture.",'
            ' cites:["fo-a"]}}};\n'
        )
        reading_only = self.review(
            "__dashboard.unasked = true;\n"
            "__dashboard.delivery_counts = {raises: 1, attempted: 1, handed_over: 0};\n"
            + setup
            + "__dashboard.sessions[0].departures = [];\n"
            "__dashboard.sessions[0].departure_checked = true;\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )
        both = self.review(
            "__dashboard.unasked = true;\n"
            "__dashboard.delivery_counts = {raises: 1, attempted: 1, handed_over: 0};\n"
            + setup
            + f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertIn("It changed the board mid-capture.", reading_only["visible"])
        self.assertEqual(
            ["1", "0", "1", "1", "0"],
            re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', reading_only["block"]),
        )
        self.assertEqual(
            ["1", "1", "1", "1", "0"],
            re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', both["block"]),
        )

    def test_the_review_surface_does_not_open_a_closed_reading_gate(self) -> None:
        """The unasked review does not authorize reader-requested readings.

        The control is read straight out of its own renderer, because the tab
        only reaches it once an annotation and an observer model are present and
        neither is what is under test here. What IS under test is that nothing
        this change added moved that paragraph or enabled that button.
        """
        out = self.review(
            f"__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )
        control = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            '__dashboard.reading_check = "not-run";\n'
            "__dashboard.annotate = true;\n"
            "console.log(JSON.stringify(nextCockpitReadingControl("
            '{harness:"codex", sid:"focus-1"}, {goal:"ship it", reading_count:0}, '
            "{enabled:true})));",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(control, str)

        self.assertIn(
            "Checking for drift is not enabled in this build, because the abstention check that "
            "gates it has not been recorded.",
            control,
        )
        self.assertIn("Check for drift</button>", control)
        # `aria-disabled`, not the bare attribute: the control keeps its place
        # in the tab order and `nextCockpitAskForReading` refuses the press it
        # now receives (DRC-4588). Both spellings are named, because a
        # substring check for "disabled" alone matches either one.
        self.assertIn('aria-disabled="true"', control)
        self.assertNotIn(" disabled>", control)
        # And the review section itself invites no press of its own.
        self.assertNotIn("Check for drift", out["block"])

    def test_an_unsettled_baseline_leaves_no_departure_in_the_reading_part(self) -> None:
        """AC3, verified rather than rebuilt.

        DRC-4508 built the demotion and
        `test_a_later_direction_demotes_a_departure_rather_than_filtering_it`
        pins it at the criterion row. What is checked here is its consequence
        for this section: the reading part carries no departure row, and the
        conflict block states the conflict without deciding it.
        """
        out = self.review(
            "__dashboard.unasked = true;\n"
            '__dashboard.sessions[0].annotation_goal = "do not change the board";\n'
            '__dashboard.sessions[0].annotation_goal_why = "";\n'
            '__dashboard.sessions[0].annotation_output = "";\n'
            '__dashboard.sessions[0].annotation_output_why = "No expected output typed.";\n'
            "__dashboard.sessions[0].annotation_revision = 1;\n"
            "__dashboard.sessions[0].annotation_revision_count = 1;\n"
            "__dashboard.sessions[0].annotation_at = 100;\n"
            '__dashboard.sessions[0].annotation_binding_why = "";\n'
            "__dashboard.sessions[0].annotation_assessment = {revision_read:1, criteria:{"
            ' goal:{result:"departure", detail:"It changed the board.", cites:["fo-a"]}}};\n'
            "__dashboard.sessions[0].departures = [];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertIn("CONFLICT TO SETTLE", out["html"])
        self.assertNotIn("It changed the board.", out["block"])
        self.assertIn(
            "This reading verified neither constraint, so it raised nothing and confirmed nothing.",
            out["visible"],
        )

    def test_the_section_points_at_where_a_raise_is_kept(self) -> None:
        # The design's order ends at "where it is kept", and the Intent log is
        # the only surface a raise survives its session on. It is the TAB's last
        # slot rather than this section's: emitted as the section's last child
        # it landed above HOW IT LANDED, because the six-slot tab order had been
        # re-read as five slots internal to the section.
        out = self.review(
            f"__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )
        html = out["html"]

        self.assertIn('href="#n=intent"', html)
        self.assertNotIn('href="#n=intent"', out["block"])
        self.assertLess(html.find("<h2>DEPARTURES RAISED TO YOU</h2>"), html.find("HOW IT LANDED"))
        self.assertLess(html.find("HOW IT LANDED"), html.find("next-cockpit-departures-kept"))

    def test_no_departure_standing_draws_no_sentence_about_how_one_was_raised(self) -> None:
        """A delivery sentence for a raise that does not exist.

        `delivery_*` is filled on every row from every lane -- gate, ask, hook
        and departure -- so a default board with a needs-input banner and no
        departure at all printed "One notification was raised about this
        session" under HOW IT WAS RAISED, four lines below the heading saying
        nothing watches for a departure.
        """
        delivery = (
            "__dashboard.sessions[0].delivery_departure = {delivery_raises: 1,"
            ' delivery_outcome: "handed-over", delivery_why: "Handed to this machine\'s '
            'notification service, which accepted it."};\n'
        )
        # The lane on, so the section draws and the gate inside it is what is measured.
        out = self.review("__dashboard.unasked = true;\n" + delivery)

        self.assertIn("DEPARTURES RAISED TO YOU", out["block"])
        self.assertNotIn("HOW IT WAS RAISED", out["block"])
        self.assertNotIn("which accepted it.", out["block"])
        # And with it off there is no section to carry the sentence at all.
        off = self.review("delete __dashboard.unasked;\n" + delivery)
        self.assertNotIn("which accepted it.", off["html"])

    def test_the_outcome_beside_a_departure_is_that_lane_s_and_not_the_board_s(self) -> None:
        """Four lanes write the delivery store and one sentence is published.

        Measured: a departure raise handed over, and an unrelated hook refusal
        an hour later, printed "The notification service returned an error"
        beside the departure that got out -- and the amber rule painted it.
        `delivery_mixed_why` cannot cover this: it says earlier raises ended
        differently, never that some were not about a departure.
        """
        out = self.review(
            f"__dashboard.unasked = true;\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
            "__dashboard.sessions[0].delivery_raises = 2;\n"
            '__dashboard.sessions[0].delivery_outcome = "refused";\n'
            '__dashboard.sessions[0].delivery_why = "The notification service returned an '
            'error, so no banner was created.";\n'
            "__dashboard.sessions[0].delivery_mixed = true;\n"
            "__dashboard.sessions[0].delivery_departure = {delivery_raises: 1,"
            ' delivery_outcome: "handed-over",'
            " delivery_why: \"Handed to this machine's notification service, which accepted"
            ' it."};\n'
        )

        self.assertIn("which accepted it.", out["visible"])
        self.assertNotIn("The notification service returned an error", out["block"])
        self.assertIn('data-next-delivery="handed-over"', out["block"])
        self.assertNotIn('data-next-delivery="refused"', out["block"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitCuesReachTheReaderTest(NextPageJsHarness):
    """DRC-4564: the four cue families, and the region that carries them.

    None of these tests asserts that anything is spoken. The stub document has
    no accessibility tree, so what is checkable here is the shape a reader's
    software reads: where the region sits, that it is the same node across
    every redraw, its role and politeness, the ordered list of writes into it,
    and the attribute that ties the armed warning to the control it warns
    about. That any of it is announced was measured in a browser, not here.

    The regions are held OUTSIDE `#app` for the reason the attention announcer
    is: `renderNext` assigns `#app`'s inner HTML wholesale, so a region drawn
    inside it is destroyed and recreated with its text already in place on
    every render, which is the shape a reader's software skips.
    """

    FIXTURE = CockpitHeldToTabTest.FIXTURE
    ANNOTATED = CockpitHeldToTabTest.ANNOTATED
    # The held-to DOM stub, plus the two things the announcer lane needs from
    # a document: an element factory whose nodes remember every write, and an
    # `#app` that accepts a sibling.
    ANNOUNCER_DOM = (
        CockpitHeldToTabTest.FOCUS_DOM
        + """
let __regions = [];
document.createElement = () => ({
  style: {}, appendChild(){}, writes: [], attrs: {},
  setAttribute(name, value){ this.attrs[name] = value; },
  get textContent(){ return this.text || ""; },
  set textContent(value){ this.text = String(value); this.writes.push(String(value)); }
});
__els.app.insertAdjacentElement = (position, node) => {
  __regions.push({position, id: node.id, node});
};
const region = id => (__regions.find(entry => entry.id === id) || {}).node;
const wrote = id => (region(id) || {writes: []}).writes;
renderNext();
"""
    )

    def run_fixture(self, checks: str) -> Any:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_two_regions_are_held_outside_the_application_node_across_renders(self) -> None:
        """AC7 and AC10, as far as a stub document can carry them.

        Ensured on every render beside the attention announcer rather than
        lazily from a handler: lazy creation is the defect in the two
        announcers that are not the attention one, where the node and its first
        message arrive together and a node that arrives carrying its text is
        the one a reader's software skips.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const first = __regions.map(entry => entry.node);
renderNext();
renderNext();
console.log(JSON.stringify({
  ids: __regions.map(entry => entry.id),
  positions: [...new Set(__regions.map(entry => entry.position))],
  same: __regions.every((entry, index) => entry.node === first[index]),
  roles: __regions.map(entry => entry.node.role),
  live: __regions.map(entry => entry.node.ariaLive),
  atomic: __regions.map(entry => entry.node.ariaAtomic),
  hidden: __regions.map(entry => entry.node.className),
}));
"""
        )

        self.assertEqual(
            ["next-attention-status", "next-cockpit-cue-status", "next-cockpit-cue-alert"],
            out["ids"],
        )
        self.assertEqual(["afterend"], out["positions"])
        self.assertTrue(out["same"], "one node per region for the life of the tab")
        self.assertEqual(["status", "status", "alert"], out["roles"])
        self.assertEqual(["polite", "polite", "assertive"], out["live"])
        self.assertEqual(["true", "true", "true"], out["atomic"])
        self.assertEqual(["next-visually-hidden"] * 3, out["hidden"])

    def test_no_live_region_is_added_inside_the_application_node(self) -> None:
        """AC8. The count inside `#app` stays at the zero the walk measured."""
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  live: (html.match(/aria-live=/g) || []).length,
  status: (html.match(/role="status"/g) || []).length,
  alert: (html.match(/role="alert"/g) || []).length,
}));
"""
        )

        self.assertEqual(0, out["live"])
        self.assertEqual(0, out["status"])
        self.assertEqual(0, out["alert"])

    def test_a_repeated_save_against_the_same_failing_store_is_written_once(self) -> None:
        """AC7 for the save family, and the guard against writing it twice.

        Three presses, two writes: what the guard suppresses is the second
        report of one standing mark, not the second press. The write is pushed
        from the mark rather than from the render, which runs on every fallback
        poll.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + """
let persisted = false;
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
type("output", "Six screenshots");
await __settle();
save("output");
await __settle();
/* A second press with nothing typed between them. The mark from the first is
   still standing, and the words and the store are the same, so this is the
   repeat rather than a second attempt. */
save("output");
await __settle();
persisted = true;
save("output");
await __settle();
console.log(JSON.stringify({
  polite: wrote("next-cockpit-cue-status"),
  alert: wrote("next-cockpit-cue-alert"),
  onScreen: (__els.app.innerHTML
    .match(/class="next-cockpit-held-cue">([^<]*)</) || [])[1],
}));
"""
        )

        # Three presses, two writes: the repeated sentence is written once, and
        # the sentence that differs is written when it differs.
        self.assertEqual(
            [
                (
                    "Not stored. The store could not be written, so the refresh has already "
                    "dropped these words, and they are still in the box."
                ),
                "Saved as a new revision.",
            ],
            out["polite"],
        )
        self.assertEqual([], out["alert"])
        # And the region says what the block says, rather than a second wording.
        self.assertEqual("Saved as a new revision.", out["onScreen"])

    def test_a_save_after_a_keystroke_is_written_again_though_the_sentence_is_the_same(
        self,
    ) -> None:
        """Where the guard has to stop, on the drop site a keystroke reaches.

        A keystroke drops the mark the cue is drawn from, so the next render
        takes the cue off the screen and the press after it is a fresh attempt
        on different words. Suppressing its report would leave a reader who
        edited and saved again with a cue on screen and silence in the region.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + """
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => String(url) === "/api/annotate"
  ? {ok:true, status:200, json: async () => ({ok:true, persisted:false,
      outcome:"unwritable", revision:2, revision_count:2})}
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
type("output", "Six screenshots");
await __settle();
save("output");
await __settle();
type("output", "Six screenshots and a log");
await __settle();
const marked = nextCockpitHeldStates.has("held:codex:focus-1:output");
save("output");
await __settle();
console.log(JSON.stringify({marked, polite: wrote("next-cockpit-cue-status")}));
"""
        )

        self.assertFalse(out["marked"], "the keystroke drops the mark the cue is drawn from")
        self.assertEqual(
            [
                (
                    "Not stored. The store could not be written, so the refresh has already "
                    "dropped these words, and they are still in the box."
                )
            ]
            * 2,
            out["polite"],
        )

    def test_a_save_in_each_field_is_written_once_for_each(self) -> None:
        """The ordinary two-field workflow, and the guard keyed to survive it.

        `Saved as a new revision.` is field-independent, so a guard holding one
        sentence for the whole page dropped the second field's write: measured
        two cue nodes on screen against a single write into the region. The
        guard is keyed by the mark's own key, which is per field.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + """
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => String(url) === "/api/annotate"
  ? {ok:true, status:200, json: async () => ({ok:true, persisted:true, outcome:"stored",
      revision:2, revision_count:2})}
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
type("goal", "Ship the cockpit");
await __settle();
save("goal");
await __settle();
type("output", "Six screenshots");
await __settle();
save("output");
await __settle();
console.log(JSON.stringify({
  polite: wrote("next-cockpit-cue-status"),
  onScreen: (__els.app.innerHTML
    .match(/class="next-cockpit-held-cue">([^<]*)</g) || []).length,
}));
"""
        )

        self.assertEqual(2, out["onScreen"])
        self.assertEqual(["Saved as a new revision."] * 2, out["polite"])

    def test_the_armed_control_carries_the_warning_as_its_description(self) -> None:
        """AC9's markup half, and the highest-value item in the issue.

        Measured in the accessibility tree: a reader who tabs to the armed
        control is told exactly `confirm discard, button`. The warning sits
        after the button as an unlinked sibling — browsable, and reached by
        no live region, because nothing mutates when you tab.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + f"const __armed = {json.dumps(annotation_store.DISCARD_ARMED)};\n"
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const control = () => controls.find(entry =>
  entry.dataset.nextCockpitAction === "held-discard");
const before = {
  described: control().getAttribute("aria-describedby"),
  label: control().attrs["data-next-cockpit-discard-key"],
};
__fire("click", {target:control(), preventDefault(){}});
await __settle();
const html = __els.app.innerHTML;
const described = control().getAttribute("aria-describedby");
console.log(JSON.stringify({
  before,
  described,
  target: (html.match(new RegExp('id="' + described + '">([^<]*)<')) || [])[1],
  matches: (html.match(/id="next-cockpit-discard-armed"/g) || []).length,
  pressed: (html.match(/aria-pressed|aria-expanded/g) || []).length,
  armedIsTheWarning: (html.match(new RegExp('id="' + described + '">([^<]*)<')) || [])[1]
    === __armed,
}));
"""
        )

        # Unarmed the control describes nothing, because there is no warning
        # beside it to describe.
        self.assertIsNone(out["before"]["described"])
        self.assertEqual("next-cockpit-discard-armed", out["described"])
        self.assertEqual(1, out["matches"])
        self.assertEqual(annotation_store.DISCARD_ARMED, out["target"])
        self.assertTrue(out["armedIsTheWarning"])
        # A pressed or expanded state would say a toggle is on. The second
        # press performs a different, irreversible act rather than an un-press.
        self.assertEqual(0, out["pressed"])

    def test_the_armed_warning_goes_to_the_alert_region_and_the_outcome_to_the_polite_one(
        self,
    ) -> None:
        """AC7 and AC9's region half, for the two-press act.

        Assertive for the arm alone, and it is the first assertive region in
        the bundle. After the first press focus returns to the same button and
        the dwell that refuses a too-fast second press is 1.2 seconds, so a
        polite message queued behind whatever the redraw is already saying can
        still be unspoken when the second press lands.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + CockpitHeldToTabTest.DISCARD_WITH_REPLY
            + """
press();
await __settle();
const armed = {
  polite: [...wrote("next-cockpit-cue-status")],
  alert: [...wrote("next-cockpit-cue-alert")],
};
dwell();
press();
await __settle();
console.log(JSON.stringify({
  armed,
  polite: wrote("next-cockpit-cue-status"),
  alert: wrote("next-cockpit-cue-alert"),
}));
"""
        )

        self.assertEqual([], out["armed"]["polite"])
        self.assertEqual([annotation_store.DISCARD_ARMED], out["armed"]["alert"])
        # The act itself is the polite region's, and the alert region is emptied
        # before it: the warning says nothing has been deleted yet, and by now
        # something has.
        self.assertEqual([annotation_store.DISCARD_STORED], out["polite"])
        self.assertEqual([annotation_store.DISCARD_ARMED, ""], out["alert"])

    def test_the_armed_warning_is_taken_back_once_the_arm_no_longer_stands(self) -> None:
        """The sentence that goes false, and the one place it survives.

        Measured in the accessibility tree on a live board: after a completed
        discard the alert node still read `Nothing has been deleted yet` beside
        a status node reading `Discarded ... is gone`. The paragraph the render
        drew is gone by then, so the region is the only place that sentence
        survives, and it is the one that says nothing has happened. Two
        channels of one page disagreeing about whether an irreversible act
        took place is a shipped defect class here.

        Emptying a region is a removal rather than an addition, so taking the
        warning back is silent where writing it was not. That is what makes the
        retraction safe to do at every site that stops an arm, and the writes
        below are what says it happens at each of them.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + CockpitHeldToTabTest.DISCARD_WITH_REPLY
            + """
press();
await __settle();
const armed = [...wrote("next-cockpit-cue-alert")];
__fire("keydown", {key:"Escape", target:discardControl(), preventDefault(){}});
await __settle();
const afterEscape = [...wrote("next-cockpit-cue-alert")];
press();
await __settle();
// Past NEXT_CONTROL_STATE_TTL_MS: the arm lapses on its own at the next read.
__setNow(__nowSec + 60);
renderNext();
const afterLapse = [...wrote("next-cockpit-cue-alert")];
press();
await __settle();
dwell();
press();
await __settle();
console.log(JSON.stringify({
  armed, afterEscape, afterLapse,
  alert: wrote("next-cockpit-cue-alert"),
  polite: wrote("next-cockpit-cue-status"),
}));
"""
        )

        armed = annotation_store.DISCARD_ARMED
        self.assertEqual([armed], out["armed"])
        # Escape disarms, so the offer the sentence describes is off the table.
        self.assertEqual([armed, ""], out["afterEscape"])
        # And so does the window running out, which is read at a render rather
        # than by anything the reader did.
        self.assertEqual([armed, "", armed, ""], out["afterLapse"])
        # The act itself: the outcome is the polite region's, and the warning
        # that said nothing had been deleted yet is taken back before it.
        self.assertEqual([armed, "", armed, "", armed, ""], out["alert"])
        self.assertEqual([annotation_store.DISCARD_STORED], out["polite"])

    def test_an_arm_that_lapsed_is_warned_about_again_when_it_is_re_armed(self) -> None:
        """The cost of the repeat guard, and where it has to stop.

        The guard is there so one press reports once. An arm that lapsed on its
        own is not a repeat: the reader walked away, came back to a disarmed
        control and pressed it again, and the warning they need is the same
        sentence they were told 30 seconds ago.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + CockpitHeldToTabTest.DISCARD_WITH_REPLY
            + """
press();
await __settle();
// Past NEXT_CONTROL_STATE_TTL_MS, so the arm has lapsed and the control the
// reader comes back to is the unarmed one.
__setNow(__nowSec + 60);
renderNext();
press();
await __settle();
console.log(JSON.stringify({
  alert: wrote("next-cockpit-cue-alert"),
  armedNow: __els.app.innerHTML.includes("confirm discard"),
}));
"""
        )

        self.assertEqual(
            [annotation_store.DISCARD_ARMED, "", annotation_store.DISCARD_ARMED], out["alert"]
        )
        self.assertTrue(out["armedNow"])

    def test_an_arm_dropped_with_escape_is_written_to_the_alert_region_again(self) -> None:
        """The other deliberate drop, and the one nothing bound.

        Escape on the armed control disarms it, so the press after that is a
        fresh arm rather than a repeat of the one the reader dismissed. Nothing
        pinned it: deleting the guard's clear from that handler left the whole
        cockpit, chrome, documentation and focus suite green.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + self.ANNOTATED
            + f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            + CockpitHeldToTabTest.DISCARD_WITH_REPLY
            + """
press();
await __settle();
__fire("keydown", {key:"Escape", target:discardControl(), preventDefault(){}});
await __settle();
const disarmed = __els.app.innerHTML.includes("confirm discard");
press();
await __settle();
console.log(JSON.stringify({
  disarmed,
  alert: wrote("next-cockpit-cue-alert"),
  armedNow: __els.app.innerHTML.includes("confirm discard"),
}));
"""
        )

        self.assertFalse(out["disarmed"], "Escape disarms the control")
        self.assertEqual(
            [annotation_store.DISCARD_ARMED, "", annotation_store.DISCARD_ARMED], out["alert"]
        )
        self.assertTrue(out["armedNow"])

    def test_both_settle_outcomes_are_written_to_the_polite_region(self) -> None:
        """AC7 for the settle family, which the issue counted as one cue.

        A settle that lands prints no cue at all and re-renders a different
        element, so covering only the cue table would ship the landed one
        silent. Its sentence is the page's own, because the block's account of
        a settle that landed is composed at the next render out of the store
        the refresh has not read yet.
        """
        out = self.run_fixture(
            self.ANNOUNCER_DOM
            + """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.sessions[0].annotation_goal = "do not change the board";
__dashboard.sessions[0].annotation_goal_why = "";
__dashboard.sessions[0].annotation_output = "";
__dashboard.sessions[0].annotation_output_why = "";
__dashboard.sessions[0].annotation_revision = 1;
__dashboard.sessions[0].annotation_revision_count = 1;
__dashboard.sessions[0].annotation_at = 100;
__dashboard.sessions[0].annotation_binding_why = "";
let reply = {ok:true, persisted:false, outcome:"unwritable", revision:1, revision_count:1};
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => {
  if(String(url) !== "/api/annotate") return upstream(url, init);
  return {ok:true, status:200, json: async () => reply};
};
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const settle = () => __fire("click", {target:controls.find(control =>
  control.dataset.nextCockpitAction === "conflict-settle"), preventDefault(){}});
settle();
await __settle();
await __settle();
const failed = [...wrote("next-cockpit-cue-status")];
reply = {ok:true, persisted:true, outcome:"stored", revision:1, revision_count:1};
settle();
await __settle();
await __settle();
console.log(JSON.stringify({
  failed,
  polite: wrote("next-cockpit-cue-status"),
  alert: wrote("next-cockpit-cue-alert"),
}));
"""
        )

        self.assertEqual(
            [
                (
                    "Not settled. The store could not be written, so the mark has already been "
                    "dropped and the question below still stands."
                )
            ],
            out["failed"],
        )
        self.assertEqual(
            [
                (
                    "Not settled. The store could not be written, so the mark has already been "
                    "dropped and the question below still stands."
                ),
                "Settled. A direction given after this will raise it again.",
            ],
            out["polite"],
        )
        self.assertEqual([], out["alert"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CountsAbsenceIsStampedAndAZeroIsNotTest(NextPageJsHarness):
    """DRC-4589 AC-2. COUNTS wrote "not published" into the same span a real
    figure gets, so an absence rendered byte-identical to a fact.

    The attribute is what the stylesheet hangs the em dash and the family swap
    on, and the case that matters is the negative one: a real `0` is a
    measurement and must carry neither. A rule cannot make that distinction --
    `0` and `null` reach the same selector -- so it is stamped at emission and
    asserted here on both arms.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE
    DEPARTURE = CockpitDepartureReviewTest.DEPARTURE

    def counts(self, setup: str) -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "__dashboard.annotate = true;\n__dashboard.annotate_cap = 240;\n"
            + setup
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const block = (__els.app.innerHTML.match(
  /<section class="next-cockpit-departures">[\\s\\S]*?<\\/section>/) || [""])[0];
// Every count span with its attribute, in document order: an assertion that
// reads only the absent ones cannot see a stamp landing on a real figure.
const spans = [...block.matchAll(
  /<span class="next-cockpit-count-value"([^>]*)>([^<]*)</g)].map(
  m => [m[2], m[1].includes("data-next-absent")]);
console.log(JSON.stringify({spans}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_a_null_count_is_stamped_and_a_real_zero_is_not(self) -> None:
        out = self.counts(
            "delete __dashboard.unasked;\n"
            "__dashboard.delivery_counts = {raises: 0, attempted: 0, handed_over: 0};\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        # The first row is the unmeasured one and the three zeroes behind it are
        # measurements. A blanket stamp passes an absent-only assertion and
        # fails this one.
        self.assertEqual(
            [["not published", True], ["1", False], ["0", False], ["0", False], ["0", False]],
            out["spans"],
        )

    def test_the_stamp_follows_the_value_and_not_the_row(self) -> None:
        """The same rows with figures behind them carry no stamp at all."""
        out = self.counts(
            "delete __dashboard.unasked;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            f"__dashboard.sessions[0].departures = [{self.DEPARTURE}];\n"
            '__dashboard.sessions[0].departure_why = "";\n'
        )

        self.assertEqual(
            [["not published", True], ["1", False], ["3", False], ["3", False], ["2", False]],
            out["spans"],
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class AnAbsenceParagraphNamesItsKindTest(NextPageJsHarness):
    """DRC-4589 AC-4. One paragraph class carried a rule, an offer, a result and
    three different kinds of absence in one treatment.

    The two negative cases below are the point of the criterion: tagging all
    twenty-one emission sites would turn `data-absence` into a
    structurally-present default that measures nothing about the session, and
    would put an absence cue on a reading that ran and raised nothing.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    def whys(self, setup: str, after: str = "") -> list[list[Any]]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "__dashboard.annotate = true;\n__dashboard.annotate_cap = 240;\n"
            + setup
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
"""
            + after
            + """
const rows = [...__els.app.innerHTML.matchAll(
  /<(?:p|span) class="next-cockpit-reading-why"([^>]*)>([^<]*)</g)].map(m => {
  const kind = (m[1].match(/data-absence="([a-z-]+)"/) || [null, ""])[1];
  return [m[2].slice(0, 46), kind];
});
console.log(JSON.stringify({rows}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return [list(row) for row in out["rows"]]

    def kind_of(self, rows: list[list[Any]], prefix: str) -> str:
        found = [row for row in rows if row[0].startswith(prefix)]
        self.assertEqual(1, len(found), f"{prefix!r} matched {len(found)} paragraphs: {rows}")
        return str(found[0][1])

    def test_the_run_config_sentence_names_the_flag_and_the_kind(self) -> None:
        """The `--unasked-readings` paragraph, which AC-5 also holds in place."""
        rows = self.whys("delete __dashboard.unasked;\n" + STANDING_RAISE)

        self.assertEqual(
            "run-config", self.kind_of(rows, "Nothing watches for a departure on its own")
        )

    def test_a_reading_nobody_asked_for_is_not_observed_rather_than_waited_on(self) -> None:
        rows = self.whys(
            "__dashboard.unasked = true;\n"
            '__dashboard.sessions[0].annotation_goal = "ship the thing";\n'
            "delete __dashboard.sessions[0].assessment;\n"
        )

        self.assertEqual(
            "not-observed", self.kind_of(rows, "No reading has been made at your request")
        )

    def test_a_reader_who_has_typed_nothing_is_waiting_on_themselves(self) -> None:
        """The one kind the reader can act on, and the only one the stylesheet
        marks with the accent rule."""
        rows = self.whys(
            "__dashboard.unasked = true;\n"
            '__dashboard.sessions[0].annotation_goal = "";\n'
            '__dashboard.sessions[0].annotation_output = "";\n'
        )

        self.assertEqual(
            "waiting-on-you", self.kind_of(rows, "Nothing has been typed for this session")
        )

    def test_an_explicit_model_off_switch_is_a_choice_about_the_run(self) -> None:
        # The model lands on the context entry the cockpit fetches, so it is set
        # after navigation and re-rendered rather than seeded on the payload.
        rows = self.whys(
            "__dashboard.unasked = true;\n"
            '__dashboard.sessions[0].annotation_goal = "ship the thing";\n',
            """
const group = nextProjectGroups().find(g => g.label === "cargento");
const entry = nextCockpitContexts.get(
  nextCockpitContextKey(group, nextCockpitFocusedSession(group)));
__dashboard.reading = {consent:true,reason:"run-disabled"};
renderNext();
""",
        )

        self.assertEqual("run-config", self.kind_of(rows, "Model calls are off for this run"))

    def test_a_statement_that_is_not_an_absence_carries_no_attribute(self) -> None:
        """Two paragraphs the criterion names by hand. Both are the board
        reasoning about figures it has, not reporting a gap."""
        rows = self.whys(
            "delete __dashboard.unasked;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            + STANDING_RAISE
        )

        self.assertEqual("", self.kind_of(rows, "Five figures, and no arithmetic between them"))
        self.assertEqual("", self.kind_of(rows, "Neither card implies the other"))

    def test_no_emission_carries_a_kind_outside_the_declared_three(self) -> None:
        rows = self.whys("delete __dashboard.unasked;\n")

        self.assertEqual(
            set(),
            {row[1] for row in rows} - {"", "not-observed", "waiting-on-you", "run-config"},
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheBriefingSaysWhoIsWaitingBeforeItNamesItselfTest(NextPageJsHarness):
    """DRC-4593 AC-1, AC-3, AC-5 and AC-6.

    The briefing is redrawn above every tab, and its loudest string was
    `FO INSPECTING` -- workflow vocabulary, never glossed, computed from
    attention coverage rather than from anything an agent is doing -- while the
    line telling the reader they are off the hook was the dimmest thing in the
    same cell.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    def briefing(self, setup: str = "", after: str = "") -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + setup
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"now"});
await __settle();
"""
            + after
            + """
const html = __els.app.innerHTML;
// Balanced rather than lazy: STATED GOAL is a nested <section>, so a lazy match
// cuts the briefing off three cells before COMMAND and every assertion below
// would pass against a fragment that never contained what it denies.
const start = html.indexOf('<section class="next-cockpit-recovery"');
let block = "";
if(start >= 0){
  const scan = /<section\\b|<\\/section>/g;
  scan.lastIndex = start;
  let depth = 0, hit;
  while((hit = scan.exec(html))){
    depth += hit[0] === "</section>" ? -1 : 1;
    if(depth === 0){ block = html.slice(start, scan.lastIndex); break; }
  }
}
const header = (block.match(/<header>[\\s\\S]*?<\\/header>/) || [""])[0];
const authority = (block.match(
  /<div class="next-cockpit-authority[\\s\\S]*?<details/) || [""])[0];
console.log(JSON.stringify({block, header, authority,
  chip: (authority.match(/<span>([^<]*)</) || [null, ""])[1],
  strongs: [...authority.matchAll(/<strong>([^<]*)</g)].map(m => m[1]),
  smalls: [...authority.matchAll(/<small>([^<]*)</g)].map(m => m[1])}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_the_state_names_survive_verbatim_and_the_gloss_sits_in_the_header(self) -> None:
        """AC-1. The states are strings a source published, so substituting
        prose about what the agent is doing would be a claim nothing observed.
        """
        out = self.briefing()

        self.assertIn(out["chip"], {"FO INSPECTING", "FO CONTINUES", "CAPTAIN NEEDED"})
        self.assertIn(
            "FO is the first officer, the agent driving this workflow; Captain is you.",
            out["header"],
        )
        self.assertIn("next-cockpit-recovery-gloss", out["header"])

    def test_the_authority_block_states_no_agent_activity(self) -> None:
        """AC-3. `fo-inspecting` is computed from attention coverage, so a verb
        about what the agent is doing would be unobserved on every board."""
        out = self.briefing()

        for invented in ("is looking", "is working", "is thinking", "is editing"):
            self.assertNotIn(invented, out["authority"])

    def test_the_fo_attention_row_renders_unchanged_when_discovery_errors(self) -> None:
        """AC-3's second half: the row is emitted only when workflow discovery
        fails, so demoting it would delete a live signal."""
        # Discovery lands on the project context entry, so it is set after
        # navigation and re-rendered rather than seeded on the payload.
        out = self.briefing(
            after="""
const group = nextProjectGroups().find(g => g.label === "cargento");
const key = nextCockpitContextKey(group, null);
const entry = nextCockpitContexts.get(key) || {};
entry.data = Object.assign({}, entry.data, {workflow_discovery:
  {state:"error", reason:"timed out", source:"project workflow discovery"}});
nextCockpitContexts.set(key, entry);
renderNext();
""",
        )

        self.assertIn("refresh workflow discovery", out["authority"])
        self.assertIn("<strong>", out["authority"])

    def test_the_briefing_states_absence_on_two_verbs_and_never_on_captured(self) -> None:
        """AC-5. A value says what was not observed; a caption says what was not
        published. "captured" said neither and implied a third distinction."""
        out = self.briefing()

        self.assertNotIn("captured", out["block"])
        self.assertIn("not observed", out["block"])

    def test_no_absence_phrase_absent_from_the_tree_is_introduced(self) -> None:
        """AC-5's other half: "None recorded" was proposed at triage and found
        nowhere in the repository, so adopting it would have created a
        convention and its documentation in one change."""
        out = self.briefing()

        self.assertNotIn("None recorded", out["block"])

    def test_the_evidence_caption_renders_only_when_the_task_is_known(self) -> None:
        """AC-6. With no task observed the value cell already reads
        "Not observed", and the caption states a second absence about a first.
        """
        # `task.known` is computed from the project observation's trail head, not
        # from the session rows, so the unknown arm empties the observation after
        # navigation. Emptying the session rows leaves it known and the test
        # passes against a board that never entered the arm it names.
        strip = """
const group = nextProjectGroups().find(g => g.label === "cargento");
const key = nextCockpitContextKey(group, null);
const entry = nextCockpitContexts.get(key) || {};
entry.data = Object.assign({}, entry.data,
  {semantic:{facts:[], work_items:[], projections:{}}});
nextCockpitContexts.set(key, entry);
for(const session of __dashboard.sessions){
  delete session.last_output;
  session.subagent_hierarchy = [];
}
renderNext();
"""
        known = self.briefing()
        unknown = self.briefing(after=strip)

        self.assertIn("data-next-cockpit-task-known", known["block"])
        self.assertNotIn("data-next-cockpit-task-known", unknown["block"])
        self.assertNotIn("Assignment evidence not published", unknown["block"])
        self.assertIn("Not observed", unknown["block"])


class AnAbsentVariantBorrowsItsSizeFromTheValueItReplacesTest(unittest.TestCase):
    """DRC-4589 AC-2, the half a selector sweep cannot reach.

    COUNTS and DELEGATION choose between a real figure and its absence with a
    ternary, so the two never co-exist in one render and no CSS rule holds both
    sides. The sibling comparison test above works because those pairs are two
    selectors; these are one selector and an attribute. What is asserted instead
    is that the absent variant declares no size of its own -- neither
    `font-size` nor a `font` shorthand, which would reset it -- so its size is
    the value's by construction and cannot drift above it.

    Read off the stylesheet: the cascade is what decides this either way, and
    three tests on the branch that introduced this defect class passed over it
    by asserting an absence with its value left out.
    """

    ABSENT_VARIANTS = (
        ".next-cockpit-count-value[data-next-absent]",
        ".next-delegation-withheld strong[data-next-absent]",
    )

    css: str

    @classmethod
    def setUpClass(cls) -> None:
        source = (
            pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"
        ).read_text(encoding="utf-8")
        cls.css = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)

    def block_for(self, selector: str) -> str:
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.css):
            if selector in [head.strip() for head in rule.group(1).split(",")]:
                return rule.group(2)
        self.fail(f"{selector} declares no rule at all, so the stamp draws nothing")
        raise AssertionError

    def test_no_absent_variant_declares_a_size(self) -> None:
        for selector in self.ABSENT_VARIANTS:
            with self.subTest(selector=selector):
                body = self.block_for(selector)
                self.assertNotIn("font-size", body)
                self.assertFalse(
                    re.search(r"(?<![-a-z])font:", body),
                    f"{selector} sets the font shorthand, which resets the size it "
                    "must inherit from the value it replaces",
                )
                # And it does change something, or the stamp is decorative.
                self.assertIn("font-family", body)

    def test_the_withheld_figure_is_smaller_than_the_figure_it_replaces(self) -> None:
        """The other half of AC-2, and the half the stamp assertions cannot see.

        Everything above proves the STAMP adds no size. None of it constrains
        the base rule the stamp sits on, so a `.next-delegation-withheld strong`
        raised above `.next-delegation-figure>strong` passes every assertion in
        this class while rendering an absence larger than the figure it stands
        in for. Measured: at 40px against the figure's 32px the class above is
        still green.

        It lives here rather than with the raised absences, which are scoped to
        the two DRC-4587 lifted to the sentence tier. This pair is not one of
        them -- the withheld caption is still at the label tier -- so widening that
        class to reach it would contradict its own stated bound.
        """

        sizes = {
            name: float(value)
            for name, value in re.findall(r"--(fs-[a-z0-9-]+):([0-9.]+)rem", self.css)
        }
        self.assertTrue(sizes, "the type scale declares no sizes to read")

        def declared_px(head: str) -> float:
            """The size the rule draws at, through the type scale.

            Both rules carried a literal `32px`/`16px` when this was written.
            The scale replaced every literal `font-size` with a token, so the
            number is resolved from the token table instead; the comparison
            below is unchanged, and a rule that declares no size at all still
            fails here rather than being read as zero.
            """
            body = self.block_for(head)
            found = re.findall(r"font:(?:\d+ )?(?:var\(--(fs-[a-z0-9-]+)\)|([0-9.]+)rem)", body)
            self.assertTrue(found, f"{head} declares no size")
            token, literal = found[-1]
            if not token:
                return float(literal)
            self.assertIn(token, sizes, f"{head} names --{token}, which the scale does not define")
            return sizes[token]

        figure = declared_px(".next-delegation-figure>strong")
        withheld = declared_px(".next-delegation-withheld strong")

        self.assertLessEqual(
            withheld,
            figure,
            f"withheld {withheld}px against figure {figure}px: "
            "the absence outranks the fact it replaces",
        )

    def test_the_dash_is_a_mark_and_never_a_size_or_a_tone_step(self) -> None:
        """The shared `::before`. A dash drawn brighter than the string it
        prefixes would put the emphasis on the absence rather than the fact."""
        body = self.block_for("[data-next-absent]::before")

        self.assertIn("content", body)
        self.assertNotIn("font-size", body)
        self.assertIn("var(--ink-absence)", body)


# The briefing's value rule is declared with its evidence sibling in one head, and
# the head is what identifies the rule, so it is spelled once here rather than
# wrapped inside the table below where a line break reads as two selectors.
VALUE_HEAD = (
    ".next-cockpit-recovery [data-next-cockpit-task-known]>strong,"
    ".next-cockpit-recovery .next-cockpit-recovery-evidence>strong"
)


class TheBriefingsThreeRegistersStayApartTest(unittest.TestCase):
    """DRC-4593 AC-4. In an absent ASSIGNMENT cell the label, the value and the
    caption explaining it all resolved to one ink, and DRC-4587 left the caption
    the biggest of the three.

    The cell this reads is the only one that can still render a caption: AC-6
    suppresses `Assignment evidence not published` when the task is unknown, so
    a caption now only ever sits beside a value the board did observe. That is
    what separates the registers -- the value is at `--ink-value`, the caption
    at `--ink-caption` -- rather than any size or hex moving.

    Resolved through the cascade and then through the registers, because a test
    that compared register NAMES would pass with all four pointing at one ink.
    """

    # role -> (selector whose colour wins, selector whose size wins)
    CELL: ClassVar[dict[str, tuple[str, str]]] = {
        "label": (".next-cockpit-recovery span", ".next-cockpit-recovery span"),
        "value": (VALUE_HEAD, ".next-cockpit-recovery strong,.next-cockpit-recovery small"),
        "caption": (
            ".next-cockpit-content .next-cockpit-evidence-missing",
            ".next-cockpit-content .next-cockpit-evidence-missing",
        ),
    }

    css: str
    sizes: dict[str, float]
    inks: dict[str, str]

    @classmethod
    def setUpClass(cls) -> None:
        source = (
            pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"
        ).read_text(encoding="utf-8")
        cls.css = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        cls.sizes = {
            name: float(value)
            for name, value in re.findall(r"--(fs-[a-z0-9-]+):([0-9.]+)rem", cls.css)
        }
        cls.inks = dict(re.findall(r"--(ink[a-z0-9-]*):(#[0-9a-f]{6}|var\(--ink[0-9]?\))", cls.css))

    def body_of(self, head: str) -> str:
        """Every block with this exact head, in source order and joined.

        Four of these selectors are declared twice -- once in their own region
        and once in the override region below it -- and the second declaration
        is the one that paints. Reading only the first reported the pre-DRC-4587
        sizes and would have called the inversion fixed while it was still on
        screen.
        """
        bodies = [
            rule.group(2)
            for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.css)
            if rule.group(1).strip() == head
        ]
        self.assertTrue(bodies, f"no rule with head {head!r}")
        return ";".join(bodies)

    def resolved_ink(self, head: str) -> str:
        """The hex the rule's colour lands on, one register hop at a time."""
        found = re.findall(r"color:var\(--([a-z0-9-]+)\)", self.body_of(head))
        self.assertTrue(found, f"{head} declares no colour")
        name = found[-1]
        for _ in range(4):
            value = self.inks.get(name, "")
            hop = re.fullmatch(r"var\(--(ink[0-9]?)\)", value)
            if not hop:
                return value
            name = hop.group(1)
        self.fail(f"{head} never resolves to a hex")
        raise AssertionError

    def resolved_size(self, head: str) -> float:
        found = re.findall(
            r"(?:font-size:|font:(?:\d+ )?)var\(--(fs-[a-z0-9-]+)\)", self.body_of(head)
        )
        self.assertTrue(found, f"{head} declares no size")
        return self.sizes[found[-1]]

    def register(self, head: str) -> str:
        """The register NAME the rule names, before any hop."""
        found: list[str] = re.findall(r"color:var\(--([a-z0-9-]+)\)", self.body_of(head))
        self.assertTrue(found, f"{head} declares no colour")
        return found[-1]

    def test_label_value_and_caption_are_three_distinct_size_and_ink_pairs(self) -> None:
        """AC-4, on all three things the criterion names, because each collapse
        survives the other two assertions.

        The criterion's word is REGISTERS. Asserting `(size, ink)` pairs alone
        was not that: pointing two roles at one register keeps the pairs
        distinct as long as the sizes differ, and it survived -- proved applied,
        with the resolved ink moving `var(--ink-label)` -> `var(--ink-caption)`
        down a real element path, so the mutant demonstrably reached the thing
        under test, and 319 tests still passed.

        Register names alone are not enough either, so both are asserted and
        each is the only guard against its own collapse.

        **What is deliberately NOT asserted is three distinct hexes.**
        `--ink-label`, `--ink-caption` and `--ink-absence` all resolve to the
        dim reading ink, and `docs/design-next-ui.md` records that as a ruling rather
        than an accident: the palette has three inks where the roles need four,
        and label, caption and absence are separated by family, case and size
        instead. A hex check here would contradict a shipped decision, which is
        why the pair carries the on-screen half.
        """
        registers = {role: self.register(ink_head) for role, (ink_head, _s) in self.CELL.items()}
        pairs = {
            role: (self.resolved_size(size_head), self.resolved_ink(ink_head))
            for role, (ink_head, size_head) in self.CELL.items()
        }

        self.assertEqual(3, len(set(registers.values())), registers)
        self.assertEqual(3, len(set(pairs.values())), pairs)

    def test_no_caption_is_drawn_larger_than_the_value_it_explains(self) -> None:
        """The inversion DRC-4587 left behind: the caption went to 15px while the
        value stayed at 12.5px, so the least important string in the cell was
        the biggest."""
        value = self.resolved_size(self.CELL["value"][1])
        caption = self.resolved_size(self.CELL["caption"][1])

        self.assertLessEqual(caption, value, f"caption {caption}px against value {value}px")

    def test_the_authority_chip_is_smaller_than_the_captain_line_beside_it(self) -> None:
        """DRC-4593 AC-2's offline half. The chip carried 15px and full `--ink`
        against a 12.5px `--ink3` captain line, so the loudest string on the page
        was the one piece of vocabulary the page never defines. This is a proxy
        for the criterion and not the criterion: AC-2 is judged on a painted
        board, because size and contrast are what a reader sees.
        """
        chip = self.resolved_size(".next-cockpit-authority>span")
        captain = self.resolved_size(".next-cockpit-authority>small")

        self.assertLess(chip, captain)
        self.assertEqual(self.resolved_ink(".next-cockpit-authority>small"), self.inks["ink"])
        # The chip read `--ink3` until `--ink3` stopped being a reading ink and
        # became the text of an inert control. The property is unchanged -- the
        # chip is quieter than the line beside it -- so it is asserted against
        # the dim reading ink that now carries that step.
        self.assertEqual(self.resolved_ink(".next-cockpit-authority>span"), self.inks["ink2"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitTabsNameTheirPanelTest(NextPageJsHarness):
    """DRC-4592. A tab strip of five bare labels cannot be ranked before the
    click: three of the five open onto a heading that does not repeat the label,
    and nothing on a label says whether anything is behind it.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    LEDES: ClassVar[dict[str, str]] = {
        "now": "Now:",
        "course": "Course:",
        "decisions": "Decisions:",
        "console": "Console:",
    }

    def run_fixture(self, checks: str, *, storage: dict[str, str] | None = None) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude(storage or {}) + self.FIXTURE,
        )

    def test_every_tab_renders_exactly_one_lede_naming_its_own_tab_word(self) -> None:
        """AC-1. Falsified by a tab with no lede, with two, or with a lede whose
        text omits its own tab word."""
        out = self.run_fixture(
            """
const seen = {};
for(const tab of ["now","course","decisions","console"]){
  navigateNext({view:"project",project:"cargento",focus:null,tab});
  await __settle();
  const html = __els.app.innerHTML;
  const ledes = [...html.matchAll(/<p class="next-cockpit-lede">([\\s\\S]*?)<\\/p>/g)]
    .map(match => match[1]);
  const panel = (html.match(/<section class="next-cockpit-panel"[\\s\\S]*/) || [""])[0];
  seen[tab] = {count:ledes.length, text:ledes[0] || "",
    firstInPanel:panel.indexOf('class="next-cockpit-lede"') > -1 &&
      panel.indexOf('class="next-cockpit-lede"') < 200};
}
console.log(JSON.stringify(seen));
"""
        )
        assert isinstance(out, dict)
        for tab, word in self.LEDES.items():
            with self.subTest(tab=tab):
                self.assertEqual(1, out[tab]["count"], f"{tab} does not render exactly one lede")
                self.assertTrue(
                    out[tab]["text"].startswith(word),
                    f"{tab} lede does not open on its own tab word: {out[tab]['text']!r}",
                )
                self.assertTrue(out[tab]["firstInPanel"], f"{tab} lede is not under the strip")

    def test_departure_and_revision_are_defined_once_and_reading_is_not_defined_twice(self) -> None:
        """AC-2. Falsified by a second copy of any of the three sentences, or a
        definition rendered somewhere other than the first use of its noun."""
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + CockpitHeldToTabTest.ANNOTATED
            # The lane on, so the departures section that defines its noun renders.
            + "__dashboard.unasked = true;\n"
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
const count = needle => html.split(needle).length - 1;
console.log(JSON.stringify({
  departure:count("A departure is a place the record does not match the words you chose"),
  revision:count("Each save is a revision"),
  readingShort:count("A reading is one model pass over the record"),
  readingOffer:count("A reading is a model\\u2019s account of the evidence on this page"),
  departureAfterHeader:html.indexOf("A departure is a place the record") >
    html.indexOf("DEPARTURES RAISED TO YOU"),
  revisionNearStamp:Math.abs(html.indexOf("Each save is a revision") -
    html.indexOf('class="next-cockpit-held-revision"')) < 400
}));
""",
            storage_prelude({}) + CockpitHeldToTabTest.FIXTURE,
        )
        assert isinstance(out, dict)
        self.assertEqual(1, out["departure"])
        self.assertEqual(1, out["revision"])
        self.assertTrue(out["departureAfterHeader"])
        self.assertTrue(out["revisionNearStamp"])
        # Exactly one account of what a reading is, wherever the panel landed.
        self.assertEqual(1, out["readingShort"] + out["readingOffer"])

    def test_observed_state_changes_keeps_its_name_and_its_two_windows(self) -> None:
        """AC-3. Falsified by renaming the heading at either emitter, or by
        collapsing the 37m and 24h windows into one figure."""
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        project = (web / "next-project.js").read_text(encoding="utf-8")
        workstream = (web / "next-workstream.js").read_text(encoding="utf-8")
        observed = (web / "next-observed.js").read_text(encoding="utf-8")
        self.assertIn("OBSERVED STATE CHANGES", project)
        self.assertIn("OBSERVED STATE CHANGES", workstream)
        # changeNoteText carries the unattended count and the window label as
        # two separately-derived halves joined by " · ".
        self.assertIn("unattended · ", observed)
        self.assertIn("nextWorkstreamWindowLabel(window)", observed)

    def test_each_cue_counts_its_own_collection_and_never_falls_back_to_zero(self) -> None:
        """AC-4. Falsified by a cue that holds steady while its fixture
        collection grows, or that renders 0 when the collection is undefined."""
        out = self.run_fixture(
            """
const group = nextProjectGroups()[0];
const cue = (tab, project, extra) => nextCockpitTabCue(tab,
  Object.assign({group, project}, extra || {}), null);
const courseFor = n => cue("course",
  {key:"cargento", changes:Array.from({length:n}, (_, i) => ({at:i,label:"x"}))});
// Seeded on the context entry the cue reads, not passed in beside it. The cue
// and the Decisions panel resolve one entry through `nextCockpitContextRead`,
// so a fixture that supplies facts any other way is describing a board that
// cannot exist.
const seedProject = semantic => nextCockpitContexts.set(
  nextCockpitContextKey(group, null), {data:{semantic}, revision:105});
const decisionsFor = n => {
  seedProject({facts:Array.from({length:n}, (_, i) => ({fact_id:"d" + i, type:"gate_decision",
    at:i, by:"person:captain", decision:"approve", stage:"review"})),
    work_items:[], projections:{}});
  return nextCockpitTabCue("decisions", {group, project:{key:"cargento"}}, null);
};
const heldFor = n => {
  nextData.annotate = true;
  nextData.unasked = true;
  const session = {harness:"codex", sid:"focus-1",
    departures:Array.from({length:n}, (_, i) => ({id:"r" + i})), departure_checked:true};
  return nextCockpitTabCue("held-to", {group, project:{key:"cargento"}}, session, null);
};
console.log(JSON.stringify({
  course:[0,1,4].map(n => courseFor(n)),
  courseAbsent:cue("course", {key:"cargento", changes:null}),
  decisions:[0,2,5].map(n => decisionsFor(n)),
  decisionsAbsent:(() => { seedProject({work_items:[], projections:{}});
    return nextCockpitTabCue("decisions", {group, project:{key:"cargento"}}, null); })(),
  held:[0,1,3].map(n => heldFor(n)),
  heldAbsent:(() => { nextData.annotate = true; nextData.unasked = true;
    return nextCockpitTabCue("held-to", {group, project:{key:"cargento"}},
      {harness:"codex", sid:"focus-1"}, null); })()
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(
            [
                {"state": "zero", "value": 0},
                {"state": "count", "value": 1},
                {"state": "count", "value": 4},
            ],
            out["course"],
        )
        self.assertEqual(
            [
                {"state": "zero", "value": 0},
                {"state": "count", "value": 2},
                {"state": "count", "value": 5},
            ],
            out["decisions"],
        )
        # Held to is no longer a tab (DRC-4639), so it carries no cue at all
        # rather than a count of a collection no strip shows.
        self.assertEqual([None, None, None], out["held"])
        self.assertIsNone(out["heldAbsent"])
        # A collection the board never published is not a collection read and
        # found empty, and neither is 0.
        for absent in ("courseAbsent", "decisionsAbsent"):
            with self.subTest(absent=absent):
                self.assertEqual({"state": "unobserved"}, out[absent])

    def test_the_pending_mark_and_the_never_observed_mark_are_different(self) -> None:
        """AC-5. Falsified by the two states rendering the same mark or the same
        gloss."""
        out = self.run_fixture(
            """
const group = nextProjectGroups()[0];
const projectKey = nextCockpitContextKey(group, null);
// Withhold the context entry so the Decisions panel takes the
// "Loading semantic context…" arm the cue has to agree with.
nextCockpitContexts.clear();
const pending = nextCockpitTabCue("decisions", {group, project:{key:"cargento"}},
  {harness:"codex", sid:"focus-1"});
// The entry arrived and published no facts: read, and empty-handed.
nextCockpitContexts.set(projectKey, {data:{semantic:{work_items:[], projections:{}}},
  revision:105});
const unobserved = nextCockpitTabCue("decisions", {group, project:{key:"cargento"}}, null);
// The read FINISHED and failed. `nextCockpitLoadContext`'s catch is the only
// writer of `error`, and this is the exact record it stores.
nextCockpitContexts.set(projectKey, {data:null, revision:105, error:true});
const unavailable = nextCockpitTabCue("decisions", {group, project:{key:"cargento"}}, null);
const panelUnavailable = nextCockpitTimeline(group, null)
  .includes("Semantic context unavailable.");
console.log(JSON.stringify({pending, unobserved, unavailable, panelUnavailable,
  pendingHtml:nextCockpitTabCueHtml("decisions", pending),
  unobservedHtml:nextCockpitTabCueHtml("decisions", unobserved),
  unavailableHtml:nextCockpitTabCueHtml("decisions", unavailable),
  countHtml:nextCockpitTabCueHtml("decisions", {state:"count", value:2})}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual({"state": "pending"}, out["pending"])
        self.assertEqual({"state": "unobserved"}, out["unobserved"])
        # A read that FINISHED and failed is neither. The cue reported it as
        # `pending` -- "decisions not loaded yet", about a read that was over --
        # beside a panel already saying "Semantic context unavailable."; the two
        # now resolve one `nextCockpitContextRead`, so they cannot disagree
        # about what state the read is in.
        self.assertEqual({"state": "unavailable"}, out["unavailable"])
        self.assertTrue(out["panelUnavailable"], "the panel did not take its failed arm")
        marks = {}
        glosses = {}
        for key in ("pendingHtml", "unobservedHtml", "unavailableHtml", "countHtml"):
            html = out[key]
            assert isinstance(html, str)
            mark = re.search(r'aria-hidden="true">([^<]*)<', html)
            gloss = re.search(r'class="next-visually-hidden">([^<]*)<', html)
            self.assertIsNotNone(mark, f"{key} renders no mark")
            self.assertIsNotNone(gloss, f"{key} renders no gloss")
            assert mark is not None and gloss is not None
            marks[key] = mark.group(1)
            glosses[key] = gloss.group(1)
        self.assertEqual("…", marks["pendingHtml"])
        self.assertEqual("·", marks["unobservedHtml"])
        self.assertEqual("—", marks["unavailableHtml"])
        self.assertEqual(4, len(set(marks.values())))
        self.assertEqual(4, len(set(glosses.values())))
        self.assertIn("next-cockpit-tab-cue--pending", out["pendingHtml"])
        # Every non-count state names its own variant. One that fell through to
        # "" would inherit the cue's `--ink2`, the ink a real figure gets.
        self.assertIn("next-cockpit-tab-cue--unavailable", out["unavailableHtml"])
        self.assertIn("next-cockpit-tab-cue--unobserved", out["unobservedHtml"])

    def test_now_console_and_unannotated_held_to_render_no_cue_element(self) -> None:
        """AC-6. Falsified by an empty cue span, a 0, or a · on any of the three."""
        out = self.run_fixture(
            """
const group = nextProjectGroups()[0];
const context = {group, project:{key:"cargento", changes:[]}};
nextData.annotate = false;
const cues = {
  now:nextCockpitTabCue("now", context, null, null),
  console:nextCockpitTabCue("console", context, null, null),
  heldOff:nextCockpitTabCue("held-to", context,
    {harness:"codex", sid:"focus-1", departures:[{id:"r"}]}, null)
};
navigateNext({view:"project",project:"cargento",focus:"codex:focus-1",tab:"now"});
await __settle();
const strip = (__els.app.innerHTML.match(/<nav class="next-cockpit-tabs"[\\s\\S]*?<\\/nav>/) || [""])[0];
const buttons = Object.fromEntries([...strip.matchAll(/<button[^>]*data-arg="([^"]+)"[^>]*>([\\s\\S]*?)<\\/button>/g)]
  .map(match => [match[1], match[2]]));
console.log(JSON.stringify({cues, buttons,
  html:Object.fromEntries(Object.entries(cues).map(([k, v]) => [k, nextCockpitTabCueHtml(k, v)]))}));
"""
        )
        assert isinstance(out, dict)
        for tab in ("now", "console", "heldOff"):
            with self.subTest(tab=tab):
                self.assertIsNone(out["cues"][tab])
                self.assertEqual("", out["html"][tab])
        for tab in ("now", "console"):
            with self.subTest(button=tab):
                self.assertNotIn("next-cockpit-tab-cue", out["buttons"][tab])

    def test_the_strip_still_takes_its_tab_set_from_the_route(self) -> None:
        """AC-7. Falsified by resolving the strip's tab set from the passed focus
        argument instead of the route, which makes the nav and the panel
        disagree on a stale route."""
        out = self.run_fixture(
            """
const group = nextProjectGroups()[0];
const context = {group, project:{key:"cargento", changes:[]}};
const focus = group.sessions[0];
navigateNext({view:"project",project:"cargento",focus:null,tab:"now"});
await __settle();
// The route has no focus; a session is handed in anyway. The nav must answer
// four, the same as the panel, or a stale route splits them.
const atProject = nextCockpitTabList(context, focus, null);
navigateNext({view:"project",project:"cargento",focus:"codex:focus-1",tab:"now"});
await __settle();
const atSession = nextCockpitTabList(context, null, null);
const args = html => [...html.matchAll(/data-arg="([^"]+)"/g)].map(m => m[1]);
console.log(JSON.stringify({atProject:args(atProject), atSession:args(atSession)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(["now", "course", "decisions", "console"], out["atProject"])
        # Held to merged into the session page (DRC-4639), so both scopes answer
        # four; the route is still the source, which the stale case above binds.
        self.assertEqual(["now", "course", "decisions", "console"], out["atSession"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitTimelineFilterTest(NextPageJsHarness):
    """DRC-4598. The Decisions tab is one of three modes of a renderer whose own
    three-button filter the cockpit switched off, so the filtered activity view
    and the all-events view were reachable nowhere in the next UI.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE
    FOCUS_DOM = NextCockpitCompositionTest.FOCUS_DOM
    # Mirrored from next-cockpit.js; the first check below pins the two together.
    KEY = "cargento.next.graph.mode"

    # A SECOND project, because the per-project criterion is not expressible on
    # a board with one. Built by appending a session to the shared fixture's
    # payload rather than by writing a second fixture, so the two boards cannot
    # drift apart in anything but the thing under test.
    TWO_PROJECT_FIXTURE: ClassVar[str] = (
        NextCockpitCompositionTest.FIXTURE
        + """
__dashboard.sessions.push({sid:"infra-1", harness:"claude", project:"recce-cloud-infra",
  project_key:"recce/recce-cloud-infra", state:"working", active:true,
  last_activity:104, title:"Rotate the SSO role", subagents:[]});
"""
    )

    def run_fixture(self, checks: str, *, storage: dict[str, str] | None = None) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + self.FOCUS_DOM + checks,
            storage_prelude(storage or {}) + self.FIXTURE,
        )

    def test_the_decisions_panel_carries_the_filter_and_a_press_changes_the_mode(self) -> None:
        """AC-1. Falsified by the panel rendering no filter, or a press that
        leaves data-graph-mode unchanged after a redraw."""
        out = self.run_fixture(
            r"""
navigateNext({view:"project",project:"cargento",focus:null,tab:"decisions"});
await __settle(); await __settle();
const before = __els.app.innerHTML;
const filter = (before.match(/<div class="pc-graph-filter"[\s\S]*?<\/div>/) || [""])[0];
const buttons = [...filter.matchAll(/data-next-cockpit-action="graph-mode"[^>]*data-arg="([^"]+)"/g)]
  .map(match => match[1]);
const mode = html => (html.match(/data-graph-mode="([^"]+)"/) || [])[1] || "";
const rows = html => (html.match(/class="pc-graph-row/g) || []).length;
const press = value => {
  const button = controls.find(c => c.dataset.nextCockpitAction === "graph-mode" &&
    c.dataset.arg === value);
  __fire("click",{target:button,preventDefault(){}});
};
press("all");
await __settle();
const afterAll = __els.app.innerHTML;
press("decisions");
await __settle();
const afterDecisions = __els.app.innerHTML;
console.log(JSON.stringify({buttons, hasFilter:Boolean(filter),
  pressed:[...filter.matchAll(/aria-pressed="([^"]+)"/g)].map(m => m[1]),
  modes:[mode(before), mode(afterAll), mode(afterDecisions)],
  rows:[rows(before), rows(afterAll), rows(afterDecisions)]}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["hasFilter"])
        self.assertEqual(["active", "all", "decisions"], out["buttons"])
        self.assertEqual(["false", "false", "true"], out["pressed"])
        self.assertEqual(["decisions", "all", "decisions"], out["modes"])
        self.assertNotEqual(out["rows"][0], out["rows"][1])
        self.assertEqual(out["rows"][0], out["rows"][2])

    def test_the_panel_heading_names_the_mode_on_screen(self) -> None:
        """AC-3. Falsified by a heading that keeps saying RECORDED DECISIONS over
        an all-events list."""
        out = self.run_fixture(
            r"""
navigateNext({view:"project",project:"cargento",focus:null,tab:"decisions"});
await __settle(); await __settle();
const head = html => (html.match(/<section class="next-cockpit-semantic"[^>]*><h2>([^<]*)<\/h2>/) || [])[1] || "";
const press = value => {
  const button = controls.find(c => c.dataset.nextCockpitAction === "graph-mode" &&
    c.dataset.arg === value);
  __fire("click",{target:button,preventDefault(){}});
};
const before = head(__els.app.innerHTML);
press("all"); await __settle();
const all = head(__els.app.innerHTML);
press("decisions"); await __settle();
console.log(JSON.stringify({before, all, back:head(__els.app.innerHTML)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual("RECORDED DECISIONS", out["before"])
        self.assertEqual("SEMANTIC TIMELINE", out["all"])
        self.assertEqual("RECORDED DECISIONS", out["back"])

    def test_the_chosen_mode_is_written_to_storage_and_read_back_on_load(self) -> None:
        """AC-4. Falsified by a press that writes nothing, or a seeded store the
        first render ignores.

        Run on the TWO-project board, not patched. This test seeded the empty
        key and asserted the first render took it -- the collided key written
        down as the expected result, and on a one-project fixture that key
        reads as "project scope" rather than as "every project", so the oracle
        could not tell the two apart. Changing the seed alone would have left a
        one-project board asserting a per-project property.

        The seed is now a real key for a real project, and a SECOND project is
        on the board to prove the seed reaches the one it names and no other.
        """
        written = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + self.FOCUS_DOM
            + r"""
navigateNext({view:"project",project:"cargento",focus:null,tab:"decisions"});
await __settle(); await __settle();
const button = controls.find(c => c.dataset.nextCockpitAction === "graph-mode" &&
  c.dataset.arg === "all");
__fire("click",{target:button,preventDefault(){}});
await __settle();
console.log(JSON.stringify({writes:__storageWrites, store:__store}));
""",
            storage_prelude({}) + self.TWO_PROJECT_FIXTURE,
        )
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        self.assertIn(f'"{self.KEY}"', (web / "project.js").read_text(encoding="utf-8"))
        assert isinstance(written, dict)
        keys = [key for key in written["writes"] if key.startswith("cargento.next.")]
        self.assertIn(self.KEY, keys)
        self.assertIn("all", written["store"][self.KEY])

        seeded = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + self.FOCUS_DOM
            + r"""
const read = async project => {
  navigateNext({view:"project",project,focus:null,tab:"decisions"});
  await __settle(); await __settle();
  return (__els.app.innerHTML.match(/data-graph-mode="([^"]+)"/) || [])[1];
};
console.log(JSON.stringify({seeded: await read("cargento"),
  other: await read("recce-cloud-infra")}));
""",
            storage_prelude({self.KEY: json.dumps({"cargento" + NUL_CHAR: "all"})})
            + self.TWO_PROJECT_FIXTURE,
        )
        assert isinstance(seeded, dict)
        self.assertEqual("all", seeded["seeded"], "the seeded project did not take its mode")
        self.assertEqual(
            "decisions",
            seeded["other"],
            "a seeded mode reached a project the seed does not name",
        )

    def test_two_sessions_in_one_project_keep_their_own_modes(self) -> None:
        """The half a project-only key would destroy, and the reason the key
        carries BOTH halves.

        The resolver reads a per-session distinction at session scope: the
        filter is drawn on a focused board too, and a mode chosen while looking
        at one session is that session's. Keying by project alone fixes the
        cross-project collision and silently collapses this one -- measured,
        that mutant passes every other test in this class, which is why this
        one exists.

        Three scopes on one project, each pressed to a different mode, each
        read back after visiting the others.
        """
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + self.FOCUS_DOM
            + r"""
const open = async focus => {
  navigateNext({view:"project",project:"cargento",focus,tab:"decisions"});
  await __settle(); await __settle();
  return (__els.app.innerHTML.match(/data-graph-mode="([^"]+)"/) || [])[1];
};
const press = value => {
  const button = controls.find(c => c.dataset.nextCockpitAction === "graph-mode" &&
    c.dataset.arg === value);
  if(!button) throw new Error("no graph-mode button for " + value);
  __fire("click",{target:button,preventDefault(){}});
};
await open(null); press("all"); await __settle();
await open("codex:focus-1"); press("active"); await __settle();
await open("claude:claude-idle"); press("decisions"); await __settle();
// Read every scope back, after each has been left and returned to.
const after = {project: await open(null), focus1: await open("codex:focus-1"),
  idle: await open("claude:claude-idle")};
console.log(JSON.stringify({after,
  store: JSON.parse(__store["cargento.next.graph.mode"] || "{}")}));
""",
            storage_prelude({}) + self.TWO_PROJECT_FIXTURE,
        )
        assert isinstance(out, dict)
        self.assertEqual(
            {"project": "all", "focus1": "active", "idle": "decisions"},
            out["after"],
            "one scope's press reached another scope in the same project",
        )
        store = out["store"]
        assert isinstance(store, dict)
        self.assertEqual(
            {
                "cargento" + NUL_CHAR: "all",
                "cargento" + NUL_CHAR + "codex:focus-1": "active",
                "cargento" + NUL_CHAR + "claude:claude-idle": "decisions",
            },
            store,
        )

    def test_a_key_shape_this_build_cannot_parse_is_dropped_on_load(self) -> None:
        """The migration, which is the half a new key scheme quietly skips.

        A browser that already ran this branch holds every project's choice
        under ONE empty key. `projectLoadGraphModes` validated VALUES and not
        key shapes, so a scheme where that empty key parses as a real project
        would hand the old collision straight to the new one. It is dropped at
        load instead, once, rather than defended against at each read site.
        """
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + self.FOCUS_DOM
            + r"""
const read = async project => {
  navigateNext({view:"project",project,focus:null,tab:"decisions"});
  await __settle(); await __settle();
  return (__els.app.innerHTML.match(/data-graph-mode="([^"]+)"/) || [])[1];
};
const modes = {cargento: await read("cargento"), infra: await read("recce-cloud-infra")};
// And the legacy entry does not survive the next write either.
const button = controls.find(c => c.dataset.nextCockpitAction === "graph-mode" &&
  c.dataset.arg === "active");
__fire("click",{target:button,preventDefault(){}});
await __settle();
console.log(JSON.stringify({modes,
  store: JSON.parse(__store["cargento.next.graph.mode"] || "{}")}));
""",
            storage_prelude({self.KEY: json.dumps({"": "all"})}) + self.TWO_PROJECT_FIXTURE,
        )
        assert isinstance(out, dict)
        # Neither project inherits the legacy entry.
        self.assertEqual({"cargento": "decisions", "infra": "decisions"}, out["modes"])
        store = out["store"]
        assert isinstance(store, dict)
        self.assertNotIn("", store, "the legacy collided key survived a load and a write")
        self.assertEqual({"recce-cloud-infra" + NUL_CHAR: "active"}, store)

    def test_a_mode_pressed_on_one_project_does_not_follow_the_reader_to_another(
        self,
    ) -> None:
        """AC-2, on a board with TWO projects, which is the only board that can
        show it.

        `projectQuerySession` is "" at project scope for every project, so the
        map held one entry for all of them -- and this branch mirrors that map
        to `localStorage`, which turned a per-tab quirk into a persisted one.
        Reproduced on a live board before the fix: "All events" pressed on
        `cargento`, then `recce-cloud-infra` opened for the first time, drew
        `data-graph-mode="all"` under a SEMANTIC TIMELINE heading with the store
        reading `{"": "all"}`.

        **Both directions, deliberately.** A fix that namespaces the write but
        resolves the fallback from the other scope passes the first half and
        fails the second, so pressing on the second project and returning to the
        first is the half that catches it.

        Neither a stronger assertion nor a wider mutation on the single-project
        fixture could have found this: a defect that needs two projects to be
        visible is invisible to a one-project board at any width. The fixture's
        SHAPE is the oracle here.
        """
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + self.FOCUS_DOM
            + r"""
const press = value => {
  const button = controls.find(c => c.dataset.nextCockpitAction === "graph-mode" &&
    c.dataset.arg === value);
  if(!button) throw new Error("no graph-mode button for " + value);
  __fire("click",{target:button,preventDefault(){}});
};
const open = async project => {
  navigateNext({view:"project",project,focus:null,tab:"decisions"});
  await __settle(); await __settle();
  return (__els.app.innerHTML.match(/data-graph-mode="([^"]+)"/) || [])[1] || "";
};
const first = await open("cargento");
press("all");
await __settle();
const firstAfterPress = await open("cargento");
// A project this reader has never pressed anything on.
const secondUntouched = await open("recce-cloud-infra");
press("active");
await __settle();
const secondAfterPress = await open("recce-cloud-infra");
// Back to the first: its own choice must have survived the second's press.
const firstOnReturn = await open("cargento");
console.log(JSON.stringify({first, firstAfterPress, secondUntouched,
  secondAfterPress, firstOnReturn,
  store:JSON.parse(__store["cargento.next.graph.mode"] || "{}")}));
""",
            storage_prelude({}) + self.TWO_PROJECT_FIXTURE,
        )
        assert isinstance(out, dict)
        # The Decisions tab opens on decisions for both, untouched.
        self.assertEqual("decisions", out["first"])
        self.assertEqual("all", out["firstAfterPress"])
        self.assertEqual(
            "decisions",
            out["secondUntouched"],
            "a mode pressed on one project followed the reader to another",
        )
        self.assertEqual("active", out["secondAfterPress"])
        self.assertEqual(
            "all",
            out["firstOnReturn"],
            "the second project's press overwrote the first project's choice",
        )
        # And the persisted shape: one entry per scope, none of them the
        # collided empty key.
        store = out["store"]
        assert isinstance(store, dict)
        self.assertEqual(
            {"cargento" + NUL_CHAR: "all", "recce-cloud-infra" + NUL_CHAR: "active"},
            store,
        )
        self.assertNotIn("", store)

    def test_the_dead_scope_helper_is_gone_and_its_neighbour_survives(self) -> None:
        """AC-5. Falsified by deleting the wrong name, which takes
        nextCockpitProjectScopeKind with it."""
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        sources = {path.name: path.read_text(encoding="utf-8") for path in web.glob("*.js")}
        joined = "\n".join(sources.values())
        self.assertNotIn("nextCockpitProjectScope(", joined)
        # Fifteen, not the sixteen triage counted: one of those sites was the
        # call inside the dead helper this change deletes. A grep-and-delete on
        # the shorter name is a prefix match on the longer one and would take
        # every remaining site with it.
        self.assertGreaterEqual(joined.count("nextCockpitProjectScopeKind("), 15)

    def test_nui_3_states_that_retiring_a_tab_slug_is_a_route_change(self) -> None:
        """AC-6. Falsified by the section not saying it, or saying it somewhere a
        merge proposal would not read."""
        doc = (
            pathlib.Path(__file__).resolve().parents[4] / "docs" / "design-next-ui.md"
        ).read_text(encoding="utf-8")
        heads = [index for index, line in enumerate(doc.splitlines()) if line.startswith("## ")]
        lines = doc.splitlines()
        start = next(index for index in heads if "NUI-3" in lines[index])
        end = next((index for index in heads if index > start), len(lines))
        section = "\n".join(lines[start:end])
        self.assertIn("route change", section)
        self.assertIn("nextRouteFromFragment", section)
        self.assertIn("alias table", section)

    def test_no_route_slug_and_no_fragment_behaviour_changes(self) -> None:
        """AC-7. Falsified by any edit to NEXT_PROJECT_TABS, NEXT_SESSION_TABS or
        nextRouteFromFragment."""
        boot = (
            pathlib.Path(__file__).resolve().parents[1]
            / "cargento_runtime"
            / "web"
            / "next-boot.js"
        ).read_text(encoding="utf-8")
        self.assertIn('const NEXT_PROJECT_TABS = ["now", "course", "decisions", "console"];', boot)
        # Held to retired into the session page (DRC-4639): the session tab list is
        # empty and its slug is an alias, not a tab.
        self.assertIn("const NEXT_SESSION_TABS = [];", boot)
        self.assertIn('const NEXT_RETIRED_SESSION_TAB = "held-to";', boot)
        out = self.run_fixture(
            r"""
const routes = ["#n=project:cargento:decisions", "#n=project:cargento:codex%3Afocus-1:held-to",
  "#n=project:cargento", "#n=project:cargento:codex%3Afocus-1"].map(hash => {
    const route = nextRouteFromFragment(hash);
    return {view:route.view || null, project:route.project || null,
      focus:route.focus || null, tab:route.tab || null};
  });
const round = nextFragmentForRoute({view:"project",project:"cargento",
  focus:"codex:focus-1",tab:"held-to"});
console.log(JSON.stringify({routes, round}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(
            [
                {"view": "project", "project": "cargento", "focus": None, "tab": "decisions"},
                # The retired slug opens that session's page (NUI-3's alias).
                {"view": "session", "project": "cargento", "focus": None, "tab": None},
                {"view": "project", "project": "cargento", "focus": None, "tab": None},
                {
                    "view": "project",
                    "project": "cargento",
                    "focus": "codex:focus-1",
                    "tab": None,
                },
            ],
            out["routes"],
        )
        self.assertEqual("#n=session:cargento:codex:focus-1", out["round"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CockpitScopeRailCardTest(NextPageJsHarness):
    """DRC-4597. The rail card led with the harness and the state and put the
    session's own title last and smallest, so the only string that tells one
    card from another was the least prominent one in it.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    GROUP = r"""
const mixed = {label:"cargento", sessions:[
  {harness:"claude", sid:"c1", state:"idle", title:"Quiet lane", last_activity:40},
  {harness:"codex", sid:"w1", state:"working", title:"Live lane", tone:"want",
    last_activity:100}
]};
const single = {label:"cargento", sessions:[
  {harness:"claude", sid:"c1", state:"idle", title:"First lane", last_activity:40},
  {harness:"claude", sid:"c2", state:"idle", title:"Second lane", last_activity:60}
]};
const twins = {label:"cargento", sessions:[
  {harness:"claude", sid:"t1", state:"idle", last_activity:40},
  {harness:"claude", sid:"t2", state:"idle", last_activity:40}
]};
const rows = html => [...html.matchAll(/<a\s+([^>]+)>([\s\S]*?)<\/a>/g)]
  .map(match => ({attrs:match[1], body:match[2]}));
const slot = (body, name) => {
  const open = `class="next-cockpit-scope-${name}"`;
  const at = body.indexOf(open);
  if(at < 0) return "";
  const from = body.indexOf(">", at) + 1;
  const tail = name === "meta" ? body.slice(from).replace(/<\/span>\s*$/, "") :
    body.slice(from, body.indexOf("</span>", from));
  return tail.replace(/<[^>]+>/g, "").trim();
};
"""

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + self.GROUP + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    def test_the_title_is_line_one_and_the_meta_is_line_two(self) -> None:
        """AC-1. Falsified by restoring the <small> title after the state span,
        or letting the title and the meta resolve to the same size or ink."""
        out = self.run_fixture(
            r"""
const html = nextCockpitScopeLinks(mixed, null);
const sessions = rows(html).filter(row => row.attrs.includes('data-scope-kind="session"'));
console.log(JSON.stringify({count:sessions.length, cards:sessions.map(row => ({
  titleAt:row.body.indexOf('class="next-cockpit-scope-title"'),
  metaAt:row.body.indexOf('class="next-cockpit-scope-meta"'),
  title:slot(row.body, "title"), meta:slot(row.body, "meta")
}))}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(2, out["count"])
        for card in out["cards"]:
            self.assertGreater(card["titleAt"], -1)
            self.assertGreater(card["metaAt"], card["titleAt"])
        self.assertEqual("Live lane", out["cards"][0]["title"])
        self.assertIn("Codex", out["cards"][0]["meta"])
        self.assertIn("working", out["cards"][0]["meta"])

    def test_the_kind_is_stated_in_words_once_per_group(self) -> None:
        """AC-2. Falsified by deleting the hidden span, hard-coding the count, or
        reinstating the visible per-row cue."""
        out = self.run_fixture(
            r"""
const html = nextCockpitScopeLinks(mixed, null);
const all = rows(html);
const sessions = all.filter(row => row.attrs.includes('data-scope-kind="session"'));
console.log(JSON.stringify({
  cuesOnSessions:sessions.filter(row => row.body.includes('class="next-scope-cue')).length,
  hiddenSession:sessions.map(row =>
    (row.body.match(/class="next-visually-hidden">([^<]*)<\/span>/) || [])[1] || ""),
  markers:sessions.filter(row => row.body.includes("next-scope-marker--round")).length,
  projectCue:all[0].body.includes('class="next-scope-cue'),
  projectMeta:slot(all[0].body, "meta"),
  expected:`${mixed.sessions.length} sessions`,
  /* Counted across group SIZES, because every fixture in this class holds
     exactly two sessions and `esc("2 sessions")` therefore satisfies a
     derivation asserted on one of them. Measured: that literal survived all
     564 tests in the group with the substitution proved applied, and "derived"
     is this criterion's central word. Sizes 1, 2 and 4 also put the
     singular/plural on both arms. */
  sized:[1, 2, 4].map(size => slot(rows(nextCockpitScopeLinks({label:"cargento",
    sessions:Array.from({length:size}, (_, i) => ({harness:"claude", sid:`s${i}`,
      state:"idle", title:`Lane ${i}`, last_activity:40 + i}))}, null))[0].body, "meta"))
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(0, out["cuesOnSessions"])
        self.assertEqual(["SESSION", "SESSION"], out["hiddenSession"])
        self.assertEqual(2, out["markers"])
        self.assertTrue(out["projectCue"])
        self.assertEqual(out["expected"], out["projectMeta"])
        # No single literal satisfies all three, which is the whole point.
        self.assertEqual(["1 session", "2 sessions", "4 sessions"], out["sized"])

    def test_the_harness_hoists_only_when_every_row_shares_one(self) -> None:
        """AC-3. Falsified by hoisting on a mixed-harness group, or keeping the
        per-row harness on a single-harness group."""
        out = self.run_fixture(
            r"""
const draw = group => nextCockpitScopeTree(group, null);
const count = (html, needle) => html.split(needle).length - 1;
const singleHtml = draw(single);
const mixedHtml = draw(mixed);
const heading = html => (html.match(/class="next-cockpit-scope-heading">([^<]*)<\/span>/) || [])[1] || "";
console.log(JSON.stringify({
  singleHeading:heading(singleHtml), mixedHeading:heading(mixedHtml),
  singleClaude:count(singleHtml, "Claude"), mixedClaude:count(mixedHtml, "Claude"),
  mixedCodex:count(mixedHtml, "Codex"),
  switcherHeading:heading(nextCockpitScopeSwitcher(single, null))
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual("SCOPE · Claude", out["singleHeading"])
        self.assertEqual("SCOPE", out["mixedHeading"])
        # Once in the heading and on no row.
        self.assertEqual(1, out["singleClaude"])
        self.assertEqual(1, out["mixedClaude"])
        self.assertEqual(1, out["mixedCodex"])
        self.assertEqual("SCOPE · Claude", out["switcherHeading"])

    def test_a_withheld_title_is_marked_on_twin_rows_too(self) -> None:
        """AC-4. Falsified by re-appending the sid to the title string, or a
        second [data-next-withheld] colour rule reappearing."""
        out = self.run_fixture(
            r"""
const html = nextCockpitScopeLinks(twins, null);
const sessions = rows(html).filter(row => row.attrs.includes('data-scope-kind="session"'));
console.log(JSON.stringify({
  marked:sessions.filter(row => row.body.includes("data-next-withheld")).length,
  titles:sessions.map(row => slot(row.body, "title")),
  metas:sessions.map(row => slot(row.body, "meta"))
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(2, out["marked"])
        self.assertEqual(
            ["Session title not published", "Session title not published"], out["titles"]
        )
        for meta, sid in zip(out["metas"], ("t1", "t2"), strict=True):
            self.assertTrue(meta.endswith(sid), f"the twin sid is not last on the meta: {meta!r}")

        styles = (
            pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"
        ).read_text(encoding="utf-8")
        coloured = [
            block
            for block in re.finditer(
                r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", styles, flags=re.DOTALL)
            )
            if "[data-next-withheld]" in block.group(1) and "color:" in block.group(2)
        ]
        # Two rules colour it, and both must resolve through DRC-4589's absence
        # register. The criterion was drafted as "exactly one", on the reading
        # that the rail override merely restated the base rule; this issue's own
        # change refuted that, by moving the attribute onto
        # `span.next-cockpit-scope-title`, which declares `color:var(--ink)` at
        # the same (0,1,0) specificity and later in the sheet. With the override
        # stripped, a withheld title rendered in full ink -- see
        # `WithheldTitleKeepsTheAbsenceInkTest`, which resolves the pair.
        self.assertNotEqual([], coloured)
        for block in coloured:
            with self.subTest(rule=block.group(1).strip()[:60]):
                self.assertIn("color:var(--ink-absence)", block.group(2))
        rail = re.search(
            r"\.next-cockpit-scope-tree \[data-next-withheld\][^{]*\{([^}]*)\}", styles
        )
        self.assertIsNotNone(rail)
        self.assertEqual(
            "font-family:var(--sans);color:var(--ink-absence)",
            (rail.group(1) if rail else "").strip(),
        )

    def test_the_card_keeps_its_target_size_and_selection_on_both_surfaces(self) -> None:
        """AC-5. Falsified by a min-block-size override in the new card rules, or
        a card shape that renders only in the tree and breaks in the disclosure."""
        out = self.run_fixture(
            r"""
const focus = single.sessions[1];
const tree = nextCockpitScopeLinks(single, focus);
const switcher = nextCockpitScopeLinks(single, focus, "switcher");
const current = html => rows(html).filter(row => row.attrs.includes('aria-current="page"')).length;
const shape = html => rows(html).filter(row => row.attrs.includes('data-scope-kind="session"'))
  .every(row => row.body.includes('class="next-cockpit-scope-title"') &&
    row.body.includes('class="next-cockpit-scope-meta"'));
console.log(JSON.stringify({treeCurrent:current(tree), switcherCurrent:current(switcher),
  treeShape:shape(tree), switcherShape:shape(switcher),
  switcherFocus:switcher.includes('data-next-focus="cockpit-scope:switcher:')}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(1, out["treeCurrent"])
        self.assertEqual(1, out["switcherCurrent"])
        self.assertTrue(out["treeShape"])
        self.assertTrue(out["switcherShape"])
        self.assertTrue(out["switcherFocus"])

        styles = (
            pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"
        ).read_text(encoding="utf-8")
        self.assertIn("min-block-size:44px", styles)
        selected = re.search(
            r'\.next-cockpit-scope-tree a\[aria-current="page"\][^{]*\{([^}]*)\}', styles
        )
        self.assertIsNotNone(selected)
        self.assertIn("box-shadow:inset 2px 0", selected.group(1) if selected else "")
        # Nothing in the new card rules may take the target size back.
        for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", styles):
            if "next-cockpit-scope-title" in block.group(
                1
            ) or "next-cockpit-scope-meta" in block.group(1):
                self.assertNotIn("min-block-size", block.group(2))


@unittest.skipUnless(shutil.which("node"), "node not available")
class CaveatTieringTest(NextPageJsHarness):
    """DRC-4591. Three tiers, and nothing deleted.

    Every caveat on this tab used to render as one paragraph in the reading
    flow. The claim now stays inline and the rest goes behind a summary whose
    open state survives a redraw. What is asserted is that no sentence left the
    page, that no figure moved behind a click, and that the disclosure is the
    board's own redraw-safe one rather than a bare `<details>`.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    # The four caveat sentences that exist on the pre-change tree. AC-1 is that
    # each still reaches `innerHTML` -- a closed `<details>` contributes its
    # body to markup, so no browser is needed to read one.
    COUNTS_CLAIM = "Five figures, and no arithmetic between them."
    COUNTS_WHY = (
        "A count identifies a session worth reading; it establishes nothing about whether "
        "the brief, the agent or Cargento\u2019s own judgement was poor, and those three are "
        "not separable from it."
    )
    STEER_CLAIM = "Raised to you and nowhere else."
    STEER_WHY = (
        "Cargento does not write into a session, so steering is by hand; the steer box in "
        "Console states the same rule about notes you write there."
    )
    LANDED_CLAIM = "Neither card implies the other."

    def held(self, setup: str = "") -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "__dashboard.annotate = true;\n__dashboard.annotate_cap = 240;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            # The lane on, so the departures section these caveats live in renders: with it off
            # and nothing on record the section is absent (DRC-4543). A setup may delete it.
            "__dashboard.unasked = true;\n"
            + setup
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  html,
  counts: (html.match(
    /<div class="next-cockpit-departure-part"><span class="next-cockpit-departure-label">COUNTS[\\s\\S]*?<\\/details><\\/div>|<div class="next-cockpit-departure-part"><span class="next-cockpit-departure-label">COUNTS[\\s\\S]*?<\\/div><\\/div>/) || [""])[0],
  landed: (html.match(
    /<section class="next-cockpit-landed">[\\s\\S]*?<\\/section>/) || [""])[0],
  departures: (html.match(
    /<section class="next-cockpit-departures">[\\s\\S]*?<\\/section>/) || [""])[0],
  reading: (html.match(
    /<div class="next-session-drift-check">[\\s\\S]*?<section class="next-cockpit-reading">[\\s\\S]*?<\\/section>/) || [""])[0],
}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    # Derived, not selected. Every constant caveat sentence the PRE-CHANGE tree
    # puts inside a `next-cockpit-reading-why`, taken from the merge base:
    #
    #   git show 21a0e935289ea64c963d4664daf7abab12c9866d:\
    #     cargento/skills/cargento/cargento_runtime/web/next-cockpit.js > base.js
    #
    # then, from the repository root, sort what `reading_why_sentences` yields
    # over `base.js` -- which is exactly what the test below does for you,
    # against the same revision, whenever the blob is reachable.
    #
    # Re-running that command must reproduce this tuple exactly; the test below
    # runs it for you whenever the base blob is reachable. AC-1's claim is
    # "every caveat sentence on the pre-change tree still exists verbatim", and
    # it was verified over five strings against roughly twenty-three emission
    # sites -- a selection, which cannot fail on what it left out. What the
    # derivation buys is that a sentence deleted from a site nobody listed reds
    # this test. What it does not reach is a paragraph assembled through
    # `${...}`: the text is not in the file, so it is out of scope here and is
    # covered instead by `HeldToPositionalSentencesTest`, which reads the
    # rendered page.
    BASE_REVISION = "21a0e935289ea64c963d4664daf7abab12c9866d"
    BASE_CAVEAT_SENTENCES: ClassVar[tuple[str, ...]] = (
        (
            "A count identifies a session worth reading; it establishes nothing about "
            "whether the brief, the agent or Cargento\u2019s own judgement was poor, and "
            "those three are not separable from it."
        ),
        "A reading is stored for this session and this build could not read it, so nothing from it is shown.",
        "Five figures, and no arithmetic between them.",
        "Neither card implies the other.",
        "No reading has been made at your request, so nothing has been raised from one.",
        "Nothing watches for a departure on its own.",
        "Start with --unasked-readings to have Cargento check a session against what you asked for while you are away.",
        "The reading raised no departure from the revision it read.",
        "This session was not in the observed payload, so nothing here says how it ended.",
    )

    # The three the fixture arms cannot reach, each with the state it needs and
    # none of it reachable without a stored reading or a doctored payload. They
    # are still held to the verbatim half above; what is declared here is only
    # that nothing rendered them, so the render loop cannot quietly shrink to
    # nothing while reporting success.
    UNRENDERED_CAVEATS: ClassVar[frozenset[str]] = frozenset(
        {
            (
                "A reading is stored for this session and this build could not read it, "
                "so nothing from it is shown."
            ),
            "The reading raised no departure from the revision it read.",
            "This session was not in the observed payload, so nothing here says how it ended.",
        }
    )

    def test_the_base_sentence_list_is_what_the_command_derives(self) -> None:
        """The difference between a derivation and a longer list.

        Skipped rather than failed where the base blob is unreachable: CI
        checks out at depth 1, and a test that cannot read the revision it
        names has nothing to say about it. Locally it is the guarantee that the
        tuple above was not edited by hand.
        """
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        blob = f"{self.BASE_REVISION}:cargento/skills/cargento/cargento_runtime/web/next-cockpit.js"
        try:
            base = subprocess.run(
                # Fixed argv and no shell; git is on PATH in every dev and CI image.
                ["git", "show", blob],  # noqa: S607
                capture_output=True,
                check=True,
                cwd=web,
                text=True,
                timeout=30,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            self.skipTest(f"{self.BASE_REVISION} is not in this clone")
        self.assertEqual(set(self.BASE_CAVEAT_SENTENCES), reading_why_sentences(base))

    def test_every_caveat_sentence_survives_the_tiering(self) -> None:
        """AC-1, over the derived set. Falsified by deleting or paraphrasing any
        sentence the pre-change tree stated, at any of its emission sites.

        Two halves, because the strong one cannot cover every sentence. The
        verbatim check reaches all of them and is what makes the set worth
        deriving; the rendered check reaches the ones a fixture can reach and is
        what proves a surviving string is still on the page rather than only in
        the file.
        """
        self.assertNotEqual((), self.BASE_CAVEAT_SENTENCES)
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        current = (web / "next-cockpit.js").read_text(encoding="utf-8")
        emitted = "\n".join(" ".join(run.split()) for run in emitted_strings(current))
        for sentence in self.BASE_CAVEAT_SENTENCES:
            with self.subTest(sentence=sentence[:40]):
                self.assertIn(sentence, emitted)

        # Two boards: the lane on, and the lane off with a raise standing, which is the one
        # state the lane-off instruction renders in now that an empty off board draws no
        # departures section.
        html = str(self.held()["html"]) + str(
            self.held("delete __dashboard.unasked;\n" + STANDING_RAISE)["html"]
        )
        rendered = [s for s in self.BASE_CAVEAT_SENTENCES if s in html]
        self.assertEqual(
            sorted(set(self.BASE_CAVEAT_SENTENCES) - self.UNRENDERED_CAVEATS),
            sorted(rendered),
            "a caveat sentence stopped rendering, or one declared unreachable now renders",
        )
        # And no disclosure standing empty in place of one.
        self.assertNotIn("</summary></details>", html)

    def test_the_remainder_is_behind_a_summary_and_the_claim_is_not(self) -> None:
        """AC-1 and the tier rule together: the claim inline, the rest one click away."""
        counts = self.held()["counts"]
        assert isinstance(counts, str)
        self.assertIn(self.COUNTS_CLAIM, counts)
        self.assertIn("What a count does not say", counts)
        # The claim is before the summary; the remainder is after it.
        self.assertLess(counts.index(self.COUNTS_CLAIM), counts.index("<summary>"))
        self.assertGreater(counts.index(self.COUNTS_WHY), counts.index("</summary>"))
        self.assertIn("data-next-cockpit-disclosure", counts)

    def test_the_steer_claim_stays_inline_and_its_reason_discloses(self) -> None:
        """AC-1 on the DEPARTURES site."""
        block = self.held()["departures"]
        assert isinstance(block, str)
        self.assertIn(self.STEER_CLAIM, block)
        self.assertIn("Why no raise goes further", block)
        self.assertLess(block.index(self.STEER_CLAIM), block.index(self.STEER_WHY))
        self.assertGreater(block.index(self.STEER_WHY), block.index("</summary>"))

    def test_an_opened_disclosure_is_still_open_after_a_redraw(self) -> None:
        """AC-2, the offline half. A bare `<details>` snaps shut on every redraw.

        Falsified by a helper that emits no `data-next-cockpit-disclosure`,
        which makes the generic restore lane skip it. The node list is stubbed
        off the rendered markup the way the scope/attention case above does it,
        because this fixture's `app` is a plain object.
        """
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "__dashboard.annotate = true;\n__dashboard.annotate_cap = 240;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            "__dashboard.unasked = true;\n"
            """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
let markup = __els.app.innerHTML;
let disclosures = [];
__els.app.querySelectorAll = selector =>
  selector === "[data-next-cockpit-disclosure]" ? disclosures : [];
Object.defineProperty(__els.app, "innerHTML", {
  get: () => markup,
  set: value => {
    markup = value;
    disclosures = [...value.matchAll(
      /class="next-cockpit-why" data-next-cockpit-disclosure="([^"]+)"/g)]
      .map(match => ({key:match[1],open:false,
        getAttribute: () => match[1],querySelector: () => ({setAttribute(){}})}));
  }
});
__els.app.innerHTML = markup;
const keys = disclosures.map(row => row.key);
disclosures.forEach(row => {row.open = true;});
renderNext();
const kept = disclosures.map(row => row.open);
disclosures.forEach(row => {row.open = false;});
renderNext();
console.log(JSON.stringify({keys, kept, closed: disclosures.map(row => row.open)}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        keys = out["keys"]
        assert isinstance(keys, list)
        self.assertTrue(keys, "no tier-2 disclosure carried the restore attribute")
        self.assertEqual([True] * len(keys), out["kept"], "a disclosure snapped shut")
        # And the lane restores the closed state too, rather than latching open.
        self.assertEqual([False] * len(keys), out["closed"])

    def test_the_five_count_rows_and_their_absences_never_collapse(self) -> None:
        """AC-3. Only the explanatory paragraph may go behind a summary.

        "Only the paragraph goes behind the summary" has two halves and this
        checked one. The rows staying out was asserted; the paragraph being
        THERE was not, so the criterion's own empty-body falsifier -- a
        disclosure rendered with nothing behind it -- passed. Every row is
        still before the summary when the summary hides nothing at all, and a
        reader then gets a control that opens onto emptiness.
        """
        counts = self.held()["counts"]
        assert isinstance(counts, str)
        values = re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', counts)
        self.assertEqual(["not published", "not published", "3", "3", "2"], values)
        # None of the five rows sits inside the disclosure body.
        summary_at = counts.index("<summary>")
        for value in re.finditer(r'class="next-cockpit-count-value"', counts):
            self.assertLess(value.start(), summary_at)
        # And the summary hides something: the half the falsifier aimed at.
        shut = counts.index("</summary>") + len("</summary>")
        body = counts[shut : counts.index("</details>", shut)]
        self.assertNotEqual("", body.strip(), "the disclosure opens onto an empty body")
        self.assertIn("<p", body, "the disclosure hides no paragraph")
        prose = re.sub(r"<[^>]+>", "", body).strip()
        self.assertGreater(len(prose), 40, f"the disclosure hides no sentence, only {prose!r}")
        # The other half of the same guard, and the one nothing reached: a
        # caveat paragraph with nothing in it, anywhere on the tab. Removing
        # `nextCockpitWhy`'s empty-body return leaves 3652 behavioural tests
        # green and draws exactly one of these, in the re-entry block, on the
        # default board -- a reachable arm emitting an empty sentence.
        html = self.held()["html"]
        assert isinstance(html, str)
        self.assertNotIn(
            '<p class="next-cockpit-reading-why"></p>',
            html,
            "a caveat paragraph rendered with nothing in it",
        )
        self.assertNotIn(
            "</summary></details>", html, "a disclosure rendered with nothing behind it"
        )

    def test_the_card_independence_claim_is_stated_exactly_once(self) -> None:
        """AC-4. Falsified by leaving both statements, or by deleting both."""
        out = self.held()
        html, landed = out["html"], out["landed"]
        assert isinstance(html, str) and isinstance(landed, str)
        self.assertNotIn("two axes, read separately", html)
        self.assertEqual(1, landed.count(self.LANDED_CLAIM))
        # The claim did not merely move -- it is still adjacent to the cards.
        self.assertIn("next-cockpit-landed-cards", landed)

    def test_the_unasked_instruction_needs_no_click(self) -> None:
        """AC-6. Falsified by wrapping the unasked part's first paragraph."""
        out = self.held("delete __dashboard.unasked;\n" + STANDING_RAISE)
        html = out["html"]
        assert isinstance(html, str)
        part = re.search(
            r'<div class="next-cockpit-departure-part">'
            r'<span class="next-cockpit-departure-label">FROM THE CHECKS'
            r"[\s\S]*?</div>",
            html,
        )
        assert part is not None, "the unasked part did not render"
        body = part.group(0)
        self.assertIn("--unasked-readings", body)
        summary_at = body.find("<summary>")
        if summary_at != -1:
            self.assertLess(body.index("--unasked-readings"), summary_at)

    def test_no_rendered_string_carries_a_docs_link_or_a_decision_token(self) -> None:
        """AC-7. Tier 3 cites a source comment, never rendered HTML.

        A `docs/` href is a dead link in an installed plugin, where no `docs/`
        sits beside the page, and a bare `DEC-N` in a product string is a
        `RuntimeDecisionCitationsTest` hit.

        **Derived over the bundle, not rendered on a list of tabs.** The first
        repair for this added the Console surface to a fixture, and a second
        fixture still cannot fail on the surface nobody thought to add -- the
        argument `js_literals` makes about itself, and the same reason AC-4's
        retired-span check walks every runtime file instead of naming two. The
        criterion's own falsifier did not fire on the `pc-`/Console surface,
        which this issue itself introduced, and naming that surface would have
        left the next one uncovered.

        The file count is asserted because a walk that reaches nothing passes
        an empty loop in silence.

        One blind spot, stated rather than left implicit: `emitted_strings`
        splits a template literal at each `${...}`, so an href composed through
        a hole is out of this sweep's reach. Nothing in the bundle builds one
        today; a future one needs a different instrument, not a longer list.
        """
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        scripts = sorted(web.glob("*.js"))
        self.assertGreater(len(scripts), 15, "the bundle walk found almost no scripts")
        decision = re.compile(r"\bDEC-\d+\b")
        offenders = [
            f"{script.name}: {text[:70]}"
            for script in scripts
            for text in emitted_strings(script.read_text(encoding="utf-8"))
            if "docs/" in text or decision.search(text)
        ]
        self.assertEqual([], offenders)

    # A stored reading, so the branch that renders the reading section's own
    # baseline, scope and caveat actually executes. Without it the section
    # returns early and a tier-2 body planted in that branch is never drawn,
    # which is how the assertion below first passed over its own mutation.
    READING = (
        '__dashboard.sessions[0].annotation_goal = "do not change the board";\n'
        '__dashboard.sessions[0].annotation_goal_why = "";\n'
        '__dashboard.sessions[0].annotation_output = "";\n'
        '__dashboard.sessions[0].annotation_output_why = "No expected output typed.";\n'
        "__dashboard.sessions[0].annotation_revision = 1;\n"
        "__dashboard.sessions[0].annotation_revision_count = 1;\n"
        "__dashboard.sessions[0].annotation_at = 100;\n"
        '__dashboard.sessions[0].annotation_binding_why = "";\n'
        "__dashboard.sessions[0].annotation_assessment = {revision_read:1,\n"
        '  scope:"mid-flight",\n'
        '  scope_text:"This covers only the work so far.",\n'
        '  criteria:{goal:{result:"departure", detail:"It drifted.", cites:["fo-a"]}}};\n'
    )

    def test_the_reading_sections_own_first_caveat_is_untouched(self) -> None:
        """AC-8. A new `reading-why` emitted earlier hijacks three assertions
        that read the first one in a slice running to end of document.

        Asserted on a board that has a reading, so the section renders its
        baseline, scope and caveat rather than returning on its absence branch.
        """
        out = self.held(self.READING)
        html, reading = out["html"], out["reading"]
        assert isinstance(html, str) and isinstance(reading, str)
        self.assertIn("This covers only the work so far", reading)
        # No tier-2 control anywhere inside the reading section -- the four
        # sites this change touches all sit after it.
        self.assertNotIn("next-cockpit-why", reading)
        # And the first `reading-why` in a slice to end of document is still
        # the reading section's own, not one tiered from below it.
        block = html[html.index('class="next-cockpit-reading"') :]
        first = re.search(r'class="next-cockpit-reading-why">([^<]*)<', block)
        assert first is not None
        self.assertLess(
            block.index(first.group(0)),
            block.index("next-cockpit-departures"),
            "a caveat from the departures section became the reading's first one",
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class HeldToOrderingTest(NextPageJsHarness):
    """DRC-4594. Purpose and inputs before the caveats.

    The tab opened on its two textareas, followed them with a paragraph whose
    middle forty-two words explained why this session cannot be raised, and
    then ran four sections that each reported that nothing is here. The lede
    says what typing buys, and the record moves to last.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    ANNOTATED = (
        '__dashboard.sessions[0].annotation_goal = "Ship the cockpit";\n'
        '__dashboard.sessions[0].annotation_output = "A green suite";\n'
        "__dashboard.sessions[0].annotation_revision = 1;\n"
        "__dashboard.sessions[0].annotation_revision_count = 1;\n"
        "__dashboard.sessions[0].annotation_at = 100;\n"
        '__dashboard.sessions[0].annotation_binding_why = "";\n'
    )

    def tab(self, setup: str = "") -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "__dashboard.annotate = true;\n__dashboard.annotate_cap = 240;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            # The lane on, so the departures section renders; a setup may delete it.
            "__dashboard.unasked = true;\n"
            + self.ANNOTATED
            + setup
            + """
navigateNext({view:"session", project:"cargento", harness:"codex", session:"focus-1"});
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  html,
  lede: (html.match(/class="next-cockpit-held-lede">([\\s\\S]*?)<\\/p>/) || [])[1] || "",
  counts: (html.match(
    /<div class="next-cockpit-departure-part"><span class="next-cockpit-departure-label">COUNTS[\\s\\S]*?<\\/details><\\/div>|<div class="next-cockpit-departure-part"><span class="next-cockpit-departure-label">COUNTS[\\s\\S]*?<\\/div><\\/div>/) || [""])[0],
}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_the_lede_is_the_first_thing_on_the_tab(self) -> None:
        """AC-1. Falsified by emitting it after the fields grid, or omitting it."""
        out = self.tab()
        html = out["html"]
        assert isinstance(html, str)
        # The tab, not the page. The chrome and the scope rail state absences of
        # their own above every panel, and this criterion is about what the tab
        # opens on. Sliced from the panel to the end of the document rather than
        # to a matching `</section>`, which nested sections make unfindable by
        # scan; anything after the panel is also after the lede, so the slice
        # can only ever add elements the assertion still holds for.
        panel = html[html.index("data-next-session-drift") :]
        at = panel.index('class="next-cockpit-held-lede"')
        self.assertLess(at, panel.index('class="next-cockpit-held-fields"'))
        # Every absence element the board rendered, found by the same convention
        # `test_next_page._absence_rules` sweeps the stylesheet with: an
        # `-absent` class-name segment, or one of the three absence attributes.
        #
        # The four-string list this replaces failed twice over one gap, and the
        # second failure is why adding a fifth string could not have fixed it:
        # the strings were passed through `if absence in html`, so an absence
        # this tab renders and nobody listed was both off the list AND filtered
        # out of the comparison -- the loop then ran over the three that did
        # render and reported success. A list that silently drops its own
        # misses is not a shorter version of this sweep; it is a different
        # assertion.
        absences = [
            match.start()
            for match in re.finditer(
                r'<\w+[^>]*?(?:class="[^"]*-absent[^"]*"'
                r"|data-absence=|data-next-absent|data-next-withheld)[^>]*>",
                panel,
            )
        ]
        self.assertGreater(len(absences), 3, "no absence element rendered to be measured against")
        for start in absences:
            with self.subTest(absence=panel[start : start + 60]):
                self.assertLess(at, start)

    def test_the_lede_claims_no_automatic_reading(self) -> None:
        """AC-2, on the default board -- the one the `--unasked-readings`
        instruction four sections down exists for."""
        out = self.tab("delete __dashboard.unasked;\n")
        lede = out["lede"]
        assert isinstance(lede, str)
        self.assertTrue(lede.strip(), "no lede rendered")
        for claim in ("watch", "automatic", "checks for you"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, lede.lower())
        self.assertIn("check for drift", lede)

    def test_the_section_order_puts_the_record_last(self) -> None:
        """AC-3. Falsified by moving any section, including re-raising OBSERVED
        RECORD, which no test on the pre-change tree can see."""
        out = self.tab()
        html = out["html"]
        assert isinstance(html, str)
        # The check sits directly under the words and the direction, so it is on the first
        # screen; the reading, then the later-direction question it constrains, follow it
        # (DRC-4639).
        order = [
            "WHAT YOU ASKED FOR",
            'data-next-cockpit-action="reading-ask"',
            "<h2>READING</h2>",
            "CONFLICT TO SETTLE",
            "DEPARTURES RAISED TO YOU",
            "HOW IT LANDED",
            "OBSERVED RECORD",
        ]
        found = [html.find(heading) for heading in order]
        for heading, at in zip(order, found, strict=True):
            with self.subTest(section=heading):
                self.assertNotEqual(-1, at, f"{heading} did not render")
        for before, after in itertools.pairwise(order):
            with self.subTest(pair=(before, after)):
                self.assertLess(html.find(before), html.find(after))
        # The Intent-log pointer is the tab's last line, after the record.
        self.assertLess(html.find("OBSERVED RECORD"), html.find("next-cockpit-departures-kept"))

    def test_the_record_read_phrase_did_not_merely_move(self) -> None:
        """AC-4's original string check, kept as the regression it is.

        The sweep that replaces it is `HeldToPositionalSentencesTest`. This one
        stays because it is cheap and because the phrase it names is the one
        DRC-4594 actually reworded; what it cannot do is notice the next one,
        which is the whole reason the sweep exists.
        """
        out = self.tab("__dashboard.sessions[0].annotation_at = 200;\n")
        html = out["html"]
        assert isinstance(html, str)
        self.assertNotIn("record read above", html)
        self.assertIn("is in the observed record read for this session", html)

    def test_the_count_labels_drop_the_repeated_quantity_noun(self) -> None:
        """AC-7. Falsified by rewording any `line()` value argument or collapsing
        the null-to-"not published" branch while relabelling."""
        # The lane on and this session never checked, so both departure figures are unpublished
        # and the section still draws (with the lane off and nothing on record it does not).
        out = self.tab("__dashboard.sessions[0].departures = [];\n")
        counts = out["counts"]
        assert isinstance(counts, str)
        labels = re.findall(r'class="next-cockpit-count-label">([^<]*)<', counts)
        self.assertEqual(
            [
                "From the reading you asked for",
                "From the checks run while you were away",
                "On record for this board",
                "This board attempted",
                "A notification service accepted",
            ],
            labels,
        )
        groups = re.findall(r'class="next-cockpit-count-group">([^<]*)<', counts)
        self.assertEqual(["DEPARTURES", "RAISES"], groups)
        values = re.findall(r'class="next-cockpit-count-value"[^>]*>([^<]*)<', counts)
        self.assertEqual(["not published", "not published", "3", "3", "2"], values)

    def test_the_your_words_sub_label_and_everything_citing_it_are_gone(self) -> None:
        """AC-8. Falsified by deleting the span and leaving the rule, or leaving
        the handler comment that explains itself by that label."""
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        cockpit = (web / "next-cockpit.js").read_text(encoding="utf-8")
        styles = (web / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn("next-cockpit-held-sub", cockpit)
        self.assertNotIn("next-cockpit-held-sub", styles)
        # The two surviving occurrences are sentences, not labels.
        self.assertEqual(2, cockpit.count("your words"))
        self.assertIn("your words are still in the box", cockpit)
        self.assertIn("your words are kept", cockpit)


@unittest.skipUnless(shutil.which("node"), "node not available")
class HeldToPositionalSentencesTest(NextPageJsHarness):
    """DRC-4594 AC-4, as a sweep over the class rather than over one phrase.

    The criterion was written "no sentence says the record is above it" and
    verified by asserting one phrase was gone. DRC-4594's own comment records
    that it reworded "the one sentence that was positionally anchored" -- so it
    swept by known string, and it missed two: `NEXT_READING_OFFER`, which was
    false on every render, and `NEXT_READING_UNAUTHORIZED`, which is false
    whenever it renders and renders rarely. This sweep then found a third, the
    two settle cues, which no one had looked at at all. Three misses from a
    by-hand pass is the argument for deriving the subject.

    **Two things were deliberately not done here**, because each would leave a
    sweep that passes while measuring nothing:

    * The obvious repair for a false "above" is to delete the word. After that
      the sweep returns an empty set and is green forever. So every sentence
      keeps a positional word and the word is required to be TRUE, and the
      assertions below require the sweep to be non-empty, to be a bijection
      with the referents declared here, and for every member to have been
      index-checked in at least one arm.
    * "Every hit lands after the record" is right for *above* and wrong for
      *below* -- and the record genuinely IS below now, so the correct fix
      ("the observed record below") would FAIL that assertion. The direction is
      read from each sentence and the comparison flips with it.

    The referents are the one enumerated part, and they have to be: a marker's
    identity is not in the sentence. What is derived is the SUBJECT, so a new
    positional sentence reds this test until someone says what it points at.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE
    ANNOTATED = HeldToOrderingTest.ANNOTATED

    POSITIONAL = re.compile(r"\b(above|below)\b")

    # A distinctive fragment of each swept sentence -> the rendered marker whose
    # side it claims. Asserted below to be a bijection with the sweep.
    REFERENTS: ClassVar[dict[str, str]] = {
        "so the question below still stands as it did": "next-cockpit-conflict-open",
        "already been dropped and the question below still stands": "next-cockpit-conflict-open",
        "so nothing above is an inspected file": "OBSERVED RECORD",
        "Save a goal above to check for drift": 'class="next-cockpit-held-fields"',
        "the observed record below and the goal and output you saved": "OBSERVED RECORD",
        "after you saved the words above": 'class="next-cockpit-held-fields"',
    }

    # Each arm exists to render sentences the default board does not. `model`
    # supplies an observer model so the reading control stops refusing for a
    # different reason and reaches the abstention sentence; `settle-*` marks the
    # cue lane directly, which is the only way to reach a store outcome without
    # driving a POST.
    ARMS: ClassVar[dict[str, str]] = {
        "default": "",
        "late-words": "__dashboard.sessions[0].annotation_at = 200;\n",
        "no-words": (
            '__dashboard.sessions[0].annotation_goal = "";\n'
            '__dashboard.sessions[0].annotation_output = "";\n'
        ),
        "settle-refused": "",
        "settle-unpersisted": "",
        "model": "",
    }

    def arm(self, name: str) -> str:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "__dashboard.annotate = true;\n__dashboard.annotate_cap = 240;\n"
            "__dashboard.delivery_counts = {raises: 3, attempted: 3, handed_over: 2};\n"
            + self.ANNOTATED
            + self.ARMS[name]
            + f"const ARM = {json.dumps(name)};\n"
            + """
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
const group = nextProjectGroups().find(candidate => candidate.label === "cargento");
const session = nextCockpitFocusedSession(group);
if(ARM.startsWith("settle-")){
  nextCockpitHeldMark(nextCockpitHeldKey(session, "settle"), ARM);
  renderNext();
}
if(ARM === "model"){
  for(const key of [nextCockpitContextKey(group, null), nextCockpitContextKey(group, session)]){
    const entry = nextCockpitContexts.get(key);
    if(entry && entry.data) entry.data = Object.assign({}, entry.data,
      {observer_model:{enabled:true, disclosure:"x", model:"sonnet"}});
  }
  renderNext();
}
console.log(JSON.stringify({html: __els.app.innerHTML}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        html = out["html"]
        assert isinstance(html, str)
        return html

    def sweep(self) -> list[str]:
        source = (frontend_page.WEB_DIR / "next-cockpit.js").read_text(encoding="utf-8")
        return [
            text
            for text in emitted_strings(source)
            if self.POSITIONAL.search(text) and text.strip()
        ]

    def test_the_sweep_and_the_referents_are_a_bijection(self) -> None:
        """Non-vacuity. A sweep that can return nothing is not a measurement.

        Two directions, because neither implies the other: a new positional
        sentence with no referent is unchecked, and a referent whose sentence
        has been deleted or reworded is a row measuring nothing.
        """
        found = self.sweep()
        self.assertNotEqual([], found, "the sweep found no positional sentence at all")
        matched: dict[str, list[str]] = {fragment: [] for fragment in self.REFERENTS}
        unclaimed: list[str] = []
        for text in found:
            hits = [fragment for fragment in self.REFERENTS if fragment in text]
            if not hits:
                unclaimed.append(text)
                continue
            self.assertEqual(1, len(hits), f"{text[:60]!r} matches {len(hits)} referents")
            matched[hits[0]].append(text)
        self.assertEqual(
            [],
            unclaimed,
            "a positional sentence has no declared referent; say what it points at",
        )
        for fragment, texts in matched.items():
            with self.subTest(fragment=fragment[:40]):
                self.assertEqual(1, len(texts), f"{fragment!r} matched {len(texts)} sentences")

    def test_every_positional_sentence_renders_on_the_side_it_claims(self) -> None:
        """AC-4, directionally. Falsified three ways, each one shipped here
        before this test existed: a sentence saying `above` about something
        below it, a sentence saying `below` about something above it, and a
        sentence that was made true by deleting the word.
        """
        arms = {name: self.arm(name) for name in self.ARMS}
        checked: dict[str, list[str]] = {}
        for text in self.sweep():
            fragment = next(f for f in self.REFERENTS if f in text)
            marker = self.REFERENTS[fragment]
            words = set(self.POSITIONAL.findall(text))
            self.assertEqual(
                1, len(words), f"{fragment!r} states two directions at once: {sorted(words)}"
            )
            claims_above = words == {"above"}
            for name, html in arms.items():
                at = html.find(text.strip())
                anchor = html.find(marker)
                if at == -1 or anchor == -1:
                    continue
                checked.setdefault(fragment, []).append(name)
                with self.subTest(fragment=fragment[:40], arm=name):
                    if claims_above:
                        self.assertGreater(
                            at, anchor, f"{fragment!r} says `above` about something below it"
                        )
                    else:
                        self.assertLess(
                            at, anchor, f"{fragment!r} says `below` about something above it"
                        )
        # Every sentence was measured somewhere. A referent no arm renders is a
        # row this test carries and never reads, which is the vacuity the list
        # form of this criterion had.
        self.assertEqual(
            sorted(self.REFERENTS),
            sorted(checked),
            "a positional sentence rendered in no arm, so nothing was compared for it",
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class ConsoleSetupNeverCallsAnUnreadCapabilityOffTest(NextPageJsHarness):
    """The Console setup summary, in the three states it can honestly be in.

    Reported by review: the two booleans collapsed an unread capability into
    `false`, so a server started with BOTH capabilities on opened its Console
    saying "terminal bridge off, observer model off" and corrected itself a tick
    later. That is AGENTS.md's first Measured Invariant -- a structurally
    present default standing in for a measurement -- in a function whose own
    comment cites it.

    The fixture serves an enabled observer model and a registered terminal, so
    every `false` this test sees is wrong about the fixture rather than merely
    unproven.

    The refresh arm is the one that matters most and it is a defect the FIX
    introduced, caught by re-reading the diff rather than by a suite.
    `projectTerminalLookup` marks a registered terminal
    `{state:"registered", loading:true}` while it re-checks, and it re-checks
    whenever the payload revision advances -- so a first draft that read the
    `loading` flag reported `null` on EVERY poll of a working console, flipped
    the summary to "not read yet" and moved the live terminal into the setup
    disclosure. Reading `state` is what makes the third value mean "no answer
    yet" rather than "an answer is being refreshed".
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    CAPABLE_SERVER = """
__fetchImpl = async url => ({ok: true, json: async () =>
  String(url).startsWith("/api/project-context")
    ? {semantic: __semantic, child_assignments: [], observers: [],
       observer_model: {enabled: true, disclosure: "x"}}
    : String(url).startsWith("/api/interaction/origin")
      ? {state: "registered", tty: "/dev/ttys004"}
      : __dashboard});
for(let i = 0; i < 10; i++) await __settle();
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"console"});
for(let i = 0; i < 12; i++) await __settle();
const group = nextProjectGroups().find(candidate => candidate.label === "cargento");
const focus = group.sessions.find(session => session.sid === "focus-1");
const summaryOf = html =>
  (html.match(/<summary>(How this server was started[^<]*)<\\/summary>/) || [])[1] || null;
const inDisclosure = html => (html.match(
  /<details class="next-cockpit-console-setup"[\\s\\S]*?<\\/details>/) || [""])[0]
  .includes("next-cockpit-terminal");
"""

    # The same board with the bridge OFF, which is the default a plain
    # `cargento` start gives. `/api/interaction/origin` answers, and its answer
    # is "no terminal for this session" -- a measurement, not a missing read.
    BRIDGE_OFF_SERVER = """
__fetchImpl = async url => ({ok: true, json: async () =>
  String(url).startsWith("/api/project-context")
    ? {semantic: __semantic, child_assignments: [], observers: [],
       observer_model: {enabled: true, disclosure: "x"}}
    : String(url).startsWith("/api/interaction/origin")
      ? {state: "unavailable", reason: "no terminal bridge on this server"}
      : __dashboard});
for(let i = 0; i < 10; i++) await __settle();
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"console"});
for(let i = 0; i < 12; i++) await __settle();
const group = nextProjectGroups().find(candidate => candidate.label === "cargento");
const focus = group.sessions.find(session => session.sid === "focus-1");
const summaryOf = html =>
  (html.match(/<summary>(How this server was started[^<]*)<\\/summary>/) || [])[1] || null;
"""

    def state(self, checks: str) -> dict[str, Any]:
        out = self._run_page_js(
            self.CAPABLE_SERVER + checks,
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def bridge_off(self, checks: str) -> dict[str, Any]:
        out = self._run_page_js(
            self.BRIDGE_OFF_SERVER + checks,
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_an_unavailable_bridge_stays_off_across_every_poll(self) -> None:
        """The reset that the `registered` half of this fix hid.

        `projectTerminalLookup` preserved `registered` across a re-check and
        reset `unavailable` to `loading`, so a default bridge-off console said
        "terminal bridge off" and then "not read yet" on the very next poll,
        for as long as the board stayed open. The revision advances every
        payload and that is exactly what releases the lookup's guard.

        **Driven the way production drives it** -- advance `nextData.generated`
        and let `renderNext` run the lookup -- rather than by writing the map,
        because writing the map is what let the sibling test pass over this.
        The assertion is not the interesting part; the path is.
        """
        out = self.bridge_off("""
const polls = [];
for(const revision of [106, 107, 108]){
  nextData.generated = revision;
  /* Sampled on the render that STARTS the re-check, before its fetch settles.
     That is the frame a reader sees, and it is the only frame the defect is
     visible in: four microtasks later the reply has landed and the entry reads
     `unavailable` again whatever the guard did to it in between. A sample
     taken after the await passes on the broken code. */
  renderNext();
  const entry = projectTerminalBySession[sessKey(focus)];
  polls.push({revision, state: entry && entry.state, loading: entry && entry.loading === true,
    terminal: nextCockpitConsoleCapabilities(group, focus).terminal,
    summary: summaryOf(__els.app.innerHTML)});
  for(let i = 0; i < 4; i++) await __settle();
}
console.log(JSON.stringify({polls}));
""")
        polls = out["polls"]
        assert isinstance(polls, list)
        self.assertEqual(3, len(polls))
        for poll in polls:
            with self.subTest(revision=poll["revision"]):
                # The re-check really is in flight on the sampled frame, or the
                # guard was never released and nothing was measured.
                self.assertTrue(poll["loading"], "no re-check was in flight on this poll")
                self.assertEqual("unavailable", poll["state"])
                self.assertIs(False, poll["terminal"])
                self.assertIn("terminal bridge off", poll["summary"])
                self.assertNotIn("not read yet", poll["summary"])

    def test_with_no_session_selected_the_bridge_is_named_per_session(self) -> None:
        """The fourth state, and it exists because the third one created a gap.

        At project scope `focus` is null, so no lookup is ever attempted: the
        board said "terminal bridge not read yet" for as long as it stayed
        open. A pending state that can never resolve is the same defect as the
        confident "off" it replaced, one step over -- both describe the board
        rather than the server. The bridge is a per-session registration and
        that is what the summary now says, next to the prompt already telling
        the reader to select a session.
        """
        out = self.bridge_off("""
const capabilities = nextCockpitConsoleCapabilities(group, null);
navigateNext({view:"project", project:"cargento", focus:null, tab:"console"});
for(let i = 0; i < 6; i++) await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({capabilities, summary: summaryOf(html),
  prompt: html.includes("Select one exact session to open its read-only console")}));
""")
        self.assertEqual("per-session", out["capabilities"]["terminal"])
        self.assertIn("terminal bridge per-session", out["summary"])
        # Neither of the two wrong answers this state exists to avoid.
        self.assertNotIn("terminal bridge off", out["summary"])
        self.assertNotIn("terminal bridge not read yet", out["summary"])
        # And the sentence is only complete beside the prompt, so the prompt
        # rendering is part of what is asserted.
        self.assertTrue(out["prompt"], "the select-a-session prompt did not render")

    def test_a_bridge_nothing_has_looked_up_yet_still_reports_not_read(self) -> None:
        """The reverse, and the reason this repair is not just "preserve
        everything". A repair that pinned `unavailable` by making the third
        state unreachable would trade this defect for the one the three-state
        read exists to prevent, and nothing else in this class would notice.
        """
        out = self.bridge_off("""
// A session whose lookup has never run: no entry in the map at all.
delete projectTerminalBySession[sessKey(focus)];
const capabilities = nextCockpitConsoleCapabilities(group, focus);
console.log(JSON.stringify({capabilities,
  summary: summaryOf(nextCockpitConsoleSetup(capabilities, ""))}));
""")
        self.assertIsNone(out["capabilities"]["terminal"])
        self.assertIn("terminal bridge not read yet", out["summary"])

    def test_an_unread_capability_is_not_reported_as_disabled(self) -> None:
        """Falsified by `Boolean(...)` over either field: both arms then read
        `false`, and the summary says `off` about a server that has them on."""
        out = self.state("""
const settled = nextCockpitConsoleCapabilities(group, focus);
const settledHtml = __els.app.innerHTML;
// Rewind to the state the first render of this tab is in.
nextCockpitContexts.delete(nextCockpitContextKey(group, focus));
nextCockpitRequests.delete(nextCockpitContextKey(group, focus));
delete projectTerminalBySession[sessKey(focus)];
const unread = nextCockpitConsoleCapabilities(group, focus);
renderNext();
const firstHtml = __els.app.innerHTML;
console.log(JSON.stringify({unread, settled,
  firstSummary: summaryOf(firstHtml), settledSummary: summaryOf(settledHtml),
  firstInDisclosure: inDisclosure(firstHtml),
  settledInDisclosure: inDisclosure(settledHtml)}));
""")
        self.assertEqual({"terminal": None, "observer": None}, out["unread"])
        self.assertEqual({"terminal": True, "observer": True}, out["settled"])
        self.assertEqual(
            "How this server was started — terminal bridge not read yet, "
            "observer model not read yet",
            out["firstSummary"],
        )
        self.assertEqual(
            "How this server was started — terminal bridge on, observer model on",
            out["settledSummary"],
        )
        # Placement is unchanged by the third state: nothing unread is operable.
        self.assertTrue(out["firstInDisclosure"])
        self.assertFalse(out["settledInDisclosure"])

    def test_a_refreshing_terminal_keeps_the_answer_it_already_has(self) -> None:
        """Falsified by reading `terminal.loading` instead of `terminal.state`.

        One revision bump is all it takes, and the payload's revision advances
        on every poll.
        """
        out = self.state("""
const settled = nextCockpitConsoleCapabilities(group, focus);
nextData.generated = 106;
renderNext();
const refreshing = nextCockpitConsoleCapabilities(group, focus);
const entry = projectTerminalBySession[sessKey(focus)];
const html = __els.app.innerHTML;
console.log(JSON.stringify({settled, refreshing, loading: entry.loading === true,
  state: entry.state, summary: summaryOf(html), inDisclosure: inDisclosure(html)}));
""")
        # The refresh really is in flight, or this test proves nothing.
        self.assertTrue(out["loading"], "the lookup did not re-arm, so no refresh was measured")
        self.assertEqual("registered", out["state"])
        self.assertEqual(out["settled"], out["refreshing"])
        self.assertEqual({"terminal": True, "observer": True}, out["refreshing"])
        self.assertEqual(
            "How this server was started — terminal bridge on, observer model on",
            out["summary"],
        )
        self.assertFalse(out["inDisclosure"], "a live terminal moved into the setup disclosure")

    def test_an_unavailable_terminal_is_reported_off_and_not_unknown(self) -> None:
        """The third value must not swallow a real negative: a session with no
        registered terminal is a measurement, and `off` is what it deserves."""
        out = self.state("""
projectTerminalBySession[sessKey(focus)] = {state:"unavailable", revision:105,
  data:{reason:"lookup-failed"}};
const capabilities = nextCockpitConsoleCapabilities(group, focus);
console.log(JSON.stringify({capabilities,
  summary: summaryOf(nextCockpitConsoleSetup(capabilities, ""))}));
""")
        self.assertEqual({"terminal": False, "observer": True}, out["capabilities"])
        self.assertIn("terminal bridge off", out["summary"])


class EveryTabCueVariantIsColouredByItsOwnRuleTest(unittest.TestCase):
    """A cue variant with no rule renders in the ink a real figure gets.

    `.next-cockpit-tab-cue` is `--ink2`, the value ink. Each non-count state
    adds a variant class that takes it down to the absence ink, so a variant
    the producer emits and the sheet does not style resolves to `--ink2` and a
    stated absence renders exactly as loudly as the count it replaces -- the
    inversion this milestone exists to remove.

    This was written because the obvious assertion does not catch it. Pinning
    the emitted class name passes whether or not a rule exists: measured, the
    `--unavailable` rule was deleted and the whole cockpit module stayed green.
    The byte-pin oracles went red, but they go red on any stylesheet edit and
    so are evidence of nothing here.

    The variants are DERIVED from the producer, so a state added with no rule
    reds this instead of arriving beside it. Resolved through the cascade and
    compared against the unmodified cue, per this sheet's standing rule that a
    colour is read by resolving an element and never by counting rules.
    """

    tokens: dict[str, float]
    rules: list[tuple[str, str, int]]

    @classmethod
    def setUpClass(cls) -> None:
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        cls.tokens, cls.rules = css_cascade.load(web / "styles.css")
        cls.cockpit_js = (web / "next-cockpit.js").read_text(encoding="utf-8")

    cockpit_js: str

    def ink(self, *classes: str) -> str:
        path = [_node("span", "next-cockpit-tab-cue", *classes)]
        winning = []
        for selector, body, order in self.rules:
            try:
                specificity = css_cascade.matches(path, selector)
            except css_cascade.UnsupportedSelectorError:
                continue
            if specificity is None:
                continue
            declared = re.search(r"(?:^|;)\s*color:\s*([^;]+)", body)
            if declared:
                winning.append((specificity, order, declared.group(1).strip()))
        self.assertNotEqual([], winning, f"no rule colours {classes or ('the bare cue',)}")
        winning.sort()
        return winning[-1][2]

    def variants(self) -> set[str]:
        """Every variant class `nextCockpitTabCueHtml` can put on a cue."""
        return set(re.findall(r'" (next-cockpit-tab-cue--[a-z-]+)"', self.cockpit_js))

    def test_every_variant_the_producer_emits_is_styled(self) -> None:
        found = self.variants()
        # A derivation that found nothing would pass the loop below in silence.
        self.assertEqual(
            {"pending", "unobserved", "unavailable"}, {name.rsplit("--", 1)[1] for name in found}
        )
        value = self.ink()
        for variant in sorted(found):
            with self.subTest(variant=variant):
                self.assertNotEqual(
                    value,
                    self.ink(variant),
                    f"{variant} resolves to the cue's own ink, so an absence renders "
                    "in the ink a real figure gets",
                )


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheCueAndItsPanelAgreeInEveryContextStateTest(NextPageJsHarness):
    """`nextCockpitContexts` has five reachable shapes, and both surfaces that
    read it must describe each the same way.

    Three writers store into that map and only one writes `error`, so the field
    sets differ by writer. The tab cue this branch adds keyed off `.data`
    alone: a read that had FINISHED AND FAILED with nothing to show rendered as
    "decisions not loaded yet" beside a panel already saying "Semantic context
    unavailable." -- a completed request described as still in flight.

    The fifth shape is the one both independent enumerations missed and the
    comparison between them found. The `.catch()` MERGES rather than replaces:
    it carries the previous `data` into the new object and stamps `error` over
    it, so a failed poll over a loaded context is indistinguishable from a
    clean resolve by `.data` alone.

    **Stale-plus-error renders exactly as resolved does, deliberately.**
    Keeping the last known rows is a defensible product choice; saying so on
    screen is new copy nobody specified, and it is filed as DRC-4613 rather
    than invented here. What is asserted is that the two surfaces AGREE in
    every state -- agreeing wrongly was the old defect and disagreeing would be
    a new one, so a partial fix fails this as loudly as no fix.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    def states(self) -> dict[str, Any]:
        out = self._run_page_js(
            """
await __settle(); await __settle();
const group = nextProjectGroups().find(candidate => candidate.label === "cargento");
const key = nextCockpitContextKey(group, null);
const resolved = nextCockpitContexts.get(key).data;
const panelSays = () => {
  const html = nextCockpitTimeline(group, null);
  return html.includes("Semantic context unavailable.") ? "unavailable"
    : (html.includes("Loading semantic context") ? "loading" : "rows");
};
const read = () => {
  const cue = nextCockpitTabCue("decisions", {group}, null);
  return {cue: cue.state, panel: panelSays(),
    classified: nextCockpitContextRead(group, null).state};
};
const seen = {};
// 1. Nothing has been read at all.
nextCockpitContexts.delete(key);
nextCockpitRequests.delete(key);
seen.absent = read();
// 2. An entry with neither data nor a failure.
nextCockpitContexts.set(key, {data:null, revision:105});
seen.pending = read();
// 3. The read FINISHED and failed with nothing to show. This is the exact
//    record the `.catch()` writes when no prior data existed.
nextCockpitContexts.set(key, {data:null, revision:105, error:true});
seen.unavailable = read();
// 4. A clean resolve.
nextCockpitContexts.set(key, {data:resolved, revision:105});
seen.resolved = read();
// 5. The merge: the catch carried the previous data forward and stamped
//    `error` over it. Byte-identical to (4) on both surfaces by design.
nextCockpitContexts.set(key, {data:resolved, revision:105, error:true});
seen.stale = read();
console.log(JSON.stringify(seen));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_no_finished_read_is_ever_called_pending(self) -> None:
        """Falsified by the cue keying off `.data` alone, which is what it did.

        The `unavailable` row is the defect: `pending` there claims a read is
        still coming when it has already failed.
        """
        seen = self.states()
        self.assertEqual(
            {"cue": "unavailable", "panel": "unavailable", "classified": "unavailable"},
            seen["unavailable"],
        )

    def test_the_two_surfaces_describe_every_state_the_same_way(self) -> None:
        """The property a partial fix breaks. Teaching only the cue to read
        `error` would make it claim failure over a panel rendering rows.
        """
        agreeing = {
            "absent": ("pending", "loading", "absent"),
            "pending": ("pending", "loading", "pending"),
            "unavailable": ("unavailable", "unavailable", "unavailable"),
            "resolved": ("count", "rows", "ready"),
            "stale": ("count", "rows", "stale"),
        }
        seen = self.states()
        # Five distinct classifications, so the separation is real rather than
        # four states wearing five names.
        self.assertEqual(5, len({row["classified"] for row in seen.values()}))
        for name, (cue, panel, classified) in agreeing.items():
            with self.subTest(state=name):
                self.assertEqual({"cue": cue, "panel": panel, "classified": classified}, seen[name])

    def test_a_failure_over_loaded_data_still_shows_the_rows_it_had(self) -> None:
        """The ruling, pinned so a later change cannot quietly adopt the other
        one. Stale-plus-error keeps the last known rows and claims nothing about
        staleness; whether the board should SAY the rows are stale is DRC-4613.
        """
        seen = self.states()
        self.assertEqual(seen["resolved"]["cue"], seen["stale"]["cue"])
        self.assertEqual(seen["resolved"]["panel"], seen["stale"]["panel"])
        self.assertEqual("rows", seen["stale"]["panel"])
        # And it is still separable, which is what DRC-4613 will need.
        self.assertNotEqual(seen["resolved"]["classified"], seen["stale"]["classified"])


class ATierTwoControlIsNeverSmallerThanWhatItHidesTest(unittest.TestCase):
    """DRC-4591. The summary of a tier-2 disclosure, read beside the body it hides.

    Not a value/absence pair, which is why it is not in
    `AnAbsenceNeverOutranksTheValueItReplacesTest` above: that test is scoped to
    DRC-4587's claim and says so. But it is the same trap one layer out. A
    summary and the body behind it never render together either, because the
    body is collapsed until the summary is clicked, and the summary carries the
    only words a reader has for deciding whether to open it. A control set below
    the text it conceals loses the caveat as surely as deleting it, which is the
    whole thing the three-tier rule exists to prevent.

    Resolved through `css_cascade` rather than by reading the two rules, for the
    reason that module's own docstring gives: the number only exists once the
    cascade is composed down a path the application really builds.
    """

    tokens: dict[str, float]
    rules: list[tuple[str, str, int]]
    cockpit_js: str

    @classmethod
    def setUpClass(cls) -> None:
        web = pathlib.Path(__file__).resolve().parents[1] / "cargento_runtime" / "web"
        cls.tokens, cls.rules = css_cascade.load(web / "styles.css")
        cls.cockpit_js = (web / "next-cockpit.js").read_text(encoding="utf-8")

    def size(self, path: list[dict[str, object]]) -> float:
        resolved = css_cascade.resolve(path, self.tokens, self.rules)
        self.assertIsNotNone(resolved, f"no size resolves for {path}")
        assert resolved is not None
        return resolved

    def test_the_summary_is_not_smaller_than_the_body_it_conceals(self) -> None:
        """Falsified by dropping the summary to the label tier, which reads as
        the tidier choice and makes the control quieter than what it hides."""
        disclosure = [
            *_CONTENT,
            _node("section", "next-cockpit-departures"),
            _node("details", "next-cockpit-why"),
        ]
        summary = self.size([*disclosure, _node("summary")])
        body = self.size([*disclosure, _node("p", "next-cockpit-reading-why")])
        self.assertGreaterEqual(
            summary,
            body,
            f"the summary resolves {summary}px against a {body}px body, "
            "so the control is quieter than the text it conceals",
        )

    def test_a_count_and_its_not_published_cannot_diverge(self) -> None:
        """The five COUNTS rows have no absence class at all, and that is the
        point: one rule cannot diverge from itself.

        Asserted against the emitter and not the stylesheet, the same way
        `test_the_revision_slot_cannot_invert_because_one_class_carries_both`
        asserts its chain: a second class added here is what would start the
        divergence, and by the time it is in the stylesheet a CSS-only check is
        already comparing two rules rather than noticing there is now a pair.
        """
        emitter = re.search(r"const line = \(label, value\) =>([\s\S]*?);\n", self.cockpit_js)
        assert emitter is not None, "the COUNTS row emitter moved"
        body = emitter.group(1)
        self.assertIn('value == null ? "not published"', body)
        self.assertEqual(
            1,
            len(set(re.findall(r"next-cockpit-count-value[a-z-]*", body))),
            "the value and its absence no longer share one class",
        )


if __name__ == "__main__":
    unittest.main()


class EveryProjectContextWriterAgreesOnItsFieldsTest(NextPageJsHarness):
    """DRC-4612: five writers, two shapes, and both readers keyed off the gap.

    `projectContextByLabel` is written in four places in `project.js` and once
    in `next-cockpit.js`. The four carry `dashboard_revision`; the fifth did
    not, and both readers key off exactly what it omitted --
    `projectLoadContext` guards on `(old.dashboard_revision || old.generated)`
    and `projectRefreshControl` on `state === "loading"`.

    The criterion's falsifier is "a sixth writer added later with a third
    shape", so this is an enumeration over the source rather than a check of
    the one that was wrong. A writer added tomorrow with a different key set
    reds here without anyone remembering to extend a list.
    """

    # `state` is deliberately excluded from the compared set: it is the field
    # whose VALUE differs per writer (loading / ready / error), where the other
    # three must be present in all of them.
    REQUIRED: ClassVar[frozenset[str]] = frozenset({"data", "generated", "dashboard_revision"})

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    def run_fixture(self, checks: str) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    @staticmethod
    def _writers() -> list[tuple[str, int, set[str]]]:
        """Every `projectContextByLabel[...] = { ... }` literal, with its keys."""
        found: list[tuple[str, int, set[str]]] = []
        for name in ("project.js", "next-cockpit.js"):
            text = (frontend_page.WEB_DIR / name).read_text(encoding="utf-8")
            for match in re.finditer(r"projectContextByLabel\[[^\]]+\]\s*=\s*\{", text):
                depth, i = 1, match.end()
                while depth and i < len(text):
                    depth += (text[i] == "{") - (text[i] == "}")
                    i += 1
                body = text[match.end() : i - 1]
                keys = set(re.findall(r"(?:^|[{,\s])([A-Za-z_]\w*)\s*:", body))
                line = text[: match.start()].count("\n") + 1
                found.append((name, line, keys))
        return found

    def test_every_writer_declares_the_same_field_set(self) -> None:
        writers = self._writers()
        # A scan that found nothing would pass the check below in silence.
        #
        # Four, not the five DRC-4612 reports. That issue counted the
        # `const projectContextByLabel = {}` declaration at `project.js:18` as a
        # writer; it is the map's creation, and three object literals in
        # `project.js` plus one in `next-cockpit.js` are the real set. Corrected
        # on the issue rather than quietly written as four here.
        self.assertEqual(4, len(writers), f"the writer set moved: {writers}")
        short = {
            f"{name}:{line}": sorted(self.REQUIRED - keys)
            for name, line, keys in writers
            if self.REQUIRED - keys
        }
        self.assertEqual({}, short, "these writers omit a field both readers key off")

    def test_a_cockpit_render_cannot_move_an_in_flight_slot_out_of_loading(self) -> None:
        """DRC-4612 AC-2, as the state's survival rather than a field's presence.

        Asserting only that `dashboard_revision` is now written would pass while
        the state is still clobbered, which the criterion names as its falsifier.
        """
        out = self.run_fixture(
            """
// Derive both the tab and the key from the runtime rather than naming them:
// the writer only runs on the tab that renders the timeline, and its key comes
// from `projectContextKey(nextCockpitStableKey(group))`, which is not the
// route's project label. Guessing either made an earlier version of this test
// pass while the guard it defends was removed.
const group = nextProjectGroups()[0];
const key = projectContextKey(nextCockpitStableKey(group));
projectContextByLabel[key] = {
  state: "loading", data: null, generated: 7, dashboard_revision: 7
};
nextRoute = {view:"project", project:group.label, focus:null, tab:"decisions"};
renderNext();
const after = projectContextByLabel[key];
console.log(JSON.stringify({state: after && after.state,
                            revision: after && after.dashboard_revision,
                            wrote: !!after}));
"""
        )
        # The slot must still exist at all: a test that asserted only the state
        # would pass if the render never touched the key it seeded.
        self.assertTrue(out["wrote"], "the seeded slot vanished, so nothing was tested")
        self.assertEqual("loading", out["state"], "the cockpit clobbered an in-flight slot")
        self.assertEqual(7, out["revision"], "the in-flight revision was dropped")


class AStaleReadSaysSoOnBothSurfacesTest(NextPageJsHarness):
    """DRC-4613, the captain's 2026-09-21 ruling: disclose, do not stay silent.

    A semantic refresh that fails over data the board already had keeps the
    previous rows and, until this, presented them exactly as a fresh read. The
    rows are true; implying they are current is the board claiming more than it
    knows, which is the defect class this milestone exists to remove.

    Both surfaces are asserted together because the criterion's falsifier is a
    fix that moves one and not the other, and because a disclosure only inside
    the panel does not reach a reader looking at the tab strip.
    """

    FIXTURE = NextCockpitCompositionTest.FIXTURE

    def run_fixture(self, checks: str) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + self.FIXTURE,
        )

    # Drives the entry into each of the states `nextCockpitEntryState` produces,
    # rather than only the one that was wrong. `stale` is data plus error.
    DRIVE = """
const group = nextProjectGroups()[0];
const key = nextCockpitContextKey(group, null);
const held = nextCockpitContexts.get(key);
nextCockpitContexts.set(key, Object.assign({}, held, {error: %s, revision: 1755000000}));
nextRoute = {view:"project", project:group.label, focus:null, tab:"decisions"};
renderNext();
console.log(JSON.stringify({
  html: __els.app.innerHTML,
  state: nextCockpitContextRead(group, null).state
}));
"""

    def test_a_refresh_that_failed_over_existing_rows_says_so_in_the_panel(self) -> None:
        out = self.run_fixture(self.DRIVE % "true")
        self.assertEqual("stale", out["state"], "the fixture did not reach the stale state")
        self.assertIn("data-next-cockpit-stale-read", out["html"])
        self.assertIn("Refresh has failed since", out["html"])
        self.assertIn("these are the rows from that read", out["html"])

    def test_the_tab_cue_carries_it_too_so_an_unopened_panel_still_tells_you(self) -> None:
        out = self.run_fixture(self.DRIVE % "true")
        self.assertIn("data-next-cockpit-tab-stale", out["html"])
        # The marker is its own span with its own rule, not a variant class on
        # the wrapper: the count's ink does not change, only the word beside it.
        self.assertIn('class="next-cockpit-tab-cue-stale"', out["html"])

    def test_the_visible_cue_and_the_announced_one_agree(self) -> None:
        """A visible 'stale' with an unchanged gloss would tell a sighted reader
        one thing and a screen-reader user another, which this repository has
        shipped before."""
        out = self.run_fixture(self.DRIVE % "true")
        self.assertIn(">stale</span>", out["html"])
        self.assertIn("refresh has failed since", out["html"])

    def test_a_read_that_did_not_fail_says_none_of_it(self) -> None:
        """The other half of the claim: a clean resolve must be unchanged, or
        the disclosure is noise on every board rather than a signal on one."""
        out = self.run_fixture(self.DRIVE % "false")
        self.assertEqual("ready", out["state"])
        self.assertNotIn("data-next-cockpit-stale-read", out["html"])
        self.assertNotIn("data-next-cockpit-tab-stale", out["html"])
        self.assertNotIn("Refresh has failed since", out["html"])
