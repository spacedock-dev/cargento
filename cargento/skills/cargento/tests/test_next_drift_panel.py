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


class PanelPage(NextPageJsHarness):
    """Renders the session page on a named harness; holds no tests of its own."""

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


@unittest.skipUnless(shutil.which("node"), "node not available")
class IntentAndDriftPanelTest(PanelPage):
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


STYLES = Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "styles.css"


def rule(selector: str) -> str:
    """The declarations of the first rule whose selector is exactly `selector`: the default
    viewport's, since the sheet puts every media query after the rules it narrows."""
    css = re.sub(r"/\*[\s\S]*?\*/", "", STYLES.read_text(encoding="utf-8"))
    found = [
        body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if sel.strip() == selector
    ]
    assert found, selector
    return str(found[0])


def children(markup: str) -> list[str]:
    """The top-level elements of `markup`, each with its whole subtree, void tags aside."""
    out: list[str] = []
    depth, start = 0, 0
    for tag in re.finditer(r"<(/?)([a-z0-9]+)\b[^>]*>", markup):
        if tag.group(2) in {"br", "img", "input", "hr", "meta", "link"}:
            continue
        if tag.group(1):
            depth -= 1
            if depth == 0:
                out.append(markup[start : tag.end()])
        else:
            if depth == 0:
                start = tag.start()
            depth += 1
    return out


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePanelKeepsAnalyzeOnTheFirstScreenTest(PanelPage):
    """The structure the 1440x900 fold rests on (DRC-4680 walk).

    Measured on a live board: with one element per header line the header took 205px and
    Analyze drift's bottom sat at 1022 (Claude Code) and 1085 (Codex). With the two-row header,
    the one-line revision stamp and a line's box sharing a row with its count, it sat at 820 and
    879. The pixels are the walk's to measure; these tests hold the structure that bought them.
    """

    def test_the_header_is_two_rows_state_name_and_id_then_the_measured_line_and_controls(
        self,
    ) -> None:
        html = self.page()
        start = html.index('<header class="next-session-detail-header">')
        header = html[start : html.index("</header>", start)]
        title = re.search(r'<div class="next-session-detail-title">([\s\S]*?)</div>', header)
        assert title is not None
        for part in ('class="next-session-state"', "<h1", 'class="next-session-identity"'):
            with self.subTest(part=part):
                self.assertIn(part, title.group(1))
        # The header's children are exactly the two rows, and the controls are in the second.
        rows = children(header[len('<header class="next-session-detail-header">') :])
        self.assertEqual(
            ['<div class="next-session-detail-title">', '<div class="next-session-detail-bar">'],
            [row[: row.index(">") + 1] for row in rows],
        )
        bar = rows[1]
        self.assertLess(
            bar.index('class="next-session-detail-meta"'),
            bar.index('class="next-session-controls"'),
        )
        self.assertIn("flex-direction:column", rule(".next-session-detail-header"))
        self.assertIn("flex-wrap:wrap", rule(".next-session-detail-title"))
        self.assertIn("flex-wrap:wrap", rule(".next-session-detail-bar"))

    def test_the_intent_section_is_heading_lede_one_stamp_line_then_the_fields(self) -> None:
        aside = aside_of(self.page())
        intent = aside[aside.index(">Intent</h2>") : aside.index(">Drift</h2>")]
        order = [
            intent.index(mark)
            for mark in (
                'class="next-cockpit-held-lede"',
                'class="next-cockpit-held-stamp"',
                'class="next-cockpit-held-fields"',
            )
        ]
        self.assertEqual(sorted(order), order)
        stamp = re.search(r'<div class="next-cockpit-held-stamp">([\s\S]*?)</div>', intent)
        assert stamp is not None
        self.assertIn('class="next-cockpit-held-revision"', stamp.group(1))
        self.assertIn("Each save is a revision.", stamp.group(1))
        self.assertIn("flex-wrap:wrap", rule(".next-cockpit-held-stamp"))
        # A line's box shares its row with the count and remove.
        self.assertIn(
            "grid-column:auto", rule(".next-cockpit-held-field .next-cockpit-held-line textarea")
        )

    def test_each_fields_count_and_controls_share_its_heading_row(self) -> None:
        """Owner-reworded fold (DRC-4680 review): under the box the goal's count, clear and save,
        and the outcome's add and save, each cost a second 44px row in the panel's column. In the
        heading row they also come before the box in reading order, as they are on screen."""
        html = self.page(setup=THREE_LINES)
        for kind, inside in (
            ("goal", ("data-next-cockpit-held-count", "held-clear", "held-save")),
            ("lines", ("held-line-add", "held-save")),
        ):
            with self.subTest(field=kind):
                start = html.index(f'data-next-cockpit-held-field="{kind}"')
                field = html[start:]
                heading = re.search(
                    r'<div class="next-cockpit-held-heading">((?:(?!<textarea|<ol)[\s\S])*?)</div>',
                    field,
                )
                assert heading is not None
                for part in inside:
                    self.assertIn(part, heading.group(1))
                box = field.index("<textarea")
                self.assertLess(field.index(heading.group(1)), box)

    def test_the_columns_put_the_panel_in_a_460px_track_that_is_neither_scrolled_nor_sticky(
        self,
    ) -> None:
        columns = rule(".next-session-columns")
        self.assertIn("grid-template-columns:minmax(0,1fr) 460px", columns)
        panel = rule(".next-session-panel")
        self.assertIn("grid-column:2", panel)
        for never in ("overflow", "sticky", "max-height"):
            with self.subTest(never=never):
                self.assertNotIn(never, panel)
                self.assertNotIn(never, columns)
        # And nothing between the header and the panel's first section but the ask block.
        html = self.page()
        between = html[
            html.index("</header>", html.index("next-session-detail-header")) + len("</header>") :
        ]
        between = between[: between.index("<aside")]
        self.assertEqual('<div class="next-session-columns">', between.strip())


