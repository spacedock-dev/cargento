#!/usr/bin/env python3
"""Cargento: live coding-agent session activity across harnesses.

Stdlib-only local server. Supported harnesses (each shown only if its local
data is discovered): Claude Code, Codex, Gemini CLI / Antigravity CLI,
GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, Factory Droid. Serves a
summary UI at http://localhost:<port>/ and JSON at /api/data.

Waiting-on-you detection (Claude only):
- transcript tail shows a pending AskUserQuestion (tool_use with no
  tool_result yet) -> NEEDS INPUT, popup fired
- POST /api/notify (wired to Claude Code Notification + SessionEnd hooks)
  -> popup for idle prompts, NEEDS INPUT for actionable prompts, and clear
  standing hook state when the session exits
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import glob
import hashlib
import http.client
import json
import math
import ntpath
import os
import posixpath
import re
import select
import socket
import stat as stat_module
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    import sqlite3
except ImportError as exc:  # pragma: no cover — depends on the interpreter build
    # ``sqlite3`` is an optional stdlib module: minimal and musl-based builds
    # (Alpine images, hand-rolled interpreters) ship without the extension. A
    # bare ``import`` here would take the whole dashboard down, including the
    # five harnesses that need no database at all.
    SQLITE_IMPORT_ERROR: str | None = str(exc)
else:
    SQLITE_IMPORT_ERROR = None

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

HOME = os.path.expanduser("~")
DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")

# Documented per-harness relocation variables. When one of these is set it is
# authoritative: only paths derived from it are searched, so a user who
# relocated a store never silently reads a stale default instead. Variables
# whose semantics are not documented upstream are deliberately absent rather
# than guessed at — a wrong override would break a working setup, while a
# missing one only costs an entry in --diagnose.
STORE_ENV_VARS = (
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "GEMINI_CLI_HOME",
    "COPILOT_HOME",
    "PI_CODING_AGENT_DIR",
    "PI_CODING_AGENT_SESSION_DIR",
)

# Wall-clock start of the serving process, reported by /api/health so a caller
# can compute uptime without a second request. Set once by main().
SERVER_STARTED = 0.0


def resolve_store_roots(
    *,
    platform_name: str,
    environ: Mapping[str, str],
    home: str,
    pi_settings: Mapping[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Candidate locations for every harness store, best candidate first.

    Pure: everything it depends on is an argument, so each platform's layout is
    exercisable from any runner (and mypy sees every branch, rather than
    treating the other platforms' as unreachable).

    Candidates are cheap — one that does not exist simply never matches — so
    the lists include plausible-but-unconfirmed locations alongside documented
    ones. What must never happen is silently searching *only* a wrong path,
    which is why --diagnose reports every candidate it considered.
    """
    windows = platform_name == "win32"
    # Join with the *target* platform's rules, not the host's, so a Windows
    # layout resolved on a Linux runner is byte-identical to the real thing.
    join = ntpath.join if windows else posixpath.join
    is_absolute = ntpath.isabs if windows else posixpath.isabs

    def under_home(*parts: str) -> str:
        return join(home, *parts)

    def env_dir(name: str) -> str | None:
        value = environ.get(name)
        if not isinstance(value, str) or not value.strip():
            return None
        # Returned byte-for-byte, not stripped: trailing whitespace is legal in
        # a POSIX path, and XDG_DATA_HOME was already honoured before this
        # resolver existed. Stripping it would silently move an existing
        # OpenCode or Goose store out from under a macOS or Linux user.
        return value

    xdg_data = env_dir("XDG_DATA_HOME") or under_home(".local", "share")
    # Windows app-data roots; None elsewhere so those entries drop out.
    local_app_data = env_dir("LOCALAPPDATA") if windows else None
    roaming_app_data = env_dir("APPDATA") if windows else None

    claude_home = env_dir("CLAUDE_CONFIG_DIR") or under_home(".claude")
    codex_home = env_dir("CODEX_HOME") or under_home(".codex")
    # GEMINI_CLI_HOME names a parent: the CLI creates ".gemini" inside it.
    gemini_root = env_dir("GEMINI_CLI_HOME")
    gemini_home = join(gemini_root, ".gemini") if gemini_root else under_home(".gemini")
    copilot_home = env_dir("COPILOT_HOME") or under_home(".copilot")
    pi_config_dir = env_dir("PI_CODING_AGENT_DIR") or under_home(".pi", "agent")
    pi_session_dir = env_dir("PI_CODING_AGENT_SESSION_DIR")
    session_setting = pi_settings.get("sessionDir") if pi_settings is not None else None
    if pi_session_dir is None and isinstance(session_setting, str) and session_setting.strip():
        if session_setting == "~":
            pi_session_dir = home
        elif len(session_setting) > 1 and session_setting[0] == "~" and session_setting[1] in "/\\":
            pi_session_dir = join(home, session_setting[2:])
        elif is_absolute(session_setting):
            pi_session_dir = session_setting
        else:
            pi_session_dir = join(pi_config_dir, session_setting)
    pi_sessions = pi_session_dir or join(pi_config_dir, "sessions")
    antigravity_home = join(gemini_home, "antigravity-cli")

    def ordered(*candidates: str | None) -> list[str]:
        """Drop ``None`` and duplicates, keep order.

        Candidates coincide on some setups — XDG_DATA_HOME already pointing at
        ~/.local/share, a Windows profile without LOCALAPPDATA — and a repeated
        root would scan the same store twice. ``normcase`` folds case and
        separators on Windows, where paths are case-insensitive; on POSIX it is
        the identity.
        """
        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate is None:
                continue
            key = ntpath.normcase(candidate) if windows else candidate
            if key not in seen:
                seen.add(key)
                deduped.append(candidate)
        return deduped

    def app_data(root: str | None, *parts: str) -> str | None:
        return join(root, *parts) if root else None

    return {
        "claude.projects": ordered(join(claude_home, "projects")),
        "claude.tasks": ordered(join(claude_home, "tasks")),
        "codex.sessions": ordered(join(codex_home, "sessions")),
        "pi.sessions": ordered(pi_sessions),
        "gemini.tmp": ordered(join(gemini_home, "tmp")),
        "antigravity.root": ordered(antigravity_home),
        "copilot.root": ordered(copilot_home),
        # OpenCode: the XDG location is confirmed and must stay first — it is
        # what works on Linux and macOS today, and the first candidate becomes
        # the primary constant. Windows builds have been reported both under
        # %LOCALAPPDATA% and at a literal ~/.local/share; both follow.
        "opencode.data": ordered(
            join(xdg_data, "opencode"),
            app_data(local_app_data, "opencode", "data"),
            app_data(local_app_data, "opencode"),
            under_home(".local", "share", "opencode") if windows else None,
        ),
        "cursor.chats": ordered(under_home(".cursor", "chats")),
        # Goose: the Windows build uses an org-scoped app-data directory.
        "goose.db": ordered(
            join(xdg_data, "goose", "sessions", "sessions.db"),
            app_data(roaming_app_data, "Block", "goose", "data", "sessions", "sessions.db"),
            app_data(local_app_data, "Block", "goose", "data", "sessions", "sessions.db"),
        ),
        "droid.projects": ordered(under_home(".factory", "projects")),
    }


def load_pi_settings(config_dir: str) -> dict[str, Any]:
    try:
        with open(os.path.join(config_dir, "settings.json"), "rb") as source:
            value = json.loads(source.read(1_000_001))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


_pi_config_dir = os.environ.get("PI_CODING_AGENT_DIR")
if not isinstance(_pi_config_dir, str) or not _pi_config_dir.strip():
    _pi_config_dir = os.path.join(HOME, ".pi", "agent")

STORE_ROOTS: dict[str, list[str]] = resolve_store_roots(
    platform_name=sys.platform,
    environ=os.environ,
    home=HOME,
    pi_settings=load_pi_settings(_pi_config_dir),
)


def store_roots(key: str, primary: str) -> list[str]:
    """Every candidate root for ``key``, ``primary`` first.

    ``primary`` is the module constant below rather than a lookup, because that
    constant is the override seam: tests patch it to point a collector at a
    fixture. When it no longer matches the resolved default it is treated as an
    explicit instruction and searched *alone* — otherwise a fixture could pick
    up a real store elsewhere on the machine and a test would pass or fail on
    whatever the developer happened to have running.
    """
    candidates = STORE_ROOTS.get(key) or []
    if not candidates or primary != candidates[0]:
        return [primary]
    return candidates


def glob_stores(key: str, primary: str, *pattern: str) -> list[str]:
    """``glob_under`` across every candidate root for a store.

    Collectors already key sessions by id and keep the newest file per key, so
    scanning more than one root merges naturally instead of double-counting.
    """
    return [path for root in store_roots(key, primary) for path in glob_under(root, *pattern)]


def any_store_dir(key: str, primary: str, *parts: str) -> bool:
    """Whether any candidate root for a store contains ``parts`` as a directory."""
    return any(os.path.isdir(os.path.join(root, *parts)) for root in store_roots(key, primary))


def existing_stores(key: str, primary: str) -> list[str]:
    """Candidate paths for a store that actually exist as files."""
    return [path for path in store_roots(key, primary) if os.path.isfile(path)]


# Per-harness data roots. Each is the best candidate for its store and stays a
# module-level constant: it is the documented override seam (see store_roots).
TASKS_DIR = STORE_ROOTS["claude.tasks"][0]
PROJECTS_DIR = STORE_ROOTS["claude.projects"][0]
CODEX_SESSIONS_DIR = STORE_ROOTS["codex.sessions"][0]
PI_SESSIONS_DIR = STORE_ROOTS["pi.sessions"][0]
GEMINI_TMP = STORE_ROOTS["gemini.tmp"][0]
ANTIGRAVITY_CLI_DIR = STORE_ROOTS["antigravity.root"][0]
ANTIGRAVITY_CONVERSATIONS_DIR = os.path.join(ANTIGRAVITY_CLI_DIR, "conversations")
ANTIGRAVITY_LOG_DIR = os.path.join(ANTIGRAVITY_CLI_DIR, "log")
ANTIGRAVITY_LAST_CONVERSATIONS = os.path.join(
    ANTIGRAVITY_CLI_DIR, "cache", "last_conversations.json"
)
COPILOT_DIR = STORE_ROOTS["copilot.root"][0]
OPENCODE_DATA = STORE_ROOTS["opencode.data"][0]
CURSOR_CHATS = STORE_ROOTS["cursor.chats"][0]
GOOSE_DB = STORE_ROOTS["goose.db"][0]
FACTORY_PROJECTS = STORE_ROOTS["droid.projects"][0]

RATE_WINDOW_SEC = 600  # usage rate is measured over the last 10 minutes
WORKING_THRESHOLD_SEC = 90  # activity newer than this = WORKING
# A transcript that writes nothing for this long mid-turn was waiting on a
# human (permission prompt, open question) or asleep — not generating. The
# turn clock re-anchors after such a gap so "elapsed" measures work, not
# waiting. Kept well above the longest common tool run.
TURN_GAP_RESET_SEC = 300
TAIL_BYTES = 400_000  # only the transcript tail is parsed per refresh
POPUP_COOLDOWN_SEC = 60  # per-session floor between macOS popups
GLOBAL_POPUP_COOLDOWN_SEC = 15  # floor across caller-controlled session ids
POPUP_REPEAT_SUPPRESS_SEC = 600  # identical message per session: one popup per window
LONG_TURN_WARN_SEC = 900  # warn when a request runs (or is estimated) this long
# How far ahead of the collection clock a store timestamp may read before it is
# treated as skew rather than activity. Generous enough to absorb sampling noise
# and coarse filesystem write times; far below any real clock drift.
FUTURE_SKEW_TOLERANCE_SEC = 120
SQL_MSG_LIMIT = 400  # newest messages fetched per DB-backed session
MAX_CACHE_ENTRIES = 8192  # bound process-lifetime caches over long uptime
GEMINI_SEEN_ENTRIES = 2048  # bound per-transcript snapshot deduplication


def encoded_home_prefix(home: str) -> str:
    """Reproduce how Claude encodes ``home`` into a ``projects/`` directory name.

    Claude turns a working directory into a directory name by replacing path
    separators with ``-``; stripping that prefix is what leaves a readable
    project label. Replacing only ``/`` worked on POSIX and did nothing on a
    Windows home, so every Claude row there showed the whole encoded path
    instead of the project.

    Backslash and the drive colon are folded too. The exact Windows encoding is
    not documented, so this is deliberately non-destructive: if it turns out to
    differ, the prefix simply does not match and project_label() shows the full
    name — exactly what it does today.
    """
    return re.sub(r"[/\\:]", "-", home)


HOME_PREFIX = encoded_home_prefix(HOME)

# Tools that mean Claude is blocked on the human, not just running long.
INPUT_TOOLS = {"AskUserQuestion", "ExitPlanMode"}
# Claude Code's documented Notification matcher values. ``idle_timeout`` is
# accepted as a compatibility alias, while current payloads use
# ``idle_prompt``. Unknown structured values remain actionable so a newly
# introduced prompt type does not silently disappear.
IDLE_NOTIFICATION_TYPES = {"idle_prompt", "idle_timeout"}
INFORMATIONAL_NOTIFICATION_TYPES = {
    "agent_completed",
    "auth_success",
    "elicitation_complete",
    "elicitation_response",
}
ACTIONABLE_NOTIFICATION_TYPES = {
    "agent_needs_input",
    "elicitation_dialog",
    "permission_prompt",
}
CLEARING_NOTIFICATION_TYPES = IDLE_NOTIFICATION_TYPES | {
    "agent_completed",
    "elicitation_complete",
    "elicitation_response",
}

_lock = threading.Lock()
# session prefix -> {"ts": epoch, "message": str, "user_event"?: str | None}
_hook_notifs: dict[str, dict[str, Any]] = {}
_last_popup: dict[str, float] = {}  # session prefix -> epoch
_last_popup_message: dict[str, tuple[str, float]] = {}  # prefix -> (message, epoch)
_last_state: dict[str, str] = {}  # session prefix -> state string (popup on transition)
# Bumped only by SessionEnd — the one event meaning "this session is gone".
# Notification handling and collection both sample it before their slow
# transcript lookups and refuse to act if it moved, so a SessionEnd arriving
# mid-lookup is not undone by the notification it supersedes.
#
# Deliberately NOT bumped by clearing notifications (agent_completed,
# idle_prompt): those end one alert, not the session. Bumping there dropped an
# actionable permission prompt that happened to overlap a clearing one — losing
# a real "Claude is blocked" signal, which is worse than the stale state this
# guard exists to prevent.
#
# Bounded like the other caches. Evicting a session's entry degrades it to the
# pre-guard behaviour for that session — a stale row that clears on the next
# refresh — never to anything worse, so the bound is safe to keep.
_hook_generation: dict[str, int] = {}
_cache_lock = threading.Lock()


def bounded_put(cache: dict[Any, Any], key: Any, value: Any) -> None:
    """Set a bounded insertion-ordered cache entry.

    Callers must hold the lock that protects ``cache``.
    """
    if key not in cache and len(cache) >= MAX_CACHE_ENTRIES:
        cache.pop(next(iter(cache)))
    cache[key] = value


def notification_text(value: Any, limit: int) -> str:
    """Return argv-safe single-line notification text."""
    text = str(value or "").encode("utf-8", "replace").decode("utf-8")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return text[:limit]


def normalized_notification_type(value: Any) -> str:
    """Return a normalized structured notification type, if present."""
    return value.strip().lower() if isinstance(value, str) and value.strip() else ""


def notification_disposition(notification_type: Any, message: str) -> tuple[bool, bool]:
    """Return ``(needs_input, popup)`` for a Notification-hook payload.

    Structured Claude Code payloads are authoritative. Text matching remains
    only as a compatibility fallback for older hooks that omitted
    ``notification_type``.
    """
    kind = normalized_notification_type(notification_type)
    if kind in IDLE_NOTIFICATION_TYPES:
        return (False, True)
    if kind in INFORMATIONAL_NOTIFICATION_TYPES:
        return (False, False)
    if kind in ACTIONABLE_NOTIFICATION_TYPES:
        return (True, True)
    if kind:
        return (True, True)  # future/unknown structured prompt: fail visible
    idle_nudge = message.strip().lower().startswith("claude is waiting for your input")
    return (not idle_nudge, True)


def project_label(dirname: str, home_prefix: str | None = None) -> str:
    """Shorten an encoded project directory name to just the project part."""
    prefix = HOME_PREFIX if home_prefix is None else home_prefix
    dirname = dirname.removeprefix(prefix)
    return dirname.lstrip("-") or "(home)"


def project_from_cwd(cwd: str, home: str | None = None, windows: bool | None = None) -> str:
    """``<parent>/<basename>`` for a working directory, ``""`` when unusable.

    One directory has to read the same on every harness row, so this is the
    single rule they all share. Bare basename was the old per-collector rule
    and it collapses every checkout named ``subspace`` into one label; two
    segments keep sibling worktrees apart without pasting a whole path into
    the row.

    Separators are the host's, via ``ntpath``/``posixpath``, never a hand-rolled
    split on both. ``docs/design-cross-platform.md`` rejects that helper outright:
    ``\\`` is a legal POSIX filename character, so splitting on it turns one
    directory named ``my\\proj`` into two. Cargento only ever reads stores written
    on the machine it runs on, so the host's own rules are the correct ones.

    A path under ``home`` is labelled relative to it, because ``project_label``
    strips the home prefix and the two have to agree: ``~/foo`` reads ``foo``
    from either, never ``<username>/foo``.

    ``home`` and ``windows`` are injectable so one runner exercises both
    platforms (design decision D-4).

    Callers apply their own fallback to ``""`` — the harness name, or the
    encoded-directory label for the two collectors that have one.
    """
    path = ntpath if (os.name == "nt" if windows is None else windows) else posixpath
    if not cwd or not path.isabs(cwd):
        return ""  # a relative cwd names no project; fall through to the caller
    home_dir = HOME if home is None else home

    def trim(value: str) -> str:
        seps = path.sep + (path.altsep or "")
        return value.rstrip(seps) or value

    # normcase folds Windows case *and* separators, and preserves length, so
    # the comparison is spelling-independent and the slice below stays valid.
    cwd_cmp, home_cmp = path.normcase(trim(cwd)), path.normcase(trim(home_dir))
    if cwd_cmp == home_cmp:
        return "(home)"
    rest = trim(cwd)
    if home_cmp and cwd_cmp.startswith(home_cmp + path.sep):
        rest = rest[len(trim(home_dir)) :]
    else:
        rest = path.splitdrive(rest)[1]  # "C:" names no project
    if path.altsep:  # Windows accepts either spelling; POSIX has no altsep
        rest = rest.replace(path.altsep, path.sep)
    parts = [p for p in rest.split(path.sep) if p and p != "."]
    if any(p == ".." for p in parts):
        return ""  # an unresolved cwd would render as an absurd label
    return "/".join(parts[-2:])


def parse_ts(ts: Any) -> float | None:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return None


def parse_utc_sql(v: Any) -> float:
    """SQL TIMESTAMP text (e.g. goose datetime('now'): "YYYY-MM-DD HH:MM:SS",
    stored UTC without offset) -> epoch."""
    try:
        dt = datetime.fromisoformat(str(v).replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0


def norm_epoch(v: Any) -> float:
    """Numeric timestamp in unknown unit (s or ms) -> epoch seconds."""
    if not isinstance(v, (int, float)) or v <= 0:
        return 0
    return v / 1000 if v > 1e12 else v


def fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "–"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def read_tail(path: str) -> list[str]:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            truncated = False
            if size > TAIL_BYTES:
                # Only drop the first line when the seek actually lands
                # mid-record: if the byte before the window is a newline,
                # the window starts on a complete record.
                f.seek(size - TAIL_BYTES - 1)
                truncated = f.read(1) != b"\n"
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = data.split("\n")
    if truncated:
        lines = lines[1:]
    return lines


REVERSE_CHUNK_BYTES = 262_144  # bytes per read when walking a transcript backward


def reverse_lines(
    path: str,
    end_pos: int | None = None,
    *,
    max_bytes: int | None = None,
    contains: bytes | None = None,
) -> Iterator[bytes]:
    """Yield complete lines from ``path`` newest-first, reading fixed chunks.

    Deliberately not ``mmap``, which is faster but unsafe on a file a running
    agent owns. If the writer truncates or rotates a transcript while a region
    of it is mapped, POSIX delivers SIGBUS on the next access — uncatchable,
    it kills the process — and Windows instead refuses the writer's truncate,
    so the reader breaks the agent. A chunked read has neither failure mode:
    the worst case is a short read, which ends the scan.

    ``end_pos`` scans only what precedes that offset, exclusively — but a line
    that *ends* exactly at ``end_pos`` is still yielded. That boundary is not
    arbitrary: ``scan_turns`` resumes its forward pass at the same offset, and
    a forward read starting on a newline never sees the record that newline
    terminates. Dropping it here would lose that record entirely, which is what
    the previous mmap implementation did.

    ``max_bytes`` bounds how far back to walk. When the walk stops early the
    oldest line is dropped, since it is probably a fragment rather than a whole
    record.

    ``contains`` skips whole chunks that cannot hold a match, avoiding the
    per-line split for them. The line scan, not the I/O, is what costs: on a
    38 MB transcript whose only match is at the very start (the worst case)
    this takes the backward walk from 44 ms to 20 ms, against 16 ms for the
    mmap version it replaces. It is a coarse filter — callers must still test
    each line they receive.

    Empty lines are yielded as-is — callers already skip anything that is not a
    JSON object.
    """
    try:
        with open(path, "rb") as source:
            size = os.fstat(source.fileno()).st_size
            stop = size if end_pos is None else min(end_pos, size)
            floor = 0 if max_bytes is None else max(0, stop - max_bytes)
            pos = stop
            # Fragments of a line whose start lies further back, newest first.
            # Kept as a list and joined once: concatenating bytes per chunk made
            # a single very long record quadratic (a 64 MB one-line transcript
            # took 0.9 s), and large tool results do produce such records.
            carry: list[bytes] = []
            while pos > floor:
                read_size = min(REVERSE_CHUNK_BYTES, pos - floor)
                pos -= read_size
                source.seek(pos)
                chunk = source.read(read_size)
                if len(chunk) < read_size:
                    return  # truncated underneath us — stop rather than misparse
                last_newline = chunk.rfind(b"\n")
                if last_newline < 0:
                    carry.append(chunk)  # no line boundary in this window yet
                    continue
                carry.append(chunk[last_newline + 1 :])
                completed = b"".join(reversed(carry))
                # Everything before the final newline splits cleanly; its first
                # element is the next line's tail and becomes the new carry.
                parts = chunk[:last_newline].split(b"\n")
                carry = [parts[0]]
                if contains is None or contains in chunk or contains in completed:
                    yield completed
                    yield from reversed(parts[1:])
            # Emit the first line even when empty (a file starting with a
            # newline has one), but only if the walk actually reached the start
            # of the file — otherwise it is a fragment, not a record.
            if floor == 0 and stop > 0:
                yield b"".join(reversed(carry))
    except OSError:
        return


def extract_text(v: Any, depth: int = 0) -> str:
    """Best-effort text from harness message payloads whose exact shape
    varies (string, list of parts, nested dicts)."""
    if depth > 4 or v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        parts = (extract_text(x, depth + 1) for x in v)
        return " ".join(p for p in parts if p)[:2000]
    if isinstance(v, dict):
        for k in ("text", "content", "message", "prompt", "value"):
            if k in v:
                t = extract_text(v[k], depth + 1)
                if t:
                    return t
    return ""


def as_dict(value: Any) -> dict[str, Any]:
    """``value`` if it is a dict, else an empty dict.

    Every harness payload is untyped JSON read off disk, and the idiom
    ``record.get("x") or {}`` is not safe: any truthy non-dict (a string, a
    number, a list) passes the ``or`` and the following ``.get()`` raises,
    taking the whole collector down for that refresh. Same for iteration —
    see ``as_list``.
    """
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """``value`` if it is a list, else an empty list."""
    return value if isinstance(value, list) else []


def message_dict(record: Any) -> dict[str, Any]:
    """The ``message`` object of a transcript record, or an empty dict."""
    return as_dict(as_dict(record).get("message"))


def alnum(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def normalize_host(value: str) -> str:
    """Reduce a ``Host`` header to a bare, lowercased hostname.

    Naive ``rsplit(":", 1)`` mishandles two legitimate forms: a bracketed IPv6
    authority (``[::1]`` with no port becomes ``[:``) and any host whose case
    differs from the allowlist, even though DNS names are case-insensitive and
    ``LOCALHOST`` is as valid as ``localhost``. Both were rejected as non-local.
    """
    host = (value or "").strip()
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return ""
        # Only a port may follow the bracketed literal. Without this check
        # "[::1]evil.example" reduced to "::1" and passed as loopback.
        rest = host[end + 1 :]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return ""
        return host[1:end].lower()
    if host.count(":") > 1:
        return host.lower()  # bare IPv6 with no port
    if ":" not in host:
        return host.lower()
    name, _, port = host.rpartition(":")
    # Same rule as the bracketed branch: only a numeric port may follow, so
    # "localhost:evil.example" does not reduce to "localhost".
    return name.lower() if port.isdigit() else ""


def reuse_address_allowed(os_name: str) -> bool:
    """Whether the listening socket should set ``SO_REUSEADDR``.

    On POSIX the option only bypasses ``TIME_WAIT``, which is what lets the
    dashboard restart immediately after a kill — worth keeping. On Windows the
    same option means something else entirely: a second process may bind a port
    that is *already bound*, with undefined delivery between the two sockets. A
    stray second Cargento would silently steal half the requests, and any local
    process could hijack the port of a server handing out local session data.
    """
    return os_name != "nt"


def bind_error_message(exc: OSError, port: int) -> str:
    """Explain a failed bind instead of dumping a raw traceback."""
    winerror = getattr(exc, "winerror", None)
    if exc.errno == errno.EADDRINUSE or winerror == 10048:  # WSAEADDRINUSE
        return (
            f"Cargento: port {port} is already in use. If that is a dashboard "
            f"already running, use it: curl -s http://127.0.0.1:{port}/api/data. "
            f"Otherwise pick another port with --port."
        )
    if exc.errno == errno.EACCES or winerror == 10013:  # WSAEACCES
        # On Windows this is also what an in-use port reports once
        # SO_EXCLUSIVEADDRUSE is set, so name both causes.
        return (
            f"Cargento: not permitted to bind port {port} — it may already be "
            f"held by another process, reserved by the system, or blocked by "
            f"local policy. Try another port with --port."
        )
    return f"Cargento: cannot bind 127.0.0.1:{port} — {type(exc).__name__}: {exc}"


class LoopbackHTTPServer(ThreadingHTTPServer):
    """Loopback listener that refuses to share its port on Windows."""

    allow_reuse_address = reuse_address_allowed(os.name)

    def server_bind(self) -> None:
        # Windows-only socket option. Clearing SO_REUSEADDR above stops *us*
        # from hijacking someone else's port; this is what stops anyone else
        # hijacking ours. Absent on POSIX, where getattr returns None.
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            except OSError as exc:
                # Bind anyway, but say so: without this option the port can be
                # hijacked, and silently dropping the guarantee is worse than
                # a noisy one-line warning at startup.
                diag(f"Cargento: could not claim the port exclusively ({exc}); continuing")
        super().server_bind()


def dedupe_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse sessions found in more than one candidate store.

    Scanning every candidate root means a session left behind by a migration
    can be discovered twice. Most collectors key by session id internally and
    merge naturally, but the database-backed ones append per store — so the
    same id produced two rows and counted its tokens twice in the summary.
    The freshest copy wins.
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for session in sessions:
        key = (str(session["harness"]), str(session["sid"]))
        current = best.get(key)
        if current is None or session["last_activity"] > current["last_activity"]:
            best[key] = session
    return list(best.values())


DISPLAY_ID_LEN = 8  # floor; widened per harness only where 8 chars collide


def assign_display_ids(sessions: list[dict[str, Any]]) -> None:
    """Widen each session's display id until it is unique among the rows it
    could be confused with.

    Codex hands out UUIDv7, whose leading 48 bits are a millisecond timestamp.
    A fan-out launched in one directory therefore shares its leading hex, and
    an 8-char display id rendered several distinct sessions as the same
    harness, project and id — one session, apparently.

    The group is ``(harness, project)`` because that is exactly what a row
    prints beside the id, so those are the rows a reader has to tell apart.
    Widening per harness instead would drag every unrelated row in that harness
    out to the width one colliding fan-out needed: four agents started in the
    same millisecond need 16 to 18 characters, and a lone session in another
    worktree would inherit that for nothing.

    Mutates ``session["session"]`` only. ``sid`` is what every caller keys on
    and is left whole.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for session in sessions:
        groups.setdefault((str(session["harness"]), str(session["project"])), []).append(session)
    for group in groups.values():
        sids = [str(s["sid"]) for s in group]
        width = DISPLAY_ID_LEN
        longest = max((len(sid) for sid in sids), default=DISPLAY_ID_LEN)
        # Terminates: width strictly increases and is bounded by the longest
        # sid, where every prefix is the whole id. Comparing distinct prefixes
        # against distinct sids also means repeated sids cannot drive it.
        while width < longest and len({sid[:width] for sid in sids}) != len(set(sids)):
            width += 1
        for session in group:
            session["session"] = str(session["sid"])[:width]


_store_errors: dict[str, str] = {}


def record_store_error(path: str, exc: BaseException) -> None:
    """Remember why a store could not be read, for ``--diagnose``.

    Collectors swallow these so one broken store cannot take the dashboard
    down. Without recording them, a corrupt or locked database is reported as
    a healthy store holding no sessions — precisely the confusion --diagnose
    exists to remove.
    """
    with _cache_lock:
        bounded_put(_store_errors, path, f"{type(exc).__name__}: {exc}")


def sqlite_available() -> bool:
    """Whether the optional ``sqlite3`` extension module was importable."""
    return SQLITE_IMPORT_ERROR is None


def diag(message: str) -> None:
    """Write a diagnostic line without ever raising.

    Diagnostics carry harness-derived text (tool names, session titles, error
    strings) and the skill is normally started with stdout redirected to a log,
    where the stream uses the locale encoding rather than the console's Unicode
    path — so text outside that encoding raises UnicodeEncodeError. This is
    called from inside the collectors' own exception handler, where a second
    exception would escape it and take down the refresh it was reporting on.
    """
    try:
        print(message)
    except (OSError, ValueError):
        # Retry ASCII-safe; if even that fails (stdout closed or detached) a
        # diagnostic must still never be fatal.
        with contextlib.suppress(OSError, ValueError):
            print(message.encode("ascii", "backslashreplace").decode("ascii"))


def age(now: float, timestamp: float) -> float | None:
    """Seconds since ``timestamp``; ``None`` when the timestamp is implausible.

    A timestamp far in the future is not activity. It arrives from a store
    restored from backup, a file copied across the WSL boundary with its original
    mtime, or a guest whose clock drifted while the host was suspended. Read as
    an ordinary age, ``now - timestamp`` goes negative and satisfies *every*
    ``<= threshold`` comparison built on it — so the session reads Working, and
    keeps reading Working, for as long as the skew lasts. A clock a day ahead
    buys a day of phantom activity and phantom output tokens.

    Note that merely clamping the result at zero does not help: zero reads as
    "just now", which is still fresh. An implausible timestamp has to be
    rejected outright so no activity is invented from it. Overshoots within
    ``FUTURE_SKEW_TOLERANCE_SEC`` are clamped instead of rejected, because at
    that scale they are sampling noise — ``stat()`` and the collection clock are
    read microseconds apart, and coarse filesystems (FAT's two-second write
    time, some network mounts) round upward.
    """
    if timestamp - now > FUTURE_SKEW_TOLERANCE_SEC:
        return None
    return max(0.0, now - timestamp)


def is_fresh(now: float, timestamp: float, window_sec: float) -> bool:
    """Whether ``timestamp`` is a plausible time within ``window_sec`` of now."""
    seconds = age(now, timestamp)
    return seconds is not None and seconds <= window_sec


def newest_plausible(now: float, timestamps: Iterable[float]) -> float:
    """Newest timestamp that is not implausibly ahead of ``now``; 0 if none.

    Every activity decision goes through this rather than ``max()``. ``max()``
    picks the *implausible* value — a future timestamp is by definition the
    largest — so rejecting it afterwards throws away the good evidence too, and
    a transcript being written right now but holding one clock-skewed record
    reads Idle. That is the opposite of what rejecting future timestamps is
    for. It also matters for display (a skewed value renders as "–") and for
    de-duplication, where it would beat a perfectly good copy of the session.

    Callers then test the result with ``is_fresh()``: freshness is monotonic in
    the timestamp, so checking the newest plausible source is equivalent to
    checking them all, at half the work on every five-second refresh.
    """
    return max((t for t in timestamps if age(now, t) is not None), default=0.0)


def glob_under(root: str, *pattern: str) -> list[str]:
    """Glob ``pattern`` beneath a literal directory ``root``.

    ``root`` is a real path, not a pattern. Interpolating it into a glob makes
    any metacharacter in it (``[``, ``*``, ``?``) match nothing at all, so a
    home directory such as ``/Users/A [Contractor]`` silently hides every
    session — the failure is total and looks identical to "no sessions".

    Results are sorted because ``glob()`` order is unspecified: several callers
    keep the newest file per session, and an unsorted list makes an equal-mtime
    tie resolve differently from one platform (or one call) to the next.
    """
    return sorted(glob.glob(os.path.join(glob.escape(root), *pattern)))


def sqlite_ro_uri(path: str, *, immutable: bool = False, windows: bool | None = None) -> str:
    """Return a read-only SQLite URI for a filesystem path.

    Interpolating a path straight into ``file:{path}?mode=ro`` is wrong on every
    platform: SQLite percent-decodes the path portion, so a store path
    containing ``%`` becomes unopenable, and ``?``/``#`` terminate the path
    early. On Windows a ``C:\\dir`` path is not a valid URI path at all —
    SQLite documents that backslashes must become forward slashes and that a
    drive letter is only recognized in the form ``/X:/``.

    ``windows`` selects the path flavor and defaults to the running platform;
    tests pass it explicitly so both branches are exercised everywhere.
    """
    if windows is None:
        windows = os.name == "nt"
    absolute = (ntpath if windows else posixpath).abspath(path)
    if windows:
        absolute = absolute.replace("\\", "/")
        if not absolute.startswith("/"):
            absolute = "/" + absolute  # C:/dir -> /C:/dir, SQLite's drive form
    # "/" stays a separator and ":" must survive for the drive form; everything
    # else SQLite would reinterpret (%, ?, #) gets escaped.
    quoted = quote(absolute, safe="/:")
    if quoted.startswith("//") and not quoted.startswith("///"):
        # "//server/share" (UNC) or a POSIX "//dir" would parse as a URI
        # authority, which SQLite rejects unless it is empty or "localhost".
        # Two more slashes make the authority explicitly empty.
        quoted = "//" + quoted
    query = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    return f"file:{quoted}{query}"


# ---------------------------------------------------------------------------
# First-line metadata cache (JSONL harnesses write immutable line-1 metadata)

_meta_cache: dict[str, dict[str, Any]] = {}  # path -> parsed metadata dict


def first_line_meta(path: str, parse: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """parse(first-line JSON dict) -> dict; cached per path. Not cached on
    read/parse failure so a partially written first line retries later."""
    with _cache_lock:
        m = _meta_cache.get(path)
    if m is not None:
        return m
    try:
        with open(path, "rb") as f:
            d = json.loads(f.readline(200_000))
    except (OSError, ValueError):
        return {}
    m = parse(d if isinstance(d, dict) else {})
    with _cache_lock:
        cached = _meta_cache.get(path)
        if cached is not None:
            return cached
        bounded_put(_meta_cache, path, m)
        return m


def codex_meta(path: str) -> dict[str, Any]:
    """Codex rollout line 1 (session_meta): identity, cwd, and whether the
    file is a subagent thread (thread_source == "subagent")."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        # Every field is untyped JSON from disk — one malformed rollout must
        # not AttributeError the whole Codex collector.
        p = d.get("payload")
        if not isinstance(p, dict):
            p = {}
        spawn = as_dict(as_dict(as_dict(p.get("source")).get("subagent")).get("thread_spawn"))
        nickname = p.get("agent_nickname")
        agent_path = p.get("agent_path")
        label = (
            nickname
            if isinstance(nickname, str) and nickname
            # basename(), not rsplit("/"): on Windows the recorded path is
            # backslash-separated, and a hardcoded "/" would keep the whole
            # path as the agent's label.
            else (
                os.path.basename(agent_path) if isinstance(agent_path, str) and agent_path else None
            )
        )
        return {
            "session_id": p.get("session_id") or p.get("id"),
            "parent_session_id": (
                spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
            ),
            "cwd": p.get("cwd"),
            "subagent": p.get("thread_source") == "subagent",
            "agent_label": label or None,
        }

    return first_line_meta(path, parse)


def gemini_meta(path: str) -> dict[str, Any]:
    """Gemini chat recording line 1: sessionId, kind (main|subagent),
    directories (cwd list)."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        dirs = d.get("directories")
        return {
            "session_id": d.get("sessionId"),
            "kind": d.get("kind"),
            "cwd": dirs[0] if isinstance(dirs, list) and dirs else None,
        }

    return first_line_meta(path, parse)


def copilot_meta(path: str) -> dict[str, Any]:
    """Copilot events.jsonl line 1 is normally session.start with
    data.context.cwd."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        data = as_dict(d.get("data"))
        ctx = as_dict(data.get("context"))
        return (
            {"cwd": ctx.get("cwd") or data.get("cwd")} if d.get("type") == "session.start" else {}
        )

    return first_line_meta(path, parse)


def droid_meta(path: str) -> dict[str, Any]:
    """Droid transcript line 1 (session_start): id, session title, cwd."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        if d.get("type") != "session_start":
            return {}
        return {
            "session_id": d.get("id"),
            "title": d.get("sessionTitle") or d.get("title"),
            "cwd": d.get("cwd"),
        }

    return first_line_meta(path, parse)


def pi_meta(path: str) -> dict[str, Any]:
    """Pi v3's immutable session header: identity and workspace only."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        if d.get("type") != "session":
            return {}
        session_id = d.get("id")
        cwd = d.get("cwd")
        parent_session = d.get("parentSession")
        return {
            "session_id": session_id if isinstance(session_id, str) else None,
            "cwd": cwd if isinstance(cwd, str) else None,
            "parent_session": parent_session if isinstance(parent_session, str) else None,
        }

    return first_line_meta(path, parse)


# ---------------------------------------------------------------------------
# Transcript analyzers (tail pass -> title, prompt, usage, activity)


_claude_title_cache: dict[str, tuple[int, int, str | None]] = {}
_claude_user_event_cache: dict[str, tuple[int, int, str | None]] = {}

# Harness-injected wrappers around a user prompt. A slash command arrives as
# `<command-name>/plugin</command-name>` and a dispatched worker's instructions
# as `<teammate-message teammate_id="...">`, so the naive "first line of the
# first prompt" title renders raw markup. Measured over 248 real transcripts,
# 138 titles began with one of these.
_PROMPT_TAG_RE = re.compile(r"</?[a-z][a-z0-9-]*(?:\s[^>]*?)?/?>", re.IGNORECASE)
_COMMAND_NAME_RE = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.DOTALL)
_COMMAND_ARGS_RE = re.compile(r"<command-args>\s*(.*?)\s*</command-args>", re.DOTALL)
# A filesystem path, not a URL: `://` is excluded so a GitHub link survives
# whole, since the repo and PR number in it are the informative part. Absolute
# paths otherwise eat the entire title budget and say nothing a basename does
# not, and a dispatch prompt naming a UUID temp file is the worst of them.
_PROMPT_PATH_RE = re.compile(r"(?<!:)(?<![\w/])(?:~|/[^\s/]+)(?:/[^\s/]+)+/?")
# Only collapse a path long enough to be the problem this solves. Across the
# transcripts sampled the median slash-run is 11 characters and the 90th
# percentile is 140: the short ones are mostly not paths at all, and collapsing
# them corrupts real content. `^/api/v1/users$` became `^users$` before this.
SD_MIN_COLLAPSED_PATH = 25


def shorten_paths(text: str) -> str:
    """Collapse long absolute filesystem paths in a title to their last segment."""

    def basename(match: re.Match[str]) -> str:
        path = match.group(0)
        if len(path) < SD_MIN_COLLAPSED_PATH:
            return path
        return path.rstrip("/").rpartition("/")[2] or path

    return _PROMPT_PATH_RE.sub(basename, text)


def clip(text: str, limit: int) -> str:
    """Trim to ``limit`` on a word boundary where one is close enough.

    Cutting mid-word reads as damage rather than as truncation: "tell all
    subagents and tea" looks like a bug. Falling back to a hard cut keeps the
    bound absolute for a single long token such as a URL.
    """
    if len(text) <= limit:
        return text
    head = text[:limit].rstrip()
    space = head.rfind(" ")
    # Only honour a boundary in the last third, so one long token cannot
    # shrink the title to a couple of words.
    kept = head[:space] if space > limit * 2 // 3 else head
    # A hard cut can land on punctuation, and ".…" reads as a typo.
    kept = kept.rstrip(" .,;:-_/(")
    # It can also land inside a decomposed grapheme, leaving accent marks whose
    # base character was cut away to combine with the ellipsis instead.
    while kept and unicodedata.combining(kept[-1]):
        kept = kept[:-1]
    return kept + "…"


def prompt_title(text: str, limit: int = 80) -> str | None:
    """A readable one-line title from a raw user prompt, or None.

    Slash commands keep their name and any arguments, so `/plugin` reads as
    `/plugin` rather than as the markup it arrived in. Everything else has its
    wrapper tags removed and falls back to the first line with real content in
    it, which is what makes a `<teammate-message>` show the instruction instead
    of the envelope.
    """
    name = _COMMAND_NAME_RE.search(text)
    if name and name.group(1):
        args = _COMMAND_ARGS_RE.search(text)
        command = name.group(1).strip()
        argument = _PROMPT_TAG_RE.sub(" ", args.group(1)).strip() if args else ""
        joined = f"{command} {argument}".strip() if argument else command
        return clip(" ".join(shorten_paths(joined).split()), limit) or None
    for line in _PROMPT_TAG_RE.sub("", text).split("\n"):
        collapsed = " ".join(shorten_paths(line).split())
        if collapsed:
            return clip(collapsed, limit)
    return None


def claude_session_title(path: str) -> str | None:
    """Newest generated Claude title, falling back to the first user prompt.

    ``ai-title`` records can be older than the bounded activity tail, so walk
    the file backward to find the newest one. The cache is invalidated whenever
    the transcript's size or mtime changes because Claude repeats title records
    as a session grows.
    """
    try:
        stat = os.stat(path)
    except OSError:
        return None
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        cached = _claude_title_cache.get(path)
    if cached is not None and cached[:2] == cache_key:
        return cached[2]

    title = None
    # The chunk filter does the heavy lifting; the per-line test below only
    # re-checks the few lines inside a chunk that had a hit.
    for raw in reverse_lines(path, contains=b'"aiTitle"'):
        if b'"aiTitle"' not in raw:
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        value = record.get("aiTitle")
        if record.get("type") == "ai-title" and isinstance(value, str) and value:
            title = value
            break

    if title is None:
        try:
            with open(path, encoding="utf-8", errors="replace") as source:
                for line in source:
                    if not line.startswith("{"):
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    signal = _turn_signal(record, "claude")
                    if not signal or signal[0] != "prompt":
                        continue
                    prompt = extract_text(message_dict(record).get("content")).strip()
                    title = prompt_title(prompt)
                    break
        except OSError:
            pass

    with _cache_lock:
        bounded_put(_claude_title_cache, path, (*cache_key, title))
    return title


def claude_last_user_event(path: str) -> str | None:
    """Identity of the newest user record, independent of record timestamps."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        cached = _claude_user_event_cache.get(path)
    if cached is not None and cached[:2] == cache_key:
        return cached[2]

    marker = None
    # Superset filter: a user record must contain the literal "user".
    for raw in reverse_lines(path, contains=b'"user"'):
        if not raw.startswith(b"{") or b'"user"' not in raw:
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("type") != "user":
            continue
        uuid = record.get("uuid")
        marker = (
            uuid
            if isinstance(uuid, str) and uuid
            else hashlib.blake2b(raw, digest_size=16).hexdigest()
        )
        break

    with _cache_lock:
        bounded_put(_claude_user_event_cache, path, (*cache_key, marker))
    return marker


def analyze_transcript(path: str) -> dict[str, Any]:
    """Claude Code transcript tail."""
    info: dict[str, Any] = {
        "title": claude_session_title(path),
        "last_prompt": None,
        "usage_events": [],  # (epoch, output_tokens)
        "pending_input_tool": None,  # {"name", "ts"} awaiting the human
        "last_tool": None,
        "last_event_ts": 0,
        "last_user_event": claude_last_user_event(path),
    }
    pending: dict[Any, Any] = {}  # tool_use id -> {"name", "ts"} for INPUT_TOOLS only
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        ep = parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        if t == "last-prompt":
            info["last_prompt"] = d.get("lastPrompt")
        elif t == "assistant":
            msg = message_dict(d)
            usage = as_dict(msg.get("usage"))
            if ep and usage.get("output_tokens"):
                info["usage_events"].append((ep, usage["output_tokens"]))
            for c in as_list(msg.get("content")):
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    info["last_tool"] = c.get("name")
                    if c.get("name") in INPUT_TOOLS:
                        pending[c.get("id")] = {"name": c.get("name"), "ts": ep}
        elif t == "user":
            for c in as_list(message_dict(d).get("content")):
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    pending.pop(c.get("tool_use_id"), None)
    if pending:
        info["pending_input_tool"] = max(pending.values(), key=lambda p: p["ts"] or 0)
    return info


_CWD_SCAN_LINES = 50
_cwd_cache: dict[str, str] = {}


def claude_session_cwd(path: str) -> str:
    """Working directory recorded on the transcript head, ``""`` if absent.

    Claude is the one harness whose store does not hand a collector a cwd: the
    ``projects/`` directory name encodes the path with every separator replaced
    by ``-``, and that cannot be split back apart because a directory may
    legitimately contain ``-``. The records themselves carry the real path, so
    read it rather than guessing at the encoding.

    An absent cwd is not cached: a transcript head can be written before any
    record carries one, and the answer changes as soon as one does.
    """
    with _cache_lock:
        hit = _cwd_cache.get(path)
    if hit is not None:
        return hit
    cwd = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for _ in range(_CWD_SCAN_LINES):
                # Bounded like codex_meta's head read: one pasted prompt is
                # enough to make an unbounded readline pull megabytes into
                # memory before the substring test can reject the line.
                line = f.readline(200_000)
                if not line:
                    break
                if '"cwd"' not in line:
                    continue  # cheap reject before paying for a JSON parse
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                value = d.get("cwd") if isinstance(d, dict) else None
                if isinstance(value, str) and value:
                    cwd = value
                    break
    except OSError:
        return ""
    if cwd:
        with _cache_lock:
            bounded_put(_cwd_cache, path, cwd)
    return cwd


def claude_hook_user_event(path: str, prefix: str) -> tuple[bool, str | None]:
    """Return a safe transcript baseline for a Notification-hook payload."""
    try:
        real_path = os.path.realpath(path)
        projects_root = os.path.realpath(PROJECTS_DIR)
        inside_projects = os.path.commonpath((projects_root, real_path)) == projects_root
    except (OSError, ValueError):
        return (False, None)
    basename = os.path.basename(real_path)
    if not inside_projects or not basename.startswith(prefix) or not basename.endswith(".jsonl"):
        return (False, None)
    return (True, claude_last_user_event(real_path))


def analyze_codex_transcript(path: str) -> dict[str, Any]:
    """Codex rollout tail: user_message (prompt/title), token_count (usage),
    tool calls. Turn spans come from scan_turns; cwd/subagents from meta."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
    }
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        t = d.get("type")
        p = as_dict(d.get("payload"))
        if t == "event_msg":
            pt = p.get("type")
            if pt == "user_message":
                msg = p.get("message")
                msg = msg.strip() if isinstance(msg, str) else ""
                info["last_prompt"] = msg
                info["title"] = msg.split("\n")[0][:80] or None
            elif pt == "token_count":
                out = as_dict(as_dict(p.get("info")).get("last_token_usage")).get("output_tokens")
                if ep and out:
                    info["usage_events"].append((ep, out))
        elif t == "response_item" and p.get("type") in ("function_call", "custom_tool_call"):
            info["last_tool"] = p.get("name")
    return info


def record_fingerprint(record: Any) -> bytes:
    """Stable bounded-size identity for repeated transcript records."""
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8", "replace"
    )
    return hashlib.blake2b(raw, digest_size=16).digest()


