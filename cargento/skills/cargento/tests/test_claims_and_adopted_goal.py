"""An adopted goal is read whole, and what the agent claims is its own constraint.

Owner, 2026-10-04, from the first drift replay run (docs/drift-replay/README.md, "The first
run"): a goal adopted from the reader's prompt kept 240 characters, which dropped the instruction
that mattered in one session and kept only plan-file preamble in another; and most drift the
reader pushed back on was a status claim ("merged", "tests pass") that no intent line speaks to.

So a reading sends the adopted prompt's whole words as the Goal, out of the reader's words share,
and keeps the clip everywhere else; and a reader's press on a Claude Code session that carries the
agent's messages asks a `claims` question beside the intent, whose fourth result, `unsupported`,
is a caution and never a departure (DEC-17 rule 3).

Every message here is placeholder prose.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import correction, levels, observer, reading
from cargento_runtime.config import build_runtime_config

from . import test_next_cockpit as cockpit_tests
from .next_harness import NextPageJsHarness, storage_prelude

REPO = Path(__file__).resolve().parents[4]
SCORER = REPO / "scripts"

SID = {"harness": "claude", "sid": "s1"}
CLIP = "Make the retry queue survive a restart, and before anything else read the plan file " + (
    "and its preamble " * 9
)
CLIP = CLIP[:239] + "…"
POINT = "the one instruction that mattered: never drop a queued event on shutdown"
WHOLE = CLIP[:-1] + " and so on. " + "More plan text. " * 30 + POINT
BUDGET = 16_384


def _person(fact_id: str, at: float, words: str, summary: str = "") -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "type": "user_message",
        "summary": summary or f"{fact_id} opens",
        reading.WORDS_FIELD: words,
        "at": at,
        "source_session": SID,
        "evidence": {"source": "timestamped non-meta user-role record", "confidence": "exact"},
    }


def _agent(fact_id: str, at: float, title: str) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "type": reading.AGENT_MESSAGE_TYPE,
        "summary": title,
        reading.AGENT_WORDS_FIELD: f"{title} More words follow the title.",
        "at": at,
        "source_session": SID,
        "evidence": {
            "source": "timestamped top-level assistant text record",
            "confidence": "exact",
        },
    }


def _check(fact_id: str, at: float, result: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "fact_id": fact_id,
        "type": reading.TOOL_REPORT_TYPE,
        "subject": reading.CHECK_SUBJECT,
        "result": result,
        "result_source": "flag",
        "summary": "python3 -m pytest tests/test_retry.py",
        "at": at,
        "evidence": {"source": "Claude Bash call and paired result", "confidence": "exact"},
        "source_session": SID,
        "branch": {**SID, "record_id": f"call-{fact_id}"},
    }
    row.update(extra)
    return row


def _snapshot(fact_id: str, at: float) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "type": "observer_snapshot",
        "summary": "Cargento's summary: the retry merged",
        "at": at,
        "source_session": SID,
        "evidence": {"source": "observer snapshot", "confidence": "low"},
    }


class _Producer(unittest.TestCase):
    """One `produce` call, the prompts kept, no model reached."""

    class _Config:
        reading_settle_sec = 8.0
        annotation_text_cap_chars = 240

    def setUp(self) -> None:
        self.prompts: list[str] = []

    def model(self, answer: str = "{}") -> Any:
        def run(prompt: str, **_kw: Any) -> tuple[str, str]:
            self.prompts.append(prompt)
            return answer, "ok"

        return run

    def produce(
        self,
        facts: list[dict[str, Any]],
        *,
        revision: dict[str, Any] | None = None,
        answer: str = "{}",
        read_agent_words: bool = True,
        tool_output: reading.ToolOutput | None = None,
    ) -> Any:
        return reading.produce(
            cast("Any", self._Config()),
            {**SID, "state": "working", "ended_at": None},
            [revision or {"n": 1, "at": 50.0, "goal": "add retry", "output": "tests pass"}],
            facts,
            now=500.0,
            stamp_text="read at 10:00",
            model=self.model(answer),
            tool_output=tool_output,
            read_lines=True,
            read_agent_words=read_agent_words,
        )


ADOPTED = {
    "n": 1,
    "at": 200.0,
    "goal": CLIP,
    "output": "",
    "goal_source": "first-prompt",
    "goal_source_at": 60.0,
}


class AnAdoptedGoalIsReadWholeTest(_Producer):
    def goal_block(self) -> str:
        prompt = self.prompts[0]
        return prompt[prompt.index("<goal>\n") + 7 : prompt.index("\n</goal>")]

    def test_the_whole_prompt_is_the_goal_the_model_reads(self) -> None:
        facts = [_person("p1", 60.0, WHOLE), _agent("a1", 90.0, "I wired the queue.")]
        assessment, why, _ = self.produce(facts, revision=ADOPTED)
        self.assertEqual("", why)
        self.assertIn(POINT, self.goal_block())
        self.assertNotIn("…", self.goal_block())
        self.assertNotIn(reading.GOAL_SOURCE_UNROOMED.strip(), assessment["cutoff"])
        self.assertNotIn(reading.GOAL_SOURCE_GONE.strip(), assessment["cutoff"])

    def test_the_stored_reading_keeps_the_clip_and_nothing_new(self) -> None:
        facts = [_person("p1", 60.0, WHOLE)]
        assessment, _, _ = self.produce(facts, revision=ADOPTED)
        self.assertEqual(CLIP, assessment["criteria"]["goal"]["clause"])
        self.assertNotIn(POINT, json.dumps(assessment))
        self.assertLessEqual(set(assessment), set(reading.ASSESSMENT_KEYS))
        self.assertEqual("first-prompt", assessment["goal_source"])
        self.assertNotIn(reading.GOAL_SOURCE_GONE.strip(), assessment["cutoff"])

    def test_the_source_row_is_not_sent_whole_a_second_time(self) -> None:
        self.produce([_person("p1", 60.0, WHOLE)], revision=ADOPTED)
        self.assertEqual(1, self.prompts[0].count(POINT))

    def test_with_the_prompt_gone_the_clip_is_read_and_the_cutoff_says_so(self) -> None:
        facts = [_person("p9", 70.0, "a later message"), _agent("a1", 90.0, "I wired it.")]
        assessment, _, _ = self.produce(facts, revision=ADOPTED)
        self.assertEqual(CLIP, self.goal_block())
        self.assertIn(reading.GOAL_SOURCE_GONE.strip(), assessment["cutoff"])

    def test_a_prompt_with_no_words_left_reads_as_gone(self) -> None:
        bare = _person("p1", 60.0, "")
        assessment, _, _ = self.produce([bare, _agent("a1", 90.0, "Done.")], revision=ADOPTED)
        self.assertEqual(CLIP, self.goal_block())
        self.assertIn(reading.GOAL_SOURCE_GONE.strip(), assessment["cutoff"])

    def test_a_typed_goal_is_never_replaced(self) -> None:
        typed = {k: v for k, v in ADOPTED.items() if not k.startswith("goal_source")}
        typed["at"] = 60.0
        assessment, _, _ = self.produce([_person("p1", 60.0, WHOLE)], revision=typed)
        self.assertEqual(CLIP, self.goal_block())
        self.assertNotIn(reading.GOAL_SOURCE_GONE.strip(), assessment["cutoff"])

    def test_a_copied_correction_at_that_time_is_never_the_source(self) -> None:
        copied = {**_person("p1", 60.0, WHOLE), reading.COPIED_FLAG: True}
        assessment, _, _ = self.produce([copied, _agent("a1", 90.0, "ok")], revision=ADOPTED)
        self.assertEqual(CLIP, self.goal_block())
        self.assertIn(reading.GOAL_SOURCE_GONE.strip(), assessment["cutoff"])

    def test_two_prompts_at_the_same_moment_are_told_apart_by_their_opening(self) -> None:
        other = _person("p0", 60.0, "an unrelated prompt " * 10)
        self.produce([other, _person("p1", 60.0, WHOLE)], revision=ADOPTED)
        self.assertIn(POINT, self.goal_block())

    def test_each_adopted_source_reads_whole(self) -> None:
        for source in reading.PROMPT_SOURCES:
            with self.subTest(source=source):
                self.prompts.clear()
                self.produce(
                    [_person("p1", 60.0, WHOLE)], revision={**ADOPTED, "goal_source": source}
                )
                self.assertIn(POINT, self.goal_block())

    def test_with_no_room_the_clip_is_read_and_the_cutoff_says_so(self) -> None:
        facts = [_person("p1", 60.0, WHOLE), _agent("a1", 90.0, "I wired it.")]
        with mock.patch.object(observer, "OBSERVER_MODEL_MAX_PROMPT_BYTES", 2_400):
            assessment, why, _ = self.produce(facts, revision=ADOPTED)
        self.assertEqual("", why)
        self.assertEqual(CLIP, self.goal_block())
        self.assertIn(reading.GOAL_SOURCE_UNROOMED.strip(), assessment["cutoff"])


class TheGoalsWordsComeFromTheReadersShareTest(unittest.TestCase):
    """Out of the person-words half, before any message's words, never in place of an entry."""

    def prompt(self, facts: list[dict[str, Any]], max_bytes: int = BUDGET) -> Any:
        ledger = reading.build_ledger(facts, "claude", "s1", tool_output={}, read_agent_words=True)
        return reading.build_prompt(
            ledger,
            goal=CLIP,
            lines=("the queue survives a restart",),
            max_bytes=max_bytes,
            goal_words=WHOLE,
            goal_fact="p1",
        )

    def test_the_goal_goes_whole_before_the_readers_other_messages(self) -> None:
        people = [_person(f"q{n:02d}", 100.0 + n, f"q{n:02d} MINE " + "m" * 990) for n in range(20)]
        prompt, selection = self.prompt(
            [_person("p1", 60.0, WHOLE), *people, _check("c1", 400.0, "failed")]
        )
        self.assertTrue(selection.goal_whole)
        self.assertIn(POINT, prompt)
        self.assertIn("python3 -m pytest", prompt)
        mine = [line for line in prompt.splitlines() if line.startswith("[") and " MINE " in line]
        goal = prompt[prompt.index("<goal>") : prompt.index("</goal>")]
        # The reader's half holds the goal's words and the messages read whole together.
        spent = sum(len((row + "\n").encode()) for row in mine) + len(goal.encode())
        self.assertLessEqual(spent, BUDGET // reading.WORDS_SHARE_DIVISOR + len(CLIP.encode()))

    def test_the_goals_words_never_cost_an_entry(self) -> None:
        facts = [_person("p1", 60.0, WHOLE), _check("c1", 400.0, "failed")]
        for budget in range(1_800, 6_000, 50):
            with self.subTest(budget=budget):
                plain = reading.build_prompt(
                    reading.build_ledger(facts, "claude", "s1", tool_output={}),
                    goal=CLIP,
                    lines=("the queue survives a restart",),
                    max_bytes=budget,
                )[1]
                whole = self.prompt(facts, budget)[1]
                self.assertEqual(
                    [row["id"] for row in plain.entries], [row["id"] for row in whole.entries]
                )

    def test_without_room_it_keeps_the_clip(self) -> None:
        prompt, selection = self.prompt([_person("p1", 60.0, WHOLE)], max_bytes=2_400)
        self.assertFalse(selection.goal_whole)
        self.assertIn(CLIP, prompt)
        self.assertLessEqual(len(prompt.encode()), 2_400)


class TheClaimsQuestionIsAskedOnlyWithTheAgentsWordsTest(_Producer):
    def test_a_press_carrying_an_agent_message_asks_it_and_stores_it_last(self) -> None:
        facts = [_person("p1", 60.0, "add retry"), _agent("a1", 90.0, "All tests pass.")]
        answer = json.dumps({"claims": {"result": "unsupported", "cites": [2]}})
        assessment, _, _ = self.produce(facts, answer=answer)
        self.assertIn('"claims": A', self.prompts[0])
        self.assertIn(reading.CLAIMS_RULE.strip(), self.prompts[0])
        self.assertEqual("claims", list(assessment["criteria"])[-1])
        row = assessment["criteria"]["claims"]
        self.assertEqual(reading.RESULT_UNSUPPORTED, row["result"])
        self.assertEqual(("a1",), row["cites"])
        self.assertEqual("", row["clause"])

    def test_no_agent_message_no_question(self) -> None:
        assessment, _, _ = self.produce([_person("p1", 60.0, "add retry")])
        self.assertNotIn('"claims"', self.prompts[0])
        self.assertNotIn("claims", assessment["criteria"])

    def test_the_unasked_lane_and_the_scorers_never_ask_it(self) -> None:
        facts = [_person("p1", 60.0, "add retry"), _agent("a1", 90.0, "All tests pass.")]
        assessment, _, _ = self.produce(facts, read_agent_words=False)
        self.assertNotIn('"claims"', self.prompts[0])
        self.assertNotIn("All tests pass", self.prompts[0])
        self.assertNotIn("claims", assessment["criteria"])

    def test_a_goal_or_line_answered_unsupported_has_no_result(self) -> None:
        facts = [_person("p1", 60.0, "add retry"), _agent("a1", 90.0, "All tests pass.")]
        answer = json.dumps(
            {
                "goal": {"result": "unsupported", "cites": [2]},
                "line_1": {"result": "unsupported", "cites": [2]},
            }
        )
        assessment, _, _ = self.produce(facts, answer=answer)
        for name in ("goal", "line_1"):
            with self.subTest(name=name):
                self.assertNotIn("result", assessment["criteria"][name])
                self.assertEqual(reading.WHY_UNREADABLE, assessment["criteria"][name]["why"])


def _resolve(token: str, facts: list[dict[str, Any]], cites: list[int], **kw: Any) -> Any:
    entries = reading.build_ledger(facts, "claude", "s1", tool_output={}, read_agent_words=True)
    return reading._resolve_one(
        {"token": token, "cites": cites, "detail": kw.pop("detail", "")},
        dict(enumerate(entries, 1)),
        name=reading.CONSTRAINT_CLAIMS,
        clause="",
        detail_cap_chars=200,
        window_start=50.0,
        **kw,
    )


SAID = _agent("a1", 90.0, "All tests pass.")
FAILED = _check("c1", 95.0, "failed")
PASSED = _check("c1", 95.0, "passed")


class EachClaimsResultCitesWhatItNeedsTest(unittest.TestCase):
    """Rule 3 for this question, and rule 4's backstop: the cases the resolver keeps."""

    # (case, token, facts in time order, cites, result, why)
    CASES: tuple[tuple[str, str, list[dict[str, Any]], list[int], str, str], ...] = (
        ("contradicted", "departure", [SAID, FAILED], [1, 2], reading.RESULT_DEPARTURE, ""),
        (
            "contradicted on the message alone",
            "departure",
            [SAID],
            [1],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_CLAIM_UNCITED,
        ),
        (
            "contradicted with no message",
            "departure",
            [SAID, FAILED],
            [2],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_CLAIM_UNCITED,
        ),
        (
            "contradicted by a pass",
            "departure",
            [SAID, PASSED],
            [1, 2],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_CHECK_DOES_NOT_SHOW_IT,
        ),
        ("unshown", "unsupported", [SAID], [1], reading.RESULT_UNSUPPORTED, ""),
        (
            "unshown citing only the reader",
            "unsupported",
            [_person("p1", 80.0, "is it merged?"), SAID],
            [1],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_CLAIM_UNCITED,
        ),
        ("shown", "consistent", [SAID, PASSED], [1, 2], reading.RESULT_CONSISTENT, ""),
        (
            "shown by the message alone",
            "consistent",
            [SAID],
            [1],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_CLAIM_UNCITED,
        ),
        (
            "shown by a pass a write followed",
            "consistent",
            [SAID, _check("c1", 95.0, "passed", before_last_change=True)],
            [1, 2],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_CHECK_DOES_NOT_SHOW_IT,
        ),
        (
            "shown by a failure",
            "consistent",
            [SAID, FAILED],
            [1, 2],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_CHECK_DOES_NOT_SHOW_IT,
        ),
        (
            "shown by Cargento's own summary",
            "consistent",
            [SAID, _snapshot("o1", 95.0)],
            [1, 2],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_BOARD_QUOTING_ITSELF,
        ),
        (
            "contradicted by Cargento's own summary",
            "departure",
            [SAID, _snapshot("o1", 95.0)],
            [1, 2],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_BOARD_QUOTING_ITSELF,
        ),
        (
            "a message from before the words",
            "unsupported",
            [_agent("a0", 40.0, "Merged."), SAID],
            [1],
            reading.RESULT_UNVERIFIABLE,
            reading.WHY_UNCITED,
        ),
    )

    def test_each_case(self) -> None:
        for case, token, facts, cites, result, why in self.CASES:
            with self.subTest(case=case):
                row = _resolve(token, facts, cites)
                self.assertEqual(result, row.get("result"))
                self.assertEqual(why, row["why"])
                self.assertIn(row["why"], reading.WHY_TOKENS)

    def test_a_departure_keeps_its_detail_and_an_unsupported_never_does(self) -> None:
        said = "The agent said every test passed and the check at the end failed."
        departed = _resolve("departure", [SAID, FAILED], [1, 2], detail=said)
        self.assertEqual(said, departed["detail"])
        unshown = _resolve("unsupported", [SAID], [1], detail="nothing shows a merge")
        self.assertEqual("", unshown["detail"])

    def test_a_stated_verdict_still_withdraws_it(self) -> None:
        row = _resolve("unsupported", [SAID], [1], detail="it delivered the feature")
        self.assertEqual(reading.WHY_VERDICT_STATED, row["why"])

    def test_a_shown_claim_beside_an_uncited_failure_on_record_is_withdrawn(self) -> None:
        row = _resolve(
            "consistent", [SAID, _person("p1", 92.0, "yes merged")], [1, 2], failed_on_record=True
        )
        self.assertEqual(reading.WHY_FAILED_CHECK_ON_RECORD, row["why"])


class TheStoreKnowsTheQuestionAndItsResultTest(unittest.TestCase):
    def assessment(self, criteria: dict[str, Any]) -> dict[str, Any]:
        return {
            "revision_read": 1,
            "revision_read_at": 100.0,
            "stamp": "read at 10:00",
            "cutoff": "Read 2 of the 2 entries after your words",
            "scope": reading.SCOPE_FINAL,
            "scope_text": reading.SCOPE_TEXT[reading.SCOPE_FINAL],
            "ended_at_read": 99.0,
            "criteria": criteria,
        }

    @staticmethod
    def row(result: str, cites: tuple[str, ...] = ("a1",), why: str = "") -> dict[str, Any]:
        return {"result": result, "cites": list(cites), "detail": "", "clause": "", "why": why}

    def test_claims_reads_back_last(self) -> None:
        stored = annotation_store._assessment(
            self.assessment(
                {
                    "claims": self.row(reading.RESULT_UNSUPPORTED),
                    "goal": self.row(reading.RESULT_UNVERIFIABLE, ()),
                    "line_1": self.row(reading.RESULT_UNVERIFIABLE, ()),
                }
            ),
            240,
        )
        assert stored is not None
        self.assertEqual(["goal", "line_1", "claims"], list(stored["criteria"]))
        self.assertEqual(reading.RESULT_UNSUPPORTED, stored["criteria"]["claims"]["result"])

    def test_unsupported_anywhere_else_refuses_the_reading_whole(self) -> None:
        for name in ("goal", "line_1"):
            with self.subTest(name=name):
                criteria = {
                    "goal": self.row(reading.RESULT_UNVERIFIABLE, ()),
                    "line_1": self.row(reading.RESULT_UNVERIFIABLE, ()),
                }
                criteria[name] = self.row(reading.RESULT_UNSUPPORTED)
                self.assertIsNone(annotation_store._assessment(self.assessment(criteria), 240))

    def test_the_new_reason_is_in_the_closed_set(self) -> None:
        criteria = {
            "goal": self.row(reading.RESULT_UNVERIFIABLE, ()),
            "claims": self.row(reading.RESULT_UNVERIFIABLE, (), reading.WHY_CLAIM_UNCITED),
        }
        stored = annotation_store._assessment(self.assessment(criteria), 240)
        assert stored is not None
        self.assertEqual(reading.WHY_CLAIM_UNCITED, stored["criteria"]["claims"]["why"])


class AnOlderBuildRefusesAReadingWithClaimsWholeTest(unittest.TestCase):
    """The downgrade: a build that knows neither the key nor the result refuses the
    reading whole, publishes the refusal and writes it back verbatim."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.config = build_runtime_config(
            environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=root / "server.py",
        )

    def write(self, assessment: Any) -> dict[str, Any]:
        os.makedirs(self.config.state_home, mode=0o700, exist_ok=True)
        payload = {
            "v": annotation_store.SCHEMA_VERSION,
            "entries": [
                {
                    "harness": "claude",
                    "sid": "s1",
                    "revisions": [{"n": 1, "at": 100.0, "goal": "ship it", "output": ""}],
                    "readings": 1,
                    "assessment": assessment,
                }
            ],
        }
        with open(annotation_store.store_path(self.config), "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        (entry,) = annotation_store.load(self.config)
        return dict(annotation_store.published(entry, binding_why=""))

    def test_refused_whole_kept_verbatim_and_read_again_forward(self) -> None:
        stored = TheStoreKnowsTheQuestionAndItsResultTest().assessment(
            {
                "goal": TheStoreKnowsTheQuestionAndItsResultTest.row(
                    reading.RESULT_UNVERIFIABLE, ()
                ),
                "claims": TheStoreKnowsTheQuestionAndItsResultTest.row(reading.RESULT_UNSUPPORTED),
            }
        )
        older = (
            mock.patch.object(reading, "RESULTS", reading.RESULTS[:3]),
            mock.patch.object(reading, "CONSTRAINT_CLAIMS", "a-key-this-build-never-had"),
        )
        for patch in older:
            with self.subTest(older=str(patch.attribute)), patch:
                row = self.write(stored)
                self.assertIsNone(row["assessment"])
                self.assertTrue(row["reading_refused"])
                entries = annotation_store.load(self.config)
                self.assertTrue(annotation_store.save(self.config, entries, diagnostic_sink=print))
            with open(annotation_store.store_path(self.config), encoding="utf-8") as handle:
                self.assertEqual(stored, json.load(handle)["entries"][0]["assessment"])
            current = self.write(stored)
            self.assertFalse(current["reading_refused"])
            assert current["assessment"] is not None
            self.assertEqual(
                reading.RESULT_UNSUPPORTED, current["assessment"]["criteria"]["claims"]["result"]
            )


def _stored(result: str, cites: list[str], *, lines: int = 1) -> dict[str, Any]:
    criteria: dict[str, Any] = {
        "goal": {
            "result": reading.RESULT_UNVERIFIABLE,
            "cites": [],
            "detail": "",
            "clause": "",
            "why": "",
        },
    }
    for k in range(1, lines + 1):
        criteria[f"line_{k}"] = {
            "result": reading.RESULT_UNVERIFIABLE,
            "cites": [],
            "detail": "",
            "clause": "",
            "why": "",
        }
    criteria["claims"] = {"result": result, "cites": cites, "detail": "", "clause": "", "why": ""}
    return {"read_at": 500.0, "window_start": 50.0, "criteria": criteria}


class TheAnalysisLevelReadsAClaimMediumTest(unittest.TestCase):
    def level(self, result: str, cites: list[str], facts: list[dict[str, Any]]) -> levels.Level:
        evidence = levels.Evidence(tuple(facts), dict.fromkeys(levels.SCAN_KEYS, 0), 0)
        return levels.analysis_level(_stored(result, cites), evidence, outcome_lines=1)

    def test_a_contradicted_claim_reads_medium_with_its_own_reason(self) -> None:
        # A pass, so the failed check's own High is not what decides it.
        facts = [SAID, _person("p1", 92.0, "it is not merged")]
        level = self.level(reading.RESULT_DEPARTURE, ["a1", "p1"], facts)
        self.assertEqual(levels.MEDIUM, level.level)
        self.assertIn(levels.REASON_CLAIM_CONTRADICTED, level.reasons)
        self.assertNotIn(levels.REASON_DEPARTURE, level.reasons)
        self.assertIn("a1", level.cites)

    def test_an_unshown_claim_reads_medium_with_its_own_reason(self) -> None:
        level = self.level(reading.RESULT_UNSUPPORTED, ["a1"], [SAID])
        self.assertEqual(levels.MEDIUM, level.level)
        self.assertEqual((levels.REASON_CLAIM_NOT_SHOWN,), level.reasons)
        self.assertEqual(("a1",), level.cites)

    def test_an_unshown_claim_whose_message_left_the_record_reads_nothing(self) -> None:
        level = self.level(reading.RESULT_UNSUPPORTED, ["a1"], [])
        self.assertNotEqual(levels.MEDIUM, level.level)

    def test_a_shown_claim_never_lifts_the_level_to_the_floor(self) -> None:
        level = self.level(reading.RESULT_CONSISTENT, ["a1", "c1"], [SAID, PASSED])
        self.assertEqual(levels.NOT_ENOUGH, level.level)

    def test_unsupported_on_a_line_is_malformed(self) -> None:
        stored = _stored(reading.RESULT_UNVERIFIABLE, [])
        stored["criteria"]["line_1"]["result"] = reading.RESULT_UNSUPPORTED
        evidence = levels.Evidence((), dict.fromkeys(levels.SCAN_KEYS, 0), 0)
        level = levels.analysis_level(stored, evidence, outcome_lines=1)
        self.assertEqual((levels.REASON_READING_MALFORMED,), level.reasons)


class SteerBackSaysWhatTheRecordDoesNotShowTest(unittest.TestCase):
    def compose(
        self, result: str, cites: list[str], facts: list[dict[str, Any]], **row: Any
    ) -> str:
        published = {
            **SID,
            "annotation_goal": "Ship the retry",
            "annotation_revision": 2,
            "annotation_window_start": 50.0,
            "annotation_assessment": {
                "revision_read": 2,
                "window_start": 50.0,
                "read_at": 500.0,
                "criteria": {
                    "claims": {"result": result, "cites": cites, "detail": "", "why": ""},
                },
            },
            **row,
        }
        for k in range(1, 7):
            published.setdefault(f"annotation_line_{k}", "")
        answer = correction.compose(
            published, facts, floor=50.0, lines_judged=True, clock=lambda at: f"T{int(at)}"
        )
        return "".join(
            part if isinstance(part, str) else "{" + part["entry"] + "}"
            for part in answer.get("parts", [])
        )

    def test_an_unshown_claim_is_said_in_one_line(self) -> None:
        text = self.compose(reading.RESULT_UNSUPPORTED, ["a1"], [SAID])
        self.assertIn('You said "All tests pass" at T90{a1}; the record does not show it.', text)
        self.assertTrue(text.startswith("Back to my goal: Ship the retry"))
        self.assertTrue(text.endswith("Please continue from here."))

    def test_a_contradicted_claim_is_said_the_same_way(self) -> None:
        text = self.compose(reading.RESULT_DEPARTURE, ["a1", "c1"], [SAID, FAILED])
        self.assertIn('You said "All tests pass" at T90{a1}; the record does not show it.', text)
        self.assertIn("A check failed at T95{c1}.", text)

    def test_a_shown_claim_adds_nothing_and_alone_is_nothing_to_steer_from(self) -> None:
        self.assertEqual("", self.compose(reading.RESULT_CONSISTENT, ["a1", "c1"], [SAID, PASSED]))

    def test_a_claim_the_record_no_longer_holds_adds_nothing(self) -> None:
        self.assertEqual("", self.compose(reading.RESULT_UNSUPPORTED, ["a1"], []))

    def test_an_unsettled_later_direction_holds_it_back(self) -> None:
        later = _person("p2", 120.0, "actually, pause the retry work")
        text = self.compose(reading.RESULT_UNSUPPORTED, ["a1"], [SAID, later])
        self.assertNotIn("You said", text)
        self.assertIn("I gave a later direction at T120{p2}.", text)

    def test_only_the_title_is_quoted_never_the_words(self) -> None:
        text = self.compose(reading.RESULT_UNSUPPORTED, ["a1"], [SAID])
        self.assertNotIn("More words follow the title", text)


class ThePageDrawsWhatTheAgentClaimedTest(NextPageJsHarness):
    def run_fixture(self, script: str) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + script,
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )

    def facts_js(self, facts: list[dict[str, Any]]) -> str:
        return json.dumps(facts)

    def shape(self, criteria: dict[str, Any], facts: list[dict[str, Any]]) -> Any:
        return self.run_fixture(f"""
const session = {{harness:"claude", sid:"s1"}};
const entries = nextCockpitWorkEntries(session, {{facts:{self.facts_js(facts)}}});
const numbers = new Map(entries.map((e, i) => [e.id, i + 1]));
const byId = new Map(entries.map(e => [e.id, e]));
const shape = nextCockpitReadingShape({{revision_read_at:50, criteria:{json.dumps(criteria)}}},
  {{goal:"add retry", line_1:"the retry backs off"}}, entries, "");
const why = row => (Object.entries(NEXT_READING_STORED_WHY).find(([, v]) => v === row.why) || [""])[0];
console.log(JSON.stringify({{
  rows: shape.criteria.map(row => ({{key: row.key, label: row.label, result: row.result,
    why: why(row), status: nextCockpitResultStatus(row, numbers, byId),
    short: nextCockpitResultStatus(row, numbers, byId, true),
    state: nextCockpitResultState(row), clause: row.clause, known: row.clauseKnown}})),
  answer: nextDriftAnswer(shape, entries).kind,
  html: nextCockpitResultAnswer(nextDriftAnswer(shape, entries), numbers, byId),
}}));
""")

    def claims(self, result: str, cites: list[str], facts: list[dict[str, Any]]) -> Any:
        out = self.shape({"claims": {"result": result, "cites": cites}}, facts)
        (row,) = [row for row in out["rows"] if row["key"] == "claims"]
        return row, out

    def test_four_states_and_their_sentences(self) -> None:
        tail = "The record read is the board's recent tail."
        row, out = self.claims(reading.RESULT_UNSUPPORTED, ["a1"], [SAID])
        self.assertEqual("WHAT THE AGENT CLAIMED", row["label"])
        self.assertEqual(
            f"What the agent said at #1 is not shown by the record. {tail}", row["status"]
        )
        self.assertEqual("unshown", row["state"])
        self.assertEqual("claim", out["answer"])
        self.assertIn("What the agent said at #1 is not shown by the record.", out["html"])
        row, out = self.claims(reading.RESULT_DEPARTURE, ["a1", "c1"], [SAID, FAILED])
        self.assertEqual("What the agent said at #1 is contradicted at #2", row["status"])
        self.assertEqual("departs", row["state"])
        row, _ = self.claims(reading.RESULT_CONSISTENT, ["a1", "c1"], [SAID, PASSED])
        self.assertEqual(
            "What the agent said at #1 is shown at #2, as the tool reported; not inspected",
            row["status"],
        )
        self.assertEqual("What the agent said at #1 is shown at #2", row["short"])
        row, _ = self.claims(reading.RESULT_UNVERIFIABLE, [], [SAID])
        self.assertEqual("cant-tell", row["state"])
        self.assertFalse(row["known"])

    def test_a_contradicted_claim_is_not_a_departure_from_the_intent(self) -> None:
        _row, out = self.claims(reading.RESULT_DEPARTURE, ["a1", "c1"], [SAID, FAILED])
        # The failed check is the answer before the claim, and nothing says "departs".
        self.assertEqual("failed-check", out["answer"])
        self.assertNotIn("Departs from your intent", out["html"])

    def test_a_claim_with_none_never_holds_nothing_found_back(self) -> None:
        criteria = {
            "goal": {"result": reading.RESULT_CONSISTENT, "cites": ["c1"]},
            "line_1": {"result": reading.RESULT_CONSISTENT, "cites": ["c1"]},
            "claims": {"result": reading.RESULT_UNVERIFIABLE, "cites": []},
        }
        out = self.shape(criteria, [_person("p1", 60.0, "add retry"), PASSED])
        self.assertEqual("nothing-found", out["answer"])

    def test_unsupported_on_the_goal_reads_as_unreadable(self) -> None:
        out = self.shape({"goal": {"result": reading.RESULT_UNSUPPORTED, "cites": ["a1"]}}, [SAID])
        (goal,) = [row for row in out["rows"] if row["key"] == "goal"]
        self.assertEqual(reading.RESULT_UNVERIFIABLE, goal["result"])
        self.assertEqual("unreadable", goal["why"])

    def test_the_page_and_the_resolver_agree_on_every_case(self) -> None:
        """Parity: the stored verdict, re-derived on the page, lands where the resolver puts it."""
        for case, token, facts, cites, result, why in EachClaimsResultCitesWhatItNeedsTest.CASES:
            if why == reading.WHY_UNCITED:
                continue  # the page holds no entry before the window to refuse
            ids = [facts[i - 1]["fact_id"] for i in cites]
            stored = reading.CLAIMS_RESULT_BY_TOKEN[token]
            with self.subTest(case=case):
                row, _ = self.claims(stored, ids, facts)
                self.assertEqual(result, row["result"])
                self.assertEqual(why, row["why"])


class ThePageSaysTheLevelsClaimReasonsTest(NextPageJsHarness):
    def test_each_claim_reason_names_the_message(self) -> None:
        out = self._run_page_js(
            "await __settle();\n"
            """
const entries = [{id:"a1", type:"agent_message"}];
const numbers = new Map([["a1", 4]]);
console.log(JSON.stringify(["claim-contradicted", "claim-not-shown"].map(token =>
  nextDriftReasons("medium", [token], ["a1"], entries, numbers, new Set()).first)));
""",
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )
        self.assertEqual(
            [
                "The record contradicts what the agent said at #4.",
                "The record read does not show what the agent said at #4.",
            ],
            out,
        )


class TheQuestionAndItsResultAreSpeltOnceEachSideTest(unittest.TestCase):
    def test_the_page_spells_the_producers_key_and_result(self) -> None:
        source = (
            (REPO / "cargento" / "skills" / "cargento" / "cargento_runtime" / "web")
            .joinpath("next-cockpit.js")
            .read_text(encoding="utf-8")
        )
        self.assertIn(f'const NEXT_READING_CLAIMS = "{reading.CONSTRAINT_CLAIMS}";', source)
        self.assertIn(f'const NEXT_READING_UNSUPPORTED = "{reading.RESULT_UNSUPPORTED}";', source)
        self.assertEqual(
            {**reading.RESULT_BY_TOKEN, "unsupported": reading.RESULT_UNSUPPORTED},
            reading.CLAIMS_RESULT_BY_TOKEN,
        )
        self.assertEqual(4, len(reading.RESULTS))


class TheScorerKnowsTheQuestionTest(unittest.TestCase):
    def test_unsupported_is_its_own_outcome_and_never_a_departure(self) -> None:
        import sys  # noqa: PLC0415

        sys.path.insert(0, str(SCORER))
        try:
            import score_abstention  # noqa: PLC0415
        finally:
            sys.path.remove(str(SCORER))
        self.assertEqual(reading.RESULT_UNSUPPORTED, score_abstention._UNSUPPORTED)
        self.assertEqual(
            score_abstention.OUTCOME_JUDGED_UNSUPPORTED,
            score_abstention.outcome({"result": reading.RESULT_UNSUPPORTED}, ""),
        )
        self.assertEqual(reading.RESULT_BY_TOKEN, score_abstention.RESULT_BY_TOKEN)


class TheGoalBoxSaysAnExcerptIsReadWholeTest(NextPageJsHarness):
    def test_the_sentence_is_short_and_names_the_whole_prompt(self) -> None:
        out = self._run_page_js(
            "await __settle();\n"
            """
console.log(JSON.stringify([
  nextPromptSourceLine({goal:"a clipped goal\\u2026", goal_source:"first-prompt", goal_source_at:5}),
  nextPromptSourceLine({goal:"a whole goal", goal_source:"first-prompt", goal_source_at:5}),
]));
""",
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )
        self.assertIn("Excerpt. Analyze reads the whole prompt.", out[0])
        self.assertNotIn("Analyze reads", out[1])


if __name__ == "__main__":
    unittest.main()
