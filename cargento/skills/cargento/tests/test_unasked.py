"""The unasked reading lane, and the four things it must never do.

DRC-4541. The lane checks an annotated session against what the reader typed
without being asked and raises a departure. It is off by default, it spends the
reader's own model capacity, and the reader is by construction not at the desk
while it runs, which is why most of what is asserted here is a refusal.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

from cargento_runtime import departures, reading, unasked
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

if TYPE_CHECKING:
    from cargento_runtime.annotations import Annotation


def _config(root: Path, **changes: Any) -> Any:
    config = build_runtime_config(
        environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
        platform_name="linux",
        os_name="posix",
        launcher_path=root / "server.py",
        unasked_enabled=True,
    )
    import dataclasses  # noqa: PLC0415

    return dataclasses.replace(config, **changes) if changes else config


def _annotation(sid: str = "s-1") -> Annotation:
    return {
        "harness": "claude",
        "sid": sid,
        "revisions": ({"n": 4, "goal": "Ship the cockpit", "output": "", "at": 10.0},),
    }


def _row(sid: str = "s-1", state: str = "working") -> dict[str, Any]:
    return {"harness": "claude", "sid": sid, "state": state, "project": "trio/app"}


def _assessment(*results: str) -> reading.Assessment:
    return {
        "revision_read": 4,
        "revision_read_at": 10.0,
        "stamp": "a stamp",
        "cutoff": "900.0",
        "scope": "final",
        "scope_text": "",
        "ended_at_read": None,
        "criteria": {
            f"c{n}": {"result": result, "cites": ("e1",), "detail": "went elsewhere", "clause": "G"}
            for n, result in enumerate(results)
        },
    }


class _Harness:
    """One lane with every outside edge replaced by something countable."""

    def __init__(self, config: Any, assessment: reading.Assessment | None) -> None:
        self.config = config
        self.state = build_runtime_state(config, started=1_000.0)
        self.readings: list[str] = []
        self.popups: list[tuple[str, str]] = []
        self.assessment = assessment

        def produce(_config: Any, row: Any, *_args: Any, **_kwargs: Any) -> Any:
            self.readings.append(str(row.get("sid")))
            return (self.assessment, "", True)

        def popup(title: str, message: str) -> str:
            self.popups.append((title, message))
            return "handed-over"

        self.lane = unasked.Lane(
            config,
            popup_notifier=popup,
            diagnostic_sink=lambda _line: None,
            clock=lambda: 5_000.0,
            produce=produce,
            facts_for=lambda _state, _row, _now: [{"id": "e1"}],
            # Inline rather than threaded, so a test asserts on what happened
            # rather than on what was scheduled. The lane's own threading is
            # covered by the in-flight test below.
            spawn=lambda work: work(),
        )

    def consider(self, rows: list[dict[str, Any]], *, now: float = 5_000.0) -> None:
        self.lane.consider(self.state, rows, [_annotation()], now=now)


class TheSwitchIsTheWholeGateTest(unittest.TestCase):
    """AC1. With the switch off nothing runs, asserted on the absence of a call.

    Asserted at the assembly point rather than inside the lane, because with the
    switch off there is no lane: `build_application` does not attach one, so
    there is no code path a later refactor could leave reachable.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_the_switch_defaults_off(self) -> None:
        config = build_runtime_config(
            environ={"HOME": str(self.root)},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
        )

        self.assertFalse(config.unasked_enabled)

    def test_no_lane_is_attached_with_the_switch_off(self) -> None:
        from cargento_runtime import cli  # noqa: PLC0415

        config = build_runtime_config(
            environ={"HOME": str(self.root), "CARGENTO_HOME": str(self.root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
        )
        state = build_runtime_state(config, started=1_000.0)

        application = cli.build_application(config, state, diagnostic_sink=lambda _line: None)

        self.assertIsNone(application.unasked_lane)

    def test_diagnose_attaches_no_lane_even_with_the_switch_on(self) -> None:
        # `--diagnose` runs a collection and must not start a codex subprocess
        # while reporting what the stores hold. It is the one caller that says
        # no to `record_history`, and this rides the same signal rather than
        # inventing a second is-this-diagnose flag.
        from cargento_runtime import cli  # noqa: PLC0415

        config = _config(self.root)
        state = build_runtime_state(config, started=1_000.0)

        application = cli.build_application(
            config, state, diagnostic_sink=lambda _line: None, record_history=False
        )

        self.assertIsNone(application.unasked_lane)

    def test_the_lane_is_attached_when_the_switch_is_on(self) -> None:
        from cargento_runtime import cli  # noqa: PLC0415

        config = _config(self.root)
        state = build_runtime_state(config, started=1_000.0)

        application = cli.build_application(config, state, diagnostic_sink=lambda _line: None)

        self.assertIsNotNone(application.unasked_lane)


class ItEvaluatesOnAChangeAndNotPerCollectionTest(unittest.TestCase):
    """AC2. A working session generates nothing until something changes."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.harness = _Harness(_config(Path(self.temp.name)), _assessment("departure"))

    def _harness(self) -> _Harness:
        return self.harness

    def test_the_first_sighting_of_a_row_is_not_a_change(self) -> None:
        # The board restarts and has observed nothing. Treating every row of
        # the first collection as a transition would read the whole board at
        # once on a boot nobody asked for.
        self.harness.consider([_row(state="working")])

        self.assertEqual([], self.harness.readings)

    def test_an_unchanged_session_produces_none(self) -> None:
        for _ in range(4):
            self.harness.consider([_row(state="working")])

        self.assertEqual([], self.harness.readings)

    def test_one_change_produces_one_reading(self) -> None:
        self.harness.consider([_row(state="working")])
        self.harness.consider([_row(state="idle")])
        self.harness.consider([_row(state="idle")])

        self.assertEqual(["s-1"], self.harness.readings)

    def test_a_session_nobody_annotated_is_never_read(self) -> None:
        self.harness.lane.consider(self.harness.state, [_row(state="working")], [], now=5_000.0)
        self.harness.lane.consider(self.harness.state, [_row(state="idle")], [], now=5_000.0)

        self.assertEqual([], self.harness.readings)

    def test_an_annotation_arriving_later_is_not_itself_a_change(self) -> None:
        # The state is noted for every row whether or not it is a candidate, so
        # a session annotated after it was first seen does not read as a
        # transition the moment the words land.
        self.harness.lane.consider(self.harness.state, [_row(state="working")], [], now=5_000.0)
        self.harness.consider([_row(state="working")])

        self.assertEqual([], self.harness.readings)

    def test_only_one_reading_starts_per_collection(self) -> None:
        # Forty annotated sessions crossing a boundary together must not start
        # forty subprocesses. Written against a SYNCHRONOUS worker on purpose:
        # with an asynchronous one the in-flight slot masks this, and the
        # guarantee would then rest on a `codex` subprocess outliving the loop
        # rather than on anything this function does. Measured without the
        # guard: four candidate rows started four readings.
        annotations = [_annotation(f"s-{n}") for n in range(4)]
        rows = [_row(f"s-{n}", "working") for n in range(4)]
        self.harness.lane.consider(self.harness.state, rows, annotations, now=5_000.0)
        moved = [_row(f"s-{n}", "idle") for n in range(4)]
        self.harness.lane.consider(self.harness.state, moved, annotations, now=5_000.0)

        self.assertEqual(1, len(self.harness.readings))

    def test_a_collection_with_no_candidate_reads_the_store_not_at_all(self) -> None:
        # `_claim` used to load the store per row. On a board where most rows
        # are not candidates that is a file read per row per collection, and
        # nothing else in the suite would have noticed.
        reads = 0
        real_load = departures.load

        def counted(config: Any) -> Any:
            nonlocal reads
            reads += 1
            return real_load(config)

        with mock.patch.object(departures, "load", counted):
            rows = [_row(f"s-{n}", "working") for n in range(20)]
            self.harness.lane.consider(self.harness.state, rows, [], now=5_000.0)
            moved = [_row(f"s-{n}", "idle") for n in range(20)]
            self.harness.lane.consider(self.harness.state, moved, [], now=5_000.0)

        self.assertEqual(0, reads)

    def test_candidates_that_all_fail_to_claim_still_read_the_store_once(self) -> None:
        # The case the cached read exists for, and the only one that reaches it:
        # the per-collection guard is set by a SUCCESSFUL claim, so a board
        # whose candidates are all held off by a cap walks the whole list. Once
        # per row would be a file read per annotated session per collection.
        reads = 0
        real_load = departures.load

        def counted(config: Any) -> Any:
            nonlocal reads
            reads += 1
            return real_load(config)

        spent: list[departures.Departure] = [
            {
                "harness": "claude",
                "sid": f"s-{n}",
                "at": 4_000.0,
                "constraint": "Goal",
                "clause": "G",
                "reading": "went elsewhere",
                "evidence": "e1",
                "revision": 4,
                "cutoff": 900.0,
            }
            for n in range(20)
            for _ in range(self.harness.config.unasked_session_cap)
        ]
        departures.record(self.harness.config, spent, diagnostic_sink=lambda _line: None)
        annotations = [_annotation(f"s-{n}") for n in range(20)]
        rows = [_row(f"s-{n}", "working") for n in range(20)]
        self.harness.lane.consider(self.harness.state, rows, annotations, now=5_000.0)
        with mock.patch.object(departures, "load", counted):
            moved = [_row(f"s-{n}", "idle") for n in range(20)]
            self.harness.lane.consider(self.harness.state, moved, annotations, now=5_000.0)

        self.assertEqual([], self.harness.readings, "every candidate was at its cap")
        self.assertEqual(1, reads)

    def test_a_collection_with_candidates_reads_the_store_once(self) -> None:
        reads = 0
        real_load = departures.load

        def counted(config: Any) -> Any:
            nonlocal reads
            reads += 1
            return real_load(config)

        # The worker is collected rather than run, so the only reads counted are
        # the ones `consider` itself makes. The worker's own read is the
        # store's read-modify-write and is not this test's subject.
        self.harness.lane.spawn = lambda _work: None
        annotations = [_annotation(f"s-{n}") for n in range(20)]
        rows = [_row(f"s-{n}", "working") for n in range(20)]
        self.harness.lane.consider(self.harness.state, rows, annotations, now=5_000.0)
        with mock.patch.object(departures, "load", counted):
            moved = [_row(f"s-{n}", "idle") for n in range(20)]
            self.harness.lane.consider(self.harness.state, moved, annotations, now=5_000.0)

        self.assertEqual(1, reads)


class OnlyDeparturesAreRaisedTest(unittest.TestCase):
    """AC4. An unasked reassurance is the output the evidence floor called most
    damaging, and it has no value to someone away from the desk."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _run(self, assessment: reading.Assessment | None) -> _Harness:
        harness = _Harness(_config(self.root), assessment)
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])
        return harness

    def test_a_consistent_reading_raises_nothing(self) -> None:
        harness = self._run(_assessment(reading.RESULT_CONSISTENT))

        self.assertEqual(["s-1"], harness.readings, "the reading still ran")
        self.assertEqual([], harness.popups)
        self.assertEqual((), departures.load(harness.config))

    def test_an_unverifiable_reading_raises_nothing(self) -> None:
        harness = self._run(_assessment(reading.RESULT_UNVERIFIABLE))

        self.assertEqual([], harness.popups)
        self.assertEqual((), departures.load(harness.config))

    def test_a_withheld_reading_raises_nothing(self) -> None:
        harness = self._run(None)

        self.assertEqual([], harness.popups)
        self.assertEqual((), departures.load(harness.config))

    def test_a_departure_is_raised_and_named_apart_from_a_question(self) -> None:
        harness = self._run(_assessment(reading.RESULT_DEPARTURE))

        self.assertEqual(1, len(harness.popups))
        title = harness.popups[0][0]
        self.assertIn("may be going off track", title)
        self.assertNotIn("waiting on you", title)
        self.assertNotIn("is asking you", title)

    def test_a_mixed_reading_raises_only_its_departures(self) -> None:
        harness = self._run(_assessment(reading.RESULT_CONSISTENT, reading.RESULT_DEPARTURE))

        stored = departures.load(harness.config)
        self.assertEqual(1, len(stored))
        self.assertEqual("c1", stored[0]["constraint"])

    def test_two_departures_in_one_reading_are_one_banner(self) -> None:
        # One reading is one thing that happened. Two banners about it would
        # read as two events.
        harness = self._run(_assessment(reading.RESULT_DEPARTURE, reading.RESULT_DEPARTURE))

        self.assertEqual(2, len(departures.load(harness.config)))
        self.assertEqual(1, len(harness.popups))
        self.assertIn("2 constraints departed", harness.popups[0][1])

    def test_the_raise_records_its_delivery_outcome(self) -> None:
        # The record DRC-4540 built. A departure that never left the machine
        # must not read as one the reader ignored.
        from cargento_runtime import deliveries  # noqa: PLC0415

        harness = self._run(_assessment(reading.RESULT_DEPARTURE))

        rows = deliveries.load(harness.config)
        self.assertEqual(1, len(rows))
        self.assertEqual("departure", rows[0]["lane"])


