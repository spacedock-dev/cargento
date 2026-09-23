"""A restricted CSS cascade resolver, for asking what size a slot renders at.

A value and the absence that replaces it never co-exist in one render: a ternary
in the emitter picks one class or the other. No sweep of co-existing selectors
and no reading of a populated board can see such a pair, so the only way to
compare them is to resolve each branch on its own. That is what this module is
for, and `AnAbsenceNeverOutranksTheValueItReplacesTest` is its caller.

Restricted deliberately. It handles the selector forms this stylesheet uses,
descendant and child combinators over tags, classes, attribute presence and
pseudo-classes, and refuses sibling combinators rather than guessing. Every
number it returns for that test's census was checked against `getComputedStyle`
in a real browser before it was committed; a form it cannot express belongs here
and gets checked the same way, never approximated.

**A pseudo-class is evaluated or refused, never skipped.** It used to be neither:
`_SIMPLE` parsed `:not([class])` into the compound and `_node_matches` then
compared only tag, classes and attributes, so the pseudo-class contributed
specificity while imposing no condition -- it always matched. Measured on
`de1550fa`: `:where(#app) button:not([class])` matched `<button class="next-action
next-notify-button">`, a button that plainly has a class, and contributed (0,2,1)
of specificity doing it. That is both halves of a wrong answer at once -- a rule
applied to elements the browser excludes, at a weight that outranks the real
winner -- and it reached a test, where a mutant had to carry an `#app` prefix to
beat a phantom. An unknown pseudo-class now raises `UnsupportedSelectorError`,
for the reason that exception already gives: a rule that leaves the cascade in
silence produces plausible numbers.

Two approximations remain, named rather than left to be discovered. An id is
counted for specificity and never matched, because a `Node` carries no id -- so
`#app` behaves as it did before this change. And a pseudo-ELEMENT still matches
the element it hangs off: it selects a generated box rather than the element, but
`path_for` is asked for paths whose leaf selector names one, and answering None
there would resolve the parent's size instead of the rule's own.

`@media` blocks are dropped on purpose: the census is the default viewport, and
a rule applying at one width only would otherwise outrank the base rule and
report a size nobody sees.
"""

from __future__ import annotations

import functools
import pathlib
import re
from typing import cast

Rule = tuple[str, str, int]
Node = dict[str, object]
Compound = dict[str, object]

_SIMPLE = re.compile(r"[.#][\w-]+|\[[^\]]+\]|::?[\w-]+(?:\([^)]*\))?")
_BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")

Specificity = tuple[int, int, int]
_NO_SPECIFICITY: Specificity = (0, 0, 0)

# A pseudo-class the element is in only while the reader is doing something to
# it, or while the document says so. The census reads a board at rest, so these
# match only a node that declares the state -- `rendered_paths` sets `disabled`
# from the attribute, and `path_for` sets whatever its own selector names.
_STATE_PSEUDO = frozenset(
    {
        "active",
        "checked",
        "disabled",
        "enabled",
        "focus",
        "focus-visible",
        "focus-within",
        "hover",
        "indeterminate",
        "open",
        "target",
        "visited",
    }
)

# Position in the parent, which needs a real tree. `rendered_paths` has one and
# fills `index`/`count` from it; a node built from a selector alone has neither,
# and a structural pseudo-class then does not match. Not matching is the safe
# direction here: the defect this module was carrying is a rule applied where
# the browser would not apply it.
_STRUCTURAL_PSEUDO = frozenset({"first-child", "last-child", "only-child", "root"})

# Selects a generated box rather than the element. Matched anyway -- see the
# module docstring for why -- and counted as an element, which is its real
# specificity. The legacy one-colon spellings are in the sheet and mean the same.
_PSEUDO_ELEMENTS = frozenset(
    {
        "after",
        "backdrop",
        "before",
        "file-selector-button",
        "first-letter",
        "first-line",
        "marker",
        "placeholder",
        "selection",
    }
)


