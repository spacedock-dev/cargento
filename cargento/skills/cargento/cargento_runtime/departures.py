"""The departures Cargento raised without being asked, and their baselines.

[DEC-18](docs/design-reading-a-session.md#dec-18-an-unasked-reading-is-permitted-and-gated-on-delivery-first)
permits an unasked reading and adds one amendment this module exists for: every
raise persists the annotation revision and the evidence cutoff it rested on. By
the time the reader comes back the annotation may be at a later revision and the
evidence window has moved, so a raise that does not carry its own baseline cannot
be understood on return.

Durable, for `deliveries`' reason and one of its own: the whole framing is that
you were away, so the read is later than the write by design and a restart in
between is the expected case rather than an edge.

A leaf, shaped on `deliveries`: `config` for the paths and caps, `records` for
the untrusted-input discipline, `io` for the diagnostic sink. It reads nothing
else in the runtime, which is what lets `unasked`, `aggregate` and `http_api`
all consult it.

## The lock is not optional here

`deliveries` shipped this shape without one and lost records: an unlocked
read-modify-write with three threads reaching it, plus a temp name shared by
every thread in the process. Measured there, two barrier-synchronised writers
lost a record in 60 of 60 trials. This module has the lock and the per-thread
temp name from its first commit rather than after the same measurement.

## What may be said, and what may not

Only a departure is ever stored, because only a departure is ever raised. The
ruling at the top of this file refuses an unasked `consistent`: an unasked
reassurance is the output the evidence-floor ruling called most damaging, and it
has no value at all to someone away from the desk.

Nothing here is a rate. A count of departures on one session identifies a
session worth reading; it establishes nothing about whether the brief was poor,
the agent was poor, or Cargento's own judgement was poor, and those three are
not separable from the number.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from typing import TYPE_CHECKING, Any, Final, TypedDict

from . import io as runtime_io
from . import records

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .config import RuntimeConfig

SCHEMA_VERSION: Final = 1

KEY_CAP_CHARS: Final = 200
# The reading and its evidence line as the producer wrote them. Bounded because
# any local process can rewrite this file and the page renders what it holds.
TEXT_CAP_CHARS: Final = 600

# Held across the read-modify-write in `record`. See the module docstring: this
# is the half `deliveries` shipped without and had to be measured into.
_WRITE_LOCK: Final = threading.Lock()

# What the board says when the lane is on and has raised nothing on this
# session. Distinct from the exhausted sentence below, and that distinction is
# the second amendment of the ruling cited at the top of this file: the
# reader is by construction not present, so
# "nothing departed" and "nothing was checked" must never render alike.
NOTHING_DEPARTED: Final = (
    "Cargento has checked this session against what you asked for and found nothing to raise."
)
NEVER_CHECKED: Final = (
    "Cargento has not checked this session against what you asked for. Nothing here says whether "
    "it would have found anything."
)
SESSION_EXHAUSTED: Final = (
    "This session has reached its limit of unasked checks, so no further check will run on it. "
    "That is a limit being spent, not a session found to be on track."
)
DAY_EXHAUSTED: Final = (
    "This board has reached its limit of unasked checks for the day, so no further check will run "
    "on any session. That is a limit being spent, not a board found to be on track."
)


class Departure(TypedDict):
    """One departure raised, and the baseline it rested on.

    `revision` and `cutoff` are the first amendment of the ruling cited at the
    top of this file: the annotation revision the
    reading read, and the moment its evidence stopped. Both are recorded at
    raise time and never re-derived, because by the time this is read neither is
    recoverable.
    """

    harness: str
    sid: str
    at: float
    constraint: str
    clause: str
    reading: str
    evidence: str
    revision: int
    cutoff: float


def store_path(config: RuntimeConfig) -> str:
    """Beside the state file, and not per port, for `deliveries.store_path`'s reason."""
    return os.path.join(config.state_home, "cargento-departures.json")


