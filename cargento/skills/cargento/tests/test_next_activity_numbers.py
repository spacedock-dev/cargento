"""Session activity numbers its entries and flags the ones an analysis cites (DRC-4694).

[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
items 6 and 11, with the owner's build decisions of 2026-09-25: with no saved intent the whole
record is numbered; with one, #1 is the first entry at the evidence-window start and earlier
entries are counted, not listed; a cited entry from before the window shows unnumbered with its
time; a missing window start is said; order is time with the fact id as the tie-break; "Cited"
comes only from the current reading's surviving departures; a later direction is flagged by the
predicate the conflict block uses, stays flagged when settled, and is never drift; the list sits
right after CURRENT ACTIVITY under "Session activity" and OBSERVED RECORD is retired; the header's
second row says "N entries", and says nothing when the record was not read.

Every assertion reads the assembled page a reader would see.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from typing import Any

from .next_harness import storage_prelude
from .test_next_drift_panel import FIXTURE, PanelPage, aside_of, visible_text

ROW = re.compile(r'<div class="next-cockpit-work-row"')
NUMBER = re.compile(r'class="next-cockpit-work-n">(?:#(\d+))?')
SUMMARY = re.compile(
    r'class="next-cockpit-work-(?:summary|derived)">([^<]*)<',
)
FLAG = re.compile(r'class="next-cockpit-work-flag"[^>]*>([^<]*)<')

# Strings the design draws for this list that a ruling replaces (README table, DEC-24 item 11,
# DEC-16, and the build decisions on DRC-4694).
OVERRULED = (
    "Key turns",
    " turns ·",
    "turn 29",
    "In progress",
    "Correction from drift analysis",
    "Drift began",
    "Off goal",
    "Breaks outcome",
    "OBSERVED RECORD",
)


def facts_js(harness: str, rows: list[Any]) -> str:
    """Replace the fixture's facts with `rows`, each naming this session."""
    made = []
    for fact_id, at, kind, summary, extra in rows:
        fact = {
            "fact_id": fact_id,
            "at": at,
            "type": kind,
            "summary": summary,
            "source_session": {"harness": harness, "sid": "focus-1"},
            "evidence": {"source": "transcript", "confidence": "exact"},
            **extra,
        }
        made.append(fact)
    return (
        f"__semantic.facts = {json.dumps(made)};\n"
        "__dashboard.generated = 1000;\n"
        "nextCockpitContexts.clear();\n"
    )


def record_of(html: str) -> str:
    start = html.index("data-next-cockpit-work")
    start = html.rindex("<section", 0, start)
    return html[start : html.index("</section>", start)]


def text_of(html: str) -> str:
    return visible_text(record_of(html)).replace("\u2019", "'")


def rows_of(html: str) -> list[dict[str, Any]]:
    record = record_of(html)
    out = []
    for part in ROW.split(record)[1:]:
        number = NUMBER.search(part)
        summary = SUMMARY.search(part)
        out.append(
            {
                "n": int(number.group(1)) if number and number.group(1) else None,
                "summary": summary.group(1) if summary else "",
                "flags": FLAG.findall(part),
                "text": visible_text(part),
            }
        )
    return out


def meta_of(html: str) -> str:
    found = re.search(r'<p class="next-session-detail-meta">([^<]*)</p>', html)
    return found.group(1) if found else ""


def departure(cites: list[str], key: str = "goal", result: str = "departure") -> str:
    criterion = {"result": result, "detail": "It went elsewhere.", "cites": cites}
    return (
        "__dashboard.sessions[0].annotation_reading_count = 1;\n"
        "__dashboard.sessions[0].annotation_assessment = "
        + json.dumps({"revision_read": 2, "criteria": {key: criterion}})
        + ";\n"
    )


WINDOW = "__dashboard.sessions[0].annotation_window_start = 60;\n"

# A saved intent at 100 whose window opens at the prompt at 60: two entries before it, the prompt,
# and two after.
Fact = tuple[str, float, str, str, dict[str, Any]]

