"""Tests for deterministic installer release assets."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/build_release_assets.py"


class BuildReleaseAssetsTests(unittest.TestCase):
    def build(self, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--tag",
                "v1.2.3",
                "--output-dir",
                str(output),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_builds_deterministic_self_consistent_release_assets(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="cargento-assets-a-") as first_dir,
            tempfile.TemporaryDirectory(prefix="cargento-assets-b-") as second_dir,
        ):
            first = Path(first_dir)
            second = Path(second_dir)

            first_result = self.build(first)
            second_result = self.build(second)

            archive_name = "cargento-runtime-1.2.3.tar.gz"
            archive = first / archive_name
            checksum = first / f"{archive_name}.sha256"
            installer = first / "install.sh"
            built = first_result.returncode == 0 and second_result.returncode == 0
            first_bytes = archive.read_bytes() if built else b""
            second_bytes = (second / archive_name).read_bytes() if built else b"missing"
            digest = hashlib.sha256(first_bytes).hexdigest()
            installer_body = installer.read_text() if built else ""
            if built:
                with tarfile.open(archive, "r:gz") as bundle:
                    names = bundle.getnames()
            else:
                names = []
            self.assertEqual(
                (
                    first_result.returncode,
                    second_result.returncode,
                    first_bytes == second_bytes,
                    checksum.read_text() if built else "",
                    bool(installer.stat().st_mode & 0o111) if built else False,
                    "v1.2.3" in installer_body,
                    archive_name in installer_body,
                    (
                        "https://github.com/spacedock-dev/cargento/releases/download/v1.2.3"
                        in installer_body
                    ),
                    "cargento/skills/cargento/server.py" in names,
                    "cargento/.claude-plugin/plugin.json" in names,
                ),
                (
                    0,
                    0,
                    True,
                    f"{digest}  {archive_name}\n",
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                ),
                first_result.stderr or second_result.stderr,
            )

    def test_rejects_non_semver_tag_without_writing_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-assets-invalid-") as directory:
            output = Path(directory)

            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--tag",
                    "latest",
                    "--output-dir",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                (
                    result.returncode != 0,
                    "strict semver" in result.stderr,
                    list(output.iterdir()),
                ),
                (True, True, []),
            )

    def test_ci_builds_and_tests_installer_assets_without_renaming_gates(self) -> None:
        release_workflow = (ROOT / ".github/workflows/release.yml").read_text()
        quality_workflow = (ROOT / ".github/workflows/quality-gate.yml").read_text()
        validate_workflow = (ROOT / ".github/workflows/validate.yml").read_text()

        self.assertEqual(
            (
                'python3 scripts/build_release_assets.py --tag "$TAG"' in release_workflow,
                'gh release upload "$TAG"' in release_workflow,
                "scripts.tests.test_build_release_assets" in quality_workflow,
                "scripts.tests.test_installer" in quality_workflow,
                "name: quality-gate" in quality_workflow,
                "scripts/tests/test_build_release_assets.py" in validate_workflow,
                "scripts/tests/test_installer.py" in validate_workflow,
                "\n  validate:\n" in validate_workflow,
            ),
            (True, True, True, True, True, True, True, True),
        )
