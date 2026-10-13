"""A press keeps the closing agent message of each earlier turn, and the prompt reserves a share for them.

A long window leaves the first turns' evidence behind the newest messages: the project cap keeps
the newest, and the prompt ranks the agent's messages last, newest first. What the agent said it
had done is the last message of a turn, so those are kept past the cap (oldest first, bounded) and
given an eighth of the prompt before the newest messages take the rest. Reader messages, checks and
writes keep their rank, and a prompt everything fits in is selected exactly as it was.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from typing import Any
from unittest import mock

from compass_runtime import project_context, reading, semantic_history

from . import test_claude_checks as checks
from .test_agent_words import BUDGET, _agent, _person
from .test_press_message_reach import PressReachTestCase

SENTENCE = "I did this step of the plan and here is a long-ish title sentence describing it."


def person(index: int, at: float) -> reading.LedgerEntry:
    return reading.build_ledger(
        [_person(f"p{index:03d}", at, f"Please do part {index}.")], "claude", "s1"
    )[0]


def turns(count: int, steps: int) -> list[dict[str, Any]]:
    """A reader's message and then `steps` agent messages, the last of which closes the turn."""
    facts: list[dict[str, Any]] = []
    clock = 1_700_000_000.0
    for turn in range(count):
        facts.append(_person(f"p{turn:03d}", clock, f"Please do part {turn}."))
        for step in range(steps):
            clock += 1
            last = step == steps - 1
            name = f"c{turn:03d}" if last else f"a{turn:03d}-{step:02d}"
            facts.append(_agent(name, clock, "w" * 200, SENTENCE if not last else f"{name} done."))
        clock += 1
    return facts


def prompt_ids(facts: list[dict[str, Any]], budget: int = BUDGET) -> set[str]:
    ledger = reading.build_ledger(facts, "claude", "s1", tool_output={}, read_agent_words=True)
    _prompt, chosen = reading.build_prompt(ledger, goal="ship it", lines=("x",), max_bytes=budget)
    return {row["id"] for row in chosen.entries}


class TurnClosings(unittest.TestCase):
    def closings(self, kinds: str) -> frozenset[int]:
        rows = []
        for index, kind in enumerate(kinds):
            at = 1_700_000_000.0 + index
            if kind == "P":
                rows.append(person(index, at))
            else:
                rows.extend(
                    reading.build_ledger(
                        [_agent(f"a{index}", at, "words")], "claude", "s1", read_agent_words=True
                    )
                )
        return reading._turn_closings(rows)

    def test_the_last_agent_message_before_a_reader_message_and_the_last_of_all_close_a_turn(
        self,
    ) -> None:
        self.assertEqual({2, 4}, self.closings("PAAPA"))
        self.assertEqual({1}, self.closings("AA"))
        self.assertEqual({0, 2}, self.closings("APA"))

    def test_nothing_closes_a_turn_with_no_agent_message(self) -> None:
        self.assertEqual(frozenset(), self.closings(""))
        self.assertEqual(frozenset(), self.closings("PPP"))


class ThePromptReservesTheClosings(unittest.TestCase):
    def test_each_turns_closing_message_is_in_a_prompt_the_newest_messages_would_fill(self) -> None:
        facts = turns(6, 30)
        ids = prompt_ids(facts)
        self.assertTrue({f"c{turn:03d}" for turn in range(6)} <= ids)
        # Between them the budget was spent, so the early turns' other messages are what went.
        self.assertNotIn("a000-05", ids)
        self.assertIn("a005-28", ids)

    def test_the_reservation_is_bounded_and_takes_the_oldest_turns_first(self) -> None:
        ids = prompt_ids(turns(60, 3))
        early = [turn for turn in range(30) if f"c{turn:03d}" in ids]
        # The oldest turns, without a gap, and not every turn of the first half.
        self.assertEqual(list(range(len(early))), early)
        self.assertTrue(0 < len(early) < 30)
        self.assertNotIn("c030", ids)

    def test_every_reader_message_a_check_and_a_write_keep_their_rank(self) -> None:
        facts = turns(6, 30)
        facts.append(
            {
                "fact_id": "check-1",
                "type": "tool_report",
                "subject": "check",
                "summary": "ran the tests",
                "result": "failed",
                "result_source": "tool-result",
                "at": 1_700_000_050.0,
                "source_session": {"harness": "claude", "sid": "s1"},
                "evidence": {"source": "transcript", "confidence": "exact"},
            }
        )
        ids = prompt_ids(facts)
        self.assertTrue({f"p{turn:03d}" for turn in range(6)} <= ids)
        self.assertIn("check-1", ids)

    def test_a_prompt_everything_fits_in_is_selected_as_it_was(self) -> None:
        facts = turns(3, 4)
        ids = prompt_ids(facts)
        self.assertEqual({fact["fact_id"] for fact in facts}, ids)

    def test_the_selection_is_the_same_whatever_the_order_the_facts_arrive_in(self) -> None:
        facts = turns(6, 30)
        self.assertEqual(prompt_ids(facts), prompt_ids(list(reversed(facts))))


