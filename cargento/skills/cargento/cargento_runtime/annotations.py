"""Annotations: what the reader typed a session should achieve and produce.

DRC-4508. The third thing Cargento writes on the reader's behalf, after the
dismissal store and the history store, and the only one holding text the reader
composed rather than text a harness published.

Shaped on `dismissals` deliberately, and it departs from it in exactly one
place, which is the whole design decision here. A dismissal lapses when the
session moves again, because "I have handled this" is answered by later
activity. An annotation does not lapse, because "this is what I asked for" is
not answered by later activity — that is the thing it exists to be compared
against. There is no watermark in this module, and `holds` says so rather than
leaving the absence to be read as an oversight.

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
from typing import TYPE_CHECKING, Any, TypedDict, cast

from cargento_runtime import io as runtime_io
from cargento_runtime import records

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

# Whether the identity this store bound on is the session's whole identity.
# `exact` is the ordinary case. `prefix` is the one the issue named as a hazard
# and it is real on this tree: `collectors/claude.py` passes the transcript
# stem's first eight characters to `base_session`, so a Claude row's `sid` IS
# the display prefix and the full stem is published beside it as `resume_id`.
# Two sessions sharing those eight characters share an annotation, and the
# honest answer is to say so on the row rather than to claim an exactness the
# identity does not have.
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


class Annotation(TypedDict):
    """One session's words, newest revision last."""

    harness: str
    sid: str
    revisions: tuple[Revision, ...]


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
    return {"harness": harness, "sid": sid, "revisions": kept}


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
            {**entry, "revisions": [dict(rev) for rev in entry["revisions"]]}
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
        os.replace(tmp, target)
    except (OSError, ValueError):
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


def holds(entries: Iterable[Annotation], harness: Any, sid: Any, _last_activity: float) -> bool:
    """Whether this session carries words the reader typed.

    Takes `last_activity` and ignores it, which is the point. `dismissals.holds`
    compares it against a watermark because a dismissal lapses when the work
    resumes. An annotation does not lapse: later activity is the thing it is
    there to be read against, not a reason to forget it. The parameter is here
    so the difference is visible at the call site rather than inferred from an
    absence.
    """
    return find(entries, harness, sid) is not None


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
    }


def _key(harness: Any, sid: Any) -> tuple[str, str]:
    """The binding key: harness plus the full session id, both bounded."""
    return (
        records.safe_text(harness, KEY_CAP_CHARS).strip(),
        records.safe_text(sid, KEY_CAP_CHARS).strip(),
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
) -> bool:
    """Append a revision to one session's annotation. Returns whether it landed.

    Both fields are optional and independent, and a save that repeats the last
    revision verbatim appends nothing: opening the field and closing it is not a
    change of intent, and burning a revision number on it would let an
    assessment cite one.
    """
    if not config.annotations_enabled:
        return False
    key = _key(harness, sid)
    if not key[0] or not key[1]:
        return False
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
        return False
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
                return True
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
        return save(config, bounded, diagnostic_sink=diagnostic_sink)


def clear(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Forget one session's words entirely. Returns whether the store was rewritten.

    Every revision goes, not just the latest. A reader clearing the field is
    withdrawing the request, and leaving the history behind would keep it
    citable by an assessment.
    """
    if not config.annotations_enabled:
        return False
    key = _key(harness, sid)
    if not key[0] or not key[1]:
        return False
    with state.annotation_lock:
        kept = tuple(e for e in load(config) if (e["harness"], e["sid"]) != key)
        state.annotations = _stored(kept)
        # Inside the lock, for `annotate`'s reason.
        return save(config, kept, diagnostic_sink=diagnostic_sink)
