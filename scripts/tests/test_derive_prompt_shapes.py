"""The prompt-shape derivation script.

Two things are worth testing here and they are not the counts. The counts are the
script's output over whoever's store it is pointed at, and a fixture store can
only prove the arithmetic reaches the right column. What matters is:

  1. **It never prints prompt text.** That is a deliverable constraint, and a
     guard nobody tests is a guard that stops holding the first time a label is
     added. The fixtures below seed distinctive strings and the tests assert the
     whole stdout carries none of them.
  2. **Its `_turn_signal` reimplementation agrees with the real one.** The
     refusal column in `records.py`'s comments is derived from that copy, so a
     copy that drifts publishes a wrong provenance claim.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cargento" / "skills" / "cargento"))

import derive_prompt_shapes as derive
from cargento_runtime import records

# Nothing a real transcript would contain, so a leak is unambiguous. Named for
# what it is rather than for what it stands in for: a variable called
# SECRET_ anything trips ruff's hardcoded-credential rule.
SEEDED_PROMPT = "zzqq operator typed this into the prompt box"


def _claude_record(content: Any, **extra: Any) -> str:
    record: dict[str, Any] = {
        "type": "user",
        "uuid": "u1",
        "message": {"role": "user", "content": content},
    }
    record.update(extra)
    return json.dumps(record)


def _codex_record(role: str, text: str) -> str:
    return json.dumps(
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": "input_text", "text": text}],
            },
        }
    )


def _seed(root: Path) -> tuple[Path, Path]:
    """A two-harness fixture store shaped like the globs the script uses."""
    claude = root / "claude" / "projects" / "-home-me-repo"
    claude.mkdir(parents=True)
    (claude / "session.jsonl").write_text(
        "\n".join(
            [
                _claude_record(SEEDED_PROMPT),
                _claude_record("<task-notification>done</task-notification>"),
                _claude_record("<local-command-caveat>x</local-command-caveat>"),
                _claude_record("[Image: source: /tmp/a.png]"),
                _claude_record("Warmup", isSidechain=True),
                _claude_record("Stop hook feedback: " + SEEDED_PROMPT),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    codex = root / "codex" / "sessions" / "2026" / "08" / "17"
    codex.mkdir(parents=True)
    (codex / "rollout-2026-08-17T02-00-00-abc.jsonl").write_text(
        "\n".join(
            [
                _codex_record("user", SEEDED_PROMPT),
                _codex_record("user", "<recommended_plugins>list</recommended_plugins>"),
                _codex_record("developer", "<permissions>x</permissions>"),
                _codex_record("developer", "<apps_instructions>x</apps_instructions>"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return (root / "claude" / "projects", root / "codex" / "sessions")


@contextmanager
def _temp_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


class OutputTest(unittest.TestCase):
    def _run(self, root: Path) -> str:
        claude_root, codex_root = _seed(root)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = derive.main(["--claude-root", str(claude_root), "--codex-root", str(codex_root)])
        self.assertEqual(0, code)
        return buffer.getvalue()

    def test_no_prompt_text_reaches_stdout(self) -> None:
        # The deliverable constraint. A derivation script reads every prompt the
        # operator ever typed, credentials included, so the one thing it may
        # never do is echo one.
        with _temp_root() as root:
            output = self._run(root)
        self.assertNotIn(SEEDED_PROMPT, output)
        self.assertIn("never prints prompt text", output)

    def test_the_counts_land_in_the_right_columns(self) -> None:
        with _temp_root() as root:
            output = self._run(root)
        # Shape names and totals only; each of these is one seeded record.
        self.assertIn("user-role texts                                      6", output)
        self.assertIn("files scanned                                        1", output)
        # A leading tag is counted as leading; a developer tag that only ever
        # appears contained is counted as contained.
        self.assertRegex(output, r"task-notification\s+1\s+\(contained 1, refused 0\)")
        self.assertRegex(output, r"local-command-caveat\s+1\s+\(contained 1, refused 1\)")
        self.assertRegex(output, r"apps_instructions\s+1\s+\(contained 1")
        self.assertRegex(output, r"Warmup\s+1")

    def test_a_missing_store_is_reported_rather_than_crashed(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = derive.main(
                ["--claude-root", "/nonexistent/a", "--codex-root", "/nonexistent/b"]
            )
        self.assertEqual(0, code)
        self.assertIn("no store at", buffer.getvalue())


class SafeLabelTest(unittest.TestCase):
    def test_a_label_that_could_be_prompt_text_raises(self) -> None:
        # The guard is a whitelist, so anything new has to be added to it
        # deliberately rather than printed because it happened to be short.
        for label in (
            SEEDED_PROMPT,
            "fix the build",
            "",
            "<script>",
            # One long hyphenated token, which is what a prompt looks like when
            # it happens to contain no spaces. The length bound is what rejects
            # it — the character class alone reads it as a tag name.
            "zzqq-operator-typed-this-into-the-prompt-box",
        ):
            with self.subTest(label=label), self.assertRaises(derive.UnsafeLabelError):
                derive._safe_label(label)

    def test_the_length_bound_is_pinned_at_the_boundary(self) -> None:
        # The bound was 40 while the comment justifying it said 21, so a
        # 40-character run reached stdout verbatim and the negative case above
        # (44 characters) proved rejection one class too high to catch it. Both
        # sides of the real edge, so neither can drift again unnoticed.
        longest_real_tag = "subagent_notification"  # 21, the longest in records.py
        self.assertEqual(21, len(longest_real_tag))
        self.assertEqual(longest_real_tag, derive._safe_label(longest_real_tag))

        at_bound = "a" + "b" * 23  # 24 characters: the last one still printable
        self.assertEqual(24, len(at_bound))
        self.assertEqual(at_bound, derive._safe_label(at_bound))

        over_bound = "a" + "b" * 24  # 25, and every longer run with it
        with self.assertRaises(derive.UnsafeLabelError):
            derive._safe_label(over_bound)

    def test_an_over_long_leading_tag_aggregates_rather_than_printing(self) -> None:
        # The other half: a discovered name too long to vouch for must come back
        # as the aggregate label, not as itself.
        body = "<" + "q" * 30 + "> please review this"
        self.assertEqual(derive._OVER_LONG_TAG, derive._leading_tag(body))

    def test_the_three_allowed_classes_pass(self) -> None:
        self.assertEqual("task-notification", derive._safe_label("task-notification"))
        self.assertEqual("files scanned", derive._safe_label("files scanned"))
        self.assertEqual("Warmup", derive._safe_label("Warmup"))


class TurnSignalAgreementTest(unittest.TestCase):
    """The refusal column in `records.py` is only as good as this copy."""

    def test_the_reimplementation_matches_the_real_turn_signal(self) -> None:
        cases: list[dict[str, Any]] = [
            {"type": "user", "message": {"role": "user", "content": "fix the build"}},
            {"type": "user", "isMeta": True, "message": {"role": "user", "content": "x"}},
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}],
                },
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "<local-command-stdout>x"},
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "<local-command-caveat>x"},
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "<task-notification>x"},
            },
            {
                "type": "user",
                "message": {"role": "user", "content": [{"type": "text", "text": "x"}]},
            },
        ]
        for record in cases:
            content = records.message_dict(record).get("content")
            with self.subTest(record=json.dumps(record)[:60]):
                self.assertEqual(
                    records._turn_signal(record, "claude") is None,
                    derive._claude_refuses(record, content),
                )


if __name__ == "__main__":
    unittest.main()