def gemini_records(record: Any) -> tuple[Any, ...]:
    """Expand a Gemini control record into its contained messages."""
    snapshot = record.get("$set")
    messages = snapshot.get("messages") if isinstance(snapshot, dict) else None
    if isinstance(messages, list):
        return tuple(message for message in messages if isinstance(message, dict))
    return (record,)


def incremental_gemini_records(record: Any, state: dict[str, Any]) -> tuple[Any, ...]:
    """Return only messages added since the prior cumulative $set snapshot."""
    snapshot = record.get("$set")
    messages = snapshot.get("messages") if isinstance(snapshot, dict) else None
    if not isinstance(messages, list):
        return (record,)
    messages = tuple(message for message in messages if isinstance(message, dict))
    previous_count = state["gemini_snapshot_count"]
    start = 0
    if (
        previous_count
        and len(messages) >= previous_count
        and record_fingerprint(messages[previous_count - 1]) == state["gemini_snapshot_tail"]
    ):
        start = previous_count
    state["gemini_snapshot_count"] = len(messages)
    state["gemini_snapshot_tail"] = record_fingerprint(messages[-1]) if messages else None
    return messages[start:]


def analyze_gemini_transcript(path: str) -> dict[str, Any]:
    """Gemini chats/*.jsonl tail: type 'user' | 'gemini' records with
    per-message tokens; resumed-session $set snapshots are expanded."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
    }
    seen = set()
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        for message in gemini_records(d):
            fingerprint = record_fingerprint(message)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            ep = parse_ts(message.get("timestamp") or "")
            if ep:
                info["last_event_ts"] = max(info["last_event_ts"], ep)
            t = message.get("type")
            if t == "user":
                txt = extract_text(message.get("content")).strip()
                if txt:
                    info["last_prompt"] = txt
                    info["title"] = txt.split("\n")[0][:80]
            elif t == "gemini":
                toks = message.get("tokens") or {}
                if ep and isinstance(toks, dict) and toks.get("output"):
                    info["usage_events"].append((ep, toks["output"]))
                for tc in as_list(message.get("toolCalls")):
                    if isinstance(tc, dict) and tc.get("name"):
                        info["last_tool"] = tc.get("name")
    return info


def analyze_copilot_events(path: str) -> dict[str, Any]:
    """Copilot events.jsonl tail: typed events with data payloads. Field
    names inside data are de-facto (not a stable API) — extracted
    defensively."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
        "cwd": None,
        "pending_agents": {},  # started-but-not-completed subagents
    }
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        t = d.get("type")
        data = as_dict(d.get("data"))
        if t == "session.start":
            ctx = as_dict(data.get("context"))
            info["cwd"] = ctx.get("cwd") or data.get("cwd") or info["cwd"]
        elif t == "user.message":
            txt = extract_text(data).strip()
            if txt:
                info["last_prompt"] = txt
                info["title"] = txt.split("\n")[0][:80]
        elif t == "tool.execution_start":
            name = data.get("toolName") or data.get("name") or data.get("tool")
            if name:
                info["last_tool"] = str(name)
        elif t == "subagent.started":
            key = data.get("id") or data.get("subagentId") or d.get("id")
            label = (
                data.get("name")
                or data.get("agentName")
                or data.get("agent")
                or data.get("agentType")
                or "subagent"
            )
            info["pending_agents"][key] = str(label)[:70]
        elif t == "subagent.completed":
            key = data.get("id") or data.get("subagentId") or d.get("id")
            if key in info["pending_agents"]:
                info["pending_agents"].pop(key)
            elif info["pending_agents"]:  # unmatched key scheme: drop oldest
                info["pending_agents"].pop(next(iter(info["pending_agents"])))
    return info


def analyze_droid_transcript(path: str) -> dict[str, Any]:
    """Droid transcript tail: {type: "message", timestamp, message: {role,
    content: [Anthropic-style blocks]}}."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
    }
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        if d.get("type") != "message":
            continue
        msg = message_dict(d)
        content = msg.get("content")
        blocks = content if isinstance(content, list) else []
        if msg.get("role") == "user":
            if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in blocks):
                continue
            txt = extract_text(content).strip()
            if txt:
                info["last_prompt"] = txt
                info["title"] = txt.split("\n")[0][:80]
        elif msg.get("role") == "assistant":
            for c in blocks:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    info["last_tool"] = c.get("name")
    return info


# Pi stores an append-only tree rather than a linear transcript.  The session
# selector follows the path from the newest entry back to parentId: null, so
# retaining sibling branches would report tools and tokens the agent abandoned.
_PI_NO_NAME = object()
_pi_scan: dict[str, dict[str, Any]] = {}


def _pi_projection(record: Any) -> dict[str, Any] | None:
    """The bounded subset of a Pi JSONL entry needed by the dashboard."""
    if not isinstance(record, dict):
        return None
    kind = record.get("type")
    entry_id = record.get("id")
    parent_id = record.get("parentId")
    if not isinstance(entry_id, str) or not entry_id:
        entry_id = None
    if not isinstance(parent_id, str):
        parent_id = None
    message = message_dict(record)
    role = message.get("role")
    prompt = None
    tool = None
    usage_source: Any = record.get("usage")
    if kind == "message":
        usage_source = message.get("usage")
        if role == "user":
            text = extract_text(message.get("content")).strip()
            prompt = text or None
        if role == "assistant":
            for block in as_list(message.get("content")):
                if not isinstance(block, dict) or block.get("type") != "toolCall":
                    continue
                tool_name = block.get("name")
                if isinstance(tool_name, str) and tool_name:
                    tool = tool_name
    output = as_dict(usage_source).get("output")
    usage = output if isinstance(output, (int, float)) and not isinstance(output, bool) else None
    name: Any = _PI_NO_NAME
    if kind == "session_info":
        value = record.get("name")
        name = value if isinstance(value, str) and value else None
    return {
        "id": entry_id,
        "parent_id": parent_id,
        "timestamp": parse_ts(record.get("timestamp") or "") or 0,
        "prompt": prompt,
        "usage": usage,
        "tool": tool,
        "name": name,
        "kind": kind,
    }


def _pi_complete_end(path: str, size: int) -> int:
    """End offset after the newest complete JSONL entry, or zero."""
    if not size:
        return 0
    try:
        with open(path, "rb") as source:
            pos = size
            while pos:
                read_size = min(REVERSE_CHUNK_BYTES, pos)
                pos -= read_size
                source.seek(pos)
                chunk = source.read(read_size)
                if len(chunk) < read_size:
                    return 0
                newline = chunk.rfind(b"\n")
                if newline >= 0:
                    return pos + newline + 1
    except OSError:
        return 0
    return 0


def _pi_latest_name(path: str, end_pos: int) -> Any:
    """The newest global Pi session name, including an explicit clear."""
    for raw in reverse_lines(path, end_pos, contains=b'"session_info"'):
        if not raw.startswith(b"{") or b'"session_info"' not in raw:
            continue
        try:
            projection = _pi_projection(json.loads(raw))
        except ValueError:
            continue
        if projection is not None and projection["name"] is not _PI_NO_NAME:
            return projection["name"]
    return _PI_NO_NAME


def _pi_state(path_entries: list[dict[str, Any]], path: str, end_pos: int) -> dict[str, Any]:
    """Build cache state only for a branch whose ancestry reaches root."""
    return {
        "pos": end_pos,
        "path": path_entries,
        "ids": {entry["id"]: index for index, entry in enumerate(path_entries)},
        "name": _pi_latest_name(path, end_pos),
    }


def _pi_last_complete_branch(path: str, end_pos: int) -> list[dict[str, Any]]:
    """Find the newest root-connected path after the latest candidate breaks."""
    entries: dict[str, dict[str, Any]] = {}
    newest: list[dict[str, Any]] = []
    for raw in reverse_lines(path, end_pos):
        if not raw.startswith(b"{"):
            continue
        try:
            projection = _pi_projection(json.loads(raw))
        except ValueError:
            continue
        if projection is None or projection["kind"] == "session":
            continue
        entry_id = projection["id"]
        if entry_id is None or entry_id in entries:
            continue
        entries[entry_id] = projection
        newest.append(projection)
    for leaf in newest:
        reverse_path = []
        entry = leaf
        seen = set()
        while entry["id"] not in seen:
            reverse_path.append(entry)
            seen.add(entry["id"])
            parent_id = entry["parent_id"]
            if parent_id is None:
                return list(reversed(reverse_path))
            parent = entries.get(parent_id)
            if parent is None:
                break
            entry = parent
    return []


def _pi_rebuild(path: str, end_pos: int) -> dict[str, Any]:
    """Reconstruct the live Pi branch newest-first without retaining payloads."""
    reverse_path: list[dict[str, Any]] = []
    wanted: str | None = None
    for raw in reverse_lines(path, end_pos):
        if not raw.startswith(b"{"):
            continue
        try:
            projection = _pi_projection(json.loads(raw))
        except ValueError:
            continue
        if projection is None or projection["kind"] == "session":
            continue
        entry_id = projection["id"]
        if entry_id is None:
            continue
        if wanted is None or entry_id == wanted:
            reverse_path.append(projection)
            wanted = projection["parent_id"]
        else:
            continue
        if wanted is None:
            break
    if wanted is None and reverse_path:
        return _pi_state(list(reversed(reverse_path)), path, end_pos)
    return _pi_state(_pi_last_complete_branch(path, end_pos), path, end_pos)


def _pi_extend(state: dict[str, Any], entry: dict[str, Any]) -> bool:
    """Add one complete Pi entry; false asks the caller to rebuild from disk."""
    if entry["name"] is not _PI_NO_NAME:
        state["name"] = entry["name"]
    if entry["kind"] == "session" or entry["id"] is None:
        return True
    path_entries = state["path"]
    if not path_entries:
        if entry["parent_id"] is not None:
            return False
        state["path"] = [entry]
        state["ids"] = {entry["id"]: 0}
        return True
    parent_id = entry["parent_id"]
    ids = state["ids"]
    if parent_id == path_entries[-1]["id"]:
        path_entries.append(entry)
        ids[entry["id"]] = len(path_entries) - 1
        return True
    index = ids.get(parent_id)
    if index is None:
        return False
    state["path"] = [*path_entries[: index + 1], entry]
    state["ids"] = {item["id"]: i for i, item in enumerate(state["path"])}
    return True


def _pi_turn(path_entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn state for Pi's active branch, using scan_turns' quiet-gap rule."""
    turn_start = prev_ts = None
    durations: list[float] = []
    for entry in path_entries:
        timestamp = entry["timestamp"]
        if not timestamp:
            continue
        if turn_start and prev_ts and timestamp - prev_ts > TURN_GAP_RESET_SEC:
            if prev_ts > turn_start:
                durations.append(prev_ts - turn_start)
            turn_start = timestamp
        if entry["prompt"]:
            if turn_start and prev_ts and prev_ts > turn_start:
                durations.append(prev_ts - turn_start)
            turn_start = timestamp
        prev_ts = timestamp
    return {"turn_start": turn_start, "durations": durations[-50:]}


def _pi_info(state: dict[str, Any]) -> dict[str, Any] | None:
    """Dashboard analyzer output from the compact active-branch projection."""
    path_entries = state["path"]
    if not path_entries:
        return None
    prompts = [entry["prompt"] for entry in path_entries if entry["prompt"]]
    name = state["name"]
    title = (
        name if isinstance(name, str) and name else (prompt_title(prompts[0]) if prompts else None)
    )
    usage_events = [
        (entry["timestamp"], entry["usage"])
        for entry in path_entries
        if entry["timestamp"] and entry["usage"] is not None
    ]
    tools = [entry["tool"] for entry in path_entries if entry["tool"]]
    return {
        "title": title,
        "last_prompt": prompts[-1] if prompts else None,
        "usage_events": usage_events,
        "last_tool": tools[-1] if tools else None,
        "last_event_ts": max((entry["timestamp"] for entry in path_entries), default=0),
        "turn": _pi_turn(path_entries),
    }


def scan_pi_session(path: str) -> dict[str, Any] | None:
    """Scan Pi's live branch incrementally, retaining only compact entries."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    with _scan_lock:
        state = _pi_scan.get(path)
        if state is None or state["pos"] > size:
            if len(_pi_scan) >= MAX_CACHE_ENTRIES:
                _pi_scan.pop(next(iter(_pi_scan)))
            state = _pi_rebuild(path, _pi_complete_end(path, size))
            _pi_scan[path] = state
            return _pi_info(state)
        if size == state["pos"]:
            return _pi_info(state)
        try:
            with open(path, "rb") as source:
                source.seek(state["pos"])
                data = source.read()
        except OSError:
            return _pi_info(state)
        end = data.rfind(b"\n")
        if end < 0:
            return _pi_info(state)
        new_pos = state["pos"] + end + 1
        for raw in data[:end].split(b"\n"):
            if not raw.startswith(b"{"):
                continue
            try:
                projection = _pi_projection(json.loads(raw))
            except ValueError:
                continue
            if projection is not None and not _pi_extend(state, projection):
                state = _pi_rebuild(path, new_pos)
                _pi_scan[path] = state
                return _pi_info(state)
        state["pos"] = new_pos
        return _pi_info(state)


# ---------------------------------------------------------------------------
# Turn tracking


_turn_scan: dict[str, Any] = {}  # path -> incremental turn-tracking state
_scan_lock = threading.Lock()  # ThreadingHTTPServer: serialize scanner state
TURN_SCAN_MAX_BYTES = 8 * 1024 * 1024  # cap per-call read of a transcript delta


def _turn_signal(d: dict[str, Any], harness: str) -> tuple[str, Any] | None:
    """Classify a transcript record for turn tracking.

    Returns ("prompt"|"start"|"end", epoch_override|None) or None.
    "prompt" starts a turn and closes the previous one at the last event
    before it; "start"/"end" are explicit turn-span markers."""
    t = d.get("type")
    if harness == "codex":
        if t != "event_msg":
            return None
        p = as_dict(d.get("payload"))
        pt = p.get("type")
        if pt == "task_started":
            return ("start", p.get("started_at"))
        if pt in ("task_complete", "turn_aborted"):
            return ("end", None)
        return None
    if harness == "copilot":
        if t == "user.message":
            return ("prompt", None)
        if t in ("session.task_complete", "session.shutdown", "abort"):
            return ("end", None)
        return None
    if harness == "gemini":
        if t != "user":
            return None
        content = d.get("content")
        if isinstance(content, list) and any(
            isinstance(c, dict) and "functionResponse" in c for c in content
        ):
            return None  # tool response recorded as a user part, not a prompt
        return ("prompt", None)
    if harness == "droid":
        if t != "message":
            return None
        msg = message_dict(d)
        if msg.get("role") != "user":
            return None
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(c, dict) and c.get("type") == "tool_result" for c in content
        ):
            return None
        return ("prompt", None)
    # claude
    if t != "user" or d.get("isMeta"):
        return None
    content = message_dict(d).get("content")
    if isinstance(content, list) and any(
        isinstance(c, dict) and c.get("type") == "tool_result" for c in content
    ):
        return None
    # Local command output/caveat records are user-typed but are not prompts —
    # nothing generates in response to them, so they must not start a turn.
    if isinstance(content, str) and content.lstrip().startswith(
        ("<local-command-stdout>", "<local-command-caveat>")
    ):
        return None
    return ("prompt", None)


def _apply_turn_record(st: dict[str, Any], record: Any, harness: str) -> None:
    """Apply one chronological transcript record to incremental turn state."""
    ep = parse_ts(record.get("timestamp") or "")
    if not ep:
        return
    # A quiet stretch longer than TURN_GAP_RESET_SEC inside a turn means the
    # agent was not generating (permission wait, AskUserQuestion, sleep).
    # Bank the active segment and restart the clock at the post-gap event so
    # "elapsed" reflects work, not waiting.
    if st["turn_start"] and st["prev_ts"] and ep - st["prev_ts"] > TURN_GAP_RESET_SEC:
        if st["prev_ts"] > st["turn_start"]:
            st["durations"].append(st["prev_ts"] - st["turn_start"])
        st["turn_start"] = ep
        st["last_start"] = ep
    sig = _turn_signal(record, harness)
    if sig:
        kind, override = sig
        if kind == "end":
            if st["turn_start"] and ep > st["turn_start"]:
                st["durations"].append(ep - st["turn_start"])
            st["turn_start"] = None
        else:
            if (
                kind == "prompt"
                and st["turn_start"]
                and st["prev_ts"]
                and st["prev_ts"] > st["turn_start"]
            ):
                st["durations"].append(st["prev_ts"] - st["turn_start"])
            start = norm_epoch(override) or ep
            st["turn_start"] = start
            st["last_start"] = start
    st["prev_ts"] = ep


def _latest_turn_context(path: str, end_pos: int, harness: str) -> dict[str, Any]:
    """Find the nearest turn boundary before ``end_pos`` without loading the
    prefix into memory. Used when the file is larger than the forward-read
    budget so a long current turn is not lost."""
    context: dict[str, Any] = {"turn_start": None, "last_start": None, "prev_ts": None}
    if end_pos <= 0:
        return context
    active_decided = False
    later_ts: float | None = None
    for raw in reverse_lines(path, end_pos):
        if not raw.startswith(b"{"):
            continue
        try:
            decoded = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(decoded, dict):
            continue
        records = reversed(gemini_records(decoded)) if harness == "gemini" else (decoded,)
        for record in records:
            ep = parse_ts(record.get("timestamp") or "")
            if not ep:
                continue
            # Walking backward: `later_ts` is the timestamp of the record that
            # chronologically FOLLOWS this one. A quiet gap re-anchors the turn
            # at the post-gap record, same rule as the forward scanner.
            if later_ts is not None and later_ts - ep > TURN_GAP_RESET_SEC:
                if not active_decided:
                    context["turn_start"] = later_ts
                context["last_start"] = later_ts
                return context
            later_ts = ep
            if context["prev_ts"] is None:
                context["prev_ts"] = ep
            sig = _turn_signal(record, harness)
            if not sig:
                continue
            kind, override = sig
            if not active_decided:
                active_decided = True
                if kind != "end":
                    context["turn_start"] = norm_epoch(override) or ep
            if kind != "end":
                context["last_start"] = norm_epoch(override) or ep
                return context
    return context


def scan_turns(path: str, harness: str) -> dict[str, Any] | None:
    """Whole-file turn tracker for JSONL harnesses. The transcript tail can
    be shorter than the current turn (long turns bury the prompt >TAIL_BYTES
    back), so turns are tracked incrementally: each call parses only bytes
    appended since the last call and carries state in _turn_scan.

    Serialized via _scan_lock — concurrent /api/data requests would otherwise
    double-advance pos and double-count durations."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    with _scan_lock:
        st = _turn_scan.get(path)
        if st is None or st["pos"] > size:  # new, truncated, or rotated file
            if len(_turn_scan) >= MAX_CACHE_ENTRIES:
                _turn_scan.pop(next(iter(_turn_scan)))
            st = {
                "pos": 0,
                "turn_start": None,
                "last_start": None,
                "durations": [],
                "prev_ts": None,
                "gemini_seen": {},
                "gemini_snapshot_count": 0,
                "gemini_snapshot_tail": None,
            }
            _turn_scan[path] = st
        if size == st["pos"]:
            return st
        if size - st["pos"] > TURN_SCAN_MAX_BYTES:
            # Locate the active turn boundary in the skipped prefix with a
            # reverse mmap scan, then process the bounded tail forward.
            tail_start = size - TURN_SCAN_MAX_BYTES
            st.update(_latest_turn_context(path, tail_start, harness))
            st["pos"] = tail_start
        with open(path, "rb") as f:
            f.seek(st["pos"])
            data = f.read()
        end = data.rfind(b"\n")
        if end < 0:
            return st  # incomplete line, wait for more bytes
        st["pos"] += end + 1
        for raw in data[:end].split(b"\n"):
            if not raw.startswith(b"{"):
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            records = incremental_gemini_records(d, st) if harness == "gemini" else (d,)
            for record in records:
                if harness == "gemini":
                    fingerprint = record_fingerprint(record)
                    if fingerprint in st["gemini_seen"]:
                        continue
                    if len(st["gemini_seen"]) >= GEMINI_SEEN_ENTRIES:
                        st["gemini_seen"].pop(next(iter(st["gemini_seen"])))
                    st["gemini_seen"][fingerprint] = None
                _apply_turn_record(st, record, harness)
        st["durations"] = st["durations"][-50:]
        return st


def turns_from_events(events: list[tuple[float, bool]]) -> dict[str, Any]:
    """Turn state from chronologically sorted (epoch, is_user_prompt) pairs —
    used by DB-backed harnesses where messages come from SQL, not a file."""
    turn_start = prev = None
    durations = []
    for ep, is_user in events:
        if not ep:
            continue
        if is_user:
            if turn_start and prev and prev > turn_start:
                durations.append(prev - turn_start)
            turn_start = ep
        prev = ep
    return {"turn_start": turn_start, "durations": durations[-50:]}


