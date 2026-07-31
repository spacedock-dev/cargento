from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import records as runtime_records
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
