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
import re
import time
from typing import TYPE_CHECKING, Any, Final, NamedTuple, NotRequired, TypedDict, cast

from cargento_runtime import io as runtime_io
from cargento_runtime import reading, records

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.state import RuntimeState

# Read but not enforced, for `dismissals.SCHEMA_VERSION`'s reason: every field
# is re-validated on the way in, so refusing a whole file on an unrecognised
# number throws away words a downgrade could still show. 2 stores outcome
# lines where 1 stored one `output`; a version 1 revision reads as one typed
# line and is written back as lines by the next save, never rewritten in place.
SCHEMA_VERSION = 2

# What a stored key may occupy. Wide enough for a full UUID session id, which is
# the identity this store binds on, and far narrower than the read cap.
KEY_CAP_CHARS = 64

# The absence sentences, in one place. Three issues render them and the shared
# contract's first rule is that an absent value states its reason rather than
# rendering a blank, a dash or a zero. Wording that lives in three files
# diverges; wording that lives here cannot.
# The captain accepted the twelve marked recorded cases as sufficient to
# enable readings on 2026-09-14. `accepted` records that decision separately
# from a scorer's `passed` verdict. The amendment owns the distinction:
# [DEC-17](docs/design-reading-a-session.md#amended-2026-09-14-the-captain-accepts-the-case-review).
ABSTENTION_CHECK_NOT_RUN = "not-run"
ABSTENTION_CHECK_PASSED = "passed"
ABSTENTION_CHECK_ACCEPTED = "accepted"
ABSTENTION_CHECK = ABSTENTION_CHECK_ACCEPTED


# The Claude Code producer's own check, and it has not run: no eligible
# recorded Claude case exists for it. The 2026-09-14 acceptance above was a
# review of Codex readings and opens nothing here. While this is `not-run` the
# producer is never offered, selected or invoked by any route
# ([DEC-21](docs/design-reading-a-session.md#amended-2026-09-23-claude-code-is-built-and-gated)).
CLAUDE_ABSTENTION_CHECK = ABSTENTION_CHECK_NOT_RUN
_OPEN = (ABSTENTION_CHECK_PASSED, ABSTENTION_CHECK_ACCEPTED)


def reading_enabled() -> bool:
    """Either recorded authorization opens the Codex producer and its route."""
    return ABSTENTION_CHECK in _OPEN


def provider_enabled(provider: str) -> bool:
    """Whether this provider's own recorded check lets it be offered at all."""
    if provider == "codex":
        return reading_enabled()
    if provider == "claude":
        return CLAUDE_ABSTENTION_CHECK in _OPEN
    return False


def any_reading_enabled() -> bool:
    """Whether some provider could be offered, which is what opens the route."""
    return provider_enabled("codex") or provider_enabled("claude")


def published_check() -> str:
    """The check the page's build-wide gate reads: Codex's, unless only Claude Code's opens."""
    if not reading_enabled() and provider_enabled("claude"):
        return CLAUDE_ABSTENTION_CHECK
    return ABSTENTION_CHECK


NO_GOAL_TYPED = "No goal typed for this session."
NO_LINES_TYPED = "No expected outcome typed."

# Where an outcome line came from, a closed set. `typed` is every line a
# reader saves; `entry` is a line added from an entry in the record, which only
# a server-side route may mint, because a client that could send it could
# forge the claim (DRC-4682 builds that route). Anything else refuses the
# revision, and with it the entry, for `_entry`'s reason.
LINE_TYPED = "typed"
LINE_ENTRY = "entry"
LINE_SOURCES = (LINE_TYPED, LINE_ENTRY)

# What discarding a whole annotation is, and what it is not (DRC-4561).
#
# Here rather than in the page's own cue table, which every other control on
# this block reads, because these claim something about the DEPARTURE store:
# `clear` drops the entry and `http_api._withdraw_raises` blanks the rows that
# quoted it, and the page never reads that store. A sentence about it cannot be
# checked where it is written, so it is written where it can be. The precedent
# is the reading route's disclosure, published for the same reason.
#
# The first is the disclosure the walk measured the need for: a reader presses
# the `clear` beside the box, saves, and believes the words are gone while a
# departure still quotes them verbatim on the wire. Naming both acts where the
# reader meets them is what closes that belief, and SECURITY.md already says
# the shorter name is the one printed on the button.
DISCARD_WHY = (
    "The clear beside the goal and the remove beside each outcome line empty them, and the save "
    "after it keeps every earlier revision, so anything raised against those words goes on "
    "quoting them. Discarding everything is the other act."
)
# The confirmation, and it carries the whole scope rather than the fact that
# there is one. It is the only sentence a reader sees before the act, so
# naming the four effects here is what makes the two presses a decision
# instead of a speed bump; the shipped one said only that a second press would
# discard, and the four names arrived after the write. Future tense against
# DISCARD_STORED's past, same four names in the same order, so a reader who
# read one recognises the other.
DISCARD_ARMED = (
    "Press it again to discard. Every revision of what you asked of this session will go, along "
    "with any reading of it, and nothing raised against those words will quote them any more; "
    "the record that a check ran stays. Nothing has been deleted yet, and this offer lapses on "
    "its own."
)
# Categorical and with no count. Nothing measures how many raises were
# withdrawn: `departures.withdraw` answers True whether it blanked five rows or
# none, and a figure derived from the row's own `departures` list would be the
# first Measured Invariant's defect again.
DISCARD_STORED = (
    "Discarded. Every revision of what you asked of this session is gone, along with any "
    "reading of it, and nothing raised against those words quotes them any more. The record "
    "that a check ran stays, because it is what bounds how often one may run."
)
DISCARD_REFUSED = (
    "Not discarded. The server refused, so every revision is still stored and nothing raised "
    "against them was withdrawn."
)
DISCARD_UNWRITABLE = (
    "Not discarded. The store could not be written, so the next collection reads every "
    "revision back and nothing raised against them was withdrawn."
)
# The store exists and this build cannot read it, so nothing was written. It
# names the file and the step, as every refusal here names one.
DISCARD_UNTRUSTED = (
    "Not discarded. Cargento could not read cargento-annotations.json, so nothing was saved "
    "and nothing was overwritten. Move or repair that file to save again."
)
# This session's own entry is one this build cannot read.
DISCARD_HELD = (
    "Not discarded. This session's words were saved by a build of Cargento that can read more "
    "than this one, so nothing was changed. Discard them from that build, or remove this "
    "session's entry from cargento-annotations.json."
)
# What the board says at rest while the store cannot be read, in place of
# every session reading as one nobody typed against.
STORE_UNREADABLE = (
    "Cargento could not read cargento-annotations.json, so what you typed against sessions "
    "cannot be shown and nothing will be saved over it. Move or repair that file to save again."
)
# The half-landed case, and the reason DISCARD_STORED cannot simply be worded
# more carefully. A discard is one act over two stores: `clear` drops the
# entry, then `http_api._withdraw_raises` blanks the rows that quoted it, and
# the second half can fail on its own -- `departures.withdraw` answers False on
# a store it could not write. The annotation is gone by then and cannot be put
# back, so this is not a failure of the act; it is the act with one effect
# missing, and the reader is about to be redrawn the quotations it was told
# were withdrawn.
#
# It stops at what happened and offers no remedy, because there is none on
# this board: the control is gated on a stored revision and there is no longer
# one, so a second press is not available to the reader who needs it.
DISCARD_UNWITHDRAWN = (
    "Discarded here. Every revision of what you asked of this session is gone, along with any "
    "reading of it. The departure store could not be written, so anything raised against those "
    "words goes on quoting them."
)
# What a discard leaves behind once its cue has lapsed (DRC-4565).
#
# The cue above is transient by construction and right to be: a thirty second
# lifetime is what a cue is for. The record is the half that was missing, and
# what it may say is bounded from two directions. It may not restate the words,
# because deleting them was the act. And it may not claim anything about the
# departure store, because a discard is one act over two stores and the second
# half fails on its own -- so this sentence speaks only about the annotation
# store, and the standing sentence below is added beside it by whichever
# surface can see that a raise still quotes.
#
# "kept here" and not "kept", and the qualifier is the whole of what stops this
# sentence being false. Session history keeps its own copy of `annotation_goal`
# and each `annotation_line_<k>` for fourteen days, it is on by default, and nothing in
# the discard path touches it: measured, the discarded words were still in the
# store on disk and in every `/api/data` payload's `history` array after the
# act. The Intent log prints that fourteen-day copy in its own closing note, so
# an unqualified claim contradicted a sentence rendered in the same view. The
# other copy is named here rather than left to that note, because this sentence
# also renders on the Held to tab and the session page, where the note does not.
DISCARD_RECORD = (
    "What you asked of this session was discarded, along with any reading of it. "
    "None of it is kept here: this record says only that the act happened and when. Where "
    "session history is recording, it holds its own fourteen-day copy of the goal and each "
    "outcome line, and --forget deletes that store."
)
DISCARD_RECORD_STANDING = (
    "The departure store could not be written when they went, so anything raised against "
    "those words goes on quoting them."
)
# The absences on a session whose words were discarded, which must never be
# the absences on a session nobody ever typed against. Both states render in
# the same slot, and rendering one sentence for both is the false answer this
# issue exists to remove.
#
# One sentence for both fields, and it names neither (DRC-4668). A discard
# record keeps no per-field facts, so it cannot say which field held words or
# how they got there: a goal may have been adopted from the reader's prompt,
# and either field may never have been filled. "The goal you typed" was false
# of an adopted goal, and any per-field "was discarded" is false of an empty
# field. The two names stay so each slot reads as its own.
DISCARDED_GOAL = "Discarded with everything else you asked of this session."
DISCARDED_LINES = DISCARDED_GOAL
# A discard of a session that had nothing to discard. The control is gated on
# a stored revision so a reader cannot reach it, but the route can be reached
# by hand and answered as though an act had landed.
DISCARD_NOTHING = (
    "Nothing to discard. Nothing was typed against this session, so nothing was deleted "
    "and no record of a deletion was made."
)
DISCARD_SENTENCES: Final[dict[str, str]] = {
    "why": DISCARD_WHY,
    "armed": DISCARD_ARMED,
    "stored": DISCARD_STORED,
    "unwithdrawn": DISCARD_UNWITHDRAWN,
    "refused": DISCARD_REFUSED,
    "unwritable": DISCARD_UNWRITABLE,
    "untrusted": DISCARD_UNTRUSTED,
    "held": DISCARD_HELD,
    "record": DISCARD_RECORD,
    "record_standing": DISCARD_RECORD_STANDING,
    "nothing": DISCARD_NOTHING,
    # The reading route's own refusal, so the block on the tab and the route
    # behind its button cannot word one state two ways.
    "unreadable": reading.WITHHELD[reading.WITHHELD_DISCARDED],
}

