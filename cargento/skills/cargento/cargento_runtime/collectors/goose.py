"""Goose collection from its shared read-only SQLite store."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cargento_runtime import io as runtime_io
from cargento_runtime import records, sessions, turns

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState


def discover(config: RuntimeConfig, _state: RuntimeState) -> bool:
    """Whether a readable Goose sessions database is present."""
    return runtime_io.sqlite_available() and bool(runtime_io.existing_stores(config, "goose.db"))


def _user_prompt(content: Any) -> bool:
    """Return whether a Goose role=user message came from the human.

    Goose also records tool results with role=user; those entries carry a
    toolResponse content part and must not start a new turn.
    """
    if not isinstance(content, list):
        return True
    return not any(
        isinstance(part, dict) and records.alnum(part.get("type")) == "toolresponse"
        for part in content
    )


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    if not runtime_io.sqlite_available():
        return []
    # Goose keeps its store in a different place per platform, so scan every
    # candidate that exists rather than betting on one.
    out: list[dict[str, Any]] = []
    for db in runtime_io.existing_stores(config, "goose.db"):
        out.extend(_collect_db(config, state, db, now, window_hours, show_all))
    return out


def _collect_db(
    config: RuntimeConfig,
    state: RuntimeState,
    goose_db: str,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
    # Single shared sessions.db (v1.10.0+): per-session activity comes from
    # the updated_at column, NOT file mtime (the DB is shared by all
    # sessions). Legacy per-session .jsonl files are not supported.
    try:
        con = runtime_io.open_sqlite_read_only(goose_db, state)
    except runtime_io.sqlite_module.Error:
        return []
    try:
        try:
            rows = con.execute(
                "SELECT id, description, working_dir, updated_at, "
                "session_type, parent_session_id, archived_at FROM sessions"
            ).fetchall()
        except runtime_io.sqlite_module.OperationalError:  # older schema without those columns
            rows = con.execute(
                "SELECT id, description, working_dir, updated_at, "
                "NULL AS session_type, NULL AS parent_session_id, "
                "NULL AS archived_at FROM sessions"
            ).fetchall()

        children: dict[Any, list[tuple[str, float]]] = {}  # parent session id -> [(label, epoch)]
        tops: list[tuple[Any, float]] = []
        for r in rows:
            if r["archived_at"]:
                continue  # archival bumps updated_at; don't resurrect
            upd = records.parse_utc_sql(r["updated_at"])
            stype = records.alnum(r["session_type"])
            if stype == "subagent":
                if r["parent_session_id"] and sessions.is_fresh(
                    config, now, upd, config.working_threshold_sec
                ):
                    children.setdefault(r["parent_session_id"], []).append(
                        ((r["description"] or "subagent")[:70], upd)
                    )
                continue
            if stype in ("hidden", "terminal", "gateway", "acp"):
                continue  # infrastructure sessions goose's own list hides
            tops.append((r, upd))

        out: list[dict[str, Any]] = []
        for r, upd in tops:
            agents = sorted(children.get(r["id"], []), key=lambda a: -a[1])
            activity_sources = (upd, *(m for _, m in agents))
            last_activity = sessions.newest_plausible(config, now, activity_sources)
            active = sessions.is_fresh(config, now, last_activity, window_hours * 3600)
            if not (active or show_all):
                continue
            # `model` is always present on a subagent element, per the contract
            # in `sessions.base_session`. None here says nobody has looked for
            # where Goose records the model, not that Goose runs on none.
            subagents = [{"name": label, "model": None, "started_at": None} for label, _ in agents]
            session_state, state_detail = "idle", "awaiting your message"
            if sessions.is_fresh(config, now, last_activity, config.working_threshold_sec):
                session_state = "working"
                state_detail = sessions.working_detail(None, subagents)

            turn = None
            last_prompt = ""
            rate = 0
            if active:
                events = []
                try:
                    msgs = con.execute(
                        "SELECT role, created_timestamp, content_json FROM messages "
                        "WHERE session_id = ? ORDER BY created_timestamp DESC LIMIT ?",
                        (r["id"], config.sql_message_limit),
                    ).fetchall()
                    for m in reversed(msgs):
                        ep = records.norm_epoch(m["created_timestamp"])
                        try:
                            content = json.loads(m["content_json"] or "[]")
                        except (ValueError, TypeError, RecursionError):
                            content = []
                        is_prompt = m["role"] == "user" and _user_prompt(content)
                        events.append((ep, is_prompt))
                        if is_prompt:
                            last_prompt = records.extract_text(content) or last_prompt
                except runtime_io.sqlite_module.Error:
                    pass
                try:
                    # Token accounting lives in usage_ledger, NOT messages.tokens
                    # (goose never writes that column).
                    led = con.execute(
                        "SELECT created_timestamp, output_tokens FROM usage_ledger "
                        "WHERE session_id = ? ORDER BY created_timestamp DESC LIMIT 200",
                        (r["id"],),
                    ).fetchall()
                    recent = sum(
                        (x["output_tokens"] or 0)
                        for x in led
                        if sessions.is_fresh(
                            config,
                            now,
                            records.norm_epoch(x["created_timestamp"]),
                            config.rate_window_sec,
                        )
                    )
                    rate = round(recent / (config.rate_window_sec / 60))
                except runtime_io.sqlite_module.Error:
                    pass
                turn = turns.turn_progress(
                    turns.turns_from_events(events), session_state, now, config
                )

            s = sessions.base_session(
                "goose",
                r["id"],
                sessions.project_from_cwd(config, r["working_dir"] or "") or "goose",
            )
            s.update(
                {
                    "title": records.redact_clip(
                        (r["description"] or "").strip(), records.PROMPT_TITLE_CAP_CHARS
                    )
                    or None,
                    # Redacted here rather than where it is assigned, which is
                    # inside the message loop: the filter belongs on what is
                    # published, once, not on every prompt the loop walks past.
                    "last_prompt": records.redact_clip(last_prompt, records.LAST_PROMPT_CAP_CHARS),
                    "state": session_state,
                    "state_detail": state_detail,
                    "active": active,
                    "last_activity": last_activity,
                    "rate_per_min": rate,
                    "turn": turn,
                    "subagents": subagents,
                }
            )
            out.append(s)
    except runtime_io.sqlite_module.Error as exc:
        runtime_io.record_store_error(state, goose_db, exc)
        return []
    else:
        return out
    finally:
        con.close()
