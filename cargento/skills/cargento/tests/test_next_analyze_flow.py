"""The Analyze drift flow says beside the button what a press can do (DRC-4758 slice B).

The owner's walk pressed "Analyze drift" on a session the server could only withhold: the
analyzing box flashed, the panel snapped back to the bare button, and the reason sat in the
READING section far below. The board now publishes `reading_eligibility`, and the page draws a
press it cannot serve as inert, with one short line keyed by the server's token directly under
the button and the server's own sentence one click away. An outcome a press came to stands in the
same place. Every assertion reads the assembled bundle's rendered markup.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest

from cargento_runtime import levels, reading

from . import test_next_analysis_result as result_tests
from . import test_next_cockpit as cockpit_tests
from . import test_next_drift_panel as panel
from .next_harness import NEXT_STYLES, storage_prelude
from .test_next_drift_panel import FIXTURE, JOB, PanelPage, drift_of, routes
from .visible_text import visible_text

ASK = re.compile(r'<button\b[^>]*data-next-cockpit-action="reading-(?:ask|allow)"[^>]*>')
POSTS = """
const posts = [];
const upstream = __fetchImpl;
__fetchImpl = async (url, init) => {
  if(init && init.method === "POST"){
    posts.push(JSON.parse(init.body));
    return REPLY;
  }
  return upstream(url, init);
};
"""


def eligibility(token: str | None, *, until: float | None = None) -> str:
    """The row's published `reading_eligibility`, as `reading.press_eligibility` builds it."""
    value = (
        {"ok": True, "reason": None, "until": None, "sentence": None}
        if token is None
        else {"ok": False, "reason": token, "until": until, "sentence": reading.WITHHELD[token]}
    )
    return f"__dashboard.sessions[0].reading_eligibility = {json.dumps(value)};\n"


def after_button(drift: str) -> str:
    """The visible text after the Analyze control's row and the count line under it, so a test
    reads what follows them (the count left the row on 2026-10-02, NU-9)."""
    match = ASK.search(drift)
    assert match is not None, "no Analyze control drawn"
    tail = drift[drift.index("</div>", match.end()) + len("</div>") :]
    count = re.match(r'<p class="next-cockpit-reading-count">[\s\S]*?</p>', tail)
    return visible_text(tail[count.end() :] if count else tail)


