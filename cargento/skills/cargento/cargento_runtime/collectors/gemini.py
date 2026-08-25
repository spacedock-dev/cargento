"""Gemini CLI collection.

Gemini CLI stopped serving consumer accounts on 2026-06-18, and Antigravity CLI
is Google's current agent. It does *not* follow that nothing writes this store.
Enterprise Gemini Code Assist licences and API-key authentication were explicitly
unaffected, and the CLI is actively released: 0.53.1 shipped on 2026-07-31 with
nightly builds continuing, and a real 0.53.1 session was measured writing
``<tmp>/<project>/chats/session-*.jsonl``, the layout this collector globs. Say
"consumer access ended" rather than "legacy".

That measurement is also what cleared the adapter gate: Gemini's hooks carry the
same ``session_id`` this collector keys on, so live events reach these rows. See
``docs/captures/gemini/`` for the evidence and ``event_hook.py`` for the mapping.

Antigravity is its own collector beside this one; see
``docs/design-harness-registry.md``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from cargento_runtime import io as runtime_io
from cargento_runtime import records, sessions, transcripts, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    # Gemini CLI main sessions: <tmp>/<project>/chats/session-*.jsonl. The file
    # name carries only the first eight characters of the session id; the whole id
    # is on line 1, which is why `sid` is read from the file and not the name.
    # Subagents: <tmp>/<project>/chats/<safeParentSessionId>/<id>.jsonl, linked
    # to the parent purely by the directory name. Antigravity CLI sessions are
    # appended from its per-conversation SQLite stores below.
    # sanitized parent session id -> [(label, mtime)]
    agents_by_parent: dict[str, list[tuple[str, float]]] = {}
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
        if not sessions.is_fresh(config, now, mtime, config.working_threshold_sec):
            continue
        parent = records.alnum(os.path.basename(os.path.dirname(fp)))
        label = "subagent " + os.path.basename(fp)[:8]
        agents_by_parent.setdefault(parent, []).append((label, mtime))

    found: dict[str, tuple[float, str]] = {}  # session id (or filename fallback) -> (mtime, path)
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
        meta = transcripts.gemini_meta(config, state, fp)
        if meta.get("kind") == "subagent":
            continue
        sid = meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")]
        if sid not in found or mtime > found[sid][0]:
            found[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in found.items():
        agents = sorted(agents_by_parent.get(records.alnum(sid), []), key=lambda a: -a[1])
        activity_sources = (mtime, *(m for _, m in agents))
        last_activity = sessions.newest_plausible(config, now, activity_sources)
        active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        info = transcripts.analyze_gemini_transcript(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, *activity_sources)
        # `model` is always present on a subagent element, per the contract in
        # `sessions.base_session`. None here says nobody has looked for where
        # Gemini records the model, not that Gemini runs on none.
        subagents = [{"name": label, "model": None, "started_at": None} for label, _ in agents]
        session_state, state_detail = "idle", "awaiting your message"
        if sessions.is_fresh(
            config,
            now,
            sessions.newest_plausible(config, now, last_event_sources),
            config.working_threshold_sec,
        ):
            session_state = "working"
            state_detail = sessions.working_detail(info, subagents)

        cwd = transcripts.gemini_meta(config, state, fp).get("cwd")
        project = sessions.project_from_cwd(config, cwd or "") or sessions.project_label(
            config, os.path.basename(os.path.dirname(os.path.dirname(fp)))
        )
        s = sessions.base_session("gemini", sid, project)
        scan = turns.scan_turns(config, state, fp, "gemini") if info else None
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": sessions.rate_from(info, now, config),
                "started_at": turns.started_at(scan),
                "turn": turns.turn_progress(
                    scan,
                    session_state,
                    now,
                    config,
                ),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether a Gemini CLI chat store is present."""
    return bool(runtime_io.glob_stores(config, "gemini.tmp", "*", "chats", "session-*.jsonl"))
