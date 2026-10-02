"""Plain words a first-time reader meets on the session page (2026-10-02, NU-3, NU-5, NU-6).

The activity list printed a fact's raw type ("prepared_dispatch"), the header's copy controls were
upper-case mono buttons beside sentence-case ones, and the live monitor's hint suggested a cost the
code beside it says is never incurred. Every assertion reads what a sighted reader sees.
"""

from __future__ import annotations

import re
import shutil
import unittest
from typing import Any, ClassVar

from cargento_runtime import levels

from . import test_next_analysis_result as result_tests
from . import test_next_drift_panel as panel
from . import test_next_intent_draft as draft_tests
from . import test_next_text_density as density
from .next_harness import NEXT_STYLES, storage_prelude
from .visible_text import visible_text

SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")
ENDED = "__dashboard.sessions[0].state='ended'; __dashboard.sessions[0].ended_at=110;\n"
NO_FIRST = (
    draft_tests.DRAFT + "__s.first_prompt = ''; __s.first_prompt_at = null;\n" + density.ELIGIBLE
)


def without_fields(html: str) -> str:
    """The page without the reader's own words, which are field values rather than labels."""
    return re.sub(r"<textarea\b[^>]*>[^<]*</textarea>", "<textarea></textarea>", html)


@unittest.skipUnless(shutil.which("node"), "node not available")
class AReaderNeverSeesARawFactTypeTest(panel.PanelPage):
    STATES: ClassVar[dict[str, Any]] = {
        "01 no intent": lambda self: self.page("claude", NO_FIRST),
        "02 drafted": lambda self: self.page("claude", density.IDLE_DRAFTED),
        "03 saved": lambda self: self.page("claude", density.ELIGIBLE),
        "04 consent": lambda self: self.confirming(),
        "05 analyzing": lambda self: self.page(setup=panel.JOB + density.ELIGIBLE),
        "08 ended": lambda self: self.page("claude", density.STORED + ENDED),
        "09 codex": lambda self: self.page("codex", density.ELIGIBLE),
    }

    def test_a_reader_never_sees_a_snake_case_fact_type_in_the_activity_list(self) -> None:
        for name, render in self.STATES.items():
            with self.subTest(state=name):
                text = visible_text(without_fields(render(self)))
                self.assertEqual([], SNAKE.findall(text))
        # The fixture's dispatch reads as a word, and its number stays.
        drafted = visible_text(self.page("claude", density.IDLE_DRAFTED))
        self.assertRegex(drafted, r"#\d+ Agent Dispatch")

    def test_a_type_with_no_word_reads_entry_never_its_token_or_a_property(self) -> None:
        for token in ("branch_merge", "constructor", "toString"):
            with self.subTest(token=token):
                text = visible_text(
                    self.page(
                        "claude",
                        density.IDLE_DRAFTED
                        + "__semantic.facts.forEach(f => { if(f.type === 'prepared_dispatch')"
                        + f" f.type = {token!r}; }});\n",
                    )
                )
                self.assertNotIn(token, text)
                self.assertNotIn("function", text)
                self.assertRegex(text, r"#\d+ Agent Entry")

    def test_the_headers_copy_controls_read_in_sentence_case(self) -> None:
        html = self.page()
        labels = re.findall(
            r"<button[^>]*data-next-copy-(?:session|link|command)[^>]*>[\s\S]*?</button>", html
        )
        seen = [visible_text(label) for label in labels]
        self.assertIn("Copy ID", seen)
        self.assertIn("Copy link", seen)
        for gone in ("COPY ID", "COPY LINK", "COPY COMMAND"):
            self.assertNotIn(gone, html)
        copy = re.search(r"\.next-session-copy\{([^}]*)\}", NEXT_STYLES)
        assert copy is not None
        self.assertNotIn("var(--mono)", copy.group(1))

    def test_the_live_monitor_hint_does_not_suggest_a_cost(self) -> None:
        hint = self._run_page_js("console.log(JSON.stringify(NEXT_DRIFT_LIVE_HINT));")
        self.assertIn("no model call", hint)
        self.assertNotIn("low-cost", hint)
        self.assertEqual(
            "Shows a level after every turn, from checks and file paths, with no model call. "
            "The level shows here and in the header.",
            hint,
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class AStoredReadingNamesNoRawTypeTest(result_tests._ResultPage):
    def test_a_stored_reading_shows_no_snake_case_fact_type(self) -> None:
        for name, (value, level, facts) in {
            "06 stored departure": (result_tests.MIXED, levels.HIGH, result_tests.FACTS),
            "07 stored consistent": (
                result_tests.ALL_CONSISTENT,
                levels.NONE_OR_LOW,
                result_tests.NO_FAILURE,
            ),
        }.items():
            with self.subTest(state=name):
                html = self.page(value, level, facts=facts)
                assert isinstance(html, str)
                self.assertEqual([], SNAKE.findall(visible_text(without_fields(html))))


@unittest.skipUnless(shutil.which("node"), "node not available")
class AttentionSaysWhatIsOnTheBoardTest(panel.PanelPage):
    """NU-4 and N9 (2026-10-02): the "Not on this board yet" list printed roadmap ids (F3, E5,
    E6), two headings carried a sentence fragment under them, and three section titles were in
    capitals beside sentence-case ones."""

    def attention(self, setup: str = "") -> str:
        html = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + panel.ANNOTATED
            + setup
            + "await refreshNext();\nawait __settle();\n"
            "navigateNext({view:'attention', project:null, session:null});\nawait __settle();\n"
            "console.log(JSON.stringify(__els.app.innerHTML));",
            storage_prelude({}) + panel.FIXTURE,
        )
        assert isinstance(html, str)
        return html

    def test_a_first_time_reader_sees_no_tracker_ids_and_no_fragments_under_headings(self) -> None:
        html = self.attention()
        text = visible_text(html)
        self.assertEqual([], re.findall(r"\b[EF]\d\b", text))
        for fragment in ("not in that denominator", "gap reads as a gap"):
            self.assertNotIn(fragment, text)
        # Each gap is still named, with its sentence.
        self.assertIn("Ended with unpushed commits", text)
        self.assertIn("Finished and never read", text)
        headings = re.findall(r'<h2 tabindex="-1">([^<]*)</h2>', html)
        self.assertTrue(headings)
        for heading in headings:
            with self.subTest(heading=heading):
                words = re.sub(r"\(\d+\)", "", heading).strip()
                self.assertNotEqual(words.upper(), words)
        waiting = visible_text(
            self.attention(
                "__dashboard.sessions[0].state = 'needs_input';\n"
                "__dashboard.summary = {working:0, needs_input:1};\n"
            )
        )
        self.assertRegex(waiting, r"Needs you now \(\d+\)")
        self.assertNotIn("NEEDS YOU NOW", waiting)


