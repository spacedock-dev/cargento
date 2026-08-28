"""The end-of-session git probe: what it runs, what it refuses to do, what it publishes.

The two behavioural tests here are DEC-3's measurement turned into an oracle. They
build real repositories and run the real `git`, because the hazards both flags
disarm are properties of git rather than of this module, and a mocked runner
cannot observe either one.
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

from cargento_runtime import git_status

GIT = shutil.which("git")


def _run(*argv: str, cwd: Path) -> None:
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True)


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
        hook.write_text(f'#!/bin/sh\necho ran >> "{fsmonitor_log}"\nexit 1\n')
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
            root = _repo(Path(tmp))
            index = root / ".git" / "index"
            before = index.stat().st_mtime_ns
            git_status.probe(str(root), timeout_sec=10.0)
            self.assertEqual(before, index.stat().st_mtime_ns)

    def test_the_probe_does_not_execute_a_repository_supplied_script(self) -> None:
        # `-c core.fsmonitor=` is what stops this. Without it a script named by
        # the inspected repository's own `.git/config` runs under Cargento's
        # identity — arbitrary execution sourced from the directory being read.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            log = Path(tmp) / "fsmonitor.log"
            _repo(root, fsmonitor_log=log)
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
