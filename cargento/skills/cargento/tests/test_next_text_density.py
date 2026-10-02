"""The Intent and drift panel holds to a visible word budget (DRC-4758 slice E).

The owner's walk: "so much text it is unclear where to look". The plan's critic gave that a
number, measured with the shared visibility helper: an idle-drafted aside (a Claude Code session,
consent given, the goal drafted from the first prompt) shows no more than about 90 words outside
the field values, and an aside under a stored reading no more than about 160. Every sentence
moved to meet it stays in the DOM behind a worded `<details>`
([NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)), so each test below also
asserts the moved text is still on the page.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest

from cargento_runtime import annotations as annotation_store
from cargento_runtime import levels

from .next_harness import storage_prelude
from .test_next_analysis_result import (
    ALL_CANT_TELL,
    ALL_CONSISTENT,
    FACTS,
    MIXED,
    NO_FAILURE,
    _ResultPage,
)
from .test_next_drift_panel import FIXTURE, READING, PanelPage, aside_of
from .test_next_intent_draft import DRAFT
from .visible_text import visible_text

ELIGIBLE = (
    "__dashboard.sessions[0].reading_eligibility = "
    '{"ok":true,"reason":null,"until":null,"sentence":null};\n'
)
# The design's C1: the first prompt drafted as the goal and no later direction since.
NO_LATER = (
    "__semantic.facts = __semantic.facts.filter("
    "f => !(f.fact_id === 'fo-a' || f.fact_id === 'fo-b'));\n"
)
IDLE_DRAFTED = DRAFT + NO_LATER + ELIGIBLE
STORED = '__dashboard.reading = {consent:true, reason:"", used:1, limit:12};\n' + READING + ELIGIBLE
LANE = """
__dashboard.unasked = true;
__dashboard.sessions[0].departure_checked = true;
__dashboard.sessions[0].departures = [{
  constraint: "TYPED GOAL", clause: "do not change the board while capturing",
  reading: "Two turns edited the running board.", revision: 2,
  at: __dashboard.generated - 600, cutoff: __dashboard.generated - 600,
  cutoff_text: "Read 4 of the 4 entries after your words.",
  evidence: "turn transcript"}];
"""
# The plan's figures are about 90 and about 160. The idle one is held at 80 since the stamp went
# behind "Saved" (DRC-4758 fix round), so a sentence creeping back into view is caught before it
# reaches the plan's ceiling.
IDLE_BUDGET = 80
STORED_BUDGET = 160

# What the popover says under the server's list, which already says what a reading is (ui4 V2).
SCOPE = "What it reads is the evidence on this page"
LATER_NONE = (
    "Nothing you have said since you saved these words is in the observed record read for "
    "this session."
)
STEER = "Nothing here decides whether it changes what you are asking for."
LEDE = "Choose a goal or use your prompt, then analyze drift"
NOBODY_WATCHES = "Nothing watches for a departure on its own."


def outside_fields(html: str) -> str:
    """The markup without the boxes' own words, which are the reader's rather than the page's."""
    return re.sub(r"<textarea\b[^>]*>[\s\S]*?</textarea>", " ", html)


def words(html: str) -> int:
    return len(visible_text(outside_fields(html)).split())


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheAsideHoldsToItsWordBudgetTest(PanelPage):
    def test_an_idle_drafted_aside_shows_no_more_than_about_ninety_words(self) -> None:
        aside = aside_of(self.page("claude", IDLE_DRAFTED))
        count = words(aside)
        print(f"\nidle-drafted aside: {count} visible words outside field values")
        self.assertLessEqual(count, IDLE_BUDGET, visible_text(outside_fields(aside)))

    def test_a_stored_reading_aside_shows_no_more_than_about_one_hundred_sixty(self) -> None:
        aside = aside_of(self.page("claude", STORED))
        count = words(aside)
        print(f"\nstored-reading aside: {count} visible words outside field values")
        self.assertLessEqual(count, STORED_BUDGET, visible_text(outside_fields(aside)))


