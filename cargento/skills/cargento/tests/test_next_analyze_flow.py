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

from cargento_runtime import reading

from .next_harness import storage_prelude
from .test_next_drift_panel import FIXTURE, PanelPage, drift_of
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
    """The visible text after the Analyze control's row, so a test reads what follows it."""
    match = ASK.search(drift)
    assert match is not None, "no Analyze control drawn"
    return visible_text(drift[drift.index("</div>", match.end()) :])


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
