"""Model-free native replay grading; no launch, store or acceptance side effects.

Counts are measured from native read/page artifacts, never from transport usability.
The operator still binds and independently reviews source/scorer/marks and artifacts.
"""

# ruff: noqa: INP001
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import abstention_ledger as authority

NATIVE_CODE_FILES = (
    "scripts/drift_closure_operator.py",
    "scripts/drift_replay.py",
    "scripts/drift_study.py",
    "scripts/levels_cases.py",
    "scripts/abstention_ledger.py",
    "scripts/analyze_campaign.py",
    "scripts/mark_abstention.py",
    "scripts/score_abstention.py",
    "scripts/drift_closure_grading.py",
    "scripts/drift_study_controls.py",
)
_PHASE_CONDITIONS = {
    "pilot": {"production"},
    "scope": {"legacy-scope", "turn-scope"},
    "words": {"reply-first1000", "newest-final-whole"},
}


def digest(value: Any) -> str:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bind_blind_sort(source: bytes, expected_sha256: str) -> list[dict[str, Any]]:
    """Verify the exact frozen 58 questions without rereading or modifying marks."""
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise ValueError("Blind source file digest changed")
    body = json.loads(source)
    marks = body.get("marks", [])
    if (
        body.get("questions") != 58
        or len(marks) != 58
        or len({r.get("id") for r in marks}) != 58
        or body.get("marks_digest") != digest(marks)
        or any(
            r.get("departure") not in {"yes", "no", "unclear"}
            or type(r.get("neutral_safe")) is not bool
            or (r["neutral_safe"] and r["departure"] != "no")
            for r in marks
        )
    ):
        raise ValueError("Blind sort coverage/digest/shape is incomplete")
    return list(marks)


def _clause(intent: dict[str, Any], name: str) -> str | None:
    if name == "goal":
        return str(intent.get("goal") or "")
    lines = intent.get("lines") or []
    if name.startswith("line_") and name[5:].isdigit() and 0 < int(name[5:]) <= len(lines):
        return str(lines[int(name[5:]) - 1])
    return None


def _criterion_checks(
    reg: dict[str, Any],
    entry: dict[str, Any],
    criteria: dict[str, Any],
    parsed: dict[str, Any],
    rows: dict[str, Any],
    reading: Any,
) -> list[str]:
    names = reg["expected_criteria"]
    failures = []
    selected = reg["selected_ids"]
    facts = entry.get("facts") or {}
    for name in names:
        row = criteria.get(name) or {}
        token = parsed[name]["token"]
        if reading.result_for(name, token) is None or row.get("result") not in reading.RESULTS:
            failures.append("requested-criterion-unparsed")
            continue
        expected_clause = _clause(reg["intent"], name)
        if expected_clause is not None and row.get("clause") != expected_clause:
            failures.append("requested-clause-changed")
        raw_ids = {
            selected[index - 1] for index in parsed[name]["cites"] if 0 < index <= len(selected)
        }
        cites = row.get("cites") or []
        if any(cite not in facts or cite not in raw_ids for cite in cites):
            failures.append("native-citation-key")
        shown = rows.get(name)
        withdrawn = name == "claims" and row.get("result") == reading.RESULT_UNVERIFIABLE
        if not shown and not withdrawn:
            failures.append("requested-page-row-missing")
        if shown and (
            shown.get("result") != row.get("result")
            or set(shown.get("citedIds") or []) != set(cites)
        ):
            failures.append("page-native-criterion-mismatch")
        if (
            row.get("result")
            in {
                reading.RESULT_DEPARTURE,
                reading.RESULT_CONSISTENT,
                reading.RESULT_UNSUPPORTED,
                reading.RESULT_NOT_REACHED,
            }
            and not cites
        ):
            failures.append("ungrounded-verdict")
    return failures


def _native(
    reg: dict[str, Any], output: dict[str, Any], reading: Any
) -> tuple[dict[str, Any], list[str]]:
    """Reconcile exact requested keys and native raw/resolved/page citation identities."""
    entry = output.get("entry") or {}
    page = output.get("page") or {}
    assessment = entry.get("assessment") or {}
    criteria = assessment.get("criteria") or {}
    names = reg["expected_criteria"]
    failures = []
    if (
        entry.get("withheld")
        or entry.get("model_status") != "ok"
        or entry.get("intent") != reg["intent"]
        or entry.get("prompt_digest") != reg["prompt_digest"]
        or not criteria
        or set(criteria) != set(names)
    ):
        failures.append("native-input-or-output")
    bindings = output.get("bindings") or {}
    if bindings.get("prompt_sha256") != reg["prompt_digest"] or any(
        key not in bindings or bindings[key] != value
        for key, value in reg["source_bindings"].items()
    ):
        failures.append("actual-source-or-final-prompt")
    raw = str(entry.get("raw_verdict") or "")
    parsed = reading.parse_reply(
        raw,
        names,
        salvage=len(raw.encode("utf-8", "replace"))
        >= reading.REPLY_CAP_BYTES - reading.REPLY_CUT_SLACK_BYTES,
    )
    page_rows = page.get("criteria") or []
    rows = {row.get("key"): row for row in page_rows}
    if len(rows) != len(page_rows) or page.get("answer") in {None, "refused", "malformed"}:
        failures.append("page-refused-or-duplicate")
    failures.extend(_criterion_checks(reg, entry, criteria, parsed, rows, reading))
    return {"criteria": criteria, "page_rows": rows, "parsed": parsed, "page": page}, failures


