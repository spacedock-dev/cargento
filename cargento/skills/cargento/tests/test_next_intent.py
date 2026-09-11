"""The Intent log: DRC-4512's retention surface and DRC-4533's read surface.

One surface answering both, because they are one question. What makes it a
surface rather than a column somewhere is that its rows outlive the board: an
annotation is keyed on `(harness, sid)` and carries no project, so a departed
session's words cannot be filed under one.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import annotations as annotation_store
from cargento_runtime import history
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

from .next_harness import NextPageJsHarness, storage_prelude


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextIntentViewTest(NextPageJsHarness):
    FIXTURE = """
const __dashboard = {
  generated: 200, rate_window_sec: 600, window_hours: 24, annotate: true,
  summary: {working: 1, needs_input: 0},
  harnesses: [{key: "codex", label: "Codex"}],
  sessions: [{sid: "live-1", harness: "codex", project: "cargento",
    project_key: "cargento", state: "working", active: true,
    last_activity: 199, title: "Still here", subagents: []}]
};
__fetchImpl = async url => String(url) === "/api/annotations"
  ? {ok: true, json: async () => ({annotations: __annotations})}
  : {ok: true, json: async () => __dashboard};
__els.app = {innerHTML: ""};
"""

    def render(self, annotations: list[dict[str, Any]], *, annotate: bool = True) -> dict[str, Any]:
        out = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            f"const __rows = {json.dumps(annotations)};\n"
            """
