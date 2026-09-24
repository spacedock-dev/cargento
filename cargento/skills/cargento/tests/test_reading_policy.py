"""Remembered permission and rolling admission survive tabs and processes."""

from __future__ import annotations

import concurrent.futures
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cargento_runtime import io as runtime_io
from cargento_runtime import reading, reading_policy, supervise

from .support import make_runtime


def _reserve_in_process(home: str) -> str:
    config, _ = make_runtime(state_dir=Path(home), state_home=home)
    return reading_policy.reserve(config, now=100.0)["reason"]


class ReadingPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.config, _ = make_runtime(state_dir=Path(self.home.name), state_home=self.home.name)
        # An open model runner: GuardedModel refuses once it is shut.
        patcher = mock.patch.object(supervise, "_SHUTDOWN", threading.Event())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_answer_survives_a_new_client_and_forget_preserves_spend(self) -> None:
        self.assertFalse(reading_policy.status(self.config, now=100.0)["consent"])
        self.assertTrue(reading_policy.set_consent(self.config, True, now=100.0)["consent"])
        self.assertEqual("", reading_policy.reserve(self.config, now=100.0)["reason"])
        self.assertEqual(1, reading_policy.status(self.config, now=101.0)["used"])
        answer = reading_policy.set_consent(self.config, False, now=102.0)
        self.assertFalse(answer["consent"])
        self.assertEqual(1, answer["used"])
        self.assertTrue(reading_policy.forget(self.config, now=103.0))
        self.assertEqual(1, reading_policy.status(self.config, now=103.0)["used"])

    def test_rolling_cap_expires_at_the_oldest_spend_not_midnight(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0)
        for offset in range(12):
            self.assertEqual("", reading_policy.reserve(self.config, now=100.0 + offset)["reason"])
        refused = reading_policy.reserve(self.config, now=150.0)
        self.assertEqual("daily-cap", refused["reason"])
        self.assertEqual(86500.0, refused["retry_at"])
        self.assertEqual("", reading_policy.reserve(self.config, now=86500.0)["reason"])
        self.assertEqual("daily-cap", reading_policy.reserve(self.config, now=86500.0)["reason"])

    def test_concurrent_clients_cannot_admit_more_than_twelve(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(lambda _: reading_policy.reserve(self.config, now=100.0), range(24))
            )
        self.assertEqual(12, sum(result["reason"] == "" for result in results))
        self.assertEqual(12, reading_policy.status(self.config, now=100.0)["used"])

    def test_known_missing_cli_reserves_nothing(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0)
        for binary in (None, "relative/codex"):
            with self.subTest(binary=binary):
                model = reading.CodexReadingModel(
                    self.config, binary_resolver=mock.Mock(return_value=binary)
                )
                guarded = reading_policy.GuardedModel(self.config, model, lambda: 100.0)
                self.assertEqual(("", "unavailable"), guarded("prompt", output_cap_bytes=100))
                self.assertEqual(0, reading_policy.status(self.config, now=100.0)["used"])

    def test_corrupt_store_never_resets_permission_or_budget(self) -> None:
        reading_policy.store_path(self.config).write_bytes(b"not a database")
        self.assertEqual(
            "store-unavailable", reading_policy.reserve(self.config, now=100.0)["reason"]
        )
        self.assertEqual(
            "store-unavailable", reading_policy.set_consent(self.config, True, now=100.0)["reason"]
        )

    def test_failed_model_attempt_is_charged_without_a_refund(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0)
        model = mock.Mock(side_effect=TimeoutError)
        guarded = reading_policy.GuardedModel(self.config, model, lambda: 100.0)
        with self.assertRaises(TimeoutError):
            guarded("prompt", output_cap_bytes=100)
        self.assertEqual(1, reading_policy.status(self.config, now=100.0)["used"])

    def test_a_committed_reservation_is_announced_and_a_refused_one_is_not(self) -> None:
        """DRC-4686: a reading job's restart marker is written from this seam.

        Called after the spend is committed and before the model runs, so a
        marker never says an attempt was spent when it was not.
        """
        used_when_told: list[int] = []

        def reserved() -> None:
            used_when_told.append(reading_policy.status(self.config, now=100.0)["used"])

        model = mock.Mock(return_value=("{}", "ok"))
        guarded = reading_policy.GuardedModel(
            self.config, model, lambda: 100.0, on_reserved=reserved
        )
        with self.assertRaises(reading_policy.RefusedError):
            guarded("prompt", output_cap_bytes=100)
        self.assertEqual([], used_when_told)
        model.assert_not_called()
        reading_policy.set_consent(self.config, True, now=100.0)
        guarded("prompt", output_cap_bytes=100)
        self.assertEqual([1], used_when_told)
        model.available = mock.Mock(return_value=False)
        self.assertEqual(("", "unavailable"), guarded("prompt", output_cap_bytes=100))
        self.assertEqual([1], used_when_told)

    def test_a_marker_that_cannot_be_written_stops_the_call_before_it_spends(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0)
        model = mock.Mock(return_value=("{}", "ok"))
        guarded = reading_policy.GuardedModel(
            self.config, model, lambda: 100.0, before_reserve=mock.Mock(side_effect=OSError)
        )
        with self.assertRaises(OSError):
            guarded("prompt", output_cap_bytes=100)
        self.assertEqual(0, reading_policy.status(self.config, now=100.0)["used"])
        model.assert_not_called()

    def test_a_call_made_while_cargento_stops_is_refused_before_it_spends(self) -> None:
        """Verify N4: a job still preparing at shutdown must not be charged for nothing."""
        reading_policy.set_consent(self.config, True, now=100.0)
        model = mock.Mock(return_value=("{}", "ok"))
        stopping = threading.Event()
        stopping.set()
        with mock.patch.object(supervise, "_SHUTDOWN", stopping):
            guarded = reading_policy.GuardedModel(self.config, model, lambda: 100.0)
            self.assertEqual(("", "closed"), guarded("prompt", output_cap_bytes=100))
        self.assertEqual(0, reading_policy.status(self.config, now=100.0)["used"])
        model.assert_not_called()

    def test_missing_sqlite_refuses_permission_and_launch(self) -> None:
        with mock.patch.object(runtime_io, "sqlite_module", None):
            self.assertEqual(
                "store-unavailable",
                reading_policy.set_consent(self.config, True, now=100.0)["reason"],
            )
            self.assertEqual(
                "store-unavailable", reading_policy.reserve(self.config, now=100.0)["reason"]
            )

    def test_separate_processes_share_the_same_admission_bound(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0)
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_reserve_in_process, [self.home.name] * 24))
        self.assertEqual(12, results.count(""))
        self.assertEqual(12, results.count("daily-cap"))


