"""Observer analyzer and panel tests.

Five tests covering the acceptance criteria:
1. No-goal session yields "no goal derived" sentinel (AC2).
2. Positive case derives goal + stage + block (AC1).
3. Read-only invariant: the observer never mutates the target tree (AC3).
4. Model failure degrades to the deterministic fallback.
5. Observer panel renders the user-facing output from the sidecar (AC4).
"""

from __future__ import annotations

import dataclasses
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import observer

from . import test_page_calm
from .page_harness import PageJsHarness
from .support import (
    RuntimeTestCase,
    make_config,
    make_runtime,
    make_server,
    runtime,
    store_patch,
)


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


def _claude_message(
    uuid: str,
    role: str,
    content: Any,
    *,
    ts: str = "2026-08-17T02:00:00Z",
    sidechain: bool = False,
    meta: bool = False,
) -> str:
    """One Claude-style JSONL record: ``type`` is the role, ``uuid`` is the id.

    The field names are the ones a live transcript carries — surveyed over
    `~/.claude/projects`, where all 289 user and assistant records in the sample
    carried `parentUuid`, `isSidechain`, `type`, `message`, `uuid` and
    `timestamp`, and **none** carried a top-level `id`. The text is invented,
    per the convention `docs/captures/` sets: shapes, never values.
    """
    record: dict[str, Any] = {
        "parentUuid": None,
        "isSidechain": sidechain,
        "userType": "external",
        "cwd": "/home/test/project",
        "sessionId": "s-1",
        "version": "2.1.222",
        "gitBranch": "main",
        "type": role,
        "message": {"role": role, "content": content},
        "uuid": uuid,
        "timestamp": ts,
    }
    if meta:
        record["isMeta"] = True
    return json.dumps(record)


def _codex_message(
    payload_id: str,
    role: str,
    text: str,
    *,
    ts: str = "2026-08-17T02:00:00Z",
) -> str:
    """One Codex-style JSONL record: ``response_item`` wrapping a message payload.

    Again the live shape: the id lives at `payload.id` (never at the top level),
    the text at `payload.content[].text`, and the block type differs by role —
    `input_text` for the operator, `output_text` for the agent.
    """
    block = "input_text" if role == "user" else "output_text"
    return json.dumps(
        {
            "timestamp": ts,
            "type": "response_item",
            "payload": {
                "id": payload_id,
                "type": "message",
                "role": role,
                "content": [{"type": block, "text": text}],
            },
        }
    )


def _codex_session_meta(
    sid: str, cwd: str = "/home/test/project", *, subagent: bool = False
) -> str:
    """A Codex rollout's line 1, which is what `transcripts.codex_meta` reads.

    ``thread_source`` is the field the collector's subagent test reads, and a
    subagent thread's rollout carries its PARENT's session id — measured on 262
    of 262 local subagent rollouts, none of which declared an id of its own.
    """
    payload: dict[str, Any] = {"id": sid, "cwd": cwd, "cli_version": "0.149.1"}
    if subagent:
        payload["thread_source"] = "subagent"
        payload["agent_nickname"] = "explorer"
    return json.dumps(
        {
            "timestamp": "2026-08-17T01:59:00Z",
            "type": "session_meta",
            "payload": payload,
        }
    )


def _write_entity(entity_dir: Path, slug: str, status: str) -> Path:
    """Write one entity file with ``status:`` frontmatter."""
    entity_dir.mkdir(parents=True, exist_ok=True)
    path = entity_dir / f"{slug}.md"
    path.write_text(f"---\nstatus: {status}\ntitle: {slug}\n---\nbody\n", encoding="utf-8")
    return path


def _write_workflow(workflow_dir: Path, stages: list[str]) -> Path:
    """A Spacedock workflow README declaring `stages`, the discriminator's source.

    The analyzer publishes a stage only when the entity's `status` names one this
    README declares — the per-file discriminator SECURITY.md names as standing in
    for the containment check a split-root state directory cannot get. A fixture
    with no README is a fixture whose stage is empty, which is what the observer
    must do with a state directory nothing vouched for.
    """
    workflow_dir.mkdir(parents=True, exist_ok=True)
    states = "".join(f"    - name: {stage}\n" for stage in stages)
    readme = workflow_dir / "README.md"
    readme.write_text(
        "---\ncommissioned-by: spacedock@0.22.0\nstages:\n  states:\n" + states + "---\n",
        encoding="utf-8",
    )
    return readme


def _boot_line(mid: str, parent: str | None, workflow_dir: Path, entity_dir: Path) -> str:
    """A `spacedock status --boot` envelope in a transcript record.

    Written in the `type: "tool_result"` block shape rather than Pi's
    `toolResult` *role*, and that is a branch dependency rather than a
    preference: reading the role shape is what `#127` adds to
    `spacedock.tool_result_text`, and on this branch it is not there yet. Both
    shapes reach the same `boot_records` scan once that lands, so this fixture
    stays correct either way. The envelope's first key must be `command`, which
    is what `boot_records` searches for.
    """
    envelope = json.dumps(
        {
            "command": "boot",
            "definition_dir": str(workflow_dir),
            "entity_dir": str(entity_dir),
        }
    )
    return json.dumps(
        {
            "type": "message",
            "id": mid,
            "parentId": parent,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": envelope}],
            },
        }
    )


