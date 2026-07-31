from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import mock

from cargento_runtime import spacedock

from .support import (
    make_runtime,
    runtime,
    state_of,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class SpacedockParserTest(unittest.TestCase):
    """Pure parsers, so every branch runs on every OS runner (decision D-4)."""

    DEBUG_FLYWHEEL: ClassVar[list[str]] = [
        "intake",
        "reproduce",
        "discover",
        "hypothesize",
        "verify",
        "fix-and-harden",
        "uat",
        "closed",
    ]

    def frontmatter(self, body: str) -> list[str]:
        config, _runtime = runtime()
        lines: list[str] = spacedock.frontmatter_lines(config, body)
        return lines

    def test_stage_names_read_document_order_past_sibling_blocks(self) -> None:
        """`transitions:` and a nested `decision:` must not leak into the spine."""
        config, _runtime = runtime()
        body = (
            "---\n"
            "commissioned-by: spacedock@0.22.0\n"
            "state: .spacedock-state\n"
            "stages:\n"
            "  defaults:\n"
            "    worktree: false\n"
            "  states:\n"
            "    - name: intake\n"
            "      initial: true\n"
            "    - name: review\n"
            "    - name: fix-and-harden\n"
            "      worktree: true\n"
            "    - name: escalated\n"
            "      gate: true\n"
            "      decision:\n"
            "        field: verdict\n"
            "        options:\n"
            "          - {label: Close, value: CLOSED, handoff: fo}\n"
            "    - name: posted\n"
            "      terminal: true\n"
            "  transitions:\n"
            "    - from: review\n"
            "      to: intake\n"
            "      label: needs rework\n"
            "---\n"
            "# Prose\n"
        )
        lines = self.frontmatter(body)

        self.assertEqual("spacedock@0.22.0", spacedock.scalar(lines, "commissioned-by"))
        self.assertEqual(
            ["intake", "review", "fix-and-harden", "escalated", "posted"],
            spacedock.stage_names(config, lines),
        )
        # The initial and terminal flags belong to the item they are nested
        # under, and `gate:`/`worktree:`/the decision options are not flags.
        self.assertEqual(
            [("intake", True, False), ("posted", False, True)],
            [
                (entry["name"], entry["initial"], entry["terminal"])
                for entry in spacedock.stage_entries(config, lines)
                if entry["initial"] or entry["terminal"]
            ],
        )

    def test_stage_flags_accept_yamls_true_ish_spellings(self) -> None:
        config, _runtime = runtime()
        body = (
            "---\n"
            "stages:\n"
            "  states:\n"
            "    - name: intake\n"
            '      initial: "true"\n'
            "    - name: review\n"
            "      terminal: false\n"
            "    - name: posted\n"
            "      terminal: yes\n"
            "---\n"
        )

        self.assertEqual(
            [("intake", True, False), ("review", False, False), ("posted", False, True)],
            [
                (e["name"], e["initial"], e["terminal"])
                for e in spacedock.stage_entries(config, self.frontmatter(body))
            ],
        )

    def test_frontmatter_requires_a_closed_leading_fence(self) -> None:
        for label, body in [
            ("no fence", "# Just prose\n"),
            ("unterminated", "---\nstages:\n"),
            ("prose first", "intro\n---\nstages:\n---\n"),
        ]:
            with self.subTest(case=label):
                self.assertEqual([], self.frontmatter(body))

    def test_stage_names_refuse_shapes_the_scanner_cannot_model(self) -> None:
        """An unmodellable construct must render no strip, never a wrong one."""
        config, _runtime = runtime()
        cases = {
            "flow sequence": "stages:\n  states: [intake, review]\n",
            "no states block": "stages:\n  defaults:\n    worktree: false\n",
            "stages absent": "state: .spacedock-state\n",
            "illegal name": "stages:\n  states:\n    - name: Intake_Bad\n",
            "flow item": "stages:\n  states:\n    - {name: intake}\n    - name: review\n",
            "single char name": "stages:\n  states:\n    - name: x\n",
            "duplicate name": "stages:\n  states:\n    - name: review\n    - name: review\n",
        }
        for label, block in cases.items():
            with self.subTest(case=label):
                lines = ("---\n" + block + "---\n").split("\n")[1:-2]
                self.assertEqual([], spacedock.stage_names(config, lines))

    def test_workers_are_attributed_to_a_known_slug(self) -> None:
        """Cycle markers appear on either side of the stage, and a slug may end
        in a cycle-shaped token of its own — so the slug must be known, never
        guessed off the name."""
        slugs = ["case-7", "verify-the-thing", "case-7-r3"]
        cases = [
            ("spacedock-ensign-case-7-uat", ("case-7", "uat", "")),
            ("spacedock-ensign-case-7-fix-and-harden", ("case-7", "fix-and-harden", "")),
            ("spacedock-ensign-case-7-cycle2-verify", ("case-7", "verify", "cycle2")),
            ("spacedock-ensign-case-7-verify-c2", ("case-7", "verify", "c2")),
            ("spacedock-ensign-case-7-verify-pass2b", ("case-7", "verify", "pass2b")),
            # A slug ending in a cycle-shaped token is one entity, not a retry of
            # a shorter slug: longest-slug-first keeps them apart.
            ("spacedock-ensign-case-7-r3-verify", ("case-7-r3", "verify", "")),
            # A slug containing a stage name survives intact.
            ("spacedock-ensign-verify-the-thing-uat", ("verify-the-thing", "uat", "")),
        ]
        for name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    expected,
                    spacedock.attribute_worker(name, slugs, self.DEBUG_FLYWHEEL),
                )

    def test_workers_are_rejected_rather_than_mis_attributed(self) -> None:
        slugs = ["case-7"]
        for label, name in [
            ("not an ensign", "some-other-agent-uat"),
            ("slug unknown to this workflow", "spacedock-ensign-case-9-uat"),
            ("no known stage", "spacedock-ensign-case-7-shipit"),
            ("real content beside the stage", "spacedock-ensign-case-7-uat-extra"),
        ]:
            with self.subTest(case=label):
                self.assertIsNone(spacedock.attribute_worker(name, slugs, self.DEBUG_FLYWHEEL))

    def test_boot_records_require_tool_result_provenance(self) -> None:
        """Boot output is command output. Conversation text that merely contains
        an envelope must not be able to nominate a path for Cargento to open."""
        config, _runtime = runtime()
        envelope = (
            '{"command":"boot","id_style":"slug",'
            '"dispatchable":[{"slug":"drc-1","current":"review","next":"disposition"}],'
            '"definition_dir":"/w/one","entity_dir":"/w/one"}'
        )

        def line(block_type: str) -> bytes:
            return json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [{"type": block_type, "content": "=== BOOT ===\n" + envelope}]
                    },
                }
            ).encode()

        records = spacedock.boot_records(config, line("tool_result"))

        self.assertEqual(1, len(records))
        self.assertEqual("/w/one", records[0]["definition_dir"])
        self.assertEqual({"drc-1": "review"}, spacedock.boot_entities(records, "/w/one"))
        self.assertEqual(["/w/one"], spacedock.workflow_dirs(config, records))
        # Same bytes, ordinary text block: no provenance, no record.
        self.assertEqual([], spacedock.boot_records(config, line("text")))
        self.assertEqual([], spacedock.boot_records(config, b'{"not":"jsonl definition_dir"}'))

    def test_boot_scan_is_bounded_against_decoy_candidates(self) -> None:
        """Every unbalanced candidate used to rescan to the end of the blob."""
        config, _runtime = runtime()
        decoys = '{"command"' * 40_000
        payload = json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "content": decoys + " definition_dir"}]
                },
            }
        ).encode()
        started = time.monotonic()

        self.assertEqual([], spacedock.boot_records(config, payload))

        self.assertLess(time.monotonic() - started, 1.0)

    def test_workflow_dirs_reject_relative_and_nul_paths(self) -> None:
        config, _runtime = runtime()
        records: list[dict[str, Any]] = [
            {"command": "boot", "definition_dir": "docs/spacedock/rel"},
            {"command": "boot", "definition_dir": "/abs/ok"},
            {"command": "boot", "definition_dir": "/abs/ok"},
            {"command": "boot", "definition_dir": ""},
        ]

        self.assertEqual(["/abs/ok"], spacedock.workflow_dirs(config, records))


