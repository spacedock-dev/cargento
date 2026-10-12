"""Release 1 must not ship the temporary rename compatibility layer."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
MARKER = "legacy-cargento: remove at 1.0.0"
EXCLUDED = {Path(__file__).relative_to(ROOT).as_posix()}
SITES = {
    "compass-droid/hooks/event_hook.py": (
        "default_home",
        "state_home",
        "legacy_read_path",
        "state_file",
    ),
    "compass-gemini/hooks/event_hook.py": (
        "default_home",
        "state_home",
        "legacy_read_path",
        "state_file",
    ),
    "compass/skills/compass/agy_hook.py": (
        "default_home",
        "state_home",
        "legacy_read_path",
        "capability",
    ),
    "compass/skills/compass/compass_runtime/annotations.py": (
        "store_path",
        "_sweep_other_spelling",
    ),
    "compass/skills/compass/compass_runtime/config.py": (
        "environment_value",
        "default_home",
        "legacy_read_path",
        "state_file_paths",
        "remove_state_shadows",
    ),
    "compass/skills/compass/compass_runtime/copied_corrections.py": ("store_path",),
    "compass/skills/compass/compass_runtime/deliveries.py": ("store_path",),
    "compass/skills/compass/compass_runtime/departures.py": (
        "store_path",
        "_withdraw_other_spelling",
    ),
    "compass/skills/compass/compass_runtime/diagnostics.py": ("diagnose", "render_diagnosis"),
    "compass/skills/compass/compass_runtime/dismissals.py": ("store_path",),
    "compass/skills/compass/compass_runtime/ends.py": ("store_path",),
    "compass/skills/compass/compass_runtime/history.py": ("store_path",),
    "compass/skills/compass/compass_runtime/lifecycle.py": ("state_path", "_state_prefix"),
    "compass/skills/compass/compass_runtime/reading_policy.py": ("store_path",),
    "compass/skills/compass/compass_runtime/tripwires.py": ("store_path",),
    "compass/skills/compass/event_hook.py": (
        "default_home",
        "state_home",
        "legacy_read_path",
        "state_file",
    ),
    "compass/skills/compass/mcp_server.py": (
        "default_home",
        "state_home",
        "legacy_read_path",
        "_published_ports",
    ),
    "compass/skills/compass/statusline_hook.py": (
        "default_home",
        "state_home",
        "legacy_read_path",
        "capability",
    ),
    "scripts/legacy_paths.py": ("environment_value", "default_home"),
    "scripts/ordinary_turn_driver.py": ("validate_runtime",),
}
TEXT_SITES = {
    ".github/workflows/version-guard.yml": 1,
    "compass-droid/hooks/event_hook.py": 4,
    "compass-gemini/hooks/event_hook.py": 4,
    "compass/skills/compass/agy_hook.py": 4,
    "compass/skills/compass/compass_runtime/annotations.py": 5,
    "compass/skills/compass/compass_runtime/config.py": 5,
    "compass/skills/compass/compass_runtime/copied_corrections.py": 2,
    "compass/skills/compass/compass_runtime/deliveries.py": 2,
    "compass/skills/compass/compass_runtime/departures.py": 5,
    "compass/skills/compass/compass_runtime/diagnostics.py": 4,
    "compass/skills/compass/compass_runtime/dismissals.py": 2,
    "compass/skills/compass/compass_runtime/ends.py": 2,
    "compass/skills/compass/compass_runtime/history.py": 2,
    "compass/skills/compass/compass_runtime/lifecycle.py": 2,
    "compass/skills/compass/compass_runtime/reading_policy.py": 2,
    "compass/skills/compass/compass_runtime/tripwires.py": 2,
    "compass/skills/compass/event_hook.py": 4,
    "compass/skills/compass/mcp_server.py": 4,
    "compass/skills/compass/opencode_plugin.js": 6,
    "compass/skills/compass/pi_extension.js": 6,
    "compass/skills/compass/statusline_hook.py": 4,
    "frontend/src/storage/backend.ts": 3,
    "frontend/src/storage/keys.ts": 1,
    "scripts/legacy_paths.py": 2,
    "scripts/ordinary_turn_driver.py": 1,
}


def effective_version(root: Path, environ: dict[str, str]) -> tuple[int, int, int]:
    plugin = json.loads((root / "compass/.claude-plugin/plugin.json").read_text())["version"]
    versions = [tuple(int(part) for part in plugin.split("."))]
    for tag in (
        environ.get("GITHUB_REF_NAME", ""),
        environ.get("GITHUB_REF", "").removeprefix("refs/tags/")
        if environ.get("GITHUB_REF", "").startswith("refs/tags/")
        else "",
    ):
        if re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+", tag):
            versions.append(tuple(int(part) for part in tag.removeprefix("v").split(".")))  # noqa: PERF401 - version candidates
    version = max(versions)
    return version[0], version[1], version[2]


def assert_removed(root: Path, environ: dict[str, str]) -> None:
    try:
        result = subprocess.run(
            [shutil.which("git") or "git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
        )
        paths = {root / path for path in result.stdout.decode().split("\0") if path}
        # Newly introduced runtime helpers are checked before this uncommitted
        # rename is staged too. At release time these are already tracked.
        paths.update(root / path for path in TEXT_SITES)
    except (OSError, subprocess.CalledProcessError):
        paths = {
            p for p in root.rglob("*") if ".git" not in p.parts and "node_modules" not in p.parts
        }
    found: list[str] = []
    for path in sorted(paths):
        if not path.is_file() or path.relative_to(root).as_posix() in EXCLUDED:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        found.extend(
            f"{path.relative_to(root)}:{n}" for n, line in enumerate(lines, 1) if MARKER in line
        )
    if effective_version(root, environ)[0] >= 1 and found:
        raise AssertionError(
            "Remove the listed fallbacks before releasing 1.0.0: " + ", ".join(found)
        )


class LegacyRemovalTest(unittest.TestCase):
    def tree(self, version: str, *, markers: bool) -> Path:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        manifest = root / "compass/.claude-plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"version": version}))
        (root / "source.py").write_text("pass\n" + ("# " + MARKER + "\n" if markers else ""))
        (root / "adapter.js").write_text("export {};\n")
        return root

    def test_a_reader_installing_major_one_gets_no_temporary_fallbacks(self) -> None:
        assert_removed(ROOT, dict(os.environ))

    def test_a_release_owner_can_ship_a_clean_major_one_tree(self) -> None:
        root = self.tree("1.0.0", markers=False)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(__name__ + ".ROOT", root):
            self.test_a_reader_installing_major_one_gets_no_temporary_fallbacks()
            with self.assertRaisesRegex(unittest.SkipTest, "At 1.0.0 or later"):
                self.test_a_maintainer_cannot_hide_a_fallback_by_deleting_its_marker()

    def test_a_release_owner_is_shown_remaining_fallbacks_without_git(self) -> None:
        root = self.tree("1.0.0", markers=True)
        with (
            mock.patch.object(subprocess, "run", side_effect=OSError("no git")),
            self.assertRaisesRegex(AssertionError, "Remove the listed fallbacks.*source.py"),
        ):
            assert_removed(root, {})

    def test_a_release_owner_cannot_ship_fallbacks_by_tagging_an_unbumped_tree(self) -> None:
        for env in (
            {"GITHUB_REF_NAME": "v1.0.0"},
            {"GITHUB_REF_NAME": "1.0.0"},
            {"GITHUB_REF": "refs/tags/v1.0.0"},
        ):
            with self.subTest(environment=env):
                with self.assertRaisesRegex(AssertionError, "Remove the listed fallbacks"):
                    assert_removed(self.tree("0.28.0", markers=True), env)
                assert_removed(self.tree("0.28.0", markers=False), env)

    def test_a_release_owner_uses_the_higher_version_and_ignores_non_tag_names(self) -> None:
        root = self.tree("0.28.0", markers=True)
        for env in ({}, {"GITHUB_REF_NAME": "main"}, {"GITHUB_REF": "refs/heads/v1.0.0"}):
            assert_removed(root, env)
        with self.assertRaisesRegex(AssertionError, "Remove the listed fallbacks"):
            assert_removed(self.tree("1.0.0", markers=True), {"GITHUB_REF_NAME": "v0.28.0"})

    def test_a_maintainer_can_delete_marked_python_arms_without_breaking_current_code(self) -> None:
        for relative in TEXT_SITES:
            if not relative.endswith(".py"):
                continue
            with self.subTest(source=relative):
                if not (ROOT / relative).is_file():
                    continue
                source = (ROOT / relative).read_text()
                lines = source.splitlines(keepends=True)
                nodes = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.stmt)]
                removed = set()
                for number, line in enumerate(lines, 1):
                    if MARKER not in line:
                        continue
                    if not line.lstrip().startswith("#"):
                        # Inline sites are extra tuple members or import aliases.
                        removed.add(number)
                        continue
                    statement = min(
                        (node for node in nodes if node.lineno > number),
                        key=lambda node: (node.lineno, -(node.end_lineno or node.lineno)),
                    )
                    removed.update(range(number, (statement.end_lineno or statement.lineno) + 1))
                current = "".join(
                    line for number, line in enumerate(lines, 1) if number not in removed
                )
                compile(current, relative, "exec")

    def test_a_maintainer_cannot_hide_a_fallback_by_deleting_its_marker(self) -> None:
        if effective_version(ROOT, dict(os.environ))[0] >= 1:
            self.skipTest("At 1.0.0 or later fallback sites must be removed, not preserved.")
        for relative, names in SITES.items():
            source = (ROOT / relative).read_text()
            lines = source.splitlines()
            functions = [
                n
                for n in ast.walk(ast.parse(source))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            for name in names:
                with self.subTest(site=f"{relative}:{name}"):
                    candidates = [n for n in functions if n.name == name]
                    self.assertTrue(candidates)
                    self.assertTrue(
                        any(
                            MARKER in "\n".join(lines[n.lineno - 1 : n.end_lineno])
                            for n in candidates
                        )
                    )
        for relative, count in TEXT_SITES.items():
            with self.subTest(site=relative):
                self.assertEqual(count, (ROOT / relative).read_text().count(MARKER))
