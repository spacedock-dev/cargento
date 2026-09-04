"""Local history: what this server observed, kept on this machine.

The board is rebuilt from the harness stores on every start, so a restart used
to leave it with no memory of sessions that already ran. This module owns the
one file that answers that, and `SECURITY.md`'s "Local history (the session
history store)" section is the contract it implements. The bounds are DEC-6's
ruling (Linear DRC-4234) as written into that contract, not this module's
preferences.

A leaf: `config` for the paths and the bounds, and nothing else. It is the shape
`git_status.py` took rather than the shape `dismissals.py` took, deliberately —
`dismissals` reaches `records` and `io`, and a store written continuously by the
collection lane must not be able to reach a module that could grow an edge back
toward it. The diagnostic sink is a parameter for the same reason.

Why a derived record rather than a row copy: the contract's one rule is that the
store holds nothing the live snapshot does not already serve, and the enforceable
reading of that is field provenance — every field written is one the board
already publishes. A retained row would satisfy it on its face and violate it in
its nested carriers, because a row's `tasks` and `subagents` hold operator text
the never-list bans and the contract's own never-list does not enumerate. So what
is written is five named fields and never a row, which makes the rule satisfiable
by construction instead of by review.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import threading
from typing import TYPE_CHECKING, Any, Final, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from cargento_runtime.config import RuntimeConfig

# The file format version, and unlike `dismissals.SCHEMA_VERSION` this one is
# enforced. DEC-6 named only a corrupt store; the contract added "a version the
# running build does not understand", and the reason the repository should not
# grow a second inert version field is that it already has one: a fourteen-day
# time series whose reader must tolerate every past shape forever is how a silent
# mis-parse ships.
SCHEMA_VERSION: Final = 1

STORE_FILENAME: Final = "cargento-history.json"

# What a stored string may occupy. The identity fields are far shorter than this
# (Claude publishes an 8-character sid, the longest harness key is 11) and the
# project label is capped at two segments by the collector that derives it, so
# this is a ceiling on a tampered file rather than a bound any real value meets.
FIELD_CAP_CHARS: Final = 256

# C0 and DEL, the zero-width space, the two directional marks, and the bidi
# embedding and isolate ranges, mirroring `records._UNSAFE_CHARS`. Inlined
# rather than imported because this module imports `config` and nothing else,
# and the reason it is here at all is that these four strings reach the DOM
# through `/api/data`: this file is one any local process could have replaced,
# and a bidi mark in a project label reorders how the row renders around it. The
# credential redaction `records.safe_text` also does is not repeated, and does
# not need to be — every value written here came off a row that had already been
# through it, so the only strings this guards are an attacker's own.
_UNSAFE_CHARS = re.compile("[\x00-\x1f\x7f\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069]+")

# Why the store reports which reset it was: a corruption reset may be the user's
# disk, a version reset is ours, and one message for both hides the difference.
RESET_UNREADABLE: Final = "unreadable"
RESET_VERSION: Final = "version"

# How many segments a stored project label may hold. The captain's D4 ruling
# authorized the derived two-segment label the board groups by and nothing
# wider, and the never-list bans a working directory outright.
PROJECT_SEGMENT_CAP: Final = 2


class Observation(TypedDict):
    """One state transition this server observed, and when.

    Five fields, every one of them already published on the row this was derived
    from. `project` is the derived two-segment label the board groups by, kept by
    the captain's D4 ruling of 2026-09-03 and never a raw working directory.
    """

    harness: str
    sid: str
    project: str
    state: str
    last_activity: float


# Written out rather than derived from `Observation.__annotations__`, so the
# oracle that checks this set against the published row fields is comparing two
# independent statements rather than one restated twice.
OBSERVATION_FIELDS: Final[tuple[str, ...]] = (
    "harness",
    "sid",
    "project",
    "state",
    "last_activity",
)


def store_path(config: RuntimeConfig) -> str:
    """Where the history lives: beside the dismissals file, and not per port.

    `lifecycle.state_path` is `cargento-<port>.json` and is deleted on exit. A
    history of what was observed is the machine's, not the instance's, so it must
    survive both a restart and a different --port.
    """
    return os.path.join(config.state_home, STORE_FILENAME)


def observation(row: Mapping[str, Any]) -> Observation | None:
    """One published row as an observation, or nothing.

    Nothing when the row carries no activity reading: a stamp of 0 is the
    declared default rather than a measurement, and recording it would put an
    observation at the epoch that age eviction drops on its next pass. One-sided
    on purpose, the way the overlay activity guards are — it declines to record,
    and never invents a time.
    """
    # `stamp <= 0` cannot stand alone: every comparison against NaN is false,
    # so the guard that rejects the declared default admitted the one value
    # that has no order. `_finite` is where that is refused.
    stamp = _finite(row.get("last_activity"))
    if stamp is None or stamp <= 0:
        return None
    harness, sid, state = row.get("harness"), row.get("sid"), row.get("state")
    if not all(isinstance(x, str) and x for x in (harness, sid, state)):
        return None
    project = row.get("project")
    return {
        "harness": str(harness),
        "sid": str(sid),
        # Kept by the captain's D4 ruling: both panels group by this label and
        # cannot be seeded without a grouping key. It is already published on
        # every row, and it is bounded here to the two segments that ruling
        # authorized rather than trusted to be that already — a row whose
        # collector fell back to the encoded directory name carries a whole
        # home-relative path, which the never-list bans outright.
        "project": _bounded_project(project) if isinstance(project, str) else "",
        "state": str(state),
        "last_activity": stamp,
    }


def _bounded_project(label: str) -> str:
    """A project label trimmed to its last two path segments.

    Both label producers cap themselves now — `sessions.project_from_cwd` at two
    path segments, and `sessions.bounded_project_label` at two segments of the
    dash-encoded fallback — so what arrives here is bounded already and this is
    the store's own guarantee rather than the row's.

    There used to be a second branch splitting a label with no `/` on `-`, and it
    is gone rather than fixed: a dash-encoded path and a hyphenated directory
    name are the same string by the time they reach this module, so the split
    truncated correct labels. Measured on real directories, `my-cool-project`
    was stored as `cool-project` and `spacedock-ensign-drc-4044` as `drc-4044`,
    which grouped a project's history under a different name than the live board
    and left the seeded panels with nothing to show for it (DRC-4044 DR-8). The
    fix is the bound moving to `sessions`, where the label is being built by
    joining path segments and the difference is still known.
    """
    return "/".join(label.split("/")[-PROJECT_SEGMENT_CAP:])


def _finite(value: Any) -> float | None:
    """One numeric field as a finite float, or nothing.

    Three shapes `isinstance` alone admits are refused here. A bool, which is
    an int. `Infinity` and `NaN`, which Python's `json` accepts as an extension
    and a tampered store can therefore carry. And an integer too large for a
    float, which `float()` refuses with OverflowError rather than ValueError —
    the class that was not in any except tuple, and so escaped the read
    boundary entirely.

    The cost of admitting one is not this record: a stamp that cannot be ordered
    reorders eviction, and a non-finite one makes `json.dumps` emit a bare
    `Infinity` token that `JSON.parse` rejects, which loses the whole
    `/api/data` body rather than one row.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except OverflowError:
        return None
    return numeric if math.isfinite(numeric) else None


