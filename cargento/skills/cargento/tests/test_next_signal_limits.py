"""Live event explanations, estimate limits and cited records have distinct homes."""

from __future__ import annotations

import shutil
import unittest

from cargento_runtime import levels

from .test_next_intent_draft import TYPED, drift_of
from .test_next_live_estimate import CHECK, _LivePage, live
from .visible_text import visible_text

PASS = CHECK.replace('result:"failed"', 'result:"passed",result_at:105')


@unittest.skipUnless(shutil.which("node"), "node not available")
class LiveSignalsAndLimitsTest(_LivePage):
    def test_not_enough_has_one_why_home_for_all_its_reasons_and_visible_no_folder_limit(
        self,
    ) -> None:
        html = drift_of(
            self.on(
                live(
                    "not_enough",
                    reasons=[
                        "failed-check",
                        "no-passing-check",
                        "scan-incomplete",
                        "later-direction",
                        "pass-then-write",
                        "intent-names-no-folder",
                    ],
                )
            )
        )
        for sentence in (
            "No check has passed yet.",
            "The record was not read in full.",
            "A later direction of yours is unsettled.",
            "A check passed, then files were written after it.",
        ):
            self.assertEqual(1, html.count(sentence), sentence)
            self.assertNotIn(sentence, visible_text(html))
            self.assertIn(sentence, visible_text(html.replace("<details", "<details open")))
        self.assertEqual(1, html.count("pytest failed"))
        self.assertIn("Why not None or low", html)
        self.assertIn("Limits of this estimate", visible_text(html))
        self.assertEqual(1, html.count("Your intent names no folder"))
        self.assertIn("Call recorded at", visible_text(html))

    def test_limits_do_not_hide_a_floor_only_passing_citation_or_duplicate_its_source(self) -> None:
        for reasons in (
            ["floor-met"],
            ["floor-met", "intent-names-no-folder", "entries-not-listed"],
        ):
            html = drift_of(self.on(live("none_or_low", reasons=reasons), TYPED + PASS))
            text = visible_text(html)
            self.assertIn("Recorded signals", text)
            self.assertIn("passed check", text)
            self.assertIn("Call recorded at", text)
            self.assertIn("Result recorded at", text)
            self.assertEqual(1, html.count("assessment-source:signals:c-fail"))
            if len(reasons) > 1:
                self.assertIn("Limits of this estimate", text)
                self.assertIn("Some written files were counted and not listed.", text)
                self.assertEqual(1, html.count("Your intent names no folder"))
                self.assertGreater(
                    text.index("Your intent names no folder"), text.index("Limits of this estimate")
                )

    def test_no_cite_limit_has_no_empty_signal_heading(self) -> None:
        text = visible_text(
            drift_of(self.on(live("none_or_low", reasons=["intent-names-no-folder"], cites=[])))
        )
        self.assertIn("Limits of this estimate", text)
        self.assertNotIn("Recorded signals", text)

    def test_named_failure_age_and_order_survive_level_and_reason_order(self) -> None:
        for level in ("medium", "high", "extreme"):
            for changed, suffix in (
                (False, "no passing re-run recorded"),
                (True, "files changed after it"),
            ):
                setup = TYPED + CHECK.replace(
                    'result:"failed"', f'result:"failed",before_last_change:{str(changed).lower()}'
                )
                setup += "__dashboard.generated=284.5;\n"
                text = visible_text(
                    drift_of(
                        self.on(live(level, reasons=["pass-then-write", "failed-check"]), setup)
                    )
                )
                self.assertIn("pytest failed 3m ago at #4", text)
                self.assertIn(suffix, text)
                self.assertIn("A check passed, then files were written after it.", text)

    def test_mixed_missing_ids_keep_real_evidence_and_explicit_incompleteness(self) -> None:
        for reasons in (["failed-check"], ["floor-met"]):
            html = drift_of(
                self.on(live(reasons=reasons, cites=["c-fail", "missing"]), TYPED + PASS)
            )
            text = visible_text(html)
            self.assertIn("passed check", text)
            self.assertIn("Call recorded at", text)
            self.assertIn("not listed", text)
            self.assertNotIn("#5", text)
            self.assertEqual(1, html.count("assessment-source:signals:c-fail"))

    def test_model_only_and_unknown_tokens_are_silent_in_both_live_reason_paths(self) -> None:
        for level in ("not_enough", "high"):
            html = drift_of(
                self.on(
                    live(
                        level,
                        reasons=[
                            "departure",
                            "claim-contradicted",
                            "claim-not-shown",
                            "reading-malformed",
                            "line-not-shown-by-a-check",
                            "outcome-not-reached",
                            "no-outcome-line",
                            "foreign-token",
                            "constructor",
                            "__proto__",
                        ],
                        cites=[],
                    )
                )
            )
            text = visible_text(html)
            self.assertNotIn("Departure evidence", text)
            self.assertNotIn("The model assessed", text)
            self.assertNotIn("The record contradicts", text)
            self.assertNotIn("The record read does not show", text)
            self.assertNotIn("foreign-token", text)
            for line in (
                "Part of the stored analysis could not be read.",
                "A line of your intent is not shown by any check.",
                "Work against your intent was not reached at this stop.",
                "No expected outcome line was saved.",
            ):
                self.assertNotIn(line, html)

    def test_every_registered_native_reason_has_one_home(self) -> None:
        registry = self.drive(
            after="console.log(JSON.stringify({tokens:[...Object.keys(NEXT_DRIFT_REASON_LINES),...Object.keys(NEXT_DRIFT_BLOCKER_LINES),...NEXT_DRIFT_REASON_SILENT],limits:Object.values(NEXT_DRIFT_BLOCKER_LINES)}));"
        )
        self.assertEqual(set(levels.REASONS), set(registry["tokens"]))
        for level in ("not_enough", "high"):
            html = drift_of(self.on(live(level, reasons=registry["tokens"])))
            for line in registry["limits"]:
                expected = (
                    0
                    if line
                    in (
                        "Part of the stored analysis could not be read.",
                        "A line of your intent is not shown by any check.",
                        "Work against your intent was not reached at this stop.",
                        "No expected outcome line was saved.",
                    )
                    else 1
                )
                self.assertEqual(expected, html.count(line), (level, line))
            for line in (
                "A check passed, then files were written after it.",
                "Some files were written outside the folders your intent names.",
                "Most files were written outside the folders your intent names.",
            ):
                self.assertEqual(1, html.count(line), (level, line))
            self.assertEqual(1, html.count("pytest failed"))
            self.assertNotIn("Departure evidence", html)
            self.assertNotIn("The record contradicts", html)
            self.assertNotIn("The record read does not show", html)

    def test_full_signed_year_and_unknown_result_grammar_preserve_the_entry(self) -> None:
        value = self.drive(
            after="console.log(JSON.stringify([nextDriftRecordedTime(253402300800),nextDriftRecordedTime(8640000000000),nextDriftRecordedTime(8640000000001)]));"
        )
        self.assertEqual(
            ["+010000-01-01 00:00:00 UTC", "+275760-09-13 00:00:00 UTC", "time not recorded"], value
        )
        text = visible_text(drift_of(self.on(live(reasons=["failed-check"]))))
        self.assertIn("Result time not recorded.", text)
        self.assertIn("pytest", text)
