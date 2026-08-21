"""The observer agent: a read-only analyzer that derives goal + stage + block.

Sits beside an active session, reads its transcript and workflow entity dir
read-only, and writes one sidecar (``<harness>_<sid>.observer.json``) the
observer panel renders. The analyzer never mutates the observed session's
repo or state; the sidecar is written to the observer's own store under
``config.state_dir``.

The goal is derived deterministically from the most recent concrete user
directive in the transcript. A session whose only content is a generic
skill-load opener with no assistant output short-circuits to ``"no goal
derived"`` without calling the model — the rule-based sentinel that bounds
the model and prevents fabrication. A model callable may enhance the
derivation; on any failure it degrades to the deterministic fallback, never
to a crash or a hallucination.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, Protocol

from . import io as runtime_io
from . import records, spacedock, transcripts

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import RuntimeConfig
    from .state import RuntimeState

NO_GOAL = "no goal derived"
NO_GOAL_REASON = "generic-opener-only-no-work"

# Generic skill-load directives that carry no goal by themselves. Measured
# against real Pi session transcripts: the opening line is a harness-injected
# wrapper, not a user objective.
_GENERIC_OPENER_PREFIXES = (
    "use $",
    "skill(",
)

# Block indicators scanned for in recent assistant text. The MVP derives one
# open block; the scan is a bounded keyword search, not a semantic parse.
_BLOCK_INDICATORS = (
    "blocked",
    "cannot",
    "can't",
    "unable",
    "stuck",
    "waiting for",
    "failed to",
    "error:",
    "not permitted",
)


class ModelCaller(Protocol):
    """A cheap model invocation that derives a goal line, or None on failure.

    The callable receives the transcript head text and an entity-context
    string and returns a bounded goal line, or None if it cannot produce
    one. None is the only failure signal: the analyzer degrades to the
    deterministic fallback rather than raising.
    """

    def __call__(self, transcript_head: str, entity_context: str) -> str | None: ...


def _is_generic_opener(text: str) -> bool:
    """Whether a user message is a generic skill-load directive, not a goal."""
    stripped = text.strip().lower()
    return any(stripped.startswith(prefix) for prefix in _GENERIC_OPENER_PREFIXES)


def _parse_message_record(record: Any) -> dict[str, str] | None:
    """One (role, text) pair from a JSONL message record, or None.

    Guards every field the way the collectors guard theirs: untyped JSON
    from disk. Skips tool results (a user turn whose content is a tool_result
    is a system echo, not a directive) and records with no text.
    """
    if not isinstance(record, dict) or record.get("type") != "message":
        return None
    message = records.message_dict(record)
    role = message.get("role")
    if role not in ("user", "assistant"):
        return None
    content = message.get("content")
    if isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    ):
        return None
    text = records.extract_text(content).strip()
    if not text:
        return None
    return {"role": role, "text": text}


def _extract_messages(config: RuntimeConfig, path: str) -> list[dict[str, str]]:
    """User and assistant texts from a JSONL transcript, head + tail bounded.

    The head carries the opening directive; the tail carries the recent
    window. Records are deduped by id so the overlap region between head and
    tail does not double-count.
    """
    messages: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        head = runtime_io.read_prefix_bytes(path, max_bytes=config.observer_head_bytes)
    except OSError:
        head = b""
    head_lines = head.decode("utf-8", "replace").split("\n")
    tail_lines = runtime_io.read_tail(config, path)
    for raw in head_lines + tail_lines:
        if not raw or not raw.lstrip().startswith("{"):
            continue
        try:
            record = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            continue
        parsed = _parse_message_record(record)
        if parsed is None:
            continue
        entry_id = record.get("id") if isinstance(record, dict) else None
        key = entry_id if isinstance(entry_id, str) and entry_id else parsed["text"]
        if key in seen:
            continue
        seen.add(key)
        messages.append(parsed)
    return messages


def _user_directives(messages: list[dict[str, str]]) -> list[str]:
    """Concrete user directives, excluding generic openers, newest last."""
    return [
        msg["text"]
        for msg in messages
        if msg["role"] == "user" and not _is_generic_opener(msg["text"])
    ]


def _has_assistant_output(messages: list[dict[str, str]]) -> bool:
    return any(msg["role"] == "assistant" for msg in messages)


def _derive_goal_deterministic(
    config: RuntimeConfig,
    messages: list[dict[str, str]],
) -> tuple[str, str | None]:
    """A goal line from the most recent concrete directive, or the sentinel.

    Returns (goal, reason). The reason is ``NO_GOAL_REASON`` when the
    short-circuit fires, None otherwise. The short-circuit is the
    deterministic fallback that bounds the model: when the only user
    message is a generic opener and no assistant text was produced, the
    analyzer returns the sentinel without calling the model.
    """
    directives = _user_directives(messages)
    if not directives and not _has_assistant_output(messages):
        return NO_GOAL, NO_GOAL_REASON
    if not directives:
        # Assistant work exists but no concrete directive was found: the
        # goal is unknown, not fabricated.
        return NO_GOAL, None
    goal = directives[-1].split("\n")[0].strip()
    return records.safe_text(goal, config.observer_goal_cap_chars), None


def _derive_stage(
    config: RuntimeConfig,
    state: RuntimeState,
    entity_dir: str | None,
) -> str:
    """The current stage from the entity dir's newest file, or empty.

    Reuses the read-only frontmatter reader the Spacedock cartography already
    proved safe. No file under the entity dir is written; only the
    ``status`` scalar leaves this function.
    """
    if not entity_dir:
        return ""
    files = spacedock.entity_files(config, entity_dir)
    if not files:
        return ""
    _slug, path, info = files[0]
    return spacedock.entity_stage(config, state, path, info)


def _derive_block(
    config: RuntimeConfig,
    messages: list[dict[str, str]],
) -> str:
    """One open block from recent assistant text, or empty.

    A bounded keyword scan: the last assistant message whose text contains a
    block indicator contributes the sentence around the first hit. Nothing
    is inferred; a message without an indicator yields no block.
    """
    for msg in reversed(messages):
        if msg["role"] != "assistant":
            continue
        text = msg["text"]
        lower = text.lower()
        for indicator in _BLOCK_INDICATORS:
            pos = lower.find(indicator)
            if pos < 0:
                continue
            # Extract the sentence around the indicator.
            start = text.rfind(". ", 0, pos)
            start = start + 2 if start >= 0 else 0
            end = text.find(". ", pos)
            end = end + 1 if end >= 0 else len(text)
            sentence = text[start:end].strip()
            if sentence:
                return records.safe_text(sentence, config.observer_block_cap_chars)
    return ""


def analyze(
    config: RuntimeConfig,
    state: RuntimeState,
    transcript_path: str,
    *,
    entity_dir: str | None = None,
    model: ModelCaller | Callable[[str, str], str | None] | None = None,
) -> dict[str, Any]:
    """Derive goal + stage + block from a session transcript, read-only.

    Returns ``{"goal": str, "stage": str, "block": str, "reason": str | None}``.
    The goal is either a derived goal line or the literal ``"no goal derived"``
    sentinel. The stage comes from the entity dir's frontmatter ``status``.
    The block is one sentence from recent assistant text containing a block
    indicator, or empty.

    The model callable is optional. When provided and the deterministic
    short-circuit does not fire, the model may enhance the goal; on any
    failure (returning None) the deterministic goal is kept. The
    short-circuit always bypasses the model.
    """
    messages = _extract_messages(config, transcript_path)
    goal, reason = _derive_goal_deterministic(config, messages)

    # The short-circuit bypasses the model entirely: a no-goal session must
    # never produce a fabricated goal, regardless of what the model says.
    if goal != NO_GOAL and model is not None:
        head_text = " ".join(msg["text"] for msg in messages[-20:])
        entity_context = _derive_stage(config, state, entity_dir)
        try:
            enhanced = model(head_text, entity_context)
        except Exception:  # noqa: BLE001 — a model failure degrades, never crashes
            enhanced = None
        if isinstance(enhanced, str) and enhanced.strip():
            goal = records.safe_text(enhanced.strip(), config.observer_goal_cap_chars)

    stage = _derive_stage(config, state, entity_dir)
    block = _derive_block(config, messages)
    return {"goal": goal, "stage": stage, "block": block, "reason": reason}


def sidecar_path(config: RuntimeConfig, harness: str, sid: str) -> str:
    """The filesystem path to the observer sidecar for one session.

    The sidecar lives under the observer's own store (``config.state_dir``),
    never under the observed session's repo or state tree.
    """
    safe_harness = records.safe_text(harness, 64)
    safe_sid = records.safe_text(sid, 128)
    return os.path.join(str(config.state_dir), "observer", f"{safe_harness}_{safe_sid}.json")


def write_sidecar(config: RuntimeConfig, harness: str, sid: str, result: dict[str, Any]) -> str:
    """Write the observer sidecar to the observer's own store; return its path."""
    path = sidecar_path(config, harness, sid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(result))
    return path


