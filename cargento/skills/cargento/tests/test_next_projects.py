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
        self.assertEqual(
            [("codex", "live"), ("claude", "second")],
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


if __name__ == "__main__":
    unittest.main()