@unittest.skipUnless(shutil.which("node"), "node not available")
class AnInertPressSaysWhyBesideTheButtonTest(PanelPage):
    def lines(self) -> object:
        return self._run_page_js(
            "console.log(JSON.stringify(NEXT_READING_PRESS_LINES));",
            storage_prelude({}) + FIXTURE,
        )

    def test_an_idle_session_with_no_stop_draws_analyze_inert_with_its_line(self) -> None:
        drift = drift_of(self.page(setup=eligibility(reading.WITHHELD_IDLE_UNKNOWN)))

        button = ASK.search(drift)
        assert button is not None
        self.assertIn('aria-disabled="true"', button.group(0))
        self.assertNotIn("next-action--primary", button.group(0))
        text = after_button(drift)
        self.assertTrue(text.startswith("Analyze opens once this session finishes a turn."), text)
        self.assertNotIn("Allow and analyze", drift)
        # The server's sentence is one click away, verbatim, and not in view.
        sentence = reading.WITHHELD[reading.WITHHELD_IDLE_UNKNOWN]
        self.assertIn(sentence, drift)
        self.assertIn("Why it can't read", text)
        self.assertNotIn(sentence, visible_text(drift))

    def test_pressing_an_inert_analyze_posts_nothing_and_draws_no_box(self) -> None:
        html = self.page(
            setup=eligibility(reading.WITHHELD_IDLE_UNKNOWN)
            + '__dashboard.reading = {consent:false, reason:"consent-required", used:0, limit:12};\n',
            after="const REPLY = {ok:true, json:async()=>({ok:true, produced:true})};\n"
            + POSTS
            + "await nextCockpitAskForReading(__dashboard.sessions[0], null);\n"
            + "renderNext();\nawait __settle();\n"
            + '__els.app.innerHTML = `<i data-posts="${posts.length}"></i>` + __els.app.innerHTML;\n',
        )
        self.assertIn('<i data-posts="0"></i>', html)
        drift = drift_of(html)
        self.assertNotIn("data-next-analyzing", drift)
        self.assertNotIn("Allow and analyze", drift)
        self.assertIn("Analyze opens once this session finishes a turn.", after_button(drift))

    def test_every_token_the_board_can_publish_has_one_short_line(self) -> None:
        out = self.lines()
        assert isinstance(out, dict)
        self.assertSetEqual(set(reading.PRESS_WITHHELD), set(out))
        for token, line in out.items():
            with self.subTest(token=token):
                self.assertLessEqual(len(line.split()), 12, line)
                self.assertNotEqual(reading.WITHHELD[token], line)

    def test_each_token_draws_its_line_under_the_button(self) -> None:
        lines = self.lines()
        assert isinstance(lines, dict)
        for token in reading.PRESS_WITHHELD:
            with self.subTest(token=token):
                # A settling row's `until` is in the future, so it is still inert.
                drift = drift_of(self.page(setup=eligibility(token, until=4_000_000_000.0)))
                self.assertTrue(after_button(drift).startswith(lines[token]))

    def test_a_settled_row_lights_up_without_a_press(self) -> None:
        drift = drift_of(self.page(setup=eligibility(reading.WITHHELD_STOP_SETTLING, until=1.0)))
        button = ASK.search(drift)
        assert button is not None
        self.assertNotIn("aria-disabled", button.group(0))

    def test_a_codex_row_between_turns_says_a_reading_cannot_run_there_yet(self) -> None:
        drift = drift_of(self.page("codex", eligibility(reading.WITHHELD_TURN_STOP)))
        button = ASK.search(drift)
        assert button is not None
        self.assertIn('aria-disabled="true"', button.group(0))
        self.assertNotIn("next-action--primary", drift)
        self.assertIn(
            "Codex sessions can be analyzed only while a turn is running.", after_button(drift)
        )

    def test_a_codex_row_whose_turn_is_running_can_be_pressed(self) -> None:
        drift = drift_of(self.page("codex", eligibility(None)))
        button = ASK.search(drift)
        assert button is not None
        self.assertNotIn("aria-disabled", button.group(0))
        self.assertIn("next-action--primary", button.group(0))


@unittest.skipUnless(shutil.which("node"), "node not available")
class WhatAPressCameToStandsBesideTheButtonTest(PanelPage):
    WITHHELD_REPLY = (
        "const REPLY = {ok:true, status:200, json:async()=>("
        + json.dumps(
            {
                "ok": False,
                "produced": False,
                "reason": "withheld",
                "withheld": reading.WITHHELD_IDLE_UNKNOWN,
                "sentence": reading.WITHHELD[reading.WITHHELD_IDLE_UNKNOWN],
                "until": None,
            }
        )
        + ")};\n"
    )

    def test_a_press_the_server_withholds_says_so_beside_the_button_with_no_box(self) -> None:
        html = self.page(
            "codex",
            "__dashboard.reading = {consent:true, providers:{codex:true}, used:0, limit:12};\n",
            after=self.WITHHELD_REPLY
            + POSTS
            + "await nextCockpitAskForReading(__dashboard.sessions[0], null);\n"
            + "renderNext();\nawait __settle();\n",
        )
        drift = drift_of(html)
        self.assertNotIn("data-next-analyzing", drift)
        text = after_button(drift)
        codex = "Codex sessions can be analyzed only while a turn is running."
        self.assertTrue(text.startswith(codex), text)
        self.assertNotIn("Could not confirm the reading", drift)
        line = re.search(rf"<p\b[^>]*>{re.escape(codex)}</p>", drift)
        assert line is not None
        self.assertIn('role="status"', line.group(0))

    def test_a_stored_withhold_stands_beside_the_button_with_its_age(self) -> None:
        sentence = reading.WITHHELD[reading.WITHHELD_AFTER_STOP]
        html = self.page(
            setup="__dashboard.generated = 400;\n"
            f"__dashboard.sessions[0].annotation_reading_withheld = {json.dumps(sentence)};\n"
            "__dashboard.sessions[0].annotation_reading_withheld_at = 220;\n"
        )
        drift = drift_of(html)
        text = after_button(drift)
        self.assertTrue(text.startswith(f"Last analysis, 3m ago: {sentence}"), text)
        # Said once, beside the button, and not again in the READING section.
        self.assertEqual(1, visible_text(drift).count(sentence))

    def test_a_press_that_could_not_be_confirmed_says_so_beside_the_button(self) -> None:
        html = self.page(
            "codex",
            "__dashboard.reading = {consent:true, providers:{codex:true}, used:0, limit:12};\n",
            after="const REPLY = Promise.reject(new Error('lost'));\nREPLY.catch(() => {});\n"
            + POSTS
            + "await nextCockpitAskForReading(__dashboard.sessions[0], null);\n"
            + "renderNext();\nawait __settle();\n",
        )
        text = after_button(drift_of(html))
        self.assertTrue(text.startswith("Could not confirm the reading."), text)


