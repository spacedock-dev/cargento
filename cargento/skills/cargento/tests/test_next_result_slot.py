"""The result stands in the button's place, under the level and its labelled meter (DRC-4758 C).

The owner's walk never saw a drift level: the stored reading rendered in a READING section below
the fold, under a second "Analyze drift" that looked like nothing had happened. Under a stored
reading for the saved revision the Drift card now reads, top to bottom: the level over the
four-segment meter with its labels, the ruled analysis line (the only place its time is said), the
range the reading covered, why the level is what it is, the headline, the checklist against the
expected outcome, where the work went, Steer back and one "Analyze again". With a saved intent and
no level at all it says "Not checked yet" over the unlit meter (owner Q2), and never once a reading
is stored. Every assertion reads the assembled bundle's rendered markup.
"""

from __future__ import annotations

import re
import shutil
import unittest

from cargento_runtime import levels

from .test_next_analysis_result import (
    ALL_CONSISTENT,
    MIXED,
    NO_FAILURE,
    NUMBER,
    READ_AT,
    SOURCE_LINE,
    _ResultPage,
    assessment,
    clock,
)
from .test_next_drift_panel import JOB
from .test_next_intent_draft import drift_of
from .visible_text import visible_text

SCALE = ("None or low", "Medium", "High", "Extreme")


def level_of(html: str) -> str:
    """The level word alone, which the scale labels beside it must not be mistaken for."""
    found = re.search(r'<span class="next-session-drift-level">([^<]*)</span>', html)
    return found.group(1) if found else ""


def in_order(test: unittest.TestCase, text: str, *needles: str) -> None:
    at = 0
    for needle in needles:
        found = text.find(needle, at)
        test.assertNotEqual(-1, found, f"{needle!r} not found after offset {at} in {text!r}")
        at = found + len(needle)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheResultTakesTheButtonsPlaceTest(_ResultPage):
    def test_a_departure_reads_in_the_ruled_order_with_one_analyze_again(self) -> None:
        html = self.page(MIXED, levels.HIGH)
        drift = visible_text(drift_of(html))
        in_order(
            self,
            drift,
            # The source sits beside the level word, as the design's title row draws it.
            "High",
            "Analysis",
            *SCALE,
            SOURCE_LINE.format(time=clock(READ_AT)),
            "#1 to #8",
            "Departs from your intent",
            "Against expected outcome",
            f"Departs; evidence #{NUMBER['c-fail']}",
            "Where the work went",
            "Steer back",
            "Analyze again",
        )
        self.assertEqual("High", level_of(html))
        self.assertNotIn(">Analyze drift</button>", html)
        self.assertEqual(1, len(re.findall(r">Analyze again</button>", html)))
        self.assertNotIn("<h2>READING</h2>", html)
        for word in ("Done", "✓", "✔"):
            self.assertNotIn(word, drift)

    def test_the_time_is_said_once(self) -> None:
        drift = visible_text(drift_of(self.page(MIXED, levels.HIGH)))
        self.assertEqual(1, drift.count(clock(READ_AT)), drift)
        self.assertNotIn("Analysis ·", drift)

    def test_a_reading_of_one_entry_names_it_alone(self) -> None:
        one = assessment(MIXED["criteria"], window_start=104.85, evidence_through=104.95)
        drift = visible_text(drift_of(self.page(one, levels.HIGH)))
        self.assertIn(f"#{NUMBER['c-fail']}", drift)
        self.assertNotRegex(drift, r"#\d+ to #\d+")

    def test_each_outcome_line_is_one_item_of_a_list_with_the_goal_above_it(self) -> None:
        html = drift_of(self.page(MIXED, levels.HIGH))
        heading = html.index("Against expected outcome")
        listed = re.search(r'<ol class="next-cockpit-result-lines">([\s\S]*?)</ol>', html)
        assert listed is not None
        self.assertGreater(listed.start(), heading)
        items = re.findall(r'<li class="next-cockpit-reading-row"[^>]*>', listed.group(1))
        self.assertEqual(2, len(items))
        states = [re.search(r'data-next-result-state="([^"]+)"', i).group(1) for i in items]  # type: ignore[union-attr]
        self.assertEqual(["departs", "consistent"], states)
        # The goal row stands above the heading, on its own.
        goal = html.index("data-next-result-goal")
        self.assertLess(goal, heading)
        # Each line's own words are its title, and the source tag is one click away.
        text = visible_text(listed.group(1))
        self.assertIn("The parser tests pass", text)
        self.assertNotIn("EXPECTED OUTCOME · LINE 1", text)
        self.assertIn("EXPECTED OUTCOME · LINE 1", listed.group(1))

    def test_a_job_takes_the_slot_and_hides_the_old_result(self) -> None:
        html = drift_of(self.page(MIXED, levels.HIGH, extra=JOB))
        self.assertIn("next-cockpit-reading-job", html)
        self.assertNotIn(">Analyze again</button>", html)
        self.assertNotIn("Against expected outcome", html)

    def test_a_press_the_board_cannot_serve_leaves_analyze_again_inert_with_its_line(self) -> None:
        cannot = (
            "__s.reading_eligibility = {ok:false, reason:'idle-unknown', until:null,"
            " sentence:'Idle with no stop.'};\n"
        )
        html = drift_of(self.page(MIXED, levels.HIGH, extra=cannot))
        button = re.search(r"<button[^>]*>Analyze again</button>", html)
        assert button is not None
        self.assertIn('aria-disabled="true"', button.group(0))
        self.assertNotIn("next-action--primary", button.group(0))
        self.assertIn(
            "Last turn isn't recorded as finished. Run another turn to open Analyze.",
            visible_text(html),
        )

    def test_analyze_again_is_never_the_stages_primary(self) -> None:
        html = drift_of(self.page(ALL_CONSISTENT, levels.NONE_OR_LOW, facts=NO_FAILURE))
        button = re.search(r"<button[^>]*>Analyze again</button>", html)
        assert button is not None
        self.assertNotIn("next-action--primary", button.group(0))

    def test_the_finished_announcement_points_at_the_drift_level(self) -> None:
        said = self.page(None, after="console.log(JSON.stringify(NEXT_READING_FINISHED));")
        self.assertEqual("The analysis finished. Its result is in the Drift section.", said)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheLabelledMeterTest(_ResultPage):
    def test_the_meter_carries_its_four_labels_and_marks_the_current_one(self) -> None:
        html = drift_of(self.page(MIXED, levels.HIGH))
        scale = re.search(r'<p class="next-session-drift-scale"[^>]*>([\s\S]*?)</p>', html)
        assert scale is not None
        labels = re.findall(r"<span([^>]*)>([^<]*)</span>", scale.group(1))
        self.assertEqual(list(SCALE), [text for _attrs, text in labels])
        self.assertEqual(["High"], [text for attrs, text in labels if "data-current" in attrs])

    def test_not_checked_yet_over_the_unlit_meter_with_a_saved_intent(self) -> None:
        html = self.page(None)
        drift = drift_of(html)
        self.assertEqual("Not checked yet", level_of(drift))
        in_order(self, visible_text(drift), "Not checked yet", *SCALE, "Analyze drift")
        self.assertNotIn("data-on", drift)
        self.assertNotIn("data-current", drift)
        self.assertNotIn("data-next-drift-pill", html)
        self.assertNotIn("no drift", visible_text(drift).lower())

    def test_never_once_a_reading_is_stored(self) -> None:
        # A reading of words since replaced has no level for these words, and still is stored.
        stale = assessment(MIXED["criteria"], revision_read=1)
        drift = drift_of(self.page(stale, levels.HIGH))
        self.assertNotIn("Not checked yet", drift)

    def test_never_over_an_unsaved_draft(self) -> None:
        unsaved = (
            "__s.annotation_goal = ''; __s.annotation_revision = 0;"
            " __s.annotation_revision_count = 0;\n"
            "__s.annotation_line_1 = ''; __s.annotation_line_2 = '';\n"
        )
        self.assertNotIn("Not checked yet", drift_of(self.page(None, extra=unsaved)))


