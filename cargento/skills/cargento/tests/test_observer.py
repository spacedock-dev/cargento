"""Observer analyzer and panel tests.

Five tests covering the acceptance criteria:
1. No-goal session yields "no goal derived" sentinel (AC2).
2. Positive case derives goal + stage + block (AC1).
3. Read-only invariant: the observer never mutates the target tree (AC3).
4. Model failure degrades to the deterministic fallback.
5. Observer panel renders the user-facing output from the sidecar (AC4).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from cargento_runtime import observer

from .page_harness import PageJsHarness
from .support import make_config, make_runtime


def _pi_message(
    msg_id: str,
    parent: str | None,
    role: str,
    content: str,
    *,
    ts: str = "2026-08-17T02:00:00Z",
) -> str:
    """One Pi-style JSONL message record."""
    return json.dumps(
        {
            "type": "message",
            "id": msg_id,
            "parentId": parent,
            "timestamp": ts,
            "message": {"role": role, "content": content},
        }
    )


def _pi_session(sid: str, cwd: str = "/home/test/project") -> str:
    return json.dumps({"type": "session", "id": sid, "cwd": cwd})


def _write_entity(entity_dir: Path, slug: str, status: str) -> Path:
    """Write one entity file with ``status:`` frontmatter."""
    entity_dir.mkdir(parents=True, exist_ok=True)
    path = entity_dir / f"{slug}.md"
    path.write_text(f"---\nstatus: {status}\ntitle: {slug}\n---\nbody\n", encoding="utf-8")
    return path


class ObserverAnalyzerTest(unittest.TestCase):
    """The observer analyzer: goal + stage + block from a transcript, read-only."""

    def setUp(self) -> None:
        self.config = make_config()
        self.config, self.state = make_runtime()

    def _write_transcript(self, tmp: str, lines: list[str]) -> str:
        path = Path(tmp) / "session.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    def test_no_goal_session_yields_sentinel_not_hallucination(self) -> None:
        """AC2: a session with only a generic opener and no assistant output
        returns 'no goal derived' without calling the model."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_transcript(
                tmp,
                [
                    _pi_session("neg-001"),
                    _pi_message(
                        "m1",
                        None,
                        "user",
                        "Use $spacedock:first-officer for this whole Pi session.",
                    ),
                ],
            )

            # A model that fabricates a goal: the short-circuit must bypass it.
            def fabricating_model(_head: str, _ctx: str) -> str:
                return "fabricated goal that must not appear"

            result = observer.analyze(self.config, self.state, path, model=fabricating_model)

        self.assertEqual("no goal derived", result["goal"])
        self.assertEqual("generic-opener-only-no-work", result["reason"])
        # The model was not called: the short-circuit bypassed it entirely.

    def test_positive_case_derives_goal_stage_and_block(self) -> None:
        """AC1: a known FO session produces a goal referencing the recent
        concrete directive and the entity dir's stage."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_transcript(
                tmp,
                [
                    _pi_session("pos-001"),
                    _pi_message(
                        "m1",
                        None,
                        "user",
                        "Use $spacedock:first-officer for this whole Pi session.",
                    ),
                    _pi_message(
                        "m2",
                        "m1",
                        "assistant",
                        "I'll start by running spacedock status --boot.",
                    ),
                    _pi_message(
                        "m3",
                        "m2",
                        "user",
                        "report the remaining pi related test and ergonomics issues",
                        ts="2026-08-17T02:05:00Z",
                    ),
                    _pi_message(
                        "m4",
                        "m3",
                        "assistant",
                        "I am blocked on a missing dependency in the test suite.",
                        ts="2026-08-17T02:06:00Z",
                    ),
                ],
            )
            entity_dir = Path(tmp) / "state"
            _write_entity(entity_dir, "observer-agent-pattern", "implementation")

            result = observer.analyze(self.config, self.state, path, entity_dir=str(entity_dir))

        # The goal tracks the most recent concrete user directive, not the
        # generic opener. Falsified by editing the directive to a different
        # objective and observing the goal not track it.
        self.assertIn("report the remaining pi related test", result["goal"])
        # The stage comes from the entity dir's frontmatter ``status``.
        self.assertEqual("implementation", result["stage"])
        # The block comes from recent assistant text containing a block indicator.
        self.assertIn("blocked", result["block"])

    def test_read_only_invariant(self) -> None:
        """AC3: the observer never mutates the observed session's repo/state.
        The sidecar is written to the observer's own store, not the target tree."""
        with (
            tempfile.TemporaryDirectory() as target_tmp,
            tempfile.TemporaryDirectory() as store_tmp,
        ):
            observer_store = Path(store_tmp) / "observer-store"
            observer_store.mkdir()
            config = make_config(state_dir=observer_store, state_home=str(observer_store))
            transcript = self._write_transcript(
                target_tmp,
                [
                    _pi_session("ro-001"),
                    _pi_message("m1", None, "user", "Fix the failing build"),
                    _pi_message("m2", "m1", "assistant", "Running the tests now."),
                ],
            )
            entity_dir = Path(target_tmp) / "state"
            entity_file = _write_entity(entity_dir, "task-one", "backlog")

            # Record mtimes before the run.
            transcript_mtime = os.path.getmtime(transcript)
            entity_mtime = os.path.getmtime(str(entity_file))

            # Make the target tree read-only (chmod -w the directory and files).
            os.chmod(transcript, 0o444)
            os.chmod(str(entity_file), 0o444)
            os.chmod(target_tmp, 0o555)  # noqa: S103
            os.chmod(str(entity_dir), 0o555)  # noqa: S103
            try:
                result = observer.analyze(
                    config, self.state, transcript, entity_dir=str(entity_dir)
                )
                sidecar = observer.write_sidecar(config, "pi", "ro-001", result)
            finally:
                # Restore permissions so cleanup can delete.
                os.chmod(target_tmp, 0o755)  # noqa: S103
                os.chmod(str(entity_dir), 0o755)  # noqa: S103
                os.chmod(transcript, 0o644)
                os.chmod(str(entity_file), 0o644)

            # The run produced a sidecar and a goal.
            self.assertIn("Fix the failing build", result["goal"])
            self.assertTrue(os.path.isfile(sidecar))
            # The sidecar is outside the target tree.
            self.assertFalse(sidecar.startswith(target_tmp))
            # No file under the target tree was modified.
            self.assertEqual(transcript_mtime, os.path.getmtime(transcript))
            self.assertEqual(entity_mtime, os.path.getmtime(str(entity_file)))

    def test_model_failure_degrades_to_deterministic_fallback(self) -> None:
        """A model error degrades to the deterministic fallback, never crashes
        or hallucinates."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_transcript(
                tmp,
                [
                    _pi_session("model-fail-001"),
                    _pi_message("m1", None, "user", "Review the PR"),
                    _pi_message("m2", "m1", "assistant", "Starting the review."),
                ],
            )

            def crashing_model(_head: str, _ctx: str) -> str:
                raise RuntimeError("model unavailable")

            result = observer.analyze(self.config, self.state, path, model=crashing_model)

        # The deterministic goal survives the model crash.
        self.assertIn("Review the PR", result["goal"])
        self.assertIsNone(result["reason"])

    def test_no_goal_sentinel_not_overridden_by_model(self) -> None:
        """The deterministic short-circuit bypasses the model entirely: a
        model that would fabricate a goal must not override the sentinel."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_transcript(
                tmp,
                [
                    _pi_session("neg-002"),
                    _pi_message("m1", None, "user", "skill(spacedock:first-officer)"),
                ],
            )

            def fabricator(_head: str, _ctx: str) -> str:
                return "inferred goal from the opener"

            result = observer.analyze(self.config, self.state, path, model=fabricator)

        self.assertEqual("no goal derived", result["goal"])


