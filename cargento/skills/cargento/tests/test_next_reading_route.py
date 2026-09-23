"""The page names who reads THIS session before the press (DRC-4650).

Every route here is the server's own: `reading_route.resolve` builds it and the
fixture publishes it, so the sentence asserted is the sentence a reader would
see rather than one invented for the test.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import reading_route

from . import test_next_sessions
from .next_harness import NextPageJsHarness


def _route(harness: str, installed: set[str], *, claude_open: bool = False) -> dict[str, Any]:
    check = (
        annotation_store.ABSTENTION_CHECK_PASSED
        if claude_open
        else annotation_store.ABSTENTION_CHECK_NOT_RUN
    )
    with mock.patch.object(annotation_store, "CLAUDE_ABSTENTION_CHECK", check):
        return dict(
            reading_route.resolve(
                harness,
                binary_resolver=lambda name: (
                    f"/usr/local/bin/{name}" if name in installed else None
                ),
            )
        )


GATED_CLAUDE = _route("claude", {"codex", "claude"})
NO_READER = _route("claude", {"claude"})
OPEN_CLAUDE = _route("claude", {"codex", "claude"}, claude_open=True)
CODEX = _route("codex", {"codex", "claude"})


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
                "providers:{codex:true,claude:false}};\n"
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
session.annotation_output = "";
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
