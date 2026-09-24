"""The supervised runner every model call goes through (DRC-4686).

Each test runs a real child: `sys.executable -c ...` standing in for a CLI.
A fake runner cannot show the property that matters, which is that the whole
tree the CLI started dies on a timeout, and that the daemon's own group is
never the one signalled.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import supervise

from .support import process_alive

# A CLI that starts a grandchild, writes the grandchild's pid where the test can
# read it, and then outlives any timeout the test sets.
_SPAWNS_A_GRANDCHILD = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "with open(sys.argv[1], 'w') as out:\n"
    "    out.write(str(child.pid))\n"
    "time.sleep(60)\n"
)


def _wait_until(predicate: Any, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return bool(predicate())


class SupervisedRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.home, True))
        # A shutdown closes the runner for the life of the process. Each test
        # gets an open one, so a test that shuts it cannot close it for the next.
        patcher = mock.patch.object(supervise, "_SHUTDOWN", threading.Event())
        patcher.start()
        self.addCleanup(patcher.stop)

    def _grandchild(self, pid_file: Path) -> int:
        self.assertTrue(
            _wait_until(lambda: pid_file.exists() and pid_file.read_text().strip()),
            "the fake CLI never started its grandchild",
        )
        return int(pid_file.read_text())

    def test_a_timeout_kills_the_grandchild_as_well_as_the_child(self) -> None:
        pid_file = self.home / "grandchild.pid"
        seen: list[supervise.Group] = []

        def spawned(group: supervise.Group) -> None:
            seen.append(group)

        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            supervise.run(
                [sys.executable, "-c", _SPAWNS_A_GRANDCHILD, str(pid_file)],
                input="",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                timeout=3,
                check=False,
                on_spawn=spawned,
            )
        grandchild = self._grandchild(pid_file)
        self.assertLess(time.monotonic() - started, 30, "the timeout did not bound the call")
        self.assertEqual(1, len(seen))
        self.assertFalse(process_alive(seen[0].pid), "the child outlived its timeout")
        self.assertTrue(
            _wait_until(lambda: not process_alive(grandchild)),
            "the grandchild outlived the timeout: only the direct child was killed",
        )

    @unittest.skipIf(sys.platform == "win32", "process groups are POSIX")
    def test_the_daemons_own_process_group_is_never_signalled(self) -> None:
        pid_file = self.home / "grandchild.pid"
        own = os.getpgrp()
        with (
            mock.patch.object(os, "killpg", wraps=os.killpg) as killpg,
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            supervise.run(
                [sys.executable, "-c", _SPAWNS_A_GRANDCHILD, str(pid_file)],
                input="",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            )
        groups = [call.args[0] for call in killpg.call_args_list]
        self.assertTrue(groups, "nothing was killed, so this test proved nothing")
        self.assertNotIn(own, groups)

    @unittest.skipIf(sys.platform == "win32", "process groups are POSIX")
    def test_a_kill_aimed_at_the_daemons_own_group_is_refused(self) -> None:
        with mock.patch.object(os, "killpg") as killpg:
            supervise.kill_group(os.getpgrp())
            supervise.kill_group(0)
            supervise.kill_group(1)
        killpg.assert_not_called()

    @unittest.skipIf(sys.platform == "win32", "process groups are POSIX")
    def test_the_child_leads_a_process_group_of_its_own(self) -> None:
        out = self.home / "group.txt"
        with out.open("w") as handle:
            supervise.run(
                [sys.executable, "-c", "import os; print(os.getpgrp(), os.getpid())"],
                input="",
                stdout=handle,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=30,
            )
        group, pid = (int(part) for part in out.read_text().split())
        self.assertEqual(pid, group)
        self.assertNotEqual(os.getpgrp(), group)

    def test_a_long_prompt_arrives_whole_on_stdin(self) -> None:
        out = self.home / "length.txt"
        prompt = "x" * 16_384
        with out.open("w") as handle:
            result = supervise.run(
                [sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"],
                input=prompt,
                stdout=handle,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        self.assertEqual(0, result.returncode)
        self.assertEqual("16384", out.read_text().strip())

    def test_on_spawn_fires_once_while_the_child_is_running(self) -> None:
        running: list[bool] = []

        def spawned(group: supervise.Group) -> None:
            running.append(group.running())

        result = supervise.run(
            [sys.executable, "-c", "import time; time.sleep(0.5)"],
            input="",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            on_spawn=spawned,
        )
        self.assertEqual(0, result.returncode)
        self.assertEqual([True], running)

    def test_a_nonzero_exit_is_returned_rather_than_raised(self) -> None:
        result = supervise.run(
            [sys.executable, "-c", "raise SystemExit(3)"],
            input="",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        self.assertEqual(3, result.returncode)

    def test_a_failing_on_spawn_still_kills_and_reaps_the_child(self) -> None:
        seen: list[supervise.Group] = []

        def spawned(group: supervise.Group) -> None:
            seen.append(group)
            raise RuntimeError("the job could not be told")

        with self.assertRaises(RuntimeError):
            supervise.run(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                input="",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                on_spawn=spawned,
            )
        self.assertFalse(seen[0].running())
        self.assertEqual(frozenset(), supervise.live())

    def test_shutdown_kills_every_running_supervised_child(self) -> None:
        pid_file = self.home / "grandchild.pid"
        spawned = threading.Event()
        results: list[Any] = []

        def call() -> None:
            results.append(
                supervise.run(
                    [sys.executable, "-c", _SPAWNS_A_GRANDCHILD, str(pid_file)],
                    input="",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                    on_spawn=lambda _group: spawned.set(),
                )
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        self.assertTrue(spawned.wait(10))
        grandchild = self._grandchild(pid_file)
        self.assertEqual(1, len(supervise.live()))
        supervise.kill_all()
        worker.join(timeout=15)
        self.assertFalse(worker.is_alive(), "a killed child left its caller waiting")
        self.assertNotEqual(0, results[0].returncode)
        self.assertTrue(_wait_until(lambda: not process_alive(grandchild)))
        self.assertEqual(frozenset(), supervise.live())

    # Correction round (review F2): nothing spawns once shutdown has begun.

    def test_a_spawn_after_shutdown_is_refused_and_starts_nothing(self) -> None:
        supervise.kill_all()
        self.assertTrue(supervise.closed())
        with (
            mock.patch.object(subprocess, "Popen") as popen,
            self.assertRaises(supervise.ClosedError),
        ):
            supervise.run([sys.executable, "-c", "pass"], input="", timeout=5)
        popen.assert_not_called()
        self.assertIsInstance(supervise.ClosedError(), OSError)

    def test_a_shutdown_that_meets_a_spawn_in_progress_waits_for_it_and_kills_it(self) -> None:
        """The interleaving the review measured: spawned, not yet registered, then shutdown."""
        spawned, go = threading.Event(), threading.Event()
        real = subprocess.Popen
        results: list[Any] = []

        def slow_popen(*args: Any, **kwargs: Any) -> Any:
            process = real(*args, **kwargs)
            spawned.set()
            go.wait(10)
            return process

        def call() -> None:
            results.append(
                supervise.run(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    input="",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                )
            )

        with mock.patch.object(subprocess, "Popen", slow_popen):
            worker = threading.Thread(target=call, daemon=True)
            worker.start()
            self.assertTrue(spawned.wait(10))
            shutdown = threading.Thread(target=supervise.kill_all, daemon=True)
            shutdown.start()
            shutdown.join(0.3)
            self.assertTrue(shutdown.is_alive(), "shutdown snapshotted before the spawn registered")
            go.set()
            shutdown.join(10)
            worker.join(15)
        self.assertFalse(worker.is_alive(), "the child spawned during shutdown outlived it")
        self.assertNotEqual(0, results[0].returncode)

    # Correction round (review F7): never a bare group signal after the leader is reaped.

    @unittest.skipIf(sys.platform == "win32", "process groups are POSIX")
    def test_the_group_is_only_ever_signalled_while_its_leader_is_unreaped(self) -> None:
        groups: list[supervise.Group] = []
        reaped_at_kill: list[bool] = []
        real_killpg = os.killpg

        def killpg(pgid: int, sig: int) -> None:
            reaped_at_kill.append(groups[0]._process.returncode is not None)
            real_killpg(pgid, sig)

        for script, timeout in (("pass", 30.0), ("import time; time.sleep(60)", 1.0)):
            with self.subTest(script=script):
                groups.clear()
                reaped_at_kill.clear()
                with (
                    mock.patch.object(os, "killpg", killpg),
                    contextlib.suppress(subprocess.TimeoutExpired),
                ):
                    supervise.run(
                        [sys.executable, "-c", script],
                        input="",
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=timeout,
                        on_spawn=groups.append,
                    )
                self.assertTrue(reaped_at_kill, "no sweep ran, so this proved nothing")
                self.assertEqual([False] * len(reaped_at_kill), reaped_at_kill)
                self.assertIsNotNone(groups[0]._process.returncode)

    @unittest.skipIf(sys.platform == "win32", "reaping is a POSIX hazard")
    def test_asking_whether_a_group_runs_does_not_reap_its_leader(self) -> None:
        process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        self.addCleanup(process.wait)
        group = supervise.Group(process)
        self.assertTrue(_wait_until(lambda: not group.running()))
        self.assertIsNone(process.returncode, "running() reaped the leader")

    # Correction round (codex F6): a kill that fails must not hang the call.

    @unittest.skipIf(sys.platform == "win32", "process groups are POSIX")
    def test_a_kill_that_fails_is_bounded_and_reported_rather_than_waited_on(self) -> None:
        groups: list[supervise.Group] = []
        started = time.monotonic()
        with (
            mock.patch.object(os, "killpg", side_effect=PermissionError(1, "denied")),
            mock.patch.object(supervise, "REAP_TIMEOUT_SEC", 1.0),
            self.assertRaises(supervise.UnstoppedError),
        ):
            supervise.run(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                input="",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1,
                on_spawn=groups.append,
            )
        self.assertLess(time.monotonic() - started, 15)
        process = groups[0]._process
        process.kill()
        process.wait()
        self.assertTrue(issubclass(supervise.UnstoppedError, subprocess.SubprocessError))

    @unittest.skipIf(sys.platform == "win32", "process groups are POSIX")
    def test_a_group_already_gone_is_told_apart_from_a_failed_kill(self) -> None:
        with mock.patch.object(os, "killpg", side_effect=ProcessLookupError()):
            self.assertTrue(supervise.kill_group(99_999))
        with mock.patch.object(os, "killpg", side_effect=PermissionError()):
            self.assertFalse(supervise.kill_group(99_999))

    # Correction round (review F6): the limit of a process group, documented.

    @unittest.skipIf(sys.platform == "win32", "a Job Object has no such exit")
    def test_a_helper_that_leaves_the_group_is_not_reached(self) -> None:
        """The documented limit: SECURITY.md and COMPATIBILITY.md name it.

        A helper that calls `setsid` leads a session of its own, so the kill
        that ends the CLI's group cannot reach it. If this ever fails, the
        runner contains more than the docs say, and they can be widened.
        """
        pid_file = self.home / "escaped.pid"
        escapes = (
            "import os, subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],"
            " start_new_session=True)\n"
            "open(sys.argv[1], 'w').write(str(child.pid))\n"
            "time.sleep(60)\n"
        )
        with self.assertRaises(subprocess.TimeoutExpired):
            supervise.run(
                [sys.executable, "-c", escapes, str(pid_file)],
                input="",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        escaped = self._grandchild(pid_file)
        try:
            self.assertTrue(process_alive(escaped))
        finally:
            with contextlib.suppress(OSError):
                os.kill(escaped, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
