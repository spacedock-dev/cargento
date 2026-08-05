"""Explicit immutable configuration for the Cargento runtime."""

from __future__ import annotations

import json
import ntpath
import os
import posixpath
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

STORE_ENV_VARS = (
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "GEMINI_CLI_HOME",
    "COPILOT_HOME",
    "PI_CODING_AGENT_DIR",
    "PI_CODING_AGENT_SESSION_DIR",
)
CARGENTO_HOME_ENV = "CARGENTO_HOME"
_PATH_TYPE = type(Path())


@dataclass(frozen=True)
class RuntimeConfig:
    home: str
    data_home: str
    store_roots: Mapping[str, tuple[str, ...]]
    platform_name: str
    os_name: str
    state_dir: Path
    # The same location as ``state_dir``, kept verbatim as the user wrote it.
    # A native Path rewrites separators on Windows, so an override of
    # "C:/plugin/state" would come back as "C:\\plugin\\state" — a different
    # string in --status output and in the dirname contract lifecycle relies on.
    state_home: str
    launcher_path: Path
    host: str
    port: int
    window_hours: float
    spacedock_enabled: bool
    usage_fetch_enabled: bool
    rate_window_sec: float
    working_threshold_sec: float
    turn_gap_reset_sec: float
    tail_bytes: int
    popup_cooldown_sec: float
    global_popup_cooldown_sec: float
    popup_repeat_suppress_sec: float
    long_turn_warn_sec: float
    future_skew_tolerance_sec: float
    sql_message_limit: int
    max_cache_entries: int
    gemini_seen_entries: int
    reverse_chunk_bytes: int
    display_id_len: int
    claude_cwd_scan_lines: int
    claude_cwd_line_bytes: int
    turn_scan_max_bytes: int
    claude_agent_scan_lines: int
    claude_agent_cache_negative_min_bytes: int
    claude_agent_scan_bytes: int
    cursor_meta_rows: int
    antigravity_log_head_bytes: int
    spacedock_boot_scan_bytes: int
    spacedock_readme_bytes: int
    spacedock_entity_bytes: int
    spacedock_max_frontmatter_lines: int
    spacedock_max_stages: int
    spacedock_max_workflows: int
    spacedock_max_entities: int
    spacedock_max_entity_files: int
    spacedock_max_boot_records: int
    spacedock_max_boot_candidates: int
    collect_memo_sec: float
    # The SSE stream. The client cap is above the browsers' six-per-origin
    # limit, so the server is not the thing that refuses first: it bounds
    # handler threads, it does not police tabs.
    stream_max_clients: int
    stream_heartbeat_sec: float
    stream_write_timeout_sec: float
    stream_producer_interval_sec: float
    daemon_ready_timeout_sec: float
    stop_release_timeout_sec: float
    state_read_cap_bytes: int
    prompt_path_collapse_min_length: int
    first_line_json_cap_bytes: int
    notification_body_cap_bytes: int
    # The quota fetch (SECURITY.md, "Usage quota reads"): the contract's
    # five-minute floor between requests to one vendor, the request timeout,
    # and the read caps on the credential file and the response body.
    usage_poll_floor_sec: float
    usage_fetch_timeout_sec: float
    usage_credentials_cap_bytes: int
    usage_response_cap_bytes: int
    # A pushed status-line receipt. Larger than the notification cap because
    # the payload carries a whole session-state block, not just a message.
    usage_receipt_cap_bytes: int
    # Event overlays. The Working deadline is tied to `working_threshold_sec`
    # rather than chosen separately: that value is already what the collectors
    # mean by Working, so an overlay that outlived it would be claiming Working
    # for a session the scan would call Idle, which is the disagreement the
    # overlay exists to avoid. The dwell is a chosen constant, set well above the
    # 50 to 150 millisecond coalescing window so a stop followed immediately by a
    # new prompt resolves inside one publish instead of flapping the row.
    overlay_working_ttl_sec: float
    overlay_idle_dwell_sec: float
    # The coordinator. The coalescing window is fixed rather than sliding: a
    # sliding window never closes under a sustained burst, and the board would
    # stop updating entirely. The ledger and pending caps are refusal thresholds,
    # not eviction thresholds, because evicting to make room would drop whichever
    # permission alert happened to be oldest. `reconcile_interval_sec` is the
    # longest a probe-negative tick may keep skipping, which is what bounds the
    # probe's documented false negative.
    event_coalesce_sec: float
    event_overlay_max_sessions: int
    event_pending_max: int
    event_pending_ttl_sec: float
    reconcile_interval_sec: float


