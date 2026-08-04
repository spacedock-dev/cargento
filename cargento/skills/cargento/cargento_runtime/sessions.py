"""Session identity, shape, and deterministic aggregation."""

from __future__ import annotations

import ntpath
import posixpath
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .config import RuntimeConfig

Session: TypeAlias = dict[str, Any]


def encoded_home_prefix(home: str) -> str:
    """Reproduce how Claude encodes ``home`` into a ``projects/`` directory name.

    Claude turns a working directory into a directory name by replacing path
    separators with ``-``; stripping that prefix is what leaves a readable
    project label. Replacing only ``/`` worked on POSIX and did nothing on a
    Windows home, so every Claude row there showed the whole encoded path
    instead of the project.

    Backslash and the drive colon are folded too. The exact Windows encoding is
    not documented, so this is deliberately non-destructive: if it turns out to
    differ, the prefix simply does not match and project_label() shows the full
    name — exactly what it does today.
    """
    return re.sub(r"[/\\:]", "-", home)


def project_label(config: RuntimeConfig, dirname: str) -> str:
    """Shorten an encoded project directory name to just the project part."""
    dirname = dirname.removeprefix(encoded_home_prefix(config.home))
    return dirname.lstrip("-") or "(home)"


def project_from_cwd(config: RuntimeConfig, cwd: str) -> str:
    """``<parent>/<basename>`` for a working directory, ``""`` when unusable.

    One directory has to read the same on every harness row, so this is the
    single rule they all share. Bare basename was the old per-collector rule
    and it collapses every checkout named ``subspace`` into one label; two
    segments keep sibling worktrees apart without pasting a whole path into
    the row.

    Separators are the host's, via ``ntpath``/``posixpath``, never a hand-rolled
    split on both. ``docs/design-cross-platform.md`` rejects that helper outright:
    ``\\`` is a legal POSIX filename character, so splitting on it turns one
    directory named ``my\\proj`` into two. Cargento only ever reads stores written
    on the machine it runs on, so the host's own rules are the correct ones.

    A path under the configured home is labelled relative to it, because
    ``project_label`` strips the home prefix and the two have to agree: ``~/foo``
    reads ``foo`` from either, never ``<username>/foo``.

    ``config.home`` and ``config.os_name`` carry those two facts, so one runner
    exercises both platforms (design decision D-4).

    Callers apply their own fallback to ``""`` — the harness name, or the
    encoded-directory label for the two collectors that have one.
    """
    path = ntpath if config.os_name == "nt" else posixpath
    if not cwd or not path.isabs(cwd):
        return ""  # a relative cwd names no project; fall through to the caller
    home_dir = config.home

    def trim(value: str) -> str:
        seps = path.sep + (path.altsep or "")
        return value.rstrip(seps) or value

    # normcase folds Windows case *and* separators, and preserves length, so
    # the comparison is spelling-independent and the slice below stays valid.
    cwd_cmp, home_cmp = path.normcase(trim(cwd)), path.normcase(trim(home_dir))
    if cwd_cmp == home_cmp:
        return "(home)"
    rest = trim(cwd)
    if home_cmp and cwd_cmp.startswith(home_cmp + path.sep):
        rest = rest[len(trim(home_dir)) :]
    else:
        rest = path.splitdrive(rest)[1]  # "C:" names no project
    if path.altsep:  # Windows accepts either spelling; POSIX has no altsep
        rest = rest.replace(path.altsep, path.sep)
    parts = [p for p in rest.split(path.sep) if p and p != "."]
    if any(p == ".." for p in parts):
        return ""  # an unresolved cwd would render as an absurd label
    return "/".join(parts[-2:])


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


def age(config: RuntimeConfig, now: float, timestamp: float) -> float | None:
    """Seconds since ``timestamp``; ``None`` when the timestamp is implausible.

    A timestamp far in the future is not activity. It arrives from a store
    restored from backup, a file copied across the WSL boundary with its original
    mtime, or a guest whose clock drifted while the host was suspended. Read as
    an ordinary age, ``now - timestamp`` goes negative and satisfies *every*
    ``<= threshold`` comparison built on it — so the session reads Working, and
    keeps reading Working, for as long as the skew lasts. A clock a day ahead
    buys a day of phantom activity and phantom output tokens.

    Note that merely clamping the result at zero does not help: zero reads as
    "just now", which is still fresh. An implausible timestamp has to be
    rejected outright so no activity is invented from it. Overshoots within
    ``config.future_skew_tolerance_sec`` are clamped instead of rejected, because
    at that scale they are sampling noise — ``stat()`` and the collection clock
    are read microseconds apart, and coarse filesystems (FAT's two-second write
    time, some network mounts) round upward.
    """
    if timestamp - now > config.future_skew_tolerance_sec:
        return None
    return max(0.0, now - timestamp)


def is_fresh(config: RuntimeConfig, now: float, timestamp: float, window_sec: float) -> bool:
    """Whether ``timestamp`` is a plausible time within ``window_sec`` of now."""
    seconds = age(config, now, timestamp)
    return seconds is not None and seconds <= window_sec


def reset_fields(now: float, epoch: float) -> dict[str, Any]:
    """Both forms of one reset stamp, so they cannot drift apart.

    `reset` is the wall-clock words and `resetAt` is the instant. The page shows
    a countdown built from `resetAt` and keeps the words for the tooltip: "Thu
    02:00" answers "when", but the question a quota window actually raises is
    "how long until I get it back", and the reader should not have to subtract.
    Sending the instant rather than a server-rendered countdown also keeps the
    figure true between polls instead of ageing by up to the poll interval.
    """
    return {"reset": format_reset(now, epoch), "resetAt": int(epoch)}


