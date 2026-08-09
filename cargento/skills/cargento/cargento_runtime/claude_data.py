"""Claude transcript facts and agent classification shared below the collector.

Spacedock, notifications and the Claude collector all read these, so they sit
below all three rather than inside any one of them.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
from typing import TYPE_CHECKING, Any

from cargento_runtime import config as runtime_config
from cargento_runtime import io as runtime_io
from cargento_runtime import records, transcripts
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime import state as runtime_state

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.state import RuntimeState

# Tools that mean Claude is blocked on the human, not just running long.
INPUT_TOOLS = {"AskUserQuestion", "ExitPlanMode"}

# Claude's own sentinel for an assistant record it generated locally, without
# the request ever reaching the API: a cancellation notice, an error banner, a
# tool-limit message. It is not a model, and it is common — one top-level
# transcript in five carries it as its newest assistant record, and many carry
# nothing else.
SYNTHETIC_MODEL = "<synthetic>"


def model_reported(value: Any) -> str | None:
    """The model an assistant record names, or None when it names none.

    `SYNTHETIC_MODEL` is rejected **by value**, never by the `isApiErrorMessage`
    flag that sits beside it on the same record. That flag is falsy on some
    synthetic records, so a flag gate publishes the sentinel as though it were a
    measurement — and "<synthetic>" on a session card is indistinguishable from a
    real model name to the person reading it. When the sentinel is all a
    transcript has, the honest answer is that no model was reported.

    Bounded here rather than at the caller because this is the only door: the
    value is untrusted vendor text on its way to the DOM.
    """
    if not isinstance(value, str) or value.strip() in ("", SYNTHETIC_MODEL):
        return None
    return records.safe_text(value, runtime_sessions.MODEL_CAP_CHARS).strip() or None


def session_title(config: RuntimeConfig, state: RuntimeState, path: str) -> str | None:
    """Newest generated Claude title, falling back to the first user prompt.

    ``ai-title`` records can be older than the bounded activity tail, so walk
    the file backward to find the newest one. The cache is invalidated whenever
    the transcript's size or mtime changes because Claude repeats title records
    as a session grows.
    """
    try:
        stat = os.stat(path)
    except OSError:
        return None
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with state.cache_lock:
        cached = state.claude_title_cache.get(path)
    if cached is not None and cached[:2] == cache_key:
        return cached[2]

    title = None
    # The chunk filter does the heavy lifting; the per-line test below only
    # re-checks the few lines inside a chunk that had a hit.
    for raw in runtime_io.reverse_lines(config, path, contains=b'"aiTitle"'):
        if b'"aiTitle"' not in raw:
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        value = record.get("aiTitle")
        if record.get("type") == "ai-title" and isinstance(value, str) and value:
            title = value
            break

    if title is None:
        try:
            with open(path, encoding="utf-8", errors="replace") as source:
                for line in source:
                    if not line.startswith("{"):
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    signal = records._turn_signal(record, "claude")  # noqa: SLF001
                    if not signal or signal[0] != "prompt":
                        continue
                    prompt = records.extract_text(
                        records.message_dict(record).get("content")
                    ).strip()
                    title = transcripts.prompt_title(config, prompt)
                    break
        except OSError:
            pass

    with state.cache_lock:
        runtime_state.bounded_put(
            state.claude_title_cache, path, (*cache_key, title), limit=config.max_cache_entries
        )
    return title


def last_user_event(config: RuntimeConfig, state: RuntimeState, path: str) -> str | None:
    """Identity of the newest user record, independent of record timestamps."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with state.cache_lock:
        cached = state.claude_user_event_cache.get(path)
    if cached is not None and cached[:2] == cache_key:
        return cached[2]

    marker = None
    # Superset filter: a user record must contain the literal "user".
    for raw in runtime_io.reverse_lines(config, path, contains=b'"user"'):
        if not raw.startswith(b"{") or b'"user"' not in raw:
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("type") != "user":
            continue
        uuid = record.get("uuid")
        marker = (
            uuid
            if isinstance(uuid, str) and uuid
            else hashlib.blake2b(raw, digest_size=16).hexdigest()
        )
        break

    with state.cache_lock:
        runtime_state.bounded_put(
            state.claude_user_event_cache,
            path,
            (*cache_key, marker),
            limit=config.max_cache_entries,
        )
    return marker


