"""Inline markup cannot carry a recognized credential past the shared filter."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import (
    claude_data,
    project_context,
    reading,
    records,
    semantic_history,
    transcripts,
)
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

from . import test_direction_windows as direction_tests
from . import test_newest_final_words as final_tests
from .test_claude_checks import SHORT

KEY = "AKIAIOSFODNN7EXAMPLE"  # documented, nonfunctional AWS example
SPLITS = (
    "AKIAIOSFODNN7<em>EXAMPLE",
    "AK<em>IAIOSFODNN7EXAMPLE",
    "AKIAIOSFODNN7</em>EXAMPLE",
    'AKIA<SPAN title="format > only">IOSFODNN7</SPAN>EXAMPLE',
    "AKIA<b><i>IOSFODNN7</i></b>EXAMPLE",
    "AKIA<em/>IOSFODNN7EXAMPLE",
)


def command(words: str) -> str:
    return (
        "<command-message>review</command-message>\n"
        "<command-name>/review</command-name>\n"
        f"<command-args>{words}</command-args>"
    )


class InlineCredentialsStayMasked(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.root = Path(home.name)
        self.config = build_runtime_config(
            environ={"HOME": home.name, "CARGENTO_HOME": str(self.root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
        )

    def assert_masked(self, value: str) -> None:
        self.assertIn(records.SECRET_MARKER, value)
        self.assertNotIn("EXAMPLE", value)
        self.assertNotIn(KEY, re.sub(r"\s|<[^>]*>", "", value))

    def event(self, text: str) -> dict[str, Any]:
        event = project_context._instruction_event(
            self.config,
            {
                "type": "user",
                "timestamp": "2026-10-01T12:00:00Z",
                "uuid": "owned-placeholder",
                "message": {"role": "user", "content": [{"type": "text", "text": text}]},
            },
            "claude",
            "owned-session",
        )
        assert event is not None
        return event

    def collector_title(self, text: str) -> str | None:
        path = self.root / "owned-collector.jsonl"
        path.write_text(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-10-01T12:00:00Z",
                    "uuid": "owned-placeholder",
                    "message": {"role": "user", "content": [{"type": "text", "text": text}]},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        state = build_runtime_state(self.config, started=0)
        return claude_data.session_title(self.config, state, str(path))

    def test_complete_command_cues_keep_arguments_and_do_not_create_a_cut(self) -> None:
        for cue, expected in (
            ("DB_KEY=staging", "DB_KEY=…REDACTED"),
            ("secret=staging", "secret=staging"),
            ("the token: next", "the token: next"),
        ):
            for trailing in ("", " "):
                with self.subTest(cue=cue, trailing=bool(trailing)):
                    raw = command("note " + cue + trailing)
                    wanted = "/review note " + expected
                    self.assertEqual(wanted, transcripts.prompt_title(self.config, raw, 200))
                    self.assertEqual(wanted, transcripts.command_direction(self.config, raw))

    def test_the_file_collector_keeps_complete_arguments_and_masks_credentials(self) -> None:
        for cue, expected in (
            ("DB_KEY=staging", "DB_KEY=…REDACTED"),
            ("secret=staging", "secret=staging"),
            ("the token: next", "the token: next"),
        ):
            for wrapped in (False, True):
                with self.subTest(cue=cue, wrapped=wrapped):
                    raw = "note " + cue
                    self.assertEqual(
                        ("/review " if wrapped else "") + "note " + expected,
                        self.collector_title(command(raw) if wrapped else raw),
                    )
        for split in SPLITS:
            with self.subTest(split=split):
                title = self.collector_title(command("rotate " + split + " today"))
                assert title is not None
                self.assert_masked(title)

    def test_complete_overbound_markup_withholds_arguments_without_reusing_raw_words(self) -> None:
        raw = command("note <em>" + "harmless " * 2000 + "</em>")
        self.assertEqual("/review …REDACTED", transcripts.prompt_title(self.config, raw))
        self.assertEqual("/review …REDACTED", transcripts.command_direction(self.config, raw))

    def test_a_genuine_cut_and_already_premasked_cut_remain_honestly_cut(self) -> None:
        raw = command("note secret=staging").removesuffix("</command-args>")
        self.assertEqual(
            "/review note secret=staging…", transcripts.command_direction(self.config, raw)
        )
        premasked = records.redact_secrets(command("note secret=staging"))
        self.assertTrue(transcripts.command_cut(premasked))
        self.assertEqual(
            "/review note secret=…REDACTED…",
            transcripts.command_direction(self.config, premasked),
        )

    def test_command_argument_rendering_still_clips_and_preserves_control_classification(
        self,
    ) -> None:
        raw = command("ordinary words " * 30)
        title = transcripts.prompt_title(self.config, raw, 30)
        assert title is not None
        self.assertLessEqual(len(title), 31)
        self.assertTrue(title.startswith("/review ordinary words"))
        self.assertFalse(transcripts.harness_control_prompt(self.config, raw))
        local = raw.replace("<command-message>review</command-message>\n", "")
        self.assertTrue(transcripts.harness_control_prompt(self.config, local))
        self.assertEqual("", transcripts.command_direction(self.config, local))

    def test_inline_shapes_are_masked_before_hint_matching_and_clipping(self) -> None:
        for split in SPLITS:
            with self.subTest(shape=split):
                raw = f"rotate {split} today"
                self.assert_masked(records.redact_secrets(raw))
                self.assert_masked(records.safe_text(raw, 18))
                self.assert_masked(records.mask_prose(raw))

    def test_ordinary_and_command_event_page_history_and_prompt_are_masked(self) -> None:
        for split in SPLITS:
            for wrapped in (False, True):
                with self.subTest(shape=split, wrapped=wrapped):
                    words = f"rotate {split} today"
                    event = self.event(command(words) if wrapped else words)
                    self.assert_masked(event["title"])
                    self.assert_masked(event["reader_words"])
                    fact = project_context._semantic_fact_from_event(
                        event, "steer", "user_message", ""
                    )
                    page = project_context.for_page(
                        {"events": [event], "semantic": {"facts": [fact]}}
                    )
                    self.assert_masked(json.dumps(page, ensure_ascii=False))
                    history = {"v": 1, "projects": {"owned": {"events": [event], "facts": [fact]}}}
                    self.assertTrue(semantic_history._write(self.config, history))
                    stored = json.loads(Path(semantic_history.store_path(self.config)).read_text())
                    self.assert_masked(json.dumps(stored, ensure_ascii=False))
                    ledger = reading.build_ledger([fact], "claude", "owned-session")
                    prompt, selection = reading.build_prompt(
                        ledger, goal="Rotate credentials", max_bytes=16384
                    )
                    self.assertEqual(1, len(selection.entries))
                    self.assert_masked(prompt)

    def test_command_tags_do_not_separate_the_key_before_redaction(self) -> None:
        for split in SPLITS:
            with self.subTest(shape=split):
                raw = command(f"rotate {split} today")
                title = transcripts.prompt_title(self.config, raw, 200)
                direction = transcripts.command_direction(self.config, raw)
                assert title is not None and direction is not None
                self.assert_masked(title)
                self.assert_masked(direction)

    def test_cut_command_arguments_mask_seen_credentials_before_tag_spacing(self) -> None:
        words = f"rotate {SPLITS[0]} today"
        for raw in (
            command(words).removesuffix("</command-args>"),
            command(words + " harmless trailer" * 200),
        ):
            with self.subTest(raw_chars=len(raw)):
                direction = transcripts.command_direction(self.config, raw)
                assert direction is not None
                self.assert_masked(direction)
                self.assert_masked(project_context._message_words(self.config, raw, "claude"))
                event = self.event(raw)
                self.assert_masked(event["title"])
                self.assert_masked(event["reader_words"])
                fact = project_context._semantic_fact_from_event(event, "steer", "user_message", "")
                ledger = reading.build_ledger([fact], "claude", "owned-session")
                prompt, selection = reading.build_prompt(
                    ledger, goal="Rotate credentials", max_bytes=16384
                )
                self.assertEqual(1, len(selection.entries))
                self.assert_masked(prompt)

    def test_a_split_cue_is_masked_and_other_markup_is_preserved(self) -> None:
        value = 'keep <em>retry</em>; DB_PASS<strong>WORD</strong>="fixture-password-9"'
        masked = records.redact_secrets(value)
        self.assertIn("keep <em>retry</em>", masked)
        self.assertIn(records.SECRET_MARKER, masked)
        self.assertNotIn("fixture-password-9", masked)
        self.assertEqual(masked, records.redact_secrets(masked))

    def test_credentials_in_attributes_are_not_hidden_from_the_raw_scan(self) -> None:
        value = f'<span title="{KEY}">keep retry</span>'
        self.assert_masked(records.redact_secrets(value))

    def test_formatting_after_a_credential_is_preserved(self) -> None:
        value = f"rotate {KEY}<em> then retry</em>"
        self.assertEqual("rotate AKIA…REDACTED<em> then retry</em>", records.redact_secrets(value))

    def test_real_word_boundaries_and_plain_prose_are_preserved(self) -> None:
        for value in (
            "AKIAIOSFODNN7 <em>EXAMPLE</em>",
            "AKIAIOSFODNN7\n<em>EXAMPLE</em>",
            "keep <em>retry</em> bounded",
            "compare a<b>c and x < 3",
            "clone https://someone@github.com/o/r.git",
            "PASSWORD=os.environ",
        ):
            with self.subTest(value=value):
                self.assertEqual(value, records.redact_secrets(value))

    def test_markup_above_the_scan_bound_is_withheld_without_a_raw_tail(self) -> None:
        value = "ordinary words " * 2000 + f"rotate {SPLITS[0]} today"
        self.assertEqual(records.SECRET_MARKER, records.redact_secrets(value))
        plain = "ordinary words " * 2000
        self.assertEqual(plain, records.redact_secrets(plain))

    def test_an_oversized_unfinished_attribute_is_refused_in_an_owned_process(self) -> None:
        script = (
            "from cargento_runtime import records; "
            "value=\"<em title='\"+'x'*1000000; "
            "assert records.redact_secrets(value)==records.SECRET_MARKER"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode())


class RestoringAnInlineCredentialFinal(final_tests._Source):
    def test_the_actual_whole_final_lookup_and_prompt_mask_beyond_the_excerpt(self) -> None:
        words = final_tests.long_text(25) + f" Rotate {SPLITS[0]} today."
        self.write([final_tests.record("u1", 1, words)])
        ledger = self.ledger()
        found = self.look(ledger)
        self.assertEqual("whole", found["outcome"])
        self.assertIn(records.SECRET_MARKER, found["words"])
        self.assertNotIn("EXAMPLE", found["words"])
        prompt, selected = reading.build_prompt(
            ledger,
            goal="Rotate credentials",
            max_bytes=16384,
            final_lookup=self.look,
        )
        self.assertEqual("whole", selected.newest_final)
        self.assertIn(records.SECRET_MARKER, prompt)
        self.assertNotIn("EXAMPLE", prompt)


class OpeningAnInlineCredentialDirection(direction_tests.TheServerVerifiesAnExplicitDirection):
    def test_the_actual_direction_route_returns_masked_whole_words(self) -> None:
        for wrapped in (False, True):
            with self.subTest(wrapped=wrapped):
                words = f"rotate {SPLITS[0]} today"
                self.session.prompt(command(words) if wrapped else words)
                self.session.save(self.path)
                selected = max(
                    (fact for fact in self.facts() if fact["type"] == "user_message"),
                    key=lambda fact: fact["at"],
                )
                with self.serving() as port:
                    opened = self.request(
                        port,
                        "/api/direction",
                        {"harness": "claude", "sid": SHORT, "fact_id": selected["fact_id"]},
                    )
                self.assertIs(True, opened["ok"])
                self.assertIn(records.SECRET_MARKER, opened["text"])
                self.assertNotIn("EXAMPLE", opened["text"])
                self.assertIn(records.SECRET_MARKER, opened["goal_choice"]["text"])
