from __future__ import annotations

import re
import shutil
import unittest

from cargento_runtime.notifications import asking_title

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextSessionBehaviorTest(NextPageJsHarness):
    SID = "session-1234567890abcdef"
    FIXTURE = f"""
location.hash = "#n=session:alpha%2Frepo:{SID}";
__els.app = {{innerHTML: ""}};
const __nextPayload = {{
  generated: 10000,
  window_hours: 24,
  ask: true,
  summary: {{working: 0, needs_input: 1}},
  harnesses: [
    {{key: "claude", label: "Claude Code"}},
    {{key: "codex", label: "Codex"}}
  ],
  sessions: [{{
    sid: "{SID}", session: "session-", harness: "claude", project: "alpha/repo",
    state: "needs_input", active: true, title: "Resolve the gate",
    last_prompt: "Older instruction", state_detail: "open question · AskUserQuestion",
    blocked_since: 9400, last_activity: 9400, started_at: 8200,
    session_output_tokens: 12500, turn_output_tokens: 2400,
    turn: {{elapsed_h: "5m"}},
    tasks: [
      {{id: "task-pending", subject: "Prepare payload", status: "pending"}},
      {{id: "task-done", subject: "Ship parser", status: "completed"}},
      {{id: "task-live", subject: "Review response", status: "in_progress"}}
    ],
    subagents: [
      {{name: "worker-a", model: "sonnet", started_at: 9700}},
      {{name: "worker-b", model: "opus", started_at: null}}
    ]
  }}],
  asks: [
    {{
      id: "ask-one", harness: "claude", session_id: "{SID}", project: "alpha/repo",
      question: "Choose <img src=x onerror='1'>", options: ["Approve", "<Later>"]
    }},
    {{
      id: "wrong-session", harness: "claude", session_id: "session-123", project: "alpha/repo",
      question: "Do not show a prefix match", options: ["Wrong"]
    }},
    {{
      id: "ask-two", harness: "claude", session_id: "{SID}", project: "alpha/repo",
      question: "Then choose again", options: ["Continue"]
    }}
  ]
}};
let __answerResult = {{answered: true}};
__fetchImpl = async url => ({{
  ok: true,
  json: async () => url === "/api/answer" ? __answerResult : __nextPayload
}});
"""

    def render(self, checks: str = "console.log(JSON.stringify(__els.app.innerHTML));") -> object:
        return self._run_page_js("await __settle();\n" + checks, self.FIXTURE)

    @staticmethod
    def task_row(html: str, task_id: str) -> str:
        match = re.search(
            rf'<div[^>]*data-next-session-task="{re.escape(task_id)}"[\s\S]*?</div>',
            html,
        )
        if match is None:
            raise AssertionError(f"no task row for {task_id!r} in {html}")
        return match.group(0)

    @staticmethod
    def subagent_row(html: str, index: int) -> str:
        match = re.search(
            rf'<div[^>]*data-next-session-subagent="{index}"[\s\S]*?</div>',
            html,
        )
        if match is None:
            raise AssertionError(f"no subagent row for {index!r} in {html}")
        return match.group(0)

    def test_plain_session_uses_the_last_instruction_and_only_measured_metadata(self) -> None:
        html = self.render(
            """
const session = nextData.sessions[0];
Object.assign(session, {
  state: "working", title: "Compile the release", state_detail: "running tests",
  blocked_since: null, tasks: [], subagents: [],
  session_output_tokens: null, turn_output_tokens: null
});
nextData.asks = [];
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn(f'data-next-session-detail="{self.SID}"', html)
        self.assertIn(">Compile the release</h1>", html)
        self.assertIn("Claude Code · session- · running tests · started 5m ago", html)
        self.assertNotIn("started 30m ago", html)
        self.assertNotIn("blocked ", html)
        self.assertNotIn("AGENT IS ASKING", html)
        self.assertNotIn("TASKS ·", html)
        self.assertNotIn("SUBAGENTS", html)
        self.assertNotIn("output tokens", html)

    def test_session_age_metadata_matches_state_and_requires_measurement(self) -> None:
        out = self.render(
            """
const session = nextData.sessions[0];
const variants = {};
session.state = "working";
renderNext();
variants.working = __els.app.innerHTML;
for(const [name, turn] of Object.entries({
  noTurn: null,
  missingElapsed: {},
  emptyElapsed: {elapsed_h: ""},
  malformedElapsed: {elapsed_h: 5}
})){
  session.turn = turn;
  renderNext();
  variants[name] = __els.app.innerHTML;
}
session.state = "idle";
session.turn = {elapsed_h: "5m"};
renderNext();
variants.idle = __els.app.innerHTML;
session.started_at = null;
renderNext();
variants.idleWithoutStart = __els.app.innerHTML;
session.state = "needs_input";
session.blocked_since = 9400;
renderNext();
variants.waiting = __els.app.innerHTML;
console.log(JSON.stringify(variants));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("started 5m ago", out["working"])
        self.assertNotIn("started 30m ago", out["working"])
        for variant in ("noTurn", "missingElapsed", "emptyElapsed", "malformedElapsed"):
            with self.subTest(variant=variant):
                self.assertNotIn("started ", out[variant])
        self.assertIn("session started 30m ago", out["idle"])
        self.assertNotIn("session started", out["idleWithoutStart"])
        self.assertIn("blocked 10m", out["waiting"])

    def test_health_callout_uses_only_measured_long_turns_and_tool_loops(self) -> None:
        out = self.render(
            """
const session = nextData.sessions[0];
const variants = {};
session.state = "working";
session.turn = {elapsed_h: "5m", long: true};
session.loop = null;
renderNext();
variants.longOnly = __els.app.innerHTML;
session.turn.long = false;
session.loop = {errors: 4, tool: "Bash"};
renderNext();
variants.loopOnly = __els.app.innerHTML;
session.loop = {errors: 4};
renderNext();
variants.loopWithoutTool = __els.app.innerHTML;
session.turn.long = true;
session.loop = {errors: 4, tool: "Bash"};
renderNext();
variants.both = __els.app.innerHTML;
for(const state of ["idle", "needs_input"]){
  session.state = state;
  session.turn = null;
  renderNext();
  variants[state] = __els.app.innerHTML;
}
for(const [name, loop] of Object.entries({
  absent: null,
  zero: {errors: 0, tool: "Bash"},
  fractional: {errors: 4.5, tool: "Bash"},
  stringCount: {errors: "4", tool: "Bash"},
  missingCount: {tool: "Bash"}
})){
  session.state = "working";
  session.turn = null;
  session.loop = loop;
  renderNext();
  variants[name] = __els.app.innerHTML;
}
session.turn = {long: "true"};
session.loop = null;
renderNext();
variants.truthyLong = __els.app.innerHTML;
session.loop = {
  errors: 5,
  tool: "mcp__claude_ai_Linear__save_issue<img src=x onerror='1'>"
};
renderNext();
variants.mcp = __els.app.innerHTML;
console.log(JSON.stringify(variants));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(1, out["longOnly"].count("data-next-session-health="))
        self.assertIn('data-next-session-health="long-turn"', out["longOnly"])
        self.assertIn("LONG TURN", out["longOnly"])
        self.assertIn("This request is running long (or estimated to).", out["longOnly"])
        self.assertIn('role="note" aria-label="LONG TURN"', out["longOnly"])
        self.assertNotIn('role="alert"', out["longOnly"])

        self.assertEqual(1, out["loopOnly"].count("data-next-session-health="))
        self.assertIn('data-next-session-health="failed-tool-loop"', out["loopOnly"])
        self.assertIn("FAILED TOOL LOOP", out["loopOnly"])
        self.assertIn("4 tool calls in a row came back as errors", out["loopOnly"])
        self.assertIn("most recently Bash", out["loopOnly"])
        self.assertIn("4 tool calls in a row came back as errors", out["loopWithoutTool"])
        self.assertNotIn("most recently", out["loopWithoutTool"])

        self.assertEqual(1, out["both"].count("data-next-session-health="))
        self.assertIn('data-next-session-health="long-turn"', out["both"])
        self.assertIn("LONG TURN", out["both"])
        self.assertIn("4 tool calls in a row came back as errors", out["both"])
        self.assertNotIn("FAILED TOOL LOOP", out["both"])
        self.assertNotIn("This request is running long (or estimated to).", out["both"])

        for state in ("idle", "needs_input"):
            with self.subTest(state=state):
                self.assertIn("FAILED TOOL LOOP", out[state])
                self.assertIn("4 tool calls in a row came back as errors", out[state])
        for variant in (
            "absent",
            "zero",
            "fractional",
            "stringCount",
            "missingCount",
            "truthyLong",
        ):
            with self.subTest(variant=variant):
                self.assertNotIn("data-next-session-health", out[variant])

        self.assertIn("Linear · save issue&lt;img", out["mcp"])
        self.assertNotIn("claude_ai_", out["mcp"])
        self.assertNotIn("<img src=x", out["mcp"])

    def test_blocked_session_renders_all_exact_asks_in_payload_order_and_escapes_them(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertIn("next-session-detail--blocked", html)
        self.assertIn(
            "Claude Code · session- · open question · AskUserQuestion · blocked 10m", html
        )
        self.assertIn(asking_title("Claude Code"), html)
        self.assertEqual(1, html.count("AGENT IS ASKING"))
        self.assertEqual(2, html.count("data-next-session-ask="))
        self.assertLess(
            html.index('data-next-session-ask="ask-one"'),
            html.index('data-next-session-ask="ask-two"'),
        )
        self.assertNotIn("Do not show a prefix match", html)
        self.assertIn("Choose &lt;img src=x onerror=&#39;1&#39;&gt;", html)
        self.assertNotIn("Choose <img", html)
        self.assertIn('data-next-answer="ask-one" data-next-answer-index="1"', html)
        self.assertIn("&lt;Later&gt;", html)

    def test_question_is_only_the_title_when_no_instruction_exists(self) -> None:
        html = self.render(
            """
nextData.sessions[0].title = "";
nextData.sessions[0].last_prompt = "";
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn(">Choose &lt;img src=x onerror=&#39;1&#39;&gt;</h1>", html)

    def test_task_bearing_claude_session_keeps_payload_order_and_status_glyphs(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertIn("TASKS · 1 OF 3 DONE", html)
        positions = [
            html.index(f'data-next-session-task="{task_id}"')
            for task_id in ("task-pending", "task-done", "task-live")
        ]
        self.assertEqual(sorted(positions), positions)
        pending = self.task_row(html, "task-pending")
        done = self.task_row(html, "task-done")
        live = self.task_row(html, "task-live")
        self.assertIn("next-session-task--pending", pending)
        self.assertIn('aria-label="pending">○</span>', pending)
        self.assertIn('aria-label="completed">✓</span>', done)
        self.assertIn('aria-label="in progress">●</span>', live)

    def test_non_claude_session_does_not_claim_foreign_tasks(self) -> None:
        html = self.render(
            """
nextData.sessions[0].harness = "codex";
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertNotIn("TASKS ·", html)
        self.assertNotIn("Prepare payload", html)

    def test_subagents_keep_payload_order_and_omit_unmeasured_elapsed_time(self) -> None:
        html = self.render()
        assert isinstance(html, str)

        self.assertIn("SUBAGENTS", html)
        self.assertLess(html.index("worker-a"), html.index("worker-b"))
        measured = self.subagent_row(html, 0)
        unmeasured = self.subagent_row(html, 1)
        self.assertIn("next-live", measured)
        self.assertIn("next-live", unmeasured)
        self.assertIn('aria-label="running">●</span>', measured)
        self.assertIn("worker-a", measured)
        self.assertIn("5m", measured)
        self.assertNotIn("sonnet", measured)
        self.assertIn("worker-b", unmeasured)
        self.assertNotIn("0m", unmeasured)
        self.assertNotIn("opus", unmeasured)

    def test_token_footer_uses_state_scoped_totals_fallbacks_and_real_zero(self) -> None:
        out = self.render(
            """
const session = nextData.sessions[0];
const variants = {};
session.state = "working";
renderNext();
variants.working = __els.app.innerHTML;
session.state = "needs_input";
renderNext();
variants.waiting = __els.app.innerHTML;
session.state = "idle";
renderNext();
variants.idle = __els.app.innerHTML;
session.state = "working";
session.turn_output_tokens = null;
renderNext();
variants.workingFallback = __els.app.innerHTML;
session.state = "needs_input";
session.session_output_tokens = null;
session.turn_output_tokens = 2400;
renderNext();
variants.waitingFallback = __els.app.innerHTML;
session.turn_output_tokens = null;
renderNext();
variants.absent = __els.app.innerHTML;
session.state = "working";
session.session_output_tokens = 12500;
session.turn_output_tokens = 0;
renderNext();
variants.turnZero = __els.app.innerHTML;
session.state = "idle";
session.session_output_tokens = 0;
session.turn_output_tokens = 2400;
renderNext();
variants.sessionZero = __els.app.innerHTML;
console.log(JSON.stringify(variants));
"""
        )
        assert isinstance(out, dict)

        self.assertIn(
            'data-next-session-tokens="turn">2.4k output tokens this turn', out["working"]
        )
        self.assertNotIn("12.5k output tokens", out["working"])
        for state in ("waiting", "idle"):
            with self.subTest(state=state):
                self.assertIn(
                    'data-next-session-tokens="session">12.5k output tokens this session',
                    out[state],
                )
                self.assertNotIn("2.4k output tokens", out[state])
        self.assertIn(
            'data-next-session-tokens="session">12.5k output tokens this session',
            out["workingFallback"],
        )
        self.assertIn(
            'data-next-session-tokens="turn">2.4k output tokens this turn',
            out["waitingFallback"],
        )
        self.assertNotIn("data-next-session-tokens", out["absent"])
        self.assertIn('data-next-session-tokens="turn">0 output tokens this turn', out["turnZero"])
        self.assertIn(
            'data-next-session-tokens="session">0 output tokens this session',
            out["sessionZero"],
        )

    def test_answer_posts_a_numeric_index_and_refreshes_after_confirmation(self) -> None:
        out = self.render(
            """
const html = __els.app.innerHTML;
const match = html.match(/data-next-answer="([^"]+)" data-next-answer-index="([^"]+)"/);
const dataset = {nextAnswer: match ? match[1] : "", nextAnswerIndex: match ? match[2] : ""};
__fire("click", {
  target: {closest(selector){
    return selector === "[data-next-answer]" ? {dataset} : null;
  }},
  preventDefault(){}
});
await __settle();
await __settle();
const post = __fetchCalls.find(call => call[0] === "/api/answer");
const body = post ? JSON.parse(post[1].body) : null;
console.log(JSON.stringify({body, calls: __fetchCalls.map(call => call[0]), html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual({"id": "ask-one", "index": 0}, out["body"])
        self.assertIs(type(out["body"]["index"]), int)
        self.assertGreaterEqual(out["calls"].count("/api/data"), 2)
        self.assertNotIn("no confirmation came back", out["html"])

    def test_unconfirmed_answer_keeps_the_ask_and_keys_its_failure_note(self) -> None:
        out = self.render(
            """
__answerResult = {answered: false};
__fire("click", {
  target: {closest(selector){
    return selector === "[data-next-answer]"
      ? {dataset: {nextAnswer: "ask-one", nextAnswerIndex: "1"}}
      : null;
  }},
  preventDefault(){}
});
await __settle();
await __settle();
const post = __fetchCalls.find(call => call[0] === "/api/answer");
console.log(JSON.stringify({body: JSON.parse(post[1].body), html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual({"id": "ask-one", "index": 1}, out["body"])
        self.assertIn("Choose &lt;img", out["html"])
        self.assertIn("Then choose again", out["html"])
        self.assertIn("no confirmation came back — it may already have been answered", out["html"])
        self.assertLess(
            out["html"].index('data-next-session-ask="ask-one"'),
            out["html"].index("no confirmation came back"),
        )
        self.assertLess(
            out["html"].index("no confirmation came back"),
            out["html"].index('data-next-session-ask="ask-two"'),
        )

    def test_ask_capability_gate_and_empty_arrays_leave_no_empty_section_labels(self) -> None:
        html = self.render(
            """
nextData.ask = false;
nextData.sessions[0].tasks = [];
nextData.sessions[0].subagents = [];
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertNotIn("AGENT IS ASKING", html)
        self.assertNotIn("TASKS ·", html)
        self.assertNotIn("SUBAGENTS", html)

    def test_unregistered_harness_uses_the_shared_generic_asking_title(self) -> None:
        html = self.render(
            """
nextData.sessions[0].harness = "unregistered";
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn(asking_title(""), html)
        self.assertNotIn("unregistered is asking you", html)

    def test_a_missing_sid_or_wrong_project_has_an_explicit_outside_payload_state(self) -> None:
        out = self.render(
            """
nextRoute = {view: "session", project: "alpha/repo", session: "missing"};
renderNext();
const missing = __els.app.innerHTML;
nextRoute = {view: "session", project: "other/repo", session: "session-1234567890abcdef"};
renderNext();
console.log(JSON.stringify({missing, wrongProject: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)

        for html in out.values():
            self.assertIn('data-next-session-state="outside-payload"', html)
            self.assertIn("This session is outside the current payload.", html)


if __name__ == "__main__":
    unittest.main()
