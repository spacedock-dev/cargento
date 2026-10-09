#!/usr/bin/env python3
"""Check the migration inventory: every row is owned, has a contract and names oracles that exist.

The inventory maps what the previous interface did (its script parts, surfaces, routes, reader
state and persisted keys) to the React owner that took it over and the proofs that hold it. The
interface is gone, so its source is no longer a thing to derive coverage from: the reader-state rows
must match the design record's table, and the storage rows must match the keys the React codec owns.
Every file the reader-state record cites as an owner, and every symbol it names in that file, must
exist, so an owner that is renamed or deleted fails here rather than rotting in the prose.
The `parts` rows are the historical map and are checked for form only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STORAGE_KEYS = Path("frontend/src/storage/keys.ts")
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
    gaps.extend(owner_gaps(root, document))
    literals = re.compile(r"""["'`](cargento\.[^"'`\s$]+)""")
    storage_names = set(literals.findall((root / STORAGE_KEYS).read_text(encoding="utf-8")))
    _coverage("storage", storage_names, groups["storage"], gaps)
    gaps.extend(
        f"storage {row['name']}: missing format contract"
        for row in groups["storage"]
        if not isinstance(row.get("format"), str) or not row["format"].strip()
    )
    return gaps


# `path`: `Symbol`, `other` is the form every cited owner takes. A path alone is cited for the file;
# the symbols after the colon are identifiers the file must still declare or use. A symbol that is
# not a plain identifier (a CSS class, a storage key) is not checked, because a word search says
# nothing of it.
OWNER = re.compile(r"`(frontend/[^`\s]+)`(?::\s*((?:`[^`]+`(?:,\s*)?)+))?")
IDENTIFIER = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$")


def owner_gaps(root: Path, document: str) -> list[str]:
    """Each cited owner file that is missing, and each cited symbol its file no longer names."""
    gaps = []
    for match in OWNER.finditer(document):
        path, listed = match.group(1), match.group(2)
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            gaps.append(f"owner {path}: the file the reader-state record cites does not exist")
            continue
        if not listed:
            continue
        text = target.read_text(encoding="utf-8")
        for raw in re.findall(r"`([^`]+)`", listed):
            symbol = raw.strip()
            if not IDENTIFIER.fullmatch(symbol):
                continue
            if not all(
                re.search(rf"(?<![\w$]){re.escape(part)}(?![\w$])", text)
                for part in symbol.split(".")
            ):
                gaps.append(
                    f"owner {path}: {symbol} is not in the file the reader-state record cites"
                )
    return gaps


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
