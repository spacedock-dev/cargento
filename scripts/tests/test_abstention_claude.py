"""Qualifying the Claude Code reading producer (DRC-4666), with no model spend.

Every model here is a fake that records its prompts, so a test can say what
the producer was given and prove what was not spent. Format 5 is the packet
this qualification scores: a per-case intent with several outcome lines, and a
Claude Code case's checks frozen as they stood at the capture.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


BINDING = {"producer": "claude", "model": observer.CLAUDE_READING_MODEL, "argv_digest": "ab" * 32}


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
        cap: int = 20,
        resume: dict[str, Any] | None = None,
    ) -> int:
        ledger = score_abstention.SpendLedger(str(self.ledger_path), cap=cap, producer="claude")
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
                binding=BINDING,
                tool_destination=destination,
                ledger=ledger,
                resume=resume,
            )

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
            mock.patch("builtins.print"),
        ):
            self.assertEqual(0, score_abstention.main(["--score", "--producer", "claude"]))
        self.assertIsInstance(seen["model"], reading.ClaudeReadingModel)
        self.assertEqual(score_abstention.CLAUDE_SUMMARY_PATH, seen["summary_path"])
        self.assertTrue(seen["summary_path"].endswith("docs/abstention/claude-results.json"))
        self.assertEqual(
            {
                "producer": "claude",
                "model": observer.CLAUDE_READING_MODEL,
                "argv_digest": "cd" * 32,
            },
            dict(seen["binding"]),
        )
        self.assertEqual(20, seen["ledger"].cap)

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


class TwentyCallsAcrossRunsTest(_Packet):
    """Test 11: the spend ledger is a hard stop, and a resume re-calls model failures only."""

    def test_the_ledger_stops_at_its_cap_across_runs(self) -> None:
        self.ledger_path.write_text(json.dumps({"calls": [{"case": "x", "status": "ok"}] * 19}))
        second = _codex_case()
        self.cases.append(second)
        self.marks[second["id"]] = {"goal": "judge", "line_1": "abstain"}
        model = _Model()
        self.score(model)
        self.assertEqual(1, len(model.prompts))
        withheld = {k: v["withheld"] for k, v in self.local()["cases"].items()}
        self.assertEqual(["", "spend-cap"], sorted(withheld.values()))
        self.assertEqual(20, len(json.loads(self.ledger_path.read_text())["calls"]))
        again = _Model()
        self.score(again)
        self.assertEqual([], again.prompts)

    def test_no_cap_above_twenty_is_accepted(self) -> None:
        with mock.patch("builtins.print"):
            self.assertEqual(
                2, score_abstention.main(["--score", "--producer", "claude", "--max-calls", "21"])
            )

    def test_a_resume_re_calls_only_the_cases_the_model_failed(self) -> None:
        second = _codex_case()
        self.cases.append(second)
        self.marks[second["id"]] = {"goal": "judge", "line_1": "abstain"}
        self.score(_Model(("", "failed"), ("{}", "ok")))
        failed = [k for k, v in self.local()["cases"].items() if v["withheld"] == "model-failed"]
        self.assertEqual([self.cases[0]["id"]], failed)
        model = _Model(("{}", "ok"))
        self.score(model, resume=self.local())
        self.assertEqual(1, len(model.prompts))
        self.assertIn(TAIL, model.prompts[0])
        self.assertEqual(
            {"": 2}, {"": sum(v["withheld"] == "" for v in self.local()["cases"].values())}
        )
        self.assertEqual(3, len(json.loads(self.ledger_path.read_text())["calls"]))

    def test_a_resume_against_other_inputs_refuses(self) -> None:
        self.score(_Model(("", "failed")))
        previous = self.local()
        self.cases[0]["intent"]["goal"] = "CHANGED"
        model = _Model()
        self.assertEqual(2, self.score(model, resume=previous))
        self.assertEqual([], model.prompts)


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
        self.assertNotIn(TAIL, json.dumps(json.loads(self.ledger_path.read_text())))
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
        corpus = score_abstention.Corpus({"v": 5, "cases": [case]}, {}, b"", {})
        with mock.patch("builtins.print"):
            self.assertTrue(score_abstention._replay_preflight(corpus))
