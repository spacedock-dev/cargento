"""Codex rollout collection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

# Absolute on the canonical top-level package: a sub-package cannot use
# parent-relative imports without tripping the repository's own TID252 rule.
from cargento_runtime import io as runtime_io
from cargento_runtime import records, sessions, transcripts, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether a Codex sessions store is present."""
    return runtime_io.any_store_dir(config, "codex.sessions")


# Rollout tails examined for a quota snapshot, newest mtime first. Token
# events are frequent, so the snapshot is almost always in the newest file;
# the rest of the budget covers a file that was only just created.
_USAGE_FILE_CAP = 8


def _usage_window(now: float, raw: Any) -> tuple[str, dict[str, Any]] | None:
    """One rate_limits window mapped onto the payload contract, or nothing."""
    win = records.as_dict(raw)
    pct = win.get("used_percent")
    minutes = win.get("window_minutes")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return None
    if not isinstance(minutes, (int, float)) or isinstance(minutes, bool):
        return None
    # Codex names no windows, only durations: 300 minutes is the 5-hour
    # window, 10080 the weekly. Classify by length so a plan that carries
    # only one of them (prolite writes just the weekly) still maps.
    key = "fiveH" if minutes < 1440 else "week"
    shaped: dict[str, Any] = {"pct": max(0, min(100, round(pct)))}
    resets = win.get("resets_at")
    if isinstance(resets, (int, float)) and not isinstance(resets, bool) and resets > 0:
        shaped["reset"] = sessions.format_reset(now, resets)
    return key, shaped


def usage(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
) -> list[dict[str, Any]]:
    """The newest quota snapshot Codex left on disk, as one usage entry.

    Codex writes ``rate_limits`` beside every token count, so this is a read
    of what is already there: no network, no credential, and a snapshot only
    as fresh as the last active turn, which is why the entry carries ``asOf``.
    One entry for the whole store — the CLI reports account quota, not
    per-session quota.
    """
    del state
    files: list[tuple[float, str]] = []
    for fp in runtime_io.glob_stores(
        config,
        "codex.sessions",
        "*",
        "*",
        "*",
        "rollout-*.jsonl",
    ):
        try:
            files.append((os.path.getmtime(fp), fp))
        except OSError:
            continue
    best: tuple[float, dict[str, Any]] | None = None
    for _, fp in sorted(files, reverse=True)[:_USAGE_FILE_CAP]:
        snap = transcripts.analyze_codex_transcript(config, fp)["rate_limits"]
        if snap and (best is None or snap[0] > best[0]):
            best = snap
    # A snapshot older than the dashboard's own activity window describes
    # quota windows that have themselves reset; the band's empty state is
    # more honest than a number that old.
    if not best or not sessions.is_fresh(config, now, best[0], window_hours * 3600):
        return []
    epoch, limits = best
    entry: dict[str, Any] = {"harness": "codex", "state": "ok", "asOf": int(epoch)}
    for raw in (limits.get("primary"), limits.get("secondary")):
        mapped = _usage_window(now, raw)
        if mapped:
            entry.setdefault(mapped[0], mapped[1])
    if "fiveH" not in entry and "week" not in entry:
        return []
    return [entry]


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
    # Resumes and subagent threads each write their own rollout file, so group
    # by the session_meta session_id rather than by file.
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
