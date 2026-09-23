from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NEXT_STYLES, NextPageJsHarness

# A literal frozen-interface fixture keeps view tests independent of workstream A.
V2_MODEL_FIXTURE = """
const v2Session = {
  sid: "live", harness: "codex", project: "alpha/repo",
  titleText: "Title not published", titleKnown: false,
  nowText: "Compiling", nowKnown: true,
  nextText: "No pending step published", nextKnown: false,
  turnText: "Harness does not report turn bounds", turnKnown: false,
  state: "working", isWorking: true, isNeeds: false, isEnded: false, isQuiet: false,
  tone: "ok", stuckText: "No stuck signal published", stuckKnown: false,
  askText: "No exact request published", askKnown: false,
  rateText: "Token rate not reported", rateKnown: false,
  waitedText: "Wait duration not published", subagents: [], tasks: [],
  outcomeText: "No end outcome published", outcomeKnown: false, outcomeGlyph: "",
  gitText: "Git state was not measured", gitKnown: false
};
const v2Project = {
  key: "alpha/repo", scopeText: "Exact location not published", scopeKnown: false,
  countLine: "1 session · 1 working", sharedLabelText: "No shared display label observed",
  sharedLabelKnown: false, goalText: "No harness published a goal", goalKnown: false,
  goalSrcText: "No goal source published", goalGapText: "1 of 1 sessions publish no goal.",
  goalGapKnown: true, sessions: [v2Session], needs: [], working: [v2Session], ended: [],
  risky: [], tone: "ok", changes: [], changeNoteText: "no state changes observed in the last 3m"
};
const v2Model = {projects: [v2Project], activeProjects: [v2Project], restProjects: []};
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextProjectsBehaviorTest(NextPageJsHarness):
    def test_a_blocked_project_precedes_risk_and_work_with_stable_ties(self) -> None:
        for reverse in ("false", "true"):
            with self.subTest(reverse=reverse):
                out = self._run_page_js(
                    f"""
__els.app = {{innerHTML: ""}};
const sessions = [
  {{sid: "work", project: "work", state: "working"}},
  {{sid: "risk", project: "risk", state: "working", loop: {{errors: 4, tool: "Bash"}}}},
  {{sid: "review", project: "review", state: "idle", active: false,
    finished_at: 9700, last_activity: 9700}},
  {{sid: "gate-a", project: "gate-a", state: "needs_input"}},
  {{sid: "gate-b", project: "gate-b", state: "needs_input"}},
  {{sid: "gate-c", project: "gate-c", state: "needs_input"}},
  {{sid: "exact", project: "exact", state: "working"}},
  {{sid: "ended", project: "ended", state: "needs_input", ended_at: 9800}},
  {{sid: "recent", project: "recent", state: "idle", last_activity: 9950}}
].map(s => ({{harness: "claude", active: true, last_activity: 9900, ...s}}));
if({reverse}) sessions.reverse();
nextData = {{generated: 10000, sessions, ask: true, asks: [
  {{id: "question", session_id: "exact", project: "exact", question: "Approve?"}}
]}};
const original = JSON.stringify(nextData);
nextAttention = nextAttentionModel(nextData);
nextRoute = {{view: "projects", project: null, session: null}};
renderNext();
console.log(JSON.stringify({{html: __els.app.innerHTML,
  unchanged: original === JSON.stringify(nextData)}}));
"""
                )
                assert isinstance(out, dict)
                html = out["html"]
                order = re.findall(r'<article[^>]*data-next-project="([^"]+)"', html)
                self.assertEqual(
                    [
                        "exact",
                        "gate-a",
                        "gate-b",
                        "gate-c",
                        "risk",
                        "work",
                        "ended",
                        "recent",
                        "review",
                    ],
                    order,
                )
                self.assertTrue(out["unchanged"])
                self.assertIn("1 waiting on you", self.project_row(html, "gate-a"))
                self.assertIn("1 working", self.project_row(html, "risk"))
                self.assertNotIn("close the loop", self.project_row(html, "review"))
                self.assertNotIn("blocked", self.project_row(html, "ended"))

    FIXTURE = """
