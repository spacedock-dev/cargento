"""The four drift levels, and the two ways a session can say it has too little to tell.

[DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn)
rules two sources, each over its own named evidence: a live estimate computed without a model from
the checks and written paths the transcript recorded, and an analysis level derived from a stored
reading's per-line results. DRC-4692 names six cases the levels must get right before any reader
sees one; each is a class below, and each runs both functions.
"""

from __future__ import annotations

import unittest
from typing import TYPE_CHECKING, Any

from cargento_runtime import levels, reading

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

SAVE = 1_800_000_000.0


def check(fid: str, at: float, result: str, *, stale: bool = False) -> dict[str, Any]:
    """A check's latest run, as layer 1 publishes it into the observed record."""
    return {
        "fact_id": fid,
        "type": "tool_report",
        "subject": "check",
        "summary": "node --test",
        "result": result,
        "before_last_change": stale,
        "at": at,
    }


def wrote(fid: str, at: float, path: str) -> dict[str, Any]:
    """A written path, relative to the session's working directory."""
    return {"fact_id": fid, "type": "tool_report", "subject": "write", "summary": path, "at": at}


def scan(**counts: Any) -> dict[str, Any]:
    """The full-scan counts, zero unless named."""
    body: dict[str, Any] = dict.fromkeys(
        (
            "failed",
            "passed",
            "not_recorded",
            "background",
            "written_paths",
            "outside_paths",
            "more",
        ),
        0,
    )
    body["last_changing_command_at"] = None
    body.update(counts)
    return body


def evidence(
    facts: Sequence[Mapping[str, Any]], counts: Mapping[str, Any], *, directions: int = 0
) -> levels.Evidence:
    return levels.Evidence(facts=tuple(facts), scan=counts, unsettled_directions=directions)


def intent(
    *lines: str, saved: bool = True, goal: str = "Build the tic-tac-toe game"
) -> levels.Intent:
    return levels.Intent(saved=saved, goal=goal, lines=tuple(lines))


def criterion(result: str | None, *cites: str, why: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"cites": cites, "detail": "", "clause": "", "why": why}
    if result is not None:
        row["result"] = result
    return row


def a_reading(**criteria: dict[str, Any]) -> dict[str, Any]:
    return {"read_at": SAVE + 600, "window_start": SAVE, "criteria": criteria}


PASSING = evidence(
    [wrote("w1", SAVE + 10, "index.html"), check("c1", SAVE + 20, "passed")],
    scan(passed=1, written_paths=1),
)
SUPPORTED = a_reading(
    goal=criterion(reading.RESULT_CONSISTENT, "m1"),
    line_1=criterion(reading.RESULT_CONSISTENT, "c1"),
)


class FailedCheckTest(unittest.TestCase):
    """The latest run of a check failed: High on both sources (starting definitions)."""

    FACTS = evidence([check("c1", SAVE + 20, "failed")], scan(failed=1))

    def test_the_live_estimate_is_high_and_names_the_failed_check(self) -> None:
        got = levels.live_level(self.FACTS, intent("Tests pass"))
        self.assertEqual(got.level, levels.HIGH)
        self.assertIn(levels.REASON_FAILED_CHECK, got.reasons)
        self.assertEqual(got.cites, ("c1",))
        self.assertEqual(got.source, levels.SOURCE_LIVE)

    def test_an_analysis_departing_on_that_failure_is_high(self) -> None:
        got = levels.analysis_level(
            a_reading(line_1=criterion(reading.RESULT_DEPARTURE, "c1")), self.FACTS
        )
        self.assertEqual(got.level, levels.HIGH)
        self.assertIn(levels.REASON_FAILED_CHECK, got.reasons)
        self.assertEqual(got.source, levels.SOURCE_ANALYSIS)

    def test_a_failure_the_analysis_did_not_cite_still_keeps_it_high(self) -> None:
        got = levels.analysis_level(
            a_reading(line_1=criterion(reading.RESULT_UNVERIFIABLE, why="failed-check-unread")),
            self.FACTS,
        )
        self.assertEqual(got.level, levels.HIGH)

    def test_an_earlier_passing_run_does_not_soften_it(self) -> None:
        facts = evidence(
            [check("c1", SAVE + 20, "failed"), check("c2", SAVE + 5, "passed")],
            scan(failed=1, passed=1),
        )
        self.assertEqual(levels.live_level(facts, intent("Tests pass")).level, levels.HIGH)


