"""Parity and polish on the drafted-goal page (DRC-4732, DRC-4734, DRC-4726, DRC-4736).

Built to the owner's rulings of 2026-09-28. Analyze and the goal save name the revision the
page drew, and a stale one is refused; Keep lets the reader read the whole text of every
direction it settles, or refuses; the page judges a check as the server's `check_supports`
does on every harness, and the record column says whose work results are read; an analysis
announces its start and its outcome once, through the page's persistent polite region; the
later-direction question adds no second mark after a quote that ends in one; and the Intent
heading's landing focus uses the page's accent ring.

Every assertion is on what a reader sees, what the page sends, or what the region carries.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from types import SimpleNamespace
from typing import Any

from cargento_runtime import project_context, reading

from . import test_harness_records as records_tests
from . import test_next_cockpit as cockpit_tests
from .next_harness import NEXT_STYLES, NextPageJsHarness, storage_prelude
from .test_next_intent_draft import (
    EARLIEST,
    KEEP_REFUSED,
    ROUTE,
    TYPED,
    _DraftPage,
    drift_of,
    intent_of,
    visible_text,
)

SETTLED = TYPED + "__s.annotation_settled_through = 104; __s.annotation_settled_at = 104;\n"
DOM = cockpit_tests.CockpitCuesReachTheReaderTest.ANNOUNCER_DOM
FINISHED = "The analysis finished. Its reading is in the Reading section."
READ_FIRST = (
    "Nothing was settled yet. Each direction Keep settles is now shown whole. Read it, then "
    "press again."
)
UNOPENED = (
    "Nothing was settled and no analysis was started: Cargento could not open the whole text "
    "of every direction Keep would settle, so it cannot show you what you would keep. Press "
    "again to retry."
)
CLIPPED = "Only the start of this direction is shown; it is longer than Cargento opens."
SAVE_REFUSED = "Not saved. The server refused the write, and your words are still in the box."
RECORD_LINE = "Cargento reads work results from Claude Code and Pi only."
JOB = (
    'const JOB = {id:"j1", phase:"preparing", started_at:106, phase_at:106, provider:"codex",'
    ' steps:[{phase:"preparing", text:"Preparing what is sent"},'
    ' {phase:"waiting", text:"Waiting for Codex"}, {phase:"checking", text:"Checking the reply"}]};\n'
    '__reply["/api/reading"] = () => { __dashboard.reading_jobs = {"claude:focus-1": JOB};'
    " return {status:202, body:{ok:true, job:JOB}}; };\n"
)
POLITE = 'wrote("next-cockpit-cue-status")'


def posted(out: dict[str, Any]) -> list[str]:
    return [post["url"] for post in out["posts"]]


@unittest.skipUnless(shutil.which("node"), "node not available")
class AnalyzeAndTheGoalSaveNameTheirRevisionTest(_DraftPage):
    """DRC-4732 items 1 and 2."""

    def test_analyze_sends_the_revision_the_page_drew(self) -> None:
        out = self.drive(
            SETTLED,
            '__press("reading-ask");\nawait __settle();\nconsole.log(JSON.stringify(__posts));',
        )
        assert isinstance(out, list)
        self.assertEqual("/api/reading", out[0]["url"])
        self.assertEqual(2, out[0]["body"]["expected_revision"])

    def test_after_a_discard_analyze_sends_the_revision_number_not_the_count(self) -> None:
        # Numbering continues past a discard: revision 3 is the only one kept.
        out = self.drive(
            SETTLED + "__s.annotation_revision = 3; __s.annotation_revision_count = 1;\n",
            '__press("reading-ask");\nawait __settle();\nconsole.log(JSON.stringify(__posts));',
        )
        assert isinstance(out, list)
        self.assertEqual(3, out[0]["body"]["expected_revision"])

    def test_allow_and_analyze_sends_the_revision_the_page_drew(self) -> None:
        out = self.drive(
            SETTLED + '__dashboard.reading = {consent:false, reason:"consent-required"};\n',
            '__press("reading-ask");\nawait __settle();\n__press("reading-allow");\n'
            "await __settle();\nconsole.log(JSON.stringify(__posts));",
        )
        assert isinstance(out, list)
        self.assertEqual(["/api/reading"], [post["url"] for post in out])
        self.assertIs(True, out[0]["body"]["allow"])
        self.assertEqual(2, out[0]["body"]["expected_revision"])

    def test_a_stale_analyze_says_the_intent_changed_and_shows_no_analysis(self) -> None:
        out = self.drive(
            SETTLED + '__reply["/api/reading"] = () => ({status:409, body:{ok:false,'
            ' produced:false, reason:"revision-changed"}});\n',
            '__press("reading-ask");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        drift = visible_text(drift_of(out["html"]))
        self.assertIn(KEEP_REFUSED, drift)
        self.assertNotIn("Analyzing drift", drift)
        self.assertIn('data-next-cockpit-action="reading-ask"', out["html"])

    STALE = (
        '__reply["/api/reading"] = () => { __s.annotation_goal = "Words another tab saved";'
        " __s.annotation_revision = 3; __s.annotation_revision_count = 3;"
        ' return {status:409, body:{ok:false, produced:false, reason:"revision-changed"}}; };\n'
    )

    def test_a_stale_analyze_is_said_once_by_the_region_and_by_no_status_paragraph(self) -> None:
        out = self.drive(
            SETTLED + DOM + self.STALE,
            '__press("reading-ask");\nawait __settle();\nawait __settle();\n'
            "renderNext();\nawait refreshNext();\nawait __settle();\nrenderNext();\n"
            f"console.log(JSON.stringify({{polite:{POLITE}, html:__els.app.innerHTML}}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(1, out["polite"].count(KEEP_REFUSED), out["polite"])
        tags = re.findall(r"<p\b[^>]*>(?=" + re.escape(KEEP_REFUSED) + ")", out["html"])
        self.assertEqual(1, len(tags), tags)
        self.assertNotIn("role=", tags[0])

    # Board reads counted from the refusal on, so the refresh it asks for is seen: the
    # fixture's board is one object, whose new words would draw without one, and every
    # click reads the board once of its own accord.
    READS = (
        "let __boardReads = 0;\nconst __readBase = __fetchImpl;\n"
        "__fetchImpl = async (url, init) => {\n"
        "  if(!(init && init.method === 'POST') && String(url).startsWith('/api/data'))"
        " __boardReads += 1;\n"
        "  return __readBase(url, init);\n};\n"
    )

    def test_a_stale_allow_reads_the_board_again_and_asks_for_the_allow_again(self) -> None:
        out = self.drive(
            SETTLED
            + '__dashboard.reading = {consent:false, reason:"consent-required"};\n'
            + self.STALE
            + self.READS,
            '__press("reading-ask");\nawait __settle();\n'
            "const __stale = __reply['/api/reading'];\nlet __atReply = null;\n"
            "__reply['/api/reading'] = body => { __atReply = __boardReads; return __stale(body); };\n"
            '__press("reading-allow");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts, reads:__boardReads - __atReply,"
            " html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(["/api/reading"], posted(out))
        self.assertGreaterEqual(out["reads"], 1)
        # The refresh drew the words the refusal was about, and the Allow step is gone.
        self.assertIn("Words another tab saved", out["html"])
        self.assertNotIn('data-next-cockpit-action="reading-allow"', out["html"])
        self.assertIn(KEEP_REFUSED, visible_text(drift_of(out["html"])))

    def test_the_goal_save_sends_its_revision_and_a_refusal_keeps_the_typed_words(self) -> None:
        typed = "Ship the retry queue with jitter"
        out = self.drive(
            SETTLED + '__reply["/api/annotate"] = () => ({status:200, body:{ok:true,'
            ' persisted:false, outcome:"refused"}});\n',
            f"__typeGoal({json.dumps(typed)});\n"
            '__press("held-save", "goal");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(["/api/annotate"], posted(out))
        self.assertEqual(typed, out["posts"][0]["body"]["goal"])
        self.assertEqual(2, out["posts"][0]["body"]["expected_revision"])
        intent = intent_of(out["html"])
        box = re.search(r'<textarea[^>]*data-next-cockpit-held-kind="goal"[^>]*>([^<]*)<', intent)
        assert box is not None
        self.assertEqual(typed, box.group(1))
        self.assertIn(SAVE_REFUSED, visible_text(intent))


@unittest.skipUnless(shutil.which("node"), "node not available")
class KeepShowsTheWholeDirectionTest(_DraftPage):
    """DRC-4732 item 3: the reader can read every direction Keep settles, or Keep is refused."""

    TWO_SENTENCES = "Correct the lane order. Then keep the old tests exactly as they are."

    def keep_twice(self, reply: str) -> dict[str, Any]:
        out = self.drive(
            reply,
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "const first = {posts:__posts.map(p => p.url), html:__els.app.innerHTML};\n"
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({first, posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        return out

    def test_a_direction_longer_than_its_summary_is_shown_whole_before_keep_settles(self) -> None:
        out = self.keep_twice(
            '__reply["/api/direction"] = body => ({status:200, body:{ok:true,'
            " fact_id:body.fact_id, text: body.fact_id === 'fo-b' ? "
            + json.dumps(self.TWO_SENTENCES)
            + ' : "Newest direction", clipped:false, fits:true}});\n'
        )
        first = out["first"]
        self.assertEqual(["/api/direction", "/api/direction"], first["posts"])
        drift = visible_text(drift_of(first["html"]))
        self.assertIn(self.TWO_SENTENCES, drift)
        self.assertIn("Newest direction", drift)
        self.assertIn(READ_FIRST, drift)
        # The second press settles on what is now on screen, and opens nothing again.
        self.assertEqual(["/api/direction", "/api/direction", "/api/reading"], posted(out))
        self.assertEqual(104, out["posts"][-1]["body"]["settle_through"])

    def test_the_first_press_moves_focus_to_the_whole_directions_and_scrolls_to_their_start(
        self,
    ) -> None:
        # The stub document parses lists too, so the list's focus key is reachable.
        dom = cockpit_tests.NextCockpitCompositionTest.FOCUS_DOM.replace(
            "(button|a|textarea)", "(button|a|textarea|ol)"
        ).replace(
            "focus(){ document.activeElement = this; },",
            "focus(options){ document.activeElement = this; this.focused = options || {}; },"
            " scrollIntoView(options){ this.scrolled = options; },",
        )
        out = self.drive(
            dom,
            "const keep = controls.find(c => c.dataset.nextCockpitAction === 'direction-keep');\n"
            "keep.focus();\n__fire('click', {preventDefault(){}, target:keep});\n"
            "await __settle();\nawait __settle();\n"
            "const active = document.activeElement;\n"
            "console.log(JSON.stringify({tag:active && active.tagName, key:active &&"
            " active.dataset.nextFocus, tabindex:active && active.getAttribute('tabindex'),"
            " scrolled:active && active.scrolled, focused:active && active.focused}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(
            ("OL", "direction-whole:claude:focus-1", "-1"),
            (out["tag"], out["key"], out["tabindex"]),
        )
        self.assertEqual({"block": "start"}, out["scrolled"])
        self.assertEqual({"preventScroll": True}, out["focused"])

    def test_a_direction_that_cannot_be_opened_refuses_keep(self) -> None:
        out = self.keep_twice(
            '__reply["/api/direction"] = body => body.fact_id === "fo-a"'
            ' ? {status:200, body:{ok:false, reason:"unavailable", why:"gone"}}'
            ' : {status:200, body:{ok:true, fact_id:body.fact_id, text:"Correct the lane order",'
            " clipped:false, fits:true}};\n"
        )
        self.assertNotIn("/api/reading", posted(out))
        self.assertNotIn("/api/annotate", posted(out))
        self.assertIn(UNOPENED, visible_text(drift_of(out["first"]["html"])))

    def test_a_sole_direction_its_summary_already_shows_whole_settles_in_one_press(self) -> None:
        # TYPED saved its goal at 103, so fo-a (104) is the one direction open, and the
        # question quotes its whole text.
        out = self.drive(
            TYPED,
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts, opened:__opened.map(p => p.body.fact_id),"
            " html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(["fo-a"], out["opened"])
        self.assertEqual(["/api/reading"], posted(out))
        self.assertNotIn(READ_FIRST, visible_text(out["html"]))

    def test_two_directions_are_drawn_whole_first_even_when_each_equals_its_summary(self) -> None:
        # The question quotes only the earliest, so the later one was never on screen.
        out = self.keep_twice("")
        first = out["first"]
        self.assertEqual([], first["posts"])
        drift = visible_text(drift_of(first["html"]))
        self.assertIn(READ_FIRST, drift)
        whole = re.search(r"<ol[^>]*data-next-cockpit-direction-whole[\s\S]*?</ol>", first["html"])
        assert whole is not None, "no whole-direction list drawn"
        self.assertIn(EARLIEST, visible_text(whole.group(0)))
        self.assertIn("Newest direction", visible_text(whole.group(0)))
        self.assertEqual(["/api/reading"], posted(out))
        self.assertEqual(104, out["posts"][-1]["body"]["settle_through"])

    def test_a_clipped_direction_is_drawn_with_the_owners_clipped_sentence(self) -> None:
        # Even where the opened start equals the quoted summary: the rest was never opened.
        out = self.drive(
            TYPED + '__reply["/api/direction"] = body => ({status:200, body:{ok:true,'
            ' fact_id:body.fact_id, text:"Newest direction", clipped:true, fits:false}});\n',
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(["/api/direction"], posted(out))
        whole = re.search(r"<ol[^>]*data-next-cockpit-direction-whole[\s\S]*?</ol>", out["html"])
        assert whole is not None, "no whole-direction list drawn"
        self.assertIn(CLIPPED, visible_text(whole.group(0)))
        self.assertIn(READ_FIRST, visible_text(drift_of(out["html"])))

    ARRIVES = (
        "__semantic.facts.unshift({fact_id:'fo-c', at:106, type:'user_message',"
        " summary:'Also delete the whole tests folder.',"
        " source_session:{harness:'claude', sid:'focus-1'},"
        " evidence:{source:'root transcript', confidence:'exact'}});\n"
        "await refreshNext();\nawait __settle();\nawait __settle();\n"
    )

    def test_a_direction_arriving_between_presses_is_drawn_and_not_settled(self) -> None:
        out = self.drive(
            "",
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            + self.ARRIVES
            + '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "const second = {posts:__posts.map(p => p.url), html:__els.app.innerHTML,"
            " opened:__opened.map(p => p.body.fact_id)};\n"
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({second, posts:__posts}));",
        )
        assert isinstance(out, dict)
        second = out["second"]
        self.assertEqual([], second["posts"])
        self.assertEqual(["fo-b", "fo-a", "fo-c"], second["opened"])
        whole = re.search(r"<ol[^>]*data-next-cockpit-direction-whole[\s\S]*?</ol>", second["html"])
        assert whole is not None, "no whole-direction list drawn"
        self.assertIn("Also delete the whole tests folder.", visible_text(whole.group(0)))
        self.assertIn(READ_FIRST, visible_text(drift_of(second["html"])))
        # The third press settles what the second drew, the new direction included.
        self.assertEqual(["/api/reading"], posted(out))
        self.assertEqual(106, out["posts"][-1]["body"]["settle_through"])

    def test_the_second_press_names_the_revision_the_list_was_drawn_with(self) -> None:
        out = self.drive(
            "",
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "__s.annotation_revision = 5;\nawait refreshNext();\nawait __settle();\n"
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(["/api/reading"], posted(out))
        self.assertEqual(0, out["posts"][-1]["body"]["expected_revision"])

    def test_a_refused_keep_draws_the_directions_again_against_the_new_revision(self) -> None:
        out = self.drive(
            '__reply["/api/reading"] = () => ({status:422, body:{ok:false, produced:false,'
            ' adoption_refused:true, settled:"refused"}});\n',
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "__s.annotation_revision = 5;\nawait refreshNext();\nawait __settle();\n"
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "const refused = __posts.length;\n"
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({refused, posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(1, out["refused"])
        # The press after the refusal draws again rather than repeating the stale revision.
        self.assertEqual(["/api/reading"], posted(out))
        self.assertIn(READ_FIRST, visible_text(drift_of(out["html"])))


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheQuestionEndsWithOneMarkTest(_DraftPage):
    """DRC-4736 item 1: no outer mark after a quote that ends in its own."""

    def summary(self, fact_id: str, text: str) -> str:
        return (
            f"__semantic.facts.find(f => f.fact_id === {json.dumps(fact_id)}).summary = "
            f"{json.dumps(text)};\n"
        )

    def test_a_quoted_direction_ending_in_a_mark_gets_no_second_one(self) -> None:
        for said in ("Also log each move to the console.", "Should it log?", "Log it all…"):
            with self.subTest(said=said):
                drift = visible_text(drift_of(self.html(TYPED + self.summary("fo-a", said))))
                self.assertIn(f'You gave a later direction at #3: "{said}"', drift)
                self.assertNotIn(f'"{said}".', drift)

    def test_a_mark_before_a_closing_quote_or_bracket_gets_no_second_one(self) -> None:
        for said in (
            "Ship it now!",
            'Say "done."',
            "Keep it (see tests.)",
            "\u201call green.\u201d",
        ):
            with self.subTest(said=said):
                drift = visible_text(drift_of(self.html(TYPED + self.summary("fo-a", said))))
                self.assertIn(f'You gave a later direction at #3: "{said}"', drift)
                self.assertNotIn(f'"{said}".', drift)

    def test_a_trailing_space_is_trimmed_before_quoting(self) -> None:
        drift = visible_text(drift_of(self.html(TYPED + self.summary("fo-a", "Log it all. "))))
        self.assertIn('You gave a later direction at #3: "Log it all."', drift)
        self.assertNotIn('"Log it all. "', drift)
        self.assertNotIn('"Log it all.".', drift)

    def test_the_plural_form_gets_no_second_mark_either(self) -> None:
        said = "Should the lanes swap?"
        drift = visible_text(drift_of(self.html(self.summary("fo-b", said))))
        self.assertIn(f'the earliest at #1: "{said}"', drift)
        self.assertNotIn(f'"{said}".', drift)

    def test_a_quote_with_no_mark_of_its_own_still_ends_the_sentence(self) -> None:
        drift = visible_text(drift_of(self.html()))
        self.assertIn(f'the earliest at #1: "{EARLIEST}".', drift)


class TheWholeDirectionListWrapsAlikeTest(unittest.TestCase):
    """A11y review F4: a long direction's number stays beside its text, as a short one's does."""

    def rule(self, selector: str) -> str:
        match = re.search(re.escape(selector) + r"\{([^}]*)\}", NEXT_STYLES)
        assert match is not None, f"no rule for {selector}"
        return match.group(1)

    def test_each_item_is_a_two_column_grid_that_never_wraps_the_number_away(self) -> None:
        item = self.rule(".next-cockpit-direction-whole-item")
        self.assertIn("display:grid", item)
        self.assertIn("grid-template-columns:auto minmax(0,1fr)", item)
        self.assertNotIn("flex-wrap", item)
        self.assertIn("grid-column:2", self.rule(".next-cockpit-direction-whole-text"))
        self.assertIn(
            "grid-column:2",
            self.rule(".next-cockpit-direction-whole-item>.next-cockpit-held-full"),
        )


class TheIntentHeadingUsesThePagesRingTest(unittest.TestCase):
    """DRC-4736 item 2."""

    def test_keyboard_focus_on_the_intent_heading_draws_the_accent_ring(self) -> None:
        rule = re.search(r"#next-session-intent-heading:focus-visible\{([^}]*)\}", NEXT_STYLES)
        assert rule is not None, "no focus rule for the Intent heading"
        self.assertIn("outline:2px solid var(--accent)", rule.group(1))


@unittest.skipUnless(shutil.which("node"), "node not available")
class AnAnalysisIsAnnouncedOnceTest(_DraftPage):
    """DRC-4726 and DRC-4736 item 3: the box carries no role, and the persistent polite region
    carries "Analyzing drift" once per job and its outcome once when it ends."""

    RUN = (
        '__press("reading-ask");\nawait __settle();\nawait __settle();\n'
        "const during = __els.app.innerHTML;\n"
        "renderNext();\nawait refreshNext();\nawait __settle();\nrenderNext();\n"
        '__dashboard.reading_jobs = {"claude:focus-1": {...JOB, phase:"waiting", phase_at:107}};\n'
        "await refreshNext();\nawait __settle();\nrenderNext();\n"
        f"const started = [...{POLITE}];\n"
    )
    AFTER = (
        "await refreshNext();\nawait __settle();\nrenderNext();\n"
        f"const ended = [...{POLITE}];\n"
        "renderNext();\nawait refreshNext();\nawait __settle();\nrenderNext();\n"
        f"console.log(JSON.stringify({{during, started, ended, polite:{POLITE}}}));"
    )

    def run_job(self, end: str) -> dict[str, Any]:
        out = self.drive(SETTLED + DOM + JOB, self.RUN + end + self.AFTER)
        assert isinstance(out, dict)
        return out

    def test_the_running_box_is_not_a_status_region(self) -> None:
        out = self.run_job("__dashboard.reading_jobs = {};\n")
        box = re.search(r'<div class="next-cockpit-reading-job"[^>]*>', out["during"])
        assert box is not None, "no analyzing box drawn"
        self.assertNotIn("role=", box.group(0))

    def test_one_press_announces_analyzing_drift_once(self) -> None:
        out = self.run_job("__dashboard.reading_jobs = {};\n")
        self.assertEqual(1, out["started"].count("Analyzing drift"), out["started"])
        self.assertEqual(1, out["polite"].count("Analyzing drift"), out["polite"])

    def test_a_stored_reading_is_announced_once_when_the_job_ends(self) -> None:
        out = self.run_job(
            "__dashboard.reading_jobs = {};\n"
            "__s.annotation_assessment = {read_at:108, revision_read:2, criteria:{goal:"
            '{result:"not verifiable from available evidence", cites:[]}}};\n'
        )
        self.assertNotIn(FINISHED, out["started"])
        self.assertEqual(1, out["ended"].count(FINISHED), out["ended"])
        self.assertEqual(1, out["polite"].count(FINISHED), out["polite"])

    def test_a_withheld_outcome_is_announced_in_the_servers_own_words_once(self) -> None:
        said = reading.WITHHELD[reading.WITHHELD_CANCELLED]
        out = self.run_job(
            f"__dashboard.reading_jobs = {{}};\n__s.annotation_reading_withheld = {json.dumps(said)};\n"
        )
        self.assertEqual(1, out["polite"].count(said), out["polite"])
        self.assertNotIn(FINISHED, out["polite"])

    def test_an_end_that_stored_nothing_new_announces_no_reading(self) -> None:
        """A job whose outcome write left the old reading in place is not a finished reading."""
        before = (
            "__s.annotation_assessment = {read_at:90, revision_read:2, criteria:{goal:"
            '{result:"not verifiable from available evidence", cites:[]}}};\n'
        )
        out = self.drive(
            SETTLED + before + DOM + JOB, self.RUN + "__dashboard.reading_jobs = {};\n" + self.AFTER
        )
        assert isinstance(out, dict)
        self.assertEqual(1, out["polite"].count("Analyzing drift"), out["polite"])
        self.assertNotIn(FINISHED, out["polite"])

    def test_a_job_already_running_at_load_is_not_announced_until_it_ends(self) -> None:
        said = reading.WITHHELD[reading.WITHHELD_CANCELLED]
        out = self.drive(
            SETTLED + JOB + '__dashboard.reading_jobs = {"claude:focus-1": JOB};\n' + DOM,
            # A reload onto the session page: a tab that has seen nothing, whose
            # first board already draws the running job.
            "nextCockpitReadingJobsSeen.clear();\nnextCockpitReadingJobsPrimed = false;\n"
            "renderNext();\n"
            "const drawnAtLoad = __els.app.innerHTML.includes('data-next-analyzing=\"j1\"');\n"
            "await refreshNext();\nawait __settle();\nrenderNext();\n"
            f"const loaded = [...{POLITE}];\n"
            f"__dashboard.reading_jobs = {{}};\n__s.annotation_reading_withheld = {json.dumps(said)};\n"
            "await refreshNext();\nawait __settle();\nrenderNext();\n"
            f"console.log(JSON.stringify({{drawnAtLoad, loaded, polite:{POLITE}}}));",
        )
        assert isinstance(out, dict)
        self.assertTrue(out["drawnAtLoad"], "the job was not drawn on the first board")
        self.assertEqual([], [text for text in out["loaded"] if text])
        self.assertEqual(1, out["polite"].count(said), out["polite"])

    def test_a_job_that_ends_while_the_reader_is_on_another_page_is_not_announced(self) -> None:
        said = reading.WITHHELD[reading.WITHHELD_CANCELLED]
        out = self.run_job(
            'navigateNext({view:"sessions"});\nawait __settle();\n'
            f"__dashboard.reading_jobs = {{}};\n__s.annotation_reading_withheld = {json.dumps(said)};\n"
        )
        self.assertEqual(1, out["polite"].count("Analyzing drift"), out["polite"])
        self.assertNotIn(said, out["polite"])

    REGION = 'region("next-cockpit-cue-status").textContent'

    def test_a_job_that_ends_unannounced_leaves_no_analyzing_drift_in_the_region(self) -> None:
        said = reading.WITHHELD[reading.WITHHELD_CANCELLED]
        cases = {
            "ended while away": 'navigateNext({view:"sessions"});\nawait __settle();\n'
            f"__dashboard.reading_jobs = {{}};\n__s.annotation_reading_withheld = {json.dumps(said)};\n"
            "await refreshNext();\nawait __settle();\n"
            f"{ROUTE}\nawait __settle();\nrenderNext();\n",
            "ended with nothing new": "__dashboard.reading_jobs = {};\n"
            "await refreshNext();\nawait __settle();\nrenderNext();\n",
        }
        for name, end in cases.items():
            with self.subTest(case=name):
                out = self.drive(
                    SETTLED + DOM + JOB,
                    self.RUN + end + f"console.log(JSON.stringify({self.REGION}));",
                )
                self.assertEqual("", out)

    def test_two_jobs_in_a_row_each_announce_their_start_and_their_end(self) -> None:
        said = reading.WITHHELD[reading.WITHHELD_CANCELLED]
        second = (
            f"__dashboard.reading_jobs = {{}};\n__s.annotation_reading_withheld = {json.dumps(said)};\n"
            "await refreshNext();\nawait __settle();\nrenderNext();\n"
            'const JOB2 = {...JOB, id:"j2"};\n'
            '__reply["/api/reading"] = () => { __dashboard.reading_jobs = {"claude:focus-1": JOB2};'
            " return {status:202, body:{ok:true, job:JOB2}}; };\n"
            '__press("reading-ask");\nawait __settle();\nawait __settle();\n'
            "await refreshNext();\nawait __settle();\nrenderNext();\n"
            "__dashboard.reading_jobs = {};\n"
            "await refreshNext();\nawait __settle();\nrenderNext();\n"
        )
        out = self.drive(
            SETTLED + DOM + JOB,
            self.RUN + second + f"console.log(JSON.stringify({POLITE}));",
        )
        assert isinstance(out, list)
        self.assertEqual(2, out.count("Analyzing drift"), out)
        self.assertEqual(2, out.count(said), out)

    def test_an_outcome_the_region_already_holds_is_emptied_before_it_is_said_again(self) -> None:
        # A second job another tab started while the reader was away, ending as the first did:
        # no start is said in between, so the region still holds the first job's outcome.
        said = reading.WITHHELD[reading.WITHHELD_CANCELLED]
        second = (
            f"__dashboard.reading_jobs = {{}};\n__s.annotation_reading_withheld = {json.dumps(said)};\n"
            "await refreshNext();\nawait __settle();\nrenderNext();\n"
            'navigateNext({view:"sessions"});\nawait __settle();\n'
            '__dashboard.reading_jobs = {"claude:focus-1": {...JOB, id:"j2"}};\n'
            "await refreshNext();\nawait __settle();\n"
            f"{ROUTE}\nawait __settle();\nrenderNext();\n"
            "__dashboard.reading_jobs = {};\n"
            "await refreshNext();\nawait __settle();\nrenderNext();\n"
        )
        out = self.drive(
            SETTLED + DOM + JOB,
            self.RUN + second + f"console.log(JSON.stringify({POLITE}));",
        )
        assert isinstance(out, list)
        self.assertEqual(1, out.count("Analyzing drift"), out)
        self.assertEqual(2, out.count(said), out)
        last = len(out) - 1 - out[::-1].index(said)
        self.assertEqual("", out[last - 1], out)

    def test_a_reload_after_the_job_ended_announces_nothing(self) -> None:
        said = reading.WITHHELD[reading.WITHHELD_CANCELLED]
        out = self.drive(
            SETTLED + DOM + f"__s.annotation_reading_withheld = {json.dumps(said)};\n"
            "__s.annotation_assessment = {read_at:108, revision_read:2, criteria:{}};\n",
            f"renderNext();\nawait refreshNext();\nawait __settle();\nconsole.log(JSON.stringify({POLITE}));",
        )
        assert isinstance(out, list)
        self.assertNotIn(said, out)
        self.assertNotIn(FINISHED, out)
        self.assertNotIn("Analyzing drift", out)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheRecordColumnNamesWhoseWorkIsReadTest(_DraftPage):
    """DRC-4734: the record column's line names Claude Code and Pi."""

    def test_the_rendered_record_column_names_the_two_harnesses(self) -> None:
        html = self.html(SETTLED)
        self.assertIn(RECORD_LINE, visible_text(html))

    def test_every_harness_line_opens_with_the_owners_sentence(self) -> None:
        out = self.drive(
            SETTLED,
            "console.log(JSON.stringify(['claude', 'pi', 'codex', 'gemini'].map("
            "h => nextCockpitWorkEvidenceLimit(h))));",
        )
        assert isinstance(out, list)
        for line in out:
            with self.subTest(line=line):
                self.assertTrue(line.startswith(RECORD_LINE + " "), line)
        self.assertIn("Codex publishes no demonstrated work results", out[2])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePageJudgesAPiCheckAsTheServerDoesTest(NextPageJsHarness):
    """DRC-4734: `nextReadingCheckSupports` against `reading.check_supports`, over facts the
    server's own Pi fixture publishes and the subjectless rows an older build stored."""

    FIXTURE = cockpit_tests.NextCockpitCompositionTest.FIXTURE
    SID = records_tests.PiRecord.SID
    SCENARIOS: tuple[tuple[tuple[str, str, bool | None, str], ...], ...] = (
        (("bash", "pytest -q", False, "4 passed in 1s"),),
        (("bash", "pytest -q", True, records_tests.exited("2 failed, 3 passed in 0.12s", 1)),),
        (("bash", "pytest -q -k nomatch", False, "0 passed in 0.01s"),),
        (("bash", "pytest -q", False, "4 passed in 1s"), ("edit", "a.py", None, "")),
        (("bash", "pytest -q && sed -i s/a/b/ a.py", False, "5 passed in 0.1s"),),
        (("bash", "ruff check --fix .", False, "All checks passed!"),),
        (("bash", "pytest -q", False, "4 passed in 1s"), ("bash", "rm -rf build", False, "")),
    )

    def pi_facts(self) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for number, steps in enumerate(self.SCENARIOS):
            record = records_tests.APiValidationRunIsReadUnderDec23(
                "test_a_passing_run_is_a_pass_with_its_count"
            )
            record.setUp()
            self.addCleanup(record.doCleanups)
            for kind, what, is_error, text in steps:
                if kind == "edit":
                    record.tool("edit", {"path": what, "oldText": "a", "newText": "b"})
                else:
                    record.bash(what, is_error=is_error, text=text)
            for event in record.checks():
                fact = project_context._semantic_fact_from_event(event, "outcome", "result", "")
                fact["source_session"] = {"harness": "pi", "sid": self.SID}
                fact["fact_id"] = f"s{number}-{fact['fact_id']}"
                facts.append(fact)
        older = records_tests.APiCheckNeverComesBackFromSemanticHistory._old_row
        # The fixture method reads only `now` and `SID` from its instance.
        holder: Any = SimpleNamespace(now=records_tests.NOW, SID=self.SID)
        for fact_id, source in (
            ("fact:old-echo", "Pi bash tool call and paired successful result"),
            ("fact:old-pass", "Pi bash tool call and paired result"),
        ):
            facts.append(older(holder, fact_id, source, 400)["fact"])
        # And the two rows that are not subjectless Pi checks, so the page's test is held to
        # both halves of it: another type from a Pi bash call, and a result from a source
        # that names a Pi bash call without starting with it. Each passes through.
        other_type = older(
            holder, "fact:old-other-type", "Pi bash tool call and paired result", 400
        )
        other_type["fact"]["type"] = "agent_message"
        not_prefixed = older(holder, "fact:old-not-prefixed", "After a Pi bash tool call", 400)
        facts.extend([other_type["fact"], not_prefixed["fact"]])
        return facts

    def test_every_pi_fact_carries_a_verdict_on_the_page_exactly_when_it_does_on_the_server(
        self,
    ) -> None:
        facts = self.pi_facts()
        ledger = {entry["id"]: entry for entry in reading.build_ledger(facts, "pi", self.SID)}
        self.assertTrue(any(fact.get("changed_after") for fact in facts), "no changed_after case")
        self.assertTrue(any(fact.get("before_last_change") for fact in facts), "no aged case")
        verdicts = (
            reading.RESULT_CONSISTENT,
            reading.RESULT_DEPARTURE,
            reading.RESULT_UNVERIFIABLE,
        )
        windows = (0.0, records_tests.AT_EPOCH, records_tests.NOW)
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            f"const facts = {json.dumps(facts)};\n"
            f"const entries = nextCockpitWorkEntries({{harness:'pi', sid:{json.dumps(self.SID)}}},"
            " {facts});\n"
            f"const verdicts = {json.dumps(verdicts)};\nconst windows = {json.dumps(windows)};\n"
            "console.log(JSON.stringify(Object.fromEntries(entries.map(e => [e.id,"
            " verdicts.map(v => windows.map(w => nextReadingCheckSupports(e, v, w)))]))));",
            storage_prelude({}) + self.FIXTURE,
        )
        assert isinstance(out, dict)
        server = {
            fact_id: [
                [reading.check_supports(entry, verdict, window) for window in windows]
                for verdict in verdicts
            ]
            for fact_id, entry in ledger.items()
        }
        self.assertEqual(sorted(server), sorted(out))
        self.assertEqual(server, out)
        for fact_id in ("fact:old-other-type", "fact:old-not-prefixed"):
            self.assertIn(fact_id, server)
            self.assertIn(True, [value for row in server[fact_id] for value in row], fact_id)
        flat = [value for rows in server.values() for row in rows for value in row]
        self.assertIn(True, flat)
        self.assertIn(False, flat)


if __name__ == "__main__":
    unittest.main()
