"""Mutable process state owned by one Cargento runtime."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from _thread import LockType

    from cargento_runtime.config import RuntimeConfig


class CollectMemoEntry(TypedDict):
    ts: float
    body: bytes


class UsageFetchEntry(TypedDict):
    ts: float
    entries: list[dict[str, Any]]


@dataclass
class RuntimeState:
    config: RuntimeConfig
    server_started: float
    hook_lock: LockType = field(default_factory=threading.Lock)
    cache_lock: LockType = field(default_factory=threading.Lock)
    scanner_lock: LockType = field(default_factory=threading.Lock)
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
    collect_memo: dict[tuple[float, bool], CollectMemoEntry] = field(default_factory=dict)
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
