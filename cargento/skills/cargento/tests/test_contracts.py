from __future__ import annotations

import ast
import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

from . import test_claude, test_codex, test_copilot, test_droid, test_pi
from .fixtures import (
    HARNESSES,
    STORE_CONSTANTS,
    build_opencode,
    build_pi,
)
from .support import HarnessContractTestCase, LegacyDashboardTestCase, dashboard

SKILL_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = SKILL_DIR / "cargento_runtime"
RUNTIME_PREFIX = "cargento_runtime"
FORBIDDEN_RUNTIME_PREFIX = "cargento.skills.cargento.cargento_runtime"


class RuntimeImportGraphTest(unittest.TestCase):
    """Every runtime dependency is reviewed in the task that introduces it."""

    EXPECTED: ClassVar[dict[str, set[str]]] = {
        "cargento_runtime": set(),
        "cargento_runtime.web": set(),
        "cargento_runtime.web.page": set(),
    }

    @staticmethod
    def _module_name(path: Path) -> str:
        relative = path.relative_to(SKILL_DIR).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    def _relative_target(self, module: str, node: ast.ImportFrom, *, is_package: bool) -> str:
        package = module.split(".") if is_package else module.split(".")[:-1]
        if node.level > len(package):
            self.fail(f"{module} has a relative import that climbs above cargento_runtime")
        base = package[: len(package) - node.level + 1]
        if not base or base[0] != RUNTIME_PREFIX:
            self.fail(f"{module} has a relative import that climbs above cargento_runtime")
        return ".".join([*base, *([node.module] if node.module else [])])

    def _run_graph_fixture(
        self,
        source: str,
        expected_dependencies: set[str],
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            runtime_dir = skill_dir / "cargento_runtime"
            runtime_dir.mkdir()
            module_path = runtime_dir / "fixture.py"
            module_path.write_text(source, encoding="utf-8")
            expected = {"cargento_runtime.fixture": expected_dependencies}
            with (
                mock.patch.multiple(
                    sys.modules[__name__],
                    SKILL_DIR=skill_dir,
                    RUNTIME_DIR=runtime_dir,
                ),
                mock.patch.object(self, "EXPECTED", expected),
            ):
                self.test_runtime_import_graph_matches_the_reviewed_allowlist()

    def test_importfrom_namespace_aliases_are_rejected(self) -> None:
        forbidden = (
            "from cargento.skills.cargento import cargento_runtime\n",
            "from cargento.skills.cargento import cargento_runtime as runtime\n",
            "from cargento.skills.cargento import cargento_runtime, server\n",
        )
        for source in forbidden:
            with (
                self.subTest(source=source),
                self.assertRaisesRegex(AssertionError, "namespace-qualified runtime import"),
            ):
                self._run_graph_fixture(source, set())

    def test_canonical_import_forms_remain_legal(self) -> None:
        source = """
import cargento_runtime.web.page
from cargento_runtime.web import page
from . import page as sibling_page
"""
        self._run_graph_fixture(
            source,
            {
                "cargento_runtime.page",
                "cargento_runtime.web",
                "cargento_runtime.web.page",
            },
        )

    def test_relative_import_cannot_climb_above_runtime(self) -> None:
        with self.assertRaisesRegex(AssertionError, "climbs above cargento_runtime"):
            self._run_graph_fixture("from .. import server\n", set())

    def test_runtime_import_graph_matches_the_reviewed_allowlist(self) -> None:
        actual: dict[str, set[str]] = {}
        for path in sorted(RUNTIME_DIR.rglob("*.py")):
            module = self._module_name(path)
            dependencies: set[str] = set()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(
                            alias.name == FORBIDDEN_RUNTIME_PREFIX
                            or alias.name.startswith(f"{FORBIDDEN_RUNTIME_PREFIX}."),
                            f"{module} uses namespace-qualified runtime import {alias.name}",
                        )
                        if alias.name == RUNTIME_PREFIX or alias.name.startswith(
                            f"{RUNTIME_PREFIX}."
                        ):
                            dependencies.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    imported = (
                        self._relative_target(
                            module,
                            node,
                            is_package=path.name == "__init__.py",
                        )
                        if node.level
                        else (node.module or "")
                    )
                    candidates = [
                        imported,
                        *(f"{imported}.{alias.name}" for alias in node.names),
                    ]
                    for candidate in candidates:
                        self.assertFalse(
                            candidate == FORBIDDEN_RUNTIME_PREFIX
                            or candidate.startswith(f"{FORBIDDEN_RUNTIME_PREFIX}."),
                            f"{module} uses namespace-qualified runtime import {candidate}",
                        )
                    if imported == RUNTIME_PREFIX or imported.startswith(f"{RUNTIME_PREFIX}."):
                        if imported == RUNTIME_PREFIX or node.module is None:
                            dependencies.update(f"{imported}.{alias.name}" for alias in node.names)
                        else:
                            dependencies.add(imported)
            dependencies.discard(module)
            actual[module] = dependencies
        self.assertEqual(self.EXPECTED, actual)


class CollectorAgreementTest(LegacyDashboardTestCase):
    def test_claude_and_codex_agree_on_one_directory(self) -> None:
        # DRC-3963. The reported case: one worktree, two harnesses, two
        # different project strings — Claude showed the whole encoded path
        # ("git-spacedock-research-spacedock-subspace") while Codex showed a
        # bare basename. Same directory has to read the same on every row.
        now = dashboard.time.time()
        home = "/Users/cl"
        cwd = f"{home}/git/spacedock-research/spacedock/subspace"
        iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        encoded = dashboard.encoded_home_prefix(cwd)  # Claude's projects/ dir name
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / encoded
            project_dir.mkdir(parents=True)
            (project_dir / "aaaa1111-0000-0000-0000-000000000000.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": iso,
                        "cwd": cwd,
                        "message": {"role": "user", "content": "hi"},
                    }
                )
                + "\n"
            )
            rollout = Path(tmp) / "codex" / "2026" / "07" / "28"
            rollout.mkdir(parents=True)
            sid = "019f855d-aaaa-7000-8000-000000000001"
            (rollout / f"rollout-2026-07-28T09-36-23-{sid}.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": iso,
                        "type": "session_meta",
                        "payload": {"id": sid, "cwd": cwd, "source": "exec"},
                    }
                )
                + "\n"
            )
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
                mock.patch.object(dashboard, "CODEX_SESSIONS_DIR", str(Path(tmp) / "codex")),
                mock.patch.dict(
                    dashboard.STORE_ROOTS,
                    {
                        "claude.projects": [str(Path(tmp) / "projects")],
                        "claude.tasks": [str(Path(tmp) / "no-tasks")],
                        "codex.sessions": [str(Path(tmp) / "codex")],
                    },
                ),
                mock.patch.object(dashboard, "HOME", home),
                mock.patch.object(dashboard, "HOME_PREFIX", dashboard.encoded_home_prefix(home)),
            ):
                claude = dashboard.collect_claude(now, 24, False)
                codex = dashboard.collect_codex(now, 24, False)

        self.assertEqual(1, len(claude))
        self.assertEqual(1, len(codex))
        self.assertEqual("spacedock/subspace", claude[0]["project"])
        self.assertEqual(claude[0]["project"], codex[0]["project"])


