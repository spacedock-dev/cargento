"""A copied correction coming back unedited is recognised as Cargento's words (DRC-4678).

Item 9 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
built to the owner's rulings of 2026-09-28. The server records a digest of the exact text the
reader copied; a later Claude Code user message whose raw text has the same digest, under one
normalisation applied to both sides, is `derived`: not a person's evidence, not a later direction,
never adopted. The normalisation is what the live paste capture on Claude Code 2.1.283 measured
the input box doing to a paste: CRLF and CR become LF, a tab becomes four spaces, and a short
paste loses its trailing whitespace.

Every text here is placeholder prose.
"""

from __future__ import annotations

import contextlib
import dataclasses
import http.client
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import aggregate, http_api, observer, project_context
from cargento_runtime import annotations as annotation_store
from cargento_runtime import copied_corrections as copies
from cargento_runtime import io as runtime_io
from cargento_runtime import reading as runtime_reading
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

from .support import make_server, serve_until_closed
from .test_claude_checks import SHORT, START, Transcript
from .test_history import isolated_environment, no_instance, run_one_shot_cli

FIRST = "Add retry with backoff to the webhook handler."
NOW = START.timestamp() + 3600

# What the reader copied from Cargento's box: over 112 characters, three lines, a tab, CRLF line
# ends and trailing whitespace, which is what a clipboard can hand back.
COPIED = (
    "Steer back to your intent: ship the placeholder parser and nothing else.\r\n"
    "\tLine 1 is not shown yet: the parser tests at #3 failed at 14:02.\r\n"
    "Keep the lexer as it is, and rerun the parser tests before anything else.  \n"
)
# What Claude Code 2.1.283 stored for that paste (paste4678, cases 2, 3 and 7): LF line ends, the
# tab as exactly four spaces, the trailing whitespace of a short paste gone.
STORED = (
    "Steer back to your intent: ship the placeholder parser and nothing else.\n"
    "    Line 1 is not shown yet: the parser tests at #3 failed at 14:02.\n"
    "Keep the lexer as it is, and rerun the parser tests before anything else."
)
OWN = "Actually, rename the placeholder lexer before the parser tests run again."


