"""A Claude Code session waiting at its prompt, read through its last turn (DRC-4679).

[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
item 13 lets a reader analyze a session that finished a turn and waits for them, while they can
still paste a correction into it, instead of meeting "A turn stop was observed and no session end
was". The evidence window starts at the words' own time rather than at the save, and the revision
stores that start. Every test here is a sentence about the reader: what they get back, and what
stays withheld from everyone who did not press.
"""

from __future__ import annotations

import dataclasses
import html
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import departures, reading, reading_policy, unasked
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime.config import RuntimeConfig, build_runtime_config
from cargento_runtime.state import build_runtime_state

# Read through the module, so the loader does not collect that class a second time here.
from . import test_next_cockpit as cockpit_tests
from .next_harness import NextPageJsHarness, named_machine, storage_prelude

STOP = 1_800_000_000.0  # the turn stopped
PROMPT = STOP - 600.0  # the reader's latest message, which started that turn
SAVE = STOP + 120.0  # words typed after the stop
NOW = STOP + 300.0  # the press
SETTLE = 8.0


def _config(root: Path, **changes: Any) -> RuntimeConfig:
    config = build_runtime_config(
        environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
        platform_name="linux",
        os_name="posix",
        launcher_path=root / "server.py",
    )
    return dataclasses.replace(config, **changes) if changes else config


def _waiting(harness: str = "claude") -> dict[str, Any]:
    """A session that finished a turn and waits at its prompt: idle, a stop, no end."""
    return {
        "harness": harness,
        "sid": "s1",
        "state": "idle",
        "acquisition": "event",
        "finished_at": STOP,
        "ended_at": None,
    }


def _message(fact_id: str, at: Any, **over: Any) -> dict[str, Any]:
    row = {
        "fact_id": fact_id,
        "type": "user_message",
        "by": "",
        "summary": "please add retry to the webhook",
        "at": at,
        "evidence": {"source": "root transcript", "confidence": "exact"},
        "source_session": {"harness": "claude", "sid": "s1"},
    }
    row.update(over)
    return row


def _check(at: float, result: str = "failed", **over: Any) -> dict[str, Any]:
    return over | {
        "fact_id": f"check-{int(at)}",
        "type": "tool_report",
        "subject": "check",
        "result": result,
        "result_source": "flag",
        "summary": "python3 -m pytest tests/test_retry.py",
        "at": at,
        "evidence": {"source": "Claude Bash call and paired result", "confidence": "exact"},
        "source_session": {"harness": "claude", "sid": "s1"},
        "branch": {"harness": "claude", "sid": "s1", "record_id": "call-1"},
    }


ADMITTED = reading.ToolOutput(destination="Anthropic", label="Claude Code", tails={})


class _Config:
    reading_settle_sec = SETTLE
    annotation_text_cap_chars = 240


# ------------------------------------------------------------------------------ when it may read


class ASessionWaitingAtItsPromptIsReadWhenYouPressTest(unittest.TestCase):
    """`eligibility` with the reader's switch, which only the reader route turns on."""

    def eligibility(self, row: dict[str, Any], **over: Any) -> tuple[str, str]:
        arguments: dict[str, Any] = {
            "latest_revision_at": SAVE,
            "now": NOW,
            "settle_sec": SETTLE,
        }
        arguments.update(over)
        return reading.eligibility(row, **arguments)

    def test_a_reader_who_presses_on_a_session_waiting_at_its_prompt_gets_its_last_turn_read(
        self,
    ) -> None:
        self.assertEqual(
            (reading.SCOPE_LAST_TURN, ""), self.eligibility(_waiting(), admit_turn_stop=True)
        )

    def test_a_goal_typed_after_the_turn_stopped_does_not_withhold_the_reading(self) -> None:
        for typed in (STOP - 1.0, STOP + 1.0, NOW):
            with self.subTest(typed=typed):
                scope, withheld = self.eligibility(
                    _waiting(), latest_revision_at=typed, admit_turn_stop=True
                )
                self.assertEqual((reading.SCOPE_LAST_TURN, ""), (scope, withheld))

    def test_nobody_who_did_not_press_gets_a_reading_of_a_turn_stop(self) -> None:
        self.assertEqual(("", reading.WITHHELD_TURN_STOP), self.eligibility(_waiting()))

    def test_a_reader_pressing_the_moment_the_turn_stopped_is_asked_to_wait_a_few_seconds(
        self,
    ) -> None:
        scope, withheld = self.eligibility(
            _waiting(), now=STOP + SETTLE - 0.001, admit_turn_stop=True
        )
        self.assertEqual(("", reading.WITHHELD_STOP_SETTLING), (scope, withheld))
        sentence = reading.WITHHELD[withheld]
        self.assertIn("turn", sentence)
        self.assertNotIn("ended", sentence)
        self.assertEqual(
            (reading.SCOPE_LAST_TURN, ""),
            self.eligibility(_waiting(), now=STOP + SETTLE, admit_turn_stop=True),
        )

    def test_a_clock_that_is_not_a_moment_never_reads_a_turn_stop(self) -> None:
        for now in (float("nan"), float("inf"), "later"):
            with self.subTest(now=now):
                scope, withheld = self.eligibility(_waiting(), now=now, admit_turn_stop=True)
                self.assertEqual("", scope)
                self.assertIn(withheld, reading.WITHHELD)

    def test_a_stop_that_is_not_a_moment_is_not_read_as_a_turn_stop(self) -> None:
        for stop in ("1800000000", True, float("nan"), 0, -1.0):
            with self.subTest(stop=stop):
                row = {**_waiting(), "finished_at": stop}
                scope, withheld = self.eligibility(row, admit_turn_stop=True)
                self.assertNotEqual(reading.SCOPE_LAST_TURN, scope)
                self.assertIn(withheld, reading.WITHHELD)

    def test_words_typed_after_a_session_ended_are_still_withheld_when_you_press(self) -> None:
        ended = {**_waiting(), "ended_at": STOP}
        self.assertEqual(
            ("", reading.WITHHELD_REVISION_AFTER_END),
            self.eligibility(ended, latest_revision_at=STOP + 60.0, admit_turn_stop=True),
        )

    def test_the_reading_says_it_covers_the_last_turn_and_not_how_the_session_ended(
        self,
    ) -> None:
        text = reading.SCOPE_TEXT[reading.SCOPE_LAST_TURN]
        self.assertIn("through the last turn", text)
        self.assertIn("not a reading of how the session ended", text)
        self.assertNotIn(text, set(reading.WITHHELD.values()))
        self.assertNotEqual(text, reading.SCOPE_TEXT[reading.SCOPE_FINAL])


# ------------------------------------------------------------------------ where the window opens