class HarnessContractTest(HarnessContractTestCase):
    """One behavioural contract, asserted against every harness.

    The rest of the suite grew out of specific bugs, so it covers Claude deeply
    and the other seven thinly. This states what the dashboard must do and
    checks all of them, on whichever OS the runner is.
    """

    def test_pi_store_is_registered_as_a_harness(self) -> None:
        # Removing Pi from the registry would make a valid store invisible.
        self.assertIs(sys.modules["cargento_server"], dashboard)
        self.assertNotIn("cargento.skills.cargento.cargento_runtime", sys.modules)
        self.assertEqual(
            {id(dashboard)},
            {
                id(module.dashboard)
                for module in (test_claude, test_codex, test_copilot, test_droid, test_pi)
            },
        )
        data = self.collect(build_pi, when=self.NOW)
        self.assertTrue(
            any(harness["key"] == "pi" for harness in data["harnesses"]),
            "Pi store must appear in the harness registry",
        )

    def test_a_fresh_store_is_discovered_and_reads_working(self) -> None:
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW)
                harness = next(h for h in data["harnesses"] if h["key"] == key)
                self.assertTrue(harness["discovered"], "store present but not discovered")
                self.assertIsNone(harness["error"])
                sessions = self.sessions_for(data, key)
                self.assertEqual(1, len(sessions), f"expected one session, got {sessions}")
                self.assertEqual("working", sessions[0]["state"])

    def test_a_stale_store_reads_idle_but_still_appears(self) -> None:
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW - 7200)
                sessions = self.sessions_for(data, key)
                self.assertEqual(1, len(sessions))
                self.assertEqual("idle", sessions[0]["state"])

    def test_an_absent_store_is_not_discovered_and_is_not_an_error(self) -> None:
        # "No harness here" and "harness broken" must never look the same.
        data = self.collect(lambda *_a: {}, when=self.NOW)
        for harness in data["harnesses"]:
            with self.subTest(harness=harness["key"]):
                self.assertFalse(harness["discovered"])
                self.assertIsNone(harness["error"])
        self.assertEqual([], data["sessions"])

    def test_a_future_dated_store_does_not_read_working(self) -> None:
        # A clock-skewed store must not invent activity, on any harness.
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW + 86_400)
                for session in self.sessions_for(data, key):
                    self.assertNotEqual("working", session["state"])
                    self.assertEqual(0, session["rate_per_min"])

    def test_one_session_in_two_candidate_roots_yields_one_row(self) -> None:
        # De-duplication has to be wired into collect(), not merely available:
        # scanning every candidate root is what makes a migrated store appear
        # twice, and only the full pass can collapse it.
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            first, second = Path(tmp) / "one", Path(tmp) / "two"
            build_opencode(first, self.NOW, self.SID, self.TITLE)
            build_opencode(second, self.NOW - 60, self.SID, self.TITLE)
            patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
            patches["OPENCODE_DATA"] = str(first)
            with contextlib.ExitStack() as stack:
                for name, value in patches.items():
                    stack.enter_context(mock.patch.object(dashboard, name, value))
                # primary == candidates[0], so the whole list is scanned.
                stack.enter_context(
                    mock.patch.dict(
                        dashboard.STORE_ROOTS,
                        {"opencode.data": [str(first), str(second)]},
                    )
                )
                stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                stack.enter_context(mock.patch.object(dashboard.time, "time", lambda: self.NOW))
                data = dashboard.collect(24, show_all=True)

        opencode = [s for s in data["sessions"] if s["harness"] == "opencode"]
        self.assertEqual(1, len(opencode), f"duplicate rows: {opencode}")
        self.assertEqual(self.NOW, opencode[0]["last_activity"], "kept the staler copy")
        self.assertEqual(1, data["summary"]["active_sessions"])

    def test_a_corrupt_store_never_breaks_the_collector(self) -> None:
        # Every store file replaced with junk: the harness may vanish or report
        # an error, but collection must complete and the others must survive.
        for key, build in HARNESSES:
            with (
                self.subTest(harness=key, fixture=build.__name__),
                tempfile.TemporaryDirectory() as tmp,
            ):
                empty = Path(tmp) / "empty"
                empty.mkdir()
                patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
                store = Path(tmp) / "store"
                patches.update(build(store, self.NOW, self.SID, self.TITLE))
                for path in store.rglob("*"):
                    if path.is_file():
                        path.write_bytes(b"\x00\xff not a valid store at all \xfe")
                with contextlib.ExitStack() as stack:
                    for name, value in patches.items():
                        stack.enter_context(mock.patch.object(dashboard, name, value))
                    stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                    data = dashboard.collect(24, show_all=True)  # must not raise
                self.assertIsInstance(data["sessions"], list)


