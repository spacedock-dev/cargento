"""Negative and rendering tests for the repository plugin validator."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_plugins as validator


class ValidatorTests(unittest.TestCase):
    def write_temp(self, body: str, name: str = "fixture.yaml") -> Path:
        directory = Path(tempfile.mkdtemp(prefix="cargento-validator-"))
        path = directory / name
        path.write_text(body)
        self.addCleanup(directory.rmdir)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def copy_plugin(self) -> Path:
        """A complete installed copy of the plugin, outside the checkout."""
        destination = Path(tempfile.mkdtemp(prefix="cargento-installed-")) / "cargento"
        shutil.copytree(validator.ROOT / "cargento", destination)
        self.addCleanup(shutil.rmtree, destination.parent, ignore_errors=True)
        return destination

    def test_a_complete_installed_copy_passes_the_runtime_inventory(self) -> None:
        validation = validator.Validation()

        validator.validate_runtime_files(self.copy_plugin(), validation)

        self.assertEqual([], validation.errors)

    def test_every_required_runtime_file_category_is_caught_when_missing(self) -> None:
        # One representative per category the plan names, each deleted only
        # inside its own temporary copy. The whole point of an explicit
        # inventory is that an omission is reported rather than inferred, so
        # each case asserts the precise relative path comes back.
        categories = {
            "launcher": "skills/cargento/server.py",
            "hook forwarder": "skills/cargento/notify_hook.py",
            "package initializer": "skills/cargento/cargento_runtime/__init__.py",
            "runtime module": "skills/cargento/cargento_runtime/cli.py",
            "collector": "skills/cargento/cargento_runtime/collectors/goose.py",
            "frontend asset": "skills/cargento/cargento_runtime/web/next-boot.js",
        }
        for category, relative in categories.items():
            with self.subTest(category=category):
                plugin_root = self.copy_plugin()
                (plugin_root / relative).unlink()
                validation = validator.Validation()

                validator.validate_runtime_files(plugin_root, validation)

                self.assertTrue(
                    any(relative in error and "is missing" in error for error in validation.errors),
                    f"{category} not reported: {validation.errors}",
                )

    def test_a_directory_where_a_runtime_file_belongs_is_rejected(self) -> None:
        # exists() would call this present, and the failure would then surface
        # as an ImportError from an installed copy instead of here.
        plugin_root = self.copy_plugin()
        target = plugin_root / "skills/cargento/cargento_runtime/config.py"
        target.unlink()
        target.mkdir()
        validation = validator.Validation()

        validator.validate_runtime_files(plugin_root, validation)

        self.assertTrue(
            any("must be a file, not a directory" in error for error in validation.errors),
            validation.errors,
        )

    def test_the_inventory_covers_every_shipped_runtime_file(self) -> None:
        # The inventory is hand-written so it can notice an omission, which means
        # it can also fall behind. Compare it against what the checkout actually
        # ships: a new runtime module or asset must be added here deliberately.
        skill = validator.ROOT / "cargento" / "skills" / "cargento"
        # Discovered rather than listed. The top-level scripts were named here by
        # hand, and adding `event_hook.py` beside them failed this test for the
        # right reason but in the wrong place: the inventory is the thing meant to
        # be deliberate, not this test's idea of what exists. `glob`, not `rglob`,
        # so `tests/` and `agents/` stay out.
        plugin_root = validator.ROOT / "cargento"
        shipped = {path.relative_to(plugin_root).as_posix() for path in skill.glob("*.py")}
        # Hook definitions count too. They are not read by the dashboard, but they
        # fail the same way: absent from an install, the harness registers no hooks
        # and reports no events, silently. Both locations, because the harnesses
        # disagree: Claude and Codex read files under `hooks/`, Antigravity reads a
        # root `hooks.json`.
        shipped |= {
            path.relative_to(plugin_root).as_posix()
            for path in (plugin_root / "hooks").glob("*.json")
        }
        shipped |= {path.name for path in plugin_root.glob("hooks.json") if path.is_file()}
        for path in (skill / "cargento_runtime").rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix in {".py", ".html", ".css", ".js", ".b64", ".txt"}:
                shipped.add(path.relative_to(validator.ROOT / "cargento").as_posix())

        self.assertEqual(sorted(shipped), sorted(validator.CARGENTO_RUNTIME_FILES))

    def test_frontmatter_rejects_malformed_flow_yaml(self) -> None:
        path = self.write_temp(
            "---\nname: broken\ndescription: [unterminated\n---\nbody\n", "SKILL.md"
        )
        validation = validator.Validation()

        self.assertIsNone(validator.parse_frontmatter(path, validation))
        self.assertTrue(any("invalid frontmatter YAML" in error for error in validation.errors))

    def test_frontmatter_rejects_duplicate_keys(self) -> None:
        path = self.write_temp(
            "---\nname: first\nname: second\ndescription: Duplicate\n---\n", "SKILL.md"
        )
        validation = validator.Validation()

        self.assertIsNone(validator.parse_frontmatter(path, validation))
        self.assertTrue(any("duplicate key" in error for error in validation.errors))

    def test_openai_metadata_rejects_invalid_escape(self) -> None:
        path = self.write_temp(
            'interface:\n  display_name: "Bad\\qEscape"\n'
            '  short_description: "A sufficiently long description"\n'
            '  default_prompt: "Use $broken to help."\n',
            "openai.yaml",
        )
        validation = validator.Validation()

        self.assertIsNone(validator.parse_openai_metadata(path, validation))
        self.assertTrue(
            any("invalid agents/openai.yaml YAML" in error for error in validation.errors)
        )

    def test_catalog_estimate_includes_namespace_and_locator(self) -> None:
        path = validator.ROOT / "cargento/skills/cargento/SKILL.md"
        line = validator.render_catalog_estimate_line("cargento", "cargento", "Map agents.", path)

        self.assertEqual(
            line,
            "- cargento:cargento: Map agents. (file: cargento/skills/cargento/SKILL.md)",
        )
        self.assertEqual(validator.approx_token_count("12345"), 2)

    def test_frontmatter_rejects_non_string_license(self) -> None:
        path = self.write_temp(
            "---\nname: broken\ndescription: Broken\nlicense: [MIT]\n---\n", "SKILL.md"
        )
        validation = validator.Validation()

        validator.parse_frontmatter(path, validation)

        self.assertTrue(any("license must be a string" in error for error in validation.errors))

    def test_the_shipped_skill_declares_every_distributed_license(self) -> None:
        path = validator.ROOT / "cargento" / "skills" / "cargento" / "SKILL.md"
        validation = validator.Validation()

        metadata = validator.parse_frontmatter(path, validation)

        self.assertEqual([], validation.errors)
        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(
            validator.SHIPPED_SKILL_LICENSES[("cargento", "cargento")],
            metadata["license"],
        )

    def test_cargento_rejects_an_incomplete_license_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "cargento"
            skill = plugin / "skills" / "cargento"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: cargento\ndescription: Map local agents.\nlicense: Apache-2.0\n---\n",
                encoding="utf-8",
            )
            validation = validator.Validation()

            with mock.patch.object(
                validator,
                "render_catalog_estimate_line",
                return_value="- cargento:cargento: Map local agents.",
            ):
                validator.validate_skills(plugin, validation)

        self.assertTrue(
            any(
                "frontmatter license must be 'Apache-2.0 AND OFL-1.1'" in error
                for error in validation.errors
            ),
            validation.errors,
        )

    def test_openai_metadata_rejects_invalid_optional_types(self) -> None:
        path = self.write_temp(
            "interface:\n"
            '  display_name: "Broken"\n'
            '  short_description: "A sufficiently long description"\n'
            "  icon_small: 123\n"
            '  default_prompt: "Use $broken to help."\n'
            "dependencies: bogus\n"
            "policy: 42\n",
            "openai.yaml",
        )
        validation = validator.Validation()

        validator.parse_openai_metadata(path, validation)

        self.assertTrue(any("icon_small" in error for error in validation.errors))
        self.assertTrue(
            any("dependencies must be a mapping" in error for error in validation.errors)
        )
        self.assertTrue(any("policy must be a mapping" in error for error in validation.errors))

    def test_antigravity_manifest_requires_runtime_marker_at_plugin_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            nested_manifest = plugin_root / ".gemini-plugin/plugin.json"
            nested_manifest.parent.mkdir(parents=True)
            nested_manifest.write_text(
                '{"name":"fixture-plugin","version":"1.0.0","description":"Fixture"}\n'
            )
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", Path(directory)):
                manifest = validator.validate_antigravity_manifest(plugin_root, validation)

            self.assertIsNone(manifest)
            self.assertTrue(
                any(
                    "plugin.json" in error and "cannot read file" in error
                    for error in validation.errors
                )
            )

    def test_the_gemini_extension_lives_in_its_own_root(self) -> None:
        # And specifically *not* in the plugin root. Sharing one root is what made
        # a Gemini session load Claude's hooks/hooks.json, warn about eight event
        # names it does not know, and run two hooks that failed: both harnesses
        # read `<root>/hooks/hooks.json` and neither lets that path be moved.
        gemini_root = validator.ROOT / validator.GEMINI_EXTENSION_ROOT
        self.assertTrue((gemini_root / "gemini-extension.json").is_file())
        for plugin_name in validator.PLUGIN_NAMES:
            with self.subTest(plugin=plugin_name):
                self.assertFalse(
                    (validator.ROOT / plugin_name / "gemini-extension.json").is_file(),
                    "the plugin root must not also be a Gemini extension",
                )

    def test_the_gemini_extension_is_self_contained(self) -> None:
        # `gemini extensions install` copies the directory and a git-URL install
        # clones it, so a hook command reaching outside this root would not resolve
        # once installed.
        gemini_root = validator.ROOT / validator.GEMINI_EXTENSION_ROOT
        for relative in validator.GEMINI_EXTENSION_FILES:
            with self.subTest(file=relative):
                self.assertTrue((gemini_root / relative).is_file())

    def test_antigravity_manifest_rejects_unknown_fields_and_name_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            plugin_root.mkdir()
            (plugin_root / "plugin.json").write_text(
                '{"name":"other-name","description":"Fixture","version":"1.0.0"}\n'
            )
            validation = validator.Validation()

            validator.validate_antigravity_manifest(plugin_root, validation)

            self.assertTrue(
                any(
                    "unsupported Antigravity manifest fields" in error
                    for error in validation.errors
                )
            )
            self.assertTrue(
                any("name must match the plugin directory" in error for error in validation.errors)
            )

    def test_gemini_extension_rejects_missing_version_and_bad_mcp_server(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            plugin_root.mkdir()
            (plugin_root / "gemini-extension.json").write_text(
                '{"name":"fixture-plugin","description":"Fixture",'
                '"mcpServers":{"fixture":{"transport":"sse"}}}\n'
            )
            validation = validator.Validation()

            validator.validate_gemini_extension(plugin_root, "fixture-plugin", validation)

            self.assertTrue(
                any("version must be a non-empty string" in error for error in validation.errors)
            )
            self.assertTrue(any("needs a url or command" in error for error in validation.errors))

    def test_the_gemini_manifest_name_is_the_plugin_name_not_the_directory(self) -> None:
        # The extension installs and lists as `cargento`, while its directory is
        # `cargento-gemini` so its hooks file cannot collide with Claude's. Tying
        # the name to the directory would force one of those two to be wrong.
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            extension_root = Path(directory) / "cargento-gemini"
            extension_root.mkdir()
            (extension_root / "gemini-extension.json").write_text(
                '{"name":"cargento","description":"Fixture","version":"1.0.0"}\n'
            )
            validation = validator.Validation()

            validator.validate_gemini_extension(extension_root, "cargento", validation)

            self.assertEqual(
                [],
                [error for error in validation.errors if "name must be" in error],
                "the directory name must not be required to match",
            )

    def test_mcp_endpoint_parity_rejects_drift_and_missing_antigravity_config(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            plugin_root.mkdir()
            (plugin_root / ".mcp.json").write_text(
                '{"mcpServers":{"fixture":{"type":"sse","url":"http://localhost:9090/sse"}}}\n'
            )
            gemini_manifest = {"mcpServers": {"fixture": {"url": "http://localhost:8081/sse"}}}
            validation = validator.Validation()

            validator.validate_mcp_endpoint_parity(plugin_root, gemini_manifest, None, validation)

            self.assertTrue(
                any(
                    "gemini-extension.json" in error and "must mirror" in error
                    for error in validation.errors
                )
            )
            self.assertTrue(
                any(
                    "mcp_config.json" in error and "must exist" in error
                    for error in validation.errors
                )
            )

    def test_mcp_endpoint_parity_rejects_runtime_endpoints_without_base(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            plugin_root.mkdir()
            gemini_manifest = {"mcpServers": {"rogue": {"url": "http://localhost:9999/sse"}}}
            mcp_config = {"mcpServers": {"rogue": {"serverUrl": "http://localhost:9999/sse"}}}
            validation = validator.Validation()

            validator.validate_mcp_endpoint_parity(
                plugin_root, gemini_manifest, mcp_config, validation
            )

            self.assertTrue(
                any(
                    "gemini-extension.json" in error and "no .mcp.json to mirror" in error
                    for error in validation.errors
                )
            )
            self.assertTrue(
                any(
                    "mcp_config.json" in error and "no .mcp.json to mirror" in error
                    for error in validation.errors
                )
            )

    def test_antigravity_mcp_config_rejects_missing_or_blank_server_url(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            plugin_root.mkdir()
            (plugin_root / "mcp_config.json").write_text(
                '{"mcpServers":{"fixture":{"url":"http://localhost:8081/sse"},"blank":{"serverUrl":"  "}}}\n'
            )
            validation = validator.Validation()

            validator.validate_antigravity_mcp_config(plugin_root, validation)

            self.assertTrue(
                any(
                    "'fixture' must define a non-empty serverUrl" in error
                    for error in validation.errors
                )
            )
            self.assertTrue(
                any(
                    "'blank' must define a non-empty serverUrl" in error
                    for error in validation.errors
                )
            )

            (plugin_root / "mcp_config.json").write_text('{"mcpServers":{}}\n')
            validation = validator.Validation()

            validator.validate_antigravity_mcp_config(plugin_root, validation)

            self.assertTrue(
                any("mcpServers must be a non-empty object" in error for error in validation.errors)
            )

    def test_mcp_endpoint_parity_accepts_matching_endpoints(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            plugin_root.mkdir()
            (plugin_root / ".mcp.json").write_text(
                '{"mcpServers":{"fixture":{"type":"sse","url":"http://localhost:8081/sse"}}}\n'
            )
            gemini_manifest = {"mcpServers": {"fixture": {"url": "http://localhost:8081/sse"}}}
            mcp_config = {"mcpServers": {"fixture": {"serverUrl": "http://localhost:8081/sse"}}}
            validation = validator.Validation()

            validator.validate_mcp_endpoint_parity(
                plugin_root, gemini_manifest, mcp_config, validation
            )

            self.assertEqual(validation.errors, [])

    def test_a_bundled_hook_command_must_reference_a_script_that_ships(self) -> None:
        # This replaced a byte-parity rule between hooks/hooks.json and the root
        # hooks.json. Parity assumed one file could serve both Claude and
        # Antigravity, which stopped being true once the command named its
        # harness. The check that matters is the one parity never made: a hooks
        # file pointing at a missing script installs cleanly and reports nothing.
        command = 'python3 "${CLAUDE_PLUGIN_ROOT}/skills/cargento/event_hook.py" claude'
        document = {
            "hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": command}]}]}
        }
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            (plugin_root / "hooks").mkdir(parents=True)
            (plugin_root / "skills/cargento").mkdir(parents=True)
            (plugin_root / "hooks/hooks.json").write_text(json.dumps(document))

            validation = validator.Validation()
            validator.validate_hooks_adapter(plugin_root, validation)
            self.assertTrue(
                any(
                    "references missing skills/cargento/event_hook.py" in e
                    for e in validation.errors
                ),
                validation.errors,
            )

            (plugin_root / "skills/cargento/event_hook.py").write_text("#\n")
            validation = validator.Validation()
            validator.validate_hooks_adapter(plugin_root, validation)
            self.assertEqual([], validation.errors)

    def test_a_bundled_hooks_file_registering_nothing_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            (plugin_root / "hooks").mkdir(parents=True)
            (plugin_root / "hooks/hooks.json").write_text('{"hooks": {}}')

            validation = validator.Validation()
            validator.validate_hooks_adapter(plugin_root, validation)

            self.assertTrue(any("registers no events" in e for e in validation.errors))

    def test_two_harnesses_may_bundle_different_hooks_files(self) -> None:
        # The whole point of dropping parity. Claude fires UserPromptSubmit and
        # SessionEnd; Antigravity fires PreInvocation and PostInvocation. A
        # mirrored file would also make Antigravity post as Claude, where the id
        # gets truncated by Claude's normalizer and matches no row.
        def document(event: str, harness: str) -> str:
            command = f'python3 "${{PLUGIN_ROOT}}/skills/cargento/event_hook.py" {harness}'
            return json.dumps(
                {
                    "hooks": {
                        event: [{"matcher": "", "hooks": [{"type": "command", "command": command}]}]
                    }
                }
            )

        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            (plugin_root / "hooks").mkdir(parents=True)
            (plugin_root / "skills/cargento").mkdir(parents=True)
            (plugin_root / "skills/cargento/event_hook.py").write_text("#\n")
            (plugin_root / "hooks/hooks.json").write_text(document("UserPromptSubmit", "claude"))
            (plugin_root / "hooks.json").write_text(document("PostInvocation", "antigravity"))

            validation = validator.Validation()
            validator.validate_hooks_adapter(plugin_root, validation)

            self.assertEqual([], validation.errors)

    def test_description_parity_rejects_drifted_manifests(self) -> None:
        validation = validator.Validation()

        validator.validate_description_parity(
            "fixture-plugin",
            {
                ".claude-plugin/plugin.json": "Long canonical description",
                "gemini-extension.json": "Short variant",
                "plugin.json": None,
            },
            validation,
        )

        self.assertTrue(any("description drift" in error for error in validation.errors))

        validation = validator.Validation()
        validator.validate_description_parity(
            "fixture-plugin",
            {
                ".claude-plugin/plugin.json": "Same description",
                "gemini-extension.json": "Same description",
                "plugin.json": None,
            },
            validation,
        )

        self.assertEqual(validation.errors, [])

    def test_claude_manifest_name_must_match_plugin_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            root = Path(directory)
            (root / ".agents/plugins").mkdir(parents=True)
            (root / ".agents/plugins/marketplace.json").write_text(
                '{"plugins":[{"name":"cargento",'
                '"source":{"source":"local","path":"./cargento"}}]}\n'
            )
            (root / "cargento/.claude-plugin").mkdir(parents=True)
            (root / "cargento/.claude-plugin/plugin.json").write_text(
                '{"name":"wrong-plugin-name","version":"0.1.0","description":"Desc"}\n'
            )
            manifest = {"version": "0.1.0", "description": "Desc"}
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", root):
                validator.validate_marketplaces(
                    {"cargento": dict(manifest)},
                    {"cargento": dict(manifest)},
                    {"cargento": {"description": "Desc"}},
                    validation,
                )

            self.assertTrue(
                any(
                    ".claude-plugin/plugin.json" in error
                    and "name must match the plugin directory" in error
                    for error in validation.errors
                )
            )

    def test_error_labels_use_forward_slashes_on_every_platform(self) -> None:
        # resolve() rewrites 8.3 short names on Windows and /var -> /private/var
        # on macOS, so a path inside ROOT can still fail relative_to(). The
        # fallback must not leak native separators into the error text.
        with tempfile.TemporaryDirectory(prefix="cargento-validator-label-") as directory:
            root = Path(directory)
            nested = root / "cargento" / ".claude-plugin" / "plugin.json"
            nested.parent.mkdir(parents=True)
            nested.write_text("{}\n")
            validation = validator.Validation()
            with mock.patch.object(validator, "ROOT", root):
                validation.error(nested, "boom")
            # Inside a resolved ROOT: label is relative.
            self.assertEqual(["cargento/.claude-plugin/plugin.json: boom"], validation.errors)

            # Outside ROOT: still forward slashes, never backslashes.
            outside = validator.Validation()
            with mock.patch.object(validator, "ROOT", root / "elsewhere"):
                outside.error(nested, "boom")
        self.assertEqual(1, len(outside.errors))
        self.assertNotIn("\\", outside.errors[0])
        self.assertIn("cargento/.claude-plugin/plugin.json", outside.errors[0])

    def test_manifest_version_drift_is_rejected(self) -> None:
        """cargento has no marketplace of its own any more (it is listed in
        spacedock-dev/marketplace), so parity is asserted straight across the
        three shipped manifests."""
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            root = Path(directory)
            (root / ".agents/plugins").mkdir(parents=True)
            (root / ".agents/plugins/marketplace.json").write_text(
                '{"plugins":[{"name":"cargento",'
                '"source":{"source":"local","path":"./cargento"}}]}\n'
            )
            (root / "cargento/.claude-plugin").mkdir(parents=True)
            (root / "cargento/.claude-plugin/plugin.json").write_text(
                '{"name":"cargento","version":"0.1.0","description":"Desc"}\n'
            )
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", root):
                validator.validate_marketplaces(
                    {"cargento": {"version": "9.9.9", "description": "Desc"}},
                    {"cargento": {"version": "0.1.0", "description": "Desc"}},
                    {"cargento": {"description": "Desc"}},
                    validation,
                )

            self.assertTrue(
                any("version fields are not in parity" in error for error in validation.errors)
            )

    def test_markdown_link_rejects_missing_bundled_resource(self) -> None:
        path = self.write_temp("Read [the bundled reference](../missing/file.md).\n", "SKILL.md")
        validation = validator.Validation()

        validator.validate_markdown_links(path, validation)

        self.assertTrue(any("Markdown link" in error for error in validation.errors))

    def test_validate_skills_reports_non_string_required_fields_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            skill_root = plugin_root / "skills/broken"
            (skill_root / "agents").mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\nname: [broken]\ndescription: Broken fixture\n---\n"
            )
            (skill_root / "agents/openai.yaml").write_text(
                "interface:\n"
                '  display_name: "Broken"\n'
                '  short_description: "A sufficiently long description"\n'
                "  default_prompt: 42\n"
            )
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", Path(directory)):
                validator.validate_skills(plugin_root, validation)

            self.assertTrue(any("name must use lowercase" in error for error in validation.errors))
            self.assertTrue(any("default_prompt" in error for error in validation.errors))

    def test_bundled_markdown_rejects_host_specific_skill_api(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            skill_root = plugin_root / "skills/broken"
            (skill_root / "agents").mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\nname: broken\ndescription: Broken fixture\n---\n"
            )
            (skill_root / "reference.md").write_text(
                'Invoke Skill(skill="fixture:security-review", args="files").\n'
            )
            (skill_root / "agents/openai.yaml").write_text(
                "interface:\n"
                '  display_name: "Broken"\n'
                '  short_description: "A sufficiently long description"\n'
                '  default_prompt: "Use $broken to help."\n'
            )
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", Path(directory)):
                validator.validate_skills(plugin_root, validation)

            self.assertTrue(any("Skill(skill=" in error for error in validation.errors))

    def build_repo_docs(self, root: Path) -> None:
        """Write a minimal but complete stand-in for the repository's prose docs."""
        (root / ".github").mkdir(parents=True, exist_ok=True)
        (root / "docs").mkdir(parents=True, exist_ok=True)
        for name in validator.ROOT_DOCS:
            (root / name).write_text("Placeholder.\n", encoding="utf-8")

    def test_repo_docs_reject_dangling_relative_link(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-docs-") as directory:
            # Resolve as the real ROOT is: on macOS a temp path is under
            # /var, a symlink to /private/var, and link containment is
            # checked against a resolved target.
            root = Path(directory).resolve()
            self.build_repo_docs(root)
            (root / "README.md").write_text("See [the guide](docs/absent.md).\n", encoding="utf-8")
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", root):
                validator.validate_repo_docs(validation)

            self.assertTrue(
                any("docs/absent.md" in error for error in validation.errors), validation.errors
            )

    def test_repo_docs_reject_banned_loopback_spelling(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-docs-") as directory:
            # Resolve as the real ROOT is: on macOS a temp path is under
            # /var, a symlink to /private/var, and link containment is
            # checked against a resolved target.
            root = Path(directory).resolve()
            self.build_repo_docs(root)
            (root / "docs/design-example.md").write_text(
                "Open http://localhost:4553 to see it.\n", encoding="utf-8"
            )
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", root):
                validator.validate_repo_docs(validation)

            self.assertTrue(
                any("127.0.0.1:4553" in error for error in validation.errors), validation.errors
            )

    def test_repo_docs_reject_a_missing_owned_document(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-docs-") as directory:
            # Resolve as the real ROOT is: on macOS a temp path is under
            # /var, a symlink to /private/var, and link containment is
            # checked against a resolved target.
            root = Path(directory).resolve()
            self.build_repo_docs(root)
            (root / "SECURITY.md").unlink()
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", root):
                validator.validate_repo_docs(validation)

            self.assertTrue(
                any("SECURITY.md" in error for error in validation.errors), validation.errors
            )

    def slugs_for(self, body: str) -> set[str]:
        holder = tempfile.TemporaryDirectory(prefix="cargento-validator-slug-")
        self.addCleanup(holder.cleanup)
        path = Path(holder.name).resolve() / "doc.md"
        path.write_text(body, encoding="utf-8")
        return validator.heading_slugs(path)

    def test_heading_slugs_match_github_anchoring(self) -> None:
        """Each case is an anchor GitHub accepts; rejecting one is a false failure."""
        cases: list[tuple[str, str, set[str]]] = [
            ("plain ATX", "## Pre-PR Checks\n", {"pre-pr-checks"}),
            ("repeated heading", "# Same\n# Same\n# Same\n", {"same", "same-1", "same-2"}),
            ("non-ASCII letters", "# Café résumé\n", {"café-résumé"}),
            ("underscores survive", "# server_py notes\n", {"server_py-notes"}),
            ("Setext", "Title Here\n==========\n", {"title-here"}),
            ("indented up to three spaces", "   # Indented\n", {"indented"}),
            ("inline link collapses", "# [Install](README.md)\n", {"install"}),
            ("explicit HTML anchor", '<a name="manual"></a>\n', {"manual"}),
            (
                "punctuation dropped, spacing kept",
                "## D-1 — Scan every root; never pick one\n",
                {"d-1--scan-every-root-never-pick-one"},
            ),
        ]
        for label, body, expected in cases:
            with self.subTest(case=label):
                self.assertEqual(expected, self.slugs_for(body))

    def test_heading_slugs_ignore_code_and_frontmatter(self) -> None:
        """A `#` inside a fence is a shell comment; treating it as a heading
        invents an anchor that silently satisfies a dangling link."""
        for label, body in [
            ("backtick fence", "```bash\n# not a heading\n```\n"),
            ("tilde fence", "~~~\n# not a heading\n~~~\n"),
            ("frontmatter", "---\nname: x\ndescription: y\n---\n"),
        ]:
            with self.subTest(case=label):
                self.assertEqual(set(), self.slugs_for(body))

    def test_markdown_links_accept_valid_commonmark(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-links-") as directory:
            root = Path(directory).resolve()
            (root / "real.md").write_text("# Heading\n", encoding="utf-8")
            for label, body in [
                ("quoted title", '[x](real.md "the title")\n'),
                ("parenthesised title", "[x](real.md (the title))\n"),
                ("angle-bracket destination", "[x](<real.md>)\n"),
                ("image", "![alt](real.md)\n"),
                ("link inside a tilde fence", "~~~\n[x](absent.md)\n~~~\n"),
                ("fragment on a resolving target", "[x](real.md#heading)\n"),
            ]:
                with self.subTest(case=label):
                    (root / "doc.md").write_text(body, encoding="utf-8")
                    validation = validator.Validation()

                    with mock.patch.object(validator, "ROOT", root):
                        validator.validate_markdown_links(root / "doc.md", validation)

                    self.assertEqual([], validation.errors)

    def test_markdown_links_still_reject_real_breakage(self) -> None:
        """The permissiveness above must not blunt the checks that matter."""
        with tempfile.TemporaryDirectory(prefix="cargento-validator-links-") as directory:
            root = Path(directory).resolve()
            (root / "real.md").write_text("# Heading\n", encoding="utf-8")
            for label, body, fragment in [
                ("missing target", "[x](gone.md)\n", "does not exist"),
                ("escapes the repository", "[x](../../outside.md)\n", "escapes the repository"),
                ("dangling fragment", "[x](real.md#absent)\n", "anchor does not exist"),
                ("title does not excuse a miss", '[x](gone.md "t")\n', "does not exist"),
            ]:
                with self.subTest(case=label):
                    (root / "doc.md").write_text(body, encoding="utf-8")
                    validation = validator.Validation()

                    with mock.patch.object(validator, "ROOT", root):
                        validator.validate_markdown_links(root / "doc.md", validation)

                    self.assertTrue(
                        any(fragment in error for error in validation.errors), validation.errors
                    )

    def test_root_docs_lists_every_prose_doc_in_the_repository(self) -> None:
        """ROOT_DOCS is what decides coverage; a silent drop must fail here.

        Tracked files only: a gitignored export sitting at the repository
        root is a local artifact, not a prose doc the sync pass owns, and a
        filesystem glob failed here on any machine carrying one.
        CODE_OF_CONDUCT.md is excluded deliberately — it is verbatim upstream
        text that no sync pass may edit.
        """
        listing = subprocess.run(
            ["git", "-C", str(validator.ROOT), "ls-files", "*.md"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        expected = {name for name in listing.stdout.splitlines() if name and "/" not in name} - {
            "CODE_OF_CONDUCT.md"
        }
        expected.add(".github/PULL_REQUEST_TEMPLATE.md")

        self.assertEqual(expected, set(validator.ROOT_DOCS))

    def test_repo_docs_reject_a_dangling_heading_anchor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-docs-") as directory:
            root = Path(directory).resolve()
            self.build_repo_docs(root)
            (root / "AGENTS.md").write_text("## Pre-PR Checks\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[gone](AGENTS.md#removed-heading) and [here](#nowhere)\n", encoding="utf-8"
            )
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", root):
                validator.validate_repo_docs(validation)

            self.assertEqual(2, sum("anchor does not exist" in e for e in validation.errors))

    def test_repo_docs_accept_resolving_links_and_anchors(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-docs-") as directory:
            # Resolve as the real ROOT is: on macOS a temp path is under
            # /var, a symlink to /private/var, and link containment is
            # checked against a resolved target.
            root = Path(directory).resolve()
            self.build_repo_docs(root)
            (root / "docs/design-example.md").write_text("Rationale.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("## Pre-PR Checks\n", encoding="utf-8")
            (root / "README.md").write_text(
                "# Top\n"
                "See [design](docs/design-example.md) and [checks](AGENTS.md#pre-pr-checks)\n"
                "and [upstream](https://example.invalid/x.md) and [anchor](#top).\n",
                encoding="utf-8",
            )
            (root / ".github/PULL_REQUEST_TEMPLATE.md").write_text(
                "Run the suite in [AGENTS.md](../AGENTS.md#pre-pr-checks).\n", encoding="utf-8"
            )
            validation = validator.Validation()

            with mock.patch.object(validator, "ROOT", root):
                validator.validate_repo_docs(validation)

            self.assertEqual([], validation.errors)


if __name__ == "__main__":
    unittest.main()


class BundledHooksSchemaTests(unittest.TestCase):
    """The two hook schemas Cargento ships, which are not the same shape."""

    def _validate(self, document: object, *, ship_script: bool) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="cargento-hooks-schema-") as directory:
            plugin_root = Path(directory) / "plug"
            (plugin_root / "skills/cargento").mkdir(parents=True)
            if ship_script:
                (plugin_root / "skills/cargento/agy_hook.py").write_text("#\n")
            (plugin_root / "hooks.json").write_text(json.dumps(document))
            validation = validator.Validation()
            validator.validate_hooks_adapter(plugin_root, validation)
            return validation.errors

    def test_a_name_wrapped_antigravity_file_is_understood(self) -> None:
        # Antigravity's guide states that each top-level key is a hook NAME, with
        # the events one level inside it. This test previously asserted the
        # opposite -- that a file with event names at the top level was valid --
        # and that is how the shipped file came to be malformed: `agy plugin
        # validate` accepted it by counting keys without type-checking them, so
        # "Antigravity's own validator had just accepted it" was true and
        # meaningless. agy's runtime discards such a file. See
        # AntigravityHookNestingTests.
        document = {
            "cargento": {
                "PostToolUse": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": 'python3 "${PLUGIN_ROOT}/skills/cargento/agy_hook.py"',
                            }
                        ],
                    }
                ]
            }
        }
        self.assertEqual([], self._validate(document, ship_script=True))
        self.assertTrue(
            any("agy_hook.py" in e for e in self._validate(document, ship_script=False))
        )

    def test_a_flat_handler_list_is_walked_too(self) -> None:
        # Antigravity uses both layouts in one file: tool-scoped events group their
        # handlers under a matcher, loop-scoped events list them directly. A walker
        # that understood only the grouped form would check nothing in the flat
        # half, so a missing script there would ship unnoticed.
        document = {
            "cargento": {
                "PostInvocation": [
                    {
                        "type": "command",
                        "command": 'python3 "${PLUGIN_ROOT}/skills/cargento/agy_hook.py"',
                    }
                ]
            }
        }
        self.assertEqual([], self._validate(document, ship_script=True))
        self.assertTrue(
            any("agy_hook.py" in e for e in self._validate(document, ship_script=False)),
            "a flat handler's command went unchecked",
        )


class HookVocabularyTests(unittest.TestCase):
    """No bundled hooks file may register another harness's event names.

    The guard exists because the failure was real, not hypothetical. Before Gemini
    got its own extension root, a Gemini session loading Claude's `hooks/hooks.json`
    printed eight `Invalid hook event name` warnings, then ran the two names that do
    overlap and reported both as failed hooks. Nothing in the build noticed.
    """

    def _errors(self, relative: str, document: dict[str, Any], tmp: Path) -> list[str]:
        path = tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        validation = validator.Validation()
        with mock.patch.object(validator, "ROOT", tmp):
            validator.validate_hook_vocabulary(validation)
        return [str(message) for message in validation.errors]

    @staticmethod
    def _gemini_document(event: str = "BeforeAgent", harness: str = "gemini") -> dict[str, Any]:
        return {
            "hooks": {
                event: [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": (
                                    'python3 "${extensionPath}/hooks/event_hook.py" ' + harness
                                ),
                            }
                        ],
                    }
                ]
            }
        }

    def test_a_name_the_harness_knows_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self.assertEqual(
                [],
                self._errors("cargento-gemini/hooks/hooks.json", self._gemini_document(), tmp),
            )

    def test_a_foreign_event_name_is_rejected(self) -> None:
        # `UserPromptSubmit` is Claude's name for the same moment. Gemini skips it.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            errors = self._errors(
                "cargento-gemini/hooks/hooks.json",
                self._gemini_document(event="UserPromptSubmit"),
                tmp,
            )
            self.assertTrue(
                any("UserPromptSubmit" in message for message in errors),
                f"a foreign event name went unreported: {errors}",
            )

    def test_a_foreign_harness_argument_is_rejected(self) -> None:
        # The other half of the same bug: the file could carry Gemini's event names
        # and still post them to Claude's route, where Claude's normalizer
        # truncates the id to eight characters and it matches no row.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            errors = self._errors(
                "cargento-gemini/hooks/hooks.json",
                self._gemini_document(harness="claude"),
                tmp,
            )
            self.assertTrue(
                any("wrong route" in message for message in errors),
                f"a foreign harness argument went unreported: {errors}",
            )

    def test_every_bundled_hooks_file_in_the_repository_satisfies_its_vocabulary(self) -> None:
        # The shipped files themselves, not a fixture: this is what would have
        # failed before the split.
        validation = validator.Validation()
        validator.validate_hook_vocabulary(validation)
        self.assertEqual([], [str(message) for message in validation.errors])