def _matches(predicate: dict[str, Any], row: dict[str, Any]) -> bool:
    return (
        row["case"] in predicate.get("cases", [predicate.get("case")])
        and row["arm"] == predicate["arm"]
        and row["condition"] in predicate["phases_and_conditions"].get(row["phase"], [])
    )


_SOURCE_KEYS = frozenset(
    {
        "packet_inputs_sha256",
        "window_sha256",
        "selection_sha256",
        "body_sha256",
        "intent_sha256",
        "reading_source_sha256",
        "shim_sha256",
        "contract_sha256",
    }
)


def _unique_ids(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
        and len(set(value)) == len(value)
    )


def _valid_registration(reg: dict[str, Any]) -> bool:
    row = reg.get("row")
    names = reg.get("expected_criteria") or []
    selected = reg.get("selected_ids") or []
    bound = reg.get("source_bindings") or {}
    admitted = reg.get("admitted_support_ids", {})
    protected = reg.get("protected_facts")
    return bool(
        isinstance(row, dict)
        and type(row.get("repeat")) is int
        and row["repeat"] > 0
        and _unique_ids(names)
        and len(set(names)) == len(names)
        and _unique_ids(selected)
        and isinstance(admitted, dict)
        and set(admitted) <= set(names)
        and all(_unique_ids(ids) and set(ids) <= set(selected) for ids in admitted.values())
        and set(bound) == _SOURCE_KEYS
        and all(isinstance(v, str) and re.fullmatch("[0-9a-f]{64}", v) for v in bound.values())
        and type(reg.get("no_drift")) is bool
        and type(reg.get("protect_offer")) is bool
        and isinstance(reg.get("protected_intents"), list)
        and set(reg["protected_intents"]) <= set(names)
        and isinstance(protected, dict)
        and all(
            isinstance(key, str) and key.strip() and value in selected
            for key, value in protected.items()
        )
        and (not protected or "claims" in names)
        and isinstance(reg.get("blind_source_bindings"), dict)
        and re.fullmatch("[0-9a-f]{64}", str(reg.get("request_digest")))
        and re.fullmatch("[0-9a-f]{64}", str(reg.get("prompt_digest")))
    )


def _validate_predicates(predicates: Any) -> None:
    required = {"arm", "criterion", "k", "n", "phases_and_conditions", "required_resolved_result"}
    optional = {
        "case",
        "cases",
        "required_raw_token",
        "failure",
        "required_page_state",
        "legacy_scope_baseline",
        "rationale",
        "reporting",
    }
    if not isinstance(predicates, list):
        raise TypeError("Critical predicates must be a list")
    for p in predicates:
        if not isinstance(p, dict) or not required <= set(p) or set(p) - required - optional:
            raise ValueError("Critical predicate shape is unknown")
        # These notes describe the reviewed protocol; they add no executable
        # obligation beyond the typed fields validated below.
        if any(
            key in p and (not isinstance(p[key], str) or not p[key].strip())
            for key in ("failure", "reporting", "rationale")
        ):
            raise ValueError("Descriptive critical notes must be nonempty strings")
        if "required_page_state" in p and (
            p["required_page_state"] != "drawn-grounded-departure"
            or p["required_resolved_result"] != "departure"
        ):
            raise ValueError("Unsupported executable critical page condition")
        if "legacy_scope_baseline" in p and p["legacy_scope_baseline"] != "report-all-repeats":
            raise ValueError("Unsupported executable legacy baseline condition")
        cases = p.get("cases") if "cases" in p else [p.get("case")]
        phases = p["phases_and_conditions"]
        if (
            ("case" in p) == ("cases" in p)
            or not _unique_ids(cases)
            or p["arm"] not in {"current", "adopted"}
            or not isinstance(p["criterion"], str)
            or not re.fullmatch(r"goal|claims|line_[1-9][0-9]*", p["criterion"])
            or type(p["k"]) is not int
            or type(p["n"]) is not int
            or p["k"] != 3
            or p["n"] != 3
            or p["required_resolved_result"] not in {"departure", "not departure"}
            or not isinstance(phases, dict)
            or not phases
            or any(
                phase not in _PHASE_CONDITIONS
                or not _unique_ids(conditions)
                or not set(conditions) <= _PHASE_CONDITIONS[phase]
                for phase, conditions in phases.items()
            )
            or (
                "required_raw_token" in p
                and (
                    not isinstance(p["required_raw_token"], str)
                    or p["required_raw_token"].casefold()
                    not in {"departure", "consistent", "unverifiable", "not_reached", "unsupported"}
                )
            )
        ):
            raise ValueError("Critical predicate does not bind declared cases/criteria/conditions")
        if p.get("legacy_scope_baseline") and "legacy-scope" in phases.get("scope", []):
            raise ValueError("Report-only legacy baseline overlaps a critical result condition")


