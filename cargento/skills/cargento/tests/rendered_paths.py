"""Element paths taken from what the emitters render, not from what a selector says.

`css_cascade.path_for` builds a path out of the tier selector itself, so it
builds exactly the ancestors that selector names and no others. That is correct
for the question it was written for and structurally blind to a second one: a
rule reaching the same element through ancestors the tier selector never
mentions can take it below the floor, and no path derived from that selector
will ever let the two rules meet. Measured on `58b1a81e`: inserting
`.next-steer>header p{font-size:var(--fs-label)}` takes `.next-steer-caveat`
from 0.9375rem to 0.8125rem, and the selector-derived sweep reports zero
below-floor selectors and zero skips.

So the paths here come from the other end. The page's own JS is executed under
the node harness, the HTML it writes into `#app` is parsed, and each element
becomes a path carrying its real ancestor chain. Nothing is hypothesised and
nothing is hand-listed: the source is the emitter output, and a surface nobody
renders contributes no paths.

Two things this deliberately does not do.

It does not enumerate every DOM the application could produce. Widening the
guard that way was tried and rejected on the record at 8,873 false positives on
a clean sheet, which is the "built a DOM the application never renders" failure
this repository already carries. What renders here is what the fixtures below
drive, and `coverage()` reports that rather than implying more.

It does not claim a count. The set of paths is a floor on the rendered
population, in the same sense the milestone's density figures are floors: a
busier board renders more elements, never fewer. Any figure taken from it
carries the fixture it was taken on.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .css_cascade import Node

# Void elements never open a scope, so the parser must not push them. Without
# this an `<img>` or `<br>` mid-panel would swallow every following sibling as
# its descendant and manufacture ancestor chains the page never renders --
# which is the same class of error as hypothesising a DOM, arriving by accident.
_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


class _PathCollector(HTMLParser):
    """Every open element, as a path of `css_cascade` nodes from the root."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paths: list[list[Node]] = []
        self._stack: list[Node] = []
        # Siblings opened so far under each open element, plus one bucket for
        # the fragment's own top level. `count` is settled on the way out, so
        # `:last-child` is answered rather than guessed -- the path entries hold
        # the same dicts, so filling it late fills it everywhere.
        self._children: list[list[Node]] = [[]]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pairs = dict(attrs)
        names = {name for name, _value in attrs if name != "class"}
        node: Node = {
            "tag": tag,
            "classes": set((pairs.get("class") or "").split()),
            # Attribute PRESENCE only, which is what `css_cascade` matches on.
            "attrs": names,
        }
        # The one state a rendered element declares about itself. Every other
        # state pseudo-class needs a reader doing something, and this census
        # reads a board at rest.
        if "disabled" in names:
            node["states"] = {"disabled"}
        siblings = self._children[-1]
        siblings.append(node)
        node["index"] = len(siblings)
        self._stack.append(node)
        self._children.append([])
        self.paths.append([*self._stack])
        if tag in _VOID:
            self._close(len(self._stack) - 1)

    def _close(self, depth: int) -> None:
        """Pop back to `depth`, settling `count` on each scope left behind."""
        while len(self._stack) > depth:
            self._stack.pop()
            siblings = self._children.pop()
            for child in siblings:
                child["count"] = len(siblings)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self._close(len(self._stack) - 1)

    def handle_endtag(self, tag: str) -> None:
        # Walk back to the nearest matching open tag rather than popping blind.
        # An unbalanced fragment would otherwise shift every later element up
        # one level and invent ancestors, silently.
        for depth in range(len(self._stack) - 1, -1, -1):
            if self._stack[depth]["tag"] == tag:
                self._close(depth)
                return

    def close(self) -> None:
        super().close()
        self._close(0)
        for child in self._children[0]:
            child["count"] = len(self._children[0])


def paths_in(html: str) -> list[list[Node]]:
    """Each element in `html`, as a path carrying its real ancestor chain."""
    collector = _PathCollector()
    collector.feed(html)
    collector.close()
    return collector.paths


# One payload, shaped to render as many distinct surfaces as it can rather than
# to be realistic. Sessions differ by harness and state on purpose: the cockpit
# and the rails branch on both, and a fixture where every row is identical
# renders one row's worth of selectors however many rows it carries.
FIXTURE_PAYLOAD: dict[str, object] = {
    "generated": 1000,
    "window_hours": 24,
    "summary": {"working": 1, "needs_input": 1},
    "harnesses": [
        {"harness": "claude", "sessions": 2, "working": 1},
        {"harness": "codex", "sessions": 1, "working": 0},
    ],
    "sessions": [
        {
            "harness": "claude",
            "sid": "s1",
            "project": "recce/cargento",
            "state": "working",
            "title": "A session that is working",
            "started_at": 900,
            "updated_at": 990,
            "model": "opus",
            "cwd": "/repo",
            "turns": 4,
            "goal": "ship the composing guard",
        },
        {
            "harness": "codex",
            "sid": "s2",
            "project": "recce/cargento",
            "state": "needs_input",
            "title": "A session stopped at a gate",
            "started_at": 800,
            "updated_at": 980,
            "model": "gpt",
            "cwd": "/repo",
            "turns": 2,
        },
        {
            "harness": "claude",
            "sid": "s3",
            "project": "recce/other",
            "state": "idle",
            "title": "A session that went quiet",
            "started_at": 700,
            "updated_at": 900,
            "model": "sonnet",
            "cwd": "/other",
            "turns": 9,
        },
    ],
}

# The routes the board offers: the four top-level views, then the cockpit on
# each of its own tabs, then one session. The hash is set in the prelude rather
# than after the bundle loads, because the route is parsed once at boot --
# setting it afterwards renders the default view under a different hash and
# silently measures one surface five times over. Measured: the four top-level
# routes alone leave `.next-steer` unrendered, so the guard below had nothing
# to say about the very mutation DRC-4614 names.
#
# The tab spellings come from the route parser, which accepts a tab only when
# `nextCockpitTabs` lists it, so a renamed tab drops that route to the default
# view rather than failing. `coverage()` is what notices: the element count for
# the dropped route collapses onto the default one's.
FIXTURE_ROUTES: tuple[str, ...] = (
    "",
    "#n=projects",
    "#n=sessions",
    "#n=attention",
    "#n=intent",
    "#n=project:recce%2Fcargento",
    "#n=project:recce%2Fcargento:course",
    "#n=project:recce%2Fcargento:held-to",
    "#n=project:recce%2Fcargento:decisions",
    "#n=session:recce%2Fcargento:claude:s1",
)


def render_script(route: str, payload: dict[str, object] | None = None) -> str:
    """A check body that boots the page on `route` and prints what it rendered."""
    body = json.dumps(payload if payload is not None else FIXTURE_PAYLOAD)
    return (
        'location.search = "";\n'
        '__els.app = {innerHTML: ""};\n'
        f"__fetchImpl = async () => ({{ok: true, json: async () => ({body})}});\n"
        f"location.hash = {json.dumps(route)};\n"
        "await refreshNext();\n"
        "console.log(JSON.stringify(__els.app.innerHTML));\n"
    )
