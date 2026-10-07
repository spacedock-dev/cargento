"""The real repeat loop measures semantic failures without retrying their slots.

Cheap loop controls replace source admission and producer execution only. The
classifier, rubric, summaries, charged wrapper and persisted checkpoints are real.
They do not establish native campaign/account integration or model accuracy.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import abstention_ledger
import mark_abstention
import score_abstention as scorer

if TYPE_CHECKING:
    from tests import test_analyze_campaign as campaign_fixture
    from tests import test_qualification_conditional_priority as native_fixture
else:
    import test_analyze_campaign as campaign_fixture
    import test_qualification_conditional_priority as native_fixture


class _LoopCampaign:
    def __init__(self, *, legacy: bool, roles: dict[str, str]) -> None:
        self.stop_on_semantic_failure = legacy
        self.pause_after: int | None = None
        self.completed = 0
        self.stopped_reason = ""
        self.manifest = {
            "slots": {"qualification": [f"{cid}:r{r}" for r in (1, 2, 3) for cid in roles]},
            "batches": {"qualification": [[f"{next(iter(roles))}:r1"]]},
            "qualification_kinds": roles,
        }

    def review_pending(self, _lane: str, _slot: str) -> bool:
        return self.pause_after is not None and self.completed >= self.pause_after

    def stop(self, reason: str) -> None:
        self.stopped_reason = reason


class _LoopLedger:
    """A boundary double; it never reads or writes a production spend account."""

    def __init__(self, campaign: _LoopCampaign, path: Path) -> None:
        self.campaign = campaign
        self.path = str(path)
        self.cap = 31
        self.charges = 0
        self.refuse_finish = False

    def charge(self, _case_id: str, **_kwargs: Any) -> str:
        self.charges += 1
        return f"charge-{self.charges}"

    def settle(self, _charge: str, _status: str) -> None:
        pass

    def finish_exposure(self, _charge: str, _classification: str) -> None:
        if self.refuse_finish:
            raise abstention_ledger.LedgerError("test settlement refusal")
        self.campaign.completed += 1

    def record_run(self, _digest: str) -> None:
        pass

    def used(self) -> int:
        return self.charges


class SemanticMeasurementLoop(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.ids = [f"{n:016x}" for n in range(1, 11)]
        kinds = (*scorer.KINDS, *scorer.PASSING_CHECK_ADVERSARIES)
        self.roles = dict(zip(self.ids, kinds, strict=True))
        marks = {cid: {"goal": "abstain", "line_1": "abstain"} for cid in self.ids}
        self.cases: dict[str, dict[str, Any]] = {
            cid: {
                "id": cid,
                "origin": "recorded" if n < 5 else "synthetic",
                "row_snapshot": {},
                "producer_facts": [],
                "captured_at": 100.0,
            }
            for n, cid in enumerate(self.ids)
        }
        rubric = {
            cid: {
                "kind": scorer.KINDS[n % 5],
                "harness": "claude",
                "origin": self.cases[cid]["origin"],
                "expect": {name: {"result": "unverifiable", "cites": []} for name in marks[cid]},
            }
            for n, cid in enumerate(self.ids)
        }
        self.corpus = scorer.Corpus(
            cases={"v": 5, "closure_kinds": self.roles},
            marks={"marks": marks},
            marks_bytes=json.dumps(marks).encode(),
            rubric={"cases": rubric},
        )
        self.bad_slots = {(self.ids[0], 1)}
        self.technical = ""
        self.technical_slot: tuple[str, int] | None = None
        self.source_error = False
        self.transport_status: dict[str, str] = {}

    def execute(
        self, ledger: Any, resume: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        def produce(
            _config: Any,
            case: dict[str, Any],
            _row: Any,
            _facts: Any,
            mark: dict[str, str],
            *,
            model: Any,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            withheld = ""
            technical = (
                self.technical
                if self.technical_slot is None or self.technical_slot == (case["id"], model.repeat)
                else ""
            )
            if technical == "coverage":
                withheld = "no-source"
            else:
                model(case["id"], output_cap_bytes=1024)
                if technical:
                    withheld = "model-failed" if technical == "unusable" else technical
            result = (
                "consistent with the evidence read"
                if (case["id"], model.repeat) in self.bad_slots
                else "not verifiable from available evidence"
            )
            criteria = {name: {"result": result, "cites": ["f1"]} for name in mark}
            return {
                "id": case["id"],
                "harness": "claude",
                "reached_model": not bool(withheld),
                "withheld": withheld,
                "constraints": tuple(mark),
                "marks": mark,
                "criteria": criteria,
                "outcomes": {
                    name: scorer.outcome(value, withheld) for name, value in criteria.items()
                },
            }

        result_path = self.root / "local.json"
        printed = io.StringIO()
        with (
            mock.patch.object(scorer, "_evidence_bearing", return_value=True),
            mock.patch.object(
                scorer,
                "_production_source",
                side_effect=mark_abstention.FreezeError("test unsealed source")
                if self.source_error
                else None,
            ),
            mock.patch.object(mark_abstention, "case_revision", return_value={}),
            mock.patch.object(scorer, "_tool_output", return_value=None),
            mock.patch.object(scorer, "score_case", side_effect=produce),
            mock.patch.object(abstention_ledger, "chain_of", return_value={"calls": 0})
            if isinstance(ledger, _LoopLedger)
            else contextlib.nullcontext(),
            contextlib.redirect_stdout(printed),
        ):
            code = scorer._score_repeated(
                self.corpus,
                self.cases,
                ledger,
                config=None,
                model=lambda prompt, **_kwargs: ("{}", self.transport_status.get(prompt, "ok")),
                results_path=str(result_path),
                summary_path=str(self.root / "summary.json"),
                now=100.0,
                binding={"producer": "claude"},
                tool_destination=None,
                resume=resume,
            )
        self.last_output = printed.getvalue()
        return code, json.loads(result_path.read_bytes()) if result_path.exists() else {}

    def ledger(self, *, legacy: bool = False) -> _LoopLedger:
        return _LoopLedger(
            _LoopCampaign(legacy=legacy, roles=self.roles), self.root / "ledger.json"
        )

    def test_semantic_first_slot_keeps_failure_and_measures_all_thirty(self) -> None:
        # Restoring either unconditional semantic stop must strand the other 29 slots.
        code, local = self.execute(self.ledger())
        self.assertEqual(1, code)
        self.assertEqual("failed", local["summary"]["verdict"])
        self.assertFalse(local["summary"]["stopped"])
        self.assertEqual(30, local["summary"]["counts"]["registered_exposures"])
        self.assertEqual("semantic-failed", local["attempts"][0]["classification"])
        self.assertEqual(29, sum(a["classification"] == "usable" for a in local["attempts"]))
        self.assertEqual("false-reassurance", local["attempts"][0]["rubric"]["judgement"]["goal"])
        self.assertTrue(all(not attempt["retry"] for attempt in local["attempts"]))

    def test_batch_pause_checkpoint_resumes_without_retrying_terminal_failure(self) -> None:
        ledger = self.ledger()
        ledger.campaign.pause_after = 1
        _code, checkpoint = self.execute(ledger)
        self.assertEqual(1, len(checkpoint["attempts"]))
        self.assertTrue(checkpoint["summary"]["stopped"])
        ledger.campaign.pause_after = None
        code, complete = self.execute(ledger, checkpoint)
        self.assertEqual(1, code)
        self.assertEqual(30, len(complete["attempts"]))
        self.assertEqual(checkpoint["attempts"][0], complete["attempts"][0])
        self.assertEqual(30, complete["summary"]["counts"]["attempts"])
        self.assertFalse(complete["summary"]["stopped"])
        _code, repeated_resume = self.execute(ledger, complete)
        self.assertEqual(complete["attempts"], repeated_resume["attempts"])
        self.assertEqual(30, repeated_resume["summary"]["spend"]["charged"])

    def test_later_semantic_failures_preserve_all_registered_measurements(self) -> None:
        self.bad_slots = {(self.ids[4], 2), (self.ids[9], 3)}
        code, local = self.execute(self.ledger())
        self.assertEqual(1, code)
        self.assertEqual("failed", local["summary"]["verdict"])
        self.assertEqual(30, len(local["attempts"]))
        self.assertEqual(
            [(self.ids[4], 2), (self.ids[9], 3)],
            [
                (attempt["id"], attempt["repeat"])
                for attempt in local["attempts"]
                if attempt["classification"] == "semantic-failed"
            ],
        )

    def test_unsealed_source_refuses_before_any_exposure(self) -> None:
        self.source_error = True
        ledger = self.ledger()
        code, local = self.execute(ledger)
        self.assertEqual(2, code)
        self.assertEqual({}, local)
        self.assertEqual(0, ledger.used())

    def test_passing_measurement_retains_strict_accuracy_verdict(self) -> None:
        self.bad_slots = set()
        code, local = self.execute(self.ledger())
        self.assertEqual(0, code)
        self.assertEqual("passed", local["summary"]["verdict"])
        self.assertEqual(30, len(local["attempts"]))
        self.assertTrue(all(a["classification"] == "usable" for a in local["attempts"]))

    def test_legacy_campaign_stops_and_resume_makes_no_more_attempts(self) -> None:
        ledger = self.ledger(legacy=True)
        code, stopped = self.execute(ledger)
        self.assertEqual(1, code)
        self.assertEqual(1, len(stopped["attempts"]))
        self.assertTrue(stopped["summary"]["stopped"])
        _code, resumed = self.execute(ledger, stopped)
        self.assertEqual(stopped["attempts"], resumed["attempts"])

    def test_coverage_failure_stops_measurement_and_resume(self) -> None:
        self.technical = "coverage"
        ledger = self.ledger()
        _code, stopped = self.execute(ledger)
        self.assertEqual(1, len(stopped["attempts"]))
        self.assertEqual("coverage-failed", stopped["attempts"][0]["classification"])
        self.assertTrue(stopped["summary"]["stopped"])
        _code, resumed = self.execute(ledger, stopped)
        self.assertEqual(stopped["attempts"], resumed["attempts"])

    def test_unusable_opening_has_no_retry(self) -> None:
        self.technical = "unusable"
        _code, stopped = self.execute(self.ledger())
        self.assertEqual(1, len(stopped["attempts"]))
        self.assertEqual("unusable", stopped["attempts"][0]["classification"])
        self.assertTrue(stopped["summary"]["stopped"])

    def test_settlement_refusal_still_stops_measurement(self) -> None:
        ledger = self.ledger()
        ledger.refuse_finish = True
        _code, stopped = self.execute(ledger)
        self.assertEqual(1, len(stopped["attempts"]))
        self.assertTrue(stopped["summary"]["stopped"])

    def test_unsafe_second_exposure_latches_protection_without_retry_or_resume(self) -> None:
        self.bad_slots = set()
        self.technical_slot = (self.ids[1], 1)
        for status in ("unstopped", "oversized"):
            with self.subTest(status=status):
                self.technical = status
                ledger = self.ledger()
                code, stopped = self.execute(ledger)
                self.assertEqual(2, code)
                self.assertEqual("blocked", stopped["summary"]["verdict"])
                self.assertEqual(2, len(stopped["attempts"]))
                unsafe = stopped["attempts"][1]
                self.assertEqual(status, unsafe["withheld"])
                self.assertEqual("protection-failed", unsafe["classification"])
                self.assertEqual("protection-failed", ledger.campaign.stopped_reason)
                self.assertFalse(unsafe["retry"])
                self.assertTrue(stopped["summary"]["stopped"])
                _code, resumed = self.execute(ledger, stopped)
                self.assertEqual(stopped["attempts"], resumed["attempts"])

    def test_legacy_unsafe_classification_and_registered_retry_are_unchanged(self) -> None:
        self.bad_slots = set()
        self.technical = "unstopped"
        self.technical_slot = (self.ids[1], 1)
        ledger = self.ledger(legacy=True)
        code, local = self.execute(ledger)
        self.assertEqual(2, code)
        self.assertEqual(3, len(local["attempts"]))
        self.assertEqual(
            ["usable", "unusable", "unusable"], [a["classification"] for a in local["attempts"]]
        )
        self.assertEqual([False, False, True], [a["retry"] for a in local["attempts"]])
        self.assertEqual("", ledger.campaign.stopped_reason)

    def test_generic_failure_classification_cannot_resume_measurement(self) -> None:
        self.bad_slots = set()
        ledger = self.ledger()
        with mock.patch.object(scorer, "_repeat_classification", return_value="protection-failed"):
            _code, stopped = self.execute(ledger)
            self.assertEqual(1, len(stopped["attempts"]))
            _code, resumed = self.execute(ledger, stopped)
        self.assertEqual(stopped["attempts"], resumed["attempts"])


class NativeSemanticMeasurement(unittest.TestCase):
    @staticmethod
    def bind_kind_registry(fixture: Any, loop: SemanticMeasurementLoop) -> None:
        # The guard fixture has slot authority but no scorer kind registry.
        # Add it prospectively and bind every test-only carrier before activation.
        fixture.manifest["qualification_kinds"] = loop.roles
        fixture.binding = abstention_ledger.digest(
            {
                key: value
                for key, value in fixture.manifest.items()
                if key not in ("phase", "activation_anchor")
            }
        )
        fixture.next_path.write_text(json.dumps(fixture.manifest))
        fixture.grant["conditional_priority_allowance"]["campaign_binding"] = fixture.binding
        fixture.native_fixture.grant_paths[8].write_text(json.dumps(fixture.grant))
        fixture.handoff["successor"].update(
            manifest_digest=fixture.binding, grant_digest=abstention_ledger.digest(fixture.grant)
        )
        fixture.write_handoff()

    def test_real_ninth_campaign_reviews_resume_thirty_terminal_slots(self) -> None:
        # Build the expensive paid predecessor once, then use distinct clones
        # for semantic measurement and unsafe transport. All paths are temporary.
        import analyze_campaign  # noqa: PLC0415

        fixture_type = native_fixture.QualificationConditionalPriority
        fixture_type.setUpClass()
        self.addCleanup(fixture_type.doClassCleanups)
        fixture = fixture_type()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        loop = SemanticMeasurementLoop()
        self.addCleanup(loop.doCleanups)
        loop.setUp()
        self.bind_kind_registry(fixture, loop)
        campaign = fixture.activate()
        ledger = fixture.native(campaign)
        resume = None
        # Producer/source admission is doubled above; this seam binds its
        # deterministic test request to the fixture's preregistered request.
        # Native charge, classification settlement, review and resume are real.
        with mock.patch.object(analyze_campaign, "request_digest", return_value="a" * 64):
            for batch in range(len(campaign.manifest["batches"]["qualification"])):
                code, local = loop.execute(ledger, resume)
                self.assertEqual(1, code, loop.last_output)
                self.assertEqual("failed", local["summary"]["verdict"])
                if batch + 1 < len(campaign.manifest["batches"]["qualification"]):
                    self.assertTrue(local["summary"]["stopped"])
                campaign.review_batch("qualification", batch, fixture.measurement(campaign, batch))
                resume = local
        self.assertIsNotNone(resume)
        assert resume is not None
        self.assertEqual(30, len(resume["attempts"]))
        self.assertEqual(68, ledger.used())
        self.assertFalse(resume["summary"]["stopped"])
        self.assertEqual("semantic-failed", resume["attempts"][0]["classification"])
        self.assertEqual(29, sum(a["classification"] == "usable" for a in resume["attempts"]))
        self.assertTrue(all(not a["retry"] for a in resume["attempts"]))
        self.assertEqual("semantic-failed", fixture.previous._state()["calls"][-1]["status"])
        self.assertEqual(fixture.old_state, fixture.previous._state())
        with self.assertRaises(abstention_ledger.LedgerError):
            campaign.accept("qualification", campaign_fixture.acceptance(campaign, "qualification"))
        with self.assertRaises(abstention_ledger.LedgerError):
            ledger.charge(loop.ids[0], retry=True, request_binding="a" * 64)
        self.assertEqual(68, ledger.used())

        fixture.doCleanups()
        self.assert_unsafe_transport_stop(fixture_type)

    def assert_unsafe_transport_stop(self, fixture_type: type[Any]) -> None:
        import analyze_campaign  # noqa: PLC0415

        unsafe_fixture = fixture_type()
        self.addCleanup(unsafe_fixture.doCleanups)
        unsafe_fixture.setUp()
        unsafe_loop = SemanticMeasurementLoop()
        self.addCleanup(unsafe_loop.doCleanups)
        unsafe_loop.setUp()
        unsafe_loop.bad_slots = set()
        unsafe_loop.technical = "unstopped"
        unsafe_loop.technical_slot = (unsafe_loop.ids[1], 1)
        unsafe_loop.transport_status = {unsafe_loop.ids[1]: "unstopped"}
        self.bind_kind_registry(unsafe_fixture, unsafe_loop)
        unsafe_campaign = unsafe_fixture.activate()
        unsafe_ledger = unsafe_fixture.native(unsafe_campaign)
        with mock.patch.object(analyze_campaign, "request_digest", return_value="a" * 64):
            _code, opening = unsafe_loop.execute(unsafe_ledger)
            self.assertEqual(1, len(opening["attempts"]))
            unsafe_campaign.review_batch(
                "qualification", 0, unsafe_fixture.measurement(unsafe_campaign, 0)
            )
            code, stopped = unsafe_loop.execute(unsafe_ledger, opening)
            self.assertEqual(2, code)
            self.assertEqual("blocked", stopped["summary"]["verdict"])
            self.assertEqual(2, len(stopped["attempts"]))
            self.assertEqual("unstopped", stopped["attempts"][-1]["withheld"])
            self.assertEqual("protection-failed", stopped["attempts"][-1]["classification"])
            state = unsafe_campaign._state()
            self.assertEqual("protection-failed", state["stop"])
            self.assertEqual(["usable", "unusable"], [call["status"] for call in state["calls"]])
            self.assertEqual(
                "failed", abstention_ledger.read(unsafe_ledger.path)["calls"][-1]["status"]
            )
            settlement = unsafe_campaign.receipts / (state["calls"][-1]["id"] + "-SETTLED.json")
            settled_bytes = settlement.read_bytes()
            self.assertEqual("unusable", json.loads(settled_bytes)["status"])
            _code, resumed = unsafe_loop.execute(unsafe_ledger, stopped)
            self.assertEqual(stopped["attempts"], resumed["attempts"])
            self.assertEqual(settled_bytes, settlement.read_bytes())
        with self.assertRaises(abstention_ledger.LedgerError):
            unsafe_ledger.charge(unsafe_loop.ids[1], retry=True, request_binding="a" * 64)
        self.assertEqual(40, unsafe_ledger.used())
        self.assertEqual(unsafe_fixture.old_state, unsafe_fixture.previous._state())
