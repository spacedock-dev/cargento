"""GitHub Copilot CLI collection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

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
    which would drift with how much history happens to be retained.
    """
    if not runtime_io.sqlite_available():
        return []
    root = runtime_config.primary_store(config, "copilot.root")
    database = os.path.join(root, "session-store.db")
    if not os.path.isfile(database):
        return []
    try:
        connection = runtime_io.open_sqlite_read_only(database, state)
    except Exception:  # noqa: BLE001 — a broken store must not fail the harness
        return []
    try:
        rows = connection.execute(
            "SELECT total_nano_aiu, created_at FROM assistant_usage_events "
            "ORDER BY id DESC LIMIT ?",
            (_USAGE_ROW_CAP,),
        ).fetchall()
    except Exception:  # noqa: BLE001 — schema drift is a miss, never an error
        runtime_io.record_store_error(state, database, RuntimeError("no assistant_usage_events"))
        return []
    finally:
        connection.close()

    window_sec = window_hours * 3600
    nano = 0
    newest = 0.0
    for row in rows:
        stamp = records.parse_utc_sql(row["created_at"])
        if not stamp or not sessions.is_fresh(config, now, stamp, window_sec):
            continue
        amount = row["total_nano_aiu"]
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
            continue
        nano += int(amount)
        newest = max(newest, stamp)
    if not newest:
        return []
    return [
        {
            "harness": "copilot",
            "state": "ok",
            "asOf": int(newest),
            "used": f"{nano / _NANO_PER_AIU:.2f} AIU",
        }
    ]


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

    out: list[Session] = []
    for sid, (mtime, fp) in files.items():
        active = sessions.is_fresh(config, now, mtime, window_hours * 3600)
        if not (active or show_all):
            continue
        info = transcripts.analyze_copilot_events(config, fp) if active else None
        last_event_sources = (info["last_event_ts"] if info else 0, mtime)
        session_state, state_detail = "idle", "awaiting your message"
        subagents: list[str] = []
        if sessions.is_fresh(
            config,
            now,
            sessions.newest_plausible(config, now, last_event_sources),
            config.working_threshold_sec,
        ):
            session_state = "working"
            subagents = list((info or {}).get("pending_agents", {}).values())
            state_detail = sessions.working_detail(info, subagents)

        cwd = (info or {}).get("cwd") or transcripts.copilot_meta(config, state, fp).get("cwd")
        s = sessions.base_session(
            "copilot", sid, sessions.project_from_cwd(config, cwd or "") or "copilot"
        )
        s.update(
            {
                "title": (info or {}).get("title"),
                "last_prompt": ((info or {}).get("last_prompt") or "")[:140],
                "state": session_state,
                "state_detail": state_detail,
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
