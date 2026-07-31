#!/usr/bin/env python3
"""Prove the board's scores derive from the blind panel evidence beside this file.

Recomputes every access and impact value in ../items.json from the raw JSONL in this
directory, applying the two documented override rules, and reports any disagreement.
Run it whenever a score is questioned, or after editing items.json by hand.

    python3 verify-scores.py
"""

from __future__ import annotations

import contextlib
import json
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BOARD = HERE.parent


def read_jsonl(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(HERE.glob(pattern)):
        for line in path.read_text().splitlines():
            if line.strip():
                with contextlib.suppress(json.JSONDecodeError):
                    rows.append(json.loads(line))
    return rows


def main() -> int:
    board = json.loads((BOARD / "items.json").read_text())
    items = {i["id"]: i for i in board["items"]}

    panel: dict[str, list[dict[str, Any]]] = {}
    for row in read_jsonl("scores-?-?.jsonl") + read_jsonl("g2-scores-?-?.jsonl"):
        panel.setdefault(row["id"], []).append(row)

    kinds = {k["id"]: k for k in read_jsonl("g2-kinds.jsonl")}
    strong = {
        f["id"]: f
        for f in read_jsonl("g2-boundary.jsonl")
        if f.get("strength") == "strong" and f.get("direction") != "correct as placed"
    }
    detector = {d["id"]: d for d in read_jsonl("g2-detector.jsonl")}

    lenses = len({(p.stem.rsplit("-", 2)[-2]) for p in HERE.glob("scores-?-?.jsonl")})
    print(
        f"evidence: {sum(len(v) for v in panel.values())} blind scores over "
        f"{len(panel)} items from {lenses} lenses"
    )

    mismatch = []
    for iid, rows in panel.items():
        it = items.get(iid)
        if not it:
            print(f"  {iid}: scored by the panel but absent from the board")
            continue

        access = statistics.median_low([r["access"] for r in rows])
        impact = statistics.median_low([r["impact"] for r in rows])
        basis = "panel median"

        # Rule 1: an ACTION's access means how hard it is to DO today, not to learn.
        kind = kinds.get(iid)
        if kind and kind["kind"] == "action" and kind.get("currentReadingWrong"):
            access, basis = kind["doAccess"], "action re-read"

        # Rule 2: only a STRONG adversarial finding outranks three independent lenses.
        if iid in strong:
            access = strong[iid]["proposedAccess"]
            impact = strong[iid]["proposedImpact"]
            basis = "boundary audit, strong"

        risk = detector.get(iid, {}).get("riskDiscount", 0)
        expected = {
            "access": access,
            "impact": impact,
            "detectorRisk": risk,
            "riskAdjustedImpact": max(0, impact - risk),
        }
        for field, want in expected.items():
            got = it.get(field)
            if got != want:
                mismatch.append((iid, field, got, want, basis))

    if mismatch:
        print(f"\n{len(mismatch)} field(s) do not match the evidence:")
        for iid, field, got, want, basis in mismatch:
            print(f"  {iid:4} {field:18} board={got!s:5} evidence={want!s:5}  ({basis})")
        return 1

    print(
        f"all {len(panel)} items match the evidence, including the "
        "action re-reads and strong boundary overrides"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
