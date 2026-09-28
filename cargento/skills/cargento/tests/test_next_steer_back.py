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


INPUT = """
const __typeCorrection = value => __fire("input", {target:{value,
  dataset:{nextCockpitCorrectionKey:"claude:focus-1"},
  closest(selector){ return selector === "[data-next-cockpit-correction-key]" ? this : null; }}});
"""


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
        reading = drift[drift.index("<h2>READING</h2>") :]
        self.assertNotIn("steer-back", reading[: reading.index("</section>")])
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

    def test_a_typed_line_is_still_typed(self) -> None:
        self.assertEqual("typed", self.label('__s.annotation_line_1_source = "typed";\n'))

    def test_at_phone_widths_the_label_wraps_and_remove_keeps_its_own_column(self) -> None:
        # "added from your direction at 14:00" sized an `auto` column to its whole width and
        # pushed remove past the page at 375 and 320 (page F2); measured live with CDP.
        phone = "".join(
            block[: block.index("\n}\n")]
            for block in NEXT_STYLES.split("@media(max-width:760px){")[1:]
        )
        self.assertIn(
            ".next-session-panel .next-cockpit-held-line"
            "{grid-template-columns:auto minmax(0,1fr) auto}",
            phone,
        )
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
