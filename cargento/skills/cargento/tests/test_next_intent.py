"""The Intent log: DRC-4512's retention surface and DRC-4533's read surface.

One surface answering both, because they are one question. What makes it a
surface rather than a column somewhere is that its rows outlive the board: an
annotation is keyed on `(harness, sid)` and carries no project, so a departed
session's words cannot be filed under one.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

from cargento_runtime import annotations as annotation_store
from cargento_runtime import history
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

from .next_harness import NextPageJsHarness, storage_prelude


def _assessment(*, revision_read: int) -> dict[str, Any]:
    """A stored reading in the shape `annotations._assessment` admits."""
    return {
        "revision_read": revision_read,
        "revision_read_at": 140,
        "scope": "final",
        "stamp": "a-model - read at 10:00",
        "ended_at_read": 200,
        "criteria": {
            "goal": {
                "result": "consistent with the evidence read",
                "cites": [],
                "detail": "",
                "clause": "Ship the cockpit",
            },
            "output": {
                "result": "not verifiable from available evidence",
                "cites": [],
                "detail": "",
                "clause": "",
            },
        },
    }


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextIntentViewTest(NextPageJsHarness):
    FIXTURE = """
const __dashboard = {
  generated: 200, rate_window_sec: 600, window_hours: 24, annotate: true,
  summary: {working: 1, needs_input: 0},
  harnesses: [{key: "codex", label: "Codex"}],
  sessions: [{sid: "live-1", harness: "codex", project: "cargento",
    project_key: "cargento", state: "working", active: true,
    last_activity: 199, title: "Still here", subagents: []}]
};
__fetchImpl = async url => String(url) === "/api/annotations"
  ? {ok: true, json: async () => ({annotations: __annotations})}
  : {ok: true, json: async () => __dashboard};
__els.app = {innerHTML: ""};
"""

    def render(
        self,
        annotations: list[dict[str, Any]],
        *,
        annotate: bool = True,
        unasked: bool = False,
    ) -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            f"const __rows = {json.dumps(annotations)};\n"
            """
