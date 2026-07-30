#!/usr/bin/env python3
"""Lint the dashboard frontend source files.

The Cargento dashboard ships its HTML, CSS, and JavaScript as direct source
files. Python linters cannot see inside those assets, so this script checks
them:

- JavaScript: syntax-checked with ``node --check`` (hard requirement; pass
  ``--allow-missing-node`` to degrade to a warning for local machines
  without node).
- CSS: structural checks — balanced braces, no empty rules, no stray ``<``
  outside selectors, every declaration line ends in ``}`` or ``;``.
- HTML shell: every ``id=`` referenced from the JS via
  ``getElementById`` exists either in the static HTML or is created by the
  JS itself (catches renamed-element regressions the unit tests may miss).

Exit code 0 when clean; 1 with a findings listing otherwise.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WEB_DIR = (
    Path(__file__).resolve().parents[1]
    / "cargento"
    / "skills"
    / "cargento"
    / "cargento_runtime"
    / "web"
)


def load_frontend(web_dir: Path = WEB_DIR) -> tuple[str, str, str]:
    return (
        (web_dir / "index.html").read_text(encoding="utf-8"),
        (web_dir / "styles.css").read_text(encoding="utf-8"),
        (web_dir / "app.js").read_text(encoding="utf-8"),
    )


def check_js(js: str, *, allow_missing_node: bool) -> list[str]:
    node = shutil.which("node")
    if node is None:
        message = "node not found — JS syntax check skipped"
        if allow_missing_node:
            print(f"warning: {message}")
            return []
        return [message + " (install node or pass --allow-missing-node)"]
    # Explicit UTF-8: without it Windows writes through the locale codec (cp1252),
    # and any non-Latin-1 character in the page — an arrow, a box-drawing glyph —
    # raises UnicodeEncodeError instead of being linted. node reads UTF-8.
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(js)
        temp_path = Path(handle.name)
    try:
        proc = subprocess.run(  # noqa: S603 — fixed binary resolved via which()
            [node, "--check", str(temp_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        temp_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        return [f"frontend JS failed node --check:\n{proc.stderr.strip()}"]
    return []


def check_css(css: str) -> list[str]:
    problems: list[str] = []
    depth = 0
    for lineno, raw in enumerate(css.splitlines(), start=1):
        line = raw.strip()
        depth += line.count("{") - line.count("}")
        if depth < 0:
            problems.append(f"css line {lineno}: unbalanced closing brace")
            depth = 0
        if "{}" in line.replace(" ", ""):
            problems.append(f"css line {lineno}: empty rule")
    if depth != 0:
        problems.append(f"css: {depth} unclosed brace(s) at end of block")
    return problems


def check_dom_ids(page: str, js: str) -> list[str]:
    referenced = set(re.findall(r"getElementById\(\"([\w-]+)\"\)", js))
    static_ids = set(re.findall(r'id="([\w-]+)"', page))
    created_ids = set(re.findall(r'id=\\?"([\w-]+)\\?"', js))
    missing = referenced - static_ids - created_ids
    return [
        f'js references getElementById("{element_id}") but no such id exists '
        "in the static HTML or is created by the JS"
        for element_id in sorted(missing)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-missing-node",
        action="store_true",
        help="degrade the node JS syntax check to a warning when node is absent",
    )
    args = parser.parse_args()

    page, css, js = load_frontend()

    problems = (
        check_js(js, allow_missing_node=args.allow_missing_node)
        + check_css(css)
        + check_dom_ids(page, js)
    )
    if problems:
        for problem in problems:
            print(f"error: {problem}")
        print(f"{len(problems)} frontend problem(s) found.")
        return 1
    print("Frontend assets clean (JS syntax, CSS structure, DOM id references).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
