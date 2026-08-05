"""A coarse store probe: cheap detection that something on disk moved.

The probe answers one question, "is it worth collecting", and answers it wrongly
in one documented direction. It is a wake-up hint, never authority, which is why
periodic reconciliation stays whatever this reports.

What it stats, and why that set:

- every store root, so a new project directory is noticed;
- every immediate child of a store root, so a new session file inside an
  existing project is noticed;
- every path a caller names as tracked, so an append to a live session's
  transcript is noticed.

That last group is the reason the probe stats files at all. Appending to a file
does not change its parent directory's mtime on any supported filesystem, so a
directory-only probe would miss exactly the event that matters most: an active
session writing another turn. Size is stamped alongside mtime because a coarse
filesystem timestamp can leave mtime unchanged for two writes inside one tick,
and a length change survives that.

SQLite needs its siblings. A write may land in the database, its write-ahead log,
or its shared-memory file, and a busy harness often touches only the WAL, so the
`-wal` and `-shm` companions of a tracked database are stamped with it.

## The false negative, stated plainly

A session that is not tracked and whose directory does not change is invisible.
Concretely: a session older than the activity window becomes active again. Its
transcript's mtime moves, but the file is not in the tracked set and appending
changed no directory, so the stamp does not move.

That is not a bug to fix by widening the set. Widening it means statting every
historical transcript, which on a real machine is tens of thousands of files and
costs more than the collection the probe exists to avoid. The bounded set is the
point, and reconciliation is what covers the gap.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cargento_runtime.config import RuntimeConfig

# One entry per watched path: its mtime and its size. A directory's size is
# meaningless on some filesystems and merely unhelpful on others, so it is
# stamped and ignored rather than special-cased.
Stamp = dict[str, tuple[float, int]]

# Suffixes a SQLite write may land in instead of the database itself.
SQLITE_SIBLINGS = ("-wal", "-shm")


def _stat_into(stamp: Stamp, path: str) -> None:
    try:
        info = os.stat(path)
    except OSError:
        # Absent stamps as a sentinel rather than dropping out, so a path
        # appearing or disappearing is itself a change.
        stamp[path] = (-1.0, -1)
        return
    stamp[path] = (info.st_mtime, info.st_size)


def watched_paths(config: RuntimeConfig, *, tracked: Iterable[str] = ()) -> list[str]:
    """Every path the probe stats, in a stable order.

    Separate from `stamp` so the cost of the probe can be measured against the
    size of the set it walks, and so a test can assert what is covered.
    """
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        if path not in seen:
            seen.add(path)
            paths.append(path)

    for roots in config.store_roots.values():
        for root in roots:
            add(root)
            try:
                with os.scandir(root) as entries:
                    children = sorted(entry.path for entry in entries if entry.is_dir())
            except OSError:
                continue  # absent, a file, or unreadable: the root stamp covers it
            for child in children:
                add(child)
    for path in tracked:
        add(path)
        for suffix in SQLITE_SIBLINGS:
            if path.endswith(".db"):
                add(path + suffix)
    return paths


def stamp(config: RuntimeConfig, *, tracked: Iterable[str] = ()) -> Stamp:
    """Stat every watched path once. No globbing, no reads, no recursion."""
    result: Stamp = {}
    for path in watched_paths(config, tracked=tracked):
        _stat_into(result, path)
    return result


def changed(before: Stamp | None, after: Stamp) -> bool:
    """Whether anything watched moved.

    A first probe with no previous stamp reports change, so a cold start
    collects rather than waiting for a second sample.
    """
    if before is None:
        return True
    return before != after
