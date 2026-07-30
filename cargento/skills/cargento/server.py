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
import os
import re
import select
import socket
import stat as stat_module
import subprocess
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import parse_qs, unquote, urlparse

from cargento_runtime import config as runtime_config
from cargento_runtime import io as runtime_io
from cargento_runtime import records
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime import state as runtime_state
from cargento_runtime import transcripts as runtime_transcripts
from cargento_runtime.web import page as frontend_page

sqlite3 = runtime_io.sqlite_module

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def _runtime_environ(home: str | None = None) -> dict[str, str]:
    """Capture ambient process inputs at the executable boundary."""
    environ = dict(os.environ)
    resolved_home = os.path.expanduser("~") if home is None else home
    environ["HOME"] = resolved_home
    if sys.platform == "win32":
        environ["USERPROFILE"] = resolved_home
    return environ


_LAUNCHER_PATH = Path(__file__).resolve()
_BASE_CONFIG = runtime_config.build_runtime_config(
    environ=_runtime_environ(),
    platform_name=sys.platform,
    os_name=os.name,
    launcher_path=_LAUNCHER_PATH,
)

# Transitional aliases preserve every test and collector seam until its owner
# moves. Configuration truth lives in cargento_runtime.config.
HOME = _BASE_CONFIG.home
DATA_HOME = _BASE_CONFIG.data_home
STORE_ENV_VARS = runtime_config.STORE_ENV_VARS
CARGENTO_HOME_ENV = runtime_config.CARGENTO_HOME_ENV
resolve_store_roots = runtime_config.resolve_store_roots
load_pi_settings = runtime_config.load_pi_settings
STORE_ROOTS: dict[str, list[str]] = {
    key: list(candidates) for key, candidates in _BASE_CONFIG.store_roots.items()
}

TASKS_DIR = runtime_config.primary_store(_BASE_CONFIG, "claude.tasks")
PROJECTS_DIR = runtime_config.primary_store(_BASE_CONFIG, "claude.projects")
CODEX_SESSIONS_DIR = runtime_config.primary_store(_BASE_CONFIG, "codex.sessions")
PI_SESSIONS_DIR = runtime_config.primary_store(_BASE_CONFIG, "pi.sessions")
GEMINI_TMP = runtime_config.primary_store(_BASE_CONFIG, "gemini.tmp")
ANTIGRAVITY_CLI_DIR = runtime_config.primary_store(_BASE_CONFIG, "antigravity.root")
ANTIGRAVITY_CONVERSATIONS_DIR = os.path.join(ANTIGRAVITY_CLI_DIR, "conversations")
ANTIGRAVITY_LOG_DIR = os.path.join(ANTIGRAVITY_CLI_DIR, "log")
ANTIGRAVITY_LAST_CONVERSATIONS = os.path.join(
    ANTIGRAVITY_CLI_DIR, "cache", "last_conversations.json"
)
COPILOT_DIR = runtime_config.primary_store(_BASE_CONFIG, "copilot.root")
OPENCODE_DATA = runtime_config.primary_store(_BASE_CONFIG, "opencode.data")
CURSOR_CHATS = runtime_config.primary_store(_BASE_CONFIG, "cursor.chats")
GOOSE_DB = runtime_config.primary_store(_BASE_CONFIG, "goose.db")
FACTORY_PROJECTS = runtime_config.primary_store(_BASE_CONFIG, "droid.projects")

RATE_WINDOW_SEC = _BASE_CONFIG.rate_window_sec
WORKING_THRESHOLD_SEC = _BASE_CONFIG.working_threshold_sec
TURN_GAP_RESET_SEC = _BASE_CONFIG.turn_gap_reset_sec
TAIL_BYTES = _BASE_CONFIG.tail_bytes
POPUP_COOLDOWN_SEC = _BASE_CONFIG.popup_cooldown_sec
GLOBAL_POPUP_COOLDOWN_SEC = _BASE_CONFIG.global_popup_cooldown_sec
POPUP_REPEAT_SUPPRESS_SEC = _BASE_CONFIG.popup_repeat_suppress_sec
LONG_TURN_WARN_SEC = _BASE_CONFIG.long_turn_warn_sec
FUTURE_SKEW_TOLERANCE_SEC = _BASE_CONFIG.future_skew_tolerance_sec
SQL_MSG_LIMIT = _BASE_CONFIG.sql_message_limit
MAX_CACHE_ENTRIES = _BASE_CONFIG.max_cache_entries
GEMINI_SEEN_ENTRIES = _BASE_CONFIG.gemini_seen_entries
REVERSE_CHUNK_BYTES = _BASE_CONFIG.reverse_chunk_bytes
DISPLAY_ID_LEN = _BASE_CONFIG.display_id_len
_CWD_SCAN_LINES = _BASE_CONFIG.claude_cwd_scan_lines
CLAUDE_CWD_LINE_BYTES = _BASE_CONFIG.claude_cwd_line_bytes
TURN_SCAN_MAX_BYTES = _BASE_CONFIG.turn_scan_max_bytes
_AGENT_SCAN_LINES = _BASE_CONFIG.claude_agent_scan_lines
_AGENT_CACHE_NEGATIVE_MIN_BYTES = _BASE_CONFIG.claude_agent_cache_negative_min_bytes
_AGENT_SCAN_BYTES = _BASE_CONFIG.claude_agent_scan_bytes
_CURSOR_META_ROWS = _BASE_CONFIG.cursor_meta_rows
ANTIGRAVITY_LOG_HEAD_BYTES = _BASE_CONFIG.antigravity_log_head_bytes
SD_BOOT_SCAN_BYTES = _BASE_CONFIG.spacedock_boot_scan_bytes
SD_README_BYTES = _BASE_CONFIG.spacedock_readme_bytes
SD_ENTITY_BYTES = _BASE_CONFIG.spacedock_entity_bytes
SD_MAX_FRONTMATTER_LINES = _BASE_CONFIG.spacedock_max_frontmatter_lines
SD_MAX_STAGES = _BASE_CONFIG.spacedock_max_stages
SD_MAX_WORKFLOWS = _BASE_CONFIG.spacedock_max_workflows
SD_MAX_ENTITIES = _BASE_CONFIG.spacedock_max_entities
SD_MAX_ENTITY_FILES = _BASE_CONFIG.spacedock_max_entity_files
SD_MAX_BOOT_RECORDS = _BASE_CONFIG.spacedock_max_boot_records
SD_MAX_BOOT_CANDIDATES = _BASE_CONFIG.spacedock_max_boot_candidates
COLLECT_MEMO_SEC = _BASE_CONFIG.collect_memo_sec
DAEMON_READY_TIMEOUT_SEC = _BASE_CONFIG.daemon_ready_timeout_sec
STOP_RELEASE_TIMEOUT_SEC = _BASE_CONFIG.stop_release_timeout_sec
STATE_READ_CAP_BYTES = _BASE_CONFIG.state_read_cap_bytes
SD_MIN_COLLAPSED_PATH = _BASE_CONFIG.prompt_path_collapse_min_length
FIRST_LINE_JSON_CAP_BYTES = _BASE_CONFIG.first_line_json_cap_bytes
NOTIFICATION_BODY_CAP_BYTES = _BASE_CONFIG.notification_body_cap_bytes
SPACEDOCK_ENABLED = _BASE_CONFIG.spacedock_enabled

