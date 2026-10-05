"""A verified line request refuses earlier actions, including delayed check results."""

from __future__ import annotations

import json
import shutil
import unittest
from typing import Any

from cargento_runtime import reading

from . import test_next_analysis_result as result_page
from . import test_next_outcome_lines as checklist
from .visible_text import visible_text


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePageUsesVerifiedLineRequestAges(checklist._ChecklistPage):
    def resolve(  # noqa: PLR0913 - independent source, time and revision boundary mutations
        self,
        *,
        action: float = 100,
        result_at: float = 200,
        request: dict[str, Any] | None = None,
        source: bool = True,
        copied: bool = False,
        source_at: float = 150,
        historical: bool = False,
        duplicate: bool = False,
        line_source: str = "entry",
        source_id: str = "request",
    ) -> dict[str, Any]:
        bound = (
            request
            if request is not None
            else {
                "harness": "claude",
                "sid": "focus-1",
                "revision": 2,
                "lines": {"line_1": {"at": 150, "source_id": "request"}},
            }
        )
        rows: list[dict[str, Any]] = [
            {
                "id": "work",
                "type": "tool_report",
                "subject": "check",
                "result": "passed",
                "work": True,
                "at": action,
                "resultAt": result_at,
                "source": "Claude Bash call and paired result",
            }
        ]
        if source:
            parent = {"id": "request", "type": "user_message", "at": source_at, "copied": copied}
            rows.append(parent)
            if duplicate:
                rows.append(dict(parent))
        after = """
const session = {harness:"claude", sid:"focus-1"};
const annotation = {revision:2, line_1:"Run the tests", line_1_source:__lineSource,
  line_1_source_id:__sourceId};
const source = {all:__rows, entries:__rows, lineRequests:__bound};
const floors = nextCockpitLineRequests(session, annotation, source);
const raw = {revision_read:__historical ? 1 : 2, window_start:90, read_at:210, scope:"full",
  criteria:{goal:{result:"consistent with the evidence read", cites:["work"], clause:"G"},
    line_1:{result:"consistent with the evidence read", cites:["work"], clause:"Run the tests"}}};
const shape = nextCockpitReadingShape(raw, annotation, __rows, "", false,
  nextOutcomeLineSource, floors);
console.log(JSON.stringify({floors, rows:shape.criteria.map(row=>[row.key,row.result,row.citedIds.length])}));
"""
        value = self.page(
            f"const __rows={json.dumps(rows)}, __bound={json.dumps(bound)}, "
            f"__historical={json.dumps(historical)}, __lineSource={json.dumps(line_source)}, "
            f"__sourceId={json.dumps(source_id)};\n",
            after,
        )
        assert isinstance(value, dict)
        return value

    def test_a_delayed_result_does_not_move_the_action_after_the_request(self) -> None:
        value = self.resolve()
        self.assertEqual({"line_1": 150}, value["floors"])
        self.assertEqual(["line_1", reading.RESULT_UNVERIFIABLE, 0], value["rows"][1])
        self.assertEqual(reading.RESULT_CONSISTENT, value["rows"][0][1])

    def test_an_action_at_the_request_time_is_ambiguous(self) -> None:
        self.assertEqual(reading.RESULT_UNVERIFIABLE, self.resolve(action=150)["rows"][1][1])

    def test_an_action_after_the_request_can_answer_the_line(self) -> None:
        self.assertEqual(reading.RESULT_CONSISTENT, self.resolve(action=151)["rows"][1][1])

    def test_an_unavailable_or_copied_source_keeps_age_unknown(self) -> None:
        for changes in (
            {"source": False},
            {"copied": True},
            {"source_at": 149},
            {"duplicate": True},
        ):
            with self.subTest(changes=changes):
                value = self.resolve(**changes)
                self.assertEqual({}, value["floors"])
                self.assertEqual(reading.RESULT_CONSISTENT, value["rows"][1][1])

    def test_a_different_session_revision_or_source_cannot_supply_the_floor(self) -> None:
        for changes in (
            {"sid": "other"},
            {"harness": "codex"},
            {"revision": 1},
            {"lines": {"line_1": {"at": 150, "source_id": "other"}}},
        ):
            with self.subTest(changes=changes):
                bound = {
                    "harness": "claude",
                    "sid": "focus-1",
                    "revision": 2,
                    "lines": {"line_1": {"at": 150, "source_id": "request"}},
                    **changes,
                }
                self.assertEqual({}, self.resolve(request=bound)["floors"])

    def test_a_reading_of_an_older_revision_keeps_the_old_window(self) -> None:
        self.assertEqual(reading.RESULT_CONSISTENT, self.resolve(historical=True)["rows"][1][1])

    def test_typed_or_edited_lines_cannot_borrow_a_saved_source_age(self) -> None:
        variants: tuple[dict[str, Any], ...] = (
            {"line_source": "typed"},
            {"source_id": "edited"},
        )
        for changes in variants:
            with self.subTest(changes=changes):
                self.assertEqual({}, self.resolve(**changes)["floors"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheRenderedResultJoinsTheFocusedRequestAge(result_page._ResultPage):
    def rendered(self, *, bound: bool, failed: bool = False) -> str:
        fact = result_page._report(
            "before-line",
            103,
            "check",
            result="failed" if failed else "passed",
            result_at=105,
            summary="pytest tests/parser",
        )
        value = result_page.assessment(
            {
                "goal": result_page.criterion(reading.RESULT_UNVERIFIABLE),
                "line_1": result_page.criterion(reading.RESULT_CONSISTENT, "before-line"),
            }
        )
        extra = '__s.annotation_line_1_source="entry"; __s.annotation_line_1_source_id="fo-a";\n'
        rows = (
            [
                {
                    "harness": "claude",
                    "sid": "focus-1",
                    "revision": 2,
                    "lines": {"line_1": {"at": 104, "source_id": "fo-a"}},
                }
            ]
            if bound
            else []
        )
        extra += (
            f"const __requestRows={json.dumps(rows)};\n"
            """
const __requestUpstream=__fetchImpl;
__fetchImpl=async(url,init)=>{
  const got=await __requestUpstream(url,init);
  if(!String(url).startsWith("/api/project-context")) return got;
  const data=await got.json(), sources=data.sources || {}, work=sources.work || {};
  return {ok:true,status:200,json:async()=>({...data,sources:{...sources,
    work:{...work,line_requests:__requestRows}}})};
};
"""
        )
        html = self.page(value, facts=(fact,), extra=extra)
        assert isinstance(html, str)
        return html

    def test_the_real_result_refuses_a_pass_called_before_its_verified_request(self) -> None:
        unbound = result_page.rows_of(self.rendered(bound=False))
        bound = result_page.rows_of(self.rendered(bound=True))
        self.assertTrue(any("Consistent with" in row for row in unbound), unbound)
        self.assertTrue(any("Can't tell" in row for row in bound), bound)
        self.assertFalse(any("Consistent with" in row for row in bound), bound)

    def test_the_global_failed_check_answer_survives_the_line_floor(self) -> None:
        html = self.rendered(bound=True, failed=True)
        self.assertIn("A check failed", visible_text(html))
        self.assertIn("Steer back", visible_text(html))