def analyze_transcript(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
    """Claude Code transcript tail.

    `model` and `model_sidechain` are the two halves of one reading, split on the
    `isSidechain` flag, because that flag **inverts** between a session and its
    subagents. A top-level transcript's own turns are not sidechains, so its model
    lands in `model`; a subagent writes its own transcript and every assistant
    record in it is flagged as a sidechain, so its model lands in
    `model_sidechain`. A caller holding a child transcript therefore reads
    `model_sidechain or model` — see `collectors.claude.child_model`.

    Newest wins for both: the last assistant record in the tail is the model the
    session is on now. A mid-session switch is real and rare (a plan change), and
    a transcript does not carry stray background models to be confused with one.
    Not cached on session identity for the same reason: the value is mutable
    while the session runs.
    """
    info: dict[str, Any] = {
        "title": session_title(config, state, path),
        "last_prompt": None,
        "model": None,
        "model_sidechain": None,
        "usage_events": [],  # (epoch, output_tokens)
        "pending_input_tool": None,  # {"name", "ts"} awaiting the human
        "last_tool": None,
        "last_event_ts": 0,
        # Newest record the *agent* wrote, which is not the same as the newest
        # record in the file. Bookkeeping records land in a parked transcript
        # from causes that are not the agent resuming, so a wait guard that
        # reads "has this session moved on" has to read this and not the mtime.
        "last_assistant_ts": 0,
        "last_user_event": last_user_event(config, state, path),
    }
    pending: dict[Any, Any] = {}  # tool_use id -> {"name", "ts"} for INPUT_TOOLS only
    for line in runtime_io.read_tail(config, path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        ep = records.parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        if t == "last-prompt":
            info["last_prompt"] = d.get("lastPrompt")
        elif t == "assistant":
            if ep:
                info["last_assistant_ts"] = max(info["last_assistant_ts"], ep)
            msg = records.message_dict(d)
            model = model_reported(msg.get("model"))
            if model:
                # Last write wins, and a rejected value overwrites nothing: a
                # trailing synthetic error must not withdraw the model the turns
                # before it were measured on.
                info["model_sidechain" if d.get("isSidechain") else "model"] = model
            usage = records.as_dict(msg.get("usage"))
            if ep and usage.get("output_tokens"):
                info["usage_events"].append((ep, usage["output_tokens"]))
            for c in records.as_list(msg.get("content")):
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    info["last_tool"] = c.get("name")
                    if c.get("name") in INPUT_TOOLS:
                        pending[c.get("id")] = {"name": c.get("name"), "ts": ep}
        elif t == "user":
            for c in records.as_list(records.message_dict(d).get("content")):
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    pending.pop(c.get("tool_use_id"), None)
    if pending:
        info["pending_input_tool"] = max(pending.values(), key=lambda p: p["ts"] or 0)
    return info


def session_cwd(config: RuntimeConfig, state: RuntimeState, path: str) -> str:
    """Working directory recorded on the transcript head, ``""`` if absent.

    Claude is the one harness whose store does not hand a collector a cwd: the
    ``projects/`` directory name encodes the path with every separator replaced
    by ``-``, and that cannot be split back apart because a directory may
    legitimately contain ``-``. The records themselves carry the real path, so
    read it rather than guessing at the encoding.

    An absent cwd is not cached: a transcript head can be written before any
    record carries one, and the answer changes as soon as one does.
    """
    with state.cache_lock:
        hit = state.cwd_cache.get(path)
    if hit is not None:
        return hit
    cwd = ""
    try:
        lines = runtime_io.iter_bounded_text_lines(
            path,
            max_lines=config.claude_cwd_scan_lines,
            per_line_bytes=config.claude_cwd_line_bytes,
        )
        for line in lines:
            if '"cwd"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            value = d.get("cwd") if isinstance(d, dict) else None
            if isinstance(value, str) and value:
                cwd = value
                break
    except OSError:  # pragma: no cover - iterator handles filesystem failures
        return ""
    if cwd:
        with state.cache_lock:
            runtime_state.bounded_put(state.cwd_cache, path, cwd, limit=config.max_cache_entries)
    return cwd


def hook_user_event(
    config: RuntimeConfig,
    state: RuntimeState,
    path: str,
    prefix: str,
) -> tuple[bool, str | None]:
    """Return a safe transcript baseline for a Notification-hook payload."""
    try:
        real_path = os.path.realpath(path)
        projects_root = os.path.realpath(runtime_config.primary_store(config, "claude.projects"))
        inside_projects = os.path.commonpath((projects_root, real_path)) == projects_root
    except (OSError, ValueError):
        return (False, None)
    basename = os.path.basename(real_path)
    if not inside_projects or not basename.startswith(prefix) or not basename.endswith(".jsonl"):
        return (False, None)
    return (True, last_user_event(config, state, real_path))


def agent_identity(
    config: RuntimeConfig,
    state: RuntimeState,
    path: str,
) -> tuple[bool, str, str]:
    """Classify a top-level transcript: (is_subagent, agent_name, parent_prefix).

    Harness >= 2.x writes subagent transcripts as ordinary <uuid>.jsonl files
    in the project directory; their records carry ``agentName`` and
    ``teamName`` = "session-<parent 8-char prefix>". Older harnesses used
    <session>/subagents/agent-*.jsonl, still handled by
    load_claude_subagents().
    """
    with state.cache_lock:
        cached = state.agent_class_cache.get(path)
    if cached is not None:
        return cached
    name, parent = "", ""
    size = 0
    lines_seen = 0
    try:
        size = os.path.getsize(path)
        data = runtime_io.read_prefix_bytes(path, max_bytes=config.claude_agent_scan_bytes)
        lines = data.split(b"\n")
        if size > len(data) and data and not data.endswith(b"\n"):
            lines.pop()  # the byte prefix ended inside a JSON record
        for line in lines[: config.claude_agent_scan_lines]:
            if not line:
                continue
            lines_seen += 1
            if name and parent:
                break
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            agent_name = rec.get("agentName")
            if not name and isinstance(agent_name, str) and agent_name:
                name = agent_name
            team = rec.get("teamName")
            if not parent and isinstance(team, str) and team.startswith("session-"):
                parent = team[len("session-") :][:8]
    except OSError:
        return (False, "", "")
    result = (bool(parent), name, parent)
    # A complete subagent identity is conclusive; an incomplete result is only
    # trusted once the file has enough content that later records cannot change it.
    if (
        (parent and name)
        or lines_seen >= config.claude_agent_scan_lines
        or size >= config.claude_agent_cache_negative_min_bytes
    ):
        with state.cache_lock:
            runtime_state.bounded_put(
                state.agent_class_cache, path, result, limit=config.max_cache_entries
            )
    return result


def agent_setting(config: RuntimeConfig, state: RuntimeState, path: str) -> str:
    """The ``agentSetting`` a transcript declares in its head, else "".

    The launcher passes ``--agent spacedock:first-officer``, so the value is
    written at record index 0 or 1 — inside the same head bytes the subagent
    classifier already reads. Immutable per file once present.
    """
    with state.cache_lock:
        cached = state.spacedock_role_cache.get(path)
    if cached is not None:
        return cached
    setting = ""
    size = 0
    try:
        size = os.path.getsize(path)
        data = runtime_io.read_prefix_bytes(path, max_bytes=config.claude_agent_scan_bytes)
        lines = data.split(b"\n")
        if size > len(data) and data and not data.endswith(b"\n"):
            lines.pop()
        for line in lines[: config.claude_agent_scan_lines]:
            if not line or b"agentSetting" not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            value = record.get("agentSetting")
            if isinstance(value, str) and value:
                setting = value
                break
    except OSError:
        return ""
    if setting or size >= config.claude_agent_cache_negative_min_bytes:
        with state.cache_lock:
            runtime_state.bounded_put(
                state.spacedock_role_cache, path, setting, limit=config.max_cache_entries
            )
    return setting


def prefix_is_agent(config: RuntimeConfig, state: RuntimeState, prefix: str) -> bool:
    """True when the newest transcript for this 8-char prefix belongs to a
    subagent. Used to suppress popups for agent sessions."""
    newest, newest_mtime = None, 0.0
    for fp in runtime_io.glob_stores(
        config,
        "claude.projects",
        "*",
        glob.escape(prefix) + "*.jsonl",
    ):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        if mtime > newest_mtime:
            newest, newest_mtime = fp, mtime
    if not newest:
        return False
    return agent_identity(config, state, newest)[0]
