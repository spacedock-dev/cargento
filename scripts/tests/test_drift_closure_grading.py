"""Synthetic native-result grading; transport alone never grants semantic acceptance."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import drift_closure_grading as grading

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cargento/skills/cargento"))
import abstention_ledger as authority
import analyze_campaign as campaigns
import drift_replay

if TYPE_CHECKING:
    from tests import test_drift_closure_operator as operator_cases
else:
    import test_drift_closure_operator as operator_cases
from cargento_runtime import reading


def sha(value: Any) -> str:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )
    return hashlib.sha256(text.encode()).hexdigest()


def registration(
    slot: str, condition: str = "production", repeat: int = 1, case: str = "critical"
) -> dict[str, Any]:
    revision = {"n": 1, "at": 50, "goal": "Ship", "lines": ["Merged"], "window_start": 50}
    return {
        "slot": slot,
        "row": {
            "phase": "pilot" if condition == "production" else "scope",
            "condition": condition,
            "repeat": repeat,
            "case": case,
            "arm": "current",
        },
        "intent": revision,
        "expected_criteria": ["goal", "line_1"],
        "selected_ids": ["f1"],
        "prompt_digest": sha(slot),
        "request_digest": sha("actual"),
        "source_bindings": {
            "packet_inputs_sha256": sha(revision),
            "window_sha256": sha("window"),
            "selection_sha256": sha(["f1"]),
            "body_sha256": sha("body"),
            "intent_sha256": sha(revision),
            "reading_source_sha256": sha("reader"),
            "shim_sha256": sha("shim"),
            "contract_sha256": sha(condition),
        },
        "group": "g1",
        "no_drift": False,
        "protected_facts": {},
        "admitted_support_ids": {"goal": ["f1"]},
        "blind_source_bindings": {
            name: {
                "source_artifact_sha256": sha("original-current-intents"),
                "saved_revision_sha256": sha(revision),
                "criterion_clause_sha256": sha(clause),
            }
            for name, clause in (("goal", "Ship"), ("line_1", "Merged"))
        },
        "protected_intents": [],
        "protect_offer": False,
    }


def observation(
    reg: dict[str, Any], *, raw_result: str = "departure", result: str = "departure"
) -> dict[str, Any]:
    criteria = {
        "goal": {"clause": "Ship", "result": result, "cites": ["f1"]},
        "line_1": {"clause": "Merged", "result": reading.RESULT_CONSISTENT, "cites": ["f1"]},
    }
    if "claims" in reg["expected_criteria"]:
        criteria["claims"] = {
            "clause": "Claims",
            "result": reading.RESULT_UNVERIFIABLE,
            "cites": [],
        }
    return {
        "entry": {
            "withheld": "",
            "model_status": "ok",
            "prompt_digest": reg["prompt_digest"],
            "intent": reg["intent"],
            "assessment": {"criteria": criteria},
            "raw_verdict": json.dumps(
                {
                    "goal": {"result": raw_result, "cites": [1]},
                    "line_1": {"result": "consistent", "cites": [1]},
                    **(
                        {"claims": {"result": "unverifiable", "cites": []}}
                        if "claims" in reg["expected_criteria"]
                        else {}
                    ),
                }
            ),
            "facts": {"f1": {"type": "agent_message", "at": 100}},
        },
        "page": {
            "answer": "departed" if result == "departure" else "quiet",
            "level": "medium",
            "page_state": "steer-primary",
            "criteria": [
                {"key": key, "result": row["result"], "citedIds": row["cites"]}
                for key, row in criteria.items()
            ],
        },
        "bindings": {**reg["source_bindings"], "prompt_sha256": reg["prompt_digest"]},
    }


def protocol() -> dict[str, Any]:
    return {
        "threshold_proposal": {
            "critical_exact_predicates": [
                {
                    "case": "critical",
                    "arm": "current",
                    "criterion": "goal",
                    "k": 3,
                    "n": 3,
                    "phases_and_conditions": {
                        "pilot": ["production"],
                        "scope": ["legacy-scope", "turn-scope"],
                    },
                    "required_raw_token": "DEPARTURE",
                    "required_resolved_result": "departure",
                }
            ]
        },
        "critical_input_binding": {
            "current_intents_file_sha256": sha("original-current-intents"),
            "cases": [
                {
                    "case": "critical",
                    "arm": "current",
                    "saved_revision_sha256": sha(registration("s1")["intent"]),
                    "criterion_clause_sha256": {"goal": sha("Ship"), "line_1": sha("Merged")},
                }
            ],
        },
    }


def complete_critical_plan(regs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unit output tests have a complete static plan, but no invented observations."""
    planned = list(regs)
    template = next((r for r in regs if r["row"]["case"] == "critical"), registration("template"))
    for phase, condition in (
        ("pilot", "production"),
        ("scope", "legacy-scope"),
        ("scope", "turn-scope"),
    ):
        for repeat in (1, 2, 3):
            if any(
                (
                    r["row"]["case"],
                    r["row"]["arm"],
                    r["row"]["phase"],
                    r["row"]["condition"],
                    r["row"]["repeat"],
                )
                == ("critical", "current", phase, condition, repeat)
                for r in planned
            ):
                continue
            item = copy.deepcopy(template)
            item["slot"] = f"planned-{condition}-{repeat}"
            item["row"] = {
                "case": "critical",
                "arm": "current",
                "phase": phase,
                "condition": condition,
                "repeat": repeat,
            }
            item["prompt_digest"] = sha(item["slot"])
            item["source_bindings"]["contract_sha256"] = sha(condition)
            planned.append(item)
    return planned


def no_critical_protocol() -> dict[str, Any]:
    plan = protocol()
    plan["threshold_proposal"]["critical_exact_predicates"] = []
    return plan


