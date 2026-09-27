"""DRC-4682's server half: adopting a later direction as an outcome line, and Keep.

DEC-24 item 4 and DEC-16's 2026-09-24 amendment. "Add it to my intent" opens a
later direction's raw text for review and saves it as an outcome line the
server marks as added from that entry; "Keep my intent" settles every
unsettled direction, and over an unsaved draft both adopt the draft in the same
store write. Every text here is placeholder prose, and the one credential shape
is the documented `AKIAIOSFODNN7EXAMPLE`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import http.client
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from cargento_runtime import aggregate, history, http_api, observer, project_context, reading_route
from cargento_runtime import annotations as annotation_store
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

from .support import make_runtime, make_server, serve_until_closed
from .test_claude_checks import SHORT, START, Transcript

FIRST = "Add retry with backoff to the webhook handler."
FIRST_AT = START.timestamp() + 5
NOW = START.timestamp() + 3600
# A 300-character, two-line direction: over the 240 a line may hold, so it
# opens for review and can never be saved as it is.
LONG = (
    "Use the placeholder lexer for every token in the fixture. "
    + "x" * 180
    + ("\nThen keep the parser tests exactly as they are today, please.")
)


def _row(**extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict(runtime_sessions.base_session("claude", SHORT, "billing"))
    row.update(
        {
            "project": "billing",
            "state": "working",
            "active": True,
            "last_activity": NOW,
            "first_prompt": FIRST,
            "first_prompt_at": FIRST_AT,
        }
    )
    row.update(extra)
    return row


def _six(config: Any, state: Any, *, now: float = 20.0) -> None:
    annotation_store.annotate(
        config,
        state,
        "claude",
        SHORT,
        goal="Ship the placeholder parser",
        lines=[f"Line {k}" for k in range(1, 7)],
        now=now,
    )


class _Writes:
    """Every `_write` the store makes, counted, so "one write" is measured."""

    def __init__(self) -> None:
        self.count = 0
        self._real = annotation_store._write

    def __call__(self, *args: Any, **kwargs: Any) -> bool:
        self.count += 1
        return self._real(*args, **kwargs)


class AddDirectionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        self.config, self.state = make_runtime(state_home=home, state_dir=Path(home))
        self.writes = _Writes()
        patcher = mock.patch.object(annotation_store, "_write", self.writes)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _entry(self) -> Any:
        return annotation_store.find(annotation_store.load(self.config), "claude", SHORT)

    def _add(self, **over: Any) -> str:
        arguments: dict[str, Any] = {
            "source_id": "fact:0123456789abcdef",
            "text": "Use the placeholder lexer",
            "entry_at": FIRST_AT + 60,
            "expected_revision": 0,
            "now": FIRST_AT + 120,
        }
        arguments.update(over)
        return annotation_store.add_direction(self.config, self.state, _row(), **arguments)

    def _adopting(self, **over: Any) -> str:
        return self._add(
            adopt="first-prompt", expected_prompt=FIRST, expected_prompt_at=FIRST_AT, **over
        )

    def test_over_a_draft_one_write_holds_the_goal_the_line_and_the_settlement(self) -> None:
        self.assertEqual(annotation_store.OUTCOME_STORED, self._adopting())
        self.assertEqual(1, self.writes.count)
        entry = self._entry()
        revision = entry["revisions"][-1]
        self.assertEqual(1, revision["n"])
        self.assertEqual(FIRST, revision["goal"])
        self.assertEqual("first-prompt", revision["goal_source"])
        self.assertEqual(FIRST_AT, revision["goal_source_at"])
        self.assertEqual(
            (
                {
                    "text": "Use the placeholder lexer",
                    "source": "entry",
                    "source_id": "fact:0123456789abcdef",
                },
            ),
            revision["lines"],
        )
        self.assertEqual(
            {"at": FIRST_AT + 120, "through": FIRST_AT + 60, "revision": 1}, entry["settled"]
        )

    def test_a_refused_adoption_writes_nothing_at_all(self) -> None:
        outcome = self._add(
            adopt="first-prompt", expected_prompt="Different words", expected_prompt_at=FIRST_AT
        )
        self.assertEqual(annotation_store.OUTCOME_REFUSED, outcome)
        self.assertEqual(0, self.writes.count)
        self.assertIsNone(self._entry())

    def test_an_untrusted_store_is_never_written_over(self) -> None:
        path = Path(annotation_store.store_path(self.config))
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(annotation_store.OUTCOME_UNTRUSTED, self._adopting())
        self.assertEqual(0, self.writes.count)
        self.assertEqual("{not json", path.read_text(encoding="utf-8"))

    def test_a_stale_page_is_refused_by_its_revision(self) -> None:
        _six(self.config, self.state)
        before = self.writes.count
        self.assertEqual(
            annotation_store.OUTCOME_REFUSED, self._add(expected_revision=0, replace=0)
        )
        self.assertEqual(before, self.writes.count)
        self.assertEqual(annotation_store.OUTCOME_REFUSED, self._add(expected_revision=None))

    def test_a_full_list_is_refused_without_an_explicit_replacement(self) -> None:
        _six(self.config, self.state)
        before = self.writes.count
        self.assertEqual(annotation_store.OUTCOME_REFUSED, self._add(expected_revision=1))
        self.assertEqual(before, self.writes.count)
        self.assertEqual(6, len(self._entry()["revisions"][-1]["lines"]))
        for bad in (-1, 6, True, "1"):
            with self.subTest(replace=bad):
                self.assertEqual(
                    annotation_store.OUTCOME_REFUSED, self._add(expected_revision=1, replace=bad)
                )

    def test_replacing_names_one_line_and_every_other_line_keeps_its_source(self) -> None:
        _six(self.config, self.state)
        self.assertEqual(
            annotation_store.OUTCOME_STORED,
            self._add(expected_revision=1, replace=2, source_id="fact:aaaa"),
        )
        # Typed words are floored at their latest save, so the add itself moved
        # the floor past every direction given before it (the page's own rule).
        self.assertEqual(
            annotation_store.OUTCOME_REFUSED,
            self._add(expected_revision=2, replace=4, source_id="fact:bbbb", text="Second"),
        )
        self.assertEqual(
            annotation_store.OUTCOME_STORED,
            self._add(
                expected_revision=2,
                replace=4,
                source_id="fact:bbbb",
                text="Second",
                entry_at=FIRST_AT + 130,
                now=FIRST_AT + 140,
            ),
        )
        lines = self._entry()["revisions"][-1]["lines"]
        self.assertEqual(6, len(lines))
        self.assertEqual(
            ["Line 1", "Line 2", "Use the placeholder lexer", "Line 4", "Second", "Line 6"],
            [line["text"] for line in lines],
        )
        self.assertEqual(
            {"text": "Use the placeholder lexer", "source": "entry", "source_id": "fact:aaaa"},
            lines[2],
        )
        self.assertEqual("typed", lines[0]["source"])

    def test_a_long_or_multi_line_direction_is_refused_never_clipped(self) -> None:
        self.assertEqual(annotation_store.OUTCOME_REFUSED, self._adopting(text=LONG))
        self.assertEqual(0, self.writes.count)
        self.assertEqual(annotation_store.OUTCOME_REFUSED, self._adopting(text="   "))
        # Within 240 once collapsed, a pasted line break is one space, as a
        # typed line's is, and nothing is summarised.
        self.assertEqual(
            annotation_store.OUTCOME_STORED, self._adopting(text="First half\nsecond half")
        )
        self.assertEqual(
            "First half second half", self._entry()["revisions"][-1]["lines"][0]["text"]
        )

    def test_a_direction_that_is_not_later_than_the_words_is_refused(self) -> None:
        for at in (FIRST_AT, FIRST_AT - 1, None, True, FIRST_AT + 999_999):
            with self.subTest(at=at):
                self.assertEqual(annotation_store.OUTCOME_REFUSED, self._adopting(entry_at=at))
        self.assertEqual(0, self.writes.count)

    def test_the_settlement_never_moves_back_over_one_already_given(self) -> None:
        annotation_store.adopt(
            self.config,
            self.state,
            _row(),
            source="first-prompt",
            expected_text=FIRST,
            expected_at=FIRST_AT,
            now=FIRST_AT + 10,
        )
        annotation_store.settle(
            self.config, self.state, "claude", SHORT, through=FIRST_AT + 90, now=FIRST_AT + 100
        )
        self.assertEqual(annotation_store.OUTCOME_STORED, self._add(expected_revision=1))
        settled = self._entry()["settled"]
        self.assertEqual(FIRST_AT + 90, settled["through"])
        self.assertEqual(2, settled["revision"])

    def test_adopted_words_keep_their_floor_so_a_later_direction_stays_open(self) -> None:
        annotation_store.adopt(
            self.config,
            self.state,
            _row(),
            source="first-prompt",
            expected_text=FIRST,
            expected_at=FIRST_AT,
            now=FIRST_AT + 10,
        )
        self.assertEqual(annotation_store.OUTCOME_STORED, self._add(expected_revision=1))
        published = annotation_store.published(self._entry())
        self.assertEqual(FIRST_AT, published["goal_source_at"])
        self.assertEqual(FIRST_AT + 60, published["settled_through"])
        self.assertEqual("entry", published["line_1_source"])
        self.assertEqual("fact:0123456789abcdef", published["line_1_source_id"])


class KeepStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        self.config, self.state = make_runtime(state_home=home, state_dir=Path(home))

    def test_keep_over_a_draft_adopts_and_settles_in_one_write(self) -> None:
        writes = _Writes()
        with mock.patch.object(annotation_store, "_write", writes):
            outcome = annotation_store.adopt(
                self.config,
                self.state,
                _row(),
                source="first-prompt",
                expected_text=FIRST,
                expected_at=FIRST_AT,
                now=FIRST_AT + 200,
                settle_through=FIRST_AT + 150,
            )
        self.assertEqual(annotation_store.OUTCOME_STORED, outcome)
        self.assertEqual(1, writes.count)
        entry = annotation_store.load(self.config)[0]
        self.assertEqual(FIRST, entry["revisions"][-1]["goal"])
        self.assertEqual(
            {"at": FIRST_AT + 200, "through": FIRST_AT + 150, "revision": 1}, entry["settled"]
        )

    def test_a_refused_keep_settles_nothing(self) -> None:
        outcome = annotation_store.adopt(
            self.config,
            self.state,
            _row(),
            source="first-prompt",
            expected_text="Other words",
            expected_at=FIRST_AT,
            now=FIRST_AT + 200,
            settle_through=FIRST_AT + 150,
        )
        self.assertEqual(annotation_store.OUTCOME_REFUSED, outcome)
        self.assertEqual((), annotation_store.load(self.config))
        for bad in (True, "soon", float("nan")):
            with self.subTest(through=bad):
                self.assertEqual(
                    annotation_store.OUTCOME_REFUSED,
                    annotation_store.adopt(
                        self.config,
                        self.state,
                        _row(),
                        source="first-prompt",
                        expected_text=FIRST,
                        expected_at=FIRST_AT,
                        now=FIRST_AT + 200,
                        settle_through=bad,
                    ),
                )

    def test_keep_over_words_already_adopted_still_settles(self) -> None:
        arguments: dict[str, Any] = {
            "source": "first-prompt",
            "expected_text": FIRST,
            "expected_at": FIRST_AT,
        }
        annotation_store.adopt(self.config, self.state, _row(), now=FIRST_AT + 10, **arguments)
        outcome = annotation_store.adopt(
            self.config,
            self.state,
            _row(),
            now=FIRST_AT + 200,
            expected_revision=1,
            settle_through=FIRST_AT + 150,
            **arguments,
        )
        self.assertEqual(annotation_store.OUTCOME_STORED, outcome)
        entry = annotation_store.load(self.config)[0]
        self.assertEqual(1, len(entry["revisions"]))
        self.assertEqual(FIRST_AT + 150, entry["settled"]["through"])


class DirectionReviewTest(unittest.TestCase):
    def test_the_review_text_is_whole_one_line_redacted_and_says_whether_it_fits(self) -> None:
        text, clipped, fits = annotation_store.direction_review(LONG, 240)
        self.assertEqual(" ".join(LONG.split()), text)
        self.assertGreater(len(text), 240)
        self.assertFalse(clipped)
        self.assertFalse(fits)
        text, clipped, fits = annotation_store.direction_review(
            "Rotate AKIAIOSFODNN7EXAMPLE\nthen stop", 240
        )
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", text)
        self.assertNotIn("\n", text)
        self.assertEqual((False, True), (clipped, fits))
        huge = "word " * 2000
        text, clipped, fits = annotation_store.direction_review(huge, 240)
        self.assertLessEqual(len(text), annotation_store.DIRECTION_TEXT_CAP_CHARS)
        self.assertEqual((True, False), (clipped, fits))


class _ClaudeSession(unittest.TestCase):
    """A real Claude Code transcript under a store root the resolver globs."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        cwd = self.root / "work" / "billing"
        cwd.mkdir(parents=True)
        self.path = self.root / "claude" / "projects" / "-work-billing" / f"{SHORT}-full.jsonl"
        self.config = build_runtime_config(
            environ={"HOME": str(self.root), "CARGENTO_HOME": str(self.root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
            store_root_overrides={"claude.projects": str(self.root / "claude" / "projects")},
        )
        self.state = build_runtime_state(self.config, started=NOW)
        patcher = mock.patch.object(observer.CodexGoalModel, "__call__", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.session = Transcript(cwd)
        self.session.prompt(FIRST)
        self.session.bash("pytest", "5 passed")
        self.session.prompt(LONG)
        self.session.save(self.path)

    def facts(self) -> list[dict[str, Any]]:
        context = project_context.collect(
            self.config, self.state, [_row()], "billing", now=NOW, focus=("claude", SHORT)
        )
        return list(context["semantic"]["facts"])

    def direction(self) -> dict[str, Any]:
        return next(
            fact
            for fact in self.facts()
            if fact.get("type") == "user_message" and float(fact["at"]) > FIRST_AT
        )


class DirectionReReadTest(_ClaudeSession):
    def test_the_recomputed_fact_id_finds_the_full_text_of_a_claude_message(self) -> None:
        fact = self.direction()
        # The summary is the first sentence clipped; the re-read is the message.
        self.assertLess(len(str(fact["summary"])), len(LONG))
        self.assertEqual(
            LONG,
            project_context.direction_text(
                self.config, self.state, "claude", SHORT, str(fact["fact_id"])
            ),
        )

    def test_claude_user_message_ids_still_carry_no_record_id(self) -> None:
        # Claude spells it `uuid`; joining it to the hash would move every
        # stored citation of a Claude user message (the 2026-09-12 precedent).
        fact = self.direction()
        self.assertNotIn("record_id", fact.get("branch") or {})

    def test_an_unknown_id_or_a_message_older_than_the_tail_reads_nothing(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        self.assertEqual(
            "",
            project_context.direction_text(self.config, self.state, "claude", SHORT, "fact:0"),
        )
        for _ in range(40):
            self.session.bash("pytest", "p" * 200)
        self.session.save(self.path)
        narrow = dataclasses.replace(self.config, tail_bytes=4096)
        self.assertEqual(
            "", project_context.direction_text(narrow, self.state, "claude", SHORT, fact_id)
        )


class DirectionRouteTest(_ClaudeSession):
    """`POST /api/direction` and the `add_direction` arm over a real socket."""

    def _app(self, **row: Any) -> Any:
        def collect(
            config: Any, state: Any, now: float, window_hours: float, show_all: bool
        ) -> list[dict[str, Any]]:
            del config, state, now, window_hours, show_all
            return [_row(**row)]

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
    def _serving(self, application: Any | None = None) -> Any:
        httpd = make_server(application=application or self._app())
        thread = serve_until_closed(httpd)
        try:
            yield httpd.server_port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    @staticmethod
    def _post(
        port: int,
        path: str,
        payload: Any,
        *,
        headers: dict[str, str] | None = None,
        declared: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            if declared is None:
                conn.request(
                    "POST",
                    path,
                    body=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json", **(headers or {})},
                )
            else:
                conn.putrequest("POST", path)
                conn.putheader("Content-Length", declared)
                conn.endheaders()
            response = conn.getresponse()
            body = response.read()
        finally:
            conn.close()
        try:
            return response.status, json.loads(body)
        except ValueError:
            return response.status, {}

    def _open(self, port: int, fact_id: str, **over: Any) -> tuple[int, dict[str, Any]]:
        return self._post(
            port,
            "/api/direction",
            {"harness": "claude", "sid": SHORT, "fact_id": fact_id, **over},
        )

    def test_open_returns_the_whole_direction_and_says_it_does_not_fit(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        with self._serving() as port:
            status, body = self._open(port, fact_id)
        self.assertEqual(200, status)
        self.assertEqual(
            {
                "ok": True,
                "fact_id": fact_id,
                "text": " ".join(LONG.split()),
                "clipped": False,
                "fits": False,
            },
            body,
        )

    def test_a_long_direction_on_a_list_of_six_is_never_saved_clipped(self) -> None:
        _six(self.config, self.state)
        fact_id = str(self.direction()["fact_id"])
        add = {
            "harness": "claude",
            "sid": SHORT,
            "add_direction": fact_id,
            "expected_revision": 1,
            "replace": 5,
        }
        with self._serving() as port:
            _, opened = self._open(port, fact_id)
            status, refused = self._post(port, "/api/annotate", {**add, "text": opened["text"]})
            self.assertEqual((200, "refused"), (status, refused["outcome"]))
            edited = "Use the placeholder lexer; keep the parser tests"
            status, stored = self._post(port, "/api/annotate", {**add, "text": edited})
        self.assertEqual("stored", stored["outcome"])
        lines = annotation_store.load(self.config)[0]["revisions"][-1]["lines"]
        self.assertEqual(6, len(lines))
        self.assertEqual({"text": edited, "source": "entry", "source_id": fact_id}, lines[5])
        self.assertNotIn(opened["text"], json.dumps(annotation_store.load(self.config)))

    def test_add_over_the_draft_adopts_it_in_the_same_request(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        with self._serving() as port:
            status, body = self._post(
                port,
                "/api/annotate",
                {
                    "harness": "claude",
                    "sid": SHORT,
                    "add_direction": fact_id,
                    "text": "Use the placeholder lexer",
                    "expected_revision": 0,
                    "adopt": "first-prompt",
                    "expected_prompt": FIRST,
                    "expected_prompt_at": FIRST_AT,
                },
            )
        self.assertEqual((200, "stored", 1), (status, body["outcome"], body["revision"]))
        entry = annotation_store.load(self.config)[0]
        self.assertEqual(FIRST, entry["revisions"][-1]["goal"])
        self.assertEqual(self.direction()["at"], entry["settled"]["through"])

    def test_every_unopenable_direction_answers_one_body(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        first_id = next(
            str(f["fact_id"])
            for f in self.facts()
            if f.get("type") == "user_message" and float(f["at"]) == FIRST_AT
        )
        tool_id = next(str(f["fact_id"]) for f in self.facts() if f.get("type") != "user_message")
        with self._serving() as port:
            answers = [
                self._open(port, "fact:0"),
                self._open(port, tool_id),
                self._open(port, first_id),
                self._open(port, fact_id, sid="nobody00"),
                self._open(port, fact_id, harness="codex"),
            ]
        expected = (
            200,
            {"ok": False, "reason": "unavailable", "why": annotation_store.DIRECTION_UNAVAILABLE},
        )
        for answer in answers:
            self.assertEqual(expected, answer)

    def test_a_direction_older_than_the_tail_is_refused_not_summarised(self) -> None:
        # The fact still resolves (history keeps it) while the tail no longer
        # holds its record, which is exactly when the 112-character summary
        # would be the only text left to save.
        fact_id = str(self.direction()["fact_id"])
        real = project_context.direction_text

        def aged(config: Any, *rest: Any) -> str:
            return real(dataclasses.replace(config, tail_bytes=16), *rest)

        with (
            mock.patch.object(project_context, "direction_text", aged),
            self._serving() as port,
        ):
            status, body = self._open(port, fact_id)
            _, added = self._post(
                port,
                "/api/annotate",
                {
                    "harness": "claude",
                    "sid": SHORT,
                    "add_direction": fact_id,
                    "text": "Use the placeholder lexer",
                    "expected_revision": 0,
                    "adopt": "first-prompt",
                    "expected_prompt": FIRST,
                    "expected_prompt_at": FIRST_AT,
                },
            )
        self.assertEqual((200, "unavailable"), (status, body["reason"]))
        self.assertEqual("refused", added["outcome"])
        self.assertEqual((), annotation_store.load(self.config))

    def test_the_text_comes_back_redacted(self) -> None:
        self.session.prompt("Rotate AKIAIOSFODNN7EXAMPLE before the release")
        self.session.save(self.path)
        fact = next(
            f
            for f in self.facts()
            if f.get("type") == "user_message" and "before" in str(f["summary"])
        )
        with self._serving() as port:
            _, body = self._open(port, str(fact["fact_id"]))
        self.assertTrue(body["ok"])
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", body["text"])

    def test_the_route_is_guarded_as_the_intent_routes_are(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        body = {"harness": "claude", "sid": SHORT, "fact_id": fact_id}
        cases = (
            ("cross-site origin", {"Origin": "http://evil.example"}, 403),
            ("another local port", {"Origin": "http://127.0.0.1:1"}, 403),
            ("rebound host", {"Host": "evil.example"}, 403),
            ("cross-site fetch", {"Sec-Fetch-Site": "cross-site"}, 403),
            ("same-site fetch", {"Sec-Fetch-Site": "same-site"}, 403),
            (
                "document navigation",
                {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"},
                403,
            ),
        )
        with self._serving() as port:
            for label, headers, code in cases:
                with self.subTest(shape=label):
                    status, answer = self._post(port, "/api/direction", body, headers=headers)
                    self.assertEqual(code, status)
                    self.assertNotIn("text", answer)
            status, _ = self._post(
                port,
                "/api/direction",
                None,
                declared=str(self.config.annotation_body_cap_bytes + 1),
            )
            self.assertEqual(413, status)
            malformed: list[dict[str, Any]] = [
                {**body, "fact_id": {"x": 1}},
                {**body, "sid": 7},
                {"harness": "claude"},
            ]
            for bad in malformed:
                self.assertEqual(400, self._post(port, "/api/direction", bad)[0])
            for bad in (
                {
                    "harness": "claude",
                    "sid": SHORT,
                    "add_direction": fact_id,
                    "text": ["x"],
                    "expected_revision": 0,
                },
                {
                    "harness": "claude",
                    "sid": SHORT,
                    "add_direction": fact_id,
                    "text": "x",
                    "expected_revision": 0,
                    "replace": True,
                },
                {
                    "harness": "claude",
                    "sid": SHORT,
                    "add_direction": 5,
                    "text": "x",
                    "expected_revision": 0,
                },
                {
                    "harness": "claude",
                    "sid": SHORT,
                    "lines": [{"text": "x", "source": "entry", "source_id": fact_id}],
                },
            ):
                self.assertEqual(400, self._post(port, "/api/annotate", bad)[0])

    def test_the_route_answers_503_with_annotations_off(self) -> None:
        self.config = dataclasses.replace(self.config, annotations_enabled=False)
        with self._serving() as port:
            status, _ = self._open(port, str(self.direction()["fact_id"]))
        self.assertEqual(503, status)

    def test_no_full_prompt_text_reaches_the_payload_or_session_history(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        with self._serving() as port:
            self._open(port, fact_id)
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/api/data")
            data = conn.getresponse().read().decode("utf-8")
            conn.close()
        tail = "Then keep the parser tests exactly as they are today"
        self.assertNotIn(tail, data)
        store = Path(history.store_path(self.config))
        self.assertNotIn(tail, store.read_text(encoding="utf-8") if store.exists() else "")
        self.assertFalse(
            [name for name in history.OBSERVATION_FIELDS if "direction" in name],
            "a direction's text became a history field",
        )


class KeepRouteTest(unittest.TestCase):
    """Keep on both routes: settling needs no reader, and a press settles first."""

    def _runtime(self) -> Any:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        return make_runtime(state_home=home, state_dir=Path(home))

    def _handler(self, config: Any, state: Any, payload: dict[str, Any]) -> Any:
        from cargento_runtime import cli  # noqa: PLC0415

        app: Any = cli.build_application(config, state, clock=lambda: NOW)
        app.collect_json = lambda **_: (1, json.dumps({"sessions": [_row()]}).encode())
        handler: Any = object.__new__(http_api._RequestHandler)
        handler.server = SimpleNamespace(application=app, server_port=4580)
        self.replies: list[tuple[dict[str, Any], int]] = []
        handler._send = lambda body, _ctype, code=200, **_k: self.replies.append(
            (json.loads(body), code)
        )
        handler._reject = lambda code, *_a: self.replies.append(({}, code))
        body = json.dumps(payload).encode()
        handler.headers = {"Host": "127.0.0.1:4580", "Content-Length": str(len(body))}
        handler.client_address = ("127.0.0.1", 10000)
        handler.rfile = io.BytesIO(body)
        return handler

    KEEP: dict[str, Any] = {  # noqa: RUF012
        "harness": "claude",
        "sid": SHORT,
        "adopt": "first-prompt",
        "expected_prompt": FIRST,
        "expected_prompt_at": FIRST_AT,
        "settle_through": FIRST_AT + 60,
    }

    def test_keep_with_no_reader_settles_on_the_annotate_route(self) -> None:
        config, state = self._runtime()
        handler = self._handler(config, state, {**self.KEEP, "expected_revision": 0})
        handler._annotate()
        answer, code = self.replies[-1]
        self.assertEqual((200, "stored"), (code, answer["outcome"]))
        entry = annotation_store.load(config)[0]
        self.assertEqual(FIRST, entry["revisions"][-1]["goal"])
        self.assertEqual(FIRST_AT + 60, entry["settled"]["through"])

    def _press(self, config: Any, state: Any, **over: Any) -> Any:
        payload = {
            **self.KEEP,
            "press": True,
            "observer_model": 1,
            "provider": "codex",
            "allow": True,
            **over,
        }
        handler = self._handler(config, state, payload)
        with (
            mock.patch.object(shutil, "which", lambda name: f"/usr/local/bin/{name}"),
            mock.patch.object(reading_route, "destination", return_value=""),
            mock.patch.object(
                handler, "_compose_reading", return_value=(None, "test", False)
            ) as compose,
        ):
            handler._reading()
        return compose

    def test_the_keep_press_adopts_and_settles_before_the_job(self) -> None:
        config, state = self._runtime()
        compose = self._press(config, state)
        self.assertEqual(1, compose.call_count)
        entry = compose.call_args.args[1]
        self.assertEqual(FIRST, entry["revisions"][-1]["goal"])
        self.assertEqual(FIRST_AT + 60, entry["settled"]["through"])
        answer, code = self.replies[-1]
        self.assertEqual((202, "stored"), (code, answer["settled"]))

    def test_a_press_that_cannot_start_still_leaves_the_settlement(self) -> None:
        config, state = self._runtime()
        compose = self._press(config, state, provider="someone-else")
        self.assertEqual(0, compose.call_count)
        answer, code = self.replies[-1]
        self.assertEqual(
            (409, "provider-changed", "stored"), (code, answer["reason"], answer["settled"])
        )
        self.assertEqual(FIRST_AT + 60, annotation_store.load(config)[0]["settled"]["through"])

    def test_a_refused_keep_starts_nothing_and_settles_nothing(self) -> None:
        config, state = self._runtime()
        compose = self._press(config, state, expected_prompt="Other words")
        self.assertEqual(0, compose.call_count)
        answer, code = self.replies[-1]
        self.assertEqual(
            (422, True, "refused"), (code, answer["adoption_refused"], answer["settled"])
        )
        self.assertEqual((), annotation_store.load(config))


if __name__ == "__main__":
    unittest.main()
