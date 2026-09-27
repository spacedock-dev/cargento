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
from . import supervise

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from .config import RuntimeConfig

DAY_SEC = 86_400.0
DAILY_CAP = 12
# How long the job ledger keeps the id each charge was made for (DRC-4713).
# Far past `DAY_SEC`, because the budget reads only `spends`: a restart more
# than a day after a crash must still find the row, or it would call a charged
# attempt uncharged. A marker older than this is answered "cannot say".
JOB_LEDGER_SEC = 30 * DAY_SEC
# One answer per receiver (DRC-4650): allowing Codex to send a reader's words
# to OpenAI is not allowing Claude Code to send them to Anthropic. Codex keeps
# the original single-row table, so an answer saved before there were two
# providers reads as the Codex answer it was, and an older build reading this
# store still sees it. Every other provider has a row in its own table.
PROVIDERS = ("codex", "claude")
LEGACY_PROVIDER = "codex"
_SQL_ERROR = getattr(runtime_io.sqlite_module, "Error", RuntimeError)
# How long a write waits behind other processes' writes before it is refused
# as store-unavailable. Every write holds the lock for one short transaction,
# so the wait is the length of the queue, and a slow disk lengthens every place
# in it. At 2 s, three of 24 reservations from four processes were refused on a
# Windows runner while under the cap (DRC-4707), and a reader sees that as a
# refused Analyze. A read for the board keeps the short wait, so a collect does
# not stall behind a queue of presses.
WRITE_WAIT_SEC = 10.0
READ_WAIT_SEC = 2.0


class Status(TypedDict):
    consent: bool
    used: int
    limit: int
    retry_at: float | None
    reason: str
    # Which receivers the reader has allowed, so the page can tell whether the
    # provider its route names still needs an Allow. `consent` answers for the
    # one provider the call asked about.
    providers: dict[str, bool]
    # The tool-output grants, provider to the destinations the reader allowed
    # it to reach, item 7 of the ruling `reading.build_ledger` cites.
    # Its own table: no answer in the two above is
    # ever read as one, so an Allow given before tool output was named cannot
    # cover it, and a destination that moves is asked about again.
    tool_output: dict[str, list[str]]


def store_path(config: RuntimeConfig) -> Path:
    return config.state_dir / "cargento-reading-permission.sqlite3"


def _answer(
    consent: bool = False,
    dates: tuple[float, ...] = (),
    reason: str = "",
    providers: dict[str, bool] | None = None,
    tool_output: dict[str, list[str]] | None = None,
) -> Status:
    full = len(dates) >= DAILY_CAP
    return {
        "consent": consent,
        "used": len(dates),
        "limit": DAILY_CAP,
        "retry_at": min(dates) + DAY_SEC if full else None,
        # The cap first: the budget is shared, so a spent day refuses every
        # provider, and the page reads the Codex answer. Consent first told a
        # reader with only Claude Code allowed that nothing stood in the way
        # (DRC-4666).
        "reason": reason or ("daily-cap" if full else "consent-required" if not consent else ""),
        "providers": dict(providers) if providers else dict.fromkeys(PROVIDERS, False),
        "tool_output": {name: list(where) for name, where in (tool_output or {}).items()},
    }


def tool_output_allowed(answer: Status, provider: str, destination: str) -> bool:
    """Whether this answer holds a grant for exactly this provider and destination."""
    return bool(destination) and destination in answer.get("tool_output", {}).get(provider, [])


def _connect(config: RuntimeConfig, wait: float) -> Any:
    if runtime_io.sqlite_module is None:
        raise RuntimeError("SQLite is unavailable")
    path = store_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("Permission store is a symlink")
    # SQLite inherits this owner-only mode for its rollback journal too.
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    return runtime_io.sqlite_module.connect(path, timeout=wait, isolation_level=None)


def _allowed(db: Any) -> dict[str, bool]:
    row = db.execute("SELECT allowed FROM permission WHERE id=1").fetchone()
    allowed = dict.fromkeys(PROVIDERS, False)
    allowed[LEGACY_PROVIDER] = row is not None and row[0] == 1
    for name, value in db.execute("SELECT provider, allowed FROM provider_permission"):
        if name in allowed and name != LEGACY_PROVIDER:
            allowed[name] = value == 1
    return allowed


def _tool_output(db: Any) -> dict[str, list[str]]:
    granted: dict[str, list[str]] = {}
    for name, where in db.execute(
        "SELECT provider, destination FROM tool_output_permission ORDER BY provider, destination"
    ):
        if name in PROVIDERS and isinstance(where, str) and where:
            granted.setdefault(name, []).append(where)
    return granted


def _write(db: Any, provider: str, allowed: bool) -> None:
    if provider == LEGACY_PROVIDER:
        db.execute("INSERT OR REPLACE INTO permission VALUES (1, ?)", (int(allowed),))
    else:
        db.execute(
            "INSERT OR REPLACE INTO provider_permission VALUES (?, ?)", (provider, int(allowed))
        )


