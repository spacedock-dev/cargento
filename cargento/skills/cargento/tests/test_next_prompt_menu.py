""" "Use your prompt": one native select of your own prompts that fills the goal box (DRC-4758 D2).

The owner's walk found the goal row offering "Use a prompt", which opened a nested "Your latest
prompt", which held "Use latest prompt without checking": two nested disclosures and a save that
skipped the box. Owner ruling Q7 (2026-10-01): one "Use your prompt" menu lists up to five of the
reader's own prompts, published by the server as `prompt_choices`, and choosing one fills the
Goal box as a pending adoption, never as a typed edit. The owner's 2026-10-02 ruling makes it a
native `<select>`, because the `<details>` of buttons critic 14 chose jumped from the right of the
row to the left when it opened: the browser's own list drops over the page, and the poll already
defers its paint while a select holds focus. Correction 11 keeps an excerpt marked in the option.

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
from .next_harness import NEXT_STYLES
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
// A reader's pick in the native list, as the browser reports it: a change on the select.
const __pick = value => __fire("change", {target:{tagName:"SELECT", value,
  closest(selector){ return selector === "[data-next-cockpit-prompt-select]" ? this : null; }}});
"""
)


def menu_of(html: str) -> str:
    found = re.search(r'<label class="next-intent-prompt-pick"[\s\S]*?</label>', html)
    assert found is not None, "no prompt select"
    return found.group(0)


def options_of(html: str) -> list[str]:
    """The prompts offered, without the placeholder."""
    return [
        option
        for option in re.findall(r"<option\b[^>]*>[^<]*</option>", menu_of(html))
        if 'value=""' not in option
    ]


def option_text(option: str) -> str:
    return visible_text(f"<select>{option}</select>")


def goal_box(html: str) -> str:
    found = re.search(
        r'<textarea[^>]*data-next-cockpit-held-kind="goal"[^>]*>([^<]*)<', intent_of(html)
    )
    assert found is not None
    return found.group(1)


CHOOSE = '__pick("p-latest");\nawait __settle();\n'
HTML = "console.log(JSON.stringify(__els.app.innerHTML));"
SAVED_FROM_PROMPT = (
    TYPED
    + "__s.annotation_goal = __s.first_prompt;\n"
    + '__s.annotation_goal_source = "first-prompt";\n'
    + "__s.annotation_goal_source_at = 99;\n"
)


def goal_field(html: str) -> str:
    """The Goal field's markup, from its opening tag to the Expected outcome field."""
    intent = intent_of(html)
    start = intent.index('data-next-cockpit-held-field="goal"')
    end = intent.index('data-next-cockpit-held-field="lines"', start)
    return intent[start:end]


