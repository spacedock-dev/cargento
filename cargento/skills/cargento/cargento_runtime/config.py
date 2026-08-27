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
    # Whether the dismissal store is read and written at all. `--no-dismiss` is
    # the rollback switch, and off means off in both directions: the file is
    # neither consulted during a collection nor created by a request, so a run
    # that misbehaves leaves no state a later run would honour.
    dismissals_enabled: bool
    # Whether a session may ask the reader a question and wait for the answer.
    # `--no-ask` is the rollback switch, and off means off in both directions:
    # the routes refuse, and the payload carries no `ask` flag, so the page
    # offers no control rather than one that answers 503.
    ask_enabled: bool
    # The trailing window every published token rate is averaged over. What a
    # row carries is therefore a MEAN and not an instantaneous reading, and at
    # ten minutes it lags a burst by minutes. `sessions.rate_from` divides by it,
    # and the three collectors that sum their own usage events rather than going
    # through it — Codex for a subagent thread, Goose, Antigravity — re-derive the
    # same figure against this same field. The page is told the number rather than
    # having "10 min" written into its markup, so the words on screen and the
    # arithmetic behind them cannot drift apart.
    rate_window_sec: float
    working_threshold_sec: float
    turn_gap_reset_sec: float
    tail_bytes: int
    popup_cooldown_sec: float
    global_popup_cooldown_sec: float
    popup_repeat_suppress_sec: float
    long_turn_warn_sec: float
    # The ceiling on Pi's tool-in-flight assertion. A `toolUse` leaf is the
    # agent's own in-progress marker and rightly outlives `working_threshold_sec`
    # — recency cannot tell a long `bash` from a parked session. It cannot
    # outlive everything, though: a transcript records that a tool started and
    # can never record that the process died, so a Pi hard-killed mid-tool
    # leaves that marker as the permanent branch tip. Tied to
    # `long_turn_warn_sec` on purpose: past that point the turn already carries
    # the amber long-turn flag, so the two would otherwise disagree about the
    # same request — one calling it worth a human's attention and the other
    # still calling it healthy.
    pi_tool_in_flight_max_sec: float
    loop_error_run_threshold: int
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
    # The three bounds on the Cursor model read. It is a hop through
    # content-addressed blobs — the root blob of a chat lists its message blobs
    # in order — so the cost is two indexed lookups, and these are what keep it
    # two rather than "however long the conversation is". `cursor_blob_bytes`
    # caps each blob in SQLite (a tool result runs to tens of kilobytes and the
    # field being looked for is twenty bytes), `cursor_root_children` caps the
    # id list parsed out of the root (its NEWEST ids — the child list runs
    # oldest first), and `cursor_model_probe_blobs` caps how far back the walk
    # goes before giving up.
    #
    # Measured on three live stores, 145 blobs: at most 24 children, and the
    # model was on the first blob tried every time. The probe depth is set by
    # the other end of that measurement — the longest run of consecutive
    # non-assistant children between two assistant messages is 5 (one turn with
    # five tool results in flight), which a 6-deep window clears by exactly
    # nothing: a sixth tool result mid-turn would fill the window and the
    # session would report no model at all. 12 is twice the measured worst case.
    # It is still bounded work under the read budget — at most twelve indexed
    # lookups of at most `cursor_blob_bytes` each, paid only by a store whose
    # mtime moved, since `_meta` memoizes the answer.
    cursor_blob_bytes: int
    cursor_root_children: int
    cursor_model_probe_blobs: int
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
    # The workflow README's frontmatter `title`, published as a strip's goal
    # line. The only project-authored *text* that reaches `/api/data` — every
    # other published value is a grammar-checked slug or a stage name — so it is
    # the one that needs a width of its own. 120 matches the ask lane's option
    # cap, which is the other place a line of somebody else's prose lands on the
    # page, and the README byte cap alone would have allowed a 64 KiB one on
    # every snapshot and every SSE push.
    spacedock_goal_cap_chars: int
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
    # The dismissal store. The read cap is the state file's, because the shape of
    # the risk is the same: a file this process wrote, which any local process
    # could have replaced with something enormous or deeply nested. The entry
    # bound is a count and not a time-to-live — see `dismissals._bounded` for why
    # a TTL is the wrong shape — and 256 is set against what a reader can
    # plausibly have marked handled inside one 24-hour window, an order of
    # magnitude above the busiest board measured (31 sessions).
    dismissal_read_cap_bytes: int
    dismissal_max_entries: int
    # What a dismissal request may declare. Three short fields, so this is far
    # below even the event cap: nothing else is read from the body.
    dismissal_body_cap_bytes: int
    prompt_path_collapse_min_length: int
    first_line_json_cap_bytes: int
    notification_body_cap_bytes: int
    # What an open question may occupy on a row. Characters, not bytes: this one
    # is measured where it is read, and a plan's first line is prose rather than
    # a payload.
    input_summary_cap_chars: int
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
    # A needs-input overlay has no deadline, because a real permission wait can
    # last hours. What ends it, absent a hook that says so, is the session's own
    # transcript moving again: an open prompt leaves the file quiet, and the
    # tool_result that follows a grant advances it. What that quiet is not is a
    # tool_use record written ahead of the prompt -- Claude Code writes it on no
    # schedule at all, and often not while the gate stands, which leaves the file
    # quieter still. See docs/design-needs-input.md (N-2). The grace absorbs the
    # ordering between a hook process and the write that provoked it, and nothing
    # else -- a wait that ends is over within one write, not within a minute.
    overlay_wait_activity_grace_sec: float
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
    # How many recent state disputes to keep. A ring, unlike the two caps above,
    # because a dispute is evidence rather than a live alert: losing the oldest
    # costs a sample, and refusing new ones would stop recording exactly when the
    # fault became frequent.
    dispute_log_max: int
    # Event ingress. The body cap is far below the notification cap because the
    # envelope is nine short fields and nothing else is read from it. The rate
    # ceiling is independent of the capability: a looping or compromised adapter
    # holds a valid token by definition, so the token cannot be what bounds it.
    # The burst allows one turn's worth of hooks to arrive together.
    event_body_cap_bytes: int
    event_rate_per_sec: float
    event_burst_max: int
    # The ask lane. The deadline is what retires a question nobody answered, and
    # five minutes is set against the thing on the other end: the asking session
    # is parked in a tool call for the whole wait, so a longer deadline buys a
    # reader nothing and costs an agent a stalled turn. There is no timer thread
    # to enforce it: the sweep rides on `AskRegistry.register` and on the
    # collection the coordinator now runs while any ask is outstanding, which is
    # what makes it independent of anybody watching the page.
    ask_deadline_sec: float
    # How long a resolved ask stays retrievable after the sweep first sees its
    # outcome, so its poller can still collect it. One minute is six poll holds
    # at `ask_poll_timeout_sec`, which is generous against a peer that is either
    # parked in `wait` and gets the answer instantly or is gone for good. Past
    # this the row is dropped; the budget never counted it, because a resolved
    # ask needs no slot.
    ask_retention_sec: float
    # One long-poll hold. Bounded rather than held open for the whole wait, which
    # is what keeps the thread budget, the shutdown decline and a dead peer all
    # ordinary: see docs/design-ask-lane.md.
    ask_poll_timeout_sec: float
    # A hard cap, not a queue: every outstanding ask costs a card on the page and
    # a polling peer, so past this the register route refuses with a 503.
    ask_max_pending: int
    # The register body carries a question and up to `ask_max_options` options,
    # so it is sized like the event envelope rather than like a notification.
    ask_body_cap_bytes: int
    # The answer body carries an id and an integer, and nothing else is read
    # from it.
    ask_answer_body_cap_bytes: int
    # What agent-written text may occupy. Characters, not bytes, because these
    # are bounded through `records.safe_text` at the HTTP ingress -- `asks`
    # imports nothing and cannot reach it -- and that helper counts characters.
    ask_question_cap_chars: int
    ask_option_cap_chars: int
    # A project path is not a label and routinely runs past any label cap: the
    # e2e run that found this had a 122-character cwd, so a 120 cap published a
    # directory that does not exist. Its own knob, and generous.
    ask_project_cap_chars: int
    ask_max_options: int
    # The observer analyzer: a read-only bystander that derives goal + stage +
    # block from a target session's transcript head and its workflow entity dir.
    # The head bound is what it reads from the transcript's opening records; the
    # goal and block caps bound the two derived strings it publishes, and the
    # context cap bounds the one string it hands *out*, to a model callable
    # nothing in the shipped tree supplies. That callable is a parameter rather
    # than a config field precisely so no model id lives here: naming one would
    # imply the analyzer calls it, and it does not.
    observer_head_bytes: int
    observer_goal_cap_chars: int
    observer_block_cap_chars: int
    observer_model_context_chars: int


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
        # The teams registry, one directory per lead session. It is the only
        # store that names a dispatched subagent BEFORE that subagent has
        # written a transcript byte, which is the whole on-disk trace of one
        # blocked at a startup gate (DRC-4263).
        "claude.teams": ordered(join(claude_home, "teams")),
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
    dismissals_enabled: bool = True,
    ask_enabled: bool = True,
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
        dismissals_enabled=dismissals_enabled,
        ask_enabled=ask_enabled,
        # Ten minutes stays. The burn ordering (DRC-4011) wants the fastest
        # session "right now", and this window is the reason it cannot have it:
        # narrowing it would re-scale the summary tile, both sparklines and every
        # rate on the board — `sessions.rate_from` and the three collectors that
        # do that arithmetic themselves — in one edit, for a figure that would then
        # be noisier on every surface that already reads it. So the board keeps the
        # mean and names it — the payload publishes this number and the ledger
        # states the window it ranked on, rather than claiming an immediacy the
        # arithmetic does not have.
        rate_window_sec=600,
        working_threshold_sec=90,
        turn_gap_reset_sec=300,
        tail_bytes=400_000,
        popup_cooldown_sec=60,
        global_popup_cooldown_sec=15,
        popup_repeat_suppress_sec=600,
        long_turn_warn_sec=900,
        pi_tool_in_flight_max_sec=900,
        # Consecutive failed tool calls before a turn is called a loop.
        # Measured, twice, over the 25 most recent local Claude transcripts:
        # run lengths came out {1: 56, 2: 4, 4: 1}, so 3 and 4 both fire in
        # 1 session of 25 and 5 fires in none. 4 buys the same yield as 3 with
        # strictly less exposure to the benign runs the sample was full of — an
        # `ls` that found nothing, a `git` in a deleted worktree. Lower is the
        # expensive direction: the pattern this keys on is also what iterating
        # on a failing test looks like, and a flag a reader learns to ignore
        # costs more than no flag.
        loop_error_run_threshold=4,
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
        cursor_blob_bytes=65_536,
        cursor_root_children=64,
        cursor_model_probe_blobs=12,
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
        spacedock_goal_cap_chars=120,
        collect_memo_sec=2.5,
        stream_max_clients=8,
        stream_heartbeat_sec=15.0,
        stream_write_timeout_sec=10.0,
        stream_producer_interval_sec=5.0,
        daemon_ready_timeout_sec=10.0,
        stop_release_timeout_sec=5.0,
        state_read_cap_bytes=65_536,
        dismissal_read_cap_bytes=65_536,
        dismissal_max_entries=256,
        dismissal_body_cap_bytes=1_024,
        prompt_path_collapse_min_length=25,
        first_line_json_cap_bytes=200_000,
        notification_body_cap_bytes=65_536,
        input_summary_cap_chars=160,
        usage_poll_floor_sec=300,
        usage_fetch_timeout_sec=10,
        usage_credentials_cap_bytes=65_536,
        usage_response_cap_bytes=262_144,
        usage_receipt_cap_bytes=131_072,
        overlay_wait_activity_grace_sec=10.0,
        overlay_working_ttl_sec=90,
        overlay_idle_dwell_sec=3.0,
        event_coalesce_sec=0.1,
        event_overlay_max_sessions=512,
        event_pending_max=256,
        event_pending_ttl_sec=60.0,
        reconcile_interval_sec=30.0,
        dispute_log_max=50,
        event_body_cap_bytes=8_192,
        event_rate_per_sec=20.0,
        event_burst_max=40,
        ask_deadline_sec=300.0,
        ask_retention_sec=60.0,
        ask_poll_timeout_sec=10.0,
        ask_max_pending=16,
        ask_body_cap_bytes=8_192,
        ask_answer_body_cap_bytes=1_024,
        ask_question_cap_chars=500,
        ask_option_cap_chars=120,
        ask_project_cap_chars=512,
        ask_max_options=8,
        observer_head_bytes=65_536,
        observer_goal_cap_chars=200,
        observer_block_cap_chars=200,
        observer_model_context_chars=8_192,
    )


def store_roots(config: RuntimeConfig, key: str) -> tuple[str, ...]:
    return config.store_roots.get(key, ())


def primary_store(config: RuntimeConfig, key: str) -> str:
    return store_roots(config, key)[0]
