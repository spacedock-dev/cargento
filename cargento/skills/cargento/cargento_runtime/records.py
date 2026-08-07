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


def iso_epoch(value: Any) -> float | None:
    """One ISO-8601 string as epoch seconds, or nothing. **The repo-wide rule.**

    Every ISO timestamp Cargento reads comes from outside it — a transcript, a
    SQLite column, a vendor's usage endpoint, a hook payload — and the one thing
    they do not agree on is whether the offset is there at all. So the rule is
    stated once, here, and the parsers that need it call this rather than
    `fromisoformat().timestamp()`:

    **An offset-less stamp is UTC.**

    That is a decision about which wrong answer is survivable, and it was made
    against measurement rather than taste (2026-08-06). Every source checked on a
    live machine sends an explicit offset, and every one of them sends `+00:00`:
    Claude and Pi transcript records, Copilot's `assistant_usage_events.created_at`,
    and all four `resets_at` fields on Anthropic's usage endpoint. So a naive stamp
    from any of them would be one of those same UTC values with the suffix dropped,
    and reading it as UTC recovers the right instant.

    `.timestamp()` on a naive datetime does the opposite: it reads the value as
    *server-local*. In UTC+8 that is an eight-hour error in the direction that
    matters most, making a stamp look older than it is — old enough to fall out of
    an activity window and hide a live session, which is the failure this codebase
    treats as the worst kind.

    Display is unaffected and stays local: `sessions.format_reset` and
    `lifecycle` both `.astimezone()` an epoch value for rendering. This function is
    about reading an instant, not about showing one.

    `Z` is normalized because `fromisoformat` rejected it before Python 3.11 and
    the floor is 3.11; keeping the substitution costs nothing and documents the
    spelling vendors actually send.
    """
    if not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def parse_ts(ts: Any) -> float | None:
    """One ISO-8601 record stamp as epoch seconds, or nothing.

    An offset-less stamp is read as **UTC**, which is the repo-wide rule for every
    ISO string arriving from outside (see `iso_epoch`). Without the explicit
    `tzinfo`, `.timestamp()` reads a naive value as *server-local*, so the same
    transcript produced a reading that moved with the reader's timezone — eight
    hours out in UTC+8, which is enough to place a live turn outside the activity
    window and hide the session.
    """
    return iso_epoch(ts)


def parse_utc_sql(value: Any) -> float:
    """One SQL datetime as epoch seconds, or 0.

    SQLite has no timestamp type, so these arrive as text and usually without an
    offset. Same rule as everywhere else: no offset means UTC. The space-for-T
    substitution is what makes `fromisoformat` accept SQLite's own default
    spelling; 0 rather than None because the callers window on this and treat 0 as
    "not in the window".
    """
    return iso_epoch(str(value).replace(" ", "T")) or 0


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


def model_signal(record: dict[str, Any], harness: str, limit: int) -> str | None:
    """The model one transcript record declares, bounded, or nothing.

    Codex re-declares the model at the head of every turn, in a `turn_context`
    record written one to six lines after each `task_started`. The last such
    record a rollout carries is therefore the model the session is running on
    now, which is the only question this answers: it reports a value, not a
    history, so a caller keeps the newest hit and does not compare it to the
    ones before it.

    Gated on the harness for the reason `_turn_signal` is gated: `scan_turns`
    runs this over five harnesses' transcripts, and an ungated read would let
    any of them publish a model out of a record that merely shares a type name.

    Nothing is inferred. A harness with no such record, a payload with no
    `model`, a non-string value, and a string that bounds away to nothing all
    yield None, which every consumer reads as "not measured" rather than as a
    statement about which model ran.
    """
    if harness != "codex" or record.get("type") != "turn_context":
        return None
    value = as_dict(record.get("payload")).get("model")
    if not isinstance(value, str):
        return None
    # Untrusted vendor text on its way to the DOM: bounded here, escaped again
    # at the render site.
    return safe_text(value, limit).strip() or None


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
