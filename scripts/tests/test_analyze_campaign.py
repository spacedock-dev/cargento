"""A shared closure ceiling stays charged across homes, retries and process restarts."""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import abstention_ledger as ledger

if TYPE_CHECKING:
    from analyze_campaign import Campaign


def acceptance(campaign: Campaign, lane: str, batch: int | None = None) -> dict[str, Any]:
    slots = (
        campaign.manifest["slots"][lane]
        if batch is None
        else campaign.manifest["batches"][lane][batch]
    )
    own = [
        call
        for call in campaign._state()["calls"]
        if call["lane"] == lane and call["slot"] in slots
    ]
    proof = {
        "v": 1,
        "lane": lane,
        "manifest_digest": campaign.binding,
        "protocol": campaign.manifest["protocols"][lane],
        "binding": campaign.manifest["bindings"][lane],
        "evidence": campaign.manifest["evidence"][lane],
        "slots_digest": ledger.digest(slots),
        "attempts_digest": ledger.digest(own),
        "charged_attempts": len(own),
        "expected_slots": len(slots),
        "usable_slots": len(slots),
        "semantic_failures": 0,
        "coverage_failures": 0,
        "protection_failures": 0,
        "verdict": "passed",
        "output_digest": "c" * 64,
        "review_digest": "d" * 64,
    }
    if batch is not None:
        proof["batch"] = batch
    return proof


