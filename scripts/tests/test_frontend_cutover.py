"""The cutover receipts cannot silently lose a row, a proof or a measurement."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import frontend_cutover as cutover  # noqa: E402 - the scripts directory is not a package
import frontend_fluidity_fixture as fixture_module  # noqa: E402
from cargento_runtime.web.page import load_frontend_page  # noqa: E402 - path set by the fixture


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class FluidityReceiptTest(unittest.TestCase):
    """The committed React measurement re-derives from its own runs and is bound to its sources."""

    receipt: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = load(cutover.FLUIDITY)

    def mutated(self) -> dict[str, Any]:
        return copy.deepcopy(self.receipt)

    def check(self, receipt: dict[str, Any], *, current: bool = False) -> list[str]:
        return cutover.check_fluidity(ROOT, receipt, require_current_page=current)

    def test_the_committed_receipt_is_what_its_runs_give(self) -> None:
        self.assertEqual([], self.check(self.receipt))

    def test_it_holds_the_baselines_number_of_complete_runs_and_cohorts(self) -> None:
        baseline = load(cutover.BASELINE)
        self.assertEqual(len(baseline["runs"]), len(self.receipt["runs"]))
        for run in self.receipt["runs"]:
            self.assertEqual([], cutover.run_problems(run))
            self.assertEqual(["small", "median", "large"], [c["cohort"] for c in run["cohorts"]])
        for cohort in self.receipt["summary"]:
            self.assertEqual(3, len(cohort["new_document_samples"]))
            self.assertEqual(9, len(cohort["poll_samples_ms"]))

    def test_budgets_are_the_baseline_median_times_one_and_a_half_plus_fifty(self) -> None:
        self.assertAlmostEqual(199.1, cutover.budget(99.4), places=6)
        baseline = load(cutover.BASELINE)
        for row in baseline["summary"]:
            mine = next(c for c in self.receipt["summary"] if c["cohort"] == row["cohort"])
            self.assertAlmostEqual(
                row["comparison_budget_ms"]["new_document"],
                mine["comparison_budget_ms"]["new_document"],
                places=6,
            )
            self.assertAlmostEqual(
                row["comparison_budget_ms"]["poll_to_render"],
                mine["comparison_budget_ms"]["poll_to_render"],
                places=6,
            )
        self.assertEqual(
            baseline["budget_policy"]["core_html_max_bytes"], self.receipt["page"]["max_bytes"]
        )

    def test_every_budget_the_policy_names_has_a_verdict(self) -> None:
        named = {item["budget"] for item in self.receipt["verdicts"]}
        for budget in (
            "first_render_median",
            "poll_to_paint_median",
            "long_tasks_derived",
            "edited_or_open_node_replacements",
            "resource_constant_after_collection",
            "core_html_bytes",
        ):
            self.assertIn(budget, named)
        for cohort in ("small", "median", "large"):
            self.assertIn(
                ("first_render_median", cohort),
                {(v["budget"], v["cohort"]) for v in self.receipt["verdicts"]},
            )

    def test_a_failed_budget_is_recorded_as_failed_not_reworded(self) -> None:
        failed = {item["budget"] for item in self.receipt["verdicts"] if not item["pass"]}
        self.assertEqual(failed, {item["budget"] for item in self.receipt["overall"]["failed"]})
        self.assertIs(not failed, self.receipt["overall"]["all_budgets_pass"])

    def verdicts_after(self, edit: Any) -> dict[tuple[str, Any], bool]:
        runs = copy.deepcopy(self.receipt["runs"])
        for run in runs:
            edit(run)
        derived = cutover.evaluate(runs, load(cutover.BASELINE))
        return {(v["budget"], v["cohort"]): v["pass"] for v in derived["verdicts"]}

    def test_slow_loads_polls_and_long_tasks_fail_their_budgets(self) -> None:
        def slow(run: dict[str, Any]) -> None:
            for cohort in run["cohorts"]:
                cohort["firstRenderMs"] = 5000.0
                for update in cohort["updates"]:
                    update["getToPaintMs"] = 5000.0
                cohort["footprint"]["longTasks"] = [{"startMs": 1.0, "durationMs": 300.0}]

        failed = self.verdicts_after(slow)
        for cohort in ("small", "median", "large"):
            self.assertFalse(failed[("first_render_median", cohort)])
            self.assertFalse(failed[("poll_to_paint_median", cohort)])
            self.assertFalse(failed[("long_tasks_derived", cohort)])

    def test_a_replaced_edited_node_or_lost_undo_fails_the_identity_budget(self) -> None:
        def replaced(run: dict[str, Any]) -> None:
            run["retention"]["editedNodeReplacements"] = 1
            run["editor"]["nodeRetained"] = False

        def lost_undo(run: dict[str, Any]) -> None:
            run["editor"]["nativeUndo"]["restoredPriorWords"] = False

        def closed(run: dict[str, Any]) -> None:
            run["retention"]["openDisclosureKeptOpen"] = False

        for edit in (replaced, lost_undo, closed):
            verdicts = self.verdicts_after(edit)
            self.assertFalse(verdicts[("edited_or_open_node_replacements", None)], edit.__name__)

    def test_growth_that_survives_a_collection_fails_and_every_counter_is_judged(self) -> None:
        for name in cutover.COLLECTED:

            def leaking(run: dict[str, Any], name: str = name) -> None:
                point = run["navigationAfterCollection"][-1]
                if isinstance(point[name], dict):
                    point[name]["open"] += 1
                else:
                    point[name] += 1

            verdicts = self.verdicts_after(leaking)
            self.assertFalse(verdicts[("resource_constant_after_collection", None)], name)

    def test_growth_that_a_collection_clears_does_not_fail(self) -> None:
        def pending(run: dict[str, Any]) -> None:
            for step, point in enumerate(run["navigation"]):
                point["jsEventListeners"] += 500 * step
                point["nodes"] += 900 * step
                point["activeWebSockets"] += step

        verdicts = self.verdicts_after(pending)
        self.assertTrue(verdicts[("resource_constant_after_collection", None)])
        self.assertTrue(all(verdicts.values()) or not self.receipt["overall"]["all_budgets_pass"])

    def test_a_heavy_page_fails(self) -> None:
        def heavy(run: dict[str, Any]) -> None:
            run["fixture"]["page_bytes"] = 9_000_000

        self.assertFalse(self.verdicts_after(heavy)[("core_html_bytes", None)])

    def test_the_uncollected_series_is_kept_beside_the_ruling_and_the_legacy_page(self) -> None:
        pending = self.receipt["navigation"]["gc_pending"]
        self.assertEqual("informational", pending["status"])
        self.assertIn("cutover review", pending["ruling"])
        self.assertEqual([37] * 5, pending["react"][0]["jsEventListeners"]["growth_per_round"])
        self.assertEqual([583] * 5, pending["legacy_baseline"][0]["nodes"]["growth_per_round"])
        self.assertEqual(
            [0] * 5, pending["legacy_baseline"][0]["jsEventListeners"]["growth_per_round"]
        )
        self.assertNotIn("resource_settles_raw", json.dumps(self.receipt["verdicts"]))

    def test_the_committed_receipt_passes_every_budget(self) -> None:
        self.assertEqual([], self.receipt["overall"]["failed"])
        self.assertTrue(self.receipt["overall"]["all_budgets_pass"])

    def test_the_budgets_the_runs_meet_are_the_ones_the_receipt_says_pass(self) -> None:
        passing = {(v["budget"], v["cohort"]) for v in self.receipt["verdicts"] if v["pass"]}
        for cohort in ("small", "median", "large"):
            self.assertIn(("first_render_median", cohort), passing)
            self.assertIn(("poll_to_paint_median", cohort), passing)
        self.assertIn(("edited_or_open_node_replacements", None), passing)
        self.assertIn(("core_html_bytes", None), passing)

    def test_an_edited_verdict_is_caught(self) -> None:
        receipt = self.mutated()
        receipt["verdicts"][0]["pass"] = False
        receipt["overall"] = {"failed": [], "all_budgets_pass": False}
        problems = self.check(receipt)
        self.assertTrue(any("verdicts is not what the embedded runs give" in p for p in problems))

    def test_an_edited_sample_is_caught(self) -> None:
        receipt = self.mutated()
        receipt["summary"][0]["poll_samples_ms"][0] = 1.0
        self.assertTrue(any("summary is not what" in p for p in self.check(receipt)))

    def test_a_script_that_changed_since_the_receipt_recorded_it_breaks_its_binding(self) -> None:
        receipt = self.mutated()
        receipt["current_sources"]["driver"]["sha256"] = "0" * 64
        problems = self.check(receipt)
        self.assertTrue(
            any("frontend_fluidity.mjs changed since this receipt" in p for p in problems)
        )

    def test_the_sources_the_runs_were_taken_with_cannot_be_rewritten(self) -> None:
        # What was measured is bound by what every run recorded of itself, not by the tree: the
        # tree may change after the runs, and the binding must not follow it.
        receipt = self.mutated()
        recorded = receipt["runs"][0]["sources"]
        self.assertEqual(
            {name: recorded[name] for name in receipt["source_bindings"]},
            receipt["source_bindings"],
        )
        receipt["source_bindings"]["driver"]["sha256"] = "0" * 64
        problems = self.check(receipt)
        self.assertTrue(any("different driver than the receipt binds" in p for p in problems))

    def test_the_receipt_says_the_baseline_is_historical_and_cannot_be_remeasured(self) -> None:
        self.assertEqual(cutover.BASELINE_STATUS, self.receipt["baseline_status"])
        self.assertIn("cannot be re-measured", self.receipt["baseline_status"])
        for name in ("frontend_baseline.mjs", "frontend_baseline_fixture.py"):
            self.assertFalse((SCRIPTS / name).exists(), name)

    def test_a_changed_baseline_breaks_its_binding(self) -> None:
        receipt = self.mutated()
        receipt["baseline_binding"]["bytes"] += 1
        self.assertTrue(any("frontend-baseline.json changed" in p for p in self.check(receipt)))

    def test_an_incomplete_run_is_refused(self) -> None:
        receipt = self.mutated()
        receipt["runs"][0]["fatal"] = "Error: browser died"
        self.assertTrue(any("incomplete" in p for p in self.check(receipt)))
        receipt = self.mutated()
        receipt["runs"].pop()
        self.assertTrue(any("must embed 3 complete runs" in p for p in self.check(receipt)))

    def test_a_run_without_the_stream_is_refused(self) -> None:
        receipt = self.mutated()
        receipt["runs"][2]["leadership"]["leaderAcquired"] = False
        self.assertTrue(any("never took the live stream" in p for p in self.check(receipt)))

    def test_the_page_binding_names_the_measured_page_and_goes_stale_with_it(self) -> None:
        receipt = self.mutated()
        shipped = load(cutover.REACT_DOCUMENT)["document"]["sha256"]
        self.assertEqual(64, len(receipt["page"]["sha256"]))
        stale = "1" * 64
        receipt["page"]["sha256"] = stale
        for run in receipt["runs"]:
            run["fixture"]["page_sha256"] = stale
        self.assertEqual([], self.check(receipt, current=False))
        self.assertTrue(
            any("not the one that was measured" in p for p in self.check(receipt, current=True))
        )
        self.assertNotEqual(stale, shipped)

    def test_the_control_block_re_derives_from_the_unchanged_baseline_driver(self) -> None:
        control = self.receipt["legacy_control"]
        self.assertTrue(control["sources_are_the_baselines"])
        receipt = self.mutated()
        receipt["legacy_control"]["runs"][0]["sources"]["driver"]["sha256"] = "2" * 64
        problems = self.check(receipt)
        self.assertTrue(any("legacy_control" in p for p in problems))

    def test_an_unobserved_counter_is_unavailable_never_zero(self) -> None:
        series = [{"jsEventListeners": 1, "activeWebSockets": None} for _ in range(3)]
        detail = cutover.gc_pending(series, cutover.COLLECTED)
        self.assertEqual("unavailable", detail["activeWebSockets"]["status"])
        self.assertEqual("unavailable", detail["eventSourceConnections"]["status"])
        self.assertEqual("measured", detail["jsEventListeners"]["status"])
        self.assertFalse(cutover.constant(series)["activeWebSockets"]["constant"])

    def test_growth_is_listed_round_by_round(self) -> None:
        grows = [{"jsEventListeners": value} for value in (10, 20, 21, 22)]
        detail = cutover.gc_pending(grows, ("jsEventListeners",))
        self.assertEqual([10, 1, 1], detail["jsEventListeners"]["growth_per_round"])
        self.assertFalse(cutover.constant(grows)["jsEventListeners"]["constant"])
        flat = [{"jsEventListeners": value} for value in (7, 7, 7)]
        self.assertTrue(cutover.constant(flat)["jsEventListeners"]["constant"])


class FinalVerificationTest(unittest.TestCase):
    """`--final` is the form the release hold waits on: it needs no gap and no failed budget."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scratch = Path(self.temp.name)
        self.real = load(cutover.FLUIDITY)

    def write_runs(self, edit: Any = None) -> list[Path]:
        paths = []
        for number, run in enumerate(copy.deepcopy(self.real["runs"]), 1):
            if edit:
                edit(run)
            path = self.scratch / f"run{number}.json"
            path.write_text(json.dumps(run), encoding="utf-8")
            paths.append(path)
        return paths

    @staticmethod
    def leak_after_collection(run: dict[str, Any]) -> None:
        run["navigationAfterCollection"][-1]["nodes"] += 1

    def compose(self, edit: Any = None) -> Path:
        receipt = cutover.compose(ROOT, self.write_runs(edit), date="2026-10-09", commit="0" * 40)
        path = self.scratch / "fluidity.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return path

    def receipt_without_gaps(self) -> Path:
        receipt = load(cutover.RECEIPT)
        for entry in receipt["classes"].values():
            for column in cutover.COLUMNS:
                if "gap" in entry[column]:
                    entry[column] = {"na": "decided for this test"}
        receipt["production_artifact"].pop("gap", None)
        path = self.scratch / "receipt.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return path

    def run_check(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cutover.main(["--root", str(ROOT), "check", *args])
        return code, out.getvalue(), err.getvalue()

    def test_the_committed_receipts_pass_the_final_form(self) -> None:
        code, out, err = self.run_check("--final")
        self.assertEqual(0, code, out + err)
        self.assertNotIn("GAP", out)
        self.assertNotIn("BUDGET FAILED", out)

    def test_final_passes_only_without_a_gap_a_failed_budget_or_a_stale_page(self) -> None:
        fluidity = self.compose()
        receipt = self.receipt_without_gaps()
        args = ("--fluidity", str(fluidity), "--receipt", str(receipt))
        code, out, err = self.run_check(*args, "--final")
        self.assertEqual(0, code, out + err)

    def test_final_refuses_growth_that_survives_a_collection(self) -> None:
        fluidity = self.compose(self.leak_after_collection)
        receipt = self.receipt_without_gaps()
        args = ("--fluidity", str(fluidity), "--receipt", str(receipt))
        code, out, _ = self.run_check(*args)
        self.assertEqual(0, code)
        self.assertIn("BUDGET FAILED resource_constant_after_collection", out)
        final, _, _ = self.run_check(*args, "--final")
        self.assertEqual(1, final)

    def test_final_refuses_a_gap(self) -> None:
        receipt = load(cutover.RECEIPT)
        receipt["classes"]["shell"]["editor"] = {"gap": "decided for this test"}
        path = self.scratch / "gappy.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        args = ("--receipt", str(path))
        code, out, _ = self.run_check(*args)
        self.assertEqual(0, code)
        self.assertIn("GAP class shell editor", out)
        self.assertEqual(1, self.run_check(*args, "--final")[0])

    def test_final_refuses_a_receipt_of_a_page_that_no_longer_ships(self) -> None:
        def other_page(run: dict[str, Any]) -> None:
            run["fixture"]["page_sha256"] = "3" * 64

        fluidity = self.compose(other_page)
        receipt = self.receipt_without_gaps()
        args = ("--fluidity", str(fluidity), "--receipt", str(receipt))
        self.assertEqual(0, self.run_check(*args)[0])
        code, _, err = self.run_check(*args, "--final")
        self.assertEqual(1, code)
        self.assertIn("not the one that was measured", err)

    def test_composing_refuses_the_wrong_number_of_runs_and_an_incomplete_run(self) -> None:
        paths = self.write_runs()
        with self.assertRaises(ValueError):
            cutover.compose(ROOT, paths[:2], date="2026-10-09", commit="0")
        broken = json.loads(paths[0].read_text())
        broken["fatal"] = "Error: x"
        paths[0].write_text(json.dumps(broken))
        with self.assertRaises(ValueError):
            cutover.compose(ROOT, paths, date="2026-10-09", commit="0")

    def test_composing_from_the_command_line_writes_a_receipt_and_names_failures(self) -> None:
        paths = self.write_runs()
        out = self.scratch / "composed.json"
        args = ["--root", str(ROOT), "fluidity", "--output", str(out), "--commit", "abc"]
        for path in paths:
            args += ["--run", str(path)]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cutover.main(args)
        self.assertEqual(0, code)
        self.assertEqual(self.real["overall"], json.loads(out.read_text())["overall"])
        self.assertIn("budget(s) failed", stdout.getvalue())
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = cutover.main(["--root", str(ROOT), "fluidity", "--run", str(paths[0])])
        self.assertEqual(1, code)
        self.assertIn("Cannot compose", errors.getvalue())


class MappedReceiptTest(unittest.TestCase):
    """Every row of the ownership map has a named React-side proof, and a missing one fails."""

    receipt: dict[str, Any]
    inventory: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = load(cutover.RECEIPT)
        cls.inventory = load(cutover.INVENTORY)

    def result(self, receipt: dict[str, Any]) -> dict[str, Any]:
        return cutover.check_receipt(ROOT, receipt, self.inventory)

    def mutated(self) -> dict[str, Any]:
        return copy.deepcopy(self.receipt)

    def test_every_inventory_row_is_mapped_and_every_proof_exists(self) -> None:
        result = self.result(self.receipt)
        self.assertEqual([], result["problems"])
        total = sum(len(self.inventory[group]) for group in cutover.GROUPS)
        self.assertEqual(total, sum(result["counts"].values()))

    def test_gaps_are_listed_by_name_and_are_not_a_silent_pass(self) -> None:
        result = self.result(self.receipt)
        cells = sum(
            1
            for entry in self.receipt["classes"].values()
            for column in cutover.COLUMNS
            if "gap" in entry[column]
        )
        artifact = 1 if self.receipt["production_artifact"].get("gap") else 0
        self.assertEqual(result["counts"]["gap"] + cells + artifact, len(result["gaps"]))
        for gap in result["gaps"]:
            self.assertRegex(
                gap, r"^(parts|surfaces|routes|reader_state|storage|class|production artifact)[ :]"
            )

    def test_the_production_artifact_block_is_required_and_its_proofs_must_exist(self) -> None:
        receipt = self.mutated()
        del receipt["production_artifact"]
        self.assertTrue(
            any("no production_artifact" in p for p in self.result(receipt)["problems"])
        )
        receipt = self.mutated()
        receipt["production_artifact"]["proofs"] = []
        self.assertTrue(any("names no proof" in p for p in self.result(receipt)["problems"]))
        receipt = self.mutated()
        receipt["production_artifact"]["proofs"][0]["contains"] = "text installed.mjs never held"
        self.assertTrue(any("does not contain" in p for p in self.result(receipt)["problems"]))
        receipt = self.mutated()
        receipt["production_artifact"]["gap"] = " "
        self.assertTrue(any("gap must say" in p for p in self.result(receipt)["problems"]))
        receipt = self.mutated()
        receipt["production_artifact"]["gap"] = "an unproven corner"
        result = self.result(receipt)
        self.assertEqual([], result["problems"])
        self.assertIn("production artifact: an unproven corner", result["gaps"])

    def test_the_committed_receipt_records_the_production_bundle_proof_without_a_gap(self) -> None:
        block = self.receipt["production_artifact"]
        self.assertNotIn("gap", block)
        self.assertEqual("pnpm test:production:browser", block["production_bundle"]["command"])
        result = self.result(self.receipt)
        self.assertFalse(any(g.startswith("production artifact") for g in result["gaps"]))

    def test_the_production_bundle_proof_cannot_be_silently_dropped(self) -> None:
        def problems(mutate: Any) -> list[str]:
            receipt = self.mutated()
            mutate(receipt["production_artifact"])
            return list(self.result(receipt)["problems"])

        # The installed smoke alone used to satisfy the block, so each of these is a mutation that used to pass.
        runner = cutover.PRODUCTION_RUNNER
        dropped = problems(
            lambda block: block.update(
                proofs=[p for p in block["proofs"] if p.get("browser") != runner]
            )
        )
        self.assertTrue(any(runner in p for p in dropped), dropped)
        missing = problems(lambda block: block.pop("production_bundle"))
        self.assertTrue(any("no production_bundle" in p for p in missing), missing)
        renamed = problems(lambda block: block["production_bundle"].update(ci_job="No such job"))
        self.assertTrue(any("has no job named" in p for p in renamed), renamed)
        command = problems(lambda block: block["production_bundle"].update(command="pnpm test"))
        self.assertTrue(any("command must be" in p for p in command), command)

    def test_the_production_shards_must_name_every_parity_proof_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".github/workflows").mkdir(parents=True)
            (root / "frontend/e2e").mkdir(parents=True)
            shutil.copy(ROOT / cutover.WORKFLOW, root / cutover.WORKFLOW)
            shards = json.loads((ROOT / cutover.PRODUCTION_SHARDS).read_text())
            self.assertEqual([], cutover._shard_problems(ROOT))
            edits: list[tuple[Any, str]] = [
                (lambda data: data["a"].remove("test:shell:browser"), "runs no test:shell:browser"),
                (
                    lambda data: data["b"].append("test:shell:browser"),
                    "lists a proof in two shards",
                ),
                (lambda data: data["b"].append("test:dev:browser"), "not a parity proof"),
            ]
            for edit, expected in edits:
                data = copy.deepcopy(shards)
                edit(data)
                (root / cutover.PRODUCTION_SHARDS).write_text(json.dumps(data), encoding="utf-8")
                found = cutover._shard_problems(root)
                self.assertTrue(any(expected in problem for problem in found), found)
            (root / cutover.PRODUCTION_SHARDS).unlink()
            self.assertTrue(any("missing" in p for p in cutover._shard_problems(root)))

    def test_every_surface_class_names_its_four_columns(self) -> None:
        for name, entry in self.receipt["classes"].items():
            for column in cutover.COLUMNS:
                self.assertIn(column, entry, f"{name} has no {column}")
        members = {m for entry in self.receipt["classes"].values() for m in entry["surfaces"]}
        self.assertEqual({row["name"] for row in self.inventory["surfaces"]}, members)

    def test_a_deleted_mapping_fails_naming_the_row(self) -> None:
        for group in cutover.GROUPS:
            receipt = self.mutated()
            name = next(iter(receipt["rows"][group]))
            del receipt["rows"][group][name]
            problems = self.result(receipt)["problems"]
            self.assertIn(f"{group}: no mapping for {name}", problems)

    def test_a_new_inventory_row_without_a_mapping_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["surfaces"].append({"name": "a-new-surface"})
        problems = cutover.check_receipt(ROOT, self.receipt, inventory)["problems"]
        self.assertIn("surfaces: no mapping for a-new-surface", problems)
        self.assertIn("surface a-new-surface belongs to no class", problems)

    def test_a_mapping_for_a_row_that_was_removed_fails(self) -> None:
        receipt = self.mutated()
        receipt["rows"]["routes"]["a-retired-route"] = {"status": "gap", "gap": "x", "note": "x"}
        self.assertIn(
            "routes: mapping for a-retired-route names no inventory row",
            self.result(receipt)["problems"],
        )

    def first_proof(self, receipt: dict[str, Any], kind: str) -> dict[str, Any]:
        for group in receipt["rows"].values():
            for entry in group.values():
                for proof in entry.get("proofs", []):
                    if kind in proof:
                        found: dict[str, Any] = proof
                        return found
        raise AssertionError(kind)

    def test_a_proof_file_that_is_gone_fails(self) -> None:
        for kind in ("vitest", "browser", "python"):
            receipt = self.mutated()
            self.first_proof(receipt, kind)[kind] += ".gone"
            self.assertTrue(
                any("does not exist" in p for p in self.result(receipt)["problems"]), kind
            )

    def test_a_test_title_that_was_renamed_fails(self) -> None:
        receipt = self.mutated()
        self.first_proof(receipt, "vitest")["test"] = "a title nobody wrote"
        self.assertTrue(
            any("does not declare a running test" in p for p in self.result(receipt)["problems"])
        )

    def test_a_browser_step_that_was_renamed_or_is_ambiguous_fails(self) -> None:
        receipt = self.mutated()
        self.first_proof(receipt, "browser")["step"] = "a step nobody wrote"
        self.assertTrue(any("matches 0 steps" in p for p in self.result(receipt)["problems"]))
        receipt = self.mutated()
        self.first_proof(receipt, "browser")["step"] = ":"
        self.assertTrue(any("not exactly one" in p for p in self.result(receipt)["problems"]))

    def test_a_script_that_no_package_command_runs_fails(self) -> None:
        receipt = self.mutated()
        proof = self.first_proof(receipt, "browser")
        scratch = ROOT / "frontend/e2e/support/browser.mjs"
        proof["browser"] = str(scratch.relative_to(ROOT))
        proof["step"] = "x"
        self.assertTrue(
            any(
                "is not run by any package.json script" in p
                for p in self.result(receipt)["problems"]
            )
        )

    def test_a_vitest_proof_outside_the_vitest_include_fails(self) -> None:
        receipt = self.mutated()
        proof = self.first_proof(receipt, "vitest")
        proof["vitest"] = "frontend/e2e/parser.test.mjs"
        proof["test"] = "hostile"
        self.assertTrue(
            any(
                "not a file the vitest configuration includes" in p
                for p in self.result(receipt)["problems"]
            )
        )

    def test_a_proof_must_name_what_it_relies_on_inside_the_file(self) -> None:
        receipt = self.mutated()
        del self.first_proof(receipt, "vitest")["test"]
        self.assertTrue(any("names the 'test' text" in p for p in self.result(receipt)["problems"]))

    def test_a_fluidity_proof_must_name_a_verdict_that_exists(self) -> None:
        receipt = self.mutated()
        receipt["rows"]["parts"]["next-live.js"]["proofs"].append({"fluidity": "no_such_budget"})
        self.assertTrue(any("no verdict named" in p for p in self.result(receipt)["problems"]))

    def test_status_rules_hold(self) -> None:
        cases = {
            "proven with no proof": {"status": "proven", "proofs": []},
            "deviation without a link": {
                "status": "deviation",
                "proofs": [self.some_proof()],
                "note": "n",
            },
            "deviation with a missing heading": {
                "status": "deviation",
                "proofs": [self.some_proof()],
                "deviation": "docs/design-frontend-migration.md#no-such-heading",
                "note": "n",
            },
            "deviation with a missing file": {
                "status": "deviation",
                "proofs": [self.some_proof()],
                "deviation": "docs/none.md#x",
                "note": "n",
            },
            "deferred without an owner": {"status": "deferred", "reason": "later", "note": "n"},
            "deferred with a bad owner": {
                "status": "deferred",
                "owner": "later",
                "reason": "r",
                "note": "n",
            },
            "gap without its text": {"status": "gap", "gap": " ", "note": "n"},
            "gap without a note": {"status": "gap", "gap": "missing"},
            "unknown status": {"status": "fine"},
            "not an object": "proven",
        }
        for label, entry in cases.items():
            receipt = self.mutated()
            receipt["rows"]["routes"]["top-level-sessions"] = entry
            problems = self.result(receipt)["problems"]
            self.assertTrue(problems, label)

    def test_valid_deviation_deferral_and_gap_are_counted(self) -> None:
        receipt = self.mutated()
        rows = receipt["rows"]["routes"]
        rows["top-level-sessions"] = {
            "status": "deviation",
            "proofs": [self.some_proof()],
            "deviation": "docs/design-frontend-migration.md#the-cutover-receipt",
            "note": "n",
        }
        rows["top-level-attention"] = {
            "status": "deferred",
            "owner": "DRC-4999",
            "reason": "retirement",
            "note": "n",
        }
        rows["top-level-projects"] = {"status": "gap", "gap": "nothing yet", "note": "n"}
        result = self.result(receipt)
        self.assertEqual([], result["problems"])
        self.assertIn("routes top-level-projects: nothing yet", result["gaps"])
        self.assertGreaterEqual(result["counts"]["deferred"], 1)

    def some_proof(self) -> dict[str, Any]:
        return self.first_proof(self.receipt, "vitest")

    def test_class_cells_need_proofs_a_reason_or_a_gap(self) -> None:
        cells: tuple[Any, ...] = ({}, {"na": " "}, {"gap": ""}, {"proofs": []}, "x")
        for cell in cells:
            receipt = self.mutated()
            receipt["classes"]["shell"]["editor"] = cell
            self.assertTrue(self.result(receipt)["problems"], cell)

    def test_a_class_naming_a_missing_surface_or_leaving_one_out_fails(self) -> None:
        receipt = self.mutated()
        receipt["classes"]["shell"]["surfaces"].append("no-such-surface")
        self.assertTrue(
            any("is not an inventory surface" in p for p in self.result(receipt)["problems"])
        )
        receipt = self.mutated()
        receipt["classes"]["shell"]["surfaces"].pop(0)
        self.assertTrue(any("belongs to no class" in p for p in self.result(receipt)["problems"]))

    def test_malformed_receipts_are_reported_not_raised(self) -> None:
        self.assertTrue(self.result({"schema": 2})["problems"])
        self.assertTrue(self.result({"schema": 1, "rows": []})["problems"])
        receipt = self.mutated()
        receipt["rows"]["storage"] = []
        self.assertTrue(any("maps none of its" in p for p in self.result(receipt)["problems"]))
        receipt = self.mutated()
        receipt["classes"] = {}
        self.assertTrue(any("no surface classes" in p for p in self.result(receipt)["problems"]))

    def test_the_command_line_fails_on_a_deleted_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            receipt = self.mutated()
            del receipt["rows"]["parts"]["next-live.js"]
            path = Path(scratch) / "receipt.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = cutover.main(["--root", str(ROOT), "check", "--receipt", str(path)])
            self.assertEqual(1, code)
            self.assertIn("parts: no mapping for next-live.js", err.getvalue())
            missing = io.StringIO()
            with contextlib.redirect_stderr(missing):
                code = cutover.main(
                    ["--root", str(ROOT), "check", "--receipt", str(path) + ".none"]
                )
            self.assertEqual(1, code)
            self.assertIn("Cannot check", missing.getvalue())

    def test_step_names_reads_every_quoting_style(self) -> None:
        text = "await step('one', f); await step(\n  \"two\", f); await step(`three ${x}`, f);"
        self.assertEqual(["one", "two", "three ${x}"], cutover.step_names(text))

    def test_the_receipt_keeps_tracker_keys_to_owners_and_out_of_prose(self) -> None:
        body = (ROOT / cutover.RECEIPT).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"linear\.app|https?://", body))
        for entry in self.receipt["rows"]["reader_state"].values():
            self.assertNotRegex(entry.get("note", ""), r"DRC-\d+")