def turn_progress(scan: dict[str, Any] | None, state: str, now: float) -> dict[str, Any] | None:
    """Naive current-turn ETA: estimated total = median of this session's
    past turns that lasted at least as long as the current one has so far."""
    if state != "working" or not scan or not scan.get("turn_start"):
        return None
    elapsed = age(now, scan["turn_start"])
    if elapsed is None:
        return None  # turn start is implausibly ahead of the clock; no ETA
    history = scan.get("durations") or []
    cands = sorted(d for d in history if d >= elapsed)
    if cands:
        est_total = cands[len(cands) // 2]
        return {
            "elapsed_h": fmt_duration(elapsed),
            "eta_h": fmt_duration(est_total - elapsed),
            "pct": min(99, round(elapsed * 100 / est_total)) if est_total else 99,
            "long": max(est_total, elapsed) >= LONG_TURN_WARN_SEC,
        }
    return {
        "elapsed_h": fmt_duration(elapsed),
        "eta_h": None,  # running longer than any recent turn
        "pct": 99 if history else None,
        "long": elapsed >= LONG_TURN_WARN_SEC,
    }


# ---------------------------------------------------------------------------
# Claude task files + subagents


def load_tasks() -> dict[str, list[dict[str, Any]]]:
    """session prefix -> list of task dicts."""
    by_session: dict[str, list[dict[str, Any]]] = {}
    for fp in glob_stores("claude.tasks", TASKS_DIR, "*", "*.json"):
        if os.path.basename(fp).startswith("."):
            continue
        try:
            # Explicit UTF-8: the locale default is cp1252 on Windows, which
            # silently mojibakes non-ASCII task subjects and raises
            # UnicodeDecodeError on the bytes that code page leaves undefined.
            # That is a ValueError but not a JSONDecodeError, so it escaped the
            # handler below and errored the whole Claude collector for a pass.
            with open(fp, encoding="utf-8") as f:
                task = json.load(f)
            st = os.stat(fp)
        except (OSError, ValueError):
            continue
        if not isinstance(task, dict):
            continue
        dirname = os.path.basename(os.path.dirname(fp))
        dirname = dirname.removeprefix("session-")
        prefix = dirname[:8]
        if not prefix:
            continue
        created = getattr(st, "st_birthtime", st.st_mtime)
        # Field types are unvalidated JSON from disk — coerce non-strings so
        # one malformed record cannot TypeError the whole Claude collector.
        subject = task.get("subject")
        active_form = task.get("activeForm")
        status = task.get("status")
        by_session.setdefault(prefix, []).append(
            {
                "id": task.get("id"),
                "subject": subject if isinstance(subject, str) and subject else "(untitled)",
                "activeForm": active_form if isinstance(active_form, str) else "",
                "status": status if isinstance(status, str) and status else "pending",
                "created": created,
                "updated": st.st_mtime,
            }
        )
    return by_session


# Subagent transcripts sit beneath the session directory in two layouts. A
# plain Task subagent lands directly in subagents/; a workflow fan-out nests
# one level deeper, under the run that owns it. Missing the second layout hid
# every workflow agent, which is how a session driving ten of them read Idle.
CLAUDE_SUBAGENT_GLOBS = (
    ("subagents", "agent-*.jsonl"),
    ("subagents", "workflows", "*", "agent-*.jsonl"),
)


def claude_agent_transcripts(transcript: str | None) -> list[tuple[str, float]]:
    """(path, mtime) for every subagent transcript belonging to a session."""
    if not transcript:
        return []
    sess_dir = os.path.join(
        os.path.dirname(transcript), os.path.basename(transcript)[: -len(".jsonl")]
    )
    found: list[tuple[str, float]] = []
    for pattern in CLAUDE_SUBAGENT_GLOBS:
        for fp in glob_under(sess_dir, *pattern):
            try:
                found.append((fp, os.path.getmtime(fp)))
            except OSError:
                continue  # transcript rotated/deleted between glob and stat
    return found


def load_claude_subagents(transcript: str | None, now: float) -> list[dict[str, Any]]:
    """Running Claude subagents beneath the session directory; fresh mtime =
    running. Covers both layouts in ``CLAUDE_SUBAGENT_GLOBS``."""
    agents: list[dict[str, Any]] = []
    for fp, mtime in claude_agent_transcripts(transcript):
        if not is_fresh(now, mtime, WORKING_THRESHOLD_SEC):
            continue
        label = None
        try:
            with open(fp[: -len(".jsonl")] + ".meta.json", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):  # ValueError covers UnicodeDecodeError
            meta = None
        # Meta values are untyped JSON — a non-string name must not
        # TypeError the whole Claude collector.
        if isinstance(meta, dict):
            for key in ("name", "description", "agentType"):
                value = meta.get(key)
                if isinstance(value, str) and value:
                    label = value
                    break
        agents.append({"label": (label or "subagent")[:70], "mtime": mtime})
    agents.sort(key=lambda a: -a["mtime"])
    return agents


# ---------------------------------------------------------------------------
# Notifications


def native_notifier(platform_name: str) -> str:
    """Name of the OS-level notification backend for a platform, "" if none.

    Pure in ``platform_name`` so both branches run on every CI runner and mypy
    checks them all, rather than treating the non-host branch as unreachable
    (design decision D-4 in docs/design-cross-platform.md).

    The page reads this through ``/api/data`` to decide whether to raise its
    own browser notification. Exactly one layer notifies for a given
    transition: the server when it has a backend here, the browser when it does
    not. Linux and Windows have no backend yet (tracked in
    docs/plans/native-notifications.md) — so today the
    browser covers them and macOS behavior is unchanged.
    """
    return "osascript" if platform_name == "darwin" else ""


def notify_mac(title: Any, message: Any) -> None:
    if not native_notifier(sys.platform):
        return

    def esc(s: str) -> str:
        return str(s).replace("\\", "\\\\").replace('"', '\\"')

    safe_message = notification_text(message, 180)
    safe_title = notification_text(title, 60)
    script = f'display notification "{esc(safe_message)}" with title "{esc(safe_title)}" sound name "Glass"'
    try:
        result = subprocess.run(  # noqa: S603 — fixed binary, esc()-sanitized args
            ["/usr/bin/osascript", "-e", script],
            timeout=5,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            diag(f"[notify] osascript failed: {detail[:300]}")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        diag(f"[notify] osascript failed: {type(exc).__name__}: {exc}")


def hook_generation(prefix: str) -> int:
    """Current generation for a session's hook state (see ``_hook_generation``)."""
    with _lock:
        return _hook_generation.get(prefix, 0)


def current_hook(
    prefix: str, last_user_event: str | None, last_event_ts: float
) -> dict[str, Any] | None:
    """Return an uncleared hook notification for a session.

    Hooks with a user-event marker clear when the newest user record changes
    (clock-independent). Hooks without one (payloads lacking transcript_path:
    the documented curl simulation, older Claude Code versions) fall back to
    the parsed-timestamp rule so they cannot stick forever.
    """
    with _lock:
        hook = _hook_notifs.get(prefix)
        if not hook:
            return None
        if "user_event" in hook:
            if last_user_event != hook["user_event"]:
                _hook_notifs.pop(prefix, None)
                return None
        elif last_event_ts > hook["ts"]:
            _hook_notifs.pop(prefix, None)
            return None
        return hook


def maybe_popup(
    prefix: str, state: str, detail: str | None, *, expect_generation: int | None = None
) -> None:
    """Popup when a session transitions into a needs-input state.

    ``expect_generation`` is re-checked under the same lock that guards
    ``_last_state``. Checking it in the caller leaves a window in which a
    SessionEnd commits first, and this would then re-create the state it just
    cleared and fire a popup for a session that has already exited.
    """
    now = time.time()
    with _lock:
        if expect_generation is not None and _hook_generation.get(prefix, 0) != expect_generation:
            return
        prev = _last_state.get(prefix)
        bounded_put(_last_state, prefix, state)
        if state != "needs_input" or prev == "needs_input":
            return
        if now - _last_popup.get(prefix, 0) < POPUP_COOLDOWN_SEC:
            return
        if now - _last_popup.get("_global", 0) < GLOBAL_POPUP_COOLDOWN_SEC:
            return
        bounded_put(_last_popup, prefix, now)
        bounded_put(_last_popup, "_global", now)
    notify_mac("Claude is waiting on you", detail or f"Session {prefix} needs your input")


# ---------------------------------------------------------------------------
# Session assembly helpers


def base_session(harness: str, sid: Any, project: str) -> dict[str, Any]:
    # "session" is the display id and starts at the DISPLAY_ID_LEN floor;
    # assign_display_ids() widens it per harness where that floor collides.
    # "sid" keeps the full identity so the client can key per-session state
    # without truncation collisions (e.g. two Gemini "session-*" fallback ids
    # are one string apart at the floor). Claude passes its 8-char prefix, so
    # sid == session there — that whole collector is already keyed on the
    # prefix upstream, and widening is a no-op for it.
    return {
        "session": str(sid)[:8],
        "sid": str(sid),
        "harness": harness,
        "project": project,
        "title": None,
        "last_prompt": "",
        "state": "idle",
        "state_detail": "awaiting your message",
        "active": False,
        "last_activity": 0,
        "rate_per_min": 0,
        "total": 0,
        "done": 0,
        "open": 0,
        "progress_pct": 0,
        "eta_h": None,
        "turn": None,
        "subagents": [],
        "tasks": [],
        "spacedock": None,
    }


def rate_from(info: dict[str, Any] | None, now: float) -> int:
    if not info:
        return 0
    recent: float = sum(
        tok for ep, tok in info["usage_events"] if is_fresh(now, ep, RATE_WINDOW_SEC)
    )
    return round(recent / (RATE_WINDOW_SEC / 60))


def codex_subagent_rate(path: str, now: float) -> int:
    """Recent Codex subagent output after its own task_started boundary."""
    scan = scan_turns(path, "codex")
    start = scan.get("last_start") if scan else None
    if not start:
        return 0
    info = analyze_codex_transcript(path)
    recent: float = sum(
        tokens
        for epoch, tokens in info["usage_events"]
        if epoch >= start and is_fresh(now, epoch, RATE_WINDOW_SEC)
    )
    return round(recent / (RATE_WINDOW_SEC / 60))


def working_detail(info: dict[str, Any] | None, subagents: list[Any]) -> str:
    if subagents:
        n = len(subagents)
        return f"running {n} subagent{'s' if n > 1 else ''}"
    if info and info.get("last_tool"):
        return f"running {info['last_tool']}"
    return "generating…"


# ---------------------------------------------------------------------------
# Harness collectors — each returns a list of session dicts


# --- Spacedock workflow cartography ---------------------------------------
#
# Spacedock drives work items ("entities") through an ordered list of named
# stages, with a "first officer" session dispatching "ensign" workers. Four
# facts make it visible to a passive reader, in decreasing order of authority:
#
# 1. The launcher starts the session with `--agent spacedock:first-officer`, so
#    the transcript's first records carry an ``agentSetting``. That alone proves
#    the session is Spacedock, and costs nothing — it is in the head bytes the
#    subagent classifier already reads.
# 2. The first officer runs `spacedock status --boot` at startup and the JSON
#    envelope lands in the transcript as a tool result. It carries the ABSOLUTE
#    workflow directory and the ABSOLUTE entity-state directory, so nothing has
#    to be discovered by scanning.
# 3. The ordered stage list is the one fact that envelope's `dispatchable` view
#    omits, so it is read from the workflow README's frontmatter, along with
#    which stages are initial and which are terminal. See SECURITY.md for the
#    contract these reads operate under.
# 4. The entity-state directory holds one file per entity, whose frontmatter
#    carries the entity's current ``status`` — the stage it is actually parked
#    on right now.
#
# Fact 4 exists because the boot envelope's ``dispatchable`` list is a snapshot
# of what was dispatchable AT BOOT, not the entity roster. A long-running first
# officer that boots an empty queue and intakes work later — the common case —
# reports `dispatchable: []` forever, so a strip anchored on it alone never
# renders. The state directory is authoritative and current; boot fills in
# behind it.
#
# Every parser here is pure so the whole matrix is exercisable on any runner
# (design decision D-4 in docs/design-cross-platform.md).
SPACEDOCK_FO = "spacedock:first-officer"
SPACEDOCK_ENSIGN = "spacedock:ensign"
# Boot output sits near the session start, not the tail: measured across the
# transcripts on one machine it lands 97 KB-405 KB in, so the tail window the
# turn scanner uses never contains it. 512 KiB caught 25 of 27; a session that
# boots later than that renders no strip rather than a guessed one.
SD_BOOT_SCAN_BYTES = 512_000
SD_README_BYTES = 65_536  # frontmatter is ~540 bytes behind 32 KB of prose
SD_ENTITY_BYTES = 8_192  # an entity file's frontmatter, ahead of its report body
SD_MAX_FRONTMATTER_LINES = 400
SD_MAX_STAGES = 32
SD_MAX_WORKFLOWS = 8  # one first officer can drive several workflows
SD_MAX_ENTITIES = 12  # strips rendered per workflow
# Entity files whose frontmatter is read per workflow, newest first. A mature
# queue holds far more than it is running: 31 files in the largest live state
# directory measured, nearly all parked on the initial stage.
SD_MAX_ENTITY_FILES = 96
SD_MAX_BOOT_RECORDS = 16
# Decode attempts per tool result. A transcript full of `{"command"` lookalikes
# would otherwise cost one failed decode each while the collection lock is held.
SD_MAX_BOOT_CANDIDATES = 64
# Spacedock's own stage-name grammar (internal/status/stages.go): lowercase
# kebab, at least two characters, interior hyphens legal. Hyphens inside stage
# names are why worker names cannot be parsed positionally.
SD_STAGE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
# Cycle/retry markers a first officer appends to a worker name. Observed live in
# every position: before the stage and after it.
SD_CYCLE_RE = re.compile(r"^(?:cycle|pass|round|c|v|p|r)\d+[a-z]?$|^(?:retry|rerun)$")
SD_COMMISSIONED_PREFIX = "spacedock@"
# The workflow README and the entity-state frontmatter are the only project
# reads Cargento performs. The switch exists so an operator who wants the
# store-only read surface can have it back; see SECURITY.md.
SPACEDOCK_ENABLED = True


def sd_frontmatter_lines(text: str) -> list[str]:
    """The lines between a leading ``---`` fence and its closer, else [].

    Mirrors Spacedock's own fence finder: a leading BOM is stripped, truly
    empty leading lines are skipped, and the first content line must be exactly
    ``---``. CRLF is normalized so a ``---\\r`` fence still matches.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    start = None
    for index, raw in enumerate(lines):
        line = raw.removeprefix("﻿") if index == 0 else raw
        if line == "":
            continue
        if line.strip() != "---":
            return []
        start = index + 1
        break
    if start is None:
        return []
    out: list[str] = []
    for raw in lines[start:]:
        if raw.strip() == "---":
            return out
        if len(out) >= SD_MAX_FRONTMATTER_LINES:
            return []
        out.append(raw)
    return []  # unterminated frontmatter is not frontmatter


def sd_scalar(lines: list[str], key: str) -> str:
    """A column-0 scalar from frontmatter lines, unquoted."""
    prefix = key + ":"
    for raw in lines:
        if raw.startswith(prefix):
            return raw[len(prefix) :].strip().strip("\"'")
    return ""


def sd_truthy(value: str) -> bool:
    """YAML's true-ish scalars, quoted or bare. Anything else is false."""
    return value.strip().strip("\"'").lower() in {"true", "yes", "on"}


def sd_stage_entries(lines: list[str]) -> list[dict[str, Any]]:
    """The ordered ``stages.states[]`` list, or [] if unrecognised.

    Each entry is ``{"name", "initial", "terminal"}``. An indentation-scoped
    scan, not a YAML evaluator: enter ``stages:``, then ``states:``, then take
    each ``- name:`` until the block dedents to a sibling key
    (``transitions:``), attributing the ``initial:``/``terminal:`` flags nested
    under an item to it. Document order is the stage order — Spacedock's own
    advancement indexes this list.

    Anything the scan cannot model yields [] so the dashboard renders no strip
    rather than a wrong one. That deliberately covers flow-style sequences,
    quoted keys, anchors and aliases.
    """
    entries: list[dict[str, Any]] = []
    names: set[str] = set()
    stages_indent: int | None = None
    states_indent: int | None = None
    item_indent: int | None = None
    for raw in lines:
        body = raw.strip()
        if not body or body.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if stages_indent is None:
            if body == "stages:":
                stages_indent = indent
            continue
        if states_indent is None:
            if indent <= stages_indent:
                return []  # left the stages block without finding states
            if body == "states:":
                states_indent = indent
            continue
        if indent <= states_indent and not body.startswith("- "):
            break  # dedented to a sibling of states:
        if body.startswith("- "):
            if item_indent is None:
                item_indent = indent
            if indent == item_indent and not body.startswith("- name:"):
                # A states entry this scanner cannot model (flow style
                # `- {name: x}`, a quoted key, an anchor). Skipping it would emit
                # a spine missing a stage the workflow really declares — a wrong
                # strip, the one outcome worse than no strip. Deeper `- ` items
                # are nested values (a stage's `decision.options`), not states.
                return []
        if not body.startswith("- name:") or indent != item_indent:
            # A flag nested under the item currently being built. Deeper `- `
            # items reach here too, but they cannot start with these keys.
            if entries and item_indent is not None and indent > item_indent:
                for flag in ("initial", "terminal"):
                    if body.startswith(flag + ":"):
                        entries[-1][flag] = sd_truthy(body[len(flag) + 1 :])
            continue
        value = body[len("- name:") :].strip().strip("\"'")
        if not value or not SD_STAGE_RE.match(value) or value in names:
            return []
        if len(entries) >= SD_MAX_STAGES:
            return []
        names.add(value)
        entries.append({"name": value, "initial": False, "terminal": False})
    return entries


def sd_stage_names(lines: list[str]) -> list[str]:
    """The ordered stage names, or [] if the states block is unrecognised."""
    return [entry["name"] for entry in sd_stage_entries(lines)]


def sd_tool_result_text(record: dict[str, Any]) -> list[str]:
    """The text of every ``tool_result`` block in one transcript record.

    Provenance matters: boot output is *command output*, so it counts only when
    it arrives in a tool result. Scanning the raw line would let ordinary
    conversation text — anything a user pasted or a model echoed — nominate an
    absolute path for Cargento to open.
    """
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        text = block.get("content")
        if isinstance(text, str):
            out.append(text)
        elif isinstance(text, list):
            out.extend(
                part["text"]
                for part in text
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
    return out


def sd_boot_records(data: bytes) -> list[dict[str, Any]]:
    """Every ``spacedock status --boot`` envelope in a transcript head.

    Decoded line by line as the JSONL it is, so the JSON decoder does the
    unescaping and each envelope is located inside already-plain text. An
    earlier version scanned the escaped bytes with a hand-rolled brace balancer,
    which both mis-sliced a path containing a brace and rescanned to the end of
    the blob for every unbalanced marker — quadratic, under the collection lock.
    """
    out: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for line in data.split(b"\n"):
        if b"definition_dir" not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        for text in sd_tool_result_text(record):
            position = 0
            for _ in range(SD_MAX_BOOT_CANDIDATES):
                begin = text.find('{"command"', position)
                if begin < 0:
                    break
                try:
                    envelope, position = decoder.raw_decode(text, begin)
                except ValueError:
                    # raw_decode fails at the first bad byte, so stepping past a
                    # bad candidate cannot degrade into a whole-blob rescan.
                    position = begin + 1
                    continue
                if isinstance(envelope, dict) and envelope.get("command") == "boot":
                    out.append(envelope)
                    if len(out) >= SD_MAX_BOOT_RECORDS:
                        return out
    return out


def sd_workflow_dirs(records: list[dict[str, Any]]) -> list[str]:
    """Distinct absolute workflow directories named by boot envelopes.

    Order is first-seen so the display order matches the boot order. Only
    absolute paths are kept: a relative value cannot be resolved without
    guessing a base, and guessing is what the read contract forbids.
    """
    out: list[str] = []
    for record in records:
        value = record.get("definition_dir")
        if not isinstance(value, str) or not value:
            continue
        if not os.path.isabs(value) or "\x00" in value:
            continue
        if value not in out:
            out.append(value)
        if len(out) >= SD_MAX_WORKFLOWS:
            break
    return out


def sd_boot_entities(records: list[dict[str, Any]], workflow_dir: str) -> dict[str, str]:
    """``{slug: current_stage}`` for one workflow, newest envelope winning.

    A first officer boots once per workflow and may re-boot; later envelopes
    carry fresher stages, so they overwrite earlier ones.
    """
    out: dict[str, str] = {}
    for record in records:
        if record.get("definition_dir") != workflow_dir:
            continue
        items = record.get("dispatchable")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            current = item.get("current")
            if isinstance(slug, str) and slug and isinstance(current, str) and current:
                out[slug] = current
    return out


def sd_boot_entity_dir(records: list[dict[str, Any]], workflow_dir: str) -> str:
    """The absolute entity-state directory one workflow's boot output names.

    Same provenance and same authority as ``definition_dir``: the session's own
    command output, in a tool result. The newest envelope wins, and the value is
    kept only if it is absolute — a relative path cannot be resolved without
    guessing a base, and guessing is what the read contract forbids. A
    ``split-root`` workflow legitimately stores state outside its definition
    directory, so containment is NOT required here; the discriminator is applied
    per file instead (see :func:`sd_read_entities`).
    """
    out = ""
    for record in records:
        if record.get("definition_dir") != workflow_dir:
            continue
        value = record.get("entity_dir")
        if isinstance(value, str) and value and os.path.isabs(value) and "\x00" not in value:
            out = value
    return out


# Subagent-transcript classification cache. Whether a top-level transcript
# belongs to a subagent and its eventual label are immutable for a given file,
# but young files may not have written both identifying records yet — so
# incomplete results are cached only once the file is big enough to be conclusive.
_agent_class_cache: dict[str, tuple[bool, str, str]] = {}
_AGENT_SCAN_LINES = 50
_AGENT_CACHE_NEGATIVE_MIN_BYTES = 16384
_AGENT_SCAN_BYTES = _AGENT_CACHE_NEGATIVE_MIN_BYTES


def claude_agent_identity(path: str) -> tuple[bool, str, str]:
    """Classify a top-level transcript: (is_subagent, agent_name, parent_prefix).

    Harness >= 2.x writes subagent transcripts as ordinary <uuid>.jsonl files
    in the project directory; their records carry ``agentName`` and
    ``teamName`` = "session-<parent 8-char prefix>". Older harnesses used
    <session>/subagents/agent-*.jsonl, still handled by
    load_claude_subagents().
    """
    with _cache_lock:
        cached = _agent_class_cache.get(path)
    if cached is not None:
        return cached
    name, parent = "", ""
    size = 0
    lines_seen = 0
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            data = f.read(_AGENT_SCAN_BYTES)
        lines = data.split(b"\n")
        if size > len(data) and data and not data.endswith(b"\n"):
            lines.pop()  # the byte prefix ended inside a JSON record
        for line in lines[:_AGENT_SCAN_LINES]:
            if not line:
                continue
            lines_seen += 1
            if name and parent:
                break
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            agent_name = rec.get("agentName")
            if not name and isinstance(agent_name, str) and agent_name:
                name = agent_name
            team = rec.get("teamName")
            if not parent and isinstance(team, str) and team.startswith("session-"):
                parent = team[len("session-") :][:8]
    except OSError:
        return (False, "", "")
    result = (bool(parent), name, parent)
    # A complete subagent identity is conclusive; an incomplete result is only
    # trusted once the file has enough content that later records cannot change it.
    if (
        (parent and name)
        or lines_seen >= _AGENT_SCAN_LINES
        or size >= _AGENT_CACHE_NEGATIVE_MIN_BYTES
    ):
        with _cache_lock:
            bounded_put(_agent_class_cache, path, result)
    return result


_sd_role_cache: dict[str, str] = {}
_sd_boot_cache: dict[tuple[str, int], list[dict[str, Any]]] = {}
_sd_workflow_cache: dict[tuple[str, int, int], dict[str, Any] | None] = {}
_sd_entity_cache: dict[tuple[str, int, int], str] = {}


def claude_agent_setting(path: str) -> str:
    """The ``agentSetting`` a transcript declares in its head, else "".

    The launcher passes ``--agent spacedock:first-officer``, so the value is
    written at record index 0 or 1 — inside the same head bytes the subagent
    classifier already reads. Immutable per file once present.
    """
    with _cache_lock:
        cached = _sd_role_cache.get(path)
    if cached is not None:
        return cached
    setting = ""
    size = 0
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            data = handle.read(_AGENT_SCAN_BYTES)
        lines = data.split(b"\n")
        if size > len(data) and data and not data.endswith(b"\n"):
            lines.pop()
        for line in lines[:_AGENT_SCAN_LINES]:
            if not line or b"agentSetting" not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            value = record.get("agentSetting")
            if isinstance(value, str) and value:
                setting = value
                break
    except OSError:
        return ""
    if setting or size >= _AGENT_CACHE_NEGATIVE_MIN_BYTES:
        with _cache_lock:
            bounded_put(_sd_role_cache, path, setting)
    return setting


def sd_transcript_boot(path: str) -> list[dict[str, Any]]:
    """Boot envelopes from a transcript's head, cached per (path, size).

    Boot output is written once at session start and never rewritten, so the
    scan is amortised: keying on size lets a still-growing session pick the
    envelope up on a later refresh without rescanning an unchanged prefix.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    key = (path, min(size, SD_BOOT_SCAN_BYTES))
    with _cache_lock:
        cached = _sd_boot_cache.get(key)
    if cached is not None:
        return cached
    records: list[dict[str, Any]] = []
    try:
        with open(path, "rb") as handle:
            blob = handle.read(SD_BOOT_SCAN_BYTES)
        if b"definition_dir" in blob:
            records = sd_boot_records(blob)
    except OSError:
        return []
    with _cache_lock:
        bounded_put(_sd_boot_cache, key, records)
    return records


def sd_open_regular(path: str) -> int | None:
    """Open ``path`` read-only, refusing symlinks and non-regular files.

    ``O_NOFOLLOW`` is absent on Windows, so there the refusal rests on the
    ``lstat`` classification alone and a racing reparse-point swap could still
    be followed — the same unclosable class as the FILE_SHARE_DELETE window
    documented in SKILL.md.
    """
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        if stat_module.S_ISLNK(os.lstat(path).st_mode):
            return None
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        if not stat_module.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            return None
    except OSError:
        os.close(descriptor)
        return None
    return descriptor


class SdMismatchError(Exception):
    """The opened file is not the one that was stat'd. Distinct from an empty
    read, which is merely a file with no frontmatter."""


def sd_read_frontmatter(path: str, limit: int, expect: os.stat_result) -> list[str]:
    """The frontmatter lines of a regular, non-symlink file, or [].

    At most ``limit`` bytes are read, and the descriptor must describe the same
    file ``expect`` does. O_NOFOLLOW guards only the final path component, so a
    parent-directory swap between the stat and the open would otherwise seed a
    cache from a different file under a trusted key — that raises
    :class:`SdMismatchError` so the caller can decline to cache. Only the frontmatter
    lines leave this function; the body is never returned.
    """
    descriptor = sd_open_regular(path)
    if descriptor is None:
        return []
    try:
        opened = os.fstat(descriptor)
        same_file = (opened.st_dev, opened.st_ino) == (expect.st_dev, expect.st_ino)
    except OSError:
        same_file = False
    if not same_file:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        raise SdMismatchError(path)
    raw = b""
    try:
        handle = os.fdopen(descriptor, "rb")
    except OSError:
        # os.fdopen does not close the descriptor when it fails to wrap it,
        # and this runs on every refresh — leaking here exhausts the table.
        with contextlib.suppress(OSError):
            os.close(descriptor)
    else:
        with handle, contextlib.suppress(OSError):
            raw = handle.read(limit)
    return sd_frontmatter_lines(raw.decode("utf-8", "replace"))


def sd_read_workflow(workflow_dir: str) -> dict[str, Any] | None:
    """The stage taxonomy of one workflow directory, or None.

    ``workflow_dir`` is an absolute path the session itself recorded in its boot
    output; it is canonicalised, its README must be a regular non-symlink file,
    at most ``SD_README_BYTES`` are read, and the result counts only if the
    frontmatter declares ``commissioned-by: spacedock@`` — Spacedock's own
    workflow discriminator. No other file in the workflow directory is read and
    no directory is walked; the entity-state directory the boot output names
    separately is read by :func:`sd_read_entities`. Only derived scalars leave
    this function; no file text does.

    ``resting`` is the subset of stages an entity is not moving through: the
    initial stage it is queued on and the terminal stages it has finished at.
    """
    try:
        root = os.path.realpath(workflow_dir)
        readme = os.path.join(root, "README.md")
        info = os.stat(readme)
    except OSError:
        return None
    # Containment: the README must resolve inside the directory it was found in,
    # so a symlinked or swapped entry cannot redirect the read elsewhere.
    try:
        resolved = os.path.realpath(readme)
        if os.path.commonpath((root, resolved)) != root:
            return None
    except (OSError, ValueError):
        return None
    key = (root, info.st_mtime_ns, info.st_size)
    with _cache_lock:
        if key in _sd_workflow_cache:
            return _sd_workflow_cache[key]
    result: dict[str, Any] | None = None
    try:
        lines = sd_read_frontmatter(readme, SD_README_BYTES, info)
    except SdMismatchError:
        return None
    if sd_scalar(lines, "commissioned-by").startswith(SD_COMMISSIONED_PREFIX):
        entries = sd_stage_entries(lines)
        if entries:
            result = {
                "name": os.path.basename(root) or root,
                "stages": [entry["name"] for entry in entries],
                "resting": [
                    entry["name"] for entry in entries if entry["initial"] or entry["terminal"]
                ],
            }
    with _cache_lock:
        bounded_put(_sd_workflow_cache, key, result)
    return result


def sd_entity_stage(path: str, info: os.stat_result) -> str:
    """The ``status`` scalar in one entity file's frontmatter, or "".

    Cached on ``(path, st_mtime_ns, st_size)``, so a state directory in which
    only one entity is moving costs one read per refresh and a stat per file.
    """
    key = (path, info.st_mtime_ns, info.st_size)
    with _cache_lock:
        cached = _sd_entity_cache.get(key)
    if cached is not None:
        return cached
    try:
        lines = sd_read_frontmatter(path, SD_ENTITY_BYTES, info)
    except SdMismatchError:
        return ""
    stage = sd_scalar(lines, "status")
    with _cache_lock:
        bounded_put(_sd_entity_cache, key, stage)
    return stage


def sd_entity_files(entity_dir: str) -> list[tuple[str, str, os.stat_result]]:
    """``(slug, path, stat)`` for a state directory's entity files, newest first.

    Spacedock writes an entity as either ``<slug>.md`` or ``<slug>/index.md``
    (the folder form, for entities that accumulate per-stage artifacts). One
    ``scandir`` of the directory the boot output named; nothing below it is
    walked, and ``_archive/`` — where Spacedock retires finished entities — is
    skipped along with every other name that is not a well-formed slug.

    Newest-first because the cap that follows is a budget: a mature queue holds
    far more entities than it is running, and the ones being written are the
    ones in flight.

    Every candidate is `lstat`ed for real rather than taking the stat
    ``scandir`` already cached. On Windows that cached result reports
    ``st_ino`` and ``st_dev`` as zero, which can never match the ``fstat`` of an
    open descriptor — so the identity check in :func:`sd_read_frontmatter`
    would refuse every entity file and the strip would come back empty on that
    platform alone. A silent per-platform false negative is exactly the failure
    mode D-4 in ``docs/design-cross-platform.md`` exists to keep out.
    """
    try:
        with os.scandir(os.path.realpath(entity_dir)) as entries:
            found = list(entries)
    except OSError:
        return []
    out: list[tuple[str, str, os.stat_result]] = []
    for entry in found:
        name = entry.name
        slug = name.removesuffix(".md")
        # Spacedock's slug grammar is its stage grammar: lowercase kebab. That
        # rejects `_archive`, `README.md` and the report files operators leave
        # beside the state without a second pass over the listing.
        if not SD_STAGE_RE.match(slug):
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                path = os.path.join(entry.path, "index.md")
            elif name.endswith(".md"):
                path = entry.path
            else:
                continue
            info = os.lstat(path)
        except OSError:
            continue  # entity written or retired between the listing and the stat
        if not stat_module.S_ISREG(info.st_mode):
            continue  # a symlinked entity file is refused, not followed
        out.append((slug, path, info))
    out.sort(key=lambda item: -item[2].st_mtime_ns)
    return out[:SD_MAX_ENTITY_FILES]


def sd_read_entities(
    entity_dir: str, stages: list[str], now: float, window_sec: float
) -> list[tuple[str, str]]:
    """``[(slug, stage)]`` for one workflow's recent entity state, newest first.

    The authoritative, current answer to "where is each entity", against which
    the boot envelope's ``dispatchable`` snapshot is only a stale hint. An entity
    counts only when:

    - its state file was written within ``window_sec`` — the same freshness
      window every collector applies to a session. A first officer discovers
      every workflow in the project, and a workflow retired months ago still has
      entities frozen mid-pipeline; those are history, not work in flight.
    - its frontmatter ``status`` names a stage this workflow declares — the
      per-file discriminator that stands in for the containment check
      :func:`sd_read_workflow` performs, since a ``split-root`` workflow may
      legitimately keep its state outside the definition directory.
    """
    declared = set(stages)
    out: list[tuple[str, str]] = []
    for slug, path, info in sd_entity_files(entity_dir):
        if not is_fresh(now, info.st_mtime, window_sec):
            continue
        stage = sd_entity_stage(path, info)
        if stage in declared:
            out.append((slug, stage))
    return out


def sd_attribute_worker(
    name: str, slugs: list[str], stages: list[str]
) -> tuple[str, str, str] | None:
    """``(slug, stage, cycle)`` for a worker, anchored on a *known* slug.

    Guessing the slug by stripping cycle-shaped tokens is wrong twice over: real
    entity slugs end in cycle-shaped tokens of their own (`…-pr-1506-r3` is one
    entity, not `…-pr-1506` on round 3), and a guessed slug matches every other
    workflow that declares the same stage. So the slug comes from this
    workflow's own boot snapshot, longest first so a slug that prefixes another
    cannot win.
    """
    body = name.removeprefix("spacedock-ensign-")
    if body == name:
        return None
    for slug in sorted(slugs, key=len, reverse=True):
        remainder = body.removeprefix(slug + "-")
        if remainder == body:
            continue
        tokens = remainder.split("-")
        for stage in sorted(stages, key=len, reverse=True):
            stage_tokens = stage.split("-")
            for offset in range(len(tokens) - len(stage_tokens), -1, -1):
                if tokens[offset : offset + len(stage_tokens)] != stage_tokens:
                    continue
                rest = tokens[:offset] + tokens[offset + len(stage_tokens) :]
                if any(not SD_CYCLE_RE.match(token) for token in rest):
                    continue
                return (slug, stage, "-".join(rest))
    return None


def sd_session_workflows(
    boot: list[dict[str, Any]],
    worker_names: list[str],
    now: float,
    window_sec: float,
) -> list[dict[str, Any]]:
    """Render-ready workflow strips for one session.

    An entity earns a strip when it is *in flight*: named by a live worker, or
    parked on a stage it is moving through, or listed as dispatchable at boot.
    Three sources in decreasing order of freshness — live workers first and
    marked, then the entity state directory, then the boot snapshot — deduped by
    slug so the freshest answer for an entity wins.

    Entities resting on the initial or a terminal stage are left out of the
    middle source. A mature queue is mostly those: reporting thirty entities
    parked on ``intake`` would push the handful that are actually moving off the
    end of the strip. They still appear if boot called them dispatchable, which
    is Spacedock's own statement that they are next to move.
    """
    out: list[dict[str, Any]] = []
    for workflow_dir in sd_workflow_dirs(boot):
        info = sd_read_workflow(workflow_dir)
        if info is None:
            continue
        stages: list[str] = info["stages"]
        resting: set[str] = set(info["resting"])
        booted = sd_boot_entities(boot, workflow_dir)
        entity_dir = sd_boot_entity_dir(boot, workflow_dir)
        roster = sd_read_entities(entity_dir, stages, now, window_sec) if entity_dir else []
        # Live worker names carry a stage but not a slug boundary, so the slug
        # has to come from a roster. The state directory is what makes that
        # roster non-empty for a first officer that booted an empty queue.
        slugs = list({slug for slug, _ in roster} | set(booted))
        entities: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in worker_names:
            attributed = sd_attribute_worker(name, slugs, stages)
            if attributed is None:
                continue
            slug, stage, cycle = attributed
            if slug in seen:
                continue
            seen.add(slug)
            entities.append({"slug": slug, "stage": stage, "cycle": cycle, "live": True})
        for slug, stage in roster:
            if slug in seen or stage in resting:
                continue
            seen.add(slug)
            entities.append({"slug": slug, "stage": stage, "cycle": "", "live": False})
        for slug, stage in booted.items():
            if slug in seen or stage not in stages:
                continue
            seen.add(slug)
            entities.append({"slug": slug, "stage": stage, "cycle": "", "live": False})
        if not entities:
            continue
        out.append(
            {
                "workflow": info["name"],
                "stages": stages,
                "entities": entities[:SD_MAX_ENTITIES],
            }
        )
    return out


def claude_prefix_is_agent(prefix: str) -> bool:
    """True when the newest transcript for this 8-char prefix belongs to a
    subagent. Used to suppress popups for agent sessions."""
    newest, newest_mtime = None, 0.0
    for fp in glob_stores("claude.projects", PROJECTS_DIR, "*", glob.escape(prefix) + "*.jsonl"):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        if mtime > newest_mtime:
            newest, newest_mtime = fp, mtime
    if not newest:
        return False
    return claude_agent_identity(newest)[0]


def collect_claude(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    tasks_by_session = load_tasks()
    transcripts: dict[str, str] = {}  # prefix -> newest transcript path
    agent_children: dict[str, list[dict[str, Any]]] = {}  # parent prefix -> children
    for fp in glob_stores("claude.projects", PROJECTS_DIR, "*", "*.jsonl"):
        base = os.path.basename(fp)
        if "-agent-" in base or base.startswith("agent-"):
            continue  # legacy subagent transcripts aren't top-level sessions
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue  # transcript rotated/deleted between glob and stat
        if show_all or is_fresh(now, mtime, window_hours * 3600):
            is_agent, agent_name, parent_prefix = claude_agent_identity(fp)
            if is_agent:
                # Fold into the parent session; never a standalone session.
                # Without a parent prefix there is nothing to attach to.
                if parent_prefix and is_fresh(now, mtime, window_hours * 3600):
                    agent_children.setdefault(parent_prefix, []).append(
                        {
                            "path": fp,
                            "mtime": mtime,
                            "label": (agent_name or "subagent")[:70],
                        }
                    )
                continue
        prefix = base[:8]
        try:
            if prefix not in transcripts or mtime > os.path.getmtime(transcripts[prefix]):
                transcripts[prefix] = fp
        except OSError:
            continue  # transcript rotated/deleted between glob and stat

    out: list[dict[str, Any]] = []
    for prefix in set(transcripts) | set(tasks_by_session):
        transcript = transcripts.get(prefix)
        tasks = sorted(
            tasks_by_session.get(prefix, []),
            key=lambda t: int(t["id"]) if str(t["id"]).isdigit() else 0,
        )
        try:
            transcript_mtime = os.path.getmtime(transcript) if transcript else 0
        except OSError:
            transcript_mtime = 0
        latest_task_mtime = max((t["updated"] for t in tasks), default=0)
        agent_files = claude_agent_transcripts(transcript)
        subagents = load_claude_subagents(transcript, now)
        children = agent_children.get(prefix, [])
        subagents += [
            {"label": c["label"], "mtime": c["mtime"]}
            for c in children
            if is_fresh(now, c["mtime"], WORKING_THRESHOLD_SEC)  # fresh = running
        ]
        latest_agent_mtime = max(
            (a["mtime"] for a in subagents),
            default=0,
        )
        latest_child_mtime = max((c["mtime"] for c in children), default=0)
        # Every subagent write, not just the ones fresh enough to read as
        # running: a workflow that has been going for hours parks its parent
        # transcript, and without this the session ages out of the window.
        latest_agent_file_mtime = max((m for _, m in agent_files), default=0)
        activity_sources = (
            latest_task_mtime,
            transcript_mtime,
            latest_agent_mtime,
            latest_agent_file_mtime,
            latest_child_mtime,
        )
        last_activity = newest_plausible(now, activity_sources)
        active = is_fresh(now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue

        project = (
            (
                project_from_cwd(claude_session_cwd(transcript))
                # Lossy fallback: the encoded name cannot be split back into
                # segments, so it stays whole rather than guessing at a split.
                or project_label(os.path.basename(os.path.dirname(transcript)))
            )
            if transcript
            else "unknown"
        )
        # Sampled before analyze_transcript: that scan is the slow part, and a
        # SessionEnd landing during it must invalidate everything derived here.
        seen_generation = hook_generation(prefix)
        info = analyze_transcript(transcript) if (transcript and active) else None

        state, state_detail = "idle", "awaiting your message"
        blocked_since = None
        # mtime floor: match the other collectors when the newest write has
        # no parseable timestamp (partial line, untimestamped record)
        parsed_last_event = info["last_event_ts"] if info else 0
        last_event_sources = (parsed_last_event, transcript_mtime)
        hook = (
            current_hook(prefix, (info or {}).get("last_user_event"), parsed_last_event)
            if active
            else None
        )
        if info and info["pending_input_tool"]:
            p = info["pending_input_tool"]
            state = "needs_input"
            blocked_since = p["ts"] or last_activity
            state_detail = f"open question ({p['name']}), waiting {fmt_duration(age(now, p['ts'])) if p['ts'] else '?'}"
        # Fresh activity beats a hook: Claude Code emits "waiting for your
        # input" notifications for sessions that keep running via background
        # tasks and will resume on their own. A hook only surfaces as
        # needs-input once the session actually goes quiet; permission-prompt
        # popups are unaffected (they fire on the POST itself).
        elif subagents or is_fresh(
            now, newest_plausible(now, last_event_sources), WORKING_THRESHOLD_SEC
        ):
            state = "working"
            in_prog = next((t for t in tasks if t["status"] == "in_progress"), None)
            if in_prog:
                state_detail = (in_prog["activeForm"] or in_prog["subject"]) + "…"
            else:
                state_detail = working_detail(info, subagents)
        elif hook:
            state = "needs_input"
            blocked_since = hook["ts"]
            state_detail = hook["message"] or "waiting for your input"
        if state == "needs_input" and hook_generation(prefix) != seen_generation:
            # The session exited while this snapshot was being built. Applies to
            # the transcript-detected case too: an unanswered AskUserQuestion in
            # a session the user has quit is moot, not blocking.
            state, blocked_since = "idle", None
            state_detail = "awaiting your message"
        if active:
            maybe_popup(
                prefix,
                state,
                f"[{project}] {state_detail}" if state == "needs_input" else None,
                expect_generation=seen_generation,
            )

        total = len(tasks)
        done = sum(1 for t in tasks if t["status"] == "completed")
        open_count = total - done
        durations = [
            t["updated"] - t["created"]
            for t in tasks
            if t["status"] == "completed" and (t["updated"] - t["created"]) >= 30
        ]
        eta_sec = (
            (sum(durations) / len(durations)) * open_count if durations and open_count else None
        )

        for t in tasks:
            elapsed = (
                (t["updated"] - t["created"])
                if t["status"] == "completed"
                else age(now, t["created"])
            )
            t["elapsed_h"] = fmt_duration(elapsed)
            t["updated_ago"] = fmt_duration(age(now, t["updated"])) + " ago"

        s = base_session("claude", prefix, project)
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "blocked_since": blocked_since,
                "active": active,
                "last_activity": last_activity,
                # Subagent output now lives in the children's own transcripts;
                # fold it in so the session's rate reflects all its work.
                "rate_per_min": rate_from(info, now)
                + sum(
                    rate_from(analyze_transcript(path), now)
                    for path, mtime in agent_files
                    if is_fresh(now, mtime, RATE_WINDOW_SEC)
                )
                + sum(
                    rate_from(analyze_transcript(c["path"]), now)
                    for c in children
                    if is_fresh(now, c["mtime"], RATE_WINDOW_SEC)
                ),
                "total": total,
                "done": done,
                "open": open_count,
                "progress_pct": round(done * 100 / total) if total else 0,
                "eta_h": fmt_duration(eta_sec) if eta_sec else None,
                "turn": turn_progress(
                    scan_turns(transcript, "claude") if (info and transcript) else None,
                    state,
                    now,
                ),
                "subagents": [a["label"] for a in subagents],
                "tasks": tasks,
                "spacedock": claude_spacedock(transcript, subagents, now, window_hours * 3600),
            }
        )
        out.append(s)
    return out


def claude_spacedock(
    transcript: str | None,
    subagents: list[dict[str, Any]],
    now: float,
    window_sec: float,
) -> dict[str, Any] | None:
    """Spacedock role and workflow strips for one Claude session, or None.

    Gated on the session declaring a Spacedock ``agentSetting``, so a session
    that has nothing to do with Spacedock costs one cached lookup and opens no
    project file. Only a first officer gets strips: an ensign is a single worker
    whose own stage is already the parent's strip.
    """
    if not transcript:
        return None
    setting = claude_agent_setting(transcript)
    if setting == SPACEDOCK_ENSIGN:
        return {"role": "ensign", "workflows": []}
    if setting != SPACEDOCK_FO:
        return None
    if not SPACEDOCK_ENABLED:
        # The switch withdraws the project reads, not the role: the badge comes
        # from the transcript head, which is a store path either way.
        return {"role": "first-officer", "workflows": []}
    boot = sd_transcript_boot(transcript)
    names = [str(a.get("label") or "") for a in subagents]
    return {
        "role": "first-officer",
        "workflows": sd_session_workflows(boot, names, now, window_sec),
    }


def collect_codex(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    # Resumes and subagent threads write separate rollout files; group by the
    # session_meta session_id, keep the newest top-level file per session,
    # and treat fresh subagent-thread files as that session's running agents.
    sessions: dict[str, tuple[float, str]] = {}  # session_id -> (mtime, path)
    # parent session_id -> {"agents": [(label, mtime)], "rate": int}
    agent_data: dict[str, dict[str, Any]] = {}
    for fp in glob_stores("codex.sessions", CODEX_SESSIONS_DIR, "*", "*", "*", "rollout-*.jsonl"):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        meta = codex_meta(fp)
        sid = meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")][-36:]
        if meta.get("subagent"):
            parent_sid = meta.get("parent_session_id") or sid
            data = agent_data.setdefault(parent_sid, {"agents": [], "rate": 0})
            if is_fresh(now, mtime, RATE_WINDOW_SEC):
                data["rate"] += codex_subagent_rate(fp, now)
            if is_fresh(now, mtime, WORKING_THRESHOLD_SEC):
                data["agents"].append(((meta.get("agent_label") or "subagent")[:70], mtime))
            continue
        if sid not in sessions or mtime > sessions[sid][0]:
            sessions[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in sessions.items():
        data = agent_data.get(sid) or {"agents": [], "rate": 0}
        agents = sorted(data["agents"], key=lambda a: -a[1])
        activity_sources = (mtime, *(m for _, m in agents))
        last_activity = newest_plausible(now, activity_sources)
        active = is_fresh(now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        info = analyze_codex_transcript(fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, *activity_sources)
        subagents = [label for label, _ in agents]
        state, state_detail = "idle", "awaiting your message"
        if is_fresh(now, newest_plausible(now, last_event_sources), WORKING_THRESHOLD_SEC):
            state = "working"
            state_detail = working_detail(info, subagents)

        s = base_session("codex", sid, project_from_cwd(codex_meta(fp).get("cwd") or "") or "codex")
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": rate_from(info, now) + data["rate"],
                "turn": turn_progress(scan_turns(fp, "codex") if info else None, state, now),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out


def discover_pi() -> bool:
    """Whether Pi has at least one JSONL file with a valid session header."""
    paths = set(glob_stores("pi.sessions", PI_SESSIONS_DIR, "*.jsonl"))
    paths.update(glob_stores("pi.sessions", PI_SESSIONS_DIR, "*", "*.jsonl"))
    for path in paths:
        try:
            if pi_meta(path).get("session_id"):
                return True
        except (OSError, ValueError):
            continue
    return False


def collect_pi(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    """Collect Pi's independent JSONL sessions from flat and nested stores."""
    paths = set(glob_stores("pi.sessions", PI_SESSIONS_DIR, "*.jsonl"))
    paths.update(glob_stores("pi.sessions", PI_SESSIONS_DIR, "*", "*.jsonl"))
    sessions: dict[str, tuple[float, str, dict[str, Any]]] = {}
    for path in paths:
        try:
            mtime = os.path.getmtime(path)
            meta = pi_meta(path)
        except (OSError, ValueError):
            continue
        sid = meta.get("session_id")
        if not isinstance(sid, str) or not sid:
            continue
        if sid not in sessions or mtime > sessions[sid][0]:
            sessions[sid] = (mtime, path, meta)

    out: list[dict[str, Any]] = []
    for sid, (mtime, path, meta) in sessions.items():
        try:
            info = scan_pi_session(path)
        except (OSError, ValueError):
            continue
        last_event_ts = info["last_event_ts"] if info else 0
        last_activity = newest_plausible(now, (last_event_ts, mtime))
        active = is_fresh(now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        state, state_detail = "idle", "awaiting your message"
        if is_fresh(now, last_activity, WORKING_THRESHOLD_SEC):
            state = "working"
            state_detail = working_detail(info, [])
        project = project_from_cwd(meta.get("cwd") or "") or "pi"
        session = base_session("pi", sid, project)
        session.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": rate_from(info, now),
                "turn": turn_progress((info or {}).get("turn"), state, now),
            }
        )
        out.append(session)
    return out


def antigravity_log_head_lines(path: str) -> list[str]:
    """Read the bounded identity-bearing beginning of an Antigravity CLI log."""
    try:
        with open(path, "rb") as source:
            return source.read(80_000).decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def antigravity_log_lines(path: str) -> list[str]:
    """Read the beginning and bounded tail of an Antigravity CLI log.

    Workspace and conversation identity are written near the beginning,
    while the latest user prompt is near the tail. Long-running sessions can
    exceed ``TAIL_BYTES``, so reading only one side loses one of those.
    """
    return antigravity_log_head_lines(path) + read_tail(path)


def antigravity_session_metadata(
    now: float, window_hours: float, show_all: bool
) -> dict[str, dict[str, Any]]:
    """Best-effort conversation metadata from Antigravity's public-facing
    CLI logs and last-conversation cache.

    Conversation payloads are protobuf blobs inside per-session SQLite
    stores. The logs already expose the stable boundaries needed here:
    workspace, conversation id, and human prompt. Broken or rotated files are
    skipped so one incomplete Antigravity run cannot break the dashboard.
    """
    sessions: dict[str, dict[str, Any]] = {}
    cached_cwds: dict[str, str] = {}
    try:
        with open(ANTIGRAVITY_LAST_CONVERSATIONS, encoding="utf-8") as source:
            recent = json.load(source)
        if isinstance(recent, dict):
            for workspace, sid in recent.items():
                if (
                    isinstance(workspace, str)
                    and isinstance(sid, str)
                    and project_from_cwd(workspace)
                ):
                    sessions.setdefault(sid, {})["cwd"] = workspace
                    cached_cwds[sid] = workspace
    except (OSError, ValueError, TypeError, RecursionError):
        pass

    all_logs = glob_under(ANTIGRAVITY_LOG_DIR, "cli-*.log")
    try:
        all_logs.sort(key=os.path.getmtime)
    except OSError:
        all_logs.sort()
    logs = all_logs
    if not show_all:
        recent_logs: list[str] = []
        for path in logs:
            try:
                if is_fresh(now, os.path.getmtime(path), window_hours * 3600):
                    recent_logs.append(path)
            except OSError:
                continue
        logs = recent_logs

    workspace_re = re.compile(r"workspaceDirs=\[(.*?)\]\s+appDataDir=")
    session_re = re.compile(r"(?:Created|Streaming) conversation ([0-9a-fA-F-]{36})")
    forward_re = re.compile(r"Forwarding user message to conversation ([0-9a-fA-F-]{36})")
    prompt_marker = "HandleUserInput called with text: "
    workspace_primaries: dict[str, str] = {}
    events: list[tuple[str, str | None, str | None]] = []

    for path in logs:
        workspace = None
        pending_prompt = None
        for line in antigravity_log_lines(path):
            match = workspace_re.search(line)
            if match:
                workspace = match.group(1).strip() or None
                continue
            match = session_re.search(line)
            if match:
                sid = match.group(1)
                if workspace and sid in cached_cwds:
                    workspace_primaries[workspace] = cached_cwds[sid]
                events.append((sid, workspace, None))
                continue
            if prompt_marker in line:
                raw = line.split(prompt_marker, 1)[1].strip()
                try:
                    decoded = json.loads(raw)
                    pending_prompt = decoded if isinstance(decoded, str) else raw
                except (ValueError, TypeError, RecursionError):
                    pending_prompt = raw.strip('"')
                pending_prompt = notification_text(pending_prompt, 2000)
                continue
            match = forward_re.search(line)
            if match:
                sid = match.group(1)
                if workspace and sid in cached_cwds:
                    workspace_primaries[workspace] = cached_cwds[sid]
                prompt = None
                if pending_prompt:
                    prompt = pending_prompt
                    pending_prompt = None
                events.append((sid, workspace, prompt))

    # last_conversations.json names only the newest session for a workspace.
    # That anchor session can be quiet while a sibling using the same
    # multi-folder context remains active. Recover only its identity from
    # bounded stale-log heads; stale prompts and session events stay excluded.
    missing_contexts = {
        workspace
        for _, workspace, _ in events
        if workspace and workspace not in workspace_primaries
    }
    if missing_contexts and cached_cwds and not show_all:
        recent_paths = set(logs)
        for path in reversed(all_logs):
            if path in recent_paths:
                continue
            workspace = None
            for line in antigravity_log_head_lines(path):
                match = workspace_re.search(line)
                if match:
                    workspace = match.group(1).strip() or None
                    continue
                match = session_re.search(line) or forward_re.search(line)
                if not match:
                    continue
                sid = match.group(1)
                if workspace in missing_contexts and sid in cached_cwds:
                    workspace_primaries[workspace] = cached_cwds[sid]
                    missing_contexts.remove(workspace)
            if not missing_contexts:
                break

    for sid, workspace, prompt in events:
        session = sessions.setdefault(sid, {})
        if workspace:
            session["cwd"] = workspace_primaries.get(workspace, workspace)
        if prompt:
            session["last_prompt"] = prompt
    return sessions


def antigravity_wal_has_data(path: str) -> bool:
    """Whether an Antigravity WAL has content beyond an empty sidecar."""
    with contextlib.suppress(OSError):
        return os.path.getsize(path + "-wal") > 0
    return False


def antigravity_store_mtime(path: str, now: float) -> float:
    """Newest plausible durable activity marker for a conversation store."""
    mtimes: list[float] = []
    with contextlib.suppress(OSError):
        mtimes.append(os.path.getmtime(path))
    if antigravity_wal_has_data(path):
        with contextlib.suppress(OSError):
            mtimes.append(os.path.getmtime(path + "-wal"))
    return newest_plausible(now, mtimes)


def protobuf_fields(payload: Any) -> Iterator[tuple[int, int, Any]]:
    """Yield ``(field_number, wire_type, value)`` from a protobuf message.

    Antigravity persists step metadata as protobuf without shipping Python
    descriptors. This bounded wire reader extracts only the stable scalar and
    length-delimited envelope fields needed by the dashboard. Malformed
    messages raise ``ValueError`` and non-buffer payloads raise ``TypeError``;
    callers skip both.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("protobuf payload must be bytes-like")
    payload = bytes(payload)
    offset = 0

    def read_varint(position: int) -> tuple[int, int]:
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(payload):
                raise ValueError("truncated protobuf varint")
            byte = payload[position]
            position += 1
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                return value, position
        raise ValueError("oversized protobuf varint")

    value: Any  # varint int or a length-delimited/fixed-width bytes slice
    while offset < len(payload):
        key, offset = read_varint(offset)
        number, wire_type = key >> 3, key & 7
        if not number:
            raise ValueError("invalid protobuf field")
        if wire_type == 0:
            value, offset = read_varint(offset)
        elif wire_type == 1:
            if offset + 8 > len(payload):
                raise ValueError("truncated protobuf fixed64")
            value = payload[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            size, offset = read_varint(offset)
            end = offset + size
            if end > len(payload):
                raise ValueError("truncated protobuf bytes")
            value = payload[offset:end]
            offset = end
        elif wire_type == 5:
            if offset + 4 > len(payload):
                raise ValueError("truncated protobuf fixed32")
            value = payload[offset : offset + 4]
            offset += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
        yield number, wire_type, value


def protobuf_first(payload: Any, number: int, wire_type: int) -> Any:
    try:
        for field, wire, value in protobuf_fields(payload):
            if field == number and wire == wire_type:
                return value
    except (ValueError, TypeError):
        pass
    return None


def protobuf_timestamp(payload: Any) -> float:
    seconds = protobuf_first(payload, 1, 0)
    nanos = protobuf_first(payload, 2, 0) or 0
    if not seconds:
        return 0
    return float(seconds + nanos / 1_000_000_000)


def antigravity_step_info(metadata: Any) -> dict[str, Any]:
    """Timestamp, output usage, and tool labels from a step metadata blob."""
    started = protobuf_first(metadata, 1, 2)
    usage = protobuf_first(metadata, 9, 2)
    summary = protobuf_first(metadata, 30, 2)
    action = protobuf_first(metadata, 31, 2)
    output_tokens = protobuf_first(usage, 3, 0) if usage else 0

    def text(value: Any) -> str:
        if not value:
            return ""
        return notification_text(value.decode("utf-8", "replace"), 140)

    return {
        "epoch": protobuf_timestamp(started) if started else 0,
        "output_tokens": output_tokens or 0,
        "tool_summary": text(summary),
        "tool_action": text(action),
    }


def antigravity_step_activity(path: str, now: float) -> dict[str, Any]:
    """Read live rate, turn boundaries, and current action from a store.

    Prefer a plain ``mode=ro`` connection: it sees committed WAL frames, so
    activity from a live Antigravity writer is current. Some stores refuse
    plain read-only opens (e.g. WAL recovery is needed but the reader cannot
    create shm/journal files); for those, fall back to ``immutable=1``, which
    never contends with the writer but may lag until checkpoint. A transient
    or incompatible store simply returns an empty activity snapshot.
    """
    result: dict[str, Any] = {
        "rate_per_min": 0,
        "turns": None,
        "last_tool_action": "",
    }
    if not sqlite_available():
        return result
    query = "SELECT step_type, metadata FROM steps ORDER BY idx DESC LIMIT ?"
    rows = None
    read_error: BaseException | None = None
    for uri in (sqlite_ro_uri(path), sqlite_ro_uri(path, immutable=True)):
        try:
            con = sqlite3.connect(uri, uri=True, timeout=0.2)
        except sqlite3.Error as exc:
            read_error = exc
            continue
        try:
            rows = con.execute(query, (SQL_MSG_LIMIT,)).fetchall()
            break
        except sqlite3.Error as exc:
            read_error = exc
            continue
        finally:
            con.close()
    if rows is None:
        if read_error:
            record_store_error(path, read_error)
        return result

    events = []
    usage_events = []
    last_prompt = 0
    latest_action = (0, "")
    for step_type, metadata in reversed(rows):
        info = antigravity_step_info(metadata)
        epoch = info["epoch"]
        if not epoch:
            continue
        is_prompt = step_type == 14
        events.append((epoch, is_prompt))
        if is_prompt:
            last_prompt = epoch
            latest_action = (0, "")
        if step_type == 15 and info["output_tokens"]:
            usage_events.append((epoch, info["output_tokens"]))
        action = info["tool_action"] or info["tool_summary"]
        if action and epoch >= last_prompt:
            latest_action = (epoch, action)

    recent = sum(tokens for epoch, tokens in usage_events if is_fresh(now, epoch, RATE_WINDOW_SEC))
    result["rate_per_min"] = round(recent / (RATE_WINDOW_SEC / 60))
    result["turns"] = turns_from_events(events) if events else None
    result["last_tool_action"] = latest_action[1]
    return result


def antigravity_session_info(path: str, sid: str) -> dict[str, Any]:
    """Extract parent conversation ID and subagent label from an Antigravity store."""
    info: dict[str, Any] = {"parent_id": None, "subagent_label": None}
    if not sqlite_available():
        return info
    query = "SELECT data FROM trajectory_metadata_blob WHERE id='main'"

    def read_row(uri: str) -> tuple[bool, Any, BaseException | None]:
        try:
            con = sqlite3.connect(uri, uri=True, timeout=0.2)
        except sqlite3.Error as exc:
            return False, None, exc
        try:
            return True, con.execute(query).fetchone(), None
        except sqlite3.Error as exc:
            return False, None, exc
        finally:
            con.close()

    readable, row, read_error = read_row(sqlite_ro_uri(path))
    if not readable and antigravity_wal_has_data(path):
        if read_error:
            record_store_error(path, read_error)
        return info
    if not readable:
        readable, row, fallback_error = read_row(sqlite_ro_uri(path, immutable=True))
        if antigravity_wal_has_data(path):
            if read_error:
                record_store_error(path, read_error)
            return info
        if not readable:
            if fallback_error:
                record_store_error(path, fallback_error)
            return info
    if not readable or not row or not row[0]:
        return info
    data = row[0]

    def text(value: Any) -> str | None:
        if not isinstance(value, (bytes, bytearray, memoryview)):
            return None
        with contextlib.suppress(UnicodeDecodeError):
            return bytes(value).decode("utf-8") or None
        return None

    p5 = text(protobuf_first(data, 5, 2))
    p6 = text(protobuf_first(data, 6, 2))
    parent_id = p5 or (p6 if p6 != sid else None)
    if parent_id:
        info["parent_id"] = parent_id
        f8 = protobuf_first(data, 8, 2)
        labels = (
            text(protobuf_first(f8, 2, 2)),
            text(protobuf_first(f8, 1, 2)),
        )
        info["subagent_label"] = next(
            (
                cleaned
                for label in labels
                if label
                for cleaned in (notification_text(label, 70).strip(),)
                if cleaned
            ),
            None,
        )
    return info


def collect_antigravity(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    metadata = antigravity_session_metadata(now, window_hours, show_all)
    dbs = glob_under(ANTIGRAVITY_CONVERSATIONS_DIR, "*.db")

    agents_by_parent: dict[str, list[tuple[str, str, float]]] = {}
    subagent_sids: set[str] = set()
    db_mtimes: dict[str, float] = {}
    db_paths: dict[str, str] = {}

    for db in dbs:
        sid = os.path.basename(db)[: -len(".db")]
        mtime = antigravity_store_mtime(db, now)
        if not mtime:
            continue
        db_mtimes[sid] = mtime
        db_paths[sid] = db

    pending = [
        sid
        for sid, mtime in db_mtimes.items()
        if show_all or is_fresh(now, mtime, window_hours * 3600)
    ]
    inspected: set[str] = set()
    while pending:
        sid = pending.pop()
        if sid in inspected:
            continue
        inspected.add(sid)
        info = antigravity_session_info(db_paths[sid], sid)
        parent = info.get("parent_id")
        if parent and parent != sid:
            subagent_sids.add(sid)
            label = info.get("subagent_label") or ("subagent " + sid[:8])
            agents_by_parent.setdefault(parent, []).append((sid, label, db_mtimes[sid]))
            if parent in db_paths:
                pending.append(parent)

    def descendants(parent_sid: str) -> list[tuple[str, str, float]]:
        agents: list[tuple[str, str, float]] = []
        pending_agents = list(agents_by_parent.get(parent_sid, []))
        seen: set[str] = set()
        while pending_agents:
            agent_sid, label, mtime = pending_agents.pop()
            if agent_sid in seen or agent_sid == parent_sid:
                continue
            seen.add(agent_sid)
            agents.append((agent_sid, label, mtime))
            pending_agents.extend(agents_by_parent.get(agent_sid, []))
        return agents

    out: list[dict[str, Any]] = []
    for db in dbs:
        sid = os.path.basename(db)[: -len(".db")]
        if sid in subagent_sids:
            continue
        session_mtime = db_mtimes.get(sid)
        if not session_mtime:
            continue
        agents = sorted(descendants(sid), key=lambda a: -a[2])
        activity_sources = (session_mtime, *(mtime for _, _, mtime in agents))
        last_activity = newest_plausible(now, activity_sources)
        active = is_fresh(now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        activity: dict[str, Any] = (
            antigravity_step_activity(db, now)
            if active
            else {"rate_per_min": 0, "turns": None, "last_tool_action": ""}
        )
        if active:
            activity["rate_per_min"] += sum(
                antigravity_step_activity(db_paths[agent_sid], now)["rate_per_min"]
                for agent_sid, _, agent_mtime in agents
                if is_fresh(now, agent_mtime, RATE_WINDOW_SEC)
            )
        subagents = [
            label
            for _, label, agent_mtime in agents
            if is_fresh(now, agent_mtime, WORKING_THRESHOLD_SEC)
        ]
        state, state_detail = "idle", "awaiting your message"
        if is_fresh(now, last_activity, WORKING_THRESHOLD_SEC):
            state = "working"
            state_detail = (
                working_detail(None, subagents)
                if subagents
                else activity["last_tool_action"] or working_detail(None, [])
            )

        meta = metadata.get(sid) or {}
        prompt = str(meta.get("last_prompt") or "").strip()
        cwd = str(meta.get("cwd") or "").strip()
        project = project_from_cwd(cwd) or "antigravity"
        session = base_session("gemini", sid, project)
        session.update(
            {
                "title": prompt.split("\n")[0][:80] or None,
                "last_prompt": prompt[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": activity["rate_per_min"],
                "turn": turn_progress(activity["turns"], state, now),
                "subagents": subagents,
            }
        )
        out.append(session)
    return out


def collect_gemini(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    # Legacy Gemini CLI main sessions:
    # <tmp>/<project>/chats/session-*.jsonl. Subagents:
    # <tmp>/<project>/chats/<safeParentSessionId>/<id>.jsonl — linked to the
    # parent purely by the directory name. Antigravity CLI sessions are
    # appended from its per-conversation SQLite stores below.
    # sanitized parent session id -> [(label, mtime)]
    agents_by_parent: dict[str, list[tuple[str, float]]] = {}
    for fp in glob_stores("gemini.tmp", GEMINI_TMP, "*", "chats", "*", "*.jsonl"):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        if not is_fresh(now, mtime, WORKING_THRESHOLD_SEC):
            continue
        parent = alnum(os.path.basename(os.path.dirname(fp)))
        label = "subagent " + os.path.basename(fp)[:8]
        agents_by_parent.setdefault(parent, []).append((label, mtime))

    sessions: dict[
        str, tuple[float, str]
    ] = {}  # session id (or filename fallback) -> (mtime, path)
    for fp in glob_stores("gemini.tmp", GEMINI_TMP, "*", "chats", "session-*.jsonl"):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        meta = gemini_meta(fp)
        if meta.get("kind") == "subagent":
            continue
        sid = meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")]
        if sid not in sessions or mtime > sessions[sid][0]:
            sessions[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in sessions.items():
        agents = sorted(agents_by_parent.get(alnum(sid), []), key=lambda a: -a[1])
        activity_sources = (mtime, *(m for _, m in agents))
        last_activity = newest_plausible(now, activity_sources)
        active = is_fresh(now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        info = analyze_gemini_transcript(fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, *activity_sources)
        subagents = [label for label, _ in agents]
        state, state_detail = "idle", "awaiting your message"
        if is_fresh(now, newest_plausible(now, last_event_sources), WORKING_THRESHOLD_SEC):
            state = "working"
            state_detail = working_detail(info, subagents)

        cwd = gemini_meta(fp).get("cwd")
        project = project_from_cwd(cwd or "") or project_label(
            os.path.basename(os.path.dirname(os.path.dirname(fp)))
        )
        s = base_session("gemini", sid, project)
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": rate_from(info, now),
                "turn": turn_progress(scan_turns(fp, "gemini") if info else None, state, now),
                "subagents": subagents,
            }
        )
        out.append(s)
    out.extend(collect_antigravity(now, window_hours, show_all))
    return out


def collect_copilot(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    files: dict[
        str, tuple[float, str]
    ] = {}  # session uuid -> newest events.jsonl (dir tie: current)
    # history-session-state is assumed to share the <uuid>/events.jsonl
    # layout — unverified legacy format; a mismatch just means those old
    # sessions stay invisible.
    for base in ("session-state", "history-session-state"):
        for fp in glob_stores("copilot.root", COPILOT_DIR, base, "*", "events.jsonl"):
            sid = os.path.basename(os.path.dirname(fp))
            try:
                mtime = os.path.getmtime(fp)
            except OSError:
                continue
            if sid not in files or mtime > files[sid][0]:
                files[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in files.items():
        active = is_fresh(now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        info = analyze_copilot_events(fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, mtime)
        state, state_detail = "idle", "awaiting your message"
        subagents: list[str] = []
        if is_fresh(now, newest_plausible(now, last_event_sources), WORKING_THRESHOLD_SEC):
            state = "working"
            subagents = list((info or {}).get("pending_agents", {}).values())
            state_detail = working_detail(info, subagents)

        cwd = (info or {}).get("cwd") or copilot_meta(fp).get("cwd")
        s = base_session("copilot", sid, project_from_cwd(cwd or "") or "copilot")
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
                "turn": turn_progress(scan_turns(fp, "copilot") if info else None, state, now),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out


def _sql_ro(path: str) -> sqlite3.Connection:
    """Read-only SQLite connection that never blocks a live agent's writes.

    Deliberately no ``immutable=1`` fallback: these are databases a live agent
    is still writing, and SQLite documents that opening a changing database as
    immutable can return incorrect results or SQLITE_CORRUPT. A failure here is
    reported, not silently downgraded.
    """
    con = sqlite3.connect(sqlite_ro_uri(path), uri=True, timeout=0.2)
    con.row_factory = sqlite3.Row
    return con


def collect_opencode(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    if not sqlite_available():
        return []
    out: list[dict[str, Any]] = []
    for db in glob_stores("opencode.data", OPENCODE_DATA, "opencode*.db"):
        try:
            con = _sql_ro(db)
        except sqlite3.Error as exc:
            record_store_error(db, exc)
            continue
        # ?all=1 promises every session ever; LIMIT -1 is SQLite's "no limit".
        limit = -1 if show_all else 200
        try:
            try:
                rows = con.execute(
                    "SELECT id, parent_id, directory, title, time_updated, time_archived "
                    "FROM session ORDER BY time_updated DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            except sqlite3.OperationalError:  # older schema without time_archived
                rows = con.execute(
                    "SELECT id, parent_id, directory, title, time_updated, "
                    "NULL AS time_archived FROM session "
                    "ORDER BY time_updated DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except sqlite3.Error as exc:
            record_store_error(db, exc)
            con.close()
            continue
        try:
            children: dict[
                Any, list[tuple[str, float]]
            ] = {}  # parent session id -> [(title, epoch)]
            tops: list[tuple[Any, float]] = []
            for r in rows:
                if r["time_archived"]:
                    continue  # archival bumps time_updated; don't ghost as working
                upd = norm_epoch(r["time_updated"])
                if r["parent_id"]:
                    if is_fresh(now, upd, WORKING_THRESHOLD_SEC):
                        children.setdefault(r["parent_id"], []).append(
                            ((r["title"] or "subagent")[:70], upd)
                        )
                else:
                    tops.append((r, upd))
            for r, upd in tops:
                agents = sorted(children.get(r["id"], []), key=lambda a: -a[1])
                activity_sources = (upd, *(m for _, m in agents))
                last_activity = newest_plausible(now, activity_sources)
                active = is_fresh(now, last_activity, window_hours * 3600)
                if not (active or show_all):
                    continue
                subagents = [label for label, _ in agents]
                state, state_detail = "idle", "awaiting your message"
                if is_fresh(now, last_activity, WORKING_THRESHOLD_SEC):
                    state = "working"
                    state_detail = working_detail(None, subagents)

                turn = None
                last_prompt = ""
                if active:
                    events = []
                    try:
                        # The message kind lives in the `type` COLUMN (tagged
                        # union discriminator); `data` omits type/id and holds
                        # the prompt in data.text.
                        msgs = con.execute(
                            "SELECT type, time_created, data FROM session_message "
                            "WHERE session_id = ? ORDER BY time_created DESC LIMIT ?",
                            (r["id"], SQL_MSG_LIMIT),
                        ).fetchall()
                        for m in reversed(msgs):
                            is_user = m["type"] == "user"
                            events.append((norm_epoch(m["time_created"]), is_user))
                            if is_user:
                                try:
                                    jd = json.loads(m["data"] or "{}")
                                except (ValueError, TypeError):
                                    jd = {}
                                last_prompt = extract_text(jd)[:140] or last_prompt
                    except sqlite3.Error:
                        pass
                    turn = turn_progress(turns_from_events(events), state, now)

                s = base_session(
                    "opencode", r["id"], project_from_cwd(r["directory"] or "") or "opencode"
                )
                s.update(
                    {
                        "title": (r["title"] or "").strip()[:80] or None,
                        "last_prompt": last_prompt,
                        "state": state,
                        "state_detail": state_detail,
                        "active": active,
                        "last_activity": last_activity,
                        "turn": turn,
                        "subagents": subagents,
                    }
                )
                out.append(s)
        finally:
            con.close()
    return out


# db path -> (mtime, title, cwd)
_cursor_meta_cache: dict[str, tuple[float, str | None, str]] = {}

# Cursor does not document its meta payload, so the workspace path is read by
# trying the plausible spellings, in this order of trust. A miss leaves the row
# on the harness-name fallback, which is what every Cursor row showed before.
#
# The spellings are inferred from the VS Code lineage, not observed in a store,
# so a shape check is not enough on its own: "workspace" in that family often
# holds a .code-workspace *file*, and workspaceStorage/<hash> paths are
# everywhere in its chat storage. Either would produce a confident wrong label,
# which is worse than the fallback. So a candidate is accepted only if it
# resolves to a directory that exists here — a guess that validates itself.
_CURSOR_CWD_KEYS = ("workspacePath", "workspace", "rootPath", "projectPath", "folder", "cwd")
_ABS_PATH_RE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
_CURSOR_META_ROWS = 50  # a key/value table; the workspace need not be in row 1-5


def _cursor_workspace(value: Any) -> str:
    """A meta value promoted to a workspace path, or ``""``.

    Accepts the ``file://`` URI form as well as a bare path: that is the
    canonical serialization in the VS Code family, and rejecting it would make
    the whole read a silent no-op that looks identical to "Cursor records no
    workspace".
    """
    if not isinstance(value, str) or not value:
        return ""
    if value.startswith("file://"):
        parsed = urlparse(value)
        if parsed.netloc:  # file://server/share is a UNC path, not a local dir
            return ""
        value = unquote(parsed.path)
        # file:///C:/x parses to /C:/x; ntpath cannot read that spelling.
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", value):
            value = value[1:]
    if not _ABS_PATH_RE.match(value):
        return ""
    try:
        return value if os.path.isdir(value) else ""
    except OSError:
        return ""


def _cursor_meta(db: str, mtime: float) -> tuple[str | None, str]:
    """(session name, workspace path) from the meta table: hex-encoded UTF-8
    JSON (some versions store plain JSON; value may be NULL or non-text).
    mode=ro (not immutable) so names still in the WAL are visible. Memoized by
    mtime — both are stable, so no per-refresh reopen."""
    with _cache_lock:
        hit = _cursor_meta_cache.get(db)
    if hit and hit[0] == mtime:
        return hit[1], hit[2]
    title = None
    cwd_by_key: dict[str, str] = {}
    try:
        con = sqlite3.connect(sqlite_ro_uri(db), uri=True, timeout=0.2)
    except sqlite3.Error as exc:
        record_store_error(db, exc)
        return None, ""
    failed = False
    try:
        rows = con.execute("SELECT value FROM meta LIMIT ?", (_CURSOR_META_ROWS,)).fetchall()
    except sqlite3.Error as exc:
        record_store_error(db, exc)
        rows, failed = [], True
    finally:
        con.close()
    for (raw,) in rows:
        v = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not isinstance(v, str):
            continue
        candidates = [v]  # plain JSON first: a hex string can't parse to a dict
        with contextlib.suppress(ValueError):
            candidates.append(bytes.fromhex(v).decode("utf-8", "replace"))
        for decoded in candidates:
            try:
                d = json.loads(decoded)
            except (ValueError, TypeError):
                continue
            if not isinstance(d, dict):
                continue
            if not title:
                # Untyped JSON from disk: a non-string name must not
                # AttributeError the whole Cursor collector. Take the first
                # value that is actually a string rather than the first that
                # is merely truthy, or a numeric "name" shadows a good "title".
                name = next(
                    (
                        v.strip()
                        for v in (d.get("name"), d.get("title"))
                        if isinstance(v, str) and v.strip()
                    ),
                    "",
                )
                if name:
                    title = name[:80]
            # Keyed by spelling, not by first-seen: the keys are ranked by
            # trust, and a payload may spread them across rows, so a later row
            # holding a better-trusted key must still win.
            for key in _CURSOR_CWD_KEYS:
                if key in cwd_by_key:
                    continue
                workspace = _cursor_workspace(d.get(key))
                if workspace:
                    cwd_by_key[key] = workspace
        if title and _CURSOR_CWD_KEYS[0] in cwd_by_key:
            break  # best-trusted key already found; nothing later can beat it
    cwd = next((cwd_by_key[k] for k in _CURSOR_CWD_KEYS if k in cwd_by_key), "")
    if failed:
        # Transient: do not cache values the query never returned.
        return None, ""
    with _cache_lock:
        hit = _cursor_meta_cache.get(db)
        if hit and hit[0] == mtime:
            return hit[1], hit[2]
        bounded_put(_cursor_meta_cache, db, (mtime, title, cwd))
        return title, cwd


def collect_cursor(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    if not sqlite_available():
        return []
    # One store.db per chat; content is opaque-ish (hex JSON blobs), so
    # Cursor rows are discovery + state + title only — no turn ETA.
    out: list[dict[str, Any]] = []
    for db in glob_stores("cursor.chats", CURSOR_CHATS, "*", "*", "store.db"):
        sid = os.path.basename(os.path.dirname(db))
        try:
            mtime = os.path.getmtime(db)
            wal = db + "-wal"
            if os.path.exists(wal):
                mtime = max(mtime, os.path.getmtime(wal))
        except OSError:
            continue
        active = is_fresh(now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        state, state_detail = "idle", "awaiting your message"
        if is_fresh(now, mtime, WORKING_THRESHOLD_SEC):
            state, state_detail = "working", "generating…"
        title, cwd = _cursor_meta(db, mtime)
        s = base_session("cursor", sid, project_from_cwd(cwd) or "cursor")
        s.update(
            {
                "title": title if active else None,
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
            }
        )
        out.append(s)
    return out


def goose_user_prompt(content: Any) -> bool:
    """Return whether a Goose role=user message came from the human.

    Goose also records tool results with role=user; those entries carry a
    toolResponse content part and must not start a new turn.
    """
    if not isinstance(content, list):
        return True
    return not any(
        isinstance(part, dict) and alnum(part.get("type")) == "toolresponse" for part in content
    )


def collect_goose(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    if not sqlite_available():
        return []
    # Goose keeps its store in a different place per platform, so scan every
    # candidate that exists rather than betting on one.
    out: list[dict[str, Any]] = []
    for db in existing_stores("goose.db", GOOSE_DB):
        out.extend(collect_goose_db(db, now, window_hours, show_all))
    return out


def collect_goose_db(
    goose_db: str, now: float, window_hours: float, show_all: bool
) -> list[dict[str, Any]]:
    # Single shared sessions.db (v1.10.0+): per-session activity comes from
    # the updated_at column, NOT file mtime (the DB is shared by all
    # sessions). Legacy per-session .jsonl files are not supported.
    try:
        con = _sql_ro(goose_db)
    except sqlite3.Error as exc:
        record_store_error(goose_db, exc)
        return []
    try:
        try:
            rows = con.execute(
                "SELECT id, description, working_dir, updated_at, "
                "session_type, parent_session_id, archived_at FROM sessions"
            ).fetchall()
        except sqlite3.OperationalError:  # older schema without those columns
            rows = con.execute(
                "SELECT id, description, working_dir, updated_at, "
                "NULL AS session_type, NULL AS parent_session_id, "
                "NULL AS archived_at FROM sessions"
            ).fetchall()

        children: dict[Any, list[tuple[str, float]]] = {}  # parent session id -> [(label, epoch)]
        tops: list[tuple[Any, float]] = []
        for r in rows:
            if r["archived_at"]:
                continue  # archival bumps updated_at; don't resurrect
            upd = parse_utc_sql(r["updated_at"])
            stype = alnum(r["session_type"])
            if stype == "subagent":
                if r["parent_session_id"] and is_fresh(now, upd, WORKING_THRESHOLD_SEC):
                    children.setdefault(r["parent_session_id"], []).append(
                        ((r["description"] or "subagent")[:70], upd)
                    )
                continue
            if stype in ("hidden", "terminal", "gateway", "acp"):
                continue  # infrastructure sessions goose's own list hides
            tops.append((r, upd))

        out: list[dict[str, Any]] = []
        for r, upd in tops:
            agents = sorted(children.get(r["id"], []), key=lambda a: -a[1])
            activity_sources = (upd, *(m for _, m in agents))
            last_activity = newest_plausible(now, activity_sources)
            active = is_fresh(now, last_activity, window_hours * 3600)
            if not (active or show_all):
                continue
            subagents = [label for label, _ in agents]
            state, state_detail = "idle", "awaiting your message"
            if is_fresh(now, last_activity, WORKING_THRESHOLD_SEC):
                state = "working"
                state_detail = working_detail(None, subagents)

            turn = None
            last_prompt = ""
            rate = 0
            if active:
                events = []
                try:
                    msgs = con.execute(
                        "SELECT role, created_timestamp, content_json FROM messages "
                        "WHERE session_id = ? ORDER BY created_timestamp DESC LIMIT ?",
                        (r["id"], SQL_MSG_LIMIT),
                    ).fetchall()
                    for m in reversed(msgs):
                        ep = norm_epoch(m["created_timestamp"])
                        try:
                            content = json.loads(m["content_json"] or "[]")
                        except (ValueError, TypeError, RecursionError):
                            content = []
                        is_prompt = m["role"] == "user" and goose_user_prompt(content)
                        events.append((ep, is_prompt))
                        if is_prompt:
                            last_prompt = extract_text(content)[:140] or last_prompt
                except sqlite3.Error:
                    pass
                try:
                    # Token accounting lives in usage_ledger, NOT messages.tokens
                    # (goose never writes that column).
                    led = con.execute(
                        "SELECT created_timestamp, output_tokens FROM usage_ledger "
                        "WHERE session_id = ? ORDER BY created_timestamp DESC LIMIT 200",
                        (r["id"],),
                    ).fetchall()
                    recent = sum(
                        (x["output_tokens"] or 0)
                        for x in led
                        if is_fresh(now, norm_epoch(x["created_timestamp"]), RATE_WINDOW_SEC)
                    )
                    rate = round(recent / (RATE_WINDOW_SEC / 60))
                except sqlite3.Error:
                    pass
                turn = turn_progress(turns_from_events(events), state, now)

            s = base_session("goose", r["id"], project_from_cwd(r["working_dir"] or "") or "goose")
            s.update(
                {
                    "title": (r["description"] or "").strip()[:80] or None,
                    "last_prompt": last_prompt,
                    "state": state,
                    "state_detail": state_detail,
                    "active": active,
                    "last_activity": last_activity,
                    "rate_per_min": rate,
                    "turn": turn,
                    "subagents": subagents,
                }
            )
            out.append(s)
    except sqlite3.Error as exc:
        record_store_error(goose_db, exc)
        return []
    else:
        return out
    finally:
        con.close()


def collect_droid(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fp in glob_stores("droid.projects", FACTORY_PROJECTS, "*", "*.jsonl"):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        active = is_fresh(now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        meta = droid_meta(fp)
        sid = str(meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")])
        info = analyze_droid_transcript(fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, mtime)
        state, state_detail = "idle", "awaiting your message"
        if is_fresh(now, newest_plausible(now, last_event_sources), WORKING_THRESHOLD_SEC):
            state = "working"
            state_detail = working_detail(info, [])

        project = project_from_cwd(meta.get("cwd") or "") or project_label(
            os.path.basename(os.path.dirname(fp))
        )
        s = base_session("droid", sid, project)
        s.update(
            {
                "title": (meta.get("title") or "").strip()[:80] or (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
                "turn": turn_progress(scan_turns(fp, "droid") if info else None, state, now),
            }
        )
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# Harness registry — a harness appears in the dashboard only if discovered


HARNESSES: list[
    tuple[str, str, Callable[[], bool], Callable[[float, float, bool], list[dict[str, Any]]]]
] = [
    ("claude", "Claude", lambda: any_store_dir("claude.projects", PROJECTS_DIR), collect_claude),
    ("codex", "Codex", lambda: any_store_dir("codex.sessions", CODEX_SESSIONS_DIR), collect_codex),
    ("pi", "Pi", discover_pi, collect_pi),
    # Predicate matches both supported Gemini stores: legacy Gemini CLI
    # JSONL and current Antigravity CLI per-conversation SQLite databases.
    (
        "gemini",
        "Gemini",
        lambda: bool(
            glob_stores("gemini.tmp", GEMINI_TMP, "*", "chats", "session-*.jsonl")
            # Antigravity discovery needs no sqlite3: identity and working/idle
            # come from store mtime and the CLI logs. Only the token rate and
            # turn ETA read the database, and those degrade to zero without it.
            or glob_under(ANTIGRAVITY_CONVERSATIONS_DIR, "*.db")
        ),
        collect_gemini,
    ),
    (
        "copilot",
        "Copilot",
        lambda: (
            any_store_dir("copilot.root", COPILOT_DIR, "session-state")
            or any_store_dir("copilot.root", COPILOT_DIR, "history-session-state")
        ),
        collect_copilot,
    ),
    (
        "opencode",
        "OpenCode",
        lambda: (
            sqlite_available() and bool(glob_stores("opencode.data", OPENCODE_DATA, "opencode*.db"))
        ),
        collect_opencode,
    ),
    (
        "cursor",
        "Cursor",
        lambda: (
            sqlite_available()
            and bool(glob_stores("cursor.chats", CURSOR_CHATS, "*", "*", "store.db"))
        ),
        collect_cursor,
    ),
    (
        "goose",
        "Goose",
        lambda: sqlite_available() and bool(existing_stores("goose.db", GOOSE_DB)),
        collect_goose,
    ),
    (
        "droid",
        "Droid",
        lambda: bool(glob_stores("droid.projects", FACTORY_PROJECTS, "*", "*.jsonl")),
        collect_droid,
    ),
]


def collect(window_hours: float, show_all: bool) -> dict[str, Any]:
    now = time.time()
    out_sessions: list[dict[str, Any]] = []
    harnesses: list[dict[str, Any]] = []
    for key, label, discover, collector in HARNESSES:
        try:
            found = bool(discover())
        except OSError:
            found = False
        harness: dict[str, Any] = {
            "key": key,
            "label": label,
            "discovered": found,
            "error": None,
        }
        harnesses.append(harness)
        if not found:
            continue
        try:
            out_sessions.extend(collector(now, window_hours, show_all))
        except Exception as e:  # noqa: BLE001 — one broken harness must not take down the rest
            harness["error"] = f"{type(e).__name__}: {e}"
            diag(f"[{key}] collector error: {harness['error']}")

    out_sessions = dedupe_sessions(out_sessions)
    assign_display_ids(out_sessions)
    state_rank = {"needs_input": 0, "working": 1, "idle": 2}
    # Session id as tiebreaker (not last_activity) so rows don't reshuffle
    # on every refresh while sessions are generating.
    out_sessions.sort(key=lambda x: (state_rank.get(x["state"], 3), x["sid"]))
    active_sessions = [x for x in out_sessions if x["active"]]
    total_tasks = sum(x["total"] for x in out_sessions)
    total_done = sum(x["done"] for x in out_sessions)
    return {
        "generated": now,
        "window_hours": window_hours,
        "show_all": show_all,
        # Which layer owns needs-input popups. Empty means the page should
        # raise its own; a backend name means the server already did.
        "native_notify": native_notifier(sys.platform),
        "harnesses": harnesses,
        "summary": {
            "needs_input": sum(1 for x in active_sessions if x["state"] == "needs_input"),
            "working": sum(1 for x in active_sessions if x["state"] == "working"),
            "rate_per_min": sum(x["rate_per_min"] for x in active_sessions),
            "active_sessions": len(active_sessions),
            "open_tasks": sum(x["open"] for x in out_sessions),
            "progress_pct": round(total_done * 100 / total_tasks) if total_tasks else 0,
            "total_tasks": total_tasks,
            "total_done": total_done,
        },
        "sessions": out_sessions,
    }


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cargento</title>
<style>
  :root{
    --bg:#f6f3ec; --panel:#fffdf8; --ink:#26241d; --ink2:#57534a; --ink3:#8f897c;
    --line:#e6e0d3; --accent:oklch(0.80 0.16 122); --alert:oklch(0.55 0.19 27);
    --sans:'Space Grotesk',system-ui,-apple-system,sans-serif; --mono:'Space Mono',ui-monospace,monospace;
    /* calm mode: a sunk surface below --bg, a heavier rule than --line, and a
       second flag tone for "worth a look" as distinct from --alert's "act now" */
    --sunk:#f0ece2; --line2:#cfc7b5; --accent-ink:oklch(0.34 0.07 130);
    --warn:oklch(0.74 0.11 78); --warnink:oklch(0.50 0.09 70);
  }
  @media (prefers-color-scheme:dark){
    :root{
      --bg:#1a1916; --panel:#222019; --ink:#efece3; --ink2:#b3ad9f; --ink3:#7c7669;
      --line:#302d25; --accent:oklch(0.84 0.17 122); --alert:oklch(0.72 0.17 27);
      --sunk:#161512; --line2:#463f33; --accent-ink:oklch(0.86 0.10 128);
      --warn:oklch(0.78 0.11 78); --warnink:oklch(0.80 0.10 76);
    }
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--bg);color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  a{color:var(--ink)}
  .wrap{max-width:1180px;margin:0 auto;padding:34px 30px 64px;display:flex;flex-direction:column;gap:26px}
  @keyframes pulse{50%{opacity:.32}}
  @keyframes livebar{0%{transform:translateX(-140%)}100%{transform:translateX(320%)}}

  /* header */
  .top{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;flex-wrap:wrap}
  .brand{font-size:32px;font-weight:700;letter-spacing:-.025em;line-height:1}
  .sub{font-family:var(--mono);font-size:12px;color:var(--ink3);margin-top:10px;display:flex;align-items:center;gap:8px}
  .live{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 1.6s infinite}
  .live.stalled{background:var(--alert);animation:none}
  .notify-btn{font-family:var(--mono);font-size:11px;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:3px 10px;margin-left:4px;cursor:pointer;transition:background .15s}
  .notify-btn:hover{background:var(--line)}
  .notify-btn:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .notify-note{font-family:var(--mono);font-size:11px;color:var(--ink3);margin-left:4px;cursor:help;border-bottom:1px dotted var(--line)}
  .hstrip{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end;max-width:440px}
  .hstrip-k{font-family:var(--mono);font-size:10px;color:var(--ink3);text-transform:uppercase;letter-spacing:.1em;margin-right:3px}

  /* harness badges */
  .hbadge{position:relative;display:inline-flex}
  .btile{width:24px;height:24px;border-radius:7px;display:inline-flex;align-items:center;justify-content:center;flex:none}
  .bico{width:14px;height:14px;display:block}
  .bmono{font-family:var(--mono);font-size:9.5px;font-weight:700}
  .hstrip .btile{width:26px;height:26px;border-radius:8px}
  .hstrip .bico{width:15px;height:15px}
  .hstrip .bmono{font-size:10px}
  .hbadge .htip{position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%) translateY(3px);opacity:0;pointer-events:none;transition:opacity .14s ease,transform .14s ease;white-space:nowrap;z-index:40;font-family:var(--mono);font-size:11px;font-weight:500;color:var(--bg);background:var(--ink);padding:5px 9px;border-radius:7px;box-shadow:0 6px 18px -6px rgba(0,0,0,.5)}
  .hbadge:hover .htip{opacity:1;transform:translateX(-50%) translateY(0)}

  /* hero tiles */
  .hero{display:grid;grid-template-columns:1fr 1fr 1.35fr;gap:16px}
  .tile{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:20px 22px}
  .tile-label{font-size:13px;color:var(--ink2);font-weight:500}
  .tile-val{font-size:44px;font-weight:700;letter-spacing:-.03em;line-height:1.05;margin:6px 0 2px;font-variant-numeric:tabular-nums}
  .tile-val.alert{color:var(--alert)}
  .tile-sub{font-family:var(--mono);font-size:11.5px;color:var(--ink3)}
  .tile-top{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
  .tile-cap{font-family:var(--mono);font-size:10.5px;color:var(--ink3);text-transform:uppercase;letter-spacing:.06em}
  .rate-rows{display:flex;flex-direction:column;gap:7px;margin-top:8px}
  .rrow{display:flex;align-items:center;gap:10px}
  .rrow-badge{width:26px;display:flex;align-items:center;justify-content:center;flex:none}
  .rrow-bar{flex:1;height:5px;border-radius:3px;background:var(--line);overflow:hidden}
  .rrow-fill{display:block;height:100%;border-radius:3px;background:var(--accent)}
  .rrow-v{font-family:var(--mono);font-size:11px;color:var(--ink2);width:46px;text-align:right;font-variant-numeric:tabular-nums}
  .spark-wrap{position:relative;margin:12px 0 4px;outline:none;cursor:crosshair;border-radius:6px}
  .spark-wrap:focus-visible{box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .spark-wrap svg{display:block;width:100%;height:46px}
  .spark-dot{position:absolute;width:8px;height:8px;border-radius:50%;background:var(--accent);border:2px solid var(--panel);transform:translate(-50%,-50%);pointer-events:none}
  .spark-x{position:absolute;top:0;bottom:0;width:1px;background:var(--ink3);opacity:0;pointer-events:none;transition:opacity .12s}
  .spark-tip{position:absolute;bottom:calc(100% + 7px);transform:translateX(-50%);opacity:0;pointer-events:none;white-space:nowrap;font-family:var(--mono);font-size:11px;color:var(--bg);background:var(--ink);padding:4px 9px;border-radius:6px;z-index:30;transition:opacity .12s}
  .spark-tip b{font-weight:700}
  .rate-flex{display:flex;align-items:center;justify-content:flex-end;gap:10px}
  .rate-spark svg{display:block;width:84px;height:26px}
  .subnote{display:flex;gap:22px;margin-top:-12px;font-family:var(--mono);font-size:11.5px;color:var(--ink3);align-items:center;flex-wrap:wrap}
  .subnote b{color:var(--ink2);font-weight:700}
  .subnote .div{width:1px;height:11px;background:var(--line)}

  /* needs-input band */
  .band{border:1px solid color-mix(in oklab,var(--alert) 42%,var(--line));background:color-mix(in oklab,var(--alert) 7%,var(--panel));border-radius:20px;padding:20px 24px;display:flex;flex-direction:column;gap:16px}
  .band-head{display:flex;align-items:center;gap:9px}
  .band-dot{width:8px;height:8px;border-radius:50%;background:var(--alert);animation:pulse 1.1s infinite}
  .band-k{font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--alert)}
  .need{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}
  .need-meta{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-family:var(--mono);font-size:12px;color:var(--ink3)}
  .need-title{font-size:19px;font-weight:600;line-height:1.3;letter-spacing:-.01em}
  .need-detail{font-size:13px;color:var(--ink2);margin-top:5px}
  .blocked-k{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink3);text-align:right}
  .blocked-v{font-family:var(--mono);font-size:24px;font-weight:700;color:var(--alert);line-height:1.1;text-align:right}

  /* section head */
  .sec{display:flex;align-items:center;gap:10px}
  .sec-k{font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--ink2)}
  .sec-count{font-family:var(--mono);font-size:11px;color:var(--ink3)}
  .sec-rule{flex:1;height:1px;background:var(--line)}
  .stack{display:flex;flex-direction:column;gap:14px}

  /* working card */
  .card{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:22px 24px;display:flex;flex-direction:column;gap:15px}
  .card-top{display:flex;align-items:flex-start;gap:16px}
  .card-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:11px}
  .card-headrow{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
  .pill{display:inline-flex;align-items:center;gap:7px;padding:4px 11px 4px 9px;border-radius:999px;font-size:12px;font-weight:600}
  .pill-work{background:color-mix(in oklab,var(--accent) 18%,transparent);color:var(--ink)}
  .pill-dot{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 1.5s infinite}
  .card-title{font-size:20px;font-weight:600;line-height:1.25;letter-spacing:-.012em}
  .card-meta{font-family:var(--mono);font-size:12.5px;color:var(--ink3)}
  .card-bits{font-family:var(--mono);font-size:11.5px;color:var(--ink2);margin-top:-4px}
  .rate-meter{text-align:right;flex:none}
  .rate-num{font-family:var(--mono);font-size:23px;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums;line-height:1}
  .rate-lab{font-family:var(--mono);font-size:10px;color:var(--ink3);text-transform:uppercase;letter-spacing:.08em;margin-top:3px}
  .rate-track{margin-top:8px;width:100px;height:4px;border-radius:2px;background:var(--line);overflow:hidden;margin-left:auto;position:relative}
  .rate-live{position:absolute;top:0;bottom:0;width:34%;background:var(--accent);border-radius:2px;animation:livebar 2.4s linear infinite}
  .now{font-size:13.5px;color:var(--ink2)}
  .now-k{font-family:var(--mono);font-size:11px;color:var(--ink3);text-transform:uppercase;letter-spacing:.08em;margin-right:9px}
  .turn{display:flex;flex-direction:column;gap:9px}
  .turn-row{display:flex;align-items:center;justify-content:space-between;gap:12px}
  .turn-txt{font-family:var(--mono);font-size:12px;color:var(--ink2)}
  .turn-right{display:flex;align-items:center;gap:9px}
  .pct{font-family:var(--mono);font-size:14px;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums}
  .turnbar{height:9px;border-radius:5px;background:var(--line);overflow:hidden}
  .turnfill{display:block;height:100%;border-radius:5px;background:var(--accent)}
  .lwarn{position:relative;display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;border-radius:50%;background:color-mix(in oklab,var(--alert) 18%,transparent);color:var(--alert);font-family:var(--mono);font-weight:700;font-size:12px;cursor:help;outline:none}
  .lwarn:focus-visible{box-shadow:0 0 0 2px color-mix(in oklab,var(--alert) 45%,transparent)}
  .lwarn .ltip{position:absolute;bottom:calc(100% + 8px);right:-6px;width:max-content;max-width:250px;white-space:normal;text-align:left;opacity:0;pointer-events:none;transform:translateY(3px);transition:opacity .14s ease,transform .14s ease;font-family:var(--mono);font-size:11px;font-weight:500;line-height:1.5;color:var(--bg);background:var(--ink);padding:7px 10px;border-radius:8px;box-shadow:0 6px 18px -6px rgba(0,0,0,.5);z-index:40}
  .lwarn:hover .ltip,.lwarn:focus-visible .ltip{opacity:1;transform:translateY(0);transition-delay:.2s}
  .subs{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
  .subs-k{font-family:var(--mono);font-size:10.5px;color:var(--ink3);text-transform:uppercase;letter-spacing:.08em}
  .subpill{display:inline-flex;align-items:center;gap:7px;padding:4px 12px;border-radius:999px;background:color-mix(in oklab,var(--accent) 13%,transparent);border:1px solid color-mix(in oklab,var(--accent) 30%,transparent);font-size:12px;color:var(--ink)}
  .subdot{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:pulse 1.6s infinite}
  .sd{display:flex;flex-direction:column;gap:6px;border-top:1px solid var(--line);padding-top:11px}
  .sd-k{font-family:var(--mono);font-size:10.5px;color:var(--ink3);text-transform:uppercase;letter-spacing:.08em}
  .sd-role{font-family:var(--mono);font-size:10.5px;color:var(--ink2);margin-left:8px}
  .sd-row{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;min-width:0}
  .sd-ent{font-family:var(--mono);font-size:11.5px;color:var(--ink2);max-width:22ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .sd-live{color:var(--ink);font-weight:600}
  .sd-cyc{font-family:var(--mono);font-size:10px;color:var(--ink3);padding:1px 6px;border-radius:999px;border:1px solid var(--line)}
  .sd-spine{display:flex;align-items:center;gap:5px;flex-wrap:wrap;font-size:11.5px;min-width:0}
  .sd-st{color:var(--ink3)}
  .sd-cur{color:var(--ink);font-weight:600;padding:1px 8px;border-radius:999px;background:color-mix(in oklab,var(--accent) 16%,transparent);border:1px solid color-mix(in oklab,var(--accent) 34%,transparent)}
  .sd-arr{color:var(--ink3);font-size:10px}
  .sd-gap{color:var(--ink3)}
  .no-tasks{font-family:var(--mono);font-size:11.5px;color:var(--ink3);border-top:1px solid var(--line);padding-top:13px}
  .tasks{display:flex;flex-direction:column;border-top:1px solid var(--line)}
  .task{display:flex;align-items:flex-start;gap:12px;padding:11px 0;border-bottom:1px solid var(--line)}
  .task:last-child{border-bottom:none;padding-bottom:0}
  .task-body{flex:1;min-width:0}
  .task-subj{font-size:14px;font-weight:520}
  .task-af{font-family:var(--mono);font-size:11.5px;color:var(--ink3);margin-top:2px}
  .task-when{font-family:var(--mono);font-size:11px;color:var(--ink3);white-space:nowrap;text-align:right}
  .tstatus{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap}
  .tstatus::before{content:"";width:6px;height:6px;border-radius:50%}
  .st-in_progress{background:color-mix(in oklab,var(--accent) 18%,transparent);color:var(--ink)}
  .st-in_progress::before{background:var(--accent);animation:pulse 1.5s infinite}
  .st-completed{background:color-mix(in oklab,var(--ink3) 18%,transparent);color:var(--ink2)}
  .st-completed::before{background:var(--ink3)}
  .st-pending{background:color-mix(in oklab,var(--ink3) 12%,transparent);color:var(--ink3)}
  .st-pending::before{background:var(--ink3)}

  /* idle */
  .idle-wrap{position:relative}
  .idle-clip{position:relative;overflow:hidden;transition:max-height .5s cubic-bezier(.4,0,.2,1)}
  .idle-row{display:flex;align-items:center;gap:14px;padding:13px 4px;border-bottom:1px solid var(--line)}
  .idle-dot{width:6px;height:6px;border-radius:50%;background:var(--ink3);flex:none;opacity:.6}
  .idle-title{font-weight:500;font-size:14px;color:var(--ink);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .idle-proj{font-family:var(--mono);font-size:12px;color:var(--ink3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:240px}
  .idle-age{font-family:var(--mono);font-size:12px;color:var(--ink3);white-space:nowrap;width:74px;text-align:right;flex:none}
  .idle-fade{position:absolute;left:0;right:0;bottom:0;height:110px;background:linear-gradient(to bottom,transparent,var(--bg));pointer-events:none}
  .idle-toggle-wrap{display:flex;justify-content:center;margin-top:-16px;position:relative;z-index:2}
  .idle-toggle{font-family:var(--mono);font-size:11.5px;font-weight:700;letter-spacing:.04em;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:9px 20px;cursor:pointer;box-shadow:0 4px 14px -4px rgba(0,0,0,.25);transition:background .15s}
  .idle-toggle:hover{background:var(--line)}

  .empty{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:36px;text-align:center;color:var(--ink2);font-size:14px}
  .empty a{font-weight:600}

  /* display-mode switch — present in both modes, top right */
  .modebar{display:flex;align-items:center;justify-content:flex-end;gap:12px}
  .wrap:not(.calm) .modebar{margin-bottom:-20px}
  .modebar-k{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--ink3)}
  .modeseg{display:flex;align-items:center;gap:2px;padding:2px;border-radius:9px;border:1px solid var(--line);background:var(--bg)}
  .modebtn{font-family:var(--mono);font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:5px 13px;border:0;border-radius:7px;cursor:pointer;color:var(--ink3);background:transparent;transition:color .12s,background .12s}
  .modebtn:hover{color:var(--ink2)}
  .modebtn.on{color:var(--ink);background:var(--panel);box-shadow:0 1px 3px -1px rgba(0,0,0,.22)}
  .modebtn:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .stopbtn{font-family:var(--mono);font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:5px 12px;border:1px solid var(--line);border-radius:9px;cursor:pointer;color:var(--ink3);background:var(--bg);transition:color .12s,background .12s,border-color .12s}
  .stopbtn:hover{color:var(--ink2)}
  .stopbtn.armed{color:var(--alert);border-color:color-mix(in oklab,var(--alert) 45%,transparent);background:color-mix(in oklab,var(--alert) 12%,transparent)}
  .stopbtn:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .stopnote{font-family:var(--mono);font-size:10.5px;color:var(--alert);margin-left:6px}
  .stopped{margin:72px auto;max-width:440px;display:flex;flex-direction:column;gap:10px;text-align:center;font-family:var(--mono)}
  .stopped-h{font-size:15px;font-weight:700;color:var(--ink)}
  .stopped-p{font-size:12px;color:var(--ink3);line-height:1.65}

  /* calm mode — one dense ledger row per session, in a fixed frame that
     scrolls internally so the chrome never leaves the screen */
  .wrap.calm{max-width:1332px;padding:24px 26px 30px;gap:12px}
  .cm-frame{--cmcols:3px 22px minmax(0,1fr) 176px 156px 100px 46px 92px 56px 12px;display:flex;flex-direction:column;height:calc(100vh - 116px);min-height:460px;background:var(--bg);border:1px solid var(--line);border-radius:16px;overflow:hidden;box-shadow:0 22px 56px -30px rgba(0,0,0,.45)}
  @media (max-width:1060px){
    .cm-frame{--cmcols:3px 22px minmax(0,1fr) 118px 104px 84px 40px 74px 0 12px}
    .cm-q{display:none}
  }
  .cm-sp{flex:1}
  .cm-bar{flex:none;display:flex;align-items:center;gap:22px;padding:0 22px;height:46px;border-bottom:1px solid var(--line)}
  .cm-brand{font-size:14.5px;font-weight:700;letter-spacing:-.012em}
  .cm-legend{display:flex;align-items:center;gap:4px}
  .cm-chip{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11.5px;color:var(--ink2);padding:4px 9px;border:0;border-radius:7px;cursor:pointer;background:transparent;transition:background .12s}
  .cm-chip:hover{background:var(--sunk)}
  .cm-chip.on{background:var(--panel)}
  .cm-chip:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .cm-dot{width:7px;height:7px;border-radius:50%;flex:none}
  .cm-dot.hollow{border:1.5px solid var(--line2)}
  .cm-live{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10.5px;color:var(--ink3)}
  .cm-ctl{flex:none;display:flex;align-items:center;gap:16px;padding:0 22px;height:38px;border-bottom:1px solid var(--line);background:var(--sunk)}
  .cm-k{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--ink3)}
  .cm-seg{display:flex;align-items:center;gap:2px;padding:2px;border-radius:8px;border:1px solid var(--line)}
  .cm-segb{font-family:var(--mono);font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:4px 11px;border:0;border-radius:6px;cursor:pointer;color:var(--ink3);background:transparent}
  .cm-segb.on{color:var(--ink);background:var(--panel)}
  .cm-segb:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .cm-vr{width:1px;height:15px;background:var(--line)}
  .cm-flagchip{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10.5px;font-weight:700;padding:4px 11px;border-radius:999px;cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--ink2);transition:border-color .12s}
  .cm-flagchip:hover{border-color:var(--line2)}
  .cm-flagchip.on{border-color:color-mix(in oklab,var(--warn) 42%,transparent);background:color-mix(in oklab,var(--warn) 26%,transparent);color:var(--warnink)}
  .cm-flagchip:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .cm-clear{font-family:var(--mono);font-size:10.5px;color:var(--ink3);cursor:pointer;background:transparent;border:0;border-bottom:1px solid var(--line2);padding:0}
  .cm-clear:hover{color:var(--ink2)}
  .cm-note{font-family:var(--mono);font-size:10.5px;color:var(--ink3)}
  .cm-head{position:sticky;top:0;z-index:1;background:var(--bg);display:grid;grid-template-columns:var(--cmcols);align-items:center;gap:12px;padding:0 22px;height:24px;border-bottom:1px solid var(--line);font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:var(--ink3)}
  .cm-head .r{text-align:right}
  .cm-body{flex:1;overflow:auto;min-height:0}
  .cm-div{display:flex;align-items:center;gap:10px;padding:0 22px;height:28px;background:var(--sunk);border-bottom:1px solid var(--line)}
  .cm-div-k{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cm-div-n{font-family:var(--mono);font-size:9.5px;color:var(--ink3);flex:none}
  .cm-div-rule{flex:1;height:1px;background:var(--line)}
  .cm-div-f{font-family:var(--mono);font-size:9.5px;color:var(--warnink);flex:none}
  .cm-item{border-bottom:1px solid var(--line)}
  .cm-row{position:relative;display:grid;grid-template-columns:var(--cmcols);align-items:center;gap:12px;padding:0 22px;height:34px;cursor:pointer;background:transparent;transition:background .12s}
  .cm-row.focus{background:color-mix(in oklab,var(--ink) 4%,transparent)}
  .cm-row:hover{background:var(--panel)}
  .cm-row.open{background:var(--panel)}
  .cm-cursor{position:absolute;left:0;top:0;bottom:0;width:2px;background:var(--accent-ink)}
  .cm-rail{width:3px;height:15px;border-radius:2px}
  .cm-hcell{width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center}
  .cm-ico{width:15px;height:15px;background:var(--ink2)}
  .cm-icot{font-family:var(--mono);font-size:9px;font-weight:700;color:var(--ink3)}
  .cm-title{font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cm-where{display:flex;align-items:center;min-width:0;font-family:var(--mono);font-size:11px;color:var(--ink3);white-space:nowrap}
  .cm-proj{min-width:0;overflow:hidden;text-overflow:ellipsis}
  .cm-sess{flex:none;margin-left:.55ch}
  .cm-doing{font-family:var(--mono);font-size:11px;color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cm-flag{display:inline-block;max-width:100%;font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.02em;padding:2.5px 7px;border-radius:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border:1px solid var(--line)}
  .cm-track{display:block;height:4px;border-radius:2px;background:var(--line);overflow:hidden}
  .cm-fill{display:block;height:100%;border-radius:2px}
  .cm-metric{font-family:var(--mono);font-size:11px;text-align:right;font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cm-q{display:flex;justify-content:flex-end;gap:9px;opacity:0;transition:opacity .12s ease}
  .cm-row:hover .cm-q,.cm-row.focus .cm-q,.cm-row.open .cm-q,
  .cm-row:focus-within .cm-q{opacity:1}
  .cm-qb{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--ink3);background:transparent;border:0;padding:0;cursor:pointer;transition:color .12s}
  .cm-qb:hover{color:var(--ink)}
  .cm-qb:focus-visible{outline:none;color:var(--ink);box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent);border-radius:4px}
  .cm-caret{font-family:var(--mono);font-size:12px;color:var(--ink3);text-align:center}

  /* calm mode — expanded row */
  .cm-exp{background:var(--panel);border-top:1px solid var(--line);padding:18px 22px 20px 60px;display:flex;gap:34px;align-items:flex-start;flex-wrap:wrap}
  .cm-exp-main{flex:1;min-width:300px;display:flex;flex-direction:column;gap:14px}
  .cm-exp-side{flex:none;width:300px;display:flex;flex-direction:column;gap:16px}
  .cm-why{display:flex;gap:11px;align-items:flex-start;max-width:660px}
  .cm-why-g{font-family:var(--mono);font-size:12px;line-height:1.35}
  .cm-why-t{font-size:13px;line-height:1.55;color:var(--ink2);text-wrap:pretty}
  .cm-why-t b{font-weight:700}
  .cm-quote{max-width:660px;padding:11px 14px;border-left:2px solid var(--line2);background:var(--bg);border-radius:0 8px 8px 0}
  .cm-subk{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:var(--ink3)}
  .cm-quote .cm-subk{display:block;margin-bottom:6px}
  .cm-quote-t{font-family:var(--mono);font-size:11.5px;line-height:1.6;color:var(--ink2);text-wrap:pretty;overflow-wrap:anywhere}
  .cm-tasks{display:flex;flex-direction:column;gap:5px;max-width:660px}
  .cm-task{display:flex;align-items:center;gap:10px}
  .cm-task-g{font-family:var(--mono);font-size:11px;width:10px;flex:none}
  .cm-task-t{font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cm-meta{display:flex;align-items:center;gap:20px;font-family:var(--mono);font-size:10.5px;color:var(--ink3);flex-wrap:wrap;padding-top:2px}
  .cm-turn{display:flex;flex-direction:column;gap:8px}
  .cm-turn-top{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
  .cm-turn-pct{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--ink)}
  .cm-turn-track{height:7px;border-radius:4px;background:var(--line);overflow:hidden}
  .cm-turn-line{font-family:var(--mono);font-size:11px;color:var(--ink2)}
  .cm-subs{display:flex;flex-direction:column;gap:7px}
  .cm-sub{display:flex;align-items:center;gap:9px}
  .cm-sub-dot{width:5px;height:5px;flex:none;border-radius:50%;background:var(--accent);animation:pulse 1.7s infinite}
  .cm-sub-n{font-size:12.5px;color:var(--ink2);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cm-acts{display:flex;gap:8px;flex-wrap:wrap}
  .cm-act{font-family:var(--mono);font-size:11px;color:var(--ink2);background:transparent;border:1px solid var(--line);border-radius:7px;padding:7px 13px;cursor:pointer;transition:background .12s}
  .cm-act:hover{background:var(--bg)}
  .cm-act:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}

  /* calm mode — empty state and footer */
  .cm-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;padding:110px 20px;text-align:center}
  .cm-empty-t{font-size:14px;color:var(--ink3)}
  .cm-link{font-family:inherit;font-size:inherit;color:var(--accent-ink);background:transparent;border:0;border-bottom:1px solid currentColor;padding:0;cursor:pointer}
  .cm-foot{flex:none;display:flex;align-items:center;gap:8px 18px;flex-wrap:wrap;padding:7px 22px;min-height:32px;border-top:1px solid var(--line);background:var(--sunk);font-family:var(--mono);font-size:10px;color:var(--ink3)}
  .cm-keys{display:inline-flex;align-items:center;gap:14px;flex-wrap:wrap}
  .cm-keys span{display:inline-flex;align-items:center;gap:5px}
  .cm-fstrip{display:inline-flex;align-items:center;gap:4px}
  .cm-foot .btile{width:18px;height:18px;border-radius:6px}
  .cm-foot .bico{width:11px;height:11px}
  .cm-foot .bmono{font-size:8px}
</style>
</head>
<body>
<div class="wrap" id="app">
  <div class="empty">Loading…</div>
</div>
<script>
const qs = new URLSearchParams(location.search);
const showAll = qs.get("all") === "1";
let idleExpanded = false;
let lastData = null;
let refreshSequence = 0;
let latestSettledRefresh = 0;

const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function fmtDur(sec){
  if(sec == null || sec < 0) return "–";
  sec = Math.floor(sec);
  if(sec < 60) return sec + "s";
  if(sec < 3600) return Math.floor(sec/60) + "m";
  if(sec < 86400) return Math.floor(sec/3600) + "h " + Math.floor((sec%3600)/60) + "m";
  return Math.floor(sec/86400) + "d " + Math.floor((sec%86400)/3600) + "h";
}

// One wording for the long-turn signal: the regular view's ⚠️ tooltip and the
// calm ledger's flag explanation must not drift apart.
const LONG_TURN_NOTE = "This request is running long (or estimated to). " +
  "Double-check what the agent is doing matches your expectations.";

// Trailing output-rate sparklines: client-side ring buffers that start when
// the page opens and drop points once they age out of the visual window.
// Points are stamped with the VIEWER's clock at receipt — the axis and the
// tooltip timestamps must agree with the user's watch, and the server's
// `generated` value can lag (2.5s response memoization) or skew. `generated`
// is used only to drop replayed/memoized payloads.
const SPARK_WINDOW_SEC = 300;
const nowSec = () => Date.now() / 1000;
const rateHistory = [];               // overall: [{t, v}]
const sessRateHistory = new Map();    // "harness:sid" -> [{t, v}]
const sessKey = x => x.harness + ":" + (x.sid || x.session);
let lastGenerated = 0;

function pushPoint(arr, t, v){
  if(arr.length && arr[arr.length-1].t >= t) return; // non-advancing clock
  arr.push({t, v});
  const cutoff = t - SPARK_WINDOW_SEC;
  while(arr.length && arr[0].t < cutoff) arr.shift();
}

function recordRates(d){
  if(typeof d.generated !== 'number' || !isFinite(d.generated)) return;
  if(d.generated <= lastGenerated) return; // memoized/replayed payload
  lastGenerated = d.generated;
  const t = nowSec();
  pushPoint(rateHistory, t, d.summary.rate_per_min || 0);
  const seen = new Set();
  for(const x of d.sessions){
    const key = sessKey(x);
    seen.add(key);
    let arr = sessRateHistory.get(key);
    if(!arr) sessRateHistory.set(key, arr = []);
    pushPoint(arr, t, x.rate_per_min || 0);
  }
  // Remove entries for departed sessions AND aged-out orphaned buffers (no updates in 600s).
  // This ensures memory doesn't leak if a session disappears before the next recordRates() call.
  for(const [k, arr] of sessRateHistory){
    if(!seen.has(k) || (arr.length && arr[arr.length-1].t < t - 600)){
      sessRateHistory.delete(k);
    }
  }
}

const SPARK_PAD = 3;
const sparkX = (t, now, w) => {
  if(!isFinite(t) || !isFinite(now) || !isFinite(w) || SPARK_WINDOW_SEC <= 0) return 0;
  return w - SPARK_PAD - (now - t) * (w - 2*SPARK_PAD) / SPARK_WINDOW_SEC;
};
const sparkY = (v, max, h) => {
  if(!isFinite(v) || !isFinite(max) || !isFinite(h) || max <= 0) return h - SPARK_PAD;
  return h - SPARK_PAD - (v / max) * (h - 2*SPARK_PAD);
};

function sparkSVG(pts, now, w, h, stretch){
  if(!isFinite(w) || !isFinite(h) || !isFinite(now) || w <= 0 || h <= 0) return "";
  const base = h - SPARK_PAD;
  let marks = "";
  if(pts && pts.length > 1){
    const max = Math.max(1, ...pts.map(p => p.v));
    if(!isFinite(max)) return ""; // Guard against NaN from points
    const xy = pts.map(p => {
      const x = sparkX(p.t, now, w);
      const y = sparkY(p.v, max, h);
      return [isFinite(x) ? x : 0, isFinite(y) ? y : h/2]; // Default to safe values if NaN
    });
    const pathPts = xy.map(c => c[0].toFixed(2) + "," + c[1].toFixed(2));
    const area = "M" + xy[0][0].toFixed(2) + "," + base + " L" + pathPts.join(" L") +
      " L" + xy[xy.length-1][0].toFixed(2) + "," + base + " Z";
    marks = `<path d="${area}" fill="var(--accent)" fill-opacity=".12"/>` +
      `<polyline points="${pathPts.join(" ")}" fill="none"` +
      ` stroke="color-mix(in oklab,var(--accent) 72%,var(--ink3))" stroke-width="2"` +
      ` stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`;
    if(!stretch){
      const e = xy[xy.length-1];
      marks += `<circle cx="${e[0].toFixed(2)}" cy="${e[1].toFixed(2)}" r="3.5"` +
        ` fill="var(--accent)" stroke="var(--panel)" stroke-width="2"/>`;
    }
  }
  return `<svg viewBox="0 0 ${w} ${h}"${stretch ? ' preserveAspectRatio="none"' : ""} aria-hidden="true">` +
    `<line x1="0" y1="${base}" x2="${w}" y2="${base}" stroke="var(--line)" stroke-width="1"` +
    ` vector-effect="non-scaling-stroke"/>${marks}</svg>`;
}

function heroSpark(){
  // Stretched viewBox (0..100 units) so the HTML end-dot and crosshair can
  // share the same coordinates as percentages of the wrap's width and height.
  // The axis anchors to the viewer's clock — the same clock the points are
  // stamped with — so hover timestamps never drift from wall time.
  const axisNow = nowSec();
  let dot = "";
  if(rateHistory.length > 1){
    const max = Math.max(1, ...rateHistory.map(p => p.v));
    const last = rateHistory[rateHistory.length-1];
    const dotX = sparkX(last.t, axisNow, 100);
    const dotY = sparkY(last.v, max, 100); // Use 100 to get percentage coordinates (0-100%)
    dot = `<span class="spark-dot" style="left:${dotX.toFixed(2)}%;` +
      `top:${dotY.toFixed(2)}%"></span>`;
  }
  const lastV = rateHistory.length ? rateHistory[rateHistory.length-1].v : null;
  const nowLabel = lastV == null ? "" :
    `, now ${lastV.toLocaleString()} tokens per minute`;
  return `<div class="spark-wrap" id="spark-main" tabindex="0" data-now="${axisNow}"` +
    ` role="img" aria-label="output rate, trailing 5 minutes${nowLabel}">` +
    sparkSVG(rateHistory, axisNow, 100, 46, true) + dot +
    `<span class="spark-x" id="spark-x"></span><span class="spark-tip" id="spark-tip"></span></div>`;
}

function hideSparkHover(){
  if(sparkHoverCache && sparkHoverCache.xline) sparkHoverCache.xline.style.opacity = 0;
  if(sparkHoverCache && sparkHoverCache.tip) sparkHoverCache.tip.style.opacity = 0;
}

// Cache DOM nodes and child elements for efficient hover updates.
let sparkHoverCache = null;
function initSparkHoverCache(){
  sparkHoverCache = {
    xline: document.getElementById("spark-x"),
    tip: document.getElementById("spark-tip"),
    tipVal: null,
    tipTime: null
  };
  if(sparkHoverCache.tip){
    // Create tip children once and reuse them.
    sparkHoverCache.tipVal = document.createElement("b");
    sparkHoverCache.tipTime = document.createTextNode("");
    sparkHoverCache.tip.appendChild(sparkHoverCache.tipVal);
    sparkHoverCache.tip.appendChild(sparkHoverCache.tipTime);
  }
  return sparkHoverCache;
}

function showSparkHover(frac){
  const wrap = document.getElementById("spark-main");
  if(!wrap || rateHistory.length < 2) return;
  const now = parseFloat(wrap.dataset.now);
  if(typeof now !== 'number' || !isFinite(now)) return;
  const t = now - (1 - Math.min(1, Math.max(0, frac))) * SPARK_WINDOW_SEC;
  let best = rateHistory[0];
  for(const p of rateHistory) if(Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
  if(!isFinite(best.v) || !isFinite(best.t)) return;
  const x = sparkX(best.t, now, 100);
  if(!isFinite(x)) return;

  // Use cached DOM nodes instead of recreating on every move event.
  let cache = sparkHoverCache;
  if(!cache || !cache.xline || !cache.xline.parentElement){
    cache = initSparkHoverCache();
  }
  if(!cache.xline || !cache.tip || !cache.tipVal || !cache.tipTime) return;

  cache.xline.style.left = x.toFixed(2) + "%";
  cache.xline.style.opacity = 1;
  cache.tip.style.left = Math.min(88, Math.max(12, x)).toFixed(2) + "%";
  // Update cached tip content instead of recreating DOM.
  cache.tipVal.textContent = best.v.toLocaleString();
  cache.tipTime.textContent = " tok/min · " + new Date(best.t * 1000).toLocaleTimeString();
  cache.tip.style.opacity = 1;
}

let sparkPointer = null; // last pointer position while over the sparkline
let renderInProgress = false; // prevent race between DOM updates and event handlers

document.addEventListener("pointermove", e => {
  if(renderInProgress) return; // Skip updates during render
  const wrap = e.target.closest ? e.target.closest("#spark-main") : null;
  if(!wrap){ sparkPointer = null; hideSparkHover(); return; }
  sparkPointer = {x: e.clientX, y: e.clientY};
  const r = wrap.getBoundingClientRect();
  showSparkHover((e.clientX - r.left) / Math.max(1, r.width));
});
document.addEventListener("focusin", e => {
  if(e.target && e.target.id === "spark-main") showSparkHover(1);
});
document.addEventListener("focusout", e => {
  if(e.target && e.target.id === "spark-main") hideSparkHover();
});

// The pointer can leave the page without a final in-document pointermove
// (window-edge exit, alt-tab, tab switch). Clear the saved position on those
// paths, or restoreSparkState() resurrects the tooltip for a pointer that is
// gone on every subsequent poll.
function clearSparkPointer(){ sparkPointer = null; hideSparkHover(); }
document.addEventListener("mouseout", e => { if(!e.relatedTarget) clearSparkPointer(); });
window.addEventListener("blur", clearSparkPointer);
document.addEventListener("visibilitychange", () => { if(document.hidden) clearSparkPointer(); });

// render() replaces #app wholesale, which kills the sparkline's focus and
// resets its hover layer; re-apply both against the freshly built DOM.
function restoreSparkState(hadFocus, savedPointer){
  // Invalidate the hover cache since the DOM was replaced.
  sparkHoverCache = null;

  const wrap = document.getElementById("spark-main");
  if(!wrap) return;
  if(hadFocus){ wrap.focus({preventScroll: true}); return; } // focusin re-shows tip

  // Restore hover state based on saved pointer position (captured before render).
  if(!savedPointer) return;
  const r = wrap.getBoundingClientRect();
  if(savedPointer.x >= r.left && savedPointer.x <= r.right &&
     savedPointer.y >= r.top && savedPointer.y <= r.bottom){
    showSparkHover((savedPointer.x - r.left) / Math.max(1, r.width));
  }
}

const ICON_PATH = {
  claude: "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z",
  codex: "M8.086.457a6.105 6.105 0 013.046-.415c1.333.153 2.521.72 3.564 1.7a.117.117 0 00.107.029c1.408-.346 2.762-.224 4.061.366l.063.03.154.076c1.357.703 2.33 1.77 2.918 3.198.278.679.418 1.388.421 2.126a5.655 5.655 0 01-.18 1.631.167.167 0 00.04.155 5.982 5.982 0 011.578 2.891c.385 1.901-.01 3.615-1.183 5.14l-.182.22a6.063 6.063 0 01-2.934 1.851.162.162 0 00-.108.102c-.255.736-.511 1.364-.987 1.992-1.199 1.582-2.962 2.462-4.948 2.451-1.583-.008-2.986-.587-4.21-1.736a.145.145 0 00-.14-.032c-.518.167-1.04.191-1.604.185a5.924 5.924 0 01-2.595-.622 6.058 6.058 0 01-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74 7.74 0 01-.495-1.283 6.11 6.11 0 01-.017-3.064.166.166 0 00.008-.074.115.115 0 00-.037-.064 5.958 5.958 0 01-1.38-2.202 5.196 5.196 0 01-.333-1.589 6.915 6.915 0 01.188-2.132c.45-1.484 1.309-2.648 2.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129 0 00.087-.087A6.016 6.016 0 015.635 2.31C6.315 1.464 7.132.846 8.086.457zm-.804 7.85a.848.848 0 00-1.473.842l1.694 2.965-1.688 2.848a.849.849 0 001.46.864l1.94-3.272a.849.849 0 00.007-.854l-1.94-3.393zm5.446 6.24a.849.849 0 000 1.695h4.848a.849.849 0 000-1.696h-4.848z",
  gemini: "M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z",
  copilot: "M19.245 5.364c1.322 1.36 1.877 3.216 2.11 5.817.622 0 1.2.135 1.592.654l.73.964c.21.278.323.61.323.955v2.62c0 .339-.173.669-.453.868C20.239 19.602 16.157 21.5 12 21.5c-4.6 0-9.205-2.583-11.547-4.258-.28-.2-.452-.53-.453-.868v-2.62c0-.345.113-.679.321-.956l.73-.963c.392-.517.974-.654 1.593-.654l.029-.297c.25-2.446.81-4.213 2.082-5.52 2.461-2.54 5.71-2.851 7.146-2.864h.198c1.436.013 4.685.323 7.146 2.864zm-7.244 4.328c-.284 0-.613.016-.962.05-.123.447-.305.85-.57 1.108-1.05 1.023-2.316 1.18-2.994 1.18-.638 0-1.306-.13-1.851-.464-.516.165-1.012.403-1.044.996a65.882 65.882 0 00-.063 2.884l-.002.48c-.002.563-.005 1.126-.013 1.69.002.326.204.63.51.765 2.482 1.102 4.83 1.657 6.99 1.657 2.156 0 4.504-.555 6.985-1.657a.854.854 0 00.51-.766c.03-1.682.006-3.372-.076-5.053-.031-.596-.528-.83-1.046-.996-.546.333-1.212.464-1.85.464-.677 0-1.942-.157-2.993-1.18-.266-.258-.447-.661-.57-1.108-.32-.032-.64-.049-.96-.05zm-2.525 4.013c.539 0 .976.426.976.95v1.753c0 .525-.437.95-.976.95a.964.964 0 01-.976-.95v-1.752c0-.525.437-.951.976-.951zm5 0c.539 0 .976.426.976.95v1.753c0 .525-.437.95-.976.95a.964.964 0 01-.976-.95v-1.752c0-.525.437-.951.976-.951zM7.635 5.087c-1.05.102-1.935.438-2.385.906-.975 1.037-.765 3.668-.21 4.224.405.394 1.17.657 1.995.657h.09c.649-.013 1.785-.176 2.73-1.11.435-.41.705-1.433.675-2.47-.03-.834-.27-1.52-.63-1.813-.39-.336-1.275-.482-2.265-.394zm6.465.394c-.36.292-.6.98-.63 1.813-.03 1.037.24 2.06.675 2.47.968.957 2.136 1.104 2.776 1.11h.044c.825 0 1.59-.263 1.995-.657.555-.556.765-3.187-.21-4.224-.45-.468-1.335-.804-2.385-.906-.99-.088-1.875.058-2.265.394zM12 7.615c-.24 0-.525.015-.84.044.03.16.045.336.06.526l-.001.159a2.94 2.94 0 01-.014.25c.225-.022.425-.027.612-.028h.366c.187 0 .387.006.612.028-.015-.146-.015-.277-.015-.409.015-.19.03-.365.06-.526a9.29 9.29 0 00-.84-.044z",
  opencode: "M16 6H8v12h8V6zm4 16H4V2h16v20z",
  cursor: "M22.106 5.68L12.5.135a.998.998 0 00-.998 0L1.893 5.68a.84.84 0 00-.419.726v11.186c0 .3.16.577.42.727l9.607 5.547a.999.999 0 00.998 0l9.608-5.547a.84.84 0 00.42-.727V6.407a.84.84 0 00-.42-.726zm-.603 1.176L12.228 22.92c-.063.108-.228.064-.228-.061V12.34a.59.59 0 00-.295-.51l-9.11-5.26c-.107-.062-.063-.228.062-.228h18.55c.264 0 .428.286.296.514z",
  goose: "M21.595 23.61c1.167-.254 2.405-.944 2.405-.944l-2.167-1.784a12.124 12.124 0 01-2.695-3.131 12.127 12.127 0 00-3.97-4.049l-.794-.462a1.115 1.115 0 01-.488-.815.844.844 0 01.154-.575c.413-.582 2.548-3.115 2.94-3.44.503-.416 1.065-.762 1.586-1.159.074-.056.148-.112.221-.17.003-.002.007-.004.009-.007.167-.131.325-.272.45-.438.453-.524.563-.988.59-1.193-.061-.197-.244-.639-.753-1.148.319.02.705.272 1.056.569.235-.376.481-.773.727-1.171.165-.266-.08-.465-.086-.471h-.001V3.22c-.007-.007-.206-.25-.471-.086-.567.35-1.134.702-1.639 1.021 0 0-.597-.012-1.305.599a2.464 2.464 0 00-.438.45l-.007.009c-.058.072-.114.147-.17.221-.397.521-.743 1.083-1.16 1.587-.323.391-2.857 2.526-3.44 2.94a.842.842 0 01-.574.153 1.115 1.115 0 01-.815-.488l-.462-.794a12.123 12.123 0 00-4.049-3.97 12.133 12.133 0 01-3.13-2.695L1.332 0S.643 1.238.39 2.405c.352.428 1.27 1.49 2.34 2.302C1.58 4.167.73 3.75.06 3.4c-.103.765-.063 1.92.043 2.816.726.317 1.961.806 3.219 1.066-1.006.236-2.11.278-2.961.262.15.554.358 1.119.64 1.688.119.263.25.52.39.77.452.125 2.222.383 3.164.171l-2.51.897a27.776 27.776 0 002.544 2.726c2.031-1.092 2.494-1.241 4.018-2.238-2.467 2.008-3.108 2.828-3.8 3.67l-.483.678c-.25.351-.469.725-.65 1.117-.61 1.31-1.47 4.1-1.47 4.1-.154.486.202.842.674.674 0 0 2.79-.861 4.1-1.47.392-.182.766-.4 1.118-.65l.677-.483c.227-.187.453-.37.701-.586 0 0 1.705 2.02 3.458 3.349l.896-2.511c-.211.942.046 2.712.17 3.163.252.142.509.272.772.392.569.28 1.134.49 1.688.64-.016-.853.026-1.956.261-2.962.26 1.258.75 2.493 1.067 3.219.895.106 2.051.146 2.816.043a73.87 73.87 0 01-1.308-2.67c.811 1.07 1.874 1.988 2.302 2.34h-.001z"
};
const iconURI = d => "data:image/svg+xml," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#000"><path d="' + d + '"/></svg>');
const HARNESS = {
  claude:{code:"CL",name:"Claude"}, codex:{code:"CX",name:"Codex"},
  pi:{code:"PI",name:"Pi"},
  gemini:{code:"GE",name:"Gemini"}, copilot:{code:"CP",name:"Copilot"},
  opencode:{code:"OC",name:"OpenCode"}, cursor:{code:"CU",name:"Cursor"},
  goose:{code:"GO",name:"Goose"}, droid:{code:"DR",name:"Droid"}
};
for(const k in HARNESS){ if(ICON_PATH[k]) HARNESS[k].icon = iconURI(ICON_PATH[k]); }

function badge(key, active, name, tipSuffix){
  const h = own(HARNESS, key, null) ||
    {code:String(key||"?").slice(0,2).toUpperCase(), name:key};
  const label = name || h.name;
  const tileStyle = active ? "background:var(--ink)" : "border:1px solid var(--line)";
  const on = active ? "var(--bg)" : "var(--ink2)";
  const inner = h.icon
    ? `<span class="bico" style="background:${on};-webkit-mask:url('${h.icon}') center/contain no-repeat;mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="bmono" style="color:${on}">${esc(h.code)}</span>`;
  return `<span class="hbadge"><span class="btile" style="${tileStyle}">${inner}</span>` +
         `<span class="htip">${esc(label)}${esc(tipSuffix || "")}</span></span>`;
}

function harnessStrip(harnesses){
  if(!harnesses || !harnesses.length) return "";
  const chips = harnesses.map(h => {
    const healthy = h.discovered && !h.error;
    const suffix = h.error ? " — collector error" : (h.discovered ? "" : " — no data");
    return badge(h.key, healthy, h.label, suffix);
  }).join("");
  return `<span class="hstrip-k">harnesses</span>${chips}`;
}

function rateTile(d){
  const rate = d.summary.rate_per_min || 0;
  const total = (isFinite(rate) ? rate : 0).toLocaleString();
  const byH = {};
  for(const x of d.sessions){
    if(x.active && x.rate_per_min && isFinite(x.rate_per_min)){
      byH[x.harness] = (byH[x.harness]||0) + x.rate_per_min;
    }
  }
  const shown = (d.harnesses || []).filter(h => h.discovered)
    .map(h => ({key:h.key, v:byH[h.key] || 0}))
    .sort((a,b) => b.v - a.v).slice(0,5);
  const max = Math.max(1, ...shown.map(r => r.v));
  const rows = shown.length ? `<div class="rate-rows">` + shown.map(r => {
    const v = isFinite(r.v) ? r.v : 0;
    const pct = Math.max(v ? 4 : 0, Math.round(v * 100 / max));
    return `<div class="rrow"><span class="rrow-badge">${badge(r.key, true)}</span>` +
      `<span class="rrow-bar"><span class="rrow-fill" style="width:${pct}%"></span></span>` +
      `<span class="rrow-v">${v.toLocaleString()}</span></div>`;
  }).join("") + `</div>` : "";
  return `<div class="tile"><div class="tile-top"><span class="tile-label">Output rate</span>` +
    `<span class="tile-cap">tok / min · 10 min</span></div>` +
    `<div class="tile-val">${total}</div>${heroSpark()}${rows}</div>`;
}

function sdWindow(stages, idx){
  if(stages.length <= 6 || idx < 0) return stages.slice(0, 6);
  const lo = Math.max(0, idx - 2), hi = Math.min(stages.length, idx + 3);
  const out = [];
  if(lo > 0){ out.push(stages[0]); if(lo > 1) out.push(null); }
  for(let k = lo; k < hi; k++) out.push(stages[k]);
  if(hi < stages.length){ if(hi < stages.length - 1) out.push(null); out.push(stages[stages.length - 1]); }
  return out;
}

const SD_SLUG_MAX = 22;   // matches the .sd-ent column width, in mono ch
const SD_SLUG_HEAD = 8;   // enough to tell one workflow's entities from another's

// Elide the MIDDLE of an over-long entity slug, never the tail. Entity slugs
// within a workflow share a long prefix and differ only at the end
// (`datarecce-recce-cloud-infra-pr-1573` vs `…-pr-1587`), so tail truncation
// renders two different entities as the same string.
function sdSlug(slug){
  if(slug.length <= SD_SLUG_MAX) return slug;
  const tail = SD_SLUG_MAX - SD_SLUG_HEAD - 1;
  return slug.slice(0, SD_SLUG_HEAD) + "…" + slug.slice(slug.length - tail);
}

function sdBlock(sess){
  const sd = sess.spacedock;
  if(!sd) return "";
  const wfs = sd.workflows || [];
  const role = sd.role === "first-officer" ? "first officer" : sd.role;
  if(!wfs.length){
    return `<div class="sd"><div><span class="sd-k">spacedock</span>` +
      `<span class="sd-role">${esc(role)}</span></div></div>`;
  }
  let rows = "";
  for(const wf of wfs){
    const stages = wf.stages || [];
    for(const ent of (wf.entities || [])){
      const idx = stages.indexOf(ent.stage);
      const spine = sdWindow(stages, idx).map(s => s === null
        ? `<span class="sd-gap">…</span>`
        : `<span class="${s === ent.stage && idx >= 0 ? "sd-cur" : "sd-st"}">${esc(s)}</span>`
      ).join(`<span class="sd-arr">→</span>`);
      rows += `<div class="sd-row"><span class="sd-ent${ent.live ? " sd-live" : ""}"` +
        ` title="${esc(ent.slug)}">${esc(sdSlug(ent.slug))}</span>` +
        (ent.cycle ? `<span class="sd-cyc">${esc(ent.cycle)}</span>` : "") +
        `<span class="sd-spine">${spine}</span></div>`;
    }
  }
  const names = wfs.map(w => w.workflow).join(" · ");
  return `<div class="sd"><div><span class="sd-k">spacedock ${esc(names)}</span>` +
    `<span class="sd-role">${esc(role)}</span></div>${rows}</div>`;
}

function turnBlock(t){
  if(!t) return "";
  const warn = t.long ? `<span class="lwarn" tabindex="0" role="note"` +
    ` aria-label="${LONG_TURN_NOTE}">!` +
    `<span class="ltip">${LONG_TURN_NOTE}</span></span>` : "";
  const pct = (t.pct != null) ? `<span class="pct">${t.pct}%</span>` : "";
  const bar = (t.pct != null) ? `<div class="turnbar"><span class="turnfill" style="width:${t.pct}%"></span></div>` : "";
  const eta = t.eta_h ? `~${esc(t.eta_h)} left (est)` : "running longer than recent turns";
  return `<div class="turn"><div class="turn-row">` +
    `<span class="turn-txt">this request · ${esc(t.elapsed_h)} elapsed · ${eta}</span>` +
    `<span class="turn-right">${warn}${pct}</span></div>${bar}</div>`;
}

function taskBlock(sess){
  if(!sess.tasks || !sess.tasks.length)
    return `<div class="no-tasks">no tracked tasks in this session</div>`;
  const order = {in_progress:0, pending:1, completed:2};
  const STATUS = {in_progress:"In progress", pending:"Pending", completed:"Completed"};
  const tasks = [...sess.tasks].sort((a,b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));
  const rows = tasks.map(t => {
    const af = (t.status === "in_progress" && t.activeForm) ? `<div class="task-af">${esc(t.activeForm)}…</div>` : "";
    return `<div class="task"><span class="tstatus st-${esc(t.status)}">${STATUS[t.status] || esc(t.status)}</span>` +
      `<div class="task-body"><div class="task-subj">${esc(t.subject)}</div>${af}</div>` +
      `<div class="task-when">${esc(t.elapsed_h || "")}<br>${esc(t.updated_ago || "")}</div></div>`;
  }).join("");
  return `<div class="tasks">${rows}</div>`;
}

function workingCard(d, sess){
  const hist = sessRateHistory.get(sessKey(sess));
  const spark = (hist && hist.length > 1)
    ? `<span class="rate-spark" title="${(sess.rate_per_min || 0).toLocaleString()}` +
      ` tok/min · trailing 5 min">` +
      sparkSVG(hist, nowSec(), 84, 26, false) + `</span>`
    : "";
  const rateMeter = (sess.active && sess.rate_per_min)
    ? `<div class="rate-meter"><div class="rate-flex">${spark}` +
      `<div><div class="rate-num">${sess.rate_per_min.toLocaleString()}</div>` +
      `<div class="rate-lab">tok / min</div></div></div>` +
      `<div class="rate-track"><span class="rate-live"></span></div></div>`
    : "";
  const bits = [];
  if(sess.total) bits.push(`${sess.done}/${sess.total} done · ${sess.progress_pct}%`);
  if(sess.eta_h) bits.push(`~${sess.eta_h} left`);
  const bitsLine = bits.length ? `<div class="card-bits">${esc(bits.join(" · "))}</div>` : "";
  const subs = (sess.subagents && sess.subagents.length)
    ? `<div class="subs"><span class="subs-k">subagents</span>` +
      sess.subagents.slice(0,6).map(a => `<span class="subpill"><span class="subdot"></span>${esc(a)}</span>`).join("") +
      (sess.subagents.length > 6 ? `<span class="subs-k">+${sess.subagents.length-6} more</span>` : "") +
      `</div>`
    : "";
  return `<div class="card"><div class="card-top"><div class="card-main">` +
    `<div class="card-headrow"><span class="pill pill-work"><span class="pill-dot"></span>Working</span>` +
    badge(sess.harness, true) + `</div>` +
    `<div class="card-title">${esc(sess.title || sess.project)}</div>` +
    `<div class="card-meta">${esc(sess.project)} · ${esc(sess.session)}</div>${bitsLine}` +
    `</div>${rateMeter}</div>` +
    `<div class="now"><span class="now-k">now</span>${esc(sess.state_detail)}</div>` +
    turnBlock(sess.turn) + subs + sdBlock(sess) + taskBlock(sess) + `</div>`;
}

function needRow(d, sess){
  const blocked = fmtDur(d.generated - (sess.blocked_since || sess.last_activity));
  return `<div class="need"><div style="min-width:0">` +
    `<div class="need-meta">${badge(sess.harness, true)}${esc(sess.project)} · ${esc(sess.session)}</div>` +
    `<div class="need-title">${esc(sess.title || sess.last_prompt || sess.project)}</div>` +
    `<div class="need-detail">${esc(sess.state_detail)}</div></div>` +
    `<div style="flex:none"><div class="blocked-k">blocked</div><div class="blocked-v">${esc(blocked)}</div></div></div>`;
}

function idleRow(d, sess){
  const age = fmtDur(d.generated - sess.last_activity);
  const t = sess.total ? ` · ${sess.done}/${sess.total}` : "";
  return `<div class="idle-row"><span class="idle-dot"></span>${badge(sess.harness, false)}` +
    `<span class="idle-title">${esc(sess.title || sess.last_prompt || sess.project)}</span>` +
    `<span class="idle-proj">${esc(sess.project)} · ${esc(sess.session)}${t}</span>` +
    `<span class="idle-age">idle ${esc(age)}</span></div>`;
}

function toggleIdle(){ idleExpanded = !idleExpanded; if(lastData) render(lastData); }

/* ── calm mode ─────────────────────────────────────────────────────────────
   A second display of the same payload: one dense ledger row per session
   instead of a stack of cards. Every value it shows is derived from
   /api/data, so the two modes cannot disagree about what a session is
   doing. The switch is remembered in localStorage and bound to `c`. */
const DISPLAY_MODE_KEY = "cargento.displayMode";
const CALM_STALE_SEC = 7200;   // an idle session quiet this long is flagged "stale"

let displayMode = "regular";
try{
  const saved = localStorage.getItem(DISPLAY_MODE_KEY);
  if(saved === "calm" || saved === "regular") displayMode = saved;
}catch(e){ /* private mode, or a context with no storage — regular it is */ }

let calmSort = "attention";   /* attention | recent | repo */
let calmStateOnly = null;     /* needs | work | idle */
let calmFlagOnly = false;
/* Rows are identified by sessKey(), the same (harness, sid) pair the rate
   buffers and the notification map use — dedupe_sessions keys on that pair, so
   a bare sid is not unique across harnesses. */
let calmOpenKey = null;       /* the one expanded row */
let calmCursorKey = null;     /* keyboard cursor */
let calmCopyNote = null;      /* {key, text} — transient label after copy id */
let calmScrollTop = 0;        /* ledger scroll survives the 5s re-render */
let calmRevealFocus = false;  /* scroll the cursor into view after this render */
let calmResetScroll = false;  /* re-filtered: the next render starts at the top */

function setDisplayMode(mode){
  if(mode !== "calm" && mode !== "regular" || mode === displayMode) return;
  displayMode = mode;
  try{ localStorage.setItem(DISPLAY_MODE_KEY, mode); }catch(e){ /* nothing to persist to */ }
  calmResetScroll = true;
  if(lastData) render(lastData);
}

/* ── stopping the server from the page ─────────────────────────────────────
   Two clicks, because the page cannot undo a stop and the header is a place
   people click. `stopArmed` is a module variable for the documented reason:
   #app is rebuilt every five seconds, so state that is not reapplied after
   the swap is state the refresh eats — and a button that disarmed itself on
   the next poll would flicker under the reader's cursor. */
let stopArmed = false;
let stopError = "";
let serverStopped = false;
let stopFocusPending = false;

function stopControl(){
  const note = stopError ? `<span class="stopnote">${esc(stopError)}</span>` : "";
  return `<button type="button" id="stop-control"` +
    ` class="stopbtn${stopArmed ? " armed" : ""}"` +
    ` data-calm="stop" aria-pressed="${stopArmed}"` +
    ` title="Stop the Cargento server. Two clicks — this cannot be undone from the page.">` +
    (stopArmed ? "stop — sure?" : "stop") + `</button>` + note;
}

function restoreStopFocus(){
  if(!stopFocusPending) return;
  stopFocusPending = false;
  const button = document.getElementById("stop-control");
  if(button && button.focus) button.focus();
}

function disarmStop(){
  if(!stopArmed && !stopError) return false;
  stopArmed = false; stopError = ""; stopFocusPending = false;
  return true;
}

async function requestStop(){
  stopArmed = false; stopFocusPending = false;
  try{
    const r = await fetch("/api/shutdown", {method: "POST"});
    if(!r.ok) throw new Error("status " + r.status);
  }catch(e){
    /* Still running, so the page must not claim otherwise. */
    stopError = "stop failed";
    if(lastData) render(lastData);
    return;
  }
  /* Clearing the error matters even though the panel replaces the note: a
     lingering stopError keeps disarmStop() answering true forever, so every
     later click reports a disarm that disarmed nothing. */
  stopError = "";
  serverStopped = true;
  renderStopped();
}

function renderStopped(){
  /* Not the "stalled" banner: nothing is retrying, nothing is coming back,
     and the reader is the one who ended it. */
  if(refreshTimer !== null){ clearInterval(refreshTimer); refreshTimer = null; }
  document.title = "Cargento — stopped";
  const app = document.getElementById("app");
  if(!app) return;
  app.className = "wrap";
  app.innerHTML = `<div class="stopped"><div class="stopped-h">Cargento stopped.</div>` +
    `<div class="stopped-p">The server is no longer running, so this page will not ` +
    `update. Ask your agent to open Cargento again to restart it.</div></div>`;
}

function modeBar(){
  const btn = k => `<button type="button" class="modebtn${displayMode === k ? " on" : ""}"` +
    ` data-calm="mode" data-arg="${k}" aria-pressed="${displayMode === k}">${k}</button>`;
  return `<div class="modebar"><span class="modebar-k">display</span>` +
    `<div class="modeseg" role="group" aria-label="display mode">` +
    btn("regular") + btn("calm") + `</div>` + stopControl() + `</div>`;
}

/* Two flag tones, and only signals the payload actually carries: --alert for
   "you are the blocker", --warn for "worth a look", neither for "gone quiet".
   The fixture's stalled/failed flags have no server-side detector, so calm
   mode does not invent them. */
const CALM_TONE = {
  attn: {rank:0, ink:"var(--alert)",
         bg:"color-mix(in oklab,var(--alert) 13%,transparent)",
         bd:"color-mix(in oklab,var(--alert) 34%,transparent)"},
  warn: {rank:1, ink:"var(--warnink)",
         bg:"color-mix(in oklab,var(--warn) 26%,transparent)",
         bd:"color-mix(in oklab,var(--warn) 42%,transparent)"},
  quiet:{rank:3, ink:"var(--ink3)", bg:"transparent", bd:"var(--line)"}
};
const CALM_RAIL = {needs:"var(--alert)", work:"var(--accent)", idle:"var(--line2)"};
const CALM_TASK = {
  in_progress:{glyph:"▸", ink:"var(--accent-ink)", text:"var(--ink)"},
  pending:    {glyph:"·", ink:"var(--ink3)",       text:"var(--ink3)"},
  completed:  {glyph:"✓", ink:"var(--accent-ink)", text:"var(--ink3)"}
};
const CALM_TASK_ORDER = {in_progress:0, pending:1, completed:2};

/* These tables are indexed by strings that come out of the payload, and every
   plain object inherits truthy `constructor`, `toString` and friends from
   Object.prototype — enough to sail straight past an `||` or `??` fallback and
   render `undefined` as a glyph and as a colour. Ask for own properties only. */
function own(table, key, fallback){
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : fallback;
}

/* One ledger row per session. Every session lands in exactly one of the three
   buckets — a ledger that silently drops a row is worse than useless. */
function calmRow(d, x){
  const st = x.state === "needs_input" ? "needs" : (x.state === "working" ? "work" : "idle");
  const ageSec = Math.max(0, d.generated - (x.last_activity || 0));
  const waitSec = Math.max(0, d.generated - (x.blocked_since || x.last_activity || 0));
  const turn = x.turn || null;
  let flag = null, tone = "quiet", why = "";
  if(st === "needs"){
    flag = "your call"; tone = "attn";
    why = "Blocked on you for " + fmtDur(waitSec) +
      " — nothing in this session moves until you answer.";
  } else if(st === "work" && turn && turn.long){
    flag = "long turn"; tone = "warn"; why = LONG_TURN_NOTE;
  } else if(st === "idle" && ageSec >= CALM_STALE_SEC){
    flag = "stale"; tone = "quiet";
    why = "No activity for " + fmtDur(ageSec) + ". Either it finished quietly and " +
      "nobody read the result, or it is waiting on a reply that never came.";
  }
  const title = x.title || x.last_prompt || x.project;
  const prompt = String(x.last_prompt || "").trim();
  const tasks = (x.tasks || []).slice().sort(
    (a, b) => own(CALM_TASK_ORDER, a.status, 3) - own(CALM_TASK_ORDER, b.status, 3));
  const taskDone = tasks.filter(t => t.status === "completed").length;
  const rate = x.rate_per_min || 0;
  return {
    key: sessKey(x), sid: x.sid,
    harness: x.harness, project: x.project, session: x.session,
    st, title, doing: x.state_detail, ageSec, waitSec, turn, flag, tone, why,
    sortAge: st === "work" ? 0 : ageSec,   /* see byAge — a working row's age is noise */
    rail: CALM_RAIL[st] || CALM_RAIL.idle,
    /* The prompt is only worth quoting when the title is not already it. */
    excerpt: (prompt && prompt !== String(title).trim()) ? prompt : "",
    tasks, taskNote: tasks.length ? taskDone + " of " + tasks.length + " done" : "",
    subagents: x.subagents || [], spacedock: x.spacedock || null,
    rank: flag ? CALM_TONE[tone].rank : (st === "work" ? 2 : 4),
    metric: st === "needs" ? fmtDur(waitSec) + " wait"
      : (st === "work" ? (rate ? rate.toLocaleString() + " /m" : "—")
                       : fmtDur(ageSec) + " idle"),
    metricInk: st === "needs" ? "var(--alert)" : (st === "idle" ? "var(--ink3)" : "var(--ink2)"),
    titleInk: st === "idle" ? "var(--ink2)" : "var(--ink)",
    detailAge: st === "needs" ? "blocked " + fmtDur(waitSec)
      : (st === "work" ? "last event " + fmtDur(ageSec) + " ago" : "idle " + fmtDur(ageSec)),
    turnLine: turn ? turn.elapsed_h + " elapsed · " +
      (turn.eta_h ? "~" + turn.eta_h + " left (est)" : "running longer than recent turns") : ""
  };
}

function calmFilter(all){
  return all.filter(r => (!calmFlagOnly || !!r.flag) &&
                         (!calmStateOnly || r.st === calmStateOnly));
}

/* Ordering has to be STABLE across the 5s poll — a row that swaps places under
   the reader's cursor is worse than a row in the wrong place. Age is stable by
   construction everywhere it means something: it is a fixed per-session
   timestamp subtracted from one clock shared by the whole payload, so two idle
   rows keep their relative order forever. The exception is a WORKING row,
   whose last activity is always within WORKING_THRESHOLD_SEC of now — ordering
   those by age sorts on nothing but which one wrote most recently, which flips
   every poll. `sortAge` pins them level (see calmRow) and the session id, which
   never changes, breaks every remaining tie. This is the same call collect()
   makes server-side for the same reason. */
const bySid = (a, b) => (a.sid < b.sid ? -1 : (a.sid > b.sid ? 1 : 0));
const byAge = (a, b) => a.sortAge - b.sortAge || bySid(a, b);
const byRank = (a, b) => a.rank - b.rank || byAge(a, b);

/* Returns display entries: {row} for a session, {divider} for a repo heading. */
function calmEntries(shown){
  if(calmSort === "recent"){
    return shown.slice().sort(byAge).map(r => ({row: r}));
  }
  if(calmSort === "repo"){
    const by = new Map();
    for(const r of shown){
      if(!by.has(r.project)) by.set(r.project, []);
      by.get(r.project).push(r);
    }
    const out = [];
    for(const key of Array.from(by.keys()).sort()){
      const g = by.get(key).sort(byRank);
      out.push({divider: {label: key, count: g.length,
                          flagged: g.filter(r => r.flag).length}});
      for(const r of g) out.push({row: r});
    }
    return out;
  }
  return shown.slice().sort(byRank).map(r => ({row: r}));
}

/* The cursor falls back to the first row rather than being written back into
   calmCursorKey, so a re-sort moves the highlight without stranding state. */
function calmEffectiveFocus(order){
  if(calmCursorKey && order.some(r => r.key === calmCursorKey)) return calmCursorKey;
  return order.length ? order[0].key : null;
}

function calmOrder(d){
  return calmEntries(calmFilter(d.sessions.map(x => calmRow(d, x))))
    .filter(e => e.row).map(e => e.row);
}

function calmMove(step){
  if(!lastData) return;
  const order = calmOrder(lastData);
  if(!order.length) return;
  const i = order.findIndex(r => r.key === calmEffectiveFocus(order));
  calmCursorKey = order[Math.max(0, Math.min(order.length - 1, (i < 0 ? 0 : i + step)))].key;
  calmRevealFocus = true;
  render(lastData);
}

function calmCopyId(key){
  /* The row key identifies the row; the session id is what goes on the
     clipboard. Resolve one to the other rather than carrying both around. */
  const row = lastData ? lastData.sessions.find(x => sessKey(x) === key) : null;
  const sid = row ? row.sid : null;
  if(!sid) return;
  const note = text => {
    calmCopyNote = {key, text};
    if(lastData) render(lastData);
    setTimeout(() => {
      if(!calmCopyNote || calmCopyNote.key !== key) return;
      calmCopyNote = null;
      if(lastData) render(lastData);
    }, 1400);
  };
  const clip = (typeof navigator !== "undefined" && navigator.clipboard &&
                navigator.clipboard.writeText) ? navigator.clipboard.writeText(sid) : null;
  /* Never claim "copied" for a write the browser refused — an unfocused or
     non-secure context rejects, and a silent lie here costs a lost session id. */
  if(clip && typeof clip.then === "function") clip.then(() => note("copied"), () => note("blocked"));
  else note("blocked");
}

function calmAction(act, arg){
  if(act === "mode"){ setDisplayMode(arg); return; }
  if(act === "stop"){
    if(!stopArmed){
      stopArmed = true; stopError = ""; stopFocusPending = true;
      if(lastData) render(lastData);
      return;
    }
    requestStop();
    return;
  }
  if(act === "copy"){ calmCopyId(arg); return; }
  if(act === "sort"){
    if(calmSort === arg) return;
    calmSort = arg; calmResetScroll = true;
  } else if(act === "state"){
    calmStateOnly = calmStateOnly === arg ? null : arg;
    calmOpenKey = null; calmCursorKey = null; calmResetScroll = true;
  } else if(act === "flag"){
    calmFlagOnly = !calmFlagOnly;
    calmOpenKey = null; calmCursorKey = null; calmResetScroll = true;
  } else if(act === "clear"){
    calmFlagOnly = false; calmStateOnly = null; calmResetScroll = true;
  } else if(act === "open"){
    calmOpenKey = calmOpenKey === arg ? null : arg;
    calmCursorKey = arg;
  } else return;
  if(lastData) render(lastData);
}

document.addEventListener("click", e => {
  const el = (e.target && e.target.closest) ? e.target.closest("[data-calm]") : null;
  if(!el){
    /* A click anywhere else is an answer: not that one. */
    if(disarmStop() && lastData) render(lastData);
    return;
  }
  /* So is a click on a different control. Otherwise the armed state outlives
     the moment the reader was answering for — sort the ledger, toggle a mode,
     come back later, and one click would stop the server with no confirmation
     at all, which is the whole thing the second click is here to prevent. */
  const act = el.getAttribute("data-calm");
  if(act !== "stop" && disarmStop() && lastData) render(lastData);
  calmAction(act, el.getAttribute("data-arg"));
});

document.addEventListener("keydown", e => {
  /* The stopped panel is terminal, and a shortcut must not act on it, swallow
     the key, or outlive it. The render() guard stops the paint but not the side
     effects on the way there: setDisplayMode writes localStorage *before* it
     paints, so `c` on the terminal panel appeared to do nothing while durably
     flipping the saved display mode for the next run. */
  if(serverStopped) return;
  if(e.metaKey || e.ctrlKey || e.altKey) return;
  const tag = e.target && e.target.tagName;
  if(tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  const k = e.key;
  const stop = () => { if(e.preventDefault) e.preventDefault(); };
  /* The first activation rebuilds #app to show the armed label. Keep focus on
     its replacement and let Enter/Space reach the button's native click;
     disarming on keydown makes that generated click arm it all over again. */
  if(stopArmed && (k === "Enter" || k === " ") && e.target && e.target.closest &&
     e.target.closest('[data-calm="stop"]')) return;
  if(k === "Escape" && (stopArmed || stopError)){
    /* While armed, Escape answers the stop and does nothing else. */
    stop(); disarmStop(); if(lastData) render(lastData); return;
  }
  /* Every other keystroke answers it too. The keyboard drives the same controls
     the mouse does — `c` is the mode button, `f` the flag, Enter opens a row —
     so disarming only on click left exactly the staleness the second click
     exists to prevent reachable with one hand on the keyboard. */
  if(disarmStop() && lastData) render(lastData);
  /* `c` works in both modes — it is the way back out of calm. */
  if(k === "c"){ stop(); setDisplayMode(displayMode === "calm" ? "regular" : "calm"); return; }
  if(displayMode !== "calm" || !lastData) return;
  /* A focused button already answers Enter and Space itself. */
  if((k === "Enter" || k === " ") && e.target && e.target.closest &&
     e.target.closest("a[href],button,select,textarea,input,[tabindex]")) return;
  if(k === "j" || k === "ArrowDown"){ stop(); calmMove(1); }
  else if(k === "k" || k === "ArrowUp"){ stop(); calmMove(-1); }
  else if(k === "Enter" || k === " "){
    stop();
    const sid = calmEffectiveFocus(calmOrder(lastData));
    if(sid) calmAction("open", sid);
  }
  else if(k === "f"){ stop(); calmAction("flag", null); }
  else if(k === "Escape"){
    stop();
    calmOpenKey = null; calmFlagOnly = false; calmStateOnly = null;
    calmResetScroll = true;
    render(lastData);
  }
});

function calmHarnessCell(r){
  const h = own(HARNESS, r.harness, null) ||
    {code:String(r.harness || "?").slice(0, 2).toUpperCase(), name:r.harness};
  const inner = h.icon
    ? `<span class="cm-ico" style="-webkit-mask:url('${h.icon}') center/contain no-repeat;` +
      `mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="cm-icot">${esc(h.code)}</span>`;
  return `<span class="cm-hcell" title="${esc(h.name || r.harness)}">${inner}</span>`;
}

function calmExpansion(r){
  const tone = CALM_TONE[r.tone] || CALM_TONE.quiet;
  const why = r.flag
    ? `<div class="cm-why"><span class="cm-why-g" style="color:${tone.ink}">◆</span>` +
      `<span class="cm-why-t"><b style="color:${tone.ink}">${esc(r.flag)}</b>` +
      ` — ${esc(r.why)}</span></div>`
    : "";
  const quote = r.excerpt
    ? `<div class="cm-quote"><span class="cm-subk">last prompt</span>` +
      `<div class="cm-quote-t">${esc(r.excerpt)}</div></div>`
    : "";
  const tasks = r.tasks.length
    ? `<div class="cm-tasks"><span class="cm-subk">tasks · ${esc(r.taskNote)}</span>` +
      r.tasks.map(t => {
        const s = own(CALM_TASK, t.status, CALM_TASK.pending);
        const line = (t.status === "in_progress" && t.activeForm)
          ? t.activeForm + "…" : t.subject;
        return `<div class="cm-task"><span class="cm-task-g" style="color:${s.ink}">` +
          `${s.glyph}</span><span class="cm-task-t" style="color:${s.text}"` +
          ` title="${esc(t.subject)}">${esc(line)}</span></div>`;
      }).join("") + `</div>`
    : "";
  const meta = `<div class="cm-meta">` +
    `<span>${esc(own(HARNESS, r.harness, {}).name || r.harness)}</span>` +
    `<span>${esc(r.project)}</span><span>session ${esc(r.session)}</span>` +
    `<span>${esc(r.detailAge)}</span>` +
    (r.tasks.length ? `<span>${esc(r.taskNote)}</span>` : "") + `</div>`;
  const hasPct = !!(r.turn && r.turn.pct != null);
  const turn = r.turn
    ? `<div class="cm-turn"><div class="cm-turn-top"><span class="cm-k">this request</span>` +
      (hasPct ? `<span class="cm-turn-pct">${r.turn.pct}%</span>` : "") + `</div>` +
      (hasPct ? `<div class="cm-turn-track"><span class="cm-fill"` +
        ` style="width:${r.turn.pct}%;background:${r.rail}"></span></div>` : "") +
      `<div class="cm-turn-line">${esc(r.turnLine)}</div></div>`
    : "";
  const subs = r.subagents.length
    ? `<div class="cm-subs"><span class="cm-subk">subagents</span>` +
      r.subagents.slice(0, 8).map(a => `<div class="cm-sub"><span class="cm-sub-dot"></span>` +
        `<span class="cm-sub-n" title="${esc(a)}">${esc(a)}</span></div>`).join("") +
      (r.subagents.length > 8
        ? `<div class="cm-sub"><span class="cm-sub-n">+${r.subagents.length - 8} more</span></div>`
        : "") + `</div>`
    : "";
  const copied = calmCopyNote && calmCopyNote.key === r.key;
  const acts = `<div class="cm-acts"><button type="button" class="cm-act" data-calm="copy"` +
    ` data-arg="${esc(r.key)}">${copied ? esc(calmCopyNote.text) : "copy id"}</button>` +
    `<button type="button" class="cm-act" data-calm="open"` +
    ` data-arg="${esc(r.key)}">collapse</button></div>`;
  return `<div class="cm-exp"><div class="cm-exp-main">${why}${quote}${tasks}` +
    sdBlock({spacedock: r.spacedock}) + meta + `</div>` +
    `<div class="cm-exp-side">${turn}${subs}${acts}</div></div>`;
}

function calmRowHTML(r, focusSid){
  const open = calmOpenKey === r.key;
  const focus = r.key === focusSid;
  const tone = CALM_TONE[r.tone] || CALM_TONE.quiet;
  const pct = (r.turn && r.turn.pct != null) ? r.turn.pct : null;
  const signal = (r.st === "work" && pct != null)
    ? `<span class="cm-track" role="img" aria-label="request ${pct} percent complete">` +
      `<span class="cm-fill" style="width:${pct}%;background:${r.rail}"></span></span>`
    : "";
  const flag = r.flag
    ? `<span class="cm-flag" style="background:${tone.bg};color:${tone.ink};` +
      `border-color:${tone.bd}">${esc(r.flag)}</span>`
    : "";
  const copied = calmCopyNote && calmCopyNote.key === r.key;
  return `<div class="cm-item"><div class="cm-row${focus ? " focus" : ""}${open ? " open" : ""}"` +
    ` data-calm="open" data-arg="${esc(r.key)}" role="button" aria-expanded="${open}">` +
    (focus ? `<span class="cm-cursor"></span>` : "") +
    `<span class="cm-rail" style="background:${r.rail}"></span>` +
    calmHarnessCell(r) +
    `<span class="cm-title" style="color:${r.titleInk}"` +
    ` title="${esc(r.title)}">${esc(r.title)}</span>` +
    /* Real project names fill the whole cell, and tail truncation would eat the
       session id — the part that identifies the row. Only the project gives way. */
    `<span class="cm-where" title="${esc(r.project + " · " + r.session)}">` +
    `<span class="cm-proj">${esc(r.project)}</span>` +
    `<span class="cm-sess">· ${esc(r.session)}</span></span>` +
    `<span class="cm-doing" title="${esc(r.doing)}">${esc(r.doing)}</span>` +
    `<span>${flag}</span><span>${signal}</span>` +
    `<span class="cm-metric" style="color:${r.metricInk}">${esc(r.metric)}</span>` +
    `<span class="cm-q"><button type="button" class="cm-qb" data-calm="copy"` +
    ` data-arg="${esc(r.key)}" title="copy this session's id">` +
    `${copied ? esc(calmCopyNote.text) : "id"}</button></span>` +
    `<span class="cm-caret">${open ? "–" : "+"}</span></div>` +
    (open ? calmExpansion(r) : "") + `</div>`;
}

function calmLedger(d){
  const all = d.sessions.map(x => calmRow(d, x));
  const shown = calmFilter(all);
  const entries = calmEntries(shown);
  const focusSid = calmEffectiveFocus(entries.filter(e => e.row).map(e => e.row));
  const count = st => all.filter(r => r.st === st).length;
  const chip = (st, label, dot) =>
    `<button type="button" class="cm-chip${calmStateOnly === st ? " on" : ""}"` +
    ` data-calm="state" data-arg="${st}" aria-pressed="${calmStateOnly === st}">` +
    dot + count(st) + " " + label + `</button>`;
  const legend =
    chip("needs", "needs you", `<span class="cm-dot" style="background:var(--alert)"></span>`) +
    chip("work", "working", `<span class="cm-dot" style="background:var(--accent)"></span>`) +
    chip("idle", "idle", `<span class="cm-dot hollow"></span>`);
  const sorts = ["attention", "recent", "repo"].map(k =>
    `<button type="button" class="cm-segb${calmSort === k ? " on" : ""}" data-calm="sort"` +
    ` data-arg="${k}" aria-pressed="${calmSort === k}">${k}</button>`).join("");
  const flagged = all.filter(r => r.flag).length;
  const clear = (calmFlagOnly || calmStateOnly)
    ? `<button type="button" class="cm-clear" data-calm="clear">clear</button>` : "";
  const note = shown.length === all.length
    ? "showing all " + all.length
    : "showing " + shown.length + " of " + all.length;

  let body;
  if(!shown.length && !all.length){
    body = `<div class="cm-empty"><span class="cm-subk">all quiet</span>` +
      `<div class="cm-empty-t">No session activity in the last ${esc(d.window_hours)}h.` +
      (d.show_all ? "" : ` <a href="?all=1">Show all sessions</a>`) + `</div></div>`;
  } else if(!shown.length){
    body = `<div class="cm-empty"><span class="cm-subk">all quiet</span>` +
      `<div class="cm-empty-t">Nothing matches this filter. ` +
      `<button type="button" class="cm-link" data-calm="clear">Show all ${all.length}` +
      `</button></div></div>`;
  } else {
    body = entries.map(e => e.row ? calmRowHTML(e.row, focusSid)
      : `<div class="cm-div"><span class="cm-div-k">${esc(e.divider.label)}</span>` +
        `<span class="cm-div-n">${e.divider.count}</span>` +
        `<span class="cm-div-rule"></span>` +
        (e.divider.flagged ? `<span class="cm-div-f">◆ ${e.divider.flagged}</span>` : "") +
        `</div>`).join("");
  }

  const found = (d.harnesses || []).filter(h => h.discovered);
  const strip = (d.harnesses || []).map(h => badge(h.key, h.discovered && !h.error, h.label,
    h.error ? " — collector error" : (h.discovered ? "" : " — no data"))).join("");
  return `<div class="cm-frame">` +
    `<div class="cm-bar"><span class="cm-brand">Cargento</span>` +
    `<div class="cm-legend">${legend}</div><span class="cm-sp"></span>` +
    `<span class="cm-live"><span class="live" id="live-dot"></span>` +
    `<span id="live-status">auto-refresh 5s · ` +
    `${new Date(d.generated*1000).toLocaleTimeString()}</span>` +
    (d.show_all ? `<span>· showing all</span>` : "") + notifyControl(d) + `</span></div>` +
    `<div class="cm-ctl"><span class="cm-k">order</span><div class="cm-seg">${sorts}</div>` +
    `<span class="cm-vr"></span>` +
    `<button type="button" class="cm-flagchip${calmFlagOnly ? " on" : ""}" data-calm="flag"` +
    ` aria-pressed="${calmFlagOnly}">◆ ${flagged} flagged</button>${clear}` +
    `<span class="cm-sp"></span><span class="cm-note">${esc(note)}</span></div>` +
    `<div class="cm-body" id="cm-body">` +
    `<div class="cm-head"><span></span><span></span><span>session</span><span>where</span>` +
    `<span>doing</span><span>flag</span><span>turn</span><span class="r">signal</span>` +
    `<span></span><span></span></div>${body}</div>` +
    `<div class="cm-foot"><span>${all.length} sessions · ${found.length} harnesses · ` +
    `${(d.summary.rate_per_min || 0).toLocaleString()} tok/min</span>` +
    `<span class="cm-fstrip">${strip}</span><span class="cm-sp"></span>` +
    `<span class="cm-keys"><span><span style="color:var(--alert)">◆</span>you are the blocker` +
    `</span><span><span style="color:var(--warnink)">◆</span>running long</span>` +
    `<span><span>◇</span>gone quiet</span></span><span class="cm-sp"></span>` +
    `<span class="cm-keys"><span>j k move</span><span>⏎ expand</span><span>f flagged</span>` +
    `<span>c mode</span><span>esc clear</span></span></div></div>`;
}

/* Every control the ledger emits is identified by its (data-calm, data-arg)
   pair, which survives the DOM swap even though the element does not. Capture
   the focused one before the swap and hand focus back to its replacement, the
   way restoreSparkState does for the sparkline — otherwise tabbing into the
   ledger is undone by the next poll, five seconds later at most. */
function calmFocusKey(){
  const el = document.activeElement;
  if(!el || !el.getAttribute) return null;
  const act = el.getAttribute("data-calm");
  return act ? {act, arg: el.getAttribute("data-arg")} : null;
}

function calmRestoreFocus(key){
  if(!key) return;
  const root = document.getElementById("app");
  /* Matched by attribute in JS rather than through a built selector: `arg` is a
     session id, and a selector string would need escaping the DOM does not. */
  if(!root || !root.querySelectorAll) return;
  for(const el of root.querySelectorAll("[data-calm]")){
    if(el.getAttribute("data-calm") !== key.act) continue;
    if(el.getAttribute("data-arg") !== key.arg) continue;
    if(el.focus) el.focus({preventScroll: true});
    return;
  }
}

/* render() replaces #app wholesale every poll, which resets the ledger's own
   scroll offset. Put it back, then bring the keyboard cursor into view if the
   last action moved it. */
function calmRestoreScroll(){
  const body = document.getElementById("cm-body");
  if(!body) return;
  body.scrollTop = calmScrollTop;
  if(calmRevealFocus){
    calmRevealFocus = false;
    const row = body.querySelector ? body.querySelector(".cm-row.focus") : null;
    if(row && row.scrollIntoView) row.scrollIntoView({block: "nearest"});
  }
  calmScrollTop = body.scrollTop;
}

/* Desktop notifications.
   Exactly one layer notifies for a given transition. The server fires an
   OS-level popup where it has a backend and reports that as `native_notify`;
   the page raises its own only when the server cannot. Without that split,
   macOS would pop twice for every blocked session. */
let notifyState = new Map();  /* harness:sid -> last state seen */
let notifyPrimed = false;     /* first payload only records: nothing is "new" yet */

function notifySupported(){ return typeof Notification !== "undefined"; }

function notifyPermission(){
  return notifySupported() ? (Notification.permission || "default") : "unsupported";
}

function browserNotifyOwns(d){ return !(d && d.native_notify) && notifySupported(); }

function requestNotifyPermission(){
  if(!notifySupported() || !Notification.requestPermission) return;
  /* Re-render so the control reflects the new permission. Both the callback
     and promise forms are handled; Safari still uses the callback. */
  const done = () => { if(lastData) render(lastData); };
  let result;
  try{ result = Notification.requestPermission(done); }catch(e){ return; }
  if(result && typeof result.then === "function") result.then(done, done);
}

function syncNotifications(d){
  const seen = new Map();
  const fire = browserNotifyOwns(d) && notifyPermission() === "granted";
  for(const s of d.sessions){
    const key = s.harness + ":" + s.sid;
    seen.set(key, s.state);
    if(!fire || !notifyPrimed) continue;
    /* Same rule the server uses: notify on the transition into needs_input,
       not for every refresh a session spends blocked. */
    if(!s.active || s.state !== "needs_input") continue;
    if(notifyState.get(key) === "needs_input") continue;
    try{
      new Notification("Claude is waiting on you",
        {body: "[" + s.project + "] " + (s.state_detail || "needs your input"),
         tag: key});  /* tag replaces a stale popup instead of stacking */
    }catch(e){ /* permission revoked mid-session, or a headless browser */ }
  }
  notifyState = seen;  /* sessions that disappeared stop being tracked */
  notifyPrimed = true;
}

function notifyControl(d){
  if(!browserNotifyOwns(d)) return "";
  const p = notifyPermission();
  if(p === "granted" || p === "unsupported") return "";
  if(p === "denied"){
    return ` · <span class="notify-note" title="Re-enable notifications for this ` +
      `site in your browser's settings to be alerted when a session needs you.">` +
      `notifications blocked</span>`;
  }
  return ` · <button type="button" class="notify-btn" onclick="requestNotifyPermission()">` +
    `Enable notifications</button>`;
}

function render(d){
  /* The stopped panel is terminal, and this is the sink that would undo it.
     Guarding refresh() alone was not enough: fourteen other call sites end in
     render(lastData) — setDisplayMode, toggleIdle, calmAction, calmCopyId, the
     keyboard — and the keydown listener is on `document`, so nothing in #app
     gates it. One `c` was enough to repaint a live-looking board, stale
     needs-input count back in the title, for a server that is gone.

     This covers every DOM write below it, which is all of them except two
     places that need their own check and have one: renderStopped(), which is
     the panel, and refresh()'s catch arm, which writes #app and the live-status
     text without going through here. */
  if(serverStopped) return;
  lastData = d;
  syncNotifications(d);
  const app = document.getElementById("app");
  const needs = d.sessions.filter(x => x.active && x.state === "needs_input");
  if(!app){
    document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
    return;
  }
  if(displayMode === "calm"){
    // Carry the outgoing ledger's scroll offset across the DOM swap — unless
    // the last action re-filtered the list, where the old offset is meaningless.
    const outgoing = document.getElementById("cm-body");
    if(calmResetScroll){ calmScrollTop = 0; calmResetScroll = false; }
    else if(outgoing) calmScrollTop = outgoing.scrollTop;
    const focusKey = calmFocusKey();
    renderInProgress = true;
    app.className = "wrap calm";
    app.innerHTML = modeBar() + calmLedger(d);
    renderInProgress = false;
    calmRestoreScroll();
    calmRestoreFocus(focusKey);
    restoreStopFocus();
    document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
    return;
  }
  const sparkFocused = !!(document.activeElement && document.activeElement.id === "spark-main");
  // Capture pointer position before render so we can restore it afterward, even if
  // pointermove fires during the render operation.
  const savedPointer = sparkPointer ? {x: sparkPointer.x, y: sparkPointer.y} : null;
  const s = d.summary;
  const working = d.sessions.filter(x => x.state === "working");
  const idle = d.sessions.filter(x => x.state === "idle");

  const needsVal = needs.length > 0
    ? `<div class="tile-val alert">${needs.length}</div>`
    : `<div class="tile-val">0</div>`;
  const tiles =
    `<div class="tile"><div class="tile-label">Needs you</div>${needsVal}` +
      `<div class="tile-sub">sessions blocked on you</div></div>` +
    `<div class="tile"><div class="tile-label">Working now</div>` +
      `<div class="tile-val">${s.working}</div><div class="tile-sub">sessions generating</div></div>` +
    rateTile(d);

  const subnote = s.total_tasks
    ? `<span>open tasks <b>${s.open_tasks}</b></span><span class="div"></span>` +
      `<span>progress <b>${s.progress_pct}%</b></span><span class="div"></span>` +
      `<span>${s.total_done}/${s.total_tasks} tracked tasks done</span>`
    : `<span>open tasks <b>–</b></span><span class="div"></span>` +
      `<span>progress <b>–</b></span><span class="div"></span>` +
      `<span>no active session uses tracked tasks</span>`;

  const bandHtml = needs.length
    ? `<div class="band"><div class="band-head"><span class="band-dot"></span>` +
      `<span class="band-k">Needs your input</span></div>` +
      needs.map(n => needRow(d, n)).join("") + `</div>`
    : "";

  let workingHtml = "";
  if(working.length){
    workingHtml = `<div class="stack"><div class="sec"><span class="sec-k">Working now</span>` +
      `<span class="sec-count">${working.length}</span><span class="sec-rule"></span></div>` +
      working.map(s => workingCard(d, s)).join("") + `</div>`;
  } else if(d.sessions.length){
    workingHtml = `<div class="stack"><div class="sec"><span class="sec-k">Working now</span>` +
      `<span class="sec-count">0</span><span class="sec-rule"></span></div>` +
      `<div class="empty">No sessions generating right now — every agent is idle or waiting.</div></div>`;
  }

  let idleHtml = "";
  if(idle.length){
    const maxh = idleExpanded ? "3000px" : "184px";
    const fade = idleExpanded ? "" : `<div class="idle-fade"></div>`;
    const rows = idle.map(x => idleRow(d, x)).join("");
    idleHtml = `<div class="stack"><div class="sec"><span class="sec-k">Idle</span>` +
      `<span class="sec-count">${idle.length}</span><span class="sec-rule"></span></div>` +
      `<div class="idle-wrap"><div class="idle-clip" style="max-height:${maxh}">${rows}${fade}</div>` +
      `<div class="idle-toggle-wrap"><button class="idle-toggle" onclick="toggleIdle()">` +
      `${idleExpanded ? "Show less" : "Show all " + idle.length + " idle"}</button></div></div></div>`;
  }

  let body;
  if(!d.sessions.length){
    body = `<div class="empty">No session activity in the last ${esc(d.window_hours)}h.` +
      (d.show_all ? "" : ` <a href="?all=1">Show all sessions</a>`) + `</div>`;
  } else {
    body = `<div class="hero">${tiles}</div><div class="subnote">${subnote}</div>` +
      bandHtml + workingHtml + idleHtml;
  }

  renderInProgress = true;
  app.className = "wrap";
  app.innerHTML = modeBar() +
    `<div class="top"><div><div class="brand">Cargento</div>` +
    `<div class="sub"><span class="live" id="live-dot"></span>` +
    `<span id="live-status">live · updated ${new Date(d.generated*1000).toLocaleTimeString()} · auto-refresh 5s</span>` +
    (d.show_all ? " · showing all" : "") + notifyControl(d) + `</div></div>` +
    `<div class="hstrip">${harnessStrip(d.harnesses)}</div></div>` + body;
  renderInProgress = false;

  restoreSparkState(sparkFocused, savedPointer);
  restoreStopFocus();
  document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
}

async function refresh(){
  /* Checked twice, and both are load-bearing: this one skips a poll that would
     start after the stop, and the ones below drop a poll that was already in
     flight when the stop landed. Without those, the reply settles after
     renderStopped() and repaints a live-looking dashboard over the terminal
     panel — with the interval already cleared, so not even the stalled banner
     would contradict it. /api/data is the slow request here; the shutdown POST
     is a loopback round trip. */
  if(serverStopped) return;
  const sequence = ++refreshSequence;
  try{
    const r = await fetch("/api/data" + (showAll ? "?all=1" : ""));
    if(!r.ok) throw new Error("bad status");
    const data = await r.json();
    if(serverStopped) return;
    if(sequence < latestSettledRefresh) return;
    latestSettledRefresh = sequence;
    recordRates(data);
    render(data);
    window.__refreshFailures = 0;
  }catch(e){
    if(serverStopped) return;
    if(window.__SAMPLE){ recordRates(window.__SAMPLE); render(window.__SAMPLE); return; }
    if(sequence < latestSettledRefresh) return;
    latestSettledRefresh = sequence;
    console.error("dashboard refresh failed", e);
    window.__refreshFailures = (window.__refreshFailures || 0) + 1;
    const app = document.getElementById("app");
    if(app && !lastData){
      app.innerHTML = `<div class="empty">refresh failed — is the server running?</div>`;
      return;
    }
    if(window.__refreshFailures < 2) return;
    const dot = document.getElementById("live-dot");
    const status = document.getElementById("live-status");
    if(dot) dot.classList.add("stalled");
    if(status){
      const updated = new Date(lastData.generated*1000).toLocaleTimeString();
      status.textContent = `stalled · last update ${updated} · retrying every 5s`;
    }
  }
}
refresh();
let refreshTimer = setInterval(refresh, 5000);
</script>
</body>
</html>
"""


# (window_hours, show_all) -> {"ts": epoch, "body": bytes}
_collect_memo: dict[tuple[float, bool], dict[str, Any]] = {}
_collect_memo_lock = threading.Lock()
COLLECT_MEMO_SEC = 2.5  # multiple tabs / curl loops share one scan per window


def collect_json(window_hours: float, show_all: bool) -> bytes:
    key = (window_hours, show_all)
    with _collect_memo_lock:
        cached = _collect_memo.get(key)
        if cached and time.time() - cached["ts"] < COLLECT_MEMO_SEC:
            body: bytes = cached["body"]
            return body
        # Hold the lock through collection: ThreadingHTTPServer callers share
        # one filesystem/SQLite scan rather than stampeding cold cache entries.
        body = json.dumps(collect(window_hours, show_all)).encode()
        _collect_memo[key] = {"ts": time.time(), "body": body}
        return body


# ── process lifecycle: state file, health probe, detaching, stopping ────────
# Cargento is started by an agent and outlives the session that started it, so
# it needs the three things a supervised process gets for free: a way to be
# found, a way to be asked whether it is alive, and a way to be stopped. See
# docs/design-daemon.md.

CARGENTO_HOME_ENV = "CARGENTO_HOME"
DAEMON_READY_TIMEOUT_SEC = 10.0
# How long --stop waits for the port to come free after the server agrees to
# stop. Generously above the 0.5s serve_forever() poll interval it waits on.
STOP_RELEASE_TIMEOUT_SEC = 5.0
# Anything larger in a state file is not a state file. write_state produces a
# few hundred bytes; the cap is what keeps a corrupt one cheap to reject.
STATE_READ_CAP_BYTES = 65536

# Resolved through getattr, never referenced directly: `os.fork` and
# `os.setsid` do not exist on Windows, and a module-level `os.fork` reference
# would fail at import there — including under mypy, which checks both
# platforms.
_FORK: Callable[[], int] | None = getattr(os, "fork", None)
_SETSID: Callable[[], int] | None = getattr(os, "setsid", None)


def tcp_port(value: str) -> int:
    """An argparse type for a real TCP port, rather than any Python integer."""
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer from 1 to 65535") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be from 1 to 65535")
    return port


def cargento_home() -> str:
    """Where the state file and the daemon log live.

    One layout on every platform. Platform-correct runtime directories
    (XDG_RUNTIME_DIR, %LOCALAPPDATA%) would be three code paths and three ways
    for --status to look somewhere the server never wrote. A nonblank
    CARGENTO_HOME is authoritative, which is the rule the harness store
    variables in STORE_ENV_VARS already follow.
    """
    override = os.environ.get(CARGENTO_HOME_ENV)
    return override if override and override.strip() else os.path.join(HOME, ".cargento")


def state_path(port: int) -> str:
    return os.path.join(cargento_home(), f"cargento-{port}.json")


def log_path(port: int) -> str:
    return os.path.join(cargento_home(), f"cargento-{port}.log")


def ensure_cargento_home() -> str:
    """Create the state directory, owner-only, and return it.

    0o700 because the log carries tracebacks with local paths in them. The mode
    is advisory: it does not apply to a directory that already exists, and
    Windows ignores it.
    """
    home = cargento_home()
    os.makedirs(home, mode=0o700, exist_ok=True)
    return home


def write_state(port: int) -> None:
    """Record this process as the instance serving `port`.

    Written by every instance that binds, daemon or foreground: --status and
    --stop are worth having either way, and a file that exists only sometimes
    is a file whose absence tells you nothing.

    Written through a temp file and os.replace so a reader mid-write sees the
    old file or the new one, never half of one.
    """
    payload = {
        "pid": os.getpid(),
        "port": port,
        "started": SERVER_STARTED,
        "log": log_path(port),
        "python": sys.executable,
    }
    target = state_path(port)
    tmp = f"{target}.{os.getpid()}.tmp"
    try:
        ensure_cargento_home()
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, target)
    except OSError as exc:
        diag(f"Cargento: could not write {target} ({exc}); --status will not see this instance")
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def read_state(port: int) -> dict[str, Any] | None:
    """The recorded state for `port`, or None if there is none to trust.

    Read to a cap and with RecursionError caught, because "none to trust" has to
    include a corrupt file and not just a missing one. The payload write_state
    produces is a few hundred bytes; deeply nested JSON blows the recursion
    limit rather than raising ValueError, which tracebacked straight out of
    --status and --stop. do_POST already catches RecursionError for the same
    reason on the same parser.
    """
    try:
        with open(state_path(port), "rb") as handle:
            raw = handle.read(STATE_READ_CAP_BYTES + 1)
        if len(raw) > STATE_READ_CAP_BYTES:
            return None
        data = json.loads(raw or b"null")
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def remove_state(port: int) -> None:
    with contextlib.suppress(OSError):
        os.unlink(state_path(port))


