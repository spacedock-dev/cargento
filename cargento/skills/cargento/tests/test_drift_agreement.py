"""A reader gets one evidence boundary across the drift level and correction."""

from __future__ import annotations

import json
import time
import unittest
from typing import Any
from unittest import mock

from cargento_runtime import correction, levels, reading

from . import test_claims_and_adopted_goal as claims
from . import test_claude_checks as checks
from . import test_levels as tier
from . import test_next_cockpit as cockpit
from .next_harness import NextPageJsHarness, storage_prelude


class AnUnshownClaimAsksForEvidence(unittest.TestCase):
    def test_a_claim_not_shown_blocks_reassurance_without_raising_medium(self) -> None:
        stored = claims._stored(reading.RESULT_UNSUPPORTED, ["a1"])
        stored["criteria"]["goal"] = {"result": reading.RESULT_CONSISTENT, "cites": ["a1"]}
        stored["criteria"]["line_1"] = {"result": reading.RESULT_CONSISTENT, "cites": ["c1"]}
        evidence = levels.Evidence(
            (claims.SAID, claims.PASSED), {**dict.fromkeys(levels.SCAN_KEYS, 0), "passed": 1}, 0
        )
        result = levels.analysis_level(stored, evidence, outcome_lines=1)
        self.assertEqual(levels.NOT_ENOUGH, result.level)
        self.assertIn(levels.REASON_CLAIM_NOT_SHOWN, result.reasons)

    def test_the_correction_asks_for_evidence_instead_of_asserting_a_missing_result(self) -> None:
        text = claims.SteerBackSaysWhatTheRecordDoesNotShowTest().compose(
            reading.RESULT_UNSUPPORTED, ["a1"], [claims.SAID]
        )
        self.assertIn("Can you show evidence", text)
        self.assertNotIn("the record does not show it", text)

    def test_a_short_title_or_bare_url_is_never_quoted_as_the_claim(self) -> None:
        for title in ("All done", "https://example.com/results"):
            with self.subTest(title=title):
                fact = {**claims.SAID, "summary": title}
                text = claims.SteerBackSaysWhatTheRecordDoesNotShowTest().compose(
                    reading.RESULT_UNSUPPORTED, ["a1"], [fact]
                )
                self.assertNotIn('"' + title + '"', text)
                self.assertIn("show evidence", text)


class ThePageKeepsAClaimSecondary(NextPageJsHarness):
    def fixture(self, script: str) -> Any:
        return self._run_page_js(
            "await __settle();\n" + script,
            storage_prelude({}) + cockpit.NextCockpitCompositionTest.FIXTURE,
        )

    def test_a_claim_only_offer_is_secondary_even_when_no_reader_is_available(self) -> None:
        out = self.fixture(f"""
nextData={{...nextData,annotate:true}};
const session={{harness:"claude",sid:"s1",annotation_goal:"Ship the retry",
  annotation_revision:1,annotation_window_start:50}};
const entries=nextCockpitWorkEntries(session,{{facts:{json.dumps([claims.SAID])}}});
const annotation={{goal:"Ship the retry",revision:1,assessment:{{revision_read:1,
  revision_read_at:50,read_at:500,window_start:50,
  criteria:{{claims:{{result:"not shown by the record",cites:["a1"]}}}}}}}};
const source={{state:"read",entries,all:entries}};
const parts=nextCockpitReadingParts(session,annotation,entries,{{}},false,false,source);
console.log(JSON.stringify(parts.control));
""")
        self.assertIn("Steer back", out)
        self.assertNotIn(
            'class="next-action next-action--primary" data-next-cockpit-action="steer-back"', out
        )

    def test_a_withdrawn_claim_draws_no_claim_row(self) -> None:
        out = self.fixture("""
const shape={criteria:[{key:"claims",result:NEXT_READING_UNVERIFIABLE,
  why:"missing source",limit:"",declared:true}]};
console.log(JSON.stringify(nextCockpitClaimsDrawn(shape)));
""")
        self.assertEqual([], out)


