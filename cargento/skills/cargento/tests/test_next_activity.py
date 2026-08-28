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
      sid: "idle-fresh", harness: "codex", project: "alpha/repo",
      state: "idle", active: true, title: "Idle but still in the window",
      state_detail: "awaiting your message",
      last_activity: 9900, subagents: [], tasks: []
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

    @staticmethod
    def activity_subagent(card: str, index: int) -> str:
        match = re.search(
            rf'<span[^>]*data-next-activity-subagent="{index}"[\s\S]*?</span></span>',
            card,
        )
        if match is None:
            raise AssertionError(f"no activity subagent {index!r} in {card}")
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

    def test_a_fresh_idle_session_is_not_going_on(self) -> None:
        """`active` is freshness, not work. Reading it as work put every session
        the display window still carried into GOING ON — the whole idle tail of a
        busy repo, each row captioned "awaiting your message"."""
        html = self.render()
        assert isinstance(html, str)

        self.assertNotIn('data-next-going-on="idle-fresh"', html)
        self.assertNotIn("Idle but still in the window", html)
        self.assertIn('data-next-going-on="work-a"', html)

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

    def test_card_subagents_are_bounded_escaped_and_use_payload_clock_ages(self) -> None:
        html = self.render(
            """
__setNow(999999);
nextData.sessions.find(session => session.sid === "work-z").subagents = [
  {name: "worker <one>", model: "secret-model", started_at: 2260},
  {name: "worker-two", started_at: null},
  {name: "worker-three", started_at: 10010},
  {name: "worker-four", started_at: "bad"},
  null,
  {name: "worker-six", started_at: 9600},
  {name: "worker-seven", started_at: 9500},
  {name: "worker-eight", started_at: 9400}
];
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        card = self.activity_card(html, "work-z")

        self.assertIn('class="next-activity-subagents" role="list" aria-label="Subagents"', card)
        self.assertEqual(6, card.count("data-next-activity-subagent="))
        measured = self.activity_subagent(card, 0)
        unmeasured = self.activity_subagent(card, 1)
        clamped = self.activity_subagent(card, 2)
        invalid = self.activity_subagent(card, 3)
        fallback = self.activity_subagent(card, 4)
        self.assertIn("worker &lt;one&gt;", measured)
        self.assertNotIn("worker <one>", measured)
        self.assertNotIn("secret-model", measured)
        self.assertIn("2h 9m", measured)
        self.assertIn("worker-two", unmeasured)
        self.assertNotRegex(unmeasured, r"\d+m")
        self.assertIn("worker-three", clamped)
        self.assertIn("0s", clamped)
        self.assertIn("worker-four", invalid)
        self.assertNotRegex(invalid, r"\d+m")
        self.assertIn("subagent", fallback)
        self.assertNotRegex(fallback, r"\d+m")
        self.assertIn("worker-six", card)
        self.assertNotIn("worker-seven", card)
        self.assertNotIn("worker-eight", card)
        self.assertIn("+2 more", card)

    def test_subagents_render_for_gates_and_malformed_collections_are_omitted(self) -> None:
        html = self.render(
            """
nextData.sessions.find(session => session.sid === "gate-z").subagents = [
  {name: "gate-worker", started_at: 9700}
];
nextData.sessions.find(session => session.sid === "work-z").subagents = {length: 99};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        gate = self.activity_card(html, "gate-z")
        work = self.activity_card(html, "work-z")

        self.assertIn("gate-worker", gate)
        self.assertIn("5m", self.activity_subagent(gate, 0))
        self.assertNotIn("next-activity-subagents", work)

    def test_a_card_carries_the_same_labelled_second_line_the_other_surfaces_do(self) -> None:
        # GOING ON was the one next-UI surface the instruction line skipped, so
        # the card most likely to be read named work that may have finished.
        # Same renderer as the session table and the detail header: the policy
        # for when a line may be shown has one definition, not three.
        html = self.render(
            """
nextData.sessions.find(session => session.sid === "gate-z").instruction =
  {label: "asked", text: "Recompute the byte pins", at: 9400};
nextData.sessions.find(session => session.sid === "work-a").instruction =
  {label: "urgent", text: "Never rendered", at: 9400};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        gate = self.activity_card(html, "gate-z")

        self.assertIn('data-next-instruction="asked"', gate)
        self.assertIn('<span class="next-instruction-label">asked</span>, 10m:', gate)
        self.assertIn("Recompute the byte pins", gate)
        # A card is a `<button>`, which takes phrasing content, so this one line
        # renders as a span where the other two surfaces use a paragraph.
        self.assertIn('<span class="next-activity-instruction"', gate)
        self.assertNotIn("<p ", gate)
        # A label outside the published vocabulary is refused here too.
        self.assertNotIn("Never rendered", html)
        # And a row the payload publishes no line for keeps its two lines.
        self.assertNotIn("next-activity-instruction", self.activity_card(html, "work-z"))

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
        # "Foreign completed task" is a Cursor row's own completed task, and it
        # belongs here. It was excluded while DONE read `harness === "claude"`,
        # which reported "No completed tracked tasks" over work every other
        # harness had finished. Project scope still holds: see "Other completed".
        subjects = (
            "Repeat work",
            "Foreign completed task",
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
        self.assertNotIn("Other completed", done_html)
        self.assertEqual(5, done_html.count('aria-label="completed"'))

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
