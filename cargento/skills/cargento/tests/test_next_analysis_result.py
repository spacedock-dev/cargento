"""An analysis result on the session page: the level, each line against the record, and where the
work went (DRC-4695).

Items 6, 10 and 14 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
and items 1 and 2 of
[DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn).
The level is the server's `levels.analysis_level` over the stored reading, drawn in the Drift
section's level slot and the header pill; each line reads "Departs at #<n>", "Consistent with #<n>,
as the tool reported; not inspected", "Consistent with what the session said at #<n>; not a check"
or "Can't tell"; a headline and short account render only under a departure; "Where the work went"
groups written paths by folder; a stale result says why, with "Analyze again"; and "Not accurate?"
posts its token and nothing else.

Every assertion is on what a reader sees or what the page sends. Where the page draws a level, the
level the fake server answers is the one `levels.analysis_level` gives for the same facts.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import unittest
from typing import Any

from cargento_runtime import levels
from cargento_runtime import reading as runtime_reading

from .test_next_intent_draft import TYPED, _DraftPage, aside_of, drift_of, visible_text

DEPARTS = runtime_reading.RESULT_DEPARTURE
CONSISTENT = runtime_reading.RESULT_CONSISTENT
UNVERIFIABLE = runtime_reading.RESULT_UNVERIFIABLE
READ_AT = 106.0
NOTHING_FOUND = "Nothing found against what it read. This is not a check that the work was done."
SOURCE_LINE = "From the analysis at {time}: each line of your intent against the checks and messages it cited."
LINE_1 = "The parser tests pass"
LINE_2 = "Only src/parser changes"

WHO = {"harness": "claude", "sid": "focus-1"}
EVIDENCE = {"source": "Claude Bash call and paired result", "confidence": "exact"}


def _report(fact_id: str, at: float, subject: str, **extra: Any) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "at": at,
        "type": "tool_report",
        "subject": subject,
        "source_session": WHO,
        "evidence": EVIDENCE,
        **extra,
    }


# The fixture numbers the session's entries from the window at 100: fo-b #1, task-a #2 (the
# agent's own dispatch), fo-a #3; these follow at #4 to #8. A write before the window is not
# numbered and is not where this work went.
FACTS = (
    _report("c-pass", 104.5, "check", result="passed", summary="pytest tests/parser"),
    _report("w-lex", 104.6, "write", summary="src/parser/lex.py"),
    _report("w-gram", 104.7, "write", summary="src/parser/grammar.py"),
    _report("w-readme", 104.8, "write", summary="README.md"),
    _report("c-fail", 104.9, "check", result="failed", summary="pytest tests/lexer"),
    _report("w-early", 99.5, "write", summary="old/notes.md"),
)
NUMBER = {"c-pass": 4, "w-lex": 5, "w-gram": 6, "w-readme": 7, "c-fail": 8}

# Saved after every direction in the record, so none is a later one; two outcome lines.
QUIET = (
    "__s.annotation_goal_saved_at = 105;\n__s.annotation_window_start = 100;\n"
    f"__s.annotation_line_1 = {json.dumps(LINE_1)};\n"
    f"__s.annotation_line_2 = {json.dumps(LINE_2)};\n"
    '__s.annotation_lines_why = "";\n'
)
SCAN = {
    "harness": "claude",
    "sid": "focus-1",
    "failed": 1,
    "passed": 1,
    "not_recorded": 0,
    "background": 0,
    "written_paths": 5,
    "outside_paths": 0,
    "more": 0,
    "last_changing_command_at": None,
    "check_runs": 2,
    "distinct_checks": 2,
}


def scan_for(facts: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """The full-scan counts for these facts, with one written path the listing left out."""
    checks = [f for f in facts if f["subject"] == "check"]
    return {
        **SCAN,
        "failed": sum(1 for f in checks if f.get("result") == "failed"),
        "passed": sum(1 for f in checks if f.get("result") == "passed"),
        "check_runs": len(checks),
        "distinct_checks": len(checks),
        "written_paths": sum(1 for f in facts if f["subject"] == "write") + 1,
    }


def facts_js(facts: tuple[dict[str, Any], ...] = FACTS) -> str:
    return "".join(f"__semantic.facts.push({json.dumps(fact)});\n" for fact in facts)


def criterion(result: str | None, *cites: str, why: str = "", detail: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"cites": list(cites), "why": why, "detail": detail}
    if result is not None:
        row["result"] = result
    return row


def assessment(criteria: dict[str, Any], **over: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "revision_read": 2,
        "window_start": 100,
        "read_at": READ_AT,
        "evidence_through": 105.0,
        "criteria": criteria,
    }
    value.update(over)
    return value


def planted(value: dict[str, Any], *, not_accurate: bool = False) -> str:
    return (
        "__s.annotation_reading_count = 1;\n"
        f"__s.annotation_assessment = {json.dumps(value)};\n"
        f"__s.annotation_not_accurate = {json.dumps(not_accurate)};\n"
    )


def server_level(value: dict[str, Any], facts: tuple[dict[str, Any], ...] = FACTS) -> str:
    """What the server's function answers for this reading over these facts."""
    lines = sum(1 for key in value["criteria"] if key.startswith("line_"))
    found = levels.analysis_level(
        value,
        levels.Evidence(facts, scan_for(facts), 0),
        outcome_lines=lines,
    )
    return found.level


