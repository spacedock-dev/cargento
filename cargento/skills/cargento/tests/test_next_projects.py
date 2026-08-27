from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextProjectsBehaviorTest(NextPageJsHarness):
    FIXTURE = """
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000,
  window_hours: 24,
  summary: {working: 1, needs_input: 1},
  sessions: [
    {
      sid: "alpha-idle", project: "alpha/repo", state: "idle", active: false,
      last_activity: 9700, title: "Older instruction", total: 3, done: 1,
      spacedock: {role: "first-officer", workflows: [
        {workflow: "launch", goal: "Ship the next page", stages: [], entities: []}
      ]}, subagents: []
    },
    {
      sid: "alpha-gate", project: "alpha/repo", state: "needs_input", active: true,
      last_activity: 9900, last_prompt: "Approve the release", total: 2, done: 2,
      spacedock: {role: "first-officer", workflows: [
        {workflow: "review", goal: "Check the release", stages: [], entities: []}
      ]}, subagents: []
    },
    {
      sid: "beta-work", project: "beta/app", state: "working", active: true,
      last_activity: 9950, title: "Build the app", total: 0, done: 0,
      spacedock: null, subagents: []
    },
    {
      sid: "gamma-idle", project: "gamma/tool", state: "idle", active: false,
      last_activity: 9000, title: "Read the logs", total: 0, done: 0,
      spacedock: null, subagents: []
    }
  ]
})});
"""

    def render(self, checks: str = "console.log(JSON.stringify(__els.app.innerHTML));") -> object:
        return self._run_page_js("await __settle();\n" + checks, self.FIXTURE)

    @staticmethod
    def project_row(html: str, project: str) -> str:
        match = re.search(rf'<tr[^>]*data-next-project="{re.escape(project)}"[\s\S]*?</tr>', html)
        if match is None:
            raise AssertionError(f"no row for {project!r} in {html}")
        return match.group(0)

    def test_payload_groups_into_first_seen_rows_with_five_columns(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertEqual(3, html.count("data-next-project-row"))
        self.assertLess(
            html.index('data-next-project="alpha/repo"'), html.index('data-next-project="beta/app"')
        )
        self.assertLess(
            html.index('data-next-project="beta/app"'), html.index('data-next-project="gamma/tool"')
        )
        for heading in ("PROJECT", "PROGRESS", "ESTIMATE", "DELEGATION", "NOW"):
            self.assertIn(f">{heading}</th>", html)
        self.assertIn("3 of 5 done", self.project_row(html, "alpha/repo"))
        self.assertIn("launch", self.project_row(html, "alpha/repo"))
        self.assertIn("review", self.project_row(html, "alpha/repo"))
        self.assertIn("Ship the next page", self.project_row(html, "alpha/repo"))
        self.assertIn("Check the release", self.project_row(html, "alpha/repo"))
        self.assertIn(
            "last instruction · Approve the release", self.project_row(html, "alpha/repo")
        )

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
        self.assertIn("last instruction · Cut the release branch", alpha)
        self.assertNotIn("Approve the release", alpha)
        # The other two labels stay out. This cell has nowhere to put a label,
        # and "agent" and "earlier" are the readings that need one: published
        # bare they claim to be the newest instruction when they are not.
        beta_row = self.project_row(html, "beta/app")
        self.assertIn("last instruction · proceed", beta_row)
        self.assertNotIn("Not the newest thing asked", beta_row)

    def test_the_estimate_and_delegation_columns_are_withheld(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        row = self.project_row(html, "alpha/repo")
        estimate = re.search(r'<td class="next-project-estimate"[\s\S]*?</td>', row)
        delegation = re.search(r'<td class="next-project-delegation"[\s\S]*?</td>', row)

        self.assertIsNotNone(estimate)
        self.assertIsNotNone(delegation)
        estimate_html = estimate.group(0) if estimate else ""
        delegation_html = delegation.group(0) if delegation else ""
        self.assertIn("no estimate", estimate_html)
        self.assertIn("no confidence", estimate_html)
        self.assertNotRegex(estimate_html, r"\d")
        self.assertIn("not measured", delegation_html)
        self.assertNotIn("0%", delegation_html)
        self.assertNotIn("progress", delegation_html)

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
        self.assertIn(">● blocked<", alpha)
        self.assertNotIn("running", alpha)
        self.assertIn(">● 1 running<", beta)
        self.assertNotIn("blocked", beta)
        self.assertNotIn("running", gamma)
        self.assertNotIn("blocked", gamma)
        self.assertIn('class="next-project-now next-project-now--idle"', gamma)
        self.assertIn(">idle<", gamma)

    def test_two_idle_sessions_still_get_the_collision_caveat(self) -> None:
        html = self._run_page_js(
            "await __settle();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            """
__els.app = {innerHTML: ""};
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


if __name__ == "__main__":
    unittest.main()
