"""A late adoption response keeps what the reader did while it was open (DRC-4784).

`nextAdoptPrompt` adopts a prompt under Save intent's pending entry. The reply can arrive after the
reader has typed another goal, picked another prompt or left the session, and it used to delete the
held goal draft and the chosen prompt whatever they held by then, so the newer words vanished from
the box. The two paths that reach it are the untouched drafted prompt (first or latest) and a
prompt chosen from the menu. Only the draft or the choice that was actually adopted may go; the
explicit-direction paths already forget by equality (`nextIntentForgetAdopted`) and are held by
`test_next_intent_draft`.

Every assertion is on what the page holds or draws after the held reply is let go.
"""

from __future__ import annotations

import json
import shutil
import unittest
from typing import Any

from .test_next_intent_draft import FIRST, GOAL_KEY, ROUTE, _DraftPage, intent_of
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

# What the store publishes once an adoption lands, from the words the request named.
LANDS = (
    '__reply["/api/annotate"] = body => { Object.assign(__s, {annotation_goal:'
    ' body.expected_prompt, annotation_goal_why:"", annotation_goal_source: body.adopt,'
    " annotation_goal_source_at: body.expected_prompt_at, annotation_revision:3,"
    " annotation_revision_count:3, annotation_at:105});"
    ' return {status:200, body:{ok:true, persisted:true, outcome:"stored", revision:3,'
    " revision_count:3}}; };\n"
)
NOT_ON_DISK = (
    '__reply["/api/annotate"] = () => ({status:200, body:{ok:true, persisted:false,'
    ' outcome:"stored", revision:3, revision_count:3}});\n'
)

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