class ObserverPanelTest(PageJsHarness):
    """AC4: the observer panel renders the operator-visible output from the
    sidecar."""

    def test_panel_renders_goal_stage_and_block(self) -> None:
        """The panel renders the goal text, the stage badge, and the block text
        from a fixture sidecar."""
        rendered = self._run_page_js(
            "const html = renderObserverPanel({"
            "goal: 'managing the dev workflow', stage: 'implementation', "
            "block: 'blocked on a missing dependency'});"
            "console.log(JSON.stringify(html));"
        )
        self.assertIn("managing the dev workflow", rendered)
        self.assertIn("implementation", rendered)
        self.assertIn("blocked on a missing dependency", rendered)

    def test_panel_renders_no_goal_sentinel_not_fabricated_goal(self) -> None:
        """A no-goal sidecar renders the sentinel text, not a fabricated goal."""
        rendered = self._run_page_js(
            "const html = renderObserverPanel({"
            "goal: 'no goal derived', stage: '', block: ''});"
            "console.log(JSON.stringify(html));"
        )
        self.assertIn("no goal derived", rendered)
        # The sentinel has its own class, distinct from a real goal.
        self.assertIn("observer-sentinel", rendered)

    def test_panel_updates_when_sidecar_changes(self) -> None:
        """Falsification: editing the sidecar's goal changes the rendered output."""
        rendered_a = self._run_page_js(
            "console.log(JSON.stringify(renderObserverPanel({"
            "goal: 'first goal', stage: 'backlog', block: ''})));"
        )
        rendered_b = self._run_page_js(
            "console.log(JSON.stringify(renderObserverPanel({"
            "goal: 'second goal', stage: 'backlog', block: ''})));"
        )
        self.assertIn("first goal", rendered_a)
        self.assertIn("second goal", rendered_b)
        self.assertNotIn("second goal", rendered_a)

    def test_panel_no_hardcoded_fallback_goal(self) -> None:
        """A no-goal sidecar must not produce a hardcoded fallback goal."""
        rendered = self._run_page_js(
            "const html = renderObserverPanel({"
            "goal: 'no goal derived', stage: '', block: ''});"
            "console.log(JSON.stringify(html));"
        )
        # The only goal text is the sentinel; no fallback string appears.
        self.assertNotIn("unknown session", rendered)
        self.assertNotIn("session in progress", rendered)
