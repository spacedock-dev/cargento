"""A busy project neighbour cannot evict the selected session's work."""

from __future__ import annotations

from cargento_runtime import project_context

from .test_claude_checks import SHORT, Transcript
from .test_copied_corrections import NOW, _row, _Store


class FocusedEvidenceCapTest(_Store):
    def test_a_busy_sibling_does_not_push_the_selected_sessions_check_off_its_page(self) -> None:
        sibling_sid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        sibling = Transcript(self.root / "work" / "billing")
        sibling.prompt("Work on the sibling task")
        sibling.bash("pytest", "5 passed")
        for index in range(120):
            sibling.prompt(f"Continue sibling task {index}")
        for record in sibling.rows:
            record["sessionId"] = sibling_sid
        sibling.save(self.path.with_name(f"{sibling_sid}.jsonl"))
        rows = [_row(), _row(sid=sibling_sid, last_activity=NOW + 1)]

        project = project_context.collect(
            self.config, self.state, rows, "billing", now=NOW, focus=None
        )
        focused = project_context.collect(
            self.config, self.state, rows, "billing", now=NOW, focus=("claude", SHORT)
        )

        self.assertEqual(project_context.MAX_PROJECT_EVENTS, len(project["events"]))
        self.assertFalse(
            any(fact.get("subject") == "check" for fact in project["semantic"]["facts"])
        )
        self.assertLessEqual(len(focused["events"]), project_context.MAX_PROJECT_EVENTS)
        self.assertTrue(
            any(
                fact.get("subject") == "check"
                and fact.get("source_session") == {"harness": "claude", "sid": SHORT}
                for fact in focused["semantic"]["facts"]
            )
        )
