from __future__ import annotations

import json
import shutil
import unittest
from typing import Any

from .page_harness import PageJsHarness


class SessionViewTest(PageJsHarness):
    """The session display mode: one session's dispatch tree and goal line.

    These execute the shipped app.js: every assertion is about what the page
    does with a payload, not about the assembled document's source text.
    """

    # Globals the page reads at load (localStorage) and a stub for the session
    # picker's click channel.
    @staticmethod
    def prelude(saved: str | None = None) -> str:
        seed = "{}" if saved is None else json.dumps({"cargento.displayMode": saved})
        return f"""
let __store = {seed};
const localStorage = {{
  getItem(k){{ return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; }},
  setItem(k, v){{ __store[k] = String(v); }}
}};
let __timers = [];
const setTimeout = fn => {{ __timers.push(fn); return __timers.length; }};
"""

    def run_session(
        self, checks: str, *, saved: str | None = None, hash_val: str | None = None
    ) -> Any:
        prelude = self.prelude(saved)
        if hash_val is not None:
            prelude += f'\nlocation.hash = "{hash_val}";\n'
        return self._run_page_js(self.FIXTURE + checks, prelude=prelude)

    # A fixture FO session with two workflows and three entities at different
    # stages. The goal is the workflow frontmatter `title` scalar, already
    # published as `workflow.goal` by spacedock.read_workflow.
    #
    # `__els.app` is registered because these tests drive `render()`. The
    # original set called `sessionView()` directly, which is why deleting the
    # whole `displayMode === "session"` branch out of `render()` left all
    # fifteen of them green: the view was tested and the route to it was not.
    FIXTURE = """
__els.app = {innerHTML: "", className: "", querySelectorAll: () => []};
const mk = o => Object.assign({
  harness: "claude", session: "1234abcd", sid: "1234abcd", project: "repo/proj",
  title: "Active dispatch", last_prompt: "", state: "working", state_detail: "running Bash",
  active: true, last_activity: 990, rate_per_min: 10, total: 0, done: 0, open: 0,
  progress_pct: 0, eta_h: null, turn: null, subagents: [], tasks: [], spacedock: null
}, o);
const sdWf = (over) => Object.assign({
  workflow: "debug-flywheel", stages: ["intake", "review", "fix-and-harden"],
  goal: "", entities: []
}, over);
const ent = (slug, stage, live, cycle) => ({slug, stage, live: !!live, cycle: cycle || ""});
const fo = mk({
  spacedock: {
    role: "first-officer",
    workflows: [
      sdWf({goal: "Ship session view", entities: [
        ent("drc-1", "review", false, "c2"),
        ent("drc-2", "fix-and-harden", true),
        ent("drc-3", "intake", false)
      ]}),
      sdWf({workflow: "other-wf", goal: "", stages: ["intake", "posted"], entities: [
        ent("pr-7", "posted", false)
      ]})
    ]
  }
});
const board = sessions => ({
  generated: 100000, window_hours: 24, show_all: false,
  rate_window_sec: 600,
  harnesses: [{key: "claude", label: "Claude Code", discovered: true, error: null, reports_rate: true}],
  summary: {needs_input: 0, working: 1, rate_per_min: 10, active_sessions: 1,
            open_tasks: 0, progress_pct: 0, total_tasks: 0, total_done: 0},
  sessions
});
"""

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_session_mode_carries_the_ask_band_and_the_liveness_line(self) -> None:
        # Both of these are board-level and both were missing. An ask can come
        # from a session this view is not the one for, so a reader parked here
        # had a question on the board and no way to answer it. And nothing on a
        # dispatch spine ticks, so without the dot a dead server looks exactly
        # like a live tree.
        checks = """
const out = {};
const d = board([fo]);
// `ask: true` is the capability flag `askBand` gates on — the band is empty
// without it however many asks the payload carries.
d.ask = true;
d.asks = [{id: "a1", harness: "claude", session_id: "9999zzzz", project: "repo/other",
           question: "Ship it?", options: ["yes", "no"], age_sec: 5}];
d.summary.needs_input = 0;
setDisplayMode("session");
sessionViewKey = "claude:1234abcd";
render(d);
const html = __els.app.innerHTML;
out.band = html.includes('id="waitband"');
out.question = html.includes("Ship it?");
out.liveDot = html.includes('id="live-dot"');
out.liveStatus = html.includes('id="live-status"');
out.title = document.title;
out.tree = html.includes("sv-tree");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["band"], "session mode rendered no asks band")
        self.assertTrue(out["question"], "an outstanding question was not rendered")
        self.assertTrue(out["liveDot"], "session mode rendered no liveness dot")
        self.assertTrue(out["liveStatus"], "refresh()'s catch arm had no #live-status to write")
        # The count is `waitingOnYou`, the same as the other three modes: a
        # pending ask counts, and a title that disagreed with the band above it
        # was the reason to change it.
        self.assertTrue(out["title"].startswith("(1!)"), out["title"])
        self.assertTrue(out["tree"], "the tree stopped rendering")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_stage_named_constructor_does_not_throw(self) -> None:
        # `byStage` groups entities under workflow-authored stage names. On a
        # bare object `byStage["constructor"]` is an inherited function, so
        # `|| []` keeps it and `.push` throws inside render() — which wedges the
        # board on "stalled · retrying" until a reload. Falsifying edit: put
        # `const byStage = {}` back.
        checks = """
