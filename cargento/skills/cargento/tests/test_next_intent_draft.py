"""Arrive with your goal drafted, and answer a later direction before the press (DRC-4682).

The page layer of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
items 2 and 4, built to the owner's decisions of 2026-09-27: a goal-less Claude Code or Codex
session drafts its first prompt (its latest where no first is published), unsaved until Looks
right, an edit, or the press; an edited box refuses Analyze; no level or pill over a draft; every
unsettled later direction is drawn at its own number; and the question before the press replaces
the old "Conflict to settle" block, with Keep settling (and carrying Allow) and Add opening the
direction's whole text for review before saving it as an outcome line.

Every assertion is on what a reader sees or what the page sends.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from typing import Any

from cargento_runtime import annotations as annotation_store

from . import test_next_cockpit as cockpit_tests
from .next_harness import NEXT_STYLES, NextPageJsHarness, storage_prelude

FIXTURE = cockpit_tests.NextCockpitCompositionTest.FIXTURE
FIRST = "Build the retry queue for failed events"
LATEST = "Newest direction"
EARLIEST = "Correct the lane order"
FULL = "An expected outcome holds six lines. Replace or merge a line to add another."
MEASURED = "Drift is measured against these. Edit anything that is off."
EDITED = "Save your intent, or undo your edit, to analyze drift."
ADD_EDITED = "Save your intent, or undo your edit, to add this direction."
KEEP_ALLOW = (
    "Kept your intent and settled the direction. Press Allow and analyze to send it for a reading."
)
KEEP_REFUSED = (
    "Nothing was settled and no analysis was started: your intent changed since this page "
    "was drawn, or the store refused the mark. Review your intent and press again."
)
GOAL_KEY = "held:claude:focus-1:goal"
LINES_KEY = "held:claude:focus-1:lines"

# A goal-less Claude Code session: its first prompt at 99, and two directions of the reader's
# after it in the record (fo-b at 102 and fo-a at 104), numbered #1 and #3 with the dispatch
# between them at #2.
DRAFT = (
    """
__dashboard.annotate = true;
__dashboard.annotate_cap = 240;
__dashboard.reading_check = """
    + json.dumps(annotation_store.ABSTENTION_CHECK)
    + """;
__dashboard.reading = {consent:true, reason:"", used:0, limit:12, tool_output:{codex:["OpenAI"]}};
const __s = __dashboard.sessions[0];
__s.harness = "claude";
__s.first_prompt = """
    + json.dumps(FIRST)
    + """;
__s.first_prompt_at = 99;
__s.instruction = {label:"asked", text:"Newest direction", at:104};
__s.annotation_goal = "";
__s.annotation_goal_why = "No goal typed for this session.";
__s.annotation_lines_why = "No expected outcome typed.";
for(let k = 1; k <= 6; k += 1){ __s[`annotation_line_${k}`] = ""; }
__s.annotation_revision = 0;
__s.annotation_revision_count = 0;
for(const fact of __semantic.facts){
  if(fact.source_session) fact.source_session = {harness:"claude", sid:"focus-1"};
}
"""
)

# Keep settles in one press only a sole direction whose whole text is the summary the
# question quotes; of two, the first press draws both whole (DRC-4732, wire review F1). The
# tests of what Keep does once it settles keep fo-a alone, so one press still settles.
SOLE = "__semantic.facts = __semantic.facts.filter(f => f.fact_id !== 'fo-b');\n"

TYPED = """
__s.annotation_goal = "Ship the retry queue";
__s.annotation_goal_why = "";
__s.annotation_revision = 2;
__s.annotation_revision_count = 2;
__s.annotation_at = 100;
__s.annotation_goal_saved_at = 103;
"""

# What the store publishes after a Keep that adopted the draft and settled
# through fo-a: the fixture's server does not move on its own.
SETTLED_BY_KEEP = """
const SETTLED_BY_KEEP = {annotation_goal:__s.first_prompt, annotation_goal_why:"",
  annotation_goal_source:"first-prompt", annotation_goal_source_at:99, annotation_revision:1,
  annotation_revision_count:1, annotation_at:105, annotation_settled_through:104,
  annotation_settled_at:105};
"""

CLICK = (
    SETTLED_BY_KEEP
    + """
const __press = (action, arg = "") => __fire("click", {preventDefault(){},
  target:{dataset:{nextCockpitAction:action, arg:String(arg)}, closest(){ return this; }}});
const __typeGoal = value => __fire("input", {target:{value,
  dataset:{nextCockpitHeldKey:"held:claude:focus-1:goal"},
  closest(selector){ return selector === "[data-next-cockpit-held-key]" ? this : null; }}});
const __typeDirection = value => __fire("input", {target:{value,
  dataset:{nextCockpitDirectionKey:"claude:focus-1"},
  closest(selector){ return selector === "[data-next-cockpit-direction-key]" ? this : null; }}});
const __argOf = action => (__els.app.innerHTML.match(new RegExp(
  `data-next-cockpit-action="${action}" data-arg="([^"]*)"`)) || [])[1];
const __renders = [];
const __renderNext = renderNext;
renderNext = (...args) => { __renders.push(args.length ? args[0] : undefined); return __renderNext(...args); };
let __posts = [];
// Keep opens every direction it settles (DRC-4732). Where a test gives no
// reply for that route, each opens as its own summary, so the whole text is
// already on screen and one press settles; those opens are kept in `__opened`
// rather than `__posts`, which then holds what the press itself sent.
let __opened = [];
const __reply = {};
const __replyByDefault = {"/api/direction": body => {
  const fact = __semantic.facts.find(f => f.fact_id === body.fact_id);
  return {status:200, body:{ok:true, fact_id:body.fact_id, text:fact ? fact.summary : "",
    clipped:false, fits:true}};
}};
const __upstream = __fetchImpl;
__fetchImpl = async (url, init) => {
  if(!init || init.method !== "POST" || String(url).startsWith("/api/tripwire")){
    return __upstream(url, init);
  }
  const body = JSON.parse(init.body);
  (__reply[String(url)] || !__replyByDefault[String(url)] ? __posts : __opened)
    .push({url:String(url), body});
  const made = (__reply[String(url)] || __replyByDefault[String(url)] ||
    (() => ({ok:true, status:200, body:{ok:true}})))(body);
  return {ok:made.status < 400, status:made.status, json:async () => made.body};
};
"""
)

ROUTE = 'navigateNext({view:"session", project:"cargento", harness:"claude", session:"focus-1"});'
PRIMARY = re.compile(r"<button\b[^>]*next-action--primary[^>]*>([\s\S]*?)</button>")


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


def aside_of(html: str) -> str:
    start = html.index("<aside")
    return html[start : html.index("</aside>", start)]


def intent_of(html: str) -> str:
    aside = aside_of(html)
    return aside[: aside.index('id="next-session-drift-heading"')]


def drift_of(html: str) -> str:
    aside = aside_of(html)
    return aside[aside.index('id="next-session-drift-heading"') :]


class _DraftPage(NextPageJsHarness):
    def drive(self, setup: str = "", after: str = "", *, draft: str = DRAFT) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + draft
            + CLICK
            + setup
            + "await refreshNext();\nawait __settle();\n"
            + ROUTE
            + "\nawait __settle();\nawait __settle();\n"
            + (after or "console.log(JSON.stringify(__els.app.innerHTML));"),
            storage_prelude({}) + FIXTURE,
        )

    def html(self, setup: str = "", after: str = "") -> str:
        out = self.drive(setup, after)
        assert isinstance(out, str)
        return out


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheGoalArrivesDraftedTest(_DraftPage):
    def test_a_goalless_session_arrives_with_its_first_prompt_drafted_and_unsaved(self) -> None:
        html = self.html()
        intent = intent_of(html)
        box = re.search(r'<textarea[^>]*data-next-cockpit-held-kind="goal"[^>]*>([^<]*)<', intent)
        assert box is not None
        self.assertEqual(FIRST, box.group(1))
        text = visible_text(intent)
        self.assertIn("from your prompt", text)
        self.assertNotIn("from your prompt · latest", text)
        self.assertIn("Looks right", text)
        self.assertIn(MEASURED, text)
        self.assertIn("No revision saved yet", text)
        self.assertNotIn("Confirmed", text)
        # The draft's tint marks the field, and the design line replaces the lede.
        self.assertIn("data-next-cockpit-drafted", intent)
        self.assertNotIn("Choose a goal or use your prompt", text)
        # Unsaved: saving is not offered over the untouched draft; Looks right is.
        save = re.search(
            r'<button[^>]*data-next-cockpit-action="held-save" data-arg="goal"[^>]*>', intent
        )
        assert save is not None
        self.assertRegex(save.group(0), r"aria-disabled|hidden")

    def test_a_clipped_first_prompt_is_marked_as_an_excerpt(self) -> None:
        html = self.html('__s.first_prompt = "Build the retry queue and then…";\n')
        self.assertIn("Shown excerpt only.", visible_text(intent_of(html)))

    def test_with_no_first_prompt_the_latest_is_drafted_and_marked_latest(self) -> None:
        html = self.html('__s.first_prompt = ""; __s.first_prompt_at = null;\n')
        intent = intent_of(html)
        box = re.search(r'<textarea[^>]*data-next-cockpit-held-kind="goal"[^>]*>([^<]*)<', intent)
        assert box is not None
        self.assertEqual(LATEST, box.group(1))
        self.assertIn("from your prompt · latest", visible_text(intent))

    def test_use_a_prompt_still_offers_the_latest_and_no_longer_the_first(self) -> None:
        text = visible_text(intent_of(self.html()))
        self.assertIn("Use a prompt", text)
        self.assertIn("Your latest prompt", text)
        self.assertNotIn("Your first prompt", text)

    def test_no_draft_on_a_harness_that_publishes_no_prompt(self) -> None:
        html = self.html('__s.harness = "pi"; ' + ROUTE.replace("claude", "pi") + "\n")
        self.assertNotIn("data-next-cockpit-drafted", html)

    def test_looks_right_adopts_the_draft_with_its_revision(self) -> None:
        out = self.drive(
            after='__press("draft-confirm");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts));"
        )
        assert isinstance(out, list)
        self.assertEqual(1, len(out))
        self.assertEqual("/api/annotate", out[0]["url"])
        self.assertEqual(
            {
                "harness": "claude",
                "sid": "focus-1",
                "adopt": "first-prompt",
                "expected_prompt": FIRST,
                "expected_prompt_at": 99,
                "expected_revision": 0,
            },
            out[0]["body"],
        )

    def test_looks_right_returns_focus_to_the_saved_goal(self) -> None:
        out = self.drive(
            cockpit_tests.NextCockpitCompositionTest.FOCUS_DOM,
            """