def serve(
    value: dict[str, Any] | None,
    level: str | None = None,
    facts: tuple[dict[str, Any], ...] = FACTS,
    **row: Any,
) -> str:
    """The focused project context answers with this analysis level and the session's scan."""
    live = row.pop("live", None)
    answer = (
        [
            {
                "harness": "claude",
                "sid": "focus-1",
                "revision_read": value["revision_read"],
                "read_at": value["read_at"],
                "computed_at": 107.0,
                "level": level,
                "reasons": [],
                "cites": [],
                **row,
            }
        ]
        if value is not None and level is not None
        else []
    )
    return (
        f"let __analysis = {json.dumps(answer)};\nlet __scan = {json.dumps(scan_for(facts))};\n"
        f"let __live = {json.dumps([live] if live else [])};\n"
        """
const __ctxUpstream2 = __fetchImpl;
__fetchImpl = async (url, init) => {
  const got = await __ctxUpstream2(url, init);
  if(!String(url).startsWith("/api/project-context") || !String(url).includes("session=")){
    return got;
  }
  const data = await got.json();
  const sources = data.sources || {};
  const work = sources.work || {};
  return {ok:true, status:200, json:async () => ({...data, sources:{...sources,
    work:{...work, analysis_levels: __analysis, live_levels: __live,
      tool_reports: [__scan]}}})};
};
"""
    )


def clock(at: float) -> str:
    return time.strftime("%H:%M", time.localtime(at))


def rows_of(html: str) -> list[str]:
    return [
        visible_text(match)
        for match in re.findall(r'<div class="next-cockpit-reading-row"[\s\S]*?</div>', html)
    ]


def result_of(html: str) -> str:
    drift = drift_of(html)
    start = drift.index("<h2>READING</h2>")
    return drift[start : drift.index("</section>", start)]


class _ResultPage(_DraftPage):
    def page(
        self,
        value: dict[str, Any] | None,
        level: str | None = None,
        *,
        extra: str = "",
        facts: tuple[dict[str, Any], ...] = FACTS,
        not_accurate: bool = False,
        after: str = "",
        **row: Any,
    ) -> Any:
        setup = TYPED + QUIET + facts_js(facts) + extra
        if value is not None:
            setup += planted(value, not_accurate=not_accurate)
        return self.drive(setup + serve(value, level, facts, **row), after)


