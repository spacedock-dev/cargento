from __future__ import annotations

import json
import re
import shutil
import unittest
from typing import Any, ClassVar

from .next_harness import NEXT_STYLES, NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextChromeBehaviorTest(NextPageJsHarness):
    def test_a_live_revision_restores_parked_focus_without_requesting_a_scroll(self) -> None:
        out = self._run_page_js(
            """
await __settle();
window.innerHeight = 1000; window.innerWidth = 1440;
const rectangles = [
  {top: 100, bottom: 144, left: 10, right: 110},
  {top: 9000, bottom: 9044, left: 10, right: 110},
  {top: -44, bottom: 0, left: 10, right: 110},
  {top: 1000, bottom: 1044, left: 10, right: 110},
  {top: 100, bottom: 144, left: 1440, right: 1540},
  {top: -10, bottom: 34, left: 10, right: 110}
];
const rows = ["owner", "other"].map(sid => ({
  harness: "claude", sid, project: sid, state: "needs_input", active: true
}));
const results = [];
for(const lane of ["named", "control", "route", "session", "toggle", "subject", "section", "title"]){
  for(const rect of rectangles){
    nextData = {sessions: rows, asks: [], native_notify: "osascript"};
    nextAttention = nextAttentionModel(nextData);
    nextRoute = {view: "attention", project: null, session: null};
    let replaced = false;
    const calls = [];
    const old = {getBoundingClientRect: () => rect, value: "ship the fix",
      selectionStart: 4, selectionEnd: 8,
      dataset: {nextFocus: "steer-draft:owner", nextDraft: "steer", nextControlsProject: "owner"}};
    const fresh = {dataset: old.dataset, value: old.value,
      focus(options){ calls.push(options || null); document.activeElement = this; },
      setSelectionRange(start, end){ this.caret = [start, end]; }};
    const contains = active => active === old;
    const container = dataset => ({dataset, contains,
      focus: fresh.focus.bind(fresh),
      querySelector: () => lane === "session" ? null : fresh});
    __els.app = {
      set innerHTML(value){ replaced = true; this.html = value; },
      get innerHTML(){ return this.html || ""; },
      insertAdjacentElement(){},
      querySelector: selector => selector === ".next-attention h1" ? fresh : null,
      querySelectorAll(selector){
        if(lane === "named" && selector === "[data-next-focus]") return [replaced ? fresh : old];
        if(lane === "named" && selector === "[data-next-draft]") return [old];
        if(lane === "control" && selector === "[data-next-copy-session]") return [
          {...container({nextCopySession: "owner", nextCopyHarness: "claude"})}
        ];
        if(["route", "session"].includes(lane) && selector === "[data-next-session]")
          return [container({nextSession: "owner", nextHarness: "claude"})];
        if(lane === "toggle" && selector === "[data-next-attention-toggle]")
          return [container({nextAttentionToggle: "needs"})];
        if(["subject", "section", "title"].includes(lane) && selector === "[data-next-subject-key]" &&
          (!replaced || lane === "subject"))
          return [container({nextSubjectKey: 'session:["claude","owner"]'})];
        if(lane === "section" && selector === "[data-next-attention-section]")
          return [container({nextAttentionSection: "needs"})];
        return [];
      }
    };
    __fetchImpl = async () => ({ok: true, json: async () => ({
      sessions: lane === "title" ? [] : rows.slice().reverse(), asks: [], native_notify: "osascript"
    })});
    document.activeElement = old;
    await refreshNext();
    results.push({lane, calls, restored: document.activeElement === fresh, caret: fresh.caret});
  }
}
console.log(JSON.stringify(results));
"""
        )
        assert isinstance(out, list)
        for index, arm in enumerate(out):
            with self.subTest(lane=arm["lane"], rectangle=index % 6):
                self.assertTrue(arm["restored"])
                self.assertEqual([{"preventScroll": index % 6 in (1, 2, 3, 4)}], arm["calls"])
                if arm["lane"] == "named":
                    self.assertEqual([4, 8], arm["caret"])

    def test_projects_is_default_and_invalid_fragments_normalize_to_it(self) -> None:
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
            self.assertEqual("projects", route["view"])
            self.assertEqual("#n=projects", repaired)

    def test_attention_route_round_trips(self) -> None:
        out = self._run_page_js(
            """
const route = nextRouteFromFragment("#n=attention");
console.log(JSON.stringify({route, fragment: nextFragmentForRoute(route)}));
"""
        )

        self.assertEqual({"view": "attention", "project": None, "session": None}, out["route"])
        self.assertEqual("#n=attention", out["fragment"])

    def test_every_top_level_route_is_reachable_from_the_primary_nav(self) -> None:
        # The view list is read off `NEXT_TOP_LEVEL_VIEWS` rather than written
        # here, because the version of this test that named its two views
        # enforced the defect: it asserted exactly two nav links while the
        # router had three, so Attention was a whole screen with no link to it
        # and nothing marked current when you were standing on it. A fourth
        # view now cannot be added without a link to it.
        out = self._run_page_js(
            """
nextData = {summary: {working: 0, needs_input: 0}, sessions: [], asks: []};
const views = [...NEXT_TOP_LEVEL_VIEWS];
const rendered = views.map(view => {
  navigateNext({view, project: null, session: null});
  return {view, title: document.title, html: __els.app.innerHTML};
});
console.log(JSON.stringify({views, rendered}));
""",
            '__els.app = {innerHTML: ""};\n',
        )
        views = out["views"]
        self.assertIn("attention", views)

        titles = {
            "attention": "Cargento \u2014 Attention",
            "projects": "Cargento \u2014 Projects",
            "sessions": "Cargento \u2014 Sessions",
        }
        for rendered in out["rendered"]:
            view = rendered["view"]
            html = rendered["html"]
            with self.subTest(view=view):
                self.assertEqual(titles[view], rendered["title"])
                self.assertIn('<nav aria-label="Primary"', html)
                # Every top-level view is offered from every top-level view, so
                # no screen is a dead end you can only leave by guessing a
                # fragment or knowing a keyboard shortcut.
                for offered in views:
                    self.assertIn(f'href="#n={offered}"', html)
                self.assertEqual(len(views), html.count('<a href="#n='))
                # And the one you are standing on is the one marked. This is the
                # assertion the old test could not make for Attention, because
                # it never navigated there.
                self.assertEqual(1, html.count('aria-current="page"'))
                self.assertIn(f'href="#n={view}" aria-current="page"', html)
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
        self.assertIn(
            '.next-breadcrumb [aria-current="page"]{display:block;margin-top:4px;'
            "overflow-wrap:anywhere}",
            NEXT_STYLES,
        )

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
            {"view": "projects", "project": None, "session": None},
            out["attention"],
        )
        self.assertIn("<h1>Projects</h1>", out["html"])

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
    if(selector.includes("data-next-copy-session")) return this;
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

    def test_copy_re_entry_command_uses_the_same_lane_as_the_session_id_control(self) -> None:
        # One lane, not two: the command control sets the same `data-next-copy-state`
        # and announces through the same live region the session-id control does, so
        # a reader who has learned one has learned both.
        out = self._run_page_js(
            """
nextData = {
  generated: 1000,
  harnesses: [{key: "claude", label: "Claude Code", reports_needs_input: true}],
  asks: [], sessions: [{
    harness: "claude", sid: "shared-id", resume_id: "27d10654-1cb5-481e-8194-6ce868b91bb5",
    project: "alpha/repo", state: "needs_input", blocked_since: 900,
    title: "Waiting on you", tasks: [], subagents: []
  }]
};
navigateNext({view: "sessions", project: null, session: null});
const before = {...nextRoute};
const target = {
  dataset: {nextCopyCommand: "claude --resume 27d10654-1cb5-481e-8194-6ce868b91bb5"},
  closest(selector){
    if(selector.includes("data-next-copy-command")) return this;
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

        self.assertEqual(["claude --resume 27d10654-1cb5-481e-8194-6ce868b91bb5"], out["copied"])
        self.assertEqual(
            "Copied claude --resume 27d10654-1cb5-481e-8194-6ce868b91bb5", out["status"]
        )
        self.assertEqual("copied", out["state"])
        self.assertEqual(out["before"], out["after"])

    def test_a_context_without_a_clipboard_says_so_and_leaves_the_command_readable(self) -> None:
        # `navigator.clipboard` is absent over plain HTTP in some browsers, which is
        # exactly how this page is served. The fallback is the one the session-id
        # control already uses: announce the failure, and leave the command on the
        # control's own title for the reader to take by hand.
        out = self._run_page_js(
            """
nextData = {
  generated: 1000,
  harnesses: [{key: "codex", label: "Codex", reports_needs_input: true}],
  asks: [], sessions: [{
    harness: "codex", sid: "01a06fac-629f-7c40-9c86-f84c55680151",
    resume_id: "01a06fac-629f-7c40-9c86-f84c55680151",
    project: "alpha/repo", state: "needs_input", blocked_since: 900,
    title: "Waiting on you", tasks: [], subagents: []
  }]
};
const html = nextAttentionView(nextAttentionModel(nextData));
const target = {
  dataset: {nextCopyCommand: "codex resume 01a06fac-629f-7c40-9c86-f84c55680151"},
  closest(selector){
    return selector.includes("data-next-copy-command") ? this : null;
  },
  setAttribute(name, value){ this[name] = value; }
};
__fire("click", {target, preventDefault(){}, stopPropagation(){}});
await __settle();
console.log(JSON.stringify({
  html, copied: __copied, status: __copyStatus.textContent,
  state: target.dataset.nextCopyState
}));
""",
            """
let __copied = [];
const navigator = {};
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

        self.assertEqual([], out["copied"])
        self.assertEqual("Re-entry command could not be copied", out["status"])
        self.assertEqual("failed", out["state"])
        self.assertIn('title="codex resume 01a06fac-629f-7c40-9c86-f84c55680151"', out["html"])

    # The raise lane's stubs: the injected capability meta, a status element the
    # test can read back, and a fetch a test replaces per case. `__raiseTarget` is
    # the button the click listener would have found, shaped the way the copy
    # tests shape theirs.
    RAISE_PRELUDE = """
document.querySelector = selector => selector === 'meta[name="cargento-focus"]'
  ? {getAttribute: name => (name === "content" ? "0a1b2c3d" : null)}
  : null;
let __raiseStatusText = "";
const __raiseStatus = {
  setAttribute(){},
  set textContent(value){ __raiseStatusText = String(value); },
  get textContent(){ return __raiseStatusText; }
};
document.createElement = () => __raiseStatus;
__els.app = {
  innerHTML: "", querySelectorAll(){ return []; }, querySelector(){ return null; },
  insertAdjacentElement(){}
};
// The page's own boot refresh of `/api/data` is in `__fetchCalls` too; only the
// focus route is this lane's.
const __raiseCalls = () => __fetchCalls.filter(call => call[0] === "/api/focus");
const __raiseTarget = () => ({
  dataset: {nextRaiseSession: "sid-published", nextRaiseHarness: "claude"},
  closest(selector){
    return selector.includes("data-next-raise-session") ? this : null;
  },
  setAttribute(name, value){ this[name] = value; }
});
"""

    def raise_click(self, fetch_impl: str, *, prelude: str = "") -> dict[str, Any]:
        out = self._run_page_js(
            f"""
__fetchImpl = {fetch_impl};
const target = __raiseTarget();
__fire("click", {{target, preventDefault(){{}}, stopPropagation(){{}}}});
await __settle();
await __settle();
await __settle();
console.log(JSON.stringify({{
  calls: __raiseCalls(), status: __raiseStatus.textContent,
  state: target.dataset.nextRaiseState || null
}}));
""",
            self.RAISE_PRELUDE + prelude,
        )
        assert isinstance(out, dict)
        return out

    def test_a_raise_posts_the_run_capability_and_says_only_what_the_boolean_says(self) -> None:
        # The label is SENT, never RAISED. The published boolean is the raise
        # command's exit status, and DRC-4387 recorded one exiting zero with nothing
        # coming forward, so a window arriving in front of the reader is a claim this
        # page cannot make.
        out = self.raise_click(
            "async () => ({ok: true, status: 200, json: async () => ({focused: true})})"
        )

        self.assertEqual(1, len(out["calls"]))
        self.assertEqual("/api/focus", out["calls"][0][0])
        options = out["calls"][0][1]
        self.assertEqual("POST", options["method"])
        self.assertEqual("0a1b2c3d", options["headers"]["X-Cargento-Capability"])
        self.assertEqual({"harness": "claude", "sid": "sid-published"}, json.loads(options["body"]))
        self.assertEqual("sent", out["state"])
        self.assertIn("Raise sent", out["status"])
        self.assertNotIn("Raised", out["status"])

    def test_the_boolean_false_is_one_answer_and_never_named_as_a_reason(self) -> None:
        # A declined lookup, an unknown session and a failed command are the same
        # false to a caller, by contract, so the wording must cover all three.
        out = self.raise_click(
            "async () => ({ok: true, status: 200, json: async () => ({focused: false})})"
        )

        self.assertEqual("declined", out["state"])
        self.assertEqual("No terminal was raised", out["status"])

    def test_the_rate_ceiling_and_a_transport_failure_read_apart(self) -> None:
        throttled = self.raise_click(
            "async () => ({ok: false, status: 429, json: async () => ({})})"
        )
        self.assertEqual("throttled", throttled["state"])
        # The wording must be true of both arms the server refuses on, and the
        # in-flight one is the arm it is nearly never. `claim_focus` refuses when
        # `_focus_inflight` is set OR when the last raise was inside
        # `focus_floor_sec`, and `release_focus` clears only the first, so a raise
        # that completes still holds the floor for a second afterwards. The page's
        # own `nextRaiseInFlight` suppresses a same-tab repeat before it reaches
        # the wire, so the in-flight arm needs two tabs clicking within about the
        # length of one raise; the floor is what a double-click hits (DRC-4390).
        self.assertNotIn("in flight", throttled["status"])
        self.assertIn("too recent", throttled["status"])
        self.assertIn("Try again", throttled["status"])

        for impl in (
            "async () => ({ok: false, status: 503, json: async () => ({})})",
            "async () => { throw new Error('offline'); }",
        ):
            with self.subTest(impl=impl):
                failed = self.raise_click(impl)
                self.assertEqual("failed", failed["state"])
                self.assertEqual("Raise could not be sent", failed["status"])

    def test_a_stale_capability_names_the_restart_and_the_remedy(self) -> None:
        # Observed: the daemon was restarted under an open tab. `/api/data` needs no
        # capability, so the board kept rendering fresh rows and the control kept
        # rendering with them, while every click posted the previous run's
        # capability and came back 403 forever. The generic failure named neither
        # the cause nor the one-keystroke remedy (DRC-4396).
        stale = self.raise_click("async () => ({ok: false, status: 403, json: async () => ({})})")

        self.assertEqual("stale", stale["state"])
        self.assertNotEqual("Raise could not be sent", stale["status"])
        self.assertIn("restarted", stale["status"])
        self.assertIn("Reload", stale["status"])

    def test_no_capability_sends_no_request_that_could_only_be_refused(self) -> None:
        out = self.raise_click(
            "async () => ({ok: true, status: 200, json: async () => ({focused: true})})",
            prelude="document.querySelector = () => null;\n",
        )

        self.assertEqual([], out["calls"])
        self.assertIsNone(out["state"])

    def test_a_second_click_while_one_raise_is_in_flight_does_not_repeat_it(self) -> None:
        out = self._run_page_js(
            """
__fetchImpl = () => new Promise(() => {});
const target = __raiseTarget();
__fire("click", {target, preventDefault(){}, stopPropagation(){}});
await __settle();
const second = __raiseTarget();
__fire("click", {target: second, preventDefault(){}, stopPropagation(){}});
await __settle();
console.log(JSON.stringify({
  calls: __raiseCalls().length, status: __raiseStatus.textContent,
  state: target.dataset.nextRaiseState || null,
  secondState: second.dataset.nextRaiseState || null
}));
""",
            self.RAISE_PRELUDE,
        )
        assert isinstance(out, dict)

        self.assertEqual(1, out["calls"])
        self.assertEqual("sending", out["state"])
        # The second click is refused and says so. Silence there was indistinguishable
        # from a dead button, and the control the reader clicked is on the page and
        # marked unavailable — unlike the no-capability arm below it, where nothing
        # rendered and there is nothing to explain (DRC-4390).
        self.assertEqual("throttled", out["secondState"])
        self.assertIn("too recent", out["status"])

    # Two waiting rows, both reporting a terminal Cargento can reach. Two is the
    # smallest board on which the page-level fact is observable at all: with one
    # row, painting the row that was clicked and painting the page are the same
    # picture.
    RAISABLE_ROWS: ClassVar[dict[str, Any]] = {
        "generated": 10_000,
        "harnesses": [{"key": "claude", "label": "Claude Code"}],
        "sessions": [
            {
                "harness": "claude",
                "sid": "sid-published",
                "project": "alpha/repo",
                "state": "needs_input",
                "blocked_since": 9_400,
                "title": "Waiting on you",
                "focusable": True,
            },
            {
                "harness": "claude",
                "sid": "sid-elsewhere",
                "project": "beta/repo",
                "state": "needs_input",
                "blocked_since": 9_300,
                "title": "Also waiting",
                "focusable": True,
            },
        ],
        "asks": [],
    }

    # The raise lane's stubs plus a live `#app` that answers the sweep. The two
    # recording controls stand in for the buttons already in the document when the
    # click lands, which is the arm a re-render cannot show. They carry the two
    # rows' own datasets because the sweep reads them, exactly as the render does.
    LIVE_RAISE_PRELUDE = """
const __liveRaises = [
  {dataset: {nextRaiseSession: "sid-published", nextRaiseHarness: "claude"}, attrs: {}},
  {dataset: {nextRaiseSession: "sid-elsewhere", nextRaiseHarness: "claude"}, attrs: {}}
].map(control => Object.assign(control, {
  setAttribute(name, value){ this.attrs[name] = String(value); },
  removeAttribute(name){ delete this.attrs[name]; }
}));
__els.app = {
  innerHTML: "",
  querySelectorAll(selector){
    return selector === "[data-next-raise-session]" ? __liveRaises : [];
  },
  querySelector(){ return null; },
  insertAdjacentElement(){}
};
const __swept = () => __liveRaises.map(control => control.attrs["aria-disabled"] || null);
const __sweptState = () =>
  __liveRaises.map(control => control.attrs["data-next-raise-state"] || null);
// One render, applied to the live controls. `renderNext` replaces `#app`
// wholesale, so whatever the render paints is what the document now carries —
// and the node the click handler is still holding is no longer among them.
const __renderLive = () => {
  const html = nextAttentionView(nextAttentionModel(nextData));
  for(const control of __liveRaises){
    const button = html.split("<button").find(part => part.includes(
      `data-next-raise-session="${control.dataset.nextRaiseSession}"`)) || "";
    const state = /data-next-raise-state="([^"]*)"/.exec(button);
    if(state) control.attrs["data-next-raise-state"] = state[1];
    else delete control.attrs["data-next-raise-state"];
    if(button.includes('aria-disabled="true"')) control.attrs["aria-disabled"] = "true";
    else delete control.attrs["aria-disabled"];
  }
  return html;
};
"""

    def test_a_raise_in_flight_reads_unavailable_on_every_row_not_just_the_clicked_one(
        self,
    ) -> None:
        # The condition is the daemon's, not the row's: one `_focus_inflight` and one
        # `_focus_last_at` for the whole process, and one module-level flag for the
        # whole page. Painting the clicked row alone attributes a page-wide refusal to
        # whichever row was clicked while every other RAISE is equally unavailable and
        # says nothing (DRC-4390).
        out = self._run_page_js(
            f"""
nextData = JSON.parse({json.dumps(json.dumps(self.RAISABLE_ROWS))});
let __release = null;
__fetchImpl = () => new Promise(resolve => {{ __release = resolve; }});
__fire("click", {{target: __raiseTarget(), preventDefault(){{}}, stopPropagation(){{}}}});
await __settle();
const busy = nextAttentionView(nextAttentionModel(nextData));
const sweptBusy = __swept();
__release({{ok: true, status: 200, json: async () => ({{focused: true}})}});
await __settle();
await __settle();
await __settle();
const free = nextAttentionView(nextAttentionModel(nextData));
console.log(JSON.stringify({{
  rows: (busy.match(/data-next-raise-session/g) || []).length,
  busyDisabled: (busy.match(/aria-disabled="true"/g) || []).length,
  freeDisabled: (free.match(/aria-disabled="true"/g) || []).length,
  sweptBusy, sweptFree: __swept(), status: __raiseStatus.textContent
}}));
""",
            self.RAISE_PRELUDE + self.LIVE_RAISE_PRELUDE,
        )
        assert isinstance(out, dict)

        # Both rows draw a RAISE, and while one is in flight both read unavailable —
        # in the document the click found, and in every render that follows.
        self.assertEqual(2, out["rows"])
        self.assertEqual(2, out["busyDisabled"])
        self.assertEqual(["true", "true"], out["sweptBusy"])
        # And it lifts. A flag never cleared would leave the board permanently
        # unavailable after one raise, which is worse than the defect it fixes.
        self.assertEqual(0, out["freeDisabled"])
        self.assertEqual([None, None], out["sweptFree"])
        self.assertIn("Raise sent", out["status"])

    def test_a_render_landing_mid_raise_leaves_the_live_row_on_the_terminal_state(
        self,
    ) -> None:
        # The node the click is holding is not reliably the node the reader is
        # looking at. `renderNext` replaces `#app` wholesale, so a render landing
        # while the request is on the wire orphans it, and writing the answer to that
        # node alone left the live row painting `sending` — cursor:progress and the
        # warn border — until the next render, up to NEXT_FALLBACK_POLL_MS later,
        # while the live region beside it already said SENT. A cue that contradicts
        # the announcement is worse than the missing cue this lane started from,
        # and mid-action is the case DRC-4392 exists for.
        out = self._run_page_js(
            f"""
nextData = JSON.parse({json.dumps(json.dumps(self.RAISABLE_ROWS))});
let __release = null;
__fetchImpl = () => new Promise(resolve => {{ __release = resolve; }});
const detached = __raiseTarget();
__fire("click", {{target: detached, preventDefault(){{}}, stopPropagation(){{}}}});
await __settle();
__renderLive();
const mid = __sweptState();
__release({{ok: true, status: 200, json: async () => ({{focused: true}})}});
await __settle();
await __settle();
await __settle();
console.log(JSON.stringify({{
  mid, live: __sweptState(), busy: __swept(),
  detached: detached.dataset.nextRaiseState || null,
  status: __raiseStatus.textContent,
  nextRender: (__renderLive().match(/data-next-raise-state="sent"/g) || []).length
}}));
""",
            self.RAISE_PRELUDE + self.LIVE_RAISE_PRELUDE,
        )
        assert isinstance(out, dict)

        # The render did repaint the raising row from the map, and only that row.
        self.assertEqual(["sending", None], out["mid"])
        # And the answer reaches the row that is on the page, not only the orphan
        # the handler is still holding: both say the same thing at the same time.
        self.assertEqual(["sent", None], out["live"])
        self.assertEqual("sent", out["detached"])
        self.assertIn("Raise sent", out["status"])
        self.assertEqual([None, None], out["busy"])
        # The next render agrees with what the row already says rather than being
        # the first thing to say it.
        self.assertEqual(1, out["nextRender"])

    def test_a_render_landing_mid_copy_leaves_the_live_control_confirmed(self) -> None:
        # The identical orphaning on a far narrower window: the clipboard write is
        # awaited, and a render landing inside that await takes the control the click
        # found. Same mechanism, same answer — and the confirmation still belongs to
        # one control, so the command sibling beside it says nothing.
        out = self._run_page_js(
            """
const detached = {
  dataset: {nextCopySession: "sid-published", nextCopyHarness: "claude"},
  closest(selector){ return selector.includes("data-next-copy") ? this : null; }
};
__fire("click", {target: detached, preventDefault(){}, stopPropagation(){}});
await __settle();
const mid = __sweptCopy();
__releaseCopy();
await __settle();
await __settle();
console.log(JSON.stringify({
  mid, live: __sweptCopy(), detached: detached.dataset.nextCopyState || null,
  status: __copyStatus.textContent
}));
""",
            """
let __releaseCopy = null;
const navigator = {clipboard: {
  writeText(){ return new Promise(resolve => { __releaseCopy = resolve; }); }
}};
let __copyStatusText = "";
const __copyStatus = {
  setAttribute(){},
  set textContent(value){ __copyStatusText = String(value); },
  get textContent(){ return __copyStatusText; }
};
document.createElement = () => __copyStatus;
const __liveCopies = [
  {dataset: {nextCopySession: "sid-published", nextCopyHarness: "claude"}, attrs: {}},
  {dataset: {
    nextCopyCommand: "claude --resume 27d10654-1cb5-481e-8194-6ce868b91bb5",
    nextCopySession: "sid-published", nextCopyHarness: "claude"
  }, attrs: {}}
].map(control => Object.assign(control, {
  setAttribute(name, value){ this.attrs[name] = String(value); },
  removeAttribute(name){ delete this.attrs[name]; }
}));
__els.app = {
  innerHTML: "",
  querySelectorAll(selector){
    return selector === "[data-next-copy-session]" ? __liveCopies : [];
  },
  querySelector(){ return null; },
  insertAdjacentElement(){}
};
const __sweptCopy = () =>
  __liveCopies.map(control => control.attrs["data-next-copy-state"] || null);
""",
        )
        assert isinstance(out, dict)

        # Nothing is claimed while the write is still outstanding.
        self.assertEqual([None, None], out["mid"])
        self.assertEqual(["copied", None], out["live"])
        self.assertEqual("copied", out["detached"])
        self.assertIn("Copied session ID", out["status"])

    def test_the_second_click_is_refused_whichever_row_it_lands_on(self) -> None:
        # AC1 is a second row, not a second click on the first. The refusal is the
        # page's one flag over the daemon's one floor, so row B is refused while row
        # A is on the wire, and each row says its own answer rather than sharing one.
        # A real DOM also hands the same node back for a double-click, which two
        # fabricated targets cannot show: the row's own `sending` is overwritten by
        # its own refusal, and the request is still sent exactly once.
        out = self._run_page_js(
            f"""
nextData = JSON.parse({json.dumps(json.dumps(self.RAISABLE_ROWS))});
__fetchImpl = () => new Promise(() => {{}});
const rowA = __raiseTarget();
const rowB = Object.assign(__raiseTarget(), {{
  dataset: {{nextRaiseSession: "sid-elsewhere", nextRaiseHarness: "claude"}}
}});
__fire("click", {{target: rowA, preventDefault(){{}}, stopPropagation(){{}}}});
await __settle();
const sending = {{state: rowA.dataset.nextRaiseState, status: __raiseStatus.textContent}};
__fire("click", {{target: rowB, preventDefault(){{}}, stopPropagation(){{}}}});
await __settle();
const other = {{
  calls: __raiseCalls().length, a: rowA.dataset.nextRaiseState,
  b: rowB.dataset.nextRaiseState, status: __raiseStatus.textContent,
  live: __sweptState()
}};
__fire("click", {{target: rowA, preventDefault(){{}}, stopPropagation(){{}}}});
await __settle();
console.log(JSON.stringify({{
  sending, other, sameRow: rowA.dataset.nextRaiseState,
  sameRowCalls: __raiseCalls().length, sameRowLive: __sweptState()
}}));
""",
            self.RAISE_PRELUDE + self.LIVE_RAISE_PRELUDE,
        )
        assert isinstance(out, dict)

        # The accepted click is acknowledged. `nextRaiseState`'s guard is
        # `if(status && message)`, so an empty announcement here is silence for a
        # reader who has only the live region.
        self.assertEqual("sending", out["sending"]["state"])
        self.assertEqual("Raise requested", out["sending"]["status"])
        # Row B is refused, and says so on row B.
        self.assertEqual(1, out["other"]["calls"])
        self.assertEqual("throttled", out["other"]["b"])
        self.assertEqual("sending", out["other"]["a"])
        self.assertIn("too recent", out["other"]["status"])
        self.assertEqual(["sending", "throttled"], out["other"]["live"])
        # And the same row clicked twice overwrites its own cue rather than keeping
        # a `sending` the page has just refused to act on.
        self.assertEqual("throttled", out["sameRow"])
        self.assertEqual(1, out["sameRowCalls"])
        self.assertEqual(["throttled", "throttled"], out["sameRowLive"])

    def test_the_raised_row_keeps_saying_so_across_a_render_and_then_stops(self) -> None:
        # `renderNext` replaces `#app` wholesale on every revision and on a bare 20 s
        # interval, so the cue used to die of a clock rather than of anything the
        # reader did — and asymmetrically, since the live region is a sibling of
        # `#app` and survived. The cue is re-emitted from a stamped module map, and
        # the stamp is why: a row that read SENT for the rest of the run would still
        # say so after the session it names had ended (DRC-4392).
        out = self._run_page_js(
            f"""
nextData = JSON.parse({json.dumps(json.dumps(self.RAISABLE_ROWS))});
__fetchImpl = async () => ({{ok: true, status: 200, json: async () => ({{focused: true}})}});
__fire("click", {{target: __raiseTarget(), preventDefault(){{}}, stopPropagation(){{}}}});
await __settle();
await __settle();
await __settle();
const immediate = nextAttentionView(nextAttentionModel(nextData));
__setNow(1029);
const fresh = nextAttentionView(nextAttentionModel(nextData));
__setNow(1030);
const boundary = nextAttentionView(nextAttentionModel(nextData));
__setNow(1031);
const stale = nextAttentionView(nextAttentionModel(nextData));
console.log(JSON.stringify({{
  ttl: NEXT_CONTROL_STATE_TTL_MS, poll: NEXT_FALLBACK_POLL_MS,
  immediate: (immediate.match(/data-next-raise-state="sent"/g) || []).length,
  fresh: (fresh.match(/data-next-raise-state="sent"/g) || []).length,
  boundary: (boundary.match(/data-next-raise-state=/g) || []).length,
  stale: (stale.match(/data-next-raise-state=/g) || []).length,
  held: nextControlStates.size
}}));
""",
            self.RAISE_PRELUDE + self.LIVE_RAISE_PRELUDE,
        )
        assert isinstance(out, dict)

        # Longer than the idle render, read off the constant the render loop actually
        # uses rather than off a literal, so the cue's life is not decided by when the
        # next render happens to land.
        self.assertGreater(out["ttl"], out["poll"])
        self.assertEqual(1, out["immediate"])
        self.assertEqual(1, out["fresh"])
        # The TTL is a deadline, not a grace period: at exactly it, the cue is gone.
        # Which side of the boundary the operator sits on is a millisecond either
        # way, and pinning it is what stops the comparison drifting silently.
        self.assertEqual(0, out["boundary"])
        self.assertEqual(0, out["stale"])
        # Read, found stale, dropped. A map that only ever grew would be the
        # unbounded one this codebase does not ship.
        self.assertEqual(0, out["held"])

    # One session, and a click whose dataset is read off the control the page
    # actually renders. Writing that dataset by hand made the click key and the
    # render key agree by construction of the test, and their agreement is the
    # thing under test: drop an attribute from the control and the two stop
    # matching, so every control in the lane renders with no cue at all.
    COPY_CLICK_HELPERS = """
const session = {
  harness: "claude", sid: "sid-published",
  resume_id: "27d10654-1cb5-481e-8194-6ce868b91bb5"
};
const datasetOf = html => {
  const dataset = {};
  for(const [, name, value] of html.matchAll(/ data-next-([a-z-]+)="([^"]*)"/g)){
    dataset["next" + name.replace(/(^|-)([a-z])/g, (_, lead, c) => c.toUpperCase())] = value;
  }
  return dataset;
};
const click = dataset => __fire("click", {
  target: {dataset, closest(selector){
    return selector.includes("data-next-copy") ? {dataset} : null;
  }},
  preventDefault(){}, stopPropagation(){}
});
"""

    # An `#app` that answers the handler's lookups and sweeps nothing, so a test
    # reads the cue off the controls the render emits rather than off the DOM.
    COPY_STATUS_STUBS = """
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
"""

    def test_both_copy_controls_keep_their_confirmation_and_do_not_share_it(self) -> None:
        # The identical defect sat on the two siblings the issue never named. Fixing
        # the raise alone would leave three controls in one lane behaving two ways.
        # They share the lane and the live region, not the cue: copying the session id
        # is not proof the re-entry command was copied.
        out = self._run_page_js(
            self.COPY_CLICK_HELPERS
            + """
const rendered = {id: nextSessionCopyControl(session), cmd: nextSessionResumeControl(session)};
click(datasetOf(rendered.id));
await __settle();
const idOnly = {id: nextSessionCopyControl(session), cmd: nextSessionResumeControl(session)};
click(datasetOf(rendered.cmd));
await __settle();
const both = {id: nextSessionCopyControl(session), cmd: nextSessionResumeControl(session)};
__setNow(1031);
const stale = {id: nextSessionCopyControl(session), cmd: nextSessionResumeControl(session)};
console.log(JSON.stringify({rendered, idOnly, both, stale}));
""",
            "const navigator = {clipboard: {writeText(){ return Promise.resolve(); }}};\n"
            + self.COPY_STATUS_STUBS,
        )
        assert isinstance(out, dict)

        # Both halves of the key ride the control. Neither is pinned anywhere else,
        # and without the harness the click key and the render key cannot match.
        for name in ("id", "cmd"):
            with self.subTest(control=name):
                self.assertIn('data-next-copy-session="sid-published"', out["rendered"][name])
                self.assertIn('data-next-copy-harness="claude"', out["rendered"][name])
        copied = 'data-next-copy-state="copied"'
        self.assertIn(copied, out["idOnly"]["id"])
        self.assertNotIn(copied, out["idOnly"]["cmd"])
        self.assertIn(copied, out["both"]["id"])
        self.assertIn(copied, out["both"]["cmd"])
        self.assertNotIn(copied, out["stale"]["id"])
        self.assertNotIn(copied, out["stale"]["cmd"])

    def test_a_copy_that_failed_says_so_across_a_render_too(self) -> None:
        # Both halves of the cue outlive the render, not only the good one. A context
        # with no `navigator.clipboard` is the one where the reader most needs it to
        # stay put — plain HTTP is how this page is served, and the fallback there is
        # to read the value off the control by hand, so a render that dropped the cue
        # would leave nothing saying why the click did nothing.
        out = self._run_page_js(
            self.COPY_CLICK_HELPERS
            + """
click(datasetOf(nextSessionResumeControl(session)));
await __settle();
console.log(JSON.stringify({
  cmd: nextSessionResumeControl(session), id: nextSessionCopyControl(session),
  status: __copyStatus.textContent
}));
""",
            "const navigator = {};\n" + self.COPY_STATUS_STUBS,
        )
        assert isinstance(out, dict)

        self.assertIn('data-next-copy-state="failed"', out["cmd"])
        self.assertNotIn("data-next-copy-state", out["id"])
        self.assertIn("could not be copied", out["status"])

    def test_a_cue_belongs_to_one_harness_and_one_sid(self) -> None:
        # Session ids are unique per harness and nowhere else, and every other
        # session-keyed structure on this page keys on both (`nextSessionKey`). A
        # cue keyed on the bare sid would paint a Codex row because a Claude row
        # was raised.
        out = self._run_page_js(
            """
nextRememberControlState(nextControlStateKey("raise", "claude", "shared"), "sent");
const row = harness => nextSessionRaiseControl({harness, sid: "shared", focusable: true});
console.log(JSON.stringify({claude: row("claude"), codex: row("codex")}));
""",
            self.RAISE_PRELUDE,
        )
        assert isinstance(out, dict)

        self.assertIn('data-next-raise-state="sent"', out["claude"])
        self.assertNotIn("data-next-raise-state", out["codex"])

    def test_the_control_state_map_retires_its_oldest_rather_than_growing(self) -> None:
        # Every other module-level map here either refuses at a cap or retires on a
        # clock. A reader can click for as long as the tab is open, so this one does
        # both: the clock drops what is stale and the cap drops what is oldest.
        out = self._run_page_js(
            """
const key = index => nextControlStateKey("copy", "claude", `sid-${index}`);
const overflow = NEXT_CONTROL_STATE_LIMIT + 8;
for(let index = 0; index < overflow; index += 1){
  nextRememberControlState(key(index), "copied");
}
const held = {
  size: nextControlStates.size, limit: NEXT_CONTROL_STATE_LIMIT,
  oldest: nextControlState(key(0)), newest: nextControlState(key(overflow - 1))
};
// Touched again, then crowded by one. Oldest means least recently written, not
// first ever written, so the re-touched entry must outlive the one behind it.
nextRememberControlState(key(8), "copied");
nextRememberControlState(key(overflow), "copied");
console.log(JSON.stringify(Object.assign(held, {
  retouched: nextControlState(key(8)), behindIt: nextControlState(key(9))
})));
""",
            self.RAISE_PRELUDE,
        )
        assert isinstance(out, dict)

        self.assertEqual(out["limit"], out["size"])
        self.assertEqual("", out["oldest"])
        self.assertEqual("copied", out["newest"])
        self.assertEqual("copied", out["retouched"])
        self.assertEqual("", out["behindIt"])

    def test_a_refused_raise_and_an_unavailable_one_do_not_wear_the_same_look(self) -> None:
        # `throttled` shared one rule with `declined` and `failed`, which drew a
        # refusal that means "try again" as the two answers that mean "nothing more
        # to do from here". And a control unavailable because the page is busy is not
        # a control whose own raise came back refused (DRC-4390).
        answered = re.search(
            r'\.next-session-raise\[data-next-raise-state="declined"\],'
            r'\.next-session-raise\[data-next-raise-state="failed"\]\{([^}]*)\}',
            NEXT_STYLES,
        )
        throttled = re.search(
            r'\.next-session-raise\[data-next-raise-state="throttled"\],'
            r'\.next-session-raise\[data-next-raise-state="stale"\]\{([^}]*)\}',
            NEXT_STYLES,
        )
        busy = re.search(
            r'\.next-session-raise\[aria-disabled="true"\]\{([^}]*)\}',
            NEXT_STYLES,
        )
        sending = re.search(
            r'\.next-session-raise\[data-next-raise-state="sending"\]\{([^}]*)\}',
            NEXT_STYLES,
        )
        for name, rule in (
            ("answered", answered),
            ("throttled", throttled),
            ("busy", busy),
            ("sending", sending),
        ):
            with self.subTest(rule=name):
                self.assertIsNotNone(rule)
        assert answered is not None
        assert throttled is not None
        assert busy is not None
        assert sending is not None
        self.assertNotEqual(answered.group(1), throttled.group(1))
        self.assertNotEqual(answered.group(1), busy.group(1))
        self.assertNotEqual(throttled.group(1), busy.group(1))
        # Not colour alone: the cursor says the control will not act, for a reader
        # who cannot see the border change.
        self.assertIn("cursor:not-allowed", busy.group(1))
        # What each body has to say, not merely that the three differ. Reverting
        # `throttled` to the answered look left all three `assertNotEqual`s standing.
        # "Try again in a moment" is the warn line; the answered pair is the quiet
        # one, and a raise underway is the only state that says work is happening.
        self.assertIn("border-color:var(--amber)", throttled.group(1))
        self.assertIn("border-color:var(--line2)", answered.group(1))
        # `stale` shares that rule rather than bringing a fourth look, and appears
        # in no other: a second rule would win by order and quietly reclassify a
        # refusal the reader can act on as one they cannot. The announcement is
        # what says which of the two it is — a border cannot carry "reload the
        # page" (DRC-4396).
        self.assertEqual(1, NEXT_STYLES.count('data-next-raise-state="stale"'))
        self.assertIn("cursor:progress", sending.group(1))
        self.assertIn("border-color:var(--amber)", sending.group(1))
        # Same specificity, so the later rule wins: the row that is actually raising
        # keeps `sending` rather than reading as one of the rows waiting on it.
        self.assertLess(NEXT_STYLES.index(busy.group(0)), NEXT_STYLES.index(sending.group(0)))

    def test_the_irreversible_control_has_its_own_look_and_a_focus_ring(self) -> None:
        # `.next-session-copy` has no `:focus-visible` rule, which DRC-4381 left
        # standing; the irreversible control is not going to be the third to inherit
        # that gap.
        # The whole declaration, not the property name: stopping at the colon let
        # `outline:none` satisfy a test named for the ring (DRC-4017 review).
        self.assertIn(
            ".next-session-raise:focus-visible{outline:2px solid var(--accent);outline-offset:2px}",
            NEXT_STYLES,
        )
        copy = re.search(r"\.next-session-copy\{([^}]*)\}", NEXT_STYLES)
        raised = re.search(r"\.next-session-raise\{([^}]*)\}", NEXT_STYLES)
        self.assertIsNotNone(copy)
        self.assertIsNotNone(raised)
        assert copy is not None
        assert raised is not None
        self.assertNotEqual(copy.group(1), raised.group(1))
        self.assertIn("background:transparent", copy.group(1))
        self.assertNotIn("background:transparent", raised.group(1))

    def test_breadcrumb_segments_mark_current_location_and_escape_walks_up(self) -> None:
        out = self._run_page_js(
            """
const sessionHtml = __els.app.innerHTML;
navigateNext({view: "session", project: "recce", session: "019a"});
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
const project = {...nextRoute};
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
const projects = {...nextRoute};
__fire("keydown", {key: "Escape", target: {tagName: "BODY"}, preventDefault(){}});
console.log(JSON.stringify({sessionHtml, project, projects, stayed: nextRoute}));
""",
            'location.hash = "#n=session:recce:019a";\n__els.app = {innerHTML: ""};\n',
        )

        self.assertIn('<a href="#n=sessions">Sessions</a>', out["sessionHtml"])
        self.assertIn('<a href="#n=projects" aria-current="page">Projects</a>', out["sessionHtml"])
        self.assertIn('<a class="next-crumb" href="#n=project:recce">recce</a>', out["sessionHtml"])
        self.assertIn("recce", out["sessionHtml"])
        self.assertIn('<span aria-current="page">Session</span>', out["sessionHtml"])
        self.assertNotIn("<span>019a</span>", out["sessionHtml"])
        self.assertEqual(
            {"view": "project", "project": "recce", "session": None},
            out["project"],
        )
        self.assertEqual(
            {"view": "projects", "project": None, "session": None},
            out["projects"],
        )
        self.assertEqual(out["projects"], out["stayed"])

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
        self.assertEqual("#n=projects", out["repaired"])

    def test_shortcuts_select_matching_top_level_routes_and_ignore_retired_dashboard_key(
        self,
    ) -> None:
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
            'location.search = "?all=1";\nlocation.hash = "#n=project:recce";\n'
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
            {"view": "attention", "project": None, "session": None},
            out["attention"]["route"],
        )
        self.assertEqual("#n=attention", out["attention"]["hash"])
        self.assertIn('<h1 tabindex="-1">Attention</h1>', out["attention"]["html"])
        self.assertEqual([], out["assigned"])
        self.assertEqual("?all=1", out["search"])
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
                    "details[data-pc-disclosure]",
                    # The row controls are swept by the same fixed selectors the
                    # render and the state stamp use, and the key is compared
                    # against a dataset rather than interpolated into a selector —
                    # which is what the hostile key above is here to prove.
                    "[data-next-raise-session]",
                    "[data-next-copy-session]",
                    "[data-next-session]",
                    "[data-next-subject-key]",
                    "[data-next-attention-toggle]",
                    "[data-next-attention-section]",
                    ".next-attention h1",
                    # One entry for every named control, rather than a new one
                    # per rescue. The key it compares comes off the dataset.
                    "[data-next-focus]",
                    # Read before the render discards it, same discipline.
                    "[data-next-draft]",
                }
                for selector in out["selectors"]
            ),
            out["selectors"],
        )

    def test_focus_on_a_disclosure_summary_survives_a_render(self) -> None:
        # The fourth and last container the render used to drop. #288 kept the
        # <details> OPEN across a render but not the focus on its summary, and
        # avoided introducing the loss at click time only by declining to
        # re-render in that handler. An interval render still displaced it, and
        # the live lane fires one whenever anything on the machine moves.
        out = self._run_page_js(
            """
nextData = {generated: 1000, sessions: [], asks: []};
nextAttention = nextAttentionModel(nextData);
document.activeElement = {focusKey: "attention-coverage"};
renderNext();
console.log(JSON.stringify({focusCalls: __focusCalls, selectors: __selectors}));
""",
            """
let __focusCalls = [];
let __selectors = [];
__els.app = {
  innerHTML: "",
  querySelectorAll(selector){
    __selectors.push(selector);
    if(selector === "[data-next-focus]") return ["attention-coverage", "session-source-coverage"].map(id => ({
      dataset: {nextFocus: id},
      contains(active){ return active && active.focusKey === id; },
      focus(){ __focusCalls.push(`focus:${id}`); document.activeElement = this; }
    }));
    return [];
  },
  querySelector(){ return null; }
};
""",
        )
        self.assertEqual(["focus:attention-coverage"], out["focusCalls"])
        # One fixed selector for every family, compared against a dataset. The
        # allowlist test above is what stops this becoming a fifth bespoke lane.
        self.assertIn("[data-next-focus]", out["selectors"])

    def test_the_generic_focus_lane_never_interpolates_the_key(self) -> None:
        # Same proof the row-control lane carries: a hostile identity must reach
        # a dataset comparison and never a querySelectorAll argument.
        hostile = 'attention"] , [data-next-route] "'
        out = self._run_page_js(
            """
nextData = {generated: 1000, sessions: [], asks: []};
nextAttention = nextAttentionModel(nextData);
document.activeElement = {focusKey: __hostile};
renderNext();
console.log(JSON.stringify({focusCalls: __focusCalls, selectors: __selectors}));
""",
            """
const __hostile = __HOSTILE__;
let __focusCalls = [];
let __selectors = [];
__els.app = {
  innerHTML: "",
  querySelectorAll(selector){
    __selectors.push(selector);
    if(selector === "[data-next-focus]") return [{
      dataset: {nextFocus: __hostile},
      contains(active){ return active && active.focusKey === __hostile; },
      focus(){ __focusCalls.push("focus:hostile"); document.activeElement = this; }
    }];
    return [];
  },
  querySelector(){ return null; }
};
""".replace("__HOSTILE__", json.dumps(hostile)),
        )
        self.assertEqual(["focus:hostile"], out["focusCalls"])
        self.assertNotIn(hostile, "".join(out["selectors"]))

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

    def test_focused_row_control_survives_refresh(self) -> None:
        # DRC-4392 made the cue survive a render; focus did not. Observed: focus on
        # a RAISE, then a refresh, and `document.activeElement` was the row's route
        # link — the session branch's fallback, reached because nothing re-targeted
        # the control. The live lane fires a revision whenever anything on the
        # machine moves, so a keyboard reader working the queue was displaced
        # continuously (DRC-4396).
        out = self._run_page_js(
            """
const payload = generated => ({
  generated,
  sessions: [0, 1].map(index => ({
    harness: "claude", sid: `owner-${index}`, project: `project-${index}`,
    state: "needs_input"
  }))
});
nextData = payload(1000);
nextAttention = nextAttentionModel(nextData);
const focusCallsFor = active => {
  __focusCalls = [];
  document.activeElement = active;
  renderNext();
  return [...__focusCalls];
};
console.log(JSON.stringify({
  raise: focusCallsFor({controlKey: "raise\\u0000claude\\u0000owner-1"}),
  copy: focusCallsFor({controlKey: "copy\\u0000claude\\u0000owner-1"}),
  command: focusCallsFor({controlKey: "command\\u0000claude\\u0000owner-1"}),
  row: focusCallsFor({sessionId: "owner-1"})
}));
""",
            """
let __focusCalls = [];
// Each row carries its three controls, keyed the way the control-state map keys
// them, plus the route link the session branch falls back to.
const __control = (lane, sid, dataset) => ({
  dataset,
  key: `${lane}\\u0000claude\\u0000${sid}`,
  contains(active){ return Boolean(active) && active.controlKey === this.key; },
  focus(){ __focusCalls.push(`${lane}:${sid}`); document.activeElement = this; }
});
const __controls = sid => [
  __control("raise", sid, {nextRaiseSession: sid, nextRaiseHarness: "claude"}),
  __control("copy", sid, {nextCopySession: sid, nextCopyHarness: "claude"}),
  __control("command", sid, {
    nextCopySession: sid, nextCopyHarness: "claude", nextCopyCommand: `claude --resume ${sid}`
  })
];
__els.app = {
  innerHTML: "",
  querySelectorAll(selector){
    if(selector === "[data-next-raise-session]"){
      return ["owner-0", "owner-1"].flatMap(sid =>
        __controls(sid).filter(control => control.dataset.nextRaiseSession));
    }
    if(selector === "[data-next-copy-session]"){
      return ["owner-0", "owner-1"].flatMap(sid =>
        __controls(sid).filter(control => control.dataset.nextCopySession));
    }
    if(selector === "[data-next-session]") return ["owner-0", "owner-1"].map(sid => ({
      dataset: {nextSession: sid, nextHarness: "claude"},
      contains(active){
        return Boolean(active) &&
          (active.sessionId === sid || String(active.controlKey || "").endsWith(sid));
      },
      querySelector(inner){
        return inner === ".next-operation-route"
          ? {focus(){ __focusCalls.push(`route:${sid}`); }}
          : null;
      },
      focus(){ __focusCalls.push(`session:${sid}`); }
    }));
    return [];
  },
  querySelector(){ return null; },
  insertAdjacentElement(){}
};
""",
        )
        assert isinstance(out, dict)

        # The control the reader was on, not the row it sits in.
        self.assertEqual(["raise:owner-1"], out["raise"])
        self.assertEqual(["copy:owner-1"], out["copy"])
        self.assertEqual(["command:owner-1"], out["command"])
        # And the row branch is untouched where no control held focus.
        self.assertEqual(["route:owner-1"], out["row"])

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

    def test_the_subagent_count_includes_every_observed_subagent(self) -> None:
        # Observed includes quiet and unmeasured children; running requires active evidence.
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            """
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  window_hours: 24,
  summary: {working: 1, needs_input: 0, active_sessions: 1},
  sessions: [
    {project: "recce", state: "working", subagents: [
      {name: "live-a", active: true, parent: null},
      {name: "lens-a", active: true, parent: "live-a"},
      {name: "done-a", active: false, parent: null},
      {name: "never-started", active: false, parent: null},
      {name: "unmeasured"}
    ]}
  ]
})});
""",
        )

        self.assertIn("0 running · 5 subagents observed</span>", out)
        self.assertNotIn("subagents running", out)

    def test_a_single_observed_subagent_reads_in_the_singular(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            """
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  window_hours: 24,
  summary: {working: 1, needs_input: 0, active_sessions: 1},
  sessions: [
    {project: "recce", state: "working", subagents: [
      {name: "live-a", active: true, parent: null}
    ]}
  ]
})});
""",
        )

        self.assertIn("0 running · 1 subagent observed</span>", out)
        self.assertNotIn("1 subagents", out)

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
    {project: "recce", state: "working", active: true, subagents: [{}, {}]},
    {project: "recce", state: "needs_input", active: true, subagents: [{}]},
    {project: "cargento", state: "idle", subagents: []},
    {project: "cargento", state: "idle", subagents: []}
  ]
})});
""",
        )

        self.assertIn(
            '<span class="next-running next-live">'
            '<span class="next-status-dot" aria-label="live">●</span> '
            "1 running · 3 subagents observed</span>",
            out,
        )
        self.assertIn(
            '<button type="button" class="next-gate" data-next-action="needs-input">'
            "1 reported block</button>",
            out,
        )
        self.assertNotIn("4 running", out)
        self.assertIn("<h1>Projects</h1>", out)

    def test_exact_request_state_skew_is_counted_in_the_header_block_total(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            """
