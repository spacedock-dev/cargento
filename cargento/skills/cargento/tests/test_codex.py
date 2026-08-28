from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cargento_runtime import records
from cargento_runtime import records as runtime_records
from cargento_runtime import transcripts as runtime_transcripts
from cargento_runtime import turns as runtime_turns
from cargento_runtime.collectors import codex as codex_collector

from .support import (
    RuntimeTestCase,
    config_patch,
    make_runtime,
    runtime,
    store_patch,
)


class CodexCollectorTest(RuntimeTestCase):
    def test_codex_meta_extracts_parent_thread_id(self) -> None:
        record = {
            "type": "session_meta",
            "payload": {
                "id": "child-thread",
                "thread_source": "subagent",
                "agent_nickname": "reviewer",
                "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent-thread"}}},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            path.write_text(json.dumps(record) + "\n")
            config, state = make_runtime()
            meta = runtime_transcripts.codex_meta(config, state, str(path))

        self.assertTrue(meta["subagent"])
        self.assertEqual("child-thread", meta["session_id"])
        self.assertEqual("parent-thread", meta["parent_session_id"])

    def test_codex_subagent_usage_is_added_after_own_start_boundary(self) -> None:
        now = time.time()

        def timestamp(offset: float) -> str:
            iso = datetime.fromtimestamp(now + offset, UTC).isoformat()
            return str(iso)

        parent_id = "11111111-1111-1111-1111-111111111111"
        child_id = "22222222-2222-2222-2222-222222222222"
        parent_meta = {
            "type": "session_meta",
            "payload": {"id": parent_id, "cwd": "/tmp/project"},
        }
        child_meta = {
            "type": "session_meta",
            "payload": {
                "id": child_id,
                "thread_source": "subagent",
                "agent_nickname": "worker",
                "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent_id}}},
            },
        }

        def token_record(offset: float, output_tokens: int) -> dict[str, Any]:
            return {
                "type": "event_msg",
                "timestamp": timestamp(offset),
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"output_tokens": output_tokens}},
                },
            }

        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026" / "01" / "01"
            day.mkdir(parents=True)
            parent = day / "rollout-parent.jsonl"
            child = day / "rollout-child.jsonl"
            parent.write_text(
                "\n".join(json.dumps(record) for record in [parent_meta, token_record(-10, 100)])
                + "\n"
            )
            child.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        child_meta,
                        token_record(-30, 900),
                        {
                            "type": "event_msg",
                            "timestamp": timestamp(-20),
                            "payload": {
                                "type": "task_started",
                                "started_at": now - 20,
                            },
                        },
                        token_record(-10, 900),
                    ]
                )
                + "\n"
            )

            with store_patch(CODEX_SESSIONS_DIR=str(Path(tmp))):
                config, state = runtime()
                sessions = codex_collector.collect(config, state, now, 24, False)

        self.assertEqual(1, len(sessions))
        self.assertEqual(100, sessions[0]["rate_per_min"])
        # Every measurement key is present. Neither rollout here declares a
        # turn_context, so the model is unread, while the child's first dated
        # record still supplies its start independently.
        self.assertEqual(
            [
                {
                    "name": "worker",
                    "model": None,
                    "started_at": runtime_records.parse_ts(timestamp(-30)),
                }
            ],
            sessions[0]["subagents"],
        )
        self.assertEqual(runtime_records.parse_ts(timestamp(-10)), sessions[0]["started_at"])
        self.assertIsNone(sessions[0]["model"])

    def test_codex_meta_tolerates_malformed_payload_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            non_dict = Path(tmp) / "rollout-a.jsonl"
            non_dict.write_text('{"payload":42}\n')
            bad_fields = Path(tmp) / "rollout-b.jsonl"
            bad_fields.write_text(
                json.dumps(
                    {
                        "payload": {
                            "id": "s1",
                            "agent_nickname": 7,
                            "agent_path": 42,
                            "source": "not-a-dict",
                        }
                    }
                )
                + "\n"
            )

            config, state = make_runtime()
            meta_a = runtime_transcripts.codex_meta(config, state, str(non_dict))
            meta_b = runtime_transcripts.codex_meta(config, state, str(bad_fields))

        self.assertIsNone(meta_a["session_id"])
        self.assertFalse(meta_a["subagent"])
        self.assertEqual("s1", meta_b["session_id"])
        self.assertIsNone(meta_b["agent_label"])
        self.assertIsNone(meta_b["parent_session_id"])


def _token_count(when: float, limits: dict[str, Any] | Any) -> dict[str, Any]:
    return {
        "timestamp": datetime.fromtimestamp(when, tz=UTC).isoformat().replace("+00:00", "Z"),
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {"last_token_usage": {"output_tokens": 5}},
            "rate_limits": limits,
        },
    }