def _row(**extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict(runtime_sessions.base_session("claude", SHORT, "billing"))
    row.update(
        {
            "project": "billing",
            "state": "working",
            "active": True,
            "last_activity": NOW,
            "first_prompt": FIRST,
            "first_prompt_at": START.timestamp() + 5,
        }
    )
    row.update(extra)
    return row


def _paste(session: Transcript, text: str) -> float:
    """A user record whose content is the plain string Claude Code writes for a paste."""
    row = session._entry("user", [])
    row["message"]["content"] = text
    return START.timestamp() + session.seconds


class NormalisationTest(unittest.TestCase):
    """The owner's rule, applied to both sides before hashing."""

    def test_the_capture_cases_digest_alike(self) -> None:
        self.assertEqual(copies.digest(COPIED), copies.digest(STORED))

    def test_each_rewrite_the_input_box_makes_is_undone(self) -> None:
        cases = (
            ("CRLF", "first\r\nsecond", "first\nsecond"),
            ("lone CR", "first\rsecond", "first\nsecond"),
            ("tab", "stands\tagainst", "stands    against"),
            ("trailing whitespace", "short paste  \t\n\n", "short paste"),
            ("leading whitespace", "\n  indented", "indented"),
        )
        for label, pasted, stored in cases:
            with self.subTest(case=label):
                self.assertEqual(copies.digest(pasted), copies.digest(stored))

    def test_an_edit_is_a_different_digest(self) -> None:
        self.assertNotEqual(copies.digest(STORED), copies.digest(STORED + " now"))
        self.assertNotEqual(copies.digest(STORED), copies.digest(STORED.replace("14:02", "14:03")))
        # A tab is four spaces, not one: a fixed width, as the capture measured.
        self.assertNotEqual(copies.digest("a\tb"), copies.digest("a b"))


class _Store(unittest.TestCase):
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
        self.session.save(self.path)

    def register(self, text: str = COPIED, *, now: float, sid: str = SHORT) -> str:
        return copies.register(self.config, "claude", sid, text, now=now)

    def facts(self) -> list[dict[str, Any]]:
        context = project_context.collect(
            self.config, self.state, [_row()], "billing", now=NOW, focus=("claude", SHORT)
        )
        return list(context["semantic"]["facts"])

    def user_facts(self) -> list[dict[str, Any]]:
        return [fact for fact in self.facts() if fact.get("type") == "user_message"]

    def matched(self) -> tuple[dict[str, Any], ...]:
        return copies.matched(self.config, self.state, "claude", SHORT)


class CopyStoreTest(_Store):
    def test_a_copy_is_stored_once_and_a_second_registration_changes_nothing(self) -> None:
        self.assertEqual(copies.OUTCOME_STORED, self.register(now=100.0))
        self.assertEqual(copies.OUTCOME_UNCHANGED, self.register(now=200.0))
        held = copies.load(self.config)[("claude", SHORT)]
        self.assertEqual(1, len(held))
        # The first copy's time stands: a second registration cannot move where it matches from.
        self.assertEqual(100.0, held[0]["copied_at"])
        self.assertEqual(copies.digest(COPIED), held[0]["digest"])

    def test_eight_digests_per_session_and_the_oldest_goes(self) -> None:
        for n in range(10):
            self.register(f"Correction number {n} for the placeholder parser.", now=100.0 + n)
        held = copies.load(self.config)[("claude", SHORT)]
        self.assertEqual(copies.COPIES_PER_SESSION, len(held))
        self.assertEqual(8, copies.COPIES_PER_SESSION)
        self.assertEqual([102.0 + n for n in range(8)], [copy["copied_at"] for copy in held])
        on_disk = json.loads(Path(copies.store_path(self.config)).read_text(encoding="utf-8"))
        self.assertEqual(8, len(on_disk["entries"][0]["copies"]))

    def test_the_store_holds_digests_only_and_is_owner_only(self) -> None:
        self.register(now=100.0)
        path = Path(copies.store_path(self.config))
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn("placeholder parser", raw)
        self.assertNotIn("Steer back", raw)
        if sys.platform != "win32":
            self.assertEqual(0o600, stat.S_IMODE(os.stat(path).st_mode))

    def test_what_cannot_be_a_copied_correction_is_refused_and_writes_nothing(self) -> None:
        cases: tuple[tuple[str, Any, str], ...] = (
            ("empty", "   \n\t ", "claude"),
            ("not a string", ["x"], "claude"),
            ("over 2,000 characters", "x" * (copies.CORRECTION_CAP_CHARS + 1), "claude"),
            ("a harness whose messages are not read", COPIED, "codex"),
        )
        for label, text, harness in cases:
            with self.subTest(case=label):
                self.assertEqual(
                    copies.OUTCOME_REFUSED,
                    copies.register(self.config, harness, SHORT, text, now=100.0),
                )
        self.assertFalse(os.path.lexists(copies.store_path(self.config)))
        self.assertEqual(
            copies.OUTCOME_STORED,
            self.register("x" * copies.CORRECTION_CAP_CHARS, now=100.0),
        )

    def test_nothing_is_stored_with_annotations_off(self) -> None:
        self.config = dataclasses.replace(self.config, annotations_enabled=False)
        self.assertEqual(copies.OUTCOME_REFUSED, self.register(now=100.0))
        self.assertFalse(os.path.lexists(copies.store_path(self.config)))

    def test_forget_deletes_the_store(self) -> None:
        self.assertFalse(copies.forget(self.config))
        self.register(now=100.0)
        self.assertTrue(copies.forget(self.config))
        self.assertEqual({}, copies.load(self.config))


class MatchingTest(_Store):
    """The collector half: each user message's digest from its raw text, before any clipping."""

    def test_an_exact_paste_after_the_copy_is_recognised_and_a_different_message_is_not(
        self,
    ) -> None:
        copied_at = START.timestamp() + self.session.seconds + 1
        self.register(now=copied_at)
        pasted_at = _paste(self.session, STORED)
        own_at = _paste(self.session, OWN)
        self.session.save(self.path)
        by_at = {float(fact["at"]): fact for fact in self.user_facts()}
        # The published summary is clipped at 112 characters; the digest was not.
        self.assertLessEqual(len(str(by_at[pasted_at]["summary"])), 112)
        self.assertGreater(len(STORED), 112)
        self.assertEqual(
            ({"fact_id": by_at[pasted_at]["fact_id"], "at": pasted_at},), self.matched()
        )
        self.assertNotIn(own_at, [entry["at"] for entry in self.matched()])

    def test_a_paste_before_the_copy_is_the_readers_own(self) -> None:
        _paste(self.session, STORED)
        self.session.save(self.path)
        self.register(now=START.timestamp() + self.session.seconds + 1)
        self.assertEqual((), self.matched())

    def test_a_digest_never_registered_matches_nothing(self) -> None:
        self.register("A different correction altogether.", now=START.timestamp())
        _paste(self.session, STORED)
        self.session.save(self.path)
        self.assertEqual((), self.matched())
        self.assertEqual((), copies.matched(self.config, self.state, "claude", "someone"))

    def test_a_digest_is_used_once_and_registering_it_again_matches_nothing_more(self) -> None:
        self.register(now=START.timestamp() + self.session.seconds + 1)
        first = _paste(self.session, STORED)
        self.session.save(self.path)
        self.assertEqual(copies.OUTCOME_UNCHANGED, self.register(now=first + 1))
        second = _paste(self.session, STORED)
        self.session.save(self.path)
        self.assertEqual([first], [entry["at"] for entry in self.matched()])
        self.assertNotIn(second, [entry["at"] for entry in self.matched()])

    def test_an_edited_paste_is_the_readers_own_words(self) -> None:
        self.register(now=START.timestamp() + self.session.seconds + 1)
        _paste(self.session, STORED + " now")
        _paste(self.session, "now.")
        self.session.save(self.path)
        self.assertEqual((), self.matched())

    def test_text_edited_in_cargentos_box_before_copying_matches_what_was_copied(self) -> None:
        edited = COPIED.replace("rerun the parser tests", "rerun only the lexer tests")
        self.register(edited, now=START.timestamp() + self.session.seconds + 1)
        at = _paste(
            self.session, STORED.replace("rerun the parser tests", "rerun only the lexer tests")
        )
        self.session.save(self.path)
        self.assertEqual([at], [entry["at"] for entry in self.matched()])

    def test_a_long_paste_keeps_its_trailing_newlines_and_still_matches(self) -> None:
        # A collapsed paste keeps its own trailing whitespace (paste4678, case 9).
        self.register(now=START.timestamp() + self.session.seconds + 1)
        at = _paste(self.session, STORED + "\n\n")
        self.session.save(self.path)
        self.assertEqual([at], [entry["at"] for entry in self.matched()])

    def test_a_message_longer_than_the_bound_never_matches_its_prefix(self) -> None:
        text = "y" * copies.CORRECTION_CAP_CHARS
        self.register(text, now=START.timestamp() + self.session.seconds + 1)
        _paste(self.session, text + "z" * 9000)
        self.session.save(self.path)
        self.assertEqual((), self.matched())


class _App(_Store):
    now = NOW

    def app(self, **row: Any) -> aggregate.Application:
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
            clock=lambda: self.now,
        )

    def pasted(self) -> tuple[float, float]:
        self.register(now=START.timestamp() + self.session.seconds + 1)
        pasted_at = _paste(self.session, STORED)
        own_at = _paste(self.session, OWN)
        self.session.save(self.path)
        return pasted_at, own_at


