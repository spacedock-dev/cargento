"""Negative and rendering tests for the repository plugin validator."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
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

    def test_gemini_extensions_use_native_root_manifests(self) -> None:
        for plugin_name in validator.PLUGIN_NAMES:
            with self.subTest(plugin=plugin_name):
                self.assertTrue((validator.ROOT / plugin_name / "gemini-extension.json").is_file())

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

            validator.validate_gemini_extension(plugin_root, validation)

            self.assertTrue(
                any("version must be a non-empty string" in error for error in validation.errors)
            )
            self.assertTrue(any("needs a url or command" in error for error in validation.errors))

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

    def test_hooks_adapter_must_exist_and_mirror_shared_hooks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            plugin_root = Path(directory) / "fixture-plugin"
            plugin_root.mkdir()
            (plugin_root / "hooks.json").write_text('{"hooks":{"SessionStart":[]}}\n')
            validation = validator.Validation()

            validator.validate_hooks_adapter(plugin_root, validation)

            self.assertTrue(
                any(
                    "root hooks adapter exists without hooks/hooks.json" in error
                    for error in validation.errors
                )
            )

            (plugin_root / "hooks.json").unlink()
            (plugin_root / "hooks").mkdir(parents=True)
            (plugin_root / "hooks/hooks.json").write_text('{"hooks":{"SessionStart":[]}}\n')
            validation = validator.Validation()

            validator.validate_hooks_adapter(plugin_root, validation)

            self.assertTrue(any("must exist and mirror" in error for error in validation.errors))

            (plugin_root / "hooks.json").write_text(
                '{"hooks":{"SessionStart":[{"matcher":"x"}]}}\n'
            )
            validation = validator.Validation()

            validator.validate_hooks_adapter(plugin_root, validation)

            self.assertTrue(
                any("must mirror hooks/hooks.json exactly" in error for error in validation.errors)
            )

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
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin/marketplace.json").write_text(
                '{"plugins":[{"name":"cargento","source":"./cargento",'
                '"version":"0.1.0","description":"Desc"}]}\n'
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

    def test_marketplace_rejects_duplicates_and_metadata_version_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-validator-plugin-") as directory:
            root = Path(directory)
            (root / ".agents/plugins").mkdir(parents=True)
            (root / ".agents/plugins/marketplace.json").write_text(
                '{"plugins":[{"name":"cargento",'
                '"source":{"source":"local","path":"./cargento"}}]}\n'
            )
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin/marketplace.json").write_text(
                '{"metadata":{"version":"9.9.9"},'
                '"plugins":['
                '{"name":"cargento","source":"./cargento","version":"0.1.0","description":"Desc"},'
                '{"name":"cargento","source":"./cargento","version":"0.1.0","description":"Desc"}'
                "]}\n"
            )
            (root / "cargento/.claude-plugin").mkdir(parents=True)
            (root / "cargento/.claude-plugin/plugin.json").write_text(
                '{"name":"cargento","version":"0.1.0","description":"Desc"}\n'
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

            self.assertTrue(any("duplicate plugin names" in error for error in validation.errors))
            self.assertTrue(any("duplicate plugin sources" in error for error in validation.errors))
            # metadata.version 9.9.9 vs everything else 0.1.0 must be drift.
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


if __name__ == "__main__":
    unittest.main()
