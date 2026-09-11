"""What the marking tool must not do to somebody's evening.

Every test here is a defect that shipped. Two versions of this tool reached the
repository owner and both wasted his time, so these are written against the
measured failures rather than against the happy path.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

if TYPE_CHECKING:
    from collections.abc import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mark_abstention


def _collect(sink: list[str]) -> Callable[..., None]:
    """A stand-in for print that keeps what was said."""

    def record(*args: Any, **_kwargs: Any) -> None:
        sink.append(" ".join(map(str, args)))

    return record


class CaseIdentityTest(unittest.TestCase):
    """v2 hashed the row's position in the board's session list.

    The board reorders on every state change, so a rebuild re-attached answers
    to different sessions. Measured on the real corpus: four of six ids
    collided with an unrelated session after a single shift.
    """

    def test_the_id_survives_a_reorder(self) -> None:
        first = mark_abstention._case_id("claude", "1b7958bc")
        again = mark_abstention._case_id("claude", "1b7958bc")
        self.assertEqual(first, again)

    def test_two_sessions_never_share_an_id(self) -> None:
        a = mark_abstention._case_id("claude", "1b7958bc")
        b = mark_abstention._case_id("claude", "09f68b92")
        self.assertNotEqual(a, b)

    def test_the_same_sid_on_two_harnesses_is_two_cases(self) -> None:
        self.assertNotEqual(
            mark_abstention._case_id("claude", "abc123"),
            mark_abstention._case_id("codex", "abc123"),
        )

    def test_the_id_carries_no_readable_session_identity(self) -> None:
        # The marks file is the half that gets committed.
        marked = mark_abstention._case_id("claude", "1b7958bc")
        self.assertNotIn("1b7958bc", marked)
        self.assertNotIn("claude", marked)


class EndShapeTest(unittest.TestCase):
    """The three ways a session stops, which a reading treats differently."""

    def test_an_observed_end_wins_over_everything(self) -> None:
        row = {"ended_at": 1.0, "state": "working", "finished_at": 2.0}
        self.assertEqual("session end observed", mark_abstention._end_shape(row))

    def test_a_working_row_is_running_even_with_a_stale_turn_stop(self) -> None:
        # The producer reads it that way, and a display that said "this stopped"
        # above "now working" invited exactly the wrong mark.
        row = {"ended_at": None, "state": "working", "finished_at": 2.0}
        self.assertEqual("still running", mark_abstention._end_shape(row))

    def test_quiet_with_no_end_is_not_an_end(self) -> None:
        row = {"ended_at": None, "state": "idle", "finished_at": None}
        self.assertEqual("went quiet, no end observed", mark_abstention._end_shape(row))


class TheOutputQuestionIsNotAskedWhereTheRulingFixesItTest(unittest.TestCase):
    """Half of v2's prompts asked the marker to transcribe a constant.

    The Expected Output constraint is only put to the model on a harness that
    publishes a demonstrated work result. Asking about a Claude session is not a
    question, and the unanimity guard then punished the correct answer.
    """

    def test_only_a_work_evidence_harness_is_asked(self) -> None:
        self.assertNotIn("claude", mark_abstention._reading().WORK_EVIDENCE_HARNESSES)
        self.assertIn("pi", mark_abstention._reading().WORK_EVIDENCE_HARNESSES)

    def test_the_guard_ignores_a_column_the_corpus_cannot_vary(self) -> None:
        cases = [{"id": f"c{i}", "asks_output": False} for i in range(10)]
        entries = {f"c{i}": {"goal": "judge", "output": "abstain"} for i in range(10)}
        printed: list[str] = []
        with mock.patch("builtins.print", _collect(printed)):
            mark_abstention._warn_if_unanimous(entries, cases)
        joined = "\n".join(printed)
        self.assertIn("on goal", joined)
        self.assertNotIn("on output", joined)

    def test_the_guard_does_not_fire_on_a_handful_of_marks(self) -> None:
        cases = [{"id": "c1", "asks_output": True}, {"id": "c2", "asks_output": True}]
        entries = {k: {"goal": "judge", "output": "judge"} for k in ("c1", "c2")}
        printed: list[str] = []
        with mock.patch("builtins.print", _collect(printed)):
            mark_abstention._warn_if_unanimous(entries, cases)
        self.assertEqual([], printed)


class ReadingAFileAPersonCanBreakTest(unittest.TestCase):
    """v2 raised a traceback on four ordinary file states.

    The network path was careful and the disk path, which holds the artefact,
    was not.
    """

    def _in_temp(self, body: str) -> str:
        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - must outlive this call
            "w", suffix=".json", delete=False
        )
        handle.write(body)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_a_truncated_file_is_a_message_not_a_traceback(self) -> None:
        with mock.patch("builtins.print"):
            self.assertEqual({}, mark_abstention._load(self._in_temp("{not json")))

    def test_a_json_list_is_refused_rather_than_coerced(self) -> None:
        with mock.patch("builtins.print"):
            self.assertEqual({}, mark_abstention._load(self._in_temp("[1, 2, 3]")))

    def test_an_absent_file_is_simply_empty(self) -> None:
        self.assertEqual({}, mark_abstention._load("/nonexistent/nowhere.json"))

    def test_a_half_written_mark_is_not_a_mark(self) -> None:
        body = {"marks": {"a": {"goal": "judge", "output": "abstain"}, "b": {"goal": "judge"}}}
        self.assertEqual({"a"}, set(mark_abstention._marks(body)))

    def test_marks_that_are_not_a_mapping_are_dropped(self) -> None:
        self.assertEqual({}, mark_abstention._marks({"marks": ["judge"]}))


class WritingIsAtomicTest(unittest.TestCase):
    """v2 truncated in place, so an interrupt lost every mark already given."""

    def test_the_temp_file_is_gone_and_the_mode_is_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "nested", "marks.json")
            mark_abstention._write(path, {"v": 2, "marks": {}})
            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(f"{path}.tmp"))
            self.assertEqual(0o600, os.stat(path).st_mode & 0o777)

    def test_a_rewrite_replaces_rather_than_appends(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "marks.json")
            mark_abstention._write(path, {"marks": {"a": 1}})
            mark_abstention._write(path, {"marks": {"b": 2}})
            with open(path, encoding="utf-8") as handle:
                self.assertEqual({"b": 2}, json.load(handle)["marks"])


class BuildRefusesToProduceAKeyThatVerifiesNothingTest(unittest.TestCase):
    """v2 reported success three times in a row over an empty corpus."""

    def _build(self, payload: Any, *, marks: dict[str, Any] | None = None) -> tuple[int, str]:
        printed: list[str] = []
        with (
            tempfile.TemporaryDirectory() as root,
            mock.patch.object(mark_abstention, "CASES_PATH", os.path.join(root, "cases.json")),
            mock.patch.object(mark_abstention, "MARKS_PATH", os.path.join(root, "marks.json")),
            mock.patch.object(mark_abstention, "_get", lambda *_a, **_k: payload),
            mock.patch("builtins.print", _collect(printed)),
        ):
            if marks:
                mark_abstention._write(os.path.join(root, "marks.json"), {"marks": marks})
            code = mark_abstention.build(4553)
            wrote = os.path.exists(os.path.join(root, "cases.json"))
        self.assertFalse(wrote and code != 0, "a failed build must write nothing")
        return code, "\n".join(printed)

    def test_an_empty_board_writes_nothing_and_fails(self) -> None:
        code, said = self._build({"sessions": []})
        self.assertEqual(1, code)
        self.assertIn("no sessions", said)

    def test_a_rebuild_that_would_orphan_marks_refuses(self) -> None:
        payload = {"sessions": [{"harness": "claude", "sid": "aaa", "project": "p"}]}
        stale = {"deadbeefdeadbeef": {"goal": "judge", "output": "abstain"}}
        code, said = self._build(payload, marks=stale)
        self.assertEqual(1, code)
        self.assertIn("--force", said)


class ADegenerateCorpusIsCalledOutTest(unittest.TestCase):
    """One case differing from twenty is not variation.

    The first version of this check asked only whether the count was non-zero,
    which a 21 case corpus with a single evidence bearing case passed while
    still being twenty near identical screens.
    """

    def _build(self, rows: list[dict[str, Any]], facts: int) -> str:
        printed: list[str] = []
        with (
            tempfile.TemporaryDirectory() as root,
            mock.patch.object(mark_abstention, "CASES_PATH", os.path.join(root, "cases.json")),
            mock.patch.object(mark_abstention, "MARKS_PATH", os.path.join(root, "marks.json")),
            mock.patch.object(mark_abstention, "_get", lambda *_a, **_k: {"sessions": rows}),
            mock.patch.object(
                mark_abstention,
                "_ledger",
                lambda _p, case: {
                    "facts": facts if case["sid"] == "s0" else 0,
                    "citable": facts if case["sid"] == "s0" else 0,
                    "work_results": 0,
                    "reached": True,
                },
            ),
            mock.patch("builtins.print", _collect(printed)),
        ):
            mark_abstention.build(4553)
        return "\n".join(printed)

    def test_one_case_in_twenty_is_still_called_thin(self) -> None:
        # Two end shapes on purpose, so the shapes branch of the warning cannot
        # fire and only the proportion of evidence bearing cases is under test.
        # Without this the assertion passes against a guard that merely checks
        # the count is non-zero, which is the defect being fixed.
        rows: list[dict[str, Any]] = [
            {"harness": "claude", "sid": f"s{i}", "project": "p", "state": "idle", "ended_at": 1}
            for i in range(21)
        ]
        rows[0] = {"harness": "claude", "sid": "s0", "project": "p", "state": "working"}
        said = self._build(rows, facts=13)
        self.assertIn("does not vary", said)


class TheDocstringDoesNotClaimWhatTheCodeLacksTest(unittest.TestCase):
    """This repository's recorded failure mode is a comment that is not so."""

    SOURCE = mark_abstention.__doc__ or ""

    def test_it_does_not_still_claim_the_history_store(self) -> None:
        # v1's source, repudiated by v2's build and left in the module header.
        self.assertNotIn("from the local history store", self.SOURCE)

    def test_the_scorer_contract_is_written_down(self) -> None:
        # A producer handed a session with no stored revision refuses it before
        # reading any evidence, so how a case gets scored cannot be left out.
        self.assertIn("nothing-typed", self.SOURCE)

    def test_no_dead_module_state_survived_the_rewrite(self) -> None:
        for gone in ("HISTORY_PATH", "_entries"):
            self.assertFalse(hasattr(mark_abstention, gone), f"{gone} is dead and still here")


if __name__ == "__main__":
    unittest.main()
