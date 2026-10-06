"""Reviewed closure reservations shared by replay, qualification and live attempts.

Only salted slots, request digests and closed statuses reach this account ledger.
The fixed repository manifest admits 190/31/18 attempts, never 239+31+18.
Every charge has an immutable receipt; missing state cannot refund its attempts.
This is an operator evaluation guard, not provider authentication or a token cap.
"""

# ruff: noqa: INP001 - operator scripts intentionally have no package root
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import abstention_ledger as authority

MANIFEST_PATH = str(Path(__file__).resolve().parents[1] / "docs/drift-replay/closure-campaign.json")
LEDGER_PATH = authority.canonical_path(".cargento", "analyze-closure-spend.json")
REPLAY_PATH = authority.canonical_path(".cargento", "drift-replay", "spend.json")
QUALIFICATION_PATH = authority.LEDGER_PATH
LANES = ("replay", "qualification", "live")
LIMITS = {"replay": 190, "qualification": 31, "live": 18}
RETRIES = {"replay": 0, "qualification": 1, "live": 4}
SLOTS = {"replay": 190, "qualification": 30, "live": 14}
STATUSES = (
    "charged",
    "usable",
    "unusable",
    "semantic-failed",
    "coverage-failed",
    "protection-failed",
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SLOT = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,95}$")


class AwaitingReviewError(authority.LedgerError):
    """A completed batch awaits review; no provider attempt failed."""


def active_campaign() -> Campaign | None:
    """An existing fixed manifest or account receipt cannot be bypassed by removing one."""
    if os.path.lexists(MANIFEST_PATH) or (
        LEDGER_PATH
        and (os.path.lexists(LEDGER_PATH) or os.path.lexists(LEDGER_PATH + ".reservations"))
    ):
        return Campaign()
    return None


def request_digest(
    prompt: str,
    producer: Any,
    source_digest: str,
    output_cap_bytes: int,
    *,
    shim_digest: str = "",
    contract_digest: str = "",
) -> str:
    """Bind actual transport words and fixed runtime source without retaining either."""
    return authority.digest(
        {
            "prompt": hashlib.sha256(prompt.encode()).hexdigest(),
            "producer": producer,
            "source": source_digest,
            "output_cap_bytes": output_cap_bytes,
            "study_shim": shim_digest,
            "study_contract": contract_digest,
        }
    )


def verified_transport_binding(
    config: Any, verified: Any, observer: Any, *, claude_executor: Any = None
) -> dict[str, Any]:
    """Bind the verified CLI and actual argv without launching a provider."""
    import score_abstention  # noqa: PLC0415 - operator CLI verification/capture
    from cargento_runtime import reading_route  # noqa: PLC0415 - runtime already admitted

    destination = reading_route.destination("claude")
    if destination != reading_route.VENDORS["claude"]:
        raise authority.LedgerError("the bound transport destination is not Anthropic")
    result = {
        "reading": observer.claude_reading_provenance(config),
        "binary": verified.shown,
        "binary_sha256": verified.identity[-1],
        "cli_version": verified.version,
        "signature": verified.signature,
        "destination": destination,
        "argv_digest": score_abstention.argv_digest(
            "claude", config, claude_executor=claude_executor
        ),
    }
    validate_transport_binding(result)
    return result


def validate_transport_binding(value: Any) -> None:
    from cargento_runtime import reading_route  # noqa: PLC0415 - admitted native transport

    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "reading",
            "binary",
            "binary_sha256",
            "cli_version",
            "signature",
            "destination",
            "argv_digest",
        }
        or not isinstance(value["reading"], dict)
        or not value["reading"]
        or value["destination"] != reading_route.VENDORS["claude"]
        or any(
            not isinstance(value[k], str) or not _DIGEST.fullmatch(value[k])
            for k in ("binary_sha256", "argv_digest")
        )
        or any(
            not isinstance(value[k], str) or not 1 <= len(value[k]) <= 2048
            for k in ("binary", "cli_version", "signature")
        )
    ):
        raise authority.LedgerError("the actual verified transport binding is unavailable")


