from __future__ import annotations

import json
import re
import shutil
import unittest
from typing import Any

from .page_harness import APP_JS, PAGE_TEXT, STYLES, PageJsHarness


class CalmModeTest(PageJsHarness):
    """The calm display mode and the switch between it and the regular view.

    Calm mode renders the same ``/api/data`` payload as a dense ledger. These
    execute the shipped `app.js`: every assertion is about what the page does
    with a payload, not about the assembled document's source text.
    """

    # Globals the page reads at load (localStorage) or feature-detects
    # (navigator.clipboard), plus a hand-fired setTimeout so the transient
    # "copied" label clears deterministically instead of after a real 1.4s.
    @staticmethod
    def prelude(saved: str | None = None, *, clipboard: str = "none") -> str:
        seed = "{}" if saved is None else json.dumps({"cargento.displayMode": saved})
        clip = {
            "none": "const navigator = {};",
            "ok": (
                "let __wrote = [];\nconst navigator = {clipboard: {writeText(s){"
                " __wrote.push(s); return Promise.resolve(); }}};"
            ),
            "denied": (
                "const navigator = {clipboard: {writeText(){"
                ' return Promise.reject(new Error("denied")); }}};'
            ),
        }[clipboard]
        return f"""
let __store = {seed};
const localStorage = {{
  getItem(k){{ return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; }},
  setItem(k, v){{ __store[k] = String(v); }}
}};
{clip}
let __timers = [];
const setTimeout = fn => {{ __timers.push(fn); return __timers.length; }};
const __tick = () => {{ const t = __timers; __timers = []; t.forEach(f => f()); }};
"""

    # `mk` fills in every field base_session() ships, so a test only states
    # what it is exercising.
    FIXTURE = """
let __focused = null;
// Every [data-calm] control in the rendered markup, as something that answers
// getAttribute() and focus() the way a real element would.
const __controls = () => [...__els.app.innerHTML.matchAll(
    /data-calm="([^"]*)"(?: data-arg="([^"]*)")?/g)].map(m => ({
  getAttribute: a => a === "data-calm" ? m[1]
    : (a === "data-arg" ? (m[2] === undefined ? null : m[2]) : null),
  focus(){ __focused = m[1] + ":" + (m[2] === undefined ? "" : m[2]); }
}));
__els.app = {innerHTML: "", className: "", querySelectorAll: () => __controls()};
let __scrollTop = 0;
let __revealed = 0;
// Selector-aware on purpose: a stub that answers every selector makes
// "the cursor was scrolled into view" pass even when the page asked for the
// wrong element, or for nothing at all.
__els["cm-body"] = {
  get scrollTop(){ return __scrollTop; }, set scrollTop(v){ __scrollTop = v; },
  querySelector(sel){
    if(sel !== ".cm-row.focus") return null;
    if(!__els.app.innerHTML.includes('class="cm-row focus')) return null;
    return {scrollIntoView(){ __revealed++; }};
  }
};
const mk = o => Object.assign({
  harness: "claude", session: "1234abcd", sid: "1234abcd", project: "repo/proj",
  title: null, last_prompt: "", state: "idle", state_detail: "awaiting your message",
  active: false, last_activity: 99000, rate_per_min: 0, total: 0, done: 0, open: 0,
  progress_pct: 0, eta_h: null, turn: null, subagents: [], tasks: [], spacedock: null
}, o);
const payload = sessions => ({
  generated: 100000, window_hours: 24, show_all: false, native_notify: "osascript",
  harnesses: [{key: "claude", label: "Claude Code", discovered: true, error: null},
              {key: "codex", label: "Codex", discovered: false, error: null}],
  summary: {needs_input: 1, working: 1, rate_per_min: 1234, active_sessions: 2,
            open_tasks: 1, progress_pct: 50, total_tasks: 2, total_done: 1},
  sessions
});
const blocked = mk({sid: "aaa1", session: "aaa1", title: "Approve deploy?",
  state: "needs_input", active: true, last_activity: 99700, blocked_since: 99700,
  state_detail: "open question (AskUserQuestion), waiting 5m"});
const busy = mk({sid: "bbb2", session: "bbb2", harness: "codex", project: "repo/other",
  title: "Migrate warehouse sync", state: "working", active: true,
  state_detail: "running Bash", last_activity: 99990, rate_per_min: 2010,
  turn: {elapsed_h: "20m", eta_h: "39m", pct: 34, long: true},
  subagents: ["Final whole-branch review"], last_prompt: "migrate the sync",
  tasks: [{status: "completed", subject: "Map every call site", activeForm: null},
          {status: "in_progress", subject: "Convert chain", activeForm: "Converting chain"},
          {status: "pending", subject: "Re-run suite", activeForm: null}]});
const quiet = mk({sid: "ccc3", session: "ccc3", title: "Old thing", last_activity: 90000});
const board = () => payload([blocked, busy, quiet]);
const rows = () => (__els.app.innerHTML.match(/class="cm-row/g) || []).length;
// A row is identified by (harness, sid) — the same pair sessKey() builds.
const K = (harness, sid) => harness + ":" + sid;
"""

    def run_calm(self, checks: str, *, saved: str = "calm", clipboard: str = "none") -> Any:
        return self._run_page_js(
            self.FIXTURE + checks, prelude=self.prelude(saved, clipboard=clipboard)
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_display_switch_persists_and_is_bound_to_c_in_both_modes(self) -> None:
        checks = """
const out = {};
out.startedCalm = displayMode;                    // seeded from localStorage
render(board());
out.calmClass = __els.app.className;
out.calmFrame = __els.app.innerHTML.includes("cm-frame");
out.switchShown = __els.app.innerHTML.includes('data-calm="mode" data-arg="calm"' +
  ' aria-pressed="true"');

// `c` leaves calm, and the switch is still there to come back with.
__fire("keydown", {key: "c", target: {}, preventDefault(){}});
out.afterKey = displayMode;
out.stored = __store["cargento.displayMode"];
out.regularClass = __els.app.className;
out.regularKeepsSwitch = __els.app.innerHTML.includes('class="modebar"');
out.regularKeepsTiles = __els.app.innerHTML.includes('class="tile"');
out.noFrameInRegular = !__els.app.innerHTML.includes("cm-frame");

// ...and back again, this time by clicking the segment.
calmAction("mode", "calm");
out.clickedBack = displayMode;
out.storedBack = __store["cargento.displayMode"];

// A value neither mode is ignored rather than blanking the page.
calmAction("mode", "sideways");
out.rejectsJunk = displayMode;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual("calm", out["startedCalm"], "saved mode not honoured on load")
        self.assertEqual("wrap calm", out["calmClass"])
        self.assertTrue(out["calmFrame"])
        self.assertTrue(out["switchShown"])
        self.assertEqual("regular", out["afterKey"], "`c` did not leave calm mode")
        self.assertEqual("regular", out["stored"], "the switch was not persisted")
        self.assertEqual("wrap", out["regularClass"])
        self.assertTrue(out["regularKeepsSwitch"], "no way back to calm from regular")
        self.assertTrue(out["regularKeepsTiles"], "regular mode lost its hero tiles")
        self.assertTrue(out["noFrameInRegular"])
        self.assertEqual("calm", out["clickedBack"])
        self.assertEqual("calm", out["storedBack"])
        self.assertEqual("calm", out["rejectsJunk"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_page_still_loads_when_storage_is_unavailable(self) -> None:
        # Private browsing and sandboxed contexts throw on localStorage access.
        checks = """
__els.app = {innerHTML: "", className: ""};
const d = {generated: 1000, window_hours: 24, show_all: false, native_notify: "",
  harnesses: [], sessions: [],
  summary: {needs_input: 0, working: 0, rate_per_min: 0, active_sessions: 0,
            open_tasks: 0, progress_pct: 0, total_tasks: 0, total_done: 0}};
render(d);
setDisplayMode("calm");
console.log(JSON.stringify({
  mode: displayMode, rendered: __els.app.innerHTML.includes("cm-frame")}));
"""
        # No prelude at all: neither localStorage nor navigator exists.
        out = self._run_page_js(checks)
        self.assertEqual("calm", out["mode"], "storage failure blocked the switch")
        self.assertTrue(out["rendered"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_ledger_lists_every_session_exactly_once(self) -> None:
        # A ledger that silently drops a session is worse than no ledger.
        checks = """
const out = {};
render(board());
const h = __els.app.innerHTML;
out.rows = rows();
out.perSession = [K("claude", "aaa1"), K("codex", "bbb2"), K("claude", "ccc3")]
  .map(k => (h.match(new RegExp('data-arg="' + k + '"', "g")) || []).length);
out.note = h.includes("showing all 3");
// The session count lives once, in the filter-aware `showing …` note. The
// footer carries what the note does not, and pluralizes.
out.footer = h.includes("1 harness · 1,234 tok/min");
out.footerHasNoCount = !h.includes("3 sessions");
out.legend = [h.includes("1 needs you"), h.includes("1 working"), h.includes("1 idle")];
// Column values come straight from the payload.
out.doing = h.includes("open question (AskUserQuestion), waiting 5m");
// Only the project may be truncated; the session id identifies the row.
out.where = h.includes('class="cm-proj">repo/other</span><span class="cm-sess">· bbb2<');
// Two columns, one unit each: `rate` for what the request is producing,
// `idle / wait` for how long the session has sat still. Each is empty on the
// buckets it does not describe, so neither mixes units down its length.
out.metrics = [">5m<", ">2,010 /m<", ">2h 46m<"].map(m => h.includes(m));
out.headings = [">rate<", ">idle / wait<"].map(m => h.includes(m));
out.noMixedHeading = !h.includes(">signal<") && !h.includes(">turn<");
// Progress bar only for a working session with a turn percentage, and it now
// sits inside the rate cell rather than paying for a column of its own.
out.bars = (h.match(/class="cm-track"/g) || []).length;
out.barInRateCell = /class="cm-rate">[\\s\\S]*?class="cm-track"/.test(h);
out.barWidth = h.includes("width:34%");
// An unrecognised state is still a row, in the idle bucket.
render(payload([mk({sid: "z", session: "z", state: "banana"})]));
out.unknownState = rows();
out.unknownIdle = __els.app.innerHTML.includes("1 idle");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(3, out["rows"])
        # Each row carries its sid twice: the row itself and its `copy id` button.
        self.assertEqual([2, 2, 2], out["perSession"])
        self.assertTrue(out["note"])
        self.assertTrue(out["footer"], "footer counts disagree with the payload")
        self.assertTrue(out["footerHasNoCount"], "the session count is still duplicated")
        self.assertEqual([True, True, True], out["legend"])
        self.assertTrue(out["doing"])
        self.assertTrue(out["where"])
        self.assertEqual([True, True, True], out["metrics"])
        self.assertEqual([True, True], out["headings"])
        self.assertTrue(out["noMixedHeading"], "a mixed-unit column heading came back")
        self.assertEqual(1, out["bars"], "only a working turn should draw a progress bar")
        self.assertTrue(out["barInRateCell"], "the progress bar left the rate cell")
        self.assertTrue(out["barWidth"])
        self.assertEqual(1, out["unknownState"], "a state the page does not know dropped a row")
        self.assertTrue(out["unknownIdle"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_flags_use_only_signals_the_payload_carries(self) -> None:
        # The design fixture also flagged "stalled" and "failed". The server has
        # no detector for either, so calm mode must not invent them.
        checks = """
const out = {};
render(board());
calmAction("open", "claude:aaa1");
calmAction("open", "codex:bbb2");
calmAction("open", "claude:ccc3");
const each = k => { calmAction("open", k); const h = __els.app.innerHTML;
  calmAction("open", k); return h; };
const hb = each(K("claude", "aaa1")), hw = each(K("codex", "bbb2")),
      hq = each(K("claude", "ccc3"));
out.blockedFlag = hb.includes(">your call<");
out.blockedWhy = hb.includes("Blocked on you for 5m");
out.longFlag = hw.includes(">long turn<");
out.longWhy = hw.includes("This request is running long (or estimated to).");
out.staleFlag = hq.includes(">stale<");
out.staleWhy = hq.includes("No activity for 2h 46m");
out.noInvented = !/&gt;stalled&lt;|>stalled<|>failed</.test(hb + hw + hq);
// A working session inside the long-turn threshold carries no flag.
render(payload([mk({sid: "s", session: "s", state: "working", active: true,
  last_activity: 99999, turn: {elapsed_h: "2m", eta_h: "3m", pct: 40, long: false}})]));
out.shortTurnUnflagged = !__els.app.innerHTML.includes('class="cm-flag"');
out.flagChipZero = __els.app.innerHTML.includes("◆ 0 flagged");
// An idle session inside the stale threshold carries no flag either.
render(payload([mk({sid: "t", session: "t", last_activity: 99000})]));
out.freshIdleUnflagged = !__els.app.innerHTML.includes('class="cm-flag"');
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["blockedFlag"])
        self.assertTrue(out["blockedWhy"])
        self.assertTrue(out["longFlag"])
        self.assertTrue(out["longWhy"], "calm mode reworded the long-turn signal")
        self.assertTrue(out["staleFlag"])
        self.assertTrue(out["staleWhy"])
        self.assertTrue(out["noInvented"], "flagged a signal the payload cannot support")
        self.assertTrue(out["shortTurnUnflagged"])
        self.assertTrue(out["flagChipZero"])
        self.assertTrue(out["freshIdleUnflagged"])

    def test_the_long_turn_wording_has_exactly_one_source(self) -> None:
        # The ⚠️ tooltip and the calm flag explanation are the same sentence;
        # two copies is how they drift apart.
        self.assertIn("const LONG_TURN_NOTE =", APP_JS)
        self.assertEqual(
            1,
            APP_JS.count("This request is running long (or estimated to)."),
            "the long-turn sentence is duplicated instead of shared",
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_filters_and_orderings_agree_with_the_counts_they_advertise(self) -> None:
        checks = """
const out = {};
render(board());
// Attention order puts the blocker first, then the warning, then the quiet row.
const order = h => [...h.matchAll(/data-arg="[a-z]+:(aaa1|bbb2|ccc3)" role="button"/g)]
  .map(m => m[1]);
out.attention = order(__els.app.innerHTML);
calmAction("sort", "recent");
out.recent = order(__els.app.innerHTML);
out.recentPressed = __els.app.innerHTML.includes('data-arg="recent" aria-pressed="true"');
calmAction("sort", "repo");
out.repoDividers = (__els.app.innerHTML.match(/class="cm-div"/g) || []).length;
out.repoLabels = ["repo/other", "repo/proj"].map(p =>
  __els.app.innerHTML.indexOf('cm-div-k">' + p));
out.repoRows = rows();
calmAction("sort", "attention");

// A legend chip filters to its own bucket and reports the narrowing.
calmAction("open", "codex:bbb2");
calmCursorKey = "codex:bbb2";
calmAction("state", "needs");
out.filterResetsRow = [calmOpenKey, calmCursorKey];
out.needsOnly = [rows(), __els.app.innerHTML.includes("showing 1 of 3")];
out.clearOffered = __els.app.innerHTML.includes('data-calm="clear"');
calmAction("state", "needs");
out.chipIsAToggle = [calmStateOnly, rows()];

// The flagged chip narrows to flagged rows; every board row is flagged here.
calmAction("open", "codex:bbb2");
calmAction("flag", null);
out.flagFilterResetsRow = [calmOpenKey, calmCursorKey];
out.flagged = [calmFlagOnly, rows()];
calmAction("clear", null);
out.cleared = [calmFlagOnly, calmStateOnly, rows()];

// A filter that matches nothing offers its own way out.
render(payload([busy]));
calmAction("state", "idle");
const empty = __els.app.innerHTML;
out.emptyState = empty.includes("Nothing matches this filter")
  && empty.includes("Show all 1");
out.emptyHasNoRows = rows();
calmAction("clear", null);
out.recovered = rows();

// No sessions at all is a different message, with the window and the escape.
render(payload([]));
out.noData = __els.app.innerHTML.includes("No session activity in the last 24h")
  && __els.app.innerHTML.includes('href="?all=1"');
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(["aaa1", "bbb2", "ccc3"], out["attention"])
        self.assertEqual(["bbb2", "aaa1", "ccc3"], out["recent"], "recent order is not by age")
        self.assertTrue(out["recentPressed"])
        self.assertEqual(2, out["repoDividers"])
        self.assertLess(out["repoLabels"][0], out["repoLabels"][1], "repo groups not sorted")
        self.assertEqual(3, out["repoRows"], "grouping lost a row")
        self.assertEqual([None, None], out["filterResetsRow"], "a filter left a row expanded")
        self.assertEqual([None, None], out["flagFilterResetsRow"])
        self.assertEqual([1, True], out["needsOnly"])
        self.assertTrue(out["clearOffered"])
        self.assertEqual([None, 3], out["chipIsAToggle"])
        self.assertEqual([True, 3], out["flagged"])
        self.assertEqual([False, None, 3], out["cleared"])
        self.assertTrue(out["emptyState"])
        self.assertEqual(0, out["emptyHasNoRows"])
        self.assertEqual(1, out["recovered"])
        self.assertTrue(out["noData"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_row_order_does_not_churn_between_polls(self) -> None:
        # A row that swaps places under the cursor is worse than a row in the
        # wrong place. Every ordering has to be a function of things that do not
        # change while the reader is reading: collect() makes the same call.
        checks = """
const out = {};
// Eight sessions with ages spread across minute boundaries, plus three that
// are actively generating (their last_activity advances with every poll).
const many = [];
for(let i = 0; i < 8; i++){
  many.push(mk({sid: "idle-" + i, session: "idle-" + i,
    project: "repo/p" + (i % 3), last_activity: 100000 - 59 - i * 61}));
}
for(let i = 0; i < 3; i++){
  many.push(mk({sid: "work-" + i, session: "work-" + i, state: "working",
    active: true, project: "repo/p" + (i % 3), last_activity: 99990 + i,
    rate_per_min: 100 * i}));
}
// What a real poll looks like: a generating session wrote at some arbitrary
// moment since the last poll, so its age jitters; and collect() re-sorts the
// array server-side, so the client may not lean on the payload's own order.
const LAG = [[1, 4, 2], [3, 1, 4], [0, 3, 1], [4, 2, 3], [2, 0, 4], [1, 3, 0], [3, 4, 1]];
const at = (t, k) => {
  const lag = LAG[k % LAG.length];
  const sessions = many.map(s => s.state === "working"
    ? {...s, last_activity: t - lag[Number(s.sid.slice(-1))]} : s);
  // Reverse on alternate polls: payload order must not decide row order.
  return {...payload(k % 2 ? sessions.slice().reverse() : sessions), generated: t};
};
const snap = () => [...__els.app.innerHTML.matchAll(
    /data-arg="[a-z]+:([a-z]+-\\d)" role/g)].map(m => m[1]);

for(const sort of ["attention", "recent", "repo"]){
  calmAction("sort", sort);
  render(at(100000, 0));
  const first = snap();
  // Six more polls, five seconds apart: enough for several rows to tick over a
  // whole minute and for every working row to have written again.
  const same = [];
  for(let k = 1; k <= 6; k++){
    render(at(100000 + k * 5, k));
    same.push(snap().join() === first.join());
  }
  out[sort] = {rows: first.length, stable: same.every(Boolean), order: first};
}
// A session that genuinely goes quiet is allowed — and expected — to move.
calmAction("sort", "attention");
render(at(100000, 0));
const before = snap();
const next = at(100010, 2);
render({...next, sessions: next.sessions.map(s =>
  s.sid === "work-1" ? {...s, state: "idle", active: false, last_activity: 90000} : s)});
out.realChangeMoves = snap().join() !== before.join();
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        for sort in ("attention", "recent", "repo"):
            with self.subTest(sort=sort):
                self.assertEqual(11, out[sort]["rows"], "a row went missing")
                self.assertTrue(
                    out[sort]["stable"],
                    f"{sort} order churned between polls: {out[sort]['order']}",
                )
        # Working rows sort ahead of idle ones under both attention and recent.
        self.assertEqual(
            ["work-0", "work-1", "work-2"], out["attention"]["order"][:3], "working rows not first"
        )
        self.assertEqual(["work-0", "work-1", "work-2"], out["recent"]["order"][:3])
        # Idle rows stay in most-recent-first order.
        self.assertEqual(["idle-0", "idle-1", "idle-2", "idle-3"], out["attention"]["order"][3:7])
        self.assertTrue(out["realChangeMoves"], "a session that changed state did not move")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_expanded_row_shows_what_the_regular_card_shows(self) -> None:
        checks = """
const out = {};
const sd = {role: "first-officer", workflows: [{workflow: "wf", stages: ["a", "b"],
  entities: [{slug: "ent", stage: "b", live: true, cycle: "c1"}]}]};
render(payload([Object.assign({}, busy, {spacedock: sd})]));
out.collapsedFirst = !__els.app.innerHTML.includes("cm-exp");
calmAction("open", "codex:bbb2");
const h = __els.app.innerHTML;
out.expanded = h.includes("cm-exp");
out.caret = h.includes('class="cm-caret">–<');
out.ariaExpanded = h.includes('aria-expanded="true"');
out.turn = h.includes("20m elapsed · ~39m left (est)") && h.includes("34%");
out.subagent = h.includes("Final whole-branch review");
out.prompt = h.includes("migrate the sync");
// Tasks: in-progress first and shown by its activeForm, completed last.
out.taskNote = h.includes("tasks · 1 of 3 done");
out.taskOrder = ["Converting chain…", "Re-run suite", "Map every call site"]
  .map(t => h.indexOf(t));
out.spacedock = h.includes("spacedock wf") && h.includes("first officer");
out.meta = h.includes("session bbb2") && h.includes("Claude");
// Collapsing again, and only one row open at a time.
calmAction("open", "codex:bbb2");
out.collapsed = !__els.app.innerHTML.includes("cm-exp");
render(board());
calmAction("open", "claude:aaa1");
calmAction("open", "codex:bbb2");
out.onlyOneOpen = (__els.app.innerHTML.match(/class="cm-exp"/g) || []).length;
// A turn with no percentage draws no bar and says so in words.
render(payload([mk({sid: "n", session: "n", state: "working", active: true,
  last_activity: 99999, turn: {elapsed_h: "9m", eta_h: null, pct: null, long: false}})]));
calmAction("open", "claude:n");
out.noPct = !__els.app.innerHTML.includes("cm-turn-pct")
  && __els.app.innerHTML.includes("9m elapsed · running longer than recent turns");
// A session with nothing extra expands to just its identity line.
render(payload([quiet]));
calmAction("open", "claude:ccc3");
const bare = __els.app.innerHTML;
out.bare = [bare.includes("cm-exp"), bare.includes("cm-tasks"),
            bare.includes("cm-subs"), bare.includes("session ccc3")];
// The title doubles as the prompt here, so it is not quoted twice.
out.noEchoedPrompt = !bare.includes("cm-quote");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["collapsedFirst"], "rows should start collapsed")
        self.assertTrue(out["expanded"])
        self.assertTrue(out["caret"])
        self.assertTrue(out["ariaExpanded"])
        self.assertTrue(out["turn"])
        self.assertTrue(out["subagent"])
        self.assertTrue(out["prompt"])
        self.assertTrue(out["taskNote"])
        self.assertEqual(sorted(out["taskOrder"]), out["taskOrder"], "task order is wrong")
        self.assertNotIn(-1, out["taskOrder"])
        self.assertTrue(out["spacedock"], "the Spacedock strip is missing from calm mode")
        self.assertTrue(out["meta"])
        self.assertTrue(out["collapsed"])
        self.assertEqual(1, out["onlyOneOpen"])
        self.assertTrue(out["noPct"])
        self.assertEqual([True, False, False, True], out["bare"])
        self.assertTrue(out["noEchoedPrompt"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_hostile_session_text_cannot_reach_the_dom_as_markup(self) -> None:
        # Titles, prompts, task subjects and subagent names all come from files
        # a project can write. Calm mode builds HTML strings, so every one of
        # them has to go through esc().
        checks = """
const bad = '<img src=x onerror=alert(1)>"><b>';
render(payload([mk({sid: bad, session: bad, project: bad, title: bad,
  state: "working", active: true, state_detail: bad, last_prompt: "p " + bad,
  last_activity: 99999, subagents: [bad], harness: bad,
  turn: {elapsed_h: bad, eta_h: bad, pct: 50, long: true},
  tasks: [{status: "pending", subject: bad, activeForm: bad}]})]));
calmAction("open", "claude:" + bad);
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  noTag: !h.includes("<img") && !h.includes("<b>"),
  escaped: h.includes("&lt;img src=x onerror=alert(1)&gt;"),
  attrsClosed: !h.includes('title=""><b>'),
  rows: rows()
}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["noTag"], "hostile session text reached the DOM as markup")
        self.assertTrue(out["escaped"])
        self.assertTrue(out["attrsClosed"], "hostile text broke out of an attribute")
        self.assertEqual(1, out["rows"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_keyboard_drives_the_ledger(self) -> None:
        checks = """
const out = {};
let __prevented = 0;
const key = (k, target) => { const before = __prevented;
  __fire("keydown", {key: k, target: target || {}, preventDefault(){ __prevented++; }});
  return __prevented - before; };
render(board());
out.cursorStartsAtTop = __els.app.innerHTML.includes('class="cm-row focus"');
key("j"); out.down1 = calmCursorKey;
key("j"); out.down2 = calmCursorKey;
key("j"); out.clampsAtBottom = calmCursorKey;
key("k"); out.up = calmCursorKey;
key("ArrowUp"); out.arrowUp = calmCursorKey;
key("ArrowUp"); out.clampsAtTop = calmCursorKey;
key("Enter"); out.enterOpens = calmOpenKey;
key(" "); out.spaceCloses = calmOpenKey;
key("f"); out.fFilters = calmFlagOnly;
key("Escape"); out.escapeClears = [calmFlagOnly, calmStateOnly, calmOpenKey];
// Moving the cursor brings it into view; a plain poll does not yank the list.
__revealed = 0;
key("j"); out.revealedOnMove = __revealed;
render(lastData); out.revealedOnPoll = __revealed;
// Keys the ledger does not own are left alone.
key("j", {tagName: "TEXTAREA"}); out.textareaSafe = calmCursorKey;
key("q"); out.unknownKeySafe = calmCursorKey;
// The browser scrolls on Space and the arrows unless the page says otherwise.
out.prevented = [key(" "), key("ArrowDown"), key("ArrowUp"), key("q")];
key(" ");  // leave nothing expanded for the checks below
// A modifier means the chord belongs to the browser or the OS, not to us.
const mode0 = displayMode;
out.modifiersIgnored = ["metaKey", "ctrlKey", "altKey"].map(mod => {
  __fire("keydown", {key: "c", [mod]: true, target: {}, preventDefault(){}});
  return displayMode === mode0;   // checked per modifier: two toggles cancel out
});
// Enter belongs to whatever focusable thing has focus, such as the empty
// state's "Show all sessions" link.
render(payload([]));
const link = {tagName: "A", closest: () => ({})};
out.linkKeepsEnter = key("Enter", link) === 0;
render(board());
// Nothing to move to is not an error, and nothing opens.
render(payload([]));
key("j"); key("Enter");
out.emptySafe = [calmOpenKey, __els.app.innerHTML.includes("cm-empty")];
// Ledger keys stay in the ledger: `j` in regular mode must not move a cursor.
setDisplayMode("regular");
render(board());
calmCursorKey = null;
key("j"); out.regularIgnoresJ = calmCursorKey;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["cursorStartsAtTop"], "no keyboard cursor on first paint")
        self.assertEqual("codex:bbb2", out["down1"])
        self.assertEqual("claude:ccc3", out["down2"])
        self.assertEqual("claude:ccc3", out["clampsAtBottom"], "cursor ran off the end")
        self.assertEqual("codex:bbb2", out["up"])
        self.assertEqual("claude:aaa1", out["arrowUp"])
        self.assertEqual("claude:aaa1", out["clampsAtTop"], "cursor ran off the start")
        self.assertEqual("claude:aaa1", out["enterOpens"])
        self.assertIsNone(out["spaceCloses"])
        self.assertTrue(out["fFilters"])
        self.assertEqual([False, None, None], out["escapeClears"])
        self.assertEqual(1, out["revealedOnMove"])
        self.assertEqual(1, out["revealedOnPoll"], "a poll scrolled the list on its own")
        self.assertEqual("codex:bbb2", out["textareaSafe"], "stole a key from a text field")
        self.assertEqual("codex:bbb2", out["unknownKeySafe"])
        self.assertEqual(
            [1, 1, 1, 0], out["prevented"], "the browser would scroll as well as the ledger"
        )
        self.assertEqual(
            [True, True, True],
            out["modifiersIgnored"],
            "a modifier chord (cmd/ctrl/alt + c) toggled the display mode",
        )
        self.assertTrue(out["linkKeepsEnter"], "swallowed Enter from a focused link")
        self.assertEqual([None, True], out["emptySafe"])
        self.assertIsNone(out["regularIgnoresJ"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_five_second_poll_does_not_disturb_the_view(self) -> None:
        # render() replaces #app wholesale. Everything the reader set has to
        # survive that: the open row, the cursor, the filters, the scroll.
        checks = """
const out = {};
render(board());
calmAction("sort", "recent");
calmAction("state", "work");
calmAction("open", "codex:bbb2");
calmCursorKey = "codex:bbb2";
__scrollTop = 137;
render(board());
const h = __els.app.innerHTML;
out.scroll = __scrollTop;
out.openKept = h.includes("cm-exp");
out.cursorKept = h.includes('class="cm-row focus open"');
out.sortKept = h.includes('data-arg="recent" aria-pressed="true"');
out.filterKept = calmStateOnly;
// Re-filtering, though, is a new list: keeping the old offset would drop the
// reader into the middle of rows they have not seen.
__scrollTop = 137;
calmAction("clear", null);
out.scrollResetOnFilter = __scrollTop;
__scrollTop = 137;
calmAction("sort", "repo");
out.scrollResetOnSort = __scrollTop;
// A session that disappears must not leave the cursor stranded.
calmAction("sort", "attention");
calmCursorKey = "nope:gone";
render(board());
out.strandedCursor = (__els.app.innerHTML.match(/class="cm-row focus/g) || []).length;
// The stall indicator the refresh loop writes into exists in calm mode too.
out.liveIds = __els.app.innerHTML.includes('id="live-dot"')
  && __els.app.innerHTML.includes('id="live-status"');
out.notifyControlPlaced = calmLedger(Object.assign(board(), {native_notify: ""}))
  .includes("Enable notifications");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(137, out["scroll"], "the poll reset the ledger scroll")
        self.assertTrue(out["openKept"], "the poll collapsed the open row")
        self.assertTrue(out["cursorKept"], "the poll lost the keyboard cursor")
        self.assertTrue(out["sortKept"])
        self.assertEqual("work", out["filterKept"])
        self.assertEqual(0, out["scrollResetOnFilter"], "a re-filter kept a stale scroll offset")
        self.assertEqual(0, out["scrollResetOnSort"], "a re-sort kept a stale scroll offset")
        self.assertEqual(1, out["strandedCursor"], "cursor vanished with its session")
        self.assertTrue(out["liveIds"], "calm mode cannot show a stalled refresh")
        self.assertTrue(out["notifyControlPlaced"], "no way to grant notifications in calm mode")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_two_harnesses_sharing_a_session_id_stay_two_rows(self) -> None:
        # dedupe_sessions keys on (harness, sid), so the same sid CAN reach the
        # page twice on different harnesses. The rest of the page already
        # treats that pair as identity (sessKey, the notification map); keying
        # the ledger on a bare sid would expand both rows at once and leave the
        # cursor unable to tell them apart.
        checks = """
const out = {};
const clash = "019fa752";
render(payload([
  mk({sid: clash, session: clash, harness: "claude", project: "repo/a", title: "Claude one"}),
  mk({sid: clash, session: clash, harness: "codex", project: "repo/b", title: "Codex one"})]));
out.bothRows = rows();
calmAction("open", K("claude", clash));
const h = __els.app.innerHTML;
out.onlyOneExpanded = (h.match(/class="cm-exp"/g) || []).length;
out.expandedTheRightOne = h.indexOf("Claude one") < h.indexOf("cm-exp")
  && h.indexOf("cm-exp") < h.indexOf("Codex one");
out.cursorIsScoped = calmCursorKey;
// j must step from one to the other, not sit still.
__fire("keydown", {key: "j", target: {}, preventDefault(){}});
out.moved = calmCursorKey;
// And the clipboard still gets the bare session id, not the row key.
calmAction("copy", K("codex", clash));
await __settle();
out.copied = __wrote;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks, clipboard="ok")
        self.assertEqual(2, out["bothRows"], "two harnesses collapsed into one row")
        self.assertEqual(1, out["onlyOneExpanded"], "one click expanded both rows")
        self.assertTrue(out["expandedTheRightOne"])
        self.assertEqual("claude:019fa752", out["cursorIsScoped"])
        self.assertEqual("codex:019fa752", out["moved"], "the cursor could not tell them apart")
        self.assertEqual(["019fa752"], out["copied"], "copied the row key instead of the id")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_unexpected_status_or_harness_cannot_render_undefined(self) -> None:
        # Every plain object inherits truthy `constructor` and `toString` from
        # Object.prototype, so a lookup like TABLE[x.status] || FALLBACK skips
        # its own fallback for those keys and paints `undefined` as both the
        # glyph and the CSS colour.
        checks = """
render(payload([mk({sid: "p", session: "p", harness: "constructor",
  state: "working", active: true, last_activity: 99999, rate_per_min: 5,
  tasks: [{status: "constructor", subject: "poisoned", activeForm: null},
          {status: "toString", subject: "also poisoned", activeForm: null},
          {status: "in_progress", subject: "real one", activeForm: "Working"}]})]));
calmAction("open", K("constructor", "p"));
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  noUndefined: !h.includes("undefined"),
  rows: rows(),
  tasksRendered: (h.match(/class="cm-task"/g) || []).length,
  realTaskFirst: h.indexOf("Working…") < h.indexOf("poisoned")}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["noUndefined"], "an inherited key rendered as undefined")
        self.assertEqual(1, out["rows"])
        self.assertEqual(3, out["tasksRendered"], "a poisoned status dropped a task row")
        self.assertTrue(out["realTaskFirst"], "inherited keys broke the task ordering")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_keyboard_focus_survives_the_poll(self) -> None:
        # The ledger's controls are real focusable buttons, and render() throws
        # the focused one away every five seconds. Without this, tabbing to a
        # control and pressing it is a race against the refresh.
        checks = """
const out = {};
render(board());
const find = act => __controls().find(c => c.getAttribute("data-calm") === act);
// Focus a control that carries an argument, and one that does not.
document.activeElement = __controls().find(c =>
  c.getAttribute("data-calm") === "copy" &&
  c.getAttribute("data-arg") === K("claude", "aaa1"));
__focused = null;
render(board());
out.withArg = __focused;
document.activeElement = find("flag");
__focused = null;
render(board());
out.withoutArg = __focused;
// A control that is gone after the payload changed must not steal focus.
document.activeElement = __controls().find(c =>
  c.getAttribute("data-arg") === K("claude", "ccc3"));
__focused = null;
render(payload([blocked]));
out.departed = __focused;
// Focus outside the ledger is left alone.
document.activeElement = {getAttribute: () => null};
__focused = null;
render(board());
out.untracked = __focused;
document.activeElement = null;
__focused = null;
render(board());
out.noFocus = __focused;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual("copy:claude:aaa1", out["withArg"], "focus was lost across the poll")
        self.assertEqual("flag:", out["withoutArg"])
        self.assertIsNone(out["departed"], "focus jumped to an unrelated control")
        self.assertIsNone(out["untracked"], "stole focus from outside the ledger")
        self.assertIsNone(out["noFocus"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_harness_that_reports_no_rate_does_not_read_as_zero(self) -> None:
        # Copilot, OpenCode, Cursor and Droid never populate rate_per_min, and
        # the regular view omits the meter rather than printing a zero. Calm
        # mode printing "0 /m" would make the two modes disagree.
        checks = """
render(payload([
  mk({sid: "cp", session: "cp", harness: "copilot", state: "working", active: true,
      last_activity: 99999, rate_per_min: 0}),
  mk({sid: "cl", session: "cl", state: "working", active: true,
      last_activity: 99999, rate_per_min: 1200})]));
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  zero: h.includes(">0 /m<"), dash: h.includes(">—<"), real: h.includes(">1,200 /m<")}));
"""
        out = self.run_calm(checks)
        self.assertFalse(out["zero"], 'printed a fabricated "0 /m" for a rate-less harness')
        self.assertTrue(out["dash"])
        self.assertTrue(out["real"], "lost the rate for a harness that does report one")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_copy_id_reports_what_the_clipboard_actually_did(self) -> None:
        checks = """
const out = {};
render(board());
calmAction("copy", "claude:aaa1");
await __settle();
out.wrote = __wrote;
out.label = __els.app.innerHTML.includes(">copied<");
out.otherRowsUnchanged = (__els.app.innerHTML.match(/>copy id</g) || []).length;
__tick();
out.reverts = !__els.app.innerHTML.includes(">copied<");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks, clipboard="ok")
        self.assertEqual(["aaa1"], out["wrote"], "copy id wrote the wrong value")
        self.assertTrue(out["label"], "no feedback that the id was copied")
        self.assertEqual(2, out["otherRowsUnchanged"])
        self.assertTrue(out["reverts"], "the copied label never clears")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_copy_id_never_claims_a_copy_the_browser_refused(self) -> None:
        # An unfocused document or a non-secure context rejects the write. A
        # confident "copied" there costs the reader the id they wanted.
        checks = """
render(board());
calmAction("copy", "claude:aaa1");
await __settle(); await __settle();
const h = __els.app.innerHTML;
console.log(JSON.stringify({lied: h.includes(">copied<"), told: h.includes(">blocked<")}));
"""
        denied = self.run_calm(checks, clipboard="denied")
        self.assertFalse(denied["lied"], "claimed a copy the clipboard rejected")
        self.assertTrue(denied["told"])
        # And with no Clipboard API at all.
        absent = self.run_calm(checks)
        self.assertFalse(absent["lied"])
        self.assertTrue(absent["told"])

    def test_the_type_scale_is_the_only_source_of_a_font_size(self) -> None:
        # The stylesheet used to carry twenty ad-hoc px sizes between 8px and
        # 15px, which is drift rather than hierarchy. One raw px value reopens
        # that door, and a step nothing references is a rung nobody stands on.
        raw = re.findall(r"font-size:\s*[\d.]+px", STYLES)
        self.assertEqual([], raw, "a font-size bypassed the --fs-* scale")
        steps = re.findall(r"(--fs-[\w-]+)\s*:", STYLES)
        self.assertEqual(sorted(steps), sorted(set(steps)), "a scale step is declared twice")
        for step in steps:
            with self.subTest(step=step):
                self.assertIn(f"var({step})", STYLES, "declared but never used")

    def test_the_ink_ramp_stays_three_distinct_readable_steps(self) -> None:
        # --ink3 carries most of the metadata on the board and used to sit at
        # 3.1:1, below AA for normal text, on the smallest type in the UI. Both
        # themes are checked against the worst surface each ink can land on.
        def luminance(value: str) -> float:
            channels = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def ratio(a: str, b: str) -> float:
            high, low = sorted((luminance(a), luminance(b)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        dark = re.search(r"@media \(prefers-color-scheme:dark\)\{(.*?)\n  \}", STYLES, re.DOTALL)
        assert dark is not None
        light = STYLES[: STYLES.index("@media")]

        def token(block: str, name: str) -> str:
            found = re.search(rf"{name}:(#[0-9a-f]{{6}})", block)
            assert found is not None, f"{name} is not a hex value"
            return found.group(1)

        # Light ink sits on --panel at worst in dark; dark ink on --sunk in light.
        for theme, block, surface in (
            ("light", light, "--sunk"),
            ("dark", dark.group(1), "--panel"),
        ):
            worst = token(block, surface)
            ramp = [ratio(token(block, f"--ink{s}"), worst) for s in ("", "2", "3")]
            with self.subTest(theme=theme):
                self.assertGreater(ramp[2], 4.5, "--ink3 fails AA against the surface it sits on")
                # A ramp whose steps converge stops encoding hierarchy at all.
                self.assertGreater(ramp[0], ramp[1] * 1.25)
                self.assertGreater(ramp[1], ramp[2] * 1.25)

    def test_every_css_variable_the_page_uses_is_declared(self) -> None:
        # A `var(--typo)` renders as nothing at all and no linter here sees it.
        declared = set(re.findall(r"(--[\w-]+)\s*:", STYLES))
        used = set(re.findall(r"var\((--[\w-]+)", PAGE_TEXT))
        self.assertEqual(set(), used - declared, "page uses CSS variables nothing declares")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_column_headers_share_the_scrollers_width(self) -> None:
        # Headers and rows lay out on the same grid. As a SIBLING of the
        # scrolling body the header keeps the full frame width while the rows
        # lose the scrollbar's, and the whole delta lands in the one flexible
        # track, so every label from `where` rightward sits off its data. Only
        # invisible where scrollbars are overlays, which is to say only on the
        # machine this was built on.
        checks = """
render(board());
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  nested: h.includes('<div class="cm-body" id="cm-body"><div class="cm-head">'),
  headings: h.includes("<span>where</span>")}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["nested"], "the column headers are outside the scroll container")
        self.assertTrue(out["headings"])
        self.assertIn(".cm-head{position:sticky;top:0;", STYLES)

    def test_a_focused_quick_action_can_actually_be_seen(self) -> None:
        # The row's quick action lives in a container held at opacity:0 until
        # hover. Ancestor opacity composites the whole subtree as a group, so a
        # focused child cannot make itself visible — the row has to. Without
        # this the ledger has one invisible tab stop per row.
        self.assertIn(".cm-row:focus-within .cm-q{opacity:1}", STYLES)

    def test_no_control_drops_its_focus_ring_without_replacing_it(self) -> None:
        rules = re.findall(r"\n\s*([^\n{]*:focus-visible[^\n{]*)\{([^}]*)\}", STYLES)
        self.assertGreater(len(rules), 4, "focus-visible rules disappeared; is the regex stale?")
        for selector, body in rules:
            with self.subTest(selector=selector.strip()):
                if "outline:none" in body:
                    self.assertIn(
                        "box-shadow",
                        body,
                        "removes the browser focus ring and puts nothing in its place",
                    )

    def test_the_calm_palette_has_a_dark_counterpart(self) -> None:
        # Calm mode adds surfaces and a second flag tone. Declaring them only
        # in the light block leaves a light-on-light ledger after dark.
        dark = re.search(r"@media \(prefers-color-scheme:dark\)\{(.*?)\n  \}", STYLES, re.DOTALL)
        assert dark is not None
        for name in ("--sunk", "--line2", "--accent-ink", "--warn", "--warnink"):
            with self.subTest(token=name):
                self.assertIn(name, dark.group(1))

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_stop_button_arms_then_posts_and_shows_the_stopped_panel(self) -> None:
        checks = """
const out = {};
render(board());
out.shown = __els.app.innerHTML.includes('data-calm="stop"');
out.armedBefore = __els.app.innerHTML.includes("sure?");

// First click only arms it: the page cannot undo a stop.
__fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
out.armedAfter = __els.app.innerHTML.includes("sure?");
out.postedYet = __fetchCalls.filter(c => c[0] === "/api/shutdown").length;

// A refresh must not disarm it — #app is rebuilt every 5s and the button
// would flicker under the reader's cursor.
render(board());
out.survivesRender = __els.app.innerHTML.includes("sure?");

__fetchImpl = () => Promise.resolve({ok: true});
__fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
await __settle(); await __settle();
const posted = __fetchCalls.filter(c => c[0] === "/api/shutdown");
out.posted = posted.length;
out.method = posted.length ? posted[0][1].method : null;
out.stoppedPanel = __els.app.innerHTML.includes("Cargento stopped");
out.buttonGone = __els.app.innerHTML.includes('data-calm="stop"');
out.title = document.title;
out.refreshTimer = refreshTimer;
out.clearedIntervals = __clearedIntervals;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["shown"])
        self.assertFalse(out["armedBefore"])
        self.assertTrue(out["armedAfter"])
        self.assertEqual(0, out["postedYet"])
        self.assertTrue(out["survivesRender"])
        self.assertEqual(1, out["posted"])
        self.assertEqual("POST", out["method"])
        self.assertTrue(out["stoppedPanel"])
        self.assertFalse(out["buttonGone"])
        self.assertIn("stopped", out["title"])
        self.assertIsNone(out["refreshTimer"])
        # One timer, because the calm harness stubs no EventSource: without it
        # the page runs the legacy five-second poll and elects no leader, so
        # stopLive has only the poll to clear. The id is the harness's
        # sequential setInterval counter.
        self.assertEqual([1], out["clearedIntervals"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_armed_stop_button_keeps_focus_and_accepts_keyboard_activation(self) -> None:
        checks = """
const out = {trials: []};
const stopButton = {
  tagName: "BUTTON",
  getAttribute: a => a === "data-calm" ? "stop" : null,
  closest(sel){
    return sel === "[data-calm]" || sel === '[data-calm="stop"]' ||
      sel === "a[href],button,select,textarea,input,[tabindex]" ? this : null;
  },
  focus(){ document.activeElement = this; }
};
__els["stop-control"] = stopButton;
const clickStop = () => __fire("click", {target: stopButton});
__fetchImpl = () => Promise.resolve({ok: true});

for(const key of [" ", "Enter"]){
  stopArmed = false; stopError = ""; serverStopped = false; stopFocusPending = false;
  refreshTimer = 73; document.activeElement = null; __fetchCalls = [];
  render(board());
  clickStop();
  const armed = __els.app.innerHTML.includes("sure?");
  const focusKept = document.activeElement === stopButton;
  __fire("keydown", {key, target: stopButton, preventDefault(){}});
  const armedAfterKey = __els.app.innerHTML.includes("sure?");
  clickStop();  // the native click generated by Space or Enter
  await __settle(); await __settle();
  out.trials.push({key, armed, focusKept, armedAfterKey,
    posts: __fetchCalls.filter(c => c[0] === "/api/shutdown").length,
    stopped: __els.app.innerHTML.includes("Cargento stopped")});
}
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(2, len(out["trials"]))
        for trial in out["trials"]:
            with self.subTest(key=repr(trial["key"])):
                self.assertTrue(trial["armed"])
                self.assertTrue(
                    trial["focusKept"],
                    "arming re-rendered the focused button away",
                )
                self.assertTrue(
                    trial["armedAfterKey"],
                    "the activation key disarmed before the button could click",
                )
                self.assertEqual(1, trial["posts"])
                self.assertTrue(trial["stopped"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_stop_disarms_on_escape_and_on_a_click_elsewhere(self) -> None:
        checks = """
const out = {};
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
const clickAway = () => __fire("click", {target: {closest: () => null}});

render(board());
clickStop();
out.armed = __els.app.innerHTML.includes("sure?");
__fire("keydown", {key: "Escape", preventDefault(){}, target: {tagName: "DIV"}});
out.afterEsc = __els.app.innerHTML.includes("sure?");

clickStop();
out.armedAgain = __els.app.innerHTML.includes("sure?");
clickAway();
out.afterClickAway = __els.app.innerHTML.includes("sure?");

// A click on a *different* control is an answer too. Otherwise the armed
// state outlives the moment it was armed in, and a single later click on
// stop takes the server down with no confirmation at all.
const clickControl = (act) => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? act : null} : null}});
clickStop();
out.armedOnceMore = __els.app.innerHTML.includes("sure?");
clickControl("flag");
out.afterOtherControl = __els.app.innerHTML.includes("sure?");
clickStop();                    // must re-arm, not fire
out.rearmed = __els.app.innerHTML.includes("sure?");
await __settle(); await __settle();
out.nothingPosted = __fetchCalls.filter(c => c[0] === "/api/shutdown").length;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["armed"])
        self.assertFalse(out["afterEsc"])
        self.assertTrue(out["armedAgain"])
        self.assertFalse(out["afterClickAway"])
        self.assertTrue(out["armedOnceMore"])
        self.assertFalse(out["afterOtherControl"], "a click on another control left stop armed")
        self.assertTrue(out["rearmed"])
        self.assertEqual(0, out["nothingPosted"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_failed_stop_reports_inline_and_leaves_the_page_live(self) -> None:
        checks = """
const out = {};
render(board());
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop();
__fetchImpl = () => Promise.resolve({ok: false, status: 403});
clickStop();
await __settle(); await __settle();
// The server is still running, so the page must not claim otherwise.
out.stoppedPanel = __els.app.innerHTML.includes("Cargento stopped");
out.error = __els.app.innerHTML.includes("stop failed");
out.rows = rows();
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertFalse(out["stoppedPanel"])
        self.assertTrue(out["error"])
        self.assertEqual(3, out["rows"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_poll_starting_after_the_stop_never_reaches_the_network(self) -> None:
        checks = """
const out = {};
render(board());
// The page's own bottom-of-script `refresh()` already fired once at load,
// before this check ever ran — count from here, not from zero.
const before = __fetchCalls.filter(c => String(c[0]).startsWith("/api/data")).length;
serverStopped = true;
renderStopped();
await refresh();
out.stillStopped = __els.app.innerHTML.includes("Cargento stopped");
out.noFetch = __fetchCalls.filter(c => String(c[0]).startsWith("/api/data")).length - before;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stillStopped"])
        self.assertEqual(0, out["noFetch"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_poll_in_flight_across_the_stop_does_not_repaint_the_panel(self) -> None:
        # The one the entry guard above cannot cover: this poll had already
        # called fetch before the stop landed, so it settles afterwards. The
        # panel surviving is now the render() guard's doing, so this also
        # asserts what only refresh()'s own post-await guard can protect: a
        # payload that arrived after the stop must not be absorbed into the rate
        # history, which does not go through render() and would otherwise leave
        # a sample recorded for a server that was already gone.
        checks = """
const out = {};
render(board());
let releaseData;
const later = () => { const d = board(); d.generated = d.generated + 60; return d; };
__fetchImpl = (url) => String(url).startsWith("/api/data")
  ? new Promise(r => { releaseData = () =>
      r({ok: true, json: () => Promise.resolve(later())}); })
  : Promise.resolve({ok: true});          // /api/shutdown answers at once
const poll = refresh();                   // in flight, deliberately unsettled

const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop(); clickStop();                 // arm, then confirm
await __settle(); await __settle();
out.stoppedAfterStop = __els.app.innerHTML.includes("Cargento stopped");
const ratesBefore = rateHistory.length;
const generatedBefore = lastGenerated;

releaseData();
await poll; await __settle(); await __settle();
out.stoppedAfterLatePoll = __els.app.innerHTML.includes("Cargento stopped");
out.dashboardBack = __els.app.innerHTML.includes("cm-frame");
out.title = document.title;
out.ratesGrew = rateHistory.length - ratesBefore;
out.generatedMoved = lastGenerated !== generatedBefore;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(0, out["ratesGrew"], "a payload that arrived after the stop was recorded")
        self.assertFalse(out["generatedMoved"], "the stale payload advanced lastGenerated")
        self.assertTrue(out["stoppedAfterStop"])
        self.assertTrue(out["stoppedAfterLatePoll"], "a late poll repainted the stopped panel")
        self.assertFalse(out["dashboardBack"])
        self.assertIn("stopped", out["title"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_keystroke_disarms_the_stop_just_like_a_click(self) -> None:
        # The keyboard drives the same controls the mouse does — `c` is the mode
        # button, `f` the flag, Enter opens a row — so disarming only on click
        # left the armed state outliving the interaction it was armed in, and one
        # later click on stop would end the server unconfirmed.
        checks = """
const out = {trials: []};
const shutdowns = () => __fetchCalls.filter(c => String(c[0]) === "/api/shutdown").length;
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
const key = k => __fire("keydown", {key: k, target: {}, preventDefault(){}});
__fetchImpl = () => Promise.resolve({ok: true});

const trial = async (label, act) => {
  displayMode = "calm"; calmOpenKey = null; calmCursorKey = null;
  calmFlagOnly = false; calmStateOnly = null;
  stopArmed = false; stopError = ""; serverStopped = false;
  render(board());
  clickStop();
  const armed = stopArmed;
  act();
  const stillArmed = __els.app.innerHTML.includes("sure?");
  const before = shutdowns();
  clickStop();                                    // ONE further click
  await __settle(); await __settle();
  return {label, armed, stillArmed, posts: shutdowns() - before,
    stopped: __els.app.innerHTML.includes("Cargento stopped")};
};
for(const [label, act] of [
    ["c", () => key("c")], ["f", () => key("f")], ["Enter", () => key("Enter")],
    ["j", () => key("j")], ["k", () => key("k")], ["ArrowDown", () => key("ArrowDown")]]){
  out.trials.push(await trial(label, act));
}
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(6, len(out["trials"]))
        for trial in out["trials"]:
            with self.subTest(key=trial["label"]):
                self.assertTrue(trial["armed"], "the first click did not arm it")
                self.assertFalse(trial["stillArmed"], "the keystroke left stop armed")
                self.assertEqual(0, trial["posts"], "one click after a keystroke stopped it")
                self.assertFalse(trial["stopped"], "the server was stopped unconfirmed")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_stopped_panel_takes_no_keyboard_side_effects(self) -> None:
        # render()'s guard stops the paint but not what happens on the way there.
        # setDisplayMode writes localStorage *before* it paints, so `c` on the
        # terminal panel looked inert while durably flipping the saved mode for
        # the next run; and the calm keys went on calling preventDefault(),
        # swallowing page scrolling on a page that is no longer live.
        checks = """
const out = {};
let prevented = 0;
const key = k => __fire("keydown", {key: k, target: {},
  preventDefault(){ prevented++; }});
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
__fetchImpl = () => Promise.resolve({ok: true});
render(board());
out.modeBefore = displayMode;
out.storedBefore = __store["cargento.displayMode"];
clickStop(); clickStop();
await __settle(); await __settle();
out.stopped = __els.app.innerHTML.includes("Cargento stopped");

prevented = 0;
["c", "j", "k", "ArrowDown", "ArrowUp", "Enter", " ", "f", "Escape"].forEach(key);
out.storedAfter = __store["cargento.displayMode"];
out.modeAfter = displayMode;
out.prevented = prevented;
out.stillStopped = __els.app.innerHTML.includes("Cargento stopped");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stopped"])
        self.assertTrue(out["stillStopped"])
        self.assertEqual(
            out["storedBefore"], out["storedAfter"], "a keystroke persisted a mode change"
        )
        self.assertEqual(out["modeBefore"], out["modeAfter"], "a keystroke changed the mode")
        self.assertEqual(0, out["prevented"], "the terminal panel still swallows keystrokes")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_nothing_repaints_over_the_stopped_panel(self) -> None:
        # refresh() is not the only way into render(): fourteen other call sites
        # end in render(lastData), and the keydown listener is bound to
        # `document`, so nothing in #app gates it. One `c` was enough to put a
        # live-looking board back with a stale needs-input count in the title.
        checks = """
const out = {};
render(board());
__fetchImpl = () => Promise.resolve({ok: true});
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop(); clickStop();
await __settle(); await __settle();
out.stopped = __els.app.innerHTML.includes("Cargento stopped");
out.title = document.title;

const key = k => __fire("keydown", {key: k, target: {}, preventDefault(){}});
const live = () => __els.app.innerHTML.includes("cm-frame")
  || __els.app.innerHTML.includes('class="tile"');

// `c` toggles the display mode, which ends in render(lastData).
key("c");
out.afterC = {stopped: __els.app.innerHTML.includes("Cargento stopped"),
  live: live(), title: document.title};

// The calm ledger keys, and a direct call for the paths keys cannot reach.
key("f"); key("j"); key("k"); key("Escape"); key("Enter");
out.afterKeys = {stopped: __els.app.innerHTML.includes("Cargento stopped"), live: live()};

calmAction("flag", null);
toggleIdle();
setDisplayMode("regular");
render(board());
out.afterDirect = {stopped: __els.app.innerHTML.includes("Cargento stopped"),
  live: live(), title: document.title};
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stopped"])
        self.assertIn("stopped", out["title"])
        for label in ("afterC", "afterKeys", "afterDirect"):
            with self.subTest(after=label):
                self.assertTrue(out[label]["stopped"], f"{label} repainted over the stopped panel")
                self.assertFalse(out[label]["live"], f"{label} brought the dashboard back")
        # The title is part of the panel: a stale needs-input count there says
        # a session wants you, for a server that cannot tell you either way.
        self.assertIn("stopped", out["afterC"]["title"])
        self.assertIn("stopped", out["afterDirect"]["title"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_stop_is_not_counted_as_a_failed_refresh(self) -> None:
        # The same race down the catch arm: the server has gone, so the poll in
        # flight rejects. A stop the reader asked for is not a refresh failure,
        # and counting it as one drives the "stalled · retrying every 5s"
        # bookkeeping for a server that is never coming back.
        checks = """
const out = {};
render(board());
let failData;
__fetchImpl = (url) => String(url).startsWith("/api/data")
  ? new Promise((_, reject) => { failData = () => reject(new Error("connection refused")); })
  : Promise.resolve({ok: true});
const poll = refresh();

const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop(); clickStop();
await __settle(); await __settle();

failData();
await poll; await __settle(); await __settle();
out.stillStopped = __els.app.innerHTML.includes("Cargento stopped");
out.failures = window.__refreshFailures || 0;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stillStopped"])
        # No assertion on the stalled banner here: it is written to #live-status
        # and #live-dot, which the DOM stub does not register, so any such check
        # would pass whatever the code did. The failure count is the observable.
        self.assertEqual(0, out["failures"], "a deliberate stop was counted as a refresh failure")
