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
    "__s.copied_prompts = [{fact_id:'fo-a', at:104}];\n"
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
                    "__s.copied_prompts = [{fact_id:'fo-a', at:104}];\n", ""
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
