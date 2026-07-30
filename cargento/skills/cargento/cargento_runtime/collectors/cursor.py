"""Cursor CLI collection from its per-session read-only SQLite stores."""

from __future__ import annotations

import contextlib
import json
import os
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from cargento_runtime import io as runtime_io
from cargento_runtime import sessions
from cargento_runtime import state as runtime_state

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState

_STORE_GLOB = ("*", "*", "store.db")


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether a readable Cursor chat store is present."""
    return runtime_io.sqlite_available() and bool(
        runtime_io.glob_stores(config, "cursor.chats", *_STORE_GLOB)
    )


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


def _meta(
    config: RuntimeConfig,
    state: RuntimeState,
    db: str,
    mtime: float,
) -> tuple[str | None, str]:
    """(session name, workspace path) from the meta table: hex-encoded UTF-8
    JSON (some versions store plain JSON; value may be NULL or non-text).
    mode=ro (not immutable) so names still in the WAL are visible. Memoized by
    mtime — both are stable, so no per-refresh reopen."""
    with state.cache_lock:
        hit = state.cursor_metadata_cache.get(db)
    if hit and hit[0] == mtime:
        return hit[1], hit[2]
    title = None
    cwd_by_key: dict[str, str] = {}
    try:
        con = runtime_io.open_sqlite_read_only(db, state)
    except runtime_io.sqlite_module.Error:
        return None, ""
    failed = False
    try:
        rows = con.execute("SELECT value FROM meta LIMIT ?", (config.cursor_meta_rows,)).fetchall()
    except runtime_io.sqlite_module.Error as exc:
        runtime_io.record_store_error(state, db, exc)
        rows, failed = [], True
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
            # Keyed by spelling, not by first-seen: the keys are ranked by
            # trust, and a payload may spread them across rows, so a later row
            # holding a better-trusted key must still win.
            for key in _CURSOR_CWD_KEYS:
                if key in cwd_by_key:
                    continue
                workspace = _workspace(d.get(key))
                if workspace:
                    cwd_by_key[key] = workspace
        if title and _CURSOR_CWD_KEYS[0] in cwd_by_key:
            break  # best-trusted key already found; nothing later can beat it
    cwd = next((cwd_by_key[k] for k in _CURSOR_CWD_KEYS if k in cwd_by_key), "")
    if failed:
        # Transient: do not cache values the query never returned.
        return None, ""
    with state.cache_lock:
        hit = state.cursor_metadata_cache.get(db)
        if hit and hit[0] == mtime:
            return hit[1], hit[2]
        runtime_state.bounded_put(
            state.cursor_metadata_cache,
            db,
            (mtime, title, cwd),
            limit=config.max_cache_entries,
        )
        return title, cwd


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    if not runtime_io.sqlite_available():
        return []
    # One store.db per chat; content is opaque-ish (hex JSON blobs), so
    # Cursor rows are discovery + state + title only — no turn ETA.
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
        title, cwd = _meta(config, state, db, mtime)
        s = sessions.base_session("cursor", sid, sessions.project_from_cwd(config, cwd) or "cursor")
        s.update(
            {
                "title": title if active else None,
                "state": session_state,
                "state_detail": state_detail,
                "active": active,
                "last_activity": mtime,
            }
        )
        out.append(s)
    return out
