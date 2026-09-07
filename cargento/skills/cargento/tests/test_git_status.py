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

import contextlib
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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from cargento_runtime import git_status

GIT = shutil.which("git")

# The two positive controls. Written as literals rather than filtered out of
# `GIT_STATUS_ARGV`, so a change to that constant cannot quietly turn a control
# into a second copy of the probe and make the hazard test pass by agreement.
WITHOUT_NO_OPTIONAL_LOCKS = ("git", "-c", "core.fsmonitor=", "status", "--porcelain")
WITHOUT_FSMONITOR_OFF = ("git", "--no-optional-locks", "status", "--porcelain")
# The shipped argv minus the one flag, plus an explicit `core.hooksPath` naming
# the repository's own default. Without that second part the control inherits a
# global override on hosts that set one, its four hooks land outside the sandbox
# the test inspects, and the test skips with a message saying git-lfs installed
# nothing — which would be false, and would leave the flag unguarded there.
WITHOUT_HOOKS_PATH_OFF = (
    "git",
    "-c",
    "core.fsmonitor=",
    "-c",
    "core.hooksPath=.git/hooks",
    "--no-optional-locks",
    "status",
    "--porcelain",
)

LFS = shutil.which("git-lfs")


@contextlib.contextmanager
def _environment(environ: dict[str, str], *, cwd: Path | None = None) -> Iterator[None]:
    """Swap `os.environ`, and optionally the process cwd, for the duration.

    The probe reads neither directly, which is the point: what it must not do is
    hand either to the subprocess it spawns.
    """
    saved_environ = dict(os.environ)
    saved_cwd = Path.cwd()
    os.environ.clear()
    os.environ.update(environ)
    if cwd is not None:
        os.chdir(cwd)
    try:
        yield
    finally:
        os.chdir(saved_cwd)
        os.environ.clear()
        os.environ.update(saved_environ)


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


def _filtered(parent: Path, name: str) -> Path:
    """A repository whose committed attributes route a tracked path through LFS.

    The precondition is not the attribute on its own — that arm installs nothing,
    measured. It is a tracked path matching a filter attribute whose content git
    must hash, so `blob.bin` is committed raw first and then rewritten at the
    SAME SIZE, which leaves the stat racy and forces the clean filter to run.

    Every git call here carries its own `core.hooksPath`, pointed inside the
    temporary directory. Building the repository runs the same filter driver
    through `add` and `commit`, and the driver installs hooks wherever git says
    they belong: on a host whose global config sets `core.hooksPath`, that is a
    directory shared with the operator's real repositories. Without this the
    fixture writes four executables into it and the test then SKIPS, because the
    control's hooks never land in the sandbox it inspects — so the escape and the
    unguarded flag would both be hidden behind a passing suite. The suite has no
    `GIT_CONFIG_GLOBAL` isolation, and it must not have any here: the global
    config is where the git-lfs driver itself comes from, and removing it would
    disarm the mechanism this test exists to observe.
    """
    root = parent / name
    root.mkdir(parents=True)
    sandbox = root / "sandbox-hooks"
    sandbox.mkdir()

    def git(*argv: str) -> None:
        _run("git", "-c", f"core.hooksPath={sandbox}", *argv, cwd=root)

    git("init", "-q")
    git("config", "user.email", "probe@example.invalid")
    git("config", "user.name", "Probe")
    (root / "blob.bin").write_bytes(b"A" * 64)
    git("add", "blob.bin")
    git("commit", "-q", "-m", "raw blob")
    (root / ".gitattributes").write_text("*.bin filter=lfs\n")
    git("add", ".gitattributes")
    git("commit", "-q", "-m", "attributes")
    (root / "blob.bin").write_bytes(b"B" * 64)
    return root


def _installed_hooks(root: Path) -> list[str]:
    """Hook names in the repository, ignoring git's own `.sample` templates."""
    hooks = root / ".git" / "hooks"
    if not hooks.is_dir():
        return []
    return sorted(p.name for p in hooks.iterdir() if not p.name.endswith(".sample"))


