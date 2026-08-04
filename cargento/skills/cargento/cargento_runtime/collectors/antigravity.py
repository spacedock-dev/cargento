"""Antigravity CLI (``agy``) collection.

Antigravity keeps one SQLite store per conversation under the Gemini home,
plus a workspace cache and CLI logs. Conversation content is never decoded:
discovery and state come from store mtime and from protobuf metadata fields,
which is why this collector still reports on a build without ``sqlite3``.

Split from ``gemini.py`` when Gemini CLI was retired. The two shared a
registry row while both were Google's current surface; see
``docs/design-harness-registry.md``.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from typing import TYPE_CHECKING, Any

from cargento_runtime import config as runtime_config
from cargento_runtime import io as runtime_io
from cargento_runtime import records, sessions, turns

if TYPE_CHECKING:
    from collections.abc import Iterator

    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState


def _root(config: RuntimeConfig) -> str:
    return runtime_config.primary_store(config, "antigravity.root")


def _conversations_dir(config: RuntimeConfig) -> str:
    return os.path.join(_root(config), "conversations")


def _log_dir(config: RuntimeConfig) -> str:
    return os.path.join(_root(config), "log")


def _last_conversations_path(config: RuntimeConfig) -> str:
    return os.path.join(_root(config), "cache", "last_conversations.json")


def _log_head_lines_from(
    config: runtime_config.RuntimeConfig,
    path: str,
) -> list[str]:
    try:
        return (
            runtime_io.read_prefix_bytes(
                path,
                max_bytes=config.antigravity_log_head_bytes,
            )
            .decode("utf-8", "replace")
            .splitlines()
        )
    except OSError:
        return []


def _log_head_lines(config: RuntimeConfig, path: str) -> list[str]:
    """Read the bounded identity-bearing beginning of an Antigravity CLI log."""
    return _log_head_lines_from(config, path)


def _log_lines(config: RuntimeConfig, path: str) -> list[str]:
    """Read the beginning and bounded tail of an Antigravity CLI log.

    Workspace and conversation identity are written near the beginning,
    while the latest user prompt is near the tail. Long-running logs can
    exceed ``tail_bytes``, so reading only one side loses one of those.
    """
    return _log_head_lines_from(config, path) + runtime_io.read_tail(config, path)


def _session_metadata(
    config: RuntimeConfig,
    now: float,
    window_hours: float,
    show_all: bool,
) -> dict[str, dict[str, Any]]:
    """Best-effort conversation metadata from Antigravity's public-facing
    CLI logs and last-conversation cache.

    Conversation payloads are protobuf blobs inside per-session SQLite
    stores. The logs already expose the stable boundaries needed here:
    workspace, conversation id, and human prompt. Broken or rotated files are
    skipped so one incomplete Antigravity run cannot break the dashboard.
    """
    found: dict[str, dict[str, Any]] = {}
    cached_cwds: dict[str, str] = {}
    try:
        with open(_last_conversations_path(config), encoding="utf-8") as source:
            recent = json.load(source)
        if isinstance(recent, dict):
            for workspace, sid in recent.items():
                if (
                    isinstance(workspace, str)
                    and isinstance(sid, str)
                    and sessions.project_from_cwd(config, workspace)
                ):
                    found.setdefault(sid, {})["cwd"] = workspace
                    cached_cwds[sid] = workspace
    except (OSError, ValueError, TypeError, RecursionError):
        pass

    all_logs = runtime_io.glob_under(_log_dir(config), "cli-*.log")
    try:
        all_logs.sort(key=os.path.getmtime)
    except OSError:
        all_logs.sort()
    logs = all_logs
    if not show_all:
        recent_logs: list[str] = []
        for path in logs:
            try:
                if sessions.is_fresh(config, now, os.path.getmtime(path), window_hours * 3600):
                    recent_logs.append(path)
            except OSError:
                continue
        logs = recent_logs

    workspace_re = re.compile(r"workspaceDirs=\[(.*?)\]\s+appDataDir=")
    session_re = re.compile(r"(?:Created|Streaming) conversation ([0-9a-fA-F-]{36})")
    forward_re = re.compile(r"Forwarding user message to conversation ([0-9a-fA-F-]{36})")
    prompt_marker = "HandleUserInput called with text: "
    workspace_primaries: dict[str, str] = {}
    events: list[tuple[str, str | None, str | None]] = []

    for path in logs:
        workspace = None
        pending_prompt = None
        for line in _log_lines(config, path):
            match = workspace_re.search(line)
            if match:
                workspace = match.group(1).strip() or None
                continue
            match = session_re.search(line)
            if match:
                sid = match.group(1)
                if workspace and sid in cached_cwds:
                    workspace_primaries[workspace] = cached_cwds[sid]
                events.append((sid, workspace, None))
                continue
            if prompt_marker in line:
                raw = line.split(prompt_marker, 1)[1].strip()
                try:
                    decoded = json.loads(raw)
                    pending_prompt = decoded if isinstance(decoded, str) else raw
                except (ValueError, TypeError, RecursionError):
                    pending_prompt = raw.strip('"')
                pending_prompt = records.safe_text(pending_prompt, 2000)
                continue
            match = forward_re.search(line)
            if match:
                sid = match.group(1)
                if workspace and sid in cached_cwds:
                    workspace_primaries[workspace] = cached_cwds[sid]
                prompt = None
                if pending_prompt:
                    prompt = pending_prompt
                    pending_prompt = None
                events.append((sid, workspace, prompt))

    # last_conversations.json names only the newest session for a workspace.
    # That anchor session can be quiet while a sibling using the same
    # multi-folder context remains active. Recover only its identity from
    # bounded stale-log heads; stale prompts and session events stay excluded.
    missing_contexts = {
        workspace
        for _, workspace, _ in events
        if workspace and workspace not in workspace_primaries
    }
    if missing_contexts and cached_cwds and not show_all:
        recent_paths = set(logs)
        for path in reversed(all_logs):
            if path in recent_paths:
                continue
            workspace = None
            for line in _log_head_lines(config, path):
                match = workspace_re.search(line)
                if match:
                    workspace = match.group(1).strip() or None
                    continue
                match = session_re.search(line) or forward_re.search(line)
                if not match:
                    continue
                sid = match.group(1)
                if workspace is not None and workspace in missing_contexts and sid in cached_cwds:
                    workspace_primaries[workspace] = cached_cwds[sid]
                    missing_contexts.remove(workspace)
            if not missing_contexts:
                break

    for sid, workspace, prompt in events:
        session = found.setdefault(sid, {})
        if workspace:
            session["cwd"] = workspace_primaries.get(workspace, workspace)
        if prompt:
            session["last_prompt"] = prompt
    return found


def _wal_has_data(path: str) -> bool:
    """Whether an Antigravity WAL has content beyond an empty sidecar."""
    with contextlib.suppress(OSError):
        return os.path.getsize(path + "-wal") > 0
    return False


def _store_mtime(config: RuntimeConfig, path: str, now: float) -> float:
    """Newest plausible durable activity marker for a conversation store."""
    mtimes: list[float] = []
    with contextlib.suppress(OSError):
        mtimes.append(os.path.getmtime(path))
    if _wal_has_data(path):
        with contextlib.suppress(OSError):
            mtimes.append(os.path.getmtime(path + "-wal"))
    return sessions.newest_plausible(config, now, mtimes)


def protobuf_fields(payload: Any) -> Iterator[tuple[int, int, Any]]:
    """Yield ``(field_number, wire_type, value)`` from a protobuf message.

    Antigravity persists step metadata as protobuf without shipping Python
    descriptors. This bounded wire reader extracts only the stable scalar and
    length-delimited envelope fields needed by the dashboard. Malformed
    messages raise ``ValueError`` and non-buffer payloads raise ``TypeError``;
    callers skip both.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("protobuf payload must be bytes-like")
    payload = bytes(payload)
    offset = 0

    def read_varint(position: int) -> tuple[int, int]:
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(payload):
                raise ValueError("truncated protobuf varint")
            byte = payload[position]
            position += 1
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                return value, position
        raise ValueError("oversized protobuf varint")

    value: Any  # varint int or a length-delimited/fixed-width bytes slice
    while offset < len(payload):
        key, offset = read_varint(offset)
        number, wire_type = key >> 3, key & 7
        if not number:
            raise ValueError("invalid protobuf field")
        if wire_type == 0:
            value, offset = read_varint(offset)
        elif wire_type == 1:
            if offset + 8 > len(payload):
                raise ValueError("truncated protobuf fixed64")
            value = payload[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            size, offset = read_varint(offset)
            end = offset + size
            if end > len(payload):
                raise ValueError("truncated protobuf bytes")
            value = payload[offset:end]
            offset = end
        elif wire_type == 5:
            if offset + 4 > len(payload):
                raise ValueError("truncated protobuf fixed32")
            value = payload[offset : offset + 4]
            offset += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
        yield number, wire_type, value


def protobuf_first(payload: Any, number: int, wire_type: int) -> Any:
    try:
        for field, wire, value in protobuf_fields(payload):
            if field == number and wire == wire_type:
                return value
    except (ValueError, TypeError):
        pass
    return None


def protobuf_timestamp(payload: Any) -> float:
    seconds = protobuf_first(payload, 1, 0)
    nanos = protobuf_first(payload, 2, 0) or 0
    if not seconds:
        return 0
    return float(seconds + nanos / 1_000_000_000)


def _step_info(metadata: Any) -> dict[str, Any]:
    """Timestamp, output usage, and tool labels from a step metadata blob."""
    started = protobuf_first(metadata, 1, 2)
    usage = protobuf_first(metadata, 9, 2)
    summary = protobuf_first(metadata, 30, 2)
    action = protobuf_first(metadata, 31, 2)
    output_tokens = protobuf_first(usage, 3, 0) if usage else 0

    def text(value: Any) -> str:
        if not value:
            return ""
        return records.safe_text(value.decode("utf-8", "replace"), 140)

    return {
        "epoch": protobuf_timestamp(started) if started else 0,
        "output_tokens": output_tokens or 0,
        "tool_summary": text(summary),
        "tool_action": text(action),
    }


def _step_activity(
    config: RuntimeConfig, state: RuntimeState, path: str, now: float
) -> dict[str, Any]:
    """Read live rate, turn boundaries, and current action from a store.

    Prefer a plain ``mode=ro`` connection: it sees committed WAL frames, so
    activity from a live Antigravity writer is current. Some stores refuse
    plain read-only opens (e.g. WAL recovery is needed but the reader cannot
    create shm/journal files); for those, fall back to ``immutable=1``, which
    never contends with the writer but may lag until checkpoint. A transient
    or incompatible store simply returns an empty activity snapshot.
    """
    result: dict[str, Any] = {
        "rate_per_min": 0,
        "turns": None,
        "last_tool_action": "",
    }
    if not runtime_io.sqlite_available():
        return result
    query = "SELECT step_type, metadata FROM steps ORDER BY idx DESC LIMIT ?"
    rows = None
    read_error: BaseException | None = None
    for uri in (
        runtime_io.sqlite_ro_uri(path),
        runtime_io.sqlite_ro_uri(path, immutable=True),
    ):
        try:
            con = runtime_io.sqlite_module.connect(uri, uri=True, timeout=0.2)
        except runtime_io.sqlite_module.Error as exc:
            read_error = exc
            continue
        try:
            rows = con.execute(query, (config.sql_message_limit,)).fetchall()
            break
        except runtime_io.sqlite_module.Error as exc:
            read_error = exc
            continue
        finally:
            con.close()
    if rows is None:
        if read_error:
            runtime_io.record_store_error(state, path, read_error)
        return result

    events = []
    usage_events = []
    last_prompt = 0
    latest_action = (0, "")
    for step_type, metadata in reversed(rows):
        info = _step_info(metadata)
        epoch = info["epoch"]
        if not epoch:
            continue
        is_prompt = step_type == 14
        events.append((epoch, is_prompt))
        if is_prompt:
            last_prompt = epoch
            latest_action = (0, "")
        if step_type == 15 and info["output_tokens"]:
            usage_events.append((epoch, info["output_tokens"]))
        action = info["tool_action"] or info["tool_summary"]
        if action and epoch >= last_prompt:
            latest_action = (epoch, action)

    recent = sum(
        tokens
        for epoch, tokens in usage_events
        if sessions.is_fresh(config, now, epoch, config.rate_window_sec)
    )
    result["rate_per_min"] = round(recent / (config.rate_window_sec / 60))
    result["turns"] = turns.turns_from_events(events) if events else None
    result["last_tool_action"] = latest_action[1]
    return result


def _session_info(
    _config: RuntimeConfig,
    state: RuntimeState,
    path: str,
    sid: str,
) -> dict[str, Any]:
    """Extract parent conversation ID and subagent label from an Antigravity store."""
    info: dict[str, Any] = {"parent_id": None, "subagent_label": None}
    if not runtime_io.sqlite_available():
        return info
    query = "SELECT data FROM trajectory_metadata_blob WHERE id='main'"

    def read_row(uri: str) -> tuple[bool, Any, BaseException | None]:
        try:
            con = runtime_io.sqlite_module.connect(uri, uri=True, timeout=0.2)
        except runtime_io.sqlite_module.Error as exc:
            return False, None, exc
        try:
            return True, con.execute(query).fetchone(), None
        except runtime_io.sqlite_module.Error as exc:
            return False, None, exc
        finally:
            con.close()

    readable, row, read_error = read_row(runtime_io.sqlite_ro_uri(path))
    if not readable and _wal_has_data(path):
        if read_error:
            runtime_io.record_store_error(state, path, read_error)
        return info
    if not readable:
        readable, row, fallback_error = read_row(runtime_io.sqlite_ro_uri(path, immutable=True))
        if _wal_has_data(path):
            if read_error:
                runtime_io.record_store_error(state, path, read_error)
            return info
        if not readable:
            if fallback_error:
                runtime_io.record_store_error(state, path, fallback_error)
            return info
    if not readable or not row or not row[0]:
        return info
    data = row[0]

    def text(value: Any) -> str | None:
        if not isinstance(value, (bytes, bytearray, memoryview)):
            return None
        with contextlib.suppress(UnicodeDecodeError):
            return bytes(value).decode("utf-8") or None
        return None

    p5 = text(protobuf_first(data, 5, 2))
    p6 = text(protobuf_first(data, 6, 2))
    parent_id = p5 or (p6 if p6 != sid else None)
    if parent_id:
        info["parent_id"] = parent_id
        f8 = protobuf_first(data, 8, 2)
        labels = (
            text(protobuf_first(f8, 2, 2)),
            text(protobuf_first(f8, 1, 2)),
        )
        info["subagent_label"] = next(
            (
                cleaned
                for label in labels
                if label
                for cleaned in (records.safe_text(label, 70).strip(),)
                if cleaned
            ),
            None,
        )
    return info


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    metadata = _session_metadata(config, now, window_hours, show_all)
    dbs = runtime_io.glob_under(_conversations_dir(config), "*.db")

    agents_by_parent: dict[str, list[tuple[str, str, float]]] = {}
    subagent_sids: set[str] = set()
    db_mtimes: dict[str, float] = {}
    db_paths: dict[str, str] = {}

    for db in dbs:
        sid = os.path.basename(db)[: -len(".db")]
        mtime = _store_mtime(config, db, now)
        if not mtime:
            continue
        db_mtimes[sid] = mtime
        db_paths[sid] = db

    pending = [
        sid
        for sid, mtime in db_mtimes.items()
        if show_all or sessions.is_fresh(config, now, mtime, window_hours * 3600)
    ]
    inspected: set[str] = set()
    while pending:
        sid = pending.pop()
        if sid in inspected:
            continue
        inspected.add(sid)
        info = _session_info(config, state, db_paths[sid], sid)
        parent = info.get("parent_id")
        if parent and parent != sid:
            subagent_sids.add(sid)
            label = info.get("subagent_label") or ("subagent " + sid[:8])
            agents_by_parent.setdefault(parent, []).append((sid, label, db_mtimes[sid]))
            if parent in db_paths:
                pending.append(parent)

    def descendants(parent_sid: str) -> list[tuple[str, str, float]]:
        agents: list[tuple[str, str, float]] = []
        pending_agents = list(agents_by_parent.get(parent_sid, []))
        seen: set[str] = set()
        while pending_agents:
            agent_sid, label, mtime = pending_agents.pop()
            if agent_sid in seen or agent_sid == parent_sid:
                continue
            seen.add(agent_sid)
            agents.append((agent_sid, label, mtime))
            pending_agents.extend(agents_by_parent.get(agent_sid, []))
        return agents

    out: list[dict[str, Any]] = []
    for db in dbs:
        sid = os.path.basename(db)[: -len(".db")]
        if sid in subagent_sids:
            continue
        session_mtime = db_mtimes.get(sid)
        if not session_mtime:
            continue
        agents = sorted(descendants(sid), key=lambda a: -a[2])
        activity_sources = (session_mtime, *(mtime for _, _, mtime in agents))
        last_activity = sessions.newest_plausible(config, now, activity_sources)
        active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        activity: dict[str, Any] = (
            _step_activity(config, state, db, now)
            if active
            else {"rate_per_min": 0, "turns": None, "last_tool_action": ""}
        )
        if active:
            activity["rate_per_min"] += sum(
                _step_activity(config, state, db_paths[agent_sid], now)["rate_per_min"]
                for agent_sid, _, agent_mtime in agents
                if sessions.is_fresh(config, now, agent_mtime, config.rate_window_sec)
            )
        subagents = [
            label
            for _, label, agent_mtime in agents
            if sessions.is_fresh(config, now, agent_mtime, config.working_threshold_sec)
        ]
        session_state, state_detail = "idle", "awaiting your message"
        if sessions.is_fresh(config, now, last_activity, config.working_threshold_sec):
            session_state = "working"
            state_detail = (
                sessions.working_detail(None, subagents)
                if subagents
                else activity["last_tool_action"] or sessions.working_detail(None, [])
            )

        meta = metadata.get(sid) or {}
        prompt = str(meta.get("last_prompt") or "").strip()
        cwd = str(meta.get("cwd") or "").strip()
        project = sessions.project_from_cwd(config, cwd) or "antigravity"
        session = sessions.base_session("antigravity", sid, project)
        session.update(
            {
                "title": prompt.split("\n")[0][:80] or None,
                "last_prompt": prompt[:140],
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": activity["rate_per_min"],
                "turn": turns.turn_progress(activity["turns"], session_state, now, config),
                "subagents": subagents,
            }
        )
        out.append(session)
    return out


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether Antigravity has written at least one conversation store."""
    return bool(runtime_io.glob_under(_conversations_dir(config), "*.db"))