class DuplicatedScriptTests(unittest.TestCase):
    """A script that ships twice stays byte-identical in both places."""

    def test_the_shipped_copies_match_today(self) -> None:
        validation = validator.Validation()
        validator.validate_duplicated_scripts(validation)
        self.assertEqual([], [str(message) for message in validation.errors])

    def test_drift_between_the_copies_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            for copy_relative, source_relative in validator.DUPLICATED_SCRIPTS:
                for relative, body in ((source_relative, "one"), (copy_relative, "two")):
                    path = tmp / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(body, encoding="utf-8")
            validation = validator.Validation()
            with mock.patch.object(validator, "ROOT", tmp):
                validator.validate_duplicated_scripts(validation)
            self.assertEqual(
                len(validator.DUPLICATED_SCRIPTS),
                len(validation.errors),
                "each drifted copy must be reported",
            )


class RepositoryDevelopmentSkillTests(unittest.TestCase):
    """Claude owns repository skills; Codex reaches the same directories."""

    def _guard(self) -> Any:
        guard = getattr(validator, "validate_repository_skills", None)
        self.assertIsNotNone(guard, "the repository skill alias guard is missing")
        return guard

    def _write_skill(self, root: Path, name: str) -> Path:
        skill = root / ".claude/skills" / name
        (skill / "agents").mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Use when testing {name}.\n---\n\n# {name}\n",
            encoding="utf-8",
        )
        (skill / "agents/openai.yaml").write_text(
            "interface:\n"
            f'  display_name: "{name}"\n'
            '  short_description: "Repository development workflow skill"\n'
            f'  default_prompt: "Use ${name} for this repository workflow."\n',
            encoding="utf-8",
        )
        return skill

    def _link_skill(self, root: Path, name: str, target: Path | None = None) -> Path:
        aliases = root / ".agents/skills"
        aliases.mkdir(parents=True, exist_ok=True)
        alias = aliases / name
        alias.symlink_to(target or Path("../../.claude/skills") / name, target_is_directory=True)
        return alias

    def _errors(self, root: Path) -> list[str]:
        validation = validator.Validation()
        guard = self._guard()
        if guard is None:
            return []
        with mock.patch.object(validator, "ROOT", root):
            guard(validation)
        return [str(message) for message in validation.errors]

    def test_the_repository_skills_are_valid_codex_aliases_today(self) -> None:
        errors = self._errors(validator.ROOT)
        self.assertEqual([], errors)

    def test_an_empty_canonical_skill_tree_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            (root / ".claude/skills").mkdir(parents=True)

            errors = self._errors(root)

        self.assertTrue(any("no canonical repository skills" in error for error in errors), errors)

    def test_a_missing_codex_alias_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            self._write_skill(root, "fixture")

            errors = self._errors(root)

        self.assertTrue(any("missing Codex alias" in error for error in errors), errors)

    def test_repository_skill_description_length_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            skill = self._write_skill(root, "fixture")
            (skill / "SKILL.md").write_text(
                f"---\nname: fixture\ndescription: {'x' * 301}\n---\n",
                encoding="utf-8",
            )
            self._link_skill(root, "fixture")

            errors = self._errors(root)

        self.assertTrue(any("maximum is 300" in error for error in errors), errors)

    def test_repository_skill_description_rejects_angle_brackets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            skill = self._write_skill(root, "fixture")
            (skill / "SKILL.md").write_text(
                "---\nname: fixture\ndescription: Use when handling <placeholder>.\n---\n",
                encoding="utf-8",
            )
            self._link_skill(root, "fixture")

            errors = self._errors(root)

        self.assertTrue(any("angle-bracket" in error for error in errors), errors)

    def test_a_copy_is_rejected_in_place_of_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            canonical = self._write_skill(root, "fixture")
            alias = root / ".agents/skills/fixture"
            alias.parent.mkdir(parents=True)
            shutil.copytree(canonical, alias)

            errors = self._errors(root)

        self.assertTrue(any("must be a symlink" in error for error in errors), errors)

    def test_a_codex_alias_must_point_to_its_matching_claude_skill(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            self._write_skill(root, "fixture")
            self._write_skill(root, "other")
            self._link_skill(root, "fixture", Path("../../.claude/skills/other"))
            self._link_skill(root, "other")

            errors = self._errors(root)

        self.assertTrue(
            any("must target" in error and "fixture" in error for error in errors), errors
        )

    def test_repository_skills_require_openai_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            skill = self._write_skill(root, "fixture")
            (skill / "agents/openai.yaml").unlink()
            self._link_skill(root, "fixture")

            errors = self._errors(root)

        self.assertTrue(
            any("openai.yaml" in error and "required" in error for error in errors), errors
        )

    def test_repository_skills_validate_openai_metadata_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            skill = self._write_skill(root, "fixture")
            (skill / "agents/openai.yaml").write_text(
                "interface:\n"
                '  display_name: "Fixture"\n'
                '  short_description: "Too short"\n'
                '  default_prompt: "Run this repository workflow."\n',
                encoding="utf-8",
            )
            self._link_skill(root, "fixture")

            errors = self._errors(root)

        self.assertTrue(any("25 to 64 characters" in error for error in errors), errors)
        self.assertTrue(any("must mention $fixture" in error for error in errors), errors)

    def test_an_alias_without_a_canonical_skill_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-repo-skills-") as directory:
            root = Path(directory)
            self._link_skill(root, "orphan")

            errors = self._errors(root)

        self.assertTrue(any("has no canonical Claude skill" in error for error in errors), errors)


class AntigravityHookNestingTests(unittest.TestCase):
    """Antigravity's hooks file wraps its events in a name, and a flat one is dead.

    The guard exists because this shipped. Cargento's root `hooks.json` put event
    names at the top level for the whole life of the Antigravity adapter, and three
    separate things that should have caught it did not: `agy plugin validate`
    reported `hooks: 5 processed` because it counts top-level keys without
    type-checking them, this validator read those keys as event names, and the
    design note wrote the difference down as a discovered fact. agy's runtime
    rejected the file on every session, visibly only in a log nobody reads.
    """

    def _errors(self, document: dict[str, Any], tmp: Path) -> list[str]:
        path = tmp / "cargento/hooks.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        validation = validator.Validation()
        with mock.patch.object(validator, "ROOT", tmp):
            validator.validate_antigravity_hook_nesting(validation)
        return [str(message) for message in validation.errors]

    def test_event_names_at_the_top_level_are_rejected(self) -> None:
        handler = {"type": "command", "command": 'python3 "./skills/cargento/agy_hook.py" x'}
        with tempfile.TemporaryDirectory(prefix="cargento-agy-nesting-") as directory:
            errors = self._errors({"PostInvocation": [handler]}, Path(directory))
        self.assertTrue(
            any("at the top level" in e and "PostInvocation" in e for e in errors), errors
        )

    def test_a_name_wrapped_file_is_accepted(self) -> None:
        handler = {"type": "command", "command": 'python3 "./skills/cargento/agy_hook.py" x'}
        with tempfile.TemporaryDirectory(prefix="cargento-agy-nesting-") as directory:
            errors = self._errors({"cargento": {"PostInvocation": [handler]}}, Path(directory))
        self.assertEqual(errors, [])

    def test_a_file_with_no_named_hook_is_rejected(self) -> None:
        # An empty object parses and would silently load nothing.
        with tempfile.TemporaryDirectory(prefix="cargento-agy-nesting-") as directory:
            errors = self._errors({}, Path(directory))
        self.assertTrue(any("registers no named hook" in e for e in errors), errors)

    def test_the_shipped_file_is_name_wrapped(self) -> None:
        """The regression this class exists for, asserted against the real file."""
        document = json.loads((validator.ROOT / "cargento/hooks.json").read_text())
        self.assertTrue(document, "the shipped Antigravity hooks file is empty")
        for key, value in document.items():
            self.assertIsInstance(
                value, dict, f"top-level {key!r} must be a hook NAME mapping to its events"
            )
