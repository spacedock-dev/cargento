"""A reviewed zero-charge reseal preserves genesis provenance and all paid states."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import abstention_ledger as ledger
import analyze_campaign as campaigns

if TYPE_CHECKING:
    from tests import test_qualification_clause_continuation as predecessors
else:
    import test_qualification_clause_continuation as predecessors


class QualificationZeroReseal(unittest.TestCase):
    def setUp(self) -> None:
        self.prior = predecessors.QualificationClauseContinuation()
        self.addCleanup(self.prior.doCleanups)
        self.prior.setUp()
        self.review_path = self.prior.root / "zero-reseal-review.json"
        patch = mock.patch.object(
            campaigns, "CLAUSE_ZERO_RESEAL_PATH", str(self.review_path), create=True
        )
        patch.start()
        self.addCleanup(patch.stop)
        self.initial = self.prior.activate()
        self.initial_root = copy.deepcopy(self.initial._parent_state())
        self.initial_epoch = copy.deepcopy(self.initial._state())
        self.transition = self.initial.epoch_dir / "TRANSITION.json"
        self.original_transition = self.transition.read_bytes()
        self.native_path = self.prior.native_fixture.ledger_path
        self.original_native = self.native_path.read_bytes()
        self.original_manifest = copy.deepcopy(self.prior.manifest)
        self.original_grant = copy.deepcopy(self.prior.grant)
        self.original_handoff = copy.deepcopy(self.prior.handoff)
        self.public_review: dict[str, Any] = {}

    def prepare(self) -> None:
        self.prior.manifest.update(phase="prepared")
        self.prior.manifest.pop("activation_anchor")
        self.prior.manifest["evidence"]["qualification"]["source"] = "b" * 64
        binding = ledger.digest(
            {
                k: v
                for k, v in self.prior.manifest.items()
                if k not in ("phase", "activation_anchor")
            }
        )
        self.prior.binding = binding
        self.prior.grant["clause_continuation_allowance"]["campaign_binding"] = binding
        self.prior.native_fixture.grant_paths[6].write_text(json.dumps(self.prior.grant))
        self.prior.next_path.write_text(json.dumps(self.prior.manifest))
        self.prior.handoff["successor"].update(
            manifest_digest=binding,
            grant_digest=ledger.digest(self.prior.grant),
            evidence=self.prior.manifest["evidence"]["qualification"],
        )
        self.prior.write_handoff()
        new_state = {
            "v": 1,
            "manifest_digest": binding,
            "calls": [],
            "genesis_nonce": "f" * 32,
        }
        self.public_review = {
            "v": 1,
            "verdict": "GO",
            "prepared_by": "operator",
            "reviewed_by": "independent-reviewer",
            "parent": self.original_handoff["parent"],
            "before": {
                "manifest_digest": self.initial.binding,
                "grant_digest": ledger.digest(self.original_grant),
                "handoff_digest": self.initial.handoff_digest,
                "activation_anchor": ledger.digest(self.initial_epoch),
                "transition_sha256": hashlib.sha256(self.original_transition).hexdigest(),
                "epoch": self.initial_root["epochs"][2],
            },
            "after": {
                "manifest_digest": binding,
                "grant_digest": ledger.digest(self.prior.grant),
                "handoff_digest": ledger.digest(self.prior.handoff),
                "activation_anchor": ledger.digest(new_state),
                "epoch": {
                    "id": 3,
                    "handoff_digest": ledger.digest(self.prior.handoff),
                    "state": new_state,
                },
            },
        }
        self.review_path.write_text(json.dumps(self.public_review))

    def reseal(self) -> str:
        self.assertTrue(
            hasattr(campaigns.ClauseContinuationCampaign, "reseal_zero_charge"),
            "one-time zero-charge reseal is absent",
        )
        return campaigns.ClauseContinuationCampaign().reseal_zero_charge()

    def complete(self) -> campaigns.ClauseContinuationCampaign:
        self.prepare()
        anchor = self.reseal()
        self.prior.manifest.update(phase="sealed", activation_anchor=anchor)
        self.prior.next_path.write_text(json.dumps(self.prior.manifest))
        return campaigns.ClauseContinuationCampaign()

    def test_zero_reseal_preserves_original_transition_paid_states_and_charges(self) -> None:
        current = self.complete()
        self.assertEqual(self.original_transition, self.transition.read_bytes())
        self.assertEqual(self.original_native, self.native_path.read_bytes())
        root = current._parent_state()
        self.assertEqual(self.initial_root["epochs"][:2], root["epochs"][:2])
        self.assertEqual(self.initial_root["calls"], root["calls"])
        self.assertEqual([], current._state()["calls"])
        self.assertTrue((current.epoch_dir / "RESEAL.json").is_file())
        native = self.prior.native(current)
        charge = native.charge("0000000000000001", request_binding="a" * 64)
        native.settle(charge, "ok")
        native.finish_exposure(charge, "usable")
        self.assertEqual(35, native.used())
        self.assertEqual(1, len(current._state()["calls"]))
        self.assertEqual(self.original_transition, self.transition.read_bytes())

    def test_without_a_reseal_record_legacy_zero_genesis_still_reads(self) -> None:
        self.assertEqual([], self.initial._state()["calls"])
        self.assertFalse(self.review_path.exists())

    def test_public_review_does_not_implicitly_reseal_or_initialize(self) -> None:
        self.prepare()
        current = self.prior.current()
        with self.assertRaises(ledger.LedgerError):
            current._state()
        self.assertEqual(self.original_transition, self.transition.read_bytes())
        self.assertFalse((current.epoch_dir / "RESEAL.json").exists())
        with self.assertRaises(ledger.LedgerError):
            current.initialize_successor()

    def test_a_second_reseal_or_deleted_receipt_cannot_rewind_the_zero_genesis(self) -> None:
        current = self.complete()
        with self.assertRaises(ledger.LedgerError):
            current.reseal_zero_charge()
        (current.epoch_dir / "RESEAL.json").unlink()
        with self.assertRaises(ledger.LedgerError):
            current._state()
        with self.assertRaises(ledger.LedgerError):
            current.reseal_zero_charge()

    def test_attempted_epoch_or_orphan_reservation_cannot_be_resealed(self) -> None:
        native = self.prior.native(self.initial)
        charge = native.charge("0000000000000001", request_binding="a" * 64)
        native.settle(charge, "ok")
        native.finish_exposure(charge, "usable")
        self.prepare()
        with self.assertRaises(ledger.LedgerError):
            self.reseal()
        self.assertEqual(35, native.used())
        self.assertFalse((self.initial.epoch_dir / "RESEAL.json").exists())

    def test_an_orphan_receipt_with_no_native_call_still_refuses_reseal(self) -> None:
        self.initial.receipts.mkdir()
        (self.initial.receipts / "orphan.json").write_text("{}")
        self.prepare()
        with self.assertRaises(ledger.LedgerError):
            self.reseal()
        self.assertEqual(self.original_native, self.native_path.read_bytes())

    def test_an_extra_settled_native_charge_cannot_reseal_an_empty_shared_epoch(self) -> None:
        self.prepare()
        body = json.loads(self.native_path.read_bytes())
        extra = copy.deepcopy(body["calls"][-1])
        extra.update(
            id="orphan-native-charge",
            status="ok",
            marks_digest=self.prior.key["marks_digest"],
            inputs_digest=self.prior.key["inputs_digest"],
        )
        body["calls"].append(extra)
        self.native_path.write_text(json.dumps(body))
        with self.assertRaises(ledger.LedgerError):
            self.reseal()
        self.assertFalse((self.initial.epoch_dir / "RESEAL.json").exists())

    def test_missing_account_state_or_original_transition_cannot_create_a_new_genesis(self) -> None:
        self.prepare()
        path = self.prior.prior.prior.account.state
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(ledger.LedgerError):
            self.reseal()
        path.write_bytes(original)
        self.transition.unlink()
        with self.assertRaises(ledger.LedgerError):
            self.reseal()
        self.assertFalse((self.initial.epoch_dir / "RESEAL.json").exists())

    def test_any_zero_epoch_acceptance_stop_or_unregistered_file_refuses(self) -> None:
        self.prepare()
        path = self.prior.prior.prior.account.state
        original = path.read_bytes()
        for field, value in (("accepted", {}), ("accepted_batches", {}), ("stop", None)):
            with self.subTest(field=field):
                body = json.loads(original)
                body["epochs"][2]["state"][field] = value
                path.write_text(json.dumps(body))
                with self.assertRaises(ledger.LedgerError):
                    self.reseal()
                path.write_bytes(original)
        stray = self.initial.epoch_dir / "STOP.json"
        stray.write_text("{}")
        with self.assertRaises(ledger.LedgerError):
            self.reseal()

    def test_changed_original_transition_or_review_binding_refuses(self) -> None:
        self.prepare()
        self.transition.write_bytes(self.original_transition + b"\n")
        with self.assertRaises(ledger.LedgerError):
            self.reseal()
        self.transition.write_bytes(self.original_transition)
        for field in ("manifest_digest", "grant_digest", "handoff_digest", "activation_anchor"):
            with self.subTest(field=field):
                body = copy.deepcopy(self.public_review)
                body["after"][field] = "0" * 64
                self.review_path.write_text(json.dumps(body))
                with self.assertRaises(ledger.LedgerError):
                    self.reseal()
        body = copy.deepcopy(self.public_review)
        body["reviewed_by"] = body["prepared_by"]
        self.review_path.write_text(json.dumps(body))
        with self.assertRaises(ledger.LedgerError):
            self.reseal()

    def test_missing_fixed_review_private_receipt_and_partial_receipt_fail_closed(self) -> None:
        current = self.complete()
        self.review_path.unlink()
        with self.assertRaises(ledger.LedgerError):
            current._state()
        self.review_path.write_text(json.dumps(self.public_review))
        receipt = current.epoch_dir / "RESEAL.json"
        receipt.write_text("{")
        with self.assertRaises(ledger.LedgerError):
            current._state()

    def test_private_receipt_must_match_the_independent_fixed_review(self) -> None:
        current = self.complete()
        path = current.epoch_dir / "RESEAL.json"
        receipt = json.loads(path.read_bytes())
        receipt["review_digest"] = "0" * 64
        path.write_text(json.dumps(receipt))
        with self.assertRaises(ledger.LedgerError):
            current._state()

    def test_interruption_after_receipt_before_account_write_never_activates_or_retries(
        self,
    ) -> None:
        self.prepare()
        with (
            mock.patch.object(ledger, "_write", side_effect=OSError("scratch interruption")),
            self.assertRaises(OSError),
        ):
            self.reseal()
        current = self.prior.current()
        self.assertTrue((current.epoch_dir / "RESEAL.json").exists())
        self.assertEqual(self.original_transition, self.transition.read_bytes())
        with self.assertRaises(ledger.LedgerError):
            current._state()
        with self.assertRaises(ledger.LedgerError):
            current.reseal_zero_charge()


if __name__ == "__main__":
    unittest.main()