def _entry(value: Any) -> Departure | None:
    """One untrusted record, or nothing.

    Type-checked on the way in as well as on the way out, because any local
    process can rewrite this file and every string here reaches the page.
    """
    if not isinstance(value, dict):
        return None
    harness = records.safe_text(value.get("harness"), KEY_CAP_CHARS)
    sid = records.safe_text(value.get("sid"), KEY_CAP_CHARS)
    constraint = records.safe_text(value.get("constraint"), KEY_CAP_CHARS)
    at = records.norm_epoch(value.get("at"))
    if not harness or not sid or not constraint or at <= 0:
        return None
    revision = value.get("revision")
    return {
        "harness": harness,
        "sid": sid,
        "at": at,
        "constraint": constraint,
        "clause": records.safe_text(value.get("clause"), KEY_CAP_CHARS),
        "reading": records.safe_text(value.get("reading"), TEXT_CAP_CHARS),
        "evidence": records.safe_text(value.get("evidence"), TEXT_CAP_CHARS),
        # 0 rather than a drop: a raise whose revision did not survive is still
        # a raise that happened, and the render says the baseline is missing
        # rather than hiding the row.
        "revision": revision if isinstance(revision, int) and not isinstance(revision, bool) else 0,
        "cutoff": records.norm_epoch(value.get("cutoff")),
    }


def _bounded(entries: Iterable[Departure], limit: int) -> tuple[Departure, ...]:
    """The newest `limit` records, oldest evicted first."""
    ordered = sorted(entries, key=lambda entry: entry["at"])
    return tuple(ordered[-limit:]) if limit > 0 else ()


def load(config: RuntimeConfig) -> tuple[Departure, ...]:
    """Every record on disk, or none if there is none to trust."""
    try:
        with open(store_path(config), "rb") as handle:
            raw = handle.read(config.departure_read_cap_bytes + 1)
        if len(raw) > config.departure_read_cap_bytes:
            return ()
        data = json.loads(raw or b"null")
    except (OSError, ValueError, RecursionError):
        return ()
    if not isinstance(data, dict):
        return ()
    entries = data.get("entries")
    if not isinstance(entries, list):
        return ()
    parsed = [entry for entry in (_entry(value) for value in entries) if entry is not None]
    return _bounded(parsed, config.departure_max_entries)


def save(
    config: RuntimeConfig,
    entries: Iterable[Departure],
    *,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Write the store, reporting whether it reached disk."""
    payload = {
        "v": SCHEMA_VERSION,
        "entries": [dict(entry) for entry in _bounded(entries, config.departure_max_entries)],
    }
    target = store_path(config)
    # Per thread as well as per process, for `deliveries.save`'s measured
    # reason: a shared name means two writers open it `O_TRUNC` on independent
    # descriptors and `os.replace` renames the interleaving over the store.
    tmp = f"{target}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        os.makedirs(config.state_home, mode=0o700, exist_ok=True)
        handle_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, target)
    except (OSError, ValueError, TypeError, RecursionError):
        runtime_io.diag(
            f"Cargento: could not write the departure record {target}; "
            "what was raised while you were away will not be readable later",
            diagnostic_sink,
        )
        with contextlib.suppress(OSError, ValueError):
            os.unlink(tmp)
        return False
    return True


def record(
    config: RuntimeConfig,
    entries: Iterable[Departure],
    *,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Append one reading's departures, and say whether they reached disk.

    Under `_WRITE_LOCK`, and a whole reading at once rather than one row per
    call: a reading's departures are one raise, and splitting them would let a
    restart between two writes publish half a raise.
    """
    fresh = [entry for entry in (_entry(dict(value)) for value in entries) if entry is not None]
    if not fresh:
        return False
    with _WRITE_LOCK:
        return save(config, [*load(config), *fresh], diagnostic_sink=diagnostic_sink)


def counts(
    entries: Iterable[Departure], harness: str, sid: str, *, since: float
) -> tuple[int, int]:
    """(this session's raises, this board's raises since `since`).

    Two numbers because the two caps are different questions: one session
    churning, and a whole board quietly spending a day's capacity.
    """
    rows = list(entries)
    mine = sum(1 for row in rows if row["harness"] == harness and row["sid"] == sid)
    return mine, sum(1 for row in rows if row["at"] >= since)


def published(entries: Iterable[Departure], harness: str, sid: str) -> list[dict[str, Any]]:
    """This session's departures, newest first, as the board renders them."""
    mine = [row for row in entries if row["harness"] == harness and row["sid"] == sid]
    return [dict(row) for row in sorted(mine, key=lambda row: row["at"], reverse=True)]