def _split_list(text: str) -> list[str]:
    """A comma-separated selector list, split at the top level only.

    `str.split(",")` cuts `:is(a, input):focus-visible` in half and hands the
    resolver two selectors that parse into nonsense, one of which silently
    matched nothing while the other matched an element nobody renders.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _split_steps(selector: str) -> list[str]:
    """Compounds and bare combinators, split outside parentheses only.

    Two selector forms in this sheet break a plain `re.split`: `:is(a, input)`
    carries a space that belongs to one compound, and `:nth-child(-n+4)` carries
    a `+` that is arithmetic rather than a sibling combinator. Both were being
    cut in half, the first into two selectors that are not selectors and the
    second into a refusal for a sibling combinator that is not there.
    """
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in selector:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if depth == 0 and (char.isspace() or char in "+~>"):
            if current:
                parts.append("".join(current))
                current = []
            if char in "+~>":
                parts.append(char)
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _max_specificity(compounds: list[Compound]) -> Specificity:
    """The specificity `:is()` and `:not()` take: their most specific argument."""
    best = _NO_SPECIFICITY
    for compound in compounds:
        best = max(best, cast("Specificity", compound["spec"]))
    return best


def _argument_compounds(name: str, argument: str) -> list[Compound]:
    """The compounds inside a functional pseudo-class, one per listed selector.

    A combinator inside the argument is refused rather than flattened. `:not(a b)`
    is legal CSS and this sheet has none; accepting it by ignoring the descendant
    step would match elements the browser does not, which is the whole defect.
    """
    listed = _split_list(argument)
    for part in listed:
        if re.search(r"[\s>+~]", part):
            raise UnsupportedSelectorError(f":{name}({part}) uses a combinator")
    compounds = [_compound(part) for part in listed]
    if not compounds:
        raise UnsupportedSelectorError(f":{name}() is empty")
    return compounds


def _nth_terms(argument: str) -> tuple[int, int]:
    """`An+B` as (A, B). `odd` and `even` are their An+B spellings."""
    text = argument.replace(" ", "").lower()
    if text == "odd":
        return (2, 1)
    if text == "even":
        return (2, 0)
    match = re.fullmatch(r"([+-]?\d*)n([+-]\d+)?", text)
    if match:
        coefficient = match.group(1)
        step = 1 if coefficient in ("", "+") else -1 if coefficient == "-" else int(coefficient)
        return (step, int(match.group(2) or 0))
    if re.fullmatch(r"[+-]?\d+", text):
        return (0, int(text))
    raise UnsupportedSelectorError(f":nth-child({argument})")


def _strip_media(css: str) -> str:
    """Drop `@media` blocks, and refuse the case where that would hide a rule.

    Every media font rule in this stylesheet is `max-width`, so dropping them
    leaves the default viewport intact. A `min-width` block could raise or lower
    a size at a width people actually use, and silently ignoring it would let an
    always-true `@media(min-width:1px)` escape the guard, so it raises instead.
    """
    for block in re.finditer(r"@media\s*\(([^)]*)\)", css):
        if "min-width" in block.group(1) and "font" in css[block.end() : block.end() + 400]:
            raise UnsupportedSelectorError(f"@media ({block.group(1)}) sets a font size")
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
    return load_text(pathlib.Path(path).read_text(encoding="utf-8"))


# Sizes resolve in rem, because the sheet declares its scale in rem so the board
# follows the reader's own font-size setting. The reference below is what the
# rem figures were computed against, and it is the browser default: a reader who
# has not changed it renders exactly the px this module used to report.
ROOT_PX: float = 16.0


def rem(px: float) -> float:
    """A px figure as rem at the reference root, for readable assertions."""
    return px / ROOT_PX


def load_text(source: str) -> tuple[dict[str, float], list[Rule]]:
    """The same, from a string, so a mutant sheet resolves without a temp file."""
    body = _strip_media(re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL))
    tokens = {
        name: float(value) for name, value in re.findall(r"--(fs-[a-z0-9-]+):([0-9.]+)rem", body)
    }
    rules: list[Rule] = []
    for order, block in enumerate(_BLOCK.finditer(body)):
        rules.extend(
            (cleaned, block.group(2), order)
            for cleaned in _split_list(block.group(1))
            if not cleaned.startswith("@")
        )
    return tokens, rules


class _Parts:
    """The pieces of one compound, accumulated as its simple selectors are read.

    A small mutable carrier rather than locals, so the pseudo-class reader below
    can be its own function. That split is not cosmetic: the pseudo-class branch
    is where the defect was, and it is the part that grows each time the sheet
    takes up a new form.
    """

    def __init__(self) -> None:
        self.tag: str | None = None
        self.classes: set[str] = set()
        self.attrs: set[str] = set()
        self.states: set[str] = set()
        self.structural: set[str] = set()
        self.nth: list[tuple[int, int]] = []
        self.any_of: list[list[Compound]] = []
        self.nots: list[Compound] = []
        self.ids = 0
        self.pseudo = 0
        self.elements = 0
        self.nested: Specificity = _NO_SPECIFICITY


_FUNCTIONAL_PSEUDO = frozenset({"is", "not", "where"})


def _absorb_functional(part: str, name: str, argument: str | None, parts: _Parts) -> None:
    """`:is()`, `:where()` and `:not()`: a selector list, matched and weighted."""
    if argument is None:
        raise UnsupportedSelectorError(part)
    arguments = _argument_compounds(name, argument)
    if name == "not":
        parts.nots.extend(arguments)
    else:
        parts.any_of.append(arguments)
    # `:where()` is the one functional pseudo-class that adds nothing, which is
    # what it is for. `:is()` and `:not()` both take the specificity of their
    # most specific argument.
    if name != "where":
        parts.nested = cast(
            "Specificity",
            tuple(a + b for a, b in zip(parts.nested, _max_specificity(arguments), strict=True)),
        )


def _absorb_pseudo(part: str, parts: _Parts) -> None:
    """One `:pseudo` or `::pseudo` token, evaluated or refused. Never skipped."""
    token = re.fullmatch(r"(::?)([\w-]+)(?:\((.*)\))?", part)
    if token is None:
        raise UnsupportedSelectorError(part)
    colons, name, argument = token.group(1), token.group(2), token.group(3)
    if colons == "::" or name.startswith("-") or name in _PSEUDO_ELEMENTS:
        parts.elements += 1
        return
    if name in _FUNCTIONAL_PSEUDO:
        _absorb_functional(part, name, argument, parts)
        return
    if name == "nth-child":
        if argument is None:
            raise UnsupportedSelectorError(part)
        parts.nth.append(_nth_terms(argument))
    elif argument is not None:
        raise UnsupportedSelectorError(part)
    elif name in _STATE_PSEUDO:
        parts.states.add(name)
    elif name in _STRUCTURAL_PSEUDO:
        parts.structural.add(name)
    else:
        raise UnsupportedSelectorError(part)
    parts.pseudo += 1


def _compound(text: str) -> Compound:
    parts = _Parts()
    name = re.match(r"^([a-zA-Z*][\w-]*)", text)
    if name:
        parts.tag = name.group(1)
        text = text[name.end() :]
    for part in _SIMPLE.findall(text):
        if part.startswith("."):
            parts.classes.add(part[1:])
        elif part.startswith("#"):
            parts.ids += 1
        elif part.startswith("["):
            attr = re.match(r"\[([\w-]+)", part)
            if attr:
                parts.attrs.add(attr.group(1))
        else:
            _absorb_pseudo(part, parts)
    tag, classes, attrs = parts.tag, parts.classes, parts.attrs
    nested, pseudo, ids, elements = parts.nested, parts.pseudo, parts.ids, parts.elements
    states, structural, nth = parts.states, parts.structural, parts.nth
    any_of, nots = parts.any_of, parts.nots
    spec: Specificity = (
        ids + nested[0],
        len(classes) + len(attrs) + pseudo + nested[1],
        (1 if tag and tag != "*" else 0) + elements + nested[2],
    )
    return {
        "tag": None if tag == "*" else tag,
        "classes": classes,
        "attrs": attrs,
        "states": states,
        "structural": structural,
        "nth": nth,
        "any_of": any_of,
        "nots": nots,
        "spec": spec,
    }


class UnsupportedSelectorError(Exception):
    """A selector form this resolver cannot express.

    Raised rather than returned, because a `None` here reads to the caller as
    "did not match" and the rule then leaves the cascade in silence. A resolver
    that quietly forgets rules produces plausible numbers, which is the failure
    this whole guard exists to stop.
    """


def _steps(selector: str) -> list[tuple[str, Compound]]:
    """Selector as [(combinator, compound)], the first combinator ignored."""
    return list(_parsed_steps(selector))


# Parsed once per selector. The rendered-tier guards call `matches` about 840k
# times over a few hundred distinct selectors, and re-parsing was 5 of their
# 6.6 seconds (measured 2026-09-23). The compounds are shared between callers,
# so they are read-only by contract: nothing here writes to one after parsing.
@functools.cache
def _parsed_steps(selector: str) -> tuple[tuple[str, Compound], ...]:
    parts = _split_steps(selector.strip())
    if any(part in ("+", "~") for part in parts):
        raise UnsupportedSelectorError(selector)
    steps: list[tuple[str, Compound]] = []
    combinator = " "
    for part in parts:
        if part == ">":
            combinator = ">"
            continue
        steps.append((combinator, _compound(part)))
        combinator = " "
    return tuple(steps)


def _structural_matches(node: Node, name: str) -> bool:
    """A position pseudo-class against what the node knows of its own position.

    A node built from a selector rather than from a tree knows nothing, and every
    structural pseudo-class is then false. That is a decision, not a gap: the
    alternative -- matching when the position is unknown -- is the shape of the
    defect this module was carrying, a rule applied where the browser would not.
    """
    if name == "root":
        return node.get("root") is True
    index = node.get("index")
    count = node.get("count")
    if not isinstance(index, int):
        return False
    if name == "first-child":
        return index == 1
    if name == "last-child":
        return isinstance(count, int) and index == count
    return index == 1 and count == 1


def _nth_matches(node: Node, terms: list[tuple[int, int]]) -> bool:
    """`:nth-child(An+B)`, against the node's own 1-based position.

    An unknown position is false, for the reason `_structural_matches` gives.
    """
    index = node.get("index")
    if not isinstance(index, int):
        return not terms
    for step, offset in terms:
        remainder = index - offset
        if step == 0:
            if remainder != 0:
                return False
        elif remainder % step != 0 or remainder // step < 0:
            return False
    return True


def _simple_matches(node: Node, compound: Compound) -> bool:
    """Tag, classes and attribute presence: the part that never needed a tree."""
    tag = compound["tag"]
    if tag is not None and tag != node["tag"]:
        return False
    classes = compound["classes"]
    attrs = compound["attrs"]
    assert isinstance(classes, set) and isinstance(attrs, set)
    node_classes = node["classes"]
    node_attrs = node["attrs"]
    assert isinstance(node_classes, set) and isinstance(node_attrs, set)
    if not classes <= node_classes:
        return False
    # `class` is carried as the node's class set, not among its attribute names,
    # so `[class]` has to be answered from there. Without this the sheet's one
    # `button:not([class])` reads every classed button as unclassed -- the same
    # always-true the pseudo-class fix is here to remove, one layer down.
    if not {name for name in attrs if name != "class"} <= node_attrs:
        return False
    return not ("class" in attrs and not node_classes)


def _node_matches(node: Node, compound: Compound) -> bool:
    if not _simple_matches(node, compound):
        return False
    states = cast("set[str]", compound["states"])
    if states and not states <= cast("set[str]", node.get("states") or set()):
        return False
    if any(
        not _structural_matches(node, name) for name in cast("set[str]", compound["structural"])
    ):
        return False
    if not _nth_matches(node, cast("list[tuple[int, int]]", compound["nth"])):
        return False
    if any(
        not any(_node_matches(node, one) for one in group)
        for group in cast("list[list[Compound]]", compound["any_of"])
    ):
        return False
    return all(not _node_matches(node, one) for one in cast("list[Compound]", compound["nots"]))


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
    total = _NO_SPECIFICITY
    for _combinator, compound in steps:
        total = cast(
            "Specificity",
            tuple(a + b for a, b in zip(total, cast("Specificity", compound["spec"]), strict=True)),
        )
    return total


def declared_size(body: str, tokens: dict[str, float]) -> float | None:
    kind, value = _declared_size_source(body)
    if kind == "token":
        return tokens.get(str(value))
    return cast("float | None", value)


# The regexes below are the whole cost of `declared_size`, and `resolve` asks the
# same bodies again at every depth of every path; only the token lookup depends
# on the caller, so the source is cached and the lookup is not.
@functools.cache
def _declared_size_source(body: str) -> tuple[str, str | float | None]:
    token = re.search(r"font-size:\s*var\(--(fs-[a-z0-9-]+)\)", body) or re.search(
        r"font:[^;]*?var\(--(fs-[a-z0-9-]+)\)", body
    )
    if token:
        return ("token", token.group(1))
    # The lookbehind is load-bearing: without it `font:0.65rem/1.5` matched the
    # optional weight against `0` and the size resolved to `.65`.
    literal = re.search(r"font-size:\s*([0-9.]+)rem", body) or re.search(
        r"font:[^;{}]*?(?<![0-9.])([0-9.]+)rem", body
    )
    if literal:
        return ("size", float(literal.group(1)))
    # A px literal is off the scale by definition, and the sheet carries none.
    # It is still read, at the reference root, so a mutant written in px
    # resolves to something comparable rather than to nothing: a census that
    # silently answers None is the failure this whole module exists to avoid.
    fallback = re.search(r"font-size:\s*([0-9.]+)px", body) or re.search(
        r"font:[^;{}]*?(?<![0-9.])([0-9.]+)px", body
    )
    return ("size", rem(float(fallback.group(1))) if fallback else None)


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


def path_for(selector: str) -> list[Node]:
    """A node path the given selector matches, by construction.

    The census that calls this reads each rule's own declaration, which is a
    fact about the RULE. What a reader sees is a fact about the ELEMENT, and the
    two part company the moment two rules at equal specificity name the same
    element: `.next-guardrail-copy small` is declared at 15px in one grouped
    rule and 12.5px in the next, both (0,1,1), and the later one wins. A
    per-rule reading called that element compliant while it rendered below the
    floor -- so the census can OVERSTATE the compliant set, not only understate
    it as `docs/design-next-ui.md` said.

    Only the ancestors the selector names are built, which is the point: a rule
    needing an ancestor this selector does not mention correctly fails to match,
    while a rule matching the leaf alone correctly does. Descendant steps are
    built as a chain, so `>` and ` ` both resolve; sibling combinators raise,
    as everywhere else in this module.
    """
    path: list[Node] = []
    for _combinator, compound in _steps(selector):
        path.append(_node_for(compound))
    return path


def _node_for(compound: Compound) -> Node:
    """One node the compound matches, including the states its pseudo-classes name.

    The states and the child position are set from the compound for the same
    reason the classes are: this builds the element the selector describes. A
    compound that names no position leaves `index` and `count` unset, and every
    OTHER rule's structural pseudo-class then correctly fails against it.
    """
    classes = cast("set[str]", compound["classes"])
    attrs = cast("set[str]", compound["attrs"])
    states = cast("set[str]", compound["states"])
    structural = cast("set[str]", compound["structural"])
    node: Node = {
        "tag": compound["tag"] or "div",
        "classes": set(classes),
        "attrs": set(attrs),
    }
    if states:
        node["states"] = set(states)
    if "root" in structural:
        node["root"] = True
    index: int | None = None
    count: int | None = None
    if "only-child" in structural:
        index, count = 1, 1
    elif "first-child" in structural:
        index, count = 1, 2
    elif "last-child" in structural:
        index, count = 2, 2
    for step, offset in cast("list[tuple[int, int]]", compound["nth"]):
        index = (
            offset
            if step == 0
            else next((offset + step * n for n in range(64) if offset + step * n >= 1), None)
        )
        count = max(count or 0, index or 0)
    if index is not None:
        node["index"] = index
        node["count"] = count if count is not None else index
    # An `:is()`/`:not()` argument can also carry conditions, and the one this
    # sheet uses is a negation: nothing is added for it, because the node is
    # already free of what the negation excludes.
    for group in cast("list[list[Compound]]", compound["any_of"]):
        merged = _node_for(group[0])
        cast("set[str]", node["classes"]).update(cast("set[str]", merged["classes"]))
        cast("set[str]", node["attrs"]).update(cast("set[str]", merged["attrs"]))
        if merged["tag"] != "div":
            node["tag"] = merged["tag"]
    return node
