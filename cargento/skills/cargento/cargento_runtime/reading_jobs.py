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

A Cancel (DRC-4693) marks the job, kills its CLI's group, and lets this thread
finish as it would have: the reap, the file removal, the write, and only then
the slot. The outcome is decided at the seal, just before the write, so a
Cancel either lands before it and discards whatever came back, or after it and
changes nothing.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from . import annotations as annotation_store
from . import io as runtime_io
from . import reading, reading_policy, supervise

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from .config import RuntimeConfig
    from .state import RuntimeState

MARKER_DIR = "reading-jobs"
THREAD_PREFIX = "cargento-reading-"
# A marker being recovered is renamed to `<id>.json.claim-<pid>-<nonce>` first.
# The rename is atomic, so of two dashboards recovering one marker exactly one
# records it; the claim names its process, so a claimer that died is re-claimed.
_CLAIM = ".claim-"
# The claims this process made, so a thread of this process never takes another
# thread's claim for one an earlier process with the same pid left behind.
_CLAIMS: set[str] = set()
_CLAIMS_LOCK = threading.Lock()
# A recovery pass holds an OS lock on this file, beside the marker directory
# rather than in it. The rename alone is not exclusive on Windows: two
# recoverers on the windows-latest runner lost 3 attempts in 20 uncounted. The
# mechanism is inferred, not observed: a MoveFileEx holds its source open for
# DELETE, so the other recoverer's plain read of its claim fails with a sharing
# violation. An OS lock dies with its process, so it needs no stale-holder rule.
RECOVERY_LOCK = "reading-jobs.lock"
# How long a start waits for another dashboard's pass before leaving the
# markers to the next start, which loses nothing: they stay on disk.
_RECOVERY_WAIT_SECONDS = 10.0


# The reasons a kept marker carries as they were, rather than as "unstored".
# A refused `cancelled` recovered as "The analysis ran" would be false.
_KEPT_REASONS = (
    reading.WITHHELD_INTERRUPTED,
    reading.WITHHELD_UNSTOPPED,
    reading.WITHHELD_CANCELLED,
)
# Held across every read-and-rewrite and removal of a marker, because a Cancel
# rewrites one from a request thread while the job's own thread may remove it:
# unheld, a rewrite could land after the removal and leave a marker behind.
_MARKER_LOCK = threading.Lock()


class UnrecordedError(OSError):
    """The restart marker could not be written, so the job may not spend."""


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

    def before_reserve(self) -> None:
        """Leave the marker a restart would find, before anything is spent.

        Before and not after the reservation: a marker that cannot be written
        stops the job with nothing spent, where one written after could fail
        with the spend already made and nothing left to count it. The price is
        the other side of that line: a dashboard that dies between this write
        and the reservation leaves a marker for an attempt the budget never
        charged, and the next start counts it.
        """
        config = self._application.config
        marker: dict[str, Any] = {
            "id": self._job.id,
            "harness": self._job.harness,
            "sid": self._job.sid,
            "pid": os.getpid(),
            "started_at": self._job.started_at,
        }
        try:
            with _MARKER_LOCK:
                # A Cancel that came after the seam's own check still spends,
                # and a restart must say it was cancelled.
                if reading.job_cancelled(self._job):
                    marker["reason"] = reading.WITHHELD_CANCELLED
                runtime_io.atomic_write_owner_only(
                    str(_marker(config, self._job.id)), json.dumps(marker)
                )
        except OSError as exc:
            raise UnrecordedError(str(exc)) from exc

    def reserved(self) -> None:
        """The spend is committed."""
        self.spent = True

    def mark_unstored(self, why: str) -> None:
        """Rewrite the kept marker with the reason its next start should record.

        "unstored" for an outcome that ran; a stop or a kill that could not be
        confirmed keeps its own reason, so "may still be running" is never
        turned into "ran".
        """
        path = _marker(self._application.config, self._job.id)
        with _MARKER_LOCK, contextlib.suppress(OSError, ValueError):
            marker = json.loads(path.read_text(encoding="utf-8"))
            marker["reason"] = why if why in _KEPT_REASONS else reading.WITHHELD_UNSTORED
            runtime_io.atomic_write_owner_only(str(path), json.dumps(marker))

    def spawned(self, group: Any) -> None:
        """The CLI exists, so the job is waiting on the provider now.

        A Cancel that came before the handover found no group to kill, so it
        is killed here, at once.
        """
        if reading.hand_over(self._job, group):
            group.cancel()
        self.phase(reading.PHASE_WAITING)

    def cancelled(self) -> bool:
        """Whether a reader's Cancel was accepted for this job."""
        return reading.job_cancelled(self._job)

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
    """Run one job on a daemon thread and return it.

    A thread that cannot start ends the job and frees the slot before the
    error propagates, or every later press would answer `in-flight` until the
    dashboard restarted (review F8).
    """
    thread = threading.Thread(
        target=_run, args=(application, job, compose), name=f"{THREAD_PREFIX}{job.id}", daemon=True
    )
    try:
        thread.start()
    except BaseException:
        reading.end_job(application.config, f"{job.harness}:{job.sid}")
        raise
    return thread


