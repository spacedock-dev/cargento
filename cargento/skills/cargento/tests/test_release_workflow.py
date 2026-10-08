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
        "validate_plugins.py --public-text",
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

    def test_the_archive_is_proven_and_the_notes_checked_before_any_mutation(self) -> None:
        found = self.positions()
        self.assertEqual(sorted(found), found)

    def test_plain_shell_pins_head_before_any_repository_code_runs(self) -> None:
        run = commands("release")
        first = code(run[0])
        self.assertIn("git rev-parse HEAD", first)
        self.assertIn('"$TARGET"', first)
        self.assertIn('git checkout --detach "$TARGET"', first)
        self.assertRegex(first, r'\[ "\$\(git rev-parse HEAD\)" != "\$TARGET" \]')
        self.assertNotIn("python", first)
        self.assertNotIn("scripts/", first)
        self.assertIn("Re-run all jobs", first)
        # The assertion is the second check, and the first repository script to run.
        self.assertIn("assert-checkout", run[1])
        for command in run[:1]:
            self.assertNotRegex(code(command), r"python3?\s|\./scripts|scripts/")

    def test_the_resume_detach_cannot_be_skipped_or_conditional(self) -> None:
        first = steps("release")[1]
        self.assertNotIn("if", first)
        self.assertNotIn("continue-on-error", first)
        self.assertIn('elif [ "$MODE" = "resume" ]', first["run"])

    def test_the_target_is_validated_as_a_sha_in_shell_before_git_sees_it(self) -> None:
        self.assertIn("[0-9a-f]{40}", commands("release")[0])

    def test_the_assertion_binds_the_verified_commit_and_the_resolved_target(self) -> None:
        step = next(s for s in steps("release") if "assert-checkout" in s.get("run", ""))
        text = step["run"]
        self.assertIn('--mode "$MODE"', text)
        self.assertIn('--target "$TARGET"', text)
        self.assertIn('--tag "$TAG"', text)
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

    def test_a_resumed_release_runs_no_bump_and_pushes_no_bump(self) -> None:
        for fragment in (
            "release_transition.py bump",
            "release_transition.py commit-bump",
            "release_transition.py push-bump",
        ):
            step = next(s for s in steps("release") if fragment in s.get("run", ""))
            self.assertEqual("env.MODE == 'fresh'", step["if"], fragment)


