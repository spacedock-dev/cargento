"""GitHub Copilot CLI collection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, NamedTuple

from cargento_runtime import config as runtime_config
from cargento_runtime import io as runtime_io
from cargento_runtime import records, sessions, transcripts, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState

# history-session-state is assumed to share the <uuid>/events.jsonl layout —
# unverified legacy format; a mismatch just means those old sessions stay
# invisible. Discovery and collection read the same tuple so they cannot drift.
_STORE_BASES = ("session-state", "history-session-state")


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether either the current or the history Copilot store is present."""
    return any(runtime_io.any_store_dir(config, "copilot.root", base) for base in _STORE_BASES)


# One AI Unit, in the nano-AIU the store records. GitHub bills Copilot in AIU
# now; the older per-session `totalPremiumRequests` counter reads 0 on an
# AIU-billed account, so it is deliberately not read.
_NANO_PER_AIU = 1_000_000_000
_USAGE_ROW_CAP = 5000


def _aiu_text(nano: int) -> str:
    """Nano-AIU as the figure both the harness tile and a session row publish.

    AIU, not currency, and that is the whole point. Converting needs a rate
    Cargento does not have and the CLI does not write down, and
    ``docs/design-session-identity.md`` already records why a list-price estimate
    was rejected for Pi's per-turn ``cost``. The same reasoning applies here with
    less room for argument, because a Copilot AIU is drawn from a subscription
    allowance rather than invoiced: the reader can compare this against the plan
    they are on, whereas a dollar figure would read as authoritative and be wrong.

    One formatter for both surfaces, so the same quantity cannot render two ways.
    """
    return f"{nano / _NANO_PER_AIU:.2f} AIU"


