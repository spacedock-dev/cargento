"""A restricted CSS cascade resolver, for asking what size a slot renders at.

A value and the absence that replaces it never co-exist in one render: a ternary
in the emitter picks one class or the other. No sweep of co-existing selectors
and no reading of a populated board can see such a pair, so the only way to
compare them is to resolve each branch on its own. That is what this module is
for, and `AnAbsenceNeverOutranksTheValueItReplacesTest` is its caller.

Restricted deliberately. It handles the selector forms this stylesheet uses,
descendant and child combinators over tags, classes and attribute presence, and
refuses sibling combinators rather than guessing. Every number it returns for
that test's census was checked against `getComputedStyle` in a real browser
before it was committed; a form it cannot express belongs here and gets checked
the same way, never approximated.

`@media` blocks are dropped on purpose: the census is the default viewport, and
a rule applying at one width only would otherwise outrank the base rule and
report a size nobody sees.
"""

from __future__ import annotations

import pathlib
import re

Rule = tuple[str, str, int]
Node = dict[str, object]
Compound = dict[str, object]

_SIMPLE = re.compile(r"[.#][\w-]+|\[[^\]]+\]|::?[\w-]+(?:\([^)]*\))?")
_BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _strip_media(css: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(css):
        if not css.startswith("@media", index):
            out.append(css[index])
            index += 1
            continue
        cursor = css.find("{", index)
        depth = 0
        while cursor < len(css):
            if css[cursor] == "{":
                depth += 1
            elif css[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        index = cursor + 1
    return "".join(out)


def load(path: pathlib.Path | str) -> tuple[dict[str, float], list[Rule]]:
    """Return the `--fs-*` token table and every non-media rule, in source order."""
    source = pathlib.Path(path).read_text(encoding="utf-8")
    body = _strip_media(re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL))
    tokens = {
        name: float(value) for name, value in re.findall(r"--(fs-[a-z0-9-]+):([0-9.]+)px", body)
    }
    rules: list[Rule] = []
    for order, block in enumerate(_BLOCK.finditer(body)):
        for selector in block.group(1).split(","):
            cleaned = selector.strip()
            if cleaned and not cleaned.startswith("@"):
                rules.append((cleaned, block.group(2), order))
    return tokens, rules


def _compound(text: str) -> Compound:
    tag: str | None = None
    classes: set[str] = set()
    attrs: set[str] = set()
    ids = 0
    pseudo = 0
    name = re.match(r"^([a-zA-Z*][\w-]*)", text)
    if name:
        tag = name.group(1)
        text = text[name.end() :]
    for part in _SIMPLE.findall(text):
        if part.startswith("."):
            classes.add(part[1:])
        elif part.startswith("#"):
            ids += 1
        elif part.startswith("["):
            attr = re.match(r"\[([\w-]+)", part)
            if attr:
                attrs.add(attr.group(1))
        elif not part.startswith("::"):
            pseudo += 1
    return {
        "tag": None if tag == "*" else tag,
        "classes": classes,
        "attrs": attrs,
        "ids": ids,
        "weight": len(classes) + len(attrs) + pseudo,
    }


def _steps(selector: str) -> list[tuple[str, Compound]] | None:
    """Selector as [(combinator, compound)], the first combinator ignored."""
    parts = [p for p in re.split(r"\s*(>|\+|~)\s*|\s+", selector.strip()) if p]
    if any(part in ("+", "~") for part in parts):
        return None
    steps: list[tuple[str, Compound]] = []
    combinator = " "
    for part in parts:
        if part == ">":
            combinator = ">"
            continue
        steps.append((combinator, _compound(part)))
        combinator = " "
    return steps


def _node_matches(node: Node, compound: Compound) -> bool:
    tag = compound["tag"]
    if tag is not None and tag != node["tag"]:
        return False
    classes = compound["classes"]
    attrs = compound["attrs"]
    assert isinstance(classes, set) and isinstance(attrs, set)
    node_classes = node["classes"]
    node_attrs = node["attrs"]
    assert isinstance(node_classes, set) and isinstance(node_attrs, set)
    return classes <= node_classes and attrs <= node_attrs


def _walk(path: list[Node], ancestors: list[tuple[str, Compound]]) -> bool:
    """Match the ancestor steps right to left; the leaf is already matched.

    Each entry pairs a compound with the combinator that joins it to the step on
    its RIGHT, not the one on its left, which is the off-by-one that makes a
    child combinator behave like a descendant one.
    """
    index = len(path) - 2
    for combinator, compound in reversed(ancestors):
        if combinator == ">":
            if index < 0 or not _node_matches(path[index], compound):
                return False
            index -= 1
            continue
        while index >= 0 and not _node_matches(path[index], compound):
            index -= 1
        if index < 0:
            return False
        index -= 1
    return True


def matches(path: list[Node], selector: str) -> tuple[int, int, int] | None:
    """Specificity if `selector` matches the leaf of `path`, else None."""
    steps = _steps(selector)
    if not steps or not _node_matches(path[-1], steps[-1][1]):
        return None
    ancestors = [(steps[i + 1][0], steps[i][1]) for i in range(len(steps) - 1)]
    if not _walk(path, ancestors):
        return None
    ids = sum(int(step[1]["ids"]) for step in steps)  # type: ignore[call-overload]
    weight = sum(int(step[1]["weight"]) for step in steps)  # type: ignore[call-overload]
    tags = sum(1 for step in steps if step[1]["tag"])
    return (ids, weight, tags)


def declared_size(body: str, tokens: dict[str, float]) -> float | None:
    token = re.search(r"font-size:\s*var\(--(fs-[a-z0-9-]+)\)", body) or re.search(
        r"font:[^;]*?var\(--(fs-[a-z0-9-]+)\)", body
    )
    if token:
        return tokens.get(token.group(1))
    # The lookbehind is load-bearing: without it `font:10.5px/1.5` matched the
    # optional weight against `10` and the size resolved to 0.5px.
    literal = re.search(r"font-size:\s*([0-9.]+)px", body) or re.search(
        r"font:[^;{}]*?(?<![0-9.])([0-9.]+)px", body
    )
    return float(literal.group(1)) if literal else None


def resolve(path: list[Node], tokens: dict[str, float], rules: list[Rule]) -> float | None:
    """The font size the leaf of `path` renders at, inheriting where undeclared."""
    for depth in range(len(path), 0, -1):
        subject = path[:depth]
        best: tuple[tuple[tuple[int, int, int], int], float] | None = None
        for selector, body, order in rules:
            size = declared_size(body, tokens)
            if size is None:
                continue
            specificity = matches(subject, selector)
            if specificity is None:
                continue
            key = (specificity, order)
            if best is None or key > best[0]:
                best = (key, size)
        if best is not None:
            return best[1]
    return None
