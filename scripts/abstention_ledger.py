"""The one spend ledger for DRC-4666's qualification: every model call, charged first.

The owner authorized at most twenty real Claude Code readings for this
qualification (2026-09-24), and the browser walk that follows a pass is one of
them. So the scorer may make nineteen, across every run, every packet directory
and every producer, and this file is the only thing that counts them.

Four properties, each closing a bypass the review of 2026-09-24 reproduced:

- **One fixed path.** It never follows `CARGENTO_HOME`: a per-home ledger let a
  fresh, dated packet directory start again from zero. Nor does it follow
  `HOME`: the home is the account's own, from the password database, because
  `HOME=/tmp/x` gave a fresh ledger with the real CLI in verification (V1).
  Nothing reads an environment variable for it, because an override is the
  same bypass.
- **Fail closed.** A missing file is an empty ledger. A file that cannot be
  read, or reads as anything but this module's own shape, refuses every call:
  treating it as empty overwrote twenty charges with one.
- **Locked.** The cap check and the durable charge happen under an exclusive
  lock across processes, and every write goes through its own unique temporary
  file. Two unlocked runs made 24 calls against a cap of 20.
- **Bound to one packet.** Each charge records the digest of the marks and of
  the cases and rubric it was made under, and a charge under any other digest
  is refused. A mark rewritten after an output was seen is agreement, not a
  mark, and without this the re-score left no trace.

It holds case ids, times, statuses and digests. Never a session id, a prompt, a
check's output or anything a model said.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
import uuid
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


def real_home() -> str:
    """The account's home directory, which no environment variable can move.

    Windows has no password database; the scorer refuses to spend there
    rather than trust `USERPROFILE`, so its answer only has to be stable.
    """
    if sys.platform == "win32":
        return os.path.expanduser("~")
    import pwd  # noqa: PLC0415 - POSIX only

    return pwd.getpwuid(os.getuid()).pw_dir


def home_moved() -> bool:
    """Whether `HOME` names another directory than the account's own."""
    return os.path.realpath(os.path.expanduser("~")) != os.path.realpath(real_home())


# Under the account's ~/.cargento at a fixed name, never under CARGENTO_HOME or HOME.
LEDGER_PATH = os.path.join(real_home(), ".cargento", "drc-4666-spend.json")
# The committed result whose ledger chain freezes the key even if the ledger is deleted.
CLAUDE_SUMMARY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "abstention",
    "claude-results.json",
)
# Twenty authorized, one of them the AC2 browser walk the scorer cannot see.
MAX_CALLS = 19
STATUSES = ("charged", "ok", "failed", "unavailable")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CASE = re.compile(r"^[0-9a-f]{16}$")


class LedgerError(Exception):
    """The ledger refuses: unreadable, invalid, full, or another packet's."""


class SpendCapError(LedgerError):
    """The cap is reached. No further call may be made under this authorization."""


class OtherPacketError(LedgerError):
    """The ledger holds calls charged under other marks or other inputs."""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _empty() -> dict[str, Any]:
    return {"v": 1, "calls": [], "runs": []}


def _valid_call(call: Any) -> bool:
    return (
        isinstance(call, dict)
        and isinstance(call.get("id"), str)
        and bool(call["id"])
        and isinstance(call.get("case"), str)
        and bool(_CASE.fullmatch(call["case"]))
        and isinstance(call.get("producer"), str)
        and call.get("status") in STATUSES
        and all(
            isinstance(call.get(key), str) and bool(_DIGEST.fullmatch(call[key]))
            for key in ("marks_digest", "inputs_digest")
        )
        and isinstance(call.get("at"), (int, float))
        and not isinstance(call.get("at"), bool)
        and math.isfinite(call["at"])
    )


def _valid_run(run: Any) -> bool:
    return isinstance(run, dict) and all(
        isinstance(run.get(key), str) and bool(_DIGEST.fullmatch(run[key]))
        for key in ("records_digest", "marks_digest", "inputs_digest")
    )


def read(path: str) -> dict[str, Any]:
    """The ledger, or `LedgerError`. Only a file that does not exist reads as empty."""
    try:
        with open(path, encoding="utf-8") as handle:
            body = json.load(handle)
    except FileNotFoundError:
        return _empty()
    except (OSError, ValueError, RecursionError) as error:
        msg = f"the spend ledger at {path} cannot be read ({type(error).__name__})"
        raise LedgerError(msg) from error
    calls = body.get("calls") if isinstance(body, dict) else None
    runs = body.get("runs") if isinstance(body, dict) else None
    if (
        not isinstance(body, dict)
        or body.get("v") != 1
        or not isinstance(calls, list)
        or not isinstance(runs, list)
        or not all(_valid_call(call) for call in calls)
        or not all(_valid_run(run) for run in runs)
    ):
        msg = f"the spend ledger at {path} is not one this script wrote"
        raise LedgerError(msg)
    return body


