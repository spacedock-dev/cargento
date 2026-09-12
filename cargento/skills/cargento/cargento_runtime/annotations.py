"""Annotations: what the reader typed a session should achieve and produce.

DRC-4508. The third thing Cargento writes on the reader's behalf, after the
dismissal store and the history store, and the only one holding text the reader
composed rather than text a harness published.

Shaped on `dismissals` deliberately, and it departs from it in exactly one
place, which is the whole design decision here. A dismissal lapses when the
session moves again, because "I have handled this" is answered by later
activity. An annotation does not lapse, because "this is what I asked for" is
not answered by later activity — that is the thing it exists to be compared
against. There is no watermark in this module, and nothing here takes an
activity argument, which is the shape that says so. A predicate asserting it
used to stand here and was deleted: it ignored the very argument the rule is
about and nothing called it, so mutating the binding left its test green. The
rule is held where it is observable instead, on the published row.

Bounded by two counts and no time-to-live, for `dismissals._bounded`'s reason:
a TTL would delete the reader's own words while the session they describe is
still on the board.

Two acceptance criteria of DRC-4508 are not met by this module and are not
quietly skipped. Binding across a *live* harness resume needs real captures
under `docs/captures/`, which desk research cannot produce. And the
later-conflicting-instruction rule needs a detector that does not exist. The
resolution shape is buildable; nothing in this module carries it yet.

A leaf: `config` for paths and caps, `records` for the untrusted-input
discipline, `io` for the diagnostic sink. It reads nothing else in the runtime.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast

from cargento_runtime import io as runtime_io
from cargento_runtime import reading, records

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.state import RuntimeState

# Read but not enforced, for `dismissals.SCHEMA_VERSION`'s reason: every field
# is re-validated on the way in, so refusing a whole file on an unrecognised
# number throws away words a downgrade could still show.
SCHEMA_VERSION = 1

# What a stored key may occupy. Wide enough for a full UUID session id, which is
# the identity this store binds on, and far narrower than the read cap.
KEY_CAP_CHARS = 64

# The absence sentences, in one place. Three issues render them and the shared
# contract's first rule is that an absent value states its reason rather than
# rendering a blank, a dash or a zero. Wording that lives in three files
# diverges; wording that lives here cannot.
# Whether the abstention check has been run and passed. It gates the
# `Ask for a reading` control and nothing else: the ruling says the reading is
# built now and the control is not enabled until the check has run
# ([DEC-17](docs/design-reading-a-session.md#dec-17-the-shape-contract)).
#
# A recorded fact rather than a switch, and published rather than left absent
# so the page can tell "this build predates the reading" from "the check has
# not been run". Running it needs recorded sessions across Claude and Codex
# and a second person marking each constraint's expected abstention in
# advance, which is why no flag here can turn it on.
ABSTENTION_CHECK_NOT_RUN = "not-run"
ABSTENTION_CHECK_PASSED = "passed"
ABSTENTION_CHECK = ABSTENTION_CHECK_NOT_RUN

NO_GOAL_TYPED = "No goal typed for this session."
NO_OUTPUT_TYPED = "No expected output typed."

# What one call to a mutator did, as a closed vocabulary rather than a bool
# (decisions.md, DRC-4543). The reader is shown a sentence per outcome and a
# bool cannot carry four: `False` covered both a request the store refused,
# which will never work as sent, and a write it could not complete, which
# might next time; `True` covered a minted revision and a repeat of the last
# one, which mints nothing. `save()` itself stays a bool, because it has one
# job and two answers. The tokens go over the wire as `/api/annotate`'s
# `outcome`, so they are spelled for a reader of the reply.
OUTCOME_STORED = "stored"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_REFUSED = "refused"
OUTCOME_UNWRITABLE = "unwritable"
OUTCOMES = (OUTCOME_STORED, OUTCOME_UNCHANGED, OUTCOME_REFUSED, OUTCOME_UNWRITABLE)

# Whether the identity this store bound on is the session's whole identity.
# `exact` is the ordinary case. `prefix` is the one the issue named as a hazard
# and it is real on this tree: `collectors/claude.py` passes the transcript
# stem's first eight characters to `base_session`, so a Claude row's `sid` IS
# the display prefix and the full stem is published beside it as `resume_id`.
# Two sessions sharing those eight characters share an annotation, and the
# honest answer is to say so on the row rather than to claim an exactness the
# identity does not have.
# How short an identity has to be before it is a display prefix rather than a
# whole one. Claude publishes eight characters and the store keys on what it
# publishes, so two sessions sharing them share the words. Owned here beside
# the sentence that says so, because two surfaces now need the same test and a
# second copy of the number is how they come to disagree.
DISPLAY_ID_FLOOR = 8

BINDING_EXACT = ""
BINDING_BY_PREFIX = (
    "Bound by an eight-character identity prefix, which is all this harness "
    "publishes as the session id. Another session sharing it would share these "
    "words."
)


class Revision(TypedDict):
    """One save. Immutable once written.

    An assessment names the revision it read, so editing a revision in place
    would silently re-point every assessment citing revision 1 at text it never
    saw. `n` counts saves rather than surviving entries, so a revision evicted
    by the bound reads as dropped rather than as one that never existed.
    """

    n: int
    at: float
    goal: str
    output: str


class Settlement(TypedDict):
    """The reader's answer to "does a later direction change what you asked for".

    Not a `Revision` field, because a revision is immutable so that an
    assessment citing revision 1 cannot be re-pointed at text it never saw. A
    settlement is about a revision rather than part of one, so it sits beside
    them and carries the revision it rested on: a settlement that does not
    record its own baseline cannot be understood on return, which is the
    amendment made by
    [DEC-18](docs/design-reading-a-session.md#dec-18-an-unasked-reading-is-permitted-and-gated-on-delivery-first)
    to every raise.

    `through` is a moment, not a fact id. The reader is settling everything
    they had said by the time they looked, and a list of ids would go stale
    against a record whose window moves.

    Called a settlement rather than a reconciliation deliberately. `reconcile`
    already names two unrelated things in this runtime, `reconcile_interval_sec`
    and the event lane's `reconcile_required`, and a third meaning would send
    a reader grepping into the wrong subsystem.
    """

    at: float
    through: float
    revision: int


class Annotation(TypedDict):
    """One session's words, newest revision last.

    A reading lives here rather than in session history. DEC-15b named history
    and gave its reason in the same sentence -- so both reopen after a restart
    and after the live row disappears -- and this store already does both: it
    is bounded by two counts with no time-to-live, and an annotation is keyed
    on `(harness, sid)` and carries no project, so it outlives the row by
    construction. The captain amended the ruling on 2026-09-10 once that was
    measured rather than assumed.

    The price is real and recorded rather than hidden: `--forget` deletes
    session history alone and does not reach this store, so a reader who wants
    a model-authored reading gone uses `clear()` on that session. There is no
    fourteen-day expiry either; a reading is evicted when its annotation is.
    """

    harness: str
    sid: str
    revisions: tuple[Revision, ...]
    settled: NotRequired[Settlement]
    assessment: NotRequired[reading.Assessment]
    # Set on read-back when a stored reading was refused whole, never written
    # to disk and never carried across a save. It is a fact about THIS build
    # reading THAT file, so a build that can read the reading publishes no
    # refusal without anything having to clear the flag.
    refused: NotRequired[bool]
    # The reading this build could not read, held verbatim so `save` can put it
    # back. Never published and never read for meaning: it is bytes in transit
    # between two builds.
    refused_raw: NotRequired[Any]
    readings: NotRequired[int]
    withheld: NotRequired[str]


def store_path(config: RuntimeConfig) -> str:
    """Where annotations live: beside the state file, but not per port.

    The reader's words are the reader's, not the instance's, so they survive a
    restart and a different --port. Same placement and same reason as
    `dismissals.store_path`.
    """
    return os.path.join(config.state_home, "cargento-annotations.json")


def _revision(value: Any, cap: int) -> Revision | None:
    """One untrusted revision, or nothing.

    Through `records.safe_text`, which redacts before it clips. The order is
    load-bearing and `records.redact_clip` records why: clipping first can cut a
    key's tail off, leaving a head the shape list no longer matches.
    """
    if not isinstance(value, dict):
        return None
    number = value.get("n")
    # `isinstance(True, int)` is True, and a bool here would publish as a JSON
    # boolean where the shape declares a number.
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        return None
    raw_goal, raw_output = value.get("goal"), value.get("output")
    return {
        "n": number,
        "at": records.norm_epoch(value.get("at")),
        # Type-checked here as well as on the way in. Any local process can
        # rewrite this file, so a dict here would publish its repr exactly as one
        # arriving over the endpoint would.
        "goal": records.safe_text(raw_goal, cap) if isinstance(raw_goal, str) else "",
        "output": records.safe_text(raw_output, cap) if isinstance(raw_output, str) else "",
    }


def _criterion(value: Any, cap: int) -> reading.Criterion | None:
    """One untrusted criterion of a stored reading, or nothing.

    `result` absent and `result` present are both legal and they mean
    different things -- the reading could not be read, versus the evidence
    does not settle it -- so absence is preserved rather than defaulted.

    `why` absent is a reading stored before the field existed and reads back
    as `WHY_STANDS`: a missing key is a reading with less in it, not a
    diverged one. `why` present and outside `WHY_TOKENS` refuses the reading
    whole, like any other bad value here, because the page maps the token to
    one of its own sentences and a token invented by a rewrite of the file
    would otherwise render as the board's own words.
    """
    if not isinstance(value, dict) or set(value) - set(reading.CRITERION_KEYS):
        return None
    result = value.get("result")
    if result is not None and result not in reading.RESULTS:
        return None
    cites = value.get("cites")
    if not isinstance(cites, (list, tuple)) or not all(isinstance(c, str) for c in cites):
        return None
    why = value.get("why", reading.WHY_STANDS)
    if not isinstance(why, str) or why not in reading.WHY_TOKENS:
        return None
    criterion: reading.Criterion = {
        "cites": tuple(records.safe_text(c, KEY_CAP_CHARS) for c in cites),
        "detail": records.safe_text(value.get("detail"), cap),
        "clause": records.safe_text(value.get("clause"), cap),
        "why": why,
    }
    if result is not None:
        criterion["result"] = result
    return criterion


def _assessment(value: Any, cap: int) -> reading.Assessment | None:
    """One untrusted reading, or nothing at all.

    Dropped WHOLE on any failure. A half-parsed reading is the worst of the
    three outcomes: the page renders whatever survived, and what survives is
    whichever half happened to be well-formed rather than whichever half is
    true. Nothing here repairs a field.

    Type-checked on the way out as well as on the way in, for `_revision`'s
    reason: any local process can rewrite this file, and a dict arriving here
    would publish its repr exactly as one arriving over the endpoint would.
    """
    if not isinstance(value, dict) or set(value) - set(reading.ASSESSMENT_KEYS):
        return None
    revision = value.get("revision_read")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        return None
    scope = value.get("scope")
    if scope not in reading.SCOPE_TEXT:
        return None
    raw_criteria = value.get("criteria")
    if not isinstance(raw_criteria, dict) or set(raw_criteria) != set(reading.CONSTRAINTS):
        return None
    criteria: dict[str, reading.Criterion] = {}
    for name, raw in raw_criteria.items():
        criterion = _criterion(raw, cap)
        if criterion is None:
            return None
        criteria[name] = criterion
    ended = value.get("ended_at_read")
    return {
        "revision_read": revision,
        "stamp": records.safe_text(value.get("stamp"), cap),
        "cutoff": records.safe_text(value.get("cutoff"), cap),
        "scope": scope,
        "scope_text": reading.SCOPE_TEXT[scope],
        "ended_at_read": records.norm_epoch(ended) or None,
        # `.get`, so a reading stored before this field reads back as None and
        # the disclosure states the absence rather than blanking.
        "revision_read_at": records.norm_epoch(value.get("revision_read_at")) or None,
        "criteria": criteria,
    }


def _settlement(value: Any) -> Settlement | None:
    """One untrusted settlement, or nothing.

    Bools are refused before the numbers are read, for `_revision`'s reason:
    `isinstance(True, int)` is true, so a `true` in the file would otherwise
    become revision 1 settled at the epoch.
    """
    if not isinstance(value, dict):
        return None
    at = value.get("at")
    through = value.get("through")
    revision = value.get("revision")
    if isinstance(at, bool) or isinstance(through, bool) or isinstance(revision, bool):
        return None
    if not isinstance(at, (int, float)) or not isinstance(through, (int, float)):
        return None
    if not isinstance(revision, int) or revision < 1:
        return None
    return {"at": float(at), "through": float(through), "revision": revision}


def _entry(value: Any, *, text_cap: int, revision_cap: int) -> Annotation | None:
    """One untrusted record as an annotation, or nothing.

    A record whose revisions all fail validation is dropped whole: an annotation
    with no words is indistinguishable from no annotation, and publishing it
    would put an empty row on the board with nothing to say.
    """
    if not isinstance(value, dict):
        return None
    harness = records.safe_text(value.get("harness"), KEY_CAP_CHARS).strip()
    sid = records.safe_text(value.get("sid"), KEY_CAP_CHARS).strip()
    if not harness or not sid:
        return None
    raw = value.get("revisions")
    if not isinstance(raw, list):
        return None
    parsed = [rev for rev in (_revision(item, text_cap) for item in raw) if rev is not None]
    kept = tuple(sorted(parsed, key=lambda rev: rev["n"])[-revision_cap:]) if revision_cap else ()
    if not kept:
        return None
    entry: Annotation = {"harness": harness, "sid": sid, "revisions": kept}
    settled = _settlement(value.get("settled"))
    if settled is not None:
        entry["settled"] = settled
    assessment = _assessment(value.get("assessment"), text_cap)
    if assessment is not None:
        entry["assessment"] = assessment
    elif value.get("assessment") is not None:
        # A reading was stored and this build refuses it whole, which is right:
        # a half-read reading is worse than none. But `readings` survives just
        # below, so without this the row published a press with nothing to show
        # and the page read it as a session nobody had pressed on.
        #
        # The raw value is kept beside the flag and written back verbatim by
        # `save`, which is what makes "a later build reads it fine" true rather
        # than a hope. Measured otherwise: `load` drops the unreadable reading,
        # so the next save to ANY session rewrote the file without it and the
        # reading was gone for good, leaving the row back at a press with
        # nothing to show.
        entry["refused"] = True
        entry["refused_raw"] = value["assessment"]
    readings = value.get("readings")
    if isinstance(readings, int) and not isinstance(readings, bool) and readings > 0:
        entry["readings"] = readings
    withheld = value.get("withheld")
    if isinstance(withheld, str) and withheld in reading.WITHHELD.values():
        entry["withheld"] = withheld
    return entry


def _bounded(entries: Iterable[Annotation], limit: int) -> tuple[Annotation, ...]:
    """The most recently annotated `limit` sessions, oldest save evicted first."""
    ordered = sorted(entries, key=lambda entry: entry["revisions"][-1]["at"])
    return tuple(ordered[-limit:]) if limit > 0 else ()


def load(config: RuntimeConfig) -> tuple[Annotation, ...]:
    """Every annotation on disk, or none if there is none to trust.

    Read to a cap with RecursionError caught, for `lifecycle.read_state`'s
    reason: deeply nested JSON blows the recursion limit rather than raising
    ValueError, and a corrupt store must degrade to "no annotations" rather than
    take down a collection. A malformed record is dropped on its own.
    """
    if not config.annotations_enabled:
        return ()
    cap = config.annotation_read_cap_bytes
    try:
        with open(store_path(config), "rb") as handle:
            raw = handle.read(cap + 1)
        if len(raw) > cap:
            return ()
        data = json.loads(raw or b"null")
    except (OSError, ValueError, RecursionError):
        return ()
    if not isinstance(data, dict):
        return ()
    entries = data.get("entries")
    if not isinstance(entries, list):
        return ()
    parsed = [
        entry
        for entry in (
            _entry(
                value,
                text_cap=config.annotation_text_cap_chars,
                revision_cap=config.annotation_max_revisions,
            )
            for value in entries
        )
        if entry is not None
    ]
    return _bounded(parsed, config.annotation_max_sessions)


def _fsync_directory(path: str) -> None:
    """Flush the directory entry a rename just wrote.

    `os.replace` is atomic against a concurrent reader and says nothing about
    power loss: the new bytes can be durable while the directory still names
    the old file. Opening a directory needs `O_DIRECTORY`, which Windows does
    not have, so there this returns without syncing; anywhere else the caller
    decides what an `OSError` means.
    """
    flag = getattr(os, "O_DIRECTORY", None)
    if flag is None:
        return
    fd = os.open(path, os.O_RDONLY | flag)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(
    config: RuntimeConfig,
    entries: Iterable[Annotation],
    *,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Write the store, reporting whether it reached disk.

    Temp file plus `os.replace`, and `0o600` in the `os.open` call rather than a
    chmod afterwards, both copied from `lifecycle.write_state`. The mode matters
    more here than on the state file: this one holds prose the reader composed,
    which `SECURITY.md` treats as the same class as the observer sidecar's goal.
    The mode is advisory and Windows ignores it, which SECURITY.md records.
    """
    if not config.annotations_enabled:
        return False
    payload = {
        "v": SCHEMA_VERSION,
        "entries": [
            # `refused` is a fact about the build that just read the file
            # rather than about the annotation, so it is dropped. The reading it
            # refused is restored under its own name, or a save here would
            # destroy a reading this build merely could not parse.
            {
                **{
                    name: field
                    for name, field in entry.items()
                    if name not in {"refused", "refused_raw"}
                },
                **({"assessment": entry["refused_raw"]} if "refused_raw" in entry else {}),
                "revisions": [dict(rev) for rev in entry["revisions"]],
            }
            for entry in _bounded(entries, config.annotation_max_sessions)
        ],
    }
    target = store_path(config)
    tmp = f"{target}.{os.getpid()}.tmp"
    try:
        os.makedirs(config.state_home, mode=0o700, exist_ok=True)
        handle_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
            # A rename is atomic against a concurrent reader and says nothing
            # about power loss. Synced here, and the directory synced again
            # after the rename, because this store holds prose a person
            # composed and cannot retype from anywhere else; every other store
            # is reconstructible from what the harnesses already wrote.
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        # The directory sync may fail where the file sync did not (Windows
        # cannot open a directory; some filesystems refuse to fsync one), and
        # by then the bytes are durable and the rename has happened -- only the
        # rename's durability is in doubt. Suppressed rather than reported,
        # because the failure cue below says the words will be gone, and here
        # they are on disk (decisions.md, DRC-4544 directory-fsync half).
        with contextlib.suppress(OSError):
            _fsync_directory(config.state_home)
    # `TypeError` and `RecursionError` are here for the reason `load` already
    # catches `RecursionError`: an encoder that refuses a payload must reach the
    # reader as the failure cue this arm exists to send, not as a dropped
    # socket. Latent while every field is a str, int or float, which is exactly
    # when a guard is cheap.
    except (OSError, ValueError, TypeError, RecursionError):
        runtime_io.diag(
            f"Cargento: could not write the annotation store {target}; "
            "what you typed will be gone at the next collection",
            diagnostic_sink,
        )
        with contextlib.suppress(OSError, ValueError):
            os.unlink(tmp)
        return False
    return True


def _stored(entries: tuple[Annotation, ...]) -> tuple[dict[str, Any], ...]:
    """The same tuple, spelled the way `state` declares it.

    `state` cannot name `Annotation`: this module imports `state` and the arrow
    runs one way only.
    """
    return cast("tuple[dict[str, Any], ...]", entries)


def refresh(config: RuntimeConfig, state: RuntimeState) -> tuple[Annotation, ...]:
    """Re-read the store into this process's copy, and return it.

    Two dashboards can bind on one machine and the file is the record, so a save
    made in one is picked up by the other on its next collection.
    """
    entries = load(config)
    with state.annotation_lock:
        state.annotations = _stored(entries)
    return entries


def active(config: RuntimeConfig, state: RuntimeState) -> tuple[Annotation, ...]:
    """This process's copy, loading it once if no collection has run yet."""
    with state.annotation_lock:
        cached = state.annotations
    if cached is not None:
        return cast("tuple[Annotation, ...]", cached)
    return refresh(config, state)


def find(entries: Iterable[Annotation], harness: Any, sid: Any) -> Annotation | None:
    """The annotation bound to this exact session, or nothing.

    On the FULL session id. `sessions.py` publishes both an eight-character
    display prefix and the full id on every row, so exact binding needs no new
    identity work, and keying on the prefix would let one session's words appear
    under another's name.
    """
    key = _key(harness, sid)
    for entry in entries:
        if (entry["harness"], entry["sid"]) == key:
            return entry
    return None


def published(entry: Annotation | None, *, binding_why: str = BINDING_EXACT) -> dict[str, Any]:
    """The latest revision as the board renders it, absences named.

    One helper rather than three renderers, because the shared contract's first
    rule is that an absent value states its reason and three copies of that
    wording diverge. `None` is a session nobody annotated, which is an absence
    with a reason and not an error.

    `revision` and `at` are None rather than 0 when there is nothing typed. A
    zero is the thing the first rule forbids: a render printing `annotation.at`
    would show 1 January 1970 for every unannotated session, and `revision 0`
    reads as a revision rather than as none.
    """
    latest: Revision | None = entry["revisions"][-1] if entry else None
    settled = entry.get("settled") if entry else None
    goal = latest["goal"] if latest else ""
    output = latest["output"] if latest else ""
    return {
        "goal": goal,
        "goal_why": "" if goal else NO_GOAL_TYPED,
        "output": output,
        "output_why": "" if output else NO_OUTPUT_TYPED,
        "revision": latest["n"] if latest else None,
        "revision_count": len(entry["revisions"]) if entry else 0,
        "at": latest["at"] if latest else None,
        "binding_why": binding_why,
        "reading_refused": bool(entry.get("refused")) if entry else False,
        # Three scalars and no prose, which is what keeps this out of DEC-15b's
        # admission path: `history.OBSERVATION_FIELDS` is a closed tuple and a
        # new published field does not enter the store by being published.
        "settled_at": settled["at"] if settled else None,
        "settled_through": settled["through"] if settled else None,
        "settled_revision": settled["revision"] if settled else None,
        # A reading, the count of presses that reached the model, and the
        # reason there is no reading. Three keys and not one, because a reader
        # who pressed and got nothing must be able to tell that from a reader
        # who has not pressed: the count and the reason say different things
        # and an absent reading says neither.
        "assessment": entry.get("assessment") if entry else None,
        "reading_count": entry.get("readings", 0) if entry else 0,
        "reading_withheld": entry.get("withheld", "") if entry else "",
    }


def _key(harness: Any, sid: Any) -> tuple[str, str]:
    """The binding key: harness plus the full session id, both bounded."""
    return (
        records.safe_text(harness, KEY_CAP_CHARS).strip(),
        records.safe_text(sid, KEY_CAP_CHARS).strip(),
    )


def _carried(existing: Annotation, updated: Annotation) -> Annotation:
    """Copy every optional field the caller did not set onto the new entry.

    Three mutators rebuild this dict from scratch and each one must carry
    every optional field, so the list lives once. A mutator that forgets one
    silently discards the reader's reading, and nothing about the row would
    look wrong afterwards.
    """
    for name in ("settled", "assessment", "readings", "withheld"):
        if name not in updated and name in existing:
            updated[name] = existing[name]
    return updated


def record_reading(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    assessment: reading.Assessment,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """Store one reading beside the words it read. Returns an `OUTCOMES` token.

    The count goes up whether or not the reading is usable, because the
    reader's capacity was spent either way and the control shows what they
    have spent. Any previously withheld reason is cleared: a reading arrived,
    so the sentence saying why one did not is no longer true.
    """
    return _record(
        config,
        state,
        harness,
        sid,
        assessment=assessment,
        withheld="",
        spent=True,
        diagnostic_sink=diagnostic_sink,
    )


def record_withheld(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    reason: str,
    spent: bool,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """Store why there is no reading. Returns an `OUTCOMES` token.

    `spent` is the difference between a press that reached the model and one
    that never could. A missing Codex CLI costs nothing and must not count
    against a reader who has spent nothing; a model call that started and then
    failed has already cost them, and the count says so.

    A previous reading is NOT cleared. It was true when it was made and it
    still names the revision it read; a later press that could not produce one
    does not retract it.
    """
    if reason not in reading.WITHHELD:
        return OUTCOME_REFUSED
    return _record(
        config,
        state,
        harness,
        sid,
        assessment=None,
        withheld=reading.WITHHELD[reason],
        spent=spent,
        diagnostic_sink=diagnostic_sink,
    )


def _record(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    assessment: reading.Assessment | None,
    withheld: str,
    spent: bool,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """The shared write behind `record_reading` and `record_withheld`.

    Speaks the mutators' vocabulary: a reading of a session nobody annotated
    is `OUTCOME_REFUSED`, like any other request the store will not take.
    """
    if not config.annotations_enabled:
        return OUTCOME_REFUSED
    key = _key(harness, sid)
    if not key[0] or not key[1]:
        return OUTCOME_REFUSED
    with state.annotation_lock:
        # From disk under the lock, for `annotate`'s reason: a save made by a
        # second dashboard since this one's last collection is carried forward
        # rather than written away.
        current = load(config)
        existing = find(current, *key)
        if existing is None:
            # A reading of nothing is not a reading. There is no baseline to
            # have read, and inventing an entry here would put a row on the
            # board for a session nobody annotated.
            return OUTCOME_REFUSED
        updated: Annotation = {
            "harness": existing["harness"],
            "sid": existing["sid"],
            "revisions": existing["revisions"],
        }
        if assessment is not None:
            updated["assessment"] = assessment
        if withheld:
            updated["withheld"] = withheld
        elif "withheld" in existing:
            # Cleared rather than carried: a reading arrived.
            updated["withheld"] = ""
        if spent:
            updated["readings"] = existing.get("readings", 0) + 1
        others = [e for e in current if (e["harness"], e["sid"]) != key]
        bounded = _bounded([*others, _carried(existing, updated)], config.annotation_max_sessions)
        # Before the write and inside the lock, as every other mutator does.
        state.annotations = _stored(bounded)
        return (
            OUTCOME_STORED
            if save(config, bounded, diagnostic_sink=diagnostic_sink)
            else OUTCOME_UNWRITABLE
        )


def annotate(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    goal: Any = None,
    output: Any = None,
    now: float | None = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """Append a revision to one session's annotation. Returns an `OUTCOMES` token.

    Both fields are optional and independent, and a save that repeats the last
    revision verbatim appends nothing: opening the field and closing it is not a
    change of intent, and burning a revision number on it would let an
    assessment cite one. That save answers `OUTCOME_UNCHANGED`, not
    `OUTCOME_STORED`: the words are on disk either way, and only the second
    minted anything, which is the difference the page's cue states.
    """
    if not config.annotations_enabled:
        return OUTCOME_REFUSED
    key = _key(harness, sid)
    if not key[0] or not key[1]:
        return OUTCOME_REFUSED
    cap = config.annotation_text_cap_chars
    # Type-checked before redaction, not after. `records.safe_text` does
    # `str(value or "")`, so a dict arriving here would publish its Python repr
    # — with whatever is inside it — rather than being refused. `/api/ask`
    # checks for the same reason, and the endpoint above answers 400; this is
    # the store's own floor under that.
    #
    # None means "not sent" and carries the previous revision's value forward.
    # The empty string means "clear this one field". Collapsing the two would
    # make a client that posts only the goal silently destroy the expected
    # output beside it, which is the opposite of the independence the two fields
    # are documented to have.
    new_goal = records.safe_text(goal, cap) if isinstance(goal, str) else None
    new_output = records.safe_text(output, cap) if isinstance(output, str) else None
    if new_goal is None and new_output is None:
        return OUTCOME_REFUSED
    stamp = time.time() if now is None else now

    with state.annotation_lock:
        # From disk under the lock rather than from the cached copy, so a save
        # made by a second dashboard since this one's last collection is carried
        # forward instead of being written away.
        current = load(config)
        existing = find(current, *key)
        if existing is not None:
            last = existing["revisions"][-1]
            text_goal = last["goal"] if new_goal is None else new_goal
            text_output = last["output"] if new_output is None else new_output
            if (last["goal"], last["output"]) == (text_goal, text_output):
                # Unchanged text is not a new request, so it mints no revision.
                # The cache is still refreshed from the load above: two
                # dashboards share this file, and returning early with a stale
                # cache is how this process went on reporting "no goal typed"
                # for words the other one had already saved.
                state.annotations = _stored(_bounded(current, config.annotation_max_sessions))
                return OUTCOME_UNCHANGED
            revision: Revision = {
                "n": last["n"] + 1,
                "at": stamp,
                "goal": text_goal,
                "output": text_output,
            }
            kept_revisions = (*existing["revisions"], revision)[-config.annotation_max_revisions :]
            updated: Annotation = {
                "harness": key[0],
                "sid": key[1],
                "revisions": tuple(kept_revisions),
            }
            # Carried, not cleared. A settlement records what the reader had
            # already answered, and retyping the baseline clears the block by
            # its own stamp rather than by discarding that history: the new
            # revision's `at` is later than the directions that raised it.
            updated = _carried(existing, updated)
        else:
            updated = {
                "harness": key[0],
                "sid": key[1],
                "revisions": (
                    {
                        "n": 1,
                        "at": stamp,
                        "goal": new_goal or "",
                        "output": new_output or "",
                    },
                ),
            }
        others = [e for e in current if (e["harness"], e["sid"]) != key]
        bounded = _bounded([*others, updated], config.annotation_max_sessions)
        state.annotations = _stored(bounded)
        # Inside the lock, not after it. The server is threaded, so two saves on
        # one session both read the pre-write store, both mint revision n+1, and
        # the later write erases the earlier one. Holding the lock across the
        # write costs one file write and closes the whole in-process window.
        return (
            OUTCOME_STORED
            if save(config, bounded, diagnostic_sink=diagnostic_sink)
            else OUTCOME_UNWRITABLE
        )


def settle(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    through: Any,
    now: float | None = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """Record that the reader has answered a later direction. Returns an `OUTCOMES` token.

    `through` comes from the client, because the moment being settled is the
    one the reader was looking at and this process has no access to the
    project-context facts that produced it. It is clamped to `now`: unclamped,
    a single local POST with a far-future value would silently disable the
    block for that session forever, and clamping bounds the damage to "settled
    as of now", which any later direction re-opens.

    Settling a session with nothing typed is refused. The mark is an answer
    about a baseline, and there is no baseline to answer about.
    """
    if not config.annotations_enabled:
        return OUTCOME_REFUSED
    key = _key(harness, sid)
    if not key[0] or not key[1]:
        return OUTCOME_REFUSED
    if isinstance(through, bool) or not isinstance(through, (int, float)):
        return OUTCOME_REFUSED
    stamp = time.time() if now is None else now

    with state.annotation_lock:
        # From disk under the lock, for `annotate`'s reason: a save made by a
        # second dashboard since this one's last collection is carried forward
        # rather than written away.
        current = load(config)
        existing = find(current, *key)
        if existing is None:
            return OUTCOME_REFUSED
        updated: Annotation = {
            "harness": existing["harness"],
            "sid": existing["sid"],
            "revisions": existing["revisions"],
            "settled": {
                "at": stamp,
                "through": min(float(through), stamp),
                "revision": existing["revisions"][-1]["n"],
            },
        }
        updated = _carried(existing, updated)
        others = [e for e in current if (e["harness"], e["sid"]) != key]
        bounded = _bounded([*others, updated], config.annotation_max_sessions)
        # Before the write and inside the lock, as `annotate` and `clear` both
        # do. `active()` serves the cached copy when it is not None, and the
        # endpoint reads back through it on the same request, so a settle that
        # skipped this would answer with the mark it had just written missing.
        state.annotations = _stored(bounded)
        return (
            OUTCOME_STORED
            if save(config, bounded, diagnostic_sink=diagnostic_sink)
            else OUTCOME_UNWRITABLE
        )


def clear(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """Forget one session's words entirely. Returns an `OUTCOMES` token.

    Every revision goes, not just the latest. A reader clearing the field is
    withdrawing the request, and leaving the history behind would keep it
    citable by an assessment.
    """
    if not config.annotations_enabled:
        return OUTCOME_REFUSED
    key = _key(harness, sid)
    if not key[0] or not key[1]:
        return OUTCOME_REFUSED
    with state.annotation_lock:
        kept = tuple(e for e in load(config) if (e["harness"], e["sid"]) != key)
        state.annotations = _stored(kept)
        # Inside the lock, for `annotate`'s reason.
        return (
            OUTCOME_STORED
            if save(config, kept, diagnostic_sink=diagnostic_sink)
            else OUTCOME_UNWRITABLE
        )
