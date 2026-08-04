"""Claude Code collection: task files, subagents, sessions, and Spacedock strips."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from cargento_runtime import claude_data, notifications
from cargento_runtime import io as runtime_io
from cargento_runtime import quota as runtime_quota
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime import spacedock as runtime_spacedock
from cargento_runtime import turns as runtime_turns

if TYPE_CHECKING:
    from collections.abc import Callable

    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState


# Subagent transcripts sit beneath the session directory in two layouts. A
# plain Task subagent lands directly in subagents/; a workflow fan-out nests
# one level deeper, under the run that owns it. Missing the second layout hid
# every workflow agent, which is how a session driving ten of them read Idle.
SUBAGENT_GLOBS = (
    ("subagents", "agent-*.jsonl"),
    ("subagents", "workflows", "*", "agent-*.jsonl"),
)


def load_tasks(config: RuntimeConfig) -> dict[str, list[dict[str, Any]]]:
    """session prefix -> list of task dicts."""
    by_session: dict[str, list[dict[str, Any]]] = {}
    for fp in runtime_io.glob_stores(config, "claude.tasks", "*", "*.json"):
        if os.path.basename(fp).startswith("."):
            continue
        try:
            # Explicit UTF-8: the locale default is cp1252 on Windows, which
            # mojibakes non-ASCII task subjects and raises UnicodeDecodeError on
            # the bytes that code page leaves undefined. That is a ValueError but
            # not a JSONDecodeError, so narrowing the handler below lets it escape
            # and error the whole Claude collector for a pass.
            with open(fp, encoding="utf-8") as f:
                task = json.load(f)
            st = os.stat(fp)
        except (OSError, ValueError):
            continue
        if not isinstance(task, dict):
            continue
        dirname = os.path.basename(os.path.dirname(fp))
        dirname = dirname.removeprefix("session-")
        prefix = dirname[:8]
        if not prefix:
            continue
        created = getattr(st, "st_birthtime", st.st_mtime)
        # Field types are unvalidated JSON from disk — coerce non-strings so
        # one malformed record cannot TypeError the whole Claude collector.
        subject = task.get("subject")
        active_form = task.get("activeForm")
        status = task.get("status")
        by_session.setdefault(prefix, []).append(
            {
                "id": task.get("id"),
                "subject": subject if isinstance(subject, str) and subject else "(untitled)",
                "activeForm": active_form if isinstance(active_form, str) else "",
                "status": status if isinstance(status, str) and status else "pending",
                "created": created,
                "updated": st.st_mtime,
            }
        )
    return by_session


def agent_transcripts(transcript: str | None) -> list[tuple[str, float]]:
    """(path, mtime) for every subagent transcript belonging to a session."""
    if not transcript:
        return []
    sess_dir = os.path.join(
        os.path.dirname(transcript), os.path.basename(transcript)[: -len(".jsonl")]
    )
    found: list[tuple[str, float]] = []
    for pattern in SUBAGENT_GLOBS:
        for fp in runtime_io.glob_under(sess_dir, *pattern):
            try:
                found.append((fp, os.path.getmtime(fp)))
            except OSError:
                continue  # transcript rotated/deleted between glob and stat
    return found


def load_subagents(
    config: RuntimeConfig, transcript: str | None, now: float
) -> list[dict[str, Any]]:
    """Running Claude subagents beneath the session directory; fresh mtime =
    running. Covers both layouts in ``SUBAGENT_GLOBS``."""
    agents: list[dict[str, Any]] = []
    for fp, mtime in agent_transcripts(transcript):
        if not runtime_sessions.is_fresh(config, now, mtime, config.working_threshold_sec):
            continue
        label = None
        try:
            with open(fp[: -len(".jsonl")] + ".meta.json", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):  # ValueError covers UnicodeDecodeError
            meta = None
        # Meta values are untyped JSON: a non-string name must not TypeError the
        # whole Claude collector.
        if isinstance(meta, dict):
            for key in ("name", "description", "agentType"):
                value = meta.get(key)
                if isinstance(value, str) and value:
                    label = value
                    break
        agents.append({"label": (label or "subagent")[:70], "mtime": mtime})
    agents.sort(key=lambda a: -a["mtime"])
    return agents


def session_spacedock(
    config: RuntimeConfig,
    state: RuntimeState,
    transcript: str | None,
    subagents: list[dict[str, Any]],
    now: float,
    window_sec: float,
) -> dict[str, Any] | None:
    """Spacedock role and workflow strips for one Claude session, or None.

    Gated on the session declaring a Spacedock ``agentSetting``, so a session
    that has nothing to do with Spacedock costs one cached lookup and opens no
    project file. Only a first officer gets strips: an ensign is a single worker
    whose own stage is already the parent's strip.
    """
    if not transcript:
        return None
    setting = claude_data.agent_setting(config, state, transcript)
    if setting == runtime_spacedock.SPACEDOCK_ENSIGN:
        return {"role": "ensign", "workflows": []}
    if setting != runtime_spacedock.SPACEDOCK_FO:
        return None
    if not config.spacedock_enabled:
        # The switch withdraws the project reads, not the role: the badge comes
        # from the transcript head, which is a store path either way.
        return {"role": "first-officer", "workflows": []}
    boot = runtime_spacedock.transcript_boot(config, state, transcript)
    names = [str(a.get("label") or "") for a in subagents]
    return {
        "role": "first-officer",
        "workflows": runtime_spacedock.session_workflows(
            config, state, boot, names, now, window_sec
        ),
    }


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether a Claude projects store is present."""
    return runtime_io.any_store_dir(config, "claude.projects")