const confirm = controls.find(control => control.dataset.nextCockpitAction === "draft-confirm");
confirm.focus();
__reply["/api/annotate"] = () => {
  Object.assign(__s, {annotation_goal:__s.first_prompt,
    annotation_goal_source:"first-prompt", annotation_goal_source_at:99,
    annotation_revision:1, annotation_revision_count:1});
  return {status:200, body:{ok:true,persisted:true}};
};
__press("draft-confirm");
await __settle(); await __settle(); await __settle();
console.log(JSON.stringify({
  confirmed: !controls.some(control => control.dataset.nextCockpitAction === "draft-confirm"),
  focus:document.activeElement?.dataset.nextFocus || null,
  tag:document.activeElement?.tagName || null,
}));
""",
        )
        assert isinstance(out, dict)
        self.assertTrue(out["confirmed"])
        self.assertEqual(GOAL_KEY, out["focus"])
        self.assertEqual("TEXTAREA", out["tag"])

    def test_save_with_the_box_back_at_the_draft_adopts_rather_than_typing(self) -> None:
        out = self.drive(
            after=f"__typeGoal({json.dumps(FIRST + 'x')});\n"
            f"__typeGoal({json.dumps(FIRST)});\n"
            '__press("held-save", "goal");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts));"
        )
        assert isinstance(out, list)
        self.assertEqual(1, len(out))
        self.assertEqual("first-prompt", out[0]["body"].get("adopt"))
        self.assertNotIn("goal", out[0]["body"])

    def test_analyze_over_the_draft_adopts_the_first_prompt(self) -> None:
        out = self.drive(
            "__semantic.facts = __semantic.facts.filter(f => f.type !== 'user_message');\n",
            '__press("reading-ask");\nawait __settle();\nconsole.log(JSON.stringify(__posts));',
        )
        assert isinstance(out, list)
        self.assertEqual("/api/reading", out[0]["url"])
        self.assertEqual("first-prompt", out[0]["body"]["adopt"])
        self.assertEqual(FIRST, out[0]["body"]["expected_prompt"])
        self.assertEqual(99, out[0]["body"]["expected_prompt_at"])

    def test_an_edited_unsaved_box_takes_the_marks_away_and_refuses_analyze(self) -> None:
        out = self.drive(
            "__semantic.facts = __semantic.facts.filter(f => f.type !== 'user_message');\n",
            '__typeGoal("Something else entirely");\nrenderNext();\n'
            'const before = __els.app.innerHTML;\n__press("reading-ask");\nawait __settle();\n'
            "console.log(JSON.stringify({before, after:__els.app.innerHTML, posts:__posts}));",
        )
        assert isinstance(out, dict)
        self.assertEqual([], out["posts"])
        intent = visible_text(intent_of(out["before"]))
        self.assertNotIn("Looks right", intent)
        self.assertNotIn("from your prompt", intent)
        self.assertNotIn("data-next-cockpit-drafted", intent_of(out["before"]))
        self.assertIn(EDITED, visible_text(drift_of(out["after"])))

    def test_a_saved_goal_reads_confirmed_with_no_check_mark(self) -> None:
        html = self.html(TYPED)
        intent = intent_of(html)
        self.assertIn("Confirmed", visible_text(intent))
        self.assertNotIn("<svg", intent)
        self.assertNotIn("✓", intent)
        self.assertNotIn("Looks right", visible_text(intent))
        self.assertNotIn(MEASURED, visible_text(intent))


@unittest.skipUnless(shutil.which("node"), "node not available")
class NoLevelOverADraftTest(_DraftPage):
    """The guard DRC-4695 and DRC-4696 consult, proved able to fail with a stubbed level."""

    STUB = 'nextDriftEstimate = () => ({label:"Stubbed level"});\n'

    def test_an_unsaved_draft_shows_no_level_and_no_pill(self) -> None:
        drafted = self.html(
            after=self.STUB + "renderNext();\nconsole.log(JSON.stringify(__els.app.innerHTML));"
        )
        self.assertNotIn("data-next-drift-level", drafted)
        self.assertNotIn("Stubbed level", drafted)
        self.assertNotIn("data-next-drift-pill", drafted)
        saved = self.html(
            TYPED, self.STUB + "renderNext();\nconsole.log(JSON.stringify(__els.app.innerHTML));"
        )
        self.assertIn("Stubbed level", saved)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheQuestionBeforeThePressTest(_DraftPage):
    def test_the_question_replaces_the_conflict_block_and_names_a_drawn_number(self) -> None:
        html = self.html()
        drift = visible_text(drift_of(html))
        self.assertIn(
            f'You gave 2 later directions since your first prompt, the earliest at #1: "{EARLIEST}".',
            drift,
        )
        self.assertNotIn("CONFLICT TO SETTLE", html)
        self.assertNotIn("The baseline still applies", html)
        self.assertNotIn("Retype the baseline", html)
        primaries = PRIMARY.findall(html)
        self.assertEqual(
            ["Keep my intent and analyze"], [visible_text(p).strip() for p in primaries]
        )
        self.assertIn("Add it to my intent", drift)
        self.assertNotIn('data-next-cockpit-action="reading-ask"', html)
        # The number named is a drawn row, and the direction Add opens (owner, 2026-09-28).
        self.assertRegex(html, r'data-next-entry="1" data-next-entry-id="fo-b"')
        add = re.search(r'data-next-cockpit-action="direction-add" data-arg="([^"]*)"', html)
        assert add is not None
        self.assertEqual("fo-b", add.group(1))

    def test_a_typed_goal_floors_on_its_goal_save_time_not_its_revision_time(self) -> None:
        html = self.html(TYPED)
        drift = visible_text(drift_of(html))
        self.assertIn(f'You gave a later direction at #3: "{LATEST}".', drift)

    def test_several_since_saving_a_typed_goal(self) -> None:
        html = self.html(TYPED + "__s.annotation_goal_saved_at = 100;\n")
        self.assertIn(
            f"You gave 2 later directions since saving your intent, the earliest at #1: "
            f'"{EARLIEST}".',
            visible_text(drift_of(html)),
        )

    def test_every_unsettled_later_direction_is_drawn_past_the_bound(self) -> None:
        many = (
            "for(let i = 0; i < 25; i += 1){ __semantic.facts.push({fact_id:`agent-${i}`,"
            " at:110 + i, type:'prepared_dispatch', summary:`Dispatch ${i}`,"
            " source_session:{harness:'claude', sid:'focus-1'},"
            " evidence:{source:'dispatch artifact', confidence:'exact'}}); }\n"
        )
        html = self.html(many)
        self.assertRegex(html, r'data-next-entry="1" data-next-entry-id="fo-b"')
        self.assertRegex(html, r'data-next-entry="3" data-next-entry-id="fo-a"')

    def test_without_consent_keep_promises_no_analysis(self) -> None:
        """Keep is never the consent (owner, consent F5): Allow and analyze is."""
        html = self.html('__dashboard.reading = {consent:false, reason:"consent-required"};\n')
        drift = visible_text(drift_of(html))
        self.assertIn("Keep my intent", drift)
        self.assertNotIn("Keep my intent and analyze", drift)

    def test_a_settled_direction_asks_nothing(self) -> None:
        html = self.html(
            TYPED + "__s.annotation_settled_through = 104; __s.annotation_settled_at = 104;\n"
        )
        self.assertNotIn("Keep my intent", html)
        self.assertIn('data-next-cockpit-action="reading-ask"', html)


@unittest.skipUnless(shutil.which("node"), "node not available")
class KeepInEveryRouteStateTest(_DraftPage):
    def keep(self, setup: str = "", reply: str = "") -> dict[str, Any]:
        out = self.drive(
            SOLE + setup + reply,
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        return out

    def test_keep_over_a_draft_settles_adopts_and_analyzes_in_one_reading_press(self) -> None:
        out = self.keep()
        self.assertEqual(1, len(out["posts"]))
        post = out["posts"][0]
        self.assertEqual("/api/reading", post["url"])
        body = post["body"]
        self.assertEqual(104, body["settle_through"])
        self.assertEqual(0, body["expected_revision"])
        self.assertEqual("first-prompt", body["adopt"])
        self.assertEqual(FIRST, body["expected_prompt"])
        self.assertEqual(99, body["expected_prompt_at"])
        self.assertIs(True, body["press"])
        self.assertNotIn("allow", body)

    STORED = (
        '__reply["/api/annotate"] = () => { Object.assign(__s, SETTLED_BY_KEEP);'
        ' return {status:200, body:{ok:true, persisted:true, outcome:"stored", revision:1,'
        " revision_count:1}}; };\n"
    )

    def test_keep_never_carries_allow_and_leaves_the_allow_to_its_own_button(self) -> None:
        cases = {
            "no consent": '__dashboard.reading = {consent:false, reason:"consent-required"};\n',
            "no tool-output permission": "__dashboard.reading = {consent:true, reason:'',"
            " used:0, limit:12, tool_output:{}};\n",
        }
        for name, setup in cases.items():
            with self.subTest(state=name):
                out = self.keep(setup, self.STORED)
                self.assertEqual(["/api/annotate"], [post["url"] for post in out["posts"]])
                body = out["posts"][0]["body"]
                self.assertNotIn("allow", body)
                self.assertNotIn("tool_output", body)
                self.assertNotIn("press", body)
                self.assertEqual(104, body["settle_through"])
                self.assertEqual(0, body["expected_revision"])
                self.assertEqual("first-prompt", body["adopt"])
                drift = drift_of(out["html"])
                self.assertIn(KEEP_ALLOW, visible_text(drift))
                self.assertRegex(
                    drift, r'data-next-cockpit-action="reading-allow"[^>]*>Allow and analyze<'
                )

    def test_the_allow_after_keep_is_the_press_that_sends(self) -> None:
        out = self.drive(
            SOLE
            + '__dashboard.reading = {consent:false, reason:"consent-required"};\n'
            + self.STORED,
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            '__press("reading-allow");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts));",
        )
        assert isinstance(out, list)
        self.assertEqual(["/api/annotate", "/api/reading"], [post["url"] for post in out])
        self.assertIs(True, out[1]["body"]["allow"])
        self.assertNotIn("adopt", out[1]["body"])

    def test_keep_over_saved_words_sends_their_revision_and_no_adoption(self) -> None:
        out = self.keep(TYPED)
        body = out["posts"][0]["body"]
        self.assertEqual(2, body["expected_revision"])
        self.assertNotIn("adopt", body)

    def test_where_no_analysis_can_start_keep_settles_through_annotate(self) -> None:
        cases = {
            "model calls off": '__dashboard.reading = {consent:true, reason:"run-disabled"};\n',
            "no provider enabled": '__dashboard.reading_check = "not-run";\n',
            "no reader": "for(const h of Object.keys(__dashboard.reading_routes)){"
            " __dashboard.reading_routes[h] = {...__dashboard.reading_routes[h], provider:null,"
            ' note:"No reader here."}; }\n',
        }
        reply = (
            '__reply["/api/annotate"] = () => ({status:200, body:{ok:true, persisted:true,'
            ' outcome:"stored", revision:1, revision_count:1}});\n'
        )
        for name, setup in cases.items():
            with self.subTest(state=name):
                out = self.keep(setup, reply)
                self.assertEqual(["/api/annotate"], [post["url"] for post in out["posts"]])
                body = out["posts"][0]["body"]
                self.assertEqual(104, body["settle_through"])
                self.assertEqual(0, body["expected_revision"])
                self.assertEqual("first-prompt", body["adopt"])
                self.assertNotIn("press", body)
                self.assertIn("No analysis was started.", visible_text(drift_of(out["html"])))

    def test_a_keep_the_store_could_not_take_says_nothing_was_settled(self) -> None:
        off = '__dashboard.reading = {consent:true, reason:"run-disabled"};\n'
        for outcome, said in (
            ("refused", "Nothing was settled and no analysis was started"),
            ("unwritable", "Nothing was settled and no analysis was started"),
            ("untrusted", "Not settled. Cargento could not read cargento-annotations.json"),
        ):
            with self.subTest(outcome=outcome):
                out = self.keep(
                    off,
                    '__reply["/api/annotate"] = () => ({status:200, body:{ok:true,'
                    f' persisted:false, outcome:"{outcome}"}}}});\n',
                )
                text = visible_text(drift_of(out["html"]))
                self.assertIn(said, text)
                self.assertNotIn("Kept your intent", text)

    def test_where_no_analysis_can_start_the_button_does_not_promise_one(self) -> None:
        html = self.html('__dashboard.reading = {consent:true, reason:"run-disabled"};\n')
        self.assertIn("Keep my intent", html)
        self.assertNotIn("Keep my intent and analyze", html)

    def test_a_stale_revision_refusal_is_rendered_and_nothing_is_said_to_be_settled(self) -> None:
        out = self.keep(
            reply='__reply["/api/reading"] = () => ({status:422, body:{ok:false, produced:false,'
            ' adoption_refused:true, settled:"refused"}});\n'
        )
        text = visible_text(drift_of(out["html"]))
        self.assertIn("Nothing was settled and no analysis was started", text)
        self.assertIn("Keep my intent and analyze", text)

    def test_a_press_that_settled_and_could_not_start_says_so(self) -> None:
        out = self.keep(
            reply='__reply["/api/reading"] = () => ({status:409, body:{ok:false, produced:false,'
            ' reason:"provider-changed", settled:"stored"}});\n'
        )
        self.assertIn("No analysis was started.", visible_text(drift_of(out["html"])))

    def test_an_edited_box_refuses_keep_with_the_same_sentence(self) -> None:
        out = self.drive(
            after='__typeGoal("Something else");\n__press("direction-keep");\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts, html:__els.app.innerHTML}));"
        )
        assert isinstance(out, dict)
        self.assertEqual([], out["posts"])
        self.assertIn(EDITED, visible_text(drift_of(out["html"])))


LONG = "Retry the failed events with exponential backoff " * 6  # 300 characters
# The rendered "Replace line 3" button, pressed with its own data-arg, so an
# off-by-one in the renderer reaches the wire (layout F6).
REPLACE_THREE = r"""
const three = __els.app.innerHTML.match(
  /<button[^>]*data-next-cockpit-action="direction-replace" data-arg="(\d+)"[^>]*aria-label="Replace line 3"/);
