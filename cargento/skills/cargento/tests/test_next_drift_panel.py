"""The Intent and drift panel, beside the session's activity (DRC-4680).

[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
item 1 names the panel "Intent and drift", with an "Intent" section and a "Drift" section, and
renames the action "Analyze drift". The owner's build decisions (DRC-4680, 2026-09-24) fix the
rest: one primary per stage (idle, analyzing, result, no reader); on a machine with no producer the
route's reason replaces the button; the harness limit replaces only the level and meter, and never
on Pi; the disclosure follows the button when idle and precedes "Allow and analyze" when
confirming; no meter, pill or "Not checked yet" before a level exists; no Stop session.

Every route here is the server's own, resolved by `reading_route` on a machine described by the
test, so the sentences asserted are the ones a reader would see.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import reading_route

from . import test_next_cockpit as cockpit_tests
from .next_harness import NextPageJsHarness, named_platform, storage_prelude

FIXTURE = cockpit_tests.NextCockpitCompositionTest.FIXTURE
ANNOTATED = cockpit_tests.CockpitHeldToTabTest.ANNOTATED

HARNESSES = ("codex", "pi", "claude", "antigravity")
LIMIT = "Cargento can't read work from this harness"
PRIMARY = re.compile(r"<button\b[^>]*next-action--primary[^>]*>([\s\S]*?)</button>")

# A stored reading with one departure, as `test_next_session_drift` stores it.
READING = """
__dashboard.sessions[0].annotation_at = 106;
__dashboard.sessions[0].annotation_reading_count = 1;
__dashboard.sessions[0].annotation_assessment = {revision_read:2, criteria:{
  goal:{result:"departure", detail:"It changed the board.", cites:["fo-a", "task-a"]}}};
"""

JOB = """
__dashboard.reading_jobs = {[`${__dashboard.sessions[0].harness}:focus-1`]: {id:"j1",
  phase:"waiting", started_at:100, phase_at:101, provider:"codex",
  steps:[{phase:"preparing", text:"Preparing what is sent"},
    {phase:"waiting", text:"Waiting for Codex"}, {phase:"checking", text:"Checking the reply"}]}};
"""

# Strings the design draws that no layer may show yet, or ever: the level and meter belong to
# DRC-4695 and DRC-4696, "Stop session" is not offered (DEC-16), and the old labels are renamed.
NEVER = (
    "Stop session",
    "Not checked yet",
    "Not enough recorded yet",
    "None or low",
    "None/Low",
    "Extreme",
    "Drift:",
    "Live monitor",
    "Check for drift",
    "Allow and check",
    "on Pi alone",
    "Reviews all",
)


def routes(
    *,
    installed: tuple[str, ...] = ("codex",),
    enabled: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """`reading_routes` for a machine with `installed` on PATH and, when given, only `enabled`
    providers' gates open; otherwise the shipped gates."""

    def gate(provider: str) -> bool:
        return provider in enabled if enabled is not None else original(provider)

    original = annotation_store.provider_enabled
    with named_platform(), mock.patch.object(annotation_store, "provider_enabled", gate):
        resolved = reading_route.resolve_all(
            HARNESSES,
            binary_resolver=lambda name: f"/usr/local/bin/{name}" if name in installed else None,
            environ={},
            root=Path("/nonexistent-cargento-root"),
        )
    return dict(resolved)


def visible_text(html: str) -> str:
    text = re.sub(r"<[^>]*>", " ", html)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text.replace("&#39;", "'"))


def aside_of(html: str) -> str:
    start = html.index("<aside")
    return html[start : html.index("</aside>", start)]


def drift_of(html: str) -> str:
    aside = aside_of(html)
    return aside[aside.index('id="next-session-drift-heading"') :]


