from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextDelegationBehaviorTest(NextPageJsHarness):
    FIXTURE = """
location.hash = "#n=project:alpha%2Frepo";
__els.app = {innerHTML: ""};
let __delegationPayload = {
  generated: 1000,
  summary: {working: 0, needs_input: 0},
  harnesses: [{
    key: "claude", label: "Claude Code", reports_rate: true, error: null
  }],
  sessions: [{
    sid: "session-one", harness: "claude", project: "alpha/repo",
    state: "working", state_detail: "running", rate_per_min: 10,
    finished_at: null, active: false, subagents: []
  }],
  asks: []
};
__fetchImpl = async () => ({ok: true, json: async () => __delegationPayload});
"""

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js("await __settle();\n" + checks, self.FIXTURE)

    def delegation_block(self, html: str) -> str:
        match = re.search(r'<section class="next-delegation"[\s\S]*?</section>', html)
        self.assertIsNotNone(match)
        return match.group(0) if match else ""

    def test_known_split_reports_delegation_rate_and_human_turns(self) -> None:
        html = self.run_fixture(
            """
nextWorkstreamGroups[0].samples[0].state = "idle";
for(const [generated, state, rate] of [
  [1300, "needs_input", 100],
  [1600, "working", 30],
  [1900, "idle", 50],
  [2200, "working", 70]
]){
  __delegationPayload = {
    ...__delegationPayload, generated,
    sessions: [{...__delegationPayload.sessions[0], state, rate_per_min: rate}]
  };
  await refreshNext();
}
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("50%", block)
        self.assertIn("of the time ran without you", block)
        self.assertIn("30 tok/m while delegated", block)
        self.assertIn("2 human turns", block)
        self.assertIn("<progress", block)
        self.assertLess(html.index("DELEGATION"), html.index("STEER · LOCAL ONLY"))

    def test_gate_exit_across_idle_resumption_counts_one_human_turn(self) -> None:
        out = self.run_fixture(
            """
const session = __delegationPayload.sessions[0];
nextWorkstreamGroups = [];
nextWorkstreamEntryCount = 0;
nextWorkstreamPreviousSessions = new Map();
nextWorkstreamSeenAsks = new Map();
nextWorkstreamLastGenerated = null;
nextWorkstreamObservedSince = null;
nextObserveWorkstream({
  ...__delegationPayload,
  generated: 1000,
  sessions: [{...session, state: "needs_input"}]
});
for(const [generated, state] of [
  [1300, "idle"],
  [1600, "working"],
  [1900, "working"]
]){
  __delegationPayload = {
    ...__delegationPayload, generated, sessions: [{...session, state}]
  };
  nextObserveWorkstream(__delegationPayload);
}
nextData = __delegationPayload;
renderNext();
const window = nextWorkstreamProjectWindow("alpha/repo");
console.log(JSON.stringify({
  events: window.events.map(event => [event.fromState, event.toState]),
  html: __els.app.innerHTML,
  metric: nextDelegationMetric(window)
}));
"""
        )
        assert isinstance(out, dict)
        block = self.delegation_block(out["html"])

        self.assertEqual([["needs_input", "idle"], ["idle", "working"]], out["events"])
        self.assertEqual(1, out["metric"]["humanTurns"])
        self.assertIn("1 human turn", block)
        self.assertNotIn("2 human turns", block)

    def test_human_turn_coalescing_is_session_scoped_and_window_aware(self) -> None:
        out = self._run_page_js(
            """
const state = (at, sid, fromState, toState) => ({
  at, fromState, harness: "claude", kind: "state", sid, toState
});
const direct = [state(100, "one", "needs_input", "working")];
const sequence = [
  state(100, "one", "needs_input", "idle"),
  state(200, "one", "idle", "working")
];
const laterPrompt = [
  ...sequence,
  state(300, "one", "working", "idle"),
  state(400, "one", "idle", "working")
];
const interleaved = [
  state(100, "one", "needs_input", "idle"),
  state(150, "two", "idle", "working"),
  state(200, "one", "idle", "working")
];
console.log(JSON.stringify({
  direct: nextDelegationHumanTurns(direct, 0, 500),
  interleaved: nextDelegationHumanTurns(interleaved, 0, 500),
  laterPrompt: nextDelegationHumanTurns(laterPrompt, 0, 500),
  sequence: nextDelegationHumanTurns(sequence, 0, 500),
  windowSplit: nextDelegationHumanTurns(sequence, 150, 500)
}));
"""
        )

        self.assertEqual(
            {
                "direct": 1,
                "interleaved": 2,
                "laterPrompt": 2,
                "sequence": 1,
                "windowSplit": 0,
            },
            out,
        )

    def test_a_young_buffer_withholds_the_figure_and_bar(self) -> None:
        html = self.run_fixture(
            """
__delegationPayload = {...__delegationPayload, generated: 1300};
await refreshNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("no figure yet", block)
        self.assertIn("DELEGATION · SINCE THIS TAB OPENED", block)
        self.assertIsNone(re.search(r"\d", block))
        self.assertNotIn("%", block)
        self.assertNotIn("<progress", block)
        self.assertNotIn("tok/m", block)
        self.assertNotIn("human turn", block)

    def test_all_idle_time_does_not_become_delegated_time(self) -> None:
        html = self.run_fixture(
            """
nextWorkstreamGroups[0].samples[0].state = "idle";
__delegationPayload = {
  ...__delegationPayload,
  generated: 1600,
  sessions: [{...__delegationPayload.sessions[0], state: "idle"}]
};
await refreshNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("no figure yet", block)
        self.assertNotIn("%", block)
        self.assertNotIn("<progress", block)

    def test_idle_time_advances_the_observed_evidence_floor(self) -> None:
        html = self.run_fixture(
            """
nextWorkstreamGroups[0].samples[0].state = "idle";
for(const [generated, state] of [
  [1500, "working"],
  [1600, "working"]
]){
  __delegationPayload = {
    ...__delegationPayload, generated,
    sessions: [{...__delegationPayload.sessions[0], state}]
  };
  await refreshNext();
}
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("100%", block)
        self.assertNotIn("no figure yet", block)

    def test_project_absence_is_not_observed_delegated_time(self) -> None:
        out = self.run_fixture(
            """
const session = __delegationPayload.sessions[0];
__delegationPayload = {...__delegationPayload, generated: 1300, sessions: []};
await refreshNext();
__delegationPayload = {...__delegationPayload, generated: 1900, sessions: [{
  ...session, state: "working"
}]};
await refreshNext();
const window = nextWorkstreamProjectWindow("alpha/repo");
const metric = nextDelegationMetric(window);
const html = __els.app.innerHTML;
__delegationPayload = {...__delegationPayload, generated: 2200, sessions: [{
  ...session, state: "working"
}]};
await refreshNext();
const resumedMetric = nextDelegationMetric(nextWorkstreamProjectWindow("alpha/repo"));
console.log(JSON.stringify({
  batchRows: window.batches.map(batch => batch.rows.length),
  html,
  metric,
  resumedHtml: __els.app.innerHTML,
  resumedMetric
}));
"""
        )
        assert isinstance(out, dict)
        block = self.delegation_block(out["html"])

        self.assertEqual([1, 0, 1], out["batchRows"])
        self.assertEqual(300, out["metric"]["delegatedSec"])
        self.assertEqual(300, out["metric"]["totalSec"])
        self.assertEqual(300, out["metric"]["observedSec"])
        self.assertEqual(100, out["metric"]["delegatedPct"])
        self.assertEqual(0, out["metric"]["humanTurns"])
        self.assertIn("no figure yet", block)
        self.assertNotIn("<progress", block)
        self.assertEqual(600, out["resumedMetric"]["observedSec"])
        self.assertEqual(600, out["resumedMetric"]["delegatedSec"])
        self.assertIn("100%", self.delegation_block(out["resumedHtml"]))

    def test_another_projects_snapshot_is_an_absence_boundary(self) -> None:
        out = self.run_fixture(
            """
const session = __delegationPayload.sessions[0];
__delegationPayload = {...__delegationPayload, generated: 1300, sessions: [{
  ...session, sid: "session-two", project: "beta/repo"
}]};
await refreshNext();
__delegationPayload = {
  ...__delegationPayload, generated: 1900, sessions: [session]
};
await refreshNext();
const window = nextWorkstreamProjectWindow("alpha/repo");
console.log(JSON.stringify({
  batchRows: window.batches.map(batch => batch.rows.length),
  metric: nextDelegationMetric(window)
}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual([1, 0, 1], out["batchRows"])
        self.assertEqual(300, out["metric"]["observedSec"])
        self.assertEqual(300, out["metric"]["delegatedSec"])
        self.assertEqual(0, out["metric"]["humanTurns"])

    def test_known_gate_time_survives_an_unknown_absence(self) -> None:
        out = self.run_fixture(
            """
const session = __delegationPayload.sessions[0];
nextWorkstreamGroups[0].samples[0].state = "needs_input";
__delegationPayload = {...__delegationPayload, generated: 1300, sessions: []};
await refreshNext();
for(const generated of [1900, 2200]){
  __delegationPayload = {
    ...__delegationPayload, generated, sessions: [{...session, state: "working"}]
  };
  await refreshNext();
}
const metric = nextDelegationMetric(nextWorkstreamProjectWindow("alpha/repo"));
console.log(JSON.stringify(metric));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(600, out["observedSec"])
        self.assertEqual(600, out["totalSec"])
        self.assertEqual(300, out["delegatedSec"])
        self.assertEqual(50, out["delegatedPct"])
        self.assertEqual(0, out["humanTurns"])

    def test_no_delegated_segment_withholds_rate_instead_of_printing_zero(self) -> None:
        html = self.run_fixture(
            """
__delegationPayload = {
  ...__delegationPayload,
  generated: 1600,
  sessions: [{
    ...__delegationPayload.sessions[0], state: "needs_input", rate_per_min: 80
  }]
};
nextWorkstreamGroups = [];
nextWorkstreamEntryCount = 0;
nextWorkstreamPreviousSessions = new Map();
nextWorkstreamSeenAsks = new Map();
nextWorkstreamLastGenerated = null;
nextWorkstreamObservedSince = null;
nextObserveWorkstream({
  ...__delegationPayload,
  generated: 1000,
  sessions: [{
    ...__delegationPayload.sessions[0], state: "needs_input", rate_per_min: 40
  }]
});
nextObserveWorkstream(__delegationPayload);
nextData = __delegationPayload;
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("0%", block)
        self.assertIn("no token-rate figure", block)
        self.assertNotIn("0 tok/m", block)

    def test_gate_overrides_a_concurrent_working_session(self) -> None:
        html = self.run_fixture(
            """
const working = __delegationPayload.sessions[0];
const gated = {
  ...working, sid: "session-two", state: "needs_input", rate_per_min: 80
};
__delegationPayload = {
  ...__delegationPayload, generated: 1600, sessions: [working, gated]
};
nextWorkstreamGroups = [];
nextWorkstreamEntryCount = 0;
nextWorkstreamPreviousSessions = new Map();
nextWorkstreamSeenAsks = new Map();
nextWorkstreamLastGenerated = null;
nextWorkstreamObservedSince = null;
nextObserveWorkstream({...__delegationPayload, generated: 1000});
nextObserveWorkstream(__delegationPayload);
nextData = __delegationPayload;
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("0%", block)
        self.assertIn("no token-rate figure", block)
        self.assertNotIn("tok/m while delegated", block)

    def test_null_rate_turns_the_rate_into_a_floor_without_hiding_real_zero(self) -> None:
        out = self.run_fixture(
            """
const measured = __delegationPayload.sessions[0];
const measuredZero = {
  ...measured, sid: "session-zero", rate_per_min: 0
};
const unknown = {
  ...measured, sid: "session-two", harness: "cursor", rate_per_min: null
};
__delegationPayload = {
  ...__delegationPayload,
  generated: 1600,
  harnesses: [
    ...__delegationPayload.harnesses,
    {key: "cursor", label: "Cursor", reports_rate: false, error: null}
  ],
  sessions: [measured, measuredZero, unknown]
};
nextWorkstreamGroups = [];
nextWorkstreamEntryCount = 0;
nextWorkstreamPreviousSessions = new Map();
nextWorkstreamSeenAsks = new Map();
nextWorkstreamLastGenerated = null;
nextWorkstreamObservedSince = null;
nextObserveWorkstream({...__delegationPayload, generated: 1000});
nextObserveWorkstream(__delegationPayload);
nextData = __delegationPayload;
renderNext();
const samples = nextWorkstreamGroups.flatMap(group => group.samples);
console.log(JSON.stringify({
  html: __els.app.innerHTML,
  zeroKnown: samples.some(sample =>
    sample.sid === "session-zero" && sample.rate === 0 && sample.rateKnown),
  unknownKept: samples.some(sample =>
    sample.sid === "session-two" && sample.rate === null && !sample.rateKnown)
}));
"""
        )
        assert isinstance(out, dict)
        block = self.delegation_block(out["html"])

        self.assertIn("≥10 tok/m while delegated", block)
        self.assertTrue(out["zeroKnown"])
        self.assertTrue(out["unknownKept"])

    def test_the_heading_names_the_real_twelve_minute_window(self) -> None:
        html = self.run_fixture(
            """
__delegationPayload = {...__delegationPayload, generated: 1720};
await refreshNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("DELEGATION · LAST 12M", block)
        self.assertNotIn("LAST 6H", block)

    def test_no_trend_until_two_complete_six_hour_windows_exist(self) -> None:
        html = self.run_fixture(
            """
__delegationPayload = {...__delegationPayload, generated: 22600};
await refreshNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("DELEGATION · LAST 6H", block)
        self.assertNotIn("data-next-delegation-trend", block)

    def test_an_absence_gap_withholds_a_twelve_hour_trend(self) -> None:
        out = self._run_page_js(
            """
const working = {state: "working", rate: 10, rateKnown: true};
const window = {
  batches: [
    {at: 0, rows: [working]},
    {at: 21600, rows: [working]},
    {at: 21601, rows: []},
    {at: 21602, rows: [working]},
    {at: 43200, rows: [working]}
  ],
  endedAt: 43200,
  events: [],
  samples: [],
  startedAt: 0
};
console.log(JSON.stringify({
  current: nextDelegationRange(window, 21600, 43200),
  previous: nextDelegationRange(window, 0, 21600),
  trend: nextDelegationTrend(window)
}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(21_600, out["previous"]["observedSec"])
        self.assertEqual(21_599, out["current"]["observedSec"])
        self.assertIsNone(out["trend"])

    def test_trend_compares_two_complete_six_hour_windows(self) -> None:
        html = self.run_fixture(
            """
nextWorkstreamGroups[0].samples[0].state = "needs_input";
for(const [generated, state] of [
  [1600, "idle"],
  [22000, "working"],
  [22600, "working"],
  [23200, "idle"],
  [43600, "working"],
  [44200, "working"]
]){
  __delegationPayload = {
    ...__delegationPayload, generated,
    sessions: [{...__delegationPayload.sessions[0], state}]
  };
  await refreshNext();
}
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        block = self.delegation_block(html)

        self.assertIn("data-next-delegation-trend", block)
        self.assertIn("+50", block)


if __name__ == "__main__":
    unittest.main()
