"""Who reads a session, and the words a reader sees before pressing.

One resolver for the page, the reading route and the stamp, so the provider a
reader was told about is the provider that runs. It is pure except for
`shutil.which`: it never starts a model, and it reads each provider's gate
before looking for its CLI, so a gated provider is never even looked up.

A route depends only on the session's harness and on this machine, never on
the session, which is why the reading route can resolve one from the payload's
harness without confirming that a session exists.
See [DEC-21](docs/design-reading-a-session.md#amended-2026-09-23-claude-code-is-built-and-gated).
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Any, TypedDict

from . import annotations as annotation_store
from . import observer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

CODEX = "codex"
CLAUDE = "claude"
PROVIDERS = (CODEX, CLAUDE)
LABELS = {CODEX: "Codex", CLAUDE: "Claude Code"}
VENDORS = {CODEX: "OpenAI", CLAUDE: "Anthropic"}
BINARIES = {CODEX: "codex", CLAUDE: "claude"}
MODELS = {CODEX: observer.OBSERVER_MODEL, CLAUDE: observer.CLAUDE_READING_MODEL}
# Which session harness is each provider's own. Every other harness has no
# producer of its own and prefers Codex, the producer that existed first.
OWN_HARNESS = {CODEX: "codex", CLAUDE: "claude"}

# Why this provider, or why none, as a closed token set. Four "none" tokens
# rather than one, because "not installed" and "not yet qualified" ask a
# reader to do different things and the ruling makes the second its own state.
REASON_OWN_HARNESS = "own-harness"
REASON_NO_OWN_PRODUCER = "no-own-producer"
REASON_FALLBACK_MISSING = "fallback-not-installed"
REASON_FALLBACK_UNQUALIFIED = "fallback-not-qualified"
REASON_NOT_INSTALLED = "not-installed"
REASON_MISSING_OTHER_UNQUALIFIED = "not-installed-other-not-qualified"
REASON_UNQUALIFIED_OTHER_MISSING = "not-qualified-other-not-installed"
REASON_UNQUALIFIED = "not-qualified"
REASONS = (
    REASON_OWN_HARNESS,
    REASON_NO_OWN_PRODUCER,
    REASON_FALLBACK_MISSING,
    REASON_FALLBACK_UNQUALIFIED,
    REASON_NOT_INSTALLED,
    REASON_MISSING_OTHER_UNQUALIFIED,
    REASON_UNQUALIFIED_OTHER_MISSING,
    REASON_UNQUALIFIED,
)
_NONE_REASONS = {
    ("missing", "missing"): REASON_NOT_INSTALLED,
    ("missing", "unqualified"): REASON_MISSING_OTHER_UNQUALIFIED,
    ("unqualified", "missing"): REASON_UNQUALIFIED_OTHER_MISSING,
    ("unqualified", "unqualified"): REASON_UNQUALIFIED,
}

_UNQUALIFIED = {
    CLAUDE: "Claude Code checks are built but not yet qualified",
    CODEX: "Codex checks are not qualified on this build",
}
_NO_PRODUCER = "This harness has no reading producer of its own"


class Route(TypedDict):
    harness: str
    provider: str
    label: str
    vendor: str
    model: str
    reason: str
    note: str
    disclosure: str
    fallback: bool


def _base_disclosure(provider: str) -> str:
    """What a reading sends and where, named for the provider that receives it.

    The Codex wording is the one DRC-4640 shipped with its provider spelt
    out. An earlier draft said "Nothing leaves it"; the harness's own sign-in
    reaches its vendor, so this is a path off the machine, and a consent
    string is the worst place for the reassuring half to be the false half.
    """
    label, vendor = LABELS[provider], VENDORS[provider]
    return (
        "A reading sends the goal you chose, and a bounded list of entries from the "
        f"observed record, to a {label} subprocess. {label} uses its own authentication to "
        f"reach {vendor}, so this is one of the paths that sends session content off this "
        f"machine and spends your {label} capacity. Your expected output is sent only on a "
        "harness that publishes work evidence, and on no other. The reading is a model's "
        "account of the evidence it was given, never a verification that the work was done."
    )


def _state(provider: str, which: Callable[[str], Any]) -> str:
    # The gate first: a provider this build may not offer is never looked up.
    if not annotation_store.provider_enabled(provider):
        return "unqualified"
    binary = which(BINARIES[provider])
    return "usable" if binary and os.path.isabs(binary) else "missing"


def _clause(provider: str, state: str) -> str:
    if state == "unqualified":
        return _UNQUALIFIED[provider]
    return f"the {LABELS[provider]} CLI was not found on this machine"


def _sentence(parts: list[str], tail: str) -> str:
    text = ", and ".join(parts) + tail
    return text[:1].upper() + text[1:]


def _route(harness: str, provider: str, reason: str, note: str, *, fallback: bool) -> Route:
    return {
        "harness": harness,
        "provider": provider,
        "label": LABELS.get(provider, ""),
        "vendor": VENDORS.get(provider, ""),
        "model": MODELS.get(provider, ""),
        "reason": reason,
        "note": note,
        "disclosure": f"{note} {_base_disclosure(provider)}" if provider else "",
        "fallback": fallback,
    }


def resolve(harness: str, *, binary_resolver: Callable[[str], Any] | None = None) -> Route:
    """The one provider that reads a session on this harness, or why none can.

    Own harness first; else the other provider, said before the press; else
    nothing. Never a third choice, and never a second provider after a launch
    failed: the route is decided once, here, before anything is spent.
    """
    which = binary_resolver or shutil.which
    preferred = CLAUDE if harness == OWN_HARNESS[CLAUDE] else CODEX
    other = CODEX if preferred == CLAUDE else CLAUDE
    own = harness == OWN_HARNESS[preferred]
    lead = [] if own else [_NO_PRODUCER]
    first = _state(preferred, which)
    if first == "usable":
        label = LABELS[preferred]
        if own:
            return _route(
                harness,
                preferred,
                REASON_OWN_HARNESS,
                f"{label} reads this {label} session.",
                fallback=False,
            )
        return _route(
            harness,
            preferred,
            REASON_NO_OWN_PRODUCER,
            f"{_NO_PRODUCER}, so {label} reads this session.",
            fallback=False,
        )
    second = _state(other, which)
    if second == "usable":
        return _route(
            harness,
            other,
            REASON_FALLBACK_MISSING if first == "missing" else REASON_FALLBACK_UNQUALIFIED,
            _sentence(
                [*lead, _clause(preferred, first)], f", so {LABELS[other]} reads this session."
            ),
            fallback=True,
        )
    return _route(
        harness,
        "",
        _NONE_REASONS[(first, second)],
        _sentence(
            [*lead, _clause(preferred, first), _clause(other, second)],
            ", so no check can run for this session.",
        ),
        fallback=False,
    )


def resolve_all(
    harnesses: Iterable[str], *, binary_resolver: Callable[[str], Any] | None = None
) -> dict[str, Route]:
    """One route per harness, looking each CLI up at most once per call."""
    which = binary_resolver or shutil.which
    memo: dict[str, Any] = {}

    def cached(name: str) -> Any:
        if name not in memo:
            memo[name] = which(name)
        return memo[name]

    return {harness: resolve(harness, binary_resolver=cached) for harness in sorted(set(harnesses))}
