"""Study measurements refuse old causes, hindsight guesses and worker prompts."""

from __future__ import annotations

import datetime as dt
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

import drift_replay as replay
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

    def test_a_failure_between_baseline_and_episode_is_still_too_early(self) -> None:
        self.assertIsNone(
            study.early_catch(
                self.episode(),
                {200: {"level": "high", "cause_at": 75}},
                baseline=50,
                relevant={200: [75]},
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
    def test_worker_notifications_and_invisible_wrappers_cannot_be_person_turns(self) -> None:
        wrappers = [
            "<subagent_notification>done",
            "<skill>context",
            "<recommended_plugins>context",
            "<user_shell_command>pwd",
            "<turn_aborted>context",
            "<task-notification>done",
            "[Request interrupted by user for tool use]",
            "[external_agent_tool_result] done",
            "\ufeff# AGENTS.md instructions",
            "\u200b<environment_context>context",
            "<permissions>context",
        ]
        got = self.load(
            {"source": "cli", "thread_source": "user"}, [*wrappers, "Build the importer"]
        )
        self.assertEqual(1, len(got["messages"]))
        self.assertEqual(len(wrappers), got["injected_excluded"])

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
                "<skills_instructions>meta",
                "Base directory for this skill: /placeholder",
                "Build the placeholder importer",
                "Why did you omit the requested output?",
            ],
        )
        self.assertEqual(2, len(got["messages"]))
        self.assertEqual(4, got["injected_excluded"])

    def test_policy_is_not_widened_by_loading_study_messages(self) -> None:
        got = self.load({"source": "vscode", "thread_source": "user"}, ["Build the importer"])
        self.assertFalse(got["qualifies_analyze"])
        self.assertEqual("codex", got["harness"])