if __name__ == "__main__":
    unittest.main()


CONSENT_NEEDED = (
    '__dashboard.reading = {consent:false, reason:"consent-required", used:0, limit:12};\n'
)
FIRST_PRESS = (
    "const REPLY = {ok:true, json:async()=>({ok:true, produced:true})};\n"
    + POSTS
    + "await nextCockpitAskForReading(__dashboard.sessions[0], null);\n"
    + "renderNext();\nawait __settle();\n"
)
SHOW_POSTS = '__els.app.innerHTML = `<i data-posts="${posts.length}"></i>` + __els.app.innerHTML;\n'
CARD = re.compile(r'<div class="next-cockpit-reading-consent"[\s\S]*?</ul>')


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheFirstPressAsksBeforeItSendsTest(PanelPage):
    """Owner Q1, 2026-10-01: the first press that would send anything is a consent step."""

    def test_the_first_press_asks_a_question_over_the_disclosure_parts_and_sends_nothing(
        self,
    ) -> None:
        html = self.page("codex", CONSENT_NEEDED, after=FIRST_PRESS + SHOW_POSTS)
        self.assertIn('<i data-posts="0"></i>', html)
        drift = drift_of(html)
        card = CARD.search(drift)
        assert card is not None, "no consent card drawn"
        heading = re.search(r"<h3\b[^>]*>([^<]*)</h3>", card.group(0))
        assert heading is not None
        self.assertEqual("Send this session to Codex for analysis?", heading.group(1))
        # The server's parts, in its order and unreworded, each its own item and in view.
        parts = routes()["codex"]["disclosure_parts"]
        items = [visible_text(item) for item in re.findall(r"<li>([\s\S]*?)</li>", card.group(0))]
        self.assertEqual([visible_text(part) for part in parts], items)
        shown = visible_text(drift)
        for part in parts:
            self.assertIn(visible_text(part), shown)
        # Then Allow and analyze, the stage's one primary, then Not now.
        allow = shown.index("Allow and analyze")
        self.assertLess(shown.index(visible_text(parts[-1])), allow)
        self.assertLess(allow, shown.index("Not now"))
        self.assertEqual(
            ["Allow and analyze"], re.findall(r"next-action--primary[^>]*>([^<]*)<", drift)
        )
        self.assertNotIn('data-next-cockpit-action="reading-ask"', drift)

    def test_the_card_takes_the_press_s_focus_key_so_a_second_enter_cannot_allow(self) -> None:
        drift = drift_of(self.page("codex", CONSENT_NEEDED, after=FIRST_PRESS))
        heading = re.search(r"<h3\b[^>]*>", drift)
        assert heading is not None
        self.assertIn('data-next-focus="reading:codex:focus-1"', heading.group(0))
        self.assertIn('tabindex="-1"', heading.group(0))
        allow = re.search(r'<button\b[^>]*data-next-cockpit-action="reading-allow"[^>]*>', drift)
        assert allow is not None
        self.assertIn('data-next-focus="reading-allow:codex:focus-1"', allow.group(0))
        not_now = re.search(
            r'<button\b[^>]*data-next-cockpit-action="reading-not-now"[^>]*>', drift
        )
        assert not_now is not None
        self.assertIn('data-next-focus="reading-not-now:codex:focus-1"', not_now.group(0))
        # Not now's key falls back to the press, which Analyze drift carries once the card goes.
        self.assertIn('data-next-focus-fallback="reading:codex:focus-1"', not_now.group(0))

    def test_allow_keeps_its_focus_while_it_is_answered(self) -> None:
        # Pressing Allow keeps the question drawn with Allow busy while it is answered (owner,
        # 2026-10-02), so a keyboard reader's focus stays on the press rather than falling to the
        # page (INT-3).
        stub = cockpit_tests.CockpitHeldToTabTest.FOCUS_DOM
        focus_dom = stub.replace(
            "(button|a|textarea|",
            "(button|a|textarea|p(?=[^>]*\\btabindex=)|h3(?=[^>]*\\btabindex=)|",
            1,
        )
        html = self.page(
            "codex",
            focus_dom + CONSENT_NEEDED,
            after="const upstream = __fetchImpl;\n"
            "__fetchImpl = async (url, init) => init && init.method === 'POST'"
            " ? new Promise(() => {}) : upstream(url, init);\n"
            "await nextCockpitAskForReading(__dashboard.sessions[0], null);\n"
            "renderNext();\nawait __settle();\n"
            "const allow = controls.find(c => c.dataset.nextCockpitAction === 'reading-allow');\n"
            "allow.focus();\n"
            "nextCockpitAskForReading(__dashboard.sessions[0], null, true);\n"
            "await __settle();\n"
            "const now = document.activeElement;\n"
            '__els.app.innerHTML = `<i data-focused="${now && now.dataset ? '
            "now.dataset.nextFocus : ''}\"></i>` + __els.app.innerHTML;\n",
        )
        self.assertIn('<i data-focused="reading-allow:codex:focus-1"></i>', html)
        allow = re.search(r'<button[^>]*data-next-cockpit-action="reading-allow"[^>]*>', html)
        assert allow is not None
        self.assertIn("data-next-pending", allow.group(0))

    def test_not_now_restores_the_idle_button_and_sends_nothing(self) -> None:
        html = self.page(
            "codex",
            CONSENT_NEEDED,
            after=FIRST_PRESS
            + "nextCockpitReadingNotNow(__dashboard.sessions[0]);\nawait __settle();\n"
            + SHOW_POSTS,
        )
        self.assertIn('<i data-posts="0"></i>', html)
        drift = drift_of(html)
        self.assertIsNone(CARD.search(drift))
        self.assertNotIn("Allow and analyze", drift)
        button = ASK.search(drift)
        assert button is not None
        self.assertIn("next-action--primary", button.group(0))
        self.assertIn('data-next-focus="reading:codex:focus-1"', button.group(0))

    def test_not_now_is_reached_by_its_click(self) -> None:
        html = self.page(
            "codex",
            CONSENT_NEEDED,
            after=FIRST_PRESS
            + "const notNow = {dataset:{nextCockpitAction:'reading-not-now'},"
            + " closest(selector){ return selector.includes('data-next-cockpit-action') ? this : null; }};\n"
            + "__fire('click', {target:notNow, preventDefault(){}});\nawait __settle();\n",
        )
        self.assertIsNone(CARD.search(drift_of(html)))