# A departure on line 1, citing the failed check; line 2 consistent on the passing check; the
# goal resting on the agent's own dispatch.
MIXED = assessment(
    {
        "goal": criterion(CONSISTENT, "task-a"),
        "line_1": criterion(DEPARTS, "c-fail", detail="The lexer tests fail after the change."),
        "line_2": criterion(CONSISTENT, "c-pass"),
    }
)
ALL_CONSISTENT = assessment(
    {
        "goal": criterion(CONSISTENT, "task-a"),
        "line_1": criterion(CONSISTENT, "c-pass"),
        "line_2": criterion(CONSISTENT, "c-pass"),
    }
)
ALL_CANT_TELL = assessment(
    {
        "goal": criterion(UNVERIFIABLE, why="uncited"),
        "line_1": criterion(UNVERIFIABLE, why="uncited"),
        "line_2": criterion(UNVERIFIABLE, why="uncited"),
    }
)
NO_FAILURE = tuple(f for f in FACTS if f["fact_id"] != "c-fail")


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheLevelTest(_ResultPage):
    def test_the_analysis_level_shows_in_the_level_slot_with_its_source_and_time(self) -> None:
        html = self.page(MIXED, levels.HIGH)
        drift = visible_text(drift_of(html))
        self.assertIn("High", drift)
        self.assertIn(f"Analysis · {clock(READ_AT)}", drift)
        self.assertIn(SOURCE_LINE.format(time=clock(READ_AT)), drift)
        self.assertIn("data-next-drift-level", html)
        # The header pill too, with the live monitor off: the switch hides the live level only.
        self.assertIn("Drift: High", visible_text(html[: html.index("<aside")]))

    def test_it_is_drawn_over_the_live_estimate_when_both_are_published(self) -> None:
        switch = "nextLiveMonitorMemory.set('cargento.next.live-estimate:claude:focus-1', true);\n"
        live = {
            "harness": "claude",
            "sid": "focus-1",
            "revision": 2,
            "computed_at": 107.0,
            "level": levels.MEDIUM,
            "reasons": [],
            "rose_from": None,
            "rose_at": None,
        }
        # The live estimate alone shows, so the switch and the served row are live.
        alone = visible_text(drift_of(self.page(None, extra=switch, live=live)))
        self.assertIn("Live estimate", alone)
        html = self.page(MIXED, levels.HIGH, extra=switch, live=live)
        drift = visible_text(drift_of(html))
        self.assertIn(f"Analysis · {clock(READ_AT)}", drift)
        self.assertNotIn("Live estimate", drift)
        self.assertIn("Drift: High", visible_text(html[: html.index("<aside")]))

    def test_a_reading_of_words_since_replaced_yields_to_the_live_estimate(self) -> None:
        # Revision 1's reading scores None or low against its own two lines; revision 2 is the
        # saved intent, and the live estimate for it is High. A level for words the reader has
        # replaced is not drawn, in the slot or the pill, and the live estimate stands.
        stale = assessment(ALL_CONSISTENT["criteria"], revision_read=1)
        level = server_level(stale, NO_FAILURE)
        self.assertEqual(levels.NONE_OR_LOW, level)
        switch = "nextLiveMonitorMemory.set('cargento.next.live-estimate:claude:focus-1', true);\n"
        live = {
            "harness": "claude",
            "sid": "focus-1",
            "revision": 2,
            "computed_at": 107.0,
            "level": levels.HIGH,
            "reasons": [],
            "rose_from": None,
            "rose_at": None,
        }
        html = self.page(stale, level, facts=NO_FAILURE, extra=switch, live=live)
        drift = visible_text(drift_of(html))
        self.assertIn("Live estimate", drift)
        self.assertNotIn("None or low", drift)
        self.assertNotIn("Analysis ·", drift)
        self.assertIn("Drift: High", visible_text(html[: html.index("<aside")]))
        # The reading itself still says why it is stale and offers another press.
        self.assertIn("Your intent changed after this analysis.", visible_text(result_of(html)))
        # With the switch off there is no live estimate, and still no stale level.
        off = self.page(stale, level, facts=NO_FAILURE)
        self.assertNotIn("None or low", visible_text(drift_of(off)))
        self.assertNotIn("data-next-drift-pill", off)

    def test_a_level_computed_for_another_reading_is_not_drawn(self) -> None:
        html = self.page(MIXED, levels.HIGH, read_at=READ_AT - 1)
        self.assertNotIn("data-next-drift-level", html)
        self.assertNotIn("data-next-drift-pill", html)

    def test_it_never_shows_on_a_sessions_row(self) -> None:
        out = self.page(
            MIXED,
            levels.HIGH,
            after='navigateNext({view:"sessions"});\nawait __settle();\nawait __settle();\n'
            "console.log(JSON.stringify(__els.app.innerHTML));",
        )
        self.assertNotIn("data-next-drift-pill", out)
        self.assertNotIn("Drift: High", visible_text(out))
        self.assertNotIn("Analysis ·", visible_text(out))

    def test_every_line_cant_tell_never_reads_none_or_low(self) -> None:
        # The server's own function over this reading.
        level = server_level(ALL_CANT_TELL, NO_FAILURE)
        self.assertEqual(levels.NOT_ENOUGH, level)
        html = self.page(ALL_CANT_TELL, level, facts=NO_FAILURE)
        self.assertIn("Not enough recorded yet", visible_text(drift_of(html)))
        # And the page holds the line against a level that says otherwise.
        forged = self.page(ALL_CANT_TELL, levels.NONE_OR_LOW, facts=NO_FAILURE)
        self.assertNotIn("None or low", visible_text(drift_of(forged)))
        self.assertIn("Not enough recorded yet", visible_text(drift_of(forged)))
        self.assertNotIn("data-next-drift-pill", forged)

    def test_none_or_low_shows_where_every_line_the_page_draws_is_consistent(self) -> None:
        html = self.page(ALL_CONSISTENT, levels.NONE_OR_LOW, facts=NO_FAILURE)
        self.assertIn("None or low", visible_text(drift_of(html)))
        # One line the page demotes is enough to withhold it.
        demoted = assessment(
            {
                "goal": criterion(CONSISTENT, "task-a"),
                "line_1": criterion(CONSISTENT, "c-pass"),
                "line_2": criterion(CONSISTENT, "w-lex"),
            }
        )
        held = self.page(demoted, levels.NONE_OR_LOW, facts=NO_FAILURE)
        self.assertNotIn("None or low", visible_text(drift_of(held)))


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheRowsTest(_ResultPage):
    def test_a_departure_row_cites_its_entry_by_the_lists_number(self) -> None:
        html = self.page(MIXED, levels.HIGH)
        rows = rows_of(result_of(html))
        departing = [r for r in rows if "LINE 1" in r]
        self.assertEqual(1, len(departing))
        self.assertIn(f"Departs at #{NUMBER['c-fail']}", departing[0])
        # The same number is the activity list's, and the entry is flagged Cited there.
        entry = re.search(
            r'<div class="next-cockpit-work-row"[^>]*data-next-entry-id="c-fail"', html
        )
        assert entry is not None
        self.assertIn(f'data-next-entry="{NUMBER["c-fail"]}"', entry.group(0))
        self.assertIn('data-next-entry-flag="cited"', html[entry.start() : entry.start() + 1200])

    def test_a_consistent_row_names_the_check_as_the_tool_reported(self) -> None:
        rows = rows_of(result_of(self.page(MIXED, levels.HIGH)))
        (line_2,) = [r for r in rows if "LINE 2" in r]
        self.assertIn(
            f"Consistent with #{NUMBER['c-pass']}, as the tool reported; not inspected", line_2
        )

    def test_a_row_resting_on_the_agents_own_account_says_so(self) -> None:
        rows = rows_of(result_of(self.page(MIXED, levels.HIGH)))
        (goal,) = [r for r in rows if "GOAL" in r]
        self.assertIn("Consistent with what the session said at #2; not a check", goal)
        self.assertNotIn("as the tool reported", goal)

    def test_a_line_added_from_an_entry_names_it_by_the_lists_number(self) -> None:
        entry_line = (
            '__s.annotation_line_2_source = "entry";\n__s.annotation_line_2_source_id = "fo-a";\n'
        )
        rows = rows_of(result_of(self.page(MIXED, levels.HIGH, extra=entry_line)))
        (line_2,) = [r for r in rows if "LINE 2" in r]
        self.assertIn("EXPECTED OUTCOME · LINE 2 · ADDED FROM #3", line_2)
        self.assertNotIn("ADDED FROM AN ENTRY", line_2)

    def test_no_row_says_done_or_draws_a_check_mark(self) -> None:
        result = visible_text(result_of(self.page(ALL_CONSISTENT, levels.NONE_OR_LOW)))
        for word in ("Done", "✓", "✔", "Not started"):
            self.assertNotIn(word, result)

    def test_a_line_nothing_shows_reads_cant_tell(self) -> None:
        bare = assessment(
            {
                "goal": criterion(CONSISTENT, "task-a"),
                "line_1": criterion(UNVERIFIABLE),
                "line_2": criterion(UNVERIFIABLE, why="uncited"),
            }
        )
        rows = rows_of(result_of(self.page(bare, levels.NOT_ENOUGH)))
        (line_1,) = [r for r in rows if "LINE 1" in r]
        (line_2,) = [r for r in rows if "LINE 2" in r]
        self.assertIn("Can't tell: nothing recorded shows this yet", line_1)
        self.assertIn("Can't tell", line_2)
        self.assertIn("Nothing resolvable was cited", line_2)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheAnswerTest(_ResultPage):
    """Item 14's reducer, as the reader sees it."""

    def answer_of(self, html: str) -> str:
        found = re.search(r'<div class="next-cockpit-result-answer"[\s\S]*?</div>', html)
        assert found is not None, result_of(html)[:600]
        return visible_text(found.group(0)).strip()

    def test_a_departure_gives_the_headline_its_count_and_the_account(self) -> None:
        html = self.page(MIXED, levels.HIGH)
        answer = self.answer_of(html)
        self.assertIn("Departs from your intent", answer)
        self.assertIn("1 departure", answer)
        self.assertIn(f"The lexer tests fail after the change. (#{NUMBER['c-fail']})", answer)

    def test_a_failed_check_in_the_window_outranks_cant_tell(self) -> None:
        answer = self.answer_of(self.page(ALL_CANT_TELL, levels.HIGH))
        self.assertIn(f"A check failed at #{NUMBER['c-fail']}.", answer)
        self.assertNotIn("Can't tell", answer)
        self.assertNotIn("departure", answer)

    def test_a_failed_check_in_the_window_outranks_nothing_found(self) -> None:
        answer = self.answer_of(self.page(ALL_CONSISTENT, levels.HIGH))
        self.assertIn(f"A check failed at #{NUMBER['c-fail']}.", answer)
        self.assertNotIn("Nothing found", answer)

    def test_a_failed_check_before_the_window_does_not(self) -> None:
        early = tuple({**f, "at": 99.0} if f["fact_id"] == "c-fail" else f for f in FACTS)
        answer = self.answer_of(self.page(ALL_CONSISTENT, levels.NOT_ENOUGH, facts=early))
        self.assertEqual(NOTHING_FOUND, answer)

    def test_every_line_consistent_and_no_failure_is_nothing_found(self) -> None:
        answer = self.answer_of(self.page(ALL_CONSISTENT, levels.NONE_OR_LOW, facts=NO_FAILURE))
        self.assertEqual(NOTHING_FOUND, answer)

    def test_a_reading_with_a_goal_and_no_line_cannot_tell(self) -> None:
        # A saved goal with no outcome line is enough to press; the goal row alone is not an
        # answer against what the work was for.
        goal_only = assessment({"goal": criterion(CONSISTENT, "task-a")})
        no_lines = '__s.annotation_line_1 = "";\n__s.annotation_line_2 = "";\n'
        html = self.page(goal_only, levels.NOT_ENOUGH, facts=NO_FAILURE, extra=no_lines)
        self.assertIn("Consistent with what the session said", visible_text(result_of(html)))
        self.assertEqual("Can't tell", self.answer_of(html))

    def test_a_malformed_or_missing_line_result_gives_cant_tell(self) -> None:
        malformed = assessment(
            {
                "goal": criterion(CONSISTENT, "task-a"),
                "line_1": criterion(CONSISTENT, "c-pass"),
                "line_2": criterion(None, "c-pass"),
            }
        )
        missing = assessment(
            {"goal": criterion(CONSISTENT, "task-a"), "line_1": criterion(CONSISTENT, "c-pass")}
        )
        for value in (malformed, missing):
            with self.subTest(value=value):
                answer = self.answer_of(self.page(value, levels.NOT_ENOUGH, facts=NO_FAILURE))
                self.assertEqual("Can't tell", answer)

    def test_a_departure_count_and_the_headline_render_only_beside_a_departure(self) -> None:
        for value, facts in (
            (ALL_CANT_TELL, FACTS),
            (ALL_CONSISTENT, NO_FAILURE),
            (ALL_CANT_TELL, NO_FAILURE),
        ):
            with self.subTest(value=value, facts=len(facts)):
                result = visible_text(result_of(self.page(value, levels.NOT_ENOUGH, facts=facts)))
                self.assertNotRegex(result, r"\b\d+ departures?\b")
                self.assertNotIn("Departs from your intent", result)

    def test_a_departure_the_page_demotes_is_no_departure(self) -> None:
        # Resting on a passing check, a departure is not valid (rule 3 and item 8 of DEC-23).
        demoted = assessment(
            {
                "goal": criterion(CONSISTENT, "task-a"),
                "line_1": criterion(DEPARTS, "c-pass", detail="It departs."),
                "line_2": criterion(CONSISTENT, "c-pass"),
            }
        )
        answer = self.answer_of(self.page(demoted, levels.MEDIUM, facts=NO_FAILURE))
        self.assertEqual("Can't tell", answer)