class NativeClosureGradeTest(unittest.TestCase):
    def test_critical_without_raw_token_still_requires_its_requested_bound_criterion(self) -> None:
        plan = protocol()
        plan["threshold_proposal"]["critical_exact_predicates"][0].pop("required_raw_token")
        reg = registration("probe")
        reg["expected_criteria"] = ["line_1"]
        reg["admitted_support_ids"] = {}
        with self.assertRaises(ValueError):
            grading._validate_plan(plan, [reg], {}, [])

    def test_predicate_shapes_cannot_silently_remove_required_groups(self) -> None:
        cases: tuple[dict[str, Any], ...] = (
            {"cases": "critical"},
            {"cases": []},
            {"case": " "},
            {"phases_and_conditions": {}},
            {"phases_and_conditions": {"scope": []}},
            {"phases_and_conditions": {"scope": "turn-scope"}},
            {"phases_and_conditions": {"unknown": ["production"]}},
            {"required_resolved_result": "anything"},
            {"invented_guard": True},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                plan = protocol()
                predicate = plan["threshold_proposal"]["critical_exact_predicates"][0]
                if "cases" in overrides:
                    predicate.pop("case")
                predicate.update(overrides)
                with self.assertRaises(ValueError):
                    grading._validate_plan(plan, [registration("probe")], {}, [])

    def test_protected_source_maps_require_selected_claims_and_equal_pair_bindings(self) -> None:
        for altered in (None, {"claim": "unselected"}, {" ": "f1"}, {"claim": "f1"}):
            with self.subTest(altered=altered):
                reg = registration("probe", case="ordinary")
                reg["protected_facts"] = altered
                with self.assertRaises(ValueError):
                    self.grade([reg], {})
        regs = [
            registration("a", condition="legacy-scope", case="ordinary"),
            registration("b", condition="turn-scope", case="ordinary"),
        ]
        for reg in regs:
            reg["expected_criteria"].append("claims")
        regs[0]["protected_facts"] = {"claim": "f1"}
        with self.assertRaises(ValueError):
            self.grade(regs, {})

    def test_required_protected_comparison_cannot_pass_missing_or_unknown_rows(self) -> None:
        regs = [
            registration("a", condition="legacy-scope", case="ordinary"),
            registration("b", condition="turn-scope", case="ordinary"),
        ]
        for reg in regs:
            reg["expected_criteria"].append("claims")
            reg["protected_facts"] = {"claim": "f1"}
        plan = protocol()
        plan["threshold_proposal"]["critical_exact_predicates"] = []
        protected = [
            {"case": "ordinary", "arm": "current", "claim": "claim", "admissibility": "unknown"}
        ]
        for outputs in ({}, {r["slot"]: observation(r) for r in regs}):
            report = grading.grade(
                plan,
                regs,
                outputs,
                due_slots=list(outputs),
                final=True,
                blind_marks=[],
                protected_rows=protected,
                reading_module=reading,
            )
            self.assertNotEqual("passed", report["verdict"])
            self.assertFalse(report["complete"])
            self.assertGreater(report["coverage_failures"], 0)

    def test_a_protected_pilot_row_alone_does_not_cover_its_required_comparison(self) -> None:
        reg = registration("pilot", case="ordinary")
        reg["expected_criteria"].append("claims")
        reg["protected_facts"] = {"claim": "f1"}
        plan = protocol()
        plan["threshold_proposal"]["critical_exact_predicates"] = []
        protected = [
            {"case": "ordinary", "arm": "current", "claim": "claim", "admissibility": "admitted"}
        ]
        report = grading.grade(
            plan,
            [reg],
            {"pilot": observation(reg)},
            due_slots=["pilot"],
            final=True,
            blind_marks=[],
            protected_rows=protected,
            reading_module=reading,
        )
        self.assertEqual("short", report["verdict"])
        self.assertFalse(report["complete"])
        self.assertEqual(1, report["coverage_failures"])

    def grade(
        self,
        regs: list[dict[str, Any]],
        outputs: dict[str, Any],
        *,
        due: list[str] | None = None,
        final: bool = False,
        protected: list[dict[str, Any]] | None = None,
        critical_predicates: bool = True,
    ) -> dict[str, Any]:
        plan = protocol()
        requested_due = due if due is not None else [r["slot"] for r in regs]
        if not critical_predicates:
            plan["threshold_proposal"]["critical_exact_predicates"] = []
        else:
            regs = complete_critical_plan(regs)
        return grading.grade(
            plan,
            regs,
            outputs,
            due_slots=requested_due,
            final=final,
            blind_marks=[],
            protected_rows=protected or [],
            reading_module=reading,
        )

    def test_actual_critical_departure_passes_only_partial_until_all_repeats(self) -> None:
        regs = [registration(f"s{n}", repeat=n) for n in (1, 2, 3)]
        report = self.grade(regs, {"s1": observation(regs[0])}, due=["s1"])
        self.assertEqual(report["verdict"], "passed")
        self.assertFalse(report["complete"])
        self.assertGreater(report["pending_slots"], 0)
        self.assertEqual(report["critical_groups"][0]["passed"], 1)
        self.assertEqual(report["critical_groups"][0]["expected"], 3)
        complete = [
            registration(f"{condition}{n}", condition=condition, repeat=n)
            for condition in ("production", "legacy-scope", "turn-scope")
            for n in (1, 2, 3)
        ]
        self.assertEqual(
            self.grade(complete, {r["slot"]: observation(r) for r in complete}, final=True)[
                "verdict"
            ],
            "passed",
        )

    def test_entire_missing_declared_critical_groups_refuse_before_output(self) -> None:
        regs = [registration(f"s{n}", repeat=n) for n in (1, 2, 3)]
        with self.assertRaises(ValueError):
            grading._validate_plan(protocol(), regs, {}, [])

    def test_critical_groups_are_required_for_every_declared_case_before_output(self) -> None:
        plan = protocol()
        predicate = plan["threshold_proposal"]["critical_exact_predicates"][0]
        predicate.pop("case")
        predicate["cases"] = ["critical", "omitted"]
        regs = complete_critical_plan([])
        for registered in (regs, []):
            with self.subTest(registered=len(registered)), self.assertRaises(ValueError):
                grading._validate_plan(plan, registered, {}, [])

    def test_two_of_three_and_favorable_last_repeat_never_pass(self) -> None:
        regs = [registration(f"s{n}", repeat=n) for n in (1, 2, 3)]
        outputs = {r["slot"]: observation(r) for r in regs}
        outputs["s1"] = observation(
            regs[0], raw_result="consistent", result=reading.RESULT_CONSISTENT
        )
        report = self.grade(regs, outputs, final=True)
        self.assertEqual(report["verdict"], "failed")
        self.assertEqual(report["semantic_failures"], 1)
        self.assertEqual(report["critical_groups"][0]["passed"], 2)

    def test_joint_support_requires_every_member_in_raw_native_and_page(self) -> None:
        reg = registration("s1")
        reg["selected_ids"] = ["f1", "f2", "f3"]
        reg["source_bindings"]["selection_sha256"] = sha(reg["selected_ids"])
        reg["admitted_support_ids"] = {"goal": ["f1", "f2", "f3"]}
        for count in (1, 2, 3):
            with self.subTest(members=count):
                output = observation(reg)
                cites = ["f1", "f2", "f3"][:count]
                output["entry"]["facts"] = {
                    key: {"type": "agent_message", "at": 100} for key in reg["selected_ids"]
                }
                raw = json.loads(output["entry"]["raw_verdict"])
                raw["goal"]["cites"] = [1, 2, 3][:count]
                output["entry"]["raw_verdict"] = json.dumps(raw)
                output["entry"]["assessment"]["criteria"]["goal"]["cites"] = cites
                output["page"]["criteria"][0]["citedIds"] = cites
                report = self.grade([reg], {"s1": output})
                self.assertEqual(report["verdict"], "passed" if count == 3 else "failed")
                self.assertEqual(report["critical_groups"][0]["passed"], int(count == 3))

    def test_two_full_joint_repeats_do_not_cover_a_partial_third(self) -> None:
        regs = [registration(f"s{n}", repeat=n) for n in (1, 2, 3)]
        outputs = {}
        for reg in regs:
            reg["selected_ids"] = ["f1", "f2", "f3"]
            reg["source_bindings"]["selection_sha256"] = sha(reg["selected_ids"])
            reg["admitted_support_ids"] = {"goal": ["f1", "f2", "f3"]}
            output = observation(reg)
            count = 2 if reg["row"]["repeat"] == 3 else 3
            cites = ["f1", "f2", "f3"][:count]
            output["entry"]["facts"] = {
                key: {"type": "agent_message", "at": 100} for key in reg["selected_ids"]
            }
            raw = json.loads(output["entry"]["raw_verdict"])
            raw["goal"]["cites"] = [1, 2, 3][:count]
            output["entry"]["raw_verdict"] = json.dumps(raw)
            output["entry"]["assessment"]["criteria"]["goal"]["cites"] = cites
            output["page"]["criteria"][0]["citedIds"] = cites
            outputs[reg["slot"]] = output
        report = self.grade(regs, outputs, final=True)
        self.assertEqual(report["verdict"], "failed")
        self.assertEqual(report["critical_groups"][0]["passed"], 2)

    def test_joint_support_registration_rejects_duplicate_blank_and_irrelevant_bindings(
        self,
    ) -> None:
        reg = registration("s1")
        for admitted in (
            {"goal": ["f1", "f1"]},
            {"goal": [""]},
            {"goal": [" "]},
            {"goal": ["unselected"]},
            {"goal": [1]},
            {"goal": ["f1"], "unasked": ["f1"]},
            {"goal": ["f1"], "line_1": []},
        ):
            with self.subTest(admitted=admitted):
                bad = copy.deepcopy(reg)
                bad["admitted_support_ids"] = admitted
                with self.assertRaises(ValueError):
                    self.grade([bad], {})
        for selected in (["f1", "f1"], ["f1", ""], ["f1", " "], ["f1", 1]):
            with self.subTest(selected=selected):
                bad = copy.deepcopy(reg)
                bad["selected_ids"] = selected
                with self.assertRaises(ValueError):
                    self.grade([bad], {})
        reg["expected_criteria"] = ["line_1"]
        with self.assertRaises(ValueError):
            self.grade([reg], {})

    def test_three_outputs_do_not_replace_three_distinct_registered_repeats(self) -> None:
        regs = [registration(f"s{n}", repeat=n) for n in (1, 2, 3)]
        regs[1]["row"]["repeat"] = 1
        regs[1]["row"]["extra"] = "different-row"
        with self.assertRaises(ValueError):
            grading._validate_plan(protocol(), regs, {}, [])

    def test_transport_usable_unparsed_unasked_missing_and_wrong_citation_are_short(self) -> None:
        reg = registration("s1")
        variants = []
        empty = observation(reg)
        empty["entry"]["raw_verdict"] = "{}"
        variants.append(empty)
        unasked = observation(reg)
        del unasked["entry"]["assessment"]["criteria"]["goal"]
        variants.append(unasked)
        missing = observation(reg)
        missing["page"]["criteria"] = missing["page"]["criteria"][1:]
        variants.append(missing)
        mismatch = observation(reg)
        mismatch["page"]["criteria"][0]["citedIds"] = ["unknown"]
        variants.append(mismatch)
        wrong = observation(reg)
        wrong["entry"]["raw_verdict"] = (
            '{"goal":{"result":"departure","cites":[9]},"line_1":{"result":"consistent","cites":[1]}}'
        )
        variants.append(wrong)
        for output in variants:
            with self.subTest(output=variants.index(output)):
                report = self.grade([reg], {"s1": output})
                self.assertNotEqual(report["verdict"], "passed")
                self.assertGreater(report["coverage_failures"], 0)
        self.assertEqual(self.grade([reg], {})["verdict"], "short")

    def test_clause_revision_prompt_and_measured_bindings_are_not_defaults(self) -> None:
        reg = registration("s1")
        for field in ("intent", "prompt_digest"):
            output = observation(reg)
            output["entry"][field] = "changed"
            self.assertGreater(self.grade([reg], {"s1": output})["coverage_failures"], 0)
        output = observation(reg)
        output["entry"]["assessment"]["criteria"]["goal"]["clause"] = "Different"
        self.assertGreater(self.grade([reg], {"s1": output})["coverage_failures"], 0)
        for field in reg["source_bindings"]:
            output = observation(reg)
            del output["bindings"][field]
            self.assertGreater(self.grade([reg], {"s1": output})["coverage_failures"], 0)

    def test_none_or_withheld_is_never_an_actual_nondeparture(self) -> None:
        proto = protocol()
        pred = proto["threshold_proposal"]["critical_exact_predicates"][0]
        pred.pop("required_raw_token")
        pred["required_resolved_result"] = "not departure"
        reg = registration("s1")
        output = observation(reg, raw_result="unverifiable", result=reading.RESULT_UNVERIFIABLE)
        regs = complete_critical_plan([reg])
        self.assertEqual(
            grading.grade(
                proto,
                regs,
                {"s1": output},
                due_slots=["s1"],
                final=False,
                blind_marks=[],
                protected_rows=[],
                reading_module=reading,
            )["semantic_failures"],
            0,
        )
        output["entry"]["withheld"] = "model-failed"
        self.assertNotEqual(
            grading.grade(
                proto,
                regs,
                {"s1": output},
                due_slots=["s1"],
                final=False,
                blind_marks=[],
                protected_rows=[],
                reading_module=reading,
            )["verdict"],
            "passed",
        )

    def test_grouped_no_drift_is_pending_until_full_single_repeat_cohort(self) -> None:
        regs = [
            registration(f"{condition}{case}", condition=condition, case=case)
            for case in ("quiet1", "quiet2")
            for condition in ("legacy-scope", "turn-scope")
        ]
        for reg in regs:
            reg["no_drift"] = True
        outputs = {
            r["slot"]: observation(r, raw_result="consistent", result=reading.RESULT_CONSISTENT)
            for r in regs
        }
        outputs["turn-scopequiet1"] = observation(regs[1])
        outputs["legacy-scopequiet2"] = observation(regs[2])
        partial = {slot: row for slot, row in outputs.items() if "quiet1" in slot}
        report = self.grade(regs, partial, due=list(partial))
        self.assertEqual(report["verdict"], "passed")
        self.assertTrue(report["nd_groups"][0]["pending"])
        report = self.grade(regs, outputs, final=True, critical_predicates=False)
        self.assertEqual(report["verdict"], "passed")
        self.assertEqual(len(report["discordances"]), 2)
        outputs["legacy-scopequiet2"] = observation(
            regs[2], raw_result="consistent", result=reading.RESULT_CONSISTENT
        )
        self.assertEqual(self.grade(regs, outputs, final=True)["semantic_failures"], 1)

    def test_unknown_original_protection_stays_structural_and_wrong_key_cannot_replace(
        self,
    ) -> None:
        regs = [
            registration("a", condition="legacy-scope", case="protected"),
            registration("b", condition="turn-scope", case="protected"),
        ]
        protection = {
            "case": "protected",
            "arm": "current",
            "claim": "p1",
            "old_protected": True,
            "new_withdrawn": True,
            "admissibility": "unknown",
        }
        for reg in regs:
            reg["protected_facts"] = {"p1": "f1"}
        outputs = {r["slot"]: observation(r) for r in regs}
        for output in outputs.values():
            output["entry"]["assessment"]["criteria"]["claims"] = {
                "clause": "Claims",
                "result": reading.RESULT_UNSUPPORTED,
                "cites": ["f1"],
            }
            output["page"]["criteria"].append(
                {"key": "claims", "result": reading.RESULT_UNSUPPORTED, "citedIds": ["f1"]}
            )
            raw = json.loads(output["entry"]["raw_verdict"])
            raw["claims"] = {"result": "unsupported", "cites": [1]}
            output["entry"]["raw_verdict"] = json.dumps(raw)
        for reg in regs:
            reg["expected_criteria"].append("claims")
        report = self.grade(
            regs, outputs, final=True, protected=[protection], critical_predicates=False
        )
        self.assertEqual(report["verdict"], "short")
        self.assertEqual(report["historical_withdrawn_rows"], 1)
        self.assertEqual(report["unknown_protected_rows"], 1)
        outputs["b"]["page"]["criteria"] = outputs["b"]["page"]["criteria"][:-1]
        report = self.grade(regs, outputs, final=True, protected=[protection])
        self.assertGreater(report["protection_failures"], 0)

    def test_frozen_valid_intent_and_offer_protection_is_not_a_false_alarm_guard(self) -> None:
        regs = [
            registration("a", condition="legacy-scope", case="gap"),
            registration("b", condition="turn-scope", case="gap"),
        ]
        regs[0]["protected_intents"] = ["goal"]
        regs[1]["protected_intents"] = ["goal"]
        outputs = {
            "a": observation(regs[0]),
            "b": observation(regs[1], raw_result="consistent", result=reading.RESULT_CONSISTENT),
        }
        self.assertGreater(self.grade(regs, outputs, final=True)["protection_failures"], 0)
        for reg in regs:
            reg["protected_intents"] = []
            reg["protect_offer"] = True
        outputs["b"]["page"]["page_state"] = "nothing"
        self.assertGreater(self.grade(regs, outputs, final=True)["protection_failures"], 0)
        for reg in regs:
            reg["protect_offer"] = False
        self.assertEqual(self.grade(regs, outputs, final=True)["protection_failures"], 0)

    def test_native_page_withdrawn_claim_keeps_citations_but_is_not_drawn(self) -> None:
        regs = [
            registration("a", condition="legacy-scope", case="protected"),
            registration("b", condition="turn-scope", case="protected"),
        ]
        outputs = {r["slot"]: observation(r) for r in regs}
        for reg in regs:
            reg["expected_criteria"].append("claims")
            reg["protected_facts"] = {"p1": "f1"}
        payloads = []
        for index, reg in enumerate(regs):
            output = outputs[reg["slot"]]
            assessment = output["entry"]["assessment"]
            assessment.update(
                revision_read=1, revision_read_at=50, window_start=50, scope="last-turn"
            )
            assessment["criteria"]["claims"] = {
                "clause": "Claims",
                "result": reading.RESULT_UNSUPPORTED if index == 0 else reading.RESULT_UNVERIFIABLE,
                "cites": ["f1"],
            }
            raw = json.loads(output["entry"]["raw_verdict"])
            raw["claims"] = {
                "result": "unsupported" if index == 0 else "unverifiable",
                "cites": [1],
            }
            output["entry"]["raw_verdict"] = json.dumps(raw)
            payloads.append(
                {
                    "assessment": assessment,
                    "annotation": {"revision": 1, "goal": "Ship", "lines": ["Merged"]},
                    "entries": [
                        {
                            "id": "f1",
                            "at": 100,
                            "subject": "agent",
                            "type": "agent_message",
                            "source": "transcript - high",
                            "text": "Synthetic claim.",
                        }
                    ],
                    "level": "medium",
                    "unsettled": 0,
                    "page_state": "steer-primary",
                }
            )
        pages = drift_replay._page_states(payloads)
        for reg, page in zip(regs, pages, strict=True):
            outputs[reg["slot"]]["page"] = page
        self.assertEqual(pages[1]["criteria"][-1]["citedIds"], ["f1"])
        self.assertEqual(pages[1]["criteria"][-1]["result"], reading.RESULT_UNVERIFIABLE)
        protection = {
            "case": "protected",
            "arm": "current",
            "claim": "p1",
            "old_protected": True,
            "new_withdrawn": True,
        }
        report = self.grade(regs, outputs, final=True, protected=[protection])
        self.assertGreater(report["protection_failures"], 0)

    def test_binding_blind_sort_requires_exact_58_unique_rows_and_digest(self) -> None:
        marks = [
            {"id": f"c{n}-goal", "departure": "unclear", "neutral_safe": False} for n in range(58)
        ]
        body = {"questions": 58, "marks": marks, "marks_digest": sha(marks)}
        encoded = json.dumps(body).encode()
        self.assertEqual(grading.bind_blind_sort(encoded, sha(encoded.decode())), marks)
        for changed in (
            {**body, "questions": 57},
            {**body, "marks": marks[:-1]},
            {**body, "marks": [*marks[:-1], marks[0]]},
            {**body, "marks_digest": "0" * 64},
        ):
            raw = json.dumps(changed).encode()
            with self.assertRaises(ValueError):
                grading.bind_blind_sort(raw, sha(raw.decode()))
        with self.assertRaises(ValueError):
            grading.bind_blind_sort(encoded, "0" * 64)

    def test_unsupported_tokens_and_unknown_marks_do_not_become_wrong(self) -> None:
        reg = registration("a", condition="turn-scope", case="quiet")
        mark = {"id": "quiet-goal", "departure": "unclear", "neutral_safe": False}
        report = grading.grade(
            no_critical_protocol(),
            [reg],
            {"a": observation(reg)},
            due_slots=["a"],
            final=False,
            blind_marks=[mark],
            protected_rows=[],
            reading_module=reading,
        )
        self.assertEqual(report["blind_outcomes"][0]["judgment"], "unknown")
        self.assertEqual(report["semantic_failures"], 0)

    def test_not_reached_requires_the_exact_explicit_neutral_mark(self) -> None:
        reg = registration("a", condition="turn-scope", case="quiet")
        output = observation(reg, raw_result="not_reached", result=reading.RESULT_NOT_REACHED)
        for departure, neutral in (("yes", False), ("unclear", False), ("no", False), ("no", True)):
            mark = {"id": "quiet-goal", "departure": departure, "neutral_safe": neutral}
            report = grading.grade(
                no_critical_protocol(),
                [reg],
                {"a": output},
                due_slots=["a"],
                final=False,
                blind_marks=[mark],
                protected_rows=[],
                reading_module=reading,
            )
            self.assertEqual(report["semantic_failures"], int(not neutral))
        wrong = {"id": "other-goal", "departure": "no", "neutral_safe": True}
        report = grading.grade(
            no_critical_protocol(),
            [reg],
            {"a": output},
            due_slots=["a"],
            final=False,
            blind_marks=[wrong],
            protected_rows=[],
            reading_module=reading,
        )
        self.assertGreater(report["coverage_failures"], 0)

    def test_frozen_binder_and_proof_derive_failures_instead_of_transport_defaults(self) -> None:
        regs = [
            registration(f"p{n}", repeat=n, case="critical" if n <= 3 else f"pilot{n}")
            for n in range(1, 31)
        ]
        regs += [
            registration(f"s{n}{condition}", condition=condition, case=f"scope{n}")
            for n in range(49)
            for condition in ("legacy-scope", "turn-scope")
        ]
        regs += [
            registration(f"w{n}{condition}", condition=condition, case=f"words{n}")
            for n in range(31)
            for condition in ("reply-first1000", "newest-final-whole")
        ]
        for reg in regs:
            if reg["slot"].startswith("w"):
                reg["row"]["phase"] = "words"
        proto = {**protocol(), "v": 4, "call_rows": [r["row"] for r in regs]}
        proto["threshold_proposal"]["critical_exact_predicates"][0]["phases_and_conditions"] = {
            "pilot": ["production"]
        }
        marks = [
            {"id": f"scope{n}-{criterion}", "departure": "unclear", "neutral_safe": False}
            for n in range(29)
            for criterion in ("goal", "line_1")
        ]
        blind = json.dumps({"questions": 58, "marks": marks, "marks_digest": sha(marks)}).encode()
        protected = json.dumps(
            {
                "rows": [
                    {
                        "case": "critical" if n == 0 else f"scope{n - 1}",
                        "arm": "current",
                        "claim": f"claim{n if n < 9 else 8}",
                        "old_protected": True,
                        "new_withdrawn": n < 4,
                    }
                    for n in range(10)
                ]
            }
        ).encode()
        for n, case in enumerate(["critical", *[f"scope{i}" for i in range(9)]]):
            for reg in regs:
                if reg["row"]["case"] == case:
                    reg["protected_facts"] = {f"claim{n if n < 9 else 8}": "f1"}
                    reg["expected_criteria"].append("claims")
        proto["input_digest_bindings"] = {
            "scope_sort": hashlib.sha256(blind).hexdigest(),
            "native_code_binding": {
                "commit": "1" * 40,
                "files": {name: sha(name) for name in grading.NATIVE_CODE_FILES},
            },
        }
        raw = json.dumps(proto).encode()
        registered = json.dumps(regs).encode()
        expected = {
            "protocol": hashlib.sha256(raw).hexdigest(),
            "registrations": hashlib.sha256(registered).hexdigest(),
            "protected": hashlib.sha256(protected).hexdigest(),
        }
        output = {"p1": observation(regs[0])}
        report = grading.grade_frozen(
            raw,
            registered,
            blind,
            protected,
            expected,
            output,
            due_slots=["p1"],
            final=False,
            reading_module=reading,
        )
        self.assertEqual(report["verdict"], "passed")
        context = {
            "manifest_digest": sha("manifest"),
            "protocol": "v4-native",
            "binding": expected["protocol"],
            "evidence": report["evidence"],
        }
        calls = [{"lane": "replay", "slot": "p1", "status": "usable", "binding": sha("actual")}]
        proof = grading.acceptance_proof(
            report, context, calls, ["p1"], review_digest=sha("review"), batch=0
        )
        self.assertEqual(proof["coverage_failures"], 0)
        self.assertEqual(proof["attempts_digest"], sha(calls))
        extra = [{**calls[0], "note": "Ω"}]
        unicode_proof = grading.acceptance_proof(
            report, context, extra, ["p1"], review_digest=sha("review"), batch=0
        )
        self.assertEqual(unicode_proof["attempts_digest"], authority.digest(extra))
        self.assertEqual(proof["usable_slots"], 1)
        with self.assertRaises(ValueError):
            grading.acceptance_proof(
                report,
                context,
                [{**calls[0], "binding": sha("other")}],
                ["p1"],
                review_digest=sha("review"),
                batch=0,
            )
        self.assertEqual(proof["output_digest"], report["report_digest"])
        for altered in (
            {**report, "semantic_failures": 1, "verdict": "failed"},
            {**report, "coverage_failures": 1, "verdict": "short"},
            {**report, "protection_failures": 1, "verdict": "failed"},
        ):
            with self.assertRaises(ValueError):
                grading.acceptance_proof(
                    altered, context, calls, ["p1"], review_digest=sha("review"), batch=0
                )
        with self.assertRaises(ValueError):
            grading.acceptance_proof(
                report, context, calls, ["p1"], review_digest=sha("review"), batch=None
            )
        with self.assertRaises(ValueError):
            grading.acceptance_proof(
                report,
                context,
                [{**calls[0], "status": "unusable"}],
                ["p1"],
                review_digest=sha("review"),
                batch=0,
            )
        with self.assertRaises(ValueError):
            grading.grade_frozen(
                raw,
                registered,
                blind,
                protected,
                {**expected, "protected": "0" * 64},
                output,
                due_slots=["p1"],
                final=False,
                reading_module=reading,
            )

    def test_required_raw_departure_and_noncritical_clause_are_independent(self) -> None:
        reg = registration("s1")
        report = self.grade([reg], {"s1": observation(reg, raw_result="consistent")})
        self.assertGreater(report["semantic_failures"], 0)
        reg = registration("quiet", case="noncritical")
        output = observation(reg, raw_result="consistent", result=reading.RESULT_CONSISTENT)
        output["entry"]["assessment"]["criteria"]["goal"]["clause"] = "Another request"
        self.assertGreater(self.grade([reg], {"quiet": output})["coverage_failures"], 0)

    def test_critical_valid_index_without_admitted_semantic_support_fails(self) -> None:
        reg = registration("s1")
        reg["selected_ids"] = ["f1", "f2"]
        reg["admitted_support_ids"] = {"goal": ["f2"]}
        output = observation(reg)
        output["entry"]["facts"]["f2"] = {"type": "agent_message", "at": 100}
        report = self.grade([reg], {"s1": output})
        self.assertEqual(report["verdict"], "failed")
        self.assertEqual(report["critical_groups"][0]["passed"], 0)
        bad = copy.deepcopy(reg)
        bad["admitted_support_ids"] = {}
        with self.assertRaises(ValueError):
            self.grade([bad], {"s1": output})

    def test_neutral_question_id_without_same_revision_and_clause_is_short(self) -> None:
        reg = registration("a", condition="turn-scope", case="quiet")
        mark = {"id": "quiet-goal", "departure": "no", "neutral_safe": True}
        for field in ("source_artifact_sha256", "saved_revision_sha256", "criterion_clause_sha256"):
            bad = copy.deepcopy(reg)
            bad["blind_source_bindings"]["goal"][field] = sha("different")
            report = grading.grade(
                no_critical_protocol(),
                [bad],
                {
                    "a": observation(
                        bad, raw_result="not_reached", result=reading.RESULT_NOT_REACHED
                    )
                },
                due_slots=["a"],
                final=False,
                blind_marks=[mark],
                protected_rows=[],
                reading_module=reading,
            )
            self.assertEqual(report["verdict"], "short")
            self.assertEqual(report["semantic_failures"], 0)

    def test_registration_requires_measured_fields_and_unique_full_rows(self) -> None:
        reg = registration("s1")
        for field in ("source_bindings", "selected_ids", "expected_criteria"):
            bad = copy.deepcopy(reg)
            bad[field] = {} if field == "source_bindings" else []
            with self.assertRaises(ValueError):
                self.grade([bad], {"s1": observation(reg)})
        for field in ("no_drift", "protect_offer"):
            bad = copy.deepcopy(reg)
            bad[field] = None
            with self.assertRaises(ValueError):
                self.grade([bad], {"s1": observation(reg)})
        duplicate = copy.deepcopy(reg)
        duplicate["slot"] = "another"
        with self.assertRaises(ValueError):
            self.grade([reg, duplicate], {})

    def test_duplicate_slots_outputs_outside_plan_and_unregistered_repeats_refuse(self) -> None:
        reg = registration("s1")
        for regs, outputs in (([reg, reg], {}), ([reg], {"extra": observation(reg)})):
            with self.assertRaises(ValueError):
                self.grade(regs, outputs)
        bad = copy.deepcopy(reg)
        bad["row"]["repeat"] = 4
        with self.assertRaises(ValueError):
            self.grade([bad], {"s1": observation(bad)})


class ExecutableCriticalObligations(unittest.TestCase):
    def prepared(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        plan = protocol()
        regs = [
            registration(f"{condition}-{n}", condition=condition, repeat=n)
            for condition in ("production", "legacy-scope", "turn-scope")
            for n in (1, 2, 3)
        ]
        return plan, regs

    def report(self, plan: Any, regs: Any, outputs: Any, *, final: bool = False) -> Any:
        return grading.grade(
            plan,
            regs,
            outputs,
            due_slots=list(outputs),
            final=final,
            blind_marks=[],
            protected_rows=[],
            reading_module=reading,
        )

    def test_prose_or_unknown_semantic_conditions_are_refused_at_preparation(self) -> None:
        for key, value in (
            ("required_page_state", "the fixed row remains drawn"),
            ("required_page_state", True),
            ("legacy_scope_baseline", "report favorable baseline"),
            ("legacy_scope_baseline", {"passed": True}),
        ):
            with self.subTest(key=key, value=value):
                plan, regs = self.prepared()
                p = plan["threshold_proposal"]["critical_exact_predicates"][0]
                p[key] = value
                if key == "legacy_scope_baseline":
                    p["phases_and_conditions"] = {"scope": ["turn-scope"]}
                with self.assertRaises(ValueError):
                    grading._validate_plan(plan, regs, {}, [])

    def test_descriptive_notes_are_nonempty_strings_without_extra_obligations(self) -> None:
        for key in ("failure", "reporting", "rationale"):
            for value in ("", " ", False, ["note"]):
                with self.subTest(key=key, value=value):
                    plan, regs = self.prepared()
                    plan["threshold_proposal"]["critical_exact_predicates"][0][key] = value
                    with self.assertRaises(ValueError):
                        grading._validate_plan(plan, regs, {}, [])
        plan, regs = self.prepared()
        plan["threshold_proposal"]["critical_exact_predicates"][0].update(
            failure="descriptive note", reporting="descriptive note", rationale="descriptive note"
        )
        grading._validate_plan(plan, regs, {}, [])

    def test_declared_groups_require_exact_static_repeat_registrations_before_output(self) -> None:
        for mutation in ("missing-group", "missing-repeat", "duplicate-repeat", "boolean-repeat"):
            with self.subTest(mutation=mutation):
                plan, regs = self.prepared()
                if mutation == "missing-group":
                    regs = [r for r in regs if r["row"]["condition"] != "legacy-scope"]
                elif mutation == "missing-repeat":
                    regs.pop()
                elif mutation == "duplicate-repeat":
                    regs[-1]["row"]["repeat"] = 2
                    regs[-1]["row"]["note"] = "distinct registration"
                else:
                    regs[0]["row"]["repeat"] = True
                with self.assertRaises(ValueError):
                    grading._validate_plan(plan, regs, {}, [])

    def test_typed_drawn_departure_requires_support_even_without_raw_token(self) -> None:
        plan, regs = self.prepared()
        p = plan["threshold_proposal"]["critical_exact_predicates"][0]
        p.pop("required_raw_token")
        p["required_page_state"] = "drawn-grounded-departure"
        regs[0]["admitted_support_ids"] = {}
        with self.assertRaises(ValueError):
            grading._validate_plan(plan, regs, {}, [])

    def test_typed_drawn_departure_cannot_request_a_nondeparture_result(self) -> None:
        plan, regs = self.prepared()
        p = plan["threshold_proposal"]["critical_exact_predicates"][0]
        p["required_page_state"] = "drawn-grounded-departure"
        p["required_resolved_result"] = "not departure"
        with self.assertRaises(ValueError):
            grading._validate_plan(plan, regs, {}, [])

    def test_typed_page_condition_checks_all_joint_members_without_raw_token(self) -> None:
        plan, regs = self.prepared()
        p = plan["threshold_proposal"]["critical_exact_predicates"][0]
        p.pop("required_raw_token")
        p["required_page_state"] = "drawn-grounded-departure"
        for r in regs:
            r["selected_ids"] = ["f1", "f2"]
            r["admitted_support_ids"] = {"goal": ["f1", "f2"]}
        first = regs[0]
        output = observation(first)
        output["entry"]["facts"]["f2"] = {"type": "agent_message", "at": 100}
        report = self.report(plan, regs, {first["slot"]: output})
        self.assertEqual("failed", report["verdict"])
        self.assertGreater(report["semantic_failures"], 0)
        raw = json.loads(output["entry"]["raw_verdict"])
        raw["goal"]["cites"] = [1, 2]
        output["entry"]["raw_verdict"] = json.dumps(raw)
        output["entry"]["assessment"]["criteria"]["goal"]["cites"] = ["f1", "f2"]
        output["page"]["criteria"][0]["citedIds"] = ["f1", "f2"]
        self.assertEqual("passed", self.report(plan, regs, {first["slot"]: output})["verdict"])

    def test_typed_legacy_baseline_needs_three_static_legacy_rows(self) -> None:
        plan, regs = self.prepared()
        p = plan["threshold_proposal"]["critical_exact_predicates"][0]
        p["phases_and_conditions"] = {"scope": ["turn-scope"]}
        p["legacy_scope_baseline"] = "report-all-repeats"
        regs = [r for r in regs if r["slot"] != "legacy-scope-3"]
        with self.assertRaises(ValueError):
            grading._validate_plan(plan, regs, {}, [])

    def test_typed_legacy_baseline_reports_all_results_without_favorable_expectation(self) -> None:
        plan, regs = self.prepared()
        p = plan["threshold_proposal"]["critical_exact_predicates"][0]
        p["phases_and_conditions"] = {"scope": ["turn-scope"]}
        p["legacy_scope_baseline"] = "report-all-repeats"
        outputs = {r["slot"]: observation(r) for r in regs}
        expected = (
            reading.RESULT_DEPARTURE,
            reading.RESULT_CONSISTENT,
            reading.RESULT_UNVERIFIABLE,
        )
        for n, (token, result) in enumerate(
            zip(("departure", "consistent", "unverifiable"), expected, strict=True), 1
        ):
            r = next(r for r in regs if r["slot"] == f"legacy-scope-{n}")
            outputs[r["slot"]] = observation(r, raw_result=token, result=result)
        report = self.report(plan, regs, outputs, final=True)
        self.assertEqual("passed", report["verdict"])
        baseline = report.get("legacy_scope_baselines", [])
        self.assertEqual(1, len(baseline))
        self.assertTrue(baseline[0]["complete"])
        self.assertEqual(list(expected), [r["result"] for r in baseline[0]["results"]])
        outputs.pop("legacy-scope-3")
        report = self.report(plan, regs, outputs, final=True)
        self.assertEqual("short", report["verdict"])
        self.assertFalse(report["legacy_scope_baselines"][0]["complete"])

    def test_typed_legacy_condition_refuses_malformed_phase_shapes(self) -> None:
        for phases in (None, "scope", {"scope": True}):
            with self.subTest(phases=phases):
                plan, regs = self.prepared()
                p = plan["threshold_proposal"]["critical_exact_predicates"][0]
                p["legacy_scope_baseline"] = "report-all-repeats"
                p["phases_and_conditions"] = phases
                with self.assertRaises(ValueError):
                    grading._validate_plan(plan, regs, {}, [])

    def test_report_only_legacy_baseline_cannot_also_require_a_critical_result(self) -> None:
        plan, regs = self.prepared()
        plan["threshold_proposal"]["critical_exact_predicates"][0]["legacy_scope_baseline"] = (
            "report-all-repeats"
        )
        with self.assertRaises(ValueError):
            grading._validate_plan(plan, regs, {}, [])

    def test_malformed_legacy_criterion_is_reported_as_incomplete_coverage(self) -> None:
        plan, regs = self.prepared()
        p = plan["threshold_proposal"]["critical_exact_predicates"][0]
        p["phases_and_conditions"] = {"scope": ["turn-scope"]}
        p["legacy_scope_baseline"] = "report-all-repeats"
        outputs = {r["slot"]: observation(r) for r in regs}
        outputs["legacy-scope-1"]["entry"]["assessment"]["criteria"].pop("goal")
        try:
            report = self.report(plan, regs, outputs, final=True)
        except KeyError:
            self.fail("Known malformed legacy criterion must report coverage, not escape grading")
        self.assertEqual("short", report["verdict"])
        self.assertFalse(report["legacy_scope_baselines"][0]["complete"])


class FrozenPrechargeObligations(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = operator_cases.NativeOperator()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_missing_static_critical_group_refuses_real_preparation_without_charge(self) -> None:
        f = self.fixture
        p = f.proto["threshold_proposal"]["critical_exact_predicates"][0]
        p["phases_and_conditions"]["scope"] = ["turn-scope"]
        with self.assertRaises(ValueError):
            f.seal()
            f.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])
        self.assertEqual(631, len(json.loads(f.ledger.read_text())["calls"]))
        self.assertEqual([], f.sends)

    def test_duplicate_protected_identity_cannot_replace_an_obligation_before_charge(self) -> None:
        f = self.fixture
        body = json.loads(f.frozen["protected"].read_bytes())
        body["rows"][9] = copy.deepcopy(body["rows"][8])
        self.assertEqual(10, len(body["rows"]))
        self.assertEqual(9, len({r["claim"] for r in body["rows"]}))
        self.assertEqual(4, sum(r["new_withdrawn"] for r in body["rows"]))
        f.frozen["protected"].write_text(json.dumps(body))
        with self.assertRaises(ValueError):
            f.seal()
            f.prepare()
        self.assertEqual([], campaigns.Campaign()._state()["calls"])
        self.assertEqual(631, len(json.loads(f.ledger.read_text())["calls"]))
        self.assertEqual([], f.sends)


class NoncriticalIdentityAndComparisonCoverage(unittest.TestCase):
    def pair(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        regs = [
            registration(condition, condition=condition, case="paired")
            for condition in ("legacy-scope", "turn-scope")
        ]
        for reg in regs:
            reg["expected_criteria"].append("claims")
            reg["protected_facts"] = {"kept": "f1"}
        return regs, [
            {"case": "paired", "arm": "current", "claim": "kept", "admissibility": "admitted"}
        ]

    def report(self, regs: Any, protected: Any, outputs: Any, *, final: bool) -> Any:
        return grading.grade(
            no_critical_protocol(),
            regs,
            outputs,
            due_slots=list(outputs),
            final=final,
            blind_marks=[],
            protected_rows=protected,
            reading_module=reading,
        )

    def test_noncritical_repeats_are_exact_positive_integers(self) -> None:
        for repeat in (True, False, 0, -1, 1.0, "1", None):
            with self.subTest(repeat=repeat):
                reg = registration("bad", case="paired")
                reg["row"]["repeat"] = repeat
                with self.assertRaises(ValueError):
                    grading._validate_plan(no_critical_protocol(), [reg], {}, [])

    def test_extra_row_metadata_cannot_hide_duplicate_logical_identity(self) -> None:
        reg = registration("first", condition="legacy-scope", case="paired")
        duplicate = copy.deepcopy(reg)
        duplicate["slot"] = "later"
        duplicate["row"]["note"] = "different full row digest"
        with self.assertRaises(ValueError):
            grading._validate_plan(no_critical_protocol(), [reg, duplicate], {}, [])

    def test_distinct_noncritical_positive_repeats_remain_distinct(self) -> None:
        regs = [
            registration(f"legacy-{n}", condition="legacy-scope", repeat=n, case="paired")
            for n in (1, 2, 4, 30)
        ]
        self.assertEqual(4, len(grading._validate_plan(no_critical_protocol(), regs, {}, [])))

    def test_two_undrawn_protected_claims_are_incomplete_comparison(self) -> None:
        regs, protected = self.pair()
        outputs = {reg["slot"]: observation(reg) for reg in regs}
        for final in (False, True):
            with self.subTest(final=final):
                report = self.report(regs, protected, outputs, final=final)
                self.assertEqual("short", report["verdict"])
                self.assertEqual(1, report["paired_unresolved_protected_observations"])
                self.assertEqual(0, report["protection_failures"])
                self.assertTrue(
                    any(
                        row["kind"] == "protected-key-comparison-unresolved"
                        for row in report["failures"]["coverage"]
                    )
                )
                if final:
                    self.assertFalse(report["complete"])

    def test_no_outputs_yet_defers_future_protected_comparison(self) -> None:
        regs, protected = self.pair()
        report = self.report(regs, protected, {}, final=False)
        self.assertEqual("passed", report["verdict"])
        self.assertEqual(0, report["coverage_failures"])
        self.assertEqual(0, report["paired_unresolved_protected_observations"])

    def test_protection_does_not_require_a_favorable_legacy_claim(self) -> None:
        regs, protected = self.pair()
        outputs = {reg["slot"]: observation(reg) for reg in regs}
        new = outputs["turn-scope"]
        new["entry"]["assessment"]["criteria"]["claims"].update(
            result=reading.RESULT_UNSUPPORTED,
            cites=["f1"],
        )
        raw = json.loads(new["entry"]["raw_verdict"])
        raw["claims"] = {"result": "unsupported", "cites": [1]}
        new["entry"]["raw_verdict"] = json.dumps(raw)
        next(row for row in new["page"]["criteria"] if row["key"] == "claims").update(
            result=reading.RESULT_UNSUPPORTED,
            citedIds=["f1"],
        )
        report = self.report(regs, protected, outputs, final=True)
        self.assertEqual("passed", report["verdict"])
        self.assertEqual(0, report["paired_unresolved_protected_observations"])


if __name__ == "__main__":
    unittest.main()