class PermissionIsPerProviderTest(unittest.TestCase):
    """DRC-4650: allowing Codex to read a session is not allowing Anthropic to.

    The answer a reader gave named one receiver. A second provider receives a
    reader's words only after the page named it and the reader allowed it.
    """

    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.config, _ = make_runtime(state_dir=Path(self.home.name), state_home=self.home.name)

    def _consent(self, provider: str) -> bool:
        return reading_policy.status(self.config, now=100.0, provider=provider)["consent"]

    def test_a_reader_who_allowed_codex_has_not_allowed_claude_code(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0, provider="codex")
        self.assertTrue(self._consent("codex"))
        self.assertFalse(self._consent("claude"))
        refused = reading_policy.reserve(self.config, now=100.0, provider="claude")
        self.assertEqual("consent-required", refused["reason"])
        self.assertEqual(0, reading_policy.status(self.config, now=100.0)["used"])

    def test_allowing_claude_code_allows_only_claude_code(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0, provider="claude")
        self.assertTrue(self._consent("claude"))
        self.assertFalse(self._consent("codex"))
        self.assertEqual(
            "", reading_policy.reserve(self.config, now=100.0, provider="claude")["reason"]
        )

    def test_an_answer_saved_before_there_were_two_providers_reads_as_codex(self) -> None:
        path = reading_policy.store_path(self.config)
        path.parent.mkdir(parents=True, exist_ok=True)
        assert runtime_io.sqlite_module is not None
        db = runtime_io.sqlite_module.connect(path)
        db.execute(
            "CREATE TABLE permission (id INTEGER PRIMARY KEY CHECK(id=1), "
            "allowed INTEGER NOT NULL CHECK(allowed IN (0,1)))"
        )
        db.execute("CREATE TABLE spends (at REAL NOT NULL)")
        db.execute("INSERT INTO permission VALUES (1, 1)")
        db.execute("INSERT INTO spends VALUES (99.0)")
        db.commit()
        db.close()
        self.assertTrue(self._consent("codex"))
        self.assertFalse(self._consent("claude"))
        self.assertEqual(1, reading_policy.status(self.config, now=100.0)["used"])

    def test_turning_readings_off_or_forgetting_revokes_every_provider(self) -> None:
        for revoke in ("off", "forget"):
            with self.subTest(revoke=revoke):
                for provider in ("codex", "claude"):
                    reading_policy.set_consent(self.config, True, now=100.0, provider=provider)
                    reading_policy.reserve(self.config, now=100.0, provider=provider)
                used = reading_policy.status(self.config, now=100.0)["used"]
                if revoke == "off":
                    reading_policy.set_consent(self.config, False, now=100.0)
                else:
                    self.assertTrue(reading_policy.forget(self.config, now=100.0))
                self.assertFalse(self._consent("codex"))
                self.assertFalse(self._consent("claude"))
                self.assertEqual(used, reading_policy.status(self.config, now=100.0)["used"])

    def test_the_rolling_cap_is_shared_across_providers(self) -> None:
        for provider in ("codex", "claude"):
            reading_policy.set_consent(self.config, True, now=100.0, provider=provider)
        for index in range(12):
            provider = ("codex", "claude")[index % 2]
            self.assertEqual(
                "", reading_policy.reserve(self.config, now=100.0, provider=provider)["reason"]
            )
        for provider in ("codex", "claude"):
            with self.subTest(provider=provider):
                self.assertEqual(
                    "daily-cap",
                    reading_policy.reserve(self.config, now=100.0, provider=provider)["reason"],
                )

    def test_the_published_status_says_which_providers_are_allowed(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0, provider="claude")
        published = reading_policy.status(self.config, now=100.0)
        self.assertEqual({"codex": False, "claude": True}, published["providers"])

    def test_no_other_name_can_be_allowed(self) -> None:
        for name in ("", "gemini", "openai"):
            with self.subTest(name=name):
                answer = reading_policy.set_consent(self.config, True, now=100.0, provider=name)
                self.assertFalse(answer["consent"])
                self.assertEqual(
                    "consent-required",
                    reading_policy.reserve(self.config, now=100.0, provider=name)["reason"],
                )
        self.assertEqual(
            {"codex": False, "claude": False},
            reading_policy.status(self.config, now=100.0)["providers"],
        )

    def test_the_run_off_switch_outranks_a_claude_code_answer(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0, provider="claude")
        config, _ = make_runtime(
            state_dir=Path(self.home.name), state_home=self.home.name, model_calls_disabled=True
        )
        self.assertEqual(
            "run-disabled", reading_policy.status(config, now=100.0, provider="claude")["reason"]
        )
        self.assertEqual(
            "run-disabled", reading_policy.reserve(config, now=100.0, provider="claude")["reason"]
        )

    def test_a_guarded_claude_code_model_needs_claude_code_permission(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0, provider="codex")
        model = mock.Mock(return_value=("{}", "ok"))
        guarded = reading_policy.GuardedModel(self.config, model, lambda: 100.0, provider="claude")
        with self.assertRaises(reading_policy.RefusedError) as caught:
            guarded("prompt", output_cap_bytes=100)
        self.assertEqual("consent-required", caught.exception.answer["reason"])
        model.assert_not_called()

    def test_a_known_missing_claude_code_reserves_nothing(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0, provider="claude")
        model = reading.ClaudeReadingModel(
            self.config, binary_resolver=mock.Mock(return_value=None)
        )
        guarded = reading_policy.GuardedModel(self.config, model, lambda: 100.0, provider="claude")
        self.assertEqual(("", "unavailable"), guarded("prompt", output_cap_bytes=100))
        self.assertEqual(0, reading_policy.status(self.config, now=100.0)["used"])


