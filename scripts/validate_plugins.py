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

# Gemini CLI gets its own extension root rather than sharing the plugin root.
# Both harnesses load extension hooks from `<root>/hooks/hooks.json` and neither
# lets that path be moved: Claude Code reads it whichever path the manifest
# declares, and Gemini's reference states hooks "are not defined in the
# gemini-extension.json manifest". Sharing one root therefore hands each harness
# the other's vocabulary. Measured, before the split: a Gemini session loading
# Claude's file printed eight `Invalid hook event name` warnings, then ran the two
# names that do overlap and reported both as failed hooks, because Gemini does not
# expand `${CLAUDE_PLUGIN_ROOT}` -- at a synchronous cost of 258 ms and 259 ms per
# session for nothing.
GEMINI_EXTENSION_ROOT = "cargento-gemini"

# The Gemini extension is self-contained because `gemini extensions install`
# copies the directory and a git-URL install clones it, so a command reaching
# outside the extension root would not resolve once installed. That means two
# scripts ship twice, and drift between the copies is the hazard the byte check
# below exists to prevent.
GEMINI_EXTENSION_FILES = (
    "gemini-extension.json",
    "hooks/hooks.json",
    "hooks/event_hook.py",
    "hooks/notify_hook.py",
)

# Which shipped file is a byte-identical copy of which source of truth.
DUPLICATED_SCRIPTS = (
    (f"{GEMINI_EXTENSION_ROOT}/hooks/event_hook.py", "cargento/skills/cargento/event_hook.py"),
    (f"{GEMINI_EXTENSION_ROOT}/hooks/notify_hook.py", "cargento/skills/cargento/notify_hook.py"),
)
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
# Prose documentation outside the plugin tree. validate_skills() covers bundled
# skill Markdown; without this list the repository's own docs get no link check
# at all, which is how two of them kept pointing at a dashboard URL the server
# does not serve. CODE_OF_CONDUCT.md is verbatim upstream text and LICENSE and
# NOTICE are not Markdown, so none of them are listed.
ROOT_DOCS = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "COMPATIBILITY.md",
    "SECURITY.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)
# The server binds IPv4 loopback only, and on some systems `localhost` resolves
# to ::1 first. Every document says 127.0.0.1; the dashboard tests pin this for the
# shipped SKILL.md, and this pins it for the rest.
BANNED_DOC_LITERALS = {
    "http://localhost:4553": "the server is IPv4-only; write http://127.0.0.1:4553",
}


class UniqueKeyLoader(yaml.SafeLoader):  # type: ignore[misc]  # PyYAML ships no stubs, so SafeLoader is Any
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


