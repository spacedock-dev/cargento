"""The expected outcome as a checklist on the session page (DRC-4685).

Item 3 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
makes the expected outcome up to six typed lines. This page lets a reader type, add and remove
them, refuses a seventh with a sentence saying why, and shows a reading's answer one line per row.
Every assertion is on what a reader sees or what the page sends.

The fixtures are the cockpit composition board's, read through the module rather than imported by
name, so the loader does not collect that class a second time here.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import unittest
from typing import Any

from cargento_runtime import annotations as annotation_store
from cargento_runtime import reading

from . import test_next_cockpit as cockpit_tests
from .next_harness import NextPageJsHarness, storage_prelude

FIXTURE = cockpit_tests.NextCockpitCompositionTest.FIXTURE
ANNOTATED = cockpit_tests.CockpitHeldToTabTest.ANNOTATED
SESSION_ROUTE = (
    'navigateNext({view:"session", project:"cargento", harness:"codex", session:"focus-1"});'
)
SIX = [
    "Failed events retry with backoff",
    "Events that still fail go to a dead-letter table",
    "Tests cover the retry path",
    "Tests cover the failure path",
    "The public API does not change",
    "The logging migration stays out of this branch",
]
FULL = "An expected outcome holds six lines. Replace or merge a line to add another."


def lines_setup(texts: list[str], sources: list[str] | None = None) -> str:
    """The published flat fields for these lines, as `annotations.published` writes them."""
    out = []
    for k in range(1, 7):
        text = texts[k - 1] if k <= len(texts) else ""
        source = (sources or ["typed"] * len(texts))[k - 1] if k <= len(texts) else None
        out.append(f"__dashboard.sessions[0].annotation_line_{k} = {json.dumps(text)};")
        out.append(f"__dashboard.sessions[0].annotation_line_{k}_source = {json.dumps(source)};")
        out.append(f'__dashboard.sessions[0].annotation_line_{k}_source_id = "";')
    why = "" if texts else annotation_store.NO_LINES_TYPED
    out.append(f"__dashboard.sessions[0].annotation_lines_why = {json.dumps(why)};")
    return "\n".join(out) + "\n"


def visible_text(html: str) -> str:
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


# A click the delegated handler reads: the target is its own closest action element.
CLICK = """
const __press = (action, arg = "") => __fire("click", {preventDefault(){},
  target:{dataset:{nextCockpitAction:action, arg:String(arg)}, closest(){ return this; }}});
const __type = (index, value) => __fire("input", {target:{value,
  dataset:{nextCockpitHeldLinesKey:"held:codex:focus-1:lines", nextCockpitHeldLineIndex:String(index)},
  closest(selector){ return selector === "[data-next-cockpit-held-lines-key]" ? this : null; }}});
const __escape = index => __fire("keydown", {key:"Escape", preventDefault(){},
  target:{dataset:{nextCockpitHeldLinesKey:"held:codex:focus-1:lines", nextCockpitHeldLineIndex:String(index)},
  closest(selector){ return selector === "[data-next-cockpit-held-lines-key]" ? this : null; }}});
