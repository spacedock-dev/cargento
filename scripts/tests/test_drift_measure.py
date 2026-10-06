"""The replay preserves baseline and counterfactual meaning and keeps correction text private."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analyze_campaign as campaign_guard
import drift_replay as dr

if TYPE_CHECKING:
    from tests.test_drift_replay import SID, _at, _Home, _Session

    from tests import test_drift_replay as replay_tests
else:
    # unittest discovery loads this fixture module at the test-directory top level.
    import test_drift_replay as replay_tests
    from test_drift_replay import SID, _at, _Home, _Session


class TheReplayKeepsItsBaselineAndText(unittest.TestCase):
    def setUp(self) -> None:
        """legacy_no_campaign: these fixtures exercise the original replay allowance."""
        self.enterContext(mock.patch.object(campaign_guard, "active_campaign", return_value=None))

    def test_a_time_match_is_named_flag_after_start(self) -> None:
        self.assertEqual(
            "flag-after-start",
            dr._live_bin(
                {"level": "high", "cause_at": 40},
                drifted=True,
                start=30,
            ),
        )

    def test_legacy_fact_collection_retains_distinct_rows_with_the_same_handle(self) -> None:
        context = mock.Mock()
        context.claude_tool_reports.return_value = ([{"kind": "check"}, {"kind": "check"}], {})
        context._semantic_fact_from_event.side_effect = [
            {"fact_id": "same", "result": "failed"},
            {"fact_id": "same", "result": "passed"},
        ]
        context.frozen_claude_user_messages.return_value = ([], [])
        context.frozen_claude_agent_messages.return_value = ([], [])
        facts, _press = dr.facts_at(mock.Mock(), context, "unused", SID, _at(10))
        self.assertEqual(["failed", "passed"], [fact["result"] for fact in facts])

    def test_unsettled_direction_shows_question_without_a_correction(self) -> None:
        config, context, _live, correction, _reading = dr._runtime()
        with _Session() as session:
            home = _Home(session)
            case = home.body["cases"][-1]
            facts, _press = dr.facts_at(config, context, str(session.log), SID, case["cut"])
            intent = dr.Intent("realistic", "Change only the parser", _at(0))
            result = dr._steer(correction, dr._row(SID, intent, case["cut"]), facts, intent.at)
            self.assertFalse(result["offered"])
            self.assertEqual("question", result["page_state"])
            self.assertEqual("", result["text"])
            self.assertNotIn("later-direction", result["kinds"])

    def test_live_tag_preserves_earlier_output_and_names_its_counterfactual(self) -> None:
        with _Session() as session, mock.patch.object(dr, "_run_refusal", return_value=""):
            home = _Home(session)
            sentinel = '{"baseline":"preserved"}'
            Path(home.paths["live"]).write_text(sentinel)
            self.assertEqual(
                0, dr.live(home=str(session.home), tag="baseline", say=lambda _m: None)
            )
            self.assertEqual(sentinel, Path(home.paths["live"]).read_text())
            tagged = Path(home.paths["dir"]) / "live-baseline.json"
            body = json.loads(tagged.read_text())
            self.assertEqual("without-analysis", body["mode"])
            self.assertEqual("tail-v1", body["facts_version"])
            self.assertEqual(len(home.body["cases"]), len(body["cases"]))
            self.assertTrue(all(case.get("arms") for case in body["cases"].values()))

    def test_counterfactual_needs_a_tag_and_a_safe_read_name(self) -> None:
        with _Session() as session, mock.patch.object(dr, "_run_refusal", return_value=""):
            _Home(session)
            for tag, read in (("", "base"), ("valid", "../../read")):
                self.assertEqual(
                    1,
                    dr.live(
                        home=str(session.home),
                        tag=tag,
                        counterfactual_read=read,
                        say=lambda _m: None,
                    ),
                )

    def test_missing_counterfactual_reads_are_refused_not_treated_as_keep(self) -> None:
        with _Session() as session, mock.patch.object(dr, "_run_refusal", return_value=""):
            home = _Home(session)
            self.assertEqual(
                1,
                dr.live(
                    home=str(session.home),
                    tag="missing",
                    counterfactual_read="absent",
                    say=lambda _m: None,
                ),
            )
            self.assertFalse((Path(home.paths["dir"]) / "live-missing.json").exists())

    def test_history_age_and_cap_are_counted_separately_after_coalescing(self) -> None:
        config, context, _live, _correction, _reading = dr._runtime()
        from cargento_runtime import semantic_history  # noqa: PLC0415

        cut = 200_000
        candidates = [
            {
                "event_id": str(i),
                "event_type": "goal_shift",
                "source_identity": "one",
                "at": cut - (100_000 if i == 1 else i),
                "fact": {"fact_id": str(i)},
            }
            for i in range(6)
        ]
        with (
            mock.patch.object(context, "_semantic_history_source_events", return_value=[]),
            mock.patch.object(context, "_semantic_model", return_value={"facts": candidates}),
            mock.patch.object(semantic_history, "_event_from_fact", side_effect=lambda f, _r: f),
            mock.patch.object(semantic_history, "MAX_EVENTS_PER_PROJECT", 4),
        ):
            facts, counts = dr._history_at(config, context, "unused", SID, cut)
        self.assertEqual(2, counts["cap_pruned"])
        # The oldest event was removed by the cap, not the independent age bound.
        self.assertEqual(0, counts["age_pruned"])
        self.assertEqual(4, len(facts))
        with (
            mock.patch.object(context, "_semantic_history_source_events", return_value=[]),
            mock.patch.object(context, "_semantic_model", return_value={"facts": candidates}),
            mock.patch.object(semantic_history, "_event_from_fact", side_effect=lambda f, _r: f),
        ):
            facts, counts = dr._history_at(config, context, "unused", SID, cut)
        self.assertEqual(0, counts["cap_pruned"])
        self.assertEqual(1, counts["age_pruned"])
        self.assertEqual(5, len(facts))

    def test_stored_reads_keep_raw_reply_and_original_arm_definition(self) -> None:
        charged = dr._Charged(
            lambda _p, **_kw: ('{"goal":{"result":"consistent"}}', "ok"), None, "synthetic"
        )
        charged("frozen prompt", output_cap_bytes=10_000)
        self.assertEqual('{"goal":{"result":"consistent"}}', charged.raw)
        self.assertEqual(hashlib.sha256(b"frozen prompt").hexdigest(), charged.prompt_digest)
        raw = '{"goal":{"result":"unverifiable","cites":[],"detail":""}}'
        _calls, _charges, done, _said = replay_tests.UnusableCallsStopTheReplay().run_batch(
            [(raw, "ok")]
        )
        entry = next(iter(next(iter(done.values())).values()))
        self.assertEqual(raw, entry["raw_verdict"])
        self.assertEqual("ok", entry["model_status"])
        self.assertEqual("tail-v1", entry["facts_version"])
        self.assertIn("window_start", entry["intent"])
        self.assertRegex(entry["prompt_digest"], r"^[a-f0-9]{64}$")

    def test_history_choice_and_prompt_digests_are_part_of_a_tagged_plan(self) -> None:
        with _Session() as session, mock.patch.object(dr, "_run_refusal", return_value=""):
            home = _Home(session)
            with mock.patch.object(dr, "LEDGER_PATH", str(session.home / "spend.json")):
                self.assertEqual(
                    0,
                    dr.read(
                        home=str(session.home),
                        dry_run=True,
                        tag="history",
                        arms=("adopted",),
                        include_history=True,
                        say=lambda _m: None,
                    ),
                )
                plan = json.loads((Path(home.paths["dir"]) / "plan-history.json").read_text())
                self.assertTrue(plan["include_history"])
                self.assertEqual(plan["calls"], len(plan["prompts"]))
                self.assertTrue(all(p["bytes"] > 0 for p in plan["prompts"].values()))
                import score_abstention  # noqa: PLC0415
                from cargento_runtime import reading_route  # noqa: PLC0415

                with (
                    mock.patch.object(
                        reading_route, "destination", return_value=reading_route.VENDORS["claude"]
                    ),
                    mock.patch.object(
                        score_abstention,
                        "verify_claude_binary",
                        side_effect=AssertionError("A model-free test cannot start a CLI"),
                    ),
                ):
                    self.assertEqual(
                        1,
                        dr.read(
                            home=str(session.home),
                            tag="history",
                            arms=("adopted",),
                            include_history=False,
                            say=lambda _m: None,
                        ),
                    )
                self.assertFalse((session.home / "spend.json").exists())

    def test_an_arm_with_every_goal_source_missing_is_not_scored(self) -> None:
        readings = {
            "one": {"adopted": {"goal_source": {"needed": 1, "found": 0}}},
            "two": {"adopted": {"goal_source": {"needed": 1, "found": 0}}},
        }
        self.assertEqual({"adopted"}, dr._fallback_arms(readings))
        readings["two"]["adopted"]["goal_source"]["found"] = 1
        self.assertEqual(set(), dr._fallback_arms(readings))
        self.assertEqual(set(), dr._fallback_arms({"old": {"adopted": {}}}))

    def test_unclear_final_marks_still_contribute_to_the_blind_column(self) -> None:
        tables = dr._ScoreTables()
        tables.record(
            {"roles": []},
            "current",
            {"drift": "unclear"},
            {"live": "false-alarm"},
            {"live|drift": "flag-after-start"},
            "salted",
        )
        self.assertEqual({}, tables.counts)
        self.assertEqual({"current|live|drift": {"flag-after-start": 1}}, tables.blind)

    def test_saved_arm_window_is_not_reconstructed_from_a_newer_draft(self) -> None:
        generated = [dr.Intent("current", "New goal", 50, ("New line",), window_start=40)]
        stored = {
            "current": {
                "intent": {
                    "n": 1,
                    "goal": "Old goal",
                    "at": 10,
                    "window_start": 3,
                    "lines": ["Old line"],
                }
            }
        }
        found = dr._reading_intents(generated, stored)[0]
        self.assertEqual("Old goal", found.goal)
        self.assertEqual(3, found.window_start)
        self.assertEqual(("Old line",), found.lines)

    def test_live_counterfactual_uses_the_saved_window_after_a_draft_changes(self) -> None:
        with _Session() as session, mock.patch.object(dr, "_run_refusal", return_value=""):
            home = _Home(session)
            saved = {"goal": "Old goal", "at": _at(0), "window_start": _at(0), "lines": []}
            entries = {case["id"]: {"current": {"intent": saved}} for case in home.body["cases"]}
            Path(home.paths["read"]).write_text(json.dumps({"cases": entries}))
            changed = dr.Intent("current", "New goal", _at(5), window_start=_at(5))
            with (
                mock.patch.object(dr, "intents", return_value=[changed]),
                mock.patch.object(dr, "_live_measured", return_value=({}, {})) as measured,
            ):
                self.assertEqual(
                    0,
                    dr.live(
                        home=str(session.home),
                        tag="saved",
                        counterfactual_read="base",
                        say=lambda _m: None,
                    ),
                )
            self.assertTrue(measured.call_args_list)
            self.assertTrue(
                all(call.args[5].goal == "Old goal" for call in measured.call_args_list)
            )

    def test_goal_source_refusal_also_applies_to_the_blind_outcomes(self) -> None:
        with _Session() as session:
            home = _Home(session)
            case = home.body["cases"][0]
            tables = dr._ScoreTables()
            marks = {case["id"]: {"final": {"drift": "no-drift"}, "blind": {"drift": "drift"}}}
            dr._score_case(
                case,
                marks,
                {case["id"]: {"arms": {"adopted": {}}}},
                {},
                {},
                lambda _case, _arm: True,
                tables,
                salt="synthetic",
                source="fixtures",
                fallback_arms={"adopted"},
            )
            self.assertEqual({"refused-goal-source": 1}, tables.blind["adopted|analyze|drift"])

    def test_folder_diagnostics_use_the_exact_evidence_the_live_level_read(self) -> None:
        dr._runtime()
        from cargento_runtime import levels  # noqa: PLC0415

        evidence = levels.Evidence(
            (
                {"fact_id": "inside", "subject": "write", "result": "written", "summary": "src/a"},
                {
                    "fact_id": "outside",
                    "subject": "write",
                    "result": "written",
                    "summary": "other/a",
                },
            ),
            {"written_paths": 4, "outside_paths": 1},
            0,
        )
        intent = dr.Intent("realistic", "Change only src/", 1)
        engine = mock.Mock()
        engine.for_session.side_effect = lambda *_a, **_kw: {
            "level": levels.live_level(evidence, levels.Intent(True, intent.goal, ())).level
        }
        original = levels.live_level
        _level, measured = dr._live_measured(engine, mock.Mock(), {}, "unused", [], intent, 5, {})
        self.assertEqual(["src"], measured["folders"])
        self.assertEqual(4, measured["outside"])
        self.assertEqual(5, measured["total"])
        self.assertEqual(2, measured["unlisted"])
        self.assertEqual(1, measured["beyond_cwd"])
        self.assertIs(original, levels.live_level)