# Every file the shipped dashboard needs at runtime, relative to the plugin root.
# The launcher imports cargento_runtime.cli, which reaches all of these, so any
# one of them missing from an installed copy is a dashboard that cannot start.
# A packaging step that copies "the skill" without walking subpackages, or an
# archive that drops a frontend asset, both fail here with the exact path.
#
# Kept as an explicit tuple rather than derived from the checkout on purpose: a
# glob would describe whatever happens to be present and could never notice an
# omission.
CARGENTO_RUNTIME_FILES = (
    # Codex loads this through the `hooks` key in its manifest, so an install
    # missing it silently reports no Codex events at all rather than failing.
    "hooks/hooks.json",
    "hooks/codex-hooks.json",
    "hooks.json",
    "skills/cargento/server.py",
    "skills/cargento/notify_hook.py",
    "skills/cargento/event_hook.py",
    "skills/cargento/statusline_hook.py",
    "skills/cargento/agy_hook.py",
    "skills/cargento/cargento_runtime/__init__.py",
    "skills/cargento/cargento_runtime/cli.py",
    "skills/cargento/cargento_runtime/config.py",
    "skills/cargento/cargento_runtime/state.py",
    "skills/cargento/cargento_runtime/stream.py",
    "skills/cargento/cargento_runtime/io.py",
    "skills/cargento/cargento_runtime/probe.py",
    "skills/cargento/cargento_runtime/records.py",
    "skills/cargento/cargento_runtime/transcripts.py",
    "skills/cargento/cargento_runtime/turns.py",
    "skills/cargento/cargento_runtime/sessions.py",
    "skills/cargento/cargento_runtime/snapshot.py",
    "skills/cargento/cargento_runtime/events.py",
    "skills/cargento/cargento_runtime/claude_data.py",
    "skills/cargento/cargento_runtime/notifications.py",
    "skills/cargento/cargento_runtime/spacedock.py",
    "skills/cargento/cargento_runtime/quota.py",
    "skills/cargento/cargento_runtime/aggregate.py",
    "skills/cargento/cargento_runtime/observation.py",
    "skills/cargento/cargento_runtime/diagnostics.py",
    "skills/cargento/cargento_runtime/lifecycle.py",
    "skills/cargento/cargento_runtime/http_api.py",
    "skills/cargento/cargento_runtime/collectors/__init__.py",
    "skills/cargento/cargento_runtime/collectors/claude.py",
    "skills/cargento/cargento_runtime/collectors/codex.py",
    "skills/cargento/cargento_runtime/collectors/pi.py",
    "skills/cargento/cargento_runtime/collectors/gemini.py",
    "skills/cargento/cargento_runtime/collectors/antigravity.py",
    "skills/cargento/cargento_runtime/collectors/copilot.py",
    "skills/cargento/cargento_runtime/collectors/opencode.py",
    "skills/cargento/cargento_runtime/collectors/cursor.py",
    "skills/cargento/cargento_runtime/collectors/goose.py",
    "skills/cargento/cargento_runtime/collectors/droid.py",
    "skills/cargento/cargento_runtime/web/__init__.py",
    "skills/cargento/cargento_runtime/web/index.html",
    "skills/cargento/cargento_runtime/web/styles.css",
    "skills/cargento/cargento_runtime/web/spark.js",
    "skills/cargento/cargento_runtime/web/regular.js",
    "skills/cargento/cargento_runtime/web/mode.js",
    "skills/cargento/cargento_runtime/web/usage.js",
    "skills/cargento/cargento_runtime/web/controls.js",
    "skills/cargento/cargento_runtime/web/calm.js",
    "skills/cargento/cargento_runtime/web/notify.js",
    "skills/cargento/cargento_runtime/web/main.js",
    "skills/cargento/cargento_runtime/web/live.js",
    "skills/cargento/cargento_runtime/web/page.py",
)


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, path: Path | str, message: str) -> None:
        candidate = Path(path)
        try:
            # Resolve both sides: resolve() rewrites 8.3 short names on Windows
            # and /var -> /private/var on macOS, so comparing a resolved path
            # against an unresolved ROOT raises ValueError for paths that are
            # in fact inside it.
            label = candidate.resolve().relative_to(Path(ROOT).resolve()).as_posix()
        except (TypeError, ValueError, OSError):
            # Genuinely outside ROOT, or unresolvable. Still render with forward
            # slashes so error text reads identically on every platform —
            # str(path) would emit backslashes on Windows.
            label = candidate.as_posix()
        self.errors.append(f"{label}: {message}")


def load_json(path: Path, validation: Validation) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
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
        value = yaml.load(text, Loader=UniqueKeyLoader)  # noqa: S506 — SafeLoader subclass
    except yaml.YAMLError as exc:
        validation.error(path, f"invalid {label} YAML ({exc})")
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        validation.error(path, f"{label} must be a mapping with string keys")
        return None
    return value


def parse_frontmatter(path: Path, validation: Validation) -> dict[str, Any] | None:
    lines = path.read_text(encoding="utf-8").splitlines()
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
    yaml_text = path.read_text(encoding="utf-8")
    document = load_yaml_mapping(yaml_text, path, validation, "agents/openai.yaml")
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