TEST_FILE = """
import { describe, it, test } from 'vitest';
describe('group', () => {
  it('runs one', () => {});
  it.concurrent('runs two', () => {});
  it.each([1, 2])('runs for %i', () => {});
  test('runs three', () => {});
});
"""


class ProofIsRealTest(unittest.TestCase):
    """A proof counts only if the test it names is declared and runs."""

    def titles(self, text: str) -> list[str]:
        return cutover.declared_tests(text)

    def test_declared_tests_are_found_in_every_running_form(self) -> None:
        self.assertEqual(
            ["runs one", "runs two", "runs for %i", "runs three"], self.titles(TEST_FILE)
        )

    def test_a_skipped_todo_only_or_failing_test_is_not_a_proof(self) -> None:
        for modifier in ("skip", "todo", "only", "fails", "skipIf(true)"):
            text = TEST_FILE.replace("it('runs one'", f"it.{modifier}('runs one'")
            if modifier == "only":
                self.assertEqual([], self.titles(text), modifier)
            else:
                self.assertNotIn("runs one", self.titles(text), modifier)
        skipped_each = TEST_FILE.replace("it.each([1, 2])", "it.skip.each([1, 2])")
        self.assertNotIn("runs for %i", self.titles(skipped_each))
        for old in ("xit('runs one'", "xtest('runs one'"):
            self.assertNotIn("runs one", self.titles(TEST_FILE.replace("it('runs one'", old)))

    def test_a_skipped_group_or_an_only_elsewhere_voids_the_file(self) -> None:
        self.assertEqual([], self.titles(TEST_FILE.replace("describe(", "describe.skip(")))
        self.assertEqual(
            [], self.titles(TEST_FILE.replace("test('runs three'", "test.only('runs three'"))
        )

    def test_a_commented_out_test_is_not_a_proof(self) -> None:
        line = TEST_FILE.replace("  it('runs one', () => {});", "  // it('runs one', () => {});")
        self.assertNotIn("runs one", self.titles(line))
        block = TEST_FILE.replace(
            "  it('runs one', () => {});", "  /* it('runs one', () => {});\n  */"
        )
        self.assertNotIn("runs one", self.titles(block))
        self.assertIn("runs two", self.titles(block))

    def test_a_title_in_a_string_that_is_not_a_declaration_is_not_a_proof(self) -> None:
        text = TEST_FILE + "const note = 'runs four';\nconsole.log('runs five');\n"
        self.assertNotIn("runs four", self.titles(text))
        self.assertNotIn("runs five", self.titles(text))

    def test_comment_markers_inside_strings_do_not_hide_a_test(self) -> None:
        text = "it('see http://example.com/x', () => {});\nit('after it', () => {});\n"
        self.assertEqual(["see http://example.com/x", "after it"], self.titles(text))

    def test_a_proof_in_a_scratch_tree_fails_once_its_test_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()
            target = root / "frontend/src/x.test.ts"
            target.parent.mkdir(parents=True)
            proof = {"vitest": "frontend/src/x.test.ts", "test": "runs one"}
            target.write_text(TEST_FILE, encoding="utf-8")
            self.assertEqual([], cutover.proof_problems(root, proof, "row", ""))
            target.write_text(
                TEST_FILE.replace("it('runs one'", "it.skip('runs one'"), encoding="utf-8"
            )
            problems = cutover.proof_problems(root, proof, "row", "")
            self.assertTrue(any("does not declare a running test" in p for p in problems), problems)

    def test_a_skipped_python_test_is_not_a_proof(self) -> None:
        source = (
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_runs(self) -> None: ...\n"
            "    @unittest.skip('no')\n"
            "    def test_skipped(self) -> None: ...\n"
            "    @unittest.skipUnless(False, 'no')\n"
            "    def test_conditional(self) -> None: ...\n"
            "    # def test_commented(self): ...\n"
            "    NOTE = 'def test_in_a_string(self)'\n"
            "@unittest.skip('all')\n"
            "class Off(unittest.TestCase):\n"
            "    def test_in_a_skipped_class(self) -> None: ...\n"
        )
        self.assertEqual(("test_runs",), cutover.python_tests(source))
        self.assertEqual((), cutover.python_tests("def broken(:"))

    def test_a_commented_out_browser_step_is_not_a_step(self) -> None:
        text = "await step('live one', f);\n// await step('dead one', f);\n/* await step('dead two', f); */\n"
        self.assertEqual(["live one"], cutover.step_names(text))


