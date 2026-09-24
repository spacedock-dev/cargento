"""Qualifying the Claude Code reading producer (DRC-4666), with no model spend.

Every model here is a fake that records its prompts, so a test can say what
the producer was given and prove what was not spent. Format 5 is the packet
this qualification scores: a per-case intent with several outcome lines, and a
Claude Code case's checks frozen as they stood at the capture.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import abstention_ledger
import mark_abstention
import score_abstention

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "cargento" / "skills" / "cargento"
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

from cargento_runtime import observer, reading  # noqa: E402

CLAUDE_SID = "c1a2b3c4-SECRET-SID"
CODEX_SID = "d5e6f7a8-SECRET-SID"
GOAL = "GOAL_WORDS make the computer win when it can"
LINE_ONE = "LINE_ONE_WORDS the ai tests pass"
LINE_TWO = "LINE_TWO_WORDS the toggle switches the theme"
TAIL = "TAIL_WORDS 29 passed"
PROSE = "MODEL_PROSE the agent did something else"


class _Config:
    reading_settle_sec = 8.0
    annotation_text_cap_chars = 240


class _Model:
    """A reply per call, in order, and every prompt it was asked."""

    def __init__(self, *replies: tuple[str, str]) -> None:
        self.replies = list(replies) or [("{}", "ok")]
        self.prompts: list[str] = []

    def __call__(self, prompt: str, **_kw: Any) -> tuple[str, str]:
        self.prompts.append(prompt)
        return self.replies[min(len(self.prompts), len(self.replies)) - 1]


def _reply(**tokens: tuple[str, tuple[int, ...]]) -> str:
    return json.dumps(
        {
            name: {"result": token, "cites": list(cites), "detail": PROSE}
            for name, (token, cites) in tokens.items()
        }
    )


def _fact(fid: str, *, sid: str, harness: str, at: float, **fields: Any) -> dict[str, Any]:
    return {
        "fact_id": fid,
        "type": "result",
        "summary": "I finished the change",
        "at": at,
        "evidence": {"source": "session assistant/tool exchange", "confidence": "exact"},
        "source_session": {"harness": harness, "sid": sid},
        **fields,
    }


def _check(
    fid: str, *, at: float, result: str = "passed", record: str = "toolu_9"
) -> dict[str, Any]:
    return _fact(
        fid,
        sid=CLAUDE_SID,
        harness="claude",
        at=at,
        type="tool_report",
        subject="check",
        result=result,
        result_source="flag",
        summary="node --test tests/ai.test.js",
        evidence={"source": "Claude Bash call and paired result", "confidence": "exact"},
        branch={"harness": "claude", "sid": CLAUDE_SID, "record_id": record},
    )


def _claude_case() -> dict[str, Any]:
    return {
        "id": mark_abstention._case_id("claude", CLAUDE_SID),
        "harness": "claude",
        "sid": CLAUDE_SID,
        "origin": "recorded",
        "title": "TITLE_WORDS",
        "captured_at": 110.0,
        # A turn stop at 100 s, captured after the settle.
        "row_snapshot": {
            "harness": "claude",
            "sid": CLAUDE_SID,
            "state": "idle",
            "finished_at": 100.0,
            "ended_at": None,
        },
        "producer_facts": [
            _fact("a1", sid=CLAUDE_SID, harness="claude", at=80.0),
            _check("k1", at=90.0),
        ],
        "intent": {
            "goal": GOAL,
            "lines": [{"text": LINE_ONE, "source": "typed"}, {"text": LINE_TWO, "source": "typed"}],
        },
        "tool_output": {"tails": {"toolu_9": TAIL}, "changed_after": []},
    }


def _codex_case() -> dict[str, Any]:
    # A recorded history `working` observation, frozen at its last activity.
    return {
        "id": mark_abstention._case_id("codex", CODEX_SID),
        "harness": "codex",
        "sid": CODEX_SID,
        "origin": "recorded",
        "captured_at": 200.0,
        "row_snapshot": {"harness": "codex", "sid": CODEX_SID, "state": "working"},
        "producer_facts": [_fact("x1", sid=CODEX_SID, harness="codex", at=150.0)],
        "intent": {"goal": GOAL, "lines": [{"text": LINE_ONE}]},
    }


BINDING = {
    "producer": "claude",
    "model": observer.CLAUDE_READING_MODEL,
    "argv_digest": "ab" * 32,
    "destination": "Anthropic",
    "binary": "~/.local/share/claude/versions/2.1.281",
    "cli_version": "2.1.281 (Claude Code)",
}

_LEDGER_PATCH: Any = None


def setUpModule() -> None:
    """Never the real ledger: every test here charges a throwaway one."""
    global _LEDGER_PATCH  # noqa: PLW0603
    folder = tempfile.mkdtemp()
    _LEDGER_PATCH = mock.patch.object(
        abstention_ledger, "LEDGER_PATH", str(Path(folder, "never-real.json"))
    )
    _LEDGER_PATCH.start()


def tearDownModule() -> None:
    _LEDGER_PATCH.stop()


class _Packet(unittest.TestCase):
    """A format 5 packet on disk in a temp home, marked, and a way to score it."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.cases = [_claude_case()]
        self.marks: dict[str, dict[str, str]] = {
            self.cases[0]["id"]: {"goal": "judge", "line_1": "judge", "line_2": "abstain"}
        }
        self.rubric: dict[str, Any] = {}
        self.result = self.home / "local.json"
        self.summary = self.home / "claude-results.json"
        self.ledger_path = self.home / "spend.json"

    def body(self) -> dict[str, Any]:
        return {"v": 5, "cases": self.cases}

    def corpus(self) -> score_abstention.Corpus:
        marks = {
            "v": 4,
            "cases_digest": mark_abstention.cases_digest(self.body()),
            "marks": self.marks,
        }
        return score_abstention.Corpus(self.body(), marks, json.dumps(marks).encode(), self.rubric)

    def score(
        self,
        model: _Model,
        *,
        destination: str | None = "Anthropic",
        cap: int = 19,
        resume: dict[str, Any] | None = None,
        binding: dict[str, str] | None = None,
    ) -> int:
        with (
            mock.patch.object(score_abstention, "_get", side_effect=AssertionError("live read")),
            mock.patch("builtins.print"),
        ):
            return score_abstention.score(
                1,
                self.corpus(),
                config=_Config(),
                model=model,
                results_path=str(self.result),
                summary_path=str(self.summary),
                now=100000.0,
                binding=BINDING if binding is None else binding,
                tool_destination=destination,
                ledger_path=str(self.ledger_path),
                max_calls=cap,
                resume=resume,
            )

    def calls(self) -> list[dict[str, Any]]:
        return list(json.loads(self.ledger_path.read_text())["calls"])

    def committed(self) -> Any:
        return json.loads(self.summary.read_text())

    def local(self) -> Any:
        return json.loads(self.result.read_text())