__annotations = __rows;
navigateNext({view:"intent"});
await __settle();
await __settle();
await __settle();
const html = __els.app.innerHTML;
console.log(JSON.stringify({
  html,
  title: document.title,
  rows: (html.match(/class="next-intent-row"/g) || []).length,
  visible: html.replace(/<[^>]*>/g, " ").replace(/\\s+/g, " "),
}));
""",
            storage_prelude({})
            + "let __annotations = [];\n"
            + self.FIXTURE.replace("annotate: true", f"annotate: {str(annotate).lower()}"),
        )
        assert isinstance(out, dict)
        return out

    @staticmethod
    def _row(**over: Any) -> dict[str, Any]:
        row = {
            "harness": "codex",
            "sid": "live-1",
            "goal": "Ship the cockpit",
            "goal_why": "",
            "output": "",
            "output_why": "No expected output typed.",
            "revision": 1,
            "revision_count": 1,
            "at": 150,
            "binding_why": "",
            "settled_at": None,
            "settled_through": None,
            "settled_revision": None,
        }
        row.update(over)
        return row

    def test_the_view_is_reachable_and_names_itself(self) -> None:
        out = self.render([self._row()])

        self.assertEqual("Cargento — Intent log", out["title"])
        self.assertIn("Intent log", out["visible"])
        # Reachable from the primary nav on every view, which is what stops it
        # being a screen only a typed fragment finds.
        self.assertIn('href="#n=intent"', out["html"])
        self.assertIn(">Intent log</a>", out["html"])

    def test_a_session_still_on_the_board_links_into_its_held_to_tab(self) -> None:
        out = self.render([self._row()])

        self.assertEqual(1, out["rows"])
        self.assertIn("Ship the cockpit", out["visible"])
        self.assertIn("#n=project:cargento:codex%3Alive-1:held-to", out["html"])

    def test_a_departed_session_keeps_its_words_and_says_it_cannot_be_opened(self) -> None:
        out = self.render([self._row(sid="gone-9", goal="Prove the fixes landed")])

        # The whole reason this is a surface: the words outlive the row.
        self.assertIn("Prove the fixes landed", out["visible"])
        self.assertIn("Not on the board now, so there is nowhere to open", out["visible"])
        # And it offers no link that would land on the stale-filter surface.
        self.assertNotIn("gone-9:held-to", out["html"])

    def test_a_prefix_bound_row_says_so_here_too(self) -> None:
        """Found by walking the board, not by the suite.

        The Held to tab tells a reader that Claude's eight-character identity
        means another session sharing it would share these words. This list is
        where many sessions are on screen at once, which is where a shared
        prefix would actually bite, and it said nothing. Worse than nothing:
        `published`'s default is `BINDING_EXACT`, so an absent caveat is a
        claim of exact binding rather than an absence of information.
        """
        out = self.render(
            [
                self._row(sid="bbc131ca", binding_why=annotation_store.BINDING_BY_PREFIX),
                self._row(sid="a-full-length-identity", goal="Whole id", binding_why=""),
            ]
        )

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("Another session sharing it would share these words", visible)
        # Once, for the row it is true of. A caveat on every row would be the
        # same overclaim in the other direction.
        self.assertEqual(1, visible.count("Another session sharing it"))

    def test_the_bound_is_a_count_and_the_copy_does_not_deny_history_holds_them(self) -> None:
        out = self.render([self._row()])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertIn("keeps the newest 256 and sixteen revisions each", visible)
        self.assertIn("dropping the oldest save first", visible)
        # History DOES keep a fourteen-day copy of these two fields, so the
        # surface may not say it is the only place they live. What it says is
        # narrower and true: leaving this list is an eviction, not an expiry.
        self.assertIn("eviction and not an expiry", visible)
        self.assertNotIn("is not what holds these words", visible)

    def test_the_reading_column_states_its_absence_once_for_the_block(self) -> None:
        out = self.render([self._row(), self._row(sid="gone-9")])

        visible = out["visible"]
        assert isinstance(visible, str)
        self.assertEqual(1, visible.count("No reading has been made against any of these"))
        # The one clause both this surface and the reading block owe, from one
        # constant rather than two wordings.
        self.assertIn("never a verification that the work was done", visible)

    def test_nothing_typed_anywhere_is_not_the_same_as_the_store_being_off(self) -> None:
        empty = self.render([])

        self.assertIn("Nothing has been typed against any session yet", empty["visible"])
        self.assertEqual(0, empty["rows"])

        # The half this test was named for and did not check. Measured while
        # closing DRC-4533: the fixture hardcoded `annotate: true`, so deleting
        # the off branch entirely left the suite green and told a
        # `--no-annotations` reader that nothing had been typed -- which is the
        # one thing this surface must never say when it cannot know.
        off = self.render([], annotate=False)

        self.assertIn("Annotations are off for this run", off["visible"])
        self.assertIn("--no-annotations", off["visible"])
        self.assertNotIn("Nothing has been typed against any session yet", off["visible"])
        self.assertEqual(0, off["rows"])


class TheIntentLogReadsTheStoreAndNotHistoryTest(unittest.TestCase):
    """Why the rows come from the annotation store alone.

    Not a preference. `annotations.clear` removes the entry, because clearing
    the field is withdrawing the request, while `annotation_goal` and
    `annotation_output` are in history's `OBSERVATION_FIELDS` and an
    observation already appended is never retro-deleted. A log backfilled from
    history would therefore republish, on a permanent surface, words the reader
    took back.
    """

    def test_history_admits_the_two_fields_the_log_must_not_read_back(self) -> None:
        # Both halves of the hazard, asserted rather than assumed: history
        # holds them, and holds them as prompt text.
        for field in ("annotation_goal", "annotation_output"):
            with self.subTest(field=field):
                self.assertIn(field, history.OBSERVATION_FIELDS)
                self.assertIn(field, history.PROMPT_TEXT_ALLOWLIST)

    def test_clearing_removes_the_entry_from_the_store_the_log_reads(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            config = build_runtime_config(
                environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
                platform_name="linux",
                os_name="posix",
                launcher_path=root / "server.py",
            )
            state = build_runtime_state(config, started=1_800_000_000.0)
            annotation_store.annotate(
                config, state, "pi", "s1", goal="withdraw me", now=1_800_000_000.0
            )
            self.assertIsNotNone(
                annotation_store.find(annotation_store.active(config, state), "pi", "s1")
            )

            annotation_store.clear(config, state, "pi", "s1")

            # Gone from the store, so gone from the log. That is the property
            # a history-backed log would not have.
            self.assertIsNone(
                annotation_store.find(annotation_store.active(config, state), "pi", "s1")
            )


if __name__ == "__main__":
    unittest.main()
