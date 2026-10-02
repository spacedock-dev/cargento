"""The intent editor's boxes, buttons, spacing and footer (DRC-4758 D1, owner Q4, Q5, Q6, Q11).

The owner's walk found the goal box two rows tall and every outcome line one, neither resizable,
"clear", "save", "add a line" and "remove" drawn as bare text, and no way to tell which box a
save belonged to. The rulings of 2026-10-01: the goal rests at three rows and each line at two,
both resize vertically, and a dragged height survives a redraw (Q4); every field control is a real
button, secondary or quiet and never primary (Q5); each field is a label, a box and a counter,
Clear sits under the goal box, and one footer under both fields holds the hint, Undo changes and
Save intent (Q6); an empty field's absence sentence stays in the DOM as the save's description,
visually hidden (Q11); and the stamp over saved words reads "Saved", not "Confirmed".

Every assertion is on the assembled bundle's rendered markup, its stylesheet, or what it sends.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from pathlib import Path

from .test_next_intent_draft import (
    FIRST,
    GOAL_KEY,
    LINES_KEY,
    MEASURED,
    ONE_LINE,
    OPEN_ADD,
    OPENED,
    REPORT,
    TYPED,
    _DraftPage,
    intent_of,
    pending_line,
)
from .visible_text import visible_text

STYLES = Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"

TWO_LINES = """
__s.annotation_line_1 = "The parser tests pass";
__s.annotation_line_1_source = "typed";
__s.annotation_line_2 = "A reload opens in the saved mode";
__s.annotation_line_2_source = "typed";
__s.annotation_lines_why = "";
"""

# A session with nothing typed and no prompt to draft from, so both fields are empty and both
# absence sentences are drawn.
NOTHING = """
__s.first_prompt = ""; __s.first_prompt_at = null;
__s.instruction = null;
"""

TYPE_LINE = """
const __typeLine = (index, value) => __fire("input", {target:{value,
  dataset:{nextCockpitHeldLinesKey:"held:claude:focus-1:lines", nextCockpitHeldLineIndex:String(index)},
  closest(selector){ return selector === "[data-next-cockpit-held-lines-key]" ? this : null; }}});
"""


def css() -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", STYLES.read_text(encoding="utf-8"))


def rules() -> list[tuple[str, str]]:
    """Every (selector, body) in the sheet, media blocks included."""
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css())]


def rule(selector: str) -> str:
    for sel, body in rules():
        if sel == selector:
            return body
    msg = f"{selector} not in styles.css"
    raise AssertionError(msg)


def button(html: str, action: str, arg: str | None = None) -> str:
    pattern = rf'<button[^>]*data-next-cockpit-action="{action}"'
    if arg is not None:
        pattern += rf' data-arg="{re.escape(arg)}"'
    found = re.search(pattern + r"[^>]*>[\s\S]*?</button>", html)
    assert found is not None, f"no {action} button"
    return found.group(0)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheBoxesAreRoomyAndResizableTest(_DraftPage):
    def test_the_goal_rests_at_three_rows_and_each_line_at_two(self) -> None:
        intent = intent_of(self.html(TYPED + TWO_LINES))
        goal = re.search(r'<textarea[^>]*data-next-cockpit-held-kind="goal"[^>]*>', intent)
        assert goal is not None
        self.assertIn('rows="3"', goal.group(0))
        lines = re.findall(r"<textarea[^>]*data-next-cockpit-held-line-index[^>]*>", intent)
        self.assertEqual(2, len(lines))
        for line in lines:
            self.assertIn('rows="2"', line)

    def test_a_drafted_goal_rests_at_three_rows_too(self) -> None:
        # The drafted box sizes to its text, which would cancel `rows="3"` and draw a short
        # prompt one line tall, so its floor is three rows; where `field-sizing` is missing it
        # rests at three rows as well (owner Q4; DRC-4758 fix round).
        three = "calc(var(--fs-body)*1.55*3 + 16px)"
        drafted = ".next-session-panel .next-cockpit-held-field[data-next-cockpit-drafted]>textarea"
        bodies = [body for selector, body in rules() if selector == drafted]
        self.assertEqual(2, len(bodies), bodies)
        sized, fallback = bodies
        self.assertIn("field-sizing:content", sized)
        self.assertIn(f"min-height:{three}", sized)
        self.assertNotIn("min-height:0", sized)
        self.assertIn(f"height:{three}", fallback)

    def test_both_boxes_resize_vertically_and_no_rule_fights_a_drag(self) -> None:
        self.assertIn("resize:vertical", rule(".next-cockpit-held-field textarea"))
        for selector, body in rules():
            if "next-cockpit-held" not in selector:
                continue
            with self.subTest(selector=selector):
                self.assertNotIn("resize:none", body)
                # A height rule tied to focus puts the box back over the reader's drag on the
                # next blur, which is what the one-clean-row pair did.
                if ":focus" in selector and "textarea" in selector:
                    self.assertNotIn("height", body)
                self.assertNotIn("textarea:not(:focus)", selector)

    def test_a_dragged_height_survives_a_redraw(self) -> None:
        out = self.drive(
            TYPED + TWO_LINES,
            """
