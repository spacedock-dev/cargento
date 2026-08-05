"""Negative and rendering tests for the repository plugin validator."""

from __future__ import annotations

import json
import shutil
import subprocess
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
            "frontend asset": "skills/cargento/cargento_runtime/web/main.js",
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
            if path.suffix in {".py", ".html", ".css", ".js"}:
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

    def test_an_unwrapped_antigravity_file_is_understood(self) -> None:
        # Antigravity's guide states that each top-level key is a hook name, with
        # no `hooks` wrapper. Requiring the wrapper rejected a file Antigravity's
        # own validator had just accepted, which is how this was found.
        document = {
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
            "PostInvocation": [
                {
                    "type": "command",
                    "command": 'python3 "${PLUGIN_ROOT}/skills/cargento/agy_hook.py"',
                }
            ]
        }
        self.assertEqual([], self._validate(document, ship_script=True))
        self.assertTrue(
            any("agy_hook.py" in e for e in self._validate(document, ship_script=False)),
            "a flat handler's command went unchecked",
        )
