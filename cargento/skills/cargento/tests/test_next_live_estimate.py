"""The live drift estimate on the session page: the switch, the level, the nudge, the pill (DRC-4696).

Items 2 to 6 of
[DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn).
The switch is off by default and remembered per session in this browser only; nothing about it is
ever sent. With it on, the Drift section shows the server's live level labelled "Live estimate"
with the time it was computed, a nudge to analyze at High, and "Rose from <level> at #<n>" with
the number filled from the page's own list; the header shows the pill. Over an unsaved draft there
is no level and no pill, and a Sessions row never shows either.

Every assertion is on what a reader sees or what the page sends.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import unittest
from typing import Any

from .next_harness import NextPageJsHarness, storage_prelude
from .test_next_intent_draft import (
    CLICK,
    DRAFT,
    FIXTURE,
    ROUTE,
    TYPED,
    aside_of,
    drift_of,
    visible_text,
)

NUDGE = "This is a quick estimate. Analyze to see what drifted and how to steer back."
HINT = (
    "Turn on for a quick, low-cost drift check after every turn. "
    "The level shows here and in the header."
)
SAVE_FIRST = "Save your intent to see a live estimate"
SOURCE_LINE = "Reads checks and file paths, not what your intent says."
KEY = "cargento.next.live-estimate:claude:focus-1"

# A failed check in the window, numbered #4 after fo-b, task-a and fo-a (the window opens at 100).
CHECK = """
__semantic.facts.push({fact_id:"c-fail", at:104.5, type:"tool_report", subject:"check",
  result:"failed", summary:"pytest",
  source_session:{harness:"claude", sid:"focus-1"},
  evidence:{source:"Claude Bash call and paired result", confidence:"exact"}});
__s.annotation_window_start = 100;
"""

COMPUTED_AT = 104.9


def live(level: str = "high", **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "harness": "claude",
        "sid": "focus-1",
        "revision": 2,
        "computed_at": COMPUTED_AT,
        "level": level,
        "reasons": [],
        "rose_from": None,
        "rose_at": None,
    }
    row.update(extra)
    return row


def serve(row: dict[str, Any] | None) -> str:
    """The focused project context answers with this live level; the project one with none."""
    return (
        f"let __live = {json.dumps(row)};\n"
        """
let __gets = [];
const __ctxUpstream = __fetchImpl;
__fetchImpl = async (url, init) => {
  if(!init || init.method !== "POST") __gets.push(String(url));
  const got = await __ctxUpstream(url, init);
  if(!String(url).startsWith("/api/project-context") || !String(url).includes("session=")){
    return got;
  }
  const data = await got.json();
  return {ok:true, status:200, json:async () => ({...data,
    sources:{work:{live_levels: __live ? [__live] : []}}})};
};
"""
    )


PRESS_SWITCH = (
    '__fire("click", {preventDefault(){}, target:{dataset:{nextCockpitAction:"live-monitor",'
    ' arg:""}, closest(){ return this; }}});\nawait __settle();\nawait __settle();\n'
)
HTML = "console.log(JSON.stringify(__els.app.innerHTML));"


def clock(at: float) -> str:
    return time.strftime("%H:%M", time.localtime(at))


class _LivePage(NextPageJsHarness):
    def drive(
        self,
        setup: str = "",
        after: str = HTML,
        *,
        seed: dict[str, str] | None = None,
        draft: str = DRAFT,
    ) -> Any:
        return self._run_page_js(
            "await __settle();\nawait __settle();\n"
            + draft
            + CLICK
            + setup
            + "await refreshNext();\nawait __settle();\n"
            + ROUTE
            + "\nawait __settle();\nawait __settle();\n"
            + after,
            storage_prelude(seed or {}) + FIXTURE,
        )

    def html(self, setup: str = "", after: str = HTML, **kwargs: Any) -> str:
        out = self.drive(setup, after, **kwargs)
        assert isinstance(out, str)
        return out

    def on(self, row: dict[str, Any] | None, setup: str = TYPED + CHECK) -> str:
        """The page with the switch on for this session and the server's live level."""
        return self.html(setup + serve(row), seed={KEY: "1"})


def switch_of(html: str) -> str:
    found = re.search(r'<button\b[^>]*role="switch"[^>]*>', html)
    assert found is not None, html[:400]
    return found.group(0)


