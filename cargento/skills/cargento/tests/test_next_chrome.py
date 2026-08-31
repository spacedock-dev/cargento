from __future__ import annotations

import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextChromeBehaviorTest(NextPageJsHarness):
    def test_attention_is_default_and_old_overview_normalizes_to_it(self) -> None:
        out = self._run_page_js(
            """
const fragments = ["", "#n=overview", "#n=unknown"];
const routes = fragments.map(nextRouteFromFragment);
const repaired = routes.map(nextFragmentForRoute);
console.log(JSON.stringify({routes, repaired}));
""",
            '__els.app = {innerHTML: ""};\n',
        )
        assert isinstance(out, dict)

        for route, repaired in zip(out["routes"], out["repaired"], strict=True):
            self.assertEqual("attention", route["view"])
            self.assertEqual("#n=attention", repaired)

    def test_primary_routes_are_native_links_with_current_page(self) -> None:
        out = self._run_page_js(
            """
nextData = {summary: {working: 0, needs_input: 0}, sessions: [], asks: []};
const views = ["attention", "projects", "sessions"];
const rendered = views.map(view => {
  navigateNext({view, project: null, session: null});
  return {view, title: document.title, html: __els.app.innerHTML};
});
console.log(JSON.stringify(rendered));
""",
            '__els.app = {innerHTML: ""};\n',
        )
        assert isinstance(out, list)

        for rendered, title in zip(
            out,
            ["Cargento — Attention", "Cargento — Projects", "Cargento — Sessions"],
            strict=True,
        ):
            html = rendered["html"]
            self.assertEqual(title, rendered["title"])
            self.assertIn('<nav aria-label="Primary"', html)
            self.assertIn('href="#n=attention"', html)
            self.assertIn('href="#n=projects"', html)
            self.assertIn('href="#n=sessions"', html)
            self.assertEqual(3, html.count('<a href="#n='))
            self.assertEqual(1, html.count('aria-current="page"'))
            self.assertEqual(1, html.count("<h1>"))
            self.assertLess(html.index('href="#n=attention"'), html.index('href="#n=projects"'))
            self.assertLess(html.index('href="#n=projects"'), html.index('href="#n=sessions"'))

    def test_route_survives_load_and_browser_history(self) -> None:
        out = self._run_page_js(
            """
const initial = {...nextRoute};
location.hash = "#n=project:recce%20cloud";
__fire("window:hashchange", {});
const project = {...nextRoute};
location.hash = "#n=overview";
__fire("window:hashchange", {});
console.log(JSON.stringify({initial, project, attention: nextRoute, html: __els.app.innerHTML}));
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
            {"view": "attention", "project": None, "session": None},
            out["attention"],
        )
        self.assertIn("<h1>Attention</h1>", out["html"])

    def test_breadcrumb_segments_are_clickable_and_escape_walks_up(self) -> None:
        out = self._run_page_js(
            """
const sessionHtml = __els.app.innerHTML;
navigateNext({view: "session", project: "recce", session: "019a"});
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
const project = {...nextRoute};
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
const attention = {...nextRoute};
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
console.log(JSON.stringify({sessionHtml, project, attention, stayed: nextRoute}));
""",
            'location.hash = "#n=session:recce:019a";\n__els.app = {innerHTML: ""};\n',
        )

        self.assertIn('<a href="#n=attention">Attention</a>', out["sessionHtml"])
        self.assertIn('<a href="#n=projects">Projects</a>', out["sessionHtml"])
        self.assertIn('<a class="next-crumb" href="#n=project:recce">recce</a>', out["sessionHtml"])
        self.assertIn("recce", out["sessionHtml"])
        self.assertIn("019a", out["sessionHtml"])
        self.assertEqual(
            {"view": "project", "project": "recce", "session": None},
            out["project"],
        )
        self.assertEqual(
            {"view": "attention", "project": None, "session": None},
            out["attention"],
        )
        self.assertEqual(out["attention"], out["stayed"])

    def test_the_next_fragment_never_contains_the_old_session_token(self) -> None:
        out = self._run_page_js(
            """
const routes = [
  {view: "attention", project: null, session: null},
  {view: "projects", project: null, session: null},
  {view: "sessions", project: null, session: null},
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
        self.assertEqual("#n=attention", out["fragments"][0])
        self.assertEqual("#n=projects", out["fragments"][1])
        self.assertEqual("#n=sessions", out["fragments"][2])
        self.assertEqual("#n=project:recce%3Acloud", out["fragments"][3])
        self.assertEqual("#n=attention", out["repaired"])

    def test_shortcuts_select_matching_top_level_routes_and_leave_for_dashboard(self) -> None:
        out = self._run_page_js(
            """
__fire("keydown", {key: "s", target: {tagName: "BODY"}, preventDefault(){}});
const sessions = {route: {...nextRoute}, hash: location.hash, html: __els.app.innerHTML};
navigateNext({view: "session", project: "recce", session: "one"});
__fire("keydown", {key: "P", target: {tagName: "BODY"}, preventDefault(){}});
const projects = {route: {...nextRoute}, hash: location.hash, html: __els.app.innerHTML};
__fire("keydown", {key: "a", target: {tagName: "BODY"}, preventDefault(){}});
const attention = {route: {...nextRoute}, hash: location.hash, html: __els.app.innerHTML};
__fire("keydown", {key: "d", target: {tagName: "BODY"}, preventDefault(){}});
console.log(JSON.stringify({
  sessions,
  projects,
  attention,
  assigned: __assignedLocations,
  search: location.search,
  keydownListeners: (__listeners.keydown || []).length
}));
""",
            'location.search = "?next=true";\nlocation.hash = "#n=project:recce";\n'
            '__els.app = {innerHTML: ""};\n',
        )

        self.assertEqual({"view": "sessions", "project": None, "session": None}, out["sessions"]["route"])
        self.assertEqual("#n=sessions", out["sessions"]["hash"])
        self.assertIn('<h1>Sessions</h1>', out["sessions"]["html"])
        self.assertEqual({"view": "projects", "project": None, "session": None}, out["projects"]["route"])
        self.assertEqual("#n=projects", out["projects"]["hash"])
        self.assertIn('<h1>Projects</h1>', out["projects"]["html"])
        self.assertEqual({"view": "attention", "project": None, "session": None}, out["attention"]["route"])
        self.assertEqual("#n=attention", out["attention"]["hash"])
        self.assertIn('<h1>Attention</h1>', out["attention"]["html"])
        self.assertEqual(["/"], out["assigned"])
        self.assertEqual("?next=true", out["search"])
        self.assertEqual(1, out["keydownListeners"])

    def test_projects_shortcut_keeps_modifier_and_form_field_guards(self) -> None:
        out = self._run_page_js(
            """
const cases = {};
function attempt(name, event){
  navigateNext({view: "session", project: "recce", session: "one"});
  let prevented = false;
  __fire("keydown", {...event, key: "p", preventDefault(){ prevented = true; }});
  cases[name] = {route: {...nextRoute}, hash: location.hash, prevented};
}
for(const key of ["a", "p", "s"]){
  for(const tag of ["INPUT", "SELECT", "TEXTAREA"]){
    attempt(`${key}-${tag.toLowerCase()}`, {key, target: {tagName: tag}});
  }
  for(const modifier of ["metaKey", "ctrlKey", "altKey"]){
    attempt(`${key}-${modifier}`, {key, target: {tagName: "BODY"}, [modifier]: true});
  }
}
console.log(JSON.stringify(cases));
""",
            '__els.app = {innerHTML: ""};\n',
        )

        expected_route = {"view": "session", "project": "recce", "session": "one"}
        for name, case in out.items():
            with self.subTest(name=name):
                self.assertEqual(expected_route, case["route"])
                self.assertEqual("#n=session:recce:one", case["hash"])
                self.assertFalse(case["prevented"])

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

        self.assertIn(
            '<span class="next-running next-live">'
            '<span class="next-status-dot" aria-label="live">●</span> '
            "1 running · 3 subagents</span>",
            out,
        )
        self.assertIn(
            '<button type="button" class="next-gate" data-next-action="needs-input">'
            "1 need you</button>",
            out,
        )
        self.assertNotIn("4 running", out)
        self.assertIn('<h1>Attention</h1>', out)

    def test_the_need_you_pill_opens_the_session_queue(self) -> None:
        out = self._run_page_js(
            """
await __settle();
__fire("click", {
  target: {closest(selector){
    return selector === "[data-next-action]"
      ? {dataset: {nextAction: "needs-input"}}
      : null;
  }}
});
console.log(JSON.stringify({route: nextRoute, hash: location.hash, html: __els.app.innerHTML}));
""",
            """
location.hash = "#n=project:recce";
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  window_hours: 24,
  summary: {working: 0, needs_input: 1, active_sessions: 1},
  sessions: [{project: "recce", state: "needs_input", subagents: []}]
})});
""",
        )

        self.assertEqual({"view": "attention", "project": None, "session": None}, out["route"])
        self.assertEqual("#n=attention", out["hash"])
        self.assertIn('<h1>Attention</h1>', out["html"])

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

        self.assertIn(
            '<span class="next-running next-live">'
            '<span class="next-status-dot" aria-label="live">●</span> '
            "0 running · 0 subagents</span>",
            out,
        )
        self.assertNotIn("need you", out)
        self.assertNotIn('class="next-gate"', out)
        self.assertNotIn('data-next-action="needs-input"', out)
        self.assertIn('<nav aria-label="Primary"', out)
        self.assertIn('href="#n=attention"', out)
        self.assertIn('href="#n=projects"', out)
        self.assertIn('href="#n=sessions"', out)
        self.assertIn('<h1>Attention</h1>', out)
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

    def test_repeated_refresh_failures_explain_the_retained_legacy_poll_view(self) -> None:
        out = self._run_page_js(
            """
await __settle();
const good = __els.app.innerHTML;
__setNow(1040);
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

        self.assertIn('aria-label="live">●</span> 1 running', out["good"])
        self.assertNotIn('data-next-state="stalled"', out["once"])
        self.assertIn("Live refresh failed twice in a row", out["twice"])
        self.assertIn("Displayed data may be stale", out["twice"])
        self.assertIn("Last updated 40s ago", out["twice"])
        self.assertIn("Retrying automatically every 5s", out["twice"])
        self.assertIn("Retry now", out["twice"])
        self.assertNotIn("stream stopped", out["twice"].lower())
        self.assertIn('aria-label="live">●</span> 1 running', out["twice"])
        self.assertIn('data-next-state="stalled"', out["twice"])

    def test_retry_now_serializes_attempts_and_success_clears_the_notice(self) -> None:
        out = self._run_page_js(
            """
await __settle();
__mode = "fail";
__runInterval(5000);
await __settle();
__runInterval(5000);
await __settle();
__mode = "deferred";
const before = __fetchCalls.length;
const retry = {dataset: {nextAction: "retry-refresh"}, closest(selector){
  return selector === "[data-next-action]" ? this : null;
}};
__fire("click", {target: retry, preventDefault(){}});
__fire("click", {target: retry, preventDefault(){}});
const during = {calls: __fetchCalls.length - before, html: __els.app.innerHTML};
__releaseRetry({ok: true, json: async () => ({
  window_hours: 24,
  summary: {working: 2, needs_input: 0},
  sessions: [{project: "recce", subagents: []}, {project: "cargento", subagents: []}]
})});
await __settle();
await __settle();
console.log(JSON.stringify({during, recovered: __els.app.innerHTML}));
""",
            """
__els.app = {innerHTML: ""};
let __mode = "good";
let __releaseRetry = null;
__fetchImpl = async () => {
  if(__mode === "fail") throw new Error("offline");
  if(__mode === "deferred") return new Promise(resolve => { __releaseRetry = resolve; });
  return {ok: true, json: async () => ({
    window_hours: 24,
    summary: {working: 1, needs_input: 0},
    sessions: [{project: "recce", subagents: []}]
  })};
};
""",
        )

        self.assertEqual(1, out["during"]["calls"])
        self.assertIn('data-next-action="retry-refresh" disabled', out["during"]["html"])
        self.assertNotIn('data-next-state="stalled"', out["recovered"])
        self.assertIn('aria-label="live">●</span> 2 running', out["recovered"])


if __name__ == "__main__":
    unittest.main()
