#!/usr/bin/env python3
"""Check the migration inventory against the legacy contracts it must preserve."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEB = Path("cargento/skills/cargento/cargento_runtime/web")
OWNERS = frozenset(f"DRC-{number}" for number in range(4822, 4828))
DISPOSITIONS = frozenset(
    {"stable-identity", "store-held", "retained-deferral", "obsolete-with-proof", "not-managed"}
)


def check_inventory(root: Path, data: dict[str, Any]) -> list[str]:
    """Return actionable gaps; do not import the dashboard or read its stores."""
    if not isinstance(data, dict) or data.get("schema") != 1:
        msg = "inventory must use schema 1"
        raise ValueError(msg)
    gaps: list[str] = []
    groups = {
        name: _rows(data, name, root, gaps)
        for name in ("parts", "reader_state", "storage", "surfaces", "routes")
    }
    expected_parts = _parts(root / WEB / "page.py")
    _coverage("parts", expected_parts, groups["parts"], gaps)
    document = (root / "docs/design-reader-state.md").read_text(encoding="utf-8")
    table = document.split("## The inventory", 1)[1].split("\n## ", 1)[0]
    state_names = {
        line.split("|")[1].strip()
        for line in table.splitlines()
        if line.startswith("| ") and not line.startswith("| Reader state |")
    }
    _coverage("reader_state", state_names, groups["reader_state"], gaps)
    gaps.extend(
        f"reader_state {row['name']}: missing disposition"
        for row in groups["reader_state"]
        if row.get("disposition") not in DISPOSITIONS
    )
    literals = re.compile(r"""["'`](cargento\.[^"'`\s$]+)""")
    source_files = [root / WEB / name for name in expected_parts]
    index = root / WEB / "index.html"
    if index.exists():
        source_files.append(index)
    storage_names = {
        key
        for source in source_files
        for key in literals.findall(source.read_text(encoding="utf-8"))
    }
    _coverage("storage", storage_names, groups["storage"], gaps)
    gaps.extend(
        f"storage {row['name']}: missing format contract"
        for row in groups["storage"]
        if not isinstance(row.get("format"), str) or not row["format"].strip()
    )
    return gaps


def _parts(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        value = None
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "APP_PARTS"
        ) or (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "APP_PARTS" for target in node.targets
            )
        ):
            value = node.value
        if value is not None:
            parts = ast.literal_eval(value)
            if not isinstance(parts, tuple) or not all(isinstance(part, str) for part in parts):
                break
            return set(parts)
    msg = "page.py must declare the APP_PARTS tuple"
    raise ValueError(msg)


def _rows(data: dict[str, Any], group: str, root: Path, gaps: list[str]) -> list[dict[str, Any]]:
    rows = data.get(group)
    if not isinstance(rows, list) or not rows:
        gaps.append(f"{group}: inventory is empty")
        return []
    valid = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]:
            gaps.append(f"{group}: row needs a name")
            continue
        name = row["name"]
        if name in seen:
            gaps.append(f"{group}: duplicate {name}")
        seen.add(name)
        if (
            row.get("owner") not in OWNERS
            or not isinstance(row.get("contract"), str)
            or not row["contract"].strip()
        ):
            gaps.append(f"{group} {name}: missing migration owner or behavior contract")
        oracles = row.get("oracles")
        if not isinstance(oracles, list) or not oracles:
            gaps.append(f"{group} {name}: missing oracle")
        else:
            for oracle in oracles:
                if not isinstance(oracle, str):
                    gaps.append(f"{group} {name}: invalid oracle")
                    continue
                path = (root / oracle).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    gaps.append(f"{group} {name}: missing or outside oracle {oracle}")
        valid.append(row)
    return valid


def _coverage(group: str, expected: set[str], rows: list[dict[str, Any]], gaps: list[str]) -> None:
    actual = {row["name"] for row in rows}
    gaps.extend(f"{group}: unowned {name}" for name in sorted(expected - actual))
    gaps.extend(f"{group}: obsolete row {name}" for name in sorted(actual - expected))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args()
    try:
        path = args.inventory or args.root / "scripts/frontend-migration.json"
        gaps = check_inventory(args.root.resolve(), json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, SyntaxError, TypeError) as error:
        print(f"Cannot check frontend inventory: {error}", file=sys.stderr)
        return 1
    for gap in gaps:
        print(gap, file=sys.stderr)
    if not gaps:
        print("Frontend migration inventory is complete.")
    return int(bool(gaps))


if __name__ == "__main__":
    raise SystemExit(main())
