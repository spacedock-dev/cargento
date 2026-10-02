"""A press that awaits the server shows it is working (owner, 2026-10-02).

The owner typed a goal and two outcome lines, pressed Save intent, and "nothing happened for a
couple seconds and then the page updated". Measured on the owner's board, the POST took about
900 ms and the first change to the page came at about 1.3 s, with Save intent a live button
throughout. The rulings: every control that awaits a fetch is `aria-disabled` and `aria-busy`
while it is in flight, shows a spinner and a short busy label at the same width, keeps focus,
answers a second press with nothing, and comes back with a true sentence when the request is
lost; the start is said after 400 ms and the outcome when it is drawn.

Every assertion is on the assembled bundle's markup, what it sends, or what its live region
carries.
"""

from __future__ import annotations

import re
import shutil
import unittest
from typing import Any

from . import test_next_cockpit as cockpit_tests
from .test_next_intent_draft import TYPED, _DraftPage, drift_of, intent_of
from .test_next_intent_editor import css
from .visible_text import visible_text

SAVE_KEY = "held:claude:focus-1:intent:save"
DOM = cockpit_tests.CockpitCuesReachTheReaderTest.ANNOUNCER_DOM
SAVED = "Saved as a new revision."
REFUSED = "Not saved. The server refused the write, and your words are still in the box."
UNCONFIRMED = (
    "Cargento did not answer, so this page cannot tell whether your intent was saved. Your "
    "words are still in the box."
)
EDITED = "Save your intent, or undo your edit, to analyze drift."

# The save's POST and, once `__holdData` is set, the refresh after it, each held until the test
# lets it go. A held request honours its abort signal, as `fetch` does.
HELD = """
let __annotates = [];
let __answer = null;
let __holdData = false;
let __dataGets = 0;
let __dataAnswer = null;
const __timeouts = [];
const __base = __fetchImpl;
__fetchImpl = (url, init) => {
  if(String(url) === "/api/annotate"){
    const body = JSON.parse(init.body);
    __annotates.push(body);
    return new Promise((resolve, reject) => {
      __answer = {resolve(outcome = "stored"){
        if(outcome === "stored"){
          if(typeof body.goal === "string") __s.annotation_goal = body.goal;
          __s.annotation_revision = 3; __s.annotation_revision_count = 3;
        }
        resolve({ok:true, status:200, json:async () => ({ok:true, outcome, persisted:true})});
      }, reject};
      if(init.signal) init.signal.addEventListener("abort", () => reject(new Error("aborted")));
    });
  }
  if(String(url).startsWith("/api/data")){
    __dataGets += 1;
    if(__holdData) return new Promise(resolve => {
      __dataAnswer = () => resolve({ok:true, json:async () => __dashboard});
    });
  }
  return __base(url, init);
};
const __saveButton = () => (__els.app.innerHTML.match(
  /<button[^>]*data-next-cockpit-action="held-save"[^>]*>[\\s\\S]*?<\\/button>/) || [""])[0];
"""

TIMERS = """
setTimeout = (fn, ms) => { __timeouts.push({fn, ms}); return __timeouts.length; };
clearTimeout = id => { if(__timeouts[id - 1]) __timeouts[id - 1].fn = () => {}; };
const __fireTimers = ms => __timeouts.filter(t => t.ms === ms).forEach(t => {
  const fn = t.fn; t.fn = () => {}; fn(); });
"""


def press_save(edit: str = '__typeGoal("Ship the retry queue today");') -> str:
    return edit + '\n__press("held-save", "intent");\nawait __settle();\n'


