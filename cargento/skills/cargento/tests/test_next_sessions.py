from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NEXT_STYLES, NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextSessionsBehaviorTest(NextPageJsHarness):
    FIXTURE = """
location.search = "";
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


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextSessionsSessionEndTest(NextPageJsHarness):
    """DRC-4036: the operations row must separate over from waiting for you."""

    def view(self, session: str, extra: str = "") -> str:
        rendered = self._run_page_js(
            "\n".join(
                (
                    (
                        "nextData = {generated: 10000, window_hours: 24, harnesses: ["
                        '{key: "claude", label: "Claude Code", reports_needs_input: true}],'
                        f"{extra} sessions: [{session}]}};"
                    ),
                    "console.log(JSON.stringify(nextSessionsView()));",
                )
            )
        )
        assert isinstance(rendered, str)
        return rendered

    ENDED = (
        '{sid: "e1", harness: "claude", project: "a/b", state: "idle", active: false,'
        ' title: "Ended run", last_activity: 9000, finished_at: 9350, ended_at: 9400,'
        " tasks: [], subagents: []}"
    )
    QUIET = (
        '{sid: "q1", harness: "claude", project: "a/b", state: "idle", active: false,'
        ' title: "Quiet run", last_activity: 9000, finished_at: 9350,'
        " tasks: [], subagents: []}"
    )
    # The shape that actually ships. `session_ended` pops the whole overlay
    # ledger, so it publishes no `state` of its own and the collector's word
    # stands; the capture puts the end 0.565–5.581s after the last transcript
    # write, well inside `working_threshold_sec` (90). So `working` beside a
    # stamped end is the row for roughly the minute and a half after every
    # ordinary end — the common case, not an edge one.
    WORKING_ENDED = (
        '{sid: "w1", harness: "claude", project: "a/b", state: "working", active: false,'
        ' title: "Just ended", state_detail: "Editing files…",'
        " last_activity: 9990, ended_at: 9400, tasks: [], subagents: []}"
    )

    def group(self, html: str, kind: str) -> str:
        """The one operations group's markup, so membership is asserted not implied."""
        opened = html.split(f'data-next-operation-group="{kind}"', 1)
        self.assertEqual(2, len(opened), f"no {kind} group rendered")
        return opened[1].split("</section>", 1)[0]

    def test_an_ended_row_says_it_ended_and_how_long_ago(self) -> None:
        html = self.view(self.ENDED)

        self.assertIn("NOW · ENDED", html)
        self.assertIn("Session reported its own end", html)
        self.assertIn("ended 10m ago", html)

    def test_a_row_with_no_observed_end_keeps_the_em_dash_it_had(self) -> None:
        # The history row's "—" is what an unread session has always shown, and
        # it must stay that: an absent end is not evidence the session is alive,
        # so the page may say nothing rather than say "still running".
        html = self.view(self.QUIET)

        self.assertNotIn("NOW · ENDED", html)
        self.assertNotIn("Session reported its own end", html)

    def test_an_ended_session_leaves_active_now_even_while_the_scan_says_working(self) -> None:
        html = self.view(self.WORKING_ENDED)

        self.assertNotIn("w1", self.group(html, "active"))
        self.assertIn("w1", self.group(html, "history"))

    def test_an_ended_session_never_renders_the_working_state_word(self) -> None:
        # The caveat below teaches that an unmarked row reported no end, so a
        # row that DID report one may not sit unmarked reading NOW · WORKING.
        html = self.view(self.WORKING_ENDED)

        self.assertNotIn("NOW · WORKING", html)
        self.assertIn("NOW · ENDED", html)
        self.assertIn("ended 10m ago", html)

    def test_the_fleet_no_longer_counts_an_ended_session_as_active_now(self) -> None:
        html = self.view(self.WORKING_ENDED)
        strip = html.split('data-next-fleet-fact="active"', 1)[1].split("</section>", 1)[0]

        self.assertIn("<strong>0</strong>", strip)

    def test_an_outstanding_request_keeps_an_ended_row_active_and_still_marks_it(self) -> None:
        # The one path that reaches the NOW cell with an end stamped. An exact
        # request is a published fact with its own lifecycle rather than a
        # reading of recency, so it still holds the row in Active now — but the
        # end still owns the NOW cell, because the two answer different
        # questions and only one of them was observed rather than inferred.
        html = self.view(
            self.WORKING_ENDED,
            ' ask: true, asks: [{session_id: "w1", harness: "claude", question: "Which branch?"}],',
        )

        self.assertIn("w1", self.group(html, "active"))
        self.assertIn("NOW · ENDED", html)
        self.assertNotIn("NOW · WORKING", html)

    def test_a_working_session_with_no_end_still_leads_active_now(self) -> None:
        # The end is what moves the row, and only the end: an ordinary working
        # session must keep the lane whose whole job is "what is still running".
        working = self.WORKING_ENDED.replace(" ended_at: 9400,", "").replace(
            'sid: "w1"', 'sid: "w2"'
        )
        html = self.view(working)

        self.assertIn("w2", self.group(html, "active"))
        self.assertIn("NOW · WORKING", html)
        self.assertNotIn("NOW · ENDED", html)

    def test_the_recent_history_caveat_is_qualified_where_an_end_was_observed(self) -> None:
        # The old sentence was unqualified — "Recently observed is not proof the
        # harness process is still open or closed" — which was true before any
        # row could report its own end, and understates the rows that now can.
        html = self.view(self.ENDED)

        self.assertIn("Recently observed is not proof", html)
        self.assertIn("ENDED reported their own end", html)


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextSessionsUnreadSourceTest(NextPageJsHarness):
    """DRC-4447: a store the collector read and matched nothing in must say so.

    Both arms, because the issue was filed about one of them. A row whose store
    would not read renders as a session at its prompt when its mtime is stale
    and as one *generating* when its mtime is fresh, and the second is the worse
    of the two: it is a positive claim about work nobody observed.
    """

    HARNESSES = (
        "nextData = {generated: 10000, window_hours: 24, harnesses: ["
        '{key: "antigravity", label: "Antigravity", reports_needs_input: false},'
        '{key: "copilot", label: "Copilot", reports_needs_input: true}],'
    )

    def view(self, sessions: str) -> str:
        rendered = self._run_page_js(
            f"{self.HARNESSES} sessions: [{sessions}]}};\n"
            "console.log(JSON.stringify(nextSessionsView()));"
        )
        assert isinstance(rendered, str)
        return rendered

    def detail(self, session: str, project: str, harness: str, sid: str) -> str:
        rendered = self._run_page_js(
            f"{self.HARNESSES} sessions: [{session}]}};\n"
            "console.log(JSON.stringify(nextSessionView("
            f'"{project}", "{harness}", "{sid}")));'
        )
        assert isinstance(rendered, str)
        return rendered

    STALE = (
        '{sid: "agy-stale", harness: "antigravity", project: "trio/app", state: "idle",'
        ' active: true, title: null, state_detail: "awaiting your message",'
        " last_activity: 6400, rate_per_min: 0, turn: null, tasks: [], subagents: [],"
        ' source_gaps: ["message history", "token accounting"]}'
    )
    FRESH = (
        '{sid: "agy-fresh", harness: "antigravity", project: "trio/app", state: "working",'
        ' active: true, title: null, state_detail: "generating…",'
        " last_activity: 9990, rate_per_min: 0, turn: null, tasks: [], subagents: [],"
        ' source_gaps: ["message history", "token accounting"]}'
    )
    QUIET = (
        '{sid: "agy-quiet", harness: "antigravity", project: "trio/app", state: "idle",'
        ' active: true, title: null, state_detail: "awaiting your message",'
        " last_activity: 6400, rate_per_min: 0, turn: null, tasks: [], subagents: [],"
        " source_gaps: []}"
    )
    COPILOT = (
        '{sid: "cop-1", harness: "copilot", project: "trio/other", state: "idle",'
        ' active: true, title: "Refactor the parser", state_detail: "awaiting your message",'
        " last_activity: 6400, consumption: null, model: null, tasks: [], subagents: [],"
        ' source_gaps: ["token accounting"]}'
    )

    def row(self, html: str, sid: str) -> str:
        match = re.search(
            rf'<article[^>]*data-next-session="{re.escape(sid)}"[\s\S]*?</article>', html
        )
        if match is None:
            raise AssertionError(f"no operation row for {sid!r} in {html}")
        return match.group(0)

    def test_a_stale_row_whose_store_told_us_nothing_names_the_missing_readings(self) -> None:
        row = self.row(self.view(self.STALE), "agy-stale")

        self.assertIn("Source not fully read: message history, token accounting", row)

    def test_the_same_store_read_reads_as_working_and_still_says_it(self) -> None:
        # The arm the issue's blank-row framing left out. "generating…" is a
        # claim, and it must not stand beside an unqualified silence.
        row = self.row(self.view(self.FRESH), "agy-fresh")

        self.assertIn("generating…", row)
        self.assertIn("Source not fully read: message history, token accounting", row)

    def test_a_session_that_has_genuinely_done_nothing_says_nothing_extra(self) -> None:
        # The whole point of the disclosure is that it is not on every quiet row.
        # A quiet row's history NOW cell is the em dash it has always been, and
        # the disclosed row above differs from this one by the sentence alone.
        row = self.row(self.view(self.QUIET), "agy-quiet")

        self.assertIn("<small>NOW</small><strong>—</strong>", row)
        self.assertNotIn("Source not fully read", row)

    def test_a_second_harnesss_unread_store_uses_the_same_sentence(self) -> None:
        # Harness-agnostic by construction: five collectors report through one
        # published field, so the page has one sentence rather than five.
        row = self.row(self.view(self.COPILOT), "cop-1")

        self.assertIn("Source not fully read: token accounting", row)
        self.assertIn("Refactor the parser", row)

    def test_the_disclosure_explains_itself_without_leaving_the_row(self) -> None:
        row = self.row(self.view(self.STALE), "agy-stale")

        self.assertIn("Cargento opened this session&#39;s store", row)
        self.assertIn("missing here rather than empty", row)

    def test_the_session_page_repeats_what_the_row_disclosed(self) -> None:
        # A reader who clicks through must not land on a page that has quietly
        # dropped the qualifier and gone back to asserting the state alone.
        html = self.detail(self.STALE, "trio/app", "antigravity", "agy-stale")

        self.assertIn("Antigravity · awaiting your message", html)
        self.assertIn("source not fully read: message history, token accounting", html)

    def test_the_session_page_of_a_quiet_row_adds_nothing(self) -> None:
        html = self.detail(self.QUIET, "trio/app", "antigravity", "agy-quiet")

        self.assertIn("Antigravity · awaiting your message", html)
        self.assertNotIn("not fully read", html)

    def test_a_row_carrying_junk_where_the_gap_names_go_renders_none_of_it(self) -> None:
        # `source_gaps` is a published field, and the page treats every payload
        # value as untrusted: a non-array, and a non-string member, are both
        # nothing rather than a rendered surprise.
        junk = self.QUIET.replace("source_gaps: []", 'source_gaps: "message history"').replace(
            'sid: "agy-quiet"', 'sid: "agy-junk"'
        )
        member = self.QUIET.replace("source_gaps: []", 'source_gaps: [{}, 7, null, "  "]').replace(
            'sid: "agy-quiet"', 'sid: "agy-member"'
        )

        self.assertNotIn("not fully read", self.row(self.view(junk), "agy-junk"))
        self.assertNotIn("not fully read", self.row(self.view(member), "agy-member"))


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextSessionsScanOnlyTest(NextPageJsHarness):
    """DRC-4473: an idle row that could never have carried a stop must say so.

    Measured on the board at 5bca94b before this shipped: a Goose idle row and a
    Claude idle row with no stop observed rendered the same five cells, character
    for character, down to the three em dashes. For the Claude row the absent
    stop means "did not finish"; for the Goose row it means "cannot be seen from
    here", and the reader had nothing to separate them by.
    """

    HARNESSES = (
        "nextData = {generated: 10000, window_hours: 24, harnesses: ["
        '{key: "claude", label: "Claude Code", reports_needs_input: true},'
        '{key: "goose", label: "Goose", reports_needs_input: false}],'
    )

    SCANNED = (
        '{sid: "goose-1", harness: "goose", project: "solo/app", state: "idle",'
        ' active: false, title: "Rebuild the index", state_detail: null,'
        " last_activity: 9600, started_at: 9000, tasks: [], subagents: [],"
        ' source_gaps: [], acquisition: "scan-only"}'
    )
    EVENTED = (
        '{sid: "claude-1", harness: "claude", project: "solo/app", state: "idle",'
        ' active: false, title: "Rebuild the index", state_detail: null,'
        " last_activity: 9600, started_at: 9000, tasks: [], subagents: [],"
        " source_gaps: [], acquisition: null}"
    )
    STOPPED = SCANNED.replace('sid: "goose-1"', 'sid: "goose-stopped"').replace(
        "last_activity: 9600", "last_activity: 9600, finished_at: 9600"
    )
    WORKING = SCANNED.replace('sid: "goose-1"', 'sid: "goose-working"').replace(
        'state: "idle", active: false', 'state: "working", active: true'
    )

    def view(self, sessions: str) -> str:
        rendered = self._run_page_js(
            f"{self.HARNESSES} sessions: [{sessions}]}};\n"
            "console.log(JSON.stringify(nextSessionsView()));"
        )
        assert isinstance(rendered, str)
        return rendered

    def detail(self, session: str, project: str, harness: str, sid: str) -> str:
        rendered = self._run_page_js(
            f"{self.HARNESSES} sessions: [{session}]}};\n"
            "console.log(JSON.stringify(nextSessionView("
            f'"{project}", "{harness}", "{sid}")));'
        )
        assert isinstance(rendered, str)
        return rendered

    def row(self, html: str, sid: str) -> str:
        match = re.search(
            rf'<article[^>]*data-next-session="{re.escape(sid)}"[\s\S]*?</article>', html
        )
        if match is None:
            raise AssertionError(f"no operation row for {sid!r} in {html}")
        return match.group(0)

    def test_a_row_no_event_can_reach_says_no_turn_end_can_be_observed_on_it(self) -> None:
        row = self.row(self.view(self.SCANNED), "goose-1")

        self.assertIn("Read by scanning: no turn end can be observed here", row)

    def test_an_event_backed_idle_row_keeps_the_em_dash_and_adds_nothing(self) -> None:
        # The other half of the distinction. Without this the sentence could be
        # on every idle row, which is Idle restated rather than qualified.
        row = self.row(self.view(self.EVENTED), "claude-1")

        self.assertIn("<small>NOW</small><strong>—</strong>", row)
        self.assertNotIn("Read by scanning", row)

    def test_the_sentence_is_the_only_thing_the_two_idle_rows_differ_by(self) -> None:
        # The measured before-state, pinned so it cannot come back. Both rows are
        # idle with no stop published, so all three of their reading cells are the
        # em dash on either side of the fix, and the note is the whole difference.
        cells = r'<span class="next-operation-fact"[\s\S]*$'
        scanned = re.search(cells, self.row(self.view(self.SCANNED), "goose-1"))
        evented = re.search(cells, self.row(self.view(self.EVENTED), "claude-1"))
        assert scanned is not None
        assert evented is not None

        self.assertEqual(scanned.group(0), evented.group(0))
        self.assertEqual(3, scanned.group(0).count("<strong>—</strong>"))

    def test_the_sentence_explains_itself_without_leaving_the_row(self) -> None:
        # Not a `<details>`, on #302's ground: it qualifies a claim already on
        # screen beside it, and one a reader can leave shut cannot do that.
        row = self.row(self.view(self.SCANNED), "goose-1")

        self.assertNotIn("<details", row)
        self.assertIn("no event from its harness can reach it", row)

    def test_a_working_row_that_no_event_can_reach_says_it_too(self) -> None:
        # The field is a property of the row's source, not of its state, and the
        # working arm is where the reader most needs it: this one will stop, and
        # nothing will tell them that it did.
        row = self.row(self.view(self.WORKING), "goose-working")

        self.assertIn("Read by scanning: no turn end can be observed here", row)

    def test_a_row_that_somehow_published_a_stop_drops_the_sentence(self) -> None:
        # Unreachable from this server — `events.parse` refuses the six
        # harnesses' envelopes outright — so this is the untrusted-payload arm.
        # The sentence says a stop could not be observed, and a published stamp
        # beside it would make that false on the reader's screen.
        row = self.row(self.view(self.STOPPED), "goose-stopped")

        self.assertNotIn("Read by scanning", row)

    def test_the_session_page_repeats_what_the_row_disclosed(self) -> None:
        html = self.detail(self.SCANNED, "solo/app", "goose", "goose-1")

        self.assertIn("read by scanning: no turn end can be observed here", html)

    def test_the_session_page_of_an_event_backed_row_adds_nothing(self) -> None:
        html = self.detail(self.EVENTED, "solo/app", "claude", "claude-1")

        self.assertNotIn("read by scanning", html)

    def test_a_row_carrying_junk_where_the_provenance_goes_renders_none_of_it(self) -> None:
        # One exact string, and everything else is nothing: the value is
        # published and therefore untrusted, and a truthy-check here would print
        # the sentence for `acquisition: "event"` as readily as for a hostile one.
        for value in (
            '"event"',
            '"SCAN-ONLY"',
            '" scan-only "',
            "true",
            "7",
            "{}",
            '["scan-only"]',
        ):
            with self.subTest(acquisition=value):
                junk = self.SCANNED.replace(
                    'acquisition: "scan-only"', f"acquisition: {value}"
                ).replace('sid: "goose-1"', 'sid: "goose-junk"')

                self.assertNotIn("Read by scanning", self.row(self.view(junk), "goose-junk"))
