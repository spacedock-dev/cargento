"""The agent's own words are evidence (owner ruling, 2026-10-03).

"allow whatever the agent says or does to be used as evidence for claims and drift." Each top-level
assistant text message in a Claude Code transcript becomes an `agent_message` fact: its first
sentence the title the page shows, and the whole message, redacted and at most 1,000 characters, in
`agent_words`, which only a reading reads. Like `reader_words` it is in no store and on no page
route. A reading carries the words inside a quarter of the prompt, after the reader's own messages
had their half, and an outcome line may rest on what the agent said. The floor of the drift level
still needs a passing check, and Steer back still says only what departed.

Every message here is placeholder prose, and the one credential shape is the documented
`AKIAIOSFODNN7EXAMPLE`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import http.client
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

from cargento_runtime import (
    aggregate,
    correction,
    levels,
    observer,
    project_context,
    reading,
    records,
    semantic_history,
)

from . import test_next_cockpit as cockpit_tests
from .next_harness import NextPageJsHarness, storage_prelude
from .support import make_server, serve_until_closed
from .test_claude_checks import SHORT
from .test_direction_adoption import _row
from .test_slash_command_direction import NOW, Board, Session

if TYPE_CHECKING:
    from collections.abc import Iterator

FIELD = "agent_words"
OPENING = "I changed the retry to back off exponentially."
# The point is past the first sentence, which is all the title holds.
POINT = "the placeholder webhook test was skipped rather than run"
SAID = f"{OPENING} One thing to flag:\n\n   {POINT}, so nothing checked the retry."
SAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"
BUDGET = 16_384


def say(
    session: Session, text: str, *, model: str = "claude-sonnet-5", **extra: Any
) -> dict[str, Any]:
    """One top-level assistant text record, in Claude Code's recorded shape."""
    row = session._entry("assistant", [{"type": "text", "text": text}], **extra)
    row["message"]["model"] = model
    return row


