from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cargento_runtime import transcripts as runtime_transcripts
from cargento_runtime.collectors import codex as codex_collector

from .support import (
    RuntimeTestCase,
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
        self.assertEqual(["worker"], sessions[0]["subagents"])

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