def cancel(application: Application, session_key: str, job_id: str) -> bool:
    """A reader's Cancel. True when the named job was running and is now ending.

    Never waits for the reap: the job's own thread does that, so a request
    thread is never held for `supervise.REAP_TIMEOUT_SEC`.
    """
    accepted, group = reading.cancel_job(
        application.config, session_key, job_id, now=application.clock()
    )
    if not accepted:
        return False
    # So a dashboard that dies before the outcome is stored says at its next
    # start that the attempt was cancelled. A marker that already carries a
    # reason keeps it: "may still be running" is never overwritten.
    path = _marker(application.config, job_id)
    with _MARKER_LOCK, contextlib.suppress(OSError, ValueError):
        marker = json.loads(path.read_text(encoding="utf-8"))
        if "reason" not in marker:
            marker["reason"] = reading.WITHHELD_CANCELLED
            runtime_io.atomic_write_owner_only(str(path), json.dumps(marker))
    if group is not None:
        group.cancel()
    _publish(application)
    return True


def _run(application: Application, job: reading.Job, compose: Callable[[Hooks], Outcome]) -> None:
    config = application.config
    hooks = Hooks(application, job)
    durable = True
    try:
        _publish(application)
        outcome = _outcome(application, compose, hooks)
        if reading.seal_job(job) and outcome is not None:
            outcome = _cancelled(job, outcome, spent=hooks.spent)
        if outcome is not None:
            durable = _record(application, job, outcome)
    finally:
        # A spend the store would not take keeps its marker: it is then the
        # only record that the attempt was charged, and the next start counts
        # it. Anything else has been stored, or never spent.
        if durable or not hooks.spent:
            with _MARKER_LOCK, contextlib.suppress(OSError):
                _marker(config, job.id).unlink(missing_ok=True)
        else:
            # Kept, and told why, so the next start says the store refused the
            # outcome rather than that Cargento stopped (verify N6).
            hooks.mark_unstored(outcome[1] if outcome is not None else "")
        # After the write and only then: a page that sees the job gone sees
        # its result with it, never a finished box beside no result.
        reading.end_job(config, f"{job.harness}:{job.sid}")
        _publish(application)


def _outcome(
    application: Application, compose: Callable[[Hooks], Outcome], hooks: Hooks
) -> Outcome | None:
    """The reading's result, or None when the model seam refused it."""
    try:
        outcome = compose(hooks)
    except reading_policy.RefusedError:
        # Another tab filled the budget, or consent was withdrawn, after the
        # press was admitted. Nothing ran and nothing is written: the board's
        # published permission already says why.
        return None
    except UnrecordedError:
        return None, reading.WITHHELD_JOB_UNRECORDED, False
    except Exception as exc:  # noqa: BLE001 (a failed job must still free its slot)
        runtime_io.diag(
            f"Cargento: a reading job failed ({exc.__class__.__name__}).",
            application.diagnostic_sink,
        )
        outcome = None, reading.WITHHELD_MODEL_FAILED, hooks.spent
    assessment, why, spent = outcome
    # "May still be running" is the one sentence a stop must not hide (verify N5).
    if assessment is None and spent and supervise.closed() and why != reading.WITHHELD_UNSTOPPED:
        # The dashboard is stopping and killed the call: said as the stop it
        # was, as the next start would have said it (review F5).
        return None, reading.WITHHELD_INTERRUPTED, True
    return outcome


def _cancelled(job: reading.Job, outcome: Outcome, *, spent: bool) -> Outcome:
    """The outcome of a job a Cancel reached before its seal.

    "May still be running" outranks the cancel, as it outranks a stop (verify
    N5). A cancel made after the shutdown began leaves the stop's own word.
    Anything else, a reply included, becomes the cancel: spent from the
    reservation on, and unspent before it.
    """
    _assessment, why, was_spent = outcome
    if why == reading.WITHHELD_UNSTOPPED:
        return outcome
    if job.cancelled_after_close and why == reading.WITHHELD_INTERRUPTED:
        return outcome
    if was_spent or spent:
        return None, reading.WITHHELD_CANCELLED, True
    return None, reading.WITHHELD_CANCELLED_UNSENT, False


def _record(application: Application, job: reading.Job, outcome: Outcome) -> bool:
    """Write the outcome under the job's id. True when the store holds it."""
    assessment, why, spent = outcome
    config, state = application.config, application.state
    try:
        if assessment is not None:
            answer = annotation_store.record_reading(
                config,
                state,
                job.harness,
                job.sid,
                assessment=assessment,
                diagnostic_sink=application.diagnostic_sink,
                job_id=job.id,
            )
        else:
            answer = annotation_store.record_withheld(
                config,
                state,
                job.harness,
                job.sid,
                reason=why,
                spent=spent,
                diagnostic_sink=application.diagnostic_sink,
                job_id=job.id,
            )
    except Exception as exc:  # noqa: BLE001 (the slot is freed whatever the store did)
        runtime_io.diag(
            f"Cargento: a reading's outcome could not be stored ({exc.__class__.__name__}).",
            application.diagnostic_sink,
        )
        return False
    return answer not in {annotation_store.OUTCOME_UNWRITABLE, annotation_store.OUTCOME_UNTRUSTED}


