"""The post-bump archive proof stops a bad release before `stable` can move.

Each failing case builds the commit a real release could have produced and runs
the proof against its `git archive`, so a check that only looked at the working
tree would pass where the shipped bytes do not.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_transition as rt
import verify_release_archive as vra

if TYPE_CHECKING:
    from tests.release_fixture import MANIFESTS, WEB, Fixture, git
else:
    from release_fixture import MANIFESTS, WEB, Fixture, git

BUNDLE = f"{WEB}/react.html"
RUNTIME_FILE = "cargento/skills/cargento/cargento_runtime/http_api.py"


class ArchiveProofTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture(self)
        self.verified = self.fx.commit("feat: work")

    def bumped(self, version: str = "0.2.0") -> str:
        rt.bump(self.fx.work, version)
        return rt.commit_bump(self.fx.work, f"v{version}")

    def prove(self, commit: str, version: str = "0.2.0", verified: str | None = None) -> None:
        vra.verify_archive(self.fx.work, commit, verified or self.verified, version)

    def rejected(self, commit: str, needle: str, version: str = "0.2.0") -> None:
        with self.assertRaises(vra.ArchiveError) as caught:
            self.prove(commit, version)
        self.assertIn(needle, str(caught.exception))

    def test_the_real_bump_commit_passes_every_check(self) -> None:
        report = vra.verify_archive(self.fx.work, self.bumped(), self.verified, "0.2.0")
        self.assertEqual(
            ["versions", "changes", "bundle", "inventory", "page", "launch"],
            list(report.checks),
        )

    def test_a_resumed_release_is_proven_against_itself(self) -> None:
        self.prove(self.verified, version="0.1.0")

    def test_the_proof_reads_the_commit_not_the_working_tree(self) -> None:
        final = self.bumped()
        (self.fx.work / BUNDLE).write_text("<!doctype html>\n", encoding="utf-8")
        self.prove(final)

    def test_a_bundle_changed_after_verification_is_refused(self) -> None:
        rt.bump(self.fx.work, "0.2.0")
        (self.fx.work / BUNDLE).write_bytes((self.fx.work / BUNDLE).read_bytes() + b"<!-- x -->\n")
        git(self.fx.work, "add", "-A")
        git(self.fx.work, "commit", "-q", "-m", "chore(release): v0.2.0 plus a rebuilt bundle")
        self.rejected(git(self.fx.work, "rev-parse", "HEAD"), "changed")

    def test_a_tampered_bundle_verified_and_final_alike_fails_the_integrity_check(self) -> None:
        self.fx.commit("fix: tamper", files={BUNDLE: "<!doctype html>\n"})
        tampered = git(self.fx.work, "rev-parse", "HEAD")
        rt.bump(self.fx.work, "0.2.0")
        final = rt.commit_bump(self.fx.work, "v0.2.0")
        with self.assertRaises(vra.ArchiveError) as caught:
            vra.verify_archive(self.fx.work, final, tampered, "0.2.0")
        self.assertIn("integrity", str(caught.exception))

    def test_a_wrong_version_is_refused(self) -> None:
        final = self.bumped("0.2.0")
        self.rejected(final, "0.3.0", version="0.3.0")

    def test_a_partial_bump_is_refused_as_version_drift(self) -> None:
        path = self.fx.work / MANIFESTS[0]
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = "0.2.0"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        git(self.fx.work, "add", "-A")
        git(self.fx.work, "commit", "-q", "-m", "chore(release): v0.2.0")
        self.rejected(git(self.fx.work, "rev-parse", "HEAD"), "parity")

    def test_a_missing_runtime_file_is_refused(self) -> None:
        git(self.fx.work, "rm", "-q", RUNTIME_FILE)
        git(self.fx.work, "commit", "-q", "-m", "fix: drop a module")
        broken = git(self.fx.work, "rev-parse", "HEAD")
        rt.bump(self.fx.work, "0.2.0")
        final = rt.commit_bump(self.fx.work, "v0.2.0")
        with self.assertRaises(vra.ArchiveError) as caught:
            vra.verify_archive(self.fx.work, final, broken, "0.2.0")
        self.assertIn("http_api.py", str(caught.exception))

    def test_a_release_commit_that_changes_anything_but_the_manifests_is_refused(self) -> None:
        rt.bump(self.fx.work, "0.2.0")
        (self.fx.work / "README.md").write_text("changed in the release commit\n", encoding="utf-8")
        git(self.fx.work, "add", "-A")
        git(self.fx.work, "commit", "-q", "-m", "chore(release): v0.2.0")
        self.rejected(git(self.fx.work, "rev-parse", "HEAD"), "README.md")

    def test_a_scratch_directory_never_outlives_the_proof(self) -> None:
        final = self.bumped()
        created: list[str] = []
        real = tempfile.mkdtemp

        def spy(*args: object, **kwargs: object) -> str:
            path = real(*args, **kwargs)  # type: ignore[call-overload]
            created.append(path)
            return str(path)

        with mock.patch.object(tempfile, "mkdtemp", spy):
            self.prove(final)
        self.assertTrue(created)
        self.assertFalse([path for path in created if Path(path).exists()])


class IsolationTest(unittest.TestCase):
    def test_the_smoke_environment_carries_no_ambient_state(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            planted = {
                "GITHUB_TOKEN": "x",
                "RELEASE_DEPLOY_KEY": "x",
                "SSH_AUTH_SOCK": "/tmp/agent",
                "NODE_OPTIONS": "--require /tmp/x",
                "PYTHONPATH": "/tmp/x",
                "HOME": "/Users/someone",
            }
            with mock.patch.dict(os.environ, planted):
                env = vra.isolated_env(Path(home))
            self.assertEqual(
                {"PATH", "HOME", "USERPROFILE", "CARGENTO_HOME", "PYTHONNOUSERSITE", "LC_ALL"},
                set(env),
            )
            self.assertEqual(home, env["HOME"])
            self.assertTrue(env["CARGENTO_HOME"].startswith(home))
            path = Path(env["PATH"])
            self.assertTrue(path.is_dir())
            self.assertEqual([], list(path.iterdir()), "no executable, so no Node, is reachable")

    def test_the_interpreter_runs_isolated_from_site_and_environment(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(["-I"], vra.PAGE_FLAGS)
            self.assertEqual(["-E", "-s"], vra.LAUNCH_FLAGS)
            result = vra.run_python(
                Path(home), ["-I", "-c", "import sys; print(sys.flags.isolated)"]
            )
            self.assertEqual("1", result.stdout.strip())


class ExtractionTest(unittest.TestCase):
    def archive(self, names: list[str], *, link: tuple[str, str] | None = None) -> Path:
        handle, name = tempfile.mkstemp(suffix=".tar")
        os.close(handle)
        self.addCleanup(Path(name).unlink)
        with tarfile.open(name, "w") as tar:
            for member in names:
                info = tarfile.TarInfo(member)
                data = b"x"
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            if link:
                info = tarfile.TarInfo(link[0])
                info.type = tarfile.SYMTYPE
                info.linkname = link[1]
                tar.addfile(info)
        return Path(name)

    def test_members_that_escape_the_destination_are_refused(self) -> None:
        for names in (["../evil"], ["/abs/evil"], ["ok", "a/../../evil"]):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as dest:
                with self.assertRaises(vra.ArchiveError):
                    vra.extract_archive(self.archive(names), Path(dest))
                self.assertEqual([], list(Path(dest).iterdir()))

    def test_links_that_leave_the_tree_are_refused(self) -> None:
        for target in ("/etc/passwd", "../../outside", "a/../../outside"):
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as dest,
                self.assertRaises(vra.ArchiveError),
            ):
                vra.extract_archive(self.archive(["ok"], link=("escape", target)), Path(dest))

    def test_a_link_that_stays_inside_the_tree_extracts(self) -> None:
        with tempfile.TemporaryDirectory() as dest:
            vra.extract_archive(self.archive(["dir/real"], link=("dir/alias", "real")), Path(dest))
            self.assertEqual(b"x", (Path(dest) / "dir/alias").read_bytes())

    def test_ordinary_members_extract(self) -> None:
        with tempfile.TemporaryDirectory() as dest:
            vra.extract_archive(self.archive(["a/b.txt"]), Path(dest))
            self.assertEqual(b"x", (Path(dest) / "a/b.txt").read_bytes())


if __name__ == "__main__":
    unittest.main()
