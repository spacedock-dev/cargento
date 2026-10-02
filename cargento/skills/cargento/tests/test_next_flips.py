"""Analyze says when it opens or closes by itself (owner, 2026-10-02).

The owner watched Analyze drift go from inert to live after 20 to 30 seconds with nothing said,
then back to inert two minutes later, "and it just looks like the Drift analysis feature is not
working". The rulings: a change of whether Analyze can be pressed that no press of the reader's
caused is said in one short line under the button and once to the polite region; closing waits
until the inert state has held for two payloads and ten seconds, so a session pausing between
turns never flickers; a settle draws a waiting dot and opens on time with no new data; a consent
question Analyze closes under is withdrawn with a sentence and never raised again on its own; and
the region hears a flapping session at most once a minute.

Every assertion is on the assembled bundle's markup or what its live region carries.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from typing import Any

from cargento_runtime import annotations as annotation_store

from . import test_next_cockpit as cockpit_tests
from .next_harness import NextPageJsHarness, storage_prelude
from .test_next_drift_panel import ANNOTATED, FIXTURE, drift_of, routes
from .visible_text import visible_text

DOM = cockpit_tests.CockpitCuesReachTheReaderTest.ANNOUNCER_DOM
OPEN_RUNNING = "Analyze is open again: the session is running."
OPEN_LAST_TURN = "Analyze is open: the session's last turn finished."
CLOSED = "Analyze closed: the session stopped running."
CLOSED_UNANSWERED = "Analyze closed before you answered, so nothing was sent."
IDLE_LINE = "This session's last turn isn't recorded as finished."

# Every poll hands the page a new payload object, as the server does; the fixture's own stub
# hands back the same one, which no payload-counting rule could tell apart.
FRESH = """
const __fixtureFetch = __fetchImpl;
__fetchImpl = async (url, init) => String(url).startsWith("/api/data")
  ? {ok:true, json:async () => JSON.parse(JSON.stringify(__dashboard))}
  : __fixtureFetch(url, init);
const __s = __dashboard.sessions[0];
const IDLE = {ok:false, reason:"idle-unknown", until:null, sentence:"Idle, with no end."};
const OPEN = {ok:true, reason:null, until:null, sentence:null};
const __poll = async (eligibility, at) => {
  if(at != null) __setNow(at);
  __s.reading_eligibility = eligibility;
  await refreshNext(); await __settle(); await __settle();
  return __els.app.innerHTML;
};
const __ask = html => (html.match(
  /<button[^>]*data-next-cockpit-action="reading-(?:ask|allow)"[^>]*>[\\s\\S]*?<\\/button>/) || [""])[0];
const __flipWrites = () => wrote("next-cockpit-cue-status").filter(text =>
  text.startsWith("Analyze is open") || text.startsWith("Analyze closed"));