class TheClaudeProducerIsChosenExplicitlyTest(unittest.TestCase):
    """Test 4: `--producer` is required to score, and the result names what ran."""

    def test_scoring_without_a_producer_refuses_before_building_any_model(self) -> None:
        printed: list[str] = []
        with (
            mock.patch.object(reading, "ClaudeReadingModel", side_effect=AssertionError),
            mock.patch.object(reading, "CodexReadingModel", side_effect=AssertionError),
            mock.patch("builtins.print", side_effect=lambda *a, **_k: printed.append(" ".join(a))),
        ):
            self.assertEqual(2, score_abstention.main(["--score"]))
        self.assertIn("--producer", "\n".join(printed))

    def test_the_claude_producer_builds_the_claude_model_and_its_own_result_file(self) -> None:
        seen: dict[str, Any] = {}

        def fake_score(*_args: Any, **kwargs: Any) -> int:
            seen.update(kwargs)
            return 0

        corpus = score_abstention.Corpus({"v": 5, "cases": [_claude_case()]}, {}, b"", {})
        with (
            mock.patch.object(score_abstention, "_load_corpus", return_value=corpus),
            mock.patch.object(score_abstention, "score", side_effect=fake_score),
            mock.patch.object(score_abstention, "argv_digest", return_value="cd" * 32),
            mock.patch.object(
                score_abstention,
                "verify_claude_binary",
                return_value=(BINDING["binary"], BINDING["cli_version"], "/abs/claude"),
            ),
            mock.patch("cargento_runtime.reading_route.destination", return_value="Anthropic"),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(0, score_abstention.main(["--score", "--producer", "claude"]))
        self.assertIsInstance(seen["model"], reading.ClaudeReadingModel)
        self.assertEqual(score_abstention.CLAUDE_SUMMARY_PATH, seen["summary_path"])
        self.assertTrue(seen["summary_path"].endswith("docs/abstention/claude-results.json"))
        self.assertEqual({**BINDING, "argv_digest": "cd" * 32}, dict(seen["binding"]))
        self.assertEqual(19, seen["max_calls"])
        self.assertEqual(abstention_ledger.LEDGER_PATH, seen["ledger_path"])

    def test_the_argv_digest_is_read_without_running_anything(self) -> None:
        with mock.patch("subprocess.run", side_effect=AssertionError("spent")):
            first = score_abstention.argv_digest("claude", _state_config())
            again = score_abstention.argv_digest("claude", _state_config())
            with mock.patch.object(observer, "CLAUDE_READING_EFFORT", "low"):
                moved = score_abstention.argv_digest("claude", _state_config())
            codex = score_abstention.argv_digest("codex", _state_config())
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, again)
        self.assertNotEqual(first, moved)
        self.assertEqual(codex, score_abstention.argv_digest("codex", _state_config()))


def _state_config() -> Any:
    from cargento_runtime.config import build_runtime_config  # noqa: PLC0415

    home = tempfile.mkdtemp()
    return build_runtime_config(
        environ={"HOME": home, "CARGENTO_HOME": home},
        platform_name="linux",
        os_name="posix",
        launcher_path=Path(home, "server.py"),
    )


class TheSummaryIsBoundToWhatProducedItTest(_Packet):
    def test_the_committed_file_names_the_producer_the_model_and_the_argv(self) -> None:
        self.assertEqual(0, self.score(_Model()))
        committed = self.committed()
        for key, value in BINDING.items():
            self.assertEqual(value, committed[key])


class TheFrozenChecksReachTheProducerTest(_Packet):
    """Test 5: the frozen tails go to the prompt, and only with a named destination."""

    def test_the_frozen_check_and_its_tail_are_in_the_prompt(self) -> None:
        model = _Model()
        self.score(model)
        self.assertEqual(1, len(model.prompts))
        self.assertIn("node --test tests/ai.test.js", model.prompts[0])
        self.assertIn(TAIL, model.prompts[0])
        self.assertTrue(self.committed()["cases"][self.cases[0]["id"]]["asks_output"])

    def test_an_unnamed_destination_refuses_to_score_before_anything(self) -> None:
        model = _Model()
        self.assertEqual(2, self.score(model, destination=""))
        self.assertEqual([], model.prompts)
        self.assertFalse(self.summary.exists())
        self.assertFalse(self.result.exists())
        self.assertFalse(self.ledger_path.exists())


class ATurnStopIsReadWhereTheRouteReadsOneTest(_Packet):
    """Test 6: `admit_turn_stop` for a Claude Code turn stop, never for Codex."""

    def test_a_claude_turn_stop_reaches_the_model(self) -> None:
        model = _Model()
        self.score(model)
        self.assertEqual(1, len(model.prompts))
        self.assertEqual("", self.local()["cases"][self.cases[0]["id"]]["withheld"])

    def test_a_codex_turn_stop_stays_withheld(self) -> None:
        case = _codex_case()
        case["row_snapshot"].update(state="idle", finished_at=150.0)
        self.cases = [case]
        self.marks = {case["id"]: {"goal": "judge", "line_1": "abstain"}}
        model = _Model()
        self.score(model)
        self.assertEqual([], model.prompts)
        self.assertEqual("turn-stop", self.local()["cases"][case["id"]]["withheld"])

    def test_a_recorded_working_observation_is_a_codex_case(self) -> None:
        case = _codex_case()
        self.cases = [case]
        self.marks = {case["id"]: {"goal": "judge", "line_1": "abstain"}}
        model = _Model()
        self.score(model)
        self.assertEqual(1, len(model.prompts))
        # No work evidence on Codex, so the line is the ruling's answer.
        self.assertFalse(self.committed()["cases"][case["id"]]["asks_output"])


