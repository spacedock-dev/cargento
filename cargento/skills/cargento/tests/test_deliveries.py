"""What became of a raise, and what the record may not claim about it.

DRC-4540. Before this store there was no raise record at all: the only trace
was a cooldown floor in memory, overwritten on every raise, so a signal that
never left the machine and one handed to the operating system left the same
mark.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cargento_runtime.deliveries import Delivery

from cargento_runtime import deliveries, notifications
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state


def _config(root: Path) -> Any:
    return build_runtime_config(
        environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
        platform_name="linux",
        os_name="posix",
        launcher_path=root / "server.py",
    )


class TheSentencesAreDisjointTest(unittest.TestCase):
    """One sentence per cause and never a shared one.

    `reading.WITHHELD`'s rule, for its reason: folding causes together makes the
    least true of them read as the most reassuring. Asserted rather than
    intended, because nothing else would notice a copy-paste.
    """

    def test_every_outcome_has_a_sentence(self) -> None:
        self.assertEqual(set(deliveries.OUTCOMES), set(deliveries.DELIVERY))

    def test_no_two_outcomes_read_alike(self) -> None:
        self.assertEqual(len(deliveries.DELIVERY), len(set(deliveries.DELIVERY.values())))

    def test_no_sentence_claims_the_reader_saw_anything(self) -> None:
        # The whole point of the wording. `osascript` exits zero under Do Not
        # Disturb and with the hosting app's notifications switched off, so the
        # call returning says the service accepted it and nothing more.
        every = [
            *deliveries.DELIVERY.values(),
            deliveries.NO_RECORD,
            deliveries.BROWSER_LANE_REPORTED,
            deliveries.BROWSER_LANE_UNREPORTED,
        ]
        for sentence in every:
            with self.subTest(sentence=sentence[:40]):
                lowered = sentence.lower()
                for claim in (
                    "you saw",
                    "you were told",
                    "was seen",
                    "was delivered",
                    "reached you",
                ):
                    self.assertNotIn(claim, lowered)

    def test_the_handed_over_sentence_declines_the_claim_in_its_own_words(self) -> None:
        handed = deliveries.DELIVERY[deliveries.OUTCOME_HANDED_OVER]
        self.assertIn("whether anyone saw it, is not something that call reports", handed)

    def test_a_timeout_is_not_a_failure(self) -> None:
        # Collapsing these is the same error the module exists to refuse one
        # level down: the call did not return, so what it did is unknown.
        timed_out = deliveries.DELIVERY[deliveries.OUTCOME_DID_NOT_RETURN]
        self.assertIn("unrecorded rather than known to have failed", timed_out)
        self.assertNotIn("error", timed_out)

    def test_an_absent_record_does_not_say_undelivered(self) -> None:
        self.assertIn("never written down", deliveries.NO_RECORD)
        self.assertNotIn("not delivered", deliveries.NO_RECORD)

    def test_the_unreported_browser_lane_declines_to_say_the_raise_missed(self) -> None:
        # DEC-19: absence is stale in one direction only, because a tab that
        # opens sends a report and a tab that closes sends none. Trimming the
        # second sentence is what would turn this into the forbidden claim.
        self.assertIn(
            "says nothing about whether the page raised one", deliveries.BROWSER_LANE_UNREPORTED
        )


class TheRecordSurvivesARestartTest(unittest.TestCase):
    """DRC-4547's defect one layer over, refused here rather than repeated.

    An outcome held in memory would make the no-record sentence fire for every
    raise before the last restart, and that sentence means "this predates the
    record" rather than "this board forgot".
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = _config(Path(self.temp.name))

    def test_a_recorded_outcome_reads_back_from_disk(self) -> None:
        self.assertTrue(
            deliveries.record(
                self.config,
                harness="claude",
                sid="s-1",
                lane="native",
                outcome=deliveries.OUTCOME_HANDED_OVER,
                now=100.0,
                diagnostic_sink=lambda _line: None,
            )
        )

        rows = deliveries.load(self.config)
        self.assertEqual(1, len(rows))
        self.assertEqual(deliveries.OUTCOME_HANDED_OVER, rows[0]["outcome"])
        self.assertEqual("native", rows[0]["lane"])

    def test_two_raises_on_one_session_are_two_records(self) -> None:
        # Session history could not hold this: `appended` keeps one transition
        # per (harness, sid) and would collapse them.
        for stamp in (100.0, 200.0):
            deliveries.record(
                self.config,
                harness="claude",
                sid="s-1",
                lane="native",
                outcome=deliveries.OUTCOME_HANDED_OVER,
                now=stamp,
                diagnostic_sink=lambda _line: None,
            )

        self.assertEqual(2, len(deliveries.load(self.config)))

    def test_an_outcome_outside_the_closed_set_is_refused_on_the_way_in(self) -> None:
        self.assertFalse(
            deliveries.record(
                self.config,
                harness="claude",
                sid="s-1",
                lane="native",
                outcome="delivered",
                now=100.0,
                diagnostic_sink=lambda _line: None,
            )
        )
        self.assertEqual((), deliveries.load(self.config))

    def test_an_outcome_outside_the_closed_set_is_refused_on_read_back(self) -> None:
        # Any local process can rewrite this file. The page looks a sentence up
        # by token, so an unknown one would render as nothing at all.
        os.makedirs(self.config.state_home, mode=0o700, exist_ok=True)
        with open(deliveries.store_path(self.config), "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "v": 1,
                    "entries": [
                        {
                            "harness": "claude",
                            "sid": "s-1",
                            "at": 1.0,
                            "lane": "native",
                            "outcome": "seen-by-the-reader",
                        },
                        {
                            "harness": "claude",
                            "sid": "s-2",
                            "at": 2.0,
                            "lane": "native",
                            "outcome": deliveries.OUTCOME_REFUSED,
                        },
                    ],
                },
                handle,
            )

        rows = deliveries.load(self.config)
        self.assertEqual(1, len(rows), "one bad record must not discard the others")
        self.assertEqual("s-2", rows[0]["sid"])

    def test_a_corrupt_store_is_no_records_rather_than_a_raise(self) -> None:
        os.makedirs(self.config.state_home, mode=0o700, exist_ok=True)
        with open(deliveries.store_path(self.config), "w", encoding="utf-8") as handle:
            handle.write("{not json")

        self.assertEqual((), deliveries.load(self.config))

    def test_the_oldest_record_is_the_one_that_gives_way(self) -> None:
        rows: list[Delivery] = [
            {
                "harness": "claude",
                "sid": f"s-{n}",
                "at": float(n),
                "lane": "native",
                "outcome": deliveries.OUTCOME_HANDED_OVER,
            }
            for n in range(1, 6)
        ]
        bounded = deliveries._bounded(rows, 3)

        self.assertEqual(["s-3", "s-4", "s-5"], [row["sid"] for row in bounded])