def _limits(
    *windows: tuple[int, float, float],
) -> dict[str, Any]:
    """A rate_limits block from (window_minutes, used_percent, resets_at) triples."""
    slots = ["primary", "secondary"]
    block: dict[str, Any] = {"limit_id": "codex", "plan_type": "test"}
    for slot, (minutes, pct, resets) in zip(slots, windows, strict=False):
        block[slot] = {"used_percent": pct, "window_minutes": minutes, "resets_at": resets}
    return block


def _local_noon() -> float:
    """Today at 12:00 local, so a reset a few hours out stays on the same date."""
    return (
        datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
    )


class CodexUsageTest(RuntimeTestCase):
    """The Codex quota tile: rate_limits snapshots read from rollout files."""

    def _rollout(self, root: Path, name: str, when: float, records: list[dict[str, Any]]) -> Path:
        path = root / "2026" / "08" / "04" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in records))
        os.utime(path, (when, when))
        return path

    def test_analyzer_captures_the_newest_rate_limits_snapshot(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._rollout(
                Path(tmp),
                "rollout-a.jsonl",
                now,
                [
                    _token_count(now - 60, _limits((10080, 41.0, now + 900))),
                    _token_count(now - 5, _limits((10080, 62.0, now + 900))),
                ],
            )
            config, _ = make_runtime()
            info = runtime_transcripts.analyze_codex_transcript(config, str(path))

        epoch, limits = info["rate_limits"]
        self.assertAlmostEqual(now - 5, epoch, delta=1.5)
        self.assertEqual(62.0, limits["primary"]["used_percent"])

    def test_analyzer_tolerates_malformed_rate_limits(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._rollout(
                Path(tmp),
                "rollout-a.jsonl",
                now,
                [_token_count(now - 5, "not-a-dict"), _token_count(now - 2, None)],
            )
            config, _ = make_runtime()
            info = runtime_transcripts.analyze_codex_transcript(config, str(path))

        self.assertIsNone(info["rate_limits"])

    def test_usage_maps_windows_by_minutes_and_bounds_percent(self) -> None:
        # Anchored to local noon rather than the wall clock. `format_reset` prints a
        # bare "HH:MM" only when the reset falls on the same LOCAL date, and this
        # pins a reset one hour out -- so between 23:00 and midnight it crossed
        # midnight and came back as "Thu 00:06". CI runs in UTC, which made it a
        # one-hour-a-day failure for everybody.
        now = _local_noon()
        with tempfile.TemporaryDirectory() as tmp:
            self._rollout(
                Path(tmp),
                "rollout-a.jsonl",
                now,
                [
                    _token_count(
                        now - 5, _limits((300, 63.4, now + 3600), (10080, 141.0, now + 90000))
                    )
                ],
            )
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                entries = codex_collector.usage(config, state, now, 24)

        (entry,) = entries
        self.assertEqual("codex", entry["harness"])
        self.assertEqual("ok", entry["state"])
        self.assertAlmostEqual(now - 5, entry["asOf"], delta=1.5)
        self.assertEqual(63, entry["fiveH"]["pct"])
        self.assertEqual(100, entry["week"]["pct"])
        self.assertRegex(entry["fiveH"]["reset"], r"^\d{2}:\d{2}$")
        # The disk reader ships the instant too, same as the fetchers, so the
        # page can count down instead of printing a clock time.
        self.assertAlmostEqual(now + 3600, entry["fiveH"]["resetAt"], delta=1.5)

    def test_usage_publishes_a_weekly_only_plan(self) -> None:
        # A prolite account writes only the weekly window (secondary is null).
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            self._rollout(
                Path(tmp),
                "rollout-a.jsonl",
                now,
                [_token_count(now - 5, _limits((10080, 62.0, now + 3 * 86400)))],
            )
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                entries = codex_collector.usage(config, state, now, 24)

        (entry,) = entries
        self.assertNotIn("fiveH", entry)
        self.assertEqual(62, entry["week"]["pct"])
        self.assertRegex(entry["week"]["reset"], r"^[A-Z][a-z]{2} \d{2}:\d{2}$")
        self.assertAlmostEqual(now + 3 * 86400, entry["week"]["resetAt"], delta=1.5)

    def test_usage_newest_snapshot_wins_across_files(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            self._rollout(
                Path(tmp),
                "rollout-old.jsonl",
                now - 600,
                [_token_count(now - 600, _limits((10080, 30.0, now + 900)))],
            )
            self._rollout(
                Path(tmp),
                "rollout-new.jsonl",
                now,
                [_token_count(now - 5, _limits((10080, 70.0, now + 900)))],
            )
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                entries = codex_collector.usage(config, state, now, 24)

        self.assertEqual(70, entries[0]["week"]["pct"])

    def test_usage_is_empty_without_a_snapshot_or_past_the_window(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                self.assertEqual([], codex_collector.usage(config, state, now, 24))
            self._rollout(
                Path(tmp),
                "rollout-stale.jsonl",
                now - 30 * 86400,
                [_token_count(now - 30 * 86400, _limits((10080, 55.0, now + 900)))],
            )
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                self.assertEqual([], codex_collector.usage(config, state, now, 24))


def _stamp(when: float) -> str:
    return datetime.fromtimestamp(when, tz=UTC).isoformat().replace("+00:00", "Z")


def _turn_context(when: float, model: Any) -> dict[str, Any]:
    """One `turn_context` record, as Codex writes it at the head of every turn."""
    return {
        "timestamp": _stamp(when),
        "type": "turn_context",
        "payload": {"cwd": "/tmp/project", "effort": "high", "model": model},
    }


def _task_started(when: float) -> dict[str, Any]:
    return {
        "timestamp": _stamp(when),
        "type": "event_msg",
        "payload": {"type": "task_started", "started_at": when},
    }


def _padding(when: float, filler: int = 1000) -> dict[str, Any]:
    """A well-formed record carrying neither a turn signal nor a model.

    Streamed deltas are what actually sits between a turn's context record and
    the end of a long rollout, and they are what pushes the declaration out of
    reach of any tail-sized read.
    """
    return {
        "timestamp": _stamp(when),
        "type": "event_msg",
        "payload": {"type": "agent_message_delta", "delta": "x" * filler},
    }


class CodexModelSignalTest(RuntimeTestCase):
    """`records.model_signal`: what it will read, and what it refuses to."""

    def test_the_signal_is_gated_on_the_harness_that_writes_the_record(self) -> None:
        # scan_turns runs this over five harnesses' transcripts. Ungated, any of
        # them could publish a model out of a record that merely shares a type
        # name -- which would be a guess rendered identically to a measurement.
        record = _turn_context(0, "gpt-5.6-sol")
        self.assertEqual(
            "gpt-5.6-sol",
            runtime_records.model_signal(record, "codex", 40),
        )
        for harness in ("claude", "gemini", "copilot", "droid"):
            self.assertIsNone(runtime_records.model_signal(record, harness, 40))

    def test_only_a_usable_string_is_reported_and_never_a_stand_in(self) -> None:
        cases: list[Any] = [None, 42, True, ["gpt-5"], {"name": "gpt-5"}, "", "   "]
        for value in cases:
            with self.subTest(value=value):
                self.assertIsNone(
                    runtime_records.model_signal(_turn_context(0, value), "codex", 40)
                )
        # A record of another type carries no model even on the right harness.
        self.assertIsNone(runtime_records.model_signal(_task_started(0), "codex", 40))

    def test_vendor_text_is_bounded_and_stripped_of_control_characters(self) -> None:
        # The value reaches the DOM, so it is bounded here and escaped again at
        # the render site. Neither layer is a substitute for the other.
        hostile = "gpt-\x00\x1b5.6\x7f-sol " + "z" * 200
        read = runtime_records.model_signal(_turn_context(0, hostile), "codex", 40)
        assert read is not None
        self.assertEqual(40, len(read))
        self.assertNotIn("\x00", read)
        self.assertNotIn("\x1b", read)
        self.assertNotIn("\x7f", read)
        self.assertTrue(read.startswith("gpt- 5.6 -sol "))


class CodexSessionModelTest(RuntimeTestCase):
    """The model a Codex session is running on, read where it actually sits."""

    def _write(
        self,
        root: Path,
        name: str,
        entries: list[dict[str, Any]],
        when: float,
    ) -> Path:
        path = root / "2026" / "08" / "07" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in entries))
        os.utime(path, (when, when))
        return path

    def test_the_model_is_found_far_behind_the_tail_a_transcript_read_would_stop_at(
        self,
    ) -> None:
        """The whole point of reading this inside the turn scanner.

        Every other Codex display field comes from `analyze_codex_transcript`,
        which reads the last `tail_bytes` of the rollout. On a real store the
        last `turn_context` sits a median of 273 KB and up to 3 MB behind EOF,
        so a tail-sized read reports "no model reported" for better than a third
        of sessions while passing every small fixture. This fixture is built to
        fail that way if the source is ever moved.
        """
        now = time.time()
        sid = "33333333-3333-3333-3333-333333333333"
        entries: list[dict[str, Any]] = [
            {"type": "session_meta", "payload": {"id": sid, "cwd": "/tmp/project"}},
            _task_started(now - 60),
            _turn_context(now - 60, "gpt-5.6-sol"),
        ]
        entries += [_padding(now - 30) for _ in range(420)]

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), "rollout-deep.jsonl", entries, now)
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                blob = path.read_bytes()
                # The fixture is only meaningful if the declaration really is
                # out of a tail read's reach. Pin that, not just the outcome.
                self.assertNotIn(b'"turn_context"', blob[-config.tail_bytes :])
                collected = codex_collector.collect(config, state, now, 24, False)

        (session,) = collected
        self.assertEqual("gpt-5.6-sol", session["model"])
        # No source on disk names a vendor, and reading one off the harness
        # name would be inference.
        self.assertIsNone(session["provider"])

    def test_a_rollout_that_declares_no_model_reports_none_rather_than_a_guess(
        self,
    ) -> None:
        # Reachable on the current CLI, not only on legacy files: a short
        # session with a task_started and no turn_context. "No model reported"
        # is a third state and must not be filled in from anything nearby.
        now = time.time()
        sid = "44444444-4444-4444-4444-444444444444"
        entries: list[dict[str, Any]] = [
            {"type": "session_meta", "payload": {"id": sid, "cwd": "/tmp/project"}},
            _task_started(now - 40),
            _padding(now - 30, filler=20),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            self._write(Path(tmp), "rollout-quiet.jsonl", entries, now)
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                collected = codex_collector.collect(config, state, now, 24, False)

        (session,) = collected
        self.assertIsNone(session["model"])
        self.assertEqual([], session["subagents"])

    def test_the_last_declaration_in_file_order_is_the_one_published(self) -> None:
        """The rule is "the model in current use", not "the models used".

        `turn_context` is re-written at the head of every turn, so the newest
        one is the current setting. This fixture puts two values in one file to
        pin the overwrite; no live rollout observed carries two, so nothing here
        claims a mid-session change was measured.
        """
        now = time.time()
        sid = "55555555-5555-5555-5555-555555555555"
        entries: list[dict[str, Any]] = [
            {"type": "session_meta", "payload": {"id": sid, "cwd": "/tmp/project"}},
            _task_started(now - 120),
            _turn_context(now - 120, "gpt-5.5"),
            _task_started(now - 40),
            _turn_context(now - 40, "gpt-5.6-sol"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            self._write(Path(tmp), "rollout-two.jsonl", entries, now)
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                collected = codex_collector.collect(config, state, now, 24, False)

        self.assertEqual("gpt-5.6-sol", collected[0]["model"])

    def test_each_subagent_publishes_the_model_its_own_rollout_declares(self) -> None:
        """A child thread is its own rollout and declares its own model.

        All three children are published with whatever was read, including the
        one that matches the parent and the one that reported nothing. Deciding
        which of them is worth showing is the page's job and is made on two
        measured values; the collector must not pre-empt it, because "matches
        the parent" and "not measured" are different facts and both have to
        survive the wire.
        """
        now = time.time()
        parent_id = "66666666-6666-6666-6666-666666666666"

        def child(sid: str, nickname: str, model: Any) -> list[dict[str, Any]]:
            entries: list[dict[str, Any]] = [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": sid,
                        "thread_source": "subagent",
                        "agent_nickname": nickname,
                        "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent_id}}},
                    },
                },
                _task_started(now - 30),
            ]
            if model is not None:
                entries.append(_turn_context(now - 30, model))
            return entries

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(
                root,
                "rollout-parent.jsonl",
                [
                    {"type": "session_meta", "payload": {"id": parent_id, "cwd": "/tmp/project"}},
                    _task_started(now - 50),
                    _turn_context(now - 50, "gpt-5.6-sol"),
                ],
                now,
            )
            # The only differing pair seen on a live store is a terra child
            # under a sol parent, so that is the pair the fixture uses.
            self._write(root, "rollout-a.jsonl", child("c-a", "Confucius", "gpt-5.6-terra"), now)
            self._write(root, "rollout-b.jsonl", child("c-b", "Meitner", "gpt-5.6-sol"), now)
            self._write(root, "rollout-c.jsonl", child("c-c", "Ohm", None), now)

            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                collected = codex_collector.collect(config, state, now, 24, False)

        (session,) = collected
        self.assertEqual("gpt-5.6-sol", session["model"])
        self.assertEqual(
            {"Confucius": "gpt-5.6-terra", "Meitner": "gpt-5.6-sol", "Ohm": None},
            {a["name"]: a["model"] for a in session["subagents"]},
        )
        # `model` is a key on every element, never an absence and never a
        # suffix on the label: a subagent genuinely named "Ohm · gpt-5" must
        # stay distinguishable from a reading.
        expected_start = runtime_records.parse_ts(_stamp(now - 30))
        for agent in session["subagents"]:
            self.assertEqual({"name", "model", "started_at"}, set(agent))
            self.assertEqual(expected_start, agent["started_at"])


class CodexModelPrefixScanTest(RuntimeTestCase):
    """The branch that runs when a rollout grew past the scanner's budget."""

    def _rollout(self, root: Path, entries: list[dict[str, Any]]) -> Path:
        path = root / "rollout-big.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in entries))
        return path

    def test_the_backward_pass_reaches_a_declaration_left_in_the_skipped_prefix(
        self,
    ) -> None:
        # A rollout bigger than the scan budget is read backward from the tail
        # boundary. `turn_context` is written after its `task_started`, so the
        # backward walk crosses it before the boundary that ends the walk.
        base = time.time() - 100_000
        entries: list[dict[str, Any]] = [
            {"type": "session_meta", "payload": {"id": "big", "cwd": "/tmp/project"}},
            _task_started(base),
            _turn_context(base, "gpt-5.6-sol"),
        ]
        entries += [_padding(base + 1 + i) for i in range(20)]

        with tempfile.TemporaryDirectory() as tmp, config_patch(turn_scan_max_bytes=4096):
            path = self._rollout(Path(tmp), entries)
            config, state = runtime()
            self.assertGreater(path.stat().st_size, config.turn_scan_max_bytes)
            scan = runtime_turns.scan_turns(config, state, str(path), "codex")

        assert scan is not None
        self.assertEqual("gpt-5.6-sol", scan["model"])

    def test_a_prefix_rescan_that_reads_no_declaration_leaves_the_model_standing(
        self,
    ) -> None:
        """The clobber this arrangement is here to prevent.

        `scan_turns` merges the backward pass's result with `st.update()`. That
        pass stops at the first turn boundary it meets, so it often has nothing
        to report about the model — and if it reported that as `None`, the merge
        would erase a model an earlier pass had already read. It must omit the
        key instead, so silence stays silence.
        """
        base = time.time() - 200_000
        head: list[dict[str, Any]] = [
            {"type": "session_meta", "payload": {"id": "grow", "cwd": "/tmp/project"}},
            _task_started(base),
            _turn_context(base, "gpt-5.6-sol"),
            _padding(base + 1, filler=20),
        ]
        with tempfile.TemporaryDirectory() as tmp, config_patch(turn_scan_max_bytes=4096):
            path = self._rollout(Path(tmp), head)
            config, state = runtime()
            first = runtime_turns.scan_turns(config, state, str(path), "codex")
            assert first is not None
            self.assertEqual("gpt-5.6-sol", first["model"])

            # The session goes quiet, then resumes: a long stretch of output
            # with a gap in the middle and no further declaration. The backward
            # pass returns at that gap, having read no model at all.
            with path.open("a") as handle:
                for i in range(30):
                    when = base + 10 + i if i < 15 else base + 100_010 + i
                    handle.write(json.dumps(_padding(when)) + "\n")
            self.assertGreater(
                path.stat().st_size - first["pos"],
                config.turn_scan_max_bytes,
            )
            second = runtime_turns.scan_turns(config, state, str(path), "codex")

        assert second is not None
        # The re-anchored turn start is the proof the backward pass ran and
        # returned at the gap rather than walking back to the declaration.
        self.assertGreater(second["last_start"], base + 50_000)
        self.assertEqual("gpt-5.6-sol", second["model"])


class CodexInstructionRowTest(RuntimeTestCase):
    """What a Codex session row actually publishes, end to end.

    The reported bug is a row that says `running 2 subagents` and nothing about
    the work, so the assertions here are on the collected row rather than on the
    reader that feeds it.
    """

    SID = "44444444-4444-4444-4444-444444444444"

    def _collect(self, entries: list[dict[str, Any]], now: float) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026" / "08" / "27" / "rollout-row.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(json.dumps(e) + "\n" for e in entries),
                encoding="utf-8",
            )
            os.utime(path, (now, now))
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                collected = codex_collector.collect(config, state, now, 24, False)
        (session,) = collected
        return session

    def test_a_running_session_names_what_it_was_asked_to_do(self) -> None:
        now = time.time()
        entries: list[dict[str, Any]] = [
            {"type": "session_meta", "payload": {"id": self.SID, "cwd": "/tmp/project"}},
            _task_started(now - 120),
            {
                "timestamp": _stamp(now - 119),
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "Reconcile the harness registry with the shipped docs",
                },
            },
        ]
        entries += [_padding(now - 60) for _ in range(500)]

        session = self._collect(entries, now)

        self.assertEqual("Reconcile the harness registry with the shipped docs", session["title"])
        self.assertEqual(
            "Reconcile the harness registry with the shipped docs", session["last_prompt"]
        )
        # Line 1 says the work, so there is nothing for line 2 to add.
        self.assertIsNone(session["instruction"])

    def test_a_continuation_puts_the_agents_own_intent_on_the_second_line(self) -> None:
        now = time.time()
        entries: list[dict[str, Any]] = [
            {"type": "session_meta", "payload": {"id": self.SID, "cwd": "/tmp/project"}},
            _task_started(now - 120),
            {
                "timestamp": _stamp(now - 119),
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "proceed"},
            },
            {
                "timestamp": _stamp(now - 100),
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "AgentMessage",
                        "phase": "commentary",
                        "content": [
                            {
                                "type": "Text",
                                "text": "I'll compare the repository guidance files first",
                            }
                        ],
                    },
                },
            },
        ]
        entries += [_padding(now - 60) for _ in range(500)]

        session = self._collect(entries, now)

        self.assertEqual("proceed", session["title"])
        self.assertEqual(
            {
                "label": "agent",
                "text": "I'll compare the repository guidance files first",
                "at": records.parse_ts(_stamp(now - 100)),
            },
            session["instruction"],
        )

    def test_a_session_with_no_genuine_prompt_publishes_neither_line(self) -> None:
        # The `||` chain on the page then falls through to the project name,
        # which is today's behaviour and the honest one. 143 local rollouts have
        # `<recommended_plugins>` as their only user record.
        now = time.time()
        session = self._collect(
            [
                {"type": "session_meta", "payload": {"id": self.SID, "cwd": "/tmp/project"}},
                _task_started(now - 120),
                {
                    "timestamp": _stamp(now - 119),
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "<recommended_plugins>\nHere is a list of plugins",
                    },
                },
            ],
            now,
        )

        self.assertIsNone(session["title"])
        self.assertEqual("", session["last_prompt"])
        self.assertIsNone(session["instruction"])
        self.assertEqual("tmp/project", session["project"])

    def test_untrusted_prompt_text_is_bounded_and_scrubbed_on_the_row(self) -> None:
        # `last_prompt` used to be a raw `[:140]` slice with no `safe_text` at
        # all. It is untrusted transcript text bound for the DOM, so it is
        # bounded here and escaped again at the render site.
        now = time.time()
        hostile = "Reconcile\u202e the\x07 registry " + "z" * 400
        session = self._collect(
            [
                {"type": "session_meta", "payload": {"id": self.SID, "cwd": "/tmp/project"}},
                _task_started(now - 120),
                {
                    "timestamp": _stamp(now - 119),
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": hostile},
                },
            ],
            now,
        )

        self.assertEqual(records.LAST_PROMPT_CAP_CHARS, len(session["last_prompt"]))
        self.assertNotIn("\u202e", session["last_prompt"])
        self.assertNotIn("\x07", session["last_prompt"])
        assert session["title"] is not None
        # `transcripts.clip` appends the ellipsis after cutting to the cap.
        self.assertLessEqual(len(session["title"]), records.PROMPT_TITLE_CAP_CHARS + 1)
        self.assertNotIn("\u202e", session["title"])


