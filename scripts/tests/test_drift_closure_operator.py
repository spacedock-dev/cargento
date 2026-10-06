"""Actual native closure attempts stop and resume without invented observations."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib
import json
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import abstention_ledger as authority
import analyze_campaign as campaigns
import drift_closure_grading as grading
import drift_replay as replay
import drift_study_controls as controls
import levels_cases as level_cases
import score_abstention

if TYPE_CHECKING:
    from tests import test_analyze_campaign as campaign_cases
    from tests import test_drift_replay as replay_cases
else:
    import test_analyze_campaign as campaign_cases
    import test_drift_replay as replay_cases


class NativeOperator(unittest.TestCase):
    operator: Any
    proto: dict[str, Any]

    def setUp(self) -> None:  # noqa: PLR0915 - synthetic source and account fixture
        try:
            self.operator = importlib.import_module("drift_closure_operator")
        except ModuleNotFoundError:
            self.operator = None
        self.assertIsNotNone(self.operator, "native closure operator is missing")
        # Only temporary account paths are activated by the existing test fixture.
        self.account = campaign_cases.CampaignReservations()
        self.account.setUp()
        self.addCleanup(self.account.doCleanups)
        self.session = replay_cases._Session()
        self.session.__enter__()
        self.addCleanup(self.session.__exit__)
        self.native = replay_cases._Home(self.session)
        self.home = self.session.home
        self.paths = replay._paths(str(self.home))
        self.ledger = Path(self.paths["dir"]) / "spend.json"
        self.ledger.write_bytes(self.account.replay.read_bytes())
        self.account.replay = self.ledger
        for obj, attr, value in (
            (replay, "LEDGER_PATH", str(self.ledger)),
            (campaigns, "REPLAY_PATH", str(self.ledger)),
            (replay, "_run_refusal", lambda *_a: ""),
        ):
            patch = mock.patch.object(obj, attr, value)
            patch.start()
            self.addCleanup(patch.stop)
        config, _, _, _, self.reading = replay._runtime()
        from cargento_runtime import observer  # noqa: PLC0415 - native runtime loaded above

        self.observer = observer
        self.actual_exec = observer.claude_exec
        self.config = replay._read_model_config(config, "claude-sonnet-5")
        self.binary = self.account.root / "synthetic-cli"
        self.binary.write_bytes(b"synthetic verified CLI")
        self.verified = score_abstention.VerifiedClaude(
            "synthetic-cli",
            "synthetic-version",
            str(self.binary),
            "synthetic-signature",
            score_abstention.file_identity(str(self.binary)),
        )
        self.transport = campaigns.verified_transport_binding(self.config, self.verified, observer)
        self.body = self.native.body
        template = self.body["cases"][0]
        self.body["cases"] = [{**template, "id": f"case{n:02}"} for n in range(29)]
        Path(self.paths["cases"]).write_text(json.dumps(self.body))
        revision = {
            "goal": "Build the importer only.",
            "at": replay_cases._at(1),
            "lines": ["The importer is built."],
            "window_start": replay_cases._at(1),
        }
        Path(self.paths["current"]).write_text(
            json.dumps({"intents": {c["id"]: revision for c in self.body["cases"]}})
        )
        control = controls.control_for_row(
            {"phase": "pilot", "condition": "production"}, self.reading
        )
        selected: list[Any] = []
        build = control.module.build_prompt

        def capture(*args: Any, **kwargs: Any) -> Any:
            prompt, selection = build(*args, **kwargs)
            selected.append(selection)
            return prompt, selection

        control.module.build_prompt = capture
        self.assertEqual(
            0,
            replay.read(
                home=str(self.home),
                dry_run=True,
                tag="fixture-plan",
                cases=("case00:current",),
                arms=("current",),
                claude_model="claude-sonnet-5",
                reading_override=control.module,
                say=lambda _: None,
            ),
        )
        binding = control.bindings()
        plan = json.loads((Path(self.paths["dir"]) / "plan-fixture-plan.json").read_text())
        prompt = plan["prompts"]["case00:current"]["digest"]
        # The spy saw the actual final prompt; transport request is reconstructed transiently.
        prompts: list[str] = []

        class CaptureSpy(level_cases._Spy):
            def __call__(self, prompt: str, **kwargs: Any) -> Any:
                prompts.append(prompt)
                super().__call__(prompt, **kwargs)
                return json.dumps(
                    {
                        name: {"result": "unverifiable", "cites": [], "detail": ""}
                        for name in ("goal", "line_1", "claims")
                    }
                ), "ok"

        with mock.patch.object(level_cases, "_Spy", CaptureSpy):
            replay.read(
                home=str(self.home),
                dry_run=True,
                tag="fixture-capture",
                cases=("case00:current",),
                arms=("current",),
                claude_model="claude-sonnet-5",
                reading_override=control.module,
                say=lambda _: None,
            )
        binding = control.bindings()
        request = campaigns.request_digest(
            prompts[0],
            self.transport,
            campaigns.runtime_source_digest(Path(observer.__file__).parent),
            self.reading.REPLY_CAP_BYTES,
            shim_digest=binding["shim_sha256"],
            contract_digest=binding["contract_sha256"],
        )
        self.regs = []
        for n in range(190):
            case = self.body["cases"][n % 29]
            if n >= 87 and case["id"] == "case00":
                case = self.body["cases"][1]
            intent = next(
                i
                for i in replay.intents(
                    case,
                    replay.conversation(str(self.session.log)),
                    replay_cases.ANNOTATION,
                    {case["id"]: revision},
                )
                if i.arm == "current"
            ).revision()
            self.regs.append(
                {
                    "slot": f"replay{n:03}",
                    "claude_model": "claude-sonnet-5",
                    "row": {
                        "phase": "pilot",
                        "condition": "production",
                        "repeat": n // 29 + 1 if n < 87 or n % 29 else n + 1,
                        "case": case["id"],
                        "arm": "current",
                    },
                    "intent": intent,
                    "expected_criteria": list(
                        self.reading.constraints_for(
                            selected[0].lines, claims=selected[0].asked_claims
                        )
                    ),
                    "selected_ids": [e["id"] for e in selected[0].entries],
                    "prompt_digest": prompt,
                    "request_digest": request,
                    "source_bindings": {k: binding[k] for k in grading._SOURCE_KEYS},
                    "group": "synthetic",
                    "no_drift": False,
                    "protected_intents": [],
                    "protect_offer": False,
                    "protected_facts": (
                        {
                            f"claim{min(int(case['id'][4:]), 8)}": next(
                                e["id"] for e in selected[0].entries if e["type"] == "agent_message"
                            )
                        }
                        if int(case["id"][4:]) < 10
                        else {}
                    ),
                    "admitted_support_ids": {},
                    "blind_source_bindings": {
                        name: {
                            "source_artifact_sha256": hashlib.sha256(
                                Path(self.paths["current"]).read_bytes()
                            ).hexdigest(),
                            "saved_revision_sha256": grading.digest(intent),
                            "criterion_clause_sha256": grading.digest(
                                intent["goal"] if name == "goal" else intent["lines"][0]
                            ),
                        }
                        for name in ("goal", "line_1")
                    },
                }
            )
        self.regs[1], self.regs[29] = self.regs[29], self.regs[1]
        for n, reg in enumerate(self.regs):
            reg["slot"] = f"replay{n:03}"
        self.frozen = {
            key: self.account.root / f"{key}.json"
            for key in ("protocol", "registrations", "blind", "protected")
        }
        marks = [
            {"id": f"case{n:02}-{name}", "departure": "unclear", "neutral_safe": False}
            for n in range(29)
            for name in ("goal", "line_1")
        ]
        self.frozen["blind"].write_text(
            json.dumps({"questions": 58, "marks": marks, "marks_digest": grading.digest(marks)})
        )
        self.frozen["protected"].write_text(
            json.dumps(
                {
                    "rows": [
                        {
                            "case": f"case{n:02}",
                            "arm": "current",
                            "claim": f"claim{min(n, 8)}",
                            "old_protected": True,
                            "new_withdrawn": n < 4,
                            "admissibility": "admitted",
                        }
                        for n in range(10)
                    ]
                }
            )
        )
        self.proto = {
            "v": 4,
            "call_rows": [r["row"] for r in self.regs],
            "threshold_proposal": {
                "critical_exact_predicates": [
                    {
                        "case": "case00",
                        "arm": "current",
                        "criterion": "goal",
                        "k": 3,
                        "n": 3,
                        "phases_and_conditions": {"pilot": ["production"]},
                        "required_resolved_result": "not departure",
                    }
                ]
            },
            "critical_input_binding": {
                "cases": [
                    {
                        "case": "case00",
                        "arm": "current",
                        "saved_revision_sha256": grading.digest(self.regs[0]["intent"]),
                        "criterion_clause_sha256": {
                            "goal": grading.digest(self.regs[0]["intent"]["goal"])
                        },
                    }
                ],
                "current_intents_file_sha256": self.sha(Path(self.paths["current"])),
            },
            "input_digest_bindings": {
                "native_code_binding": self.operator.native_code_binding(),
                "scope_sort": self.sha(self.frozen["blind"]),
                "native_source_files": {
                    str(p.resolve()): self.sha(p)
                    for p in (
                        Path(self.paths["cases"]),
                        Path(self.paths["current"]),
                        self.session.log,
                        self.session.annotations / replay_cases.SID / "annotation.md",
                    )
                },
            },
        }
        from cargento_runtime.web import page  # noqa: PLC0415 - actual native projection fixture

        self.proto["input_digest_bindings"]["native_page_projection"] = grading.digest(
            {
                "node": self.sha(Path(replay._ROOT) / "scripts/drift_page.js"),
                "script": grading.digest(page.load_script()),
            }
        )
        self.seal()
        self.sends: list[str] = []

        def fake_exec(*args: Any, **_kwargs: Any) -> tuple[str, str]:
            self.sends.append(str(args))
            reply = {
                name: {"result": "unverifiable", "cites": [], "detail": ""}
                for name in self.regs[0]["expected_criteria"]
            }
            return json.dumps(reply), "ok"

        self.fake_exec = fake_exec

    @staticmethod
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def seal(self) -> None:
        self.frozen["protocol"].write_text(json.dumps(self.proto))
        self.frozen["registrations"].write_text(json.dumps(self.regs))
        report = grading.grade_frozen(
            self.frozen["protocol"].read_bytes(),
            self.frozen["registrations"].read_bytes(),
            self.frozen["blind"].read_bytes(),
            self.frozen["protected"].read_bytes(),
            {k: self.sha(self.frozen[k]) for k in ("protocol", "registrations", "protected")},
            {},
            due_slots=[],
            final=False,
            reading_module=self.reading,
        )
        self.account.body["bindings"]["replay"] = self.sha(self.frozen["protocol"])
        self.account.body["evidence"]["replay"] = report["evidence"]
        self.account.body["requests"]["replay"] = {
            r["slot"]: r["request_digest"] for r in self.regs
        }
        self.account.body["historical"]["replay"] = {
            "calls": 631,
            "sha256": self.sha(self.ledger),
            "calls_digest": authority.digest(json.loads(self.ledger.read_text())["calls"]),
        }
        self.account.activate()

    def prepare(self) -> Any:
        return self.operator.NativeClosureOperator(
            **{f"{k}_path": p for k, p in self.frozen.items()}
        )

    def execute(self, op: Any, **kwargs: Any) -> Any:
        argv_digest = score_abstention.argv_digest
        with (
            mock.patch.object(
                score_abstention,
                "verify_claude_binary",
                return_value=contextlib.nullcontext(self.verified),
            ),
            mock.patch.object(self.observer, "claude_exec", self.fake_exec),
            mock.patch.object(
                score_abstention,
                "argv_digest",
                side_effect=lambda provider, cfg, **_kw: argv_digest(
                    provider, cfg, claude_executor=self.actual_exec
                ),
            ),
        ):
            return op.run_next(claude_model="claude-sonnet-5", **kwargs)

    def review(self, op: Any, report: dict[str, Any]) -> Path:
        path = self.account.root / "independent-review.json"
        path.write_text(
            json.dumps(
                {
                    "v": 1,
                    "reviewer": "independent-reviewer",
                    "verdict": "passed",
                    "binding": op.review_binding(report, batch=0),
                }
            )
        )
        return path

    def test_actual_native_route_node_projection_and_metadata_only_resume(self) -> None:
        op = self.prepare()
        report = self.execute(op)
        self.assertEqual("passed", report["verdict"])
        self.assertEqual(1, report["observed_slots"])
        self.assertEqual(1, len(self.sends))
        self.assertEqual(632, len(json.loads(self.ledger.read_text())["calls"]))
        self.assertEqual(1, len(campaigns.Campaign()._state()["calls"]))
        journal = json.loads(op.journal_path.read_text())
        self.assertNotIn("entry", journal["attempts"][0])
        self.assertNotIn("raw_verdict", op.journal_path.read_text())
        self.assertNotIn("Build the importer", op.journal_path.read_text())
        self.assertEqual(report["report_digest"], self.prepare().grade()["report_digest"])
        with self.assertRaises(campaigns.AwaitingReviewError):
            self.execute(op)
        self.assertEqual(1, len(self.sends))
        op.accept_batch(0, self.review(op, report))
        second = self.execute(op)
        self.assertEqual(2, second["observed_slots"])
        attempts = json.loads(op.journal_path.read_text())["attempts"]
        self.assertEqual(attempts[0]["row"]["case"], attempts[1]["row"]["case"])
        self.assertEqual(attempts[0]["read_sha256"], attempts[1]["read_sha256"])
        self.assertNotEqual(attempts[0]["tag"], attempts[1]["tag"])
        self.assertNotEqual(attempts[0]["shared_id"], attempts[1]["shared_id"])
        self.assertNotEqual(attempts[0]["native_index"], attempts[1]["native_index"])

    def test_source_change_refuses_before_charge(self) -> None:
        for path in (
            self.frozen["protocol"],
            self.frozen["registrations"],
            self.frozen["blind"],
            self.frozen["protected"],
            Path(self.paths["current"]),
            self.session.log,
        ):
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaises((ValueError, authority.LedgerError)):
                self.prepare()
            path.write_bytes(original)
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_missing_joint_support_refuses_before_charge(self) -> None:
        self.proto["threshold_proposal"]["critical_exact_predicates"] = [
            {
                "case": "case00",
                "arm": "current",
                "criterion": "goal",
                "k": 3,
                "n": 3,
                "required_raw_token": "departure",
                "required_resolved_result": "departure",
                "phases_and_conditions": {"pilot": ["production"]},
            }
        ]
        self.frozen["protocol"].write_text(json.dumps(self.proto))
        self.account.body["bindings"]["replay"] = self.sha(self.frozen["protocol"])
        self.account.activate()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_first_semantic_failure_latches_stop_across_restart(self) -> None:
        op = self.prepare()

        def bad_exec(*_args: Any, **_kwargs: Any) -> tuple[str, str]:
            self.sends.append("failed semantic")
            return json.dumps(
                {
                    "goal": {"result": "not_reached", "cites": [1]},
                    "line_1": {"result": "unverifiable", "cites": []},
                    "claims": {"result": "unverifiable", "cites": []},
                }
            ), "ok"

        self.fake_exec = bad_exec
        report = self.execute(op)
        self.assertNotEqual("passed", report["verdict"])
        self.assertEqual(1, report["semantic_failures"])
        self.assertEqual("semantic-failed", campaigns.Campaign()._state().get("stop"))
        with self.assertRaises(authority.LedgerError):
            self.prepare()
        self.assertEqual(1, len(self.sends))

    def test_deleted_journal_or_altered_result_stops_without_refund(self) -> None:
        op = self.prepare()
        self.execute(op)
        op.journal_path.unlink()
        with self.assertRaises(authority.LedgerError):
            self.prepare()
        self.assertEqual("coverage-failed", campaigns.Campaign()._state().get("stop"))
        self.assertEqual(632, len(json.loads(self.ledger.read_text())["calls"]))

    def test_arbitrary_review_hash_or_wrong_bound_review_cannot_accept(self) -> None:
        op = self.prepare()
        report = self.execute(op)
        with self.assertRaises((ValueError, authority.LedgerError, OSError)):
            op.accept_batch(0, "d" * 64)
        path = self.review(op, report)
        review = json.loads(path.read_text())
        review["binding"]["report_digest"] = "d" * 64
        path.write_text(json.dumps(review))
        with self.assertRaises((ValueError, authority.LedgerError)):
            op.accept_batch(0, path)
        self.assertEqual({}, campaigns.Campaign()._state().get("accepted_batches", {}))

    def test_review_replacement_during_validation_cannot_accept_another_artifact(self) -> None:
        op = self.prepare()
        report = self.execute(op)
        path = self.review(op, report)
        read_bytes = self.operator._bytes
        invalid = json.dumps(
            {"v": 1, "reviewer": "native-closure-operator", "verdict": "failed", "binding": {}}
        ).encode()

        def replaced(source: Path) -> bytes:
            content = read_bytes(source)
            assert isinstance(content, bytes)
            if source == path:
                path.write_bytes(invalid)
            return content

        with (
            mock.patch.object(self.operator, "_bytes", side_effect=replaced),
            self.assertRaises((ValueError, authority.LedgerError)),
        ):
            op.accept_batch(0, path)
        self.assertEqual({}, campaigns.Campaign()._state().get("accepted_batches", {}))
        self.assertEqual(1, len(self.sends))

    def test_cached_tag_and_held_slot_cannot_charge(self) -> None:
        op = self.prepare()
        tag = "a" * 32
        (Path(self.paths["dir"]) / f"plan-{tag}.json").write_text("{}")
        with (
            mock.patch.object(self.operator.uuid, "uuid4", return_value=mock.Mock(hex=tag)),
            self.assertRaises(authority.LedgerError),
        ):
            self.execute(op)
        self.assertEqual([], campaigns.Campaign()._state()["calls"])
        self.account.body["deferred_slots"] = {
            "replay": ["replay000"],
            "qualification": [],
            "live": [],
        }
        self.account.body["requests"]["replay"].pop("replay000")
        self.account.activate()
        with self.assertRaises(authority.LedgerError):
            self.execute(self.prepare())
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_changed_later_row_prompt_or_selection_refuses_preparation(self) -> None:
        for field, value in (("prompt_digest", "f" * 64), ("selected_ids", ["invented-source"])):
            original = copy.deepcopy(self.regs[189][field])
            self.regs[189][field] = value
            self.seal()
            with self.assertRaises((ValueError, authority.LedgerError)):
                self.prepare()
            self.regs[189][field] = original
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_source_change_after_charge_persists_coverage_stop(self) -> None:
        op = self.prepare()
        self.execute(op)
        self.session.log.write_bytes(self.session.log.read_bytes() + b" ")
        with self.assertRaises((ValueError, authority.LedgerError)):
            self.prepare()
        self.assertEqual("coverage-failed", campaigns.Campaign()._state().get("stop"))

    def test_altered_native_result_blocks_restart_without_refund(self) -> None:
        op = self.prepare()
        self.execute(op)
        attempt = json.loads(op.journal_path.read_text())["attempts"][0]
        path = Path(self.paths["dir"]) / f"read-{attempt['tag']}.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(authority.LedgerError):
            self.prepare()
        self.assertEqual("coverage-failed", campaigns.Campaign()._state().get("stop"))
        self.assertEqual(632, len(json.loads(self.ledger.read_text())["calls"]))

    def test_orphan_native_attempt_after_transport_stops_the_whole_campaign(self) -> None:
        op = self.prepare()
        original = self.fake_exec

        def orphan(*args: Any, **kwargs: Any) -> tuple[str, str]:
            replay.Ledger(str(self.ledger)).charge("orphan|current")
            return original(*args, **kwargs)

        self.fake_exec = orphan
        with self.assertRaises(authority.LedgerError):
            self.execute(op)
        self.assertEqual("coverage-failed", campaigns.Campaign()._state().get("stop"))
        self.assertEqual(633, len(json.loads(self.ledger.read_text())["calls"]))
        with self.assertRaises(authority.LedgerError):
            self.prepare()

    def test_partial_lane_cannot_be_accepted_and_latches_coverage_stop(self) -> None:
        op = self.prepare()
        report = self.execute(op)
        with self.assertRaises((ValueError, authority.LedgerError)):
            op.accept_lane(self.review(op, report))
        self.assertEqual("coverage-failed", campaigns.Campaign()._state().get("stop"))

    def test_unactivated_authority_refuses_preparation_without_charge(self) -> None:
        self.account.body["phase"] = "prepared"
        self.account.body.pop("activation_anchor")
        self.account.manifest.write_text(json.dumps(self.account.body))
        with self.assertRaises(authority.LedgerError):
            self.prepare()
        self.assertEqual(631, len(json.loads(self.ledger.read_text())["calls"]))

    def test_critical_original_revision_or_clause_mismatch_refuses_before_charge(self) -> None:
        self.proto["critical_input_binding"]["cases"] = [
            {
                "case": "case00",
                "arm": "current",
                "saved_revision_sha256": "f" * 64,
                "criterion_clause_sha256": {"goal": grading.digest(self.regs[0]["intent"]["goal"])},
            }
        ]
        self.seal()
        with self.assertRaises((ValueError, authority.LedgerError)):
            self.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_native_page_source_change_refuses_before_charge(self) -> None:
        self.proto["input_digest_bindings"]["native_page_projection"] = "f" * 64
        self.seal()
        with self.assertRaises((ValueError, authority.LedgerError)):
            self.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_actual_node_failure_after_charge_stops_and_preserves_charge(self) -> None:
        op = self.prepare()
        with (
            mock.patch.object(
                replay, "_score_pages", side_effect=RuntimeError("synthetic Node failure")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.execute(op)
        self.assertEqual("coverage-failed", campaigns.Campaign()._state().get("stop"))
        self.assertEqual(632, len(json.loads(self.ledger.read_text())["calls"]))
        self.assertEqual(1, len(self.sends))

    def test_grading_validation_after_charge_stops_before_another_attempt(self) -> None:
        op = self.prepare()
        score = op._score

        def invalid(outputs: dict[str, Any], due: list[str], *, final: bool) -> Any:
            if outputs:
                raise ValueError("synthetic grading validation failure")
            return score(outputs, due, final=final)

        with (
            mock.patch.object(op, "_score", side_effect=invalid),
            self.assertRaises(authority.LedgerError),
        ):
            self.execute(op)
        self.assertEqual("coverage-failed", campaigns.Campaign()._state().get("stop"))
        self.assertEqual(1, len(self.sends))

    def test_protected_withdrawal_report_stops_before_another_attempt(self) -> None:
        op = self.prepare()
        score = op._score

        def withdrawal(outputs: dict[str, Any], due: list[str], *, final: bool) -> Any:
            report = score(outputs, due, final=final)
            if outputs:
                report["protection_failures"] = 1
                report["verdict"] = "failed"
            return report

        with mock.patch.object(op, "_score", side_effect=withdrawal):
            report = self.execute(op)
        self.assertEqual(1, report["protection_failures"])
        self.assertEqual("protection-failed", campaigns.Campaign()._state().get("stop"))
        with self.assertRaises(authority.LedgerError):
            self.prepare()
        self.assertEqual(1, len(self.sends))

    def test_resume_grades_complete_join_interrupted_before_semantic_stop(self) -> None:
        op = self.prepare()
        self.fake_exec = lambda *_a, **_kw: (
            json.dumps(
                {
                    "goal": {"result": "not_reached", "cites": [1]},
                    "line_1": {"result": "unverifiable", "cites": []},
                    "claims": {"result": "unverifiable", "cites": []},
                }
            ),
            "ok",
        )
        # Leave the actual native/journal artifacts exactly where a process kill
        # after durable join but before grading would leave them.
        with mock.patch.object(op, "_grade", return_value={"verdict": "ungraded"}):
            self.execute(op)
        self.assertIsNone(campaigns.Campaign()._state().get("stop"))
        with self.assertRaises(authority.LedgerError):
            self.prepare()
        self.assertEqual("semantic-failed", campaigns.Campaign()._state().get("stop"))
        self.assertEqual(632, len(json.loads(self.ledger.read_text())["calls"]))

    def test_changed_scorer_or_selected_control_refuses_before_charge(self) -> None:
        scorer = self.account.root / "changed-scorer.py"
        scorer.write_bytes(Path(grading.__file__).read_bytes() + b"# altered scorer\n")
        with mock.patch.object(grading, "__file__", str(scorer)), self.assertRaises(ValueError):
            self.prepare()
        self.regs[189]["source_bindings"]["shim_sha256"] = "f" * 64
        self.seal()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_unbound_native_code_inventory_refuses_before_charge(self) -> None:
        self.proto["input_digest_bindings"]["native_code_binding"] = {
            "commit": "1" * 40,
            "files": {"scripts/drift_closure_grading.py": "f" * 64},
        }
        with self.assertRaises(ValueError):
            self.seal()
            self.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_every_native_code_source_and_checkout_identity_is_bound_before_charge(self) -> None:
        actual = copy.deepcopy(self.proto["input_digest_bindings"]["native_code_binding"])
        for name in grading.NATIVE_CODE_FILES:
            with self.subTest(source=name):
                self.proto["input_digest_bindings"]["native_code_binding"] = copy.deepcopy(actual)
                self.proto["input_digest_bindings"]["native_code_binding"]["files"][name] = "f" * 64
                self.seal()
                with self.assertRaises(ValueError):
                    self.prepare()
        self.proto["input_digest_bindings"]["native_code_binding"] = copy.deepcopy(actual)
        self.proto["input_digest_bindings"]["native_code_binding"]["commit"] = "f" * 40
        self.seal()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_frozen_required_protection_cannot_lose_its_selected_source_binding(self) -> None:
        self.regs[0]["protected_facts"] = {}
        with self.assertRaises(ValueError):
            self.seal()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_each_required_protected_source_must_be_admitted_before_the_first_pilot(self) -> None:
        original = self.frozen["protected"].read_bytes()
        for n in range(10):
            with self.subTest(required_row=n):
                body = json.loads(original)
                body["rows"][n].pop("admissibility")
                if n % 2:
                    body["rows"][n]["admissibility"] = "unknown"
                self.frozen["protected"].write_text(json.dumps(body))
                self.seal()
                with self.assertRaisesRegex(ValueError, "preparation"):
                    self.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])
        self.assertEqual(631, len(json.loads(self.ledger.read_text())["calls"]))
        self.assertEqual([], self.sends)

    def test_empty_critical_protocol_and_unselected_historical_claim_refuse_before_charge(
        self,
    ) -> None:
        predicates = self.proto["threshold_proposal"]["critical_exact_predicates"]
        self.proto["threshold_proposal"]["critical_exact_predicates"] = []
        with self.assertRaises(ValueError):
            self.seal()
        self.proto["threshold_proposal"]["critical_exact_predicates"] = predicates
        self.regs[0]["protected_facts"] = {"claim0": "unselected"}
        with self.assertRaises(ValueError):
            self.seal()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])

    def test_source_change_during_transport_stops_without_join_or_refund(self) -> None:
        op = self.prepare()
        original = self.fake_exec

        def changed(*args: Any, **kwargs: Any) -> tuple[str, str]:
            self.session.log.write_bytes(self.session.log.read_bytes() + b" ")
            return original(*args, **kwargs)

        self.fake_exec = changed
        with self.assertRaises((ValueError, authority.LedgerError)):
            self.execute(op)
        self.assertEqual("coverage-failed", campaigns.Campaign()._state().get("stop"))
        self.assertEqual(632, len(json.loads(self.ledger.read_text())["calls"]))
        self.assertEqual(1, len(self.sends))

    def test_native_refusal_before_charge_is_not_measured_coverage_failure(self) -> None:
        op = self.prepare()
        with (
            mock.patch.object(
                score_abstention,
                "verify_claude_binary",
                side_effect=ValueError("synthetic precharge refusal"),
            ),
            self.assertRaises(ValueError),
        ):
            op.run_next(claude_model="claude-sonnet-5")
        self.assertIsNone(campaigns.Campaign()._state().get("stop"))
        self.assertEqual([], campaigns.Campaign()._state()["calls"])
        self.assertEqual(631, len(json.loads(self.ledger.read_text())["calls"]))
        self.assertNotIn("pending", json.loads(op.journal_path.read_text()))
        self.assertEqual("passed", self.execute(self.prepare())["verdict"])


if __name__ == "__main__":
    unittest.main()
