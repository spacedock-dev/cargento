from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextActivityBehaviorTest(NextPageJsHarness):
    FIXTURE = """
location.hash = "#n=project:alpha%2Frepo";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000,
  rate_window_sec: 600,
  window_hours: 24,
  summary: {working: 3, needs_input: 2},
  harnesses: [
    {key: "claude", label: "Claude Code"},
    {key: "codex", label: "Codex"},
    {key: "cursor", label: "Cursor"}
  ],
  sessions: [
    {
      sid: "gate-z", harness: "claude", project: "alpha/repo",
      state: "needs_input", active: true, title: "First gate",
      state_detail: "open question · AskUserQuestion", blocked_since: 9400,
      last_activity: 9400, subagents: [],
      tasks: [
        {id: "1", subject: "Repeat work", status: "completed"},
        {id: "2", subject: "Still pending", status: "pending"}
      ]
    },
    {
      sid: "gate-a", harness: "codex", project: "alpha/repo",
      state: "needs_input", active: true, title: "Second gate",
      state_detail: "awaiting approval", blocked_since: null,
      last_activity: 9300, subagents: [], tasks: []
    },
    {
      sid: "work-a", harness: "cursor", project: "alpha/repo",
      state: "working", active: true, title: "Normal work",
      state_detail: "running Bash", rate_per_min: 14.2,
      last_activity: 9990, turn: {long: false}, subagents: [],
      tasks: [{id: "3", subject: "Foreign completed task", status: "completed"}]
    },
    {
      sid: "work-z", harness: "claude", project: "alpha/repo",
      state: "working", active: true, last_prompt: "Long work",
      state_detail: "running 1 subagent", rate_per_min: 1234.6,
      last_activity: 9980, turn: {long: true}, subagents: [{}],
      tasks: [
        {id: "4", subject: "Not finished", status: "in_progress"},
        {id: "5", subject: "Review <script>", status: "completed"},
        {id: "6", subject: "Repeat work", status: "completed"}
      ]
    },
    {
      sid: "inactive-work", harness: "codex", project: "alpha/repo",
      state: "working", active: false, title: "Inactive working row",
      rate_per_min: 88, last_activity: 9970, subagents: [], tasks: []
    },
    {
      sid: "idle", harness: "claude", project: "alpha/repo",
      state: "idle", active: false, title: "Idle row",
      last_activity: 9000, subagents: [],
      tasks: [{id: "7", subject: "Archived payload item", status: "completed"}]
    },
    {
      sid: "other", harness: "claude", project: "other/repo",
      state: "working", active: true, title: "Other project",
      rate_per_min: 9, last_activity: 9999, subagents: [],
      tasks: [{id: "8", subject: "Other completed", status: "completed"}]
    }
  ]
})});
"""

    def render(self, checks: str = "console.log(JSON.stringify(__els.app.innerHTML));") -> object:
        return self._run_page_js("await __settle();\n" + checks, self.FIXTURE)

    @staticmethod
    def activity_card(html: str, sid: str) -> str:
        match = re.search(
            rf'<button[^>]*data-next-going-on="{re.escape(sid)}"[\s\S]*?</button>',
            html,
        )
        if match is None:
            raise AssertionError(f"no GOING ON card for {sid!r} in {html}")
        return match.group(0)

    def test_going_on_keeps_gate_order_then_uses_the_active_attention_ladder(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        order = [
            html.index(f'data-next-going-on="{sid}"')
            for sid in ("gate-z", "gate-a", "work-z", "work-a")
        ]
        self.assertEqual(sorted(order), order)
        self.assertNotIn('data-next-going-on="inactive-work"', html)
        self.assertNotIn('data-next-going-on="idle"', html)
        self.assertNotIn("Other project", html)

    def test_cards_render_payload_clock_metrics_registry_labels_and_activity(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        gate = self.activity_card(html, "gate-z")
        unstamped_gate = self.activity_card(html, "gate-a")
        work = self.activity_card(html, "work-z")

        self.assertNotIn("next-live", gate)
        self.assertNotIn("next-live", unstamped_gate)
        self.assertIn('aria-label="needs input"', gate)
        self.assertIn("10m wait", gate)
        self.assertIn("Claude Code · open question · AskUserQuestion", gate)
        self.assertNotIn(" wait", unstamped_gate)
        self.assertIn("next-live", work)
        self.assertIn('aria-label="working"', work)
        self.assertIn("1,235 /m", work)
        self.assertIn("Claude Code · running 1 subagent", work)

    def test_a_card_click_sets_the_session_route(self) -> None:
        out = self.render(
            """
const html = __els.app.innerHTML;
const match = html.match(/data-next-going-on="gate-z"[^>]*data-next-route="([^"]+)"/);
const token = match ? match[1] : "";
__fire("click", {
  target: {closest(selector){
    return selector === "[data-next-route]" ? {dataset: {nextRoute: token}} : null;
  }},
  preventDefault(){}
});
console.log(JSON.stringify({html, route: nextRoute, hash: location.hash}));
"""
        )
        assert isinstance(out, dict)

        self.assertIn(
            'data-next-going-on="gate-z" data-next-route="session:alpha%2Frepo:gate-z"',
            out["html"],
        )
        self.assertEqual(
            {"view": "session", "project": "alpha/repo", "session": "gate-z"},
            out["route"],
        )
        self.assertEqual("#n=session:alpha%2Frepo:gate-z", out["hash"])

    def test_done_lists_only_completed_tasks_in_payload_order_without_deduplication(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        done = re.search(r'data-next-project-activity="done"[\s\S]*?</section>', html)

        self.assertIsNotNone(done)
        done_html = done.group(0) if done else ""
        subjects = (
            "Repeat work",
            "Review &lt;script&gt;",
            "Repeat work",
            "Archived payload item",
        )
        positions = []
        start = 0
        for subject in subjects:
            position = done_html.index(subject, start)
            positions.append(position)
            start = position + len(subject)
        self.assertEqual(sorted(positions), positions)
        self.assertEqual(2, done_html.count("Repeat work"))
        self.assertNotIn("Still pending", done_html)
        self.assertNotIn("Not finished", done_html)
        self.assertNotIn("Foreign completed task", done_html)
        self.assertNotIn("Other completed", done_html)
        self.assertEqual(4, done_html.count('aria-label="completed"'))

    def test_done_has_no_spacedock_source(self) -> None:
        html = self._run_page_js(
            "await __settle();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            """
location.hash = "#n=project:spacedock%2Frepo";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000, window_hours: 24,
  summary: {working: 0, needs_input: 0}, harnesses: [], sessions: [{
    sid: "fo", project: "spacedock/repo", state: "idle", active: false,
    tasks: [], subagents: [], spacedock: {role: "first-officer", workflows: [{
      workflow: "launch", stages: ["release"],
      entities: [{slug: "terminal-looking-entity", stage: "release", live: false}]
    }]}
  }]
})});
""",
        )
        assert isinstance(html, str)
        done = re.search(r'data-next-project-activity="done"[\s\S]*?</section>', html)

        self.assertIsNotNone(done)
        done_html = done.group(0) if done else ""
        self.assertIn("No completed tracked tasks in this payload.", done_html)
        self.assertNotIn("terminal-looking-entity", done_html)
        self.assertNotIn('aria-label="completed"', done_html)

    def test_both_halves_render_explicit_empty_lines(self) -> None:
        html = self._run_page_js(
            "await __settle();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            """
location.hash = "#n=project:quiet%2Frepo";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000, window_hours: 24,
  summary: {working: 0, needs_input: 0}, harnesses: [], sessions: [{
    sid: "quiet", project: "quiet/repo", state: "idle", active: false,
    tasks: [], subagents: [], spacedock: null
  }]
})});
""",
        )
        assert isinstance(html, str)

        self.assertIn("Nothing active or waiting on you in this project.", html)
        self.assertIn("No completed tracked tasks in this payload.", html)


if __name__ == "__main__":
    unittest.main()