class _Board(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.board = Board(Path(temp.name))
        self.config, self.state = self.board.config, self.board.state
        self.session: Session = self.board.session

    def events(self) -> list[dict[str, Any]]:
        self.session.save(self.board.path)
        return project_context.agent_message_events(
            self.config, str(self.board.path), "claude", "s1"
        )


class WhatTheAgentSaidBecomesACitableFactTest(_Board):
    def test_one_field_name_on_both_sides(self) -> None:
        self.assertEqual(FIELD, project_context.AGENT_WORDS_FIELD)
        self.assertEqual(FIELD, reading.AGENT_WORDS_FIELD)
        self.assertEqual(1_000, project_context.AGENT_WORDS_CAP_CHARS)
        self.assertEqual(project_context.AGENT_WORDS_CAP_CHARS, reading.LEDGER_WORDS_CAP_CHARS)

    def test_a_text_message_carries_its_words_beside_a_first_sentence_title(self) -> None:
        say(self.session, SAID)
        (event,) = self.events()
        self.assertEqual("agent_say", event["kind"])
        self.assertEqual(OPENING, event["title"])
        self.assertIn(POINT, event[FIELD])
        self.assertNotIn("\n", event[FIELD])
        self.assertTrue(event["record_id"])

    def test_the_words_take_the_titles_redaction_and_their_own_bound(self) -> None:
        say(self.session, f"{OPENING} Used {SAMPLE_KEY} \u202efor {POINT}. " + "word " * 400)
        (event,) = self.events()
        self.assertNotIn(SAMPLE_KEY[:12], event[FIELD])
        self.assertIn(records.SECRET_MARKER, event[FIELD])
        self.assertNotIn("\u202e", event[FIELD])
        self.assertLessEqual(len(event[FIELD]), project_context.AGENT_WORDS_CAP_CHARS)
        self.assertGreater(len(event[FIELD]), project_context.AGENT_WORDS_CAP_CHARS - 20)

    def test_only_the_top_level_agent_speaking_is_read(self) -> None:
        say(self.session, "A subagent's report.", isSidechain=True)
        say(self.session, "Harness bookkeeping.", isMeta=True)
        say(self.session, "API Error: placeholder banner.", model="<synthetic>")
        self.session._entry(
            "assistant", [{"type": "thinking", "thinking": "private reasoning", "signature": "s"}]
        )
        self.session.call("Bash", {"command": "pytest"})
        self.assertEqual([], self.events())
        say(self.session, SAID)
        self.assertEqual([OPENING], [event["title"] for event in self.events()])

    def test_another_harness_has_no_agent_messages_yet(self) -> None:
        say(self.session, SAID)
        self.session.save(self.board.path)
        for harness in ("codex", "pi", "antigravity"):
            with self.subTest(harness=harness):
                self.assertEqual(
                    [],
                    project_context.agent_message_events(
                        self.config, str(self.board.path), harness, "s1"
                    ),
                )

    def test_the_fact_is_citable_and_the_agents(self) -> None:
        say(self.session, SAID)
        (event,) = self.events()
        kind = project_context._SEMANTIC_FACT_TYPES["agent_say"]
        self.assertEqual(reading.AGENT_MESSAGE_TYPE, kind)
        fact = project_context._semantic_fact_from_event(event, "agent_say", kind, "")
        self.assertTrue(fact["evidence"]["source"])
        self.assertEqual(reading.AUTHOR_AGENT, reading.author_of(fact))
        self.assertEqual(event[FIELD], fact[FIELD])
        fact["source_session"] = {"harness": "claude", "sid": "s1"}
        (row,) = reading.build_ledger([fact], "claude", "s1")
        self.assertEqual(OPENING, row["summary"])
        self.assertIn(POINT, row["agent_words"])
        self.assertNotIn("words", row)
        self.assertFalse(row["work"])

    def test_the_frozen_helper_reads_what_the_board_reads(self) -> None:
        say(self.session, SAID)
        self.session.save(self.board.path)
        whole, tail = project_context.frozen_claude_agent_messages(
            self.config, str(self.board.path), "s1", until=NOW
        )
        for facts in (whole, tail):
            (fact,) = facts
            self.assertEqual(reading.AGENT_MESSAGE_TYPE, fact["type"])
            self.assertIn(POINT, fact[FIELD])
        before, _ = project_context.frozen_claude_agent_messages(
            self.config, str(self.board.path), "s1", until=0.0
        )
        self.assertEqual([], before)


def _event(kind: str, at: float, sid: str = "s1", **extra: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "at": at,
        "title": f"{kind} {at}",
        "harness": "claude",
        "sid": sid,
        **extra,
    }


class TheAgentsChatterNeverEvictsTheRecordTest(unittest.TestCase):
    """`MAX_PROJECT_EVENTS` reserves the agent's messages after the checks and the reader's."""

    def setUp(self) -> None:
        self.said = [_event("agent_say", 1_000.0 + n, record_id=f"r{n}") for n in range(300)]
        self.checks = [_event("check_run", 10.0 + n, subject="check") for n in range(5)]
        self.steers = [_event("steer", 20.0 + n) for n in range(5)]

    def test_focused_the_checks_and_the_readers_messages_survive_and_the_agent_fills_the_rest(
        self,
    ) -> None:
        kept = project_context._project_timeline(
            [*self.said, *self.checks, *self.steers], ("claude", "s1")
        )
        kinds = [event["kind"] for event in kept]
        self.assertEqual(project_context.MAX_PROJECT_EVENTS, len(kept))
        self.assertEqual(5, kinds.count("check_run"))
        self.assertEqual(5, kinds.count("steer"))
        self.assertEqual(project_context.MAX_PROJECT_EVENTS - 10, kinds.count("agent_say"))

    def test_unfocused_the_same_holds(self) -> None:
        kept = project_context._project_timeline([*self.said, *self.checks, *self.steers], None)
        kinds = [event["kind"] for event in kept]
        self.assertEqual(5, kinds.count("check_run"))
        self.assertEqual(5, kinds.count("steer"))

    def test_the_agent_is_counted_as_neither_a_direction_nor_work(self) -> None:
        gates, steers, work = project_context._timeline_counts(
            [*self.said[:3], *self.steers[:2], _event("path_written", 5.0)]
        )
        self.assertEqual((0, 2, 1), (gates, steers, work))


def _agent(fact_id: str, at: float, words: str, summary: str = "") -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "type": reading.AGENT_MESSAGE_TYPE,
        "summary": summary or f"{fact_id} opens",
        FIELD: words,
        "at": at,
        "source_session": {"harness": "claude", "sid": "s1"},
        "evidence": {
            "source": "timestamped top-level assistant text record",
            "confidence": "exact",
        },
    }


