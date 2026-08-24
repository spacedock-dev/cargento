"""Cursor CLI collection from its per-session read-only SQLite stores."""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections import deque
from typing import TYPE_CHECKING, Any, NamedTuple
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

# The `cwd` of the sibling meta.json, ranked as if it were a seventh key so the
# selection below stays one decision. It outranks all six because it is the only
# one anybody has seen: the decoded `meta` payload of three live stores holds
# agentId, blobEncryptionKey, createdAt, isRunEverything, latestRootBlobId, mode
# and name — none of the six, which are inferred from the VS Code lineage. If
# some build writes a stale `workspace` key, ranking it above the measured value
# is exactly the confident-wrong label the isdir gate exists to prevent.
_SIBLING_CWD_KEY = "meta.json:cwd"
_CWD_KEY_RANKING = (_SIBLING_CWD_KEY, *_CURSOR_CWD_KEYS)


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


def _sibling_cwd(config: RuntimeConfig, db: str) -> str:
    """The workspace the ``meta.json`` beside one store records, or ``""``.

    An absent, unparseable or truncated file yields nothing and is never a store
    error: one live agent directory has no meta.json at all, so a miss is an
    ordinary shape rather than a fault, and badging the harness for it would
    withdraw the title, the model and the workspace of every other Cursor row.

    The value goes through `_workspace` like any meta key, so being measured
    buys it the top of the ranking and not an exemption from the isdir gate.
    """
    meta_json = os.path.join(os.path.dirname(db), "meta.json")
    return _workspace(runtime_io.read_first_json(config, meta_json).get("cwd"))


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


# The gate. `pendingToolExecutionContracts` is a map keyed by tool call id, and
# a non-empty one is a person being asked to approve something; the answer --
# approval or refusal alike -- appends a blob carrying the same key with the map
# emptied. `pendingToolCallStartedAtMs` rides the same object and is the stamp,
# not the discriminator: it survives the answer (`a1-approve` recorded
# `pending_started_ms_present_after_answer` beside zero contract entries), so a
# reader keyed on it reports every session that ever stood at a gate as waiting
# forever. Measured in docs/captures/cursor/pending-tool-call-2026.08.11-macos.jsonl.
#
# Matched on bytes because the carrier is a length-prefixed binary frame rather
# than a JSON object, so `_meta_fields`' parse finds nothing in it. The optional
# quote absorbs both spellings of the key's own terminator, and the `\s*` are the
# liberty `_MODEL_RE` already takes with a compact serializer. `(\S)` is the first
# non-space byte inside the map: `}` is empty and anything else is a contract.
#
# A frame that does not match at all publishes no wait. That is the safe
# direction on this field -- a missed gate is a row that reads Working, and an
# invented one is a red row and a desktop popup for nobody.
_PENDING_KEY = b"pendingToolExecutionContracts"
_PENDING_MAP_RE = re.compile(rb'pendingToolExecutionContracts"?\s*:\s*\{\s*(\S)')
_PENDING_STARTED_RE = re.compile(rb'pendingToolCallStartedAtMs"?\s*:\s*(\d{1,20})')

# How much of the carrier blob to read around the key. The enclosing object holds
# three keys and one contract entry ran to about 200 bytes with an 85-character
# id, so this is two orders above what the two readings need, and it is what keeps
# a per-session-per-refresh read from materialising a whole blob: the largest of
# the 145 blobs measured across three live stores is 48,842 bytes.
_PENDING_WINDOW_BYTES = 4096


