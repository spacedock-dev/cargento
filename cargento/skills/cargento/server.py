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
import http.client
import json
import math
import os
import select
import socket
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from cargento_runtime import aggregate, diagnostics, http_api, notifications
from cargento_runtime import config as runtime_config
from cargento_runtime import io as runtime_io
from cargento_runtime import state as runtime_state
from cargento_runtime.web import page as frontend_page

sqlite3 = runtime_io.sqlite_module

if TYPE_CHECKING:
    from collections.abc import Callable


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
    global _agent_class_cache  # noqa: PLW0603
    global _cursor_meta_cache  # noqa: PLW0603
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
    _cursor_meta_cache = state.cursor_metadata_cache
    _collect_memo = state.collect_memo


# Tools that mean Claude is blocked on the human, not just running long.
# Claude Code's documented Notification matcher values. ``idle_timeout`` is
# accepted as a compatibility alias, while current payloads use
# ``idle_prompt``. Unknown structured values remain actionable so a newly
# introduced prompt type does not silently disappear.

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


_store_errors = _LEGACY_STATE.store_errors


# The first-line metadata cache itself lives in RuntimeState, and its readers
# are cargento_runtime.transcripts. This alias stays until the last local
# collector moves, because the shared test reset still clears it.
_meta_cache = _LEGACY_STATE.metadata_cache


# ---------------------------------------------------------------------------
# Claude transcript analyzers (tail pass -> title, prompt, usage, activity)


_claude_title_cache = _LEGACY_STATE.claude_title_cache
_claude_user_event_cache = _LEGACY_STATE.claude_user_event_cache


_cwd_cache = _LEGACY_STATE.cwd_cache


# Pi's branch scanner and the generic turn scanner both live in the runtime now
# (collectors.pi and turns), and their state and lock live in RuntimeState.
# These aliases stay until the last local collector moves, because the shared
# test reset still clears them.
_pi_scan = _LEGACY_STATE.pi_scan
_turn_scan = _LEGACY_STATE.turn_scan
_scan_lock = _LEGACY_STATE.scanner_lock


# ---------------------------------------------------------------------------
# Notifications


# ---------------------------------------------------------------------------
# Session assembly helpers


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
# Cycle/retry markers a first officer appends to a worker name. Observed live in
# every position: before the stage and after it.


# The workflow README and the entity-state frontmatter are the only project
# reads Cargento performs. The switch exists so an operator who wants the
# store-only read surface can have it back; see SECURITY.md.


# Subagent-transcript classification cache. Whether a top-level transcript
# belongs to a subagent and its eventual label are immutable for a given file,
# but young files may not have written both identifying records yet — so
# incomplete results are cached only once the file is big enough to be conclusive.
_agent_class_cache = _LEGACY_STATE.agent_class_cache


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


# ---------------------------------------------------------------------------
# Harness registry — a harness appears in the dashboard only if discovered


def _bound_popup_notifier(
    config: runtime_config.RuntimeConfig,
) -> Callable[[str, str], None]:
    """The application's popup notifier: config and sink bound, two arguments left."""

    def notify(title: str, message: str) -> None:
        notifications.notify_mac(config, title, message, diagnostic_sink=print)

    return notify


# The registry as the runtime sees it. Every row is a collector module under
# `cargento_runtime.collectors`; nothing here reads a module global. Read this
# one for keys and labels: its Claude row notifies through a notifier bound to
# the import-time config, so anything that CALLS a spec should build a live
# registry the way the application below does.
HARNESSES: tuple[aggregate.HarnessSpec, ...] = aggregate.default_harnesses(
    _bound_popup_notifier(_LEGACY_STATE.config)
)


def _legacy_application(window_hours: float) -> aggregate.Application:
    """The one transitional application, built over the legacy globals."""
    config, state = _legacy_runtime()
    if window_hours != config.window_hours:
        # The window is a request-time argument until the CLI owns it outright.
        # Kept local on purpose: publishing it onto the process-lifetime state
        # would race between concurrent requests, and nothing reads it there.
        config = replace(config, window_hours=window_hours)
    popup_notifier = _bound_popup_notifier(config)
    return aggregate.Application(
        config,
        state,
        aggregate.default_harnesses(popup_notifier),
        native_notifier=notifications.native_notifier,
        # The same callable the Claude collector notifies through, so the
        # transcript path and the hook path cannot diverge.
        popup_notifier=popup_notifier,
        diagnostic_sink=print,
        # Passed explicitly rather than left to the default: the default binds
        # time.time once at import, and the tests still patch the time module.
        clock=time.time,
    )


# (window_hours, show_all) -> {"ts": epoch, "body": bytes}. Both live in
# RuntimeState now; the aliases stay until the last local collector moves,
# because the shared test reset still clears them.
_collect_memo = _LEGACY_STATE.collect_memo
_collect_memo_lock = _LEGACY_STATE.collect_memo_lock


def collect(window_hours: float, show_all: bool) -> dict[str, Any]:
    return _legacy_application(window_hours).collect(show_all=show_all)


def collect_json(window_hours: float, show_all: bool) -> bytes:
    return _legacy_application(window_hours).collect_json(show_all=show_all)


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
            if http_api.reuse_address_allowed(os.name):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Windows-only, and the same option CargentoHTTPServer.server_bind
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


def diagnose(window_hours: float) -> dict[str, Any]:
    """Diagnose the transitional application, for the CLI's --diagnose path."""
    return diagnostics.diagnose(_legacy_application(window_hours))


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
    # The window is no longer a handler class attribute: it is in the config
    # the application carries, which is what /api/data collects through.
    if args.diagnose:
        report = diagnose(args.window_hours)
        runtime_io.diag(
            json.dumps(report, indent=2) if args.json else diagnostics.render_diagnosis(report),
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
        server = http_api.CargentoHTTPServer(
            ("127.0.0.1", args.port),
            _legacy_application(args.window_hours),
            page_bytes,
        )
    except OSError as exc:
        runtime_io.diag(http_api.bind_error_message(exc, args.port), print)
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