class TheCountsAreTwoNumbersAndNotOneTest(unittest.TestCase):
    """Attempts and hand-overs answer different questions.

    A single ratio answers neither, and neither figure is a compliance number:
    what a person saw is not in here and cannot be derived from it.
    """

    def _rows(self) -> list[Delivery]:
        rows: list[Delivery] = [
            {
                "harness": "claude",
                "sid": "a",
                "at": 1.0,
                "lane": "native",
                "outcome": deliveries.OUTCOME_HANDED_OVER,
            },
            {
                "harness": "claude",
                "sid": "b",
                "at": 2.0,
                "lane": "native",
                "outcome": deliveries.OUTCOME_REFUSED,
            },
            {
                "harness": "claude",
                "sid": "c",
                "at": 3.0,
                "lane": "native",
                "outcome": deliveries.OUTCOME_DID_NOT_RETURN,
            },
            {
                "harness": "claude",
                "sid": "d",
                "at": 4.0,
                "lane": "native",
                "outcome": deliveries.OUTCOME_NO_LANE,
            },
        ]
        return rows

    def test_a_raise_with_no_lane_is_not_an_attempt(self) -> None:
        counted = deliveries.counts(self._rows())

        self.assertEqual(4, counted["raises"])
        self.assertEqual(3, counted["attempted"])
        self.assertEqual(1, counted["handed_over"])

    def test_a_timeout_counts_as_attempted_and_not_as_handed_over(self) -> None:
        counted = deliveries.counts(self._rows())

        self.assertNotEqual(counted["attempted"], counted["handed_over"])


