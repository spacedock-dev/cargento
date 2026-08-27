#!/usr/bin/env python3
"""Re-derive the prompt-shape counts written into `records.py`.

Every number in the "Harness-injected prompts" comment block of
`cargento_runtime/records.py` was measured against a real local store. Until this
script existed the measuring code did not survive the measurement, so no reviewer
could tell a derived count from a plausible one. This is that code, kept.

    python3 scripts/derive_prompt_shapes.py                       # default roots
    python3 scripts/derive_prompt_shapes.py --claude-root DIR --codex-root DIR
    python3 scripts/derive_prompt_shapes.py --no-codex            # one half only

**It prints counts and shape names, never prompt text.** That is a deliverable
constraint, not a courtesy: a transcript store holds whatever the operator typed,
including credentials, and a derivation script is the one tool whose whole job is
to read all of it. So every emitted label goes through `_safe_label`, which
accepts a markup tag name (`[A-Za-z][A-Za-z0-9_-]*`), a literal already present in
`records.py`'s own vocabularies, or a fixed structural label defined below —
and raises on anything else. Discovering a *new* prose prefix would require
printing prose, so it is deliberately out of scope; the tag half discovers new
names on its own because a tag name is markup rather than text.

`records._HARNESS_CONTROL_COMMANDS` is also out of scope. Its counts are
"occurrences as the last published GOAL", which is a derivation over the
observer's session-level pick rather than a shape scan over records, so it needs
a different instrument than this one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "cargento" / "skills" / "cargento"
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from cargento_runtime import records  # noqa: E402

DEFAULT_CLAUDE_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_CODEX_ROOT = Path.home() / ".codex" / "sessions"

# The collectors' own globs, so the population this reports is the population the
# dashboard actually reads rather than a wider sweep of the same directory.
CLAUDE_GLOB = "*/*.jsonl"
CODEX_GLOB = "*/*/*/rollout-*.jsonl"

# A markup tag name, and short enough to be one. The length bound is the part
# that matters: without it a hyphenated run with no spaces in it — which is what
# a prompt looks like once it is one long token — reads as a tag name and would
# be printed. The longest TAG name in any of `records.py`'s vocabularies is 21
# characters (`subagent_notification`); the longer entries there are prose
# prefixes, which reach stdout through `_safe_label`'s membership clauses and not
# through this pattern.
#
# 24 and not 40. At 40 a prompt opening with `<` plus a 40-character
# `[A-Za-z0-9_-]` run reached stdout verbatim, which falsified this module's own
# docstring on the one script whose job is to read every prompt in the store. The
# discovery affordance survives the narrower bound: over 3,774 local Claude
# transcripts there are exactly 2 distinct unlisted leading tag names occurring
# more than once, both 21 characters or shorter, and 0 occurrences of the
# over-long aggregate.
_TAG_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,23}$")

# Leading image-marker populations, reported separately because they are three
# populations and were once counted as one. `[Image #N]` is Codex's spelling
# reaching a Claude record through a pasted screenshot; the other two are
# Claude's own.
_IMAGE_SHAPES = (
    ("[Image: …]", re.compile(r"^\s*\[Image:", re.IGNORECASE)),
    ("[Image source…]", re.compile(r"^\s*\[Image source", re.IGNORECASE)),
    ("[Image #N]", re.compile(r"^\s*\[Image\s*#", re.IGNORECASE)),
    ("<image> (Codex tag)", re.compile(r"^\s*<image\b", re.IGNORECASE)),
)

# Structural labels this script emits that are neither a tag name nor a listed
# literal. Enumerated so `_safe_label` can be a whitelist rather than a filter.
_STRUCTURAL_LABELS = frozenset(
    {name for name, _ in _IMAGE_SHAPES}
    | {
        "files scanned",
        "user-role texts",
        "developer-role texts",
        "event_msg user_message texts",
        "response_item user texts",
        "dual-written event_msg prompts",
        "leading",
        "contained",
        "refused by _turn_signal",
        "strips to empty",
        "carries operator text",
        "in subagent rollouts",
        "in sidechain records",
        "whole-body matches",
        "leading tag names too long to print",
    }
)

# Where a discovered tag name longer than `_TAG_NAME_RE` allows is counted. It is
# aggregated rather than named, and rather than raised on: a name that long is
# almost certainly prose that happened to open with `<`, so printing it would be
# the leak the guard exists to stop, and crashing on it would make the script
# unusable against the one store that has one.
_OVER_LONG_TAG = "leading tag names too long to print"


class UnsafeLabelError(RuntimeError):
    """A label that is not provably free of prompt text tried to reach stdout."""


def _safe_label(label: str) -> str:
    """One emitted label, or a raise.

    The guard the module docstring promises. Anything that is not a markup tag
    name, a literal `records.py` already carries, or a structural label from the
    fixed set above could be operator text, and this script never prints that.
    """
    if (
        _TAG_NAME_RE.match(label)
        or label in _STRUCTURAL_LABELS
        or label in records._INJECTED_PROMPTS  # noqa: SLF001 - the vocabulary is the subject
        or label in records._INJECTED_PROMPT_PREFIXES  # noqa: SLF001 - same
    ):
        return label
    raise UnsafeLabelError(label)


def _emit(label: str, count: int, *, indent: int = 2) -> None:
    print(f"{' ' * indent}{_safe_label(label):<52} {count}")


def _records(path: Path) -> list[dict[str, Any]]:
    """Every JSON object in one JSONL file, malformed lines dropped."""
    out: list[dict[str, Any]] = []
    try:
        raw = path.read_bytes()
    except OSError:
        return out
    for line in raw.split(b"\n"):
        if not line.startswith(b"{"):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def _leading_tag(text: str) -> str | None:
    """The tag name `injected_prompt` would read off this text, or None.

    The same two steps that function takes, in the same order: image wrappers off
    the front first, then the leading-tag match on what is left.
    """
    body = records.strip_prompt_wrappers(text)
    if not body:
        return None
    match = records._PROMPT_LEADING_TAG_RE.match(body)  # noqa: SLF001 - the regex is the subject
    if match is None:
        return None
    name = match.group(1).casefold()
    return name if _TAG_NAME_RE.match(name) else _OVER_LONG_TAG


class TagTally:
    """Leading, containment and refusal counts for one harness's tag vocabulary.

    Three counters and not one, because the shipped comment carried a single
    number that was silently a containment count: a tag that never *leads* can
    never make `injected_prompt` fire, so a containment count reads as evidence
    for a rule it cannot support.
    """

    def __init__(self) -> None:
        self.leading: Counter[str] = Counter()
        self.contained: Counter[str] = Counter()
        self.refused: Counter[str] = Counter()

    def add(self, text: str, vocabulary: frozenset[str], *, refused: bool) -> None:
        tag = _leading_tag(text)
        if tag is not None:
            self.leading[tag] += 1
            if refused:
                self.refused[tag] += 1
        lowered = text.casefold()
        for name in vocabulary:
            if f"<{name}" in lowered:
                self.contained[name] += 1

    def report(self, vocabulary: frozenset[str], *, title: str) -> None:
        print(f"\n{title}")
        for name in sorted(vocabulary, key=lambda n: (-self.leading[n], n)):
            leading = self.leading[name]
            contained = self.contained[name]
            refused = self.refused[name]
            suffix = f"  (contained {contained}, refused {refused})"
            print(f"  {_safe_label(name):<52} {leading}{suffix}")
        unlisted = [
            (name, count)
            for name, count in self.leading.most_common()
            if name not in vocabulary and count > 1
        ]
        if unlisted:
            print("  -- leading tags NOT in the vocabulary (count > 1) --")
            for name, count in unlisted:
                _emit(name, count)


def _claude_refuses(record: dict[str, Any], content: Any) -> bool:
    """Whether `records._turn_signal` would drop this Claude user record.

    Reimplemented rather than called, because `_turn_signal` returns a signal and
    this needs the reason. Kept in step with it by
    `scripts/tests/test_derive_prompt_shapes.py`, which asserts the two agree.
    """
    if record.get("isMeta"):
        return True
    if isinstance(content, list) and any(
        isinstance(item, dict) and item.get("type") == "tool_result" for item in content
    ):
        return True
    return isinstance(content, str) and content.lstrip().startswith(
        ("<local-command-stdout>", "<local-command-caveat>")
    )


class ProseTally:
    """The prefix, whole-body and image-marker counts, for one harness.

    Shared by both halves because the three vocabularies are shared: splitting
    them per harness is exactly the thing the comment block in `records.py` says
    was considered and rejected, so the instrument must count them the same way
    on both sides or the comparison is meaningless.

    ``flagged`` is whatever narrower population that half wants counted beside
    the whole-body hits — sidechain records on Claude, subagent rollouts on
    Codex — because "97, and all 97 are subagent-only" is the claim, not "97".
    """

    def __init__(self) -> None:
        self.prefixes: Counter[str] = Counter()
        self.whole: Counter[str] = Counter()
        self.images: Counter[str] = Counter()
        self.empty: Counter[str] = Counter()
        self.flagged = 0

    def add(self, text: str, *, flagged: bool) -> None:
        body = records.strip_prompt_wrappers(text)
        for prefix in records._INJECTED_PROMPT_PREFIXES:  # noqa: SLF001 - the vocabulary is the subject
            if body.startswith(prefix):
                self.prefixes[prefix] += 1
        if body in records._INJECTED_PROMPTS:  # noqa: SLF001 - same
            self.whole[body] += 1
            self.flagged += int(flagged)
        for name, pattern in _IMAGE_SHAPES:
            if pattern.match(text):
                self.images[name] += 1
                self.empty[name] += int(not body)

    def report(self, half: str, flag_label: str) -> None:
        print("\nleading image markers")
        for name, _ in _IMAGE_SHAPES:
            carries = self.images[name] - self.empty[name]
            print(
                f"  {_safe_label(name):<52} {self.images[name]}"
                f"  ({_safe_label('strips to empty')} {self.empty[name]},"
                f" {_safe_label('carries operator text')} {carries})"
            )
        print(f"\ninjected prose prefixes ({half})")
        for prefix in records._INJECTED_PROMPT_PREFIXES:  # noqa: SLF001 - the vocabulary is the subject
            _emit(prefix, self.prefixes[prefix])
        print(f"\nwhole-body injections ({half})")
        for value in sorted(records._INJECTED_PROMPTS):  # noqa: SLF001 - same
            _emit(value, self.whole[value])
        _emit(flag_label, self.flagged, indent=4)


def derive_claude(root: Path) -> None:
    """Counts for `_CLAUDE_USER_TAGS` and the Claude half of the prose lists."""
    files = sorted(root.glob(CLAUDE_GLOB))
    tags = TagTally()
    prose = ProseTally()
    texts = 0
    for path in files:
        for record in _records(path):
            if record.get("type") != "user":
                continue
            content = records.message_dict(record).get("content")
            text = records.extract_text(content)
            if not text:
                continue
            texts += 1
            tags.add(text, records._CLAUDE_USER_TAGS, refused=_claude_refuses(record, content))  # noqa: SLF001
            prose.add(text, flagged=bool(record.get("isSidechain")))

    print("\n=== Claude ===")
    _emit("files scanned", len(files))
    _emit("user-role texts", texts)
    tags.report(records._CLAUDE_USER_TAGS, title="_CLAUDE_USER_TAGS (leading occurrences)")  # noqa: SLF001
    prose.report("Claude half", "in sidechain records")


def _codex_texts(record: dict[str, Any]) -> tuple[str, str]:
    """``(population, text)`` for one Codex rollout record, or ``("", "")``.

    Three populations, because the vocabularies were derived from two of them and
    the third is what makes the occurrence counts double-count: a Codex build
    writes the operator's prompt as an `event_msg`/`user_message` AND again as a
    `response_item` message, so one prompt is two records.
    """
    payload = records.as_dict(record.get("payload"))
    outer = record.get("type")
    if outer == "event_msg" and payload.get("type") == "user_message":
        return ("event_msg user_message texts", records.extract_text(payload.get("message")))
    if outer == "response_item" and payload.get("type") == "message":
        role = payload.get("role")
        if role == "user":
            return ("response_item user texts", records.extract_text(payload.get("content")))
        if role == "developer":
            return ("developer-role texts", records.extract_text(payload.get("content")))
    return ("", "")


DEVELOPER_POPULATION = "developer-role texts"
EVENT_MSG_POPULATION = "event_msg user_message texts"
RESPONSE_POPULATION = "response_item user texts"


def _dual_written(event_msg_texts: list[str], response_texts: set[str]) -> int:
    """How many of one rollout's `event_msg` prompts are also `response_item`s.

    Matched on the first 400 characters, not on equality: `extract_text` joins a
    `response_item`'s content blocks and caps the join at 2,000 characters while
    an `event_msg`'s `message` is one uncapped string, so a long prompt's two
    spellings differ past that cap. Equality scores 850 of 1,007 across the local
    store where the head match scores 974.
    """
    heads = {text[:400] for text in response_texts}
    return sum(1 for text in event_msg_texts if text[:400] in heads)


def derive_codex(root: Path) -> None:
    """Counts for the two Codex tag sets and the Codex half of the prose list."""
    files = sorted(root.glob(CODEX_GLOB))
    tallies = {
        DEVELOPER_POPULATION: (TagTally(), records._CODEX_DEVELOPER_TAGS),  # noqa: SLF001
        EVENT_MSG_POPULATION: (TagTally(), records._CODEX_USER_TAGS),  # noqa: SLF001
    }
    # The two user populations share one tally: the vocabulary was derived from
    # their union, which is what makes its counts occurrences rather than prompts.
    tallies[RESPONSE_POPULATION] = tallies[EVENT_MSG_POPULATION]
    prose = ProseTally()
    counts: Counter[str] = Counter()
    dual = 0
    for path in files:
        event_msg_texts: list[str] = []
        response_texts: set[str] = set()
        subagent = False
        for record in _records(path):
            if record.get("type") == "session_meta":
                subagent = records.as_dict(record.get("payload")).get("thread_source") == "subagent"
            population, text = _codex_texts(record)
            if not population or not text:
                continue
            counts[population] += 1
            if population == EVENT_MSG_POPULATION:
                event_msg_texts.append(text)
            elif population == RESPONSE_POPULATION:
                response_texts.add(text)
            tally, vocabulary = tallies[population]
            tally.add(text, vocabulary, refused=False)
            prose.add(text, flagged=subagent)
        dual += _dual_written(event_msg_texts, response_texts)

    print("\n=== Codex ===")
    _emit("files scanned", len(files))
    for population in (EVENT_MSG_POPULATION, RESPONSE_POPULATION, DEVELOPER_POPULATION):
        _emit(population, counts[population])
    _emit("dual-written event_msg prompts", dual)
    tallies[EVENT_MSG_POPULATION][0].report(
        records._CODEX_USER_TAGS,  # noqa: SLF001
        title="_CODEX_USER_TAGS (leading occurrences)",
    )
    tallies[DEVELOPER_POPULATION][0].report(
        records._CODEX_DEVELOPER_TAGS,  # noqa: SLF001
        title="_CODEX_DEVELOPER_TAGS (leading occurrences)",
    )
    prose.report("Codex half", "in subagent rollouts")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--claude-root", type=Path, default=DEFAULT_CLAUDE_ROOT)
    parser.add_argument("--codex-root", type=Path, default=DEFAULT_CODEX_ROOT)
    parser.add_argument("--no-claude", action="store_true")
    parser.add_argument("--no-codex", action="store_true")
    args = parser.parse_args(argv)
    print("counts and shape names only — this script never prints prompt text")
    if not args.no_claude:
        if args.claude_root.is_dir():
            derive_claude(args.claude_root)
        else:
            print(f"\n=== Claude ===\n  no store at {args.claude_root}")
    if not args.no_codex:
        if args.codex_root.is_dir():
            derive_codex(args.codex_root)
        else:
            print(f"\n=== Codex ===\n  no store at {args.codex_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