def header_of(html: str) -> str:
    start = html.index('<header class="next-session-detail-header"')
    return html[start : html.index("</header>", start)]


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheSwitchTest(_LivePage):
    def test_it_is_off_by_default_and_then_shows_no_level_and_no_pill(self) -> None:
        html = self.html(TYPED + CHECK + serve(live("high")))
        switch = switch_of(drift_of(html))
        self.assertIn('aria-checked="false"', switch)
        text = visible_text(drift_of(html))
        self.assertIn("Live monitor", text)
        self.assertIn(HINT, text)
        self.assertNotIn("data-next-drift-level", html)
        self.assertNotIn("data-next-drift-pill", html)
        self.assertNotIn(NUDGE, visible_text(html))

    def test_turning_it_on_shows_the_live_estimate_and_remembers_it_for_this_session(self) -> None:
        out = self.drive(
            TYPED + CHECK + serve(live("high")),
            PRESS_SWITCH + "console.log(JSON.stringify({html:__els.app.innerHTML, store:__store,"
            " posts:__posts, gets:__gets}));",
        )
        assert isinstance(out, dict)
        drift = drift_of(out["html"])
        self.assertIn('aria-checked="true"', switch_of(drift))
        self.assertIn("High", visible_text(drift))
        self.assertIn(f"Live estimate · {clock(COMPUTED_AT)}", visible_text(drift))
        self.assertEqual("1", out["store"].get(KEY))
        # Browser only: nothing about the switch is sent.
        self.assertEqual([], out["posts"])
        self.assertFalse([g for g in out["gets"] if "live" in g or "monitor" in g], out["gets"])
        self.assertNotIn(HINT, visible_text(drift))

    def test_a_reload_keeps_it_on_for_this_session_and_not_for_another(self) -> None:
        self.assertIn('aria-checked="true"', switch_of(drift_of(self.on(live("high")))))
        other = self.html(
            TYPED + CHECK + serve(live("high")),
            seed={"cargento.next.live-estimate:claude:other-session": "1"},
        )
        self.assertIn('aria-checked="false"', switch_of(drift_of(other)))

    def test_turning_it_off_hides_the_level_and_the_pill_again(self) -> None:
        out = self.drive(
            TYPED + CHECK + serve(live("high")),
            PRESS_SWITCH
            + "console.log(JSON.stringify({html:__els.app.innerHTML, store:__store}));",
            seed={KEY: "1"},
        )
        assert isinstance(out, dict)
        self.assertNotIn("data-next-drift-level", out["html"])
        self.assertNotIn("data-next-drift-pill", out["html"])
        self.assertNotEqual("1", out["store"].get(KEY))

    def test_storage_that_throws_still_turns_it_on_for_the_tab(self) -> None:
        throwing = (
            "localStorage.getItem = () => { throw new Error('denied'); };\n"
            "localStorage.setItem = () => { throw new Error('denied'); };\n"
        )
        out = self.drive(throwing + TYPED + CHECK + serve(live("high")), PRESS_SWITCH + HTML)
        assert isinstance(out, str)
        self.assertIn('aria-checked="true"', switch_of(drift_of(out)))
        self.assertIn("data-next-drift-level", out)

    def test_no_switch_on_a_harness_with_no_live_estimate(self) -> None:
        claude = self.html(TYPED)
        self.assertIn('role="switch"', aside_of(claude))
        pi = self.html(
            TYPED + '__s.harness = "pi";\n',
            ROUTE.replace("claude", "pi") + "\nawait __settle();\nawait __settle();\n" + HTML,
        )
        self.assertIn("<aside", pi)
        self.assertNotIn('role="switch"', aside_of(pi))


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheLevelTest(_LivePage):
    def test_the_level_shows_with_its_source_line_and_the_pill_beside_the_entry_count(
        self,
    ) -> None:
        html = self.on(live("medium"))
        drift = visible_text(drift_of(html))
        self.assertIn("Medium", drift)
        self.assertIn(SOURCE_LINE, drift)
        header = header_of(html)
        self.assertIn("data-next-drift-pill", header)
        self.assertIn("Drift: Medium", visible_text(header))
        # Beside "N entries", in the header's measured row.
        bar = header[header.index("next-session-detail-bar") :]
        self.assertLess(bar.index("entries"), bar.index("data-next-drift-pill"))

    def test_the_nudge_shows_at_high_and_extreme_and_not_below(self) -> None:
        for level, shown in (
            ("high", True),
            ("extreme", True),
            ("medium", False),
            ("none_or_low", False),
            ("not_enough", False),
        ):
            with self.subTest(level=level):
                text = visible_text(drift_of(self.on(live(level))))
                self.assertEqual(shown, NUDGE in text)

    def test_not_enough_recorded_yet_shows_as_the_level_with_no_pill(self) -> None:
        html = self.on(live("not_enough"))
        self.assertIn("Not enough recorded yet", visible_text(drift_of(html)))
        self.assertNotIn("data-next-drift-pill", html)

    def test_rose_from_names_the_entry_by_the_pages_own_number(self) -> None:
        html = self.on(live("high", rose_from="medium", rose_at="c-fail"))
        self.assertIn("Rose from Medium at #4.", visible_text(drift_of(html)))
        # The number is the list's: the same entry reads #4 in the activity column.
        self.assertRegex(visible_text(html), r"#4\b")

    def test_rose_from_is_withheld_when_the_page_cannot_number_the_entry(self) -> None:
        html = self.on(live("high", rose_from="medium", rose_at="not-in-the-record"))
        self.assertNotIn("Rose from", visible_text(html))

    def test_a_level_read_against_other_words_is_not_shown(self) -> None:
        html = self.on(live("high", revision=1))
        self.assertNotIn("data-next-drift-level", html)
        self.assertNotIn("data-next-drift-pill", html)

    def test_it_raises_no_notification(self) -> None:
        out = self.drive(
            TYPED + CHECK + serve(live("high")),
            PRESS_SWITCH + "console.log(JSON.stringify(__notifications));",
        )
        self.assertEqual([], out)


