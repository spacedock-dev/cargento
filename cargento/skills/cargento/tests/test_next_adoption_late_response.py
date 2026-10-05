"""A late adoption response keeps what the reader did while it was open (DRC-4784).

`nextAdoptPrompt` adopts a prompt under Save intent's pending entry. The reply can arrive after the
reader has typed another goal, picked another prompt or left the session, and it used to delete the
held goal draft and the chosen prompt whatever they held by then, so the newer words vanished from
the box. The two paths that reach it are the untouched drafted prompt (first or latest) and a
prompt chosen from the menu. Only the draft or the choice that was actually adopted may go; the
explicit-direction paths already forget by equality (`nextIntentForgetAdopted`) and are held by
`test_next_intent_draft`.

A press that also changes the outcome lines chains a second request after the adoption. It writes
only the lines the press held, no goal, against the revision the adoption minted; what the reader
chose, typed or edited meanwhile is not read, and a failure between the two stages leaves the
adoption landed and every newer word held.

Every assertion is on what the page holds or draws after the held reply is let go.
"""

from __future__ import annotations

import json
import shutil
import unittest
from typing import Any

from .test_next_intent_draft import FIRST, GOAL_KEY, ROUTE, _DraftPage, intent_of
from .test_next_intent_draft import LATEST as DRAFT_LATEST
from .test_next_prompt_menu import CHOICES, SERVE_CHOICES, goal_box

LATEST = next(c["text"] for c in CHOICES if c["fact_id"] == "p-latest")
EXCERPT = next(c["text"] for c in CHOICES if c["fact_id"] == "p-long")
TYPED_LATE = "Words typed while the save was open"
REVISED = "Make the retry queue survive a restart, and say so on the board"
OTHER_KEY = "held:claude:another-session:goal"

# The annotate request is held until `__gate()` lets it go, so a test can act while it is open.
HOLD = """
let __holdAnnotate = false, __gate = null;
const __beforeHold = __fetchImpl;
__fetchImpl = (url, init) => {
  if(__holdAnnotate && String(url) === "/api/annotate" && init && init.method === "POST"){
    return new Promise(resolve => { __gate = () => resolve(__beforeHold(url, init)); });
  }
  return __beforeHold(url, init);
};
"""

# What the store publishes once an adoption lands, from the words the request named. A typed
# lines save after it changes nothing the goal holds.
LANDS = (
    '__reply["/api/annotate"] = body => { if(body.adopt) Object.assign(__s, {annotation_goal:'
    ' body.expected_prompt, annotation_goal_why:"", annotation_goal_source: body.adopt,'
    " annotation_goal_source_at: body.expected_prompt_at, annotation_revision:body.expected_revision + 1,"
    " annotation_revision_count:body.expected_revision + 1, annotation_at:105});"
    ' return {status:200, body:{ok:true, persisted:true, outcome:"stored", revision:body.expected_revision + 1,'
    " revision_count:body.expected_revision + 1, saved_revision:body.adopt ? body.expected_revision + 1 : null}}; };\n"
)
NOT_ON_DISK = (
    '__reply["/api/annotate"] = () => ({status:200, body:{ok:true, persisted:false,'
    ' outcome:"stored", revision:3, revision_count:3}});\n'
)
# The adoption lands as revision 1, and another tab saves revision 2 before this page refreshes.
# The store refuses any lines save that does not name the revision it holds, as the real one does.
CONCURRENT = (
    '__reply["/api/annotate"] = body => {\n'
    "  if(body.adopt){\n"
    "    Object.assign(__s, {annotation_goal: body.expected_prompt, annotation_goal_why:'',\n"
    "      annotation_goal_source: body.adopt, annotation_goal_source_at: body.expected_prompt_at,\n"
    "      annotation_at:105});\n"
    '    const answer = {ok:true, persisted:true, outcome:"stored", revision:1, revision_count:1, saved_revision:1};\n'
    "    Object.assign(__s, {annotation_revision:2, annotation_revision_count:2});\n"
    "    return {status:200, body:answer};\n"
    "  }\n"
    "  if(body.expected_revision !== __s.annotation_revision){\n"
    '    return {status:200, body:{ok:true, persisted:false, outcome:"refused",\n'
    "      revision:__s.annotation_revision, revision_count:__s.annotation_revision_count}};\n"
    "  }\n"
    "  __s.annotation_revision += 1; __s.annotation_revision_count += 1;\n"
    '  return {status:200, body:{ok:true, persisted:true, outcome:"stored",\n'
    "    revision:__s.annotation_revision, revision_count:__s.annotation_revision_count}};\n"
    "};\n"
)


