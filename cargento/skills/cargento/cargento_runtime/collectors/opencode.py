"""OpenCode collection from its read-only SQLite store."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cargento_runtime import io as runtime_io
from cargento_runtime import records, sessions, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState

_DB_GLOB = ("opencode*.db",)

# The `session` selects, widest first. Each one down is a column the widest read
# wants and an older store may not have, substituted with NULL so every caller
# indexes the same row shape. A ladder rather than a `PRAGMA table_info` probe
# because the probe cannot distinguish "no such column" from "no such table",
# and a store with no `session` table at all has to reach `record_store_error`.
_SESSION_SELECTS: tuple[str, ...] = (
    "SELECT id, parent_id, directory, title, time_updated, time_archived, model FROM session",
    (
        "SELECT id, parent_id, directory, title, time_updated, time_archived, "
        "NULL AS model FROM session"
    ),
    (
        "SELECT id, parent_id, directory, title, time_updated, "
        "NULL AS time_archived, NULL AS model FROM session"
    ),
)


def _json(raw: Any) -> dict[str, Any]:
    try:
        return records.as_dict(json.loads(raw or "{}"))
    except (ValueError, TypeError):
        return {}


def _session_model(raw: Any) -> str | None:
    """The model on a `session` row, which 1.18.20 stores as a JSON object.

    Measured on a real 1.18.20 store:
    `{"id": "...", "providerID": "...", "variant": "default"}`, the shape its
    own `Session.setAgentModel` writes. A bare string is accepted too, since
    the column is untyped text and an older build's spelling is not measured
    here.
    """
    if not raw:
        return None
    data = _json(raw)
    ident = data.get("id") if data else raw
    return records.safe_text(ident, sessions.MODEL_CAP_CHARS).strip() or None


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether an OpenCode database is present and readable at all.

    False without sqlite3: reporting the harness as discovered when it can
    never be opened would show it as present but permanently empty.
    """
    return runtime_io.sqlite_available() and runtime_io.any_glob_stores(
        config, "opencode.data", *_DB_GLOB
    )