WINDOWED: list[Fact] = [
    ("old-1", 40, "user_message", "an older prompt", {}),
    ("old-2", 50, "task_result", "older work", {}),
    ("p", 60, "user_message", "please add retry", {}),
    ("a1", 70, "task_result", "added the wrapper", {}),
    ("a2", 80, "task_result", "wired it in", {}),
]


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheActivityListNumbersItsEntriesTest(PanelPage):
    def render(
        self, rows: list[Any], setup: str = "", after: str = "", harness: str = "claude"
    ) -> str:
        return self.page(harness, facts_js(harness, rows) + setup, after=after)

    def test_numbering_starts_at_the_window_start_and_counts_the_earlier_entries(self) -> None:
        html = self.render(WINDOWED, WINDOW)
        rows = rows_of(html)
        self.assertEqual(
            [(1, "please add retry"), (2, "added the wrapper"), (3, "wired it in")],
            [(row["n"], row["summary"]) for row in rows],
        )
        text = text_of(html)
        self.assertIn("2 earlier entries, from before your intent's window opened, are", text)
        self.assertNotIn("an older prompt", text)
        self.assertIn("3 entries", meta_of(html))

    def test_with_no_saved_intent_the_whole_record_is_numbered(self) -> None:
        cleared = (
            "for(const name of ['goal','revision','revision_count','at','window_start']){\n"
            "  __dashboard.sessions[0][`annotation_${name}`] = null;\n}\n"
        )
        for label, setup in (
            ("no revision", cleared),
            ("annotations off", "__dashboard.annotate = false;\n" + WINDOW),
        ):
            with self.subTest(label):
                html = self.render(WINDOWED, setup)
                rows = rows_of(html)
                self.assertEqual([1, 2, 3, 4, 5], [row["n"] for row in rows])
                self.assertEqual("an older prompt", rows[0]["summary"])
                self.assertNotIn("earlier entr", text_of(html))
                self.assertEqual([], [row for row in rows if row["flags"]])
                self.assertIn("5 entries", meta_of(html))

    def test_two_entries_at_one_time_number_by_fact_id_whatever_the_payload_order(self) -> None:
        checks = [
            ("c-b", 70, "tool_report", "ruff check .", {"subject": "check", "result": "passed"}),
            ("c-a", 70, "tool_report", "pytest", {"subject": "check", "result": "passed"}),
        ]
        seen = []
        for order in (checks, list(reversed(checks))):
            html = self.render([WINDOWED[2], *order], WINDOW)
            seen.append([(row["n"], row["summary"]) for row in rows_of(html)])
        self.assertEqual(seen[0], seen[1])
        self.assertEqual([(1, "please add retry"), (2, "pytest"), (3, "ruff check .")], seen[0])

    def test_numbers_hold_when_an_entry_arrives_at_the_end(self) -> None:
        before = self.render(WINDOWED, WINDOW)
        after = self.render([*WINDOWED, ("a3", 90, "task_result", "ran the suite", {})], WINDOW)
        first = {row["summary"]: row["n"] for row in rows_of(before)}
        second = {row["summary"]: row["n"] for row in rows_of(after)}
        self.assertEqual(first, {key: second[key] for key in first})
        self.assertEqual(4, second["ran the suite"])

    def test_a_missing_window_start_is_said_rather_than_mislabelling_one(self) -> None:
        html = self.render(WINDOWED[3:], WINDOW)
        text = text_of(html)
        self.assertIn(
            "The record read here no longer reaches back to where your intent's window opens, "
            "so #1 is the first entry it holds after that point.",
            text,
        )
        self.assertEqual([1, 2], [row["n"] for row in rows_of(html)])
        # A window at the save time is where typed words with no earlier message open, and no
        # entry is expected there.
        saved = self.render(
            WINDOWED[3:], "__dashboard.sessions[0].annotation_window_start = 100;\n"
        )
        self.assertNotIn("no longer reaches back", text_of(saved))

    def test_a_cited_entry_from_before_the_window_shows_unnumbered_with_its_time(self) -> None:
        html = self.render(WINDOWED, WINDOW + departure(["old-2"]))
        rows = rows_of(html)
        cited = [row for row in rows if row["summary"] == "older work"]
        self.assertEqual(1, len(cited), rows)
        self.assertIsNone(cited[0]["n"])
        self.assertEqual(["Cited"], cited[0]["flags"])
        self.assertIn("ago", cited[0]["text"])
        self.assertEqual([None, 1, 2, 3], [row["n"] for row in rows])
        self.assertIn(
            "are counted and not listed, except the one the analysis cites, listed with its time "
            "and no number.",
            text_of(html),
        )

    def test_a_cited_entry_past_the_bound_is_drawn_at_its_own_number(self) -> None:
        rows = [
            WINDOWED[2],
            ("early", 61, "task_result", "the early change", {}),
            *[(f"w{n}", 62 + n, "task_result", f"work {n}", {}) for n in range(25)],
        ]
        html = self.render(rows, WINDOW + departure(["early"]))
        drawn = rows_of(html)
        self.assertEqual([2, *range(8, 28)], [row["n"] for row in drawn])
        self.assertEqual(["Cited"], drawn[0]["flags"])
        self.assertEqual("the early change", drawn[0]["summary"])
        self.assertIn(
            "Listing 21 of 27 entries: the 20 most recent and every entry the analysis cites. "
            "6 are counted and not listed.",
            text_of(html),
        )
        self.assertIn("27 entries", meta_of(html))

    def test_cited_comes_only_from_a_departure_that_survived(self) -> None:
        base = [
            *WINDOWED,
            ("snap", 85, "observer_snapshot", "a derived summary", {}),
            (
                "pass",
                86,
                "tool_report",
                "pytest",
                {"subject": "check", "result": "passed", "result_source": "flag"},
            ),
        ]

        def flagged(setup: str, rows: list[Any] = base) -> dict[str, list[str]]:
            html = self.render(rows, WINDOW + setup)
            return {row["summary"]: row["flags"] for row in rows_of(html) if row["flags"]}

        self.assertEqual({"added the wrapper": ["Cited"]}, flagged(departure(["a1"])))
        cases = {
            "uncited": departure([]),
            "derived only": departure(["snap"]),
            "a check that does not show it": departure(["pass"]),
            "a consistent row": departure(["a1"], result="consistent"),
            "malformed": departure(["a1"]).replace('"revision_read"', '"revisionRead"'),
            "refused": "__dashboard.sessions[0].annotation_reading_refused = true;\n",
        }
        for label, setup in cases.items():
            with self.subTest(label):
                self.assertEqual({}, flagged(setup))
        # An unsettled later direction demotes every departure: its own flag stands, and no
        # entry is Cited.
        later = [*base, ("later", 120, "user_message", "also clean the logs", {})]
        self.assertEqual(
            {"also clean the logs": ["A later direction you gave"]},
            flagged(departure(["a1"]), later),
        )
        # A consistent row's entry stays listed.
        html = self.render(base, WINDOW + departure(["a1"], result="consistent"))
        self.assertIn("added the wrapper", [row["summary"] for row in rows_of(html)])

    def test_a_replaced_reading_leaves_no_flag_behind(self) -> None:
        html = self.render(
            WINDOWED,
            WINDOW + departure(["a1"]),
            after=departure(["a2"]) + "renderNext();\nawait __settle();\n",
        )
        flagged = {row["summary"]: row["flags"] for row in rows_of(html) if row["flags"]}
        self.assertEqual({"wired it in": ["Cited"]}, flagged)

    def test_a_later_direction_is_flagged_settled_or_not_and_never_as_drift(self) -> None:
        rows = [*WINDOWED, ("later", 120, "user_message", "also clean the logs", {})]
        unsettled = self.render(rows, WINDOW)
        settled = self.render(
            rows,
            WINDOW
            + "__dashboard.sessions[0].annotation_settled_through = 120;\n"
            + "__dashboard.sessions[0].annotation_settled_at = 130;\n"
            + "__dashboard.sessions[0].annotation_settled_revision = 2;\n",
        )
        for label, html in (("unsettled", unsettled), ("settled", settled)):
            with self.subTest(label):
                drawn = rows_of(html)
                flagged = [row for row in drawn if row["flags"]]
                self.assertEqual(["also clean the logs"], [row["summary"] for row in flagged])
                self.assertEqual(["A later direction you gave"], flagged[0]["flags"])
                self.assertEqual(4, flagged[0]["n"])
                for row in drawn:
                    self.assertNotIn("drift", row["text"].lower())
        # The flag and the conflict block read one predicate: what the block lists as unsettled
        # is exactly what the list flags while nothing is settled.
        conflict = re.findall(r'class="next-cockpit-conflict-text">([^<]*)<', unsettled)
        self.assertEqual(["also clean the logs"], conflict)
        self.assertIn("You settled this", settled)
        # The opening prompt, at the window start and before the save, is never one.
        self.assertEqual([], rows_of(unsettled)[0]["flags"])

    def test_the_header_count_is_absent_when_the_record_was_not_read(self) -> None:
        after = (
            "const keys = [...nextCockpitContexts.keys()];\n"
            "nextCockpitContexts.clear();\n"
            "for(const key of keys) nextCockpitContexts.set(key, {data:null, revision:1, error:true});\n"
            "renderNext();\n"
        )
        html = self.render(WINDOWED, WINDOW + departure(["a1"]), after=after)
        self.assertNotIn("entries", meta_of(html))
        self.assertNotIn("0 entr", meta_of(html))
        self.assertTrue(meta_of(html), "the measured line itself went missing")
        self.assertNotIn('class="next-cockpit-work-flag"', html)
        # One entry reads as one.
        one = self.render(WINDOWED[2:3], WINDOW)
        self.assertIn("1 entry", meta_of(one))
        self.assertNotIn("1 entries", meta_of(one))

    def test_the_list_follows_current_activity_under_session_activity(self) -> None:
        html = self.render(WINDOWED, WINDOW)
        column = html[html.index("data-next-session-activity") :]
        order = [
            column.index(mark)
            for mark in (
                ">Session activity</h2>",
                "CURRENT ACTIVITY",
                "data-next-cockpit-work",
                'class="next-session-facts"',
                "HOW IT LANDED",
            )
        ]
        self.assertEqual(sorted(order), order)
        self.assertNotIn("data-next-cockpit-work", aside_of(html))
        for never in OVERRULED:
            with self.subTest(never=never):
                self.assertNotIn(never, visible_text(html))

    def test_no_sentence_in_the_list_points_across_the_columns(self) -> None:
        rows = [*WINDOWED, ("later", 120, "user_message", "also clean the logs", {})]
        html = self.render(rows, WINDOW + departure(["old-2"]), harness="codex")
        record = record_of(html)
        text = visible_text(record)
        for word in ("panel", "beside", "left", "right", "Intent and drift"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)
        # "above" only in the record's own limit line, which follows every row it names.
        limit = re.search(r'class="next-cockpit-work-limit">([^<]*)<', record)
        assert limit is not None
        self.assertLess(record.rindex('<div class="next-cockpit-work-row"'), limit.start())
        outside = visible_text(record.replace(limit.group(0), ""))
        self.assertIsNone(re.search(r"\b(above|below)\b", outside), outside)

    def test_a_codex_session_numbers_and_never_says_turn(self) -> None:
        html = self.render(WINDOWED, WINDOW, harness="codex")
        self.assertEqual([1, 2, 3], [row["n"] for row in rows_of(html)])
        self.assertNotIn("turn", text_of(html).lower())

    def test_the_number_lookup_matches_the_rendered_numbers(self) -> None:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "const session = {harness:'claude', sid:'s1', annotation_window_start:60,"
            " annotation_at:100, annotation_revision:1};\n"
            "const fact = (fact_id, at) => ({fact_id, at, type:'task_result', summary:fact_id,"
            " source_session:{harness:'claude', sid:'s1'},"
            " evidence:{source:'transcript', confidence:'exact'}});\n"
            "const all = nextCockpitWorkEntries(session, {facts:[fact('z', 70), fact('b', 50),"
            " fact('a', 70), fact('m', 60)]});\n"
            "nextData.annotate = true;\n"
            "const numbers = nextCockpitEntryNumbers(session, {state:'read', entries:all, all});\n"
            "console.log(JSON.stringify(Object.fromEntries(numbers)));",
            storage_prelude({}) + FIXTURE,
        )
        self.assertEqual({"m": 1, "a": 2, "z": 3}, out)


if __name__ == "__main__":
    unittest.main()