let __boxes = [];
__els.app = {
  get innerHTML(){ return this.html || ""; },
  set innerHTML(html){
    this.html = html;
    __boxes = [...html.matchAll(/<textarea\\b([^>]*)>/g)].map(match => ({
      dataset:{nextFocus:(match[1].match(/data-next-focus="([^"]*)"/) || [])[1]},
      selectionStart:0, selectionEnd:0, scrollTop:0, scrollLeft:0,
      style:{height:"", width:""}, setSelectionRange(){},
    }));
  },
  querySelectorAll(selector){
    return selector === "[data-next-focus]" ? __boxes.filter(box => box.dataset.nextFocus) : [];
  },
};
renderNext();
const box = key => __boxes.find(item => item.dataset.nextFocus === key);
const before = box(__GOAL__);
before.style.height = "180px";
box(__LINE__).style.height = "96px";
renderNext();
console.log(JSON.stringify({replaced: box(__GOAL__) !== before,
  goal: box(__GOAL__).style.height, line: box(__LINE__).style.height}));
""".replace("__GOAL__", json.dumps(GOAL_KEY)).replace("__LINE__", json.dumps(f"{LINES_KEY}:1")),
        )
        assert isinstance(out, dict)
        self.assertTrue(
            out["replaced"], "the redraw must build new boxes for this to test anything"
        )
        self.assertEqual("180px", out["goal"])
        self.assertEqual("96px", out["line"])


ENTRY_LINE = """
__s.annotation_line_2_source = "entry";
__s.annotation_line_2_source_id = "";
"""


def lines_of(html: str) -> list[str]:
    return re.findall(
        r'<li class="next-cockpit-held-line" data-next-cockpit-held-line="\d+">[\s\S]*?</li>',
        intent_of(html),
    )


@unittest.skipUnless(shutil.which("node"), "node not available")
class EachOutcomeLineFollowsTheGoalsPatternTest(_DraftPage):
    """Owner ask 3 (2026-10-02): "the character length and buttons should all be on the bottom
    and follow the same pattern as the buttons above for the Goal form control (character length
    on left, buttons aligned right)". Each line had its count, source and a bare multiplication sign to the right
    of its box."""

    def test_under_each_outcome_box_the_reader_finds_its_count_on_the_left_and_remove_on_the_right(
        self,
    ) -> None:
        rows = lines_of(self.html(TYPED + TWO_LINES))
        self.assertEqual(2, len(rows))
        for n, row in enumerate(rows, start=1):
            with self.subTest(line=n):
                inside = row[row.index(">") + 1 : -len("</li>")]
                # The box first, then one row under it and nothing else.
                self.assertTrue(inside.startswith("<textarea"), inside[:40])
                after = inside[inside.index("</textarea>") + len("</textarea>") :]
                self.assertTrue(after.startswith('<div class="next-cockpit-held-under">'), after)
                self.assertTrue(after.endswith("</div>"), after[-40:])
                self.assertEqual(1, after.count("<div"))
                under = after
                count = under.index("data-next-cockpit-held-line-count")
                remove = under.index('data-next-cockpit-action="held-line-remove"')
                self.assertLess(count, remove)
                button = re.search(r"<button[^>]*>([^<]*)</button>", under)
                assert button is not None
                self.assertEqual("Remove", button.group(1))
                self.assertIn(f'aria-label="Remove line {n}"', button.group(0))
        # The Goal's own row, which the lines now copy: count, then Clear.
        sheet = css()
        self.assertIn(".next-cockpit-held-line{display:grid;gap:4px}", sheet)
        self.assertIn(
            ".next-cockpit-held-line>.next-cockpit-held-under>:last-child{margin-inline-start:auto}",
            sheet,
        )
        self.assertIn(
            ".next-cockpit-held-lines>.next-cockpit-held-under{justify-content:flex-end}", sheet
        )

    def test_a_line_the_reader_typed_says_nothing_about_being_typed(self) -> None:
        rows = lines_of(self.html(TYPED + TWO_LINES + ENTRY_LINE))
        # What sits around the box, which is where a source would be; the box holds the words.
        typed, entry = (visible_text(row[row.index("</textarea>") :]) for row in rows)
        self.assertEqual("21/240 Remove", typed)
        self.assertNotIn("typed", typed)
        self.assertIn("added from", entry)
        self.assertTrue(entry.startswith("32/240 added from"), entry)
        self.assertTrue(entry.endswith("Remove"), entry)

    def test_the_direction_lines_buttons_read_save_and_remove(self) -> None:
        out = self.drive(TYPED + ONE_LINE + OPENED, OPEN_ADD + REPORT)
        assert isinstance(out, dict)
        line = pending_line(out["html"])
        self.assertTrue(line.split(">", 1)[1].startswith("<textarea"), line[:120])
        after = line[line.index("</textarea>") :]
        self.assertTrue(after.startswith('</textarea><div class="next-cockpit-held-under">'))
        under = after[: after.index("</div>") + len("</div>")]
        # The direction Save holds its busy label as a hidden ghost (verifier R3), which is
        # not a label a reader sees or hears.
        bare = re.sub(r'<span class="next-action-ghost"[^>]*>[\s\S]*?</span></span>', "", under)
        labels = [
            visible_text(label).strip()
            for label in re.findall(r"<button[^>]*>([\s\S]*?)</button>", bare)
        ]
        self.assertEqual(["Save", "Remove"], labels)
        text = visible_text(under)
        self.assertTrue(text.startswith("16/240 from #"), text)
        self.assertIn("not saved", text)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheControlsAreButtonsInOneFooterTest(_DraftPage):
    def test_every_field_control_is_a_real_button_and_none_is_primary(self) -> None:
        """Outlined, not quiet: the quiet tier is a bottom rule at the foot of a 44px box, which
        the owner's walk read as a stray line under Clear and Remove rather than as a button."""
        intent = intent_of(self.html(TYPED + TWO_LINES))
        save = button(intent, "held-save")
        self.assertRegex(save, r'class="next-action next-action--secondary[" ]')
        self.assertIn(">Save intent</button>", save)
        undo = button(intent, "held-undo")
        self.assertRegex(undo, r'class="next-action next-action--secondary[" ]')
        self.assertIn(">Undo changes</button>", undo)
        clear = button(intent, "held-clear", "goal")
        self.assertRegex(clear, r'class="next-action next-action--secondary[" ]')
        self.assertIn(">Clear</button>", clear)
        add = button(intent, "held-line-add")
        self.assertRegex(add, r'class="next-action next-action--secondary[" ]')
        self.assertIn(">+ Add a line</button>", add)
        removes = re.findall(
            r'<button[^>]*data-next-cockpit-action="held-line-remove"[^>]*>[^<]*</button>', intent
        )
        self.assertEqual(2, len(removes))
        for n, remove in enumerate(removes, start=1):
            self.assertIn(f'aria-label="Remove line {n}"', remove)
            self.assertIn(">Remove</button>", remove)
            self.assertIn("next-action--secondary", remove)
        self.assertNotIn("next-action--primary", intent)
        # One save and one undo for both fields, never one per field.
        self.assertEqual(1, intent.count('data-next-cockpit-action="held-save"'))
        self.assertEqual(1, intent.count('data-next-cockpit-action="held-undo"'))
        for bare in (">save<", ">clear<", ">add a line<", ">remove<"):
            self.assertNotIn(bare, intent)

    def test_the_fields_own_button_rule_leaves_the_primitive_alone(self) -> None:
        """`.next-cockpit-held-field button` strips borders and background at (0,1,1), above the
        primitive's (0,1,0): left unscoped it draws every new button as bare text again."""
        for selector, body in rules():
            for part in selector.split(","):
                if part.strip().endswith(".next-cockpit-held-field button") and "border:0" in body:
                    self.fail(f"{selector} strips the button primitive")

    def test_the_order_is_field_box_counter_then_one_footer_under_both(self) -> None:
        intent = intent_of(self.html(TYPED + TWO_LINES))
        marks = (
            ">Goal<",
            'data-next-cockpit-held-kind="goal"',
            'data-next-cockpit-held-count="goal"',
            'data-next-cockpit-action="held-clear"',
            ">Expected outcome<",
            'class="next-cockpit-held-list"',
            'data-next-cockpit-action="held-line-add"',
            'class="next-cockpit-held-footer"',
            MEASURED,
            'data-next-cockpit-action="held-undo"',
            'data-next-cockpit-action="held-save"',
        )
        at = [intent.index(mark) for mark in marks]
        self.assertEqual(sorted(at), at, list(zip(marks, at, strict=True)))
        # The footer follows both fields rather than sitting inside either.
        footer = intent.index('class="next-cockpit-held-footer"')
        fields = re.search(r'<div class="next-cockpit-held-fields">', intent)
        assert fields is not None
        self.assertLess(fields.start(), footer)
        self.assertEqual(1, visible_text(intent).count(MEASURED))

    def test_the_two_field_groups_stand_20_to_24px_apart(self) -> None:
        gap = re.search(
            r"(?:row-)?gap:(\d+)px", rule(".next-session-panel .next-cockpit-held-fields")
        )
        assert gap is not None
        self.assertGreaterEqual(int(gap.group(1)), 20)
        self.assertLessEqual(int(gap.group(1)), 24)

    def test_save_intent_and_undo_are_inert_until_something_changed(self) -> None:
        intent = intent_of(self.html(TYPED + TWO_LINES))
        self.assertIn('aria-disabled="true"', button(intent, "held-save"))
        self.assertIn('aria-disabled="true"', button(intent, "held-undo"))
        typed = intent_of(
            self.html(
                TYPED + TWO_LINES,
                f'nextCockpitHeldDrafts.set({json.dumps(GOAL_KEY)}, "x");\n'
                "renderNext();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            )
        )
        self.assertNotIn("aria-disabled", button(typed, "held-save"))
        self.assertNotIn("aria-disabled", button(typed, "held-undo"))

    def test_save_intent_writes_the_goal_and_the_lines_in_one_request(self) -> None:
        out = self.drive(
            TYPED + TWO_LINES + TYPE_LINE,
            '__typeGoal("Ship the retry queue today");\n'
            '__typeLine(1, "A reload opens where it was");\n'
            '__press("held-save", "intent");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify(__posts));",
        )
        assert isinstance(out, list)
        self.assertEqual(1, len(out), out)
        self.assertEqual(
            {
                "harness": "claude",
                "sid": "focus-1",
                "goal": "Ship the retry queue today",
                "lines": ["The parser tests pass", "A reload opens where it was"],
                "origins": [0, 1],
                "expected_revision": 2,
            },
            out[0]["body"],
        )

    def test_save_intent_leaves_an_unchanged_field_alone(self) -> None:
        out = self.drive(
            TYPED + TWO_LINES + TYPE_LINE,
            # The fixture's store takes the goal, so the second press sees it saved.
            '__reply["/api/annotate"] = body => {\n'
            "  if(body.goal != null) __s.annotation_goal = body.goal;\n"
            "  __s.annotation_revision += 1;\n"
            '  return {status:200, body:{ok:true, outcome:"stored", persisted:true}};\n'
            "};\n"
            '__typeGoal("Ship the retry queue today");\n'
            '__press("held-save", "intent");\nawait __settle();\nawait __settle();\n'
            '__typeLine(0, "The parser tests pass on CI");\n'
            '__press("held-save", "intent");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts.map(post => post.body)));",
        )
        assert isinstance(out, list)
        self.assertEqual(2, len(out), out)
        self.assertNotIn("lines", out[0])
        self.assertEqual("Ship the retry queue today", out[0]["goal"])
        self.assertIsNone(out[1]["goal"])
        self.assertEqual(
            ["The parser tests pass on CI", "A reload opens in the saved mode"], out[1]["lines"]
        )

    def test_undo_changes_puts_both_fields_back_and_sends_nothing(self) -> None:
        out = self.drive(
            TYPED + TWO_LINES + TYPE_LINE,
            '__typeGoal("Something else");\n'
            '__typeLine(0, "Another line");\n'
            '__press("held-undo");\nawait __settle();\n'
            "console.log(JSON.stringify({posts: __posts, html: __els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        self.assertEqual([], out["posts"])
        intent = intent_of(out["html"])
        self.assertIn(">Ship the retry queue</textarea>", intent)
        self.assertIn(">The parser tests pass</textarea>", intent)
        self.assertNotIn("Something else", intent)
        self.assertNotIn("Another line", intent)

    def test_every_new_control_keeps_its_own_focus_key(self) -> None:
        intent = intent_of(self.html(TYPED + TWO_LINES))
        for control, key in (
            (button(intent, "held-save"), "held:claude:focus-1:intent:save"),
            (button(intent, "held-undo"), "held:claude:focus-1:intent:undo"),
            (button(intent, "held-clear", "goal"), f"{GOAL_KEY}:clear"),
            (button(intent, "held-line-add"), f"{LINES_KEY}:add"),
            (button(intent, "held-line-remove", "1"), f"{LINES_KEY}:remove:1"),
        ):
            with self.subTest(key=key):
                self.assertIn(f'data-next-focus="{key}"', control)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheAbsenceIsTheEmptyBoxTest(_DraftPage):
    def test_an_empty_fields_sentence_is_visually_hidden_and_still_describes_the_save(
        self,
    ) -> None:
        intent = intent_of(self.html(NOTHING))
        text = visible_text(intent)
        for sentence, kind in (
            ("No goal typed for this session.", "goal"),
            ("No expected outcome typed.", "lines"),
        ):
            with self.subTest(kind=kind):
                self.assertNotIn(sentence, text)
                node = re.search(
                    r'<p class="([^"]*)" id="(next-cockpit-held-absent-'
                    + kind
                    + r')"[^>]*>'
                    + re.escape(sentence),
                    intent,
                )
                assert node is not None, f"{sentence} left the DOM"
                self.assertIn("next-visually-hidden", node.group(1).split())
                self.assertIn(node.group(2), button(intent, "held-save"))
        # The placeholders are the visible absence.
        self.assertIn('placeholder="what you are after, in one line"', intent)

    def test_the_store_unreadable_sentence_stays_in_view(self) -> None:
        unreadable = "Cargento could not read cargento-annotations.json."
        intent = intent_of(
            self.html(NOTHING + f"__dashboard.annotate_unreadable = {json.dumps(unreadable)};\n")
        )
        self.assertIn(unreadable, visible_text(intent))


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheStampSaysSavedTest(_DraftPage):
    def test_saved_words_wear_saved_not_confirmed(self) -> None:
        intent = intent_of(self.html(TYPED))
        self.assertNotIn("Confirmed", intent)
        head = intent[: intent.index('class="next-cockpit-held-fields"')]
        self.assertIn("Saved", visible_text(head))
        # The revision line, what a revision is and the store key sit in its details
        # (DRC-4758 fix round): none of the three is in view until it is opened.
        self.assertRegex(
            head, r"<details[^>]*next-cockpit-held-stamp[^>]*><summary>Saved</summary>"
        )
        for hidden in ("revision 2 of 2", "Each save is a revision.", "claude:focus-1"):
            self.assertIn(hidden, head)
            self.assertNotIn(hidden, visible_text(head))

    def test_no_stamp_over_a_draft(self) -> None:
        intent = intent_of(self.html())
        self.assertIn(FIRST, intent)
        head = intent[: intent.index('class="next-cockpit-held-fields"')]
        self.assertNotIn("Saved", visible_text(head))
        for gone in ("No revision saved yet", "Each save is a revision.", "claude:focus-1"):
            self.assertNotIn(gone, visible_text(head))


if __name__ == "__main__":
    unittest.main()
