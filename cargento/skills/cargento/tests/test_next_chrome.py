from __future__ import annotations

import shutil
import unittest

from .next_harness import NEXT_STYLES, NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextChromeBehaviorTest(NextPageJsHarness):
    def test_sessions_is_default_and_legacy_overviews_normalize_to_it(self) -> None:
        out = self._run_page_js(
            """
const fragments = ["", "#n=overview", "#n=attention", "#n=unknown"];
const routes = fragments.map(nextRouteFromFragment);
const repaired = routes.map(nextFragmentForRoute);
console.log(JSON.stringify({routes, repaired}));
""",
            '__els.app = {innerHTML: ""};\n',
        )
        assert isinstance(out, dict)

        for route, repaired in zip(out["routes"], out["repaired"], strict=True):
            self.assertEqual("sessions", route["view"])
            self.assertEqual("#n=sessions", repaired)

    def test_primary_routes_are_native_links_with_current_page(self) -> None:
        out = self._run_page_js(
            """
nextData = {summary: {working: 0, needs_input: 0}, sessions: [], asks: []};
        const views = ["projects", "sessions"];
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
            ["Cargento — Projects", "Cargento — Sessions"],
            strict=True,
        ):
            html = rendered["html"]
            self.assertEqual(title, rendered["title"])
            self.assertIn('<nav aria-label="Primary"', html)
            self.assertIn('href="#n=projects"', html)
            self.assertIn('href="#n=sessions"', html)
            self.assertEqual(2, html.count('<a href="#n='))
            self.assertEqual(1, html.count('aria-current="page"'))
            self.assertEqual(1, html.count("<h1"))
            self.assertLess(html.index('href="#n=projects"'), html.index('href="#n=sessions"'))

    def test_every_next_actionable_control_shares_the_44_pixel_target_contract(self) -> None:
        self.assertIn(
            '#app a,#app button,#app summary,#app [role="link"]{min-block-size:44px;'
            "min-inline-size:44px",
            NEXT_STYLES,
        )
        self.assertIn(
            "#app a{display:inline-flex;align-items:center;max-inline-size:100%",
            NEXT_STYLES,
        )
        self.assertIn(
            '.next-header nav[aria-label="Primary"] a{display:inline-flex;align-items:center;'
            "min-block-size:44px;min-inline-size:44px",
            NEXT_STYLES,
        )
        self.assertIn(
            ".next-menu summary{display:flex;align-items:center;justify-content:center;"
            "min-block-size:44px;min-inline-size:44px",
            NEXT_STYLES,
        )
        self.assertIn(".next-menu button{min-block-size:44px", NEXT_STYLES)

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
            {"view": "sessions", "project": None, "session": None},
            out["attention"],
        )
        self.assertIn("<h1>Session operations</h1>", out["html"])

    def test_canonical_session_route_round_trips_harness_and_sid(self) -> None:
        out = self._run_page_js(
            """
const route = {
  view: "session", project: "recce:cloud", harness: "antigravity", session: "same/sid"
};
const fragment = nextFragmentForRoute(route);
console.log(JSON.stringify({fragment, parsed: nextRouteFromFragment(fragment)}));
"""
        )

        self.assertEqual("#n=session:recce%3Acloud:antigravity:same%2Fsid", out["fragment"])
        self.assertEqual(
            {
                "view": "session",
                "project": "recce:cloud",
                "harness": "antigravity",
                "session": "same/sid",
            },
            out["parsed"],
        )

    def test_copy_session_id_uses_clipboard_announces_success_and_does_not_navigate(self) -> None:
        out = self._run_page_js(
            """
nextData = {
  generated: 1000, ask: true,
  harnesses: [{key: "claude", label: "Claude Code", reports_needs_input: true}],
  asks: [], sessions: [{
    harness: "claude", sid: "shared-id", project: "alpha/repo",
    state: "working", active: true, title: "Build it", tasks: [], subagents: []
  }]
};
navigateNext({view: "sessions", project: null, session: null});
const before = {...nextRoute};
const target = {
  dataset: {nextCopySession: "shared-id"},
  closest(selector){
    if(selector === "[data-next-copy-session]") return this;
    if(selector === "[data-next-route]") return {dataset: {nextRoute: "wrong"}};
    return null;
  },
  setAttribute(name, value){ this[name] = value; }
};
__fire("click", {target, preventDefault(){}, stopPropagation(){}});
await __settle();
console.log(JSON.stringify({
  before, after: nextRoute, copied: __copied, status: __copyStatus.textContent,
  state: target.dataset.nextCopyState
}));
""",
            """
let __copied = [];
const navigator = {clipboard: {writeText(value){ __copied.push(value); return Promise.resolve(); }}};
let __copyStatusText = "";
const __copyStatus = {
  setAttribute(){},
  set textContent(value){ __copyStatusText = String(value); },
  get textContent(){ return __copyStatusText; }
};
document.createElement = () => __copyStatus;
__els.app = {
  innerHTML: "", querySelectorAll(){ return []; }, querySelector(){ return null; },
  insertAdjacentElement(){}
};
""",
        )

        self.assertEqual(["shared-id"], out["copied"])
        self.assertEqual("Copied session ID shared-id", out["status"])
        self.assertEqual("copied", out["state"])
        self.assertEqual(out["before"], out["after"])

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

        self.assertIn('<a href="#n=sessions">Sessions</a>', out["sessionHtml"])
        self.assertIn('<a href="#n=projects">Projects</a>', out["sessionHtml"])
        self.assertIn('<a class="next-crumb" href="#n=project:recce">recce</a>', out["sessionHtml"])
        self.assertIn("recce", out["sessionHtml"])
        self.assertIn("<span>Session</span>", out["sessionHtml"])
        self.assertNotIn("<span>019a</span>", out["sessionHtml"])
        self.assertEqual(
            {"view": "project", "project": "recce", "session": None},
            out["project"],
        )
        self.assertEqual(
            {"view": "sessions", "project": None, "session": None},
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
        self.assertEqual("#n=sessions", out["fragments"][0])
        self.assertEqual("#n=projects", out["fragments"][1])
        self.assertEqual("#n=sessions", out["fragments"][2])
        self.assertEqual("#n=project:recce%3Acloud", out["fragments"][3])
        self.assertEqual("#n=sessions", out["repaired"])

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

        self.assertEqual(
            {"view": "sessions", "project": None, "session": None}, out["sessions"]["route"]
        )
        self.assertEqual("#n=sessions", out["sessions"]["hash"])
        self.assertIn("<h1>Session operations</h1>", out["sessions"]["html"])
        self.assertEqual(
            {"view": "projects", "project": None, "session": None}, out["projects"]["route"]
        )
        self.assertEqual("#n=projects", out["projects"]["hash"])
        self.assertIn("<h1>Projects</h1>", out["projects"]["html"])
        self.assertEqual(
            {"view": "sessions", "project": None, "session": None}, out["attention"]["route"]
        )
        self.assertEqual("#n=sessions", out["attention"]["hash"])
        self.assertIn("<h1>Session operations</h1>", out["attention"]["html"])
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
  __fire("keydown", {...event, preventDefault(){ prevented = true; }});
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

    def test_attention_focus_restoration_uses_stable_keys_and_bounded_fallbacks(self) -> None:
        out = self._run_page_js(
            """
const hostileKey = 'session:["claude","bad\\\"] [data-next-route] "]';
const retainedKey = 'session:["claude","retained"]';
const oldModel = {
  needs: [{key: retainedKey}, {key: hostileKey}], risk: [], close: [], next: []
};
const reorderedModel = {
  needs: [{key: hostileKey}, {key: retainedKey}], risk: [], close: [], next: []
};
const sectionModel = {
  needs: [{key: retainedKey}], risk: [], close: [], next: []
};
const emptyModel = {needs: [], risk: [], close: [], next: []};
nextAttention = oldModel;
document.activeElement = {subjectKey: hostileKey};
const snapshot = nextCaptureFocus();
nextAttention = reorderedModel;
nextRestoreFocus(snapshot, reorderedModel);
const survivorCall = __focusCalls.pop();
nextAttention = sectionModel;
nextRestoreFocus(snapshot, sectionModel);
nextAttention = emptyModel;
nextRestoreFocus(snapshot, emptyModel);
const calls = [...__focusCalls];
document.activeElement = {subjectKey: "outside-the-queue"};
const absent = nextCaptureFocus();
nextRestoreFocus(absent, emptyModel);
console.log(JSON.stringify({snapshot, survivorCall, calls, absent, selectors: __selectors}));
""",
            """
let __focusCalls = [];
let __selectors = [];
const __focusTarget = (name, subjectKey = null) => ({
  subjectKey,
  focus(){ __focusCalls.push(name); document.activeElement = this; }
});
__els.app = {
  innerHTML: "",
  querySelectorAll(selector){
    __selectors.push(selector);
    if(selector === "[data-next-subject-key]"){
      return ["needs", "risk", "close", "next"].flatMap(section =>
        nextAttention[section].map(subject => ({
          dataset: {nextSubjectKey: subject.key},
          contains(active){ return active && active.subjectKey === subject.key; },
          querySelector(inner){
            return inner === "h3 a" ? __focusTarget(`subject:${subject.key}`, subject.key) : null;
          }
        }))
      );
    }
    if(selector === "[data-next-attention-section]"){
      return ["needs", "risk", "close", "next"].filter(section =>
        nextAttention[section].length > 0
      ).map(section => ({
        dataset: {nextAttentionSection: section},
        querySelector(inner){
          return inner === "h2" ? __focusTarget(`next-attention-${section}`) : null;
        }
      }));
    }
    return [];
  },
  querySelector(selector){
    __selectors.push(selector);
    return selector === ".next-attention h1"
      ? __focusTarget("next-attention-title")
      : null;
  }
};
""",
        )

        self.assertEqual(
            {"key": 'session:["claude","bad"] [data-next-route] "]', "section": "needs"},
            out["snapshot"],
        )
        self.assertEqual(
            'subject:session:["claude","bad"] [data-next-route] "]',
            out["survivorCall"],
        )
        self.assertEqual(["next-attention-needs", "next-attention-title"], out["calls"])
        self.assertIsNone(out["absent"])
        self.assertNotIn(out["snapshot"]["key"], out["selectors"])
        self.assertTrue(
            all(
                selector
                in {
                    "[data-next-session]",
                    "[data-next-subject-key]",
                    "[data-next-attention-toggle]",
                    "[data-next-attention-section]",
                    ".next-attention h1",
                }
                for selector in out["selectors"]
            )
        )

    def test_focused_session_row_survives_refresh(self) -> None:
        out = self._run_page_js(
            """
const payload = generated => ({
  generated,
  sessions: [0, 1, 2, 3].map(index => ({
    harness: "claude", sid: `owner-${index}`, project: `project-${index}`,
    state: "needs_input"
  })),
  asks: [0, 1, 2, 3].map(index => ({
    id: `ask-${index}`, session_id: `owner-${index}`, project: `project-${index}`,
    question: `Question ${index}`, age_sec: 400 - index
  }))
});
nextData = payload(1000);
nextAttention = nextAttentionModel(nextData);
document.activeElement = {sessionId: "owner-2"};
__fetchImpl = async () => ({ok: true, json: async () => payload(2000)});
await refreshNext();
console.log(JSON.stringify({
  html: __els.app.innerHTML,
  focusCalls: __focusCalls
}));
""",
            """
let __focusCalls = [];
__els.app = {
  innerHTML: "",
  querySelectorAll(selector){
    if(selector === "[data-next-session]") return [0, 1, 2, 3].map(index => ({
      dataset: {nextSession: `owner-${index}`},
      contains(active){ return active && active.sessionId === `owner-${index}`; },
      focus(){ __focusCalls.push(`session:owner-${index}`); document.activeElement = this; }
    }));
    if(selector === "[data-next-subject-key]") return [];
    if(selector === "[data-next-attention-toggle]") return [];
    if(selector === "[data-next-attention-section]") return [];
    return [];
  },
  querySelector(){ return null; }
};
""",
        )

        self.assertIn('data-next-session="owner-2"', out["html"])
        self.assertEqual(["session:owner-2"], out["focusCalls"])

    def test_attention_announces_successful_count_changes_only(self) -> None:
        out = self._run_page_js(
            """
const previous = {counts: {needs: 1, risk: 1, close: 0, next: 0}};
const current = {counts: {needs: 2, risk: 1, close: 0, next: 0}};
const reordered = {counts: {needs: 2, risk: 1, close: 0, next: 0}};
console.log(JSON.stringify({
  initial: nextAttentionAnnouncement(null, current),
  changed: nextAttentionAnnouncement(previous, current),
  reordered: nextAttentionAnnouncement(current, reordered)
}));
""",
            '__els.app = {innerHTML: ""};\n',
        )

        self.assertEqual("", out["initial"])
        self.assertEqual("Attention updated: 2 need you, 1 at risk", out["changed"])
        self.assertNotIn("moved", out["changed"].lower())
        self.assertNotIn("because", out["changed"].lower())
        self.assertEqual("", out["reordered"])

    def test_attention_status_does_not_replay_on_failure_navigation_or_reorder(self) -> None:
        out = self._run_page_js(
            """
await __settle();
const first = __statusNodes[0];
__payload = {
  generated: 2000,
  window_hours: 24,
  summary: {working: 0, needs_input: 1},
  harnesses: [],
  asks: [{id: "first", question: "First", session_id: "first"}],
  sessions: [{harness: "claude", sid: "first", project: "first", state: "needs_input"}]
};
await refreshNext();
const afterSuccess = {writes: [...__statusWrites], text: first.textContent};
__fail = true;
await refreshNext();
navigateNext({view: "projects", project: null, session: null});
__fail = false;
__payload = {
  generated: 3000,
  window_hours: 24,
  summary: {working: 0, needs_input: 1},
  harnesses: [],
  asks: [{id: "second", question: "Second", session_id: "second"}],
  sessions: [{harness: "codex", sid: "second", project: "second", state: "needs_input"}]
};
await refreshNext();
renderNext();
console.log(JSON.stringify({
  nodes: __statusNodes.length,
  same: first === __statusNodes[0],
  role: first.role,
  ariaLive: first.ariaLive,
  afterSuccess,
  finalWrites: __statusWrites,
  text: first.textContent
}));
""",
            """
let __statusNodes = [];
let __statusWrites = [];
let __statusText = "";
document.createElement = () => ({
  style: {},
  appendChild(){},
  setAttribute(){},
  set textContent(value){ __statusText = String(value); __statusWrites.push(__statusText); },
  get textContent(){ return __statusText; }
});
__els.app = {
  innerHTML: "",
  querySelectorAll(){ return []; },
  querySelector(){ return null; },
  insertAdjacentElement(_position, node){ __statusNodes.push(node); }
};
let __fail = false;
let __payload = {
  generated: 1000,
  window_hours: 24,
  summary: {working: 0, needs_input: 0},
  harnesses: [],
  asks: [],
  sessions: []
};
__fetchImpl = async () => {
  if(__fail) throw new Error("offline");
  return {ok: true, json: async () => __payload};
};
""",
        )

        self.assertEqual(1, out["nodes"])
        self.assertTrue(out["same"])
        self.assertEqual("status", out["role"])
        self.assertEqual("polite", out["ariaLive"])
        self.assertEqual("Attention updated: 1 need you", out["afterSuccess"]["text"])
        self.assertEqual(1, out["afterSuccess"]["writes"].count("Attention updated: 1 need you"))
        self.assertEqual(out["afterSuccess"]["writes"], out["finalWrites"])
        self.assertEqual("Attention updated: 1 need you", out["text"])

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
            "1 reported block</button>",
            out,
        )
        self.assertNotIn("4 running", out)
        self.assertIn("<h1>Session operations</h1>", out)

    def test_exact_request_state_skew_is_counted_in_the_header_block_total(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            """
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  ask: true,
  window_hours: 24,
  summary: {working: 0, needs_input: 0},
  harnesses: [{key: "codex", reports_needs_input: true}],
  sessions: [{harness: "codex", sid: "skew", project: "recce", state: "idle"}],
  asks: [{id: "ask", session_id: "skew", question: "Choose the lane"}]
})});
""",
        )

        self.assertIn(
            '<button type="button" class="next-gate" data-next-action="needs-input">'
            "1 reported block</button>",
            out,
        )
        self.assertIn(
            'data-next-fleet-fact="reported-blocks"><span>REPORTED BLOCKS</span><strong>1</strong>',
            out,
        )

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

        self.assertEqual({"view": "sessions", "project": None, "session": None}, out["route"])
        self.assertEqual("#n=sessions", out["hash"])
        self.assertIn("<h1>Session operations</h1>", out["html"])

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
        self.assertNotIn('class="next-gate"', out)
        self.assertNotIn('data-next-action="needs-input"', out)
        self.assertIn('<nav aria-label="Primary"', out)
        self.assertIn('href="#n=projects"', out)
        self.assertIn('href="#n=sessions"', out)
        self.assertIn("<h1>Session operations</h1>", out)
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

    def test_repeated_refresh_failures_retain_the_attention_queue(self) -> None:
        out = self._run_page_js(
            """
