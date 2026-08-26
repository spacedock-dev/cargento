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

    def test_unmeasured_session_turns_the_rate_into_a_floor(self) -> None:
        html = self.run_fixture(
            """
const measured = __delegationPayload.sessions[0];
const unknown = {
  ...measured, sid: "session-two", harness: "cursor", rate_per_min: 0
};
__delegationPayload = {
  ...__delegationPayload,
  generated: 1600,
  harnesses: [
    ...__delegationPayload.harnesses,
    {key: "cursor", label: "Cursor", reports_rate: false, error: null}
  ],
  sessions: [measured, unknown]
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

        self.assertIn("≥10 tok/m while delegated", block)

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