def runtime_source_digest(root: Path) -> str:
    """Hash the shipped Python runtime bytes; source changes cannot inherit old admission."""
    files = sorted(root.rglob("*.py"))
    if not files or len(files) > 256:
        raise authority.LedgerError("the runtime source inventory is unavailable")
    parts = []
    for path in files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise authority.LedgerError("the runtime source exceeds its bound")
        parts.append((str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest()))
    return authority.digest(parts)


def _read(path: str | None, label: str) -> Any:
    if not path:
        raise authority.LedgerError("the account's canonical home is unavailable")
    return authority._review_json(path, label, cap=2 * 1024 * 1024)  # noqa: SLF001 - shared bounded ledger reader


def _manifest() -> tuple[dict[str, Any], str]:  # noqa: C901, PLR0912 - each authority field fails closed independently
    body = _read(MANIFEST_PATH, "closure campaign manifest")
    if (
        not isinstance(body, dict)
        or type(body.get("v")) is not int
        or body["v"] != 1
        or body.get("phase") not in ("prepared", "sealed")
    ):
        raise authority.LedgerError("the closure campaign is not sealed")
    if body["phase"] == "sealed" and (
        not isinstance(body.get("activation_anchor"), str)
        or not _DIGEST.fullmatch(body["activation_anchor"])
    ):
        raise authority.LedgerError("the reviewed campaign activation anchor is missing")
    if (
        not isinstance(body.get("order"), list)
        or len(body["order"]) != 3
        or any(not isinstance(lane, str) for lane in body["order"])
        or body["order"] != ["replay", "qualification", "live"]
    ):
        raise authority.LedgerError("the reviewed study order is missing")
    if any(
        not isinstance(body.get(field), dict)
        for field in (
            "limits",
            "retry_limits",
            "bindings",
            "slots",
            "evidence",
            "protocols",
            "historical",
            "requests",
        )
    ):
        raise authority.LedgerError("the reviewed campaign fields are malformed")
    if (
        body.get("limits") != LIMITS
        or body.get("retry_limits") != RETRIES
        or any(
            type((body.get(field) or {}).get(lane)) is not int
            for field in ("limits", "retry_limits")
            for lane in LANES
        )
    ):
        raise authority.LedgerError("the closure campaign has another allowance")
    held = body.get("deferred_slots", {lane: [] for lane in LANES})
    if not isinstance(held, dict) or set(held) != set(LANES):
        raise authority.LedgerError("the explicitly deferred campaign slots are malformed")
    for lane in LANES:
        evidence = body["evidence"].get(lane)
        if (
            not isinstance(evidence, dict)
            or set(evidence) != {"scorer", "source", "marks"}
            or any(
                not isinstance(value, str) or not _DIGEST.fullmatch(value)
                for value in evidence.values()
            )
            or not isinstance(body["protocols"].get(lane), str)
            or not _SLOT.fullmatch(body["protocols"][lane])
        ):
            raise authority.LedgerError("the reviewed measurement protocol is unbound")
        binding = (body.get("bindings") or {}).get(lane)
        slots = (body.get("slots") or {}).get(lane)
        if not isinstance(binding, str) or not _DIGEST.fullmatch(binding):
            raise authority.LedgerError("the closure request binding is missing")
        if (
            not isinstance(slots, list)
            or len(slots) != SLOTS[lane]
            or any(not isinstance(slot, str) or not _SLOT.fullmatch(slot) for slot in slots)
            or len(set(slots)) != len(slots)
        ):
            raise authority.LedgerError("the registered campaign slots are malformed")
        requests = body["requests"].get(lane)
        if (
            not isinstance(held[lane], list)
            or any(not isinstance(slot, str) or slot not in slots for slot in held[lane])
            or len(set(held[lane])) != len(held[lane])
        ):
            raise authority.LedgerError("the deferred campaign slots are unregistered")
        if (
            not isinstance(requests, dict)
            or set(requests) != set(slots) - set(held[lane])
            or any(
                not isinstance(value, str) or not _DIGEST.fullmatch(value)
                for value in requests.values()
            )
        ):
            raise authority.LedgerError("the actual campaign requests are unbound")
    batches = body.get("batches")
    if not isinstance(batches, dict) or set(batches) != set(LANES):
        raise authority.LedgerError("the registered batch boundaries are missing")
    for lane in LANES:
        groups = batches[lane]
        if (
            not isinstance(groups, list)
            or not groups
            or any(
                not isinstance(group, list)
                or not 1 <= len(group) <= (10 if lane == "qualification" else 25)
                for group in groups
            )
            or [slot for group in groups for slot in group] != body["slots"][lane]
        ):
            raise authority.LedgerError("the registered batches do not partition the lane")
        if len(groups[0]) != 1:
            raise authority.LedgerError("each lane's opening batch must be one availability call")
    # Digest normalized reviewed fields; formatting does not change authorization.
    return body, authority.digest(
        {key: value for key, value in body.items() if key not in ("phase", "activation_anchor")}
    )


