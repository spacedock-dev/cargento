from __future__ import annotations

import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextChromeBehaviorTest(NextPageJsHarness):
    def test_route_survives_load_and_browser_history(self) -> None:
        out = self._run_page_js(
            """
const initial = {...nextRoute};
location.hash = "#n=project:recce%20cloud";
__fire("window:hashchange", {});
const project = {...nextRoute};
location.hash = "#n=overview";
__fire("window:hashchange", {});
console.log(JSON.stringify({initial, project, overview: nextRoute, html: __els.app.innerHTML}));
            """,
            'location.hash = "#n=session:recce%20cloud:019a%2Fabc";\n'
            '__els.app = {innerHTML: ""};\n',
        )

        self.assertEqual(
            {"view": "session", "project": "recce cloud", "session": "019a/abc"},
            out["initial"],
        )
        self.assertEqual(
            {"view": "project", "project": "recce cloud", "session": None},
            out["project"],
        )
        self.assertEqual(
            {"view": "overview", "project": None, "session": None},
            out["overview"],
        )
        self.assertIn("Cargento | overview", out["html"])

    def test_breadcrumb_segments_are_clickable_and_escape_walks_up(self) -> None:
        out = self._run_page_js(
            """
const sessionHtml = __els.app.innerHTML;
__fire("click", {
  target: {closest(){ return {dataset: {nextRoute: "project:recce"}}; }},
  preventDefault(){}
});
const clicked = {...nextRoute};
navigateNext({view: "session", project: "recce", session: "019a"});
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
const project = {...nextRoute};
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
const overview = {...nextRoute};
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
console.log(JSON.stringify({sessionHtml, clicked, project, overview, stayed: nextRoute}));
""",
            'location.hash = "#n=session:recce:019a";\n__els.app = {innerHTML: ""};\n',
        )

        self.assertIn("Cargento | overview", out["sessionHtml"])
        self.assertIn("recce", out["sessionHtml"])
        self.assertIn("019a", out["sessionHtml"])
        self.assertIn('data-next-route="overview"', out["sessionHtml"])
        self.assertIn('data-next-route="project:recce"', out["sessionHtml"])
        self.assertEqual(
            {"view": "project", "project": "recce", "session": None},
            out["clicked"],
        )
        self.assertEqual(out["clicked"], out["project"])
        self.assertEqual(
            {"view": "overview", "project": None, "session": None},
            out["overview"],
        )
        self.assertEqual(out["overview"], out["stayed"])

    def test_the_next_fragment_never_contains_the_old_session_token(self) -> None:
        out = self._run_page_js(
            """
const routes = [
  {view: "overview", project: null, session: null},
  {view: "project", project: "recce:cloud", session: null},
  {view: "session", project: "recce:cloud", session: "session=one/two"}
];
const fragments = routes.map(nextFragmentForRoute);
location.hash = "#n=session=old-bundle-token";
__fire("window:hashchange", {});
console.log(JSON.stringify({fragments, repaired: location.hash}));
"""
        )

        self.assertTrue(all("session=" not in fragment for fragment in out["fragments"]))
        self.assertEqual("#n=overview", out["fragments"][0])
        self.assertEqual("#n=project:recce%3Acloud", out["fragments"][1])
        self.assertEqual("#n=overview", out["repaired"])

    def test_shortcuts_select_sessions_and_leave_for_dashboard_mode(self) -> None:
        out = self._run_page_js(
            """
__fire("keydown", {key: "s", target: {tagName: "BODY"}, preventDefault(){}});
const sessionsHtml = __els.app.innerHTML;
__fire("keydown", {key: "d", target: {tagName: "BODY"}, preventDefault(){}});
console.log(JSON.stringify({
  sessionsHtml,
  assigned: __assignedLocations,
  search: location.search,
  keydownListeners: (__listeners.keydown || []).length
}));
""",
            'location.search = "?next=true";\n__els.app = {innerHTML: ""};\n',
        )

        self.assertIn('data-next-tab="sessions" aria-selected="true"', out["sessionsHtml"])
        self.assertEqual(["/"], out["assigned"])
        self.assertEqual("?next=true", out["search"])
        self.assertEqual(1, out["keydownListeners"])

    def test_the_running_count_excludes_blocked_sessions(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            """
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  window_hours: 24,
  summary: {working: 1, needs_input: 1, active_sessions: 4},
  sessions: [
    {project: "recce", state: "working", subagents: [{}, {}]},
    {project: "recce", state: "needs_input", subagents: [{}]},
    {project: "cargento", state: "idle", subagents: []},
    {project: "cargento", state: "idle", subagents: []}
  ]
})});
""",
        )

        self.assertIn("● 1 running · 3 subagents", out)
        self.assertIn("1 need you", out)
        self.assertNotIn("4 running", out)
        self.assertIn("2 projects · 4 sessions", out)
        self.assertIn("in this 24h window", out)

    def test_a_payload_with_no_gates_renders_no_pill(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            """
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  window_hours: 6,
  summary: {working: 0, needs_input: 0, active_sessions: 0},
  sessions: []
})});
""",
        )

        self.assertIn("● 0 running · 0 subagents", out)
        self.assertNotIn("need you", out)
        self.assertIn('data-next-tab="projects"', out)
        self.assertIn('data-next-tab="sessions"', out)
        self.assertIn('data-next-body="projects"', out)
        self.assertIn('data-next-body="sessions"', out)
        self.assertEqual(1, out.count("flat session list"))
        self.assertEqual(1, out.count("dashboard mode"))

    def test_poll_forwards_only_the_all_flag(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify({calls: __fetchCalls.map(call => call[0]), periods: __intervalPeriods()}));
""",
            """
location.search = "?next=true&all=1&view=ignored";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  window_hours: 24,
  summary: {working: 0, needs_input: 0},
  sessions: []
})});
""",
        )

        self.assertEqual(["/api/data?all=1"], out["calls"])
        self.assertEqual([5000], out["periods"])

    def test_poll_omits_all_when_the_query_does(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__fetchCalls.map(call => call[0])));
""",
            """
location.search = "?next=true";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  window_hours: 24,
  summary: {working: 0, needs_input: 0},
  sessions: []
})});
""",
        )

        self.assertEqual(["/api/data"], out)

    def test_repeated_refresh_failures_surface_a_stalled_state(self) -> None:
        out = self._run_page_js(
            """
await __settle();
const good = __els.app.innerHTML;
__nextShouldFail = true;
__runInterval(5000);
await __settle();
const once = __els.app.innerHTML;
__runInterval(5000);
await __settle();
console.log(JSON.stringify({good, once, twice: __els.app.innerHTML}));
""",
            """
__els.app = {innerHTML: ""};
let __nextShouldFail = false;
__fetchImpl = async () => {
  if(__nextShouldFail) throw new Error("offline");
  return {ok: true, json: async () => ({
    window_hours: 24,
    summary: {working: 1, needs_input: 0},
    sessions: [{project: "recce", subagents: []}]
  })};
};
""",
        )

        self.assertIn("● 1 running", out["good"])
        self.assertNotIn("Refresh stalled", out["once"])
        self.assertIn("Refresh stalled", out["twice"])
        self.assertIn("● 1 running", out["twice"])
        self.assertIn('data-next-state="stalled"', out["twice"])


if __name__ == "__main__":
    unittest.main()
