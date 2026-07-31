from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import records
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime import turns as runtime_turns
from cargento_runtime.collectors import claude as claude_collector

from .support import (
    STORE_OVERRIDES,
    RuntimeTestCase,
    collect,
    collect_claude,
    make_config,
    make_runtime,
    store_patch,
)


class CargentoServerTest(RuntimeTestCase):
    def test_large_transcript_recovers_turn_start_before_bounded_tail(self) -> None:
        prompt_time = "2026-01-01T00:00:00Z"
        prompt = {
            "type": "user",
            "timestamp": prompt_time,
            "message": {"content": "long request"},
        }
        events = [
            {
                "type": "assistant",
                "timestamp": f"2026-01-01T00:00:{second:02d}Z",
                "message": {"content": "x" * 40},
            }
            for second in range(1, 20)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.jsonl"
            path.write_text("\n".join(json.dumps(record) for record in [prompt, *events]) + "\n")
            config, state = make_runtime(turn_scan_max_bytes=200)
            turns = runtime_turns.scan_turns(config, state, str(path), "claude")

        assert turns is not None
        self.assertEqual(records.parse_ts(prompt_time), turns["turn_start"])

    def test_large_append_recovers_new_turn_start_from_skipped_delta(self) -> None:
        first_time = "2026-01-01T00:00:00Z"
        second_time = "2026-01-01T00:01:00Z"
        first_prompt = {
            "type": "user",
            "timestamp": first_time,
            "message": {"content": "first"},
        }
        second_prompt = {
            "type": "user",
            "timestamp": second_time,
            "message": {"content": "second"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "growing.jsonl"
            path.write_text(json.dumps(first_prompt) + "\n")
            # Both scan calls share one runtime: the scanner is incremental, so
            # the second must see the state the first recorded.
            config, state = make_runtime(turn_scan_max_bytes=200)
            runtime_turns.scan_turns(config, state, str(path), "claude")
            with path.open("a") as output:
                output.write(json.dumps(second_prompt) + "\n")
                for second in range(1, 20):
                    output.write(
                        json.dumps(
                            {
                                "type": "assistant",
                                "timestamp": (f"2026-01-01T00:01:{second:02d}Z"),
                                "message": {"content": "x" * 40},
                            }
                        )
                        + "\n"
                    )
            turns = runtime_turns.scan_turns(config, state, str(path), "claude")

        assert turns is not None
        self.assertEqual(records.parse_ts(second_time), turns["turn_start"])

    def test_base_session_exposes_full_sid_and_truncated_display_id(self) -> None:
        s = runtime_sessions.base_session("gemini", "session-abcdef123", "proj")
        self.assertEqual("session-", s["session"])  # display stays 8 chars
        self.assertEqual("session-abcdef123", s["sid"])  # identity stays full

    def test_turn_clock_reanchors_after_quiet_gap(self) -> None:
        # Time blocked on a human (permission prompt, AskUserQuestion, sleep)
        # writes nothing to the transcript. A quiet gap longer than
        # TURN_GAP_RESET_SEC inside a turn must re-anchor the elapsed clock at
        # the post-gap event instead of billing the wait as generation time.
        base = 1_784_000_000.0

        def iso(offset: float) -> str:
            return str(datetime.fromtimestamp(base + offset, UTC).isoformat())

        records = [
            {
                "type": "user",
                "timestamp": iso(0),
                "message": {"role": "user", "content": "start the work"},
            },
            {
                "type": "assistant",
                "timestamp": iso(20),
                "message": {"role": "assistant", "content": []},
            },
            {
                "type": "assistant",
                "timestamp": iso(40),
                "message": {"role": "assistant", "content": []},
            },
            # 45-minute wait on the human, then generation resumes.
            {
                "type": "assistant",
                "timestamp": iso(40 + 2700),
                "message": {"role": "assistant", "content": []},
            },
            {
                "type": "assistant",
                "timestamp": iso(70 + 2700),
                "message": {"role": "assistant", "content": []},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            config, state = make_runtime()
            scan = runtime_turns.scan_turns(config, state, str(path), "claude")

        assert scan is not None
        # Clock re-anchored at the post-gap record, not the original prompt.
        self.assertEqual(base + 40 + 2700, scan["turn_start"])
        # The pre-gap active segment is banked as a finished duration.
        self.assertIn(40.0, scan["durations"])

    def test_local_command_output_is_not_a_turn_start(self) -> None:
        rec = {
            "type": "user",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": "<local-command-stdout>ok</local-command-stdout>",
            },
        }
        self.assertIsNone(records._turn_signal(rec, "claude"))
        caveat = {
            "type": "user",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": "<local-command-caveat>x</local-command-caveat>",
            },
        }
        self.assertIsNone(records._turn_signal(caveat, "claude"))

    def test_uuidv7_sessions_started_together_get_distinct_display_ids(self) -> None:
        # DRC-3962. Codex ids are UUIDv7: the first 48 bits are a millisecond
        # timestamp, so a fan-out launched in one directory shares its leading
        # hex. Truncating the display id to 8 chars rendered four distinct
        # sessions as the same harness, project and id — one session, seen
        # four times. Observed live: 019fa752-a888…, -a889…, -a88d…, -a8a7….
        sessions = [
            runtime_sessions.base_session(
                "codex", f"019fa752-a88{tail}-7fe3-a529-ebd8042771c{i}", "p"
            )
            for i, tail in enumerate(("8", "9", "d"))
        ]
        runtime_sessions.assign_display_ids(make_config(), sessions)
        shown = [s["session"] for s in sessions]

        self.assertEqual(len(shown), len(set(shown)))
        # The full id stays intact for keying; only the display id grows.
        self.assertEqual("019fa752-a888-7fe3-a529-ebd8042771c0", sessions[0]["sid"])

    def test_display_ids_widen_only_for_the_harness_that_collides(self) -> None:
        # Expanding every id because one pair collides would churn the whole
        # UI. The other harness's ids must be long enough to *show* whether
        # they were truncated: an 8-char sid is unaffected by any width, so a
        # test using one cannot tell per-harness widening from global.
        sessions = [
            runtime_sessions.base_session("gemini", "aaaa1111-cccc-4444-8888-000000000001", "p"),
            runtime_sessions.base_session("gemini", "bbbb2222-dddd-4444-8888-000000000002", "p"),
            runtime_sessions.base_session("codex", "019fa752-a888-7fe3-a529-ebd8042771c1", "p"),
            runtime_sessions.base_session("codex", "019fa752-a889-73a3-88ba-d362c54a1ae6", "p"),
        ]
        runtime_sessions.assign_display_ids(make_config(), sessions)

        # Gemini's ids already differ at 8 chars, so they stay at the floor
        # even though Codex in the same snapshot had to widen.
        self.assertEqual(["aaaa1111", "bbbb2222"], [s["session"] for s in sessions[:2]])
        codex = [s["session"] for s in sessions[2:]]
        self.assertEqual(len(codex), len(set(codex)))
        self.assertTrue(all(len(c) > 8 for c in codex))

    def test_a_colliding_fan_out_does_not_widen_unrelated_projects(self) -> None:
        # A four-agent fan-out started in the same millisecond needs 16 to 18
        # characters to separate. Grouping by harness alone would hand that
        # width to every other Codex row, including a lone session in an
        # unrelated worktree that was never ambiguous.
        sessions = [
            runtime_sessions.base_session(
                "codex", "019fa752-a888-7fe3-a529-ebd8042771c1", "recce/infra"
            ),
            runtime_sessions.base_session(
                "codex", "019fa752-a889-73a3-88ba-d362c54a1ae6", "recce/infra"
            ),
            runtime_sessions.base_session(
                "codex", "019fa752-a88d-7d23-978a-a8d2d2584c3b", "recce/infra"
            ),
            runtime_sessions.base_session(
                "codex", "019fa752-a8a7-71f1-ac29-fd97c876c5e3", "recce/other"
            ),
        ]
        runtime_sessions.assign_display_ids(make_config(), sessions)

        # The lone row in the other worktree keeps the floor.
        self.assertEqual("019fa752", sessions[3]["session"])
        colliding = [s["session"] for s in sessions[:3]]
        self.assertEqual(len(colliding), len(set(colliding)))

    def test_display_ids_ignore_collisions_across_different_harnesses(self) -> None:
        # Two harnesses can hand out the same id without either row being
        # ambiguous: the harness badge already separates them.
        shared = "019fa752-a888-7fe3-a529-ebd8042771c1"
        sessions = [
            runtime_sessions.base_session("codex", shared, "p"),
            runtime_sessions.base_session("gemini", shared, "p"),
        ]
        runtime_sessions.assign_display_ids(make_config(), sessions)

        self.assertEqual(["019fa752", "019fa752"], [s["session"] for s in sessions])

    def test_collect_widens_colliding_display_ids_end_to_end(self) -> None:
        # The widening is only worth anything if collect() actually applies
        # it: deleting the call leaves every unit test green.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        sids = (
            "019fa752-a888-7fe3-a529-ebd8042771c1",
            "019fa752-a889-73a3-88ba-d362c54a1ae6",
        )
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "codex" / "2026" / "07" / "28"
            rollout.mkdir(parents=True)
            for sid in sids:
                (rollout / f"rollout-2026-07-28T09-36-23-{sid}.jsonl").write_text(
                    json.dumps(
                        {
                            "timestamp": iso,
                            "type": "session_meta",
                            "payload": {"id": sid, "cwd": "/w/proj", "source": "exec"},
                        }
                    )
                    + "\n"
                )
            with (
                store_patch(CODEX_SESSIONS_DIR=str(Path(tmp) / "codex")),
                mock.patch.dict(STORE_OVERRIDES, {"codex.sessions": [str(Path(tmp) / "codex")]}),
            ):
                data = collect(24, False)

        codex = [s for s in data["sessions"] if s["harness"] == "codex"]
        self.assertEqual(2, len(codex))
        shown = [s["session"] for s in codex]
        self.assertEqual(len(shown), len(set(shown)), f"collect() left ambiguous ids: {shown}")

    def test_identical_sids_do_not_widen_display_ids_forever(self) -> None:
        # Two rows with the same sid cannot be told apart by widening, so the
        # widening must not fire at all: it terminates, and it leaves the id
        # short rather than pointlessly expanding both to the full uuid.
        sessions = [
            runtime_sessions.base_session("codex", "019fa752-a888-7fe3-a529-ebd8042771c1", "p"),
            runtime_sessions.base_session("codex", "019fa752-a888-7fe3-a529-ebd8042771c1", "p"),
        ]
        runtime_sessions.assign_display_ids(make_config(), sessions)

        self.assertEqual(["019fa752"] * 2, [s["session"] for s in sessions])


class DurationAndEpochTest(unittest.TestCase):
    """`fmt_duration` and `norm_epoch` render on every card and had no tests at
    all. Mutation-checked: each boundary below fails a real off-by-one that the
    suite previously missed."""

    def test_each_unit_changes_at_its_own_boundary(self) -> None:
        # The second either side of every cutover, because `<` vs `<=` here is
        # the difference between a card reading "60m" and "1h 0m".
        for seconds, expected in (
            (0, "0s"),
            (59, "59s"),
            (60, "1m"),
            (3599, "59m"),
            (3600, "1h 0m"),
            (3661, "1h 1m"),
            (86399, "23h 59m"),
            (86400, "1d 0h"),
            (90061, "1d 1h"),
        ):
            with self.subTest(seconds=seconds):
                self.assertEqual(expected, runtime_sessions.fmt_duration(seconds))

    def test_an_unknown_or_impossible_duration_renders_a_dash(self) -> None:
        # A negative duration means the clock moved, not that work took
        # negative time, so the card must decline to state one.
        for bad in (None, -1, -0.5, -86400):
            with self.subTest(seconds=bad):
                self.assertEqual("–", runtime_sessions.fmt_duration(bad))

    def test_millisecond_timestamps_are_detected_by_magnitude(self) -> None:
        """Harness stores mix seconds and milliseconds. Guessing wrong puts a
        session in 1970 or 55000 AD, and it silently reads as never-active."""
        self.assertEqual(1_700_000_000, records.norm_epoch(1_700_000_000))
        self.assertEqual(1_700_000_000.0, records.norm_epoch(1_700_000_000_000))
        # The cutover itself: 1e12 is seconds, one above it is milliseconds.
        self.assertEqual(1e12, records.norm_epoch(1e12))
        self.assertAlmostEqual(1e9, records.norm_epoch(1e12 + 1), places=0)

    def test_a_task_shorter_than_the_floor_does_not_licence_an_estimate(self) -> None:
        """The skill body promises "no estimate" until a session has a completed
        task that took at least 30s, so a burst of instant tasks cannot imply a
        confident ETA. Mutation-checked: `>=` vs `>` on that floor survived.

        The rule is exercised through `load_tasks` rather than through real
        files because `created` comes from `st_birthtime`, which Linux does not
        have. On that runner it degrades to mtime, every task looks
        zero-length, and a file-based fixture would assert nothing.
        """
        now = 1_700_000_000.0

        def tasks(took: float) -> dict[str, list[dict[str, Any]]]:
            return {
                "abcd1234": [
                    {
                        "id": "1",
                        "subject": "done",
                        "activeForm": "",
                        "status": "completed",
                        "created": now - took,
                        "updated": now,
                    },
                    {
                        "id": "2",
                        "subject": "still open",
                        "activeForm": "",
                        "status": "pending",
                        "created": now - 10,
                        "updated": now,
                    },
                ]
            }

        with tempfile.TemporaryDirectory() as empty:
            observed = {}
            for took in (29, 30, 60):
                with (
                    mock.patch.object(
                        claude_collector, "load_tasks", lambda _config, t=took: tasks(t)
                    ),
                    store_patch(PROJECTS_DIR=empty),
                ):
                    observed[took] = collect_claude(now, 24, True)[0]["eta_h"]

        self.assertIsNone(observed[29], "29s of evidence is not enough for an ETA")
        # One open task times the 30s average.
        self.assertEqual("30s", observed[30])
        self.assertEqual("1m", observed[60])

    def test_a_missing_or_nonsense_timestamp_is_not_activity(self) -> None:
        # 0 is the "no timestamp" sentinel every freshness check treats as
        # ancient. Returning the raw value instead would date a session to 1970
        # and, for a negative, to before it.
        nonsense: list[Any] = [0, -5, "1700000000", None, [], {}]
        for bad in nonsense:
            with self.subTest(value=bad):
                self.assertEqual(0, records.norm_epoch(bad))


class ClockSkewTest(unittest.TestCase):
    # A future timestamp satisfies every `now - ts <= threshold` test, so before
    # age()/is_fresh() a clock-skewed store pinned its session to Working
    # permanently and kept feeding its tokens into the output rate.
    NOW = 1_700_000_000.0
    SKEW = 86_400.0  # a day ahead, e.g. a WSL2 guest clock after host suspend

    def test_an_implausibly_future_timestamp_is_rejected(self) -> None:
        config = make_config()
        self.assertIsNone(runtime_sessions.age(config, self.NOW, self.NOW + self.SKEW))
        self.assertEqual(10.0, runtime_sessions.age(config, self.NOW, self.NOW - 10))

    def test_sampling_noise_is_clamped_rather_than_rejected(self) -> None:
        # stat() and the collection clock are read microseconds apart, and
        # coarse filesystems round upward — a small overshoot is not skew.
        config = make_config()
        jitter = config.future_skew_tolerance_sec / 2
        self.assertEqual(0.0, runtime_sessions.age(config, self.NOW, self.NOW + jitter))
        self.assertTrue(runtime_sessions.is_fresh(config, self.NOW, self.NOW + jitter, 1))

    def test_a_future_timestamp_does_not_read_as_activity(self) -> None:
        # The whole point: negative ages used to pass every threshold test.
        config = make_config()
        self.assertFalse(
            runtime_sessions.is_fresh(
                config, self.NOW, self.NOW + self.SKEW, config.working_threshold_sec
            )
        )

    def test_future_dated_tokens_do_not_inflate_the_output_rate(self) -> None:
        info = {"usage_events": [(self.NOW + self.SKEW, 5000)]}
        self.assertEqual(0, runtime_sessions.rate_from(info, self.NOW, make_config()))

    def test_a_future_dated_turn_start_yields_no_eta(self) -> None:
        scan = {"turn_start": self.NOW + self.SKEW, "durations": [60.0]}
        self.assertIsNone(runtime_turns.turn_progress(scan, "working", self.NOW, make_config()))

    def test_a_future_dated_transcript_does_not_read_as_working(self) -> None:
        session_id = "beefcafe-1111-2222-3333-444455556666"
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project = projects / "-w-skewed"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(json.dumps({"type": "user", "uuid": "u1"}) + "\n")
            future = self.NOW + self.SKEW
            os.utime(transcript, (future, future))
            with (
                store_patch(PROJECTS_DIR=str(projects)),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
            ):
                # A day-ahead mtime previously made `now - mtime` negative, so
                # the session reported "working" for the whole day of skew.
                sessions = collect_claude(self.NOW, 24, True)

        self.assertEqual(1, len(sessions))
        self.assertEqual("idle", sessions[0]["state"])


class ReviewFixTest(unittest.TestCase):
    """Regressions found by the adversarial review passes on PR #7."""

    NOW = 1_700_000_000.0

    def test_the_same_session_in_two_stores_yields_one_row(self) -> None:
        # Scanning every candidate root can find a session left behind by a
        # migration twice; the DB-backed collectors append per store.
        rows = [
            {**runtime_sessions.base_session("opencode", "same", "p"), "last_activity": 10.0},
            {**runtime_sessions.base_session("opencode", "same", "p"), "last_activity": 99.0},
            {**runtime_sessions.base_session("goose", "same", "p"), "last_activity": 5.0},
        ]
        merged = runtime_sessions.dedupe_sessions(rows)
        self.assertEqual(2, len(merged), "duplicate session id was not merged")
        opencode = next(r for r in merged if r["harness"] == "opencode")
        self.assertEqual(99.0, opencode["last_activity"], "kept the staler copy")


class VerificationFixTest(unittest.TestCase):
    """Regressions found by the adversarial pass that tried to refute the fixes."""

    NOW = 1_700_000_000.0

    FUTURE = NOW + 86_400

    def test_newest_plausible_ignores_skew(self) -> None:
        config = make_config()
        self.assertEqual(
            self.NOW,
            runtime_sessions.newest_plausible(config, self.NOW, (self.FUTURE, self.NOW)),
        )
        self.assertEqual(0.0, runtime_sessions.newest_plausible(config, self.NOW, (self.FUTURE,)))
        self.assertEqual(0.0, runtime_sessions.newest_plausible(config, self.NOW, ()))

    def test_a_skewed_duplicate_does_not_win_deduplication(self) -> None:
        # Ranking by raw last_activity let a clock-skewed migrated copy beat the
        # live one — the very problem rejecting future timestamps is for.
        config = make_config()
        good = {**runtime_sessions.base_session("opencode", "same", "p"), "state": "working"}
        good["last_activity"] = runtime_sessions.newest_plausible(config, self.NOW, (self.NOW,))
        skewed = {**runtime_sessions.base_session("opencode", "same", "p"), "state": "idle"}
        skewed["last_activity"] = runtime_sessions.newest_plausible(
            config, self.NOW, (self.FUTURE,)
        )
        for order in ([good, skewed], [skewed, good]):
            with self.subTest(order=[s["state"] for s in order]):
                self.assertEqual("working", runtime_sessions.dedupe_sessions(order)[0]["state"])
