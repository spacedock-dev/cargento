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
from cargento_runtime import state as runtime_state
from cargento_runtime import turns as runtime_turns

if TYPE_CHECKING:
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


def subagent_tree_stamp(sess_dir: str) -> tuple[float, ...]:
    """The mtimes of every directory a ``SUBAGENT_GLOBS`` pattern can reach.

    A file appears in or leaves a directory only by changing that directory's
    mtime, so this tuple is a complete change detector for the listing: the two
    container directories catch a first flat subagent and a first workflow run,
    and every existing run directory catches an agent landing inside a run that
    the glob has already walked. Watching the run directories by listing them,
    rather than by taking the parents of an existing listing, is what makes the
    empty case safe: a run directory is created a beat before its first agent
    transcript, and a run watched only once it holds one would never notice the
    file that put it there. Absent directories stamp as -1 rather than dropping
    out, so a directory appearing changes the tuple instead of shifting it.
    """
    subagents = os.path.join(sess_dir, "subagents")
    workflows = os.path.join(subagents, "workflows")
    watched = {sess_dir, subagents, workflows}
    try:
        with os.scandir(workflows) as entries:
            watched.update(entry.path for entry in entries if entry.is_dir())
    except OSError:
        pass  # no workflows directory: the two containers are the whole tree
    stamp: list[float] = []
    for directory in sorted(watched):
        try:
            stamp.append(os.stat(directory).st_mtime)
        except OSError:
            stamp.append(-1.0)  # absent, or a file where a directory was expected
    return tuple(stamp)


def agent_transcripts(
    transcript: str | None,
    *,
    config: RuntimeConfig | None = None,
    state: RuntimeState | None = None,
) -> list[tuple[str, float]]:
    """(path, mtime) for every subagent transcript belonging to a session.

    With ``config`` and ``state`` the glob is memoised on the subagent tree's
    directory mtimes, which is what makes a large history cheap: most session
    directories belong to finished work and are walked once per process rather
    than once per collection. Without them the scan is unmemoised, so callers
    outside a runtime keep working.
    """
    if not transcript:
        return []
    sess_dir = os.path.join(
        os.path.dirname(transcript), os.path.basename(transcript)[: -len(".jsonl")]
    )
    # Most historical prefixes never ran a subagent, so the directory is absent.
    # One stat is cheaper than running every SUBAGENT_GLOBS pattern against a
    # path that cannot match.
    if not os.path.isdir(sess_dir):
        return []
    cache = None if state is None or config is None else state.claude_subagent_cache
    # Stamped before the listing, never after it. A transcript written while the
    # tree is being walked moves a directory mtime, and a stamp taken afterwards
    # would record that move as already accounted for, pinning the listing that
    # missed the file. Stamping first can only cost one extra glob next time.
    stamp = None if cache is None else subagent_tree_stamp(sess_dir)
    hit = None if cache is None else cache.get(sess_dir)
    if hit is not None and hit[0] == stamp:
        return stamped(hit[1])
    paths = [fp for pattern in SUBAGENT_GLOBS for fp in runtime_io.glob_under(sess_dir, *pattern)]
    if cache is not None and config is not None and stamp is not None:
        runtime_state.bounded_put(
            cache, sess_dir, (stamp, list(paths)), limit=config.max_cache_entries
        )
    return stamped(paths)


def stamped(paths: list[str]) -> list[tuple[str, float]]:
    """(path, current mtime) per path, dropping any that has since gone.

    Restated on every call, cached listing or not: a subagent writing to its
    transcript moves no directory mtime, so serving a remembered mtime would
    freeze a running agent at the moment it was first seen.
    """
    found: list[tuple[str, float]] = []
    for fp in paths:
        try:
            found.append((fp, os.path.getmtime(fp)))
        except OSError:
            continue  # transcript rotated/deleted between glob and stat
    return found


