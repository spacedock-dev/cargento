"""One finite login recovery keeps both stopped campaigns and every charge."""

from __future__ import annotations

import copy
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
    from collections.abc import Callable

    from tests import test_analyze_campaign as fixtures
    from tests import test_qualification_successor as predecessors
else:
    import test_analyze_campaign as fixtures
    import test_qualification_successor as predecessors


class QualificationLoginResume(unittest.TestCase):
    def setUp(self) -> None:
        self.prior = predecessors.QualificationSuccessor()
        self.addCleanup(self.prior.doCleanups)
        self.prior.setUp()
        self.previous = self.prior.activate()
        native = self.prior.new_native(self.previous)
        first = native.charge("0000000000000001", request_binding="a" * 64)
        native.settle(first, "failed")
        second = native.charge("0000000000000001", retry=True, request_binding="a" * 64)
        native.settle(second, "failed")
        self.old_state = self.previous._state()
        self.native_prefix = ledger.read(str(self.prior.native.ledger_path))["calls"]
        self.failed = {
            "verdict": "blocked",
            "producer": "claude",
            "stopped": True,
            "counts": {"attempts": 2, "unusable_attempts": 2},
            "ledger_chain": ledger.chain_of(str(self.prior.native.ledger_path)),
            "marks_digest": self.prior.key["marks_digest"],
            "inputs_digest": self.prior.key["inputs_digest"],
        }
        self.prior.native.result_paths[4].write_text(json.dumps(self.failed))
        self.next_path = self.prior.root / "login-resume.json"
        self.handoff_path = self.prior.root / "login-handoff.json"
        for name, path in (
            ("LOGIN_RESUME_MANIFEST_PATH", self.next_path),
            ("LOGIN_RESUME_HANDOFF_PATH", self.handoff_path),
        ):
            patch = mock.patch.object(campaigns, name, str(path), create=True)
            patch.start()
            self.addCleanup(patch.stop)
        self.manifest = copy.deepcopy(self.prior.next_manifest)
        self.manifest.update(phase="prepared")
        self.manifest.pop("activation_anchor", None)
        self.manifest["bindings"]["qualification"] = "e" * 64
        self.next_path.write_text(json.dumps(self.manifest))
        self.binding = ledger.digest(
            {k: v for k, v in self.manifest.items() if k not in ("phase", "activation_anchor")}
        )
        self.key = {"cases_digest": "e" * 64, "marks_digest": "f" * 64, "inputs_digest": "1" * 64}
        self.model_key = "3" * 64
        self.grant: dict[str, Any] = {
            "v": 1,
            "phase": "sealed",
            "previous": {
                k: self.failed[k] for k in ("ledger_chain", "marks_digest", "inputs_digest")
            },
            "next": self.key,
            "login_resume_allowance": {
                "previous_calls": 32,
                "additional_calls": 31,
                "carried_calls": 29,
                "renewed_calls": 2,
                "repeats": 3,
                "retry_calls": 1,
                "model_binding": self.model_key,
                "campaign_binding": self.binding,
            },
        }
        self.prior.native.grant_paths[5].write_text(json.dumps(self.grant))
        root_state = self.prior.parent._state()
        self.handoff: dict[str, Any] = {
            "v": 1,
            "verdict": "GO",
            "prepared_by": "synthetic-operator",
            "reviewed_by": "independent-synthetic-reviewer",
            "parent": {
                "manifest_digest": self.previous.binding,
                "activation_anchor": self.previous.manifest["activation_anchor"],
                "handoff_digest": self.previous.handoff_digest,
                "state_digest": ledger.digest(self.old_state),
                "original_digest": ledger.digest(
                    {k: v for k, v in root_state.items() if k != "epochs"}
                ),
                "calls": 2,
                "calls_digest": ledger.digest(self.old_state["calls"]),
                "stop_proof": {
                    "kind": "two-consecutive-unusable",
                    "settlements_digest": ledger.digest(
                        [
                            json.loads(
                                (self.previous.receipts / (c["id"] + "-SETTLED.json")).read_text()
                            )
                            for c in self.old_state["calls"]
                        ]
                    ),
                },
                "failed_result_digest": ledger.digest(self.failed),
                "native_calls": 32,
                "native_calls_digest": ledger.digest(self.native_prefix),
                "native_chain": self.failed["ledger_chain"],
            },
            "successor": {
                "manifest_digest": self.binding,
                "grant_digest": ledger.digest(self.grant),
                "evidence": self.manifest["evidence"]["qualification"],
                "cases_digest": self.key["cases_digest"],
                "inputs_digest": self.key["inputs_digest"],
                "model_binding": self.model_key,
                "additional_calls": 31,
                "carried_calls": 29,
                "renewed_calls": 2,
                "shared_total": 243,
                "native_total": 63,
            },
        }
        self.write_handoff()

    def write_handoff(self) -> None:
        self.handoff_path.write_text(json.dumps(self.handoff))

    def current(self) -> Any:
        self.assertTrue(
            hasattr(campaigns, "LoginResumeCampaign"), "login recovery authority is absent"
        )
        return campaigns.LoginResumeCampaign()

    def activate(self) -> Any:
        anchor = self.current().initialize_successor()
        self.manifest.update(phase="sealed", activation_anchor=anchor)
        self.next_path.write_text(json.dumps(self.manifest))
        return self.current()

    def native(self, current: Any) -> ledger.Ledger:
        return ledger.Ledger(
            str(self.prior.native.ledger_path),
            cap=63,
            producer="claude",
            **self.key,
            model_binding=self.model_key,
            campaign=current,
        )

    def test_recovery_preserves_two_stops_and_charges_before_opening(self) -> None:
        current = self.activate()
        native = self.native(current)
        self.assertEqual(63, native.cap)
        self.assertEqual(61, self.prior.new_native(self.previous).cap)
        self.assertEqual(self.old_state, self.previous._state())
        with self.assertRaisesRegex(ledger.LedgerError, "two consecutive"):
            self.previous.reserve("qualification", "0000000000000001:r1", "a" * 64, retry=True)
        charge = native.charge("0000000000000001", request_binding="a" * 64)
        self.assertEqual(33, native.used())
        self.assertEqual(1, len(current._state()["calls"]))
        self.assertEqual(self.native_prefix, ledger.read(native.path)["calls"][:32])
        native.settle(charge, "ok")
        native.finish_exposure(charge, "usable")
        with self.assertRaises(campaigns.AwaitingReviewError):
            native.charge("0000000000000002", request_binding="a" * 64)
        self.assertIsInstance(campaigns.active_campaign(), campaigns.LoginResumeCampaign)

    def test_current_allowance_is_only_29_carried_plus_2_renewed(self) -> None:
        current = self.activate()
        native = self.native(current)
        slots = current.manifest["slots"]["qualification"]
        first = native.charge(slots[0].split(":")[0], request_binding="a" * 64)
        native.settle(first, "failed")
        for index, group in enumerate(current.manifest["batches"]["qualification"]):
            for slot in group:
                cid, repeat = slot.split(":r")
                charge = native.charge(
                    cid, repeat=int(repeat), retry=slot == slots[0], request_binding="a" * 64
                )
                native.settle(charge, "ok")
                native.finish_exposure(charge, "usable")
            current.accept_batch(
                "qualification", index, fixtures.acceptance(current, "qualification", index)
            )
        self.assertEqual(63, native.used())
        self.assertEqual(31, len(current._state()["calls"]))
        self.assertEqual(243, 4 + 31 + 190 + 18)
        with self.assertRaises(ledger.SpendCapError):
            native.charge("0000000000000001", request_binding="a" * 64)
        for lane in ("replay", "live"):
            with self.subTest(lane=lane), self.assertRaises(ledger.LedgerError):
                current.reserve(lane, current.manifest["slots"][lane][0], "a" * 64)

    def test_wrong_grant_ancestry_and_reallocation_refuse(self) -> None:
        original = copy.deepcopy(self.grant)
        for field, bad in (
            ("previous_calls", 31),
            ("carried_calls", 30),
            ("renewed_calls", 3),
            ("additional_calls", 60),
            ("retry_calls", True),
        ):
            with self.subTest(field=field):
                body = copy.deepcopy(original)
                body["login_resume_allowance"][field] = bad
                self.prior.native.grant_paths[5].write_text(json.dumps(body))
                with self.assertRaises(ledger.LedgerError):
                    ledger.continuation()
        self.prior.native.grant_paths[5].write_text(json.dumps(original))
        for verdict in ("passed", "failed"):
            with self.subTest(verdict=verdict):
                self.failed["verdict"] = verdict
                self.prior.native.result_paths[4].write_text(json.dumps(self.failed))
                with self.assertRaises(ledger.LedgerError):
                    ledger.continuation()

    def test_deletion_reinitialization_and_rewritten_prefix_refuse(self) -> None:
        current = self.activate()
        with self.assertRaises(ledger.LedgerError):
            current.initialize_successor()
        original = self.prior.account.state.read_bytes()
        mutations: tuple[Callable[[dict[str, Any]], Any], ...] = (
            lambda b: b["epochs"].pop(0),
            lambda b: b["epochs"].pop(),
            lambda b: b["epochs"][0]["state"]["calls"].clear(),
            lambda b: b["calls"][0].update(at=123.0),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                body = json.loads(original)
                mutation(body)
                self.prior.account.state.write_text(json.dumps(body))
                with self.assertRaises(ledger.LedgerError):
                    current.reserve("qualification", "0000000000000001:r1", "a" * 64)
                self.prior.account.state.write_bytes(original)
        self.handoff_path.unlink()
        with self.assertRaises(ledger.LedgerError):
            campaigns.active_campaign()

    def test_two_new_unusable_attempts_stop_without_refunding_any_epoch(self) -> None:
        current = self.activate()
        native = self.native(current)
        first = native.charge("0000000000000001", request_binding="a" * 64)
        native.settle(first, "failed")
        second = native.charge("0000000000000001", retry=True, request_binding="a" * 64)
        native.settle(second, "failed")
        with self.assertRaisesRegex(ledger.LedgerError, "two consecutive"):
            native.charge("0000000000000002", request_binding="a" * 64)
        self.assertEqual(34, native.used())
        self.assertEqual(self.old_state, self.previous._state())

    def test_same_packet_model_identity_still_needs_the_new_campaign_for_63(self) -> None:
        self.key = self.prior.key
        self.model_key = self.prior.native.model_key
        self.grant["next"] = self.key
        self.grant["login_resume_allowance"]["model_binding"] = self.model_key
        self.prior.native.grant_paths[5].write_text(json.dumps(self.grant))
        self.handoff["successor"].update(
            grant_digest=ledger.digest(self.grant),
            cases_digest=self.key["cases_digest"],
            inputs_digest=self.key["inputs_digest"],
            model_binding=self.model_key,
        )
        self.write_handoff()
        current = self.activate()
        self.assertEqual(63, self.native(current).cap)
        self.assertEqual(61, self.prior.new_native(self.previous).cap)
