#!/usr/bin/env python3
"""Validate the shared Codex, Claude Code, Antigravity, and Gemini contracts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAMES = ("cargento",)
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PORTABILITY_MARKERS = {
    "${CLAUDE_PLUGIN_ROOT}": "resolve shared skill resources relative to the skill instead",
    ".claude/skills/": "reference the bundled skill path instead of a user cache",
    "mcp__claude_ai_": "describe the MCP capability instead of a host-specific tool name",
    "ToolSearch(": "describe tool discovery semantically",
    "Skill(skill=": "describe skill invocation semantically",
    "subagent_type": "describe the required worker capability instead of a Claude API field",
}
SHARED_FRONTMATTER_FIELDS = {"name", "description", "license"}
MAX_CATALOG_TOKEN_ESTIMATE = 4_000


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping
)


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, path: Path | str, message: str) -> None:
        try:
            label = Path(path).resolve().relative_to(ROOT).as_posix()
        except (TypeError, ValueError):
            label = str(path)
        self.errors.append(f"{label}: {message}")


def load_json(path: Path, validation: Validation) -> dict[str, Any] | None:
    try:
        text = path.read_text()
    except OSError as exc:
        validation.error(path, f"cannot read file ({exc})")
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        validation.error(path, f"invalid JSON ({exc})")
        return None
    if not isinstance(value, dict):
        validation.error(path, "top level must be an object")
        return None
    return value


def load_yaml_mapping(
    text: str, path: Path, validation: Validation, label: str
) -> dict[str, Any] | None:
    try:
        value = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        validation.error(path, f"invalid {label} YAML ({exc})")
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        validation.error(path, f"{label} must be a mapping with string keys")
        return None
    return value


def parse_frontmatter(path: Path, validation: Validation) -> dict[str, Any] | None:
    lines = path.read_text().splitlines()
    if not lines or lines[0] != "---":
        validation.error(path, "SKILL.md must begin with YAML frontmatter")
        return None
    try:
        end = lines.index("---", 1)
    except ValueError:
        validation.error(path, "frontmatter is missing its closing delimiter")
        return None

    metadata = load_yaml_mapping("\n".join(lines[1:end]), path, validation, "frontmatter")
    if metadata is None:
        return None
    unknown = set(metadata) - SHARED_FRONTMATTER_FIELDS
    if unknown:
        validation.error(path, f"unsupported shared frontmatter fields: {sorted(unknown)}")
    if "license" in metadata and not isinstance(metadata["license"], str):
        validation.error(path, "frontmatter license must be a string")
    return metadata


def parse_openai_metadata(path: Path, validation: Validation) -> dict[str, Any] | None:
    document = load_yaml_mapping(path.read_text(), path, validation, "agents/openai.yaml")
    if document is None:
        return None
    unknown_top_level = set(document) - {"interface", "dependencies", "policy"}
    if unknown_top_level:
        validation.error(path, f"unsupported openai.yaml fields: {sorted(unknown_top_level)}")
    interface = document.get("interface")
    if not isinstance(interface, dict) or not all(isinstance(key, str) for key in interface):
        validation.error(path, "interface must be a mapping with string keys")
        return None
    allowed_interface = {
        "display_name",
        "short_description",
        "icon_small",
        "icon_large",
        "brand_color",
        "default_prompt",
    }
    unknown_interface = set(interface) - allowed_interface
    if unknown_interface:
        validation.error(path, f"unsupported interface fields: {sorted(unknown_interface)}")
    for field in allowed_interface:
        if field in interface and (
            not isinstance(interface[field], str) or not interface[field].strip()
        ):
            validation.error(path, f"interface.{field} must be a non-empty string")
    brand_color = interface.get("brand_color")
    if isinstance(brand_color, str) and not re.fullmatch(r"#[0-9A-Fa-f]{6}", brand_color):
        validation.error(path, "interface.brand_color must be a six-digit hex color")

    dependencies = document.get("dependencies")
    if dependencies is not None:
        if not isinstance(dependencies, dict):
            validation.error(path, "dependencies must be a mapping")
        else:
            unknown_dependencies = set(dependencies) - {"tools"}
            if unknown_dependencies:
                validation.error(
                    path,
                    f"unsupported dependencies fields: {sorted(unknown_dependencies)}",
                )
            tools = dependencies.get("tools")
            if not isinstance(tools, list):
                validation.error(path, "dependencies.tools must be a list")
            else:
                allowed_tool_fields = {"type", "value", "description", "transport", "url"}
                for index, tool in enumerate(tools):
                    if not isinstance(tool, dict):
                        validation.error(path, f"dependencies.tools[{index}] must be a mapping")
                        continue
                    unknown_tool_fields = set(tool) - allowed_tool_fields
                    if unknown_tool_fields:
                        validation.error(
                            path,
                            f"dependencies.tools[{index}] has unsupported fields: "
                            f"{sorted(unknown_tool_fields)}",
                        )
                    if tool.get("type") != "mcp":
                        validation.error(path, f"dependencies.tools[{index}].type must be 'mcp'")
                    for field in ("value", "description"):
                        if not isinstance(tool.get(field), str) or not tool[field].strip():
                            validation.error(
                                path,
                                f"dependencies.tools[{index}].{field} must be a non-empty string",
                            )
                    for field in ("transport", "url"):
                        if field in tool and (
                            not isinstance(tool[field], str) or not tool[field].strip()
                        ):
                            validation.error(
                                path,
                                f"dependencies.tools[{index}].{field} must be a non-empty string",
                            )

    policy = document.get("policy")
    if policy is not None:
        if not isinstance(policy, dict):
            validation.error(path, "policy must be a mapping")
        else:
            unknown_policy = set(policy) - {"allow_implicit_invocation"}
            if unknown_policy:
                validation.error(path, f"unsupported policy fields: {sorted(unknown_policy)}")
            if "allow_implicit_invocation" in policy and not isinstance(
                policy["allow_implicit_invocation"], bool
            ):
                validation.error(path, "policy.allow_implicit_invocation must be a boolean")
    return interface


def render_catalog_estimate_line(plugin: str, name: str, description: str, path: Path) -> str:
    """Build the repository's conservative, client-independent catalog estimate."""
    rendered_path = path.relative_to(ROOT).as_posix()
    return f"- {plugin}:{name}: {description} (file: {rendered_path})"


