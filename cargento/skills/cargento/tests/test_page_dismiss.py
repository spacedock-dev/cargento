"""The handled control: what the page does when a reader clears a session.

Executed against the shipped script, like every other page test here: the
subtraction is the server's, so what these prove is that the page asks for it,
never that it hid a row on its own.
"""

from __future__ import annotations

import shutil
import unittest
from typing import Any

from .page_harness import PageJsHarness
from .test_page_calm import CalmModeTest


class HandledControlTest(PageJsHarness):
    # The calm fixture plus the two fields the feature adds to the payload, and
    # one click helper. `dismiss` is the server's capability flag and `cleared`
    # its count of subtracted rows — the page derives neither.
    FIXTURE = (
        CalmModeTest.FIXTURE
        + """
const withDismiss = (sessions, cleared) => Object.assign(payload(sessions),
  {dismiss: true, cleared: cleared === undefined ? 0 : cleared});
const clickCalm = (act, arg) => __fire("click", {target: {closest: sel =>
  sel === "[data-calm]" ? {getAttribute: a => a === "data-calm" ? act
    : (a === "data-arg" ? (arg === undefined ? null : arg) : null)} : null}});
const key = k => __fire("keydown", {key: k, target: {}, preventDefault(){}});
// Answers both routes the feature touches, and records every request.
const wire = (opts) => {
  const o = opts || {};
  __fetchImpl = (url, init) => {
    const u = String(url);
    if(u === "/api/dismiss"){
      if(o.postFails) return Promise.reject(new Error("connection refused"));
      return Promise.resolve({ok: true, json: () => Promise.resolve(
        {ok: true, persisted: o.persisted === undefined ? true : o.persisted, cleared: 1})});
    }
    if(u === "/api/cleared"){
      return Promise.resolve({ok: true, json: () => Promise.resolve(
        {cleared: o.list === undefined
          ? [{harness: "claude", sid: "aaa1", at: 99700}] : o.list})});
    }
    return Promise.resolve({ok: true, json: () => Promise.resolve(
      o.after === undefined ? withDismiss([busy], 1) : o.after)});
  };
};
const posted = () => __fetchCalls.filter(c => String(c[0]) === "/api/dismiss")
  .map(c => JSON.parse(c[1].body));
const asked = url => __fetchCalls.filter(c => String(c[0]) === url).length;
"""
    )

    def run_page(self, checks: str) -> Any:
        return self._run_page_js(
            self.FIXTURE + checks, prelude=CalmModeTest.prelude("calm", clipboard="none")
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_marking_a_session_handled_posts_the_pair_and_refetches(self) -> None:
        checks = """
const out = {};
render(withDismiss([blocked, busy]));
out.control = __els.app.innerHTML.includes('data-calm="handled"');
// The row has to be open for the drawer control to exist; the keyboard path is
// tested separately.
clickCalm("open", K("claude", "aaa1"));
wire();
const before = asked("/api/data");
clickCalm("handled", K("claude", "aaa1"));
await __settle(); await __settle(); await __settle();
out.posted = posted();
out.refetched = asked("/api/data") - before;
out.rowsAfter = rows();
out.stillThere = __els.app.innerHTML.includes("aaa1");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertFalse(out["control"], "the closed row should not carry the drawer control")
        self.assertEqual(
            [{"harness": "claude", "sid": "aaa1", "clear": True}],
            out["posted"],
            "one POST carrying the (harness, sid) pair and nothing else",
        )
        self.assertEqual(1, out["refetched"], "the page did not refetch after the mark")
        # The server's next payload is what removes it. That is the whole point:
        # the count in the tile, the tab title and both views follow the payload.
        self.assertEqual(1, out["rowsAfter"])
        self.assertFalse(out["stillThere"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_failed_post_leaves_the_row_and_says_so(self) -> None:
        # No optimistic hide. A row removed locally before the server agreed is
        # the one lie this board must not tell.
        checks = """
const out = {};
render(withDismiss([blocked, busy]));
clickCalm("open", K("claude", "aaa1"));
wire({postFails: true});
const before = asked("/api/data");
clickCalm("handled", K("claude", "aaa1"));
await __settle(); await __settle(); await __settle();
out.refetched = asked("/api/data") - before;
out.stillThere = __els.app.innerHTML.includes("aaa1");
out.note = __els.app.innerHTML.includes("clear failed");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertEqual(0, out["refetched"], "a failed mark still refetched")
        self.assertTrue(out["stillThere"], "the row was hidden without the server agreeing")
        self.assertTrue(out["note"], "a failed mark said nothing")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_mark_that_never_reached_disk_says_which(self) -> None:
        # It holds for this run either way, so the row does leave — but a mark
        # that will not survive a restart must not look durable.
        checks = """
const out = {};
render(withDismiss([blocked, busy]));
clickCalm("open", K("claude", "aaa1"));
wire({persisted: false});
clickCalm("handled", K("claude", "aaa1"));
await __settle(); await __settle(); await __settle();
out.gone = !__els.app.innerHTML.includes("aaa1");
out.note = __els.app.innerHTML.includes("could not write the store");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["gone"])
        self.assertTrue(out["note"], "an unwritable store was reported as a durable mark")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_without_the_capability_there_is_no_control_and_no_key(self) -> None:
        # `--no-dismiss` leaves the store unread and unwritten, so a button that
        # answered 503 would be worse than no button.
        checks = """
const out = {};
render(payload([blocked, busy]));            // no `dismiss` key
clickCalm("open", K("claude", "aaa1"));
out.control = __els.app.innerHTML.includes('data-calm="handled"');
out.chip = __els.app.innerHTML.includes('data-calm="cleared"');
out.legend = __els.app.innerHTML.includes("x handled");
wire();
key("x");
await __settle(); await __settle();
out.posted = posted().length;
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertFalse(out["control"], "the control appeared with the feature off")
        self.assertFalse(out["chip"], "the chip appeared with the feature off")
        self.assertFalse(out["legend"], "the ledger advertised a key that does nothing")
        self.assertEqual(0, out["posted"], "`x` posted with the feature off")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_x_marks_the_row_under_the_cursor(self) -> None:
        checks = """
const out = {};
render(withDismiss([blocked, busy]));
out.legend = __els.app.innerHTML.includes("x handled");
wire();
key("x");                                     // no cursor moved yet: the head
await __settle(); await __settle(); await __settle();
out.posted = posted();
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["legend"], "the ledger did not advertise the key")
        # `blocked` is the head of the attention order, so the cursor is on it.
        self.assertEqual([{"harness": "claude", "sid": "aaa1", "clear": True}], out["posted"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_chip_reveals_the_list_and_one_row_goes_back(self) -> None:
        checks = """
const out = {};
render(withDismiss([busy], 1));
out.chip = __els.app.innerHTML.includes('data-calm="cleared"');
out.count = __els.app.innerHTML.includes("1 handled");
wire();
clickCalm("cleared");
await __settle(); await __settle();
out.askedList = asked("/api/cleared");
out.listed = __els.app.innerHTML.includes("aaa1");
out.restoreControl = __els.app.innerHTML.includes('data-calm="restore"');
clickCalm("restore", K("claude", "aaa1"));
await __settle(); await __settle(); await __settle();
out.posted = posted();
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["chip"], "no way to see what was cleared")
        self.assertTrue(out["count"], "the chip did not carry the server's count")
        self.assertEqual(1, out["askedList"])
        self.assertTrue(out["listed"], "the panel did not list the cleared session")
        self.assertTrue(out["restoreControl"])
        self.assertEqual([{"harness": "claude", "sid": "aaa1", "clear": False}], out["posted"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_chip_sits_in_the_mode_bar_and_not_on_the_idle_toggle(self) -> None:
        # Two reveal controls in one place is the collision the idle clip's own
        # boundary note exists to avoid: that toggle reveals rows the payload
        # carries, and this chip reveals rows it does not.
        checks = """
const out = {};
render(withDismiss([blocked, busy, quiet, mk({sid: "d4", session: "d4",
  last_activity: 98000}), mk({sid: "d5", session: "d5", last_activity: 97000})], 2));
const h = __els.app.innerHTML;
out.chipBeforeFrame = h.indexOf('data-calm="cleared"') < h.indexOf("cm-frame");
out.inModebar = /class="modebar">\\s*<span class="clearedbar">\\s*<button[^>]*data-calm="cleared"/
  .test(h);
out.idleToggleUntouched = h.includes('data-calm="idle"')
  && !/data-calm="idle"[^>]*cleared/.test(h);
out.clipStillThere = h.includes("idle-clip");
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["chipBeforeFrame"], "the chip is not in the mode bar")
        self.assertTrue(out["inModebar"], "the chip is not the mode bar's first control")
        self.assertTrue(out["idleToggleUntouched"], "the chip landed on the idle toggle")
        self.assertTrue(out["clipStillThere"], "the idle clip stopped clipping")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_gate_row_carries_the_control_in_regular_mode(self) -> None:
        # A gate the reader has decided to answer elsewhere is exactly the row
        # they want off the board.
        checks = """
const out = {};
setDisplayMode("regular");
render(withDismiss([blocked, busy]));
const h = __els.app.innerHTML;
out.band = h.includes('class="need');
out.control = /class="need-act"[\\s\\S]*?data-calm="handled"/.test(h);
wire();
clickCalm("handled", K("claude", "aaa1"));
await __settle(); await __settle(); await __settle();
out.posted = posted();
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertTrue(out["band"], "the gate band did not render")
        self.assertTrue(out["control"], "the gate row carries no handled control")
        self.assertEqual([{"harness": "claude", "sid": "aaa1", "clear": True}], out["posted"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_row_with_no_session_id_gets_no_control(self) -> None:
        # The server keys its store on `sid` alone. sessKey() falls back to the
        # display id, which would write a mark that never matched a row again.
        checks = """
const out = {};
render(withDismiss([mk({sid: "", session: "zz9", state: "needs_input", active: true,
  last_activity: 99700, title: "No id"}), busy]));
clickCalm("open", "claude:zz9");
out.control = __els.app.innerHTML.includes('data-calm="handled"');
console.log(JSON.stringify(out));
"""
        out = self.run_page(checks)
        self.assertFalse(out["control"], "a row with no sid offered a mark the server cannot key")


if __name__ == "__main__":
    unittest.main()