location.hash = "#n=projects";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000,
  window_hours: 24,
  ask: true,
  summary: {working: 1, needs_input: 1},
  sessions: [
    {
      sid: "beta-work", project: "beta/app", state: "working", active: true,
      last_activity: 9950, title: "Build the app", total: 0, done: 0,
      spacedock: null, subagents: []
    },
    {
      sid: "gamma-idle", project: "gamma/tool", state: "idle", active: false,
      last_activity: 9000, title: "Read the logs", total: 0, done: 0,
      spacedock: null, subagents: []
    },
    {
      sid: "delta-loop", project: "delta/risk", state: "idle", active: false,
      last_activity: 9700, title: "Inspect failures", total: 0, done: 0,
      loop: {errors: 4, tool: "Bash"}, spacedock: null, subagents: []
    },
    {
      sid: "alpha-gate", project: "alpha/repo", state: "needs_input", active: true,
      last_activity: 9900, last_prompt: "Approve the release", total: 5, done: 3,
      spacedock: {role: "first-officer", workflows: [
        {workflow: "launch", goal: "Ship the next page", stages: [], entities: []},
        {workflow: "review", goal: "Check the release", stages: [], entities: []}
      ]}, subagents: []
    },
    {
      sid: "epsilon-stop", project: "epsilon/close", state: "idle", active: false,
      last_activity: 8000, finished_at: 8000, dirty: true, changed: 3,
      title: "Stopped work", total: 0, done: 0, spacedock: null, subagents: []
    }
  ],
  asks: [
    {
      id: "ask-alpha", session_id: "alpha-gate", project: "alpha/repo",
      question: "Approve the release", options: ["Approve", "Hold"]
    },
    {
      id: "ask-unresolved", session_id: "", project: "gamma/tool",
      question: "Unresolved label-only request", options: ["Ignore"]
    }
  ]
})});
"""

    def render(self, checks: str = "console.log(JSON.stringify(__els.app.innerHTML));") -> object:
        return self._run_page_js("await __settle();\n" + checks, self.FIXTURE)

    @staticmethod
    def project_row(html: str, project: str) -> str:
        match = re.search(
            rf'<article[^>]*data-next-project="{re.escape(project)}"[\s\S]*?</article>', html
        )
        if match is None:
            raise AssertionError(f"no row for {project!r} in {html}")
        return match.group(0)

    def test_complete_map_reuses_attention_summary_for_order_and_supported_counts(self) -> None:
        out = self.render(
            """
