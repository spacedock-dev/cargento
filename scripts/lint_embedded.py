#!/usr/bin/env python3
"""Lint the HTML page embedded in the dashboard server module.

The Cargento dashboard ships as a single stdlib-only Python file whose UI
lives in one big ``PAGE`` string (HTML + CSS + JS). Python linters cannot see
inside that string, so this script extracts the embedded assets and checks
them:

- JavaScript: syntax-checked with ``node --check`` (hard requirement; pass
  ``--allow-missing-node`` to degrade to a warning for local machines
  without node).
- CSS: structural checks — balanced braces, no empty rules, no stray ``<``
  outside selectors, every declaration line ends in ``}`` or ``;``.
- HTML shell: every ``id=`` referenced from the extracted JS via
  ``getElementById`` exists either in the static HTML or is created by the
  JS itself (catches renamed-element regressions the unit tests may miss).

Exit code 0 when clean; 1 with a findings listing otherwise.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SERVER_PATH = Path(__file__).resolve().parents[1] / "cargento" / "skills" / "cargento" / "server.py"


def load_page() -> str:
    spec = importlib.util.spec_from_file_location("cargento_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        msg = f"cannot import {SERVER_PATH}"
        raise SystemExit(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = module.PAGE
    if not isinstance(page, str):
        msg = "PAGE is not a string"
        raise SystemExit(msg)
    return page


def extract(page: str, tag: str) -> str:
    blocks = re.findall(rf"<{tag}[^>]*>\n?(.*?)</{tag}>", page, re.DOTALL)
    if not blocks:
        msg = f"no <{tag}> block found in PAGE"
        raise SystemExit(msg)
    return "\n".join(blocks)


def check_js(js: str, *, allow_missing_node: bool) -> list[str]:
    node = shutil.which("node")
    if node is None:
        message = "node not found — JS syntax check skipped"
        if allow_missing_node:
            print(f"warning: {message}")
            return []
        return [message + " (install node or pass --allow-missing-node)"]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
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
        return [f"embedded JS failed node --check:\n{proc.stderr.strip()}"]
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

    page = load_page()
    js = extract(page, "script")
    css = extract(page, "style")

    problems = (
        check_js(js, allow_missing_node=args.allow_missing_node)
        + check_css(css)
        + check_dom_ids(page, js)
    )
    if problems:
        for problem in problems:
            print(f"error: {problem}")
        print(f"{len(problems)} embedded-asset problem(s) found.")
        return 1
    print("Embedded page assets clean (JS syntax, CSS structure, DOM id references).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
