"""A fresh qualification may follow a failed one without erasing its spend."""

from __future__ import annotations

import json
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import IO
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import abstention_ledger
import mark_abstention
import score_abstention


class AFailedQualificationKeepsItsLedger(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.ledger_path = self.root / "spend.json"
        self.summary_path = self.root / "failed.json"
        self.grant_path = self.root / "continuation.json"
        self.new_summary_path = self.root / "new-result.json"
        self.old_marks = "a" * 64
        self.old_inputs = "b" * 64
        self.new_cases = "c" * 64
        self.new_marks = "d" * 64
        self.new_inputs = "e" * 64
        patches = (
            mock.patch.object(abstention_ledger, "LEDGER_PATH", str(self.ledger_path)),
            mock.patch.object(abstention_ledger, "CLAUDE_SUMMARY_PATH", str(self.summary_path)),
            mock.patch.object(abstention_ledger, "CONTINUATION_PATH", str(self.grant_path)),
            mock.patch.object(
                score_abstention, "CLAUDE_CONTINUATION_SUMMARY_PATH", str(self.new_summary_path)
            ),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        old = abstention_ledger.Ledger(
            str(self.ledger_path),
            cap=19,
            marks_digest=self.old_marks,
            inputs_digest=self.old_inputs,
            producer="claude",
        )
        for _ in range(13):
            old.settle(old.charge("1" * 16), "ok")
        self.prior = abstention_ledger.chain_of(str(self.ledger_path))
        self.summary_path.write_text(
            json.dumps(
                {
                    "verdict": "failed",
                    "producer": "claude",
                    "ledger_chain": self.prior,
                    "marks_digest": self.old_marks,
                    "inputs_digest": self.old_inputs,
                }
            )
        )

    def grant(self, phase: str = "sealed") -> None:
        new = {"cases_digest": self.new_cases}
        if phase == "sealed":
            new.update(marks_digest=self.new_marks, inputs_digest=self.new_inputs)
        self.grant_path.write_text(
            json.dumps(
                {
                    "v": 1,
                    "phase": phase,
                    "previous": {
                        "ledger_chain": self.prior,
                        "marks_digest": self.old_marks,
                        "inputs_digest": self.old_inputs,
                    },
                    "next": new,
                }
            )
        )

    def fresh(self) -> abstention_ledger.Ledger:
        return abstention_ledger.Ledger(
            str(self.ledger_path),
            cap=19,
            marks_digest=self.new_marks,
            inputs_digest=self.new_inputs,
            producer="claude",
            cases_digest=self.new_cases,
        )

    def test_a_second_packet_needs_a_sealed_grant_before_any_call(self) -> None:
        fresh = self.fresh()
        self.assertNotEqual("", fresh.check())
        self.grant("marking")
        self.assertNotEqual("", fresh.check())
        self.grant("sealed")
        self.assertEqual("", fresh.check())
        fresh.charge("2" * 16)
        self.assertEqual(14, fresh.used())
        self.assertTrue(abstention_ledger.begins_with(str(self.ledger_path), self.prior))

    def test_the_old_prefix_cannot_be_deleted_or_redigested(self) -> None:
        self.grant()
        body = abstention_ledger.read(str(self.ledger_path))
        body["calls"][0]["marks_digest"] = self.new_marks
        self.ledger_path.write_text(json.dumps(body))
        fresh = self.fresh()
        self.assertNotEqual("", fresh.check())
        with self.assertRaises(abstention_ledger.LedgerError):
            fresh.charge("2" * 16)

    def test_a_new_key_cannot_change_after_its_first_charge(self) -> None:
        self.grant()
        fresh = self.fresh()
        fresh.charge("2" * 16)
        self.new_marks = "f" * 64
        self.grant()
        changed = self.fresh()
        self.assertNotEqual("", changed.check())
        with self.assertRaises(abstention_ledger.LedgerError):
            changed.charge("2" * 16)

    def test_the_grant_names_the_case_set_as_well_as_the_scoring_digests(self) -> None:
        self.grant()
        fresh = self.fresh()
        fresh.cases_digest = "f" * 64
        self.assertNotEqual("", fresh.check())
        with self.assertRaises(abstention_ledger.LedgerError):
            fresh.charge("2" * 16)

    def test_the_global_cap_counts_both_packets(self) -> None:
        self.grant()
        fresh = self.fresh()
        for _ in range(6):
            fresh.charge("2" * 16)
        self.assertEqual(19, fresh.used())
        with self.assertRaises(abstention_ledger.SpendCapError):
            fresh.charge("2" * 16)

    def test_marking_is_scoped_to_new_cases_and_stops_after_the_first_call(self) -> None:
        self.grant("marking")
        self.assertFalse(
            mark_abstention._ledger_refusal(continuation=True, cases_digest=self.new_cases)
        )
        self.assertTrue(mark_abstention._ledger_refusal(continuation=True, cases_digest="f" * 64))
        self.grant("sealed")
        self.fresh().charge("2" * 16)
        self.assertTrue(
            mark_abstention._ledger_refusal(continuation=True, cases_digest=self.new_cases)
        )

    def test_a_grant_sealed_while_marking_cannot_save_late_answers(self) -> None:
        case = {"id": "2" * 16}
        body = {"v": 5, "cases": [case]}
        cases = self.root / "fresh-cases.json"
        marks = self.root / "fresh-marks.json"
        cases.write_text(json.dumps(body))
        self.new_cases = mark_abstention.cases_digest(body)
        self.grant("marking")

        def seal(*_args: object) -> dict[str, str]:
            self.grant("sealed")
            return {"goal": "abstain"}

        with (
            mock.patch.object(mark_abstention, "CASES_PATH", str(cases)),
            mock.patch.object(mark_abstention, "MARKS_PATH", str(marks)),
            mock.patch.object(mark_abstention, "_refuse_mismatch", return_value=False),
            mock.patch.object(mark_abstention, "_show_mark_case"),
            mock.patch.object(mark_abstention, "_mark_one", side_effect=seal),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(1, mark_abstention.mark(continuation=True))
        self.assertFalse(marks.exists())

    def test_a_new_charge_waits_until_the_final_mark_write_finishes(self) -> None:
        case = {"id": "2" * 16}
        body = {"v": 5, "cases": [case]}
        cases = self.root / "fresh-cases.json"
        marks = self.root / "fresh-marks.json"
        cases.write_text(json.dumps(body))
        self.new_cases = mark_abstention.cases_digest(body)
        self.grant("marking")
        native_write = mark_abstention._write
        native_lock = abstention_ledger._lock_file
        attempted = threading.Event()
        completed = threading.Event()
        errors: list[Exception] = []
        threads: list[threading.Thread] = []
        locks = 0

        def traced_lock(handle: IO[bytes]) -> None:
            nonlocal locks
            locks += 1
            if locks == 2:
                attempted.set()
            native_lock(handle)

        def charge() -> None:
            try:
                self.fresh().charge("2" * 16)
            except Exception as error:  # noqa: BLE001 - surface a worker failure to the test
                errors.append(error)
            finally:
                completed.set()

        def writing(path: str, value: dict[str, object]) -> None:
            self.grant("sealed")
            worker = threading.Thread(target=charge)
            threads.append(worker)
            worker.start()
            self.assertTrue(attempted.wait(1))
            self.assertFalse(completed.is_set())
            native_write(path, value)

        with (
            mock.patch.object(mark_abstention, "CASES_PATH", str(cases)),
            mock.patch.object(mark_abstention, "MARKS_PATH", str(marks)),
            mock.patch.object(mark_abstention, "_refuse_mismatch", return_value=False),
            mock.patch.object(mark_abstention, "_show_mark_case"),
            mock.patch.object(mark_abstention, "_mark_one", return_value={"goal": "abstain"}),
            mock.patch.object(mark_abstention, "_write", side_effect=writing),
            mock.patch.object(abstention_ledger, "_lock_file", side_effect=traced_lock),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(0, mark_abstention.mark(continuation=True))
        for worker in threads:
            # Windows' blocking file lock may retry at one-second intervals.
            worker.join(15)
        self.assertTrue(completed.is_set())
        self.assertEqual([], errors)
        self.assertTrue(marks.exists())

    def test_the_marking_flag_cannot_turn_into_a_freeze_or_reset(self) -> None:
        with mock.patch.object(mark_abstention, "freeze") as frozen, mock.patch("builtins.print"):
            self.assertEqual(
                2, mark_abstention.main(["--continue-mark", "--freeze", str(self.root / "spec")])
            )
            self.assertEqual(2, mark_abstention.main(["--continue-mark", "--reset"]))
        frozen.assert_not_called()

    def test_the_failed_result_cannot_be_overwritten_by_a_continuation(self) -> None:
        self.grant()
        self.assertFalse(score_abstention._chain_holds(self.fresh(), str(self.summary_path)))
        self.assertTrue(score_abstention._chain_holds(self.fresh(), str(self.new_summary_path)))
        alias = self.root / "alias.json"
        alias.symlink_to(self.new_summary_path)
        self.assertFalse(score_abstention._chain_holds(self.fresh(), str(alias)))

    def test_a_symlinked_new_result_still_cannot_overwrite_the_failed_result(self) -> None:
        original = self.summary_path.read_bytes()
        self.new_summary_path.symlink_to(self.summary_path)
        with (
            mock.patch.object(score_abstention, "local_results", return_value={}),
            mock.patch.object(score_abstention, "render", return_value=[]),
            mock.patch("builtins.print"),
        ):
            score_abstention._write_halves(
                {},
                {"verdict": "passed"},
                results_path=str(self.root / "local.json"),
                summary_path=str(self.new_summary_path),
            )
        self.assertEqual(original, self.summary_path.read_bytes())
        self.assertEqual("passed", json.loads(self.new_summary_path.read_text())["verdict"])

    def test_the_failed_result_cannot_alias_the_new_result(self) -> None:
        original = self.summary_path.read_bytes()
        self.new_summary_path.write_bytes(original)
        self.summary_path.unlink()
        self.summary_path.symlink_to(self.new_summary_path)
        self.grant()
        self.assertFalse(score_abstention._chain_holds(self.fresh(), str(self.new_summary_path)))

    def test_a_review_file_that_grows_after_stat_still_has_a_read_bound(self) -> None:
        path = self.root / "growing.json"
        path.write_bytes(b"x" * 100)
        forged = mock.Mock(st_mode=stat.S_IFREG, st_size=0)
        with (
            mock.patch("os.fstat", return_value=forged),
            self.assertRaises(abstention_ledger.LedgerError),
        ):
            abstention_ledger._review_json(str(path), "growing", cap=10)

    def test_both_results_accept_only_the_granted_old_prefix_and_new_suffix(self) -> None:
        self.grant()
        self.fresh().charge("2" * 16)
        old_summary = json.loads(self.summary_path.read_text())
        new_summary = {
            "producer": "claude",
            "marks_digest": self.new_marks,
            "inputs_digest": self.new_inputs,
            "ledger_chain": abstention_ledger.chain_of(str(self.ledger_path)),
        }
        self.assertEqual("", score_abstention._ledger_drift(old_summary))
        self.assertEqual("", score_abstention._ledger_drift(new_summary))
        body = abstention_ledger.read(str(self.ledger_path))
        body["calls"][-1]["marks_digest"] = "f" * 64
        self.ledger_path.write_text(json.dumps(body))
        self.assertNotEqual("", score_abstention._ledger_drift(old_summary))
        self.assertNotEqual("", score_abstention._ledger_drift(new_summary))

    def test_marking_a_new_packet_does_not_make_the_failed_result_stale(self) -> None:
        self.grant("marking")
        old_summary = json.loads(self.summary_path.read_text())
        self.assertEqual("", score_abstention._ledger_drift(old_summary))


if __name__ == "__main__":
    unittest.main()
