from __future__ import annotations

import json
import re
import shutil
import unittest

from .next_harness import NextPageJsHarness, storage_prelude


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextControlsBehaviorTest(NextPageJsHarness):
    PROJECT = "alpha/repo"
    STORAGE_KEY = "cargento.next.guardrails.alpha%2Frepo"
    FIXTURE = """
location.hash = "#n=project:alpha%2Frepo:console";
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

    def test_a_typed_steer_draft_survives_a_render(self) -> None:
        # The worst of the four render losses, because it is the only one that
        # destroys something the reader cannot recreate by clicking. The input
        # was re-emitted with no `value` attribute, so a sentence in progress
        # died on the next revision: 20 s with EventSource, 5 s without.
        out = self.run_fixture(
            """
const typed = 'Refocus on <img src=x onerror=1> the failing test';
const drafts = [{
  dataset: {nextDraft: "steer", nextControlsProject: "alpha/repo"},
  value: typed
}];
__els.app.querySelectorAll = selector => selector === "[data-next-draft]" ? drafts : [];
renderNext();
console.log(JSON.stringify({html: __els.app.innerHTML, typed}));
"""
        )
        assert isinstance(out, dict)
        # Emitted with the live value, and escaped: the draft is reader-supplied
        # text going back into an attribute.
        self.assertIn(
            'value="Refocus on &lt;img src=x onerror=1&gt; the failing test"',
            out["html"],
        )
        self.assertNotIn("<img src=x", out["html"])

    def test_a_typed_guardrail_draft_survives_a_render(self) -> None:
        out = self.run_fixture(
            """