def _person(fact_id: str, at: float, words: str) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "type": "user_message",
        "summary": f"{fact_id} opens",
        "reader_words": words,
        "at": at,
        "source_session": {"harness": "claude", "sid": "s1"},
        "evidence": {"source": "timestamped non-meta user-role record", "confidence": "exact"},
    }


def _check(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "fact_id": "check-1",
        "type": "tool_report",
        "subject": "check",
        "result": "failed",
        "result_source": "flag",
        "summary": "python3 -m pytest tests/test_retry.py",
        "at": 1_700_000_500.0,
        "evidence": {"source": "Claude Bash call and paired result", "confidence": "exact"},
        "source_session": {"harness": "claude", "sid": "s1"},
        "branch": {"harness": "claude", "sid": "s1", "record_id": "call-1"},
    }
    row.update(overrides)
    return row


def _write() -> dict[str, Any]:
    return _check(
        fact_id="write-1",
        subject="write",
        result="",
        result_source="",
        summary="src/retry.py",
        at=1_700_000_400.0,
        branch={"harness": "claude", "sid": "s1", "record_id": "call-2"},
    )


class TheAgentsWordsNeverCostAVerdictItsEvidenceTest(unittest.TestCase):
    """The 2026-10-01 budget measurements, run again with the agent talking."""

    LINES = ("the retry backs off", "a regression test covers it")

    def prompt(self, facts: list[dict[str, Any]]) -> tuple[str, reading.Selection]:
        ledger = reading.build_ledger(facts, "claude", "s1", tool_output={})
        return reading.build_prompt(
            ledger, goal="ship the retry", lines=self.LINES, max_bytes=BUDGET
        )

    def said(self, count: int, text: str) -> list[dict[str, Any]]:
        return [_agent(f"a{n:02d}", 1_700_000_000.0 + n, f"a{n:02d} {text}") for n in range(count)]

    def whole_rows(self, prompt: str, marker: str) -> list[str]:
        return [line for line in prompt.splitlines() if line.startswith("[") and marker in line]

    def test_fourteen_long_agent_messages_keep_a_failed_check_and_a_write(self) -> None:
        for text in ("SAID " + "w" * 990, "SAID " + "漢" * 990):
            with self.subTest(width=len(text.encode())):
                prompt, selected = self.prompt([*self.said(14, text), _check(), _write()])
                self.assertLessEqual(len(prompt.encode()), BUDGET)
                self.assertIn("python3 -m pytest tests/test_retry.py", prompt)
                self.assertIn("src/retry.py", prompt)
                self.assertEqual((), selected.unread_failures)
                self.assertTrue(selected.asked_output)
                for n in range(14):
                    self.assertIn(f"a{n:02d}", prompt)
                rows = self.whole_rows(prompt, " SAID ")
                self.assertTrue(rows)
                # A quarter, written as a figure so a moved divisor fails here.
                self.assertEqual(4, reading.AGENT_WORDS_SHARE_DIVISOR)
                self.assertLessEqual(sum(len((row + "\n").encode()) for row in rows), BUDGET // 4)

    def test_the_readers_words_go_first_and_keep_their_half(self) -> None:
        people = [
            _person(f"p{n:02d}", 1_700_000_100.0 + n, f"p{n:02d} MINE " + "m" * 990)
            for n in range(20)
        ]
        prompt, _ = self.prompt([*people, *self.said(20, "SAID " + "w" * 990), _check()])
        mine = self.whole_rows(prompt, " MINE ")
        theirs = self.whole_rows(prompt, " SAID ")
        self.assertTrue(mine)
        self.assertLessEqual(len(theirs), len(mine))
        # The reader's words fill their half before any agent message is read whole.
        self.assertGreater(
            sum(len((row + "\n").encode()) for row in mine),
            BUDGET // reading.WORDS_SHARE_DIVISOR - 1_200,
        )
        self.assertIn("python3 -m pytest tests/test_retry.py", prompt)

    def test_where_room_is_left_for_one_whole_message_it_is_the_readers(self) -> None:
        facts = [
            _person("p1", 1_700_000_100.0, "p1 MINE " + "m" * 300),
            _agent("a1", 1_700_000_200.0, "a1 SAID " + "s" * 300),
            _check(),
        ]
        ledger = reading.build_ledger(facts, "claude", "s1", tool_output={})
        for budget in range(2_000, 8_000, 20):
            prompt, _ = reading.build_prompt(
                ledger, goal="ship the retry", lines=self.LINES, max_bytes=budget
            )
            if " MINE " in prompt or " SAID " in prompt:
                break
        else:
            self.fail("no budget sent a message whole")
        self.assertIn(" MINE ", prompt)
        self.assertNotIn(" SAID ", prompt)

    def test_agent_messages_never_crowd_out_the_readers_messages(self) -> None:
        people = [_person(f"p{n:02d}", 1_600_000_000.0 + n, "short") for n in range(5)]
        many = [_agent(f"a{n:03d}", 1_700_000_000.0 + n, "x", "a" * 170) for n in range(200)]
        _prompt, selected = self.prompt([*people, *many, _check()])
        chosen = {row["id"] for row in selected.entries}
        self.assertTrue({f"p{n:02d}" for n in range(5)} <= chosen)
        self.assertIn("check-1", chosen)

    def test_a_short_session_sends_the_agents_message_whole(self) -> None:
        prompt, _ = self.prompt([_agent("a1", 1_700_000_000.0, SAID.replace("\n", " ")), _check()])
        self.assertIn(POINT, prompt)


class AnOutcomeLineRestsOnWhatTheAgentSaidTest(unittest.TestCase):
    """A departure or a consistent on an outcome line may rest on the agent's message."""

    def resolve(self, token: str, cites: tuple[int, ...], facts: list[dict[str, Any]]) -> Any:
        ledger = reading.build_ledger(facts, "claude", "s1", tool_output={})
        _prompt, selected = reading.build_prompt(
            ledger, goal="ship the retry", lines=("the retry backs off",), max_bytes=BUDGET
        )
        return reading.resolve(
            {"line_1": {"token": token, "cites": cites, "detail": ""}},
            selected,
            goal="ship the retry",
            lines=("the retry backs off",),
            detail_cap_chars=200,
        )["line_1"]

    def test_a_departure_citing_an_agent_message_stands(self) -> None:
        row = self.resolve("departure", (1,), [_agent("a1", 1_700_000_000.0, SAID)])
        self.assertEqual(reading.RESULT_DEPARTURE, row["result"])
        self.assertEqual(("a1",), row["cites"])
        self.assertEqual(reading.WHY_STANDS, row["why"])

    def test_a_consistent_resting_only_on_the_agent_stands(self) -> None:
        row = self.resolve("consistent", (1,), [_agent("a1", 1_700_000_000.0, SAID)])
        self.assertEqual(reading.RESULT_CONSISTENT, row["result"])
        self.assertEqual(("a1",), row["cites"])

    def test_the_agents_word_beside_a_check_its_result_contradicts_is_withdrawn(self) -> None:
        facts = [_agent("a1", 1_700_000_600.0, SAID), _check()]
        row = self.resolve("consistent", (1, 2), facts)
        self.assertEqual(reading.RESULT_UNVERIFIABLE, row["result"])
        self.assertEqual(reading.WHY_CHECK_DOES_NOT_SHOW_IT, row["why"])

    def test_a_write_cited_beside_the_agent_does_not_withdraw_it(self) -> None:
        # Not a check, so not the record saying the claim is false (a Q8A shape).
        facts = [_agent("a1", 1_700_000_600.0, SAID), _write()]
        row = self.resolve("consistent", (1, 2), facts)
        self.assertEqual(reading.RESULT_CONSISTENT, row["result"])
        self.assertEqual(("a1",), row["cites"])

    def test_the_level_reads_a_departure_on_it_medium_and_a_consistent_never_the_floor(
        self,
    ) -> None:
        fact = _agent("a1", 1_700_000_000.0, SAID)
        evidence = levels.Evidence((fact,), dict.fromkeys(levels.SCAN_KEYS, 0), 0)

        def level(result: str) -> str:
            stored = {
                "read_at": 1_700_000_900.0,
                "window_start": 1_699_999_000.0,
                "criteria": {
                    "goal": {
                        "result": result,
                        "cites": ["a1"],
                        "detail": "",
                        "clause": "",
                        "why": "",
                    },
                    "line_1": {
                        "result": result,
                        "cites": ["a1"],
                        "detail": "",
                        "clause": "",
                        "why": "",
                    },
                },
            }
            return levels.analysis_level(stored, evidence, outcome_lines=1).level

        self.assertEqual(levels.MEDIUM, level(reading.RESULT_DEPARTURE))
        self.assertEqual(levels.NOT_ENOUGH, level(reading.RESULT_CONSISTENT))


class SteerBackSaysALineDepartedOnWhatTheAgentSaidTest(unittest.TestCase):
    def compose(self, result: str, *, lines_judged: bool = True) -> str:
        fact = {
            **_agent("a1", 112.0, SAID),
            "source_session": {"harness": "claude", "sid": "s1"},
        }
        row = {
            "harness": "claude",
            "sid": "s1",
            "annotation_goal": "Ship the placeholder parser",
            "annotation_line_1": "The retry backs off",
            "annotation_revision": 2,
            "annotation_window_start": 100.0,
            "annotation_assessment": {
                "revision_read": 2,
                "window_start": 100.0,
                "read_at": 120.0,
                "criteria": {
                    "line_1": {"result": result, "cites": ["a1"], "detail": "", "why": ""}
                },
            },
        }
        for k in range(2, 7):
            row[f"annotation_line_{k}"] = ""
        answer = correction.compose(
            row, [fact], floor=100.0, lines_judged=lines_judged, clock=lambda at: f"T{int(at)}"
        )
        return "".join(
            part if isinstance(part, str) else "{" + part["entry"] + "}"
            for part in answer.get("parts", [])
        )

    def test_a_departure_resting_on_the_agent_shows_as_departed(self) -> None:
        self.assertIn(
            "- The retry backs off: departed at T112{a1}", self.compose(reading.RESULT_DEPARTURE)
        )

    def test_a_consistent_resting_on_the_agent_is_never_said_as_the_tool_reported(self) -> None:
        # Nothing departed and nothing failed, so there is nothing to steer from.
        self.assertEqual("", self.compose(reading.RESULT_CONSISTENT))

    def test_the_words_never_reach_the_correction(self) -> None:
        self.assertNotIn(POINT, self.compose(reading.RESULT_DEPARTURE))


class _Collected(_Board):
    """A real Claude Code transcript holding what the agent said, collected as the board does."""

    def setUp(self) -> None:
        super().setUp()
        self.config = dataclasses.replace(self.config, annotations_enabled=True)
        self.board.config = self.config
        say(self.session, SAID)
        self.session.save(self.board.path)

    def application(self) -> Any:
        def collect(*_: Any) -> list[dict[str, Any]]:
            return [_row()]

        spec = aggregate.HarnessSpec(
            key="claude", label="Claude", discover=lambda *_: True, collect=collect
        )
        return aggregate.Application(
            self.config,
            self.state,
            (spec,),
            native_notifier=lambda _p: "",
            popup_notifier=lambda _t, _b: None,
            diagnostic_sink=lambda _m: None,
            clock=lambda: NOW,
        )

    @contextlib.contextmanager
    def serving(self) -> Iterator[int]:
        httpd = make_server(application=self.application())
        thread = serve_until_closed(httpd)
        try:
            with mock.patch.object(observer.CodexGoalModel, "__call__", return_value=None):
                yield httpd.server_port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def get(self, port: int, path: str) -> bytes:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read()
            self.assertEqual(200, response.status, path)
            return body
        finally:
            conn.close()

    def on_disk(self) -> list[str]:
        held = []
        for folder, _dirs, files in os.walk(self.config.state_home):
            for name in files:
                with open(os.path.join(folder, name), "rb") as handle:
                    if POINT.encode() in handle.read():
                        held.append(name)
        return held


class TheAgentsWordsAreNeitherStoredNorPublishedTest(_Collected):
    def test_the_collected_fact_carries_the_words(self) -> None:
        (fact,) = [f for f in self.board.facts() if f.get("summary") == OPENING]
        self.assertEqual(reading.AGENT_MESSAGE_TYPE, fact["type"])
        self.assertIn(POINT, fact[FIELD])

    def test_no_store_on_disk_holds_the_words_or_the_message_after_a_collection(self) -> None:
        self.assertTrue(any(POINT in str(f.get(FIELD)) for f in self.board.facts()))
        self.assertEqual([], self.on_disk())
        with open(semantic_history.store_path(self.config), encoding="utf-8") as handle:
            stored = handle.read()
        # Live only: the history store records the reader's direction and not the agent.
        self.assertNotIn(OPENING, stored)
        self.assertNotIn(reading.AGENT_MESSAGE_TYPE, stored)

    def test_the_page_routes_publish_the_title_and_never_the_words(self) -> None:
        with self.serving() as port:
            context = self.get(port, f"/api/project-context?project=billing&session=claude:{SHORT}")
            plain = self.get(port, "/api/project-context?project=billing")
            data = self.get(port, "/api/data")
        for body in (context, plain, data):
            self.assertNotIn(POINT.encode(), body)
            self.assertNotIn(FIELD.encode(), body)
        facts = json.loads(context)["semantic"]["facts"]
        self.assertIn(OPENING, [f.get("summary") for f in facts])

    def test_for_page_strips_both_words_fields_at_any_depth(self) -> None:
        nested = {"a": [{FIELD: "x", "reader_words": "y", "keep": 1}], FIELD: "z"}
        self.assertEqual({"a": [{"keep": 1}]}, project_context.for_page(nested))


class ThePageShowsWhatTheAgentSaidTest(NextPageJsHarness):
    def run_fixture(self, script: str) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + script,
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )

    def test_an_agent_message_reads_agent_said_and_is_not_counted_as_work(self) -> None:
        out = self.run_fixture("""
const session = {harness:"claude", sid:"s1", state:"working"};
const fact = (fact_id, at, type, summary) => ({fact_id, at, type, summary,
  source_session:{harness:"claude", sid:"s1"}, evidence:{source:"transcript", confidence:"exact"}});
const entries = nextCockpitWorkEntries(session, {facts:[
  fact("m1", 50, "user_message", "please add retry"),
  fact("a1", 60, "agent_message", "I added the retry.")]});
const html = nextCockpitWorkEvidence(session, {state:"read", entries});
console.log(JSON.stringify({html, mix: nextCockpitWorkMix(entries),
  work: entries.map(e => e.work)}));
""")
        self.assertIn("Agent said", out["html"])
        self.assertIn("I added the retry.", out["html"])
        self.assertIn("1 message the agent wrote", out["mix"])
        self.assertIn("0 observed of what it did", out["mix"])
        self.assertEqual([False, False], out["work"])

    def test_the_agent_never_pushes_the_readers_messages_off_the_list(self) -> None:
        out = self.run_fixture("""
const session = {harness:"claude", sid:"s1", state:"working"};
const fact = (fact_id, at, type, summary) => ({fact_id, at, type, summary,
  source_session:{harness:"claude", sid:"s1"}, evidence:{source:"transcript", confidence:"exact"}});
const facts = [];
for(let n = 0; n < 20; n += 1) facts.push(fact(`m${n}`, 10 + n, "user_message", `MINE-${n}`));
for(let n = 0; n < 60; n += 1) facts.push(fact(`a${n}`, 100 + n, "agent_message", `SAID-${n}`));
const entries = nextCockpitWorkEntries(session, {facts});
const html = nextCockpitWorkEvidence(session, {state:"read", entries});
const rows = html.split('<div class="next-cockpit-work-row"').slice(1);
console.log(JSON.stringify({
  mine: rows.filter(row => row.includes("MINE-")).length,
  said: rows.filter(row => row.includes("SAID-")).length,
  html,
}));
""")
        self.assertEqual(20, out["mine"])
        self.assertEqual(10, out["said"])
        self.assertIn("the 10 most recent messages the agent wrote", out["html"])

    def test_a_line_consistent_on_the_agent_alone_says_it_is_not_a_check(self) -> None:
        out = self.run_fixture("""
const session = {harness:"claude", sid:"s1"};
const entries = nextCockpitWorkEntries(session, {facts:[
  {fact_id:"a1", at:95, type:"agent_message", summary:"I added the retry.",
   source_session:{harness:"claude", sid:"s1"},
   evidence:{source:"timestamped top-level assistant text record", confidence:"exact"}}]});
const shape = nextCockpitReadingShape({revision_read_at:50, criteria:{
  line_1:{result:"consistent with the evidence read", cites:["a1"]},
  line_2:{result:"departure", cites:["a1"], detail:"it said it skipped the test"}}},
  {goal:"add retry", line_1:"the retry backs off", line_2:"a test covers it"}, entries, "");
const numbers = new Map([["a1", 3]]);
const byId = new Map(entries.map(e => [e.id, e]));
console.log(JSON.stringify(shape.criteria.map(row =>
  [row.key, row.result, nextCockpitResultStatus(row, numbers, byId)])));
""")
        rows = {key: (result, status) for key, result, status in out}
        self.assertEqual(
            (reading.RESULT_CONSISTENT, "Consistent with what the session said at #3; not a check"),
            rows["line_1"],
        )
        self.assertEqual((reading.RESULT_DEPARTURE, "Departs at #3"), rows["line_2"])

    def test_the_agent_beside_a_check_its_result_contradicts_is_withdrawn_on_the_page(
        self,
    ) -> None:
        out = self.run_fixture("""
const session = {harness:"claude", sid:"s1"};
const entries = nextCockpitWorkEntries(session, {facts:[
  {fact_id:"c1", at:90, type:"tool_report", subject:"check", result:"failed",
   result_source:"flag", summary:"pytest", source_session:{harness:"claude", sid:"s1"},
   evidence:{source:"Claude Bash call and paired result", confidence:"exact"}},
  {fact_id:"a1", at:95, type:"agent_message", summary:"All tests pass.",
   source_session:{harness:"claude", sid:"s1"},
   evidence:{source:"timestamped top-level assistant text record", confidence:"exact"}}]});
const shape = nextCockpitReadingShape({revision_read_at:50, criteria:{
  line_1:{result:"consistent with the evidence read", cites:["c1", "a1"]}}},
  {goal:"add retry", line_1:"the tests pass"}, entries, "");
console.log(JSON.stringify(shape.criteria.map(row => [row.key, row.result, row.why])));
""")
        (row,) = [row for row in out if row[0] == "line_1"]
        self.assertEqual(reading.RESULT_UNVERIFIABLE, row[1])
        self.assertIn("The check it cited does not show this", row[2])

    def test_a_write_cited_beside_the_agent_does_not_withdraw_it_on_the_page(self) -> None:
        out = self.run_fixture("""
const session = {harness:"claude", sid:"s1"};
const entries = nextCockpitWorkEntries(session, {facts:[
  {fact_id:"w1", at:90, type:"tool_report", subject:"write", result:"", summary:"src/retry.py",
   source_session:{harness:"claude", sid:"s1"},
   evidence:{source:"Claude Write call", confidence:"exact"}},
  {fact_id:"a1", at:95, type:"agent_message", summary:"I wrote the retry.",
   source_session:{harness:"claude", sid:"s1"},
   evidence:{source:"timestamped top-level assistant text record", confidence:"exact"}}]});
const shape = nextCockpitReadingShape({revision_read_at:50, criteria:{
  line_1:{result:"consistent with the evidence read", cites:["w1", "a1"]}}},
  {goal:"add retry", line_1:"the retry is written"}, entries, "");
console.log(JSON.stringify(shape.criteria.map(row => [row.key, row.result, row.restsOn])));
""")
        (row,) = [row for row in out if row[0] == "line_1"]
        self.assertEqual([reading.RESULT_CONSISTENT, "agent"], row[1:])

    def test_a_stored_reading_with_either_withdrawn_reason_still_reads_back(self) -> None:
        out = self.run_fixture("""
const shape = nextCockpitReadingShape({revision_read_at:50, criteria:{
  line_1:{result:"not verifiable from available evidence", cites:[], why:"no-work-shown"},
  line_2:{result:"not verifiable from available evidence", cites:[], why:"tells-the-person"}}},
  {goal:"add retry", line_1:"the retry backs off", line_2:"its counts are reported"}, [], "");
console.log(JSON.stringify(shape.criteria.map(row => [row.key, row.result, row.why])));
""")
        rows = {key: (result, why) for key, result, why in out}
        for key in ("line_1", "line_2"):
            with self.subTest(line=key):
                self.assertEqual(reading.RESULT_UNVERIFIABLE, rows[key][0])
                self.assertTrue(rows[key][1])
                self.assertNotIn("could not be read", rows[key][1])
        self.assertIn("what the session told you", rows["line_2"][1])


if __name__ == "__main__":
    unittest.main()
