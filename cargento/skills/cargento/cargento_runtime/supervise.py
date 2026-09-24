"""Model subprocesses, each in a process group of its own (a Job Object on Windows).

`subprocess.run` kills only the direct child on a timeout. A CLI that has
started a helper, or the `cmd.exe` behind a `.CMD` shim on Windows, leaves that
grandchild running with nobody to reap it. Every model call Cargento makes goes
through `run` instead, so a timeout, a shutdown and (DRC-4693) a Cancel kill the
whole tree and never the daemon's own group: `--daemon` calls `setsid`, and a
foreground run shares the job of the terminal that started it.

`run` keeps `subprocess.run`'s keyword subset, so a test that injects a runner
with that signature stays valid, plus `on_spawn`: it is handed the `Group` the
moment the child exists, which is the seam a reading job uses to say it is
waiting on the provider and DRC-4693 will use to cancel.

This module imports nothing from the runtime.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

_LOCK = threading.Lock()
_LIVE: set[Group] = set()


def kill_group(pgid: int) -> None:
    """SIGKILL one process group, and never this process's own.

    The guard is the property DRC-4693 depends on, so it lives at the one call
    to `killpg` rather than at each caller: 0 and 1 name the caller's own group
    and init, and `getpgrp()` is the daemon's.
    """
    if sys.platform == "win32" or pgid <= 1 or pgid == os.getpgrp():
        return
    # ESRCH once the group has emptied; EPERM on macOS for a group left holding
    # only zombies. Neither is a group this call could still stop.
    with contextlib.suppress(OSError):
        os.killpg(pgid, signal.SIGKILL)


class Group:
    """One supervised child and everything it started."""

    def __init__(self, process: subprocess.Popen[Any], job: int = 0) -> None:
        self._process = process
        # The Windows Job Object handle, 0 on POSIX.
        self._job = job
        # Held across a kill and across the close, so a shutdown's kill from
        # another thread never lands on a handle, or a group id, that `run`
        # has already given up.
        self._lock = threading.Lock()
        self._done = False

    @property
    def pid(self) -> int:
        return self._process.pid

    def running(self) -> bool:
        return self._process.poll() is None

    def kill(self) -> None:
        """Kill the whole tree. Safe to call more than once, and from any thread."""
        with self._lock:
            if not self._done:
                self._kill()

    def _kill(self) -> None:
        if sys.platform == "win32":
            if self._job:
                _windows.terminate(self._job)
            return
        # The child leads its own session, so its pid is the group id. Killed
        # while the leader is unreaped, which is what keeps the id from being
        # reused: `run` reaps only after this returns, and a group with a live
        # member keeps its id on its own.
        kill_group(self._process.pid)

    def close(self) -> None:
        """The last word on this group: one straggler sweep, then no more kills."""
        with self._lock:
            if self._done:
                return
            # A helper the CLI left behind after a normal exit. The leader is
            # reaped by now, and a group keeps its id while any member lives,
            # so this reaches only the stragglers or nothing.
            self._kill()
            self._done = True
            if sys.platform == "win32" and self._job:
                # KILL_ON_JOB_CLOSE: closing the last handle ends any straggler.
                _windows.close(self._job)
                self._job = 0


def live() -> frozenset[Group]:
    """The groups running now."""
    with _LOCK:
        return frozenset(_LIVE)


def kill_all() -> None:
    """Kill every running group. Daemon shutdown calls this.

    With a group of its own, a child no longer receives the Ctrl-C a foreground
    run gets, so without this it would outlive the daemon, orphaned, with
    nobody left to remove its temporary files.
    """
    for group in live():
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
    """`subprocess.run`, with the whole tree killed on a timeout or an error.

    Returns only after the child is reaped, so a caller's `finally` that
    removes a temporary file never races a writer that is still alive.
    """
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
    process = group._process  # noqa: SLF001 (the one owner of the handle)
    with _LOCK:
        _LIVE.add(group)
    try:
        try:
            if on_spawn is not None:
                on_spawn(group)
            # `communicate` writes stdin from a thread on Windows, where the
            # pipe buffer is smaller than a 16 KiB prompt.
            out, err = process.communicate(input, timeout=timeout)
        except BaseException:
            # The timeout, a failing `on_spawn`, or an interrupt: kill before
            # reaping, then reap, then let it propagate.
            group.kill()
            process.communicate()
            raise
    finally:
        with _LOCK:
            _LIVE.discard(group)
        group.close()
    if check and process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command, out, err)
    return subprocess.CompletedProcess(command, process.returncode, out, err)


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

    def terminate(self, job: int) -> None:
        kernel32, _ = self._load()
        kernel32.TerminateJobObject(job, 1)

    def close(self, job: int) -> None:
        kernel32, _ = self._load()
        kernel32.CloseHandle(job)


_windows = _Windows()
