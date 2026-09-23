"""The parallel runner reaches the same verdict unittest would.

The runner replaces ``python -m unittest discover`` in every CI job that runs a
suite, so a runner that reported OK on a failing suite would turn the whole
quality gate green. Each check builds a small suite in a temporary directory and
runs it through ``run_tests.main`` with real spawned workers.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_tests

PASSING = """
import os
import unittest


class Kept(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.environ["RUNNER_PID_LOG"], "a") as log:
            log.write(f"setup {os.getpid()}\\n")

    def _note(self):
        with open(os.environ["RUNNER_PID_LOG"], "a") as log:
            log.write(f"test {os.getpid()}\\n")

    def test_one(self):
        self._note()

    def test_two(self):
        self._note()

    def test_three(self):
        self._note()


class Other(unittest.TestCase):
    def test_other(self):
        self.assertTrue(True)
"""

MIXED = """
import unittest


class Mixed(unittest.TestCase):
    def test_passes(self):
        self.assertEqual(1, 1)

    def test_fails(self):
        self.assertEqual(1, 2)

    def test_errors(self):
        raise RuntimeError("boom")

    @unittest.skip("not here")
    def test_skipped(self):
        pass
"""


def write_suite(root: Path, modules: dict[str, str]) -> None:
    for name, body in modules.items():
        (root / name).write_text(textwrap.dedent(body), encoding="utf-8")


def run(root: Path, *extra: str) -> tuple[int, str]:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = run_tests.main(["-s", str(root), "-t", str(root), "-j", "2", *extra])
    return code, stderr.getvalue()


class RunnerVerdictTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = self.root / "pids.log"
        self.addCleanup(self.tmp.cleanup)
        # The pid, not multiprocessing.parent_process(): under the runner this
        # test itself runs in a worker, so "has a parent" is true everywhere.
        env = mock_env({"RUNNER_PID_LOG": str(self.log), "RUNNER_PARENT_PID": str(os.getpid())})
        env.__enter__()
        self.addCleanup(env.__exit__, None, None, None)

    def test_a_passing_suite_is_ok_and_keeps_each_class_on_one_worker(self) -> None:
        write_suite(self.root, {"test_passing.py": PASSING})

        code, out = run(self.root)

        self.assertEqual(0, code, out)
        self.assertIn("Ran 4 tests", out)
        self.assertTrue(out.rstrip().endswith("OK"), out)
        lines = self.log.read_text(encoding="utf-8").split()
        pids = set(lines[1::2])
        self.assertEqual(1, lines.count("setup"), "setUpClass must run once for its class")
        self.assertEqual(1, len(pids), "a class was split across workers")

    def test_failures_errors_skips_and_an_import_failure_all_reach_the_verdict(self) -> None:
        write_suite(
            self.root,
            {"test_mixed.py": MIXED, "test_broken.py": "import a_module_that_does_not_exist\n"},
        )

        code, out = run(self.root)

        self.assertEqual(1, code, out)
        self.assertIn("FAIL: test_fails", out)
        self.assertIn("ERROR: test_errors", out)
        self.assertIn("a_module_that_does_not_exist", out)
        self.assertIn("FAILED (failures=1, errors=2, skipped=1)", out)

    def test_a_class_only_the_parent_could_import_is_an_error_not_an_empty_pass(self) -> None:
        # The false green the review reproduced: the worker's discovery lacked
        # the class, ran an empty suite for it, and the verdict was OK.
        write_suite(
            self.root,
            {
                "test_worker_only_fails.py": """
                import os
                import unittest

                if str(os.getpid()) != os.environ["RUNNER_PARENT_PID"]:
                    raise ImportError("only a worker fails to import this")


                class Hidden(unittest.TestCase):
                    def test_fails(self):
                        self.fail("serial unittest reports this")
                """
            },
        )

        code, out = run(self.root)

        self.assertEqual(1, code, out)
        self.assertIn("discovery", out)

    def test_a_class_only_a_worker_could_import_is_an_error_not_skipped(self) -> None:
        write_suite(
            self.root,
            {
                "test_parent_only_fails.py": """
                import os
                import unittest

                if str(os.getpid()) == os.environ["RUNNER_PARENT_PID"]:
                    raise ImportError("only the parent fails to import this")


                class Seen(unittest.TestCase):
                    def test_passes(self):
                        pass
                """
            },
        )

        code, out = run(self.root)

        self.assertEqual(1, code, out)
        self.assertIn("test_parent_only_fails", out)

    def test_discovering_nothing_is_a_failure_not_a_pass(self) -> None:
        # A mistyped -s would otherwise turn a CI job green having run nothing.
        code, out = run(self.root)

        self.assertEqual(1, code, out)
        self.assertIn("Ran 0 tests", out)


def mock_env(values: dict[str, str]) -> contextlib.AbstractContextManager[object]:
    return mock.patch.dict(os.environ, values)


if __name__ == "__main__":
    unittest.main()
