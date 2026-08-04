"""The quota fetch, held to the SECURITY.md "Usage quota reads" contract.

Every boundary the contract names is asserted here: the request carries the
token and nothing else, the token reaches no diagnostic line and no loopback
response, no refresh path exists, the five-minute floor holds for failures as
well as successes, and neither `collect` nor `--diagnose` can trigger a fetch.
"""

from __future__ import annotations

import dataclasses
import email.message
import http.client
import json
import tempfile
import threading
import time
import unittest
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Self
from unittest import mock

from cargento_runtime import aggregate, cli, diagnostics, quota
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

from .support import SERVER_PATH, RuntimeTestCase, make_server, runtime

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.state import RuntimeState

# Deliberately not credential-shaped: it appears in assertions about where a
# token must NOT show up, and those assertions read better with a value that
# could never be mistaken for a real one.
TOKEN = "usage-test-access-token"  # noqa: S105 — deliberately fake; asserted ABSENT from outputs
NOW = 1_700_000_000.0


def _http_error(code: int, msg: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(quota.USAGE_ENDPOINT, code, msg, email.message.Message(), None)


def _no_runner(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("the keychain must not be consulted on this platform")


def _config(
    home: str = "/home/cargento-test",
    platform_name: str = "linux",
    **changes: Any,
) -> RuntimeConfig:
    config = build_runtime_config(
        environ={"HOME": home},
        platform_name=platform_name,
        os_name="posix",
        launcher_path=SERVER_PATH,
    )
    return dataclasses.replace(config, **changes) if changes else config


def _state(config: RuntimeConfig) -> RuntimeState:
    return build_runtime_state(config, started=NOW)


def _credentials(expires_at_ms: float | None = None) -> str:
    oauth: dict[str, Any] = {"accessToken": TOKEN}
    if expires_at_ms is not None:
        oauth["expiresAt"] = expires_at_ms
    return json.dumps({"claudeAiOauth": oauth})


def _keychain_runner(
    stdout: str,
    returncode: int = 0,
    calls: list[list[str]] | None = None,
) -> Any:
    def runner(argv: list[str], **_kwargs: Any) -> SimpleNamespace:
        if calls is not None:
            calls.append(argv)
        return SimpleNamespace(returncode=returncode, stdout=stdout)

    return runner


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, n: int = -1) -> bytes:
        return self._body[:n] if n > 0 else self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _opener(
    body: dict[str, Any] | None = None,
    *,
    error: BaseException | None = None,
    requests: list[Any] | None = None,
    raw: bytes | None = None,
) -> Any:
    def opener(request: Any, timeout: float) -> _Response:
        del timeout
        if requests is not None:
            requests.append(request)
        if error is not None:
            raise error
        return _Response(raw if raw is not None else json.dumps(body or {}).encode())

    return opener


def _usage_body(five: float = 42, week: float = 61) -> dict[str, Any]:
    return {
        "five_hour": {"utilization": five, "resets_at": NOW + 3600},
        "seven_day": {"utilization": week, "resets_at": NOW + 4 * 86400},
        "limits": [{"model": "opus", "utilization": 12}],
    }


def _forbidden_opener() -> Any:
    def opener(_request: Any, timeout: float) -> _Response:
        del timeout
        raise AssertionError("a request was made where the contract forbids one")

    return opener


class TokenReadTest(unittest.TestCase):
    def test_credentials_path_follows_the_claude_store(self) -> None:
        self.assertEqual(
            "/home/cargento-test/.claude/.credentials.json",
            quota.credentials_path(_config()),
        )
        # A CLAUDE_CONFIG_DIR override moves the projects store, and the
        # credential file must move with it.
        moved = build_runtime_config(
            environ={"HOME": "/home/x", "CLAUDE_CONFIG_DIR": "/srv/claude-home"},
            platform_name="linux",
            os_name="posix",
            launcher_path=SERVER_PATH,
        )
        self.assertEqual("/srv/claude-home/.credentials.json", quota.credentials_path(moved))

    def test_macos_reads_the_keychain_item_by_its_service_name(self) -> None:
        calls: list[list[str]] = []
        runner = _keychain_runner(_credentials(), calls=calls)
        requests: list[Any] = []
        entries, note = quota._claude_entries(
            _config(platform_name="darwin"),
            NOW,
            _opener(_usage_body(), requests=requests),
            runner,
        )
        self.assertIsNone(note)
        self.assertEqual(1, len(entries))
        (argv,) = calls
        self.assertEqual("/usr/bin/security", argv[0])
        self.assertIn(quota.KEYCHAIN_SERVICE, argv)
        self.assertEqual(1, len(requests))

    def test_an_unavailable_keychain_item_is_a_category_never_a_value(self) -> None:
        # A denied prompt or a missing item must not become "expired": the
        # sign-in-again pointer would be the wrong advice. And whatever the
        # subprocess did print must never travel into the note.
        runner = _keychain_runner("secret-looking stdout", returncode=1)
        entries, note = quota._claude_entries(
            _config(platform_name="darwin"), NOW, _forbidden_opener(), runner
        )
        self.assertEqual([], entries)
        self.assertEqual("keychain item unavailable", note)

    def test_missing_and_malformed_credential_files_stay_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(home=tmp)
            entries, note = quota._claude_entries(config, NOW, _forbidden_opener(), _no_runner)
            self.assertEqual(([], "no credential file"), (entries, note))

            path = Path(quota.credentials_path(config))
            path.parent.mkdir(parents=True)
            path.write_text("{not json")
            entries, note = quota._claude_entries(config, NOW, _forbidden_opener(), _no_runner)
            self.assertEqual(([], "malformed credentials"), (entries, note))

            path.write_text(json.dumps({"claudeAiOauth": {"accessToken": "  "}}))
            entries, note = quota._claude_entries(config, NOW, _forbidden_opener(), _no_runner)
            self.assertEqual(([], "no oauth token"), (entries, note))

    def test_an_expired_token_makes_no_request_and_never_refreshes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(home=tmp)
            path = Path(quota.credentials_path(config))
            path.parent.mkdir(parents=True)
            path.write_text(_credentials(expires_at_ms=(NOW - 60) * 1000))
            entries, note = quota._claude_entries(config, NOW, _forbidden_opener(), _no_runner)
        self.assertIsNone(note)
        self.assertEqual([{"harness": "claude", "state": "expired", "asOf": int(NOW)}], entries)


class FetchRequestTest(unittest.TestCase):
    def _fetch(
        self,
        opener: Any,
        *,
        config: RuntimeConfig | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        return quota._fetch_windows(config or _config(), TOKEN, NOW, opener)

    def test_the_request_carries_the_token_and_nothing_else(self) -> None:
        requests: list[Any] = []
        self._fetch(_opener(_usage_body(), requests=requests))
        (request,) = requests
        self.assertEqual(quota.USAGE_ENDPOINT, request.full_url)
        self.assertEqual("GET", request.get_method())
        self.assertIsNone(request.data)
        # Exactly two headers of ours. Asserting equality (not membership) is
        # what makes "nothing else" a tested claim rather than a hope.
        self.assertEqual(
            {
                "Authorization": f"Bearer {TOKEN}",
                "Anthropic-beta": quota.USAGE_BETA_VALUE,
            },
            dict(request.headers),
        )

    def test_windows_are_shaped_clamped_and_reset_stamped(self) -> None:
        entries, note = self._fetch(_opener(_usage_body(five=63.4, week=141)))
        self.assertIsNone(note)
        (entry,) = entries
        self.assertEqual("claude", entry["harness"])
        self.assertEqual("ok", entry["state"])
        self.assertEqual(int(NOW), entry["asOf"])
        self.assertEqual(63, entry["fiveH"]["pct"])
        self.assertEqual(100, entry["week"]["pct"])
        self.assertTrue(entry["fiveH"]["reset"])

    def test_iso_reset_stamps_parse_like_epoch_ones(self) -> None:
        iso = datetime.fromtimestamp(NOW + 3600, tz=UTC).isoformat()
        body = {"five_hour": {"utilization": 10, "resets_at": iso}}
        entries, _ = self._fetch(_opener(body))
        self.assertEqual(
            quota._shape_window(NOW, {"utilization": 10, "resets_at": NOW + 3600}),
            entries[0]["fiveH"],
        )

    def test_a_rejected_token_reads_as_expired_without_retry(self) -> None:
        for code in (401, 403):
            with self.subTest(code=code):
                error = _http_error(code, "no")
                entries, note = self._fetch(_opener(error=error))
                self.assertIsNone(note)
                self.assertEqual("expired", entries[0]["state"])

    def test_failures_shape_into_categories_without_the_token(self) -> None:
        cases: list[tuple[BaseException | None, bytes | None, str]] = [
            (_http_error(503, "down"), None, "HTTP 503"),
            (urllib.error.URLError("nope"), None, "URLError"),
            (TimeoutError("slow"), None, "TimeoutError"),
            (None, b"{not json", "malformed response"),
            (None, b"{}", "response carried no windows"),
        ]
        for error, raw, expected in cases:
            with self.subTest(expected=expected):
                entries, note = self._fetch(_opener(error=error, raw=raw))
                self.assertEqual([], entries)
                self.assertEqual(expected, note)
                self.assertNotIn(TOKEN, note or "")


class FetchLifecycleTest(unittest.TestCase):
    def _darwin(self, **changes: Any) -> tuple[RuntimeConfig, RuntimeState]:
        config = _config(platform_name="darwin", **changes)
        return config, _state(config)

    def test_a_fetch_caches_entries_and_diagnoses_only_categories(self) -> None:
        config, state = self._darwin()
        diagnostics_log: list[str] = []
        quota.fetch_claude_usage(
            config,
            state,
            clock=lambda: NOW,
            opener=_opener(_usage_body()),
            runner=_keychain_runner(_credentials()),
            diagnostic_sink=diagnostics_log.append,
        )
        self.assertEqual([], diagnostics_log)
        cached = quota.cached_entries(state)
        self.assertEqual("ok", cached[0]["state"])

        quota.fetch_claude_usage(
            config,
            state,
            clock=lambda: NOW,
            opener=_opener(error=urllib.error.URLError("net down")),
            runner=_keychain_runner(_credentials()),
            diagnostic_sink=diagnostics_log.append,
        )
        self.assertEqual([], quota.cached_entries(state))
        self.assertTrue(any("URLError" in line for line in diagnostics_log))
        self.assertFalse(any(TOKEN in line for line in diagnostics_log))

    def test_cached_entries_returns_copies(self) -> None:
        _, state = self._darwin()
        with state.usage_fetch_lock:
            state.usage_fetch_cache["claude"] = {
                "ts": NOW,
                "entries": [{"harness": "claude", "state": "ok"}],
            }
        quota.cached_entries(state)[0]["state"] = "mangled"
        self.assertEqual("ok", quota.cached_entries(state)[0]["state"])

    def test_request_fetch_holds_every_gate_of_the_polling_posture(self) -> None:
        clock_now = [NOW]
        fetched: list[Any] = []
        config, state = self._darwin()

        def inline(run: Any) -> None:
            run()

        def request(**overrides: Any) -> bool:
            return quota.request_fetch(
                overrides.pop("config", config),
                state,
                clock=lambda: clock_now[0],
                opener=overrides.pop("opener", _opener(_usage_body(), requests=fetched)),
                runner=_keychain_runner(_credentials()),
                diagnostic_sink=lambda _line: None,
                spawn=inline,
                **overrides,
            )

        # Gate 1: the feature switch. --no-usage means never, full stop.
        off = dataclasses.replace(config, usage_fetch_enabled=False)
        self.assertFalse(request(config=off, opener=_forbidden_opener()))

        # First consented request fetches.
        self.assertTrue(request())
        self.assertEqual(1, len(fetched))

        # Gate 2: the five-minute floor, inside it nothing moves.
        clock_now[0] = NOW + config.usage_poll_floor_sec - 1
        self.assertFalse(request(opener=_forbidden_opener()))

        # Past the floor the next consented request fetches again.
        clock_now[0] = NOW + config.usage_poll_floor_sec + 1
        self.assertTrue(request())
        self.assertEqual(2, len(fetched))

    def test_the_floor_applies_to_failed_fetches_too(self) -> None:
        # A missing credential must retry on the same cadence as success —
        # "a failed poll means an empty tile, never a retry storm".
        config, state = self._darwin()
        attempts: list[list[str]] = []
        for _ in range(3):
            quota.request_fetch(
                config,
                state,
                clock=lambda: NOW,
                runner=_keychain_runner("", returncode=1, calls=attempts),
                diagnostic_sink=lambda _line: None,
                spawn=lambda run: run(),
            )
        self.assertEqual(1, len(attempts))

    def test_a_fetch_already_in_flight_blocks_a_second(self) -> None:
        config, state = self._darwin()
        with state.usage_fetch_lock:
            state.usage_fetch_inflight.add("claude")
        self.assertFalse(
            quota.request_fetch(
                config,
                state,
                clock=lambda: NOW,
                opener=_forbidden_opener(),
                spawn=lambda run: run(),
            )
        )

    def test_the_inflight_marker_clears_even_when_the_fetch_dies(self) -> None:
        config, state = self._darwin()
        boom = RuntimeError("thread death")
        with (
            mock.patch.object(quota, "fetch_claude_usage", side_effect=boom),
            self.assertRaises(RuntimeError),
        ):
            quota.request_fetch(config, state, clock=lambda: NOW, spawn=lambda run: run())
        with state.usage_fetch_lock:
            self.assertEqual(set(), state.usage_fetch_inflight)

    def test_the_default_spawn_runs_on_a_daemon_thread(self) -> None:
        seen: list[bool] = []
        done = threading.Event()

        def probe() -> None:
            seen.append(threading.current_thread().daemon)
            done.set()

        quota._spawn_thread(probe)
        self.assertTrue(done.wait(timeout=5))
        self.assertEqual([True], seen)


class NoFetchWithoutConsentTest(RuntimeTestCase):
    """The serving surface: only a consented /api/data request may trigger."""

    def _server(self) -> tuple[Any, Any]:
        application = cli.build_application(*runtime(), clock=time.time)
        httpd = make_server(application=application)
        return httpd, application

    def _get(self, port: int, path: str) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", path)
        response = conn.getresponse()
        response.read()
        conn.close()

    def test_only_a_consented_request_triggers_and_diagnose_never_does(self) -> None:
        httpd, application = self._server()
        calls: list[bool] = []
        original = application.request_usage_fetch

        def fake_trigger() -> bool:
            calls.append(True)
            return False

        application.request_usage_fetch = fake_trigger
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            self._get(httpd.server_port, "/api/data")
            self._get(httpd.server_port, "/api/data?all=1")
            self.assertEqual([], calls, "a bare request must never trigger a fetch")
            self._get(httpd.server_port, "/api/data?usage=1")
            self.assertEqual(1, len(calls))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
            application.request_usage_fetch = original

        # --diagnose runs a full collection; a fetch riding along would be a
        # network side effect on a path documented to report local paths only.
        with (
            mock.patch.object(quota, "request_fetch") as trigger,
            mock.patch.object(quota, "fetch_claude_usage") as fetch,
        ):
            diagnostics.diagnose(application)
            application.collect(show_all=True)
        trigger.assert_not_called()
        fetch.assert_not_called()

    def test_the_token_reaches_no_loopback_response(self) -> None:
        # End to end: a successful fetch fills the cache, the collection
        # publishes the shaped quota numbers, and the serialized payload every
        # loopback endpoint could serve carries no trace of the token.
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(home=tmp, platform_name="darwin")
            Path(tmp, ".claude", "projects").mkdir(parents=True)
            state = _state(config)
            quota.fetch_claude_usage(
                config,
                state,
                clock=lambda: NOW,
                opener=_opener(_usage_body()),
                runner=_keychain_runner(_credentials()),
                diagnostic_sink=lambda _line: None,
            )
            application = aggregate.Application(
                config,
                state,
                aggregate.default_harnesses(lambda _t, _m: None),
                native_notifier=lambda _p: "",
                popup_notifier=lambda _t, _m: None,
                diagnostic_sink=lambda _line: None,
                clock=lambda: NOW,
            )
            body = application.collect_json(show_all=True)
        self.assertNotIn(TOKEN.encode(), body)
        data = json.loads(body)
        self.assertTrue(data.get("usage_fetch"))
        (claude_entry,) = [u for u in data["usage"] if u.get("harness") == "claude"]
        self.assertEqual("ok", claude_entry["state"])
        self.assertEqual(42, claude_entry["fiveH"]["pct"])


class StatuslineReceiptTest(unittest.TestCase):
    """Pushed receipts: shaping, the worst-of-pair rule, and staleness.

    Field names and the two-family shape come from a payload captured off a
    live agy 1.1.10 install, not from the vendor's documentation.
    """

    @staticmethod
    def _payload(**buckets: float | None) -> dict[str, Any]:
        """A status-line payload carrying the named buckets, plus the noise a
        real one carries. The email is deliberately present: it must never
        reach an entry."""
        quota: dict[str, Any] = {}
        for key, remaining in buckets.items():
            name = key.replace("_", "-")
            quota[name] = (
                {"remaining_fraction": remaining, "reset_time": "2026-08-04T14:16:36Z"}
                if remaining is not None
                else {}
            )
        return {
            "quota": quota,
            "email": "someone@example.com",
            "transcript_path": "/Users/someone/secret/path.jsonl",
            "plan_tier": "Google AI Ultra",
            "agent_state": "idle",
        }

    def test_the_captured_shape_becomes_one_entry(self) -> None:
        # The exact four keys the live capture carried.
        entries = quota.shape_statusline(
            self._payload(gemini_5h=1, gemini_weekly=1, **{"3p_5h": 1, "3p_weekly": 1}), NOW
        )
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual("antigravity", entry["harness"])
        self.assertEqual("ok", entry["state"])
        self.assertEqual(int(NOW), entry["asOf"])
        self.assertEqual(0, entry["fiveH"]["pct"])
        self.assertEqual(0, entry["week"]["pct"])

    def test_remaining_fraction_is_inverted_to_percent_used(self) -> None:
        # The live capture was all 1.0, where a wrong inversion is invisible,
        # so this is the assertion that actually pins the arithmetic.
        entries = quota.shape_statusline(self._payload(gemini_5h=0.4, gemini_weekly=0.0), NOW)
        self.assertEqual(60, entries[0]["fiveH"]["pct"])
        self.assertEqual(100, entries[0]["week"]["pct"])

    def test_the_worse_of_each_family_pair_wins(self) -> None:
        # Two model families report the same windows. The band answers "am I
        # about to run out", so the binding constraint is the honest number.
        entries = quota.shape_statusline(
            self._payload(gemini_5h=0.4, gemini_weekly=1.0, **{"3p_5h": 0.9, "3p_weekly": 0.0}),
            NOW,
        )
        self.assertEqual(60, entries[0]["fiveH"]["pct"], "gemini-5h is worse than 3p-5h")
        self.assertEqual(100, entries[0]["week"]["pct"], "3p-weekly is worse than gemini-weekly")

    def test_no_payload_field_beyond_the_windows_is_published(self) -> None:
        entries = quota.shape_statusline(self._payload(gemini_5h=0.5), NOW)
        serialized = json.dumps(entries)
        for leak in ("example.com", "secret/path", "Google AI Ultra", "idle"):
            self.assertNotIn(leak, serialized)
        self.assertEqual({"harness", "state", "asOf", "fiveH"}, set(entries[0]))

    def test_unknown_and_malformed_buckets_are_dropped(self) -> None:
        cases: list[tuple[str, dict[str, Any]]] = [
            ("no quota key", {}),
            ("quota not an object", {"quota": "nope"}),
            ("empty quota", {"quota": {}}),
            ("unknown suffix", {"quota": {"gemini-monthly": {"remaining_fraction": 0.5}}}),
            ("fraction missing", {"quota": {"gemini-5h": {}}}),
            ("fraction not a number", {"quota": {"gemini-5h": {"remaining_fraction": "half"}}}),
            ("fraction is a bool", {"quota": {"gemini-5h": {"remaining_fraction": True}}}),
            ("bucket not an object", {"quota": {"gemini-5h": 0.5}}),
        ]
        for label, payload in cases:
            with self.subTest(case=label):
                self.assertEqual([], quota.shape_statusline(payload, NOW))

    def test_out_of_range_fractions_clamp(self) -> None:
        entries = quota.shape_statusline(self._payload(gemini_5h=-3, gemini_weekly=42), NOW)
        self.assertEqual(100, entries[0]["fiveH"]["pct"])
        self.assertEqual(0, entries[0]["week"]["pct"])

    def test_a_receipt_is_stored_and_read_back(self) -> None:
        config = _config()
        state = _state(config)
        response = quota.receive_statusline(state, self._payload(gemini_5h=0.25), now=NOW)
        self.assertEqual({"ok": True, "usage": 1}, response)
        entries = quota.receipt_entries(config, state, NOW, 24)
        self.assertEqual(75, entries[0]["fiveH"]["pct"])
        # Copied out, so a caller cannot mutate the stored receipt.
        entries[0]["fiveH"]["pct"] = 1
        self.assertEqual(75, quota.receipt_entries(config, state, NOW, 24)[0]["fiveH"]["pct"])

    def test_a_stale_receipt_is_dropped_rather_than_shown(self) -> None:
        # Receipts only arrive while the harness runs, so a stored figure can
        # be arbitrarily old. Past the window its own quota windows have reset.
        config = _config()
        state = _state(config)
        quota.receive_statusline(state, self._payload(gemini_5h=0.5), now=NOW)
        self.assertEqual(1, len(quota.receipt_entries(config, state, NOW + 3600, 24)))
        self.assertEqual([], quota.receipt_entries(config, state, NOW + 48 * 3600, 24))

    def test_an_unusable_payload_still_stamps_the_arrival(self) -> None:
        # Storing an empty list matters: a harness that stops reporting quota
        # must go stale and drop out, not show its last figure forever.
        config = _config()
        state = _state(config)
        quota.receive_statusline(state, self._payload(gemini_5h=0.5), now=NOW)
        response = quota.receive_statusline(state, {"quota": {}}, now=NOW + 60)
        self.assertEqual({"ok": True, "usage": 0}, response)
        self.assertEqual([], quota.receipt_entries(config, state, NOW + 60, 24))

    def test_nothing_is_read_back_before_any_receipt(self) -> None:
        config = _config()
        self.assertEqual([], quota.receipt_entries(config, _state(config), NOW, 24))


class UsageEndpointTest(RuntimeTestCase):
    """POST /api/usage: the same guards as /api/notify, and no new exposure."""

    def _post(
        self, port: int, body: bytes, headers: dict[str, str] | None = None
    ) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST",
            "/api/usage",
            body=body,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        response = conn.getresponse()
        payload = response.read()
        status = response.status
        conn.close()
        return status, payload

    def test_a_receipt_reaches_the_band_through_the_endpoint(self) -> None:
        application = cli.build_application(*runtime(), clock=time.time)
        httpd = make_server(application=application)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            body = json.dumps(
                {
                    "quota": {
                        "gemini-5h": {"remaining_fraction": 0.3},
                        "3p-5h": {"remaining_fraction": 0.8},
                    },
                    "email": "someone@example.com",
                }
            ).encode()
            status, response = self._post(httpd.server_port, body)
            self.assertEqual(200, status)
            self.assertEqual(b'{"ok":true,"usage":1}', response)
            entries = quota.receipt_entries(application.config, application.state, time.time(), 24)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        # Worse of the pair: 1 - 0.3 = 70, not 1 - 0.8 = 20.
        self.assertEqual(70, entries[0]["fiveH"]["pct"])
        self.assertNotIn("example.com", json.dumps(entries))

    def test_the_endpoint_rejects_what_notify_rejects(self) -> None:
        application = cli.build_application(*runtime(), clock=time.time)
        httpd = make_server(application=application)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            cap = application.config.usage_receipt_cap_bytes
            # Oversized: refused on the declared length, before any read.
            status, _ = self._post(httpd.server_port, b"x" * (cap + 1))
            self.assertEqual(413, status)
            # Cross-site: the same _local_ok() gate as every other route.
            status, _ = self._post(httpd.server_port, b"{}", {"Sec-Fetch-Site": "cross-site"})
            self.assertEqual(403, status)
            # Malformed and non-object bodies degrade rather than raise.
            for body in (b"{not json", b"[1,2,3]", b"null", b""):
                with self.subTest(body=body):
                    status, response = self._post(httpd.server_port, body)
                    self.assertEqual(200, status)
                    self.assertEqual(b'{"ok":true,"usage":0}', response)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_the_receipt_path_never_fetches(self) -> None:
        # The whole point of this path is that it needs no credential and makes
        # no request. --diagnose runs collect(), so this must hold there too.
        application = cli.build_application(*runtime(), clock=time.time)
        quota.receive_statusline(
            application.state,
            {"quota": {"gemini-5h": {"remaining_fraction": 0.5}}},
            now=time.time(),
        )
        with (
            mock.patch.object(quota, "request_fetch") as trigger,
            mock.patch.object(quota, "fetch_claude_usage") as fetch,
        ):
            diagnostics.diagnose(application)
            application.collect(show_all=True)
        trigger.assert_not_called()
        fetch.assert_not_called()