const out = {};
const d = board([mk({spacedock: {role: "first-officer", workflows: [
  sdWf({workflow: "hostile", stages: ["constructor", "toString", "__proto__"], entities: [
    ent("drc-9", "constructor", true), ent("drc-8", "toString", false)
  ]})
]}})]);
setDisplayMode("session");
sessionViewKey = "claude:1234abcd";
try{ render(d); out.threw = false; }catch(e){ out.threw = true; out.msg = String(e); }
out.html = __els.app.innerHTML.includes("drc-9");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertFalse(out.get("threw"), out.get("msg"))
        self.assertTrue(out["html"], "the entity under a prototype-named stage was dropped")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_board_keys_do_not_act_on_a_queue_this_view_does_not_draw(self) -> None:
        # `j`, `k` and Enter move and copy from the gate queue. The session view
        # draws no gate band, so Enter put a session id on the clipboard with no
        # visible cause. `c` and `g` still work and both leave. Falsifying edit:
        # drop the `displayMode === "session"` early return in calm.js.
        checks = """
const out = {};
const blocked = mk({sid: "bbbb2222", session: "bbbb2222", state: "needs_input",
                    state_detail: "waiting on you", flag: "blocked"});
const d = board([fo, blocked]);
d.summary.needs_input = 1;
setDisplayMode("session");
sessionViewKey = "claude:1234abcd";
render(d);
const before = waitCursorKey;
__fire("keydown", {key: "j", target: {}, preventDefault(){}, stopPropagation(){}});
__fire("keydown", {key: "k", target: {}, preventDefault(){}, stopPropagation(){}});
__fire("keydown", {key: "Enter", target: {}, preventDefault(){}, stopPropagation(){}});
out.cursorUnmoved = waitCursorKey === before;
out.stillSession = displayMode;
// `g` is one of the two that still applies, and it leaves on the way to the
// queue rather than landing a cursor nothing draws.
__fire("keydown", {key: "g", target: {}, preventDefault(){}, stopPropagation(){}});
out.afterG = displayMode;
out.gCursor = waitCursorKey;
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["cursorUnmoved"], "j/k/Enter moved a cursor the view does not draw")
        self.assertEqual("session", out["stillSession"])
        self.assertEqual("regular", out["afterG"], "`g` left the reader in a view with no queue")
        self.assertEqual("claude:bbbb2222", out["gCursor"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_ac1_session_view_renders_dispatch_tree(self) -> None:
        """AC-1: the session view renders one tree per workflow, with entity
        slugs, stage names, and the sd-live class on live entities. Fails if
        the tree-rendering branch is deleted."""
        checks = """