def probe_port(port: int, timeout: float = 1.0) -> tuple[str, dict[str, Any] | None]:
    """What is listening on `port`: Cargento, something else, or nothing.

    Returns ("cargento", health) | ("foreign", None) | ("closed", None).

    The distinction is the entire point of this function. "Something is
    listening" reading as "Cargento is running" is how a stop command ends up
    aimed at an unrelated local server.
    """
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", "/api/health")
        response = conn.getresponse()
        body = response.read(4096)
        if response.status != 200:
            return ("foreign", None)
        data = json.loads(body)
    except (OSError, http.client.HTTPException):
        return ("closed", None)
    except (ValueError, RecursionError):
        return ("foreign", None)  # answered 200 with something that is not JSON
    finally:
        conn.close()
    if not isinstance(data, dict):
        return ("foreign", None)
    pid = data.get("pid")
    reported_port = data.get("port")
    started = data.get("started")
    if (
        data.get("ok") is not True
        or not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or not isinstance(reported_port, int)
        or isinstance(reported_port, bool)
        or reported_port != port
        or not isinstance(started, int | float)
        or isinstance(started, bool)
        or not math.isfinite(started)
    ):
        return ("foreign", None)
    return ("cargento", data)


def port_released(port: int) -> bool:
    """Whether a new listener could take `port` — the question --stop's caller
    actually has, since what follows a stop is usually a start.

    By binding, because binding is the question. Tried and rejected: a TCP
    connect probe. Connecting to a listening socket that nothing is accepting
    from still completes, so it cannot see the window between `serve_forever()`
    returning and `server_close()` running — and worse, each probe leaves an
    unaccepted connection in the backlog, so after `request_queue_size` of them
    the probe starts reporting "gone" for a port that is still bound. Same
    reuse semantics as the real listener, so this answers for that listener and
    not for a hypothetical one with different options.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if reuse_address_allowed(os.name):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Windows-only, and the same option LoopbackHTTPServer.server_bind
            # sets. Without it the probe is more permissive than the listener it
            # answers for: a foreign socket holding the port with SO_REUSEADDR
            # admits a plain bind but not an exclusive one, so the probe would
            # report a port released that the real listener cannot take.
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive is not None:
                sock.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            sock.bind(("127.0.0.1", port))
    except OSError as exc:
        # Only "the address is in use" is evidence the port is held. EACCES on a
        # privileged port, or an exhausted fd table, says nothing about use —
        # and answering False there made --stop sit out its entire timeout and
        # then report an instance still listening when it had already stopped.
        # Where a bind cannot answer the question, say so by answering True: the
        # caller is deciding whether to keep waiting, not whether to trust it.
        winerror = getattr(exc, "winerror", None)
        if exc.errno == errno.EADDRINUSE or winerror == 10048:  # WSAEADDRINUSE
            return False
        # On Windows an in-use port also reports EACCES once SO_EXCLUSIVEADDRUSE
        # is in play — the same ambiguity bind_error_message already names.
        return not (os.name == "nt" and (exc.errno == errno.EACCES or winerror == 10013))
    return True


def await_release(port: int, timeout: float | None = None) -> bool:
    """Wait for `port` to become bindable. Returns whether it did.

    Always probes at least once, so a zero timeout still answers.

    The default is read here rather than bound in the signature: a default
    evaluated at import cannot be patched, so a caller lowering
    STOP_RELEASE_TIMEOUT_SEC — every test that does — silently waited the full
    five seconds anyway.
    """
    deadline = time.monotonic() + (STOP_RELEASE_TIMEOUT_SEC if timeout is None else timeout)
    while True:
        if port_released(port):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def instance_status(port: int) -> dict[str, Any]:
    """Whether Cargento is on `port`, and what to say about it if not."""
    kind, health = probe_port(port)
    state = read_state(port)
    recorded_log = (state or {}).get("log") or log_path(port)
    if kind == "cargento" and health is not None:
        return {
            "state": "running",
            "port": port,
            "pid": health["pid"],
            "started": health.get("started"),
            "log": recorded_log,
        }
    if kind == "foreign":
        return {"state": "foreign", "port": port, "pid": (state or {}).get("pid")}
    return {
        "state": "stale" if state is not None else "absent",
        "port": port,
        "pid": (state or {}).get("pid"),
        "log": recorded_log,
    }


def render_status(status: dict[str, Any]) -> str:
    """One line describing an instance, for --status and --stop."""
    port = status["port"]
    state = status["state"]
    if state == "running":
        started = status.get("started")
        since = "unknown"
        if isinstance(started, int | float) and started:
            # `started` arrives from whatever answered /api/health — the one
            # process probe_port has just declined to take on trust. A value
            # outside time_t, or NaN, raises here rather than printing a line.
            with contextlib.suppress(OverflowError, ValueError, OSError):
                since = datetime.fromtimestamp(started, tz=UTC).astimezone().strftime("%H:%M")
        return (
            f"Cargento: running on port {port} (pid {status['pid']}, since {since}) "
            f"http://127.0.0.1:{port}/"
        )
    if state == "foreign":
        return (
            f"Cargento: port {port} is held by another process — what answered "
            f"/api/health is not Cargento. Nothing was stopped or removed."
        )
    if state == "stale":
        return (
            f"Cargento: not running on port {port}. A stale state file remains "
            f"(pid {status['pid']}); --stop removes it."
        )
    return f"Cargento: not running on port {port}."


def stop_instance(port: int) -> tuple[str, int]:
    """Ask the instance on `port` to stop. Returns (message, exit code).

    Over HTTP, the same route the page's stop button uses — one implementation
    of stopping, and no per-platform signal semantics to reconcile. A server
    wedged badly enough not to serve cannot be stopped this way; SKILL.md keeps
    the platform kill commands for that.
    """
    status = instance_status(port)
    state = status["state"]
    if state == "foreign":
        # The state file is evidence about a port we do not own. Leave it.
        return (render_status(status), 1)
    if state == "running":
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        failure = ""
        answered: int | None = None
        try:
            conn.request("POST", "/api/shutdown", body=b"", headers={"Content-Length": "0"})
            response = conn.getresponse()
            response.read(1024)
            answered = response.status
        except (OSError, http.client.HTTPException) as exc:
            # Not evidence the stop failed. A concurrent --stop, or the page's
            # own button, may already have taken the server down while this
            # request was in flight — which reset the connection and reported a
            # failure for a stop that had in fact just happened. Let the port
            # decide instead of this connection.
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            conn.close()
        if answered is not None and answered != 200:
            return (f"Cargento: the instance on port {port} refused to stop ({answered}).", 1)
        # Do not claim it stopped until the port is actually free. The handler
        # answers before shutting down, `shutdown()` takes up to one poll
        # interval to be noticed, and the listening socket closes only after
        # serve_forever() returns — so returning on the 200 alone reported a
        # completed stop while the port was still bound, and the obvious restart
        # (--stop then start again) failed on a busy port.
        if not await_release(port):
            if failure:
                return (f"Cargento: could not stop port {port} — {failure}", 1)
            return (
                (
                    f"Cargento: asked the instance on port {port} (pid {status['pid']}) to "
                    f"stop, and it agreed, but it was still listening "
                    f"{STOP_RELEASE_TIMEOUT_SEC:.0f}s later. Check --status before restarting."
                ),
                1,
            )
        return (f"Cargento: stopped (pid {status['pid']}) on port {port}.", 0)
    # Nothing answered /api/health, which is not the same as nothing holding the
    # port: main() removes the state file *before* it closes the listener, so a
    # stop already in progress lands here with the port still bound. Exit 0 has
    # to mean a new listener can take the port, or the unconditional
    # --stop-then-start this promises is not safe.
    if not await_release(port):
        return (
            (
                f"Cargento: nothing on port {port} answers /api/health, but something is "
                f"still holding the port. Nothing was stopped or removed."
            ),
            1,
        )
    if state == "stale":
        remove_state(port)
        return (f"Cargento: nothing running on port {port}; removed the stale state file.", 0)
    # Nothing there and nothing recorded. Stopping is idempotent on purpose:
    # a script that calls --stop unconditionally should not fail for it.
    return (f"Cargento: nothing running on port {port}.", 0)


def fork_daemon(
    *,
    fork: Callable[[], int] | None = None,
    setsid: Callable[[], int] | None = None,
    exit_intermediate: Callable[[int], None] | None = None,
) -> tuple[str, int]:
    """Split this process into a detached daemon and a reporting parent.

    Returns ("parent", read_fd) in the original process, which must report what
    the daemon says and then exit, and ("daemon", write_fd) in the detached
    process, which must serve.

    Why the parent reports rather than the daemon: an agent's shell tool stops
    capturing output when the process it waited for exits, so a line printed by
    the detached child afterwards is simply lost. The pipe also makes the
    report *true* — the parent says "running" because the daemon said so.

    Why two forks: the first detaches from the caller, setsid leaves the
    session and its controlling terminal, and the second means the daemon is
    not a session leader, so it can never reacquire one.

    The hooks exist so the call sequence can be asserted without a test suite
    that forks itself.
    """
    do_fork = fork or _FORK
    do_setsid = setsid or _SETSID
    do_exit = exit_intermediate or os._exit
    if do_fork is None or do_setsid is None:  # pragma: no cover — POSIX-only path
        raise RuntimeError("--daemon needs fork/setsid; use the Windows re-spawn path")
    read_fd, write_fd = os.pipe()
    if do_fork() > 0:
        os.close(write_fd)
        return ("parent", read_fd)
    os.close(read_fd)
    do_setsid()
    if do_fork() > 0:
        do_exit(0)
    return ("daemon", write_fd)


def daemon_redirect_stdio(log_file: str) -> None:
    """Point stdio at the log, once there is nothing left to say on the terminal.

    dup2 rather than reassigning sys.stdout: writes from C and an uncaught
    traceback go to fd 1 and 2 directly, and those are exactly the output a
    detached failure leaves behind.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "rb") as devnull:
        os.dup2(devnull.fileno(), 0)
    with open(log_file, "ab", buffering=0) as handle:
        os.dup2(handle.fileno(), 1)
        os.dup2(handle.fileno(), 2)