def _pending_since(con: sqlite3_types.Connection) -> float | None:
    """When the newest standing tool-call gate opened, or None if none stands.

    ``0.0`` is a gate whose stamp would not read, which the caller falls back to
    the store's mtime for rather than publishing a wait that began at the epoch.

    Newest **by rowid**, and that is the constraint rather than a preference. The
    store is append-only and its ids are content-addressed sha256, so the blob
    that stood at the gate is still in the table long after the answer and the id
    carries no chronology at all; `rowid` is the only order handle the schema
    (`id TEXT PRIMARY KEY, data BLOB`) leaves. "Any blob carries a non-empty map"
    is a wait that never ends.

    Its own read rather than a widening of `_model`'s meta-root-children walk:
    the carrier is not reachable from `latestRootBlobId` in the general case --
    the capture found one readable store whose root id was not in the table at
    all -- so a walk that started there would miss it. It rides the connection
    `_meta` already opened and is memoized on the same mtime, so an idle session
    costs nothing and a busy one cannot be pinned to a stale answer.

    The scan happens inside SQLite: `instr` filters and the rowid index orders,
    so at most one bounded window crosses into Python however many blobs the
    store holds.

    The `CAST` is load-bearing and not tidiness. SQLite types values rather than
    columns, so a build that wrote the frame as text keeps it as text in a column
    declared BLOB — and `instr` compares a text value against a blob needle by
    finding nothing at all. Without the cast such a store reports no gate ever,
    silently and identically to a store with no gate in it. Casting also keeps
    the offsets `substr` counts in bytes on both, which is what the byte match
    downstream assumes.
    """
    row = con.execute(
        "SELECT substr(CAST(data AS BLOB), max(1, instr(CAST(data AS BLOB), :key) - :window), "
        ":window * 2) FROM blobs WHERE instr(CAST(data AS BLOB), :key) > 0 "
        "ORDER BY rowid DESC LIMIT 1",
        {"key": _PENDING_KEY, "window": _PENDING_WINDOW_BYTES},
    ).fetchone()
    if row is None:
        return None
    if not isinstance(row[0], (bytes, bytearray, memoryview)):
        return None
    frame = bytes(row[0])
    # Last carrier in the window rather than first, for the reason the blob is
    # chosen by highest rowid: a blob is bytes appended in order, so where two
    # objects in one carry the key the later one is the later state. First-match
    # disagrees with that in both directions -- an answered call followed by a
    # new gate reads as no wait, and a gate followed by its answer reads as a
    # wait that never ends. A second carrier further from the key than the
    # window is not reachable without materialising the whole blob, and whether
    # a real blob ever holds two is unmeasured: the capture counted contract
    # entries, never occurrences of the key.
    found = None
    for match in _PENDING_MAP_RE.finditer(frame):
        found = match
    if found is None or found.group(1) == b"}":
        return None
    stamp = _nearest_stamp(frame, found.start())
    return 0.0 if stamp is None else stamp


def _nearest_stamp(frame: bytes, key_pos: int) -> float | None:
    """The gate stamp beside the carrier at ``key_pos``, or None if there is none.

    Nearest rather than first, and that is the whole point of the function. The
    stamp sits in the same object as the contracts map but *before* it in the
    orders measured, so it has to be looked for behind the key — and the window
    opens 4096 bytes behind, which is room for other objects that spell the same
    field. Searching that window forwards takes the candidate furthest from the
    carrier: a 40-second-old gate rendered as eleven hours that way, and the
    attention queue ranks on this stamp, so it sorted eleven hours wrong too.
    Nearest is direction-agnostic, so it also survives a serializer that puts
    the stamp after the map.
    """
    best: re.Match[bytes] | None = None
    for match in _PENDING_STARTED_RE.finditer(frame):
        if best is None or abs(match.start() - key_pos) < abs(best.start() - key_pos):
            best = match
    return None if best is None else int(best.group(1)) / 1000


def _blobs_table_missing(con: sqlite3_types.Connection) -> bool:
    """Whether this store has no `blobs` table, asked after a failed gate read.

    Separates the one gate failure that is a reading from every failure that is
    not. Read from `sqlite_master` rather than by matching the exception's
    message, because that text is SQLite's to change and a reader that got it
    wrong would silently memoize a transient error again.

    False when the question itself cannot be answered, since that is the same
    "no value returned" the caller is already deciding not to trust.
    """
    try:
        row = con.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'blobs'"
        ).fetchone()
    except runtime_io.sqlite_module.Error:
        return False
    return bool(row) and not row[0]


