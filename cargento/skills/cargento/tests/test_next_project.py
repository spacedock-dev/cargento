from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NextPageJsHarness
from .test_next_projects import V2_MODEL_FIXTURE


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextProjectBehaviorTest(NextPageJsHarness):
    FIXTURE = """
location.hash = "#n=project:alpha%2Frepo";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000,
  rate_window_sec: 600,
  window_hours: 24,
  summary: {working: 1, needs_input: 1},
  harnesses: [
    {key: "claude", label: "Claude Code"},
    {key: "codex", label: "Codex"}
  ],
  sessions: [
    {
      sid: "alpha-gate", harness: "claude", project: "alpha/repo",
      state: "needs_input", active: true, last_activity: 9200,
      title: "Older instruction", total: 2, done: 1, subagents: [],
      spacedock: {role: "first-officer", workflows: [{
        workflow: "launch", goal: "Ship the next page",
        stages: ["intake", "review", "release"],
        entities: [
          {slug: "release-candidate", stage: "release", cycle: "", live: false},
          {slug: "queued-change", stage: "intake", cycle: "", live: false},
          {slug: "approve-copy", stage: "review", cycle: "c2", live: true}
        ]
      }]}
    },
    {
      sid: "alpha-work", harness: "codex", project: "alpha/repo",
      state: "working", active: true, last_activity: 9300,
      last_prompt: "Finish the project page", total: 3, done: 1, subagents: [],
      spacedock: {role: "first-officer", workflows: [
        {
          workflow: "launch", goal: "Ship the next page",
          stages: ["intake", "review", "release", "observe"],
          entities: [
            {slug: "release-candidate", stage: "review", cycle: "c3", live: true},
            {slug: "watch-rollout", stage: "observe", cycle: "", live: false}
          ]
        },
        {
          workflow: "audit", goal: "Check the release",
          stages: ["scan", "report"],
          entities: [{slug: "security-report", stage: "report", cycle: "", live: false}]
        }
      ]}
    },
    {
      sid: "other", harness: "claude", project: "other/repo",
      state: "idle", active: false, last_activity: 9999,
      title: "Do not fold this project", subagents: [], spacedock: null
    }
  ]
})});
"""

    def render(self, checks: str = "console.log(JSON.stringify(__els.app.innerHTML));") -> object:
        return self._run_page_js("await __settle();\n" + checks, self.FIXTURE)

    @staticmethod
    def plan(html: str, workflow: str) -> str:
        match = re.search(
            rf'<section[^>]*data-next-plan="{re.escape(workflow)}"[\s\S]*?</section>', html
        )
        if match is None:
            raise AssertionError(f"no PLAN block for {workflow!r} in {html}")
        return match.group(0)

    @staticmethod
    def entity_row(html: str, slug: str) -> str:
        match = re.search(
            rf'<div[^>]*data-next-plan-entity="{re.escape(slug)}"[\s\S]*?</div>', html
        )
        if match is None:
            raise AssertionError(f"no entity row for {slug!r} in {html}")
        return match.group(0)

    def test_project_header_and_two_column_slots_render_for_the_selected_group(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertIn('data-next-view-body="project"', html)
        self.assertIn('data-next-project-detail="alpha/repo"', html)
        self.assertNotIn("data-next-project-main", html)
        self.assertNotIn("data-next-project-rail", html)
        self.assertIn("data-next-cockpit-plan-details", html)
        self.assertIn("<summary>Show project plan</summary>", html)
        self.assertIn('class="next-project-detail-name">alpha/repo</', html)
        self.assertIn("launch", html)
        self.assertIn("audit", html)
        self.assertNotIn("latest session context", html)
        self.assertNotIn("latest assignment", html)
        self.assertIn("2 sessions share this display label", html)
        self.assertIn("shared location is not established", html)
        self.assertNotIn("Do not fold this project", html)

    def test_two_workflows_in_one_project_render_two_independent_plans(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertEqual(2, html.count("data-next-plan="))
        self.assertLess(html.index('data-next-plan="launch"'), html.index('data-next-plan="audit"'))
        launch = self.plan(html, "launch")
        audit = self.plan(html, "audit")
        self.assertIn("release-candidate", launch)
        self.assertNotIn("security-report", launch)
        self.assertIn("security-report", audit)
        self.assertNotIn("release-candidate", audit)

    def test_same_workflow_merges_by_slug_prefers_live_and_uses_stage_order(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        launch = self.plan(html, "launch")

        self.assertEqual(1, launch.count('data-next-plan-entity="release-candidate"'))
        self.assertLess(launch.index("queued-change"), launch.index("approve-copy"))
        self.assertLess(launch.index("release-candidate"), launch.index("approve-copy"))
        self.assertLess(launch.index("release-candidate"), launch.index("watch-rollout"))
        chosen = self.entity_row(launch, "release-candidate")
        self.assertIn('data-next-live="true"', chosen)
        self.assertIn(">●<", chosen)
        self.assertIn("Codex", chosen)
        self.assertIn("c3", chosen)

    def test_ownership_and_unhealthy_states_are_only_drawn_from_proven_live_sources(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        blocked = self.entity_row(html, "approve-copy")
        stalled = self.entity_row(html, "release-candidate")
        pending = self.entity_row(html, "queued-change")
        self.assertIn("Claude Code", blocked)
        self.assertIn("blocked on you", blocked)
        self.assertIn("Codex", stalled)
        self.assertIn("stalled 11m", stalled)
        self.assertIn('data-next-live="false"', pending)
        self.assertIn(">○<", pending)
        self.assertNotIn("Claude Code", pending)
        self.assertNotIn("Codex", pending)
        self.assertNotIn("blocked on you", pending)
        self.assertNotIn("stalled", pending)

    def test_the_header_estimate_is_withheld_and_the_unhealthy_entity_count_is_real(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        status = re.search(r'<div class="next-project-detail-status"[\s\S]*?</div>', html)

        self.assertIsNotNone(status)
        status_html = status.group(0) if status else ""
        self.assertIn(
            "2 entities unhealthy — <span data-next-withheld>estimate withheld",
            status_html,
        )
        self.assertNotIn("no estimate left", status_html)
        self.assertNotIn("no confidence", status_html)

    def test_the_unhealthy_entity_label_uses_the_singular(self) -> None:
        html = self.render(
            """
nextData.sessions.find(session => session.sid === "alpha-work").last_activity = 9999;
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("1 entity unhealthy", html)
        self.assertNotIn("1 entities unhealthy", html)
        self.assertNotIn("1 step unhealthy", html)

    def test_a_declared_plan_with_no_entities_reports_a_measured_zero(self) -> None:
        html = self.render(
            """
for(const session of nextData.sessions){
  const workflows = session.spacedock && session.spacedock.workflows || [];
  for(const workflow of workflows) workflow.entities = [];
}
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("0 entities unhealthy", html)
        self.assertNotIn("0 entity unhealthy", html)
        self.assertNotIn("0 steps unhealthy", html)

    def test_stalled_uses_the_named_floor_and_payload_clock(self) -> None:
        out = self.render(
            """
__setNow(999999);
const session = {state: "working", last_activity: 9401};
const entity = {live: true, session};
const fresh = nextProjectEntityState(entity);
session.last_activity = 9399;
const stale = nextProjectEntityState(entity);
session.last_activity = 2260;
const older = nextProjectEntityState(entity);
console.log(JSON.stringify({fresh, stale, older, floor: NEXT_PROJECT_STALLED_SEC}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(600, out["floor"])
        self.assertEqual({"label": "", "unhealthy": False}, out["fresh"])
        self.assertEqual({"label": "stalled 10m", "unhealthy": True}, out["stale"])
        self.assertEqual({"label": "stalled 2h 9m", "unhealthy": True}, out["older"])

    def test_plan_never_fabricates_completion_or_pull_request_states(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        plans = self.plan(html, "launch") + self.plan(html, "audit")

        self.assertNotIn("✓", plans)
        self.assertNotRegex(plans, r"\d+ of \d+")
        self.assertNotIn("merged", plans)
        self.assertNotIn("in review", plans)
        self.assertNotIn("failed", plans)

    def test_project_discovery_renders_two_workflows_without_session_attachment_metadata(
        self,
    ) -> None:
        checks = """
await __settle();
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        html = self._run_page_js(
            checks,
            """
location.hash = "#n=project:plain%2Frepo";
__els.app = {innerHTML: ""};
const dashboard = {
  generated: 10000, rate_window_sec: 600, window_hours: 24,
  summary: {working: 0, needs_input: 0}, harnesses: [], sessions: [
    {sid: "plain", harness: "codex", project: "plain/repo", project_key: "git:plain",
     state: "idle", active: true, spacedock: null, subagents: []}
  ]
};
__fetchImpl = async url => ({ok: true, json: async () =>
  String(url).startsWith("/api/project-context") ? {
    workflow_discovery: {state: "observed", source: "spacedock status --discover", workflows: [
      {workflow: "dev", goal: "Build safely", stages: ["shaping", "review"]},
      {workflow: "explore", goal: "Explore safely", stages: ["discovery", "shaping"]}
    ]}, semantic: {facts: [], work_items: [], projections: {}}
  } : dashboard});
""",
        )
        assert isinstance(html, str)

        self.assertEqual(2, html.count("data-next-workflow-definition="))
        self.assertIn('data-next-workflow-definition="dev"', html)
        self.assertIn('data-next-workflow-definition="explore"', html)
        self.assertIn("Build safely", html)
        self.assertIn("Explore safely", html)
        self.assertNotIn("declares no workflow", html)
        self.assertNotIn("data-next-plan=", html)

    def test_workflow_observation_states_keep_their_sources_distinct(self) -> None:
        checks = """
await __settle();
const cases = {};
for(const project of ["plain/repo", "empty/fo", "worker/repo"]){
  nextRoute = {view: "project", project, session: null};
  renderNext();
  await __settle();
  await __settle();
  cases[project] = __els.app.innerHTML;
}
console.log(JSON.stringify(cases));
"""
        out = self._run_page_js(
            checks,
            """
location.hash = "#n=project:plain%2Frepo";
__els.app = {innerHTML: ""};
const dashboard = {
  generated: 10000, rate_window_sec: 600, window_hours: 24,
  summary: {working: 0, needs_input: 0}, harnesses: [], sessions: [
    {sid: "plain", project: "plain/repo", state: "idle", spacedock: null, subagents: []},
    {sid: "fo", project: "empty/fo", state: "idle",
     spacedock: {role: "first-officer", workflows: []}, subagents: []},
    {sid: "worker", project: "worker/repo", state: "working",
     spacedock: {role: "ensign", workflows: []}, subagents: []}
  ]
};
const contexts = {
  "plain/repo": {workflow_discovery: {state: "none", workflows: []},
    semantic: {facts: [], work_items: [], projections: {}}},
  "empty/fo": {workflow_discovery: {state: "unavailable", reason: "project root unavailable", workflows: []},
    semantic: {facts: [], work_items: [], projections: {}}},
  "worker/repo": {workflow_discovery: {state: "error", reason: "discovery timed out", workflows: []},
    semantic: {facts: [], work_items: [{kind: "workflow_item"}], projections: {}}}
};
__fetchImpl = async url => ({ok: true, json: async () => {
  const value = String(url);
  if(!value.startsWith("/api/project-context")) return dashboard;
  const project = decodeURIComponent((value.match(/[?&]project=([^&]+)/) || [])[1] || "");
  return contexts[project];
}});
""",
        )
        assert isinstance(out, dict)

        self.assertNotIn("no commissioned workflow directories", out["plain/repo"])
        self.assertNotIn("first-officer attachment", out["empty/fo"])
        self.assertIn("project root unavailable", out["empty/fo"])
        self.assertNotIn("semantic timeline", out["worker/repo"])
        self.assertIn("discovery timed out", out["worker/repo"])
        for html in out.values():
            self.assertNotIn("Show project plan", html)
            self.assertNotIn("data-next-plan=", html)
            self.assertNotIn("declares no workflow", html)
            self.assertNotIn("unhealthy", html)
            self.assertNotIn("next-project-detail-divider", html)

    def test_missing_project_is_bounded_and_links_to_the_complete_project_map(self) -> None:
        html = self.render(
            """
nextRoute = {view: "project", project: "missing/repo", session: null};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("Not present in the current payload", html)
        self.assertIn('href="#n=projects"', html)
        self.assertNotIn("deleted", html.lower())
        self.assertNotIn("completed", html.lower())


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextProjectV2Test(NextPageJsHarness):
    def test_legacy_plan_records_follow_model_identity_even_without_a_raw_label(self) -> None:
        out = self._run_page_js(
            V2_MODEL_FIXTURE
            + """
nextObserved = () => ({...v2Model, sessions: [], totals: {running: 0, subagents: 0}});
// Retain the raw-record adapter assertion while the cockpit owns composition.
nextProjectCockpit = context => nextProjectPlanBlock(context) + nextProjectDone(context);
nextData = {generated: 10000, sessions: [{sid: "live", harness: "codex", total: 3, done: 2,
  spacedock: {role: "first-officer", workflows: [{workflow: "Retained plan", goal: "Keep the plan", stages: [], entities: []}]}
}]};
console.log(JSON.stringify(nextProjectView("alpha/repo")));
"""
        )
        assert isinstance(out, str)
        self.assertIn("Retained plan", out)
        self.assertIn("2 of 3 done", out)

    def test_published_goal_and_timeline_values_are_escaped_without_normalizing(self) -> None:
        out = self._run_page_js(
            V2_MODEL_FIXTURE
            + """
v2Project.goalKnown = true;
v2Project.goalText = "  Ship <exactly>\\n  what was asked.  ";
v2Project.goalSrcText = "Harness <source>";
v2Project.goalGapKnown = false;
v2Project.changes = [
  {at: 9900, filled: true, label: "Finished <build>", harness: "codex"},
  {at: 9910, filled: false, label: "Needs approval", harness: "claude"}
];
v2Project.changeNoteText = "1 of 2 unattended · last 3m";
nextWorkstreamCollapsed = false;
console.log(JSON.stringify({goal: nextProjectGoal(v2Project), changes: nextProjectChanges(v2Project)}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("  Ship &lt;exactly&gt;\n  what was asked.  ", out["goal"])
        self.assertIn("Harness &lt;source&gt;", out["goal"])
        self.assertNotIn("publish no goal", out["goal"])
        self.assertIn("1 of 2 unattended · last 3m", out["changes"])
        self.assertIn("Finished &lt;build&gt;", out["changes"])
        self.assertIn("Needs approval", out["changes"])
        self.assertIn("codex", out["changes"])
        self.assertIn("claude", out["changes"])
        self.assertEqual(1, out["changes"].count('aria-label="unattended"'))
        self.assertEqual(1, out["changes"].count('aria-label="attended"'))

    def test_identity_goal_and_model_timeline_survive_both_toggle_directions(self) -> None:
        out = self._run_page_js(
            V2_MODEL_FIXTURE
            + """
nextObserved = () => ({...v2Model, sessions: [], totals: {running: 0, subagents: 0}});
// RC-3 folding follows this merge; these renderers must remain callable now.
nextViewBody = () => {
  const context = {project: v2Project};
  return nextProjectDetailHeader({...context, plans: []}) + nextProjectGoal(v2Project) +
    nextProjectChanges(v2Project) + '<div data-rail-project="' + context.project.key + '">rail</div>';
};
nextData = {generated: 10000, sessions: []};
nextRoute = {view: "project", project: "alpha/repo", session: null};
__els.app = {innerHTML: ""};
nextWorkstreamCollapsed = false;
renderNext();
const open = __els.app.innerHTML;
const click = {target: {closest: selector => selector === "[data-next-workstream-toggle]" ? {} : null}, preventDefault(){}};
__fire("click", click);
renderNext();
const closed = __els.app.innerHTML;
__fire("click", click);
renderNext();
console.log(JSON.stringify({open, closed, reopened: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        for html in out.values():
            self.assertIn("No harness published a goal", html)
            self.assertIn("Exact location not published", html)
            self.assertIn("1 of 1 sessions publish no goal.", html)
            self.assertIn("no state changes observed in the last 3m", html)
            self.assertIn('data-rail-project="alpha/repo"', html)
        self.assertIn('aria-expanded="true"', out["open"])
        self.assertIn('aria-expanded="false"', out["closed"])
        self.assertNotIn('class="next-workstream-empty"', out["closed"])
        self.assertIn('aria-expanded="true"', out["reopened"])


if __name__ == "__main__":
    unittest.main()
