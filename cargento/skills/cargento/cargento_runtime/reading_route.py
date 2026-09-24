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

import json
import os
import platform
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict
from urllib.parse import urlsplit

from . import annotations as annotation_store
from . import observer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

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
    # Where tool output would reach as configured on this machine, or "" where
    # the build cannot name it, and the sentence saying so. Both are empty
    # destinations-wise on a harness whose record lists no checks.
    destination: str
    tool_output: str


# The harness whose observed record lists checks (`project_context.
# claude_tool_reports`). A route for any other harness has no tool output to
# send, so it names none.
TOOL_OUTPUT_HARNESSES = ("claude",)
# How much of a check's output a reading carries: the ledger cap the record
# already reads it under, item 5 of the ruling `reading.build_ledger` cites.
TOOL_OUTPUT_TAIL_CHARS = 180

# Where each CLI reads settings that still apply under the flags a reading
# passes (`--restricted` for Claude Code, `--ignore-user-config` for Codex).
# Measured in the live binaries on 2026-09-24, Claude Code 2.1.281 and
# codex-cli 0.156.1, rather than recalled: the Windows path is under Program
# Files, not ProgramData. Windows policy lives in the registry as well, which
# this build does not read, so no destination is named on Windows at all.
CLAUDE_MANAGED_DIRS = {
    "Darwin": "/Library/Application Support/ClaudeCode",
    "Linux": "/etc/claude-code",
}
CLAUDE_MANAGED_PREFERENCES = "com.anthropic.claudecode.plist"
CODEX_MANAGED_FILES = ("/etc/codex/managed_config.toml", "/etc/codex/config.toml")
CODEX_MANAGED_PREFERENCES = "com.openai.codex.plist"
MANAGED_PREFERENCES_DIR = "/Library/Managed Preferences"
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})
_CLAUDE_CLOUDS = {
    "CLAUDE_CODE_USE_BEDROCK": "Amazon Bedrock",
    "CLAUDE_CODE_USE_VERTEX": "Google Vertex AI",
}


class _UnnamedError(Exception):
    """A setting exists that this build cannot read or does not recognise."""


def _under(root: Path, path: str) -> Path:
    return root / path.lstrip("/")


def _present(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise _UnnamedError from exc
    return True


def _env_block(path: Path) -> dict[str, str]:
    """A settings file's `env` block, {} when absent, refused when unreadable."""
    if not _present(path):
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        raise _UnnamedError from exc
    if not isinstance(data, dict):
        raise _UnnamedError
    env = data.get("env", {})
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in env.items()
    ):
        raise _UnnamedError
    return env


def _account(environ: Mapping[str, str]) -> tuple[str, str]:
    """(home, user) as the CLI finds them: the environment, else the password file.

    Node's `os.homedir()` and `os.userInfo()` fall back to the password entry,
    so a daemon started without `HOME` or `USER` still has a remote settings
    file and a per-user profile the CLI reads (review, 2026-09-24).
    """
    home, user = environ.get("HOME", ""), environ.get("USER", "")
    if home and user:
        return home, user
    try:
        import pwd  # noqa: PLC0415 - absent on Windows, which names nothing anyway

        entry = pwd.getpwuid(os.getuid())
    except (ImportError, KeyError, OSError):
        return home, user
    return home or entry.pw_dir, user or entry.pw_name


def _claude_sources(environ: Mapping[str, str], root: Path, system: str) -> list[Mapping[str, str]]:
    managed = CLAUDE_MANAGED_DIRS.get(system)
    if managed is None or environ.get("CLAUDE_CODE_MANAGED_SETTINGS_PATH"):
        raise _UnnamedError
    base = _under(root, managed)
    sources: list[Mapping[str, str]] = [environ, _env_block(base / "managed-settings.json")]
    drop_ins = base / "managed-settings.d"
    if _present(drop_ins):
        try:
            names = sorted(
                name
                for name in os.listdir(drop_ins)
                if name.endswith(".json") and not name.startswith(".")
            )
        except OSError as exc:
            raise _UnnamedError from exc
        sources.extend(_env_block(drop_ins / name) for name in names)
    home, user = _account(environ)
    if not home or not user:
        # Where the CLI would look cannot be known, so what it reads cannot be.
        raise _UnnamedError
    if system == "Darwin" and any(
        _present(_under(root, f"{MANAGED_PREFERENCES_DIR}/{prefix}{CLAUDE_MANAGED_PREFERENCES}"))
        for prefix in ("", f"{user}/")
    ):
        raise _UnnamedError
    config_dir = environ.get("CLAUDE_CONFIG_DIR") or f"{home}/.claude"
    sources.append(_env_block(_under(root, config_dir) / "remote-settings.json"))
    return sources