const out = {};
sessionViewKey = "claude:1234abcd";
const h = sessionView(board([fo]));
out.hasWf1 = h.includes("debug-flywheel");
out.hasWf2 = h.includes("other-wf");
// AC-1: every entity slug is present.
out.slugs = ["drc-1", "drc-2", "drc-3", "pr-7"].map(s => h.includes(s));
// AC-1: every stage name is present.
out.stages = ["intake", "review", "fix-and-harden", "posted"].map(s => h.includes(s));
// AC-1: the live entity (drc-2) carries the sd-live class.
out.liveClass = h.includes('class="sv-ent sd-live"');
// A non-live entity must NOT carry sd-live.
out.parkedNotLive = !h.includes('sv-ent sd-live">drc-1') && !h.includes('sv-ent sd-live">drc-3');
// Cycle label present on drc-1.
out.cycle = h.includes("c2");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["hasWf1"])
        self.assertTrue(out["hasWf2"])
        self.assertEqual([True, True, True, True], out["slugs"], "an entity slug is missing")
        self.assertEqual([True, True, True, True], out["stages"], "a stage name is missing")
        self.assertTrue(out["liveClass"], "the live entity does not carry sd-live")
        self.assertTrue(out["parkedNotLive"], "a parked entity was marked live")
        self.assertTrue(out["cycle"], "the cycle label is missing")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_ac2a_goal_line_shows_stated_goal(self) -> None:
        """AC-2a: when the workflow frontmatter carries a title, the session
        view renders it as a one-line goal header. Fails if the goal field is
        dropped from the payload."""
        checks = """
const out = {};
sessionViewKey = "claude:1234abcd";
const h = sessionView(board([fo]));
out.hasGoal = h.includes('class="sv-goal"');
out.goalText = h.includes("Ship session view");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["hasGoal"], "the goal header element is missing")
        self.assertTrue(out["goalText"], "the goal text is missing from the header")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_ac2b_no_goal_line_when_title_absent(self) -> None:
        """AC-2b: when the workflow frontmatter carries no title, no goal line
        renders. Fails if the renderer emits a goal element when goal is empty."""
        checks = """
const out = {};
sessionViewKey = "claude:1234abcd";
// The second workflow (other-wf) has goal: "" — it must not render a goal.
const h = sessionView(board([fo]));
// Check that no sv-goal element appears for the other-wf section. The
// first workflow has a goal, so we need to check per-workflow. The session
// view renders workflows in order, so we look at the HTML after "other-wf".
const wf2Start = h.indexOf("other-wf");
const wf2Section = h.slice(wf2Start);
out.noGoalForWf2 = !wf2Section.includes('class="sv-goal"');
// Also test with a session whose only workflow has no goal.
const noGoal = mk({
  spacedock: {
    role: "first-officer",
    workflows: [sdWf({goal: "", entities: [ent("drc-1", "review", false)]})]
  }
});
const h2 = sessionView(board([noGoal]));
out.noGoalAtAll = !h2.includes('class="sv-goal"');
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["noGoalForWf2"], "a goal was fabricated for a workflow with no title")
        self.assertTrue(out["noGoalAtAll"], "a goal was fabricated when no title is present")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_ac2_no_hardcoded_goal_fallback(self) -> None:
        """AC-2 falsifying edit: hardcoding a goal string as a fallback when
        goal is absent must fail this test. No fabricated or placeholder text
        should appear."""
        checks = """
const out = {};
sessionViewKey = "claude:1234abcd";
const noGoal = mk({
  spacedock: {
    role: "first-officer",
    workflows: [sdWf({goal: "", entities: [ent("drc-1", "review", false)]})]
  }
});
const h = sessionView(board([noGoal]));
out.noCurrentSprint = !h.includes("Current sprint");
out.noGoalLabel = !h.includes('class="sv-goal"');
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["noCurrentSprint"], "a hardcoded goal fallback was rendered")
        self.assertTrue(out["noGoalLabel"], "a goal element was rendered for an empty goal")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_session_picker_shown_when_no_key(self) -> None:
        """Entering session mode with no session selected shows a picker, not
        a blank or fabricated view."""
        checks = """
