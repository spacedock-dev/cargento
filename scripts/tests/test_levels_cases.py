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
import subprocess
import sys
import tempfile
import time
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


def _git(repo: Path, *args: str) -> str:
    """Git in the throwaway repository, isolated from the operator's hooks and signing."""
    done = subprocess.run(
        [  # noqa: S607 - git on PATH, as the tool itself uses it
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


def a_reading(read_at: float, **criteria: dict[str, Any]) -> dict[str, Any]:
    """A stored reading in the store's own shape, as `annotations._assessment` admits it."""
    return {
        "revision_read": 1,
        "revision_read_at": read_at - 600,
        "window_start": None,
        "read_at": read_at,
        "stamp": "03:10",
        "cutoff": "",
        "scope": "mid-flight",
        "scope_text": "",
        "ended_at_read": None,
        "evidence_through": None,
        "criteria": {
            name: {"cites": [], "detail": "", "clause": "", "why": "", **row}
            for name, row in {"goal": {}, **criteria}.items()
        },
    }


class CaseToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home" / ".cargento"
        self.repo = self.root / "repo"
        (self.repo / "docs" / "drift-levels").mkdir(parents=True)
        _git(self.repo, "init", "-q")
        (self.repo / "README.md").write_text("repo\n", encoding="utf-8")
        _git(self.repo, "add", "README.md")
        _git(self.repo, "commit", "-q", "-m", "init")
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

    def marks(self) -> dict[str, Any]:
        path = self.home / "drift-levels" / "marks.json"
        return dict(json.loads(path.read_text(encoding="utf-8"))["marks"])

    def mark(self, answers: Answers) -> int:
        return levels_cases.mark(
            home=str(self.home),
            digest_path=str(self.digest_path),
            results_path=str(self.results_path),
            repo_root=str(self.repo),
            ask=answers,
            say=self.say,
        )

    def commit_digest(self) -> None:
        _git(self.repo, "add", str(self.digest_path))
        _git(self.repo, "commit", "-q", "-m", "marks digest")

    def attach(self, readings: dict[str, Any]) -> int:
        path = self.home / "drift-levels" / "readings-spec.json"
        path.write_text(json.dumps({"v": 1, "readings": readings}), encoding="utf-8")
        return levels_cases.attach_readings(
            path,
            home=str(self.home),
            repo_root=str(self.repo),
            digest_path=str(self.digest_path),
            now=time.time() + 120,
            say=self.say,
        )

    def score(self) -> int:
        return levels_cases.score(
            home=str(self.home),
            repo_root=str(self.repo),
            digest_path=str(self.digest_path),
            results_path=str(self.results_path),
            now=time.time() + 300,
            say=self.say,
        )

    def marked(self, *replies: str) -> str:
        """Build one failed-check case, mark it, commit the digest; the case id."""
        self.build(self.case())
        self.mark(Answers(*replies))
        self.commit_digest()
        return str(self.cases()[0]["id"])

    def results(self) -> dict[str, Any]:
        return dict(json.loads(self.results_path.read_text(encoding="utf-8")))


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

    def test_the_working_directory_is_frozen_for_the_folder_rule(self) -> None:
        self.build(self.case())
        self.assertEqual(self.cases()[0]["cwd"], self.cwd)

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

    def test_a_reading_in_the_spec_is_refused_because_marks_come_first(self) -> None:
        # T1: a case built with its reading lets the reading shape the key.
        self.assertEqual(self.build(self.case(reading=a_reading(1.0))), 1)
        self.assertFalse((self.home / "drift-levels" / "cases.json").exists())

    def test_the_same_session_under_two_kinds_is_two_cases(self) -> None:
        self.build(self.case(), self.case(kind="intent-names-no-folder"))
        self.assertEqual(len({c["id"] for c in self.cases()}), 2)

    def test_a_rebuild_that_would_orphan_marks_is_refused(self) -> None:
        self.build(self.case())
        self.mark(Answers("h", "h"))
        self.assertEqual(self.build(self.case(kind="other")), 1)


class MarkTest(CaseToolTestCase):
    def test_the_tool_refuses_to_guess_and_has_no_default(self) -> None:
        self.build(self.case())
        answers = Answers("", "maybe", "h", "", "h")
        self.assertEqual(self.mark(answers), 0)
        # Replies that were not a level were asked again, not defaulted.
        self.assertEqual(len(answers.prompts), 5)
        self.assertEqual(list(self.marks().values()), [{"live": "high", "analysis": "high"}])

    def test_stopping_keeps_nothing_it_was_not_told(self) -> None:
        self.build(self.case(), self.case(kind="other", until=None))
        self.mark(Answers("h", "h", "q"))
        self.assertEqual(len(self.marks()), 1)

    def test_both_levels_are_asked_for_every_case_with_an_outcome_line(self) -> None:
        # T1: the analysis mark is asked from the evidence and intent, with no reading in hand.
        self.build(self.case())
        answers = Answers("h", "x")
        self.mark(answers)
        self.assertEqual(list(self.marks().values()), [{"live": "high", "analysis": "not_enough"}])
        self.assertEqual(len(answers.prompts), 2)

    def test_no_outcome_line_means_no_analysis_question(self) -> None:
        intent = {"saved": True, "goal": GOAL, "lines": []}
        self.build(self.case(intent=intent))
        answers = Answers("x")
        self.mark(answers)
        self.assertEqual(list(self.marks().values()), [{"live": "not_enough", "analysis": None}])
        self.assertEqual(len(answers.prompts), 1)

    def test_the_marking_screen_shows_no_reading_or_model_output(self) -> None:
        self.build(self.case())
        self.mark(Answers("h", "h"))
        screen = "\n".join(self.out)
        for word in ("READING", "departure", "consistent", "not verifiable"):
            self.assertNotIn(word, screen)

    def test_the_marks_and_their_sha256_are_written_and_the_digest_is_committable(self) -> None:
        self.build(self.case())
        self.mark(Answers("h", "h"))
        raw = (self.home / "drift-levels" / "marks.json").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(
            (self.home / "drift-levels" / "marks.sha256").read_text(encoding="utf-8").split()[0],
            digest,
        )
        committed = json.loads(self.digest_path.read_text(encoding="utf-8"))
        self.assertEqual(committed["marks_digest"], digest)
        self.assertNotIn(SID[:8], json.dumps(committed))

    def test_marks_for_a_different_case_set_are_refused(self) -> None:
        self.build(self.case())
        self.mark(Answers("h", "h"))
        cases_path = self.home / "drift-levels" / "cases.json"
        body = json.loads(cases_path.read_text(encoding="utf-8"))
        body["cases"][0]["unsettled_directions"] = 3
        cases_path.write_text(json.dumps(body), encoding="utf-8")
        self.assertEqual(self.mark(Answers("m", "m")), 1)

    def test_marking_is_refused_once_any_result_exists(self) -> None:
        # T2: re-marking after seeing a result is agreement, not a mark.
        self.build(self.case(), self.case(kind="other", until=None))
        self.mark(Answers("h", "h", "q"))
        self.results_path.write_text("{}", encoding="utf-8")
        self.assertEqual(self.mark(Answers("e", "e")), 1)
        self.assertEqual(len(self.marks()), 1)


class RemarkAfterScoreTest(CaseToolTestCase):
    """V2: a result seen is a key closed, however the files that showed it were removed."""

    def scored(self) -> None:
        self.marked("h", "h")
        self.assertEqual(self.score(), 0)

    def forget_locally(self) -> None:
        self.results_path.unlink()
        (self.home / "drift-levels" / "marks.json").unlink()

    def test_deleting_the_result_and_the_marks_does_not_reopen_marking(self) -> None:
        self.scored()
        self.forget_locally()
        self.assertEqual(self.mark(Answers("e", "e")), 1)
        self.assertFalse((self.home / "drift-levels" / "marks.json").exists())

    def test_the_scored_marker_is_local_and_keyed_by_the_case_set(self) -> None:
        self.scored()
        markers = list((self.home / "drift-levels").glob("scored-*.json"))
        self.assertEqual(len(markers), 1)
        body = json.loads((self.home / "drift-levels" / "cases.json").read_text("utf-8"))
        self.assertIn(levels_cases.digest(body), markers[0].name)
        self.assertFalse(list(self.repo.rglob("scored-*.json")))

    def test_deleting_the_marker_too_is_caught_by_the_committed_digest(self) -> None:
        self.scored()
        self.forget_locally()
        for marker in (self.home / "drift-levels").glob("scored-*.json"):
            marker.unlink()
        self.assertEqual(self.mark(Answers("e", "e")), 1)

    def test_a_result_once_committed_and_removed_still_closes_marking(self) -> None:
        self.scored()
        _git(self.repo, "add", str(self.results_path))
        _git(self.repo, "commit", "-q", "-m", "results")
        _git(self.repo, "rm", "-q", str(self.results_path), str(self.digest_path))
        _git(self.repo, "commit", "-q", "-m", "gone")
        (self.home / "drift-levels" / "marks.json").unlink()
        for marker in (self.home / "drift-levels").glob("scored-*.json"):
            marker.unlink()
        self.assertEqual(self.mark(Answers("e", "e")), 1)

    def test_the_local_marker_holds_when_history_was_rewritten(self) -> None:
        self.scored()
        _git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        _git(self.repo, "reflog", "expire", "--expire=now", "--all")
        self.results_path.unlink(missing_ok=True)
        (self.home / "drift-levels" / "marks.json").unlink()
        self.assertEqual(self.mark(Answers("e", "e")), 1)

    def test_a_committed_result_with_no_case_digest_closes_marking(self) -> None:
        self.build(self.case())
        self.results_path.write_text('{"v": 1}\n', encoding="utf-8")
        _git(self.repo, "add", str(self.results_path))
        _git(self.repo, "commit", "-q", "-m", "a result from before the case digest")
        _git(self.repo, "rm", "-q", str(self.results_path))
        _git(self.repo, "commit", "-q", "-m", "gone")
        self.assertEqual(self.mark(Answers("h", "h")), 1)

    def test_an_earlier_committed_digest_for_this_case_set_closes_marking(self) -> None:
        self.build(self.case(), self.case(kind="other", until=None))
        self.mark(Answers("h", "h", "q"))
        self.commit_digest()
        self.assertEqual(self.mark(Answers("m", "m")), 1)

    def test_another_case_set_may_still_be_marked(self) -> None:
        self.scored()
        (self.home / "drift-levels" / "marks.json").unlink()
        self.results_path.unlink()
        self.build(self.case(kind="other", until=None))
        self.assertEqual(self.mark(Answers("m", "m")), 0)


class CommittedDigestTest(CaseToolTestCase):
    def test_git_is_handed_the_digest_path_with_forward_slashes(self) -> None:
        # What `HEAD:<path>` needs on Windows, where relpath answers with backslashes.
        relative = levels_cases._repo_path(str(self.digest_path), str(self.repo))
        self.assertEqual(relative, "docs/drift-levels/marks-digest.json")

    def test_a_digest_committed_with_crlf_is_the_committed_digest(self) -> None:
        # Windows with core.autocrlf off commits the bytes as written; the
        # working copy is read in text mode, so only a line-wise compare agrees.
        self.marked("h", "h")
        self.digest_path.write_bytes(self.digest_path.read_bytes().replace(b"\n", b"\r\n"))
        _git(self.repo, "-c", "core.autocrlf=false", "add", str(self.digest_path))
        _git(self.repo, "commit", "-q", "-m", "marks digest, CRLF")
        blob = _git(self.repo, "cat-file", "-s", "HEAD:docs/drift-levels/marks-digest.json")
        self.assertEqual(int(blob), self.digest_path.stat().st_size)  # the CRLF bytes, kept
        committed = levels_cases.committed_digest(str(self.repo), str(self.digest_path))
        self.assertIsInstance(committed, levels_cases.Committed)


class AttachReadingsTest(CaseToolTestCase):
    def test_v4_a_reading_for_a_case_not_in_the_committed_marks_is_refused(self) -> None:
        self.build(self.case(), self.case(kind="other", until=None))
        self.mark(Answers("h", "h", "q"))
        self.commit_digest()
        unmarked = self.cases()[1]["id"]
        body = a_reading(time.time() + 60, line_1={"result": "departure"})
        self.assertEqual(self.attach({unmarked: body}), 1)
        self.assertFalse((self.home / "drift-levels" / "readings.json").exists())

    def test_a_reading_attaches_after_the_committed_digest(self) -> None:
        case_id = self.marked("h", "h")
        body = a_reading(time.time() + 60, line_1={"result": "departure"})
        self.assertEqual(self.attach({case_id: body}), 0)
        saved = json.loads((self.home / "drift-levels" / "readings.json").read_text("utf-8"))
        committed = json.loads(self.digest_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["marks_digest"], committed["marks_digest"])
        self.assertEqual(saved["digest_commit"], _git(self.repo, "rev-parse", "HEAD").strip())
        self.assertIn(case_id, saved["readings"])

    def test_nothing_attaches_before_the_digest_is_committed(self) -> None:
        self.build(self.case())
        self.mark(Answers("h", "h"))
        case_id = self.cases()[0]["id"]
        body = a_reading(time.time() + 60, line_1={"result": "departure"})
        self.assertEqual(self.attach({case_id: body}), 1)
        self.assertFalse((self.home / "drift-levels" / "readings.json").exists())

    def test_a_reading_made_before_the_digest_was_committed_is_refused(self) -> None:
        case_id = self.marked("h", "h")
        body = a_reading(time.time() - 3600, line_1={"result": "departure"})
        self.assertEqual(self.attach({case_id: body}), 1)

    def test_a_reading_the_store_would_refuse_is_refused(self) -> None:
        case_id = self.marked("h", "h")
        body = a_reading(time.time() + 60, line_1={"result": "departure"})
        body["surprise"] = "field"
        self.assertEqual(self.attach({case_id: body}), 1)

    def test_a_reading_for_an_unknown_case_is_refused(self) -> None:
        self.marked("h", "h")
        body = a_reading(time.time() + 60, line_1={"result": "departure"})
        self.assertEqual(self.attach({"0" * 16: body}), 1)


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
    def test_a_case_matching_its_mark_passes_and_names_the_digest_commit(self) -> None:
        case_id = self.marked("h", "h")
        self.attach({case_id: a_reading(time.time() + 60, line_1={"result": "departure"})})
        self.assertEqual(self.score(), 0)
        body = self.results()
        self.assertEqual(body["verdict"], levels_cases.VERDICT_PASSED)
        self.assertEqual(body["digest_commit"], _git(self.repo, "rev-parse", "HEAD").strip())
        row = body["cases"][case_id]
        self.assertEqual(row["live"]["level"], "high")
        self.assertEqual(row["live"]["outcome"], levels_cases.MATCH)
        self.assertEqual(row["analysis"]["level"], "high")
        self.assertIn("failed-check", row["live"]["reasons"])

    def test_a_case_marked_higher_than_it_scores_fails(self) -> None:
        self.build(self.case(until=None, kind="other"))
        self.mark(Answers("e", "e"))
        self.commit_digest()
        self.assertEqual(self.score(), 1)
        self.assertEqual(self.results()["verdict"], levels_cases.VERDICT_FAILED)

    def test_an_analysis_mark_with_no_reading_attached_is_not_scored(self) -> None:
        case_id = self.marked("h", "h")
        self.assertEqual(self.score(), 0)
        self.assertEqual(self.results()["cases"][case_id]["analysis"], None)
        self.assertEqual(self.results()["counts"]["no_reading"], 1)

    def test_marks_that_moved_since_the_committed_digest_write_nothing(self) -> None:
        self.marked("h", "h")
        marks_path = self.home / "drift-levels" / "marks.json"
        body = json.loads(marks_path.read_text(encoding="utf-8"))
        marks_path.write_text(json.dumps(body, indent=4), encoding="utf-8")
        self.assertEqual(self.score(), 1)
        self.assertFalse(self.results_path.exists())

    def test_an_uncommitted_digest_refuses_the_score(self) -> None:
        # T2: the working copy the marker rewrites is not the committed digest.
        self.build(self.case())
        self.mark(Answers("h", "h"))
        self.assertEqual(self.score(), 1)
        self.assertFalse(self.results_path.exists())

    def test_a_working_copy_that_differs_from_the_commit_refuses_the_score(self) -> None:
        self.marked("h", "h")
        self.digest_path.write_text('{"marks_digest": "0"}\n', encoding="utf-8")
        self.assertEqual(self.score(), 1)
        self.assertFalse(self.results_path.exists())

    def test_an_unmarked_case_refuses_the_score_and_writes_nothing(self) -> None:
        # T3: a level written for an unmarked case can be read and then marked.
        self.build(self.case(), self.case(kind="other", until=None))
        self.mark(Answers("h", "h", "q"))
        self.commit_digest()
        self.assertEqual(self.score(), 1)
        self.assertFalse(self.results_path.exists())

    def test_an_analysis_mark_outside_the_closed_set_is_not_a_mark(self) -> None:
        # T4
        self.build(self.case())
        self.mark(Answers("h", "h"))
        marks_path = self.home / "drift-levels" / "marks.json"
        body = json.loads(marks_path.read_text(encoding="utf-8"))
        (key,) = body["marks"]
        body["marks"][key]["analysis"] = "SESSION TEXT"
        marks_path.write_text(json.dumps(body), encoding="utf-8")
        levels_cases._publish_digest(
            levels_cases._paths(str(self.home)),
            str(self.digest_path),
            1,
            1,
            cases_digest=body["cases_digest"],
        )
        self.commit_digest()
        self.assertEqual(self.score(), 1)
        self.assertFalse(self.results_path.exists())

    def test_a_reading_stored_in_the_case_file_is_refused(self) -> None:
        case_id = self.marked("h", "h")
        cases_path = self.home / "drift-levels" / "cases.json"
        body = json.loads(cases_path.read_text(encoding="utf-8"))
        body["cases"][0]["reading"] = a_reading(time.time() + 60, line_1={"result": "departure"})
        cases_path.write_text(json.dumps(body), encoding="utf-8")
        # Editing the case file also unbinds the marks, so this is refused before it is read.
        self.assertEqual(self.score(), 1)
        self.assertFalse(self.results_path.exists())
        committed = levels_cases.committed_digest(str(self.repo), str(self.digest_path))
        assert isinstance(committed, levels_cases.Committed)
        got = levels_cases._reading_for(body["cases"][0], {}, committed, None)
        self.assertEqual(got, (None, "reading-in-cases"))
        del case_id

    def test_a_reading_attached_under_another_digest_is_refused(self) -> None:
        case_id = self.marked("h", "h")
        self.attach({case_id: a_reading(time.time() + 60, line_1={"result": "departure"})})
        path = self.home / "drift-levels" / "readings.json"
        body = json.loads(path.read_text(encoding="utf-8"))
        body["marks_digest"] = "f" * 64
        path.write_text(json.dumps(body), encoding="utf-8")
        self.assertEqual(self.score(), 1)
        row = self.results()["cases"][case_id]
        self.assertEqual(row["analysis"]["outcome"], "refused:other-digest")

    def test_a_reading_stamped_with_another_digest_commit_is_refused(self) -> None:
        case_id = self.marked("h", "h")
        self.attach({case_id: a_reading(time.time() + 60, line_1={"result": "departure"})})
        path = self.home / "drift-levels" / "readings.json"
        body = json.loads(path.read_text(encoding="utf-8"))
        body["digest_commit"] = "0" * 40
        path.write_text(json.dumps(body), encoding="utf-8")
        self.assertEqual(self.score(), 1)
        row = self.results()["cases"][case_id]
        self.assertEqual(row["analysis"]["outcome"], "refused:other-digest")

    def test_the_results_hold_expectations_and_results_only(self) -> None:
        case_id = self.marked("h", "h")
        body = a_reading(time.time() + 60, line_1={"result": "departure", "detail": "MODEL PROSE"})
        self.attach({case_id: body})
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
        self.assertIn(case_id, raw)


if __name__ == "__main__":
    unittest.main()