def rule(selector: str) -> str:
    """The body of the one top-level rule with exactly this selector."""
    bodies = re.findall(
        r"(?:^|\})" + re.escape(selector) + r"\{([^}]*)\}", NEXT_STYLES, re.MULTILINE
    )
    if len(bodies) != 1:
        message = f"{len(bodies)} rules for {selector!r}"
        raise AssertionError(message)
    return str(bodies[0])


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheMenuIsOneNativeSelectTest(_DraftPage):
    def page(self, setup: str = "", after: str = "") -> Any:
        return self.drive(SERVE_CHOICES + setup, after)

    def test_one_select_whose_face_reads_use_your_prompt_and_no_disclosure(self) -> None:
        out = self.page()
        assert isinstance(out, str)
        intent = intent_of(out)
        menu = menu_of(out)
        self.assertEqual(1, intent.count("<select"))
        self.assertEqual(1, menu.count("<select"))
        # The closed face is the placeholder, which a pick never sends.
        self.assertRegex(menu, r'<select[^>]*>\s*<option value="">Use your prompt</option>')
        self.assertEqual("Use your prompt", visible_text(menu))
        # Named for a screen reader by what it does, since the face is a value.
        self.assertIn(
            '<span class="next-visually-hidden">Fill the goal from one of your prompts</span>', menu
        )
        # No disclosure of buttons any more: it jumped left when it opened.
        self.assertNotIn("<details", menu)
        self.assertNotIn("<button", menu)
        self.assertNotIn('role="listbox"', menu)
        self.assertNotIn("adopt:choices", out)
        for gone in ("Use a prompt", "Your latest prompt", "without checking"):
            self.assertNotIn(gone, out)

    def test_the_options_are_the_published_prompts_in_order_with_their_own_times(self) -> None:
        out = self.page(
            after="console.log(JSON.stringify({html:__els.app.innerHTML, "
            "clocks:[99,140,120].map(nextSessionClock)}));"
        )
        assert isinstance(out, dict)
        options = options_of(out["html"])
        self.assertEqual(3, len(options))
        texts = [option_text(option) for option in options]
        first, latest, earlier = out["clocks"]
        self.assertEqual(f"First prompt · {first} — {FIRST}", texts[0])
        self.assertEqual(f"Latest prompt · {latest} — {CHOSEN}", texts[1])
        # An excerpt says so in the option itself (critic 11), and a whole prompt does not.
        self.assertEqual(f"Earlier prompt · {earlier} · excerpt — {LONG}", texts[2])
        self.assertNotIn("excerpt", texts[0] + texts[1])
        self.assertEqual(
            ['value="p-first"', 'value="p-latest"', 'value="p-long"'],
            [re.search(r'value="[^"]*"', option).group(0) for option in options],  # type: ignore[union-attr]
        )

    def test_a_long_prompt_is_clipped_at_a_word_in_its_option(self) -> None:
        words = "Keep every retry attempt in one ledger the board can read " * 4
        out = self.page(
            "__choices = [{fact_id:'p-w', at:99, text:"
            + json.dumps(words.strip())
            + ", cut:false}];\n",
            HTML,
        )
        assert isinstance(out, str)
        text = option_text(options_of(out)[0])
        shown = text.split(" — ", 1)[1]
        self.assertTrue(shown.endswith("…"), shown)
        self.assertLessEqual(len(shown), 61)
        # Cut at a word: what is left before the mark is a prefix ending on a whole word.
        self.assertTrue(words.startswith(shown[:-1].rstrip()), shown)
        self.assertEqual(" ", words[len(shown[:-1].rstrip())])

    def test_the_earliest_offered_is_first_only_when_it_is_the_first_prompt(self) -> None:
        # The record the choices come from holds the newest 100 events, so in a long session
        # its earliest prompt is a later message than the row's first prompt (F2).
        out = self.page("__s.first_prompt_at = 50;\n", HTML)
        assert isinstance(out, str)
        label = option_text(options_of(out)[0])
        self.assertTrue(label.startswith("Earliest prompt · "), label)
        self.assertNotIn("First prompt", menu_of(out))

    def test_the_select_keeps_its_focus_key_across_a_redraw(self) -> None:
        out = self.page(
            after="const before = __els.app.innerHTML; renderNext();\n"
            "console.log(JSON.stringify({before, after:__els.app.innerHTML}));"
        )
        assert isinstance(out, dict)
        for html in (out["before"], out["after"]):
            select = re.search(r"<select\b[^>]*>", menu_of(html))
            assert select is not None
            self.assertIn(f'data-next-focus="{GOAL_KEY}:prompt"', select.group(0))
            self.assertIn("data-next-cockpit-prompt-select", select.group(0))
        # No option carries a key of its own: the select is the one control.
        self.assertNotIn(":prompt:p-", out["before"])

    def test_no_menu_without_published_prompts_or_with_annotations_off(self) -> None:
        none = self.page("__choices = [];\n")
        off = self.page("__dashboard.annotate = false;\n")
        assert isinstance(none, str)
        assert isinstance(off, str)
        self.assertNotIn("next-intent-prompt-select", none)
        self.assertNotIn("next-intent-prompt-select", off)
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
        # field carries the draft's tint, and Save intent is the save (owner, 2026-10-02).
        self.assertFalse(out["held"])
        intent = intent_of(html)
        self.assertIn("data-next-cockpit-drafted", intent)
        seen = visible_text(intent)
        self.assertIn(f"from your prompt · {out['clock']}", seen)
        self.assertNotIn("Looks right", seen)
        # Focus stays on the select, so arrowing through it previews each prompt in turn.
        self.assertIn({"named": f"{GOAL_KEY}:prompt"}, out["renders"])

    def test_choosing_says_so_politely(self) -> None:
        out = self.page(
            cockpit_tests.CockpitCuesReachTheReaderTest.ANNOUNCER_DOM,
            CHOOSE + 'console.log(JSON.stringify(wrote("next-cockpit-cue-status")));',
        )
        self.assertEqual(["Goal filled from your prompt. Not saved."], out)

    def test_an_excerpt_stays_marked_in_view_once_chosen(self) -> None:
        out = self.page(after='__pick("p-long");\nawait __settle();\n' + HTML)
        assert isinstance(out, str)
        self.assertEqual(LONG, goal_box(out))
        self.assertIn("Shown excerpt only.", visible_text(intent_of(out)))

    def test_save_intent_adopts_the_choice_by_its_fact_and_time(self) -> None:
        out = self.page(
            after=CHOOSE + '__press("held-save", "intent");\nawait __settle();\n'
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
        self.assertNotIn(CHOSEN, intent_of(out).split("next-intent-prompt-pick")[0])

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
            '__pick("p-first");\nawait __settle();\n'
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
            after='__pick("p-first");\nawait __settle();\n'
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
class ANativeListThatStaysWhereItIsTest(_DraftPage):
    """Owner ask 2 (2026-10-02): a native select that does not jump, and a pick fills the box."""

    def page(self, setup: str = "", after: str = "") -> Any:
        return self.drive(SERVE_CHOICES + setup, after)

    def test_a_reader_picks_a_prompt_from_a_native_list_and_the_goal_box_fills_unsaved(
        self,
    ) -> None:
        out = self.page(
            cockpit_tests.CockpitCuesReachTheReaderTest.ANNOUNCER_DOM,
            '__pick("p-long");\nawait __settle();\n'
            "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts, "
            'said:wrote("next-cockpit-cue-status")}));',
        )
        assert isinstance(out, dict)
        # The whole prompt, not the option's clipped label.
        self.assertEqual(LONG, goal_box(out["html"]))
        self.assertEqual([], out["posts"])
        self.assertEqual(["Goal filled from your prompt. Not saved."], out["said"])

    def test_after_picking_the_readers_focus_stays_on_the_list(self) -> None:
        out = self.page(after=CHOOSE + "console.log(JSON.stringify(__renders));")
        assert isinstance(out, list)
        self.assertEqual({"named": f"{GOAL_KEY}:prompt"}, out[-1])

    def test_a_poll_that_arrived_while_the_list_was_focused_does_not_take_focus_back(
        self,
    ) -> None:
        out = self.page(
            after='nextDeferredRender = {focus:{named:"x"}, announcement:""};\n'
            "const __before = __renders.length;\n" + CHOOSE + "console.log(JSON.stringify("
            "{pending:nextDeferredRender, renders:__renders.slice(__before)}));"
        )
        assert isinstance(out, dict)
        self.assertIsNone(out["pending"])
        self.assertEqual([{"named": f"{GOAL_KEY}:prompt"}], out["renders"])

    def test_the_poll_the_list_held_back_is_still_announced_after_the_pick(self) -> None:
        out = self.page(
            after="const __said = [];\nconst __announce = nextAnnounceAttention;\n"
            "nextAnnounceAttention = message => { __said.push(message); return __announce(message); };\n"
            'nextDeferredRender = {focus:{named:"x"}, announcement:"1 session needs you"};\n'
            + CHOOSE
            + "console.log(JSON.stringify(__said));"
        )
        self.assertEqual(["1 session needs you"], out)

    def test_picking_the_placeholder_changes_nothing_and_lets_the_held_poll_paint(self) -> None:
        out = self.page(
            after='nextDeferredRender = {focus:{named:"x"}, announcement:""};\n'
            "const __before = __renders.length;\n"
            '__pick("");\nawait __settle();\n'
            "console.log(JSON.stringify({renders:__renders.slice(__before), "
            "chosen:nextIntentChosenPrompts.size}));"
        )
        assert isinstance(out, dict)
        # The list's own deferral runs as it always has: the poll it held back paints, once.
        self.assertEqual([{"named": "x"}], out["renders"])
        self.assertEqual(0, out["chosen"])

    def test_the_list_shows_the_pick_while_the_box_holds_it_and_the_placeholder_once_typed(
        self,
    ) -> None:
        field = (
            "const __select = {value:'p-latest'};\n"
            "const __field = {querySelector(selector){ return selector === "
            "'[data-next-cockpit-prompt-select]' ? __select : null; }, setAttribute(){}, "
            "removeAttribute(){}};\n"
            "__fire('input', {target:{value:'Typed over it', dataset:{nextCockpitHeldKey:"
            + json.dumps(GOAL_KEY)
            + "}, closest(selector){ return selector === '[data-next-cockpit-held-key]' ? this"
            " : selector === '[data-next-cockpit-held-field]' ? __field : null; }}});\n"
        )
        out = self.page(
            after=CHOOSE + "const picked = __els.app.innerHTML;\n" + field + "renderNext();\n"
            "console.log(JSON.stringify({picked, inPlace:__select.value, "
            "typed:__els.app.innerHTML}));"
        )
        assert isinstance(out, dict)
        picked = menu_of(out["picked"])
        self.assertRegex(picked, r'<option value="p-latest" selected>')
        self.assertEqual(1, picked.count(" selected"))
        self.assertTrue(option_text(options_of(out["picked"])[1]).startswith("Latest prompt"))
        self.assertTrue(visible_text(picked).startswith("Latest prompt"), visible_text(picked))
        # The first keystroke puts the face back in place, with no redraw, so the same prompt
        # can be picked again.
        self.assertEqual("", out["inPlace"])
        self.assertNotIn(" selected", menu_of(out["typed"]))
        self.assertEqual("Use your prompt", visible_text(menu_of(out["typed"])))

    def test_picking_a_prompt_or_typing_over_it_never_moves_the_goal_box(self) -> None:
        """Measured in Chrome at 1440x900 (verifier F1, 2026-10-02): a pick drew the draft's
        marks ("from your prompt · 08:02") on a line of their own between the select and the box,
        so the box the pick fills dropped 25px, and the first keystroke hid them and pulled it
        back up under the caret. Whatever the box holds, the label row is the label and the select
        alone, and where the words came from sits in the row under the box, between the count and
        Clear, as an outcome line's source sits between its count and Remove."""
        states = {
            "a typed goal at rest": self.page(TYPED, HTML),
            "a prompt just picked": self.page(TYPED, CHOOSE + HTML),
            "the first prompt drafted": self.page("", HTML),
            "a goal saved from a prompt": self.page(SAVED_FROM_PROMPT, HTML),
        }
        for name, out in states.items():
            with self.subTest(state=name):
                assert isinstance(out, str)
                field = goal_field(out)
                heading = field[: field.index("<textarea")]
                self.assertIn("next-intent-prompt-pick", heading)
                self.assertNotIn("from your prompt", heading)
                self.assertNotIn("next-cockpit-held-cue", heading)
                self.assertNotIn("data-next-cockpit-draft-marks", heading)
                under = field[field.index('<div class="next-cockpit-held-under">') :]
                if name != "a typed goal at rest":
                    self.assertIn("from your prompt", visible_text(under))
                    count = under.index("data-next-cockpit-held-count")
                    clear = under.index('data-next-cockpit-action="held-clear"')
                    source = under.index("from your prompt")
                    self.assertLess(count, source)
                    self.assertLess(source, clear)
        # The row under the box holds one control's height whatever it shows, so neither the
        # marks going on the first keystroke nor Clear going with the last character moves what
        # is below it, and it does not wrap the marks onto a line of their own.
        goal_under = rule(
            '.next-cockpit-held-field[data-next-cockpit-held-field="goal"]>.next-cockpit-held-under'
        )
        self.assertIn("min-block-size:44px", goal_under)
        self.assertIn("flex-wrap:nowrap", goal_under)
        marks = rule(".next-intent-draft-marks")
        self.assertNotIn("flex-basis:100%", marks)
        self.assertIn("min-width:0", marks)

    def test_a_240_character_prompt_does_not_stretch_the_list(self) -> None:
        pick = re.search(r"\.next-intent-prompt-pick\{([^}]*)\}", NEXT_STYLES)
        assert pick is not None
        self.assertIn("max-inline-size:min(18rem,100%)", pick.group(1))
        self.assertIn("margin-left:auto", pick.group(1))
        select = re.search(r"\.next-intent-prompt-select\{([^}]*)\}", NEXT_STYLES)
        assert select is not None
        self.assertIn("max-inline-size:100%", select.group(1))
        self.assertIn("text-overflow:ellipsis", select.group(1))
        # The old menu's rules are gone with it.
        self.assertNotIn(".next-intent-prompt-menu", NEXT_STYLES)


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePageSpellsTheSourcesAsTheServerDoesTest(_DraftPage):
    def test_the_prompt_sources_match_the_servers(self) -> None:
        out = self.drive(after="console.log(JSON.stringify(NEXT_PROMPT_SOURCES));")
        self.assertEqual(list(runtime_reading.PROMPT_SOURCES), out)

    def test_old_controls_are_gone_from_the_bundle(self) -> None:
        out = self.drive(
            after="console.log(JSON.stringify({adopt:typeof nextPromptAdoptControls, "
            "menu:typeof nextIntentPromptMenu, select:typeof nextIntentPromptSelect}));"
        )
        self.assertEqual({"adopt": "undefined", "menu": "undefined", "select": "function"}, out)


if __name__ == "__main__":
    unittest.main()