def markdown_prose(text: str) -> str:
    """Blank out YAML frontmatter and fenced code, preserving line positions.

    Both fence styles count. Anything inside them is code, not prose: a link
    there must not be resolved and a `#` there is a comment, not a heading.
    Known gap: four-space indented code blocks are still treated as prose.
    """
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                start = index + 1
                break
    out = [""] * min(start, len(lines))
    fence: str | None = None
    for line in lines[start:]:
        marker = re.match(r"\s{0,3}(`{3,}|~{3,})", line)
        if fence is None and marker:
            fence = marker.group(1)[0]
            out.append("")
        elif fence is not None:
            if marker and marker.group(1)[0] == fence:
                fence = None
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


def slugify_heading(text: str) -> str:
    """Anchor a heading's rendered text the way GitHub does.

    GitHub slugs what the heading *renders* to, so inline links collapse to
    their label and markup characters vanish. Word characters survive —
    including underscores and non-ASCII letters, which a naive `[a-z0-9]`
    filter would silently drop.
    """
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"[^\w\- ]", "", text.strip().lower(), flags=re.UNICODE)
    return text.replace(" ", "-")


def heading_slugs(path: Path) -> set[str]:
    """Every anchor a Markdown file exposes: ATX, Setext, and explicit HTML."""
    body = markdown_prose(path.read_text(encoding="utf-8"))
    lines = body.splitlines()
    slugs: set[str] = set()
    seen: dict[str, int] = {}
    for index, line in enumerate(lines):
        atx = re.match(r"\s{0,3}#{1,6}\s+(.*?)\s*#*$", line)
        if atx:
            title = atx.group(1)
        elif (
            line.strip()
            and index + 1 < len(lines)
            and re.fullmatch(r"\s{0,3}(=+|-{2,})\s*", lines[index + 1])
        ):
            title = line.strip()
        else:
            continue
        base = slugify_heading(title)
        # GitHub disambiguates repeated headings with -1, -2, …
        count = seen.get(base, 0)
        seen[base] = count + 1
        slugs.add(base if count == 0 else f"{base}-{count}")
    slugs.update(re.findall(r"<a\s[^>]*(?:name|id)=[\"']([^\"']+)", body))
    return slugs


# Inline link, with the optional CommonMark title consumed rather than
# swallowed into the destination. Known gap: parentheses inside a bare
# destination are not balanced — wrap such a target in <>.
MARKDOWN_LINK_RE = re.compile(
    r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^\s)]*)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)