@unittest.skipUnless(shutil.which("node"), "node not available")
class SaveIntentShowsItIsWorkingTest(_DraftPage):
    def run_save(self, after: str, setup: str = "") -> Any:
        return self.drive(TYPED + setup + HELD, after)

    def test_a_reader_who_presses_save_intent_sees_it_disabled_with_a_spinner_reading_saving_until_the_saved_words_are_drawn(
        self,
    ) -> None:
        out = self.run_save(
            press_save()
            + """
const busy = __saveButton();
__answer.resolve(); await __settle(); await __settle(); await __settle();
console.log(JSON.stringify({busy, after:__saveButton(), html:__els.app.innerHTML}));
"""
        )
        busy = out["busy"]
        self.assertIn('aria-disabled="true"', busy)
        self.assertIn('aria-busy="true"', busy)
        self.assertIn("data-next-pending", busy)
        self.assertIn('class="next-spinner"', busy)
        # The busy label is what a sighted reader sees; the idle label is a hidden ghost that
        # holds the width.
        self.assertEqual("Saving…", visible_text(busy).strip())
        self.assertIn('class="next-action-ghost" aria-hidden="true">Save intent<', busy)
        after = out["after"]
        self.assertNotIn("data-next-pending", after)
        self.assertNotIn("aria-busy", after)
        self.assertEqual("Save intent", visible_text(after).strip())
        self.assertIn(SAVED, visible_text(intent_of(out["html"])))

    def test_a_reader_who_presses_save_intent_twice_sends_one_save(self) -> None:
        out = self.run_save(
            press_save()
            + """
__press("held-save", "intent"); await __settle();
__press("held-save", "intent"); await __settle();
console.log(JSON.stringify({posts:__annotates.length}));
"""
        )
        self.assertEqual(1, out["posts"])

    def test_a_reader_who_keeps_typing_during_a_save_cannot_press_save_again_until_it_answers(
        self,
    ) -> None:
        out = self.run_save(
            press_save()
            + """
const attrs = {save:new Set(["aria-disabled"]), undo:new Set()};
const control = name => ({dataset:{nextFocus:`held:claude:focus-1:intent:${name}`},
  setAttribute(a){ attrs[name].add(a); }, removeAttribute(a){ attrs[name].delete(a); }});
const controls = {"held-save":control("save"), "held-undo":control("undo")};
const footer = {querySelector(selector){
  const m = selector.match(/data-next-cockpit-action="([^"]+)"/); return m ? controls[m[1]] : null; },
  closest(){ return null; }};
__els.app.querySelector = selector => selector === ".next-cockpit-held-footer" ? footer : null;
const field = {querySelector(){ return null; }, setAttribute(){}, removeAttribute(){}};
__fire("input", {target:{value:"Ship the retry queue today, and the docs",
  dataset:{nextCockpitHeldKey:"held:claude:focus-1:goal"},
  closest(selector){ return selector === "[data-next-cockpit-held-key]" ? this
    : selector === "[data-next-cockpit-held-field]" ? field : null; }}});
const typed = [...attrs.save];
__press("held-save", "intent"); await __settle();
console.log(JSON.stringify({typed, posts:__annotates.length}));
"""
        )
        self.assertIn("aria-disabled", out["typed"])
        self.assertEqual(1, out["posts"])

    def test_a_reader_whose_save_is_never_answered_gets_the_button_back_and_is_told_cargento_did_not_answer_not_that_it_refused(
        self,
    ) -> None:
        out = self.run_save(
            TIMERS
            + press_save()
            + """
const busy = __saveButton();
__fireTimers(15000);
await __settle(); await __settle(); await __settle(); await __settle();
console.log(JSON.stringify({busy, after:__saveButton(), html:__els.app.innerHTML}));
"""
        )
        self.assertIn("data-next-pending", out["busy"])
        self.assertNotIn("data-next-pending", out["after"])
        self.assertNotIn('aria-disabled="true"', out["after"])
        intent = visible_text(intent_of(out["html"]))
        self.assertIn(UNCONFIRMED, intent)
        self.assertNotIn("Not saved", intent)
        self.assertIn("Ship the retry queue today", intent_of(out["html"]))

    def test_a_save_the_server_kept_while_its_answer_was_lost_is_said_as_saved(self) -> None:
        out = self.run_save(
            TIMERS
            + press_save()
            + """
__s.annotation_goal = "Ship the retry queue today";
__s.annotation_revision = 3; __s.annotation_revision_count = 3;
__fireTimers(15000);
await __settle(); await __settle(); await __settle(); await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML}));
"""
        )
        intent = visible_text(intent_of(out["html"]))
        self.assertIn(SAVED, intent)
        self.assertNotIn(UNCONFIRMED, intent)

    def test_a_backstop_clears_a_save_whose_handler_never_returns(self) -> None:
        out = self.run_save(
            TIMERS
            + press_save()
            + """
// The answer arrives and the refresh after it never does.
__holdData = true;
__answer.resolve(); await __settle(); await __settle();
const held = __saveButton();
__fireTimers(20000);
await __settle();
console.log(JSON.stringify({held, after:__saveButton()}));
"""
        )
        self.assertIn("data-next-pending", out["held"])
        self.assertNotIn("data-next-pending", out["after"])

    def test_a_refusal_the_server_answers_still_says_not_saved(self) -> None:
        out = self.run_save(
            press_save()
            + """
__answer.resolve("refused"); await __settle(); await __settle(); await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML}));
"""
        )
        self.assertIn(REFUSED, visible_text(intent_of(out["html"])))

    def test_a_reader_who_has_just_pressed_save_intent_is_not_told_to_save_their_intent(
        self,
    ) -> None:
        out = self.run_save(
            press_save()
            + """
const busy = __els.app.innerHTML;
__answer.resolve(); await __settle(); await __settle(); await __settle();
console.log(JSON.stringify({busy, after:__els.app.innerHTML}));
"""
        )
        busy = visible_text(drift_of(out["busy"]))
        self.assertIn("Saving your intent…", busy)
        self.assertNotIn(EDITED, busy)
        self.assertNotIn("Saving your intent…", visible_text(drift_of(out["after"])))

    def test_a_screen_reader_user_hears_the_saves_outcome_when_it_is_drawn_not_before(
        self,
    ) -> None:
        out = self.drive(
            TYPED + DOM + HELD,
            press_save()
            + """
__holdData = true;
__answer.resolve(); await __settle(); await __settle();
const before = [...wrote("next-cockpit-cue-status")];
const drawnBefore = __els.app.innerHTML.includes("Saved as a new revision.");
__dataAnswer(); await __settle(); await __settle(); await __settle();
console.log(JSON.stringify({before, drawnBefore, after:[...wrote("next-cockpit-cue-status")],
  drawn:__els.app.innerHTML.includes("Saved as a new revision.")}));
""",
        )
        self.assertFalse(out["drawnBefore"])
        self.assertNotIn(SAVED, out["before"])
        self.assertTrue(out["drawn"])
        self.assertEqual(SAVED, out["after"][-1])

    def test_the_start_is_said_only_when_the_save_takes_longer_than_400_ms(self) -> None:
        out = self.drive(
            TYPED + DOM + HELD,
            TIMERS
            + press_save()
            + """
const quiet = [...wrote("next-cockpit-cue-status")];
__fireTimers(400);
console.log(JSON.stringify({quiet, said:[...wrote("next-cockpit-cue-status")]}));
""",
        )
        self.assertNotIn("Saving your intent.", out["quiet"])
        self.assertIn("Saving your intent.", out["said"])


