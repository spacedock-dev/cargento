#!/usr/bin/env python3
"""Compose and check the two receipts the React default flip stands on.

`fluidity` composes three complete runs of `frontend_fluidity.mjs` into
`docs/frontend-fluidity.json` and judges them against the budgets the pre-React receipt
(`docs/frontend-baseline.json`) fixes. That baseline is historical: its probe and fixture were
removed with the previous interface, so it is read, never re-measured, and its control runs (the
unchanged baseline driver, run again beside the React runs) are kept as they were taken.
`check` re-derives the fluidity receipt from its embedded runs, so a hand-edited verdict fails, and
checks the mapped cutover receipt
(`docs/frontend-cutover-receipt.json`): every row of the ownership map in
`scripts/frontend-migration.json` must name a React-side proof that exists, or be recorded as a
deviation, a deferral with an owner, or an explicit gap. Nothing here starts a browser, a server
or a model; the measurement itself is `frontend_fluidity.mjs`.
"""

from __future__ import annotations

import argparse
import ast
import functools
import hashlib
import json
import re
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_plugins import heading_slugs  # noqa: E402 - the validator owns the anchor grammar

BASELINE = "docs/frontend-baseline.json"
FLUIDITY = "docs/frontend-fluidity.json"
RECEIPT = "docs/frontend-cutover-receipt.json"
INVENTORY = "scripts/frontend-migration.json"
REACT_DOCUMENT = "cargento/skills/cargento/cargento_runtime/web/react.integrity.json"
WORKFLOW = ".github/workflows/quality-gate.yml"
PRODUCTION_RUNNER = "frontend/e2e/production-proofs.mjs"
PRODUCTION_COMMAND = "pnpm test:production:browser"
PRODUCTION_SHARDS = "frontend/e2e/production-shards.json"
# The parity proofs the production-bundle job must run between its shards; nothing else stands in.
PARITY_SCRIPTS = frozenset(
    f"test:{name}:browser"
    for name in (
        "storage",
        "shell",
        "controls",
        "sessions",
        "intent",
        "drift",
        "project",
        "console",
        "attention",
        "capacity",
        "terminal",
    )
)
# Not a parity proof: the computed-style contract that replaced the legacy stylesheet guards also
# runs on the shipped bundle.
EXTRA_PRODUCTION_PROOFS = frozenset({"test:css:browser"})
# The sources a measurement is taken with. A receipt records two digests of each: what the runs were
# taken with (`source_bindings`, embedded in every run and never rewritten) and what the tree holds
# when the receipt was last composed (`current_sources`, checked against the files).
SCRIPTS = {
    "driver": "scripts/frontend_fluidity.mjs",
    "fixture": "scripts/frontend_fluidity_fixture.py",
}
BASELINE_STATUS = (
    "Historical. The pre-React baseline's probe and fixture were removed with the previous "
    "interface, so it cannot be re-measured: its budgets derive from the runs embedded in "
    "docs/frontend-baseline.json, which is bound here by digest, and its control runs are kept as "
    "they were taken."
)
COHORTS = ("small", "median", "large")
COHORT_SIZES = {"small": 5, "median": 50, "large": 250}
GROUPS = ("parts", "surfaces", "routes", "reader_state", "storage")
STATUSES = frozenset({"proven", "deviation", "deferred", "gap"})
COLUMNS = ("keyboard", "narrow", "zoom", "editor")
ENVIRONMENT_KEYS = ("node", "platform", "release", "arch", "cores", "chrome")
SAMPLES = 3
NAVIGATIONS = 5
STATES_PER_COHORT = 2  # empty and unavailable
# The baseline's budget policy: a timing budget is the baseline median x 1.5 + 50 ms.
TIMING_FACTOR = 1.5
TIMING_ALLOWANCE_MS = 50.0
# The baseline states no long-task budget. Its recorded total is 0 ms, so the same formula gives a
# derived allowance, and the verdict says that it is derived rather than stated.
LONG_TASK_BASELINE_MS = 0.0
# The counters read on every navigation round.
SETTLING = (
    "jsEventListeners",
    "activeMainWindowTimeouts",
    "activeMainWindowIntervals",
    "activeWebSockets",
    "eventSourceConnections",
)
# Counters that must be exactly constant across the rounds once garbage is collected before each
# reading. The uncollected series is recorded beside them as `gc_pending`, not judged: see
# GC_PENDING_RULING.
COLLECTED = (*SETTLING, "nodes", "documents")
LEGACY_RAW = ("jsEventListeners", "nodes", "documents")
GC_PENDING_RULING = (
    "Ruled by the migration lead at cutover review on 2026-10-09, under the owner's standing "
    "delegation; the owner has not reviewed it. Resource counts must settle rather than grow with "
    "navigation, and retained growth is what matters, so the settle criterion is evaluated after a "
    "forced collection before each reading. The series read with no collection forced is recorded "
    "here as gc_pending, informational and not a budget, beside the legacy page's own raw series."
)
REPLACEMENTS = ("editedNodeReplacements", "openDisclosureReplacements", "focusedSelectReplacements")
STEP_CALL = re.compile(
    r"""\bstep\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`([^`]*)`)""", re.DOTALL
)