class YourTypedWordsReadWorkFromYourLatestMessageTest(unittest.TestCase):
    """`typed_window_start`: the latest person-authored message at or before the save."""

    def test_the_window_opens_at_your_latest_message_before_you_saved(self) -> None:
        facts = [_message("m1", PROMPT - 900.0), _message("m2", PROMPT), _message("m3", SAVE + 5)]
        self.assertEqual(PROMPT, reading.typed_window_start(facts, "claude", "s1", SAVE))

    def test_a_message_sent_at_the_moment_you_saved_opens_the_window_there(self) -> None:
        self.assertEqual(
            SAVE, reading.typed_window_start([_message("m1", SAVE)], "claude", "s1", SAVE)
        )

    def test_with_no_message_of_yours_before_the_save_the_window_opens_at_the_save(self) -> None:
        self.assertEqual(SAVE, reading.typed_window_start([], "claude", "s1", SAVE))
        self.assertEqual(
            SAVE, reading.typed_window_start([_message("m1", SAVE + 1)], "claude", "s1", SAVE)
        )

    def test_only_your_own_messages_in_this_session_move_the_window(self) -> None:
        facts = [
            # A permission you approved is not new words from you.
            {**_message("g1", PROMPT + 10), "type": "gate_decision", "by": "person:jared"},
            {**_message("a1", PROMPT + 20), "type": "task_result", "by": "agent"},
            {**_message("o1", PROMPT + 30), "type": "observer_snapshot"},
            _message("x1", PROMPT + 40, source_session={"harness": "claude", "sid": "other"}),
            _message("x2", PROMPT + 50, source_session={"harness": "codex", "sid": "s1"}),
            _message("z1", 0),
            _message("z2", None),
            _message("z3", float("nan")),
            _message("z4", True),
            _message("m1", PROMPT),
        ]
        self.assertEqual(PROMPT, reading.typed_window_start(facts, "claude", "s1", SAVE))


class TheWindowARevisionOpensTest(unittest.TestCase):
    """`reading.window_start`: the stored start, or the save time a build without it used."""

    def test_a_revision_that_stored_its_window_opens_there(self) -> None:
        revision = {"n": 1, "at": SAVE, "goal": "g", "window_start": PROMPT}
        self.assertEqual(PROMPT, reading.window_start(revision))

    def test_a_revision_saved_before_window_starts_existed_opens_at_its_save(self) -> None:
        self.assertEqual(SAVE, reading.window_start({"n": 1, "at": SAVE, "goal": "g"}))

    def test_adopted_words_saved_before_window_starts_existed_open_at_their_prompt(self) -> None:
        revision = {
            "n": 1,
            "at": SAVE,
            "goal": "g",
            "goal_source": "first-prompt",
            "goal_source_at": PROMPT - 100,
        }
        self.assertEqual(PROMPT - 100, reading.window_start(revision))

    def test_a_window_after_its_own_save_is_never_used(self) -> None:
        revision = {"n": 1, "at": SAVE, "goal": "g", "window_start": SAVE + 1}
        self.assertEqual(SAVE, reading.window_start(revision))


# --------------------------------------------------------------------------------- the producer


class _PressCase(unittest.TestCase):
    """`produce` on a waiting session, with a model that answers one departure."""

    def setUp(self) -> None:
        state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, state_dir, True)
        self.config = _Config()
        self.config.state_dir = state_dir  # type: ignore[attr-defined]
        self.prompts: list[str] = []

    def model(self, answer: str) -> Any:
        def run(prompt: str, **_kw: Any) -> tuple[str, str]:
            self.prompts.append(prompt)
            return answer, "ok"

        return run

    def produce(
        self,
        facts: list[dict[str, Any]],
        *,
        revision: dict[str, Any] | None = None,
        admit_turn_stop: bool = True,
        row: dict[str, Any] | None = None,
        cites: tuple[int, ...] = (2,),
    ) -> Any:
        """A departure on line 1 citing `cites`, the check's number in the prompt."""
        answer = json.dumps(
            {"line_1": {"result": "departure", "cites": list(cites), "detail": "the test failed"}}
        )
        return reading.produce(
            cast("Any", self.config),
            row or _waiting(),
            [
                revision
                or {
                    "n": 3,
                    "at": SAVE,
                    "window_start": PROMPT,
                    "goal": "add retry to the webhook",
                    "lines": ({"text": "tests pass", "source": "typed"},),
                }
            ],
            facts,
            now=NOW,
            stamp_text="read at 10:00",
            model=self.model(answer),
            tool_output=ADMITTED,
            read_lines=True,
            admit_turn_stop=admit_turn_stop,
        )


