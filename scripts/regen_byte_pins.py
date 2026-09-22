#!/usr/bin/env python3
"""Regenerate the frontend byte pins from the assets. DRC-4605.

Every change under `cargento_runtime/web/` moves a set of size and digest
assertions. The procedure is mechanical, it was uncommitted, and each change
re-derived it: five throwaway versions were written during one milestone and
none survived its session. This is that procedure, executed rather than
remembered.

Three things make it less trivial than it looks, and each one is a way a
hand-written version gets it wrong quietly rather than loudly.

**`expected_fonts` pins the base64-DECODED payload, not the file.** It is the
only table that pins something other than its file's own bytes. For
`ibm-plex-mono-v20-italic-latin` the payload is 11,568 bytes and the file is
15,627, with unrelated digests. A script that reads raw bytes for every table
writes real, plausible, wrong numbers into 15 entries -- both figures are
genuine sha256s of genuine bytes, so nothing looks off until CI reddens on
someone else's branch. Derivation is therefore a property of the TABLE here,
never of the file extension.

**`styles.css` is pinned in a different textual shape.** Two bare `assertEqual`
statements rather than a `name: (size, digest)` row, so a script that walks
table rows skips it in silence.

**`expected_faces` looks exactly like a pin table and is not one.** It maps each
font to its template slot and unicode range, in the same `"name": (` shape, and
carries no digest at all. This is the one that actually bites: a count or a
guard written against "rows that look like pins" reports 15 phantom entries, and
it produced two wrong readings before it was understood -- once in a throwaway
script that miscounted the tables, and once in the analysis that proposed this
one, which claimed on that basis that fonts were pinned twice under two
derivations. They are not. Only `expected_fonts` pins a font.

The tables are named rather than discovered, which is a hand-list and so the
same failure one layer along. `_unaccounted` is the answer: every row that has
the PIN shape -- a name, an integer and a 64-character digest -- must fall
inside a table this module knows, and one that does not raises instead of being
passed over. A sixth table fails loudly on its first run. Matching the looser
tuple shape instead is what produces the phantoms above, so the precision there
is load bearing rather than tidiness.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "cargento/skills/cargento/tests"
PINNED_FILES: tuple[str, ...] = ("test_next_page.py", "test_next_flag.py", "test_focus.py")

# Which derivation each pin table records. Keyed by the table's own variable
# name, because two tables hold the same keys and disagree about what the
# numbers mean.
DECODED = "decoded"
RAW = "raw"
TABLES: dict[str, str] = {
    "expected_parts": RAW,
    "expected_fonts": DECODED,
    "expected_notices": RAW,
    "assets": RAW,
}

_ROW = re.compile(
    r'^(?P<lead>\s+)"(?P<name>[^"]+)":\s*\(\s*\n'
    r"\s+(?P<size>[\d_]+),\s*\n"
    r'\s+"(?P<digest>[0-9a-f]{64})",\s*\n'
    r"\s*\),",
    re.MULTILINE,
)
# A PIN row, not any `"name": (` tuple. `expected_faces` maps each font to its
# template slot and its unicode range in exactly that shape and carries no
# digest at all, so a looser pattern reports 15 phantom gaps on a clean tree.
# The guard has to detect unaccounted PINS or it cries wolf and gets deleted.
_ANY_ROW = re.compile(
    r'^\s+"(?P<name>[^"]+)":\s*\(\s*\n\s+[\d_]+,\s*\n\s+"[0-9a-f]{64}",', re.MULTILINE
)


@dataclass(frozen=True)
class Change:
    """One figure this run would rewrite, named as a reader would look for it."""

    path: Path
    what: str


def _raw_bytes(web: Path, name: str) -> bytes:
    return (web / name).read_bytes()


def _decoded_bytes(web: Path, name: str) -> bytes:
    """The payload the page embeds, not the file that carries it."""
    encoded = "".join((web / name).read_text(encoding="ascii").splitlines())
    return base64.b64decode(encoded, validate=True)


_DERIVATIONS = {RAW: _raw_bytes, DECODED: _decoded_bytes}


def _table_span(text: str, name: str) -> tuple[int, int] | None:
    """The body of `name = {` ... `}`, by brace matching rather than by regex."""
    opened = re.search(rf"^\s+{re.escape(name)}(?::[^=\n]+)?\s*=\s*\{{$", text, re.MULTILINE)
    if opened is None:
        return None
    depth, i = 1, opened.end()
    while depth and i < len(text):
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return opened.end(), i - 1


def _unaccounted(text: str, spans: list[tuple[int, int]]) -> list[str]:
    """Pin rows that fall outside every table this module knows about."""
    return [
        m.group("name")
        for m in _ANY_ROW.finditer(text)
        if not any(start <= m.start() < end for start, end in spans)
    ]


def _rewrite_tables(text: str, web: Path, path: Path) -> tuple[str, list[Change]]:
    changes: list[Change] = []
    spans: list[tuple[int, int]] = []
    for table, kind in TABLES.items():
        span = _table_span(text, table)
        if span is None:
            continue
        derive = _DERIVATIONS[kind]
        # Rebuilt back to front so earlier offsets stay valid as the text grows.
        edits = []
        for match in _ROW.finditer(text, span[0], span[1]):
            name = match.group("name")
            data = derive(web, name)
            size, digest = len(data), hashlib.sha256(data).hexdigest()
            if int(match.group("size").replace("_", "")) != size:
                changes.append(Change(path, f"{name} size"))
            if match.group("digest") != digest:
                changes.append(Change(path, f"{name} digest"))
            if (
                int(match.group("size").replace("_", "")) == size
                and match.group("digest") == digest
            ):
                continue
            lead = match.group("lead")
            edits.append(
                (
                    match.start(),
                    match.end(),
                    f'{lead}"{name}": (\n{lead}    {size:_},\n{lead}    "{digest}",\n{lead}),',
                )
            )
        for start, end, replacement in reversed(edits):
            text = text[:start] + replacement + text[end:]
        # Recompute the span after editing this table, so the next one is found
        # against the text as it now stands rather than as it was.
        refreshed = _table_span(text, table)
        if refreshed is not None:
            spans.append(refreshed)
    stray = _unaccounted(text, spans)
    if stray:
        msg = (
            f"{path.name}: {len(stray)} pin rows sit outside every known table "
            f"({', '.join(sorted(set(stray))[:4])}). Add the table to TABLES with its "
            f"derivation rather than letting these go unwritten."
        )
        raise RuntimeError(msg)
    return text, changes


def _rewrite_scalar(
    text: str, path: Path, label: str, var: str, data: bytes
) -> tuple[str, list[Change]]:
    """The `assertEqual(N, len(x))` / bare-digest shape, which owns no table."""
    changes: list[Change] = []
    size, digest = len(data), hashlib.sha256(data).hexdigest()

    length = re.search(rf"self\.assertEqual\(\s*([\d_]+), len\({var}\)\)", text)
    if length is not None and int(length.group(1).replace("_", "")) != size:
        changes.append(Change(path, f"{label} length" if var != "styles" else f"{label} size"))
        text = (
            text[: length.start()]
            + f"self.assertEqual({size:_}, len({var}))"
            + text[length.end() :]
        )

    pattern = re.compile(rf'"([0-9a-f]{{64}})",(\s*\n\s*hashlib\.sha256\({var}\))')
    found = pattern.search(text)
    if found is not None and found.group(1) != digest:
        changes.append(Change(path, f"{label} digest"))
        text = pattern.sub(lambda m: f'"{digest}",{m.group(2)}', text, count=1)
    return text, changes


def regenerate(paths: list[Path], *, check: bool = False, web: Path | None = None) -> list[Change]:
    """Bring every pin in `paths` up to date. Returns what moved."""
    sys.path.insert(0, str(REPO / "cargento/skills/cargento"))
    # Deferred on purpose, the same way `bench_collect` defers its runtime
    # imports: `sys.path` has to carry the skill directory before the package
    # resolves, and the insert above is what puts it there.
    from cargento_runtime.web import page as frontend_page  # noqa: PLC0415

    root = web if web is not None else frontend_page.WEB_DIR
    assembled = frontend_page.load_page()
    styles = (root / "styles.css").read_bytes()

    changes: list[Change] = []
    for path in paths:
        original = path.read_text(encoding="utf-8")
        text, table_changes = _rewrite_tables(original, root, path)
        changes.extend(table_changes)
        text, styles_changes = _rewrite_scalar(text, path, "styles.css", "styles", styles)
        changes.extend(styles_changes)
        for var in ("assembled", "page"):
            text, page_changes = _rewrite_scalar(text, path, "assembled", var, assembled)
            changes.extend(page_changes)
        if text != original and not check:
            path.write_text(text, encoding="utf-8")
    return changes


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="report stale pins and exit non-zero without writing",
    )
    args = parser.parse_args(argv[1:])
    changes = regenerate([TESTS / name for name in PINNED_FILES], check=args.check)
    if not changes:
        print("byte pins are current")
        return 0
    verb = "stale" if args.check else "rewrote"
    for change in changes:
        print(f"{verb}: {change.what}  ({change.path.name})")
    print(f"{len(changes)} figures")
    return 1 if args.check else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main(sys.argv))