# What the page says for each reason `levels` can publish. Every token belongs to exactly one map.
_MAPS = (
    "console.log(JSON.stringify({lines:Object.keys(NEXT_DRIFT_REASON_LINES),"
    " blockers:Object.keys(NEXT_DRIFT_BLOCKER_LINES), silent:[...NEXT_DRIFT_REASON_SILENT]}));"
)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheLevelSaysWhyTest(_ResultPage):
    def test_every_reason_token_has_exactly_one_home(self) -> None:
        maps = self.page(None, after=_MAPS)
        assert isinstance(maps, dict)
        homes = [*maps["lines"], *maps["blockers"], *maps["silent"]]
        self.assertEqual(sorted(levels.REASONS), sorted(homes))
        self.assertEqual(len(homes), len(set(homes)))

    def test_a_high_level_says_its_first_reason_numbered_from_its_cites(self) -> None:
        html = self.page(
            MIXED, levels.HIGH, reasons=["failed-check", "departure"], cites=["c-fail"]
        )
        reason = re.search(r'<p class="next-session-drift-reason">([^<]*)</p>', html)
        assert reason is not None
        self.assertEqual(
            f"pytest tests/lexer failed 0s ago at #{NUMBER['c-fail']}; no passing re-run recorded.",
            reason.group(1),
        )
        self.assertEqual(1, len(re.findall('next-session-drift-reason"', html)))

    def test_not_enough_puts_what_holds_it_back_one_click_away(self) -> None:
        html = drift_of(
            self.page(
                ALL_CONSISTENT,
                levels.NOT_ENOUGH,
                facts=NO_FAILURE,
                reasons=["scan-incomplete", "later-direction"],
            )
        )
        text = visible_text(html)
        self.assertIn("Why not None or low", text)
        self.assertNotIn('next-session-drift-reason"', html)
        why = re.search(
            r"<details[^>]*>\s*<summary>Why not None or low</summary>([\s\S]*?)</details>", html
        )
        assert why is not None
        self.assertIn("unsettled", why.group(1))
        self.assertNotIn("drift", why.group(1).lower())

    def test_an_unknown_token_renders_nothing(self) -> None:
        html = drift_of(self.page(MIXED, levels.HIGH, reasons=["no-such-token"], cites=[]))
        self.assertNotIn("no-such-token", html)
        self.assertNotIn('next-session-drift-reason"', html)
        # And it is passed over, not taken as the first reason: the next known one reads.
        html = drift_of(
            self.page(
                MIXED, levels.HIGH, reasons=["no-such-token", "failed-check"], cites=["c-fail"]
            )
        )
        reason = re.search(r'<p class="next-session-drift-reason">([^<]*)</p>', html)
        assert reason is not None
        self.assertEqual(
            f"pytest tests/lexer failed 0s ago at #{NUMBER['c-fail']}; no passing re-run recorded.",
            reason.group(1),
        )


if __name__ == "__main__":
    unittest.main()
