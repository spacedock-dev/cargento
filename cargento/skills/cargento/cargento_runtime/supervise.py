"""Model subprocesses, each in a process group of its own (a Job Object on Windows).

`subprocess.run` kills only the direct child on a timeout. A CLI that has
started a helper, or the `cmd.exe` behind a `.CMD` shim on Windows, leaves that
grandchild running with nobody to reap it. Every model call Cargento makes goes
through `run` instead, so a timeout, a shutdown and (DRC-4693) a Cancel kill the
CLI's process group and never the daemon's own: `--daemon` calls `setsid`, and a
foreground run shares the job of the terminal that started it. The limit on
POSIX: a helper that leaves the group, by `setsid` or `setpgid`, is not reached.
A Job Object on Windows has no such exit.

`run` keeps `subprocess.run`'s keyword subset, so a test that injects a runner
with that signature stays valid, plus `on_spawn`: it is handed the `Group` the
moment the child exists, which is the seam a reading job uses to say it is
waiting on the provider and a Cancel reaches the CLI through (`Group.cancel`). Output goes to a file
or nowhere, never to a pipe: every model call writes its reply to a file.

This module imports nothing from the runtime.
"""

from __future__ import annotations

import contextlib
import errno
import os
import select
import signal
import subprocess
import sys
import threading
import time
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

# Held across the spawn and its registration as well as across the shutdown's
# snapshot, so no child can exist between the two where a shutdown misses it.
_LOCK = threading.Lock()
_LIVE: set[Group] = set()
# Set once, by the shutdown, for the life of the process: a daemon on its way
# out starts nothing more (review F2, measured: a CLI spawned 0.2 s after the
# snapshot outlived the daemon).
_SHUTDOWN = threading.Event()
# How long a killed child may take to exit before the call stops waiting on it.
# SIGKILL is not ignorable, so the only children that outlast this are ones the
# kill never reached, and waiting longer would hang the reading instead.
REAP_TIMEOUT_SEC = 5.0
# How often a running call looks up from its wait to see whether it was
# cancelled. Only a kill that failed needs it: one that worked ends the wait
# at once. It bounds how late the call starts its own bounded reap.
_CANCEL_POLL_SEC = 0.1

_RUNNING, _EXITED, _REAPED, _UNKNOWN = "running", "exited", "reaped", "unknown"


class ClosedError(OSError):
    """The runner is shut down: nothing more is spawned in this process."""


class UnstoppedError(subprocess.SubprocessError):
    """A killed child did not exit within `REAP_TIMEOUT_SEC`, so it may still run."""


def kill_group(pgid: int) -> bool:
    """SIGKILL one process group, and never this process's own.

    True when the signal was delivered or the group is already gone, False when
    the kill itself failed. The guard is the property DRC-4693 depends on, so
    it lives at the one call to `killpg` rather than at each caller: 0 and 1
    name the caller's own group and init, and `getpgrp()` is the daemon's.
    """
    if sys.platform == "win32" or pgid <= 1 or pgid == os.getpgrp():
        return False
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        # EPERM, including macOS's answer for a group left holding only a
        # zombie leader. Whether the kill mattered is settled by whether the
        # leader exits, which the caller waits on with a bound.
        return False
    return True


def _state(pid: int, timeout: float) -> str:
    """Whether a child is running, has exited, or is already reaped. Never reaps.

    `waitid` with `WNOWAIT` where it exists (Linux), and a kqueue exit filter
    where it does not (macOS, whose `os` has no `waitid`). This only observes:
    what keeps a group from being signalled after its leader is reaped is
    `Group._reaped`, set under the group's lock in the same step as the reap.

    kqueue reports a registration it cannot make as an event flagged
    `EV_ERROR`, not as an exception. ESRCH there means the process has exited
    (a zombie cannot be registered either, and only `run` reaps, so it has not
    been reaped), and any other error means the exit cannot be watched:
    `_UNKNOWN`, which callers never read as an exit (verify N2).
    """
    return _state_waitid(pid, timeout) if hasattr(os, "waitid") else _state_kqueue(pid, timeout)


def _state_waitid(pid: int, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while True:
        try:
            info = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)  # type: ignore[attr-defined,unused-ignore]
        except ChildProcessError:
            return _REAPED
        if info is not None:
            return _EXITED
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _RUNNING
        time.sleep(min(0.02, remaining))