class WorkflowStepTest(unittest.TestCase):
    """The production-bundle command counts only as a step's run value in the named job."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".github/workflows").mkdir(parents=True)
        shutil.copytree(ROOT / "frontend/e2e", self.root / "frontend/e2e")
        self.receipt = load(cutover.RECEIPT)
        self.workflow = (ROOT / cutover.WORKFLOW).read_text(encoding="utf-8")
        self.commands = cutover._package_commands(ROOT)

    def problems(self, workflow: str) -> list[str]:
        (self.root / cutover.WORKFLOW).write_text(workflow, encoding="utf-8")
        return cutover._bundle_problems(
            self.root, self.receipt["production_artifact"], self.commands
        )

    def test_the_real_workflow_runs_the_command_in_its_job(self) -> None:
        self.assertEqual([], self.problems(self.workflow))

    def test_an_echoed_comment_is_not_a_step(self) -> None:
        run = "run: pnpm test:production:browser --shard ${{ matrix.shard }}"
        self.assertIn(run, self.workflow)
        for fake in (
            "run: echo skipped # pnpm test:production:browser --shard ${{ matrix.shard }}",
            "run: echo pnpm test:production:browser",
            "run: |\n          # pnpm test:production:browser\n          true",
        ):
            problems = self.problems(self.workflow.replace(run, fake))
            self.assertTrue(any("no step whose run value runs" in p for p in problems), fake)

    def test_a_substring_in_a_comment_or_another_job_is_not_the_job_running_it(self) -> None:
        run = "run: pnpm test:production:browser --shard ${{ matrix.shard }}"
        dead = self.workflow.replace(run, "run: true")
        problems = self.problems(dead + "\n# pnpm test:production:browser\n")
        self.assertTrue(any("no step whose run value runs" in p for p in problems))

    def test_a_missing_job_or_an_unreadable_workflow_fails(self) -> None:
        renamed = self.workflow.replace("name: Frontend production bundle", "name: Elsewhere")
        self.assertTrue(any("has no job named" in p for p in self.problems(renamed)))
        self.assertTrue(any("not YAML" in p for p in self.problems("a: [unclosed")))
        (self.root / cutover.WORKFLOW).unlink()
        found = cutover._bundle_problems(
            self.root, self.receipt["production_artifact"], self.commands
        )
        self.assertTrue(any("missing or is not YAML" in p for p in found))


class FluidityFixtureTest(unittest.TestCase):
    """The fixture is the baseline's data behind the React page, on the migration's own ports."""

    def test_ports_are_the_migrations_own(self) -> None:
        for port in (4581, 4586, 4594, 4595, 4597, 4599):
            self.assertEqual(port, fixture_module.validate_port(port))
        for port in (4553, 4563, 4567, 4571, 4580, 4587, 4596, 4600, True):
            with self.subTest(port=port), self.assertRaises(ValueError):
                fixture_module.validate_port(port)

    def test_it_serves_the_react_document_with_the_baselines_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-fluidity-test-") as scratch:
            fixture = fixture_module.build_fixture(Path(scratch))
            self.assertEqual(load_frontend_page(), fixture.page)
            shipped = load(cutover.REACT_DOCUMENT)["document"]["sha256"]
            self.assertEqual(shipped, fixture.describe()["page_sha256"])
            for sequence, (cohort, size) in enumerate(
                {"small": 5, "median": 50, "large": 250}.items(), 1
            ):
                fixture.configure(cohort=cohort, state="healthy", sequence=sequence)
                data = fixture.application.collect(show_all=True)
                self.assertTrue(data["build"].startswith("react-"))
                self.assertEqual(size, len(data["sessions"]))
                self.assertEqual(size, data["baseline_fixture"]["session_count"])
                self.assertEqual("b0000000", data["baseline_fixture"]["current_session"]["sid"])
                self.assertTrue(all("tasks" in r and "subagents" in r for r in data["sessions"]))
                self.assertTrue(
                    all(
                        r["title"].startswith(f"Baseline {sequence} session")
                        for r in data["sessions"]
                    )
                )
            config = fixture.application.config
            self.assertTrue(config.model_calls_disabled)
            self.assertFalse(config.usage_fetch_enabled)
            self.assertFalse(config.focus_enabled)
            self.assertFalse(config.history_enabled)
            self.assertTrue(config.state_dir.resolve().is_relative_to(Path(scratch).resolve()))

    def test_empty_and_unavailable_are_different_production_states(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-fluidity-test-") as scratch:
            fixture = fixture_module.build_fixture(Path(scratch))
            fixture.configure(cohort="small", state="empty", sequence=2)
            empty = fixture.application.collect(show_all=True)
            fixture.configure(cohort="small", state="unavailable", sequence=3)
            unavailable = fixture.application.collect(show_all=True)
            self.assertEqual([], empty["sessions"])
            self.assertEqual([], unavailable["sessions"])
            self.assertIsNone(empty["harnesses"][0]["error"])
            self.assertIsNotNone(unavailable["harnesses"][0]["error"])

    def test_controls_are_strict_and_sequence_monotonic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-fluidity-test-") as scratch:
            fixture = fixture_module.build_fixture(Path(scratch))
            for command in (
                {"cohort": "real", "state": "healthy", "sequence": 1},
                {"cohort": "small", "state": "online", "sequence": 1},
                {"cohort": "small", "state": "healthy", "sequence": True},
                {"cohort": "small", "state": "healthy", "sequence": 0},
            ):
                with self.subTest(command=command), self.assertRaises(ValueError):
                    fixture.control(command)
            fixture.configure(cohort="small", state="healthy", sequence=1)
            with self.assertRaises(ValueError):
                fixture.configure(cohort="small", state="healthy", sequence=1)

    def test_it_serves_its_page_and_each_board_over_http_and_refuses_a_busy_port(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargento-fluidity-test-") as scratch:
            fixture = fixture_module.build_fixture(Path(scratch))
            # This listener is ours, and proves the fixture never steals a busy port.
            with socket.socket() as occupied:
                for port in fixture_module.ALLOWED_PORTS:
                    try:
                        occupied.bind(("127.0.0.1", port))
                        occupied.listen()
                        break
                    except OSError:
                        continue
                else:
                    self.skipTest("no owned port is free")
                with self.assertRaises(OSError):
                    fixture.server(port)
            server = fixture.server(port)
            self.addCleanup(server.server_close)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(thread.join, 2)
            self.addCleanup(server.shutdown)
            for sequence, cohort, size in ((1, "small", 5), (2, "median", 50)):
                fixture.configure(cohort=cohort, state="healthy", sequence=sequence)
                url = f"http://127.0.0.1:{port}/api/data"
                with urllib.request.urlopen(url, timeout=2) as response:
                    data = json.load(response)
                self.assertEqual(sequence, data["baseline_fixture"]["sequence"])
                self.assertEqual(size, len(data["sessions"]))
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                self.assertEqual(fixture.page, response.read())

    def test_the_command_refuses_a_foreign_port_before_binding(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "frontend_fluidity_fixture.py"), "--port", "4571"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("4581..4586", result.stderr)
        self.assertNotIn('"ready"', result.stdout)


def node_major() -> int:
    node = shutil.which("node")
    if node is None:
        return 0
    out = subprocess.run([node, "--version"], capture_output=True, text=True, check=False).stdout
    return int(out.strip().lstrip("v").split(".")[0] or 0)


FAKE_CHROME = """#!/usr/bin/env node
// A stand-in for Chrome: a DevTools endpoint that answers setup and then never answers Page.navigate.
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
writeFileSync(process.env.FAKE_CHROME_PID, String(process.pid));
const answers = {
  'Browser.getVersion': { product: 'Chrome/0.0.0 (fake)' },
  'Target.createTarget': { targetId: 't1' },
  'Target.attachToTarget': { sessionId: 's1' },
};
const server = createServer();
server.on('upgrade', (request, socket) => {
  const key = createHash('sha1').update(request.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
  socket.write('HTTP/1.1 101 Switching Protocols\\r\\nUpgrade: websocket\\r\\nConnection: Upgrade\\r\\nSec-WebSocket-Accept: ' + key + '\\r\\n\\r\\n');
  socket.on('data', (data) => {
    if ((data[0] & 15) === 8) return socket.end();
    let length = data[1] & 127, at = 2;
    if (length === 126) { length = data.readUInt16BE(2); at = 4; }
    const mask = data.subarray(at, at + 4);
    const body = Buffer.from(data.subarray(at + 4, at + 4 + length).map((byte, index) => byte ^ mask[index % 4]));
    const message = JSON.parse(body.toString());
    if (message.method === 'Page.navigate') return; // never answered
    const reply = Buffer.from(JSON.stringify({ id: message.id, result: answers[message.method] ?? {} }));
    socket.write(Buffer.concat([Buffer.from([0x81, reply.length]), reply]));
  });
});
server.listen(0, '127.0.0.1', () => {
  process.stderr.write('DevTools listening on ws://127.0.0.1:' + server.address().port + '/devtools/browser/fake\\n');
});
"""


class FluidityDriverTest(unittest.TestCase):
    """The driver measures as the baseline did and refuses what it must not touch."""

    # The text the page is instrumented with. When the baseline probe still existed it was compared
    # with this line by line: three baseline lines are rewritten to keep each interval callback and
    # to hold the two new collections, and one block wrapping EventSource is added; nothing else
    # differed. The probe is gone, so the digest below stands in for that comparison, and a change
    # to the instrumentation moves every later measurement away from the baseline's.
    INSTRUMENTATION_SHA256 = "51137df81c5f6c10ed595302a743fb7ace9c41afce50e56332591a3fe80b0bd4"

    @staticmethod
    def instrumentation() -> list[str]:
        text = (SCRIPTS / "frontend_fluidity.mjs").read_text(encoding="utf-8")
        match = re.search(r"const instrumentation = `(.*?)\n\}\)\(\)`;", text, re.DOTALL)
        assert match is not None
        return match.group(1).splitlines()

    def test_the_shared_instrumentation_is_the_one_the_baseline_comparison_held(self) -> None:
        lines = self.instrumentation()
        digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        self.assertEqual(self.INSTRUMENTATION_SHA256, digest)
        joined = "\n".join(lines)
        self.assertIn("intervalCalls.set(id, {fn, ms})", joined)
        self.assertIn("intervalCalls.delete(id)", joined)
        self.assertIn("intervalCalls: new Map(), eventSources: new Set()", joined)
        self.assertIn("class extends NativeEventSource", joined)

    def test_it_polls_the_pages_own_callback_not_a_manual_refresh(self) -> None:
        text = (SCRIPTS / "frontend_fluidity.mjs").read_text(encoding="utf-8")
        self.assertIn("c.ms === 20000", text)
        self.assertIn("exactly one", text)
        self.assertNotIn("nextRefreshPoll()", text.split("const poll")[1].split("const removed")[0])

    def test_it_never_uses_a_foreign_port_and_names_no_model_or_store(self) -> None:
        text = (SCRIPTS / "frontend_fluidity.mjs").read_text(encoding="utf-8")
        self.assertNotIn("4571,", text)
        self.assertNotIn("4553", text)
        self.assertIn("requireFreePort", text)
        fixture = (SCRIPTS / "frontend_fluidity_fixture.py").read_text(encoding="utf-8")
        self.assertNotIn("import frontend_baseline_fixture", fixture)

    @unittest.skipIf(node_major() < 26, "Node 26 or later unavailable")
    def test_help_and_a_foreign_port_are_refused_before_anything_launches(self) -> None:
        node = shutil.which("node")
        assert node is not None
        driver = str(SCRIPTS / "frontend_fluidity.mjs")
        helped = subprocess.run(
            [node, driver, "--help"], capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(0, helped.returncode, helped.stderr)
        self.assertIn("4581..4586", helped.stdout)
        with tempfile.TemporaryDirectory() as scratch:
            for port in ("4553", "4571", "4596", "4600"):
                out = Path(scratch) / f"{port}.json"
                result = subprocess.run(
                    [
                        node,
                        driver,
                        "--output",
                        str(out),
                        "--chrome",
                        "never-launched",
                        "--port",
                        port,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertNotEqual(0, result.returncode, port)
                self.assertIn("port must be", result.stderr)
                self.assertFalse(out.exists())

    @unittest.skipIf(node_major() < 26, "Node 26 or later unavailable")
    def test_a_busy_port_is_refused_and_the_stranger_is_left_alone(self) -> None:
        node = shutil.which("node")
        assert node is not None
        with socket.socket() as stranger:
            for port in cutover_ports():
                try:
                    stranger.bind(("127.0.0.1", port))
                    stranger.listen()
                    break
                except OSError:
                    continue
            else:
                self.skipTest("no owned port is free")
            with tempfile.TemporaryDirectory() as scratch:
                out = Path(scratch) / "busy.json"
                result = subprocess.run(
                    [
                        node,
                        str(SCRIPTS / "frontend_fluidity.mjs"),
                        "--output",
                        str(out),
                        "--chrome",
                        "never-launched",
                        "--port",
                        str(port),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "is busy", result.stdout + result.stderr + (out.read_text() if out.exists() else "")
            )
            self.assertEqual(port, stranger.getsockname()[1])

    @unittest.skipIf(node_major() < 26, "Node 26 or later unavailable")
    def test_a_navigation_that_never_answers_fails_the_run_cleanly(self) -> None:
        node = shutil.which("node")
        assert node is not None
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            chrome = root / "fake-chrome.mjs"
            chrome.write_text(FAKE_CHROME, encoding="utf-8")
            chrome.chmod(0o755)
            pid_file, out = root / "chrome.pid", root / "report.json"
            for port in cutover_ports():
                with socket.socket() as probe:
                    try:
                        probe.bind(("127.0.0.1", port))
                    except OSError:
                        continue
                break
            else:
                self.skipTest("no owned port is free")
            result = subprocess.run(
                [
                    node,
                    str(SCRIPTS / "frontend_fluidity.mjs"),
                    "--output",
                    str(out),
                    "--chrome",
                    str(chrome),
                    "--port",
                    str(port),
                    # The same budget bounds the backend child's readiness, so a short one lets a loaded
                    # machine fail the child first and the run never reaches the navigation it is about.
                    "--timeout-ms",
                    "5000",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env={**os.environ, "FAKE_CHROME_PID": str(pid_file)},
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("incomplete", result.stderr)
            self.assertNotIn("Unhandled", result.stderr + result.stdout)
            self.assertNotIn("triggerUncaughtException", result.stderr)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertRegex(
                report["fatal"], r"CDP (event )?deadline: Page\.(navigate|loadEventFired)"
            )
            pid = int(pid_file.read_text(encoding="utf-8"))
            for _ in range(50):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, 9)
                self.fail("the fake Chrome was left running")


def cutover_ports() -> tuple[int, ...]:
    return fixture_module.ALLOWED_PORTS


if __name__ == "__main__":
    unittest.main()
