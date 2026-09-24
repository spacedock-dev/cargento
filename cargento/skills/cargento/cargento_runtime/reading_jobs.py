"""A reader-pressed reading, run as a job the server owns (DRC-4686).

The press answers at once with the job, and the reading runs on a thread of its
own: `produce` over the supervised CLI, then the store write. The job itself,
its id and phase, lives beside the one-in-flight slot in `reading`, because the
unasked lane takes that same slot. This module is the thread: it tells the job
each real phase as it happens, publishes a revision for each, writes the
outcome, and only then frees the slot.

A spend the dashboard was stopped in the middle of is not lost. Once the spend
is committed, a small marker names the job; the outcome's write removes it,
and the next start turns any marker whose process is gone into a spent
`interrupted` attempt (Q2 on the issue). The marker holds identifiers only.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from . import annotations as annotation_store
from . import io as runtime_io
from . import reading, reading_policy

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import RuntimeConfig
    from .state import RuntimeState

MARKER_DIR = "reading-jobs"
THREAD_PREFIX = "cargento-reading-"

Outcome = tuple["reading.Assessment | None", str, bool]


class Application(Protocol):
    """What a job needs of `aggregate.Application`, without importing upward."""

    config: RuntimeConfig
    state: RuntimeState

    def clock(self) -> float: ...

    def diagnostic_sink(self, message: str, /) -> None: ...

    def collect_json(self, *, show_all: bool) -> tuple[Any, bytes]: ...


class Hooks:
    """What the reading tells its job, from the seams it passes through."""

    def __init__(self, application: Application, job: reading.Job) -> None:
        self._application = application
        self._job = job
        self._key = f"{job.harness}:{job.sid}"
        # Whether the reader's capacity went: set at the reservation, so an
        # exception after it still records a spent attempt.
        self.spent = False

    def reserved(self) -> None:
        """The spend is committed: leave the marker a restart would find."""
        self.spent = True
        config = self._application.config
        with contextlib.suppress(OSError):
            runtime_io.atomic_write_owner_only(
                str(_marker(config, self._job.id)),
                json.dumps(
                    {
                        "id": self._job.id,
                        "harness": self._job.harness,
                        "sid": self._job.sid,
                        "pid": os.getpid(),
                        "started_at": self._job.started_at,
                    }
                ),
            )

    def spawned(self, group: Any) -> None:
        """The CLI exists, so the job is waiting on the provider now."""
        self._job.group = group
        self.phase(reading.PHASE_WAITING)

    def phase(self, phase: str) -> None:
        if reading.advance_job(
            self._application.config, self._key, phase, now=self._application.clock()
        ):
            _publish(self._application)


def _marker(config: Any, job_id: str) -> Path:
    return Path(config.state_dir) / MARKER_DIR / f"{job_id}.json"


def _publish(application: Application) -> None:
    """A fresh revision for every connected page. Never raises into the job.

    From the job's own thread, so a phase reaches a reloaded page and an open
    one alike, through the push they already hold.
    """
    try:
        application.state.snapshot.clear()
        application.collect_json(show_all=False)
    except Exception as exc:  # noqa: BLE001 (a failed publish must not end the reading)
        runtime_io.diag(
            f"Cargento: a reading job could not publish ({exc.__class__.__name__}).",
            application.diagnostic_sink,
        )


def launch(
    application: Application, job: reading.Job, compose: Callable[[Hooks], Outcome]
) -> threading.Thread:
    """Run one job on a daemon thread and return it."""
    thread = threading.Thread(
        target=_run, args=(application, job, compose), name=f"{THREAD_PREFIX}{job.id}", daemon=True
    )
    thread.start()
    return thread


def _run(application: Application, job: reading.Job, compose: Callable[[Hooks], Outcome]) -> None:
    config = application.config
    hooks = Hooks(application, job)
    try:
        _publish(application)
        outcome = _outcome(application, compose, hooks)
        if outcome is not None:
            _record(application, job, outcome)
    finally:
        with contextlib.suppress(OSError):
            _marker(config, job.id).unlink(missing_ok=True)
        # After the write and only then: a page that sees the job gone sees
        # its result with it, never a finished box beside no result.
        reading.end_job(config, f"{job.harness}:{job.sid}")
        _publish(application)


def _outcome(
    application: Application, compose: Callable[[Hooks], Outcome], hooks: Hooks
) -> Outcome | None:
    """The reading's result, or None when the model seam refused it."""
    try:
        return compose(hooks)
    except reading_policy.RefusedError:
        # Another tab filled the budget, or consent was withdrawn, after the
        # press was admitted. Nothing ran and nothing is written: the board's
        # published permission already says why.
        return None
    except Exception as exc:  # noqa: BLE001 (a failed job must still free its slot)
        runtime_io.diag(
            f"Cargento: a reading job failed ({exc.__class__.__name__}).",
            application.diagnostic_sink,
        )
        return None, reading.WITHHELD_MODEL_FAILED, hooks.spent


def _record(application: Application, job: reading.Job, outcome: Outcome) -> None:
    assessment, why, spent = outcome
    config, state = application.config, application.state
    try:
        if assessment is not None:
            annotation_store.record_reading(
                config,
                state,
                job.harness,
                job.sid,
                assessment=assessment,
                diagnostic_sink=application.diagnostic_sink,
            )
        else:
            annotation_store.record_withheld(
                config,
                state,
                job.harness,
                job.sid,
                reason=why,
                spent=spent,
                diagnostic_sink=application.diagnostic_sink,
            )
    except Exception as exc:  # noqa: BLE001 (the slot is freed whatever the store did)
        runtime_io.diag(
            f"Cargento: a reading's outcome could not be stored ({exc.__class__.__name__}).",
            application.diagnostic_sink,
        )


def recover(application: Application, *, alive: Callable[[int], bool]) -> int:
    """Record every job a stopped dashboard left spent. Returns how many.

    `alive` is `lifecycle.pid_exists`, injected so this module never imports
    the lifecycle. A marker whose process still runs belongs to another
    dashboard on this state directory, on another port, and is left alone. A
    reused pid leaves a marker for a later start rather than recording a live
    job as interrupted.
    """
    config, state = application.config, application.state
    recorded = 0
    for path in sorted((Path(config.state_dir) / MARKER_DIR).glob("*.json")):
        try:
            marker = json.loads(path.read_text(encoding="utf-8"))
            harness, sid, pid = marker["harness"], marker["sid"], int(marker["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            with contextlib.suppress(OSError):
                path.unlink()
            continue
        if pid == os.getpid() or alive(pid):
            continue
        annotation_store.record_withheld(
            config,
            state,
            harness,
            sid,
            reason=reading.WITHHELD_INTERRUPTED,
            spent=True,
            diagnostic_sink=application.diagnostic_sink,
        )
        recorded += 1
        with contextlib.suppress(OSError):
            path.unlink()
    return recorded
