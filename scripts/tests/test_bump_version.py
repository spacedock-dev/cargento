"""Tests for the release version-bump script."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bump_version


def make_repo(root: Path, version: str = "0.1.0", drift: str | None = None) -> None:
    (root / "cargento/.claude-plugin").mkdir(parents=True)
    (root / "cargento/.codex-plugin").mkdir(parents=True)
    for rel in (
        "cargento/.claude-plugin/plugin.json",
        "cargento/.codex-plugin/plugin.json",
        "cargento/gemini-extension.json",
    ):
        v = drift if drift and rel.endswith("gemini-extension.json") else version
        (root / rel).write_text(
            json.dumps({"name": "cargento", "version": v, "description": "d"}, indent=2) + "\n"
        )


class BumpVersionTests(unittest.TestCase):
    def with_repo(self, **kwargs: Any) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        make_repo(root, **kwargs)
        patches: list[Any] = [
            mock.patch.object(bump_version, "ROOT", root),
            mock.patch.object(bump_version, "TRUTH", root / "cargento/.claude-plugin/plugin.json"),
            mock.patch.object(
                bump_version,
                "MANIFESTS",
                (
                    root / "cargento/.claude-plugin/plugin.json",
                    root / "cargento/.codex-plugin/plugin.json",
                    root / "cargento/gemini-extension.json",
                ),
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return root

    def test_bump_updates_every_owned_field(self) -> None:
        root = self.with_repo(version="0.1.0")

        bump_version.bump("0.2.0")

        for rel in (
            "cargento/.claude-plugin/plugin.json",
            "cargento/.codex-plugin/plugin.json",
            "cargento/gemini-extension.json",
        ):
            self.assertEqual("0.2.0", json.loads((root / rel).read_text())["version"])
        self.assertEqual("0.2.0", bump_version.current_version())

    def test_bump_rejects_equal_and_lower_targets(self) -> None:
        self.with_repo(version="0.2.0")

        for bad in ("0.2.0", "0.1.9", "0.0.1"):
            with self.assertRaises(SystemExit) as ctx:
                bump_version.bump(bad)
            self.assertIn("strictly greater", str(ctx.exception))

    def test_bump_rejects_non_semver(self) -> None:
        self.with_repo(version="0.1.0")

        for bad in ("v0.2.0", "0.2", "0.02.0", "1.0.0-rc1", "1.0.0.0"):
            with self.assertRaises(SystemExit):
                bump_version.bump(bad)

    def test_numeric_not_lexicographic_comparison(self) -> None:
        root = self.with_repo(version="0.9.0")

        bump_version.bump("0.10.0")

        self.assertEqual("0.10.0", bump_version.current_version())
        del root

    def test_current_version_rejects_parity_drift(self) -> None:
        self.with_repo(version="0.1.0", drift="0.1.1")

        with self.assertRaises(SystemExit) as ctx:
            bump_version.current_version()
        self.assertIn("parity", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


class ManifestPathsTest(unittest.TestCase):
    """`--paths` exists so the Release workflow stops restating this list.

    It was restated, and it drifted the moment the Gemini manifest moved out of the
    plugin root. The bump succeeded, `validate_plugins.py` passed, and then
    `git add` failed on `cargento/gemini-extension.json`, which no longer existed.
    That took the release down after the version fields had already been rewritten,
    which is the worst point in the run to fail at: nothing was pushed, but the tag
    had been created and release tags are immutable.
    """

    def test_paths_prints_every_owned_manifest_repo_relative(self) -> None:
        with mock.patch.object(sys, "stdout", new_callable=_Capture) as out:
            self.assertEqual(0, bump_version.main(["--paths"]))
        printed = out.text().split()
        expected = [
            path.relative_to(bump_version.ROOT).as_posix() for path in bump_version.MANIFESTS
        ]
        self.assertEqual(expected, printed)
        self.assertEqual(3, len(printed), "three manifests carry the version field")

    def test_every_printed_path_exists(self) -> None:
        # The failure mode this guards is a path that is listed but absent, which is
        # exactly what the workflow hit.
        for path in bump_version.MANIFESTS:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"{path} is listed but missing")

    def test_the_release_workflow_derives_the_paths_rather_than_restating_them(self) -> None:
        """The guard that would have caught the outage.

        A literal manifest path inside the workflow's staging step is the drift that
        broke v0.7.0. Deriving them means the workflow cannot disagree with the
        script that rewrites them.
        """
        workflow = (bump_version.ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("bump_version.py --paths", workflow)
        staged = [line for line in workflow.splitlines() if line.strip().startswith("git add")]
        self.assertEqual(1, len(staged), "one staging step")
        for path in bump_version.MANIFESTS:
            with self.subTest(path=path.name):
                self.assertNotIn(
                    path.relative_to(bump_version.ROOT).as_posix(),
                    staged[0],
                    "stage the derived list, not a literal path",
                )


class _Capture:
    """Minimal stdout stand-in; `io.StringIO` would need a `flush` on some paths."""

    def __init__(self) -> None:
        self._chunks: list[str] = []

    def write(self, chunk: str) -> int:
        self._chunks.append(chunk)
        return len(chunk)

    def flush(self) -> None:
        return None

    def text(self) -> str:
        return "".join(self._chunks)