const projects = __els.app.innerHTML;
nextRoute = {view: "session", project: "alpha/repo", session: "alpha-gate"};
renderNext();
console.log(JSON.stringify({projects, session: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        html = out["projects"]

        expected = ["alpha/repo", "beta/app", "delta/risk", "epsilon/close", "gamma/tool"]
        positions = [html.index(f'data-next-project="{project}"') for project in expected]
        self.assertEqual(sorted(positions), positions)
        self.assertEqual(5, html.count("data-next-project-row"))
        for project in expected:
            self.assertEqual(1, html.count(f'data-next-project="{project}"'))

        alpha = self.project_row(html, "alpha/repo")
        risk = self.project_row(html, "delta/risk")
        close = self.project_row(html, "epsilon/close")
        working = self.project_row(html, "beta/app")
        quiet = self.project_row(html, "gamma/tool")
        self.assertIn("1 waiting on you", alpha)
        self.assertNotIn("at risk", risk)
        self.assertNotIn("close the loop", close)
        self.assertIn("1 working", working)
        self.assertIn("1 quiet", quiet)
        self.assertNotIn("0 exact requests", html)
        self.assertNotIn("0 at risk", html)
        self.assertNotIn("0 close the loop", html)
        self.assertNotIn("0 working", html)
        self.assertNotIn("0 quiet", html)
        self.assertNotIn("next-command-brief", html)
        self.assertNotIn('class="next-project-progress"></div>', html)
        self.assertNotIn("next-project-workflow", risk + close + working + quiet)
        self.assertNotIn("RESPONSE", risk + close + working + quiet)
        self.assertNotIn("Unresolved label-only request", quiet)
        self.assertNotIn("exact request", quiet)

        self.assertIn('aria-label="needs_input"', alpha)
        self.assertIn("Activity not published", alpha)
        self.assertIn("next-project-session-next", alpha)
        self.assertIn("No pending step published", alpha)
        self.assertIn("1 waiting on you", alpha)
        self.assertIn("Title not published", alpha)
        self.assertNotIn("Latest session context", alpha)
        self.assertIn("CAPTAIN</h2>", out["session"])
        self.assertNotIn("NEEDS YOU</h2>", out["session"])

    def test_active_projects_lead_and_history_omits_operational_placeholders(self) -> None:
        html = self.render(
            """
nextData.sessions.find(session => session.sid === "beta-work").instruction = {
  label: "asked", text: "Build the source-backed release", at: 9950
};
nextData.sessions.find(session => session.sid === "gamma-idle").instruction = {
  label: "asked", text: "Old historical assignment", at: 9000
};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        active = re.search(r'<section[^>]*data-next-project-group="active"[\s\S]*?</section>', html)
        history = re.search(
            r'<section[^>]*data-next-project-group="history"[\s\S]*?</section>', html
        )
        self.assertIsNotNone(active)
        self.assertIsNotNone(history)
        active_html = active.group(0) if active else ""
        history_html = history.group(0) if history else ""
        self.assertLess(
            html.index('data-next-project-group="active"'),
            html.index('data-next-project-group="history"'),
        )
        for project in ("alpha/repo", "beta/app"):
            self.assertIn(f'data-next-project="{project}"', active_html)
            self.assertNotIn(f'data-next-project="{project}"', history_html)
        for project in ("gamma/tool", "delta/risk", "epsilon/close"):
            self.assertIn(f'data-next-project="{project}"', history_html)
            self.assertNotIn(f'data-next-project="{project}"', active_html)
        self.assertIn("1 waiting on you", active_html)
        self.assertNotIn("Old historical assignment", history_html)
        for missing in (
            "No active session observed",
            "State unavailable",
            "Latest session context",
            "at risk",
            "close the loop",
            "SITUATION",
            "RESPONSE",
        ):
            self.assertNotIn(missing, history_html)

    def test_active_project_preserves_each_exact_sessions_command_facts(self) -> None:
        html = self.render(
            """
nextData.harnesses = [
  {key: "codex", label: "Codex", reports_needs_input: true},
  {key: "antigravity", label: "Antigravity", reports_needs_input: false}
];
const codex = nextData.sessions.find(session => session.sid === "beta-work");
codex.harness = "codex";
codex.tasks = [
  {status: "in_progress", subject: "Compile exact release"},
  {status: "pending", subject: "Publish checkpoint"}
];
nextData.sessions.push({
  sid: "beta-work", harness: "antigravity", project: "beta/app",
  state: "working", active: true, state_detail: "Synchronizing capture",
  last_activity: 9940, title: "Capture the proof", total: 0, done: 0,
  spacedock: null, tasks: [], subagents: []
});
nextAttention = nextAttentionModel(nextData);
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        row = self.project_row(html, "beta/app")

        self.assertEqual(2, row.count("data-next-project-session"))
        self.assertIn('data-next-harness="codex" data-next-session="beta-work"', row)
        self.assertIn('data-next-harness="antigravity" data-next-session="beta-work"', row)
        self.assertIn("codex", row)
        self.assertIn("Build the app", row)
        self.assertIn("antigravity", row)
        self.assertIn("Capture the proof", row)
        self.assertIn("Compile exact release", row)
        self.assertIn("Publish checkpoint", row)
        self.assertIn('aria-label="working"', row)
        self.assertIn("Synchronizing capture", row)
        self.assertIn("No pending step published", row)
        self.assertIn("next-project-tone--unknown", row)
        self.assertNotIn("2 sessions executing", row)
        self.assertNotIn("Assignment unavailable", row)
        self.assertNotIn("ASSIGNMENT · Not published", row)

    def test_plain_exact_ask_keeps_attention_without_claiming_captain_authority(self) -> None:
        out = self.render(
            """
location.hash = "#n=projects";
nextRoute = nextRouteFromFragment(location.hash);
nextData.sessions.push({
  sid: "beta-spacedock-sibling", project: "beta/app", state: "idle", active: false,
  last_activity: 9000, title: "Sibling session", total: 0, done: 0,
  spacedock: {role: "first-officer", workflows: []}, subagents: []
});
nextData.asks = [{
  id: "ask-beta", session_id: "beta-work", project: "beta/app",
  question: "Plain approval", options: ["Approve"]
}];
nextAttention = nextAttentionModel(nextData);
renderNext();
const projects = __els.app.innerHTML;
nextRoute = {view: "attention", project: null, session: null};
renderNext();
const attention = __els.app.innerHTML;
nextRoute = {view: "session", project: "beta/app", session: "beta-work"};
renderNext();
console.log(JSON.stringify({attention, projects, session: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("NEEDS YOU · Source not identified", out["attention"])
        beta_attention = re.search(
            r'<article class="next-attention-item next-attention-item--legacy"[^>]*'
            r'data-next-subject-key="session:\[&quot;&quot;,&quot;beta-work&quot;\]"[^>]*>'
            r"(.*?)</article>",
            out["attention"],
            re.DOTALL,
        )
        self.assertIsNotNone(beta_attention)
        self.assertIn(
            "NEEDS YOU · Source not identified",
            beta_attention.group(1) if beta_attention else "",
        )
        self.assertNotIn(
            "CAPTAIN · Source not identified",
            beta_attention.group(1) if beta_attention else "",
        )
        beta = self.project_row(out["projects"], "beta/app")
        self.assertIn("next-project-tone--want", beta)
        self.assertIn("Build the app", beta)
        self.assertNotIn("BLOCKED · CAPTAIN", beta)
        self.assertIn("NEEDS YOU</h2>", out["session"])
        self.assertNotIn("CAPTAIN</h2>", out["session"])

    def test_exact_spacedock_owner_is_captain_on_attention_projects_and_session(self) -> None:
        out = self.render(
            """
const projects = __els.app.innerHTML;
nextRoute = {view: "attention", project: null, session: null};
renderNext();
const attention = __els.app.innerHTML;
nextRoute = {view: "session", project: "alpha/repo", session: "alpha-gate"};
renderNext();
console.log(JSON.stringify({attention, projects, session: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("CAPTAIN · Source not identified", out["attention"])
        project = self.project_row(out["projects"], "alpha/repo")
        self.assertIn("1 waiting on you", project)
        self.assertIn("Title not published", project)
        self.assertIn("CAPTAIN</h2>", out["session"])
        for html in out.values():
            self.assertNotIn("NEEDS YOU</h2>", html)

    def test_the_goal_prefers_the_filtered_asked_line_over_the_raw_prompt(self) -> None:
        # `last_prompt` is the raw newest record on every harness but Codex, so
        # a Claude row can carry a harness-injected string there while the
        # runtime's own filtered reading of the same prompt sits beside it.
        html = self.render(
            """
// The cockpit's assignment fold follows this merge; keep v2's goal contract callable.
nextProjectCockpit = context => nextProjectGoal(context.project);
const gate = nextData.sessions.find(session => session.sid === "alpha-gate");
gate.instruction = {label: "asked", text: "Cut the release branch", at: 9900};
const beta = nextData.sessions.find(session => session.sid === "beta-work");
beta.last_prompt = "proceed";
beta.instruction = {label: "earlier", text: "Not the newest thing asked", at: 9000};
nextRoute = {view: "project", project: "alpha/repo", session: null};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("Cut the release branch", html)
        goal = re.search(r'<section class="next-project-goal">[\s\S]*?</section>', html)
        self.assertIsNotNone(goal)
        self.assertNotIn("Approve the release", goal.group(0) if goal else "")
        self.assertNotIn("Not the newest thing asked", html)

    def test_absent_inventory_facts_do_not_displace_the_command_answer(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        self.assertNotIn("ESTIMATE", html)
        self.assertNotIn("DELEGATION", html)
        self.assertNotIn("no estimate", html)
        self.assertNotIn("not measured", html)

    def test_project_summary_counts_have_visible_separation(self) -> None:
        self.assertIn(
            ".next-project-summary{display:flex;flex-wrap:wrap;gap:4px 10px}",
            NEXT_STYLES,
        )

    def test_no_exact_ask_omits_the_request_lede_and_response_region(self) -> None:
        html = self.render(
            """
nextData.asks = [];
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertNotIn("CAPTAIN —", html)
        self.assertNotIn("NEEDS YOU —", html)
        self.assertNotIn("next-command-brief", html)
        self.assertNotIn("No request observed", html)
        self.assertNotIn("Current payload only", html)
        gamma = self.project_row(html, "gamma/tool")
        self.assertNotIn("RESPONSE", gamma)
        self.assertNotIn("next-project-command", gamma)

    def test_a_project_with_no_task_counts_renders_no_progress(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        row = self.project_row(html, "gamma/tool")

        self.assertNotIn("next-project-progress-bar", row)
        self.assertNotIn("tasks done", row)

    def test_blocked_wins_over_running_and_idle_is_explicit(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        alpha = self.project_row(html, "alpha/repo")
        beta = self.project_row(html, "beta/app")
        gamma = self.project_row(html, "gamma/tool")

        self.assertIn("next-project-tone--want", alpha)
        self.assertIn("1 waiting on you", alpha)
        self.assertIn("Title not published", alpha)
        self.assertIn('aria-label="working"', beta)
        self.assertIn("Activity not published", beta)
        self.assertIn("No pending step published", beta)
        self.assertNotIn("1 session executing", beta)
        self.assertNotIn("running", gamma)
        self.assertNotIn("blocked", gamma)
        self.assertNotIn("No active session observed", gamma)
        self.assertIn('data-next-project-history="true"', gamma)

    def test_two_idle_sessions_still_get_the_collision_caveat(self) -> None:
        out = self._run_page_js(
            """
await __settle();
const projects = __els.app.innerHTML;
nextRoute = {view: "project", project: "repo/main", session: null};
renderNext();
console.log(JSON.stringify({projects, detail: __els.app.innerHTML}));
""",
            """
__els.app = {innerHTML: ""};
location.hash = "#n=projects";
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000, window_hours: 24,
  summary: {working: 0, needs_input: 0},
  sessions: [
    {sid: "one", project: "repo/main", state: "idle", active: false, last_activity: 9000, subagents: []},
    {sid: "two", project: "repo/main", state: "idle", active: false, last_activity: 8000, subagents: []}
  ]
})});
""",
        )
        assert isinstance(out, dict)
        html = out["projects"]

        self.assertEqual(1, html.count("data-next-project-row"))
        self.assertIn("2 sessions · 2 quiet", html)
        self.assertIn('data-next-route="project:repo%2Fmain"', html)
        self.assertIn("2 sessions share this display label", out["detail"])
        self.assertIn("shared location is not established", out["detail"])

    def test_zero_session_projects_keeps_its_route_and_bounded_empty_sentence(self) -> None:
        html = self.render(
            """
nextData.sessions = [];
nextData.asks = [];
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn('<section class="next-projects" data-next-view-body="projects">', html)
        self.assertIn("<h1>Projects</h1>", html)
        self.assertIn("No project has active session evidence right now.", html)
        self.assertIn('<nav aria-label="Primary">', html)
        self.assertIn('<a href="#n=projects" aria-current="page">Projects</a>', html)
        self.assertIn('<a href="#n=sessions">Sessions</a>', html)
        self.assertNotIn('data-next-view-body="attention"', html)

    def test_no_published_state_still_has_an_explicit_count(self) -> None:
        html = self.render("""
nextData.sessions = [{sid: "unknown", project: "unknown", subagents: []}];
nextData.asks = [];
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")
        assert isinstance(html, str)
        self.assertIn("1 session · 1 in no counted state", html)

    def test_clicking_a_project_row_uses_the_project_route(self) -> None:
        out = self.render(
            """
const html = __els.app.innerHTML;
__fire("click", {
  target: {closest(selector){
    return selector === "[data-next-route]" ? {dataset: {nextRoute: "project:alpha%2Frepo"}} : null;
  }},
  preventDefault(){}
});
console.log(JSON.stringify({html, route: nextRoute, hash: location.hash}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn('data-next-route="project:alpha%2Frepo"', out["html"])
        self.assertEqual(
            {"view": "project", "project": "alpha/repo", "session": None}, out["route"]
        )
        self.assertEqual("#n=project:alpha%2Frepo", out["hash"])

    def test_project_briefs_are_focusable_and_enter_activates_the_route(self) -> None:
        out = self.render(
            """
const html = __els.app.innerHTML;
const target = {dataset: {nextRoute: "project:alpha%2Frepo"}, closest(selector){
  return selector === "[data-next-route]" ? this : null;
}, getAttribute(name){ return name === "role" ? "link" : null; }};
__fire("keydown", {target, key: "Enter", preventDefault(){}});
console.log(JSON.stringify({html, route: nextRoute, hash: location.hash}));
"""
        )
        assert isinstance(out, dict)

        row = self.project_row(out["html"], "alpha/repo")
        self.assertIn('role="link"', row)
        self.assertIn('tabindex="0"', row)
        self.assertEqual(
            {"view": "project", "project": "alpha/repo", "session": None}, out["route"]
        )
        self.assertEqual("#n=project:alpha%2Frepo", out["hash"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ProjectRowDenominatorTest(NextPageJsHarness):
    """Every state word and the leading total count the same project collection."""

    SUMMARY = re.compile(r'<div class="next-project-summary">([\s\S]*?)</div>')

    def summary(self, sessions: str, asks: str = "[]") -> str:
        html = self._run_page_js(
            "await __settle();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            f"""
__els.app = {{innerHTML: ""}};
location.hash = "#n=projects";
__fetchImpl = async () => ({{ok: true, json: async () => ({{
  generated: 10000, window_hours: 24, ask: true,
  summary: {{}}, sessions: {sessions}, asks: {asks}
}})}});
""",
        )
        assert isinstance(html, str)
        match = self.SUMMARY.search(html)
        if match is None:  # pragma: no cover — the assertion below reports it
            raise AssertionError(f"no project summary in {html}")
        return match.group(1)

    def test_all_distinguishable_states_share_one_hand_counted_denominator(self) -> None:
        self.assertEqual(
            "5 sessions · 1 working · 1 waiting on you · 1 ended · 1 quiet · 1 in no counted state",
            self.summary("""[
              {sid: "work", project: "mixed", state: "working", active: true},
              {sid: "wait", project: "mixed", state: "needs_input", active: true},
              {sid: "end", project: "mixed", state: "idle", ended_at: 9900},
              {sid: "quiet", project: "mixed", state: "idle", active: false},
              {sid: "unknown", project: "mixed", state: "starting", active: false}
            ]"""),
        )

    def test_a_row_with_one_of_three_sessions_active_says_so(self) -> None:
        # Measured at HEAD in Chrome and in this harness, the same group rendered
        # `3 sessions   1 subject at risk   1 working`: two sessions in the total
        # and in neither state word. The three sharing a label are one collision
        # subject, which is why `at risk` reads 1 over 3 sessions and keeps the
        # unit DRC-4426 gave it.
        self.assertEqual(
            "3 sessions · 1 working · 2 quiet",
            self.summary(
                """[
  {sid: "one", project: "trio/app", state: "working", active: true,
   last_activity: 9950, title: "Build", subagents: []},
  {sid: "two", project: "trio/app", state: "idle", active: false,
   last_activity: 9000, title: "Read", subagents: []},
  {sid: "three", project: "trio/app", state: "idle", active: false,
   last_activity: 8900, title: "Wait", subagents: []}
]"""
            ),
        )

    def test_an_all_idle_row_says_none_are_active_rather_than_going_quiet(self) -> None:
        # The history arm, and the ordinary row on a quiet machine rather than an
        # edge case: those rows are rendered with an empty active set, so the row
        # read `3 sessions` and said nothing about any of them.
        self.assertEqual(
            "3 sessions · 3 quiet",
            self.summary(
                """[
  {sid: "one", project: "trio/app", state: "idle", active: false,
   last_activity: 9950, title: "Build", subagents: []},
  {sid: "two", project: "trio/app", state: "idle", active: false,
   last_activity: 9000, title: "Read", subagents: []},
  {sid: "three", project: "trio/app", state: "idle", active: false,
   last_activity: 8900, title: "Wait", subagents: []}
]"""
            ),
        )

    def test_one_idle_session_holding_an_exact_request_still_reads_quiet(self) -> None:
        # `summary.quiet` is reachable and is not dead code: an outstanding exact
        # request holds an idle row in the active set through the ask branch at
        # next-sessions.js:86, which next-sessions.js:81-83 documents as
        # deliberate. This is the payload that renders it.
        self.assertEqual(
            "1 session · 1 quiet",
            self.summary(
                """[
  {sid: "solo", project: "quiet/repo", state: "idle", active: false,
   last_activity: 9000, title: "Idle work", subagents: []}
]""",
                """[
  {id: "ask-solo", session_id: "solo", project: "quiet/repo",
   question: "Which branch?", options: ["main", "next"]}
]""",
            ),
        )

    def test_a_blocked_session_is_counted_rather_than_left_out_of_every_word(self) -> None:
        # `working` and `quiet` do not cover `needs_input`, so the one active
        # session on this row sat in the leading total and in no word at all.
        # The three session states now partition the active subset.
        self.assertEqual(
            "1 session · 1 waiting on you",
            self.summary(
                """[
  {sid: "gate", project: "gate/repo", state: "needs_input", active: true,
   last_activity: 9900, title: "Approve", subagents: []}
]"""
            ),
        )

    def test_an_active_session_in_no_published_state_is_still_accounted_for(self) -> None:
        # The residue, and why the three state words are not enough alone: an
        # outstanding exact request holds a row active whatever its state says,
        # so a state outside the collectors' closed vocabulary would otherwise
        # vanish from the words while staying in the total. The construction the
        # Attention brief already uses at next-attention.js:1069-1073.
        self.assertEqual(
            "1 session · 1 in no counted state",
            self.summary(
                """[
  {sid: "odd", project: "odd/repo", state: "starting", active: true,
   last_activity: 9900, title: "Booting", subagents: []}
]""",
                """[
  {id: "ask-odd", session_id: "odd", project: "odd/repo",
   question: "Ready?", options: ["yes"]}
]""",
            ),
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextProjectsV2Test(NextPageJsHarness):
    def test_reasons_and_navigation_reach_every_rendered_row(self) -> None:
        out = self._run_page_js(
            V2_MODEL_FIXTURE
            + """
const before = JSON.stringify(v2Model);
const html = nextProjectsView(v2Model);
console.log(JSON.stringify({html, unchanged: before === JSON.stringify(v2Model)}));
"""
        )
        assert isinstance(out, dict)
        html = out["html"]
        self.assertTrue(out["unchanged"])
        for reason in (
            "Title not published",
            "Exact location not published",
            "No pending step published",
        ):
            self.assertIn(reason, html)
        self.assertIn('data-next-route="project:alpha%2Frepo"', html)
        self.assertRegex(
            html,
            r'<button[^>]*data-next-project-session[^>]*data-next-route="session:alpha%2Frepo:codex:live"',
        )
        self.assertIn("1 session · 1 working", html)
        self.assertIn(">Active</h2>", html)
        self.assertIn("identity stays reachable; operational claims lapse", html)

    def test_every_session_line_binds_its_own_exact_navigation_target(self) -> None:
        out = self._run_page_js(
            V2_MODEL_FIXTURE
            + """
v2Project.sessions = [v2Session, {...v2Session, harness: "claude", sid: "second", isWorking: false, isNeeds: true, state: "needs_input", tone: "want"}];
const html = nextProjectsView(v2Model);
__els.app = {innerHTML: html};
const tokens = [...html.matchAll(/<button[^>]*data-next-project-session[^>]*data-next-route="([^"]+)"/g)].map(match => match[1]);
const routes = [];
for(const token of tokens){
  __fire("click", {target: {closest: selector => selector === "[data-next-route]" ? {dataset: {nextRoute: token}} : null}, preventDefault(){}});
  routes.push({...nextRoute});
}
console.log(JSON.stringify({html, routes}));
"""
        )
        assert isinstance(out, dict)
        # Blocked on you renders first (DRC-4647), so the needs-input line leads.
        self.assertEqual(
            [("claude", "second"), ("codex", "live")],
            [(route["harness"], route["session"]) for route in out["routes"]],
        )
        self.assertEqual(0, out["html"].count("next-project-dot--working"))
        for button in re.findall(r"<button[^>]*data-next-project-session[^>]*>", out["html"]):
            self.assertIn("data-next-focus=", button)

    def test_groups_follow_the_model_order_and_history_has_no_activity_claims(self) -> None:
        out = self._run_page_js(
            V2_MODEL_FIXTURE
            + """
const blocked = {...v2Project, key: "z-blocked", tone: "want"};
const rest = {...v2Project, key: "old", countLine: "1 session · 1 quiet"};
v2Model.activeProjects = [blocked, v2Project];
v2Model.restProjects = [rest];
console.log(JSON.stringify(nextProjectsView(v2Model)));
"""
        )
        assert isinstance(out, str)
        self.assertLess(
            out.index('data-next-project="z-blocked"'), out.index('data-next-project="alpha/repo"')
        )
        row = NextProjectsBehaviorTest.project_row(out, "old")
        self.assertIn('data-next-route="project:old"', row)
        self.assertIn("1 session · 1 quiet", row)
        self.assertNotIn("Compiling", row)
        self.assertNotIn("data-next-project-session", row)


PROJECT_PAYLOAD_JS = """
__els.app = {innerHTML: ""};
const base = {harness: "claude", project: "repo/main", active: true, last_activity: 9900};
function renderProjects(sessions){
  nextData = {generated: 100000, sessions: sessions.map(s => ({...base, ...s}))};
  nextAttention = nextAttentionModel(nextData);
  nextRoute = {view: "projects", project: null, session: null};
  renderNext();
  return __els.app.innerHTML;
}
function lines(html){
  return [...html.matchAll(/<button[^>]*data-next-project-session[^>]*data-next-session="([^"]+)"[^>]*>([\\s\\S]*?)<\\/button>/g)]
    .map(m => ({sid: m[1], body: m[2]}));
}
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextProjectMemberLinesTest(NextPageJsHarness):
    """DRC-4646 and DRC-4647: what a member line claims, and how many render."""

    def test_a_quiet_session_is_hollow_and_says_how_long_it_has_been_quiet(self) -> None:
        out = self._run_page_js(
            PROJECT_PAYLOAD_JS
            + """
const html = renderProjects([
  {sid: "work", state: "working", last_activity: 9995},
  {sid: "quiet", state: "idle", state_detail: "awaiting your message", last_activity: 100000 - 23 * 3600},
  {sid: "gone", state: "idle", ended_at: 9800, last_activity: 9800},
  {sid: "gate", state: "needs_input", state_detail: "waiting for your input"}
]);
console.log(JSON.stringify(lines(html)));
"""
        )
        assert isinstance(out, list)
        by = {row["sid"]: row["body"] for row in out}
        dot = {}
        for sid, body in by.items():
            found = re.search(r'<span class="(next-project-dot[^"]*)"', body)
            assert found is not None, body
            dot[sid] = found.group(1)
        self.assertIn("next-project-dot--working", dot["work"])
        self.assertIn("next-project-dot--quiet", dot["quiet"])
        self.assertNotIn("next-project-tone--ok", dot["quiet"])
        self.assertIn("next-project-dot--ended", dot["gone"])
        self.assertNotIn("next-project-dot--quiet", dot["gone"])
        self.assertIn("next-project-tone--want", dot["gate"])
        self.assertNotIn("next-project-dot--quiet", dot["gate"])
        self.assertIn("last active 23h 0m ago", by["quiet"])
        self.assertNotIn("awaiting your message", by["quiet"])
        self.assertIn("waiting for your input", by["gate"])

    def test_the_three_lifecycle_dots_differ_by_shape_not_only_by_colour(self) -> None:
        # Greyscale test by construction: working is filled, quiet is a ring,
        # ended is square. Colour alone must not be what tells them apart.
        styles = NEXT_STYLES
        self.assertRegex(styles, r"\.next-project-dot--quiet\{[^}]*background:transparent")
        self.assertRegex(
            styles,
            r"\.next-project-dot\.next-project-dot--filled\{[^}]*background:var\(--project-tone\)",
        )
        # The fill must outrank the unknown-tone rule, which empties the dot.
        self.assertLess(
            styles.index(".next-project-dot.next-project-tone--unknown{"),
            styles.index(".next-project-dot.next-project-dot--filled{"),
        )
        self.assertRegex(styles, r"\.next-project-dot--ended\{[^}]*border-radius:1px")

    def test_working_on_a_harness_without_block_reporting_is_still_filled(self) -> None:
        # Goose, Gemini and Droid publish no block state, so a working row's
        # tone is unknown; before the fix that drew the same ring as quiet.
        out = self._run_page_js(
            PROJECT_PAYLOAD_JS
            + """
const html = renderProjects([{sid: "g", harness: "goose", state: "working", last_activity: 99990}]);
console.log(JSON.stringify(lines(html)[0].body));
"""
        )
        assert isinstance(out, str)
        self.assertIn("next-project-tone--unknown", out)
        self.assertIn("next-project-dot--filled", out)
        self.assertNotIn("next-project-dot--quiet", out)

    def test_an_idle_session_holding_a_request_is_blocked_not_quiet(self) -> None:
        out = self._run_page_js(
            PROJECT_PAYLOAD_JS
            + """
nextData = null;
const sessions = [{sid: "asker", state: "idle", last_activity: 99000}, {sid: "w", state: "working"}]
  .map(s => ({...base, ...s}));
nextData = {generated: 100000, sessions, ask: true,
  asks: [{id: "q", session_id: "asker", project: "repo/main", question: "Ship it?"}]};
nextAttention = nextAttentionModel(nextData);
nextRoute = {view: "projects", project: null, session: null};
renderNext();
console.log(JSON.stringify(lines(__els.app.innerHTML)));
"""
        )
        assert isinstance(out, list)
        asker = next(row["body"] for row in out if row["sid"] == "asker")
        self.assertEqual("asker", out[0]["sid"])
        self.assertIn("next-project-dot--filled", asker)
        self.assertNotIn("next-project-dot--quiet", asker)
        self.assertNotIn("last active", asker)

    def test_a_risky_quiet_member_is_pinned_past_the_cap_and_keeps_its_colour(self) -> None:
        out = self._run_page_js(
            PROJECT_PAYLOAD_JS
            + """
const sessions = [{sid: "w", state: "working", last_activity: 99999}];
for(let i = 0; i < 6; i++) sessions.push({sid: "q" + i, state: "idle", last_activity: 99900 + i});
sessions.push({sid: "dirty", state: "idle", last_activity: 90000, finished_at: 90000,
  dirty: true, changed: 3});
const html = renderProjects(sessions);
console.log(JSON.stringify(lines(html)));
"""
        )
        assert isinstance(out, list)
        sids = [row["sid"] for row in out]
        self.assertIn("dirty", sids)
        self.assertEqual(["w", "dirty"], sids[:2])
        dirty = out[1]["body"]
        self.assertIn("next-project-dot--quiet", dirty)
        self.assertIn("next-project-tone--bad", dirty)

    def test_a_long_project_shows_five_lines_and_names_the_rest(self) -> None:
        out = self._run_page_js(
            PROJECT_PAYLOAD_JS
            + """
const sessions = [
  {sid: "q1", state: "idle", last_activity: 9000},
  {sid: "q2", state: "idle", last_activity: 9500},
  {sid: "q3", state: "idle", last_activity: 9990},
  {sid: "g1", state: "needs_input"},
  {sid: "e1", state: "idle", ended_at: 9990, last_activity: 9990},
  {sid: "w1", state: "working", last_activity: 9999},
  {sid: "q4", state: "idle", last_activity: 9100},
  {sid: "g2", state: "needs_input"}
];
const html = renderProjects(sessions);
const more = html.match(/<button[^>]*data-next-project-more[^>]*>([^<]*)<\\/button>/);
const moreTag = html.match(/<button[^>]*data-next-project-more[^>]*>/);
console.log(JSON.stringify({sids: lines(html).map(r => r.sid), more: more && more[1],
  tag: moreTag && moreTag[0]}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(["g1", "g2", "w1", "q3", "q2"], out["sids"])
        self.assertEqual("3 other sessions", out["more"])
        self.assertIn('data-next-route="project:repo%2Fmain"', out["tag"] or "")

    def test_blocked_and_working_members_are_never_hidden_to_meet_the_cap(self) -> None:
        out = self._run_page_js(
            PROJECT_PAYLOAD_JS
            + """
const sessions = [];
for(let i = 0; i < 6; i++) sessions.push({sid: "g" + i, state: "needs_input"});
sessions.push({sid: "w", state: "working"});
sessions.push({sid: "q", state: "idle"});
const html = renderProjects(sessions);
const more = html.match(/<button[^>]*data-next-project-more[^>]*>([^<]*)<\\/button>/);
console.log(JSON.stringify({sids: lines(html).map(r => r.sid), more: more && more[1]}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(["g0", "g1", "g2", "g3", "g4", "g5", "w"], out["sids"])
        self.assertEqual("1 other session", out["more"])

    def test_a_project_at_the_cap_has_no_count_line(self) -> None:
        out = self._run_page_js(
            PROJECT_PAYLOAD_JS
            + """
// One working member keeps the project Active; an all-quiet one is history.
const sessions = [{sid: "w", state: "working"}];
for(let i = 0; i < 4; i++) sessions.push({sid: "q" + i, state: "idle", last_activity: 9000 + i});
const html = renderProjects(sessions);
console.log(JSON.stringify({count: lines(html).length, more: html.includes("data-next-project-more")}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(5, out["count"])
        self.assertFalse(out["more"])


if __name__ == "__main__":
    unittest.main()