def validate_markdown_links(path: Path, validation: Validation) -> None:
    prose = markdown_prose(path.read_text(encoding="utf-8"))
    for raw_target in MARKDOWN_LINK_RE.findall(prose):
        stripped = raw_target.strip().strip("<>")
        if stripped.startswith(("http://", "https://", "mailto:")):
            continue
        target, _, fragment = stripped.partition("#")
        if not target:
            # Same-file anchor: resolve it against this file's own headings.
            if fragment and fragment not in heading_slugs(path):
                validation.error(path, f"Markdown anchor does not exist: {raw_target}")
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
            continue
        # A fragment that points at a heading which no longer exists is a
        # dangling link the reader only discovers by clicking it.
        if fragment and resolved.suffix == ".md" and fragment not in heading_slugs(resolved):
            validation.error(path, f"Markdown anchor does not exist: {raw_target}")


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
        elif any(
            not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 128
            for prompt in prompts
        ):
            validation.error(
                path, "default prompts must be non-empty strings of at most 128 characters"
            )

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
    extension_root: Path, expected_name: str, validation: Validation
) -> dict[str, Any] | None:
    """The Gemini extension manifest, which lives in its own root.

    `expected_name` rather than the directory name: the extension installs and is
    listed as `cargento`, the same name as the plugin, while its directory is
    `cargento-gemini` so that its `hooks/hooks.json` cannot collide with Claude's.
    """
    path = extension_root / "gemini-extension.json"
    manifest = load_json(path, validation)
    if manifest is None:
        return None

    for field in ("name", "version", "description"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            validation.error(path, f"{field} must be a non-empty string")
    if manifest.get("name") != expected_name:
        validation.error(path, f"name must be {expected_name!r}, matching the plugin")
    for relative in GEMINI_EXTENSION_FILES:
        if not (extension_root / relative).is_file():
            validation.error(extension_root / relative, "missing from the Gemini extension")
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
        compare(gemini_manifest.get("mcpServers"), "url", plugin_root / "gemini-extension.json")
    if mcp_config is not None:
        compare(mcp_config.get("mcpServers"), "serverUrl", plugin_root / "mcp_config.json")
    else:
        validation.error(
            plugin_root / "mcp_config.json",
            "Antigravity MCP config must exist and mirror .mcp.json",
        )


# Where each harness looks for the hooks this plugin bundles. Verified by running
# each harness against an installed or --plugin-dir copy, not read off a page:
# Claude loads `hooks/hooks.json` by convention, Codex loads whatever path its
# manifest's `hooks` key names, and Antigravity loads a root `hooks.json`.
BUNDLED_HOOKS_FILES = (
    "hooks/hooks.json",
    "hooks/codex-hooks.json",
    "hooks.json",
)

# Which harness reads each bundled hooks file, and every event name that harness
# recognises. Listed explicitly rather than derived from `event_hook.py`, because
# the failure this catches is a *name the harness rejects*, and the adapter's own
# table cannot describe that: a file may legitimately register names the adapter
# does not map, but never a name the harness has never heard of.
#
# The Gemini row is why this exists. Before the root split, Claude's file sat where
# Gemini looks and eight of its ten names were rejected on every Gemini session.
HOOK_FILE_VOCABULARY = {
    "cargento/hooks/hooks.json": (
        "claude",
        frozenset(
            {
                "SessionStart",
                "SessionEnd",
                "UserPromptSubmit",
                "Stop",
                "PermissionRequest",
                "Notification",
                "PreToolUse",
                "PostToolUse",
                "SubagentStart",
                "SubagentStop",
                "TaskCompleted",
                "PreCompact",
                "PostCompact",
            }
        ),
    ),
    "cargento/hooks/codex-hooks.json": (
        "codex",
        frozenset(
            {
                "SessionStart",
                "SessionEnd",
                "UserPromptSubmit",
                "Stop",
                "PreToolUse",
                "PostToolUse",
                "SubagentStart",
                "SubagentStop",
                "PreCompact",
                "PostCompact",
                # Recognised, and measured as such: a hooks file listing it beside
                # the seven mapped names installed cleanly and left all seven
                # firing. This set is what the harness *accepts*, which is a
                # different question from what the adapter maps -- `CODEX_EVENTS`
                # omits it because `codex exec` pins `approval_policy` to `never`
                # so its payload could not be captured.
                "PermissionRequest",
            }
        ),
    ),
    "cargento/hooks.json": (
        "antigravity",
        frozenset({"PreInvocation", "PostInvocation", "PreToolUse", "PostToolUse"}),
    ),
    f"{GEMINI_EXTENSION_ROOT}/hooks/hooks.json": (
        "gemini",
        # The whole documented 0.53.1 vocabulary, measured firing in that order.
        frozenset(
            {
                "SessionStart",
                "SessionEnd",
                "BeforeAgent",
                "AfterAgent",
                "BeforeModel",
                "BeforeToolSelection",
                "AfterModel",
                "BeforeTool",
                "AfterTool",
                "Notification",
                "PreCompress",
            }
        ),
    ),
}


def validate_hook_vocabulary(validation: Validation) -> None:
    """No bundled hooks file registers a name its harness does not know.

    Two failures, both observed rather than imagined:

    1. A foreign event name. The harness skips it with a warning on every session,
       so the hook silently reports nothing while looking installed.
    2. A foreign harness argument. `event_hook.py claude` in Gemini's file would
       post Gemini sessions to `/api/events/claude`, where Claude's normalizer
       truncates the id to eight characters and it matches no row.
    """
    for relative, (harness, vocabulary) in HOOK_FILE_VOCABULARY.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        document = load_json(path, validation)
        if not isinstance(document, dict):
            continue
        for name in _hook_events(document):
            if name not in vocabulary:
                validation.error(
                    path,
                    f"registers {name!r}, which {harness} does not recognise; "
                    f"a foreign event name is skipped with a warning on every session",
                )
        for command in _hook_commands(_hook_events(document)):
            if "event_hook.py" not in command:
                continue
            named = command.rsplit('"', 1)[-1].strip().split(" ")
            if named and named[0] and named[0] != harness:
                validation.error(
                    path,
                    f"hook command passes harness {named[0]!r} in {harness}'s hooks file; "
                    "events would post to the wrong route",
                )


def validate_duplicated_scripts(validation: Validation) -> None:
    """A script that ships twice is byte-identical in both places.

    The Gemini extension cannot reach outside its own root once installed, so it
    carries its own copy of the adapter and of the transport it imports. Copies
    drift silently; a byte comparison is the only check that does not.
    """
    for copy_relative, source_relative in DUPLICATED_SCRIPTS:
        copy_path = ROOT / copy_relative
        source_path = ROOT / source_relative
        if not copy_path.is_file() or not source_path.is_file():
            continue
        if copy_path.read_bytes() != source_path.read_bytes():
            validation.error(
                copy_path,
                f"must be byte-identical to {source_relative}; "
                f"run: cp {source_relative} {copy_relative}",
            )


def validate_hooks_adapter(plugin_root: Path, validation: Validation) -> None:
    """Every bundled hooks file is well formed and points at a script that ships.

    This used to require the root `hooks.json` to mirror `hooks/hooks.json` byte
    for byte, on the assumption that one hooks file could serve both Claude and
    Antigravity. That assumption is now false in two ways, so the rule is gone
    rather than worked around:

    1. The event vocabularies differ. Claude fires `UserPromptSubmit` and
       `SessionEnd`; Antigravity fires `PreInvocation` and `PostInvocation`. A
       file that satisfies one registers mostly-dead entries in the other.
    2. The command names its harness. `event_hook.py claude` posts to
       `/api/events/claude`, so a mirrored file would make Antigravity sessions
       post as Claude, where the id would be truncated by Claude's normalizer and
       match no row.

    What replaces it is a check byte parity never made: that every command
    references a file this plugin actually ships. A hooks file pointing at a
    missing script installs cleanly and reports nothing, which is the same silent
    failure the runtime inventory exists to prevent.
    """
    for relative in BUNDLED_HOOKS_FILES:
        path = plugin_root / relative
        if not path.is_file():
            continue
        document = load_json(path, validation)
        if document is None or not isinstance(document, dict):
            continue
        events = _hook_events(document)
        if not events:
            validation.error(path, "bundled hooks file registers no events")
            continue
        for command in _hook_commands(events):
            for script in _referenced_plugin_paths(command):
                if not (plugin_root / script).is_file():
                    validation.error(path, f"hook command references missing {script}")


def _hook_events(document: dict[str, Any]) -> dict[str, Any]:
    """The event map, whichever of the two shipped schemas this file uses.

    Claude and Codex wrap the events in a `hooks` object. Antigravity does not:
    its guide states that each top-level key *is* a hook name. Requiring the
    wrapper rejected a file Antigravity's own validator had just accepted, which
    is how this difference was found.
    """
    wrapped = document.get("hooks")
    if isinstance(wrapped, dict):
        return wrapped
    return {key: value for key, value in document.items() if isinstance(value, list)}


def _hook_commands(events: Any) -> list[str]:
    """Every command string in a hooks document, in either handler layout.

    Two layouts ship, and Antigravity uses both in one file. Tool-scoped events
    group their handlers under a `matcher`; its loop-scoped events list handlers
    directly. A walker that understood only the grouped form would silently check
    nothing in the flat half.
    """
    found: list[str] = []
    for entries in events.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if isinstance(entry.get("command"), str):
                found.append(entry["command"])  # flat: a handler directly
            found.extend(
                hook["command"]
                for hook in entry.get("hooks") or []
                if isinstance(hook, dict) and isinstance(hook.get("command"), str)
            )
    return found


def _referenced_plugin_paths(command: str) -> list[str]:
    """Plugin-relative paths a command names through a plugin-root variable.

    Both harnesses expand a variable rather than a literal path, which is what
    keeps the command stable across upgrades: Codex records a trust hash over the
    hook definition, so a command carrying a version number would re-prompt every
    time the plugin updated.
    """
    paths: list[str] = []
    for marker in ("${CLAUDE_PLUGIN_ROOT}/", "${PLUGIN_ROOT}/", "${extensionPath}/"):
        start = 0
        while (found := command.find(marker, start)) != -1:
            rest = command[found + len(marker) :]
            # Ends at the closing quote or the next whitespace, whichever is first.
            end = min((i for i in (rest.find('"'), rest.find(" ")) if i != -1), default=len(rest))
            paths.append(rest[:end])
            start = found + len(marker)
    return paths


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
            f"description drift across manifests ({drifted}); "
            "align them with .claude-plugin/plugin.json",
        )


