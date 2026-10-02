"""Steer back and Update intent instead, on the session page (DRC-4681, DRC-4697).

Items 7 and 8 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
built to the owner's rulings of 2026-09-28. Steer back is drawn only where there is something to
steer from: under a departure it is the stage's one primary with Update intent instead beside it;
with no reader it takes Analyze's slot as the primary; with a reader and no analysis it sits beside
Analyze as a secondary. It opens the server's correction, with "#n" filled from the page's own
numbering, in an editable box capped at 2,000 characters. Copy writes the box's exact text and then
records that text; nothing is sent to the session. Update intent instead offers the direction a
departure cites, else the latest, else an empty line, and a saved line names where it came from.

Every assertion is on what a reader sees or what the page sends. The corrections the fake server
answers are composed by `correction.compose` from the same facts, so the page is asserted against
the server's own words.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import unittest
from typing import Any

from cargento_runtime import correction

from .next_harness import NEXT_STYLES
from .test_next_drift_panel import routes
from .test_next_intent_draft import (
    PRIMARY,
    ROUTE,
    TYPED,
    _DraftPage,
    aside_of,
    drift_of,
    visible_text,
)

KEY = "claude:focus-1"
LINE = "The parser tests pass"
HINT = "Cargento never sends this. Copy it and paste it into the session."
TOO_LONG = "This correction would be longer than 2,000 characters. Shorten a line of your intent."

# A failed check after the words, planted with a command in its summary. The fixture numbers the
# session's entries in the window from 100: fo-b #1, task-a #2, fo-a #3, c-fail #4.
CHECK = """
__semantic.facts.push({fact_id:"c-fail", at:104.5, type:"tool_report", subject:"check",
  result:"failed", summary:"pytest INJECTED-COMMAND",
  source_session:{harness:"claude", sid:"focus-1"},
  evidence:{source:"Claude Bash call and paired result", confidence:"exact"}});
__s.annotation_window_start = 100;
"""
# The words were saved after every direction in the record, so none is later.
QUIET = "__s.annotation_goal_saved_at = 105;\n__s.annotation_window_start = 100;\n"
LINES = f'__s.annotation_line_1 = {json.dumps(LINE)};\n__s.annotation_lines_why = "";\n'
DEPARTURE = """
__s.annotation_reading_count = 1;
__s.annotation_assessment = {revision_read:2, window_start:100, read_at:106, criteria:{
  goal:{result:"not verifiable from available evidence", cites:[], why:"uncited"},
  line_1:{result:"departure", detail:"INJECTED-PROSE", cites:["c-fail"]}}};
"""
SETTLED = "__s.annotation_settled_through = 104.8;\n__s.annotation_settled_at = 106;\n"
# A goal departure citing fo-a, a later direction the reader settled with Keep.
CITED = """
__s.annotation_settled_through = 104.8;
__s.annotation_settled_at = 106;
__s.annotation_reading_count = 1;
__s.annotation_assessment = {revision_read:2, window_start:100, read_at:106, criteria:{
  goal:{result:"departure", detail:"INJECTED-PROSE", cites:["fo-a"]}}};
"""
# A later direction after fo-a that no departure cites: the latest.
LATEST = """
__semantic.facts.push({fact_id:"fo-c", at:104.7, type:"user_message", summary:"Newer still",
  source_session:{harness:"claude", sid:"focus-1"},
  evidence:{source:"root transcript", confidence:"exact"}});
"""

WHO = {"harness": "claude", "sid": "focus-1"}


def _fact(fact_id: str, at: float, kind: str, **extra: Any) -> dict[str, Any]:
    return {"fact_id": fact_id, "at": at, "type": kind, "source_session": WHO, **extra}


SERVER_FACTS = (
    _fact("fo-b", 102, "user_message"),
    _fact("task-a", 103, "prepared_dispatch"),
    _fact("fo-a", 104, "user_message"),
    _fact(
        "c-fail",
        104.5,
        "tool_report",
        subject="check",
        result="failed",
        summary="pytest INJECTED-COMMAND",
    ),
)


def composed(**row: Any) -> dict[str, Any]:
    """What `POST /api/correction` answers for the fixture's session."""
    base: dict[str, Any] = {
        "harness": "claude",
        "sid": "focus-1",
        "annotation_goal": "Ship the retry queue",
        "annotation_line_1": LINE,
        "annotation_revision": 2,
        "annotation_window_start": 100.0,
        "annotation_settled_through": None,
        "annotation_assessment": {
            "revision_read": 2,
            "window_start": 100,
            "read_at": 106,
            "criteria": {
                "goal": {
                    "result": "not verifiable from available evidence",
                    "cites": [],
                    "why": "uncited",
                },
                "line_1": {"result": "departure", "detail": "INJECTED-PROSE", "cites": ["c-fail"]},
            },
        },
    }
    base.update(row)
    return correction.compose(base, SERVER_FACTS, floor=105.0, lines_judged=True)


def clock(at: float) -> str:
    return time.strftime("%H:%M", time.localtime(at))


def reply(answer: dict[str, Any]) -> str:
    return f'__reply["/api/correction"] = () => ({{status:200, body:{json.dumps(answer)}}});\n'


NATIVE_INSERT = """
let __nativeInput = null;
document.execCommand = (command, _show, inserted) => {
  if(command !== "insertText" || !__nativeInput) return false;
  const input = __nativeInput;
  input.value = input.value.slice(0,input.selectionStart) + inserted + input.value.slice(input.selectionEnd);
  input.selectionStart = input.selectionEnd = input.selectionStart + inserted.length;
  __fire("input", {target:input, isComposing:false, inputType:"insertText"});
  return true;
};
"""

INPUT = (
    NATIVE_INSERT
    + """
const __typeCorrection = value => {
  const held = nextCockpitCorrections.get("claude:focus-1");
  const before = typeof held.text === "string" ? held.text : held.shownText;
  const input = {value:before, defaultValue:before, selectionStart:0, selectionEnd:before.length,
    dataset:{nextCockpitCorrectionKey:"claude:focus-1"},
    closest(selector){ return selector === "[data-next-cockpit-correction-key]" ? this : null; },
    setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}};
  __nativeInput = input;
  document.activeElement = input;
  let cancelled = false;
  __fire("beforeinput", {target:input, data:value, cancelable:true, inputType:"insertText",
    preventDefault(){cancelled=true;}});
  if(!cancelled){
    input.value = value; input.selectionStart = input.selectionEnd = value.length;
    __fire("input", {target:input, inputType:"insertText"});
  }
  document.activeElement = null;
  __fire("blur", {target:input});
};
"""
)


def box_of(html: str) -> str:
    match = re.search(r"<div[^>]*data-next-steer-box[\s\S]*?</div>\s*</div>", html)
    assert match is not None, "no correction box"
    return match.group(0)


def textarea_of(html: str) -> str:
    match = re.search(
        r"<textarea[^>]*data-next-cockpit-correction-key[^>]*>([^<]*)</textarea>", html
    )
    assert match is not None, "no correction textarea"
    return (
        match.group(1)
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )


@unittest.skipUnless(shutil.which("node"), "node not available")
class WhereSteerBackIsDrawnTest(_DraftPage):
    def test_under_a_departure_it_is_the_one_primary_with_update_intent_beside_it(self) -> None:
        html = self.html(TYPED + QUIET + LINES + CHECK + DEPARTURE)
        drift = drift_of(html)
        self.assertEqual(["Steer back"], [visible_text(b).strip() for b in PRIMARY.findall(html)])
        # In the control's slot on the first screen, ahead of Analyze drift, which stays as the
        # design's "Analyze again"; the result stage below gains nothing (DRC-4695's).
        slot = re.search(r'<div class="next-cockpit-reading-ask">[\s\S]*?</div>', drift)
        assert slot is not None
        order = [
            slot.group(0).index(f'data-next-cockpit-action="{action}"')
            for action in ("steer-back", "update-intent", "reading-ask")
        ]
        self.assertEqual(sorted(order), order)
        self.assertIn(">Update intent instead</button>", drift)
        # The result stands in the button's place (DRC-4758 slice C), and Steer back follows
        # what it found, once.
        self.assertLess(drift.index("data-next-result"), drift.index("steer-back"))
        self.assertEqual(1, drift.count('data-next-cockpit-action="steer-back"'))

    def test_with_no_reader_it_is_the_one_primary_where_analyze_would_be(self) -> None:
        machines = {
            "not installed": routes(installed=(), enabled=("claude", "codex")),
            "missing, other unqualified": routes(installed=(), enabled=("claude",)),
            "unqualified, other missing": routes(installed=(), enabled=("codex",)),
            "unqualified": routes(installed=("codex", "claude"), enabled=()),
        }
        for label, routed in machines.items():
            with self.subTest(reason=label):
                html = self.html(
                    TYPED + QUIET + CHECK + f"__dashboard.reading_routes = {json.dumps(routed)};\n"
                )
                drift = drift_of(html)
                self.assertEqual(
                    ["Steer back"], [visible_text(b).strip() for b in PRIMARY.findall(html)]
                )
                slot = re.search(
                    r'<div class="next-cockpit-reading-ask next-cockpit-reading-ask--none">'
                    r"[\s\S]*?</div>",
                    drift,
                )
                assert slot is not None
                self.assertIn(routed["claude"]["note"], visible_text(slot.group(0)))
                self.assertIn('data-next-cockpit-action="steer-back"', slot.group(0))
                # Where Analyze would be, so ahead of "Turn off readings" (page F5).
                first = re.search(r"<button\b[^>]*>", slot.group(0))
                assert first is not None
                self.assertIn('data-next-cockpit-action="steer-back"', first.group(0))
                self.assertIn('data-next-cockpit-action="reading-off"', slot.group(0))
                self.assertNotIn('data-next-cockpit-action="reading-ask"', html)
                self.assertNotIn("update-intent", html)

    def test_with_a_reader_and_no_analysis_it_is_secondary_to_analyze(self) -> None:
        html = self.html(TYPED + QUIET + CHECK)
        self.assertEqual(
            ["Analyze drift"], [visible_text(b).strip() for b in PRIMARY.findall(html)]
        )
        slot = re.search(r'<div class="next-cockpit-reading-ask">[\s\S]*?</div>', drift_of(html))
        assert slot is not None
        self.assertLess(
            slot.group(0).index('data-next-cockpit-action="reading-ask"'),
            slot.group(0).index('data-next-cockpit-action="steer-back"'),
        )
        self.assertNotIn("update-intent", html)

    def test_with_nothing_to_steer_from_it_is_not_drawn(self) -> None:
        no_reader = f"__dashboard.reading_routes = {json.dumps(routes(installed=()))};\n"
        for label, setup in (
            ("reader", TYPED + QUIET),
            ("no reader", TYPED + QUIET + no_reader),
            ("a failed check before the words", TYPED + QUIET + CHECK.replace("104.5", "99.5")),
            ("no saved words", QUIET + CHECK + '__s.annotation_goal = "";\n'),
        ):
            with self.subTest(label):
                html = self.html(setup)
                self.assertNotIn("steer-back", html)
                self.assertNotIn("Steer back", html)

    def test_a_settled_later_direction_alone_is_something_to_steer_from(self) -> None:
        html = self.html(TYPED + SETTLED)
        self.assertIn('data-next-cockpit-action="steer-back"', html)
        self.assertEqual(
            ["Analyze drift"], [visible_text(b).strip() for b in PRIMARY.findall(html)]
        )

    def test_while_the_question_before_the_press_stands_it_waits(self) -> None:
        # The question owns the control's slot and Keep is its one primary (DRC-4682).
        html = self.html(TYPED)
        self.assertIn('data-next-cockpit-action="direction-keep"', html)
        self.assertNotIn("steer-back", html)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheCorrectionTest(_DraftPage):
    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE

    def opened(self, answer: dict[str, Any] | None = None, after: str = "") -> Any:
        return self.drive(
            self.SETUP + reply(answer if answer is not None else composed()) + INPUT,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + after
            + "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts,"
            " renders:__renders}));",
        )

    def test_the_press_asks_the_server_for_this_session_only(self) -> None:
        out = self.opened()
        self.assertEqual([{"url": "/api/correction", "body": WHO}], out["posts"])

    def test_the_box_shows_the_servers_correction_with_the_pages_numbers(self) -> None:
        out = self.opened()
        failed = clock(104.5)
        self.assertEqual(
            "Back to my goal: Ship the retry queue\n"
            "Where it stands against what I expect:\n"
            f"- The parser tests pass: departed at {failed} (#4 in Cargento)\n"
            f"A check failed at {failed} (#4).\n"
            "Please continue from here.",
            textarea_of(out["html"]),
        )

    def test_the_box_is_labelled_for_copying_capped_and_offers_no_send(self) -> None:
        html = self.opened()["html"]
        box = box_of(html)
        self.assertIn(">Correction to copy</label>", box)
        # Counted in characters as the server counts them, so no UTF-16 `maxlength` (F2).
        self.assertNotIn("maxlength", box)
        self.assertRegex(visible_text(box), r"\b\d+/2000\b")
        self.assertIn(HINT, visible_text(box))
        self.assertIn(">Copy</button>", box)
        self.assertNotIn("Send", visible_text(aside_of(html)))
        steer = re.search(r'<button[^>]*data-next-cockpit-action="steer-back"[^>]*>', html)
        assert steer is not None
        self.assertIn('aria-expanded="true"', steer.group(0))
        self.assertIn({"named": f"correction:{KEY}"}, self.opened()["renders"])

    def test_nothing_the_facts_carry_reaches_the_box(self) -> None:
        text = textarea_of(self.opened()["html"])
        for planted in ("INJECTED", "pytest", "c-fail", "fo-a"):
            self.assertNotIn(planted, text)

    def test_an_entry_the_list_does_not_number_keeps_its_time_and_loses_its_number(self) -> None:
        answer = {
            "ok": True,
            "parts": ["A at 1", {"entry": "gone"}, ". B at 2", {"entry": "fo-a"}, "."],
        }
        self.assertEqual(
            "A at 1. B at 2 (#3 in Cargento).", textarea_of(self.opened(answer)["html"])
        )

    def test_a_correction_too_long_is_refused_with_the_servers_sentence(self) -> None:
        html = self.opened({"ok": False, "reason": "too-long", "why": TOO_LONG})["html"]
        self.assertIn(TOO_LONG, visible_text(drift_of(html)))
        self.assertNotIn("data-next-cockpit-correction-key", html)

    def test_a_second_press_closes_the_box(self) -> None:
        html = self.opened(after='__press("steer-back");\nawait __settle();\n')["html"]
        self.assertNotIn("data-next-steer-box", html)
        self.assertIn('aria-expanded="false"', html)


