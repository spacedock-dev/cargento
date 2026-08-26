from __future__ import annotations

import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextWorkstreamBehaviorTest(NextPageJsHarness):
    FIXTURE = """
location.hash = "#n=project:alpha%2Frepo";
__els.app = {innerHTML: ""};
let __workstreamPayload = {
  generated: 1000,
  summary: {working: 0, needs_input: 0},
  harnesses: [{key: "claude", label: "Claude Code"}],
  sessions: [{
    sid: "session-one", harness: "claude", project: "alpha/repo",
    state: "idle", state_detail: "awaiting your message", rate_per_min: 1,
    finished_at: null, active: false, subagents: []
  }],
  asks: []
};
__fetchImpl = async () => ({ok: true, json: async () => __workstreamPayload});
"""

    def run_fixture(self, checks: str) -> object:
        return self._run_page_js("await __settle();\n" + checks, self.FIXTURE)

    def test_successive_payloads_render_three_chronological_state_entries(self) -> None:
        out = self.run_fixture(
            """
for(const [generated, state, rate] of [
  [1060, "working", 2],
  [1120, "needs_input", 3],
  [1180, "idle", 4]
]){
  __workstreamPayload = {
    ...__workstreamPayload, generated,
    sessions: [{...__workstreamPayload.sessions[0], state, rate_per_min: rate}]
  };
  await refreshNext();
}
const window = nextWorkstreamProjectWindow("alpha/repo");
console.log(JSON.stringify({
  events: window.events.map(event => ({
    at: event.at, from: event.fromState, state: event.state, to: event.toState
  })),
  samples: window.samples.map(sample => sample.rate),
  html: __els.app.innerHTML
}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(
            [
                {"at": 1060, "from": "idle", "state": "working", "to": "working"},
                {
                    "at": 1120,
                    "from": "working",
                    "state": "needs_input",
                    "to": "needs_input",
                },
                {"at": 1180, "from": "needs_input", "state": "idle", "to": "idle"},
            ],
            out["events"],
        )
        self.assertEqual([1, 2, 3, 4], out["samples"])
        self.assertLess(out["html"].index("agent resumed"), out["html"].index("needs input"))
        self.assertLess(out["html"].index("needs input"), out["html"].index("became idle"))

    def test_prompt_resumption_is_attended_on_both_project_summaries(self) -> None:
        out = self.run_fixture(
            """
for(const generated of [1600, 2200]){
  __workstreamPayload = {
    ...__workstreamPayload, generated,
    sessions: [{...__workstreamPayload.sessions[0], state: "working"}]
  };
  await refreshNext();
}
const window = nextWorkstreamProjectWindow("alpha/repo");
nextWorkstreamCollapsed = true;
renderNext();
console.log(JSON.stringify({event: window.events[0], html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        self.assertFalse(out["event"]["filled"])
        self.assertIn("0 of 1 unattended", out["html"])
        self.assertIn("1 human turn", out["html"])

    def test_state_transition_classifier_preserves_gate_and_agent_events(self) -> None:
        out = self._run_page_js(
            """
console.log(JSON.stringify([
  nextWorkstreamTransition("idle", "working"),
  nextWorkstreamTransition("needs_input", "working"),
  nextWorkstreamTransition("working", "needs_input"),
  nextWorkstreamTransition("working", "idle")
]));
"""
        )

        self.assertEqual(
            [
                {"filled": False, "humanTurn": True},
                {"filled": False, "humanTurn": True},
                {"filled": False, "humanTurn": False},
                {"filled": True, "humanTurn": False},
            ],
            out,
        )

    def test_turn_stop_and_new_ask_use_measured_times_and_honest_labels(self) -> None:
        out = self.run_fixture(
            """
__workstreamPayload = {
  ...__workstreamPayload,
  generated: 1060,
  sessions: [{
    ...__workstreamPayload.sessions[0], state: "working", active: true,
    finished_at: 1030, rate_per_min: 8
  }],
  asks: [{
    id: "ask-new", session_id: "session-one", harness: "claude",
    project: "alpha/repo", question: "Choose <img src=x onerror=1>", age_sec: 15
  }]
};
await refreshNext();
const window = nextWorkstreamProjectWindow("alpha/repo");
console.log(JSON.stringify({
  events: window.events.map(event => ({at: event.at, kind: event.kind, right: event.right})),
  html: __els.app.innerHTML
}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(
            [
                {"at": 1030, "kind": "turn", "right": "CC"},
                {"at": 1045, "kind": "ask", "right": "asked you"},
                {"at": 1060, "kind": "state", "right": "CC"},
            ],
            out["events"],
        )
        self.assertIn("Choose &lt;img src=x onerror=1&gt;", out["html"])
        self.assertNotIn("Choose <img", out["html"])
        self.assertNotIn("you steered", out["html"])
        self.assertNotIn("failed", out["html"])

    def test_the_buffer_is_bounded_and_keeps_the_newest_entries(self) -> None:
        out = self._run_page_js(
            """
for(let index = 0; index < NEXT_WORKSTREAM_ENTRY_CAP + 10; index += 1){
  nextWorkstreamAppendGroup({
    at: index + 1,
    samples: [],
    events: [{kind: "state", project: "alpha/repo", at: index + 1}]
  });
}
const window = nextWorkstreamProjectWindow("alpha/repo");
console.log(JSON.stringify({
  cap: NEXT_WORKSTREAM_ENTRY_CAP,
  count: nextWorkstreamEntryCount,
  length: window.events.length,
  first: window.events[0].at,
  last: window.events[window.events.length - 1].at
}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(out["cap"], out["count"])
        self.assertEqual(out["cap"], out["length"])
        self.assertEqual(11, out["first"])
        self.assertEqual(out["cap"] + 10, out["last"])

    def test_the_window_label_reflects_the_retained_buffer(self) -> None:
        out = self.run_fixture(
            """
__workstreamPayload = {
  ...__workstreamPayload, generated: 1120,
  sessions: [{...__workstreamPayload.sessions[0], state: "working"}]
};
await refreshNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(out, str)

        self.assertIn("last 2m", out)
        self.assertNotIn("6h", out)

    def test_click_and_keyboard_collapse_use_only_the_namespaced_key(self) -> None:
        out = self._run_page_js(
            """
await __settle();
const toggle = {dataset: {nextWorkstreamToggle: ""}, closest(selector){
  return selector === "[data-next-workstream-toggle]" ? this : null;
}};
__fire("click", {target: toggle, preventDefault(){}});
const afterClick = __els.app.innerHTML;
__fire("keydown", {target: toggle, key: "Enter", preventDefault(){}});
const afterKeyboard = __els.app.innerHTML;
console.log(JSON.stringify({afterClick, afterKeyboard, writes: __storageWrites}));
""",
            """
const __storageWrites = [];
const localStorage = {
  getItem(){ return null; },
  setItem(key, value){ __storageWrites.push([key, value]); }
};
"""
            + self.FIXTURE,
        )
        assert isinstance(out, dict)

        self.assertIn("data-next-workstream-collapsed", out["afterClick"])
        self.assertNotIn("data-next-workstream-collapsed", out["afterKeyboard"])
        self.assertEqual(
            [
                ["cargento.next.workstream.collapsed", "1"],
                ["cargento.next.workstream.collapsed", "0"],
            ],
            out["writes"],
        )

    def test_localstorage_failure_leaves_an_honest_expanded_empty_state(self) -> None:
        out = self._run_page_js(
            """
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
""",
            """
const localStorage = {
  getItem(){ throw new Error("private mode"); },
  setItem(){ throw new Error("private mode"); }
};
"""
            + self.FIXTURE,
        )
        assert isinstance(out, str)

        self.assertIn("WORKSTREAM", out)
        self.assertIn("No workstream events since this tab opened.", out)
        self.assertNotIn("data-next-workstream-collapsed", out)


if __name__ == "__main__":
    unittest.main()