class YourPressOnAWaitingSessionReadsItsLastTurnTest(_PressCase):
    """`produce`, with the live walk's check: run after your message and before your save."""

    def test_a_reader_gets_a_reading_that_says_it_covers_the_last_turn(self) -> None:
        assessment, why, spent = self.produce([_message("m1", PROMPT), _check(PROMPT + 60)])
        self.assertEqual("", why)
        self.assertTrue(spent)
        self.assertEqual(reading.SCOPE_LAST_TURN, assessment["scope"])
        self.assertEqual(reading.SCOPE_TEXT[reading.SCOPE_LAST_TURN], assessment["scope_text"])

    def test_a_check_run_after_your_message_and_before_your_save_supports_its_verdict(
        self,
    ) -> None:
        assessment, _why, _spent = self.produce([_message("m1", PROMPT), _check(PROMPT + 60)])
        row = assessment["criteria"]["line_1"]
        self.assertEqual(reading.RESULT_DEPARTURE, row["result"])
        self.assertEqual((f"check-{int(PROMPT + 60)}",), row["cites"])

    def test_a_check_run_before_your_message_is_never_offered_to_the_reading(self) -> None:
        # DRC-4715, owner 2026-09-27: an entry from before the window is dropped from the
        # prompt, so it is never numbered and nothing can cite it. The model's `1` is your
        # message now, which shows no work, so the check's failure carries no verdict.
        assessment, _why, _spent = self.produce(
            [_check(PROMPT - 60), _message("m1", PROMPT)], cites=(1,)
        )
        row = assessment["criteria"]["line_1"]
        self.assertEqual(reading.RESULT_UNVERIFIABLE, row["result"])
        self.assertNotIn(f"check-{int(PROMPT - 60)}", row["cites"])
        self.assertNotIn("pytest", self.prompts[0])
        self.assertIn("[1] user_message", self.prompts[0])

    def test_a_check_whose_result_arrived_after_your_message_supports_its_verdict(self) -> None:
        # DRC-4702: the call began before the words and its result landed after them.
        straddling = _check(PROMPT - 60, result_at=PROMPT + 30)
        assessment, _why, _spent = self.produce([straddling, _message("m1", PROMPT)], cites=(1,))
        row = assessment["criteria"]["line_1"]
        self.assertEqual(reading.RESULT_DEPARTURE, row["result"])
        self.assertEqual((f"check-{int(PROMPT - 60)}",), row["cites"])

    def test_a_revision_without_a_window_start_still_reads_work_from_its_save(self) -> None:
        legacy = {
            "n": 3,
            "at": SAVE,
            "goal": "add retry to the webhook",
            "lines": ({"text": "tests pass", "source": "typed"},),
        }
        # Its window opens at the save, after the turn stopped, so the turn holds nothing
        # after the words to read (DRC-4715).
        assessment, why, _spent = self.produce(
            [_message("m1", PROMPT), _check(PROMPT + 60)], revision=legacy
        )
        self.assertIsNone(assessment)
        self.assertEqual(reading.WITHHELD_WINDOW_EMPTY, why)

    def test_a_check_run_after_the_turn_stopped_is_not_read_into_the_last_turn(self) -> None:
        assessment, why, _spent = self.produce([_message("m1", PROMPT), _check(STOP + 10)])
        self.assertEqual("", why)
        self.assertNotEqual(reading.RESULT_DEPARTURE, assessment["criteria"]["line_1"]["result"])
        self.assertNotIn("pytest", self.prompts[0])
        self.assertEqual(PROMPT, assessment["evidence_through"])

    def test_a_resumed_turn_the_row_has_not_caught_up_with_is_left_out(self) -> None:
        """The row still says idle at the old stop while the record has moved on."""
        resumed = _message("m2", STOP + 30, summary="now also add structured logging")
        assessment, _why, _spent = self.produce(
            [_message("m1", PROMPT), _check(PROMPT + 60), resumed, _check(STOP + 60)]
        )
        self.assertNotIn("structured logging", self.prompts[0])
        self.assertEqual(PROMPT + 60, assessment["evidence_through"])
        self.assertEqual(reading.SCOPE_LAST_TURN, assessment["scope"])

    def test_a_last_turn_reading_of_a_transcript_stop_reads_the_turns_entries_and_leaves_out_only_what_came_after_it(
        self,
    ) -> None:
        """The twin of the resumed-turn test, on a board no hook reaches (owner, 2026-10-02).

        The stop is the transcript's own record, `turn_end_at`, with no `finished_at`.
        """
        recorded = {**_waiting(), "finished_at": None, "turn_end_at": STOP, "acquisition": None}
        resumed = _message("m2", STOP + 30, summary="now also add structured logging")
        assessment, why, _spent = self.produce(
            [_message("m1", PROMPT), _check(PROMPT + 60), resumed, _check(STOP + 60)],
            row=recorded,
        )
        self.assertEqual("", why)
        self.assertIn("please add retry", self.prompts[0])
        self.assertIn("pytest", self.prompts[0])
        self.assertNotIn("structured logging", self.prompts[0])
        self.assertEqual(PROMPT + 60, assessment["evidence_through"])
        self.assertEqual(reading.SCOPE_LAST_TURN, assessment["scope"])
        self.assertEqual(reading.SCOPE_TEXT_LAST_TURN_TRANSCRIPT, assessment["scope_text"])
        self.assertIn("2 entries after the last observed stop", assessment["cutoff"])

    def test_a_hook_stop_wins_over_a_transcript_stop_and_says_so(self) -> None:
        both = {**_waiting(), "turn_end_at": STOP + 200}
        assessment, _why, _spent = self.produce(
            [_message("m1", PROMPT), _check(PROMPT + 60), _check(STOP + 60)], row=both
        )
        self.assertEqual(PROMPT + 60, assessment["evidence_through"])
        self.assertEqual(reading.SCOPE_TEXT[reading.SCOPE_LAST_TURN], assessment["scope_text"])

    def test_a_codex_row_carrying_a_transcript_stop_is_not_read_through_it(self) -> None:
        codex = {**_waiting("codex"), "finished_at": None, "turn_end_at": STOP}
        self.assertIsNone(reading.observed_stop(codex))
        self.assertEqual(reading.WITHHELD_IDLE_UNKNOWN, reading.end_kind(codex))

    def test_the_reading_keeps_where_its_window_opened(self) -> None:
        assessment, _why, _spent = self.produce([_message("m1", PROMPT), _check(PROMPT + 60)])
        self.assertEqual(PROMPT, assessment["window_start"])
        self.assertEqual(SAVE, assessment["revision_read_at"])
        self.assertLessEqual(set(assessment), set(reading.ASSESSMENT_KEYS))

    def test_without_the_readers_press_nothing_is_spent_on_a_turn_stop(self) -> None:
        assessment, why, spent = self.produce(
            [_message("m1", PROMPT), _check(PROMPT + 60)], admit_turn_stop=False
        )
        self.assertIsNone(assessment)
        self.assertEqual(reading.WITHHELD_TURN_STOP, why)
        self.assertFalse(spent)
        self.assertEqual([], self.prompts)


# ------------------------------------------------------------------------------------ the store


class _StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = _config(Path(self.temp.name))
        self.state = build_runtime_state(self.config, started=NOW)

    def latest(self) -> Any:
        found = annotation_store.find(annotation_store.load(self.config), "claude", "s1")
        assert found is not None
        return found["revisions"][-1]

    def write_raw(self, revision: dict[str, Any], **entry: Any) -> None:
        path = annotation_store.store_path(self.config)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "version": annotation_store.SCHEMA_VERSION,
            "entries": [{"harness": "claude", "sid": "s1", "revisions": [revision], **entry}],
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)


