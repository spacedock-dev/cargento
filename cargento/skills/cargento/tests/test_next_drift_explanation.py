"""Existing shaped assessments and recorded signals explain their evidence, not an onset."""

from __future__ import annotations

import json
import shutil
import unittest

from cargento_runtime import levels

from .test_next_analysis_result import (
    DEPARTS,
    FACTS,
    MIXED,
    UNVERIFIABLE,
    _report,
    _ResultPage,
    assessment,
    criterion,
)
from .test_next_drift_panel import JOB
from .test_next_intent_draft import TYPED, drift_of
from .test_next_live_estimate import CHECK, _LivePage, live
from .visible_text import visible_text

SECOND = _report(
    "c-second", 105.1, "check", result="failed", result_at=105.8, summary="ruff check src/parser"
)
TWO = assessment(
    {
        **MIXED["criteria"],
        "line_1": {
            **criterion(DEPARTS, "c-fail", "c-second", detail="Two parser checks failed."),
            "clause": "The parser tests pass",
        },
    },
    evidence_through=105.8,
)


@unittest.skipUnless(shutil.which("node"), "node not available")
class AssessmentExplanationTest(_ResultPage):
    def test_same_check_in_two_departures_keeps_only_the_first_source_open_and_focused(
        self,
    ) -> None:
        value = assessment(
            {
                **MIXED["criteria"],
                "goal": criterion(DEPARTS, "c-fail", detail="The recorded check failed."),
                "line_1": criterion(DEPARTS, "c-fail", detail="The parser check failed."),
            }
        )
        after = r"""
let markup=__els.app.innerHTML, disclosures=[], focused=[];
__els.app.querySelectorAll=selector => selector === '[data-next-cockpit-disclosure]'
  ? disclosures : selector === '[data-next-focus]' ? disclosures.map(d=>d.summary) : [];
Object.defineProperty(__els.app,'innerHTML',{get:()=>markup,set:value=>{
  markup=value;
  disclosures=[...value.matchAll(/<details\b[^>]*data-next-cockpit-disclosure="([^"]+)"([^>]*)>/g)]
    .map(match=>{
      const summary={dataset:{},setAttribute(name,value){if(name==='data-next-focus')this.dataset.nextFocus=value;},
        focus(){document.activeElement=this;focused.push(this.dataset.nextFocus);}};
      return {key:match[1],open:/\bopen\b/.test(match[2]),summary,
        getAttribute(){return this.key;},querySelector(){return summary;}};
    });
}});
__els.app.innerHTML=markup;
nextCockpitAfterRender();
let sources=disclosures.filter(d=>d.key.includes('assessment-source:'));
const keys=sources.map(d=>d.key);
sources[0].open=true;document.activeElement=sources[0].summary;
const focus=nextCaptureFocus();
nextCockpitBeforeRender(focus);
renderNext();
sources=disclosures.filter(d=>d.key.includes('assessment-source:'));
console.log(JSON.stringify({keys,open:sources.map(d=>d.open),
  focus:document.activeElement.dataset.nextFocus,first:sources[0].summary.dataset.nextFocus,
  sameNode:document.activeElement===sources[0].summary,focused}));
"""
        result = self.page(value, levels.HIGH, after=after)
        self.assertEqual(2, len(result["keys"]))
        self.assertEqual(2, len(set(result["keys"])))
        self.assertEqual([True, False], result["open"])
        self.assertEqual(result["first"], result["focus"])
        self.assertTrue(result["sameNode"])
        self.assertEqual([result["first"]], result["focused"])

    def test_live_claim_and_intent_source_keys_have_distinct_scopes(self) -> None:
        after = """
const entry={id:'same',type:'tool_report',subject:'check',result:'failed',at:105,
  sourceSession:{harness:'claude',sid:'focus-1'},source:'native check'};
const byId=new Map([['same',entry]]),numbers=new Map([['same',1]]);
const account=key=>nextCockpitAssessmentAccount({key,citedIds:['same','same'],detail:'Synthetic.'},numbers,byId);
const html=account('goal')+account('line_1')+account('claims')+
  nextDriftRecordedSignals({reasons:['failed-check'],cites:['same','same']},{all:[entry]},numbers);
console.log(JSON.stringify([...html.matchAll(/data-next-cockpit-disclosure="([^"]+)"/g)].map(m=>m[1])));
"""
        keys = self.page(None, after=after)
        self.assertEqual(4, len(keys))
        self.assertEqual(4, len(set(keys)))

    def test_retained_detail_clause_and_both_checks_are_open_in_the_result(self) -> None:
        html = drift_of(self.page(TWO, levels.HIGH, facts=(*FACTS, SECOND)))
        text = visible_text(html)
        self.assertIn("Model assessment", text)
        self.assertIn("The parser tests pass", text)
        self.assertIn("Two parser checks failed.", text)
        self.assertIn("pytest tests/lexer", text)
        self.assertIn("ruff check src/parser", text)
        self.assertIn("Call recorded at", text)
        self.assertIn("1970-01-01 00:01:45 UTC", text)
        self.assertIn("Result recorded at 1970-01-01 00:01:45 UTC", text)
        self.assertNotIn("departed from your intent at", text)
        self.assertNotIn("Departs at", text)
        self.assertNotIn("Departure at", text)

    def test_repeated_citations_are_once_per_account_and_untrusted_prose_is_escaped(self) -> None:
        value = assessment(
            {
                **TWO["criteria"],
                "line_1": criterion(DEPARTS, "c-fail", "c-fail", detail="<img src=x>"),
            }
        )
        html = drift_of(self.page(value, levels.HIGH))
        self.assertNotIn("<img src=x>", html)
        self.assertIn("&lt;img src=x&gt;", html)
        self.assertEqual(1, html.count("Call recorded at"))

    def test_old_revision_uses_its_retained_clause_beside_the_existing_warning(self) -> None:
        old = assessment(TWO["criteria"], revision_read=1)
        text = visible_text(drift_of(self.page(old, levels.HIGH, facts=(*FACTS, SECOND))))
        self.assertIn("Model assessment", text)
        self.assertIn("Read intent: The parser tests pass", text)
        self.assertIn("Your intent changed after this analysis.", text)

    def test_missing_detail_has_an_explicit_limit_without_an_invented_explanation(self) -> None:
        no_detail = assessment(
            {**TWO["criteria"], "line_1": criterion(DEPARTS, "c-fail", "c-second")}
        )
        text = visible_text(drift_of(self.page(no_detail, levels.HIGH, facts=(*FACTS, SECOND))))
        self.assertIn("No explanation was retained for this assessment.", text)
        self.assertNotIn("Two parser checks failed.", text)

    def test_demoted_row_does_not_publish_its_detail_or_assessment_evidence(self) -> None:
        invalid = assessment(
            {**TWO["criteria"], "line_1": criterion(DEPARTS, "missing", detail="Invented reason")}
        )
        text = visible_text(drift_of(self.page(invalid, levels.NOT_ENOUGH)))
        self.assertNotIn("Invented reason", text)
        self.assertNotIn("Model assessment", text)

    def test_claim_explanation_has_its_own_home_and_preserves_both_kinds_of_evidence(self) -> None:
        agent = {
            "fact_id": "agent-claim",
            "type": "agent_message",
            "subject": "",
            "at": 104.7,
            "summary": "The parser tests passed.",
            "source_session": {"harness": "claude", "sid": "focus-1"},
            "evidence": {"source": "native agent message", "confidence": "exact"},
        }
        value = assessment(
            {
                "goal": criterion(UNVERIFIABLE),
                "line_1": criterion(UNVERIFIABLE),
                "claims": criterion(
                    DEPARTS,
                    "agent-claim",
                    "c-fail",
                    detail="The later check contradicts the claim.",
                ),
            }
        )
        text = visible_text(drift_of(self.page(value, levels.HIGH, facts=(*FACTS, agent))))
        self.assertIn("What the agent claimed", text)
        self.assertIn("The later check contradicts the claim.", text)
        self.assertIn("Agent message", text)
        self.assertIn("native agent message", self.page(value, levels.HIGH, facts=(*FACTS, agent)))
        self.assertIn("pytest tests/lexer", text)
        self.assertNotIn("Departs from your intent", text)

    def test_not_accurate_keeps_its_existing_warning_and_busy_hides_the_old_result(self) -> None:
        text = visible_text(drift_of(self.page(TWO, levels.HIGH, not_accurate=True)))
        self.assertIn("You marked this analysis not accurate.", text)
        self.assertLess(
            text.index("You marked this analysis not accurate."), text.index("Model assessment")
        )
        self.assertNotIn("High Analysis", text)
        busy = visible_text(drift_of(self.page(TWO, levels.HIGH, extra=JOB)))
        self.assertNotIn("Two parser checks failed.", busy)
        self.assertNotIn("Model assessment", busy)


