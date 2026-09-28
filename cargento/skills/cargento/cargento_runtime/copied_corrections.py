"""Copied corrections: a correction the reader copied, recognised when it comes back.

Item 9 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
(DRC-4678). `POST /api/correction/copied` records the digest of the exact text the reader
copied; a later Claude Code user message whose raw text has the same digest is Cargento's words,
`derived`, for adoption, rule 7 and the later-direction floor alike. Only the digest is stored,
never the text.

The digest is computed here by re-reading the transcript tail, the way
`project_context.direction_text` does, rather than inside the collector: the collector's module
is frozen with the abstention qualification (`scripts/mark_abstention.py`, `_PARSER_FILES`), and
this read runs only for a session that holds a copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from typing import TYPE_CHECKING, Any, TypedDict, cast

from . import io as runtime_io
from . import observer, project_context, reading, records
from . import state as runtime_state

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from .config import RuntimeConfig
    from .state import RuntimeState

SCHEMA_VERSION = 1

# The most a correction may hold, which is the most item 7 of that ruling lets the box compose.
CORRECTION_CAP_CHARS = 2000
# The owner's bound, 2026-09-28: eight per session, the oldest dropped.
COPIES_PER_SESSION = 8
# How much of a message is read to digest it. A tab stored as four spaces makes the stored text
# longer than what was copied, so four times the cap covers any correction the route accepts; a
# message that reaches this is longer than any of them and is never digested, so a correction
# cannot match the opening of a longer message the reader wrote.
_MESSAGE_READ_CAP = 4 * CORRECTION_CAP_CHARS + 1
_READ_CAP_BYTES = 1 << 20
_KEY_CAP_CHARS = 64
_LOCK_WAIT_SECONDS = 10.0
# Only Claude Code's messages are read for a digest, which is what item 9 rules.
HARNESSES = frozenset({"claude"})

OUTCOME_STORED = "stored"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_REFUSED = "refused"
OUTCOME_UNWRITABLE = "unwritable"

_WRITE_LOCK = threading.Lock()
_DIGEST = re.compile(r"[0-9a-f]{64}")


class Copy(TypedDict):
    digest: str
    copied_at: float


def normalise(text: str) -> str:
    """The owner's rule, 2026-09-28, applied to both sides.

    Measured on Claude Code 2.1.283 (paste4678): at paste time CRLF and CR become LF and a tab
    becomes exactly four spaces, and a short paste loses its trailing whitespace on submit while
    a long one keeps it. Trimming both ends makes the two agree; nothing else is folded, so any
    edit is a different digest.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ").strip()


