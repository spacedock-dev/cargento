"""Factory Droid transcript collection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from cargento_runtime import io as runtime_io
from cargento_runtime import sessions, transcripts, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState

_TRANSCRIPT_GLOB = ("*", "*.jsonl")


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether any Droid project holds a transcript."""
    return bool(runtime_io.glob_stores(config, "droid.projects", *_TRANSCRIPT_GLOB))


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    out: list[Session] = []
    for fp in runtime_io.glob_stores(config, "droid.projects", *_TRANSCRIPT_GLOB):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        active = sessions.is_fresh(config, now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        meta = transcripts.droid_meta(config, state, fp)
        sid = str(meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")])
        info = transcripts.analyze_droid_transcript(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, mtime)
        session_state, state_detail = "idle", "awaiting your message"
        if sessions.is_fresh(
            config,
            now,
            sessions.newest_plausible(config, now, last_event_sources),
            config.working_threshold_sec,
        ):
            session_state = "working"
            state_detail = sessions.working_detail(info, [])

        project = sessions.project_from_cwd(
            config, meta.get("cwd") or ""
        ) or sessions.project_label(config, os.path.basename(os.path.dirname(fp)))
        s = sessions.base_session("droid", sid, project)
        scan = turns.scan_turns(config, state, fp, "droid") if info else None
        s.update(
            {
                "title": (meta.get("title") or "").strip()[:80] or (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
                "started_at": turns.started_at(scan),
                "session_output_tokens": (scan.get("session_output_tokens") if scan else None),
                "turn_output_tokens": scan.get("turn_output_tokens") if scan else None,
                "turn": turns.turn_progress(
                    scan,
                    session_state,
                    now,
                    config,
                ),
            }
        )
        out.append(s)
    return out