class TreatedAsCargentoAssistedTest(_App):
    """Adoption, rule 7 and DEC-16 read one mark, so the three stay one rule."""

    def test_the_row_publishes_the_recognised_message_and_every_row_carries_the_key(self) -> None:
        pasted_at, _ = self.pasted()
        rows = self.app().collect(show_all=True)["sessions"]
        self.assertEqual([pasted_at], [entry["at"] for entry in rows[0]["copied_prompts"]])
        self.assertEqual([], runtime_sessions.base_session("claude", "x", "p")["copied_prompts"])

    def test_the_facts_the_reading_reads_mark_it_derived_and_the_others_stay_yours(self) -> None:
        pasted_at, own_at = self.pasted()
        application = self.app()
        row = application.collect(show_all=True)["sessions"][0]
        facts = http_api._facts_of(http_api._session_context(application, row))
        authors = {
            float(fact["at"]): runtime_reading.author_of(fact)
            for fact in facts
            if fact.get("type") == "user_message"
        }
        self.assertEqual(runtime_reading.AUTHOR_DERIVED, authors[pasted_at])
        self.assertEqual(runtime_reading.AUTHOR_PERSON, authors[own_at])

    def test_the_window_for_typed_words_does_not_open_at_a_copied_correction(self) -> None:
        pasted_at, own_at = self.pasted()
        application = self.app()
        row = application.collect(show_all=True)["sessions"][0]
        facts = http_api._facts_of(http_api._session_context(application, row))
        # Saved between the paste and the reader's own message: the window opens at the reader's
        # previous message, never at the paste.
        start = runtime_reading.typed_window_start(facts, "claude", SHORT, pasted_at + 1)
        self.assertLess(start, pasted_at)
        self.assertEqual(own_at, runtime_reading.typed_window_start(facts, "claude", SHORT, NOW))

    def test_a_copied_correction_is_never_adopted_or_the_floor_for_a_later_direction(
        self,
    ) -> None:
        pasted_at, _ = self.pasted()
        latest = {"label": "asked", "text": STORED[:80], "at": pasted_at}
        row = self.app(first_prompt="", first_prompt_at=None, instruction=latest).collect(
            show_all=True
        )["sessions"][0]
        self.assertEqual(("", None), annotation_store.prompt_candidate(row, "latest-prompt"))
        self.assertIsNone(annotation_store.direction_floor(None, row))
        # The same row with nothing copied adopts the latest prompt as before.
        plain = {**row, "copied_prompts": []}
        self.assertEqual(
            (STORED[:80], pasted_at), annotation_store.prompt_candidate(plain, "latest-prompt")
        )


