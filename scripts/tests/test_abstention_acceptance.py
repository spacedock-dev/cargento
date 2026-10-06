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
                repeated = committed.get("v") == 2
                parts = (
                    [repeat["summary"] for repeat in committed["repetitions"]]
                    if repeated
                    else [committed]
                )
                if repeated:
                    self.assertEqual("closure-three-repeats", committed["protocol"])
                    self.assertEqual([1, 2, 3], [r["repeat"] for r in committed["repetitions"]])
                rubric: dict[str, int] = {}
                for part in parts:
                    for name, count in part["rubric"]["counts"].items():
                        rubric[name] = rubric.get(name, 0) + count
                cases_key = "unique_cases" if repeated else "cases"
                failed = {case for part in parts for case in part["dec17"]["failed"]}
                self.assertEqual(committed["verdict"], run["verdict"])
                self.assertIn(run["verdict"], {"failed", "blocked"})
                self.assertEqual(committed["inputs_digest"], run["inputs_digest"])
                self.assertEqual(committed["marks_digest"], run["marks_digest"])
                self.assertEqual(committed["counts"][cases_key], run["cases"])
                self.assertEqual(len(failed), run["dec17_failed_cases"])
                self.assertEqual(rubric["correct"], run["correct"])
                self.assertEqual(
                    sum(v for k, v in rubric.items() if not k.startswith("unscored:")),
                    run["scored_constraints"],
                )
                self.assertEqual(committed["spend"], run["spend"])

    def test_the_blocked_opening_records_two_unusable_attempts_and_no_accuracy(self) -> None:
        by_result = {run["result"]: run for run in self.runs}
        name = "claude-results-continuation-5.json"
        self.assertIn(name, by_result)
        run = by_result[name]
        committed = _load(ABSTENTION / name)
        self.assertEqual("blocked", run["verdict"])
        self.assertEqual(1, run["cases"])
        self.assertEqual(0, run["correct"])
        self.assertEqual(0, run["scored_constraints"])
        self.assertEqual(0, run["dec17_failed_cases"])
        self.assertEqual({"charged": 32, "cap": 61}, run["spend"])
        self.assertEqual(
            {"unique_cases": 1, "registered_exposures": 1, "attempts": 2, "unusable_attempts": 2},
            committed["counts"],
        )
        self.assertTrue(committed["stopped"])
        for repetition in committed["repetitions"]:
            part = repetition["summary"]
            self.assertEqual(0, part["counts"]["reached_model"])
            self.assertEqual([], part["dec17"]["failed"])
            self.assertTrue(all(count == 0 for count in part["rubric"]["counts"].values()))
        self.assertIn("blocked", self.record["statement"])
        self.assertIn("no accuracy", self.record["statement"])

    def test_new_blocked_run_preserves_five_failures_and_the_original_owner_decision(self) -> None:
        self.assertEqual(6, self.record["scored_runs"])
        expected = {
            "claude-results.json": "failed",
            "claude-results-continuation.json": "failed",
            **{f"claude-results-continuation-{n}.json": "failed" for n in (2, 3, 4)},
            "claude-results-continuation-5.json": "blocked",
        }
        self.assertEqual(expected, {run["result"]: run["verdict"] for run in self.runs})
        self.assertEqual(
            {
                "accepted_by": "owner",
                "accepted_on": "2026-10-02",
                "decision": "accepted",
                "producer": "claude",
                "qualification": "failed",
            },
            {
                key: self.record[key]
                for key in ("accepted_by", "accepted_on", "decision", "producer", "qualification")
            },
        )
        self.assertEqual({"charged": 32, "cap": 61}, self.record["spend"])

    def test_the_runs_are_in_the_order_they_were_scored(self) -> None:
        stamps = [_load(ABSTENTION / run["result"])["scored_at"] for run in self.runs]
        self.assertEqual(sorted(stamps), stamps)

    def test_spend_matches_each_run_and_a_repeated_failure_can_stop_before_the_cap(self) -> None:
        last = _load(ABSTENTION / self.runs[-1]["result"])
        self.assertEqual(last["spend"], self.record["spend"])
        if last.get("v") != 2:
            self.assertEqual(last["spend"]["cap"], last["spend"]["charged"])
        for run in self.runs:
            committed = _load(ABSTENTION / run["result"])
            spend = committed["spend"]
            self.assertLessEqual(spend["charged"], spend["cap"])
            if committed.get("v") != 2:
                continue
            if spend["charged"] < spend["cap"]:
                self.assertTrue(committed["stopped"])
                if committed["verdict"] == "blocked":
                    self.assertEqual(2, committed["counts"]["attempts"])
                    self.assertEqual(2, committed["counts"]["unusable_attempts"])
                    self.assertTrue(
                        all(
                            not repeat["summary"]["dec17"]["failed"]
                            and not any(repeat["summary"]["rubric"]["counts"].values())
                            for repeat in committed["repetitions"]
                        )
                    )
                else:
                    self.assertEqual("failed", committed["verdict"])
                    self.assertTrue(
                        any(
                            repeat["summary"]["dec17"]["failed"]
                            or repeat["summary"]["rubric"]["counts"]["false-reassurance"]
                            for repeat in committed["repetitions"]
                        )
                    )


if __name__ == "__main__":
    unittest.main()