def _function_call_plan(when: float, steps: list[tuple[str, str]]) -> dict[str, Any]:
    """The pre-`exec` shape: a `function_call` whose arguments are JSON text."""
    return {
        "timestamp": _stamp(when),
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "update_plan",
            "call_id": "call_plan",
            "arguments": json.dumps(
                {"plan": [{"step": step, "status": status} for step, status in steps]}
            ),
        },
    }


def _exec_plan(when: float, script: str) -> dict[str, Any]:
    """The current shape: a `custom_tool_call` carrying JavaScript source."""
    return {
        "timestamp": _stamp(when),
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "name": "exec",
            "call_id": "call_exec",
            "input": script,
        },
    }


class CodexPlanReaderTest(RuntimeTestCase):
    """`update_plan` is the only place Codex records what it is working through.

    Both wire shapes are exercised, and both are live rather than historical: a
    build writes one or the other, so a reader that knows only one reports an
    empty plan on whichever build the operator happens to be running.
    """

    def _plan(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout-plan.jsonl"
            path.write_text(
                "".join(json.dumps(e) + "\n" for e in entries),
                encoding="utf-8",
            )
            config, state = make_runtime()
            return runtime_transcripts.codex_plan(config, state, str(path))

    def test_the_json_argument_shape_becomes_a_task_list(self) -> None:
        tasks = self._plan(
            [
                _function_call_plan(
                    1_700_000_000.0,
                    [("Trace the contract", "completed"), ("Write the tests", "in_progress")],
                )
            ]
        )

        self.assertEqual(
            [("Trace the contract", "completed"), ("Write the tests", "in_progress")],
            [(t["subject"], t["status"]) for t in tasks],
        )

    def test_the_exec_shape_is_read_out_of_javascript_source(self) -> None:
        """Bare keys and single quotes are how the model writes the call.

        Strict JSON parsing rejects every one of the 211 local `exec` records,
        so this is the difference between a plan and an empty panel.
        """
        tasks = self._plan(
            [
                _exec_plan(
                    1_700_000_000.0,
                    "const p = await tools.update_plan({plan:[\n"
                    "  {step:\"Fetch the issue\", status:'completed'},\n"
                    '  {step:"Land the fix", status:"in_progress"},\n'
                    "]});\ntext(JSON.stringify(p));\n",
                )
            ]
        )

        self.assertEqual(
            [("Fetch the issue", "completed"), ("Land the fix", "in_progress")],
            [(t["subject"], t["status"]) for t in tasks],
        )

    def test_a_plan_bound_to_a_variable_before_the_call_is_still_found(self) -> None:
        """The idiom that anchoring on `update_plan(` misses.

        6 of the 211 local `exec` records write it, and an anchored reader finds
        `{plan}` \u2014 an object with no array in it \u2014 and publishes nothing.
        """
        tasks = self._plan(
            [
                _exec_plan(
                    1_700_000_000.0,
                    "const plan = [\n"
                    '  {step: "Capture the baseline", status: "completed"},\n'
                    '  {step: "Implement the pins", status: "pending"},\n'
                    "];\nawait tools.update_plan({plan});\n",
                )
            ]
        )

        self.assertEqual(
            [("Capture the baseline", "completed"), ("Implement the pins", "pending")],
            [(t["subject"], t["status"]) for t in tasks],
        )

    def test_step_text_holding_a_colon_or_an_apostrophe_survives_the_rewrite(self) -> None:
        """The reason the JS rewrite is a string-aware scan and not a regex.

        `Recce Task 7: full verification` is the literal wording this was built
        against, and a rewrite that quotes every `word:` it sees corrupts it.
        """
        tasks = self._plan(
            [
                _exec_plan(
                    1_700_000_000.0,
                    "await tools.update_plan({plan:[\n"
                    '  {step:"Recce Task 7: full Recce verification", status:"in_progress"},\n'
                    "  {step:'the reviewer\\'s second pass', status:\"pending\"},\n"
                    "]});\n",
                )
            ]
        )

        self.assertEqual(
            [
                ("Recce Task 7: full Recce verification", "in_progress"),
                ("the reviewer's second pass", "pending"),
            ],
            [(t["subject"], t["status"]) for t in tasks],
        )

    def test_the_newest_plan_wins_and_the_walk_stops_there(self) -> None:
        tasks = self._plan(
            [
                _function_call_plan(1_700_000_000.0, [("Old and superseded", "pending")]),
                _function_call_plan(1_700_000_100.0, [("What it is doing now", "in_progress")]),
            ]
        )

        self.assertEqual(["What it is doing now"], [t["subject"] for t in tasks])

    def test_the_plan_is_found_behind_a_tail_flooded_with_reasoning_blobs(self) -> None:
        """Why the walk is backward from EOF rather than a bounded tail read.

        A session that has done any work since writing its plan has pushed it
        out of tail range, and those are exactly the sessions worth reading.
        """
        now = 1_700_000_000.0
        entries: list[dict[str, Any]] = [
            _function_call_plan(now, [("Behind the flood", "in_progress")])
        ]
        entries += [_padding(now + 1) for _ in range(500)]

        self.assertEqual(["Behind the flood"], [t["subject"] for t in self._plan(entries)])

    def test_a_plan_older_than_a_compaction_is_still_published(self) -> None:
        """A compaction disowns an older prompt; it does not retire the plan.

        The CLI keeps rendering the plan across one, so stopping at the boundary
        would blank the panel for the long sessions this exists to make legible.
        """
        now = 1_700_000_000.0
        tasks = self._plan(
            [
                _function_call_plan(now, [("Written before the compaction", "in_progress")]),
                {
                    "timestamp": _stamp(now + 1),
                    "type": "event_msg",
                    "payload": {"type": "compacted"},
                },
            ]
        )

        self.assertEqual(["Written before the compaction"], [t["subject"] for t in tasks])

    def test_a_malformed_record_reports_no_plan_rather_than_raising(self) -> None:
        now = 1_700_000_000.0
        for payload in (
            {"type": "function_call", "name": "update_plan", "arguments": "{not json"},
            {"type": "function_call", "name": "update_plan", "arguments": {"plan": "not a list"}},
            {"type": "custom_tool_call", "name": "exec", "input": "tools.update_plan({plan:[{"},
            {"type": "custom_tool_call", "name": "exec", "input": "update_plan([1, 2, 3])"},
        ):
            with self.subTest(payload=payload["type"]):
                entries = [{"timestamp": _stamp(now), "type": "response_item", "payload": payload}]
                self.assertEqual([], self._plan(entries))

    def test_untrusted_step_text_is_bounded_and_scrubbed(self) -> None:
        hostile = "\u202e" + "z" * 400 + "\x07"
        tasks = self._plan([_function_call_plan(1_700_000_000.0, [(hostile, "pending")])])

        (task,) = tasks
        self.assertLessEqual(
            len(task["subject"]), runtime_transcripts.CODEX_PLAN_STEP_CAP_CHARS + 1
        )
        self.assertNotIn("\u202e", task["subject"])
        self.assertNotIn("\x07", task["subject"])

    def test_the_step_count_is_bounded(self) -> None:
        over = runtime_transcripts.CODEX_PLAN_MAX_STEPS + 20
        tasks = self._plan(
            [_function_call_plan(1_700_000_000.0, [(f"step {i}", "pending") for i in range(over)])]
        )

        self.assertEqual(runtime_transcripts.CODEX_PLAN_MAX_STEPS, len(tasks))

    def test_an_unknown_status_falls_back_to_pending(self) -> None:
        """Codex owns this vocabulary, so a value outside it is unread.

        Pending is the safe direction: it counts as neither done nor in flight,
        so an added status cannot inflate a progress bar or claim the row.
        """
        tasks = self._plan([_function_call_plan(1_700_000_000.0, [("Something", "deferred")])])

        self.assertEqual("pending", tasks[0]["status"])


class CodexPlanRowTest(RuntimeTestCase):
    """The plan on the published row: the panel the dashboard was hiding."""

    SID = "55555555-5555-5555-5555-555555555555"

    def _collect(self, entries: list[dict[str, Any]], now: float) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026" / "08" / "28" / "rollout-plan-row.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(json.dumps(e) + "\n" for e in entries),
                encoding="utf-8",
            )
            os.utime(path, (now, now))
            with store_patch(CODEX_SESSIONS_DIR=tmp):
                config, state = runtime()
                collected = codex_collector.collect(config, state, now, 24, False)
        (session,) = collected
        return session

    def _entries(self, now: float, steps: list[tuple[str, str]]) -> list[dict[str, Any]]:
        return [
            {"type": "session_meta", "payload": {"id": self.SID, "cwd": "/tmp/project"}},
            _task_started(now - 120),
            {
                "timestamp": _stamp(now - 119),
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Work the plan"},
            },
            _function_call_plan(now - 60, steps),
        ]

    def test_the_row_publishes_the_plan_and_its_arithmetic(self) -> None:
        now = time.time()
        session = self._collect(
            self._entries(
                now,
                [
                    ("Task 1", "completed"),
                    ("Task 2", "completed"),
                    ("Task 3", "in_progress"),
                    ("Task 4", "pending"),
                ],
            ),
            now,
        )

        self.assertEqual(
            ["Task 1", "Task 2", "Task 3", "Task 4"], [t["subject"] for t in session["tasks"]]
        )
        self.assertEqual(4, session["total"])
        self.assertEqual(2, session["done"])
        self.assertEqual(2, session["open"])
        self.assertEqual(50, session["progress_pct"])

    def test_the_in_progress_step_says_what_is_happening(self) -> None:
        """The reported complaint, on the field the card actually prints.

        `running 1 subagent` is true of every fan-out and names no work; the
        step is the only published field that says which piece is in flight.
        """
        now = time.time()
        session = self._collect(
            self._entries(
                now, [("Done already", "completed"), ("Wiring the collector", "in_progress")]
            ),
            now,
        )

        self.assertEqual("working", session["state"])
        self.assertEqual("Wiring the collector\u2026", session["state_detail"])

    def test_a_session_with_no_plan_keeps_the_generic_line(self) -> None:
        now = time.time()
        entries = [
            {"type": "session_meta", "payload": {"id": self.SID, "cwd": "/tmp/project"}},
            _task_started(now - 120),
            {
                "timestamp": _stamp(now - 119),
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Work with no plan"},
            },
        ]

        session = self._collect(entries, now)

        self.assertEqual([], session["tasks"])
        self.assertEqual(0, session["total"])
        self.assertEqual("generating\u2026", session["state_detail"])

    def test_an_eta_is_left_unset_rather_than_estimated(self) -> None:
        """A Codex plan step carries no timestamps, so there is nothing to average."""
        now = time.time()
        session = self._collect(
            self._entries(now, [("Task 1", "completed"), ("Task 2", "pending")]), now
        )

        self.assertIsNone(session["eta_h"])
