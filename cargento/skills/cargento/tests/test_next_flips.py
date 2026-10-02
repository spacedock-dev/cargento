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
from .test_next_intent_draft import TYPED, _DraftPage
from .visible_text import visible_text

DOM = cockpit_tests.CockpitCuesReachTheReaderTest.ANNOUNCER_DOM
OPEN_RUNNING = "Analyze is open again: the session is running."
OPEN_LAST_TURN = "Analyze is open: the session's last turn finished."
CLOSED = "Analyze closed: the session went quiet."
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


def ask_tag(html: str) -> str:
    found = re.search(r"<button[^>]*reading-ask[^>]*>", html)
    assert found is not None, "no Analyze control drawn"
    return found.group(0)


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
        self.assertNotIn('aria-disabled="true"', ask_tag(drift))
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
        self.assertNotIn('aria-disabled="true"', ask_tag(opened))
        self.assertIn(OPEN_LAST_TURN, visible_text(opened))
        self.assertNotIn("next-wait-dot", opened)
        self.assertEqual([OPEN_LAST_TURN], out["said"])

    def test_a_close_held_past_its_moment_with_no_new_payload_waits_quietly_for_one(
        self,
    ) -> None:
        # Measured by the regressions verifier: a hold whose moment had passed re-armed itself at
        # that past moment on every render, so a page whose stream had stopped redrew #app several
        # hundred times a second. Every timer the page arms is fired, round after round.
        out = self.run_flip(
            """
await __poll(OPEN, 1000);
await __poll(IDLE, 1001);
__setNow(1012);
const before = nextReadingFlipRender;
for(let round = 0; round < 40; round += 1){ __fireAll(); await __settle(); }
const renders = nextReadingFlipRender - before;
const armed = __timeouts.length;
const held = __els.app.innerHTML;
const closed = await __poll(IDLE, 1013);
console.log(JSON.stringify({renders, armed, held:__ask(held), closed:__ask(closed)}));
""",
            setup=TIMERS,
        )
        self.assertLessEqual(out["renders"], 2)
        self.assertNotIn('aria-disabled="true"', out["held"])
        # The next payload is the one the hold was waiting for.
        self.assertIn('aria-disabled="true"', out["closed"])

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

    def test_a_screen_reader_hears_the_newest_state_once_the_minute_is_up(self) -> None:
        """Verifier F4 (ui3): a close was announced, the session ended 19 s later and Analyze
        opened, and the once-a-minute limit dropped that open, so the last thing a screen reader
        heard was false. The limit now holds the newest flip and says it when the minute is up,
        unless the region's last word is already the current state."""
        out = self.run_flip(
            """
await __poll(OPEN, 1000);
await __poll(IDLE, 1001); await __poll(IDLE, 1006);
await __poll(IDLE, 1012);
const closedSaid = __flipWrites();
const reopened = await __poll(OPEN, 1031);
const within = __flipWrites();
// Only the timer armed for the minute's end (1012 + 60 - 1031 = 41 s): no payload, no other.
__setNow(1072);
__timeouts.filter(t => t.ms === 41000).forEach(t => { const fn = t.fn; t.fn = () => {}; fn(); });
await __settle(); await __settle();
const due = __flipWrites();
await __poll(OPEN, 1080);
console.log(JSON.stringify({closedSaid, within, due, after:__flipWrites(),
  shown:reopened.includes("next-cockpit-reading-change")}));
""",
            setup=TIMERS,
        )
        self.assertEqual([CLOSED], out["closedSaid"])
        # In view at once, and held from the region inside the minute.
        self.assertTrue(out["shown"])
        self.assertEqual([CLOSED], out["within"])
        # Said when the minute is up, once, with no payload needed to say it.
        self.assertEqual([CLOSED, OPEN_RUNNING], out["due"])
        self.assertEqual([CLOSED, OPEN_RUNNING], out["after"])

    def test_a_held_flip_that_reverted_is_not_said_when_the_minute_is_up(self) -> None:
        out = self.run_flip(
            """
await __poll(OPEN, 1001);
await __poll(IDLE, 1002); await __poll(IDLE, 1007); await __poll(IDLE, 1013);
await __poll(OPEN, 1020);
__setNow(1062); __fireAll(); await __settle(); await __settle();
console.log(JSON.stringify({said:__flipWrites()}));
""",
            setup=IDLE_FIRST + TIMERS,
        )
        # The region last said "open", and open is what the card shows: nothing is owed.
        self.assertEqual([OPEN_RUNNING], out["said"])

    def test_a_close_on_a_turn_that_did_not_stop_does_not_say_it_stopped(self) -> None:
        """Verifier F5 (ui3): "the session stopped running" was said of a turn left on an open
        tool call or an interruption, beside a line saying the turn isn't recorded as finished."""
        out = self.run_flip(
            """
await __poll(OPEN, 1000);
await __poll(IDLE, 1001); await __poll(IDLE, 1006);
const closed = await __poll(IDLE, 1012);
console.log(JSON.stringify({closed}));
"""
        )
        text = visible_text(drift_of(out["closed"]))
        self.assertIn(CLOSED, text)
        self.assertIn(IDLE_LINE, text)
        self.assertNotIn("stopped", text)

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

    def test_a_change_another_refusal_still_hides_is_not_said(self) -> None:
        # Measured on a scratch board run with --no-observer-model: the settle ended and the
        # line said "Analyze is open" beside a button the model switch still held inert.
        out = self.run_flip(
            """
const opened = await __poll(OPEN, 1005);
await __poll(IDLE, 1006);
const closed = await __poll(IDLE, 1017);
console.log(JSON.stringify({opened, closed, said:__flipWrites()}));
""",
            setup=IDLE_FIRST
            + '__dashboard.reading = {consent:false, reason:"run-disabled", used:0, limit:12,'
            " providers:{codex:false, claude:false}, tool_output:{}};\n",
        )
        self.assertIn('aria-disabled="true"', ask_tag(drift_of(out["opened"])))
        self.assertNotIn(OPEN_RUNNING, out["opened"])
        self.assertNotIn(CLOSED, out["closed"])
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


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheDirectionQuestionDoesNotFlipSilentlyTest(_DraftPage):
    """Verifier F1: a later direction replaces Analyze with Keep and Add, and the board's press
    refusal under them came and went with no hold, no Why and nothing said. A later direction is
    the normal state of any session the reader keeps prompting."""

    SETUP = (
        TYPED
        + DOM
        + f"__dashboard.reading_check = {json.dumps(annotation_store.ABSTENTION_CHECK)};\n"
        + f"__dashboard.reading_routes = {json.dumps(routes())};\n"
        + "__dashboard.reading = {consent:true, providers:{codex:true, claude:true}, used:0,"
        " limit:12};\n"
        + "__s.harness = 'claude'; __s.state = 'working';\n"
        + "__s.reading_eligibility = {ok:true, reason:null, until:null, sentence:null};\n"
        + FRESH.replace("const __s = __dashboard.sessions[0];\n", "")
    )

    def walk(self, script: str, setup: str = "") -> Any:
        return self.drive(
            self.SETUP + setup,
            """
const __question = () => { const h = __els.app.innerHTML;
  const i = h.indexOf("data-next-cockpit-direction-question");
  return i < 0 ? "" : h.slice(i, h.indexOf("</div></div>", i) + 12); };
"""
            + script,
        )

    def test_a_reader_with_a_later_direction_open_is_told_when_analyze_closes_and_why(
        self,
    ) -> None:
        out = self.walk(
            """
await __poll(OPEN, 1100);
const working = __question();
await __poll(IDLE, 1101);
const quiet = __question();
await __poll(IDLE, 1112);
const closed = __question();
const reopened = (await __poll(OPEN, 1130), __question());
console.log(JSON.stringify({working, quiet, closed, reopened, said:__flipWrites()}));
"""
        )
        self.assertIn("later direction", visible_text(out["working"]))
        # The first quiet payload is a pause between turns until it has held.
        quiet = visible_text(out["quiet"])
        self.assertNotIn(IDLE_LINE, quiet)
        self.assertNotIn(CLOSED, quiet)
        closed = visible_text(out["closed"])
        self.assertIn(CLOSED, closed)
        self.assertIn(IDLE_LINE, closed)
        self.assertLess(closed.index(CLOSED), closed.index(IDLE_LINE))
        self.assertIn("Why it can't read", closed)
        # The board's own sentence, one click away under that summary.
        self.assertIn("Idle, with no end.", out["closed"])
        reopened = visible_text(out["reopened"])
        self.assertIn(OPEN_RUNNING, reopened)
        self.assertNotIn(IDLE_LINE, reopened)
        # Once to the region; the reopening 18 s later is in view only (once a minute).
        self.assertEqual([CLOSED], out["said"])

    def test_a_keep_pressed_while_a_close_is_held_says_why_nothing_was_analyzed(self) -> None:
        # The press learns the board's state, as Analyze's own press does: "No analysis was
        # started" with the reason beside it, never a close announced ten seconds later.
        out = self.walk(
            """
__reply["/api/annotate"] = () => ({status:200, body:{ok:true, outcome:"stored"}});
await __poll(OPEN, 1100);
await __poll(IDLE, 1101);
const held = __question();
__press("direction-keep"); await __settle(); await __settle();
const kept = __els.app.innerHTML;
const later = await __poll(IDLE, 1112);
console.log(JSON.stringify({held, kept, later, said:__flipWrites(),
  posts:__posts.map(p => p.url)}));
"""
        )
        self.assertNotIn(IDLE_LINE, visible_text(out["held"]))
        self.assertEqual(["/api/annotate"], out["posts"])
        kept = visible_text(drift_of(out["kept"]))
        self.assertIn("No analysis was started.", kept)
        self.assertIn(IDLE_LINE, kept)
        self.assertNotIn(CLOSED, visible_text(drift_of(out["later"])))
        self.assertEqual([], out["said"])

    def test_a_reader_with_a_later_direction_open_sees_the_settle_wait_and_its_end(self) -> None:
        out = self.walk(
            """
const settling = __question();
__setNow(1008);
__fireAll(); await __settle();
console.log(JSON.stringify({settling, opened:__question(), said:__flipWrites()}));
""",
            setup=TIMERS
            + """
__setNow(1003);
__s.state = "idle"; __s.finished_at = 1000;
__s.reading_eligibility = {ok:false, reason:"stop-settling", until:1008, sentence:"Settling."};
""",
        )
        self.assertIn('<span class="next-wait-dot" aria-hidden="true"></span>', out["settling"])
        self.assertIn("Ready in a few seconds.", visible_text(out["settling"]))
        opened = visible_text(out["opened"])
        self.assertIn(OPEN_LAST_TURN, opened)
        self.assertNotIn("Ready in a few seconds.", opened)
        self.assertEqual([OPEN_LAST_TURN], out["said"])


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
