"""Tests for deterministic installer release assets."""

from __future__ import annotations

import hashlib
import io
import runpy
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/build_release_assets.py"
BUILDER_GLOBALS = runpy.run_path(
    str(BUILDER),
    run_name="cargento_release_asset_builder_test",
)
build_assets = cast(
    "Callable[[str, Path], tuple[Path, Path, Path]]",
    BUILDER_GLOBALS["build_assets"],
)
main = cast("Callable[[], int]", BUILDER_GLOBALS["main"])


class BuildReleaseAssetsTests(unittest.TestCase):
    def build_with_cli(self, output: Path) -> subprocess.CompletedProcess[str]:
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

            first_assets = build_assets("v1.2.3", first)
            second_assets = build_assets("v1.2.3", second)

            archive_name = "cargento-runtime-1.2.3.tar.gz"
            archive = first / archive_name
            checksum = first / f"{archive_name}.sha256"
            installer = first / "install.sh"
            first_bytes = archive.read_bytes()
            second_bytes = (second / archive_name).read_bytes()
            digest = hashlib.sha256(first_bytes).hexdigest()
            installer_body = installer.read_text()
            with tarfile.open(archive, "r:gz") as bundle:
                names = bundle.getnames()
            self.assertEqual(
                (
                    first_assets,
                    second_assets,
                    first_bytes == second_bytes,
                    checksum.read_text(),
                    bool(installer.stat().st_mode & 0o111),
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
                    (installer, archive, checksum),
                    (
                        second / "install.sh",
                        second / archive_name,
                        second / f"{archive_name}.sha256",
                    ),
                    True,
                    f"{digest}  {archive_name}\n",
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                ),
            )

    def test_rejects_non_semver_tag_without_writing_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-assets-invalid-") as directory:
            output = Path(directory)

            try:
                build_assets("latest", output)
            except ValueError as error:
                message = str(error)
            else:
                message = "no error"

            self.assertEqual(
                (
                    "strict semver" in message,
                    list(output.iterdir()),
                ),
                (True, []),
            )

    def test_cli_builds_release_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-assets-cli-") as directory:
            output = Path(directory)

            result = self.build_with_cli(output)

            self.assertEqual(
                (
                    result.returncode,
                    [path.name for path in sorted(output.iterdir())],
                    len(result.stdout.splitlines()),
                ),
                (
                    0,
                    [
                        "cargento-runtime-1.2.3.tar.gz",
                        "cargento-runtime-1.2.3.tar.gz.sha256",
                        "install.sh",
                    ],
                    3,
                ),
                result.stderr,
            )

    def test_main_builds_and_prints_release_assets_in_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-assets-main-") as directory:
            output = Path(directory)
            stdout = io.StringIO()

            with (
                patch.object(
                    sys,
                    "argv",
                    ["build_release_assets.py", "--tag", "v1.2.3", "--output-dir", str(output)],
                ),
                redirect_stdout(stdout),
            ):
                result = main()

            self.assertEqual(
                (
                    result,
                    stdout.getvalue().splitlines(),
                ),
                (
                    0,
                    [
                        str(output / "install.sh"),
                        str(output / "cargento-runtime-1.2.3.tar.gz"),
                        str(output / "cargento-runtime-1.2.3.tar.gz.sha256"),
                    ],
                ),
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
