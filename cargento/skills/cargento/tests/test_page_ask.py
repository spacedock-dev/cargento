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
__els["waitband"] = {
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
out.n = (h.match(/class="band-n">([^<]*)</) || [])[1];
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
        # Two, because the band is the whole queue: this payload carries a
        # blocked session as well as the question, and a head that counted only
        # one kind would disagree with the tile and the tab title above it.
        self.assertEqual("2 waiting", out["n"])

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
out.band = __els.app.innerHTML.includes("waitband");
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
out.band = __els.app.innerHTML.includes("waitband");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertFalse(out["band"], "an empty asks list still drew a band")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_ask_is_not_a_session_row_even_though_it_shares_the_queue(self) -> None:
        # docs/design-dismissals.md D-4: a synthetic row in `d.sessions` would be
        # the page asserting a session state no collector measured, and it would
        # collide with dupMark on the asker's own project label. Folding the two
        # into one order did not reverse that — `gateQueue` is still a filter over
        # sessions and the question is still absent from it — so this is the test
        # that says the merge happens in the reader rather than in the payload.
        checks = """
const out = {};
render(withAsks([blocked, busy]));
const h = __els.app.innerHTML;
out.sessions = lastData.sessions.length;
out.gates = gateQueue(lastData).length;
out.needRows = (h.match(/class="need(?: cursor)?">/g) || []).length;
out.n = (h.match(/class="band-n">([^<]*)</) || [])[1];
out.title = document.title;
out.bands = (h.match(/class="band"/g) || []).length;
// The gate has been blocked since 99700 against a payload generated at 100000;
// the question is 42s old. So the gate has waited longer and leads, which is the
// merge deciding rather than either list being appended to the other.
out.gateFirst = h.indexOf('class="need-title"') < h.indexOf('class="ask-q"');
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(2, out["sessions"], "the page wrote a row into the payload")
        self.assertEqual(1, out["gates"], "the ask leaked into the gate half of the queue")
        self.assertEqual(1, out["needRows"])
        # One band and one count, over both kinds — the tile and the tab title
        # read the same list, so a head that disagreed with them would be the
        # false reassurance cargento#116 was filed for, one surface further on.
        self.assertEqual("2 waiting", out["n"])
        self.assertEqual(1, out["bands"], "the questions kept a band of their own")
        self.assertEqual("(2!) Cargento", out["title"])
        self.assertTrue(out["gateFirst"], "the merge did not put the longer wait first")

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
out.inFrame = __els.app.innerHTML.indexOf("waitband") > __els.app.innerHTML.indexOf("cm-frame");
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
out.n = (__els.app.innerHTML.match(/class="band-n">([^<]*)</) || [])[1];
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
out.band = h.includes("waitband");
out.question = h.includes("Ship the migration now?");
out.controls = askControls().length;
out.bandFirst = h.indexOf("waitband") < h.indexOf("No session activity");
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

        band = self._css_rule(".cm-frame .band")
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
out.hasId = __els.app.innerHTML.includes('id="waitband"');
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


class WaitingQueueTest(PageJsHarness):
    """One order over the two kinds of thing that wait on a reader, and its keys.

    DRC-4172 shipped the asks as their own band above the gate queue, with the
    queue's ordering, its cursor and its keys stopping at the band's edge. These
    are about the pass that folds the two together: a single definition of the
    order, a cursor that holds a key rather than a position, and the same
    keystrokes reaching both kinds in both display modes.
    """

    # `since` is stated rather than an age, because that is what the merge ranks
    # on and the two payload fields spell it differently: a gate carries an
    # absolute `blocked_since`, an ask carries `age_sec` off the same clock that
    # stamped `generated`. Both lists are handed over in the order their own
    # server-side sort publishes them, which is what the merge is entitled to
    # assume — `row_order` in aggregate.py and `AskRegistry.pending` are tested
    # for those two sorts.
    FIXTURE = (
        test_page_calm.CalmModeTest.FIXTURE
        + """
const GEN = 100000;
const gateAt = (sid, since) => mk({sid, session: sid, title: "gate-" + sid,
  state: "needs_input", active: true, last_activity: since, blocked_since: since,
  state_detail: "permission needed"});
const askAt = (id, since, options) => ({id, harness: "codex", session_id: "s-" + id,
  project: "repo/asker", question: "q-" + id, age_sec: GEN - since,
  options: options === undefined ? ["Yes", "No"] : options});
const queueBoard = (gates, asks) => Object.assign(payload(gates),
  {ask: true, asks: asks || []});
// Read back off the DOM in document order, so a merge that only happens in the
// model and never reaches the band fails here.
const bandOrder = () => [...__els.app.innerHTML.matchAll(
  /class="need-title">gate-([a-z0-9]+)<|class="ask-q">q-([a-z0-9]+)</g)]
  .map(m => m[1] ? "gate-" + m[1] : "ask-" + m[2]);
const cursorOn = () => {
  const h = __els.app.innerHTML;
  const gate = h.match(/class="need cursor">[\\s\\S]*?class="need-title">gate-([a-z0-9]+)</);
  if(gate) return "gate-" + gate[1];
  const asked = h.match(/class="ask cursor">[\\s\\S]*?class="ask-q">q-([a-z0-9]+)</);
  return asked ? "ask-" + asked[1] : null;
};
const key = k => __fire("keydown", {key: k, target: {tagName: "BODY"},
                                    preventDefault(){}});
// Two gates and two asks, interleaved: neither kind is contiguous in the merged
// order, so a page that concatenates the lists in either direction fails.
const G1 = gateAt("g1", 99100), G3 = gateAt("g3", 99500);
const A2 = askAt("a2", 99300), A4 = askAt("a4", 99700);
const mixed = () => queueBoard([G1, G3], [A2, A4]);
"""
    )

    def run_queue(self, checks: str, *, saved: str = "regular") -> Any:
        return self._run_page_js(
            self.FIXTURE + checks,
            prelude=test_page_calm.CalmModeTest.prelude(saved, clipboard="ok"),
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_one_merged_order_covers_both_kinds_and_the_band_renders_it(self) -> None:
        # The order is a merge of two lists that each arrive sorted, never a
        # re-sort of either: the comparator only ever decides between one gate
        # and one ask. So the queue is longest-waiting first across both kinds,
        # and the band draws exactly that.
        checks = """
const out = {};
render(mixed());
out.keys = waitingQueue(lastData).map(e => e.key);
out.kinds = waitingQueue(lastData).map(e => e.kind);
out.positions = waitingQueue(lastData).map(e => e.pos);
out.drawn = bandOrder();
out.bands = (__els.app.innerHTML.match(/class="band"/g) || []).length;
out.n = (__els.app.innerHTML.match(/class="band-n">([^<]*)</) || [])[1];
console.log(JSON.stringify(out));
"""
        out = self.run_queue(checks)
        self.assertEqual(
            ["claude:g1", "ask:a2", "claude:g3", "ask:a4"],
            out["keys"],
            "the two kinds were concatenated rather than merged",
        )
        self.assertEqual(["gate", "ask", "gate", "ask"], out["kinds"])
        self.assertEqual([1, 2, 3, 4], out["positions"])
        self.assertEqual(
            ["gate-g1", "ask-a2", "gate-g3", "ask-a4"],
            out["drawn"],
            "the band did not render the merged order",
        )
        self.assertEqual(1, out["bands"], "the asks kept a band of their own")
        self.assertEqual("4 waiting", out["n"], "the band head did not count both kinds")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_cursor_holds_an_ask_by_its_id_and_does_not_slide(self) -> None:
        # The reason gateFocusKey() held a session key rather than an index,
        # carried over to the other kind of row: answering something above the
        # cursor must not move the cursor onto a different question. The ask id
        # is what makes that possible — it is generated once at registration, it
        # addresses the answer route, and it leaves the payload at the moment the
        # card leaves the board.
        checks = """
const out = {};
render(mixed());
out.head = cursorOn();
key("j"); key("j"); key("j");
out.onTailAsk = cursorOn();
out.cursorKey = waitCursorKey;
// The head gate is answered elsewhere and the first ask is answered in someone
// else's tab: both leave the payload. An index-based cursor lands on a
// different question here.
render(queueBoard([G3], [A4]));
out.afterOthersLeft = cursorOn();
out.keyKept = waitCursorKey;
// And when the cursor's own ask is answered, the pass advances to the head
// rather than stranding.
render(queueBoard([G3], []));
out.afterMineLeft = cursorOn();
console.log(JSON.stringify(out));
"""
        out = self.run_queue(checks)
        self.assertEqual("gate-g1", out["head"])
        self.assertEqual("ask-a4", out["onTailAsk"], "j did not step through the asks")
        self.assertEqual("ask:a4", out["cursorKey"], "the cursor is not keyed on the ask id")
        self.assertEqual(
            "ask-a4", out["afterOthersLeft"], "the cursor slid onto a different waiting thing"
        )
        self.assertEqual("ask:a4", out["keyKept"])
        self.assertEqual("gate-g3", out["afterMineLeft"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_g_reaches_the_head_of_the_queue_when_the_head_is_an_ask(self) -> None:
        # `g` names the queue, so it has to reach whatever is at the head of it.
        # With an ask waiting longer than every gate, a `g` that walked the gates
        # alone skipped the very thing that had waited longest.
        checks = """
const out = {};
const askHead = () => queueBoard([G3], [askAt("a0", 99000)]);
render(askHead());
key("g");
out.regularCursor = waitCursorKey;
out.regularDrawn = cursorOn();
out.regularOrder = waitingQueue(lastData).map(e => e.key);
setDisplayMode("calm");
// Cleared first: the regular pass above left its own cursor on the same ask, and
// reading a stale value here would pass whatever calm's `g` did.
waitCursorKey = null;
calmCursorKey = null;
render(askHead());
key("g");
out.calmCursor = calmCursorKey;
out.calmDrawn = cursorOn();
// Both modes read the one order, so both land on the same waiting thing.
out.calmOrder = waitingQueue(lastData).map(e => e.key);
console.log(JSON.stringify(out));
"""
        out = self.run_queue(checks)
        self.assertEqual("ask:a0", out["regularCursor"], "`g` skipped the ask at the head")
        self.assertEqual("ask-a0", out["regularDrawn"], "the band drew no cursor on the ask")
        self.assertEqual("ask:a0", out["calmCursor"], "calm's `g` skipped the ask at the head")
        self.assertEqual("ask-a0", out["calmDrawn"], "calm drew no cursor on the ask")
        self.assertEqual(out["regularOrder"], out["calmOrder"], "the two modes ordered differently")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_g_narrows_calms_ledger_only_when_the_queue_holds_a_gate(self) -> None:
        # `needs` filters the ledger to the blocked rows, and a queue of
        # questions alone has none — the ordinary shape, since most harnesses
        # report no `needs_input` at all and a question is Cargento's own. `g`
        # applied it regardless, so on a board whose only waiting thing was a
        # question the ledger collapsed to "Nothing matches this filter" and the
        # reader lost the rest of the board to reach a card already on screen.
        checks = """
const out = {};
// Question-only: two ordinary rows in the ledger, no gate anywhere.
render(queueBoard([busy, quiet], [askAt("a0", 99000)]));
out.before = rows();
key("g");
out.askOnlyRows = rows();
out.askOnlyFilter = calmStateOnly;
out.askOnlyCursor = calmCursorKey;
out.askOnlyEmpty = __els.app.innerHTML.includes("Nothing matches this filter");
// The control arm: one gate in the queue and the narrowing is back, ordering
// included. Without this the fix could be "never narrow" and still pass.
calmAction("clear", null);
calmAction("sort", "recent");
render(queueBoard([gateAt("g1", 99100), busy, quiet], [askAt("a0", 99000)]));
key("g");
out.mixedFilter = calmStateOnly;
out.mixedSort = calmSort;
out.mixedRows = rows();
out.mixedCursor = calmCursorKey;
console.log(JSON.stringify(out));
"""
        out = self.run_queue(checks, saved="calm")
        self.assertEqual(2, out["before"])
        self.assertEqual(2, out["askOnlyRows"], "`g` filtered the board down to nothing")
        self.assertIsNone(out["askOnlyFilter"], "a queue with no gate in it still narrowed")
        self.assertFalse(out["askOnlyEmpty"])
        self.assertEqual("ask:a0", out["askOnlyCursor"], "`g` did not reach the question")
        self.assertEqual("needs", out["mixedFilter"], "a real gate queue stopped narrowing")
        self.assertEqual("attention", out["mixedSort"])
        self.assertEqual(1, out["mixedRows"], "the narrowed ledger is not the gate alone")
        self.assertEqual("ask:a0", out["mixedCursor"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_only_the_band_that_draws_the_whole_queue_numbers_its_rows(self) -> None:
        # An ordinal is a place in the queue, so it belongs to the band that
        # draws the queue. Calm and the session view draw the questions with the
        # gates elsewhere. Deriving that from "shown is as long as the queue"
        # made it true exactly when no gate happened to exist, so calm's numbers
        # appeared and disappeared as gates came and went on the board.
        checks = """
const out = {};
const ords = () => [...__els.app.innerHTML.matchAll(/class="need-n">([^<]*)</g)]
  .map(m => m[1]);
const asksOnly = () => queueBoard([busy, quiet], [askAt("a2", 99300), askAt("a4", 99700)]);
render(asksOnly());
out.calmNoGate = ords();
render(mixed());
out.calmWithGate = ords();
render(asksOnly());
out.calmGateGone = ords();
setDisplayMode("session");
location.hash = "#session=codex:bbb2";
render(asksOnly());
out.sessionNoGate = ords();
render(mixed());
out.sessionWithGate = ords();
setDisplayMode("regular");
render(mixed());
out.regular = ords();
render(asksOnly());
out.regularAsksOnly = ords();
console.log(JSON.stringify(out));
"""
        out = self.run_queue(checks, saved="calm")
        self.assertEqual([], out["calmNoGate"], "calm numbered a band the queue runs past")
        self.assertEqual([], out["calmWithGate"])
        self.assertEqual([], out["calmGateGone"], "calm's ordinals came back when the gate left")
        self.assertEqual([], out["sessionNoGate"], "the session view numbered its band")
        self.assertEqual([], out["sessionWithGate"])
        self.assertEqual(
            ["1", "2", "3", "4"], out["regular"], "the regular band stopped numbering the queue"
        )
        self.assertEqual(["1", "2"], out["regularAsksOnly"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_calm_steps_the_asks_with_the_same_keys_regular_does(self) -> None:
        # Calm shipped the band reachable but not walkable: `j` and `k` moved
        # through the ledger's session rows and could not reach a question at
        # all, so the one thing on a calm board that is answered ON the board was
        # the one thing the keyboard could not select.
        checks = """
const out = {};
render(mixed());
out.calmMode = displayMode;
out.startsOnAsk = cursorOn();
key("j");
out.afterJ = cursorOn();
// Calm's pass has its own cursor variable because it is longer than the queue —
// its ledger rows come after the questions — but it holds a key the same way,
// and an ask's key is one of the keys it can hold.
out.cursorKey = calmCursorKey;
key("k");
out.afterK = cursorOn();
out.asksDrawn = bandOrder();
console.log(JSON.stringify(out));
"""
        out = self.run_queue(checks, saved="calm")
        self.assertEqual("calm", out["calmMode"])
        # The band sits above the ledger in calm, so the questions lead the pass
        # there. What has to hold is that the keys reach them at all and that the
        # order among them is the queue's.
        self.assertEqual("ask-a2", out["startsOnAsk"], "calm's cursor could not reach a question")
        self.assertEqual("ask-a4", out["afterJ"], "j did not step between the questions")
        self.assertEqual("ask:a4", out["cursorKey"])
        self.assertEqual("ask-a2", out["afterK"])
        self.assertEqual(["ask-a2", "ask-a4"], out["asksDrawn"], "calm reordered the questions")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_enter_hands_the_keyboard_to_the_cards_own_buttons(self) -> None:
        # Enter on a gate copies the session id, because a gate is answered in
        # the session's own terminal. Enter on an ask must NOT pick an option:
        # the answer is irreversible and reaches an agent, so the keystroke moves
        # focus onto the card's first button and lets the reader choose.
        checks = """
const out = {};
render(mixed());
key("Enter");
await __settle();
out.copiedGate = __wrote.slice();
out.gateHint = (__els.app.innerHTML.match(/class="band-keys">([^<]*)</) || [])[1];
key("j");
out.focusedBefore = __focused;
key("Enter");
out.focusedAfter = __focused;
out.askHint = (__els.app.innerHTML.match(/class="band-keys">([^<]*)</) || [])[1];
out.answered = __fetchCalls.filter(c => String(c[0]) === "/api/answer").length;
console.log(JSON.stringify(out));
"""
        out = self.run_queue(checks)
        self.assertEqual(["g1"], out["copiedGate"], "Enter on a gate stopped copying its id")
        self.assertIn("⏎ copy id", out["gateHint"])
        self.assertIsNone(out["focusedBefore"])
        self.assertEqual(
            "answer:a2:0", out["focusedAfter"], "Enter on a question focused no answer button"
        )
        self.assertIn("⏎ answer", out["askHint"], "the hint still named the gate action")
        self.assertEqual(0, out["answered"], "Enter answered a question the reader did not pick")


if __name__ == "__main__":
    unittest.main()
