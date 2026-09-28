"""A copied correction coming back reads as Cargento's words on the page (DRC-4678).

The page half of item 9 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy):
a message the server marked `copied` is labelled "You · Copied from Cargento" in the activity
list, is not a later direction, is not drafted as the goal, and is Cargento's in rule 7, one rule
in the three places, as the server keeps it. The correction here is longer than the 112
characters a published summary holds, so the page sees only its clipped summary and the mark.
"""

from __future__ import annotations

import re
import shutil
import unittest
from typing import Any

from .test_next_intent_draft import TYPED, _DraftPage, drift_of, intent_of, visible_text

CORRECTION = (
    "Steer back to your intent: ship the placeholder parser and nothing else. "
    "Line 1 is not shown yet: the parser tests at #3 failed."
)
SUMMARY = CORRECTION[:111] + "…"
# The server's marks for fo-a, the newest of the fixture's two user messages (at 104), which is
# also the latest prompt the row publishes.
COPIED = (
    "const __fa = __semantic.facts.find(f => f.fact_id === 'fo-a');\n"
    f"__fa.summary = {SUMMARY!r};\n"
    "__fa.copied = true;\n"
    "__s.copied_prompts = [{fact_id:'fo-a', at:104, quoted_as:['instruction']}];\n"
    f"__s.instruction = {{label:'asked', text:{CORRECTION[:80]!r}, at:104}};\n"
)


def _head(html: str, fact_id: str) -> str:
    row = re.search(
        rf'data-next-entry-id="{fact_id}">[\s\S]*?<div class="next-cockpit-work-head">([\s\S]*?)</div>',
        html,
    )
    assert row is not None, f"no activity row for {fact_id}"
    return visible_text(row.group(1)).strip()


@unittest.skipUnless(shutil.which("node"), "node not available")
class CopiedCorrectionPageTest(_DraftPage):
    def test_the_fixture_is_long_enough_to_be_clipped(self) -> None:
        self.assertGreater(len(CORRECTION), 112)

    def test_the_activity_list_labels_it_copied_from_cargento_and_yours_as_a_prompt(self) -> None:
        html = self.html(TYPED + COPIED)
        self.assertEqual("You Copied from Cargento", _head(html, "fo-a"))
        self.assertEqual("You Prompt", _head(html, "fo-b"))

    def test_a_copied_correction_raises_no_later_direction(self) -> None:
        plain = self.html(TYPED)
        self.assertIn("Keep my intent", plain)
        html = self.html(TYPED + COPIED)
        self.assertNotIn("Keep my intent", html)
        self.assertNotIn('data-next-entry-flag="later"', html)
        self.assertIn('data-next-cockpit-action="reading-ask"', html)

    def test_a_different_message_is_still_the_readers_own_direction(self) -> None:
        html = self.html(COPIED)
        drift = visible_text(drift_of(html))
        self.assertIn(
            'You gave a later direction at #1: "Correct the lane order".',
            drift,
        )
        self.assertNotIn("2 later directions", drift)

    def test_a_copied_correction_is_never_drafted_as_the_goal(self) -> None:
        latest_only = '__s.first_prompt = ""; __s.first_prompt_at = null;\n'
        drafted = intent_of(
            self.html(
                latest_only
                + COPIED.replace("__fa.copied = true;\n", "").replace(
                    "__s.copied_prompts = [{fact_id:'fo-a', at:104, quoted_as:['instruction']}];\n",
                    "",
                )
            )
        )
        self.assertIn("data-next-cockpit-drafted", drafted)
        html = intent_of(self.html(latest_only + COPIED))
        self.assertNotIn("data-next-cockpit-drafted", html)
        self.assertNotIn("from your prompt", visible_text(html))

    def test_rule_7_counts_it_as_cargentos(self) -> None:
        out = self.drive(
            TYPED + COPIED,
            "const all = nextCockpitWorkEntries(__s, __semantic);\n"
            "const byId = id => all.find(e => e.id === id);\n"
            "console.log(JSON.stringify({copied: nextReadingAuthor(byId('fo-a')),"
            " own: nextReadingAuthor(byId('fo-b')),"
            " person: nextReadingPersonAuthored(byId('fo-a')),"
            " mix: nextCockpitWorkMix(all)}));",
        )
        assert isinstance(out, dict)
        self.assertEqual("derived", out["copied"])
        self.assertEqual("person", out["own"])
        self.assertIs(False, out["person"])
        self.assertIn("1 direction you gave", out["mix"])
        self.assertIn("1 copied from Cargento", out["mix"])


# The server placed the row's instruction on a message the reader typed in the same second as
# the paste: the copied entry is quoted by nothing.
TYPED_SAME_SECOND = "__s.copied_prompts = [{fact_id:'fo-a', at:104, quoted_as:[]}];\n"
# Newest first, fo-a is the direction every surface below would otherwise present.
PROMOTED = (
    "for(const f of __semantic.facts){ if(f.type === 'user_message') f.intent_promoted = true; }\n"
)