def _clear_hooks(root: Path) -> None:
    """Empty the hook directory, so what is found afterwards has one cause.

    Building the repository runs `git add` and `git commit` through the same
    filter driver, and the driver installs its hooks there too. Without this the
    test reads hooks the SETUP wrote and attributes them to the probe, which is
    how it passes with the flag removed and fails with it present.
    """
    hooks = root / ".git" / "hooks"
    if not hooks.is_dir():
        return
    for path in hooks.iterdir():
        if not path.name.endswith(".sample"):
            path.unlink()


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
    """AC1 and AC2: one argv, and the three hazards its flags disarm.

    "Neither writes nor executes" is no longer the whole claim. The probe does not
    write the index and does not run the repository's fsmonitor script, and since
    2026-09-07 it installs no hook either; a filter driver named by the inspected
    repository's own `.git/config` can still run. SECURITY.md owns that residual.
    """

    def test_the_probe_is_exactly_the_one_bounded_command(self) -> None:
        # Bound 1 of DEC-3, as amended: this literal, or there is no probe. All
        # three flags are independently load-bearing (see the three tests below),
        # so this asserts the whole argv rather than membership of any one flag.
        self.assertEqual(
            (
                "git",
                "-c",
                "core.fsmonitor=",
                "-c",
                "core.hooksPath=/dev/null",
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

    @unittest.skipIf(LFS is None, "git-lfs is not on PATH")
    def test_the_probe_does_not_install_a_hook_in_the_repository(self) -> None:
        # `-c core.hooksPath=/dev/null` is what stops this. Without it, hashing a
        # tracked path whose committed attributes name a filter driver lets that
        # driver install its own hooks: measured 2026-09-07 at git 2.55.0 with
        # git-lfs 3.8.0, four files at mode 0755 — post-checkout, post-commit,
        # post-merge and pre-push — written inside a repository the probe was
        # only meant to read. `.git/index` was untouched in both arms, so neither
        # existing flag sees this and neither existing test could have caught it.
        with tempfile.TemporaryDirectory() as tmp:
            control = _filtered(Path(tmp), "control")
            _clear_hooks(control)
            subprocess.run(WITHOUT_HOOKS_PATH_OFF, cwd=control, check=False, capture_output=True)
            if not _installed_hooks(control):
                # The driver installed nothing even with the flag removed, so an
                # empty directory below would prove nothing about the flag. A
                # git-lfs that does not install hooks from the clean filter, or
                # one whose global config names no filter driver, reaches this.
                self.skipTest("git-lfs installed no hook without -c core.hooksPath=")
            root = _filtered(Path(tmp), "probed")
            _clear_hooks(root)
            self.assertEqual([], _installed_hooks(root), "the clear did not take")
            git_status.probe(str(root), timeout_sec=10.0)
            self.assertEqual([], _installed_hooks(root), "a hook was installed in the repository")


@unittest.skipIf(GIT is None, "git is not on PATH")
class GitProbeEnvironmentTest(unittest.TestCase):
    """The reading is about the directory it names, and about no other.

    Both tests here run a POSITIVE CONTROL first, for the same reason the three
    hazard tests above do: without it neither can tell "the scrub worked" from
    "the mechanism was never armed here".
    """

    def test_an_inherited_git_dir_cannot_point_the_reading_elsewhere(self) -> None:
        # R16. Measured before the fix: probe() on a CLEAN repository returned
        # a dirty reading belonging to a different repository, because the
        # subprocess inherited GIT_DIR and GIT_WORK_TREE from the environment.
        # `isdir` does not help — a directory that is not a repository at all
        # returned the other repository's reading too.
        with tempfile.TemporaryDirectory() as tmp:
            outer = _fresh(Path(tmp), "outer")
            (outer / "one.txt").write_text("changed\n")
            (outer / "two.txt").write_text("new\n")
            (outer / "three.txt").write_text("new\n")
            inner = _fresh(Path(tmp), "inner")
            clean = git_status.probe(str(inner), timeout_sec=10.0)
            self.assertEqual(git_status.GitStatus(dirty=False, changed=0), clean)

            environ = {
                **os.environ,
                "GIT_DIR": str(outer / ".git"),
                "GIT_WORK_TREE": str(outer),
            }
            control = subprocess.run(
                git_status.GIT_STATUS_ARGV,
                cwd=inner,
                capture_output=True,
                env=environ,
                check=False,
            )
            leaked = sum(1 for line in control.stdout.split(b"\n") if line.strip())
            if leaked == 0:
                # The environment did not redirect git on this host, so an equal
                # reading below would prove nothing about the scrub.
                self.skipTest("GIT_DIR did not redirect git on this host")

            with _environment(environ):
                self.assertEqual(clean, git_status.probe(str(inner), timeout_sec=10.0))

    def test_a_relative_path_element_cannot_supply_the_executable(self) -> None:
        # R12. The rule is ORDER, not position: ANY empty or relative PATH
        # element before the first element holding a real `git` hijacks. The
        # register and its verifier both stated this wrongly, in opposite
        # directions, because /usr/bin/git exists on macOS and contaminated
        # both readings. The trailing arms are asserted NEGATIVE so this test
        # cannot pass by resolving nothing at all.
        with tempfile.TemporaryDirectory() as tmp:
            probed = Path(tmp) / "probed"
            probed.mkdir()
            fake = probed / "git"
            # Seven entries, a count no real repository here produces, and the
            # probed directory is deliberately NOT a repository so real git
            # returns None and any reading at all means the fake ran.
            fake.write_text(
                '#!/bin/sh\nfor i in 1 2 3 4 5 6 7; do echo " M f$i"; done\n', newline=""
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            git_free = Path(tmp) / "git-free"
            git_free.mkdir()
            real = str(Path(GIT or "/usr/bin/git").parent)

            hijacks = {
                "leading relative": f".:{real}",
                "leading empty": f":{real}",
                "interior empty": f"{git_free}::{real}",
                "interior relative": f"{git_free}:.:{real}",
            }
            harmless = {
                "trailing empty": f"{real}:",
                "trailing relative": f"{real}:.",
                "unmodified": real,
            }
            armed = False
            for label, path in hijacks.items():
                with self.subTest(arm=label):
                    with _environment({**os.environ, "PATH": path}, cwd=probed):
                        reading = git_status.probe(str(probed), timeout_sec=10.0)
                    if reading is not None and reading.changed == 7:
                        armed = True
                    self.assertNotEqual(
                        7,
                        getattr(reading, "changed", None),
                        f"the probed directory's own `git` supplied the executable ({label})",
                    )
            if not armed:
                # Nothing to prove if no arm could hijack even before the fix.
                # Recorded rather than passed silently, per this file's rule.
                self.skipTest("no PATH shape hijacked on this host")
            for label, path in harmless.items():
                with (
                    self.subTest(arm=label),
                    _environment({**os.environ, "PATH": path}, cwd=probed),
                ):
                    self.assertIsNone(git_status.probe(str(probed), timeout_sec=10.0))


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
# Measured with PATH pointed at a shim: 2 errors, 6 skips. The sixth arrived
# with the hook test, which skips on a host with no git-lfs.
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
    where the three behavioural tests above skip. Measured before it existed:
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
        # argv[0] is the RESOLVED path, not the bare name the constant prints.
        # Asserting absoluteness is the point: a bare name is resolved by the
        # child against a PATH the probe does not control, and that is how an
        # empty or relative element ahead of the first real `git` supplied the
        # binary from the session's own directory.
        self.assertTrue(os.path.isabs(argv[0]), f"argv[0] is not an absolute path: {argv[0]!r}")
        self.assertEqual("git", Path(argv[0]).stem)
        # Everything after argv[0] is the constant, unchanged.
        self.assertEqual(git_status.GIT_STATUS_ARGV[1:], tuple(argv[1:]))

    def test_the_probe_scrubs_the_environment_it_hands_the_child(self) -> None:
        # The scrub is asserted here as well as behaviourally above, because this
        # one runs on a host with no git and pins the exact keys.
        runner, seen = self._spy()
        hostile = {
            **os.environ,
            "GIT_DIR": "/elsewhere/.git",
            "GIT_WORK_TREE": "/elsewhere",
        }
        with tempfile.TemporaryDirectory() as tmp, _environment(hostile):
            git_status.probe(tmp, timeout_sec=3.5, runner=runner)
        _argv, kwargs = seen[0]
        self.assertNotIn("GIT_DIR", kwargs["env"])
        self.assertNotIn("GIT_WORK_TREE", kwargs["env"])
        # And the child gets an environment at all, rather than inheriting.
        self.assertIsNotNone(kwargs.get("env"))

    def test_the_scrub_drops_relative_and_empty_path_elements(self) -> None:
        # A unit assertion on the helper, so the rule is stated once where it can
        # be read: ORDER is what matters, and dropping is what makes order safe.
        scrubbed = git_status.probe_environment(
            {"PATH": f".{os.pathsep}{os.pathsep}/usr/bin{os.pathsep}.{os.pathsep}/bin"}
        )
        self.assertEqual(f"/usr/bin{os.pathsep}/bin", scrubbed["PATH"])
        # An entirely untrusted PATH leaves nothing, and `which` then finds no
        # git, which publishes None rather than falling back to the ambient PATH.
        self.assertEqual("", git_status.probe_environment({"PATH": f".{os.pathsep}"})["PATH"])

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
