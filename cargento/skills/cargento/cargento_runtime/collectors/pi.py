"""Pi session collection, including its append-only branch scanner."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from cargento_runtime import io as runtime_io
from cargento_runtime import records, sessions, transcripts, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState

# Pi stores an append-only tree rather than a linear transcript. The scanners
# below follow the path from the newest entry back to parentId: null, so
# sibling branches cannot report tools and tokens the agent abandoned.

_PI_NO_NAME = object()


def _projection(record: Any) -> dict[str, Any] | None:
    """The bounded subset of a Pi JSONL entry needed by the dashboard."""
    if not isinstance(record, dict):
        return None
    kind = record.get("type")
    entry_id = record.get("id")
    parent_id = record.get("parentId")
    if not isinstance(entry_id, str) or not entry_id:
        entry_id = None
    if not isinstance(parent_id, str):
        parent_id = None
    message = records.message_dict(record)
    role = message.get("role")
    prompt = None
    tool = None
    usage_source: Any = record.get("usage")
    if kind == "message":
        usage_source = message.get("usage")
        if role == "user":
            text = records.extract_text(message.get("content")).strip()
            prompt = text or None
        if role == "assistant":
            for block in records.as_list(message.get("content")):
                if not isinstance(block, dict) or block.get("type") != "toolCall":
                    continue
                tool_name = block.get("name")
                if isinstance(tool_name, str) and tool_name:
                    tool = tool_name
    output = records.as_dict(usage_source).get("output")
    usage = output if isinstance(output, (int, float)) and not isinstance(output, bool) else None
    name: Any = _PI_NO_NAME
    if kind == "session_info":
        value = record.get("name")
        name = value if isinstance(value, str) and value else None
    return {
        "id": entry_id,
        "parent_id": parent_id,
        "timestamp": records.parse_ts(record.get("timestamp") or "") or 0,
        "prompt": prompt,
        "usage": usage,
        "tool": tool,
        "name": name,
        "kind": kind,
    }


def _complete_end(config: RuntimeConfig, path: str, size: int) -> int:
    """End offset after the newest complete JSONL entry, or zero."""
    if not size:
        return 0
    try:
        with open(path, "rb") as source:
            pos = size
            while pos:
                read_size = min(config.reverse_chunk_bytes, pos)
                pos -= read_size
                source.seek(pos)
                chunk = source.read(read_size)
                if len(chunk) < read_size:
                    return 0
                newline = chunk.rfind(b"\n")
                if newline >= 0:
                    return pos + newline + 1
    except OSError:
        return 0
    return 0


def _latest_name(config: RuntimeConfig, path: str, end_pos: int) -> Any:
    """The newest global Pi session name, including an explicit clear."""
    for raw in runtime_io.reverse_lines(
        config,
        path,
        end_pos,
        contains=b'"session_info"',
    ):
        if not raw.startswith(b"{") or b'"session_info"' not in raw:
            continue
        try:
            projection = _projection(json.loads(raw))
        except ValueError:
            continue
        if projection is not None and projection["name"] is not _PI_NO_NAME:
            return projection["name"]
    return _PI_NO_NAME


def _scan_state(
    config: RuntimeConfig,
    path_entries: list[dict[str, Any]],
    path: str,
    end_pos: int,
) -> dict[str, Any]:
    """Build cache state only for a branch whose ancestry reaches root."""
    return {
        "pos": end_pos,
        "path": path_entries,
        "ids": {entry["id"]: index for index, entry in enumerate(path_entries)},
        "name": _latest_name(config, path, end_pos),
    }


def _last_complete_branch(
    config: RuntimeConfig,
    path: str,
    end_pos: int,
) -> list[dict[str, Any]]:
    """Find the newest root-connected path after the latest candidate breaks."""
    entries: dict[str, dict[str, Any]] = {}
    newest: list[dict[str, Any]] = []
    for raw in runtime_io.reverse_lines(config, path, end_pos):
        if not raw.startswith(b"{"):
            continue
        try:
            projection = _projection(json.loads(raw))
        except ValueError:
            continue
        if projection is None or projection["kind"] == "session":
            continue
        entry_id = projection["id"]
        if entry_id is None or entry_id in entries:
            continue
        entries[entry_id] = projection
        newest.append(projection)
    for leaf in newest:
        reverse_path = []
        entry = leaf
        seen = set()
        while entry["id"] not in seen:
            reverse_path.append(entry)
            seen.add(entry["id"])
            parent_id = entry["parent_id"]
            if parent_id is None:
                return list(reversed(reverse_path))
            parent = entries.get(parent_id)
            if parent is None:
                break
            entry = parent
    return []


def _rebuild(config: RuntimeConfig, path: str, end_pos: int) -> dict[str, Any]:
    """Reconstruct the live Pi branch newest-first without retaining payloads."""
    reverse_path: list[dict[str, Any]] = []
    wanted: str | None = None
    for raw in runtime_io.reverse_lines(config, path, end_pos):
        if not raw.startswith(b"{"):
            continue
        try:
            projection = _projection(json.loads(raw))
        except ValueError:
            continue
        if projection is None or projection["kind"] == "session":
            continue
        entry_id = projection["id"]
        if entry_id is None:
            continue
        if wanted is None or entry_id == wanted:
            reverse_path.append(projection)
            wanted = projection["parent_id"]
        else:
            continue
        if wanted is None:
            break
    if wanted is None and reverse_path:
        return _scan_state(config, list(reversed(reverse_path)), path, end_pos)
    return _scan_state(config, _last_complete_branch(config, path, end_pos), path, end_pos)


def _extend(scan: dict[str, Any], entry: dict[str, Any]) -> bool:
    """Add one complete Pi entry; false asks the caller to rebuild from disk."""
    if entry["name"] is not _PI_NO_NAME:
        scan["name"] = entry["name"]
    if entry["kind"] == "session" or entry["id"] is None:
        return True
    path_entries = scan["path"]
    if not path_entries:
        if entry["parent_id"] is not None:
            return False
        scan["path"] = [entry]
        scan["ids"] = {entry["id"]: 0}
        return True
    parent_id = entry["parent_id"]
    ids = scan["ids"]
    if parent_id == path_entries[-1]["id"]:
        path_entries.append(entry)
        ids[entry["id"]] = len(path_entries) - 1
        return True
    index = ids.get(parent_id)
    if index is None:
        return False
    scan["path"] = [*path_entries[: index + 1], entry]
    scan["ids"] = {item["id"]: i for i, item in enumerate(scan["path"])}
    return True


def _turn(config: RuntimeConfig, path_entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn state for Pi's active branch, using scan_turns' quiet-gap rule."""
    turn_start = prev_ts = None
    durations: list[float] = []
    for entry in path_entries:
        timestamp = entry["timestamp"]
        if not timestamp:
            continue
        if turn_start and prev_ts and timestamp - prev_ts > config.turn_gap_reset_sec:
            if prev_ts > turn_start:
                durations.append(prev_ts - turn_start)
            turn_start = timestamp
        if entry["prompt"]:
            if turn_start and prev_ts and prev_ts > turn_start:
                durations.append(prev_ts - turn_start)
            turn_start = timestamp
        prev_ts = timestamp
    return {"turn_start": turn_start, "durations": durations[-50:]}


