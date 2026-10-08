"""The release workflow keeps its credentials away from dependency code.

The job that holds the deploy key can push to main and move release tags past both
rulesets, so these tests pin the boundary rather than the steps: which job has which
permission, what each checkout persists, and that nothing which runs `node`, `pnpm`
or a package script shares a job with the key.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[4]
RELEASE = ROOT / ".github/workflows/release.yml"
GATE = ROOT / ".github/workflows/quality-gate.yml"
SHA = re.compile(r"^[0-9a-f]{40}$")
FRONTEND_TOOLS = ("setup-node", "pnpm/setup")
NODE_COMMAND = re.compile(
    r"(?<![\w./-])(node|nodejs|pnpm|npm|npx|corepack|yarn|bun|deno)(?![\w-])", re.IGNORECASE
)


def load(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))


def jobs() -> dict[str, Any]:
    return cast("dict[str, Any]", load(RELEASE)["jobs"])


def steps(job: str) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", jobs()[job]["steps"])


def commands(job: str) -> list[str]:
    return [step["run"] for step in steps(job) if "run" in step]


def code(command: str) -> str:
    """The command without its comment lines, which explain a rule by naming it."""
    return "\n".join(line for line in command.splitlines() if not line.lstrip().startswith("#"))


def uses(job: str, action: str) -> list[dict[str, Any]]:
    return [step for step in steps(job) if step.get("uses", "").startswith(f"{action}@")]


def serialized(value: Any) -> str:
    return str(yaml.safe_dump(value, sort_keys=True))


class JobGraphTest(unittest.TestCase):
    def test_the_release_is_resolve_then_verify_then_publish(self) -> None:
        self.assertEqual({"resolve", "verify-frontend", "verify-tree", "release"}, set(jobs()))
        self.assertEqual("resolve", jobs()["verify-frontend"]["needs"])
        self.assertEqual("resolve", jobs()["verify-tree"]["needs"])
        self.assertEqual(
            {"resolve", "verify-frontend", "verify-tree"}, set(jobs()["release"]["needs"])
        )
        self.assertNotIn("needs", jobs()["resolve"])

    def test_only_a_tag_push_triggers_it_and_it_never_cancels_a_running_release(self) -> None:
        workflow = load(RELEASE)
        triggers = (
            cast("dict[Any, Any]", workflow).get(True) or workflow["on"]
        )  # PyYAML reads a bare `on` as True
        self.assertEqual({"push"}, set(triggers))
        self.assertEqual({"tags"}, set(triggers["push"]))
        self.assertEqual("release", workflow["concurrency"]["group"])
        self.assertFalse(workflow["concurrency"]["cancel-in-progress"])
        self.assertNotIn("pull_request_target", serialized(workflow))

    def test_every_action_is_pinned_to_an_immutable_sha(self) -> None:
        for name, job in jobs().items():
            for step in job["steps"]:
                if "uses" in step:
                    with self.subTest(job=name, action=step["uses"]):
                        self.assertRegex(step["uses"].split("@", 1)[1], SHA)

    def test_every_job_and_run_step_has_a_timeout(self) -> None:
        for name, job in jobs().items():
            self.assertGreater(job["timeout-minutes"], 0, name)
            for step in job["steps"]:
                if "run" in step and name != "release":
                    with self.subTest(job=name, step=step.get("name")):
                        self.assertGreater(step.get("timeout-minutes", 0), 0)

    def test_workflow_default_token_is_read_only(self) -> None:
        self.assertEqual({"contents": "read"}, load(RELEASE)["permissions"])


class CredentialBoundaryTest(unittest.TestCase):
    def test_the_deploy_key_and_write_token_belong_to_the_publishing_job_alone(self) -> None:
        for name, job in jobs().items():
            text = serialized(job)
            with self.subTest(job=name):
                if name == "release":
                    self.assertIn("RELEASE_DEPLOY_KEY", text)
                    self.assertEqual({"contents": "write"}, job["permissions"])
                else:
                    self.assertNotIn("secrets.", text)
                    self.assertNotIn("ssh-key", text)
                    self.assertNotIn("github.token", text)
                    self.assertNotIn("GITHUB_TOKEN", text)
                    self.assertNotIn("GH_TOKEN", text)
                    self.assertEqual({"contents": "read"}, job["permissions"])

    def test_the_secret_is_named_once_in_the_whole_workflow(self) -> None:
        self.assertEqual(1, RELEASE.read_text().count("secrets.RELEASE_DEPLOY_KEY"))

    def test_credential_free_jobs_never_persist_credentials(self) -> None:
        for name in ("resolve", "verify-frontend", "verify-tree"):
            checkouts = uses(name, "actions/checkout")
            self.assertEqual(1, len(checkouts), name)
            self.assertIs(False, checkouts[0]["with"]["persist-credentials"], name)

    def test_the_publishing_checkout_is_main_with_history_and_the_key(self) -> None:
        (checkout,) = uses("release", "actions/checkout")
        self.assertEqual("main", checkout["with"]["ref"])
        self.assertEqual(0, checkout["with"]["fetch-depth"])
        self.assertEqual("${{ secrets.RELEASE_DEPLOY_KEY }}", checkout["with"]["ssh-key"])
        self.assertIs(True, checkout["with"]["persist-credentials"])
        self.assertEqual(checkout, steps("release")[0], "nothing may run before the checkout")

    def test_only_the_publishing_job_can_push(self) -> None:
        for name in ("resolve", "verify-frontend", "verify-tree"):
            for command in commands(name):
                with self.subTest(job=name):
                    self.assertNotRegex(command, r"git\s+(-\S+\s+)*push|gh\s+(release|api)")

    def test_no_untrusted_context_is_interpolated_into_a_shell_command(self) -> None:
        # Tag names, branch names and needs outputs reach commands through env: and
        # are quoted there. A `${{ }}` inside `run:` is textual substitution.
        for name, job in jobs().items():
            for step in job["steps"]:
                with self.subTest(job=name, step=step.get("name")):
                    self.assertNotIn("${{", step.get("run", ""))


class PublishingJobRunsNoFrontendCodeTest(unittest.TestCase):
    def test_it_installs_and_runs_no_node_tooling(self) -> None:
        for step in steps("release"):
            for tool in FRONTEND_TOOLS:
                self.assertNotIn(tool, step.get("uses", ""))
        for command in commands("release"):
            with self.subTest(command=command[:60]):
                self.assertIsNone(NODE_COMMAND.search(command))
        self.assertEqual([], uses("release", "actions/setup-node"))
        self.assertEqual([], uses("release", "pnpm/setup"))

    def test_the_full_validation_suite_moved_out_with_the_node_tests_it_contains(self) -> None:
        # validate_plugins.py and several dashboard tests start `node` when it is on
        # PATH, and a hosted runner has it there. The suite therefore runs where no
        # credential does.
        for command in commands("release"):
            self.assertNotIn("unittest discover", command)
            self.assertNotRegex(
                command, r"validate_plugins\.py(?!\s+--(public-text|runtime-files))", command
            )
        self.assertTrue(any("unittest discover" in c for c in commands("verify-tree")))
        self.assertTrue(any("validate_plugins.py" in c for c in commands("verify-tree")))

    def test_the_python_entry_points_it_keeps_never_start_node(self) -> None:
        # `--public-text` and `--runtime-files` return before the adapter check that
        # shells out to node; a planted `node` on PATH must therefore never run.
        with tempfile.TemporaryDirectory() as scratch:
            marker = Path(scratch) / "node-ran"
            fake = Path(scratch) / "bin" / "node"
            fake.parent.mkdir()
            fake.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            env = {**os.environ, "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}"}
            note = Path(scratch) / "notes.md"
            note.write_text("Plain release notes.\n")
            for args in (
                ["--public-text", str(note)],
                ["--runtime-files", str(ROOT / "cargento")],
            ):
                with self.subTest(args=args[0]):
                    subprocess.run(
                        [sys.executable, str(ROOT / "scripts/validate_plugins.py"), *args],
                        env=env,
                        capture_output=True,
                        check=False,
                        timeout=120,
                    )
                    self.assertFalse(marker.exists(), "node was started")


class VerificationJobTest(unittest.TestCase):
    def test_it_checks_out_exactly_the_resolved_target(self) -> None:
        for name in ("verify-frontend", "verify-tree"):
            (checkout,) = uses(name, "actions/checkout")
            self.assertEqual("${{ needs.resolve.outputs.target }}", checkout["with"]["ref"], name)
            self.assertNotIn("ref: main", serialized(checkout))

    def test_it_pins_the_gates_toolchain(self) -> None:
        gate = {step["uses"] for step in load(GATE)["jobs"]["frontend"]["steps"] if "uses" in step}
        for step in steps("verify-frontend"):
            if "uses" in step:
                with self.subTest(action=step["uses"]):
                    self.assertIn(step["uses"], gate)
        (node,) = uses("verify-frontend", "actions/setup-node")
        self.assertEqual(".node-version", node["with"]["node-version-file"])
        self.assertIs(False, node["with"]["check-latest"])
        (manager,) = uses("verify-frontend", "pnpm/setup")
        gate_manager = next(
            s
            for s in load(GATE)["jobs"]["frontend"]["steps"]
            if s.get("uses", "").startswith("pnpm/setup@")
        )
        self.assertEqual(gate_manager["with"], manager["with"])

    def test_it_installs_without_scripts_and_never_with_corepack(self) -> None:
        run = commands("verify-frontend")
        self.assertIn("pnpm install --frozen-lockfile --ignore-scripts", run)
        self.assertFalse(any("corepack" in command.lower() for command in run))

    def test_it_rebuilds_and_compares_before_the_installed_python_only_proof(self) -> None:
        run = commands("verify-frontend")
        for command in (
            "pnpm lint",
            "pnpm typecheck",
            "pnpm test",
            "pnpm build:check",
            "pnpm test:installed",
        ):
            self.assertIn(command, run)
        self.assertLess(run.index("pnpm build:check"), run.index("pnpm test:installed"))
        self.assertLess(
            run.index("pnpm install --frozen-lockfile --ignore-scripts"), run.index("pnpm lint")
        )

    def test_it_records_the_commit_it_verified_and_leaves_the_tree_untouched(self) -> None:
        job = jobs()["verify-frontend"]
        self.assertEqual("${{ steps.verified.outputs.sha }}", job["outputs"]["verified"])
        recording = [s for s in steps("verify-frontend") if s.get("id") == "verified"]
        self.assertEqual(1, len(recording))
        self.assertIn("git rev-parse HEAD", recording[0]["run"])
        dirty = [c for c in commands("verify-frontend") if "git status --porcelain" in c]
        self.assertTrue(dirty, "a verification that rewrote the tree verified a different tree")

    def test_the_tree_job_records_its_commit_the_same_way(self) -> None:
        self.assertEqual(
            "${{ steps.verified.outputs.sha }}", jobs()["verify-tree"]["outputs"]["verified"]
        )
        recording = [s for s in steps("verify-tree") if s.get("id") == "verified"]
        self.assertEqual(1, len(recording))
        self.assertIn("git rev-parse HEAD", recording[0]["run"])

    def test_it_asserts_it_is_looking_at_the_target_before_building_anything(self) -> None:
        run = commands("verify-frontend")
        first = next(i for i, c in enumerate(run) if "assert-head" in c)
        self.assertLess(first, run.index("pnpm install --frozen-lockfile --ignore-scripts"))


class PublishingOrderTest(unittest.TestCase):
    ORDER = (
        "release_transition.py assert-checkout",
        "release_transition.py bump",
        "release_transition.py commit-bump",
        "verify_release_archive.py",
        "release_transition.py push-bump",
        "release_transition.py move-tag",
        "release_transition.py advance-stable",
        "gh release create",
    )

    def positions(self) -> list[int]:
        run = commands("release")
        return [next(i for i, c in enumerate(run) if needle in c) for needle in self.ORDER]

    def test_the_checkout_is_asserted_first_and_the_archive_is_proven_before_any_push(self) -> None:
        found = self.positions()
        self.assertEqual(sorted(found), found)
        self.assertEqual(0, found[0], "the assertion is the first command the key can reach")

    def test_the_assertion_binds_the_verified_commit_and_the_resolved_target(self) -> None:
        step = next(s for s in steps("release") if "assert-checkout" in s.get("run", ""))
        text = step["run"]
        for flag in ("--mode", "--target", "--verified", "--tag"):
            self.assertIn(flag, text)
        self.assertIn('--verified "$VERIFIED_FRONTEND"', text)
        self.assertIn('--verified "$VERIFIED_TREE"', text)
        env = jobs()["release"]["env"]
        self.assertEqual("${{ needs.resolve.outputs.target }}", env["TARGET"])
        self.assertEqual("${{ needs.verify-frontend.outputs.verified }}", env["VERIFIED_FRONTEND"])
        self.assertEqual("${{ needs.verify-tree.outputs.verified }}", env["VERIFIED_TREE"])
        self.assertEqual("${{ needs.resolve.outputs.mode }}", env["MODE"])

    def test_the_archive_proof_checks_the_final_commit_against_the_target(self) -> None:
        step = next(s for s in steps("release") if "verify_release_archive.py" in s.get("run", ""))
        for flag in ('--commit "$FINAL"', '--verified "$TARGET"', '--version "$VERSION"'):
            self.assertIn(flag, step["run"])

    def test_nothing_forces_the_bump_push_and_main_is_only_pushed_by_the_script(self) -> None:
        for command in map(code, commands("release")):
            self.assertNotIn("git push", command)
            self.assertNotIn("--force", command)

    def test_a_resumed_release_runs_no_bump_and_no_validation_suite(self) -> None:
        for fragment in ("release_transition.py bump", "release_transition.py commit-bump"):
            step = next(s for s in steps("release") if fragment in s.get("run", ""))
            self.assertEqual("env.MODE == 'fresh'", step["if"])

    def test_the_python_requirements_install_into_a_venv(self) -> None:
        text = "\n".join(commands("release"))
        self.assertIn("python3 -m venv", text)
        self.assertIn("GITHUB_PATH", text)


if __name__ == "__main__":
    unittest.main()
