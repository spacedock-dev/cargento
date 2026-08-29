"""Bounded filesystem and read-only database operations."""

from __future__ import annotations

import contextlib
import glob
import json
import ntpath
import os
import posixpath
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from . import state as runtime_state

if TYPE_CHECKING:
    import sqlite3 as sqlite3_types
    from collections.abc import Callable, Iterator

    from .config import RuntimeConfig
    from .state import RuntimeState

try:
    import sqlite3 as _sqlite_module
except ImportError as exc:  # pragma: no cover - depends on the interpreter build
    SQLITE_IMPORT_ERROR: str | None = str(exc)
    sqlite_module: Any = None
else:
    SQLITE_IMPORT_ERROR = None
    sqlite_module = _sqlite_module


def read_tail(config: RuntimeConfig, path: str) -> list[str]:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as source:
            truncated = False
            if size > config.tail_bytes:
                source.seek(size - config.tail_bytes - 1)
                truncated = source.read(1) != b"\n"
            data = source.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = data.split("\n")
    if truncated:
        lines = lines[1:]
    return lines


def read_first_json(config: RuntimeConfig, path: str) -> dict[str, Any]:
    try:
        with open(path, "rb") as source:
            size = os.fstat(source.fileno()).st_size
            raw = source.readline(config.first_line_json_cap_bytes)
    except OSError:
        return {}
    if size > len(raw) and raw and not raw.endswith(b"\n"):
        return {}
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def read_prefix_bytes(path: str, *, max_bytes: int) -> bytes:
    with open(path, "rb") as source:
        return source.read(max_bytes)


def iter_bounded_text_lines(
    path: str,
    *,
    max_lines: int,
    per_line_bytes: int,
) -> Iterator[str]:
    try:
        with open(path, "rb") as source:
            for _ in range(max_lines):
                raw = source.readline(per_line_bytes)
                if not raw:
                    break
                yield raw.decode("utf-8", "replace")
    except OSError:
        return


def reverse_lines(
    config: RuntimeConfig,
    path: str,
    end_pos: int | None = None,
    *,
    max_bytes: int | None = None,
    contains: bytes | None = None,
) -> Iterator[bytes]:
    """Yield complete lines from ``path`` newest-first, reading fixed chunks."""
    try:
        with open(path, "rb") as source:
            size = os.fstat(source.fileno()).st_size
            stop = size if end_pos is None else min(end_pos, size)
            floor = 0 if max_bytes is None else max(0, stop - max_bytes)
            pos = stop
            carry: list[bytes] = []
            while pos > floor:
                read_size = min(config.reverse_chunk_bytes, pos - floor)
                pos -= read_size
                source.seek(pos)
                chunk = source.read(read_size)
                if len(chunk) < read_size:
                    return
                last_newline = chunk.rfind(b"\n")
                if last_newline < 0:
                    carry.append(chunk)
                    continue
                carry.append(chunk[last_newline + 1 :])
                completed = b"".join(reversed(carry))
                parts = chunk[:last_newline].split(b"\n")
                carry = [parts[0]]
                if contains is None or contains in chunk or contains in completed:
                    yield completed
                    yield from reversed(parts[1:])
            if floor == 0 and stop > 0:
                yield b"".join(reversed(carry))
    except OSError:
        return


def glob_under(root: str, *pattern: str) -> list[str]:
    return sorted(glob.glob(os.path.join(glob.escape(root), *pattern)))


def glob_stores(config: RuntimeConfig, key: str, *pattern: str) -> list[str]:
    return [path for root in config.store_roots.get(key, ()) for path in glob_under(root, *pattern)]


def any_glob_under(root: str, *pattern: str) -> bool:
    """Whether anything under ``root`` matches, without building the list.

    A predicate's answer is one bit, and `glob_under` pays for a full match list
    and a sort to produce it. `iglob` stops at the first hit. Same escaping
    contract as `glob_under`: the root is a real path and is escaped, the
    pattern is a pattern and is not.
    """
    return next(glob.iglob(os.path.join(glob.escape(root), *pattern)), None) is not None


def any_glob_stores(config: RuntimeConfig, key: str, *pattern: str) -> bool:
    """`glob_stores` as a predicate: the first root that matches ends the walk."""
    return any(any_glob_under(root, *pattern) for root in config.store_roots.get(key, ()))


def any_store_dir(config: RuntimeConfig, key: str, *parts: str) -> bool:
    return any(
        os.path.isdir(os.path.join(root, *parts)) for root in config.store_roots.get(key, ())
    )


def existing_stores(config: RuntimeConfig, key: str) -> list[str]:
    return [path for path in config.store_roots.get(key, ()) if os.path.isfile(path)]


def sqlite_available() -> bool:
    return SQLITE_IMPORT_ERROR is None


def sqlite_ro_uri(path: str, *, immutable: bool = False, windows: bool | None = None) -> str:
    if windows is None:
        windows = os.name == "nt"
    absolute = (ntpath if windows else posixpath).abspath(path)
    if windows:
        absolute = absolute.replace("\\", "/")
        if not absolute.startswith("/"):
            absolute = "/" + absolute
    quoted = quote(absolute, safe="/:")
    if quoted.startswith("//") and not quoted.startswith("///"):
        quoted = "//" + quoted
    query = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    return f"file:{quoted}{query}"


def record_store_error(state: RuntimeState, path: str, exc: BaseException) -> None:
    with state.cache_lock:
        runtime_state.bounded_put(
            state.store_errors,
            path,
            f"{type(exc).__name__}: {exc}",
            limit=state.config.max_cache_entries,
        )


def open_sqlite_read_only(path: str, state: RuntimeState) -> sqlite3_types.Connection:
    try:
        connection: sqlite3_types.Connection = sqlite_module.connect(
            sqlite_ro_uri(path),
            uri=True,
            timeout=0.2,
        )
    except sqlite_module.Error as exc:
        record_store_error(state, path, exc)
        raise
    connection.row_factory = sqlite_module.Row
    return connection


def diag(message: str, sink: Callable[[str], object]) -> None:
    try:
        sink(message)
    except (OSError, ValueError):
        with contextlib.suppress(OSError, ValueError):
            sink(message.encode("ascii", "backslashreplace").decode("ascii"))