def _meta_fields(rows: list[Any], sibling_cwd: str) -> tuple[str | None, str, str, str, str]:
    """(session name, workspace, root blob id, parent agent id, subagent type).

    Every value here is untrusted JSON from disk, and each is taken on its own
    terms: a row that fails to parse, or parses to something other than an
    object, costs the reader nothing but that row.

    ``sibling_cwd`` is the meta.json reading, already through `_workspace`. It
    is seeded into the same ranked map the meta keys fill rather than compared
    against the winner afterwards, so which path a row publishes stays one
    decision in one place.
    """
    title = None
    root_id = ""
    parent_id = ""
    type_name = ""
    cwd_by_key: dict[str, str] = {}
    if sibling_cwd:
        cwd_by_key[_SIBLING_CWD_KEY] = sibling_cwd
    # What the rows could still beat. The sibling file is read before the loop,
    # so when it produced a value the best key is already in hand and only the
    # title and the root id are still worth scanning for; when it did not, the
    # early exit is the one it always was.
    best_cwd_key = _SIBLING_CWD_KEY if sibling_cwd else _CURSOR_CWD_KEYS[0]
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
            if not parent_id:
                # Measured on a live subagent store: `subagentInfo` carries
                # parentAgentId, rootParentAgentId, toolCallId and typeName,
                # and both ids name a sibling agent directory that exists —
                # which is the `sid` another row already publishes, since a
                # Cursor sid IS the agent directory name. So this is an
                # id-to-id edge, not an inference from timing or a shared hash.
                #
                # The ROOT parent is read first. No live store nests deeper
                # than one level (there the two ids are equal), so flattening
                # the subtree onto the root card is the rule that cannot orphan a
                # grandchild into a peer row, which is the defect being closed.
                # parentAgentId is the fallback for a payload that carries only
                # the direct edge.
                info = d.get("subagentInfo")
                if isinstance(info, dict):
                    parent = next(
                        (
                            v.strip()
                            for v in (info.get("rootParentAgentId"), info.get("parentAgentId"))
                            if isinstance(v, str) and v.strip()
                        ),
                        "",
                    )
                    if parent:
                        # Only ever an index key, never displayed; the cap is
                        # there so an absurd value cannot ride in a cache entry.
                        parent_id = records.safe_text(parent, 120)
                        # `name` is the literal "New Agent" on the live subagent
                        # store, so typeName is the only label that says what
                        # the child is. Capped at 70 like every other harness's
                        # subagent label.
                        type_name = records.safe_text(info.get("typeName"), 70).strip()
            # Keyed by spelling, not by first-seen: the keys are ranked by
            # trust, and a payload may spread them across rows, so a later row
            # holding a better-trusted key must still win.
            for key in _CURSOR_CWD_KEYS:
                if key in cwd_by_key:
                    continue
                workspace = _workspace(d.get(key))
                if workspace:
                    cwd_by_key[key] = workspace
        if title and root_id and best_cwd_key in cwd_by_key:
            # Best-trusted key already found; nothing later can beat it. The
            # parent edge is not in this condition because no value says "there
            # is no subagentInfo later" — and it does not need to be: every live
            # store's `meta` holds exactly one row, key `0`, so the row that
            # satisfies this is the row the edge would be on.
            break
    cwd = next((cwd_by_key[k] for k in _CWD_KEY_RANKING if k in cwd_by_key), "")
    return title, cwd, root_id, parent_id, type_name


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


def _subagent_key(db: str) -> str:
    """The cache key the parent edge and the child's label ride under.

    A third entry for the same reason the model got a second one: they are all
    memoized on one mtime under one lock, and the alternative is widening
    `state.cursor_metadata_cache`'s value type, which is a change to a module
    this collector does not own.
    """
    return db + "\x00subagent"


def _pending_key(db: str) -> str:
    """The cache key the standing gate rides under.

    A fourth entry, for the reason the model and the subagent edge got the
    second and third: they are all memoized on one mtime under one lock, and
    folding them together means widening `state.cursor_metadata_cache`'s value
    type, which is a change to a module this collector does not own.

    The slot holds `None` for "nobody is waiting" and the stamp as `repr` text
    otherwise, `"0.0"` being a gate whose stamp would not read. Those are two
    different readings and the encoding keeps them apart: collapsing them would
    turn an unreadable stamp into no gate at all.
    """
    return db + "\x00pending"


