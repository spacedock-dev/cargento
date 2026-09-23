"""The session page leads with drift (DRC-4639) and puts the way back beside it (DRC-4642).

[DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)
merges the cockpit's Held to tab into the session view: one DRIFT block, first after the page's
identity, holding the reader's words, the agent's direction, the later-direction question, the
reading and every departure on record. It has at most one primary: "Check for drift", or, while
the session waits on the reader, the raise when one is offered and nothing otherwise.

The fixtures are the cockpit composition board's, read through the module rather than imported by
name, so the loader does not collect that class a second time here.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from typing import Any

from cargento_runtime import annotations as annotation_store
from cargento_runtime import reading

from . import test_next_cockpit as cockpit_tests
from .next_harness import NextPageJsHarness, storage_prelude

FIXTURE = cockpit_tests.NextCockpitCompositionTest.FIXTURE
FOCUS_DOM = cockpit_tests.CockpitHeldToTabTest.FOCUS_DOM
ANNOTATED = cockpit_tests.CockpitHeldToTabTest.ANNOTATED

SESSION_ROUTE = (
    'navigateNext({view:"session", project:"cargento", harness:"codex", session:"focus-1"});'
)

# A stored reading with one departure, against words saved after every observed direction so no
# later direction demotes it. Each result cites a fact the fixture's project context publishes.
READING = """
__dashboard.sessions[0].annotation_at = 106;
__dashboard.sessions[0].annotation_reading_count = 1;
__dashboard.sessions[0].annotation_assessment = {revision_read:2, criteria:{
  goal:{result:"departure", detail:"It changed the board.", cites:["fo-a", "task-a"]}}};
"""

# The same reading, finding the goal consistent instead.
CONSISTENT = """
__dashboard.sessions[0].annotation_at = 106;
__dashboard.sessions[0].annotation_reading_count = 1;
__dashboard.sessions[0].annotation_assessment = {revision_read:2, criteria:{
  goal:{result:"consistent with the evidence read", detail:"Screens were captured.",
    cites:["fo-a", "task-a"]}}};
"""

# One raise from the unasked lane, standing on record.
UNASKED = """
__dashboard.unasked = true;
__dashboard.sessions[0].departure_checked = true;
__dashboard.sessions[0].departures = [{
  constraint: "TYPED GOAL", clause: "do not change the board while capturing",
  reading: "Two turns edited the running board.", revision: 2,
  at: __dashboard.generated - 600, cutoff: __dashboard.generated - 600,
  cutoff_text: "Read 4 of 4 entries in the observed record.",
  evidence: "turn transcript"}];