ALLOWED = (
    "__dashboard.reading = {consent:true, providers:{codex:true}, used:0, limit:12};\n"
    "__dashboard.sessions[0].annotation_reading_count = 2;\n"
)
SENT = re.compile(r"<details\b[^>]*next-cockpit-reading-sent[^>]*>[\s\S]*?</details>")


@unittest.skipUnless(shutil.which("node"), "node not available")
class IdleTheDisclosureIsOneWordedClickAwayTest(PanelPage):
    """Owner Q1, 2026-10-01: idle, the button, one hint line, then the disclosure under a summary."""

    def test_idle_and_never_allowed_shows_the_count_the_hint_and_a_closed_summary(self) -> None:
        drift = drift_of(self.page("codex", CONSENT_NEEDED))
        disclosure = routes()["codex"]["disclosure"]
        # The count on its own line under the button's row (NU-9), short to the eye and whole
        # to a screen reader.
        row = drift[drift.index('<div class="next-cockpit-reading-ask">') :]
        row = row[row.index("</div>") + len("</div>") :]
        row = row[: row.index("</p>")]
        self.assertTrue(row.startswith('<p class="next-cockpit-reading-count">'), row[:60])
        self.assertIn("0 model requests", visible_text(row))
        self.assertRegex(row, r"\d+ model requests? recorded for this session\.")
        self.assertNotIn("recorded for this session", visible_text(row))
        # A screen reader hears the sentence once, not the short form before it.
        self.assertIn('<span aria-hidden="true">0 model requests</span>', row)
        # Then only the hint and the summary are in view before the next section.
        tail = after_button(drift)
        hint = "Reads the session up to now against your intent. Runs in the background."
        self.assertTrue(tail.startswith(f"{hint} What is sent to Codex"), tail)
        self.assertNotIn(visible_text(disclosure)[:60], visible_text(drift))
        sent = SENT.search(drift)
        assert sent is not None
        self.assertNotIn(" open", sent.group(0)[: sent.group(0).index(">")])
        # Keyed by session through `nextCockpitDisclosureAttr`, the lane that puts an open
        # summary back after `renderNext` (docs/design-reader-state.md).
        self.assertIn(
            'data-next-cockpit-disclosure="cargento\ncodex:focus-1\nreading-sent"', sent.group(0)
        )
        # The disclosure paragraph the button is described by is inside it, whole and tag-free.
        button = ASK.search(drift)
        assert button is not None
        described = re.search(r'aria-describedby="([^"]+)"', button.group(0))
        assert described is not None
        bound = re.search(rf'<p\b[^>]*id="{described.group(1)}"[^>]*>([^<]*)</p>', sent.group(0))
        assert bound is not None
        self.assertEqual(visible_text(disclosure), visible_text(bound.group(1)))

    def test_once_allowed_the_summary_is_what_is_sent_and_holds_turn_off(self) -> None:
        drift = drift_of(self.page("codex", ALLOWED))
        sent = SENT.search(drift)
        assert sent is not None
        summary = re.search(r"<summary>([^<]*)</summary>", sent.group(0))
        assert summary is not None
        self.assertEqual("What is sent", summary.group(1))
        self.assertIn('data-next-cockpit-action="reading-off"', sent.group(0))
        self.assertEqual(1, drift.count('data-next-cockpit-action="reading-off"'))
        self.assertNotIn("Turn off readings", visible_text(drift))
        line = re.search(r'<p class="next-cockpit-reading-count">[\s\S]*?</p>', drift)
        assert line is not None
        self.assertEqual("2 model requests", visible_text(line.group(0)))

    def test_a_fallback_route_names_its_receiver_even_once_allowed(self) -> None:
        # A Codex session read by Claude Code sends straight away once Claude Code is allowed,
        # so the summary in view is what names the second provider before that press (F1;
        # DEC-21 item 4).
        drift = drift_of(
            self.page(
                "codex",
                "__dashboard.reading = {consent:true, providers:{claude:true}, used:0, limit:12};\n",
                routed=routes(installed=("claude",), enabled=("claude", "codex")),
            )
        )
        sent = SENT.search(drift)
        assert sent is not None
        summary = re.search(r"<summary>([^<]*)</summary>", sent.group(0))
        assert summary is not None
        self.assertEqual("What is sent to Claude Code", summary.group(1))
        self.assertIn("What is sent to Claude Code", after_button(drift))

    def test_while_analyzing_the_disclosure_is_not_drawn_and_the_count_stays(self) -> None:
        drift = drift_of(self.page("codex", ALLOWED + JOB))
        self.assertIn("data-next-analyzing", drift)
        self.assertNotIn(routes()["codex"]["disclosure"][:60], drift)
        self.assertRegex(drift, r"2 model requests recorded for this session\.")


