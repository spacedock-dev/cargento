"""Remembered permission and rolling admission survive tabs and processes."""

from __future__ import annotations

import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from cargento_runtime import reading_policy

from .support import make_runtime


class ReadingPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.config, _ = make_runtime(state_dir=Path(self.home.name), state_home=self.home.name)

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

    def test_corrupt_store_never_resets_permission_or_budget(self) -> None:
        reading_policy.store_path(self.config).write_bytes(b"not a database")
        self.assertEqual(
            "store-unavailable", reading_policy.reserve(self.config, now=100.0)["reason"]
        )
        self.assertEqual(
            "store-unavailable", reading_policy.set_consent(self.config, True, now=100.0)["reason"]
        )
