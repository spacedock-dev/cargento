"""Study measurements refuse old causes, hindsight guesses and worker prompts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

if TYPE_CHECKING:
    from collections.abc import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import drift_study as study
import levels_cases as lc


class EarlyWarningNeedsANewRelevantCause(unittest.TestCase):
    def episode(self) -> dict[str, object]:
        return {
            "start": 100,
            "push": 10000,
            "window_stops": [200, 400],
            "active_events": [100, 200, 400, 10000],
        }

    def test_repeated_old_failure_is_not_an_early_catch(self) -> None:
        self.assertIsNone(
            study.early_catch(
                self.episode(),
                {200: {"level": "high", "cause_at": 50}},
                baseline=50,
                relevant={200: [50]},
            )
        )

    def test_a_new_unrelated_failure_is_not_an_early_catch(self) -> None:
        self.assertIsNone(
            study.early_catch(
                self.episode(), {200: {"level": "high", "cause_at": 150}}, baseline=50, relevant={}
            )
        )

    def test_a_new_relevant_failure_counts_only_when_the_level_is_flagged(self) -> None:
        rows: dict[float, dict[str, Any]] = {
            200: {"level": "not_enough", "cause_at": 150},
            400: {"level": "high", "cause_at": 350},
        }
        got = study.early_catch(
            self.episode(), rows, baseline=50, relevant={200: [150], 400: [350]}
        )
        self.assertEqual({"cut": 400.0, "stops_before_pushback": 0, "active_minutes": 30.0}, got)

    def test_no_baseline_is_not_a_measurement_of_a_new_cause(self) -> None:
        with self.assertRaises(ValueError):
            study.early_catch(self.episode(), {}, baseline="not-measured", relevant={})

    def test_active_time_caps_idle_gaps_at_thirty_minutes(self) -> None:
        self.assertEqual(33.0, study.active_minutes([0, 60, 120, 10000, 10060], 0, 10060))


class APositiveGapMarkNeedsLaterRecordedProof(unittest.TestCase):
    def test_marker_opinion_alone_is_not_positive_proof(self) -> None:
        self.assertFalse(study.positive_gap({"gap": "yes", "proof": []}, cut=100))

    def test_earlier_or_unrelated_receipt_does_not_make_a_positive(self) -> None:
        for at, points in ((90, True), (110, False)):
            self.assertFalse(
                study.positive_gap(
                    {
                        "gap": "yes",
                        "proof": [{"at": at, "kind": "failed-check", "points_to_gap": points}],
                    },
                    cut=100,
                )
            )

    def test_a_later_specific_receipt_can_support_a_positive(self) -> None:
        self.assertTrue(
            study.positive_gap(
                {
                    "gap": "yes",
                    "proof": [{"at": 110, "kind": "person-correction", "points_to_gap": True}],
                },
                cut=100,
            )
        )


class CodexStudyReadsOnlyActualParentMessages(unittest.TestCase):
    def load(self, meta: Mapping[str, object], texts: list[str]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.jsonl"
            rows = [{"type": "session_meta", "payload": meta}]
            rows += [
                {
                    "type": "response_item",
                    "timestamp": "2026-09-01T00:00:00Z",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                    },
                }
                for text in texts
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            return study.codex_messages(path)

    def test_worker_and_exec_logs_cannot_supply_a_persons_goal(self) -> None:
        for meta in (
            {"source": "exec", "thread_source": "user"},
            {"source": "cli", "thread_source": "subagent"},
            {"source": "cli", "thread_source": "user", "agent_path": "worker"},
        ):
            with self.subTest(meta=meta), self.assertRaises(ValueError):
                self.load(meta, ["Build the placeholder importer"])

    def test_injected_instructions_are_not_genuine_requests_or_corrections(self) -> None:
        got = self.load(
            {"source": "cli", "thread_source": "user"},
            [
                "# AGENTS.md instructions for placeholder",
                "<environment_context>meta",
                "<skill_instructions>meta",
                "Build the placeholder importer",
                "Why did you omit the requested output?",
            ],
        )
        self.assertEqual(2, len(got["messages"]))
        self.assertEqual(3, got["injected_excluded"])

    def test_policy_is_not_widened_by_loading_study_messages(self) -> None:
        got = self.load({"source": "vscode", "thread_source": "user"}, ["Build the importer"])
        self.assertFalse(got["qualifies_analyze"])
        self.assertEqual("codex", got["harness"])


class AStudyClosesMarksBeforeProducingOutputs(unittest.TestCase):
    def bundle(self) -> dict[str, object]:
        return {
            "kind": "in-drift",
            "source": "fixtures",
            "cases": [
                {
                    "id": "a" * 16,
                    "sid": "placeholder",
                    "cut": 100,
                    "roles": ["in-drift"],
                    "events": [],
                }
            ],
            "marks": {
                "a" * 16: {
                    "gap": "no",
                    "class": "none",
                    "message_times": [90],
                    "relevant_causes": [],
                }
            },
            "episodes": [],
        }

    def test_import_is_separate_and_requires_every_blind_mark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, home = Path(directory) / "repo", Path(directory) / "home"
            source = Path(directory) / "bundle.json"
            original = home / "drift-replay" / "cases.json"
            original.parent.mkdir(parents=True)
            original.write_text("original frozen cases", encoding="utf-8")
            source.write_text(json.dumps(self.bundle()), encoding="utf-8")
            study.import_study(home, root, "in-drift", source)
            self.assertEqual("original frozen cases", original.read_text(encoding="utf-8"))
            self.assertTrue((root / "docs/drift-replay/study-in-drift-marks-digest.json").exists())
            broken = self.bundle()
            broken["marks"] = {}
            source.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(ValueError):
                study.import_study(home, root, "another", source)

    def test_uncommitted_or_changed_marks_are_refused_before_live(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, home = Path(directory) / "repo", Path(directory) / "home"
            source = Path(directory) / "bundle.json"
            source.write_text(json.dumps(self.bundle()), encoding="utf-8")
            study.import_study(home, root, "in-drift", source)
            with (
                mock.patch.object(lc, "committed_digest", return_value="not committed"),
                self.assertRaises(ValueError),
            ):
                study.load_study(home, root, "in-drift")

    def test_producing_an_output_closes_reimport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, home = Path(directory) / "repo", Path(directory) / "home"
            source = Path(directory) / "bundle.json"
            source.write_text(json.dumps(self.bundle()), encoding="utf-8")
            study.import_study(home, root, "in-drift", source)
            (home / "drift-replay/live-study-in-drift.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                study.import_study(home, root, "in-drift", source)

    def test_a_tag_cannot_escape_the_study_store(self) -> None:
        with self.assertRaises(ValueError):
            study.study_paths(Path("/placeholder"), Path("/placeholder"), "../read")


if __name__ == "__main__":
    unittest.main()
