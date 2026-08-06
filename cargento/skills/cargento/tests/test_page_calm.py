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
// footer carries what the note does not, and pluralizes. The `≥` is this
// board's own arithmetic, not decoration: `blocked` is active and its rate is
// unmeasurable — the strip states no `reports_rate` for claude and the row's
// own rate is 0 — so the total is short by whatever that session is burning.
// The rule itself is pinned below, in the floor test.
out.footer = h.includes("1 harness · ≥ 1,234 tok/min");
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

// `burn` is in this loop deliberately. It is the one ordering that ranks on a
// value which ticks, so it is the one that CAN move a row — but only when the
// rate itself moves. These rows keep a fixed rate while their ages advance, so
// churn here would mean the ordering is reading the clock, not the rate.
for(const sort of ["attention", "recent", "repo", "burn"]){
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
        for sort in ("attention", "recent", "repo", "burn"):
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
        # Copilot, OpenCode, Cursor and Droid never populate rate_per_min. Both
        # views say so rather than printing the 0 those rows carry: the regular
        # card reads "rate unknown" and the ledger cell shows a dash. A fabricated
        # "0 /m" would be indistinguishable from a session that really did
        # generate nothing, which is a different fact.
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

    # A strip that states, per harness, whether a rate from it is a measurement
    # at all — which is what the server publishes as `reports_rate`. Copilot is
    # the rate-less row here; its sessions carry the same 0 Claude's would for a
    # session that generated nothing, so only this flag separates them.
    BURN_FIXTURE = """
const strip = [
  {key: "claude", label: "Claude Code", discovered: true, error: null, reports_rate: true},
  {key: "codex", label: "Codex", discovered: true, error: null, reports_rate: true},
  {key: "copilot", label: "Copilot", discovered: true, error: null, reports_rate: false}];
const working = (sid, harness, rate) => mk({sid, session: sid, harness, state: "working",
  active: true, last_activity: 99990, rate_per_min: rate});
const burnBoard = (over) => Object.assign(payload([
  working("slow", "claude", 40), working("fast", "codex", 3100),
  working("zero", "claude", 0), working("mute", "copilot", 0),
  working("mid", "codex", 900)]), {harnesses: strip, rate_window_sec: 600}, over || {});
const seq = h => [...h.matchAll(/data-arg="[a-z]+:([a-z]+)" role="button"/g)].map(m => m[1]);
const dividers = h => [...h.matchAll(/cm-div-k">([^<]*)<\\/span><span class="cm-div-n">(\\d+)</g)]
  .map(m => [m[1], Number(m[2])]);
// One row's markup, ending at the first </div> — a ledger row is spans only, so
// the row's own close is the first one after it.
const rowOf = (h, key) => {
  const i = h.indexOf('data-arg="' + key + '" role="button"');
  return i < 0 ? "" : h.slice(i, h.indexOf("</div>", i));
};
// Sessions that are NOT working, carrying the rates a trailing mean really does
// report for them: one that stopped inside the window keeps the number it earned
// before it stopped, and one blocked on the reader keeps the number it burned
// before it asked.
const stopped = (sid, harness, rate, ago) => mk({sid, session: sid, harness,
  state: "idle", active: true, last_activity: 100000 - ago, rate_per_min: rate});
const waiting = (sid, harness, rate) => mk({sid, session: sid, harness,
  state: "needs_input", active: true, last_activity: 99880, blocked_since: 99880,
  rate_per_min: rate});
// The board the two views used to disagree about: one codex session actually
// generating, at a thirtieth of the mean still carried by a claude session that
// stopped nearly two minutes ago.
const contra = () => burnBoard({sessions: [
  stopped("stop", "claude", 9000, 110), working("work", "codex", 300),
  working("zed", "claude", 0), working("mute", "copilot", 0),
  waiting("held", "claude", 4000), stopped("hush", "copilot", 0, 3000)]});
// One row's rate cell exactly as rendered — "" for an empty cell, so a missing
// number and a dash cannot be mistaken for each other here either.
const rateCellOf = (h, key) => {
  const m = rowOf(h, key).match(/class="cm-rate"><span class="cm-metric"[^>]*>([^<]*)</);
  return m ? m[1] : null;
};
// The rows sitting under one divider, in rendered order, keyed the way the
// ledger keys them: (harness, sid).
const groupRows = (h, label) => {
  const start = h.indexOf('cm-div-k">' + label);
  if(start < 0) return null;
  const next = h.indexOf('class="cm-div"', start);
  return [...h.slice(start, next < 0 ? h.length : next)
    .matchAll(/data-arg="([a-z]+:[a-z]+)" role="button"/g)].map(m => m[1]);
};
"""

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_burn_ordering_ranks_on_rate_and_ranks_no_unknown(self) -> None:
        # A10's question, and the trap in it. Four of the ten harnesses report no
        # rate, so a descending sort that treats their 0 as a number puts them
        # below every session it can prove is slow — a claim the payload does not
        # support and the reader cannot see through. They are ranked nowhere
        # instead, under a divider that says so, and a REAL zero still ranks.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
calmAction("sort", "burn");
render(burnBoard());
const h = __els.app.innerHTML;
out.order = seq(h);
out.dividers = dividers(h);
out.rows = rows();
// A real zero prints its number; an unmeasured one prints a dash. Both sit in
// the ledger, in different groups, saying different things.
out.realZero = rowOf(h, "claude:zero").includes(">0 /m<");
out.unknownCell = [rowOf(h, "copilot:mute").includes(">—<"),
                   rowOf(h, "copilot:mute").includes("/m")];
out.unknownTip = rowOf(h, "copilot:mute").includes("this harness reports no token rate");
// The unranked group sits after every ranked row, behind its divider.
out.dividerBeforeUnknown = h.indexOf("no rate reported") < h.indexOf('data-arg="copilot:mute"');
out.slowestRankedBeforeDivider =
  h.indexOf('data-arg="claude:zero"') < h.indexOf("no rate reported");
// A board with nothing unmeasured raises no unranked divider at all.
render(burnBoard({sessions: [working("fast", "codex", 3100), working("slow", "claude", 40)]}));
out.allKnown = [seq(__els.app.innerHTML), dividers(__els.app.innerHTML)];
// A board with nothing measured ranks nobody, and says that rather than
// presenting an arbitrary order as a ranking.
render(burnBoard({sessions: [working("mute", "copilot", 0), working("hush", "copilot", 0)]}));
out.noneKnown = dividers(__els.app.innerHTML);
// Switching away restores the ordering that was there before.
calmAction("sort", "attention");
render(burnBoard());
out.attentionUnaffected = dividers(__els.app.innerHTML).length;
console.log(JSON.stringify(out));
"""
        )
        out = self.run_calm(checks)
        self.assertEqual(["fast", "mid", "slow", "zero", "mute"], out["order"])
        self.assertEqual(
            [["fastest first · 10m mean", 4], ["no rate reported · cannot be ranked", 1]],
            out["dividers"],
        )
        self.assertEqual(5, out["rows"], "the ordering dropped a row")
        self.assertTrue(out["realZero"], "a measured zero lost its number")
        self.assertEqual([True, False], out["unknownCell"], "an unmeasured row printed a rate")
        self.assertTrue(out["unknownTip"])
        self.assertTrue(out["dividerBeforeUnknown"], "an unknown row was ranked")
        self.assertTrue(out["slowestRankedBeforeDivider"])
        self.assertEqual(
            [["fast", "slow"], [["fastest first · 10m mean", 2]]],
            out["allKnown"],
            "an unranked divider appeared with nothing in it",
        )
        self.assertEqual(
            [["no rate reported · cannot be ranked", 2]],
            out["noneKnown"],
            "a board with no measurements still claimed a fastest-first ranking",
        )
        self.assertEqual(0, out["attentionUnaffected"], "burn dividers leaked into another order")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_burn_ordering_ranks_only_the_sessions_that_are_working(self) -> None:
        # The rate is a trailing mean, so a session that stopped inside the window
        # still carries the number it earned before it stopped — routinely a much
        # larger one than anything still running. Ranking those rows headed
        # "fastest first" with an agent doing nothing, and made the two views
        # disagree about one payload: the regular card marks the fastest WORKING
        # session, and that is the semantics both of them now hold.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
calmAction("sort", "burn");
render(contra());
const h = __els.app.innerHTML;
out.order = seq(h);
out.dividers = dividers(h);
out.rows = rows();
out.ranked = groupRows(h, "fastest first");
// The one claim a reader takes from this ordering is that the top row is the
// session generating fastest. It is also the row the regular view marks, and on
// this payload the old ordering and that marker named different sessions.
out.topRow = (h.match(/data-arg="([a-z]+:[a-z]+)" role="button"/) || [])[1];
out.regularLeaders = [...burnLeaders(contra()).keys];
// A row that is not ranked sits under a divider that says why, rather than
// leaving the reader to infer it from an `idle / wait` column three cells away.
out.stillGroup = groupRows(h, "not working");
// Ranking is read off state, not off a demotion: dropping the stopped row
// entirely leaves the same ranked group behind.
render(burnBoard({sessions: [working("work", "codex", 300), working("zed", "claude", 0)]}));
out.withoutStopped = groupRows(__els.app.innerHTML, "fastest first");
// With nothing working there is no ranking to head at all, however fast the
// stopped rows were a minute ago.
render(burnBoard({sessions: [stopped("stop", "claude", 9000, 110),
                             waiting("held", "claude", 4000)]}));
out.noneWorking = dividers(__els.app.innerHTML);
console.log(JSON.stringify(out));
"""
        )
        out = self.run_calm(checks)
        self.assertEqual(6, out["rows"], "the ordering dropped a row")
        self.assertEqual(
            ["codex:work", "claude:zed"],
            out["ranked"],
            "a session that is not working was ranked on its stale mean",
        )
        self.assertEqual(
            "codex:work", out["topRow"], '"fastest first" led with a session doing nothing'
        )
        self.assertEqual(
            ["codex:work"],
            out["regularLeaders"],
            "the fixture stopped pinning the two views to one answer",
        )
        self.assertEqual(
            [
                ["fastest first · 10m mean", 2],
                ["no rate reported · cannot be ranked", 1],
                # "now": the same group also takes a row whose state still says
                # working but whose harness has not written inside the window,
                # and that row displays as working. See the parity test below.
                ["not working now · not in the ranking", 3],
            ],
            out["dividers"],
            "the groups do not account for every row, or do not say what they are",
        )
        self.assertEqual(["work", "zed", "mute", "held", "stop", "hush"], out["order"])
        self.assertEqual(["claude:held", "claude:stop", "copilot:hush"], out["stillGroup"])
        self.assertEqual(["codex:work", "claude:zed"], out["withoutStopped"])
        self.assertEqual(
            [["not working now · not in the ranking", 2]],
            out["noneWorking"],
            "a board with nothing working still claimed a fastest-first ranking",
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_ranking_takes_the_predicate_the_regular_view_marks_on(self) -> None:
        # `state === "working"` is the harness's claim; `active` is whether it has
        # written anything inside the display window. A row can carry the first
        # without the second — `?all=1` lists those, and a session whose subagents
        # hold the state file open reaches it too — and it still carries the last
        # trailing mean its harness measured. Ranking on the state alone put that
        # row first under "fastest first" while the regular view marked a live
        # session fifty times slower as `fastest`: two views, one payload, two
        # answers to "which is fastest". Both read one predicate now.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
// Working by state, silent for longer than the display window.
const ghost = (sid, harness, rate) => mk({sid, session: sid, harness, state: "working",
  active: false, last_activity: 99990, rate_per_min: rate});
const d = burnBoard({show_all: true, sessions: [
  ghost("ghost", "claude", 5000), working("live", "codex", 100),
  working("mute", "copilot", 0), ghost("hush", "copilot", 0)]});
calmAction("sort", "burn");
render(d);
const h = __els.app.innerHTML;
out.order = seq(h);
out.dividers = dividers(h);
out.rows = rows();
out.ranked = groupRows(h, "fastest first");
out.topRow = (h.match(/data-arg="([a-z]+:[a-z]+)" role="button"/) || [])[1];
// The SAME payload object the ledger just rendered, so nothing about the two
// answers can be blamed on two payloads.
out.regularLeaders = [...burnLeaders(d).keys];
out.stillGroup = groupRows(h, "not working now");
// Left out of the ranking, not stripped of what its harness measured: the row
// keeps its number, under a divider that says why it is not being compared.
out.ghostCell = rateCellOf(h, "claude:ghost");
// An unmeasured row that is not running belongs to the same group as the rest of
// them, not to the divider about measurement.
out.muteGroup = groupRows(h, "no rate reported");
console.log(JSON.stringify(out));
"""
        )
        out = self.run_calm(checks)
        self.assertEqual(4, out["rows"], "the ordering dropped a row")
        self.assertEqual(
            ["codex:live"],
            out["ranked"],
            "a session that has not written inside the window was ranked on its stale mean",
        )
        self.assertEqual(
            out["regularLeaders"],
            [out["topRow"]],
            "the two views disagree about which session is burning fastest",
        )
        self.assertEqual(
            [
                ["fastest first · 10m mean", 1],
                ["no rate reported · cannot be ranked", 1],
                ["not working now · not in the ranking", 2],
            ],
            out["dividers"],
            "the groups do not account for every row, or do not say what they are",
        )
        self.assertEqual(["live", "mute", "ghost", "hush"], out["order"])
        self.assertEqual(["claude:ghost", "copilot:hush"], out["stillGroup"])
        self.assertEqual(["copilot:mute"], out["muteGroup"])
        self.assertEqual("5,000 /m", out["ghostCell"], "an unranked row lost its measurement")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_footer_total_says_when_it_is_only_a_floor(self) -> None:
        # `summary.rate_per_min` sums every ACTIVE session's rate, and the four
        # harnesses that never measure one contribute the same 0 a reporting
        # harness sends for a session that generated nothing — so on a mixed board
        # the footer's single number is the measured part of the output printed as
        # all of it. The ledger dashes those rows one at a time; this is the number
        # a reader takes for the board, and calm used to print it bare while the
        # regular view's tile said the same total was a floor.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
const foot = h => (h.match(/class="cm-foot"><span>([^<]*)</) || [])[1];
// The qualification exactly as rendered: the footer item after the total, and
// the tooltip on it. null when there is none.
const floorOf = h => {
  const m = h.match(/tok\\/min<\\/span><span title="([^"]*)">([^<]*)</);
  return m ? [m[2], m[1]] : null;
};
const rated = (sessions, total) => burnBoard(
  {sessions, summary: Object.assign({}, payload([]).summary, {rate_per_min: total,
    active_sessions: sessions.filter(x => x.active).length})});
// One measured session, one active session whose harness takes no measurement.
const partial = rated([working("live", "claude", 450), working("mute", "copilot", 0)], 450);
render(partial);
out.partial = foot(__els.app.innerHTML);
out.partialNote = floorOf(__els.app.innerHTML);
// The regular view's tile, on the SAME payload: same numeral, same sentence.
const tile = rateTile(partial);
out.tileVal = (tile.match(/class="tile-val">([^<]*)</) || [])[1];
out.tileSub = (tile.match(/class="tile-sub"[^>]*>([^<]*)</) || [])[1];
// Every active session measured: an exact total, said exactly, with nothing
// hedging it. This is the common case and it must stay unqualified.
render(rated([working("live", "claude", 450), working("fast", "codex", 3100)], 3550));
out.exact = foot(__els.app.innerHTML);
out.exactNote = floorOf(__els.app.innerHTML);
out.exactClean = !/≥|a floor|no rate from/.test(__els.app.innerHTML);
// The whole board unmeasured: a bare 0 here would read as "nothing is being
// generated", which is the one thing this payload cannot say. Singular, too.
render(rated([working("mute", "copilot", 0)], 0));
out.blind = foot(__els.app.innerHTML);
out.blindNote = floorOf(__els.app.innerHTML);
// The same 0, measured. Claude reports a rate, so a session of it generating
// nothing IS in the total, correctly and completely — the absence of a
// measurement is what makes a floor, never the size of one.
render(rated([working("zero", "claude", 0)], 0));
out.measuredZero = foot(__els.app.innerHTML);
out.measuredZeroNote = floorOf(__els.app.innerHTML);
// The sum is over ACTIVE sessions, so an inactive unmeasured row is not missing
// from it and must not make the total a floor.
render(rated([working("live", "claude", 450),
              mk({sid: "gone", session: "gone", harness: "copilot", state: "working",
                  active: false, last_activity: 99990, rate_per_min: 0})], 450));
out.inactive = foot(__els.app.innerHTML);
out.inactiveNote = floorOf(__els.app.innerHTML);
// Two harnesses missing: both named, and the sentence agrees with itself.
render(rated([working("live", "claude", 450), working("mute", "copilot", 0),
              working("cur", "cursor", 0)], 450));
out.twoNote = floorOf(__els.app.innerHTML);
console.log(JSON.stringify(out));
"""
        )
        out = self.run_calm(checks)
        self.assertEqual("3 harnesses · ≥ 450 tok/min", out["partial"])
        self.assertEqual(
            [
                "no rate from 1 of 2 active sessions — a floor",
                (
                    "Copilot reports no token accounting, so what its sessions are burning"
                    " is missing from this total — and is not zero."
                ),
            ],
            out["partialNote"],
            "the footer total does not say how much of the board it could not see",
        )
        # The two views on one payload. A reader switching modes with `c` must not
        # be told the same total is a floor in one and a figure in the other.
        self.assertEqual("≥ 450", out["tileVal"])
        self.assertEqual(out["partialNote"][0], out["tileSub"], "the two modes word it differently")
        self.assertEqual("3 harnesses · 3,550 tok/min", out["exact"])
        self.assertIsNone(out["exactNote"], "an exact total was hedged")
        self.assertTrue(out["exactClean"], "a floor mark survived onto a fully measured board")
        self.assertEqual("3 harnesses · ≥ 0 tok/min", out["blind"])
        self.assertEqual("no rate from 1 of 1 active session — a floor", out["blindNote"][0])
        self.assertEqual("3 harnesses · 0 tok/min", out["measuredZero"])
        self.assertIsNone(out["measuredZeroNote"], "a measured zero was called a floor")
        self.assertEqual("3 harnesses · 450 tok/min", out["inactive"])
        self.assertIsNone(
            out["inactiveNote"], "a session outside the total was counted as missing from it"
        )
        self.assertEqual(
            [
                "no rate from 2 of 3 active sessions — a floor",
                (
                    "Copilot, Cursor report no token accounting, so what their sessions are"
                    " burning is missing from this total — and is not zero."
                ),
            ],
            out["twoNote"],
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_footer_total_says_when_a_harness_could_not_be_read(self) -> None:
        # The other way a total is a floor, and the one no session count can see: a
        # discovered harness whose collector raised publishes an `error` and no
        # sessions at all. The strip badges it `— collector error`, so the failure
        # is disclosed — but the footer's numeral sat beside that badge unqualified,
        # counting the sessions it did have and finding them all measured. A total
        # missing a whole harness is the least exact number on the board.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
const foot = h => (h.match(/class="cm-foot"><span>([^<]*)</) || [])[1];
const floorOf = h => {
  const m = h.match(/tok\\/min<\\/span><span title="([^"]*)">([^<]*)</);
  return m ? [m[2], m[1]] : null;
};
// One strip apart from the error, so nothing else can account for a difference.
const okStrip = [strip[0], {...strip[1]}, strip[2]];
const errStrip = [strip[0], {...strip[1], error: "OSError: [Errno 13] Permission denied"},
                  strip[2]];