# Two settings measured in the 2.1.281 binary that move the API host without a
# base URL: an approved custom OAuth host replaces the first-party base
# (FedStart), and a unix socket sends every API request to a local socket whose
# far end forwards under another machine's configuration (review, 2026-09-24).
_OAUTH_HOST = "CLAUDE_CODE_CUSTOM_OAUTH_URL"
_MOVES_HOST = (_OAUTH_HOST, "ANTHROPIC_UNIX_SOCKET")


def _endpoint_env(sources: list[Mapping[str, str]]) -> dict[str, str]:
    """The endpoint variables across every source; two that disagree name nothing."""
    merged: dict[str, str] = {}
    for source in sources:
        for key, value in source.items():
            if not key.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_", _OAUTH_HOST)):
                continue
            if key in merged and merged[key] != value:
                raise _UnnamedError
            merged[key] = value
    return merged


def _clouds(merged: Mapping[str, str]) -> list[str]:
    """The provider switches turned on; a value that is neither on nor off names nothing."""
    clouds = []
    for key, value in merged.items():
        if not key.startswith("CLAUDE_CODE_USE_"):
            continue
        flag = value.strip().lower()
        if flag not in _TRUE | _FALSE:
            raise _UnnamedError
        if flag in _TRUE:
            clouds.append(key)
    if len(clouds) > 1 or any(cloud not in _CLAUDE_CLOUDS for cloud in clouds):
        raise _UnnamedError
    return clouds


def _claude_destination(sources: list[Mapping[str, str]]) -> str:
    merged = _endpoint_env(sources)
    if any(merged.get(key, "").strip() for key in _MOVES_HOST):
        raise _UnnamedError
    clouds = _clouds(merged)
    base_urls = [
        key for key, value in merged.items() if key.endswith("_BASE_URL") and value.strip()
    ]
    if clouds:
        if base_urls:
            raise _UnnamedError
        return _CLAUDE_CLOUDS[clouds[0]]
    if not base_urls:
        return VENDORS[CLAUDE]
    if base_urls != ["ANTHROPIC_BASE_URL"]:
        raise _UnnamedError
    return _host(merged["ANTHROPIC_BASE_URL"])


