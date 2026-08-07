"""Cursor CLI collection from its per-session read-only SQLite stores."""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections import deque
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from cargento_runtime import io as runtime_io
from cargento_runtime import quota as runtime_quota
from cargento_runtime import records, sessions
from cargento_runtime import state as runtime_state

if TYPE_CHECKING:
    import sqlite3 as sqlite3_types

    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState

_STORE_GLOB = ("*", "*", "store.db")


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether a readable Cursor chat store is present."""
    return runtime_io.sqlite_available() and bool(
        runtime_io.glob_stores(config, "cursor.chats", *_STORE_GLOB)
    )


def usage(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
) -> list[dict[str, Any]]:
    """The last fetched Cursor quota, read from the quota module's cache.

    Cursor writes no allowance to disk and pushes nothing to a hook, so the
    only route is the fetch: the CLI's own `GetCurrentPeriodUsage`, reached
    with the session token it keeps in the macOS Keychain. Like Claude's, this
    provider never touches the network. It publishes whatever the fetch thread
    last cached, and the registry wires it in only while the fetch feature is
    enabled, so `--no-usage` leaves the Cursor row with no provider at all.

    Unlike the other harnesses the figures are money against a monthly billing
    cycle rather than a rolling window, which is why the entry fills `month`.
    """
    del config, now, window_hours
    return runtime_quota.cached_entries(state, "cursor")


_CURSOR_CWD_KEYS = ("workspacePath", "workspace", "rootPath", "projectPath", "folder", "cwd")


_ABS_PATH_RE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")


def _workspace(value: Any) -> str:
    """A meta value promoted to a workspace path, or ``""``.

    Accepts the ``file://`` URI form as well as a bare path: that is the
    canonical serialization in the VS Code family, and rejecting it would make
    the whole read a silent no-op that looks identical to "Cursor records no
    workspace".
    """
    if not isinstance(value, str) or not value:
        return ""
    if value.startswith("file://"):
        parsed = urlparse(value)
        if parsed.netloc:  # file://server/share is a UNC path, not a local dir
            return ""
        value = unquote(parsed.path)
        # file:///C:/x parses to /C:/x; ntpath cannot read that spelling.
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", value):
            value = value[1:]
    if not _ABS_PATH_RE.match(value):
        return ""
    try:
        return value if os.path.isdir(value) else ""
    except OSError:
        return ""


_BLOB_ID_RE = re.compile(r"^[0-9a-f]{64}$")

# `providerOptions.cursor.modelName` on a message blob — the one place a Cursor
# store records which model answered. The whole path is the anchor rather than
# `"modelName"` alone: enumerating every `providerOptions.<key>` across three
# live stores returned the `cursor` namespace and nothing else, so a looser
# match would be accepting a field nobody has seen, from a namespace nobody has
# seen, as this session's model. The `\s*` are the one liberty taken with the
# measured spelling — Cursor writes the JSON compact today, and a serializer
# that starts padding its colons is a formatting change, not a new field.
_MODEL_RE = re.compile(
    rb'"providerOptions"\s*:\s*\{\s*"cursor"\s*:\s*\{\s*"modelName"\s*:\s*"([^"]{1,64})"'
)

# One child id inside a root blob: protobuf field 1, wire type 2, length 32.
_CHILD_FRAME = b"\x0a\x20"
_CHILD_ID_BYTES = 32


def _root_child_ids(root: bytes, limit: int) -> list[str]:
    """The LAST ``limit`` message blob ids a root blob lists, in list order.

    That order is the only chronology this store has. `blobs` is
    `(id TEXT PRIMARY KEY, data BLOB)` — no timestamp column — and the ids are
    content-addressed sha256, so the same blob sits under the same id in every
    store that holds it and ordering by id orders by hash, which means nothing.
    The root blob's list is ordered system, user, …, assistant, so the newest
    message is its last child.

    Which is why the cap keeps the newest ids and not the first ones it meets.
    Keeping the first `limit` froze the probe window at the oldest end of the
    list: past `limit` children the window never moved again, and the model of
    message ~63 was published as the model of a chat that had since switched —
    rendered identically to a live reading, and re-derived identically on every
    refresh, so it could not self-correct. Every tool result is its own child,
    so on the live stores 64 children is about 16 assistant turns.

    Parsing the whole list to keep its tail costs nothing: the caller caps the
    root at `cursor_blob_bytes`, and each frame advances at least 34 bytes, so
    the loop runs at most `cursor_blob_bytes / 34` times.

    A stray `0a 20` pair inside message text yields a plausible-looking id that
    belongs to no blob. That is left to miss on the primary-key lookup rather
    than filtered against the id set first: the filter is `SELECT id FROM blobs`,
    a full table scan, and the miss it would save costs one index probe.
    """
    ids: deque[str] = deque(maxlen=limit)
    position = 0
    while True:
        found = root.find(_CHILD_FRAME, position)
        if found < 0 or found + 2 + _CHILD_ID_BYTES > len(root):
            break
        ids.append(root[found + 2 : found + 2 + _CHILD_ID_BYTES].hex())
        position = found + 2 + _CHILD_ID_BYTES
    return list(ids)


def _blob(
    con: sqlite3_types.Connection, blob_id: str, cap: int, *, tail: bool = False
) -> tuple[bytes, bool]:
    """(at most ``cap`` bytes of one blob, whether the read cut the blob short).

    `substr` bounds the read inside SQLite: a tool result runs to tens of
    kilobytes and the field being looked for is twenty, so materialising the
    whole value to search it is the cost this avoids. `length` rides the same
    row so the caller can tell "this blob does not carry the field" from "this
    blob may carry it past the byte we stopped at" — two different facts, and
    only the first one licenses reading an older message instead.

    ``tail`` takes the last ``cap`` bytes rather than the first. A blob shorter
    than the cap comes back whole either way, so this only matters for the one
    read that wants the END of a list: the root's newest children.

    A row that does not exist is not truncated — there is nothing there to cut
    short — and neither is a NULL value. Only a measured length past the cap
    reports true.
    """
    row = con.execute(
        "SELECT substr(data, ?, ?), length(data) FROM blobs WHERE id = ?",
        (-cap if tail else 1, cap, blob_id),
    ).fetchone()
    if row is None:
        return b"", False
    value, size = row[0], row[1]
    truncated = isinstance(size, int) and size > cap
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value), truncated
    if isinstance(value, str):
        return value.encode("utf-8", "replace"), truncated
    return b"", truncated


def _model(config: RuntimeConfig, con: sqlite3_types.Connection, root_id: str) -> str | None:
    """The model of the newest message in one chat store, or nothing.

    Indexed lookups only: one for the root blob's child list, then message
    blobs walked newest first until one carries the model, at most
    `cursor_model_probe_blobs` of them. On three live stores the first blob
    tried held it every time, and the caps are there for the conversation
    shapes that were not measured rather than the ones that were.

    The root is read from its END. Its children are ordered oldest first, so a
    root longer than `cursor_blob_bytes` (about 1,900 children) read from byte 0
    would hand back the oldest window and freeze the answer there. Reading the
    tail can land mid-frame; the re-sync then yields a garbage id or two at the
    OLD end of the window, which `_root_child_ids` drops when it keeps the
    newest ids — and any that survive miss on the primary key like every other
    stray frame.

    The walk stops at a blob it could not read whole. `providerOptions` is not
    anchored near the head: on the live stores it is the last top-level key on
    some assistant blobs and nested inside a content part on others, at offsets
    676–6,042 bytes in, so where it sits tracks how long the message was. A
    blob cut short at the cap is therefore a message whose model we did not
    read, not a message with no model, and reaching past it would publish an
    older message's model as this one's. No live blob is anywhere near the cap
    (the largest of 145 is 48,842 bytes), so this costs nothing measured.

    The value is published verbatim. Cursor writes its own codename (`vega`),
    and mapping that to a marketing name is presentation, which belongs to the
    page — and a mapping table is itself a guess that silently mislabels the
    next codename Cursor ships.

    Blobs are plaintext on every store measured, but every meta payload carries
    a `blobEncryptionKey`, so some build almost certainly encrypts them. There
    the regex simply does not match and the session reports no model, which is
    the honest reading of bytes we cannot read. The key is never used: opening a
    user's conversation to label a card is not a trade this dashboard makes.
    """
    root, _ = _blob(con, root_id, config.cursor_blob_bytes, tail=True)
    if not root:
        return None
    children = _root_child_ids(root, config.cursor_root_children)
    for child_id in list(reversed(children))[: config.cursor_model_probe_blobs]:
        blob, truncated = _blob(con, child_id, config.cursor_blob_bytes)
        found = _MODEL_RE.search(blob)
        if found:
            name = found.group(1).decode("utf-8", "replace")
            return records.safe_text(name, sessions.MODEL_CAP_CHARS).strip() or None
        if truncated:
            return None
    return None


def _meta_fields(rows: list[Any]) -> tuple[str | None, str, str]:
    """(session name, workspace path, root blob id) read out of the meta rows.

    Every value here is untrusted JSON from disk, and each is taken on its own
    terms: a row that fails to parse, or parses to something other than an
    object, costs the reader nothing but that row.
    """
    title = None
    root_id = ""
    cwd_by_key: dict[str, str] = {}
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
            if not isinstance(d, dict):
                continue
            if not title:
                # Untyped JSON from disk: a non-string name must not
                # AttributeError the whole Cursor collector. Take the first
                # value that is actually a string rather than the first that
                # is merely truthy, or a numeric "name" shadows a good "title".
                name = next(
                    (
                        v.strip()
                        for v in (d.get("name"), d.get("title"))
                        if isinstance(v, str) and v.strip()
                    ),
                    "",
                )
                if name:
                    title = name[:80]
            if not root_id:
                # The id of the newest message list. Validated as 64 clean hex
                # characters, because everything downstream of it is a lookup
                # keyed on untrusted text. `lastUsedModel` sits in this same
                # payload and is deliberately not read: it is the model-picker
                # setting, "default" on two of three live sessions and absent on
                # the third, so publishing it would render a session as running
                # a model literally named "default".
                latest = d.get("latestRootBlobId")
                if isinstance(latest, str) and _BLOB_ID_RE.match(latest):
                    root_id = latest
            # Keyed by spelling, not by first-seen: the keys are ranked by
            # trust, and a payload may spread them across rows, so a later row
            # holding a better-trusted key must still win.
            for key in _CURSOR_CWD_KEYS:
                if key in cwd_by_key:
                    continue
                workspace = _workspace(d.get(key))
                if workspace:
                    cwd_by_key[key] = workspace
        if title and root_id and _CURSOR_CWD_KEYS[0] in cwd_by_key:
            break  # best-trusted key already found; nothing later can beat it
    cwd = next((cwd_by_key[k] for k in _CURSOR_CWD_KEYS if k in cwd_by_key), "")
    return title, cwd, root_id


def _model_key(db: str) -> str:
    """The cache key the model rides under, beside the store's own entry.

    The model is memoized on the same mtime as the title and the workspace and
    is written and read with them under one lock, so the two entries are one
    entry in everything but layout. They are two because the cache's value type
    lives in `state.py` and widening it is a change to a module this collector
    does not own; folding them together is a tidy-up, not a behaviour change.
    A NUL is used as the separator because a store path cannot contain one.
    """
    return db + "\x00model"


def _meta(
    config: RuntimeConfig,
    state: RuntimeState,
    db: str,
    mtime: float,
) -> tuple[str | None, str, str | None]:
    """(session name, workspace path, model) from one chat store.

    The first two come from the meta table: hex-encoded UTF-8 JSON (some
    versions store plain JSON; value may be NULL or non-text). mode=ro (not
    immutable) so names still in the WAL are visible — and the model needs that
    even more than the name does, since the blob it reads is the newest message
    of a live session. Memoized by mtime: the meta row is stable and a new
    message necessarily moves the store, so an idle session costs no reopen and
    a busy one cannot be pinned to a stale model.

    The model rides the connection the meta read already opens, and fails on its
    own. A store with no `blobs` table reports no model and keeps its title and
    its workspace: "we did not read a model" and "this store is broken" are
    different facts about different things, and routing the first through the
    second withdraws two readings that were fine.
    """
    with state.cache_lock:
        hit = state.cursor_metadata_cache.get(db)
        model_hit = state.cursor_metadata_cache.get(_model_key(db))
    if hit and model_hit and hit[0] == mtime and model_hit[0] == mtime:
        return hit[1], hit[2], model_hit[1]
    model: str | None = None
    try:
        con = runtime_io.open_sqlite_read_only(db, state)
    except runtime_io.sqlite_module.Error:
        return None, "", None
    failed = False
    try:
        try:
            rows = con.execute(
                "SELECT value FROM meta LIMIT ?", (config.cursor_meta_rows,)
            ).fetchall()
        except runtime_io.sqlite_module.Error as exc:
            runtime_io.record_store_error(state, db, exc)
            rows, failed = [], True
        title, cwd, root_id = _meta_fields(rows)
        if root_id:
            try:
                model = _model(config, con, root_id)
            except runtime_io.sqlite_module.Error:
                model = None
    finally:
        con.close()
    if failed:
        # Transient: do not cache values the query never returned.
        return None, "", None
    with state.cache_lock:
        hit = state.cursor_metadata_cache.get(db)
        model_hit = state.cursor_metadata_cache.get(_model_key(db))
        if hit and model_hit and hit[0] == mtime and model_hit[0] == mtime:
            return hit[1], hit[2], model_hit[1]
        runtime_state.bounded_put(
            state.cursor_metadata_cache,
            db,
            (mtime, title, cwd),
            limit=config.max_cache_entries,
        )
        runtime_state.bounded_put(
            state.cursor_metadata_cache,
            _model_key(db),
            (mtime, model, ""),
            limit=config.max_cache_entries,
        )
        return title, cwd, model


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    if not runtime_io.sqlite_available():
        return []
    # One store.db per chat; message content sits in content-addressed blobs
    # with no timestamps, so Cursor rows are discovery + state + title + model
    # only — no turn ETA. Subagents keep their own store under the same
    # workspace hash and are published as peer top-level rows here; folding them
    # into their parent (and the `_CURSOR_CWD_KEYS` defect above) is Cursor's own
    # ticket, so no Cursor row carries a subagent, or a subagent model, yet.
    out: list[dict[str, Any]] = []
    for db in runtime_io.glob_stores(config, "cursor.chats", "*", "*", "store.db"):
        sid = os.path.basename(os.path.dirname(db))
        try:
            mtime = os.path.getmtime(db)
            wal = db + "-wal"
            if os.path.exists(wal):
                mtime = max(mtime, os.path.getmtime(wal))
        except OSError:
            continue
        active = sessions.is_fresh(config, now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        session_state, state_detail = "idle", "awaiting your message"
        if sessions.is_fresh(config, now, mtime, config.working_threshold_sec):
            session_state, state_detail = "working", "generating…"
        title, cwd, model = _meta(config, state, db, mtime)
        s = sessions.base_session("cursor", sid, sessions.project_from_cwd(config, cwd) or "cursor")
        s.update(
            {
                "title": title if active else None,
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
                # Unlike the title, this is not gated on `active`. A parked
                # session's last message was still answered by some model, and
                # that reading does not go stale the way a title does.
                # `provider` stays None: the on-disk namespace is literally
                # `cursor`, so filling it would be a measurement rather than a
                # guess, but the page would then print "via Cursor" beside a
                # badge that already says Cursor.
                "model": model,
            }
        )
        out.append(s)
    return out