const rated = (sessions, harnesses, total) => burnBoard({harnesses, sessions,
  summary: Object.assign({}, payload([]).summary, {rate_per_min: total,
    active_sessions: sessions.filter(x => x.active).length})});
const one = [working("live", "claude", 2010)];
const errored = rated(one, errStrip, 2010);
render(errored);
out.errored = foot(__els.app.innerHTML);
out.erroredNote = floorOf(__els.app.innerHTML);
// The regular view's tile, on the SAME payload: same numeral, same sentence.
const tile = rateTile(errored);
out.tileVal = (tile.match(/class="tile-val">([^<]*)</) || [])[1];
out.tileSub = (tile.match(/class="tile-sub"[^>]*>([^<]*)</) || [])[1];
// Every discovered harness read, every active session measured: an exact total,
// with nothing hedging it. Codex having no sessions is not a hole.
render(rated(one, okStrip, 2010));
out.exact = foot(__els.app.innerHTML);
out.exactNote = floorOf(__els.app.innerHTML);
out.exactClean = !/≥|a floor|could not be read/.test(__els.app.innerHTML);
// The strip still discloses the failure the footer now qualifies — a reader has
// to be able to get from "a floor" to which harness it was.
render(errored);
out.badge = __els.app.innerHTML.includes("Codex — collector error");
// Both holes at once, each counted as itself.
render(rated([working("live", "claude", 2010), working("mute", "copilot", 0)],
             errStrip, 2010));