def _transaction(
    config: RuntimeConfig,
    now: float,
    operation: str,
    provider: str,
    tool_output: str = "",
    job_id: str = "",
) -> Status:
    if not math.isfinite(now) or now <= 0:
        return _answer(reason="store-unavailable")
    wait = READ_WAIT_SEC if operation == "read" else WRITE_WAIT_SEC
    with contextlib.closing(_connect(config, wait)) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "CREATE TABLE IF NOT EXISTS permission (id INTEGER PRIMARY KEY CHECK(id=1), "
            "allowed INTEGER NOT NULL CHECK(allowed IN (0,1)))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS provider_permission (provider TEXT PRIMARY KEY, "
            "allowed INTEGER NOT NULL CHECK(allowed IN (0,1)))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS tool_output_permission (provider TEXT NOT NULL, "
            "destination TEXT NOT NULL, PRIMARY KEY (provider, destination))"
        )
        db.execute("CREATE TABLE IF NOT EXISTS spends (at REAL NOT NULL)")
        # A table of its own rather than a column on `spends`: an older build's
        # `INSERT INTO spends VALUES (?)` fails against a second column, and a
        # rollback would then refuse every press as store-unavailable.
        db.execute("CREATE TABLE IF NOT EXISTS spend_jobs (job TEXT PRIMARY KEY, at REAL NOT NULL)")
        # How far back an absent row still means "no charge": from the
        # ledger's creation, raised on every prune. Without it, a row pruned
        # under a clock that ran ahead, or a store deleted and made again,
        # read as "never charged" for a job that was (review F2).
        db.execute(
            "CREATE TABLE IF NOT EXISTS spend_jobs_since "
            "(id INTEGER PRIMARY KEY CHECK(id=1), at REAL NOT NULL)"
        )
        db.execute("INSERT OR IGNORE INTO spend_jobs_since VALUES (1, ?)", (now,))
        # Schema, so it fires inside a pre-DRC-4650 build's own write: that
        # build's Turn off and `--forget` touch only the legacy row, and without
        # this the Claude Code answer survived a rollback (DRC-4666).
        for event in ("INSERT", "UPDATE"):
            db.execute(
                f"CREATE TRIGGER IF NOT EXISTS permission_off_{event.lower()} "  # noqa: S608 - two fixed words
                f"AFTER {event} ON permission WHEN NEW.allowed = 0 BEGIN "
                "UPDATE provider_permission SET allowed = 0; "
                "DELETE FROM tool_output_permission; END"
            )
        allowed = _allowed(db)
        db.execute("DELETE FROM spends WHERE at <= ?", (now - DAY_SEC,))
        db.execute("DELETE FROM spend_jobs WHERE at <= ?", (now - JOB_LEDGER_SEC,))
        db.execute(
            "UPDATE spend_jobs_since SET at = max(at, ?) WHERE id = 1", (now - JOB_LEDGER_SEC,)
        )
        dates = tuple(float(row[0]) for row in db.execute("SELECT at FROM spends ORDER BY at"))
        if any(not math.isfinite(at) or at <= 0 for at in dates):
            raise ValueError("Invalid spend timestamp")
        if operation == "allow" and provider in allowed:
            _write(db, provider, True)
            allowed[provider] = True
            if tool_output:
                db.execute(
                    "INSERT OR IGNORE INTO tool_output_permission VALUES (?, ?)",
                    (provider, tool_output),
                )
        elif operation == "off":
            # Every receiver at once: "Turn off readings" and `--forget` name
            # no provider, and a revocation that left one allowed would not be
            # the answer the reader gave.
            for name in PROVIDERS:
                _write(db, name, False)
            allowed = dict.fromkeys(PROVIDERS, False)
            db.execute("DELETE FROM tool_output_permission")
        answer = _answer(
            allowed.get(provider, False), dates, providers=allowed, tool_output=_tool_output(db)
        )
        if operation == "reserve" and not answer["reason"]:
            return _commit_charge(db, answer, now, job_id)
        db.execute("COMMIT")
        return answer


def _commit_charge(db: Any, answer: Status, now: float, job_id: str) -> Status:
    """Insert the charge and its job, and commit, unless the runner has shut.

    Under the lock a shutdown takes (DRC-4712). The wait for SQLite's write
    lock is already behind this, so `kill_all` waits one commit at most, and
    it never touches SQLite, so the two locks cannot be taken in both orders.
    """
    with supervise.admitting() as open_:
        if not open_:
            db.execute("ROLLBACK")
            return {**answer, "reason": "stopping"}
        db.execute("INSERT INTO spends VALUES (?)", (now,))
        if job_id:
            db.execute("INSERT OR IGNORE INTO spend_jobs VALUES (?, ?)", (job_id, now))
        db.execute("COMMIT")
    return {**answer, "used": answer["used"] + 1}


def _run(
    config: RuntimeConfig,
    now: float,
    operation: str,
    provider: str,
    tool_output: str = "",
    job_id: str = "",
) -> Status:
    try:
        return _transaction(config, now, operation, provider, tool_output, job_id)
    except (OSError, ValueError, RuntimeError, _SQL_ERROR):
        return _answer(reason="store-unavailable")


