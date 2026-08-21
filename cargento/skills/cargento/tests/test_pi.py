from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import records as runtime_records
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime import transcripts as runtime_transcripts
from cargento_runtime.collectors import pi as pi_collector

from .fixtures import (
    _iso,
    _jsonl,
)
from .support import (
    PiScanTestCase,
    cfg,
    make_runtime,
    runtime,
    store_patch,
)


class PiTranscriptTest(unittest.TestCase):
    """Pi v3 transcripts: only the leaf's parent chain is the live branch."""

    def setUp(self) -> None:
        # One runtime per test: the scanner is incremental, so successive calls
        # in a test must share the state the previous call recorded.
        self.config, self.state = make_runtime()

    def scan(self, path: Any) -> Any:
        return pi_collector.scan_pi_session(self.config, self.state, str(path))

    NOW = "2026-07-29T12:00:00Z"

    @staticmethod
    def _write(path: Path, records: list[dict[str, Any]]) -> None:
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

    @staticmethod
    def _message(
        entry_id: str,
        parent_id: str | None,
        timestamp: str,
        role: str,
        content: Any,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "type": "message",
            "id": entry_id,
            "parentId": parent_id,
            "timestamp": timestamp,
            "message": {"role": role, "content": content, **extra},
        }

    def test_an_unterminated_trailing_entry_waits_for_its_newline(self) -> None:
        # Pi appends line by line, so a record without its newline is still
        # being written; reading it would report a prompt the agent has not
        # finished sending. Mutation-checked: scanning to the raw file size
        # instead of the last complete entry passed the whole suite.
        header = {"type": "session", "version": 3, "id": "s1", "cwd": "/w/proj"}
        first = self._message("m1", None, "2026-07-29T11:59:30Z", "user", "First prompt")
        second = self._message("m2", "m1", "2026-07-29T11:59:55Z", "user", "Second prompt")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-session.jsonl"
            path.write_text(
                json.dumps(header)
                + "\n"
                + json.dumps(first)
                + "\n"
                + json.dumps(second)  # deliberately unterminated
            )

            scanned = self.scan(path)
            assert scanned is not None
            self.assertEqual("First prompt", scanned["last_prompt"])

            with path.open("a") as output:
                output.write("\n")
            completed = self.scan(path)

        assert completed is not None
        self.assertEqual("Second prompt", completed["last_prompt"])

    def test_metadata_and_global_name_survive_a_long_transcript(self) -> None:
        # Removing the global name pass, or reading only TAIL_BYTES, would make
        # this live session fall back to its prompt despite Pi's named selector.
        sid = "pi-session-id"
        header = {"type": "session", "version": 3, "id": sid, "cwd": "/w/proj"}
        named = {
            "type": "session_info",
            "id": "info-named",
            "parentId": None,
            "timestamp": "2026-07-29T11:59:00Z",
            "name": "Named session",
        }
        root = self._message(
            "root",
            None,
            "2026-07-29T11:59:10Z",
            "user",
            [{"type": "text", "text": "Implement the fix"}],
        )
        assistant = self._message(
            "assistant",
            "root",
            self.NOW,
            "assistant",
            [{"type": "toolCall", "id": "call-1", "name": "bash", "arguments": {}}],
            usage={"output": 40},
        )
        leaf = self._message(
            "leaf",
            "assistant",
            "2026-07-29T12:00:01Z",
            "toolResult",
            [{"type": "text", "text": "done"}],
        )
        filler = self._message(
            "discarded-filler",
            "root",
            "2026-07-29T11:59:20Z",
            "assistant",
            "x" * (cfg().tail_bytes + 10),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-session.jsonl"
            self._write(path, [header, named, root, filler, assistant, leaf])

            config, state = make_runtime()
            self.assertEqual(
                {"session_id": sid, "cwd": "/w/proj", "parent_session": None},
                runtime_transcripts.pi_meta(config, state, str(path)),
            )
            scan = self.scan(path)
            assert scan is not None
            self.assertEqual("Named session", scan["title"])
            self.assertEqual("Implement the fix", scan["last_prompt"])
            self.assertEqual("bash", scan["last_tool"])
            self.assertEqual([(runtime_records.parse_ts(self.NOW), 40)], scan["usage_events"])
            self.assertIn("turn", scan)

            with path.open("a") as output:
                output.write(
                    json.dumps(
                        {
                            "type": "session_info",
                            "id": "info-cleared",
                            "parentId": "leaf",
                            "timestamp": "2026-07-29T12:00:02Z",
                            "name": None,
                        }
                    )
                    + "\n"
                )
            cleared = self.scan(path)
            assert cleared is not None

        self.assertEqual("Implement the fix", cleared["title"])

    def test_active_branch_ignores_abandoned_usage_and_tools(self) -> None:
        # Following file order instead of parentId would surface this abandoned
        # branch's 900-token shell call as the active Pi session.
        records = [
            {"type": "session", "version": 3, "id": "tree", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Start work"),
            self._message("abandoned", "root", "2026-07-29T11:00:01Z", "user", "Abandoned prompt"),
            self._message(
                "bad-tool",
                "abandoned",
                "2026-07-29T11:00:02Z",
                "assistant",
                [{"type": "toolCall", "name": "wrong-tool"}],
                usage={"output": 900},
            ),
            self._message("shared", "root", "2026-07-29T11:00:30Z", "assistant", "thinking"),
            self._message("winning", "shared", "2026-07-29T11:01:00Z", "user", "Winning prompt"),
            self._message(
                "output-10",
                "winning",
                "2026-07-29T11:01:01Z",
                "assistant",
                [{"type": "toolCall", "name": "bash"}],
                usage={"output": 10},
            ),
            self._message(
                "output-3",
                "output-10",
                "2026-07-29T11:01:02Z",
                "toolResult",
                [],
                usage={"output": 3},
            ),
            {
                "type": "compaction",
                "id": "output-4",
                "parentId": "output-3",
                "timestamp": "2026-07-29T11:01:03Z",
                "usage": {"output": 4},
            },
            {
                "type": "branch_summary",
                "id": "output-5",
                "parentId": "output-4",
                "timestamp": "2026-07-29T11:01:04Z",
                "usage": {"output": 5},
            },
            self._message("leaf", "output-5", "2026-07-29T11:01:05Z", "assistant", "complete"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-tree.jsonl"
            self._write(path, records)
            scan = self.scan(path)
            assert scan is not None

        self.assertEqual("Winning prompt", scan["last_prompt"])
        self.assertEqual("bash", scan["last_tool"])
        self.assertEqual(
            [
                (runtime_records.parse_ts("2026-07-29T11:01:01Z"), 10),
                (runtime_records.parse_ts("2026-07-29T11:01:02Z"), 3),
                (runtime_records.parse_ts("2026-07-29T11:01:03Z"), 4),
                (runtime_records.parse_ts("2026-07-29T11:01:04Z"), 5),
            ],
            scan["usage_events"],
        )
        self.assertEqual([30.0], scan["turn"]["durations"])
        self.assertEqual(
            runtime_records.parse_ts("2026-07-29T11:01:00Z"),
            scan["turn"]["turn_start"],
        )

    @staticmethod
    def _switch(
        entry_id: str, parent_id: str | None, timestamp: str, provider: Any, model: Any
    ) -> dict[str, Any]:
        return {
            "type": "model_change",
            "id": entry_id,
            "parentId": parent_id,
            "timestamp": timestamp,
            "provider": provider,
            "modelId": model,
        }

    def test_the_newest_authority_wins_whichever_kind_carries_it(self) -> None:
        # Pi records the provider twice over: on the assistant message that
        # spent the turn, and on a `model_change` the user has not spent yet.
        # Recency alone decides, so no precedence rule is needed — but that only
        # holds if both kinds are consulted. Mutation-checked: ignoring
        # `model_change` reports the superseded anthropic turn, and walking the
        # path forwards instead of backwards reports the first entry. The
        # opposite mutation, ignoring the message provider, is caught by
        # `test_an_abandoned_branch_never_reports_its_authority` and
        # `test_switching_branch_does_not_leave_a_stale_authority_cached`, whose
        # winning provider sits on a message rather than on a switch.
        records = [
            {"type": "session", "version": 3, "id": "auth", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Start"),
            self._message(
                "turn-a",
                "root",
                "2026-07-29T11:00:01Z",
                "assistant",
                "one",
                provider="anthropic",
                model="claude-opus-5",
                usage={"output": 5},
            ),
            self._switch("sw", "turn-a", "2026-07-29T11:00:02Z", "openai-codex", "gpt-5.6-sol"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-auth.jsonl"
            self._write(path, records)
            after_switch = self.scan(path)
            assert after_switch is not None
            # A turn on the new provider: now the message is the newest again.
            with path.open("a") as output:
                output.write(
                    json.dumps(
                        self._message(
                            "turn-b",
                            "sw",
                            "2026-07-29T11:00:03Z",
                            "assistant",
                            "two",
                            provider="openai-codex",
                            model="gpt-5.6-sol",
                            usage={"output": 7},
                        )
                    )
                    + "\n"
                )
            after_turn = self.scan(path)
            assert after_turn is not None

        # The unspent switch is newer than the last turn, and is what the next
        # turn will cost.
        self.assertEqual("openai-codex", after_switch["provider"])
        self.assertEqual("gpt-5.6-sol", after_switch["model"])
        self.assertEqual("openai-codex", after_turn["provider"])

    def test_the_provider_and_model_always_come_from_one_entry(self) -> None:
        # Pairing them across entries would report a provider that never served
        # that model.
        records = [
            {"type": "session", "version": 3, "id": "pair", "cwd": "/w/proj"},
            self._message(
                "root",
                None,
                "2026-07-29T11:00:00Z",
                "assistant",
                "one",
                provider="anthropic",
                model="claude-opus-5",
            ),
            # Newest entry names a provider and no model at all.
            self._switch("sw", "root", "2026-07-29T11:00:01Z", "groq", None),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-pair.jsonl"
            self._write(path, records)
            scan = self.scan(path)
            assert scan is not None

        self.assertEqual("groq", scan["provider"])
        self.assertIsNone(scan["model"], "the older entry's model leaked across")

    def test_the_authority_is_bounded_and_scrubbed_before_it_can_reach_a_card(self) -> None:
        # Both values are the vendor's own text, copied out of an API response,
        # and DRC-4117 turns `model` from a Pi-only field into a slot every
        # harness's card draws — so the length is bounded and the control bytes
        # are stripped at the type guard both fields pass through, not trusted.
        # Mutation-checked: returning the raw string from `_text` publishes all
        # 96 characters of the model and the tab inside the provider with them.
        cap = runtime_sessions.MODEL_CAP_CHARS
        long_model = "gpt-" + "5" * 92
        records = [
            {"type": "session", "version": 3, "id": "cap", "cwd": "/w/proj"},
            self._message(
                "root",
                None,
                "2026-07-29T11:00:00Z",
                "assistant",
                "one",
                provider="open\tai-codex",
                model=long_model,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-cap.jsonl"
            self._write(path, records)
            scan = self.scan(path)
            assert scan is not None

        self.assertEqual(96, len(long_model), "fixture no longer exceeds the cap")
        self.assertEqual(long_model[:cap], scan["model"])
        self.assertEqual(cap, len(scan["model"]))
        self.assertEqual("open ai-codex", scan["provider"])

    def test_a_switch_bounds_its_authority_the_same_way_a_message_does(self) -> None:
        # The two kinds read different keys, so a cap applied to one arm and not
        # the other ships an unbounded model to anyone who just switched.
        cap = runtime_sessions.MODEL_CAP_CHARS
        long_model = "claude-" + "opus" * 20
        records = [
            {"type": "session", "version": 3, "id": "capsw", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Start"),
            self._switch("sw", "root", "2026-07-29T11:00:01Z", "anthropic", long_model),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-capsw.jsonl"
            self._write(path, records)
            scan = self.scan(path)
            assert scan is not None

        self.assertEqual(long_model[:cap], scan["model"])
        self.assertEqual("anthropic", scan["provider"], "a short value is left alone")

    def test_an_abandoned_branch_never_reports_its_authority(self) -> None:
        # The whole reason this is derived from the branch path rather than a
        # global reverse scan: `_latest_name` scans globally by design, and
        # copying that shape would surface a provider the user switched away
        # from on a branch the agent abandoned.
        records = [
            {"type": "session", "version": 3, "id": "abandon", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Start"),
            self._switch("wrong", "root", "2026-07-29T11:00:01Z", "groq", "llama-4"),
            self._message("shared", "root", "2026-07-29T11:00:02Z", "user", "Winning prompt"),
            self._message(
                "leaf",
                "shared",
                "2026-07-29T11:00:03Z",
                "assistant",
                "done",
                provider="anthropic",
                model="claude-opus-5",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-abandon.jsonl"
            self._write(path, records)
            scan = self.scan(path)
            assert scan is not None

        self.assertEqual("anthropic", scan["provider"])
        self.assertEqual("claude-opus-5", scan["model"])

    def test_switching_branch_does_not_leave_a_stale_authority_cached(self) -> None:
        # `_extend` truncates the cached path on a branch switch. A provider
        # cached as a scalar on the scan state, the way the session name is,
        # would survive that truncation and keep reporting the abandoned
        # branch's provider. Deriving from the path each time cannot go stale,
        # and this is the test that tells the two implementations apart.
        records = [
            {"type": "session", "version": 3, "id": "rebranch", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Start"),
            self._message(
                "first",
                "root",
                "2026-07-29T11:00:01Z",
                "assistant",
                "one",
                provider="groq",
                model="llama-4",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-rebranch.jsonl"
            self._write(path, records)
            before = self.scan(path)
            assert before is not None
            # Re-branch from root, discarding "first" and its provider.
            with path.open("a") as output:
                output.write(
                    json.dumps(
                        self._message(
                            "second",
                            "root",
                            "2026-07-29T11:00:02Z",
                            "assistant",
                            "two",
                            provider="anthropic",
                            model="claude-opus-5",
                        )
                    )
                    + "\n"
                )
            after = self.scan(path)
            assert after is not None

        self.assertEqual("groq", before["provider"])
        self.assertEqual("anthropic", after["provider"], "stale provider survived a re-branch")
        self.assertEqual("claude-opus-5", after["model"])

    def test_a_session_with_no_authority_makes_no_claim(self) -> None:
        # Not every session names one, and Pi's global default lives in
        # settings.json, which is *current* state: attributing today's default to
        # an older session would report a provider it never used.
        records = [
            {"type": "session", "version": 3, "id": "silent", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Start"),
            self._message("leaf", "root", "2026-07-29T11:00:01Z", "assistant", "done"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-silent.jsonl"
            self._write(path, records)
            scan = self.scan(path)
            assert scan is not None

        self.assertIsNone(scan["provider"])
        self.assertIsNone(scan["model"])

    def test_unusable_authority_values_are_dropped_not_rendered(self) -> None:
        # These stores are untrusted input like every other. A non-string or an
        # empty string must not reach the page as a provider name.
        for provider, model in ((123, ["x"]), ("", ""), (None, None), ({}, True)):
            with self.subTest(provider=provider):
                records = [
                    {"type": "session", "version": 3, "id": "junk", "cwd": "/w/proj"},
                    self._message("root", None, "2026-07-29T11:00:00Z", "user", "Start"),
                    self._switch("sw", "root", "2026-07-29T11:00:01Z", provider, model),
                ]
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "pi-junk.jsonl"
                    self._write(path, records)
                    scan = self.scan(path)
                    assert scan is not None
                self.assertIsNone(scan["provider"])
                self.assertIsNone(scan["model"])

    def test_initial_rebuild_follows_messages_through_session_info(self) -> None:
        records = [
            {"type": "session", "version": 3, "id": "named-tree", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Old prompt"),
            {
                "type": "session_info",
                "id": "named",
                "parentId": "root",
                "timestamp": "2026-07-29T11:00:01Z",
                "name": "Renamed work",
            },
            self._message(
                "new-prompt",
                "named",
                "2026-07-29T11:00:02Z",
                "user",
                "Continue after rename",
            ),
            self._message(
                "tool",
                "new-prompt",
                "2026-07-29T11:00:03Z",
                "assistant",
                [{"type": "toolCall", "name": "bash"}],
                usage={"output": 12},
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-named-tree.jsonl"
            self._write(path, records)
            scan = self.scan(path)
            assert scan is not None

        self.assertEqual("Renamed work", scan["title"])
        self.assertEqual("Continue after rename", scan["last_prompt"])
        self.assertEqual("bash", scan["last_tool"])
        self.assertEqual(
            [(runtime_records.parse_ts("2026-07-29T11:00:03Z"), 12)],
            scan["usage_events"],
        )
        self.assertEqual(
            runtime_records.parse_ts("2026-07-29T11:00:02Z"),
            scan["turn"]["turn_start"],
        )
        self.assertEqual(
            runtime_records.parse_ts("2026-07-29T11:00:03Z"),
            scan["last_event_ts"],
        )

    def test_incremental_append_follows_messages_through_session_info(self) -> None:
        records = [
            {"type": "session", "version": 3, "id": "append-name", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Old prompt"),
        ]
        appended = [
            {
                "type": "session_info",
                "id": "named",
                "parentId": "root",
                "timestamp": "2026-07-29T11:00:01Z",
                "name": "Renamed work",
            },
            self._message(
                "new-prompt",
                "named",
                "2026-07-29T11:00:02Z",
                "user",
                "Continue after rename",
            ),
            self._message(
                "tool",
                "new-prompt",
                "2026-07-29T11:00:03Z",
                "assistant",
                [{"type": "toolCall", "name": "bash"}],
                usage={"output": 12},
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-append-name.jsonl"
            self._write(path, records)
            before = self.scan(path)
            assert before is not None
            with path.open("a") as output:
                for record in appended:
                    output.write(json.dumps(record) + "\n")
            scan = self.scan(path)
            assert scan is not None

        self.assertEqual("Old prompt", before["last_prompt"])
        self.assertEqual("Renamed work", scan["title"])
        self.assertEqual("Continue after rename", scan["last_prompt"])
        self.assertEqual("bash", scan["last_tool"])
        self.assertEqual(
            [(runtime_records.parse_ts("2026-07-29T11:00:03Z"), 12)],
            scan["usage_events"],
        )
        self.assertEqual(
            runtime_records.parse_ts("2026-07-29T11:00:02Z"),
            scan["turn"]["turn_start"],
        )
        self.assertEqual(
            runtime_records.parse_ts("2026-07-29T11:00:03Z"),
            scan["last_event_ts"],
        )

    def test_disconnected_first_append_does_not_seed_an_empty_branch(self) -> None:
        header = {"type": "session", "version": 3, "id": "empty", "cwd": "/w/proj"}
        child = self._message(
            "child",
            "missing-parent",
            "2026-07-29T11:00:00Z",
            "user",
            "Disconnected prompt",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-empty.jsonl"
            self._write(path, [header])
            self.assertIsNone(self.scan(path))
            with path.open("a") as output:
                output.write(json.dumps(child) + "\n")
            scan = self.scan(path)

        self.assertIsNone(scan)

    def test_partial_writes_and_rebranching_preserve_the_last_complete_branch(self) -> None:
        # Treating an incomplete append as EOF, or retaining children after a
        # rebranch to root, would respectively erase useful state or show it.
        records = [
            {"type": "session", "version": 3, "id": "append", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "First prompt"),
            self._message("old-leaf", "root", "2026-07-29T11:00:01Z", "assistant", "old"),
        ]
        rebranch = self._message(
            "new-leaf", "root", "2026-07-29T11:02:00Z", "user", "Rebranched prompt"
        )
        encoded = json.dumps(rebranch)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-append.jsonl"
            self._write(path, records)
            first = self.scan(path)
            assert first is not None
            with path.open("a") as output:
                output.write("not json\n" + encoded[:-1])
            partial = self.scan(path)
            assert partial is not None
            with path.open("a") as output:
                output.write(encoded[-1:] + "\n")
            rebased = self.scan(path)
            assert rebased is not None

        self.assertEqual("First prompt", partial["last_prompt"])
        self.assertEqual("Rebranched prompt", rebased["last_prompt"])
        self.assertEqual("First prompt", rebased["title"])

    def test_corrupt_parent_does_not_replace_the_last_complete_branch(self) -> None:
        # Publishing a newest child before its parent has decoded disconnects
        # it from root and makes a partial write look like a new Pi session.
        records = [
            {"type": "session", "version": 3, "id": "corrupt-parent", "cwd": "/w/proj"},
            self._message("root", None, "2026-07-29T11:00:00Z", "user", "Stable prompt"),
            self._message("stable-leaf", "root", "2026-07-29T11:00:01Z", "assistant", "stable"),
        ]
        child = self._message(
            "unrooted-child", "corrupt-parent", "2026-07-29T11:01:00Z", "user", "Unrooted child"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-corrupt-parent.jsonl"
            self._write(path, records)
            stable = self.scan(path)
            assert stable is not None
            with path.open("a") as output:
                output.write('{"type":"message","id":"corrupt-parent"\n')
                output.write(json.dumps(child) + "\n")
            after_corruption = self.scan(path)
            assert after_corruption is not None

        self.assertEqual("Stable prompt", stable["last_prompt"])
        self.assertEqual("Stable prompt", after_corruption["last_prompt"])


class PiCollectorTest(PiScanTestCase):
    """Pi session stores are flat for exports and one-level nested by default."""

    NOW = 1_700_000_000.0

    @staticmethod
    def _header(sid: str, *, parent: str | None = None) -> dict[str, Any]:
        return {
            "type": "session",
            "version": 3,
            "id": sid,
            "timestamp": _iso(PiCollectorTest.NOW - 60),
            "cwd": "/w/proj",
            "parentSession": parent,
        }

    @staticmethod
    def _message(
        entry_id: str,
        parent_id: str | None,
        when: float,
        role: str,
        content: Any,
        *,
        usage: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        message: dict[str, Any] = {"role": role, "content": content}
        if usage is not None:
            message["usage"] = usage
        return {
            "type": "message",
            "id": entry_id,
            "parentId": parent_id,
            "timestamp": _iso(when),
            "message": message,
        }

    def test_discovery_requires_a_real_session_header(self) -> None:
        # A stray .jsonl in the Pi store must not make Pi "discovered": a
        # harness that is not installed has to read differently from a broken
        # one. Mutation-checked: skipping the header check passed the suite.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            root.mkdir()
            (root / "not-pi.jsonl").write_text('{"type": "other", "id": "x"}\n')
            with store_patch(PI_SESSIONS_DIR=str(root)):
                config, state = runtime()

                self.assertFalse(pi_collector.discover(config, state))

                (root / "real.jsonl").write_text(json.dumps(self._header("s1")) + "\n")

                self.assertTrue(pi_collector.discover(config, state))

    def test_collects_flat_and_nested_sessions_with_render_ready_details(self) -> None:
        # Missing either glob would hide one of Pi's supported on-disk layouts.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _jsonl(
                root / "flat.jsonl",
                [
                    self._header("flat"),
                    {"type": "session_info", "name": "Pi collector"},
                    self._message("prompt", None, self.NOW - 30, "user", "Build Pi support"),
                    self._message(
                        "tool",
                        "prompt",
                        self.NOW - 20,
                        "assistant",
                        [{"type": "toolCall", "name": "bash"}],
                        usage={"output": 100},
                    ),
                ],
                self.NOW - 20,
            )
            _jsonl(
                root / "--w-proj--" / "nested.jsonl",
                [
                    self._header("nested"),
                    self._message("prompt", None, self.NOW - 10, "user", "Nested session"),
                ],
                self.NOW - 10,
            )
            with store_patch(PI_SESSIONS_DIR=str(root)):
                config, state = runtime()
                rows = pi_collector.collect(config, state, self.NOW, 24, False)

        by_sid = {row["sid"]: row for row in rows}
        self.assertEqual({"flat", "nested"}, set(by_sid))
        flat = by_sid["flat"]
        self.assertEqual("w/proj", flat["project"])
        self.assertEqual("Pi collector", flat["title"])
        self.assertEqual("Build Pi support", flat["last_prompt"])
        self.assertEqual(10, flat["rate_per_min"])
        self.assertEqual("running bash", flat["state_detail"])
        self.assertIsNotNone(flat["turn"])
        self.assertEqual("30s", flat["turn"]["elapsed_h"])

    def test_keeps_the_newest_duplicate_and_does_not_fold_parent_sessions(self) -> None:
        # Deduping by parentSession would merge independent resumed Pi sessions.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _jsonl(
                root / "old.jsonl",
                [
                    self._header("duplicate"),
                    {"type": "session_info", "name": "Old copy"},
                    self._message("old", None, self.NOW - 60, "user", "Old prompt"),
                ],
                self.NOW - 60,
            )
            _jsonl(
                root / "--w-proj--" / "old-peer.jsonl",
                [
                    self._header("duplicate"),
                    {"type": "session_info", "name": "Old peer"},
                    self._message("old-peer", None, self.NOW - 60, "user", "Old peer prompt"),
                ],
                self.NOW - 60,
            )
            _jsonl(
                root / "--w-proj--" / "new.jsonl",
                [
                    self._header("duplicate"),
                    {"type": "session_info", "name": "New copy"},
                    self._message("new", None, self.NOW - 5, "user", "New prompt"),
                ],
                self.NOW - 5,
            )
            _jsonl(
                root / "--w-proj--" / "parent.jsonl",
                [
                    self._header("parent"),
                    self._message("parent-prompt", None, self.NOW - 5, "user", "Parent prompt"),
                ],
                self.NOW - 5,
            )
            _jsonl(
                root / "--w-proj--" / "child.jsonl",
                [
                    self._header("child", parent="parent"),
                    self._message("child-prompt", None, self.NOW - 5, "user", "Child prompt"),
                ],
                self.NOW - 5,
            )
            with store_patch(PI_SESSIONS_DIR=str(root)):
                config, state = runtime()
                rows = pi_collector.collect(config, state, self.NOW, 24, True)

        by_sid = {row["sid"]: row for row in rows}
        self.assertEqual({"duplicate", "parent", "child"}, set(by_sid))
        self.assertEqual("New copy", by_sid["duplicate"]["title"])

    def test_ignores_non_session_files_and_rejects_future_event_activity_and_rate(self) -> None:
        # Promoting any JSONL to a session or accepting a future token event
        # would show phantom Pi work and output.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _jsonl(
                root / "not-a-session.jsonl",
                [self._message("orphan", None, self.NOW, "user", "Not a session")],
                self.NOW,
            )
            _jsonl(
                root / "future.jsonl",
                [
                    self._header("future"),
                    self._message("prompt", None, self.NOW - 20, "user", "Real prompt"),
                    self._message(
                        "future-output",
                        "prompt",
                        self.NOW + 86_400,
                        "assistant",
                        "future output",
                        usage={"output": 999},
                    ),
                ],
                self.NOW - 20,
            )
            with store_patch(PI_SESSIONS_DIR=str(root)):
                config, state = runtime()
                rows = pi_collector.collect(config, state, self.NOW, 24, True)

        self.assertEqual(["future"], [row["sid"] for row in rows])
        self.assertEqual(self.NOW - 20, rows[0]["last_activity"])
        self.assertEqual(0, rows[0]["rate_per_min"])

    def test_pi_fo_session_renders_spacedock_strip(self) -> None:
        # A Pi first officer writes the same boot envelope a Claude officer
        # does, as a ``toolResult`` message. Finding it classifies the session
        # as a first officer and feeds ``session_workflows`` the workflow
        # directory and entity-state directory. Falsifying edit: remove the
        # ``toolResult`` branch from ``tool_result_text`` —
        # ``transcript_boot`` returns [], ``spacedock`` is None, the
        # assertion fails.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / "wf"
            wf.mkdir()
            (wf / "README.md").write_text(
                "---\n"
                "commissioned-by: spacedock@1.0.0\n"
                "stages:\n"
                "  states:\n"
                "    - name: intake\n"
                "      initial: true\n"
                "    - name: review\n"
                "    - name: posted\n"
                "      terminal: true\n"
                "---\n",
                encoding="utf-8",
            )
            entity_state = wf / ".spacedock-state"
            entity_state.mkdir()
            entity_file = entity_state / "drc-1.md"
            entity_file.write_text("---\nstatus: review\n---\n\n# entity\n", encoding="utf-8")
            os.utime(entity_file, (self.NOW, self.NOW))
            envelope = json.dumps(
                {
                    "command": "boot",
                    "definition_dir": str(wf),
                    "entity_dir": str(entity_state),
                    "dispatchable": [],
                }
            )
            sessions_dir = root / "sessions"
            sessions_dir.mkdir()
            _jsonl(
                sessions_dir / "fo.jsonl",
                [
                    self._header("fo"),
                    self._message("p", None, self.NOW - 30, "user", "Start workflow"),
                    self._message(
                        "call",
                        "p",
                        self.NOW - 20,
                        "assistant",
                        [{"type": "toolCall", "name": "bash"}],
                    ),
                    self._message(
                        "boot",
                        "call",
                        self.NOW - 15,
                        "toolResult",
                        [{"type": "text", "text": "=== BOOT ===\n" + envelope}],
                    ),
                ],
                self.NOW - 15,
            )
            with store_patch(PI_SESSIONS_DIR=str(sessions_dir)):
                config, state = runtime()
                rows = pi_collector.collect(config, state, self.NOW, 24, True)

        by_sid = {row["sid"]: row for row in rows}
        self.assertIn("fo", by_sid)
        sd = by_sid["fo"]["spacedock"]
        assert sd is not None
        self.assertEqual("first-officer", sd["role"])
        self.assertEqual(1, len(sd["workflows"]))
        self.assertEqual(["intake", "review", "posted"], sd["workflows"][0]["stages"])
        # Equality, not membership: `live` and `stage` are the fields a wrong
        # worker list silently rewrites, and `live` can never be True on Pi
        # because Pi reports no workers to attribute one to.
        self.assertEqual(
            [{"slug": "drc-1", "stage": "review", "cycle": "", "live": False}],
            sd["workflows"][0]["entities"],
        )

    def test_pi_non_fo_session_has_no_spacedock(self) -> None:
        # A Pi session with no boot envelope in its transcript has no
        # Spacedock strip — the baseline does not move. Falsifying edit:
        # unconditionally set ``spacedock`` on every Pi session regardless of
        # boot presence — the test fails, which is the baseline moving the
        # wrong way.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions"
            sessions_dir.mkdir()
            _jsonl(
                sessions_dir / "plain.jsonl",
                [
                    self._header("plain"),
                    self._message("p", None, self.NOW - 10, "user", "Just a normal session"),
                    self._message("a", "p", self.NOW - 5, "assistant", "working"),
                ],
                self.NOW - 5,
            )
            with store_patch(PI_SESSIONS_DIR=str(sessions_dir)):
                config, state = runtime()
                rows = pi_collector.collect(config, state, self.NOW, 24, True)

        self.assertEqual(["plain"], [row["sid"] for row in rows])
        # Subscript, not `.get`: with `.get` this passes even if the key were
        # dropped from the published row altogether.
        self.assertIsNone(rows[0]["spacedock"])


class TurnTrackingTest(unittest.TestCase):
    def setUp(self) -> None:
        # One runtime per test: the scanner is incremental, so successive calls
        # in a test must share the state the previous call recorded.
        self.config, self.state = make_runtime()

    def scan(self, path: Any) -> Any:
        return pi_collector.scan_pi_session(self.config, self.state, str(path))

    def test_pi_turns_apply_the_quiet_gap_rule(self) -> None:
        # Omitting the quiet-gap reset would count the inactive wait as work.
        records = [
            {"type": "session", "version": 3, "id": "turns", "cwd": "/w/proj"},
            PiTranscriptTest._message("prompt", None, "2026-07-29T11:00:00Z", "user", "Work"),
            PiTranscriptTest._message(
                "event", "prompt", "2026-07-29T11:00:05Z", "assistant", "working"
            ),
            PiTranscriptTest._message(
                "resumed", "event", "2026-07-29T11:11:00Z", "assistant", "resumed"
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-turns.jsonl"
            PiTranscriptTest._write(path, records)
            scan = self.scan(path)
            assert scan is not None

        self.assertEqual([5.0], scan["turn"]["durations"])
        self.assertEqual(
            runtime_records.parse_ts("2026-07-29T11:11:00Z"),
            scan["turn"]["turn_start"],
        )