def daemon_announce(write_fd: int) -> None:
    """Tell the waiting parent this process is serving, and how to name it."""
    with contextlib.suppress(OSError):
        os.write(write_fd, f"{os.getpid()}\n".encode())
    with contextlib.suppress(OSError):
        os.close(write_fd)


def await_daemon(
    read_fd: int, port: int, log_file: str, timeout: float = DAEMON_READY_TIMEOUT_SEC
) -> tuple[str, int]:
    """Wait for the forked daemon's pid. Returns (message, exit code).

    POSIX only, and unreachable elsewhere: select() on Windows accepts sockets
    and nothing else, so watching a pipe fd raises there. main() gives Windows
    the re-spawn path and await_spawned instead.
    """
    deadline = time.monotonic() + timeout
    seen = b""
    died = False
    pipe_error: OSError | None = None
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([read_fd], [], [], 0.1)
            if not ready:
                continue
            chunk = os.read(read_fd, 64)
            if not chunk:
                died = True  # closed the pipe without announcing
                break
            seen += chunk
            if b"\n" in seen:
                break
    except OSError as exc:
        seen = b""
        pipe_error = exc
    finally:
        with contextlib.suppress(OSError):
            os.close(read_fd)
    pid = seen.strip().decode("ascii", "replace")
    if pid.isdigit():
        return (f"Cargento: http://127.0.0.1:{port}/ (pid {pid}, log {log_file})", 0)
    if pipe_error is not None:
        return (
            (
                f"Cargento: could not read the background server's readiness pipe "
                f"({type(pipe_error).__name__}: {pipe_error}) — check {log_file}."
            ),
            1,
        )
    if died:
        # Distinguished from the timeout because it is a different thing to go
        # and look at, and reporting a 10s wait that in fact took a moment sent
        # readers hunting for a hang that never happened.
        return (
            (
                f"Cargento: the background server exited before it began serving. "
                f"Its output was:\n{log_tail(log_file)}"
            ),
            1,
        )
    return (
        (
            f"Cargento: started in the background, but it did not report ready "
            f"within {timeout:.0f}s — check {log_file}."
        ),
        1,
    )