class TheCutoffSaysWhatTheAnchorsAre(unittest.TestCase):
    def selected(self, *times: float) -> list[reading.LedgerEntry]:
        return list(
            reading.build_ledger(
                [_agent(f"a{index}", at, "words") for index, at in enumerate(times)],
                "claude",
                "s1",
                read_agent_words=True,
            )
        )

    def text(self, rows: list[reading.LedgerEntry]) -> str:
        coverage = {"tail_truncated": True, "tail_start": 1_700_003_000.0}
        return reading.cutoff_text(
            rows, len(rows), 1_700_004_000.0, window_start=1_700_000_000.0, coverage=coverage
        )

    def test_it_counts_the_messages_kept_from_before_the_tail(self) -> None:
        text = self.text(self.selected(1_700_000_100.0, 1_700_000_200.0, 1_700_003_500.0))
        self.assertIn("2 agent messages that closed an earlier turn were kept.", text)

    def test_it_says_one_in_the_singular_and_nothing_when_none_were_kept(self) -> None:
        self.assertIn(
            "1 agent message that closed an earlier turn was kept.",
            self.text(self.selected(1_700_000_100.0, 1_700_003_500.0)),
        )
        self.assertNotIn("closed an earlier turn", self.text(self.selected(1_700_003_500.0)))


