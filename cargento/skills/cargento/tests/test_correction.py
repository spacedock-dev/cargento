"""Steer back's correction, composed on the server without a model (DRC-4681).

Item 7 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
built to the owner's rulings of 2026-09-28: the approved template, filled only from the goal, each
outcome line with its state, and the cited entries' times. Each entry is a placeholder the page
turns into "#n" or drops, so no fact id, command, check name, tool output or model prose can reach
the text. Over 2,000 characters the consistent lines go first, then the correction is refused
with a sentence; it is never truncated. With nothing to steer from there is no correction.

Every text here is placeholder prose.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import time
import unittest
from typing import Any
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import correction, http_api

from .support import make_server, serve_until_closed
from .test_claude_checks import SHORT, START
from .test_copied_corrections import _App

WHO = {"harness": "claude", "sid": "s1"}
GOAL = "Ship the placeholder parser"
L1 = "The parser tests pass"
L2 = "The lexer is unchanged"
L3 = "Lint is clean"
DEPARTED = "departure"
CONSISTENT = "consistent with the evidence read"
UNVERIFIABLE = "not verifiable from available evidence"

# Planted wherever a fact or a reading carries words that are not the reader's: a command, a check
# name, tool output, model prose, the direction's own text, and a fact id that reads as prose.
PLANTED = (
    "INJECTED-COMMAND",
    "INJECTED-CHECK",
    "INJECTED-OUTPUT",
    "INJECTED-PROSE",
    "INJECTED-DIRECTION",
    "INJECTED-ID",
)


def clock(at: float) -> str:
    return f"T{int(at)}"


def fact(fact_id: str, at: float, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "at": at,
        "type": kind,
        "summary": "placeholder",
        "source_session": dict(WHO),
        "evidence": {"source": "placeholder source", "confidence": "exact"},
        **extra,
    }


def check(fact_id: str, at: float, result: str, **extra: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "subject": "check",
        "result": result,
        "summary": "pytest INJECTED-COMMAND INJECTED-CHECK",
        "output": "INJECTED-OUTPUT",
        "before_last_change": False,
        "changed_after": False,
        **extra,
    }
    return fact(fact_id, at, "tool_report", **fields)


FACTS = (
    check("c-fail", 110, "failed"),
    check("c-pass", 115, "passed"),
    fact("d1", 104, "user_message", summary="INJECTED-DIRECTION"),
    fact("a1", 112, "assistant_message", summary="INJECTED-PROSE"),
)


def reading(**criteria: Any) -> dict[str, Any]:
    return {"revision_read": 2, "window_start": 100.0, "read_at": 120.0, "criteria": criteria}


def row_of(result: str, cites: tuple[str, ...] = (), **extra: Any) -> dict[str, Any]:
    return {"result": result, "cites": list(cites), "detail": "INJECTED-PROSE", **extra}


FULL_READING = reading(
    goal=row_of(CONSISTENT, ("a1",), clause=GOAL),
    line_1=row_of(DEPARTED, ("c-fail",), clause=L1),
    line_2=row_of(UNVERIFIABLE, (), clause=L2, why="uncited"),
    line_3=row_of(CONSISTENT, ("c-pass",), clause=L3),
)


def session_row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "harness": "claude",
        "sid": "s1",
        "annotation_goal": GOAL,
        "annotation_line_1": L1,
        "annotation_line_2": L2,
        "annotation_line_3": L3,
        "annotation_revision": 2,
        "annotation_window_start": 100.0,
        "annotation_settled_through": 114.0,
        "annotation_assessment": FULL_READING,
    }
    for k in range(4, 7):
        row[f"annotation_line_{k}"] = ""
    row.update(over)
    return row


def rendered(parts: list[Any]) -> str:
    """The parts with each placeholder written as `{fact id}`."""
    return "".join(part if isinstance(part, str) else "{" + part["entry"] + "}" for part in parts)


def words(parts: list[Any]) -> str:
    """Only the text the server wrote, as the page would show it with no number drawn."""
    return "".join(part for part in parts if isinstance(part, str))


def compose(row: dict[str, Any] | None = None, facts: Any = FACTS, **kw: Any) -> dict[str, Any]:
    return correction.compose(
        row or session_row(),
        (*facts, fact("p0", 100, "user_message")),
        floor=kw.pop("floor", 100.0),
        lines_judged=kw.pop("lines_judged", True),
        clock=clock,
    )


class TemplateTest(unittest.TestCase):
    def test_every_state_fills_the_approved_template(self) -> None:
        answer = compose()
        self.assertIs(True, answer["ok"])
        self.assertEqual(
            "Back to my goal: Ship the placeholder parser\n"
            "A check failed at T110{c-fail}.\n"
            "Where it stands against what I expect:\n"
            "- The parser tests pass: departed at T110{c-fail}\n"
            "- The lexer is unchanged: can you show evidence for this?\n"
            "- Lint is clean: consistent with T115{c-pass}, as the tool reported\n"
            "Please continue from here.",
            rendered(answer["parts"]),
        )

    def test_a_placeholder_carries_the_fact_id_and_nothing_else(self) -> None:
        for part in compose()["parts"]:
            if not isinstance(part, str):
                self.assertEqual({"entry"}, set(part))

    def test_the_times_are_the_servers_local_clock_by_default(self) -> None:
        answer = correction.compose(session_row(), FACTS, floor=100.0, lines_judged=True)
        self.assertIn(
            f"departed at {time.strftime('%Y-%m-%d %H:%M', time.localtime(110))}",
            words(answer["parts"]),
        )

    def test_a_reading_of_an_older_revision_lends_no_line_its_state(self) -> None:
        answer = compose(session_row(annotation_revision=3))
        text = rendered(answer["parts"])
        self.assertIn("- The parser tests pass: can you show evidence for this?", text)
        self.assertIn("- Lint is clean: can you show evidence for this?", text)
        self.assertIn("A check failed at T110{c-fail}.", text)

    def test_an_unsettled_later_direction_demotes_a_departure(self) -> None:
        text = rendered(compose(session_row(annotation_settled_through=None))["parts"])
        self.assertIn("- The parser tests pass: can you show evidence for this?", text)
        self.assertIn("- Lint is clean: can you show evidence for this?", text)
        self.assertNotIn("later direction", text)

    def test_a_departure_on_a_check_before_the_window_does_not_stand(self) -> None:
        facts = (check("c-fail", 90, "failed"), check("c-pass", 115, "passed"), FACTS[2])
        self.assertEqual({"ok": False, "reason": "nothing"}, compose(facts=facts))

    def test_a_consistent_line_on_an_aged_pass_is_not_shown(self) -> None:
        facts = (
            check("c-fail", 110, "failed"),
            check("c-pass", 115, "passed", before_last_change=True),
        )
        text = rendered(compose(facts=facts)["parts"])
        self.assertIn("- Lint is clean: can you show evidence for this?", text)

    def test_where_no_reading_can_carry_the_checks_no_outcome_line_keeps_a_verdict(self) -> None:
        # The page's Expected Output limit (`nextReadingOutputLimit`): a Claude Code route that
        # cannot name where the checks go demotes every outcome-line verdict, stored or not.
        text = rendered(compose(lines_judged=False)["parts"])
        self.assertIn("- The parser tests pass: can you show evidence for this?", text)
        self.assertIn("- Lint is clean: can you show evidence for this?", text)
        self.assertIn("A check failed at T110{c-fail}.", text)

    def test_a_copied_correction_is_not_a_later_direction(self) -> None:
        facts = (fact("d1", 114, "user_message", copied=True),)
        answer = compose(session_row(annotation_assessment=None), facts)
        self.assertEqual({"ok": False, "reason": "nothing"}, answer)

    def test_another_sessions_facts_are_not_read(self) -> None:
        other = {"harness": "claude", "sid": "s2"}
        facts = (check("c-fail", 110, "failed", source_session=other),)
        answer = compose(session_row(annotation_assessment=None), facts)
        self.assertEqual({"ok": False, "reason": "nothing"}, answer)

    def test_a_goal_alone_leaves_out_the_lines(self) -> None:
        row = session_row(
            annotation_line_1="",
            annotation_line_2="",
            annotation_line_3="",
            annotation_assessment=None,
        )
        self.assertEqual(
            "Back to my goal: Ship the placeholder parser\n"
            "A check failed at T110{c-fail}.\n"
            "Please continue from here.",
            rendered(compose(row)["parts"]),
        )


class SomethingToSteerFromTest(unittest.TestCase):
    def test_with_no_analysis_a_failed_check_is_enough(self) -> None:
        answer = compose(session_row(annotation_assessment=None), (check("c-fail", 110, "failed"),))
        self.assertIs(True, answer["ok"])
        self.assertIn("A check failed at T110{c-fail}.", rendered(answer["parts"]))

    def test_with_no_analysis_a_later_direction_offers_nothing(self) -> None:
        answer = compose(
            session_row(annotation_assessment=None), (fact("d1", 114, "user_message"),)
        )
        self.assertEqual({"ok": False, "reason": "nothing"}, answer)

    def test_consistent_lines_alone_are_nothing_to_steer_from(self) -> None:
        quiet = reading(line_3=row_of(CONSISTENT, ("c-pass",), clause=L3))
        answer = compose(
            session_row(annotation_assessment=quiet), (check("c-pass", 115, "passed"),)
        )
        self.assertEqual({"ok": False, "reason": "nothing"}, answer)

    def test_no_saved_words_is_nothing_to_steer_back_to(self) -> None:
        row = session_row(
            annotation_goal="", annotation_line_1="", annotation_line_2="", annotation_line_3=""
        )
        self.assertEqual({"ok": False, "reason": "nothing"}, compose(row))

    def test_a_failed_check_before_the_words_is_not_one(self) -> None:
        answer = compose(session_row(annotation_assessment=None), (check("c-fail", 90, "failed"),))
        self.assertEqual({"ok": False, "reason": "nothing"}, answer)


class WhatCountsTest(unittest.TestCase):
    """The rules the correction shares with the panel, each on a fixture that tells them apart."""

    def test_a_departure_on_the_goal_alone_is_something_to_steer_from(self) -> None:
        row = session_row(
            annotation_line_1="",
            annotation_line_2="",
            annotation_line_3="",
            annotation_assessment=reading(goal=row_of(DEPARTED, ("a1",))),
        )
        answer = compose(row, (fact("a1", 112, "assistant_message"),), floor=200.0)
        self.assertIs(True, answer["ok"], answer)
        self.assertEqual(
            "Back to my goal: Ship the placeholder parser\n"
            "The session departed from my goal at T112{a1}.\nPlease continue from here.",
            rendered(answer["parts"]),
        )

    def test_only_the_latest_failure_after_the_person_is_named(self) -> None:
        facts = (
            check("c-late", 118, "failed"),
            check("c-fail", 110, "failed"),
            fact("d-late", 116, "user_message"),
            fact("d1", 114, "user_message"),
        )
        row = session_row(annotation_assessment=None, annotation_settled_through=120.0)
        text = rendered(compose(row, facts)["parts"])
        self.assertIn("A check failed at T118{c-late}.", text)
        self.assertNotIn("later direction", text)
        self.assertNotIn("{c-fail}", text)
        self.assertNotIn("{d1}", text)

    def test_a_direction_after_the_settlement_demotes_a_departure(self) -> None:
        facts = (*FACTS, fact("d-late", 116, "user_message"))
        self.assertEqual(
            {"ok": False, "reason": "nothing"},
            compose(session_row(annotation_settled_through=114.0), facts),
        )
        # Settled through it, the same departure stands.
        settled = rendered(compose(session_row(annotation_settled_through=116.0), facts)["parts"])
        self.assertIn("- The parser tests pass: departed at T110{c-fail}", settled)

    def test_a_stored_reason_the_page_knows_leaves_a_departure_standing(self) -> None:
        # The page applies a stored `why` only once its own rules left the row unverifiable
        # (`nextCockpitReadingCriterion`); an unknown one demotes the row as unreadable.
        for why, said in (
            ("uncited", "- The parser tests pass: departed at T110{c-fail}"),
            ("not-asked", "- The parser tests pass: departed at T110{c-fail}"),
            ("made-up", "- The parser tests pass: can you show evidence for this?"),
        ):
            with self.subTest(why=why):
                criteria = {"line_1": row_of(DEPARTED, ("c-fail",), why=why)}
                row = session_row(annotation_assessment=reading(**criteria))
                self.assertIn(said, rendered(compose(row)["parts"]))


class LatestFailedResultTest(unittest.TestCase):
    """DRC-4780: "A check failed at" names the failure whose result arrived last.

    `reading.evidence_at` is the one rule (owner, 2026-09-27, DRC-4702): a check's result time
    where one was recorded and its call time otherwise. The window already counts a failure by it;
    the sentence, its choice among several, and its clock all follow it. The entry stays
    identified by its id, which the page numbers from the call time.
    """

    ROW = session_row(annotation_assessment=None, annotation_settled_through=300.0)

    def text(self, *facts: dict[str, Any]) -> str:
        return rendered(compose(self.ROW, facts)["parts"])

    def test_a_call_before_the_person_with_a_result_after_is_shown_at_the_result(self) -> None:
        # Called at 90, before the person's message at 100, but the result arrived at 140.
        text = self.text(check("c-delayed", 90, "failed", result_at=140))
        self.assertIn("A check failed at T140{c-delayed}.", text)
        self.assertNotIn("T90", text)

    def test_overlapping_failures_name_the_later_result_not_the_later_call(self) -> None:
        # A was called first (90) and returned last (160); B was called later (110), returned at 140.
        text = self.text(
            check("c-a", 90, "failed", result_at=160),
            check("c-b", 110, "failed", result_at=140),
        )
        self.assertIn("A check failed at T160{c-a}.", text)
        self.assertNotIn("{c-b}", text)

    def test_the_choice_does_not_depend_on_the_order_the_facts_arrive_in(self) -> None:
        a = check("c-a", 90, "failed", result_at=160)
        b = check("c-b", 110, "failed", result_at=140)
        for facts in ((a, b), (b, a)):
            with self.subTest(first=facts[0]["fact_id"]):
                self.assertIn("A check failed at T160{c-a}.", self.text(*facts))

    def test_a_result_time_is_what_places_a_failure_after_the_person(self) -> None:
        # Result 95 is still before the person's message at 100: not a failure after them.
        answer = compose(self.ROW, (check("c-early", 90, "failed", result_at=95),))
        self.assertEqual({"ok": False, "reason": "nothing"}, answer)

    def test_a_missing_or_unusable_result_time_falls_back_to_the_call(self) -> None:
        for bad in (None, 0, -5, "later", True):
            with self.subTest(result_at=bad):
                text = self.text(
                    check("c-a", 118, "failed", result_at=bad),
                    check("c-b", 110, "failed", result_at=140),
                )
                self.assertIn("A check failed at T140{c-b}.", text)
        text = self.text(
            check("c-a", 150, "failed", result_at=None),
            check("c-b", 110, "failed", result_at=140),
        )
        self.assertIn("A check failed at T150{c-a}.", text)

    def test_a_departure_on_a_delayed_check_keeps_its_call_time_and_its_entry(self) -> None:
        # Only the failure sentence follows the result; a line's own time is unchanged.
        row = session_row(annotation_settled_through=300.0)
        facts = (check("c-fail", 110, "failed", result_at=140), check("c-pass", 115, "passed"))
        text = rendered(compose(row, facts)["parts"])
        self.assertIn("A check failed at T140{c-fail}.", text)
        self.assertIn("- The parser tests pass: departed at T110{c-fail}", text)

    def test_a_tie_goes_to_the_one_the_page_lists_last(self) -> None:
        # `nextDriftAnswer` keeps the later entry on equal evidence times.
        text = self.text(
            check("c-a", 90, "failed", result_at=140),
            check("c-b", 110, "failed", result_at=140),
        )
        self.assertIn("A check failed at T140{c-b}.", text)


class InjectionTest(unittest.TestCase):
    """Nothing but the reader's words, the connectives and times reaches the text."""

    def test_nothing_planted_in_the_facts_or_the_reading_appears(self) -> None:
        facts = (
            *FACTS,
            check("INJECTED-ID", 118, "failed"),
            fact("o1", 113, "observer_snapshot", summary="INJECTED-PROSE"),
        )
        for row in (
            session_row(),
            session_row(annotation_assessment=None),
            session_row(annotation_settled_through=None),
        ):
            answer = compose(row, facts)
            text = words(answer["parts"])
            for planted in PLANTED:
                with self.subTest(planted=planted):
                    self.assertNotIn(planted, text)

    def test_the_whole_text_is_the_template_around_the_readers_words(self) -> None:
        text = words(compose()["parts"])
        for said in (GOAL, L1, L2, L3):
            text = text.replace(said, "")
        for connective in (
            "Back to my goal: ",
            "Where it stands against what I expect:",
            ": departed at T110",
            ": can you show evidence for this?",
            ": consistent with T115, as the tool reported",
            "A check failed at T110.",
            "I gave a later direction at T114.",
            "Please continue from here.",
            "- ",
        ):
            text = text.replace(connective, "")
        self.assertEqual("", text.replace("\n", ""))