class AFailureBelongsToThePersonsLastTurn(unittest.TestCase):
    def facts(self, failed_at: float, *, writes: bool = False) -> levels.Evidence:
        facts = [
            tier.check("failed", failed_at, "failed"),
            tier.check("passed", tier.SAVE + 5, "passed"),
        ]
        if writes:
            facts.append(tier.wrote("write", failed_at + 1, "src/a.py"))
        return tier.evidence(facts, tier.scan(failed=1, passed=1, last_user_at=tier.SAVE))

    def test_an_older_failure_blocks_none_or_low_but_raises_neither_level(self) -> None:
        facts = self.facts(tier.SAVE - 5)
        for result in (
            levels.live_level(facts, tier.intent("Tests pass")),
            tier.analyze(tier.SUPPORTED, facts),
        ):
            self.assertEqual(levels.NOT_ENOUGH, result.level)
            self.assertIn(levels.REASON_FAILED_CHECK, result.reasons)

    def test_an_older_listed_failure_keeps_its_citation(self) -> None:
        got = levels.live_level(self.facts(tier.SAVE - 5), tier.intent("Tests pass"))
        self.assertIn("failed", got.cites)

    def test_a_failure_after_the_last_message_is_high_on_both_sources(self) -> None:
        facts = self.facts(tier.SAVE + 10)
        for result in (
            levels.live_level(facts, tier.intent("Tests pass")),
            tier.analyze(tier.SUPPORTED, facts),
        ):
            self.assertEqual(levels.HIGH, result.level)
            self.assertIn("failed", result.cites)

    def test_writes_after_that_failure_limit_it_to_medium(self) -> None:
        facts = self.facts(tier.SAVE + 10, writes=True)
        for result in (
            levels.live_level(facts, tier.intent("Tests pass")),
            tier.analyze(tier.SUPPORTED, facts),
        ):
            self.assertEqual(levels.MEDIUM, result.level)

    def test_an_unplaced_failure_cannot_raise_high_without_a_citation(self) -> None:
        facts = tier.evidence(
            [tier.check("passed", tier.SAVE + 5, "passed")],
            tier.scan(failed=1, passed=1, last_user_at=tier.SAVE),
        )
        for result in (
            levels.live_level(facts, tier.intent("Tests pass")),
            tier.analyze(tier.SUPPORTED, facts),
        ):
            self.assertEqual(levels.NOT_ENOUGH, result.level)

    def test_a_failure_with_unknown_time_cannot_raise_high(self) -> None:
        facts = tier.evidence(
            [tier.check("failed", None, "failed")], tier.scan(failed=1, last_user_at=tier.SAVE)
        )
        self.assertEqual(
            levels.NOT_ENOUGH, levels.live_level(facts, tier.intent("Tests pass")).level
        )

    def test_no_outcome_line_still_has_no_analysis_level_even_with_a_fresh_failure(self) -> None:
        got = levels.analysis_level(tier.SUPPORTED, self.facts(tier.SAVE + 10), outcome_lines=0)
        self.assertEqual(levels.NOT_ENOUGH, got.level)
        self.assertEqual((levels.REASON_NO_OUTCOME_LINE,), got.reasons)