class CheckWithNoRecordedResultTest(unittest.TestCase):
    """A check with no recorded result never counts toward "None or low" (DEC-26 item 1)."""

    def test_the_live_estimate_reads_not_enough(self) -> None:
        facts = evidence([check("c1", SAVE + 20, "not-recorded")], scan(not_recorded=1))
        got = levels.live_level(facts, intent("Tests pass"))
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertIn(levels.REASON_CHECK_NOT_RECORDED, got.reasons)

    def test_one_such_check_beside_a_pass_still_withholds_the_floor(self) -> None:
        facts = evidence(
            [check("c1", SAVE + 20, "not-recorded"), check("c2", SAVE + 30, "passed")],
            scan(not_recorded=1, passed=1),
        )
        self.assertEqual(levels.live_level(facts, intent("Tests pass")).level, levels.NOT_ENOUGH)

    def test_a_run_only_ever_launched_in_the_background_withholds_the_floor(self) -> None:
        # 3f4e7b30: a background-only check is not listed and not counted, so
        # only the launch count shows that something ran without a result.
        facts = evidence(list(PASSING.facts), scan(passed=1, background=1))
        got = levels.live_level(facts, intent("Tests pass"))
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertIn(levels.REASON_BACKGROUND_RUN, got.reasons)

    def test_an_analysis_citing_it_reads_not_enough(self) -> None:
        facts = evidence([check("c1", SAVE + 20, "not-recorded")], scan(not_recorded=1))
        got = levels.analysis_level(
            a_reading(line_1=criterion(reading.RESULT_UNVERIFIABLE, "c1")), facts
        )
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertIn(levels.REASON_LINE_NOT_SHOWN, got.reasons)

    def test_a_consistent_resting_on_it_is_not_counted_as_shown(self) -> None:
        facts = evidence([check("c1", SAVE + 20, "not-recorded")], scan(not_recorded=1))
        got = levels.analysis_level(
            a_reading(line_1=criterion(reading.RESULT_CONSISTENT, "c1")), facts
        )
        self.assertEqual(got.level, levels.NOT_ENOUGH)


class PassFollowedByWriteTest(unittest.TestCase):
    """A pass followed by writes is Medium (starting definitions)."""

    FACTS = evidence(
        [check("c1", SAVE + 20, "passed", stale=True), wrote("w1", SAVE + 30, "index.html")],
        scan(passed=1, written_paths=1),
    )

    def test_the_live_estimate_is_medium_and_cites_the_aged_pass(self) -> None:
        got = levels.live_level(self.FACTS, intent("Tests pass"))
        self.assertEqual(got.level, levels.MEDIUM)
        self.assertIn(levels.REASON_PASS_THEN_WRITE, got.reasons)
        self.assertIn("c1", got.cites)

    def test_an_analysis_demoting_the_aged_pass_is_medium(self) -> None:
        got = levels.analysis_level(
            a_reading(
                line_1=criterion(
                    reading.RESULT_UNVERIFIABLE, "c1", why=reading.WHY_CHECK_DOES_NOT_SHOW_IT
                )
            ),
            self.FACTS,
        )
        self.assertEqual(got.level, levels.MEDIUM)
        self.assertIn(levels.REASON_PASS_THEN_WRITE, got.reasons)

    def test_a_pass_a_later_command_may_have_changed_is_medium_too(self) -> None:
        got = levels.analysis_level(
            a_reading(
                line_1=criterion(
                    reading.RESULT_UNVERIFIABLE, "c1", why=reading.WHY_CHANGED_AFTER_CHECK
                )
            ),
            evidence([check("c1", SAVE + 20, "passed")], scan(passed=1)),
        )
        self.assertEqual(got.level, levels.MEDIUM)


class OwnAccountOnlyTest(unittest.TestCase):
    """845fe493: the final message claims a layout no check covers.

    The live estimate reads checks and file paths, not what the intent says, so a
    session whose checks pass reads "None or low" there and says so. An analysis
    may not rest an outcome line on the agent's own account (DEC-17 rule 7).
    """

    def test_the_live_estimate_meets_its_floor_and_says_what_it_read(self) -> None:
        got = levels.live_level(PASSING, intent("Works on a phone"))
        self.assertEqual(got.level, levels.NONE_OR_LOW)
        self.assertIn(levels.REASON_FLOOR_MET, got.reasons)
        self.assertEqual(got.source_line, levels.LIVE_SOURCE_LINE)

    def test_an_outcome_line_on_the_agents_account_reads_not_enough(self) -> None:
        got = levels.analysis_level(
            a_reading(
                goal=criterion(reading.RESULT_CONSISTENT, "c1"),
                line_1=criterion(reading.RESULT_UNVERIFIABLE, "m1", why=reading.WHY_NO_WORK_SHOWN),
            ),
            PASSING,
        )
        self.assertEqual(got.level, levels.NOT_ENOUGH)

    def test_a_consistent_citing_only_a_message_is_never_the_floor(self) -> None:
        got = levels.analysis_level(
            a_reading(line_1=criterion(reading.RESULT_CONSISTENT, "m1")), PASSING
        )
        self.assertEqual(got.level, levels.NOT_ENOUGH)

    def test_the_goal_may_rest_on_the_sessions_own_account(self) -> None:
        got = levels.analysis_level(SUPPORTED, PASSING)
        self.assertEqual(got.level, levels.NONE_OR_LOW)
        self.assertEqual(got.source_line, levels.ANALYSIS_SOURCE_LINE)
        self.assertEqual(got.computed_at, SAVE + 600)