class TheRaiseCarriesItsOwnBaselineTest(unittest.TestCase):
    """AC3. By the time this is read the annotation may be at a later revision
    and the evidence window has moved."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.harness = _Harness(
            _config(Path(self.temp.name)), _assessment(reading.RESULT_DEPARTURE)
        )
        self.harness.consider([_row(state="working")])
        self.harness.consider([_row(state="idle")])

    def test_the_revision_and_cutoff_are_stored_with_the_raise(self) -> None:
        stored = departures.load(self.harness.config)

        self.assertEqual(4, stored[0]["revision"])
        self.assertEqual(900.0, stored[0]["cutoff"])

    def test_a_later_revision_does_not_rewrite_what_was_raised(self) -> None:
        # The store holds the baseline, not a pointer to one, so a save after
        # the raise cannot change what the raise said it read.
        before = departures.load(self.harness.config)[0]["revision"]

        self.harness.lane.consider(
            self.harness.state,
            [_row(state="working")],
            [
                {
                    "harness": "claude",
                    "sid": "s-1",
                    "revisions": (
                        {"n": 4, "goal": "Ship the cockpit", "output": "", "at": 10.0},
                        {"n": 9, "goal": "Something else entirely", "output": "", "at": 20.0},
                    ),
                }
            ],
            now=5_000.0,
        )

        self.assertEqual(before, departures.load(self.harness.config)[0]["revision"])

    def test_a_reading_with_no_machine_readable_cutoff_stores_zero(self) -> None:
        assessment = _assessment(reading.RESULT_DEPARTURE)
        assessment["cutoff"] = "the last nine turns"
        harness = _Harness(_config(Path(self.temp.name) / "other"), assessment)
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])

        self.assertEqual(0.0, departures.load(harness.config)[0]["cutoff"])


class ExhaustedNeverReadsLikeQuietTest(unittest.TestCase):
    """AC5. The reader is by construction not present, so "nothing departed" and
    "nothing was checked" must never render alike."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = _config(Path(self.temp.name), unasked_session_cap=2, unasked_daily_cap=3)

    def _store(self, count: int, *, sid: str = "s-1", at: float = 4_000.0) -> None:
        rows: list[departures.Departure] = [
            {
                "harness": "claude",
                "sid": sid,
                "at": at + n,
                "constraint": f"c{n}",
                "clause": "G",
                "reading": "went elsewhere",
                "evidence": "e1",
                "revision": 4,
                "cutoff": 900.0,
            }
            for n in range(count)
        ]
        departures.record(self.config, rows, diagnostic_sink=lambda _line: None)

    def _why(self, *, checked: bool = True) -> str:
        stored = departures.load(self.config)
        return str(
            unasked.published(self.config, stored, _row(), now=5_000.0, checked=checked)[
                "departure_why"
            ]
        )

    def test_the_lane_off_says_nothing_was_checked(self) -> None:
        self.assertEqual(departures.NEVER_CHECKED, self._why(checked=False))
        self.assertIn("has not checked", self._why(checked=False))

    def test_the_lane_on_with_nothing_found_says_so_and_not_the_same_thing(self) -> None:
        self.assertEqual(departures.NOTHING_DEPARTED, self._why())
        self.assertNotEqual(departures.NEVER_CHECKED, departures.NOTHING_DEPARTED)

    def test_a_spent_session_cap_says_a_limit_was_spent(self) -> None:
        self._store(2)

        why = self._why()

        self.assertEqual(departures.SESSION_EXHAUSTED, why)
        self.assertIn("not a session found to be on track", why)

    def test_a_spent_day_cap_says_so_apart_from_the_session_cap(self) -> None:
        # Three raises spread across three sessions: no session is at its cap
        # and the board is at its daily one, which is the case a single number
        # would hide.
        for n in range(3):
            self._store(1, sid=f"other-{n}")

        why = self._why()

        self.assertEqual(departures.DAY_EXHAUSTED, why)
        self.assertNotEqual(departures.SESSION_EXHAUSTED, departures.DAY_EXHAUSTED)

    def test_the_four_sentences_are_four_sentences(self) -> None:
        every = {
            departures.NEVER_CHECKED,
            departures.NOTHING_DEPARTED,
            departures.SESSION_EXHAUSTED,
            departures.DAY_EXHAUSTED,
        }

        self.assertEqual(4, len(every))

    def test_no_sentence_claims_the_session_is_on_track(self) -> None:
        for sentence in (
            departures.NEVER_CHECKED,
            departures.NOTHING_DEPARTED,
            departures.SESSION_EXHAUSTED,
            departures.DAY_EXHAUSTED,
        ):
            with self.subTest(sentence=sentence[:40]):
                lowered = sentence.lower()
                for claim in ("on track", "is fine", "no problem", "as you asked"):
                    if claim == "on track":
                        # The two exhausted sentences say "NOT a ... found to be
                        # on track", which is the refusal rather than the claim.
                        self.assertNotIn("is on track", lowered)
                        continue
                    self.assertNotIn(claim, lowered)


