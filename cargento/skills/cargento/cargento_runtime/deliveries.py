"""What became of each notification Cargento raised.

The first precondition of
[DEC-18](docs/design-reading-a-session.md#dec-18-an-unasked-reading-is-permitted-and-gated-on-delivery-first),
and the one it kept as a build gate: a raise that records no delivery outcome is
exactly the defect the review view exists to show. Measured before this
existed, nothing recorded a raise at all. The only trace was
`state.last_popup`, a cooldown floor held in memory, one float per key
and overwritten on every raise, so a signal that never left the machine and one
handed to the operating system left the same mark.

Named for the outcome rather than the event, because `raise` already means
something else on this board: the control that switches a terminal to a session.

A leaf, shaped on `dismissals`: `config` for the paths and caps, `records` for
the untrusted-input discipline, `io` for the diagnostic sink. It reads nothing
else in the runtime, which is what lets `notifications`, `aggregate` and
`http_api` all consult it.

## Durable rather than in memory, and that is the decision

An outcome held on `RuntimeState` would be the defect [DRC-4547] records one
layer over: an observed session end lives only in the memory of the process that
saw it, so a restart makes every finished session look like it merely went
quiet. The read here is deliberately later than the write, because the whole
framing is that you walked away and came back, and a restart in between is the
expected case rather than an edge. An in-memory record would also make the
sentence for "no record" fire for every raise before the last restart, and that
sentence must mean "this predates the record" rather than "this board forgot".

Not session history: `history.appended` keeps one transition per `(harness,
sid)` and skips an unchanged row, so two raises on one session collapse into
one and an outcome settled later is not expressible. Not the annotation store:
its `_record` refuses a session nobody annotated, and a raise fires on every
active row.

[DRC-4547](https://linear.app/recce/issue/DRC-4547)

## What may be said, and what may not

Four outcomes, one sentence each and never a shared one, which is
`reading.WITHHELD`'s rule for the same reason: folding causes together makes the
least true of them read as the most reassuring. A fifth sentence covers a raise
this store has no record of, and it says so rather than saying undelivered.

Nothing here claims a person saw anything. `osascript` exiting zero means the
scripting bridge accepted the call; it exits zero under Do Not Disturb and with
the hosting application's notifications switched off. That is the whole reason
`HANDED_TO_OS` is worded the way it is.

Two further sentences report the browser lane, under
[DEC-19](docs/design-reading-a-session.md#dec-19-the-page-may-report-a-lane-never-a-delivery):
the page may say whether a notification lane exists in it, and may never
report a delivery. The
negative one says no lane has been REPORTED since a moment, never that the raise
did not reach the reader, because a tab that opens sends a report and a tab that
closes sends none, so absence is stale in one direction only.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import TYPE_CHECKING, Any, Final, TypedDict

from . import io as runtime_io
from . import records

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .config import RuntimeConfig

SCHEMA_VERSION: Final = 1

# The four things a server-side attempt can end as. Tokens, not sentences: the
# notifier returns one of these and the prose is looked up, so no call site
# composes a claim about what happened.
OUTCOME_HANDED_OVER: Final = "handed-over"
OUTCOME_REFUSED: Final = "refused"
OUTCOME_DID_NOT_RETURN: Final = "did-not-return"
OUTCOME_NO_LANE: Final = "no-lane"

OUTCOMES: Final = (
    OUTCOME_HANDED_OVER,
    OUTCOME_REFUSED,
    OUTCOME_DID_NOT_RETURN,
    OUTCOME_NO_LANE,
)

# One sentence per outcome and never a shared one. Each names the observation
# first and the consequence second, and each distinguishes itself from its
# nearest neighbour in its own words rather than by omission.
DELIVERY: Final[dict[str, str]] = {
    # Deliberately not "delivered" and not "shown". The call returning says the
    # notification service accepted the request and nothing about whether a
    # banner was drawn or anyone was at the desk.
    OUTCOME_HANDED_OVER: (
        "Handed to this machine's notification service, which accepted it. Whether it was "
        "displayed, and whether anyone saw it, is not something that call reports."
    ),
    OUTCOME_REFUSED: ("The notification service returned an error, so no banner was created."),
    # A timeout is not a failure, and folding it into one is the same collapse
    # this module exists to refuse one level down.
    OUTCOME_DID_NOT_RETURN: (
        "The notification call was still running when its time limit expired, so what it did "
        "is unrecorded rather than known to have failed."
    ),
    OUTCOME_NO_LANE: (
        "This platform has no notification backend in this build, so nothing was sent from "
        "the server and no banner was attempted."
    ),
}

# A raise older than this record. It says what is true, which is that nothing
# was written down, and never that the raise went undelivered.
NO_RECORD: Final = (
    "This raise predates the delivery record, so what became of it was never written down."
)

# The two sentences of
# [DEC-19](docs/design-reading-a-session.md#dec-19-the-page-may-report-a-lane-never-a-delivery).
# Both sit BESIDE a `no-lane` outcome and never instead of one: the server
# saying it has no backend and the page saying whether it has one are
# different facts and the reader needs both.
BROWSER_LANE_REPORTED: Final = (
    "A dashboard tab reported a working notification lane, so the page may have raised one "
    "itself. Nothing reports back whether it did."
)
# The second sentence is load bearing and must not be trimmed to fit. Without it
# the first reads as "this did not reach you", which is what
# [DEC-19](docs/design-reading-a-session.md#dec-19-the-page-may-report-a-lane-never-a-delivery)
# forbids.
BROWSER_LANE_UNREPORTED: Final = (
    "No dashboard tab has reported a notification lane. A tab that opens sends a report and a "
    "tab that closes sends none, so this says nothing about whether the page raised one."
)


class Delivery(TypedDict):
    """One raise and what became of it.

    `lane` is which producer raised it, so adding a lane later adds a value
    rather than changing this shape, which is what the issue asks for. `at` is
    the server's clock at the attempt and never a value a caller sent.
    """

    harness: str
    sid: str
    at: float
    lane: str
    outcome: str


def store_path(config: RuntimeConfig) -> str:
    """Beside the state file, but not per port.

    `lifecycle.state_path` is `cargento-<port>.json` and is deleted on exit. What
    became of a raise is the reader's, not the instance's, so it survives both a
    restart and a different --port, for `dismissals.store_path`'s reason.
    """
    return os.path.join(config.state_home, "cargento-deliveries.json")


def _entry(value: Any) -> Delivery | None:
    """One untrusted record, or nothing.

    Type-checked on the way in as well as on the way out. Any local process can
    rewrite this file, so an outcome outside the closed set is dropped rather
    than published: the page looks the sentence up by token and an unknown one
    would render as nothing at all.
    """
    if not isinstance(value, dict):
        return None
    harness = records.safe_text(value.get("harness"), KEY_CAP_CHARS)
    sid = records.safe_text(value.get("sid"), KEY_CAP_CHARS)
    lane = records.safe_text(value.get("lane"), KEY_CAP_CHARS)
    outcome = value.get("outcome")
    at = records.norm_epoch(value.get("at"))
    if not harness or not sid or not lane or at <= 0:
        return None
    if outcome not in OUTCOMES:
        return None
    return {"harness": harness, "sid": sid, "at": at, "lane": lane, "outcome": outcome}


KEY_CAP_CHARS: Final = 200


def _bounded(entries: Iterable[Delivery], limit: int) -> tuple[Delivery, ...]:
    """The newest `limit` records, oldest evicted first.

    A count bound rather than a time to live, for `dismissals._bounded`'s
    reason and one of its own: the review surface reads across sessions, so an
    age bound would empty it exactly when a reader came back from a long
    absence, which is the case the whole feature is for.
    """
    ordered = sorted(entries, key=lambda entry: entry["at"])
    return tuple(ordered[-limit:]) if limit > 0 else ()


def load(config: RuntimeConfig) -> tuple[Delivery, ...]:
    """Every record on disk, or none if there is none to trust.

    Read to a cap with RecursionError caught, for `lifecycle.read_state`'s
    reason: deeply nested JSON blows the recursion limit rather than raising
    ValueError, and a corrupt store degrades to "no records" rather than taking
    down a collection. A malformed record is dropped on its own.
    """
    try:
        with open(store_path(config), "rb") as handle:
            raw = handle.read(config.delivery_read_cap_bytes + 1)
        if len(raw) > config.delivery_read_cap_bytes:
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
    return _bounded(parsed, config.delivery_max_entries)


def save(
    config: RuntimeConfig,
    entries: Iterable[Delivery],
    *,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Write the store, reporting whether it reached disk.

    Temp file plus `os.replace`, and `0o600` in the `os.open` call rather than a
    chmod afterwards, copied from `lifecycle.write_state`. `TypeError` and
    `RecursionError` are caught alongside the rest for `annotations.save`'s
    reason: an encoder that refuses a payload must not reach the caller as a
    dropped connection.
    """
    payload = {
        "v": SCHEMA_VERSION,
        "entries": [dict(entry) for entry in _bounded(entries, config.delivery_max_entries)],
    }
    target = store_path(config)
    tmp = f"{target}.{os.getpid()}.tmp"
    try:
        os.makedirs(config.state_home, mode=0o700, exist_ok=True)
        handle_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, target)
    except (OSError, ValueError, TypeError, RecursionError):
        runtime_io.diag(
            f"Cargento: could not write the delivery record {target}; "
            "what became of this raise will not be readable later",
            diagnostic_sink,
        )
        with contextlib.suppress(OSError, ValueError):
            os.unlink(tmp)
        return False
    return True