class EachOutcomeLineIsItsOwnConstraintTest(_Packet):
    """Test 7: marks and outcomes per line, and a line marked abstain that judged fails."""

    def test_the_outcomes_are_keyed_goal_then_each_line(self) -> None:
        self.score(_Model(("{}", "ok")))
        outcomes = self.committed()["cases"][self.cases[0]["id"]]["outcomes"]
        self.assertEqual(["goal", "line_1", "line_2"], list(outcomes))

    def test_an_abstain_marked_line_judged_consistent_fails_the_check(self) -> None:
        reply = _reply(
            goal=("consistent", (2,)), line_1=("consistent", (2,)), line_2=("consistent", (2,))
        )
        self.assertEqual(1, self.score(_Model((reply, "ok"))))
        committed = self.committed()
        outcomes = committed["cases"][self.cases[0]["id"]]["outcomes"]
        self.assertEqual("judged:consistent", outcomes["line_1"])
        self.assertEqual("judged:consistent", outcomes["line_2"])
        self.assertEqual([self.cases[0]["id"]], committed["dec17"]["failed"])
        self.assertEqual("failed", committed["verdict"])

    def test_a_mark_missing_a_line_refuses_the_packet(self) -> None:
        self.marks[self.cases[0]["id"]].pop("line_2")
        model = _Model()
        self.assertEqual(2, self.score(model))
        self.assertEqual([], model.prompts)


class WhatAConsistentRestsOnTest(_Packet):
    """Test 8: a Goal consistent on the agent's own account is never tool-reported."""

    def test_the_basis_token_tells_a_check_from_the_agents_account(self) -> None:
        reply = _reply(
            goal=("consistent", (1,)), line_1=("consistent", (2,)), line_2=("unverifiable", ())
        )
        self.score(_Model((reply, "ok")))
        committed = self.committed()
        case = committed["cases"][self.cases[0]["id"]]
        self.assertEqual("judged:consistent", case["outcomes"]["goal"])
        self.assertEqual("account", case["basis"]["goal"])
        self.assertEqual("tool", case["basis"]["line_1"])
        self.assertEqual("", case["basis"]["line_2"])
        self.assertEqual(1, committed["counts"]["goal_consistent_on_account"])


class ARubricFalseReassuranceFailsTest(_Packet):
    """Decision of 2026-09-24: marking the line abstain is not enough on its own."""

    def test_a_false_reassurance_fails_a_run_the_marks_would_pass(self) -> None:
        self.marks[self.cases[0]["id"]]["line_2"] = "judge"
        self.rubric = {
            "cases": {
                self.cases[0]["id"]: {
                    "kind": "misleading-completion",
                    "origin": "recorded",
                    "expect": {"line_1": {"result": "unverifiable", "cites": []}},
                }
            }
        }
        reply = _reply(
            goal=("unverifiable", ()), line_1=("consistent", (2,)), line_2=("unverifiable", ())
        )
        self.assertEqual(1, self.score(_Model((reply, "ok"))))
        committed = self.committed()
        self.assertEqual([], committed["dec17"]["failed"])
        self.assertEqual(1, committed["rubric"]["counts"]["false-reassurance"])
        self.assertEqual("failed", committed["verdict"])


class TheCommittedFileHoldsNothingReadableTest(_Packet):
    """Test 13: no sid, no intent text, no tail and no model prose under docs/."""

    def test_the_summary_carries_none_of_the_session(self) -> None:
        reply = _reply(
            goal=("departure", (1,)), line_1=("consistent", (2,)), line_2=("unverifiable", ())
        )
        self.score(_Model((reply, "ok")))
        text = self.summary.read_text()
        for absent in (
            CLAUDE_SID,
            GOAL,
            LINE_ONE,
            LINE_TWO,
            TAIL,
            PROSE,
            "TITLE_WORDS",
            "node --test",
        ):
            self.assertNotIn(absent, text)
        self.assertNotIn(TAIL, self.ledger_path.read_text())
        self.assertNotIn(CLAUDE_SID, self.ledger_path.read_text())


class TheMarkerAsksPerLineAndShowsTheChecksTest(unittest.TestCase):
    """Test 10: the screen lists the frozen checks, and each line is its own question."""

    def run_marker(
        self, case: dict[str, Any], answers: list[str]
    ) -> tuple[Any, list[str], dict[str, Any]]:
        body = {"v": 5, "cases": [case]}
        printed: list[str] = []
        with tempfile.TemporaryDirectory() as folder:
            cases, marks = Path(folder, "cases.json"), Path(folder, "marks.json")
            cases.write_text(json.dumps(body))
            with (
                mock.patch.object(mark_abstention, "CASES_PATH", str(cases)),
                mock.patch.object(mark_abstention, "MARKS_PATH", str(marks)),
                mock.patch.object(mark_abstention, "_ask", side_effect=answers) as ask,
                mock.patch(
                    "builtins.print",
                    side_effect=lambda *a, **_k: printed.append(" ".join(map(str, a))),
                ),
            ):
                self.assertEqual(0, mark_abstention.mark())
            saved = json.loads(marks.read_text())
        self.assertEqual(mark_abstention.cases_digest(body), saved["cases_digest"])
        return ask, printed, saved["marks"][case["id"]]

    def test_a_claude_case_with_a_check_asks_the_goal_and_every_line(self) -> None:
        ask, printed, saved = self.run_marker(_claude_case(), ["judge", "judge", "abstain"])
        self.assertEqual(3, ask.call_count)
        self.assertIn(GOAL, ask.call_args_list[0].args[0])
        self.assertIn(LINE_ONE, ask.call_args_list[1].args[0])
        self.assertIn(LINE_TWO, ask.call_args_list[2].args[0])
        self.assertEqual({"goal": "judge", "line_1": "judge", "line_2": "abstain"}, saved)
        screen = "\n".join(printed)
        self.assertIn("node --test tests/ai.test.js (passed, as the tool reported)", screen)
        self.assertIn(TAIL, screen)
        self.assertIn("Recorded lifecycle: turn-stop", screen)

    def test_a_record_with_no_check_fixes_every_line_at_abstain(self) -> None:
        ask, _printed, saved = self.run_marker(_codex_case(), ["judge"])
        self.assertEqual(1, ask.call_count)
        self.assertEqual({"goal": "judge", "line_1": "abstain"}, saved)


