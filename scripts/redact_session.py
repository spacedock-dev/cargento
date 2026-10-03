#!/usr/bin/env python3
"""Redact a Claude Code session log, and its subagents, into a replayable local fixture.

The generic rules live here: secrets, emails, identifiers, private addresses, time zones, paths
outside the repository, other sessions' prompt listings and other people's chat messages. The
names, handles, organisations and places that identify real people live in a local JSON config
(default `~/.cargento/redaction.json`), because a public repository cannot list them. The config
shape is in [tests/README.md](tests/README.md#redaction).

The output is meant to be replayed by `scripts/drift_replay.py`, so the redaction keeps what the
drift detectors read: every line still parses, keys and tool-use ids are unchanged, a path outside
the repository stays absolute and keeps one numbered tag per distinct path, and a runner's own name
(`python3`, `node`, `pytest`) survives so a check is still a check. Measured on four sessions,
2026-10-03: with those three rules the redacted and original logs give the same live level and the
same listed checks at all 31 pushback cuts.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

CONFIG = os.path.expanduser("~/.cargento/redaction.json")

SECRET = re.compile(
    r"(AKIA|ASIA)[A-Z0-9]{16}"
    r"|(?<![A-Za-z0-9])sk-(?:ant-)?(?=[A-Za-z0-9_-]*[A-Z0-9])[A-Za-z0-9_-]{20,}"
    r"|phc_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[bpasr]-[A-Za-z0-9-]{10,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+|eyJhbGciOi[A-Za-z0-9_.%-]+"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----"
    r"|lin_(?:api|oauth)_[A-Za-z0-9]{20,}|ntn_[A-Za-z0-9]{20,}|secret_[A-Za-z0-9]{30,}"
    r"|AIza[0-9A-Za-z_-]{35}",
    re.DOTALL,
)
QUERY_SECRET = re.compile(
    r"([?&](?i:x-goog-signature|x-goog-credential|x-amz-signature|x-amz-credential"
    r"|x-amz-security-token|signature|sig|sk|token|key|secret|access_token)=)"
    r"([A-Za-z0-9_.%/+-]{8,})"
)
# A documented placeholder, not a credential.
KEEP_SECRET = frozenset({"AKIAIOSFODNN7EXAMPLE"})
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9-]*(?:\.[A-Za-z0-9-]*)+")
KEEP_EMAIL = re.compile(
    r"noreply@anthropic\.com|@example\.|@users\.noreply\.github\.com$"
    r"|^[a-z0-9+]{0,4}@(?:unittest|contextlib|dataclass|staticmethod|classmethod|property"
    r"|functools|typing|pytest|mock|patch)\.|\.md$|\.py$|\.js$|\.json$|^git@github\.com"
)
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ID_CONTEXT = re.compile(
    r"((?:createdById|assigneeId|userId|creatorId|organizationId|ownerId|actorId|leadId|memberId)"
    r"\\?\"\s*:\s*\\?\")(" + _UUID + ")"
)
CHAT_ID = re.compile(r"\b(?:U[A-Z0-9]{8,10}|[CDG]0[A-Z0-9]{8,10}|T0[A-Z0-9]{7,10})\b")
PAGE_ID = re.compile(r"(notion\.(?:so|com)/[^\s\"\\)]*?)([0-9a-f]{32})")
MORE_IDS = (
    re.compile(r"(uploads\.linear\.app/)([0-9a-f-]{36})"),
    re.compile(r"(claude\.ai/design/p/)([0-9a-f-]{36})"),
    re.compile(r"(projectId\\?\"?`?\s*[:=]?\s*\\?\"?`?)(" + _UUID + ")"),
    re.compile(r"(#(?:comment|project-update)-)([0-9a-f]{6,})"),
    re.compile(r"(Message TS: )(\d{9,}\.\d+)"),
    re.compile(r"(notion\.(?:so|com)/\S*?)(" + _UUID + ")"),
    re.compile(r"(slack\.com/archives/\S+?/p)(\d{16})"),
    re.compile(r"(linear\.app/[^/\s]+/project/[\w-]*?-)([0-9a-f]{12})\b"),
    re.compile(
        r"(\\?\"id\\?\"\s*:\s*\\?\")("
        + _UUID
        + r")(?=\\?\"[^{}]{0,60}\\?\"(?:name|displayName|email)"
        r"\\?\"\s*:\s*\\?\"(?:\[NAME_|\[PII|[A-Z][a-z]+ [A-Z]))"
    ),
)
# An identifier seen in one of these forms is redacted everywhere, bare or cut short, too.
LITERAL_SOURCES = (
    re.compile(r"claude\.ai/design/p/(" + _UUID + ")"),
    re.compile(r"projectId\\?\"?\s*[:=]\s*\\?\"?(" + _UUID + ")"),
)
TIME_ZONE = re.compile(
    r"\b(?:Asia|America|Europe|Australia|Pacific|Africa)/[A-Z][A-Za-z_]+\b"
    r"|\b(?:CST|CDT|EST|EDT|PST|PDT|MST|MDT|JST|KST|HKT|SGT|AEST|AEDT|CET|CEST|BST)\b"
)
PRIVATE_HOST = re.compile(
    r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"
)
# A runner's own name survives a hidden directory, so `/<hidden>/python3 -m unittest` stays a check.
RUNNER = re.compile(
    r"(?:python|pypy)(?:\d+(?:\.\d+)*)?|node|nodejs|npm|npx|pnpm|yarn|bun|deno|pytest|py\.test"
    r"|ruff|mypy|pyright|tox|nox|uv|uvx|pip\d?|go|cargo|rustc|java|mvn|gradle|make|bash|sh|zsh"
    r"|jest|vitest|tsc|eslint|ctest|swift|xcodebuild|ruby|rspec|php|phpunit|dotnet"
)
BASE64 = re.compile(r"[A-Za-z0-9+/=\s]+")
# Tool output that lists other sessions' prompts, which may be anyone's and about anything.
LISTINGS = (
    re.compile(r"(?m)^\s*#\d+ [0-9a-f]{8} \S+ \d+K"),
    re.compile(r"\('[0-9a-f]{8}', '"),
    re.compile(r"(?m)^\s*[0-9a-f]{8} \S+ \d+K\b"),
    re.compile(r"FIRST: '"),
    re.compile(r"\bacts=\d+ #\d+: '"),
)
LISTING_FLOOR = 3


class Config:
    """The local half: who and what to hide, and which path is this repository."""

    def __init__(self, body: Mapping[str, Any]) -> None:
        user = re.escape(str(body.get("home_user_prefix") or ""))
        keep = re.escape(str(body.get("repository_under_home") or ""))
        self.outside = (
            re.compile(rf"/Users/{user}[a-z]*/(?!{keep}\b)[^\s`'\")>,;]+", re.IGNORECASE)
            if user
            else None
        )
        self.rules: list[tuple[re.Pattern[str], str]] = []
        for group in ("names", "orgs"):
            for entry in body.get(group) or ():
                flags = 0 if entry.get("case_sensitive") else re.IGNORECASE
                self.rules.append((re.compile(str(entry["pattern"]), flags), f"[{entry['tag']}]"))
        places = [str(p) for p in body.get("places") or ()]
        alternatives = "|".join(places)
        self.places = re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE) if places else None
        self.self_tag = str(body.get("self_tag") or "NAME_1")


class Redactor:
    """One session's redaction: numbered tags stay the same for the same value within it."""

    def __init__(self, config: Config, literals: Iterable[str] = ()) -> None:
        self.config = config
        self.literals = sorted({v for v in literals if v})
        self.maps: dict[str, dict[str, str]] = {}
        self.slack = re.compile(
            rf"(=== Message from (?!\[{re.escape(config.self_tag)}\])[^\n]*?===)"
            r"(.*?)(?=\n=== Message from |\Z)",
            re.DOTALL,
        )

    def tag(self, kind: str, value: str) -> str:
        seen = self.maps.setdefault(kind, {})
        if value not in seen:
            seen[value] = f"[{kind}_{len(seen) + 1}]"
        return seen[value]

    def _outside(self, match: re.Match[str]) -> str:
        path = match.group(0)
        head, _, base = path.rpartition("/")
        if RUNNER.fullmatch(base):
            return "/" + self.tag("EXTERNAL_PATH", head) + "/" + base
        return "/" + self.tag("EXTERNAL_PATH", path)

    def text(self, value: str) -> str:
        for literal in self.literals:
            if literal[:8] in value:
                value = re.sub(
                    re.escape(literal[:8]) + r"(?:-[0-9a-f]{1,12})*",
                    self.tag("ID_REDACTED", literal),
                    value,
                )
        if self.config.outside is not None:
            value = self.config.outside.sub(self._outside, value)
        value = SECRET.sub(
            lambda m: (
                m.group(0) if m.group(0) in KEEP_SECRET else self.tag("REDACTED_SECRET", m.group(0))
            ),
            value,
        )
        value = EMAIL.sub(
            lambda m: (
                m.group(0)
                if KEEP_EMAIL.search(m.group(0))
                else self.tag("PII_ANONYMIZED", m.group(0).lower())
            ),
            value,
        )
        value = QUERY_SECRET.sub(
            lambda m: m.group(1) + self.tag("REDACTED_SECRET", m.group(2)), value
        )
        value = ID_CONTEXT.sub(lambda m: m.group(1) + self.tag("ID_REDACTED", m.group(2)), value)
        value = CHAT_ID.sub(
            lambda m: (
                self.tag("ID_REDACTED", m.group(0)) if re.search(r"\d", m.group(0)) else m.group(0)
            ),
            value,
        )
        value = PAGE_ID.sub(lambda m: m.group(1) + self.tag("ID_REDACTED", m.group(2)), value)
        value = PRIVATE_HOST.sub(lambda m: self.tag("INTERNAL_HOST", m.group(0)), value)
        for rule in MORE_IDS:
            value = rule.sub(lambda m: m.group(1) + self.tag("ID_REDACTED", m.group(2)), value)
        value = TIME_ZONE.sub("[TZ_REDACTED]", value)
        if self.config.places is not None:
            value = self.config.places.sub("[LOCATION_REDACTED]", value)
        for rule, replacement in self.config.rules:
            value = rule.sub(replacement, value)
        return value

    def value(self, item: Any) -> Any:
        """One JSON value, redacted in place of its structure."""
        if isinstance(item, str):
            return self._string(item)
        if isinstance(item, list):
            return [self.value(v) for v in item]
        if isinstance(item, dict):
            return {self.text(k): self.value(v) for k, v in item.items()}
        return item

    def _string(self, item: str) -> str:
        if len(item) > 400 and BASE64.fullmatch(item):
            return item  # image data: a two-letter rule would corrupt it
        stripped = item.lstrip()
        if stripped[:1] in "{[" and len(stripped) > 2:
            try:
                inner = json.loads(item)
            except ValueError:
                inner = None
            if isinstance(inner, dict | list):
                return _reencode(stripped, inner, self.value(inner)) if inner else item
        if any(len(rule.findall(item)) >= LISTING_FLOOR for rule in LISTINGS):
            return "[CROSS_SESSION_LISTING_REMOVED]"
        return self.slack.sub(
            lambda m: m.group(1) + "\n[THIRD_PARTY_MESSAGE_REMOVED]", self.text(item)
        )

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.maps.items()}