def _text(value: Any) -> str:
    """One stored string, stripped of reordering characters and bounded."""
    return _UNSAFE_CHARS.sub(" ", str(value))[:FIELD_CAP_CHARS]


def _entry(value: Any) -> Observation | None:
    """One untrusted record as an observation, or nothing.

    Every field is re-validated on the way in, because this file is one any local
    process could have replaced. A malformed record is dropped on its own rather
    than discarding the rest of the history.
    """
    if not isinstance(value, dict):
        return None
    harness, sid = value.get("harness"), value.get("sid")
    project, state = value.get("project"), value.get("state")
    if not all(isinstance(x, str) and x for x in (harness, sid, state)):
        return None
    if not isinstance(project, str):
        return None
    stamp = _finite(value.get("last_activity"))
    if stamp is None:
        return None
    return {
        "harness": _text(harness),
        "sid": _text(sid),
        "project": _text(project),
        "state": _text(state),
        "last_activity": stamp,
    }


def _payload(entries: Iterable[Observation]) -> bytes:
    return json.dumps({"v": SCHEMA_VERSION, "entries": [dict(entry) for entry in entries]}).encode(
        "utf-8"
    )


# The store's serialised size, derived from the records' own lengths rather
# than by re-serialising the whole file. `_payload` is `json.dumps` with its
# default separators, so a store is the empty envelope, plus each record, plus
# the two bytes (`, `) that join one record to the next; `ensure_ascii` is on
# by default, so one character is one byte and the arithmetic is exact rather
# than an estimate. `test_history` pins it against `_payload` itself.
_EMPTY_STORE_BYTES: Final = len(_payload(()))
_RECORD_SEPARATOR_BYTES: Final = 2


