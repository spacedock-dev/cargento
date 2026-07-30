"""Harness registry, per-harness failure boundary, collection, and the application."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias

from . import io as runtime_io
from . import sessions

if TYPE_CHECKING:
    from .config import RuntimeConfig
    from .sessions import Session
    from .state import RuntimeState

Collection: TypeAlias = dict[str, Any]
Discoverer: TypeAlias = Callable[["RuntimeConfig", "RuntimeState"], bool]
Collector: TypeAlias = Callable[
    ["RuntimeConfig", "RuntimeState", float, float, bool],
    "list[Session]",
]


@dataclass(frozen=True)
class HarnessSpec:
    """One supported harness: how to discover its store and how to read it."""

    key: str
    label: str
    discover: Discoverer
    collect: Collector


class Application:
    """One dashboard process's collection surface.

    Everything ambient is injected, so two applications can run in one
    interpreter without sharing configuration, caches, notifications or a clock.
    """

    def __init__(
        self,
        config: RuntimeConfig,
        state: RuntimeState,
        harnesses: tuple[HarnessSpec, ...],
        *,
        native_notifier: Callable[[str], str],
        popup_notifier: Callable[[str, str], None],
        diagnostic_sink: Callable[[str], None],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.state = state
        self.harnesses = harnesses
        self.native_notifier = native_notifier
        self.popup_notifier = popup_notifier
        self.diagnostic_sink = diagnostic_sink
        self.clock = clock

    def collect(self, *, show_all: bool) -> Collection:
        config, state = self.config, self.state
        window_hours = config.window_hours
        now = self.clock()
        out_sessions: list[Session] = []
        harnesses: list[dict[str, Any]] = []
        for spec in self.harnesses:
            try:
                found = bool(spec.discover(config, state))
            except OSError:
                found = False
            harness: dict[str, Any] = {
                "key": spec.key,
                "label": spec.label,
                "discovered": found,
                "error": None,
            }
            harnesses.append(harness)
            if not found:
                continue
            try:
                out_sessions.extend(spec.collect(config, state, now, window_hours, show_all))
            except Exception as e:  # noqa: BLE001 — one broken harness must not take down the rest
                harness["error"] = f"{type(e).__name__}: {e}"
                runtime_io.diag(
                    f"[{spec.key}] collector error: {harness['error']}",
                    self.diagnostic_sink,
                )

        out_sessions = sessions.dedupe_sessions(out_sessions)
        sessions.assign_display_ids(config, out_sessions)
        state_rank = {"needs_input": 0, "working": 1, "idle": 2}
        # Session id as tiebreaker (not last_activity) so rows don't reshuffle
        # on every refresh while sessions are generating.
        out_sessions.sort(key=lambda x: (state_rank.get(x["state"], 3), x["sid"]))
        active_sessions = [x for x in out_sessions if x["active"]]
        total_tasks = sum(x["total"] for x in out_sessions)
        total_done = sum(x["done"] for x in out_sessions)
        return {
            "generated": now,
            "window_hours": window_hours,
            "show_all": show_all,
            # Which layer owns needs-input popups. Empty means the page should
            # raise its own; a backend name means the server already did.
            "native_notify": self.native_notifier(config.platform_name),
            "harnesses": harnesses,
            "summary": {
                "needs_input": sum(1 for x in active_sessions if x["state"] == "needs_input"),
                "working": sum(1 for x in active_sessions if x["state"] == "working"),
                "rate_per_min": sum(x["rate_per_min"] for x in active_sessions),
                "active_sessions": len(active_sessions),
                "open_tasks": sum(x["open"] for x in out_sessions),
                "progress_pct": round(total_done * 100 / total_tasks) if total_tasks else 0,
                "total_tasks": total_tasks,
                "total_done": total_done,
            },
            "sessions": out_sessions,
        }

    def collect_json(self, *, show_all: bool) -> bytes:
        state = self.state
        key = (self.config.window_hours, show_all)
        with state.collect_memo_lock:
            cached = state.collect_memo.get(key)
            if cached and self.clock() - cached["ts"] < self.config.collect_memo_sec:
                body: bytes = cached["body"]
                return body
            # Hold the lock through collection: ThreadingHTTPServer callers share
            # one filesystem/SQLite scan rather than stampeding cold cache entries.
            body = json.dumps(self.collect(show_all=show_all)).encode()
            state.collect_memo[key] = {"ts": self.clock(), "body": body}
            return body