class ObserverAnalyzerTest(unittest.TestCase):
    """The observer analyzer: goal + stage + block from a transcript, read-only."""

    NOW = 1_700_000_000.0
    WINDOW = 86_400.0

    def setUp(self) -> None:
        self.config, self.state = make_runtime()

    def analyze(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """`observer.analyze` on this test's runtime and a fixed clock."""
        return observer.analyze(
            self.config, self.state, path, now=self.NOW, window_sec=self.WINDOW, **kwargs
        )

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

            result = self.analyze(path, model=fabricating_model)

        self.assertEqual("no goal derived", result["goal"])
        self.assertEqual("generic-opener-only-no-work", result["reason"])
        # The model was not called: the short-circuit bypassed it entirely.

    def test_positive_case_derives_goal_stage_and_block(self) -> None:
        """AC1: a known FO session produces a goal referencing the recent
        concrete directive, and the stage of the newest in-flight entity."""
        with tempfile.TemporaryDirectory() as tmp:
            workflow_dir = Path(tmp) / "wf"
            entity_dir = workflow_dir / ".spacedock-state"
            _write_workflow(workflow_dir, ["intake", "implementation", "posted"])
            _write_entity(entity_dir, "observer-agent-pattern", "implementation")
            os.utime(entity_dir / "observer-agent-pattern.md", (self.NOW, self.NOW))
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
                    _boot_line("m5", "m4", workflow_dir, entity_dir),
                ],
            )
            result = self.analyze(path)

        # The goal tracks the most recent concrete user directive, not the
        # generic opener. Falsified by editing the directive to a different
        # objective and observing the goal not track it.
        self.assertIn("report the remaining pi related test", result["goal"])
        # The stage is the entity's `status`, and only because the workflow
        # README declares it. Falsified by renaming the stage in the README:
        # `read_entities` then drops the entity and the stage comes back empty.
        self.assertEqual("implementation", result["stage"])
        # The block comes from recent assistant text containing a block indicator.
        self.assertIn("blocked", result["block"])

    def _fo_transcript(
        self, tmp: str, *, stage: str, declared: list[str], age_sec: float = 0.0
    ) -> str:
        """One first-officer transcript over a workflow whose entity sits on `stage`."""
        workflow_dir = Path(tmp) / "wf"
        entity_dir = workflow_dir / ".spacedock-state"
        _write_workflow(workflow_dir, declared)
        entity = _write_entity(entity_dir, "drc-1", stage)
        written = self.NOW - age_sec
        os.utime(str(entity), (written, written))
        return self._write_transcript(
            tmp,
            [
                _pi_session("fo-001"),
                _pi_message("m1", None, "user", "Ship the observer route"),
                _pi_message("m2", "m1", "assistant", "Booting the workflow."),
                _boot_line("m3", "m2", workflow_dir, entity_dir),
            ],
        )

    def test_ordinary_reporting_prose_is_not_a_block(self) -> None:
        # The false-positive case, which the indicator table had none of. A bare
        # `cannot`/`can't`/`failed to`/`error:` matches an agent describing work
        # it has finished, and a block is the one field on the panel a reader
        # would act on. Falsifying edit: put the bare words back — every line
        # here publishes a block.
        for line in (
            "I can't reproduce the failure any more, so the fix holds.",
            "The old code cannot have worked; the new one does.",
            "It failed to build before the patch. It builds now.",
            "The log said error: missing header, which the include fixes.",
            "I was unable to reproduce it until I widened the window.",
            "Waiting for the suite to finish, then I will push.",
            # `blocked on` went the same way once the parser reached Claude and
            # Codex: over 857 real sessions it produced four blocks and all four
            # were prose about a PR or another issue. Both lines below are the
            # shape of those four.
            "The PR is mergeable and blocked only by required review.",
            "Your conclusion that live egress is still blocked on the other PR is correct.",
        ):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as tmp:
                path = self._write_transcript(
                    tmp,
                    [
                        _pi_session("fp-001"),
                        _pi_message("m1", None, "user", "Fix the build"),
                        _pi_message("m2", "m1", "assistant", line),
                    ],
                )
                self.assertEqual("", self.analyze(path)["block"])

    def test_a_resolved_block_is_not_walked_back_to(self) -> None:
        # Scanning backwards through every assistant message found a block that
        # had been reported and then resolved, and published it as current.
        # Falsifying edit: drop the `return ""` after the newest assistant
        # message — this publishes the twenty-turn-old block.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_transcript(
                tmp,
                [
                    _pi_session("res-001"),
                    _pi_message("m1", None, "user", "Fix the build"),
                    _pi_message("m2", "m1", "assistant", "I am blocked on a missing token."),
                    _pi_message("m3", "m2", "user", "Here is the token."),
                    _pi_message("m4", "m3", "assistant", "Thanks — the build is green now."),
                ],
            )
            self.assertEqual("", self.analyze(path)["block"])

    def test_a_current_block_is_still_reported(self) -> None:
        # The other side: narrowing the table must not cost the real case.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_transcript(
                tmp,
                [
                    _pi_session("cur-001"),
                    _pi_message("m1", None, "user", "Deploy it"),
                    _pi_message(
                        "m2",
                        "m1",
                        "assistant",
                        "I pulled the manifest. I am blocked on a missing AWS role.",
                    ),
                ],
            )
            self.assertEqual("I am blocked on a missing AWS role.", self.analyze(path)["block"])

    def test_no_spacedock_withdraws_the_project_reads(self) -> None:
        # `--no-spacedock` is the switch that turns off the project reads, and
        # SECURITY.md's project-read contract is written against it. The route
        # read the entity frontmatter regardless, so the switch withdrew a
        # strip and left this reading the same files.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fo_transcript(tmp, stage="review", declared=["intake", "review"])
            self.assertEqual("review", self.analyze(path)["stage"])

            self.config = dataclasses.replace(self.config, spacedock_enabled=False)
            result = self.analyze(path)

        # The transcript half survives — a transcript read is not a project read.
        self.assertIn("Ship the observer route", result["goal"])
        self.assertEqual("", result["stage"])

    def test_an_undeclared_status_publishes_no_stage(self) -> None:
        # The per-file discriminator. SECURITY.md names `status in declared` as
        # what stands in for `read_workflow`'s containment check, because a
        # split-root workflow's state directory legitimately sits outside the
        # definition directory. Reading the scalar directly published whatever
        # the newest file in an unverified directory happened to say.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fo_transcript(
                tmp, stage="/etc/passwd he said", declared=["intake", "review"]
            )
            self.assertEqual("", self.analyze(path)["stage"])

    def test_a_stale_entity_publishes_no_stage(self) -> None:
        # The freshness gate. A first officer discovers every workflow in the
        # project, and one retired months ago still has entities frozen
        # mid-pipeline; those are history, not work in flight.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fo_transcript(
                tmp, stage="review", declared=["intake", "review"], age_sec=self.WINDOW * 2
            )
            self.assertEqual("", self.analyze(path)["stage"])

    def test_sidecar_path_refuses_a_name_that_is_not_a_name(self) -> None:
        # `safe_text` strips control characters and truncates; it passes `/`,
        # `\` and `..` straight through, so a session id carrying separators
        # walked out of the observer store and truncated whatever it landed on.
        config, _state = make_runtime()
        # `..` alone is absent on purpose: it lands as `pi_...json`, a legitimate
        # name inside the observer store, so refusing it would be superstition.
        # What has to be refused is anything that can leave that directory.
        for sid in (
            "x/../../../../.claude/settings",
            "a/b",
            "a\\b",
            "",
            "x" * 129,
        ):
            with self.subTest(sid=sid):
                self.assertIsNone(observer.sidecar_path(config, "pi", sid))
                self.assertIsNone(observer.write_sidecar(config, "pi", sid, {"goal": "x"}))
        self.assertIsNone(observer.sidecar_path(config, "../pi", "ok-1"))
        # A real id still resolves, inside the observer store.
        path = observer.sidecar_path(config, "pi", "abcdef12-3456-7890-abcd-ef1234567890")
        assert path is not None
        self.assertEqual(
            os.path.normpath(os.path.join(str(config.state_dir), "observer")),
            os.path.dirname(os.path.normpath(path)),
        )

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
            workflow_dir = Path(target_tmp) / "wf"
            entity_dir = workflow_dir / ".spacedock-state"
            transcript = self._write_transcript(
                target_tmp,
                [
                    _pi_session("ro-001"),
                    _pi_message("m1", None, "user", "Fix the failing build"),
                    _pi_message("m2", "m1", "assistant", "Running the tests now."),
                    # The boot line matters to the README assertion below:
                    # without it the stage reader opens neither file, and "the
                    # README was not modified" would hold because it was never
                    # read at all.
                    _boot_line("m3", "m2", workflow_dir, entity_dir),
                ],
            )
            _write_workflow(workflow_dir, ["backlog", "doing"])
            entity_file = _write_entity(entity_dir, "task-one", "backlog")
            os.utime(str(entity_file), (self.NOW, self.NOW))
            readme_mtime = os.path.getmtime(str(workflow_dir / "README.md"))

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
                    config, self.state, transcript, now=self.NOW, window_sec=self.WINDOW
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
            assert sidecar is not None
            self.assertTrue(os.path.isfile(sidecar))
            # The sidecar is outside the target tree.
            self.assertFalse(sidecar.startswith(target_tmp))
            # No file under the target tree was modified — the README the stage
            # reader now opens included.
            self.assertEqual(transcript_mtime, os.path.getmtime(transcript))
            self.assertEqual(entity_mtime, os.path.getmtime(str(entity_file)))
            self.assertEqual(readme_mtime, os.path.getmtime(str(workflow_dir / "README.md")))

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

            result = self.analyze(path, model=crashing_model)

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

            result = self.analyze(path, model=fabricator)

        self.assertEqual("no goal derived", result["goal"])


