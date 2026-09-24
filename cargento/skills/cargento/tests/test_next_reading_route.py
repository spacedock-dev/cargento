"""The page names who reads THIS session before the press (DRC-4650).

Every route here is the server's own: `reading_route.resolve` builds it and the
fixture publishes it, so the sentence asserted is the sentence a reader would
see rather than one invented for the test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import reading_route

from . import test_next_sessions
from .next_harness import NextPageJsHarness, named_platform


def _route(
    harness: str,
    installed: set[str],
    *,
    claude_open: bool = False,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The server's route on a machine with no endpoint setting unless one is
    given, so this machine's own environment never decides a page test."""
    check = (
        annotation_store.ABSTENTION_CHECK_PASSED
        if claude_open
        else annotation_store.ABSTENTION_CHECK_NOT_RUN
    )
    with mock.patch.object(annotation_store, "CLAUDE_ABSTENTION_CHECK", check), named_platform():
        return dict(
            reading_route.resolve(
                harness,
                binary_resolver=lambda name: (
                    f"/usr/local/bin/{name}" if name in installed else None
                ),
                environ=environ or {},
                root=Path("/nonexistent-cargento-root"),
            )
        )


GATED_CLAUDE = _route("claude", {"codex", "claude"})
NO_READER = _route("claude", {"claude"})
OPEN_CLAUDE = _route("claude", {"codex", "claude"}, claude_open=True)
CODEX = _route("codex", {"codex", "claude"})
UNNAMED_CLAUDE = _route("claude", {"codex"}, environ={"OPENAI_BASE_URL": "https://gw.example"})