def forwarded_args(args: argparse.Namespace) -> list[str]:
    """The flags a re-spawned child needs — built from parsed values, not sys.argv.

    --daemon is deliberately absent: the child is an ordinary foreground run
    that happens to own no console, and forwarding the flag would re-spawn
    forever. Rebuilding from the namespace rather than filtering argv means a
    future flag has to be added here consciously.
    """
    forwarded = ["--port", str(args.port), "--window-hours", str(args.window_hours)]
    if args.no_spacedock:
        forwarded.append("--no-spacedock")
    return forwarded


def spawn_detached(args: argparse.Namespace, log_file: str) -> subprocess.Popen[bytes]:
    """Re-spawn this script with no console attached (Windows has no fork)."""
    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    with open(log_file, "ab", buffering=0) as handle:
        return subprocess.Popen(  # noqa: S603 — fixed argv from parsed flags, no shell
            [sys.executable, os.path.abspath(__file__), *forwarded_args(args)],
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=handle,
            creationflags=creationflags,
            close_fds=True,
        )


def log_tail(log_file: str, limit: int = 2000) -> str:
    """The end of the daemon log — the only account of a failure the parent
    could not watch happen."""
    try:
        with open(log_file, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            data = handle.read()
    except OSError:
        return f"(could not read {log_file})"
    return data.decode("utf-8", "replace").strip() or f"({log_file} is empty)"


def await_spawned(
    proc: subprocess.Popen[bytes],
    port: int,
    log_file: str,
    timeout: float = DAEMON_READY_TIMEOUT_SEC,
) -> tuple[str, int]:
    """Wait for the re-spawned child to answer. Returns (message, exit code).

    Windows cannot report the child's bind() to the parent, so the parent
    observes the consequence instead. That is what keeps the POSIX promise that
    a busy port explains itself on the terminal rather than only in a log.

    Which is why the answer has to be matched against the child's own pid. A
    dashboard already on that port answers /api/health perfectly well, and
    treating that as proof told the user their daemon had started when it had
    in fact lost the bind, handing back a pid belonging to someone else's
    process. The pid is in the health payload for exactly this reason.
    """
    deadline = time.monotonic() + timeout
    foreign = False
    while time.monotonic() < deadline:
        kind, health = probe_port(port, timeout=0.5)
        if kind == "cargento" and health is not None:
            if health.get("pid") == proc.pid:
                return (
                    f"Cargento: http://127.0.0.1:{port}/ (pid {health['pid']}, log {log_file})",
                    0,
                )
            foreign = True  # someone else's dashboard; our child lost the bind
        if proc.poll() is not None:
            return (
                (
                    f"Cargento: the background server exited immediately "
                    f"(code {proc.returncode}). Its output was:\n{log_tail(log_file)}"
                ),
                1,
            )
        time.sleep(0.2)
    if foreign:
        return (
            (
                f"Cargento: port {port} is already served by a different Cargento, so "
                f"the one just started could not bind it. Look at that instance with "
                f"--status, or pick another port with --port."
            ),
            1,
        )
    return (
        (
            f"Cargento: started in the background, but nothing answered on port "
            f"{port} within {timeout:.0f}s — check {log_file}."
        ),
        1,
    )


class Handler(BaseHTTPRequestHandler):
    window_hours = 24

    # Loopback-origin requests only: the Host check defeats DNS rebinding,
    # the Origin check defeats cross-site fetch()es from web pages (both
    # reach 127.0.0.1-bound servers through the victim's browser).
    LOCAL_HOSTS: ClassVar[set[str]] = {"127.0.0.1", "localhost", "::1"}

    def _local_ok(self, *, allow_cross_site_navigation: bool = False) -> bool:
        if normalize_host(self.headers.get("Host") or "") not in self.LOCAL_HOSTS:
            return False
        if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site" and not (
            allow_cross_site_navigation and self._is_document_navigation()
        ):
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True  # same-origin GETs send none
        # Compare the whole origin, not just the host. Every port on this
        # machine is the *same site*, so Sec-Fetch-Site reports "same-site" for
        # a page served from another local port — and a hostname-only check
        # then trusted it. Any unrelated local dev server could POST here
        # (text/plain is CORS-safelisted, so no preflight would stop it).
        parsed = urlparse(origin)
        if parsed.scheme != "http" or (parsed.hostname or "") not in self.LOCAL_HOSTS:
            return False
        listening_port = getattr(self.server, "server_port", None)
        try:
            # Browsers omit the port when it is the scheme default, so
            # "http://localhost" is a legitimate same-origin value on port 80.
            origin_port = parsed.port if parsed.port is not None else 80
        except ValueError:
            return False  # unparseable port in the Origin header
        return origin_port == listening_port

    def _is_document_navigation(self) -> bool:
        """Whether this is the browser navigating a tab to us, top level.

        Chrome labels *any* navigation whose initiator was another origin
        ``Sec-Fetch-Site: cross-site`` — including one the user started by
        clicking a link to the dashboard. Rejecting those returned 403 for a
        perfectly ordinary way to open the page.

        Serving them is safe: the initiating page cannot read a cross-origin
        document, so there is nothing to exfiltrate, and the Host check above
        still blocks DNS rebinding. Everything else cross-site — ``fetch``,
        XHR, an iframe, a subresource — *can* be read by its initiator and
        stays blocked, which is what ``Sec-Fetch-Dest: document`` distinguishes
        (an iframe reports ``iframe``). GET only: a cross-site form submission
        is also a "navigation", so POST never takes this path.
        """
        return (self.headers.get("Sec-Fetch-Mode") or "").lower() == "navigate" and (
            self.headers.get("Sec-Fetch-Dest") or ""
        ).lower() == "document"

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _health(self) -> None:
        """Liveness and identity, with no filesystem access.

        `/api/data` can answer "is a dashboard here?" only by scanning every
        harness store on the machine. The daemon readiness wait and --status ask
        that question in a loop, so they need an answer that costs nothing. The
        pid is part of it because "something is listening on the port" is not
        the same claim as "Cargento is running on the port".
        """
        self._send(
            json.dumps(
                {
                    "ok": True,
                    "pid": os.getpid(),
                    "port": getattr(self.server, "server_port", 0),
                    "started": SERVER_STARTED,
                }
            ).encode(),
            "application/json",
        )

    def _shutdown(self) -> None:
        """Stop the server: the page's stop button and --stop both land here.

        Answer first, then stop. `socketserver.shutdown()` blocks until the
        accept loop notices the request and exits, which can take up to one
        poll interval (0.5s by default) — running it on its own thread lets
        this handler return and the connection close immediately, instead of
        holding the client for that long. It also keeps this correct if the
        server class ever stops being a threading one: on a non-threading
        server the handler runs on the serve loop's own thread, and calling
        `shutdown()` inline would then deadlock, exactly as `BaseServer.
        shutdown`'s docstring warns.
        """
        try:
            self._send(b'{"ok":true,"stopping":true}', "application/json")
            with contextlib.suppress(OSError, ValueError):
                self.wfile.flush()
        except (OSError, ValueError):
            # The request was accepted even if the peer vanished before it
            # could read the reply. Do not let that disconnect cancel the stop.
            pass
        finally:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def do_GET(self) -> None:
        if not self._local_ok(allow_cross_site_navigation=True):
            self.send_error(403)
            return
        url = urlparse(self.path)
        if url.path == "/api/data":
            show_all = parse_qs(url.query).get("all", ["0"])[0] == "1"
            self._send(collect_json(self.window_hours, show_all), "application/json")
        elif url.path == "/api/health":
            self._health()
        elif url.path == "/":
            self._send(PAGE.encode(), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        # Ingest Claude Code Notification-hook payloads:
        # {"session_id": "...", "message": "...", ...}
        if not self._local_ok():
            self.send_error(403)
            return
        path = urlparse(self.path).path
        if path == "/api/shutdown":
            self._shutdown()
            return
        if path != "/api/notify":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= 65536:
            self.send_error(413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        session_id = payload.get("session_id")
        prefix = session_id[:8] if isinstance(session_id, str) else ""
        hook_event_name = payload.get("hook_event_name")
        if isinstance(hook_event_name, str) and hook_event_name.lower() == "sessionend":
            if prefix:
                with _lock:
                    _hook_notifs.pop(prefix, None)
                    _last_state.pop(prefix, None)
                    bounded_put(_hook_generation, prefix, _hook_generation.get(prefix, 0) + 1)
            self._send(b'{"ok":true,"cleared":"session_end"}', "application/json")
            return
        raw_message = payload.get("message")
        message = notification_text(
            raw_message
            if isinstance(raw_message, str) and raw_message
            else "Claude is waiting for your input",
            500,
        )
        kind = normalized_notification_type(payload.get("notification_type"))
        needs_input, popup = notification_disposition(kind, message)
        # Sampled before the transcript lookups below, which are slow enough
        # for a SessionEnd to land in between and be silently undone.
        with _lock:
            generation = _hook_generation.get(prefix, 0)
        # Subagent sessions also emit Notification-hook events (permission
        # prompts inside agents). They are not user-facing sessions — a popup
        # about them is noise the human cannot act on from the dashboard.
        if prefix and claude_prefix_is_agent(prefix):
            self._send(b'{"ok":true,"suppressed":"subagent"}', "application/json")
            return
        now = time.time()
        hook = {"ts": now, "message": message}
        transcript_path = payload.get("transcript_path")
        if prefix and isinstance(transcript_path, str):
            found, user_event = claude_hook_user_event(transcript_path, prefix)
            if found:
                hook["user_event"] = user_event
        with _lock:
            if prefix and _hook_generation.get(prefix, 0) != generation:
                # The session ended while this notification was being processed.
                self._send(b'{"ok":true,"superseded":true}', "application/json")
                return
            if prefix:
                clears_input = kind in CLEARING_NOTIFICATION_TYPES or (not kind and not needs_input)
                if clears_input:
                    _hook_notifs.pop(prefix, None)
                    _last_state.pop(prefix, None)
                elif needs_input:
                    bounded_put(_hook_notifs, prefix, hook)
            popup_key = prefix or "_anonymous"
            session_ready = now - _last_popup.get(popup_key, 0) >= POPUP_COOLDOWN_SEC
            global_ready = now - _last_popup.get("_global", 0) >= GLOBAL_POPUP_COOLDOWN_SEC
            # Claude re-emits the same idle/permission notification for as
            # long as the session stays blocked; repeating the popup adds no
            # information. One popup per distinct message per session within
            # POPUP_REPEAT_SUPPRESS_SEC.
            prev_msg, prev_ts = _last_popup_message.get(popup_key, ("", 0.0))
            repeat = message == prev_msg and now - prev_ts < POPUP_REPEAT_SUPPRESS_SEC
            fire = popup and session_ready and global_ready and not repeat
            if fire:
                bounded_put(_last_popup, popup_key, now)
                bounded_put(_last_popup, "_global", now)
                bounded_put(_last_popup_message, popup_key, (message, now))
        if fire:
            notify_mac("Claude is waiting on you", message)
        self._send(b'{"ok":true}', "application/json")

    def log_message(self, *args: Any) -> None:
        pass  # keep stdout quiet


def store_primaries() -> dict[str, str]:
    """Current primary root per store, read from the module constants so a
    patched constant is reflected here too."""
    return {
        "claude.projects": PROJECTS_DIR,
        "claude.tasks": TASKS_DIR,
        "codex.sessions": CODEX_SESSIONS_DIR,
        "pi.sessions": PI_SESSIONS_DIR,
        "gemini.tmp": GEMINI_TMP,
        "antigravity.root": ANTIGRAVITY_CLI_DIR,
        "copilot.root": COPILOT_DIR,
        "opencode.data": OPENCODE_DATA,
        "cursor.chats": CURSOR_CHATS,
        "goose.db": GOOSE_DB,
        "droid.projects": FACTORY_PROJECTS,
    }


def candidate_report(path: str) -> dict[str, Any]:
    """What a single candidate store path actually is on disk."""
    entry: dict[str, Any] = {"path": path, "kind": "missing", "readable": False, "entries": None}
    # stat(), not isdir()/isfile(): those swallow OSError and return False, so
    # a candidate under an unreadable parent reported "missing" — the exact
    # confusion between "absent" and "inaccessible" this exists to remove.
    try:
        stat_result = os.stat(path)
    except FileNotFoundError:
        # stat() follows symlinks, so a dangling one lands here. Say so rather
        # than calling it absent — the target is what the user needs to fix.
        if os.path.islink(path):
            entry["kind"] = "broken symlink"
        return entry
    except OSError as exc:
        entry["kind"] = "inaccessible"
        entry["error"] = f"{type(exc).__name__}: {exc}"
        return entry
    if stat_module.S_ISDIR(stat_result.st_mode):
        entry["kind"] = "directory"
        try:
            with os.scandir(path) as scan:
                entry["entries"] = sum(1 for _ in scan)  # streamed, not materialised
            entry["readable"] = True
        except OSError as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
    elif stat_module.S_ISREG(stat_result.st_mode):
        entry["kind"] = "file"
        entry["readable"] = os.access(path, os.R_OK)
    else:
        # A FIFO or socket at a store path is never a usable store; reporting
        # it as a readable file would send someone looking in the wrong place.
        entry["kind"] = "special file"
    return entry


def diagnose(window_hours: float) -> dict[str, Any]:
    """Everything needed to explain a harness that is not showing up.

    Collectors swallow their errors so one broken store cannot take down the
    dashboard, which means a wrong path looks exactly like an idle machine.
    This is the counterweight: it names every location searched and what was
    found there. Local only — nothing is transmitted anywhere.
    """
    with _cache_lock:
        _store_errors.clear()  # this run's failures only
    data = collect(window_hours, show_all=True)
    with _cache_lock:
        store_errors = dict(_store_errors)
    sessions_by_harness: dict[str, int] = {}
    for session in data["sessions"]:
        key = str(session["harness"])
        sessions_by_harness[key] = sessions_by_harness.get(key, 0) + 1
    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "home": HOME,
        "sqlite": {
            "available": sqlite_available(),
            "error": SQLITE_IMPORT_ERROR,
            "version": sqlite3.sqlite_version if sqlite_available() else None,
        },
        "env": {name: os.environ[name] for name in STORE_ENV_VARS if os.environ.get(name)},
        # Failures the collectors swallowed. Without these a corrupt database
        # reads as a healthy store with no sessions.
        "store_errors": store_errors,
        "stores": {
            key: {
                "primary": primary,
                "candidates": [candidate_report(root) for root in store_roots(key, primary)],
            }
            for key, primary in store_primaries().items()
        },
        "harnesses": [
            {**harness, "sessions": sessions_by_harness.get(str(harness["key"]), 0)}
            for harness in data["harnesses"]
        ],
    }


def render_diagnosis(report: dict[str, Any]) -> str:
    """ASCII-only rendering — this output gets pasted into bug reports from
    consoles whose encoding we do not control."""
    sqlite_info = report["sqlite"]
    lines = [
        "Cargento diagnostics",
        f"  platform   {report['platform']} (python {report['python']})",
        f"  python at  {report['executable']}",
        f"  home       {report['home']}",
        f"  sqlite3    {sqlite_info['version'] or 'UNAVAILABLE: ' + str(sqlite_info['error'])}",
    ]
    env = report["env"]
    lines.append(
        "  overrides  " + (", ".join(f"{k}={v}" for k, v in env.items()) if env else "none")
    )

    lines.append("")
    lines.append("Harnesses")
    for harness in report["harnesses"]:
        mark = "ok  " if harness["discovered"] else "  --"
        detail = f"{harness['sessions']} session(s)" if harness["discovered"] else "not discovered"
        lines.append(f"  [{mark}] {harness['label']!s:<10} {detail}")
        if harness["error"]:
            lines.append(f"           error: {harness['error']}")

    if report["store_errors"]:
        lines.append("")
        lines.append("Stores that failed to open or query")
        for path, message in report["store_errors"].items():
            lines.append(f"  [  --] {path}")
            lines.append(f"           {message}")

    lines.append("")
    lines.append("Stores searched (in order)")
    for key, store in report["stores"].items():
        lines.append(f"  {key}")
        for candidate in store["candidates"]:
            mark = "ok  " if candidate["kind"] != "missing" else "  --"
            detail = candidate["kind"]
            if candidate["entries"] is not None:
                detail += f", {candidate['entries']} entries"
            if not candidate["readable"] and candidate["kind"] != "missing":
                detail += ", NOT READABLE"
            if candidate.get("error"):
                detail += f", {candidate['error']}"
            lines.append(f"    [{mark}] {candidate['path']}  ({detail})")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=tcp_port, default=4553)
    ap.add_argument(
        "--diagnose",
        action="store_true",
        help="report where each harness's data is searched for, and exit",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable --diagnose output")
    ap.add_argument(
        "--no-spacedock",
        action="store_true",
        help="do not read Spacedock workflow definitions (drops the stage strips)",
    )
    ap.add_argument(
        "--status",
        action="store_true",
        help="report whether a Cargento is running on --port, and exit",
    )
    ap.add_argument(
        "--stop",
        action="store_true",
        help="stop the Cargento running on --port, and exit",
    )
    ap.add_argument(
        "--daemon",
        action="store_true",
        help="detach and keep running after the session that started it exits",
    )
    ap.add_argument(
        "--window-hours",
        type=float,
        default=24,
        help="sessions with no activity in this window are hidden (default 24)",
    )
    args = ap.parse_args()
    global SERVER_STARTED  # noqa: PLW0603 — one process-wide start stamp
    SERVER_STARTED = time.time()
    if args.daemon and (args.diagnose or args.stop or args.status):
        # Each of those three exits without serving, so --daemon cannot apply.
        # Accepting it silently would teach that it had been honored.
        ap.error("--daemon cannot be combined with --diagnose, --stop or --status")
    if args.no_spacedock:
        global SPACEDOCK_ENABLED  # noqa: PLW0603 — one process-wide switch
        SPACEDOCK_ENABLED = False
    Handler.window_hours = args.window_hours
    if args.diagnose:
        report = diagnose(args.window_hours)
        diag(json.dumps(report, indent=2) if args.json else render_diagnosis(report))
        return
    if args.stop:
        message, code = stop_instance(args.port)
        diag(message)
        raise SystemExit(code)
    if args.status:
        status = instance_status(args.port)
        diag(render_status(status))
        raise SystemExit(0 if status["state"] == "running" else 1)
    if not sqlite_available():
        diag(
            f"Cargento: sqlite3 unavailable ({SQLITE_IMPORT_ERROR}) — OpenCode, "
            "Cursor and Goose sessions cannot be read; Antigravity still appears "
            "but without its token rate or turn ETA. Install the sqlite3 "
            "extension for this interpreter to enable them."
        )
    log_file = log_path(args.port)
    if args.daemon:
        # Explain a home that cannot be used, rather than tracebacking out of
        # the documented start command. write_state() already degrades this way
        # for a foreground run; detaching has nowhere to put its log without it.
        #
        # Open the log here too, for the same reason the socket is bound before
        # detaching: makedirs(exist_ok=True) succeeds for a directory that
        # already exists whatever its mode, so the likeliest bad home of all —
        # one that exists and is not writable — got past the guard and raised in
        # daemon_redirect_stdio (or spawn_detached) instead, after the point
        # where a message can still reach the terminal that asked. Failing there
        # produced a raw traceback and then told the user to check the very file
        # that could not be opened.
        try:
            ensure_cargento_home()
            with open(log_file, "ab"):
                pass
        except OSError as exc:
            diag(
                f"Cargento: cannot use {cargento_home()} for the daemon state and log "
                f"({type(exc).__name__}: {exc}). Point {CARGENTO_HOME_ENV} at a writable "
                f"directory, or drop --daemon to run in the foreground."
            )
            raise SystemExit(1) from exc
    if args.daemon and os.name == "nt":
        # No fork on Windows: re-spawn, then wait to be sure (D-2). Returns
        # before binding, so the parent never holds the port it handed over.
        message, code = await_spawned(spawn_detached(args, log_file), args.port, log_file)
        diag(message)
        raise SystemExit(code)
    # Bind to loopback only — this exposes local session data.
    #
    # Bind before detaching. bind_error_message() exists so a busy port gets an
    # explanation rather than a traceback, and SKILL.md tells the agent to look
    # for an already-running dashboard when it sees one. Forking first would
    # send that message to a log file nobody has been told about yet, and
    # report success.
    try:
        server = LoopbackHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        diag(bind_error_message(exc, args.port))
        raise SystemExit(1) from exc
    announce_fd: int | None = None
    if args.daemon and os.name != "nt":
        role, fd = fork_daemon()
        if role == "parent":
            # The daemon holds its own dup of the listening socket; closing
            # this one keeps a dead daemon from leaving the port looking bound.
            with contextlib.suppress(OSError):
                server.server_close()
            message, code = await_daemon(fd, args.port, log_file)
            diag(message)
            raise SystemExit(code)
        announce_fd = fd
        daemon_redirect_stdio(log_file)
    # 127.0.0.1, not localhost: on some systems "localhost" resolves to ::1
    # first, and this listener is IPv4-only, so the literal address is the one
    # that always connects.
    diag(f"Cargento: http://127.0.0.1:{args.port}/")
    write_state(args.port)
    if announce_fd is not None:
        # After write_state, so --status works the instant the parent returns.
        daemon_announce(announce_fd)
    try:
        server.serve_forever()
    finally:
        remove_state(args.port)
        with contextlib.suppress(OSError):
            server.server_close()


if __name__ == "__main__":
    main()
