"""Harness registry, per-harness failure boundary, collection, and the application."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias

from . import io as runtime_io
from . import quota, sessions

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
UsageProvider: TypeAlias = Callable[
    ["RuntimeConfig", "RuntimeState", float, float],
    "list[dict[str, Any]]",
]


@dataclass(frozen=True)
class HarnessSpec:
    """One supported harness: how to discover its store and how to read it.

    ``usage`` is the optional quota reader. Most harnesses have none: the
    survey behind DEC-1 found Codex alone writing quota to disk, and every
    other vendor keeping it behind an authenticated API. The field is where
    a quota source plugs in without widening the ``Collector`` contract.

    ``usage_is_fetch`` marks a provider whose numbers come from the network
    fetcher rather than from disk. Its presence on a discovered harness is
    what raises the payload's ``usage_fetch`` capability flag, and that flag
    is what wakes the page's first-run disclosure modal — a disk reader like
    Codex's must never raise it.
    """

    key: str
    label: str
    discover: Discoverer
    collect: Collector
    usage: UsageProvider | None = None
    usage_is_fetch: bool = False


def default_harnesses(
    popup_notifier: Callable[[str, str], None],
    *,
    usage_fetch_enabled: bool = True,
) -> tuple[HarnessSpec, ...]:
    """Every supported harness, in display order.

    Claude is the one collector that notifies during collection, because a
    transcript-detected transition into needs-input has no HTTP request behind
    it. Binding its notifier here keeps ``Collector`` a single five-argument
    contract for all ten harnesses instead of widening every collector with a
    dependency only one of them has. Pass the same bound callable given to
    ``Application.popup_notifier`` so both paths notify identically.

    ``usage_fetch_enabled`` is ``--no-usage`` arriving at assembly: with the
    fetch off, the Claude row gets no usage provider at all, so nothing ever
    reads the fetch cache and the ``usage_fetch`` flag can never rise.
    """
    from .collectors import (  # noqa: PLC0415 — deferred to keep import order acyclic
        antigravity,
        claude,
        codex,
        copilot,
        cursor,
        droid,
        gemini,
        goose,
        opencode,
        pi,
    )

    def collect_claude(
        config: RuntimeConfig,
        state: RuntimeState,
        now: float,
        window_hours: float,
        show_all: bool,
    ) -> list[Session]:
        return claude.collect(
            config, state, now, window_hours, show_all, popup_notifier=popup_notifier
        )

    return (
        HarnessSpec(
            "claude",
            "Claude",
            claude.discover,
            collect_claude,
            usage=claude.usage if usage_fetch_enabled else None,
            usage_is_fetch=True,
        ),
        HarnessSpec("codex", "Codex", codex.discover, codex.collect, usage=codex.usage),
        HarnessSpec("pi", "Pi", pi.discover, pi.collect),
        # Gemini CLI was retired on 2026-06-18 and Antigravity replaced it.
        # They shared this row while both were Google's current surface; the
        # legacy row stays so a machine that ran Gemini CLI keeps its history.
        HarnessSpec("gemini", "Gemini", gemini.discover, gemini.collect),
        HarnessSpec("antigravity", "Antigravity", antigravity.discover, antigravity.collect),
        HarnessSpec("copilot", "Copilot", copilot.discover, copilot.collect),
        HarnessSpec("opencode", "OpenCode", opencode.discover, opencode.collect),
        HarnessSpec("cursor", "Cursor", cursor.discover, cursor.collect),
        HarnessSpec("goose", "Goose", goose.discover, goose.collect),
        HarnessSpec("droid", "Droid", droid.discover, droid.collect),
    )


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
        usage: list[dict[str, Any]] = []
        usage_supported = False
        usage_fetch_active = False
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
            if spec.usage is None:
                continue
            # The `usage` key exists exactly when a discovered harness can
            # publish quota; the page keeps its band hidden otherwise. A
            # failed quota read is a diagnostic, never a harness error — the
            # session rows above already collected, and a broken tile must
            # not repaint the whole strip red.
            usage_supported = True
            usage_fetch_active = usage_fetch_active or spec.usage_is_fetch
            try:
                usage.extend(spec.usage(config, state, now, window_hours))
            except Exception as e:  # noqa: BLE001 — same boundary as the collector above
                runtime_io.diag(
                    f"[{spec.key}] usage error: {type(e).__name__}: {e}",
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
        collection: Collection = {
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
        if usage_supported:
            # Present even when empty: the page distinguishes "no quota data
            # yet" (key with no entries) from "nothing here publishes quota"
            # (no key), and only the former draws the band.
            collection["usage"] = sorted(usage, key=lambda u: str(u.get("harness", "")))
        if usage_fetch_active:
            # The fetcher's capability flag: present exactly when a discovered
            # harness's quota comes from the network fetcher. The page's
            # first-run disclosure modal keys on it, so it must never rise for
            # a disk-read provider or with the fetch disabled.
            collection["usage_fetch"] = True
        return collection

    def request_usage_fetch(self) -> bool:
        """Maybe start a background quota fetch; the gates live in `quota`.

        Called only from `/api/data` handling for requests that carry the
        page's consent — never from `collect`, which `--diagnose` also runs
        and which must stay free of network side effects.
        """
        return quota.request_fetch(
            self.config,
            self.state,
            clock=self.clock,
            diagnostic_sink=self.diagnostic_sink,
        )

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