def status(config: RuntimeConfig, *, now: float, provider: str = LEGACY_PROVIDER) -> Status:
    if config.model_calls_disabled:
        return _answer(reason="run-disabled")
    if not store_path(config).exists():
        return _answer()
    return _run(config, now, "read", provider)


def set_consent(
    config: RuntimeConfig,
    allowed: bool,
    *,
    now: float,
    provider: str = LEGACY_PROVIDER,
    tool_output: str = "",
) -> Status:
    """Allow one provider, or revoke every provider: off never names one.

    `tool_output` is the destination the press's disclosure named. Only an
    Allow that carried one grants tool output, and only to that destination.
    """
    return _run(config, now, "allow" if allowed else "off", provider, tool_output)


def reserve(
    config: RuntimeConfig, *, now: float, provider: str = LEGACY_PROVIDER, job_id: str = ""
) -> Status:
    """Commit a charge before launch; uncertainty about spend never refunds it.

    One rolling budget whichever provider is admitted: two providers must not
    be a way to double a reader's daily readings. `job_id` commits with the
    charge, so a restart can ask `charged` whether that job's attempt was made.
    A shutdown before the commit answers `stopping` and charges nothing.
    """
    if config.model_calls_disabled:
        return status(config, now=now, provider=provider)
    return _run(config, now, "reserve", provider, job_id=job_id)


def charged(config: RuntimeConfig, job_id: str, *, started_at: Any, now: float) -> bool | None:
    """Whether the ledger holds a charge for this job, or None when it cannot say.

    A row is a charge whenever it was made. No row means no charge only for a
    job that started after the ledger's watermark: None for a start at or
    before it, older than the ledger keeps, or not a positive number, and for
    no id or a store that is missing, unreadable or older than the ledger. A
    caller counts None as spent: dropping a charged attempt silently is the
    loss DRC-4686 Q2 ruled out. Reads only; creates nothing.
    """
    if not job_id or runtime_io.sqlite_module is None:
        return None
    path = store_path(config)
    try:
        if path.is_symlink() or not path.is_file():
            return None
        with contextlib.closing(
            runtime_io.sqlite_module.connect(path, timeout=READ_WAIT_SEC, isolation_level=None)
        ) as db:
            row = db.execute("SELECT 1 FROM spend_jobs WHERE job = ?", (job_id,)).fetchone()
            since = db.execute("SELECT at FROM spend_jobs_since WHERE id = 1").fetchone()
    except (OSError, ValueError, RuntimeError, _SQL_ERROR):
        return None
    if row is not None:
        return True
    # A watermark that is not a finite number is damage, and damage cannot
    # vouch for an absent row. Raising here once let recovery delete the
    # marker and record nothing (verify N1).
    watermark = since[0] if since is not None else None
    if (
        not isinstance(watermark, (int, float))
        or not math.isfinite(watermark)
        or not isinstance(started_at, (int, float))
        or not math.isfinite(started_at)
        or started_at <= max(float(watermark), now - JOB_LEDGER_SEC, 0.0)
    ):
        return None
    return False


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
        *,
        provider: str = LEGACY_PROVIDER,
        on_reserved: Callable[[], None] | None = None,
        before_reserve: Callable[[], str | None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self.config = config
        self.model = model
        self.clock = clock
        self.provider = provider
        # A reading job is told the spend is committed (DRC-4686).
        self.on_reserved = on_reserved
        # And its marker before the reservation: a hook that raises here
        # stops the call with nothing spent. What it returns is the job id the
        # charge is recorded under, so the marker and the ledger row it
        # promises come from one place (DRC-4713).
        self.before_reserve = before_reserve
        # A reader's Cancel, asked here so one that lands before the
        # reservation spends nothing (owner, 2026-09-24; see the Cancel
        # section of docs/design-reading-a-session.md).
        self.cancelled = cancelled
        # Passed through, so the refusal names the CLI this press would have used.
        self.unavailable_reason: str | None = getattr(model, "unavailable_reason", None)

    def __call__(self, prompt: str, *, output_cap_bytes: int) -> tuple[str, str]:
        available = getattr(self.model, "available", None)
        if available is not None and not available():
            return "", "unavailable"
        if supervise.closed():
            # Cargento is stopping and the call could never be sent, so it is
            # refused before the reservation rather than charged (verify N4).
            return "", "closed"
        if self.cancelled is not None and self.cancelled():
            return "", "cancelled"
        job_id = self.before_reserve() if self.before_reserve is not None else None
        answer = reserve(self.config, now=self.clock(), provider=self.provider, job_id=job_id or "")
        if answer["reason"] == "stopping":
            # The shutdown reached the reservation before its commit, so the
            # call is the stop the early look above would have refused.
            return "", "closed"
        if answer["reason"]:
            raise RefusedError(answer)
        if self.on_reserved is not None:
            self.on_reserved()
        return self.model(prompt, output_cap_bytes=output_cap_bytes)


def forget(config: RuntimeConfig, *, now: float | None = None) -> bool:
    # Forgetting the answer cannot refill a rolling budget. No session content
    # is retained here, only the timestamps protecting the spend bound.
    return (
        set_consent(config, False, now=time.time() if now is None else now)["reason"]
        != "store-unavailable"
    )