def _session_rows(
    con: Any,
    state: RuntimeState,
    db: str,
    limit: int,
) -> list[Any] | None:
    """Session rows, tolerating an older schema missing the newer columns."""
    sqlite3 = runtime_io.sqlite_module
    last: Exception | None = None
    for select in _SESSION_SELECTS:
        try:
            return list(
                con.execute(
                    f"{select} ORDER BY time_updated DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )
        except sqlite3.Error as exc:
            last = exc
    if last is not None:
        runtime_io.record_store_error(state, db, last)
    return None


def _prompt_from_parts(con: Any, config: RuntimeConfig, message_id: Any, gaps: set[str]) -> str:
    """The text of one user message, out of its `part` rows.

    Bounded by ``sql_message_limit`` even though these are parts rather than
    messages: the capture recorded 58 parts behind 23 messages, so the two
    cannot share one budget, and the same ceiling applied per table is a bound
    on both without a second knob nobody can calibrate.

    Only ``type == "text"`` parts count. A user message also carries file and
    agent-mention parts, and admitting those would publish an attached
    filename as the prompt the person typed.
    """
    sqlite3 = runtime_io.sqlite_module
    try:
        rows = con.execute(
            "SELECT data FROM part WHERE message_id = ? ORDER BY id LIMIT ?",
            (message_id, config.sql_message_limit),
        ).fetchall()
    except sqlite3.Error:
        gaps.add(sessions.UNREAD_HISTORY)
        return ""
    texts = []
    for row in rows:
        data = _json(row["data"])
        if data.get("type") != "text":
            continue
        text = records.extract_text(data)
        if text:
            texts.append(text)
    return " ".join(texts)


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    if not runtime_io.sqlite_available():
        return []
    sqlite3 = runtime_io.sqlite_module
    out: list[Session] = []
    for db in runtime_io.glob_stores(config, "opencode.data", *_DB_GLOB):
        try:
            con = runtime_io.open_sqlite_read_only(db, state)
        except sqlite3.Error:
            continue
        # ?all=1 promises every session ever; LIMIT -1 is SQLite's "no limit".
        rows = _session_rows(con, state, db, -1 if show_all else 200)
        if rows is None:
            con.close()
            continue
        try:
            children: dict[
                Any, list[tuple[str, float, str | None]]
            ] = {}  # parent session id -> [(title, epoch, model)]
            tops: list[tuple[Any, float]] = []
            for r in rows:
                if r["time_archived"]:
                    continue  # archival bumps time_updated; don't ghost as working
                upd = records.norm_epoch(r["time_updated"])
                if r["parent_id"]:
                    if sessions.is_fresh(config, now, upd, config.working_threshold_sec):
                        children.setdefault(r["parent_id"], []).append(
                            (
                                (r["title"] or "subagent")[:70],
                                upd,
                                _session_model(r["model"]),
                            )
                        )
                else:
                    tops.append((r, upd))
            for r, upd in tops:
                # One row's cost, and never the store's or the harness's. Same
                # rule and same reason as `collectors/goose.py`: this body is a
                # straight-line build, so an exception in it does not say which
                # published field is wrong and the row is the smallest unit it
                # invalidates.
                # [U-5](docs/design-unread-sources.md#u-5).
                try:
                    agents = sorted(children.get(r["id"], []), key=lambda a: -a[1])
                    activity_sources = (upd, *(m for _, m, _ in agents))
                    last_activity = sessions.newest_plausible(config, now, activity_sources)
                    active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
                    if not (active or show_all):
                        continue
                    # A child session keeps its own `session` row, so its model is
                    # the same read done twice rather than the parent's attributed
                    # downwards — the shape `collectors/cursor.py` already uses.
                    subagents = [
                        {
                            "name": label,
                            "model": child_model,
                            "started_at": None,
                            "active": None,
                            "parent": None,
                        }
                        for label, _, child_model in agents
                    ]
                    session_state, state_detail = "idle", "awaiting your message"
                    if sessions.is_fresh(config, now, last_activity, config.working_threshold_sec):
                        session_state = "working"
                        state_detail = sessions.working_detail(None, subagents)

                    turn = None
                    last_prompt = ""
                    gaps: set[str] = set()
                    # Read off the session row, so an idle session outside the
                    # window still names its model; the message fallback below needs
                    # the transcript read and is therefore gated with it.
                    model = _session_model(r["model"])
                    if active:
                        events = []
                        newest_user: Any = None
                        from_message: str | None = None
                        try:
                            # Turns and prompts live in `message` and `part`, not in
                            # `session_message`. Measured on OpenCode 1.18.20:
                            # `opencode db` ran the migrations and `opencode import`
                            # wrote one session, and `session_message` came back
                            # with 0 rows against 2 messages and 2 parts; the
                            # capture at docs/captures/opencode/ records the same
                            # store with 0 against 23 and 58. `message` has no
                            # `type` column — the role is inside `data` — and the
                            # text is inside `part.data`, so both halves of the read
                            # this replaced were wrong, not just the table name.
                            msgs = con.execute(
                                "SELECT id, time_created, data FROM message "
                                "WHERE session_id = ? ORDER BY time_created DESC LIMIT ?",
                                (r["id"], config.sql_message_limit),
                            ).fetchall()
                            for m in reversed(msgs):
                                data = _json(m["data"])
                                role = data.get("role")
                                if role not in ("user", "assistant"):
                                    gaps.add(sessions.UNREAD_HISTORY)
                                    # An unknown role cannot extend a measured turn
                                    # as though it were a recognised reply.
                                    continue
                                is_user = role == "user"
                                events.append((records.norm_epoch(m["time_created"]), is_user))
                                if is_user:
                                    newest_user = m["id"]  # oldest-first, so the last wins
                                elif role == "assistant":
                                    # `modelID` on the newest assistant message,
                                    # measured populated on a real 1.18.20 store.
                                    # It stands behind `session.model` rather than
                                    # in front of it, because that column is what
                                    # the next turn will run on — but it is
                                    # optional in OpenCode's own session schema, so
                                    # a row can carry none while its transcript
                                    # still names what ran.
                                    from_message = (
                                        records.safe_text(
                                            data.get("modelID"), sessions.MODEL_CAP_CHARS
                                        ).strip()
                                        or from_message
                                    )
                        except sqlite3.Error:
                            # The turn, the prompt and the model fallback all ride
                            # this one read, so the row that survives it is thinner
                            # than a quiet session's and looks identical to one.
                            gaps.add(sessions.UNREAD_HISTORY)
                        model = model or from_message
                        if newest_user is not None:
                            last_prompt = _prompt_from_parts(con, config, newest_user, gaps)
                        turn = turns.turn_progress(
                            turns.turns_from_events(events), session_state, now, config
                        )

                    s = sessions.base_session(
                        "opencode",
                        r["id"],
                        sessions.project_from_cwd(config, r["directory"] or "") or "opencode",
                    )
                    s.update(
                        {
                            "title": records.redact_clip(
                                (r["title"] or "").strip(), records.PROMPT_TITLE_CAP_CHARS
                            )
                            or None,
                            # Redacted here rather than where it is assigned, for
                            # the reason `collectors/goose.py` gives: once, on what
                            # is published, not on every prompt the loop walks past.
                            "last_prompt": records.redact_clip(
                                last_prompt, records.LAST_PROMPT_CAP_CHARS
                            ),
                            "model": model,
                            "state": session_state,
                            "state_detail": state_detail,
                            "active": active,
                            "last_activity": last_activity,
                            "turn": turn,
                            "subagents": subagents,
                            "source_gaps": sorted(gaps),
                        }
                    )
                    out.append(s)
                except Exception as exc:  # noqa: BLE001 — one bad row, not the harness
                    # Recorded rather than swallowed, for the reason
                    # `goose.py`'s matching handler gives: `--diagnose` is
                    # the only reader `state.store_errors` has, and going
                    # silent here would buy row retention with silence.
                    runtime_io.record_store_error(state, db, exc)
                    continue
        except Exception as exc:  # noqa: BLE001 — one bad store, not the harness
            # The `except` this `try` never had. Everything the loop raises is
            # already caught per row above, so what lands here was raised
            # outside a row body and costs this store only: `out` is the
            # accumulator across candidate stores, and the rows in it — this
            # store's earlier rows included — publish.
            runtime_io.record_store_error(state, db, exc)
        finally:
            con.close()
    return out
