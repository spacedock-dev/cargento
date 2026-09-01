from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NEXT_STYLES, NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextSessionsBehaviorTest(NextPageJsHarness):
    FIXTURE = """
location.search = "?next=true";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 10000,
  window_hours: 24,
  ask: true,
  summary: {working: 99, needs_input: 99},
  harnesses: [
    {key: "claude", label: "Claude Code", reports_needs_input: true},
    {key: "codex", label: "Codex", reports_needs_input: true},
    {key: "cursor", label: "Cursor", reports_needs_input: true},
    {key: "antigravity", label: "Antigravity", reports_needs_input: false}
  ],
  sessions: [
    {
      sid: "gate-z", harness: "claude", project: "repo/main", state: "needs_input",
      active: true, title: "First gate", state_detail: "open question · AskUserQuestion",
      blocked_since: 9400, last_activity: 9400, tasks: [], subagents: []
    },
    {
      sid: "gate-a", harness: "codex", project: "solo/app", state: "needs_input",
      active: true, title: "Second gate", state_detail: null,
      blocked_since: null, last_activity: 9000, tasks: [], subagents: []
    },
    {
      sid: "work-a", harness: "cursor", project: "work/app", state: "working",
      active: true, title: "Normal work", state_detail: "running Bash", rate_per_min: 12,
      last_activity: 9990, turn: {long: false}, subagents: [],
      tasks: [
        {id: "live", subject: "Review response", status: "in_progress"},
        {id: "next", subject: "Prepare payload", status: "pending"}
      ]
    },
    {
      sid: "work-z", harness: "claude", project: "repo/main", state: "working",
      active: true, title: "Long work", state_detail: "running 1 subagent", rate_per_min: 42,
      last_activity: 9980, turn: {long: true}, subagents: [{}], tasks: []
    },
    {
      sid: "idle-old", harness: "antigravity", project: "idle/old", state: "idle",
      active: false, title: "Old idle", state_detail: null, last_activity: 7000,
      finished_at: 7000, tasks: [], subagents: []
    },
    {
      sid: "idle-new", harness: "codex", project: "idle/new", state: "idle",
      active: false, title: "New idle", state_detail: "awaiting your message",
      last_activity: 9460, finished_at: 9460, tasks: [], subagents: []
    },
    {
      sid: "idle-mid", harness: "cursor", project: "idle/mid", state: "idle",
      active: false, title: "Middle idle", state_detail: null, last_activity: 8800,
      finished_at: 8800, tasks: [], subagents: []
    }
  ],
  asks: [
    {id: "ask-live", session_id: "gate-z", question: "Approve release?", options: ["Yes"]},
    {id: "ask-orphan", session_id: "outside-window", question: "Ignore me", options: ["No"]}
  ]
})});
"""

    def render(self, checks: str = "console.log(JSON.stringify(__els.app.innerHTML));") -> object:
        return self._run_page_js(
            'await __settle();\nnavigateNext({view: "sessions", project: null, session: null});\n'
            + checks,
            self.FIXTURE,
        )

    @staticmethod
    def session_row(html: str, sid: str) -> str:
        match = re.search(
            rf'<(?P<tag>article|a)[^>]*data-next-session="{re.escape(sid)}"[\s\S]*?</(?P=tag)>',
            html,
        )
        if match is None:
            raise AssertionError(f"no operation row for {sid!r} in {html}")
        return match.group(0)

    @staticmethod
    def fact(row: str, name: str) -> str:
        match = re.search(
            rf'<span[^>]*data-next-operation-fact="{re.escape(name)}"[\s\S]*?</span>',
            row,
        )
        if match is None:
            raise AssertionError(f"no {name!r} fact in {row}")
        return match.group(0)

    @staticmethod
    def operation_group(html: str, name: str) -> str:
        match = re.search(
            rf'<section[^>]*data-next-operation-group="{re.escape(name)}"[\s\S]*?</section>',
            html,
        )
        if match is None:
            raise AssertionError(f"no {name!r} operation group in {html}")
        return match.group(0)

    def test_default_surface_leads_with_four_fleet_facts_from_exact_rows(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertIn('<section class="next-operations"', html)
        self.assertIn("<h1>Session operations</h1>", html)
        self.assertIn(
            "Active evidence leads. Every recently observed session remains reachable.", html
        )
        expected = {
            "active": "4",
            "working": "2",
            "requests": "1",
            "reported-blocks": "2",
        }
        for name, value in expected.items():
            with self.subTest(fact=name):
                match = re.search(
                    rf'data-next-fleet-fact="{name}"[^>]*>[\s\S]*?<strong>{value}</strong>',
                    html,
                )
                self.assertIsNotNone(match)
        self.assertIn("6 of 7 sessions report block state", html)
        self.assertNotIn("99", html, "summary aggregates replaced the exact-row population")
        self.assertNotIn("Ignore me", html, "an ask outside the payload entered fleet facts")

    def test_active_now_and_recent_history_use_only_explicit_active_evidence(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        active = self.operation_group(html, "active")
        history = self.operation_group(html, "history")

        self.assertIn("Active now", active)
        self.assertIn("Working, needs-input, or exact request.", active)
        for sid in ("gate-z", "gate-a", "work-a", "work-z"):
            self.assertIn(f'data-next-session="{sid}"', active)
            self.assertNotIn(f'data-next-session="{sid}"', history)
        self.assertIn("Recent history", history)
        self.assertIn(
            "Recently observed is not proof the harness process is still open or closed", history
        )
        for sid in ("idle-new", "idle-mid", "idle-old"):
            self.assertIn(f'data-next-session="{sid}"', history)
            self.assertNotIn(f'data-next-session="{sid}"', active)

    def test_exact_request_state_skew_agrees_in_fleet_row_and_active_group(self) -> None:
        html = self.render(
            """
const skewed = nextData.sessions.find(session => session.sid === "idle-mid");
skewed.spacedock = {role: "first-officer", workflows: []};
nextData.asks.push({
  id: "skew", session_id: "idle-mid", question: "Choose the release lane"
});
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        requests = re.search(
            r'data-next-fleet-fact="requests"[^>]*>[\s\S]*?<strong>(\d+)</strong>', html
        )
        blocks = re.search(
            r'data-next-fleet-fact="reported-blocks"[^>]*>[\s\S]*?<strong>(\d+)</strong>',
            html,
        )
        self.assertEqual("2", requests.group(1) if requests else None)
        self.assertEqual("3", blocks.group(1) if blocks else None)
        self.assertIn('data-next-session="idle-mid"', self.operation_group(html, "active"))
        blocked = self.fact(self.session_row(html, "idle-mid"), "blocked")
        self.assertIn("BLOCKED · CAPTAIN", blocked)
        self.assertIn("Choose the release lane", blocked)

    def test_cross_harness_sid_collision_keeps_routes_and_asks_on_exact_owners(self) -> None:
        out = self.render(
            """
const cursor = nextData.sessions.find(session => session.sid === "idle-mid");
cursor.harness = "cursor";
cursor.spacedock = null;
nextData.sessions.push({
  ...cursor, harness: "antigravity", title: "Shadow AGY",
  spacedock: {role: "first-officer", workflows: []}
});
nextData.asks.push({
  id: "agy-collision", harness: "antigravity", session_id: "idle-mid",
  question: "Choose the release lane"
});
renderNext();
const board = __els.app.innerHTML;
const routes = [...board.matchAll(/<article[^>]*data-next-harness="([^"]+)"[^>]*data-next-session="idle-mid"[^>]*>[\\s\\S]*?data-next-route="([^"]+)"/g)]
  .map(match => [match[1], match[2]]);
const details = {};
for(const [harness, route] of routes){
  navigateNext(nextRouteFromFragment(`#n=${route}`));
  details[harness] = __els.app.innerHTML;
}
console.log(JSON.stringify({board, routes, details}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(
            [
                ["antigravity", "session:idle%2Fmid:antigravity:idle-mid"],
                ["cursor", "session:idle%2Fmid:cursor:idle-mid"],
            ],
            out["routes"],
        )
        self.assertIn("Middle idle", out["details"]["cursor"])
        self.assertNotIn("Choose the release lane", out["details"]["cursor"])
        self.assertIn("Shadow AGY", out["details"]["antigravity"])
        self.assertIn("Choose the release lane", out["details"]["antigravity"])
        self.assertIn("CAPTAIN</h2>", out["details"]["antigravity"])
        self.assertEqual(1, out["board"].count("Choose the release lane"))

    def test_exact_request_itself_covers_block_state_for_an_incapable_harness(self) -> None:
        html = self.render(
            """
nextData.asks.push({
  id: "agy-request", session_id: "idle-old", question: "Choose the AGY lane"
});
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("7 of 7 sessions report block state", html)
        self.assertIn('data-next-session="idle-old"', self.operation_group(html, "active"))
        self.assertIn(
            "Choose the AGY lane", self.fact(self.session_row(html, "idle-old"), "blocked")
        )

    def test_assignment_presence_and_absence_are_visible_in_each_session_identity(self) -> None:
        html = self.render(
            """
nextData.sessions.find(session => session.sid === "work-a").instruction = {
  label: "asked", text: "Audit the fleet", at: 9990
};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("ASSIGNMENT · Audit the fleet", self.session_row(html, "work-a"))
        self.assertNotIn("ASSIGNMENT", self.session_row(html, "idle-old"))

    def test_one_row_per_exact_session_survives_exception_sorting(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertEqual(7, html.count("data-next-session="))
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

    def test_each_row_exposes_copyable_exact_identity_and_four_command_facts(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        for sid in ("gate-z", "gate-a", "work-a", "work-z", "idle-old", "idle-new", "idle-mid"):
            with self.subTest(sid=sid):
                row = self.session_row(html, sid)
                self.assertIn(f'aria-label="Copy session ID {sid}"', row)
                self.assertIn(f'title="{sid}"', row)
                self.assertNotIn(f'<span class="next-operation-sid">{sid}</span>', row)
                for fact in ("where", "now", "next", "blocked"):
                    self.fact(row, fact)

    def test_where_calls_the_project_value_a_label_and_refuses_exact_location(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        where = self.fact(self.session_row(html, "work-a"), "where")

        self.assertIn("PROJECT LABEL", where)
        self.assertIn("work/app", where)
        self.assertIn("Exact location not published", where)
        self.assertNotIn("directory", where.lower())
        self.assertNotIn("branch", where.lower())

    def test_now_uses_in_progress_work_and_next_uses_only_a_pending_step(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        row = self.session_row(html, "work-a")
        now = self.fact(row, "now")
        next_fact = self.fact(row, "next")

        self.assertIn("Review response", now)
        self.assertNotIn("Prepare payload", now)
        self.assertIn("Prepare payload", next_fact)
        self.assertNotIn("Review response", next_fact)

    def test_missing_now_and_next_are_explicit_not_empty_or_inferred(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        row = self.session_row(html, "gate-a")

        self.assertIn("Activity not published", self.fact(row, "now"))
        self.assertIn("No pending step published", self.fact(row, "next"))
        for forbidden in ("done", "finished", "died"):
            self.assertNotIn(forbidden, row.lower())

    def test_blocked_fact_separates_exact_request_no_report_and_unknown(self) -> None:
        html = self.render(
            """
const agy = nextData.sessions.find(session => session.sid === "idle-old");
agy.state = "working";
agy.active = true;
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        reported = self.fact(self.session_row(html, "gate-z"), "blocked")
        no_report = self.fact(self.session_row(html, "work-a"), "blocked")
        unknown = self.fact(self.session_row(html, "idle-old"), "blocked")

        self.assertIn("Reported", reported)
        self.assertIn("Approve release?", reported)
        self.assertIn("No reported block", no_report)
        self.assertIn("Unknown", unknown)
        self.assertIn("Harness does not report blocks", unknown)
        self.assertNotIn("No reported block", unknown)

    def test_shared_project_labels_warn_without_merging_rows(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        gate = self.session_row(html, "gate-z")
        work = self.session_row(html, "work-z")

        for row in (gate, work):
            self.assertIn("2 sessions share this label", row)
            self.assertIn("Same label is not proof of the same directory", row)
            self.assertIn("sibling worktrees read alike", row)
        self.assertEqual(2, html.count("2 sessions share this label"))

    def test_rows_use_a_native_route_link_sibling_to_the_copy_button(self) -> None:
        html = self.render()
        assert isinstance(html, str)
        row = self.session_row(html, "gate-z")

        self.assertIn('data-next-harness="claude"', row)
        route = (
            '<a class="next-operation-route" href="#n=session:repo%2Fmain:claude:gate-z" '
            'data-next-route="session:repo%2Fmain:claude:gate-z" '
            'aria-label="Open session First gate"><strong>First gate</strong></a>'
        )
        self.assertIn(route, row)
        self.assertLess(row.index(route), row.index('data-next-copy-session="gate-z"'))
        self.assertNotIn('role="link"', row)

    def test_native_route_link_covers_the_row_without_covering_copy_id(self) -> None:
        self.assertIn(
            '.next-operation-route::after{content:"";position:absolute;inset:0}',
            NEXT_STYLES,
        )
        self.assertIn(
            ".next-session-copy{position:relative;z-index:1;",
            NEXT_STYLES,
        )

    def test_history_keeps_identity_and_scope_but_not_empty_operational_copy(self) -> None:
        html = self.render(
            """
nextData.sessions.find(session => session.sid === "idle-mid").instruction = {
  label: "asked", text: "Historical assignment", at: 9900
};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        row = self.session_row(html, "idle-mid")

        self.assertIn('data-next-operation-history="true"', row)
        self.assertIn("Middle idle", row)
        self.assertIn("idle/mid", row)
        self.assertNotIn("Historical assignment", row)
        self.assertNotIn("next-operation-assignment", row)
        for fact in ("now", "next", "blocked"):
            fact_html = self.fact(row, fact)
            self.assertIn("<strong>—</strong>", fact_html)
            self.assertNotIn("Not published", fact_html)
            self.assertNotIn("Unknown", fact_html)

    def test_zero_session_inventory_keeps_the_board_and_bounded_empty_sentence(self) -> None:
        html = self.render(
            """
nextData.sessions = [];
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn('<section class="next-operations"', html)
        self.assertIn("<h1>Session operations</h1>", html)
        self.assertIn("No exact session has active evidence right now.", html)
        self.assertIn("No recent-history rows in this 24h payload.", html)
        self.assertIn('<a href="#n=sessions" aria-current="page">Sessions</a>', html)
        self.assertNotIn("data-next-session=", html)

    def test_board_css_has_wide_scan_columns_and_narrow_stacks_without_overflow(self) -> None:
        self.assertIn(
            "#app .next-operation-row{display:grid;grid-template-columns:",
            NEXT_STYLES,
        )
        self.assertIn("@media(max-width:980px)", NEXT_STYLES)
        self.assertIn(
            "#app .next-operation-row{grid-template-columns:repeat(2,minmax(0,1fr))}",
            NEXT_STYLES,
        )
        self.assertIn("@media(max-width:620px)", NEXT_STYLES)
        self.assertIn("#app .next-operation-row{grid-template-columns:minmax(0,1fr)", NEXT_STYLES)
        self.assertIn("@media(max-width:360px)", NEXT_STYLES)
        self.assertIn("#app{padding:18px 8px 40px}", NEXT_STYLES)
        self.assertIn("border:1px solid var(--line2)", NEXT_STYLES)
        self.assertIn("overflow-wrap:anywhere", NEXT_STYLES)

    def test_320_fleet_keeps_the_four_facts_in_two_columns(self) -> None:
        self.assertIn(
            ".next-operations-fleet{grid-template-columns:repeat(2,minmax(0,1fr))}",
            NEXT_STYLES,
        )
        self.assertNotIn(
            ".next-operations-fleet{grid-template-columns:minmax(0,1fr)}",
            NEXT_STYLES,
        )
        self.assertIn(
            ".next-operations-fleet>section{display:grid;"
            "grid-template-columns:minmax(0,1fr) auto;gap:3px 8px;"
            "align-items:baseline;padding:6px 8px}",
            NEXT_STYLES,
        )

    def test_320_active_card_keeps_command_facts_in_two_columns(self) -> None:
        self.assertIn("@media(max-width:360px)", NEXT_STYLES)
        self.assertIn(
            "#app .next-operation-row{grid-template-columns:repeat(2,minmax(0,1fr))}",
            NEXT_STYLES,
        )
        self.assertIn(
            ".next-operation-fact{display:block;padding:6px 10px;",
            NEXT_STYLES,
        )
        self.assertIn(
            '.next-operation-row[data-next-operation-history="true"] '
            '.next-operation-fact[data-next-operation-fact="where"]{grid-column:1/-1}',
            NEXT_STYLES,
        )

    def test_desktop_uses_shared_headers_and_mobile_keeps_only_card_labels(self) -> None:
        self.assertIn(
            ".next-operation-identity>.next-operation-local-label,"
            ".next-operation-fact>small{display:none}",
            NEXT_STYLES,
        )
        self.assertIn(
            ".next-operation-identity>.next-operation-local-label,"
            ".next-operation-fact>small{display:block}",
            NEXT_STYLES,
        )
        self.assertIn(
            '.next-operation-row[data-next-operation-history="true"] '
            '.next-operation-fact[data-next-operation-fact="now"]{display:none}',
            NEXT_STYLES,
        )

    def test_detail_current_work_does_not_share_the_old_activity_rail_selector(self) -> None:
        self.assertIn(".next-session-current>strong", NEXT_STYLES)
        self.assertNotIn(".next-session-activity>strong", NEXT_STYLES)


if __name__ == "__main__":
    unittest.main()