# The adoption lands as in LANDS, and the lines save that follows is answered by `second`, a
# JavaScript function expression of the request body.
def lands_then(second: str) -> str:
    return (
        LANDS
        + '{ const __adopts = __reply["/api/annotate"];\n'
        + f'  __reply["/api/annotate"] = body => body.adopt ? __adopts(body) : ({second})(body); }}\n'
    )


PRESSED = 'nextCockpitHeldDrafts.set("held:claude:focus-1:lines", ["Pressed line"]);\n'
LINES_KEY = "held:claude:focus-1:lines"

PICK_LATEST = '__pick("p-latest");\nawait __settle();\n'
PICK_EXCERPT = '__pick("p-long");\nawait __settle();\n'
SETTLE = "await __settle();\nawait __settle();\nawait __settle();\n"
SAVE_KEY = "nextCockpitIntentKey(__s) + ':save'"


def type_goal(words: str) -> str:
    return f"__typeGoal({json.dumps(words)});\n"


REPORT = """
console.log(JSON.stringify({
  html: __els.app.innerHTML,
  drafts: Object.fromEntries(nextCockpitHeldDrafts),
  chosen: Object.fromEntries([...nextIntentChosenPrompts].map(([key, held]) => [key, held.factId])),
  posts: __posts.map(post => post.body),
  pending: [...nextPending.keys()],
  saved: __s.annotation_goal,
  revision: __s.annotation_revision,
}));
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class ALateAdoptionResponseTest(_DraftPage):
    def late(self, *, first: str = "", meanwhile: str = "", reply: str = LANDS) -> dict[str, Any]:
        """Press Save intent, do `meanwhile` while its request is open, then let the reply go.

        `first` runs before the press: the one choice that makes the save adopt a chosen prompt
        rather than the drafted first prompt.
        """
        out = self.drive(
            SERVE_CHOICES + HOLD + reply,
            first
            + '__holdAnnotate = true;\n__press("held-save", "intent");\nawait __settle();\n'
            + meanwhile
            + "__holdAnnotate = false;\n__gate();\n"
            + SETTLE
            + REPORT,
        )
        assert isinstance(out, dict)
        return out

    def drafted(self, out: dict[str, Any]) -> bool:
        return "data-next-cockpit-drafted" in intent_of(out["html"])

    # The untouched drafted prompt is what the press adopts.

    def test_an_adopted_draft_leaves_nothing_held_and_the_box_on_the_saved_words(self) -> None:
        out = self.late()
        self.assertEqual({}, out["drafts"])
        self.assertEqual({}, out["chosen"])
        self.assertEqual(FIRST, goal_box(out["html"]))
        self.assertFalse(self.drafted(out))
        self.assertEqual("first-prompt", out["posts"][0]["adopt"])

    def test_words_typed_while_the_draft_is_adopted_stay_in_the_box(self) -> None:
        out = self.late(meanwhile=type_goal(TYPED_LATE))
        self.assertEqual({GOAL_KEY: TYPED_LATE}, out["drafts"])
        self.assertEqual(TYPED_LATE, goal_box(out["html"]))

    def test_a_prompt_chosen_while_the_draft_is_adopted_stays_chosen(self) -> None:
        out = self.late(meanwhile=PICK_LATEST)
        self.assertEqual({GOAL_KEY: "p-latest"}, out["chosen"])
        self.assertEqual(LATEST, goal_box(out["html"]))
        self.assertTrue(self.drafted(out))

    def test_words_typed_away_and_back_to_the_adopted_draft_are_the_saved_words(self) -> None:
        # Edit-away and back ends on the words just saved, so nothing newer is lost by letting
        # the held copy go, and the box is not left marked as an unsaved edit.
        out = self.late(meanwhile=type_goal(FIRST + " x") + type_goal(FIRST))
        self.assertEqual({}, out["drafts"])
        self.assertEqual(FIRST, goal_box(out["html"]))
        self.assertFalse(self.drafted(out))

    def test_typing_away_and_choosing_the_draft_again_is_not_a_second_unsaved_edit(self) -> None:
        # The same ending by the menu: the prompt picked last is the one the store now holds.
        out = self.late(first=PICK_LATEST, meanwhile=PICK_EXCERPT + PICK_LATEST)
        self.assertEqual({}, out["chosen"])
        self.assertEqual({}, out["drafts"])
        self.assertEqual(LATEST, goal_box(out["html"]))
        self.assertFalse(self.drafted(out))

    # A prompt chosen from the menu is what the press adopts.

    def test_an_adopted_choice_leaves_nothing_held(self) -> None:
        out = self.late(first=PICK_LATEST)
        self.assertEqual({}, out["drafts"])
        self.assertEqual({}, out["chosen"])
        self.assertEqual(LATEST, goal_box(out["html"]))
        self.assertEqual("chosen-prompt", out["posts"][0]["adopt"])
        self.assertEqual("p-latest", out["posts"][0]["prompt_fact"])

    def test_words_typed_while_a_choice_is_adopted_stay_in_the_box(self) -> None:
        out = self.late(first=PICK_LATEST, meanwhile=type_goal(TYPED_LATE))
        self.assertEqual({GOAL_KEY: TYPED_LATE}, out["drafts"])
        self.assertEqual(TYPED_LATE, goal_box(out["html"]))

    def test_another_prompt_chosen_while_a_choice_is_adopted_stays_chosen(self) -> None:
        out = self.late(first=PICK_LATEST, meanwhile=PICK_EXCERPT)
        self.assertEqual({GOAL_KEY: "p-long"}, out["chosen"])
        self.assertEqual(EXCERPT, goal_box(out["html"]))
        self.assertTrue(self.drafted(out))

    def test_a_lines_save_does_not_adopt_the_prompt_chosen_after_the_press(self) -> None:
        out = self.late(
            first=PICK_LATEST
            + 'nextCockpitHeldDrafts.set("held:claude:focus-1:lines", ["Pressed line"]);\n',
            meanwhile=PICK_EXCERPT,
        )
        self.assertEqual(2, len(out["posts"]))
        self.assertEqual(LATEST, out["saved"])
        self.assertEqual({GOAL_KEY: "p-long"}, out["chosen"])
        self.assertEqual(EXCERPT, goal_box(out["html"]))
        self.assertIsNone(out["posts"][1]["goal"])
        self.assertEqual(["Pressed line"], out["posts"][1]["lines"])

    def test_a_lines_save_does_not_save_goal_words_typed_after_the_press(self) -> None:
        out = self.late(
            first=PICK_LATEST
            + 'nextCockpitHeldDrafts.set("held:claude:focus-1:lines", ["Pressed line"]);\n',
            meanwhile=type_goal(TYPED_LATE),
        )
        self.assertEqual(2, len(out["posts"]))
        self.assertEqual(TYPED_LATE, goal_box(out["html"]))
        self.assertEqual(TYPED_LATE, out["drafts"][GOAL_KEY])
        self.assertIsNone(out["posts"][1]["goal"])
        self.assertEqual(["Pressed line"], out["posts"][1]["lines"])

    def test_the_chained_request_sends_only_lines_present_when_save_was_pressed(self) -> None:
        out = self.late(
            first=PICK_LATEST
            + 'nextCockpitHeldDrafts.set("held:claude:focus-1:lines", ["Pressed line"]);\n',
            meanwhile='nextCockpitHeldDrafts.set("held:claude:focus-1:lines", ["Later line"]);\n',
        )
        self.assertEqual(["Pressed line"], out["posts"][1]["lines"])
        self.assertEqual(["Later line"], out["drafts"]["held:claude:focus-1:lines"])

    # What the press held is saved, once, against the revision its adoption minted.

    def test_untouched_first_or_latest_draft_and_lines_are_saved_together(self) -> None:
        for first, source, words in (
            ("", "first-prompt", FIRST),
            ('__s.first_prompt=""; __s.first_prompt_at=null;\n', "latest-prompt", DRAFT_LATEST),
            (type_goal(FIRST + " edited") + type_goal(FIRST), "first-prompt", FIRST),
        ):
            with self.subTest(source=source, first=first):
                out = self.late(first=first + PRESSED)
                self.assertEqual(2, len(out["posts"]), "the drafted goal must be adopted first")
                self.assertEqual(source, out["posts"][0]["adopt"])
                self.assertEqual(words, out["posts"][0]["expected_prompt"])
                self.assertEqual(words, out["saved"])
                self.assertEqual(["Pressed line"], out["posts"][1]["lines"])
                self.assertIsNone(out["posts"][1]["goal"])
                self.assertEqual(1, out["posts"][1]["expected_revision"])
                self.assertNotIn(LINES_KEY, out["drafts"])

    def test_a_draft_with_lines_freezes_the_press_and_keeps_newer_edits(self) -> None:
        out = self.late(
            first=PRESSED,
            meanwhile=type_goal(TYPED_LATE)
            + f"nextCockpitHeldDrafts.set({json.dumps(LINES_KEY)}, ['Newer held line']);\n",
        )
        self.assertEqual(FIRST, out["posts"][0]["expected_prompt"])
        self.assertEqual(["Pressed line"], out["posts"][1]["lines"])
        self.assertEqual(FIRST, out["saved"])
        self.assertEqual(TYPED_LATE, out["drafts"][GOAL_KEY])
        self.assertEqual(["Newer held line"], out["drafts"][LINES_KEY])

    def test_a_draft_with_lines_keeps_its_lines_if_adoption_is_refused(self) -> None:
        out = self.late(first=PRESSED, reply=NOT_ON_DISK)
        self.assertEqual(1, len(out["posts"]))
        self.assertEqual("first-prompt", out["posts"][0]["adopt"])
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])

    def test_cancelled_draft_adoption_with_lines_keeps_the_press_words(self) -> None:
        out = self.drive(
            SERVE_CHOICES + HOLD + LANDS,
            PRESSED
            + '__holdAnnotate = true;\n__press("held-save", "intent");\nawait __settle();\n'
            + f"nextPending.get({SAVE_KEY}).controller.abort();\n"
            + SETTLE
            + REPORT,
        )
        assert isinstance(out, dict)
        self.assertEqual([], out["pending"])
        self.assertEqual("", out["saved"])
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])

    def test_a_typed_new_goal_and_lines_use_one_direct_save(self) -> None:
        out = self.late(first=type_goal(TYPED_LATE) + PRESSED)
        self.assertEqual(1, len(out["posts"]))
        self.assertNotIn("adopt", out["posts"][0])
        self.assertEqual(TYPED_LATE, out["posts"][0]["goal"])
        self.assertEqual(["Pressed line"], out["posts"][0]["lines"])

    def test_lines_beside_an_existing_saved_goal_use_one_direct_save(self) -> None:
        stored = (
            '__s.annotation_goal="Already saved"; __s.annotation_goal_why="";'
            "__s.annotation_revision=3; __s.annotation_revision_count=3;\n"
        )
        out = self.late(first=stored + PRESSED)
        self.assertEqual(1, len(out["posts"]))
        self.assertNotIn("adopt", out["posts"][0])
        self.assertIsNone(out["posts"][0]["goal"])
        self.assertEqual(3, out["posts"][0]["expected_revision"])
        self.assertEqual("Already saved", out["saved"])
        self.assertEqual(["Pressed line"], out["posts"][0]["lines"])

    def test_the_lines_the_press_held_are_still_saved_after_the_adoption(self) -> None:
        out = self.late(first=PICK_LATEST + PRESSED)
        self.assertEqual(LATEST, out["saved"])
        self.assertEqual(
            {
                "harness": "claude",
                "sid": "focus-1",
                "goal": None,
                "lines": ["Pressed line"],
                "origins": [0],
                "expected_revision": 1,
            },
            out["posts"][1],
        )
        self.assertNotIn(LINES_KEY, out["drafts"])
        self.assertEqual({}, out["chosen"])

    def test_a_choice_with_no_line_change_makes_one_request(self) -> None:
        out = self.late(first=PICK_LATEST)
        self.assertEqual(1, len(out["posts"]))

    def test_the_chained_lines_are_refused_over_a_revision_saved_after_the_adoption(self) -> None:
        # The refreshed row already shows another tab's revision 2. The lines are written against
        # the 1 the adoption minted, so the store refuses them rather than the page naming 4.
        out = self.late(first=PICK_LATEST + PRESSED, reply=CONCURRENT)
        self.assertEqual(2, len(out["posts"]))
        self.assertEqual(1, out["posts"][1]["expected_revision"])
        self.assertEqual(2, out["revision"], "the other tab's revision was not written over")
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertIn("Not saved. The server refused the write", out["html"])

    # A failure between the stages leaves the adoption as it landed and the reader's words held.

    def test_a_refused_adoption_sends_no_lines_and_keeps_both_drafts(self) -> None:
        out = self.late(first=PICK_LATEST + PRESSED, reply=NOT_ON_DISK)
        self.assertEqual(1, len(out["posts"]))
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertEqual({GOAL_KEY: "p-latest"}, out["chosen"])

    def test_a_reply_that_rereads_a_newer_revision_does_not_chain_lines(self) -> None:
        # The handler reads back after the store lock. Another save can land before that read;
        # revision 2 is then an honest current revision, but is not this adoption's revision 1.
        reread = CONCURRENT.replace("revision:1, revision_count:1", "revision:2, revision_count:2")
        out = self.late(first=PICK_LATEST + PRESSED, reply=reread)
        self.assertEqual(1, len(out["posts"]), "no lines write may name somebody else's revision")
        self.assertEqual(2, out["revision"])
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertIn("Not saved. The server refused the write", out["html"])

    def test_discarded_rebirth_uses_the_actual_locked_revision(self) -> None:
        reborn = LANDS.replace("body.expected_revision + 1", "4")
        out = self.late(first=PICK_LATEST + PRESSED, reply=reborn)
        self.assertEqual(2, len(out["posts"]))
        self.assertEqual(4, out["posts"][1]["expected_revision"])
        self.assertNotIn(LINES_KEY, out["drafts"])

    def test_unchanged_goal_cannot_upgrade_the_frozen_checklist_revision(self) -> None:
        upgraded = (
            '__reply["/api/annotate"] = body => { Object.assign(__s, {annotation_revision:2,'
            ' annotation_goal:body.expected_prompt, annotation_goal_why:""});'
            ' return {status:200, body:{ok:true, persisted:true, outcome:"unchanged",'
            " revision:2, saved_revision:2}}; };\n"
        )
        out = self.late(first=PICK_LATEST + PRESSED, reply=upgraded)
        self.assertEqual(1, len(out["posts"]))
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertIn("Not saved. The server refused the write", out["html"])

    def test_an_adoption_that_could_not_be_read_sends_no_lines(self) -> None:
        broken = '__reply["/api/annotate"] = () => { throw new Error("no answer"); };\n'
        out = self.late(first=PICK_LATEST + PRESSED, reply=broken)
        self.assertEqual(1, len(out["posts"]))
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertIn("did not answer", out["html"])

    def test_an_adoption_that_names_no_revision_sends_no_lines(self) -> None:
        unnamed = (
            '__reply["/api/annotate"] = () => ({status:200, body:{ok:true, persisted:true,'
            ' outcome:"stored"}});\n'
        )
        out = self.late(first=PICK_LATEST + PRESSED, reply=unnamed)
        self.assertEqual(1, len(out["posts"]))
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertIn("Not saved. The server refused the write", out["html"])

    def test_refused_lines_leave_the_adopted_goal_and_a_newer_choice(self) -> None:
        refused = (
            '() => ({status:200, body:{ok:true, persisted:false, outcome:"refused",'
            " revision:3, revision_count:3}})"
        )
        out = self.late(
            first=PICK_LATEST + PRESSED, meanwhile=PICK_EXCERPT, reply=lands_then(refused)
        )
        self.assertEqual(2, len(out["posts"]))
        self.assertEqual(LATEST, out["saved"], "the adoption landed and stays")
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertEqual({GOAL_KEY: "p-long"}, out["chosen"])
        self.assertIn("Not saved. The server refused the write", out["html"])

    def test_lost_lines_reply_is_unconfirmed_and_keeps_the_lines(self) -> None:
        lost = '() => { throw new Error("no answer"); }'
        out = self.late(first=PICK_LATEST + PRESSED, reply=lands_then(lost))
        self.assertEqual(2, len(out["posts"]))
        self.assertEqual(LATEST, out["saved"])
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertIn("did not answer", out["html"])

    def test_a_save_cancelled_between_the_stages_keeps_the_lines_and_the_newer_choice(self) -> None:
        # The adoption lands, the lines request is held open, and the reader cancels it.
        out = self.drive(
            SERVE_CHOICES + HOLD + LANDS,
            PICK_LATEST
            + PRESSED
            + '__holdAnnotate = true;\n__press("held-save", "intent");\nawait __settle();\n'
            + PICK_EXCERPT
            + "const __adoption = __gate;\n__adoption();\n"
            + SETTLE
            + 'if(__gate === __adoption) throw new Error("the lines request was never opened");\n'
            + f"nextPending.get({SAVE_KEY}).controller.abort();\n"
            + SETTLE
            + REPORT,
        )
        assert isinstance(out, dict)
        self.assertEqual([], out["pending"], "the abort ended the request")
        self.assertEqual(1, len(out["posts"]), "the held lines request was never answered")
        self.assertEqual(LATEST, out["saved"])
        self.assertEqual(["Pressed line"], out["drafts"][LINES_KEY])
        self.assertEqual({GOAL_KEY: "p-long"}, out["chosen"])

    def test_the_same_prompt_offered_again_with_other_words_is_a_newer_choice(self) -> None:
        # A refreshed record can offer one fact with its whole words after an excerpt: the fact
        # is the same and the words, and the time, are not what the adoption named.
        revised = (
            "for(const [, entry] of nextCockpitContexts){\n"
            "  if(entry && entry.data && Array.isArray(entry.data.prompt_choices)){\n"
            "    entry.data.prompt_choices = entry.data.prompt_choices.map(choice =>\n"
            f'      choice.fact_id === "p-latest" ? {{...choice, text: {json.dumps(REVISED)}, at: 141}}'
            " : choice);\n  }\n}\nnextIntentPromptLists.clear();\n" + PICK_LATEST
        )
        out = self.late(first=PICK_LATEST, meanwhile=revised)
        self.assertEqual({GOAL_KEY: "p-latest"}, out["chosen"])
        self.assertEqual(REVISED, goal_box(out["html"]))
        self.assertEqual(LATEST, out["posts"][0]["expected_prompt"])

    # Leaving the session is not an edit, and another session's words are never this one's.

    def test_another_sessions_held_words_are_untouched(self) -> None:
        other = (
            f"nextCockpitHeldDrafts.set({json.dumps(OTHER_KEY)}, 'Words held elsewhere');\n"
            f"nextIntentChosenPrompts.set({json.dumps(OTHER_KEY)}, {{factId:'p-x', text:'x', at:5}});\n"
        )
        out = self.late(meanwhile=other)
        self.assertEqual("Words held elsewhere", out["drafts"][OTHER_KEY])
        self.assertEqual("p-x", out["chosen"][OTHER_KEY])
        self.assertNotIn(GOAL_KEY, out["drafts"])

    def test_words_typed_before_leaving_the_session_are_there_on_return(self) -> None:
        out = self.drive(
            SERVE_CHOICES + HOLD + LANDS,
            '__holdAnnotate = true;\n__press("held-save", "intent");\nawait __settle();\n'
            + type_goal(TYPED_LATE)
            + 'navigateNext({view:"sessions"});\nawait __settle();\n'
            "__holdAnnotate = false;\n__gate();\n" + SETTLE + ROUTE + "\n" + SETTLE + REPORT,
        )
        assert isinstance(out, dict)
        self.assertEqual({GOAL_KEY: TYPED_LATE}, out["drafts"])
        self.assertEqual(TYPED_LATE, goal_box(out["html"]))

    # No adoption landed, so nothing the reader holds is theirs to lose.

    def test_a_cancelled_save_keeps_what_was_typed_and_adopts_nothing(self) -> None:
        out = self.drive(
            SERVE_CHOICES + HOLD + LANDS,
            '__holdAnnotate = true;\n__press("held-save", "intent");\nawait __settle();\n'
            + type_goal(TYPED_LATE)
            + f"nextPending.get({SAVE_KEY}).controller.abort();\n"
            + SETTLE
            + REPORT,
        )
        assert isinstance(out, dict)
        self.assertEqual([], out["pending"], "the abort ended the request")
        self.assertEqual("", out["saved"], "nothing was adopted")
        self.assertEqual({GOAL_KEY: TYPED_LATE}, out["drafts"])
        self.assertEqual(TYPED_LATE, goal_box(out["html"]))

    def test_a_cancelled_save_keeps_the_choice(self) -> None:
        out = self.drive(
            SERVE_CHOICES + HOLD + LANDS,
            PICK_LATEST
            + '__holdAnnotate = true;\n__press("held-save", "intent");\nawait __settle();\n'
            + PICK_EXCERPT
            + f"nextPending.get({SAVE_KEY}).controller.abort();\n"
            + SETTLE
            + REPORT,
        )
        assert isinstance(out, dict)
        self.assertEqual([], out["pending"], "the abort ended the request")
        self.assertEqual("", out["saved"], "nothing was adopted")
        self.assertEqual({GOAL_KEY: "p-long"}, out["chosen"])
        self.assertEqual(EXCERPT, goal_box(out["html"]))

    def test_a_reply_that_did_not_reach_disk_keeps_the_typed_words_and_the_choice(self) -> None:
        typed = self.late(meanwhile=type_goal(TYPED_LATE), reply=NOT_ON_DISK)
        self.assertEqual({GOAL_KEY: TYPED_LATE}, typed["drafts"])
        self.assertEqual(TYPED_LATE, goal_box(typed["html"]))
        chosen = self.late(first=PICK_LATEST, meanwhile=PICK_EXCERPT, reply=NOT_ON_DISK)
        self.assertEqual({GOAL_KEY: "p-long"}, chosen["chosen"])
        self.assertEqual(EXCERPT, goal_box(chosen["html"]))

    def test_a_reply_that_could_not_be_read_keeps_the_typed_words(self) -> None:
        broken = '__reply["/api/annotate"] = () => { throw new Error("no answer"); };\n'
        out = self.late(meanwhile=type_goal(TYPED_LATE), reply=broken)
        self.assertEqual({GOAL_KEY: TYPED_LATE}, out["drafts"])
        self.assertEqual(TYPED_LATE, goal_box(out["html"]))


if __name__ == "__main__":
    unittest.main()