class AnAllowGivenBeforeToolOutputWasNamedDoesNotCoverIt(unittest.TestCase):
    """DEC-23 item 7: tool output leaves only after a fresh Allow whose
    disclosure named it and its destination. The grant is its own row, keyed
    by provider and destination, so no older answer can be read as one."""

    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.config, _ = make_runtime(state_dir=Path(self.home.name), state_home=self.home.name)

    def _granted(self, provider: str, where: str) -> bool:
        answer = reading_policy.status(self.config, now=100.0, provider=provider)
        return reading_policy.tool_output_allowed(answer, provider, where)

    def test_a_reader_who_allowed_both_providers_before_this_build_sent_no_tool_output(
        self,
    ) -> None:
        for provider in ("codex", "claude"):
            reading_policy.set_consent(self.config, True, now=100.0, provider=provider)
        for provider in ("codex", "claude"):
            with self.subTest(provider=provider):
                self.assertTrue(
                    reading_policy.status(self.config, now=100.0, provider=provider)["consent"]
                )
                self.assertFalse(self._granted(provider, reading_route_vendor(provider)))

    def test_an_allow_naming_a_destination_covers_that_destination_and_no_other(self) -> None:
        answer = reading_policy.set_consent(
            self.config, True, now=100.0, provider="codex", tool_output="OpenAI"
        )
        self.assertTrue(answer["consent"])
        self.assertTrue(reading_policy.tool_output_allowed(answer, "codex", "OpenAI"))
        self.assertTrue(self._granted("codex", "OpenAI"))
        self.assertFalse(self._granted("codex", "gw.corp.example"))
        self.assertFalse(self._granted("claude", "OpenAI"))

    def test_an_empty_destination_is_never_a_grant(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0, provider="codex", tool_output="")
        self.assertFalse(self._granted("codex", ""))
        self.assertEqual({}, reading_policy.status(self.config, now=100.0)["tool_output"])

    def test_turning_readings_off_or_forgetting_withdraws_every_tool_output_grant(self) -> None:
        for revoke in ("off", "forget"):
            with self.subTest(revoke=revoke):
                reading_policy.set_consent(
                    self.config, True, now=100.0, provider="codex", tool_output="OpenAI"
                )
                if revoke == "off":
                    reading_policy.set_consent(self.config, False, now=100.0)
                else:
                    reading_policy.forget(self.config, now=100.0)
                self.assertFalse(self._granted("codex", "OpenAI"))

    def test_a_store_that_cannot_be_read_grants_nothing(self) -> None:
        reading_policy.store_path(self.config).write_bytes(b"not a database")
        answer = reading_policy.set_consent(
            self.config, True, now=100.0, provider="codex", tool_output="OpenAI"
        )
        self.assertEqual("store-unavailable", answer["reason"])
        self.assertFalse(reading_policy.tool_output_allowed(answer, "codex", "OpenAI"))