def resolve_store_roots(
    *,
    platform_name: str,
    environ: Mapping[str, str],
    home: str,
    pi_settings: Mapping[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Return candidate locations for every harness store, best first."""
    windows = platform_name == "win32"
    join = ntpath.join if windows else posixpath.join
    is_absolute = ntpath.isabs if windows else posixpath.isabs

    def under_home(*parts: str) -> str:
        return join(home, *parts)

    def env_dir(name: str) -> str | None:
        value = environ.get(name)
        if not isinstance(value, str) or not value.strip():
            return None
        return value

    xdg_data = env_dir("XDG_DATA_HOME") or under_home(".local", "share")
    local_app_data = env_dir("LOCALAPPDATA") if windows else None
    roaming_app_data = env_dir("APPDATA") if windows else None
    claude_home = env_dir("CLAUDE_CONFIG_DIR") or under_home(".claude")
    codex_home = env_dir("CODEX_HOME") or under_home(".codex")
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
        "opencode.data": ordered(
            join(xdg_data, "opencode"),
            app_data(local_app_data, "opencode", "data"),
            app_data(local_app_data, "opencode"),
            under_home(".local", "share", "opencode") if windows else None,
        ),
        "cursor.chats": ordered(under_home(".cursor", "chats")),
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


def build_runtime_config(
    *,
    environ: Mapping[str, str],
    platform_name: str,
    os_name: str,
    launcher_path: Path,
    store_root_overrides: Mapping[str, str] | None = None,
    host: str = "127.0.0.1",
    port: int = 4553,
    window_hours: float = 24.0,
    spacedock_enabled: bool = True,
    usage_fetch_enabled: bool = True,
) -> RuntimeConfig:
    """Construct runtime configuration solely from explicit inputs."""
    windows = platform_name == "win32"
    join = ntpath.join if windows else posixpath.join
    home_key = "USERPROFILE" if windows else "HOME"
    home = environ.get(home_key) or environ.get("HOME") or ""
    data_home = environ.get("XDG_DATA_HOME") or join(home, ".local", "share")
    pi_config_dir = environ.get("PI_CODING_AGENT_DIR")
    if not isinstance(pi_config_dir, str) or not pi_config_dir.strip():
        pi_config_dir = join(home, ".pi", "agent")
    roots = resolve_store_roots(
        platform_name=platform_name,
        environ=environ,
        home=home,
        pi_settings=load_pi_settings(pi_config_dir),
    )
    resolved = {key: tuple(candidates) for key, candidates in roots.items()}
    for key, selected in (store_root_overrides or {}).items():
        resolved[key] = (selected,)
    state_override = environ.get(CARGENTO_HOME_ENV)
    state_home = (
        state_override if state_override and state_override.strip() else join(home, ".cargento")
    )
    state_dir = _PATH_TYPE(state_home)
    return RuntimeConfig(
        home=home,
        data_home=data_home,
        store_roots=MappingProxyType(resolved),
        platform_name=platform_name,
        os_name=os_name,
        state_dir=state_dir,
        state_home=state_home,
        launcher_path=launcher_path,
        host=host,
        port=port,
        window_hours=window_hours,
        spacedock_enabled=spacedock_enabled,
        usage_fetch_enabled=usage_fetch_enabled,
        rate_window_sec=600,
        working_threshold_sec=90,
        turn_gap_reset_sec=300,
        tail_bytes=400_000,
        popup_cooldown_sec=60,
        global_popup_cooldown_sec=15,
        popup_repeat_suppress_sec=600,
        long_turn_warn_sec=900,
        future_skew_tolerance_sec=120,
        sql_message_limit=400,
        max_cache_entries=8192,
        gemini_seen_entries=2048,
        reverse_chunk_bytes=262_144,
        display_id_len=8,
        claude_cwd_scan_lines=50,
        claude_cwd_line_bytes=200_000,
        turn_scan_max_bytes=8 * 1024 * 1024,
        claude_agent_scan_lines=50,
        claude_agent_cache_negative_min_bytes=16_384,
        claude_agent_scan_bytes=16_384,
        cursor_meta_rows=50,
        antigravity_log_head_bytes=80_000,
        spacedock_boot_scan_bytes=512_000,
        spacedock_readme_bytes=65_536,
        spacedock_entity_bytes=8_192,
        spacedock_max_frontmatter_lines=400,
        spacedock_max_stages=32,
        spacedock_max_workflows=8,
        spacedock_max_entities=12,
        spacedock_max_entity_files=96,
        spacedock_max_boot_records=16,
        spacedock_max_boot_candidates=64,
        collect_memo_sec=2.5,
        stream_max_clients=8,
        stream_heartbeat_sec=15.0,
        stream_write_timeout_sec=10.0,
        stream_producer_interval_sec=5.0,
        daemon_ready_timeout_sec=10.0,
        stop_release_timeout_sec=5.0,
        state_read_cap_bytes=65_536,
        prompt_path_collapse_min_length=25,
        first_line_json_cap_bytes=200_000,
        notification_body_cap_bytes=65_536,
        usage_poll_floor_sec=300,
        usage_fetch_timeout_sec=10,
        usage_credentials_cap_bytes=65_536,
        usage_response_cap_bytes=262_144,
        usage_receipt_cap_bytes=131_072,
        overlay_working_ttl_sec=90,
        overlay_idle_dwell_sec=3.0,
        event_coalesce_sec=0.1,
        event_overlay_max_sessions=512,
        event_pending_max=256,
        event_pending_ttl_sec=60.0,
        reconcile_interval_sec=30.0,
    )


def store_roots(config: RuntimeConfig, key: str) -> tuple[str, ...]:
    return config.store_roots.get(key, ())


def primary_store(config: RuntimeConfig, key: str) -> str:
    return store_roots(config, key)[0]
