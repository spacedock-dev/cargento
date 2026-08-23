"""The asks band: what the page does when a session asks the reader a question.

Executed against the shipped script, like every other page test here. The two
things these have to prove are the two things a string assertion would not: the
question and its options are agent-written text and reach the document as text,
and a card whose answer did not land stays on screen, because the session is
holding its tool call open and a hidden card would leave it waiting on nothing.
"""

from __future__ import annotations

import re
import shutil
import unittest
from typing import Any

from . import test_page_calm
from .page_harness import STYLES, PageJsHarness

# The calm fixture is reused through its module, never bound here: any
# module-level name holding a TestCase subclass is collected by the loader, so
# `from .test_page_calm import CalmModeTest` (and equally an alias for it) ran
# that module's 61 tests a second time and spawned node 61 extra times on every
# full-suite run.

# What the card says when the answer POST did not come back confirmed. Pinned
# because the wording is the finding: the note used to read "the question is
# still open", which the page had not observed and which was measurably wrong
# whenever the ask had already been answered or swept.
NOTE = "no confirmation came back — it may already have been answered"


class AskBandTest(PageJsHarness):
    # The calm fixture plus the payload fields the feature adds. `ask` is the
    # server's capability flag and `asks` the outstanding questions; the page
    # derives neither, and it never puts one in `sessions`.
    FIXTURE = (
        test_page_calm.CalmModeTest.FIXTURE
        + """
const ask = o => Object.assign({id: "askA1", harness: "claude", session_id: "aaa1",
  project: "repo/proj", question: "Ship the migration now?",
  options: ["Ship it", "Wait for review"], age_sec: 42}, o || {});
const withAsks = (sessions, asks) => Object.assign(payload(sessions),
  {ask: true, asks: asks === undefined ? [ask()] : asks});
// Every answer control the render emitted, as the routed click sees it: the
// data-arg is read back off the DOM, so a wrong id or index fails here rather
// than in a hand-built event.
const askControls = () => __controls()
  .filter(c => c.getAttribute("data-calm") === "answer");
const clickAnswer = i => {
  const el = askControls()[i];
  if(!el) throw new Error("no answer control at " + i);
  __fire("click", {target: {closest: sel => sel === "[data-calm]" ? el : null}});
};
const wire = opts => {
  const o = opts || {};
  __fetchImpl = url => {
    const u = String(url);
    if(u === "/api/answer"){
      if(o.postFails) return Promise.reject(new Error("connection refused"));
      if(o.status) return Promise.resolve({ok: false, status: o.status,
        json: () => Promise.resolve({})});
      return Promise.resolve({ok: true, json: () => Promise.resolve(
        {ok: true, answered: o.answered === undefined ? true : o.answered})});
    }
    return Promise.resolve({ok: true, json: () => Promise.resolve(
      o.after === undefined ? withAsks([busy], []) : o.after)});
  };
};
const posted = () => __fetchCalls.filter(c => String(c[0]) === "/api/answer")
  .map(c => JSON.parse(c[1].body));
const asked = url => __fetchCalls.filter(c => String(c[0]) === url).length;
// Both spellings on purpose: `askband-note` was the band-level note this
// module used to accept, so a test written against the per-card note still
// fails loudly if the band-level one comes back.
const noteRe = /class="ask(?:band)?-note">([^<]*)</;
const noteText = () => (__els.app.innerHTML.match(noteRe) || [])[1] || null;
const noteCount = () => (__els.app.innerHTML
  .match(/class="ask(?:band)?-note">/g) || []).length;
// The band scrolls inside the calm frame, so its offset has to survive the
// DOM swap the way the ledger's does.
let __askScroll = 0;
__els["askband"] = {
  get scrollTop(){ return __askScroll; }, set scrollTop(v){ __askScroll = v; }
};
"""
    )

    def run_page(self, checks: str, *, saved: str = "regular") -> Any:
        return self._run_page_js(
            self.FIXTURE + checks,
            prelude=test_page_calm.CalmModeTest.prelude(saved, clipboard="none"),
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_band_renders_the_question_its_source_and_one_button_per_option(self) -> None:
        checks = """
const out = {};
render(withAsks([blocked, busy]));
const h = __els.app.innerHTML;
out.question = h.includes("Ship the migration now?");
out.project = h.includes("repo/proj");
out.session = h.includes("aaa1");
out.age = /class="ask-age">[^<]*42s/.test(h);
out.opts = [...h.matchAll(/class="ask-opt"[^>]*>([^<]*)</g)].map(m => m[1]);
out.args = askControls().map(c => c.getAttribute("data-arg"));
out.n = (h.match(/class="askband-n">([^<]*)</) || [])[1];
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["question"], "the band did not render the question")
        self.assertTrue(out["project"], "the band did not say where the question came from")
        self.assertTrue(out["session"], "the band did not name the asking session")
        self.assertTrue(out["age"], "the band did not say how long the session has waited")
        self.assertEqual(["Ship it", "Wait for review"], out["opts"])
        # The answer is an index, never the option text: the id and the position
        # are the whole payload the click carries.
        self.assertEqual(["askA1:0", "askA1:1"], out["args"])
        self.assertEqual("1 waiting", out["n"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_click_posts_the_id_and_the_index_then_refetches(self) -> None:
        checks = """
const out = {};
render(withAsks([blocked, busy]));
wire();
const before = asked("/api/data");
clickAnswer(1);
await __settle(); await __settle(); await __settle();
out.posted = posted();
out.refetched = asked("/api/data") - before;
out.gone = !__els.app.innerHTML.includes("Ship the migration now?");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual([{"id": "askA1", "index": 1}], out["posted"])
        self.assertEqual(1, out["refetched"], "the page did not refetch after answering")
        # The server's next payload is what removes the card, exactly as it is
        # for the handled control.
        self.assertTrue(out["gone"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_question_and_its_options_reach_the_page_as_text(self) -> None:
        # Both strings are written by an agent. This is the one assertion in this
        # module whose failure is a security bug rather than a wrong reading.
        checks = """
const out = {};
render(withAsks([busy], [ask({question: '<img src=x onerror="boom()">hi',
  options: ['</button><script>boom()</script>', 'ok"onclick="boom()']})]));
const h = __els.app.innerHTML;
out.rawImg = h.includes("<img");
out.rawScript = h.includes("<script");
// The page's own markup is full of </button>, so the tell is the break-out
// sequence rather than the tag: the option's text closing its own button.
out.rawClose = h.includes("</button><script");
out.escaped = h.includes("&lt;img src=x onerror=&quot;boom()&quot;&gt;hi");
console.log(JSON.stringify(out));
"""
        # The attribute case is its own test below. It used to live here as
        # /class="ask-opt"[^>]*onclick/, which could not fail for the reason it
        # claimed: an option label lands between the `>` and the `<`, and the
        # character class cannot cross the `>` to reach it.
        out = self.run_page(checks)
        self.assertFalse(out["rawImg"], "an agent's question reached the document as markup")
        self.assertFalse(out["rawScript"], "an agent's option reached the document as markup")
        self.assertFalse(out["rawClose"], "an option closed the button element around it")
        self.assertTrue(out["escaped"], "the question was not rendered at all")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_attribution_fields_reach_the_page_as_text(self) -> None:
        # `harness`, `project` and `session_id` are taken off the request body
        # with no check that the named session exists, so any local process can
        # write them. Deleting esc() from either of the two the card prints
        # verbatim left this whole module green before this test existed.
        checks = """
const out = {};
render(withAsks([busy], [ask({project: '<b>owned</b>"p',
  session_id: "<i>sid</i>'s"})]));
const h = __els.app.innerHTML;
out.rawProject = h.includes("<b>owned");
out.rawSession = h.includes("<i>sid");
out.escProject = h.includes("&lt;b&gt;owned&lt;/b&gt;&quot;p");
out.escSession = h.includes("&lt;i&gt;sid&lt;/i&gt;&#39;s");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertFalse(out["rawProject"], "an ask's project label reached the document as markup")
        self.assertFalse(out["rawSession"], "an ask's session id reached the document as markup")
        self.assertTrue(out["escProject"], "the project label was not rendered at all")
        self.assertTrue(out["escSession"], "the session id was not rendered at all")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_asks_id_cannot_open_a_second_control_out_of_its_attribute(self) -> None:
        # The id is server-minted today, but it is the one ask field that lands
        # inside an attribute, and the page is what decides whether a control
        # exists. An unescaped id closes data-arg and declares its own
        # data-calm, which the click router would then honour.
        checks = """
const out = {};
render(withAsks([busy], [ask({id: 'x" data-calm="stop'})]));
out.args = askControls().map(c => c.getAttribute("data-arg"));
// The page has a real data-calm="stop"; only the index-suffixed spelling can
// have come out of the id, so that is what this looks for.
out.acts = __controls().map(c => c.getAttribute("data-calm"))
  .filter(a => String(a).indexOf("stop:") === 0);
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(
            ["x&quot; data-calm=&quot;stop:0", "x&quot; data-calm=&quot;stop:1"],
            out["args"],
            "the ask id was not escaped into its attribute",
        )
        self.assertEqual([], out["acts"], "an ask id declared its own control")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_failed_answer_leaves_the_card_and_says_so(self) -> None:
        # No optimistic hide. A card removed before the answer landed leaves the
        # asking session waiting with nothing on screen to answer it with.
        checks = """
const out = {};
render(withAsks([busy]));
wire({postFails: true});
const before = asked("/api/data");
clickAnswer(0);
await __settle(); await __settle(); await __settle();
out.refetched = asked("/api/data") - before;
out.stillThere = __els.app.innerHTML.includes("Ship the migration now?");
out.note = noteText();
out.notes = noteCount();
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(0, out["refetched"], "a failed answer still refetched")
        self.assertTrue(out["stillThere"], "the card was hidden without the server agreeing")
        self.assertEqual(NOTE, out["note"], "a failed answer said nothing")
        self.assertEqual(1, out["notes"], "the note was drawn more than once")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_non_ok_status_is_the_same_failure_as_a_rejected_fetch(self) -> None:
        checks = """
const out = {};
render(withAsks([busy]));
wire({status: 503});
clickAnswer(0);
await __settle(); await __settle(); await __settle();
out.stillThere = __els.app.innerHTML.includes("Ship the migration now?");
out.note = noteText();
out.notes = noteCount();
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["stillThere"])
        self.assertEqual(NOTE, out["note"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_200_that_answered_nothing_is_reported_not_celebrated(self) -> None:
        # An unknown id or an out-of-range index is a 200 no-op server side, so
        # `ok` alone does not mean the waiting session heard anything.
        checks = """
const out = {};
render(withAsks([busy]));
wire({answered: false});
const before = asked("/api/data");
clickAnswer(0);
await __settle(); await __settle(); await __settle();
out.refetched = asked("/api/data") - before;
out.stillThere = __els.app.innerHTML.includes("Ship the migration now?");
out.note = noteText();
out.notes = noteCount();
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(0, out["refetched"], "a no-op answer was treated as landed")
        self.assertTrue(out["stillThere"])
        self.assertEqual(NOTE, out["note"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_without_the_capability_there_is_no_band_and_no_control(self) -> None:
        # `--no-ask` never registers an ask, so a button that answered 503 would
        # be worse than no button, exactly as it is for `--no-dismiss`.
        checks = """
const out = {};
render(Object.assign(payload([busy]), {asks: [ask()]}));   // no `ask` key
out.band = __els.app.innerHTML.includes("askband");
out.control = askControls().length;
out.question = __els.app.innerHTML.includes("Ship the migration now?");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertFalse(out["band"], "the band appeared with the feature off")
        self.assertEqual(0, out["control"], "an answer control appeared with the feature off")
        self.assertFalse(out["question"], "a question rendered with the feature off")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_capability_with_nothing_pending_draws_no_band(self) -> None:
        checks = """
const out = {};
render(withAsks([busy], []));
out.band = __els.app.innerHTML.includes("askband");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertFalse(out["band"], "an empty asks list still drew a band")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_ask_is_not_a_session_row_and_does_not_move_the_gate_queue(self) -> None:
        # docs/design-dismissals.md D-4: a synthetic row in `d.sessions` would be
        # the page asserting a session state no collector measured, and it would
        # collide with dupMark on the asker's own project label.
        checks = """
const out = {};
render(withAsks([blocked, busy]));
const h = __els.app.innerHTML;
out.sessions = lastData.sessions.length;
out.queue = gateQueue(lastData).length;
out.needRows = (h.match(/class="need(?: cursor)?">/g) || []).length;
out.gateN = (h.match(/class="band-n">([^<]*)</) || [])[1];
out.title = document.title;
out.bandBeforeGate = h.indexOf("askband") < h.indexOf('class="band"');
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(2, out["sessions"], "the page wrote a row into the payload")
        self.assertEqual(1, out["queue"], "the ask leaked into the gate queue")
        self.assertEqual(1, out["needRows"])
        self.assertEqual("1 waiting", out["gateN"], "the ask was counted as a gate")
        # Two, and the band's "1 waiting" above is the reason both numbers are
        # right. The band counts the gate queue, which an ask deliberately stays
        # out of. The title counts everything waiting on the reader, which an ask
        # is. This assertion originally read "(1!)" and was using the title as a
        # proxy for "the ask is not a session" — it was pinning a tile and title
        # that stayed silent while a question waited.
        self.assertEqual("(2!) Cargento", out["title"])
        self.assertTrue(out["bandBeforeGate"], "the asks band is not above the gate queue")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_calm_mode_can_answer_too(self) -> None:
        # Calm returns from render() before the regular band is assembled, so
        # without its own rendering a reader in calm mode could see nothing to
        # answer while a session waited.
        checks = """
const out = {};
render(withAsks([blocked, busy]));
out.mode = displayMode;
out.question = __els.app.innerHTML.includes("Ship the migration now?");
out.inFrame = __els.app.innerHTML.indexOf("askband") > __els.app.innerHTML.indexOf("cm-frame");
wire();
clickAnswer(0);
await __settle(); await __settle(); await __settle();
out.posted = posted();
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks, saved="calm")
        self.assertEqual("calm", out["mode"])
        self.assertTrue(out["question"], "calm mode showed no question to answer")
        self.assertTrue(out["inFrame"], "the calm band landed outside the ledger frame")
        self.assertEqual([{"id": "askA1", "index": 0}], out["posted"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_several_asks_each_carry_their_own_id(self) -> None:
        checks = """
const out = {};
render(withAsks([busy], [ask(), ask({id: "askB2", question: "Drop the index?",
  options: ["Drop", "Keep", "Ask me later"], project: "repo/other", age_sec: 5})]));
out.args = askControls().map(c => c.getAttribute("data-arg"));
out.n = (__els.app.innerHTML.match(/class="askband-n">([^<]*)</) || [])[1];
wire();
clickAnswer(4);
await __settle(); await __settle(); await __settle();
out.posted = posted();
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(
            ["askA1:0", "askA1:1", "askB2:0", "askB2:1", "askB2:2"],
            out["args"],
            "one card's buttons carried another card's id",
        )
        self.assertEqual("2 waiting", out["n"])
        self.assertEqual([{"id": "askB2", "index": 2}], out["posted"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_malformed_entry_does_not_take_the_band_down(self) -> None:
        # `asks` is server-built, but a card that threw would take the whole
        # render with it, including the gate queue below it.
        checks = """
const out = {};
try{
  render(withAsks([blocked], [{id: "askC3", question: "Now what?"}]));
  out.rendered = true;
}catch(e){ out.rendered = false; out.err = String(e); }
out.gate = __els.app.innerHTML.includes('class="band"');
out.opts = askControls().length;
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["rendered"], out.get("err", "the render threw"))
        self.assertTrue(out["gate"], "a malformed ask took the gate queue down with it")
        self.assertEqual(0, out["opts"], "an ask with no options offered a button anyway")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_pending_ask_alone_still_counts_in_the_tile_and_the_title(self) -> None:
        """The tile may not say nothing is waiting while a question is waiting.

        Found by driving a browser rather than by reading: with one ask pending
        and no blocked session, the tile read "Needs you 0" over "Nothing is
        waiting on you." with the question in the band directly beneath it. That
        is the false reassurance cargento#116 was filed for, so it is a defect
        rather than the deferred ordering work in DRC-4178.
        """
        checks = """
const out = {};
render(withAsks([busy], [ask()]));
const h = __els.app.innerHTML;
out.tileVal = (h.match(/class="tile-val alert">([^<]*)</) || [])[1];
out.claimsNothing = h.includes("Nothing is waiting on you.");
out.title = document.title;
out.line = (h.match(/class="tile-sub">([^<]*)</) || [])[1];
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual("1", out["tileVal"], "the tile did not count the pending ask")
        self.assertFalse(out["claimsNothing"], "the tile claimed nothing was waiting")
        self.assertTrue(out["title"].startswith("(1!)"), out["title"])
        self.assertIn("question", out["line"], out["line"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_gate_and_an_ask_are_counted_together_and_named_together(self) -> None:
        checks = """
const out = {};
render(withAsks([blocked, busy], [ask()]));
const h = __els.app.innerHTML;
out.tileVal = (h.match(/class="tile-val alert">([^<]*)</) || [])[1];
out.line = (h.match(/class="tile-sub">([^<]*)</) || [])[1];
out.title = document.title;
out.queue = gateQueue(lastData).length;
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual("2", out["tileVal"], "a gate plus an ask did not total two")
        self.assertEqual("sessions and questions waiting on you", out["line"])
        self.assertTrue(out["title"].startswith("(2!)"), out["title"])
        # The band and the cursor still read gateQueue, which is DRC-4178's call
        # to change, so the ask must not have leaked into it.
        self.assertEqual(1, out["queue"], "the ask leaked into the gate queue")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_band_renders_on_an_empty_board(self) -> None:
        # The empty-board branch is its own assembly, and it is reachable with a
        # question waiting: the PR's own Codex capture ran with no session row at
        # all. Deleting the band from that branch left both page modules green.
        checks = """
const out = {};
render(withAsks([], [ask()]));
const h = __els.app.innerHTML;
out.emptyBoard = h.includes("No session activity in the last");
out.band = h.includes("askband");
out.question = h.includes("Ship the migration now?");
out.controls = askControls().length;
out.bandFirst = h.indexOf("askband") < h.indexOf("No session activity");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["emptyBoard"], "the fixture did not reach the empty-board branch")
        self.assertTrue(out["band"], "the empty board dropped the asks band")
        self.assertTrue(out["question"], "a waiting question was invisible on an empty board")
        self.assertEqual(2, out["controls"], "the empty board drew the card without its buttons")
        self.assertTrue(out["bandFirst"], "the band rendered below the empty-state line")

    def test_the_calm_band_is_bounded_and_scrolls_inside_the_clipping_frame(self) -> None:
        """Every card has to stay clickable in calm mode, at any card count.

        Measured in headless Chrome against the shipped page: `.cm-frame` is a
        fixed-height `overflow:hidden` column, and the band was a flex child
        with no cap and `min-height:auto`, so it could not shrink below its own
        content. Past four cards the lower ones and their answer buttons were
        painted outside the frame with no scrollbar anywhere to reach them, and
        calm mode is sticky in localStorage.
        """
        frame = self._css_rule(".cm-frame")
        self.assertIn("overflow:hidden", frame)
        self.assertIn("height:calc(100vh", frame)
        self.assertIn("min-height:0", self._css_rule(".cm-body"), "the ledger cannot yield room")

        band = self._css_rule(".cm-frame .askband")
        cap = re.search(r"max-height:([^;}]+)", band)
        self.assertIsNotNone(cap, "the calm band is unbounded inside a clipping frame")
        assert cap is not None
        # Viewport- or container-relative, so the cap is always less than the
        # frame it sits in. A px cap would exceed the frame on a short viewport,
        # which is the case that clipped.
        self.assertRegex(cap.group(1).strip(), r"^\d+(?:\.\d+)?(?:vh|%)$")
        self.assertRegex(band, r"overflow(?:-y)?:auto", "the capped band has no way to scroll")

    @staticmethod
    def _css_rule(selector: str) -> str:
        found = re.search(r"(?:^|[{}\s])" + re.escape(selector) + r"\{([^}]*)\}", STYLES)
        if found is None:
            msg = f"no rule for {selector} in styles.css"
            raise AssertionError(msg)
        return found.group(1)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_calm_bands_scroll_offset_survives_the_poll(self) -> None:
        # The same reason calmScrollTop exists, on the surface where the cost is
        # higher: the band's cards are buttons. A scroll offset reset by the 5s
        # poll does not merely lose the reader's place, it slides a different
        # question's button under a cursor already on its way down.
        checks = """
const out = {};
render(withAsks([blocked, busy], [ask(), ask({id: "askB2"})]));
out.hasId = __els.app.innerHTML.includes('id="askband"');
__askScroll = 96;
render(withAsks([blocked, busy], [ask(), ask({id: "askB2"})]));
out.kept = __askScroll;
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks, saved="calm")
        self.assertTrue(out["hasId"], "the band has no id to restore a scroll offset through")
        self.assertEqual(96, out["kept"], "the poll reset the asks band's scroll offset")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_failure_note_belongs_to_the_card_it_describes(self) -> None:
        # Band-level, the note sat above every card including the ones that had
        # answered fine.
        checks = """
const out = {};
render(withAsks([busy], [ask(), ask({id: "askB2", question: "Drop the index?",
  options: ["Drop", "Keep"]})]));
wire({postFails: true});
clickAnswer(0);
await __settle(); await __settle(); await __settle();
const h = __els.app.innerHTML;
out.note = noteText();
out.notes = noteCount();
out.insideFailedCard = h.indexOf("ask-note") > h.indexOf("Ship the migration now?")
  && h.indexOf("ask-note") < h.indexOf("Drop the index?");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(NOTE, out["note"])
        self.assertEqual(1, out["notes"], "one failure marked more than one card")
        self.assertTrue(out["insideFailedCard"], "the note was not drawn inside the failing card")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_note_does_not_outlive_the_card_it_was_written_for(self) -> None:
        # The answered-or-swept case, which is why the old wording was wrong as
        # well as misplaced: by the time the reader reads the note, the ask it
        # named is often gone from the payload, and a different one is on screen.
        checks = """
const out = {};
render(withAsks([busy], [ask()]));
wire({postFails: true});
clickAnswer(0);
await __settle(); await __settle(); await __settle();
out.noteWhileThere = noteCount();
render(withAsks([busy], [ask({id: "askB2", question: "Drop the index?"})]));
out.noteAfterGone = noteCount();
out.stillShowsB = __els.app.innerHTML.includes("Drop the index?");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(1, out["noteWhileThere"])
        self.assertTrue(out["stillShowsB"], "the replacement card did not render")
        self.assertEqual(
            0, out["noteAfterGone"], "a stale note appeared above an unrelated question"
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_only_the_card_that_landed_loses_its_note(self) -> None:
        """A success on one card cleared the note on another, and vice versa.

        Both directions come out of the same band-level variable: answering B
        wiped the standing note on A, which had genuinely failed, and a failure
        on A wrote a note the reader read above B. Every payload here still
        lists both asks, so a note that survived is a note that rendered rather
        than one pruned away with its card.
        """
        both = 'withAsks([busy], [ask(), ask({id: "askB2", question: "Drop the index?", '
        both += 'options: ["Drop", "Keep"]})])'
        checks = f"""
const out = {{}};
const both = () => {both};
render(both());
wire({{postFails: true}});
clickAnswer(0);
await __settle(); await __settle(); await __settle();
out.afterFailA = noteCount();
// B lands. A's failure is still the last thing anybody knows about A.
wire({{after: both()}});
clickAnswer(2);
await __settle(); await __settle(); await __settle();
out.afterLandB = noteCount();
out.stillOnA = __els.app.innerHTML.indexOf("ask-note")
  < __els.app.innerHTML.indexOf("Drop the index?");
// Then A lands too, and only now should the note go.
clickAnswer(0);
await __settle(); await __settle(); await __settle();
out.afterLandA = noteCount();
out.bothStillListed = __els.app.innerHTML.includes("Ship the migration now?")
  && __els.app.innerHTML.includes("Drop the index?");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(1, out["afterFailA"])
        self.assertEqual(1, out["afterLandB"], "answering one card cleared another card's note")
        self.assertTrue(out["stillOnA"], "the surviving note moved to the card that succeeded")
        self.assertTrue(out["bothStillListed"], "the fixture stopped listing both asks")
        self.assertEqual(0, out["afterLandA"], "an answer that landed left its own failure note up")


if __name__ == "__main__":
    unittest.main()