class AFolderSignalNamesARecordedPlace(unittest.TestCase):
    def test_a_branch_shaped_word_without_a_directory_or_write_is_not_weighed(self) -> None:
        facts = tier.evidence(
            [tier.wrote("w", tier.SAVE + 1, "src/a.py")], tier.scan(written_paths=1)
        )
        got = levels.live_level(facts, tier.intent("Review feat/my-branch and web/ PR"))
        self.assertIsNone(got.writes_total)
        self.assertIn(levels.REASON_NO_FOLDER, got.reasons)

    def test_unknown_or_relative_session_cwd_cannot_borrow_a_daemon_folder(self) -> None:
        for cwd in ("", "relative"):
            with (
                self.subTest(cwd=cwd),
                mock.patch("cargento_runtime.levels.os.path.isdir", return_value=True),
            ):
                facts = levels.Evidence(
                    (tier.wrote("w", tier.SAVE + 1, "outside/a.py"),),
                    tier.scan(written_paths=1),
                    0,
                    cwd,
                )
                got = levels.live_level(facts, tier.intent("Only touch scripts/"))
                self.assertIsNone(got.writes_total)

    def test_a_folder_with_a_recorded_write_can_be_weighed_without_disk_access(self) -> None:
        facts = tier.evidence(
            [
                tier.wrote("w", tier.SAVE + 1, "src/a.py"),
                tier.wrote("x", tier.SAVE + 2, "other/a.py"),
            ],
            tier.scan(written_paths=2),
        )
        got = levels.live_level(facts, tier.intent("Only touch src/"))
        self.assertEqual((1, 2), (got.writes_outside, got.writes_total))


