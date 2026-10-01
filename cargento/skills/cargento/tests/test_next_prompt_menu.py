""" "Use your prompt": one disclosure menu of your own prompts that fills the goal box (DRC-4758 D2).

The owner's walk found the goal row offering "Use a prompt", which opened a nested "Your latest
prompt", which held "Use latest prompt without checking": two nested disclosures and a save that
skipped the box. Owner ruling Q7 (2026-10-01): one "Use your prompt" menu lists up to five of the
reader's own prompts, published by the server as `prompt_choices`, and choosing one fills the
Goal box as a pending adoption, never as a typed edit. The critic's correction 14 makes the menu a
`<details>` of `<button>` options with their own focus keys, so a poll redraw restores it through
the disclosure lane rather than closing it mid-choice; correction 11 keeps an excerpt marked in
view.

Every assertion is on the assembled bundle's rendered markup, what a sighted reader sees of it, or
what the page sends.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from typing import Any

from cargento_runtime import reading as runtime_reading

from . import test_next_cockpit as cockpit_tests
from .test_next_drift_panel import routes
from .test_next_intent_draft import (
    ADD_EDITED,
    EDITED,
    FIRST,
    GOAL_KEY,
    TYPED,
    _DraftPage,
    drift_of,
    intent_of,
)
from .visible_text import visible_text

CHOSEN = "Make the retry queue survive a restart"
LONG = "Wire the dead-letter lane into the board and then…"
CHOICES = [
    {"fact_id": "p-first", "at": 99, "text": FIRST, "cut": False},
    {"fact_id": "p-latest", "at": 140, "text": CHOSEN, "cut": False},
    {"fact_id": "p-long", "at": 120, "text": LONG, "cut": True},
]

# The focused project context, as `/api/project-context?session=` publishes it, with the
# reader's prompts beside it. `__choices` is reassigned by a test that changes the record.
SERVE_CHOICES = (
    "let __choices = "
    + json.dumps(CHOICES)
    + """;