await __settle();
const good = __els.app.innerHTML;
const firstKeys = nextAttention.needs.map(subject => subject.key);
document.activeElement = {subjectKey: firstKeys[1]};
__setNow(1040);
__nextShouldFail = true;
__runInterval(5000);
await __settle();
const once = __els.app.innerHTML;
const onceKeys = nextAttention.needs.map(subject => subject.key);
__runInterval(5000);
await __settle();
const twice = __els.app.innerHTML;
const twiceKeys = nextAttention.needs.map(subject => subject.key);
const focusAfterFailures = document.activeElement.subjectKey;
__nextShouldFail = false;
__payload = {
  generated: 1040,
  window_hours: 24,
  ask: true,
  summary: {working: 0, needs_input: 1},
  asks: [{id: "first", question: "Approve deploy", session_id: "one", age_sec: 20}],
  sessions: [
    {harness: "claude", sid: "one", project: "recce", state: "needs_input", subagents: []}
  ]
};
await refreshNext();
console.log(JSON.stringify({
  good, once, twice, firstKeys, onceKeys, twiceKeys, focusAfterFailures,
  recovered: __els.app.innerHTML,
  recoveredKeys: nextAttention.needs.map(subject => subject.key),
  focusCalls: __focusCalls,
  failures: nextRefreshFailures
}));
""",
            """