def validate_runtime_files(plugin_root: Path, validation: Validation) -> None:
    """Every runtime file the installed dashboard needs is present and is a file.

    is_file() rather than exists(): a directory where a module belongs is a
    packaging bug that reads as "present" to exists() and then fails at import,
    which is much harder to diagnose from an installed copy than from here.
    """
    for relative in CARGENTO_RUNTIME_FILES:
        target = plugin_root / relative
        if target.is_file():
            continue
        reason = "must be a file, not a directory" if target.is_dir() else "is missing"
        validation.error(target, f"required runtime file {reason}")


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
            validation.error(
                openai_path, "Codex presentation metadata is required by repository policy"
            )
        else:
            fields = parse_openai_metadata(openai_path, validation)
            if fields is None:
                continue
            for field in ("display_name", "short_description", "default_prompt"):
                if not isinstance(fields.get(field), str) or not fields[field].strip():
                    validation.error(
                        openai_path, f"interface.{field} must be a quoted non-empty string"
                    )
            short_description = fields.get("short_description", "")
            if (
                isinstance(short_description, str)
                and short_description
                and not 25 <= len(short_description) <= 64
            ):
                validation.error(
                    openai_path, "interface.short_description must be 25 to 64 characters"
                )
            default_prompt = fields.get("default_prompt", "")
            if isinstance(default_prompt, str) and f"${name}" not in default_prompt:
                validation.error(openai_path, f"interface.default_prompt must mention ${name}")

    # References and operation modules are shipped with the skill just like
    # SKILL.md. Validate every bundled Markdown resource so a top-level skill
    # cannot route an agent into a missing or repository-external file.
    for resource_path in sorted(skills_root.rglob("*.md")):
        validate_markdown_links(resource_path, validation)
        body = resource_path.read_text(encoding="utf-8")
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
                resolve_contract_path(
                    ROOT, source.get("path"), f"{name} source", codex_path, validation
                )
            if names != set(PLUGIN_NAMES):
                validation.error(codex_path, f"plugin names must be {sorted(PLUGIN_NAMES)}")

    # cargento is listed in spacedock-dev/marketplace, not in a marketplace of
    # its own, so there is no repository-level Claude marketplace to check.
    # Version and description parity is asserted directly across the manifests
    # the plugin ships with; cargento/.claude-plugin/plugin.json is the source
    # of truth that bump_version.py writes from.
    for name in PLUGIN_NAMES:
        claude_manifest_path = ROOT / name / ".claude-plugin/plugin.json"
        claude_manifest = load_json(claude_manifest_path, validation)
        if claude_manifest is not None and claude_manifest.get("name") != name:
            validation.error(claude_manifest_path, "name must match the plugin directory")
        codex_manifest = codex_manifests.get(name)
        gemini_manifest = gemini_manifests.get(name)
        versions = {
            claude_manifest.get("version") if claude_manifest else None,
            codex_manifest.get("version") if codex_manifest else None,
            gemini_manifest.get("version") if gemini_manifest else None,
        }
        if len(versions) != 1:
            validation.error(
                claude_manifest_path,
                f"{name} version fields are not in parity: {sorted(map(str, versions))}",
            )
        antigravity_manifest = antigravity_manifests.get(name)
        validate_description_parity(
            name,
            {
                ".claude-plugin/plugin.json": (
                    claude_manifest.get("description") if claude_manifest else None
                ),
                ".codex-plugin/plugin.json": (
                    codex_manifest.get("description") if codex_manifest else None
                ),
                "gemini-extension.json": (
                    gemini_manifest.get("description") if gemini_manifest else None
                ),
                "plugin.json": (
                    antigravity_manifest.get("description") if antigravity_manifest else None
                ),
            },
            validation,
        )