# What one call to a mutator did, as a closed vocabulary rather than a bool
# (decisions.md, DRC-4543). The reader is shown a sentence per outcome and a
# bool cannot carry four: `False` covered both a request the store refused,
# which will never work as sent, and a write it could not complete, which
# might next time; `True` covered a minted revision and a repeat of the last
# one, which mints nothing. `save()` itself stays a bool, because it has one
# job and two answers. The tokens go over the wire as `/api/annotate`'s
# `outcome`, so they are spelled for a reader of the reply.
OUTCOME_STORED = "stored"
# How many reading-job ids an entry remembers. Only the newest few can still
# meet a restart marker, since a marker names one job and is gone once recorded.
RECORDED_JOBS_CAP = 32
_JOB_ID = re.compile(r"[0-9a-f]{1,64}")
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_REFUSED = "refused"
OUTCOME_UNWRITABLE = "unwritable"
# The store on disk exists and this build cannot read it whole, so nothing is
# written: a save would keep only what this process holds and write every
# other session's words away (owner ruling, 2026-09-24). Its own token, because
# the reader's remedy differs from a failed write's: the file needs looking at.
OUTCOME_UNTRUSTED = "untrusted"
# The store is readable and this session's own entry is not: a later build
# wrote it with more lines or a source this one does not know. Kept raw and
# never written over, renumbered or dropped from this build.
OUTCOME_UNREADABLE = "unreadable"
OUTCOMES = (
    OUTCOME_STORED,
    OUTCOME_UNCHANGED,
    OUTCOME_REFUSED,
    OUTCOME_UNWRITABLE,
    OUTCOME_UNTRUSTED,
    OUTCOME_UNREADABLE,
)

# What one `--forget` sweep of this store did (DRC-4565). A closed vocabulary
# for `OUTCOMES`' reason and not the wire's: these never leave the process, and
# `cli` picks one of three sentences from them.
FORGET_SWEPT = "swept"
FORGET_NOTHING = "nothing"
FORGET_UNWRITABLE = "unwritable"
# The store exists and could not be read, so the sweep wrote nothing.
FORGET_UNTRUSTED = "untrusted"

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


class Provenance(TypedDict, total=False):
    goal_source: str
    goal_source_at: float


class Window(TypedDict, total=False):
    window_start: float


class OutcomeLine(TypedDict):
    """One line of the expected outcome: one line of text and where it came from.

    `source_id` is the fact id of the entry an `entry` line came from, never a
    number: the activity list numbers entries afresh, so a stored number would
    point at a different entry later (item 11 of the ruling
    `reading.MAX_OUTCOME_LINES` cites).
    """

    text: str
    source: str
    source_id: NotRequired[str]


