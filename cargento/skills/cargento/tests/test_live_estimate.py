"""The live drift estimate the session page shows when the reader turns it on (DRC-4696).

Items 2 to 6 of
[DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn):
the live level is `levels.live_level` over the saved intent, computed without a model after every
call that can move it, published on the focused session's project context and nowhere else, and
never stored. "Rose from <level> at #<n>" is recomputed from the same replay every time.

Every transcript here is built from the recorded field shapes (`test_claude_checks.Transcript`).
"""

from __future__ import annotations

import contextlib
import dataclasses
import http.client
import json
import subprocess
import unittest
from typing import Any
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import http_api, levels, live_estimate, observer, project_context

from .support import make_server, serve_until_closed
from .test_claude_checks import SHORT, START
from .test_copied_corrections import _App

GOAL = "Ship the placeholder parser"
LINE = "The parser tests pass"


def saved_row(**extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "harness": "claude",
        "sid": SHORT,
        "annotation_goal": GOAL,
        "annotation_line_1": LINE,
        "annotation_revision": 1,
        "annotation_settled_through": None,
    }
    row.update(extra)
    return row


class RoseFromTest(unittest.TestCase):
    """`levels.rose_from`: where the latest level was reached from a lower one on the scale."""

    def test_a_rise_names_the_level_before_and_the_step_that_reached_it(self) -> None:
        steps = [levels.NOT_ENOUGH, levels.MEDIUM, levels.MEDIUM, levels.HIGH, levels.HIGH]
        self.assertEqual((levels.MEDIUM, 3), levels.rose_from(steps))

    def test_the_latest_rise_counts_when_the_level_rose_twice(self) -> None:
        steps = [levels.MEDIUM, levels.HIGH, levels.MEDIUM, levels.HIGH]
        self.assertEqual((levels.MEDIUM, 3), levels.rose_from(steps))

    def test_nothing_rose_when_it_fell_held_or_came_from_off_the_scale(self) -> None:
        for steps in (
            [],
            [levels.HIGH],
            [levels.HIGH, levels.MEDIUM],
            [levels.MEDIUM, levels.MEDIUM],
            [levels.NOT_ENOUGH, levels.HIGH],
            [levels.NO_LIVE_LEVEL, levels.HIGH],
            [levels.MEDIUM, levels.NOT_ENOUGH],
        ):
            with self.subTest(steps=steps):
                self.assertIsNone(levels.rose_from(steps))

    def test_extreme_rises_from_high_and_none_or_low_rises_to_medium(self) -> None:
        self.assertEqual((levels.HIGH, 1), levels.rose_from([levels.HIGH, levels.EXTREME]))
        self.assertEqual(
            (levels.NONE_OR_LOW, 1), levels.rose_from([levels.NONE_OR_LOW, levels.MEDIUM])
        )