class ReadingRoutePageTest(NextPageJsHarness):
    FIXTURE = test_next_sessions.NextSessionsBehaviorTest.FIXTURE

    def render(self, routes: dict[str, Any], checks: str, reading: str = "") -> Any:
        prelude = (
            "nextData.annotate = true;\n"
            f"nextData.reading_check = {json.dumps(annotation_store.ABSTENTION_CHECK)};\n"
            f"nextData.reading_routes = {json.dumps(routes)};\n"
            + (
                reading
                or 'nextData.reading = {consent:true,reason:"",used:0,limit:12,'
                'providers:{codex:true,claude:false},tool_output:{codex:["OpenAI"]}};\n'
            )
            + "const session = nextData.sessions[0];\n"
            'session.harness = "claude";\n'
            'session.annotation_goal = "Ship the parser";\n'
            "session.annotation_revision = 1;\n"
            "const posts = [];\n"
            "const control = () => nextCockpitReadingControl(session,"
            " nextCockpitAnnotation(session), null);\n"
        )
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + prelude + checks, self.FIXTURE
        )

    def test_a_claude_code_row_on_this_build_names_codex_and_why_before_the_button(self) -> None:
        out = self.render({"claude": GATED_CLAUDE}, "console.log(JSON.stringify(control()));")
        assert isinstance(out, str)
        note = "Claude Code checks are built but not yet qualified, so Codex reads this session."
        self.assertIn(note, out)
        self.assertIn("OpenAI", out)
        self.assertNotIn("Anthropic", out)
        self.assertLess(out.index(note), out.index('data-next-cockpit-action="reading-ask"'))
        self.assertIn("next-action--primary", out)
        self.assertNotIn('aria-disabled="true"', out)

    def test_with_no_reader_the_page_says_why_and_offers_no_check_and_no_allow(self) -> None:
        out = self.render(
            {"claude": NO_READER},
            """
__fetchImpl = async (url, init) => { if(init && init.method === "POST") posts.push(init); return {ok:true,json:async()=>nextData}; };
const before = control();
await nextCockpitAskForReading(session, null);
await nextCockpitAskForReading(session, null, true);
console.log(JSON.stringify({before, after: control(), posts: posts.length}));
""",
        )
        assert isinstance(out, dict)
        for html in (out["before"], out["after"]):
            self.assertEqual(1, html.count(NO_READER["note"]))
            self.assertNotIn("next-action--primary", html)
            self.assertIn('aria-disabled="true"', html)
            self.assertNotIn("Allow and check", html)
            self.assertNotIn("A reading sends", html)
        self.assertEqual(0, out["posts"])

    def test_a_press_tells_the_server_which_provider_the_page_named(self) -> None:
        out = self.render(
            {"claude": GATED_CLAUDE},
            """
__fetchImpl = async (url, init) => {
  if(init && init.method === "POST"){ posts.push(JSON.parse(init.body)); return {ok:true,status:200,json:async()=>({ok:true,produced:true})}; }
  return {ok:true,json:async()=>nextData};
};
await nextCockpitAskForReading(session, null);
console.log(JSON.stringify(posts));
""",
        )
        assert isinstance(out, list)
        self.assertEqual(1, len(out))
        self.assertEqual("codex", out[0]["provider"])

    def test_a_codex_answer_does_not_skip_the_claude_code_allow(self) -> None:
        out = self.render(
            {"claude": OPEN_CLAUDE},
            """
__fetchImpl = async (url, init) => {
  if(init && init.method === "POST"){ posts.push(JSON.parse(init.body)); return {ok:true,status:200,json:async()=>({ok:true,produced:true})}; }
  return {ok:true,json:async()=>nextData};
};
await nextCockpitAskForReading(session, null);
const asked = {posts: posts.length, html: control()};
await nextCockpitAskForReading(session, null, true);
console.log(JSON.stringify({asked, posts}));
""",
        )
        assert isinstance(out, dict)
        self.assertEqual(0, out["asked"]["posts"], "a Codex answer sent words to Anthropic")
        html = out["asked"]["html"]
        self.assertIn("Allow and check", html)
        self.assertIn("Anthropic", html)
        self.assertLess(html.index("Anthropic"), html.index("Allow and check"))
        self.assertEqual(1, len(out["posts"]))
        self.assertEqual("claude", out["posts"][0]["provider"])
        self.assertIs(True, out["posts"][0]["allow"])

    def test_a_reader_whose_route_changed_is_told_once_and_must_press_and_allow_again(
        self,
    ) -> None:
        out = self.render(
            {"claude": GATED_CLAUDE},
            f"""
const fresh = {json.dumps(OPEN_CLAUDE)};
let gets = 0;
__fetchImpl = async (url, init) => {{
  if(init && init.method === "POST"){{
    posts.push(JSON.parse(init.body));
    return {{ok:false,status:409,json:async()=>({{ok:false,produced:false,reason:"provider-changed",route:fresh}})}};
  }}
  gets += 1;
  const next = JSON.parse(JSON.stringify(nextData));
  next.reading_routes = {{claude: fresh}};
  return {{ok:true,json:async()=>next}};
}};
await nextCockpitAskForReading(session, null);
const changed = control();
const firstPosts = posts.length;
await nextCockpitAskForReading(session, null);
console.log(JSON.stringify({{changed, firstPosts, posts: posts.length, gets, again: control()}}));
""",
        )
        assert isinstance(out, dict)
        self.assertEqual(1, out["firstPosts"])
        self.assertGreaterEqual(out["gets"], 1, "the page did not refresh who reads the session")
        sentence = "The reader for this session changed since this page was drawn"
        self.assertEqual(1, out["changed"].count(sentence))
        self.assertIn("Anthropic", out["changed"])
        # The next press asks for Claude Code's own Allow and sends nothing.
        self.assertEqual(1, out["posts"])
        self.assertIn("Allow and check", out["again"])

    def test_two_rows_on_two_harnesses_each_name_their_own_receiver(self) -> None:
        out = self.render(
            {"claude": OPEN_CLAUDE, "codex": CODEX},
            """
const other = {...session, harness: "codex", sid: "other-1"};
console.log(JSON.stringify({claude: control(), codex: nextCockpitReadingControl(other, nextCockpitAnnotation(session), null)}));
""",
            reading='nextData.reading = {consent:true,reason:"",used:0,limit:12,'
            "providers:{codex:true,claude:true}};\n",
        )
        assert isinstance(out, dict)
        self.assertIn("Anthropic", out["claude"])
        self.assertNotIn("OpenAI", out["claude"])
        self.assertIn("OpenAI", out["codex"])
        self.assertNotIn("Anthropic", out["codex"])

    def test_with_no_route_published_nothing_is_offered_that_names_no_receiver(self) -> None:
        out = self.render(
            {},
            """
__fetchImpl = async (url, init) => { if(init && init.method === "POST") posts.push(init); return {ok:true,json:async()=>nextData}; };
await nextCockpitAskForReading(session, null);
console.log(JSON.stringify({html: control(), posts: posts.length}));
""",
        )
        assert isinstance(out, dict)
        self.assertEqual(0, out["posts"])
        self.assertIn('aria-disabled="true"', out["html"])
        self.assertNotIn("A reading sends", out["html"])
        self.assertIn("Who would read this session is not published", out["html"])

    def test_turn_off_shows_while_any_provider_is_allowed(self) -> None:
        out = self.render(
            {"claude": GATED_CLAUDE},
            "console.log(JSON.stringify(control()));",
            reading='nextData.reading = {consent:false,reason:"consent-required",used:0,limit:12,'
            "providers:{codex:false,claude:true}};\n",
        )
        assert isinstance(out, str)
        self.assertIn("Turn off readings", out)

    def test_with_no_reader_and_no_goal_the_page_does_not_send_them_to_type_one(self) -> None:
        """Saving a goal would not let a check run here, so the machine's
        reason wins over the step the page would otherwise name."""
        out = self.render(
            {"claude": NO_READER},
            """
session.annotation_goal = "";
session.annotation_line_1 = "";
session.annotation_revision = null;
session.instruction = null;
session.instructions = [];
session.first_prompt = "";
console.log(JSON.stringify({html: control(), candidate: nextPromptCandidate(session)}));
""",
        )
        assert isinstance(out, dict)
        self.assertIsNone(out["candidate"], "a prompt candidate would hide the nothing-typed arm")
        self.assertEqual(1, out["html"].count(NO_READER["note"]))
        self.assertNotIn("Save a goal above", out["html"])
        self.assertNotIn("next-action--primary", out["html"])

    def test_a_session_whose_harness_has_no_route_never_borrows_another_harness_route(
        self,
    ) -> None:
        out = self.render(
            {"codex": CODEX, "pi": _route("pi", {"codex"})},
            """
__fetchImpl = async (url, init) => { if(init && init.method === "POST") posts.push(init); return {ok:true,json:async()=>nextData}; };
await nextCockpitAskForReading(session, null);
console.log(JSON.stringify({html: control(), posts: posts.length}));
""",
        )
        assert isinstance(out, dict)
        self.assertEqual(0, out["posts"])
        self.assertNotIn("OpenAI", out["html"])
        self.assertNotIn("A reading sends", out["html"])
        self.assertIn("Who would read this session is not published", out["html"])