def approx_token_count(text: str) -> int:
    """Apply the repository's conservative four-bytes-per-token policy."""
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


def validate_markdown_links(path: Path, validation: Validation) -> None:
    prose = re.sub(r"```.*?```", "", path.read_text(), flags=re.DOTALL)
    for raw_target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", prose):
        target = raw_target.strip().strip("<>").split("#", 1)[0]
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        # Bare prose placeholders such as `(url)` are not filesystem links.
        if "/" not in target and not Path(target).suffix:
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            validation.error(path, f"Markdown link escapes the repository: {raw_target}")
            continue
        if not resolved.exists():
            validation.error(path, f"Markdown link target does not exist: {raw_target}")


def resolve_contract_path(
    plugin_root: Path, raw_path: object, field: str, manifest_path: Path, validation: Validation
) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.startswith("./"):
        validation.error(manifest_path, f"{field} must be an ./-prefixed relative path")
        return None
    resolved = (plugin_root / raw_path).resolve()
    try:
        resolved.relative_to(plugin_root.resolve())
    except ValueError:
        validation.error(manifest_path, f"{field} must stay inside the plugin root")
        return None
    if not resolved.exists():
        validation.error(manifest_path, f"{field} path does not exist: {raw_path}")
    return resolved


def validate_mcp_entries(entries: object, path: Path, validation: Validation) -> None:
    if not isinstance(entries, dict) or not entries:
        validation.error(path, "MCP server map must be a non-empty object")
        return
    for name, config in entries.items():
        if not isinstance(name, str) or not name:
            validation.error(path, "MCP server names must be non-empty strings")
        if not isinstance(config, dict):
            validation.error(path, f"MCP server {name!r} must be an object")
            continue
        if not any(key in config for key in ("url", "command")):
            validation.error(path, f"MCP server {name!r} needs a url or command")


