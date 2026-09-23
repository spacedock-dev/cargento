"""Remembered reading permission and durable, atomic rolling spend admission.

The transaction is the bound on concurrent tabs and daemons, not the browser's
button state. No session identities or content enter this store.
See [DEC-21](docs/design-reading-a-session.md#dec-21-a-reading-works-the-first-time-you-ask).
"""

from __future__ import annotations

import contextlib
import math
import os
import time
from typing import TYPE_CHECKING, Any, TypedDict

from . import io as runtime_io

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from .config import RuntimeConfig

DAY_SEC = 86_400.0
DAILY_CAP = 12
_SQL_ERROR = getattr(runtime_io.sqlite_module, "Error", RuntimeError)


class Status(TypedDict):
    consent: bool
    used: int
    limit: int
    retry_at: float | None
    reason: str


def store_path(config: RuntimeConfig) -> Path:
    return config.state_dir / "cargento-reading-permission.sqlite3"


def _answer(consent: bool = False, dates: tuple[float, ...] = (), reason: str = "") -> Status:
    full = len(dates) >= DAILY_CAP
    return {
        "consent": consent,
        "used": len(dates),
        "limit": DAILY_CAP,
        "retry_at": min(dates) + DAY_SEC if full else None,
        "reason": reason or ("consent-required" if not consent else "daily-cap" if full else ""),
    }


def _connect(config: RuntimeConfig) -> Any:
    if runtime_io.sqlite_module is None:
        raise RuntimeError("SQLite is unavailable")
    path = store_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("Permission store is a symlink")
    # SQLite inherits this owner-only mode for its rollback journal too.
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    return runtime_io.sqlite_module.connect(path, timeout=2.0, isolation_level=None)


def _transaction(config: RuntimeConfig, now: float, operation: str) -> Status:
    if not math.isfinite(now) or now <= 0:
        return _answer(reason="store-unavailable")
    with contextlib.closing(_connect(config)) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "CREATE TABLE IF NOT EXISTS permission (id INTEGER PRIMARY KEY CHECK(id=1), "
            "allowed INTEGER NOT NULL CHECK(allowed IN (0,1)))"
        )
        db.execute("CREATE TABLE IF NOT EXISTS spends (at REAL NOT NULL)")
        row = db.execute("SELECT allowed FROM permission WHERE id=1").fetchone()
        consent = row is not None and row[0] == 1
        db.execute("DELETE FROM spends WHERE at <= ?", (now - DAY_SEC,))
        dates = tuple(float(row[0]) for row in db.execute("SELECT at FROM spends ORDER BY at"))
        if any(not math.isfinite(at) or at <= 0 for at in dates):
            raise ValueError("Invalid spend timestamp")
        if operation in {"allow", "off"}:
            consent = operation == "allow"
            db.execute("INSERT OR REPLACE INTO permission VALUES (1, ?)", (int(consent),))
        answer = _answer(consent, dates)
        if operation == "reserve" and not answer["reason"]:
            db.execute("INSERT INTO spends VALUES (?)", (now,))
            answer = {**answer, "used": len(dates) + 1}
        db.execute("COMMIT")
        return answer


def _run(config: RuntimeConfig, now: float, operation: str) -> Status:
    try:
        return _transaction(config, now, operation)
    except (OSError, ValueError, RuntimeError, _SQL_ERROR):
        return _answer(reason="store-unavailable")


def status(config: RuntimeConfig, *, now: float) -> Status:
    if config.model_calls_disabled:
        return _answer(reason="run-disabled")
    if not store_path(config).exists():
        return _answer()
    return _run(config, now, "read")


def set_consent(config: RuntimeConfig, allowed: bool, *, now: float) -> Status:
    return _run(config, now, "allow" if allowed else "off")


def reserve(config: RuntimeConfig, *, now: float) -> Status:
    """Commit a charge before launch; uncertainty about spend never refunds it."""
    return status(config, now=now) if config.model_calls_disabled else _run(config, now, "reserve")


class RefusedError(Exception):
    def __init__(self, answer: Status) -> None:
        super().__init__(answer["reason"])
        self.answer = answer


class GuardedModel:
    """Reserve at the actual model seam, after eligibility and evidence checks."""

    def __init__(
        self,
        config: RuntimeConfig,
        model: Callable[..., tuple[str, str]],
        clock: Callable[[], float],
    ) -> None:
        self.config = config
        self.model = model
        self.clock = clock

    def __call__(self, prompt: str, *, output_cap_bytes: int) -> tuple[str, str]:
        answer = reserve(self.config, now=self.clock())
        if answer["reason"]:
            raise RefusedError(answer)
        return self.model(prompt, output_cap_bytes=output_cap_bytes)


def forget(config: RuntimeConfig, *, now: float | None = None) -> bool:
    # Forgetting the answer cannot refill a rolling budget. No session content
    # is retained here, only the timestamps protecting the spend bound.
    return (
        set_consent(config, False, now=time.time() if now is None else now)["reason"]
        != "store-unavailable"
    )