"""

# Anything a reader could take as "this session has no drift". DEC-20 item 3: the word may name
# the block and the control, never a result.
DRIFT_ABSENCE = re.compile(
    r"\b(?:no|not|without|zero|free of)\s+(?:any\s+)?drift\b|\bdrift[- ]free\b|"
    r"\bdrift\s*:\s*(?:none|no)\b|\bhas(?:n't| not)\s+drifted\b|\bdid(?:n't| not)\s+drift\b",
    re.IGNORECASE,
)


def visible_text(html: str) -> str:
    """The characters a reader sees: tags and attribute values dropped, entities decoded."""
    text = re.sub(r"<[^>]*>", " ", html)
    for entity, char in (
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
    ):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheSessionPageLeadsWithDriftTest(NextPageJsHarness):
    def run_fixture(self, checks: str) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n" + checks,
            storage_prelude({}) + FIXTURE,
        )

    def page(self, setup: str = "", after: str = "") -> str:
        out = self.run_fixture(
            ANNOTATED
            + setup
            + SESSION_ROUTE
            + "\nawait __settle();\nawait __settle();\n"
            + after
            + "\nconsole.log(JSON.stringify(__els.app.innerHTML));"
        )
        assert isinstance(out, str)
        return out

    def test_the_drift_block_is_the_first_thing_after_the_sessions_name(self) -> None:
        html = self.page(READING + UNASKED)

        drift = html.index("data-next-session-drift")
        # The identity header names the session; everything a reader reads about it comes after,
        # and the drift block comes first of that.
        self.assertLess(html.index("<h1"), drift)
        for later in (
            'class="next-session-facts"',
            "data-next-command-reports",
            "HOW IT LANDED",
            "OBSERVED RECORD",
        ):
            with self.subTest(later=later):
                self.assertLess(drift, html.index(later))
        # Inside it, in the reader's order: their words, the agent's direction, the reading, then
        # every departure on record.
        block = html[drift : html.index('class="next-session-facts"')]
        order = [
            block.index(mark)
            for mark in (
                "WHAT YOU ASKED FOR",
                "CURRENT ACTIVITY",
                'data-next-cockpit-action="reading-ask"',
                "<h2>READING</h2>",
                "DEPARTURES RAISED TO YOU",
            )
        ]
        self.assertEqual(sorted(order), order)
        self.assertIn(">DRIFT<", block)

    def test_the_check_comes_before_every_caveat_so_it_reaches_the_first_screen(self) -> None:
        """Goal fields, direction, the check with its send disclosure, then the reading.

        The binding caveat, the discard explanation and its button, and the later-direction block
        all render below the reading: above the control they pushed it off a 1440x900 screen.
        """
        html = self.page(
            f"__dashboard.reading_disclosure = {json.dumps(reading.DISCLOSURE)};\n"
            f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
            f"__dashboard.reading_check = {json.dumps(annotation_store.ABSTENTION_CHECK)};\n"
            '__dashboard.sessions[0].annotation_binding_why = "Bound to codex:focus-1 by its id.";\n'
            # The lane on, so the departures section draws and its place can be measured.
            "__dashboard.unasked = true;\n"
        )
        drift = html[
            html.index("data-next-session-drift") : html.index('class="next-session-facts"')
        ]
        fields = drift.index('class="next-cockpit-held-fields"')
        direction = drift.index("CURRENT ACTIVITY")
        check = drift.index('data-next-cockpit-action="reading-ask"')
        disclosure = drift.index(reading.DISCLOSURE.split(".")[0])
        the_reading = drift.index("<h2>READING</h2>")
        self.assertLess(fields, direction)
        self.assertLess(direction, check)
        self.assertLess(direction, disclosure)
        # Beside the control: the disclosure and the button share one container, before the
        # reading starts.
        container = drift[drift.index('class="next-session-drift-check"') : the_reading]
        self.assertIn('data-next-cockpit-action="reading-ask"', container)
        self.assertIn(reading.DISCLOSURE.split(".")[0], container)
        for below in (
            "Bound to codex:focus-1 by its id.",
            annotation_store.DISCARD_WHY,
            'data-next-cockpit-action="held-discard"',
            'class="next-cockpit-conflict"',
        ):
            with self.subTest(below=below[:40]):
                self.assertLess(the_reading, drift.index(below))
        self.assertLess(
            drift.index('class="next-cockpit-conflict"'), drift.index("DEPARTURES RAISED TO YOU")
        )
        # Said once on the page, by the disclosure beside the control.
        self.assertEqual(1, visible_text(html).count("never a verification that the work was done"))

    def test_a_routed_session_with_no_project_renders_the_same_drift_block(self) -> None:
        """Rendering only: the route is set by hand here.

        Whether a session with no project can reach its page from the board is a routing
        question this test does not answer, so it claims no reachability.
        """
        out = self.run_fixture(
            ANNOTATED
            + """