def validate_repo_docs(validation: Validation) -> None:
    """Resolve Markdown inline links and anchors in the repository's prose docs.

    Bundled skill Markdown is covered by validate_skills(); this covers
    everything a documentation-sync pass is allowed to edit outside it. It
    catches inline `[text](target)` links only — a backticked path in a table,
    a reference-style link definition, or a path named in a Python comment is
    not checked here.
    """
    paths = [ROOT / name for name in ROOT_DOCS]
    paths.extend(sorted((ROOT / "docs").rglob("*.md")))
    # Repository development skills. Not shipped, so the portability markers
    # they document are legal there — but their links still have to resolve.
    paths.extend(sorted(ROOT.glob(".claude/skills/*/SKILL.md")))
    for path in paths:
        if not path.is_file():
            validation.error(path, "documented repository file is missing")
            continue
        validate_markdown_links(path, validation)
        body = path.read_text(encoding="utf-8")
        for literal, guidance in BANNED_DOC_LITERALS.items():
            if literal in body:
                validation.error(path, f"contains {literal!r}; {guidance}")


def validate_readme(skill_names: dict[str, set[str]], validation: Validation) -> None:
    path = ROOT / "README.md"
    body = path.read_text(encoding="utf-8")
    for plugin, names in skill_names.items():
        for name in names:
            if f"/{plugin}:{name}" not in body:
                validation.error(path, f"skill inventory is missing /{plugin}:{name}")
    if "codex plugin add cargento@cargento-marketplace" not in body:
        validation.error(path, "Codex installation must install cargento")