class _Replay(_App):
    """A saved intent and a transcript, replayed as the route replays it."""

    def facts_now(self) -> list[dict[str, Any]]:
        self.session.save(self.path)
        rows, _scan = project_context.claude_tool_reports(self.config, str(self.path), SHORT)
        return [
            project_context._semantic_fact_from_event(row, row["kind"], "tool_report", "")
            for row in rows
        ]

    def estimate(self, row: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        self.session.save(self.path)
        return live_estimate.for_session(
            self.config,
            row or saved_row(),
            str(self.path),
            kwargs.get("facts", []),
            floor=kwargs.get("floor"),
            now=12345.0,
        )


class TheLiveEstimateTest(_Replay):
    def test_it_changes_when_a_check_fails_and_names_where_it_rose(self) -> None:
        # setUp ran `pytest` and it passed; a write after that pass is Medium.
        self.session.write(self.session.cwd + "/src/a.py")
        medium = self.estimate()
        self.assertEqual(levels.MEDIUM, medium["level"])
        self.session.bash("pytest", "1 failed, 4 passed", is_error=True)
        high = self.estimate()
        self.assertEqual(levels.HIGH, high["level"])
        failing = [f for f in self.facts_now() if f.get("result") == "failed"]
        self.assertEqual(1, len(failing))
        self.assertEqual(levels.MEDIUM, high["rose_from"])
        self.assertEqual(failing[0]["fact_id"], high["rose_at"])
        self.assertIn(levels.REASON_FAILED_CHECK, high["reasons"])

    def test_it_reads_not_enough_recorded_yet_with_too_little_recorded(self) -> None:
        # Only a prompt and a write: no check whose latest run passed.
        self.session.rows = self.session.rows[:1]
        self.session.write(self.session.cwd + "/a.py")
        answer = self.estimate()
        self.assertEqual(levels.NOT_ENOUGH, answer["level"])
        self.assertIn(levels.REASON_NO_PASSING_CHECK, answer["reasons"])
        self.assertIsNone(answer["rose_from"])
        self.assertIsNone(answer["rose_at"])

    def test_with_no_saved_revision_there_is_no_live_level(self) -> None:
        self.session.bash("pytest", "1 failed", is_error=True)
        for row in (
            saved_row(annotation_revision=0),
            saved_row(annotation_revision=None, annotation_goal="", annotation_line_1=""),
            saved_row(annotation_goal="", annotation_line_1=""),
        ):
            with (
                self.subTest(row=row),
                # Over a draft nothing is read at all, not merely no level drawn.
                mock.patch.object(
                    project_context, "_work_records", side_effect=AssertionError("read")
                ),
            ):
                answer = self.estimate(row)
                self.assertEqual(levels.NO_LIVE_LEVEL, answer["level"])
                self.assertIsNone(answer["rose_from"])

    def test_a_level_that_fell_says_nothing_rose(self) -> None:
        self.session.bash("pytest", "1 failed", is_error=True)
        self.session.bash("pytest", "5 passed")
        answer = self.estimate()
        self.assertNotEqual(levels.HIGH, answer["level"])
        self.assertIsNone(answer["rose_from"])

    def test_it_carries_the_time_it_was_computed_and_the_revision_it_read(self) -> None:
        answer = self.estimate(saved_row(annotation_revision=3))
        self.assertEqual(12345.0, answer["computed_at"])
        self.assertEqual(3, answer["revision"])
        self.assertEqual(
            {"harness": "claude", "sid": SHORT},
            {"harness": answer["harness"], "sid": answer["sid"]},
        )

    def test_an_unsettled_later_direction_blocks_none_or_low_and_is_never_drift(self) -> None:
        later = {
            "fact_id": "d-1",
            "type": "user_message",
            "at": 50.0,
            "summary": "Also do the lexer",
            "source_session": {"harness": "claude", "sid": SHORT},
            "evidence": {"source": "root transcript", "confidence": "exact"},
        }
        quiet = self.estimate()
        blocked = self.estimate(facts=[later], floor=10.0)
        settled = self.estimate(
            saved_row(annotation_settled_through=60.0), facts=[later], floor=10.0
        )
        self.assertNotIn(levels.REASON_LATER_DIRECTION, quiet["reasons"])
        self.assertEqual(levels.NOT_ENOUGH, blocked["level"])
        self.assertIn(levels.REASON_LATER_DIRECTION, blocked["reasons"])
        self.assertNotIn(levels.REASON_LATER_DIRECTION, settled["reasons"])

    def test_no_model_is_launched_and_nothing_is_written(self) -> None:
        self.session.bash("pytest", "1 failed", is_error=True)
        self.session.save(self.path)
        before = sorted(p.name for p in self.root.rglob("*"))
        with (
            mock.patch.object(subprocess, "Popen", side_effect=AssertionError("a process")),
            mock.patch.object(subprocess, "run", side_effect=AssertionError("a process")),
            mock.patch.object(
                observer.CodexGoalModel, "__call__", side_effect=AssertionError("a model")
            ),
        ):
            answer = live_estimate.for_session(
                self.config, saved_row(), str(self.path), [], floor=None, now=1.0
            )
        self.assertEqual(levels.HIGH, answer["level"])
        self.assertEqual(before, sorted(p.name for p in self.root.rglob("*")))

    def test_the_level_now_is_the_one_the_published_facts_give(self) -> None:
        # The replay's last step and `levels.live_level` over the published record agree.
        self.session.write(self.session.cwd + "/b.py")
        self.session.save(self.path)
        rows, scan = project_context.claude_tool_reports(self.config, str(self.path), SHORT)
        facts = [
            project_context._semantic_fact_from_event(row, row["kind"], "tool_report", "")
            for row in rows
        ]
        direct = levels.live_level(
            levels.Evidence(tuple(facts), scan, 0, str(self.session.cwd)),
            levels.Intent(saved=True, goal=GOAL, lines=(LINE,)),
        )
        self.assertEqual(direct.level, self.estimate()["level"])


class TheRouteTest(_Replay):
    """Published on the focused project context only, over a real socket."""

    @contextlib.contextmanager
    def serving(self) -> Any:
        httpd = make_server(application=self.app())
        thread = serve_until_closed(httpd)
        try:
            yield httpd.server_port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    @staticmethod
    def get(port: int, path: str) -> dict[str, Any]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("GET", path)
            body = conn.getresponse().read()
        finally:
            conn.close()
        answer = json.loads(body)
        assert isinstance(answer, dict)
        return answer

    def save_goal(self) -> None:
        outcome = annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            SHORT,
            goal=GOAL,
            lines=[LINE],
            now=START.timestamp() + self.session.seconds + 1,
        )
        self.assertEqual(annotation_store.OUTCOME_STORED, outcome)

    def test_the_focused_context_publishes_the_live_level_and_nothing_else_does(self) -> None:
        self.save_goal()
        self.session.bash("pytest", "1 failed", is_error=True)
        self.session.save(self.path)
        with self.serving() as port:
            focused = self.get(port, f"/api/project-context?project=billing&session=claude:{SHORT}")
            project = self.get(port, "/api/project-context?project=billing")
            board = self.get(port, "/api/data")
        live = focused["sources"]["work"]["live_levels"]
        self.assertEqual(1, len(live))
        self.assertEqual(
            ("claude", SHORT, levels.HIGH), (live[0]["harness"], live[0]["sid"], live[0]["level"])
        )
        self.assertNotIn("live_levels", project["sources"]["work"])
        # Never on a Sessions row: the board's rows carry no level of any kind.
        self.assertNotIn("live_level", json.dumps(board))
        self.assertNotIn('"level"', json.dumps(board["sessions"]))

    def test_the_entry_it_rose_at_is_one_the_page_holds(self) -> None:
        self.save_goal()
        self.session.write(self.session.cwd + "/src/a.py")
        self.session.bash("pytest", "1 failed", is_error=True)
        self.session.save(self.path)
        with self.serving() as port:
            focused = self.get(port, f"/api/project-context?project=billing&session=claude:{SHORT}")
        live = focused["sources"]["work"]["live_levels"][0]
        self.assertEqual(levels.MEDIUM, live["rose_from"])
        failing = [
            f["fact_id"] for f in focused["semantic"]["facts"] if f.get("result") == "failed"
        ]
        self.assertEqual(failing, [live["rose_at"]])

    def test_the_reading_routes_own_context_carries_no_live_level(self) -> None:
        self.save_goal()
        self.session.bash("pytest", "1 failed", is_error=True)
        self.session.save(self.path)
        app = self.app()
        _rev, body = app.collect_json(show_all=True)
        row = json.loads(body)["sessions"][0]
        context = http_api._session_context(app, row)
        self.assertNotIn("live_levels", json.dumps(context))

    def test_with_annotations_off_nothing_is_published(self) -> None:
        self.config = dataclasses.replace(self.config, annotations_enabled=False)
        with self.serving() as port:
            focused = self.get(port, f"/api/project-context?project=billing&session=claude:{SHORT}")
        self.assertNotIn("live_levels", focused["sources"]["work"])


if __name__ == "__main__":
    unittest.main()
