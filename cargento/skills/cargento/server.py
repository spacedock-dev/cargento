#!/usr/bin/env python3
"""Cargento: live coding-agent session activity across harnesses.

Stdlib-only local server. Supported harnesses (each shown only if its local
data is discovered): Claude Code, Codex, Gemini CLI / Antigravity CLI,
GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, Factory Droid. Serves a
summary UI at http://localhost:<port>/ and JSON at /api/data.

Waiting-on-you detection (Claude only):
- transcript tail shows a pending AskUserQuestion (tool_use with no
  tool_result yet) -> NEEDS INPUT, popup fired
- POST /api/notify (wired to Claude Code Notification + SessionEnd hooks)
  -> popup for idle prompts, NEEDS INPUT for actionable prompts, and clear
  standing hook state when the session exits
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import hashlib
import json
import mmap
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

HOME = os.path.expanduser("~")
DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")

# Per-harness data roots
TASKS_DIR = os.path.join(HOME, ".claude", "tasks")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
CODEX_SESSIONS_DIR = os.path.join(HOME, ".codex", "sessions")
GEMINI_TMP = os.path.join(HOME, ".gemini", "tmp")
ANTIGRAVITY_CLI_DIR = os.path.join(HOME, ".gemini", "antigravity-cli")
ANTIGRAVITY_CONVERSATIONS_DIR = os.path.join(ANTIGRAVITY_CLI_DIR, "conversations")
ANTIGRAVITY_LOG_DIR = os.path.join(ANTIGRAVITY_CLI_DIR, "log")
ANTIGRAVITY_LAST_CONVERSATIONS = os.path.join(
    ANTIGRAVITY_CLI_DIR, "cache", "last_conversations.json"
)
COPILOT_DIR = os.path.join(HOME, ".copilot")
OPENCODE_DATA = os.path.join(DATA_HOME, "opencode")
CURSOR_CHATS = os.path.join(HOME, ".cursor", "chats")
GOOSE_DB = os.path.join(DATA_HOME, "goose", "sessions", "sessions.db")
FACTORY_PROJECTS = os.path.join(HOME, ".factory", "projects")

RATE_WINDOW_SEC = 600  # usage rate is measured over the last 10 minutes
WORKING_THRESHOLD_SEC = 90  # activity newer than this = WORKING
# A transcript that writes nothing for this long mid-turn was waiting on a
# human (permission prompt, open question) or asleep — not generating. The
# turn clock re-anchors after such a gap so "elapsed" measures work, not
# waiting. Kept well above the longest common tool run.
TURN_GAP_RESET_SEC = 300
TAIL_BYTES = 400_000  # only the transcript tail is parsed per refresh
POPUP_COOLDOWN_SEC = 60  # per-session floor between macOS popups
GLOBAL_POPUP_COOLDOWN_SEC = 15  # floor across caller-controlled session ids
POPUP_REPEAT_SUPPRESS_SEC = 600  # identical message per session: one popup per window
LONG_TURN_WARN_SEC = 900  # warn when a request runs (or is estimated) this long
SQL_MSG_LIMIT = 400  # newest messages fetched per DB-backed session
MAX_CACHE_ENTRIES = 8192  # bound process-lifetime caches over long uptime
GEMINI_SEEN_ENTRIES = 2048  # bound per-transcript snapshot deduplication

HOME_PREFIX = HOME.replace("/", "-")

# Tools that mean Claude is blocked on the human, not just running long.
INPUT_TOOLS = {"AskUserQuestion", "ExitPlanMode"}
# Claude Code's documented Notification matcher values. ``idle_timeout`` is
# accepted as a compatibility alias, while current payloads use
# ``idle_prompt``. Unknown structured values remain actionable so a newly
# introduced prompt type does not silently disappear.
IDLE_NOTIFICATION_TYPES = {"idle_prompt", "idle_timeout"}
INFORMATIONAL_NOTIFICATION_TYPES = {
    "agent_completed",
    "auth_success",
    "elicitation_complete",
    "elicitation_response",
}
ACTIONABLE_NOTIFICATION_TYPES = {
    "agent_needs_input",
    "elicitation_dialog",
    "permission_prompt",
}
CLEARING_NOTIFICATION_TYPES = IDLE_NOTIFICATION_TYPES | {
    "agent_completed",
    "elicitation_complete",
    "elicitation_response",
}

_lock = threading.Lock()
# session prefix -> {"ts": epoch, "message": str, "user_event"?: str | None}
_hook_notifs: dict[str, dict[str, Any]] = {}
_last_popup: dict[str, float] = {}  # session prefix -> epoch
_last_popup_message: dict[str, tuple[str, float]] = {}  # prefix -> (message, epoch)
_last_state: dict[str, str] = {}  # session prefix -> state string (popup on transition)
_cache_lock = threading.Lock()


def bounded_put(cache: dict[Any, Any], key: Any, value: Any) -> None:
    """Set a bounded insertion-ordered cache entry.

    Callers must hold the lock that protects ``cache``.
    """
    if key not in cache and len(cache) >= MAX_CACHE_ENTRIES:
        cache.pop(next(iter(cache)))
    cache[key] = value


def notification_text(value: Any, limit: int) -> str:
    """Return argv-safe single-line notification text."""
    text = str(value or "").encode("utf-8", "replace").decode("utf-8")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return text[:limit]


def normalized_notification_type(value: Any) -> str:
    """Return a normalized structured notification type, if present."""
    return value.strip().lower() if isinstance(value, str) and value.strip() else ""


def notification_disposition(notification_type: Any, message: str) -> tuple[bool, bool]:
    """Return ``(needs_input, popup)`` for a Notification-hook payload.

    Structured Claude Code payloads are authoritative. Text matching remains
    only as a compatibility fallback for older hooks that omitted
    ``notification_type``.
    """
    kind = normalized_notification_type(notification_type)
    if kind in IDLE_NOTIFICATION_TYPES:
        return (False, True)
    if kind in INFORMATIONAL_NOTIFICATION_TYPES:
        return (False, False)
    if kind in ACTIONABLE_NOTIFICATION_TYPES:
        return (True, True)
    if kind:
        return (True, True)  # future/unknown structured prompt: fail visible
    idle_nudge = message.strip().lower().startswith("claude is waiting for your input")
    return (not idle_nudge, True)


def project_label(dirname: str) -> str:
    dirname = dirname.removeprefix(HOME_PREFIX)
    return dirname.lstrip("-") or "(home)"


def parse_ts(ts: Any) -> float | None:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return None


def parse_utc_sql(v: Any) -> float:
    """SQL TIMESTAMP text (e.g. goose datetime('now'): "YYYY-MM-DD HH:MM:SS",
    stored UTC without offset) -> epoch."""
    try:
        dt = datetime.fromisoformat(str(v).replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0


def norm_epoch(v: Any) -> float:
    """Numeric timestamp in unknown unit (s or ms) -> epoch seconds."""
    if not isinstance(v, (int, float)) or v <= 0:
        return 0
    return v / 1000 if v > 1e12 else v


def fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "–"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def read_tail(path: str) -> list[str]:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            truncated = False
            if size > TAIL_BYTES:
                # Only drop the first line when the seek actually lands
                # mid-record: if the byte before the window is a newline,
                # the window starts on a complete record.
                f.seek(size - TAIL_BYTES - 1)
                truncated = f.read(1) != b"\n"
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = data.split("\n")
    if truncated:
        lines = lines[1:]
    return lines


def extract_text(v: Any, depth: int = 0) -> str:
    """Best-effort text from harness message payloads whose exact shape
    varies (string, list of parts, nested dicts)."""
    if depth > 4 or v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        parts = (extract_text(x, depth + 1) for x in v)
        return " ".join(p for p in parts if p)[:2000]
    if isinstance(v, dict):
        for k in ("text", "content", "message", "prompt", "value"):
            if k in v:
                t = extract_text(v[k], depth + 1)
                if t:
                    return t
    return ""


def alnum(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


# ---------------------------------------------------------------------------
# First-line metadata cache (JSONL harnesses write immutable line-1 metadata)

_meta_cache: dict[str, dict[str, Any]] = {}  # path -> parsed metadata dict


def first_line_meta(path: str, parse: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """parse(first-line JSON dict) -> dict; cached per path. Not cached on
    read/parse failure so a partially written first line retries later."""
    with _cache_lock:
        m = _meta_cache.get(path)
    if m is not None:
        return m
    try:
        with open(path, "rb") as f:
            d = json.loads(f.readline(200_000))
    except (OSError, ValueError):
        return {}
    m = parse(d if isinstance(d, dict) else {})
    with _cache_lock:
        cached = _meta_cache.get(path)
        if cached is not None:
            return cached
        bounded_put(_meta_cache, path, m)
        return m


def codex_meta(path: str) -> dict[str, Any]:
    """Codex rollout line 1 (session_meta): identity, cwd, and whether the
    file is a subagent thread (thread_source == "subagent")."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        # Every field is untyped JSON from disk — one malformed rollout must
        # not AttributeError the whole Codex collector.
        p = d.get("payload")
        if not isinstance(p, dict):
            p = {}
        source = p.get("source") or {}
        subagent = source.get("subagent") if isinstance(source, dict) else {}
        spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else {}
        nickname = p.get("agent_nickname")
        agent_path = p.get("agent_path")
        label = (
            nickname
            if isinstance(nickname, str) and nickname
            else (
                agent_path.rsplit("/", 1)[-1]
                if isinstance(agent_path, str) and agent_path
                else None
            )
        )
        return {
            "session_id": p.get("session_id") or p.get("id"),
            "parent_session_id": (
                spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
            ),
            "cwd": p.get("cwd"),
            "subagent": p.get("thread_source") == "subagent",
            "agent_label": label or None,
        }

    return first_line_meta(path, parse)


def gemini_meta(path: str) -> dict[str, Any]:
    """Gemini chat recording line 1: sessionId, kind (main|subagent),
    directories (cwd list)."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        dirs = d.get("directories")
        return {
            "session_id": d.get("sessionId"),
            "kind": d.get("kind"),
            "cwd": dirs[0] if isinstance(dirs, list) and dirs else None,
        }

    return first_line_meta(path, parse)


def copilot_meta(path: str) -> dict[str, Any]:
    """Copilot events.jsonl line 1 is normally session.start with
    data.context.cwd."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        data = d.get("data") or {}
        ctx = data.get("context") or {}
        return (
            {"cwd": ctx.get("cwd") or data.get("cwd")} if d.get("type") == "session.start" else {}
        )

    return first_line_meta(path, parse)


def droid_meta(path: str) -> dict[str, Any]:
    """Droid transcript line 1 (session_start): id, session title, cwd."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        if d.get("type") != "session_start":
            return {}
        return {
            "session_id": d.get("id"),
            "title": d.get("sessionTitle") or d.get("title"),
            "cwd": d.get("cwd"),
        }

    return first_line_meta(path, parse)


# ---------------------------------------------------------------------------
# Transcript analyzers (tail pass -> title, prompt, usage, activity)


_claude_title_cache: dict[str, tuple[int, int, str | None]] = {}
_claude_user_event_cache: dict[str, tuple[int, int, str | None]] = {}


def claude_session_title(path: str) -> str | None:
    """Newest generated Claude title, falling back to the first user prompt.

    ``ai-title`` records can be older than the bounded activity tail, so find
    the newest one by searching the mmap backward. The cache is invalidated
    whenever the transcript's size or mtime changes because Claude repeats
    title records as a session grows.
    """
    try:
        stat = os.stat(path)
    except OSError:
        return None
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        cached = _claude_title_cache.get(path)
    if cached is not None and cached[:2] == cache_key:
        return cached[2]

    title = None
    try:
        with open(path, "rb") as source:
            if stat.st_size:
                with mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
                    pos = len(data)
                    while pos:
                        match = data.rfind(b'"aiTitle"', 0, pos)
                        if match < 0:
                            break
                        line_start = data.rfind(b"\n", 0, match) + 1
                        line_end = data.find(b"\n", match)
                        if line_end < 0:
                            line_end = len(data)
                        try:
                            record = json.loads(data[line_start:line_end])
                        except json.JSONDecodeError:
                            record = {}
                        value = record.get("aiTitle")
                        if record.get("type") == "ai-title" and isinstance(value, str) and value:
                            title = value
                            break
                        pos = match
    except (OSError, ValueError):
        pass

    if title is None:
        try:
            with open(path, encoding="utf-8", errors="replace") as source:
                for line in source:
                    if not line.startswith("{"):
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    signal = _turn_signal(record, "claude")
                    if not signal or signal[0] != "prompt":
                        continue
                    prompt = extract_text((record.get("message") or {}).get("content")).strip()
                    title = prompt.split("\n")[0][:80] or None
                    break
        except OSError:
            pass

    with _cache_lock:
        bounded_put(_claude_title_cache, path, (*cache_key, title))
    return title


def claude_last_user_event(path: str) -> str | None:
    """Identity of the newest user record, independent of record timestamps."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        cached = _claude_user_event_cache.get(path)
    if cached is not None and cached[:2] == cache_key:
        return cached[2]

    marker = None
    try:
        with open(path, "rb") as source:
            if stat.st_size:
                with mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
                    line_end = len(data)
                    while line_end:
                        if data[line_end - 1 : line_end] == b"\n":
                            line_end -= 1
                        line_start = data.rfind(b"\n", 0, line_end) + 1
                        raw = data[line_start:line_end]
                        line_end = line_start
                        if not raw.startswith(b"{"):
                            continue
                        try:
                            record = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if record.get("type") != "user":
                            continue
                        uuid = record.get("uuid")
                        marker = (
                            uuid
                            if isinstance(uuid, str) and uuid
                            else hashlib.blake2b(raw, digest_size=16).hexdigest()
                        )
                        break
    except (OSError, ValueError):
        pass

    with _cache_lock:
        bounded_put(_claude_user_event_cache, path, (*cache_key, marker))
    return marker