class APendingControlIsDrawnBusyNotRefusedTest(unittest.TestCase):
    def test_a_reader_who_prefers_reduced_motion_sees_a_still_ring(self) -> None:
        sheet = css()
        blocks = re.findall(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?\})\s*\}", sheet
        )
        spinner = [
            body
            for block in blocks
            for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block + "}")
            if ".next-spinner" in selector
        ]
        self.assertTrue(spinner, "no reduced-motion rule for the spinner")
        self.assertIn("animation:none", spinner[0])
        self.assertIn("opacity:.55", spinner[0])

    def test_a_busy_control_overrides_the_inert_hatch_and_holds_its_width(self) -> None:
        rules = {sel.strip(): body for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css())}
        pending = rules.get(".next-action[data-next-pending]", "")
        self.assertIn("display:inline-grid", pending)
        self.assertIn("cursor:progress", pending)
        self.assertIn("border:1px solid", pending)
        self.assertIn("grid-area:1/1", rules.get(".next-action[data-next-pending]>span", ""))
        self.assertIn("visibility:hidden", rules.get(".next-action-ghost", ""))
        sheet = css()
        hatch = sheet.index('.next-action:disabled,.next-action[aria-disabled="true"]{')
        self.assertGreater(sheet.index(".next-action[data-next-pending]{"), hatch)