@unittest.skipUnless(shutil.which("node"), "node not available")
class IntentAndDriftPanelTest(NextPageJsHarness):
    def page(
        self,
        harness: str = "claude",
        setup: str = "",
        *,
        routed: dict[str, Any] | None = None,
        after: str = "",
    ) -> str:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + ANNOTATED
            + f"__dashboard.reading_check = {json.dumps(annotation_store.ABSTENTION_CHECK)};\n"
            + f"__dashboard.reading_routes = {json.dumps(routes() if routed is None else routed)};\n"
            + f"__dashboard.sessions[0].harness = {json.dumps(harness)};\n"
            + setup
            + "await refreshNext();\nawait __settle();\n"
            + "navigateNext({view:'session', project:'cargento', harness:"
            + json.dumps(harness)
            + ", session:'focus-1'});\nawait __settle();\n"
            + after
            + "\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            storage_prelude({}) + FIXTURE,
        )
        assert isinstance(out, str)
        return out

    def confirming(self, harness: str = "claude") -> str:
        return self.page(
            harness,
            '__dashboard.reading = {consent:false, reason:"consent-required", used:0, limit:12};\n',
            after="""
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => init && init.method === "POST"
  ? {ok:true, json:async()=>({ok:true, produced:true})} : upstream(url, init);
await nextCockpitAskForReading(__dashboard.sessions[0], null);
renderNext();
await __settle();
""",
        )

    def stages(self) -> dict[str, str]:
        no_reader = routes(installed=())
        return {
            "idle": self.page(),
            "confirming": self.confirming(),
            "analyzing": self.page(setup=JOB),
            # On Codex, whose facts the reading cites, so its rows resolve.
            "result": self.page("codex", READING),
            "no reader": self.page(routed=no_reader),
        }

    def test_the_panel_is_an_aside_named_intent_and_drift_before_the_activity(self) -> None:
        html = self.page(setup=READING)

        aside = aside_of(html)
        self.assertIn('aria-label="Intent and drift"', html[html.index("<aside") :][:200])
        intent = aside.index(">Intent</h2>")
        drift = aside.index(">Drift</h2>")
        self.assertLess(intent, drift)
        self.assertIn("How far the session has moved from the goal", visible_text(drift_of(html)))
        # The reader's words are the Intent section's, under the design's labels.
        section = aside[intent:drift]
        self.assertIn(">Goal<", section)
        self.assertIn(">Expected outcome<", section)
        self.assertIn("data-next-cockpit-held-key", section)
        self.assertNotIn("WHAT YOU ASKED FOR", html)
        self.assertNotIn(">DRIFT<", html)
        # Aside first in markup order, so it leads at 375 and 320 with no reordering trick; the
        # activity follows it in its own column.
        main = html.index("data-next-session-activity")
        self.assertLess(html.index("<aside"), main)
        self.assertLess(html.index("<h1"), html.index("<aside"))
        activity = html[main:]
        self.assertIn(">Session activity</h2>", activity)
        order = [
            activity.index(mark)
            for mark in ("CURRENT ACTIVITY", "HOW IT LANDED", "OBSERVED RECORD")
        ]
        self.assertEqual(sorted(order), order)
        for elsewhere in ("CURRENT ACTIVITY", "HOW IT LANDED", "OBSERVED RECORD"):
            with self.subTest(elsewhere=elsewhere):
                self.assertNotIn(elsewhere, aside)

    def test_each_stage_has_at_most_one_primary_and_says_its_own_words(self) -> None:
        stages = self.stages()
        expected = {
            "idle": "Analyze drift",
            "confirming": "Allow and analyze",
            "analyzing": None,
            "result": "Analyze drift",
            "no reader": None,
        }
        for name, html in stages.items():
            with self.subTest(stage=name):
                primaries = PRIMARY.findall(html)
                want = expected[name]
                self.assertEqual(0 if want is None else 1, len(primaries), primaries)
                if want is not None:
                    self.assertEqual(want, visible_text(primaries[0]).strip())
                    self.assertIn(want, visible_text(drift_of(html)))
        # The running box stands where the button was, and Cancel is a plain control.
        analyzing = drift_of(stages["analyzing"])
        self.assertIn("Analyzing drift", analyzing)
        self.assertNotIn('data-next-cockpit-action="reading-ask"', analyzing)
        cancel = re.search(
            r'<button\b[^>]*data-next-cockpit-action="reading-cancel"[^>]*>', analyzing
        )
        assert cancel is not None
        self.assertIn('class="next-action"', cancel.group(0))
        # The stored reading renders in the Drift section.
        result = drift_of(stages["result"])
        self.assertIn("<h2>READING</h2>", result)
        self.assertIn("It changed the board.", result)

    def test_no_stage_draws_a_level_a_pill_a_stop_control_or_an_old_label(self) -> None:
        for name, html in self.stages().items():
            with self.subTest(stage=name):
                text = visible_text(html)
                for never in NEVER:
                    self.assertNotIn(never, text)
                self.assertNotIn("data-next-drift-level", html)
                self.assertNotIn("data-next-drift-pill", html)

    def test_the_disclosure_follows_analyze_when_idle_and_precedes_allow_when_confirming(
        self,
    ) -> None:
        route = routes()["claude"]
        disclosure = route["disclosure"][:60]

        idle = drift_of(self.page())
        button = re.search(r'<button\b[^>]*data-next-cockpit-action="reading-ask"[^>]*>', idle)
        assert button is not None
        self.assertLess(button.start(), idle.index(disclosure))
        described = re.search(r'aria-describedby="([^"]+)"', button.group(0))
        assert described is not None
        bound = re.search(rf'<p\b[^>]*id="{described.group(1)}"[^>]*>([^<]*)</p>', idle)
        assert bound is not None
        self.assertIn(disclosure, bound.group(1))

        confirming = drift_of(self.confirming())
        self.assertIn('data-next-cockpit-action="reading-allow"', confirming)
        self.assertLess(confirming.index(disclosure), confirming.index("Allow and analyze"))

    def test_each_refusal_reason_stands_where_analyze_would_be(self) -> None:
        machines = {
            reading_route.REASON_NOT_INSTALLED: routes(installed=(), enabled=("claude", "codex")),
            reading_route.REASON_MISSING_OTHER_UNQUALIFIED: routes(
                installed=(), enabled=("claude",)
            ),
            reading_route.REASON_UNQUALIFIED_OTHER_MISSING: routes(
                installed=(), enabled=("codex",)
            ),
            reading_route.REASON_UNQUALIFIED: routes(installed=("codex", "claude"), enabled=()),
        }
        seen = set()
        for token, routed in machines.items():
            route = routed["claude"]
            with self.subTest(reason=token):
                self.assertEqual(token, route["reason"])
                self.assertEqual("", route["provider"])
                html = self.page(routed=routed)
                drift = drift_of(html)
                seen.add(route["note"])
                self.assertEqual(1, visible_text(html).count(route["note"]))
                self.assertIn(route["note"], visible_text(drift))
                self.assertNotIn('data-next-cockpit-action="reading-ask"', html)
                self.assertNotIn('data-next-cockpit-action="reading-allow"', html)
                self.assertNotIn("A reading sends", html)
                self.assertEqual([], PRIMARY.findall(html))
        self.assertEqual(4, len(seen))
        # And a route the server has not published: the same slot, its own sentence.
        html = self.page(routed={})
        drift = drift_of(html)
        self.assertIn("Who would read this session is not published", visible_text(drift))
        self.assertNotIn('data-next-cockpit-action="reading-ask"', html)
        self.assertEqual([], PRIMARY.findall(html))

    def test_another_harness_states_the_limit_where_the_level_would_be_and_keeps_analyze(
        self,
    ) -> None:
        for harness in ("codex", "antigravity"):
            with self.subTest(harness=harness):
                drift = drift_of(self.page(harness))
                text = visible_text(drift)
                self.assertEqual(1, text.count(LIMIT))
                # In the level's place: after the heading, before the control.
                self.assertLess(
                    drift.index(LIMIT.replace("'", "&#39;")), drift.index("reading-ask")
                )
                primaries = PRIMARY.findall(drift)
                self.assertEqual(["Analyze drift"], [visible_text(p).strip() for p in primaries])

    def test_claude_code_and_pi_say_nothing_false_about_reading_work(self) -> None:
        for harness in ("claude", "pi"):
            with self.subTest(harness=harness):
                html = self.page(harness)
                self.assertNotIn(LIMIT, visible_text(html))
                self.assertIn("Analyze drift", visible_text(drift_of(html)))
        pi = visible_text(self.page("pi"))
        self.assertIn("Pi publishes demonstrated work results, and they are read here.", pi)

    def test_the_retired_pi_sentence_is_gone_from_every_harness(self) -> None:
        for harness in ("codex", "antigravity"):
            with self.subTest(harness=harness):
                text = visible_text(self.page(harness, READING))
                self.assertNotIn("on Pi alone", text)
                self.assertIn(
                    "publishes no demonstrated work results, so nothing above is an inspected "
                    "file, test or deliverable.",
                    text,
                )

    def test_the_header_names_the_state_in_cargentos_own_words(self) -> None:
        html = self.page()
        start = html.index('<header class="next-session-detail-header"')
        header = html[start : html.index("</header>", start)]
        # Visible, not only announced: the word sits outside the visually hidden prefix.
        self.assertIn(
            '<span class="next-session-state"><span class="next-visually-hidden">State: </span>'
            "working</span>",
            header,
        )
        self.assertNotIn("Running", visible_text(html))

    def test_a_question_waiting_on_you_sits_above_both_columns(self) -> None:
        html = self.page(
            setup="""
__dashboard.ask = true;
__dashboard.sessions[0].state = "needs_input";
__dashboard.asks = [{id:"ask-1", harness:"claude", session_id:"focus-1", project:"cargento",
  question:"Ship it?", options:["Yes", "Not yet"]}];
"""
        )
        ask = html.index('data-next-session-section="ask"')
        self.assertLess(ask, html.index("<aside"))
        self.assertLess(ask, html.index("data-next-session-activity"))
        self.assertEqual([], PRIMARY.findall(html))
        self.assertIn("Analyze drift", visible_text(drift_of(html)))

    def test_with_annotations_off_the_panel_keeps_an_inert_analyze_with_one_refusal(self) -> None:
        html = self.page(setup="delete __dashboard.annotate;\n")
        drift = drift_of(html)
        control = re.search(
            r'<button\b[^>]*data-next-cockpit-action="reading-ask"[^>]*>([\s\S]*?)</button>', drift
        )
        assert control is not None
        self.assertEqual("Analyze drift", visible_text(control.group(1)).strip())
        self.assertIn('aria-disabled="true"', control.group(0))
        self.assertEqual(1, html.count("Annotations are off for this run"))


if __name__ == "__main__":
    unittest.main()