class CampaignReservations(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.module: Any = importlib.import_module("analyze_campaign")
        except ModuleNotFoundError:
            self.module = None
        self.assertIsNotNone(self.module, "shared campaign reservation implementation missing")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.manifest = self.root / "reviewed.json"
        self.state = self.root / "campaign.json"
        self.replay = self.root / "replay.json"
        self.qualification = self.root / "qualification.json"
        self.replay.write_text(json.dumps({"calls": [{} for _ in range(631)]}))
        self.qualification.write_text(json.dumps({"calls": [{} for _ in range(28)]}))
        self.slots = {
            lane: [f"{lane}{n:03}" for n in range(count)]
            for lane, count in (("replay", 190), ("qualification", 30), ("live", 14))
        }
        self.body: dict[str, Any] = {
            "v": 1,
            "phase": "sealed",
            "limits": {"replay": 190, "qualification": 31, "live": 18},
            "retry_limits": {"replay": 0, "qualification": 1, "live": 4},
            "bindings": dict.fromkeys(self.slots, "a" * 64),
            "slots": self.slots,
            "requests": {
                lane: dict.fromkeys(slots, "a" * 64) for lane, slots in self.slots.items()
            },
            "order": ["replay", "qualification", "live"],
            "batches": {
                lane: [
                    slots[n : n + (10 if lane == "qualification" else 25)]
                    for n in range(0, len(slots), 10 if lane == "qualification" else 25)
                ]
                for lane, slots in self.slots.items()
            },
            "protocols": dict.fromkeys(self.slots, "synthetic-test-v1"),
            "evidence": {
                lane: dict.fromkeys(("scorer", "source", "marks"), "e" * 64) for lane in self.slots
            },
            "historical": {
                lane: {
                    "calls": count,
                    "sha256": self.sha(path),
                    "calls_digest": ledger.digest(json.loads(path.read_text())["calls"]),
                }
                for lane, path, count in (
                    ("replay", self.replay, 631),
                    ("qualification", self.qualification, 28),
                )
            },
        }
        for lane, slots in self.slots.items():
            size = 10 if lane == "qualification" else 25
            self.body["batches"][lane] = [
                slots[:1],
                *[slots[n : n + size] for n in range(1, len(slots), size)],
            ]
        self.manifest.write_text(json.dumps(self.body))
        for key, value in (
            ("MANIFEST_PATH", self.manifest),
            ("LEDGER_PATH", self.state),
            ("REPLAY_PATH", self.replay),
            ("QUALIFICATION_PATH", self.qualification),
        ):
            patch = mock.patch.object(self.module, key, str(value))
            patch.start()
            self.addCleanup(patch.stop)
        self.activate()

    def activate(self) -> None:
        if self.state.exists():
            self.assertEqual([], json.loads(self.state.read_text())["calls"])
            self.state.unlink()
        self.body["phase"] = "prepared"
        self.body.pop("activation_anchor", None)
        self.manifest.write_text(json.dumps(self.body))
        anchor = self.module.Campaign().initialize()
        self.body.update(phase="sealed", activation_anchor=anchor)
        self.manifest.write_text(json.dumps(self.body))

    @staticmethod
    def sha(path: Path) -> str:
        import hashlib  # noqa: PLC0415 - isolated digest helper

        return hashlib.sha256(path.read_bytes()).hexdigest()

    def campaign(self) -> Campaign:
        return cast("Campaign", self.module.Campaign())

    def charge(self, lane: str, slot: str, *, retry: bool = False) -> str:
        return self.campaign().reserve(lane, slot, "a" * 64, retry=retry)

    def fill_replay(self, *, accept: bool = True) -> None:
        self.fill_lane("replay", accept=accept)

    def fill_lane(self, lane: str, *, accept: bool = True) -> None:
        for n, group in enumerate(self.body["batches"][lane]):
            for slot in group:
                charge = self.charge(lane, slot)
                self.campaign().settle(charge, "usable")
            campaign = self.campaign()
            campaign.accept_batch(lane, n, acceptance(campaign, lane, n))
        if accept:
            campaign = self.campaign()
            campaign.accept(lane, acceptance(campaign, lane))

    def test_unregistered_or_changed_request_never_creates_a_charge(self) -> None:
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", "unregistered")
        with self.assertRaises(ledger.LedgerError):
            self.campaign().reserve("replay", self.slots["replay"][0], "b" * 64)
        self.assertEqual([], json.loads(self.state.read_text())["calls"])

    def test_only_approved_lane_order_can_be_registered(self) -> None:
        self.body["order"] = ["live", "qualification", "replay"]
        self.manifest.write_text(json.dumps(self.body))
        with self.assertRaises(ledger.LedgerError):
            self.campaign()

    def test_a_later_slot_cannot_skip_the_next_fresh_or_unusable_slot(self) -> None:
        campaign = self.campaign()
        campaign.settle(self.charge("replay", self.slots["replay"][0]), "usable")
        campaign.accept_batch("replay", 0, acceptance(campaign, "replay", 0))
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][2])
        campaign.settle(self.charge("replay", self.slots["replay"][1]), "unusable")
        self.assertEqual(self.slots["replay"][1], campaign.request_slot("replay", "a" * 64))
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][2])
        self.assertEqual(2, len(campaign._state()["calls"]))

    def test_unbound_held_live_slots_never_charge_or_accept(self) -> None:
        self.body["deferred_slots"] = {
            "replay": [],
            "qualification": [],
            "live": self.slots["live"],
        }
        self.body["requests"]["live"] = {}
        self.activate()
        self.fill_replay()
        self.fill_lane("qualification")
        campaign = self.campaign()
        with self.assertRaises(ledger.LedgerError):
            campaign.request_slot("live", "a" * 64)
        with self.assertRaises(ledger.LedgerError):
            self.charge("live", self.slots["live"][0])
        with self.assertRaises(ledger.LedgerError):
            campaign.accept("live", acceptance(campaign, "live"))
        self.assertEqual([], [c for c in campaign._state()["calls"] if c["lane"] == "live"])

    def test_missing_binding_on_nonheld_slot_refuses(self) -> None:
        del self.body["requests"]["live"][self.slots["live"][0]]
        self.manifest.write_text(json.dumps(self.body))
        with self.assertRaises(ledger.LedgerError):
            self.campaign()
        self.assertEqual([], json.loads(self.state.read_text())["calls"])

    def test_opening_unusable_call_allows_only_explicit_same_slot_retry(self) -> None:
        self.body["batches"]["live"] = [[self.slots["live"][0]], self.slots["live"][1:]]
        self.activate()
        self.fill_replay()
        self.fill_lane("qualification")
        slot = self.slots["live"][0]
        first = self.charge("live", slot)
        self.campaign().settle(first, "unusable")
        with self.assertRaises(ledger.LedgerError):
            self.charge("live", slot)
        with self.assertRaises(ledger.LedgerError):
            self.charge("live", self.slots["live"][1])
        second = self.charge("live", slot, retry=True)
        self.campaign().settle(second, "usable")
        campaign = self.campaign()
        calls = [c for c in campaign._state()["calls"] if c["lane"] == "live"]
        self.assertEqual([1, 2], [call["availability_attempt"] for call in calls])
        campaign.accept_batch("live", 0, acceptance(campaign, "live", 0))
        self.charge("live", self.slots["live"][1])

    def test_bound_batch_can_pass_while_later_held_live_slots_cannot(self) -> None:
        held = self.slots["live"][-4:]
        self.body["deferred_slots"] = {"replay": [], "qualification": [], "live": held}
        for slot in held:
            del self.body["requests"]["live"][slot]
        self.activate()
        self.fill_replay()
        self.fill_lane("qualification")
        campaign = self.campaign()
        campaign.settle(self.charge("live", self.slots["live"][0]), "usable")
        campaign.accept_batch("live", 0, acceptance(campaign, "live", 0))
        with self.assertRaises(ledger.LedgerError):
            campaign.accept("live", acceptance(campaign, "live"))
        with self.assertRaises(ledger.LedgerError):
            self.charge("live", held[0])

    def test_missing_old_prefix_cannot_initialize_new_authorization(self) -> None:
        self.qualification.unlink()
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][0])
        self.assertEqual([], json.loads(self.state.read_text())["calls"])

    def test_new_process_or_home_cannot_repeat_a_usable_slot(self) -> None:
        campaign = self.campaign()
        c = self.charge("replay", self.slots["replay"][0])
        campaign.settle(c, "usable")
        campaign.accept_batch("replay", 0, acceptance(campaign, "replay", 0))
        slot = self.slots["replay"][1]
        c = self.charge("replay", slot)
        self.campaign().settle(c, "usable")
        with (
            mock.patch.dict("os.environ", {"CARGENTO_HOME": str(self.root / "another")}),
            self.assertRaises(ledger.LedgerError),
        ):
            self.charge("replay", slot)
        self.assertEqual(2, len(json.loads(self.state.read_text())["calls"]))

    def test_pending_or_orphan_charge_blocks_all_later_calls(self) -> None:
        campaign = self.campaign()
        c = self.charge("replay", self.slots["replay"][0])
        campaign.settle(c, "usable")
        campaign.accept_batch("replay", 0, acceptance(campaign, "replay", 0))
        self.charge("replay", self.slots["replay"][1])
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][2])
        self.assertEqual(2, len(json.loads(self.state.read_text())["calls"]))

    def test_deleted_ledger_with_reservation_receipt_cannot_reset_budget(self) -> None:
        c = self.charge("replay", self.slots["replay"][0])
        self.campaign().settle(c, "usable")
        self.state.unlink()
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][0])

    def test_semantic_failure_is_persistent_and_stops_every_lane(self) -> None:
        campaign = self.campaign()
        c = self.charge("replay", self.slots["replay"][0])
        campaign.settle(c, "usable")
        campaign.accept_batch("replay", 0, acceptance(campaign, "replay", 0))
        c = self.charge("replay", self.slots["replay"][1])
        self.campaign().settle(c, "protection-failed")
        for lane in self.slots:
            with self.subTest(lane=lane), self.assertRaises(ledger.LedgerError):
                self.charge(lane, self.slots[lane][2])

    def test_two_unusable_calls_stop_across_new_instances(self) -> None:
        self.fill_replay()
        self.fill_lane("qualification")
        campaign = self.campaign()
        c = self.charge("live", self.slots["live"][0])
        campaign.settle(c, "usable")
        campaign.accept_batch("live", 0, acceptance(campaign, "live", 0))
        slot = self.slots["live"][1]
        for retry in (False, True):
            c = self.charge("live", slot, retry=retry)
            self.campaign().settle(c, "unusable")
        with self.assertRaises(ledger.LedgerError):
            self.charge("live", slot, retry=True)
        calls = json.loads(self.state.read_text())["calls"]
        self.assertEqual(3, len([c for c in calls if c["lane"] == "live"]))

    def test_rewriting_a_settled_failure_cannot_erase_its_stop(self) -> None:
        campaign = self.campaign()
        c = self.charge("replay", self.slots["replay"][0])
        campaign.settle(c, "usable")
        campaign.accept_batch("replay", 0, acceptance(campaign, "replay", 0))
        c = self.charge("replay", self.slots["replay"][1])
        campaign.settle(c, "semantic-failed")
        body = json.loads(self.state.read_text())
        body["calls"][-1]["status"] = "usable"
        self.state.write_text(json.dumps(body))
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][2])

    def test_activated_manifest_cannot_reinitialize_after_all_private_proofs_are_deleted(
        self,
    ) -> None:
        self.state.unlink()
        with self.assertRaises(ledger.LedgerError):
            self.campaign().initialize()
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][0])
        self.assertFalse(self.state.exists())

    def test_restoring_genesis_cannot_ignore_existing_charge_and_classification_receipts(
        self,
    ) -> None:
        genesis = self.state.read_bytes()
        c = self.charge("replay", self.slots["replay"][0])
        self.campaign().settle(c, "usable")
        self.state.write_bytes(genesis)
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][0])

    def test_later_lane_requires_all_predecessor_slots_usable(self) -> None:
        with self.assertRaises(ledger.LedgerError):
            self.charge("qualification", self.slots["qualification"][0])
        self.fill_replay()
        c = self.charge("qualification", self.slots["qualification"][0])
        self.assertTrue(c)

    def test_qualification_retry_ceiling_cannot_replace_successes(self) -> None:
        self.fill_replay()
        first, second = self.slots["qualification"][:2]
        c = self.charge("qualification", first)
        self.campaign().settle(c, "unusable")
        c = self.charge("qualification", first, retry=True)
        self.campaign().settle(c, "usable")
        campaign = self.campaign()
        campaign.accept_batch("qualification", 0, acceptance(campaign, "qualification", 0))
        c = self.charge("qualification", second)
        self.campaign().settle(c, "unusable")
        with self.assertRaises(ledger.LedgerError):
            self.charge("qualification", second, retry=True)
        with self.assertRaises(ledger.LedgerError):
            self.charge("qualification", first, retry=True)

    def test_lane_and_aggregate_caps_account_all_reserved_attempts(self) -> None:
        self.fill_replay()
        for lane in ("qualification", "live"):
            retry_slots = 1 if lane == "qualification" else 4
            for n, group in enumerate(self.body["batches"][lane]):
                for slot in group:
                    if self.slots[lane].index(slot) < retry_slots:
                        c = self.charge(lane, slot)
                        self.campaign().settle(c, "unusable")
                        c = self.charge(lane, slot, retry=True)
                    else:
                        c = self.charge(lane, slot)
                    self.campaign().settle(c, "usable")
                campaign = self.campaign()
                campaign.accept_batch(lane, n, acceptance(campaign, lane, n))
            campaign = self.campaign()
            campaign.accept(lane, acceptance(campaign, lane))
        calls = json.loads(self.state.read_text())["calls"]
        self.assertEqual(239, len(calls))
        self.assertEqual(31, sum(c["lane"] == "qualification" for c in calls))
        self.assertEqual(18, sum(c["lane"] == "live" for c in calls))
        for lane in self.slots:
            with self.subTest(lane=lane), self.assertRaises(ledger.LedgerError):
                self.charge(lane, self.slots[lane][-1], retry=True)

    def test_zero_call_coverage_failure_latches_across_processes(self) -> None:
        self.campaign().stop("coverage-failed")
        self.assertEqual([], json.loads(self.state.read_text())["calls"])
        with self.assertRaises(ledger.LedgerError):
            self.charge("replay", self.slots["replay"][0])

    def test_usable_replay_slots_do_not_authorize_a_later_lane_without_acceptance(self) -> None:
        self.fill_replay(accept=False)
        with self.assertRaises(ledger.LedgerError):
            self.charge("qualification", self.slots["qualification"][0])

    def test_review_and_native_output_bindings_are_required_for_acceptance(self) -> None:
        self.fill_replay(accept=False)
        for key, value in (
            ("review_digest", ""),
            ("output_digest", ""),
            ("usable_slots", 189),
            ("coverage_failures", False),
            ("attempts_digest", "f" * 64),
        ):
            proof = acceptance(self.campaign(), "replay")
            proof[key] = value
            with self.subTest(key=key), self.assertRaises(ledger.LedgerError):
                self.campaign().accept("replay", proof)

    def test_order_is_explicit_and_not_module_lane_enumeration(self) -> None:
        self.body["order"] = ["qualification", "replay", "live"]
        self.body["batches"]["qualification"] = [
            self.slots["qualification"][:1],
            *[self.slots["qualification"][n : n + 10] for n in range(1, 30, 10)],
        ]
        with self.assertRaises(ledger.LedgerError):
            self.activate()

    def test_deleted_acceptance_receipt_blocks_every_new_process(self) -> None:
        self.fill_replay()
        (Path(str(self.state) + ".reservations") / "replay-ACCEPTED.json").unlink()
        with self.assertRaises(ledger.LedgerError):
            self.charge("qualification", self.slots["qualification"][0])

    def test_next_batch_refuses_without_review_even_with_all_usable_outputs(self) -> None:
        self.body["batches"]["replay"] = [
            self.slots["replay"][:1],
            *[self.slots["replay"][n : n + 25] for n in range(1, 190, 25)],
        ]
        self.manifest.write_text(json.dumps(self.body))
        for slot in self.slots["replay"][:1]:
            self.campaign().settle(self.charge("replay", slot), "usable")
        with self.assertRaises(self.module.AwaitingReviewError):
            self.charge("replay", self.slots["replay"][1])
        campaign = self.campaign()
        proof = acceptance(campaign, "replay")
        own = campaign._state()["calls"]
        proof.update(
            batch=0,
            slots_digest=ledger.digest(self.slots["replay"][:1]),
            expected_slots=1,
            usable_slots=1,
            attempts_digest=ledger.digest(own),
        )
        campaign.accept_batch("replay", 0, proof)
        self.assertTrue(self.charge("replay", self.slots["replay"][1]))
