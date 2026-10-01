"""What a sighted reader sees of rendered page markup, as text.

The tag-strip `visible_text` helpers the page suites grew each keep two kinds of text no sighted
reader sees: the body of a closed `<details>` and a `.next-visually-hidden` node. Both stay in the
DOM on purpose, so a screen reader and the rendered-text tests still reach them, which made
"moved behind a disclosure" and "visible" indistinguishable to every assertion written with those
helpers. This one drops both, and keeps a closed `<details>`'s `<summary>`, which is what the reader
sees in its place. A `hidden` attribute is dropped too, as the browser drops it.

It reads markup, not layout: text a stylesheet hides by any other rule is still counted, and that
is the conservative side for an assertion that a sentence is out of view.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Elements with no end tag, so they never open a level of the stack.
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
        "source",
        "track",
        "wbr",
    }
)
_HIDDEN_CLASS = "next-visually-hidden"


class _Visible(HTMLParser):
    """Collects text outside hidden subtrees.

    Each open element pushes whether its contents are hidden. A closed `<details>` hides
    everything but its own `<summary>`, which is tracked by depth rather than by name, so a
    nested `<details>` inside the summary of an open one is handled by the same rule.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # (tag, hides its descendants, is a closed details whose summary is still to come)
        self._stack: list[tuple[str, bool, bool]] = []
        self.parts: list[str] = []

    def _hidden(self) -> bool:
        return any(hides for _tag, hides, _closed in self._stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID:
            return
        named = dict(attrs)
        classes = (named.get("class") or "").split()
        hides = _HIDDEN_CLASS in classes or "hidden" in named
        parent = self._stack[-1] if self._stack else None
        if parent is not None and parent[2] and tag != "summary":
            # A child of a closed details that is not its summary is behind the disclosure.
            hides = True
        closed = tag == "details" and "open" not in named
        self._stack.append((tag, hides, closed))

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        # Pop to the matching open element; tolerate the unclosed `<p>` and `<li>` HTML allows.
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        parent = self._stack[-1] if self._stack else None
        if parent is not None and parent[2]:
            # Loose text directly inside a closed details is behind it as well.
            return
        if not self._hidden():
            self.parts.append(data)


def visible_text(html: str) -> str:
    """The text a sighted reader sees, whitespace collapsed to single spaces."""
    parser = _Visible()
    parser.feed(html)
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
