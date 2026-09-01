from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NEXT_STYLES, NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextProjectsBehaviorTest(NextPageJsHarness):
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

        expected = ["alpha/repo", "beta/app", "delta/risk", "gamma/tool", "epsilon/close"]
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
        self.assertIn("1 exact request", alpha)
        self.assertNotIn("at risk", risk)
        self.assertNotIn("close the loop", close)
        self.assertIn("1 working", working)
        self.assertNotIn("quiet", quiet)
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

        self.assertIn("NOW · NEEDS INPUT", alpha)
        self.assertIn("Activity not published", alpha)
        self.assertIn("NEXT", alpha)
        self.assertIn("No pending step published", alpha)
        self.assertIn("BLOCKED · CAPTAIN", alpha)
        self.assertIn("Approve the release", alpha)
        self.assertIn("3 of 5 done", alpha)
        self.assertIn("launch", alpha)
        self.assertIn("review", alpha)
        self.assertIn("Ship the next page", alpha)
        self.assertIn("Check the release", alpha)
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
        self.assertIn("Latest assignment · Build the source-backed release", active_html)
        self.assertNotIn("Old historical assignment", history_html)
        for missing in (
            "No active session observed",
            "State unavailable",
            "Latest session context",
            "at risk",
            "close the loop",
            "quiet",
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
        self.assertIn("Codex", row)
        self.assertIn("Build the app", row)
        self.assertIn("Antigravity", row)
        self.assertIn("Capture the proof", row)
        self.assertIn("Compile exact release", row)
        self.assertIn("Publish checkpoint", row)
        self.assertIn("No reported block", row)
        self.assertIn("Synchronizing capture", row)
        self.assertIn("No pending step published", row)
        self.assertIn("Harness does not report blocks", row)
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
            r'<article class="next-attention-item"[^>]*'
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
        self.assertIn("BLOCKED · NEEDS YOU", beta)
        self.assertIn("Plain approval", beta)
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
        self.assertIn("BLOCKED · CAPTAIN", project)
        self.assertIn("Approve the release", project)
        self.assertIn("CAPTAIN</h2>", out["session"])
        for html in out.values():
            self.assertNotIn("NEEDS YOU</h2>", html)

    def test_the_cell_prefers_the_filtered_asked_line_over_the_raw_prompt(self) -> None:
        # `last_prompt` is the raw newest record on every harness but Codex, so
        # a Claude row can carry a harness-injected string there while the
        # runtime's own filtered reading of the same prompt sits beside it.
        html = self.render(
            """
const gate = nextData.sessions.find(session => session.sid === "alpha-gate");
gate.instruction = {label: "asked", text: "Cut the release branch", at: 9900};
const beta = nextData.sessions.find(session => session.sid === "beta-work");
beta.last_prompt = "proceed";
beta.instruction = {label: "earlier", text: "Not the newest thing asked", at: 9000};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        alpha = self.project_row(html, "alpha/repo")
        self.assertIn("Latest assignment · Cut the release branch", alpha)
        instruction = re.search(r'<div class="next-project-instruction">[\s\S]*?</div>', alpha)
        self.assertIsNotNone(instruction)
        self.assertNotIn("Approve the release", instruction.group(0) if instruction else "")
        # The other two labels stay out. This cell has nowhere to put a label,
        # and "agent" and "earlier" are the readings that need one: published
        # bare they claim to be the newest instruction when they are not.
        beta_row = self.project_row(html, "beta/app")
        self.assertNotIn("Latest session context", beta_row)
        self.assertNotIn("Not the newest thing asked", beta_row)

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
        self.assertNotIn(" of ", row)

    def test_blocked_wins_over_running_and_idle_is_explicit(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        alpha = self.project_row(html, "alpha/repo")
        beta = self.project_row(html, "beta/app")
        gamma = self.project_row(html, "gamma/tool")

        self.assertIn("next-project-row--blocked", alpha)
        self.assertIn("BLOCKED · CAPTAIN", alpha)
        self.assertIn("Approve the release", alpha)
        self.assertIn("NOW · WORKING", beta)
        self.assertIn("Activity not published", beta)
        self.assertIn("No pending step published", beta)
        self.assertNotIn("1 session executing", beta)
        self.assertNotIn("running", gamma)
        self.assertNotIn("blocked", gamma)
        self.assertNotIn("No active session observed", gamma)
        self.assertIn('data-next-project-history="true"', gamma)

    def test_two_idle_sessions_still_get_the_collision_caveat(self) -> None:
        html = self._run_page_js(
            "await __settle();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
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
        assert isinstance(html, str)

        self.assertEqual(1, html.count("data-next-project-row"))
        self.assertIn("2 sessions share this label", html)
        self.assertIn("Same label is not proof of the same directory", html)
        self.assertIn("sibling worktrees read alike", html)

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
        self.assertIn("No project display labels in this 24h payload.", html)
        self.assertIn('<nav aria-label="Primary">', html)
        self.assertIn('<a href="#n=projects" aria-current="page">Projects</a>', html)
        self.assertIn('<a href="#n=sessions">Sessions</a>', html)
        self.assertNotIn('data-next-view-body="attention"', html)

    def test_idle_requires_known_states_but_not_active_work(self) -> None:
        out = self.render(
            """
console.log(JSON.stringify({
  inactive: nextProjectNow([{state: "working", active: false}]),
  unknown: nextProjectNow([{active: false}])
}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn(">idle<", out["inactive"])
        self.assertEqual("", out["unknown"])

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


if __name__ == "__main__":
    unittest.main()
