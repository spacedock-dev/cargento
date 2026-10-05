"""The model named before a press cannot change before consent or spend."""

from __future__ import annotations

import json
import unittest

from cargento_runtime import reading_policy

from . import test_http_api


class AClaudePressBindsItsDrawnModel(unittest.TestCase):
    def test_missing_or_stale_selection_refuses_before_permission_and_call(self) -> None:
        fixture = test_http_api.ReadingRouteTest()
        self.addCleanup(fixture.doCleanups)
        config, state = fixture._runtime(claude_reading_model="claude-opus-6")
        reading_policy.set_consent(config, False, now=1_700_000_100.0)
        with (
            fixture._counting_model(("claude",), harness="claude") as calls,
            fixture._serving(fixture._app(config, state, harness="claude")) as port,
        ):
            for model in (None, "claude-sonnet-5", "claude-haiku-6"):
                payload = fixture._press(
                    harness="claude", provider="claude", allow=True, words_destination=""
                )
                if model is None:
                    payload.pop("model", None)
                else:
                    payload["model"] = model
                status, raw = fixture._post(port, payload)
                self.assertEqual(
                    (409, "destination-changed"), (status, json.loads(raw).get("reason"))
                )
                self.assertEqual([], calls)
                self.assertFalse(reading_policy.status(config, now=1_700_000_100.0)["consent"])
            status, _raw = fixture._post(
                port,
                fixture._press(
                    harness="claude",
                    provider="claude",
                    allow=True,
                    words_destination="",
                    model="claude-opus-6",
                ),
            )
            self.assertEqual(202, status)
            self.assertEqual(1, len(calls))

    def test_codex_keeps_its_existing_press_without_a_claude_model(self) -> None:
        fixture = test_http_api.ReadingRouteTest()
        self.addCleanup(fixture.doCleanups)
        config, state = fixture._runtime()
        with (
            fixture._counting_model() as calls,
            fixture._serving(fixture._app(config, state)) as port,
        ):
            status, _raw = fixture._post(port, fixture._press())
        self.assertEqual(202, status)
        self.assertEqual(1, len(calls))
