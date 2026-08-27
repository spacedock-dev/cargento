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

    def test_header_rail_names_only_known_states_and_keeps_the_blocked_alert(self) -> None:
        out = self.render(
            """
const session = nextData.sessions[0];
const variants = {};
for(const state of ["working", "idle", "needs_input", "unknown<script>"]){
  session.state = state;
  renderNext();
  variants[state] = __els.app.innerHTML;
}
console.log(JSON.stringify(variants));
"""
        )
        assert isinstance(out, dict)

        for state, label in (
            ("working", "working"),
            ("idle", "idle"),
            ("needs_input", "needs input"),
        ):
            with self.subTest(state=state):
                self.assertIn(f'data-next-session-state="{state}"', out[state])
                self.assertIn(f"State: {label}", out[state])
                self.assertIn(">Resolve the gate</h1>", out[state])
        self.assertNotIn("next-session-detail--blocked", out["working"])
        self.assertNotIn("next-session-detail--blocked", out["idle"])
        self.assertIn("next-session-detail--blocked", out["needs_input"])
        self.assertIn("AGENT IS ASKING", out["needs_input"])
        self.assertNotIn("data-next-session-state=", out["unknown<script>"])
        self.assertNotIn("State:", out["unknown<script>"])
        self.assertNotIn("unknown<script>", out["unknown<script>"])

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

    def test_multi_hour_metadata_and_subagent_ages_share_the_duration_grammar(self) -> None:
        out = self.render(
            """
const session = nextData.sessions[0];
const variants = {};
session.state = "working";
session.turn = {elapsed_h: "5h 40m"};
session.subagents[0].started_at = 2260;
renderNext();
variants.working = __els.app.innerHTML;
session.state = "idle";
session.started_at = 2260;
renderNext();
variants.idle = __els.app.innerHTML;
session.state = "needs_input";
session.blocked_since = 2260;
renderNext();
variants.waiting = __els.app.innerHTML;
console.log(JSON.stringify(variants));
"""
        )
        assert isinstance(out, dict)

        self.assertIn("started 5h 40m ago", out["working"])
        self.assertIn("2h 9m", self.subagent_row(out["working"], 0))
        self.assertIn("session started 2h 9m ago", out["idle"])
        self.assertIn("blocked 2h 9m", out["waiting"])
        for html in out.values():
            self.assertNotIn("129m", html)

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


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextInstructionLineTest(NextPageJsHarness):
    """The second line under a session title: what renders, and what refuses to.

    Line 1 answers "which session is this" and line 2 answers "what is it doing
    now". Each is labelled, because the two questions have different answers on
    a long session and a reader who cannot tell them apart is worse off than one
    who was shown nothing.
    """

    SID = "session-1234567890abcdef"
    BASE = """
location.hash = "#n=sessions";
__els.app = {{innerHTML: ""}};
const __nextPayload = {{
  generated: 10000,
  window_hours: 24,
  summary: {{working: 1, needs_input: 0}},
  harnesses: [{{key: "claude", label: "Claude Code"}}, {{key: "codex", label: "Codex"}}],
  sessions: [{{
    sid: "{sid}", session: "session-", harness: "claude", project: "alpha/repo",
    state: "working", active: true, title: {title},
    last_prompt: "", state_detail: "generating…",
    last_activity: 9400, started_at: 8200, instruction: {instruction},
    tasks: [], subagents: []
  }}]
}};
__fetchImpl = async () => ({{ok: true, json: async () => __nextPayload}});
"""

    def rows(self, instruction: str, title: str = '"Resolve the gate"') -> str:
        html = self._run_page_js(
            "await __settle();\nconsole.log(JSON.stringify(nextSessionsView()));",
            self.BASE.format(sid=self.SID, title=title, instruction=instruction),
        )
        assert isinstance(html, str)
        return html

    def detail(self, instruction: str, title: str = '"Resolve the gate"') -> str:
        html = self._run_page_js(
            "await __settle();\n"
            'nextRoute = {view: "session", project: "alpha/repo", '
            f'session: "{self.SID}"}};\n'
            "renderNext();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            self.BASE.format(sid=self.SID, title=title, instruction=instruction),
        )
        assert isinstance(html, str)
        return html

    def test_the_line_carries_its_label_and_the_age_of_the_record(self) -> None:
        # Never the text alone. "earlier" without an age is a claim about
        # recency the payload does not make, and an age without a label reads as
        # the newest instruction when it is not.
        line = '{label: "earlier", text: "Reconcile the registry", at: 9400}'
        for html in (self.rows(line), self.detail(line)):
            self.assertIn("earlier, 10m:", html)
            self.assertIn("Reconcile the registry", html)
            self.assertIn('data-next-instruction="earlier"', html)

    def test_each_label_in_the_vocabulary_renders_and_nothing_else_does(self) -> None:
        for label in ("asked", "agent", "earlier"):
            with self.subTest(label=label):
                html = self.detail(f'{{label: "{label}", text: "Real work", at: 9400}}')
                self.assertIn(f"{label}, 10m:", html)
        # A label the runtime does not publish is not rendered on trust. The
        # payload is a file this page did not write.
        for label in ("", "urgent", "<b>"):
            with self.subTest(label=label):
                html = self.detail(f'{{label: "{label}", text: "Real work", at: 9400}}')
                self.assertNotIn("Real work", html)

    def test_no_instruction_renders_line_one_alone(self) -> None:
        # The publish-nothing branch reaching the page. Never a blank row, and
        # never a placeholder standing where a measurement would be.
        for value in ("null", "undefined", '"a string"', "[]", "0"):
            with self.subTest(value=value):
                html = self.detail(value)
                self.assertIn("Resolve the gate", html)
                self.assertNotIn("next-instruction-label", html)

    def test_the_line_is_dropped_when_it_would_only_repeat_the_title(self) -> None:
        # `calm.js` already computes both fields and would show the same string
        # twice on a session whose first prompt is still its newest.
        same = '{label: "asked", text: "Resolve the gate", at: 9400}'
        self.assertNotIn("next-instruction-label", self.detail(same))
        # And once more across the two caps: line 1 clips at 80 and line 2 at
        # 140, so one prompt reaches them as two strings, the shorter ellipsed.
        clipped = '{label: "asked", text: "Resolve the gate and ship it", at: 9400}'
        self.assertNotIn(
            "next-instruction-label", self.detail(clipped, title='"Resolve the gate…"')
        )

    def test_a_title_that_merely_opens_a_longer_instruction_is_not_a_duplicate(self) -> None:
        # The reason the rule is not a plain prefix test. A generated title is a
        # summary of the OPENING prompt, so one that happens to be the first few
        # words of a genuinely newer instruction is the case this feature exists
        # for, and suppressing it would delete exactly the line that was added.
        longer = '{label: "asked", text: "Resolve the gate blocking the Windows job", at: 9400}'
        html = self.detail(longer, title='"Resolve the gate"')

        self.assertIn("asked, 10m:", html)
        self.assertIn("blocking the Windows job", html)

    def test_an_unusable_stamp_renders_the_label_without_an_age(self) -> None:
        # 0 is "unstamped", and the page must not turn that into "0s ago".
        html = self.detail('{label: "agent", text: "Real work", at: 0}')

        self.assertIn("agent:", html)
        self.assertNotIn("agent, 0s:", html)

    def test_untrusted_instruction_text_is_escaped_at_the_render_site(self) -> None:
        # Bounded at the collector and escaped again here. Neither layer is a
        # substitute for the other.
        html = self.detail('{label: "asked", text: "<img src=x onerror=alert>", at: 9400}')

        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)

    def test_a_codex_row_whose_title_is_its_prompt_shows_one_line(self) -> None:
        # Codex's line 1 IS the newest prompt, so the collector publishes no
        # "asked" line for it at all. This pins the page half of that decision.
        html = self.rows("null", title='"Reconcile the harness registry"')

        self.assertIn("Reconcile the harness registry", html)
        self.assertNotIn("next-instruction-label", html)


if __name__ == "__main__":
    unittest.main()
