"""The press check, the job and the page agree on what an Allow covers (owner, 2026-10-02).

"Bind the allow to the destination": an Allow for the reader's words covers a
press only while the provider's destination is exactly the one the Allow's
disclosure named. Three places decide it, and each row of one table is put to
all three, after a restart, on a machine whose environment the row names:

- the press handler, over a socket (`http_api._reading_permission`);
- the job, at the reservation (`reading_policy.GuardedModel`);
- the page, from what the board publishes (`nextReadingNeedsAllow`).

A Pi session read by Claude Code, so no tool-output grant is involved and the
words' own binding is the only rule that can refuse.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any
from unittest import mock

from cargento_runtime import io as runtime_io
from cargento_runtime import reading_policy

from . import test_http_api, test_next_sessions
from .next_harness import NextPageJsHarness, named_machine

PRE = object()
# The daemon's environment under which `reading_route.destination` names each.
ENVIRON: dict[str, dict[str, str]] = {
    "Anthropic": {},
    "gw.corp.example": {"ANTHROPIC_BASE_URL": "https://gw.corp.example"},
    "Amazon Bedrock": {"CLAUDE_CODE_USE_BEDROCK": "1"},
    "": {"ANTHROPIC_UNIX_SOCKET": "/tmp/cargento-test.sock"},
}
# name, the Allow on record (None: none; PRE: a row from before the binding),
# whether it was then turned off, today's destination, and whether it covers.
ROWS: tuple[tuple[str, Any, bool, str, bool], ...] = (
    ("the same destination after a restart", "Anthropic", False, "Anthropic", True),
    ("Anthropic, then a base-URL host", "Anthropic", False, "gw.corp.example", False),
    ("Anthropic, then Bedrock", "Anthropic", False, "Amazon Bedrock", False),
    ("unnamed, still unnamed", "", False, "", True),
    ("named, then unnamed", "Anthropic", False, "", False),
    ("unnamed, then named", "", False, "Anthropic", False),
    ("a row from before the binding", PRE, False, "Anthropic", False),
    ("no Allow at all", None, False, "Anthropic", False),
    ("turned off, then moved", "Anthropic", True, "gw.corp.example", False),
    ("turned off, unchanged", "Anthropic", True, "Anthropic", False),
)


class ThePressTheJobAndThePageAgree(NextPageJsHarness):
    FIXTURE = test_next_sessions.NextSessionsBehaviorTest.FIXTURE

    def setUp(self) -> None:
        super().setUp()
        # The socket helpers `ReadingRouteTest` already proved can observe a
        # call, on an instance of their own: inheriting them would run that
        # whole suite again here, and binding the class at module level would
        # make the loader do the same.
        self.route = test_http_api.ReadingRouteTest("run")
        self.addCleanup(self.route.doCleanups)

    def _on(self, where: str) -> tuple[contextlib.ExitStack, list[str]]:
        """Claude Code on PATH, no Codex, and an environment naming `where`."""
        stack = contextlib.ExitStack()
        stack.enter_context(self.route._open_claude())
        calls = stack.enter_context(self.route._counting_model(("claude",)))
        # After `_counting_model`, so this machine's destination is the one read.
        stack.enter_context(named_machine(ENVIRON[where]))
        return stack, calls

    def _give(self, config: Any, state: Any, given: Any, declined: bool) -> None:
        if given is PRE:
            reading_policy.status(config, now=1_700_000_100.0)
            assert runtime_io.sqlite_module is not None
            db = runtime_io.sqlite_module.connect(reading_policy.store_path(config))
            db.execute("INSERT OR REPLACE INTO provider_permission VALUES ('claude', 1)")
            db.commit()
            db.close()
        elif given is not None:
            stack, calls = self._on(given)
            with stack, self.route._serving(self.route._app(config, state)) as port:
                status, body = self.route._post(
                    port, self.route._press(provider="claude", allow=True, words_destination=given)
                )
            self.assertEqual(202, status, body)
            self.assertEqual(1, len(calls))
        if declined:
            stack, _calls = self._on("Anthropic")
            with stack, self.route._serving(self.route._app(config, state)) as port:
                status, _ = self.route._post(
                    port, {"consent": "off", "press": True, "observer_model": 1}
                )
            self.assertEqual(200, status)

    def _today(self, config: Any, state: Any, today: str) -> dict[str, Any]:
        """A new application on the same home, as a restarted daemon is."""
        stack, calls = self._on(today)
        with stack:
            # Nothing a collection before the restart memoised survives it.
            state.snapshot.clear()
            application = self.route._app(config, state)
            _revision, body = application.collect_json(show_all=False)
            board = json.loads(body)
            route = board["reading_routes"]["pi"]
            with self.route._serving(application) as port:
                status, _ = self.route._post(port, self.route._press(provider="claude"))
            pressed = len(calls)
            model = mock.Mock(return_value=("{}", "ok"))
            guarded = reading_policy.GuardedModel(
                config,
                model,
                lambda: 1_700_000_100.0,
                provider="claude",
                destination=route["words_destination"],
            )
            # Refused or run: the count on the model says which.
            with contextlib.suppress(reading_policy.RefusedError):
                guarded("prompt", output_cap_bytes=100)
        return {
            "board": board,
            "route": route,
            "press": status,
            "pressed": pressed,
            "job": model.call_count,
        }

    def _page(self, board: dict[str, Any], route: dict[str, Any]) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "nextData.annotate = true;\n"
            f"nextData.reading_check = {json.dumps(board['reading_check'])};\n"
            f"nextData.reading_routes = {json.dumps({'pi': route})};\n"
            f"nextData.reading = {json.dumps(board['reading'])};\n"
            "const session = nextData.sessions[0];\n"
            'session.harness = "pi";\n'
            'session.annotation_goal = "Ship the parser";\n'
            "session.annotation_revision = 1;\n"
            "const posts = [];\n"
            "__fetchImpl = async (url, init) => {\n"
            "  if(init && init.method === 'POST'){ posts.push(JSON.parse(init.body));"
            " return {ok:true,status:200,json:async()=>({ok:true,produced:true})}; }\n"
            "  return {ok:true,json:async()=>nextData};\n"
            "};\n"
            "const route = nextReadingRoute(session);\n"
            "const needs = nextReadingNeedsAllow(route);\n"
            "await nextCockpitAskForReading(session, null);\n"
            "const asked = posts.length;\n"
            "const html = nextCockpitReadingControl(session, nextCockpitAnnotation(session), null);\n"
            "if(needs) await nextCockpitAskForReading(session, null, true);\n"
            "console.log(JSON.stringify({needs, asked, html, posts}));\n",
            self.FIXTURE,
        )

    def test_every_row_is_answered_the_same_by_the_press_the_job_and_the_page(self) -> None:
        for name, given, declined, today, covered in ROWS:
            with self.subTest(row=name):
                config, state = self.route._runtime()
                self._give(config, state, given, declined)
                seen = self._today(config, state, today)
                self.assertEqual(today, seen["route"]["words_destination"])
                published = seen["board"]["reading"]
                self.assertIs(covered, published["providers"]["claude"])
                # The press check.
                self.assertEqual(202 if covered else 403, seen["press"])
                self.assertEqual(1 if covered else 0, seen["pressed"], "sent before an Allow")
                # The job.
                self.assertEqual(1 if covered else 0, seen["job"])
                # The page.
                page = self._page(seen["board"], seen["route"])
                assert isinstance(page, dict)
                self.assertIs(not covered, page["needs"])
                self.assertEqual(1 if covered else 0, page["asked"], "the page sent first")
                moved = given is not None and not declined and not covered
                self.assertEqual(
                    1 if moved else 0, page["html"].count(reading_policy.DESTINATION_CHANGED)
                )
                if not covered:
                    # The step names the receiver, and the line comes before Allow.
                    self.assertIn("Allow and analyze", page["html"])
                    if moved:
                        self.assertLess(
                            page["html"].index(reading_policy.DESTINATION_CHANGED),
                            page["html"].index("Allow and analyze"),
                        )
                    self.assertEqual(1, len(page["posts"]))
                    self.assertIs(True, page["posts"][0]["allow"])
                    self.assertEqual(today, page["posts"][0]["words_destination"])
