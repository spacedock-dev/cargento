#!/usr/bin/env python3
"""Tests for the release version-bump script."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bump_version  # noqa: E402


def make_repo(root: Path, version: str = "0.1.0", drift: str | None = None) -> None:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / "cargento/.claude-plugin").mkdir(parents=True)
    (root / "cargento/.codex-plugin").mkdir(parents=True)
    (root / ".claude-plugin/marketplace.json").write_text(json.dumps({
        "name": "cargento-marketplace",
        "metadata": {"description": "d", "version": version},
        "plugins": [{"name": "cargento", "source": "./cargento", "version": version}],
    }, indent=2) + "\n")
    for rel in ("cargento/.claude-plugin/plugin.json",
                "cargento/.codex-plugin/plugin.json",
                "cargento/gemini-extension.json"):
        v = drift if drift and rel.endswith("gemini-extension.json") else version
        (root / rel).write_text(json.dumps(
            {"name": "cargento", "version": v, "description": "d"}, indent=2
        ) + "\n")


class BumpVersionTests(unittest.TestCase):
    def with_repo(self, **kwargs) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        make_repo(root, **kwargs)
        patches = [
            mock.patch.object(bump_version, "ROOT", root),
            mock.patch.object(
                bump_version, "MARKETPLACE", root / ".claude-plugin/marketplace.json"
            ),
            mock.patch.object(bump_version, "MANIFESTS", (
                root / "cargento/.claude-plugin/plugin.json",
                root / "cargento/.codex-plugin/plugin.json",
                root / "cargento/gemini-extension.json",
            )),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return root

    def test_bump_updates_all_five_fields(self) -> None:
        root = self.with_repo(version="0.1.0")

        bump_version.bump("0.2.0")

        marketplace = json.loads((root / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual("0.2.0", marketplace["metadata"]["version"])
        self.assertEqual("0.2.0", marketplace["plugins"][0]["version"])
        for rel in ("cargento/.claude-plugin/plugin.json",
                    "cargento/.codex-plugin/plugin.json",
                    "cargento/gemini-extension.json"):
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