class TheCapsStopTheReadingRatherThanTheRaiseTest(unittest.TestCase):
    """A cap that let the subprocess run and dropped the result would have spent
    the reader's capacity to produce nothing, which is the failure
    `reading.produce` refuses one layer down."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _harness(self, **changes: Any) -> _Harness:
        return _Harness(_config(self.root, **changes), _assessment(reading.RESULT_DEPARTURE))

    def test_a_session_at_its_cap_starts_no_reading(self) -> None:
        harness = self._harness(unasked_session_cap=1, unasked_session_floor_sec=0.0)
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])

        self.assertEqual(["s-1"], harness.readings)

    def test_the_board_at_its_day_cap_starts_no_reading_on_any_session(self) -> None:
        harness = self._harness(unasked_daily_cap=1, unasked_session_floor_sec=0.0)
        harness.consider([_row("s-1", "working")])
        harness.consider([_row("s-1", "idle")])
        harness.lane.consider(
            harness.state, [_row("s-2", "working")], [_annotation("s-2")], now=5_000.0
        )
        harness.lane.consider(
            harness.state, [_row("s-2", "idle")], [_annotation("s-2")], now=5_000.0
        )

        self.assertEqual(["s-1"], harness.readings)

    def test_the_per_session_floor_holds_a_second_reading_off(self) -> None:
        # A session can cross a state boundary repeatedly inside a minute, and
        # the cap is not a rate limit.
        harness = self._harness()
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])

        self.assertEqual(["s-1"], harness.readings)

    def test_the_floor_opens_again_once_it_has_passed(self) -> None:
        harness = self._harness()
        harness.consider([_row(state="working")], now=5_000.0)
        harness.consider([_row(state="idle")], now=5_000.0)
        harness.consider([_row(state="working")], now=99_000.0)
        harness.consider([_row(state="idle")], now=99_000.0)

        self.assertEqual(["s-1", "s-1"], harness.readings)

    def test_a_reading_in_flight_blocks_the_next(self) -> None:
        # Counted, not inspected. Asserting on the in-flight SET passed with the
        # check removed, because a second claim re-adds the same key and the set
        # reads identically either way.
        harness = self._harness()
        spawned: list[Any] = []
        harness.lane.spawn = spawned.append  # never runs, so the slot stays held
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])

        self.assertEqual(1, len(spawned))
        self.assertEqual({"claude:s-1"}, harness.state.unasked_inflight)

    def test_a_reading_still_in_flight_blocks_the_next_collection(self) -> None:
        # One reading at a TIME, which is the rule the per-collection guard does
        # not give. A different session in a LATER collection is the only shape
        # that isolates it: the same session would be held by its own floor, and
        # the same collection by the guard.
        harness = self._harness()
        spawned: list[Any] = []
        harness.lane.spawn = spawned.append  # never runs, so the slot stays held
        both = [_annotation("s-1"), _annotation("s-2")]
        harness.lane.consider(
            harness.state, [_row("s-1", "working"), _row("s-2", "working")], both, now=5_000.0
        )
        harness.lane.consider(harness.state, [_row("s-1", "idle")], both, now=5_000.0)
        self.assertEqual(1, len(spawned), "the first collection started one")

        harness.lane.consider(harness.state, [_row("s-2", "idle")], both, now=5_000.0)

        self.assertEqual(1, len(spawned))
        self.assertEqual({"claude:s-1"}, harness.state.unasked_inflight)

    def test_the_slot_is_released_once_the_reading_finishes(self) -> None:
        # Held, not leaked. A slot never released would silence the lane for the
        # life of the process, which reads exactly like a board with nothing to
        # raise.
        harness = self._harness()
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])

        self.assertEqual(set(), harness.state.unasked_inflight)

    def test_a_reading_that_raises_still_releases_the_slot(self) -> None:
        harness = self._harness()
        harness.lane.produce = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom"))
        harness.consider([_row(state="working")])
        harness.consider([_row(state="idle")])

        self.assertEqual(set(), harness.state.unasked_inflight)


class TheDepartureStoreSurvivesConcurrentWritersTest(unittest.TestCase):
    """The lesson `deliveries` had to be measured into, applied here from the
    first commit rather than after the same loss."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = _config(Path(self.temp.name))

    def _write(self, n: int) -> None:
        departures.record(
            self.config,
            [
                {
                    "harness": "claude",
                    "sid": f"s-{n}",
                    "at": 100.0 + n,
                    "constraint": "Goal",
                    "clause": "G",
                    "reading": "went elsewhere",
                    "evidence": "e1",
                    "revision": 4,
                    "cutoff": 900.0,
                }
            ],
            diagnostic_sink=lambda _line: None,
        )

    def test_two_simultaneous_writers_both_land(self) -> None:
        ready = threading.Barrier(2)

        def write(n: int) -> None:
            ready.wait()
            self._write(n)

        threads = [threading.Thread(target=write, args=(n,)) for n in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(2, len(departures.load(self.config)))

    def test_a_reading_lands_whole_or_not_at_all(self) -> None:
        # One reading's departures are one raise. Splitting them would let a
        # restart between two writes publish half a raise.
        rows: list[departures.Departure] = [
            {
                "harness": "claude",
                "sid": "s-1",
                "at": 100.0 + n,
                "constraint": f"c{n}",
                "clause": "G",
                "reading": "went elsewhere",
                "evidence": "e1",
                "revision": 4,
                "cutoff": 900.0,
            }
            for n in range(3)
        ]

        departures.record(self.config, rows, diagnostic_sink=lambda _line: None)

        self.assertEqual(3, len(departures.load(self.config)))

    def test_a_corrupt_store_is_no_records_rather_than_a_raise(self) -> None:
        import os  # noqa: PLC0415

        os.makedirs(self.config.state_home, mode=0o700, exist_ok=True)
        with open(departures.store_path(self.config), "w", encoding="utf-8") as handle:
            handle.write("{not json")

        self.assertEqual((), departures.load(self.config))


if __name__ == "__main__":
    unittest.main()