class SpacedockReadContractTest(unittest.TestCase):
    """The one project read Cargento performs, and its refusals."""

    README = (
        "---\n"
        "commissioned-by: spacedock@0.22.0\n"
        "state: .spacedock-state\n"
        "stages:\n"
        "  states:\n"
        "    - name: intake\n"
        "      initial: true\n"
        "    - name: review\n"
        "    - name: posted\n"
        "      terminal: true\n"
        "---\n"
    )

    def setUp(self) -> None:
        _config, state = runtime()
        with state_of().cache_lock:
            state.spacedock_workflow_cache.clear()
            state.spacedock_boot_cache.clear()
            state.spacedock_role_cache.clear()
            state.spacedock_entity_cache.clear()

    def workflow(self, body: str | None = None) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="cargento-sd-")
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "wf"
        root.mkdir()
        if body is not None:
            (root / "README.md").write_text(body, encoding="utf-8")
        return root

    def entity(self, state: Path, slug: str, status: str, *, folder: bool = False) -> Path:
        state.mkdir(exist_ok=True)
        body = f'---\nid:\ntitle: "a thing"\nstatus: {status}\n---\n\n# report\n'
        if folder:
            (state / slug).mkdir()
            path = state / slug / "index.md"
        else:
            path = state / f"{slug}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_commissioned_readme_yields_its_ordered_stages(self) -> None:
        config, state = runtime()
        root = self.workflow(self.README)

        self.assertEqual(
            {
                "name": "wf",
                "stages": ["intake", "review", "posted"],
                "resting": ["intake", "posted"],
            },
            spacedock.read_workflow(config, state, str(root)),
        )

    def test_uncommissioned_or_absent_readme_yields_nothing(self) -> None:
        config, state = runtime()
        cases = [
            ("absent", None),
            ("not commissioned", "---\nstages:\n  states:\n    - name: intake\n---\n"),
            ("commissioned but no stages", "---\ncommissioned-by: spacedock@1.0.0\n---\n"),
        ]
        for label, body in cases:
            with self.subTest(case=label):
                self.assertIsNone(spacedock.read_workflow(config, state, str(self.workflow(body))))

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlink")
    def test_a_symlinked_readme_is_refused_not_followed(self) -> None:
        config, state = runtime()
        root = self.workflow(None)
        target = root.parent / "elsewhere.md"
        target.write_text(self.README, encoding="utf-8")
        try:
            (root / "README.md").symlink_to(target)
        except OSError:  # pragma: no cover - Windows without the privilege
            self.skipTest("symlink creation not permitted")

        self.assertIsNone(spacedock.read_workflow(config, state, str(root)))

    def test_the_readme_read_stops_at_its_configured_bounds(self) -> None:
        # These are project reads, not store reads, so the byte and line bounds
        # are the read policy rather than an optimisation. Mutation-checked:
        # raising either bound passed the whole suite, because every other
        # fixture is far smaller than the shipped defaults.
        root = self.workflow(self.README)
        head = self.README.index("states:")

        generous, state = make_runtime()
        self.assertIsNotNone(spacedock.read_workflow(generous, state, str(root)))

        # A byte bound that stops before the states block yields no stages.
        byte_bound, byte_runtime = make_runtime(spacedock_readme_bytes=head)
        truncated = spacedock.read_workflow(byte_bound, byte_runtime, str(root))
        self.assertEqual([], (truncated or {}).get("stages", []))

        # A line bound of one cannot reach the states block either.
        line_bound, line_runtime = make_runtime(spacedock_max_frontmatter_lines=1)
        clipped = spacedock.read_workflow(line_bound, line_runtime, str(root))
        self.assertEqual([], (clipped or {}).get("stages", []))

    def test_only_frontmatter_is_read_however_long_the_body(self) -> None:
        config, state = runtime()
        root = self.workflow(self.README + ("prose line\n" * 40_000))

        result = spacedock.read_workflow(config, state, str(root))

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(["intake", "review", "posted"], result["stages"])

    def test_session_workflows_prefer_live_workers_then_boot_entities(self) -> None:
        config, state = runtime()
        root = self.workflow(self.README)
        boot = [
            {
                "command": "boot",
                "definition_dir": str(root),
                "dispatchable": [
                    {"slug": "drc-1", "current": "review"},
                    {"slug": "drc-2", "current": "intake"},
                    {"slug": "drc-3", "current": "not-a-stage"},
                ],
            }
        ]

        strips = spacedock.session_workflows(
            config, state, boot, ["spacedock-ensign-drc-1-posted"], time.time(), 3600
        )

        self.assertEqual(1, len(strips))
        self.assertEqual(["intake", "review", "posted"], strips[0]["stages"])
        # The live worker wins for drc-1 (posted, not the booted review) and is
        # marked live; drc-3 is dropped because its stage is not declared.
        self.assertEqual(
            [("drc-1", "posted", True), ("drc-2", "intake", False)],
            [(e["slug"], e["stage"], e["live"]) for e in strips[0]["entities"]],
        )

    def test_entity_state_anchors_a_first_officer_that_booted_an_empty_queue(self) -> None:
        """The regression this whole path exists for. A first officer that boots
        before any entity is intaken reports `dispatchable: []` for the rest of
        the session; without the state directory there is no slug to anchor the
        live worker on, and the workflow renders no strip at all."""
        config, state = runtime()
        root = self.workflow(self.README)
        entity_state = root / ".spacedock-state"
        self.entity(entity_state, "drc-7", "intake")  # queued, not moving
        self.entity(entity_state, "drc-8", "review")  # moving, no live worker
        self.entity(entity_state, "drc-9", "posted")  # finished
        self.entity(entity_state, "pr-42", "review")  # the live worker's entity
        boot = [
            {
                "command": "boot",
                "definition_dir": str(root),
                "entity_dir": str(entity_state),
                "entity_dir_present": "false",
                "dispatchable": [],
            }
        ]

        strips = spacedock.session_workflows(
            config, state, boot, ["spacedock-ensign-pr-42-posted"], time.time(), 3600
        )

        self.assertEqual(1, len(strips))
        # pr-42 is live and at the worker's stage, not the file's; drc-8 is in
        # flight; drc-7 (initial) and drc-9 (terminal) are resting, not moving.
        self.assertEqual(
            [("pr-42", "posted", True), ("drc-8", "review", False)],
            [(e["slug"], e["stage"], e["live"]) for e in strips[0]["entities"]],
        )

    def test_entity_state_is_read_newest_first_in_both_file_shapes(self) -> None:
        config, state = runtime()
        root = self.workflow(self.README)
        entity_state = root / ".spacedock-state"
        older = self.entity(entity_state, "drc-1", "review")
        newer = self.entity(entity_state, "drc-2", "review", folder=True)
        os.utime(older, (1_700_000_000, 1_700_000_000))
        os.utime(newer, (1_700_000_100, 1_700_000_100))

        self.assertEqual(
            [("drc-2", "review"), ("drc-1", "review")],
            spacedock.read_entities(
                config,
                state,
                str(entity_state),
                ["intake", "review", "posted"],
                1_700_000_200,
                3600,
            ),
        )

    def test_entity_state_refuses_everything_that_is_not_an_entity(self) -> None:
        config, state = runtime()
        root = self.workflow(self.README)
        entity_state = root / ".spacedock-state"
        self.entity(entity_state, "drc-1", "review")
        # Spacedock retires finished entities into _archive/, operators leave
        # reports beside the entity_state, and a stage the workflow never declared
        # cannot be placed on the spine.
        self.entity(entity_state / "_archive", "drc-0", "review")
        (entity_state / "REVIEW-REPORT-DRC-1.md").write_text(
            "---\nstatus: review\n---\n", encoding="utf-8"
        )
        (entity_state / "notes.txt").write_text("---\nstatus: review\n---\n", encoding="utf-8")
        self.entity(entity_state, "drc-2", "not-a-declared-stage")
        self.entity(entity_state, "drc-3", "")

        self.assertEqual(
            [("drc-1", "review")],
            spacedock.read_entities(
                config, state, str(entity_state), ["intake", "review", "posted"], time.time(), 3600
            ),
        )

    def test_entity_files_report_a_stat_that_identifies_the_file(self) -> None:
        """`scandir` caches a stat, and on Windows that cached result reports
        st_ino and st_dev as zero — which can never match the fstat of an open
        descriptor, so every entity file would be refused on that platform
        alone. Reproduced here by simulating the cached stat, because a POSIX
        runner cannot otherwise see it."""
        config, state = runtime()
        root = self.workflow(self.README)
        entity_state = root / ".spacedock-state"
        self.entity(entity_state, "drc-1", "review")
        real_scandir = os.scandir

        class WindowsLikeEntry:
            def __init__(self, entry: os.DirEntry[str]) -> None:
                self.name, self.path = entry.name, entry.path
                self._entry = entry

            def is_dir(self, *, follow_symlinks: bool = True) -> bool:
                return self._entry.is_dir(follow_symlinks=follow_symlinks)

            def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
                real = self._entry.stat(follow_symlinks=follow_symlinks)
                fields = list(real)
                fields[1] = 0  # st_ino
                fields[2] = 0  # st_dev
                # Only the identity fields are zeroed. The nanosecond times
                # have to be carried through the extended dict or they come
                # back as None and the failure under test is masked by a
                # TypeError in the sort.
                return os.stat_result(
                    fields,
                    {
                        "st_atime_ns": real.st_atime_ns,
                        "st_mtime_ns": real.st_mtime_ns,
                        "st_ctime_ns": real.st_ctime_ns,
                    },
                )

        @contextlib.contextmanager
        def windows_like_scandir(path: str) -> Iterator[list[WindowsLikeEntry]]:
            with real_scandir(path) as entries:
                yield [WindowsLikeEntry(entry) for entry in entries]

        with mock.patch.object(os, "scandir", windows_like_scandir):
            found = spacedock.entity_files(config, str(entity_state))
            self.assertEqual(1, len(found))
            _, path, info = found[0]
            self.assertEqual(
                (os.stat(path).st_dev, os.stat(path).st_ino),
                (info.st_dev, info.st_ino),
            )
            self.assertEqual(
                [("drc-1", "review")],
                spacedock.read_entities(
                    config,
                    state,
                    str(entity_state),
                    ["intake", "review", "posted"],
                    time.time(),
                    3600,
                ),
            )

    def test_entity_state_older_than_the_window_is_history_not_work(self) -> None:
        """A first officer discovers every workflow in the project. One retired
        months ago still has entities frozen mid-pipeline."""
        config, state = runtime()
        root = self.workflow(self.README)
        entity_state = root / ".spacedock-state"
        stale = self.entity(entity_state, "drc-1", "review")
        os.utime(stale, (1_700_000_000, 1_700_000_000))

        self.assertEqual(
            [],
            spacedock.read_entities(
                config,
                state,
                str(entity_state),
                ["intake", "review", "posted"],
                1_700_000_000 + 90_000,
                86_400,
            ),
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlink")
    def test_a_symlinked_entity_file_is_refused_not_followed(self) -> None:
        config, state = runtime()
        root = self.workflow(self.README)
        entity_state = root / ".spacedock-state"
        target = self.entity(entity_state, "drc-1", "review")
        try:
            (entity_state / "drc-2.md").symlink_to(target)
        except OSError:  # pragma: no cover - Windows without the privilege
            self.skipTest("symlink creation not permitted")

        self.assertEqual(
            [("drc-1", "review")],
            spacedock.read_entities(
                config, state, str(entity_state), ["intake", "review", "posted"], time.time(), 3600
            ),
        )

    def test_entity_frontmatter_is_reread_only_when_the_file_changes(self) -> None:
        config, state = runtime()
        root = self.workflow(self.README)
        entity_state = root / ".spacedock-state"
        path = self.entity(entity_state, "drc-1", "review")
        stages = ["intake", "review", "posted"]
        now = time.time()

        reads: list[str] = []
        real = spacedock.read_frontmatter

        def counting(cfg: Any, p: str, limit: int, expect: os.stat_result) -> list[str]:
            reads.append(p)
            lines: list[str] = real(cfg, p, limit, expect)
            return lines

        with mock.patch.object(spacedock, "read_frontmatter", counting):
            spacedock.read_entities(config, state, str(entity_state), stages, now, 3600)
            spacedock.read_entities(config, state, str(entity_state), stages, now, 3600)
            self.assertEqual(1, len(reads))
            self.entity(entity_state, "drc-1", "posted")
            os.utime(path, (now + 1, now + 1))
            self.assertEqual(
                [("drc-1", "posted")],
                spacedock.read_entities(config, state, str(entity_state), stages, now + 2, 3600),
            )
        self.assertEqual(2, len(reads))

    def test_the_entity_dir_is_taken_from_boot_and_must_be_absolute(self) -> None:
        records: list[dict[str, Any]] = [
            {"command": "boot", "definition_dir": "/w", "entity_dir": "relative/state"},
            {"command": "boot", "definition_dir": "/other", "entity_dir": "/other/state"},
            {"command": "boot", "definition_dir": "/w", "entity_dir": "/w/state"},
            {"command": "boot", "definition_dir": "/w", "entity_dir": 17},
        ]

        self.assertEqual("/w/state", spacedock.boot_entity_dir(records, "/w"))
        self.assertEqual("/other/state", spacedock.boot_entity_dir(records, "/other"))
        self.assertEqual("", spacedock.boot_entity_dir(records, "/absent"))

    def test_a_failed_wrap_does_not_leak_the_descriptor(self) -> None:
        """os.fdopen leaves the fd open when it raises, and this runs every
        refresh — a leak here exhausts the descriptor table."""
        config, state = runtime()
        root = self.workflow(self.README)
        opened: list[int] = []
        real_open = os.open

        def counting_open(*args: object, **kwargs: object) -> int:
            descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
            opened.append(descriptor)
            return descriptor

        with (
            mock.patch.object(os, "open", counting_open),
            mock.patch.object(os, "fdopen", side_effect=OSError("boom")),
        ):
            self.assertIsNone(spacedock.read_workflow(config, state, str(root)))

        self.assertEqual(1, len(opened))
        with self.assertRaises(OSError):
            os.fstat(opened[0])

    def test_no_workflow_no_strip(self) -> None:
        config, state = runtime()
        now = time.time()
        self.assertEqual([], spacedock.session_workflows(config, state, [], [], now, 3600))
        self.assertEqual(
            [],
            spacedock.session_workflows(
                config,
                state,
                [{"command": "boot", "definition_dir": "/nonexistent/wf"}],
                [],
                now,
                3600,
            ),
        )

    def test_a_workflow_with_no_state_directory_still_costs_no_walk(self) -> None:
        config, state = runtime()
        root = self.workflow(self.README)
        boot = [
            {
                "command": "boot",
                "definition_dir": str(root),
                "entity_dir": str(root / ".spacedock-state"),
                "dispatchable": [],
            }
        ]

        self.assertEqual(
            [], spacedock.session_workflows(config, state, boot, [], time.time(), 3600)
        )