ANALYZING = """
__dashboard.reading_jobs = {"claude:focus-1": {id:"job-1", phase:"reading", steps:[]}};
"""


def segments_on(html: str) -> int:
    meter = re.search(r'<p class="next-session-drift-meter"[^>]*>([\s\S]*?)</p>', html)
    assert meter is not None, html[:400]
    return meter.group(1).count(" data-on")


@unittest.skipUnless(shutil.which("node"), "node not available")
class WhileAnalyzingTest(_LivePage):
    """The design's analyzing state: the title and pill stay, the detail line goes, the
    meter dims, and there is no nudge."""

    def test_the_detail_line_and_the_nudge_go_and_the_meter_dims(self) -> None:
        html = self.on(
            live("high", rose_from="medium", rose_at="c-fail"), setup=TYPED + CHECK + ANALYZING
        )
        drift = drift_of(html)
        text = visible_text(drift)
        self.assertIn("High", text)
        self.assertIn("data-next-drift-pill", header_of(html))
        self.assertNotIn(SOURCE_LINE, text)
        self.assertNotIn("Rose from", text)
        self.assertNotIn(NUDGE, text)
        self.assertRegex(drift, r'<p class="next-session-drift-meter"[^>]*\bdata-dim\b')

    def test_with_no_analysis_the_meter_is_not_dimmed(self) -> None:
        drift = drift_of(self.on(live("high")))
        self.assertIn(SOURCE_LINE, visible_text(drift))
        self.assertNotRegex(drift, r"\bdata-dim\b")