if __name__ == "__main__":
    unittest.main()


SETTLED = TYPED + "__s.annotation_settled_through = 104; __s.annotation_settled_at = 104;\n"
CONSENT = '__dashboard.reading = {consent:false, reason:"consent-required", used:0, limit:12};\n'
RUNNING_JOB = """
__dashboard.reading_jobs = {"claude:focus-1": {id:"j1", phase:"waiting", started_at:100,
  phase_at:101, provider:"codex", steps:[{phase:"preparing", text:"Preparing what is sent"},
  {phase:"waiting", text:"Waiting for Codex"}, {phase:"checking", text:"Checking the reply"}]}};
"""
UNCONFIRMED_READING = "Could not confirm the reading."

# Any POST to a held URL waits until the test answers it, honouring its abort signal, as `fetch`
# does. `__held[url]` lists what was sent and how to answer each.
HOLD = """
const __held = {};
const __holding = new Set();
const __timeouts = [];
const __hold = url => __holding.add(url);
const __upstreamHold = __fetchImpl;
__fetchImpl = (url, init) => {
  if(init && init.method === "POST" && __holding.has(String(url))){
    return new Promise((resolve, reject) => {
      (__held[String(url)] = __held[String(url)] || []).push({body:JSON.parse(init.body),
        answer(status, body){ resolve({ok:status < 400, status, json:async () => body}); }});
      if(init.signal) init.signal.addEventListener("abort", () => reject(new Error("aborted")));
    });
  }
  return __upstreamHold(url, init);
};
const __buttonOf = action => (__els.app.innerHTML.match(new RegExp(
  `<button[^>]*data-next-cockpit-action="${action}"[^>]*>[\\\\s\\\\S]*?<\\\\/button>`)) || [""])[0];
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheAnalyzeFamilyShowsItIsWorkingTest(_DraftPage):
    def test_a_reader_who_presses_analyze_drift_sees_starting_until_the_analyzing_box_appears(
        self,
    ) -> None:
        out = self.drive(
            SETTLED + HOLD,
            """
__hold("/api/reading");
__press("reading-ask"); await __settle();
const busy = __buttonOf("reading-ask");
const JOB = {id:"j1", phase:"preparing", started_at:106, phase_at:106, provider:"codex",
  steps:[{phase:"preparing", text:"Preparing what is sent"}]};
__dashboard.reading_jobs = {"claude:focus-1": JOB};
__held["/api/reading"][0].answer(202, {ok:true, job:JOB});
await __settle(); await __settle(); await __settle();
console.log(JSON.stringify({busy, html:__els.app.innerHTML}));
""",
        )
        busy = out["busy"]
        self.assertIn("data-next-pending", busy)
        self.assertIn('aria-busy="true"', busy)
        self.assertEqual("Starting…", visible_text(busy).strip())
        self.assertIn("next-action--primary", busy)
        drift = drift_of(out["html"])
        self.assertIn("data-next-analyzing", drift)
        self.assertNotIn("data-next-pending", drift)

    def test_a_started_analysis_does_not_then_say_it_is_starting(self) -> None:
        # The box is the answer: once it is drawn the press stops being busy, so the start
        # sentence never follows the box onto the region.
        out = self.drive(
            SETTLED + DOM + HOLD,
            TIMERS
            + """
__hold("/api/reading");
__press("reading-ask"); await __settle();
const JOB = {id:"j1", phase:"preparing", started_at:106, phase_at:106, provider:"codex",
  steps:[{phase:"preparing", text:"Preparing what is sent"}]};
__dashboard.reading_jobs = {"claude:focus-1": JOB};
const upstream = __fetchImpl;
__fetchImpl = (url, init) => String(url).startsWith("/api/data") ? new Promise(() => {})
  : upstream(url, init);
