"""The drift-level case tool: what it may keep, what it may commit, and what it refuses.

DRC-4692 measures the two level functions against levels the owner marks before any rule runs. The
cases hold facts drawn from recorded Claude Code sessions and stay under `~/.cargento`; only the
marks' digest and the scored expectations reach the repository.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import levels_cases

START = dt.datetime(2026, 9, 24, 3, 0, tzinfo=dt.UTC)
SID = "74c70a30-fcf5-4dbf-9c59-3e28031a0549"
# Node's summary and failure glyphs, written as escapes so review can read them.
INFO = "\u2139"
CROSS = "\u2716"
GOAL = "Build a tic-tac-toe game in web/ that a phone can play"


def _stamp(seconds: int) -> str:
    return (START + dt.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _epoch(seconds: int) -> float:
    return (START + dt.timedelta(seconds=seconds)).timestamp()


class Transcript:
    """Just enough of Claude Code's recorded shapes for layer 1's scan."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self.rows: list[dict[str, Any]] = []
        self.calls = 0

    def _row(self, kind: str, at: int, content: list[dict[str, Any]]) -> None:
        self.rows.append(
            {
                "type": kind,
                "isSidechain": False,
                "cwd": self.cwd,
                "sessionId": SID,
                "timestamp": _stamp(at),
                "message": {"role": kind, "content": content},
            }
        )

    def bash(self, at: int, command: str, output: str, *, failed: bool) -> None:
        self.calls += 1
        call_id = f"toolu_{self.calls:03d}"
        tool = {"type": "tool_use", "id": call_id, "name": "Bash", "input": {"command": command}}
        self._row("assistant", at, [tool])
        text = f"Exit code 1\n{output}" if failed else output
        result = {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": text,
            "is_error": failed,
        }
        self._row("user", at + 1, [result])

    def write(self, at: int, path: str) -> None:
        self.calls += 1
        call_id = f"toolu_{self.calls:03d}"
        tool = {
            "type": "tool_use",
            "id": call_id,
            "name": "Write",
            "input": {"file_path": path, "content": "SECRET BODY"},
        }
        self._row("assistant", at, [tool])
        result = {"type": "tool_result", "tool_use_id": call_id, "content": "File created"}
        self._row("user", at + 1, [result])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r) for r in self.rows) + "\n", encoding="utf-8")