class IntentNamesNoFolderTest(unittest.TestCase):
    """The folder signal is not used when the intent names no folder, so it is never read as 0%."""

    SPREAD = evidence(
        [
            wrote("w1", SAVE + 5, "server/app.py"),
            wrote("w2", SAVE + 6, "server/db.py"),
            wrote("w3", SAVE + 7, "web/index.html"),
            check("c1", SAVE + 20, "passed"),
        ],
        scan(passed=1, written_paths=3),
    )

    def test_no_folder_leaves_the_share_unread(self) -> None:
        got = levels.live_level(self.SPREAD, intent("Tests pass"))
        self.assertEqual(got.level, levels.NONE_OR_LOW)
        self.assertIn(levels.REASON_NO_FOLDER, got.reasons)
        self.assertIsNone(got.writes_outside)
        self.assertIsNone(got.writes_total)

    def test_a_named_folder_with_some_writes_outside_is_medium(self) -> None:
        got = levels.live_level(self.SPREAD, intent("Only touch `server/`", "Tests pass"))
        self.assertEqual(got.level, levels.MEDIUM)
        self.assertIn(levels.REASON_SOME_OUTSIDE, got.reasons)
        self.assertEqual((got.writes_outside, got.writes_total), (1, 3))
        self.assertEqual(got.cites, ("w3",))

    def test_most_writes_outside_is_high(self) -> None:
        got = levels.live_level(self.SPREAD, intent("Only touch web/", "Tests pass"))
        self.assertEqual(got.level, levels.HIGH)
        self.assertIn(levels.REASON_MOST_OUTSIDE, got.reasons)

    def test_every_write_inside_meets_the_floor_and_counts_the_share(self) -> None:
        got = levels.live_level(self.SPREAD, intent("Work in server/ and web/"))
        self.assertEqual(got.level, levels.NONE_OR_LOW)
        self.assertEqual((got.writes_outside, got.writes_total), (0, 3))

    def test_a_write_outside_the_working_directory_is_outside_every_folder(self) -> None:
        facts = evidence([check("c1", SAVE + 20, "passed")], scan(passed=1, outside_paths=1))
        got = levels.live_level(facts, intent("Only touch server/"))
        self.assertEqual(got.level, levels.HIGH)

    def test_the_analysis_does_not_read_folders_at_all(self) -> None:
        self.assertEqual(levels.analysis_level(SUPPORTED, self.SPREAD).level, levels.NONE_OR_LOW)


class UnsavedDraftTest(unittest.TestCase):
    """Over an unsaved draft there is no live level (DEC-26 item 2)."""

    def test_the_live_estimate_has_no_level_even_over_a_failure(self) -> None:
        facts = evidence([check("c1", SAVE + 20, "failed")], scan(failed=1))
        got = levels.live_level(facts, intent("Tests pass", saved=False))
        self.assertEqual(got.level, levels.NO_LIVE_LEVEL)
        self.assertEqual(got.reasons, (levels.REASON_DRAFT_UNSAVED,))
        self.assertEqual(got.cites, ())

    def test_with_no_reading_the_analysis_has_too_little(self) -> None:
        got = levels.analysis_level(None, PASSING)
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertEqual(got.reasons, (levels.REASON_NO_READING,))