class Revision(TypedDict):
    """One save. Immutable once written.

    An assessment names the revision it read, so editing a revision in place
    would silently re-point every assessment citing revision 1 at text it never
    saw. `n` counts saves rather than surviving entries, so a revision evicted
    by the bound reads as dropped rather than as one that never existed.
    """

    goal_source: NotRequired[str]
    goal_source_at: NotRequired[float]
    # Where this revision's evidence window opens, beside the save (item 13 of
    # the ruling `reading.TURN_STOP_HARNESSES` cites). Absent on a revision an
    # older build saved, which then opens at `reading.baseline_at`.
    window_start: NotRequired[float]
    n: int
    at: float
    goal: str
    lines: tuple[OutcomeLine, ...]


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

    The price is real and recorded rather than hidden: `--forget` deletes no
    reading and no word a reader typed, so a reader who wants a model-authored
    reading gone uses `clear()` on that session. It reaches this store for one
    thing only, the text-free discard records `forget` sweeps, which is the
    machine's memory of an act rather than anything a person wrote. There is no
    fourteen-day expiry either; a reading is evicted when its annotation is.
    """

    harness: str
    sid: str
    revisions: tuple[Revision, ...]
    # The reading jobs whose outcome this entry already holds, newest last, so
    # an outcome written twice for one job (a restart recovering a marker whose
    # write had landed) counts once. Ids only, bounded by `RECORDED_JOBS_CAP`.
    jobs: NotRequired[list[str]]
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
    # A discard record, and the only entry shape with no revisions at all
    # (DRC-4565). `discarded` is when the act happened; `discarded_revision` is
    # the last revision number that went, kept so the next save mints n+1
    # rather than reusing a number a withdrawn departure row still records
    # having read. Neither is text and nothing else survives beside them: the
    # reasoning `clear` gives is unchanged, because a record carrying no words
    # leaves nothing citable.
    discarded: NotRequired[float]
    discarded_revision: NotRequired[int]
    # When a mutator last wrote this entry, which is what `_kept` trims by: a
    # settle or a reading writes without minting a revision.
    written: NotRequired[float]


def store_path(config: RuntimeConfig) -> str:
    """Where annotations live: beside the state file, but not per port.

    The reader's words are the reader's, not the instance's, so they survive a
    restart and a different --port. Same placement and same reason as
    `dismissals.store_path`.
    """
    return os.path.join(config.state_home, "cargento-annotations.json")


def _line(value: Any, cap: int) -> OutcomeLine | None:
    """One untrusted stored line, or nothing if it is not one."""
    if not isinstance(value, dict) or not isinstance(value.get("text"), str):
        return None
    source = value.get("source")
    if source not in LINE_SOURCES:
        return None
    line: OutcomeLine = {"text": records.safe_text(value["text"], cap), "source": str(source)}
    if source == LINE_ENTRY:
        fact = records.safe_text(value.get("source_id"), KEY_CAP_CHARS).strip()
        if not fact:
            return None
        line["source_id"] = fact
    return line


def _lines(value: Mapping[str, Any], cap: int) -> tuple[OutcomeLine, ...] | None:
    """A revision's outcome lines, or None when they cannot be trusted.

    A revision written before the checklist carries one `output` and reads as
    that one typed line, or none when it was empty. `lines` wins where both
    are present. More than six, or one with an unknown source, is not a
    revision this build can read, and the caller refuses the entry.
    """
    raw = value.get("lines")
    if raw is None:
        output = value.get("output")
        text = records.safe_text(output, cap) if isinstance(output, str) else ""
        return ({"text": text, "source": LINE_TYPED},) if text.strip() else ()
    if not isinstance(raw, list) or len(raw) > reading.MAX_OUTCOME_LINES:
        return None
    parsed = [_line(item, cap) for item in raw]
    if any(line is None for line in parsed):
        return None
    return tuple(line for line in parsed if line is not None and line["text"].strip())


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
    raw_goal = value.get("goal")
    provenance = _provenance(value)
    lines = _lines(value, cap)
    window = _window(value)
    if provenance is None or lines is None or window is None:
        return None
    return {
        **provenance,
        **window,
        "n": number,
        "at": records.norm_epoch(value.get("at")),
        # Type-checked here as well as on the way in. Any local process can
        # rewrite this file, so a dict here would publish its repr exactly as one
        # arriving over the endpoint would.
        "goal": records.safe_text(raw_goal, cap) if isinstance(raw_goal, str) else "",
        "lines": lines,
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
    scope = value.get("scope")
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or scope not in reading.SCOPE_TEXT
    ):
        return None
    criteria = _criteria(value.get("criteria"), cap)
    if criteria is None:
        return None
    ended = value.get("ended_at_read")
    provenance = _provenance({**value, "at": value.get("revision_read_at")})
    if provenance is None:
        return None
    # A null is a reading with no window to state, as `produce` writes one for
    # a revision with no usable time. Anything else present must be a moment
    # at or before the revision it read, or the page would apply a window the
    # producer never did.
    window: float | None = None
    if value.get("window_start") is not None:
        window_fields = _window(
            {"window_start": value["window_start"], "at": value.get("revision_read_at")}
        )
        if not window_fields:
            return None
        window = window_fields["window_start"]
    return {
        **provenance,
        "revision_read": revision,
        "read_at": records.norm_epoch(value.get("read_at")) or None,
        "stamp": records.safe_text(value.get("stamp"), cap),
        "cutoff": records.safe_text(value.get("cutoff"), max(cap, reading.CUTOFF_CAP_CHARS)),
        "scope": scope,
        "scope_text": reading.SCOPE_TEXT[scope],
        "ended_at_read": records.norm_epoch(ended) or None,
        # `.get`, so a reading stored before this field reads back as None and
        # the disclosure states the absence rather than blanking.
        "revision_read_at": records.norm_epoch(value.get("revision_read_at")) or None,
        "window_start": window,
        # `.get`, for the reason above: a reading stored before item 6 of the
        # ruling `reading.MAX_OUTCOME_LINES` cites reads back as None, which
        # says how far it read is unknown rather than claiming a time.
        "evidence_through": records.norm_epoch(value.get("evidence_through")) or None,
        "criteria": criteria,
    }


def _criteria(value: Any, cap: int) -> dict[str, reading.Criterion] | None:
    """A reading's criteria, keyed goal then each line in order, or nothing.

    The keys are the goal and `line_1` to `line_N` with no gap, N at most six:
    a gap would caption one line's verdict with another's words. A reading
    stored before the checklist carries `goal` and `output`, and `output`
    reads back as `line_1`, so the old reading renders rather than being
    refused. An `output` with no words and no verdict is dropped instead: it
    is a field nobody typed, which a reading from before `why` existed stored
    as `not verifiable` with no reason.
    """
    if not isinstance(value, dict):
        return None
    parsed: dict[str, reading.Criterion] = {}
    for name, raw in value.items():
        criterion = _criterion(raw, cap)
        if criterion is None:
            return None
        parsed[str(name)] = criterion
    if set(parsed) == {reading.CONSTRAINT_GOAL, reading.CONSTRAINT_OUTPUT}:
        output = parsed.pop(reading.CONSTRAINT_OUTPUT)
        verdict = output.get("result") in (reading.RESULT_DEPARTURE, reading.RESULT_CONSISTENT)
        if output["clause"].strip() or output["cites"] or verdict:
            parsed[reading.outcome_line(1)] = output
    names = reading.constraints_for(["line"] * (len(parsed) - 1))
    if len(parsed) - 1 > reading.MAX_OUTCOME_LINES or set(parsed) != set(names):
        return None
    return {name: parsed[name] for name in names}


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


def _discard_record(value: dict[str, Any], harness: str, sid: str) -> Annotation | None:
    """One untrusted record with no revisions as a discard record, or nothing.

    A record and nothing else: every optional field beside it is dropped
    unread, which is what makes "carries no text" a property of the parser
    rather than a promise about the writer. A file rewritten by any local
    process to hang a reading off a discard record reads back as a discard
    record with no reading.
    """
    at = value.get("discarded")
    if isinstance(at, bool) or not isinstance(at, (int, float)) or at <= 0:
        return None
    entry: Annotation = {"harness": harness, "sid": sid, "revisions": (), "discarded": float(at)}
    revision = value.get("discarded_revision")
    if not isinstance(revision, bool) and isinstance(revision, int) and revision > 0:
        entry["discarded_revision"] = revision
    return entry


def _entry(value: Any, *, text_cap: int, revision_cap: int) -> Annotation | None:
    """One untrusted record as an annotation, or nothing.

    A record whose revisions all fail validation is dropped whole unless it
    carries a discard stamp: an annotation with no words and no stamp is
    indistinguishable from no annotation, and publishing it would put an empty
    row on the board with nothing to say. A discard record has something to
    say, which is the whole of DRC-4565.
    """
    if not isinstance(value, dict):
        return None
    harness = records.safe_text(value.get("harness"), KEY_CAP_CHARS).strip()
    sid = records.safe_text(value.get("sid"), KEY_CAP_CHARS).strip()
    if not harness or not sid:
        return None
    raw = value.get("revisions")
    if not isinstance(raw, list) or any(
        isinstance(item, dict)
        and (_provenance(item) is None or _lines(item, text_cap) is None or _window(item) is None)
        for item in raw
    ):
        # Dropping just this revision could restore older typed words and
        # authorize the unasked lane against a baseline we no longer know.
        return None
    parsed = [rev for rev in (_revision(item, text_cap) for item in raw) if rev is not None]
    kept = tuple(sorted(parsed, key=lambda rev: rev["n"])[-revision_cap:]) if revision_cap else ()
    if not kept:
        return _discard_record(value, harness, sid)
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
    return _counters(entry, value)


def _counters(entry: Annotation, value: dict[str, Any]) -> Annotation:
    """The entry's press count, withheld reason and write time, each read on its own."""
    jobs = value.get("jobs")
    if isinstance(jobs, list):
        kept = [job for job in jobs if isinstance(job, str) and _JOB_ID.fullmatch(job)]
        if kept:
            entry["jobs"] = kept[-RECORDED_JOBS_CAP:]
    readings = value.get("readings")
    if isinstance(readings, int) and not isinstance(readings, bool) and readings > 0:
        entry["readings"] = readings
    withheld = _withheld(value.get("withheld"))
    if withheld:
        entry["withheld"] = withheld
    written = records.norm_epoch(value.get("written"))
    if written:
        entry["written"] = float(written)
    return entry


