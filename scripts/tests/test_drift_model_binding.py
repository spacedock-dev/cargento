"""Failures and changed prompts cannot silently change a replay cohort."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import drift_replay as dr
import levels_cases as lc

if TYPE_CHECKING:
    from tests.test_drift_replay import _Home, _Session
else:
    from test_drift_replay import _Home, _Session


class AReplayTagKeepsEveryChargedProducer(unittest.TestCase):
    def test_a_charged_failure_still_binds_the_tag_but_remains_retryable(self) -> None:
        with (
            _Session() as session,
            mock.patch.object(dr, "_run_refusal", return_value=""),
            mock.patch.object(dr, "LEDGER_PATH", str(session.home / "spend.json")),
        ):
            home = _Home(session)
            config, *_unused = dr._runtime()
            selected = dr._read_model_config(config, "claude-sonnet-5")
            tag = "producer-bound"
            read_path, _plan = dr._tagged(home.paths, tag)
            ledger = dr.Ledger(dr.LEDGER_PATH)
            done: dict[str, Any] = {}
            self.assertEqual(
                1,
                dr._read_cases(
                    home.body,
                    {**home.paths, "read": read_path},
                    lambda _p, **_k: ("", "failed"),
                    ledger,
                    done,
                    "fixtures",
                    ("realistic",),
                    dry_run=False,
                    say=lambda _m: None,
                    selection=frozenset({f"{home.ids[0]}:realistic"}),
                    runtime_config=selected,
                ),
            )
            self.assertEqual({}, done)
            self.assertEqual(1, ledger.used())
            receipt = ledger.calls()[0]
            self.assertEqual({"key", "at", "read_scope", "producer"}, set(receipt))
            self.assertEqual(dr._read_scope(read_path), receipt["read_scope"])
            self.assertEqual("claude-sonnet-5", receipt["producer"]["selected_model"])
            self.assertNotIn(str(session.home), str(receipt))
            self.assertEqual(
                1,
                dr.read(
                    home=str(session.home),
                    dry_run=True,
                    tag=tag,
                    arms=("realistic",),
                    cases=(home.ids[0],),
                    claude_model="claude-opus-6",
                    say=lambda _m: None,
                ),
            )
            self.assertEqual(
                0,
                dr.read(
                    home=str(session.home),
                    dry_run=True,
                    tag=tag,
                    arms=("realistic",),
                    cases=(home.ids[0],),
                    claude_model="claude-sonnet-5",
                    say=lambda _m: None,
                ),
            )
            self.assertEqual(1, ledger.used())

    def test_charge_rechecks_the_producer_binding_under_the_ledger_lock(self) -> None:
        with _Session() as session:
            config, *_unused = dr._runtime()
            from cargento_runtime import observer  # noqa: PLC0415

            old = observer.claude_reading_provenance(
                dr._read_model_config(config, "claude-sonnet-5")
            )
            new = observer.claude_reading_provenance(dr._read_model_config(config, "claude-opus-6"))
            path = str(session.home / "spend.json")
            first = dr.Ledger(path, binding=("a" * 64, old))
            self.assertTrue(first.charge("first"))
            with self.assertRaises(dr.LedgerError):
                dr.Ledger(path, binding=("a" * 64, new)).charge("another-model")
            self.assertEqual(1, first.used())
            self.assertTrue(dr.Ledger(path, binding=("a" * 64, old)).charge("retry"))
            self.assertTrue(dr.Ledger(path, binding=("b" * 64, new)).charge("another-tag"))
            self.assertEqual(3, first.used())


class ADryPlanActuallyBindsThePrompt(unittest.TestCase):
    def test_changed_plan_prompt_refuses_before_verification_or_charge(self) -> None:
        for change in ("digest", "fixture"):
            with self.subTest(change=change):
                self._changed_plan_prompt(change)

    def _changed_plan_prompt(self, change: str) -> None:
        with (
            _Session() as session,
            mock.patch.object(dr, "_run_refusal", return_value=""),
            mock.patch.object(dr, "LEDGER_PATH", str(session.home / "spend.json")),
        ):
            home = _Home(session)
            kwargs: dict[str, Any] = {
                "home": str(session.home),
                "tag": "prompt-bound",
                "arms": ("realistic",),
                "cases": (home.ids[0],),
                "claude_model": "claude-sonnet-5",
                "say": lambda _m: None,
            }
            self.assertEqual(0, dr.read(**kwargs, dry_run=True))
            _read, plan_path = dr._tagged(home.paths, "prompt-bound")
            plan = lc._load(plan_path)
            if change == "digest":
                next(iter(plan["prompts"].values()))["digest"] = "0" * 64
                lc._write(plan_path, plan)
            else:
                session.log.write_text(
                    session.log.read_text().replace(
                        "Build the importer and nothing else.", "Build a different component."
                    )
                )
            import score_abstention  # noqa: PLC0415
            from cargento_runtime import reading_route  # noqa: PLC0415

            with (
                mock.patch.object(reading_route, "destination", return_value="Anthropic"),
                mock.patch.object(
                    score_abstention,
                    "verify_claude_binary",
                    side_effect=AssertionError("must refuse before launch"),
                ),
            ):
                self.assertEqual(1, dr.read(**kwargs))
            self.assertFalse((session.home / "spend.json").exists())

    def test_a_prompt_change_after_preflight_still_cannot_reach_the_charge(self) -> None:
        with _Session() as session:
            ledger = dr.Ledger(str(session.home / "spend.json"))
            calls: list[str] = []
            expected: dict[str, Any] = {
                "digest": hashlib.sha256(b"planned prompt").hexdigest(),
                "bytes": len("planned prompt"),
            }

            def inner(prompt: str, **_kw: Any) -> tuple[str, str]:
                calls.append(prompt)
                return "{}", "ok"

            model = dr._Charged(
                inner,
                ledger,
                "case",
                expected_prompt=expected,
            )
            with self.assertRaises(dr.LedgerError):
                model("changed prompt", output_cap_bytes=100)
            self.assertEqual([], calls)
            self.assertEqual(0, ledger.used())
            expected["bytes"] += 1
            with self.assertRaises(dr.LedgerError):
                model("planned prompt", output_cap_bytes=100)
            self.assertEqual([], calls)
            self.assertEqual(0, ledger.used())
            expected["bytes"] -= 1
            model("planned prompt", output_cap_bytes=100)
            self.assertEqual(1, ledger.used())
            self.assertEqual(["planned prompt"], calls)

    def test_a_paid_resume_checks_only_pending_prompts_and_does_not_mutate_results(self) -> None:
        with (
            _Session() as session,
            mock.patch.object(dr, "LEDGER_PATH", str(session.home / "spend.json")),
        ):
            home = _Home(session)
            config, *_unused = dr._runtime()
            from cargento_runtime import observer  # noqa: PLC0415

            producer = observer.claude_reading_provenance(config)
            measurements: dict[str, Any] = {}
            ledger = dr.Ledger(dr.LEDGER_PATH)
            dr._read_cases(
                home.body,
                home.paths,
                lc._Spy(),
                ledger,
                {},
                "fixtures",
                ("realistic",),
                dry_run=True,
                say=lambda _m: None,
                prompt_measurements=measurements,
                runtime_config=config,
            )
            first = next(iter(measurements))
            case_id, _, arm = first.rpartition(":")
            done = {case_id: {arm: {"charged": True, "producer": producer}}}
            plan = {
                "cases_digest": lc.digest(home.body),
                "arms": ["realistic"],
                "producer": producer,
                "calls": len(measurements),
                "prompts": measurements,
            }
            self.assertEqual(
                "",
                dr._read_plan_refusal(
                    home.body,
                    home.paths,
                    plan,
                    ledger,
                    done,
                    "fixtures",
                    ("realistic",),
                    selection=[],
                    include_history=False,
                    config=config,
                    producer=producer,
                    dry_run=False,
                ),
            )
            self.assertEqual({case_id: {arm: {"charged": True, "producer": producer}}}, done)
            self.assertEqual(0, ledger.used())

    def test_an_unbound_historical_plan_requires_a_new_tag(self) -> None:
        with _Session() as session, mock.patch.object(dr, "_run_refusal", return_value=""):
            home = _Home(session)
            _read, plan_path = dr._tagged(home.paths, "historical")
            lc._write(plan_path, {"calls": 0})
            self.assertEqual(
                1,
                dr.read(
                    home=str(session.home),
                    dry_run=True,
                    tag="historical",
                    arms=("realistic",),
                    say=lambda _m: None,
                ),
            )