def validate_codex_manifest(plugin_root: Path, validation: Validation) -> dict[str, Any] | None:
    path = plugin_root / ".codex-plugin/plugin.json"
    manifest = load_json(path, validation)
    if manifest is None:
        return None

    for field in ("name", "version", "description"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            validation.error(path, f"{field} must be a non-empty string")
    if manifest.get("name") != plugin_root.name:
        validation.error(path, "name must match the plugin directory")
    resolve_contract_path(plugin_root, manifest.get("skills"), "skills", path, validation)

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        validation.error(path, "interface metadata is required by repository policy")
    else:
        for field in ("displayName", "shortDescription", "longDescription", "developerName"):
            if not isinstance(interface.get(field), str) or not interface[field].strip():
                validation.error(path, f"interface.{field} must be a non-empty string")
        capabilities = interface.get("capabilities")
        if not isinstance(capabilities, list) or "Read" not in capabilities:
            validation.error(path, "interface.capabilities must include Read")
        prompts = interface.get("defaultPrompt")
        if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
            validation.error(path, "interface.defaultPrompt must contain one to three prompts")
        elif any(not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 128 for prompt in prompts):
            validation.error(path, "default prompts must be non-empty strings of at most 128 characters")

    mcp_servers = manifest.get("mcpServers")
    if isinstance(mcp_servers, dict):
        validate_mcp_entries(mcp_servers, path, validation)
    elif isinstance(mcp_servers, str):
        mcp_path = resolve_contract_path(plugin_root, mcp_servers, "mcpServers", path, validation)
        if mcp_path and mcp_path.is_file():
            config = load_json(mcp_path, validation)
            if config is not None:
                entries = config.get("mcp_servers", config.get("mcpServers", config))
                validate_mcp_entries(entries, mcp_path, validation)
    elif mcp_servers is not None:
        validation.error(path, "mcpServers must be a path or server map")
    return manifest


def validate_antigravity_manifest(
    plugin_root: Path, validation: Validation
) -> dict[str, Any] | None:
    path = plugin_root / "plugin.json"
    manifest = load_json(path, validation)
    if manifest is None:
        return None

    allowed_fields = {"$schema", "name", "description"}
    unknown_fields = set(manifest) - allowed_fields
    if unknown_fields:
        validation.error(path, f"unsupported Antigravity manifest fields: {sorted(unknown_fields)}")
    for field in ("name", "description"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            validation.error(path, f"{field} must be a non-empty string")
    if manifest.get("name") != plugin_root.name:
        validation.error(path, "name must match the plugin directory")
    return manifest


def validate_gemini_extension(
    plugin_root: Path, validation: Validation
) -> dict[str, Any] | None:
    path = plugin_root / "gemini-extension.json"
    manifest = load_json(path, validation)
    if manifest is None:
        return None

    for field in ("name", "version", "description"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            validation.error(path, f"{field} must be a non-empty string")
    if manifest.get("name") != plugin_root.name:
        validation.error(path, "name must match the plugin directory")
    if "mcpServers" in manifest:
        validate_mcp_entries(manifest["mcpServers"], path, validation)
    return manifest


def validate_antigravity_mcp_config(
    plugin_root: Path, validation: Validation
) -> dict[str, Any] | None:
    path = plugin_root / "mcp_config.json"
    if not path.is_file():
        return None
    config = load_json(path, validation)
    if config is None:
        return None
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        validation.error(path, "mcpServers must be a non-empty object")
        return config
    for name, entry in servers.items():
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("serverUrl"), str)
            or not entry["serverUrl"].strip()
        ):
            validation.error(path, f"MCP server {name!r} must define a non-empty serverUrl")
    return config


def validate_mcp_endpoint_parity(
    plugin_root: Path,
    gemini_manifest: dict[str, Any] | None,
    mcp_config: dict[str, Any] | None,
    validation: Validation,
) -> None:
    """Every runtime-specific copy of the MCP endpoint must mirror .mcp.json."""
    base_path = plugin_root / ".mcp.json"
    if not base_path.is_file():
        if gemini_manifest is not None and "mcpServers" in gemini_manifest:
            validation.error(
                plugin_root / "gemini-extension.json",
                "declares MCP servers but the plugin has no .mcp.json to mirror",
            )
        if mcp_config is not None:
            validation.error(
                plugin_root / "mcp_config.json",
                "exists but the plugin has no .mcp.json to mirror",
            )
        return
    base = load_json(base_path, validation)
    if base is None or not isinstance(base.get("mcpServers"), dict):
        return
    base_urls = {
        name: entry.get("url")
        for name, entry in base["mcpServers"].items()
        if isinstance(entry, dict)
    }

    def compare(servers: object, url_key: str, path: Path) -> None:
        found: dict[str, Any] = {}
        if isinstance(servers, dict):
            found = {
                name: entry.get(url_key)
                for name, entry in servers.items()
                if isinstance(entry, dict)
            }
        if found != base_urls:
            validation.error(
                path,
                f"MCP endpoints must mirror .mcp.json ({base_urls}); found {found}",
            )

    if gemini_manifest is not None:
        compare(
            gemini_manifest.get("mcpServers"), "url", plugin_root / "gemini-extension.json"
        )
    if mcp_config is not None:
        compare(mcp_config.get("mcpServers"), "serverUrl", plugin_root / "mcp_config.json")
    else:
        validation.error(
            plugin_root / "mcp_config.json",
            "Antigravity MCP config must exist and mirror .mcp.json",
        )


def validate_hooks_adapter(plugin_root: Path, validation: Validation) -> None:
    """Antigravity loads hooks from a root hooks.json; keep it in parity with hooks/hooks.json."""
    shared_path = plugin_root / "hooks/hooks.json"
    adapter_path = plugin_root / "hooks.json"
    if not shared_path.is_file():
        if adapter_path.is_file():
            validation.error(adapter_path, "root hooks adapter exists without hooks/hooks.json")
        return
    if not adapter_path.is_file():
        validation.error(
            adapter_path,
            "Antigravity hook adapter must exist and mirror hooks/hooks.json",
        )
        return
    shared = load_json(shared_path, validation)
    adapter = load_json(adapter_path, validation)
    if shared is not None and adapter is not None and shared != adapter:
        validation.error(adapter_path, "root hooks adapter must mirror hooks/hooks.json exactly")


def validate_description_parity(
    plugin_name: str,
    descriptions: dict[str, str | None],
    validation: Validation,
) -> None:
    """Every manifest that carries a description must carry the same one."""
    present = {label: value for label, value in descriptions.items() if value is not None}
    if len(set(present.values())) > 1:
        drifted = ", ".join(sorted(present))
        validation.error(
            ROOT / plugin_name,
            f"description drift across manifests ({drifted}); align them with .claude-plugin/plugin.json",
        )


def validate_skills(plugin_root: Path, validation: Validation) -> tuple[set[str], list[str]]:
    skills_root = plugin_root / "skills"
    names: set[str] = set()
    catalog_lines: list[str] = []
    for path in sorted(skills_root.glob("*/SKILL.md")):
        metadata = parse_frontmatter(path, validation)
        if metadata is None:
            continue
        raw_name = metadata.get("name", "")
        name = raw_name if isinstance(raw_name, str) else path.parent.name
        description = metadata.get("description", "")
        if not isinstance(raw_name, str) or not NAME_RE.fullmatch(raw_name):
            validation.error(path, "name must use lowercase kebab-case")
        if isinstance(raw_name, str) and raw_name != path.parent.name:
            validation.error(path, "frontmatter name must match its directory")
        if name in names:
            validation.error(path, f"duplicate skill name {name!r}")
        names.add(name)
        if not isinstance(description, str) or not description:
            validation.error(path, "description is required")
            description = ""
        if len(description) > 300:
            validation.error(path, f"description is {len(description)} characters; maximum is 300")
        if "<" in description or ">" in description:
            validation.error(path, "description must not contain angle-bracket placeholders")
        catalog_lines.append(
            render_catalog_estimate_line(plugin_root.name, name, description, path)
        )
        openai_path = path.parent / "agents/openai.yaml"
        if not openai_path.is_file():
            validation.error(openai_path, "Codex presentation metadata is required by repository policy")
        else:
            fields = parse_openai_metadata(openai_path, validation)
            if fields is None:
                continue
            for field in ("display_name", "short_description", "default_prompt"):
                if not isinstance(fields.get(field), str) or not fields[field].strip():
                    validation.error(openai_path, f"interface.{field} must be a quoted non-empty string")
            short_description = fields.get("short_description", "")
            if isinstance(short_description, str) and short_description and not 25 <= len(short_description) <= 64:
                validation.error(openai_path, "interface.short_description must be 25 to 64 characters")
            default_prompt = fields.get("default_prompt", "")
            if isinstance(default_prompt, str) and f"${name}" not in default_prompt:
                validation.error(openai_path, f"interface.default_prompt must mention ${name}")

    # References and operation modules are shipped with the skill just like
    # SKILL.md. Validate every bundled Markdown resource so a top-level skill
    # cannot route an agent into a missing or repository-external file.
    for resource_path in sorted(skills_root.rglob("*.md")):
        validate_markdown_links(resource_path, validation)
        body = resource_path.read_text()
        for marker, guidance in PORTABILITY_MARKERS.items():
            if marker in body:
                validation.error(resource_path, f"shared skill contains {marker!r}; {guidance}")

    if not names:
        validation.error(skills_root, "no skills discovered")
    return names, catalog_lines


def validate_marketplaces(
    codex_manifests: dict[str, dict[str, Any] | None],
    gemini_manifests: dict[str, dict[str, Any] | None],
    antigravity_manifests: dict[str, dict[str, Any] | None],
    validation: Validation,
) -> None:
    codex_path = ROOT / ".agents/plugins/marketplace.json"
    codex_marketplace = load_json(codex_path, validation)
    if codex_marketplace is not None:
        entries = codex_marketplace.get("plugins")
        if not isinstance(entries, list):
            validation.error(codex_path, "plugins must be an array")
        else:
            names: set[str] = set()
            for entry in entries:
                if not isinstance(entry, dict):
                    validation.error(codex_path, "each plugin entry must be an object")
                    continue
                name = entry.get("name")
                names.add(name) if isinstance(name, str) else None
                source = entry.get("source")
                if not isinstance(source, dict) or source.get("source") != "local":
                    validation.error(codex_path, f"{name}: expected a local source object")
                    continue
                resolve_contract_path(ROOT, source.get("path"), f"{name} source", codex_path, validation)
            if names != set(PLUGIN_NAMES):
                validation.error(codex_path, f"plugin names must be {sorted(PLUGIN_NAMES)}")

    claude_path = ROOT / ".claude-plugin/marketplace.json"
    claude_marketplace = load_json(claude_path, validation)
    if claude_marketplace is None:
        return
    entries = claude_marketplace.get("plugins")
    if not isinstance(entries, list):
        validation.error(claude_path, "plugins must be an array")
        return
    names = [entry.get("name") for entry in entries if isinstance(entry, dict)]
    sources = [entry.get("source") for entry in entries if isinstance(entry, dict)]
    if len(names) != len(set(names)):
        validation.error(claude_path, "duplicate plugin names in marketplace")
    if len(sources) != len(set(sources)):
        validation.error(claude_path, "duplicate plugin sources in marketplace")
    metadata_version = (claude_marketplace.get("metadata") or {}).get("version")
    by_name = {entry.get("name"): entry for entry in entries if isinstance(entry, dict)}
    for name in PLUGIN_NAMES:
        entry = by_name.get(name)
        if entry is None:
            validation.error(claude_path, f"missing plugin entry {name}")
            continue
        resolve_contract_path(ROOT, entry.get("source"), f"{name} source", claude_path, validation)
        codex_manifest = codex_manifests.get(name)
        claude_manifest = load_json(ROOT / name / ".claude-plugin/plugin.json", validation)
        if claude_manifest is not None and claude_manifest.get("name") != name:
            validation.error(
                ROOT / name / ".claude-plugin/plugin.json",
                "name must match the plugin directory",
            )
        gemini_manifest = gemini_manifests.get(name)
        versions = {
            metadata_version,
            entry.get("version"),
            claude_manifest.get("version") if claude_manifest else None,
            codex_manifest.get("version") if codex_manifest else None,
            gemini_manifest.get("version") if gemini_manifest else None,
        }
        if len(versions) != 1:
            validation.error(claude_path, f"{name} version fields are not in parity: {sorted(map(str, versions))}")
        antigravity_manifest = antigravity_manifests.get(name)
        validate_description_parity(
            name,
            {
                "marketplace entry": entry.get("description"),
                ".claude-plugin/plugin.json": claude_manifest.get("description") if claude_manifest else None,
                ".codex-plugin/plugin.json": codex_manifest.get("description") if codex_manifest else None,
                "gemini-extension.json": gemini_manifest.get("description") if gemini_manifest else None,
                "plugin.json": antigravity_manifest.get("description") if antigravity_manifest else None,
            },
            validation,
        )


def validate_readme(skill_names: dict[str, set[str]], validation: Validation) -> None:
    path = ROOT / "README.md"
    body = path.read_text()
    for plugin, names in skill_names.items():
        for name in names:
            if f"/{plugin}:{name}" not in body:
                validation.error(path, f"skill inventory is missing /{plugin}:{name}")
    if "codex plugin add cargento@cargento-marketplace" not in body:
        validation.error(path, "Codex installation must install cargento")


def main() -> int:
    validation = Validation()
    manifests: dict[str, dict[str, Any] | None] = {}
    gemini_manifests: dict[str, dict[str, Any] | None] = {}
    antigravity_manifests: dict[str, dict[str, Any] | None] = {}
    skill_names: dict[str, set[str]] = {}
    catalog_lines: list[str] = []
    for plugin_name in PLUGIN_NAMES:
        plugin_root = ROOT / plugin_name
        manifests[plugin_name] = validate_codex_manifest(plugin_root, validation)
        antigravity_manifests[plugin_name] = validate_antigravity_manifest(plugin_root, validation)
        gemini_manifests[plugin_name] = validate_gemini_extension(plugin_root, validation)
        mcp_config = validate_antigravity_mcp_config(plugin_root, validation)
        validate_mcp_endpoint_parity(
            plugin_root, gemini_manifests[plugin_name], mcp_config, validation
        )
        validate_hooks_adapter(plugin_root, validation)
        skill_names[plugin_name], plugin_catalog_lines = validate_skills(plugin_root, validation)
        catalog_lines.extend(plugin_catalog_lines)
        legacy_commands = list((plugin_root / "commands").glob("*.md"))
        if legacy_commands:
            validation.error(plugin_root / "commands", "legacy commands must be migrated to shared skills")

    validate_marketplaces(manifests, gemini_manifests, antigravity_manifests, validation)
    validate_readme(skill_names, validation)

    catalog_text = "\n".join(catalog_lines) + "\n"
    catalog_token_estimate = approx_token_count(catalog_text)
    if catalog_token_estimate > MAX_CATALOG_TOKEN_ESTIMATE:
        validation.error(
            "skills",
            f"combined repository catalog estimate is {catalog_token_estimate} tokens; "
            f"repository maximum is {MAX_CATALOG_TOKEN_ESTIMATE}",
        )

    if validation.errors:
        print("Plugin compatibility validation failed:")
        for error in validation.errors:
            print(f"- {error}")
        return 1
    print(
        f"Validated {sum(map(len, skill_names.values()))} skills across "
        f"{len(PLUGIN_NAMES)} plugins ({catalog_token_estimate} repository-estimated catalog tokens, "
        f"{len(catalog_text)} rendered bytes)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
