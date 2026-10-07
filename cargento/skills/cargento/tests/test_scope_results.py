"""Unfinished work at a non-final stop has its own neutral result."""

from __future__ import annotations

import shutil
import unittest
from typing import Any, cast
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import levels, reading

from . import test_correction as correction_tests
from . import test_levels as level_tests
from . import test_next_cockpit as cockpit_tests
from . import test_reading as reading_tests
from .next_harness import NextPageJsHarness, storage_prelude

NEUTRAL = "not reached at this stop"
DETAIL = "The placeholder PR is waiting on CI."


def criterion(result: str = NEUTRAL) -> dict[str, object]:
    return {"result": result, "cites": ["a1"], "detail": DETAIL, "clause": "Ship the parser"}


class TheScopeGoesToTheReading(unittest.TestCase):
    def test_the_header_names_work_so_far_and_a_neutral_result(self) -> None:
        header = reading._header(
            "Ship", ["Tests pass"], tool_note=True, claims=True, scope=reading.SCOPE_LAST_TURN
        )
        self.assertIn("work so far", header)
        self.assertIn("not_reached", header)
        self.assertIn("remainder", header)
        self.assertIn("unkept", header)

    def test_a_final_header_does_not_offer_the_non_final_token(self) -> None:
        header = reading._header("Ship", ["Tests pass"], tool_note=False, scope=reading.SCOPE_FINAL)
        self.assertIn("through the session end", header)
        self.assertNotIn('"not_reached"', header)

    def test_the_worst_intent_still_fits_every_line_inside_its_share(self) -> None:
        wide = "\U0001f600" * 240
        for scope in (reading.SCOPE_LAST_TURN, reading.SCOPE_MID_FLIGHT, reading.SCOPE_FINAL):
            with self.subTest(scope=scope):
                header = reading._header(wide, [wide] * 6, tool_note=True, claims=True, scope=scope)
                self.assertLessEqual(len(header.encode()), reading.INTENT_SHARE_BYTES)

    def test_in_flight_work_does_not_excuse_an_unkept_continuation(self) -> None:
        header = reading._header("Ship", ["Merged"], tool_note=True, scope=reading.SCOPE_MID_FLIGHT)
        for guard in (
            "unkept promise",
            "needless wait on the person",
            "remainder",
            "finished/ready overstatement",
            "Known departure stays in recovery",
            "e.g. unkept stalled promise",
        ):
            self.assertIn(guard, header)

    def test_a_wider_adopted_goal_keeps_the_same_final_scope(self) -> None:
        rows = (reading_tests.entry(id="a1", type="agent_message"),)
        prompt, selected = reading.build_prompt(
            rows,
            goal="Ship",
            lines=["Merged"],
            goal_words="Ship the entire placeholder parser with every review completed",
            max_bytes=16384,
            scope=reading.SCOPE_FINAL,
        )
        self.assertEqual(len(selected.entries), 1)
        self.assertIn("through the session end", prompt)
        self.assertNotIn('"not_reached"', prompt)

    def test_the_producer_sends_and_resolves_the_scope_it_actually_observed(self) -> None:
        helper = reading_tests.AClaudeCodeReadingProducer()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        agent = reading_tests.fact(
            fact_id="a1",
            type="agent_message",
            at=100,
            source_session={"harness": "claude", "sid": "s1"},
        )
        for state, end, stop, scope in (
            ("working", None, None, reading.SCOPE_MID_FLIGHT),
            ("idle", 150, None, reading.SCOPE_FINAL),
            ("idle", None, 150, reading.SCOPE_LAST_TURN),
        ):
            with (
                self.subTest(scope=scope),
                mock.patch.object(reading, "build_prompt", wraps=reading.build_prompt) as prompt,
                mock.patch.object(reading, "resolve", wraps=reading.resolve) as resolve,
            ):
                out, why, spent = reading.produce(
                    cast("Any", helper.config),
                    {
                        "harness": "claude",
                        "sid": "s1",
                        "state": state,
                        "ended_at": end,
                        "turn_end_at": stop,
                    },
                    [{"n": 1, "at": 50, "goal": "Ship", "output": "Merged"}],
                    [agent],
                    now=200,
                    stamp_text="read at 10:00",
                    model=helper._model(),
                    read_lines=True,
                    read_agent_words=True,
                    admit_turn_stop=True,
                )
                self.assertEqual(why, "")
                self.assertTrue(spent)
                self.assertIsNotNone(out)
                self.assertEqual(prompt.call_args.kwargs["scope"], scope)
                self.assertEqual(resolve.call_args.kwargs["scope"], scope)


