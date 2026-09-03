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
import os
import threading
from typing import TYPE_CHECKING, Any, Final, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from cargento_runtime.config import RuntimeConfig

# The file format version, and unlike `dismissals.SCHEMA_VERSION` this one is
# enforced. DEC-6 named only a corrupt store; the contract added "a version the
# running build does not understand", and the reason the repository should not
# grow a second inert version field is that it already has one: a fourteen-day
# time series whose reader must tolerate every past shape forever is how a silent
# mis-parse ships.
SCHEMA_VERSION: Final = 1

STORE_FILENAME: Final = "cargento-history.json"

# Why the store reports which reset it was: a corruption reset may be the user's
# disk, a version reset is ours, and one message for both hides the difference.
RESET_UNREADABLE: Final = "unreadable"
RESET_VERSION: Final = "version"


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
    stamp = row.get("last_activity")
    if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or stamp <= 0:
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
        # every row, it is capped at the last two segments rather than being a
        # path, and it is never a raw working directory.
        "project": project if isinstance(project, str) else "",
        "state": str(state),
        "last_activity": float(stamp),
    }


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
    stamp = value.get("last_activity")
    if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
        return None
    return {
        "harness": str(harness),
        "sid": str(sid),
        "project": project,
        "state": str(state),
        "last_activity": float(stamp),
    }


def _payload(entries: Iterable[Observation]) -> bytes:
    return json.dumps({"v": SCHEMA_VERSION, "entries": [dict(entry) for entry in entries]}).encode(
        "utf-8"
    )


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
    # observation over the cap, and the read below refuses a file larger than it
    # so an oversized store never reaches this loop.
    while kept and len(_payload(kept)) > max_bytes:
        kept.pop(0)
    return tuple(kept)


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


def _decode(raw: bytes) -> tuple[tuple[Observation, ...], str | None]:
    """The store's bytes as observations, or which reset they earned.

    Split from `load` so neither half sits on ruff's return-statement cap; the
    reasons are the contract's three, and each is returned rather than collapsed
    because the header has to name which one it was.
    """
    try:
        data = json.loads(raw or b"null")
    except (ValueError, RecursionError):
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


def record(
    config: RuntimeConfig,
    rows: Iterable[Mapping[str, Any]],
    *,
    now: float,
    diagnostic_sink: Callable[[str], object] = print,
) -> tuple[Observation, ...]:
    """Record the transitions in one collection's rows, and return the store.

    A transition and not a sample: a row whose state matches the last observation
    already held for it records nothing, so the file grows with what changed
    rather than with how often the board was collected. The baseline comes from
    the store itself rather than from process memory, which is what stops the
    first collection after a restart from re-recording every session's current
    state as a fresh transition.
    """
    if not config.history_enabled:
        return ()
    held, _ = load(config)
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
    if not fresh:
        return held
    kept = evict(
        [*held, *fresh],
        now=now,
        retention_sec=config.history_retention_sec,
        max_bytes=config.history_max_bytes,
    )
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
        # Lazily, so building an application for `--diagnose` reads no store.
        self._opened = False

    def _open(self) -> None:
        if self._opened:
            return
        self._entries, self._reset = load(self._config)
        self._opened = True

    def record(self, rows: Iterable[Mapping[str, Any]], *, now: float) -> list[dict[str, Any]]:
        """Record this collection's transitions and return the whole history."""
        with self._lock:
            self._open()
            if not self._config.history_enabled:
                return []
            self._entries = record(self._config, rows, now=now, diagnostic_sink=self._sink)
            return [dict(entry) for entry in self._entries]

    def notice(self) -> str | None:
        """Which reset this run opened with, or None if it opened cleanly."""
        with self._lock:
            self._open()
            return self._reset