def _host(url: str) -> str:
    """Scheme-checked host and port only: never the path, query or userinfo."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise _UnnamedError from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise _UnnamedError
    return f"{parts.hostname}:{port}" if port else parts.hostname


def _codex_destination(environ: Mapping[str, str], root: Path, system: str) -> str:
    if system not in {"Darwin", "Linux"}:
        raise _UnnamedError
    # Whether Codex honours either variable under `--ignore-user-config` is not
    # measured, so their presence is a destination this build cannot name.
    if any(environ.get(key, "").strip() for key in ("OPENAI_BASE_URL", "OPENAI_API_BASE")):
        raise _UnnamedError
    paths = list(CODEX_MANAGED_FILES)
    if system == "Darwin":
        _home, user = _account(environ)
        if not user:
            raise _UnnamedError
        paths.append(f"{MANAGED_PREFERENCES_DIR}/{CODEX_MANAGED_PREFERENCES}")
        paths.append(f"{MANAGED_PREFERENCES_DIR}/{user}/{CODEX_MANAGED_PREFERENCES}")
    # Present at all is enough: these can move the endpoint and the build does
    # not parse them.
    if any(_present(_under(root, path)) for path in paths):
        raise _UnnamedError
    return VENDORS[CODEX]


def destination(
    provider: str,
    *,
    environ: Mapping[str, str] | None = None,
    root: Path | None = None,
    system: str | None = None,
) -> str:
    """Where this provider's reading call reaches as configured, or "".

    "" means the build cannot positively name it, and then tool output is not
    sent, item 7 of
    [DEC-23](docs/design-reading-a-session.md#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work).
    A proxy variable is ignored on purpose: it carries
    the call, and the vendor answering it is unchanged (owner, 2026-09-24).
    `root` and `system` exist for tests; production reads `/` on this OS.
    """
    env = os.environ if environ is None else environ
    base = Path("/") if root is None else root
    name = platform.system() if system is None else system
    try:
        if provider == CLAUDE:
            return _claude_destination(_claude_sources(env, base, name))
        if provider == CODEX:
            return _codex_destination(env, base, name)
    except _UnnamedError:
        return ""
    return ""


def _tool_output_sentence(provider: str, harness: str, where: str) -> str:
    if not provider or harness not in TOOL_OUTPUT_HARNESSES:
        return ""
    label = LABELS[provider]
    if not where:
        return (
            f"Tool output is not sent: Cargento cannot name where {label} would send it on this "
            "machine, so a reading reads your words and the rest of the record without the checks."
        )
    return (
        "For this session a reading can also send tool output: each check's command, the result "
        f"the tool reported and the last {TOOL_OUTPUT_TAIL_CHARS} characters of what it printed, "
        "with the paths of the files it wrote relative to its folder, "
        f"to {label}, which reaches {where}, and only after you allow tool output. That output "
        "is sent as the runner printed it, with credential shapes redacted."
    )


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
        f"machine and spends your {label} capacity. Your expected outcome lines are sent only "
        "when an entry sent is work evidence, and on no other reading. The reading is a model's "
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


def _route(
    harness: str,
    provider: str,
    reason: str,
    note: str,
    *,
    fallback: bool,
    where: Callable[[str], str],
) -> Route:
    reached = where(provider) if provider and harness in TOOL_OUTPUT_HARNESSES else ""
    sentence = _tool_output_sentence(provider, harness, reached)
    disclosure = f"{note} {_base_disclosure(provider)}" if provider else ""
    return {
        "harness": harness,
        "provider": provider,
        "label": LABELS.get(provider, ""),
        "vendor": VENDORS.get(provider, ""),
        "model": MODELS.get(provider, ""),
        "reason": reason,
        "note": note,
        "disclosure": f"{disclosure} {sentence}" if disclosure and sentence else disclosure,
        "fallback": fallback,
        "destination": reached,
        "tool_output": sentence,
    }


def resolve(
    harness: str,
    *,
    binary_resolver: Callable[[str], Any] | None = None,
    environ: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> Route:
    """The one provider that reads a session on this harness, or why none can.

    Own harness first; else the other provider, said before the press; else
    nothing. Never a third choice, and never a second provider after a launch
    failed: the route is decided once, here, before anything is spent.
    """
    which = binary_resolver or shutil.which

    def where(provider: str) -> str:
        return destination(provider, environ=environ, root=root)

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
                where=where,
            )
        return _route(
            harness,
            preferred,
            REASON_NO_OWN_PRODUCER,
            f"{_NO_PRODUCER}, so {label} reads this session.",
            fallback=False,
            where=where,
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
            where=where,
        )
    # The harness's own lack stands as a sentence of its own, so the two
    # machine facts after it join with one "and" rather than a chain of them.
    lack = "".join(f"{clause}. " for clause in lead)
    return _route(
        harness,
        "",
        _NONE_REASONS[(first, second)],
        lack
        + _sentence(
            [_clause(preferred, first), _clause(other, second)],
            ", so no check can run for this session.",
        ),
        fallback=False,
        where=where,
    )


def resolve_all(
    harnesses: Iterable[str],
    *,
    binary_resolver: Callable[[str], Any] | None = None,
    environ: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, Route]:
    """One route per harness, looking each CLI up at most once per call."""
    which = binary_resolver or shutil.which
    memo: dict[str, Any] = {}

    def cached(name: str) -> Any:
        if name not in memo:
            memo[name] = which(name)
        return memo[name]

    return {
        harness: resolve(harness, binary_resolver=cached, environ=environ, root=root)
        for harness in sorted(set(harnesses))
    }