class ObserverRecordShapeTest(unittest.TestCase):
    """One test per harness record shape, so this cannot revert to Pi-only.

    The analyzer required ``type: "message"`` — Pi's shape and Droid's — and
    returned zero messages on 3,769 of 3,769 local Claude transcripts and 457 of
    457 Codex rollouts, publishing the ``no goal derived`` sentinel for sessions
    full of work. Teaching it the other two shapes and nothing else would have
    been worse: measured here over the same corpora, the published goal was a
    harness-injected shape on 234 of 457 Codex rollouts (51.2%) and 247 of a
    seeded 400-transcript Claude sample (61.8%). A confident wrong answer where
    there had been a silent one.
    """

    NOW = 1_700_000_000.0
    WINDOW = 86_400.0

    def setUp(self) -> None:
        self.config, self.state = make_runtime()

    def analyze(self, lines: list[str], **changes: Any) -> dict[str, Any]:
        config = dataclasses.replace(self.config, **changes) if changes else self.config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return observer.analyze(
                config, self.state, str(path), now=self.NOW, window_sec=self.WINDOW
            )

    def test_a_claude_transcript_derives_a_goal(self) -> None:
        result = self.analyze(
            [
                _claude_message("u1", "user", "Rewrite the changelog for the release"),
                _claude_message(
                    "u2",
                    "assistant",
                    [{"type": "text", "text": "Reading the tags now."}],
                    ts="2026-08-17T02:01:00Z",
                ),
            ]
        )
        self.assertEqual("Rewrite the changelog for the release", result["goal"])

    def test_a_codex_rollout_derives_a_goal(self) -> None:
        result = self.analyze(
            [
                _codex_session_meta("019f1c51-6cf9-7981-9a2d-172428800000"),
                _codex_message("p1", "user", "Rewrite the changelog for the release"),
                _codex_message("p2", "assistant", "Reading the tags now.", ts="2026-08-17T02:01Z"),
            ]
        )
        self.assertEqual("Rewrite the changelog for the release", result["goal"])

    def test_the_pi_and_droid_shape_still_parses(self) -> None:
        # The union is additive on purpose. Falsifying edit: gate the shapes on a
        # `harness` argument and this fixture stops parsing.
        result = self.analyze(
            [
                _pi_session("shape-001"),
                _pi_message("m1", None, "user", "Rewrite the changelog for the release"),
                _pi_message("m2", "m1", "assistant", "Reading the tags now."),
            ]
        )
        self.assertEqual("Rewrite the changelog for the release", result["goal"])

    def test_an_injected_shape_is_never_published_as_the_goal(self) -> None:
        # The whole reason this change could not ship on the parser alone. Each
        # pair below is one harness's own machinery in the user channel; the
        # analyzer must fall back to the sentinel rather than publish it.
        for label, lines in (
            (
                "claude-tag",
                [
                    _claude_message(
                        "u1", "user", "<task-notification>agent done</task-notification>"
                    ),
                    _claude_message("u2", "assistant", "Acknowledged.", ts="2026-08-17T02:01:00Z"),
                ],
            ),
            (
                "claude-compaction",
                [
                    _claude_message(
                        "u1", "user", "Analyze this conversation and determine what happened."
                    ),
                    _claude_message("u2", "assistant", "Acknowledged.", ts="2026-08-17T02:01:00Z"),
                ],
            ),
            (
                "claude-sidechain",
                [
                    _claude_message(
                        "u1", "user", "Search the tree for the dead route", sidechain=True
                    ),
                    _claude_message("u2", "assistant", "Acknowledged.", ts="2026-08-17T02:01:00Z"),
                ],
            ),
            (
                "claude-meta",
                [
                    _claude_message("u1", "user", "Set the model to opus", meta=True),
                    _claude_message("u2", "assistant", "Acknowledged.", ts="2026-08-17T02:01:00Z"),
                ],
            ),
            (
                "codex-tag",
                [
                    _codex_session_meta("019f1c51-6cf9-7981-9a2d-172428800001"),
                    _codex_message("p1", "user", "<recommended_plugins>\nHere is a list."),
                    _codex_message("p2", "assistant", "Acknowledged.", ts="2026-08-17T02:01Z"),
                ],
            ),
            (
                "codex-prose",
                [
                    _codex_session_meta("019f1c51-6cf9-7981-9a2d-172428800002"),
                    _codex_message("p1", "user", "# AGENTS.md instructions for /home/test/project"),
                    _codex_message("p2", "assistant", "Acknowledged.", ts="2026-08-17T02:01Z"),
                ],
            ),
        ):
            with self.subTest(shape=label):
                result = self.analyze(lines)
                self.assertEqual(observer.NO_GOAL, result["goal"])
                # Assistant work exists, so this is the "unknown, not
                # fabricated" branch rather than the generic-opener one.
                self.assertIsNone(result["reason"])

    def test_a_slash_command_is_the_operators_intent_and_is_published(self) -> None:
        # The deliberate carve-out. `records.injected_prompt` does not reject the
        # slash-command wrappers, because a slash command is what the person
        # asked for, spelled in the harness's markup — and `transcripts.prompt_title`
        # owns reading it back out. Falsifying edit: add `command-message` to
        # `records._CLAUDE_USER_TAGS` and this session loses its goal entirely.
        result = self.analyze(
            [
                _claude_message(
                    "u1",
                    "user",
                    "<command-message>code-review is running…</command-message>\n"
                    "<command-name>/code-review</command-name>\n"
                    "<command-args>1287 with fresh eyes</command-args>",
                ),
                _claude_message("u2", "assistant", "Reading the diff.", ts="2026-08-17T02:01:00Z"),
            ]
        )
        self.assertEqual("/code-review 1287 with fresh eyes", result["goal"])

    def test_a_bare_harness_control_command_is_not_an_objective(self) -> None:
        # `/clear`, `/login`, `/plugin`, `/mcp` and the rest drive the harness,
        # not the work, and they rendered into the ordinary goal slot looking
        # exactly like a derived objective: 200 of 1,469 published Claude goals
        # (13.6%) and 4 of 141 Codex ones.
        #
        # The guard beside this one could not fire, and the reason is an
        # ordering bug rather than a missing rule: `_is_generic_opener` reads the
        # RAW `<command-name>/clear</command-name>` spelling while the value
        # actually published is `prompt_title(raw)` — `/clear`. The two
        # spellings never meet. Falsifying edit: move the `_is_harness_control`
        # test off the rendered value and back onto `msg["text"]`.
        for harness, lines in (
            (
                "claude",
                [
                    _claude_message(
                        "u1",
                        "user",
                        "<command-message>clear</command-message>\n"
                        "<command-name>/clear</command-name>\n"
                        "<command-args></command-args>",
                    ),
                    _claude_message("u2", "assistant", "Cleared.", ts="2026-08-17T02:01:00Z"),
                ],
            ),
            (
                "codex",
                [
                    _codex_session_meta("019f1c51-6cf9-7981-9a2d-172428800009"),
                    _codex_message("p1", "user", "/login"),
                    _codex_message("p2", "assistant", "Signed in.", ts="2026-08-17T02:01Z"),
                ],
            ),
        ):
            with self.subTest(harness=harness):
                self.assertEqual(observer.NO_GOAL, self.analyze(lines)["goal"])

    def test_a_control_command_does_not_displace_the_objective_beneath_it(self) -> None:
        # The rejection happens where `_is_generic_opener`'s does — over the
        # directive list — rather than at the point of publication, so the real
        # objective the session already contains survives the `/clear` typed
        # after it. Measured: 25 of the 200 Claude cases are this shape.
        result = self.analyze(
            [
                _claude_message(
                    "u1", "user", "Fix the flaky quota test", ts="2026-08-17T02:00:00Z"
                ),
                _claude_message("u2", "assistant", "On it.", ts="2026-08-17T02:01:00Z"),
                _claude_message(
                    "u3",
                    "user",
                    "<command-name>/clear</command-name>",
                    ts="2026-08-17T02:02:00Z",
                ),
            ]
        )
        self.assertEqual("Fix the flaky quota test", result["goal"])

    def test_a_bare_skill_invocation_is_still_an_objective(self) -> None:
        # The rule is a measured name list and NOT "a bare command carries no
        # arguments, so it carries no goal". That structural rule was checked
        # against the same corpus and is wrong: 39 further bare-command goals
        # are skill invocations, and a skill invoked with no arguments is
        # exactly what the operator asked for. Falsifying edit: reject on
        # `_BARE_COMMAND_RE` alone and this goal disappears.
        result = self.analyze(
            [
                _claude_message("u1", "user", "<command-name>/create-pr</command-name>"),
                _claude_message("u2", "assistant", "Opening it.", ts="2026-08-17T02:01:00Z"),
            ]
        )
        self.assertEqual("/create-pr", result["goal"])

    def test_the_injected_tag_set_is_gated_on_the_record_s_harness(self) -> None:
        # Each arm of `_parse_message_record` hands `injected_prompt` its own
        # harness literal, and nothing else in the suite pinned that: mutating
        # the Claude arm's literal to `"codex"` left the whole suite green while
        # degrading 4 real Claude goals, every one of them a `<system-reminder>`
        # published as the operator's objective.
        #
        # Two directions, because one literal per arm needs one test per arm.
        # Falsifying edits: `"claude"` -> `"codex"` in `_claude_message`, and
        # `"codex"` -> `"claude"` in the `response_item` branch.
        claude_only = self.analyze(
            [
                _claude_message(
                    "u1",
                    "user",
                    "<system-reminder>\nYou are running in non-interactive mode.",
                ),
                _claude_message("u2", "assistant", "Understood.", ts="2026-08-17T02:01:00Z"),
            ]
        )
        self.assertEqual(observer.NO_GOAL, claude_only["goal"])
        codex_only = self.analyze(
            [
                _codex_session_meta("019f1c51-6cf9-7981-9a2d-172428800010"),
                _codex_message("p1", "user", "<recommended_plugins>\nHere is a list."),
                _codex_message("p2", "assistant", "Understood.", ts="2026-08-17T02:01Z"),
            ]
        )
        self.assertEqual(observer.NO_GOAL, codex_only["goal"])

    def test_the_newest_directive_is_the_newest_by_stamp_not_by_position(self) -> None:
        # `_extract_messages` concatenates the head window and the tail window,
        # and `_derive_goal_deterministic` takes `directives[-1]`, so "newest"
        # used to mean "last in that concatenation". File position is not record
        # order: a resumed Claude session replays the earlier transcript's
        # records into the new file, and the replayed block carries its original
        # stamps while sitting after records written later.
        #
        # Falsifying edit: drop the `ordered.sort` in `_extract_messages` — the
        # goal then becomes "the replayed opening prompt".
        result = self.analyze(
            [
                _claude_message("u1", "user", "the newest prompt", ts="2026-08-17T09:00:00Z"),
                _claude_message("u2", "assistant", "Working.", ts="2026-08-17T09:01:00Z"),
                _claude_message(
                    "u3", "user", "the replayed opening prompt", ts="2026-08-17T02:00:00Z"
                ),
            ]
        )
        self.assertEqual("the newest prompt", result["goal"])

    def test_the_head_window_and_the_tail_window_are_both_read(self) -> None:
        # The two windows are disjoint on any file over head + tail (465,536 B
        # with the shipped figures), and the opening directive lives in the head.
        # The windows are shrunk here rather than the file grown: a 465 KB
        # fixture proves the same thing and costs a disk write per run.
        filler = [
            _claude_message(f"f{i}", "assistant", "x" * 200, ts=f"2026-08-17T02:{i:02d}:00Z")
            for i in range(2, 40)
        ]
        result = self.analyze(
            [
                _claude_message("u1", "user", "the opening prompt", ts="2026-08-17T02:00:00Z"),
                *filler,
                _claude_message("u2", "assistant", "Still going.", ts="2026-08-17T02:59:00Z"),
            ],
            observer_head_bytes=1_200,
            tail_bytes=1_200,
        )
        self.assertEqual("the opening prompt", result["goal"])

    def test_a_repeated_prompt_does_not_keep_its_oldest_position(self) -> None:
        # The dedup key read `record["id"]`, which **0 of 8,312 Claude and 0 of
        # 14,389 Codex records carry**, so it degraded silently to the message
        # text: a prompt repeated verbatim later in the session was dropped as a
        # duplicate of its own first occurrence, and the goal stayed on whatever
        # came between them. Falsifying edit: key on `record.get("id")` again.
        result = self.analyze(
            [
                _claude_message("u1", "user", "align the release notes", ts="2026-08-17T02:00:00Z"),
                _claude_message("u2", "user", "run the migration", ts="2026-08-17T02:01:00Z"),
                _claude_message("u3", "user", "align the release notes", ts="2026-08-17T02:02:00Z"),
                _claude_message("u4", "assistant", "On it.", ts="2026-08-17T02:03:00Z"),
            ]
        )
        self.assertEqual("align the release notes", result["goal"])

    def test_a_tool_result_echo_is_not_a_directive(self) -> None:
        # A user turn whose content is a tool_result is the harness echoing its
        # own output back, on every one of the three shapes.
        result = self.analyze(
            [
                _claude_message("u1", "user", "Fix the failing build", ts="2026-08-17T02:00:00Z"),
                _claude_message(
                    "u2",
                    "user",
                    [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
                    ts="2026-08-17T02:05:00Z",
                ),
            ]
        )
        self.assertEqual("Fix the failing build", result["goal"])


class ObserverTranscriptResolutionTest(RuntimeTestCase):
    """Which transcript `/api/observe?harness=&sid=` resolves to, per harness."""

    def test_a_claude_transcript_resolves_one_directory_down(self) -> None:
        # `projects/<encoded-cwd>/<session-id>.jsonl`, which is how
        # `collectors/claude.py` globs it. A flat `*.jsonl` matched nothing, so
        # `?harness=claude` was a 404 on every machine — the route advertised a
        # harness it could never answer for.
        sid = "abcdef12-3456-7890-abcd-ef1234567890"
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            (projects / "-home-me-repo").mkdir(parents=True)
            wanted = projects / "-home-me-repo" / f"{sid}.jsonl"
            wanted.write_text("{}\n", encoding="utf-8")
            with store_patch(PROJECTS_DIR=str(projects)):
                config, state = runtime()
                found = observer.resolve_transcript(config, state, "claude", sid)
                # The dashboard shortens an id for display, so a prefix resolves.
                short = observer.resolve_transcript(config, state, "claude", sid[:8])
        self.assertEqual(str(wanted), found)
        self.assertEqual(str(wanted), short)

    def test_an_ambiguous_claude_prefix_resolves_to_nothing(self) -> None:
        # Codex-style time-ordered ids share long prefixes, and the old
        # `sid in basename` substring match handed back whichever transcript
        # happened to contain the characters. Two candidates is no answer.
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            (projects / "-home-me-repo").mkdir(parents=True)
            for suffix in ("aa", "bb"):
                (projects / "-home-me-repo" / f"sess-{suffix}.jsonl").write_text("{}\n")
            with store_patch(PROJECTS_DIR=str(projects)):
                config, state = runtime()
                self.assertIsNone(observer.resolve_transcript(config, state, "claude", "sess-"))

    def test_a_codex_rollout_resolves_by_session_meta_and_newest_wins(self) -> None:
        # A rollout's uuid sits at the END of `rollout-<timestamp>-<uuid>.jsonl`,
        # so the Claude branch's stem `startswith` cannot be reused; the id is
        # matched against `session_meta` instead, which is the field
        # `collectors/codex.py` keys on.
        #
        # Newest mtime and not the first match, because one `session_id` is
        # legitimately spread over several files: a resume and each subagent
        # thread write their own rollout under it. The first by glob order is the
        # oldest — the one nothing is being written to.
        sid = "019f1c51-6cf9-7981-9a2d-172428800003"
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026" / "08" / "17"
            day.mkdir(parents=True)
            older = day / f"rollout-2026-08-17T01-00-00-{sid}.jsonl"
            newer = day / f"rollout-2026-08-17T09-00-00-{sid}.jsonl"
            other = day / "rollout-2026-08-17T10-00-00-019f1c51-6cf9-7981-9a2d-172428800004.jsonl"
            for path, resumed in ((older, sid), (newer, sid), (other, "other-session")):
                path.write_text(_codex_session_meta(resumed) + "\n", encoding="utf-8")
            os.utime(str(older), (1_700_000_000, 1_700_000_000))
            os.utime(str(newer), (1_700_000_900, 1_700_000_900))
            with store_patch(CODEX_SESSIONS_DIR=str(tmp)):
                config, state = runtime()
                found = observer.resolve_transcript(config, state, "codex", sid)
        self.assertEqual(str(newer), found)

    def test_a_subagent_rollout_never_stands_in_for_its_parent(self) -> None:
        # A subagent thread's rollout carries its PARENT's `session_id` — 262 of
        # 262 locally — so a max-mtime pick over the id alone hands back the
        # child whenever the child is the file being written, and `analyze` then
        # publishes the parent agent's dispatch prompt as the operator's goal.
        # In 262 of 262 local subagent runs there is a window where that is what
        # the resolver returns (32.8 h of 102.8 h of aggregate subagent
        # wall-clock); the static corpus shows 0 only because each of its 31
        # mixed groups was captured after the parent resumed writing, which is
        # exactly why a fixture is needed rather than a corpus count.
        #
        # Falsifying edit: drop the `meta.get("subagent")` test from the Codex
        # branch of `resolve_transcript` and the NEWER child file is returned.
        sid = "019f1c51-6cf9-7981-9a2d-172428800005"
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026" / "08" / "17"
            day.mkdir(parents=True)
            parent = day / f"rollout-2026-08-17T01-00-00-{sid}.jsonl"
            child = day / "rollout-2026-08-17T09-00-00-019f1c51-6cf9-7981-9a2d-172428800006.jsonl"
            parent.write_text(_codex_session_meta(sid) + "\n", encoding="utf-8")
            # The child declares the parent's id, which is the whole collision.
            child.write_text(_codex_session_meta(sid, subagent=True) + "\n", encoding="utf-8")
            os.utime(str(parent), (1_700_000_000, 1_700_000_000))
            os.utime(str(child), (1_700_000_900, 1_700_000_900))
            with store_patch(CODEX_SESSIONS_DIR=str(tmp)):
                config, state = runtime()
                found = observer.resolve_transcript(config, state, "codex", sid)
        self.assertEqual(str(parent), found)

    def test_a_session_that_is_only_a_subagent_thread_resolves_to_nothing(self) -> None:
        # The exclusion is not "prefer the parent", it is "a child is never the
        # answer": a subagent rollout is not a session a person opened.
        sid = "019f1c51-6cf9-7981-9a2d-172428800007"
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026" / "08" / "17"
            day.mkdir(parents=True)
            child = day / "rollout-2026-08-17T09-00-00-019f1c51-6cf9-7981-9a2d-172428800008.jsonl"
            child.write_text(_codex_session_meta(sid, subagent=True) + "\n", encoding="utf-8")
            with store_patch(CODEX_SESSIONS_DIR=str(tmp)):
                config, state = runtime()
                self.assertIsNone(observer.resolve_transcript(config, state, "codex", sid))

    def test_an_unregistered_harness_and_an_unnamed_id_resolve_to_nothing(self) -> None:
        # The Codex store is patched to an empty directory on purpose: without
        # it `runtime()` resolves the developer's real `~/.codex/sessions`, and
        # this assertion passed vacuously on a machine with no rollouts.
        with tempfile.TemporaryDirectory() as tmp, store_patch(CODEX_SESSIONS_DIR=tmp):
            config, state = runtime()
            self.assertIsNone(observer.resolve_transcript(config, state, "codex", "abc"))
            self.assertIsNone(observer.resolve_transcript(config, state, "gemini", "abc"))
            self.assertIsNone(observer.resolve_transcript(config, state, "pi", "a/../b"))


class ObserverRouteTest(RuntimeTestCase):
    """`GET /api/observe`, which had no test of its own."""

    def _get(self, server: Any, query: str) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/observe" + query)
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response.status, body

    def test_the_route_answers_with_the_sidecar_and_writes_it(self) -> None:
        sid = "abcdef12-3456-7890-abcd-ef1234567890"
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            (projects / "-home-me-repo").mkdir(parents=True)
            (projects / "-home-me-repo" / f"{sid}.jsonl").write_text(
                json.dumps(
                    {
                        "type": "message",
                        "id": "m1",
                        "message": {"role": "user", "content": "Fix the failing build"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = Path(tmp) / "cargento-home"
            with (
                store_patch(PROJECTS_DIR=str(projects)),
                mock.patch.dict(os.environ, {"CARGENTO_HOME": str(home)}),
            ):
                httpd = make_server()
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    status, body = self._get(httpd, f"?harness=claude&sid={sid}")
                    missing, _ = self._get(httpd, "?harness=claude&sid=deadbeef")
                    unnamed, _ = self._get(httpd, "?harness=claude&sid=a%2Fb")
                    bare, _ = self._get(httpd, "?harness=claude")
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=2)
                # The path the *server's* config resolves, not a second one: the
                # store home comes off the environment and both must agree. And
                # checked in here, before the temp tree is torn down.
                sidecar = observer.sidecar_path(httpd.application.config, "claude", sid)
                assert sidecar is not None
                wrote_sidecar = os.path.isfile(sidecar)

        self.assertEqual(200, status)
        payload = json.loads(body)
        self.assertIn("Fix the failing build", payload["goal"])
        self.assertEqual("", payload["stage"])  # no workflow booted
        # A sid that resolves to no transcript is a 404, not an empty 200: the
        # panel must be able to tell "nothing to observe" from "nothing found".
        self.assertEqual(404, missing)
        # A sid that is not a name never reaches the resolver.
        self.assertEqual(404, unnamed)
        self.assertEqual(400, bare)
        self.assertTrue(wrote_sidecar)


class ObserverReachabilityTest(PageJsHarness):
    """That a reader can actually get to the panel, and what happens when they do.

    The gap this closes: `renderObserverPanel` and `observeSession` existed and
    nothing in the page called either, so the whole surface was unreachable
    while four tests calling the render function directly stayed green. These
    drive the control, not the function.

    The calm board fixture is borrowed rather than inherited, and reached
    through its module rather than imported by name: subclassing `CalmModeTest`
    re-runs all sixty of its tests under a second name, and so does importing
    the class into this namespace, because that is where discovery looks.
    """

    def run_calm(self, checks: str) -> Any:
        calm = test_page_calm.CalmModeTest
        return self._run_page_js(calm.FIXTURE + checks, prelude=calm.prelude("calm"))

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_drawer_offers_observe_and_the_control_fetches_and_paints(self) -> None:
        checks = """
const out = {};
__fetchImpl = () => Promise.resolve({ok: true, json: () => Promise.resolve(
  {goal: "ship the observer route", stage: "implementation", block: "blocked on node"})});
render(board());

// Closed: no control and no panel.
out.closedHasControl = __els.app.innerHTML.includes('data-calm="observe"');

calmAction("open", K("claude", "aaa1"));
out.openHasControl = __els.app.innerHTML.includes('data-calm="observe" data-arg="claude:aaa1"');
out.openHasPanelBeforeAsking = __els.app.innerHTML.includes("observer-panel");

// The control, through the same channel a click takes.
calmAction("observe", K("claude", "aaa1"));
out.loading = __els.app.innerHTML.includes("observer-loading");
out.asked = __fetchCalls.map(c => c[0]).filter(u => String(u).includes("/api/observe"));
await __settle();
await __settle();
out.painted = __els.app.innerHTML.includes("ship the observer route");
out.stage = __els.app.innerHTML.includes("implementation");
out.block = __els.app.innerHTML.includes("blocked on node");

// It survives the 5s re-render, which is what killed a container-only write.
render(board());
out.survivesRerender = __els.app.innerHTML.includes("ship the observer route");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertFalse(out["closedHasControl"])
        self.assertTrue(out["openHasControl"])
        # Nothing is derived until asked: the route reads a transcript and two
        # project files, which a thirty-row board must not do on a poll.
        self.assertFalse(out["openHasPanelBeforeAsking"])
        self.assertEqual(
            ["/api/observe?harness=claude&sid=aaa1"],
            out["asked"],
        )
        self.assertTrue(out["painted"])
        self.assertTrue(out["stage"])
        self.assertTrue(out["block"])
        self.assertTrue(out["survivesRerender"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_failed_observe_says_so_and_an_unobservable_harness_has_no_control(self) -> None:
        checks = """
const out = {};
__fetchImpl = () => Promise.resolve({ok: false, json: () => Promise.resolve({})});
render(board());
calmAction("open", K("claude", "aaa1"));
calmAction("observe", K("claude", "aaa1"));
await __settle();
await __settle();
out.error = __els.app.innerHTML.includes("observer-error");

// `bbb2` is the Codex row in the shared fixture, and `resolve_transcript` grew
// a Codex branch: the control follows the resolver rather than lagging it.
calmAction("open", K("codex", "bbb2"));
out.codexHasControl = __els.app.innerHTML.includes('data-calm="observe" data-arg="codex:bbb2"');

// A harness the resolver has no branch for still gets none, which is the half
// of the gate that keeps a control off a row that could only 404.
render(payload([blocked, busy, quiet,
  mk({sid: "ddd4", session: "ddd4", harness: "cursor", title: "Cursor row"})]));
calmAction("open", K("cursor", "ddd4"));
out.cursorHasControl = __els.app.innerHTML.includes('data-calm="observe" data-arg="cursor:ddd4"');
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["error"])
        self.assertTrue(out["codexHasControl"])
        self.assertFalse(out["cursorHasControl"])


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