_LEGACY_STATE = runtime_state.build_runtime_state(_BASE_CONFIG, started=0.0)
SERVER_STARTED = _LEGACY_STATE.server_started


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


def _legacy_runtime() -> tuple[runtime_config.RuntimeConfig, runtime_state.RuntimeState]:
    """Synchronize legacy aliases into the process-lifetime runtime state."""
    environ = _runtime_environ(HOME)
    current = _LEGACY_STATE.config
    normal = runtime_config.build_runtime_config(
        environ=environ,
        platform_name=sys.platform,
        os_name=os.name,
        launcher_path=_LAUNCHER_PATH,
        host=current.host,
        port=current.port,
        window_hours=current.window_hours,
        spacedock_enabled=current.spacedock_enabled,
    )
    aliases = {
        "claude.tasks": TASKS_DIR,
        "claude.projects": PROJECTS_DIR,
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
    overrides = {
        key: selected
        for key, selected in aliases.items()
        if selected != runtime_config.primary_store(normal, key)
    }
    config = runtime_config.build_runtime_config(
        environ=environ,
        platform_name=sys.platform,
        os_name=os.name,
        launcher_path=_LAUNCHER_PATH,
        store_root_overrides=overrides,
        host=current.host,
        port=current.port,
        window_hours=current.window_hours,
        spacedock_enabled=current.spacedock_enabled,
    )
    config = replace(
        config,
        store_roots=MappingProxyType(
            {key: tuple(store_roots(key, aliases[key])) for key in aliases}
        ),
        rate_window_sec=RATE_WINDOW_SEC,
        working_threshold_sec=WORKING_THRESHOLD_SEC,
        turn_gap_reset_sec=TURN_GAP_RESET_SEC,
        tail_bytes=TAIL_BYTES,
        popup_cooldown_sec=POPUP_COOLDOWN_SEC,
        global_popup_cooldown_sec=GLOBAL_POPUP_COOLDOWN_SEC,
        popup_repeat_suppress_sec=POPUP_REPEAT_SUPPRESS_SEC,
        long_turn_warn_sec=LONG_TURN_WARN_SEC,
        future_skew_tolerance_sec=FUTURE_SKEW_TOLERANCE_SEC,
        sql_message_limit=SQL_MSG_LIMIT,
        max_cache_entries=MAX_CACHE_ENTRIES,
        gemini_seen_entries=GEMINI_SEEN_ENTRIES,
        reverse_chunk_bytes=REVERSE_CHUNK_BYTES,
        display_id_len=DISPLAY_ID_LEN,
        claude_cwd_scan_lines=_CWD_SCAN_LINES,
        claude_cwd_line_bytes=CLAUDE_CWD_LINE_BYTES,
        turn_scan_max_bytes=TURN_SCAN_MAX_BYTES,
        claude_agent_scan_lines=_AGENT_SCAN_LINES,
        claude_agent_cache_negative_min_bytes=_AGENT_CACHE_NEGATIVE_MIN_BYTES,
        claude_agent_scan_bytes=_AGENT_SCAN_BYTES,
        cursor_meta_rows=_CURSOR_META_ROWS,
        antigravity_log_head_bytes=ANTIGRAVITY_LOG_HEAD_BYTES,
        spacedock_boot_scan_bytes=SD_BOOT_SCAN_BYTES,
        spacedock_readme_bytes=SD_README_BYTES,
        spacedock_entity_bytes=SD_ENTITY_BYTES,
        spacedock_max_frontmatter_lines=SD_MAX_FRONTMATTER_LINES,
        spacedock_max_stages=SD_MAX_STAGES,
        spacedock_max_workflows=SD_MAX_WORKFLOWS,
        spacedock_max_entities=SD_MAX_ENTITIES,
        spacedock_max_entity_files=SD_MAX_ENTITY_FILES,
        spacedock_max_boot_records=SD_MAX_BOOT_RECORDS,
        spacedock_max_boot_candidates=SD_MAX_BOOT_CANDIDATES,
        collect_memo_sec=COLLECT_MEMO_SEC,
        daemon_ready_timeout_sec=DAEMON_READY_TIMEOUT_SEC,
        stop_release_timeout_sec=STOP_RELEASE_TIMEOUT_SEC,
        state_read_cap_bytes=STATE_READ_CAP_BYTES,
        prompt_path_collapse_min_length=SD_MIN_COLLAPSED_PATH,
        first_line_json_cap_bytes=FIRST_LINE_JSON_CAP_BYTES,
        notification_body_cap_bytes=NOTIFICATION_BODY_CAP_BYTES,
    )
    _LEGACY_STATE.config = config
    return config, _LEGACY_STATE


def _install_legacy_state(state: runtime_state.RuntimeState) -> None:
    """Rebind transitional aliases when main creates the serving state."""
    global _LEGACY_STATE, _lock, _cache_lock, _scan_lock, _collect_memo_lock  # noqa: PLW0603
    global _hook_notifs, _last_popup, _last_popup_message, _last_state  # noqa: PLW0603
    global _hook_generation, _store_errors, _meta_cache, _claude_title_cache  # noqa: PLW0603
    global _claude_user_event_cache, _cwd_cache, _pi_scan, _turn_scan  # noqa: PLW0603
    global _agent_class_cache, _sd_role_cache, _sd_boot_cache  # noqa: PLW0603
    global _sd_workflow_cache, _sd_entity_cache, _cursor_meta_cache  # noqa: PLW0603
    global _collect_memo  # noqa: PLW0603

    _LEGACY_STATE = state
    _lock = state.hook_lock
    _cache_lock = state.cache_lock
    _scan_lock = state.scanner_lock
    _collect_memo_lock = state.collect_memo_lock
    _hook_notifs = state.hook_notifications
    _last_popup = state.last_popup
    _last_popup_message = state.last_popup_message
    _last_state = state.last_session_state
    _hook_generation = state.hook_generation
    _store_errors = state.store_errors
    _meta_cache = state.metadata_cache
    _claude_title_cache = state.claude_title_cache
    _claude_user_event_cache = state.claude_user_event_cache
    _cwd_cache = state.cwd_cache
    _pi_scan = state.pi_scan
    _turn_scan = state.turn_scan
    _agent_class_cache = state.agent_class_cache
    _sd_role_cache = state.spacedock_role_cache
    _sd_boot_cache = state.spacedock_boot_cache
    _sd_workflow_cache = state.spacedock_workflow_cache
    _sd_entity_cache = state.spacedock_entity_cache
    _cursor_meta_cache = state.cursor_metadata_cache
    _collect_memo = state.collect_memo


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

_lock = _LEGACY_STATE.hook_lock
# session prefix -> {"ts": epoch, "message": str, "user_event"?: str | None}
_hook_notifs = _LEGACY_STATE.hook_notifications
_last_popup = _LEGACY_STATE.last_popup
_last_popup_message = _LEGACY_STATE.last_popup_message
_last_state = _LEGACY_STATE.last_session_state
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
_hook_generation = _LEGACY_STATE.hook_generation
_cache_lock = _LEGACY_STATE.cache_lock


def bounded_put(cache: dict[Any, Any], key: Any, value: Any) -> None:
    """Set a bounded insertion-ordered cache entry.

    Callers must hold the lock that protects ``cache``.
    """
    runtime_state.bounded_put(cache, key, value, limit=MAX_CACHE_ENTRIES)


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

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler: type[BaseHTTPRequestHandler],
        *,
        page_bytes: bytes,
    ) -> None:
        self.page_bytes = page_bytes
        super().__init__(server_address, request_handler)

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
                runtime_io.diag(
                    f"Cargento: could not claim the port exclusively ({exc}); continuing",
                    print,
                )
        super().server_bind()