def _withheld(value: Any) -> str:
    """A stored reason for no reading, in today's words, or nothing.

    A sentence this build no longer writes is mapped through
    `reading.LEGACY_WITHHELD` rather than dropped, for that table's reason.
    """
    if isinstance(value, str) and value in reading.LEGACY_WITHHELD:
        return reading.WITHHELD[reading.LEGACY_WITHHELD[value]]
    return value if isinstance(value, str) and value in reading.WITHHELD.values() else ""


def _last_written(entry: Annotation) -> float:
    """When anything was last written to this entry, as far as the entry can say.

    Not its newest revision alone. A settle, a reading and a withheld reason
    enlarge an entry without minting a revision, and ranking by revision time
    made the entry being written the first one `_kept` dropped at the cap: the
    save answered `stored` over words it had just deleted. `written` is set by
    every mutator; an entry stored before it existed falls back to the newest
    time it carries.
    """
    stamps = [float(entry.get("written") or 0.0), float(entry.get("discarded") or 0.0)]
    if entry["revisions"]:
        stamps.append(entry["revisions"][-1]["at"])
    settled = entry.get("settled")
    if settled:
        stamps.append(settled["at"])
    assessment = entry.get("assessment")
    if assessment:
        stamps.append(assessment.get("read_at") or 0.0)
    return max(stamps)


def _eviction_rank(entry: Annotation) -> tuple[int, float]:
    """Where this entry stands in the queue to be dropped. Lowest goes first.

    Two keys and not one, because age alone gets it backwards (DRC-4565). A
    discard record is stamped at the moment of the act, which is later than
    every entry typed before it, so oldest-first would keep a record of a
    deletion and evict words the reader still has. Words outrank a record of
    their absence, and within each group the least recently written goes first.
    """
    return (1 if entry["revisions"] else 0, _last_written(entry))


def _bounded(entries: Iterable[Annotation], limit: int) -> tuple[Annotation, ...]:
    """The `limit` entries worth keeping, by `_eviction_rank`."""
    ordered = sorted(entries, key=_eviction_rank)
    return tuple(ordered[-limit:]) if limit > 0 else ()


def _on_disk(entry: Annotation) -> dict[str, Any]:
    """One entry as the file holds it.

    `refused` is a fact about the build that just read the file rather than
    about the annotation, so it is dropped. The reading it refused is restored
    under its own name, or a save here would destroy a reading this build
    merely could not parse.
    """
    return {
        **{name: field for name, field in entry.items() if name not in {"refused", "refused_raw"}},
        **({"assessment": entry["refused_raw"]} if "refused_raw" in entry else {}),
        "revisions": [
            {**rev, "lines": [dict(line) for line in rev["lines"]]} for rev in entry["revisions"]
        ],
    }


def _kept(
    config: RuntimeConfig,
    entries: Iterable[Annotation],
    *,
    keep: tuple[str, str] | None = None,
    raw: Sequence[Any] = (),
) -> tuple[Annotation, ...] | None:
    """The entries a write keeps: the count bound, then the read limit.

    Owner ruling, 2026-09-24. `_read` refuses a file over
    `annotation_read_cap_bytes`, and the next save then wrote only what this
    process held, so a store over the limit lost every reader's words at once.
    The count bounds alone allow more than any fixed limit, because
    `ensure_ascii` writes an astral character as twelve bytes. So the write
    drops entries by `_eviction_rank` until the file fits, and the next read
    reads exactly what this write kept.

    `keep` is the entry the caller is writing, and it is never the one
    dropped: None comes back instead when it cannot fit even alone, and the
    caller answers `unwritable` and writes nothing. `raw` is what this build
    could not read (`_Store.kept_raw`), carried verbatim and never dropped.

    Sized from each entry's own serialisation, for `history._store_bytes`'
    reason: `json.dump` uses the default separators and `ensure_ascii`, so the
    file is the empty envelope plus each entry plus two bytes between entries,
    exactly, and one character is one byte.
    """
    ordered = sorted(entries, key=_eviction_rank)
    written = [entry for entry in ordered if (entry["harness"], entry["sid"]) == keep]
    others = [entry for entry in ordered if (entry["harness"], entry["sid"]) != keep]
    limit = max(0, config.annotation_max_sessions - len(written))
    others = others[-limit:] if limit else []
    sizes = [len(json.dumps(_on_disk(entry))) for entry in others]
    fixed = [len(json.dumps(_on_disk(entry))) for entry in written]
    fixed += [len(json.dumps(value)) for value in raw]
    count = len(sizes) + len(fixed)
    total = len(json.dumps({"v": SCHEMA_VERSION, "entries": []})) + sum(sizes) + sum(fixed)
    total += 2 * max(0, count - 1)
    dropped = 0
    while dropped < len(others) and total > config.annotation_read_cap_bytes:
        count -= 1
        total -= sizes[dropped] + (2 if count > 0 else 0)
        dropped += 1
    if keep is not None and total > config.annotation_read_cap_bytes:
        return None
    return tuple(sorted([*others[dropped:], *written], key=_eviction_rank))


class _Store(NamedTuple):
    """The file as this build read it.

    `trusted` is False when a file exists and this build could not read it
    whole: unreadable, over the read limit, not JSON or not a store. That is
    not a missing file, and it must never be written over, because the next
    save would keep only what this process holds (owner ruling, 2026-09-24).
    `kept_raw` holds each entry this build refused, verbatim, so a save puts
    it back as `refused_raw` does for a reading.
    """

    entries: tuple[Annotation, ...]
    kept_raw: tuple[Any, ...]
    trusted: bool


def load(config: RuntimeConfig) -> tuple[Annotation, ...]:
    """Every annotation this run may read, or none if there is none to trust.

    The flag gate and nothing else. `_read` is the file, and `forget` needs the
    file whether or not this run reads annotations (DRC-4565).
    """
    if not config.annotations_enabled:
        return ()
    return _read(config)


def _read(config: RuntimeConfig) -> tuple[Annotation, ...]:
    """Every annotation on disk, or none if there is none to trust."""
    return _read_store(config).entries