__held["/api/reading"][0].answer(202, {ok:true, job:JOB});
await __settle(); await __settle();
__fireTimers(400);
console.log(JSON.stringify({said:[...wrote("next-cockpit-cue-status")],
  boxed:__els.app.innerHTML.includes("data-next-analyzing")}));
""",
        )
        self.assertTrue(out["boxed"])
        self.assertNotIn("Starting the analysis.", out["said"])

    def test_a_busy_control_is_not_drawn_as_refused(self) -> None:
        out = self.drive(
            SETTLED + HOLD,
            """
__hold("/api/reading");
__press("reading-ask"); await __settle();
console.log(JSON.stringify({busy:__buttonOf("reading-ask"), html:__els.app.innerHTML}));
""",
        )
        busy = out["busy"]
        self.assertIn("data-next-pending", busy)
        self.assertNotIn("next-cockpit-reading-refused", busy)
        self.assertNotIn("Why it can", visible_text(drift_of(out["html"])))

    def test_a_reader_who_presses_allow_and_analyze_keeps_the_question_in_view_with_allow_reading_starting(
        self,
    ) -> None:
        out = self.drive(
            SETTLED + CONSENT + HOLD,
            """
__hold("/api/reading");
__press("reading-ask"); await __settle();
__press("reading-allow"); await __settle();
const busy = __els.app.innerHTML;
console.log(JSON.stringify({busy, allow:__buttonOf("reading-allow"),
  notNow:__buttonOf("reading-not-now"), posts:(__held["/api/reading"] || []).length}));
""",
        )
        self.assertEqual(1, out["posts"])
        self.assertIn("for analysis?", visible_text(drift_of(out["busy"])))
        self.assertIn("data-next-pending", out["allow"])
        self.assertEqual("Starting…", visible_text(out["allow"]).strip())
        self.assertIn('aria-disabled="true"', out["notNow"])

    def test_a_reader_whose_analysis_request_is_never_answered_can_press_analyze_drift_again_after_the_bound(
        self,
    ) -> None:
        out = self.drive(
            SETTLED + HOLD,
            TIMERS
            + """
__hold("/api/reading");
__press("reading-ask"); await __settle();
__press("reading-ask"); await __settle();
const once = __held["/api/reading"].length;
__fireTimers(15000);
await __settle(); await __settle(); await __settle();
const after = __buttonOf("reading-ask");
const html = __els.app.innerHTML;
__press("reading-ask"); await __settle();
console.log(JSON.stringify({once, after, html, twice:__held["/api/reading"].length}));
""",
        )
        self.assertEqual(1, out["once"])
        self.assertNotIn("data-next-pending", out["after"])
        self.assertNotIn('aria-disabled="true"', out["after"])
        self.assertIn(UNCONFIRMED_READING, visible_text(drift_of(out["html"])))
        self.assertEqual(2, out["twice"])

    def test_a_reader_cancelling_an_analysis_sees_cancelling(self) -> None:
        out = self.drive(
            SETTLED + RUNNING_JOB + HOLD,
            """
__hold("/api/reading/cancel");
__press("reading-cancel"); await __settle();
const busy = __buttonOf("reading-cancel");
__press("reading-cancel"); await __settle();
console.log(JSON.stringify({busy, posts:__held["/api/reading/cancel"].length}));
""",
        )
        self.assertIn("data-next-pending", out["busy"])
        self.assertEqual("Cancelling…", visible_text(out["busy"]).strip())
        self.assertEqual(1, out["posts"])

    def test_a_reader_who_presses_keep_sees_keeping(self) -> None:
        out = self.drive(
            TYPED
            + "__semantic.facts = __semantic.facts.filter(f => f.fact_id !== 'fo-b');\n"
            + HOLD,
            """
__hold("/api/reading");
__press("direction-keep"); await __settle(); await __settle();
const busy = __buttonOf("direction-keep");
__press("direction-keep"); await __settle();
console.log(JSON.stringify({busy, posts:(__held["/api/reading"] || []).length}));
""",
        )
        self.assertIn("data-next-pending", out["busy"])
        self.assertEqual("Keeping…", visible_text(out["busy"]).strip())
        self.assertEqual(1, out["posts"])