const __beforeChoices = __fetchImpl;
__fetchImpl = async (url, init) => {
  const answer = await __beforeChoices(url, init);
  if(init || !String(url).startsWith("/api/project-context")) return answer;
  const data = await answer.json();
  return {ok:true, json:async () => ({...data, prompt_choices:__choices})};
};
"""
)


def menu_of(html: str) -> str:
    found = re.search(r'<details class="next-intent-prompt-menu"[\s\S]*?</details>', html)
    assert found is not None, "no prompt menu"
    return found.group(0)


def options_of(html: str) -> list[str]:
    return re.findall(
        r'<button[^>]*data-next-cockpit-action="prompt-choose"[^>]*>[\s\S]*?</button>',
        menu_of(html),
    )


def goal_box(html: str) -> str:
    found = re.search(
        r'<textarea[^>]*data-next-cockpit-held-kind="goal"[^>]*>([^<]*)<', intent_of(html)
    )
    assert found is not None
    return found.group(1)


CHOOSE = '__press("prompt-choose", "p-latest");\nawait __settle();\n'
HTML = "console.log(JSON.stringify(__els.app.innerHTML));"


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheMenuIsOneDisclosureOfButtonsTest(_DraftPage):
    def page(self, setup: str = "", after: str = "") -> Any:
        return self.drive(SERVE_CHOICES + setup, after)

    def test_one_menu_named_use_your_prompt_and_no_nested_disclosure(self) -> None:
        out = self.page()
        assert isinstance(out, str)
        intent = intent_of(out)
        menu = menu_of(out)
        self.assertEqual(1, intent.count('class="next-intent-prompt-menu"'))
        self.assertRegex(menu, r"<summary[^>]*>Use your prompt</summary>")
        # One level: the old menu nested a second disclosure for the latest prompt.
        self.assertEqual(1, menu.count("<details"))
        self.assertNotIn('role="listbox"', menu)
        self.assertNotIn("<select", intent)
        for gone in ("Use a prompt", "Your latest prompt", "without checking"):
            self.assertNotIn(gone, out)
        # Reused restore lane: the menu carries the disclosure key the redraw reopens.
        self.assertIn("adopt:choices", menu)

    def test_the_options_are_the_published_prompts_in_order_with_their_own_times(self) -> None:
        out = self.page(
            after="console.log(JSON.stringify({html:__els.app.innerHTML, "
            "clocks:[99,140,120].map(nextSessionClock)}));"
        )
        assert isinstance(out, dict)
        options = options_of(out["html"])
        self.assertEqual(3, len(options))
        texts = [visible_text(option).strip() for option in options]
        first, latest, earlier = out["clocks"]
        self.assertTrue(texts[0].startswith(f"First prompt · {first}"), texts[0])
        self.assertIn(FIRST, texts[0])
        self.assertTrue(texts[1].startswith(f"Latest prompt · {latest}"), texts[1])
        self.assertIn(CHOSEN, texts[1])
        self.assertTrue(texts[2].startswith(f"Earlier prompt · {earlier}"), texts[2])
        # An excerpt says so in the option itself (critic 11), and a whole prompt does not.
        self.assertIn("Shown excerpt only.", texts[2])
        self.assertNotIn("Shown excerpt only.", texts[0] + texts[1])
        for option in options:
            self.assertIn('type="button"', option)
            self.assertIn("next-action", option)
            self.assertNotIn("next-action--primary", option)

    def test_every_option_keeps_its_own_focus_key_across_a_redraw(self) -> None:
        out = self.page(
            after="const before = __els.app.innerHTML; renderNext();\n"
            "console.log(JSON.stringify({before, after:__els.app.innerHTML}));"
        )
        assert isinstance(out, dict)
        keys = [
            re.search(r'data-next-focus="([^"]*)"', option).group(1)  # type: ignore[union-attr]
            for option in options_of(out["before"])
        ]
        self.assertEqual(
            [
                f"{GOAL_KEY}:prompt:p-first",
                f"{GOAL_KEY}:prompt:p-latest",
                f"{GOAL_KEY}:prompt:p-long",
            ],
            keys,
        )
        for key in keys:
            self.assertIn(f'data-next-focus="{key}"', out["after"])

    def test_no_menu_without_published_prompts_or_with_annotations_off(self) -> None:
        none = self.page("__choices = [];\n")
        off = self.page("__dashboard.annotate = false;\n")
        assert isinstance(none, str)
        assert isinstance(off, str)
        self.assertNotIn("next-intent-prompt-menu", none)
        self.assertNotIn("next-intent-prompt-menu", off)
        self.assertNotIn("Use your prompt", none + off)

    def test_a_malformed_choice_is_not_offered(self) -> None:
        out = self.page(
            '__choices = [{fact_id:"", at:99, text:"No id"}, {fact_id:"x", at:null, text:"No time"},'
            ' {fact_id:"y", at:99, text:""}, {fact_id:"p-ok", at:99, text:"Fine"}];\n'
        )
        assert isinstance(out, str)
        options = options_of(out)
        self.assertEqual(1, len(options))
        self.assertIn("Fine", options[0])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ChoosingFillsTheGoalAsAPendingAdoptionTest(_DraftPage):
    def page(self, setup: str = "", after: str = "") -> Any:
        return self.drive(SERVE_CHOICES + setup, after)

    def test_choosing_fills_the_box_unsaved_marked_and_sends_nothing(self) -> None:
        out = self.page(
            after=CHOOSE + "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts, "
            "renders:__renders, held:nextCockpitHeldDrafts.has(" + json.dumps(GOAL_KEY) + "), "
            "clock:nextSessionClock(140)}));"
        )
        assert isinstance(out, dict)
        html = out["html"]
        self.assertEqual(CHOSEN, goal_box(html))
        self.assertEqual([], out["posts"])
        # A pending adoption, not a typed edit: nothing is held as the reader's typing, the
        # field carries the draft's tint, and Looks right is the save.
        self.assertFalse(out["held"])
        intent = intent_of(html)
        self.assertIn("data-next-cockpit-drafted", intent)
        seen = visible_text(intent)
        self.assertIn(f"from your prompt · {out['clock']}", seen)
        self.assertIn("Looks right", seen)
        self.assertIn({"named": GOAL_KEY}, out["renders"])

    def test_choosing_says_so_politely(self) -> None:
        out = self.page(
            cockpit_tests.CockpitCuesReachTheReaderTest.ANNOUNCER_DOM,
            CHOOSE + 'console.log(JSON.stringify(wrote("next-cockpit-cue-status")));',
        )
        self.assertEqual(["Goal filled from your prompt. Not saved."], out)

    def test_an_excerpt_stays_marked_in_view_once_chosen(self) -> None:
        out = self.page(after='__press("prompt-choose", "p-long");\nawait __settle();\n' + HTML)
        assert isinstance(out, str)
        self.assertEqual(LONG, goal_box(out))
        self.assertIn("Shown excerpt only.", visible_text(intent_of(out)))

    def test_looks_right_adopts_the_choice_by_its_fact_and_time(self) -> None:
        out = self.page(
            after=CHOOSE + '__press("draft-confirm");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts));"
        )
        assert isinstance(out, list)
        self.assertEqual(1, len(out))
        self.assertEqual("/api/annotate", out[0]["url"])
        self.assertEqual(
            {
                "harness": "claude",
                "sid": "focus-1",
                "adopt": runtime_reading.PROMPT_CHOSEN,
                "prompt_fact": "p-latest",
                "expected_prompt": CHOSEN,
                "expected_prompt_at": 140,
                "expected_revision": 0,
            },
            out[0]["body"],
        )

    def test_analyze_over_the_choice_adopts_it_not_the_first_prompt(self) -> None:
        out = self.page(
            "__semantic.facts = __semantic.facts.filter(f => f.type !== 'user_message');\n",
            CHOOSE + '__press("reading-ask");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts));",
        )
        assert isinstance(out, list)
        self.assertEqual("/api/reading", out[0]["url"])
        body = out[0]["body"]
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, body["adopt"])
        self.assertEqual("p-latest", body["prompt_fact"])
        self.assertEqual(CHOSEN, body["expected_prompt"])
        self.assertEqual(140, body["expected_prompt_at"])

    def test_one_keystroke_after_the_fill_makes_it_typed(self) -> None:
        out = self.page(
            after=CHOOSE + f"__typeGoal({json.dumps(CHOSEN + '!')});\n"
            '__press("held-save", "intent");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts));"
        )
        assert isinstance(out, list)
        self.assertEqual(1, len(out))
        body = out[0]["body"]
        self.assertEqual(CHOSEN + "!", body.get("goal"))
        self.assertNotIn("adopt", body)
        self.assertNotIn("prompt_fact", body)

    def test_a_choice_replaces_what_the_box_held(self) -> None:
        out = self.page(after='__typeGoal("Half a sentence");\n' + CHOOSE + HTML)
        assert isinstance(out, str)
        self.assertEqual(CHOSEN, goal_box(out))
        self.assertIn("data-next-cockpit-drafted", intent_of(out))

    def test_a_typed_save_puts_the_typed_words_in_the_box_not_the_choice(self) -> None:
        typed = CHOSEN + "!"
        out = self.page(
            after=CHOOSE + f"__typeGoal({json.dumps(typed)});\n"
            '__reply["/api/annotate"] = () => { Object.assign(__s, {annotation_goal:'
            + json.dumps(typed)
            + ', annotation_goal_why:"", annotation_goal_source:"typed", annotation_revision:1,'
            " annotation_revision_count:1}); return {status:200, body:{ok:true, persisted:true,"
            ' outcome:"stored"}}; };\n'
            '__press("held-save", "intent");\nawait __settle();\nawait __settle();\n' + HTML
        )
        assert isinstance(out, str)
        self.assertEqual(typed, goal_box(out))
        self.assertNotIn("data-next-cockpit-drafted", intent_of(out))

    def test_escape_in_the_goal_box_drops_the_choice(self) -> None:
        out = self.page(
            after=CHOOSE + '__fire("keydown", {key:"Escape", preventDefault(){}, target:{'
            "dataset:{nextCockpitHeldKey:" + json.dumps(GOAL_KEY) + "}, "
            'closest(selector){ return selector === "[data-next-cockpit-held-key]" ? this : null; }'
            "}});\nawait __settle();\n" + HTML
        )
        assert isinstance(out, str)
        self.assertEqual(FIRST, goal_box(out))

    def test_a_changed_prompt_drops_the_choice(self) -> None:
        out = self.page(
            after=CHOOSE + "__choices = [{fact_id:'p-latest', at:140, text:'Something new', "
            "cut:false}];\nnextData.generated = (nextData.generated || 0) + 1;\n"
            "await refreshNext();\nawait __settle();\nawait __settle();\n" + HTML
        )
        assert isinstance(out, str)
        # Back to the first-prompt draft, never the new words under the old choice.
        self.assertEqual(FIRST, goal_box(out))

    def test_undo_changes_drops_the_choice(self) -> None:
        out = self.page(
            after=CHOOSE + '__press("held-undo", "intent");\nawait __settle();\n' + HTML
        )
        assert isinstance(out, str)
        self.assertEqual(FIRST, goal_box(out))

    def test_clear_drops_the_choice_and_empties_the_box(self) -> None:
        out = self.page(after=CHOOSE + '__press("held-clear", "goal");\nawait __settle();\n' + HTML)
        assert isinstance(out, str)
        self.assertEqual("", goal_box(out))
        self.assertNotIn(CHOSEN, intent_of(out).split("next-intent-prompt-menu")[0])

    def test_after_clear_the_same_words_typed_back_are_typed(self) -> None:
        out = self.page(
            after=CHOOSE + '__press("held-clear", "goal");\nawait __settle();\n'
            f"__typeGoal({json.dumps(CHOSEN)});\nrenderNext();\n" + HTML
        )
        assert isinstance(out, str)
        self.assertEqual(CHOSEN, goal_box(out))
        self.assertNotIn("data-next-cockpit-drafted", intent_of(out))

    def test_adding_a_direction_over_the_choice_waits_for_its_save(self) -> None:
        # `add_direction` adopts only the first or latest prompt, so the page sends no save
        # the store would refuse, and says why beside the line.
        out = self.page(
            '__reply["/api/direction"] = body => ({status:200, body:{ok:true, '
            'fact_id:body.fact_id, text:"Newest direction", clipped:false, fits:true}});\n',
            # The first prompt chosen, so the record's two directions after it are later.
            '__press("prompt-choose", "p-first");\nawait __settle();\n'
            '__press("direction-add", __argOf("direction-add"));\n'
            "await __settle();\nawait __settle();\n"
            '__press("direction-save");\nawait __settle();\n'
            "console.log(JSON.stringify({posts:__posts, html:__els.app.innerHTML}));",
        )
        assert isinstance(out, dict)
        self.assertEqual(["/api/direction"], [post["url"] for post in out["posts"]])
        self.assertIn(ADD_EDITED, out["html"])
        # The sentence sends the reader to Save intent, so Save intent can be pressed (INT-5).
        save = re.search(
            r'<button[^>]*data-next-cockpit-action="held-save"[^>]*>', intent_of(out["html"])
        )
        assert save is not None
        self.assertNotIn("aria-disabled", save.group(0))

    def test_save_intent_over_an_empty_goal_adopts_the_choice(self) -> None:
        out = self.page(
            after='__press("prompt-choose", "p-first");\nawait __settle();\n'
            '__press("held-save", "intent");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts.map(post => post.body)));"
        )
        assert isinstance(out, list)
        self.assertEqual(1, len(out), out)
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, out[0]["adopt"])
        self.assertEqual("p-first", out[0]["prompt_fact"])
        self.assertNotIn("goal", out[0])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ChoosingOverASavedGoalTest(_DraftPage):
    def page(self, after: str) -> Any:
        return self.drive(SERVE_CHOICES + TYPED, after)

    def test_the_box_holds_the_choice_and_analyze_waits_for_the_save(self) -> None:
        out = self.page(
            CHOOSE + 'const before = __els.app.innerHTML;\n__press("reading-ask");\n'
            "await __settle();\nconsole.log(JSON.stringify({before, after:__els.app.innerHTML, "
            "posts:__posts}));"
        )
        assert isinstance(out, dict)
        self.assertEqual(CHOSEN, goal_box(out["before"]))
        # `/api/reading` refuses an implicit adoption over saved words, so the press is
        # refused on the page rather than sent.
        self.assertEqual([], out["posts"])
        self.assertIn(EDITED, visible_text(drift_of(out["after"])))
        save = re.search(
            r'<button[^>]*data-next-cockpit-action="held-save"[^>]*>', intent_of(out["before"])
        )
        assert save is not None
        self.assertNotIn("aria-disabled", save.group(0))

    def test_the_saved_words_level_still_stands_beside_the_choice(self) -> None:
        # The level is a fact about the saved words, as it is beside a typed edit; only a
        # draft over an empty goal takes it away (item 2 of DEC-26).
        out = self.page(CHOOSE + HTML)
        assert isinstance(out, str)
        self.assertIn("Not checked yet", visible_text(drift_of(out)))

    def test_save_intent_adopts_the_choice_over_the_saved_revision(self) -> None:
        out = self.page(
            CHOOSE + '__press("held-save", "intent");\nawait __settle();\n'
            "console.log(JSON.stringify(__posts));"
        )
        assert isinstance(out, list)
        self.assertEqual(1, len(out))
        body = out[0]["body"]
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, body["adopt"])
        self.assertEqual("p-latest", body["prompt_fact"])
        self.assertEqual(2, body["expected_revision"])
        self.assertNotIn("goal", body)

    def test_the_lines_after_an_adopted_choice_name_the_revision_it_minted(self) -> None:
        # A real refresh hands back new row objects, so the lines save must read the revision
        # off the refreshed row, never the row the click held (INT-2).
        out = self.drive(
            SERVE_CHOICES + TYPED + '__s.annotation_line_1 = "old line";\n',
            "let __rev = 2;\n"
            '__reply["/api/annotate"] = () => { __rev += 1; return {status:200, body:{ok:true, '
            'persisted:true, outcome:"stored", revision:__rev}}; };\n'
            "const __plain = __fetchImpl;\n"
            "__fetchImpl = async (url, init) => {\n"
            "  const answer = await __plain(url, init);\n"
            '  if(init || !String(url).startsWith("/api/data")) return answer;\n'
            "  const data = JSON.parse(JSON.stringify(await answer.json()));\n"
            "  if(data && data.sessions && data.sessions[0]) data.sessions[0].annotation_revision = __rev;\n"
            "  return {ok:true, json:async () => data};\n"
            "};\n" + CHOOSE + '__fire("input", {target:{value:"new line", dataset:'
            '{nextCockpitHeldLineIndex:"0", nextCockpitHeldLinesKey:'
            + json.dumps(GOAL_KEY.rsplit(":", 1)[0] + ":lines")
            + '}, closest(selector){ return selector.includes("lines-key") || '
            'selector.includes("line-index") ? this : null; }}});\n'
            '__press("held-save", "intent");\n'
            "await __settle();\nawait __settle();\nawait __settle();\n"
            "console.log(JSON.stringify(__posts.map(post => post.body)));",
        )
        assert isinstance(out, list)
        self.assertEqual(2, len(out), out)
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, out[0]["adopt"])
        self.assertEqual(2, out[0]["expected_revision"])
        self.assertEqual(["new line"], out[1]["lines"])
        self.assertEqual(3, out[1]["expected_revision"])

    def test_a_landed_choice_lets_the_saved_words_stand(self) -> None:
        out = self.page(
            CHOOSE + "Object.assign(__s, {annotation_goal:" + json.dumps(CHOSEN) + ", "
            "annotation_goal_source:'chosen-prompt', annotation_goal_source_at:140, "
            "annotation_revision:3, annotation_revision_count:3});\n"
            "await refreshNext();\nawait __settle();\n"
            "console.log(JSON.stringify({html:__els.app.innerHTML, "
            "refusal:nextPromptReadingRefusal(__s, nextCockpitAnnotation(__s), null)}));"
        )
        assert isinstance(out, dict)
        intent = intent_of(out["html"])
        self.assertNotIn("data-next-cockpit-drafted", intent)
        self.assertNotIn("Looks right", visible_text(intent))
        self.assertNotEqual(EDITED, out["refusal"])
        # Saved adopted words read as the reader's prompt, not as typed.
        self.assertIn("from your prompt", visible_text(intent))


@unittest.skipUnless(shutil.which("node"), "node not available")
class AllowSendsWhatTheBoxHoldsNowTest(_DraftPage):
    """The consent card is open while the reader is still free to change the box. Allow sends
    the words in the box at the press, never the ones captured when the card opened (INT-1)."""

    CONSENT = (
        "__dashboard.reading_routes = "
        + json.dumps(routes(installed=("codex", "claude")))
        + ";\n__dashboard.reading = {consent:false, reason:'consent-required', used:0, limit:12};\n"
    )
    ASK = '__press("reading-ask");\nawait __settle();\nawait __settle();\n'
    ALLOW = '__press("reading-allow");\nawait __settle();\nawait __settle();\n'
    SENT = (
        "console.log(JSON.stringify({card:__els.app.innerHTML.includes('Allow and analyze'), "
        "posts:__posts.filter(p => p.url === '/api/reading').map(p => p.body)}));"
    )

    def page(self, after: str) -> Any:
        return self.drive(SERVE_CHOICES + self.CONSENT, after)

    def test_a_choice_made_while_the_card_is_open_is_what_allow_sends(self) -> None:
        out = self.page(self.ASK + CHOOSE + self.ALLOW + self.SENT)
        assert isinstance(out, dict)
        self.assertEqual(1, len(out["posts"]), out)
        body = out["posts"][0]
        self.assertEqual(runtime_reading.PROMPT_CHOSEN, body["adopt"])
        self.assertEqual("p-latest", body["prompt_fact"])
        self.assertEqual(CHOSEN, body["expected_prompt"])
        self.assertEqual(140, body["expected_prompt_at"])
        self.assertTrue(body["allow"])

    def test_undo_while_the_card_is_open_sends_the_first_prompt_back(self) -> None:
        out = self.page(
            CHOOSE
            + self.ASK
            + '__press("held-undo", "intent");\nawait __settle();\n'
            + self.ALLOW
            + self.SENT
        )
        assert isinstance(out, dict)
        self.assertEqual(1, len(out["posts"]), out)
        body = out["posts"][0]
        self.assertEqual("first-prompt", body["adopt"])
        self.assertEqual(FIRST, body["expected_prompt"])
        self.assertEqual(99, body["expected_prompt_at"])
        self.assertNotIn("prompt_fact", body)


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePageSpellsTheSourcesAsTheServerDoesTest(_DraftPage):
    def test_the_prompt_sources_match_the_servers(self) -> None:
        out = self.drive(after="console.log(JSON.stringify(NEXT_PROMPT_SOURCES));")
        self.assertEqual(list(runtime_reading.PROMPT_SOURCES), out)

    def test_old_controls_are_gone_from_the_bundle(self) -> None:
        out = self.drive(
            after="console.log(JSON.stringify({adopt:typeof nextPromptAdoptControls, "
            "menu:typeof nextIntentPromptMenu}));"
        )
        self.assertEqual({"adopt": "undefined", "menu": "function"}, out)


if __name__ == "__main__":
    unittest.main()