class KeyJobWiringTest(unittest.TestCase):
    """Wiring a mutation can break without any Python test noticing."""

    def release_steps(self) -> list[dict[str, Any]]:
        return steps("release")

    def test_no_release_step_can_swallow_a_failure(self) -> None:
        job = jobs()["release"]
        self.assertNotIn("if", job, "an always() or cancelled() job would run past a failure")
        self.assertNotIn("continue-on-error", job)
        for step in self.release_steps():
            with self.subTest(step=step.get("name")):
                self.assertNotIn("continue-on-error", step)
                self.assertNotRegex(code(step.get("run", "")), r"\|\|\s*(true|:)\b|;\s*true\b")
                self.assertNotIn("set +e", step.get("run", ""))
                self.assertNotIn("always()", str(step.get("if", "")))
                self.assertNotIn("failure()", str(step.get("if", "")))
                if "run" in step:
                    self.assertTrue(step["run"].lstrip().startswith("set -euo pipefail"))

    def test_the_only_conditions_are_the_mode_gates(self) -> None:
        conditions = {step.get("name"): step["if"] for step in self.release_steps() if "if" in step}
        self.assertEqual(
            {
                "Write the version bump commit": "env.MODE == 'fresh'",
                "Push the release commit to main": "env.MODE == 'fresh'",
            },
            conditions,
        )

    def test_the_job_uses_one_action_and_no_cross_job_channel(self) -> None:
        self.assertEqual(
            ["actions/checkout"],
            [step["uses"].split("@")[0] for step in self.release_steps() if "uses" in step],
        )
        text = serialized(jobs()["release"])
        for channel in ("actions/cache", "download-artifact", "upload-artifact", "setup-"):
            self.assertNotIn(channel, text)

    def test_the_environment_is_exactly_the_six_resolved_values(self) -> None:
        self.assertEqual(
            {"TAG", "MODE", "VERSION", "TARGET", "VERIFIED_FRONTEND", "VERIFIED_TREE"},
            set(jobs()["release"]["env"]),
        )
        for step in self.release_steps():
            for name in step.get("env", {}):
                with self.subTest(step=step.get("name"), name=name):
                    self.assertIn(name, {"GH_TOKEN"})
        text = "\n".join(code(c) for c in commands("release"))
        for hazard in ("BASH_ENV", "GITHUB_PATH", "PYTHONPATH", "LD_PRELOAD", "NODE_OPTIONS"):
            self.assertNotIn(hazard, text)

    def test_the_python_install_is_wheels_only_from_the_default_index(self) -> None:
        installs = [c for c in commands("release") if "pip install" in c]
        self.assertEqual(1, len(installs))
        line = next(part for part in installs[0].splitlines() if "pip install" in part)
        self.assertIn("--only-binary=:all:", line)
        self.assertIn("--requirement requirements-validation.txt", line)
        for forbidden in ("--index-url", "--extra-index-url", "--find-links", "--user", "-i "):
            self.assertNotIn(forbidden, line)
        self.assertIn('"$RUNNER_TEMP/release-venv/bin/python" -m pip', line)

    def test_the_requirements_are_exact_pins(self) -> None:
        lines = [
            line.strip()
            for line in (ROOT / "requirements-validation.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*$")

    def test_scripts_that_need_yaml_run_on_the_venv_interpreter_by_explicit_path(self) -> None:
        interpreter = '"$RUNNER_TEMP/release-venv/bin/python"'
        for fragment in ("validate_plugins.py --public-text", "verify_release_archive.py"):
            command = next(c for c in commands("release") if fragment in c)
            self.assertIn(f"{interpreter} scripts/{fragment}", command)

    def test_notes_are_checked_with_their_token_before_the_first_mutation(self) -> None:
        run = commands("release")
        notes = next(i for i, c in enumerate(run) if "--public-text" in c)
        mutation = min(
            i
            for i, c in enumerate(run)
            if re.search(
                r"release_transition\.py (bump|commit-bump|push-bump|move-tag|advance-stable)", c
            )
            or "gh release create" in c
        )
        self.assertLess(notes, mutation)
        step = next(s for s in self.release_steps() if "--public-text" in s.get("run", ""))
        self.assertEqual("${{ github.token }}", step["env"]["GH_TOKEN"])

    def test_publication_binds_the_tag_and_the_token(self) -> None:
        step = next(s for s in self.release_steps() if "gh release create" in s.get("run", ""))
        self.assertEqual("${{ github.token }}", step["env"]["GH_TOKEN"])
        self.assertIn("--verify-tag", step["run"])
        self.assertIn('--notes-file "$NOTES_FILE"', step["run"])

    def test_the_commit_that_publishes_is_the_one_that_was_proven(self) -> None:
        final = next(c for c in commands("release") if "release_transition.py final" in c)
        self.assertIn('--mode "$MODE" --target "$TARGET"', final)
        self.assertIn("FINAL=$(", final)
        for name in ("push-bump", "advance-stable"):
            command = next(c for c in commands("release") if f"release_transition.py {name}" in c)
            self.assertIn('--final "$FINAL"', command)
            self.assertNotIn('--final "$TARGET"', command)
        move = next(c for c in commands("release") if "release_transition.py move-tag" in c)
        self.assertIn('--tag "$TAG" --final "$FINAL"', move)


class GateParityTest(unittest.TestCase):
    """What the credential-free jobs run, pinned beyond the `uses:` lines."""

    def test_triggers_and_runner_are_exact(self) -> None:
        workflow = load(RELEASE)
        triggers = cast("dict[Any, Any]", workflow).get(True) or workflow["on"]
        self.assertEqual(
            ["v[0-9]+.[0-9]+.[0-9]+", "[0-9]+.[0-9]+.[0-9]+"], triggers["push"]["tags"]
        )
        for name, job in jobs().items():
            self.assertEqual("ubuntu-24.04", job["runs-on"], name)

    def test_the_frontend_verifier_runs_the_gates_commands_in_order(self) -> None:
        run = commands("verify-frontend")
        expected = [
            "assert-head",
            "node -e",
            "pnpm install --frozen-lockfile --ignore-scripts",
            "pnpm lint",
            "pnpm typecheck",
            "pnpm test",
            "pnpm build:check",
            "pnpm exec playwright install --with-deps chromium",
            "pnpm test:parser",
            "pnpm test:installed",
            "git status --porcelain",
            "git rev-parse HEAD",
        ]
        self.assertEqual(len(expected), len(run), run)
        for fragment, command in zip(expected, run, strict=True):
            self.assertIn(fragment, command)
        for command in run:
            self.assertNotIn("|| true", command)
        for step in steps("verify-frontend"):
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn("if", step)
        recording = next(s for s in steps("verify-frontend") if s.get("id") == "verified")
        self.assertIn('[ "$SHA" != "$TARGET" ]', recording["run"])
        self.assertIn("exit 1", recording["run"])

    def test_the_installed_proof_gets_the_setup_python_interpreter(self) -> None:
        step = next(s for s in steps("verify-frontend") if s.get("run") == "pnpm test:installed")
        self.assertEqual(
            "${{ steps.python.outputs.python-path }}", step["env"]["CARGENTO_TEST_PYTHON"]
        )
        python = next(s for s in steps("verify-frontend") if s.get("id") == "python")
        self.assertEqual("3.11", python["with"]["python-version"])

    def test_the_tree_verifier_installs_before_it_validates_on_the_same_python(self) -> None:
        listed = steps("verify-tree")
        names = [s.get("name") or s.get("uses") for s in listed]
        install = next(i for i, s in enumerate(listed) if "pip install" in s.get("run", ""))
        setup = next(i for i, s in enumerate(listed) if "setup-python" in s.get("uses", ""))
        suite = next(i for i, s in enumerate(listed) if "unittest discover" in s.get("run", ""))
        self.assertLess(setup, install, names)
        self.assertLess(install, suite, names)
        self.assertEqual("3.12", listed[setup]["with"]["python-version"])
        for index in (setup, install, suite):
            self.assertEqual("env.MODE == 'fresh'", listed[index]["if"])
        text = listed[install]["run"]
        self.assertIn("--requirement requirements-validation.txt", text)
        run = listed[suite]["run"]
        for command in (
            "python3 scripts/validate_plugins.py",
            "python3 -m unittest scripts/tests/test_validate_plugins.py",
            "python3 -m unittest scripts/tests/test_bump_version.py",
            "python3 -m unittest discover -s cargento/skills/cargento/tests -t .",
        ):
            self.assertIn(command, run)
        self.assertNotIn("continue-on-error", listed[suite])

    def test_resolve_hands_only_validated_values_to_later_jobs(self) -> None:
        resolve = next(s for s in steps("resolve") if s.get("id") == "resolve")
        self.assertIn('--tag "$TAG"', resolve["run"])
        self.assertIn('--github-output "$GITHUB_OUTPUT"', resolve["run"])
        self.assertEqual({"TAG": "${{ github.ref_name }}"}, resolve["env"])


if __name__ == "__main__":
    unittest.main()