location.hash = "#n=sessions";
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

    def test_all_projects_header_counts_observed_children_including_finished_teammates(
        self,
    ) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            """
location.hash = "#n=project:recce";
__els.app = {innerHTML: ""};
__fetchImpl = async url => ({ok: true, json: async () =>
  String(url).startsWith("/api/project-context")
    ? {semantic:{projections:{command_attention:[],command_attention_coverage:{
        state:"complete",scanned:1,total:1,omitted:0,source:"bounded scan"}}}}
    : ({window_hours:24,summary:{working:1,needs_input:0},
      harnesses:[{key:"codex",label:"Codex"}],sessions:[{
        sid:"root",harness:"codex",project:"recce",project_key:"org/recce",
        state:"working",active:true,last_activity:10,
        subagents:[{name:"Ohm",active:null},{name:"Finished",active:false}],
        subagent_hierarchy:[{name:"Ohm",observer_sid:"child-ohm",depth:1}]
      }]})});
""",
        )

        self.assertIn("All projects · 1 running · 2 subagents observed", out)
        self.assertNotIn("0 subagents", out)
        self.assertIn('<h1 class="next-project-detail-name">recce</h1>', out)
        self.assertNotIn("org/recce", out)

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
        self.assertIn('<h1 tabindex="-1">Attention</h1>', out["html"])

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
            "0 running · 0 subagents observed</span>",
            out,
        )
        self.assertNotIn('class="next-gate"', out)
        self.assertNotIn('data-next-action="needs-input"', out)
        self.assertIn('<nav aria-label="Primary"', out)
        self.assertIn('href="#n=projects"', out)
        self.assertIn('href="#n=sessions"', out)
        self.assertIn("<h1>Projects</h1>", out)
        self.assertNotIn("dashboard mode", out)
        self.assertNotIn('data-next-action="dashboard"', out)

    def test_poll_forwards_only_the_all_flag(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify({calls: __fetchCalls.map(call => call[0]), periods: __intervalPeriods()}));
