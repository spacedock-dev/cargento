"""Every string literal a page script can emit, reassembled across `+`.

Written because the alternative is a list. Four criteria in this milestone were
drafted as "every sentence of kind X still does Y" and verified over a handful
of strings someone typed out; each one passed while an instance it had never
heard of did the opposite. A list cannot fail on the sentence it omits, so the
sweeps that replace those criteria derive their subject from the source and the
only thing left to get wrong is the derivation.

The reassembly is the part that matters. The bundle wraps long sentences across
lines with `+`, so a scan for whole literals finds `"A reading is a model's
account of the evidence on this page: the observed record below "` and never the
sentence. Adjacent literals joined only by `+` and whitespace are one string
here, which is what the renderer puts on the page.

Restricted on purpose, like `css_cascade` next door: this reads the forms this
bundle uses -- quoted strings, template literals with no substitution, line and
block comments, and regex literals -- and nothing else. A template literal
carrying `${...}` is split at each hole rather than guessed at, because the
hole's value is not in the file.
"""

from __future__ import annotations

import re

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}

# A `/` opens a regex only where a value cannot already have ended. Anything
# else is division. The list is the punctuation this bundle actually puts in
# front of one, plus the keywords; a form not here is read as division, which
# costs at most one spurious literal boundary and never a wrong sentence.
_REGEX_OPENERS = set("(,=:[!&|?{};+-*%~^") | {"\n"}
_KEYWORD_BEFORE_REGEX = re.compile(r"\b(?:return|typeof|instanceof|in|of|new|delete|void)$")


def _unescape(raw: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(raw):
            break
        marker = raw[index]
        if marker == "u" and raw[index + 1 : index + 2] == "{":
            shut = raw.index("}", index)
            out.append(chr(int(raw[index + 2 : shut], 16)))
            index = shut + 1
        elif marker == "u":
            out.append(chr(int(raw[index + 1 : index + 5], 16)))
            index += 5
        elif marker == "x":
            out.append(chr(int(raw[index + 1 : index + 3], 16)))
            index += 3
        elif marker == "\n":
            index += 1
        else:
            out.append(_ESCAPES.get(marker, marker))
            index += 1
    return "".join(out)


def _scan(source: str) -> list[tuple[int, int, str]]:
    """(start, end, text) for every string literal, in source order."""
    found: list[tuple[int, int, str]] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char == "/" and source[index + 1 : index + 2] == "/":
            index = source.find("\n", index)
            if index == -1:
                break
            continue
        if char == "/" and source[index + 1 : index + 2] == "*":
            shut = source.find("*/", index + 2)
            index = length if shut == -1 else shut + 2
            continue
        if char == "/":
            prefix = source[:index].rstrip()
            opener = prefix[-1:] if prefix else "\n"
            if opener in _REGEX_OPENERS or _KEYWORD_BEFORE_REGEX.search(prefix):
                index = _skip_regex(source, index)
                continue
            index += 1
            continue
        if char in {'"', "'", "`"}:
            index = _read_string(source, index, char, found)
            continue
        index += 1
    return found


def _read_string(source: str, index: int, quote: str, found: list[tuple[int, int, str]]) -> int:
    """Consume one literal from its opening quote, appending what it yields.

    A template literal yields one entry per run of constant text, because a
    `${...}` hole ends the run it sits in: the hole's value is not in the file,
    and joining across it would invent a sentence nobody wrote.
    """
    start = index
    index += 1
    body: list[str] = []
    while index < len(source):
        here = source[index]
        if here == "\\":
            body.append(source[index : index + 2])
            index += 2
            continue
        if here == quote:
            index += 1
            break
        if quote == "`" and here == "$" and source[index + 1 : index + 2] == "{":
            found.append((start, index, _unescape("".join(body))))
            index = _skip_braces(source, index + 1)
            start = index
            body = []
            continue
        body.append(here)
        index += 1
    found.append((start, index, _unescape("".join(body))))
    return index


def _skip_regex(source: str, index: int) -> int:
    index += 1
    in_class = False
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            return index + 1
        elif char == "\n":
            return index
        index += 1
    return index


def _skip_braces(source: str, index: int) -> int:
    depth = 0
    while index < len(source):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


_JOIN = re.compile(r"^\s*\+\s*$")


def emitted_strings(source: str) -> list[str]:
    """Every literal, with `+`-concatenated runs joined into one string.

    A run is joined only when nothing but whitespace and `+` separates its
    parts, so `esc(x) + "..."` stays two strings and a wrapped sentence becomes
    one.
    """
    literals = _scan(source)
    joined: list[str] = []
    index = 0
    while index < len(literals):
        start, end, text = literals[index]
        parts = [text]
        cursor = end
        step = index + 1
        while step < len(literals) and _JOIN.match(source[cursor : literals[step][0]]):
            parts.append(literals[step][2])
            cursor = literals[step][1]
            step += 1
        joined.append("".join(parts))
        index = max(index + 1, step)
        _ = start
    return joined


_READING_WHY = re.compile(r'class="next-cockpit-reading-why"[^>]*>(.*?)</p>', re.DOTALL)
_SENTENCE_END = re.compile(r"(?<=\.)\s+")


def reading_why_sentences(source: str, *, floor: int = 25) -> set[str]:
    """Every constant caveat sentence the script puts inside a `reading-why`.

    Paragraph, then sentence, because the tiering this verifies SPLITS a
    paragraph: DRC-4591 moved the remainder of a two-sentence caveat behind a
    disclosure, so the paragraph stopped existing while both of its sentences
    survived. Comparing paragraphs would have reported that as a deletion.

    Constant text only. A paragraph assembled through `${...}` is dropped
    rather than guessed at, since the hole's value is not in the file, and
    `floor` drops fragments too short to be a sentence.
    """
    found: set[str] = set()
    for run in emitted_strings(source):
        for chunk in _READING_WHY.findall(run):
            for sentence in _SENTENCE_END.split(" ".join(chunk.split())):
                text = sentence.strip()
                if len(text) > floor:
                    found.add(text)
    return found