def _state_kqueue(pid: int, timeout: float) -> str:
    queue = select.kqueue()
    try:
        event = select.kevent(
            pid,
            filter=select.KQ_FILTER_PROC,
            flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
            fflags=select.KQ_NOTE_EXIT,
        )
        try:
            events = queue.control([event], 1, max(timeout, 0.0))
        except ProcessLookupError:
            return _EXITED
        except OSError:
            return _UNKNOWN
    finally:
        queue.close()
    if not events:
        return _RUNNING
    if events[0].flags & select.KQ_EV_ERROR:
        return _EXITED if events[0].data == errno.ESRCH else _UNKNOWN
    return _EXITED


class Group:
    """One supervised child and everything in its process group."""

    def __init__(self, process: subprocess.Popen[Any], job: int = 0) -> None:
        self._process = process
        # The Windows Job Object handle, 0 on POSIX.
        self._job = job
        # Held across every kill and across the reap, so a shutdown's or a
        # cancel's kill from another thread never lands after the leader is
        # reaped, when its id could name somebody else's group.
        self._lock = threading.Lock()
        self._reaped = False
        # Set by a Cancel, from any thread; the call's own wait reads it.
        self._cancelled = threading.Event()

    @property
    def pid(self) -> int:
        return self._process.pid

    def running(self) -> bool:
        """Whether the CLI still runs. Never reaps a leader it could still signal."""
        if sys.platform == "win32":
            # A handle, not a pid: polling it cannot free an id for reuse.
            return self._process.poll() is None
        with self._lock:
            if self._reaped:
                return False
            state = _state(self._process.pid, 0.0)
            if state != _UNKNOWN:
                return state == _RUNNING
            # Unwatchable: reap if it has exited, marked in the same step, so
            # no kill can follow the reap.
            if self._process.poll() is None:
                return True
            self._reaped = True
            return False

    def _await_exit(self, timeout: float) -> bool:
        """For an exit `_state` cannot watch: poll, reaping and marking in one step.

        True once the leader has exited (and is reaped, so its helpers are not
        swept), False on the timeout, with the leader still unreaped for the
        kill that follows.
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                if self._process.poll() is not None:
                    self._reaped = True
                    return True
            remaining = deadline - time.monotonic()
            if remaining <= 0 or self._cancelled.is_set():
                return False
            time.sleep(min(0.02, remaining))

    def kill(self) -> bool:
        """Kill the group. Safe from any thread and more than once; False if it failed."""
        with self._lock:
            return self._kill() if not self._reaped else True

    def cancel(self) -> None:
        """Ask the call to end its CLI, and kill it now when that costs no wait.

        Never blocks the caller, which is a request thread. The group lock is
        held for up to `REAP_TIMEOUT_SEC` by the call's own reap, and that reap
        kills anyway; any other holder lets go within one poll, after which
        the call sees the flag and kills and reaps with its bound. So a kill
        skipped here is one the call makes itself.
        """
        self._cancelled.set()
        if self._lock.acquire(blocking=False):
            try:
                if not self._reaped:
                    self._kill()
            finally:
                self._lock.release()

    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def _kill(self) -> bool:
        if sys.platform == "win32":
            return _windows.terminate(self._job) if self._job else True
        return kill_group(self._process.pid)

    def _finish(self) -> None:
        """Kill or sweep the group while its leader is unreaped, then reap. POSIX only.

        After a normal exit the leader is a zombie still holding the group id,
        so the sweep reaches the helpers it left behind and nothing else. After
        a timeout it is the kill itself. The reap is bounded: whether it comes
        is the one sign a kill worked, since `killpg`'s answer is not (EPERM on
        macOS for a group of one zombie).
        """
        with self._lock:
            if self._reaped:
                return
            if _state(self._process.pid, 0.0) != _REAPED:
                self._kill()
            # No signal after this point, whatever the reap does.
            self._reaped = True
            try:
                self._process.wait(timeout=REAP_TIMEOUT_SEC)
            except subprocess.TimeoutExpired as exc:
                raise UnstoppedError(self._process.pid) from exc

    def close(self) -> None:
        if sys.platform == "win32" and self._job:
            with self._lock:
                self._reaped = True
                # KILL_ON_JOB_CLOSE: closing the last handle ends any straggler.
                _windows.close(self._job)
                self._job = 0


def live() -> frozenset[Group]:
    """The groups running now."""
    with _LOCK:
        return frozenset(_LIVE)


def closed() -> bool:
    """Whether the runner has been shut down in this process."""
    return _SHUTDOWN.is_set()


def kill_all() -> None:
    """Shut the runner and kill every running group. Daemon shutdown calls this.

    With a group of its own, a child no longer receives the Ctrl-C a foreground
    run gets, so without this it would outlive the daemon, orphaned, with
    nobody left to remove its temporary files. The runner is closed under the
    spawn lock, so a spawn in progress registers first and is killed here, and
    any spawn after is refused.
    """
    with _LOCK:
        _SHUTDOWN.set()
        groups = list(_LIVE)
    for group in groups:
        group.kill()


def _spawn(
    command: Sequence[str],
    *,
    stdin: int | None,
    stdout: int | IO[Any] | None,
    stderr: int | IO[Any] | None,
    cwd: str | None,
    env: Mapping[str, str] | None,
    text: bool,
    encoding: str | None,
) -> Group:
    options: dict[str, Any] = {
        "stdin": stdin,
        "stdout": stdout,
        "stderr": stderr,
        "cwd": cwd,
        "env": env,
        "text": text,
        "encoding": encoding,
    }
    if sys.platform == "win32":
        process = subprocess.Popen(  # noqa: S603
            command,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
                | _CREATE_SUSPENDED
            ),
            **options,
        )
        try:
            # Suspended until it is in the job: a child resumed first can start
            # a grandchild the job never contains.
            job = _windows.contain(process)
        except OSError:
            process.kill()
            process.communicate()
            raise
        return Group(process, job)
    return Group(subprocess.Popen(command, start_new_session=True, **options))  # noqa: S603


_CREATE_SUSPENDED = 0x00000004


def _feed(stream: IO[Any], data: str | bytes) -> None:
    """Write a prompt to stdin from its own thread: the pipe is smaller than 16 KiB."""
    if data:
        with contextlib.suppress(OSError, ValueError):
            stream.write(data)
    with contextlib.suppress(OSError, ValueError):
        stream.close()


def run(  # noqa: PLR0913 (subprocess.run's keywords, one each)
    command: Sequence[str],
    *,
    input: str | bytes | None = None,  # noqa: A002 (subprocess.run's name)
    cwd: str | None = None,
    stdout: int | IO[Any] | None = None,
    stderr: int | IO[Any] | None = None,
    env: Mapping[str, str] | None = None,
    text: bool = False,
    encoding: str | None = None,
    timeout: float | None = None,
    check: bool = False,
    on_spawn: Callable[[Group], None] | None = None,
) -> subprocess.CompletedProcess[Any]:
    """`subprocess.run`, with the CLI's whole group killed on a timeout or an error.

    Returns only after the child is reaped, so a caller's `finally` that
    removes a temporary file never races a writer that is still alive. Raises
    `ClosedError` after a shutdown, and `UnstoppedError` when a killed child
    would not exit.
    """
    if subprocess.PIPE in (stdout, stderr):
        raise ValueError("supervise.run writes output to a file or nowhere, never a pipe")
    with _LOCK:
        if _SHUTDOWN.is_set():
            raise ClosedError("Cargento is shutting down")
        group = _spawn(
            command,
            stdin=subprocess.PIPE if input is not None else None,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
            env=env,
            text=text,
            encoding=encoding,
        )
        _LIVE.add(group)
    try:
        if sys.platform == "win32":
            returncode = _run_windows(group, input, timeout, on_spawn)
        else:
            returncode = _run_posix(group, input, timeout, on_spawn)
    finally:
        with _LOCK:
            _LIVE.discard(group)
        group.close()
    if check and returncode:
        raise subprocess.CalledProcessError(returncode, command)
    return subprocess.CompletedProcess(command, returncode, None, None)


def _run_posix(
    group: Group,
    data: str | bytes | None,
    timeout: float | None,
    on_spawn: Callable[[Group], None] | None,
) -> int:
    process = group._process  # noqa: SLF001 (the one owner of the handle)
    try:
        if on_spawn is not None:
            on_spawn(group)
        if data is not None and process.stdin is not None:
            threading.Thread(target=_feed, args=(process.stdin, data), daemon=True).start()
        timed_out = _wait_posix(group, 1e9 if timeout is None else timeout)
    except BaseException:
        # The timeout, a failing `on_spawn`, or an interrupt: kill before
        # reaping, reap with a bound, then let it propagate.
        with contextlib.suppress(UnstoppedError):
            group._finish()  # noqa: SLF001
        raise
    # A cancelled call reaps here as a timeout does: kill while the leader is
    # unreaped, then wait with the bound, so a kill that failed is reported
    # unstopped within it rather than after the call's own timeout.
    group._finish()  # noqa: SLF001
    if timed_out and not group.cancelled():
        raise subprocess.TimeoutExpired(process.args, timeout or 0.0)
    return int(process.returncode)


def _wait_posix(group: Group, limit: float) -> bool:
    """Wait for the leader to exit, a Cancel, or the limit. True on the limit.

    In slices, so a Cancel whose kill did not land is seen within one. An exit
    that cannot be watched is waited on by polling, never read as an exit:
    that would kill a running CLI at once.
    """
    pid = group.pid
    deadline = time.monotonic() + limit
    while True:
        remaining = deadline - time.monotonic()
        step = min(_CANCEL_POLL_SEC, max(remaining, 0.0))
        state = _state(pid, step)
        if state == _UNKNOWN:
            return not group._await_exit(max(deadline - time.monotonic(), 0.0))  # noqa: SLF001
        if state != _RUNNING or group.cancelled():
            return False
        if remaining <= step:
            return True


def _run_windows(
    group: Group,
    data: str | bytes | None,
    timeout: float | None,
    on_spawn: Callable[[Group], None] | None,
) -> int:
    process = group._process  # noqa: SLF001
    try:
        if on_spawn is not None:
            on_spawn(group)
        _wait_windows(group, data, timeout)
    except UnstoppedError:
        raise
    except BaseException:
        group.kill()
        try:
            process.communicate(timeout=REAP_TIMEOUT_SEC)
        except subprocess.TimeoutExpired as exc:
            raise UnstoppedError(process.pid) from exc
        raise
    return int(process.returncode)


def _wait_windows(group: Group, data: str | bytes | None, timeout: float | None) -> None:
    """`communicate` in slices, so a Cancel is seen within one. Raises on the limit.

    CPython's Windows `communicate` writes stdin in the calling thread, so the
    first call does not return until the prompt is written; a retry after its
    timeout loses no output, and the input goes with the first call only, as it
    must. Once cancelled, the step stays `_CANCEL_POLL_SEC` whatever the call's
    deadline says: a deadline that ran out inside the reap window made every
    step zero, and the loop spun on a core until the reap bound.
    """
    process = group._process  # noqa: SLF001
    deadline = None if timeout is None else time.monotonic() + timeout
    pending = data
    reap_by: float | None = None
    while True:
        step = _CANCEL_POLL_SEC
        if deadline is not None and not group.cancelled():
            step = min(step, max(deadline - time.monotonic(), 0.0))
        try:
            process.communicate(pending, timeout=step)
        except subprocess.TimeoutExpired:
            pending = None
        else:
            return
        if group.cancelled():
            if reap_by is None:
                group.kill()
                reap_by = time.monotonic() + REAP_TIMEOUT_SEC
            elif time.monotonic() >= reap_by:
                raise UnstoppedError(process.pid)
        elif deadline is not None and time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(process.args, timeout or 0.0)


class _Windows:
    """The Job Object calls, by ctypes: the standard library has no API for them."""

    _KILL_ON_JOB_CLOSE = 0x00002000
    _EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self) -> None:
        self._kernel32: Any = None
        self._ntdll: Any = None

    def _load(self) -> tuple[Any, Any]:
        if self._kernel32 is None:
            import ctypes  # noqa: PLC0415 (Windows only)
            from ctypes import wintypes  # noqa: PLC0415

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
            kernel32.SetInformationJobObject.argtypes = (
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            )
            kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
            kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            ntdll = ctypes.WinDLL("ntdll")  # type: ignore[attr-defined]
            ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
            self._kernel32, self._ntdll = kernel32, ntdll
        return self._kernel32, self._ntdll

    def contain(self, process: subprocess.Popen[Any]) -> int:
        """Put a suspended child in a new kill-on-close job, then resume it."""
        import ctypes  # noqa: PLC0415 (Windows only)
        from ctypes import wintypes  # noqa: PLC0415

        kernel32, ntdll = self._load()

        class IoCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_ulonglong)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
        # `Popen._handle` is the process handle; Popen exposes no public one.
        handle = int(process._handle)  # type: ignore[attr-defined]  # noqa: SLF001
        if not (
            kernel32.SetInformationJobObject(
                job, self._EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)
            )
            and kernel32.AssignProcessToJobObject(job, handle)
        ):
            error = ctypes.get_last_error()  # type: ignore[attr-defined]
            kernel32.CloseHandle(job)
            raise ctypes.WinError(error)  # type: ignore[attr-defined]
        if ntdll.NtResumeProcess(handle) != 0:
            kernel32.TerminateJobObject(job, 1)
            kernel32.CloseHandle(job)
            raise OSError("the supervised child could not be resumed")
        return int(job)

    def terminate(self, job: int) -> bool:
        kernel32, _ = self._load()
        return bool(kernel32.TerminateJobObject(job, 1))

    def close(self, job: int) -> None:
        kernel32, _ = self._load()
        kernel32.CloseHandle(job)


_windows = _Windows()