def media_rule(query: str, selector: str) -> str:
    """The declarations of `selector` inside the `@media(<query>)` block."""
    css = re.sub(r"/\*[\s\S]*?\*/", "", STYLES.read_text(encoding="utf-8"))
    for block in re.finditer(
        r"@media\(" + re.escape(query) + r"\)\{((?:[^{}]*\{[^{}]*\})*)\s*\}", css
    ):
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block.group(1)):
            if sel.strip() == selector:
                return str(body)
    msg = f"{selector} not in @media({query})"
    raise AssertionError(msg)


def tracks(template: str) -> int:
    """How many tracks a `grid-template-columns` value names, parentheses kept whole."""
    depth, count, token = 0, 0, False
    for char in template.strip():
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == " " and depth == 0:
            token = False
        elif not token:
            token, count = True, count + 1
    return count


THREE_LINES = (
    "\n".join(
        f"__dashboard.sessions[0].annotation_line_{k} = {json.dumps(text)};\n"
        f"__dashboard.sessions[0].annotation_line_{k}_source = {json.dumps(source)};\n"
        f'__dashboard.sessions[0].annotation_line_{k}_source_id = "";'
        for k, text, source in (
            (1, "The toggle writes the choice to the settings store", "typed"),
            (2, "A reload opens in the saved mode", "typed"),
            (3, "Unit tests cover the read and the write", "entry"),
        )
    )
    + '\n__dashboard.sessions[0].annotation_lines_why = "";\n'
)

