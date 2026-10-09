"""The required gate measures frontend changes and cannot hide a failed matrix."""

from __future__ import annotations

import json
import os
import shutil
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
            "biome.json",
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
            "R_FRONTEND_PROOFS": "success",
            "R_FRONTEND_PRODUCTION": "success",
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
            "R_FRONTEND_PROOFS": "skipped",
            "R_FRONTEND_PRODUCTION": "skipped",
        }
        self.assertEqual(0, self.aggregate(code="false", results=skipped).returncode)
        for bad in ("failure", "cancelled", "skipped"):
            with self.subTest(detector=bad):
                self.assertNotEqual(
                    0,
                    self.aggregate(code="false", results={**skipped, "R_CHANGES": bad}).returncode,
                )
        for name in ("R_FRONTEND", "R_FRONTEND_PROOFS", "R_FRONTEND_PRODUCTION"):
            with self.subTest(failed=name):
                self.assertNotEqual(
                    0, self.aggregate(code="false", results={**skipped, name: "failure"}).returncode
                )


class FrontendWiringControlsTest(unittest.TestCase):
    def check_runs_everywhere(self, job: dict[str, Any], runners: list[str]) -> None:
        """Every pull request and every push runs every platform: the Windows legs are no longer paused."""
        selection = job["strategy"]["matrix"]["os"]
        self.assertEqual(runners, selection)
        self.assertNotIn("windows-ci", json.dumps(job))

    def test_gate_checkouts_do_not_leave_credentials_for_later_commands(self) -> None:
        for name, job in jobs().items():
            for step in job.get("steps", []):
                if step.get("uses", "").startswith("actions/checkout@"):
                    with self.subTest(job=name):
                        self.assertFalse(step.get("with", {}).get("persist-credentials", True))

    def test_matrix_is_required_and_keeps_all_current_python_jobs(self) -> None:
        workflow_jobs = jobs()
        frontend = workflow_jobs["frontend"]
        everywhere = ["ubuntu-latest", "macos-latest", "windows-latest"]
        self.check_runs_everywhere(frontend, everywhere)
        platform = workflow_jobs["platform-tests"]
        self.check_runs_everywhere(platform, ["macos-latest", "windows-latest"])
        # The two suites run as parallel legs so the slow script suite does not hold the dashboard one.
        self.assertEqual(["dashboard", "scripts"], platform["strategy"]["matrix"]["suite"])
        gated = {step["name"]: step.get("if") for step in platform["steps"] if "if" in step}
        self.assertEqual(
            {
                "Run dashboard test discovery": "matrix.suite == 'dashboard'",
                "Run script unit tests": "matrix.suite == 'scripts'",
            },
            gated,
        )
        self.assertFalse(frontend["strategy"]["fail-fast"])
        self.assertLessEqual(frontend["timeout-minutes"], 30)
        self.assertEqual("changes", frontend["needs"])
        self.assertEqual("needs.changes.outputs.code == 'true'", frontend["if"])
        aggregate = workflow_jobs["quality-gate"]
        self.assertEqual("always()", aggregate["if"])
        self.assertEqual(
            {
                "changes",
                "lint",
                "typecheck",
                "runtime-floor",
                "test",
                "platform-tests",
                "frontend",
                "frontend-proofs",
                "frontend-production",
            },
            set(aggregate["needs"]),
        )
        env = aggregate["steps"][0]["env"]
        self.assertEqual("${{ needs.frontend.result }}", env["R_FRONTEND"])
        self.assertEqual("${{ needs.frontend-proofs.result }}", env["R_FRONTEND_PROOFS"])
        self.assertEqual("${{ needs.frontend-production.result }}", env["R_FRONTEND_PRODUCTION"])
        # The proofs job is a second half of `frontend`, so it keeps the same runners and cap.
        proofs = workflow_jobs["frontend-proofs"]
        self.check_runs_everywhere(proofs, everywhere)
        self.assertFalse(proofs["strategy"]["fail-fast"])
        self.assertLessEqual(proofs["timeout-minutes"], 30)
        self.assertEqual("changes", proofs["needs"])
        self.assertEqual("needs.changes.outputs.code == 'true'", proofs["if"])

    def test_bootstrap_is_exact_without_auth_or_implicit_dependency_scripts(self) -> None:
        for name in ("frontend", "frontend-proofs", "frontend-production"):
            with self.subTest(job=name):
                self.check_bootstrap(jobs()[name]["steps"])

    def check_bootstrap(self, steps: list[dict[str, Any]]) -> None:
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

    def test_integrated_development_runs_on_every_native_frontend_runner(self) -> None:
        # `frontend` and `frontend-proofs` split the development proofs between them; each proof runs once.
        workflow_jobs = jobs()
        steps = [*workflow_jobs["frontend"]["steps"], *workflow_jobs["frontend-proofs"]["steps"]]
        for command in (
            "pnpm test:dev",
            "pnpm test:dev:browser",
            "pnpm test:storage:browser",
            "pnpm test:shell:browser",
            "pnpm test:controls:browser",
            "pnpm test:sessions:browser",
            "pnpm test:intent:browser",
            "pnpm test:drift:browser",
            "pnpm test:project:browser",
            "pnpm test:console:browser",
            "pnpm test:attention:browser",
            "pnpm test:capacity:browser",
            "pnpm test:terminal:browser",
        ):
            with self.subTest(command=command):
                matches = [step for step in steps if step.get("run") == command]
                self.assertEqual(1, len(matches), "development proof must run exactly once")
                step = matches[0]
                self.assertNotIn("if", step, "all native runners must exercise development")
                self.assertNotIn("continue-on-error", step)
                self.assertGreater(step.get("timeout-minutes", 0), 0)
                self.assertEqual(
                    "${{ steps.python.outputs.python-path }}",
                    step["env"]["CARGENTO_TEST_PYTHON"],
                )
                self.assertNotIn(
                    "CARGENTO_E2E_BUNDLE", step["env"], "development must stay development"
                )
        for name in ("frontend", "frontend-proofs"):
            commands = [step.get("run") for step in workflow_jobs[name]["steps"]]
            install = commands.index("pnpm exec playwright install --with-deps chromium")
            for command in commands:
                if command and command.endswith(":browser") and command.startswith("pnpm test:"):
                    with self.subTest(job=name, command=command):
                        self.assertLess(install, commands.index(command))

    def test_each_browser_script_runs_every_proof_it_names(self) -> None:
        """A script that chains two proofs is one workflow step, so the step test alone cannot see one dropped."""
        scripts = json.loads((ROOT / "package.json").read_text())["scripts"]
        expected = {
            "test:terminal:browser": ("terminal-parity.mjs", "timeline-filter.mjs"),
            "test:sessions:browser": ("sessions-parity.mjs",),
            "test:intent:browser": ("intent-parity.mjs",),
            "test:drift:browser": ("drift-parity.mjs",),
            "test:project:browser": ("project-parity.mjs",),
            "test:console:browser": ("console-parity.mjs",),
            "test:attention:browser": ("attention-parity.mjs",),
            "test:capacity:browser": ("capacity-parity.mjs",),
            "test:shell:browser": ("shell-routing.mjs",),
            "test:controls:browser": ("controls-continuity.mjs",),
            "test:storage:browser": ("storage-conformance.mjs",),
        }
        for name, files in expected.items():
            for file in files:
                with self.subTest(script=name, proof=file):
                    self.assertIn(f"frontend/e2e/{file}", scripts[name])

    def test_production_bundle_job_runs_every_parity_proof_in_two_shards(self) -> None:
        job = jobs()["frontend-production"]
        self.assertEqual("ubuntu-latest", job["runs-on"])
        self.assertEqual("changes", job["needs"])
        self.assertEqual("needs.changes.outputs.code == 'true'", job["if"])
        self.assertFalse(job["strategy"]["fail-fast"])
        self.assertLessEqual(job["timeout-minutes"], 30)
        self.assertNotIn("permissions", job, "the job inherits the workflow's read-only token")
        self.assertEqual("read", yaml.safe_load(WORKFLOW.read_text())["permissions"]["contents"])
        self.assertTrue(job["name"].startswith("Frontend production bundle (ubuntu-latest"))
        steps = job["steps"]
        for step in steps:
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn("secrets", json.dumps(step))
            if "run" in step:
                self.assertGreater(step.get("timeout-minutes", 0), 0)
        commands = [step.get("run") for step in steps]
        proof = "pnpm test:production:browser --shard ${{ matrix.shard }}"
        self.assertEqual(1, commands.count(proof), "the production proofs run exactly once")
        step = steps[commands.index(proof)]
        self.assertEqual(
            "${{ steps.python.outputs.python-path }}", step["env"]["CARGENTO_TEST_PYTHON"]
        )
        self.assertNotIn("if", step)
        # The tracked artifact is verified against its sources, then the chromium, then the proofs.
        build = commands.index("pnpm build:check")
        self.assertNotIn("if", steps[build])
        install = commands.index("pnpm exec playwright install --with-deps chromium")
        self.assertLess(commands.index("pnpm install --frozen-lockfile --ignore-scripts"), build)
        self.assertLess(build, commands.index(proof))
        self.assertLess(install, commands.index(proof))

    def test_production_shards_cover_every_parity_proof_exactly_once(self) -> None:
        shards = json.loads((ROOT / "frontend/e2e/production-shards.json").read_text())
        matrix = jobs()["frontend-production"]["strategy"]["matrix"]["shard"]
        self.assertEqual(sorted(shards), sorted(matrix), "one matrix leg per shard")
        listed = [name for names in shards.values() for name in names]
        self.assertEqual(len(listed), len(set(listed)), "a proof is in two shards")
        scripts = json.loads((ROOT / "package.json").read_text())["scripts"]
        development_proofs = {
            step["run"].removeprefix("pnpm ")
            for name in ("frontend", "frontend-proofs")
            for step in jobs()[name]["steps"]
            if step.get("run", "").startswith("pnpm test:") and step["run"].endswith(":browser")
        }
        # dev:browser is the hot-refresh proof, which is development-only by definition.
        development_proofs.discard("test:dev:browser")
        self.assertEqual(
            development_proofs, set(listed), "a development proof has no production run"
        )
        for name in listed:
            self.assertIn(name, scripts)
        self.assertIn("frontend/e2e/production-proofs.mjs", scripts["test:production:browser"])
        runner = (ROOT / "frontend/e2e/production-proofs.mjs").read_text()
        self.assertIn("CARGENTO_E2E_BUNDLE: 'production'", runner)

    def test_no_frontend_job_can_fail_open(self) -> None:
        """A job-level `continue-on-error` makes `needs.<job>.result` read success for a red job; a weakened `if`
        lets the job skip where the aggregator expects it to run."""
        workflow_jobs = jobs()
        for name in ("frontend", "frontend-proofs", "frontend-production"):
            with self.subTest(job=name):
                job = workflow_jobs[name]
                self.assertNotIn("continue-on-error", job)
                self.assertEqual("changes", job["needs"])
                self.assertEqual("needs.changes.outputs.code == 'true'", job["if"])
                for step in job["steps"]:
                    self.assertNotIn("continue-on-error", step)
        self.assertNotIn("continue-on-error", workflow_jobs["quality-gate"])

    def test_production_runner_refuses_an_unknown_argument_before_running_anything(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        runner = str(ROOT / "frontend/e2e/production-proofs.mjs")
        for arguments in (
            ["--bogus"],
            ["--shards", "a"],
            ["--shard"],
            ["--shard", "zz"],
            ["--", "--shard", "a"],
        ):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [node, runner, *arguments],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=20,
                )
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertIn("Usage:", result.stderr)
                self.assertNotIn("===", result.stdout, "a proof started")

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
