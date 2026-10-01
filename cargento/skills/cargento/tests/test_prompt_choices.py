"""The reader's own prompts offered for adoption as the goal (owner ruling Q7, 2026-10-01).

"Use your prompt" lists up to five of the reader's person-authored prompts from the observed
record, the first then the most recent, deduplicated. Each is resolved whole by fact id on the
server and adopted under the closed `chosen-prompt` goal source, keyed on its own time. A copied
correction, a harness control and a local command are refused as the first-prompt draft refuses
them. The list rides on the focused project context only; its words are never stored except as an
adopted goal, the path the first and latest prompt already take.

Every text here is placeholder prose.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

from cargento_runtime import annotations as annotation_store
from cargento_runtime import history, project_context, records
from cargento_runtime import reading as runtime_reading

from .support import make_runtime, make_server, serve_until_closed
from .test_claude_checks import SHORT, START
from .test_copied_corrections import FIRST, NOW, OWN, STORED, _App, _row, _Store

CAP = 240


def _fact(n: int, words: str, **over: Any) -> dict[str, Any]:
    fact: dict[str, Any] = {
        "fact_id": f"fact:{n:016x}",
        "type": "user_message",
        "at": 1_700_000_000.0 + n,
        "summary": words[:40],
        runtime_reading.WORDS_FIELD: words,
        "source_session": {"harness": "claude", "sid": "s1"},
    }
    fact.update(over)
    return fact


class WhichPromptsAreOffered(unittest.TestCase):
    """`annotations.prompt_choices` over hand-built facts."""

    ROW: ClassVar[dict[str, Any]] = {"harness": "claude", "sid": "s1"}

    def _texts(self, facts: list[dict[str, Any]]) -> list[str]:
        return [c["text"] for c in annotation_store.prompt_choices(self.ROW, facts, CAP)]

    def test_the_first_prompt_comes_first_and_then_the_most_recent(self) -> None:
        facts = [_fact(n, f"prompt number {n}") for n in range(1, 9)]
        self.assertEqual(
            [
                "prompt number 1",
                "prompt number 8",
                "prompt number 7",
                "prompt number 6",
                "prompt number 5",
            ],
            self._texts(list(reversed(facts))),
        )

    def test_at_most_five_are_offered_and_a_repeated_prompt_once(self) -> None:
        facts = [
            _fact(1, "ship the export"),
            _fact(2, "ship the export"),
            _fact(3, "add a test"),
            _fact(4, "ship the export"),
        ]
        self.assertEqual(["ship the export", "add a test"], self._texts(facts))
        many = [_fact(n, f"distinct {n}") for n in range(1, 30)]
        self.assertEqual(annotation_store.PROMPT_CHOICES_CAP, len(self._texts(many)))
        self.assertEqual(5, annotation_store.PROMPT_CHOICES_CAP)

    def test_a_copied_correction_another_session_and_the_agent_are_never_offered(self) -> None:
        facts = [
            _fact(1, "copied from cargento", copied=True),
            _fact(2, "another session", source_session={"harness": "claude", "sid": "s2"}),
            _fact(3, "the agent said this", type="assistant_message"),
            _fact(4, "my own words"),
        ]
        self.assertEqual(["my own words"], self._texts(facts))

    def test_a_harness_control_is_never_offered(self) -> None:
        facts = [_fact(1, "/clear"), _fact(2, "/login"), _fact(3, "rename the flag")]
        self.assertEqual(["rename the flag"], self._texts(facts))

    def test_a_message_with_no_whole_words_or_no_time_is_never_offered(self) -> None:
        bare = _fact(1, "summary only")
        del bare[runtime_reading.WORDS_FIELD]
        facts = [bare, _fact(2, "no time", at=None), _fact(3, "   "), _fact(4, "kept")]
        self.assertEqual(["kept"], self._texts(facts))

    def test_a_prompt_no_adoption_reads_is_never_offered(self) -> None:
        for harness in ("pi", "gemini", "antigravity"):
            with self.subTest(harness=harness):
                row = {"harness": harness, "sid": "s1"}
                fact = _fact(1, "words", source_session=row)
                self.assertEqual([], annotation_store.prompt_choices(row, [fact], CAP))

    def test_a_long_prompt_is_offered_as_an_excerpt_that_says_so(self) -> None:
        words = "ship the export and " * 40
        (choice,) = annotation_store.prompt_choices(self.ROW, [_fact(1, words)], CAP)
        self.assertLessEqual(len(choice["text"]), CAP)
        self.assertTrue(choice["cut"])
        self.assertTrue(words.startswith(choice["text"]))
        (whole,) = annotation_store.prompt_choices(self.ROW, [_fact(1, "short")], CAP)
        self.assertFalse(whole["cut"])

    def test_a_credential_in_a_prompt_is_redacted_before_it_is_offered(self) -> None:
        secret = "ghp_" + "a" * 36
        (choice,) = annotation_store.prompt_choices(
            self.ROW, [_fact(1, f"use {secret} for the push")], CAP
        )
        self.assertNotIn("a" * 10, choice["text"])
        self.assertIn("REDACTED", choice["text"])

    def test_the_offered_text_is_the_text_an_adoption_stores(self) -> None:
        # `_adoption_matches` re-bounds the page's text with `safe_text`, so the
        # offered text must be a fixed point of it or a fair press is refused.
        words = "ship the export and " * 40
        (choice,) = annotation_store.prompt_choices(self.ROW, [_fact(1, words)], CAP)
        self.assertEqual(choice["text"], records.safe_text(choice["text"], CAP))


class AChosenPromptIsAdoptedOnlyAsTheServerFoundIt(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.config, self.state = make_runtime(state_home=home.name, state_dir=Path(home.name))
        self.row = {"harness": "claude", "sid": "s1"}
        self.choice: annotation_store.PromptChoice = {
            "fact_id": "fact:1",
            "at": 10.0,
            "text": "Build the parser",
            "cut": False,
        }

    def _adopt(self, **over: Any) -> str:
        arguments: dict[str, Any] = {
            "source": runtime_reading.PROMPT_CHOSEN,
            "expected_text": "Build the parser",
            "expected_at": 10.0,
            "now": 30.0,
            "chosen": self.choice,
        }
        arguments.update(over)
        return annotation_store.adopt(self.config, self.state, self.row, **arguments)

    def test_the_choice_is_saved_under_its_own_source_and_time(self) -> None:
        self.assertEqual(annotation_store.OUTCOME_STORED, self._adopt())
        entry = annotation_store.find(annotation_store.load(self.config), "claude", "s1")
        assert entry is not None
        revision = entry["revisions"][-1]
        self.assertEqual("Build the parser", revision["goal"])
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, revision["goal_source"])
        self.assertEqual(10.0, revision["goal_source_at"])
        # Adopted words open the evidence at their own time, as the other two do.
        self.assertEqual(10.0, runtime_reading.baseline_at(revision))
        published = annotation_store.published(entry)
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, published["goal_source"])

    def test_without_the_servers_own_choice_nothing_is_adopted(self) -> None:
        self.assertEqual(annotation_store.OUTCOME_REFUSED, self._adopt(chosen=None))
        self.assertIsNone(annotation_store.find(annotation_store.load(self.config), "claude", "s1"))

    def test_words_or_a_time_other_than_the_choices_are_refused(self) -> None:
        for over in ({"expected_text": "Build the parser now"}, {"expected_at": 11.0}):
            with self.subTest(over=over):
                self.assertEqual(annotation_store.OUTCOME_REFUSED, self._adopt(**over))

    def test_the_choices_source_survives_in_session_history(self) -> None:
        row = {
            "harness": "claude",
            "sid": "s1",
            "project": "demo",
            "state": "working",
            "last_activity": 30.0,
            "annotation_goal": "Build the parser",
            "annotation_goal_source": runtime_reading.PROMPT_CHOSEN,
            "annotation_goal_source_at": 10.0,
        }
        observed = history.observation(row)
        assert observed is not None
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, observed["annotation_goal_source"])

    def test_the_choices_themselves_never_enter_session_history(self) -> None:
        self.assertNotIn("prompt_choices", history.OBSERVATION_FIELDS)
        self.assertNotIn("prompt_choices", history.PROMPT_TEXT_ALLOWLIST)


class TheMenuOverARealSocket(_App):
    """The focused project context publishes the list; the annotate route adopts from it."""

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
    def _request(port: int, method: str, path: str, payload: Any = None) -> Any:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            if payload is None:
                conn.request(method, path)
            else:
                conn.request(
                    method,
                    path,
                    body=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
            return json.loads(conn.getresponse().read())
        finally:
            conn.close()

    def _choices(self, port: int) -> Any:
        context = self._request(
            port, "GET", f"/api/project-context?project=billing&session=claude:{SHORT}"
        )
        self.assertNotIn(runtime_reading.WORDS_FIELD, json.dumps(context))
        return context["prompt_choices"]

    def _adopt(self, port: int, choice: dict[str, Any], **over: Any) -> Any:
        payload = {
            "harness": "claude",
            "sid": SHORT,
            "adopt": runtime_reading.PROMPT_CHOSEN,
            "prompt_fact": choice["fact_id"],
            "expected_prompt": choice["text"],
            "expected_prompt_at": choice["at"],
            "expected_revision": 0,
        }
        payload.update(over)
        return self._request(port, "POST", "/api/annotate", payload)

    def test_the_page_is_offered_the_readers_prompts_and_never_a_pasted_correction(self) -> None:
        self.now = START.timestamp() + self.session.seconds + 1
        pasted_at, own_at = self.pasted()
        self.now = START.timestamp() + self.session.seconds + 1
        with self.serving() as port:
            choices = self._choices(port)
        self.assertEqual([FIRST, OWN], [c["text"] for c in choices])
        self.assertNotIn(pasted_at, [c["at"] for c in choices])
        self.assertEqual(own_at, choices[1]["at"])
        self.assertNotIn(STORED.split("\n", 1)[0], json.dumps(choices))

    def test_choosing_one_adopts_it_and_a_forged_choice_adopts_nothing(self) -> None:
        self.now = START.timestamp() + self.session.seconds + 1
        self.pasted()
        self.now = START.timestamp() + self.session.seconds + 1
        with self.serving() as port:
            choices = self._choices(port)
            latest = choices[1]
            for forged in (
                {"prompt_fact": "fact:ffffffffffffffff"},
                {"expected_prompt": latest["text"] + " and more"},
                {"expected_prompt_at": latest["at"] + 1},
                {"prompt_fact": 7},
            ):
                with self.subTest(forged=forged):
                    answer = self._adopt(port, latest, **forged)
                    self.assertEqual(annotation_store.OUTCOME_REFUSED, answer["outcome"])
            answer = self._adopt(port, latest)
        self.assertEqual(annotation_store.OUTCOME_STORED, answer["outcome"])
        entry = annotation_store.find(annotation_store.load(self.config), "claude", SHORT)
        assert entry is not None
        revision = entry["revisions"][-1]
        self.assertEqual(OWN, revision["goal"])
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, revision["goal_source"])
        self.assertEqual(latest["at"], revision["goal_source_at"])

    def test_a_pasted_correction_cannot_be_adopted_by_its_fact_id(self) -> None:
        self.now = START.timestamp() + self.session.seconds + 1
        pasted_at, _own_at = self.pasted()
        self.now = START.timestamp() + self.session.seconds + 1
        pasted = next(fact for fact in self.user_facts() if float(fact["at"]) == pasted_at)
        with self.serving() as port:
            answer = self._adopt(
                port,
                {"fact_id": pasted["fact_id"], "text": STORED, "at": pasted_at},
            )
        self.assertEqual(annotation_store.OUTCOME_REFUSED, answer["outcome"])
        self.assertIsNone(
            annotation_store.find(annotation_store.load(self.config), "claude", SHORT)
        )


class ALongSessionsEarliestChoiceIsNotItsFirstPrompt(_Store):
    """The choices come from the focused record, which holds the newest 100 events. A session
    with more prompts than that after its opening one offers a later message first, so the page
    calls that option "Earliest prompt" unless its time is the row's first prompt's (F2)."""

    def test_more_than_a_hundred_later_prompts_push_the_first_out_of_the_choices(self) -> None:
        for n in range(150):
            self.session.prompt(f"tweak number {n}")
        self.session.save(self.path)
        row = _row()
        context = project_context.collect(
            self.config, self.state, [row], "billing", now=NOW, focus=("claude", SHORT)
        )
        choices = annotation_store.prompt_choices(row, context["semantic"]["facts"], 240)
        self.assertTrue(choices)
        self.assertNotIn(FIRST, [choice["text"] for choice in choices])
        # The time the page compares against before it says "First prompt".
        self.assertNotEqual(row["first_prompt_at"], choices[0]["at"])