def _validate_protected_pairs(registrations: list[dict[str, Any]]) -> None:
    paired: dict[tuple[Any, ...], dict[str, Any]] = {}
    for reg in registrations:
        row = reg["row"]
        if row["phase"] not in {"scope", "words"}:
            continue
        key = (row["phase"], row["case"], row["arm"], row["repeat"])
        fields = {
            name: reg[name] for name in ("protected_facts", "protected_intents", "protect_offer")
        }
        if key in paired and paired[key] != fields:
            raise ValueError("Paired static protection bindings differ")
        paired[key] = fields


def _critical_registrations(
    predicate: dict[str, Any], registrations: list[dict[str, Any]]
) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {
        (phase, condition, case, predicate["arm"]): []
        for case in predicate.get("cases", [predicate.get("case")])
        for phase, conditions in predicate["phases_and_conditions"].items()
        for condition in conditions
    }
    for reg in registrations:
        row = reg["row"]
        if _matches(predicate, row):
            grouped[(row["phase"], row["condition"], row["case"], row["arm"])].append(reg)
    return grouped


def _legacy_registrations(
    predicate: dict[str, Any], registrations: list[dict[str, Any]]
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    return {
        (case, predicate["arm"]): [
            r
            for r in registrations
            if (r["row"]["case"], r["row"]["arm"], r["row"]["phase"], r["row"]["condition"])
            == (case, predicate["arm"], "scope", "legacy-scope")
        ]
        for case in predicate.get("cases", [predicate.get("case")])
    }


def _require_three_registered(regs: list[dict[str, Any]]) -> None:
    if (
        len(regs) != 3
        or any(type(r["row"].get("repeat")) is not int for r in regs)
        or {r["row"]["repeat"] for r in regs} != {1, 2, 3}
    ):
        raise ValueError("Every declared critical/baseline group needs static repeats 1/2/3")


def _require_criterion_source(reg: dict[str, Any], predicate: dict[str, Any], sources: Any) -> None:
    name = predicate["criterion"]
    source = sources.get((reg["row"]["case"], reg["row"]["arm"])) or {}
    if name not in reg["expected_criteria"] or name not in source.get(
        "criterion_clause_sha256", {}
    ):
        raise ValueError("Critical requested criterion or original source reference is missing")


def _validate_semantic_groups(
    predicates: list[dict[str, Any]], registrations: list[dict[str, Any]], sources: Any
) -> None:
    for predicate in predicates:
        for regs in _critical_registrations(predicate, registrations).values():
            _require_three_registered(regs)
            for reg in regs:
                _require_criterion_source(reg, predicate, sources)
                if not (
                    predicate.get("required_raw_token") or predicate.get("required_page_state")
                ):
                    continue
                admitted = (reg.get("admitted_support_ids") or {}).get(predicate["criterion"])
                if not _unique_ids(admitted) or not set(admitted or []) <= set(reg["selected_ids"]):
                    raise ValueError(
                        "Critical semantic support is not independently admitted before output"
                    )
        if predicate.get("legacy_scope_baseline"):
            for regs in _legacy_registrations(predicate, registrations).values():
                _require_three_registered(regs)
                for reg in regs:
                    _require_criterion_source(reg, predicate, sources)


def _validate_plan(
    protocol: dict[str, Any],
    registrations: list[dict[str, Any]],
    outputs: dict[str, Any],
    due_slots: list[str],
) -> dict[str, Any]:
    if any(not _valid_registration(reg) for reg in registrations) or len(
        {
            tuple(reg["row"][name] for name in ("phase", "case", "arm", "condition", "repeat"))
            for reg in registrations
        }
    ) != len(registrations):
        raise ValueError(
            "Registration lacks measured source/criteria/guard fields or repeats a row"
        )
    by_slot = {r["slot"]: r for r in registrations}
    if (
        len(by_slot) != len(registrations)
        or len(set(due_slots)) != len(due_slots)
        or not set(due_slots) <= set(by_slot)
        or not set(outputs) <= set(by_slot)
    ):
        raise ValueError("Slot coverage is outside the frozen plan")
    predicates = protocol["threshold_proposal"]["critical_exact_predicates"]
    _validate_predicates(predicates)
    _validate_protected_pairs(registrations)
    sources = {(s["case"], s["arm"]): s for s in protocol["critical_input_binding"]["cases"]}
    _validate_semantic_groups(predicates, registrations, sources)
    return by_slot


def _bound_mark(
    mark: dict[str, Any] | None,
    reg: dict[str, Any],
    name: str,
    criterion: dict[str, Any],
    slot: str,
    coverage: list[dict[str, Any]],
    original_source_digest: str,
) -> dict[str, Any] | None:
    if mark:
        bound = reg["blind_source_bindings"].get(name) or {}
        if (
            bound.get("source_artifact_sha256") != original_source_digest
            or bound.get("saved_revision_sha256") != digest(reg["intent"])
            or bound.get("criterion_clause_sha256") != digest(criterion.get("clause", ""))
        ):
            mark = None
            coverage.append({"slot": slot, "kind": "blind-source-clause-or-revision"})
    return mark


def _observe(
    protocol: dict[str, Any],
    by_slot: dict[str, Any],
    outputs: dict[str, Any],
    blind_marks: list[dict[str, Any]],
    reading_module: Any,
    coverage: list[dict[str, Any]],
    semantic: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    observations = {}
    source_inputs = {(r["case"], r["arm"]): r for r in protocol["critical_input_binding"]["cases"]}
    marks = {r["id"]: r for r in blind_marks}
    if len(marks) != len(blind_marks):
        raise ValueError("Duplicate blind question")
    blind_outcomes = []
    for slot, output in outputs.items():
        reg = by_slot[slot]
        obs, failures = _native(reg, output, reading_module)
        observations[slot] = obs
        coverage.extend({"slot": slot, "kind": failure} for failure in failures)
        source = source_inputs.get((reg["row"]["case"], reg["row"]["arm"]))
        if source and (
            digest(reg["intent"]) != source["saved_revision_sha256"]
            or any(
                name not in obs["criteria"]
                or digest(obs["criteria"][name].get("clause", "")) != clause
                for name, clause in source["criterion_clause_sha256"].items()
            )
        ):
            coverage.append({"slot": slot, "kind": "critical-source-clause-or-revision"})
        for name, criterion in obs["criteria"].items():
            mark = (
                marks.get(reg["row"]["case"] + "-" + name)
                if reg["row"]["arm"] == "current"
                else None
            )
            mark = _bound_mark(
                mark,
                reg,
                name,
                criterion,
                slot,
                coverage,
                protocol["critical_input_binding"]["current_intents_file_sha256"],
            )
            if mark:
                blind_outcomes.append(
                    {
                        "slot": slot,
                        "criterion": name,
                        "departure": mark["departure"],
                        "actual": criterion.get("result"),
                        "judgment": "unknown"
                        if mark["departure"] == "unclear"
                        else "reported-only",
                    }
                )
            if criterion.get("result") == reading_module.RESULT_NOT_REACHED:
                if not mark:
                    coverage.append({"slot": slot, "kind": "neutral-source-unbound"})
                elif mark.get("neutral_safe") is not True or mark.get("departure") != "no":
                    semantic.append({"slot": slot, "kind": "unsafe-not-reached"})
        obs["valid"] = not any(f.get("slot") == slot for f in coverage)
    return observations, blind_outcomes


def _critical(
    protocol: dict[str, Any],
    registrations: list[dict[str, Any]],
    observations: dict[str, Any],
    reading_module: Any,
    coverage: list[dict[str, Any]],
    semantic: list[dict[str, Any]],
    *,
    final: bool,
) -> list[dict[str, Any]]:
    predicates = protocol["threshold_proposal"]["critical_exact_predicates"]
    groups = []
    for predicate in predicates:
        grouped = _critical_registrations(predicate, registrations)
        for key, regs in grouped.items():
            successful = 0
            for reg in regs:
                slot = reg["slot"]
                if slot not in observations:
                    continue
                obs = observations[slot]
                name = predicate["criterion"]
                native = obs["criteria"].get(name) or {}
                shown = obs["page_rows"].get(name) or {}
                actual = native.get("result")
                expected = predicate["required_resolved_result"]
                okay = (
                    obs["valid"]
                    and actual is not None
                    and shown.get("result") == actual
                    and (
                        actual != reading_module.RESULT_DEPARTURE
                        if expected == "not departure"
                        else actual == expected
                    )
                )
                if predicate.get("required_raw_token") or predicate.get("required_page_state"):
                    parsed = obs["parsed"].get(name) or {}
                    raw_ids = {
                        reg["selected_ids"][index - 1]
                        for index in parsed.get("cites", [])
                        if 0 < index <= len(reg["selected_ids"])
                    }
                    okay = (
                        okay
                        and (
                            not predicate.get("required_raw_token")
                            or parsed.get("token") == predicate["required_raw_token"].casefold()
                        )
                        and set(reg["admitted_support_ids"][name])
                        <= (
                            raw_ids
                            & set(native.get("cites") or [])
                            & set(shown.get("citedIds") or [])
                        )
                    )
                if okay:
                    successful += 1
                else:
                    semantic.append(
                        {"slot": slot, "kind": "critical-exact-criterion", "criterion": name}
                    )
            complete = (
                len(regs) == 3
                and {r["row"]["repeat"] for r in regs} == {1, 2, 3}
                and all(r["slot"] in observations for r in regs)
            )
            if final and not complete:
                coverage.append({"kind": "critical-three-repeat-coverage"})
            groups.append(
                {
                    "phase": key[0],
                    "condition": key[1],
                    "criterion": predicate["criterion"],
                    "passed": successful,
                    "expected": 3,
                    "complete": complete,
                }
            )
    return groups


def _legacy_baselines(
    protocol: dict[str, Any],
    registrations: list[dict[str, Any]],
    observations: dict[str, Any],
    coverage: list[dict[str, Any]],
    *,
    final: bool,
) -> list[dict[str, Any]]:
    baselines = []
    for predicate in protocol["threshold_proposal"]["critical_exact_predicates"]:
        if not predicate.get("legacy_scope_baseline"):
            continue
        for (case, arm), regs in _legacy_registrations(predicate, registrations).items():
            results = []
            for reg in sorted(regs, key=lambda r: r["row"]["repeat"]):
                obs = observations.get(reg["slot"])
                if obs is not None:
                    results.append(
                        {
                            "slot": reg["slot"],
                            "repeat": reg["row"]["repeat"],
                            "result": (obs["criteria"].get(predicate["criterion"]) or {}).get(
                                "result"
                            ),
                        }
                    )
            complete = len(results) == 3 and all(
                observations[r["slot"]]["valid"] for r in regs if r["slot"] in observations
            )
            if final and not complete:
                coverage.append(
                    {
                        "kind": "legacy-scope-three-repeat-coverage",
                        "case": case,
                        "arm": arm,
                        "criterion": predicate["criterion"],
                    }
                )
            baselines.append(
                {
                    "case": case,
                    "arm": arm,
                    "criterion": predicate["criterion"],
                    "complete": complete,
                    "results": results,
                }
            )
    return baselines


def _no_drift(
    registrations: list[dict[str, Any]],
    observations: dict[str, Any],
    reading_module: Any,
    semantic: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    nd_groups = []
    cohorts: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for reg in registrations:
        if (
            reg["no_drift"]
            and reg["row"]["repeat"] == 1
            and reg["row"]["phase"] in {"scope", "words"}
        ):
            cohorts[(reg["row"]["phase"], reg["group"], reg["row"]["arm"])].append(reg)

    def is_departed(reg: dict[str, Any]) -> bool:
        return any(
            name != "claims" and row.get("result") == reading_module.RESULT_DEPARTURE
            for name, row in observations[reg["slot"]]["page_rows"].items()
        )

    for key, regs in cohorts.items():
        conditions = (
            ("legacy-scope", "turn-scope")
            if key[0] == "scope"
            else ("reply-first1000", "newest-final-whole")
        )
        count = {
            condition: sum(
                is_departed(reg)
                for reg in regs
                if reg["row"]["condition"] == condition and reg["slot"] in observations
            )
            for condition in conditions
        }
        pending = any(reg["slot"] not in observations for reg in regs)
        nd_groups.append(
            {
                "phase": key[0],
                "group": key[1],
                "arm": key[2],
                "A": count[conditions[0]],
                "B": count[conditions[1]],
                "pending": pending,
            }
        )
        if not pending and count[conditions[1]] > count[conditions[0]]:
            semantic.append({"kind": "grouped-no-drift-increase"})
    return nd_groups


def _claim_drawn(row: dict[str, Any], fact: str) -> bool:
    return row.get("result") in {
        "departure",
        "consistent with the evidence read",
        "not shown by the record",
    } and fact in (row.get("citedIds") or [])


def _claim_protections(
    left: dict[str, Any],
    right: dict[str, Any],
    lo: dict[str, Any],
    ro: dict[str, Any],
    protected_rows: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    protection: list[dict[str, Any]],
) -> int:
    unresolved = 0
    for old in protected_rows:
        if (old["case"], old["arm"]) != (left["row"]["case"], left["row"]["arm"]):
            continue
        if old.get("admissibility", "unknown") != "admitted":
            coverage.append({"kind": "protected-source-admissibility-unknown"})
        claim = old["claim"]
        fact = left["protected_facts"].get(claim)
        if fact is None or right["protected_facts"].get(claim) != fact:
            coverage.append({"kind": "protected-source-key-unbound"})
            continue
        drawn_a = _claim_drawn(lo["page_rows"].get("claims") or {}, fact)
        drawn_b = _claim_drawn(ro["page_rows"].get("claims") or {}, fact)
        if drawn_a and not drawn_b:
            protection.append(
                {"A": left["slot"], "B": right["slot"], "kind": "protected-key-withdrawn"}
            )
        if not drawn_a and not drawn_b:
            unresolved += 1
            coverage.append(
                {
                    "A": left["slot"],
                    "B": right["slot"],
                    "claim": claim,
                    "kind": "protected-key-comparison-unresolved",
                }
            )
    return unresolved


def _compare_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    observations: dict[str, Any],
    reading_module: Any,
    protected_rows: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    protection: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    discordances = []
    lo, ro = observations[left["slot"]], observations[right["slot"]]
    for name in set(lo["criteria"]) | set(ro["criteria"]):
        a = (lo["criteria"].get(name) or {}).get("result")
        b = (ro["criteria"].get(name) or {}).get("result")
        if a != b:
            discordances.append(
                {
                    "A": left["slot"],
                    "B": right["slot"],
                    "criterion": name,
                    "A_result": a,
                    "B_result": b,
                }
            )
    unresolved = _claim_protections(left, right, lo, ro, protected_rows, coverage, protection)
    for name, row in lo["page_rows"].items():
        if (
            name in left["protected_intents"]
            and row.get("result") == reading_module.RESULT_DEPARTURE
            and (ro["page_rows"].get(name) or {}).get("result") != reading_module.RESULT_DEPARTURE
        ):
            protection.append(
                {
                    "A": left["slot"],
                    "B": right["slot"],
                    "kind": "intent-row-withdrawn",
                    "criterion": name,
                }
            )
    if (
        left["protect_offer"]
        and lo["page"].get("page_state") in {"steer-primary", "steer-secondary"}
        and ro["page"].get("page_state") not in {"steer-primary", "steer-secondary"}
    ):
        protection.append({"A": left["slot"], "B": right["slot"], "kind": "offer-withdrawn"})
    return discordances, unresolved


def _paired(
    registrations: list[dict[str, Any]],
    observations: dict[str, Any],
    reading_module: Any,
    protected_rows: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    protection: list[dict[str, Any]],
    *,
    final: bool,
) -> tuple[list[dict[str, Any]], int, int]:
    discordances = []
    pairs: dict[tuple[str, str, str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for reg in registrations:
        row = reg["row"]
        if row["phase"] in {"scope", "words"}:
            pairs[(row["phase"], row["case"], row["arm"], row["repeat"])][row["condition"]] = reg
    unresolved = 0
    compared: set[tuple[str, str, str]] = set()
    protected_outside = 0
    for key, arms in pairs.items():
        conditions = (
            ("legacy-scope", "turn-scope")
            if key[0] == "scope"
            else ("reply-first1000", "newest-final-whole")
        )
        left, right = (arms.get(condition) for condition in conditions)
        if not left or not right:
            if final:
                coverage.append({"kind": "paired-registration-missing"})
            continue
        if left["slot"] not in observations or right["slot"] not in observations:
            continue
        differences, missing = _compare_pair(
            left, right, observations, reading_module, protected_rows, coverage, protection
        )
        discordances.extend(differences)
        unresolved += missing
        compared.update(
            (old["case"], old["arm"], old["claim"])
            for old in protected_rows
            if (old["case"], old["arm"]) == (left["row"]["case"], left["row"]["arm"])
        )
    for old in protected_rows:
        if final and (old["case"], old["arm"], old["claim"]) not in compared:
            coverage.append({"kind": "required-protected-comparison-missing"})
        if not any(
            (reg["row"]["case"], reg["row"]["arm"]) == (old["case"], old["arm"])
            for reg in registrations
        ):
            protected_outside += 1
    return discordances, unresolved, protected_outside


def _validate_protected_sources(
    registrations: list[dict[str, Any]], protected: list[dict[str, Any]]
) -> None:
    for old in protected:
        matched = [
            r
            for r in registrations
            if (r["row"]["case"], r["row"]["arm"]) == (old["case"], old["arm"])
        ]
        if not matched or any(
            "claims" not in r["expected_criteria"]
            or r.get("protected_facts", {}).get(old["claim"]) not in r["selected_ids"]
            for r in matched
        ):
            raise ValueError("Required historical protection has no selected original claim source")


def _valid_code_binding(binding: Any) -> bool:
    return bool(
        isinstance(binding, dict)
        and set(binding) == {"commit", "files"}
        and isinstance(binding["commit"], str)
        and re.fullmatch("[0-9a-f]{40}", binding["commit"])
        and isinstance(binding["files"], dict)
        and set(binding["files"]) == set(NATIVE_CODE_FILES)
        and all(
            isinstance(v, str) and re.fullmatch("[0-9a-f]{64}", v)
            for v in binding["files"].values()
        )
    )


def grade(
    protocol: dict[str, Any],
    registrations: list[dict[str, Any]],
    outputs: dict[str, Any],
    *,
    due_slots: list[str],
    final: bool,
    blind_marks: list[dict[str, Any]],
    protected_rows: list[dict[str, Any]],
    reading_module: Any,
) -> dict[str, Any]:
    """Grade cumulative native observations, allowing only future slots to be pending.

    `due_slots` contains every registered slot scheduled through this batch, including
    prior batches. Full-lane grading requires every registration. A successful batch
    is only prospective partial acceptance; it cannot relabel original failure.
    """
    by_slot = _validate_plan(protocol, registrations, outputs, due_slots)
    due = set(by_slot) if final else set(due_slots)
    coverage = [
        {"slot": slot, "kind": "registered-output-missing"} for slot in sorted(due - set(outputs))
    ]
    semantic: list[dict[str, Any]] = []
    protection: list[dict[str, Any]] = []
    observations, blind_outcomes = _observe(
        protocol, by_slot, outputs, blind_marks, reading_module, coverage, semantic
    )
    groups = _critical(
        protocol, registrations, observations, reading_module, coverage, semantic, final=final
    )
    baselines = _legacy_baselines(protocol, registrations, observations, coverage, final=final)
    nd_groups = _no_drift(registrations, observations, reading_module, semantic)
    discordances, unresolved, protected_outside = _paired(
        registrations,
        observations,
        reading_module,
        protected_rows,
        coverage,
        protection,
        final=final,
    )
    verdict = "failed" if semantic or protection else "short" if coverage else "passed"
    report = {
        "v": 1,
        "scope": "prospective-limited-development-study"
        if protocol["threshold_proposal"]["critical_exact_predicates"]
        else "model-free-controls-not-qualification",
        "original_campaign": "FAILED-unrepaired",
        "verdict": verdict,
        "complete": final and not coverage and len(observations) == len(registrations),
        "expected_slots": len(due),
        "observed_slots": len(observations),
        "pending_slots": len(set(by_slot) - set(observations)),
        "semantic_failures": len(semantic),
        "coverage_failures": len(coverage),
        "protection_failures": len(protection),
        "failures": {"semantic": semantic, "coverage": coverage, "protection": protection},
        "critical_groups": groups,
        "legacy_scope_baselines": baselines,
        "nd_groups": nd_groups,
        "discordances": discordances,
        "blind_outcomes": blind_outcomes,
        "historical_protected_rows": len(protected_rows),
        "historical_unique_claims": len({r["claim"] for r in protected_rows}),
        "historical_withdrawn_rows": sum(r.get("new_withdrawn") is True for r in protected_rows),
        "unknown_protected_rows": sum(
            r.get("admissibility", "unknown") == "unknown" for r in protected_rows
        ),
        "original_guard_unmeasured_rows": protected_outside,
        "paired_unresolved_protected_observations": unresolved,
        "input_digest": digest(
            {
                "protocol": protocol,
                "registrations": registrations,
                "marks": blind_marks,
                "protected": protected_rows,
            }
        ),
        "outputs_digest": digest(outputs),
    }
    report["report_digest"] = digest(report)
    return report


def grade_frozen(  # noqa: PLR0913 - four distinct frozen artifacts and exact native grade scope
    protocol_source: bytes,
    registered_source: bytes,
    blind_source: bytes,
    protected_source: bytes,
    expected_hashes: dict[str, str],
    outputs: dict[str, Any],
    *,
    due_slots: list[str],
    final: bool,
    reading_module: Any,
) -> dict[str, Any]:
    """Bind reviewed source-only prerequisites before grading native artifacts."""
    for key, source in (
        ("protocol", protocol_source),
        ("registrations", registered_source),
        ("protected", protected_source),
    ):
        if hashlib.sha256(source).hexdigest() != expected_hashes[key]:
            raise ValueError("Frozen grading input changed")
    protocol = json.loads(protocol_source)
    registrations = json.loads(registered_source)
    marks = bind_blind_sort(blind_source, protocol["input_digest_bindings"]["scope_sort"])
    protected = json.loads(protected_source)["rows"]
    if (
        protocol.get("v") != 4
        or len(registrations) != 190
        or [r["row"] for r in registrations] != protocol["call_rows"]
    ):
        raise ValueError("Frozen grading registrations differ from the 190-row protocol")
    if not protocol.get("threshold_proposal", {}).get("critical_exact_predicates"):
        raise ValueError("A frozen qualification cannot omit all critical predicates")
    if not _valid_code_binding(protocol["input_digest_bindings"].get("native_code_binding")):
        raise ValueError("The frozen native implementation inventory is incomplete")
    if (
        len(protected) != 10
        or len({(r["case"], r["arm"], r["claim"]) for r in protected}) != 10
        or len({r["claim"] for r in protected}) != 9
        or any(r.get("old_protected") is not True for r in protected)
        or sum(r.get("new_withdrawn") is True for r in protected) != 4
    ):
        raise ValueError("Original ten-row nine-key protection and four losses must remain")
    _validate_plan(protocol, registrations, {}, [])
    _validate_protected_sources(registrations, protected)
    for mark in marks:
        case, name = mark["id"].split("-", 1)
        matched = [
            r for r in registrations if (r["row"]["case"], r["row"]["arm"]) == (case, "current")
        ]
        if not matched or any(
            (r.get("blind_source_bindings", {}).get(name) or {}).get("source_artifact_sha256")
            != protocol["critical_input_binding"]["current_intents_file_sha256"]
            or (r.get("blind_source_bindings", {}).get(name) or {}).get("saved_revision_sha256")
            != digest(r["intent"])
            or (r.get("blind_source_bindings", {}).get(name) or {}).get("criterion_clause_sha256")
            != digest(_clause(r["intent"], name))
            for r in matched
        ):
            raise ValueError(
                "Blind question no longer binds the actual current saved revision/clause"
            )
    report = grade(
        protocol,
        registrations,
        outputs,
        due_slots=due_slots,
        final=final,
        blind_marks=marks,
        protected_rows=protected,
        reading_module=reading_module,
    )
    report.pop("report_digest")
    report["frozen_protocol_digest"] = expected_hashes["protocol"]
    report["native_code_binding"] = protocol["input_digest_bindings"].get("native_code_binding")
    report["due_slots"] = list(due_slots) if not final else [r["slot"] for r in registrations]
    report["observed_slot_ids"] = list(outputs)
    report["request_bindings"] = {r["slot"]: r["request_digest"] for r in registrations}
    report["evidence"] = {
        "scorer": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source": expected_hashes["registrations"],
        "marks": digest(
            {
                "blind": hashlib.sha256(blind_source).hexdigest(),
                "protected": expected_hashes["protected"],
            }
        ),
    }
    report["report_digest"] = digest(report)
    return report


def acceptance_proof(
    report: dict[str, Any],
    context: dict[str, Any],
    calls: list[dict[str, Any]],
    slots: list[str],
    *,
    review_digest: str,
    batch: int | None,
) -> dict[str, Any]:
    """Derive the guard's receipt only from a complete scoped, reviewed native grade.

    No side effect: the root separately invokes accept_batch/accept or stop. A batch
    may have pending future guards, but lane acceptance requires complete coverage.
    """
    integrity = digest({key: value for key, value in report.items() if key != "report_digest"})
    counts = ("semantic_failures", "coverage_failures", "protection_failures")
    if (
        report.get("report_digest") != integrity
        or report.get("verdict") != "passed"
        or any(type(report.get(key)) is not int or report[key] != 0 for key in counts)
    ):
        raise ValueError("A failed or short native grade cannot be accepted")
    if batch is None and report.get("complete") is not True:
        raise ValueError("Partial batch coverage cannot qualify the lane")
    if (
        context.get("binding") != report.get("frozen_protocol_digest")
        or context.get("evidence") != report.get("evidence")
        or not slots
        or len(set(slots)) != len(slots)
        or not set(slots) <= set(report.get("due_slots") or [])
        or not set(slots) <= set(report.get("observed_slot_ids") or [])
    ):
        raise ValueError("Acceptance source and planned observations are unbound")
    if re.fullmatch("[0-9a-f]{64}", review_digest) is None or review_digest == "0" * 64:
        raise ValueError("A real independent review digest is required")
    own = [call for call in calls if call.get("lane") == "replay" and call.get("slot") in slots]
    latest = {call["slot"]: call.get("status") for call in own}
    if any(
        call.get("status") != "usable"
        or call.get("binding") != report["request_bindings"].get(call["slot"])
        for call in own
    ) or any(latest.get(slot) != "usable" for slot in slots):
        raise ValueError("Actual charged attempts do not have complete usable native outputs")
    proof = {
        "v": 1,
        "lane": "replay",
        "manifest_digest": context["manifest_digest"],
        "protocol": context["protocol"],
        "binding": context["binding"],
        "evidence": context["evidence"],
        "slots_digest": authority.digest(slots),
        "attempts_digest": authority.digest(own),
        "charged_attempts": len(own),
        "expected_slots": len(slots),
        "usable_slots": sum(latest.get(slot) == "usable" for slot in slots),
        **{key: report[key] for key in counts},
        "verdict": report["verdict"],
        "output_digest": report["report_digest"],
        "review_digest": review_digest,
    }
    if batch is not None:
        proof["batch"] = batch
    return proof
