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
    """Session rows, tolerating the older schema without ``time_archived``."""
    sqlite3 = runtime_io.sqlite_module
    try:
        try:
            return list(
                con.execute(
                    "SELECT id, parent_id, directory, title, time_updated, time_archived "
                    "FROM session ORDER BY time_updated DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )
        except sqlite3.OperationalError:  # older schema without time_archived
            return list(
                con.execute(
                    "SELECT id, parent_id, directory, title, time_updated, "
                    "NULL AS time_archived FROM session "
                    "ORDER BY time_updated DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )
    except sqlite3.Error as exc:
        runtime_io.record_store_error(state, db, exc)
        return None


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
                Any, list[tuple[str, float]]
            ] = {}  # parent session id -> [(title, epoch)]
            tops: list[tuple[Any, float]] = []
            for r in rows:
                if r["time_archived"]:
                    continue  # archival bumps time_updated; don't ghost as working
                upd = records.norm_epoch(r["time_updated"])
                if r["parent_id"]:
                    if sessions.is_fresh(config, now, upd, config.working_threshold_sec):
                        children.setdefault(r["parent_id"], []).append(
                            ((r["title"] or "subagent")[:70], upd)
                        )
                else:
                    tops.append((r, upd))
            for r, upd in tops:
                agents = sorted(children.get(r["id"], []), key=lambda a: -a[1])
                activity_sources = (upd, *(m for _, m in agents))
                last_activity = sessions.newest_plausible(config, now, activity_sources)
                active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
                if not (active or show_all):
                    continue
                # `model` is always present on a subagent element, per the
                # contract in `sessions.base_session`. None here says nobody has
                # looked for where OpenCode records the model, not that OpenCode
                # runs on none.
                subagents = [
                    {"name": label, "model": None, "started_at": None} for label, _ in agents
                ]
                session_state, state_detail = "idle", "awaiting your message"
                if sessions.is_fresh(config, now, last_activity, config.working_threshold_sec):
                    session_state = "working"
                    state_detail = sessions.working_detail(None, subagents)

                turn = None
                last_prompt = ""
                if active:
                    events = []
                    try:
                        # The message kind lives in the `type` COLUMN (tagged
                        # union discriminator); `data` omits type/id and holds
                        # the prompt in data.text.
                        msgs = con.execute(
                            "SELECT type, time_created, data FROM session_message "
                            "WHERE session_id = ? ORDER BY time_created DESC LIMIT ?",
                            (r["id"], config.sql_message_limit),
                        ).fetchall()
                        for m in reversed(msgs):
                            is_user = m["type"] == "user"
                            events.append((records.norm_epoch(m["time_created"]), is_user))
                            if is_user:
                                try:
                                    jd = json.loads(m["data"] or "{}")
                                except (ValueError, TypeError):
                                    jd = {}
                                last_prompt = records.extract_text(jd) or last_prompt
                    except sqlite3.Error:
                        pass
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
                        "state": session_state,
                        "state_detail": state_detail,
                        "active": active,
                        "last_activity": last_activity,
                        "turn": turn,
                        "subagents": subagents,
                    }
                )
                out.append(s)
        finally:
            con.close()
    return out
