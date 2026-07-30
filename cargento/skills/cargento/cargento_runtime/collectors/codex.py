"""Codex rollout collection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

# Absolute on the canonical top-level package: a sub-package cannot use
# parent-relative imports without tripping the repository's own TID252 rule.
from cargento_runtime import io as runtime_io
from cargento_runtime import sessions, transcripts, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether a Codex sessions store is present."""
    return runtime_io.any_store_dir(config, "codex.sessions")


def _subagent_rate(
    config: RuntimeConfig,
    state: RuntimeState,
    path: str,
    now: float,
) -> int:
    """Recent Codex subagent output after its own task_started boundary."""
    scan = turns.scan_turns(config, state, path, "codex")
    start = scan.get("last_start") if scan else None
    if not start:
        return 0
    info = transcripts.analyze_codex_transcript(config, path)
    recent: float = sum(
        tokens
        for epoch, tokens in info["usage_events"]
        if epoch >= start and sessions.is_fresh(config, now, epoch, config.rate_window_sec)
    )
    return round(recent / (config.rate_window_sec / 60))


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    # Resumes and subagent threads write separate rollout files; group by the
    # session_meta session_id, keep the newest top-level file per session,
    # and treat fresh subagent-thread files as that session's running agents.
    found: dict[str, tuple[float, str]] = {}  # session_id -> (mtime, path)
    # parent session_id -> {"agents": [(label, mtime)], "rate": int}
    agent_data: dict[str, dict[str, Any]] = {}
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
        meta = transcripts.codex_meta(config, state, fp)
        sid = meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")][-36:]
        if meta.get("subagent"):
            parent_sid = meta.get("parent_session_id") or sid
            data = agent_data.setdefault(parent_sid, {"agents": [], "rate": 0})
            if sessions.is_fresh(config, now, mtime, config.rate_window_sec):
                data["rate"] += _subagent_rate(config, state, fp, now)
            if sessions.is_fresh(config, now, mtime, config.working_threshold_sec):
                data["agents"].append(((meta.get("agent_label") or "subagent")[:70], mtime))
            continue
        if sid not in found or mtime > found[sid][0]:
            found[sid] = (mtime, fp)

    out: list[Session] = []
    for sid, (mtime, fp) in found.items():
        data = agent_data.get(sid) or {"agents": [], "rate": 0}
        agents = sorted(data["agents"], key=lambda a: -a[1])
        activity_sources = (mtime, *(m for _, m in agents))
        last_activity = sessions.newest_plausible(config, now, activity_sources)
        active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        info = transcripts.analyze_codex_transcript(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, *activity_sources)
        subagents = [label for label, _ in agents]
        session_state, state_detail = "idle", "awaiting your message"
        if sessions.is_fresh(
            config,
            now,
            sessions.newest_plausible(config, now, last_event_sources),
            config.working_threshold_sec,
        ):
            session_state = "working"
            state_detail = sessions.working_detail(info, subagents)

        s = sessions.base_session(
            "codex",
            sid,
            sessions.project_from_cwd(
                config,
                transcripts.codex_meta(config, state, fp).get("cwd") or "",
            )
            or "codex",
        )
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": sessions.rate_from(info, now, config) + data["rate"],
                "turn": turns.turn_progress(
                    turns.scan_turns(config, state, fp, "codex") if info else None,
                    session_state,
                    now,
                    config,
                ),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out