class ThePublishedRowNamesTheLatestOutcomeTest(unittest.TestCase):
    def test_a_session_with_no_raise_publishes_an_absence_and_not_a_verdict(self) -> None:
        row = deliveries.published((), "claude", "s-1")

        self.assertEqual("", row["delivery_outcome"])
        self.assertEqual("", row["delivery_why"])
        self.assertEqual(0, row["delivery_raises"])

    def test_the_newest_raise_is_the_one_described(self) -> None:
        rows: list[Delivery] = [
            {
                "harness": "claude",
                "sid": "s-1",
                "at": 1.0,
                "lane": "native",
                "outcome": deliveries.OUTCOME_NO_LANE,
            },
            {
                "harness": "claude",
                "sid": "s-1",
                "at": 9.0,
                "lane": "native",
                "outcome": deliveries.OUTCOME_HANDED_OVER,
            },
            {
                "harness": "claude",
                "sid": "other",
                "at": 5.0,
                "lane": "native",
                "outcome": deliveries.OUTCOME_REFUSED,
            },
        ]

        row = deliveries.published(rows, "claude", "s-1")

        self.assertEqual(deliveries.OUTCOME_HANDED_OVER, row["delivery_outcome"])
        self.assertEqual(2, row["delivery_raises"])
        self.assertIn("accepted it", row["delivery_why"])


class ARealRaiseWritesARecordTest(unittest.TestCase):
    """End to end through `maybe_popup`, not through the store's own API.

    Asserted here rather than only in `test_notifications` because the thing
    under test is that the outcome reaches the store at all: the notifier is
    called outside the lock and the record is written outside it too, so a
    refactor that drops the call site leaves both suites green otherwise.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = _config(Path(self.temp.name))
        self.state = build_runtime_state(self.config, started=1_000.0)

    def _raise(self, outcome: str | None) -> None:
        notifications.maybe_popup(
            self.config,
            self.state,
            notifications.PopupSubject(
                harness="claude", label="Claude", prefix="s-1", activity=0.0
            ),
            "needs_input",
            "a detail",
            popup_notifier=lambda _title, _message: outcome,
        )

    def test_the_outcome_the_notifier_reported_is_what_is_stored(self) -> None:
        self._raise(deliveries.OUTCOME_REFUSED)

        rows = deliveries.load(self.config)
        self.assertEqual(1, len(rows))
        self.assertEqual(deliveries.OUTCOME_REFUSED, rows[0]["outcome"])
        self.assertEqual("gate", rows[0]["lane"])
        self.assertEqual("s-1", rows[0]["sid"])

    def test_a_notifier_that_declines_to_report_writes_no_record(self) -> None:
        # `None` is a notifier that does not report, which is not a fifth
        # outcome. Recording a guess here is the collapse this store refuses.
        self._raise(None)

        self.assertEqual((), deliveries.load(self.config))

    def test_a_gate_that_never_reaches_the_notifier_writes_no_record(self) -> None:
        # Not entering needs_input: the raise does not happen, so there is
        # nothing that became of it.
        notifications.maybe_popup(
            self.config,
            self.state,
            notifications.PopupSubject(
                harness="claude", label="Claude", prefix="s-1", activity=0.0
            ),
            "working",
            None,
            popup_notifier=lambda _title, _message: deliveries.OUTCOME_HANDED_OVER,
        )

        self.assertEqual((), deliveries.load(self.config))


if __name__ == "__main__":
    unittest.main()