@unittest.skipUnless(shutil.which("node"), "node not available")
class ALeveledReadingHoldsToTheStoredBudgetTest(_ResultPage):
    """The C4 layout a reader sees under a stored reading: a level over the meter, the ruled
    headline, the checklist and where the work went. STORED above draws none of those, so the
    budget is measured here as well (DRC-4758 fix round)."""

    def test_each_leveled_state_shows_no_more_than_about_one_hundred_sixty(self) -> None:
        for name, value, level, facts in (
            ("mixed, high", MIXED, levels.HIGH, FACTS),
            ("all consistent, none or low", ALL_CONSISTENT, levels.NONE_OR_LOW, NO_FAILURE),
            ("all can't tell", ALL_CANT_TELL, None, FACTS),
        ):
            with self.subTest(state=name):
                html = self.page(value, level, facts=facts)
                assert isinstance(html, str)
                aside = aside_of(html)
                count = words(aside)
                print(f"\nstored reading, {name}: {count} visible words outside field values")
                self.assertLessEqual(count, STORED_BUDGET, visible_text(outside_fields(aside)))

    def test_what_the_budget_moved_is_still_on_the_page(self) -> None:
        html = self.page(ALL_CONSISTENT, levels.NONE_OR_LOW, facts=NO_FAILURE)
        assert isinstance(html, str)
        aside = aside_of(html)
        text = visible_text(aside)
        for moved in (
            # Each line's qualifier, in full in its Evidence; the source stays named in view.
            "as the tool reported; not inspected",
            "said at #2; not a check",
            # The unlisted count, behind its number.
            "1 more written file is counted and not listed.",
            # What it read, behind its worded summary (one sentence since NU-13).
            "Revision 2 (time not recorded).",
        ):
            with self.subTest(moved=moved):
                self.assertIn(moved, aside)
                self.assertNotIn(moved, text)
        self.assertIn("Consistent with what the session said at #2", text)
        self.assertRegex(text, r"Consistent with #\d+ ")
        self.assertIn("1 more", text)
        self.assertIn("What it read", text)
        # The tool qualifier stays in view once, in the activity record's footer.
        self.assertIn("Results are as the tool reported; not inspected.", visible_text(html))


