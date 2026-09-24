"""A reader-pressed reading run as a server-owned job (DRC-4686).

The route tests in `test_http_api.ReadingRouteTest` drive the job through a
real socket. These drive `reading_jobs` directly, with an application that
records what each collection published, so the order of the job's effects is
observable rather than inferred from a final state.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import io as runtime_io
from cargento_runtime import reading, reading_jobs, reading_policy, supervise

from .support import make_runtime

KEY = "claude:s1"


class _Application:
    """Enough of `aggregate.Application` for a job: it records every publish."""

    def __init__(self, config: Any, state: Any, events: list[Any]) -> None:
        self.config = config
        self.state = state
        self.events = events
        self.diagnostics: list[str] = []
        self.diagnostic_sink = self.diagnostics.append

    @staticmethod
    def clock() -> float:
        return 1_700_000_100.0

    def collect_json(self, *, show_all: bool) -> tuple[Any, bytes]:
        del show_all
        running = reading.published_jobs(self.config).get(KEY)
        self.events.append(("publish", running["phase"] if running else None))
        return (0.0, 0), b"{}"


class ReadingJobTest(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        self.config, self.state = make_runtime(
            state_home=home, state_dir=Path(home), annotations_enabled=True
        )
        annotation_store.annotate(
            self.config, self.state, "claude", "s1", goal="ship the parser", output="", now=10.0
        )
        self.events: list[Any] = []
        self.application: Any = _Application(self.config, self.state, self.events)
        self.addCleanup(reading.end_job, self.config, KEY)
        # A dashboard's shutdown closes the runner for the life of its process,
        # and an earlier test that ran `serve` in this worker would leave it
        # closed: every outcome here would then read as a stop.
        patcher = mock.patch.object(supervise, "_SHUTDOWN", threading.Event())
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, compose: Any) -> reading.Job:
        job = reading.start_job(
            self.config, KEY, provider="claude", label="Claude Code", now=1_700_000_100.0
        )
        assert job is not None
        self.events.append(("started", job.phase))
        record_reading = annotation_store.record_reading
        record_withheld = annotation_store.record_withheld

        def wrote(kind: str, real: Any) -> Any:
            def spy(*args: Any, **kwargs: Any) -> Any:
                self.events.append((kind, kwargs.get("reason"), kwargs.get("spent")))
                return real(*args, **kwargs)

            return spy

        end_job = reading.end_job

        def ended(*args: Any) -> None:
            self.events.append(("ended", reading.job(self.config, KEY) is not None))
            end_job(*args)

        with (
            mock.patch.object(annotation_store, "record_reading", wrote("reading", record_reading)),
            mock.patch.object(
                annotation_store, "record_withheld", wrote("withheld", record_withheld)
            ),
            mock.patch.object(reading, "end_job", ended),
        ):
            thread = reading_jobs.launch(self.application, job, compose)
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive(), "the job never finished")
        return job

    def _markers(self) -> list[Path]:
        return sorted((Path(self.config.state_dir) / reading_jobs.MARKER_DIR).glob("*.json"))

    def test_each_real_phase_is_published_once_and_in_order(self) -> None:
        def compose(hooks: reading_jobs.Hooks) -> Any:
            hooks.before_reserve()
            hooks.reserved()
            hooks.spawned(object())
            hooks.phase(reading.PHASE_CHECKING)
            return None, reading.WITHHELD_MODEL_FAILED, True

        self._run(compose)
        published = [phase for kind, phase, *_ in self.events if kind == "publish"]
        self.assertEqual(["preparing", "waiting", "checking", None], published)

    def test_the_store_is_written_before_the_job_leaves_and_one_revision_follows(self) -> None:
        self._run(lambda _hooks: (None, reading.WITHHELD_LEDGER_EMPTY, False))
        tail = self.events[-3:]
        self.assertEqual(("withheld", reading.WITHHELD_LEDGER_EMPTY, False), tail[0])
        self.assertEqual(("ended", True), tail[1])
        self.assertEqual(("publish", None), tail[2])

    def test_the_spawned_group_is_kept_on_the_job_for_a_later_cancel(self) -> None:
        group = object()
        seen: list[Any] = []

        def compose(hooks: reading_jobs.Hooks) -> Any:
            hooks.spawned(group)
            running = reading.job(self.config, KEY)
            seen.append(running.group if running else None)
            return None, reading.WITHHELD_MODEL_FAILED, True

        self._run(compose)
        self.assertEqual([group], seen)

    def test_an_exception_in_the_job_still_frees_the_slot(self) -> None:
        for reserved in (False, True):
            with self.subTest(reserved=reserved):
                self.events.clear()

                def compose(hooks: reading_jobs.Hooks, *, spend: bool = reserved) -> Any:
                    if spend:
                        hooks.before_reserve()
                        hooks.reserved()
                    raise RuntimeError("the record could not be read")

                self._run(compose)
                self.assertIsNone(reading.job(self.config, KEY))
                self.assertTrue(reading.claim(self.config, KEY))
                reading.release(self.config, KEY)
                self.assertIn(("withheld", reading.WITHHELD_MODEL_FAILED, reserved), self.events)
                self.assertEqual([], self._markers())

    def test_a_refusal_at_the_model_seam_writes_nothing(self) -> None:
        def compose(_hooks: reading_jobs.Hooks) -> Any:
            raise reading_policy.RefusedError(
                reading_policy.status(self.config, now=1_700_000_100.0)
            )

        self._run(compose)
        self.assertEqual([], [e for e in self.events if e[0] in {"reading", "withheld"}])
        self.assertIsNone(reading.job(self.config, KEY))

    def test_a_spent_attempt_leaves_a_marker_until_its_outcome_is_stored(self) -> None:
        during: list[list[dict[str, Any]]] = []

        def compose(hooks: reading_jobs.Hooks) -> Any:
            hooks.before_reserve()
            hooks.reserved()
            during.append([json.loads(p.read_text()) for p in self._markers()])
            return None, reading.WITHHELD_MODEL_FAILED, True

        job = self._run(compose)
        self.assertEqual(
            [[{"id": job.id, "harness": "claude", "sid": "s1", "pid": os.getpid()}]],
            [[{k: m[k] for k in ("id", "harness", "sid", "pid")} for m in d] for d in during],
        )
        self.assertEqual([], self._markers())

    def test_an_unspent_job_leaves_no_marker(self) -> None:
        during: list[int] = []

        def compose(_hooks: reading_jobs.Hooks) -> Any:
            during.append(len(self._markers()))
            return None, reading.WITHHELD_LEDGER_EMPTY, False

        self._run(compose)
        self.assertEqual([0], during)

    # Correction round.

    def test_a_graceful_shutdown_records_the_attempt_as_interrupted(self) -> None:
        """Review F5: a job the shutdown killed is "interrupted", as the docs say."""
        from cargento_runtime import supervise  # noqa: PLC0415

        def compose(hooks: reading_jobs.Hooks) -> Any:
            hooks.before_reserve()
            hooks.reserved()
            supervise._SHUTDOWN.set()
            return None, reading.WITHHELD_MODEL_FAILED, True

        with mock.patch.object(supervise, "_SHUTDOWN", threading.Event()):
            self._run(compose)
        self.assertIn(("withheld", reading.WITHHELD_INTERRUPTED, True), self.events)

    def test_a_shutdown_keeps_the_unstopped_reason(self) -> None:
        """Verify N5: "may still be running" is the one sentence a stop must not hide."""

        def compose(hooks: reading_jobs.Hooks) -> Any:
            hooks.before_reserve()
            hooks.reserved()
            supervise._SHUTDOWN.set()
            return None, reading.WITHHELD_UNSTOPPED, True

        self._run(compose)
        self.assertIn(("withheld", reading.WITHHELD_UNSTOPPED, True), self.events)

    def test_a_kept_marker_recovers_as_a_refused_write_not_as_a_stop(self) -> None:
        """Verify N6: the analysis finished; the store refused its outcome."""

        def compose(hooks: reading_jobs.Hooks) -> Any:
            hooks.before_reserve()
            hooks.reserved()
            return None, reading.WITHHELD_MODEL_FAILED, True

        with mock.patch.object(
            annotation_store, "_record", return_value=annotation_store.OUTCOME_UNWRITABLE
        ):
            job = self._run(compose)
        self.assertEqual([f"{job.id}.json"], [p.name for p in self._markers()])
        reading_jobs.recover(self.application, alive=lambda _pid: False)
        entry = annotation_store.find(annotation_store.load(self.config), "claude", "s1")
        assert entry is not None
        self.assertEqual(reading.WITHHELD[reading.WITHHELD_UNSTORED], entry.get("withheld"))
        self.assertEqual(1, entry.get("readings"))

    def test_a_marker_that_cannot_be_written_stops_the_job_before_anything_is_spent(
        self,
    ) -> None:
        """Codex review: a spend no marker records could be lost to a restart."""
        spent: list[bool] = []

        def compose(hooks: reading_jobs.Hooks) -> Any:
            hooks.before_reserve()
            spent.append(True)
            return None, reading.WITHHELD_MODEL_FAILED, True

        with mock.patch.object(runtime_io, "atomic_write_owner_only", side_effect=OSError("full")):
            self._run(compose)
        self.assertEqual([], spent, "the job went on to spend with no marker")
        self.assertIn(("withheld", reading.WITHHELD_JOB_UNRECORDED, False), self.events)

    def test_a_store_that_refuses_a_spent_outcome_keeps_the_marker(self) -> None:
        """Codex review: the marker is the only record of the spend until the store has it."""
        for outcome in (annotation_store.OUTCOME_UNWRITABLE, annotation_store.OUTCOME_UNTRUSTED):
            with self.subTest(outcome=outcome):

                def compose(hooks: reading_jobs.Hooks) -> Any:
                    hooks.before_reserve()
                    hooks.reserved()
                    return None, reading.WITHHELD_MODEL_FAILED, True

                with mock.patch.object(annotation_store, "_record", return_value=outcome):
                    job = self._run(compose)
                self.assertEqual([f"{job.id}.json"], [p.name for p in self._markers()])
                for marker in self._markers():
                    marker.unlink()

    def test_a_thread_that_cannot_start_frees_the_job_and_the_slot(self) -> None:
        """Review F8: a failed start would otherwise answer every later press 409."""
        job = reading.start_job(self.config, KEY, provider="claude", label="Claude Code", now=1.0)
        assert job is not None
        with (
            mock.patch.object(threading.Thread, "start", side_effect=RuntimeError("no thread")),
            self.assertRaises(RuntimeError),
        ):
            reading_jobs.launch(self.application, job, lambda _h: (None, "", False))
        self.assertIsNone(reading.job(self.config, KEY))
        self.assertTrue(reading.claim(self.config, KEY))
        reading.release(self.config, KEY)


class ARestartRecordsTheAttemptItInterruptedTest(unittest.TestCase):
    """Q2: a job lost on restart is a spent `interrupted` attempt, never a silent loss."""

    def setUp(self) -> None:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        self.config, self.state = make_runtime(
            state_home=home, state_dir=Path(home), annotations_enabled=True
        )
        annotation_store.annotate(
            self.config, self.state, "claude", "s1", goal="ship the parser", output="", now=10.0
        )
        self.application: Any = _Application(self.config, self.state, [])
        self.markers = Path(self.config.state_dir) / reading_jobs.MARKER_DIR

    def _marker(self, name: str, content: str) -> Path:
        self.markers.mkdir(parents=True, exist_ok=True)
        path = self.markers / f"{name}.json"
        path.write_text(content)
        return path

    def _entry(self) -> Any:
        # From disk: a second dashboard's write never reaches this state's cache.
        return annotation_store.find(annotation_store.load(self.config), "claude", "s1")

    def test_a_marker_left_by_a_process_that_is_gone_becomes_a_spent_interrupted_attempt(
        self,
    ) -> None:
        marker = self._marker(
            "abc", json.dumps({"id": "abc", "harness": "claude", "sid": "s1", "pid": 4242})
        )
        recovered = reading_jobs.recover(self.application, alive=lambda _pid: False)
        self.assertEqual(1, recovered)
        entry = self._entry()
        self.assertEqual(1, entry.get("readings"))
        self.assertEqual(reading.WITHHELD[reading.WITHHELD_INTERRUPTED], entry.get("withheld"))
        self.assertFalse(marker.exists())

    def test_a_marker_whose_process_still_runs_is_another_dashboards_live_job(self) -> None:
        marker = self._marker(
            "abc", json.dumps({"id": "abc", "harness": "claude", "sid": "s1", "pid": 4242})
        )
        self.assertEqual(0, reading_jobs.recover(self.application, alive=lambda _pid: True))
        self.assertTrue(marker.exists())
        self.assertNotIn("readings", self._entry())

    def test_no_marker_writes_nothing(self) -> None:
        with mock.patch.object(annotation_store, "record_withheld") as record:
            self.assertEqual(0, reading_jobs.recover(self.application, alive=lambda _pid: False))
        record.assert_not_called()

    def test_an_unreadable_marker_is_removed_and_records_nothing(self) -> None:
        marker = self._marker("bad", "{not json")
        with mock.patch.object(annotation_store, "record_withheld") as record:
            self.assertEqual(0, reading_jobs.recover(self.application, alive=lambda _pid: False))
        record.assert_not_called()
        self.assertFalse(marker.exists())

    def test_an_outcome_already_stored_for_the_job_is_not_counted_again(self) -> None:
        """Review F3: the process died after the write and before the marker went."""
        annotation_store.record_withheld(
            self.config,
            self.state,
            "claude",
            "s1",
            reason=reading.WITHHELD_MODEL_FAILED,
            spent=True,
            job_id="abc",
        )
        marker = self._marker(
            "abc", json.dumps({"id": "abc", "harness": "claude", "sid": "s1", "pid": 4242})
        )
        reading_jobs.recover(self.application, alive=lambda _pid: False)
        self.assertEqual(1, self._entry().get("readings"))
        self.assertFalse(marker.exists())

    def test_recording_one_job_twice_counts_it_once(self) -> None:
        for _ in range(2):
            annotation_store.record_withheld(
                self.config,
                self.state,
                "claude",
                "s1",
                reason=reading.WITHHELD_MODEL_FAILED,
                spent=True,
                job_id="abc",
            )
        self.assertEqual(1, self._entry().get("readings"))

    def test_two_dashboards_recovering_one_marker_count_it_once(self) -> None:
        for attempt in range(20):
            with self.subTest(attempt=attempt):
                job_id = f"job{attempt}"
                self._marker(
                    job_id,
                    json.dumps({"id": job_id, "harness": "claude", "sid": "s1", "pid": 4242}),
                )
                before = self._entry().get("readings", 0)
                _, other_state = make_runtime(
                    state_home=str(self.config.state_dir),
                    state_dir=Path(self.config.state_dir),
                    annotations_enabled=True,
                )
                other: Any = _Application(self.config, other_state, [])
                gate = threading.Barrier(2)

                def recover(app: Any, gate: threading.Barrier = gate) -> None:
                    gate.wait(5)
                    reading_jobs.recover(app, alive=lambda _pid: False)

                threads = [
                    threading.Thread(target=recover, args=(app,))
                    for app in (self.application, other)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(10)
                self.assertEqual(before + 1, self._entry().get("readings"))
                self.assertEqual([], list(self.markers.iterdir()))

    def test_a_marker_naming_this_process_is_an_earlier_run(self) -> None:
        """Review F4: a container's dashboard is PID 1 on every start."""
        self._marker(
            "abc", json.dumps({"id": "abc", "harness": "claude", "sid": "s1", "pid": os.getpid()})
        )
        self.assertEqual(1, reading_jobs.recover(self.application, alive=lambda _pid: True))
        self.assertEqual(1, self._entry().get("readings"))

    def test_the_interrupted_sentence_says_the_attempt_counted(self) -> None:
        sentence = reading.WITHHELD[reading.WITHHELD_INTERRUPTED]
        self.assertIn("stopped before it finished", sentence)
        self.assertIn("fresh press is the only retry", sentence)


class TheThreadIsNamedForItsJobTest(unittest.TestCase):
    def test_a_job_thread_carries_its_id(self) -> None:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        config, state = make_runtime(state_home=home, state_dir=Path(home))
        job = reading.start_job(config, KEY, provider="codex", label="Codex", now=1.0)
        assert job is not None
        release = threading.Event()
        application: Any = _Application(config, state, [])
        thread = reading_jobs.launch(
            application,
            job,
            lambda _hooks: (release.wait(5), (None, reading.WITHHELD_LEDGER_EMPTY, False))[1],
        )
        try:
            self.assertEqual(f"{reading_jobs.THREAD_PREFIX}{job.id}", thread.name)
            self.assertTrue(thread.daemon)
        finally:
            release.set()
            thread.join(5)


if __name__ == "__main__":
    unittest.main()
