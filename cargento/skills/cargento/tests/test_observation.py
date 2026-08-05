"""The coordinator: what it records, when it collects, and what it refuses."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import cli, events, http_api, lifecycle, observation
from cargento_runtime import io as runtime_io

from . import support

NOW = 1_700_000_000.0
SESSION = "abcdef12-3456-7890-abcd-ef1234567890"
OTHER = "beefcafe-3456-7890-abcd-ef1234567890"
PREFIX = "abcdef12"
OTHER_PREFIX = "beefcafe"


class FakeStreams:
    def __init__(self, count: int = 0) -> None:
        self.count = count


class FakeState:
    def __init__(self, streams: FakeStreams) -> None:
        self.streams = streams


class FakeApplication:
    """Just enough application for the coordinator: a config, streams, a collect."""

    def __init__(
        self, config: Any, *, streams: int = 0, fail: bool = False, reuse: bool = False
    ) -> None:
        self.config = config
        self.state = FakeState(FakeStreams(streams))
        self.collected = 0
        self.fail = fail
        # Stand in for the application's own collection floor: a real
        # `collect_json` inside `collect_memo_sec` returns the revision it already
        # published rather than minting a new one.
        self.reuse = reuse
        self.diagnostic_sink: Any = lambda _message: None

    def collect_json(self, *, show_all: bool) -> tuple[tuple[float, int], bytes]:
        assert show_all is False, "the coordinator only maintains the default variant"
        if self.fail:
            raise OSError("store exploded")
        if not self.reuse:
            self.collected += 1
        return (NOW, self.collected), b"{}"


class ObservationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.now = NOW
        self.config = support.make_config()

    def clock(self) -> float:
        return self.now

    def build(self, *, reuse: bool = False, **changes: Any) -> observation.Observation:
        config = dataclasses.replace(self.config, **changes) if changes else self.config
        self.app = FakeApplication(config, reuse=reuse)
        return observation.Observation(
            self.app,  # type: ignore[arg-type]
            clock=self.clock,
            diagnostic_sink=lambda _message: None,
        )

    def envelope(self, **overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"v": 1, "event": "turn_started", "session_id": SESSION}
        payload.update(overrides)
        return payload


class SubmitTest(ObservationTestCase):
    def test_a_valid_event_is_accepted_and_recorded(self) -> None:
        coordinator = self.build()
        self.assertEqual("accepted", coordinator.submit("claude", self.envelope()))
        overlays = coordinator.overlays_for("claude", PREFIX)
        self.assertEqual([events.OVERLAY_WORKING], [item.kind for item in overlays])

    def test_a_rejected_envelope_returns_its_reason_and_records_nothing(self) -> None:
        coordinator = self.build()
        self.assertEqual(
            events.REJECT_INCOMPATIBLE, coordinator.submit("claude", self.envelope(v=99))
        )
        self.assertEqual([], coordinator.overlays_for("claude", PREFIX))
        self.assertEqual(1, coordinator.counters[f"reject.{events.REJECT_INCOMPATIBLE}"])

    def test_a_rejected_envelope_does_not_mark_anything_dirty(self) -> None:
        # Otherwise a stream of garbage would drive collections, which is the
        # cheapest denial of service against a loopback endpoint there is.
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="nonsense"))
        self.now += 3600
        self.assertEqual((False, ""), coordinator._due())

    def test_arrival_seq_is_minted_per_submission_and_never_repeats(self) -> None:
        coordinator = self.build()
        for _ in range(3):
            coordinator.submit("claude", self.envelope(event="input_requested"))
        # One overlay survives per kind, and it carries the newest sequence.
        overlay = coordinator.overlays_for("claude", PREFIX)[0]
        self.assertEqual(3, overlay.arrival_seq)

    def test_concurrent_submissions_get_distinct_arrival_seqs(self) -> None:
        # The counter is minted under the lock. Two handler threads sharing one
        # sequence would make the reducer's order arbitrary between them.
        coordinator = self.build()
        seen: list[int] = []
        guard = threading.Lock()

        def submit() -> None:
            with coordinator._lock:
                coordinator._arrival_seq += 1
                seq = coordinator._arrival_seq
            with guard:
                seen.append(seq)

        threads = [threading.Thread(target=submit) for _ in range(24)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(24, len(set(seen)))

    def test_a_hint_event_marks_dirty_without_recording_an_overlay(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="store_changed"))
        self.assertEqual([], coordinator.overlays_for("claude", PREFIX))
        self.now += 3600
        self.assertEqual((True, "event"), coordinator._due())


class LedgerTest(ObservationTestCase):
    def test_one_overlay_per_kind_per_session_so_the_ledger_cannot_grow(self) -> None:
        # The reducer is last-writer-wins per kind, so an older overlay of the
        # same kind could never have changed the outcome.
        coordinator = self.build()
        for _ in range(50):
            coordinator.submit("claude", self.envelope(event="turn_started"))
        self.assertEqual(1, len(coordinator.overlays_for("claude", PREFIX)))

    def test_two_kinds_coexist_so_precedence_is_still_the_reducers_to_decide(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator.submit("claude", self.envelope(event="turn_stopped"))
        self.assertEqual(
            {events.OVERLAY_NEEDS_INPUT, events.OVERLAY_IDLE},
            {item.kind for item in coordinator.overlays_for("claude", PREFIX)},
        )

    def test_two_subagents_are_two_facts_rather_than_one_superseding_the_other(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="subagent_started", subagent_id="child-1"))
        coordinator.submit("claude", self.envelope(event="subagent_started", subagent_id="child-2"))
        self.assertEqual(2, len(coordinator.overlays_for("claude", PREFIX)))

    def test_a_reordered_older_delivery_does_not_replace_a_newer_overlay(self) -> None:
        # At-least-once and possibly reordered. Keeping the newer overlay is what
        # makes replaying the ledger idempotent.
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="input_requested"))
        newest = coordinator.overlays_for("claude", PREFIX)[0]
        stale = dataclasses.replace(newest, arrival_seq=newest.arrival_seq - 1, at=NOW - 500)
        with coordinator._lock:
            coordinator._remember(("claude", PREFIX), stale)
        self.assertEqual(newest, coordinator.overlays_for("claude", PREFIX)[0])
        self.assertEqual(1, coordinator.counters["overlay.stale"])

    def test_session_ended_retires_the_ledger_without_removing_a_row(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator.submit("claude", self.envelope(event="session_ended"))
        self.assertEqual([], coordinator.overlays_for("claude", PREFIX))
        self.assertEqual(1, coordinator.counters["retired"])

    def test_a_clear_followed_by_a_prompt_inside_one_window_reads_as_working(self) -> None:
        # Claude fires session_ended on /clear as well as on exit, so this exact
        # order arrives in practice and must not leave the row retired.
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="session_ended"))
        coordinator.submit("claude", self.envelope(event="turn_started"))
        patch = events.reduce_overlays(coordinator.overlays_for("claude", PREFIX), now=self.now)
        self.assertEqual("working", patch["state"])

    def test_at_capacity_a_new_session_is_refused_rather_than_evicting_a_live_one(self) -> None:
        # Evicting the oldest ledger to make room would clear whichever permission
        # alert happened to be oldest, which is the one most likely still waiting.
        coordinator = self.build(event_overlay_max_sessions=1)
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator.submit("claude", self.envelope(event="input_requested", session_id=OTHER))
        self.assertEqual(1, len(coordinator.overlays_for("claude", PREFIX)))
        self.assertEqual([], coordinator.overlays_for("claude", OTHER_PREFIX))
        self.assertEqual(1, coordinator.counters["overlay.refused"])

    def test_an_existing_session_can_still_record_at_capacity(self) -> None:
        # The cap bounds how many sessions are tracked, not how a tracked session
        # is allowed to change state.
        coordinator = self.build(event_overlay_max_sessions=1)
        coordinator.submit("claude", self.envelope(event="turn_started"))
        coordinator.submit("claude", self.envelope(event="input_requested"))
        self.assertEqual(2, len(coordinator.overlays_for("claude", PREFIX)))


class PendingTest(ObservationTestCase):
    def test_an_overlay_for_a_collected_row_leaves_no_pending_entry(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator.note_rows({("claude", PREFIX)})
        self.assertEqual({}, coordinator._pending)
        self.assertEqual(1, len(coordinator.overlays_for("claude", PREFIX)))

    def test_an_overlay_for_an_unknown_row_waits_rather_than_rendering(self) -> None:
        # A first-session permission prompt must survive until the collector sees
        # the session, without letting a forged id invent one.
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator.note_rows(set())
        self.assertIn(("claude", PREFIX), coordinator._pending)
        self.assertEqual(1, len(coordinator.overlays_for("claude", PREFIX)))

    def test_a_waiting_overlay_attaches_when_a_later_collection_produces_its_row(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator.note_rows(set())
        coordinator.note_rows({("claude", PREFIX)})
        self.assertEqual({}, coordinator._pending)
        self.assertEqual(1, len(coordinator.overlays_for("claude", PREFIX)))

    def test_a_waiting_overlay_expires_after_the_ttl_with_a_counter(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator.note_rows(set())
        self.now += self.config.event_pending_ttl_sec + 1
        coordinator.note_rows(set())
        self.assertEqual([], coordinator.overlays_for("claude", PREFIX))
        self.assertEqual(1, coordinator.counters["pending.expired"])

    def test_the_ttl_is_measured_from_first_sight_not_from_the_last_attempt(self) -> None:
        # Otherwise every collection would renew the clock and nothing would ever
        # expire while collections kept happening.
        coordinator = self.build()
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator.note_rows(set())
        for _ in range(4):
            self.now += self.config.event_pending_ttl_sec / 3
            coordinator.note_rows(set())
        self.assertEqual([], coordinator.overlays_for("claude", PREFIX))

    def test_the_pending_map_refuses_beyond_its_cap_and_counts_it(self) -> None:
        coordinator = self.build(event_pending_max=1, event_overlay_max_sessions=8)
        for suffix in "0123456789ab":
            coordinator.submit(
                "claude",
                self.envelope(event="input_requested", session_id=f"1234567{suffix}-abcd-0000"),
            )
        coordinator.note_rows(set())
        self.assertEqual(1, len(coordinator._pending))
        self.assertGreaterEqual(coordinator.counters["pending.refused"], 1)


class DueTest(ObservationTestCase):
    def test_the_floor_gates_a_dirty_harness(self) -> None:
        # The floor is the store-protection guarantee. A burst of events must not
        # be able to drive collections faster than the memo ever allowed.
        coordinator = self.build()
        coordinator._last_collect_at = self.now
        coordinator.submit("claude", self.envelope())
        self.now += self.config.event_coalesce_sec + 0.01
        self.assertEqual((False, ""), coordinator._due())
        self.now += self.config.collect_memo_sec
        self.assertEqual((True, "event"), coordinator._due())

    def test_a_dirty_harness_waits_out_the_coalescing_window(self) -> None:
        coordinator = self.build()
        coordinator._last_collect_at = self.now - 3600
        coordinator.submit("claude", self.envelope())
        self.assertEqual((False, ""), coordinator._due())
        self.now += self.config.event_coalesce_sec
        self.assertEqual((True, "event"), coordinator._due())

    def test_the_window_is_fixed_rather_than_sliding(self) -> None:
        # A sliding window never closes under a sustained burst, and the board
        # would stop updating entirely.
        coordinator = self.build()
        coordinator._last_collect_at = self.now - 3600
        coordinator.submit("claude", self.envelope())
        opened = coordinator._coalesce_until
        for _ in range(20):
            self.now += self.config.event_coalesce_sec / 4
            coordinator.submit("claude", self.envelope(event="store_changed"))
        self.assertEqual(opened, coordinator._coalesce_until)
        self.assertEqual((True, "event"), coordinator._due())

    def test_a_connected_stream_ticks_on_the_producer_interval(self) -> None:
        coordinator = self.build()
        self.app.state.streams.count = 1
        coordinator._last_collect_at = self.now
        self.now += self.config.stream_producer_interval_sec
        self.assertEqual((True, "tick"), coordinator._due())

    def test_a_connected_stream_does_not_tick_before_the_interval_elapses(self) -> None:
        # The gap between the floor and the interval is the part that matters.
        # Past the floor a tick is *permitted*, and only the interval stops it, so
        # a test that checked one instant past the floor could not tell an
        # interval-respecting tick from one that fires as fast as the floor
        # allows. This asserts inside that gap.
        self.assertGreater(
            self.config.stream_producer_interval_sec,
            self.config.collect_memo_sec,
            "the gap this test samples has to exist",
        )
        coordinator = self.build()
        self.app.state.streams.count = 1
        coordinator._last_collect_at = self.now
        self.now += (self.config.collect_memo_sec + self.config.stream_producer_interval_sec) / 2
        self.assertEqual((False, ""), coordinator._due())

    def test_with_no_stream_connected_nothing_ticks(self) -> None:
        # An idle daemon costs nothing. A timer that collected regardless would be
        # the exact regression the phase before this one existed to avoid.
        coordinator = self.build()
        coordinator._last_collect_at = self.now
        self.now += 86_400
        self.assertEqual((False, ""), coordinator._due())

    def test_an_event_outranks_a_tick_so_the_reason_is_reported_honestly(self) -> None:
        coordinator = self.build()
        self.app.state.streams.count = 1
        coordinator._last_collect_at = self.now - 3600
        coordinator.submit("claude", self.envelope())
        self.now += self.config.event_coalesce_sec
        self.assertEqual((True, "event"), coordinator._due())


class UrgencyTest(ObservationTestCase):
    """A permission alert does not wait out a window meant for batching."""

    def test_a_needs_input_event_skips_the_coalescing_window(self) -> None:
        # The exemption this module documented for two phases without
        # implementing it. Measured worth about 117 ms of the wait.
        coordinator = self.build()
        coordinator._last_collect_at = self.now - 3600
        coordinator.submit("claude", self.envelope(event="input_requested"))
        self.assertEqual((True, "event"), coordinator._due())

    def test_an_ordinary_event_still_waits_out_the_window(self) -> None:
        # The other half: without this the exemption is indistinguishable from
        # deleting the window.
        coordinator = self.build()
        coordinator._last_collect_at = self.now - 3600
        coordinator.submit("claude", self.envelope(event="store_changed"))
        self.assertEqual((False, ""), coordinator._due())

    def test_urgency_does_not_lift_the_floor(self) -> None:
        # The floor is the store-protection guarantee, so it may not become a
        # derived side effect of anything.
        coordinator = self.build()
        coordinator._last_collect_at = self.now
        coordinator.submit("claude", self.envelope(event="input_requested"))
        self.assertEqual((False, ""), coordinator._due())
        self.now += self.config.collect_memo_sec
        self.assertEqual((True, "event"), coordinator._due())


class FloorReuseTest(ObservationTestCase):
    """A collection the application's own floor satisfied is not progress.

    The floor is enforced twice, by two clocks: this coordinator's
    `_last_collect_at`, and the application's snapshot age. A fresh coordinator
    has never collected, so its floor is open while the application's is not, and
    `collect_json` then returns the body it serialized before the event existed.

    Measured before this was fixed: an `input_requested` arriving in that gap was
    retired against a read that predated it and never rendered at all, until an
    unrelated event or a five-second stream tick happened along.
    """

    def _reusing(self) -> observation.Observation:
        coordinator = self.build(reuse=True)
        # The application has already published, and its floor now serves this
        # read from those bytes while the coordinator's own floor is still open.
        coordinator._last_revision = (NOW, 0)
        coordinator._last_collect_at = self.now - 3600
        coordinator.submit("claude", self.envelope(event="input_requested"))
        return coordinator

    def _dirty(self, coordinator: observation.Observation) -> bool:
        return any(
            coordinator._dirty.get(key, 0) != coordinator._collected.get(key, 0)
            for key in coordinator._dirty
        )

    def test_a_reused_publication_leaves_the_event_dirty(self) -> None:
        coordinator = self._reusing()
        due, reason = coordinator._due()
        self.assertTrue(due)
        coordinator._collect(reason)
        self.assertTrue(
            self._dirty(coordinator),
            "the event was retired against a read that predates it",
        )
        self.assertEqual(1, coordinator.counters.get("reused.floor"))

    def test_the_retry_is_scheduled_at_the_floor_not_a_producer_interval(self) -> None:
        # `_sleep_for` consults only `_coalesce_until`, so without scheduling the
        # wake the retry lands at stream_producer_interval_sec. Measured 5.2 s
        # before, 2.5 s after.
        coordinator = self._reusing()
        coordinator._collect(coordinator._due()[1])
        self.assertIsNotNone(coordinator._coalesce_until)
        self.assertLessEqual(
            coordinator._sleep_for(),
            self.config.collect_memo_sec,
            "the worker must wake at the floor rather than at the producer interval",
        )

    def test_a_real_publication_still_marks_the_event_collected(self) -> None:
        # The control. If this failed, the fix above would simply have stopped the
        # coordinator ever making progress.
        coordinator = self.build()
        coordinator._last_collect_at = self.now - 3600
        coordinator.submit("claude", self.envelope(event="input_requested"))
        coordinator._collect(coordinator._due()[1])
        self.assertFalse(self._dirty(coordinator))
        self.assertIsNone(coordinator.counters.get("reused.floor"))


class CollectTest(ObservationTestCase):
    def test_a_collection_clears_the_dirty_generation_it_observed(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope())
        coordinator._collect("event")
        self.assertEqual(1, self.app.collected)
        self.now += 3600
        self.assertEqual((False, ""), coordinator._due())

    def test_a_generation_that_moves_during_collection_stays_dirty(self) -> None:
        # A store_changed hint cannot be recovered by replaying overlays over a
        # read that predates it, so the harness has to be read again.
        coordinator = self.build()
        coordinator.submit("claude", self.envelope())
        real = self.app.collect_json

        def racing(*, show_all: bool) -> Any:
            coordinator.submit("claude", self.envelope(event="store_changed"))
            return real(show_all=show_all)

        self.app.collect_json = racing  # type: ignore[method-assign]
        coordinator._collect("event")
        self.now += 3600
        self.assertEqual((True, "event"), coordinator._due())

    def test_a_failed_collection_is_swallowed_and_leaves_the_harness_dirty(self) -> None:
        # The per-harness failure boundary already reports the cause, and a
        # coordinator that died on one bad read would freeze every dashboard.
        coordinator = self.build()
        self.app.fail = True
        coordinator.submit("claude", self.envelope())
        coordinator._collect("event")
        self.now += 3600
        self.assertEqual((True, "event"), coordinator._due())

    def test_a_failed_collection_still_advances_the_floor(self) -> None:
        # Otherwise a permanently broken store would spin the coordinator at full
        # speed retrying it.
        coordinator = self.build()
        self.app.fail = True
        coordinator.submit("claude", self.envelope())
        coordinator._collect("event")
        self.assertEqual(self.now, coordinator._last_collect_at)

    def test_the_coalescing_window_reopens_for_the_next_burst(self) -> None:
        coordinator = self.build()
        coordinator.submit("claude", self.envelope())
        coordinator._collect("event")
        self.assertIsNone(coordinator._coalesce_until)
        coordinator.submit("claude", self.envelope())
        self.assertIsNotNone(coordinator._coalesce_until)


class ProbeTest(ObservationTestCase):
    def test_the_first_tick_reconciles_unconditionally(self) -> None:
        coordinator = self.build()
        self.assertTrue(coordinator._worth_collecting(self.now))

    def test_an_unchanged_store_lets_a_tick_skip(self) -> None:
        coordinator = self.build()
        coordinator._worth_collecting(self.now)
        self.now += 1
        self.assertFalse(coordinator._worth_collecting(self.now))

    def test_a_changed_store_makes_a_tick_collect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            projects.mkdir()
            with support.store_patch(PROJECTS_DIR=str(projects)):
                config = dataclasses.replace(
                    support.make_config(),
                    store_roots={"claude.projects": (str(projects),)},
                )
                self.assertEqual((str(projects),), config.store_roots["claude.projects"])
                app = FakeApplication(config)
                coordinator = observation.Observation(
                    app,  # type: ignore[arg-type]
                    clock=self.clock,
                    diagnostic_sink=lambda _message: None,
                )
                coordinator._worth_collecting(self.now)
                self.now += 1
                self.assertFalse(coordinator._worth_collecting(self.now))
                (projects / "-w-proj").mkdir()
                self.now += 1
                self.assertTrue(coordinator._worth_collecting(self.now))

    def test_the_reconcile_interval_forces_a_collection_the_probe_would_skip(self) -> None:
        # The probe's documented false negative is a session older than the
        # activity window becoming active again. Nothing else covers it, so this
        # interval is what bounds it instead of leaving it forever.
        coordinator = self.build()
        coordinator._worth_collecting(self.now)
        self.now += self.config.reconcile_interval_sec / 2
        self.assertFalse(coordinator._worth_collecting(self.now))
        self.now += self.config.reconcile_interval_sec
        self.assertTrue(coordinator._worth_collecting(self.now))

    def test_a_probe_negative_tick_skips_the_collection_and_counts_it(self) -> None:
        coordinator = self.build()
        coordinator._worth_collecting(self.now)
        self.now += 1
        coordinator._collect("tick")
        self.assertEqual(0, self.app.collected)
        self.assertEqual(1, coordinator.counters["skipped.probe"])

    def test_an_event_driven_collection_is_never_skipped_by_the_probe(self) -> None:
        # The probe answers "did the store move". An event is a statement about
        # what the agent is doing, and no filesystem stamp can refute it.
        coordinator = self.build()
        coordinator._worth_collecting(self.now)
        self.now += 1
        coordinator.submit("claude", self.envelope())
        coordinator._collect("event")
        self.assertEqual(1, self.app.collected)

    def test_reconcile_required_forces_the_next_tick_to_read(self) -> None:
        # Compaction. A rewritten transcript is not repaired by a cached read.
        coordinator = self.build()
        coordinator._worth_collecting(self.now)
        self.now += 1
        coordinator.submit("claude", self.envelope(event="reconcile_required"))
        self.assertTrue(coordinator._worth_collecting(self.now))


class WorkerLifecycleTest(ObservationTestCase):
    def test_construction_starts_no_thread(self) -> None:
        # The daemon forks after assembly. A coordinator that spawned in its
        # constructor would be inherited half-running, or lost with the parent.
        before = threading.active_count()
        self.build()
        self.assertEqual(before, threading.active_count())

    def test_start_spawns_one_worker_and_stop_joins_it(self) -> None:
        coordinator = self.build()
        coordinator.start()
        worker = coordinator._worker
        assert worker is not None
        self.assertTrue(worker.is_alive())
        coordinator.stop(timeout=5)
        self.assertFalse(worker.is_alive())

    def test_starting_twice_does_not_spawn_a_second_worker(self) -> None:
        coordinator = self.build()
        coordinator.start()
        first = coordinator._worker
        coordinator.start()
        self.assertIs(first, coordinator._worker)
        coordinator.stop(timeout=5)

    def test_stopping_without_starting_is_safe(self) -> None:
        self.build().stop(timeout=1)

    def test_a_worker_asked_to_stop_before_it_ran_does_no_work(self) -> None:
        # The check before the wait, not just after it. Shutdown can land between
        # start() and the worker's first loop, and a round of collection during
        # teardown would publish into a stream registry already being closed.
        coordinator = self.build()
        coordinator.stop(timeout=1)
        coordinator.start()
        worker = coordinator._worker
        assert worker is not None
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(0, self.app.collected)

    def test_stopping_twice_is_safe(self) -> None:
        coordinator = self.build()
        coordinator.start()
        coordinator.stop(timeout=5)
        coordinator.stop(timeout=1)

    def test_the_worker_wakes_on_an_event_rather_than_waiting_out_its_interval(self) -> None:
        # The producer interval is five seconds. If the wake did not work this
        # would time out rather than fail, so the deadline is deliberately short.
        coordinator = self.build()
        collected = threading.Event()
        real = self.app.collect_json

        def signalling(*, show_all: bool) -> Any:
            result = real(show_all=show_all)
            collected.set()
            return result

        self.app.collect_json = signalling  # type: ignore[method-assign]
        # A real clock here: the worker actually sleeps, so a frozen clock would
        # leave the coalescing deadline permanently in the future.
        coordinator.clock = time.time
        coordinator._last_reconcile_at = coordinator.clock()
        coordinator.start()
        try:
            coordinator.submit("claude", self.envelope())
            self.assertTrue(collected.wait(timeout=3), "the coordinator did not wake on the event")
        finally:
            coordinator.stop(timeout=5)


class ApplicationOverlayTest(unittest.TestCase):
    """The other half: what a collection does with the ledger."""

    def setUp(self) -> None:
        support.reset_runtime()

    def _collect_with(self, overlays: Any) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project = projects / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / f"{PREFIX}-0000-0000-0000-000000000000.jsonl"
            transcript.write_text(json.dumps({"type": "user", "uuid": "u"}) + "\n")
            quiet = support.SERVER_STARTED - 300
            os.utime(transcript, (quiet, quiet))
            with (
                support.store_patch(PROJECTS_DIR=str(projects)),
                support.store_patch(TASKS_DIR=str(projects / "tasks")),
            ):
                config, _state = support.runtime()
                self.assertEqual(
                    (str(projects),),
                    config.store_roots["claude.projects"],
                    "the store redirect did not take, so this read the real store",
                )
                app = support.build_app()
                app.overlays = overlays
                app.clock = lambda: support.SERVER_STARTED
                collection: dict[str, Any] = app.collect(show_all=False)
                return collection

    def _row(self, collection: dict[str, Any]) -> dict[str, Any]:
        rows = [s for s in collection["sessions"] if s["sid"] == PREFIX]
        self.assertEqual(1, len(rows), "the seeded session was not collected")
        row: dict[str, Any] = rows[0]
        return row

    def test_with_no_overlay_source_a_collection_is_unchanged(self) -> None:
        # This is what --no-events leaves behind, so it has to be the old path
        # exactly rather than a variant of the new one.
        row = self._row(self._collect_with(None))
        self.assertEqual("idle", row["state"])
        self.assertNotIn("acquisition", row)

    def test_a_live_overlay_patches_the_matching_row(self) -> None:
        class Source:
            def __init__(self) -> None:
                self.noted: set[tuple[str, str]] = set()

            def overlays_for(self, harness: str, sid: str) -> list[events.Overlay]:
                if (harness, sid) != ("claude", PREFIX):
                    return []
                return [
                    events.Overlay(
                        harness="claude",
                        sid=PREFIX,
                        arrival_seq=1,
                        kind=events.OVERLAY_NEEDS_INPUT,
                        at=support.SERVER_STARTED - 10,
                    )
                ]

            def note_rows(self, keys: set[tuple[str, str]]) -> None:
                self.noted = keys

        source = Source()
        row = self._row(self._collect_with(source))
        self.assertEqual("needs_input", row["state"])
        self.assertEqual(events.ACQUISITION_EVENT, row["acquisition"])
        self.assertIn(("claude", PREFIX), source.noted)

    def test_the_summary_counts_the_patched_state_not_the_collected_one(self) -> None:
        # Patching after the summary was counted would show a needs-input row in
        # a board reporting zero waiting sessions.
        class Source:
            def overlays_for(self, harness: str, sid: str) -> list[events.Overlay]:
                if (harness, sid) != ("claude", PREFIX):
                    return []
                return [
                    events.Overlay(
                        harness="claude",
                        sid=PREFIX,
                        arrival_seq=1,
                        kind=events.OVERLAY_NEEDS_INPUT,
                        at=support.SERVER_STARTED - 10,
                    )
                ]

            def note_rows(self, keys: set[tuple[str, str]]) -> None:
                pass

        collection = self._collect_with(Source())
        self.assertEqual(1, collection["summary"]["needs_input"])

    def test_an_overlay_for_an_unknown_session_creates_no_row(self) -> None:
        class Source:
            def __init__(self) -> None:
                self.asked: list[tuple[str, str]] = []

            def overlays_for(self, harness: str, sid: str) -> list[events.Overlay]:
                self.asked.append((harness, sid))
                return [
                    events.Overlay(
                        harness="claude",
                        sid="ffffffff",
                        arrival_seq=1,
                        kind=events.OVERLAY_NEEDS_INPUT,
                        at=support.SERVER_STARTED,
                    )
                ]

            def note_rows(self, keys: set[tuple[str, str]]) -> None:
                pass

        source = Source()
        collection = self._collect_with(source)
        self.assertNotIn("ffffffff", [s["sid"] for s in collection["sessions"]])
        # The row list is walked, not the ledger, which is what makes that true.
        self.assertNotIn(("claude", "ffffffff"), source.asked)


class WiringTest(unittest.TestCase):
    """Assembly: who builds the coordinator, and who starts it."""

    def test_the_cli_attaches_a_coordinator_both_ways(self) -> None:
        captured: dict[str, Any] = {}

        class CapturingServer:
            def __init__(
                self,
                _address: tuple[str, int],
                application: Any,
                _page: bytes,
                coordinator: Any = None,
            ) -> None:
                captured["application"] = application
                captured["coordinator"] = coordinator

            def serve_forever(self) -> None:
                raise KeyboardInterrupt

            def server_close(self) -> None:
                pass

        self._run_main(CapturingServer, [])
        self.assertIsNotNone(captured["coordinator"])
        self.assertIs(captured["coordinator"], captured["application"].overlays)

    def test_no_events_leaves_the_application_without_an_overlay_source(self) -> None:
        captured: dict[str, Any] = {}

        class CapturingServer:
            def __init__(
                self,
                _address: tuple[str, int],
                application: Any,
                _page: bytes,
                coordinator: Any = None,
            ) -> None:
                captured["application"] = application
                captured["coordinator"] = coordinator

            def serve_forever(self) -> None:
                raise KeyboardInterrupt

            def server_close(self) -> None:
                pass

        self._run_main(CapturingServer, ["--no-events"])
        self.assertIsNone(captured["coordinator"])
        self.assertIsNone(captured["application"].overlays)

    def _run_main(self, server_class: Any, extra: list[str]) -> None:
        with (
            mock.patch.object(http_api, "CargentoHTTPServer", server_class),
            mock.patch.object(lifecycle, "write_state"),
            mock.patch.object(lifecycle, "remove_state"),
            mock.patch.object(runtime_io, "diag"),
            contextlib.suppress(KeyboardInterrupt),
        ):
            cli.main(["--port", "4553", *extra])

    def test_serve_starts_the_coordinator_instead_of_the_producer(self) -> None:
        events_seen: list[str] = []

        class FakeCoordinator:
            def capabilities(self) -> dict[str, str]:
                events_seen.append("capabilities")
                return {"claude": "token"}

            def start(self) -> None:
                events_seen.append("start")

            def stop(self, *, timeout: float) -> None:  # noqa: ARG002 (signature parity)
                events_seen.append("stop")

        class FakeServer:
            observation = FakeCoordinator()
            application = None

            def serve_forever(self) -> None:
                events_seen.append("serve")

            def server_close(self) -> None:
                pass

        config = support.make_config()
        with (
            mock.patch.object(lifecycle, "write_state"),
            mock.patch.object(lifecycle, "remove_state"),
            mock.patch.object(lifecycle, "run_producer") as producer,
        ):
            lifecycle.serve(
                config,
                FakeServer(),  # type: ignore[arg-type]
                4553,
                started=NOW,
                diagnostic_sink=lambda _message: None,
            )
        # capabilities before start: the tokens are published by write_state, and
        # a hook that fires the instant the worker begins must find them already
        # on disk rather than racing the write.
        self.assertEqual(["capabilities", "start", "serve", "stop"], events_seen)
        producer.assert_not_called()

    def test_serve_falls_back_to_the_producer_without_a_coordinator(self) -> None:
        class FakeServer:
            application = None

            def serve_forever(self) -> None:
                pass

            def server_close(self) -> None:
                pass

        config = support.make_config()
        with (
            mock.patch.object(lifecycle, "write_state"),
            mock.patch.object(lifecycle, "remove_state"),
            mock.patch.object(lifecycle, "run_producer") as producer,
        ):
            lifecycle.serve(
                config,
                FakeServer(),  # type: ignore[arg-type]
                4553,
                started=NOW,
                diagnostic_sink=lambda _message: None,
            )
        producer.assert_called_once()