"""


class _ChecklistPage(NextPageJsHarness):
    """The session page with the drift block's checklist on it, and a reading to put under it."""

    def page(self, setup: str = "", after: str = "") -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + ANNOTATED
            + setup
            + CLICK
            + SESSION_ROUTE
            + "\nawait __settle();\nawait __settle();\n"
            + (after or "console.log(JSON.stringify(__els.app.innerHTML));"),
            storage_prelude({}) + FIXTURE,
        )

    def reading(self, criteria: str, extra: str = "") -> str:
        return (
            "__dashboard.sessions[0].annotation_at = 106;\n"
            "__dashboard.sessions[0].annotation_reading_count = 1;\n"
            "__dashboard.sessions[0].annotation_assessment = {revision_read:2, "
            f"evidence_through: 105, {extra} criteria:{{{criteria}}}}};\n"
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheExpectedOutcomeIsAChecklistTest(_ChecklistPage):
    def test_six_saved_lines_render_as_six_boxes_each_saying_where_it_came_from(self) -> None:
        html = self.page(lines_setup(SIX, ["typed", "typed", "entry", "typed", "typed", "typed"]))

        self.assertIn("EXPECTED OUTCOME", html)
        boxes = re.findall(
            r'data-next-cockpit-held-line-index="(\d)"[^>]*>([^<]*)</textarea>', html
        )
        self.assertEqual([(str(i), text) for i, text in enumerate(SIX)], boxes)
        captions = re.findall(r'data-next-cockpit-held-line-source="\d">([^<]*)<', html)
        self.assertEqual(
            ["typed", "typed", "added from an entry", "typed", "typed", "typed"], captions
        )
        self.assertEqual(
            6, len(re.findall(r'data-next-cockpit-held-line-count="\d">\d+/240<', html))
        )

    def test_at_six_lines_add_stays_on_the_page_inert_and_a_sentence_says_why(self) -> None:
        html = self.page(lines_setup(SIX))

        add = re.search(r'<button[^>]*data-next-cockpit-action="held-line-add"[^>]*>', html)
        assert add is not None
        self.assertIn('aria-disabled="true"', add.group(0))
        self.assertNotIn("hidden", add.group(0))
        full = re.search(r"<p[^>]*data-next-cockpit-held-full[^>]*>([^<]*)</p>", html)
        assert full is not None
        self.assertEqual(FULL, full.group(1))
        self.assertNotIn("hidden", full.group(0))
        self.assertIn('aria-describedby="next-cockpit-held-full"', add.group(0))

    def test_below_six_lines_add_is_live_and_the_sentence_is_hidden(self) -> None:
        html = self.page(lines_setup(SIX[:2]))

        add = re.search(r'<button[^>]*data-next-cockpit-action="held-line-add"[^>]*>', html)
        assert add is not None
        self.assertNotIn("aria-disabled", add.group(0))
        full = re.search(r"<p[^>]*data-next-cockpit-held-full[^>]*>", html)
        assert full is not None
        self.assertIn("hidden", full.group(0))

    def test_pressing_add_at_six_adds_no_seventh_line(self) -> None:
        out = self.page(
            lines_setup(SIX),
            """
__press("held-line-add");
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  boxes: (html.match(/data-next-cockpit-held-line-index="/g) || []).length,
  draft: nextCockpitHeldDrafts.get("held:codex:focus-1:lines") || null,
}));
""",
        )

        self.assertEqual(6, out["boxes"])
        self.assertIn(out["draft"], (None, SIX))

    def test_a_reader_adds_a_line_types_it_and_saves_the_whole_list(self) -> None:
        out = self.page(
            lines_setup(SIX[:1]),
            """
__fetchImpl = url => String(url) === "/api/annotate"
  ? Promise.resolve({ok:true, json: async () => ({ok:true, persisted:true, outcome:"stored"})})
  : new Promise(() => {});
__press("held-line-add");
await __settle();
const added = (__els.app.innerHTML.match(/data-next-cockpit-held-line-index="/g) || []).length;
__type(1, "Tests cover the retry path");
__press("held-save", "lines");
await __settle();
await __settle();
const call = __fetchCalls.find(args => String(args[0]) === "/api/annotate");
console.log(JSON.stringify({added, body: call ? JSON.parse(call[1].body) : null}));
""",
        )

        self.assertEqual(2, out["added"])
        body = out["body"]
        assert body is not None
        self.assertEqual([SIX[0], "Tests cover the retry path"], body["lines"])
        self.assertEqual(2, body["expected_revision"])
        self.assertIsNone(body["goal"])
        self.assertNotIn("output", body)

    def test_typing_updates_the_draft_without_redrawing_the_page(self) -> None:
        out = self.page(
            lines_setup(SIX[:1]),
            """
const before = __els.app.innerHTML;
__type(0, "edited\\nline");
console.log(JSON.stringify({same: __els.app.innerHTML === before,
  draft: nextCockpitHeldDrafts.get("held:codex:focus-1:lines")}));
""",
        )

        self.assertTrue(out["same"])
        # The store's scrub, mirrored: a pasted line break is one space.
        self.assertEqual(["edited line"], out["draft"])

    def test_remove_drops_a_line_and_escape_puts_the_saved_list_back(self) -> None:
        out = self.page(
            lines_setup(SIX[:3]),
            """
__press("held-line-remove", 1);
await __settle();
const removed = [...__els.app.innerHTML.matchAll(
  /data-next-cockpit-held-line-index="\\d"[^>]*>([^<]*)<\\/textarea>/g)].map(m => m[1]);
const saveShown = /data-next-cockpit-action="held-save" data-arg="lines">/.test(__els.app.innerHTML);
__escape(0);
await __settle();
const restored = [...__els.app.innerHTML.matchAll(
  /data-next-cockpit-held-line-index="\\d"[^>]*>([^<]*)<\\/textarea>/g)].map(m => m[1]);
console.log(JSON.stringify({removed, saveShown, restored}));
""",
        )

        self.assertEqual([SIX[0], SIX[2]], out["removed"])
        self.assertTrue(out["saveShown"])
        self.assertEqual(SIX[:3], out["restored"])

    def test_a_session_with_no_lines_offers_one_empty_line_and_says_none_is_typed(self) -> None:
        html = self.page(lines_setup([]))

        boxes = re.findall(
            r'data-next-cockpit-held-line-index="(\d)"[^>]*>([^<]*)</textarea>', html
        )
        self.assertEqual([("0", "")], boxes)
        self.assertIn(annotation_store.NO_LINES_TYPED, visible_text(html))
        self.assertNotIn('data-next-cockpit-held-line-source="0"', html)

    def test_a_reading_of_six_lines_shows_six_rows_each_with_its_line_and_source(self) -> None:
        unverifiable = (
            f'result:"{reading.RESULT_UNVERIFIABLE}", cites:[], detail:"", why:"not-asked"'
        )
        criteria = ", ".join(
            [f'goal:{{{unverifiable}, clause:"Capture every screen with live sessions"}}']
            + [f"line_{k}:{{{unverifiable}, clause:{json.dumps(SIX[k - 1])}}}" for k in range(1, 7)]
        )

        html = self.page(lines_setup(SIX) + self.reading(criteria))

        block = html[html.index("<h2>READING</h2>") :]
        text = visible_text(block)
        for k, line in enumerate(SIX, start=1):
            with self.subTest(line=k):
                self.assertIn(f"EXPECTED OUTCOME · LINE {k} · TYPED", text)
                self.assertIn(line, text)
        self.assertNotIn("This board cannot read the reading", text)

    def test_a_reading_stored_before_the_checklist_shows_a_goal_row_and_one_outcome_row(
        self,
    ) -> None:
        # A tab left open across the upgrade can still hold the old `output` key.
        criteria = (
            f'goal:{{result:"{reading.RESULT_UNVERIFIABLE}", cites:[], detail:"", clause:"G"}}, '
            f'output:{{result:"{reading.RESULT_UNVERIFIABLE}", cites:[], detail:"", '
            'clause:"a CSV export"}'
        )

        html = self.page(lines_setup(["a CSV export"]) + self.reading(criteria))

        text = visible_text(html[html.index("<h2>READING</h2>") :])
        self.assertIn("TYPED GOAL", text)
        self.assertIn("EXPECTED OUTCOME", text)
        self.assertIn("a CSV export", text)
        self.assertNotIn("LINE 2", text)

    def test_no_row_is_ever_marked_done_or_given_a_check_mark(self) -> None:
        cited = 'result:"consistent with the evidence read", cites:["fo-a"], detail:""'
        criteria = ", ".join(
            [f'goal:{{{cited}, clause:"G"}}']
            + [f"line_{k}:{{{cited}, clause:{json.dumps(SIX[k - 1])}}}" for k in range(1, 7)]
        )

        html = self.page(lines_setup(SIX) + self.reading(criteria))

        text = visible_text(html)
        self.assertNotRegex(text, r"\bDone\b")
        for mark in ("\u2713", "\u2714", "\u2705", "\u2611"):
            self.assertNotIn(mark, html)

    def test_the_intent_log_lists_each_line_the_reader_typed(self) -> None:
        out = self._run_page_js(
            """
const row = {goal:"G", goal_why:"", lines_why:"", line_1:"first line", line_2:"second line",
  line_1_source:"typed", line_2_source:"typed", line_3:"", line_4:"", line_5:"", line_6:""};
console.log(JSON.stringify(nextIntentSources(row, null, true)));
""",
            storage_prelude({}) + FIXTURE,
        )

        text = visible_text(out)
        self.assertIn("Expected outcome, line 1: first line", text)
        self.assertIn("Expected outcome, line 2: second line", text)
        self.assertNotIn("line 3", text)

    def test_the_intent_log_says_when_no_line_was_typed(self) -> None:
        out = self._run_page_js(
            """
const row = {goal:"G", goal_why:"", lines_why:"No expected outcome typed.", line_1:"", line_2:"",
  line_3:"", line_4:"", line_5:"", line_6:""};
console.log(JSON.stringify(nextIntentSources(row, null, true)));
""",
            storage_prelude({}) + FIXTURE,
        )

        self.assertIn("Expected outcome: No expected outcome typed.", visible_text(out))


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheCorrectionRoundOnThePageTest(_ChecklistPage):
    """The review's page findings, each a sentence about what the reader sees."""

    UNV = f'result:"{reading.RESULT_UNVERIFIABLE}", cites:[], detail:"", why:""'

    def reading_block(self, html: str) -> str:
        return visible_text(html[html.index("<h2>READING</h2>") :])

    def test_a_line_typed_after_a_reading_gets_no_row_under_it(self) -> None:
        # The reading read revision 1, which had one line. Revision 2 holds three.
        criteria = f'goal:{{{self.UNV}, clause:"G"}}, line_1:{{{self.UNV}, clause:"A"}}'

        html = self.page(
            lines_setup(["A", "B", "C"])
            + self.reading(criteria).replace("revision_read:2", "revision_read:1")
        )

        text = self.reading_block(html)
        self.assertIn("LINE 1", text)
        self.assertNotIn("LINE 2", text)
        self.assertNotIn("LINE 3", text)

    def test_no_source_is_claimed_under_a_reading_of_an_older_revision(self) -> None:
        criteria = f'goal:{{{self.UNV}, clause:"G"}}, line_1:{{{self.UNV}, clause:"A"}}'

        html = self.page(
            lines_setup(["A"])
            + self.reading(criteria).replace("revision_read:2", "revision_read:1")
        )

        self.assertNotIn("· TYPED", self.reading_block(html))

    def test_no_source_is_claimed_for_words_the_reading_did_not_read(self) -> None:
        criteria = (
            f'goal:{{{self.UNV}, clause:"G"}}, line_1:{{{self.UNV}, clause:"A"}}, '
            f'line_2:{{{self.UNV}, clause:"different words"}}'
        )

        html = self.page(lines_setup(["A", "B"]) + self.reading(criteria))

        text = self.reading_block(html)
        self.assertIn("LINE 1 · TYPED", text)
        self.assertIn("LINE 2", text)
        self.assertNotIn("LINE 2 · TYPED", text)

    def test_a_reading_from_before_the_checklist_is_not_drawn_twice(self) -> None:
        criteria = f'goal:{{{self.UNV}, clause:"G"}}, output:{{{self.UNV}, clause:"a CSV export"}}'

        html = self.page(lines_setup(["a CSV export"]) + self.reading(criteria))

        self.assertNotIn("LINE 1", self.reading_block(html))

    def test_a_line_resting_only_on_narration_is_not_verifiable_on_the_page(self) -> None:
        consistent = 'result:"consistent with the evidence read", detail:""'
        criteria = (
            f'goal:{{{self.UNV}, clause:"G"}}, line_1:{{{self.UNV}, clause:"A"}}, '
            f'line_2:{{{consistent}, cites:["task-a"], clause:"B"}}'
        )

        out = self.page(
            lines_setup(["A", "B"]) + self.reading(criteria),
            """
const session = nextCockpitFocusedSession(nextCockpitRouteGroup());
const annotation = nextCockpitAnnotation(session);
const source = nextCockpitWorkSource(nextCockpitRouteGroup(), session);
const shape = nextCockpitReadingShape(annotation.assessment, annotation,
  source.all || source.entries, "", false);
console.log(JSON.stringify(shape.criteria.map(row => [row.key, row.result])));
""",
        )

        self.assertEqual(["line_2", reading.RESULT_UNVERIFIABLE], out[-1])

    def test_pressing_add_at_six_says_why_aloud(self) -> None:
        out = self.page(
            lines_setup(SIX),
            """
const said = [];
nextCockpitAnnounceCue = (key, sentence, assertive) => said.push([sentence, assertive]);
__press("held-line-add");
await __settle();
console.log(JSON.stringify(said));
""",
        )

        self.assertEqual([[FULL, False]], out)

    def test_discarding_everything_drops_a_half_typed_line(self) -> None:
        out = self.page(
            lines_setup(SIX[:1]),
            """
__fetchImpl = url => String(url) === "/api/annotate"
  ? Promise.resolve({ok:true, json: async () => ({ok:true, persisted:true, outcome:"stored",
      withdrew:true})})
  : new Promise(() => {});
__type(0, "half typed");
const before = nextCockpitHeldDrafts.has("held:codex:focus-1:lines");
nextCockpitDiscardAnnotation(nextCockpitFocusedSession(nextCockpitRouteGroup()));
await __settle();
await __settle();
console.log(JSON.stringify({before, after: nextCockpitHeldDrafts.has("held:codex:focus-1:lines")}));
""",
        )

        self.assertEqual({"before": True, "after": False}, out)

    def test_a_save_over_a_store_the_server_cannot_read_says_so(self) -> None:
        out = self.page(
            lines_setup(SIX[:1]),
            """
__fetchImpl = url => String(url) === "/api/annotate"
  ? Promise.resolve({ok:true, json: async () => ({ok:true, persisted:false, outcome:"untrusted"})})
  : new Promise(() => {});
__type(0, "edited");
__press("held-save", "lines");
await __settle();
await __settle();
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""",
        )

        self.assertIn(
            "Not saved. Cargento could not read cargento-annotations.json, so nothing was saved and "
            "nothing was overwritten, and what you typed is still in the box. Move or repair that "
            "file to save again.",
            visible_text(out),
        )

    def save_answering(self, outcome: str) -> str:
        out = self.page(
            lines_setup(SIX[:1]),
            """
__fetchImpl = url => String(url) === "/api/annotate"
  ? Promise.resolve({ok:true, json: async () => ({ok:true, persisted:false, outcome:"OUTCOME"})})
  : new Promise(() => {});
__type(0, "edited");
__press("held-save", "lines");
await __settle();
await __settle();
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""".replace("OUTCOME", outcome),
        )
        return visible_text(out)

    def test_a_save_to_a_session_this_build_cannot_read_says_what_to_do(self) -> None:
        text = self.save_answering("unreadable")

        self.assertIn("saved by a build of Cargento that can read more than this one", text)
        self.assertIn("what you typed is still in the box", text)

    def test_the_board_says_the_store_could_not_be_read_instead_of_nothing_typed(self) -> None:
        html = self.page(
            lines_setup([])
            + "__dashboard.sessions[0].annotation_goal = '';\n"
            + f"__dashboard.sessions[0].annotation_goal_why = {json.dumps(annotation_store.NO_GOAL_TYPED)};\n"
            + f"__dashboard.annotate_unreadable = {json.dumps(annotation_store.STORE_UNREADABLE)};\n"
        )

        text = visible_text(html)
        self.assertIn(annotation_store.STORE_UNREADABLE, text)
        self.assertNotIn(annotation_store.NO_GOAL_TYPED, text)
        self.assertNotIn(annotation_store.NO_LINES_TYPED, text)

    def test_an_adoption_over_an_unreadable_store_does_not_say_the_prompt_changed(self) -> None:
        out = self.page(
            lines_setup([]),
            """
__fetchImpl = url => String(url) === "/api/annotate"
  ? Promise.resolve({ok:true, json: async () => ({ok:true, persisted:false, outcome:"untrusted"})})
  : new Promise(() => {});
const session = nextCockpitFocusedSession(nextCockpitRouteGroup());
session.harness = "claude"; session.first_prompt = "Shape the cockpit"; session.first_prompt_at = 50;
await nextAdoptPrompt(session, "first-prompt");
console.log(JSON.stringify(nextCockpitReadingRequests.get(sessKey(session)) || null));
""",
        )

        assert out is not None
        self.assertIn("could not read cargento-annotations.json", out["message"])
        self.assertNotIn("changed", out["message"])

    def test_removing_the_first_of_two_saved_lines_says_which_one_stayed(self) -> None:
        out = self.page(
            lines_setup(["same", "same"]),
            """
__fetchImpl = url => String(url) === "/api/annotate"
  ? Promise.resolve({ok:true, json: async () => ({ok:true, persisted:true, outcome:"stored"})})
  : new Promise(() => {});
__press("held-line-remove", 0);
await __settle();
__press("held-save", "lines");
await __settle();
const call = __fetchCalls.find(args => String(args[0]) === "/api/annotate");
console.log(JSON.stringify(call ? JSON.parse(call[1].body) : null));
""",
        )

        self.assertEqual(["same"], out["lines"])
        self.assertEqual([1], out["origins"])


class ThePageAndTheStoreAgreeOnSixTest(unittest.TestCase):
    def test_the_page_bounds_the_list_where_the_store_does(self) -> None:
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "cargento_runtime"
            / "web"
            / "next-project.js"
        ).read_text(encoding="utf-8")
        found = re.search(r"const NEXT_OUTCOME_LINES_MAX = (\d+);", source)
        assert found is not None
        self.assertEqual(reading.MAX_OUTCOME_LINES, int(found.group(1)))


if __name__ == "__main__":
    unittest.main()