def _store_bytes(lengths: Sequence[int]) -> int:
    if not lengths:
        return _EMPTY_STORE_BYTES
    return _EMPTY_STORE_BYTES + sum(lengths) + _RECORD_SEPARATOR_BYTES * (len(lengths) - 1)


def evict(
    entries: Iterable[Observation],
    *,
    now: float,
    retention_sec: float,
    max_bytes: int,
) -> tuple[Observation, ...]:
    """The observations that survive both bounds, oldest dropped first.

    Age first, then the size cap, and that ordering is the contract's rather than
    a preference: evicting on size first would drop a recent observation to make
    room while an observation already outside the window survived, and raising the
    cap afterwards would then appear to bring history back. It cannot — what left
    the file is gone from it — so the two bounds have to be applied in the order
    that makes the file's contents mean what the retention figure says.
    """
    kept = sorted(
        (e for e in entries if now - e["last_activity"] <= retention_sec),
        key=lambda e: e["last_activity"],
    )
    # One at a time, not a proportion: in steady state the store is at most one
    # observation over the cap. Sized from each record's own length, though,
    # rather than by re-serialising the whole store after every drop — that loop
    # cost 4.505 s and 593 `json.dumps` calls on a store an external tool had
    # compacted, inside the collection memo lock on a thread that can be
    # answering a request. And the premise it leaned on, that "an oversized
    # store never reaches this loop", was false for exactly that reason: `load`
    # caps the raw file's bytes while `_payload` re-serialises 8.16% larger, so
    # a file that parses inside the cap can exceed it on the way back out.
    lengths = [len(json.dumps(dict(entry))) for entry in kept]
    size = _store_bytes(lengths)
    dropped = 0
    while dropped < len(kept) and size > max_bytes:
        joined = _RECORD_SEPARATOR_BYTES if len(kept) - dropped > 1 else 0
        size -= lengths[dropped] + joined
        dropped += 1
    return tuple(kept[dropped:])


def load(config: RuntimeConfig) -> tuple[tuple[Observation, ...], str | None]:
    """Every observation on disk, and which reset was needed to get there.

    A store that cannot be read is discarded rather than repaired, and the reason
    is returned so the header can name it. `None` with no entries is the ordinary
    first run: no file is not a reset, and reporting one would tell a new user
    their history had been lost.

    RecursionError is caught for the reason `lifecycle.read_state` catches it:
    deeply nested JSON blows the recursion limit rather than raising ValueError.
    """
    if not config.history_enabled:
        return (), None
    path = store_path(config)
    cap = config.history_max_bytes
    try:
        with open(path, "rb") as handle:
            raw = handle.read(cap + 1)
    except FileNotFoundError:
        return (), None
    except OSError:
        return (), RESET_UNREADABLE
    if len(raw) > cap:
        return (), RESET_UNREADABLE
    return _decode(raw)


def _numeric(text: str) -> float:
    """One JSON numeric literal as a finite float, or a reset for the store.

    Handed to `json.loads` as its three number hooks, which is the only place
    these shapes can be told apart from a record this build wrote. `Infinity`
    and `NaN` are not JSON at all — Python's decoder accepts them as an
    extension — and an integer no float can hold is not a stamp any clock
    produced, so a file carrying either did not come from `save`. That makes it
    the contract's "corrupt bytes" case, dropped whole with the reset the header
    names, rather than the malformed-*record* case beside it, which is dropped
    on its own so one bad line cannot cost a fortnight of history.
    """
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number: {text[:32]}")
    return value


def _decode(raw: bytes) -> tuple[tuple[Observation, ...], str | None]:
    """The store's bytes as observations, or which reset they earned.

    Split from `load` so neither half sits on ruff's return-statement cap; the
    reasons are the contract's three, and each is returned rather than collapsed
    because the header has to name which one it was.
    """
    try:
        data = json.loads(
            raw or b"null",
            parse_float=_numeric,
            parse_int=_numeric,
            parse_constant=_numeric,
        )
    # OverflowError cannot be raised here while the three hooks above are
    # installed: an oversized integer literal reaches `_numeric` as text,
    # `float()` returns `inf` rather than raising, and `math.isfinite` turns it
    # into the ValueError beside it. Kept anyway, and named as unreachable
    # rather than deleted, because it is one class in a tuple and the shape it
    # guards against — a numeric no float can hold escaping this boundary — took
    # a live server down permanently once. The reachable copy is at
    # `Lane._open`, where removing it goes red.
    except (ValueError, RecursionError, OverflowError):
        return (), RESET_UNREADABLE
    if not isinstance(data, dict):
        return (), RESET_UNREADABLE
    if data.get("v") != SCHEMA_VERSION:
        # Enforced, unlike the dismissal store's: see SCHEMA_VERSION above.
        return (), RESET_VERSION
    entries = data.get("entries")
    if not isinstance(entries, list):
        return (), RESET_UNREADABLE
    parsed = [e for e in (_entry(value) for value in entries) if e is not None]
    return tuple(parsed), None


