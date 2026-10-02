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
from .next_harness import NEXT_STYLES
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


if __name__ == "__main__":
    unittest.main()
