"""Mutable process state owned by one Cargento runtime."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

from cargento_runtime import asks as runtime_asks
from cargento_runtime import snapshot as runtime_snapshot
from cargento_runtime import stream as runtime_stream

if TYPE_CHECKING:
    from _thread import LockType

    from cargento_runtime.config import RuntimeConfig


class UsageFetchEntry(TypedDict):
    ts: float
    entries: list[dict[str, Any]]


@dataclass
class RuntimeState:
    config: RuntimeConfig
    server_started: float
    # The published responses live here rather than on the Application, exactly
    # where the memo they replace lived. Two applications over one state must
    # share one scan: that single-flight property is what stops concurrent tabs
    # stampeding a cold entry, and it is a property of the runtime, not of the
    # object that happens to serve a request.
    snapshot: runtime_snapshot.Snapshot = field(init=False)
    # Connected SSE clients, owned here for the same reason the snapshot is:
    # they belong to the runtime, not to whichever object serves a request.
    streams: runtime_stream.StreamRegistry = field(init=False)
    # Outstanding questions a session asked, owned here for the reason the
    # streams are: they belong to the runtime, not to whichever object serves a
    # request. No `ask_lock` beside this one -- the registry owns its own, and a
    # second lock at this level would only invite a caller to hold the wrong one.
    asks: runtime_asks.AskRegistry = field(init=False)
    hook_lock: LockType = field(default_factory=threading.Lock)
    cache_lock: LockType = field(default_factory=threading.Lock)
    scanner_lock: LockType = field(default_factory=threading.Lock)
    # Named for the memo it used to guard, and still doing that memo's real job:
    # held across collection so concurrent readers share one filesystem and
    # SQLite scan. The published bytes moved to `snapshot`, which has its own
    # lock and never holds it across a collection or a socket write.
    collect_memo_lock: LockType = field(default_factory=threading.Lock)
    hook_notifications: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_popup: dict[str, float] = field(default_factory=dict)
    last_popup_message: dict[str, tuple[str, float]] = field(default_factory=dict)
    last_session_state: dict[str, str] = field(default_factory=dict)
    hook_generation: dict[str, int] = field(default_factory=dict)
    store_errors: dict[str, str] = field(default_factory=dict)
    metadata_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    claude_title_cache: dict[str, tuple[int, int, str | None]] = field(default_factory=dict)
    claude_user_event_cache: dict[str, tuple[int, int, str | None]] = field(default_factory=dict)
    # sess_dir -> (directory mtimes, subagent transcript paths). A subagent tree
    # whose directory mtimes have not moved cannot have gained or lost a
    # transcript, so only the glob is memoised; mtimes are restated on every
    # read because appending to a transcript moves no directory. Keying on
    # directory mtimes rather than on a freshness window keeps a parked
    # parent's subagents visible.
    claude_subagent_cache: dict[str, tuple[tuple[float, ...], list[str]]] = field(
        default_factory=dict
    )
    cwd_cache: dict[str, str] = field(default_factory=dict)
    pi_scan: dict[str, dict[str, Any]] = field(default_factory=dict)
    turn_scan: dict[str, Any] = field(default_factory=dict)
    agent_class_cache: dict[str, tuple[bool, str, str]] = field(default_factory=dict)
    spacedock_role_cache: dict[str, str] = field(default_factory=dict)
    spacedock_boot_cache: dict[tuple[str, int], list[dict[str, Any]]] = field(default_factory=dict)
    spacedock_workflow_cache: dict[tuple[str, int, int], dict[str, Any] | None] = field(
        default_factory=dict
    )
    spacedock_entity_cache: dict[tuple[str, int, int], str] = field(default_factory=dict)
    cursor_metadata_cache: dict[str, tuple[float, str | None, str]] = field(default_factory=dict)
    # The quota fetch. One cache entry per vendor key, stamped with the fetch
    # time so the five-minute floor is a comparison, and one in-flight marker
    # per vendor so a slow request cannot stack a second behind it. Guarded by
    # usage_fetch_lock, never cache_lock: the fetch thread holds its lock
    # across a cache write only, and must not contend with collectors.
    usage_fetch_lock: LockType = field(default_factory=threading.Lock)
    usage_fetch_cache: dict[str, UsageFetchEntry] = field(default_factory=dict)
    usage_fetch_inflight: set[str] = field(default_factory=set)
    # Receipts pushed in by a harness's own status-line command, keyed the same
    # way and guarded by the same lock: one cache, two ways to fill it. In
    # memory only, so Cargento's two written paths are unchanged.
    usage_receipts: dict[str, UsageFetchEntry] = field(default_factory=dict)
    # State disputes: an overlay overruling a collector that had found a wait.
    # A running total that never resets, so a machine can report "this happened
    # 40 times" long after the ring has turned over, plus the ring itself. The
    # lock is its own for the reason `usage_fetch_lock` is: this is written
    # inside a collection and read by a request handler, and neither should wait
    # on the other's cache work.
    # The sessions the reader marked handled, as this process last read them off
    # disk. `None` means no collection has run yet, which is not the same claim
    # as "nothing is cleared": the notification path can fire first, and an empty
    # tuple there would raise a popup for a session already handled.
    #
    # Its own lock, for the reason `dispute_lock` has one: it is written by a
    # request handler and read inside a collection, and neither should wait on the
    # other's cache work. The file, not this tuple, is the record — a second
    # dashboard's write is picked up by the next `dismissals.refresh`.
    dismissal_lock: LockType = field(default_factory=threading.Lock)
    dismissals: tuple[dict[str, Any], ...] | None = None
    dispute_lock: LockType = field(default_factory=threading.Lock)
    dispute_total: int = 0
    disputes: deque[dict[str, Any]] = field(default_factory=deque)
    # The open episode per session: its shape, and the record to update in place
    # while it lasts. Without this a standing disagreement writes one record per
    # collection, so a single 90-second one fills the ring and `dispute_total`
    # counts polls rather than faults.
    dispute_episodes: dict[tuple[str, str], tuple[tuple[str, str, int], dict[str, Any]]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        # Built here rather than by a default_factory because they need fields of
        # this same dataclass: the snapshot needs `server_started`, and the
        # dispute ring needs its bound from `config`.
        self.snapshot = runtime_snapshot.Snapshot(server_started=self.server_started)
        self.streams = runtime_stream.StreamRegistry()
        self.asks = runtime_asks.AskRegistry()
        self.disputes = deque(self.disputes, maxlen=self.config.dispute_log_max)


def build_runtime_state(config: RuntimeConfig, *, started: float) -> RuntimeState:
    return RuntimeState(config=config, server_started=started)


def bounded_put(
    cache: dict[Any, Any],
    key: Any,
    value: Any,
    *,
    limit: int,
) -> None:
    if key not in cache and len(cache) >= limit:
        cache.pop(next(iter(cache)))
    cache[key] = value