__annotations = __rows;
navigateNext({view:"intent"});
await __settle();
await __settle();
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  html,
  title: document.title,
  rows: (html.match(/class="next-intent-row"/g) || []).length,
  visible: html.replace(/<[^>]*>/g, " ").replace(/\\s+/g, " "),
}));
""",
            storage_prelude({})
            + "let __annotations = [];\n"
            + self.FIXTURE.replace(
                "annotate: true",
                f"annotate: {str(annotate).lower()}, unasked: {str(unasked).lower()}, "
                # The server publishes this table whenever the store is live,
                # and the record's standing-raise sentence is read out of it
                # rather than composed here (DRC-4565).
                f"annotate_discard: {json.dumps(annotation_store.DISCARD_SENTENCES)}",
            ),
        )
        assert isinstance(out, dict)
        return out

    @staticmethod
    def _row(**over: Any) -> dict[str, Any]:
        row = {
            "harness": "codex",
            "sid": "live-1",
            "goal": "Ship the cockpit",
            "goal_why": "",
            "output": "",
            "output_why": "No expected output typed.",
            "revision": 1,
            "revision_count": 1,
            "at": 150,
            "binding_why": "",
            "settled_at": None,
            "settled_through": None,
            "settled_revision": None,
            # Already on the wire from `annotations.published`, and the reason
            # this surface could always have known: it asserted instead.
            "assessment": None,
            "reading_count": 0,
            "reading_withheld": "",
            # Served on the same request as the words, because the payload
            # holds only sessions still on the board and these rows outlive one.
            "departures": [],
            "departure_why": "",
            # The third state (DRC-4565). Published on every row at its absent
            # value, because a row that omitted the key would render the
            # discard branch as `undefined` rather than as not-discarded.
            "discarded_at": None,
            "discarded_why": "",
        }
        row.update(over)
        return row

    @classmethod
    def _record(cls, sid: str = "gone-9", *, at: float = 160.0, **over: Any) -> dict[str, Any]:
        """A row as `annotations.published` renders a discard record.

        Built from the same helper as a live row so the two differ only in the
        fields the store actually changes: this is the pair the whole issue is
        about, and a hand-written second fixture could make them differ by
        accident and prove nothing.
        """
        return cls._row(
            sid=sid,
            goal="",
            goal_why=annotation_store.DISCARDED_GOAL,
            output="",
            output_why=annotation_store.DISCARDED_OUTPUT,
            revision=None,
            revision_count=0,
            at=None,
            discarded_at=at,
            discarded_why=annotation_store.DISCARD_RECORD,
            **over,
        )

    def test_the_view_is_reachable_and_names_itself(self) -> None:
        out = self.render([self._row()])

        self.assertEqual("Cargento — Intent log", out["title"])
        self.assertIn("Intent log", out["visible"])
        # Reachable from the primary nav on every view, which is what stops it
        # being a screen only a typed fragment finds.
        self.assertIn('href="#n=intent"', out["html"])
        self.assertIn(">Intent log</a>", out["html"])

    def test_a_session_still_on_the_board_links_into_its_held_to_tab(self) -> None:
        out = self.render([self._row()])

        self.assertEqual(1, out["rows"])
        self.assertIn("Ship the cockpit", out["visible"])
        self.assertIn("#n=project:cargento:codex%3Alive-1:held-to", out["html"])

    def test_a_departed_session_keeps_its_words_and_says_it_cannot_be_opened(self) -> None:
        out = self.render([self._row(sid="gone-9", goal="Prove the fixes landed")])

        # The whole reason this is a surface: the words outlive the row.
        self.assertIn("Prove the fixes landed", out["visible"])
        self.assertIn("Not on the board now, so there is nowhere to open", out["visible"])
        # And it offers no link that would land on the stale-filter surface.
        self.assertNotIn("gone-9:held-to", out["html"])

    def test_a_prefix_bound_row_says_so_here_too(self) -> None:
        """Found by walking the board, not by the suite.

        The Held to tab tells a reader that Claude's eight-character identity
        means another session sharing it would share these words. This list is
        where many sessions are on screen at once, which is where a shared
        prefix would actually bite, and it said nothing. Worse than nothing:
        `published`'s default is `BINDING_EXACT`, so an absent caveat is a
        claim of exact binding rather than an absence of information.
        """
        out = self.render(
            [
                self._row(sid="bbc131ca", binding_why=annotation_store.BINDING_BY_PREFIX),
                self._row(sid="a-full-length-identity", goal="Whole id", binding_why=""),
            ]
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("Another session sharing it would share these words", visible)
        # Once, for the row it is true of. A caveat on every row would be the
        # same overclaim in the other direction.
        self.assertEqual(1, visible.count("Another session sharing it"))

    def test_the_bound_is_a_count_and_the_copy_does_not_deny_history_holds_them(self) -> None:
        out = self.render([self._row()])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("keeps the newest 256 and sixteen revisions each", visible)
        self.assertIn("dropping the oldest save first", visible)
        # History DOES keep a fourteen-day copy of these two fields, so the
        # surface may not say it is the only place they live. What it says is
        # narrower and true: leaving this list is an eviction, not an expiry.
        self.assertIn("eviction and not an expiry", visible)
        self.assertNotIn("is not what holds these words", visible)

    # --- DRC-4565: the third state on the surface that outlives a session ---

    def test_a_discarded_session_keeps_a_row_and_that_row_says_when(self) -> None:
        """AC1. Measured before this: the discard REMOVED the session from the
        log, so the one surface built to outlive a session was the surface a
        discard erased it from.
        """
        out = self.render([self._record(at=140.0)])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertEqual(1, out["rows"])
        self.assertIn("codex:gone-9", visible)
        self.assertIn(annotation_store.DISCARD_RECORD, visible)
        # And when, derived from the moment on the row against the payload's
        # own `generated`, in the register the revision line already uses.
        self.assertIn("discarded 1m ago", visible)

    def test_a_discarded_session_and_one_nobody_typed_against_never_read_alike(self) -> None:
        """AC2. A session nobody typed against has no row here at all, so the
        pair is a row against no row -- and the row must not be worded as one
        that could describe an absence.
        """
        out = self.render([self._record()])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertNotIn("No goal typed for this session.", visible)
        self.assertNotIn("No expected output typed.", visible)
        self.assertNotIn("No revision saved yet", visible)
        self.assertNotIn("No reading asked for", visible)

    def test_the_leading_count_does_not_claim_words_were_typed_against_a_record(self) -> None:
        """AC3. The first Measured Invariant's shape: a figure derived from the
        row count would read a structurally-present row as a measurement.

        Measured before the record existed and still wrong the other way: the
        count fell from 2 to 1 the moment a discard landed, so the log
        asserted a smaller history than the reader had lived.
        """
        out = self.render([self._row(), self._record()])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("1 session you have typed words against", visible)
        self.assertIn("1 whose words you discarded", visible)
        self.assertNotIn("2 sessions you have typed words against", visible)

    def test_the_count_is_unchanged_where_nothing_was_discarded(self) -> None:
        """The boring outcome, so the clause is not added to every board."""
        out = self.render([self._row(), self._row(sid="two")])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("2 sessions you have typed words against", visible)
        self.assertNotIn("discarded", visible)

    def test_the_reading_denominator_does_not_count_a_record(self) -> None:
        """A record can never carry a reading, so counting it as one of the
        rows a reading could have been made against understates the figure."""
        out = self.render(
            [
                self._row(assessment=_assessment(revision_read=1), reading_count=1),
                self._record(),
            ]
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("1 of these 1 carries a reading", visible)
        self.assertNotIn("1 of these 2 carries a reading", visible)

    def test_nothing_of_the_discarded_words_reaches_the_rendered_surface(self) -> None:
        """AC4. The record carries no text, so this is a property of the store
        as much as of the render -- asserted here because the criterion is
        about what a reader can see."""
        out = self.render([self._record()])

        html = out["html"]
        assert isinstance(html, str)
        self.assertNotIn("Ship the cockpit", html)

    def test_a_record_does_not_carry_the_not_checked_sentence(self) -> None:
        """The account of a discard and the account of a check are two
        subjects, and the second reads as a claim about the past beside the
        first: "Cargento has not checked this session against what you asked
        for" is true only because the words are gone, and the record above it
        has already said that. A raise still on record IS a fact about the
        record, so the count stays.
        """
        why = "Cargento has not checked this session against what you asked for."
        out = self.render([self._record(departure_why=why)], unasked=True)

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertNotIn(why, visible)
        self.assertIn(annotation_store.DISCARD_RECORD, visible)

    def test_a_record_whose_raises_still_stand_says_so_and_counts_them(self) -> None:
        out = self.render(
            [self._record(departures=[{"constraint": "TYPED GOAL", "clause": "c"}])],
            unasked=True,
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("One departure raised", visible)
        self.assertIn(annotation_store.DISCARD_RECORD_STANDING, visible)

    def test_a_record_sorts_below_every_entry_that_still_holds_words(self) -> None:
        """The closing note says the bottom row is the next to go, and the
        store evicts records before words. Age alone puts a fresh record above
        an old entry and makes that sentence false."""
        out = self.render([self._record(at=190.0), self._row(sid="typed-1", at=100.0)])

        html = out["html"]
        assert isinstance(html, str)
        self.assertLess(html.index("codex:typed-1"), html.index("codex:gone-9"))

    def test_the_reading_column_states_its_absence_once_for_the_block(self) -> None:
        out = self.render([self._row(), self._row(sid="gone-9")])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertEqual(1, visible.count("No reading has been made against any of these"))
        # The one clause both this surface and the reading block owe, from one
        # constant rather than two wordings.
        self.assertIn("never a verification that the work was done", visible)

    def test_the_block_does_not_claim_none_when_one_row_carries_a_reading(self) -> None:
        # The defect this surface shipped with: the closing line was a constant,
        # so it said no reading existed while one rendered on the Held to tab
        # for a session listed directly beneath it.
        out = self.render(
            [
                self._row(assessment=_assessment(revision_read=1), reading_count=1),
                self._row(sid="gone-9"),
            ]
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertNotIn("No reading has been made against any of these", visible)
        self.assertIn("1 of these 2 carries a reading", visible)
        self.assertIn("never a verification that the work was done", visible)

    def test_a_row_names_the_revision_its_reading_read(self) -> None:
        out = self.render([self._row(revision=3, assessment=_assessment(revision_read=1))])

        visible = out["visible"]
        assert isinstance(visible, str)
        # Compact here on purpose. The Held to tab owns the full sentence about
        # a stale reading; two wordings of one fact is the divergence this
        # file's own comment refuses.
        self.assertIn("read revision 1", visible)
        self.assertIn("3 is current", visible)

    def test_a_row_with_a_reading_of_the_current_revision_says_so_plainly(self) -> None:
        out = self.render([self._row(revision=2, assessment=_assessment(revision_read=2))])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("read revision 2", visible)
        self.assertNotIn("2 is current", visible)

    def test_a_withheld_press_is_not_a_session_nobody_pressed_on(self) -> None:
        # Three states the old surface collapsed into one sentence: nobody
        # pressed, a press that produced nothing, and a press whose reading the
        # store refused.
        out = self.render(
            [self._row(reading_count=1, reading_withheld="The reading was not made.")]
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("The reading was not made.", visible)
        self.assertNotIn("No reading asked for", visible)

    def test_a_press_with_nothing_to_show_is_named_rather_than_read_as_unasked(self) -> None:
        # `readings` survives a reading the store refuses on read-back, so a
        # count with no assessment and no withheld reason is a real state and
        # was the one with no sentence.
        out = self.render([self._row(reading_count=2)])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("2 readings asked for", visible)
        self.assertNotIn("No reading asked for", visible)

    def test_nothing_typed_anywhere_is_not_the_same_as_the_store_being_off(self) -> None:
        empty = self.render([])

        self.assertIn("Nothing has been typed against any session yet", empty["visible"])
        self.assertEqual(0, empty["rows"])

        # The half this test was named for and did not check. Measured while
        # closing DRC-4533: the fixture hardcoded `annotate: true`, so deleting
        # the off branch entirely left the suite green and told a
        # `--no-annotations` reader that nothing had been typed -- which is the
        # one thing this surface must never say when it cannot know.
        off = self.render([], annotate=False)

        self.assertIn("Annotations are off for this run", off["visible"])
        self.assertIn("--no-annotations", off["visible"])
        self.assertNotIn("Nothing has been typed against any session yet", off["visible"])
        self.assertEqual(0, off["rows"])

    DEPARTURE: ClassVar[dict[str, Any]] = {
        "constraint": "TYPED GOAL",
        "clause": "Ship the cockpit",
        "reading": "The work moved to the installer.",
        "evidence": "turn transcript",
        "revision": 1,
        "cutoff": 150,
        "at": 151,
        "follow_up": "No later check has read this session, so what happened after this raise "
        "is not recorded here.",
    }

    def test_a_row_carries_what_was_raised_against_the_words_beside_it(self) -> None:
        """DRC-4514. The retention surface retained the words and not the raises."""
        out = self.render(
            [
                self._row(
                    assessment=_assessment(revision_read=1),
                    reading_count=1,
                    departures=[self.DEPARTURE, dict(self.DEPARTURE, constraint="EXPECTED")],
                )
            ],
            unasked=True,
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        # Both lines, not one instead of the other.
        self.assertIn("read revision 1", visible)
        self.assertIn("2 departures raised", visible)

    def test_a_row_with_no_raise_carries_the_reason_rather_than_a_bare_zero(self) -> None:
        out = self.render(
            [
                self._row(
                    departure_why="Cargento has not checked this session against what you "
                    "asked for. Nothing here says whether it would have found anything."
                )
            ],
            unasked=True,
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("has not checked this session against what you asked for", visible)
        self.assertNotIn("0 departures", visible)

    def test_a_row_says_nothing_about_a_check_when_the_lane_is_not_running(self) -> None:
        """The same board state was getting two accounts on two surfaces.

        `departures.why` is called by the route with no lane gate, defensibly:
        with the switch off the store is empty and "not checked" is literally
        true. But the session page and the departure review both DROP the block
        under the same switch, so a default board printed "Cargento has not
        checked this session against what you asked for" on every row here,
        four words above the closing note's own "and nothing watches for one".
        A feature that is not running is not a check merely pending. The switch
        is explained once for the view, in that note, rather than once a row.
        """
        off = self.render(
            [
                self._row(
                    departure_why="Cargento has not checked this session against what you "
                    "asked for. Nothing here says whether it would have found anything."
                )
            ]
        )

        visible = off["visible"]
        assert isinstance(visible, str)
        self.assertNotIn("has not checked this session against what you asked for", visible)
        self.assertIn("and nothing watches for one", visible)

    def test_a_raise_on_record_survives_the_switch_that_stops_new_checks(self) -> None:
        """DRC-4559. This log is the only surface a departed session's raise
        lives on, and the switch took the cell off every row.

        The row keeps saying a raise is on record; the closing note is where
        the switch is explained, once for the view, and it now distinguishes
        nothing watching now from nothing ever having been raised.
        """
        out = self.render([self._row(sid="gone-9", departures=[self.DEPARTURE])])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("One departure raised", visible)
        self.assertIn("and nothing watches for one", visible)
        self.assertIn(
            "The checks that run while you were away are off for this run, so nothing new "
            "is being checked. What was already raised is still on record.",
            visible,
        )

    def test_the_lane_off_note_says_nothing_extra_when_nothing_was_raised(self) -> None:
        """The clause is keyed on rows on record, never on the switch alone."""
        out = self.render([self._row()])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("and nothing watches for one", visible)
        self.assertNotIn("What was already raised is still on record", visible)

    def test_the_closing_line_stops_claiming_nothing_watches_when_something_does(self) -> None:
        """The clause was unconditional in both branches and false under the switch."""
        off = self.render([self._row()])
        on = self.render([self._row()], unasked=True)

        for out in (off, on):
            assert isinstance(out["visible"], str)
        self.assertIn("and nothing watches for one", off["visible"])
        self.assertNotIn("and nothing watches for one", on["visible"])

    def test_a_departed_session_gains_the_line_and_keeps_its_own(self) -> None:
        out = self.render(
            [self._row(sid="gone-9", goal="Prove the fixes landed", departures=[self.DEPARTURE])],
            unasked=True,
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("Prove the fixes landed", visible)
        self.assertIn("Not on the board now, so there is nowhere to open", visible)
        self.assertIn("One departure raised", visible)
        self.assertNotIn("gone-9:held-to", out["html"])


class TheIntentLogReadsTheStoreAndNotHistoryTest(unittest.TestCase):
    """Why the rows come from the annotation store alone.

    Not a preference. `annotations.clear` removes the entry, because clearing
    the field is withdrawing the request, while `annotation_goal` and
    `annotation_output` are in history's `OBSERVATION_FIELDS` and an
    observation already appended is never retro-deleted. A log backfilled from
    history would therefore republish, on a permanent surface, words the reader
    took back.
    """

    def test_history_admits_the_two_fields_the_log_must_not_read_back(self) -> None:
        # Both halves of the hazard, asserted rather than assumed: history
        # holds them, and holds them as prompt text.
        for field in ("annotation_goal", "annotation_output"):
            with self.subTest(field=field):
                self.assertIn(field, history.OBSERVATION_FIELDS)
                self.assertIn(field, history.PROMPT_TEXT_ALLOWLIST)

    def test_clearing_removes_the_entry_from_the_store_the_log_reads(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            config = build_runtime_config(
                environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
                platform_name="linux",
                os_name="posix",
                launcher_path=root / "server.py",
            )
            state = build_runtime_state(config, started=1_800_000_000.0)
            annotation_store.annotate(
                config, state, "pi", "s1", goal="withdraw me", now=1_800_000_000.0
            )
            self.assertIsNotNone(
                annotation_store.find(annotation_store.active(config, state), "pi", "s1")
            )

            annotation_store.clear(config, state, "pi", "s1")

            # The WORDS are gone from the store, so gone from the log. That is
            # the property a history-backed log would not have, and it is
            # unchanged by the discard record left in their place (DRC-4565):
            # the record holds no revisions and no text, so nothing the reader
            # took back can be read back off it.
            entry = annotation_store.find(annotation_store.active(config, state), "pi", "s1")
            assert entry is not None
            self.assertEqual((), entry["revisions"])
            self.assertNotIn("withdraw me", json.dumps(entry))
            self.assertEqual("", annotation_store.published(entry)["goal"])


if __name__ == "__main__":
    unittest.main()
