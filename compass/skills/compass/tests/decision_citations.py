"""Lexical runtime decision pointers: reachability, not semantic ownership."""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from validate_plugins import heading_slugs

LABEL = r"(?:D-?|AC-?|DEC-|DR-|N-|NUI-|Q-|R-|S-|U-)\d+"
DECISION = re.compile(r"(?<![\w-])" + LABEL + r"(?![\w-])")
LINK = re.compile(r"\[(" + LABEL + r")\]\(([^\s()]+)\)")
HISTORY = re.compile(
    r"decision-history: (" + LABEL + r") \| (?:[0-9a-f]{7,40}|\d{4}-\d{2}-\d{2}) \| (.+)"
)


def _target_error(root: Path, target: str, anchors: dict[Path, set[str]]) -> str:
    name, separator, fragment = target.partition("#")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or "\\" in name
        or ".." in path.parts
        or path.suffix != ".md"
        or (len(path.parts) != 1 and path.parts[0] != "docs")
    ):
        return "missing/nonlocal document"
    document = (root / name).resolve()
    relative = document.relative_to(root) if document.is_relative_to(root) else None
    if (
        relative is None
        or (len(relative.parts) != 1 and relative.parts[0] != "docs")
        or not document.is_file()
    ):
        return "missing/nonlocal document"
    if document not in anchors:
        anchors[document] = heading_slugs(document)
    if not separator or not fragment or fragment not in anchors[document]:
        return "missing fragment"
    return ""


def citation_errors(root: Path, runtime: Path) -> list[str]:
    """Check source text without importing the scanned runtime."""
    root = root.resolve()
    runtime = runtime.resolve()
    anchors: dict[Path, set[str]] = {}
    errors = []
    for source in sorted(runtime.rglob("*")):
        if source.suffix not in {".py", ".js", ".css", ".html"} or not source.is_file():
            continue
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            links = {match.span(1): match.group(2) for match in LINK.finditer(line)}
            history = {
                match.span(1)
                for match in HISTORY.finditer(line)
                if re.sub(r"(?:\*/|-->)\s*$", "", match.group(2)).strip(" */#")
            }
            for decision in DECISION.finditer(line):
                target = links.get(decision.span())
                if target is not None:
                    error = _target_error(root, target, anchors)
                elif decision.span() in history:
                    error = ""
                else:
                    error = "missing local link or explicit history marker"
                if error:
                    errors.append(
                        f"{source.relative_to(root).as_posix()}:{number}: {decision.group()} "
                        f"target={target or '<none>'}: {error}"
                    )
    return errors