COPY = """
let __copied = [];
navigator.clipboard = {writeText(value){ __copied.push(value); return Promise.resolve(); }};
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class CopyTest(_DraftPage):
    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE + reply(composed()) + INPUT

    def copied(self, clipboard: str = COPY, edit: str | None = None) -> Any:
        typed = f"__typeCorrection({json.dumps(edit)});\n" if edit is not None else ""
        return self.drive(
            self.SETUP + clipboard,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + typed
            + '__posts = [];\n__press("correction-copy");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts,"
            " copied: typeof __copied === 'undefined' ? null : __copied}));",
        )

    def test_copy_writes_the_box_and_records_that_exact_text(self) -> None:
        out = self.copied()
        text = textarea_of(out["html"])
        self.assertEqual([text], out["copied"])
        self.assertEqual(
            [{"url": "/api/correction/copied", "body": {**WHO, "text": text}}], out["posts"]
        )
        self.assertIn(">Copied</button>", box_of(out["html"]))

    def test_an_edit_is_what_is_copied_and_recorded(self) -> None:
        edited = "Back to my goal: only the parser.\nPlease continue from here."
        out = self.copied(edit=edited)
        self.assertEqual([edited], out["copied"])
        self.assertEqual(
            [{"url": "/api/correction/copied", "body": {**WHO, "text": edited}}], out["posts"]
        )
        self.assertEqual(edited, textarea_of(out["html"]))

    def test_an_edit_is_capped_at_two_thousand_characters_and_never_otherwise_cut(self) -> None:
        out = self.copied(edit="y" * 2100)
        self.assertEqual(["y" * 2000], out["copied"])

    def test_with_no_clipboard_it_says_so_and_records_nothing(self) -> None:
        out = self.copied(clipboard="")
        self.assertEqual([], out["posts"])
        self.assertIn(">Copy unavailable</button>", box_of(out["html"]))

    def test_nothing_is_sent_to_the_session(self) -> None:
        out = self.copied()
        urls = [post["url"] for post in out["posts"]]
        self.assertNotIn("/api/reading", urls)
        self.assertFalse([u for u in urls if "terminal" in u or "prototype" in u])


@unittest.skipUnless(shutil.which("node"), "node not available")
class UpdateIntentInsteadTest(_DraftPage):
    def pressed(self, setup: str, answer: str = "") -> Any:
        return self.drive(
            TYPED + LINES + setup + answer,
            '__press("update-intent", __argOf("update-intent"));\n'
            "await __settle();\nawait __settle();\n"
            "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts,"
            " opened:__opened, renders:__renders}));",
        )

    def test_it_offers_the_direction_a_departure_cites_over_the_latest(self) -> None:
        out = self.pressed(CITED + LATEST)
        self.assertEqual(["fo-a"], [post["body"]["fact_id"] for post in out["opened"]])

    def test_with_no_cited_direction_it_offers_the_latest(self) -> None:
        out = self.pressed(SETTLED + CHECK + DEPARTURE + LATEST)
        self.assertEqual(["fo-c"], [post["body"]["fact_id"] for post in out["opened"]])

    def test_a_settled_direction_stays_open_as_the_pending_line(self) -> None:
        out = self.pressed(CITED)
        html = out["html"]
        self.assertIn("data-next-cockpit-direction-line", html)
        self.assertIn("from #3 · not saved", visible_text(html))
        self.assertIn({"named": f"direction:{KEY}"}, out["renders"])
        # The goal is untouched.
        self.assertIn(">Ship the retry queue</textarea>", html)

    def test_with_no_later_direction_it_opens_an_empty_line(self) -> None:
        out = self.pressed(QUIET + CHECK + DEPARTURE)
        self.assertEqual([], out["opened"])
        lines = re.findall(r"data-next-cockpit-held-line-index=\"(\d+)\"", out["html"])
        self.assertEqual(["0", "1"], lines)
        self.assertIn({"named": f"held:{KEY}:lines:1"}, out["renders"])

    def test_at_six_lines_it_adds_no_seventh_box(self) -> None:
        six = "".join(f'__s.annotation_line_{k} = "Line {k}";\n' for k in range(1, 7))
        out = self.pressed(QUIET + CHECK + DEPARTURE + six)
        lines = re.findall(r"data-next-cockpit-held-line-index=\"(\d+)\"", out["html"])
        self.assertEqual(6, len(lines))


@unittest.skipUnless(shutil.which("node"), "node not available")
class AddedFromLabelTest(_DraftPage):
    ENTRY = (
        '__s.annotation_line_1 = "Correct the lane order";\n'
        '__s.annotation_line_1_source = "entry";\n'
        '__s.annotation_line_1_source_id = "fo-b";\n'
        '__s.annotation_lines_why = "";\n'
    )

    def label(self, setup: str) -> str:
        html = self.html(TYPED + self.ENTRY + setup)
        match = re.search(r'data-next-cockpit-held-line-source="0"[^>]*>([^<]*)<', html)
        assert match is not None
        return match.group(1)

    def test_a_numbered_entry_is_named_by_its_number(self) -> None:
        self.assertEqual("added from #1", self.label("__s.annotation_window_start = 100;\n"))

    def test_an_entry_with_no_number_is_named_by_its_time(self) -> None:
        self.assertEqual(
            f"added from your direction at {clock(102)}",
            self.label("__s.annotation_window_start = 103;\n"),
        )

    def test_a_typed_line_draws_no_source(self) -> None:
        # "typed" told the reader what they already knew, so the session page draws no source
        # for a typed line (owner, 2026-10-02, ask 3); the project page still names it.
        html = self.html(TYPED + self.ENTRY + '__s.annotation_line_1_source = "typed";\n')
        self.assertNotIn('data-next-cockpit-held-line-source="0"', html)
        self.assertIn('data-next-cockpit-held-line-count="0"', html)

    def test_at_phone_widths_the_label_wraps_and_remove_keeps_its_own_column(self) -> None:
        # "added from your direction at 14:00" sized an `auto` column to its whole width and
        # pushed remove past the page at 375 and 320 (page F2); measured live with CDP.
        phone = "".join(
            block[: block.index("\n}\n")]
            for block in NEXT_STYLES.split("@media(max-width:760px){")[1:]
        )
        # The line's own grid is gone at every width (owner, 2026-10-02, ask 3): the source
        # sits in the wrapping row under the box, so only its own wrap is left to hold.
        self.assertNotIn(".next-session-panel .next-cockpit-held-line{", phone)
        self.assertRegex(
            phone,
            r"\.next-session-panel \.next-cockpit-held-line \.next-cockpit-held-source"
            r"\{min-width:0;overflow-wrap:anywhere\}",
        )


# The record moving under an open box (injection F1, page F3). Each replaces what the fixture's
# server publishes and redraws, as a poll does.
REDRAW = (
    "__dashboard.generated = (__dashboard.generated || 0) + 1;\n"
    "nextCockpitContexts.clear();\nawait refreshNext();\nawait __settle();\nawait __settle();\n"
)
# A passing re-run superseded the failed check the departure cited: the entry leaves the record,
# so the panel demotes the departure and nothing is left to steer from.
SUPERSEDED = "__semantic.facts = __semantic.facts.filter(f => f.fact_id !== 'c-fail');\n" + REDRAW
# A new analysis of the same words, read later.
REREAD = "__s.annotation_assessment = {...__s.annotation_assessment, read_at:107};\n" + REDRAW
# The reader saved new words from elsewhere (revision 2 to 3).
RESAVED = (
    '__s.annotation_goal = "Ship the retry queue again"; __s.annotation_revision = 3;\n'
    "__s.annotation_revision_count = 3;\n" + REDRAW
)
FRESH = {"ok": True, "parts": ["Back to my goal: fresh.\nPlease continue from here."]}
STALE_NOTE = (
    "This was composed from an older record. Recompose replaces your edit with a correction from "
    "the record as it stands."
)


def correction_posts(out: dict[str, Any]) -> list[Any]:
    return [post for post in out["posts"] if post["url"] == "/api/correction"]


@unittest.skipUnless(shutil.which("node"), "node not available")
class AnOpenCorrectionFollowsTheRecordTest(_DraftPage):
    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE + reply(composed()) + INPUT + COPY

    def moved(self, change: str, *, before: str = "", after: str = "") -> Any:
        return self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + before
            + reply(FRESH).replace("\n", "")
            + "\n"
            + change
            + after
            + "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts,"
            " copied:__copied}));",
        )

    def test_a_departure_the_record_no_longer_holds_closes_an_unedited_box(self) -> None:
        out = self.moved(SUPERSEDED)
        html = out["html"]
        self.assertNotIn("data-next-cockpit-correction-key", html)
        self.assertNotIn("departed at", visible_text(html))
        self.assertNotIn("A check failed", visible_text(html))
        # Nothing is left to steer from, so no second request and no control.
        self.assertEqual(1, len(correction_posts(out)))
        self.assertNotIn("steer-back", html)

    def test_a_new_analysis_recomposes_an_unedited_box_from_the_server(self) -> None:
        out = self.moved(REREAD)
        self.assertEqual(2, len(correction_posts(out)))
        self.assertEqual(
            "Back to my goal: fresh.\nPlease continue from here.", textarea_of(out["html"])
        )

    def test_new_words_recompose_an_unedited_box(self) -> None:
        out = self.moved(RESAVED)
        self.assertEqual(2, len(correction_posts(out)))
        text = textarea_of(out["html"])
        self.assertNotIn("Ship the retry queue\n", text)
        self.assertNotIn("departed at", text)

    def test_a_copied_but_unedited_text_is_recomposed_too(self) -> None:
        out = self.moved(
            REREAD, before='__press("correction-copy");\nawait __settle();\nawait __settle();\n'
        )
        self.assertEqual(2, len(correction_posts(out)))
        self.assertEqual(
            "Back to my goal: fresh.\nPlease continue from here.", textarea_of(out["html"])
        )

    def test_copy_after_the_record_moved_copies_and_records_only_the_new_text(self) -> None:
        out = self.moved(
            RESAVED,
            after='__posts = [];\n__press("correction-copy");\nawait __settle();\nawait __settle();\n',
        )
        fresh = "Back to my goal: fresh.\nPlease continue from here."
        self.assertEqual([fresh], out["copied"])
        self.assertEqual(
            [{"url": "/api/correction/copied", "body": {**WHO, "text": fresh}}], out["posts"]
        )

    def test_an_edited_text_is_kept_and_marked_as_composed_from_an_older_record(self) -> None:
        edited = "Back to my goal: my own words.\nPlease continue from here."
        out = self.moved(RESAVED, before=f"__typeCorrection({json.dumps(edited)});\n")
        html = out["html"]
        self.assertEqual(edited, textarea_of(html))
        self.assertEqual(1, len(correction_posts(out)))
        self.assertIn(STALE_NOTE, visible_text(drift_of(html)))
        self.assertIn('data-next-cockpit-action="correction-recompose"', html)
        self.assertIn(">Recompose</button>", html)

    def test_recompose_replaces_an_edited_text_with_the_record_as_it_stands(self) -> None:
        edited = "Back to my goal: my own words.\nPlease continue from here."
        out = self.moved(
            RESAVED,
            before=f"__typeCorrection({json.dumps(edited)});\n",
            after='__press("correction-recompose");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual(2, len(correction_posts(out)))
        self.assertEqual(
            "Back to my goal: fresh.\nPlease continue from here.", textarea_of(out["html"])
        )
        self.assertNotIn(STALE_NOTE, visible_text(out["html"]))

    def test_an_edited_stale_text_still_copies_as_the_reader_wrote_it(self) -> None:
        edited = "Back to my goal: my own words.\nPlease continue from here."
        out = self.moved(
            RESAVED,
            before=f"__typeCorrection({json.dumps(edited)});\n",
            after='__posts = [];\n__press("correction-copy");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual([edited], out["copied"])
        self.assertEqual(
            [{"url": "/api/correction/copied", "body": {**WHO, "text": edited}}], out["posts"]
        )

    def test_copy_before_the_redraw_never_copies_a_text_the_record_moved_past(self) -> None:
        # The record arrived and the page has not drawn it yet: Copy itself reads it, whatever
        # the click path draws first.
        out = self.moved(
            "const __g = nextCockpitRouteGroup(); const __f = nextCockpitFocusedSession(__g);\n"
            "__f.annotation_revision = 3;\n__posts = [];\n"
            "await nextCockpitCopyCorrection(__f, {dataset:{nextCopyCorrection:'claude:focus-1'}},"
            " nextCockpitWorkSource(__g, __f));\nawait __settle();\n"
        )
        self.assertEqual([], out["copied"])
        self.assertEqual([], [p for p in out["posts"] if p["url"] == "/api/correction/copied"])

    def test_recomposed_to_nothing_it_closes_rather_than_refusing_an_unmade_press(self) -> None:
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + reply({"ok": False, "reason": "nothing"}).replace("\n", "")
            + "\n"
            + REREAD
            + "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts}));",
        )
        self.assertEqual(2, len(correction_posts(out)))
        self.assertNotIn("data-next-cockpit-correction-key", out["html"])
        self.assertNotIn(
            "Nothing recorded now gives a correction to steer back from.",
            visible_text(out["html"]),
        )
        self.assertIn('aria-expanded="false"', out["html"])

    def test_a_redraw_that_changes_nothing_keeps_the_box_and_asks_nothing(self) -> None:
        out = self.moved(REDRAW)
        self.assertEqual(1, len(correction_posts(out)))
        self.assertIn("departed at", textarea_of(out["html"]))


ROCKETS = "\U0001f680" * 1500


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheCapCountsCharactersTest(_DraftPage):
    """The server counts code points (`correction._width`), so the page does too (injection F2)."""

    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE + INPUT + COPY

    def run_box(self, typed: str | None = None) -> Any:
        edit = f"__typeCorrection({json.dumps(typed)});\n" if typed is not None else ""
        return self.drive(
            self.SETUP + reply({"ok": True, "parts": [ROCKETS]}),
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + edit
            + '__press("correction-copy");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({html:__els.app.innerHTML, copied:__copied}));",
        )

    def test_a_correction_of_astral_characters_is_shown_whole_and_uncapped_by_units(self) -> None:
        out = self.run_box()
        box = box_of(out["html"])
        self.assertEqual(ROCKETS, textarea_of(out["html"]))
        self.assertNotIn("maxlength", box)
        self.assertIn("1500/2000", visible_text(box))
        self.assertEqual([ROCKETS], out["copied"])

    def test_one_keystroke_on_it_cuts_nothing(self) -> None:
        typed = ROCKETS + "x"
        out = self.run_box(typed)
        self.assertEqual([typed], out["copied"])

    def test_past_the_cap_it_keeps_two_thousand_whole_characters(self) -> None:
        out = self.run_box("\U0001f680" * 2100)
        self.assertEqual(["\U0001f680" * 2000], out["copied"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ASavedDirectionIsNotOfferedAgainTest(_DraftPage):
    """Update intent instead never offers a direction already saved as a line (page F1)."""

    SAVED_FO_A = (
        '__s.annotation_line_2 = "Newest direction";\n'
        '__s.annotation_line_2_source = "entry";\n'
        '__s.annotation_line_2_source_id = "fo-a";\n'
    )

    def offered(self, setup: str) -> str | None:
        html = self.html(TYPED + LINES + setup)
        match = re.search(r'data-next-cockpit-action="update-intent" data-arg="([^"]*)"', html)
        assert match is not None, "no Update intent instead"
        return match.group(1)

    def test_the_cited_direction_already_saved_gives_way_to_the_latest_other(self) -> None:
        self.assertEqual("fo-c", self.offered(CITED + LATEST + self.SAVED_FO_A))

    def test_with_every_later_direction_saved_it_offers_the_empty_line(self) -> None:
        self.assertEqual("", self.offered(CITED + self.SAVED_FO_A))


@unittest.skipUnless(shutil.which("node"), "node not available")
class SteerBackPressesTest(_DraftPage):
    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE + INPUT + COPY

    def run_presses(self, first: str, then: str) -> Any:
        return self.drive(
            self.SETUP + first,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + then
            + "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts,"
            " renders:__renders, copied:__copied}));",
        )

    def test_retry_after_a_failure_is_one_press(self) -> None:
        failing = '__reply["/api/correction"] = () => ({status:500, body:{}});\n'
        out = self.run_presses(
            failing,
            reply(composed()) + '__press("steer-back");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual(2, len(correction_posts(out)))
        self.assertIn("departed at", textarea_of(out["html"]))

    def test_a_press_over_nothing_to_steer_from_asks_again(self) -> None:
        out = self.run_presses(
            reply({"ok": False, "reason": "nothing"}),
            reply(composed()) + '__press("steer-back");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual(2, len(correction_posts(out)))
        self.assertIn("departed at", textarea_of(out["html"]))

    def test_a_double_press_sends_one_request(self) -> None:
        out = self.drive(
            self.SETUP + reply(composed()),
            '__press("steer-back");\n__press("steer-back");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts}));",
        )
        self.assertEqual(1, len(correction_posts(out)))
        self.assertIn("data-next-steer-box", out["html"])

    def test_a_reply_whose_parts_are_not_text_or_entries_opens_no_box(self) -> None:
        out = self.run_presses(reply({"ok": True, "parts": ["Back", {"entry": 4}]}), "")
        self.assertNotIn("data-next-cockpit-correction-key", out["html"])
        self.assertIn(
            "Could not compose a correction. Press Steer back again to retry.",
            visible_text(out["html"]),
        )

    def test_an_edit_after_copying_resets_the_cue(self) -> None:
        out = self.run_presses(
            reply(composed()),
            '__press("correction-copy");\nawait __settle();\nawait __settle();\n'
            '__typeCorrection("Back to my goal: changed.");\nrenderNext();\n',
        )
        box = box_of(out["html"])
        self.assertIn(">Copy</button>", box)
        self.assertNotIn(">Copied</button>", box)

    def test_copy_keeps_its_focus_key_across_the_redraw(self) -> None:
        out = self.run_presses(
            reply(composed()), '__press("correction-copy");\nawait __settle();\nawait __settle();\n'
        )
        self.assertIn(f'data-next-focus="correction-copy:{KEY}"', box_of(out["html"]))
        self.assertIn({"named": f"correction-copy:{KEY}"}, out["renders"])

    def test_copy_freezes_the_text_it_copied_against_renumbering(self) -> None:
        out = self.run_presses(
            reply(composed()),
            '__press("correction-copy");\nawait __settle();\nawait __settle();\n'
            "__s.annotation_window_start = 102.5;\n" + REDRAW,
        )
        self.assertEqual(out["copied"], [textarea_of(out["html"])])
        self.assertIn("(#4 in Cargento)", textarea_of(out["html"]))

    def test_copy_is_announced_in_the_live_region(self) -> None:
        out = self.drive(
            self.SETUP + reply(composed()),
            "nextSessionCopyStatusElement = {textContent: ''};\n"
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            '__press("correction-copy");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify(nextSessionCopyStatusElement.textContent));",
        )
        self.assertEqual("Copied", out)


# The reply to a recompose, held until the test lets it go, so what the page shows while the
# request is out can be read (V5).
HOLD = """
let __holding = false, __release = null;
const __heldFetch = __fetchImpl;
__fetchImpl = async (url, init) => {
  if(__holding && String(url) === "/api/correction"){
    await new Promise(resolve => { __release = resolve; });
  }
  return __heldFetch(url, init);
};
"""
# A second failing check that supersedes nothing: the correction's "A check failed at" is about
# the latest failed check, so the box no longer says what the record does (V3).
NEWFAIL = (
    '__semantic.facts.push({fact_id:"c-fail-2", at:104.9, type:"tool_report", subject:"check",'
    ' result:"failed", summary:"pytest tests/unit", source_session:{harness:"claude",'
    ' sid:"focus-1"}, evidence:{source:"Claude Bash call and paired result",'
    ' confidence:"exact"}});\n' + REDRAW
)


@unittest.skipUnless(shutil.which("node"), "node not available")
class ABackgroundRecomposeLeavesTheReaderAloneTest(_DraftPage):
    """A recompose nobody pressed for never moves focus or hides the box (V1, V5)."""

    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE + reply(composed()) + INPUT + COPY + HOLD

    def renumbering(self, after: str = "") -> Any:
        return self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            "const __before = __els.app.innerHTML;\n" + reply(FRESH) + "__holding = true;\n"
            '__semantic.facts.push({fact_id:"earlier-entry", at:101, type:"user_message",'
            ' summary:"An earlier direction", source_session:{harness:"claude", sid:"focus-1"},'
            ' evidence:{source:"root transcript", confidence:"exact"}});\n'
            + REREAD
            + "const __during = __els.app.innerHTML;\n"
            + after
            + "const __afterPress = __els.app.innerHTML;\n"
            "__release();\nawait __settle();\nawait __settle();\nawait __settle();\n"
            "console.log(JSON.stringify({before:__before, during:__during, afterPress:__afterPress,"
            " html:__els.app.innerHTML, posts:__posts, copied:__copied}));",
        )

    def test_the_visible_old_text_stays_exact_when_the_record_renumbers_during_recompose(
        self,
    ) -> None:
        out = self.renumbering()
        self.assertIn("(#4 in Cargento)", textarea_of(out["before"]))
        self.assertEqual(textarea_of(out["before"]), textarea_of(out["during"]))
        self.assertEqual(
            "Back to my goal: fresh.\nPlease continue from here.", textarea_of(out["html"])
        )

    def test_copy_during_recompose_explains_why_the_old_text_was_not_copied(self) -> None:
        out = self.renumbering(
            "const __g = nextCockpitRouteGroup(); const __f = nextCockpitFocusedSession(__g);\n"
            "await nextCockpitCopyCorrection(__f, {dataset:{nextCopyCorrection:'claude:focus-1'}},"
            " nextCockpitWorkSource(__g, __f));\n"
        )
        self.assertEqual([], out["copied"])
        self.assertIn(">Copy unavailable</button>", box_of(out["afterPress"]))
        self.assertEqual([], [p for p in out["posts"] if p["url"] == "/api/correction/copied"])

    def test_a_composition_started_before_the_answer_keeps_the_committed_reader_text(self) -> None:
        mine = "Back to my goal: a composed direction漢字"
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + reply(FRESH)
            + "__holding = true;\n"
            + REREAD
            + "const __input = {value:'Back to my goal', selectionStart:15, selectionEnd:15,"
            " dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(selector){return selector === '[data-next-cockpit-correction-key]' ? this : null;}};\n"
            '__fire("compositionstart", {target:__input});\n'
            f"__input.value = {json.dumps(mine)};\n"
            '__fire("input", {target:__input, isComposing:true});\n'
            "__release();\nawait __settle();\nawait __settle();\n"
            '__fire("compositionend", {target:__input, data:"漢字"});\n'
            "await __settle();\n"
            "console.log(JSON.stringify({html:__els.app.innerHTML}));",
        )
        self.assertEqual(mine, textarea_of(out["html"]))
        self.assertIn(STALE_NOTE, visible_text(out["html"]))

    def test_it_names_no_focus_target_so_the_reader_stays_where_they_are(self) -> None:
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + reply(FRESH).replace("\n", "")
            + "\n__renders.length = 0;\n"
            + REREAD
            + "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts,"
            " renders:__renders}));",
        )
        self.assertEqual(2, len(correction_posts(out)))
        self.assertEqual(
            "Back to my goal: fresh.\nPlease continue from here.", textarea_of(out["html"])
        )
        self.assertNotIn({"named": f"correction:{KEY}"}, out["renders"])
        self.assertNotIn({"named": f"steer-back:{KEY}"}, out["renders"])

    def test_the_old_box_stays_drawn_while_the_request_is_out(self) -> None:
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + reply(FRESH).replace("\n", "")
            + "\n__holding = true;\n"
            + REREAD
            + "const __during = __els.app.innerHTML;\n"
            "__release();\nawait __settle();\nawait __settle();\nawait __settle();\n"
            "console.log(JSON.stringify({during:__during, html:__els.app.innerHTML,"
            " posts:__posts}));",
        )
        self.assertEqual(2, len(correction_posts(out)))
        self.assertIn("departed at", textarea_of(out["during"]))
        self.assertEqual(
            "Back to my goal: fresh.\nPlease continue from here.", textarea_of(out["html"])
        )

    def test_what_the_reader_types_while_it_is_out_is_kept_as_theirs(self) -> None:
        mine = "Back to my goal: typed while it was out."
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + reply(FRESH).replace("\n", "")
            + "\n__holding = true;\n"
            + REREAD
            + f"__typeCorrection({json.dumps(mine)});\n"
            "__release();\nawait __settle();\nawait __settle();\nawait __settle();\n"
            "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts}));",
        )
        self.assertEqual(mine, textarea_of(out["html"]))
        self.assertIn(STALE_NOTE, visible_text(drift_of(out["html"])))
        self.assertIn(">Recompose</button>", out["html"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ANewFailedCheckRecomposesTest(_DraftPage):
    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE + reply(composed()) + INPUT + COPY

    def test_a_failed_check_after_the_press_recomposes_an_unedited_box(self) -> None:
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            + reply(FRESH).replace("\n", "")
            + "\n"
            + NEWFAIL
            + "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts}));",
        )
        self.assertEqual(2, len(correction_posts(out)))
        self.assertEqual(
            "Back to my goal: fresh.\nPlease continue from here.", textarea_of(out["html"])
        )


# 314 characters, as the verifier's box was, ending in the sentence an end-cut loses first.
BASE = "Back to my goal: " + "q" * 270 + "\nPlease continue from here."
ACUTE = "é"
# An insertion into the box at a code-point offset, as a keystroke or a paste lands: the field's
# value after the edit, the caret after the inserted run, and the text the box was drawn with.
INSERT = """
const __insertCorrection = (at, text, drawn) => {
  const before = __lastCorrection === null ? drawn : __lastCorrection;
  const cps = [...before];
  const head = cps.slice(0, at).join("");
  const el = {value: before, defaultValue: drawn,
    selectionStart: head.length, selectionEnd: head.length,
    setSelectionRange(start, end){ this.selectionStart = start; this.selectionEnd = end; },
    dataset:{nextCockpitCorrectionKey:"claude:focus-1"},
    closest(selector){ return selector === "[data-next-cockpit-correction-key]" ? this : null; }};
  __nativeInput = el;
  document.activeElement = el;
  let cancelled = false;
  __fire("paste", {target:el, clipboardData:{getData(){return text;}},
    preventDefault(){cancelled=true;}});
  if(!cancelled){
    el.value = head + text + cps.slice(at).join("");
    el.selectionStart = el.selectionEnd = head.length + text.length;
    __fire("input", {target: el});
  }
  __lastCorrection = el.value;
  return {value: el.value, caret: [el.selectionStart, el.selectionEnd]};
};
let __lastCorrection = null;
"""


def units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


@unittest.skipUnless(shutil.which("node"), "node not available")
class AnEditAtTheCapCutsOnlyTheInsertionTest(_DraftPage):
    """Past the cap the inserted run is cut, never the reader's existing text (V2)."""

    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE + INPUT + INSERT + COPY

    def inserted(self, *edits: tuple[int, str]) -> Any:
        calls = "".join(
            f"__edits.push(__insertCorrection({at}, {json.dumps(text)}, {json.dumps(BASE)}));\n"
            for at, text in edits
        )
        return self.drive(
            self.SETUP + reply({"ok": True, "parts": [BASE]}),
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            "const __edits = [];\n" + calls + '__press("correction-copy");\n'
            "await __settle();\nawait __settle();\n"
            "console.log(JSON.stringify({edits:__edits, copied:__copied}));",
        )

    def test_the_verifiers_paste_keeps_the_tail_and_whole_characters(self) -> None:
        paste = "\U0001f680" * 1000 + ACUTE * 600
        out = self.inserted((50, paste))
        room = 2000 - len(BASE)
        kept = "\U0001f680" * 1000 + ACUTE * ((room - 1000) // 2)
        expected = BASE[:50] + kept + BASE[50:]
        self.assertEqual(2000, len(expected))
        self.assertEqual(expected, out["edits"][0]["value"])
        self.assertTrue(out["edits"][0]["value"].endswith("Please continue from here."))
        self.assertEqual([units(BASE[:50] + kept)] * 2, out["edits"][0]["caret"])
        self.assertEqual([expected], out["copied"])

    def test_an_odd_character_left_over_never_leaves_a_bare_base(self) -> None:
        # One code point of room past the rockets: the next "é" is two, so none of it goes in.
        base_room = 2000 - len(BASE) - 1000
        paste = "\U0001f680" * 1000 + "x" * (base_room - 3) + ACUTE * 5
        out = self.inserted((50, paste))
        value = out["edits"][0]["value"]
        self.assertEqual(
            BASE[:50] + "\U0001f680" * 1000 + "x" * (base_room - 3) + ACUTE,
            value[: 50 + 1000 + base_room - 3 + 2],
        )
        self.assertTrue(value.endswith(BASE[50:]))
        self.assertEqual(1999, len(value))

    def test_typing_at_the_cap_does_nothing_to_the_existing_text(self) -> None:
        fill = "z" * (2000 - len(BASE))
        out = self.inserted((50, fill), (20, "Z"))
        full = BASE[:50] + fill + BASE[50:]
        self.assertEqual(full, out["edits"][0]["value"])
        self.assertEqual(full, out["edits"][1]["value"])
        self.assertEqual([20, 20], out["edits"][1]["caret"])
        self.assertEqual([full], out["copied"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ACompositionCommitsWholeTest(_DraftPage):
    """An input-method commit is one edit, never a prefix fitted to the cap."""

    def composing(self, before: str, committed: str, *, remove: int = 0) -> Any:
        setup = TYPED + QUIET + LINES + CHECK + DEPARTURE + COPY
        return self.drive(
            setup + reply({"ok": True, "parts": [before]}),
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            f"const __base = {json.dumps(before)}; const __commit = {json.dumps(committed)};\n"
            f"const __start = __base.length - {remove};\n"
            "const __input = {value:__base, defaultValue:__base, selectionStart:__start,"
            " selectionEnd:__base.length, dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(selector){return selector === '[data-next-cockpit-correction-key]' ? this : null;},"
            " setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}};\n"
            '__fire("compositionstart", {target:__input});\n'
            "__input.value = __base.slice(0,__start) + __commit;\n"
            "__input.selectionStart = __input.selectionEnd = __input.value.length;\n"
            '__fire("input", {target:__input, isComposing:true, inputType:"insertCompositionText"});\n'
            "const __during = __input.value;\n"
            '__fire("compositionend", {target:__input, data:__commit});\n'
            '__fire("input", {target:__input, isComposing:false, inputType:"insertFromComposition"});\n'
            "const __after = __input.value;\n"
            "const __g = nextCockpitRouteGroup(); const __f = nextCockpitFocusedSession(__g);\n"
            "await nextCockpitCopyCorrection(__f, {dataset:{nextCopyCorrection:'claude:focus-1'}},"
            " nextCockpitWorkSource(__g, __f));\n"
            "console.log(JSON.stringify({during:__during, value:__after,"
            " caret:[__input.selectionStart,__input.selectionEnd], copied:__copied}));",
        )

    def test_provisional_composition_text_is_not_cut_before_the_commit(self) -> None:
        before = "q" * 1999
        out = self.composing(before, "漢字")
        self.assertEqual(before + "漢字", out["during"])

    def test_a_commit_that_would_cross_the_cap_keeps_none_of_the_inserted_text(self) -> None:
        before = "q" * 1999
        out = self.composing(before, "漢字")
        self.assertEqual(before, out["value"])
        self.assertEqual([before], out["copied"])
        self.assertEqual([1999, 1999], out["caret"])

    def test_a_commit_that_fits_keeps_every_character(self) -> None:
        before = "q" * 1998
        out = self.composing(before, "漢字")
        self.assertEqual(before + "漢字", out["value"])
        self.assertEqual([before + "漢字"], out["copied"])

    def test_a_commit_may_replace_selected_text_when_the_whole_value_fits(self) -> None:
        before = "q" * 1999
        out = self.composing(before, "漢字", remove=1)
        self.assertEqual("q" * 1998 + "漢字", out["value"])
        self.assertEqual(["q" * 1998 + "漢字"], out["copied"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class AClipboardPasteUsesTheNativeEditTransactionTest(_DraftPage):
    def paste(self, *, native: bool) -> Any:
        before = "q" * 1995 + "TAIL"
        setup = TYPED + QUIET + LINES + CHECK + DEPARTURE + COPY + NATIVE_INSERT
        return self.drive(
            setup + reply({"ok": True, "parts": [before]}),
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            f"const __before = {json.dumps(before)};\n"
            "const __input = {value:__before, defaultValue:__before, selectionStart:1999, selectionEnd:1999,"
            " dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(selector){return selector === '[data-next-cockpit-correction-key]' ? this : null;}};\n"
            "__nativeInput = __input; document.activeElement = __input; let __cancelled = false;\n"
            + ("document.execCommand = () => false;\n" if not native else "")
            + '__fire("paste", {target:__input, clipboardData:{getData(){return "ABCDE";}},'
            " preventDefault(){__cancelled=true;}});\n"
            "document.activeElement = null; __fire('blur', {target:__input});\n"
            "renderNext();\n"
            "console.log(JSON.stringify({cancelled:__cancelled, value:__input.value, html:__els.app.innerHTML}));",
        )

    def test_an_over_cap_paste_uses_the_clipboard_text_without_cutting_existing_text(self) -> None:
        out = self.paste(native=True)
        self.assertTrue(out["cancelled"])
        self.assertEqual("q" * 1995 + "TAILA", out["value"])
        self.assertEqual(out["value"], textarea_of(out["html"]))

    def test_an_unavailable_native_insert_refuses_the_paste_and_keeps_the_baseline(self) -> None:
        out = self.paste(native=False)
        self.assertTrue(out["cancelled"])
        self.assertEqual("q" * 1995 + "TAIL", out["value"])
        self.assertIn("Your text is kept", visible_text(out["html"]))

    def test_a_mismatched_native_restore_keeps_the_baseline_in_the_editor_and_copy(self) -> None:
        before = "q" * 1995 + "TAIL"
        out = self.drive(
            TYPED
            + QUIET
            + LINES
            + CHECK
            + DEPARTURE
            + COPY
            + reply({"ok": True, "parts": [before]}),
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            f"const __before = {json.dumps(before)};\n"
            "const __input = {value:__before, selectionStart:1999, selectionEnd:1999,"
            " dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(s){return s === '[data-next-cockpit-correction-key]' ? this : null;}};\n"
            "document.activeElement = __input;\n"
            "document.execCommand = command => {\n"
            " __input.value = command === 'undo' ? 'A different authored draft' : 'A mismatched insert';\n"
            " __fire('input', {target:__input, inputType:command === 'undo' ? 'historyUndo' : 'insertText'});\n"
            " return true;};\n"
            "__fire('paste', {target:__input, clipboardData:{getData(){return 'ABCDE';}},"
            " preventDefault(){}});\n"
            "document.activeElement = null; __fire('blur', {target:__input});\n"
            "const __g = nextCockpitRouteGroup(); const __f = nextCockpitFocusedSession(__g);\n"
            "await nextCockpitCopyCorrection(__f, {dataset:{nextCopyCorrection:'claude:focus-1'}},"
            " nextCockpitWorkSource(__g, __f));\n"
            "console.log(JSON.stringify({value:__input.value,copied:__copied}));",
        )
        self.assertEqual(before, out["value"])
        self.assertEqual([before], out["copied"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ALineBreakIsANativeCorrectionEditTest(_DraftPage):
    def newline(self, before: str, kind: str, *, remove: int = 0) -> Any:
        return self.drive(
            TYPED + QUIET + LINES + CHECK + DEPARTURE + reply({"ok": True, "parts": [before]}),
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            f"const __before = {json.dumps(before)}; const __kind = {json.dumps(kind)};\n"
            f"const __start = __before.length - {remove};\n"
            "const __input = {value:__before, defaultValue:__before, selectionStart:__start,"
            " selectionEnd:__before.length, dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(s){return s === '[data-next-cockpit-correction-key]' ? this : null;}};\n"
            "let __prevented = false;\n"
            "__fire('beforeinput', {target:__input,inputType:__kind,data:null,dataTransfer:null,"
            " cancelable:true,preventDefault(){__prevented=true;}});\n"
            "if(!__prevented){__input.value = __before.slice(0,__start) + '\\n';"
            " __fire('input', {target:__input,inputType:__kind});}\n"
            "console.log(JSON.stringify({prevented:__prevented,value:__input.value,"
            " held:nextCockpitCorrections.get('claude:focus-1').text}));",
        )

    def test_return_with_null_data_inserts_a_newline_below_the_cap(self) -> None:
        for kind in ("insertLineBreak", "insertParagraph"):
            with self.subTest(kind=kind):
                out = self.newline("line one", kind)
                self.assertFalse(out["prevented"])
                self.assertEqual("line one\n", out["value"])
                self.assertEqual(out["value"], out["held"])

    def test_return_at_the_cap_keeps_all_pre_existing_text(self) -> None:
        before = "q" * 1996 + "TAIL"
        for kind in ("insertLineBreak", "insertParagraph"):
            with self.subTest(kind=kind):
                out = self.newline(before, kind)
                self.assertTrue(out["prevented"])
                self.assertEqual(before, out["value"])

    def test_return_can_replace_a_selection_when_the_whole_value_fits(self) -> None:
        before = "q" * 1996 + "TAIL"
        for kind in ("insertLineBreak", "insertParagraph"):
            with self.subTest(kind=kind):
                out = self.newline(before, kind, remove=1)
                self.assertFalse(out["prevented"])
                self.assertEqual(before[:-1] + "\n", out["value"])
                self.assertEqual(out["value"], out["held"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ARefreshKeepsTheNativeCorrectionEditorTest(_DraftPage):
    SETUP = TYPED + QUIET + LINES + CHECK + DEPARTURE + reply(composed())

    def test_a_focused_authored_editor_never_moves_or_repaints_even_with_atomic_move(self) -> None:
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            "const __held = nextCockpitCorrections.get('claude:focus-1');\n"
            "__held.text = 'A correction I edited'; __held.edited = true;\n"
            "renderNext();\n"
            "let __moves = 0; let __paints = 0; let __html = __els.app.innerHTML;\n"
            "const __cue = {textContent:'',hidden:true};\n"
            "const __input = {value:__held.text, dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(selector){return selector === '[data-next-cockpit-correction-key]' ? this"
            " : selector === '[data-next-steer-box]' ? {querySelector(s){"
            " return s === '[data-next-correction-paint-why]' ? __cue : null;}} : null;},remove(){}};\n"
            "document.activeElement = __input; document.body = {moveBefore(){__moves++;}};\n"
            "__els.app.querySelector = s => s === '[data-next-cockpit-correction-key]' ? __input : null;\n"
            "Object.defineProperty(__els.app, 'innerHTML', {get(){return __html;},"
            " set(value){__paints++; __html=value;}});\n"
            "nextData.sessions[0].title = 'A title received while editing'; renderNext();\n"
            "console.log(JSON.stringify({moves:__moves,paints:__paints,why:__cue.textContent}));",
        )
        self.assertEqual(0, out["moves"], "moving even a connected editor clears native Undo")
        self.assertEqual(0, out["paints"])
        self.assertIn("Updates are paused", out["why"])

    def test_an_edited_correction_pauses_paint_until_the_reader_leaves(self) -> None:
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            "const __held = nextCockpitCorrections.get('claude:focus-1');\n"
            "__held.text = 'A correction I edited'; __held.edited = true; renderNext();\n"
            "const __before = __els.app.innerHTML; const __cue = {textContent:'',hidden:true};\n"
            "const __input = {value:__held.text, dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(selector){return selector === '[data-next-cockpit-correction-key]' ? this"
            " : selector === '[data-next-steer-box]' ? {querySelector(s){"
            " return s === '[data-next-correction-paint-why]' ? __cue : null;}} : null;}};\n"
            "document.activeElement = __input;\n"
            "nextData.sessions[0].title = 'A title received while editing'; renderNext();\n"
            "const __during = __els.app.innerHTML; const __why = __cue.textContent;\n"
            "document.activeElement = null;\n"
            '__fire("blur", {target:__input});\nawait __settle();\n'
            "console.log(JSON.stringify({before:__before,during:__during,why:__why,html:__els.app.innerHTML}));",
        )
        self.assertEqual(out["before"], out["during"])
        self.assertIn("Updates are paused", out["why"])
        self.assertIn("A title received while editing", out["html"])
        self.assertEqual("A correction I edited", textarea_of(out["html"]))

    def pointer_action(self, action: str) -> Any:
        return self.drive(
            self.SETUP + COPY,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            "const __held = nextCockpitCorrections.get('claude:focus-1');\n"
            "__held.text = 'A correction I edited'; __held.edited = true; renderNext();\n"
            "const __input = {value:__held.text,dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(s){return s === '[data-next-cockpit-correction-key]' ? this : null;}};\n"
            "const __button = {connected:true,dataset:{},closest(s){"
            " return s === '[data-next-cockpit-correction-key]' ? null : this;}};\n"
            "let __html = __els.app.innerHTML;\n"
            "Object.defineProperty(__els.app, 'innerHTML', {get(){return __html;},"
            " set(value){__button.connected=false; __html=value;}});\n"
            "document.activeElement = __input;\n"
            "nextData.sessions[0].title = 'A title received while editing'; renderNext();\n"
            "__fire('pointerdown', {target:__button,pointerId:1,button:0,isPrimary:true});\n"
            "document.activeElement = __button; __fire('blur', {target:__input,relatedTarget:__button});\n"
            "await __settle();\nawait __settle();\n"
            "const __whileHeld = __button.connected;\n"
            "renderNext(); await __settle();\n"
            "const __duringRefresh = __button.connected;\n"
            "__fire('pointerup', {target:__button,pointerId:1,button:0,isPrimary:true});\n"
            "await __settle();\n"
            "const __beforeClick = __button.connected;\n"
            f"if(__button.connected) __press({json.dumps(action)});\n"
            "await new Promise(resolve => setTimeout(resolve,0));\nawait __settle();\nawait __settle();\n"
            "console.log(JSON.stringify({held:__whileHeld,duringRefresh:__duringRefresh,"
            " beforeClick:__beforeClick,copied:__copied,posts:__posts,html:__els.app.innerHTML}));",
        )

    def test_a_held_pointer_copy_runs_once_before_the_paused_paint(self) -> None:
        out = self.pointer_action("correction-copy")
        self.assertTrue(out["held"])
        self.assertTrue(out["duringRefresh"])
        self.assertTrue(out["beforeClick"])
        self.assertEqual(["A correction I edited"], out["copied"])
        self.assertEqual(1, len([p for p in out["posts"] if p["url"] == "/api/correction/copied"]))
        self.assertIn("A title received while editing", out["html"])

    def test_a_held_pointer_recompose_runs_once_before_the_paused_paint(self) -> None:
        out = self.pointer_action("correction-recompose")
        self.assertTrue(out["held"])
        self.assertTrue(out["beforeClick"])
        self.assertEqual(2, len(correction_posts(out)))
        self.assertNotEqual("A correction I edited", textarea_of(out["html"]))
        self.assertIn("A title received while editing", out["html"])

    def test_tab_cancellation_and_release_away_flush_without_waiting_for_a_click(self) -> None:
        for finish in (
            "__fire('keydown', {key:'Tab'});",
            "__fire('pointercancel', {pointerId:1});",
            "__fire('pointerup', {target:__outside,pointerId:1});",
        ):
            with self.subTest(finish=finish):
                out = self.drive(
                    self.SETUP,
                    '__press("steer-back");\nawait __settle();\nawait __settle();\n'
                    "const __held = nextCockpitCorrections.get('claude:focus-1');\n"
                    "__held.text = 'A correction I edited'; __held.edited=true; renderNext();\n"
                    "const __input = {dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
                    " closest(s){return s === '[data-next-cockpit-correction-key]' ? this : null;}};\n"
                    "const __outside = {dataset:{},closest(){return null;}};\n"
                    "document.activeElement = __input;\n"
                    "nextData.sessions[0].title = 'New work after leaving'; renderNext();\n"
                    "__fire('pointerdown', {target:{},pointerId:1,button:0,isPrimary:true});\n"
                    "document.activeElement = __outside; __fire('blur', {target:__input});\n"
                    + finish
                    + "\nawait __settle();\nconsole.log(JSON.stringify({html:__els.app.innerHTML}));",
                )
                self.assertIn("New work after leaving", out["html"])
                self.assertEqual("A correction I edited", textarea_of(out["html"]))

    def test_explicit_navigation_leaves_the_old_session_pointer_pause(self) -> None:
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            "const __held = nextCockpitCorrections.get('claude:focus-1');\n"
            "__held.text='A correction I edited'; __held.edited=true; renderNext();\n"
            "const __input = {dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(s){return s === '[data-next-cockpit-correction-key]' ? this : null;}};\n"
            "document.activeElement=__input; renderNext();\n"
            "__fire('pointerdown', {target:{},pointerId:1,button:0,isPrimary:true});\n"
            "document.activeElement=null; __fire('blur', {target:__input});\n"
            "navigateNext({view:'sessions'}); await __settle();\n"
            "console.log(JSON.stringify({route:nextRoute.view,html:__els.app.innerHTML,draft:__held.text}));",
        )
        self.assertEqual("sessions", out["route"])
        self.assertNotIn('data-next-cockpit-correction-key="claude:focus-1"', out["html"])
        self.assertEqual("A correction I edited", out["draft"])

    def test_a_render_waits_until_a_native_composition_finishes(self) -> None:
        out = self.drive(
            self.SETUP,
            '__press("steer-back");\nawait __settle();\nawait __settle();\n'
            "const __before = __els.app.innerHTML;\n"
            "const __input = {value:'A correction', selectionStart:12, selectionEnd:12,"
            " dataset:{nextCockpitCorrectionKey:'claude:focus-1'},"
            " closest(selector){return selector === '[data-next-cockpit-correction-key]' ? this : null;}};\n"
            '__fire("compositionstart", {target:__input});\n'
            "__s.title = 'A title received during composition';\n"
            "nextData.sessions[0].title = __s.title; renderNext();\n"
            "const __during = __els.app.innerHTML;\n"
            "__input.value = 'A correction漢字';\n"
            '__fire("input", {target:__input, isComposing:true});\n'
            '__fire("compositionend", {target:__input, data:"漢字"});\n'
            '__fire("input", {target:__input, isComposing:false});\n'
            "await __settle();\n"
            "console.log(JSON.stringify({before:__before,during:__during,html:__els.app.innerHTML}));",
        )
        self.assertEqual(out["before"], out["during"])
        self.assertIn("A correction漢字", textarea_of(out["html"]))


@unittest.skipUnless(shutil.which("node"), "node not available")
class OnlyClaudeCodeIsOfferedSteerBackTest(_DraftPage):
    def test_a_codex_session_with_a_departure_and_a_failed_check_has_no_steer_back(self) -> None:
        codex = (
            '__s.harness = "codex";\n'
            "for(const f of __semantic.facts){ if(f.source_session)"
            ' f.source_session = {harness:"codex", sid:"focus-1"}; }\n'
        )
        html = self.html(
            TYPED + QUIET + LINES + CHECK + DEPARTURE + codex,
            ROUTE.replace("claude", "codex") + "\nawait __settle();\nawait __settle();\n"
            "console.log(JSON.stringify(__els.app.innerHTML));",
        )
        self.assertIn('id="next-session-drift-heading"', html)
        self.assertIn("Ship the retry queue", html)
        self.assertNotIn("steer-back", html)
        self.assertNotIn("update-intent", html)


if __name__ == "__main__":
    unittest.main()