def _refused_entry(value: Any) -> bool:
    """Whether `_entry` refused this record for revisions it could not read.

    Keyed and holding revisions, so it is somebody's words written by a
    build this one cannot read: a seventh line or a source it does not know.
    Anything less keyed is dropped as before.
    """
    if not isinstance(value, dict):
        return False
    key = _key(value.get("harness"), value.get("sid"))
    raw = value.get("revisions")
    return bool(key[0] and key[1] and isinstance(raw, list) and raw)


def _envelope(raw: bytes | None, cap: int) -> list[Any] | None:
    """The file's entry list, or None when the file cannot be trusted whole."""
    if raw is None or len(raw) > cap:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    entries = data.get("entries") if isinstance(data, dict) else None
    return entries if isinstance(entries, list) else None


def _read_store(config: RuntimeConfig) -> _Store:
    """The file, told apart from no file and from a file this build cannot trust.

    Read to a cap with RecursionError caught, for `lifecycle.read_state`'s
    reason: deeply nested JSON blows the recursion limit rather than raising
    ValueError, and a corrupt store must degrade to "no annotations" rather than
    take down a collection. A malformed record is dropped on its own, and one
    refused for revisions this build cannot read is kept raw.
    """
    cap = config.annotation_read_cap_bytes
    try:
        with open(store_path(config), "rb") as handle:
            raw = handle.read(cap + 1)
    except (FileNotFoundError, NotADirectoryError):
        # No file, or a state home that cannot hold one: nothing is there to lose.
        raw = b""
    except OSError:
        raw = None
    if raw == b"":
        return _Store((), (), trusted=True)
    entries = _envelope(raw, cap)
    if entries is None:
        return _Store((), (), trusted=False)
    parsed: list[Annotation] = []
    refused: list[Any] = []
    for value in entries:
        entry = _entry(
            value,
            text_cap=config.annotation_text_cap_chars,
            revision_cap=config.annotation_max_revisions,
        )
        if entry is not None:
            parsed.append(entry)
        elif _refused_entry(value):
            refused.append(value)
    return _Store(_bounded(parsed, config.annotation_max_sessions), tuple(refused), trusted=True)


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
    raw: Sequence[Any] = (),
) -> bool:
    """Write the store, reporting whether it reached disk.

    The flag gate and nothing else. `_write` is the file, for `load`'s reason.
    `raw` is what the read this write follows refused, put back verbatim.
    """
    if not config.annotations_enabled:
        return False
    return _write(config, entries, diagnostic_sink=diagnostic_sink, raw=raw)