class YourRevisionKeepsWhereItsWindowOpensTest(_StoreCase):
    def test_typed_words_keep_your_latest_message_beside_the_save(self) -> None:
        annotation_store.annotate(
            self.config, self.state, "claude", "s1", goal="G", now=SAVE, window_start=PROMPT
        )
        latest = self.latest()
        self.assertEqual(SAVE, latest["at"])
        self.assertEqual(PROMPT, latest["window_start"])

    def test_typed_words_with_no_message_found_keep_the_save_as_their_window(self) -> None:
        annotation_store.annotate(self.config, self.state, "claude", "s1", goal="G", now=SAVE)
        self.assertEqual(SAVE, self.latest()["window_start"])

    def test_a_window_start_later_than_the_save_is_never_stored(self) -> None:
        for bad in (SAVE + 1, float("nan"), 0, True, "then"):
            with self.subTest(bad=bad):
                annotation_store.annotate(
                    self.config,
                    self.state,
                    "claude",
                    "s1",
                    goal=f"G {bad}",
                    now=SAVE,
                    window_start=bad,
                )
                self.assertEqual(SAVE, self.latest()["window_start"])

    def test_every_save_recomputes_the_window_even_when_only_a_line_changed(self) -> None:
        annotation_store.annotate(
            self.config, self.state, "claude", "s1", goal="G", now=SAVE, window_start=PROMPT
        )
        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s1",
            lines=["tests pass"],
            now=SAVE + 60,
            window_start=SAVE + 30,
        )
        self.assertEqual(SAVE + 30, self.latest()["window_start"])

    def test_words_adopted_from_your_prompt_open_their_window_at_the_prompt(self) -> None:
        row = {
            "harness": "claude",
            "sid": "s1",
            "first_prompt": "Harden the ingest",
            "first_prompt_at": PROMPT,
        }
        outcome = annotation_store.adopt(
            self.config,
            self.state,
            row,
            source="first-prompt",
            expected_text="Harden the ingest",
            expected_at=PROMPT,
            now=SAVE,
        )
        self.assertEqual(annotation_store.OUTCOME_STORED, outcome)
        self.assertEqual(PROMPT, self.latest()["window_start"])
        # A line added under the adopted goal keeps the prompt's time, whatever was typed since.
        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s1",
            lines=["tests pass"],
            now=SAVE + 60,
            window_start=SAVE + 30,
        )
        self.assertEqual(PROMPT, self.latest()["window_start"])

    def test_a_revision_saved_by_an_older_build_reads_back_and_opens_at_its_save(self) -> None:
        self.write_raw({"n": 1, "at": SAVE, "goal": "G", "lines": []})
        latest = self.latest()
        self.assertNotIn("window_start", latest)
        self.assertEqual(SAVE, reading.window_start(latest))

    def test_a_stored_window_start_that_is_not_a_moment_before_the_save_refuses_the_entry(
        self,
    ) -> None:
        for bad in (SAVE + 1, 0, -5.0, True, "yesterday", None, [PROMPT]):
            with self.subTest(bad=bad):
                self.write_raw({"n": 1, "at": SAVE, "goal": "G", "lines": [], "window_start": bad})
                found = annotation_store.find(annotation_store.load(self.config), "claude", "s1")
                self.assertIsNone(found)

    def test_older_adopted_words_publish_their_prompt_as_where_the_window_opens(self) -> None:
        self.write_raw(
            {
                "n": 1,
                "at": SAVE,
                "goal": "G",
                "lines": [],
                "goal_source": "first-prompt",
                "goal_source_at": PROMPT,
            }
        )
        entry = annotation_store.find(annotation_store.load(self.config), "claude", "s1")
        self.assertEqual(PROMPT, annotation_store.published(entry)["window_start"])

    def test_a_save_over_an_entry_held_for_a_bad_window_start_writes_nothing(self) -> None:
        self.write_raw({"n": 1, "at": SAVE, "goal": "G", "lines": [], "window_start": SAVE + 1})
        path = annotation_store.store_path(self.config)
        with open(path, "rb") as handle:
            before = handle.read()
        outcome = annotation_store.annotate(
            self.config, self.state, "claude", "s1", goal="new words", now=NOW, window_start=PROMPT
        )
        self.assertEqual(annotation_store.OUTCOME_UNREADABLE, outcome)
        with open(path, "rb") as handle:
            self.assertEqual(before, handle.read())

    def test_the_session_publishes_where_your_window_opens(self) -> None:
        self.assertIsNone(annotation_store.published(None)["window_start"])
        annotation_store.annotate(
            self.config, self.state, "claude", "s1", goal="G", now=SAVE, window_start=PROMPT
        )
        entry = annotation_store.find(annotation_store.load(self.config), "claude", "s1")
        self.assertEqual(PROMPT, annotation_store.published(entry)["window_start"])
        self.assertIn("annotation_window_start", runtime_sessions.base_session("claude", "x", "p"))
        self.assertIsNone(
            runtime_sessions.base_session("claude", "x", "p")["annotation_window_start"]
        )


class AReadingOfTheLastTurnIsKeptTest(_StoreCase):
    def assessment(self, **over: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "revision_read": 1,
            "revision_read_at": SAVE,
            "window_start": PROMPT,
            "read_at": NOW,
            "stamp": "read",
            "cutoff": "Read 2 of the 2 entries after your words.",
            "scope": reading.SCOPE_LAST_TURN,
            "scope_text": reading.SCOPE_TEXT[reading.SCOPE_LAST_TURN],
            "ended_at_read": None,
            "evidence_through": PROMPT + 60,
            "criteria": {
                "goal": {"result": "departure", "cites": ["m1"], "detail": "d", "clause": "G"}
            },
        }
        row.update(over)
        return row

    def stored(self, assessment: dict[str, Any]) -> Any:
        self.write_raw(
            {"n": 1, "at": SAVE, "goal": "G", "lines": [], "window_start": PROMPT},
            assessment=assessment,
        )
        found = annotation_store.find(annotation_store.load(self.config), "claude", "s1")
        assert found is not None
        return found

    def test_a_last_turn_reading_reads_back_with_its_scope_and_its_window(self) -> None:
        found = self.stored(self.assessment())
        self.assertEqual(reading.SCOPE_LAST_TURN, found["assessment"]["scope"])
        self.assertEqual(PROMPT, found["assessment"]["window_start"])

    def test_a_reading_stored_before_window_starts_existed_reads_back_with_none(self) -> None:
        legacy = self.assessment()
        del legacy["window_start"]
        self.assertIsNone(self.stored(legacy)["assessment"]["window_start"])

    def test_a_reading_whose_window_opens_after_its_revision_was_saved_is_refused_whole(
        self,
    ) -> None:
        for bad in (SAVE + 1, "then", True, float("inf")):
            with self.subTest(bad=bad):
                found = self.stored(self.assessment(window_start=bad))
                self.assertNotIn("assessment", found)
                self.assertTrue(found.get("refused"))


# ----------------------------------------------------------------------------- the unasked lane


