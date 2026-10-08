"""The required gate measures frontend changes and cannot hide a failed matrix."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

import yaml

from . import test_quality_gate as detector

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/quality-gate.yml"


def jobs() -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(WORKFLOW.read_text())["jobs"])


@unittest.skipUnless(detector.BASH, "the shipped gate uses Bash")
class FrontendDetectorControlsTest(unittest.TestCase):
    def test_sources_builds_and_relevant_workflows_request_measurable_jobs(self) -> None:
        probe = detector.QualityGateDetectorTest()
        for path in (
            "frontend/src/main.tsx",
            "frontend/test/setup.ts",
            "pnpm-lock.yaml",
            "pnpm-workspace.yaml",
            ".node-version",
            ".npmrc",
            "package.json",
            "eslint.config.mjs",
            "frontend/vite.config.mts",
            "scripts/build_frontend.mjs",
            "cargento/skills/cargento/cargento_runtime/web/react.html",
            ".github/workflows/release.yml",
            ".github/workflows/release.yaml",
            ".github/workflows/frontend-build.yml",
            ".github/workflows/frontend-build.yaml",
            ".github/actions/frontend-toolchain/action.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual("code=true", probe.detect(path))

    def test_actual_frontend_doc_reads_precede_prose_classification(self) -> None:
        # Real temporary source inputs, not an invented detector result.
        with tempfile.TemporaryDirectory(prefix="frontend-doc-filter-") as temp:
            root = Path(temp)
            tests = root / "cargento/skills/cargento/tests"
            tests.mkdir(parents=True)
            (tests / "dummy.py").write_text("pass\n")
            runtime = root / "cargento/skills/cargento/cargento_runtime"
            runtime.mkdir()
            frontend = root / "frontend/test"
            frontend.mkdir(parents=True)
            source = frontend / "setup.test.ts"
            root_doc = "CONTRIBUTING" + ".md"
            quoted_doc = "docs/" + "frontend-reader" + ".md"
            cited_doc = "docs/" + "frontend-citation" + ".md"
            source.write_text(
                f"readFileSync('{root_doc}');\nreadFileSync(\"{quoted_doc}\");\n"
                f"// See ({cited_doc}#reader-state)\n"
            )
            probe = detector.QualityGateDetectorTest()
            for path in (root_doc, quoted_doc, cited_doc):
                with self.subTest(path=path):
                    self.assertEqual("code=true", probe.detect(path, root=root))
            source.unlink()
            self.assertEqual("code=false", probe.detect(root_doc, root=root))
            self.assertEqual("code=false", probe.detect(quoted_doc, root=root))
            # An unreadable source scan cannot authorize the prose skip path.
            source.write_bytes(b"\xff")
            self.assertEqual("code=true", probe.detect(root_doc, root=root))

    def test_unrelated_workflow_prose_keeps_its_short_path(self) -> None:
        self.assertEqual(
            "code=false",
            detector.QualityGateDetectorTest().detect(".github/workflows/version-guard.yml"),
        )


@unittest.skipUnless(detector.BASH, "the shipped aggregate uses Bash")
class FrontendAggregateControlsTest(unittest.TestCase):
    def aggregate(self, *, code: str, results: dict[str, str]) -> subprocess.CompletedProcess[str]:
        script = next(step["run"] for step in jobs()["quality-gate"]["steps"] if "run" in step)
        return subprocess.run(
            [detector.BASH or "bash", "-c", script],
            env={**os.environ, "CODE": code, **results},
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

    def test_every_required_result_rejects_failure_cancellation_and_unexpected_skip(self) -> None:
        successful = {
            "R_CHANGES": "success",
            "R_LINT": "success",
            "R_TYPECHECK": "success",
            "R_FLOOR": "success",
            "R_TEST": "success",
            "R_PLATFORM": "success",
            "R_FRONTEND": "success",
        }
        for name in successful:
            for bad in ("failure", "cancelled", "skipped"):
                with self.subTest(name=name, bad=bad):
                    result = self.aggregate(code="true", results={**successful, name: bad})
                    self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertEqual(0, self.aggregate(code="true", results=successful).returncode)

    def test_skip_is_allowed_only_for_prose_and_a_successful_detector(self) -> None:
        skipped = {
            "R_CHANGES": "success",
            "R_LINT": "skipped",
            "R_TYPECHECK": "skipped",
            "R_FLOOR": "skipped",
            "R_TEST": "skipped",
            "R_PLATFORM": "skipped",
            "R_FRONTEND": "skipped",
        }
        self.assertEqual(0, self.aggregate(code="false", results=skipped).returncode)
        for bad in ("failure", "cancelled", "skipped"):
            with self.subTest(detector=bad):
                self.assertNotEqual(
                    0,
                    self.aggregate(code="false", results={**skipped, "R_CHANGES": bad}).returncode,
                )
        self.assertNotEqual(
            0, self.aggregate(code="false", results={**skipped, "R_FRONTEND": "failure"}).returncode
        )


class FrontendWiringControlsTest(unittest.TestCase):
    def check_windows_paused_on_pull_requests(
        self, job: dict[str, Any], pull_request: set[str]
    ) -> None:
        """Windows runs on main pushes and labelled pull requests only, until the migration's final stage."""
        selection = job["strategy"]["matrix"]["os"]
        self.assertIsInstance(selection, str)
        self.assertIn("github.event_name == 'pull_request'", selection)
        self.assertIn("contains(github.event.pull_request.labels.*.name, 'windows-ci')", selection)
        unlabelled, everywhere = (
            json.loads(part) for part in re.findall(r"'(\[[^']*\])'", selection)
        )
        self.assertEqual(pull_request, set(unlabelled))
        self.assertEqual(pull_request | {"windows-latest"}, set(everywhere))

    def test_gate_checkouts_do_not_leave_credentials_for_later_commands(self) -> None:
        for name, job in jobs().items():
            for step in job.get("steps", []):
                if step.get("uses", "").startswith("actions/checkout@"):
                    with self.subTest(job=name):
                        self.assertFalse(step.get("with", {}).get("persist-credentials", True))

    def test_matrix_is_required_and_keeps_all_current_python_jobs(self) -> None:
        workflow_jobs = jobs()
        frontend = workflow_jobs["frontend"]
        self.check_windows_paused_on_pull_requests(frontend, {"ubuntu-latest", "macos-latest"})
        self.check_windows_paused_on_pull_requests(
            workflow_jobs["platform-tests"], {"macos-latest"}
        )
        self.assertFalse(frontend["strategy"]["fail-fast"])
        self.assertLessEqual(frontend["timeout-minutes"], 15)
        self.assertEqual("changes", frontend["needs"])
        self.assertEqual("needs.changes.outputs.code == 'true'", frontend["if"])
        aggregate = workflow_jobs["quality-gate"]
        self.assertEqual("always()", aggregate["if"])
        self.assertEqual(
            {"changes", "lint", "typecheck", "runtime-floor", "test", "platform-tests", "frontend"},
            set(aggregate["needs"]),
        )
        self.assertEqual("${{ needs.frontend.result }}", aggregate["steps"][0]["env"]["R_FRONTEND"])

    def test_bootstrap_is_exact_without_auth_or_implicit_dependency_scripts(self) -> None:
        steps = jobs()["frontend"]["steps"]
        node = next(
            step for step in steps if step.get("uses", "").startswith("actions/setup-node@")
        )
        self.assertEqual(
            "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020", node["uses"]
        )
        self.assertEqual(".node-version", node["with"]["node-version-file"])
        self.assertFalse(node["with"]["check-latest"])
        self.assertFalse(node["with"]["package-manager-cache"])
        manager = next(step for step in steps if step.get("uses", "").startswith("pnpm/setup@"))
        self.assertEqual("pnpm/setup@fbda4c85fc2e1e08721cd8763afea8f48d60f024", manager["uses"])
        self.assertEqual("12.9.1", manager["with"]["version"])
        self.assertFalse(manager["with"]["install"])
        self.assertFalse(manager["with"]["node-version-file"])
        checkout = next(
            step for step in steps if step.get("uses", "").startswith("actions/checkout@")
        )
        self.assertFalse(checkout["with"]["persist-credentials"])
        commands = [step.get("run", "") for step in steps]
        self.assertIn("pnpm install --frozen-lockfile --ignore-scripts", commands)
        self.assertFalse(any("corepack" in command.lower() for command in commands))
        for step in steps:
            self.assertNotIn("registry-url", step.get("with", {}))
            for name in ("NODE_AUTH_TOKEN", "NPM_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
                self.assertNotIn(name, step.get("env", {}))

    def test_native_build_is_separate_from_canonical_check_and_installed_smoke(self) -> None:
        steps = jobs()["frontend"]["steps"]
        commands = {step.get("run"): step for step in steps if "run" in step}
        for command in (
            "pnpm lint",
            "pnpm typecheck",
            "pnpm test",
            "pnpm build:preview",
            "pnpm test:parser",
        ):
            self.assertIn(command, commands)
            self.assertNotIn("if", commands[command])
        self.assertEqual("matrix.os == 'ubuntu-latest'", commands["pnpm build:check"]["if"])
        installed = commands["pnpm test:installed"]
        self.assertNotIn("if", installed)
        self.assertEqual(
            "${{ steps.python.outputs.python-path }}", installed["env"]["CARGENTO_TEST_PYTHON"]
        )
        self.assertTrue(all("pnpm preview" not in command for command in commands))
        self.assertTrue(all("pnpm test:browser" not in command for command in commands))
        self.assertTrue(all(step.get("timeout-minutes", 0) > 0 for step in steps if "run" in step))
        python = next(step for step in steps if step.get("id") == "python")
        self.assertEqual("3.11", python["with"]["python-version"])


if __name__ == "__main__":
    unittest.main()