class ACorrectionNamesTheCurrentGap(unittest.TestCase):
    def compose(self, facts: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
        row = {
            **claims.SID,
            "annotation_goal": "Ship the retry",
            "annotation_revision": 1,
            "annotation_window_start": 50,
            "annotation_settled_through": 120,
            **extra,
        }
        return correction.compose(
            row, facts, floor=50, lines_judged=True, clock=lambda at: f"T{int(at)}"
        )

    def test_a_later_direction_alone_never_offers_a_correction(self) -> None:
        result = self.compose([claims._person("p2", 120, "Pause the retry")])
        self.assertEqual({"ok": False, "reason": "nothing"}, result)

    def test_a_settled_direction_is_absent_from_a_correction_for_a_claim(self) -> None:
        result = self.compose(
            [claims._person("p2", 120, "Pause the retry"), claims.SAID],
            annotation_assessment={
                "revision_read": 1,
                "window_start": 50,
                "read_at": 500,
                "criteria": {"claims": {"result": reading.RESULT_UNSUPPORTED, "cites": ["a1"]}},
            },
        )
        text = "".join(p if isinstance(p, str) else "{entry}" for p in result["parts"])
        self.assertNotIn("later direction", text)
        self.assertIn("show evidence", text)

    def test_an_old_failure_alone_offers_nothing_after_the_person_answers(self) -> None:
        result = self.compose(
            [claims._check("f", 95, "failed"), claims._person("p2", 120, "Continue")]
        )
        self.assertEqual({"ok": False, "reason": "nothing"}, result)

    def test_a_fresh_failure_keeps_a_correction_available(self) -> None:
        result = self.compose(
            [claims._person("p2", 60, "Continue"), claims._check("f", 95, "failed")]
        )
        self.assertTrue(result["ok"])

    def test_a_goal_departure_is_timed_before_unshown_outcomes(self) -> None:
        result = self.compose(
            [claims.SAID],
            annotation_line_1="The retry backs off",
            annotation_assessment={
                "revision_read": 1,
                "window_start": 50,
                "read_at": 500,
                "criteria": {"goal": {"result": reading.RESULT_DEPARTURE, "cites": ["a1"]}},
            },
        )
        text = "".join(p if isinstance(p, str) else "{entry}" for p in result["parts"])
        self.assertIn("departed from my goal at T90", text)
        self.assertLess(text.index("departed"), text.index("can you show evidence"))

    def test_an_older_correction_clock_includes_its_date(self) -> None:
        today = time.struct_time((2026, 10, 5, 12, 0, 0, 0, 278, -1))
        older = time.struct_time((2026, 10, 4, 9, 15, 0, 6, 277, -1))
        with mock.patch("cargento_runtime.correction.time.localtime", side_effect=[older, today]):
            self.assertEqual("2026-10-04 09:15", correction.clock_text(1))
        with mock.patch("cargento_runtime.correction.time.localtime", side_effect=[today, today]):
            self.assertEqual("12:00", correction.clock_text(1))

    def test_an_unconfirmed_consistent_line_names_the_sessions_account(self) -> None:
        result = self.compose(
            [claims.SAID],
            annotation_line_1="The retry backs off",
            annotation_assessment={
                "revision_read": 1,
                "window_start": 50,
                "read_at": 500,
                "criteria": {
                    "goal": {"result": reading.RESULT_DEPARTURE, "cites": ["a1"]},
                    "line_1": {"result": reading.RESULT_CONSISTENT, "cites": ["a1"]},
                },
            },
        )
        text = "".join(p if isinstance(p, str) else "{entry}" for p in result["parts"])
        self.assertIn("the session says this is done; not confirmed by a tool", text)
        self.assertNotIn("nothing recorded shows this yet", text)


class ABroaderPassingRunRetiresTheCoveredFailure(checks.ClaudeChecksTestCase):
    def test_a_module_pass_supersedes_a_failed_unittest_method(self) -> None:
        self.session.bash("python3 -m unittest tests.test_retry.Retry.test_backoff", is_error=True)
        self.session.bash("python3 -m unittest tests.test_retry")
        found = self.checks()
        self.assertEqual(["passed"], [row["result"] for row in found])
        self.assertTrue(found[0]["earlier_failed"])

    def test_a_pytest_file_pass_supersedes_its_failed_test(self) -> None:
        self.session.bash("python3 -m pytest tests/test_retry.py::test_backoff", is_error=True)
        self.session.bash("python3 -m pytest tests/test_retry.py")
        self.assertEqual(["passed"], [row["result"] for row in self.checks()])

    def test_a_pass_cannot_retire_a_failure_outside_its_proven_scope(self) -> None:
        for failed, passed in (
            (
                "python3 -m unittest tests.test_retry.Bad.test_backoff",
                "python3 -m unittest tests.test_retry.Good",
            ),
            (
                "python3 -m pytest tests/test_retry.py::test_backoff",
                "python3 -m pytest tests/test_retry.py -k happy",
            ),
            ("python3 -m pytest tests/test_retry.py", "python3 -m unittest tests.test_retry"),
            (
                "python3 -m unittest tests.test_retry_more.Retry.test_backoff",
                "python3 -m unittest tests.test_retry",
            ),
        ):
            with self.subTest(failed=failed, passed=passed):
                self.session = checks.Transcript(self.cwd)
                self.session.prompt("Continue")
                self.session.bash(failed, is_error=True)
                self.session.bash(passed)
                self.assertEqual({"failed", "passed"}, {row["result"] for row in self.checks()})

    def test_the_same_scope_in_another_directory_cannot_retire_the_failure(self) -> None:
        self.session.bash("python3 -m unittest tests.test_retry.Retry.test_backoff", is_error=True)
        self.session.bash("cd elsewhere && python3 -m unittest tests.test_retry")
        self.assertEqual({"failed", "passed"}, {row["result"] for row in self.checks()})

    def test_a_different_explicit_interpreter_or_environment_cannot_cover_the_failure(self) -> None:
        for first, second in (
            ("/venv/a/python3", "/venv/b/python3"),
            ("MODE=old python3", "MODE=new python3"),
        ):
            with self.subTest(first=first):
                self.session = checks.Transcript(self.cwd)
                self.session.prompt("Continue")
                self.session.bash(
                    first + " -m unittest tests.test_retry.Retry.test_backoff", is_error=True
                )
                self.session.bash(second + " -m unittest tests.test_retry")
                self.assertEqual({"failed", "passed"}, {row["result"] for row in self.checks()})

    def test_a_later_failure_is_not_hidden_by_an_earlier_broader_pass(self) -> None:
        self.session.bash("python3 -m unittest tests.test_retry")
        self.session.bash("python3 -m unittest tests.test_retry.Retry.test_backoff", is_error=True)
        self.assertEqual({"failed", "passed"}, {row["result"] for row in self.checks()})


class TheFourFailureReadersAgree(ThePageKeepsAClaimSecondary):
    def test_live_analysis_answer_and_correction_share_the_last_person_boundary(self) -> None:
        for failed_at in (tier.SAVE - 1, tier.SAVE, tier.SAVE + 1):
            with self.subTest(failed_at=failed_at):
                facts = [
                    {**tier.check("failed", failed_at, "failed"), "source_session": claims.SID},
                    claims._person("person", tier.SAVE, "Continue"),
                    tier.check("passed", tier.SAVE + 2, "passed"),
                ]
                fresh = failed_at > tier.SAVE
                evidence = tier.evidence(
                    facts, tier.scan(failed=1, passed=1, last_user_at=tier.SAVE)
                )
                live = levels.live_level(evidence, tier.intent("Tests pass"))
                analysis = tier.analyze(tier.SUPPORTED, evidence)
                composed = correction.compose(
                    {
                        **claims.SID,
                        "annotation_goal": "Tests pass",
                        "annotation_window_start": tier.SAVE - 10,
                    },
                    facts,
                    floor=0,
                    lines_judged=True,
                )
                page = self.fixture(f"""
const facts={json.dumps(facts)};
const session={{harness:"claude",sid:"s1",annotation_window_start:{tier.SAVE - 10}}};
const entries=nextCockpitWorkEntries(session,{{facts}});
const shape={{windowStart:{tier.SAVE - 10},criteria:[{{key:"line_1",result:NEXT_READING_CONSISTENT,restsOn:true}}]}};
console.log(JSON.stringify({{answer:nextDriftAnswer(shape,entries).kind,
  correction:nextCockpitFailedChecks(session,entries).length > 0}}));
""")
                self.assertEqual(fresh, live.level == levels.HIGH)
                self.assertEqual(fresh, analysis.level == levels.HIGH)
                self.assertEqual(fresh, composed["ok"])
                self.assertEqual(fresh, page["correction"])
                self.assertEqual("failed-check" if fresh else "nothing-found", page["answer"])

    def test_a_person_anchor_outside_the_fact_tail_keeps_all_four_readers_in_agreement(
        self,
    ) -> None:
        facts = [{**tier.check("failed", tier.SAVE + 1, "failed"), "source_session": claims.SID}]
        scan = tier.scan(failed=1, last_user_at=tier.SAVE)
        evidence = tier.evidence(facts, scan)
        self.assertEqual(levels.HIGH, levels.live_level(evidence, tier.intent("Tests pass")).level)
        self.assertEqual(levels.HIGH, tier.analyze(tier.SUPPORTED, evidence).level)
        composed = correction.compose(
            {
                **claims.SID,
                "annotation_goal": "Tests pass",
                "annotation_window_start": tier.SAVE - 10,
            },
            facts,
            floor=0,
            lines_judged=True,
            person_at=tier.SAVE,
        )
        self.assertTrue(composed["ok"])
        out = self.fixture(f"""
nextData.annotate=true;
const session={{harness:"claude",sid:"s1",annotation_window_start:{tier.SAVE - 10},annotation_goal:"Tests pass",annotation_revision:1}};
const annotation={{goal:"Tests pass",revision:1}};
const entries=nextCockpitWorkEntries(session,{{facts:{json.dumps(facts)}}});
const source={{state:"read",entries,all:entries,scan:{json.dumps(scan)}}};
const shape={{criteria:[{{key:"line_1",result:NEXT_READING_CONSISTENT,restsOn:true}}],windowStart:{tier.SAVE - 10}}};
const offer=nextCockpitSteerOffer(session,annotation,source,null);
console.log(JSON.stringify({{answer:nextDriftAnswer(shape,entries,source.scan).kind,offer,
  ids:nextCockpitCorrectionFailedIds(session,source),
  trigger:nextCockpitSteerTrigger(offer,null,session,entries,new Map([["failed",1]]),source.scan)}}));
""")
        self.assertEqual("failed-check", out["answer"])
        self.assertTrue(out["offer"]["failed"])
        self.assertEqual(["failed"], out["ids"])
        self.assertIn("Check failed at #1", out["trigger"])

    def test_the_mapped_failure_reason_says_files_changed_when_they_did(self) -> None:
        fact = {
            **tier.check("aged", 140, "failed"),
            "source_session": claims.SID,
            "before_last_change": True,
        }
        out = self.fixture(f"""
nextData.generated=200;
const session={{harness:"claude",sid:"s1"}};
const entries=nextCockpitWorkEntries(session,{{facts:{json.dumps([fact])}}});
console.log(JSON.stringify(nextDriftReasons("medium",["failed-check"],["aged"],entries,new Map([["aged",1]]),new Set())));
""")
        self.assertIn("files changed after it", out["first"])
        self.assertNotIn("no passing re-run", out["first"])

    def test_a_goal_only_answer_cannot_become_a_failed_check_answer(self) -> None:
        out = self.fixture("""
const entries=[{type:"user_message",id:"p",at:10},
  {type:"tool_report",subject:"check",result:"failed",id:"f",at:20}];
console.log(JSON.stringify(nextDriftAnswer({criteria:[{key:"goal",result:NEXT_READING_UNVERIFIABLE}]},entries)));
""")
        self.assertEqual("cant-tell", out["kind"])


class TheButtonNamesTheEvidenceAndBudget(ThePageKeepsAClaimSecondary):
    def test_not_enough_analysis_does_not_hide_the_live_high_pill(self) -> None:
        got = self.fixture("""
const session={harness:"claude",sid:"s1",annotation_goal:"Tests pass",annotation_revision:1};
const annotation={goal:"Tests pass",revision:1};
const live={level:"high",label:"High",reasons:{first:"Check failed",blockers:[]}};
const analysis={level:"not_enough",label:"Not enough recorded yet",reasons:{first:"",blockers:[]}};
console.log(JSON.stringify(nextDriftLevel(session,annotation,null,live,analysis)));
""")
        self.assertIn('next-session-drift-level">High', got)
        self.assertNotIn('next-session-drift-level">Not enough', got)

    def test_the_daily_budget_distinguishes_unknown_from_measured_zero(self) -> None:
        got = self.fixture("""
nextData.reading={used:4,limit:12};
const available=nextReadingBudgetLine();
nextData.reading={used:12,limit:12};
const zero=nextReadingBudgetLine();
nextData.reading={reason:"store-unavailable"};
console.log(JSON.stringify({available,zero,unknown:nextReadingBudgetLine()}));
""")
        self.assertIn("8 of 12 left today", got["available"])
        self.assertIn("0 of 12 left today", got["zero"])
        self.assertEqual("", got["unknown"])

    def test_the_trigger_names_its_entry_age_and_current_failure(self) -> None:
        got = self.fixture("""
nextData.generated=200;
const entries=[{id:"p",type:"user_message",at:100},
  {id:"f",type:"tool_report",subject:"check",result:"failed",at:140,title:"test retry"}];
const session={annotation_window_start:50};
console.log(JSON.stringify(nextCockpitSteerTrigger({failed:true,departed:false,claimed:false},
  null,session,entries,new Map([["f",2]]))));
""")
        self.assertIn("#2", got)
        self.assertIn("ago", got)
        self.assertIn("failed", got)

    def test_new_work_is_counted_after_the_reading_not_after_the_save(self) -> None:
        got = self.fixture("""
const annotation={assessment:{read_at:100}};
const entries=[{type:"tool_report",subject:"write",at:90},
  {type:"tool_report",subject:"write",at:110},
  {type:"tool_report",subject:"check",at:120}];
console.log(JSON.stringify(nextReadingArrivedLine(annotation,entries)));
""")
        self.assertIn("1 check", got)
        self.assertIn("1 file write", got)
        self.assertIn("since this analysis", got)

    def test_a_marked_reading_cannot_offer_a_correction(self) -> None:
        stored = {
            "revision_read": 1,
            "window_start": 50,
            "read_at": 500,
            "criteria": {"goal": {"result": reading.RESULT_DEPARTURE, "cites": ["a1"]}},
        }
        row = {
            **claims.SID,
            "annotation_goal": "Ship the retry",
            "annotation_revision": 1,
            "annotation_assessment": stored,
            "annotation_not_accurate": True,
        }
        self.assertEqual(
            {"ok": False, "reason": "nothing"},
            correction.compose(row, [claims.SAID], floor=50, lines_judged=True),
        )

    def test_an_adopted_goal_cites_its_source_or_shows_the_clip(self) -> None:
        row = {
            **claims.SID,
            "annotation_goal": "Ship the retry",
            "annotation_goal_source": "latest-prompt",
            "annotation_goal_source_at": 60,
            "annotation_window_start": 50,
        }
        person = claims._person("goal-source", 60, "Ship the retry with safe backoff")
        failed = claims._check("f", 95, "failed")
        found = correction.compose(row, [person, failed], floor=50, lines_judged=True)
        self.assertIn({"entry": "goal-source"}, found["parts"])
        missing = correction.compose(
            row, [claims._person("p0", 50, "Continue"), failed], floor=50, lines_judged=True
        )
        self.assertIn("Ship the retry…", "".join(p for p in missing["parts"] if isinstance(p, str)))


class ThePageAndComposerOfferTheSameCorrection(ThePageKeepsAClaimSecondary):
    def test_offer_parity_includes_directions_claims_failures_and_marked_readings(self) -> None:
        for state in (
            "quiet",
            "direction",
            "claim",
            "fresh failure",
            "older failure",
            "departure",
            "marked",
        ):
            with self.subTest(state=state):
                criteria = {}
                facts = [claims._person("p0", 60, "Continue"), claims.SAID]
                if state in {"direction", "older failure"}:
                    facts.append(claims._person("later", 120, "Pause the retry"))
                if state in {"fresh failure", "older failure"}:
                    facts.append(claims._check("f", 95, "failed"))
                if state == "claim":
                    criteria = {"claims": {"result": reading.RESULT_UNSUPPORTED, "cites": ["a1"]}}
                if state in {"departure", "marked"}:
                    criteria = {"goal": {"result": reading.RESULT_DEPARTURE, "cites": ["a1"]}}
                stored = {
                    "revision_read": 1,
                    "window_start": 50,
                    "read_at": 500,
                    "criteria": criteria,
                }
                row = {
                    **claims.SID,
                    "annotation_goal": "Ship the retry",
                    "annotation_revision": 1,
                    "annotation_window_start": 50,
                    "annotation_settled_through": 120,
                    "annotation_assessment": stored,
                    "annotation_not_accurate": state == "marked",
                }
                annotation = {
                    "goal": "Ship the retry",
                    "revision": 1,
                    "window_start": 50,
                    "settled_through": 120,
                    "assessment": stored,
                    "not_accurate": state == "marked",
                }
                actual = correction.compose(row, facts, floor=50, lines_judged=True)
                page = self.fixture(f"""
nextData.annotate=true;
const session={json.dumps(row)};
const annotation={json.dumps(annotation)};
const entries=nextCockpitWorkEntries(session,{{facts:{json.dumps(facts)}}});
const shape=nextCockpitReadingShape(annotation.assessment,annotation,entries,"",false);
const offer=nextCockpitSteerOffer(session,annotation,{{state:"read",entries,all:entries}},shape);
console.log(JSON.stringify(Boolean(offer)));
""")
                self.assertEqual(actual["ok"], page)

    def test_a_missing_or_older_signal_never_nudges_an_analyze_spend(self) -> None:
        got = self.fixture("""
const work={all:[{id:"p",type:"user_message",at:100},
  {id:"old",type:"tool_report",subject:"check",result:"failed",at:90},
  {id:"new",type:"tool_report",subject:"check",result:"failed",at:110}]};
console.log(JSON.stringify([nextDriftSignalAnchored({cites:["old"]},work),
  nextDriftSignalAnchored({cites:["new"]},work),nextDriftSignalAnchored({cites:["missing"]},work)]));
""")
        self.assertEqual([False, True, False], got)
