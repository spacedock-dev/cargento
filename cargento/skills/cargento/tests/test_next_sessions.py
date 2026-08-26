from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextSessionsBehaviorTest(NextPageJsHarness):
    FIXTURE = """
location.search = "?next=true";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000,
  window_hours: 24,
  summary: {working: 2, needs_input: 2},
  harnesses: [
    {key: "claude", label: "Claude Code"},
    {key: "codex", label: "Codex"},
    {key: "cursor", label: "Cursor"}
  ],
  sessions: [
    {
      sid: "gate-z", harness: "claude", project: "repo/main", state: "needs_input",
      active: true,
      title: "First gate", state_detail: "open question · AskUserQuestion",
      blocked_since: 9400, last_activity: 9400, subagents: []
    },
    {
      sid: "gate-a", harness: "codex", project: "solo/app", state: "needs_input",
      active: true,
      title: "Second gate", state_detail: null,
      blocked_since: null, last_activity: 9000, subagents: []
    },
    {
      sid: "work-a", harness: "cursor", project: "work/app", state: "working",
      active: true,
      title: "Normal work", state_detail: "running Bash", rate_per_min: 12,
      last_activity: 9990, turn: {long: false}, subagents: []
    },
    {
      sid: "work-z", harness: "claude", project: "repo/main", state: "working",
      active: true,
      title: "Long work", state_detail: "running 1 subagent", rate_per_min: 42,
      last_activity: 9980, turn: {long: true}, subagents: [{}]
    },
    {
      sid: "idle-old", harness: "claude", project: "idle/old", state: "idle",
      active: false,
      title: "Old idle", state_detail: null, last_activity: 7000,
      finished_at: 7000, subagents: []
    },
    {
      sid: "idle-new", harness: "codex", project: "idle/new", state: "idle",
      active: false,
      title: "New idle", state_detail: null, last_activity: 9460,
      finished_at: 9460, subagents: []
    },
    {
      sid: "idle-mid", harness: "cursor", project: "idle/mid", state: "idle",
      active: false,
      title: "Middle idle", state_detail: null, last_activity: 8800,
      finished_at: 8800, subagents: []
    }
  ]
})});
"""

    def render(self, checks: str = "console.log(JSON.stringify(__els.app.innerHTML));") -> object:
        return self._run_page_js(
            "await __settle();\nnextSelectSessions();\n" + checks, self.FIXTURE
        )

    @staticmethod
    def session_row(html: str, sid: str) -> str:
        match = re.search(rf'<tr[^>]*data-next-session="{re.escape(sid)}"[\s\S]*?</tr>', html)
        if match is None:
            raise AssertionError(f"no row for {sid!r} in {html}")
        return match.group(0)

    def test_flat_list_preserves_each_segment_ordering_contract(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertLess(
            html.index('data-next-session="gate-a"'), html.index('data-next-session="work-z"')
        )
        self.assertLess(
            html.index('data-next-session="work-a"'), html.index('data-next-session="idle-new"')
        )
        self.assertLess(
            html.index('data-next-session="gate-z"'), html.index('data-next-session="gate-a"')
        )
        self.assertLess(
            html.index('data-next-session="work-z"'), html.index('data-next-session="work-a"')
        )
        self.assertLess(
            html.index('data-next-session="idle-new"'), html.index('data-next-session="idle-mid"')
        )
        self.assertLess(
            html.index('data-next-session="idle-mid"'), html.index('data-next-session="idle-old"')
        )

    def test_flat_list_uses_one_body_without_state_headings(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertEqual(1, html.count("<tbody>"))
        self.assertNotIn("data-next-session-block", html)
        self.assertNotIn("next-session-group", html)
        self.assertNotIn('scope="rowgroup"', html)

    def test_empty_flat_list_keeps_headers_and_one_empty_body(self) -> None:
        html = self.render(
            """
nextData.sessions = [];
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        for heading in ("SESSION", "ACTIVITY", "METRIC"):
            self.assertIn(f">{heading}</th>", html)
        self.assertEqual(1, html.count("<tbody></tbody>"))
        self.assertNotIn("data-next-session-block", html)
        self.assertNotIn("next-session-group", html)

    def test_rows_render_measured_metrics_registry_labels_and_activity(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        gate = self.session_row(html, "gate-z")
        work = self.session_row(html, "work-z")
        idle = self.session_row(html, "idle-new")

        self.assertIn("next-session-row--blocked", gate)
        self.assertNotIn("next-live", gate)
        self.assertIn("10m wait", gate)
        self.assertIn("repo/main · Claude Code", gate)
        self.assertIn("open question · AskUserQuestion", gate)
        self.assertIn("next-session-row--working", work)
        self.assertIn("next-live", work)
        self.assertIn('aria-label="working">●</span>', work)
        self.assertIn("42 /m", work)
        self.assertIn("running 1 subagent", work)
        self.assertNotIn("next-session-row--blocked", idle)
        self.assertNotIn("next-session-row--working", idle)
        self.assertNotIn("next-live", idle)
        self.assertIn("9m idle", idle)

    def test_metric_column_has_a_neutral_header_and_state_specific_units(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertEqual(1, html.count('<th scope="col">METRIC</th>'))
        self.assertNotIn('<th scope="col">RATE</th>', html)
        self.assertIn("10m wait", html)
        self.assertIn("42 /m", html)
        self.assertIn("9m idle", html)

    def test_multi_hour_wait_and_idle_metrics_use_compact_durations(self) -> None:
        html = self.render(
            """
nextData.sessions.find(row => row.sid === "gate-z").blocked_since = 2260;
nextData.sessions.find(row => row.sid === "idle-new").last_activity = 2260;
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("2h 9m wait", self.session_row(html, "gate-z"))
        self.assertIn("2h 9m idle", self.session_row(html, "idle-new"))
        self.assertNotIn("129m", html)

    def test_an_unknown_rate_is_blank_while_a_measured_zero_is_shown(self) -> None:
        html = self.render(
            """
nextData.sessions.find(row => row.sid === "work-a").rate_per_min = null;
nextData.sessions.find(row => row.sid === "work-z").rate_per_min = 0;
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        unknown = self.session_row(html, "work-a")
        measured_zero = self.session_row(html, "work-z")
        self.assertNotIn("/m", unknown)
        self.assertIn("0 /m", measured_zero)

    def test_a_working_row_without_the_active_flag_stays_static(self) -> None:
        html = self.render(
            """
const session = nextData.sessions.find(row => row.sid === "work-z");
session.active = false;
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        work = self.session_row(html, "work-z")

        self.assertIn("next-session-row--working", work)
        self.assertNotIn("next-live", work)
        self.assertNotIn('aria-label="working">●</span>', work)

    def test_an_absent_state_detail_and_gate_stamp_render_no_placeholder(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        row = self.session_row(html, "gate-a")

        self.assertNotIn("undefined", row)
        self.assertNotIn("null", row)
        self.assertNotIn(" wait", row)

    def test_idle_age_and_done_use_the_payload_clock(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        newest = self.session_row(html, "idle-new")
        middle = self.session_row(html, "idle-mid")

        self.assertIn("9m idle", newest)
        self.assertNotIn(">done<", newest)
        self.assertIn("20m idle", middle)
        self.assertIn(">done<", middle)

    def test_every_row_on_a_shared_project_label_gets_the_collision_caveat(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        gate = self.session_row(html, "gate-z")
        work = self.session_row(html, "work-z")

        for row in (gate, work):
            self.assertIn("2 sessions share this label", row)
            self.assertIn("Same label is not proof of the same directory", row)
            self.assertIn("sibling worktrees read alike", row)

    def test_all_ten_harnesses_use_the_payload_registry_label(self) -> None:
        html = self._run_page_js(
            "await __settle();\nnextSelectSessions();\n"
            "console.log(JSON.stringify(__els.app.innerHTML));",
            """
location.search = "?next=true";
__els.app = {innerHTML: ""};
const registry = [
  ["claude", "Claude"], ["codex", "Codex"], ["pi", "Pi"],
  ["gemini", "Gemini"], ["antigravity", "Antigravity"],
  ["copilot", "Copilot"], ["opencode", "OpenCode"], ["cursor", "Cursor"],
  ["goose", "Goose"], ["droid", "Droid"]
];
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000, window_hours: 24,
  summary: {working: 10, needs_input: 0},
  harnesses: registry.map(([key, label]) => ({key, label})),
  sessions: registry.map(([harness], index) => ({
    sid: `sid-${index}`, harness, project: `project/${index}`, state: "working",
    active: true, title: `session ${index}`, last_activity: 9990,
    rate_per_min: index, subagents: []
  }))
})});
""",
        )
        assert isinstance(html, str)

        for label in (
            "Claude",
            "Codex",
            "Pi",
            "Gemini",
            "Antigravity",
            "Copilot",
            "OpenCode",
            "Cursor",
            "Goose",
            "Droid",
        ):
            self.assertIn(f" · {label}</span>", html)

    def test_a_row_click_reaches_the_session_route(self) -> None:
        out = self.render(
            """
const html = __els.app.innerHTML;
const match = html.match(/data-next-session="gate-z"[^>]*data-next-route="([^"]+)"/);
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

        self.assertIn('data-next-route="session:repo%2Fmain:gate-z"', out["html"])
        self.assertEqual(
            {"view": "session", "project": "repo/main", "session": "gate-z"},
            out["route"],
        )
        self.assertEqual("#n=session:repo%2Fmain:gate-z", out["hash"])


if __name__ == "__main__":
    unittest.main()
