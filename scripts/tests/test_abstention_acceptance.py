"""The owner's acceptance of the Claude Code producer, 2026-10-02, held to the record.

The acceptance opens the producer without a pass. What keeps it honest is that
the committed record says so in the same file the gate rests on: every scored
Claude Code run is listed with its own verdict, read here from the result files
themselves, so the record cannot drop a failure or round one up. Nothing here
writes to `docs/abstention/`.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ABSTENTION = ROOT / "docs" / "abstention"
RECORD = ABSTENTION / "claude-acceptance.json"
SKILL = ROOT / "cargento" / "skills" / "cargento"
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

from cargento_runtime import annotations as annotation_store  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _committed_results() -> list[str]:
    return sorted(path.name for path in ABSTENTION.glob("claude-results*.json"))


class TheAcceptanceIsRecordedAsAcceptedAndNeverAsPassedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.record = _load(RECORD)

    def test_the_record_is_the_owners_acceptance_of_the_claude_code_producer(self) -> None:
        self.assertEqual("accepted", self.record["decision"])
        self.assertEqual("claude", self.record["producer"])
        self.assertEqual("owner", self.record["accepted_by"])
        self.assertEqual("2026-10-02", self.record["accepted_on"])
        self.assertNotIn("passed", json.dumps(self.record).casefold().replace("not passed", ""))

    def test_the_gate_the_runtime_reads_is_the_one_the_record_states(self) -> None:
        self.assertEqual(
            annotation_store.ABSTENTION_CHECK_ACCEPTED, annotation_store.CLAUDE_ABSTENTION_CHECK
        )
        self.assertEqual(self.record["decision"], annotation_store.CLAUDE_ABSTENTION_CHECK)

    def test_it_says_plainly_that_the_scored_runs_failed(self) -> None:
        statement = self.record["statement"]
        self.assertIn("failed", statement)
        self.assertIn("accepted", statement)
        self.assertIn("2026-10-02", statement)
        self.assertEqual("failed", self.record["qualification"])


class EveryScoredRunIsListedWithItsOwnVerdictTest(unittest.TestCase):
    def setUp(self) -> None:
        self.record = _load(RECORD)
        self.runs = self.record["runs"]

    def test_no_committed_claude_code_result_is_left_out(self) -> None:
        self.assertEqual(_committed_results(), sorted(run["result"] for run in self.runs))
        self.assertEqual(len(self.runs), self.record["scored_runs"])

    def test_each_listed_run_matches_the_file_it_names(self) -> None:
        for run in self.runs:
            with self.subTest(result=run["result"]):
                committed = _load(ABSTENTION / run["result"])
                rubric = committed["rubric"]["counts"]
                self.assertEqual(committed["verdict"], run["verdict"])
                self.assertEqual("failed", run["verdict"])
                self.assertEqual(committed["inputs_digest"], run["inputs_digest"])
                self.assertEqual(committed["marks_digest"], run["marks_digest"])
                self.assertEqual(committed["counts"]["cases"], run["cases"])
                self.assertEqual(len(committed["dec17"]["failed"]), run["dec17_failed_cases"])
                self.assertEqual(rubric["correct"], run["correct"])
                self.assertEqual(
                    sum(v for k, v in rubric.items() if not k.startswith("unscored:")),
                    run["scored_constraints"],
                )
                self.assertEqual(committed["spend"], run["spend"])

    def test_the_runs_are_in_the_order_they_were_scored(self) -> None:
        stamps = [_load(ABSTENTION / run["result"])["scored_at"] for run in self.runs]
        self.assertEqual(sorted(stamps), stamps)

    def test_the_spend_is_the_last_runs_and_the_ceiling_is_reached(self) -> None:
        last = _load(ABSTENTION / self.runs[-1]["result"])
        self.assertEqual(last["spend"], self.record["spend"])
        self.assertEqual(self.record["spend"]["cap"], self.record["spend"]["charged"])


if __name__ == "__main__":
    unittest.main()