class TheUnaskedLaneSpendsNothingAtATurnStopTest(unittest.TestCase):
    """Run with the real `reading.produce` and a model that counts its calls."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = _config(Path(self.temp.name), unasked_enabled=True)
        self.state = build_runtime_state(self.config, started=1_000.0)
        self.calls: list[str] = []
        calls = self.calls

        class CountingModel:
            def __init__(self, _config: Any, **_kw: Any) -> None:
                pass

            def __call__(self, prompt: str, *, output_cap_bytes: int) -> tuple[str, str]:
                del output_cap_bytes
                calls.append(prompt)
                return json.dumps({"goal": {"result": "departure", "cites": [1]}}), "ok"

        self.enterContext(mock.patch.object(reading, "CodexReadingModel", CountingModel))
        # The lane sends only under a Codex Allow for today's destination
        # (consent F5, ui5), so the machine is pinned and the Allow given.
        self.enterContext(named_machine())
        reading_policy.set_consent(
            self.config, True, now=1_000.0, provider="codex", destination="OpenAI"
        )
        self.entry = cast(
            "annotation_store.Annotation",
            {
                "harness": "claude",
                "sid": "s1",
                "revisions": (
                    {"n": 1, "at": SAVE, "window_start": PROMPT, "goal": "G", "lines": ()},
                ),
            },
        )

    def run_lane(self, *rows: dict[str, Any]) -> None:
        lane = unasked.Lane(
            self.config,
            popup_notifier=lambda _title, _message: "handed-over",
            diagnostic_sink=lambda _line: None,
            clock=lambda: NOW,
            facts_for=lambda _state, _row, _now: [_message("m1", PROMPT)],
            spawn=lambda work: work(),
        )
        for row in rows:
            lane.consider(self.state, [row], [self.entry], now=NOW)

    def test_a_session_that_stops_its_turn_is_never_read_by_the_lane(self) -> None:
        self.run_lane({**_waiting(), "state": "working"}, _waiting())
        self.assertEqual([], self.calls, "the unasked lane read a turn stop")
        self.assertEqual((), departures.load(self.config))

    def test_the_same_lane_does_read_a_session_that_starts_working_again(self) -> None:
        # The control: without it, a lane that never runs would pass the test above.
        self.run_lane(_waiting(), {**_waiting(), "state": "working"})
        self.assertEqual(1, len(self.calls))


# -------------------------------------------------------------------------------------- the page


class ThePageAndTheProducerReadATurnStopOnTheSameHarnessesTest(unittest.TestCase):
    def test_a_hint_never_promises_a_last_turn_the_server_would_withhold(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "next-observed.js"
        ).read_text(encoding="utf-8")
        match = re.search(r"const NEXT_READING_TURN_STOP_HARNESSES = \[([^\]]*)\];", source)
        assert match is not None
        page = {part.strip().strip('"') for part in match.group(1).split(",") if part.strip()}
        self.assertEqual(set(reading.TURN_STOP_HARNESSES), page)


class ThePageReadsTheServersOneStopTest(NextPageJsHarness):
    """`nextSessionStop` is a port of `reading.observed_stop`, held to it over one table."""

    def test_the_page_and_the_server_name_the_same_stop_on_every_row(self) -> None:
        table = [
            {"harness": harness, "finished_at": hook, "turn_end_at": recorded}
            for harness in ("claude", "codex", "antigravity")
            for hook in (None, 0, STOP)
            for recorded in (None, 0, STOP + 5)
        ]
        out = self._run_page_js(
            f"const rows = {json.dumps(table)};\n"
            "console.log(JSON.stringify(rows.map(row => {"
            "const stop = nextSessionStop(row); return stop ? [stop.at, stop.kind] : null;})));",
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )
        expected = [
            list(stop) if (stop := reading.observed_stop(row)) is not None else None
            for row in table
        ]
        self.assertEqual(expected, out)


class HowItLandedNamesATranscriptStopTest(NextPageJsHarness):
    def test_how_it_landed_names_a_transcript_stop_as_the_transcripts_not_as_an_observed_stop(
        self,
    ) -> None:
        out = self._run_page_js(
            """
const row = {harness:"claude", sid:"s1", state:"idle", finished_at:null, turn_end_at:100,
  ended_at:null};
const landed = nextObservedLanding(row, false, nextSessionStop(row));
console.log(JSON.stringify({text:landed.endText, kind:landed.endKind,
  hint:nextObservedReadHint(row)}));
""",
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )
        self.assertEqual("turn-stop", out["kind"])
        self.assertEqual(
            "Claude Code's transcript shows the last turn finished; no session end was observed",
            out["text"],
        )
        self.assertNotIn("was observed;", out["text"].split(";")[0])
        self.assertEqual("Reads the session up to its last turn against your intent.", out["hint"])


class SessionFactsAgreeWithHowItLandedTest(NextPageJsHarness):
    def test_session_facts_name_a_transcript_stop_rather_than_saying_none_was_observed(
        self,
    ) -> None:
        """Verifier F6 (ui3): "Session facts: No stop or end observed" stood beside a HOW IT
        LANDED card naming the transcript's stop, on the same idle Claude Code row."""
        out = self._run_page_js(
            """
const row = {harness:"claude", sid:"s1", state:"idle", finished_at:null, turn_end_at:100,
  ended_at:null};
const facts = nextObservedSession(row, [], null, 200, 1);
const hooked = nextObservedSession({...row, finished_at:100}, [], null, 200, 1);
const none = nextObservedSession({...row, turn_end_at:null}, [], null, 200, 1);
const codex = nextObservedSession({...row, harness:"codex"}, [], null, 200, 1);
console.log(JSON.stringify({facts:facts.outcomeText, known:facts.outcomeKnown,
  end:facts.landing.endText, hooked:hooked.outcomeText, none:none.outcomeText,
  codex:codex.outcomeText}));
""",
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )
        self.assertNotIn("No stop or end observed", out["facts"])
        self.assertTrue(out["facts"].startswith("Turn stop in Claude Code's transcript"))
        self.assertTrue(out["known"])
        self.assertIn("Claude Code's transcript shows the last turn finished", out["end"])
        # An observed stop still says so; with no stop at all, and on a harness whose
        # transcript stop is not read, the absence stands.
        self.assertTrue(out["hooked"].startswith("Stop observed"))
        self.assertEqual("No stop or end observed", out["none"])
        self.assertEqual("No stop or end observed", out["codex"])


class TheLastTurnLabelReadsATranscriptStopTest(NextPageJsHarness):
    def test_the_work_list_labels_the_turn_a_transcript_stop_closed(self) -> None:
        out = self._run_page_js(
            """
const entries = [{type:"user_message", at:95}, {type:"tool_report", at:97}];
const at = (row) => nextCockpitLastTurn(row, entries);
const base = {harness:"claude", sid:"s1", state:"idle", ended_at:null, annotation_window_start:90};
console.log(JSON.stringify({transcript:at({...base, turn_end_at:100}),
  codex:at({...base, harness:"codex", turn_end_at:100}), none:at(base)}));
""",
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )
        self.assertEqual({"from": 95, "to": 100}, out["transcript"])
        self.assertIsNone(out["codex"])
        self.assertIsNone(out["none"])