class CopiedRouteTest(_App):
    """`POST /api/correction/copied` over a real socket."""

    ROUTE = "/api/correction/copied"

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
    def post(
        port: int,
        payload: Any,
        *,
        headers: dict[str, str] | None = None,
        declared: str | None = None,
        path: str = ROUTE,
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

    def body(self, **over: Any) -> dict[str, Any]:
        return {"harness": "claude", "sid": SHORT, "text": COPIED, **over}

    def test_a_copy_through_the_route_recognises_the_paste_that_follows(self) -> None:
        with self.serving() as port:
            status, answer = self.post(port, self.body())
        self.assertEqual((200, {"ok": True, "registered": True}), (status, answer))
        self.assertEqual(NOW, copies.load(self.config)[("claude", SHORT)][0]["copied_at"])

    def test_a_second_registration_answers_that_nothing_new_was_registered(self) -> None:
        with self.serving() as port:
            self.post(port, self.body())
            status, answer = self.post(port, self.body())
        self.assertEqual((200, {"ok": True, "registered": False}), (status, answer))
        self.assertEqual(1, len(copies.load(self.config)[("claude", SHORT)]))

    def test_an_unknown_session_answers_one_body_and_stores_nothing(self) -> None:
        with self.serving() as port:
            unknown = self.post(port, self.body(sid="unknown-session"))
            other = self.post(port, self.body(harness="codex"))
        self.assertEqual((200, {"ok": True, "registered": False}), unknown)
        self.assertEqual((200, {"ok": True, "registered": False}), other)
        self.assertFalse(os.path.lexists(copies.store_path(self.config)))

    def test_a_forged_cross_origin_copy_is_refused_and_stores_nothing(self) -> None:
        cases = (
            ("cross-site origin", {"Origin": "http://evil.example"}),
            ("another local port", {"Origin": "http://127.0.0.1:1"}),
            ("rebound host", {"Host": "evil.example"}),
            ("cross-site fetch", {"Sec-Fetch-Site": "cross-site"}),
            ("same-site fetch", {"Sec-Fetch-Site": "same-site"}),
            ("document navigation", {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}),
        )
        with self.serving() as port:
            for label, headers in cases:
                with self.subTest(shape=label):
                    status, answer = self.post(port, self.body(), headers=headers)
                    self.assertEqual(403, status)
                    self.assertNotIn("registered", answer)
            self.assertEqual(
                413,
                self.post(port, None, declared=str(self.config.annotation_body_cap_bytes + 1))[0],
            )
            for bad in (
                self.body(text=["x"]),
                self.body(text=""),
                self.body(text="x" * (copies.CORRECTION_CAP_CHARS + 1)),
                self.body(sid=7),
                {"harness": "claude"},
            ):
                with self.subTest(body=str(bad)[:40]):
                    self.assertEqual(400, self.post(port, bad)[0])
        self.assertFalse(os.path.lexists(copies.store_path(self.config)))

    def test_the_route_answers_503_with_annotations_off(self) -> None:
        self.config = dataclasses.replace(self.config, annotations_enabled=False)
        with self.serving() as port:
            self.assertEqual(503, self.post(port, self.body())[0])

    def test_the_project_context_marks_the_recognised_message_copied(self) -> None:
        self.now = START.timestamp() + self.session.seconds + 1
        with self.serving() as port:
            self.post(port, self.body())
            pasted_at = _paste(self.session, STORED)
            own_at = _paste(self.session, OWN)
            self.session.save(self.path)
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", f"/api/project-context?project=billing&session=claude:{SHORT}")
            context = json.loads(conn.getresponse().read())
            conn.close()
        marks = {
            float(fact["at"]): fact.get("copied")
            for fact in context["semantic"]["facts"]
            if fact.get("type") == "user_message"
        }
        self.assertIs(True, marks[pasted_at])
        self.assertIsNone(marks[own_at])

    def test_a_recognised_message_cannot_be_opened_as_a_later_direction(self) -> None:
        self.now = START.timestamp() + self.session.seconds + 1
        with self.serving() as port:
            self.post(port, self.body())
            pasted_at = _paste(self.session, STORED)
            own_at = _paste(self.session, OWN)
            self.session.save(self.path)
            by_at = {float(fact["at"]): str(fact["fact_id"]) for fact in self.user_facts()}
            pasted = self.post(
                port,
                {"harness": "claude", "sid": SHORT, "fact_id": by_at[pasted_at]},
                path="/api/direction",
            )
            own = self.post(
                port,
                {"harness": "claude", "sid": SHORT, "fact_id": by_at[own_at]},
                path="/api/direction",
            )
        self.assertEqual((200, False), (pasted[0], pasted[1]["ok"]))
        self.assertEqual((200, True, OWN), (own[0], own[1]["ok"], own[1]["text"]))

    def test_no_copied_text_reaches_the_payload(self) -> None:
        with self.serving() as port:
            self.post(port, self.body())
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/api/data")
            data = conn.getresponse().read().decode("utf-8")
            conn.close()
        self.assertNotIn("rerun the parser tests", data)


class ForgetTest(unittest.TestCase):
    """`--forget` clears the digests: the machine's memory of an act, holding no text."""

    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        self.environ = isolated_environment(state.name, home.name)
        self.config = build_runtime_config(
            environ=self.environ,
            platform_name="linux",
            os_name="posix",
            launcher_path=Path(home.name) / "server.py",
        )

    def said(self, argv: list[str]) -> tuple[int, str]:
        with no_instance(), mock.patch.object(runtime_io, "diag") as diag:
            code = run_one_shot_cli(argv, self.environ)
        return code, " ".join(str(call.args[0]) for call in diag.call_args_list)

    def test_forget_deletes_the_copied_correction_store_and_says_so(self) -> None:
        copies.register(self.config, "claude", SHORT, COPIED, now=100.0)
        path = copies.store_path(self.config)
        self.assertTrue(os.path.exists(path))
        code, said = self.said(["--forget"])
        self.assertEqual(0, code)
        self.assertFalse(os.path.exists(path))
        self.assertIn(f"deleted {path}", said)
        _, again = self.said(["--forget"])
        self.assertIn(f"no copied-correction store at {path}", again)


if __name__ == "__main__":
    unittest.main()