def save(
    config: RuntimeConfig,
    entries: Iterable[Observation],
    *,
    diagnostic_sink: Callable[[str], object] = print,
) -> bool:
    """Write the store, reporting whether it reached disk.

    Temp file plus os.replace, and 0o600 in the `os.open` call rather than a chmod
    afterwards, both copied from `lifecycle.write_state`: a reader mid-write sees
    the old file or the new one, and the file is never briefly world-readable. The
    mode is advisory and Windows ignores it, which SECURITY.md records rather than
    implying isolation.

    False rather than an exception, because the caller's answer to a failed write
    is to carry on collecting: losing an observation is survivable, stopping the
    collection lane over it is not.
    """
    if not config.history_enabled:
        return False
    target = store_path(config)
    tmp = f"{target}.{os.getpid()}.tmp"
    try:
        os.makedirs(config.state_home, mode=0o700, exist_ok=True)
        handle_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(_payload(entries))
        os.replace(tmp, target)
    except (OSError, ValueError):
        _report(
            f"Cargento: could not write the history store {target}; "
            "the board will open with no memory of this run",
            diagnostic_sink,
        )
        with contextlib.suppress(OSError, ValueError):
            os.unlink(tmp)
        return False
    return True


def appended(
    held: tuple[Observation, ...],
    rows: Iterable[Mapping[str, Any]],
    *,
    now: float,
    retention_sec: float,
    max_bytes: int,
) -> tuple[tuple[Observation, ...], bool]:
    """The history after this collection, and whether anything actually changed.

    A transition and not a sample: a row whose state matches the last
    observation already held for it records nothing. That is load-bearing
    rather than tidy — the coordinator collects at least every
    `reconcile_interval_sec` whether or not anything moved, so a per-cycle
    append would write thousands of records a day per session into a store
    nothing had happened in.

    The bool is what lets the caller skip the write on a quiet board, so an idle
    Cargento touches the file exactly never.
    """
    latest: dict[tuple[str, str], Observation] = {}
    for entry in held:
        key = (entry["harness"], entry["sid"])
        current = latest.get(key)
        if current is None or entry["last_activity"] >= current["last_activity"]:
            latest[key] = entry
    fresh: list[Observation] = []
    for row in rows:
        observed = observation(row)
        if observed is None:
            continue
        previous = latest.get((observed["harness"], observed["sid"]))
        if previous is not None and previous["state"] == observed["state"]:
            continue
        latest[(observed["harness"], observed["sid"])] = observed
        fresh.append(observed)
    if not fresh and not any(now - e["last_activity"] > retention_sec for e in held):
        # Nothing appended and nothing expired: the size cap cannot be newly
        # exceeded by a store nothing was added to, so a quiet board pays one
        # comparison per record instead of the sizing pass, and touches the file
        # exactly never. A quiet board with expired records in it does fall
        # through — retention used to be reachable only from a write, so a
        # finished project or a machine left running with no active sessions kept
        # its observations past the window, on disk and in `/api/data`.
        return held, False
    kept = evict([*held, *fresh], now=now, retention_sec=retention_sec, max_bytes=max_bytes)
    # Compared rather than assumed: a fresh observation already outside the
    # window leaves the file it would have been written to unchanged, and
    # rewriting identical bytes is what the quiet-board oracle forbids.
    return kept, kept != held


def record(
    config: RuntimeConfig,
    rows: Iterable[Mapping[str, Any]],
    *,
    now: float,
    diagnostic_sink: Callable[[str], object] = print,
) -> tuple[Observation, ...]:
    """One-shot record: read the store, append this collection, write it back.

    The baseline comes from the store itself, which is what stops a fresh
    process from re-recording every session's current state as a new
    transition. `Lane` does not use this on the serving path — it holds its
    baseline in memory instead, because re-reading a full store costs 23 ms
    against the write's 6 and the collection it rides on may be answering an
    HTTP request. This one stays for a caller that owns no lane.
    """
    if not config.history_enabled:
        return ()
    held, _ = load(config)
    kept, changed = appended(
        held,
        rows,
        now=now,
        retention_sec=config.history_retention_sec,
        max_bytes=config.history_max_bytes,
    )
    if changed:
        save(config, kept, diagnostic_sink=diagnostic_sink)
    return kept