def digest(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def budget(median: float) -> float:
    return median * TIMING_FACTOR + TIMING_ALLOWANCE_MS


def count_of(metric: Any) -> int | None:
    """A counter's value, or None where the run says it did not observe it."""
    if isinstance(metric, dict):
        metric = metric.get("open")
    return metric if type(metric) is int else None


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- fluidity


def baseline_medians(baseline: dict[str, Any]) -> dict[str, dict[str, float]]:
    """The baseline's per-cohort medians, recomputed from its three embedded runs."""
    runs = baseline["runs"]
    result: dict[str, dict[str, float]] = {}
    for index, cohort in enumerate(COHORTS):
        first = [run["cohorts"][index]["firstRenderMs"] for run in runs]
        polls = [u["getToPaintMs"] for run in runs for u in run["cohorts"][index]["updates"]]
        result[cohort] = {
            "new_document_median_ms": statistics.median(first),
            "poll_median_ms": statistics.median(polls),
        }
    return result


def _cohort_problems(cohort: dict[str, Any]) -> list[str]:
    name = cohort["cohort"]
    problems = []
    if len(cohort["updates"]) != SAMPLES or len(cohort["states"]) != STATES_PER_COHORT:
        problems.append(f"{name}: updates or states are missing")
    if cohort["fixture"]["session_count"] != COHORT_SIZES[name]:
        problems.append(f"{name}: the fixture size is not the baseline's")
    return problems


def run_problems(run: dict[str, Any]) -> list[str]:
    """Why a run is not a complete React run measured the way the baseline was; empty if it is."""
    if run.get("fatal"):
        return [f"run is incomplete: {str(run['fatal'])[:120]}"]
    if run.get("schema") != 1:
        return ["run does not use schema 1"]
    if [c.get("cohort") for c in run.get("cohorts", [])] != list(COHORTS):
        return ["run does not hold the small, median and large cohorts in order"]
    problems = [problem for cohort in run["cohorts"] for problem in _cohort_problems(cohort)]
    problems += [
        f"{key} was not measured"
        for key in ("editor", "retention")
        if run.get(key, {}).get("status") != "measured"
    ]
    problems += [
        f"the {key} series is not complete"
        for key in ("navigation", "navigationAfterCollection")
        if len(run.get(key, [])) != NAVIGATIONS + 1
    ]
    if run.get("leadership", {}).get("leaderAcquired") is not True:
        problems.append("the document never took the live stream before the navigation series")
    return problems


def gc_pending(series: list[dict[str, Any]], names: tuple[str, ...]) -> dict[str, Any]:
    """The series as read with no collection forced, and its growth round by round."""
    detail: dict[str, Any] = {}
    for name in names:
        values = [count_of(point.get(name)) for point in series]
        if any(value is None for value in values):
            detail[name] = {"status": "unavailable", "values": values}
        else:
            known = [int(value) for value in values if value is not None]
            detail[name] = {
                "status": "measured",
                "values": known,
                "growth_per_round": [after - before for before, after in pairwise(known)],
            }
    return detail


def constant(series: list[dict[str, Any]]) -> dict[str, Any]:
    detail: dict[str, Any] = {}
    for name in COLLECTED:
        values = [count_of(point.get(name)) for point in series]
        known = [value for value in values if value is not None]
        detail[name] = {
            "values": known,
            "constant": len(known) == len(values) and len(set(known)) == 1,
        }
    return detail


def long_tasks(cohort: dict[str, Any]) -> dict[str, Any]:
    tasks = cohort["footprint"]["longTasks"]
    if not isinstance(tasks, list):
        return {"status": "unavailable", "reason": "the browser reported no longtask support"}
    durations = [task["durationMs"] for task in tasks]
    return {
        "status": "measured",
        "count": len(durations),
        "total_ms": sum(durations),
        "max_ms": max(durations, default=0.0),
    }


def _verdict(
    budget_id: str, cohort: str | None, measured: Any, limit: Any, *, ok: bool, **more: Any
) -> dict[str, Any]:
    return {
        "budget": budget_id,
        "cohort": cohort,
        "measured": measured,
        "limit": limit,
        "pass": ok,
        **more,
    }


def _cohort_summary(
    runs: list[dict[str, Any]], index: int, medians: dict[str, float]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One cohort's samples, its budgets, and the three verdicts that follow from them."""
    cohort = COHORTS[index]
    first = [run["cohorts"][index]["firstRenderMs"] for run in runs]
    polls = [u["getToPaintMs"] for run in runs for u in run["cohorts"][index]["updates"]]
    first_median, poll_median = statistics.median(first), statistics.median(polls)
    limits = {
        "new_document": budget(medians["new_document_median_ms"]),
        "poll_to_render": budget(medians["poll_median_ms"]),
    }
    tasks = [long_tasks(run["cohorts"][index]) for run in runs]
    summary = {
        "cohort": cohort,
        "session_count": runs[0]["cohorts"][index]["fixture"]["session_count"],
        "baseline_medians_ms": medians,
        "new_document_samples": first,
        "new_document_median_ms": first_median,
        "new_document_worst_ms": max(first),
        "poll_samples_ms": polls,
        "poll_median_ms": poll_median,
        "poll_worst_ms": max(polls),
        "comparison_budget_ms": limits,
        "fetches_per_update": [
            u["fetchesForSequence"] for run in runs for u in run["cohorts"][index]["updates"]
        ],
        "removed_nodes_per_update": [
            u["removedNodes"] for run in runs for u in run["cohorts"][index]["updates"]
        ],
        "long_tasks": tasks,
    }
    measured = [task for task in tasks if task["status"] == "measured"]
    total = sum(task["total_ms"] for task in measured)
    allowance = budget(LONG_TASK_BASELINE_MS) * len(tasks)
    verdicts = [
        _verdict(
            "first_render_median",
            cohort,
            first_median,
            limits["new_document"],
            ok=first_median <= limits["new_document"],
            statistic="median of 3 new-document loads",
            samples_over=sum(1 for value in first if value > limits["new_document"]),
        ),
        _verdict(
            "poll_to_paint_median",
            cohort,
            poll_median,
            limits["poll_to_render"],
            ok=poll_median <= limits["poll_to_render"],
            statistic="median of 9 background polls",
            samples_over=sum(1 for value in polls if value > limits["poll_to_render"]),
        ),
        _verdict(
            "long_tasks_derived",
            cohort,
            total if len(measured) == len(tasks) else None,
            allowance,
            ok=len(measured) == len(tasks) and total <= allowance,
            statistic="total long-task ms over the three runs; derived, the baseline states none",
        ),
    ]
    return summary, verdicts


def _retention_verdict(runs: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    replacements = {key: [run["retention"][key] for run in runs] for key in REPLACEMENTS}
    editor = all(
        run["editor"]["draftRetained"]
        and run["editor"]["focusRetained"]
        and run["editor"]["selectionRetained"]
        and run["editor"]["nodeRetained"]
        and run["editor"]["nativeUndo"]["restoredPriorWords"]
        for run in runs
    )
    kept = all(
        run["retention"]["openDisclosureKeptOpen"] and run["retention"]["focusedSelectKeptChoice"]
        for run in runs
    )
    none_replaced = all(value == 0 for values in replacements.values() for value in values)
    return _verdict(
        "edited_or_open_node_replacements",
        None,
        replacements,
        policy["edited_or_open_node_replacements"],
        ok=editor and kept and none_replaced,
    )


def _resource_verdicts(
    runs: list[dict[str, Any]], baseline: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    collected = [constant(run["navigationAfterCollection"]) for run in runs]
    verdict = _verdict(
        "resource_constant_after_collection",
        None,
        [{name: one[name]["values"] for name in COLLECTED} for one in collected],
        "every counter constant across the navigation rounds",
        ok=all(one[name]["constant"] for one in collected for name in COLLECTED),
        statistic="a forced collection before every reading, so a count that only rises until the "
        "next collection is not retention",
    )
    navigation = {
        "after_collection": collected,
        "gc_pending": {
            "status": "informational",
            "ruling": GC_PENDING_RULING,
            "react": [gc_pending(run["navigation"], COLLECTED) for run in runs],
            "legacy_baseline": [
                gc_pending(run["navigation"], LEGACY_RAW) for run in baseline["runs"]
            ],
        },
    }
    return [verdict], navigation


# The baseline records its own ceiling for the core page (1,816,276 bytes, 1.25 times the replaced
# page), and that record is historical and digest-bound, so it is not edited. The owner re-based the
# ceiling to 2,000,000 bytes on 2026-10-10: the page is served from the reader's machine, the size
# proxy stood in for a cost the time budgets measure directly, and the shadcn/ui migration is known
# to add to it. A layer that needs more raises this constant in its own pull request, with its
# measured times. See docs/design-shadcn-adoption.md.
CORE_HTML_CEILING_BYTES = 2_000_000


def budget_policy(baseline: dict[str, Any]) -> dict[str, Any]:
    """The baseline policy with the core page ceiling the owner set, and the reason beside it."""
    policy = dict(baseline["budget_policy"])
    policy["core_html_max_bytes_baseline"] = policy["core_html_max_bytes"]
    policy["core_html_max_bytes"] = CORE_HTML_CEILING_BYTES
    policy["core_html"] = (
        "Re-based by the owner on 2026-10-10 from the baseline's 25% growth to a fixed ceiling, "
        "because the page is served locally and the time budgets are the guard; the optional "
        "terminal packaging is accounted apart, as before."
    )
    return policy


def evaluate(runs: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    """Everything derived from the runs. Pure, so `check` can derive it again and compare."""
    medians = baseline_medians(baseline)
    summary: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    for index, cohort in enumerate(COHORTS):
        one, found = _cohort_summary(runs, index, medians[cohort])
        summary.append(one)
        verdicts.extend(found)
    policy = budget_policy(baseline)
    verdicts.append(_retention_verdict(runs, policy))
    resource, navigation = _resource_verdicts(runs, baseline)
    verdicts.extend(resource)
    page = runs[0]["fixture"]["page_bytes"]
    verdicts.append(
        _verdict(
            "core_html_bytes",
            None,
            page,
            policy["core_html_max_bytes"],
            ok=page <= policy["core_html_max_bytes"],
        )
    )
    return {
        "summary": summary,
        "verdicts": verdicts,
        "navigation": navigation,
        "removed_nodes_note": "Removed-node counts are trends: the baseline kept only a cumulative "
        "total, so this is reported, not budgeted.",
    }


def control_summary(control: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    """The unchanged baseline driver, run again beside the candidate runs, as a machine check."""
    bound = baseline["source_bindings"]
    medians = baseline_medians(baseline)
    cohorts = []
    for index, cohort in enumerate(COHORTS):
        first = [run["cohorts"][index]["firstRenderMs"] for run in control]
        polls = [u["getToPaintMs"] for run in control for u in run["cohorts"][index]["updates"]]
        cohorts.append(
            {
                "cohort": cohort,
                "new_document_median_ms": statistics.median(first),
                "poll_median_ms": statistics.median(polls),
                "recorded_baseline_medians_ms": medians[cohort],
            }
        )
    return {
        "purpose": "The pre-React driver and page, run again on the day of the React runs with "
        "the same Chrome: whether the machine still reads as the baseline did.",
        "chrome": control[0]["environment"]["chrome"]["product"],
        "node": control[0]["environment"]["node"],
        "sources_are_the_baselines": all(
            run["sources"]["driver"] == bound["driver"]
            and run["sources"]["fixture"] == bound["fixture"]
            for run in control
        ),
        "cohorts": cohorts,
        "navigation_jsEventListeners": [
            [point["jsEventListeners"] for point in run["navigation"]] for run in control
        ],
    }


def _page_binding(
    root: Path, runs: list[dict[str, Any]], baseline: dict[str, Any]
) -> dict[str, Any]:
    pages = {(run["fixture"]["page_sha256"], run["fixture"]["page_bytes"]) for run in runs}
    if len(pages) != 1:
        msg = "the runs served different pages"
        raise ValueError(msg)
    sha, size = next(iter(pages))
    terminal = read_json(root / REACT_DOCUMENT)["optionalTerminal"]
    legacy = baseline["page_bytes"]
    return {
        "sha256": sha,
        "bytes": size,
        "legacy_page_bytes": legacy,
        "change_vs_legacy_pct": round((size - legacy) / legacy * 100, 2),
        "max_bytes": budget_policy(baseline)["core_html_max_bytes"],
        "optional_terminal_bytes": {
            name: terminal[name]["bytes"] for name in ("javascript", "stylesheet")
        },
        "terminal_note": "The optional xterm script and stylesheet are served separately on first "
        "use and are accounted apart from the core page, as they were for the legacy page.",
    }


def _comparability(base: dict[str, Any], run: dict[str, Any]) -> str:
    then, now = base["environment"], run["environment"]
    return (
        f"Same platform and architecture. Chrome moved from {then['chrome']['product']} to "
        f"{now['chrome']['product']} (same major) and Node from {then['node']} to {now['node']}; "
        "the baseline's own receipt says its timings are not compared across machines or "
        "browsers, so the control block re-runs the unchanged baseline on this day."
    )


DIFFERENCES = (
    (
        "The page is react.html through frontend_fluidity_fixture.py, which serves the baseline "
        "fixture's data and states (its cohorts, rows, titles and states); the baseline's own "
        "fixture script was removed with the previous interface."
    ),
    (
        "The poll is the page's own 20 s fallback-poll callback, captured from setInterval; the "
        "React page has no global poll function."
    ),
    (
        "Two instrumentation additions: the setInterval wrapper keeps callbacks and an EventSource "
        "wrapper counts open streams. The shared instrumentation is otherwise the baseline's "
        "text, checked by a test."
    ),
    "The editor step also holds an opened disclosure and the prompt select and checks native undo.",
    (
        "A second navigation series is read after a forced collection, taken after the "
        "baseline-comparable one so it cannot disturb it."
    ),
    (
        "The navigation series runs in a document that holds the live stream (the lease is "
        "dropped and re-taken), so the stream count means something."
    ),
    "Ports come from the migration's own list; 4571 is not used.",
)


def compose(root: Path, run_paths: list[Path], *, date: str, commit: str) -> dict[str, Any]:
    baseline_path = root / BASELINE
    baseline = read_json(baseline_path)
    runs = [read_json(path) for path in run_paths]
    if len(runs) != len(baseline["runs"]):
        msg = f"the baseline holds {len(baseline['runs'])} runs; give exactly that many"
        raise ValueError(msg)
    for number, run in enumerate(runs, 1):
        problems = run_problems(run)
        if problems:
            msg = f"run {number}: " + "; ".join(problems)
            raise ValueError(msg)
    if any(run["sources"] != runs[0]["sources"] for run in runs):
        msg = "the runs were taken with different driver or fixture sources"
        raise ValueError(msg)
    derived = evaluate(runs, baseline)
    failed = [
        {"budget": item["budget"], "cohort": item["cohort"]}
        for item in derived["verdicts"]
        if not item["pass"]
    ]
    return {
        "schema": 1,
        "date": date,
        "candidate_base_commit": commit,
        "purpose": "The assembled production React page measured the way the pre-React baseline "
        "was measured, against the budgets that receipt fixes.",
        "cohort_sizing": baseline["cohort_sizing"],
        "methodology": runs[0]["methodology"],
        "differences_from_baseline": list(DIFFERENCES),
        "environment": {
            "candidate": {key: runs[0]["environment"][key] for key in ENVIRONMENT_KEYS},
            "baseline": {key: baseline["runs"][0]["environment"][key] for key in ENVIRONMENT_KEYS},
            "load_average_at_start": [run["environment"]["loadAverageAtStart"] for run in runs],
            "comparability": _comparability(baseline["runs"][0], runs[0]),
        },
        "source_bindings": {name: runs[0]["sources"][name] for name in SCRIPTS},
        "current_sources": {name: digest(root / path) for name, path in SCRIPTS.items()},
        "baseline_status": BASELINE_STATUS,
        "baseline_binding": digest(baseline_path),
        "page": _page_binding(root, runs, baseline),
        "budget_policy": budget_policy(baseline),
        "scope_limits": [
            *baseline["scope_limits"],
            "Each run starts a fresh owned browser profile; the three cohorts of one run share it.",
            (
                "TCP descriptors and retained detached nodes are not observed and are not "
                "reported as zero."
            ),
            (
                "A native select popup cannot be opened through the debugger protocol here; the "
                "open-popup hold is proven by the controls browser proof named in the cutover "
                "receipt."
            ),
        ],
        **derived,
        "overall": {"failed": failed, "all_budgets_pass": not failed},
        "runs": runs,
    }


def _derivation_problems(
    receipt: dict[str, Any], runs: list[dict[str, Any]], baseline: dict[str, Any]
) -> list[str]:
    derived = evaluate(runs, baseline)
    problems = [
        f"{key} is not what the embedded runs give; the receipt was edited"
        for key in ("summary", "verdicts", "navigation")
        if json.loads(json.dumps(derived[key])) != receipt.get(key)
    ]
    held = receipt.get("legacy_control")
    if held is not None:
        again = control_summary(held["runs"], baseline)
        if json.loads(json.dumps(again)) != {k: v for k, v in held.items() if k != "runs"}:
            problems.append("legacy_control is not what its embedded runs give; it was edited")
        if not again["sources_are_the_baselines"]:
            problems.append("the control runs were not taken with the baseline's own sources")
    passing = all(item["pass"] for item in derived["verdicts"])
    if receipt.get("overall", {}).get("all_budgets_pass") is not passing:
        problems.append("overall.all_budgets_pass disagrees with the verdicts")
    return problems


def _binding_problems(root: Path, receipt: dict[str, Any], runs: list[dict[str, Any]]) -> list[str]:
    problems = []
    if receipt.get("baseline_binding") != digest(root / BASELINE):
        problems.append(f"{BASELINE} changed since this receipt was composed")
    for name, path in SCRIPTS.items():
        bound = receipt.get("source_bindings", {}).get(name)
        if bound is None or any(run["sources"].get(name) != bound for run in runs):
            problems.append(f"a run was taken with a different {name} than the receipt binds")
        if receipt.get("current_sources", {}).get(name) != digest(root / path):
            problems.append(
                f"{path} changed since this receipt recorded it (current source {name})"
            )
    sha = receipt.get("page", {}).get("sha256")
    if any(run["fixture"]["page_sha256"] != sha for run in runs):
        problems.append("a run served a page other than the one the receipt binds")
    return problems


def check_fluidity(root: Path, receipt: dict[str, Any], *, require_current_page: bool) -> list[str]:
    """Re-derive the receipt from its runs and bindings; return every way it is not what it says."""
    baseline = read_json(root / BASELINE)
    if receipt.get("schema") != 1:
        return ["fluidity receipt must use schema 1"]
    runs = receipt.get("runs")
    if not isinstance(runs, list) or len(runs) != len(baseline["runs"]):
        return [f"fluidity receipt must embed {len(baseline['runs'])} complete runs"]
    problems = [
        f"run {number}: {problem}"
        for number, run in enumerate(runs, 1)
        for problem in run_problems(run)
    ]
    if problems:
        return problems
    problems = _derivation_problems(receipt, runs, baseline) + _binding_problems(
        root, receipt, runs
    )
    if require_current_page:
        shipped = read_json(root / REACT_DOCUMENT)["document"]["sha256"]
        if shipped != receipt.get("page", {}).get("sha256"):
            problems.append(
                "the shipped React page is not the one that was measured; measure again"
            )
    return problems


# --------------------------------------------------------------------------- cutover receipt


@functools.cache
def scan_js(text: str) -> tuple[str, tuple[tuple[int, int, str], ...]]:
    """The source with every comment blanked (same length, newlines kept), and its string literals.

    A title matched anywhere in a file is not a test: it can sit in a comment, a block comment or
    a string that only talks about the test. Matching on this output matches code.
    """
    code = list(text)
    literals: list[tuple[int, int, str]] = []
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        two = text[index : index + 2]
        if two in ("//", "/*"):
            end = text.find("\n" if two == "//" else "*/", index + 2)
            end = length if end < 0 else end + (2 if two == "/*" else 0)
            for at in range(index, end):
                if text[at] != "\n":
                    code[at] = " "
            index = end
        elif char in "'\"`":
            end = index + 1
            while end < length and text[end] != char:
                end += 2 if text[end] == "\\" else 1
            literals.append((index, end, text[index + 1 : end]))
            index = end + 1
        else:
            index += 1
    return "".join(code), tuple(literals)


NOT_RUN = frozenset({"skip", "todo", "only", "fails", "skipIf", "runIf"})
NEUTRALISED = re.compile(
    r"\b(?:describe|suite|it|test)\.(?:skip|only|todo|skipIf)\b|\bx(?:it|test|describe)\b"
)


def _call_chain(code: str, open_paren: int) -> list[str]:
    """The dotted callee before `open_paren`; for `it.each(table)(...)`, that of the table call."""
    end = open_paren
    while end > 0 and code[end - 1].isspace():
        end -= 1
    if end > 0 and code[end - 1] == ")":
        depth, at = 0, end - 1
        while at >= 0:
            depth += {")": 1, "(": -1}.get(code[at], 0)
            if depth == 0:
                break
            at -= 1
        return _call_chain(code, at)
    start = end
    while start > 0 and (code[start - 1].isalnum() or code[start - 1] in "._$"):
        start -= 1
    return code[start:end].split(".")


def declared_tests(text: str) -> list[str]:
    """Titles of the tests a vitest file really runs: declared with it or test, none skipped."""
    code, literals = scan_js(text)
    if NEUTRALISED.search(code):
        return []
    found = []
    for start, _end, title in literals:
        before = start
        while before > 0 and code[before - 1].isspace():
            before -= 1
        if before == 0 or code[before - 1] != "(":
            continue
        chain = _call_chain(code, before - 1)
        mods = {part for part in chain[1:] if part not in ("each", "concurrent", "sequential")}
        if chain[0] in ("it", "test") and not mods & NOT_RUN:
            found.append(title)
    return found


def step_names(text: str) -> list[str]:
    code, _ = scan_js(text)
    return [a or b or c for a, b, c in STEP_CALL.findall(code)]


def _skipped(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name.startswith("skip"):
            return True
    return False


@functools.cache
def python_tests(text: str) -> tuple[str, ...]:
    """Names of the test methods this module really runs: defined, not decorated with a skip."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ()
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or _skipped(node):
            continue
        found += [
            item.name
            for item in node.body
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            and item.name.startswith("test")
            and not _skipped(item)
        ]
    return tuple(found)


def _package_commands(root: Path) -> str:
    return "\n".join(read_json(root / "package.json").get("scripts", {}).values())


def _fluidity_proof(root: Path, proof: dict[str, Any], where: str) -> list[str]:
    try:
        receipt = read_json(root / FLUIDITY)
    except (OSError, ValueError):
        return [f"{where}: {FLUIDITY} is missing or unreadable"]
    if proof["fluidity"] not in {item["budget"] for item in receipt.get("verdicts", [])}:
        return [f"{where}: {FLUIDITY} holds no verdict named {proof['fluidity']!r}"]
    return []


def _literal_problems(kind: str, proof: dict[str, Any], text: str, where: str) -> list[str]:
    value = proof[kind]
    key = "contains" if kind == "browser" else "test"
    needle = proof.get(key)
    if needle is None:
        return [f"{where}: a {kind} proof names the {key!r} text it relies on in {value}"]
    if not isinstance(needle, str) or not needle:
        return [f"{where}: {value} does not contain {needle!r}"]
    if kind == "browser":
        found = needle in scan_js(text)[0]
    elif kind == "python":
        found = needle in python_tests(text)
    else:
        found = any(needle in title for title in declared_tests(text))
    if not found:
        said = "contain" if kind == "browser" else "declare a running test"
        return [f"{where}: {value} does not {said} {needle!r}"]
    return []


def _browser_problems(proof: dict[str, Any], text: str, where: str, commands: str) -> list[str]:
    value = proof["browser"]
    if value.removeprefix("frontend/") not in commands:
        return [f"{where}: {value} is not run by any package.json script"]
    if "step" not in proof:
        return _literal_problems("browser", proof, text, where)
    matches = [name for name in step_names(text) if str(proof["step"]) in name]
    if len(matches) != 1:
        found = f"step {proof['step']!r} matches {len(matches)} steps in {value}"
        return [f"{where}: {found}, not exactly one"]
    return []


def proof_problems(root: Path, proof: Any, where: str, commands: str) -> list[str]:
    """Whether one named proof exists: a file, and the step or text inside it the row relies on."""
    kinds = [
        kind
        for kind in ("vitest", "browser", "python", "fluidity")
        if isinstance(proof, dict) and kind in proof
    ]
    if len(kinds) != 1:
        return [f"{where}: a proof is an object naming one of vitest, browser, python, fluidity"]
    kind = kinds[0]
    if kind == "fluidity":
        return _fluidity_proof(root, proof, where)
    value = proof[kind]
    path = (root / value).resolve() if isinstance(value, str) else None
    if path is None or not path.is_relative_to(root) or not path.is_file():
        return [f"{where}: {kind} proof file {value!r} does not exist"]
    text = path.read_text(encoding="utf-8")
    if kind == "browser":
        return _browser_problems(proof, text, where, commands)
    if kind == "vitest" and not re.fullmatch(r"frontend/.+\.test\.tsx?", value):
        return [f"{where}: {value} is not a file the vitest configuration includes"]
    return _literal_problems(kind, proof, text, where)


def _anchor_problems(root: Path, link: Any, where: str) -> list[str]:
    if not isinstance(link, str) or "#" not in link:
        return [f"{where}: a deviation links a design-record heading as path#anchor"]
    name, anchor = link.split("#", 1)
    target = root / name
    if not target.is_file():
        return [f"{where}: {name} does not exist"]
    if anchor not in heading_slugs(target):
        return [f"{where}: {name} has no heading #{anchor}"]
    return []


def _status_problems(root: Path, entry: dict[str, Any], status: str, where: str) -> list[str]:
    if status == "deviation":
        return _anchor_problems(root, entry.get("deviation"), where)
    if status == "deferred" and (
        not re.fullmatch(r"DRC-\d+", str(entry.get("owner", ""))) or not entry.get("reason")
    ):
        return [f"{where}: a deferred row names its owner (DRC-NNNN) and a reason"]
    if status == "gap" and not str(entry.get("gap", "")).strip():
        return [f"{where}: a gap row says what proof is missing"]
    return []


def entry_problems(
    root: Path, entry: Any, where: str, commands: str
) -> tuple[list[str], str | None]:
    """One row's mapping: its problems, and its status when it has a valid one."""
    if not isinstance(entry, dict) or entry.get("status") not in STATUSES:
        return [f"{where}: an entry is an object with a status in {sorted(STATUSES)}"], None
    status = entry["status"]
    proofs = entry.get("proofs", [])
    if not isinstance(proofs, list):
        return [f"{where}: proofs must be a list"], status
    problems = [
        problem
        for number, proof in enumerate(proofs, 1)
        for problem in proof_problems(root, proof, f"{where} proof {number}", commands)
    ]
    if status in ("proven", "deviation") and not proofs:
        problems.append(f"{where}: a {status} row names at least one proof")
    problems.extend(_status_problems(root, entry, status, where))
    if status != "proven" and not str(entry.get("note", "")).strip():
        problems.append(f"{where}: a {status} row carries a note")
    return problems, status


def cell_problems(root: Path, cell: Any, where: str, commands: str) -> tuple[list[str], str]:
    """A matrix cell: proofs, or not applicable with a reason, or an explicit gap."""
    if not isinstance(cell, dict):
        return [f"{where}: a cell must be an object"], "invalid"
    for key in ("na", "gap"):
        if key in cell:
            said = isinstance(cell[key], str) and bool(cell[key].strip())
            return ([] if said else [f"{where}: {key} needs its reason"]), key
    proofs = cell.get("proofs")
    if not isinstance(proofs, list) or not proofs:
        return [f"{where}: a cell names proofs, not-applicable or a gap"], "invalid"
    return [
        problem
        for number, proof in enumerate(proofs, 1)
        for problem in proof_problems(root, proof, f"{where} proof {number}", commands)
    ], "proven"


def _group_result(
    root: Path, group: str, expected: list[str], mapped: Any, commands: str
) -> tuple[list[str], dict[str, int], list[str]]:
    counts = dict.fromkeys(sorted(STATUSES), 0)
    if not isinstance(mapped, dict):
        return [f"{group}: the receipt maps none of its {len(expected)} rows"], counts, []
    problems = [f"{group}: no mapping for {name}" for name in expected if name not in mapped]
    problems += [
        f"{group}: mapping for {name} names no inventory row"
        for name in mapped
        if name not in expected
    ]
    gaps = []
    for name in (name for name in expected if name in mapped):
        found, status = entry_problems(root, mapped[name], f"{group} {name}", commands)
        problems.extend(found)
        if status:
            counts[status] += 1
        if status == "gap":
            gaps.append(f"{group} {name}: {mapped[name]['gap']}")
    return problems, counts, gaps


def _class_result(
    root: Path, classes: Any, surfaces: set[str], commands: str
) -> tuple[list[str], list[str]]:
    if not isinstance(classes, dict) or not classes:
        return ["the receipt holds no surface classes"], []
    problems: list[str] = []
    gaps: list[str] = []
    covered: set[str] = set()
    for name, entry in classes.items():
        if not isinstance(entry, dict):
            problems.append(f"class {name}: must be an object")
            continue
        members = entry.get("surfaces", [])
        problems += [
            f"class {name}: {member} is not an inventory surface"
            for member in members
            if member not in surfaces
        ]
        covered.update(members)
        for column in COLUMNS:
            found, status = cell_problems(
                root, entry.get(column), f"class {name} {column}", commands
            )
            problems.extend(found)
            if status == "gap":
                gaps.append(f"class {name} {column}: {entry[column]['gap']}")
    problems += [f"surface {name} belongs to no class" for name in sorted(surfaces - covered)]
    return problems, gaps


def _shard_problems(root: Path) -> list[str]:
    try:
        shards = read_json(root / PRODUCTION_SHARDS)
    except (OSError, ValueError):
        return [f"{PRODUCTION_SHARDS} is missing or unreadable"]
    if not isinstance(shards, dict) or not shards:
        return [f"{PRODUCTION_SHARDS} must map each shard to its proofs"]
    listed = [name for names in shards.values() if isinstance(names, list) for name in names]
    problems = [f"{PRODUCTION_SHARDS} lists a proof in two shards"] * (
        len(listed) != len(set(listed))
    )
    problems += [
        f"{PRODUCTION_SHARDS} runs no {name}, so it is not proven on the shipped bundle"
        for name in sorted(PARITY_SCRIPTS - set(listed))
    ]
    return problems + [
        f"{PRODUCTION_SHARDS} names {name}, which is not a parity proof"
        for name in sorted(set(listed) - PARITY_SCRIPTS - EXTRA_PRODUCTION_PROOFS)
    ]


def _runs_command(step: Any, command: str) -> bool:
    """Whether a workflow step's `run:` value has a line that starts with the command.

    A substring anywhere in the file is not a step: it can sit in a comment, an `echo` or another
    job. Only a `run` line that begins with the command, then ends or takes arguments, runs it.
    """
    run = step.get("run") if isinstance(step, dict) else None
    lines = (line.strip() for line in run.splitlines()) if isinstance(run, str) else ()
    return any(line == command or line.startswith(command + " ") for line in lines)


def _bundle_problems(root: Path, block: dict[str, Any], commands: str) -> list[str]:
    """The production-bundle proof: its runner is a named proof, a script runs it, CI runs that."""
    named = [item for item in block.get("proofs", []) if isinstance(item, dict)]
    problems = []
    if not any(item.get("browser") == PRODUCTION_RUNNER for item in named):
        problems.append(f"production_artifact must name {PRODUCTION_RUNNER} among its proofs")
    bundle = block.get("production_bundle")
    if not isinstance(bundle, dict):
        problems.append("production_artifact names no production_bundle (command and CI job)")
        return problems
    if bundle.get("command") != PRODUCTION_COMMAND:
        problems.append(f"production_bundle command must be {PRODUCTION_COMMAND}")
    if PRODUCTION_RUNNER.removeprefix("frontend/") not in commands:
        problems.append(f"no package.json script runs {PRODUCTION_RUNNER}")
    job = bundle.get("ci_job")
    try:
        workflow = yaml.safe_load((root / WORKFLOW).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return [*problems, f"{WORKFLOW} is missing or is not YAML"]
    named_jobs = [
        item
        for item in (workflow.get("jobs") or {}).values()
        if isinstance(item, dict) and item.get("name") == job
    ]
    if not isinstance(job, str) or len(named_jobs) != 1:
        problems.append(f"{WORKFLOW} has no job named {job!r}, or has several")
    elif not any(
        _runs_command(step, PRODUCTION_COMMAND) for step in named_jobs[0].get("steps", [])
    ):
        problems.append(f"job {job!r} has no step whose run value runs {PRODUCTION_COMMAND}")
    return [*problems, *_shard_problems(root)]


def _artifact_result(root: Path, block: Any, commands: str) -> tuple[list[str], list[str]]:
    """The shipped-artifact block: proofs that exercise react.html itself, and what they omit."""
    if not isinstance(block, dict):
        return ["the receipt names no production_artifact block"], []
    proofs = block.get("proofs")
    if not isinstance(proofs, list) or not proofs:
        return ["production_artifact names no proof that runs against the shipped page"], []
    problems = [
        problem
        for number, proof in enumerate(proofs, 1)
        for problem in proof_problems(root, proof, f"production_artifact proof {number}", commands)
    ]
    problems += _bundle_problems(root, block, commands)
    gap = block.get("gap")
    if gap is not None and (not isinstance(gap, str) or not gap.strip()):
        problems.append("production_artifact gap must say what is not covered")
    return problems, [f"production artifact: {gap}"] if gap else []


def check_receipt(root: Path, receipt: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    """Judge the mapped cutover receipt against the inventory: problems, status counts, gaps."""
    counts = dict.fromkeys(sorted(STATUSES), 0)
    if receipt.get("schema") != 1 or not isinstance(receipt.get("rows"), dict):
        return {
            "problems": ["cutover receipt must use schema 1 and hold rows"],
            "counts": counts,
            "gaps": [],
        }
    commands = _package_commands(root)
    problems: list[str] = []
    gaps: list[str] = []
    for group in GROUPS:
        expected = [row["name"] for row in inventory.get(group, [])]
        found, group_counts, group_gaps = _group_result(
            root, group, expected, receipt["rows"].get(group), commands
        )
        problems += found
        gaps += group_gaps
        for status, number in group_counts.items():
            counts[status] += number
    surfaces = {row["name"] for row in inventory.get("surfaces", [])}
    found, class_gaps = _class_result(root, receipt.get("classes"), surfaces, commands)
    shipped, shipped_gaps = _artifact_result(root, receipt.get("production_artifact"), commands)
    return {
        "problems": problems + found + shipped,
        "counts": counts,
        "gaps": gaps + class_gaps + shipped_gaps,
    }


# --------------------------------------------------------------------------- command line


def _git_head(root: Path) -> str:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(root), "rev-parse", "HEAD"],  # noqa: S607 - git is the tool
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _run_fluidity(root: Path, args: argparse.Namespace) -> int:
    try:
        receipt = compose(root, args.run, date=args.date, commit=args.commit or _git_head(root))
    except (OSError, ValueError, KeyError) as error:
        print(f"Cannot compose the fluidity receipt: {error}", file=sys.stderr)
        return 1
    out = args.output or root / FLUIDITY
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    failed = receipt["overall"]["failed"]
    print(f"wrote {out}; {len(failed)} budget(s) failed")
    for item in failed:
        print(f"  FAIL {item['budget']} {item['cohort'] or ''}".rstrip())
    return 0


def _run_check(root: Path, args: argparse.Namespace) -> int:
    try:
        fluidity = read_json(args.fluidity or root / FLUIDITY)
        problems = check_fluidity(root, fluidity, require_current_page=args.final)
        inventory = read_json(args.inventory or root / INVENTORY)
        result = check_receipt(root, read_json(args.receipt or root / RECEIPT), inventory)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Cannot check the cutover receipts: {error}", file=sys.stderr)
        return 1
    problems += result["problems"]
    for problem in problems:
        print(problem, file=sys.stderr)
    print("rows: " + ", ".join(f"{count} {status}" for status, count in result["counts"].items()))
    for gap in result["gaps"]:
        print(f"GAP {gap}")
    failed = [item for item in fluidity.get("verdicts", []) if not item["pass"]]
    for item in failed:
        print(f"BUDGET FAILED {item['budget']} {item['cohort'] or ''}".rstrip())
    if problems:
        return 1
    return int(args.final and bool(result["gaps"] or failed))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    flu = commands.add_parser("fluidity", help="compose three runs into the committed receipt")
    flu.add_argument("--run", type=Path, action="append", required=True)
    flu.add_argument("--output", type=Path)
    flu.add_argument("--date", default=datetime.now(tz=UTC).date().isoformat())
    flu.add_argument("--commit")
    check = commands.add_parser("check", help="check the fluidity and cutover receipts")
    check.add_argument("--fluidity", type=Path)
    check.add_argument("--receipt", type=Path)
    check.add_argument("--inventory", type=Path)
    check.add_argument(
        "--final",
        action="store_true",
        help="final verification: no gap, no failed budget, receipt bound to the shipped page",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    return _run_fluidity(root, args) if args.command == "fluidity" else _run_check(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
