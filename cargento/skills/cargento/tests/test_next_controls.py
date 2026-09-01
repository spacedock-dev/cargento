from __future__ import annotations

import json
import shutil
import unittest

from .next_harness import NextPageJsHarness, storage_prelude


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextControlsBehaviorTest(NextPageJsHarness):
    PROJECT = "alpha/repo"
    STORAGE_KEY = "cargento.next.guardrails.alpha%2Frepo"
    FIXTURE = """
location.hash = "#n=project:alpha%2Frepo";
__els.app = {innerHTML: ""};
const __controlsPayload = {
  generated: 1000,
  summary: {working: 1, needs_input: 0},
  harnesses: [{key: "claude", label: "Claude Code"}],
  sessions: [{
    sid: "session-one", harness: "claude", project: "alpha/repo",
    state: "working", state_detail: "running tests", rate_per_min: 12,
    finished_at: null, active: true, subagents: []
  }],
  asks: []
};
__fetchImpl = async () => ({ok: true, json: async () => __controlsPayload});
"""

    def run_fixture(self, checks: str, *, storage: dict[str, str] | None = None) -> object:
        prelude = storage_prelude(storage or {}) + self.FIXTURE
        return self._run_page_js("await __settle();\n" + checks, prelude)

    def test_steer_and_guardrail_actions_issue_no_fetch_and_claim_no_delivery(self) -> None:
        stored = json.dumps([{"text": "Keep tests green", "enabled": True}])
        out = self.run_fixture(
            """
__fetchCalls = [];
const steer = {
  dataset: {nextControlsProject: "alpha/repo"},
  elements: {steer: {value: "Refocus <img src=x onerror=1>"}},
  closest(selector){ return selector === "[data-next-steer-form]" ? this : null; }
};
__fire("submit", {target: steer, preventDefault(){}});
steer.elements.steer.value = "Then <script>alert(2)</script>";
__fire("submit", {target: steer, preventDefault(){}});
const toggle = {
  dataset: {nextControlsProject: "alpha/repo", nextGuardrailToggle: "0"},
  closest(selector){ return selector === "[data-next-guardrail-toggle]" ? this : null; }
};
__fire("click", {target: toggle, preventDefault(){}});
console.log(JSON.stringify({
  calls: __fetchCalls.map(call => call[0]), html: __els.app.innerHTML,
  writes: __storageWrites, stored: __store
}));
""",
            storage={self.STORAGE_KEY: stored},
        )
        assert isinstance(out, dict)

        self.assertEqual([], out["calls"])
        first = "Refocus &lt;img src=x onerror=1&gt;"
        second = "Then &lt;script&gt;alert(2)&lt;/script&gt;"
        self.assertIn(first, out["html"])
        self.assertIn(second, out["html"])
        self.assertLess(out["html"].index(first), out["html"].index(second))
        self.assertNotIn("Refocus <img", out["html"])
        self.assertNotIn("Then <script>", out["html"])
        self.assertIn('class="next-steer-receipts"', out["html"])
        self.assertEqual(2, out["html"].count("data-next-steer-receipt"))
        self.assertEqual(2, out["html"].count("Not delivered."))
        self.assertEqual(2, out["html"].count("Cargento has no write path into a session."))
        self.assertIn('aria-checked="false"', out["html"])
        self.assertEqual([self.STORAGE_KEY], out["writes"])
        self.assertIn(self.STORAGE_KEY, out["stored"])
        self.assertEqual(
            [{"text": "Keep tests green", "enabled": False}],
            json.loads(out["stored"][self.STORAGE_KEY]),
        )

    def test_steer_receipts_render_the_retained_tail_in_submission_order(self) -> None:
        out = self.run_fixture(
            """
const form = {
  dataset: {nextControlsProject: "alpha/repo"},
  elements: {steer: {value: ""}},
  closest(selector){ return selector === "[data-next-steer-form]" ? this : null; }
};
for(let index = 0; index <= NEXT_STEER_RECORD_LIMIT; index += 1){
  form.elements.steer.value = `draft-${String(index).padStart(2, "0")}`;
  __fire("submit", {target: form, preventDefault(){}});
}
console.log(JSON.stringify({
  html: __els.app.innerHTML,
  retained: nextControlsProjectState("alpha/repo").steers.map(record => record.text)
}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual([f"draft-{index:02d}" for index in range(1, 21)], out["retained"])
        self.assertEqual(20, out["html"].count("data-next-steer-receipt"))
        self.assertNotIn(">draft-00<", out["html"])
        self.assertIn(">draft-01<", out["html"])
        self.assertIn(">draft-20<", out["html"])
        self.assertLess(out["html"].index(">draft-01<"), out["html"].index(">draft-20<"))
        self.assertEqual(20, out["html"].count("Not delivered."))

    def test_the_headers_and_rows_claim_no_enforcement(self) -> None:
        stored = json.dumps([{"text": "Keep tests green", "enabled": True}])
        html = self.run_fixture(
            "console.log(JSON.stringify(__els.app.innerHTML));",
            storage={self.STORAGE_KEY: stored},
        )
        assert isinstance(html, str)

        self.assertIn("STEER · LOCAL ONLY", html)
        self.assertIn("GUARDRAILS · LOCAL ONLY", html)
        self.assertIn("No observer is enforcing these.", html)
        self.assertIn("Saved in this browser. Nothing is enforcing it.", html)
        self.assertNotIn("observer ·", html)
        self.assertNotIn("observer holds the turn", html)
        self.assertNotIn("2 enforced", html)

    def test_a_hostile_stored_rule_is_escaped(self) -> None:
        hostile = '<img src=x onerror="globalThis.compromised=1">'
        stored = json.dumps([{"text": hostile, "enabled": True}])
        html = self.run_fixture(
            "console.log(JSON.stringify(__els.app.innerHTML));",
            storage={self.STORAGE_KEY: stored},
        )
        assert isinstance(html, str)

        self.assertIn("&lt;img src=x onerror=&quot;globalThis.compromised=1&quot;&gt;", html)
        self.assertNotIn("<img", html)

    def test_escape_cancels_and_enter_adds_through_the_one_keyboard_listener(self) -> None:
        out = self.run_fixture(
            """
const add = {
  dataset: {nextControlsProject: "alpha/repo"},
  closest(selector){ return selector === "[data-next-guardrail-add]" ? this : null; }
};
__fire("click", {target: add, preventDefault(){}});
const cancelInput = {
  value: "partial rule", tagName: "INPUT",
  dataset: {nextControlsProject: "alpha/repo"},
  closest(selector){ return selector === "[data-next-guardrail-input]" ? this : null; }
};
__fire("keydown", {target: cancelInput, key: "Escape", preventDefault(){}});
const afterEscape = __els.app.innerHTML;
__fire("click", {target: add, preventDefault(){}});
const addInput = {
  value: "Never render <script>", tagName: "INPUT",
  dataset: {nextControlsProject: "alpha/repo"},
  closest(selector){ return selector === "[data-next-guardrail-input]" ? this : null; }
};
__fire("keydown", {target: addInput, key: "Enter", preventDefault(){}});
console.log(JSON.stringify({
  afterEscape, html: __els.app.innerHTML,
  keydownListeners: (__listeners.keydown || []).length,
  stored: JSON.parse(__store["cargento.next.guardrails.alpha%2Frepo"])
}));
"""
        )
        assert isinstance(out, dict)

        self.assertNotIn("partial rule", out["afterEscape"])
        self.assertNotIn("data-next-guardrail-input", out["afterEscape"])
        self.assertIn("Never render &lt;script&gt;", out["html"])
        self.assertNotIn("Never render <script>", out["html"])
        self.assertEqual(1, out["keydownListeners"])
        self.assertEqual([{"text": "Never render <script>", "enabled": True}], out["stored"])

    def test_localstorage_failure_leaves_guardrails_usable_in_memory(self) -> None:
        out = self._run_page_js(
            """
await __settle();
const add = {
  dataset: {nextControlsProject: "alpha/repo"},
  closest(selector){ return selector === "[data-next-guardrail-add]" ? this : null; }
};
__fire("click", {target: add, preventDefault(){}});
const input = {
  value: "Stay local", tagName: "INPUT",
  dataset: {nextControlsProject: "alpha/repo"},
  closest(selector){ return selector === "[data-next-guardrail-input]" ? this : null; }
};
__fire("keydown", {target: input, key: "Enter", preventDefault(){}});
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

        self.assertIn("Stay local", out)
        self.assertIn("No observer is enforcing these.", out)


if __name__ == "__main__":
    unittest.main()