def _reencode(original: str, inner: Any, redacted: Any) -> str:
    """Write a string that held JSON back in its own layout, and untouched when nothing changed.

    Rewrapping unchanged output changed the tails a check's result is read from.
    """
    if redacted == inner:
        return original
    if "\n" in original:
        second = original.split("\n", 2)[1]
        indent = len(second) - len(second.lstrip(" ")) or 2
        return json.dumps(redacted, ensure_ascii=False, indent=indent)
    compact = '", "' not in original and '": ' not in original
    return json.dumps(redacted, ensure_ascii=False, separators=(",", ":") if compact else None)


def literals(paths: Iterable[str]) -> set[str]:
    """Identifiers seen in a recognisable form anywhere in these logs."""
    found: set[str] = set()
    for path in paths:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            text = handle.read()
        for rule in LITERAL_SOURCES:
            found.update(rule.findall(text))
    return found


def _redact_file(redactor: Redactor, source: str, target: str) -> tuple[int, int]:
    lines = skipped = 0
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with (
        open(source, encoding="utf-8", errors="surrogateescape") as reader,
        open(target, "w", encoding="utf-8") as writer,
    ):
        for line in reader:
            lines += 1
            try:
                record = json.loads(line)
            except ValueError:
                skipped += 1
                continue
            writer.write(
                json.dumps(redactor.value(record), ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    stamp = os.path.getmtime(source)
    os.utime(target, (stamp, stamp))
    return lines, skipped


def redact_session(
    config: Config, transcript: str, out: str, shared: Iterable[str]
) -> dict[str, Any]:
    """`<out>/<sid>/<sid>.jsonl` and `<out>/<sid>/<sid>/subagents/**`, the layout a replay reads."""
    sid = os.path.basename(transcript).removesuffix(".jsonl")
    redactor = Redactor(config, shared)
    lines, skipped = _redact_file(redactor, transcript, os.path.join(out, sid, f"{sid}.jsonl"))
    children = os.path.join(os.path.dirname(transcript), sid, "subagents")
    written = 0
    for child in sorted(glob.glob(os.path.join(children, "**", "*.jsonl"), recursive=True)):
        relative = os.path.relpath(child, children)
        _redact_file(redactor, child, os.path.join(out, sid, sid, "subagents", relative))
        written += 1
    return {
        "sid": sid,
        "lines": lines,
        "skipped": skipped,
        "subagents": written,
        "tags": redactor.counts(),
    }


def main(argv: list[str] | None = None, say: Callable[[str], Any] = print) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcripts", nargs="+", help="session logs, <sid>.jsonl")
    parser.add_argument("--out", required=True, help="fixture root, e.g. tests/raw_sessions")
    parser.add_argument("--config", default=CONFIG)
    args = parser.parse_args(argv)
    try:
        with open(args.config, encoding="utf-8") as handle:
            config = Config(json.load(handle))
    except (OSError, ValueError) as error:
        say(f"No usable redaction config at {args.config}: {error}")
        return 1
    shared = literals(args.transcripts)
    for transcript in args.transcripts:
        result = redact_session(config, transcript, args.out, shared)
        say(
            f"{result['sid'][:8]}: {result['lines']} lines, {result['skipped']} unparsed, "
            f"{result['subagents']} subagent logs, tags {result['tags']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
