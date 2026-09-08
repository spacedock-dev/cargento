"""Exercise the shipped detector with controlled Git diff inputs."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
BASH = shutil.which("bash")


@unittest.skipUnless(BASH, "the Actions detector needs bash")
class QualityGateDetectorTest(unittest.TestCase):
    def detect(self, changed: str) -> str:
        workflow = yaml.safe_load((ROOT / ".github/workflows/quality-gate.yml").read_text())
        script = next(
            step["run"]
            for step in workflow["jobs"]["changes"]["steps"]
            if step.get("id") == "detect"
        )
        # Only Git's two read results are fixtures; the actual scan and
        # classification run from the workflow, so changes there reach this test.
        git = """
git() {
  case "$1" in
    merge-base) echo fixture-base ;;
    diff) printf '%s\\n' "$CHANGED" ;;
    *) return 1 ;;
  esac
}
"""
        with tempfile.TemporaryDirectory(prefix="bld-hyg-gate-") as tmp:
            output = Path(tmp) / "output"
            result = subprocess.run(
                [BASH or "bash", "-c", git + script],
                cwd=ROOT,
                env={
                    **os.environ,
                    "EVENT": "pull_request",
                    "BASE_SHA": "base",
                    "HEAD_SHA": "head",
                    "CHANGED": changed,
                    "GITHUB_OUTPUT": str(output),
                },
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            self.assertIn(output.read_text().strip(), result.stdout)
            return output.read_text().strip()

    def test_content_dependencies_request_measurable_jobs(self) -> None:
        for name in (
            "captures/README.md",
            "design-credential-redaction.md",
            "design-reader-state.md",
            "plans/event-driven-session-observation.md",
            "promise-map.md",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.detect("docs/" + name), "code=true")
        for name in ("README.md", "SECURITY.md"):
            with self.subTest(name=name):
                self.assertEqual(self.detect(name), "code=true")

    def test_documents_only_the_citation_checker_reads_request_measurable_jobs(self) -> None:
        """A doc reached only through a runtime citation link is still a dependency.

        Separate from the case above because these arrive by a different route
        and the first arm cannot fail on them: none of its five names is
        cited-only, so dropping the citation derivation from the detector left
        that test green. Measured when the checker landed: nine documents were
        reachable this way and absent from the deny list.

        The names are derived here for the same reason the detector derives
        them. Hard-coding `design-daemon.md` would pass for as long as that one
        citation happens to exist, which is a property of today's comments
        rather than of the rule.
        """
        runtime = Path("cargento/skills/cargento/cargento_runtime")
        cited = {
            match.group(1)
            for path in runtime.rglob("*")
            if path.is_file() and path.suffix in {".py", ".js", ".css", ".html"}
            for match in re.finditer(
                r"\((docs/[^)]+\.md)#", path.read_text(encoding="utf-8", errors="replace")
            )
        }
        self.assertTrue(cited, "no runtime citation links found, so this asserts nothing")
        for name in sorted(cited):
            with self.subTest(name=name):
                self.assertEqual(self.detect(name), "code=true")

    def test_unasserted_prose_skips_measurable_jobs(self) -> None:
        self.assertEqual(self.detect("docs/" + "demo-ai-demo-night.md"), "code=false")

    def test_unknown_diff_fails_open(self) -> None:
        self.assertEqual(self.detect(""), "code=true")