class LengthTest(unittest.TestCase):
    LONG = "x" * 240

    @staticmethod
    def widest(parts: list[Any]) -> int:
        """The length with every number drawn at its widest."""
        placeholders = [part for part in parts if not isinstance(part, str)]
        return len(words(parts)) + (
            len(" (#999999 in Cargento)") + len(" (#999999)") * (len(placeholders) - 1)
            if placeholders
            else 0
        )

    def test_the_consistent_lines_go_first_and_the_rest_stays_whole(self) -> None:
        criteria: dict[str, Any] = {"line_1": row_of(DEPARTED, ("c-fail",))}
        row = session_row(annotation_goal=self.LONG)
        for k in range(1, 7):
            row[f"annotation_line_{k}"] = f"{k}{self.LONG[1:]}"
            if k > 1:
                criteria[f"line_{k}"] = row_of(CONSISTENT, ("c-pass",))
        row["annotation_assessment"] = reading(**criteria)
        answer = compose(row, (check("c-fail", 110, "failed"), check("c-pass", 115, "passed")))
        self.assertIs(True, answer["ok"])
        text = words(answer["parts"])
        self.assertIn(f"- 1{self.LONG[1:]}: departed at T110", text)
        self.assertIn(f"Back to my goal: {self.LONG}", text)
        kept = [k for k in range(2, 7) if f"- {k}{self.LONG[1:]}" in text]
        self.assertLess(len(kept), 5)
        self.assertEqual(list(range(2, 2 + len(kept))), kept, "dropped from the end")
        self.assertLessEqual(self.widest(answer["parts"]), 2000)

    def test_still_too_long_without_them_it_is_refused_with_a_sentence(self) -> None:
        row = session_row(annotation_goal=self.LONG, annotation_assessment=None)
        for k in range(1, 7):
            row[f"annotation_line_{k}"] = f"{k}{self.LONG[1:]}"
        answer = compose(row, (check("c-fail", 118, "failed"), fact("d1", 114, "user_message")))
        self.assertEqual(
            {
                "ok": False,
                "reason": "too-long",
                "why": "This correction would be longer than 2,000 characters. "
                "Shorten a line of your intent.",
            },
            answer,
        )

    def test_each_number_is_counted_at_its_widest(self) -> None:
        # The page draws " (#n in Cargento)" on the first number and " (#n)" after it, so a text
        # that fits only without them is refused rather than let past the cap on the page.
        facts = (check("c-fail", 118, "failed"), fact("d1", 114, "user_message"))
        allowance = len(" (#999999 in Cargento)")

        def with_goal(size: int) -> dict[str, Any]:
            row = session_row(
                annotation_goal="g" * size,
                annotation_line_1="",
                annotation_line_2="",
                annotation_line_3="",
                annotation_assessment=None,
            )
            return compose(row, facts)

        base = len(words(with_goal(1)["parts"])) - 1
        fits = with_goal(2000 - allowance - base)
        self.assertIs(True, fits["ok"])
        self.assertEqual(2000, self.widest(fits["parts"]))
        over = with_goal(2000 - allowance - base + 1)
        self.assertEqual("too-long", over["reason"])
        self.assertLessEqual(len(words(fits["parts"])) + allowance, 2000)


