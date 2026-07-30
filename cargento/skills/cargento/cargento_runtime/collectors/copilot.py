"""GitHub Copilot CLI collection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from cargento_runtime import io as runtime_io
from cargento_runtime import sessions, transcripts, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState

# history-session-state is assumed to share the <uuid>/events.jsonl layout —
# unverified legacy format; a mismatch just means those old sessions stay
# invisible. Discovery and collection read the same tuple so they cannot drift.
_STORE_BASES = ("session-state", "history-session-state")


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether either the current or the history Copilot store is present."""
    return any(runtime_io.any_store_dir(config, "copilot.root", base) for base in _STORE_BASES)


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    files: dict[
        str, tuple[float, str]
    ] = {}  # session uuid -> newest events.jsonl (dir tie: current)
    for base in _STORE_BASES:
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

    out: list[Session] = []
    for sid, (mtime, fp) in files.items():
        active = sessions.is_fresh(config, now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        info = transcripts.analyze_copilot_events(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, mtime)
        session_state, state_detail = "idle", "awaiting your message"
        subagents: list[str] = []
        if sessions.is_fresh(
            config,
            now,
            sessions.newest_plausible(config, now, last_event_sources),
            config.working_threshold_sec,
        ):
            session_state = "working"
            subagents = list((info or {}).get("pending_agents", {}).values())
            state_detail = sessions.working_detail(info, subagents)

        cwd = (info or {}).get("cwd") or transcripts.copilot_meta(config, state, fp).get("cwd")
        s = sessions.base_session(
            "copilot", sid, sessions.project_from_cwd(config, cwd or "") or "copilot"
        )
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
                "turn": turns.turn_progress(
                    turns.scan_turns(config, state, fp, "copilot") if info else None,
                    session_state,
                    now,
                    config,
                ),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out