def forget(config: RuntimeConfig) -> bool:
    """Delete the store. True when a file was removed.

    Independent of `history_enabled`, because the contract says so and the reason
    is the user's: someone turning the feature off and then asking for the file to
    go must not be told there was nothing to delete.
    """
    try:
        os.unlink(store_path(config))
    except OSError:
        return False
    return True


def _report(message: str, sink: Callable[[str], object]) -> None:
    """`io.diag`, inlined so this module stays a leaf over `config` alone."""
    try:
        sink(message)
    except (OSError, ValueError):
        with contextlib.suppress(OSError, ValueError):
            sink(message.encode("ascii", "backslashreplace").decode("ascii"))


class Lane:
    """One process's recording lane: the store, and which reset it opened with.

    Constructed at assembly and injected into the collection rather than reached
    through the overlay source, and that placement is load-bearing rather than a
    preference. `Application.overlays` is None forever under `--no-events`, so a
    lane reached that way would be an off switch with a second, undocumented
    name — and the contract says the off switch is `--no-history`. Governed by
    that flag alone, it records on every run that collects at all.

    The reset reason is latched on the first read and then kept for the life of
    the process, because it is a fact about this run: the store is rewritten by
    the first recording that follows, so a reason re-derived per collection would
    announce the reset once and then fall silent while the board it emptied was
    still on screen.
    """

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        diagnostic_sink: Callable[[str], object] = print,
    ) -> None:
        self._config = config
        self._sink = diagnostic_sink
        self._lock = threading.Lock()
        self._entries: tuple[Observation, ...] = ()
        self._reset: str | None = None
        self._opened = False

    def _open(self) -> None:
        if self._opened:
            return
        # Latched before the read, not after it. `load` is bounded but it was
        # not infallible, and a read that raised left this False — so the next
        # collection re-read the same file and raised again, and a tampered
        # store took the board down permanently instead of being discarded once.
        # The contract's rule is that a store which cannot be read is discarded,
        # and that has to hold for a read that fails as well as for one that
        # returns a reason.
        self._opened = True
        try:
            self._entries, self._reset = load(self._config)
        except (OSError, ValueError, RecursionError, OverflowError):
            self._entries, self._reset = (), RESET_UNREADABLE

    def _forget_a_deleted_baseline(self) -> None:
        """Drop the in-memory baseline when the file it was read from is gone.

        `--forget` refuses while a dashboard answers on the port it names, but a
        delete is a file operation and this baseline is a copy in memory: a
        store removed by hand, or by a `--forget` aimed at another port, would
        otherwise be written back whole on the next transition and the delete
        would appear to have done nothing. Existence rather than an mtime,
        because a removal is exactly what has to be noticed, and it is one
        `stat` on a path this lane is about to write anyway.
        """
        if self._entries and not os.path.exists(store_path(self._config)):
            self._entries = ()

    def record(self, rows: Iterable[Mapping[str, Any]], *, now: float) -> list[dict[str, Any]]:
        """Record this collection's transitions and return the whole history.

        The baseline is this lane's own copy, loaded once when it opened, rather
        than a fresh read of the file. Measured at the 1 MiB cap: re-reading
        costs 23 ms where the write costs 6, and this runs inside the collection
        that may be answering a `GET /api/data` on a request thread, so the
        re-read was the expensive half of a cost paid on somebody's response.
        What a re-read would buy is a second dashboard's records, and whole-file
        last-writer-wins between two dashboards is an exposure `SECURITY.md`
        already carries for the dismissal store.

        Nothing is written when nothing changed, so a quiet board never touches
        the file.
        """
        with self._lock:
            self._open()
            if not self._config.history_enabled:
                return []
            self._forget_a_deleted_baseline()
            kept, changed = appended(
                self._entries,
                rows,
                now=now,
                retention_sec=self._config.history_retention_sec,
                max_bytes=self._config.history_max_bytes,
            )
            self._entries = kept
            if changed:
                save(self._config, kept, diagnostic_sink=self._sink)
            return [dict(entry) for entry in kept]

    def notice(self) -> str | None:
        """Which reset this run opened with, or None if it opened cleanly."""
        with self._lock:
            self._open()
            return self._reset
