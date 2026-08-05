"""Untrusted lifecycle events, normalized before anything can act on them.

Every input here arrives from a hook process Cargento does not control, over a
loopback socket that is not a user boundary, in a shape whose adapter may be
older than the server reading it. This module is the whole of the validation: it
decides what an event means, which session it belongs to, and which display
fields it is allowed to influence. Nothing downstream re-checks it.

It is deliberately pure. No locks, no counters, no clock of its own, no
filesystem. `arrival_seq` is assigned by the ingress under its own lock and
passed in; the mutable pending map and overlay ledger live in the coordinator
that owns their bounds. Keeping this layer a set of functions over frozen values
is what makes the ordering rules below testable without a running server.

## Three separate ideas about order

`arrival_seq` is the server's own monotonic counter, assigned after
authentication and validation. It is the only ordering that fences a concurrent
collection, because it is the only one the server mints itself.

`(source_instance_id, source_sequence)` is optional and trusted only when a
native source supplies both. A fresh command-hook process cannot mint a shared
sequence, so most sources supply neither and get at-least-once, possibly
reordered delivery. Reducers are therefore idempotent.

Event timestamps drive displayed timing and plausibility only. They never fence
concurrency. A hook inside a container whose clock runs hours ahead must not be
able to pin a row, so an implausible stamp is replaced by server arrival time
rather than believed or rejected.

## Provenance, not recency

An overlay may patch only the fields in `PATCHABLE`. For everything else the
collector is authoritative: titles, projects, historical turns, tasks, token
rates, parent relationships and subagent reconstruction. That split is what lets
a long generation keep reading Working without letting a hook rewrite metadata
it has no knowledge of.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from cargento_runtime import sessions as runtime_sessions

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from cargento_runtime.config import RuntimeConfig

# The envelope version this build writes. Adapters live in user-owned
# configuration and are not upgraded when Cargento is, so the accepted range
# below is a public compatibility surface with an indefinite tail, not an
# internal wire format.
ENVELOPE_VERSION: Final = 1
SUPPORTED_VERSIONS: Final = frozenset({1})

# The normalized vocabulary. Adapters translate native names into these; a name
# outside the set is ignored rather than accepted into state, because an unknown
# name is indistinguishable from a typo in a hook someone wrote by hand.
EVENT_NAMES: Final = frozenset(
    {
        "session_started",
        "session_ended",
        "turn_started",
        "turn_stopped",
        "input_requested",
        "input_resolved",
        "subagent_started",
        "subagent_stopped",
        "tasks_changed",
        "store_changed",
        "reconcile_required",
    }
)

# Read from the envelope; everything else in a native payload is discarded
# rather than rejected, so a harness adding a field does not break its adapter.
ALLOWED_FIELDS: Final = frozenset(
    {
        "v",
        "event",
        "session_id",
        "timestamp",
        "source_instance_id",
        "source_sequence",
        "cwd",
        "subagent_id",
        "transcript_path",
    }
)

# Fields an overlay may patch. `acquisition` is the provenance marker: a row
# reached by events reads "event", and one reached only by scanning reads
# "scan-only", which is how the latency of a harness with no healthy event
# source gets disclosed instead of hidden.
PATCHABLE: Final = frozenset({"state", "state_detail", "active", "blocked_since", "acquisition"})

ACQUISITION_EVENT: Final = "event"
ACQUISITION_SCAN: Final = "scan-only"

# Rejection reasons. `incompatible` is reported through --diagnose and the
# acquisition strip rather than dropped silently, because an adapter too old for
# this server is a state the user can fix and the unknown-name rule would
# otherwise hide it.
REJECT_INCOMPATIBLE: Final = "incompatible"
REJECT_UNKNOWN_EVENT: Final = "unknown-event"
REJECT_MALFORMED: Final = "malformed"
REJECT_UNKNOWN_HARNESS: Final = "unknown-harness"
REJECT_UNMAPPABLE: Final = "unmappable-id"

# Bounds on the string fields. The ingress caps the whole body; these cap each
# field, so one enormous but legal-looking value cannot be stored or logged.
MAX_ID_LEN: Final = 200
MAX_PATH_LEN: Final = 4096

# Overlay kinds, in the order the design derives them from native events.
OVERLAY_WORKING: Final = "working"
OVERLAY_NEEDS_INPUT: Final = "needs_input"
OVERLAY_IDLE: Final = "idle"
OVERLAY_SUBAGENT: Final = "subagent"

# Claude's session id is a UUID. Anything outside this alphabet is not one, and a
# forged value with a path separator in it must not reach a prefix lookup.
_UUID_CHARS: Final = frozenset("0123456789abcdefABCDEF-")
# The collector keys on the first eight characters of the transcript filename,
# so a shorter id cannot be mapped to exactly one row.
_CLAUDE_SID_LEN: Final = 8


@dataclass(frozen=True)
class Event:
    """One validated event, with its harness assigned by the ingress route.

    `sid` is the collector's key, not the native id: Claude's is the
    eight-character transcript prefix, and an overlay keyed on the raw UUID would
    never match its row. `session_id` is retained for diagnostics only.
    """

    harness: str
    event: str
    sid: str
    session_id: str
    timestamp: float
    arrival_seq: int
    source_instance_id: str | None = None
    source_sequence: int | None = None
    cwd: str | None = None
    subagent_id: str | None = None
    transcript_path: str | None = None


@dataclass(frozen=True)
class Rejected:
    """Why an envelope produced no event. One of the REJECT_* reasons."""

    reason: str


@dataclass(frozen=True)
class Overlay:
    """A live semantic claim about one session, ordered by `arrival_seq`.

    `effective_at` is how the Idle dwell is expressed: a stop overlay exists
    immediately but does not apply until the dwell passes, so a user who stops
    and prompts again inside one coalescing window never sees the row flap.

    `expires_at` is set for Working and left None for Needs input. That
    asymmetry is deliberate and load-bearing. A missed stop must not pin Working
    forever, so Working gets a measured deadline. A real permission wait can last
    hours, so retiring Needs input requires positive evidence and never a
    generic timeout.
    """

    harness: str
    sid: str
    arrival_seq: int
    kind: str
    at: float
    detail: str | None = None
    effective_at: float = 0.0
    expires_at: float | None = None
    subagent_id: str | None = None

    def applies(self, *, now: float) -> bool:
        if now < self.effective_at:
            return False
        return self.expires_at is None or now < self.expires_at


def _text(payload: Mapping[str, Any], key: str, *, limit: int) -> str | None:
    """An allowlisted string field, or None if absent, wrongly typed or oversized.

    Wrong types are discarded rather than rejected. These fields are optional
    hints; refusing the whole event because a harness started sending a number
    where it used to send a string would take out a working adapter over a field
    nothing depends on.
    """
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > limit:
        return None
    return value


def _parse_timestamp(raw: str | None, *, config: RuntimeConfig, now: float) -> float:
    """ISO-8601 to epoch seconds, falling back to arrival time.

    Both fallbacks land on `now`: an unparseable stamp and an implausible one are
    the same problem from the display's point of view, and neither may be allowed
    to invent activity. `sessions.age` is the same plausibility filter every
    store timestamp passes through, so a container clock hours ahead cannot pin a
    row here either.
    """
    if raw is None:
        return now
    text = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return now
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    stamp = parsed.timestamp()
    if runtime_sessions.age(config, now, stamp) is None:
        return now
    return stamp


def _claude_sid(session_id: str) -> str | None:
    """Claude's collector key: the first eight characters of the UUID.

    Rejects anything that is not UUID-shaped, and anything shorter than the
    prefix the collector keys on. A shorter id would match every row sharing its
    prefix, which is an ambiguous mapping rather than a lookup, and the identity
    rule is that ambiguity is refused rather than guessed.
    """
    if len(session_id) < _CLAUDE_SID_LEN:
        return None
    if any(char not in _UUID_CHARS for char in session_id):
        return None
    return session_id[:_CLAUDE_SID_LEN]


# One normalizer per harness whose adapter has shipped. A harness absent here is
# refused: the design requires the identity mapping to be established per harness
# before its adapter ships, and a default passthrough would quietly skip that.
IDENTITY_NORMALIZERS: Final[dict[str, Any]] = {
    "claude": _claude_sid,
}


def normalize_session_id(harness: str, session_id: str) -> str | None:
    """The collector key for a native id, or None if it cannot be mapped."""
    normalizer = IDENTITY_NORMALIZERS.get(harness)
    if normalizer is None:
        return None
    result = normalizer(session_id)
    return result if isinstance(result, str) and result else None


def _identify(harness: str, payload: Mapping[str, Any]) -> tuple[str, str, str] | Rejected:
    """Resolve name, native id and collector key, or say why none of them hold.

    Split out of `parse` so the accept path there reads as one construction. The
    checks are ordered, and the order is the contract: version first so an
    adapter too old for this server reports `incompatible` rather than tripping
    over a vocabulary it predates.
    """
    version = payload.get("v")
    # One condition, three ways to fail. `isinstance` comes first because a
    # missing or unhashable `v` would raise on the membership test, and the
    # `bool` clause is there because `bool` is an `int` in Python, so `True`
    # would otherwise read as version 1.
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version not in SUPPORTED_VERSIONS
    ):
        return Rejected(REJECT_INCOMPATIBLE)

    name = payload.get("event")
    if not isinstance(name, str) or name not in EVENT_NAMES:
        return Rejected(REJECT_UNKNOWN_EVENT)

    session_id = _text(payload, "session_id", limit=MAX_ID_LEN)
    if session_id is None:
        return Rejected(REJECT_MALFORMED)

    if harness not in IDENTITY_NORMALIZERS:
        return Rejected(REJECT_UNKNOWN_HARNESS)
    sid = normalize_session_id(harness, session_id)
    if sid is None:
        return Rejected(REJECT_UNMAPPABLE)
    return name, session_id, sid


def parse(
    harness: str,
    payload: Mapping[str, Any],
    *,
    arrival_seq: int,
    config: RuntimeConfig,
    now: float,
) -> Event | Rejected:
    """Validate one envelope. The harness comes from the route, never the body."""
    identified = _identify(harness, payload)
    if isinstance(identified, Rejected):
        return identified
    name, session_id, sid = identified

    sequence = payload.get("source_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        sequence = None
    raw_stamp = _text(payload, "timestamp", limit=MAX_ID_LEN)

    return Event(
        harness=harness,
        event=name,
        sid=sid,
        session_id=session_id,
        timestamp=_parse_timestamp(raw_stamp, config=config, now=now),
        arrival_seq=arrival_seq,
        source_instance_id=_text(payload, "source_instance_id", limit=MAX_ID_LEN),
        source_sequence=sequence,
        cwd=_text(payload, "cwd", limit=MAX_PATH_LEN),
        subagent_id=_text(payload, "subagent_id", limit=MAX_ID_LEN),
        transcript_path=_text(payload, "transcript_path", limit=MAX_PATH_LEN),
    )


def overlay_for(event: Event, *, config: RuntimeConfig) -> Overlay | None:
    """The semantic claim an event makes, or None if it only means "look again".

    Five native shapes are stronger than the store: a prompt means Working, an
    explicit permission request means Needs input, a reply or resumed activity
    means Working again, a stop means Idle after a dwell, and a subagent
    transition changes child activity. Everything else here is a hint that the
    store probably moved, and a hint has no business patching a display field.

    `session_started` is deliberately a hint. It says a session exists, which the
    collector already knows better, and it says nothing about whether the agent
    is doing anything.
    """
    if event.event in {"turn_started", "input_resolved"}:
        return Overlay(
            harness=event.harness,
            sid=event.sid,
            arrival_seq=event.arrival_seq,
            kind=OVERLAY_WORKING,
            at=event.timestamp,
            expires_at=event.timestamp + config.overlay_working_ttl_sec,
        )
    if event.event == "input_requested":
        return Overlay(
            harness=event.harness,
            sid=event.sid,
            arrival_seq=event.arrival_seq,
            kind=OVERLAY_NEEDS_INPUT,
            at=event.timestamp,
        )
    if event.event == "turn_stopped":
        return Overlay(
            harness=event.harness,
            sid=event.sid,
            arrival_seq=event.arrival_seq,
            kind=OVERLAY_IDLE,
            at=event.timestamp,
            effective_at=event.timestamp + config.overlay_idle_dwell_sec,
        )
    if event.event in {"subagent_started", "subagent_stopped"}:
        return Overlay(
            harness=event.harness,
            sid=event.sid,
            arrival_seq=event.arrival_seq,
            kind=OVERLAY_SUBAGENT,
            at=event.timestamp,
            effective_at=event.timestamp if event.event == "subagent_started" else 0.0,
            subagent_id=event.subagent_id,
        )
    return None


def retires_overlays(event: Event) -> bool:
    """Whether this event ends a session's overlay history.

    `session_ended` is non-destructive: it retires overlays and hook state and
    never removes a row, because only the collector may decide a session is gone.
    Claude fires it on `/clear` as well as on exit, so the very next event may be
    a `turn_started` for the same session inside one coalescing window; the
    retirement is by arrival order, which keeps that sequence coherent.
    """
    return event.event == "session_ended"


def requires_reconcile(event: Event) -> bool:
    """Whether this event invalidates caches rather than describing activity.

    Compaction is the case that matters. Neither compaction hook counts as
    activity, and a rewritten transcript is not repaired by replaying overlays.
    """
    return event.event == "reconcile_required"


def reduce_overlays(overlays: Iterable[Overlay], *, now: float) -> dict[str, Any]:
    """The field patch a session's live overlays imply, in `arrival_seq` order.

    Last writer wins per field, which is why the sort is by `arrival_seq` and not
    by timestamp: only the server's own counter is trustworthy enough to order
    two hook processes that raced.

    Subagent overlays are recorded but patch nothing here. A child starting or
    stopping does not change what the parent is doing, and the parent's subagent
    list is reconstructed by the collector, which is the only thing that knows
    the whole tree.
    """
    patch: dict[str, Any] = {}
    for overlay in sorted(overlays, key=lambda item: item.arrival_seq):
        if not overlay.applies(now=now):
            continue
        if overlay.kind == OVERLAY_WORKING:
            patch.update(
                {
                    "state": "working",
                    "state_detail": overlay.detail,
                    "active": True,
                    "blocked_since": None,
                    "acquisition": ACQUISITION_EVENT,
                }
            )
        elif overlay.kind == OVERLAY_NEEDS_INPUT:
            patch.update(
                {
                    "state": "needs_input",
                    "state_detail": overlay.detail,
                    "active": True,
                    "blocked_since": overlay.at,
                    "acquisition": ACQUISITION_EVENT,
                }
            )
        elif overlay.kind == OVERLAY_IDLE:
            patch.update(
                {
                    "state": "idle",
                    "state_detail": None,
                    "active": False,
                    "blocked_since": None,
                    "acquisition": ACQUISITION_EVENT,
                }
            )
    return patch


def apply_patch(session: dict[str, Any], patch: Mapping[str, Any]) -> None:
    """Write a reduced patch onto a collected row, in place.

    Filtered against `PATCHABLE` rather than trusted, so a reducer that grows a
    key by mistake cannot rewrite a title or a token rate. An overlay patches a
    row; it never creates or deletes one, and this signature is what enforces
    that: there is no row to hand it unless a collector produced one.
    """
    session.update({key: value for key, value in patch.items() if key in PATCHABLE})