def digest(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8", "surrogatepass")).hexdigest()


def store_path(config: RuntimeConfig) -> str:
    """Beside the annotation store, and not per port, for `annotations.store_path`'s reason."""
    return os.path.join(config.state_home, "cargento-copied-corrections.json")


def _lock_path(config: RuntimeConfig) -> str:
    return f"{store_path(config)}.lock"


def _key(harness: Any, sid: Any) -> tuple[str, str]:
    return (
        records.safe_text(harness, _KEY_CAP_CHARS).strip(),
        records.safe_text(sid, _KEY_CAP_CHARS).strip(),
    )


def _copy(value: Any) -> Copy | None:
    if not isinstance(value, dict):
        return None
    found = value.get("digest")
    at = value.get("copied_at")
    if not isinstance(found, str) or not _DIGEST.fullmatch(found):
        return None
    moment = reading.valid_prompt_time(at)
    return {"digest": found, "copied_at": moment} if moment is not None else None


def _read(config: RuntimeConfig) -> dict[tuple[str, str], tuple[Copy, ...]]:
    """Every session's copies on disk. A file that cannot be read holds none.

    An unreadable file is written over by the next copy rather than refused, unlike the annotation
    store: what it loses is digests, and a digest lost only makes a pasted correction read as the
    reader's own words, the direction that never hides a real direction.
    """
    try:
        with open(store_path(config), "rb") as handle:
            raw = handle.read(_READ_CAP_BYTES + 1)
    except OSError:
        return {}
    if len(raw) > _READ_CAP_BYTES:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        return {}
    entries = data.get("entries") if isinstance(data, dict) else None
    held: dict[tuple[str, str], tuple[Copy, ...]] = {}
    for value in entries if isinstance(entries, list) else ():
        if not isinstance(value, dict):
            continue
        key = _key(value.get("harness"), value.get("sid"))
        raw_copies = value.get("copies")
        if not key[0] or not key[1] or not isinstance(raw_copies, list):
            continue
        parsed = [copy for copy in (_copy(item) for item in raw_copies) if copy is not None]
        parsed.sort(key=lambda copy: copy["copied_at"])
        if parsed:
            held[key] = tuple(parsed[-COPIES_PER_SESSION:])
    return held


def load(config: RuntimeConfig) -> dict[tuple[str, str], tuple[Copy, ...]]:
    """Every session's copies, or none under `--no-annotations`."""
    return _read(config) if config.annotations_enabled else {}


def _bounded(
    held: dict[tuple[str, str], tuple[Copy, ...]], limit: int
) -> dict[tuple[str, str], tuple[Copy, ...]]:
    """The `limit` sessions copied from most recently."""
    ordered = sorted(held.items(), key=lambda item: item[1][-1]["copied_at"])
    return dict(ordered[-limit:]) if limit > 0 else {}


def register(
    config: RuntimeConfig,
    harness: Any,
    sid: Any,
    text: Any,
    *,
    now: float,
    diagnostic_sink: Any = print,
) -> str:
    """Record that this text was copied for this session. Returns an outcome token.

    A digest the session already holds answers `unchanged` and keeps its first time, so a second
    registration cannot move where the digest matches from or earn a second match.
    """
    key = _key(harness, sid)
    moment = reading.valid_prompt_time(now)
    if (
        not config.annotations_enabled
        or key[0] not in HARNESSES
        or not key[1]
        or not isinstance(text, str)
        or len(text) > CORRECTION_CAP_CHARS
        or not normalise(text)
        or moment is None
    ):
        return OUTCOME_REFUSED
    found = digest(text)
    # This process's threads first, then the OS lock another dashboard on this home takes, for
    # the order `annotations._locked_store` gives.
    if not _WRITE_LOCK.acquire(timeout=_LOCK_WAIT_SECONDS):
        return OUTCOME_UNWRITABLE
    try:
        try:
            os.makedirs(config.state_home, mode=0o700, exist_ok=True)
        except OSError:
            return OUTCOME_UNWRITABLE
        with runtime_io.held_file_lock(_lock_path(config), wait=_LOCK_WAIT_SECONDS) as held:
            if held not in (runtime_io.LOCK_HELD, runtime_io.LOCK_UNSUPPORTED):
                return OUTCOME_UNWRITABLE
            stored = _read(config)
            prior = stored.get(key, ())
            if any(copy["digest"] == found for copy in prior):
                return OUTCOME_UNCHANGED
            copy: Copy = {"digest": found, "copied_at": moment}
            stored[key] = (*prior, copy)[-COPIES_PER_SESSION:]
            return _write(config, _bounded(stored, config.annotation_max_sessions), diagnostic_sink)
    finally:
        _WRITE_LOCK.release()


def _write(
    config: RuntimeConfig,
    held: dict[tuple[str, str], tuple[Copy, ...]],
    diagnostic_sink: Any,
) -> str:
    payload = {
        "v": SCHEMA_VERSION,
        "entries": [
            {"harness": harness, "sid": sid, "copies": [dict(copy) for copy in copies]}
            for (harness, sid), copies in held.items()
        ],
    }
    try:
        runtime_io.atomic_write_owner_only(store_path(config), json.dumps(payload))
    except (OSError, ValueError):
        runtime_io.diag(
            f"Cargento: could not write the copied-correction store {store_path(config)}",
            diagnostic_sink,
        )
        return OUTCOME_UNWRITABLE
    return OUTCOME_STORED


def forget(config: RuntimeConfig) -> bool:
    """Delete the store, reporting whether there was one. Independent of the flag, for
    `history.forget`'s reason."""
    try:
        os.unlink(store_path(config))
    except FileNotFoundError:
        return False
    return True


def _messages(config: RuntimeConfig, path: str, sid: str) -> list[tuple[str, float, str | None]]:
    """Each user message in the tail: its fact id as `collect` publishes it, its time, its digest.

    The fact id is recomputed exactly as `project_context.direction_text` recomputes it, first of
    a duplicate pair included. The digest is taken from the record's raw content, before the
    redaction and the clipping every published copy of it goes through, and is None for a message
    too long to be any correction.
    """
    out: list[tuple[str, float, str | None]] = []
    seen: set[tuple[float, str]] = set()
    steer = project_context._SEMANTIC_FACT_TYPES["steer"]  # noqa: SLF001 (the collector's own spelling, frozen)
    for raw in runtime_io.read_tail(config, path):
        if not raw or not raw.lstrip().startswith("{"):
            continue
        try:
            record = json.loads(raw)
        except (ValueError, RecursionError):
            continue
        event = project_context._instruction_event(config, record, "claude", sid)  # noqa: SLF001
        if event is None or (event["at"], event["title"]) in seen:
            continue
        seen.add((event["at"], event["title"]))
        fact = project_context._semantic_fact_from_event(event, "steer", steer, "")  # noqa: SLF001
        text = records.extract_text(
            records.message_dict(record).get("content"), cap=_MESSAGE_READ_CAP
        )
        whole = len(text) < _MESSAGE_READ_CAP
        out.append((str(fact["fact_id"]), float(event["at"]), digest(text) if whole else None))
    return out


def matched(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: str,
    sid: str,
    copies: Iterable[Copy] | None = None,
) -> tuple[dict[str, Any], ...]:
    """The messages in this session recognised as a copied correction, oldest first.

    Each copy binds the first message after its time whose digest it holds, so a digest is used
    once and matches only after its copy. A message
    older than the transcript tail is not read, and a correction pasted there is not recognised.
    """
    held = tuple(copies) if copies is not None else load(config).get(_key(harness, sid), ())
    if harness not in HARNESSES or not held:
        return ()
    path = observer.resolve_transcript(config, state, harness, sid)
    if not path:
        return ()
    try:
        stat = os.stat(path)
    except OSError:
        return ()
    cache_key = f"copied-corrections:{harness}:{sid}:{path}"
    stamp = (stat.st_ino, stat.st_mtime_ns, stat.st_size, held)
    with state.cache_lock:
        cached = state.metadata_cache.get(cache_key)
    if cached is not None and cached.get("stamp") == stamp:
        return cast("tuple[dict[str, Any], ...]", cached["result"])
    messages = sorted(_messages(config, path, sid), key=lambda message: message[1])
    found: list[dict[str, Any]] = []
    # A session holds each digest once (`register`), so no message can bind two copies.
    for copy in held:
        for fact_id, at, message_digest in messages:
            if at > copy["copied_at"] and message_digest == copy["digest"]:
                found.append({"fact_id": fact_id, "at": at})
                break
    result = tuple(sorted(found, key=lambda entry: entry["at"]))
    with state.cache_lock:
        runtime_state.bounded_put(
            state.metadata_cache,
            cache_key,
            {"stamp": stamp, "result": result},
            limit=config.max_cache_entries,
        )
    return result


def attach(config: RuntimeConfig, state: RuntimeState, rows: Iterable[dict[str, Any]]) -> None:
    """Put each session's recognised messages on its row, as `[]` where there are none."""
    held = load(config)
    for row in rows:
        key = _key(row.get("harness"), row.get("sid"))
        copies = held.get(key, ())
        row[reading.COPIED_PROMPTS] = (
            [dict(entry) for entry in matched(config, state, key[0], key[1], copies)]
            if copies
            else []
        )


def mark(context: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The project context with each recognised user message marked `copied`.

    A copy of each marked fact, never the fact itself, so a cached context another caller holds
    is not changed under it.
    """
    wanted = {
        _key(row.get("harness"), row.get("sid")): {
            str(entry.get("fact_id"))
            for entry in row.get(reading.COPIED_PROMPTS) or ()
            if isinstance(entry, dict)
        }
        for row in rows
        if row.get(reading.COPIED_PROMPTS)
    }
    raw = context.get("semantic")
    semantic: dict[str, Any] = raw if isinstance(raw, dict) else {}
    facts = semantic.get("facts")
    if not wanted or not isinstance(facts, list):
        return dict(context)

    def marked(fact: Any) -> Any:
        if not isinstance(fact, dict) or fact.get("type") != "user_message":
            return fact
        session = fact.get("source_session")
        if not isinstance(session, dict):
            return fact
        ids = wanted.get(_key(session.get("harness"), session.get("sid")), set())
        return {**fact, reading.COPIED_FLAG: True} if str(fact.get("fact_id")) in ids else fact

    return {**context, "semantic": {**semantic, "facts": [marked(fact) for fact in facts]}}