def reading_route_vendor(provider: str) -> str:
    return {"codex": "OpenAI", "claude": "Anthropic"}[provider]


class ARollbackCannotResurrectConsentTest(unittest.TestCase):
    """DRC-4666: a pre-L6 build's Turn off writes only the legacy row.

    That build runs `INSERT OR REPLACE INTO permission VALUES (1, 0)` and knows
    no other table, so without a trigger in the store's own schema its Turn off
    and `--forget` left `provider_permission('claude', 1)` standing, and the
    Claude Code answer came back on the next upgrade.
    """

    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.config, _ = make_runtime(state_dir=Path(self.home.name), state_home=self.home.name)

    def _old_build_writes(self, statement: str) -> None:
        assert runtime_io.sqlite_module is not None
        db = runtime_io.sqlite_module.connect(reading_policy.store_path(self.config))
        db.execute(statement)
        db.commit()
        db.close()

    def test_an_old_builds_turn_off_revokes_claude_code_and_its_tool_grants(self) -> None:
        for statement in (
            "INSERT OR REPLACE INTO permission VALUES (1, 0)",
            "UPDATE permission SET allowed = 0 WHERE id = 1",
        ):
            with self.subTest(statement=statement):
                reading_policy.set_consent(self.config, True, now=100.0, provider="codex")
                reading_policy.set_consent(
                    self.config, True, now=100.0, provider="claude", tool_output="Anthropic"
                )
                before = reading_policy.status(self.config, now=100.0, provider="claude")
                self.assertTrue(before["consent"])
                self.assertEqual({"claude": ["Anthropic"]}, before["tool_output"])
                self._old_build_writes(statement)
                after = reading_policy.status(self.config, now=100.0, provider="claude")
                self.assertFalse(after["consent"])
                self.assertEqual({"codex": False, "claude": False}, after["providers"])
                self.assertEqual({}, after["tool_output"])

    def test_an_old_builds_allow_leaves_claude_code_alone(self) -> None:
        reading_policy.set_consent(self.config, True, now=100.0, provider="claude")
        self._old_build_writes("INSERT OR REPLACE INTO permission VALUES (1, 1)")
        self.assertTrue(reading_policy.status(self.config, now=100.0, provider="claude")["consent"])


class TheCapOutranksConsentTest(unittest.TestCase):
    """DRC-4666: the page reads the Codex status, and the budget is shared.

    With only Claude Code allowed and the day's budget spent, the published
    answer said `consent-required`, which the page renders as nothing, so
    Analyze drift stayed enabled and the press answered 429.
    """

    def test_a_spent_budget_reads_daily_cap_for_a_provider_never_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            config, _ = make_runtime(state_dir=Path(home), state_home=home)
            reading_policy.set_consent(config, True, now=100.0, provider="claude")
            for offset in range(reading_policy.DAILY_CAP):
                self.assertEqual(
                    "",
                    reading_policy.reserve(config, now=100.0 + offset, provider="claude")["reason"],
                )
            published = reading_policy.status(config, now=200.0)
            self.assertFalse(published["consent"])
            self.assertEqual("daily-cap", published["reason"])
            self.assertEqual(
                "daily-cap", reading_policy.reserve(config, now=200.0, provider="codex")["reason"]
            )