class ThePressKeepsTheClosings(PressReachTestCase):
    def long_turns(self, count: int, steps: int) -> None:
        for turn in range(count):
            self.session.prompt(f"Part {turn}.")
            for step in range(steps - 1):
                self.say(f"t{turn} step {step}.")
            self.say(f"t{turn} done.")

    def pressed(self) -> project_context.PressMessages:
        pressed = project_context.press_message_events(
            self.config, str(self.path), "claude", checks.SHORT, self.window_at()
        )
        assert pressed is not None
        return pressed

    def test_the_oldest_turns_closing_messages_survive_a_window_the_cap_cannot_hold(self) -> None:
        self.long_turns(30, 7)
        context = self.collect(reach=self.window_at())
        said = self.said(context)
        self.assertTrue({f"t{turn} done." for turn in range(12)} <= set(said))
        # Neither the early turns' other messages nor the closings past the twelve are kept.
        self.assertNotIn("t0 step 2.", said)
        self.assertNotIn("t14 done.", said)
        self.assertIn("t29 step 5.", said)
        reach = context["sources"]["message_reach"]
        self.assertIs(reach["tail_truncated"], True)
        closing = next(
            fact["at"]
            for fact in self.facts(context, "agent_message")
            if "t11 done" in fact["summary"]
        )
        self.assertGreater(reach["tail_start"], closing)

    def test_the_read_reaches_the_window_start_and_says_what_it_did_not_keep(self) -> None:
        self.long_turns(30, 7)
        pressed = self.pressed()
        self.assertTrue(pressed.reach.reached)
        self.assertIsNotNone(pressed.reach.lost)
        # The newest messages, and for each kept anchor its own and the reader's message after it.
        bound = project_context.MAX_PROJECT_EVENTS + 1 + 2 * project_context.PRESS_ANCHORS
        self.assertLessEqual(len(pressed.events), bound)
        self.assertEqual(project_context.PRESS_ANCHORS, len(pressed.anchors))

    def test_a_window_that_fits_loses_nothing_and_keeps_no_anchor_apart(self) -> None:
        self.long_turns(3, 4)
        pressed = self.pressed()
        self.assertIsNone(pressed.reach.lost)
        self.assertEqual(frozenset(), pressed.anchors)

    def test_a_single_turn_has_nothing_to_anchor_and_the_cap_behaves_as_it_did(self) -> None:
        for index in range(project_context.MAX_PROJECT_EVENTS + 20):
            self.say(f"Step {index}.")
        pressed = self.pressed()
        self.assertEqual(frozenset(), pressed.anchors)
        self.assertLessEqual(len(pressed.events), project_context.MAX_PROJECT_EVENTS + 1)

    def test_the_newest_turns_closing_reply_survives_when_reader_messages_crowd_the_cap(
        self,
    ) -> None:
        # Eighty turns of one reader message and one reply: the reader's messages are kept first, so
        # the cap leaves room for fewer replies than the newest hundred messages hold.
        self.long_turns(80, 1)
        context = self.collect(reach=self.window_at())
        said = self.said(context)
        self.assertIn("t79 done.", said)
        self.assertIn("t70 done.", said)

    def test_a_kept_anchor_brings_the_reader_message_that_closes_its_turn_in_the_ledger(
        self,
    ) -> None:
        self.long_turns(30, 7)
        # No history store to supply the reader's older messages: the press's own read is all there is.
        with (
            mock.patch.object(semantic_history, "read", return_value=[]),
            mock.patch.object(
                project_context, "_incremental_history_events", return_value=([], None)
            ),
        ):
            context = self.collect(reach=self.window_at())
        ledger = reading.build_ledger(
            context["semantic"]["facts"], "claude", checks.SHORT, read_agent_words=True
        )
        closings = reading._turn_closings(ledger)
        older = [
            index
            for index in closings
            if ledger[index]["summary"].startswith(tuple(f"t{turn} done" for turn in range(12)))
        ]
        self.assertEqual(project_context.PRESS_ANCHORS, len(older))

    def test_a_byte_stop_after_the_cap_names_where_the_whole_record_begins(self) -> None:
        for index in range(200):
            self.say(f"Step {index}.")
        config = replace(self.config, tail_bytes=600, direction_scan_max_bytes=40_000)
        context = self.collect(reach=self.window_at(), config=config)
        reach = context["sources"]["message_reach"]
        said = sorted(fact["at"] for fact in self.facts(context, "agent_message"))
        self.assertIs(reach["tail_truncated"], True)
        self.assertEqual(said[0], reach["tail_start"])

    def test_an_unread_region_inside_the_kept_messages_is_not_called_whole_from_before_it(
        self,
    ) -> None:
        for index in range(100):
            self.say(f"Step {index}.")
        self.say("x" * (project_context.PRESS_TEXT_MAX_CHARS + 1))
        big = self.session.rows[-1]["timestamp"]
        for index in range(100, 150):
            self.say(f"Step {index}.")
        context = self.collect(reach=self.window_at())
        reach = context["sources"]["message_reach"]
        gap = project_context._record_timestamp({"timestamp": big})
        self.assertIsNotNone(gap)
        self.assertGreater(reach["tail_start"], gap)

    def test_a_long_window_does_not_build_an_event_for_every_message_it_will_not_keep(self) -> None:
        for index in range(400):
            self.say(f"Step {index}.")
        built = mock.Mock(wraps=project_context._agent_message_event)
        with mock.patch.object(project_context, "_agent_message_event", built):
            self.pressed()
        self.assertLess(built.call_count, project_context.MAX_PROJECT_EVENTS + 20)

    def test_nothing_published_carries_a_marker_for_the_closing(self) -> None:
        self.long_turns(30, 7)
        text = json.dumps(self.collect(reach=self.window_at()))
        self.assertNotIn("anchor", text)