@unittest.skipUnless(shutil.which("node"), "node not available")
class FiveSmallCopyFixesTest(panel.PanelPage):
    """NU-10, NU-13, NU-14, NU-16 and NU-20 (2026-10-02): words a first-time reader trips on."""

    def test_a_reader_with_a_stored_reading_is_not_told_how_to_start_one(self) -> None:
        stored = visible_text(self.page("codex", panel.READING))
        self.assertNotIn("What analysis does", stored)
        # Before any reading, the explanation is still one click away.
        self.assertIn("What analysis does", visible_text(self.page("claude", density.ELIGIBLE)))

    def test_what_it_read_is_one_grammatical_sentence(self) -> None:
        html = self.page("codex", panel.READING)
        self.assertIn("Revision 2 (time not recorded).", html)
        self.assertNotIn("when it was typed was not recorded", html)

    def test_an_ended_session_states_its_git_state_once(self) -> None:
        html = self.page("claude", density.STORED + ENDED)
        summary = re.search(r"<summary>(Session facts:[^<]*)</summary>", html)
        assert summary is not None
        self.assertEqual(1, summary.group(1).lower().count("git state"), summary.group(1))
        self.assertTrue(summary.group(1).startswith("Session facts: Session ended"))

    def test_the_intent_log_names_each_session_the_way_the_rest_of_the_board_does(self) -> None:
        html = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + panel.ANNOTATED
            + "await refreshNext();\nawait __settle();\n"
            "navigateNext({view:'intent', project:null, session:null});\nawait __settle();\n"
            "const on = __els.app.innerHTML;\n"
            "nextData.annotate = false; renderNext();\n"
            "console.log(JSON.stringify({on, off:__els.app.innerHTML}));",
            storage_prelude({}) + panel.FIXTURE,
        )
        assert isinstance(html, dict)
        link = re.search(
            r'<a [^>]*data-next-route="session:cargento:codex:focus-1"[^>]*>([^<]*)</a>', html["on"]
        )
        assert link is not None
        self.assertEqual("Shape project cockpit", link.group(1))
        self.assertNotIn(">codex:focus-1<", html["on"])
        self.assertIn("expected outcome", visible_text(html["off"]))
        self.assertNotIn("expected output", visible_text(html["off"]))

    def test_the_discard_controls_words_match_its_summary(self) -> None:
        html = self.page()
        offer = re.search(
            r"<details[^>]*next-cockpit-held-discard-offer[^>]*>[\s\S]*?</details>", html
        )
        assert offer is not None
        self.assertIn("<summary>Discard everything</summary>", offer.group(0))
        button = re.search(r'data-next-cockpit-action="held-discard"[^>]*>([^<]*)<', offer.group(0))
        assert button is not None
        self.assertEqual("Discard everything", button.group(1))


if __name__ == "__main__":
    unittest.main()