def recover(application: Application, *, alive: Callable[[int], bool]) -> int:
    """Record every job a stopped dashboard left spent. Returns how many.

    `alive` answers whether a pid is a dashboard serving this state directory
    now (`lifecycle.dashboard_alive`, injected so this module never imports the
    lifecycle). A marker such a dashboard holds is its running job and is left
    alone. This process's own pid is an earlier run that happened to get it
    back, as a container's PID 1 does on every start: this process has started
    no job yet. A pass holds `RECOVERY_LOCK`, each marker is claimed by a
    rename before it is recorded, and it is recorded under its job's id, so two
    dashboards recovering together, or a dashboard that died after the write,
    count it once. The rename is atomic on POSIX and is not exclusive on
    Windows, which is why the lock is there.
    """
    config = application.config
    if not any((Path(config.state_dir) / MARKER_DIR).glob("*.json*")):
        return 0
    with _recovering(Path(config.state_dir) / RECOVERY_LOCK) as held:
        return _recover(application, alive) if held else 0


def _recover(application: Application, alive: Callable[[int], bool]) -> int:
    config, state = application.config, application.state
    recorded = 0
    for path in sorted((Path(config.state_dir) / MARKER_DIR).glob("*.json*")):
        claimed = _claim(path, alive)
        if claimed is None:
            continue
        try:
            text = claimed.read_text(encoding="utf-8")
        except OSError:
            # Not a malformed marker, so not deleted as one. A file that is gone
            # was taken by another claimer; any other error is left named for
            # this process, which the next start reads as an earlier run's.
            continue
        try:
            marker = json.loads(text)
            harness, sid, job_id = marker["harness"], marker["sid"], str(marker["id"])
            kept = marker.get("reason")
            reason = (
                kept
                if kept in (*_KEPT_REASONS, reading.WITHHELD_UNSTORED)
                else reading.WITHHELD_INTERRUPTED
            )
        except (ValueError, KeyError, TypeError):
            with contextlib.suppress(OSError):
                claimed.unlink()
            continue
        answer = annotation_store.record_withheld(
            config,
            state,
            harness,
            sid,
            reason=reason,
            spent=True,
            diagnostic_sink=application.diagnostic_sink,
            job_id=job_id,
        )
        if answer in {annotation_store.OUTCOME_UNWRITABLE, annotation_store.OUTCOME_UNTRUSTED}:
            continue
        recorded += answer == annotation_store.OUTCOME_STORED
        with contextlib.suppress(OSError):
            claimed.unlink()
    return recorded


@contextlib.contextmanager
def _recovering(path: Path) -> Iterator[bool]:
    """Hold the recovery lock for one pass. Yields whether the pass may run.

    False only while another pass holds the lock past the wait. A lock file
    that cannot be opened or locked for any other reason yields True: the
    rename claim still holds on POSIX, and refusing would strand every marker.
    """
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield True
        return
    try:
        held = _lock(fd)
        try:
            yield held is not False
        finally:
            if held:
                _unlock(fd)
    finally:
        os.close(fd)


def _lock(fd: int) -> bool | None:
    """Lock `fd`, waiting a bounded time. None when this file cannot be locked."""
    deadline = time.monotonic() + _RECOVERY_WAIT_SECONDS
    while True:
        try:
            if sys.platform == "win32":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError):
            # Held elsewhere: `flock` raises the first, `msvcrt.locking` the
            # second (EACCES), each for this and nothing else.
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
        except OSError:
            return None
        else:
            return True


def _unlock(fd: int) -> None:
    with contextlib.suppress(OSError):
        if sys.platform == "win32":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)


def _claim(path: Path, alive: Callable[[int], bool]) -> Path | None:
    """Take a marker, or a dead recoverer's claim on one, for this process."""
    name = path.name
    base, _, claimant = name.partition(_CLAIM)
    if not base.endswith(".json"):
        return None
    with _CLAIMS_LOCK:
        if name in _CLAIMS:
            return None
    pid = _holder(path, claimant)
    if pid is None or (pid and pid != os.getpid() and alive(pid)):
        return None
    target = path.with_name(f"{base}{_CLAIM}{os.getpid()}-{secrets.token_hex(4)}")
    with _CLAIMS_LOCK:
        _CLAIMS.add(target.name)
    try:
        path.rename(target)
    except OSError:
        return None
    return target


def _holder(path: Path, claimant: str) -> int | None:
    """The pid that holds a marker or a claim, 0 when none can be read, None to skip."""
    if claimant:
        try:
            return int(claimant.split("-", maxsplit=1)[0])
        except ValueError:
            return None
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0