out.bothNote = floorOf(__els.app.innerHTML);
console.log(JSON.stringify(out));
"""
        )
        out = self.run_calm(checks)
        self.assertEqual("3 harnesses · ≥ 2,010 tok/min", out["errored"])
        self.assertEqual(
            [
                "1 harness could not be read — a floor",
                (
                    "Codex failed to collect, so none of its sessions reached this total"
                    " — unread, not idle."
                ),
            ],
            out["erroredNote"],
            "the footer presented a total missing a whole harness as exact",
        )
        # The two views on one payload. A reader switching modes with `c` must not
        # be told the same total is a floor in one and a figure in the other.
        self.assertEqual("≥ 2,010", out["tileVal"])
        self.assertEqual(out["erroredNote"][0], out["tileSub"], "the two modes word it differently")
        self.assertEqual("3 harnesses · 2,010 tok/min", out["exact"])
        self.assertIsNone(out["exactNote"], "an exact total was hedged")
        self.assertTrue(out["exactClean"], "a floor mark survived onto a fully read board")
        self.assertTrue(out["badge"], "the strip stopped naming the harness that failed")
        self.assertEqual(
            [
                "no rate from 1 of 2 active sessions · 1 harness could not be read — a floor",
                (
                    "Copilot reports no token accounting, so what its sessions are burning"
                    " is missing from this total — and is not zero."
                    " Codex failed to collect, so none of its sessions reached this total"
                    " — unread, not idle."
                ),
            ],
            out["bothNote"],
            "the note reported one hole and dropped the other",
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_board_generating_nothing_is_not_ranked_fastest_first(self) -> None:
        # Comparable is not the same as there being something to compare. The
        # regular view has always refused to mark a `fastest` card when the highest
        # known rate is zero — a board where nothing is generating has no fastest
        # session — and calm ranked those rows anyway, so the divider claimed
        # "fastest first" and the top row was an agent producing nothing. The rule
        # is burnRacers() now, asked by both views, because this is the second
        # parity fault after a fix that claimed one shared predicate had made them
        # impossible: one predicate for which rows may be compared was not one rule
        # for whether the comparison exists.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
calmAction("sort", "burn");
// Every working row measured, every measurement zero, plus the two kinds of row
// that were never in the ranking.
const d = burnBoard({sessions: [working("a", "claude", 0), working("b", "codex", 0),
  working("mute", "copilot", 0), stopped("stop", "claude", 9000, 110)]});
render(d);
const h = __els.app.innerHTML;
out.order = seq(h);
out.dividers = dividers(h);
out.rows = rows();
out.calmRanked = groupRows(h, "fastest first") || [];
out.zeroGroup = groupRows(h, "all measured at zero");
// The same payload object the ledger just rendered, so nothing about the two
// answers can be blamed on two payloads.
out.regularLeaders = [...burnLeaders(d).keys];
out.regularPills = d.sessions.filter(x => x.state === "working")
  .map(s => (workingCard(d, s).match(/>(fastest[a-z ]*)</) || [null, null])[1]);
// The cells were never the lie: a measured zero keeps its number, an unmeasured
// row keeps its dash. Only the placement and the divider invented the race.
out.cells = [rateCellOf(h, "claude:a"), rateCellOf(h, "copilot:mute")];
// One positive rate anywhere makes it a race, and then every measured row is in
// it — the zeroes included, sorted last, where they are genuinely slowest.
render(burnBoard({sessions: [working("a", "claude", 0), working("b", "codex", 5)]}));
out.racing = [dividers(__els.app.innerHTML),
              groupRows(__els.app.innerHTML, "fastest first")];
console.log(JSON.stringify(out));
"""
        )
        out = self.run_calm(checks)
        self.assertEqual(4, out["rows"], "the ordering dropped a row")
        self.assertEqual(
            [],
            out["calmRanked"],
            'a board where nothing is generating was headed "fastest first"',
        )
        self.assertEqual(
            out["regularLeaders"],
            out["calmRanked"],
            "the two views disagree about whether there is a fastest session",
        )
        self.assertEqual([None, None, None], out["regularPills"])
        self.assertEqual(["claude:a", "codex:b"], out["zeroGroup"])
        self.assertEqual(
            [
                ["all measured at zero · no ranking to make", 2],
                ["no rate reported · cannot be ranked", 1],
                ["not working now · not in the ranking", 1],
            ],
            out["dividers"],
            "the groups do not account for every row, or do not say what they are",
        )
        self.assertEqual(["a", "b", "mute", "stop"], out["order"])
        self.assertEqual(["0 /m", "—"], out["cells"], "a cell was changed instead of the divider")
        self.assertEqual(
            [[["fastest first · 10m mean", 2]], ["codex:b", "claude:a"]],
            out["racing"],
            "one measured rate above zero is a race and every measured row is in it",
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_every_ranked_row_shows_the_number_it_was_ranked_on(self) -> None:
        # Three states in the rate cell, and each may mean exactly one thing: a
        # number is a measurement (a real 0 included), a dash is a harness that
        # never took one, an empty cell is a row that is not working. The cell used
        # to fill by rate rather than by bucket, so a non-working row holding a
        # MEASURED 0 rendered blank while an unmeasured row rendered a dash — the
        # absence reading as less than the unknown, which is backwards — and the
        # blank row was in the ranking, ranked on a number it never showed.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
calmAction("sort", "burn");
render(contra());
const h = __els.app.innerHTML;
// Nothing under the ranking heading may be silent about what it was ranked on.
out.rankedCells = groupRows(h, "fastest first").map(k => [k, rateCellOf(h, k)]);
out.cells = ["codex:work", "claude:zed", "copilot:mute", "claude:stop",
             "claude:held", "copilot:hush"].map(k => [k, rateCellOf(h, k)]);
// The dash is the working rows nobody measured and nothing else: on a row that
// is not working it would answer a question this column has stopped asking.
out.dashes = (h.match(/>—</g) || []).length;
// The tooltip follows the cell. An empty cell makes no claim, so it explains no
// number, and a stopped row's stale mean does not arrive as a tooltip either.
out.workTip = rowOf(h, "codex:work").includes(
  "300 tokens per minute, averaged over the last 10m");
out.muteTip = rowOf(h, "copilot:mute").includes("this harness reports no token rate");
out.stopTip = rowOf(h, "claude:stop").includes("averaged over the last")
  || rowOf(h, "claude:stop").includes("9,000");
// The rule is the row's bucket, not the ordering: the same cells under an order
// that ranks nothing.
calmAction("sort", "attention");
render(contra());
out.underAttention = ["claude:zed", "claude:stop", "copilot:mute"]
  .map(k => rateCellOf(__els.app.innerHTML, k));
console.log(JSON.stringify(out));
"""
        )
        out = self.run_calm(checks)
        for key, cell in out["rankedCells"]:
            with self.subTest(row=key):
                self.assertTrue(
                    cell.endswith(" /m"), f"{key} was ranked on a number it does not show: {cell!r}"
                )
        self.assertEqual(
            [
                ["codex:work", "300 /m"],
                ["claude:zed", "0 /m"],
                ["copilot:mute", "—"],
                ["claude:stop", ""],
                ["claude:held", ""],
                ["copilot:hush", ""],
            ],
            out["cells"],
            "the rate cell's three states no longer mean one thing each",
        )
        self.assertEqual(1, out["dashes"], "a dash landed on a row that is not working")
        self.assertTrue(out["workTip"])
        self.assertTrue(out["muteTip"])
        self.assertFalse(out["stopTip"], "a stopped session's stale mean survived as a tooltip")
        self.assertEqual(["0 /m", "", "—"], out["underAttention"], "the cell reads the ordering")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_burn_ordering_names_the_window_it_actually_ranked_on(self) -> None:
        # The published rate is a trailing mean over the server's
        # `rate_window_sec`, not a reading of this instant, and immediacy is the
        # only thing this ordering has over the Output rate tile. So the wording
        # is derived from the number the payload sent: a hardcoded "10 min" would
        # go on reading 10 min the day the server's window changed, which is the
        # label lying about its own arithmetic.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
calmAction("sort", "burn");
const label = h => (h.match(/cm-div-k">fastest first[^<]*/) || [""])[0];
render(burnBoard());
out.tenMin = [label(__els.app.innerHTML),
              rowOf(__els.app.innerHTML, "codex:fast").includes(
                "3,100 tokens per minute, averaged over the last 10m")];
render(burnBoard({rate_window_sec: 300}));
out.fiveMin = [label(__els.app.innerHTML),
               __els.app.innerHTML.includes("averaged over the last 5m"),
               __els.app.innerHTML.includes("10m")];
render(burnBoard({rate_window_sec: 5400}));
out.ninetyMin = label(__els.app.innerHTML);
// A payload from before the field existed still gets a window, not a blank or a
// NaN, and not a claim about now.
const stale = burnBoard();
delete stale.rate_window_sec;
render(stale);
out.absent = label(__els.app.innerHTML);
console.log(JSON.stringify(out));
"""
        )
        out = self.run_calm(checks)
        self.assertEqual(
            ['cm-div-k">fastest first · 10m mean', True],
            out["tenMin"],
            "the ordering did not state the window it ranked on",
        )
        self.assertEqual(
            ['cm-div-k">fastest first · 5m mean', True, False],
            out["fiveMin"],
            "the window label is hardcoded rather than read from the payload",
        )
        self.assertEqual('cm-div-k">fastest first · 1h 30m mean', out["ninetyMin"])
        self.assertEqual('cm-div-k">fastest first · 10m mean', out["absent"])
        # Nothing on the ordering may call the figure current: it is a mean whose
        # newest input can be ten minutes old.
        for claim in ("right now", "now ", "live", "instant", "current"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, out["tenMin"][0])

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