class TheFreezeKeepsOnlyWhatStoodAtTheCaptureTest(unittest.TestCase):
    """Test 9, end to end: board facts after the capture and live checks are dropped."""

    def test_a_frozen_claude_case_is_a_valid_packet_with_its_checks_rebuilt(self) -> None:
        start = dt.datetime(2026, 9, 24, 3, 0, 0, tzinfo=dt.UTC).timestamp()

        def stamp(seconds: int) -> str:
            return (
                dt.datetime.fromtimestamp(start + seconds, tz=dt.UTC)
                .isoformat()
                .replace("+00:00", "Z")
            )

        rows = [
            {"type": "assistant", "isSidechain": False, "cwd": "/w", "timestamp": stamp(10),
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "pytest"}}]}},
            {"type": "user", "isSidechain": False, "cwd": "/w", "timestamp": stamp(15),
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "toolu_1", "content": "5 passed", "is_error": False}]}},
            {"type": "assistant", "isSidechain": False, "cwd": "/w", "timestamp": stamp(40),
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": "pytest"}}]}},
            {"type": "user", "isSidechain": False, "cwd": "/w", "timestamp": stamp(45),
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "toolu_2", "content": "1 failed", "is_error": True}]}},
        ]  # fmt: skip
        with tempfile.TemporaryDirectory() as folder:
            transcript = Path(folder, "t.jsonl")
            transcript.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            board = [
                _fact("early", sid=CLAUDE_SID, harness="claude", at=start + 5),
                _fact("late", sid=CLAUDE_SID, harness="claude", at=start + 50),
                _check("live", at=start + 40, result="failed", record="toolu_2"),
                _fact("other", sid="someone-else", harness="claude", at=start + 5),
            ]
            entry = {
                "harness": "claude",
                "sid": CLAUDE_SID,
                "project": "p",
                "captured_at": start + 30,
                "row": {"state": "idle", "finished_at": start + 20},
                "intent": {"goal": GOAL, "lines": [{"text": LINE_ONE}]},
                "transcript": str(transcript),
            }
            config = _state_config()
            case = mark_abstention.freeze_case(config, entry, board)
            with self.assertRaises(mark_abstention.FreezeError):
                mark_abstention.freeze_case(config, {**entry, "captured_at": start + 25}, board)
        ids = [fact["fact_id"] for fact in case["producer_facts"]]
        self.assertIn("early", ids)
        for absent in ("late", "live", "other"):
            self.assertNotIn(absent, ids)
        checks = [f for f in case["producer_facts"] if f["type"] == "tool_report"]
        self.assertEqual(["passed"], [c["result"] for c in checks])
        self.assertEqual({"toolu_1": "5 passed"}, case["tool_output"]["tails"])
        # A hand-written transcript outside ~/.claude/projects, with no session
        # id of its own and a lifecycle nothing recorded, is never a recorded case.
        self.assertEqual("synthetic", case["origin"])
        self.assertIn("transcript-outside-projects", case["unconfirmed"])
        self.assertIn("lifecycle-unconfirmed", case["unconfirmed"])
        corpus = score_abstention.Corpus({"v": 5, "cases": [case]}, {}, b"", {})
        with mock.patch("builtins.print"):
            self.assertTrue(score_abstention._replay_preflight(corpus))


# ------------------------------------------------------------------ DRC-4666 correction round


def _stamp(start: float, seconds: int) -> str:
    return dt.datetime.fromtimestamp(start + seconds, tz=dt.UTC).isoformat().replace("+00:00", "Z")


def _transcript(start: float, session_id: str) -> list[dict[str, Any]]:
    """One passing check, in the recorded shapes, stamped with its own session id."""
    return [
        {"type": "assistant", "isSidechain": False, "cwd": "/w", "sessionId": session_id,
         "timestamp": _stamp(start, 10), "message": {"role": "assistant", "content": [
             {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "pytest"}}]}},
        {"type": "user", "isSidechain": False, "cwd": "/w", "sessionId": session_id,
         "timestamp": _stamp(start, 15), "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "toolu_1", "content": "5 passed",
              "is_error": False}]}},
    ]  # fmt: skip


class _Ledgered(_Packet):
    """A packet plus a way to charge its ledger directly, as earlier runs would have."""

    def packet_ledger(self) -> abstention_ledger.Ledger:
        corpus = self.corpus()
        return abstention_ledger.Ledger(
            str(self.ledger_path),
            cap=19,
            marks_digest=score_abstention.marks_digest(corpus),
            inputs_digest=score_abstention._inputs_digest(corpus),
            producer="claude",
        )

    def precharge(self, count: int) -> None:
        ledger = self.packet_ledger()
        for _ in range(count):
            ledger.settle(ledger.charge(self.cases[0]["id"]), "ok")