OFF_FAILS = """
const offUpstream = __fetchImpl;
__fetchImpl = async (url, init) => init && init.method === "POST"
  ? {ok:false, status:500, json:async()=>({ok:false})} : offUpstream(url, init);
await nextCockpitReadingOff();
await __settle();
"""
OFF_SENTENCE = "Could not confirm readings are off. Try turning them off again."


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePanelReviewRoundTest(PanelPage):
    """The two review lenses' findings on DRC-4680, each held by the test that failed first."""

    def test_every_saved_line_is_one_row_the_grid_has_a_track_per_item(self) -> None:
        """Owner, 2026-09-24: a saved line is one row of about one control height. The source
        tag was a fourth item in a three-track grid, which pushed remove onto a second row."""
        html = self.page(setup=THREE_LINES)
        lines = re.findall(r'<li class="next-cockpit-held-line"[^>]*>([\s\S]*?)</li>', html)
        self.assertEqual(3, len(lines))
        template = re.search(r"grid-template-columns:([^;}]+)", rule(".next-cockpit-held-line"))
        assert template is not None
        for line in lines:
            with self.subTest(line=visible_text(line)[:30]):
                items = children(line)
                self.assertIn('class="next-cockpit-held-source"', "".join(items))
                self.assertEqual(len(items), tracks(template.group(1)), items)

    def test_a_failed_turn_off_is_said_with_no_reader_and_while_analyzing(self) -> None:
        for name, kwargs in (
            ("no reader", {"routed": routes(installed=())}),
            ("analyzing", {"setup": JOB}),
        ):
            with self.subTest(state=name):
                html = self.page(**kwargs, after=OFF_FAILS)
                drift = drift_of(html)
                self.assertEqual(1, drift.count(OFF_SENTENCE))
                self.assertIn('role="status"', drift[: drift.index(OFF_SENTENCE)][-200:])

    def test_the_header_says_ended_once_the_session_ended_and_nothing_waits(self) -> None:
        for state in ("working", "idle"):
            with self.subTest(state=state):
                html = self.page(
                    setup=f'__dashboard.sessions[0].state = "{state}";\n'
                    "__dashboard.sessions[0].ended_at = 104;\n"
                )
                self.assertIn(
                    '<span class="next-session-state"><span class="next-visually-hidden">'
                    "State: </span>ended</span>",
                    html,
                )
                self.assertIn(f'data-next-session-state="{state}"', html)
        # A question still waiting keeps the state word: the session is not done with you.
        waiting = self.page(
            setup="""
__dashboard.ask = true;
__dashboard.sessions[0].state = "needs_input";
__dashboard.sessions[0].ended_at = 104;
__dashboard.asks = [{id:"ask-1", harness:"claude", session_id:"focus-1", project:"cargento",
  question:"Ship it?", options:["Yes", "Not yet"]}];
"""
        )
        self.assertIn("State: </span>needs input</span>", waiting)
        # Verifier V-2: after `session_ended` pops the overlay, the state is the collector's
        # own inference, `working` or `idle`, while an exact ask can still be open. A question
        # waiting on the reader says so, whatever the collector inferred.
        for state in ("working", "idle"):
            with self.subTest(ended_with_question=state):
                html = self.page(
                    setup=f"""
__dashboard.ask = true;
__dashboard.sessions[0].state = "{state}";
__dashboard.sessions[0].ended_at = 104;
__dashboard.asks = [{{id:"ask-1", harness:"claude", session_id:"focus-1", project:"cargento",
  question:"Ship it?", options:["Yes", "Not yet"]}}];
"""
                )
                self.assertIn('data-next-session-section="ask"', html)
                self.assertIn("State: </span>needs input</span>", html)

    def test_while_analyzing_the_box_comes_first_and_the_disclosure_once_after_it(self) -> None:
        disclosure = routes()["claude"]["disclosure"][:60]
        drift = drift_of(self.page(setup=JOB))
        self.assertEqual(1, drift.count(disclosure))
        self.assertLess(drift.index("data-next-analyzing"), drift.index(disclosure))

    def test_the_disclosure_renders_once_idle_and_confirming(self) -> None:
        disclosure = routes()["claude"]["disclosure"][:60]
        for name, html in (("idle", self.page()), ("confirming", self.confirming())):
            with self.subTest(stage=name):
                self.assertEqual(1, drift_of(html).count(disclosure))

    def test_the_no_reader_slot_keeps_turn_off_the_count_and_its_absence_kind(self) -> None:
        drift = drift_of(self.page(routed=routes(installed=())))
        self.assertIn('data-next-cockpit-action="reading-off"', drift)
        self.assertRegex(visible_text(drift), r"\d+ model requests? recorded for this session\.")
        unread = drift_of(self.page(routed={}))
        self.assertRegex(
            unread, r'<p [^>]*data-next-reading-no-reader[^>]*data-absence="not-observed"'
        )
        self.assertIn("so no analysis is offered", visible_text(unread))
        for token_note in (routes(installed=())["claude"]["note"],):
            self.assertIn("so no analysis can run for this session", token_note)

    def test_a_reader_leaving_under_a_focused_analyze_keeps_focus_on_its_reason(self) -> None:
        # The stub's element scan reads focusable spans only; a paragraph with `tabindex` joins it.
        stub = cockpit_tests.CockpitHeldToTabTest.FOCUS_DOM
        self.assertIn("(button|a|textarea|", stub)
        focus_dom = stub.replace(
            "(button|a|textarea|", "(button|a|textarea|p(?=[^>]*\\btabindex=)|", 1
        )
        gone = json.dumps(routes(installed=()))
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + focus_dom
            + ANNOTATED
            + f"__dashboard.reading_check = {json.dumps(annotation_store.ABSTENTION_CHECK)};\n"
            + f"__dashboard.reading_routes = {json.dumps(routes())};\n"
            + '__dashboard.sessions[0].harness = "claude";\n'
            + "await refreshNext();\nawait __settle();\n"
            + "navigateNext({view:'session', project:'cargento', harness:'claude', session:'focus-1'});\n"
            + "await __settle();\n"
            + f"""
const press = controls.find(c => c.dataset.nextCockpitAction === "reading-ask");
if(press) press.focus();
__dashboard.reading_routes = {gone};
renderNext();
await __settle();
const active = document.activeElement;
console.log(JSON.stringify({{found: Boolean(press), tag: active ? active.tagName : null,
  key: active && active.dataset ? active.dataset.nextFocus || "" : null,
  reason: __els.app.innerHTML.includes("data-next-reading-no-reader")}}));
""",
            storage_prelude({}) + FIXTURE,
        )
        assert isinstance(out, dict)
        self.assertTrue(out["found"])
        self.assertTrue(out["reason"])
        self.assertEqual("P", out["tag"])
        self.assertEqual("reading:claude:focus-1", out["key"])

    def test_the_stack_and_the_track_placement_hold(self) -> None:
        stacked = media_rule("max-width:1100px", ".next-session-columns")
        self.assertIn("grid-template-columns:minmax(0,1fr)", stacked)
        placed = media_rule("max-width:1100px", ".next-session-panel,.next-session-activity")
        self.assertIn("grid-column:1", placed)
        self.assertIn("grid-row:auto", placed)
        for selector, column in ((".next-session-panel", 2), (".next-session-activity", 1)):
            with self.subTest(selector=selector):
                body = rule(selector)
                self.assertIn(f"grid-column:{column}", body)
                self.assertIn("grid-row:1", body)
                self.assertIn("min-width:0", body)
        self.assertIn("flex:1 1 100%", rule(".next-cockpit-reading-ask>p"))
        self.assertIn("margin:0 0 0 auto", rule(".next-session-controls"))
        # Verifier V-5: the spacing the six-line fold's 7px margin rests on, and the two margins
        # that put a field's count and controls at the end of its heading row.
        self.assertIn("gap:var(--sp-2)", rule(".next-session-panel"))
        self.assertIn("padding:8px 16px 10px", rule(".next-session-drift-head"))
        self.assertIn("margin-left:auto", rule(".next-cockpit-held-tools"))
        self.assertIn(
            "margin-left:auto", rule(".next-cockpit-held-heading>.next-cockpit-held-count")
        )
        self.assertIn(
            "margin-left:0",
            rule(".next-cockpit-held-heading>.next-cockpit-held-count+.next-cockpit-held-tools"),
        )

    def test_a_box_at_rest_shows_whole_rows_and_grows_to_the_full_text_on_focus(self) -> None:
        """Owner, 2026-09-24: "one clean row, expand on focus". A saved line longer than its box
        showed a half-cut second row, and the goal box a half-cut third. At rest a line is one
        unwrapped row with its overflow faded, and the goal exactly two whole rows; on focus
        both grow to the full text. Pure CSS, so focus carries it through a redraw and no
        reader-state row is owed."""
        line_rest = rule(".next-session-panel .next-cockpit-held-line textarea:not(:focus)")
        for part in (
            "height:calc(var(--fs-body)*1.55 + 16px)",
            "white-space:nowrap",
            "overflow:hidden",
        ):
            with self.subTest(line_rest=part):
                self.assertIn(part, line_rest)
        self.assertRegex(line_rest, r"(?:text-overflow:ellipsis|mask-image:)")
        goal_rest = rule(".next-session-panel .next-cockpit-held-field>textarea:not(:focus)")
        for part in (
            "height:calc(var(--fs-body)*1.55*2 + 9px)",
            "padding-bottom:0",
            "overflow:hidden",
        ):
            with self.subTest(goal_rest=part):
                self.assertIn(part, goal_rest)
        for selector in (
            ".next-session-panel .next-cockpit-held-line textarea:focus",
            ".next-session-panel .next-cockpit-held-field>textarea:focus",
        ):
            with self.subTest(focus=selector):
                # Focus takes the at-rest height, wrap and clip away (they are `:not(:focus)`)
                # and sizes the box to its text; it declares no overflow of its own, so it adds
                # no scroll container.
                lifted = rule(selector)
                self.assertIn("field-sizing:content", lifted)
                self.assertNotIn("overflow", lifted)
                self.assertNotIn("height:calc", lifted)
        self.assertIn(
            "white-space:pre-wrap",
            rule(".next-session-panel .next-cockpit-held-line textarea:focus"),
        )
        self.assertIn("resize:none", rule(".next-session-panel .next-cockpit-held-field textarea"))
        # The selectors reach the markup: the goal box is a direct child of its field, each line
        # box is inside its line, and the whole text stays the box's value.
        html = self.page(setup=THREE_LINES)
        self.assertRegex(
            html, r'data-next-cockpit-held-field="goal">(?:(?!</div>)[\s\S])*</div><textarea '
        )
        self.assertIn(">The toggle writes the choice to the settings store</textarea>", html)
        self.assertIn('data-next-cockpit-held-line-count="0">50/240<', html)

    def test_a_box_without_field_sizing_still_opens_several_rows_on_focus(self) -> None:
        """Verifier V-3: the focus expansion rests on `field-sizing:content`, which not every
        engine ships. Where it is missing, a focused box takes a fixed height of several rows
        and scrolls inside it; the at-rest rules are the same either way."""
        css = re.sub(r"/\*[\s\S]*?\*/", "", STYLES.read_text(encoding="utf-8"))
        block = re.search(
            r"@supports not \(field-sizing: ?content\)\{((?:[^{}]*\{[^{}]*\})*)\s*\}", css
        )
        assert block is not None, "no field-sizing fallback"
        rules = {
            sel.strip(): body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block.group(1))
        }
        self.assertIn(
            "height:calc(var(--fs-body)*1.55*4 + 16px)",
            rules[".next-session-panel .next-cockpit-held-line textarea:focus"],
        )
        self.assertIn(
            "height:calc(var(--fs-body)*1.55*6 + 16px)",
            rules[".next-session-panel .next-cockpit-held-field>textarea:focus"],
        )
        for body in rules.values():
            self.assertNotIn("overflow", body)

    def test_the_goals_heading_row_keeps_its_controls_on_the_top_line(self) -> None:
        """Verifier V-4: centred, the count, clear and save floated beside an open "Use a
        prompt" menu and read as its controls. Every item is one control tall and the row is
        top-aligned, so they stay on the heading's first line whether the menu is open or not."""
        self.assertIn(
            "align-items:flex-start", rule(".next-session-panel .next-cockpit-held-heading")
        )
        for selector in (
            ".next-session-panel .next-cockpit-held-heading>.next-cockpit-held-label",
            ".next-session-panel .next-cockpit-held-heading>.next-cockpit-held-count",
        ):
            with self.subTest(item=selector):
                self.assertIn("min-height:44px", rule(selector))
                self.assertIn("align-items:center", rule(selector))

    def test_on_a_narrow_screen_a_lines_box_takes_the_full_row(self) -> None:
        """At 320 the box shared its row with the count, source and remove and showed about 12
        characters at rest. At the sheet's narrow step the box takes the whole first row and the
        three follow on a second, in the same order; the wide rule is untouched, so the fold at
        1440 and 1100 does not move."""
        grid = media_rule("max-width:760px", ".next-session-panel .next-cockpit-held-line")
        template = re.search(r"grid-template-columns:([^;}]+)", grid)
        assert template is not None
        self.assertEqual(3, tracks(template.group(1)))
        box = media_rule(
            "max-width:760px",
            ".next-session-panel .next-cockpit-held-field .next-cockpit-held-line textarea",
        )
        self.assertIn("grid-column:1/-1", box)
        # Remove sits beside the source in the second row's last track, not centred in it.
        self.assertIn(
            "justify-self:start",
            media_rule("max-width:760px", ".next-session-panel .next-cockpit-held-line>button"),
        )
        # Wide: still one row, a track per item.
        wide = re.search(r"grid-template-columns:([^;}]+)", rule(".next-cockpit-held-line"))
        assert wide is not None
        self.assertEqual(4, tracks(wide.group(1)))

    def test_the_sentences_in_the_controls_slot_say_analyze_not_check(self) -> None:
        """Review C-6: "check" also names a tool check on this page, so the sentences that stand
        in for the renamed control, or refuse it, use its verb."""
        web = STYLES.parent
        cockpit = (web / "next-cockpit.js").read_text(encoding="utf-8")
        route = (web.parent / "reading_route.py").read_text(encoding="utf-8")
        for stale in ("so no check is offered", "before checking"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, cockpit)
        self.assertNotIn("so no check can run", route)
        self.assertIn("so no analysis can run for this session.", route)

    def test_current_activity_leads_the_activity_column_ahead_of_the_workers(self) -> None:
        html = self.page(
            setup="""
__dashboard.sessions[0].subagents = [{name:"worker-a", state:"ended", model:"m",
  started_at:80, completed_at:90}];
"""
        )
        column = html[html.index("data-next-session-activity") :]
        self.assertLess(column.index(">Session activity</h2>"), column.index("CURRENT ACTIVITY"))
        self.assertLess(
            column.index("CURRENT ACTIVITY"), column.index("data-next-session-subagents")
        )


if __name__ == "__main__":
    unittest.main()