def format_reset(now: float, epoch: float) -> str:
    """Short local-time reset text for a quota window.

    Today reads as "14:00", within the coming week as "Thu 09:00", and anything
    further out as a date, because a weekly window can reset up to seven days
    away and an hour-of-day alone would name the wrong day.
    """
    then = datetime.fromtimestamp(epoch, tz=UTC).astimezone()
    ref = datetime.fromtimestamp(now, tz=UTC).astimezone()
    if then.date() == ref.date():
        return then.strftime("%H:%M")
    if 0 <= (then - ref).total_seconds() < 7 * 86400:
        return then.strftime("%a %H:%M")
    return then.strftime("%b %d")


def newest_plausible(config: RuntimeConfig, now: float, timestamps: Iterable[float]) -> float:
    """Newest timestamp that is not implausibly ahead of ``now``; 0 if none.

    Every activity decision goes through this rather than ``max()``. ``max()``
    picks the *implausible* value — a future timestamp is by definition the
    largest — so rejecting it afterwards throws away the good evidence too, and
    a transcript being written right now but holding one clock-skewed record
    reads Idle. That is the opposite of what rejecting future timestamps is
    for. It also matters for display (a skewed value renders as "–") and for
    de-duplication, where it would beat a perfectly good copy of the session.

    Callers then test the result with ``is_fresh()``: freshness is monotonic in
    the timestamp, so checking the newest plausible source is equivalent to
    checking them all, at half the work on every five-second refresh.
    """
    return max((t for t in timestamps if age(config, now, t) is not None), default=0.0)


def base_session(harness: str, sid: Any, project: str) -> Session:
    # "session" is the display id. The 8 below is the floor and must match
    # config.display_id_len, which assign_display_ids() reads; nothing enforces
    # that they agree. assign_display_ids() widens it per (harness, project)
    # group where that floor collides. "sid" keeps the full identity so the client
    # can key per-session state without truncation collisions (e.g. two Gemini
    # "session-*" fallback ids are one string apart at the floor). Claude passes
    # its 8-char prefix, already its key upstream, so sid == session there.
    # `provider` and `model` are the authority a session is spending and the
    # model it is spending it on. Declared here for every harness, at None, so
    # the payload's shape does not depend on which collector filled a row: a key
    # that appears only for some harnesses makes every consumer test for
    # presence rather than for a value. Only Pi populates them today, because
    # Pi is the one harness with no authority of its own and therefore the one
    # where the answer is not already the harness name.
    #
    # `provider` is the vendor's own id, unmapped (`openai-codex`, not
    # `codex`). Naming is presentation and belongs to the page, which has the
    # harness table; the payload stays the raw reading.
    return {
        "session": str(sid)[:8],
        "sid": str(sid),
        "harness": harness,
        "project": project,
        "provider": None,
        "model": None,
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
        "spacedock": None,
    }


def dedupe_sessions(sessions: list[Session]) -> list[Session]:
    """Collapse sessions found in more than one candidate store.

    Scanning every candidate root means a session left behind by a migration
    can be discovered twice. Most collectors key by session id internally and
    merge naturally, but the database-backed ones append per store — so the
    same id produced two rows and counted its tokens twice in the summary.
    The freshest copy wins.
    """
    best: dict[tuple[str, str], Session] = {}
    for session in sessions:
        key = (str(session["harness"]), str(session["sid"]))
        current = best.get(key)
        if current is None or session["last_activity"] > current["last_activity"]:
            best[key] = session
    return list(best.values())


def assign_display_ids(config: RuntimeConfig, sessions: list[Session]) -> None:
    """Widen each session's display id until it is unique among the rows it
    could be confused with.

    Codex hands out UUIDv7, whose leading 48 bits are a millisecond timestamp.
    A fan-out launched in one directory therefore shares its leading hex, and
    an 8-char display id rendered several distinct sessions as the same
    harness, project and id — one session, apparently.

    The group is ``(harness, project)`` because that is exactly what a row
    prints beside the id, so those are the rows a reader has to tell apart.
    Widening per harness instead would drag every unrelated row in that harness
    out to the width one colliding fan-out needed: four agents started in the
    same millisecond need 16 to 18 characters, and a lone session in another
    worktree would inherit that for nothing.

    Mutates ``session["session"]`` only. ``sid`` is what every caller keys on
    and is left whole.
    """
    groups: dict[tuple[str, str], list[Session]] = {}
    for session in sessions:
        groups.setdefault((str(session["harness"]), str(session["project"])), []).append(session)
    for group in groups.values():
        sids = [str(s["sid"]) for s in group]
        width = config.display_id_len
        longest = max((len(sid) for sid in sids), default=config.display_id_len)
        # Terminates: width strictly increases and is bounded by the longest
        # sid, where every prefix is the whole id. Comparing distinct prefixes
        # against distinct sids also means repeated sids cannot drive it.
        while width < longest and len({sid[:width] for sid in sids}) != len(set(sids)):
            width += 1
        for session in group:
            session["session"] = str(session["sid"])[:width]


def rate_from(info: dict[str, Any] | None, now: float, config: RuntimeConfig) -> int:
    if not info:
        return 0
    recent: float = sum(
        tok for ep, tok in info["usage_events"] if is_fresh(config, now, ep, config.rate_window_sec)
    )
    return round(recent / (config.rate_window_sec / 60))


def working_detail(info: dict[str, Any] | None, subagents: list[Any]) -> str:
    if subagents:
        n = len(subagents)
        return f"running {n} subagent{'s' if n > 1 else ''}"
    if info and info.get("last_tool"):
        return f"running {info['last_tool']}"
    return "generating…"