def _history(manifest: dict[str, Any]) -> None:
    for lane, path, count in (
        ("replay", REPLAY_PATH, 631),
        ("qualification", QUALIFICATION_PATH, 28),
    ):
        expected = (manifest.get("historical") or {}).get(lane)
        if (
            not isinstance(expected, dict)
            or type(expected.get("calls")) is not int
            or expected["calls"] != count
            or not isinstance(expected.get("sha256"), str)
            or not _DIGEST.fullmatch(expected["sha256"])
        ):
            raise authority.LedgerError("the historical campaign prefix is unbound")
        body = _read(path, "historical spend prefix")
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("calls"), list)
            or len(body["calls"]) != count
        ):
            raise authority.LedgerError("the historical campaign prefix has changed")
        if hashlib.sha256(Path(str(path)).read_bytes()).hexdigest() != expected["sha256"]:
            raise authority.LedgerError("the historical campaign prefix has changed")
    _prefixes(manifest)


def _prefixes(manifest: dict[str, Any]) -> None:
    for lane, path, count in (
        ("replay", REPLAY_PATH, 631),
        ("qualification", QUALIFICATION_PATH, 28),
    ):
        expected = manifest["historical"][lane].get("calls_digest")
        body = _read(path, "historical charged prefix")
        if (
            not isinstance(expected, str)
            or not _DIGEST.fullmatch(expected)
            or not isinstance(body, dict)
            or not isinstance(body.get("calls"), list)
            or len(body["calls"]) < count
            or authority.digest(body["calls"][:count]) != expected
        ):
            raise authority.LedgerError("the original charged prefix was altered or removed")


def _receipt(call: dict[str, Any]) -> dict[str, Any]:
    return {
        key: call[key]
        for key in ("id", "at", "lane", "slot", "binding", "retry", "availability_attempt")
    }


def _valid_call(call: Any, manifest: dict[str, Any]) -> bool:
    return (
        isinstance(call, dict)
        and isinstance(call.get("id"), str)
        and re.fullmatch(r"[0-9a-f]{32}", call["id"]) is not None
        and call.get("lane") in LANES
        and call.get("slot") in manifest["slots"][call["lane"]]
        and call["slot"] in manifest["requests"][call["lane"]]
        and call.get("binding") == manifest["requests"][call["lane"]][call["slot"]]
        and type(call.get("retry")) is bool
        and type(call.get("availability_attempt")) is int
        and call["availability_attempt"] in (0, 1, 2)
        and call.get("status") in STATUSES
        and type(call.get("at")) in (float, int)
        and math.isfinite(call["at"])
    )