class ToolOutputOnThePageTest(ReadingRoutePageTest):
    """DEC-23 item 7 on the page: a Claude Code reader is told what the checks
    send and to whom before any press, an Allow given before tool output was
    named is asked again, and the press names the destination it disclosed."""

    WORDS_ONLY = (
        'nextData.reading = {consent:true,reason:"",used:0,limit:12,'
        "providers:{codex:true,claude:false},tool_output:{}};\n"
    )

    def _press_script(self, answer: str = "({ok:true,produced:true})", status: int = 200) -> str:
        return f"""
let gets = 0;
__fetchImpl = async (url, init) => {{
  if(init && init.method === "POST"){{ posts.push(JSON.parse(init.body)); return {{ok:{str(status == 200).lower()},status:{status},json:async()=>{answer}}}; }}
  gets += 1;
  return {{ok:true,json:async()=>nextData}};
}};
"""

    def test_a_reader_who_allowed_only_their_words_is_asked_again_naming_tool_output(
        self,
    ) -> None:
        out = self.render(
            {"claude": GATED_CLAUDE},
            self._press_script()
            + """
await nextCockpitAskForReading(session, null);
const asked = {posts: posts.length, html: control()};
await nextCockpitAskForReading(session, null, true);
console.log(JSON.stringify({asked, posts, policy: nextData.reading}));
""",
            reading=self.WORDS_ONLY,
        )
        assert isinstance(out, dict)
        self.assertEqual(0, out["asked"]["posts"], "tool output left before a fresh Allow")
        html = out["asked"]["html"]
        self.assertIn("Allow and check", html)
        self.assertLess(html.index("to Codex, which reaches OpenAI"), html.index("Allow and check"))
        self.assertEqual(1, len(out["posts"]))
        self.assertIs(True, out["posts"][0]["allow"])
        self.assertEqual("OpenAI", out["posts"][0]["tool_output"])
        self.assertEqual(["OpenAI"], out["policy"]["tool_output"]["codex"])

    def test_a_reader_whose_destination_cannot_be_named_presses_on_their_words_alone(
        self,
    ) -> None:
        out = self.render(
            {"claude": UNNAMED_CLAUDE},
            self._press_script()
            + """
await nextCockpitAskForReading(session, null);
console.log(JSON.stringify({posts, html: control()}));
""",
            reading=self.WORDS_ONLY,
        )
        assert isinstance(out, dict)
        self.assertEqual(1, len(out["posts"]))
        self.assertNotIn("tool_output", out["posts"][0])
        self.assertIn("Tool output is not sent", out["html"])

    def test_a_destination_that_moved_is_said_once_and_asks_again(self) -> None:
        moved = _route("claude", {"codex"}, environ={"OPENAI_BASE_URL": "https://gw.example"})
        out = self.render(
            {"claude": GATED_CLAUDE},
            self._press_script(
                '({ok:false,produced:false,reason:"destination-changed",route:'
                + json.dumps(moved)
                + "})",
                409,
            )
            + """
const before = gets;
await nextCockpitAskForReading(session, null, true);
console.log(JSON.stringify({posts, html: control(), refreshed: gets > before}));
""",
            reading=self.WORDS_ONLY,
        )
        assert isinstance(out, dict)
        self.assertEqual(1, len(out["posts"]))
        self.assertTrue(out["refreshed"], "the page did not read where the output goes now")
        self.assertEqual(
            1, out["html"].count("Where tool output would go changed since this page was drawn")
        )

    def test_a_server_asking_for_the_tool_output_allow_turns_the_button_into_allow(self) -> None:
        out = self.render(
            {"claude": GATED_CLAUDE},
            self._press_script(
                '({ok:false,produced:false,reading:{consent:false,reason:"tool-output-consent-required",'
                "used:0,limit:12,providers:{codex:true,claude:false},tool_output:{}}})",
                403,
            )
            + """
nextData.reading.tool_output = {codex: ["OpenAI"]};
await nextCockpitAskForReading(session, null);
console.log(JSON.stringify({posts: posts.length, html: control()}));
""",
            reading=self.WORDS_ONLY,
        )
        assert isinstance(out, dict)
        self.assertEqual(1, out["posts"])
        self.assertIn("Allow and check", out["html"])

    def test_the_limit_lines_say_what_is_sent_and_to_whom(self) -> None:
        for name, route in (("named", GATED_CLAUDE), ("unnamed", UNNAMED_CLAUDE)):
            with self.subTest(route=name):
                out = self.render(
                    {"claude": route},
                    "console.log(JSON.stringify({work: nextCockpitWorkEvidenceLimit('claude'),"
                    " reading: nextReadingOutputLimit('claude')}));",
                )
                assert isinstance(out, dict)
                self.assertIn(route["tool_output"], out["work"])
                if name == "named":
                    self.assertEqual("", out["reading"], "a sent check still demotes the output")
                else:
                    self.assertIn("cannot name where Codex would send them", out["reading"])