""",
            """
location.search = "?all=1&view=ignored";
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
location.search = "?view=ignored";
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
location.hash = "#n=attention";
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
    {project: "recce", sid: "one", state: "working", active: true, subagents: []},
    {project: "cargento", sid: "two", state: "working", active: true, subagents: []}
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
    sessions: [{project: "recce", sid: "one", state: "working", active: true, subagents: []}]
  })};
};
""",
        )

        self.assertEqual(1, out["during"]["calls"])
        self.assertEqual(2, out["during"]["failures"])
        self.assertEqual(1000, out["during"]["generated"])
        self.assertIn('data-next-action="retry-refresh" disabled', out["during"]["html"])
        self.assertIn(
            'aria-label="live">●</span> 1 running',
            out["during"]["html"],
        )
        self.assertNotIn('data-next-state="stalled"', out["recovered"])
        self.assertIn('aria-label="live">●</span> 2 running', out["recovered"])
        self.assertEqual(0, out["recoveredFailures"])
        self.assertEqual(2000, out["recoveredGenerated"])

    def test_a_history_reset_is_reported_with_which_reset_it_was(self) -> None:
        out = self._run_page_js(
            """
const rendered = {};
for(const reason of ["unreadable", "version", "absent"]){
  nextData = {
    summary: {working: 0, needs_input: 0}, sessions: [], asks: [],
    ...(reason === "absent" ? {} : {history_reset: reason})
  };
  renderNext();
  rendered[reason] = __els.app.innerHTML;
}
console.log(JSON.stringify(rendered));
""",
            '__els.app = {innerHTML: ""};\n',
        )
        assert isinstance(out, dict)

        for reason in ("unreadable", "version"):
            with self.subTest(reason=reason):
                self.assertIn('data-next-state="history-reset"', out[reason])
        # The two literals must not render the same sentence. A corruption reset
        # may be the reader's disk while a version reset is ours (D1), so a header
        # identical for both would discharge the contract's clause and lose the
        # distinction the ruling exists for.
        self.assertNotEqual(out["unreadable"], out["version"])
        self.assertNotIn("history-reset", out["absent"])

    def test_an_unknown_history_reset_literal_renders_no_notice(self) -> None:
        # The field is untrusted: it reaches the page from a store any local
        # process could have written. An unrecognised reason draws nothing rather
        # than inventing a sentence about it.
        out = self._run_page_js(
            """
nextData = {
  summary: {working: 0, needs_input: 0}, sessions: [], asks: [],
  history_reset: "<img src=x onerror=alert(1)>"
};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            '__els.app = {innerHTML: ""};\n',
        )
        assert isinstance(out, str)

        self.assertNotIn("history-reset", out)
        self.assertNotIn("onerror", out)


if __name__ == "__main__":
    unittest.main()