const add = {
  dataset: {nextControlsProject: "alpha/repo"},
  closest(selector){ return selector === "[data-next-guardrail-add]" ? this : null; }
};
__fire("click", {target: add, preventDefault(){}});
const drafts = [{
  dataset: {nextDraft: "guardrail", nextControlsProject: "alpha/repo"},
  value: "never force push"
}];
__els.app.querySelectorAll = selector => selector === "[data-next-draft]" ? drafts : [];
renderNext();
console.log(JSON.stringify({html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn('value="never force push"', out["html"])

    def test_the_caret_comes_back_where_the_reader_left_it(self) -> None:
        # Found on a real board during the after-walk. The value survived the
        # render and the caret did not: it landed at 0, so a reader typing in the
        # middle of a sentence would carry on at the beginning of it. Restoring
        # the text without the offset is a worse failure than losing both, since
        # the reader cannot see that it happened until the sentence is mangled.
        out = self.run_fixture(
            """
const ranges = [];
const drafts = [{
  dataset: {nextDraft: "steer", nextControlsProject: "alpha/repo"},
  value: "abcdefghij",
  selectionStart: 4,
  selectionEnd: 4,
  focus(){ document.activeElement = this; },
  setSelectionRange(start, end){ ranges.push([start, end]); },
  contains(active){ return active === this; }
}];
drafts[0].dataset.nextFocus = "steer-draft:alpha/repo";
__els.app.querySelectorAll = selector =>
  (selector === "[data-next-draft]" || selector === "[data-next-focus]") ? drafts : [];
// The reader's caret is IN the box; that is the whole scenario. Without this
// the focus snapshot is null and the lane that places the caret never runs.
document.activeElement = drafts[0];
renderNext();
console.log(JSON.stringify({ranges, html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual([[4, 4]], out["ranges"])
        self.assertIn('value="abcdefghij"', out["html"])

    def test_a_sent_steer_leaves_the_box_empty_and_does_not_resend(self) -> None:
        # The blocker the four tests above could not see. Each of them hands
        # `[data-next-draft]` a CONSTANT array, so the node it returns is not the
        # one the handler just read from; and the older keyboard test passes only
        # because its `__els.app` has no `querySelectorAll` at all, which makes
        # the capture a no-op. With a node that still exists at capture time, the
        # clear was overwritten: `renderNext`'s first statement re-read the
        # submitted node and put the sentence straight back. Measured before the
        # fix: the box kept the sentence for the life of the tab, and a second
        # send with nothing typed recorded it twice.
        out = self.run_fixture(
            """
const node = {
  dataset: {nextDraft: "steer", nextControlsProject: "alpha/repo"},
  value: "ship the fix", selectionStart: 5, selectionEnd: 5,
  focus(){ document.activeElement = this; },
  setSelectionRange(){},
  contains(active){ return active === this; }
};
// The node the render emits is the node still in the DOM when the next capture
// runs, which is what the constant-array stubs above cannot reproduce.
__els.app.querySelectorAll = selector =>
  (selector === "[data-next-draft]" || selector === "[data-next-focus]") ? [node] : [];
const form = {
  dataset: {nextControlsProject: "alpha/repo"},
  elements: {steer: node},
  closest(selector){ return selector === "[data-next-steer-form]" ? this : null; }
};
__fire("submit", {target: form, preventDefault(){}});
const afterFirst = {box: node.value, html: __els.app.innerHTML};
__fire("submit", {target: form, preventDefault(){}});
console.log(JSON.stringify({
  afterFirst, boxAfterSecond: node.value, html: __els.app.innerHTML
}));
"""
        )
        assert isinstance(out, dict)
        # The receipt carries the sentence; the box does not.
        self.assertEqual("", out["afterFirst"]["box"])
        self.assertIn('value=""', out["afterFirst"]["html"])
        self.assertEqual(1, out["afterFirst"]["html"].count("ship the fix"))
        # And a second send with nothing typed is a no-op rather than a duplicate.
        self.assertEqual("", out["boxAfterSecond"])
        self.assertEqual(1, out["html"].count("ship the fix"))

    def test_a_committed_guardrail_does_not_prefill_the_reopened_box(self) -> None:
        # The same blocker on the other input, and worse: the restored draft is
        # re-committable, so one Enter wrote the same rule to localStorage twice.
        # Both branches are covered, because an abandoned draft must not come
        # back either.
        for key, expected_rules in (("Enter", 1), ("Escape", 0)):
            with self.subTest(key=key):
                out = self.run_fixture(
                    """
const node = {
  dataset: {nextDraft: "guardrail", nextControlsProject: "alpha/repo",
            nextGuardrailInput: ""},
  value: "never force push", selectionStart: 4, selectionEnd: 4,
  focus(){ document.activeElement = this; },
  setSelectionRange(){},
  contains(active){ return active === this; },
  closest(selector){ return selector === "[data-next-guardrail-input]" ? this : null; }
};
__els.app.querySelectorAll = selector =>
  (selector === "[data-next-draft]" || selector === "[data-next-focus]") ? [node] : [];
__fire("keydown", {target: node, key: __KEY, preventDefault(){}});
// Reopening the add control is where the reader sees the prefill.
const add = {
  dataset: {nextControlsProject: "alpha/repo"},
  closest(selector){ return selector === "[data-next-guardrail-add]" ? this : null; }
};
__fire("click", {target: add, preventDefault(){}});
console.log(JSON.stringify({
  box: node.value, html: __els.app.innerHTML,
  stored: __store, writes: __storageWrites
}));
""".replace("__KEY", json.dumps(key))
                )
                assert isinstance(out, dict)
                self.assertEqual("", out["box"])
                # Read the INPUT tag, not a slice of the page: on Enter the rule
                # is SUPPOSED to appear, as a committed guardrail row. What must
                # not carry it is the reopened add box.
                add_box = re.search(r"<input data-next-guardrail-input[^>]*>", out["html"])
                self.assertIsNotNone(add_box)
                assert add_box is not None
                self.assertIn('value=""', add_box.group(0))
                self.assertNotIn("never force push", add_box.group(0))
                stored = json.dumps(out["stored"])
                self.assertEqual(expected_rules, stored.count("never force push"))

    def test_a_draft_is_not_written_to_browser_storage(self) -> None:
        # Deliberate. The guardrail RULES persist because a reader added them on
        # purpose; a half-typed sentence is not a decision, and reviving one in a
        # new tab hours later is a different feature from surviving a render.
        out = self.run_fixture(
            """
const drafts = [{
  dataset: {nextDraft: "steer", nextControlsProject: "alpha/repo"},
  value: "half a thought"
}];
__els.app.querySelectorAll = selector => selector === "[data-next-draft]" ? drafts : [];
renderNext();
console.log(JSON.stringify({writes: __storageWrites, stored: __store}));
"""
        )
        assert isinstance(out, dict)
        self.assertNotIn("half a thought", json.dumps(out["stored"]))
        self.assertNotIn("half a thought", json.dumps(out["writes"]))

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