class CorrectionRouteTest(_App):
    """`POST /api/correction` over a real socket, on a real Claude Code transcript."""

    ROUTE = "/api/correction"

    @contextlib.contextmanager
    def serving(self) -> Any:
        httpd = make_server(application=self.app())
        thread = serve_until_closed(httpd)
        try:
            yield httpd.server_port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def post(
        self, port: int, payload: Any, *, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, Any]]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request(
                "POST",
                self.ROUTE,
                body=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", **(headers or {})},
            )
            response = conn.getresponse()
            body = response.read()
        finally:
            conn.close()
        try:
            return response.status, json.loads(body)
        except ValueError:
            return response.status, {}

    def save_goal(self) -> None:
        outcome = annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            SHORT,
            goal="Ship the placeholder parser",
            lines=["The parser tests pass"],
            now=START.timestamp() + self.session.seconds + 1,
        )
        self.assertIn(outcome, {annotation_store.OUTCOME_STORED})

    def test_a_failed_check_after_the_words_composes_a_correction_with_no_command(self) -> None:
        self.save_goal()
        self.session.bash(
            "pytest tests/INJECTED-COMMAND", "INJECTED-OUTPUT\n1 failed", is_error=True
        )
        self.session.save(self.path)
        with self.serving() as port:
            status, answer = self.post(port, {"harness": "claude", "sid": SHORT})
        self.assertEqual(200, status)
        self.assertIs(True, answer["ok"], answer)
        text = words(answer["parts"])
        self.assertTrue(text.startswith("Back to my goal: Ship the placeholder parser\n"), text)
        self.assertIn("- The parser tests pass: can you show evidence for this?\n", text)
        self.assertIn("A check failed at ", text)
        for planted in ("INJECTED-COMMAND", "INJECTED-OUTPUT", "pytest"):
            self.assertNotIn(planted, text)

    def test_a_person_outside_the_tail_still_anchors_the_http_correction(self) -> None:
        self.save_goal()
        self.session.seconds = 90_000
        self.now = START.timestamp() + 91_000
        self.session.bash("python3 -m unittest tests.test_retry", "1 failed", is_error=True)
        call = self.session.call("Read", {"file_path": "src/a.py"})
        self.session.result(call, "placeholder " * 500)
        self.session.save(self.path)
        object.__setattr__(self.config, "tail_bytes", 500)
        with self.serving() as port:
            status, answer = self.post(port, {"harness": "claude", "sid": SHORT})
        self.assertEqual(200, status)
        self.assertTrue(answer["ok"], answer)
        self.assertIn("A check failed", words(answer["parts"]))

    def test_nothing_to_steer_from_and_an_unknown_session_answer_without_a_correction(self) -> None:
        self.save_goal()
        with self.serving() as port:
            quiet = self.post(port, {"harness": "claude", "sid": SHORT})
            unknown = self.post(port, {"harness": "claude", "sid": "unknown-session"})
            other = self.post(port, {"harness": "codex", "sid": SHORT})
        self.assertEqual((200, {"ok": False, "reason": "nothing"}), quiet)
        # One body for all three, so a refusal says nothing about which sessions exist.
        self.assertEqual((200, {"ok": False, "reason": "nothing"}), unknown)
        self.assertEqual((200, {"ok": False, "reason": "nothing"}), other)

    def test_a_codex_session_with_saved_words_and_a_failed_check_gets_no_correction(self) -> None:
        # A real Codex row in the collection, with saved words and a failed check in its record:
        # everything a Claude Code session would be steered from, refused at the harness.
        annotation_store.annotate(
            self.config,
            self.state,
            "codex",
            SHORT,
            goal="Ship the placeholder parser",
            lines=["The parser tests pass"],
            now=START.timestamp() + 1,
        )
        failed = check("c-fail", START.timestamp() + 5, "failed")
        failed["source_session"] = {"harness": "codex", "sid": SHORT}
        read: list[str] = []

        def facts(_handler: Any, row: dict[str, Any]) -> list[Any]:
            read.append(str(row.get("harness")))
            return [failed]

        app = self.app(harness="codex")
        with mock.patch.object(http_api._RequestHandler, "_session_facts", facts):
            httpd = make_server(application=app)
            thread = serve_until_closed(httpd)
            try:
                answer = self.post(httpd.server_port, {"harness": "codex", "sid": SHORT})
            finally:
                httpd.shutdown()
                thread.join(timeout=5)
        codex = [
            row for row in app.collect(show_all=True)["sessions"] if row.get("harness") == "codex"
        ]
        self.assertEqual(1, len(codex), "the fixture has no Codex session")
        self.assertEqual("Ship the placeholder parser", codex[0]["annotation_goal"])
        self.assertEqual((200, {"ok": False, "reason": "nothing"}), answer)
        self.assertEqual([], read)

    def test_it_is_refused_cross_origin_and_on_a_malformed_body(self) -> None:
        with self.serving() as port:
            for headers in (
                {"Origin": "http://evil.example"},
                {"Sec-Fetch-Site": "cross-site"},
                {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"},
            ):
                with self.subTest(headers=headers):
                    self.assertEqual(
                        403,
                        self.post(port, {"harness": "claude", "sid": SHORT}, headers=headers)[0],
                    )
            self.assertEqual(400, self.post(port, {"harness": "claude"})[0])
            self.assertEqual(400, self.post(port, ["claude", SHORT])[0])


if __name__ == "__main__":
    unittest.main()
