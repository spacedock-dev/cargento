from __future__ import annotations

import json
import os
import re
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

    # One turn's worth of a tight failure loop: a prompt, then `count` tool
    # calls each answered by a failing result. The shape is the measured one —
    # `is_error` rides the `tool_result` block, and the tool name is only ever on
    # the `tool_use` block whose id the result points back to.
    @staticmethod
    def _loop_transcript(count: int, *, tool: str = "Bash", minute: int = 0) -> list[Any]:
        out: list[Any] = [
            {
                "type": "user",
                "timestamp": f"2026-01-01T00:{minute:02d}:00Z",
                "message": {"content": "fix the thing"},
            }
        ]
        for i in range(count):
            out.append(
                {
                    "type": "assistant",
                    "timestamp": f"2026-01-01T00:{minute:02d}:{i * 2 + 1:02d}Z",
                    "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": tool}]},
                }
            )
            out.append(
                {
                    "type": "user",
                    "timestamp": f"2026-01-01T00:{minute:02d}:{i * 2 + 2:02d}Z",
                    "message": {
                        "content": [
                            {"type": "tool_result", "tool_use_id": f"t{i}", "is_error": True}
                        ]
                    },
                }
            )
        return out

    @staticmethod
    def _scan(written: list[Any], path: Path, **overrides: Any) -> dict[str, Any]:
        path.write_text("\n".join(json.dumps(record) for record in written) + "\n")
        config, state = make_runtime(**overrides)
        scan = runtime_turns.scan_turns(config, state, str(path), "claude")
        assert scan is not None
        return scan

    def test_a_run_of_failing_tool_results_is_counted_and_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scan = self._scan(self._loop_transcript(4), Path(tmp) / "loop.jsonl")
        self.assertEqual(4, scan["err_peak"])
        self.assertEqual("Bash", scan["err_tool"])

    def test_a_successful_call_breaks_the_run_but_not_the_peak(self) -> None:
        # Two facts in one test because they are one decision: "consecutive"
        # means the live run resets on any success, and what the turn publishes
        # is the peak, which does not — a loop that has just stopped failing is
        # exactly when the reader walks back to the machine.
        written = self._loop_transcript(4)
        written.append(
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:20Z",
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": "t3", "is_error": False}]
                },
            }
        )
        written.extend(self._loop_transcript(1)[1:])
        with tempfile.TemporaryDirectory() as tmp:
            scan = self._scan(written, Path(tmp) / "loop.jsonl")
        self.assertEqual(1, scan["err_run"])
        self.assertEqual(4, scan["err_peak"])

    def test_the_next_prompt_clears_the_loop_signal(self) -> None:
        written = self._loop_transcript(4) + self._loop_transcript(1, minute=1)
        with tempfile.TemporaryDirectory() as tmp:
            scan = self._scan(written, Path(tmp) / "loop.jsonl")
        self.assertEqual(1, scan["err_peak"])

    def test_the_loop_threshold_is_what_decides_the_signal(self) -> None:
        # The threshold IS the product: at 3 and at 4 the detector fired in the
        # same 1 of 25 local transcripts, so the extra rung costs no yield and
        # buys distance from the benign runs the sample was full of. A run one
        # short of it publishes nothing at all, not a smaller signal.
        config, _ = make_runtime()
        with tempfile.TemporaryDirectory() as tmp:
            short = self._scan(self._loop_transcript(3), Path(tmp) / "short.jsonl")
            long_enough = self._scan(self._loop_transcript(4), Path(tmp) / "long.jsonl")
        self.assertEqual(4, config.loop_error_run_threshold)
        self.assertIsNone(runtime_turns.loop_signal(short, config))
        self.assertEqual(
            {"errors": 4, "tool": "Bash"}, runtime_turns.loop_signal(long_enough, config)
        )
        self.assertIsNone(runtime_turns.loop_signal(None, config))

    def test_only_claude_records_report_a_failed_tool_call(self) -> None:
        # Every other harness gets nothing, and the assertion is the absence:
        # Codex's tool-output records carry no error field, Copilot's analyzer
        # reads no tool-end record, and Droid's block shape matches Claude's but
        # no failing Droid call has been captured. An unmeasured semantic must
        # not arrive as a measurement — so the same transcript scanned as
        # another harness counts nothing.
        for harness in ("droid", "codex", "copilot", "gemini"):
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "loop.jsonl"
                path.write_text("\n".join(json.dumps(r) for r in self._loop_transcript(6)) + "\n")
                config, state = make_runtime()
                scan = runtime_turns.scan_turns(config, state, str(path), harness)
                assert scan is not None
                self.assertEqual(0, scan["err_peak"])
                self.assertIsNone(runtime_turns.loop_signal(scan, config))

    def test_a_run_split_by_a_quiet_stretch_is_not_a_loop(self) -> None:
        # A permission prompt or an open question parks a turn for minutes at a
        # time, and the scanner already re-anchors the clock there. Failures on
        # either side of that gap are not a tight loop, so the run goes with it.
        written = self._loop_transcript(2)
        later = self._loop_transcript(2, minute=30)[1:]  # same turn, after the gap
        with tempfile.TemporaryDirectory() as tmp:
            scan = self._scan(written + later, Path(tmp) / "gap.jsonl")
        self.assertEqual(2, scan["err_peak"])

    def test_the_run_survives_an_incremental_scan_without_double_counting(self) -> None:
        # The scanner carries state between /api/data requests, so a counter is
        # exactly the shape that double-advances when the second call re-reads a
        # record the first already applied.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "growing.jsonl"
            written = self._loop_transcript(4)
            path.write_text("\n".join(json.dumps(r) for r in written) + "\n")
            config, state = make_runtime()
            first = runtime_turns.scan_turns(config, state, str(path), "claude")
            assert first is not None
            after_first = first["err_peak"]
            with path.open("a") as output:
                for record in self._loop_transcript(1, minute=1)[1:]:
                    output.write(json.dumps(record) + "\n")
            second = runtime_turns.scan_turns(config, state, str(path), "claude")
        assert second is not None
        self.assertEqual(4, after_first)
        self.assertEqual(5, second["err_peak"])

    def test_a_scan_result_is_a_snapshot_not_the_live_accumulator(self) -> None:
        # The accumulator lives in `state.turn_scan` for the life of the file, so
        # handing it back by reference makes every result an alias of the next
        # one. A top-level copy is not enough either: `durations` is appended to
        # in place, and the tail trim at the end of a scan rebinds it, so a
        # shallow copy points at the list the NEXT call appends to.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aliased.jsonl"
            written = self._loop_transcript(2) + self._loop_transcript(2, minute=1)
            path.write_text("\n".join(json.dumps(record) for record in written) + "\n")
            config, state = make_runtime()
            first = runtime_turns.scan_turns(config, state, str(path), "claude")
            assert first is not None
            durations, peak = list(first["durations"]), first["err_peak"]
            with path.open("a") as output:
                for record in self._loop_transcript(3, minute=2):
                    output.write(json.dumps(record) + "\n")
            second = runtime_turns.scan_turns(config, state, str(path), "claude")
            assert second is not None
            self.assertIsNot(first, second)
            self.assertIsNot(state.turn_scan[str(path)], second)
        # The two calls disagree, which is what makes the assertions above bite.
        self.assertNotEqual(durations, second["durations"])
        self.assertNotEqual(peak, second["err_peak"])
        self.assertEqual(durations, first["durations"])
        self.assertEqual(peak, first["err_peak"])

    def test_a_failure_is_attributed_to_the_tool_that_failed(self) -> None:
        # The name is only on the `tool_use` block, so the id is the whole join.
        # Two calls issued in one batch and answered out of order is where a
        # "most recent name wins" shortcut names the wrong tool.
        written: list[Any] = [
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:00Z",
                "message": {"content": "fix the thing"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:01Z",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "a", "name": "Bash"},
                        {"type": "tool_use", "id": "b", "name": "Edit"},
                    ]
                },
            },
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:02Z",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "b", "is_error": True},
                        {"type": "tool_result", "tool_use_id": "a", "is_error": True},
                    ]
                },
            },
        ]
        written.extend(self._loop_transcript(2, tool="Read")[1:])
        with tempfile.TemporaryDirectory() as tmp:
            scan = self._scan(written, Path(tmp) / "batch.jsonl")
        self.assertEqual(4, scan["err_peak"])
        self.assertEqual("Read", scan["err_tool"])

    def test_base_session_exposes_full_sid_and_truncated_display_id(self) -> None:
        s = runtime_sessions.base_session("gemini", "session-abcdef123", "proj")
        self.assertEqual("session-", s["session"])  # display stays 8 chars
        self.assertEqual("session-abcdef123", s["sid"])  # identity stays full

    # The payload's declared field set, written out here rather than derived from
    # base_session(), so the two sides cannot move together. Comparing a function
    # against the table it reads from holds no matter how wrong the table is.
    DECLARED_SESSION_FIELDS = frozenset(
        {
            "session",
            "sid",
            "harness",
            "project",
            "provider",
            "model",
            "consumption",
            "title",
            "last_prompt",
            "instruction",
            "state",
            "state_detail",
            "active",
            "last_activity",
            "own_activity",
            "started_at",
            "finished_at",
            "dirty",
            "changed",
            "rate_per_min",
            "session_output_tokens",
            "turn_output_tokens",
            "total",
            "done",
            "open",
            "progress_pct",
            "eta_h",
            "turn",
            "loop",
            "subagents",
            "tasks",
            "spacedock",
        }
    )

    def test_every_session_row_declares_the_same_field_set(self) -> None:
        # Why the set is fixed at all: a key that appears for only some harnesses
        # makes every consumer test for presence rather than for a value. So a
        # field arriving for one harness is declared for all of them, and this
        # test is the place that has to be edited to say so.
        for harness in ("claude", "copilot", "goose", "pi"):
            with self.subTest(harness=harness):
                row = runtime_sessions.base_session(harness, f"{harness}-1", "proj")
                self.assertEqual(self.DECLARED_SESSION_FIELDS, set(row))

    def test_no_collector_may_fill_the_completion_stamp(self) -> None:
        # Only the event path can observe a turn ending. A collector inferring it
        # from a last-record kind would render identically to a measurement, and
        # six of the ten harnesses have nothing to infer it from at all — so the
        # declared None has to survive every collector in the registry.
        self.assertIsNone(runtime_sessions.base_session("claude", "abc", "proj")["finished_at"])
        source = Path(runtime_sessions.__file__).parent
        writers = [
            path.name
            for path in sorted((source / "collectors").glob("*.py"))
            if '"finished_at"' in path.read_text(encoding="utf-8")
        ]
        self.assertEqual([], writers, "a collector is guessing at completion")

    def test_an_unmeasured_session_start_is_declared_as_none(self) -> None:
        self.assertIsNone(runtime_sessions.base_session("pi", "abc", "proj")["started_at"])

    def test_consumption_ships_unfilled_for_a_harness_that_keeps_no_ledger(self) -> None:
        # Copilot's collector fills this; every other harness leaves the declared
        # None, which reads as "no accounting", never as "spent nothing".
        self.assertIsNone(runtime_sessions.base_session("goose", "abc", "proj")["consumption"])

    def test_model_ships_unfilled_and_bounded_by_a_cap_of_its_own(self) -> None:
        # None is the declared value, and it means "not read" rather than "no
        # model" — five harnesses in ten publish it after this batch, so it is the
        # commonest reading and not an edge. The page draws it as an explicit dash
        # for that reason; a blank slot is indistinguishable from a measurement.
        row = runtime_sessions.base_session("goose", "abc", "proj")
        self.assertIsNone(row["model"])
        self.assertIsNone(row["provider"])
        self.assertEqual([], row["subagents"])

        # The cap is this module's own symbol even though `quota` already has a
        # 40. `quota` imports this module, so importing back is a cycle — but the
        # reason they are separate is that they answer different questions: quota's
        # cap feeds a distinctness digest so two long model names sharing a prefix
        # stay two usage rows, and a session row, holding one model and nothing to
        # tell it apart from, only truncates. Either may move without the other,
        # which is what this asserts: agreement is not required, independence is.
        self.assertEqual(40, runtime_sessions.MODEL_CAP_CHARS)
        source = Path(runtime_sessions.__file__ or "").read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"^\s*(?:from|import)\b.*\bquota\b", source, re.MULTILINE),
            "sessions.py imported quota — quota.py imports sessions, so that is a cycle",
        )

    def test_a_subagent_element_always_carries_measurement_keys(self) -> None:
        # The published element declares model and started_at even when neither
        # was measured. A parallel map of only measured values would be smaller,
        # but absence from it would mean either "same as the parent" / "started
        # with the parent" or "nobody measured it", which collapses the facts.
        # A parallel list of only the children whose model differs is refused for
        # the same reason: absence from such a list means
        # either "same as the parent" or "nobody read one", which collapses in the
        # wire format the two facts this field exists to keep apart. There is also
        # no sound join key to build one on — several collectors fall back to a
        # bare "subagent" label, so two unnamed children collide and a model gets
        # attributed to a sibling.
        #
        # Nothing here builds an element; the collectors do, each in its own test.
        # What this pins is that the one shared consumer survives either shape:
        # `working_detail` counts elements without reading inside them, which is
        # why the collectors can be converted one at a time.
        self.assertEqual([], runtime_sessions.base_session("claude", "abc", "proj")["subagents"])
        self.assertEqual(
            "running 2 subagents",
            runtime_sessions.working_detail(None, [{"name": "a", "model": None}, "b"]),
        )
        self.assertEqual(
            "running 1 subagent", runtime_sessions.working_detail(None, [{"name": "a"}])
        )
        self.assertEqual("generating…", runtime_sessions.working_detail(None, []))

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
