"""The asks band: what the page does when a session asks the reader a question.

Executed against the shipped script, like every other page test here. The two
things these have to prove are the two things a string assertion would not: the
question and its options are agent-written text and reach the document as text,
and a card whose answer did not land stays on screen, because the session is
holding its tool call open and a hidden card would leave it waiting on nothing.
"""

from __future__ import annotations

import shutil
import unittest
from typing import Any

from .page_harness import PageJsHarness
from .test_page_calm import CalmModeTest


class AskBandTest(PageJsHarness):
    # The calm fixture plus the payload fields the feature adds. `ask` is the
    # server's capability flag and `asks` the outstanding questions; the page
    # derives neither, and it never puts one in `sessions`.
    FIXTURE = (
        CalmModeTest.FIXTURE
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
"""
    )

    def run_page(self, checks: str, *, saved: str = "regular") -> Any:
        return self._run_page_js(
            self.FIXTURE + checks, prelude=CalmModeTest.prelude(saved, clipboard="none")
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
out.rawQuote = /class="ask-opt"[^>]*onclick/.test(h);
out.escaped = h.includes("&lt;img src=x onerror=&quot;boom()&quot;&gt;hi");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertFalse(out["rawImg"], "an agent's question reached the document as markup")
        self.assertFalse(out["rawScript"], "an agent's option reached the document as markup")
        self.assertFalse(out["rawClose"], "an option closed the button element around it")
        self.assertFalse(out["rawQuote"], "an option broke out of its attribute")
        self.assertTrue(out["escaped"], "the question was not rendered at all")

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
out.note = __els.app.innerHTML.includes("could not answer");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(0, out["refetched"], "a failed answer still refetched")
        self.assertTrue(out["stillThere"], "the card was hidden without the server agreeing")
        self.assertTrue(out["note"], "a failed answer said nothing")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_non_ok_status_is_the_same_failure_as_a_rejected_fetch(self) -> None:
        checks = """
const out = {};
render(withAsks([busy]));
wire({status: 503});
clickAnswer(0);
await __settle(); await __settle(); await __settle();
out.stillThere = __els.app.innerHTML.includes("Ship the migration now?");
out.note = __els.app.innerHTML.includes("could not answer");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["stillThere"])
        self.assertTrue(out["note"])

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
out.note = __els.app.innerHTML.includes("could not answer");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(0, out["refetched"], "a no-op answer was treated as landed")
        self.assertTrue(out["stillThere"])
        self.assertTrue(out["note"])

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
        self.assertEqual("(1!) Cargento", out["title"])
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


if __name__ == "__main__":
    unittest.main()