def child_model(analysis: dict[str, Any] | None) -> str | None:
    """The model a subagent's own transcript reports, or None.

    ``model_sidechain`` first, then ``model``, because ``isSidechain`` inverts
    between a session and its children: a subagent's own assistant records are
    all flagged as sidechains, so its model lands in the sidechain half of
    ``claude_data.analyze_transcript``. Reading both, in that order, is what lets
    one helper serve a legacy ``agent-*.jsonl`` transcript and a modern child
    ``<uuid>.jsonl`` alike.

    Never falls back to the parent's model: an unread child is published as None
    so the page can tell "the same model as its parent" from "not measured".
    """
    if not analysis:
        return None
    value = analysis.get("model_sidechain") or analysis.get("model")
    return value if isinstance(value, str) and value else None


def load_subagents(
    config: RuntimeConfig,
    transcript: str | None,
    now: float,
    *,
    found: list[tuple[str, float]] | None = None,
    models: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    """Running Claude subagents beneath the session directory; fresh mtime =
    running. Covers both layouts in ``SUBAGENT_GLOBS``.

    ``found`` lets a caller that has already listed the directory hand the
    listing over, so one session costs one scan. The collector needs the full
    listing anyway for its parked-parent activity check.

    ``models`` is transcript path -> the model that transcript reports, from the
    analysis the caller has already run for the session's rate. A path this
    function is not told about publishes None, which is what a caller with no
    analyses to hand gets for every agent — never a guess at the parent's model.
    """
    agents: list[dict[str, Any]] = []
    for fp, mtime in agent_transcripts(transcript) if found is None else found:
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
        agents.append(
            {
                "label": (label or "subagent")[:70],
                "mtime": mtime,
                "model": (models or {}).get(fp),
                "started_at": claude_data.transcript_started_at(config, fp),
            }
        )
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
    return runtime_quota.cached_entries(state, "claude")


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
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
        agent_files = agent_transcripts(transcript, config=config, state=state)
        children = agent_children.get(prefix, [])
        # One analysis per child transcript, read once and shared by everything
        # below that wants it: the session's output rate, and the model published
        # beside each running subagent's label. The two select on different
        # windows — `rate_window_sec` for the rate, `working_threshold_sec` for
        # the pills — so the union of the windows is what keeps this at one read
        # per file whichever of them a given child falls inside. `is_fresh` is
        # monotone in its window, so the wider window *is* the union; this must
        # not become a check against `working_threshold_sec` alone, because
        # nothing enforces that it is the smaller of the two.
        child_files = [*agent_files, *((c["path"], c["mtime"]) for c in children)]
        analyses = {
            path: claude_data.analyze_transcript(config, state, path)
            for path, mtime in child_files
            if runtime_sessions.is_fresh(
                config, now, mtime, max(config.rate_window_sec, config.working_threshold_sec)
            )
        }
        models = {path: child_model(analysis) for path, analysis in analyses.items()}
        subagents = load_subagents(config, transcript, now, found=agent_files, models=models)
        subagents += [
            {
                "label": c["label"],
                "mtime": c["mtime"],
                "model": models.get(c["path"]),
                "started_at": claude_data.transcript_started_at(config, c["path"]),
            }
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
        # Whether the standing hook is a prompt this build recognises. Only a
        # recognised one is allowed to outrank a live subagent below.
        actionable_prompt = notifications.hook_is_actionable_prompt(hook)
        if info and info["pending_input_tool"]:
            p = info["pending_input_tool"]
            session_state = "needs_input"
            blocked_since = p["ts"] or last_activity
            waited = (
                runtime_sessions.fmt_duration(runtime_sessions.age(config, now, p["ts"]))
                if p["ts"]
                else "?"
            )
            # The question itself when the record carried it, the tool's name when
            # it did not. Both happen: the record reaches disk on no schedule, so
            # this reads as one or the other rather than appearing and vanishing
            # for the same session. See docs/design-needs-input.md (N-4).
            asks = p.get("asks") or ""
            state_detail = (
                f"{asks}, waiting {waited}"
                if asks
                else f"open question ({p['name']}), waiting {waited}"
            )
        # Fresh activity in the session's *own* transcript still beats a hook:
        # Claude Code emits "waiting for your input" notifications for sessions
        # that keep running via background tasks and will resume on their own.
        # That window self-clears, because an open prompt leaves the parent
        # transcript quiet, so a genuinely blocked session falls out of the window
        # and surfaces. The quiet does not rest on the tool_use record being
        # written ahead of the prompt: it is written on no schedule at all, and a
        # record that never arrives leaves the file quieter still. See
        # docs/design-needs-input.md (N-2).
        #
        # A live subagent is different, and used to be tested here as if it were
        # the same. It never lapses: one running subagent pinned this branch for
        # as long as the workflow ran, so on a fan-out -- the sessions most likely
        # to be holding a prompt -- a recognised prompt could not surface at all.
        # It now yields to one. An unrecognised hook still waits for quiet, so a
        # notification type added upstream cannot invent a red band here.
        elif runtime_sessions.is_fresh(
            config,
            now,
            runtime_sessions.newest_plausible(config, now, last_event_sources),
            config.working_threshold_sec,
        ) or (subagents and not actionable_prompt):
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

        # One scan, read twice: the turn estimate and the failure run come out of
        # the same incremental state, and calling the scanner again would advance
        # its position past the records the second reading needs.
        scan = (
            runtime_turns.scan_turns(config, state, transcript, "claude")
            if (info and transcript)
            else None
        )
        s = runtime_sessions.base_session("claude", prefix, project)
        s.update(
            {
                "title": (info or {}).get("title"),
                # Line 1 above is the session's identity — the `ai-title`, fixed
                # before the second prompt on 200 of 204 long sessions — and this
                # is the line that says what it is doing now. Behind the same
                # guard as the analysis, so an unread row reports nothing rather
                # than something old.
                "instruction": (
                    claude_data.session_instruction(config, state, transcript)
                    if (info and transcript)
                    else None
                ),
                # The session's own model, from the non-sidechain half of the
                # analysis: an inactive session is not analyzed at all and
                # publishes None, which is "not read" and not "no model".
                "model": (info or {}).get("model"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": session_state,
                "state_detail": state_detail,
                "blocked_since": blocked_since,
                "active": active,
                "last_activity": last_activity,
                # The parent transcript alone, deliberately excluded from the
                # subagent and task mtimes folded into `last_activity` above:
                # this is what tells a resumed turn from a background agent
                # writing while a permission prompt is still open (DRC-4097).
                #
                # The agent's own records, not the file's mtime, and the
                # difference is the whole point. A parked transcript still
                # receives `queue-operation` and `attachment` records when a
                # background task finishes, so mtime answers "did anything
                # write" when the reducer is asking "did the agent resume".
                # Read as mtime, one background task completing retired a live
                # question for the rest of its life: the row published
                # `working` while the session sat on an open gate, and the
                # Needs-you tile counted zero. A transcript with no assistant
                # record in its tail reports 0, which leaves the wait standing
                # — the safe direction, and the same one an unreported value
                # already takes in the reducer.
                "own_activity": (info or {}).get("last_assistant_ts") or 0,
                "started_at": runtime_turns.started_at(scan),
                # Subagent output lives in the children's own transcripts; fold
                # it in so the session's rate reflects all its work. Read from
                # `analyses` rather than re-analyzing: both layouts are in there
                # already, and a second pass over the same file per refresh is
                # the cost this map exists to avoid.
                "rate_per_min": runtime_sessions.rate_from(info, now, config)
                + sum(
                    runtime_sessions.rate_from(analyses[path], now, config)
                    for path, mtime in child_files
                    if runtime_sessions.is_fresh(config, now, mtime, config.rate_window_sec)
                ),
                "session_output_tokens": (scan.get("session_output_tokens") if scan else None),
                "turn_output_tokens": scan.get("turn_output_tokens") if scan else None,
                "total": total,
                "done": done,
                "open": open_count,
                "progress_pct": round(done * 100 / total) if total else 0,
                "eta_h": runtime_sessions.fmt_duration(eta_sec) if eta_sec else None,
                "turn": runtime_turns.turn_progress(scan, session_state, now, config),
                "loop": runtime_turns.loop_signal(scan, config),
                "subagents": [
                    {
                        "name": a["label"],
                        "model": a["model"],
                        "started_at": a["started_at"],
                    }
                    for a in subagents
                ],
                "tasks": tasks,
                "spacedock": session_spacedock(
                    config, state, transcript, subagents, now, window_hours * 3600
                ),
            }
        )
        out.append(s)
    return out