class TheSessionPageSaysWhatAnAnalysisReadsTest(NextPageJsHarness):
    def run_fixture(self, checks: str) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )

    CONTROL = """
nextData.annotate = true;
nextData.reading_routes = {
  claude: {provider:"codex", label:"Codex", disclosure:"Codex reads this session."},
  codex: {provider:"codex", label:"Codex", disclosure:"Codex reads this session."}};
nextData.reading_check = "accepted";
const annotation = {goal:"add retry", revision:1, reading_count:0, at:90};
const hint = (session, words = annotation) =>
  nextCockpitReadingControl(session, words, {enabled:true});
"""

    def control_with(self, session: str, words: str) -> str:
        out = self.run_fixture(
            self.CONTROL + f"console.log(JSON.stringify(hint({session}, {words})));"
        )
        assert isinstance(out, str)
        return out

    WAITING = '{harness:"claude", sid:"s1", state:"idle", finished_at:100, ended_at:null}'

    def test_a_reader_with_no_saved_goal_is_not_promised_a_reading(self) -> None:
        html = self.control_with(self.WAITING, "{reading_count:0}")
        self.assertNotIn("Reads the session", html)

    def test_a_refused_control_carries_no_promise_beside_its_refusal(self) -> None:
        html = self.control_with(self.WAITING, "(nextData.reading_check = 'not-run', annotation)")
        self.assertIn('id="next-cockpit-reading-refused"', html)
        self.assertNotIn("Reads the session", html)

    def test_words_saved_after_the_session_ended_are_not_promised_a_reading(self) -> None:
        html = self.control_with(
            '{harness:"claude", sid:"s1", state:"idle", finished_at:100, ended_at:120}',
            "{...annotation, at:500}",
        )
        self.assertNotIn("Reads the session", html)

    def control(self, session: str) -> str:
        out = self.run_fixture(self.CONTROL + f"console.log(JSON.stringify(hint({session})));")
        assert isinstance(out, str)
        return out

    def test_a_reader_of_a_session_waiting_at_its_prompt_is_told_its_last_turn_is_read(
        self,
    ) -> None:
        html = self.control(
            '{harness:"claude", sid:"s1", state:"idle", finished_at:100, ended_at:null}'
        )
        self.assertIn("Reads the session up to its last turn against your intent.", html)
        self.assertNotIn('id="next-cockpit-reading-refused"', html)

    def test_a_reader_of_a_running_session_is_told_it_reads_the_work_so_far(self) -> None:
        html = self.control('{harness:"claude", sid:"s1", state:"working", finished_at:100}')
        self.assertIn("Reads the work so far; the session is still running.", html)

    def test_a_reader_of_an_ended_session_is_told_it_reads_up_to_its_end(self) -> None:
        html = self.control(
            '{harness:"claude", sid:"s1", state:"idle", finished_at:100, ended_at:120}'
        )
        self.assertIn("Reads the session up to its end against your intent.", html)

    def test_a_codex_session_at_a_turn_stop_promises_no_reading_of_its_last_turn(self) -> None:
        html = self.control(
            '{harness:"codex", sid:"s1", state:"idle", finished_at:100, ended_at:null}'
        )
        self.assertNotIn("Reads the session", html)

    def test_work_between_your_message_and_your_save_is_labelled_from_the_last_turn(
        self,
    ) -> None:
        out = self.run_fixture("""
const session = {harness:"claude", sid:"s1", state:"idle", finished_at:95,
  annotation_goal:"add retry", annotation_revision:1, annotation_at:100,
  annotation_window_start:60};
const fact = (fact_id, at, type, summary) => ({fact_id, at, type, summary,
  source_session:{harness:"claude", sid:"s1"}, evidence:{source:"transcript", confidence:"exact"}});
const entries = nextCockpitWorkEntries(session, {facts:[
  fact("before", 50, "task_result", "Summary before the message"),
  fact("message", 60, "user_message", "please add retry"),
  fact("during", 70, "task_result", "Summary during the turn"),
  fact("after", 120, "task_result", "Summary after the save")]});
const html = nextCockpitWorkEvidence(session, {state:"read", entries});
const rows = html.split('<div class="next-cockpit-work-row"').slice(1);
const labelled = rows.filter(row => row.includes("from the last turn"))
  .map(row => (row.match(/Summary [a-z ]+|please add retry/) || [""])[0]);
const running = nextCockpitWorkEvidence({...session, state:"working"}, {state:"read", entries});
const legacy = nextCockpitWorkEvidence({...session, annotation_window_start:null},
  {state:"read", entries});
console.log(JSON.stringify({labelled, running: running.includes("from the last turn"),
  legacy: legacy.includes("from the last turn")}));
""")
        assert isinstance(out, dict)
        self.assertEqual(["Summary during the turn"], out["labelled"])
        self.assertFalse(out["running"], "a running session's work was labelled as a last turn")
        self.assertFalse(out["legacy"], "work was labelled with no stored window start")

    TURNS = """
const fact = (fact_id, at, type, summary) => ({fact_id, at, type, summary,
  source_session:{harness:"claude", sid:"s1"}, evidence:{source:"transcript", confidence:"exact"}});
const facts = {facts:[
  fact("m0", 40, "user_message", "first prompt"),
  fact("old", 50, "task_result", "Summary old turn"),
  fact("m1", 200, "user_message", "second prompt"),
  fact("new", 250, "task_result", "Summary new turn")]};
const labelled = over => {
  const session = {harness:"claude", sid:"s1", state:"idle", finished_at:300,
    annotation_goal:"g", annotation_revision:1, ...over};
  const entries = nextCockpitWorkEntries(session, facts);
  return nextCockpitWorkEvidence(session, {state:"read", entries})
    .split('<div class="next-cockpit-work-row"').slice(1)
    .filter(row => row.includes("from the last turn"))
    .map(row => (row.match(/Summary [a-z ]+/) || [""])[0]);
};
"""

    def labels(self, over: str) -> list[str]:
        out = self.run_fixture(self.TURNS + f"console.log(JSON.stringify(labelled({over})));")
        assert isinstance(out, list)
        return out

    def test_words_saved_before_a_later_turn_label_only_that_later_turn(self) -> None:
        self.assertEqual(
            ["Summary new turn"],
            self.labels("{annotation_at:100, annotation_window_start:40}"),
        )

    def test_a_first_prompt_adopted_after_a_second_turn_labels_only_the_second(self) -> None:
        for window in ("annotation_window_start:40", "annotation_window_start:40, legacy:true"):
            with self.subTest(window=window):
                self.assertEqual(
                    ["Summary new turn"],
                    self.labels(
                        "{annotation_at:310, annotation_goal_source:'first-prompt', "
                        f"annotation_goal_source_at:40, {window}}}"
                    ),
                )

    def test_a_save_made_mid_turn_labels_the_rest_of_that_turn(self) -> None:
        self.assertEqual(
            ["Summary new turn"],
            self.labels("{annotation_at:220, annotation_window_start:200}"),
        )

    READING = """
const annotation = {goal:"add retry", revision:1, at:1000};
const entries = [
  {id:"m1", type:"user_message", by:"", at:60, source:"root transcript · exact",
   summary:"please add retry"},
  {id:"c1", type:"tool_report", subject:"check", result:"failed", at:70, work:true,
   source:"Claude Bash call and paired result · exact", summary:"pytest"}];
const reading = over => ({revision_read:1, revision_read_at:1000, scope:"last-turn",
  scope_text:"A turn stop was observed and no session end was, so this covers the work through the last turn. It is not a reading of how the session ended.",
  criteria:{line_1:{result:"departure", cites:["c1"], detail:"the retry test failed",
    clause:"tests pass"}}, ...over});
const shape = raw => nextCockpitReadingShape(raw, {...annotation, line_1:"tests pass"},
  entries, "", false);
"""

    def test_a_check_after_your_message_carries_a_departure_on_a_last_turn_reading(self) -> None:
        out = self.run_fixture(
            self.READING
            + """
const kept = shape(reading({window_start:60}));
const legacy = shape(reading({}));
console.log(JSON.stringify({kept: kept.departures.length, legacy: legacy.departures.length,
  scope: kept.scopeText, malformed: kept.malformed}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual("", out["malformed"])
        self.assertEqual(1, out["kept"])
        self.assertEqual(0, out["legacy"], "a reading without a window start read before its save")
        self.assertIn("through the last turn", out["scope"])

    def test_the_reading_shows_when_you_saved_and_where_its_work_starts(self) -> None:
        out = self.run_fixture(
            self.READING
            + """
nextData.generated = 4000;
const html = nextCockpitReadingBaseline(shape(reading({window_start:60})));
const legacy = nextCockpitReadingBaseline(shape(reading({})));
console.log(JSON.stringify({html, legacy}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("typed 50m ago", out["html"])
        self.assertIn("reads work from your message 1h 5m ago", out["html"])
        self.assertNotIn("reads work from", out["legacy"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ACheckIsInsideTheWindowWhenItsResultIsTest(unittest.TestCase):
    """DRC-4702, owner 2026-09-27: result time decides the window; call time
    stays for every change comparison and for numbering."""

    def entry(self, at: float, **over: Any) -> dict[str, Any]:
        base = {"type": reading.TOOL_REPORT_TYPE, "subject": "check", "result": "failed", "at": at}
        return base | over

    def test_a_result_that_landed_inside_the_window_admits_the_check(self) -> None:
        entry = self.entry(100, result_at=160)
        self.assertTrue(reading.check_supports(entry, reading.RESULT_DEPARTURE, 150))
        self.assertTrue(reading.check_supports(entry, reading.RESULT_DEPARTURE, 160))
        self.assertFalse(reading.check_supports(entry, reading.RESULT_DEPARTURE, 161))

    def test_a_check_with_no_result_time_is_placed_by_its_call(self) -> None:
        for result_at in (None, 0, -1, "160", True):
            with self.subTest(result_at=result_at):
                entry = self.entry(100, result_at=result_at)
                self.assertFalse(reading.check_supports(entry, reading.RESULT_DEPARTURE, 150))
                self.assertTrue(reading.check_supports(entry, reading.RESULT_DEPARTURE, 100))

    def test_the_ledger_carries_the_result_time_of_a_check(self) -> None:
        ledger = reading.build_ledger(
            [_check(PROMPT - 60, result_at=PROMPT + 30), _check(PROMPT + 60)],
            "claude",
            "s1",
            tool_output={},
        )
        self.assertEqual([PROMPT - 60, PROMPT + 60], [row["at"] for row in ledger])
        self.assertEqual(PROMPT + 30, ledger[0].get("result_at"))
        self.assertNotIn("result_at", ledger[1])


class AReadingCitesNothingFromBeforeItsWindowTest(_PressCase):
    """DRC-4715, owner 2026-09-27: a reading may not cite an entry from before
    its evidence window, of any type, and one with no time cannot be placed
    after the words. `produce` drops both from the prompt, and the resolver
    refuses one as a defence, the way any unresolvable citation is refused."""

    def agent(self, fact_id: str, at: float) -> dict[str, Any]:
        return _message(
            fact_id, at, type="assistant_message", summary="I will rewrite the parser in Go"
        )

    def test_a_pre_window_agent_message_is_not_in_the_prompt(self) -> None:
        assessment, _why, _spent = self.produce(
            [self.agent("a0", PROMPT - 60), _message("m1", PROMPT), _check(PROMPT + 60)]
        )
        self.assertNotIn("rewrite the parser in Go", self.prompts[0])
        self.assertEqual(reading.RESULT_DEPARTURE, assessment["criteria"]["line_1"]["result"])

    def test_an_untimed_entry_is_not_in_the_prompt(self) -> None:
        self.produce([self.agent("a0", 0), _message("m1", PROMPT), _check(PROMPT + 60)])
        self.assertNotIn("rewrite the parser in Go", self.prompts[0])

    def test_a_window_that_leaves_nothing_to_read_says_so(self) -> None:
        assessment, why, spent = self.produce([self.agent("a0", PROMPT - 60), _check(0)])
        self.assertIsNone(assessment)
        self.assertEqual(reading.WITHHELD_WINDOW_EMPTY, why)
        self.assertFalse(spent)
        self.assertEqual([], self.prompts)
        self.assertNotEqual(
            reading.WITHHELD[reading.WITHHELD_LEDGER_EMPTY],
            reading.WITHHELD[reading.WITHHELD_WINDOW_EMPTY],
        )
        _assessment, why, _spent = self.produce([])
        self.assertEqual(reading.WITHHELD_LEDGER_EMPTY, why)

    def test_a_turn_cut_that_empties_the_window_is_not_called_an_empty_window(self) -> None:
        # Review F1 and owner ruling N3: the check is after the words, in a resumed turn the row
        # has not caught up with. Neither "nothing after the words" nor "no entry names this
        # session" is true, so the press says the work after the words is not finished.
        for facts in (
            [_message("m0", PROMPT - 100), _check(STOP + 30)],
            [_message("m0", 0), _check(STOP + 30)],
        ):
            with self.subTest(first_at=facts[0]["at"]):
                assessment, why, spent = self.produce(facts)
                self.assertIsNone(assessment)
                self.assertEqual(reading.WITHHELD_AFTER_STOP, why)
                self.assertFalse(spent)

    def test_the_cutoff_counts_each_set_it_did_not_read(self) -> None:
        # Owner ruling N4, 2026-09-27: earlier, untimed and after-the-stop entries apart.
        assessment, _why, _spent = self.produce(
            [
                self.agent("u0", 0),
                self.agent("a0", PROMPT - 60),
                _message("m1", PROMPT),
                _check(PROMPT + 60),
                _check(STOP + 30),
            ]
        )
        self.assertTrue(
            assessment["cutoff"].startswith(
                "Read 2 of the 2 entries after your words; 1 earlier and 1 untimed entries were "
                "not read; 1 entry after the last observed stop was not read. Of those read, "
            ),
            assessment["cutoff"],
        )

    def test_the_cutoff_says_how_many_entries_before_the_words_were_not_read(self) -> None:
        # Owner ruling F2, 2026-09-27.
        assessment, _why, _spent = self.produce(
            [
                self.agent("a0", PROMPT - 60),
                self.agent("a1", PROMPT - 30),
                _message("m1", PROMPT),
                _check(PROMPT + 60),
            ]
        )
        self.assertTrue(
            assessment["cutoff"].startswith(
                "Read 2 of the 2 entries after your words; 2 earlier entries were not read."
            ),
            assessment["cutoff"],
        )
        assessment, _why, _spent = self.produce([_message("m1", PROMPT), _check(PROMPT + 60)])
        self.assertTrue(
            assessment["cutoff"].startswith("Read 2 of the 2 entries after your words. "),
            assessment["cutoff"],
        )

    def resolve(self, entries: list[reading.LedgerEntry], cites: list[int]) -> Any:
        return reading.resolve(
            {
                "goal": {"token": "departure", "cites": cites, "detail": "it went elsewhere"},
                "line_1": {"token": "departure", "cites": cites, "detail": "the test failed"},
            },
            reading.Selection(tuple(entries)),
            goal="add retry to the webhook",
            lines=["tests pass"],
            detail_cap_chars=240,
            window_start=150.0,
        )

    def ledger_row(self, fact_id: str, at: float, **over: Any) -> reading.LedgerEntry:
        row: reading.LedgerEntry = {
            "id": fact_id,
            "type": "assistant_message",
            "by": "",
            "summary": "I will rewrite the parser in Go",
            "at": at,
            "author": reading.AUTHOR_AGENT,
            "source": "root transcript · exact",
        }
        row.update(cast("Any", over))
        return row

    def check_row(self, fact_id: str, at: float, **over: Any) -> reading.LedgerEntry:
        return self.ledger_row(
            fact_id,
            at,
            type=reading.TOOL_REPORT_TYPE,
            subject="check",
            result="failed",
            summary="pytest (failed, as the tool reported)",
            source="Claude Bash call and paired result · exact",
            work=True,
            **over,
        )

    def test_a_citation_of_a_pre_window_entry_alone_is_refused_as_uncited(self) -> None:
        for at in (50.0, 149.9, 0.0):
            with self.subTest(at=at):
                goal = self.resolve([self.ledger_row("f1", at)], [1])["goal"]
                self.assertEqual(reading.RESULT_UNVERIFIABLE, goal["result"])
                self.assertEqual(reading.WHY_UNCITED, goal["why"])
                self.assertEqual((), goal["cites"])

    def test_an_entry_exactly_at_the_window_start_stays_citable(self) -> None:
        goal = self.resolve([self.ledger_row("f1", 150.0)], [1])["goal"]
        self.assertEqual(reading.RESULT_DEPARTURE, goal["result"])
        self.assertEqual(("f1",), goal["cites"])

    def test_beside_an_in_window_check_only_the_check_stands(self) -> None:
        line = self.resolve([self.ledger_row("f1", 50.0), self.check_row("c1", 160.0)], [1, 2])[
            "line_1"
        ]
        self.assertEqual(reading.RESULT_DEPARTURE, line["result"])
        self.assertEqual(("c1",), line["cites"])

    def test_a_check_whose_result_landed_inside_the_window_is_not_refused(self) -> None:
        line = self.resolve([self.check_row("c1", 100.0, result_at=160.0)], [1])["line_1"]
        self.assertEqual(reading.RESULT_DEPARTURE, line["result"])


WITHHELD_SENTENCES = {
    reading.WITHHELD_LEDGER_EMPTY: (
        "No entry in the observed record names this session, so there is nothing to read your "
        "words against. Absence of evidence is not a reading."
    ),
    reading.WITHHELD_WINDOW_EMPTY: (
        "Every entry in the observed record for this session is from before your words or has "
        "no time, so there is no work after them to read them against."
    ),
    reading.WITHHELD_AFTER_STOP: (
        "Everything after your words came after the session's last observed stop, so there is "
        "nothing finished to read yet."
    ),
}


class WhyAPressOnAWaitingSessionReadsNothingTest(NextPageJsHarness):
    """Owner ruling N3, 2026-09-27: three different reasons, each said only where it is true,
    read off the page a reader sees."""

    def whys(self) -> dict[str, str]:
        case = _PressCase("setUp")
        case.setUp()
        agent = _message("a0", PROMPT - 60, type="assistant_message", summary="I will do it")
        found = {}
        for name, facts in (
            ("empty", []),
            ("before", [agent]),
            ("after the stop", [_message("m0", PROMPT - 100), _check(STOP + 30)]),
        ):
            assessment, why, _spent = case.produce(facts)
            self.assertIsNone(assessment)
            found[name] = why
        case.doCleanups()
        return found

    def test_each_reason_is_rendered_where_it_is_true(self) -> None:
        whys = self.whys()
        self.assertEqual(
            {
                "empty": reading.WITHHELD_LEDGER_EMPTY,
                "before": reading.WITHHELD_WINDOW_EMPTY,
                "after the stop": reading.WITHHELD_AFTER_STOP,
            },
            whys,
        )
        texts = {name: reading.WITHHELD[why] for name, why in whys.items()}
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            f"const texts = {json.dumps(texts)};\n"
            "const session = __dashboard.sessions[0];\n"
            "console.log(JSON.stringify(Object.fromEntries(Object.entries(texts).map(\n"
            "  ([name, text]) => [name, nextCockpitReading(session,\n"
            "    {goal: 'add retry', reading_count: 1, reading_withheld: text}, [],\n"
            "    {enabled: true})]))));\n",
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )
        assert isinstance(out, dict)
        for name, why in whys.items():
            with self.subTest(case=name):
                rendered = html.unescape(re.sub(r"<[^>]+>", " ", out[name]))
                self.assertIn(WITHHELD_SENTENCES[why], " ".join(rendered.split()))
                for other in set(WITHHELD_SENTENCES) - {why}:
                    self.assertNotIn(WITHHELD_SENTENCES[other], " ".join(rendered.split()))