@unittest.skipUnless(shutil.which("node"), "node not available")
class WhereTheWorkWentTest(_ResultPage):
    def work_of(self, html: str) -> str:
        found = re.search(r'<div class="next-cockpit-result-work"[\s\S]*?</div>', html)
        assert found is not None, result_of(html)[:800]
        return visible_text(found.group(0))

    def test_written_paths_in_the_window_group_by_folder(self) -> None:
        work = self.work_of(self.page(MIXED, levels.HIGH))
        self.assertIn("Where the work went", work)
        self.assertIn(f"src/parser 2 files #{NUMBER['w-lex']}, #{NUMBER['w-gram']}", work)
        self.assertIn(f"The working directory 1 file #{NUMBER['w-readme']}", work)
        # Before the window, not where this work went.
        self.assertNotIn("old", work)

    def test_writes_the_listing_left_out_are_counted(self) -> None:
        # The scan counts five written paths and the page holds four of them.
        work = self.work_of(self.page(MIXED, levels.HIGH))
        self.assertIn("1 more written file is counted and not listed.", work)

    def test_with_no_write_listed_there_is_no_section(self) -> None:
        checks = tuple(f for f in FACTS if f["subject"] == "check")
        html = self.page(MIXED, levels.HIGH, facts=checks)
        self.assertNotIn("next-cockpit-result-work", html)