def _cached(
    state: RuntimeState, db: str, mtime: float, *, locked: bool = False
) -> tuple[str | None, str, str | None, str, str, float | None] | None:
    """One store's memoized readings, or None when any of the four is stale.

    All or nothing on purpose. The four entries are one memo split across four
    keys only because the cache's value type is two strings wide, so accepting a
    subset would publish readings from two different states of the same store.

    ``locked`` is for the second, double-checked call inside `_meta`'s write
    section, which already holds `cache_lock`; `cache_lock` is not reentrant.
    """
    keys = (db, _model_key(db), _subagent_key(db), _pending_key(db))
    if locked:
        hits = [state.cursor_metadata_cache.get(key) for key in keys]
    else:
        with state.cache_lock:
            hits = [state.cursor_metadata_cache.get(key) for key in keys]
    fresh = [hit for hit in hits if hit is not None and hit[0] == mtime]
    if len(fresh) != len(keys):
        return None
    base, model_hit, sub_hit, pend_hit = fresh
    return (
        base[1],
        base[2],
        model_hit[1],
        sub_hit[1] or "",
        sub_hit[2],
        None if pend_hit[1] is None else float(pend_hit[1]),
    )


def _meta(
    config: RuntimeConfig,
    state: RuntimeState,
    db: str,
    mtime: float,
) -> tuple[str | None, str, str | None, str, str, float | None]:
    """(name, workspace, model, parent agent id, subagent type, gate stamp) for one store.

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
    second withdraws two readings that were fine. The sibling meta.json is read
    on the same terms and for the same reason.
    The gate rides the same connection and the same mtime, for the same reason
    and with one more of its own: it is a scan rather than an indexed lookup, so
    it is the read that most needs an idle session to cost nothing.
    """
    cached = _cached(state, db, mtime)
    if cached is not None:
        return cached
    model: str | None = None
    pending: float | None = None
    try:
        con = runtime_io.open_sqlite_read_only(db, state)
    except runtime_io.sqlite_module.Error:
        return None, "", None, "", "", None
    failed = False
    try:
        try:
            rows = con.execute(
                "SELECT value FROM meta LIMIT ?", (config.cursor_meta_rows,)
            ).fetchall()
        except runtime_io.sqlite_module.Error as exc:
            runtime_io.record_store_error(state, db, exc)
            rows, failed = [], True
        title, cwd, root_id, parent_id, type_name = _meta_fields(rows, _sibling_cwd(config, db))
        if root_id:
            try:
                model = _model(config, con, root_id)
            except runtime_io.sqlite_module.Error:
                model = None
        # Fails on its own like the model read, and for the sharper version of
        # the same reason: a store on a schema with no `blobs` table has no gate
        # to report, and routing that through the store-error boundary would
        # withdraw a title and a workspace that were fine.
        gate_settled = True
        try:
            pending = _pending_since(con)
        except runtime_io.sqlite_module.Error:
            pending = None
            # Which failure it was decides whether `None` may be memoized, and
            # the two are not close. A schema with no `blobs` table has no gate
            # and cannot grow one while the mtime holds, so that answer is a
            # reading. Anything else — a busy writer expiring
            # `open_sqlite_read_only`'s busy timeout, most of all — returned no
            # value at all, and the mtime it would be cached against is one a
            # standing gate freezes by construction: the gate-opening write is
            # the last write the store gets, which is why the capture's
            # false-positive control found abandoned stores still at a gate
            # 29.4 hours on. Cached, that `None` hides the gate for the whole
            # life of the wait and heals only when the human answers.
            gate_settled = _blobs_table_missing(con)
    finally:
        con.close()
    if failed:
        # Transient: do not cache values the query never returned.
        return None, "", None, "", "", None
    if not gate_settled:
        # The readings that did return are still published; only the memo is
        # withheld, so the next refresh re-reads the store rather than serving
        # a gate reading that was never taken.
        return title, cwd, model, parent_id, type_name, pending
    with state.cache_lock:
        cached = _cached(state, db, mtime, locked=True)
        if cached is not None:
            return cached
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
        runtime_state.bounded_put(
            state.cursor_metadata_cache,
            _subagent_key(db),
            (mtime, parent_id, type_name),
            limit=config.max_cache_entries,
        )
        runtime_state.bounded_put(
            state.cursor_metadata_cache,
            _pending_key(db),
            (mtime, None if pending is None else repr(pending), ""),
            limit=config.max_cache_entries,
        )
        return title, cwd, model, parent_id, type_name, pending