@unittest.skipUnless(shutil.which("node"), "node not available")
class OverAnUnsavedEditTest(_LivePage):
    def test_the_nudge_hides_while_the_level_and_the_pill_stay(self) -> None:
        html = self.html(
            TYPED + CHECK + serve(live("high")),
            '__typeGoal("Something quite different");\nawait __settle();\nrenderNext();\n' + HTML,
            seed={KEY: "1"},
        )
        text = visible_text(drift_of(html))
        self.assertIn("High", text)
        self.assertIn("data-next-drift-pill", header_of(html))
        self.assertNotIn(NUDGE, text)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheSwitchContractTest(_LivePage):
    """What the review's surviving mutants showed nothing held."""

    def test_the_switch_keeps_its_focus_key_across_the_redraw(self) -> None:
        self.assertIn(
            'data-next-focus="live-monitor:claude:focus-1"', switch_of(self.on(live("high")))
        )

    def test_its_accessible_name_is_live_monitor(self) -> None:
        html = self.on(live("high"))
        labelled = re.search(r'aria-labelledby="([^"]+)"', switch_of(html))
        assert labelled is not None
        label = re.search(rf'<[^>]*\bid="{labelled.group(1)}"[^>]*>([^<]*)<', html)
        assert label is not None
        self.assertEqual("Live monitor", label.group(1).strip())

    def test_the_nudge_is_never_announced(self) -> None:
        html = self.on(live("high"))
        nudge = re.search(r"<p\b[^>]*>(?=[^<]*" + re.escape(NUDGE[:20]) + ")", html)
        assert nudge is not None
        self.assertNotRegex(nudge.group(0), r"\brole=|aria-live")
        before = html[: nudge.start()]
        # Not inside any open live region.
        for opened in re.finditer(
            r"<(\w+)\b[^>]*(?:aria-live=|role=\"(?:status|alert|log)\")", before
        ):
            tag = opened.group(1)
            rest = before[opened.start() :]
            self.assertGreater(rest.count(f"</{tag}>"), rest.count(f"<{tag}") - 1, rest[:200])

    def test_a_press_redraws_at_once_without_waiting_for_the_next_poll(self) -> None:
        out = self.html(
            TYPED + CHECK + serve(live("high")),
            '__fire("click", {preventDefault(){}, target:{dataset:{nextCockpitAction:'
            '"live-monitor", arg:""}, closest(){ return this; }}});\n' + HTML,
        )
        self.assertIn('aria-checked="true"', switch_of(drift_of(out)))
        self.assertIn("data-next-drift-level", out)

    def test_the_hint_goes_when_the_switch_is_on(self) -> None:
        # With a level, and with none published yet: the hint is for turning it on.
        for row in (live("high"), None):
            with self.subTest(row=row):
                self.assertNotIn(HINT, visible_text(self.on(row)))

    def test_the_meter_fills_one_segment_per_level(self) -> None:
        for level, filled in (("none_or_low", 1), ("medium", 2), ("high", 3), ("extreme", 4)):
            with self.subTest(level=level):
                self.assertEqual(filled, segments_on(drift_of(self.on(live(level)))))


@unittest.skipUnless(shutil.which("node"), "node not available")
class NoLevelWithoutSavedWordsTest(_LivePage):
    def test_an_unsaved_draft_shows_no_level_and_no_pill_even_when_one_is_published(
        self,
    ) -> None:
        html = self.on(live("high"), setup=CHECK)
        self.assertIn(SAVE_FIRST, visible_text(drift_of(html)))
        self.assertNotIn("data-next-drift-level", html)
        self.assertNotIn("data-next-drift-pill", html)
        self.assertNotIn(NUDGE, visible_text(html))

    def test_the_draft_guard_holds_even_against_a_level_the_seam_hands_it(self) -> None:
        stub = 'nextDriftEstimate = () => ({level:"high", label:"High", source:"Live estimate"});\n'
        drafted = self.html(CHECK, stub + "renderNext();\n" + HTML, seed={KEY: "1"})
        self.assertNotIn("data-next-drift-pill", drafted)
        self.assertNotIn("data-next-drift-level", drafted)
        saved = self.html(TYPED + CHECK, stub + "renderNext();\n" + HTML, seed={KEY: "1"})
        self.assertIn("data-next-drift-pill", saved)

    def test_no_saved_revision_reads_save_your_intent(self) -> None:
        html = self.on(live("no_live_level"))
        self.assertIn(SAVE_FIRST, visible_text(drift_of(html)))
        self.assertNotIn("data-next-drift-pill", html)


@unittest.skipUnless(shutil.which("node"), "node not available")
class NeverOnASessionsRowTest(_LivePage):
    def test_the_sessions_view_shows_no_level_and_no_pill(self) -> None:
        out = self.drive(
            TYPED + CHECK + serve(live("high")),
            'navigateNext({view:"sessions"});\nawait __settle();\nawait __settle();\n' + HTML,
            seed={KEY: "1"},
        )
        assert isinstance(out, str)
        self.assertNotIn("data-next-drift-pill", out)
        self.assertNotIn("data-next-drift-level", out)
        self.assertNotIn("Drift: High", visible_text(out))
        self.assertNotIn("Live estimate", visible_text(out))


if __name__ == "__main__":
    unittest.main()