@unittest.skipUnless(shutil.which("node"), "node not available")
class MovedTextStaysOnThePageTest(PanelPage):
    def test_what_a_reading_is_moves_into_what_is_sent_and_no_reading_heading_is_drawn(
        self,
    ) -> None:
        aside = aside_of(self.page("claude", IDLE_DRAFTED))
        self.assertIn(SCOPE, aside)
        self.assertNotIn(SCOPE, visible_text(aside))
        self.assertNotIn("READING", visible_text(aside))
        sent = aside[aside.index("next-cockpit-reading-sent") :]
        self.assertIn(SCOPE, sent[: sent.index("</details>")])

    def test_the_popover_says_what_a_reading_is_once_and_not_twice_in_a_row(self) -> None:
        """Verifier ui4 V2: the list ends "A reading is a model's account of the evidence, never
        a verification ...", and the paragraph under it opened "A reading is a model's account
        of the evidence on this page ...". The paragraph now says only what a reading reads."""
        aside = aside_of(self.page("claude", IDLE_DRAFTED))
        sent = aside[aside.index("next-cockpit-reading-sent") :]
        body = sent[: sent.index("</details>")]
        self.assertEqual(1, body.count("account of the evidence"), body)
        self.assertIn("never a verification", body)
        self.assertIn("It does not read a diff, a file, a test or a deliverable.", body)

    def test_a_refused_reading_is_still_said_in_view(self) -> None:
        aside = aside_of(
            self.page(
                "claude",
                IDLE_DRAFTED + "__dashboard.sessions[0].annotation_reading_refused = true;\n",
            )
        )
        self.assertIn("this build could not read it", visible_text(aside))

    def test_a_later_direction_is_a_summary_naming_its_state(self) -> None:
        aside = aside_of(self.page("claude", STORED))
        text = visible_text(aside)
        self.assertIn("Later directions: none", text)
        self.assertNotIn("none since your save", text)
        self.assertNotIn("A LATER DIRECTION", text)
        for sentence in (LATER_NONE, STEER):
            with self.subTest(sentence=sentence[:30]):
                self.assertIn(sentence, aside)
                self.assertNotIn(sentence, text)

    def test_a_settled_direction_says_when_in_its_summary(self) -> None:
        aside = aside_of(
            self.page(
                "claude",
                STORED
                + "__dashboard.sessions[0].annotation_settled_at = __dashboard.generated - 300;\n",
            )
        )
        self.assertRegex(visible_text(aside), r"Later directions: settled( \d+[smhd] ago)?(?= |$)")

    def test_what_analysis_does_is_behind_a_summary_under_a_saved_intent(self) -> None:
        aside = aside_of(self.page("claude", ELIGIBLE))
        self.assertIn(LEDE, aside)
        self.assertNotIn(LEDE, visible_text(aside))
        self.assertIn("What analysis does", visible_text(aside))
        # Under a stored reading the step it explains is done, so it is not drawn (NU-10).
        self.assertNotIn(LEDE, aside_of(self.page("claude", STORED)))

    def test_discard_everything_is_a_summary_with_the_button_inside(self) -> None:
        aside = aside_of(
            self.page(
                "claude",
                STORED
                + "__dashboard.annotate_discard = "
                + json.dumps(annotation_store.DISCARD_SENTENCES)
                + ";\n",
            )
        )
        text = visible_text(aside)
        # The control inside reads the summary's own words (NU-20), and is behind it.
        self.assertEqual(1, text.count("Discard everything"))
        self.assertIn('data-next-cockpit-action="held-discard"', aside)
        why = annotation_store.DISCARD_SENTENCES["why"]
        self.assertIn(why, aside)
        self.assertNotIn(why, text)

    def test_an_armed_discard_is_drawn_open_with_its_warning_inside(self) -> None:
        aside = aside_of(
            self.page(
                "claude",
                STORED
                + "__dashboard.annotate_discard = "
                + json.dumps(annotation_store.DISCARD_SENTENCES)
                + ";\n",
                after="nextCockpitHeldStates.set(nextCockpitHeldKey(__dashboard.sessions[0], "
                '"discard"), {kind:"discard-armed", at:Date.now()});\nrenderNext();\n',
            )
        )
        offer = re.search(r"<details[^>]*next-cockpit-held-discard-offer[^>]*>", aside)
        assert offer is not None
        # Open, and outside the restore lane, so no redraw can shut the warning that describes
        # the armed control.
        self.assertIn(" open", offer.group(0))
        self.assertNotIn("data-next-cockpit-disclosure", offer.group(0))
        self.assertIn(annotation_store.DISCARD_ARMED, visible_text(aside))
        self.assertIn('aria-describedby="next-cockpit-discard-armed"', aside)

    def test_no_departures_section_without_a_raise_from_the_lane(self) -> None:
        aside = aside_of(self.page("claude", STORED + "__dashboard.unasked = true;\n"))
        self.assertNotIn("next-cockpit-departures", aside)
        self.assertNotIn(NOBODY_WATCHES, aside)
        self.assertNotIn("DEPARTURES RAISED TO YOU", aside)

    def test_with_the_lane_on_and_nothing_raised_its_absence_stays_in_view(self) -> None:
        why = "Cargento has not checked this session against what you asked for."
        aside = aside_of(
            self.page(
                "claude",
                STORED
                + "__dashboard.unasked = true;\n"
                + f"__dashboard.sessions[0].departure_why = {json.dumps(why)};\n",
            )
        )
        text = visible_text(aside)
        self.assertIn(why, text)
        self.assertIn("About these checks", text)
        self.assertNotIn("Raised while you were away", text)

    def test_raises_from_the_lane_collapse_under_their_count(self) -> None:
        aside = aside_of(self.page("claude", STORED + LANE))
        text = visible_text(aside)
        self.assertIn("Raised while you were away: 1", text)
        self.assertIn("Two turns edited the running board.", aside)
        self.assertNotIn("Two turns edited the running board.", text)
        # The reading's own departures are said once, in the result.
        self.assertNotIn("FROM THE READING YOU ASKED FOR", aside)


if __name__ == "__main__":
    unittest.main()


def activity_of(html: str) -> str:
    start = html.index("data-next-session-activity")
    return html[start:]


def header_of(html: str) -> str:
    start = html.index('<header class="next-session-detail-header"')
    return html[start : html.index("</header>", start)]