__press("direction-replace", three[1]);
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class AddItToMyIntentTest(_DraftPage):
    def opened(self, text: str, setup: str = "", then: str = "") -> dict[str, Any]:
        reply = (
            '__reply["/api/direction"] = body => ({status:200, body:{ok:true, fact_id:body.fact_id,'
            f" text:{json.dumps(text)}, clipped:false, fits:{json.dumps(len(text) <= 240)}}}}});\n"
            '__reply["/api/annotate"] = () => ({status:200, body:{ok:true, persisted:true,'
            ' outcome:"stored", revision:1, revision_count:1}});\n'
        )
        out = self.drive(
            setup + reply,
            '__press("direction-add", __argOf("direction-add"));\n'
            "await __settle();\nawait __settle();\n"
            + then
            + "console.log(JSON.stringify({posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        return out

    def pending(self, html: str) -> str:
        match = re.search(r"<li[^>]*data-next-cockpit-direction-line[\s\S]*?</li>", html)
        assert match is not None, "no pending line"
        return match.group(0)

    def test_a_short_direction_opens_for_review_and_saves_with_the_draft_adopted(self) -> None:
        out = self.opened(LATEST, then='__press("direction-save");\nawait __settle();\n')
        self.assertEqual(
            {"harness": "claude", "sid": "focus-1", "fact_id": "fo-b"}, out["posts"][0]["body"]
        )
        self.assertEqual("/api/direction", out["posts"][0]["url"])
        save = out["posts"][1]
        self.assertEqual("/api/annotate", save["url"])
        self.assertEqual(
            {
                "harness": "claude",
                "sid": "focus-1",
                "add_direction": "fo-b",
                "text": LATEST,
                "expected_revision": 0,
                "adopt": "first-prompt",
                "expected_prompt": FIRST,
                "expected_prompt_at": 99,
            },
            save["body"],
        )

    def test_the_pending_line_says_where_it_came_from_and_that_it_is_not_saved(self) -> None:
        out = self.opened(LATEST)
        line = self.pending(out["html"])
        self.assertIn("from #1 · not saved", visible_text(line))
        self.assertIn(f">{LATEST}</textarea>", line)

    def test_a_long_direction_is_shown_whole_counted_over_and_never_saved(self) -> None:
        out = self.opened(LONG, then='__press("direction-save");\nawait __settle();\n')
        line = self.pending(out["html"])
        self.assertIn(f">{LONG}</textarea>", line)
        self.assertNotIn("maxlength", line)
        self.assertIn(f"{len(LONG)}/240", line)
        save = re.search(r'<button[^>]*data-next-cockpit-action="direction-save"[^>]*>', line)
        assert save is not None
        self.assertIn('aria-disabled="true"', save.group(0))
        self.assertIn(
            "A line holds 240 characters. Shorten this one to add it.", visible_text(line)
        )
        self.assertEqual(["/api/direction"], [post["url"] for post in out["posts"]])

    def test_a_multi_line_direction_is_one_line_in_the_box(self) -> None:
        out = self.opened("First line of it\nsecond line of it")
        line = self.pending(out["html"])
        self.assertIn(">First line of it second line of it</textarea>", line)

    def test_a_long_multi_line_direction_edited_down_saves_the_edit(self) -> None:
        two = LONG + "\n" + LONG
        out = self.opened(
            two,
            then='__typeDirection("Retry with backoff");\n'
            '__press("direction-save");\nawait __settle();\n',
        )
        self.assertEqual("Retry with backoff", out["posts"][1]["body"]["text"])

    def test_a_full_list_names_the_line_to_replace_and_counts_from_zero(self) -> None:
        six = (
            "".join(
                f'__s.annotation_line_{k} = "Line {k}"; __s.annotation_line_{k}_source = "typed";'
                for k in range(1, 7)
            )
            + TYPED
        )
        out = self.opened(LATEST, six, '__press("direction-save");\nawait __settle();\n')
        line = self.pending(out["html"])
        self.assertIn(FULL, visible_text(line))
        self.assertEqual(["/api/direction"], [post["url"] for post in out["posts"]])
        chosen = self.opened(
            LATEST,
            six,
            REPLACE_THREE + '__press("direction-save");\nawait __settle();\n',
        )
        body = chosen["posts"][1]["body"]
        self.assertEqual(2, body["replace"])
        self.assertEqual(2, body["expected_revision"])
        self.assertNotIn("adopt", body)

    def test_a_reader_adding_to_a_full_list_is_told_it_is_full_once(self) -> None:
        """DRC-4760. The list's own notice and the open line's reason said the same sentence twice.

        Counted over drawn paragraphs only: a `hidden` one is kept for the add control's
        `aria-describedby` and is not on screen.
        """
        six = (
            "".join(
                f'__s.annotation_line_{k} = "Line {k}"; __s.annotation_line_{k}_source = "typed";'
                for k in range(1, 7)
            )
            + TYPED
        )

        def shown(html: str) -> list[str]:
            return [
                attrs
                for attrs, text in re.findall(r"<p\b([^>]*)>([^<]*)</p>", intent_of(html))
                if visible_text(text).strip() == FULL and not re.search(r"\shidden\b", attrs)
            ]

        closed = self.drive(six, "console.log(JSON.stringify(__els.app.innerHTML));")
        assert isinstance(closed, str)
        self.assertEqual(1, len(shown(closed)), "a full list says so with no line open")
        out = self.opened(LATEST, six)
        said = shown(out["html"])
        self.assertEqual(1, len(said), "the notice is drawn once while the line is open")
        # The one beside the line's save, which names it.
        self.assertIn("data-next-cockpit-direction-why", said[0])
        self.assertIn(FULL, visible_text(self.pending(out["html"])))
        # Where the open line gives another reason, the list's notice is the only one, so the
        # disabled "add a line" is not left without a reason on screen.
        long = self.opened(LONG, six)
        self.assertIn(
            "A line holds 240 characters. Shorten this one to add it.",
            visible_text(self.pending(long["html"])),
        )
        self.assertEqual(1, len(shown(long["html"])), "over the bound the list still says full")
        self.assertNotIn("data-next-cockpit-direction-why", shown(long["html"])[0])
        five = "".join(
            f'__s.annotation_line_{k} = "Line {k}"; __s.annotation_line_{k}_source = "typed";'
            for k in range(1, 6)
        )
        typed_sixth = self.opened(
            LATEST,
            five + TYPED,
            f"nextCockpitHeldDrafts.set({json.dumps(LINES_KEY)}, "
            f"{json.dumps([f'Line {k}' for k in range(1, 7)])});\nrenderNext();\n",
        )
        self.assertIn(ADD_EDITED, visible_text(self.pending(typed_sixth["html"])))
        self.assertEqual(1, len(shown(typed_sixth["html"])), "six drafted lines still say full")
        self.assertNotIn("data-next-cockpit-direction-why", shown(typed_sixth["html"])[0])
        # A line chosen to replace gives no reason, and the list's notice stands alone.
        chosen = self.opened(LATEST, six, REPLACE_THREE)
        self.assertEqual(1, len(shown(chosen["html"])), "a chosen replace still says full once")
        self.assertNotIn("data-next-cockpit-direction-why", shown(chosen["html"])[0])

    def test_a_direction_the_server_cannot_open_says_why_and_opens_nothing(self) -> None:
        why = annotation_store.DIRECTION_UNAVAILABLE
        out = self.drive(
            '__reply["/api/direction"] = () => ({status:200, body:{ok:false,'
            f' reason:"unavailable", why:{json.dumps(why)}}}}});\n',
            '__press("direction-add", "fo-a");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify(__els.app.innerHTML));",
        )
        assert isinstance(out, str)
        self.assertIn(why, visible_text(out))
        self.assertNotIn("data-next-cockpit-direction-line", out)

    def test_a_refused_save_keeps_the_line_and_says_so(self) -> None:
        out = self.opened(
            LATEST,
            then='__reply["/api/annotate"] = () => ({status:200, body:{ok:true, persisted:false,'
            ' outcome:"refused"}});\n__press("direction-save");\nawait __settle();\nrenderNext();\n',
        )
        line = self.pending(out["html"])
        self.assertIn("Not saved.", visible_text(line))


@unittest.skipUnless(shutil.which("node"), "node not available")
class SessionsRowAndJourneyTest(_DraftPage):
    def sessions(self, setup: str = "") -> str:
        out = self.drive(
            setup,
            'navigateNext({view:"sessions"});\nawait __settle();\n'
            "console.log(JSON.stringify(__els.app.innerHTML));",
        )
        assert isinstance(out, str)
        return out

    def test_the_goal_cell_names_the_first_prompt_the_panel_drafts(self) -> None:
        html = self.sessions()
        cell = re.search(r'data-next-operation-fact="goal">([\s\S]*?)</span>', html)
        assert cell is not None
        text = visible_text(cell.group(1))
        self.assertIn("GOAL · YOUR FIRST PROMPT", text)
        self.assertIn(FIRST, text)
        self.assertIn("data-next-goal-focus", cell.group(1))

    def test_with_no_first_prompt_the_cell_names_the_latest(self) -> None:
        html = self.sessions('__s.first_prompt = ""; __s.first_prompt_at = null;\n')
        self.assertIn("GOAL · YOUR LATEST PROMPT", visible_text(html))

    def test_a_goalless_session_with_a_later_direction_reaches_a_result_in_three_presses(
        self,
    ) -> None:
        out = self.drive(
            SOLE + '__reply["/api/reading"] = () => ({status:202, body:{ok:true, produced:false,'
            ' settled:"stored", job:{id:"j1", phase:"preparing", steps:[]}}});\n',
            """
let presses = 0;
navigateNext({view:"sessions"});
await __settle();
const link = __els.app.innerHTML.match(/data-next-route="([^"]+)" data-next-goal-focus/);
presses += 1;
__fire("click", {preventDefault(){}, target:{dataset:{nextRoute:link[1]},
  hasAttribute(name){ return name === "data-next-goal-focus"; },
  closest(selector){ return selector === "[data-next-route]" ? this : null; }}});
await __settle();
const landed = __els.app.innerHTML.includes('data-next-cockpit-action="direction-keep"');
presses += 1;
__press("direction-keep");
await __settle();
await __settle();
/* The job ends and the board publishes the result: no press. */
delete __dashboard.reading_jobs;
__s.annotation_goal = __s.first_prompt;
__s.annotation_goal_source = "first-prompt";
__s.annotation_goal_source_at = 99;
__s.annotation_revision = 1;
__s.annotation_settled_through = 104;
__s.annotation_settled_at = 105;
__s.annotation_reading_count = 1;
__s.annotation_assessment = {revision_read:1, goal_source:"first-prompt", goal_source_at:99,
  criteria:{goal:{result:"departure", detail:"It moved to the dispatcher.", cites:["fo-a"]}}};
__fetchImpl = __upstream;
await refreshNext();
await __settle();
console.log(JSON.stringify({presses, landed, posts:__posts.map(p => p.url),
  html:__els.app.innerHTML}));
""",
        )
        assert isinstance(out, dict)
        self.assertTrue(out["landed"])
        self.assertEqual(["/api/reading"], out["posts"])
        self.assertIn("data-next-result", out["html"])
        self.assertLessEqual(out["presses"], 3)
        self.assertEqual(2, out["presses"])


# Every element carrying a focus key, parsed from the markup, so a test can
# see which one the page focused and what kind of element it is.
LANDING_DOM = r"""
let __focusables = [];
__els.app = {
  get innerHTML(){ return this.html || ""; },
  set innerHTML(html){
    this.html = html;
    document.activeElement = null;
    __focusables = [...html.matchAll(/<([a-z0-9]+)\b([^>]*\bdata-next-focus="([^"]*)"[^>]*)>/g)]
      .map(match => ({tagName:match[1].toUpperCase(), attrs:match[2],
        dataset:{nextFocus:match[3].replace(/&quot;/g, '"').replace(/&amp;/g, "&")},
        focus(){ document.activeElement = this; }}));
  },
  querySelectorAll(selector){ return selector === "[data-next-focus]" ? __focusables : []; }
};
"""

LAND = """
navigateNext({view:"sessions"});
await __settle();
const link = __els.app.innerHTML.match(
  /data-next-route="([^"]*:claude:focus-1)" data-next-goal-focus/);
__fire("click", {preventDefault(){}, target:{dataset:{nextRoute:link[1]},
  hasAttribute(name){ return name === "data-next-goal-focus"; },
  closest(selector){ return selector === "[data-next-route]" ? this : null; }}});
await __settle();
const active = document.activeElement;
console.log(JSON.stringify(active ? {key:active.dataset.nextFocus, tag:active.tagName,
  attrs:active.attrs} : null));
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class LandingOverADraftTest(_DraftPage):
    """Verifier V1: the landing never leaves focus in an untouched drafted goal box."""

    def test_the_sessions_link_lands_on_the_intent_heading_over_an_untouched_draft(self) -> None:
        out = self.drive(LANDING_DOM, LAND)
        assert isinstance(out, dict)
        self.assertNotEqual(GOAL_KEY, out["key"])
        self.assertEqual("H2", out["tag"])
        self.assertIn('id="next-session-intent-heading"', out["attrs"])
        self.assertIn('tabindex="-1"', out["attrs"])

    def test_with_nothing_drafted_it_still_lands_in_the_empty_goal_box(self) -> None:
        out = self.drive(
            LANDING_DOM + '__s.first_prompt = ""; __s.first_prompt_at = null;'
            " __s.instruction = null;\n",
            LAND,
        )
        assert isinstance(out, dict)
        self.assertEqual(GOAL_KEY, out["key"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class RideAlongTest(_DraftPage):
    """DRC-4714's focus keys and line width, and DRC-4671's breadcrumb."""

    def test_remove_add_clear_and_turn_off_readings_carry_focus_keys(self) -> None:
        html = self.html(
            TYPED + '__s.annotation_line_1 = "Line one"; __s.annotation_line_1_source = "typed";\n'
        )
        for action in ("held-line-remove", "held-line-add", "held-clear", "reading-off"):
            with self.subTest(action=action):
                button = re.search(rf'<button[^>]*data-next-cockpit-action="{action}"[^>]*>', html)
                assert button is not None, action
                self.assertIn("data-next-focus=", button.group(0))

    def test_a_saved_line_keeps_its_source_space_while_you_type(self) -> None:
        out = self.drive(
            TYPED + '__s.annotation_line_1 = "Line one"; __s.annotation_line_1_source = "typed";\n',
            """
nextCockpitHeldDrafts.set("held:claude:focus-1:lines", ["Line one and more"]);
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""",
        )
        assert isinstance(out, str)
        source = re.search(r"<span[^>]*data-next-cockpit-held-line-source=\"0\"[^>]*>", out)
        assert source is not None
        self.assertIn("data-next-cockpit-held-line-source-stale", source.group(0))
        self.assertNotIn(" hidden", source.group(0))
        self.assertRegex(
            NEXT_STYLES,
            r"\.next-cockpit-held-source\[data-next-cockpit-held-line-source-stale\]"
            r"\{visibility:hidden\}",
        )

    def test_a_keystroke_hides_the_source_and_keeps_its_space(self) -> None:
        out = self.drive(
            TYPED + '__s.annotation_line_1 = "Line one"; __s.annotation_line_1_source = "typed";\n',
            """
const attrs = new Set();
const source = {hidden:false, setAttribute(name){ attrs.add(name); },
  removeAttribute(name){ attrs.delete(name); }};
const field = {querySelector(selector){
  return selector === '[data-next-cockpit-held-line-source="0"]' ? source : null; }};
const box = {value:"Line one and more", dataset:{nextCockpitHeldLinesKey:"held:claude:focus-1:lines",
  nextCockpitHeldLineIndex:"0", nextCockpitHeldSaved:"Line one"},
  closest(selector){
    if(selector === "[data-next-cockpit-held-lines-key]") return this;
    return selector === "[data-next-cockpit-held-field]" ? field : null; }};
__fire("input", {target:box});
const typed = {stale:attrs.has("data-next-cockpit-held-line-source-stale"), hidden:source.hidden};
box.value = "Line one";
__fire("input", {target:box});
console.log(JSON.stringify({typed, back:attrs.has("data-next-cockpit-held-line-source-stale")}));
""",
        )
        assert isinstance(out, dict)
        self.assertEqual({"stale": True, "hidden": False}, out["typed"])
        self.assertFalse(out["back"])

    def test_no_crumb_breaks_inside_a_word(self) -> None:
        self.assertRegex(NEXT_STYLES, r"\.next-crumb\{[^}]*flex-shrink:0")
        self.assertRegex(NEXT_STYLES, r"\.next-breadcrumb\{[^}]*flex-wrap:wrap")


OPENED = (
    '__reply["/api/direction"] = body => ({status:200, body:{ok:true, fact_id:body.fact_id,'
    f" text:{json.dumps(LATEST)}, clipped:false, fits:true}}}});\n"
    '__reply["/api/annotate"] = () => ({status:200, body:{ok:true, persisted:true,'
    ' outcome:"stored", revision:3, revision_count:3}});\n'
)
OPEN_ADD = (
    '__press("direction-add", __argOf("direction-add"));\nawait __settle();\nawait __settle();\n'
)
ONE_LINE = '__s.annotation_line_1 = "Line one"; __s.annotation_line_1_source = "typed";\n'
STARTED = (
    '__reply["/api/reading"] = () => ({status:202, body:{ok:true, produced:false,'
    ' settled:"stored", job:{id:"j1", phase:"preparing", steps:[]}}});\n'
)
REPORT = (
    "console.log(JSON.stringify({posts:__posts, html:__els.app.innerHTML,"
    f" goal:nextCockpitHeldDrafts.has({json.dumps(GOAL_KEY)})"
    f" ? nextCockpitHeldDrafts.get({json.dumps(GOAL_KEY)}) : null,"
    " renders:__renders.map(r => r && r.named || null)}));"
)


def goal_box(html: str) -> str:
    box = re.search(r'<textarea[^>]*data-next-cockpit-held-kind="goal"[^>]*>([^<]*)<', html)
    assert box is not None
    return box.group(1)


def pending_line(html: str) -> str:
    match = re.search(r"<li[^>]*data-next-cockpit-direction-line[\s\S]*?</li>", html)
    assert match is not None, "no pending line"
    return match.group(0)


@unittest.skipUnless(shutil.which("node"), "node not available")
class UnsavedEditsRefuseThePressTest(_DraftPage):
    """Consent F1 and F2, Codex 2: no press stands on words other than the ones on screen."""

    def run_after(self, setup: str, after: str) -> dict[str, Any]:
        out = self.drive(setup, after + REPORT)
        assert isinstance(out, dict)
        return out

    def test_keep_over_an_edited_saved_goal_sends_nothing_and_keeps_the_edit(self) -> None:
        out = self.run_after(
            TYPED + STARTED,
            '__typeGoal("Ship it differently");\n__press("direction-keep");\nawait __settle();\n'
            "renderNext();\n",
        )
        self.assertEqual([], out["posts"])
        self.assertIn(EDITED, visible_text(drift_of(out["html"])))
        self.assertEqual("Ship it differently", goal_box(out["html"]))

    def test_where_no_reader_keep_over_an_edit_still_sends_nothing(self) -> None:
        out = self.run_after(
            TYPED + "for(const h of Object.keys(__dashboard.reading_routes)){"
            " __dashboard.reading_routes[h] = {...__dashboard.reading_routes[h], provider:null,"
            ' note:"No reader here."}; }\n',
            '__typeGoal("Ship it differently");\n__press("direction-keep");\nawait __settle();\n',
        )
        self.assertEqual([], out["posts"])
        self.assertIn(EDITED, visible_text(drift_of(out["html"])))

    def test_analyze_over_an_edited_saved_goal_sends_nothing(self) -> None:
        out = self.run_after(
            TYPED + "__s.annotation_settled_through = 104; __s.annotation_settled_at = 104;\n",
            '__typeGoal("Ship it differently");\n__press("reading-ask");\nawait __settle();\n',
        )
        self.assertEqual([], out["posts"])
        self.assertIn(EDITED, visible_text(drift_of(out["html"])))

    def test_keep_over_an_unsaved_line_edit_sends_nothing(self) -> None:
        out = self.run_after(
            TYPED + ONE_LINE + STARTED,
            f'nextCockpitHeldDrafts.set({json.dumps(LINES_KEY)}, ["Line one edited"]);\n'
            '__press("direction-keep");\nawait __settle();\n',
        )
        self.assertEqual([], out["posts"])
        self.assertIn(EDITED, visible_text(drift_of(out["html"])))

    def test_keep_is_inert_over_an_edit_and_while_it_is_pending(self) -> None:
        keep = r'<button[^>]*data-next-cockpit-action="direction-keep"[^>]*>'
        edited = self.run_after(TYPED, '__typeGoal("Ship it differently");\nrenderNext();\n')
        button = re.search(keep, edited["html"])
        assert button is not None
        self.assertIn('aria-disabled="true"', button.group(0))
        pending = self.run_after(
            TYPED + '__reply["/api/reading"] = () => { __seen = __els.app.innerHTML;'
            ' return {status:202, body:{ok:true, produced:false, settled:"stored",'
            ' job:{id:"j1", phase:"preparing", steps:[]}}}; };\nlet __seen = "";\n',
            '__press("direction-keep");\nawait __settle();\n__els.app.innerHTML = __seen;\n',
        )
        button = re.search(keep, pending["html"])
        assert button is not None
        self.assertIn('aria-disabled="true"', button.group(0))

    def test_add_save_over_an_edited_goal_is_refused_beside_the_line(self) -> None:
        out = self.run_after(
            TYPED + OPENED,
            OPEN_ADD + '__typeGoal("Ship it differently");\n'
            '__press("direction-save");\nawait __settle();\n',
        )
        self.assertEqual(["/api/direction"], [post["url"] for post in out["posts"]])
        self.assertIn(ADD_EDITED, visible_text(pending_line(out["html"])))
        # Not in the Drift control (consent F8); Keep's own refusal may stand there.
        self.assertNotIn(ADD_EDITED, visible_text(drift_of(out["html"])))
        self.assertEqual("Ship it differently", goal_box(out["html"]))

    def test_add_save_over_an_unsaved_line_edit_is_refused(self) -> None:
        out = self.run_after(
            TYPED + ONE_LINE + OPENED,
            OPEN_ADD + f'nextCockpitHeldDrafts.set({json.dumps(LINES_KEY)}, ["Line one edited"]);\n'
            '__press("direction-save");\nawait __settle();\n',
        )
        self.assertEqual(["/api/direction"], [post["url"] for post in out["posts"]])
        self.assertIn(ADD_EDITED, visible_text(pending_line(out["html"])))

    def test_a_goal_typed_while_keep_is_open_is_not_dropped(self) -> None:
        out = self.run_after(
            SOLE + '__reply["/api/reading"] = () => { __typeGoal("typed meanwhile");'
            ' return {status:202, body:{ok:true, produced:false, settled:"stored",'
            ' job:{id:"j1", phase:"preparing", steps:[]}}}; };\n',
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual(["/api/reading"], [post["url"] for post in out["posts"]])
        self.assertEqual("typed meanwhile", out["goal"])

    def test_a_goal_typed_while_add_saves_is_not_dropped(self) -> None:
        out = self.run_after(
            '__reply["/api/direction"] = body => ({status:200, body:{ok:true,'
            f" fact_id:body.fact_id, text:{json.dumps(LATEST)}, clipped:false, fits:true}}}});\n"
            '__reply["/api/annotate"] = () => { __typeGoal("typed meanwhile");'
            ' return {status:200, body:{ok:true, persisted:true, outcome:"stored", revision:1,'
            " revision_count:1}}; };\n",
            OPEN_ADD + '__press("direction-save");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual("typed meanwhile", out["goal"])

    def test_a_box_put_back_at_the_draft_is_cleared_once_a_press_adopts_it(self) -> None:
        back = f"__typeGoal({json.dumps(FIRST + 'x')});\n__typeGoal({json.dumps(FIRST)});\n"
        kept = self.run_after(
            SOLE + STARTED,
            back + '__press("direction-keep");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual(["/api/reading"], [post["url"] for post in kept["posts"]])
        self.assertIsNone(kept["goal"])
        settled_only = self.run_after(
            SOLE
            + '__dashboard.reading = {consent:true, reason:"run-disabled"};\n'
            + KeepInEveryRouteStateTest.STORED,
            back + '__press("direction-keep");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual(["/api/annotate"], [post["url"] for post in settled_only["posts"]])
        self.assertIsNone(settled_only["goal"])
        added = self.run_after(
            OPENED,
            back + OPEN_ADD + '__press("direction-save");\nawait __settle();\nawait __settle();\n',
        )
        self.assertEqual("/api/annotate", added["posts"][-1]["url"])
        self.assertIsNone(added["goal"])

    def test_add_save_forgets_an_unchanged_line_draft_so_the_added_line_shows(self) -> None:
        out = self.run_after(
            TYPED + ONE_LINE + OPENED,
            OPEN_ADD + f'nextCockpitHeldDrafts.set({json.dumps(LINES_KEY)}, ["Line one"]);\n'
            '__press("direction-save");\nawait __settle();\nawait __settle();\n'
            f"__lines = nextCockpitHeldDrafts.has({json.dumps(LINES_KEY)});\n",
        )
        self.assertEqual("/api/annotate", out["posts"][-1]["url"])
        # The draft equal to what the server held is gone, so the server's new
        # list is what the next render draws and the next line save sends.
        lines = self.drive(
            TYPED + ONE_LINE + OPENED,
            OPEN_ADD + f'nextCockpitHeldDrafts.set({json.dumps(LINES_KEY)}, ["Line one"]);\n'
            '__press("direction-save");\nawait __settle();\nawait __settle();\n'
            f"console.log(JSON.stringify(nextCockpitHeldDrafts.has({json.dumps(LINES_KEY)})));",
        )
        self.assertIs(False, lines)

    def test_a_line_typed_while_add_saves_keeps_the_added_direction(self) -> None:
        """Verifier V2: the reader types into line 0 while Add's save is open, the
        save lands, and the next lines save still carries the added direction."""
        type_line = (
            '__fire("input", {target:{value:"MY LINE", dataset:{nextCockpitHeldLinesKey:'
            f'{json.dumps(LINES_KEY)}, nextCockpitHeldLineIndex:"0"}}, closest(selector){{'
            ' return selector === "[data-next-cockpit-held-lines-key]" ? this : null; }}});'
        )
        out = self.run_after(
            '__reply["/api/direction"] = body => ({status:200, body:{ok:true,'
            f" fact_id:body.fact_id, text:{json.dumps(LATEST)}, clipped:false, fits:true}}}});\n"
            '__reply["/api/annotate"] = body => { if(body.add_direction){ '
            + type_line
            + " Object.assign(__s, SETTLED_BY_KEEP, {annotation_settled_through:102,"
            f' annotation_line_1:{json.dumps(LATEST)}, annotation_line_1_source:"direction"}});'
            ' } return {status:200, body:{ok:true, persisted:true, outcome:"stored",'
            " revision:1, revision_count:1}}; };\n",
            OPEN_ADD + '__press("direction-save");\nawait __settle();\nawait __settle();\n'
            "renderNext();\n"
            '__press("held-save", "lines");\nawait __settle();\nawait __settle();\n',
        )
        saves = [post["body"] for post in out["posts"] if "lines" in post["body"]]
        self.assertEqual(1, len(saves), out["posts"])
        self.assertEqual(["MY LINE", LATEST], saves[0]["lines"])
        self.assertEqual([None, 0], saves[0]["origins"])
        self.assertEqual(1, saves[0]["expected_revision"])

    @staticmethod
    def type_line_zero(value: str) -> str:
        return (
            f'__fire("input", {{target:{{value:{json.dumps(value)},'
            f" dataset:{{nextCockpitHeldLinesKey:{json.dumps(LINES_KEY)},"
            ' nextCockpitHeldLineIndex:"0"}, closest(selector){'
            ' return selector === "[data-next-cockpit-held-lines-key]" ? this : null; }}});'
        )

    def typed_during_save(
        self, setup: str, fresh: str, then: str, *, stale: int = 0
    ) -> dict[str, Any]:
        """The save's refresh publishes a NEW session object, as the live poll
        does, rather than mutating the one the save captured (verifier F1).
        `stale` GETs after the save still serve the pre-save row, as a refresh
        superseded by a poll leaves it live."""
        out = self.drive(
            setup + "let __fresh = null; let __staleGets = 0; const __get = __fetchImpl;\n"
            '__fetchImpl = async (url, init) => { if((!init || init.method !== "POST") &&'
            " __fresh){ if(__staleGets > 0){ __staleGets -= 1; } else {"
            " __dashboard.sessions[0] = __fresh; __fresh = null; } } return __get(url, init); };\n"
            '__reply["/api/direction"] = body => ({status:200, body:{ok:true,'
            f" fact_id:body.fact_id, text:{json.dumps(LATEST)}, clipped:false, fits:true}}}});\n"
            '__reply["/api/annotate"] = body => { if(body.add_direction){ '
            + self.type_line_zero("Line 1 MY EDIT")
            + f" __staleGets = {stale}; __fresh = Object.assign({{}}, __s, SETTLED_BY_KEEP,"
            f" {{annotation_settled_through:102}}, {fresh}); return {{status:200,"
            ' body:{ok:true, persisted:true, outcome:"stored", revision:3, revision_count:3}};'
            ' } return {status:200, body:{ok:true, persisted:true, outcome:"stored",'
            " revision:4, revision_count:4}}; };\n",
            OPEN_ADD + then + '__press("direction-save");\nawait __settle();\nawait __settle();\n'
            "renderNext();\nawait __settle();\n"
            f"const __draft = nextCockpitHeldDrafts.get({json.dumps(LINES_KEY)});\n"
            f"const __origins = nextCockpitHeldOrigins.get({json.dumps(LINES_KEY)});\n"
            "const __boxes = (__els.app.innerHTML.match("
            "/data-next-cockpit-held-line-index=/g) || []).length;\n"
            '__press("held-save", "lines");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify({draft:__draft, origins:__origins, boxes:__boxes,"
            " posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        return out

    def test_a_replace_typed_over_a_full_list_takes_the_replaced_lines_place(self) -> None:
        six = "".join(
            f'__s.annotation_line_{k} = "Line {k}"; __s.annotation_line_{k}_source = "typed";'
            for k in range(1, 7)
        )
        stored = (
            "{annotation_revision:3, annotation_revision_count:3,"
            f' annotation_line_3:{json.dumps(LATEST)}, annotation_line_3_source:"direction"}}'
        )
        out = self.typed_during_save(six + TYPED, stored, REPLACE_THREE)
        want = ["Line 1 MY EDIT", "Line 2", LATEST, "Line 4", "Line 5", "Line 6"]
        self.assertEqual(want, out["draft"])
        self.assertEqual([0, 1, 2, 3, 4, 5], out["origins"])
        self.assertEqual(6, out["boxes"])
        saves = [post["body"] for post in out["posts"] if "lines" in post["body"]]
        self.assertEqual(1, len(saves), out["posts"])
        self.assertEqual(want, saves[0]["lines"])
        self.assertEqual([0, 1, 2, 3, 4, 5], saves[0]["origins"])
        self.assertEqual(3, saves[0]["expected_revision"])
        self.assertNotIn("The server refused the write", visible_text(out["html"]))

    def test_a_replace_waits_out_a_refresh_that_served_the_pre_save_row(self) -> None:
        six = "".join(
            f'__s.annotation_line_{k} = "Line {k}"; __s.annotation_line_{k}_source = "typed";'
            for k in range(1, 7)
        )
        stored = (
            "{annotation_revision:3, annotation_revision_count:3,"
            f' annotation_line_3:{json.dumps(LATEST)}, annotation_line_3_source:"direction"}}'
        )
        out = self.typed_during_save(six + TYPED, stored, REPLACE_THREE, stale=1)
        want = ["Line 1 MY EDIT", "Line 2", LATEST, "Line 4", "Line 5", "Line 6"]
        self.assertEqual(want, out["draft"])
        self.assertEqual([0, 1, 2, 3, 4, 5], out["origins"])

    def test_an_add_typed_over_a_short_list_appends_from_a_fresh_session(self) -> None:
        stored = (
            "{annotation_revision:3, annotation_revision_count:3,"
            f' annotation_line_2:{json.dumps(LATEST)}, annotation_line_2_source:"direction"}}'
        )
        out = self.typed_during_save(ONE_LINE + TYPED, stored, "")
        self.assertEqual(["Line 1 MY EDIT", LATEST], out["draft"])
        self.assertEqual([0, 1], out["origins"])
        saves = [post["body"] for post in out["posts"] if "lines" in post["body"]]
        self.assertEqual(1, len(saves), out["posts"])
        self.assertEqual(["Line 1 MY EDIT", LATEST], saves[0]["lines"])
        self.assertEqual([0, 1], saves[0]["origins"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class KeepSettlesWithoutConsentTest(_DraftPage):
    """Owner ruling on consent F5 and Codex 1, and the survivors on Keep's outcomes."""

    def keep(self, setup: str, after: str = "") -> dict[str, Any]:
        out = self.drive(
            SOLE + setup,
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n' + after + REPORT,
        )
        assert isinstance(out, dict)
        return out

    OFF = '__dashboard.reading = {consent:true, reason:"run-disabled"};\n'

    def test_a_stored_keep_that_did_not_persist_is_not_called_kept(self) -> None:
        out = self.keep(
            self.OFF + '__reply["/api/annotate"] = () => ({status:200, body:{ok:true,'
            ' persisted:false, outcome:"stored"}});\n'
        )
        text = visible_text(drift_of(out["html"]))
        self.assertIn("Nothing was settled and no analysis was started", text)
        self.assertNotIn("Kept your intent", text)

    def test_a_bare_422_is_a_refusal(self) -> None:
        out = self.keep('__reply["/api/reading"] = () => ({status:422, body:{ok:false}});\n')
        text = visible_text(drift_of(out["html"]))
        self.assertIn("Nothing was settled and no analysis was started", text)
        self.assertEqual(FIRST, goal_box(out["html"]))


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePendingLineTest(_DraftPage):
    """Layout F2 and Codex 7, and consent F3: which direction Add opens and how its line lives."""

    def test_add_opens_the_earliest_unsettled_direction(self) -> None:
        out = self.drive(
            OPENED,
            "const arg = __argOf('direction-add');\n"
            + OPEN_ADD
            + '__press("direction-save");\nawait __settle();\n'
            "console.log(JSON.stringify({arg, posts:__posts}));",
        )
        assert isinstance(out, dict)
        self.assertEqual("fo-b", out["arg"])
        self.assertEqual("fo-b", out["posts"][0]["body"]["fact_id"])
        self.assertEqual("fo-b", out["posts"][1]["body"]["add_direction"])

    def test_a_second_add_press_keeps_the_edited_line_and_focuses_it(self) -> None:
        out = self.drive(
            OPENED,
            OPEN_ADD
            + '__typeDirection("My edited words");\n__renders.length = 0;\n'
            + OPEN_ADD
            + REPORT,
        )
        assert isinstance(out, dict)
        self.assertEqual(["/api/direction"], [post["url"] for post in out["posts"]])
        self.assertIn(">My edited words</textarea>", pending_line(out["html"]))
        self.assertIn("direction:claude:focus-1", out["renders"])

    def test_the_pending_number_is_recomputed_from_its_fact_id(self) -> None:
        out = self.drive(
            OPENED,
            OPEN_ADD + "__s.annotation_window_start = 103;\nawait refreshNext();\n"
            "await __settle();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
        )
        assert isinstance(out, str)
        line = visible_text(pending_line(out))
        self.assertIn("from your direction · not saved", line)
        self.assertNotIn("#1", line)

    def test_the_pending_line_goes_when_its_direction_is_no_longer_open(self) -> None:
        out = self.drive(
            OPENED,
            OPEN_ADD + "__s.annotation_settled_through = 102; __s.annotation_settled_at = 105;\n"
            "await refreshNext();\nawait __settle();\n"
            "console.log(JSON.stringify(__els.app.innerHTML));",
        )
        assert isinstance(out, str)
        self.assertNotIn("data-next-cockpit-direction-line", out)

    def test_the_pending_line_goes_once_its_save_lands(self) -> None:
        out = self.drive(
            OPENED,
            OPEN_ADD + '__press("direction-save");\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify(__els.app.innerHTML));",
        )
        assert isinstance(out, str)
        self.assertNotIn("data-next-cockpit-direction-line", out)

    def test_remove_hands_focus_back_to_add(self) -> None:
        out = self.drive(
            OPENED,
            OPEN_ADD
            + '__renders.length = 0;\n__press("direction-cancel");\nawait __settle();\n'
            + REPORT,
        )
        assert isinstance(out, dict)
        self.assertIn("direction-add:claude:focus-1", out["renders"])
        self.assertIn('data-next-focus="direction-add:claude:focus-1"', out["html"])

    def test_opening_moves_focus_into_the_line(self) -> None:
        out = self.drive(OPENED, "__renders.length = 0;\n" + OPEN_ADD + REPORT)
        assert isinstance(out, dict)
        self.assertIn("direction:claude:focus-1", out["renders"])
        self.assertIn('data-next-focus="direction:claude:focus-1"', pending_line(out["html"]))


# A lines-only save over the draft opens the window at 103, the ordinary shape
# of a typed lines-only revision: fo-b (102) is a later direction from before it.
LINES_ONLY = (
    ONE_LINE + "__s.annotation_revision = 1; __s.annotation_revision_count = 1;"
    " __s.annotation_at = 106; __s.annotation_window_start = 103;\n"
)


@unittest.skipUnless(shutil.which("node"), "node not available")
class EveryOpenDirectionIsDrawnTest(_DraftPage):
    """Layout F1, and the survivors on the question's sentence."""

    def test_a_later_direction_from_before_the_window_is_drawn_without_a_number(self) -> None:
        html = self.html(LINES_ONLY)
        row = re.search(r'<div class="next-cockpit-work-row"[^>]*data-next-entry-id="fo-b"', html)
        assert row is not None, "fo-b is not drawn"
        self.assertNotIn("data-next-entry=", row.group(0))
        work = visible_text(html[html.index("data-next-cockpit-work") :])
        self.assertNotIn("from before your intent\u2019s window opened", work)
        self.assertIn(
            f'You gave 2 later directions since your first prompt, the earliest: "{EARLIEST}".',
            visible_text(drift_of(html)),
        )

    def test_an_undrawn_number_is_never_named(self) -> None:
        html = self.html(
            LINES_ONLY.replace("window_start = 103", "window_start = 105")
            + "__s.annotation_settled_through = 102; __s.annotation_settled_at = 105;\n"
        )
        drift = visible_text(drift_of(html))
        self.assertIn(f'You gave a later direction: "{LATEST}".', drift)
        self.assertNotIn("#undefined", html)

    def test_over_a_latest_prompt_draft_it_counts_since_your_latest_prompt(self) -> None:
        later = "".join(
            f"__semantic.facts.push({{fact_id:'later-{k}', at:{at}, type:'user_message',"
            f" summary:'Later {k}', source_session:{{harness:'claude', sid:'focus-1'}},"
            " evidence:{source:'root transcript', confidence:'exact'}});\n"
            for k, at in ((1, 106), (2, 108))
        )
        html = self.html('__s.first_prompt = ""; __s.first_prompt_at = null;\n' + later)
        self.assertIn(
            "You gave 2 later directions since your latest prompt, the earliest at",
            visible_text(drift_of(html)),
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class KeepOutcomeReachesTheReaderTest(_DraftPage):
    """Layout F4 and consent F7: Keep's sentence is announced, and focus lands on a control."""

    DOM = cockpit_tests.CockpitCuesReachTheReaderTest.ANNOUNCER_DOM + SOLE

    def test_both_keep_outcomes_are_written_to_the_polite_region(self) -> None:
        out = self.drive(
            self.DOM + '__dashboard.reading = {consent:true, reason:"run-disabled"};\n'
            'let __answer = {ok:true, persisted:false, outcome:"unwritable"};\n'
            '__reply["/api/annotate"] = () => ({status:200, body:__answer});\n',
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            'const failed = [...wrote("next-cockpit-cue-status")];\n'
            '__answer = {ok:true, persisted:true, outcome:"stored", revision:1, revision_count:1};\n'
            '__press("direction-keep");\nawait __settle();\nawait __settle();\n'
            'console.log(JSON.stringify({failed, polite:wrote("next-cockpit-cue-status")}));',
        )
        assert isinstance(out, dict)
        self.assertIn(KEEP_REFUSED, out["failed"])
        self.assertIn(
            "Kept your intent and settled the direction. No analysis was started.", out["polite"]
        )

    def test_after_a_keep_that_settles_focus_lands_on_the_next_primary(self) -> None:
        cases = {
            "allow and analyze": '__dashboard.reading = {consent:false, reason:"consent-required"};\n',
            "analyze": '__dashboard.reading = {consent:true, reason:"run-disabled"};\n',
        }
        for name, setup in cases.items():
            with self.subTest(state=name):
                out = self.drive(
                    self.DOM + setup + KeepInEveryRouteStateTest.STORED,
                    "const keep = controls.find(c => c.dataset.nextCockpitAction === 'direction-keep');\n"
                    "keep.focus();\n"
                    "__fire('click', {preventDefault(){}, target:keep});\n"
                    "await __settle();\nawait __settle();\n"
                    "const active = document.activeElement;\n"
                    "console.log(JSON.stringify(active && active.dataset ? active.dataset.nextFocus : null));",
                )
                self.assertEqual("reading:claude:focus-1", out)

    def test_after_a_keep_that_starts_a_job_focus_lands_on_its_title_not_cancel(self) -> None:
        # The job's title holds the press's key; Cancel is kept off it (S6 review, P-1).
        out = self.drive(
            self.DOM + '__reply["/api/reading"] = () => { Object.assign(__s, SETTLED_BY_KEEP);'
            ' return {status:202, body:{ok:true, produced:false, settled:"stored",'
            ' job:{id:"j1", phase:"preparing", steps:[]}}}; };\n',
            "const keep = controls.find(c => c.dataset.nextCockpitAction === 'direction-keep');\n"
            "keep.focus();\n"
            "__fire('click', {preventDefault(){}, target:keep});\n"
            "await __settle();\nawait __settle();\n"
            "const active = document.activeElement;\n"
            "console.log(JSON.stringify(active && active.dataset ? active.dataset.nextFocus : null));",
        )
        self.assertEqual("reading:claude:focus-1", out)

    PRESS_KEEP = '__press("direction-keep");\nawait __settle();\nawait __settle();\n'

    def spoken(self, html: str, sentence: str) -> list[str]:
        """Every paragraph opening tag that carries `sentence`."""
        return re.findall(r"<p\b[^>]*>(?=" + re.escape(sentence) + ")", html)

    def test_keeps_outcome_is_announced_by_the_region_alone(self) -> None:
        """Verifier V5: the paragraph beside the control is not a second live node."""
        cases = {
            "settled, allow owed": (
                '__dashboard.reading = {consent:false, reason:"consent-required"};\n'
                + KeepInEveryRouteStateTest.STORED,
                KEEP_ALLOW,
            ),
            "refused": (
                (
                    '__dashboard.reading = {consent:true, reason:"run-disabled"};\n'
                    '__reply["/api/annotate"] = () => ({status:200, body:{ok:true,'
                    ' persisted:false, outcome:"unwritable"}});\n'
                ),
                KEEP_REFUSED,
            ),
        }
        for name, (setup, sentence) in cases.items():
            with self.subTest(state=name):
                out = self.drive(
                    self.DOM + setup,
                    self.PRESS_KEEP + "console.log(JSON.stringify({html:__els.app.innerHTML,"
                    ' polite:wrote("next-cockpit-cue-status")}));',
                )
                assert isinstance(out, dict)
                self.assertEqual([sentence], out["polite"])
                tags = self.spoken(out["html"], sentence)
                self.assertEqual(1, len(tags), tags)
                self.assertNotIn("role=", tags[0])

    def test_a_repeated_keep_outcome_is_announced_again(self) -> None:
        out = self.drive(
            self.DOM + '__dashboard.reading = {consent:true, reason:"run-disabled"};\n'
            '__reply["/api/annotate"] = () => ({status:200, body:{ok:true,'
            ' persisted:false, outcome:"unwritable"}});\n',
            self.PRESS_KEEP
            + self.PRESS_KEEP
            + 'console.log(JSON.stringify(wrote("next-cockpit-cue-status")));',
        )
        self.assertEqual([KEEP_REFUSED, "", KEEP_REFUSED], out)

    def test_the_allow_after_keep_takes_keeps_sentence_back_out_of_the_region(self) -> None:
        out = self.drive(
            self.DOM
            + '__dashboard.reading = {consent:false, reason:"consent-required"};\n'
            + KeepInEveryRouteStateTest.STORED
            + STARTED,
            self.PRESS_KEEP + '__press("reading-allow");\nawait __settle();\nawait __settle();\n'
            'console.log(JSON.stringify(wrote("next-cockpit-cue-status")));',
        )
        # The Allow's own press then starts a job, announced once (DRC-4736).
        self.assertEqual([KEEP_ALLOW, "", "Analyzing drift"], out)

    def test_the_unsaved_edit_refusal_is_written_to_the_region(self) -> None:
        out = self.drive(
            self.DOM + TYPED,
            '__typeGoal("Ship it differently");\n'
            + self.PRESS_KEEP
            + "console.log(JSON.stringify({html:__els.app.innerHTML,"
            ' polite:wrote("next-cockpit-cue-status")}));',
        )
        assert isinstance(out, dict)
        self.assertEqual([EDITED], out["polite"])
        tags = self.spoken(out["html"], EDITED)
        self.assertEqual(1, len(tags), tags)
        self.assertNotIn("role=", tags[0])


@unittest.skipUnless(shutil.which("node"), "node not available")
class FocusKeysAndTypingTest(_DraftPage):
    """The survivors on focus keys and the in-place input handlers (layout F6)."""

    SIX = "".join(
        f'__s.annotation_line_{k} = "Line {k}"; __s.annotation_line_{k}_source = "typed";'
        for k in range(1, 7)
    )

    def keys(self, html: str) -> list[str]:
        return re.findall(r'data-next-focus="([^"]*)"', html)

    def test_every_intent_control_carries_its_own_focus_key(self) -> None:
        states = {
            "draft, question and a pending line": ("", OPENED, OPEN_ADD),
            "six lines and a pending line": (TYPED + self.SIX, OPENED, OPEN_ADD),
            "settled, idle control": (
                TYPED + ONE_LINE + "__s.annotation_settled_through = 104;"
                " __s.annotation_settled_at = 104;\n",
                "",
                "",
            ),
        }
        for name, (setup, reply, then) in states.items():
            with self.subTest(state=name):
                out = self.drive(
                    setup + reply, then + "console.log(JSON.stringify(__els.app.innerHTML));"
                )
                assert isinstance(out, str)
                keys = self.keys(out)
                duplicated = sorted({key for key in keys if keys.count(key) > 1})
                self.assertEqual([], duplicated)
                for control in re.findall(
                    r"<(?:button|textarea)\b[^>]*data-next-cockpit-(?:action=\"(?:draft-confirm|"
                    r"held-save|held-clear|held-line-remove|held-line-add|direction-save|"
                    r"direction-cancel|direction-replace|direction-keep|direction-add|reading-off|"
                    r'reading-ask|reading-allow)"|direction-key=|held-kind=)[^>]*>',
                    aside_of(out),
                ):
                    self.assertIn("data-next-focus=", control)
        drafted = self.html()
        self.assertIn(f'data-next-focus="{GOAL_KEY}:confirm"', drafted)
        self.assertIn(f'data-next-focus="{GOAL_KEY}:save"', drafted)
        idle = self.html(TYPED + "__s.annotation_settled_through = 104;\n")
        self.assertIn('data-next-focus="reading-off:claude:focus-1"', idle)

    def test_the_goal_box_updates_in_place_as_you_type(self) -> None:
        out = self.drive(
            after=r"""
const attrs = new Set(["data-next-cockpit-drafted"]);
const marks = {hidden:false};
const count = {textContent:""};
const save = {attrs:new Set(["aria-disabled"]), setAttribute(n){ this.attrs.add(n); },
  removeAttribute(n){ this.attrs.delete(n); }};
const field = {setAttribute(n){ attrs.add(n); }, removeAttribute(n){ attrs.delete(n); },
  querySelector(selector){
    if(selector === "[data-next-cockpit-draft-marks]") return marks;
    if(selector === "[data-next-cockpit-held-count]") return count;
    if(selector === '[data-next-cockpit-action="held-save"]') return save;
    return null; }};
const html = __els.app.innerHTML;
const saved = html.match(/data-next-cockpit-held-kind="goal"[^>]*data-next-cockpit-held-saved="([^"]*)"/)[1];
const draft = html.match(/data-next-cockpit-held-kind="goal"[^>]*data-next-cockpit-draft="([^"]*)"/)[1];
const box = {value:"Build it another way", dataset:{nextCockpitHeldKey:"held:claude:focus-1:goal",
  nextCockpitHeldSaved:saved, nextCockpitDraft:draft},
  closest(selector){
    if(selector === "[data-next-cockpit-held-key]") return this;
    return selector === "[data-next-cockpit-held-field]" ? field : null; }};
__fire("input", {target:box});
const typed = {marks:marks.hidden, tint:attrs.has("data-next-cockpit-drafted"), count:count.textContent,
  save:save.attrs.has("aria-disabled")};
box.value = draft;
__fire("input", {target:box});
console.log(JSON.stringify({typed, back:{marks:marks.hidden, tint:attrs.has("data-next-cockpit-drafted")}}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(
            {"marks": True, "tint": False, "count": "20/240", "save": False}, out["typed"]
        )
        self.assertEqual({"marks": False, "tint": True}, out["back"])

    def test_the_pending_line_updates_in_place_as_you_type(self) -> None:
        out = self.drive(
            OPENED,
            OPEN_ADD
            + r"""
const said = {textContent:"", hidden:true};
const count = {textContent:""};
const save = {attrs:new Set(), setAttribute(n){ this.attrs.add(n); },
  removeAttribute(n){ this.attrs.delete(n); }};
const line = {querySelector(selector){
  if(selector === "[data-next-cockpit-direction-why]") return said;
  if(selector === "[data-next-cockpit-direction-count]") return count;
  if(selector === '[data-next-cockpit-action="direction-save"]') return save;
  return null; }};
const box = {value:"x".repeat(241) + "\nmore", dataset:{nextCockpitDirectionKey:"claude:focus-1"},
  closest(selector){
    if(selector === "[data-next-cockpit-direction-key]") return this;
    return selector === "[data-next-cockpit-direction-line]" ? line : null; }};
__fire("input", {target:box});
const over = {value:box.value.includes("\n"), count:count.textContent, said:said.hidden ? "" : said.textContent,
  save:save.attrs.has("aria-disabled")};
box.value = "Short enough";
__fire("input", {target:box});
console.log(JSON.stringify({over, fits:{count:count.textContent, said:said.hidden, save:save.attrs.has("aria-disabled")}}));
""",
        )
        assert isinstance(out, dict)
        self.assertEqual(
            {
                "value": False,
                "count": "246/240",
                "said": "A line holds 240 characters. Shorten this one to add it.",
                "save": True,
            },
            out["over"],
        )
        self.assertEqual({"count": "12/240", "said": True, "save": False}, out["fits"])

    def test_typing_past_the_bound_over_a_full_list_hands_the_full_notice_back_to_the_list(
        self,
    ) -> None:
        """DRC-4760: one of the two says the list is full while it is, as the reader types."""
        six = "".join(
            f'__s.annotation_line_{k} = "Line {k}"; __s.annotation_line_{k}_source = "typed";'
            for k in range(1, 7)
        )
        out = self.drive(
            OPENED + six + TYPED,
            OPEN_ADD
            + r"""
const said = {textContent:"", hidden:false};
const listSays = {hidden:true};
const field = {querySelector(selector){
  return selector === "[data-next-cockpit-held-full]" ? listSays : null; }};
const line = {querySelector(selector){
  return selector === "[data-next-cockpit-direction-why]" ? said : null; },
  closest(selector){ return selector === "[data-next-cockpit-held-field]" ? field : null; }};
const box = {value:"x".repeat(241), dataset:{nextCockpitDirectionKey:"claude:focus-1"},
  closest(selector){
    if(selector === "[data-next-cockpit-direction-key]") return this;
    return selector === "[data-next-cockpit-direction-line]" ? line : null; }};
__fire("input", {target:box});
const over = {said:said.hidden ? "" : said.textContent, list:!listSays.hidden};
box.value = "Short enough";
__fire("input", {target:box});
console.log(JSON.stringify({over, fits:{said:said.hidden ? "" : said.textContent,
  list:!listSays.hidden}}));
""",
        )
        assert isinstance(out, dict)
        self.assertEqual(
            {"said": "A line holds 240 characters. Shorten this one to add it.", "list": True},
            out["over"],
        )
        self.assertEqual({"said": FULL, "list": False}, out["fits"])

    def test_typing_back_to_a_saved_line_after_a_redraw_shows_its_source_again(self) -> None:
        out = self.drive(
            TYPED + ONE_LINE,
            f'nextCockpitHeldDrafts.set({json.dumps(LINES_KEY)}, ["Line one and more"]);\n'
            r"""
renderNext();
const saved = __els.app.innerHTML.match(
  /data-next-cockpit-held-line-index="0"[^>]*data-next-cockpit-held-saved="([^"]*)"/)[1];
const attrs = new Set(["data-next-cockpit-held-line-source-stale"]);
const source = {setAttribute(name){ attrs.add(name); }, removeAttribute(name){ attrs.delete(name); }};
const field = {querySelector(selector){
  return selector === '[data-next-cockpit-held-line-source="0"]' ? source : null; }};
const box = {value:"Line one", dataset:{nextCockpitHeldLinesKey:"held:claude:focus-1:lines",
  nextCockpitHeldLineIndex:"0", nextCockpitHeldSaved:saved},
  closest(selector){
    if(selector === "[data-next-cockpit-held-lines-key]") return this;
    return selector === "[data-next-cockpit-held-field]" ? field : null; }};
__fire("input", {target:box});
console.log(JSON.stringify({saved, stale:attrs.has("data-next-cockpit-held-line-source-stale")}));
""",
        )
        assert isinstance(out, dict)
        self.assertEqual({"saved": "Line one", "stale": False}, out)


class PhoneWidthAndThePressTest(unittest.TestCase):
    """Layout F3 and consent F4, as the sheet states them; the fold and the press were measured."""

    def test_the_pending_lines_tools_take_their_own_row_on_a_phone(self) -> None:
        narrow = NEXT_STYLES[NEXT_STYLES.index("@media(max-width:760px){") :]
        self.assertRegex(
            narrow, r"\.next-session-panel \.next-cockpit-direction-tools\{grid-column:1/-1"
        )

    def test_an_untouched_draft_is_as_tall_as_its_text_focused_or_not(self) -> None:
        """Verifier V1: focus changes nothing, so Keep holds still under the press
        (consent F4) and no part of the draft Keep adopts is clipped."""
        rule = re.search(
            r"\.next-session-panel \.next-cockpit-held-field\[data-next-cockpit-drafted\]>"
            r"textarea\{([^}]*)\}",
            NEXT_STYLES,
        )
        assert rule is not None
        self.assertIn("field-sizing:content", rule.group(1))
        self.assertIn("height:auto", rule.group(1))
        self.assertNotRegex(NEXT_STYLES, r"\[data-next-cockpit-drafted\]>textarea:focus\{")

    def test_the_pending_line_is_as_tall_as_its_text_focused_or_not(self) -> None:
        """Verifier V3: a box that shrank on blur moved its save, a second Add and
        Keep out from under the mousedown that blurred it."""
        rule = re.search(
            r"\.next-session-panel \.next-cockpit-held-line\.next-cockpit-direction-line>"
            r"textarea\{([^}]*)\}",
            NEXT_STYLES,
        )
        assert rule is not None
        for declaration in ("field-sizing:content", "height:auto", "white-space:pre-wrap"):
            self.assertIn(declaration, rule.group(1))


if __name__ == "__main__":
    unittest.main()