@unittest.skipUnless(shutil.which("node"), "node not available")
class AStaleResultSaysWhyTest(_ResultPage):
    def stale_of(self, html: str) -> str:
        found = re.search(r'<div class="next-cockpit-result-stale"[\s\S]*?</div>', html)
        return visible_text(found.group(0)) if found else ""

    def test_changed_words_say_your_intent_changed_with_analyze_again(self) -> None:
        html = self.page(assessment(MIXED["criteria"], revision_read=1), levels.HIGH)
        stale = self.stale_of(html)
        self.assertIn("Your intent changed after this analysis.", stale)
        self.assertIn("This reading read revision 1. Revision 2 is current", stale)
        self.assertIn("Analyze again", stale)
        button = re.search(r"<button[^>]*>Analyze again</button>", html)
        assert button is not None
        self.assertIn('data-next-cockpit-action="reading-ask"', button.group(0))

    def test_an_entry_after_what_it_read_says_new_work_since(self) -> None:
        html = self.page(assessment(MIXED["criteria"], evidence_through=104.85), levels.HIGH)
        stale = self.stale_of(html)
        self.assertIn("New work since this analysis.", stale)
        self.assertNotIn("Your intent changed", stale)
        self.assertIn("Analyze again", stale)

    def test_a_current_result_has_no_banner(self) -> None:
        self.assertEqual("", self.stale_of(self.page(MIXED, levels.HIGH)))

    def test_a_result_stored_with_no_evidence_time_claims_no_new_work(self) -> None:
        value = assessment(MIXED["criteria"])
        value.pop("evidence_through")
        self.assertEqual("", self.stale_of(self.page(value, levels.HIGH)))

    def test_a_result_with_no_evidence_time_counts_new_work_from_when_it_read(self) -> None:
        late = (*FACTS, _report("w-late", READ_AT + 4, "write", summary="src/parser/late.py"))
        value = assessment(MIXED["criteria"])
        value.pop("evidence_through")
        stale = self.stale_of(self.page(value, levels.HIGH, facts=late))
        self.assertIn("New work since this analysis.", stale)
        self.assertIn("Analyze again", stale)

    def test_analyze_again_is_not_offered_while_the_question_before_the_press_stands(
        self,
    ) -> None:
        # The words saved at 103 make fo-a (104) an unsettled later direction.
        unsettled = "__s.annotation_goal_saved_at = 103;\n"
        html = self.page(
            assessment(MIXED["criteria"], revision_read=1), levels.HIGH, extra=unsettled
        )
        self.assertIn("Your intent changed after this analysis.", self.stale_of(html))
        self.assertNotIn(">Analyze again</button>", html)


