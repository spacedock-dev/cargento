#!/usr/bin/env python3
"""Stamp a released version onto the compass entry of the Spacedock marketplace index.

Usage:
    python3 scripts/update_marketplace.py <marketplace.json> <X.Y.Z>

The listing tracks this repository's `stable` branch, which the Release workflow advances
on every release, so a fresh install resolves the new release without this script. The
`version` field is what the marketplace displays and what an installed copy compares
against to notice an update, so it is stamped to match. Nothing else in the entry is
rewritten.

Two refusals keep a wrong stamp from landing:

- An entry that does not point at `stable` under `compass/` is not the entry this release
  publishes to, so it fails instead of showing a version that nothing serves.
- A version below the one already listed is left alone. A resumed older release must not
  roll the listing back, the same rule `advance-stable` keeps for the branch.

Writes the index only when the version changes, and prints which of the three outcomes
it reached.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ENTRY = "compass"
SOURCE_PATH = "compass"
SOURCE_REF = "stable"
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


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
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise SystemExit(f"error: {path} has no plugins list")
    return data


def find_entry(index: dict[str, Any]) -> dict[str, Any]:
    entries = [
        plugin
        for plugin in index["plugins"]
        if isinstance(plugin, dict) and plugin.get("name") == ENTRY
    ]
    if len(entries) != 1:
        raise SystemExit(f"error: expected one {ENTRY} marketplace entry, found {len(entries)}")
    entry: dict[str, Any] = entries[0]
    source = entry.get("source")
    if (
        not isinstance(source, dict)
        or source.get("path") != SOURCE_PATH
        or source.get("ref") != SOURCE_REF
    ):
        raise SystemExit(
            f"error: the {ENTRY} entry must point at ref {SOURCE_REF!r}, path {SOURCE_PATH!r}"
        )
    return entry


def stamp(index_path: Path, version: str) -> str:
    target = parse_semver(version)
    index = load(index_path)
    entry = find_entry(index)
    listed = entry.get("version")
    if isinstance(listed, str) and SEMVER_RE.fullmatch(listed):
        if parse_semver(listed) == target:
            return f"marketplace already lists {ENTRY} {version}"
        if parse_semver(listed) > target:
            return f"marketplace lists {ENTRY} {listed}, newer than {version}; leaving it"
    entry["version"] = version
    text = json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=index_path.parent, prefix=f"{index_path.name}.", delete=False
    ) as handle:
        handle.write(text)
        staged = Path(handle.name)
    staged.replace(index_path)
    return f"marketplace now lists {ENTRY} {version}"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    print(stamp(Path(argv[0]), argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
