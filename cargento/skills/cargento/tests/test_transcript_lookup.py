"""Press-only source lookup on synthetic long transcripts; no model calls."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cargento_runtime import io as runtime_io
from cargento_runtime import project_context, reading
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state


class TranscriptSourceLookupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "session.jsonl"
        self.config = build_runtime_config(
            environ={"HOME": self.temp.name},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.path.parent / "server.py",
        )
        self.state = build_runtime_state(self.config, started=0.0)
        self.words = "Build the queue. " + "Read the plan first. " * 20 + "Preserve pending work."
        self.write(self.words)

    def write(self, text: str) -> None:
        records = [
            {
                "type": "user",
                "timestamp": "2026-09-24T03:00:01Z",
                "message": {"role": "user", "content": text},
            },
            {
                "type": "assistant",
                "timestamp": "2026-09-24T03:00:02Z",
                "message": {"role": "assistant", "content": "x" * 500_000},
            },
        ]
        self.path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def lookup(self) -> list[dict[str, object]]:
        return project_context.transcript_user_facts(
            self.config, self.state, str(self.path), "claude", "synthetic"
        )

    def test_adopted_prompt_is_found_after_it_leaves_the_tail(self) -> None:
        tail = project_context.instruction_events(
            self.config, str(self.path), "claude", "synthetic"
        )
        self.assertEqual([], tail)
        revision = {
            "goal_source": "first-prompt",
            "goal_source_at": 1_790_218_801.0,
            "goal": self.words[:240],
        }
        found = reading.adopted_prompt(revision, self.lookup(), "claude", "synthetic")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(self.words, found[1])

    def test_cache_invalidates_on_same_size_rewrite(self) -> None:
        first = self.lookup()
        self.write(self.words.replace("queue", "stack"))
        stamp = self.path.stat()
        os.utime(self.path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000))
        second = self.lookup()
        self.assertNotEqual(first[0]["reader_words"], second[0]["reader_words"])

    def test_returned_facts_cannot_poison_the_cache(self) -> None:
        first = self.lookup()
        first[0]["reader_words"] = "poison"
        self.assertEqual(self.words, self.lookup()[0]["reader_words"])

    def test_read_bound_never_treats_a_partial_record_as_a_prompt(self) -> None:
        with mock.patch.object(project_context, "SEMANTIC_BACKFILL_MAX_BYTES", 40):
            self.assertEqual([], self.lookup())

    def test_changed_size_invalidates_even_with_the_same_mtime(self) -> None:
        first = self.lookup()
        stamp = self.path.stat()
        self.write(self.words + " Include the exporter.")
        os.utime(self.path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertNotEqual(first[0]["reader_words"], self.lookup()[0]["reader_words"])

    def test_deleted_source_does_not_return_cached_words(self) -> None:
        self.lookup()
        self.path.unlink()
        self.assertEqual([], self.lookup())

    def test_a_cached_source_survives_a_redundant_read_failure(self) -> None:
        self.lookup()
        with mock.patch.object(runtime_io, "read_prefix_bytes", side_effect=OSError):
            self.assertEqual(self.words, self.lookup()[0]["reader_words"])

    def test_one_cache_entry_cannot_be_reused_for_a_different_session(self) -> None:
        self.lookup()
        other = project_context.transcript_user_facts(
            self.config, self.state, str(self.path), "claude", "other"
        )
        self.assertEqual({"harness": "claude", "sid": "other"}, other[0]["source_session"])

    def test_a_nonregular_source_is_refused(self) -> None:
        self.assertEqual(
            [],
            project_context.transcript_user_facts(
                self.config, self.state, str(self.path.parent), "claude", "synthetic"
            ),
        )

    def test_a_read_failure_does_not_cache_an_empty_source(self) -> None:
        with mock.patch.object(runtime_io, "read_prefix_bytes", side_effect=OSError):
            self.assertEqual([], self.lookup())
        self.assertEqual(self.words, self.lookup()[0]["reader_words"])

    def test_only_complete_prefix_records_survive_a_read_bound(self) -> None:
        first_line = self.path.read_bytes().split(b"\n", 1)[0]
        with mock.patch.object(
            project_context, "SEMANTIC_BACKFILL_MAX_BYTES", len(first_line) + 20
        ):
            self.assertEqual(self.words, self.lookup()[0]["reader_words"])

    def test_distinct_same_time_messages_remain_ambiguous(self) -> None:
        prefix = "Shared instruction prefix " * 12
        records = [
            {
                "type": "user",
                "id": name,
                "timestamp": "2026-09-24T03:00:01Z",
                "message": {"role": "user", "content": prefix + suffix},
            }
            for name, suffix in (("first", "Keep the queue."), ("second", "Drop the queue."))
        ]
        self.path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        facts = self.lookup()
        self.assertEqual(2, len(facts))
        revision = {
            "goal_source": "first-prompt",
            "goal_source_at": 1_790_218_801.0,
            "goal": prefix[:240],
        }
        self.assertIsNone(reading.adopted_prompt(revision, facts, "claude", "synthetic"))
