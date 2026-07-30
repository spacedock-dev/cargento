"""Pure operations over untrusted harness records."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


def safe_text(value: Any, limit: int) -> str:
    text = str(value or "").encode("utf-8", "replace").decode("utf-8")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return text[:limit]


def parse_ts(ts: Any) -> float | None:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return None


def parse_utc_sql(value: Any) -> float:
    try:
        timestamp = datetime.fromisoformat(str(value).replace(" ", "T"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.timestamp()
    except (ValueError, TypeError):
        return 0


def norm_epoch(value: Any) -> float:
    if not isinstance(value, (int, float)) or value <= 0:
        return 0
    return value / 1000 if value > 1e12 else value


def extract_text(value: Any, depth: int = 0) -> str:
    if depth > 4 or value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = (extract_text(item, depth + 1) for item in value)
        return " ".join(part for part in parts if part)[:2000]
    if isinstance(value, dict):
        for key in ("text", "content", "message", "prompt", "value"):
            if key in value:
                text = extract_text(value[key], depth + 1)
                if text:
                    return text
    return ""


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def message_dict(record: Any) -> dict[str, Any]:
    return as_dict(as_dict(record).get("message"))


def alnum(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def record_fingerprint(record: Any) -> bytes:
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8", "replace"
    )
    return hashlib.blake2b(raw, digest_size=16).digest()


def gemini_records(record: Any) -> tuple[Any, ...]:
    snapshot = record.get("$set")
    messages = snapshot.get("messages") if isinstance(snapshot, dict) else None
    if isinstance(messages, list):
        return tuple(message for message in messages if isinstance(message, dict))
    return (record,)


def incremental_gemini_records(
    record: Any,
    state: dict[str, Any],
) -> tuple[Any, ...]:
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


def _turn_signal(record: dict[str, Any], harness: str) -> tuple[str, Any] | None:
    record_type = record.get("type")
    if harness == "codex":
        if record_type != "event_msg":
            return None
        payload = as_dict(record.get("payload"))
        payload_type = payload.get("type")
        if payload_type == "task_started":
            return ("start", payload.get("started_at"))
        if payload_type in ("task_complete", "turn_aborted"):
            return ("end", None)
        return None
    if harness == "copilot":
        if record_type == "user.message":
            return ("prompt", None)
        if record_type in ("session.task_complete", "session.shutdown", "abort"):
            return ("end", None)
        return None
    if harness == "gemini":
        if record_type != "user":
            return None
        content = record.get("content")
        if isinstance(content, list) and any(
            isinstance(item, dict) and "functionResponse" in item for item in content
        ):
            return None
        return ("prompt", None)
    if harness == "droid":
        if record_type != "message":
            return None
        message = message_dict(record)
        if message.get("role") != "user":
            return None
        content = message.get("content")
        if isinstance(content, list) and any(
            isinstance(item, dict) and item.get("type") == "tool_result" for item in content
        ):
            return None
        return ("prompt", None)
    if record_type != "user" or record.get("isMeta"):
        return None
    content = message_dict(record).get("content")
    if isinstance(content, list) and any(
        isinstance(item, dict) and item.get("type") == "tool_result" for item in content
    ):
        return None
    if isinstance(content, str) and content.lstrip().startswith(
        ("<local-command-stdout>", "<local-command-caveat>")
    ):
        return None
    return ("prompt", None)