def check_installed_runtime(plugin_root: Path) -> int:
    """Report the runtime inventory for one installed plugin copy.

    Exposed as a flag so CI can point it at an installed path without
    embedding a second copy of the inventory in YAML or shell.
    """
    validation = Validation()
    validate_runtime_files(plugin_root, validation)
    for error in validation.errors:
        print(f"::error::{error}")
    if validation.errors:
        return 1
    print(f"Runtime inventory complete: {len(CARGENTO_RUNTIME_FILES)} files under {plugin_root}.")
    return 0


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--runtime-files":
        return check_installed_runtime(Path(sys.argv[2]))
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
        gemini_root = ROOT / GEMINI_EXTENSION_ROOT
        gemini_manifests[plugin_name] = validate_gemini_extension(
            gemini_root, plugin_name, validation
        )
        mcp_config = validate_antigravity_mcp_config(plugin_root, validation)
        validate_mcp_endpoint_parity(
            gemini_root, gemini_manifests[plugin_name], mcp_config, validation
        )
        validate_hooks_adapter(plugin_root, validation)
        validate_hooks_adapter(gemini_root, validation)
        validate_runtime_files(plugin_root, validation)
        skill_names[plugin_name], plugin_catalog_lines = validate_skills(plugin_root, validation)
        catalog_lines.extend(plugin_catalog_lines)
        legacy_commands = list((plugin_root / "commands").glob("*.md"))
        if legacy_commands:
            validation.error(
                plugin_root / "commands", "legacy commands must be migrated to shared skills"
            )

    validate_hook_vocabulary(validation)
    validate_duplicated_scripts(validation)
    validate_marketplaces(manifests, gemini_manifests, antigravity_manifests, validation)
    validate_readme(skill_names, validation)
    validate_repo_docs(validation)

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
        f"{len(PLUGIN_NAMES)} plugins "
        f"({catalog_token_estimate} repository-estimated catalog tokens, "
        f"{len(catalog_text)} rendered bytes)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