def _info(config: RuntimeConfig, scan: dict[str, Any]) -> dict[str, Any] | None:
    """Dashboard analyzer output from the compact active-branch projection."""
    path_entries = scan["path"]
    if not path_entries:
        return None
    prompts = [entry["prompt"] for entry in path_entries if entry["prompt"]]
    name = scan["name"]
    title = (
        name
        if isinstance(name, str) and name
        else (transcripts.prompt_title(config, prompts[0]) if prompts else None)
    )
    usage_events = [
        (entry["timestamp"], entry["usage"])
        for entry in path_entries
        if entry["timestamp"] and entry["usage"] is not None
    ]
    tools = [entry["tool"] for entry in path_entries if entry["tool"]]
    return {
        "title": title,
        "last_prompt": prompts[-1] if prompts else None,
        "usage_events": usage_events,
        "last_tool": tools[-1] if tools else None,
        "last_event_ts": max((entry["timestamp"] for entry in path_entries), default=0),
        "turn": _turn(config, path_entries),
    }


def scan_pi_session(
    config: RuntimeConfig,
    state: RuntimeState,
    path: str,
) -> dict[str, Any] | None:
    """Scan Pi's live branch incrementally, retaining only compact entries."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    with state.scanner_lock:
        scan = state.pi_scan.get(path)
        if scan is None or scan["pos"] > size:
            if len(state.pi_scan) >= config.max_cache_entries:
                state.pi_scan.pop(next(iter(state.pi_scan)))
            scan = _rebuild(config, path, _complete_end(config, path, size))
            state.pi_scan[path] = scan
            return _info(config, scan)
        if size == scan["pos"]:
            return _info(config, scan)
        try:
            with open(path, "rb") as source:
                source.seek(scan["pos"])
                data = source.read()
        except OSError:
            return _info(config, scan)
        end = data.rfind(b"\n")
        if end < 0:
            return _info(config, scan)
        new_pos = scan["pos"] + end + 1
        for raw in data[:end].split(b"\n"):
            if not raw.startswith(b"{"):
                continue
            try:
                projection = _projection(json.loads(raw))
            except ValueError:
                continue
            if projection is not None and not _extend(scan, projection):
                scan = _rebuild(config, path, new_pos)
                state.pi_scan[path] = scan
                return _info(config, scan)
        scan["pos"] = new_pos
        return _info(config, scan)


def _session_paths(config: RuntimeConfig) -> set[str]:
    """Pi writes flat and one-level-nested stores; both are supported."""
    paths = set(runtime_io.glob_stores(config, "pi.sessions", "*.jsonl"))
    paths.update(runtime_io.glob_stores(config, "pi.sessions", "*", "*.jsonl"))
    return paths


def discover(config: RuntimeConfig, state: RuntimeState) -> bool:
    """Whether Pi has at least one JSONL file with a valid session header.

    Takes state because reading that header shares the bounded first-line
    metadata cache with collection.
    """
    for path in _session_paths(config):
        try:
            if transcripts.pi_meta(config, state, path).get("session_id"):
                return True
        except (OSError, ValueError):
            continue
    return False


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    """Collect Pi's independent JSONL sessions from flat and nested stores."""
    found: dict[str, tuple[float, str, dict[str, Any]]] = {}
    for path in _session_paths(config):
        try:
            mtime = os.path.getmtime(path)
            meta = transcripts.pi_meta(config, state, path)
        except (OSError, ValueError):
            continue
        sid = meta.get("session_id")
        if not isinstance(sid, str) or not sid:
            continue
        if sid not in found or mtime > found[sid][0]:
            found[sid] = (mtime, path, meta)

    out: list[Session] = []
    for sid, (mtime, path, meta) in found.items():
        try:
            info = scan_pi_session(config, state, path)
        except (OSError, ValueError):
            continue
        last_event_ts = info["last_event_ts"] if info else 0
        last_activity = sessions.newest_plausible(config, now, (last_event_ts, mtime))
        active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        session_state, state_detail = "idle", "awaiting your message"
        if sessions.is_fresh(config, now, last_activity, config.working_threshold_sec):
            session_state = "working"
            state_detail = sessions.working_detail(info, [])
        project = sessions.project_from_cwd(config, meta.get("cwd") or "") or "pi"
        session = sessions.base_session("pi", sid, project)
        session.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": sessions.rate_from(info, now, config),
                "turn": turns.turn_progress((info or {}).get("turn"), session_state, now, config),
            }
        )
        out.append(session)
    return out