@unittest.skipUnless(shutil.which("node"), "node not available")
class RecordedSignalExplanationTest(_LivePage):
    def test_call_label_uses_structural_claude_check_fields_only(self) -> None:
        for harness, subject, expected in (
            ("claude", "check", "Call recorded at"),
            ("pi", "check", "Evidence recorded at"),
            ("claude", "write", "Evidence recorded at"),
        ):
            entry = {
                "id": "fixture",
                "type": "tool_report",
                "subject": subject,
                "sourceSession": {"harness": harness, "sid": "fixture"},
                "source": "English words are not a timestamp contract",
                "at": 105,
            }
            expression = (
                "console.log(JSON.stringify(nextDriftEvidenceRows(['fixture'],new Map(),"
                f"new Map([['fixture',{json.dumps(entry)}]]),'structural-clock')));"
            )
            text = visible_text(self.drive(after=expression))
            self.assertIn(expected, text)
            if expected != "Call recorded at":
                self.assertNotIn("Call recorded at", text)

    def test_live_signal_names_all_reasons_and_event_time_without_a_model_assessment(self) -> None:
        setup = (
            TYPED
            + CHECK
            + """
__semantic.facts.push({fact_id:"write-outside",at:104.6,type:"tool_report",subject:"write",
  summary:"docs/synthetic-guide.md",source_session:{harness:"claude",sid:"focus-1"},
  evidence:{source:"native Write call",confidence:"exact"}});
"""
        )
        html = self.on(
            live(
                reasons=["failed-check", "writes-outside-folders"],
                cites=["c-fail", "write-outside"],
            ),
            setup,
        )
        text = visible_text(drift_of(html))
        self.assertIn("Recorded signals", text)
        self.assertIn("A check failed", text)
        self.assertIn("outside the folders", text)
        self.assertIn("Call recorded at", text)
        self.assertIn("1970-01-01 00:01:44 UTC", text)
        self.assertIn("docs/synthetic-guide.md", text)
        self.assertNotIn("Model assessment", text)
        self.assertNotIn("entry is not listed", text)
        self.assertIn("No model assessment for this intent yet.", text)

    def test_reader_and_native_source_text_are_upright_while_model_detail_keeps_its_register(
        self,
    ) -> None:
        html = _ResultPage().page(TWO, levels.HIGH, facts=(*FACTS, SECOND))
        self.assertIn('class="next-cockpit-assessment-clause"', html)
        self.assertIn('class="next-cockpit-assessment-entry"', html)
        self.assertIn('class="next-cockpit-reading-detail">Two parser checks failed.', html)

    def test_an_unavailable_reader_does_not_nudge_to_analyze(self) -> None:
        setup = (
            TYPED
            + CHECK
            + """
__dashboard.reading_routes.claude = {provider:null, note:"No reading CLI is installed."};
"""
        )
        text = visible_text(drift_of(self.on(live(reasons=["failed-check"]), setup)))
        self.assertIn("No reading CLI is installed.", text)
        self.assertNotIn("Analyze to see what drifted", text)

    def test_retained_assessment_is_not_relabelled_as_no_model_assessment(self) -> None:
        setup = (
            TYPED
            + CHECK
            + """
__s.annotation_reading_count=1;
__s.annotation_assessment={revision_read:1,read_at:104,criteria:{goal:{result:"not verifiable from available evidence",cites:[]}}};
"""
        )
        text = visible_text(drift_of(self.on(live(reasons=["failed-check"]), setup)))
        self.assertNotIn("No model assessment for this intent yet.", text)

    def test_recorded_call_and_paired_result_times_are_distinct_from_estimate_computation(
        self,
    ) -> None:
        setup = TYPED + CHECK.replace("at:104.5", "at:100.5,result_at:103.5")
        text = visible_text(drift_of(self.on(live(reasons=["failed-check"]), setup)))
        self.assertIn("Call recorded at 1970-01-01 00:01:40 UTC", text)
        self.assertIn("Result recorded at 1970-01-01 00:01:43 UTC", text)
        self.assertNotIn("Evidence recorded at 1970-01-01 00:01:44 UTC", text)

    def test_unknown_time_and_missing_reference_do_not_use_the_computation_time(self) -> None:
        setup = TYPED + CHECK.replace("at:104.5", "at:null")
        text = visible_text(drift_of(self.on(live(reasons=["failed-check"]), setup)))
        self.assertIn("time not recorded", text)
        missing = visible_text(drift_of(self.on(live(reasons=["failed-check"], cites=["missing"]))))
        self.assertIn("entry is not listed", missing)
        self.assertNotIn("Evidence recorded at", missing)