for(const session of __dashboard.sessions){ session.project = ""; delete session.project_key; }
await refreshNext();
await __settle();
nextRoute = {view:"session", project:"", harness:"codex", session:"focus-1"};
renderNext();
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(out, str)
        self.assertIn("data-next-session-drift", out)
        self.assertIn("Capture every screen with live sessions", out)
        self.assertIn("Check for drift", out)

    def test_a_held_to_link_opens_that_sessions_page(self) -> None:
        out = self.run_fixture(
            r"""
const parsed = nextRouteFromFragment("#n=project:cargento:codex%3Afocus-1:held-to");
const emitted = nextFragmentForRoute(
  {view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
location.hash = "#n=project:cargento:codex%3Afocus-1:held-to";
window.dispatchEvent && window.dispatchEvent({type:"hashchange"});
navigateNext({view:"project", project:"cargento", focus:"codex:focus-1", tab:"held-to"});
await __settle();
console.log(JSON.stringify({parsed, emitted, route: nextRoute, hash: location.hash,
  tabs: nextCockpitTabs("codex:focus-1"),
  drift: __els.app.innerHTML.includes("data-next-session-drift")}));
"""
        )
        assert isinstance(out, dict)
        session = {
            "view": "session",
            "project": "cargento",
            "harness": "codex",
            "session": "focus-1",
        }
        self.assertEqual(session, out["parsed"])
        self.assertEqual("#n=session:cargento:codex:focus-1", out["emitted"])
        self.assertEqual(session, out["route"])
        self.assertEqual("#n=session:cargento:codex:focus-1", out["hash"])
        self.assertTrue(out["drift"])
        # The tab is retired rather than duplicated: the strip no longer offers it.
        self.assertNotIn("held-to", out["tabs"])

    def test_the_one_primary_reads_check_for_drift(self) -> None:
        html = self.page("__dashboard.reading_check = 'accepted';\n")

        primaries = re.findall(r"<button\b[^>]*next-action--primary[^>]*>[\s\S]*?</button>", html)
        self.assertEqual(1, len(primaries), primaries)
        self.assertIn("Check for drift", primaries[0])
        self.assertIn('data-next-cockpit-action="reading-ask"', primaries[0])
        self.assertNotIn("Ask for a reading", html)

    def test_a_question_without_a_raise_leaves_nothing_primary(self) -> None:
        """The owner's ruling (2026-09-23): no answer option is ever emphasised.

        A filled first option reads as advice to approve. With no raise on offer, nothing on the
        page is primary while the question is open, and the check renders as an ordinary control
        below the question.
        """
        html = self.page("""
__dashboard.reading_check = "accepted";
__dashboard.ask = true;
__dashboard.sessions[0].state = "needs_input";
__dashboard.asks = [{id:"ask-1", harness:"codex", session_id:"focus-1", project:"cargento",
  question:"Ship it?", options:["Yes", "Not yet"]}];
await refreshNext();
""")

        self.assertEqual([], re.findall(r"<button\b[^>]*next-action--primary[^>]*>", html))
        answers = re.findall(r"<button\b[^>]*data-next-answer=[^>]*>", html)
        self.assertEqual(2, len(answers), html)
        for answer in answers:
            self.assertIn('class="next-action"', answer)
        check = re.search(r'<button\b[^>]*data-next-cockpit-action="reading-ask"[^>]*>', html)
        self.assertIsNotNone(check)
        assert check is not None
        self.assertIn('class="next-action"', check.group(0))
        # The check sits below the question, not beside it or above.
        self.assertLess(html.index('data-next-session-section="ask"'), check.start())

    def test_the_raise_is_the_primary_while_a_question_is_open(self) -> None:
        html = self.page("""
const query = document.querySelector;
document.querySelector = selector => selector === NEXT_FOCUS_META
  ? {getAttribute(){return "test-focus";}} : query(selector);
__dashboard.reading_check = "accepted";
__dashboard.ask = true;
__dashboard.sessions[0].state = "needs_input";
__dashboard.sessions[0].focusable = true;
__dashboard.asks = [{id:"ask-1", harness:"codex", session_id:"focus-1", project:"cargento",
  question:"Ship it?", options:["Yes", "Not yet"]}];
await refreshNext();
""")

        primaries = re.findall(r"<button\b[^>]*next-action--primary[^>]*>", html)
        self.assertEqual(1, len(primaries), primaries)
        self.assertIn("data-next-raise-session=", primaries[0])
        for answer in re.findall(r"<button\b[^>]*data-next-answer=[^>]*>", html):
            self.assertNotIn("next-action--primary", answer)

    def test_departures_asked_and_unasked_render_once_in_the_drift_block(self) -> None:
        html = self.page(READING + UNASKED)

        self.assertNotIn("UNASKED CHECKS", html)
        drift = html[
            html.index("data-next-session-drift") : html.index('class="next-session-facts"')
        ]
        section = drift[drift.index("DEPARTURES RAISED TO YOU") :]
        # The unasked raise and the reading's departure: listed in the block's departures, and
        # never outside the block. The reading's own row above it states the same result, which
        # is the reading rather than a second list.
        for text in ("Two turns edited the running board.", "It changed the board."):
            with self.subTest(text=text):
                self.assertIn(text, section)
                self.assertEqual(html.count(text), drift.count(text))
        self.assertEqual(1, html.count("Two turns edited the running board."))

    def test_the_departures_section_draws_only_with_the_lane_on_or_a_departure_on_record(
        self,
    ) -> None:
        """DRC-4543, restored: a panel on every session of a board whose switch is off is noise.

        A raise on record keeps the section whichever way the switch is set (DRC-4559).
        """
        states = {
            "lane off, nothing on record": ("delete __dashboard.unasked;\n", False),
            "lane on, nothing on record": (
                "__dashboard.unasked = true;\n__dashboard.sessions[0].departure_checked = true;\n",
                True,
            ),
            "lane off, a raise standing": (UNASKED + "delete __dashboard.unasked;\n", True),
            "lane off, a reading's departure": ("delete __dashboard.unasked;\n" + READING, True),
        }
        for name, (setup, drawn) in states.items():
            with self.subTest(state=name):
                html = self.page(setup)
                self.assertEqual(drawn, "DEPARTURES RAISED TO YOU" in html, name)
                self.assertEqual(drawn, 'class="next-cockpit-departures"' in html, name)

    def test_a_consistent_result_is_shown_only_with_its_evidence_line(self) -> None:
        html = self.page(CONSISTENT)

        row = re.search(
            r'<div class="next-cockpit-reading-row">(?:(?!<div class="next-cockpit-reading-row">)'
            r"[\s\S])*?consistent with the evidence read[\s\S]*?</div>",
            html,
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertIn("next-cockpit-reading-evidence", row.group(0))
        self.assertEqual(1, html.count(">consistent with the evidence read<"))

    def test_no_state_of_the_page_says_a_session_has_no_drift(self) -> None:
        states = {
            "untyped": """
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
""",
            "typed": "",
            "read": READING,
            "consistent": CONSISTENT,
            "raised": READING + UNASKED,
            "lane-on-empty": "__dashboard.unasked = true;\n"
            "__dashboard.sessions[0].departure_checked = true;\n",
        }
        for name, setup in states.items():
            with self.subTest(state=name):
                text = visible_text(self.page(setup))
                self.assertIsNone(DRIFT_ABSENCE.search(text), DRIFT_ABSENCE.findall(text))
                # And the word is present where it names the block and the control.
                self.assertIn("DRIFT", text)
                self.assertIn("Check for drift", text)

    def test_a_refused_check_stays_on_the_page_and_names_one_next_step(self) -> None:
        cases = {
            "no goal": (
                """
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
""",
                "Save a goal above to check for drift.",
            ),
            "model unread": ("", "Cargento asks again with the next update."),
            "model off": (
                """
__fetchImpl = async url => ({ok: true, json: async () =>
  String(url).startsWith("/api/project-context")
    ? {semantic: __semantic, child_assignments: [], observers: [],
       observer_model: {enabled: false}}
    : __dashboard});
""",
                "Start with --observer-model to allow one; --no-observer-model refuses it.",
            ),
            # The server's own sentences, as the payload publishes them: the discard refusal is
            # `annotations.DISCARD_SENTENCES["unreadable"]`, which says why and names no step, so
            # the page adds the one that lifts it.
            "discarded": (
                f"__dashboard.annotate_discard = {json.dumps(annotation_store.DISCARD_SENTENCES)};\n"
                """
__dashboard.sessions[0].annotation_goal = "";
__dashboard.sessions[0].annotation_revision = null;
__dashboard.sessions[0].annotation_revision_count = 0;
__dashboard.sessions[0].annotation_discarded_at = 90;
__dashboard.sessions[0].annotation_discarded_why = "Discarded";
""",
                annotation_store.DISCARD_SENTENCES["unreadable"]
                + " Save a goal above to check for drift.",
            ),
            # A build constant no press lifts: the sentence says what it waits on, and no longer
            # points at "this ruling", which named the retired tab's paragraph.
            "unauthorized": (
                f"__dashboard.reading_check = {json.dumps(annotation_store.ABSTENTION_CHECK_NOT_RUN)};\n"
                """
__fetchImpl = async url => ({ok: true, json: async () =>
  String(url).startsWith("/api/project-context")
    ? {semantic: __semantic, child_assignments: [], observers: [],
       observer_model: {enabled: true}}
    : __dashboard});
""",
                "It waits on a later release; nothing on this page lifts it.",
            ),
        }
        for name, (setup, step) in cases.items():
            with self.subTest(state=name):
                check = (
                    ""
                    if name == "unauthorized"
                    else f"__dashboard.reading_check = {json.dumps(annotation_store.ABSTENTION_CHECK)};\n"
                )
                html = self.page(check + setup)
                control = re.search(
                    r'<button\b[^>]*data-next-cockpit-action="reading-ask"[^>]*>([\s\S]*?)</button>',
                    html,
                )
                self.assertIsNotNone(control, "the check left the page")
                assert control is not None
                self.assertIn("Check for drift", control.group(1))
                self.assertIn('aria-disabled="true"', control.group(0))
                described = re.search(r'aria-describedby="([^"]+)"', control.group(0))
                self.assertIsNotNone(described)
                assert described is not None
                reason = re.search(rf'<p\b[^>]*id="{described.group(1)}"[^>]*>([^<]*)</p>', html)
                self.assertIsNotNone(reason)
                assert reason is not None
                said = reason.group(1).replace("&#39;", "'").replace("&quot;", '"')
                self.assertIn(step, said)
                self.assertNotIn("this ruling", said)
                # One next step, not two: the refusal ends on the step it names.
                self.assertTrue(said.endswith(step), said)

    def test_conflict_to_settle_names_only_an_unsettled_later_direction(self) -> None:
        """DEC-20 item 3: "Conflict to settle" is the label for an unsettled later direction.

        Nothing since, a settled baseline and an unread record have nothing to settle, so they
        keep the neutral heading rather than asking the reader to act on nothing.
        """
        states = {
            # The fixture's own person-authored facts land at 102 and 104, after words saved at 100.
            "pending": ("", "CONFLICT TO SETTLE"),
            "nothing since": ("__dashboard.sessions[0].annotation_at = 106;\n", "A LATER DIRECTION"),
            "settled": (
                "__dashboard.sessions[0].annotation_settled_at = 300;\n"
                "__dashboard.sessions[0].annotation_settled_through = 300;\n"
                "__dashboard.sessions[0].annotation_settled_revision = 2;\n",
                "A LATER DIRECTION",
            ),
        }
        for name, (setup, heading) in states.items():
            with self.subTest(state=name):
                html = self.page(setup)
                block = re.search(r'<section class="next-cockpit-conflict">[\s\S]*?</section>', html)
                self.assertIsNotNone(block, html)
                assert block is not None
                other = {"CONFLICT TO SETTLE", "A LATER DIRECTION"} - {heading}
                self.assertIn(f"<h2>{heading}</h2>", block.group(0))
                self.assertNotIn(other.pop(), html)
        # And a record this page could not read: whether a later direction exists is unknown.
        out = self.run_fixture(
            ANNOTATED
            + """
const session = __dashboard.sessions[0];
console.log(JSON.stringify(nextCockpitConflict(session, nextCockpitAnnotation(session),
  {entries: [], state: "unread"})));
"""
        )
        assert isinstance(out, str)
        self.assertIn("<h2>A LATER DIRECTION</h2>", out)
        self.assertNotIn("CONFLICT TO SETTLE", out)

    def test_the_pending_check_says_how_long_it_can_take(self) -> None:
        out = self.run_fixture(
            ANNOTATED
            + """
__dashboard.reading_check = "accepted";
const context = __fetchImpl;
__fetchImpl = async url => String(url) === "/api/reading"
  ? new Promise(() => {})
  : (String(url).startsWith("/api/project-context")
    ? {ok: true, json: async () => ({semantic: __semantic, child_assignments: [], observers: [],
        observer_model: {enabled: true}})}
    : context(url));
"""
            + SESSION_ROUTE
            + """
await __settle();
await __settle();
const session = __dashboard.sessions[0];
const group = nextProjectGroups().find(row => row.label === "cargento");
void nextCockpitAskForReading(session, nextCockpitObserverModel(group));
await __settle();
console.log(JSON.stringify(visible_text_source(__els.app.innerHTML)));
function visible_text_source(html){ return html.replace(/<[^>]*>/g, " ").replace(/\\s+/g, " "); }
"""
        )
        assert isinstance(out, str)
        self.assertIn("Checking for drift…", out)
        self.assertIn("This can take up to a minute; the rest of the page stays usable.", out)


@unittest.skipUnless(shutil.which("node"), "node not available")
class BesideADepartureTheWayBackIsOneStepTest(NextPageJsHarness):
    """DRC-4642. Cargento never writes into a session (DEC-16), so acting on drift means putting
    the reader back in it: the resume command and the raise sit beside each departure."""

    def page(self, setup: str) -> str:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + ANNOTATED
            + READING
            + UNASKED
            + setup
            + "\nawait refreshNext();\nawait __settle();\n"
            + "navigateNext({view:'session', project:'cargento', harness:__h, session:__s});\n"
            + "await __settle();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            storage_prelude({}) + FIXTURE,
        )
        assert isinstance(out, str)
        return out

    @staticmethod
    def departures(html: str) -> list[str]:
        return re.findall(
            r'<div class="next-(?:session|cockpit)-departure">[\s\S]*?</div>\s*(?=<div class='
            r'"next-(?:session|cockpit)-departure|<p|<div class="next-cockpit-departure-part|'
            r"</div>)",
            html,
        )

    def test_a_codex_departure_offers_its_resume_command_and_raise_while_working(self) -> None:
        html = self.page("""
const query = document.querySelector;
document.querySelector = selector => selector === NEXT_FOCUS_META
  ? {getAttribute(){return "test-focus";}} : query(selector);
__dashboard.sessions[0].resume_id = "focus-1";
__dashboard.sessions[0].focusable = true;
__dashboard.sessions[0].state = "working";
const __h = "codex", __s = "focus-1";
""")
        drift = html[
            html.index("data-next-session-drift") : html.index('class="next-session-facts"')
        ]
        rows = re.findall(r"data-next-departure-reentry[^>]*>[\s\S]*?</div>", drift)
        # One per departure: the reading's and the unasked lane's.
        self.assertEqual(2, len(rows), drift)
        for row in rows:
            self.assertIn('data-next-copy-command="codex resume focus-1"', row)
            self.assertIn("data-next-raise-session=", row)

    def test_a_harness_with_no_resume_command_says_why_once(self) -> None:
        html = self.page("""
for(const session of __dashboard.sessions){
  if(session.harness === "codex"){ session.harness = "pi"; session.sid = "focus-1"; }
}
const __h = "pi", __s = "focus-1";
""")
        drift = html[
            html.index("data-next-session-drift") : html.index('class="next-session-facts"')
        ]
        self.assertNotIn("data-next-copy-command", drift)
        why = "Pi publishes no re-entry command, so there is none to copy."
        self.assertEqual(1, drift.count(why), drift)

    def test_nothing_beside_a_departure_writes_to_the_session(self) -> None:
        html = self.page("""
__dashboard.sessions[0].resume_id = "focus-1";
const __h = "codex", __s = "focus-1";
""")
        drift = html[
            html.index("data-next-session-drift") : html.index('class="next-session-facts"')
        ]
        reentry = "".join(re.findall(r"data-next-departure-reentry[^>]*>[\s\S]*?</div>", drift))
        self.assertTrue(reentry)
        # Copy and raise are the whole vocabulary: no form, no steer, no send.
        self.assertNotRegex(reentry, r"<form|data-next-steer|data-next-send|/api/")


if __name__ == "__main__":
    unittest.main()
