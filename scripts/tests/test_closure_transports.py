"""Production transport seams use synthetic providers and temporary account ledgers."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import types
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cargento/skills/cargento"))

import abstention_ledger
import analyze_campaign
import drift_replay
import live_analyze_campaign
import mark_abstention
import score_abstention

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig

    from tests import test_analyze_campaign as campaign_cases
    from tests import test_mark_full_production as source_cases
else:
    import test_analyze_campaign as campaign_cases
    import test_mark_full_production as source_cases


class SyntheticDestinationIsolation(unittest.TestCase):
    def test_native_windows_live_wrapper_never_reserves_or_calls_the_executor(self) -> None:
        from cargento_runtime import reading_route  # noqa: PLC0415 - actual native route

        inner = mock.Mock(return_value=("synthetic reply", "ok"))
        observer = types.SimpleNamespace(
            __file__="synthetic-observer.py",
            claude_exec=inner,
            claude_reading_provenance=mock.Mock(return_value={"model": "declared-model"}),
        )
        campaign = mock.Mock()
        verified = types.SimpleNamespace(path="synthetic-cli", identity=("synthetic", "a" * 64))
        with (
            mock.patch.object(platform, "system", return_value="Windows"),
            mock.patch.object(analyze_campaign, "Campaign", return_value=campaign),
            mock.patch.object(score_abstention, "PinnedClaude", return_value=lambda _: True),
            self.assertRaises(abstention_ledger.LedgerError),
        ):
            self.assertEqual("", reading_route.destination("claude"))
            wrapper = live_analyze_campaign.LiveTransport(observer, verified=verified)
            observer.claude_exec = wrapper
            wrapper("declared-model", "synthetic prompt", output_cap_bytes=1024)
        campaign.reserve.assert_not_called()
        campaign.request_slot.assert_not_called()
        observer.claude_reading_provenance.assert_not_called()
        inner.assert_not_called()

    def test_native_windows_destination_refuses_before_provenance_or_reservation(self) -> None:
        from cargento_runtime import reading_route  # noqa: PLC0415 - actual native route

        observer = mock.Mock()
        observer.claude_reading_provenance.return_value = {"model": "declared-model"}
        verified = types.SimpleNamespace(
            shown="synthetic-cli",
            identity=("synthetic", "a" * 64),
            version="synthetic-version",
            signature="synthetic-signature",
        )
        with (
            mock.patch.object(platform, "system", return_value="Windows"),
            mock.patch.object(analyze_campaign, "Campaign") as campaign,
            mock.patch.object(score_abstention, "argv_digest", return_value="a" * 64) as argv,
            self.assertRaises(abstention_ledger.LedgerError),
        ):
            self.assertEqual("", reading_route.destination("claude"))
            analyze_campaign.verified_transport_binding("declared-model", verified, observer)
        observer.claude_reading_provenance.assert_not_called()
        observer.claude_exec.assert_not_called()
        argv.assert_not_called()
        campaign.assert_not_called()

    def test_fake_transport_runs_on_windows_without_admitting_the_native_route(self) -> None:
        from cargento_runtime import reading_route  # noqa: PLC0415 - native refusal outside fixture

        with mock.patch.object(platform, "system", return_value="Windows"):
            self.assertEqual("", reading_route.destination("claude"))
            fixture = ProductionTransport(
                "test_actual_executor_is_charged_first_and_pending_until_native_review"
            )
            result = unittest.TestResult()
            fixture.run(result)
            self.assertEqual([], result.errors)
            self.assertEqual([], result.failures)
            self.assertEqual("", reading_route.destination("claude"))


class ProductionTransport(unittest.TestCase):
    module: Any
    root: Path
    state: Path
    manifest: Path
    replay: Path
    qualification: Path
    slots: dict[str, list[str]]
    body: dict[str, Any]

    def setUp(self) -> None:
        # This fixture owns a fake Anthropic executor, not native OS admission.
        self.enterContext(
            mock.patch("cargento_runtime.reading_route.destination", return_value="Anthropic")
        )
        campaign_cases.CampaignReservations.setUp(cast("campaign_cases.CampaignReservations", self))

    if TYPE_CHECKING:
        # Runtime borrows helpers over the explicitly declared fixture attributes.
        def activate(self) -> None: ...

        def fill_lane(self, lane: str, *, accept: bool = True) -> None: ...

        def campaign(self) -> analyze_campaign.Campaign: ...
    else:
        activate = campaign_cases.CampaignReservations.activate
        fill_lane = campaign_cases.CampaignReservations.fill_lane
        campaign = campaign_cases.CampaignReservations.campaign
    sha = staticmethod(campaign_cases.CampaignReservations.sha)
    charge = campaign_cases.CampaignReservations.charge

    def live(
        self, status: str = "ok"
    ) -> tuple[types.SimpleNamespace, live_analyze_campaign.LiveTransport]:
        self.body["batches"]["live"] = [[slot] for slot in self.slots["live"]]
        source = self.root / "runtime"
        source.mkdir()
        (source / "observer.py").write_text("# synthetic provider bytes\n")
        self.inner = mock.Mock(return_value=("synthetic reply", status))
        observer = types.SimpleNamespace(
            __file__=str(source / "observer.py"),
            claude_exec=self.inner,
            claude_reading_provenance=lambda cfg: {"model": cfg},
        )
        self.binary = self.root / "claude"
        self.binary.write_bytes(b"synthetic verified CLI")
        self.verified = score_abstention.VerifiedClaude(
            "synthetic-cli",
            "synthetic-version",
            str(self.binary),
            "synthetic-signature",
            score_abstention.file_identity(str(self.binary)),
        )
        argv = mock.patch.object(score_abstention, "argv_digest", return_value="a" * 64)
        argv.start()
        self.addCleanup(argv.stop)
        binding = analyze_campaign.verified_transport_binding(
            "declared-model", self.verified, observer
        )
        request = analyze_campaign.request_digest(
            "synthetic prompt",
            binding,
            analyze_campaign.runtime_source_digest(source),
            1024,
        )
        self.body["requests"]["live"][self.slots["live"][0]] = request
        self.activate()
        campaign_cases.seed_predecessor(self.campaign(), "replay")
        campaign_cases.seed_predecessor(self.campaign(), "qualification")
        wrapper = live_analyze_campaign.LiveTransport(observer, verified=self.verified)
        observer.claude_exec = wrapper
        return observer, wrapper

    def test_actual_executor_is_charged_first_and_pending_until_native_review(self) -> None:
        observer, wrapper = self.live()

        def actual(_config: Any, _prompt: str, **_kwargs: Any) -> tuple[str, str]:
            calls = [c for c in json.loads(self.state.read_text())["calls"] if c["lane"] == "live"]
            self.assertEqual(1, len(calls))
            self.assertEqual("charged", calls[0]["status"])
            return "synthetic reply", "ok"

        self.inner.side_effect = actual
        self.assertEqual(
            ("synthetic reply", "ok"),
            wrapper("declared-model", "synthetic prompt", output_cap_bytes=1024),
        )
        with self.assertRaises(abstention_ledger.LedgerError):
            observer.claude_exec("declared-model", "synthetic prompt", output_cap_bytes=1024)
        self.assertEqual(1, self.inner.call_count)

    def failed_attempt(self, status: str) -> None:
        _observer, wrapper = self.live(status)
        wrapper("declared-model", "synthetic prompt", output_cap_bytes=1024)
        self.assertEqual("unusable", json.loads(self.state.read_text())["calls"][-1]["status"])
        self.assertEqual(1, self.inner.call_count)
        with self.assertRaises(abstention_ledger.LedgerError):
            wrapper("declared-model", "synthetic prompt", output_cap_bytes=1024)
        self.assertEqual(1, self.inner.call_count)

    def test_live_explicit_same_slot_retry_preserves_both_actual_attempts(self) -> None:
        observer, wrapper = self.live("failed")
        wrapper("declared-model", "synthetic prompt", output_cap_bytes=1024)
        observer.claude_exec = self.inner  # A fresh launcher imports the original executor.
        self.inner.return_value = ("synthetic reply", "ok")
        retry = live_analyze_campaign.LiveTransport(
            observer, verified=self.verified, retry_slot=self.slots["live"][0]
        )
        observer.claude_exec = retry
        retry("declared-model", "synthetic prompt", output_cap_bytes=1024)
        calls = [c for c in retry.campaign._state()["calls"] if c["lane"] == "live"]
        self.assertEqual(["unusable", "charged"], [c["status"] for c in calls])
        self.assertEqual([1, 2], [c["availability_attempt"] for c in calls])
        self.assertEqual(2, self.inner.call_count)

    def test_failed_executor_attempt_remains_charged(self) -> None:
        self.failed_attempt("failed")

    def test_cancelled_executor_attempt_remains_charged(self) -> None:
        self.failed_attempt("cancelled")

    def test_changed_model_or_missing_seam_never_reaches_executor(self) -> None:
        observer, wrapper = self.live()
        with self.assertRaises(abstention_ledger.LedgerError):
            wrapper("another-model", "synthetic prompt", output_cap_bytes=1024)
        observer.claude_exec = self.inner
        with self.assertRaises(abstention_ledger.LedgerError):
            wrapper("declared-model", "synthetic prompt", output_cap_bytes=1024)
        self.inner.assert_not_called()
        self.assertEqual(
            [], [c for c in json.loads(self.state.read_text())["calls"] if c["lane"] == "live"]
        )

    def test_changed_live_binary_never_reserves_or_calls_executor(self) -> None:
        _observer, wrapper = self.live()
        self.binary = getattr(self, "binary", self.root / "claude")
        self.binary.write_bytes(b"changed binary")
        with self.assertRaises(abstention_ledger.LedgerError):
            wrapper("declared-model", "synthetic prompt", output_cap_bytes=1024)
        self.inner.assert_not_called()
        self.assertEqual(
            [], [c for c in json.loads(self.state.read_text())["calls"] if c["lane"] == "live"]
        )

    def test_native_reading_model_default_executor_arguments_are_admitted(self) -> None:
        from cargento_runtime import observer as native_observer  # noqa: PLC0415
        from cargento_runtime import (  # noqa: PLC0415 - actual production model seam
            reading,
        )

        _observer, wrapper = self.live()
        with mock.patch.object(native_observer, "claude_exec", wrapper):
            model = reading.ClaudeReadingModel(cast("RuntimeConfig", "declared-model"))
            self.assertEqual(
                ("synthetic reply", "ok"), model("synthetic prompt", output_cap_bytes=1024)
            )
        self.assertEqual(1, self.inner.call_count)

    def test_argv_capture_uses_saved_executor_without_entering_installed_wrapper(self) -> None:
        from cargento_runtime import (  # noqa: PLC0415 - native capture-only transport
            config,
            observer,
        )

        native = observer.claude_exec
        guarded = mock.Mock(side_effect=AssertionError("capture entered live authority"))
        runtime_config = config.build_runtime_config(
            environ={"HOME": str(self.root)},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
        )
        with mock.patch.object(observer, "claude_exec", guarded):
            actual = score_abstention.argv_digest("claude", runtime_config, claude_executor=native)
        self.assertEqual(64, len(actual))
        guarded.assert_not_called()

    def test_foreground_launcher_holds_verified_lifetime_and_restores_native_executor(self) -> None:
        from cargento_runtime import (  # noqa: PLC0415 - native foreground launch seam
            cli,
            observer,
        )

        self.activate()
        original = observer.claude_exec
        verified = object()
        active: list[bool] = []
        context = mock.MagicMock()

        def enter() -> object:
            active.append(True)
            return verified

        context.__enter__.side_effect = enter
        context.__exit__.side_effect = lambda *_args: active.clear()

        def launched(args: list[str]) -> None:
            self.assertEqual([True], active)
            self.assertIsNot(observer.claude_exec, original)
            self.assertEqual(["--no-observer-model"], args)
            raise RuntimeError("synthetic server stop")

        transport = mock.Mock()
        with (
            mock.patch.object(score_abstention, "verify_claude_binary", return_value=context),
            mock.patch.object(live_analyze_campaign, "LiveTransport", return_value=transport),
            mock.patch.object(cli, "main", side_effect=launched),
            self.assertRaisesRegex(RuntimeError, "synthetic server stop"),
        ):
            live_analyze_campaign.main(["--no-observer-model"])
        self.assertEqual([], active)
        self.assertIs(original, observer.claude_exec)

    def test_instrumented_launcher_refuses_unmetered_codex_and_restores_executor(self) -> None:
        from cargento_runtime import cli, observer, reading  # noqa: PLC0415

        original = observer.codex_exec
        inner = mock.Mock(return_value=("unmetered reply", "ok"))
        context = mock.MagicMock()
        context.__enter__.return_value = object()

        def launched(_args: list[str]) -> int:
            model = reading.CodexReadingModel(cast("RuntimeConfig", "synthetic config"))
            with self.assertRaisesRegex(abstention_ledger.LedgerError, "unmetered"):
                model("synthetic prompt", output_cap_bytes=1024)
            inner.assert_not_called()
            return 0

        with (
            mock.patch.object(observer, "codex_exec", inner),
            mock.patch.object(score_abstention, "verify_claude_binary", return_value=context),
            mock.patch.object(live_analyze_campaign, "LiveTransport"),
            mock.patch.object(cli, "main", side_effect=launched),
        ):
            self.assertEqual(0, live_analyze_campaign.main(["--observer-model"]))
            self.assertIs(inner, observer.codex_exec)
        self.assertIs(original, observer.codex_exec)

    def test_daemon_launcher_is_refused_before_verification_or_runtime(self) -> None:
        with mock.patch.object(score_abstention, "verify_claude_binary") as verify:
            with self.assertRaises(abstention_ledger.LedgerError):
                live_analyze_campaign.main(["--daemon"])
            verify.assert_not_called()

    def test_daemon_abbreviations_are_refused_before_any_runtime_or_verification(self) -> None:
        from cargento_runtime import cli  # noqa: PLC0415

        for arg in ("--da", "--dae", "--daem", "--daemo", "--daemon"):
            with (
                self.subTest(arg=arg),
                mock.patch.object(score_abstention, "verify_claude_binary") as verify,
                mock.patch.object(live_analyze_campaign, "LiveTransport"),
                mock.patch.object(cli, "main", return_value=0) as runtime,
            ):
                with self.assertRaisesRegex(abstention_ledger.LedgerError, "foreground"):
                    live_analyze_campaign.main([arg])
                verify.assert_not_called()
                runtime.assert_not_called()

    def test_native_press_permission_refusal_does_not_call_or_reserve(self) -> None:
        from cargento_runtime.http_api import (  # noqa: PLC0415 - native permission short circuit
            _RequestHandler,
        )

        _observer, wrapper = self.live()
        handler = types.SimpleNamespace(
            _press_revision_current=lambda *_args: True,
            _reading_route=lambda *_args: object(),
            _reading_permission=lambda *_args: {"reason": "consent-required"},
            _reading_permission_reply=mock.Mock(),
            _reading_adoption=lambda *_args: wrapper(
                "declared-model", "synthetic prompt", output_cap_bytes=1024
            ),
        )
        _RequestHandler._reading_press(
            cast("_RequestHandler", handler), "claude", "synthetic-session", {}
        )
        self.inner.assert_not_called()
        self.assertEqual(
            [], [c for c in json.loads(self.state.read_text())["calls"] if c["lane"] == "live"]
        )
        handler._reading_permission_reply.assert_called_once()

    def test_native_replay_call_reserves_before_actual_inner_send(self) -> None:
        producer = {"model": "declared-model"}
        from cargento_runtime import observer  # noqa: PLC0415 - source stamp of native replay tree

        source = analyze_campaign.runtime_source_digest(Path(observer.__file__).parent)
        from cargento_runtime import reading_route  # noqa: PLC0415 - admitted vendor

        transport = {
            "reading": producer,
            "binary": "synthetic-cli",
            "binary_sha256": "b" * 64,
            "cli_version": "synthetic-version",
            "signature": "synthetic-signature",
            "destination": reading_route.VENDORS["claude"],
            "argv_digest": "a" * 64,
        }
        request = analyze_campaign.request_digest("synthetic prompt", transport, source, 1024)
        self.body["requests"]["replay"][self.slots["replay"][0]] = request
        self.activate()
        replay = drift_replay.Ledger(str(self.replay), binding=("synthetic-scope", producer))

        def actual(_prompt: str, **_kwargs: Any) -> tuple[str, str]:
            self.assertEqual(1, len(json.loads(self.state.read_text())["calls"]))
            self.assertEqual(632, replay.used())
            return "synthetic reply", "failed"

        model = drift_replay._Charged(
            actual,
            replay,
            "synthetic-key",
            transport_binding=transport,
            pinned_binary=lambda _: "synthetic-cli",
        )
        self.assertEqual(
            ("synthetic reply", "failed"), model("synthetic prompt", output_cap_bytes=1024)
        )
        self.assertTrue(model.charged)
        reading = types.SimpleNamespace(WITHHELD_MODEL_FAILED="model-failed")
        batch = drift_replay._ReadBatch(
            reading,
            str(self.root / "read.json"),
            {},
            "synthetic",
            dry_run=False,
            say=lambda _: None,
        )
        batch.record(model, "synthetic-case", "current", {"withheld": "model-failed"})
        self.assertEqual("unusable", json.loads(self.state.read_text())["calls"][0]["status"])
        next_model = drift_replay._Charged(
            actual,
            replay,
            "next-synthetic-key",
            transport_binding=transport,
            pinned_binary=lambda _: "synthetic-cli",
        )
        with self.assertRaises(drift_replay.LedgerError):
            next_model("synthetic prompt", output_cap_bytes=1024)
        self.assertEqual(632, replay.used())
        self.assertEqual(1, len(json.loads(self.state.read_text())["calls"]))

    def test_missing_campaign_does_not_leave_the_old_remaining_allowance_available(self) -> None:
        self.manifest.unlink()
        inner = mock.Mock(return_value=("synthetic reply", "ok"))
        replay = drift_replay.Ledger(str(self.replay))
        with self.assertRaises((drift_replay.LedgerError, abstention_ledger.LedgerError)):
            model = drift_replay._Charged(inner, replay, "synthetic-key")
            model("synthetic prompt", output_cap_bytes=1024)
        inner.assert_not_called()
        self.assertEqual(631, replay.used())

    def test_changed_replay_binary_never_reserves_or_calls_executor(self) -> None:
        from cargento_runtime import (  # noqa: PLC0415 - admitted actual replay bindings
            observer,
            reading_route,
        )

        binary = self.root / "synthetic-claude"
        binary.write_bytes(b"verified replay binary")
        verified = score_abstention.VerifiedClaude(
            "synthetic-cli",
            "synthetic-version",
            str(binary),
            "synthetic-signature",
            score_abstention.file_identity(str(binary)),
        )
        producer = {"model": "declared-model"}
        transport = {
            "reading": producer,
            "binary": verified.shown,
            "binary_sha256": verified.identity[-1],
            "cli_version": verified.version,
            "signature": verified.signature,
            "destination": reading_route.VENDORS["claude"],
            "argv_digest": "a" * 64,
        }
        source = analyze_campaign.runtime_source_digest(Path(observer.__file__).parent)
        request = analyze_campaign.request_digest("synthetic prompt", transport, source, 1024)
        self.body["requests"]["replay"][self.slots["replay"][0]] = request
        self.activate()
        native = drift_replay.Ledger(str(self.replay), binding=("synthetic-scope", producer))
        inner = mock.Mock(return_value=("synthetic reply", "ok"))
        model = drift_replay._Charged(
            inner,
            native,
            "synthetic-key",
            transport_binding=transport,
            pinned_binary=score_abstention.PinnedClaude(verified.path, verified.identity),
        )
        binary.write_bytes(b"changed actual replay binary")
        with self.assertRaises(drift_replay.LedgerError):
            model("synthetic prompt", output_cap_bytes=1024)
        inner.assert_not_called()
        self.assertEqual(631, native.used())
        self.assertEqual([], json.loads(self.state.read_text())["calls"])


class NativeQualificationSource(unittest.TestCase):
    """Exercise actual source callbacks through the scorer, with synthetic source bytes."""

    path: Path
    config: RuntimeConfig
    rows: list[dict[str, Any]]

    setUp = source_cases.FullProductionFreezeTest.setUp
    record = source_cases.FullProductionFreezeTest.record
    if TYPE_CHECKING:
        # Runtime borrows source helpers over the declared path/config/rows fixture.
        def write(self) -> None: ...

        def freeze(self, *, production: bool = True) -> dict[str, Any]: ...
    else:
        write = source_cases.FullProductionFreezeTest.write
        freeze = source_cases.FullProductionFreezeTest.freeze

    def score_case(self, case: dict[str, Any], model: mock.Mock) -> dict[str, Any]:
        with mock.patch.object(
            mark_abstention, "_transcript_index", return_value={"syntheti": str(self.path)}
        ):
            return score_abstention.score_case(
                self.config,
                case,
                case["row_snapshot"],
                case["producer_facts"],
                {},
                model=model,
                now=case["captured_at"],
                revision=mark_abstention.case_revision(case),
                tool_output=score_abstention._tool_output(case, "Anthropic", "claude", {"v": 5}),
                read_agent_words=True,
            )

    def test_actual_scorer_rereads_bound_full_final_and_matches_freeze_prompt(self) -> None:
        marker = "WHOLE_FINAL_SYNTHETIC_TAIL"
        self.rows[1]["message"]["content"][0]["text"] = "A " * 900 + marker
        self.write()
        case = self.freeze()
        model = mock.Mock(return_value=("{}", "ok"))
        scored = self.score_case(case, model)
        self.assertEqual(1, model.call_count)
        prompt = model.call_args.args[0]
        self.assertIn(marker, prompt)
        self.assertEqual(
            case["production_reading"]["prompt_digest"],
            hashlib.sha256(prompt.encode()).hexdigest(),
        )
        self.assertTrue(scored["reached_model"])
        self.assertNotIn(marker, json.dumps(case))

    def test_source_prompt_seal_mismatch_never_reaches_model(self) -> None:
        case = self.freeze()
        case["production_reading"]["prompt_digest"] = "f" * 64
        model = mock.Mock(return_value=("{}", "ok"))
        self.assertEqual("production-source-refused", self.score_case(case, model)["withheld"])
        model.assert_not_called()

    def test_source_metadata_cannot_smuggle_whole_words_or_a_boolean_version(self) -> None:
        for change in ({"words": "invented persistent whole words"}, {"v": True}):
            with self.subTest(fields=list(change)):
                case = self.freeze()
                case["production_reading"].update(change)
                model = mock.Mock(return_value=("{}", "ok"))
                self.assertEqual(
                    "production-source-refused", self.score_case(case, model)["withheld"]
                )
                model.assert_not_called()

    def test_actual_source_changed_selection_never_reaches_model(self) -> None:
        case = self.freeze()
        case["production_reading"]["person_wanted"][0]["id"] = "wrong-source"
        model = mock.Mock(return_value=("{}", "ok"))
        self.assertEqual("production-source-refused", self.score_case(case, model)["withheld"])
        model.assert_not_called()