@unittest.skipUnless(shutil.which("node"), "node not available")
class NotAccurateTest(_ResultPage):
    PRESS = (
        '__press("not-accurate", __argOf("not-accurate"));\nawait __settle();\n'
        "await __settle();\n"
        "console.log(JSON.stringify({html:__els.app.innerHTML, posts:__posts}));"
    )

    def button_of(self, html: str) -> str:
        found = re.search(r'<button\b[^>]*data-next-cockpit-action="not-accurate"[^>]*>', html)
        assert found is not None, result_of(html)[-600:]
        return found.group(0)

    def test_it_is_offered_on_a_result_unpressed(self) -> None:
        html = self.page(MIXED, levels.HIGH)
        self.assertIn('aria-pressed="false"', self.button_of(html))
        self.assertIn("Not accurate?", visible_text(result_of(html)))

    def test_the_press_sends_the_token_and_nothing_else(self) -> None:
        out = self.page(MIXED, levels.HIGH, after=self.PRESS)
        assert isinstance(out, dict)
        self.assertEqual(
            [
                {
                    "url": "/api/annotate",
                    "body": {
                        "harness": "claude",
                        "sid": "focus-1",
                        "not_accurate": True,
                        "read_at": READ_AT,
                    },
                }
            ],
            out["posts"],
        )

    def test_a_marked_reading_says_so_and_a_press_takes_the_mark_back(self) -> None:
        html = self.page(MIXED, levels.HIGH, not_accurate=True)
        self.assertIn('aria-pressed="true"', self.button_of(html))
        self.assertIn("You marked this analysis not accurate.", visible_text(result_of(html)))
        out = self.page(MIXED, levels.HIGH, not_accurate=True, after=self.PRESS)
        assert isinstance(out, dict)
        self.assertIs(False, out["posts"][0]["body"]["not_accurate"])

    def test_a_refused_mark_says_it_was_not_saved(self) -> None:
        refuse = (
            '__reply["/api/annotate"] = () => ({status:200, body:{ok:true, persisted:false,'
            ' outcome:"refused"}});\n'
        )
        out = self.page(MIXED, levels.HIGH, extra=refuse, after=self.PRESS)
        assert isinstance(out, dict)
        self.assertIn(
            "Your mark was not saved. Press Not accurate? again to retry.",
            visible_text(result_of(out["html"])),
        )

    def test_there_is_nothing_to_mark_without_a_reading(self) -> None:
        html = self.page(None)
        self.assertNotIn('data-next-cockpit-action="not-accurate"', aside_of(html))


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheReducerTest(_ResultPage):
    """`nextDriftAnswer` alone, so each of item 14's rules can be shown to bind."""

    def reduce(self, value: dict[str, Any], facts: tuple[dict[str, Any], ...] = FACTS) -> Any:
        after = (
            "const __sess = nextCockpitFocusedSession(nextCockpitRouteGroup());\n"
            "const __group = nextCockpitRouteGroup();\n"
            "const __src = nextCockpitWorkSource(__group, __sess);\n"
            "const __ann = nextCockpitAnnotation(__sess);\n"
            "const __entries = __src.all || __src.entries;\n"
            "const __shape = nextCockpitReadingShape(__ann.assessment, __ann, __entries,"
            " nextReadingOutputLimit('claude'), false);\n"
            "const __got = nextDriftAnswer(__shape, __entries);\n"
            "console.log(JSON.stringify({kind: __got.kind, count: __got.count == null ? null"
            " : __got.count, failed: __got.failed ? __got.failed.id : null}));"
        )
        return self.page(value, levels.NOT_ENOUGH, facts=facts, after=after)

    def test_each_rule_in_order(self) -> None:
        self.assertEqual({"kind": "departs", "count": 1, "failed": None}, self.reduce(MIXED))
        self.assertEqual(
            {"kind": "failed-check", "count": None, "failed": "c-fail"},
            self.reduce(ALL_CANT_TELL),
        )
        self.assertEqual(
            {"kind": "cant-tell", "count": None, "failed": None},
            self.reduce(ALL_CANT_TELL, NO_FAILURE),
        )
        self.assertEqual(
            {"kind": "nothing-found", "count": None, "failed": None},
            self.reduce(ALL_CONSISTENT, NO_FAILURE),
        )

    def test_the_latest_failure_is_the_one_named(self) -> None:
        later = (*FACTS, _report("c-fail-2", 104.95, "check", result="failed", summary="ruff"))
        self.assertEqual("c-fail-2", self.reduce(ALL_CANT_TELL, later)["failed"])

    def test_an_untimed_failure_counts_as_inside_the_window(self) -> None:
        untimed = tuple({**f, "at": None} if f["fact_id"] == "c-fail" else f for f in FACTS)
        self.assertEqual("failed-check", self.reduce(ALL_CONSISTENT, untimed)["kind"])


if __name__ == "__main__":
    unittest.main()