class _Chat(NamedTuple):
    """One chat store, read but not yet published.

    Two passes are needed because a store cannot be published until every other
    store has been read: whether this one is a row of its own or a pill on
    another's card is decided by an id that lives in a sibling's payload.
    """

    sid: str
    mtime: float
    title: str | None
    project: str
    model: str | None
    parent_id: str
    type_name: str
    pending_since: float | None


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
    # + subagents only — no turn ETA. A subagent keeps its own store under the
    # same workspace hash, and its meta payload names the agent it belongs to:
    # `subagentInfo.rootParentAgentId` is another agent DIRECTORY name, which is
    # exactly the `sid` another row publishes, so the fold below is an id-to-id
    # edge and not an inference from timing or a shared hash. The workspace is
    # not in that payload at all — no spelling of it is — and comes from the
    # sibling meta.json instead.
    chats: list[_Chat] = []
    for db in runtime_io.glob_stores(config, "cursor.chats", "*", "*", "store.db"):
        sid = os.path.basename(os.path.dirname(db))
        try:
            mtime = os.path.getmtime(db)
            wal = db + "-wal"
            if os.path.exists(wal):
                mtime = max(mtime, os.path.getmtime(wal))
        except OSError:
            continue
        if not (sessions.is_fresh(config, now, mtime, window_hours * 3600) or show_all):
            continue
        title, cwd, model, parent_id, type_name, pending_since = _meta(config, state, db, mtime)
        chats.append(
            _Chat(
                sid,
                mtime,
                title,
                sessions.project_from_cwd(config, cwd) or "cursor",
                model,
                parent_id,
                type_name,
                pending_since,
            )
        )

    known = {chat.sid for chat in chats}
    children: dict[str, list[_Chat]] = {}
    tops: list[_Chat] = []
    for chat in chats:
        # A parent id that names no store here is not folded but promoted: the
        # live store already holds that shape, and a dropped row is an invisible
        # failure, since the reader cannot tell "folded" from "lost". A payload
        # naming itself is treated the same way, rather than nesting a row under
        # itself or losing it to an edge that cannot be true.
        if chat.parent_id and chat.parent_id != chat.sid and chat.parent_id in known:
            children.setdefault(chat.parent_id, []).append(chat)
        else:
            tops.append(chat)

    out: list[dict[str, Any]] = []
    for chat in tops:
        kids = sorted(children.get(chat.sid, []), key=lambda k: -k.mtime)
        subagents = [{"name": k.type_name or "subagent", "model": k.model} for k in kids]
        # The whole subtree, so a parent parked on a working child does not age
        # out of the window — the same absorption Goose and OpenCode do, and
        # `own_activity` below is why it loses nothing: it keeps the parent-alone
        # reading beside it.
        last_activity = sessions.newest_plausible(
            config, now, (chat.mtime, *(k.mtime for k in kids))
        )
        active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
        if not (active or show_all):
            continue
        session_state, state_detail = "idle", "awaiting your message"
        blocked_since = None
        # THE LIVENESS GATE. A Cursor store is append-only, so a session
        # abandoned at a gate carries its pending contract for as long as the
        # file exists: of ten readable stores no arm of the probe had touched, 2
        # still read as waiting 29.4 hours after their process exited, and
        # nothing beside the store records the process going away — no lock file,
        # no pid. Publishing those is a permanent red row for a session nobody is
        # in, and since DRC-4192 a desktop notification with each.
        #
        # `active` is the liveness the row already runs on: the same test that
        # decides whether this store is a session at all, and the one the title
        # is already gated on. It holds under `--all` too, where the row is shown
        # and `active` is still False, which is the mode the measured case would
        # otherwise reach the board through.
        #
        # Not `working_threshold_sec`. A gate the probe deliberately left standing
        # ran 243.7 s without expiring and nothing found an upper bound, so a
        # 90-second liveness would drop real prompts — and `config.py` already
        # rules that a needs-input overlay has no deadline for that reason.
        gate = chat.pending_since if active else None
        # AND THE STAMP HAS TO BE THIS STORE'S OWN. The gate-opening write is
        # what puts the stamp on disk, so on a real gate the two are the same
        # moment give or take the hook that ran before it — 20 seconds in the
        # measured worst case, where the probe's hook slept that long. A stamp
        # from long before the store's last write is therefore not this
        # conversation's current state: it is one donated by a neighbouring
        # object in the window, or bytes that merely spell the field, which a
        # message quoting a store record is enough to produce. Published, that
        # is a permanent red row and a desktop popup carrying a wait nobody
        # believes, and nothing retires it — the blob stays the newest carrier
        # for as long as the store exists.
        #
        # The store's own mtime is the reference rather than `now`, because it
        # is what the stamp is a claim about; `is_fresh` is the same test the
        # row's liveness runs on, and it rejects a stamp implausibly *ahead* of
        # that write for free. The window is the activity window rather than a
        # tight bound of its own: nothing measured how far a gate's stamp can
        # legitimately trail a later write to the same store, and a missed gate
        # is a row that reads Working where an invented one is a popup.
        if gate and not sessions.is_fresh(config, chat.mtime, gate, window_hours * 3600):
            gate = None
        if gate is not None:
            # Ahead of the working test, like Copilot's (design-needs-input N-2):
            # the store moves when the gate opens, so every standing gate is
            # inside the working window and a Working row here would be the whole
            # defect.
            session_state = "needs_input"
            blocked_since = gate or chat.mtime
            waited = sessions.fmt_duration(sessions.age(config, now, blocked_since))
            # Says a permission request is open and stops there. The contract
            # entry names the tool (`outerToolName`, `toolIdentifier`,
            # `allowedToolNames`), and this string is the popup body, so reading
            # any of them would put a command on a desktop notification.
            state_detail = f"permission request, waiting {waited}"
        elif sessions.is_fresh(config, now, last_activity, config.working_threshold_sec):
            session_state = "working"
            # Only the children that are moving now, which is a shorter list
            # than the pills: every folded child is published so that none
            # disappears, but a child parked hours ago must not make its parent
            # read "running 1 subagent". `working_detail` counts what it is
            # given, so the list it is given is the claim being made.
            running = [
                k
                for k in kids
                if sessions.is_fresh(config, now, k.mtime, config.working_threshold_sec)
            ]
            state_detail = sessions.working_detail(None, running)
        s = sessions.base_session("cursor", chat.sid, chat.project)
        s.update(
            {
                "title": chat.title if active else None,
                "state": session_state,
                "state_detail": state_detail,
                # The queue ranks on this, so it is the stamp the store recorded
                # rather than the collection time: a gate that has cost somebody
                # ten minutes must not sort behind one that opened just now.
                "blocked_since": blocked_since,
                "active": active,
                "last_activity": last_activity,
                "own_activity": chat.mtime,
                # Unlike the title, this is not gated on `active`. A parked
                # session's last message was still answered by some model, and
                # that reading does not go stale the way a title does.
                # `provider` stays None: the on-disk namespace is literally
                # `cursor`, so filling it would be a measurement rather than a
                # guess, but the page would then print "via Cursor" beside a
                # badge that already says Cursor.
                "model": chat.model,
                # `typeName` — `cursor-guide` on the live store — rather than the
                # child's own `name`, which is the literal "New Agent" there.
                "subagents": subagents,
            }
        )
        out.append(s)
    return out
