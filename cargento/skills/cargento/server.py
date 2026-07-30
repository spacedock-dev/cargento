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
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from cargento_runtime import aggregate, diagnostics, http_api, lifecycle, notifications
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
def diagnose(window_hours: float) -> dict[str, Any]:
    """Diagnose the transitional application, for the CLI's --diagnose path."""
    return diagnostics.diagnose(_legacy_application(window_hours))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=lifecycle.tcp_port, default=4553)
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
        message, code = lifecycle.stop_instance(config, args.port)
        runtime_io.diag(message, print)
        raise SystemExit(code)
    if args.status:
        status = lifecycle.instance_status(config, args.port)
        runtime_io.diag(lifecycle.render_status(status), print)
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
    log_file = lifecycle.log_path(config, args.port)
    if args.daemon:
        lifecycle.prepare_daemon_home(config, log_file)
    if args.daemon and config.os_name == "nt":
        # No fork on Windows: re-spawn, then wait to be sure (D-2). This branch
        # returns before any bind, so the parent never holds the port it handed
        # over, and never constructs a server at all — the spawned foreground
        # child owns the bind and therefore owns reporting a bind failure.
        message, code = lifecycle.await_spawned(
            config,
            lifecycle.spawn_detached(config, args, log_file),
            args.port,
            log_file,
        )
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
    if args.daemon and config.os_name != "nt":
        role, fd = lifecycle.fork_daemon()
        if role == "parent":
            # The daemon holds its own dup of the listening socket; closing
            # this one keeps a dead daemon from leaving the port looking bound.
            with contextlib.suppress(OSError):
                server.server_close()
            message, code = lifecycle.await_daemon(config, fd, args.port, log_file)
            runtime_io.diag(message, print)
            raise SystemExit(code)
        announce_fd = fd
        lifecycle.daemon_redirect_stdio(log_file)
    lifecycle.serve(config, server, args.port, started=started, announce_fd=announce_fd)


if __name__ == "__main__":
    main()
