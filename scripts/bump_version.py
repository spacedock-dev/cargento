#!/usr/bin/env python3
"""Set the plugin version across every owned manifest field.

Usage:
    python3 scripts/bump_version.py 0.2.0
    python3 scripts/bump_version.py --current   # print the current version

The version fields are owned by the Release workflow (tag-driven); this
script is its bump mechanism and refuses anything that is not a strict
semver increase, so a re-run or a stale tag can never move versions
backwards. Fields updated together:

    cargento/.claude-plugin/plugin.json  .version   <- source of truth
    cargento/.codex-plugin/plugin.json   .version
    cargento-gemini/gemini-extension.json  .version   <- Gemini's own root
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# The Claude plugin manifest is the source of truth. It used to be the
# repository's own marketplace metadata, but that marketplace was retired when
# cargento moved into spacedock-dev/marketplace, so the truth moved to the
# manifest the plugin actually ships with.
TRUTH = ROOT / "cargento/.claude-plugin/plugin.json"
MANIFESTS = (
    TRUTH,
    ROOT / "cargento/.codex-plugin/plugin.json",
    # Gemini gets its own extension root: both it and Claude Code claim
    # `<root>/hooks/hooks.json` and neither lets that path move.
    ROOT / "cargento-gemini/gemini-extension.json",
)
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise SystemExit(f"error: {value!r} is not strict semver (X.Y.Z)")
    major, minor, patch = match.groups()
    return (int(major), int(minor), int(patch))


def load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} top level must be an object")
    return data


def save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def current_version() -> str:
    """The single source of truth is the Claude plugin manifest's version;
    every other field must already agree (validate_plugins.py enforces
    parity)."""
    version = load(TRUTH).get("version")
    if not isinstance(version, str):
        raise SystemExit(f"error: {TRUTH.name} version missing")
    versions: set[Any] = {version}
    for path in MANIFESTS:
        versions.add(load(path).get("version"))
    if len(versions) != 1:
        raise SystemExit(f"error: version fields are not in parity: {sorted(map(str, versions))}")
    return version


def bump(target: str) -> None:
    current = current_version()
    if parse_semver(target) <= parse_semver(current):
        raise SystemExit(f"error: target {target} must be strictly greater than current {current}")
    for path in MANIFESTS:
        manifest = load(path)
        manifest["version"] = target
        save(path, manifest)
    print(f"bumped {current} -> {target}")


def main(argv: list[str]) -> int:
    if len(argv) == 1 and argv[0] == "--current":
        print(current_version())
        return 0
    if len(argv) == 1 and not argv[0].startswith("-"):
        bump(argv[0])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