class FloorTest(unittest.TestCase):
    """What else keeps "None or low" off a session: DEC-26 item 1, clause by clause."""

    def test_zero_checks_is_too_little(self) -> None:
        facts = evidence([wrote("w1", SAVE + 5, "index.html")], scan(written_paths=1))
        got = levels.live_level(facts, intent("Tests pass"))
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertIn(levels.REASON_NO_PASSING_CHECK, got.reasons)

    def test_an_intent_with_no_outcome_line_is_too_little_for_an_analysis(self) -> None:
        got = levels.analysis_level(
            a_reading(goal=criterion(reading.RESULT_CONSISTENT, "c1")), PASSING
        )
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertIn(levels.REASON_NO_OUTCOME_LINE, got.reasons)

    def test_a_later_direction_blocks_the_floor_and_is_never_drift(self) -> None:
        with_direction = evidence(list(PASSING.facts), dict(PASSING.scan), directions=1)
        got = levels.live_level(with_direction, intent("Tests pass"))
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertIn(levels.REASON_LATER_DIRECTION, got.reasons)
        self.assertEqual(levels.analysis_level(SUPPORTED, with_direction).level, levels.NOT_ENOUGH)

    def test_a_later_direction_does_not_raise_a_level(self) -> None:
        failed = evidence([check("c1", SAVE + 20, "failed")], scan(failed=1), directions=2)
        self.assertEqual(levels.live_level(failed, intent("Tests pass")).level, levels.HIGH)

    def test_a_changing_command_after_the_pass_blocks_the_floor_and_is_never_drift(self) -> None:
        facts = evidence(list(PASSING.facts), scan(passed=1, last_changing_command_at=SAVE + 40))
        got = levels.live_level(facts, intent("Tests pass"))
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertIn(levels.REASON_CHANGING_COMMAND, got.reasons)

    def test_a_changing_command_before_the_pass_does_not(self) -> None:
        facts = evidence(list(PASSING.facts), scan(passed=1, last_changing_command_at=SAVE + 1))
        self.assertEqual(levels.live_level(facts, intent("Tests pass")).level, levels.NONE_OR_LOW)

    def test_a_pass_the_listed_entries_cannot_show_withholds_the_floor(self) -> None:
        # Item 4: every answer comes from the full scan. A pass counted and not
        # listed has no time to compare a write or a command against.
        facts = evidence(list(PASSING.facts), scan(passed=2, written_paths=1, more=1))
        got = levels.live_level(facts, intent("Tests pass"))
        self.assertEqual(got.level, levels.NOT_ENOUGH)
        self.assertIn(levels.REASON_UNLISTED, got.reasons)

    def test_an_unlisted_write_withholds_the_floor_where_folders_are_named(self) -> None:
        facts = evidence(
            [wrote("w1", SAVE + 5, "web/index.html"), check("c1", SAVE + 20, "passed")],
            scan(passed=1, written_paths=2, more=1),
        )
        got = levels.live_level(facts, intent("Only touch web/"))
        self.assertEqual(got.level, levels.NOT_ENOUGH)

    def test_an_analysis_with_every_line_supported_meets_the_floor(self) -> None:
        got = levels.analysis_level(SUPPORTED, PASSING)
        self.assertEqual(got.level, levels.NONE_OR_LOW)
        self.assertEqual(got.cites, ("c1",))


class ExtremeTest(unittest.TestCase):
    """Extreme: both of High's conditions hold."""

    def test_a_failed_check_and_most_writes_outside_is_extreme(self) -> None:
        facts = evidence(
            [check("c1", SAVE + 20, "failed"), wrote("w1", SAVE + 5, "server/app.py")],
            scan(failed=1, written_paths=1),
        )
        got = levels.live_level(facts, intent("Only touch web/"))
        self.assertEqual(got.level, levels.EXTREME)
        self.assertEqual(set(got.cites), {"c1", "w1"})

    def test_an_analysis_never_reads_extreme_because_it_reads_no_folder(self) -> None:
        facts = evidence([check("c1", SAVE + 20, "failed")], scan(failed=1))
        got = levels.analysis_level(
            a_reading(
                line_1=criterion(reading.RESULT_DEPARTURE, "c1"),
                line_2=criterion(reading.RESULT_DEPARTURE, "m1"),
                line_3=criterion(reading.RESULT_CONSISTENT, "c9"),
            ),
            facts,
        )
        self.assertEqual(got.level, levels.HIGH)

    def test_a_departure_on_no_failed_check_is_medium(self) -> None:
        got = levels.analysis_level(
            a_reading(line_1=criterion(reading.RESULT_DEPARTURE, "m1")), PASSING
        )
        self.assertEqual(got.level, levels.MEDIUM)
        self.assertIn(levels.REASON_DEPARTURE, got.reasons)


class NamedFoldersTest(unittest.TestCase):
    """What counts as a folder the intent names: a path-shaped word, never a URL or a file."""

    def test_the_forms_that_name_a_folder(self) -> None:
        self.assertEqual(
            levels.named_folders(intent("Work in `src/app/` and ./web, then tests/unit.")),
            ("src/app", "tests/unit", "web"),
        )

    def test_a_trailing_slash_names_a_single_folder(self) -> None:
        self.assertEqual(levels.named_folders(intent("Only touch server/")), ("server",))

    def test_urls_files_and_bare_words_name_none(self) -> None:
        self.assertEqual(
            levels.named_folders(intent("See https://example.com/a/b and edit index.html")), ()
        )

    def test_a_file_path_names_its_folder(self) -> None:
        self.assertEqual(levels.named_folders(intent("Change web/app.js")), ("web",))

    def test_a_write_to_the_folder_itself_or_below_is_inside(self) -> None:
        self.assertTrue(levels.inside("web/app.js", ("web",)))
        self.assertTrue(levels.inside("web", ("web",)))
        self.assertFalse(levels.inside("website/app.js", ("web",)))


if __name__ == "__main__":
    unittest.main()