class HostilePathContractTest(unittest.TestCase):
    """Store paths users really have. Every character here is legal on macOS,
    Linux and Windows; the ones Windows forbids (<>:"/\\|?*) are excluded so the
    same contract runs on all three."""

    NOW = 1_700_000_000.0
    SID = "abcdef12-3456-7890-abcd-ef1234567890"
    HOSTILE = (
        "A [Contractor]",  # glob character class
        "100% pure",  # SQLite URI percent-decoding
        "Ünïcode Café",  # non-ASCII
        "a#b",  # URI fragment
        "with space",
        "it's & more",
        "plus+equals=sign",
        "semi;colon,comma",
        "dollar$at@tilde~",
        "brace{s}paren(s)",
    )

    def test_every_harness_survives_a_hostile_store_path(self) -> None:
        for component in self.HOSTILE:
            for key, build in HARNESSES:
                with self.subTest(path=component, harness=key, fixture=build.__name__):
                    with tempfile.TemporaryDirectory() as tmp:
                        empty = Path(tmp) / "empty"
                        empty.mkdir()
                        patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
                        patches.update(
                            build(Path(tmp) / component / "store", self.NOW, self.SID, "T")
                        )
                        with contextlib.ExitStack() as stack:
                            for name, value in patches.items():
                                stack.enter_context(mock.patch.object(dashboard, name, value))
                            stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                            stack.enter_context(
                                mock.patch.object(dashboard.time, "time", lambda: self.NOW)
                            )
                            data = dashboard.collect(24, show_all=True)
                    found = [s for s in data["sessions"] if s["harness"] == key]
                    self.assertEqual(1, len(found), f"{key} lost its session under {component!r}")