def read_sidecar(config: RuntimeConfig, harness: str, sid: str) -> dict[str, Any] | None:
    """Read the observer sidecar, or None if absent or malformed."""
    path = sidecar_path(config, harness, sid)
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.loads(handle.read(config.state_read_cap_bytes))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def resolve_transcript(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: str,
    sid: str,
) -> str | None:
    """Find the transcript file path for one session, or None.

    A bounded glob over the harness's store roots, matching the session id
    against the first-line metadata the collectors already use. Read-only;
    no file is opened for writing.
    """
    store_key = {
        "pi": "pi.sessions",
        "claude": "claude.projects",
    }.get(harness)
    if store_key is None:
        return None
    for path in runtime_io.glob_stores(config, store_key, "*.jsonl"):
        meta = transcripts.pi_meta(config, state, path)
        if meta.get("session_id") == sid:
            return path
        # Claude sessions encode the id in the filename, not the first line.
        if sid in os.path.basename(path):
            return path
    # One-level-nested Pi stores.
    if store_key == "pi.sessions":
        for path in runtime_io.glob_stores(config, store_key, "*", "*.jsonl"):
            meta = transcripts.pi_meta(config, state, path)
            if meta.get("session_id") == sid:
                return path
    return None


def resolve_entity_dir(
    config: RuntimeConfig,
    state: RuntimeState,
    transcript_path: str,
) -> str | None:
    """The workflow entity-state directory from the transcript's boot records.

    Reuses the read-only boot scan the Spacedock cartography already proved
    safe. Returns None when the session runs no workflow.
    """
    boot = spacedock.transcript_boot(config, state, transcript_path)
    for workflow_dir in spacedock.workflow_dirs(config, boot):
        entity_dir = spacedock.boot_entity_dir(boot, workflow_dir)
        if entity_dir:
            return entity_dir
    return None