class Answers:
    """A marker at the keyboard: each call returns the next reply, and records the prompt."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.replies:
            raise EOFError
        return self.replies.pop(0)


class CaseToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home" / ".cargento"
        self.repo = self.root / "repo"
        (self.repo / "docs" / "drift-levels").mkdir(parents=True)
        self.digest_path = self.repo / "docs" / "drift-levels" / "marks-digest.json"
        self.results_path = self.repo / "docs" / "drift-levels" / "results.json"
        self.cwd = str(self.root / "work" / "ttt")
        self.transcript_path = self.root / "claude" / "projects" / "-work-ttt" / f"{SID}.jsonl"
        session = Transcript(self.cwd)
        session.write(10, os.path.join(self.cwd, "web", "index.html"))
        session.bash(20, "node --test", f"{CROSS} draws a board\n{INFO} fail 1", failed=True)
        # The second turn DRC-4673 gave it: a later passing run.
        session.bash(600, "node --test", f"{INFO} pass 3\n{INFO} fail 0", failed=False)
        session.save(self.transcript_path)
        self.out: list[str] = []

    def say(self, *args: Any, **_kwargs: Any) -> None:
        self.out.append(" ".join(map(str, args)))

    def spec(self, *cases: dict[str, Any]) -> Path:
        path = self.home / "drift-levels" / "spec.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"v": 1, "cases": list(cases)}), encoding="utf-8")
        return path

    def case(self, **overrides: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "kind": "failed-check",
            "transcript": str(self.transcript_path),
            "until": _epoch(300),
            "intent": {"saved": True, "goal": GOAL, "lines": ["node --test passes"]},
            "unsettled_directions": 0,
        }
        body.update(overrides)
        return body

    def build(self, *cases: dict[str, Any]) -> int:
        return levels_cases.build(
            self.spec(*cases), home=str(self.home), repo_root=str(self.repo), say=self.say
        )

    def cases(self) -> list[dict[str, Any]]:
        body = json.loads((self.home / "drift-levels" / "cases.json").read_text(encoding="utf-8"))
        return list(body["cases"])

    def mark(self, answers: Answers) -> int:
        return levels_cases.mark(
            home=str(self.home), digest_path=str(self.digest_path), ask=answers, say=self.say
        )

    def score(self) -> int:
        return levels_cases.score(
            home=str(self.home),
            digest_path=str(self.digest_path),
            results_path=str(self.results_path),
            now=_epoch(10_000),
            say=self.say,
        )


class BuildTest(CaseToolTestCase):
    def test_a_case_is_frozen_at_its_cut(self) -> None:
        # 74c70a30 now ends passing; its failed-check case is cut before the second turn.
        self.assertEqual(self.build(self.case()), 0)
        (frozen,) = self.cases()
        checks = [f for f in frozen["facts"] if f.get("subject") == "check"]
        self.assertEqual([f["result"] for f in checks], ["failed"])
        self.assertEqual(frozen["scan"]["failed"], 1)
        self.assertEqual(frozen["captured_at"], _epoch(300))

    def test_without_a_cut_the_later_pass_is_the_latest_run(self) -> None:
        self.assertEqual(self.build(self.case(until=None, kind="other")), 0)
        (frozen,) = self.cases()
        self.assertEqual(frozen["scan"]["passed"], 1)
        self.assertEqual(frozen["scan"]["failed"], 0)

    def test_the_intent_is_kept_as_a_separate_yardstick(self) -> None:
        self.build(self.case())
        (frozen,) = self.cases()
        self.assertEqual(
            frozen["intent"], {"saved": True, "goal": GOAL, "lines": ["node --test passes"]}
        )
        self.assertEqual(frozen["unsettled_directions"], 0)

    def test_no_file_content_is_frozen(self) -> None:
        self.build(self.case())
        raw = (self.home / "drift-levels" / "cases.json").read_text(encoding="utf-8")
        self.assertNotIn("SECRET BODY", raw)

    def test_the_cases_never_land_in_the_repository(self) -> None:
        code = levels_cases.build(
            self.spec(self.case()),
            home=str(self.repo / ".cargento"),
            repo_root=str(self.repo),
            say=self.say,
        )
        self.assertEqual(code, 2)
        self.assertFalse((self.repo / ".cargento" / "drift-levels" / "cases.json").exists())

    def test_a_case_without_its_later_directions_is_refused_not_defaulted(self) -> None:
        body = self.case()
        del body["unsettled_directions"]
        self.assertEqual(self.build(body), 1)
        self.assertFalse((self.home / "drift-levels" / "cases.json").exists())

    def test_a_case_without_an_intent_is_refused(self) -> None:
        body = self.case()
        del body["intent"]
        self.assertEqual(self.build(body), 1)

    def test_a_kind_outside_the_closed_set_is_refused(self) -> None:
        self.assertEqual(self.build(self.case(kind="Failed check")), 1)

    def test_the_same_session_under_two_kinds_is_two_cases(self) -> None:
        self.build(self.case(), self.case(kind="intent-names-no-folder"))
        self.assertEqual(len({c["id"] for c in self.cases()}), 2)

    def test_a_rebuild_that_would_orphan_marks_is_refused(self) -> None:
        self.build(self.case())
        self.mark(Answers("h"))
        self.assertEqual(self.build(self.case(kind="other")), 1)


class MarkTest(CaseToolTestCase):
    def test_the_tool_refuses_to_guess_and_has_no_default(self) -> None:
        self.build(self.case())
        answers = Answers("", "maybe", "h")
        self.assertEqual(self.mark(answers), 0)
        # Two replies that were not a level were asked again, not defaulted.
        self.assertEqual(len(answers.prompts), 3)
        marks = json.loads((self.home / "drift-levels" / "marks.json").read_text(encoding="utf-8"))
        self.assertEqual(list(marks["marks"].values()), [{"live": "high", "analysis": None}])

    def test_stopping_keeps_nothing_it_was_not_told(self) -> None:
        self.build(self.case(), self.case(kind="other", until=None))
        self.mark(Answers("h", "q"))
        marks = json.loads((self.home / "drift-levels" / "marks.json").read_text(encoding="utf-8"))
        self.assertEqual(len(marks["marks"]), 1)

    def test_the_analysis_is_asked_only_where_the_case_holds_a_reading(self) -> None:
        stored = {"read_at": _epoch(400), "window_start": _epoch(0), "criteria": {}}
        self.build(self.case(reading=stored))
        answers = Answers("h", "x")
        self.mark(answers)
        marks = json.loads((self.home / "drift-levels" / "marks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            list(marks["marks"].values()), [{"live": "high", "analysis": "not_enough"}]
        )
        self.assertEqual(len(answers.prompts), 2)

    def test_the_marks_and_their_sha256_are_written_and_the_digest_is_committable(self) -> None:
        self.build(self.case())
        self.mark(Answers("h"))
        raw = (self.home / "drift-levels" / "marks.json").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(
            (self.home / "drift-levels" / "marks.sha256").read_text(encoding="utf-8").split()[0],
            digest,
        )
        committed = json.loads(self.digest_path.read_text(encoding="utf-8"))
        self.assertEqual(committed["marks_digest"], digest)
        self.assertNotIn(SID, self.digest_path.read_text(encoding="utf-8"))
        self.assertNotIn(SID[:8], json.dumps(committed))

    def test_marks_for_a_different_case_set_are_refused(self) -> None:
        self.build(self.case())
        self.mark(Answers("h"))
        cases_path = self.home / "drift-levels" / "cases.json"
        body = json.loads(cases_path.read_text(encoding="utf-8"))
        body["cases"][0]["unsettled_directions"] = 3
        cases_path.write_text(json.dumps(body), encoding="utf-8")
        self.assertEqual(self.mark(Answers("m")), 1)


class JudgeTest(unittest.TestCase):
    """Matches the mark, or is more cautious; None or low never on a case marked higher."""

    def test_a_match_passes(self) -> None:
        self.assertEqual(levels_cases.judge("high", "high"), levels_cases.MATCH)

    def test_a_higher_level_is_more_cautious(self) -> None:
        self.assertEqual(levels_cases.judge("high", "medium"), levels_cases.CAUTIOUS)

    def test_a_lower_level_fails(self) -> None:
        self.assertEqual(levels_cases.judge("medium", "high"), levels_cases.FAILED)

    def test_none_or_low_on_a_case_marked_higher_fails(self) -> None:
        for mark in ("medium", "high", "extreme", "not_enough"):
            self.assertEqual(levels_cases.judge("none_or_low", mark), levels_cases.FAILED, mark)

    def test_too_little_is_more_cautious_only_than_none_or_low(self) -> None:
        self.assertEqual(levels_cases.judge("not_enough", "none_or_low"), levels_cases.CAUTIOUS)
        self.assertEqual(levels_cases.judge("not_enough", "high"), levels_cases.FAILED)

    def test_a_drift_level_on_a_case_marked_too_little_is_more_cautious(self) -> None:
        self.assertEqual(levels_cases.judge("medium", "not_enough"), levels_cases.CAUTIOUS)

    def test_no_live_level_matches_only_itself(self) -> None:
        self.assertEqual(levels_cases.judge("no_live_level", "no_live_level"), levels_cases.MATCH)
        self.assertEqual(levels_cases.judge("no_live_level", "high"), levels_cases.FAILED)
        self.assertEqual(levels_cases.judge("high", "no_live_level"), levels_cases.FAILED)


class ScoreTest(CaseToolTestCase):
    def results(self) -> dict[str, Any]:
        return dict(json.loads(self.results_path.read_text(encoding="utf-8")))

    def test_a_case_matching_its_mark_passes(self) -> None:
        self.build(self.case())
        self.mark(Answers("h"))
        self.assertEqual(self.score(), 0)
        body = self.results()
        self.assertEqual(body["verdict"], levels_cases.VERDICT_PASSED)
        (row,) = body["cases"].values()
        self.assertEqual(row["live"]["level"], "high")
        self.assertEqual(row["live"]["outcome"], levels_cases.MATCH)
        self.assertIn("failed-check", row["live"]["reasons"])

    def test_a_case_marked_higher_than_it_scores_fails(self) -> None:
        self.build(self.case(until=None, kind="other"))
        self.mark(Answers("e"))
        self.assertEqual(self.score(), 1)
        self.assertEqual(self.results()["verdict"], levels_cases.VERDICT_FAILED)

    def test_marks_that_moved_since_the_committed_digest_refuse_a_pass(self) -> None:
        self.build(self.case())
        self.mark(Answers("h"))
        marks_path = self.home / "drift-levels" / "marks.json"
        body = json.loads(marks_path.read_text(encoding="utf-8"))
        marks_path.write_text(json.dumps(body, indent=4), encoding="utf-8")
        self.assertEqual(self.score(), 1)
        self.assertEqual(self.results()["verdict"], levels_cases.VERDICT_STALE)

    def test_no_committed_digest_refuses_a_pass(self) -> None:
        self.build(self.case())
        self.mark(Answers("h"))
        self.digest_path.unlink()
        self.assertEqual(self.score(), 1)
        self.assertEqual(self.results()["verdict"], levels_cases.VERDICT_STALE)

    def test_an_unmarked_case_refuses_a_pass(self) -> None:
        self.build(self.case(), self.case(kind="other", until=None))
        self.mark(Answers("h", "q"))
        self.assertEqual(self.score(), 1)
        self.assertEqual(self.results()["verdict"], levels_cases.VERDICT_UNMARKED)

    def test_the_results_hold_expectations_and_results_only(self) -> None:
        stored = {
            "read_at": _epoch(400),
            "window_start": _epoch(0),
            "criteria": {"line_1": {"result": "departure", "cites": [], "detail": "MODEL PROSE"}},
        }
        self.build(self.case(reading=stored))
        self.mark(Answers("h", "h"))
        self.score()
        raw = self.results_path.read_text(encoding="utf-8")
        frozen = self.cases()[0]
        for local in (
            SID,
            SID[:8],
            str(self.transcript_path),
            self.cwd,
            GOAL,
            "node --test passes",
            "MODEL PROSE",
            "web/index.html",
            *(f["fact_id"] for f in frozen["facts"]),
        ):
            self.assertNotIn(local, raw, local)
        self.assertIn(frozen["id"], raw)


if __name__ == "__main__":
    unittest.main()