"""

IDLE_FIRST = "__setNow(1000); __s.reading_eligibility = IDLE;\n"

TIMERS = """
const __timeouts = [];
setTimeout = (fn, ms) => { __timeouts.push({fn, ms}); return __timeouts.length; };
clearTimeout = id => { if(__timeouts[id - 1]) __timeouts[id - 1].fn = () => {}; };
const __fireAll = () => { const due = __timeouts.splice(0); due.forEach(t => t.fn()); };
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class AnalyzeSaysWhenItOpensOrClosesTest(NextPageJsHarness):
    def run_flip(self, script: str, setup: str = "") -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + ANNOTATED
            + f"__dashboard.reading_check = {json.dumps(annotation_store.ABSTENTION_CHECK)};\n"
            + f"__dashboard.reading_routes = {json.dumps(routes())};\n"
            + '__dashboard.sessions[0].harness = "claude";\n'
            + DOM
            + FRESH
            + setup
            + "await refreshNext();\nawait __settle();\n"
            + "navigateNext({view:'session', project:'cargento', harness:'claude',"
            + " session:'focus-1'});\nawait __settle();\n"
            + script,
            storage_prelude({}) + FIXTURE,
        )

    def test_a_reader_watching_the_drift_card_sees_and_hears_one_line_when_analyze_opens_by_itself(
        self,
    ) -> None:
        out = self.run_flip(
            """
const inert = __els.app.innerHTML;
const opened = await __poll(OPEN, 1005);
const again = await __poll(OPEN, 1010);
console.log(JSON.stringify({inert:__ask(inert), opened, again, said:__flipWrites()}));
""",
            setup=IDLE_FIRST,
        )
        self.assertIn('aria-disabled="true"', out["inert"])
        drift = drift_of(out["opened"])
        self.assertNotIn(
            'aria-disabled="true"', re.search(r"<button[^>]*reading-ask[^>]*>", drift)[0]
        )
        self.assertIn(OPEN_RUNNING, visible_text(drift))
        line = re.search(r'<p class="[^"]*next-cockpit-reading-change[^"]*"[^>]*>', drift)
        assert line is not None
        self.assertNotIn("role=", line.group(0))
        self.assertEqual([OPEN_RUNNING], out["said"])
        self.assertIn(OPEN_RUNNING, visible_text(drift_of(out["again"])))

    def test_a_reader_whose_session_pauses_between_turns_sees_analyze_stay_open(self) -> None:
        out = self.run_flip(
            """
const first = await __poll(OPEN, 1000);
const settling = {ok:false, reason:"stop-settling", until:1008, sentence:"Settling."};
const paused = await __poll(settling, 1001);
const later = await __poll(settling, 1006);
const running = await __poll(OPEN, 1009);
console.log(JSON.stringify({buttons:[first, paused, later, running].map(__ask),
  html:[paused, later, running].map(h => h), said:__flipWrites()}));
"""
        )
        for button in out["buttons"]:
            self.assertNotIn('aria-disabled="true"', button)
        for html in out["html"]:
            self.assertNotIn("next-cockpit-reading-change", html)
        self.assertEqual([], out["said"])

    def test_a_reader_whose_session_goes_quiet_for_good_is_told_analyze_closed_once_after_it_has_held(
        self,
    ) -> None:
        out = self.run_flip(
            """
await __poll(OPEN, 1000);
const quiet = await __poll(IDLE, 1001);
__setNow(1012); renderNext();
const unpolled = __els.app.innerHTML;
const held = await __poll(IDLE, 1006);
const closed = await __poll(IDLE, 1012);
const after = await __poll(IDLE, 1017);
console.log(JSON.stringify({quiet:__ask(quiet), held:__ask(held), closed, button:__ask(closed),
  unpolled:__ask(unpolled), after, said:__flipWrites()}));
"""
        )
        self.assertNotIn('aria-disabled="true"', out["quiet"])
        self.assertNotIn('aria-disabled="true"', out["held"])
        # Ten seconds with no new payload is not two payloads: nothing was observed to hold.
        self.assertNotIn('aria-disabled="true"', out["unpolled"])
        self.assertIn('aria-disabled="true"', out["button"])
        text = visible_text(drift_of(out["closed"]))
        self.assertIn(CLOSED, text)
        # The page's own line stays beneath, saying why and what opens it.
        self.assertIn(IDLE_LINE, text)
        self.assertLess(text.index(CLOSED), text.index(IDLE_LINE))
        self.assertEqual([CLOSED], out["said"])

    def test_a_reader_in_the_middle_of_the_consent_question_is_told_it_closed_and_is_never_asked_again_without_pressing(
        self,
    ) -> None:
        out = self.run_flip(
            """
await __poll(OPEN, 1000);
__press("reading-ask"); await __settle();
const asking = __els.app.innerHTML;
await __poll(IDLE, 1001);
const closed = await __poll(IDLE, 1012);
const reopened = await __poll(OPEN, 1100);
console.log(JSON.stringify({asking, closed, reopened}));
""",
            setup=(
                '__dashboard.reading = {consent:false, reason:"consent-required", used:0,'
                " limit:12};\n"
                "const __press = action => __fire('click', {preventDefault(){},"
                " target:{dataset:{nextCockpitAction:action}, closest(){ return this; }}});\n"
            ),
        )
        self.assertIn("for analysis?", visible_text(drift_of(out["asking"])))
        closed = visible_text(drift_of(out["closed"]))
        self.assertIn(CLOSED_UNANSWERED, closed)
        self.assertNotIn("for analysis?", closed)
        reopened = drift_of(out["reopened"])
        self.assertNotIn("for analysis?", visible_text(reopened))
        self.assertIn('data-next-cockpit-action="reading-ask"', reopened)

    def test_a_reader_waiting_through_a_settle_sees_analyze_open_at_until_with_no_new_data(
        self,
    ) -> None:
        out = self.run_flip(
            """
const settling = __els.app.innerHTML;
const due = __timeouts.map(t => t.ms);
__setNow(1008);
__fireAll(); await __settle();
const opened = __els.app.innerHTML;
console.log(JSON.stringify({settling, due, opened, said:__flipWrites()}));
""",
            setup=TIMERS
            + """
__setNow(1003);
__s.state = "idle"; __s.finished_at = 1000;
__s.reading_eligibility = {ok:false, reason:"stop-settling", until:1008, sentence:"Settling."};
""",
        )
        drift = drift_of(out["settling"])
        self.assertIn('<span class="next-wait-dot" aria-hidden="true"></span>', drift)
        self.assertIn("Ready in a few seconds.", visible_text(drift))
        self.assertIn(5000, out["due"])
        opened = drift_of(out["opened"])
        self.assertNotIn(
            'aria-disabled="true"', re.search(r"<button[^>]*reading-ask[^>]*>", opened)[0]
        )
        self.assertIn(OPEN_LAST_TURN, visible_text(opened))
        self.assertNotIn("next-wait-dot", opened)
        self.assertEqual([OPEN_LAST_TURN], out["said"])

    def test_a_flip_on_a_session_that_flaps_is_announced_at_most_once_a_minute(self) -> None:
        out = self.run_flip(
            """
const opened = await __poll(OPEN, 1001);
await __poll(IDLE, 1002);
await __poll(IDLE, 1007);
const closed = await __poll(IDLE, 1013);
const reopened = await __poll(OPEN, 1020);
const later = await __poll(IDLE, 1080);
await __poll(IDLE, 1085);
await __poll(IDLE, 1091);
console.log(JSON.stringify({opened, closed, reopened, said:__flipWrites()}));
""",
            setup=IDLE_FIRST,
        )
        self.assertIn(OPEN_RUNNING, visible_text(drift_of(out["opened"])))
        # In view every time it changes, so the card never flips silently.
        self.assertIn(CLOSED, visible_text(drift_of(out["closed"])))
        self.assertIn(OPEN_RUNNING, visible_text(drift_of(out["reopened"])))
        # The region heard the first flip, then nothing until a minute had passed.
        self.assertEqual([OPEN_RUNNING, CLOSED], out["said"])

    def test_a_press_being_answered_holds_the_card_still(self) -> None:
        out = self.run_flip(
            """
await __poll(OPEN, 1000);
const __base = __fetchImpl;
__fetchImpl = (url, init) => init && init.method === "POST" && String(url) === "/api/reading"
  ? new Promise(() => {}) : __base(url, init);
__press("reading-ask"); await __settle();
__press("reading-allow"); await __settle();
await __poll(IDLE, 1001);
const held = await __poll(IDLE, 1012);
console.log(JSON.stringify({held, said:__flipWrites()}));
""",
            setup=(
                "const __press = action => __fire('click', {preventDefault(){},"
                " target:{dataset:{nextCockpitAction:action}, closest(){ return this; }}});\n"
            ),
        )
        self.assertIn("data-next-pending", out["held"])
        self.assertNotIn(CLOSED, out["held"])
        self.assertEqual([], out["said"])

    def test_a_reader_returning_to_the_card_is_not_told_of_a_change_they_were_not_shown(
        self,
    ) -> None:
        out = self.run_flip(
            """
navigateNext({view:"sessions"}); await __settle();
await __poll(OPEN, 1005);
navigateNext({view:'session', project:'cargento', harness:'claude', session:'focus-1'});
await __settle();
console.log(JSON.stringify({back:__els.app.innerHTML, said:__flipWrites()}));
""",
            setup=IDLE_FIRST,
        )
        self.assertNotIn(OPEN_RUNNING, out["back"])
        self.assertEqual([], out["said"])

    def test_the_line_goes_with_the_next_click_inside_the_card(self) -> None:
        out = self.run_flip(
            """
const opened = await __poll(OPEN, 1001);
__fire("click", {target:{closest(selector){ return selector === "#next-session-drift" ? {} : null; }}});
renderNext();
console.log(JSON.stringify({opened, after:__els.app.innerHTML}));
""",
            setup=IDLE_FIRST,
        )
        self.assertIn(OPEN_RUNNING, out["opened"])
        self.assertNotIn(OPEN_RUNNING, out["after"])


if __name__ == "__main__":
    unittest.main()


class TheWaitingDotIsNotTheSpinnerTest(unittest.TestCase):
    def test_a_settle_pulses_and_holds_still_under_reduced_motion(self) -> None:
        from .test_next_intent_editor import css  # noqa: PLC0415 - the sheet reader lives there

        sheet = css()
        dot = re.search(r"\.next-wait-dot\{([^}]*)\}", sheet)
        assert dot is not None
        self.assertIn("next-live-pulse", dot.group(1))
        reduced = re.findall(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?\})\s*\}", sheet
        )
        self.assertTrue(
            any(re.search(r"\.next-wait-dot\{animation:none\}", block) for block in reduced)
        )