def _nano_amount(value: Any) -> int | None:
    """One ``total_nano_aiu`` cell as nano-AIU, or None when it is not an amount.

    ``bool`` is excluded explicitly because it is an ``int`` in Python, so a
    ``True`` in that column would otherwise be counted as a nano-AIU of spend.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return None
    return int(value)


class _Ledger(NamedTuple):
    """One window of Copilot's per-request billing rows, already reduced.

    ``total`` is every in-window row and is what the harness tile publishes, or
    None when any row that belonged in the window could not be accounted for. A
    sum missing an unknown addend is not a total: the reader would be shown a
    lower bound in the type of a measurement, with nothing on the page to say so.

    ``by_session`` is the same rows keyed by the ``session_id`` each one names,
    where a missing key is a *measured zero* rather than a missing measurement.
    That holds only because the two things that could falsify it are handled
    elsewhere: ``_read_ledger`` declines to return a ``_Ledger`` at all unless it
    could read the window to its end, and any session named by a row it could not
    account for is listed in ``unmeasured`` instead of reading zero here.

    ``unmeasured`` is those sessions. They have a figure — the ledger says so —
    and Cargento cannot state it, which is a third reading from both a number and
    a zero and has to survive into the payload as None.

    ``by_session`` and ``total`` are separate accumulators rather than a sum and
    its parts, because a row naming no session is still real consumption.
    Dropping it would understate the harness figure, and attributing it to some
    session would be worse. So the per-session figures need not add up to
    ``total``, and the gap is honest.

    ``models`` is the model each row names, keyed by ``(session_id, agent_id)``
    with None for the ledger's SQL NULL — which is what a row for the session
    itself carries, as against the ``sidekick-…`` string on a subagent's rows.
    Both halves of the key are needed: the NULL group spans every session in the
    store (2 of 2 on the store this was measured against), so keying on
    ``agent_id`` alone would hand every session whichever model was seen first.

    It is a separate accumulator from the two above for a reason that has to
    survive refactoring: **a model and a charge are withdrawn independently, in
    both directions.** A row whose model cell is unusable still has a perfectly
    accountable charge, and blacking out a session's spend over it would be the
    same over-withdrawal the note above rejects for an unattributed row. A row
    whose charge or stamp is unreadable still names a model, and that reading is
    good — which is why the accumulation happens before both of the loop's
    ``continue`` statements. Window coverage and model coverage are different
    questions, so an idle session outside the window can carry a model while its
    ``consumption`` is None.
    """

    by_session: dict[str, int]
    models: dict[tuple[str, str | None], str | None]
    unmeasured: frozenset[str]
    total: int | None
    newest: float


def _usage_rows(config: RuntimeConfig, state: RuntimeState) -> list[Any] | None:
    """The newest billing rows the session store holds, or None if it holds none.

    ``session_id`` is selected because the join is measured: on a live store the
    distinct values matched the ``session-state/<uuid>`` directory names 2 of 2,
    and those basenames are exactly what ``collect`` publishes as ``sid``.

    ``agent_id`` and ``model`` ride along on the statement that was already being
    run, which is the whole cost of publishing a session's model: two more
    columns in one existing projection, no second query, no second connection,
    and no per-session read. ``agent_id`` is SQL NULL on a row the session itself
    ran and ``sidekick-<name>-<epoch ms>`` on a subagent's, so selecting it is
    what lets the caller keep those two apart.

    ``ORDER BY id DESC`` is what makes newest-wins free. ``id`` is
    ``INTEGER PRIMARY KEY AUTOINCREMENT`` and was verified monotone against
    ``created_at`` over every row of a live store, so the first row a key is seen
    on is its newest — with no timestamp parsed, which matters because an
    unparseable stamp is a failure class this file already handles.

    One row past ``_USAGE_ROW_CAP`` is read deliberately. It is the only thing
    that separates "that was the whole ledger" from "there is history behind this
    we chose not to read", and the caller needs that apart to know whether a
    session's absence from the ledger means it spent nothing.
    """
    if not runtime_io.sqlite_available():
        return None
    root = runtime_config.primary_store(config, "copilot.root")
    database = os.path.join(root, "session-store.db")
    if not os.path.isfile(database):
        return None
    try:
        connection = runtime_io.open_sqlite_read_only(database, state)
    except Exception:  # noqa: BLE001 — a broken store must not fail the harness
        return None
    try:
        rows: list[Any] = connection.execute(
            "SELECT session_id, agent_id, model, total_nano_aiu, created_at "
            "FROM assistant_usage_events ORDER BY id DESC LIMIT ?",
            (_USAGE_ROW_CAP + 1,),
        ).fetchall()
    except Exception:  # noqa: BLE001 — schema drift is a miss, never an error
        runtime_io.record_store_error(state, database, RuntimeError("no assistant_usage_events"))
        return None
    finally:
        connection.close()
    return rows


def _row_model(value: Any) -> str | None:
    """One reported model as a model name, or None when it is not one.

    The single door for both of this harness's model readings — the ledger cell
    a session's own rows carry, and the value a subagent's start event reports —
    so the two cannot end up bounded differently or guarded differently.

    The ledger column is ``TEXT NOT NULL`` on the live store and the guard is
    still needed: NOT NULL excludes only NULL, so ``''`` passes it. An event
    payload is untyped JSON and offers no guarantee at all.

    Bounded here because this is where the payload is assembled and where the
    declared width lives. The value is a vendor's own string on its way to the
    DOM, and it lands inline on a metadata row beside the project and the
    session id, so an unbounded one pushes everything after it off the card.
    """
    if not isinstance(value, str):
        return None
    return records.safe_text(value, sessions.MODEL_CAP_CHARS).strip() or None


def _read_ledger(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
) -> _Ledger | None:
    """Copilot's consumption over the window, or None when it cannot be measured.

    The one reducer behind both the harness tile and the per-session figure, so
    those are one measurement read twice rather than two readings that agree by
    inspection. Both window on each row's own ``created_at``, over the same
    ``window_hours`` the payload already publishes once at the top level.

    That is the answer to the obvious alternative — a per-session *lifetime*
    total, on the argument that what a session spent is a property of the session
    — and it loses twice. It would not add up to the tile printed beside it, so a
    reader comparing the two is reading two different questions with no way to
    tell; and the row cap would silently turn a long session's "total" into a
    partial one, which is the confident-looking wrong number this codebase treats
    as worse than no number.

    None is the third state, and the reason this returns an option rather than an
    empty ledger. An absent, unreadable or drifted store means there is no
    accounting for Copilot at all — and so does a ledger longer than the cap
    whose read never reached back past the window's far edge, because with the
    newest rows first an unread tail there can hold any amount of in-window spend.
    Reading either of those as zero would report a busy session as a free one.

    A single row can be that same nothing in miniature, and it gets the same
    rule: a row this cannot account for is spend of unknown size, so it withdraws
    exactly the figures it would have fed. It always withdraws ``total`` — one
    unknown addend and the sum is not a sum — and it withdraws the figure of the
    session it names, if it names one. That scoping is the deliberate part.
    Withdrawing nothing is what published the false zero this replaces;
    withdrawing everything is safe but hands one malformed row the power to black
    out every session in the harness, and it is not needed, because a row naming
    a session says precisely which figure it spoils. A row naming no session
    takes no session's figure with it, on the same reading of the store that
    keeps such a row's *spend* out of every session's figure: unattributed rows
    belong to nobody, and voiding every session over one would contradict the
    rule beside it.

    Two kinds of row cannot be accounted for. An unreadable *amount* is the plain
    case. An unreadable *stamp* is the subtle one: it places itself nowhere, so
    it neither counts toward the window nor vouches for the window having been
    read to its end, and conflating either of those with an old row would
    manufacture coverage. An out-of-window row is in neither class — it
    contributes nothing whatever its amount column holds, so a null charge on a
    week-old row costs nothing and still proves the read reached past the edge.

    The model each row names is read first and kept in its own map, because it
    is a different question from every one above: see ``_Ledger``. The one route
    by which a model is lost to a *charge* failure is the truncation guard below,
    which returns no ledger at all and takes the models with it. That is accepted
    rather than restructured — it degrades to "no model reported", which is never
    wrong, only incomplete — and it is recorded here so the next reader does not
    read it as an oversight.

    The tile and the collection call this separately, so a refresh pays the
    bounded read twice. Caching it between them would trade one cheap read for a
    real staleness risk: the two calls are the same refresh but not the same
    instant, and a cache is the thing that would let them drift apart.
    """
    rows = _usage_rows(config, state)
    if rows is None:
        return None
    window_sec = window_hours * 3600
    by_session: dict[str, int] = {}
    models: dict[tuple[str, str | None], str | None] = {}
    unmeasured: set[str] = set()
    total = 0
    measured = True
    newest = 0.0
    reached_past_window = False
    for row in rows:
        session_id = row["session_id"]
        named = session_id if isinstance(session_id, str) and session_id else None
        if named:
            # Ahead of both `continue`s below, and that placement is the whole
            # point: an old row and a row whose charge will not read are both
            # still perfectly good statements of which model ran. An unusable
            # cell records None deliberately rather than falling through to an
            # older row — `setdefault` means the newest reading wins, including
            # when the newest reading is "cannot tell", which is the one answer
            # a stale row must never be allowed to overwrite.
            agent_id = row["agent_id"]
            key = (named, agent_id if isinstance(agent_id, str) and agent_id else None)
            models.setdefault(key, _row_model(row["model"]))
        stamp = records.parse_utc_sql(row["created_at"])
        seconds = sessions.age(config, now, stamp) if stamp else None
        if seconds is not None and seconds > window_sec:
            reached_past_window = True
            continue
        nano = _nano_amount(row["total_nano_aiu"]) if seconds is not None else None
        if nano is None:
            measured = False
            if named:
                unmeasured.add(named)
            continue
        total += nano
        if named:
            by_session[named] = by_session.get(named, 0) + nano
        newest = max(newest, stamp)
    if len(rows) > _USAGE_ROW_CAP and not reached_past_window:
        return None
    return _Ledger(by_session, models, frozenset(unmeasured), total if measured else None, newest)


def _session_consumption(ledger: _Ledger | None, sid: str, active: bool) -> str | None:
    """What one session spent over the window, or None when that is not known.

    Three readings, and the None cases are the whole point of the function. No
    ledger is no accounting for this harness at all. A ledger that could not
    account for a row naming this session knows there was spend and not how much.

    The third is the quiet one. A zero here is a claim about coverage — the
    window was read to its end and holds nothing against this session — and that
    claim is only available for a session the window covers. An idle session
    older than the window is outside it entirely, so the ledger has no reach over
    the period the session was actually running, and "0.00 AIU" would answer a
    question about the last ``window_hours`` in the type of an answer about this
    session. Those rows come back under "Show all N idle", beside detail panels
    that promise what the session spent, where a measured zero reads as a free
    session rather than an unread one.

    A stale session that *does* appear in the window keeps its figure. A positive
    number claims only that these rows exist, which is true; it is the zero that
    claims the window looked in the right place.
    """
    if ledger is None or sid in ledger.unmeasured:
        return None
    nano = ledger.by_session.get(sid)
    if nano is None:
        return _aiu_text(0) if active else None
    return _aiu_text(nano)


def usage(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
) -> list[dict[str, Any]]:
    """Copilot's own consumption record, summed over the dashboard's window.

    Unlike Codex and Claude this is consumption without a limit: GitHub keeps
    the entitlement server-side and the CLI never writes it down, so there is
    no percentage to publish and the entry carries ``used`` instead of window
    gauges. The figure is real spend rather than an estimate, taken from the
    per-request rows the CLI records for its own billing display.

    Windowed on each row's own timestamp, so the number answers "in the last
    ``window_hours``" rather than "since whenever these session files began",
    which would drift with how much history happens to be retained. Which rows
    those are, and when there are none to be had, is ``_read_ledger``'s decision
    — the same one that gives each session row its own share of this total.

    The tile is published only against a total the whole window supports. One
    in-window row whose charge could not be read is enough to withhold it, for
    the same reason a truncated read withholds it: what would go on screen is a
    lower bound wearing the word "used".
    """
    ledger = _read_ledger(config, state, now, window_hours)
    if ledger is None or ledger.total is None or not ledger.newest:
        return []
    return [
        {
            "harness": "copilot",
            "state": "ok",
            "asOf": int(ledger.newest),
            "used": _aiu_text(ledger.total),
        }
    ]


class _Gate(NamedTuple):
    """A permission prompt standing in front of a person, and when it opened.

    ``at`` is the request's own timestamp, or 0 when the record carried none the
    parser could read; the caller falls back to the file's mtime rather than
    publishing a wait that began at the epoch. ``kind`` is the closed
    ``permissionRequest.kind`` vocabulary, or None for a spelling this build has
    not measured.
    """

    at: float
    kind: str | None


# How long a request must have stood before it is read as a person being held
# up. It exists for one measured race: `copilot -p` without `--allow-all-tools`
# is not refused, it auto-denies every gated call, and the capture times that
# pair 1 ms apart. A collection tick landing inside that millisecond — or on a
# `permission.completed` line still being appended, which the parser drops as
# unreadable JSON — sees a request with nothing behind it and raises a real
# desktop popup for a run nobody is watching.
#
# Two seconds is three orders of magnitude above the 1 ms it has to beat and an
# order below the 23 s shortest gate the capture recorded, so a prompt in front
# of a person is not withheld by it: the collection that would have reported it
# at 0.2 s reports it on the next tick anyway.
_MIN_GATE_STAND_SEC = 2.0


def _standing_gate(
    config: RuntimeConfig,
    info: dict[str, Any] | None,
    now: float,
    mtime: float,
) -> _Gate | None:
    """The oldest unanswered permission request in the tail, if there is one.

    None means the tail holds no request without an answer behind it, which is
    both "nothing was ever asked" and "everything asked has been answered". The
    two are the same fact about the person: nobody is waiting on them.

    The oldest, not the newest, because the gate queue ranks on ``blocked_since``
    and the longest-standing prompt is the one that has actually cost somebody
    something. Taking the newest would restart the clock every time a second
    prompt opened behind the first.

    A request whose stamp would not parse sorts after every dated one rather than
    to the front on its zero. It still wins when it is the only thing standing —
    the map is in file order, so the first entry is the first asked — which keeps
    an unparseable stamp a missing *reading* rather than a missing gate.

    The floor is measured against the stamp the row would publish, so the wait it
    tests is the wait the reader would have been shown. A stamp too far in the
    future to age measures nothing and is left alone: the floor drops a request
    too *young* to be a prompt, not one whose clock cannot be trusted.
    """
    pending = (info or {}).get("pending_permissions") or {}
    if not pending:
        return None
    oldest = min(pending.values(), key=lambda entry: (not entry["at"], entry["at"]))
    gate = _Gate(float(oldest["at"] or 0), oldest["kind"])
    stood = sessions.age(config, now, gate.at or mtime)
    if stood is not None and stood < _MIN_GATE_STAND_SEC:
        return None
    return gate


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    files: dict[
        str, tuple[float, str]
    ] = {}  # session uuid -> newest events.jsonl (dir tie: current)
    for base in _STORE_BASES:
        for fp in runtime_io.glob_stores(
            config,
            "copilot.root",
            base,
            "*",
            "events.jsonl",
        ):
            sid = os.path.basename(os.path.dirname(fp))
            try:
                mtime = os.path.getmtime(fp)
            except OSError:
                continue
            if sid not in files or mtime > files[sid][0]:
                files[sid] = (mtime, fp)

    # Read once for the whole collection, not once per row: every session's
    # figure is a slice of the very ledger the harness tile sums, so the two
    # cannot end up describing different windows of the same store.
    ledger = _read_ledger(config, state, now, window_hours)

    out: list[Session] = []
    for sid, (mtime, fp) in files.items():
        active = sessions.is_fresh(config, now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        info = transcripts.analyze_copilot_events(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, mtime)
        session_state, state_detail = "idle", "awaiting your message"
        blocked_since = None
        gate = _standing_gate(config, info, now, mtime)
        # `{"name": str, "model": str | None}` each, built in
        # `transcripts.analyze_copilot_events` where the name and the model come
        # off one JSON object. Only a working session has any: `info` is None
        # unless the session is active, so a Copilot subagent's model is visible
        # only while it is running — which is also why it cannot be exercised
        # against an idle fixture.
        #
        # The published model is raw, not a decision. Whether a child's model is
        # worth the space is a comparison against the parent's, both measured,
        # and the page owns that rule for every harness at once; deciding it here
        # would put one rule in ten places.
        subagents: list[dict[str, Any]] = []
        busy = sessions.is_fresh(
            config,
            now,
            sessions.newest_plausible(config, now, last_event_sources),
            config.working_threshold_sec,
        )
        # Published from the gate branch as well as the busy one, because a gate
        # says the parent is held up and says nothing about the children already
        # running. Bound to those two rather than to `info` so an idle row's pills
        # keep retiring the way they always have.
        if gate is not None or busy:
            subagents = [
                {
                    "name": pending.get("name") or "subagent",
                    "model": _row_model(pending.get("model")),
                }
                for pending in (info or {}).get("pending_agents", {}).values()
            ]
        if gate is not None:
            # Ahead of the busy test, and that order is the measurement rather
            # than a preference: `permission.requested` lands 0.045 s after the
            # `tool.execution_start` it gates, so every gate opens well inside the
            # working window and a Working row here would be the whole defect.
            # Claude's collector resolves the same conflict the same way, for the
            # same reason (docs/design-needs-input.md N-2).
            session_state = "needs_input"
            blocked_since = gate.at or mtime
            waited = sessions.fmt_duration(sessions.age(config, now, blocked_since))
            state_detail = (
                f"permission request ({gate.kind}), waiting {waited}"
                if gate.kind
                else f"permission request, waiting {waited}"
            )
        elif busy:
            session_state = "working"
            state_detail = sessions.working_detail(info, subagents)

        cwd = (info or {}).get("cwd") or transcripts.copilot_meta(config, state, fp).get("cwd")
        s = sessions.base_session(
            "copilot", sid, sessions.project_from_cwd(config, cwd or "") or "copilot"
        )
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                # A session Cargento cannot account for must not read as one that
                # spent nothing: every route to the declared None is in
                # _session_consumption, and the zero it publishes is only ever
                # against a window that was read to its end, that covers this
                # session, and that holds no row for this sid.
                "consumption": _session_consumption(ledger, sid, active),
                # The ledger's own rows for this session, which are the ones
                # carrying no `agent_id`. Never a subagent's row: a child runs on
                # its own model, and reading one off the parent's card would put
                # a measured value where it does not belong. `provider` stays
                # None on purpose — Copilot's authority is Copilot, and "via
                # Copilot" beside a Copilot badge is a clause that says nothing.
                "model": ledger.models.get((sid, None)) if ledger else None,
                "state": session_state,
                "state_detail": state_detail,
                "blocked_since": blocked_since,
                # `own_activity` stays at the declared 0, and that is a decision
                # rather than an omission. It exists so the overlay reducer can
                # retire a wait no hook ever closes; a wait this collector raised
                # needs no such rescue, because the record that answers the gate
                # is the record that clears it on the next refresh. Nor could it
                # help here: Copilot has no entry in `events.IDENTITY_NORMALIZERS`,
                # so no overlay ever reaches one of these rows and the reducer
                # never runs. Publishing it would be a field nothing reads.
                "active": active,
                "last_activity": mtime,
                "turn": turns.turn_progress(
                    turns.scan_turns(config, state, fp, "copilot") if info else None,
                    session_state,
                    now,
                    config,
                ),
                "subagents": subagents,
            }
        )
        out.append(s)
    return out