_store_errors = _LEGACY_STATE.store_errors


# The first-line metadata cache itself lives in RuntimeState, and its readers
# are cargento_runtime.transcripts. This alias stays until the last local
# collector moves, because the shared test reset still clears it.
_meta_cache = _LEGACY_STATE.metadata_cache


# ---------------------------------------------------------------------------
# Claude transcript analyzers (tail pass -> title, prompt, usage, activity)


_claude_title_cache = _LEGACY_STATE.claude_title_cache
_claude_user_event_cache = _LEGACY_STATE.claude_user_event_cache


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
    config, _ = _legacy_runtime()
    for raw in runtime_io.reverse_lines(config, path, contains=b'"aiTitle"'):
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
                    signal = records._turn_signal(record, "claude")  # noqa: SLF001
                    if not signal or signal[0] != "prompt":
                        continue
                    prompt = records.extract_text(
                        records.message_dict(record).get("content")
                    ).strip()
                    title = runtime_transcripts.prompt_title(config, prompt)
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
    config, _ = _legacy_runtime()
    for raw in runtime_io.reverse_lines(config, path, contains=b'"user"'):
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
    config, _ = _legacy_runtime()
    for line in runtime_io.read_tail(config, path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        ep = records.parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        if t == "last-prompt":
            info["last_prompt"] = d.get("lastPrompt")
        elif t == "assistant":
            msg = records.message_dict(d)
            usage = records.as_dict(msg.get("usage"))
            if ep and usage.get("output_tokens"):
                info["usage_events"].append((ep, usage["output_tokens"]))
            for c in records.as_list(msg.get("content")):
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    info["last_tool"] = c.get("name")
                    if c.get("name") in INPUT_TOOLS:
                        pending[c.get("id")] = {"name": c.get("name"), "ts": ep}
        elif t == "user":
            for c in records.as_list(records.message_dict(d).get("content")):
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    pending.pop(c.get("tool_use_id"), None)
    if pending:
        info["pending_input_tool"] = max(pending.values(), key=lambda p: p["ts"] or 0)
    return info


_cwd_cache = _LEGACY_STATE.cwd_cache


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
    config, _ = _legacy_runtime()
    try:
        lines = runtime_io.iter_bounded_text_lines(
            path,
            max_lines=config.claude_cwd_scan_lines,
            per_line_bytes=config.claude_cwd_line_bytes,
        )
        for line in lines:
            if '"cwd"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            value = d.get("cwd") if isinstance(d, dict) else None
            if isinstance(value, str) and value:
                cwd = value
                break
    except OSError:  # pragma: no cover - iterator handles filesystem failures
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


# Pi stores an append-only tree rather than a linear transcript.  The session
# selector follows the path from the newest entry back to parentId: null, so
# retaining sibling branches would report tools and tokens the agent abandoned.
_PI_NO_NAME = object()
_pi_scan = _LEGACY_STATE.pi_scan


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
    message = records.message_dict(record)
    role = message.get("role")
    prompt = None
    tool = None
    usage_source: Any = record.get("usage")
    if kind == "message":
        usage_source = message.get("usage")
        if role == "user":
            text = records.extract_text(message.get("content")).strip()
            prompt = text or None
        if role == "assistant":
            for block in records.as_list(message.get("content")):
                if not isinstance(block, dict) or block.get("type") != "toolCall":
                    continue
                tool_name = block.get("name")
                if isinstance(tool_name, str) and tool_name:
                    tool = tool_name
    output = records.as_dict(usage_source).get("output")
    usage = output if isinstance(output, (int, float)) and not isinstance(output, bool) else None
    name: Any = _PI_NO_NAME
    if kind == "session_info":
        value = record.get("name")
        name = value if isinstance(value, str) and value else None
    return {
        "id": entry_id,
        "parent_id": parent_id,
        "timestamp": records.parse_ts(record.get("timestamp") or "") or 0,
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
    config, _ = _legacy_runtime()
    for raw in runtime_io.reverse_lines(
        config,
        path,
        end_pos,
        contains=b'"session_info"',
    ):
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
    config, _ = _legacy_runtime()
    for raw in runtime_io.reverse_lines(config, path, end_pos):
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
    config, _ = _legacy_runtime()
    for raw in runtime_io.reverse_lines(config, path, end_pos):
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
    config, _ = _legacy_runtime()
    prompts = [entry["prompt"] for entry in path_entries if entry["prompt"]]
    name = state["name"]
    title = (
        name
        if isinstance(name, str) and name
        else (runtime_transcripts.prompt_title(config, prompts[0]) if prompts else None)
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


_turn_scan = _LEGACY_STATE.turn_scan
_scan_lock = _LEGACY_STATE.scanner_lock


def _apply_turn_record(st: dict[str, Any], record: Any, harness: str) -> None:
    """Apply one chronological transcript record to incremental turn state."""
    ep = records.parse_ts(record.get("timestamp") or "")
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
    sig = records._turn_signal(record, harness)  # noqa: SLF001
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
            start = records.norm_epoch(override) or ep
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
    config, _ = _legacy_runtime()
    for raw in runtime_io.reverse_lines(config, path, end_pos):
        if not raw.startswith(b"{"):
            continue
        try:
            decoded = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(decoded, dict):
            continue
        transcript_records = (
            reversed(records.gemini_records(decoded)) if harness == "gemini" else (decoded,)
        )
        for record in transcript_records:
            ep = records.parse_ts(record.get("timestamp") or "")
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
            sig = records._turn_signal(record, harness)  # noqa: SLF001
            if not sig:
                continue
            kind, override = sig
            if not active_decided:
                active_decided = True
                if kind != "end":
                    context["turn_start"] = records.norm_epoch(override) or ep
            if kind != "end":
                context["last_start"] = records.norm_epoch(override) or ep
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
            transcript_records = (
                records.incremental_gemini_records(d, st) if harness == "gemini" else (d,)
            )
            for record in transcript_records:
                if harness == "gemini":
                    fingerprint = records.record_fingerprint(record)
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
    config, _ = _legacy_runtime()
    elapsed = runtime_sessions.age(config, now, scan["turn_start"])
    if elapsed is None:
        return None  # turn start is implausibly ahead of the clock; no ETA
    history = scan.get("durations") or []
    cands = sorted(d for d in history if d >= elapsed)
    if cands:
        est_total = cands[len(cands) // 2]
        return {
            "elapsed_h": runtime_sessions.fmt_duration(elapsed),
            "eta_h": runtime_sessions.fmt_duration(est_total - elapsed),
            "pct": min(99, round(elapsed * 100 / est_total)) if est_total else 99,
            "long": max(est_total, elapsed) >= LONG_TURN_WARN_SEC,
        }
    return {
        "elapsed_h": runtime_sessions.fmt_duration(elapsed),
        "eta_h": None,  # running longer than any recent turn
        "pct": 99 if history else None,
        "long": elapsed >= LONG_TURN_WARN_SEC,
    }


# ---------------------------------------------------------------------------
# Claude task files + subagents


def load_tasks() -> dict[str, list[dict[str, Any]]]:
    """session prefix -> list of task dicts."""
    by_session: dict[str, list[dict[str, Any]]] = {}
    config, _ = _legacy_runtime()
    for fp in runtime_io.glob_stores(config, "claude.tasks", "*", "*.json"):
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
        for fp in runtime_io.glob_under(sess_dir, *pattern):
            try:
                found.append((fp, os.path.getmtime(fp)))
            except OSError:
                continue  # transcript rotated/deleted between glob and stat
    return found


def load_claude_subagents(transcript: str | None, now: float) -> list[dict[str, Any]]:
    """Running Claude subagents beneath the session directory; fresh mtime =
    running. Covers both layouts in ``CLAUDE_SUBAGENT_GLOBS``."""
    agents: list[dict[str, Any]] = []
    config, _ = _legacy_runtime()
    for fp, mtime in claude_agent_transcripts(transcript):
        if not runtime_sessions.is_fresh(config, now, mtime, WORKING_THRESHOLD_SEC):
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

    safe_message = records.safe_text(message, 180)
    safe_title = records.safe_text(title, 60)
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
            runtime_io.diag(f"[notify] osascript failed: {detail[:300]}", print)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        runtime_io.diag(f"[notify] osascript failed: {type(exc).__name__}: {exc}", print)


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


def codex_subagent_rate(path: str, now: float) -> int:
    """Recent Codex subagent output after its own task_started boundary."""
    scan = scan_turns(path, "codex")
    start = scan.get("last_start") if scan else None
    if not start:
        return 0
    config, _ = _legacy_runtime()
    info = runtime_transcripts.analyze_codex_transcript(config, path)
    recent: float = sum(
        tokens
        for epoch, tokens in info["usage_events"]
        if epoch >= start and runtime_sessions.is_fresh(config, now, epoch, RATE_WINDOW_SEC)
    )
    return round(recent / (RATE_WINDOW_SEC / 60))


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
# Entity files whose frontmatter is read per workflow, newest first. A mature
# queue holds far more than it is running: 31 files in the largest live state
# directory measured, nearly all parked on the initial stage.
# Decode attempts per tool result. A transcript full of `{"command"` lookalikes
# would otherwise cost one failed decode each while the collection lock is held.
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
_agent_class_cache = _LEGACY_STATE.agent_class_cache


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
    config, _ = _legacy_runtime()
    try:
        size = os.path.getsize(path)
        data = runtime_io.read_prefix_bytes(path, max_bytes=config.claude_agent_scan_bytes)
        lines = data.split(b"\n")
        if size > len(data) and data and not data.endswith(b"\n"):
            lines.pop()  # the byte prefix ended inside a JSON record
        for line in lines[: config.claude_agent_scan_lines]:
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
        or lines_seen >= config.claude_agent_scan_lines
        or size >= config.claude_agent_cache_negative_min_bytes
    ):
        with _cache_lock:
            bounded_put(_agent_class_cache, path, result)
    return result


_sd_role_cache = _LEGACY_STATE.spacedock_role_cache
_sd_boot_cache = _LEGACY_STATE.spacedock_boot_cache
_sd_workflow_cache = _LEGACY_STATE.spacedock_workflow_cache
_sd_entity_cache = _LEGACY_STATE.spacedock_entity_cache


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
    config, _ = _legacy_runtime()
    try:
        size = os.path.getsize(path)
        data = runtime_io.read_prefix_bytes(path, max_bytes=config.claude_agent_scan_bytes)
        lines = data.split(b"\n")
        if size > len(data) and data and not data.endswith(b"\n"):
            lines.pop()
        for line in lines[: config.claude_agent_scan_lines]:
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
    if setting or size >= config.claude_agent_cache_negative_min_bytes:
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
    config, _ = _legacy_runtime()
    for slug, path, info in sd_entity_files(entity_dir):
        if not runtime_sessions.is_fresh(config, now, info.st_mtime, window_sec):
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
    config, _ = _legacy_runtime()
    for fp in runtime_io.glob_stores(
        config,
        "claude.projects",
        "*",
        glob.escape(prefix) + "*.jsonl",
    ):
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
    config, _ = _legacy_runtime()
    for fp in runtime_io.glob_stores(config, "claude.projects", "*", "*.jsonl"):
        base = os.path.basename(fp)
        if "-agent-" in base or base.startswith("agent-"):
            continue  # legacy subagent transcripts aren't top-level sessions
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue  # transcript rotated/deleted between glob and stat
        if show_all or runtime_sessions.is_fresh(config, now, mtime, window_hours * 3600):
            is_agent, agent_name, parent_prefix = claude_agent_identity(fp)
            if is_agent:
                # Fold into the parent session; never a standalone session.
                # Without a parent prefix there is nothing to attach to.
                if parent_prefix and runtime_sessions.is_fresh(
                    config, now, mtime, window_hours * 3600
                ):
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
            if runtime_sessions.is_fresh(
                config, now, c["mtime"], WORKING_THRESHOLD_SEC
            )  # fresh = running
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
        last_activity = runtime_sessions.newest_plausible(config, now, activity_sources)
        active = runtime_sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue

        project = (
            (
                runtime_sessions.project_from_cwd(config, claude_session_cwd(transcript))
                # Lossy fallback: the encoded name cannot be split back into
                # segments, so it stays whole rather than guessing at a split.
                or runtime_sessions.project_label(
                    config, os.path.basename(os.path.dirname(transcript))
                )
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
            state_detail = f"open question ({p['name']}), waiting {runtime_sessions.fmt_duration(runtime_sessions.age(config, now, p['ts'])) if p['ts'] else '?'}"
        # Fresh activity beats a hook: Claude Code emits "waiting for your
        # input" notifications for sessions that keep running via background
        # tasks and will resume on their own. A hook only surfaces as
        # needs-input once the session actually goes quiet; permission-prompt
        # popups are unaffected (they fire on the POST itself).
        elif subagents or runtime_sessions.is_fresh(
            config,
            now,
            runtime_sessions.newest_plausible(config, now, last_event_sources),
            WORKING_THRESHOLD_SEC,
        ):
            state = "working"
            in_prog = next((t for t in tasks if t["status"] == "in_progress"), None)
            if in_prog:
                state_detail = (in_prog["activeForm"] or in_prog["subject"]) + "…"
            else:
                state_detail = runtime_sessions.working_detail(info, subagents)
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
                else runtime_sessions.age(config, now, t["created"])
            )
            t["elapsed_h"] = runtime_sessions.fmt_duration(elapsed)
            t["updated_ago"] = (
                runtime_sessions.fmt_duration(runtime_sessions.age(config, now, t["updated"]))
                + " ago"
            )

        s = runtime_sessions.base_session("claude", prefix, project)
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
                "rate_per_min": runtime_sessions.rate_from(info, now, config)
                + sum(
                    runtime_sessions.rate_from(analyze_transcript(path), now, config)
                    for path, mtime in agent_files
                    if runtime_sessions.is_fresh(config, now, mtime, RATE_WINDOW_SEC)
                )
                + sum(
                    runtime_sessions.rate_from(analyze_transcript(c["path"]), now, config)
                    for c in children
                    if runtime_sessions.is_fresh(config, now, c["mtime"], RATE_WINDOW_SEC)
                ),
                "total": total,
                "done": done,
                "open": open_count,
                "progress_pct": round(done * 100 / total) if total else 0,
                "eta_h": runtime_sessions.fmt_duration(eta_sec) if eta_sec else None,
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
    config, runtime_state_value = _legacy_runtime()
    for fp in runtime_io.glob_stores(
        config,
        "codex.sessions",
        "*",
        "*",
        "*",
        "rollout-*.jsonl",
    ):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        meta = runtime_transcripts.codex_meta(config, runtime_state_value, fp)
        sid = meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")][-36:]
        if meta.get("subagent"):
            parent_sid = meta.get("parent_session_id") or sid
            data = agent_data.setdefault(parent_sid, {"agents": [], "rate": 0})
            if runtime_sessions.is_fresh(config, now, mtime, RATE_WINDOW_SEC):
                data["rate"] += codex_subagent_rate(fp, now)
            if runtime_sessions.is_fresh(config, now, mtime, WORKING_THRESHOLD_SEC):
                data["agents"].append(((meta.get("agent_label") or "subagent")[:70], mtime))
            continue
        if sid not in sessions or mtime > sessions[sid][0]:
            sessions[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in sessions.items():
        data = agent_data.get(sid) or {"agents": [], "rate": 0}
        agents = sorted(data["agents"], key=lambda a: -a[1])
        activity_sources = (mtime, *(m for _, m in agents))
        last_activity = runtime_sessions.newest_plausible(config, now, activity_sources)
        active = runtime_sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        info = runtime_transcripts.analyze_codex_transcript(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, *activity_sources)
        subagents = [label for label, _ in agents]
        state, state_detail = "idle", "awaiting your message"
        if runtime_sessions.is_fresh(
            config,
            now,
            runtime_sessions.newest_plausible(config, now, last_event_sources),
            WORKING_THRESHOLD_SEC,
        ):
            state = "working"
            state_detail = runtime_sessions.working_detail(info, subagents)

        s = runtime_sessions.base_session(
            "codex",
            sid,
            runtime_sessions.project_from_cwd(
                config,
                runtime_transcripts.codex_meta(config, runtime_state_value, fp).get("cwd") or "",
            )
            or "codex",
        )
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": runtime_sessions.rate_from(info, now, config) + data["rate"],
                "turn": turn_progress(scan_turns(fp, "codex") if info else None, state, now),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out


def discover_pi() -> bool:
    """Whether Pi has at least one JSONL file with a valid session header."""
    config, runtime_state_value = _legacy_runtime()
    paths = set(runtime_io.glob_stores(config, "pi.sessions", "*.jsonl"))
    paths.update(runtime_io.glob_stores(config, "pi.sessions", "*", "*.jsonl"))
    for path in paths:
        try:
            if runtime_transcripts.pi_meta(config, runtime_state_value, path).get("session_id"):
                return True
        except (OSError, ValueError):
            continue
    return False


def collect_pi(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    """Collect Pi's independent JSONL sessions from flat and nested stores."""
    config, runtime_state_value = _legacy_runtime()
    paths = set(runtime_io.glob_stores(config, "pi.sessions", "*.jsonl"))
    paths.update(runtime_io.glob_stores(config, "pi.sessions", "*", "*.jsonl"))
    sessions: dict[str, tuple[float, str, dict[str, Any]]] = {}
    for path in paths:
        try:
            mtime = os.path.getmtime(path)
            meta = runtime_transcripts.pi_meta(config, runtime_state_value, path)
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
        last_activity = runtime_sessions.newest_plausible(config, now, (last_event_ts, mtime))
        active = runtime_sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        state, state_detail = "idle", "awaiting your message"
        if runtime_sessions.is_fresh(config, now, last_activity, WORKING_THRESHOLD_SEC):
            state = "working"
            state_detail = runtime_sessions.working_detail(info, [])
        project = runtime_sessions.project_from_cwd(config, meta.get("cwd") or "") or "pi"
        session = runtime_sessions.base_session("pi", sid, project)
        session.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": runtime_sessions.rate_from(info, now, config),
                "turn": turn_progress((info or {}).get("turn"), state, now),
            }
        )
        out.append(session)
    return out


def _antigravity_log_head_lines(
    config: runtime_config.RuntimeConfig,
    path: str,
) -> list[str]:
    try:
        return (
            runtime_io.read_prefix_bytes(
                path,
                max_bytes=config.antigravity_log_head_bytes,
            )
            .decode("utf-8", "replace")
            .splitlines()
        )
    except OSError:
        return []


def antigravity_log_head_lines(path: str) -> list[str]:
    """Read the bounded identity-bearing beginning of an Antigravity CLI log."""
    config, _ = _legacy_runtime()
    return _antigravity_log_head_lines(config, path)


def antigravity_log_lines(path: str) -> list[str]:
    """Read the beginning and bounded tail of an Antigravity CLI log.

    Workspace and conversation identity are written near the beginning,
    while the latest user prompt is near the tail. Long-running sessions can
    exceed ``TAIL_BYTES``, so reading only one side loses one of those.
    """
    config, _ = _legacy_runtime()
    return _antigravity_log_head_lines(config, path) + runtime_io.read_tail(config, path)


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
    config, _ = _legacy_runtime()
    try:
        with open(ANTIGRAVITY_LAST_CONVERSATIONS, encoding="utf-8") as source:
            recent = json.load(source)
        if isinstance(recent, dict):
            for workspace, sid in recent.items():
                if (
                    isinstance(workspace, str)
                    and isinstance(sid, str)
                    and runtime_sessions.project_from_cwd(config, workspace)
                ):
                    sessions.setdefault(sid, {})["cwd"] = workspace
                    cached_cwds[sid] = workspace
    except (OSError, ValueError, TypeError, RecursionError):
        pass

    all_logs = runtime_io.glob_under(ANTIGRAVITY_LOG_DIR, "cli-*.log")
    try:
        all_logs.sort(key=os.path.getmtime)
    except OSError:
        all_logs.sort()
    logs = all_logs
    if not show_all:
        recent_logs: list[str] = []
        for path in logs:
            try:
                if runtime_sessions.is_fresh(
                    config, now, os.path.getmtime(path), window_hours * 3600
                ):
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
                pending_prompt = records.safe_text(pending_prompt, 2000)
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
                if workspace is not None and workspace in missing_contexts and sid in cached_cwds:
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
    config, _ = _legacy_runtime()
    mtimes: list[float] = []
    with contextlib.suppress(OSError):
        mtimes.append(os.path.getmtime(path))
    if antigravity_wal_has_data(path):
        with contextlib.suppress(OSError):
            mtimes.append(os.path.getmtime(path + "-wal"))
    return runtime_sessions.newest_plausible(config, now, mtimes)


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
        return records.safe_text(value.decode("utf-8", "replace"), 140)

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
    if not runtime_io.sqlite_available():
        return result
    config, state = _legacy_runtime()
    query = "SELECT step_type, metadata FROM steps ORDER BY idx DESC LIMIT ?"
    rows = None
    read_error: BaseException | None = None
    for uri in (
        runtime_io.sqlite_ro_uri(path),
        runtime_io.sqlite_ro_uri(path, immutable=True),
    ):
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
            runtime_io.record_store_error(state, path, read_error)
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

    recent = sum(
        tokens
        for epoch, tokens in usage_events
        if runtime_sessions.is_fresh(config, now, epoch, RATE_WINDOW_SEC)
    )
    result["rate_per_min"] = round(recent / (RATE_WINDOW_SEC / 60))
    result["turns"] = turns_from_events(events) if events else None
    result["last_tool_action"] = latest_action[1]
    return result


def antigravity_session_info(path: str, sid: str) -> dict[str, Any]:
    """Extract parent conversation ID and subagent label from an Antigravity store."""
    info: dict[str, Any] = {"parent_id": None, "subagent_label": None}
    if not runtime_io.sqlite_available():
        return info
    _, state = _legacy_runtime()
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

    readable, row, read_error = read_row(runtime_io.sqlite_ro_uri(path))
    if not readable and antigravity_wal_has_data(path):
        if read_error:
            runtime_io.record_store_error(state, path, read_error)
        return info
    if not readable:
        readable, row, fallback_error = read_row(runtime_io.sqlite_ro_uri(path, immutable=True))
        if antigravity_wal_has_data(path):
            if read_error:
                runtime_io.record_store_error(state, path, read_error)
            return info
        if not readable:
            if fallback_error:
                runtime_io.record_store_error(state, path, fallback_error)
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
                for cleaned in (records.safe_text(label, 70).strip(),)
                if cleaned
            ),
            None,
        )
    return info


def collect_antigravity(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    config, _ = _legacy_runtime()
    metadata = antigravity_session_metadata(now, window_hours, show_all)
    dbs = runtime_io.glob_under(ANTIGRAVITY_CONVERSATIONS_DIR, "*.db")

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
        if show_all or runtime_sessions.is_fresh(config, now, mtime, window_hours * 3600)
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
        last_activity = runtime_sessions.newest_plausible(config, now, activity_sources)
        active = runtime_sessions.is_fresh(config, now, last_activity, window_hours * 3600)
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
                if runtime_sessions.is_fresh(config, now, agent_mtime, RATE_WINDOW_SEC)
            )
        subagents = [
            label
            for _, label, agent_mtime in agents
            if runtime_sessions.is_fresh(config, now, agent_mtime, WORKING_THRESHOLD_SEC)
        ]
        state, state_detail = "idle", "awaiting your message"
        if runtime_sessions.is_fresh(config, now, last_activity, WORKING_THRESHOLD_SEC):
            state = "working"
            state_detail = (
                runtime_sessions.working_detail(None, subagents)
                if subagents
                else activity["last_tool_action"] or runtime_sessions.working_detail(None, [])
            )

        meta = metadata.get(sid) or {}
        prompt = str(meta.get("last_prompt") or "").strip()
        cwd = str(meta.get("cwd") or "").strip()
        project = runtime_sessions.project_from_cwd(config, cwd) or "antigravity"
        session = runtime_sessions.base_session("gemini", sid, project)
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
    config, runtime_state_value = _legacy_runtime()
    for fp in runtime_io.glob_stores(
        config,
        "gemini.tmp",
        "*",
        "chats",
        "*",
        "*.jsonl",
    ):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        if not runtime_sessions.is_fresh(config, now, mtime, WORKING_THRESHOLD_SEC):
            continue
        parent = records.alnum(os.path.basename(os.path.dirname(fp)))
        label = "subagent " + os.path.basename(fp)[:8]
        agents_by_parent.setdefault(parent, []).append((label, mtime))

    sessions: dict[
        str, tuple[float, str]
    ] = {}  # session id (or filename fallback) -> (mtime, path)
    for fp in runtime_io.glob_stores(
        config,
        "gemini.tmp",
        "*",
        "chats",
        "session-*.jsonl",
    ):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        meta = runtime_transcripts.gemini_meta(config, runtime_state_value, fp)
        if meta.get("kind") == "subagent":
            continue
        sid = meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")]
        if sid not in sessions or mtime > sessions[sid][0]:
            sessions[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in sessions.items():
        agents = sorted(agents_by_parent.get(records.alnum(sid), []), key=lambda a: -a[1])
        activity_sources = (mtime, *(m for _, m in agents))
        last_activity = runtime_sessions.newest_plausible(config, now, activity_sources)
        active = runtime_sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        info = runtime_transcripts.analyze_gemini_transcript(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, *activity_sources)
        subagents = [label for label, _ in agents]
        state, state_detail = "idle", "awaiting your message"
        if runtime_sessions.is_fresh(
            config,
            now,
            runtime_sessions.newest_plausible(config, now, last_event_sources),
            WORKING_THRESHOLD_SEC,
        ):
            state = "working"
            state_detail = runtime_sessions.working_detail(info, subagents)

        cwd = runtime_transcripts.gemini_meta(config, runtime_state_value, fp).get("cwd")
        project = runtime_sessions.project_from_cwd(
            config, cwd or ""
        ) or runtime_sessions.project_label(
            config, os.path.basename(os.path.dirname(os.path.dirname(fp)))
        )
        s = runtime_sessions.base_session("gemini", sid, project)
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": runtime_sessions.rate_from(info, now, config),
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
    config, runtime_state_value = _legacy_runtime()
    for base in ("session-state", "history-session-state"):
        for fp in runtime_io.glob_stores(
            config,
            "copilot.root",
            base,
            "*",
            "events.jsonl",
        ):
            sid = os.path.basename(os.path.dirname(fp))
            try:
                mtime = os.path.getmtime(fp)
            except OSError:
                continue
            if sid not in files or mtime > files[sid][0]:
                files[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in files.items():
        active = runtime_sessions.is_fresh(config, now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        info = runtime_transcripts.analyze_copilot_events(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, mtime)
        state, state_detail = "idle", "awaiting your message"
        subagents: list[str] = []
        if runtime_sessions.is_fresh(
            config,
            now,
            runtime_sessions.newest_plausible(config, now, last_event_sources),
            WORKING_THRESHOLD_SEC,
        ):
            state = "working"
            subagents = list((info or {}).get("pending_agents", {}).values())
            state_detail = runtime_sessions.working_detail(info, subagents)

        cwd = (info or {}).get("cwd") or runtime_transcripts.copilot_meta(
            config, runtime_state_value, fp
        ).get("cwd")
        s = runtime_sessions.base_session(
            "copilot", sid, runtime_sessions.project_from_cwd(config, cwd or "") or "copilot"
        )
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


def collect_opencode(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    if not runtime_io.sqlite_available():
        return []
    config, runtime_state_value = _legacy_runtime()
    out: list[dict[str, Any]] = []
    for db in runtime_io.glob_stores(config, "opencode.data", "opencode*.db"):
        try:
            con = runtime_io.open_sqlite_read_only(db, runtime_state_value)
        except sqlite3.Error:
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
            runtime_io.record_store_error(runtime_state_value, db, exc)
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
                upd = records.norm_epoch(r["time_updated"])
                if r["parent_id"]:
                    if runtime_sessions.is_fresh(config, now, upd, WORKING_THRESHOLD_SEC):
                        children.setdefault(r["parent_id"], []).append(
                            ((r["title"] or "subagent")[:70], upd)
                        )
                else:
                    tops.append((r, upd))
            for r, upd in tops:
                agents = sorted(children.get(r["id"], []), key=lambda a: -a[1])
                activity_sources = (upd, *(m for _, m in agents))
                last_activity = runtime_sessions.newest_plausible(config, now, activity_sources)
                active = runtime_sessions.is_fresh(config, now, last_activity, window_hours * 3600)
                if not (active or show_all):
                    continue
                subagents = [label for label, _ in agents]
                state, state_detail = "idle", "awaiting your message"
                if runtime_sessions.is_fresh(config, now, last_activity, WORKING_THRESHOLD_SEC):
                    state = "working"
                    state_detail = runtime_sessions.working_detail(None, subagents)

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
                            events.append((records.norm_epoch(m["time_created"]), is_user))
                            if is_user:
                                try:
                                    jd = json.loads(m["data"] or "{}")
                                except (ValueError, TypeError):
                                    jd = {}
                                last_prompt = records.extract_text(jd)[:140] or last_prompt
                    except sqlite3.Error:
                        pass
                    turn = turn_progress(turns_from_events(events), state, now)

                s = runtime_sessions.base_session(
                    "opencode",
                    r["id"],
                    runtime_sessions.project_from_cwd(config, r["directory"] or "") or "opencode",
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
_cursor_meta_cache = _LEGACY_STATE.cursor_metadata_cache

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
    _, state = _legacy_runtime()
    try:
        con = runtime_io.open_sqlite_read_only(db, state)
    except sqlite3.Error:
        return None, ""
    failed = False
    try:
        rows = con.execute("SELECT value FROM meta LIMIT ?", (_CURSOR_META_ROWS,)).fetchall()
    except sqlite3.Error as exc:
        runtime_io.record_store_error(state, db, exc)
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
    if not runtime_io.sqlite_available():
        return []
    config, _ = _legacy_runtime()
    # One store.db per chat; content is opaque-ish (hex JSON blobs), so
    # Cursor rows are discovery + state + title only — no turn ETA.
    out: list[dict[str, Any]] = []
    for db in runtime_io.glob_stores(config, "cursor.chats", "*", "*", "store.db"):
        sid = os.path.basename(os.path.dirname(db))
        try:
            mtime = os.path.getmtime(db)
            wal = db + "-wal"
            if os.path.exists(wal):
                mtime = max(mtime, os.path.getmtime(wal))
        except OSError:
            continue
        active = runtime_sessions.is_fresh(config, now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        state, state_detail = "idle", "awaiting your message"
        if runtime_sessions.is_fresh(config, now, mtime, WORKING_THRESHOLD_SEC):
            state, state_detail = "working", "generating…"
        title, cwd = _cursor_meta(db, mtime)
        s = runtime_sessions.base_session(
            "cursor", sid, runtime_sessions.project_from_cwd(config, cwd) or "cursor"
        )
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
        isinstance(part, dict) and records.alnum(part.get("type")) == "toolresponse"
        for part in content
    )


def collect_goose(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    if not runtime_io.sqlite_available():
        return []
    # Goose keeps its store in a different place per platform, so scan every
    # candidate that exists rather than betting on one.
    config, _ = _legacy_runtime()
    out: list[dict[str, Any]] = []
    for db in runtime_io.existing_stores(config, "goose.db"):
        out.extend(collect_goose_db(db, now, window_hours, show_all))
    return out


def collect_goose_db(
    goose_db: str, now: float, window_hours: float, show_all: bool
) -> list[dict[str, Any]]:
    # Single shared sessions.db (v1.10.0+): per-session activity comes from
    # the updated_at column, NOT file mtime (the DB is shared by all
    # sessions). Legacy per-session .jsonl files are not supported.
    config, runtime_state_value = _legacy_runtime()
    try:
        con = runtime_io.open_sqlite_read_only(goose_db, runtime_state_value)
    except sqlite3.Error:
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
            upd = records.parse_utc_sql(r["updated_at"])
            stype = records.alnum(r["session_type"])
            if stype == "subagent":
                if r["parent_session_id"] and runtime_sessions.is_fresh(
                    config, now, upd, WORKING_THRESHOLD_SEC
                ):
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
            last_activity = runtime_sessions.newest_plausible(config, now, activity_sources)
            active = runtime_sessions.is_fresh(config, now, last_activity, window_hours * 3600)
            if not (active or show_all):
                continue
            subagents = [label for label, _ in agents]
            state, state_detail = "idle", "awaiting your message"
            if runtime_sessions.is_fresh(config, now, last_activity, WORKING_THRESHOLD_SEC):
                state = "working"
                state_detail = runtime_sessions.working_detail(None, subagents)

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
                        ep = records.norm_epoch(m["created_timestamp"])
                        try:
                            content = json.loads(m["content_json"] or "[]")
                        except (ValueError, TypeError, RecursionError):
                            content = []
                        is_prompt = m["role"] == "user" and goose_user_prompt(content)
                        events.append((ep, is_prompt))
                        if is_prompt:
                            last_prompt = records.extract_text(content)[:140] or last_prompt
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
                        if runtime_sessions.is_fresh(
                            config,
                            now,
                            records.norm_epoch(x["created_timestamp"]),
                            RATE_WINDOW_SEC,
                        )
                    )
                    rate = round(recent / (RATE_WINDOW_SEC / 60))
                except sqlite3.Error:
                    pass
                turn = turn_progress(turns_from_events(events), state, now)

            s = runtime_sessions.base_session(
                "goose",
                r["id"],
                runtime_sessions.project_from_cwd(config, r["working_dir"] or "") or "goose",
            )
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
        runtime_io.record_store_error(runtime_state_value, goose_db, exc)
        return []
    else:
        return out
    finally:
        con.close()


def collect_droid(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    config, runtime_state_value = _legacy_runtime()
    for fp in runtime_io.glob_stores(config, "droid.projects", "*", "*.jsonl"):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        active = runtime_sessions.is_fresh(config, now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        meta = runtime_transcripts.droid_meta(config, runtime_state_value, fp)
        sid = str(meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")])
        info = runtime_transcripts.analyze_droid_transcript(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, mtime)
        state, state_detail = "idle", "awaiting your message"
        if runtime_sessions.is_fresh(
            config,
            now,
            runtime_sessions.newest_plausible(config, now, last_event_sources),
            WORKING_THRESHOLD_SEC,
        ):
            state = "working"
            state_detail = runtime_sessions.working_detail(info, [])

        project = runtime_sessions.project_from_cwd(
            config, meta.get("cwd") or ""
        ) or runtime_sessions.project_label(config, os.path.basename(os.path.dirname(fp)))
        s = runtime_sessions.base_session("droid", sid, project)
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


def _store_dir_exists(key: str, *parts: str) -> bool:
    config, _ = _legacy_runtime()
    return runtime_io.any_store_dir(config, key, *parts)


def _store_glob_exists(key: str, *pattern: str) -> bool:
    config, _ = _legacy_runtime()
    return bool(runtime_io.glob_stores(config, key, *pattern))


def _store_file_exists(key: str) -> bool:
    config, _ = _legacy_runtime()
    return bool(runtime_io.existing_stores(config, key))


def _discover_gemini() -> bool:
    return _store_glob_exists("gemini.tmp", "*", "chats", "session-*.jsonl") or bool(
        runtime_io.glob_under(ANTIGRAVITY_CONVERSATIONS_DIR, "*.db")
    )


HARNESSES: list[
    tuple[str, str, Callable[[], bool], Callable[[float, float, bool], list[dict[str, Any]]]]
] = [
    ("claude", "Claude", lambda: _store_dir_exists("claude.projects"), collect_claude),
    ("codex", "Codex", lambda: _store_dir_exists("codex.sessions"), collect_codex),
    ("pi", "Pi", discover_pi, collect_pi),
    # Predicate matches both supported Gemini stores: legacy Gemini CLI
    # JSONL and current Antigravity CLI per-conversation SQLite databases.
    (
        "gemini",
        "Gemini",
        _discover_gemini,
        collect_gemini,
    ),
    (
        "copilot",
        "Copilot",
        lambda: (
            _store_dir_exists("copilot.root", "session-state")
            or _store_dir_exists("copilot.root", "history-session-state")
        ),
        collect_copilot,
    ),
    (
        "opencode",
        "OpenCode",
        lambda: (
            runtime_io.sqlite_available() and _store_glob_exists("opencode.data", "opencode*.db")
        ),
        collect_opencode,
    ),
    (
        "cursor",
        "Cursor",
        lambda: (
            runtime_io.sqlite_available()
            and _store_glob_exists("cursor.chats", "*", "*", "store.db")
        ),
        collect_cursor,
    ),
    (
        "goose",
        "Goose",
        lambda: runtime_io.sqlite_available() and _store_file_exists("goose.db"),
        collect_goose,
    ),
    (
        "droid",
        "Droid",
        lambda: _store_glob_exists("droid.projects", "*", "*.jsonl"),
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
            runtime_io.diag(f"[{key}] collector error: {harness['error']}", print)

    config, _ = _legacy_runtime()
    out_sessions = runtime_sessions.dedupe_sessions(out_sessions)
    runtime_sessions.assign_display_ids(config, out_sessions)
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


# (window_hours, show_all) -> {"ts": epoch, "body": bytes}
_collect_memo = _LEGACY_STATE.collect_memo
_collect_memo_lock = _LEGACY_STATE.collect_memo_lock


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
    if override and override.strip():
        return override
    config, _ = _legacy_runtime()
    return str(config.state_dir)


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
        runtime_io.diag(
            f"Cargento: could not write {target} ({exc}); --status will not see this instance",
            print,
        )
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
    server: LoopbackHTTPServer
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
            self._send(self.server.page_bytes, "text/html; charset=utf-8")
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
        if not 0 <= length <= NOTIFICATION_BODY_CAP_BYTES:
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
        message = records.safe_text(
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
            "available": runtime_io.sqlite_available(),
            "error": runtime_io.SQLITE_IMPORT_ERROR,
            "version": sqlite3.sqlite_version if runtime_io.sqlite_available() else None,
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
    started = time.time()
    global SERVER_STARTED  # noqa: PLW0603 — one process-wide start stamp
    config, _ = _legacy_runtime()
    config = replace(
        config,
        port=args.port,
        window_hours=args.window_hours,
        spacedock_enabled=not args.no_spacedock,
    )
    _install_legacy_state(runtime_state.build_runtime_state(config, started=started))
    SERVER_STARTED = started
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
        runtime_io.diag(
            json.dumps(report, indent=2) if args.json else render_diagnosis(report),
            print,
        )
        return
    if args.stop:
        message, code = stop_instance(args.port)
        runtime_io.diag(message, print)
        raise SystemExit(code)
    if args.status:
        status = instance_status(args.port)
        runtime_io.diag(render_status(status), print)
        raise SystemExit(0 if status["state"] == "running" else 1)
    try:
        page_bytes = frontend_page.load_page()
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(
            f"Cargento: cannot load frontend assets ({type(exc).__name__}: {exc}).",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    if not runtime_io.sqlite_available():
        runtime_io.diag(
            f"Cargento: sqlite3 unavailable ({runtime_io.SQLITE_IMPORT_ERROR}) — OpenCode, "
            "Cursor and Goose sessions cannot be read; Antigravity still appears "
            "but without its token rate or turn ETA. Install the sqlite3 "
            "extension for this interpreter to enable them.",
            print,
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
            runtime_io.diag(
                f"Cargento: cannot use {cargento_home()} for the daemon state and log "
                f"({type(exc).__name__}: {exc}). Point {CARGENTO_HOME_ENV} at a writable "
                f"directory, or drop --daemon to run in the foreground.",
                print,
            )
            raise SystemExit(1) from exc
    if args.daemon and os.name == "nt":
        # No fork on Windows: re-spawn, then wait to be sure (D-2). Returns
        # before binding, so the parent never holds the port it handed over.
        message, code = await_spawned(spawn_detached(args, log_file), args.port, log_file)
        runtime_io.diag(message, print)
        raise SystemExit(code)
    # Bind to loopback only — this exposes local session data.
    #
    # Bind before detaching. bind_error_message() exists so a busy port gets an
    # explanation rather than a traceback, and SKILL.md tells the agent to look
    # for an already-running dashboard when it sees one. Forking first would
    # send that message to a log file nobody has been told about yet, and
    # report success.
    try:
        server = LoopbackHTTPServer(
            ("127.0.0.1", args.port),
            Handler,
            page_bytes=page_bytes,
        )
    except OSError as exc:
        runtime_io.diag(bind_error_message(exc, args.port), print)
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
            runtime_io.diag(message, print)
            raise SystemExit(code)
        announce_fd = fd
        daemon_redirect_stdio(log_file)
    # 127.0.0.1, not localhost: on some systems "localhost" resolves to ::1
    # first, and this listener is IPv4-only, so the literal address is the one
    # that always connects.
    runtime_io.diag(f"Cargento: http://127.0.0.1:{args.port}/", print)
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