TOOL_OUTPUT = "Tool output, only after you allow it"


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheActivityColumnIsTieredTest(PanelPage):
    def test_the_tool_output_sentence_is_said_once_on_the_page(self) -> None:
        html = self.page("claude", IDLE_DRAFTED)
        self.assertEqual(1, html.count(TOOL_OUTPUT))
        drift = html[html.index('id="next-session-drift-heading"') : html.index("</aside>")]
        self.assertIn(TOOL_OUTPUT, drift)

    def test_the_record_footer_keeps_one_clause_in_view(self) -> None:
        activity = activity_of(self.page("claude", IDLE_DRAFTED))
        text = visible_text(activity)
        self.assertIn("Results are as the tool reported; not inspected.", text)
        self.assertIn("About this record", text)
        for behind in ("1 observed of what it did", "Claude records the checks a session ran"):
            with self.subTest(behind=behind):
                self.assertIn(behind, activity)
                self.assertNotIn(behind, text)

    def test_a_harness_whose_work_is_not_read_keeps_its_limit_in_view(self) -> None:
        activity = activity_of(self.page("codex", ELIGIBLE))
        self.assertIn("Codex publishes no demonstrated work results", visible_text(activity))

    def test_command_shape_reports_off_is_one_summary(self) -> None:
        activity = activity_of(self.page("claude", IDLE_DRAFTED))
        text = visible_text(activity)
        self.assertIn("Command-shape reports: off", text)
        for behind in (
            "Command-shape reports are disabled for this run.",
            "A shape match does not prove the action succeeded.",
        ):
            with self.subTest(behind=behind):
                self.assertIn(behind, activity)
                self.assertNotIn(behind, text)

    def test_command_shape_reports_on_with_none_says_so_in_view(self) -> None:
        activity = activity_of(
            self.page("claude", IDLE_DRAFTED + "__dashboard.irreversible_enabled = true;\n")
        )
        text = visible_text(activity)
        self.assertIn("No command-shape reports.", text)
        self.assertIn("About these reports", text)
        self.assertNotIn("A shape match does not prove the action succeeded.", text)

    def test_the_facts_keep_next_step_and_blocked_in_view(self) -> None:
        activity = activity_of(self.page("claude", IDLE_DRAFTED))
        text = visible_text(activity)
        self.assertIn("NEXT STEP", text)
        self.assertIn("BLOCKED", text)
        self.assertRegex(text, r"Session facts: \S")
        for label in ("TURN", "GIT STATE", "PROJECT"):
            with self.subTest(label=label):
                self.assertIn(f"<dt>{label}</dt>", activity)
                self.assertNotIn(f" {label} ", f" {text} ")

    def test_a_missing_way_back_is_one_clause_beside_the_controls(self) -> None:
        html = self.page("claude", IDLE_DRAFTED)
        header = header_of(html)
        why = "This session published no usable id this run"
        self.assertIn("No resume command", visible_text(header))
        self.assertIn(why, header)
        self.assertNotIn(why, visible_text(header))
        self.assertEqual(1, html.count(why))

    def test_how_it_landed_keeps_its_claim_and_the_intent_log_its_link(self) -> None:
        activity = activity_of(self.page("claude", IDLE_DRAFTED))
        text = visible_text(activity)
        self.assertIn("Neither card implies the other.", text)
        self.assertNotIn("separate questions", text)
        self.assertIn('<a href="#n=intent">Intent log</a>', activity)
        self.assertIn("after the session leaves the board", activity)
        self.assertNotIn("after the session leaves the board", text)

    def test_each_rows_source_stays_on_the_page_out_of_view(self) -> None:
        # Plan slice E, D8: the per-row source was a full-width caption on every row, the same
        # string five times on a leveled page (DRC-4758 fix round).
        activity = activity_of(self.page("claude", IDLE_DRAFTED))
        text = visible_text(activity)
        sources = re.findall(
            r'<span class="next-cockpit-work-source[^"]*">([^<]*)</span>', activity
        )
        self.assertTrue(sources)
        for source in set(sources):
            with self.subTest(source=source):
                self.assertNotIn(source, text)
        self.assertIn('class="next-cockpit-work-source next-visually-hidden"', activity)

    def test_no_source_coverage_block_restates_the_next_step(self) -> None:
        # D11: "<owner> did not publish a next action." restated NEXT STEP's own absence.
        activity = activity_of(self.page("claude", IDLE_DRAFTED))
        self.assertIn("NEXT STEP", visible_text(activity))
        self.assertNotIn("SOURCE COVERAGE", activity)
        self.assertNotIn("next-session-source-coverage", activity)
        self.assertNotIn("did not publish a next action", activity)

    def test_the_activity_column_word_count(self) -> None:
        activity = activity_of(self.page("claude", IDLE_DRAFTED))
        count = len(visible_text(activity).split())
        print(f"\nidle-drafted activity column: {count} visible words")


@unittest.skipUnless(shutil.which("node"), "node not available")
class NothingRestatesItsValueTest(PanelPage):
    def test_no_block_note_restates_the_value_beside_it(self) -> None:
        sessions = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "for(const s of __dashboard.sessions){ s.harness = 'claude'; }\n"
            "await refreshNext();\nawait __settle();\n"
            "navigateNext({view:'sessions'});\nawait __settle();\n"
            "console.log(JSON.stringify(__els.app.innerHTML));",
            storage_prelude({}) + FIXTURE,
        )
        assert isinstance(sessions, str)
        self.assertIn('data-next-operation-fact="blocked"', sessions)
        page = self.page("claude", IDLE_DRAFTED)
        for html in (sessions, page):
            self.assertNotIn("Reporter available", html)
            self.assertNotIn("No block-state reading available", html)
