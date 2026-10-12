"""A reader can act on the newest requests of an image-filled, week-long session."""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest import mock

from compass_runtime import http_api, observer, project_context, reading, record_pages
from compass_runtime.config import RuntimeConfig, build_runtime_config
from compass_runtime.state import build_runtime_state

if TYPE_CHECKING:
    from collections.abc import Callable


class LongIntentSourcesTest(unittest.TestCase):
    temp: tempfile.TemporaryDirectory[str]
    root: Path
    path: Path
    config: RuntimeConfig
    rows: list[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.path = cls.root / "long.jsonl"
        cls.config = build_runtime_config(
            environ={"HOME": str(cls.root), "COMPASS_HOME": str(cls.root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=cls.root / "server.py",
        )
        cls.rows = [cls.record(n) for n in (1, 2, 3)]
        padding = (
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "tool_result", "content": "x" * (1024 * 1024)}],
                    },
                }
            ).encode()
            + b"\n"
        )
        with cls.path.open("wb") as handle:
            handle.write(json.dumps(cls.rows[0]).encode() + b"\n")
            for _ in range(71):
                handle.write(padding)
            handle.write(json.dumps(cls.rows[1]).encode() + b"\n")
            handle.write(json.dumps(cls.rows[2]).encode() + b"\n")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    @staticmethod
    def record(n: int) -> dict[str, Any]:
        return {
            "type": "user",
            "timestamp": f"2026-10-01T00:00:0{n}Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": f"Build synthetic step {n}. Keep the tests."}],
            },
        }

    def setUp(self) -> None:
        self.state = build_runtime_state(self.config, started=0)
        self.app = SimpleNamespace(config=self.config, state=self.state)
        self.row = {"harness": "claude", "sid": "long", "project": "synthetic"}
        self.facts = [
            project_context._semantic_fact_from_event(
                project_context._instruction_event(self.config, row, "claude", "long") or {},
                "steer",
                "user_message",
                "",
            )
            for row in self.rows
        ]

    def test_a_reader_with_a_week_long_session_can_use_a_recent_direction_as_their_goal(
        self,
    ) -> None:
        with mock.patch.object(observer, "resolve_transcript", return_value=str(self.path)):
            words = project_context.direction_text(
                self.config, self.state, "claude", "long", self.facts[-1]["fact_id"]
            )
        self.assertEqual("Build synthetic step 3. Keep the tests.", words.text)
        page = record_pages.read(self.config, str(self.path), "claude", "long", cursor_key=b"test")
        self.assertEqual(self.facts[-1]["fact_id"], page["entries"][0]["fact_id"])

    def test_a_reader_can_choose_recent_prompts_as_well_as_an_adopted_opening_prompt(self) -> None:
        facts = project_context.transcript_user_facts(
            self.config, self.state, str(self.path), "claude", "long", goal_choices=True
        )
        self.assertEqual(
            {fact["fact_id"] for fact in self.facts}, {fact["fact_id"] for fact in facts}
        )
        self.assertEqual(self.facts[-1]["fact_id"], facts[0]["fact_id"])
        with mock.patch.object(observer, "resolve_transcript", return_value=str(self.path)):
            context = http_api._with_prompt_choices(
                self.app,
                {"semantic": {"facts": self.facts}},
                [self.row],
                ("claude", "long"),
                "synthetic",
            )
            sources = http_api._request_sources(self.app, self.row, self.facts)
        self.assertEqual(3, len(context["prompt_choices"]))
        self.assertEqual(3, len(sources))

    def test_a_reader_can_choose_their_prompts_when_semantic_history_has_evicted_their_titles(
        self,
    ) -> None:
        with mock.patch.object(observer, "resolve_transcript", return_value=str(self.path)):
            context = http_api._with_prompt_choices(
                self.app, {"semantic": {"facts": []}}, [self.row], ("claude", "long"), "synthetic"
            )
        self.assertEqual(3, len(context["prompt_choices"]))

    def test_a_reader_is_told_when_the_search_stops_before_an_older_direction(self) -> None:
        config = dataclasses.replace(self.config, direction_scan_max_bytes=2 * 1024 * 1024)
        with mock.patch.object(observer, "resolve_transcript", return_value=str(self.path)):
            result = project_context.direction_lookup(
                config, self.state, "claude", "long", self.facts[0]["fact_id"]
            )
        self.assertEqual("out_of_reach", result.reason)
        self.assertEqual(2 * 1024 * 1024, result.scanned_bytes)
        self.assertEqual("", result.words.text)

    def test_a_reader_is_told_when_a_complete_record_does_not_hold_the_direction(self) -> None:
        path = self.root / "short.jsonl"
        path.write_text(json.dumps(self.rows[-1]) + "\n")
        with mock.patch.object(observer, "resolve_transcript", return_value=str(path)):
            result = project_context.direction_lookup(
                self.config, self.state, "claude", "long", "fact:missing"
            )
        self.assertEqual("not_found", result.reason)

    def test_a_reader_never_adopts_two_different_requests_with_the_same_identity(self) -> None:
        path = self.root / "ambiguous.jsonl"
        altered = self.record(3)
        altered["message"]["content"][0]["text"] += " Changed ending."
        path.write_text(json.dumps(self.rows[-1]) + "\n" + json.dumps(altered) + "\n")
        with mock.patch.object(observer, "resolve_transcript", return_value=str(path)):
            self.assertEqual(
                "",
                project_context.direction_text(
                    self.config, self.state, "claude", "long", self.facts[-1]["fact_id"]
                ).text,
            )

    def test_a_reader_keeps_the_opening_source_when_many_recent_prompts_fill_the_fact_allowance(
        self,
    ) -> None:
        path = self.root / "many-prompts.jsonl"
        path.write_text("".join(json.dumps(self.record(n)) + "\n" for n in range(1, 6)))
        with mock.patch.object(project_context, "TRANSCRIPT_USER_FACTS_MAX", 2):
            facts = project_context.transcript_user_facts(
                self.config, self.state, str(path), "claude", "long"
            )
        self.assertEqual(
            ["Build synthetic step 1.", "Build synthetic step 5."],
            [fact["summary"] for fact in facts],
        )

    def test_a_reader_with_a_hundred_megabyte_record_can_open_recent_words_and_get_honest_menu_coverage(
        self,
    ) -> None:
        path = self.root / "hundred.jsonl"
        padding = (
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "tool_result", "content": "x" * (1024 * 1024)}],
                    },
                }
            ).encode()
            + b"\n"
        )
        with path.open("wb") as handle:
            handle.write(json.dumps(self.rows[0]).encode() + b"\n")
            for _ in range(100):
                handle.write(padding)
            handle.write(json.dumps(self.rows[-1]).encode() + b"\n")
        with mock.patch.object(observer, "resolve_transcript", return_value=str(path)):
            recent = project_context.direction_lookup(
                self.config, self.state, "claude", "long", self.facts[-1]["fact_id"]
            )
            unreachable = project_context.direction_lookup(
                self.config, self.state, "claude", "long", self.facts[0]["fact_id"]
            )
            context = http_api._with_prompt_choices(
                self.app,
                {"semantic": {"facts": self.facts}},
                [self.row],
                ("claude", "long"),
                "synthetic",
            )
            requests = http_api._request_sources(
                self.app, self.row, [self.facts[0], self.facts[-1]]
            )
        self.assertEqual("Build synthetic step 3. Keep the tests.", recent.words.text)
        self.assertEqual("out_of_reach", unreachable.reason)
        self.assertEqual(self.config.direction_scan_max_bytes, recent.scanned_bytes)
        self.assertEqual("bytes", context["prompt_scan"]["bound"])
        self.assertEqual(
            [self.facts[-1]["fact_id"], self.facts[0]["fact_id"]],
            [choice["fact_id"] for choice in context["prompt_choices"]],
        )
        self.assertEqual(2, len(requests))

    def test_a_reader_is_told_when_the_search_clock_ends_before_reading_the_source(self) -> None:
        config = dataclasses.replace(self.config, direction_scan_max_seconds=0)
        with mock.patch.object(observer, "resolve_transcript", return_value=str(self.path)):
            result = project_context.direction_lookup(
                config, self.state, "claude", "long", self.facts[-1]["fact_id"]
            )
        self.assertEqual("out_of_reach", result.reason)
        self.assertEqual(0, result.scanned_bytes)

    def test_a_reader_can_open_a_codex_request_with_escaped_user_role_keys(self) -> None:
        path = self.root / "codex.jsonl"
        record = {
            "type": "response_item",
            "timestamp": "2026-10-01T00:00:03Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": "Build a synthetic Codex fixture.",
            },
        }
        path.write_text(
            json.dumps(record).replace('"role"', '"\\u0072ole"').replace('"user"', '"\\u0075ser"')
            + "\n"
        )
        event = project_context._instruction_event(self.config, record, "codex", "long")
        assert event is not None
        fact = project_context._semantic_fact_from_event(event, "steer", "user_message", "")
        with mock.patch.object(observer, "resolve_transcript", return_value=str(path)):
            words = project_context.direction_text(
                self.config, self.state, "codex", "long", fact["fact_id"]
            )
        self.assertEqual("Build a synthetic Codex fixture.", words.text)

    def test_a_reader_does_not_inherit_an_empty_prompt_cache_from_a_replaced_file(self) -> None:
        path = self.root / "replace.jsonl"
        path.write_text('{"type":"system"}' + " " * 495 + "\n")
        self.assertEqual(
            [],
            project_context.transcript_user_facts(
                self.config, self.state, str(path), "claude", "long"
            ),
        )
        before = path.stat()
        replacement = self.root / "replacement.jsonl"
        raw = json.dumps(self.rows[-1])
        replacement.write_text(raw + " " * (before.st_size - len(raw) - 1) + "\n")
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        replacement.replace(path)
        found = project_context.transcript_user_facts(
            self.config, self.state, str(path), "claude", "long"
        )
        self.assertEqual(1, len(found))

    def test_a_reader_does_not_get_request_age_from_a_same_time_source_dropped_by_the_fact_cap(
        self,
    ) -> None:
        rows = [self.record(3), self.record(1), self.record(1)]
        rows[-1]["message"]["content"][0]["text"] = "Build a different synthetic outcome."

        def read(visit: Callable[[bytes], None]) -> None:
            for row in rows:
                visit(json.dumps(row).encode())

        with mock.patch.object(project_context, "TRANSCRIPT_USER_FACTS_MAX", 2):
            facts = project_context._transcript_user_scan(
                self.config, b"", "claude", "long", read=read
            )
        source = min(facts, key=lambda fact: fact["at"])
        self.assertIsNone(
            reading.line_request_binding(
                facts,
                source_id=source["fact_id"],
                text=source["reader_words"],
                harness="claude",
                sid="long",
                now=1900000000,
            )
        )

    def test_a_reader_sees_a_failed_prompt_read_when_the_source_moves_after_the_scan(self) -> None:
        path = self.root / "late-append.jsonl"
        path.write_text(json.dumps(self.rows[0]) + "\n")
        original = project_context._read_user_sources

        def moving(*args: Any, **kwargs: Any) -> list[dict[str, Any]] | None:
            facts = original(*args, **kwargs)
            with path.open("a") as handle:
                handle.write("\n")
            return facts

        coverage: dict[str, Any] = {}
        with mock.patch.object(project_context, "_read_user_sources", moving):
            self.assertEqual(
                [],
                project_context.transcript_user_facts(
                    self.config,
                    self.state,
                    str(path),
                    "claude",
                    "long",
                    goal_choices=True,
                    coverage=coverage,
                ),
            )
        self.assertEqual("unavailable", coverage["state"])

    def test_a_reader_never_adopts_conflicting_words_hidden_beyond_the_review_cap(self) -> None:
        path = self.root / "long-conflict.jsonl"
        first, second = self.record(3), self.record(3)
        first["message"]["content"][0]["text"] += " x" * 1400 + " first ending."
        second["message"]["content"][0]["text"] += " x" * 1400 + " second ending."
        path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
        with mock.patch.object(observer, "resolve_transcript", return_value=str(path)):
            words = project_context.direction_text(
                self.config, self.state, "claude", "long", self.facts[-1]["fact_id"]
            )
            menu = http_api._prompt_facts(self.app, self.row, [])
        self.assertEqual("", words.text)
        self.assertFalse(any(fact.get("reader_words") for fact in menu))