def usage(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
) -> list[dict[str, Any]]:
    """The last fetched Claude quota, read from the quota module's cache.

    This provider never touches the network: the fetch runs on its own thread,
    triggered by `/api/data` requests carrying the page's consent, and this
    only publishes whatever that thread last cached. The registry wires it in
    only when the fetch feature is enabled, so `--no-usage` leaves the Claude
    row with no provider at all.
    """
    del config, now, window_hours
    return runtime_quota.cached_entries(state)


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
    *,
    popup_notifier: Callable[[str, str], None],
) -> list[Session]:
    tasks_by_session = load_tasks(config)
    transcripts: dict[str, str] = {}  # prefix -> newest transcript path
    agent_children: dict[str, list[dict[str, Any]]] = {}  # parent prefix -> children
    for fp in runtime_io.glob_stores(config, "claude.projects", "*", "*.jsonl"):
        base = os.path.basename(fp)
        if "-agent-" in base or base.startswith("agent-"):
            continue  # legacy subagent transcripts aren't top-level sessions
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue  # transcript rotated/deleted between glob and stat
        if show_all or runtime_sessions.is_fresh(config, now, mtime, window_hours * 3600):
            is_agent, agent_name, parent_prefix = claude_data.agent_identity(config, state, fp)
            if is_agent:
                # Fold into the parent, never a standalone session; without a
                # parent prefix there is nothing to attach to.
                if parent_prefix and runtime_sessions.is_fresh(
                    config, now, mtime, window_hours * 3600
                ):
                    agent_children.setdefault(parent_prefix, []).append(
                        {
                            "path": fp,
                            "mtime": mtime,
                            "label": (agent_name or "subagent")[:70],
                        }
                    )
                continue
        prefix = base[:8]
        try:
            if prefix not in transcripts or mtime > os.path.getmtime(transcripts[prefix]):
                transcripts[prefix] = fp
        except OSError:
            continue  # transcript rotated/deleted between glob and stat

    out: list[Session] = []
    for prefix in set(transcripts) | set(tasks_by_session):
        transcript = transcripts.get(prefix)
        tasks = sorted(
            tasks_by_session.get(prefix, []),
            key=lambda t: int(t["id"]) if str(t["id"]).isdigit() else 0,
        )
        try:
            transcript_mtime = os.path.getmtime(transcript) if transcript else 0
        except OSError:
            transcript_mtime = 0
        latest_task_mtime = max((t["updated"] for t in tasks), default=0)
        agent_files = agent_transcripts(transcript)
        subagents = load_subagents(config, transcript, now)
        children = agent_children.get(prefix, [])
        subagents += [
            {"label": c["label"], "mtime": c["mtime"]}
            for c in children
            if runtime_sessions.is_fresh(
                config, now, c["mtime"], config.working_threshold_sec
            )  # fresh = running
        ]
        latest_agent_mtime = max(
            (a["mtime"] for a in subagents),
            default=0,
        )
        latest_child_mtime = max((c["mtime"] for c in children), default=0)
        # Every subagent write, not just the ones fresh enough to read as
        # running: a workflow that has been going for hours parks its parent
        # transcript, and without this the session ages out of the window.
        latest_agent_file_mtime = max((m for _, m in agent_files), default=0)
        activity_sources = (
            latest_task_mtime,
            transcript_mtime,
            latest_agent_mtime,
            latest_agent_file_mtime,
            latest_child_mtime,
        )
        last_activity = runtime_sessions.newest_plausible(config, now, activity_sources)
        active = runtime_sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue

        project = (
            (
                runtime_sessions.project_from_cwd(
                    config, claude_data.session_cwd(config, state, transcript)
                )
                # Lossy fallback: the encoded name cannot be split back into
                # segments, so it stays whole rather than guessing at a split.
                or runtime_sessions.project_label(
                    config, os.path.basename(os.path.dirname(transcript))
                )
            )
            if transcript
            else "unknown"
        )
        # Sampled before analyze_transcript: that scan is the slow part, and a
        # SessionEnd landing during it must invalidate everything derived here.
        seen_generation = notifications.hook_generation(state, prefix)
        info = (
            claude_data.analyze_transcript(config, state, transcript)
            if (transcript and active)
            else None
        )

        session_state, state_detail = "idle", "awaiting your message"
        blocked_since = None
        # mtime floor: match the other collectors when the newest write has
        # no parseable timestamp (partial line, untimestamped record)
        parsed_last_event = info["last_event_ts"] if info else 0
        last_event_sources = (parsed_last_event, transcript_mtime)
        hook = (
            notifications.current_hook(
                state, prefix, (info or {}).get("last_user_event"), parsed_last_event
            )
            if active
            else None
        )
        if info and info["pending_input_tool"]:
            p = info["pending_input_tool"]
            session_state = "needs_input"
            blocked_since = p["ts"] or last_activity
            state_detail = f"open question ({p['name']}), waiting {runtime_sessions.fmt_duration(runtime_sessions.age(config, now, p['ts'])) if p['ts'] else '?'}"
        # Fresh activity beats a hook: Claude Code emits "waiting for your
        # input" notifications for sessions that keep running via background
        # tasks and will resume on their own. A hook only surfaces as
        # needs-input once the session actually goes quiet; permission-prompt
        # popups are unaffected (they fire on the POST itself).
        elif subagents or runtime_sessions.is_fresh(
            config,
            now,
            runtime_sessions.newest_plausible(config, now, last_event_sources),
            config.working_threshold_sec,
        ):
            session_state = "working"
            in_prog = next((t for t in tasks if t["status"] == "in_progress"), None)
            if in_prog:
                state_detail = (in_prog["activeForm"] or in_prog["subject"]) + "…"
            else:
                state_detail = runtime_sessions.working_detail(info, subagents)
        elif hook:
            session_state = "needs_input"
            blocked_since = hook["ts"]
            state_detail = hook["message"] or "waiting for your input"
        if (
            session_state == "needs_input"
            and notifications.hook_generation(state, prefix) != seen_generation
        ):
            # The session exited while this snapshot was being built. Applies to
            # the transcript-detected case too: an unanswered AskUserQuestion in
            # a session the user has quit is moot, not blocking.
            session_state, blocked_since = "idle", None
            state_detail = "awaiting your message"
        if active:
            notifications.maybe_popup(
                config,
                state,
                prefix,
                session_state,
                f"[{project}] {state_detail}" if session_state == "needs_input" else None,
                expect_generation=seen_generation,
                popup_notifier=popup_notifier,
            )

        total = len(tasks)
        done = sum(1 for t in tasks if t["status"] == "completed")
        open_count = total - done
        durations = [
            t["updated"] - t["created"]
            for t in tasks
            if t["status"] == "completed" and (t["updated"] - t["created"]) >= 30
        ]
        eta_sec = (
            (sum(durations) / len(durations)) * open_count if durations and open_count else None
        )

        for t in tasks:
            elapsed = (
                (t["updated"] - t["created"])
                if t["status"] == "completed"
                else runtime_sessions.age(config, now, t["created"])
            )
            t["elapsed_h"] = runtime_sessions.fmt_duration(elapsed)
            t["updated_ago"] = (
                runtime_sessions.fmt_duration(runtime_sessions.age(config, now, t["updated"]))
                + " ago"
            )

        s = runtime_sessions.base_session("claude", prefix, project)
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": session_state,
                "state_detail": state_detail,
                "blocked_since": blocked_since,
                "active": active,
                "last_activity": last_activity,
                # Subagent output lives in the children's own transcripts; fold
                # it in so the session's rate reflects all its work.
                "rate_per_min": runtime_sessions.rate_from(info, now, config)
                + sum(
                    runtime_sessions.rate_from(
                        claude_data.analyze_transcript(config, state, path),
                        now,
                        config,
                    )
                    for path, mtime in agent_files
                    if runtime_sessions.is_fresh(config, now, mtime, config.rate_window_sec)
                )
                + sum(
                    runtime_sessions.rate_from(
                        claude_data.analyze_transcript(config, state, c["path"]),
                        now,
                        config,
                    )
                    for c in children
                    if runtime_sessions.is_fresh(config, now, c["mtime"], config.rate_window_sec)
                ),
                "total": total,
                "done": done,
                "open": open_count,
                "progress_pct": round(done * 100 / total) if total else 0,
                "eta_h": runtime_sessions.fmt_duration(eta_sec) if eta_sec else None,
                "turn": runtime_turns.turn_progress(
                    runtime_turns.scan_turns(config, state, transcript, "claude")
                    if (info and transcript)
                    else None,
                    session_state,
                    now,
                    config,
                ),
                "subagents": [a["label"] for a in subagents],
                "tasks": tasks,
                "spacedock": session_spacedock(
                    config, state, transcript, subagents, now, window_hours * 3600
                ),
            }
        )
        out.append(s)
    return out