const out = {};
sessionViewKey = null;
const h = sessionView(board([fo]));
out.hasPicker = h.includes("sv-picker");
out.hasPickRow = h.includes('data-calm="session" data-arg="claude:1234abcd"');
out.noGoalWhenPicking = !h.includes('class="sv-goal"');
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["hasPicker"], "the picker was not shown for a null key")
        self.assertTrue(out["hasPickRow"], "the picker row is missing")
        self.assertTrue(out["noGoalWhenPicking"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_set_display_mode_accepts_session(self) -> None:
        """Test plan item 4: setDisplayMode("session") sets displayMode to
        "session", persists to localStorage, and triggers render(lastData).
        setDisplayMode("invalid") is a no-op."""
        checks = """
const out = {};
const d = board([fo]);
render(d);
out.before = displayMode;
setDisplayMode("session");
out.mode = displayMode;
out.stored = __store["cargento.displayMode"];
// An invalid value is a no-op.
setDisplayMode("invalid");
out.rejectsJunk = displayMode;
// The clear is on the way *out*, not the way in — asserting it here after
// entering only ever compared null to null, because nothing had set a key.
sessionViewKey = "claude:1234abcd";
setDisplayMode("regular");
out.clearedOnLeave = sessionViewKey === null;
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertEqual("regular", out["before"])
        self.assertEqual("session", out["mode"], "setDisplayMode did not accept 'session'")
        self.assertEqual("session", out["stored"], "the mode was not persisted")
        self.assertEqual("session", out["rejectsJunk"], "an invalid mode was accepted")
        self.assertTrue(out["clearedOnLeave"], "leaving session mode left a stale key")

    # ── rework: routable URL, distinct empty states, calm navigation ─────────

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_url_hash_restores_session_on_init(self) -> None:
        """Rework BUG 1: a URL hash (#session=<key>) restores the session view
        on page load. displayMode is "session" and sessionViewKey is the
        decoded key."""
        checks = """
const out = {};
out.mode = displayMode;
out.key = sessionViewKey;
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks, hash_val="#session=claude:1234abcd")
        self.assertEqual("session", out["mode"], "hash did not restore session mode")
        self.assertEqual("claude:1234abcd", out["key"], "hash did not restore the session key")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_url_hash_synced_on_session_enter(self) -> None:
        """Rework BUG 1: entering session mode via calmAction("session", key)
        sets location.hash to #session=<encoded key>."""
        checks = """
const out = {};
const d = board([fo]);
render(d);
calmAction("session", "claude:1234abcd");
out.hash = location.hash;
out.mode = displayMode;
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertIn("session=claude", out["hash"], "hash was not set")
        self.assertEqual("session", out["mode"], "did not enter session mode")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_url_hash_cleared_on_leave(self) -> None:
        """Rework BUG 1: leaving session mode (back to regular) clears the
        session hash."""
        checks = """
const out = {};
const d = board([fo]);
render(d);
calmAction("session", "claude:1234abcd");
out.hashWhenSession = location.hash;
setDisplayMode("regular");
out.hashAfterLeave = location.hash;
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertIn("session=", out["hashWhenSession"], "hash was not set in session mode")
        self.assertNotIn("session=", out["hashAfterLeave"], "hash was not cleared on leaving")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_hashchange_navigates_back(self) -> None:
        """Rework BUG 1: a hashchange to no session hash leaves session mode
        (browser back button)."""
        checks = """
const out = {};
const d = board([fo]);
render(d);
calmAction("session", "claude:1234abcd");
out.modeIn = displayMode;
// Simulate browser back: hash cleared, hashchange fires.
suppressHashChange = false;
location.hash = "";
__fire("window:hashchange", {});
out.modeOut = displayMode;
out.keyOut = sessionViewKey;
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertEqual("session", out["modeIn"])
        self.assertNotEqual("session", out["modeOut"], "did not leave session mode on hashchange")
        self.assertIsNone(out["keyOut"], "sessionViewKey was not cleared on hashchange")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_empty_state_not_a_spacedock_session(self) -> None:
        """Rework BUG 3b: a session with spacedock: null shows "Not a
        Spacedock session", not "no workflows"."""
        checks = """
const out = {};
sessionViewKey = "claude:1234abcd";
const notSd = mk({spacedock: null});
const h = sessionView(board([notSd]));
out.isNotSpacedock = h.includes("Not a Spacedock session");
out.noOldMessage = !h.includes("no Spacedock workflows");
out.hasBack = h.includes("sv-back");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["isNotSpacedock"], "the not-a-Spacedock message is missing")
        self.assertTrue(out["noOldMessage"], "the old generic message is still shown")
        self.assertTrue(out["hasBack"], "the back button is missing")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_empty_state_fo_no_entities(self) -> None:
        """Rework BUG 3c: a first-officer session with empty workflows shows
        "First officer with no in-flight entities" (pointing at the freshness
        fix), not a blank panel."""
        checks = """
const out = {};
sessionViewKey = "claude:1234abcd";
const foEmpty = mk({
  spacedock: {role: "first-officer", workflows: []}
});
const h = sessionView(board([foEmpty]));
out.isFoNoEntities = h.includes("First officer with no in-flight entities");
out.mentionsFreshness = h.includes("freshness");
out.noOldMessage = !h.includes("no Spacedock workflows");
out.hasBack = h.includes("sv-back");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["isFoNoEntities"], "the FO no-entities message is missing")
        self.assertTrue(out["mentionsFreshness"], "the freshness-gate pointer is missing")
        self.assertTrue(out["noOldMessage"], "the old generic message is still shown")
        self.assertTrue(out["hasBack"], "the back button is missing")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_empty_state_worker_session(self) -> None:
        """Rework BUG 3d: a non-FO Spacedock session (ensign/worker) with empty
        workflows shows the role + "session", not a blank panel."""
        checks = """
const out = {};
sessionViewKey = "claude:1234abcd";
const ensign = mk({
  spacedock: {role: "ensign", workflows: []}
});
const h = sessionView(board([ensign]));
out.isWorkerSession = h.includes("ensign session");
out.noOldMessage = !h.includes("no Spacedock workflows");
out.hasBack = h.includes("sv-back");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["isWorkerSession"], "the worker session message is missing")
        self.assertTrue(out["noOldMessage"], "the old generic message is still shown")
        self.assertTrue(out["hasBack"], "the back button is missing")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_loading_state_when_session_not_found(self) -> None:
        """Rework BUG 3a: when the session key is set but the session is not
        in the current data, a loading state shows — not the picker, not a
        blank panel."""
        checks = """
const out = {};
sessionViewKey = "claude:deadbeef";
const h = sessionView(board([fo]));
out.isLoading = h.includes("sv-loading");
out.hasBack = h.includes("sv-back");
out.noPicker = !h.includes("sv-picker");
out.mentionsKey = h.includes("claude:deadbeef");
out.href = (h.match(/href="([^"]*)"/) || [])[1];
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks, hash_val="#session=claude%3Adeadbeef")
        self.assertTrue(out["isLoading"], "the loading state is missing")
        self.assertTrue(out["hasBack"], "the back button is missing")
        self.assertTrue(out["noPicker"], "the picker was shown instead of loading")
        self.assertTrue(out["mentionsKey"], "the session key is not in the loading message")
        # The recovery link's whole point is to widen the window and come back
        # to *this* session. Turning the fragment into a query parameter
        # (`?all=1&session=…`) dropped the target on the way: mode.js reads the
        # hash, and nothing reads a `session` query parameter, so the link
        # landed on the picker with the session it named nowhere in sight.
        self.assertEqual("?all=1#session=claude%3Adeadbeef", out["href"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_back_button_in_session_view(self) -> None:
        """Rework BUG 1: the session view has a back button that navigates to
        the overview (data-calm="mode" data-arg="regular")."""
        checks = """
const out = {};
sessionViewKey = "claude:1234abcd";
const h = sessionView(board([fo]));
out.hasBack = h.includes('data-calm="mode" data-arg="regular"');
out.hasBackText = h.includes("overview");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["hasBack"], "the back button is missing")
        self.assertTrue(out["hasBackText"], "the back button text is missing")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_calm_expansion_has_view_button(self) -> None:
        """Rework BUG 2: the calm expansion panel has a "view" button
        (data-calm="session") that navigates to the session view."""
        checks = """
const out = {};
const d = board([fo]);
const row = calmRow(d, fo);
calmOpenKey = row.key;
const h = calmExpansion(row, d);
out.hasViewBtn = h.includes('data-calm="session"');
out.hasViewText = h.includes(">view<");
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertTrue(out["hasViewBtn"], "the view button is missing from calm expansion")
        self.assertTrue(out["hasViewText"], "the view button text is missing")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_calm_view_button_enters_session_mode(self) -> None:
        """Rework BUG 2: clicking the calm "view" button enters session mode
        with the correct session key."""
        checks = """
const out = {};
const d = board([fo]);
render(d);
calmAction("session", "claude:1234abcd");
out.mode = displayMode;
out.key = sessionViewKey;
out.hash = location.hash;
console.log(JSON.stringify(out));
"""
        out = self.run_session(checks)
        self.assertEqual("session", out["mode"], "did not enter session mode")
        self.assertEqual("claude:1234abcd", out["key"], "session key was not set")
        self.assertIn("session=", out["hash"], "hash was not synced")
