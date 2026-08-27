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
        shaped.update(sessions.reset_fields(now, resets))
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
    path: str,
    now: float,
    scan: dict[str, Any] | None,
) -> int:
    """Recent Codex subagent output after its own task_started boundary.

    Takes the scan rather than making it: the caller needs the same scan for
    the child's model, and one child file must not be walked twice in a pass.
    """
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
    # parent session_id -> {"agents": [(label, mtime, model, started_at)], "rate": int}
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
            # One scan, above both branches. The rate window is wider than the
            # working window today, so the rate branch happens to have scanned
            # every child the second branch renders — but that is two config
            # numbers agreeing, not an invariant, and a child's model must not
            # rest on it. Still gated on a child being inside one window or the
            # other, so a store full of finished threads is not re-walked.
            charged = sessions.is_fresh(config, now, mtime, config.rate_window_sec)
            rendered = sessions.is_fresh(config, now, mtime, config.working_threshold_sec)
            scan = turns.scan_turns(config, state, fp, "codex") if charged or rendered else None
            if charged:
                data["rate"] += _subagent_rate(config, fp, now, scan)
            if rendered:
                # The child's own rollout declares its own model; the page, not
                # the collector, decides whether it differs from the parent's.
                data["agents"].append(
                    (
                        (meta.get("agent_label") or "subagent")[:70],
                        mtime,
                        (scan or {}).get("model"),
                        turns.started_at(scan),
                    )
                )
            continue
        if sid not in found or mtime > found[sid][0]:
            found[sid] = (mtime, fp)

    out: list[Session] = []
    for sid, (mtime, fp) in found.items():
        data = agent_data.get(sid) or {"agents": [], "rate": 0}
        agents = sorted(data["agents"], key=lambda a: -a[1])
        activity_sources = (mtime, *(a[1] for a in agents))
        last_activity = sessions.newest_plausible(config, now, activity_sources)
        active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        info = transcripts.analyze_codex_transcript(config, fp) if active else None
        # The prompt and the instruction line come from a backward walk rather
        # than from `info`, whose tail read misses the newest prompt on 62% of
        # the rollouts that have one (DRC-4264). Behind the same `active` gate as
        # the analysis: a stale `?all=1` row pays for no read and reports no
        # title, which is "not read" rather than "no prompt".
        asked = (
            transcripts.codex_instruction(config, state, fp)
            if active
            else {"title": None, "last_prompt": "", "instruction": None}
        )
        # Hoisted above `subagents` because the model is published beside them,
        # and kept behind the `if info` guard so a stale `?all=1` row still pays
        # for no scan. Such a row reports no model rather than an old one: the
        # collector has not read it this pass, and that is the honest reading.
        scan = turns.scan_turns(config, state, fp, "codex") if info else None
        last_event_sources = (info["last_event_ts"] if info else 0, *activity_sources)
        subagents = [
            {"name": label, "model": model, "started_at": started_at}
            for label, _, model, started_at in agents
        ]
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
                "title": asked["title"],
                "last_prompt": asked["last_prompt"],
                "instruction": asked["instruction"],
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                # What retires a gate this session already answered. Codex reports
                # a gate through the event overlay, and the reducer only lets a
                # wait lapse when the session's OWN activity outruns it -- so
                # without this the row stayed red from the approval to the turn's
                # `Stop`, which is DRC-4097 on a second harness.
                #
                # The rollout's own newest record, not its mtime and not
                # `last_activity`: the latter folds in subagent files, and a child
                # writing says nothing about whether the human answered. Measured
                # on 0.149.0 rather than assumed, because the whole value of the
                # signal is that it stays put while a person is being asked: with
                # a real approval prompt standing open the rollout held at 13
                # lines and one timestamp across 25 seconds, then advanced to 27
                # once the gate was answered. A tail with no timestamp reports 0,
                # which leaves the wait standing -- the safe direction, and the
                # one an unreported value already takes in the reducer.
                "own_activity": (info or {}).get("last_event_ts") or 0,
                "started_at": turns.started_at(scan),
                "rate_per_min": sessions.rate_from(info, now, config) + data["rate"],
                "session_output_tokens": (scan.get("session_output_tokens") if scan else None),
                "turn_output_tokens": scan.get("turn_output_tokens") if scan else None,
                "turn": turns.turn_progress(scan, session_state, now, config),
                # `provider` stays None: no Codex record carries one, and
                # reading "openai" off the harness name would be inference.
                "model": scan.get("model") if scan else None,
                "subagents": subagents,
            }
        )
        out.append(s)
    return out