def _write(
    config: RuntimeConfig,
    entries: Iterable[Annotation],
    *,
    diagnostic_sink: Callable[[str], None],
    raw: Sequence[Any] = (),
) -> bool:
    """Put these entries on disk, reporting whether they reached it.

    Temp file plus `os.replace`, and `0o600` in the `os.open` call rather than a
    chmod afterwards, both copied from `lifecycle.write_state`. The mode matters
    more here than on the state file: this one holds prose the reader composed,
    which `SECURITY.md` treats as the same class as the observer sidecar's goal.
    The mode is advisory and Windows ignores it, which SECURITY.md records.
    """
    kept = _kept(config, entries, raw=raw) or ()
    payload = {
        "v": SCHEMA_VERSION,
        "entries": [*(_on_disk(entry) for entry in kept), *raw],
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


def _commit(
    config: RuntimeConfig,
    state: RuntimeState,
    store: _Store,
    key: tuple[str, str],
    entries: Iterable[Annotation],
    *,
    diagnostic_sink: Callable[[str], None],
) -> str:
    """Write one mutator's result: trimmed, the written entry kept, the refused kept raw.

    Inside the caller's lock, and the cache set before the write, as every
    mutator did before this was shared. Every raw entry goes back as it was:
    a mutator refuses a session held raw before it reaches here (`_held`).
    """
    raw = store.kept_raw
    kept = _kept(config, entries, keep=key, raw=raw)
    if kept is None:
        return OUTCOME_UNWRITABLE
    state.annotations = _stored(kept)
    return (
        OUTCOME_STORED
        if save(config, kept, diagnostic_sink=diagnostic_sink, raw=raw)
        else OUTCOME_UNWRITABLE
    )


def _held(store: _Store, key: tuple[str, str]) -> bool:
    """Whether this session's own entry is one this build refused on read."""
    return any(_key(value.get("harness"), value.get("sid")) == key for value in store.kept_raw)


def refresh(config: RuntimeConfig, state: RuntimeState) -> tuple[Annotation, ...]:
    """Re-read the store into this process's copy, and return it.

    Two dashboards can bind on one machine and the file is the record, so a save
    made in one is picked up by the other on its next collection. Whether the
    file could be read whole is kept beside it, for `store_notice`.
    """
    store = _read_store(config) if config.annotations_enabled else _Store((), (), trusted=True)
    with state.annotation_lock:
        state.annotations = _stored(store.entries)
        state.annotations_trusted = store.trusted
    return store.entries


def store_notice(state: RuntimeState) -> str:
    """The board's sentence while the store cannot be read, or nothing."""
    return "" if state.annotations_trusted else STORE_UNREADABLE


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


def has_typed_words(entry: Annotation | None) -> bool:
    """Whether there is anything here for a check to have read.

    The latest revision rather than the entry's existence, and that is the
    whole of it (DRC-4560): the board's `clear` empties a box and the save
    after it mints a revision holding two empty strings, so an entry can stand
    with nothing in it while checks recorded against the earlier revisions stay
    standing. An entry-existence test would call that state annotated and let a
    session with nothing typed keep the sentence saying it was checked against
    what the reader asked for.

    The same test `reading._readable` applies before it spends anything, so the
    asked and the unasked path mean one thing by "nothing to read against".
    """
    latest: Revision | None = entry["revisions"][-1] if entry and entry["revisions"] else None
    if latest is None:
        return False
    return bool(str(latest.get("goal") or "").strip() or reading.outcome_lines(latest))


def has_typed_goal(entry: Annotation | None) -> bool:
    """Whether the latest revision holds a goal, the only words the unasked lane reads.

    The lane's own candidate test (`unasked.Lane.consider`), for the sentence
    that says what the lane checked: counting outcome lines here claimed a
    check of words it never reads (item 12 of the ruling
    `reading.MAX_OUTCOME_LINES` cites).
    """
    latest: Revision | None = entry["revisions"][-1] if entry and entry["revisions"] else None
    return bool(latest and str(latest.get("goal") or "").strip())


def is_discarded(entry: Annotation | None) -> bool:
    """Whether this entry is a discard record rather than words.

    A predicate rather than a `.get("discarded")` at each of the five places
    that ask, because the three states this store now has are told apart from
    each other and not from one field: absent is `entry is None`, present is
    `has_typed_words`, and discarded is this. A caller that inferred one from
    the negation of another is the defect DRC-4565 exists to stop shipping.
    """
    return entry is not None and not entry["revisions"] and bool(entry.get("discarded"))


def discarded_revision(entry: Annotation | None) -> int:
    """The last revision number a discard took, or 0.

    Read by `annotate` so a save over a record mints n+1. Restarting at 1
    would re-point a withdrawn departure row that recorded "read revision 2"
    at text that revision never held, which is the re-pointing `Revision`'s
    own immutability exists to refuse.
    """
    if entry is None or not is_discarded(entry):
        return 0
    return int(entry.get("discarded_revision") or 0)


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
    latest: Revision | None = entry["revisions"][-1] if entry and entry["revisions"] else None
    settled = entry.get("settled") if entry else None
    goal = latest["goal"] if latest else ""
    lines = latest["lines"] if latest else ()
    # The third answer (DRC-4565). Absent, present and discarded render in the
    # same slots, and the sentence that says "nobody typed here" over a
    # session whose words a reader deleted is the false one this replaces.
    discarded = is_discarded(entry)
    return {
        "goal": goal,
        "goal_why": (DISCARDED_GOAL if discarded else NO_GOAL_TYPED) if not goal else "",
        "lines_why": (DISCARDED_LINES if discarded else NO_LINES_TYPED) if not lines else "",
        **_published_lines(lines),
        # When the act happened, and the record's own sentence. Two keys, for
        # the reason `annotation_at` is not folded into the revision line: the
        # moment is a number a surface renders in its own register, and the
        # sentence is the store's and never composed on a page.
        "discarded_at": float(entry["discarded"]) if discarded and entry else None,
        "discarded_why": DISCARD_RECORD if discarded else "",
        "revision": latest["n"] if latest else None,
        "revision_count": len(entry["revisions"]) if entry else 0,
        "at": latest["at"] if latest else None,
        "goal_source": latest.get("goal_source", "typed") if latest else None,
        "goal_source_at": latest.get("goal_source_at") if latest else None,
        # Where the evidence opens for these words, as the producer reads it:
        # the page labels the last turn by it and the live estimate reads from it.
        "window_start": (reading.window_start(latest) or None) if latest else None,
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


def _published_lines(lines: tuple[OutcomeLine, ...]) -> dict[str, Any]:
    """Each outcome line as three flat fields, all six slots declared.

    Flat, for the reason `sessions.base_session` gives for every annotation
    field: the history allowlist admits a field by name, and a name cannot
    reach inside a list. An empty slot is `""` and `None`, never absent.
    """
    fields: dict[str, Any] = {}
    for k in range(1, reading.MAX_OUTCOME_LINES + 1):
        line = lines[k - 1] if k <= len(lines) else None
        fields[f"line_{k}"] = line["text"] if line else ""
        fields[f"line_{k}_source"] = line["source"] if line else None
        fields[f"line_{k}_source_id"] = line.get("source_id", "") if line else ""
    return fields


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
    for name in ("settled", "assessment", "readings", "withheld", "jobs"):
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
    job_id: str = "",
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
        job_id=job_id,
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
    job_id: str = "",
) -> str:
    """Store why there is no reading. Returns an `OUTCOMES` token.

    `job_id` names the reading job this outcome ends. An entry that already
    holds it answers `unchanged` and counts nothing, so one job is one attempt
    however many times its outcome reaches the store.

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
        job_id=job_id,
    )


def _recorded_job(updated: Annotation, existing: Annotation, job_id: str) -> None:
    """Add this job to the ids the entry remembers, when an outcome names one."""
    if job_id:
        updated["jobs"] = [*existing.get("jobs", ()), job_id][-RECORDED_JOBS_CAP:]


def _record(  # noqa: PLR0913 (the two callers' fields, one keyword each)
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    assessment: reading.Assessment | None,
    withheld: str,
    spent: bool,
    diagnostic_sink: Callable[[str], None] = print,
    job_id: str = "",
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
        store = _read_store(config)
        if not store.trusted:
            return OUTCOME_UNTRUSTED
        current = store.entries
        existing = find(current, *key)
        if existing is None or is_discarded(existing):
            # A reading of nothing is not a reading. There is no baseline to
            # have read, and inventing an entry here would put a row on the
            # board for a session nobody annotated.
            #
            # A discard record is the same answer one state further on, and
            # refusing it is what keeps the record text-free: `withheld` is a
            # sentence and `readings` a count, and hanging either off a record
            # would make it an entry with something in it (DRC-4565).
            return OUTCOME_REFUSED
        if job_id and job_id in existing.get("jobs", ()):
            return OUTCOME_UNCHANGED
        updated: Annotation = {
            "harness": existing["harness"],
            "sid": existing["sid"],
            "revisions": existing["revisions"],
        }
        _recorded_job(updated, existing, job_id)
        if assessment is not None:
            updated["assessment"] = assessment
        if withheld:
            updated["withheld"] = withheld
        elif "withheld" in existing:
            # Cleared rather than carried: a reading arrived.
            updated["withheld"] = ""
        if spent:
            updated["readings"] = existing.get("readings", 0) + 1
        updated["written"] = time.time()
        others = [e for e in current if (e["harness"], e["sid"]) != key]
        return _commit(
            config,
            state,
            store,
            key,
            [*others, _carried(existing, updated)],
            diagnostic_sink=diagnostic_sink,
        )


# One keyword per field a save may carry, each independent; bundling them would
# hide which one a caller left alone.
def annotate(  # noqa: PLR0913
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    goal: Any = None,
    output: Any = None,
    lines: Any = None,
    expected_revision: Any = None,
    origins: Any = None,
    now: float | None = None,
    window_start: Any = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """Save what the reader typed. Returns an `OUTCOMES` token.

    `lines` replaces the whole outcome list, `[]` clears it, and None leaves it
    alone. Replacing a stored list needs `expected_revision`, the revision the
    list was drafted against, so a second tab or a page older than the
    checklist cannot silently undo the first one's edits. `output` is the
    one-line form such an older page posts: it saves as a list of that one
    line only where no list is stored yet, and it is refused over any stored
    list, because that page sends no revision and never showed the lines.
    `origins`, beside `lines`, names the stored line each posted line came
    from (or None for a new one), so a line keeps its own entry when two
    share text; the store checks the text, so it can only keep a source,
    never claim one.

    `window_start` is the server's `reading.typed_window_start` for this save,
    computed from the session's record at `now`; None, or anything that is not
    a moment at or before the save, opens the window at the save.
    """
    legacy = lines is None and isinstance(output, str)
    if legacy:
        lines = [output]
    if expected_revision is not None and (
        isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
    ):
        return OUTCOME_REFUSED
    aligned = _aligned_origins(origins, lines, config.annotation_text_cap_chars)
    if aligned is False:
        return OUTCOME_REFUSED
    options: dict[str, Any] = {"legacy_output": legacy, "origins": aligned}
    if expected_revision is not None:
        options["expected_revision"] = expected_revision
    return _annotate(
        config,
        state,
        (harness, sid),
        goal=goal,
        lines=lines,
        now=now,
        adoption=options,
        window_start=window_start,
        diagnostic_sink=diagnostic_sink,
    )


def _aligned_origins(origins: Any, lines: Any, cap: int) -> list[int | None] | bool | None:
    """`origins` kept beside the lines `_typed_lines` keeps; None if none sent, False if bad."""
    if origins is None:
        return None
    if (
        not isinstance(origins, list)
        or not isinstance(lines, (list, tuple))
        or len(origins) != len(lines)
        or not all(
            item is None or (isinstance(item, int) and not isinstance(item, bool) and item >= 0)
            for item in origins
        )
    ):
        return False
    return [
        origin
        for origin, line in zip(origins, lines, strict=True)
        if isinstance(line, str) and records.safe_text(line, cap).strip()
    ]


def _typed_lines(value: Any, cap: int) -> list[str] | None:
    """A posted list as the lines to save, or None when it must be refused.

    Each line goes through `records.safe_text`, so a pasted line break becomes
    one space and the line stays one line. A line the cap would clip is
    refused rather than saved clipped: a reader must never find a line saved
    that is not the line they wrote. The goal still clips, as it always has.
    Blank lines are dropped, and more than six refuses the save whole.
    """
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        return None
    texts: list[str] = []
    for item in value:
        text = records.safe_text(item, cap)
        if text != records.safe_text(item, cap * 16):
            return None
        if text.strip():
            texts.append(text)
    return texts if len(texts) <= reading.MAX_OUTCOME_LINES else None


def _sourced(
    texts: list[str],
    previous: tuple[OutcomeLine, ...],
    origins: Sequence[int | None] | None = None,
) -> tuple[OutcomeLine, ...]:
    """The lines to store, each with the source the server gives it.

    The client never names a source. Each `entry` line of the revision before
    lends its source to one new line with the same text, and only one, so a
    newly typed duplicate of it is typed; any other line, an edited one
    included, is typed, as an edited adopted goal is. Which line it lends to
    is decided by the page's `origins` first, then by position, then by the
    first line with that text: two lines sharing text each keep their own.
    """
    unused = [i for i, line in enumerate(previous) if line["source"] == LINE_ENTRY]
    out: list[OutcomeLine | None] = [None] * len(texts)

    def take(i: int, j: int | None) -> None:
        if out[i] is None and j in unused and previous[j]["text"] == texts[i]:
            out[i] = previous[j]
            unused.remove(j)

    for i in range(len(texts)):
        take(i, origins[i] if origins and i < len(origins) else None)
    for i in range(len(texts)):
        take(i, i)
    for i, text in enumerate(texts):
        take(i, next((j for j in unused if previous[j]["text"] == text), None))
    return tuple(line or _typed(texts[i]) for i, line in enumerate(out))


def _unguarded_replacement(
    existing: Annotation | None, new_texts: list[str] | None, options: Mapping[str, Any]
) -> bool:
    """Whether this save would replace a stored list from a view that cannot name its revision.

    Refused rather than taken: the lines it would write away are the reader's
    own, and the page that sent it may never have shown them. A page older
    than the checklist posts one `output` and no revision, so it may type the
    first line of an empty list and nothing more.
    """
    if new_texts is None or existing is None or not existing["revisions"]:
        return False
    stored = [line["text"] for line in existing["revisions"][-1]["lines"]]
    if not stored or new_texts == stored:
        return False
    legacy = bool(options.get("legacy_output"))
    return options.get("expected_revision") is None or (legacy and len(stored) > 1)


def _typed(text: str) -> OutcomeLine:
    return {"text": text, "source": LINE_TYPED}


def _annotate(  # noqa: PLR0913
    config: RuntimeConfig,
    state: RuntimeState,
    identity: tuple[Any, Any],
    *,
    goal: Any = None,
    lines: Any = None,
    now: float | None = None,
    adoption: dict[str, Any] | None = None,
    window_start: Any = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """Append a revision to one session's annotation. Returns an `OUTCOMES` token.

    The goal and the lines are optional and independent, and a save that
    repeats the last revision verbatim appends nothing: opening the field and closing it is not a
    change of intent, and burning a revision number on it would let an
    assessment cite one. That save answers `OUTCOME_UNCHANGED`, not
    `OUTCOME_STORED`: the words are on disk either way, and only the second
    minted anything, which is the difference the page's cue states.
    """
    key = _key(*identity)
    if not config.annotations_enabled or not key[0] or not key[1]:
        return OUTCOME_REFUSED
    cap = config.annotation_text_cap_chars
    # Type-checked before redaction, not after. `records.safe_text` does
    # `str(value or "")`, so a dict arriving here would publish its Python repr
    # — with whatever is inside it — rather than being refused. `/api/ask`
    # checks for the same reason, and the endpoint above answers 400; this is
    # the store's own floor under that.
    #
    # None means "not sent" and carries the previous revision's value forward.
    # The empty string, or an empty list, means "clear this one". Collapsing
    # the two would make a client that posts only the goal silently destroy
    # the outcome lines beside it, which is the opposite of the independence
    # the two are documented to have.
    new_goal = records.safe_text(goal, cap) if isinstance(goal, str) else None
    new_texts = None if lines is None else _typed_lines(lines, cap)
    stamp = time.time() if now is None else now
    options = adoption or {}
    source_fields = _provenance({**options, "at": stamp})
    # A list the store will not take refuses the whole save, goal included:
    # saving half of what the reader pressed save on is not what they asked.
    if source_fields is None or (new_texts is None and (lines is not None or new_goal is None)):
        return OUTCOME_REFUSED

    with state.annotation_lock:
        # From disk under the lock rather than from the cached copy, so a save
        # made by a second dashboard since this one's last collection is carried
        # forward instead of being written away.
        store = _read_store(config)
        if not store.trusted or _held(store, key):
            # A session held raw is refused like an unreadable store: its
            # words are on disk, this build cannot read them, and a save here
            # would renumber from 1 over them.
            return OUTCOME_UNTRUSTED if not store.trusted else OUTCOME_UNREADABLE
        current = store.entries
        existing = find(current, *key)
        actual_revision = (
            existing["revisions"][-1]["n"] if existing and existing["revisions"] else 0
        )
        expected_revision = options.get("expected_revision")
        if (
            (expected_revision is not None and expected_revision != actual_revision)
            or (
                options.get("empty_goal_only")
                and existing
                and existing["revisions"]
                and existing["revisions"][-1]["goal"]
            )
            or _unguarded_replacement(existing, new_texts, options)
        ):
            return OUTCOME_REFUSED
        if existing is not None and not is_discarded(existing):
            last = existing["revisions"][-1]
            if new_goal is None:
                source_fields = _provenance(last) or {}
            text_goal = last["goal"] if new_goal is None else new_goal
            text_lines = (
                last["lines"]
                if new_texts is None
                else _sourced(new_texts, last["lines"], options.get("origins"))
            )
            if (last["goal"], last["lines"]) == (text_goal, text_lines) and (
                _provenance(last) or {}
            ) == source_fields:
                # Unchanged text is not a new request, so it mints no revision.
                # The cache is still refreshed from the load above: two
                # dashboards share this file, and returning early with a stale
                # cache is how this process went on reporting "no goal typed"
                # for words the other one had already saved.
                state.annotations = _stored(_bounded(current, config.annotation_max_sessions))
                return OUTCOME_UNCHANGED
            revision: Revision = {
                **source_fields,
                **_opened(source_fields, window_start, stamp),
                "n": last["n"] + 1,
                "at": stamp,
                "goal": text_goal,
                "lines": text_lines,
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
            # A save over a discard record makes the entry live again and the
            # record yields to it: nothing here carries `discarded` forward,
            # so the row stops saying a discard stands the moment there are
            # words again. The number does carry, through
            # `discarded_revision`, so the reborn entry does not reuse a
            # revision number a withdrawn raise still records having read.
            updated = {
                "harness": key[0],
                "sid": key[1],
                "revisions": (
                    {
                        **source_fields,
                        **_opened(source_fields, window_start, stamp),
                        "n": discarded_revision(existing) + 1,
                        "at": stamp,
                        "goal": new_goal or "",
                        "lines": _sourced(new_texts or [], ()),
                    },
                ),
            }
        updated["written"] = stamp
        others = [e for e in current if (e["harness"], e["sid"]) != key]
        # Inside the lock, not after it. The server is threaded, so two saves on
        # one session both read the pre-write store, both mint revision n+1, and
        # the later write erases the earlier one. Holding the lock across the
        # write costs one file write and closes the whole in-process window.
        return _commit(
            config, state, store, key, [*others, updated], diagnostic_sink=diagnostic_sink
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
        store = _read_store(config)
        if not store.trusted:
            return OUTCOME_UNTRUSTED
        current = store.entries
        existing = find(current, *key)
        # A discard record has no baseline to answer about, which is the rule
        # the docstring already states; reading its latest revision would also
        # raise, since it has none.
        if existing is None or is_discarded(existing):
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
        updated["written"] = stamp
        others = [e for e in current if (e["harness"], e["sid"]) != key]
        # `_commit` sets the cache before the write and inside the lock, as
        # `annotate` and `clear` do. `active()` serves the cached copy when it
        # is not None, and the endpoint reads back through it on the same
        # request, so a settle that skipped this would answer with the mark it
        # had just written missing.
        return _commit(
            config, state, store, key, [*others, updated], diagnostic_sink=diagnostic_sink
        )


def clear(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: Any,
    sid: Any,
    *,
    now: float | None = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> str:
    """Forget one session's words entirely. Returns an `OUTCOMES` token.

    Every revision goes, not just the latest. A reader clearing the field is
    withdrawing the request, and leaving the history behind would keep it
    citable by an assessment. That reasoning is unchanged by the record this
    now leaves in the entry's place (DRC-4565): the record holds no text of
    any kind, so there is nothing in it for an assessment to cite, and the
    assessment itself goes with the revisions.

    What the record does hold is the moment, so the act outlives the thirty
    second cue that announced it, and the last revision number, so a later
    save does not reuse one. A session that had no entry gets no record:
    discarding nothing is not a discard, and inventing one here would put a
    deletion on the board that never happened.

    The outcome for that case stays `STORED` rather than becoming `UNCHANGED`,
    which the test pinning it gives the reason for: the caller withdraws
    departure rows only on `STORED`, and an annotation evicted out from under
    its rows would otherwise leave them quoting forever.
    """
    if not config.annotations_enabled:
        return OUTCOME_REFUSED
    key = _key(harness, sid)
    if not key[0] or not key[1]:
        return OUTCOME_REFUSED
    stamp = time.time() if now is None else now
    with state.annotation_lock:
        store = _read_store(config)
        if not store.trusted or _held(store, key):
            return OUTCOME_UNTRUSTED if not store.trusted else OUTCOME_UNREADABLE
        current = store.entries
        existing = find(current, *key)
        others = tuple(e for e in current if (e["harness"], e["sid"]) != key)
        if existing is None:
            kept: list[Annotation] = list(others)
        elif is_discarded(existing):
            # Already recorded, and the stamp does not move: the record says
            # when the words went, and a second press deleted nothing.
            kept = [*others, existing]
        else:
            record: Annotation = {
                "harness": existing["harness"],
                "sid": existing["sid"],
                "revisions": (),
                "discarded": stamp,
                "discarded_revision": existing["revisions"][-1]["n"],
            }
            kept = [*others, record]
        # Inside the lock, for `annotate`'s reason.
        return _commit(config, state, store, key, kept, diagnostic_sink=diagnostic_sink)


def forget(config: RuntimeConfig) -> str:
    """Drop every discard record, keeping every entry that still holds words.

    A sweep and not a delete, which is the whole of the distinction `--forget`
    rests on: that command removes the machine's memory of what it OBSERVED,
    and a record that Cargento deleted something is squarely that class, while
    the words a reader typed are not. The module docstring's price -- that
    `--forget` does not reach this store -- still holds for those words.

    Reads and writes the file itself rather than going through `load` and
    `save`, so `annotations_enabled` cannot change the answer. `history.forget`
    is deliberately independent of its own flag for the reason its docstring
    gives -- someone turning the feature off and then asking for the file to go
    must not be told there was nothing to delete -- and a store still holding
    records is exactly that state: measured under `--no-annotations`, the sweep
    reported nothing to remove over a file that still held one.

    Three answers and not two, because the caller prints a sentence per answer.
    A bool folded "there was nothing to remove" together with "the store could
    not be written", in the one command whose whole product is telling the
    reader what went. `_write`'s own failure line is silenced here because it
    says what a reader typed will be gone, which is the opposite of what this
    failure means: nothing was written, so every record and every word stands.
    """
    store = _read_store(config)
    if not store.trusted:
        # A store this build cannot read is never written over: the sweep
        # would keep only what it could parse, which is nothing.
        return FORGET_UNTRUSTED
    entries = store.entries
    kept = tuple(entry for entry in entries if not is_discarded(entry))
    if len(kept) == len(entries):
        return FORGET_NOTHING
    if _write(config, kept, diagnostic_sink=lambda _line: None, raw=store.kept_raw):
        return FORGET_SWEPT
    return FORGET_UNWRITABLE


def _provenance(value: Mapping[str, Any]) -> Provenance | None:
    source = value.get("goal_source", "typed")
    if source == "typed":
        return {}
    at = reading.valid_prompt_time(value.get("goal_source_at"))
    saved = reading.valid_prompt_time(value.get("at"))
    if source not in reading.PROMPT_SOURCES or at is None or saved is None or at > saved:
        return None
    return {"goal_source": source, "goal_source_at": at}


def _window(value: Mapping[str, Any]) -> Window | None:
    """A stored window start, `{}` when there is none, or None when it must be refused.

    Refused rather than dropped, for `_entry`'s reason: a start that is not a
    moment at or before its own save is a rewritten file, and reading around it
    would open the window somewhere nobody chose.
    """
    if "window_start" not in value:
        return {}
    at = reading.valid_prompt_time(value.get("window_start"))
    saved = reading.valid_prompt_time(value.get("at"))
    if at is None or saved is None or at > saved:
        return None
    return {"window_start": at}


def _opened(provenance: Mapping[str, Any], typed: Any, stamp: float) -> Window:
    """The window start a new revision stores: the words' own time.

    Adopted words, including an adopted goal carried under a lines-only save,
    open at their source time. Typed words open at `typed`, recomputed on every
    save as item 13 says, else at the save. A stamp that is not itself a moment
    stores nothing, so the revision still reads back.
    """
    saved = reading.valid_prompt_time(stamp)
    if saved is None:
        return {}
    source_at = provenance.get("goal_source_at")
    at = reading.valid_prompt_time(typed if source_at is None else source_at)
    return {"window_start": at if at is not None and at <= saved else saved}


def prompt_candidate(row: dict[str, Any], source: str) -> tuple[str, float | None]:
    """Resolve the producer's source, never a client-authored goal or observer text."""
    harness = row.get("harness")
    if harness not in {"claude", "codex"}:
        return "", None
    if source == "first-prompt":
        text, at = row.get("first_prompt"), row.get("first_prompt_at")
    elif source == "latest-prompt" and harness == "claude":
        instruction = records.as_dict(row.get("instruction"))
        if instruction.get("label") != "asked":
            return "", None
        text, at = instruction.get("text"), instruction.get("at")
    elif source == "latest-prompt" and row.get("prompt_states_work") is True:
        text, at = row.get("title"), row.get("prompt_at")
    else:
        return "", None
    return (text if isinstance(text, str) else "", reading.valid_prompt_time(at))


def adopt(
    config: RuntimeConfig,
    state: RuntimeState,
    row: dict[str, Any],
    *,
    source: str,
    expected_text: Any,
    expected_at: Any,
    now: float,
    expected_revision: int | None = None,
) -> str:
    text, at = prompt_candidate(row, source)
    if (
        not text
        or at is None
        or at > now
        or expected_text != text
        or reading.valid_prompt_time(expected_at) != at
    ):
        return OUTCOME_REFUSED
    return _annotate(
        config,
        state,
        (row.get("harness"), row.get("sid")),
        goal=text,
        now=now,
        adoption={
            "goal_source": source,
            "goal_source_at": at,
            "empty_goal_only": expected_revision is None,
            "expected_revision": expected_revision,
        },
    )