def record(
    config: RuntimeConfig,
    *,
    harness: str,
    sid: str,
    lane: str,
    outcome: str,
    now: float,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Append one outcome, and say whether it reached disk.

    Read-modify-write rather than an append, because the file is bounded and two
    dashboards may share it. An outcome outside the closed set is refused here
    as well as on read-back: a caller inventing one would otherwise publish a
    token the page cannot look up.
    """
    if outcome not in OUTCOMES:
        return False
    entry = _entry({"harness": harness, "sid": sid, "at": now, "lane": lane, "outcome": outcome})
    if entry is None:
        return False
    return save(config, [*load(config), entry], diagnostic_sink=diagnostic_sink)


def counts(entries: Iterable[Delivery]) -> dict[str, int]:
    """Attempts and hand-overs, separately, and never one figure.

    Two numbers because they answer different questions and a single ratio
    answers neither. Neither is a compliance figure: an attempt is what this
    board did, and a hand-over is what the notification service accepted. What a
    person saw is not in here and cannot be derived from it.
    """
    rows = list(entries)
    attempted = sum(1 for row in rows if row["outcome"] != OUTCOME_NO_LANE)
    return {
        "raises": len(rows),
        "attempted": attempted,
        "handed_over": sum(1 for row in rows if row["outcome"] == OUTCOME_HANDED_OVER),
    }


def published(entries: Iterable[Delivery], harness: str, sid: str) -> dict[str, Any]:
    """What one session's row says about the raises made against it."""
    mine = [row for row in entries if row["harness"] == harness and row["sid"] == sid]
    latest = max(mine, key=lambda row: row["at"], default=None)
    return {
        "delivery_outcome": latest["outcome"] if latest else "",
        "delivery_why": DELIVERY[latest["outcome"]] if latest else "",
        "delivery_at": latest["at"] if latest else None,
        "delivery_raises": len(mine),
    }