let __focusCalls = [];
const __focusTarget = (name, subjectKey = null) => ({
  subjectKey,
  focus(){ __focusCalls.push(name); document.activeElement = this; }
});
__els.app = {
  innerHTML: "",
  querySelectorAll(selector){
    if(selector === "[data-next-subject-key]"){
      return ["needs", "risk", "close", "next"].flatMap(section =>
        nextAttention[section].map(subject => ({
          dataset: {nextSubjectKey: subject.key},
          contains(active){ return active && active.subjectKey === subject.key; },
          querySelector(inner){
            return inner === "h3 a" ? __focusTarget(`subject:${subject.key}`, subject.key) : null;
          }
        }))
      );
    }
    if(selector === "[data-next-attention-section]"){
      return ["needs", "risk", "close", "next"].filter(section =>
        nextAttention[section].length > 0
      ).map(section => ({
        dataset: {nextAttentionSection: section},
        querySelector(inner){
          return inner === "h2" ? __focusTarget(`next-attention-${section}`) : null;
        }
      }));
    }
    return [];
  },
  querySelector(selector){
    return selector === ".next-attention h1" ? __focusTarget("next-attention-title") : null;
  }
};
let __nextShouldFail = false;
let __payload = {
  generated: 1000,
  window_hours: 24,
  ask: true,
  summary: {working: 0, needs_input: 2},
  asks: [
    {id: "first", question: "Approve deploy", session_id: "one", age_sec: 20},
    {id: "second", question: "Choose target", session_id: "two", age_sec: 10}
  ],
  sessions: [
    {harness: "claude", sid: "one", project: "recce", state: "needs_input", subagents: []},
    {harness: "codex", sid: "two", project: "cargento", state: "needs_input", subagents: []}
  ]
};
__fetchImpl = async () => {
  if(__nextShouldFail) throw new Error("offline");
  return {ok: true, json: async () => __payload};
};
""",
        )

        self.assertEqual(out["firstKeys"], out["onceKeys"])
        self.assertEqual(out["firstKeys"], out["twiceKeys"])
        self.assertNotIn("Live refresh failed", out["once"])
        self.assertIn("Live refresh failed twice in a row", out["twice"])
        self.assertIn("Displayed data may be stale", out["twice"])
        self.assertIn("Last updated 40s ago", out["twice"])
        self.assertIn("Retrying automatically every 5s", out["twice"])
        self.assertIn("Retry now", out["twice"])
        self.assertNotIn("stream stopped", out["twice"].lower())
        self.assertIn("Approve deploy", out["good"])
        self.assertIn("Approve deploy", out["twice"])
        self.assertIn('data-next-state="stalled"', out["twice"])
        self.assertEqual(out["firstKeys"][1], out["focusAfterFailures"])
        self.assertEqual([out["firstKeys"][0]], out["recoveredKeys"])
        self.assertEqual("next-attention-needs", out["focusCalls"][-1])
        self.assertNotIn('data-next-state="stalled"', out["recovered"])
        self.assertEqual(0, out["failures"])

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
const during = {
  calls: __fetchCalls.length - before,
  html: __els.app.innerHTML,
  failures: nextRefreshFailures,
  generated: nextData.generated
};
__releaseRetry({ok: true, json: async () => ({
  generated: 2000,
  window_hours: 24,
  summary: {working: 2, needs_input: 0},
  sessions: [
    {project: "recce", sid: "one", state: "working", subagents: []},
    {project: "cargento", sid: "two", state: "working", subagents: []}
  ]
})});
await __settle();
await __settle();
console.log(JSON.stringify({
  during,
  recovered: __els.app.innerHTML,
  recoveredFailures: nextRefreshFailures,
  recoveredGenerated: nextData.generated
}));
""",
            """
__els.app = {innerHTML: ""};
let __mode = "good";
let __releaseRetry = null;
__fetchImpl = async () => {
  if(__mode === "fail") throw new Error("offline");
  if(__mode === "deferred") return new Promise(resolve => { __releaseRetry = resolve; });
  return {ok: true, json: async () => ({
    generated: 1000,
    window_hours: 24,
    summary: {working: 1, needs_input: 0},
    sessions: [{project: "recce", sid: "one", state: "working", subagents: []}]
  })};
};
""",
        )

        self.assertEqual(1, out["during"]["calls"])
        self.assertEqual(2, out["during"]["failures"])
        self.assertEqual(1000, out["during"]["generated"])
        self.assertIn('data-next-action="retry-refresh" disabled', out["during"]["html"])
        self.assertIn('aria-label="live">●</span> 1 running', out["during"]["html"])
        self.assertNotIn('data-next-state="stalled"', out["recovered"])
        self.assertIn('aria-label="live">●</span> 2 running', out["recovered"])
        self.assertEqual(0, out["recoveredFailures"])
        self.assertEqual(2000, out["recoveredGenerated"])


if __name__ == "__main__":
    unittest.main()