def analyze_transcript(path: str) -> dict[str, Any]:
    """Claude Code transcript tail."""
    info: dict[str, Any] = {
        "title": claude_session_title(path),
        "last_prompt": None,
        "usage_events": [],  # (epoch, output_tokens)
        "pending_input_tool": None,  # {"name", "ts"} awaiting the human
        "last_tool": None,
        "last_event_ts": 0,
        "last_user_event": claude_last_user_event(path),
    }
    pending: dict[Any, Any] = {}  # tool_use id -> {"name", "ts"} for INPUT_TOOLS only
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        ep = parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        if t == "last-prompt":
            info["last_prompt"] = d.get("lastPrompt")
        elif t == "assistant":
            msg = d.get("message") or {}
            usage = msg.get("usage") or {}
            if ep and usage.get("output_tokens"):
                info["usage_events"].append((ep, usage["output_tokens"]))
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    info["last_tool"] = c.get("name")
                    if c.get("name") in INPUT_TOOLS:
                        pending[c.get("id")] = {"name": c.get("name"), "ts": ep}
        elif t == "user":
            for c in (d.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    pending.pop(c.get("tool_use_id"), None)
    if pending:
        info["pending_input_tool"] = max(pending.values(), key=lambda p: p["ts"] or 0)
    return info


def claude_hook_user_event(path: str, prefix: str) -> tuple[bool, str | None]:
    """Return a safe transcript baseline for a Notification-hook payload."""
    try:
        real_path = os.path.realpath(path)
        projects_root = os.path.realpath(PROJECTS_DIR)
        inside_projects = os.path.commonpath((projects_root, real_path)) == projects_root
    except (OSError, ValueError):
        return (False, None)
    basename = os.path.basename(real_path)
    if not inside_projects or not basename.startswith(prefix) or not basename.endswith(".jsonl"):
        return (False, None)
    return (True, claude_last_user_event(real_path))


def analyze_codex_transcript(path: str) -> dict[str, Any]:
    """Codex rollout tail: user_message (prompt/title), token_count (usage),
    tool calls. Turn spans come from scan_turns; cwd/subagents from meta."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
    }
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        t = d.get("type")
        p = d.get("payload") or {}
        if t == "event_msg":
            pt = p.get("type")
            if pt == "user_message":
                msg = (p.get("message") or "").strip()
                info["last_prompt"] = msg
                info["title"] = msg.split("\n")[0][:80] or None
            elif pt == "token_count":
                out = (((p.get("info") or {}).get("last_token_usage")) or {}).get("output_tokens")
                if ep and out:
                    info["usage_events"].append((ep, out))
        elif t == "response_item" and p.get("type") in ("function_call", "custom_tool_call"):
            info["last_tool"] = p.get("name")
    return info


def record_fingerprint(record: Any) -> bytes:
    """Stable bounded-size identity for repeated transcript records."""
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8", "replace"
    )
    return hashlib.blake2b(raw, digest_size=16).digest()


def gemini_records(record: Any) -> tuple[Any, ...]:
    """Expand a Gemini control record into its contained messages."""
    snapshot = record.get("$set")
    messages = snapshot.get("messages") if isinstance(snapshot, dict) else None
    if isinstance(messages, list):
        return tuple(message for message in messages if isinstance(message, dict))
    return (record,)


def incremental_gemini_records(record: Any, state: dict[str, Any]) -> tuple[Any, ...]:
    """Return only messages added since the prior cumulative $set snapshot."""
    snapshot = record.get("$set")
    messages = snapshot.get("messages") if isinstance(snapshot, dict) else None
    if not isinstance(messages, list):
        return (record,)
    messages = tuple(message for message in messages if isinstance(message, dict))
    previous_count = state["gemini_snapshot_count"]
    start = 0
    if (
        previous_count
        and len(messages) >= previous_count
        and record_fingerprint(messages[previous_count - 1]) == state["gemini_snapshot_tail"]
    ):
        start = previous_count
    state["gemini_snapshot_count"] = len(messages)
    state["gemini_snapshot_tail"] = record_fingerprint(messages[-1]) if messages else None
    return messages[start:]


def analyze_gemini_transcript(path: str) -> dict[str, Any]:
    """Gemini chats/*.jsonl tail: type 'user' | 'gemini' records with
    per-message tokens; resumed-session $set snapshots are expanded."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
    }
    seen = set()
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        for message in gemini_records(d):
            fingerprint = record_fingerprint(message)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            ep = parse_ts(message.get("timestamp") or "")
            if ep:
                info["last_event_ts"] = max(info["last_event_ts"], ep)
            t = message.get("type")
            if t == "user":
                txt = extract_text(message.get("content")).strip()
                if txt:
                    info["last_prompt"] = txt
                    info["title"] = txt.split("\n")[0][:80]
            elif t == "gemini":
                toks = message.get("tokens") or {}
                if ep and isinstance(toks, dict) and toks.get("output"):
                    info["usage_events"].append((ep, toks["output"]))
                for tc in message.get("toolCalls") or []:
                    if isinstance(tc, dict) and tc.get("name"):
                        info["last_tool"] = tc.get("name")
    return info


def analyze_copilot_events(path: str) -> dict[str, Any]:
    """Copilot events.jsonl tail: typed events with data payloads. Field
    names inside data are de-facto (not a stable API) — extracted
    defensively."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
        "cwd": None,
        "pending_agents": {},  # started-but-not-completed subagents
    }
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        t = d.get("type")
        data = d.get("data") or {}
        if not isinstance(data, dict):
            continue
        if t == "session.start":
            ctx = data.get("context") or {}
            info["cwd"] = ctx.get("cwd") or data.get("cwd") or info["cwd"]
        elif t == "user.message":
            txt = extract_text(data).strip()
            if txt:
                info["last_prompt"] = txt
                info["title"] = txt.split("\n")[0][:80]
        elif t == "tool.execution_start":
            name = data.get("toolName") or data.get("name") or data.get("tool")
            if name:
                info["last_tool"] = str(name)
        elif t == "subagent.started":
            key = data.get("id") or data.get("subagentId") or d.get("id")
            label = (
                data.get("name")
                or data.get("agentName")
                or data.get("agent")
                or data.get("agentType")
                or "subagent"
            )
            info["pending_agents"][key] = str(label)[:70]
        elif t == "subagent.completed":
            key = data.get("id") or data.get("subagentId") or d.get("id")
            if key in info["pending_agents"]:
                info["pending_agents"].pop(key)
            elif info["pending_agents"]:  # unmatched key scheme: drop oldest
                info["pending_agents"].pop(next(iter(info["pending_agents"])))
    return info


def analyze_droid_transcript(path: str) -> dict[str, Any]:
    """Droid transcript tail: {type: "message", timestamp, message: {role,
    content: [Anthropic-style blocks]}}."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
    }
    for line in read_tail(path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        if d.get("type") != "message":
            continue
        msg = d.get("message") or {}
        content = msg.get("content")
        blocks = content if isinstance(content, list) else []
        if msg.get("role") == "user":
            if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in blocks):
                continue
            txt = extract_text(content).strip()
            if txt:
                info["last_prompt"] = txt
                info["title"] = txt.split("\n")[0][:80]
        elif msg.get("role") == "assistant":
            for c in blocks:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    info["last_tool"] = c.get("name")
    return info


# ---------------------------------------------------------------------------
# Turn tracking


_turn_scan: dict[str, Any] = {}  # path -> incremental turn-tracking state
_scan_lock = threading.Lock()  # ThreadingHTTPServer: serialize scanner state
TURN_SCAN_MAX_BYTES = 8 * 1024 * 1024  # cap per-call read of a transcript delta


def _turn_signal(d: dict[str, Any], harness: str) -> tuple[str, Any] | None:
    """Classify a transcript record for turn tracking.

    Returns ("prompt"|"start"|"end", epoch_override|None) or None.
    "prompt" starts a turn and closes the previous one at the last event
    before it; "start"/"end" are explicit turn-span markers."""
    t = d.get("type")
    if harness == "codex":
        if t != "event_msg":
            return None
        p = d.get("payload") or {}
        pt = p.get("type")
        if pt == "task_started":
            return ("start", p.get("started_at"))
        if pt in ("task_complete", "turn_aborted"):
            return ("end", None)
        return None
    if harness == "copilot":
        if t == "user.message":
            return ("prompt", None)
        if t in ("session.task_complete", "session.shutdown", "abort"):
            return ("end", None)
        return None
    if harness == "gemini":
        if t != "user":
            return None
        content = d.get("content")
        if isinstance(content, list) and any(
            isinstance(c, dict) and "functionResponse" in c for c in content
        ):
            return None  # tool response recorded as a user part, not a prompt
        return ("prompt", None)
    if harness == "droid":
        if t != "message":
            return None
        msg = d.get("message") or {}
        if msg.get("role") != "user":
            return None
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(c, dict) and c.get("type") == "tool_result" for c in content
        ):
            return None
        return ("prompt", None)
    # claude
    if t != "user" or d.get("isMeta"):
        return None
    content = (d.get("message") or {}).get("content")
    if isinstance(content, list) and any(
        isinstance(c, dict) and c.get("type") == "tool_result" for c in content
    ):
        return None
    # Local command output/caveat records are user-typed but are not prompts —
    # nothing generates in response to them, so they must not start a turn.
    if isinstance(content, str) and content.lstrip().startswith(
        ("<local-command-stdout>", "<local-command-caveat>")
    ):
        return None
    return ("prompt", None)


def _apply_turn_record(st: dict[str, Any], record: Any, harness: str) -> None:
    """Apply one chronological transcript record to incremental turn state."""
    ep = parse_ts(record.get("timestamp") or "")
    if not ep:
        return
    # A quiet stretch longer than TURN_GAP_RESET_SEC inside a turn means the
    # agent was not generating (permission wait, AskUserQuestion, sleep).
    # Bank the active segment and restart the clock at the post-gap event so
    # "elapsed" reflects work, not waiting.
    if st["turn_start"] and st["prev_ts"] and ep - st["prev_ts"] > TURN_GAP_RESET_SEC:
        if st["prev_ts"] > st["turn_start"]:
            st["durations"].append(st["prev_ts"] - st["turn_start"])
        st["turn_start"] = ep
        st["last_start"] = ep
    sig = _turn_signal(record, harness)
    if sig:
        kind, override = sig
        if kind == "end":
            if st["turn_start"] and ep > st["turn_start"]:
                st["durations"].append(ep - st["turn_start"])
            st["turn_start"] = None
        else:
            if (
                kind == "prompt"
                and st["turn_start"]
                and st["prev_ts"]
                and st["prev_ts"] > st["turn_start"]
            ):
                st["durations"].append(st["prev_ts"] - st["turn_start"])
            start = norm_epoch(override) or ep
            st["turn_start"] = start
            st["last_start"] = start
    st["prev_ts"] = ep


def _latest_turn_context(path: str, end_pos: int, harness: str) -> dict[str, Any]:
    """Find the nearest turn boundary before ``end_pos`` without loading the
    prefix into memory. Used when the file is larger than the forward-read
    budget so a long current turn is not lost."""
    context: dict[str, Any] = {"turn_start": None, "last_start": None, "prev_ts": None}
    if end_pos <= 0:
        return context
    try:
        with open(path, "rb") as source:
            if os.fstat(source.fileno()).st_size == 0:
                return context
            with mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
                line_end = data.rfind(b"\n", 0, end_pos)
                if line_end < 0:
                    return context
                pos = line_end
                active_decided = False
                later_ts: float | None = None
                while pos > 0:
                    line_start = data.rfind(b"\n", 0, pos) + 1
                    raw = data[line_start:pos]
                    pos = line_start - 1
                    if not raw.startswith(b"{"):
                        continue
                    try:
                        decoded = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    records = (
                        reversed(gemini_records(decoded)) if harness == "gemini" else (decoded,)
                    )
                    for record in records:
                        ep = parse_ts(record.get("timestamp") or "")
                        if not ep:
                            continue
                        # Walking backward: `later_ts` is the timestamp of the
                        # record that chronologically FOLLOWS this one. A quiet
                        # gap re-anchors the turn at the post-gap record, same
                        # rule as the forward scanner.
                        if later_ts is not None and later_ts - ep > TURN_GAP_RESET_SEC:
                            if not active_decided:
                                context["turn_start"] = later_ts
                            context["last_start"] = later_ts
                            return context
                        later_ts = ep
                        if context["prev_ts"] is None:
                            context["prev_ts"] = ep
                        sig = _turn_signal(record, harness)
                        if not sig:
                            continue
                        kind, override = sig
                        if not active_decided:
                            active_decided = True
                            if kind != "end":
                                context["turn_start"] = norm_epoch(override) or ep
                        if kind != "end":
                            context["last_start"] = norm_epoch(override) or ep
                            return context
                return context
    except (OSError, ValueError):
        return context


def scan_turns(path: str, harness: str) -> dict[str, Any] | None:
    """Whole-file turn tracker for JSONL harnesses. The transcript tail can
    be shorter than the current turn (long turns bury the prompt >TAIL_BYTES
    back), so turns are tracked incrementally: each call parses only bytes
    appended since the last call and carries state in _turn_scan.

    Serialized via _scan_lock — concurrent /api/data requests would otherwise
    double-advance pos and double-count durations."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    with _scan_lock:
        st = _turn_scan.get(path)
        if st is None or st["pos"] > size:  # new, truncated, or rotated file
            if len(_turn_scan) >= MAX_CACHE_ENTRIES:
                _turn_scan.pop(next(iter(_turn_scan)))
            st = {
                "pos": 0,
                "turn_start": None,
                "last_start": None,
                "durations": [],
                "prev_ts": None,
                "gemini_seen": {},
                "gemini_snapshot_count": 0,
                "gemini_snapshot_tail": None,
            }
            _turn_scan[path] = st
        if size == st["pos"]:
            return st
        if size - st["pos"] > TURN_SCAN_MAX_BYTES:
            # Locate the active turn boundary in the skipped prefix with a
            # reverse mmap scan, then process the bounded tail forward.
            tail_start = size - TURN_SCAN_MAX_BYTES
            st.update(_latest_turn_context(path, tail_start, harness))
            st["pos"] = tail_start
        with open(path, "rb") as f:
            f.seek(st["pos"])
            data = f.read()
        end = data.rfind(b"\n")
        if end < 0:
            return st  # incomplete line, wait for more bytes
        st["pos"] += end + 1
        for raw in data[:end].split(b"\n"):
            if not raw.startswith(b"{"):
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            records = incremental_gemini_records(d, st) if harness == "gemini" else (d,)
            for record in records:
                if harness == "gemini":
                    fingerprint = record_fingerprint(record)
                    if fingerprint in st["gemini_seen"]:
                        continue
                    if len(st["gemini_seen"]) >= GEMINI_SEEN_ENTRIES:
                        st["gemini_seen"].pop(next(iter(st["gemini_seen"])))
                    st["gemini_seen"][fingerprint] = None
                _apply_turn_record(st, record, harness)
        st["durations"] = st["durations"][-50:]
        return st


def turns_from_events(events: list[tuple[float, bool]]) -> dict[str, Any]:
    """Turn state from chronologically sorted (epoch, is_user_prompt) pairs —
    used by DB-backed harnesses where messages come from SQL, not a file."""
    turn_start = prev = None
    durations = []
    for ep, is_user in events:
        if not ep:
            continue
        if is_user:
            if turn_start and prev and prev > turn_start:
                durations.append(prev - turn_start)
            turn_start = ep
        prev = ep
    return {"turn_start": turn_start, "durations": durations[-50:]}


def turn_progress(scan: dict[str, Any] | None, state: str, now: float) -> dict[str, Any] | None:
    """Naive current-turn ETA: estimated total = median of this session's
    past turns that lasted at least as long as the current one has so far."""
    if state != "working" or not scan or not scan.get("turn_start"):
        return None
    elapsed = max(0, now - scan["turn_start"])
    history = scan.get("durations") or []
    cands = sorted(d for d in history if d >= elapsed)
    if cands:
        est_total = cands[len(cands) // 2]
        return {
            "elapsed_h": fmt_duration(elapsed),
            "eta_h": fmt_duration(est_total - elapsed),
            "pct": min(99, round(elapsed * 100 / est_total)) if est_total else 99,
            "long": max(est_total, elapsed) >= LONG_TURN_WARN_SEC,
        }
    return {
        "elapsed_h": fmt_duration(elapsed),
        "eta_h": None,  # running longer than any recent turn
        "pct": 99 if history else None,
        "long": elapsed >= LONG_TURN_WARN_SEC,
    }


# ---------------------------------------------------------------------------
# Claude task files + subagents


def load_tasks() -> dict[str, list[dict[str, Any]]]:
    """session prefix -> list of task dicts."""
    by_session: dict[str, list[dict[str, Any]]] = {}
    for fp in glob.glob(os.path.join(TASKS_DIR, "*", "*.json")):
        if os.path.basename(fp).startswith("."):
            continue
        try:
            with open(fp) as f:
                task = json.load(f)
            st = os.stat(fp)
        except (OSError, json.JSONDecodeError):
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


def load_claude_subagents(transcript: str | None, now: float) -> list[dict[str, Any]]:
    """Running Claude subagents: <project>/<session-uuid>/subagents/
    agent-*.jsonl next to the session transcript; fresh mtime = running."""
    if not transcript:
        return []
    sess_dir = os.path.join(
        os.path.dirname(transcript), os.path.basename(transcript)[: -len(".jsonl")]
    )
    agents: list[dict[str, Any]] = []
    for fp in glob.glob(os.path.join(sess_dir, "subagents", "agent-*.jsonl")):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        if now - mtime > WORKING_THRESHOLD_SEC:
            continue
        label = None
        try:
            with open(fp[: -len(".jsonl")] + ".meta.json") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            meta = None
        # Meta values are untyped JSON — a non-string name must not
        # TypeError the whole Claude collector.
        if isinstance(meta, dict):
            for key in ("name", "description", "agentType"):
                value = meta.get(key)
                if isinstance(value, str) and value:
                    label = value
                    break
        agents.append({"label": (label or "subagent")[:70], "mtime": mtime})
    agents.sort(key=lambda a: -a["mtime"])
    return agents


# ---------------------------------------------------------------------------
# Notifications


def notify_mac(title: Any, message: Any) -> None:
    if sys.platform != "darwin":
        return

    def esc(s: str) -> str:
        return str(s).replace("\\", "\\\\").replace('"', '\\"')

    safe_message = notification_text(message, 180)
    safe_title = notification_text(title, 60)
    script = f'display notification "{esc(safe_message)}" with title "{esc(safe_title)}" sound name "Glass"'
    try:
        result = subprocess.run(  # noqa: S603 — fixed binary, esc()-sanitized args
            ["/usr/bin/osascript", "-e", script],
            timeout=5,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            print(f"[notify] osascript failed: {detail[:300]}")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"[notify] osascript failed: {type(exc).__name__}: {exc}")


def current_hook(
    prefix: str, last_user_event: str | None, last_event_ts: float
) -> dict[str, Any] | None:
    """Return an uncleared hook notification for a session.

    Hooks with a user-event marker clear when the newest user record changes
    (clock-independent). Hooks without one (payloads lacking transcript_path:
    the documented curl simulation, older Claude Code versions) fall back to
    the parsed-timestamp rule so they cannot stick forever.
    """
    with _lock:
        hook = _hook_notifs.get(prefix)
        if not hook:
            return None
        if "user_event" in hook:
            if last_user_event != hook["user_event"]:
                _hook_notifs.pop(prefix, None)
                return None
        elif last_event_ts > hook["ts"]:
            _hook_notifs.pop(prefix, None)
            return None
        return hook


def maybe_popup(prefix: str, state: str, detail: str | None) -> None:
    """Popup when a session transitions into a needs-input state."""
    now = time.time()
    with _lock:
        prev = _last_state.get(prefix)
        bounded_put(_last_state, prefix, state)
        if state != "needs_input" or prev == "needs_input":
            return
        if now - _last_popup.get(prefix, 0) < POPUP_COOLDOWN_SEC:
            return
        if now - _last_popup.get("_global", 0) < GLOBAL_POPUP_COOLDOWN_SEC:
            return
        bounded_put(_last_popup, prefix, now)
        bounded_put(_last_popup, "_global", now)
    notify_mac("Claude is waiting on you", detail or f"Session {prefix} needs your input")


# ---------------------------------------------------------------------------
# Session assembly helpers


def base_session(harness: str, sid: Any, project: str) -> dict[str, Any]:
    # "session" is the 8-char display id; "sid" keeps the full identity so
    # the client can key per-session state without truncation collisions
    # (e.g. Gemini "session-*" fallback ids all display as "session-").
    # Claude passes its 8-char prefix, so sid == session there — that whole
    # collector is already keyed on the prefix upstream.
    return {
        "session": str(sid)[:8],
        "sid": str(sid),
        "harness": harness,
        "project": project,
        "title": None,
        "last_prompt": "",
        "state": "idle",
        "state_detail": "awaiting your message",
        "active": False,
        "last_activity": 0,
        "rate_per_min": 0,
        "total": 0,
        "done": 0,
        "open": 0,
        "progress_pct": 0,
        "eta_h": None,
        "turn": None,
        "subagents": [],
        "tasks": [],
    }


def rate_from(info: dict[str, Any] | None, now: float) -> int:
    if not info:
        return 0
    recent: float = sum(tok for ep, tok in info["usage_events"] if now - ep <= RATE_WINDOW_SEC)
    return round(recent / (RATE_WINDOW_SEC / 60))


def codex_subagent_rate(path: str, now: float) -> int:
    """Recent Codex subagent output after its own task_started boundary."""
    scan = scan_turns(path, "codex")
    start = scan.get("last_start") if scan else None
    if not start:
        return 0
    info = analyze_codex_transcript(path)
    recent: float = sum(
        tokens
        for epoch, tokens in info["usage_events"]
        if epoch >= start and now - epoch <= RATE_WINDOW_SEC
    )
    return round(recent / (RATE_WINDOW_SEC / 60))


def working_detail(info: dict[str, Any] | None, subagents: list[Any]) -> str:
    if subagents:
        n = len(subagents)
        return f"running {n} subagent{'s' if n > 1 else ''}"
    if info and info.get("last_tool"):
        return f"running {info['last_tool']}"
    return "generating…"


# ---------------------------------------------------------------------------
# Harness collectors — each returns a list of session dicts


# Subagent-transcript classification cache. Whether a top-level transcript
# belongs to a subagent is immutable for a given file, but young files may
# not have written their identifying records yet — so negative results are
# only cached once the file is big enough to be conclusive.
_agent_class_cache: dict[str, tuple[bool, str, str]] = {}
_AGENT_SCAN_LINES = 50
_AGENT_CACHE_NEGATIVE_MIN_BYTES = 16384
_AGENT_SCAN_BYTES = _AGENT_CACHE_NEGATIVE_MIN_BYTES


def claude_agent_identity(path: str) -> tuple[bool, str, str]:
    """Classify a top-level transcript: (is_subagent, agent_name, parent_prefix).

    Harness >= 2.x writes subagent transcripts as ordinary <uuid>.jsonl files
    in the project directory; their records carry ``agentName`` and
    ``teamName`` = "session-<parent 8-char prefix>". Older harnesses used
    <session>/subagents/agent-*.jsonl, still handled by
    load_claude_subagents().
    """
    with _cache_lock:
        cached = _agent_class_cache.get(path)
    if cached is not None:
        return cached
    is_agent, name, parent = False, "", ""
    size = 0
    lines_seen = 0
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            data = f.read(_AGENT_SCAN_BYTES)
        lines = data.split(b"\n")
        if size > len(data) and data and not data.endswith(b"\n"):
            lines.pop()  # the byte prefix ended inside a JSON record
        for line in lines[:_AGENT_SCAN_LINES]:
            if not line:
                continue
            lines_seen += 1
            if is_agent and parent:
                break
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            agent_name = rec.get("agentName")
            if not is_agent and isinstance(agent_name, str) and agent_name:
                is_agent, name = True, agent_name
            team = rec.get("teamName")
            if not parent and isinstance(team, str) and team.startswith("session-"):
                parent = team[len("session-") :][:8]
    except OSError:
        return (False, "", "")
    result = (is_agent, name, parent)
    # A positive is conclusive; a negative is only trusted once the file has
    # enough content that the identifying records would have appeared.
    if is_agent or lines_seen >= _AGENT_SCAN_LINES or size >= _AGENT_CACHE_NEGATIVE_MIN_BYTES:
        with _cache_lock:
            bounded_put(_agent_class_cache, path, result)
    return result


def claude_prefix_is_agent(prefix: str) -> bool:
    """True when the newest transcript for this 8-char prefix belongs to a
    subagent. Used to suppress popups for agent sessions."""
    newest, newest_mtime = None, 0.0
    for fp in glob.glob(os.path.join(PROJECTS_DIR, "*", f"{prefix}*.jsonl")):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        if mtime > newest_mtime:
            newest, newest_mtime = fp, mtime
    if not newest:
        return False
    return claude_agent_identity(newest)[0]


def collect_claude(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    tasks_by_session = load_tasks()
    transcripts: dict[str, str] = {}  # prefix -> newest transcript path
    agent_children: dict[str, list[dict[str, Any]]] = {}  # parent prefix -> children
    for fp in glob.glob(os.path.join(PROJECTS_DIR, "*", "*.jsonl")):
        base = os.path.basename(fp)
        if "-agent-" in base or base.startswith("agent-"):
            continue  # legacy subagent transcripts aren't top-level sessions
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue  # transcript rotated/deleted between glob and stat
        if show_all or now - mtime <= window_hours * 3600:
            is_agent, agent_name, parent_prefix = claude_agent_identity(fp)
            if is_agent:
                # Fold into the parent session; never a standalone session.
                # Without a parent prefix there is nothing to attach to.
                if parent_prefix and now - mtime <= window_hours * 3600:
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

    out: list[dict[str, Any]] = []
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
        subagents = load_claude_subagents(transcript, now)
        children = agent_children.get(prefix, [])
        subagents += [
            {"label": c["label"], "mtime": c["mtime"]}
            for c in children
            if now - c["mtime"] <= WORKING_THRESHOLD_SEC  # fresh = running
        ]
        latest_agent_mtime = max(
            (a["mtime"] for a in subagents),
            default=0,
        )
        latest_child_mtime = max((c["mtime"] for c in children), default=0)
        last_activity = max(
            latest_task_mtime, transcript_mtime, latest_agent_mtime, latest_child_mtime
        )
        active = (now - last_activity) <= window_hours * 3600
        if not (active or show_all):
            continue

        project = (
            project_label(os.path.basename(os.path.dirname(transcript)))
            if transcript
            else "unknown"
        )
        info = analyze_transcript(transcript) if (transcript and active) else None

        state, state_detail = "idle", "awaiting your message"
        blocked_since = None
        # mtime floor: match the other collectors when the newest write has
        # no parseable timestamp (partial line, untimestamped record)
        parsed_last_event = info["last_event_ts"] if info else 0
        last_event = max(parsed_last_event, transcript_mtime)
        hook = (
            current_hook(prefix, (info or {}).get("last_user_event"), parsed_last_event)
            if active
            else None
        )
        if info and info["pending_input_tool"]:
            p = info["pending_input_tool"]
            state = "needs_input"
            blocked_since = p["ts"] or last_activity
            state_detail = f"open question ({p['name']}), waiting {fmt_duration(now - p['ts']) if p['ts'] else '?'}"
        # Fresh activity beats a hook: Claude Code emits "waiting for your
        # input" notifications for sessions that keep running via background
        # tasks and will resume on their own. A hook only surfaces as
        # needs-input once the session actually goes quiet; permission-prompt
        # popups are unaffected (they fire on the POST itself).
        elif subagents or now - last_event <= WORKING_THRESHOLD_SEC:
            state = "working"
            in_prog = next((t for t in tasks if t["status"] == "in_progress"), None)
            if in_prog:
                state_detail = (in_prog["activeForm"] or in_prog["subject"]) + "…"
            else:
                state_detail = working_detail(info, subagents)
        elif hook:
            state = "needs_input"
            blocked_since = hook["ts"]
            state_detail = hook["message"] or "waiting for your input"
        if active:
            maybe_popup(
                prefix, state, f"[{project}] {state_detail}" if state == "needs_input" else None
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
                else (now - t["created"])
            )
            t["elapsed_h"] = fmt_duration(elapsed)
            t["updated_ago"] = fmt_duration(now - t["updated"]) + " ago"

        s = base_session("claude", prefix, project)
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "blocked_since": blocked_since,
                "active": active,
                "last_activity": last_activity,
                # Subagent output now lives in the children's own transcripts;
                # fold it in so the session's rate reflects all its work.
                "rate_per_min": rate_from(info, now)
                + sum(
                    rate_from(analyze_transcript(c["path"]), now)
                    for c in children
                    if now - c["mtime"] <= RATE_WINDOW_SEC
                ),
                "total": total,
                "done": done,
                "open": open_count,
                "progress_pct": round(done * 100 / total) if total else 0,
                "eta_h": fmt_duration(eta_sec) if eta_sec else None,
                "turn": turn_progress(
                    scan_turns(transcript, "claude") if (info and transcript) else None,
                    state,
                    now,
                ),
                "subagents": [a["label"] for a in subagents],
                "tasks": tasks,
            }
        )
        out.append(s)
    return out


def collect_codex(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    # Resumes and subagent threads write separate rollout files; group by the
    # session_meta session_id, keep the newest top-level file per session,
    # and treat fresh subagent-thread files as that session's running agents.
    sessions: dict[str, tuple[float, str]] = {}  # session_id -> (mtime, path)
    # parent session_id -> {"agents": [(label, mtime)], "rate": int}
    agent_data: dict[str, dict[str, Any]] = {}
    for fp in glob.glob(os.path.join(CODEX_SESSIONS_DIR, "*", "*", "*", "rollout-*.jsonl")):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        meta = codex_meta(fp)
        sid = meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")][-36:]
        if meta.get("subagent"):
            parent_sid = meta.get("parent_session_id") or sid
            data = agent_data.setdefault(parent_sid, {"agents": [], "rate": 0})
            if now - mtime <= RATE_WINDOW_SEC:
                data["rate"] += codex_subagent_rate(fp, now)
            if now - mtime <= WORKING_THRESHOLD_SEC:
                data["agents"].append(((meta.get("agent_label") or "subagent")[:70], mtime))
            continue
        if sid not in sessions or mtime > sessions[sid][0]:
            sessions[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in sessions.items():
        data = agent_data.get(sid) or {"agents": [], "rate": 0}
        agents = sorted(data["agents"], key=lambda a: -a[1])
        last_activity = max(mtime, max((m for _, m in agents), default=0))
        active = (now - last_activity) <= window_hours * 3600
        if not (active or show_all):
            continue
        info = analyze_codex_transcript(fp) if active else None
        last_event = max(info["last_event_ts"] if info else 0, last_activity)
        subagents = [label for label, _ in agents]
        state, state_detail = "idle", "awaiting your message"
        if now - last_event <= WORKING_THRESHOLD_SEC:
            state = "working"
            state_detail = working_detail(info, subagents)

        s = base_session("codex", sid, os.path.basename(codex_meta(fp).get("cwd") or "") or "codex")
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": rate_from(info, now) + data["rate"],
                "turn": turn_progress(scan_turns(fp, "codex") if info else None, state, now),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out


def antigravity_log_lines(path: str) -> list[str]:
    """Read the beginning and bounded tail of an Antigravity CLI log.

    Workspace and conversation identity are written near the beginning,
    while the latest user prompt is near the tail. Long-running sessions can
    exceed ``TAIL_BYTES``, so reading only one side loses one of those.
    """
    head = []
    try:
        with open(path, "rb") as source:
            data = source.read(80_000).decode("utf-8", "replace")
        head = data.splitlines()
    except OSError:
        pass
    tail = read_tail(path)
    return head + tail


def antigravity_session_metadata(
    now: float, window_hours: float, show_all: bool
) -> dict[str, dict[str, Any]]:
    """Best-effort conversation metadata from Antigravity's public-facing
    CLI logs and last-conversation cache.

    Conversation payloads are protobuf blobs inside per-session SQLite
    stores. The logs already expose the stable boundaries needed here:
    workspace, conversation id, and human prompt. Broken or rotated files are
    skipped so one incomplete Antigravity run cannot break the dashboard.
    """
    sessions: dict[str, dict[str, Any]] = {}
    try:
        with open(ANTIGRAVITY_LAST_CONVERSATIONS, encoding="utf-8") as source:
            recent = json.load(source)
        if isinstance(recent, dict):
            for workspace, sid in recent.items():
                if isinstance(workspace, str) and isinstance(sid, str):
                    sessions.setdefault(sid, {})["cwd"] = workspace
    except (OSError, ValueError, TypeError, RecursionError):
        pass

    logs = glob.glob(os.path.join(ANTIGRAVITY_LOG_DIR, "cli-*.log"))
    if not show_all:
        recent_logs: list[str] = []
        for path in logs:
            try:
                if now - os.path.getmtime(path) <= window_hours * 3600:
                    recent_logs.append(path)
            except OSError:
                continue
        logs = recent_logs
    try:
        logs.sort(key=os.path.getmtime)
    except OSError:
        logs.sort()

    workspace_re = re.compile(r"workspaceDirs=\[(.*?)\]\s+appDataDir=")
    session_re = re.compile(r"(?:Created|Streaming) conversation ([0-9a-fA-F-]{36})")
    forward_re = re.compile(r"Forwarding user message to conversation ([0-9a-fA-F-]{36})")
    prompt_marker = "HandleUserInput called with text: "

    for path in logs:
        workspace = None
        pending_prompt = None
        for line in antigravity_log_lines(path):
            match = workspace_re.search(line)
            if match:
                workspace = match.group(1).strip() or None
                continue
            match = session_re.search(line)
            if match:
                session = sessions.setdefault(match.group(1), {})
                if workspace:
                    session["cwd"] = workspace
                continue
            if prompt_marker in line:
                raw = line.split(prompt_marker, 1)[1].strip()
                try:
                    decoded = json.loads(raw)
                    pending_prompt = decoded if isinstance(decoded, str) else raw
                except (ValueError, TypeError, RecursionError):
                    pending_prompt = raw.strip('"')
                pending_prompt = notification_text(pending_prompt, 2000)
                continue
            match = forward_re.search(line)
            if match:
                session = sessions.setdefault(match.group(1), {})
                if workspace:
                    session["cwd"] = workspace
                if pending_prompt:
                    session["last_prompt"] = pending_prompt
                    pending_prompt = None
    return sessions


def antigravity_store_mtime(path: str) -> float:
    """Newest durable activity marker for a live conversation store."""
    mtimes: list[float] = []
    for candidate in (path, path + "-wal"):
        with contextlib.suppress(OSError):
            mtimes.append(os.path.getmtime(candidate))
    return max(mtimes, default=0)


def protobuf_fields(payload: Any) -> Iterator[tuple[int, int, Any]]:
    """Yield ``(field_number, wire_type, value)`` from a protobuf message.

    Antigravity persists step metadata as protobuf without shipping Python
    descriptors. This bounded wire reader extracts only the stable scalar and
    length-delimited envelope fields needed by the dashboard; malformed
    messages raise ``ValueError`` and are skipped by the caller.
    """
    payload = bytes(payload or b"")
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


def antigravity_step_info(metadata: Any) -> dict[str, Any]:
    """Timestamp, output usage, and tool labels from a step metadata blob."""
    started = protobuf_first(metadata, 1, 2)
    usage = protobuf_first(metadata, 9, 2)
    summary = protobuf_first(metadata, 30, 2)
    action = protobuf_first(metadata, 31, 2)
    output_tokens = protobuf_first(usage, 3, 0) if usage else 0

    def text(value: Any) -> str:
        if not value:
            return ""
        return notification_text(value.decode("utf-8", "replace"), 140)

    return {
        "epoch": protobuf_timestamp(started) if started else 0,
        "output_tokens": output_tokens or 0,
        "tool_summary": text(summary),
        "tool_action": text(action),
    }


def antigravity_step_activity(path: str, now: float) -> dict[str, Any]:
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
    query = "SELECT step_type, metadata FROM steps ORDER BY idx DESC LIMIT ?"
    rows = None
    for uri in (f"file:{path}?mode=ro", f"file:{path}?mode=ro&immutable=1"):
        try:
            con = sqlite3.connect(uri, uri=True, timeout=0.2)
        except sqlite3.Error:
            continue
        try:
            rows = con.execute(query, (SQL_MSG_LIMIT,)).fetchall()
            break
        except sqlite3.Error:
            continue
        finally:
            con.close()
    if rows is None:
        return result

    events = []
    usage_events = []
    last_prompt = 0
    latest_action = (0, "")
    for step_type, metadata in reversed(rows):
        info = antigravity_step_info(metadata)
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

    recent = sum(tokens for epoch, tokens in usage_events if now - epoch <= RATE_WINDOW_SEC)
    result["rate_per_min"] = round(recent / (RATE_WINDOW_SEC / 60))
    result["turns"] = turns_from_events(events) if events else None
    result["last_tool_action"] = latest_action[1]
    return result


def collect_antigravity(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    metadata = antigravity_session_metadata(now, window_hours, show_all)
    out: list[dict[str, Any]] = []
    for db in glob.glob(os.path.join(ANTIGRAVITY_CONVERSATIONS_DIR, "*.db")):
        sid = os.path.basename(db)[: -len(".db")]
        mtime = antigravity_store_mtime(db)
        if not mtime:
            continue
        active = (now - mtime) <= window_hours * 3600
        if not (active or show_all):
            continue
        activity: dict[str, Any] = (
            antigravity_step_activity(db, now)
            if active
            else {"rate_per_min": 0, "turns": None, "last_tool_action": ""}
        )
        state, state_detail = "idle", "awaiting your message"
        if now - mtime <= WORKING_THRESHOLD_SEC:
            state = "working"
            state_detail = activity["last_tool_action"] or "generating response…"

        meta = metadata.get(sid) or {}
        prompt = str(meta.get("last_prompt") or "").strip()
        cwd = str(meta.get("cwd") or "").strip()
        project = os.path.basename(cwd.rstrip(os.sep)) or "antigravity"
        session = base_session("gemini", sid, project)
        session.update(
            {
                "title": prompt.split("\n")[0][:80] or None,
                "last_prompt": prompt[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
                "rate_per_min": activity["rate_per_min"],
                "turn": turn_progress(activity["turns"], state, now),
            }
        )
        out.append(session)
    return out


def collect_gemini(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    # Legacy Gemini CLI main sessions:
    # <tmp>/<project>/chats/session-*.jsonl. Subagents:
    # <tmp>/<project>/chats/<safeParentSessionId>/<id>.jsonl — linked to the
    # parent purely by the directory name. Antigravity CLI sessions are
    # appended from its per-conversation SQLite stores below.
    # sanitized parent session id -> [(label, mtime)]
    agents_by_parent: dict[str, list[tuple[str, float]]] = {}
    for fp in glob.glob(os.path.join(GEMINI_TMP, "*", "chats", "*", "*.jsonl")):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        if now - mtime > WORKING_THRESHOLD_SEC:
            continue
        parent = alnum(os.path.basename(os.path.dirname(fp)))
        label = "subagent " + os.path.basename(fp)[:8]
        agents_by_parent.setdefault(parent, []).append((label, mtime))

    sessions: dict[
        str, tuple[float, str]
    ] = {}  # session id (or filename fallback) -> (mtime, path)
    for fp in glob.glob(os.path.join(GEMINI_TMP, "*", "chats", "session-*.jsonl")):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        meta = gemini_meta(fp)
        if meta.get("kind") == "subagent":
            continue
        sid = meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")]
        if sid not in sessions or mtime > sessions[sid][0]:
            sessions[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in sessions.items():
        agents = sorted(agents_by_parent.get(alnum(sid), []), key=lambda a: -a[1])
        last_activity = max(mtime, max((m for _, m in agents), default=0))
        active = (now - last_activity) <= window_hours * 3600
        if not (active or show_all):
            continue
        info = analyze_gemini_transcript(fp) if active else None
        last_event = max(info["last_event_ts"] if info else 0, last_activity)
        subagents = [label for label, _ in agents]
        state, state_detail = "idle", "awaiting your message"
        if now - last_event <= WORKING_THRESHOLD_SEC:
            state = "working"
            state_detail = working_detail(info, subagents)

        cwd = gemini_meta(fp).get("cwd")
        project = os.path.basename(cwd or "") or project_label(
            os.path.basename(os.path.dirname(os.path.dirname(fp)))
        )
        s = base_session("gemini", sid, project)
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": last_activity,
                "rate_per_min": rate_from(info, now),
                "turn": turn_progress(scan_turns(fp, "gemini") if info else None, state, now),
                "subagents": subagents,
            }
        )
        out.append(s)
    out.extend(collect_antigravity(now, window_hours, show_all))
    return out


def collect_copilot(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    files: dict[
        str, tuple[float, str]
    ] = {}  # session uuid -> newest events.jsonl (dir tie: current)
    # history-session-state is assumed to share the <uuid>/events.jsonl
    # layout — unverified legacy format; a mismatch just means those old
    # sessions stay invisible.
    for base in ("session-state", "history-session-state"):
        for fp in glob.glob(os.path.join(COPILOT_DIR, base, "*", "events.jsonl")):
            sid = os.path.basename(os.path.dirname(fp))
            try:
                mtime = os.path.getmtime(fp)
            except OSError:
                continue
            if sid not in files or mtime > files[sid][0]:
                files[sid] = (mtime, fp)

    out: list[dict[str, Any]] = []
    for sid, (mtime, fp) in files.items():
        active = (now - mtime) <= window_hours * 3600
        if not (active or show_all):
            continue
        info = analyze_copilot_events(fp) if active else None
        last_event = max(info["last_event_ts"] if info else 0, mtime)
        state, state_detail = "idle", "awaiting your message"
        subagents: list[str] = []
        if now - last_event <= WORKING_THRESHOLD_SEC:
            state = "working"
            subagents = list((info or {}).get("pending_agents", {}).values())
            state_detail = working_detail(info, subagents)

        cwd = (info or {}).get("cwd") or copilot_meta(fp).get("cwd")
        s = base_session("copilot", sid, os.path.basename(cwd or "") or "copilot")
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
                "turn": turn_progress(scan_turns(fp, "copilot") if info else None, state, now),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out


def _sql_ro(path: str) -> sqlite3.Connection:
    """Read-only SQLite connection that never blocks a live agent's writes."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2)
    con.row_factory = sqlite3.Row
    return con


def collect_opencode(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for db in glob.glob(os.path.join(OPENCODE_DATA, "opencode*.db")):
        try:
            con = _sql_ro(db)
        except sqlite3.Error:
            continue
        # ?all=1 promises every session ever; LIMIT -1 is SQLite's "no limit".
        limit = -1 if show_all else 200
        try:
            try:
                rows = con.execute(
                    "SELECT id, parent_id, directory, title, time_updated, time_archived "
                    "FROM session ORDER BY time_updated DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            except sqlite3.OperationalError:  # older schema without time_archived
                rows = con.execute(
                    "SELECT id, parent_id, directory, title, time_updated, "
                    "NULL AS time_archived FROM session "
                    "ORDER BY time_updated DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except sqlite3.Error:
            con.close()
            continue
        try:
            children: dict[
                Any, list[tuple[str, float]]
            ] = {}  # parent session id -> [(title, epoch)]
            tops: list[tuple[Any, float]] = []
            for r in rows:
                if r["time_archived"]:
                    continue  # archival bumps time_updated; don't ghost as working
                upd = norm_epoch(r["time_updated"])
                if r["parent_id"]:
                    if now - upd <= WORKING_THRESHOLD_SEC:
                        children.setdefault(r["parent_id"], []).append(
                            ((r["title"] or "subagent")[:70], upd)
                        )
                else:
                    tops.append((r, upd))
            for r, upd in tops:
                agents = sorted(children.get(r["id"], []), key=lambda a: -a[1])
                last_activity = max(upd, max((m for _, m in agents), default=0))
                active = (now - last_activity) <= window_hours * 3600
                if not (active or show_all):
                    continue
                subagents = [label for label, _ in agents]
                state, state_detail = "idle", "awaiting your message"
                if now - last_activity <= WORKING_THRESHOLD_SEC:
                    state = "working"
                    state_detail = working_detail(None, subagents)

                turn = None
                last_prompt = ""
                if active:
                    events = []
                    try:
                        # The message kind lives in the `type` COLUMN (tagged
                        # union discriminator); `data` omits type/id and holds
                        # the prompt in data.text.
                        msgs = con.execute(
                            "SELECT type, time_created, data FROM session_message "
                            "WHERE session_id = ? ORDER BY time_created DESC LIMIT ?",
                            (r["id"], SQL_MSG_LIMIT),
                        ).fetchall()
                        for m in reversed(msgs):
                            is_user = m["type"] == "user"
                            events.append((norm_epoch(m["time_created"]), is_user))
                            if is_user:
                                try:
                                    jd = json.loads(m["data"] or "{}")
                                except (ValueError, TypeError):
                                    jd = {}
                                last_prompt = extract_text(jd)[:140] or last_prompt
                    except sqlite3.Error:
                        pass
                    turn = turn_progress(turns_from_events(events), state, now)

                s = base_session(
                    "opencode", r["id"], os.path.basename(r["directory"] or "") or "opencode"
                )
                s.update(
                    {
                        "title": (r["title"] or "").strip()[:80] or None,
                        "last_prompt": last_prompt,
                        "state": state,
                        "state_detail": state_detail,
                        "active": active,
                        "last_activity": last_activity,
                        "turn": turn,
                        "subagents": subagents,
                    }
                )
                out.append(s)
        finally:
            con.close()
    return out


_cursor_title_cache: dict[str, tuple[float, str | None]] = {}  # db path -> (mtime, title)


def _cursor_title(db: str, mtime: float) -> str | None:
    """Session name from the meta table: hex-encoded UTF-8 JSON (some
    versions store plain JSON; value may be NULL or non-text). mode=ro (not
    immutable) so names still in the WAL are visible. Memoized by mtime —
    titles are stable, so no per-refresh reopen."""
    with _cache_lock:
        hit = _cursor_title_cache.get(db)
    if hit and hit[0] == mtime:
        return hit[1]
    title = None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=0.2)
    except sqlite3.Error:
        return None
    try:
        rows = con.execute("SELECT value FROM meta LIMIT 5").fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        con.close()
    for (raw,) in rows:
        v = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not isinstance(v, str):
            continue
        candidates = [v]  # plain JSON first: a hex string can't parse to a dict
        with contextlib.suppress(ValueError):
            candidates.append(bytes.fromhex(v).decode("utf-8", "replace"))
        for decoded in candidates:
            try:
                d = json.loads(decoded)
            except (ValueError, TypeError):
                continue
            if isinstance(d, dict):
                name = (d.get("name") or d.get("title") or "").strip()
                if name:
                    title = name[:80]
                    break
        if title:
            break
    with _cache_lock:
        hit = _cursor_title_cache.get(db)
        if hit and hit[0] == mtime:
            return hit[1]
        bounded_put(_cursor_title_cache, db, (mtime, title))
        return title


def collect_cursor(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    # One store.db per chat; content is opaque-ish (hex JSON blobs), so
    # Cursor rows are discovery + state + title only — no turn ETA.
    out: list[dict[str, Any]] = []
    for db in glob.glob(os.path.join(CURSOR_CHATS, "*", "*", "store.db")):
        sid = os.path.basename(os.path.dirname(db))
        try:
            mtime = os.path.getmtime(db)
            wal = db + "-wal"
            if os.path.exists(wal):
                mtime = max(mtime, os.path.getmtime(wal))
        except OSError:
            continue
        active = (now - mtime) <= window_hours * 3600
        if not (active or show_all):
            continue
        state, state_detail = "idle", "awaiting your message"
        if now - mtime <= WORKING_THRESHOLD_SEC:
            state, state_detail = "working", "generating…"
        s = base_session("cursor", sid, "cursor")
        s.update(
            {
                "title": _cursor_title(db, mtime) if active else None,
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
            }
        )
        out.append(s)
    return out


def goose_user_prompt(content: Any) -> bool:
    """Return whether a Goose role=user message came from the human.

    Goose also records tool results with role=user; those entries carry a
    toolResponse content part and must not start a new turn.
    """
    if not isinstance(content, list):
        return True
    return not any(
        isinstance(part, dict) and alnum(part.get("type")) == "toolresponse" for part in content
    )


def collect_goose(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    # Single shared sessions.db (v1.10.0+): per-session activity comes from
    # the updated_at column, NOT file mtime (the DB is shared by all
    # sessions). Legacy per-session .jsonl files are not supported.
    try:
        con = _sql_ro(GOOSE_DB)
    except sqlite3.Error:
        return []
    try:
        try:
            rows = con.execute(
                "SELECT id, description, working_dir, updated_at, "
                "session_type, parent_session_id, archived_at FROM sessions"
            ).fetchall()
        except sqlite3.OperationalError:  # older schema without those columns
            rows = con.execute(
                "SELECT id, description, working_dir, updated_at, "
                "NULL AS session_type, NULL AS parent_session_id, "
                "NULL AS archived_at FROM sessions"
            ).fetchall()

        children: dict[Any, list[tuple[str, float]]] = {}  # parent session id -> [(label, epoch)]
        tops: list[tuple[Any, float]] = []
        for r in rows:
            if r["archived_at"]:
                continue  # archival bumps updated_at; don't resurrect
            upd = parse_utc_sql(r["updated_at"])
            stype = alnum(r["session_type"])
            if stype == "subagent":
                if r["parent_session_id"] and now - upd <= WORKING_THRESHOLD_SEC:
                    children.setdefault(r["parent_session_id"], []).append(
                        ((r["description"] or "subagent")[:70], upd)
                    )
                continue
            if stype in ("hidden", "terminal", "gateway", "acp"):
                continue  # infrastructure sessions goose's own list hides
            tops.append((r, upd))

        out: list[dict[str, Any]] = []
        for r, upd in tops:
            agents = sorted(children.get(r["id"], []), key=lambda a: -a[1])
            last_activity = max(upd, max((m for _, m in agents), default=0))
            active = (now - last_activity) <= window_hours * 3600
            if not (active or show_all):
                continue
            subagents = [label for label, _ in agents]
            state, state_detail = "idle", "awaiting your message"
            if now - last_activity <= WORKING_THRESHOLD_SEC:
                state = "working"
                state_detail = working_detail(None, subagents)

            turn = None
            last_prompt = ""
            rate = 0
            if active:
                events = []
                try:
                    msgs = con.execute(
                        "SELECT role, created_timestamp, content_json FROM messages "
                        "WHERE session_id = ? ORDER BY created_timestamp DESC LIMIT ?",
                        (r["id"], SQL_MSG_LIMIT),
                    ).fetchall()
                    for m in reversed(msgs):
                        ep = norm_epoch(m["created_timestamp"])
                        try:
                            content = json.loads(m["content_json"] or "[]")
                        except (ValueError, TypeError, RecursionError):
                            content = []
                        is_prompt = m["role"] == "user" and goose_user_prompt(content)
                        events.append((ep, is_prompt))
                        if is_prompt:
                            last_prompt = extract_text(content)[:140] or last_prompt
                except sqlite3.Error:
                    pass
                try:
                    # Token accounting lives in usage_ledger, NOT messages.tokens
                    # (goose never writes that column).
                    led = con.execute(
                        "SELECT created_timestamp, output_tokens FROM usage_ledger "
                        "WHERE session_id = ? ORDER BY created_timestamp DESC LIMIT 200",
                        (r["id"],),
                    ).fetchall()
                    recent = sum(
                        (x["output_tokens"] or 0)
                        for x in led
                        if now - norm_epoch(x["created_timestamp"]) <= RATE_WINDOW_SEC
                    )
                    rate = round(recent / (RATE_WINDOW_SEC / 60))
                except sqlite3.Error:
                    pass
                turn = turn_progress(turns_from_events(events), state, now)

            s = base_session("goose", r["id"], os.path.basename(r["working_dir"] or "") or "goose")
            s.update(
                {
                    "title": (r["description"] or "").strip()[:80] or None,
                    "last_prompt": last_prompt,
                    "state": state,
                    "state_detail": state_detail,
                    "active": active,
                    "last_activity": last_activity,
                    "rate_per_min": rate,
                    "turn": turn,
                    "subagents": subagents,
                }
            )
            out.append(s)
    except sqlite3.Error:
        return []
    else:
        return out
    finally:
        con.close()


def collect_droid(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fp in glob.glob(os.path.join(FACTORY_PROJECTS, "*", "*.jsonl")):
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        active = (now - mtime) <= window_hours * 3600
        if not (active or show_all):
            continue
        meta = droid_meta(fp)
        sid = str(meta.get("session_id") or os.path.basename(fp)[: -len(".jsonl")])
        info = analyze_droid_transcript(fp) if active else None
        last_event = max(info["last_event_ts"] if info else 0, mtime)
        state, state_detail = "idle", "awaiting your message"
        if now - last_event <= WORKING_THRESHOLD_SEC:
            state = "working"
            state_detail = working_detail(info, [])

        project = os.path.basename(meta.get("cwd") or "") or project_label(
            os.path.basename(os.path.dirname(fp))
        )
        s = base_session("droid", sid, project)
        s.update(
            {
                "title": (meta.get("title") or "").strip()[:80] or (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
                "turn": turn_progress(scan_turns(fp, "droid") if info else None, state, now),
            }
        )
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# Harness registry — a harness appears in the dashboard only if discovered


HARNESSES: list[
    tuple[str, str, Callable[[], bool], Callable[[float, float, bool], list[dict[str, Any]]]]
] = [
    ("claude", "Claude", lambda: os.path.isdir(PROJECTS_DIR), collect_claude),
    ("codex", "Codex", lambda: os.path.isdir(CODEX_SESSIONS_DIR), collect_codex),
    # Predicate matches both supported Gemini stores: legacy Gemini CLI
    # JSONL and current Antigravity CLI per-conversation SQLite databases.
    (
        "gemini",
        "Gemini",
        lambda: bool(
            glob.glob(os.path.join(GEMINI_TMP, "*", "chats", "session-*.jsonl"))
            or glob.glob(os.path.join(ANTIGRAVITY_CONVERSATIONS_DIR, "*.db"))
        ),
        collect_gemini,
    ),
    (
        "copilot",
        "Copilot",
        lambda: (
            os.path.isdir(os.path.join(COPILOT_DIR, "session-state"))
            or os.path.isdir(os.path.join(COPILOT_DIR, "history-session-state"))
        ),
        collect_copilot,
    ),
    (
        "opencode",
        "OpenCode",
        lambda: bool(glob.glob(os.path.join(OPENCODE_DATA, "opencode*.db"))),
        collect_opencode,
    ),
    (
        "cursor",
        "Cursor",
        lambda: bool(glob.glob(os.path.join(CURSOR_CHATS, "*", "*", "store.db"))),
        collect_cursor,
    ),
    ("goose", "Goose", lambda: os.path.isfile(GOOSE_DB), collect_goose),
    (
        "droid",
        "Droid",
        lambda: bool(glob.glob(os.path.join(FACTORY_PROJECTS, "*", "*.jsonl"))),
        collect_droid,
    ),
]


def collect(window_hours: float, show_all: bool) -> dict[str, Any]:
    now = time.time()
    out_sessions: list[dict[str, Any]] = []
    harnesses: list[dict[str, Any]] = []
    for key, label, discover, collector in HARNESSES:
        try:
            found = bool(discover())
        except OSError:
            found = False
        harness: dict[str, Any] = {
            "key": key,
            "label": label,
            "discovered": found,
            "error": None,
        }
        harnesses.append(harness)
        if not found:
            continue
        try:
            out_sessions.extend(collector(now, window_hours, show_all))
        except Exception as e:  # noqa: BLE001 — one broken harness must not take down the rest
            harness["error"] = f"{type(e).__name__}: {e}"
            print(f"[{key}] collector error: {harness['error']}")

    state_rank = {"needs_input": 0, "working": 1, "idle": 2}
    # Session id as tiebreaker (not last_activity) so rows don't reshuffle
    # on every refresh while sessions are generating.
    out_sessions.sort(key=lambda x: (state_rank.get(x["state"], 3), x["sid"]))
    active_sessions = [x for x in out_sessions if x["active"]]
    total_tasks = sum(x["total"] for x in out_sessions)
    total_done = sum(x["done"] for x in out_sessions)
    return {
        "generated": now,
        "window_hours": window_hours,
        "show_all": show_all,
        "harnesses": harnesses,
        "summary": {
            "needs_input": sum(1 for x in active_sessions if x["state"] == "needs_input"),
            "working": sum(1 for x in active_sessions if x["state"] == "working"),
            "rate_per_min": sum(x["rate_per_min"] for x in active_sessions),
            "active_sessions": len(active_sessions),
            "open_tasks": sum(x["open"] for x in out_sessions),
            "progress_pct": round(total_done * 100 / total_tasks) if total_tasks else 0,
            "total_tasks": total_tasks,
            "total_done": total_done,
        },
        "sessions": out_sessions,
    }


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cargento</title>
<style>
  :root{
    --bg:#f6f3ec; --panel:#fffdf8; --ink:#26241d; --ink2:#57534a; --ink3:#8f897c;
    --line:#e6e0d3; --accent:oklch(0.80 0.16 122); --alert:oklch(0.55 0.19 27);
    --sans:'Space Grotesk',system-ui,-apple-system,sans-serif; --mono:'Space Mono',ui-monospace,monospace;
  }
  @media (prefers-color-scheme:dark){
    :root{
      --bg:#1a1916; --panel:#222019; --ink:#efece3; --ink2:#b3ad9f; --ink3:#7c7669;
      --line:#302d25; --accent:oklch(0.84 0.17 122); --alert:oklch(0.72 0.17 27);
    }
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--bg);color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  a{color:var(--ink)}
  .wrap{max-width:1180px;margin:0 auto;padding:34px 30px 64px;display:flex;flex-direction:column;gap:26px}
  @keyframes pulse{50%{opacity:.32}}
  @keyframes livebar{0%{transform:translateX(-140%)}100%{transform:translateX(320%)}}

  /* header */
  .top{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;flex-wrap:wrap}
  .brand{font-size:32px;font-weight:700;letter-spacing:-.025em;line-height:1}
  .sub{font-family:var(--mono);font-size:12px;color:var(--ink3);margin-top:10px;display:flex;align-items:center;gap:8px}
  .live{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 1.6s infinite}
  .live.stalled{background:var(--alert);animation:none}
  .hstrip{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end;max-width:440px}
  .hstrip-k{font-family:var(--mono);font-size:10px;color:var(--ink3);text-transform:uppercase;letter-spacing:.1em;margin-right:3px}

  /* harness badges */
  .hbadge{position:relative;display:inline-flex}
  .btile{width:24px;height:24px;border-radius:7px;display:inline-flex;align-items:center;justify-content:center;flex:none}
  .bico{width:14px;height:14px;display:block}
  .bmono{font-family:var(--mono);font-size:9.5px;font-weight:700}
  .hstrip .btile{width:26px;height:26px;border-radius:8px}
  .hstrip .bico{width:15px;height:15px}
  .hstrip .bmono{font-size:10px}
  .hbadge .htip{position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%) translateY(3px);opacity:0;pointer-events:none;transition:opacity .14s ease,transform .14s ease;white-space:nowrap;z-index:40;font-family:var(--mono);font-size:11px;font-weight:500;color:var(--bg);background:var(--ink);padding:5px 9px;border-radius:7px;box-shadow:0 6px 18px -6px rgba(0,0,0,.5)}
  .hbadge:hover .htip{opacity:1;transform:translateX(-50%) translateY(0)}

  /* hero tiles */
  .hero{display:grid;grid-template-columns:1fr 1fr 1.35fr;gap:16px}
  .tile{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:20px 22px}
  .tile-label{font-size:13px;color:var(--ink2);font-weight:500}
  .tile-val{font-size:44px;font-weight:700;letter-spacing:-.03em;line-height:1.05;margin:6px 0 2px;font-variant-numeric:tabular-nums}
  .tile-val.alert{color:var(--alert)}
  .tile-sub{font-family:var(--mono);font-size:11.5px;color:var(--ink3)}
  .tile-top{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
  .tile-cap{font-family:var(--mono);font-size:10.5px;color:var(--ink3);text-transform:uppercase;letter-spacing:.06em}
  .rate-rows{display:flex;flex-direction:column;gap:7px;margin-top:8px}
  .rrow{display:flex;align-items:center;gap:10px}
  .rrow-badge{width:26px;display:flex;align-items:center;justify-content:center;flex:none}
  .rrow-bar{flex:1;height:5px;border-radius:3px;background:var(--line);overflow:hidden}
  .rrow-fill{display:block;height:100%;border-radius:3px;background:var(--accent)}
  .rrow-v{font-family:var(--mono);font-size:11px;color:var(--ink2);width:46px;text-align:right;font-variant-numeric:tabular-nums}
  .spark-wrap{position:relative;margin:12px 0 4px;outline:none;cursor:crosshair;border-radius:6px}
  .spark-wrap:focus-visible{box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .spark-wrap svg{display:block;width:100%;height:46px}
  .spark-dot{position:absolute;width:8px;height:8px;border-radius:50%;background:var(--accent);border:2px solid var(--panel);transform:translate(-50%,-50%);pointer-events:none}
  .spark-x{position:absolute;top:0;bottom:0;width:1px;background:var(--ink3);opacity:0;pointer-events:none;transition:opacity .12s}
  .spark-tip{position:absolute;bottom:calc(100% + 7px);transform:translateX(-50%);opacity:0;pointer-events:none;white-space:nowrap;font-family:var(--mono);font-size:11px;color:var(--bg);background:var(--ink);padding:4px 9px;border-radius:6px;z-index:30;transition:opacity .12s}
  .spark-tip b{font-weight:700}
  .rate-flex{display:flex;align-items:center;justify-content:flex-end;gap:10px}
  .rate-spark svg{display:block;width:84px;height:26px}
  .subnote{display:flex;gap:22px;margin-top:-12px;font-family:var(--mono);font-size:11.5px;color:var(--ink3);align-items:center;flex-wrap:wrap}
  .subnote b{color:var(--ink2);font-weight:700}
  .subnote .div{width:1px;height:11px;background:var(--line)}

  /* needs-input band */
  .band{border:1px solid color-mix(in oklab,var(--alert) 42%,var(--line));background:color-mix(in oklab,var(--alert) 7%,var(--panel));border-radius:20px;padding:20px 24px;display:flex;flex-direction:column;gap:16px}
  .band-head{display:flex;align-items:center;gap:9px}
  .band-dot{width:8px;height:8px;border-radius:50%;background:var(--alert);animation:pulse 1.1s infinite}
  .band-k{font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--alert)}
  .need{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}
  .need-meta{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-family:var(--mono);font-size:12px;color:var(--ink3)}
  .need-title{font-size:19px;font-weight:600;line-height:1.3;letter-spacing:-.01em}
  .need-detail{font-size:13px;color:var(--ink2);margin-top:5px}
  .blocked-k{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink3);text-align:right}
  .blocked-v{font-family:var(--mono);font-size:24px;font-weight:700;color:var(--alert);line-height:1.1;text-align:right}

  /* section head */
  .sec{display:flex;align-items:center;gap:10px}
  .sec-k{font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--ink2)}
  .sec-count{font-family:var(--mono);font-size:11px;color:var(--ink3)}
  .sec-rule{flex:1;height:1px;background:var(--line)}
  .stack{display:flex;flex-direction:column;gap:14px}

  /* working card */
  .card{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:22px 24px;display:flex;flex-direction:column;gap:15px}
  .card-top{display:flex;align-items:flex-start;gap:16px}
  .card-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:11px}
  .card-headrow{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
  .pill{display:inline-flex;align-items:center;gap:7px;padding:4px 11px 4px 9px;border-radius:999px;font-size:12px;font-weight:600}
  .pill-work{background:color-mix(in oklab,var(--accent) 18%,transparent);color:var(--ink)}
  .pill-dot{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 1.5s infinite}
  .card-title{font-size:20px;font-weight:600;line-height:1.25;letter-spacing:-.012em}
  .card-meta{font-family:var(--mono);font-size:12.5px;color:var(--ink3)}
  .card-bits{font-family:var(--mono);font-size:11.5px;color:var(--ink2);margin-top:-4px}
  .rate-meter{text-align:right;flex:none}
  .rate-num{font-family:var(--mono);font-size:23px;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums;line-height:1}
  .rate-lab{font-family:var(--mono);font-size:10px;color:var(--ink3);text-transform:uppercase;letter-spacing:.08em;margin-top:3px}
  .rate-track{margin-top:8px;width:100px;height:4px;border-radius:2px;background:var(--line);overflow:hidden;margin-left:auto;position:relative}
  .rate-live{position:absolute;top:0;bottom:0;width:34%;background:var(--accent);border-radius:2px;animation:livebar 2.4s linear infinite}
  .now{font-size:13.5px;color:var(--ink2)}
  .now-k{font-family:var(--mono);font-size:11px;color:var(--ink3);text-transform:uppercase;letter-spacing:.08em;margin-right:9px}
  .turn{display:flex;flex-direction:column;gap:9px}
  .turn-row{display:flex;align-items:center;justify-content:space-between;gap:12px}
  .turn-txt{font-family:var(--mono);font-size:12px;color:var(--ink2)}
  .turn-right{display:flex;align-items:center;gap:9px}
  .pct{font-family:var(--mono);font-size:14px;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums}
  .turnbar{height:9px;border-radius:5px;background:var(--line);overflow:hidden}
  .turnfill{display:block;height:100%;border-radius:5px;background:var(--accent)}
  .lwarn{position:relative;display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;border-radius:50%;background:color-mix(in oklab,var(--alert) 18%,transparent);color:var(--alert);font-family:var(--mono);font-weight:700;font-size:12px;cursor:help;outline:none}
  .lwarn:focus-visible{box-shadow:0 0 0 2px color-mix(in oklab,var(--alert) 45%,transparent)}
  .lwarn .ltip{position:absolute;bottom:calc(100% + 8px);right:-6px;width:max-content;max-width:250px;white-space:normal;text-align:left;opacity:0;pointer-events:none;transform:translateY(3px);transition:opacity .14s ease,transform .14s ease;font-family:var(--mono);font-size:11px;font-weight:500;line-height:1.5;color:var(--bg);background:var(--ink);padding:7px 10px;border-radius:8px;box-shadow:0 6px 18px -6px rgba(0,0,0,.5);z-index:40}
  .lwarn:hover .ltip,.lwarn:focus-visible .ltip{opacity:1;transform:translateY(0);transition-delay:.2s}
  .subs{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
  .subs-k{font-family:var(--mono);font-size:10.5px;color:var(--ink3);text-transform:uppercase;letter-spacing:.08em}
  .subpill{display:inline-flex;align-items:center;gap:7px;padding:4px 12px;border-radius:999px;background:color-mix(in oklab,var(--accent) 13%,transparent);border:1px solid color-mix(in oklab,var(--accent) 30%,transparent);font-size:12px;color:var(--ink)}
  .subdot{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:pulse 1.6s infinite}
  .no-tasks{font-family:var(--mono);font-size:11.5px;color:var(--ink3);border-top:1px solid var(--line);padding-top:13px}
  .tasks{display:flex;flex-direction:column;border-top:1px solid var(--line)}
  .task{display:flex;align-items:flex-start;gap:12px;padding:11px 0;border-bottom:1px solid var(--line)}
  .task:last-child{border-bottom:none;padding-bottom:0}
  .task-body{flex:1;min-width:0}
  .task-subj{font-size:14px;font-weight:520}
  .task-af{font-family:var(--mono);font-size:11.5px;color:var(--ink3);margin-top:2px}
  .task-when{font-family:var(--mono);font-size:11px;color:var(--ink3);white-space:nowrap;text-align:right}
  .tstatus{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap}
  .tstatus::before{content:"";width:6px;height:6px;border-radius:50%}
  .st-in_progress{background:color-mix(in oklab,var(--accent) 18%,transparent);color:var(--ink)}
  .st-in_progress::before{background:var(--accent);animation:pulse 1.5s infinite}
  .st-completed{background:color-mix(in oklab,var(--ink3) 18%,transparent);color:var(--ink2)}
  .st-completed::before{background:var(--ink3)}
  .st-pending{background:color-mix(in oklab,var(--ink3) 12%,transparent);color:var(--ink3)}
  .st-pending::before{background:var(--ink3)}

  /* idle */
  .idle-wrap{position:relative}
  .idle-clip{position:relative;overflow:hidden;transition:max-height .5s cubic-bezier(.4,0,.2,1)}
  .idle-row{display:flex;align-items:center;gap:14px;padding:13px 4px;border-bottom:1px solid var(--line)}
  .idle-dot{width:6px;height:6px;border-radius:50%;background:var(--ink3);flex:none;opacity:.6}
  .idle-title{font-weight:500;font-size:14px;color:var(--ink);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .idle-proj{font-family:var(--mono);font-size:12px;color:var(--ink3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:240px}
  .idle-age{font-family:var(--mono);font-size:12px;color:var(--ink3);white-space:nowrap;width:74px;text-align:right;flex:none}
  .idle-fade{position:absolute;left:0;right:0;bottom:0;height:110px;background:linear-gradient(to bottom,transparent,var(--bg));pointer-events:none}
  .idle-toggle-wrap{display:flex;justify-content:center;margin-top:-16px;position:relative;z-index:2}
  .idle-toggle{font-family:var(--mono);font-size:11.5px;font-weight:700;letter-spacing:.04em;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:9px 20px;cursor:pointer;box-shadow:0 4px 14px -4px rgba(0,0,0,.25);transition:background .15s}
  .idle-toggle:hover{background:var(--line)}

  .empty{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:36px;text-align:center;color:var(--ink2);font-size:14px}
  .empty a{font-weight:600}
</style>
</head>
<body>
<div class="wrap" id="app">
  <div class="empty">Loading…</div>
</div>
<script>
const qs = new URLSearchParams(location.search);
const showAll = qs.get("all") === "1";
let idleExpanded = false;
let lastData = null;
let refreshSequence = 0;
let latestSettledRefresh = 0;

const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function fmtDur(sec){
  if(sec == null || sec < 0) return "–";
  sec = Math.floor(sec);
  if(sec < 60) return sec + "s";
  if(sec < 3600) return Math.floor(sec/60) + "m";
  if(sec < 86400) return Math.floor(sec/3600) + "h " + Math.floor((sec%3600)/60) + "m";
  return Math.floor(sec/86400) + "d " + Math.floor((sec%86400)/3600) + "h";
}

// Trailing output-rate sparklines: client-side ring buffers that start when
// the page opens and drop points once they age out of the visual window.
// Points are stamped with the VIEWER's clock at receipt — the axis and the
// tooltip timestamps must agree with the user's watch, and the server's
// `generated` value can lag (2.5s response memoization) or skew. `generated`
// is used only to drop replayed/memoized payloads.
const SPARK_WINDOW_SEC = 300;
const nowSec = () => Date.now() / 1000;
const rateHistory = [];               // overall: [{t, v}]
const sessRateHistory = new Map();    // "harness:sid" -> [{t, v}]
const sessKey = x => x.harness + ":" + (x.sid || x.session);
let lastGenerated = 0;

function pushPoint(arr, t, v){
  if(arr.length && arr[arr.length-1].t >= t) return; // non-advancing clock
  arr.push({t, v});
  const cutoff = t - SPARK_WINDOW_SEC;
  while(arr.length && arr[0].t < cutoff) arr.shift();
}

function recordRates(d){
  if(typeof d.generated !== 'number' || !isFinite(d.generated)) return;
  if(d.generated <= lastGenerated) return; // memoized/replayed payload
  lastGenerated = d.generated;
  const t = nowSec();
  pushPoint(rateHistory, t, d.summary.rate_per_min || 0);
  const seen = new Set();
  for(const x of d.sessions){
    const key = sessKey(x);
    seen.add(key);
    let arr = sessRateHistory.get(key);
    if(!arr) sessRateHistory.set(key, arr = []);
    pushPoint(arr, t, x.rate_per_min || 0);
  }
  // Remove entries for departed sessions AND aged-out orphaned buffers (no updates in 600s).
  // This ensures memory doesn't leak if a session disappears before the next recordRates() call.
  for(const [k, arr] of sessRateHistory){
    if(!seen.has(k) || (arr.length && arr[arr.length-1].t < t - 600)){
      sessRateHistory.delete(k);
    }
  }
}

const SPARK_PAD = 3;
const sparkX = (t, now, w) => {
  if(!isFinite(t) || !isFinite(now) || !isFinite(w) || SPARK_WINDOW_SEC <= 0) return 0;
  return w - SPARK_PAD - (now - t) * (w - 2*SPARK_PAD) / SPARK_WINDOW_SEC;
};
const sparkY = (v, max, h) => {
  if(!isFinite(v) || !isFinite(max) || !isFinite(h) || max <= 0) return h - SPARK_PAD;
  return h - SPARK_PAD - (v / max) * (h - 2*SPARK_PAD);
};

function sparkSVG(pts, now, w, h, stretch){
  if(!isFinite(w) || !isFinite(h) || !isFinite(now) || w <= 0 || h <= 0) return "";
  const base = h - SPARK_PAD;
  let marks = "";
  if(pts && pts.length > 1){
    const max = Math.max(1, ...pts.map(p => p.v));
    if(!isFinite(max)) return ""; // Guard against NaN from points
    const xy = pts.map(p => {
      const x = sparkX(p.t, now, w);
      const y = sparkY(p.v, max, h);
      return [isFinite(x) ? x : 0, isFinite(y) ? y : h/2]; // Default to safe values if NaN
    });
    const pathPts = xy.map(c => c[0].toFixed(2) + "," + c[1].toFixed(2));
    const area = "M" + xy[0][0].toFixed(2) + "," + base + " L" + pathPts.join(" L") +
      " L" + xy[xy.length-1][0].toFixed(2) + "," + base + " Z";
    marks = `<path d="${area}" fill="var(--accent)" fill-opacity=".12"/>` +
      `<polyline points="${pathPts.join(" ")}" fill="none"` +
      ` stroke="color-mix(in oklab,var(--accent) 72%,var(--ink3))" stroke-width="2"` +
      ` stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`;
    if(!stretch){
      const e = xy[xy.length-1];
      marks += `<circle cx="${e[0].toFixed(2)}" cy="${e[1].toFixed(2)}" r="3.5"` +
        ` fill="var(--accent)" stroke="var(--panel)" stroke-width="2"/>`;
    }
  }
  return `<svg viewBox="0 0 ${w} ${h}"${stretch ? ' preserveAspectRatio="none"' : ""} aria-hidden="true">` +
    `<line x1="0" y1="${base}" x2="${w}" y2="${base}" stroke="var(--line)" stroke-width="1"` +
    ` vector-effect="non-scaling-stroke"/>${marks}</svg>`;
}

function heroSpark(){
  // Stretched viewBox (0..100 units) so the HTML end-dot and crosshair can
  // share the same coordinates as percentages of the wrap's width and height.
  // The axis anchors to the viewer's clock — the same clock the points are
  // stamped with — so hover timestamps never drift from wall time.
  const axisNow = nowSec();
  let dot = "";
  if(rateHistory.length > 1){
    const max = Math.max(1, ...rateHistory.map(p => p.v));
    const last = rateHistory[rateHistory.length-1];
    const dotX = sparkX(last.t, axisNow, 100);
    const dotY = sparkY(last.v, max, 100); // Use 100 to get percentage coordinates (0-100%)
    dot = `<span class="spark-dot" style="left:${dotX.toFixed(2)}%;` +
      `top:${dotY.toFixed(2)}%"></span>`;
  }
  const lastV = rateHistory.length ? rateHistory[rateHistory.length-1].v : null;
  const nowLabel = lastV == null ? "" :
    `, now ${lastV.toLocaleString()} tokens per minute`;
  return `<div class="spark-wrap" id="spark-main" tabindex="0" data-now="${axisNow}"` +
    ` role="img" aria-label="output rate, trailing 5 minutes${nowLabel}">` +
    sparkSVG(rateHistory, axisNow, 100, 46, true) + dot +
    `<span class="spark-x" id="spark-x"></span><span class="spark-tip" id="spark-tip"></span></div>`;
}

function hideSparkHover(){
  if(sparkHoverCache && sparkHoverCache.xline) sparkHoverCache.xline.style.opacity = 0;
  if(sparkHoverCache && sparkHoverCache.tip) sparkHoverCache.tip.style.opacity = 0;
}

// Cache DOM nodes and child elements for efficient hover updates.
let sparkHoverCache = null;
function initSparkHoverCache(){
  sparkHoverCache = {
    xline: document.getElementById("spark-x"),
    tip: document.getElementById("spark-tip"),
    tipVal: null,
    tipTime: null
  };
  if(sparkHoverCache.tip){
    // Create tip children once and reuse them.
    sparkHoverCache.tipVal = document.createElement("b");
    sparkHoverCache.tipTime = document.createTextNode("");
    sparkHoverCache.tip.appendChild(sparkHoverCache.tipVal);
    sparkHoverCache.tip.appendChild(sparkHoverCache.tipTime);
  }
  return sparkHoverCache;
}

function showSparkHover(frac){
  const wrap = document.getElementById("spark-main");
  if(!wrap || rateHistory.length < 2) return;
  const now = parseFloat(wrap.dataset.now);
  if(typeof now !== 'number' || !isFinite(now)) return;
  const t = now - (1 - Math.min(1, Math.max(0, frac))) * SPARK_WINDOW_SEC;
  let best = rateHistory[0];
  for(const p of rateHistory) if(Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
  if(!isFinite(best.v) || !isFinite(best.t)) return;
  const x = sparkX(best.t, now, 100);
  if(!isFinite(x)) return;

  // Use cached DOM nodes instead of recreating on every move event.
  let cache = sparkHoverCache;
  if(!cache || !cache.xline || !cache.xline.parentElement){
    cache = initSparkHoverCache();
  }
  if(!cache.xline || !cache.tip || !cache.tipVal || !cache.tipTime) return;

  cache.xline.style.left = x.toFixed(2) + "%";
  cache.xline.style.opacity = 1;
  cache.tip.style.left = Math.min(88, Math.max(12, x)).toFixed(2) + "%";
  // Update cached tip content instead of recreating DOM.
  cache.tipVal.textContent = best.v.toLocaleString();
  cache.tipTime.textContent = " tok/min · " + new Date(best.t * 1000).toLocaleTimeString();
  cache.tip.style.opacity = 1;
}

let sparkPointer = null; // last pointer position while over the sparkline
let renderInProgress = false; // prevent race between DOM updates and event handlers

document.addEventListener("pointermove", e => {
  if(renderInProgress) return; // Skip updates during render
  const wrap = e.target.closest ? e.target.closest("#spark-main") : null;
  if(!wrap){ sparkPointer = null; hideSparkHover(); return; }
  sparkPointer = {x: e.clientX, y: e.clientY};
  const r = wrap.getBoundingClientRect();
  showSparkHover((e.clientX - r.left) / Math.max(1, r.width));
});
document.addEventListener("focusin", e => {
  if(e.target && e.target.id === "spark-main") showSparkHover(1);
});
document.addEventListener("focusout", e => {
  if(e.target && e.target.id === "spark-main") hideSparkHover();
});

// The pointer can leave the page without a final in-document pointermove
// (window-edge exit, alt-tab, tab switch). Clear the saved position on those
// paths, or restoreSparkState() resurrects the tooltip for a pointer that is
// gone on every subsequent poll.
function clearSparkPointer(){ sparkPointer = null; hideSparkHover(); }
document.addEventListener("mouseout", e => { if(!e.relatedTarget) clearSparkPointer(); });
window.addEventListener("blur", clearSparkPointer);
document.addEventListener("visibilitychange", () => { if(document.hidden) clearSparkPointer(); });

// render() replaces #app wholesale, which kills the sparkline's focus and
// resets its hover layer; re-apply both against the freshly built DOM.
function restoreSparkState(hadFocus, savedPointer){
  // Invalidate the hover cache since the DOM was replaced.
  sparkHoverCache = null;

  const wrap = document.getElementById("spark-main");
  if(!wrap) return;
  if(hadFocus){ wrap.focus({preventScroll: true}); return; } // focusin re-shows tip

  // Restore hover state based on saved pointer position (captured before render).
  if(!savedPointer) return;
  const r = wrap.getBoundingClientRect();
  if(savedPointer.x >= r.left && savedPointer.x <= r.right &&
     savedPointer.y >= r.top && savedPointer.y <= r.bottom){
    showSparkHover((savedPointer.x - r.left) / Math.max(1, r.width));
  }
}

const ICON_PATH = {
  claude: "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z",
  codex: "M8.086.457a6.105 6.105 0 013.046-.415c1.333.153 2.521.72 3.564 1.7a.117.117 0 00.107.029c1.408-.346 2.762-.224 4.061.366l.063.03.154.076c1.357.703 2.33 1.77 2.918 3.198.278.679.418 1.388.421 2.126a5.655 5.655 0 01-.18 1.631.167.167 0 00.04.155 5.982 5.982 0 011.578 2.891c.385 1.901-.01 3.615-1.183 5.14l-.182.22a6.063 6.063 0 01-2.934 1.851.162.162 0 00-.108.102c-.255.736-.511 1.364-.987 1.992-1.199 1.582-2.962 2.462-4.948 2.451-1.583-.008-2.986-.587-4.21-1.736a.145.145 0 00-.14-.032c-.518.167-1.04.191-1.604.185a5.924 5.924 0 01-2.595-.622 6.058 6.058 0 01-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74 7.74 0 01-.495-1.283 6.11 6.11 0 01-.017-3.064.166.166 0 00.008-.074.115.115 0 00-.037-.064 5.958 5.958 0 01-1.38-2.202 5.196 5.196 0 01-.333-1.589 6.915 6.915 0 01.188-2.132c.45-1.484 1.309-2.648 2.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129 0 00.087-.087A6.016 6.016 0 015.635 2.31C6.315 1.464 7.132.846 8.086.457zm-.804 7.85a.848.848 0 00-1.473.842l1.694 2.965-1.688 2.848a.849.849 0 001.46.864l1.94-3.272a.849.849 0 00.007-.854l-1.94-3.393zm5.446 6.24a.849.849 0 000 1.695h4.848a.849.849 0 000-1.696h-4.848z",
  gemini: "M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z",
  copilot: "M19.245 5.364c1.322 1.36 1.877 3.216 2.11 5.817.622 0 1.2.135 1.592.654l.73.964c.21.278.323.61.323.955v2.62c0 .339-.173.669-.453.868C20.239 19.602 16.157 21.5 12 21.5c-4.6 0-9.205-2.583-11.547-4.258-.28-.2-.452-.53-.453-.868v-2.62c0-.345.113-.679.321-.956l.73-.963c.392-.517.974-.654 1.593-.654l.029-.297c.25-2.446.81-4.213 2.082-5.52 2.461-2.54 5.71-2.851 7.146-2.864h.198c1.436.013 4.685.323 7.146 2.864zm-7.244 4.328c-.284 0-.613.016-.962.05-.123.447-.305.85-.57 1.108-1.05 1.023-2.316 1.18-2.994 1.18-.638 0-1.306-.13-1.851-.464-.516.165-1.012.403-1.044.996a65.882 65.882 0 00-.063 2.884l-.002.48c-.002.563-.005 1.126-.013 1.69.002.326.204.63.51.765 2.482 1.102 4.83 1.657 6.99 1.657 2.156 0 4.504-.555 6.985-1.657a.854.854 0 00.51-.766c.03-1.682.006-3.372-.076-5.053-.031-.596-.528-.83-1.046-.996-.546.333-1.212.464-1.85.464-.677 0-1.942-.157-2.993-1.18-.266-.258-.447-.661-.57-1.108-.32-.032-.64-.049-.96-.05zm-2.525 4.013c.539 0 .976.426.976.95v1.753c0 .525-.437.95-.976.95a.964.964 0 01-.976-.95v-1.752c0-.525.437-.951.976-.951zm5 0c.539 0 .976.426.976.95v1.753c0 .525-.437.95-.976.95a.964.964 0 01-.976-.95v-1.752c0-.525.437-.951.976-.951zM7.635 5.087c-1.05.102-1.935.438-2.385.906-.975 1.037-.765 3.668-.21 4.224.405.394 1.17.657 1.995.657h.09c.649-.013 1.785-.176 2.73-1.11.435-.41.705-1.433.675-2.47-.03-.834-.27-1.52-.63-1.813-.39-.336-1.275-.482-2.265-.394zm6.465.394c-.36.292-.6.98-.63 1.813-.03 1.037.24 2.06.675 2.47.968.957 2.136 1.104 2.776 1.11h.044c.825 0 1.59-.263 1.995-.657.555-.556.765-3.187-.21-4.224-.45-.468-1.335-.804-2.385-.906-.99-.088-1.875.058-2.265.394zM12 7.615c-.24 0-.525.015-.84.044.03.16.045.336.06.526l-.001.159a2.94 2.94 0 01-.014.25c.225-.022.425-.027.612-.028h.366c.187 0 .387.006.612.028-.015-.146-.015-.277-.015-.409.015-.19.03-.365.06-.526a9.29 9.29 0 00-.84-.044z",
  opencode: "M16 6H8v12h8V6zm4 16H4V2h16v20z",
  cursor: "M22.106 5.68L12.5.135a.998.998 0 00-.998 0L1.893 5.68a.84.84 0 00-.419.726v11.186c0 .3.16.577.42.727l9.607 5.547a.999.999 0 00.998 0l9.608-5.547a.84.84 0 00.42-.727V6.407a.84.84 0 00-.42-.726zm-.603 1.176L12.228 22.92c-.063.108-.228.064-.228-.061V12.34a.59.59 0 00-.295-.51l-9.11-5.26c-.107-.062-.063-.228.062-.228h18.55c.264 0 .428.286.296.514z",
  goose: "M21.595 23.61c1.167-.254 2.405-.944 2.405-.944l-2.167-1.784a12.124 12.124 0 01-2.695-3.131 12.127 12.127 0 00-3.97-4.049l-.794-.462a1.115 1.115 0 01-.488-.815.844.844 0 01.154-.575c.413-.582 2.548-3.115 2.94-3.44.503-.416 1.065-.762 1.586-1.159.074-.056.148-.112.221-.17.003-.002.007-.004.009-.007.167-.131.325-.272.45-.438.453-.524.563-.988.59-1.193-.061-.197-.244-.639-.753-1.148.319.02.705.272 1.056.569.235-.376.481-.773.727-1.171.165-.266-.08-.465-.086-.471h-.001V3.22c-.007-.007-.206-.25-.471-.086-.567.35-1.134.702-1.639 1.021 0 0-.597-.012-1.305.599a2.464 2.464 0 00-.438.45l-.007.009c-.058.072-.114.147-.17.221-.397.521-.743 1.083-1.16 1.587-.323.391-2.857 2.526-3.44 2.94a.842.842 0 01-.574.153 1.115 1.115 0 01-.815-.488l-.462-.794a12.123 12.123 0 00-4.049-3.97 12.133 12.133 0 01-3.13-2.695L1.332 0S.643 1.238.39 2.405c.352.428 1.27 1.49 2.34 2.302C1.58 4.167.73 3.75.06 3.4c-.103.765-.063 1.92.043 2.816.726.317 1.961.806 3.219 1.066-1.006.236-2.11.278-2.961.262.15.554.358 1.119.64 1.688.119.263.25.52.39.77.452.125 2.222.383 3.164.171l-2.51.897a27.776 27.776 0 002.544 2.726c2.031-1.092 2.494-1.241 4.018-2.238-2.467 2.008-3.108 2.828-3.8 3.67l-.483.678c-.25.351-.469.725-.65 1.117-.61 1.31-1.47 4.1-1.47 4.1-.154.486.202.842.674.674 0 0 2.79-.861 4.1-1.47.392-.182.766-.4 1.118-.65l.677-.483c.227-.187.453-.37.701-.586 0 0 1.705 2.02 3.458 3.349l.896-2.511c-.211.942.046 2.712.17 3.163.252.142.509.272.772.392.569.28 1.134.49 1.688.64-.016-.853.026-1.956.261-2.962.26 1.258.75 2.493 1.067 3.219.895.106 2.051.146 2.816.043a73.87 73.87 0 01-1.308-2.67c.811 1.07 1.874 1.988 2.302 2.34h-.001z"
};
const iconURI = d => "data:image/svg+xml," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#000"><path d="' + d + '"/></svg>');
const HARNESS = {
  claude:{code:"CL",name:"Claude"}, codex:{code:"CX",name:"Codex"},
  gemini:{code:"GE",name:"Gemini"}, copilot:{code:"CP",name:"Copilot"},
  opencode:{code:"OC",name:"OpenCode"}, cursor:{code:"CU",name:"Cursor"},
  goose:{code:"GO",name:"Goose"}, droid:{code:"DR",name:"Droid"}
};
for(const k in HARNESS){ if(ICON_PATH[k]) HARNESS[k].icon = iconURI(ICON_PATH[k]); }

function badge(key, active, name, tipSuffix){
  const h = HARNESS[key] || {code:(key||"?").slice(0,2).toUpperCase(), name:key};
  const label = name || h.name;
  const tileStyle = active ? "background:var(--ink)" : "border:1px solid var(--line)";
  const on = active ? "var(--bg)" : "var(--ink2)";
  const inner = h.icon
    ? `<span class="bico" style="background:${on};-webkit-mask:url('${h.icon}') center/contain no-repeat;mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="bmono" style="color:${on}">${esc(h.code)}</span>`;
  return `<span class="hbadge"><span class="btile" style="${tileStyle}">${inner}</span>` +
         `<span class="htip">${esc(label)}${esc(tipSuffix || "")}</span></span>`;
}

function harnessStrip(harnesses){
  if(!harnesses || !harnesses.length) return "";
  const chips = harnesses.map(h => {
    const healthy = h.discovered && !h.error;
    const suffix = h.error ? " — collector error" : (h.discovered ? "" : " — no data");
    return badge(h.key, healthy, h.label, suffix);
  }).join("");
  return `<span class="hstrip-k">harnesses</span>${chips}`;
}

function rateTile(d){
  const rate = d.summary.rate_per_min || 0;
  const total = (isFinite(rate) ? rate : 0).toLocaleString();
  const byH = {};
  for(const x of d.sessions){
    if(x.active && x.rate_per_min && isFinite(x.rate_per_min)){
      byH[x.harness] = (byH[x.harness]||0) + x.rate_per_min;
    }
  }
  const shown = (d.harnesses || []).filter(h => h.discovered)
    .map(h => ({key:h.key, v:byH[h.key] || 0}))
    .sort((a,b) => b.v - a.v).slice(0,5);
  const max = Math.max(1, ...shown.map(r => r.v));
  const rows = shown.length ? `<div class="rate-rows">` + shown.map(r => {
    const v = isFinite(r.v) ? r.v : 0;
    const pct = Math.max(v ? 4 : 0, Math.round(v * 100 / max));
    return `<div class="rrow"><span class="rrow-badge">${badge(r.key, true)}</span>` +
      `<span class="rrow-bar"><span class="rrow-fill" style="width:${pct}%"></span></span>` +
      `<span class="rrow-v">${v.toLocaleString()}</span></div>`;
  }).join("") + `</div>` : "";
  return `<div class="tile"><div class="tile-top"><span class="tile-label">Output rate</span>` +
    `<span class="tile-cap">tok / min · 10 min</span></div>` +
    `<div class="tile-val">${total}</div>${heroSpark()}${rows}</div>`;
}

function turnBlock(t){
  if(!t) return "";
  const warn = t.long ? `<span class="lwarn" tabindex="0" role="note"` +
    ` aria-label="This request is running long (or estimated to). Double-check what the agent is doing matches your expectations.">!` +
    `<span class="ltip">This request is running long (or estimated to). Double-check what the agent is doing matches your expectations.</span></span>` : "";
  const pct = (t.pct != null) ? `<span class="pct">${t.pct}%</span>` : "";
  const bar = (t.pct != null) ? `<div class="turnbar"><span class="turnfill" style="width:${t.pct}%"></span></div>` : "";
  const eta = t.eta_h ? `~${esc(t.eta_h)} left (est)` : "running longer than recent turns";
  return `<div class="turn"><div class="turn-row">` +
    `<span class="turn-txt">this request · ${esc(t.elapsed_h)} elapsed · ${eta}</span>` +
    `<span class="turn-right">${warn}${pct}</span></div>${bar}</div>`;
}

function taskBlock(sess){
  if(!sess.tasks || !sess.tasks.length)
    return `<div class="no-tasks">no tracked tasks in this session</div>`;
  const order = {in_progress:0, pending:1, completed:2};
  const STATUS = {in_progress:"In progress", pending:"Pending", completed:"Completed"};
  const tasks = [...sess.tasks].sort((a,b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));
  const rows = tasks.map(t => {
    const af = (t.status === "in_progress" && t.activeForm) ? `<div class="task-af">${esc(t.activeForm)}…</div>` : "";
    return `<div class="task"><span class="tstatus st-${esc(t.status)}">${STATUS[t.status] || esc(t.status)}</span>` +
      `<div class="task-body"><div class="task-subj">${esc(t.subject)}</div>${af}</div>` +
      `<div class="task-when">${esc(t.elapsed_h || "")}<br>${esc(t.updated_ago || "")}</div></div>`;
  }).join("");
  return `<div class="tasks">${rows}</div>`;
}

function workingCard(d, sess){
  const hist = sessRateHistory.get(sessKey(sess));
  const spark = (hist && hist.length > 1)
    ? `<span class="rate-spark" title="${(sess.rate_per_min || 0).toLocaleString()}` +
      ` tok/min · trailing 5 min">` +
      sparkSVG(hist, nowSec(), 84, 26, false) + `</span>`
    : "";
  const rateMeter = (sess.active && sess.rate_per_min)
    ? `<div class="rate-meter"><div class="rate-flex">${spark}` +
      `<div><div class="rate-num">${sess.rate_per_min.toLocaleString()}</div>` +
      `<div class="rate-lab">tok / min</div></div></div>` +
      `<div class="rate-track"><span class="rate-live"></span></div></div>`
    : "";
  const bits = [];
  if(sess.total) bits.push(`${sess.done}/${sess.total} done · ${sess.progress_pct}%`);
  if(sess.eta_h) bits.push(`~${sess.eta_h} left`);
  const bitsLine = bits.length ? `<div class="card-bits">${esc(bits.join(" · "))}</div>` : "";
  const subs = (sess.subagents && sess.subagents.length)
    ? `<div class="subs"><span class="subs-k">subagents</span>` +
      sess.subagents.slice(0,6).map(a => `<span class="subpill"><span class="subdot"></span>${esc(a)}</span>`).join("") +
      (sess.subagents.length > 6 ? `<span class="subs-k">+${sess.subagents.length-6} more</span>` : "") +
      `</div>`
    : "";
  return `<div class="card"><div class="card-top"><div class="card-main">` +
    `<div class="card-headrow"><span class="pill pill-work"><span class="pill-dot"></span>Working</span>` +
    badge(sess.harness, true) + `</div>` +
    `<div class="card-title">${esc(sess.title || sess.project)}</div>` +
    `<div class="card-meta">${esc(sess.project)} · ${esc(sess.session)}</div>${bitsLine}` +
    `</div>${rateMeter}</div>` +
    `<div class="now"><span class="now-k">now</span>${esc(sess.state_detail)}</div>` +
    turnBlock(sess.turn) + subs + taskBlock(sess) + `</div>`;
}

function needRow(d, sess){
  const blocked = fmtDur(d.generated - (sess.blocked_since || sess.last_activity));
  return `<div class="need"><div style="min-width:0">` +
    `<div class="need-meta">${badge(sess.harness, true)}${esc(sess.project)} · ${esc(sess.session)}</div>` +
    `<div class="need-title">${esc(sess.title || sess.last_prompt || sess.project)}</div>` +
    `<div class="need-detail">${esc(sess.state_detail)}</div></div>` +
    `<div style="flex:none"><div class="blocked-k">blocked</div><div class="blocked-v">${esc(blocked)}</div></div></div>`;
}

function idleRow(d, sess){
  const age = fmtDur(d.generated - sess.last_activity);
  const t = sess.total ? ` · ${sess.done}/${sess.total}` : "";
  return `<div class="idle-row"><span class="idle-dot"></span>${badge(sess.harness, false)}` +
    `<span class="idle-title">${esc(sess.title || sess.last_prompt || sess.project)}</span>` +
    `<span class="idle-proj">${esc(sess.project)} · ${esc(sess.session)}${t}</span>` +
    `<span class="idle-age">idle ${esc(age)}</span></div>`;
}

function toggleIdle(){ idleExpanded = !idleExpanded; if(lastData) render(lastData); }

function render(d){
  lastData = d;
  const sparkFocused = !!(document.activeElement && document.activeElement.id === "spark-main");
  // Capture pointer position before render so we can restore it afterward, even if
  // pointermove fires during the render operation.
  const savedPointer = sparkPointer ? {x: sparkPointer.x, y: sparkPointer.y} : null;
  const s = d.summary;
  const needs = d.sessions.filter(x => x.active && x.state === "needs_input");
  const working = d.sessions.filter(x => x.state === "working");
  const idle = d.sessions.filter(x => x.state === "idle");

  const needsVal = needs.length > 0
    ? `<div class="tile-val alert">${needs.length}</div>`
    : `<div class="tile-val">0</div>`;
  const tiles =
    `<div class="tile"><div class="tile-label">Needs you</div>${needsVal}` +
      `<div class="tile-sub">sessions blocked on you</div></div>` +
    `<div class="tile"><div class="tile-label">Working now</div>` +
      `<div class="tile-val">${s.working}</div><div class="tile-sub">sessions generating</div></div>` +
    rateTile(d);

  const subnote = s.total_tasks
    ? `<span>open tasks <b>${s.open_tasks}</b></span><span class="div"></span>` +
      `<span>progress <b>${s.progress_pct}%</b></span><span class="div"></span>` +
      `<span>${s.total_done}/${s.total_tasks} tracked tasks done</span>`
    : `<span>open tasks <b>–</b></span><span class="div"></span>` +
      `<span>progress <b>–</b></span><span class="div"></span>` +
      `<span>no active session uses tracked tasks</span>`;

  const bandHtml = needs.length
    ? `<div class="band"><div class="band-head"><span class="band-dot"></span>` +
      `<span class="band-k">Needs your input</span></div>` +
      needs.map(n => needRow(d, n)).join("") + `</div>`
    : "";

  let workingHtml = "";
  if(working.length){
    workingHtml = `<div class="stack"><div class="sec"><span class="sec-k">Working now</span>` +
      `<span class="sec-count">${working.length}</span><span class="sec-rule"></span></div>` +
      working.map(s => workingCard(d, s)).join("") + `</div>`;
  } else if(d.sessions.length){
    workingHtml = `<div class="stack"><div class="sec"><span class="sec-k">Working now</span>` +
      `<span class="sec-count">0</span><span class="sec-rule"></span></div>` +
      `<div class="empty">No sessions generating right now — every agent is idle or waiting.</div></div>`;
  }

  let idleHtml = "";
  if(idle.length){
    const maxh = idleExpanded ? "3000px" : "184px";
    const fade = idleExpanded ? "" : `<div class="idle-fade"></div>`;
    const rows = idle.map(x => idleRow(d, x)).join("");
    idleHtml = `<div class="stack"><div class="sec"><span class="sec-k">Idle</span>` +
      `<span class="sec-count">${idle.length}</span><span class="sec-rule"></span></div>` +
      `<div class="idle-wrap"><div class="idle-clip" style="max-height:${maxh}">${rows}${fade}</div>` +
      `<div class="idle-toggle-wrap"><button class="idle-toggle" onclick="toggleIdle()">` +
      `${idleExpanded ? "Show less" : "Show all " + idle.length + " idle"}</button></div></div></div>`;
  }

  let body;
  if(!d.sessions.length){
    body = `<div class="empty">No session activity in the last ${esc(d.window_hours)}h.` +
      (d.show_all ? "" : ` <a href="?all=1">Show all sessions</a>`) + `</div>`;
  } else {
    body = `<div class="hero">${tiles}</div><div class="subnote">${subnote}</div>` +
      bandHtml + workingHtml + idleHtml;
  }

  renderInProgress = true;
  document.getElementById("app").innerHTML =
    `<div class="top"><div><div class="brand">Cargento</div>` +
    `<div class="sub"><span class="live" id="live-dot"></span>` +
    `<span id="live-status">live · updated ${new Date(d.generated*1000).toLocaleTimeString()} · auto-refresh 5s</span>` +
    (d.show_all ? " · showing all" : "") + `</div></div>` +
    `<div class="hstrip">${harnessStrip(d.harnesses)}</div></div>` + body;
  renderInProgress = false;

  restoreSparkState(sparkFocused, savedPointer);
  document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
}

async function refresh(){
  const sequence = ++refreshSequence;
  try{
    const r = await fetch("/api/data" + (showAll ? "?all=1" : ""));
    if(!r.ok) throw new Error("bad status");
    const data = await r.json();
    if(sequence < latestSettledRefresh) return;
    latestSettledRefresh = sequence;
    recordRates(data);
    render(data);
    window.__refreshFailures = 0;
  }catch(e){
    if(window.__SAMPLE){ recordRates(window.__SAMPLE); render(window.__SAMPLE); return; }
    if(sequence < latestSettledRefresh) return;
    latestSettledRefresh = sequence;
    console.error("dashboard refresh failed", e);
    window.__refreshFailures = (window.__refreshFailures || 0) + 1;
    const app = document.getElementById("app");
    if(app && !lastData){
      app.innerHTML = `<div class="empty">refresh failed — is the server running?</div>`;
      return;
    }
    if(window.__refreshFailures < 2) return;
    const dot = document.getElementById("live-dot");
    const status = document.getElementById("live-status");
    if(dot) dot.classList.add("stalled");
    if(status){
      const updated = new Date(lastData.generated*1000).toLocaleTimeString();
      status.textContent = `stalled · last update ${updated} · retrying every 5s`;
    }
  }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


# (window_hours, show_all) -> {"ts": epoch, "body": bytes}
_collect_memo: dict[tuple[float, bool], dict[str, Any]] = {}
_collect_memo_lock = threading.Lock()
COLLECT_MEMO_SEC = 2.5  # multiple tabs / curl loops share one scan per window


def collect_json(window_hours: float, show_all: bool) -> bytes:
    key = (window_hours, show_all)
    with _collect_memo_lock:
        cached = _collect_memo.get(key)
        if cached and time.time() - cached["ts"] < COLLECT_MEMO_SEC:
            body: bytes = cached["body"]
            return body
        # Hold the lock through collection: ThreadingHTTPServer callers share
        # one filesystem/SQLite scan rather than stampeding cold cache entries.
        body = json.dumps(collect(window_hours, show_all)).encode()
        _collect_memo[key] = {"ts": time.time(), "body": body}
        return body


class Handler(BaseHTTPRequestHandler):
    window_hours = 24

    # Loopback-origin requests only: the Host check defeats DNS rebinding,
    # the Origin check defeats cross-site fetch()es from web pages (both
    # reach 127.0.0.1-bound servers through the victim's browser).
    LOCAL_HOSTS: ClassVar[set[str]] = {"127.0.0.1", "localhost", "::1", "[::1]"}

    def _local_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in self.LOCAL_HOSTS:
            return False
        if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
            return False
        origin = self.headers.get("Origin")
        return not origin or (urlparse(origin).hostname or "") in self.LOCAL_HOSTS

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._local_ok():
            self.send_error(403)
            return
        url = urlparse(self.path)
        if url.path == "/api/data":
            show_all = parse_qs(url.query).get("all", ["0"])[0] == "1"
            self._send(collect_json(self.window_hours, show_all), "application/json")
        elif url.path == "/":
            self._send(PAGE.encode(), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        # Ingest Claude Code Notification-hook payloads:
        # {"session_id": "...", "message": "...", ...}
        if not self._local_ok():
            self.send_error(403)
            return
        if urlparse(self.path).path != "/api/notify":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= 65536:
            self.send_error(413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        session_id = payload.get("session_id")
        prefix = session_id[:8] if isinstance(session_id, str) else ""
        hook_event_name = payload.get("hook_event_name")
        if isinstance(hook_event_name, str) and hook_event_name.lower() == "sessionend":
            if prefix:
                with _lock:
                    _hook_notifs.pop(prefix, None)
                    _last_state.pop(prefix, None)
            self._send(b'{"ok":true,"cleared":"session_end"}', "application/json")
            return
        raw_message = payload.get("message")
        message = notification_text(
            raw_message
            if isinstance(raw_message, str) and raw_message
            else "Claude is waiting for your input",
            500,
        )
        kind = normalized_notification_type(payload.get("notification_type"))
        needs_input, popup = notification_disposition(kind, message)
        # Subagent sessions also emit Notification-hook events (permission
        # prompts inside agents). They are not user-facing sessions — a popup
        # about them is noise the human cannot act on from the dashboard.
        if prefix and claude_prefix_is_agent(prefix):
            self._send(b'{"ok":true,"suppressed":"subagent"}', "application/json")
            return
        now = time.time()
        hook = {"ts": now, "message": message}
        transcript_path = payload.get("transcript_path")
        if prefix and isinstance(transcript_path, str):
            found, user_event = claude_hook_user_event(transcript_path, prefix)
            if found:
                hook["user_event"] = user_event
        with _lock:
            if prefix:
                clears_input = kind in CLEARING_NOTIFICATION_TYPES or (not kind and not needs_input)
                if clears_input:
                    _hook_notifs.pop(prefix, None)
                    _last_state.pop(prefix, None)
                elif needs_input:
                    bounded_put(_hook_notifs, prefix, hook)
            popup_key = prefix or "_anonymous"
            session_ready = now - _last_popup.get(popup_key, 0) >= POPUP_COOLDOWN_SEC
            global_ready = now - _last_popup.get("_global", 0) >= GLOBAL_POPUP_COOLDOWN_SEC
            # Claude re-emits the same idle/permission notification for as
            # long as the session stays blocked; repeating the popup adds no
            # information. One popup per distinct message per session within
            # POPUP_REPEAT_SUPPRESS_SEC.
            prev_msg, prev_ts = _last_popup_message.get(popup_key, ("", 0.0))
            repeat = message == prev_msg and now - prev_ts < POPUP_REPEAT_SUPPRESS_SEC
            fire = popup and session_ready and global_ready and not repeat
            if fire:
                bounded_put(_last_popup, popup_key, now)
                bounded_put(_last_popup, "_global", now)
                bounded_put(_last_popup_message, popup_key, (message, now))
        if fire:
            notify_mac("Claude is waiting on you", message)
        self._send(b'{"ok":true}', "application/json")

    def log_message(self, *args: Any) -> None:
        pass  # keep stdout quiet


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=4553)
    ap.add_argument(
        "--window-hours",
        type=float,
        default=24,
        help="sessions with no activity in this window are hidden (default 24)",
    )
    args = ap.parse_args()
    Handler.window_hours = args.window_hours
    # Bind to loopback only — this exposes local session data.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Cargento: http://localhost:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