def _lock_file(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt  # noqa: PLC0415 - Windows only

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl  # noqa: PLC0415 - POSIX only

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt  # noqa: PLC0415 - Windows only

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl  # noqa: PLC0415 - POSIX only

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def locked(path: str) -> Iterator[None]:
    """An exclusive lock on a sidecar file, held across processes."""
    os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
    with open(f"{path}.lock", "a+b") as handle:
        _lock_file(handle)
        try:
            yield
        finally:
            _unlock_file(handle)


def _write(path: str, body: Mapping[str, Any]) -> None:
    """Durably, through a temporary file no other writer shares."""
    folder = os.path.dirname(path) or "."
    descriptor, tmp = tempfile.mkstemp(prefix=".spend-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(body, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class Ledger:
    """The ledger as one packet sees it: its digests, and the cap it runs under."""

    def __init__(
        self, path: str, *, cap: int, marks_digest: str, inputs_digest: str, producer: str
    ) -> None:
        self.path = path
        self.cap = min(cap, MAX_CALLS)
        self.marks_digest = marks_digest
        self.inputs_digest = inputs_digest
        self.producer = producer

    def _refuse_other(self, body: Mapping[str, Any]) -> None:
        for call in body["calls"]:
            if (call["marks_digest"], call["inputs_digest"]) != (
                self.marks_digest,
                self.inputs_digest,
            ):
                msg = "the spend ledger holds calls charged under other marks or other cases"
                raise OtherPacketError(msg)

    def check(self) -> str:
        """Empty when this packet may be scored, else why not."""
        try:
            body = read(self.path)
            self._refuse_other(body)
        except LedgerError as error:
            return str(error)
        if len(body["calls"]) >= self.cap:
            return f"the spend ledger already holds {len(body['calls'])} of {self.cap} calls"
        return ""

    def used(self) -> int:
        return len(read(self.path)["calls"])

    def charge(self, case_id: str) -> str:
        """Charge one call before it runs, or raise. Returns the charge's id."""
        with locked(self.path):
            body = read(self.path)
            self._refuse_other(body)
            if len(body["calls"]) >= self.cap:
                raise SpendCapError
            charge_id = uuid.uuid4().hex
            body["calls"].append(
                {
                    "id": charge_id,
                    "at": time.time(),
                    "case": case_id,
                    "producer": self.producer,
                    "status": "charged",
                    "marks_digest": self.marks_digest,
                    "inputs_digest": self.inputs_digest,
                }
            )
            _write(self.path, body)
        return charge_id

    def settle(self, charge_id: str, status: str) -> None:
        """Record how a charged call ended, re-reading under the lock first."""
        with locked(self.path):
            body = read(self.path)
            for call in body["calls"]:
                if call["id"] == charge_id:
                    call["status"] = status if status in STATUSES else "failed"
            _write(self.path, body)

    def record_run(self, records_digest: str) -> None:
        """What a finished run wrote, so a resume can prove its records are that run's."""
        with locked(self.path):
            body = read(self.path)
            body["runs"].append(
                {
                    "at": time.time(),
                    "records_digest": records_digest,
                    "marks_digest": self.marks_digest,
                    "inputs_digest": self.inputs_digest,
                }
            )
            _write(self.path, body)

    def last_run(self) -> dict[str, Any] | None:
        runs = read(self.path)["runs"]
        return dict(runs[-1]) if runs else None


def chain(ids: Any) -> str:
    """A hash chain over charge ids in order: each link hashes the last with the next id."""
    link = hashlib.sha256(b"drc-4666").hexdigest()
    for charge_id in ids:
        link = hashlib.sha256(f"{link}:{charge_id}".encode()).hexdigest()
    return link


def chain_of(path: str) -> dict[str, Any]:
    """What a committed result records of the ledger: the first charge, the count, the head."""
    ids = [call["id"] for call in read(path)["calls"]]
    return {"first": ids[0] if ids else "", "calls": len(ids), "head": chain(ids)}


def begins_with(path: str, committed: Mapping[str, Any]) -> bool:
    """Whether the ledger still starts with the chain a committed result recorded.

    A deleted or replaced ledger reads as empty or as another run's, and a
    key re-marked into it would score fresh (V3). The committed chain is what
    survives the deletion, in git beside the result.
    """
    count = committed.get("calls")
    if not isinstance(count, int) or count <= 0:
        return True
    try:
        ids = [call["id"] for call in read(path)["calls"]]
    except LedgerError:
        return False
    return (
        len(ids) >= count
        and ids[0] == committed.get("first")
        and chain(ids[:count]) == committed.get("head")
    )


def committed_chain(summary_path: str = "") -> dict[str, Any] | None:
    """The ledger chain a committed Claude Code result recorded, if there is one."""
    try:
        with open(summary_path or CLAUDE_SUMMARY_PATH, encoding="utf-8") as handle:
            body = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError):
        # A result that cannot be read cannot vouch that the key is unfrozen.
        return {"first": "", "calls": 1, "head": ""}
    held = body.get("ledger_chain") if isinstance(body, dict) else None
    return dict(held) if isinstance(held, dict) else None


def has_calls(path: str = "") -> bool:
    """Whether any call is charged. An unreadable ledger answers yes: fail closed."""
    try:
        return bool(read(path or LEDGER_PATH)["calls"])
    except LedgerError:
        return True