@unittest.skipUnless(shutil.which("node"), "node not available")
class CopiedCorrectionEverySurfaceTest(_DraftPage):
    """A recognised copy is never presented as the reader's words, on any surface (DRC-4678
    review, matching F2), and a message typed in the same second as it stays theirs (Codex 1)."""

    def ask(self, setup: str, expression: str) -> Any:
        return self.drive(setup, f"console.log(JSON.stringify({expression}));")

    def test_a_prompt_typed_in_the_same_second_as_a_paste_is_still_drafted(self) -> None:
        latest_only = '__s.first_prompt = ""; __s.first_prompt_at = null;\n'
        candidate = self.ask(latest_only + COPIED + TYPED_SAME_SECOND, "nextPromptCandidate(__s)")
        self.assertEqual(CORRECTION[:80], candidate["text"])
        self.assertIsNone(self.ask(latest_only + COPIED, "nextPromptCandidate(__s)"))

    def test_the_stated_goal_is_never_the_copied_correction(self) -> None:
        expression = "nextObservedGoal(__s)"
        typed = self.ask(COPIED + TYPED_SAME_SECOND, expression)
        self.assertEqual(CORRECTION[:80], typed["text"])
        goal = self.ask(COPIED, expression)
        self.assertFalse(goal and CORRECTION[:40] in str(goal.get("text")))

    def test_the_assignment_is_never_the_copied_correction(self) -> None:
        expression = (
            "(nextCockpitSubstantiveDirection({label:'cargento', sessions:[__s]}, __semantic)"
            " || {}).fact_id"
        )
        plain = COPIED.replace("__fa.copied = true;\n", "")
        self.assertEqual("fo-a", self.ask(PROMOTED + plain, expression))
        self.assertNotEqual("fo-a", self.ask(PROMOTED + COPIED, expression))

    def test_no_exact_direction_row_is_the_copied_correction(self) -> None:
        expression = "nextCockpitCourseDirections(__semantic, []).map(f => f.fact_id)"
        plain = COPIED.replace("__fa.copied = true;\n", "")
        self.assertIn("fo-a", self.ask(PROMOTED + plain, expression))
        self.assertNotIn("fo-a", self.ask(PROMOTED + COPIED, expression))

    def test_the_board_rows_assignment_is_never_the_copied_correction(self) -> None:
        expression = "nextOperationsAssignment(__s)"
        self.assertIn("ASSIGNMENT", self.ask(COPIED + TYPED_SAME_SECOND, expression))
        self.assertEqual("", self.ask(COPIED, expression))

    def test_the_session_page_never_says_you_asked_the_copied_correction(self) -> None:
        asked = 'data-next-instruction="asked"'
        self.assertIn(asked, self.html(COPIED + TYPED_SAME_SECOND))
        html = self.html(COPIED)
        self.assertNotIn(asked, html)

    def test_no_course_episode_names_the_copied_correction_as_its_direction(self) -> None:
        semantic = (
            "const __course = copied => ({work_items:[{work_item_id:'w1', label:'Parser'}],"
            " facts:[{fact_id:'d1', type:'user_message', at:1, work_item_id:'w1',"
            " summary:'Steer back', copied},"
            " {fact_id:'r1', type:'gate_decision', decision:'approved', at:2, work_item_id:'w1'}],"
            " projections:{operator_intents:[{projection_id:'i1', derived_from:'d1'}],"
            " steering_episodes:[{adaptation_fact:'r1', intent_id:'i1'}]}});\n"
        )
        expression = (
            "[false, true].map(copied => nextCockpitCourseEpisodes(__course(copied), [])"
            ".map(e => e.directionFact && e.directionFact.fact_id))"
        )
        plain, copied = self.drive(semantic, f"console.log(JSON.stringify({expression}));")
        self.assertIn("d1", plain)
        self.assertNotIn("d1", copied)

    def test_a_copied_first_prompt_is_never_drafted(self) -> None:
        quoted = "__s.copied_prompts = [{fact_id:'fo-first', at:99, quoted_as:QUOTED}];\n"
        expression = "nextPromptCandidate(__s, 'first-prompt')"
        typed = self.ask(quoted.replace("QUOTED", "[]"), expression)
        self.assertEqual("Build the retry queue for failed events", typed["text"])
        self.assertIsNone(self.ask(quoted.replace("QUOTED", "['first_prompt']"), expression))

    def test_no_instruction_line_quotes_the_copied_correction(self) -> None:
        expression = "nextInstructionLine(__s, '', 'next-activity-instruction', 'span')"
        self.assertIn(
            'data-next-instruction="asked"', self.ask(COPIED + TYPED_SAME_SECOND, expression)
        )
        self.assertEqual("", self.ask(COPIED, expression))