class NotReachedIsNeitherUnverifiableNorADeparture(unittest.TestCase):
    def resolve(
        self, *, scope: str = "last-turn", cites: tuple[int, ...] = (1,)
    ) -> dict[str, reading.Criterion]:
        agent = reading_tests.entry(
            id="a1", type="agent_message", summary="CI is pending", at=level_tests.SAVE + 10
        )
        selected = reading.Selection((agent,), asked_output=True)
        return reading.resolve(
            {
                "goal": {"token": "consistent", "cites": [1]},
                "line_1": {"token": "not_reached", "cites": cites, "detail": DETAIL},
            },
            selected,
            goal="Ship",
            lines=["Merged"],
            detail_cap_chars=200,
            scope=scope,
        )

    def test_a_cited_neutral_result_keeps_its_explanation(self) -> None:
        got = self.resolve()["line_1"]
        self.assertEqual(got.get("result"), NEUTRAL)
        self.assertEqual(got["detail"], DETAIL)
        self.assertEqual(got["cites"], ("a1",))
        self.assertEqual(reading.token_for(NEUTRAL), "not_reached")

    def test_an_uncited_neutral_result_cannot_name_an_unproved_blocker(self) -> None:
        got = self.resolve(cites=())["line_1"]
        self.assertEqual(got.get("result"), reading.RESULT_UNVERIFIABLE)
        self.assertEqual(got["detail"], "")

    def test_the_token_is_for_intent_at_a_non_final_stop_only(self) -> None:
        self.assertIsNone(reading.result_for("claims", "not_reached"))
        self.assertNotIn("result", self.resolve(scope=reading.SCOPE_FINAL)["line_1"])
        for scope in (reading.SCOPE_WITHDRAWN, "", "invented"):
            self.assertNotIn("result", self.resolve(scope=scope)["line_1"])
        self.assertEqual(self.resolve(scope=reading.SCOPE_MID_FLIGHT)["line_1"]["result"], NEUTRAL)

    def test_the_store_refuses_neutral_claims_and_final_assessments(self) -> None:
        for scope, claims in (
            (reading.SCOPE_LAST_TURN, False),
            (reading.SCOPE_LAST_TURN, True),
            (reading.SCOPE_FINAL, False),
        ):
            rows = {"goal": criterion(reading.RESULT_CONSISTENT), "line_1": criterion()}
            if claims:
                rows["claims"] = criterion()
            stored = annotation_store._assessment(
                {"revision_read": 1, "scope": scope, "criteria": rows}, 200
            )
            self.assertEqual(stored is not None, scope == reading.SCOPE_LAST_TURN and not claims)

    def test_neutral_work_neither_raises_medium_nor_meets_the_floor(self) -> None:
        fact = reading_tests.fact(
            fact_id="a1",
            type="agent_message",
            at=level_tests.SAVE + 10,
            source_session={"harness": "claude", "sid": "S1"},
        )
        result = levels.analysis_level(
            {
                "scope": reading.SCOPE_LAST_TURN,
                "criteria": {"goal": criterion(reading.RESULT_CONSISTENT), "line_1": criterion()},
            },
            level_tests.evidence([fact], level_tests.scan()),
            outcome_lines=1,
        )
        self.assertEqual(result.level, levels.NOT_ENOUGH)
        self.assertIn("outcome-not-reached", result.reasons)
        self.assertNotIn(levels.REASON_DEPARTURE, result.reasons)

    def test_a_neutral_line_is_not_an_evidence_request_in_another_correction(self) -> None:
        rows = correction_tests.reading(
            goal=correction_tests.row_of(reading.RESULT_DEPARTURE, ("a1",)),
            line_1=correction_tests.row_of(NEUTRAL, ("a1",)),
            line_2=correction_tests.row_of(reading.RESULT_CONSISTENT, ("a1",)),
            line_3=correction_tests.row_of(reading.RESULT_CONSISTENT, ("a1",)),
        )
        rows["scope"] = reading.SCOPE_LAST_TURN
        fact = correction_tests.fact("a1", 112, "agent_message")
        out = correction_tests.compose(
            correction_tests.session_row(annotation_assessment=rows), facts=[fact]
        )
        text = correction_tests.rendered(out["parts"])
        self.assertIn("not reached at this stop", text)
        self.assertNotIn(f"{correction_tests.L1}: can you show evidence", text)
        self.assertNotIn(DETAIL, text)

    def test_an_unfinished_line_alone_never_offers_steer_back(self) -> None:
        rows = correction_tests.reading(
            goal=correction_tests.row_of(reading.RESULT_CONSISTENT, ("a1",)),
            line_1=correction_tests.row_of(NEUTRAL, ("a1",)),
            line_2=correction_tests.row_of(reading.RESULT_CONSISTENT, ("a1",)),
            line_3=correction_tests.row_of(reading.RESULT_CONSISTENT, ("a1",)),
        )
        rows["scope"] = reading.SCOPE_LAST_TURN
        out = correction_tests.compose(
            correction_tests.session_row(annotation_assessment=rows),
            facts=[correction_tests.fact("a1", 112, "agent_message")],
        )
        self.assertFalse(out["ok"])

    def test_a_final_or_missing_scope_cannot_be_leveled_from_unfinished_work(self) -> None:
        for scope in (reading.SCOPE_FINAL, "", "invented"):
            result = levels.analysis_level(
                {
                    "scope": scope,
                    "criteria": {
                        "goal": criterion(reading.RESULT_CONSISTENT),
                        "line_1": criterion(),
                    },
                },
                level_tests.evidence([], level_tests.scan()),
                outcome_lines=1,
            )
            self.assertIn(levels.REASON_READING_MALFORMED, result.reasons)

    def test_a_neutral_claim_cannot_enter_the_level(self) -> None:
        got = levels.analysis_level(
            {
                "scope": reading.SCOPE_LAST_TURN,
                "criteria": {
                    "goal": criterion(reading.RESULT_CONSISTENT),
                    "line_1": criterion(),
                    "claims": criterion(),
                },
            },
            level_tests.evidence([], level_tests.scan()),
            outcome_lines=1,
        )
        self.assertIn(levels.REASON_READING_MALFORMED, got.reasons)

    def test_unfinished_work_cannot_rest_on_an_invented_or_pre_window_citation(self) -> None:
        agent = reading_tests.entry(id="a1", type="agent_message", at=100)
        for cites, floor in (([19], 0), ([1], 101)):
            got = reading.resolve(
                {"goal": {"token": "not_reached", "cites": cites, "detail": DETAIL}},
                reading.Selection((agent,)),
                goal="Ship",
                detail_cap_chars=200,
                window_start=floor,
            )
            self.assertEqual(got["goal"].get("result"), reading.RESULT_UNVERIFIABLE)
            self.assertEqual(got["goal"]["detail"], "")

    def test_unfinished_work_never_retains_a_model_declaration_of_delivery(self) -> None:
        agent = reading_tests.entry(id="a1", type="agent_message", at=100)
        got = reading.resolve(
            {
                "goal": {
                    "token": "not_reached",
                    "cites": [1],
                    "detail": "The requested work was delivered and verified.",
                }
            },
            reading.Selection((agent,)),
            goal="Ship",
            detail_cap_chars=200,
        )
        self.assertEqual(got["goal"].get("result"), reading.RESULT_UNVERIFIABLE)
        self.assertEqual(got["goal"]["detail"], "")


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePageNamesUnfinishedWork(NextPageJsHarness):
    def page(self, suffix: str) -> Any:
        return self._run_page_js(
            "await __settle();\n"
            """
const annotation={goal:"Ship",lines:[{text:"Merged",source:"typed"}],revision:1};
const entries=[{id:"a1",type:"agent_message",by:"agent",author:"agent",at:95,
  source:"Claude assistant text · exact",summary:"CI pending"}];
const raw={revision_read:1,scope:"last-turn",criteria:{
  goal:{result:"consistent with the evidence read",cites:["a1"]},
  line_1:{result:"not reached at this stop",cites:["a1"],detail:"CI pending"}}};
""" + suffix,
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )

    def test_final_unknown_claims_and_uncited_neutral_results_are_refused(self) -> None:
        out = self.page("""
function line(){return nextCockpitReadingShape(raw,annotation,entries,"",false).criteria[1];}
const results=[];
for(const scope of ["final","withdrawn", ""]){raw.scope=scope;results.push(line().result);}
raw.scope="last-turn"; raw.criteria.line_1.cites=[]; results.push(line().result);
raw.criteria.claims={result:"not reached at this stop",cites:["a1"]};
results.push(nextCockpitReadingShape(raw,annotation,entries,"",false).criteria[2].result);
console.log(JSON.stringify(results));
""")
        self.assertEqual(out, [reading.RESULT_UNVERIFIABLE] * 5)

    def test_an_unfinished_claim_names_an_invalid_result_before_evidence_rules(self) -> None:
        out = self.page("""
const claim=nextCockpitReadingCriterion("claims","CLAIMS","",{
 result:"not reached at this stop",cites:["a1"]},entries,"",false,null,"last-turn");
console.log(JSON.stringify({reason:claim.why,malformed:NEXT_READING_MALFORMED}));
""")
        self.assertEqual(out["reason"], out["malformed"])

    def test_an_unfinished_explanation_is_visible_and_escaped_only_under_its_result(self) -> None:
        out = self.page("""
raw.criteria.line_1.detail="<script>placeholder</script> CI pending";
const row=nextCockpitReadingShape(raw,annotation,entries,"",false).criteria[1];
const neutral=nextCockpitResultItem(row,new Map(),new Map());
raw.criteria.line_1.cites=[];
const refused=nextCockpitResultItem(nextCockpitReadingShape(raw,annotation,entries,"",false)
  .criteria[1],new Map(),new Map());
console.log(JSON.stringify({neutral,refused}));
""")
        self.assertIn("&lt;script&gt;placeholder&lt;/script&gt; CI pending", out["neutral"])
        self.assertNotIn("<script>", out["neutral"])
        self.assertIn('data-next-result-state="not-reached"', out["neutral"])
        self.assertNotIn("CI pending", out["refused"])

    def test_an_unfinished_line_does_not_hide_a_separate_unverifiable_line(self) -> None:
        out = self.page("""
raw.criteria.line_2={result:"not verifiable from available evidence",cites:[]};
const shape=nextCockpitReadingShape(raw,annotation,entries,"",false);
console.log(JSON.stringify(nextDriftAnswer(shape,entries)));
""")
        self.assertEqual(out["kind"], "cant-tell")

    def test_the_row_and_answer_are_neutral_and_offer_no_correction(self) -> None:
        out = self._run_page_js(
            "await __settle();\n"
            """
const annotation = {goal:"Ship", lines:[{text:"Merged",source:"typed"}], revision:1};
const entries = [{id:"a1", type:"agent_message", by:"agent", at:95,
  author:"agent", summary:"CI is pending", source:"Claude assistant text · exact"}];
const raw = {revision_read:1,scope:"last-turn",criteria:{
  goal:{result:"consistent with the evidence read",cites:["a1"]},
  line_1:{result:"not reached at this stop",cites:["a1"],detail:"CI is pending"}}};
const shape = nextCockpitReadingShape(raw,annotation,entries,"",false);
const answer = nextDriftAnswer(shape,entries);
nextData.annotate = true;
console.log(JSON.stringify({answer:answer.kind,row:shape.criteria[1].result,
  status:nextCockpitResultStatus(shape.criteria[1],new Map(),new Map()),
  html:nextCockpitResultAnswer(answer,new Map(),new Map()),
  offer:nextCockpitSteerOffer({harness:"claude",sid:"placeholder",annotation_revision:1},
    annotation,{state:"read",entries,all:entries},shape)}));
""",
            storage_prelude({}) + cockpit_tests.NextCockpitCompositionTest.FIXTURE,
        )
        self.assertEqual(out["row"], NEUTRAL)
        self.assertEqual(out["answer"], "not-reached")
        self.assertIn("Not reached at this stop", out["status"])
        self.assertIn("Not reached at this stop", out["html"])
        self.assertNotIn("Can't tell", out["html"])
        self.assertIsNone(out["offer"])