COUNT_LINE = re.compile(r'<p class="next-cockpit-reading-count">[\s\S]*?</p>')
ASK_ROW = re.compile(r'<div class="next-cockpit-reading-ask">([\s\S]*?)</div>')


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheReadingRowIsButtonsThenTheCountTest(PanelPage):
    """NU-9 (2026-10-02): the count sat inside the button row, pushed far right, and wrapped
    "Analyze again" onto a row of its own; its wording changed from state to state."""

    def test_the_count_is_worded_the_same_before_during_and_after_an_analysis(self) -> None:
        stages = {
            "idle": self.page(),
            "confirming": self.confirming(),
            "analyzing": self.page(setup=panel.JOB),
            "stored": self.page("codex", panel.READING),
        }
        for name, html in stages.items():
            with self.subTest(stage=name):
                lines = COUNT_LINE.findall(drift_of(html))
                self.assertEqual(1, len(lines), lines)
                self.assertRegex(visible_text(lines[0]), r"^\d+ model requests?$")
                # The whole sentence stays for a screen reader.
                self.assertRegex(lines[0], r"\d+ model requests? recorded for this session\.")
                self.assertNotRegex(visible_text(drift_of(html)), r"\b\d+ requests?\b")

    def test_an_inert_analyze_on_codex_between_turns_shows_no_request_count(self) -> None:
        drift = drift_of(self.page("codex", eligibility(reading.WITHHELD_IDLE_UNKNOWN)))
        button = ASK.search(drift)
        assert button is not None
        self.assertIn('aria-disabled="true"', button.group(0))
        self.assertNotIn("reading-count", drift)
        self.assertNotRegex(visible_text(drift), r"\b\d+ (model )?requests?\b")


