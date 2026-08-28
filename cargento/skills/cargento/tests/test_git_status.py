"""The end-of-session git probe: what it runs, what it refuses to do, what it publishes.

The two behavioural tests here are DEC-3's measurement turned into an oracle. They
build real repositories and run the real `git`, because the hazards both flags
disarm are properties of git rather than of this module, and a mocked runner
cannot observe either one.

Each of those two runs a POSITIVE CONTROL first: the same command with the one
flag removed, in its own repository, which must exhibit the hazard. Without it
neither test can tell "the flag worked" from "the mechanism was never armed
here", and both were vacuous on at least one supported platform — the fsmonitor
script was written with `Path.write_text`, whose default newline translation
makes the shebang `#!/bin/sh\r` on Windows, where `chmod(S_IEXEC)` is a no-op
besides; and the index test is equally vulnerable on a filesystem whose mtime
granularity is coarser than git's racy window. A mechanism the control cannot
arm now skips with its reason rather than passing.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cargento_runtime import git_status

GIT = shutil.which("git")

# The two positive controls. Written as literals rather than filtered out of
# `GIT_STATUS_ARGV`, so a change to that constant cannot quietly turn a control
# into a second copy of the probe and make the hazard test pass by agreement.
WITHOUT_NO_OPTIONAL_LOCKS = ("git", "-c", "core.fsmonitor=", "status", "--porcelain")
WITHOUT_FSMONITOR_OFF = ("git", "--no-optional-locks", "status", "--porcelain")


def _run(*argv: str, cwd: Path) -> None:
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True)


def _fresh(parent: Path, name: str, *, fsmonitor_log: Path | None = None) -> Path:
    """A repository of its own under `parent`.

    Every hazard test needs two — one for the control and one for the probe —
    and they must not share a `.git`, because the control's run is exactly the
    write or the execution the probe's repository must not have seen.
    """
    root = parent / name
    root.mkdir(parents=True)
    return _repo(root, fsmonitor_log=fsmonitor_log)


def _repo(root: Path, *, fsmonitor_log: Path | None = None) -> Path:
    """A repository in the racy-clean state the hazards need.

    The rewrite with identical content is the point: it leaves the file's mtime
    inside git's racy window without changing the tree, which is the state a
    repository a live session is editing is normally in.
    """
    _run("git", "init", "-q", cwd=root)
    _run("git", "config", "user.email", "probe@example.invalid", cwd=root)
    _run("git", "config", "user.name", "Probe", cwd=root)
    (root / "a.txt").write_text("one\n")
    _run("git", "add", "a.txt", cwd=root)
    _run("git", "commit", "-q", "-m", "one", cwd=root)
    if fsmonitor_log is not None:
        hook = root / "fsmonitor.sh"
        # newline="" so the shebang stays `#!/bin/sh` on Windows too. The default
        # translation writes `#!/bin/sh\r`, which no shell honours, and the test
        # that reads the log then passes for a reason that is not the flag.
        hook.write_text(f'#!/bin/sh\necho ran >> "{fsmonitor_log}"\nexit 1\n', newline="")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
        _run("git", "config", "core.fsmonitor", str(hook), cwd=root)
    # Rewrite with identical content, so the tree is clean and the stat is racy.
    time.sleep(0.01)
    (root / "a.txt").write_text("one\n")
    return root


@unittest.skipIf(GIT is None, "git is not on PATH")
class GitProbeContractTest(unittest.TestCase):
    """AC1 and AC2: one argv, and a probe that neither writes nor executes."""

    def test_the_probe_is_exactly_the_one_bounded_command(self) -> None:
        # Bound 1 of DEC-3, as amended: this literal, or there is no probe. Both
        # flags are independently load-bearing (see the two tests below), so this
        # asserts the whole argv rather than membership of either flag.
        self.assertEqual(
            (
                "git",
                "-c",
                "core.fsmonitor=",
                "--no-optional-locks",
                "status",
                "--porcelain",
            ),
            git_status.GIT_STATUS_ARGV,
        )

    def test_the_probe_does_not_write_the_index(self) -> None:
        # `--no-optional-locks` is what stops this. Without it git resolves the
        # racy stat by rewriting `.git/index`, which breaks the read-only posture
        # SECURITY.md states for everything Cargento touches.
        with tempfile.TemporaryDirectory() as tmp:
            control = _fresh(Path(tmp), "control")
            control_index = control / ".git" / "index"
            control_before = control_index.stat().st_mtime_ns
            subprocess.run(WITHOUT_NO_OPTIONAL_LOCKS, cwd=control, check=False, capture_output=True)
            if control_index.stat().st_mtime_ns == control_before:
                # The write this test exists to prevent did not happen even with
                # the flag removed, so passing below would say nothing. Coarse
                # mtime granularity relative to git's racy window is the way this
                # is reached, and a silent pass is exactly the vacuity R7 named.
                self.skipTest("git did not rewrite the index without --no-optional-locks")
            root = _fresh(Path(tmp), "probed")
            index = root / ".git" / "index"
            before = index.stat().st_mtime_ns
            git_status.probe(str(root), timeout_sec=10.0)
            self.assertEqual(before, index.stat().st_mtime_ns)

    def test_the_probe_does_not_execute_a_repository_supplied_script(self) -> None:
        # `-c core.fsmonitor=` is what stops this. Without it a script named by
        # the inspected repository's own `.git/config` runs under Cargento's
        # identity — arbitrary execution sourced from the directory being read.
        with tempfile.TemporaryDirectory() as tmp:
            control_log = Path(tmp) / "control.log"
            control = _fresh(Path(tmp), "control", fsmonitor_log=control_log)
            subprocess.run(WITHOUT_FSMONITOR_OFF, cwd=control, check=False, capture_output=True)
            if not control_log.exists():
                # The mechanism could not be armed on this host, so an empty log
                # below would prove nothing about the flag. Git for Windows is
                # the case in hand: no exec bit and a shell that may decline the
                # script outright.
                self.skipTest("git did not run the repository's fsmonitor without -c fsmonitor=")
            log = Path(tmp) / "fsmonitor.log"
            root = _fresh(Path(tmp), "probed", fsmonitor_log=log)
            git_status.probe(str(root), timeout_sec=10.0)
            self.assertFalse(log.exists(), "the repository's fsmonitor script ran")


@unittest.skipIf(GIT is None, "git is not on PATH")
class SingleInvocationTest(unittest.TestCase):
    """AC1's other half: the runtime builds a git subprocess at exactly one site.

    Before this feature that count was zero — a grep for git across
    `cargento_runtime/` returned nothing — so "exactly one" is a baseline this
    test establishes rather than an assumption it inherits. The likely second site
    is a `rev-parse` to answer "is this a repository?", and it must be folded into
    the one invocation instead: a non-repository is already distinguishable from
    the single command's exit status.
    """

    def test_only_git_status_constructs_a_git_subprocess(self) -> None:
        runtime = Path(__file__).resolve().parent.parent / "cargento_runtime"
        pattern = re.compile(r"""["']git["']""")
        offenders = sorted(
            path.name
            for path in runtime.rglob("*.py")
            if pattern.search(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(["git_status.py"], offenders)

    def test_the_argv_is_a_tuple_a_caller_cannot_extend(self) -> None:
        # A list would let a caller append to the argv it was handed, which is the
        # cheapest way a second flag or a pathspec reaches the one bounded command.
        self.assertIsInstance(git_status.GIT_STATUS_ARGV, tuple)


# `_repo` runs `git init` with `check=True`, so without this guard these two
# ERROR rather than skip where git is absent, which AC2 forbids in as many words.
# Measured with PATH pointed at a shim: 2 errors, 5 skips.
@unittest.skipIf(GIT is None, "git is not on PATH")
class GitProbeReadingTest(unittest.TestCase):
    """What the two published scalars actually mean."""

    def test_a_clean_tree_reads_clean_with_no_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _repo(Path(tmp))
            result = git_status.probe(str(root), timeout_sec=10.0)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertFalse(result.dirty)
            self.assertEqual(0, result.changed)

    def test_changed_counts_porcelain_entries_rather_than_files(self) -> None:
        # The measured case from triage: one modified tracked file plus an
        # untracked directory holding three files is 2 entries for 4 changed
        # files, because git collapses the untracked directory into one entry.
        # Publishing 4 here would be a file count wearing an entry count's name.
        with tempfile.TemporaryDirectory() as tmp:
            root = _repo(Path(tmp))
            (root / "a.txt").write_text("two\n")
            nested = root / "new"
            nested.mkdir()
            for name in ("x", "y", "z"):
                (nested / name).write_text("x\n")
            result = git_status.probe(str(root), timeout_sec=10.0)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result.dirty)
            self.assertEqual(2, result.changed)


class GitProbeCallSiteTest(unittest.TestCase):
    """What `probe()` actually hands `runner` — the argv constant proves nothing about it.

    Undecorated on purpose: this needs no git, and the pin must hold on a host
    where the two behavioural tests above skip. Measured before it existed:
    stripping BOTH flags from the `runner(...)` call left
    `test_the_probe_is_exactly_the_one_bounded_command` green, because that test
    reads the constant and nothing read the call.
    """

    def _spy(self) -> tuple[Any, list[tuple[Any, dict[str, Any]]]]:
        seen: list[tuple[Any, dict[str, Any]]] = []

        def runner(argv: Any, **kwargs: Any) -> Any:
            seen.append((argv, kwargs))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        return runner, seen

    def test_the_probe_passes_the_bounded_argv_and_nothing_else(self) -> None:
        runner, seen = self._spy()
        with tempfile.TemporaryDirectory() as tmp:
            # A real directory, because `probe` returns before spawning anything
            # when `isdir` is false — which is how this test would go vacuous.
            git_status.probe(tmp, timeout_sec=3.5, runner=runner)
        self.assertEqual(1, len(seen), "the probe ran other than exactly one command")
        argv, _kwargs = seen[0]
        self.assertEqual(git_status.GIT_STATUS_ARGV, tuple(argv))

    def test_the_probe_passes_the_bounds_the_contract_names(self) -> None:
        # The cwd it was asked about, the caller's timeout, and a closed stdin so
        # a repository configured to ask for a credential cannot stall the probe.
        # No `shell=`, which is AC1's evasion shape the argv assertion cannot see.
        runner, seen = self._spy()
        with tempfile.TemporaryDirectory() as tmp:
            git_status.probe(tmp, timeout_sec=3.5, runner=runner)
        _argv, kwargs = seen[0]
        self.assertEqual(tmp, kwargs["cwd"])
        self.assertEqual(3.5, kwargs["timeout"])
        self.assertEqual(subprocess.DEVNULL, kwargs["stdin"])
        self.assertNotIn("shell", kwargs)


class GitProbeRefusalTest(unittest.TestCase):
    """Every cause of a null, at the module's own boundary."""

    def test_a_directory_that_is_not_a_repository_is_not_probed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(git_status.probe(tmp, timeout_sec=10.0))

    def test_a_missing_directory_is_not_probed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gone = os.path.join(tmp, "nope")
            self.assertIsNone(git_status.probe(gone, timeout_sec=10.0))

    def test_git_absent_from_the_path_is_not_probed(self) -> None:
        def missing(*_args: object, **_kwargs: object) -> object:
            raise FileNotFoundError("git")

        self.assertIsNone(git_status.probe("/tmp", timeout_sec=10.0, runner=missing))

    def test_a_probe_that_timed_out_is_not_probed(self) -> None:
        def slow(*_args: object, **_kwargs: object) -> object:
            raise subprocess.TimeoutExpired(cmd="git", timeout=1.0)

        self.assertIsNone(git_status.probe("/tmp", timeout_sec=1.0, runner=slow))


if __name__ == "__main__":
    unittest.main()