class Campaign:
    """One immutable manifest and one account-wide, serial, persistent charge stream."""

    def __init__(self) -> None:
        self.manifest, self.binding = _manifest()
        if not LEDGER_PATH:
            raise authority.LedgerError("the account's canonical home is unavailable")
        self.path = LEDGER_PATH
        self.receipts = Path(self.path + ".reservations")

    def initialize(self) -> str:
        """Create a zero-charge genesis for review; activation requires its public digest.

        No activated or existing campaign is initialized again. No provider runs.
        """
        with authority.locked(self.path):
            current, key = _manifest()
            if current != self.manifest or key != self.binding:
                raise authority.LedgerError("the preparation changed before genesis initialization")
            if (
                self.manifest["phase"] != "prepared"
                or self.manifest.get("activation_anchor")
                or os.path.lexists(self.path)
                or os.path.lexists(self.receipts)
            ):
                raise authority.LedgerError("the campaign genesis cannot be initialized again")
            _history(self.manifest)
            body = {
                "v": 1,
                "manifest_digest": self.binding,
                "calls": [],
                "genesis_nonce": uuid.uuid4().hex,
            }
            authority._write(self.path, body)  # noqa: SLF001 - canonical zero-charge genesis
            return authority.digest(body)

    def _state(self) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - validate the append-only receipt chain before mutation
        if self.receipts.is_symlink():
            raise authority.LedgerError("the campaign receipts are a symlink")
        names = (
            list(itertools.islice(self.receipts.iterdir(), 717)) if self.receipts.exists() else []
        )
        if len(names) > 716:
            raise authority.LedgerError("the campaign receipt directory exceeds its bound")
        stop_path = self.receipts / "STOP.json"
        if not os.path.lexists(self.path):
            raise authority.LedgerError(
                "the initialized campaign ledger is missing; no automatic genesis is allowed"
            )
        body = _read(self.path, "closure campaign ledger")
        _prefixes(self.manifest)
        if (
            not isinstance(body, dict)
            or type(body.get("v")) is not int
            or body["v"] != 1
            or body.get("manifest_digest") != self.binding
            or not isinstance(body.get("calls"), list)
            or len(body["calls"]) > 239
            or any(not _valid_call(c, self.manifest) for c in body["calls"])
        ):
            raise authority.LedgerError("the campaign ledger has changed")
        nonce = body.get("genesis_nonce")
        genesis: dict[str, Any] = {
            "v": 1,
            "manifest_digest": self.binding,
            "calls": [],
            "genesis_nonce": nonce,
        }
        if (
            not isinstance(nonce, str)
            or not re.fullmatch(r"[0-9a-f]{32}", nonce)
            or self.manifest["phase"] != "sealed"
            or authority.digest(genesis) != self.manifest["activation_anchor"]
        ):
            raise authority.LedgerError("the campaign genesis does not match reviewed activation")
        calls = body["calls"]
        stopped = body.get("stop")
        if stopped is not None:
            if stopped not in ("semantic-failed", "coverage-failed", "protection-failed"):
                raise authority.LedgerError("the campaign stop classification changed")
            if _read(str(stop_path), "campaign stop receipt") != {
                "stop": stopped,
                "manifest_digest": self.binding,
            }:
                raise authority.LedgerError("the campaign stop receipt changed")
        accepted = body.get("accepted", {})
        accepted_batches = body.get("accepted_batches", {})
        if not isinstance(accepted, dict) or any(lane not in LANES for lane in accepted):
            raise authority.LedgerError("the accepted-lane index changed")
        if (
            not isinstance(accepted_batches, dict)
            or len({c["id"] for c in calls}) != len(calls)
            or len(names)
            != len(calls)
            + sum(call["status"] != "charged" for call in calls)
            + len(accepted)
            + len(accepted_batches)
            + int(stopped is not None)
        ):
            raise authority.LedgerError("the campaign receipt chain has changed")
        for call in calls:
            if _read(str(self.receipts / (call["id"] + ".json")), "campaign receipt") != _receipt(
                call
            ):
                raise authority.LedgerError("the campaign reservation was rewritten")
            if call["status"] != "charged":
                receipt = _read(
                    str(self.receipts / (call["id"] + "-SETTLED.json")),
                    "campaign classification receipt",
                )
                if receipt != {
                    "id": call["id"],
                    "status": call["status"],
                    "manifest_digest": self.binding,
                }:
                    raise authority.LedgerError("the settled campaign classification was rewritten")
        for lane in LANES:
            own = [c for c in calls if c["lane"] == lane]
            if len(own) > LIMITS[lane] or sum(c["retry"] for c in own) > RETRIES[lane]:
                raise authority.LedgerError("the campaign allowance was exceeded")
        for lane, proof_digest in accepted.items():
            proof = _read(
                str(self.receipts / (lane + "-ACCEPTED.json")), "accepted measurement receipt"
            )
            if authority.digest(proof) != proof_digest:
                raise authority.LedgerError("the accepted measurement receipt changed")
            self._validate_acceptance(lane, proof, calls)
        for batch, proof_digest in accepted_batches.items():
            if not isinstance(batch, str) or not re.fullmatch(
                r"(?:replay|qualification|live):[0-9]{1,2}", batch
            ):
                raise authority.LedgerError("the accepted batch index changed")
            lane, index = batch.split(":")
            if int(index) >= len(self.manifest["batches"][lane]):
                raise authority.LedgerError("the accepted batch is unregistered")
            proof = _read(
                str(self.receipts / (batch.replace(":", "-") + "-BATCH.json")),
                "accepted batch receipt",
            )
            if authority.digest(proof) != proof_digest:
                raise authority.LedgerError("the accepted batch receipt changed")
            self._validate_acceptance(lane, proof, calls, batch=int(index))
        return body

    def _validate_acceptance(
        self, lane: str, proof: Any, calls: list[dict[str, Any]], *, batch: int | None = None
    ) -> None:
        slots = (
            self.manifest["slots"][lane] if batch is None else self.manifest["batches"][lane][batch]
        )
        if set(slots) & set(self.manifest.get("deferred_slots", {}).get(lane, [])):
            raise authority.LedgerError("an explicitly deferred slot cannot pass")
        own = [call for call in calls if call["lane"] == lane and call["slot"] in slots]
        latest = {call["slot"]: call["status"] for call in own}
        expected: dict[str, Any] = {
            "v": 1,
            "lane": lane,
            "manifest_digest": self.binding,
            "protocol": self.manifest["protocols"][lane],
            "binding": self.manifest["bindings"][lane],
            "evidence": self.manifest["evidence"][lane],
            "slots_digest": authority.digest(slots),
            "attempts_digest": authority.digest(own),
            "charged_attempts": len(own),
            "expected_slots": len(slots),
            "usable_slots": len(slots),
            "semantic_failures": 0,
            "coverage_failures": 0,
            "protection_failures": 0,
            "verdict": "passed",
        }
        if batch is not None:
            expected["batch"] = batch
        if (
            not isinstance(proof, dict)
            or set(proof) != set(expected) | {"output_digest", "review_digest"}
            or any(
                proof.get(key) != value or type(proof.get(key)) is not type(value)
                for key, value in expected.items()
            )
            or any(
                not isinstance(proof.get(key), str) or not _DIGEST.fullmatch(proof[key])
                for key in ("output_digest", "review_digest")
            )
            or any(latest.get(slot) != "usable" for slot in slots)
            or any(
                call["status"].endswith("-failed") or call["status"] == "charged" for call in own
            )
        ):
            raise authority.LedgerError("the measured and reviewed lane acceptance is incomplete")

    def accept(self, lane: str, proof: dict[str, Any]) -> None:
        """Seal independently measured predicates and a review artifact before another lane.

        This validates binding and accounting, not the truth of an operator's review.
        A producer must derive the receipt from the frozen native scoring artifact.
        """
        if lane not in LANES:
            raise authority.LedgerError("the accepted lane is unknown")
        with authority.locked(self.path):
            body = self._state()
            if body.get("stop"):
                raise authority.LedgerError("the stopped campaign cannot accept another study")
            self._stop(body["calls"])
            self._validate_acceptance(lane, proof, body["calls"])
            descriptor = os.open(
                self.receipts / (lane + "-ACCEPTED.json"),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(proof, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            body.setdefault("accepted", {})[lane] = authority.digest(proof)
            authority._write(self.path, body)  # noqa: SLF001 - shared atomic ledger writer

    def accept_batch(self, lane: str, batch: int, proof: dict[str, Any]) -> None:
        """Seal measured batch predicates and review before the next registered batch."""
        if (
            lane not in LANES
            or type(batch) is not int
            or not 0 <= batch < len(self.manifest["batches"][lane])
        ):
            raise authority.LedgerError("the accepted batch is unregistered")
        with authority.locked(self.path):
            body = self._state()
            if body.get("stop"):
                raise authority.LedgerError("the stopped campaign cannot accept a batch")
            self._stop(body["calls"])
            self._validate_acceptance(lane, proof, body["calls"], batch=batch)
            key = f"{lane}:{batch}"
            self.receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(
                self.receipts / (key.replace(":", "-") + "-BATCH.json"),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(proof, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            body.setdefault("accepted_batches", {})[key] = authority.digest(proof)
            authority._write(self.path, body)  # noqa: SLF001 - shared atomic ledger writer

    @staticmethod
    def _stop(calls: list[dict[str, Any]]) -> None:
        if any(c["status"].endswith("-failed") for c in calls):
            raise authority.LedgerError("a semantic or coverage failure stopped the whole campaign")
        if any(c["status"] == "charged" for c in calls):
            raise authority.LedgerError("an unclassified or orphan campaign call blocks launch")
        if len(calls) >= 2 and all(c["status"] == "unusable" for c in calls[-2:]):
            raise authority.LedgerError("two consecutive unusable calls stopped the whole campaign")

    def review_pending(self, lane: str, slot: str) -> bool:
        """Read-only pause at reviewed batch boundaries; never create a charge."""
        with authority.locked(self.path):
            body = self._state()
            self._stop(body["calls"])
            groups = self.manifest["batches"][lane]
            index = next(n for n, group in enumerate(groups) if slot in group)
            return any(f"{lane}:{n}" not in body.get("accepted_batches", {}) for n in range(index))

    def request_slot(self, lane: str, request: str) -> str:
        """Match only the next declared request; matching a later favorable slot cannot skip one."""
        with authority.locked(self.path):
            body = self._state()
            self._stop(body["calls"])
            slot = self._next_slot(lane, body["calls"])
            if (
                slot is None
                or slot in self.manifest.get("deferred_slots", {}).get(lane, [])
                or self.manifest["requests"][lane][slot] != request
            ):
                raise authority.LedgerError(
                    "the actual transport is not the next frozen campaign request"
                )
            return str(slot)

    def _next_slot(self, lane: str, calls: list[dict[str, Any]]) -> str | None:
        latest = {call["slot"]: call["status"] for call in calls if call["lane"] == lane}
        return next(
            (slot for slot in self.manifest["slots"][lane] if latest.get(slot) != "usable"), None
        )

    def reserve(self, lane: str, slot: str, binding: str, *, retry: bool = False) -> str:  # noqa: C901, PLR0912, PLR0915 - serial authority admission, one refusal per invariant
        """Charge before launching; successful, pending and unregistered slots cannot repeat."""
        with authority.locked(self.path):
            # Re-read authority inside the same charge lock, never trusting constructor time.
            current, key = _manifest()
            if current["phase"] != "sealed":
                raise authority.LedgerError(
                    "the campaign genesis has not been reviewed and activated"
                )
            if key != self.binding or current != self.manifest:
                raise authority.LedgerError("the reviewed campaign changed before charge")
            if slot in self.manifest.get("deferred_slots", {}).get(lane, []):
                raise authority.LedgerError("the campaign slot is explicitly deferred and unbound")
            if (
                lane not in LANES
                or slot not in self.manifest["slots"][lane]
                or binding != self.manifest["requests"][lane][slot]
                or type(retry) is not bool
            ):
                raise authority.LedgerError("this is not a registered campaign request")
            body = self._state()
            calls = body["calls"]
            if body.get("stop"):
                raise authority.LedgerError("the whole campaign was explicitly stopped")
            self._stop(calls)
            if slot != self._next_slot(lane, calls):
                raise authority.LedgerError("a prior unresolved campaign slot cannot be skipped")
            own = [c for c in calls if c["lane"] == lane]
            if len(calls) >= 239 or len(own) >= LIMITS[lane]:
                raise authority.SpendCapError("the shared campaign allowance is full")
            order = self.manifest["order"]
            for previous in order[: order.index(lane)]:
                if previous not in body.get("accepted", {}):
                    raise authority.LedgerError(
                        "a predecessor study lacks measured and reviewed acceptance"
                    )
            if lane in body.get("accepted", {}):
                raise authority.LedgerError("the accepted lane cannot launch more attempts")
            groups = self.manifest["batches"][lane]
            index = next(n for n, group in enumerate(groups) if slot in group)
            group_calls = sum(call["slot"] in groups[index] for call in own)
            if group_calls >= (2 if index == 0 and retry else 1 if index == 0 else 25):
                raise authority.SpendCapError("the registered batch has charged 25 actual attempts")
            if any(f"{lane}:{n}" not in body.get("accepted_batches", {}) for n in range(index)):
                raise AwaitingReviewError(
                    "the preceding batch lacks measured and reviewed acceptance"
                )
            if f"{lane}:{index}" in body.get("accepted_batches", {}):
                raise authority.LedgerError("the accepted batch cannot launch more attempts")
            prior = [c for c in own if c["slot"] == slot]
            if retry:
                if (
                    not prior
                    or prior[-1]["status"] != "unusable"
                    or sum(c["retry"] for c in own) >= RETRIES[lane]
                ):
                    raise authority.LedgerError("the registered failed-call retry is unavailable")
            elif prior:
                raise authority.LedgerError("the registered slot is already charged")
            call: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "at": time.time(),
                "lane": lane,
                "slot": slot,
                "binding": binding,
                "retry": retry,
                "availability_attempt": group_calls + 1 if index == 0 else 0,
                "status": "charged",
            }
            self.receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
            receipt_path = self.receipts / (call["id"] + ".json")
            descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(_receipt(call), handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            calls.append(call)
            authority._write(self.path, body)  # noqa: SLF001 - shared atomic ledger writer
            return str(call["id"])

    def settle(self, charge_id: str, status: str) -> None:
        """Only a pending charge is classified; settled failures are never erased."""
        if status not in STATUSES or status == "charged":
            raise authority.LedgerError("the campaign classification is invalid")
        with authority.locked(self.path):
            body = self._state()
            found = next((c for c in body["calls"] if c["id"] == charge_id), None)
            if not found or found["status"] != "charged":
                raise authority.LedgerError("the campaign attempt is not pending")
            descriptor = os.open(
                self.receipts / (charge_id + "-SETTLED.json"),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    {"id": charge_id, "status": status, "manifest_digest": self.binding},
                    handle,
                    sort_keys=True,
                )
                handle.flush()
                os.fsync(handle.fileno())
            found["status"] = status
            authority._write(self.path, body)  # noqa: SLF001 - shared atomic ledger writer

    def stop(self, reason: str) -> None:
        """Latch an eligibility/coverage failure even when no model could be launched."""
        if reason not in ("semantic-failed", "coverage-failed", "protection-failed"):
            raise authority.LedgerError("the campaign stop reason is invalid")
        with authority.locked(self.path):
            body = self._state()
            if body.get("stop"):
                return
            self.receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = self.receipts / "STOP.json"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"stop": reason, "manifest_digest": self.binding}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            body["stop"] = reason
            authority._write(self.path, body)  # noqa: SLF001 - shared atomic ledger writer
