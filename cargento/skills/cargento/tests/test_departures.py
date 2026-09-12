"""What the departure store says about a raise, and about what came after it.

DRC-4514. Two things live here that the store alone did not answer before.

The four why-sentences moved down from `unasked.published`, because the review
surface and the Intent log both need them and neither may reach the lane: one
owner, so a spent cap cannot be worded one way on the session page and another
way where the reader reviews it.

The follow-up sentence is derived from later CHECKS in this same store rather
than from a second model call. That is what makes it affordable, and it is also
the only evidence available: a reader-requested reading carries its evidence
cutoff as a producer's sentence and not as a number, so nothing on it can be
compared with a departure's cutoff.
"""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import departures
from cargento_runtime.config import build_runtime_config


def _config(root: Path, **changes: Any) -> Any:
    config = build_runtime_config(
        environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
        platform_name="linux",
        os_name="posix",
        launcher_path=root / "server.py",
        unasked_enabled=True,
    )
    return dataclasses.replace(config, **changes) if changes else config


def _check(**over: Any) -> departures.Check:
    row: dict[str, Any] = {
        "harness": "claude",
        "sid": "abcd1234",
        "at": 1_000.0,
        "constraint": "TYPED GOAL",
        "clause": "do not change the board while capturing",
        "reading": "Two turns edited the running board's markup between captures.",
        "evidence": "turn transcript · Claude",
        "revision": 2,
        "cutoff": 1_000.0,
        "cutoff_text": "Evidence stops at 13:22.",
    }
    row.update(over)
    return row  # type: ignore[return-value]


class DepartureWhySentenceTest(unittest.TestCase):
    """The four sentences, chosen once and read from three surfaces."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.config = _config(Path(self._dir.name))

    def test_a_session_nobody_checked_is_not_a_session_found_to_be_on_track(self) -> None:
        why = departures.why(self.config, (), "claude", "abcd1234", now=2_000.0)

        self.assertEqual(departures.NEVER_CHECKED, why)

    def test_a_checked_session_with_no_raise_says_nothing_departed(self) -> None:
        stored = (_check(constraint="", clause="", reading="", evidence=""),)

        why = departures.why(self.config, stored, "claude", "abcd1234", now=2_000.0)

        self.assertEqual(departures.NOTHING_DEPARTED, why)

    def test_a_spent_session_cap_says_a_limit_was_spent(self) -> None:
        stored = tuple(
            _check(at=1_000.0 + n, cutoff=1_000.0 + n, constraint="", clause="")
            for n in range(self.config.unasked_session_cap)
        )

        why = departures.why(self.config, stored, "claude", "abcd1234", now=2_000.0)

        self.assertEqual(departures.SESSION_EXHAUSTED, why)

    def test_a_spent_day_cap_outranks_a_session_that_has_room(self) -> None:
        stored = (
            *(
                _check(sid=f"s-{n}", at=1_000.0 + n, cutoff=1_000.0 + n, constraint="")
                for n in range(self.config.unasked_daily_cap)
            ),
            _check(constraint=""),
        )

        why = departures.why(self.config, stored, "claude", "abcd1234", now=1_100.0)

        self.assertEqual(departures.DAY_EXHAUSTED, why)

    def test_a_session_with_a_raise_earns_no_absence_sentence(self) -> None:
        why = departures.why(self.config, (_check(),), "claude", "abcd1234", now=2_000.0)

        self.assertEqual("", why)


class DepartureFollowUpTest(unittest.TestCase):
    """What later evidence showed, and never that the raise caused it."""

    def test_unknown_is_the_default_and_names_its_reason(self) -> None:
        rows = departures.published((_check(),), "claude", "abcd1234")

        self.assertEqual(departures.FOLLOW_UP_NO_LATER_CHECK, rows[0]["follow_up"])

    def test_a_later_check_whose_evidence_predates_the_raise_says_so(self) -> None:
        stored = (
            _check(),
            # Ran later by the clock, read older evidence. A reading of the
            # record as it stood before the raise says nothing about after it.
            _check(at=2_000.0, cutoff=900.0, constraint=""),
        )

        rows = departures.published(stored, "claude", "abcd1234")

        self.assertEqual(departures.FOLLOW_UP_EVIDENCE_PREDATES, rows[0]["follow_up"])

    def test_a_later_check_that_raised_nothing_reports_the_evidence_not_an_effect(self) -> None:
        stored = (_check(), _check(at=2_000.0, cutoff=2_000.0, constraint="", clause=""))

        rows = departures.published(stored, "claude", "abcd1234")

        self.assertEqual(departures.FOLLOW_UP_NOT_RAISED_AGAIN, rows[0]["follow_up"])
        # The issue's third prohibition, asserted rather than trusted to the
        # wording: nothing here may read as the raise having worked.
        self.assertNotIn("because", rows[0]["follow_up"])

    def test_a_later_check_raising_the_same_constraint_says_it_departed_again(self) -> None:
        stored = (_check(), _check(at=2_000.0, cutoff=2_000.0))

        rows = departures.published(stored, "claude", "abcd1234")

        self.assertEqual(departures.FOLLOW_UP_RAISED_AGAIN, rows[1]["follow_up"])
        self.assertEqual(departures.FOLLOW_UP_NO_LATER_CHECK, rows[0]["follow_up"])

    def test_a_later_check_raising_a_different_constraint_is_not_this_one(self) -> None:
        stored = (_check(), _check(at=2_000.0, cutoff=2_000.0, constraint="EXPECTED OUTPUT"))

        rows = departures.published(stored, "claude", "abcd1234")
        by_constraint = {row["constraint"]: row["follow_up"] for row in rows}

        self.assertEqual(departures.FOLLOW_UP_NOT_RAISED_AGAIN, by_constraint["TYPED GOAL"])

    def test_another_session_s_later_check_says_nothing_about_this_one(self) -> None:
        stored = (_check(), _check(sid="zzzz9999", at=2_000.0, cutoff=2_000.0, constraint=""))

        rows = departures.published(stored, "claude", "abcd1234")

        self.assertEqual(departures.FOLLOW_UP_NO_LATER_CHECK, rows[0]["follow_up"])

    def test_the_follow_up_is_derived_at_publish_and_never_read_from_the_file(self) -> None:
        """A stored row that already carries one is not trusted on read-back.

        The store is a file any local process can rewrite, and a sentence about
        what happened next is the one a rewriter would most want to choose.
        """
        rows = departures.published((_check(follow_up="anything at all"),), "claude", "abcd1234")

        self.assertEqual(departures.FOLLOW_UP_NO_LATER_CHECK, rows[0]["follow_up"])


class DepartureCountsAreNotRaiseCountsTest(unittest.TestCase):
    """A row for every check is what bounds spend; it is not a count of raises."""

    def test_twelve_quiet_checks_and_two_raises_publish_two_rows(self) -> None:
        stored = (
            *(_check(at=100.0 + n, cutoff=100.0 + n, constraint="") for n in range(12)),
            _check(at=200.0),
            _check(at=201.0, constraint="EXPECTED OUTPUT"),
        )

        rows = departures.published(stored, "claude", "abcd1234")

        # Fourteen rows in the store, two of them raises. A surface counting
        # store rows would tell the reader this session departed fourteen times.
        self.assertEqual(14, len(stored))
        self.assertEqual(2, len(rows))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