class Q1TheMarksAreBoundToEveryChargeTest(_Ledgered):
    """F1: a mark rewritten after an output was seen must not re-score cleanly."""

    def test_every_charge_records_the_marks_and_inputs_digest(self) -> None:
        self.score(_Model())
        corpus = self.corpus()
        (call,) = self.calls()
        self.assertEqual(score_abstention.marks_digest(corpus), call["marks_digest"])
        self.assertEqual(score_abstention._inputs_digest(corpus), call["inputs_digest"])

    def test_scoring_again_under_rewritten_marks_is_refused(self) -> None:
        self.score(_Model())
        self.marks[self.cases[0]["id"]]["line_2"] = "judge"
        model = _Model()
        self.assertEqual(2, self.score(model))
        self.assertEqual([], model.prompts)
        self.assertEqual(1, len(self.calls()))

    def test_scoring_again_under_changed_cases_is_refused(self) -> None:
        self.score(_Model())
        self.cases[0]["intent"]["goal"] = "CHANGED"
        model = _Model()
        self.assertEqual(2, self.score(model))
        self.assertEqual([], model.prompts)

    def test_new_marks_and_a_reset_are_refused_once_a_call_is_charged(self) -> None:
        self.precharge(1)
        body = {"v": 5, "cases": [_claude_case()]}
        cases, marks = self.home / "cases.json", self.home / "marks.json"
        cases.write_text(json.dumps(body))
        marks.write_text("{}")
        with (
            mock.patch.object(abstention_ledger, "LEDGER_PATH", str(self.ledger_path)),
            mock.patch.object(mark_abstention, "CASES_PATH", str(cases)),
            mock.patch.object(mark_abstention, "MARKS_PATH", str(marks)),
            mock.patch.object(mark_abstention, "_ask", side_effect=AssertionError("asked")),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(1, mark_abstention.mark())
            self.assertEqual(1, mark_abstention.main(["--reset"]))
        self.assertEqual("{}", marks.read_text())

    def test_the_summary_records_both_digests_and_a_report_flags_ledger_drift(self) -> None:
        self.score(_Model())
        committed = self.committed()
        corpus = self.corpus()
        self.assertEqual(score_abstention.marks_digest(corpus), committed["marks_digest"])
        self.assertEqual(score_abstention._inputs_digest(corpus), committed["inputs_digest"])
        # A call charged under other marks, as a re-marked run would leave behind.
        body = json.loads(self.ledger_path.read_text())
        body["calls"].append({**body["calls"][0], "id": "x" * 32, "marks_digest": "0" * 64})
        self.ledger_path.write_text(json.dumps(body))
        printed: list[str] = []
        with (
            mock.patch.object(abstention_ledger, "LEDGER_PATH", str(self.ledger_path)),
            mock.patch("builtins.print", side_effect=lambda *a, **_k: printed.append(str(a))),
        ):
            score_abstention.report(corpus, committed)
        self.assertIn("STALE", "\n".join(printed))


class Q2OneLedgerThatFailsClosedTest(_Ledgered):
    """F2: one fixed ledger for every producer and home, locked, and never reset by damage."""

    def test_the_path_is_fixed_whatever_cargento_home_says(self) -> None:
        import importlib  # noqa: PLC0415

        with mock.patch.dict("os.environ", {"CARGENTO_HOME": str(self.home / "fresh")}):
            fresh = importlib.reload(abstention_ledger)
            path = fresh.LEDGER_PATH
        importlib.reload(abstention_ledger)
        _LEDGER_PATCH.stop()
        _LEDGER_PATCH.start()
        self.assertEqual(str(Path("~/.cargento/drc-4666-spend.json").expanduser()), path)
        self.assertNotIn("fresh", path)

    def test_the_cap_is_nineteen_and_cannot_be_raised(self) -> None:
        self.assertEqual(19, abstention_ledger.MAX_CALLS)
        with mock.patch("builtins.print"):
            self.assertEqual(
                2, score_abstention.main(["--score", "--producer", "claude", "--max-calls", "20"])
            )

    def test_the_cap_counts_every_earlier_run(self) -> None:
        self.precharge(18)
        second = _codex_case()
        self.cases.append(second)
        self.marks[second["id"]] = {"goal": "judge", "line_1": "abstain"}
        self.ledger_path.unlink()
        self.precharge(18)
        model = _Model()
        self.score(model)
        self.assertEqual(1, len(model.prompts))
        withheld = sorted(v["withheld"] for v in self.local()["cases"].values())
        self.assertEqual(["", "spend-cap"], withheld)
        self.assertEqual(19, len(self.calls()))

    def test_a_damaged_ledger_refuses_every_call_and_is_left_alone(self) -> None:
        for damage in (
            "{not json",
            json.dumps({"v": 1, "calls": "malformed", "runs": []}),
            json.dumps({"v": 1, "calls": [{"id": "a", "status": "ok"}], "runs": []}),
            json.dumps([]),
        ):
            with self.subTest(damage=damage[:20]):
                self.ledger_path.write_text(damage)
                model = _Model()
                self.assertEqual(2, self.score(model))
                self.assertEqual([], model.prompts)
                self.assertEqual(damage, self.ledger_path.read_text())
                self.assertFalse(self.summary.exists())

    def test_a_missing_ledger_is_an_empty_one(self) -> None:
        self.assertFalse(self.ledger_path.exists())
        model = _Model()
        self.score(model)
        self.assertEqual(1, len(model.prompts))

    def test_concurrent_processes_never_charge_past_the_cap(self) -> None:
        corpus = self.corpus()
        # Each process sleeps between its read and its write, which is where an
        # unlocked ledger loses charges: without the lock this over-charges.
        script = (
            "import sys, time; sys.path.insert(0, sys.argv[1]); import abstention_ledger as L\n"
            "read = L.read\n"
            "def slow(path):\n    body = read(path); time.sleep(0.05); return body\n"
            "L.read = slow\n"
            "l = L.Ledger(sys.argv[2], cap=3, marks_digest=sys.argv[3], inputs_digest=sys.argv[4],"
            " producer='claude')\n"
            "try:\n    l.charge('0123456789abcdef'); print('charged')\n"
            "except L.SpendCapError:\n    print('capped')\n"
        )
        args = [
            str(Path(__file__).resolve().parents[1]),
            str(self.ledger_path),
            score_abstention.marks_digest(corpus),
            score_abstention._inputs_digest(corpus),
        ]
        runs = [
            subprocess.Popen(
                [sys.executable, "-c", script, *args], stdout=subprocess.PIPE, text=True
            )
            for _ in range(8)
        ]
        said = [run.communicate(timeout=60)[0].strip() for run in runs]
        self.assertEqual(3, said.count("charged"), said)
        self.assertEqual(5, said.count("capped"), said)
        self.assertEqual(3, len(self.calls()))
        self.assertEqual([], list(self.home.glob("*.tmp")) + list(self.home.glob(".spend-*")))

    def test_codex_live_scoring_is_refused(self) -> None:
        printed: list[str] = []
        corpus = score_abstention.Corpus({"v": 5, "cases": [_claude_case()]}, {}, b"", {})
        with (
            mock.patch.object(score_abstention, "_load_corpus", return_value=corpus),
            mock.patch.object(score_abstention, "score", side_effect=AssertionError("scored")),
            mock.patch.object(reading, "CodexReadingModel", side_effect=AssertionError("built")),
            mock.patch("builtins.print", side_effect=lambda *a, **_k: printed.append(str(a))),
        ):
            self.assertEqual(2, score_abstention.main(["--score", "--producer", "codex"]))
        self.assertIn("no Codex spend", "\n".join(printed))


class Q3TheDestinationAndBinaryAreBoundTest(_Packet):
    """F3: a result must show that Anthropic's model answered through the real CLI."""

    def test_a_stub_destination_refuses_before_anything_is_written(self) -> None:
        model = _Model()
        stub = {**BINDING, "destination": "127.0.0.1:9"}
        self.assertEqual(2, self.score(model, binding=stub))
        self.assertEqual([], model.prompts)
        self.assertFalse(self.summary.exists())
        self.assertFalse(self.ledger_path.exists())

    def test_main_refuses_unless_the_destination_is_anthropic(self) -> None:
        corpus = score_abstention.Corpus({"v": 5, "cases": [_claude_case()]}, {}, b"", {})
        with (
            mock.patch.object(score_abstention, "_load_corpus", return_value=corpus),
            mock.patch.object(score_abstention, "score", side_effect=AssertionError("scored")),
            mock.patch("cargento_runtime.reading_route.destination", return_value="127.0.0.1:9"),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(2, score_abstention.main(["--score", "--producer", "claude"]))

    def test_only_the_installed_claude_cli_is_accepted(self) -> None:
        versions = self.home / "share" / "claude" / "versions"
        versions.mkdir(parents=True)
        real = versions / "2.1.281"
        real.write_text("")
        stub = self.home / "bin" / "claude"
        stub.parent.mkdir()
        stub.write_text("")
        # Named like a version, outside the installed versions: only the layout refuses it.
        lookalike = self.home / "elsewhere" / "2.1.281"
        lookalike.parent.mkdir()
        lookalike.write_text("")

        def run(version: str) -> Any:
            return mock.Mock(return_value=mock.Mock(returncode=0, stdout=f"{version}\n"))

        with mock.patch.object(score_abstention, "CLAUDE_VERSIONS_ROOTS", (str(versions),)):
            path, version, absolute = score_abstention.verify_claude_binary(
                resolver=lambda _name: str(real), runner=run("2.1.281 (Claude Code)")
            )
            self.assertEqual("2.1.281 (Claude Code)", version)
            self.assertEqual(str(real.resolve()), absolute)
            for resolver, runner in (
                (lambda _name: str(stub), run("2.1.281 (Claude Code)")),
                (lambda _name: str(lookalike), run("2.1.281 (Claude Code)")),
                (lambda _name: str(real), run("9.9.9 (Claude Code)")),
                (lambda _name: str(real), run("2.1.281 (Not Claude)")),
                (lambda _name: None, run("2.1.281 (Claude Code)")),
            ):
                with self.subTest(), self.assertRaises(score_abstention.BinaryError):
                    score_abstention.verify_claude_binary(resolver=resolver, runner=runner)
        self.assertNotIn(str(Path.home()), path)

    def test_the_stub_probe_never_writes_a_result_and_refuses_anthropic(self) -> None:
        model = _Model(("ok", "ok"))
        results = self.home / "claude-results.json"
        with (
            mock.patch.object(score_abstention, "CLAUDE_SUMMARY_PATH", str(results)),
            mock.patch.object(abstention_ledger, "LEDGER_PATH", str(self.ledger_path)),
            mock.patch.object(
                score_abstention,
                "verify_claude_binary",
                return_value=(BINDING["binary"], BINDING["cli_version"], "/abs/claude"),
            ),
            mock.patch.object(reading, "ClaudeReadingModel", return_value=model),
            mock.patch("builtins.print"),
        ):
            with mock.patch("cargento_runtime.reading_route.destination", return_value="Anthropic"):
                self.assertEqual(2, score_abstention.main(["--probe-argv"]))
            self.assertEqual([], model.prompts)
            with mock.patch(
                "cargento_runtime.reading_route.destination", return_value="127.0.0.1:8123"
            ):
                self.assertEqual(0, score_abstention.main(["--probe-argv"]))
        self.assertEqual(1, len(model.prompts))
        self.assertFalse(results.exists())
        self.assertFalse(self.ledger_path.exists())
        self.assertEqual([], list(self.home.glob("*.json")))


class Q4OnlyAGenuineCaseIsRecordedTest(unittest.TestCase):
    """F4: a case is recorded only when the machine's own records say so."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name, "projects")
        self.start = dt.datetime(2026, 9, 24, 3, 0, 0, tzinfo=dt.UTC).timestamp()
        self.config = _state_config()

    def transcript(self, session_id: str = CLAUDE_SID, *, inside: bool = True) -> str:
        folder = self.root / "-w" if inside else Path(self.temp.name, "elsewhere")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{session_id}.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in _transcript(self.start, session_id)))
        return str(path)

    def freeze(
        self, transcript: str, observations: list[dict[str, Any]], **entry: Any
    ) -> dict[str, Any]:
        base = {
            "harness": "claude",
            "sid": CLAUDE_SID,
            "project": "p",
            "captured_at": self.start + 30,
            "row": {"state": "idle", "finished_at": self.start + 20},
            "intent": {"goal": GOAL, "lines": [{"text": LINE_ONE}]},
            "transcript": transcript,
            **entry,
        }
        with mock.patch.object(mark_abstention, "CLAUDE_PROJECTS_ROOT", str(self.root)):
            return mark_abstention.freeze_case(
                self.config, base, [], observations=observations, ends=[]
            )

    def stop(self, at: float) -> list[dict[str, Any]]:
        return [
            {"harness": "claude", "sid": CLAUDE_SID, "state": "idle", "last_activity": at},
        ]

    def test_a_transcript_in_projects_with_its_own_id_and_a_recorded_stop_is_recorded(
        self,
    ) -> None:
        case = self.freeze(self.transcript(), self.stop(self.start + 20))
        self.assertEqual("recorded", case["origin"])
        self.assertEqual([], case["unconfirmed"])

    def test_anything_less_is_synthetic(self) -> None:
        for name, transcript, observations, reason in (
            ("outside", self.transcript(inside=False), self.stop(self.start + 20),
             "transcript-outside-projects"),
            ("other id", self.transcript("zz-other"), self.stop(self.start + 20),
             "transcript-other-session"),
            ("no stop", self.transcript(), [], "lifecycle-unconfirmed"),
            ("other stop", self.transcript(), self.stop(self.start + 19), "lifecycle-unconfirmed"),
        ):  # fmt: skip
            with self.subTest(name=name):
                case = self.freeze(transcript, observations)
                self.assertEqual("synthetic", case["origin"])
                self.assertIn(reason, case["unconfirmed"])

    def test_a_codex_working_case_needs_its_history_observation(self) -> None:
        entry = {
            "harness": "codex",
            "sid": CODEX_SID,
            "project": "p",
            "captured_at": 5000.0,
            "row": {"state": "working"},
            "intent": {"goal": GOAL, "lines": [{"text": LINE_ONE}]},
        }
        seen = {"harness": "codex", "sid": CODEX_SID, "state": "working", "last_activity": 5000.0}
        for observations, origin in (
            ([seen], "recorded"),
            ([], "synthetic"),
            ([{**seen, "last_activity": 4999.0}], "synthetic"),
            ([{**seen, "state": "idle"}], "synthetic"),
        ):
            with self.subTest(observations=observations):
                case = mark_abstention.freeze_case(
                    self.config, entry, [], observations=observations, ends=[]
                )
                self.assertEqual(origin, case["origin"])


class Q4ASyntheticCaseNeverMeetsTheFloorTest(_Packet):
    def test_its_rubric_entry_is_counted_synthetic_whatever_the_rubric_says(self) -> None:
        self.cases[0]["origin"] = "synthetic"
        self.rubric = {
            "cases": {
                self.cases[0]["id"]: {
                    "kind": "misleading-completion",
                    "origin": "recorded",
                    "expect": {
                        name: {"result": "unverifiable", "cites": []}
                        for name in ("goal", "line_1", "line_2")
                    },
                }
            }
        }
        self.score(_Model())
        rubric = self.committed()["rubric"]["cases"][self.cases[0]["id"]]
        self.assertEqual("synthetic", rubric["origin"])
        self.assertEqual(0, self.committed()["coverage"]["claude"]["kinds"])


class Q5MarksAreClosedTokensTest(_Packet):
    """F5: nothing hand-typed in the marks file reaches the committed summary."""

    def test_any_other_key_or_value_refuses_the_packet(self) -> None:
        case_id = self.cases[0]["id"]
        for name, marks in (
            ("extra key", {case_id: {**self.marks[case_id], "note": "PROMPT_TEXT"}}),
            ("orphan", {**self.marks, f"claude|{CLAUDE_SID}": {"goal": "SID_AS_VALUE"}}),
            ("value", {case_id: {**self.marks[case_id], "line_1": "maybe"}}),
            ("legacy key", {case_id: {**self.marks[case_id], "output": "judge"}}),
        ):
            with self.subTest(name=name):
                self.marks = marks
                model = _Model()
                self.assertEqual(2, self.score(model))
                self.assertEqual([], model.prompts)
                self.assertFalse(self.summary.exists())

    def test_the_summary_copies_marks_from_the_scored_records_only(self) -> None:
        record = {
            "id": "0123456789abcdef",
            "harness": "claude",
            "constraints": ["goal"],
            "marks": {"goal": "judge"},
            "outcomes": {"goal": "abstained"},
            "basis": {"goal": ""},
            "reached_model": True,
            "asks_output": False,
        }
        summary = score_abstention.summarize(
            [record],
            marks={"0123456789abcdef": {"goal": "judge", "note": "PROMPT_TEXT"}, "x": {"a": "b"}},
            marks_bytes=b"",
            now=1.0,
        )
        self.assertEqual({"0123456789abcdef": {"goal": "judge"}}, summary["marks"])
        self.assertNotIn("PROMPT_TEXT", json.dumps(summary))


def _rubric_record(kind: str, harness: str, judgement: dict[str, str]) -> dict[str, Any]:
    return {
        "id": "0123456789abcdef",
        "kind": kind,
        "harness": harness,
        "origin": "recorded",
        "admitted": True,
        "refused": "",
        "scored": True,
        "reached_model": True,
        "judgement": judgement,
        "extraction": {},
        "unknown_expectations": 0,
    }


class Q6AnUnscoredRequiredJudgementBlocksAPassTest(_Packet):
    """F6 and codex 3: a rubric that did not score what the case asks cannot pass."""

    def rubric_for(self, expect: dict[str, Any]) -> None:
        self.marks[self.cases[0]["id"]] = {"goal": "judge", "line_1": "judge", "line_2": "judge"}
        self.rubric = {
            "cases": {
                self.cases[0]["id"]: {
                    "kind": "misleading-completion",
                    "origin": "recorded",
                    "expect": expect,
                }
            }
        }

    def test_an_expectation_under_a_key_the_case_lacks_blocks(self) -> None:
        self.rubric_for({"goal": {"result": "consistent"}, "output": {"result": "unverifiable"}})
        reply = _reply(
            goal=("consistent", (2,)), line_1=("consistent", (2,)), line_2=("consistent", (2,))
        )
        self.score(_Model((reply, "ok")))
        committed = self.committed()
        entry = committed["rubric"]["cases"][self.cases[0]["id"]]
        self.assertEqual(1, entry["unknown_expectations"])
        self.assertEqual("unscored:missing-expectation", entry["judgement"]["line_1"])
        self.assertNotIn("output", json.dumps(entry["judgement"]))
        self.assertEqual("blocked", committed["verdict"])

    def test_a_misspelt_required_expectation_blocks(self) -> None:
        self.rubric_for({name: {"result": "unverifyable"} for name in ("goal", "line_1", "line_2")})
        self.score(_Model())
        self.assertEqual("blocked", self.committed()["verdict"])

    def test_coverage_counts_only_cases_whose_required_judgements_were_scored(self) -> None:
        full = {"goal": "correct", "line_1": "correct"}
        records = [
            _rubric_record(kind, harness, full)
            for kind in score_abstention.KINDS
            for harness in ("claude", "codex")
        ]
        self.assertEqual(5, score_abstention._coverage(records)["claude"]["kinds"])
        records[0]["judgement"] = {"goal": "correct", "line_1": "unscored:bad-expectation"}
        self.assertEqual(4, score_abstention._coverage(records)["claude"]["kinds"])
        coverage = score_abstention._coverage(records)
        counts = dict.fromkeys(score_abstention.RUBRIC_OUTCOMES, 0)
        counts["unscored:bad-expectation"] = 1
        dec17: dict[str, list[str]] = {"failed": [], "held": []}
        self.assertEqual("blocked", score_abstention._verdict(dec17, coverage, counts))


class Q7EveryCaseIsMarkedBeforeAnyCallTest(_Packet):
    def test_a_partly_marked_packet_spends_nothing(self) -> None:
        self.cases.append(_codex_case())
        model = _Model()
        self.assertEqual(2, self.score(model))
        self.assertEqual([], model.prompts)
        self.assertFalse(self.ledger_path.exists())

    def test_a_format_below_five_cannot_write_a_claude_result(self) -> None:
        case = {k: v for k, v in _claude_case().items() if k not in ("intent", "tool_output")}
        self.cases = [case]
        self.marks = {case["id"]: {"goal": "judge", "output": "abstain"}}
        model = _Model()
        with (
            mock.patch.object(self, "body", return_value={
                "v": 4, "goal": GOAL, "output": LINE_ONE, "cases": [case]}),
        ):  # fmt: skip
            self.assertEqual(2, self.score(model))
        self.assertEqual([], model.prompts)


class Q8AWriteAloneIsTheAgentsAccountTest(_Packet):
    def test_a_goal_consistent_citing_only_a_written_file_is_account(self) -> None:
        write = _fact(
            "w1",
            sid=CLAUDE_SID,
            harness="claude",
            at=90.0,
            type="tool_report",
            subject="write",
            summary="index.html",
            evidence={"source": "Claude Write call", "confidence": "exact"},
            branch={"harness": "claude", "sid": CLAUDE_SID, "record_id": "toolu_5"},
        )
        self.cases[0]["producer_facts"] = [
            _fact("a1", sid=CLAUDE_SID, harness="claude", at=80.0),
            write,
        ]
        self.cases[0]["tool_output"] = {"tails": {}, "changed_after": []}
        # Citing the agent's own words and the write: before the fix the write
        # alone made this `tool`.
        reply = _reply(goal=("consistent", (1, 2)))
        self.score(_Model((reply, "ok")))
        case = self.committed()["cases"][self.cases[0]["id"]]
        self.assertEqual("judged:consistent", case["outcomes"]["goal"])
        self.assertEqual("account", case["basis"]["goal"])

    def test_basis_calls_a_cited_write_account_and_only_a_recorded_check_tool(self) -> None:
        # Direct, because the producer's own item 8 drops a write from what a
        # verdict rests on today; the basis must not lean on that.
        agent: dict[str, Any] = {"id": "a1", "type": "result", "author": "agent"}
        write: dict[str, Any] = {"id": "w1", "type": "tool_report", "subject": "write", "result": "",
                 "author": "agent", "work": True}  # fmt: skip
        check = {**write, "id": "k1", "subject": "check", "result": "passed"}
        unrecorded = {**check, "id": "k2", "result": "not-recorded"}
        consistent = reading.RESULT_CONSISTENT
        cases: tuple[tuple[tuple[str, ...], list[dict[str, Any]], str], ...] = (
            (("w1",), [agent, write], "account"),
            (("a1", "w1"), [agent, write], "account"),
            (("k2",), [unrecorded], "account"),
            (("k1",), [check], "tool"),
        )
        for cites, ledger, want in cases:
            with self.subTest(cites=cites):
                criterion = {"result": consistent, "cites": cites}
                self.assertEqual(want, score_abstention.basis(criterion, ledger))


class Q9AResumeTrustsOnlyRecordsTheLedgerVouchesForTest(_Ledgered):
    def two_cases(self) -> None:
        second = _codex_case()
        self.cases.append(second)
        self.marks[second["id"]] = {"goal": "judge", "line_1": "abstain"}

    def test_a_resume_re_calls_only_the_cases_the_model_failed(self) -> None:
        self.two_cases()
        self.score(_Model(("", "failed"), ("{}", "ok")))
        failed = [k for k, v in self.local()["cases"].items() if v["withheld"] == "model-failed"]
        self.assertEqual([self.cases[0]["id"]], failed)
        model = _Model(("{}", "ok"))
        self.assertEqual(0, self.score(model, resume=self.local()))
        self.assertEqual(1, len(model.prompts))
        self.assertIn(TAIL, model.prompts[0])
        self.assertEqual(3, len(self.calls()))

    def test_a_hand_edited_record_refuses_the_resume(self) -> None:
        self.two_cases()
        self.score(_Model(("", "failed"), ("{}", "ok")))
        previous = self.local()
        other = self.cases[1]["id"]
        previous["records"][other]["outcomes"]["goal"] = "abstained"
        model = _Model()
        self.assertEqual(2, self.score(model, resume=previous))
        self.assertEqual([], model.prompts)

    def test_a_resume_against_other_inputs_refuses(self) -> None:
        self.score(_Model(("", "failed")))
        previous = self.local()
        self.cases[0]["intent"]["goal"] = "CHANGED"
        model = _Model()
        self.assertEqual(2, self.score(model, resume=previous))
        self.assertEqual([], model.prompts)
