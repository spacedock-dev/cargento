"""Goal provenance and recorded departures on the first screen (DEC-20)."""

from __future__ import annotations

import re
import shutil
import unittest
from typing import Any

from . import test_next_sessions as sessions_tests
from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class SessionsDriftTest(NextPageJsHarness):
    def render(self, setup: str) -> str:
        result = self.run_js(
            setup + "\nrenderNext();\nconsole.log(JSON.stringify(__els.app.innerHTML));"
        )
        assert isinstance(result, str)
        return result

    def run_js(self, checks: str) -> Any:
        return self._run_page_js(
            'await __settle();\nnavigateNext({view:"sessions"});\nnextData.annotate = true;\n'
            + checks,
            sessions_tests.NextSessionsBehaviorTest.FIXTURE,
        )

    def row(self, html: str, sid: str) -> str:
        return sessions_tests.NextSessionsBehaviorTest.session_row(html, sid)

    def test_goal_source_is_typed_else_only_the_permitted_prompt(self) -> None:
        html = self.render("""
nextData.sessions[0].annotation_goal = "My typed destination";
nextData.sessions[0].instruction = {label:"asked",text:"Do not substitute this prompt"};
nextData.sessions[1].prompt_states_work = true;
nextData.sessions[1].title = "Build the export as requested";
nextData.sessions[2].instruction = {label:"asked",text:"Forbidden other harness prompt"};
nextData.sessions[3].instruction = {label:"asked",text:"Latest Claude request"};
nextData.sessions[4].annotation_goal = "Typed other harness goal";
nextData.sessions[5].title = "continue";
nextData.sessions[5].prompt_states_work = false;
""")

        def goal(sid: str) -> str:
            return sessions_tests.NextSessionsBehaviorTest.fact(self.row(html, sid), "goal")

        self.assertIn("YOUR WORDS", goal("gate-z"))
        self.assertIn("My typed destination", goal("gate-z"))
        self.assertNotIn("Do not substitute", goal("gate-z"))
        for sid, prompt in (
            ("gate-a", "Build the export as requested"),
            ("work-z", "Latest Claude request"),
        ):
            self.assertIn("YOUR LATEST PROMPT", goal(sid))
            self.assertNotIn("YOUR WORDS", goal(sid))
            self.assertIn(prompt, goal(sid))
            self.assertIn("data-next-goal-focus", goal(sid))
        self.assertIn("Typed other harness goal", goal("idle-old"))
        for sid in ("work-a", "idle-new"):
            self.assertIn("Add a goal", goal(sid))
        self.assertNotIn("Forbidden other harness prompt", goal("work-a"))
        self.assertNotIn("continue", goal("idle-new"))

    def test_blocked_then_drift_then_working_without_counting_idle_drift(self) -> None:
        html = self.render("""
nextData.sessions[4].departures = [{at:9400,revision:1}];
nextData.sessions[4].annotation_revision = 2;
nextData.asks.push({id:"idle-ask",harness:"codex",session_id:"idle-new",question:"Choose",options:[]});
""")
        active = sessions_tests.NextSessionsBehaviorTest.operation_group(html, "active")
        order = re.findall(r'data-next-session="([^"]+)"', active)
        self.assertIn("idle-old", order)
        self.assertLess(order.index("idle-new"), order.index("idle-old"))
        self.assertLess(order.index("gate-z"), order.index("idle-old"))
        self.assertLess(order.index("idle-old"), order.index("work-a"))
        self.assertEqual(1, html.count('data-next-session="idle-old"'))
        self.assertIn(
            'data-next-fleet-fact="active"><span>ACTIVE NOW</span><strong>5</strong>', html
        )
        row = self.row(html, "idle-old")
        self.assertIn("Drift", row)
        self.assertIn("10m ago", row)
        self.assertIn("This raise read revision 1. Revision 2 is current", row)

    def test_asked_departure_age_is_measured_and_consistent_is_not_a_mark(self) -> None:
        html = self.render("""
nextData.sessions[4].annotation_assessment = {revision_read:1,read_at:9700,
 criteria:{goal:{result:"departure",cites:["fact"]}}};
nextData.sessions[5].annotation_assessment = {revision_read:1,revision_read_at:10,
 stamp:"model · read at 10:00",criteria:{goal:{result:"departure",cites:["fact"]}}};
nextData.sessions[6].annotation_assessment = {revision_read:1,read_at:9700,
 criteria:{goal:{result:"consistent with the evidence read",cites:["fact"]}}};
""")
        self.assertIn("5m ago", self.row(html, "idle-old"))
        self.assertIn("age unknown", self.row(html, "idle-new"))
        self.assertNotIn("Drift", self.row(html, "idle-mid"))
        self.assertIn('data-next-operation-history="true"', self.row(html, "idle-mid"))
        self.assertIn(
            'data-next-fleet-fact="active"><span>ACTIVE NOW</span><strong>4</strong>', html
        )

    def test_annotations_off_hides_marks_and_goal_links_without_hiding_sessions(self) -> None:
        html = self.render("""
nextData.annotate = false;
nextData.sessions[4].departures = [{at:9400,revision:1}];
nextData.sessions[4].annotation_goal = "Store must be ignored";
""")
        self.assertNotIn("data-next-goal-focus", html)
        self.assertNotIn("data-next-session-drift-mark", html)
        self.assertNotIn("Store must be ignored", html)
        self.assertIn('data-next-operation-history="true"', self.row(html, "idle-old"))
        self.assertIn("Annotations off", self.row(html, "idle-old"))

    def test_goal_link_focuses_the_existing_composer_without_a_write(self) -> None:
        out = self.run_js("""
const key = nextCockpitHeldKey(nextData.sessions[1], "goal");
let focused = "";
const input = {dataset:{nextFocus:key}, focus(){focused = key;}};
__els.app.querySelectorAll = selector => selector === "[data-next-focus]" ? [input] : [];
const writes = [];
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => {if(init && init.method === "POST") writes.push(url); return upstream(url,init);};
const link = {dataset:{nextRoute:"session:solo%2Fapp:codex:gate-a"},
  hasAttribute(name){return name === "data-next-goal-focus";},
  closest(selector){return selector === "[data-next-route]" ? this : null;}};
__fire("click", {target:link,preventDefault(){}});
console.log(JSON.stringify({focused, expected:key, route:nextRoute, writes,
  composer:__els.app.innerHTML.includes('data-next-cockpit-held-kind="goal"')}));
""")
        self.assertEqual(out["expected"], out["focused"])
        self.assertEqual("gate-a", out["route"]["session"])
        self.assertTrue(out["composer"])
        self.assertEqual([], out["writes"])