class AStudyClosesMarksBeforeProducingOutputs(unittest.TestCase):
    def test_cli_import_writes_only_a_separate_cohort_and_count_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            source.write_text(json.dumps(self.bundle()), encoding="utf-8")
            with (
                mock.patch.object(replay, "HOME", str(root / "private")),
                mock.patch.object(replay, "_ROOT", str(root / "repo")),
                mock.patch.object(replay, "_home_refusal", return_value=""),
                mock.patch.object(replay, "mark", return_value=1) as mark,
            ):
                self.assertEqual(0, replay.main(["--study-import", str(source), "--tag", "closed"]))
                mark.assert_not_called()
            paths = study.study_paths(root / "private", root / "repo", "closed")
            public = json.loads(paths["digest"].read_text(encoding="utf-8"))
            self.assertEqual(1, public["cases"])
            self.assertNotIn("placeholder", json.dumps(public))
            self.assertFalse((root / "private/drift-replay/cases.json").exists())

    def test_malformed_cohorts_refuse_before_writing_outputs(self) -> None:
        for fault in (
            "outside-mark",
            "missing-sid",
            "bad-before",
            "future-before",
            "duplicate-stop",
            "message-times",
            "proof",
            "duplicate-episode",
        ):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                body: Any = self.bundle()
                body["cases"][0]["roles"] = ["outside-span"]
                body["cases"].append(
                    {
                        "id": "c" * 16,
                        "sid": "placeholder",
                        "cut": 150,
                        "roles": ["in-drift"],
                        "session_key": "b" * 16,
                    }
                )
                body["marks"]["c" * 16] = {
                    "gap": "yes",
                    "class": "defect",
                    "message_times": [140],
                    "proof": [],
                }
                episode = {
                    "id": "d" * 16,
                    "sid": "placeholder",
                    "start": 110,
                    "push": 200,
                    "before": 100,
                    "window_stops": [150],
                    "active_events": [110, 150, 200],
                }
                body["episodes"] = [episode]
                if fault == "outside-mark":
                    body["marks"]["a" * 16] = {}
                elif fault == "missing-sid":
                    episode.pop("sid")
                    episode["before"] = None
                    episode["window_stops"] = []
                elif fault == "bad-before":
                    episode["before"] = "x"
                elif fault == "future-before":
                    episode["before"] = 150
                elif fault == "duplicate-stop":
                    episode["window_stops"] = [150, 150]
                elif fault == "message-times":
                    body["marks"]["a" * 16]["message_times"] = 42
                elif fault == "proof":
                    body["marks"]["c" * 16]["proof"] = 42
                elif fault == "duplicate-episode":
                    body["episodes"].append(dict(episode))
                source = root / "source.json"
                source.write_text(json.dumps(body), encoding="utf-8")
                with self.subTest(fault=fault), self.assertRaises(ValueError):
                    study.import_study(root / "home", root, "closed", source)

    def bundle(self) -> dict[str, object]:
        return {
            "kind": "in-drift",
            "source": "fixtures",
            "cases": [
                {
                    "id": "a" * 16,
                    "sid": "placeholder",
                    "cut": 100,
                    "session_key": "b" * 16,
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

    def test_an_exposure_with_a_nonidentity_refuses_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body: Any = self.bundle()
            body["kind"] = "gap-truth"
            body["exposures"] = [{"id": [], "arm": "current"}]
            source = root / "source.json"
            source.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaises(ValueError):
                study.import_study(root / "home", root, "closed", source)

    def test_public_session_keys_and_future_cause_marks_are_refused(self) -> None:
        for change in ("session", "future", "extra"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                body: Any = self.bundle()
                if change == "session":
                    body["cases"][0]["session_key"] = "private-session-name"
                elif change == "future":
                    body["marks"]["a" * 16]["relevant_causes"] = [101]
                else:
                    body["marks"]["c" * 16] = body["marks"]["a" * 16]
                source = root / "source.json"
                source.write_text(json.dumps(body), encoding="utf-8")
                with self.subTest(change=change), self.assertRaises(ValueError):
                    study.import_study(root / "home", root, "closed", source)


class StudyOutputsUseTheirOwnFrozenCohort(unittest.TestCase):
    def test_a_missing_study_tag_never_reaches_the_historical_live_runner(self) -> None:
        with (
            mock.patch.object(replay, "_home_refusal", return_value=""),
            mock.patch.object(replay, "live", return_value=0) as live,
        ):
            self.assertEqual(1, replay.main(["--study-live"]))
            live.assert_not_called()

    def test_empty_import_does_not_open_the_historical_marker(self) -> None:
        for flag in ("--study-import", "--codex-study"):
            with (
                mock.patch.object(replay, "_home_refusal", return_value=""),
                mock.patch.object(replay, "HOME", "/placeholder-home"),
                mock.patch.object(replay, "mark") as mark,
            ):
                self.assertEqual(1, replay.main([flag, "", "--tag", "study"]))
                mark.assert_not_called()

    def test_cli_forwards_the_selectors_that_live_must_refuse(self) -> None:
        with (
            mock.patch.object(replay, "_home_refusal", return_value=""),
            mock.patch.object(replay, "live", return_value=1) as live,
        ):
            self.assertEqual(
                1,
                replay.main(
                    [
                        "--study-live",
                        "--tag",
                        "study",
                        "--source",
                        "original",
                        "--counterfactual-read",
                        "base",
                    ]
                ),
            )
            self.assertEqual("original", live.call_args.kwargs["source"])
            self.assertEqual("base", live.call_args.kwargs["counterfactual_read"])

    def test_a_refused_stop_does_not_erase_a_measured_baseline(self) -> None:
        body = {
            "cases": [
                {
                    "id": "a" * 16,
                    "sid": "private",
                    "cut": 50,
                    "session_key": "b" * 16,
                    "roles": ["outside-span"],
                },
                {
                    "id": "c" * 16,
                    "sid": "private",
                    "cut": 200,
                    "session_key": "b" * 16,
                    "roles": ["in-drift"],
                },
            ],
            "marks": {},
            "episodes": [
                {
                    "id": "d" * 16,
                    "sid": "private",
                    "start": 100,
                    "push": 300,
                    "before": 50,
                    "window_stops": [200],
                    "active_events": [],
                }
            ],
        }
        got = study.score_in_drift(
            body, {"a" * 16: {"arms": {"realistic": {"level": "low", "cause_at": None}}}}
        )
        self.assertTrue(got["episodes"][0]["baseline_measured"])
        self.assertFalse(got["episodes"][0]["window_measured"])

    def test_a_positive_early_catch_exports_the_salted_cut_not_its_timestamp(self) -> None:
        body = {
            "cases": [
                {
                    "id": "a" * 16,
                    "sid": "private",
                    "cut": 50,
                    "session_key": "b" * 16,
                    "roles": ["outside-span"],
                },
                {
                    "id": "c" * 16,
                    "sid": "private",
                    "cut": 200,
                    "session_key": "b" * 16,
                    "roles": ["in-drift"],
                },
            ],
            "marks": {"c" * 16: {"gap": "yes", "class": "defect", "relevant_causes": [150]}},
            "episodes": [
                {
                    "id": "d" * 16,
                    "sid": "private",
                    "start": 100,
                    "push": 300,
                    "before": 50,
                    "window_stops": [200],
                    "active_events": [100, 200, 300],
                }
            ],
        }
        live = {
            "a" * 16: {"arms": {"realistic": {"level": "low", "cause_at": None}}},
            "c" * 16: {"arms": {"realistic": {"level": "high", "cause_at": 150}}},
        }
        got = study.score_in_drift(body, live)
        self.assertEqual(
            {"case": "c" * 16, "stops_before_pushback": 0, "active_minutes": 100 / 60},
            got["episodes"][0]["early_catch"],
        )
        self.assertNotIn("cut", got["episodes"][0]["early_catch"])

    def test_live_routes_only_the_committed_study_and_refuses_counterfactuals(self) -> None:
        with mock.patch.object(study, "load_study", side_effect=ValueError("not committed")):
            self.assertEqual(
                1, replay.live(home="/placeholder", study_tag="in-drift", say=lambda _: None)
            )
        with mock.patch.object(study, "load_study") as load:
            self.assertEqual(
                1,
                replay.live(
                    home="/placeholder",
                    study_tag="in-drift",
                    counterfactual_read="base",
                    say=lambda _: None,
                ),
            )
            load.assert_not_called()

    def test_outside_span_counts_do_not_claim_false_alarms(self) -> None:
        body = {
            "cases": [
                {
                    "id": "a" * 16,
                    "sid": "private",
                    "cut": 100,
                    "session_key": "b" * 16,
                    "roles": ["outside-span"],
                }
            ],
            "marks": {},
            "episodes": [],
        }
        summary = study.score_in_drift(
            body, {"a" * 16: {"arms": {"realistic": {"level": "high", "cause_at": 50}}}}
        )
        self.assertEqual({"cuts": 1, "flagged": 1}, summary["outside_annotated_spans"]["b" * 16])
        self.assertNotIn("false_alarms", summary)
        self.assertNotIn("private", json.dumps(summary))

    def test_missing_live_cut_is_a_refusal_not_an_absent_flag(self) -> None:
        body = {
            "cases": [
                {
                    "id": "a" * 16,
                    "sid": "private",
                    "cut": 100,
                    "session_key": "b" * 16,
                    "roles": ["outside-span"],
                }
            ],
            "marks": {},
            "episodes": [],
        }
        summary = study.score_in_drift(body, {})
        self.assertEqual(1, summary["refused_cuts"])
        self.assertEqual({}, summary["outside_annotated_spans"])

    def test_gap_truth_counts_each_exposure_without_promoting_opinion(self) -> None:
        key = "a" * 16
        body = {
            "cases": [{"id": key, "cut": 100}],
            "marks": {key: {"gap": "yes", "class": "defect", "proof": []}},
            "exposures": [{"id": key, "arm": "current"}, {"id": key, "arm": "adopted"}],
        }
        got = study.score_gap_truth(body)
        self.assertEqual(1, got["unique"]["unproved-positive"])
        self.assertEqual(
            {"adopted": {"unproved-positive": 1}, "current": {"unproved-positive": 1}}, got["arms"]
        )

    def test_cli_study_modes_are_exclusive_and_cannot_fall_through_to_marking(self) -> None:
        with (
            mock.patch.object(replay, "_home_refusal", return_value=""),
            mock.patch.object(replay, "_study_mode", return_value=0) as run,
        ):
            self.assertEqual(0, replay.main(["--study-score", "--tag", "in-drift"]))
            run.assert_called_once()
        with self.assertRaises(SystemExit):
            replay.main(["--study-score", "--read", "--tag", "in-drift"])

    def test_another_cohort_cannot_supply_the_live_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = study.study_paths(root / "home", root, "closed")
            paths["live"].parent.mkdir(parents=True)
            paths["live"].write_text(
                json.dumps({"cases": {}, "study_digest": "another"}), encoding="utf-8"
            )
            with (
                mock.patch.object(study, "load_study", return_value={"kind": "in-drift"}),
                self.assertRaises(ValueError),
            ):
                study.score_study(root / "home", root, "closed")


class AStoredCodexStudyNeedsAnActualCorrection(unittest.TestCase):
    def test_actual_loader_rejects_a_worker_notification_as_the_correction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "parent.jsonl"
            rows: list[dict[str, Any]] = [
                {"type": "session_meta", "payload": {"source": "cli", "thread_source": "user"}}
            ]
            for minute, role, text in (
                (1, "user", "Build the importer"),
                (2, "assistant", "I stopped before writing it"),
                (3, "user", "<subagent_notification>Why did you stop?</subagent_notification>"),
            ):
                rows.append(
                    {
                        "type": "response_item",
                        "timestamp": f"2026-09-01T00:0{minute}:00Z",
                        "payload": {
                            "type": "message",
                            "role": role,
                            "content": [
                                {
                                    "type": "input_text" if role == "user" else "output_text",
                                    "text": text,
                                }
                            ],
                        },
                    }
                )
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            def at(minute: int) -> float:
                return dt.datetime(2026, 9, 1, 0, minute, tzinfo=dt.UTC).timestamp()

            spec = root / "spec.json"
            spec.write_text(
                json.dumps(
                    {
                        "source": str(path),
                        "annotation": {
                            "id": "a" * 16,
                            "requested_at": at(1),
                            "gap_at": at(2),
                            "correction_at": at(3),
                            "gap": "yes",
                            "class": "scope-or-plan",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                study.import_codex(root / "home", root, "worker", spec, lambda value: value)

    def test_injected_correction_cannot_complete_the_episode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spec.json"
            source.write_text(
                json.dumps(
                    {
                        "source": "placeholder",
                        "annotation": {
                            "id": "a" * 16,
                            "requested_at": 100,
                            "gap_at": 200,
                            "correction_at": 300,
                            "gap": "yes",
                            "class": "scope-or-plan",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    study,
                    "codex_messages",
                    return_value={
                        "messages": [{"role": "you", "at": 100}, {"role": "agent", "at": 200}]
                    },
                ),
                self.assertRaises(ValueError),
            ):
                study.import_codex(root / "home", root, "codex", source, lambda value: value)

    def test_private_words_are_masked_and_public_output_has_only_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spec.json"
            source.write_text(
                json.dumps(
                    {
                        "source": "placeholder",
                        "annotation": {
                            "id": "a" * 16,
                            "requested_at": 100,
                            "gap_at": 200,
                            "correction_at": 300,
                            "gap": "yes",
                            "class": "scope-or-plan",
                            "reason": "private-words",
                        },
                    }
                ),
                encoding="utf-8",
            )
            body = {
                "qualifies_analyze": False,
                "injected_excluded": 2,
                "messages": [
                    {"role": role, "at": at, "text": "private-words"}
                    for role, at in (("you", 100), ("agent", 200), ("you", 300))
                ],
            }
            with mock.patch.object(study, "codex_messages", return_value=body):
                result = study.import_codex(
                    root / "home",
                    root,
                    "codex",
                    source,
                    lambda value: value.replace("private-words", "[masked]"),
                )
            private = study.study_paths(root / "home", root, "codex")["cohort"].read_text(
                encoding="utf-8"
            )
            self.assertNotIn("private-words", private)
            self.assertNotIn("[masked]", json.dumps(result))
            self.assertFalse(result["qualifies_analyze"])
            with self.assertRaises(ValueError):
                study.import_codex(root / "home", root, "codex", source, lambda value: value)


if __name__ == "__main__":
    unittest.main()