@unittest.skipUnless(shutil.which("node"), "node not available")
class UnderADepartureTheRowIsThreeButtonsTest(result_tests._ResultPage):
    def test_under_a_departure_the_buttons_share_a_style_and_the_count_has_its_own_line(
        self,
    ) -> None:
        html = self.page(result_tests.MIXED, levels.HIGH)
        assert isinstance(html, str)
        drift = drift_of(html)
        rows = [row for row in ASK_ROW.finditer(drift) if "reading-ask" in row.group(1)]
        self.assertEqual(1, len(rows))
        row = rows[0]
        buttons = re.findall(r"<button\b([^>]*)>([^<]*)</button>", row.group(1))
        self.assertEqual(
            ["Steer back", "Update intent instead", "Analyze again"], [text for _a, text in buttons]
        )
        self.assertNotIn("reading-count", row.group(1))
        self.assertIn("next-action--primary", buttons[0][0])
        for attrs, text in buttons[1:]:
            with self.subTest(button=text):
                self.assertRegex(attrs, r'class="next-action next-action--secondary"')
        # The count is the row's next sibling, on a line of its own.
        after = drift[row.end() :]
        self.assertTrue(after.startswith('<p class="next-cockpit-reading-count">'), after[:80])
        line = re.search(r"\.next-cockpit-reading-count\{([^}]*)\}", NEXT_STYLES)
        assert line is not None
        self.assertNotIn("margin-left:auto", line.group(1))

    def test_not_accurate_is_a_quiet_button_like_clear(self) -> None:
        html = self.page(result_tests.MIXED, levels.HIGH)
        assert isinstance(html, str)
        drift = drift_of(html)
        mark = re.search(r'<button\b[^>]*data-next-cockpit-action="not-accurate"[^>]*>', drift)
        assert mark is not None
        self.assertIn('class="next-action next-action--quiet"', mark.group(0))
        self.assertIn('aria-pressed="false"', mark.group(0))
        self.assertNotIn(".next-cockpit-result-mark{", NEXT_STYLES)
