"""The event ingress: the route, the capability, the ceiling, and the adapter."""

from __future__ import annotations

import hmac
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import event_hook
import notify_hook
from cargento_runtime import events, http_api, lifecycle, observation

from . import support

NOW = 1_700_000_000.0
# Sentinel for "send this run's real token", so the helper's default is not a
# string that reads like a hardcoded credential.
PRESENT = "<this run's capability>"
SESSION = "abcdef12-3456-7890-abcd-ef1234567890"
PREFIX = "abcdef12"


class FakeStreams:
    count = 0


class FakeApplication:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.state = SimpleNamespace(streams=FakeStreams())
        self.diagnostic_sink: Any = lambda _message: None

    def collect_json(self, *, show_all: bool) -> tuple[tuple[float, int], bytes]:  # noqa: ARG002
        return (NOW, 1), b"{}"


class IngressTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.config = support.make_config()
        self.coordinator = observation.Observation(
            FakeApplication(self.config),  # type: ignore[arg-type]
            clock=lambda: NOW,
            diagnostic_sink=lambda _message: None,
        )
        self.token = self.coordinator.capability("claude")

    def post(
        self,
        path: str,
        payload: Any,
        *,
        token: str | None = PRESENT,
        coordinator: Any = "default",
        declared: int | None = None,
    ) -> tuple[int | None, bytes]:
        """Drive do_POST directly and report the status and body it produced."""
        handler: Any = http_api._RequestHandler.__new__(http_api._RequestHandler)
        body = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
        headers: dict[str, str] = {
            "Content-Length": str(len(body) if declared is None else declared)
        }
        if token is not None:
            headers["X-Cargento-Capability"] = self.token if token is PRESENT else token
        handler.headers = headers
        handler.path = path
        handler.rfile = io.BytesIO(body)
        handler.server = SimpleNamespace(
            application=FakeApplication(self.config),
            observation=self.coordinator if coordinator == "default" else coordinator,
        )
        handler._local_ok = lambda **_kw: True
        handler._drain_body = lambda: None
        sent: list[tuple[int, bytes]] = []
        handler._send = lambda body_bytes, _ctype, code=200, **_k: sent.append((code, body_bytes))
        handler.send_error = lambda code, *_a, **_k: sent.append((code, b""))
        handler.do_POST()
        return (sent[0][0], sent[0][1]) if sent else (None, b"")

    def envelope(self, **overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"v": 1, "event": "turn_started", "session_id": SESSION}
        payload.update(overrides)
        return payload


class RouteTest(IngressTestCase):
    def test_a_capable_caller_is_accepted_and_the_overlay_lands(self) -> None:
        code, body = self.post("/api/events/claude", self.envelope())
        self.assertEqual(200, code)
        self.assertEqual({"ok": True, "outcome": "accepted"}, json.loads(body))
        self.assertEqual(
            [events.OVERLAY_WORKING],
            [item.kind for item in self.coordinator.overlays_for("claude", PREFIX)],
        )

    def test_no_capability_is_refused(self) -> None:
        code, _ = self.post("/api/events/claude", self.envelope(), token=None)
        self.assertEqual(403, code)
        self.assertEqual([], self.coordinator.overlays_for("claude", PREFIX))

    def test_a_wrong_capability_is_refused(self) -> None:
        code, _ = self.post("/api/events/claude", self.envelope(), token="0" * 64)
        self.assertEqual(403, code)

    def test_a_prefix_of_the_capability_is_refused(self) -> None:
        code, _ = self.post("/api/events/claude", self.envelope(), token=self.token[:-1])
        self.assertEqual(403, code)

    def test_an_empty_capability_header_is_refused(self) -> None:
        # A present-but-empty header, which is what a shell writes when the
        # variable it interpolated was unset.
        code, _ = self.post("/api/events/claude", self.envelope(), token="")
        self.assertEqual(403, code)

    def test_a_non_ascii_capability_header_is_refused_rather_than_raising(self) -> None:
        # Found by mutation analysis, and it was a real defect. `compare_digest`
        # raises TypeError on any character above 127, and `http.client` decodes
        # header bytes as latin-1, so one high byte in this header reached the
        # comparison and took the handler down instead of being refused.
        code, _ = self.post("/api/events/claude", self.envelope(), token="\xff" * 64)
        self.assertEqual(403, code)

    def test_a_non_ascii_capability_does_not_raise_out_of_authorized(self) -> None:
        # The unit-level statement of the same thing, so a future refactor of the
        # route cannot quietly lose it.
        self.assertFalse(self.coordinator.authorized("claude", "\xff" * 64))

    def test_the_comparison_is_constant_time(self) -> None:
        # Timing is not observable from a unit test, so this asserts the
        # mechanism instead: the token is a value an attacker can retry against
        # as fast as loopback allows, and `==` short-circuits on the first
        # differing byte, leaking the length of the shared prefix.
        with unittest.mock.patch.object(
            hmac, "compare_digest", wraps=hmac.compare_digest
        ) as compare:
            self.post("/api/events/claude", self.envelope())
        compare.assert_called()

    def test_another_harnesss_capability_does_not_work_here(self) -> None:
        # The point of deriving one token per source: reading an adapter's config
        # must not buy the ability to post as every harness.
        other = self.coordinator.capability("antigravity")
        self.assertNotEqual(self.token, other)
        code, _ = self.post("/api/events/claude", self.envelope(), token=other)
        self.assertEqual(403, code)

    def test_an_unregistered_harness_route_is_a_404_not_a_403(self) -> None:
        # Order matters: answering 403 for a route that does not exist would make
        # the endpoint an oracle for which harnesses have shipped an adapter.
        code, _ = self.post("/api/events/goose", self.envelope(), token=None)
        self.assertEqual(404, code)

    def test_an_empty_harness_segment_is_a_404(self) -> None:
        code, _ = self.post("/api/events/", self.envelope())
        self.assertEqual(404, code)

    def test_with_no_coordinator_the_route_does_not_exist(self) -> None:
        # --no-events. Not a 403: there is nothing to authenticate against.
        code, _ = self.post("/api/events/claude", self.envelope(), coordinator=None)
        self.assertEqual(404, code)

    def test_the_harness_comes_from_the_route_and_not_from_the_body(self) -> None:
        # A body naming its own source would let one adapter's token post as any
        # harness, which is the whole reason the route assigns it.
        code, _ = self.post("/api/events/claude", self.envelope(harness="antigravity"))
        self.assertEqual(200, code)
        self.assertEqual(1, len(self.coordinator.overlays_for("claude", PREFIX)))

    def test_an_oversized_declared_length_is_refused_before_any_read(self) -> None:
        code, _ = self.post(
            "/api/events/claude",
            self.envelope(),
            declared=self.config.event_body_cap_bytes + 1,
        )
        self.assertEqual(413, code)

    def test_a_negative_declared_length_is_refused(self) -> None:
        handler_code, _ = self.post("/api/events/claude", self.envelope(), declared=-1)
        self.assertEqual(413, handler_code)

    def test_the_event_body_cap_is_far_below_the_notification_cap(self) -> None:
        # Nine short fields. A cap sized for a whole notification payload would
        # let an adapter push kilobytes the server then throws away.
        self.assertLess(self.config.event_body_cap_bytes, self.config.notification_body_cap_bytes)

    def test_a_rejected_envelope_still_answers_200(self) -> None:
        # The hook must not learn to retry, and must never be the reason a
        # session stalls. The outcome string carries the diagnosis instead.
        code, body = self.post("/api/events/claude", self.envelope(v=99))
        self.assertEqual(200, code)
        self.assertEqual(events.REJECT_INCOMPATIBLE, json.loads(body)["outcome"])

    def test_a_malformed_body_still_answers_200(self) -> None:
        code, body = self.post("/api/events/claude", b"{not json")
        self.assertEqual(200, code)
        self.assertEqual(events.REJECT_INCOMPATIBLE, json.loads(body)["outcome"])

    def test_a_non_object_body_still_answers_200(self) -> None:
        code, _ = self.post("/api/events/claude", b"[1,2,3]")
        self.assertEqual(200, code)

    def test_a_non_local_request_never_reaches_the_route(self) -> None:
        handler: Any = http_api._RequestHandler.__new__(http_api._RequestHandler)
        handler.headers = {"Content-Length": "0"}
        handler.path = "/api/events/claude"
        handler.rfile = io.BytesIO(b"")
        handler.server = SimpleNamespace(observation=self.coordinator)
        handler._local_ok = lambda **_kw: False
        handler._drain_body = lambda: None
        refused: list[int] = []
        handler.send_error = lambda code, *_a, **_k: refused.append(code)
        handler.do_POST()
        self.assertEqual([403], refused)


class RateCeilingTest(IngressTestCase):
    def test_a_burst_within_the_ceiling_is_accepted(self) -> None:
        for _ in range(self.config.event_burst_max):
            code, _ = self.post("/api/events/claude", self.envelope())
            self.assertEqual(200, code)

    def test_beyond_the_burst_the_source_is_throttled(self) -> None:
        # The ceiling is independent of the capability: a looping or compromised
        # adapter holds a valid token by definition.
        for _ in range(self.config.event_burst_max):
            self.post("/api/events/claude", self.envelope())
        code, _ = self.post("/api/events/claude", self.envelope())
        self.assertEqual(429, code)
        self.assertGreaterEqual(self.coordinator.counters["reject.rate"], 1)

    def test_the_bucket_refills_over_time(self) -> None:
        clock = {"now": NOW}
        self.coordinator.clock = lambda: clock["now"]
        for _ in range(self.config.event_burst_max):
            self.coordinator.within_budget("claude")
        self.assertFalse(self.coordinator.within_budget("claude"))
        clock["now"] += 1.0
        self.assertTrue(self.coordinator.within_budget("claude"))

    def test_one_source_exhausting_its_budget_does_not_throttle_another(self) -> None:
        for _ in range(self.config.event_burst_max + 5):
            self.coordinator.within_budget("claude")
        self.assertFalse(self.coordinator.within_budget("claude"))
        self.assertTrue(self.coordinator.within_budget("antigravity"))

    def test_the_ceiling_is_checked_after_the_capability(self) -> None:
        # Otherwise an unauthenticated flood would consume the budget of the
        # adapter that actually holds the token, and throttle it out.
        for _ in range(self.config.event_burst_max + 10):
            self.post("/api/events/claude", self.envelope(), token="0" * 64)
        code, _ = self.post("/api/events/claude", self.envelope())
        self.assertEqual(200, code)


class CapabilityPublishingTest(unittest.TestCase):
    def test_the_state_file_publishes_a_token_per_registered_harness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = support.make_config(state_dir=Path(tmp), state_home=tmp)
            coordinator = observation.Observation(
                FakeApplication(config),  # type: ignore[arg-type]
                clock=lambda: NOW,
                diagnostic_sink=lambda _message: None,
            )
            lifecycle.write_state(
                config,
                4553,
                started=NOW,
                capabilities=coordinator.capabilities(),
                diagnostic_sink=lambda _message: None,
            )
            written = json.loads(Path(lifecycle.state_path(config, 4553)).read_text())
        self.assertEqual(
            set(events.IDENTITY_NORMALIZERS), set(written["capabilities"]), "token set drifted"
        )
        self.assertEqual(coordinator.capability("claude"), written["capabilities"]["claude"])

    def test_the_secret_itself_is_never_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = support.make_config(state_dir=Path(tmp), state_home=tmp)
            coordinator = observation.Observation(
                FakeApplication(config),  # type: ignore[arg-type]
                clock=lambda: NOW,
                diagnostic_sink=lambda _message: None,
            )
            lifecycle.write_state(
                config,
                4553,
                started=NOW,
                capabilities=coordinator.capabilities(),
                diagnostic_sink=lambda _message: None,
            )
            raw = Path(lifecycle.state_path(config, 4553)).read_bytes()
        self.assertNotIn(coordinator._secret.hex().encode(), raw)
        self.assertNotIn(coordinator._secret, raw)

    @unittest.skipIf(os.name == "nt", "POSIX file modes; Windows ignores them")
    def test_the_state_file_is_owner_only(self) -> None:
        # The token is in this file from its first byte, which is why the mode is
        # in the open() call rather than applied by a later chmod.
        with tempfile.TemporaryDirectory() as tmp:
            config = support.make_config(state_dir=Path(tmp), state_home=tmp)
            lifecycle.write_state(
                config,
                4553,
                started=NOW,
                capabilities={"claude": "t"},
                diagnostic_sink=lambda _message: None,
            )
            mode = stat.S_IMODE(os.stat(lifecycle.state_path(config, 4553)).st_mode)
        self.assertEqual(0o600, mode)

    def test_a_run_without_a_coordinator_publishes_no_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = support.make_config(state_dir=Path(tmp), state_home=tmp)
            lifecycle.write_state(config, 4553, started=NOW, diagnostic_sink=lambda _message: None)
            written = json.loads(Path(lifecycle.state_path(config, 4553)).read_text())
        self.assertNotIn("capabilities", written)

    def test_two_runs_do_not_share_a_token(self) -> None:
        # Per run, not per install. A token recovered from an old state file must
        # be useless against the next dashboard.
        config = support.make_config()
        first = observation.Observation(
            FakeApplication(config),  # type: ignore[arg-type]
            diagnostic_sink=lambda _message: None,
        )
        second = observation.Observation(
            FakeApplication(config),  # type: ignore[arg-type]
            diagnostic_sink=lambda _message: None,
        )
        self.assertNotEqual(first.capability("claude"), second.capability("claude"))


class AdapterTest(unittest.TestCase):
    """`event_hook.py`: the shaping that happens before anything is sent."""

    def test_native_names_map_onto_the_normalized_vocabulary(self) -> None:
        for native, normalized in event_hook.EVENT_NAMES.items():
            with self.subTest(native):
                self.assertIn(normalized, events.EVENT_NAMES)

    def test_a_notification_is_not_promoted_to_a_permission_overlay(self) -> None:
        # Claude Code can emit an input-waiting notification for a session that
        # then carries on running, so it stays standing hook state on the
        # /api/notify path rather than becoming an authoritative overlay.
        self.assertNotIn("Notification", event_hook.EVENT_NAMES)
        self.assertIsNone(
            event_hook.envelope({"hook_event_name": "Notification", "session_id": SESSION})
        )

    def test_an_explicit_permission_request_is_promoted(self) -> None:
        built = event_hook.envelope({"hook_event_name": "PermissionRequest", "session_id": SESSION})
        assert built is not None
        self.assertEqual("input_requested", built["event"])

    def test_precompact_is_not_mapped_and_postcompact_reconciles(self) -> None:
        self.assertNotIn("PreCompact", event_hook.EVENT_NAMES)
        self.assertEqual("reconcile_required", event_hook.EVENT_NAMES["PostCompact"])

    def test_an_unknown_native_name_is_not_forwarded(self) -> None:
        self.assertIsNone(
            event_hook.envelope({"hook_event_name": "SomethingNew", "session_id": SESSION})
        )

    def test_the_prompt_and_the_tool_payload_never_leave_the_hook(self) -> None:
        built = event_hook.envelope(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": SESSION,
                "prompt": "my secret prompt",
                "tool_input": {"command": "cat ~/.ssh/id_rsa"},
                "tool_response": "secret output",
                "cwd": "/w/proj",
            }
        )
        assert built is not None
        self.assertNotIn("my secret prompt", json.dumps(built))
        self.assertNotIn("id_rsa", json.dumps(built))
        self.assertEqual("/w/proj", built["cwd"])

    def test_every_field_it_sends_is_in_the_servers_allowlist(self) -> None:
        built = event_hook.envelope(
            {
                "hook_event_name": "SubagentStart",
                "session_id": SESSION,
                "cwd": "/w/proj",
                "transcript_path": "/store/x.jsonl",
                "agent_id": "child-1",
            }
        )
        assert built is not None
        self.assertLessEqual(set(built), set(events.ALLOWED_FIELDS))
        self.assertEqual("child-1", built["subagent_id"])

    def test_what_it_sends_is_accepted_by_the_server_end_to_end(self) -> None:
        # The two halves agree, rather than each being separately plausible.
        built = event_hook.envelope({"hook_event_name": "Stop", "session_id": SESSION})
        assert built is not None
        parsed = events.parse("claude", built, arrival_seq=1, config=support.make_config(), now=NOW)
        assert isinstance(parsed, events.Event)
        self.assertEqual("turn_stopped", parsed.event)
        self.assertEqual(PREFIX, parsed.sid)

    def test_a_missing_session_id_is_not_forwarded(self) -> None:
        self.assertIsNone(event_hook.envelope({"hook_event_name": "Stop"}))

    def test_the_adapter_version_matches_the_servers(self) -> None:
        self.assertEqual(events.ENVELOPE_VERSION, event_hook.ENVELOPE_VERSION)

    def test_the_capability_is_read_from_the_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cargento-4553.json").write_text(
                json.dumps({"capabilities": {"claude": "the-token"}})
            )
            with unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                self.assertEqual("the-token", event_hook.capability(4553, "claude"))

    def test_a_state_file_without_capabilities_yields_none(self) -> None:
        # An older dashboard, or one started with --no-events. An ordinary state:
        # the adapter simply does not post.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cargento-4553.json").write_text(json.dumps({"pid": 1}))
            with unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                self.assertIsNone(event_hook.capability(4553, "claude"))

    def test_a_missing_state_file_yields_none(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
        ):
            self.assertIsNone(event_hook.capability(4553, "claude"))

    def test_a_state_file_holding_a_scalar_yields_none(self) -> None:
        # A file that parses but is not an object. Cheap to write by accident, and
        # `data.get` would raise on it.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cargento-4553.json").write_text("42")
            with unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                self.assertIsNone(event_hook.capability(4553, "claude"))

    def test_a_non_object_payload_is_not_forwarded(self) -> None:
        self.assertIsNone(event_hook.read_event(b"[1,2,3]"))

    def test_the_shared_transport_resolves_to_the_bundled_notify_hook(self) -> None:
        # Unpatched, so this proves the sys.path insert actually finds the file
        # that ships beside it rather than relying on the test runner's path.
        self.assertIs(notify_hook, event_hook._shared())

    def test_a_port_argument_selects_the_instance(self) -> None:
        payload = json.dumps({"hook_event_name": "Stop", "session_id": SESSION}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cargento-9999.json").write_text(
                json.dumps({"capabilities": {"claude": "nine-token"}})
            )
            forwarded: list[Any] = []
            fake = SimpleNamespace(
                forward=lambda url, _body, headers=None: forwarded.append((url, headers))
            )
            with (
                unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
                unittest.mock.patch.object(event_hook, "_shared", lambda: fake),
                unittest.mock.patch.object(
                    sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload))
                ),
            ):
                self.assertEqual(0, event_hook.main(["event_hook.py", "9999"]))
        self.assertEqual("http://127.0.0.1:9999/api/events/claude", forwarded[0][0])

    def test_a_nonsense_port_argument_falls_back_to_the_default(self) -> None:
        # A hook line someone edited by hand. Exiting non-zero here would surface
        # as an error inside the session, so the argument is best-effort.
        with (
            tempfile.TemporaryDirectory() as tmp,
            unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
            unittest.mock.patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{}"))),
        ):
            self.assertEqual(0, event_hook.main(["event_hook.py", "not-a-port"]))

    def test_a_corrupt_state_file_yields_none_rather_than_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cargento-4553.json").write_text("{not json")
            with unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                self.assertIsNone(event_hook.capability(4553, "claude"))

    def test_it_posts_nothing_without_a_token(self) -> None:
        # A *forwardable* event with no dashboard running. Feeding an empty
        # payload here would prove nothing: it stops at the envelope, before the
        # token is ever looked up, which is what the first version of this test
        # did and why it passed with the token check removed.
        payload = json.dumps({"hook_event_name": "Stop", "session_id": SESSION}).encode()
        self.assertIsNotNone(event_hook.read_event(payload), "the payload must be forwardable")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
                unittest.mock.patch.object(event_hook, "_shared") as shared,
                unittest.mock.patch.object(
                    sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload))
                ),
            ):
                self.assertEqual(0, event_hook.main(["event_hook.py"]))
            shared.assert_not_called()

    def test_it_presents_the_capability_header_when_it_posts(self) -> None:
        payload = json.dumps({"hook_event_name": "Stop", "session_id": SESSION}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cargento-4553.json").write_text(
                json.dumps({"capabilities": {"claude": "the-token"}})
            )
            forwarded: list[Any] = []
            fake = SimpleNamespace(
                forward=lambda url, body, headers=None: forwarded.append((url, body, headers))
            )
            with (
                unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
                unittest.mock.patch.object(event_hook, "_shared", lambda: fake),
                unittest.mock.patch.object(
                    sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload))
                ),
            ):
                self.assertEqual(0, event_hook.main(["event_hook.py"]))
        url, body, headers = forwarded[0]
        self.assertEqual("http://127.0.0.1:4553/api/events/claude", url)
        self.assertEqual({"X-Cargento-Capability": "the-token"}, headers)
        self.assertEqual("turn_stopped", json.loads(body)["event"])

    def test_it_exits_zero_when_stdin_is_absent(self) -> None:
        # A hook that fails must never disturb the agent it reports on.
        with unittest.mock.patch.object(sys, "stdin", SimpleNamespace(buffer=None)):
            self.assertEqual(0, event_hook.main(["event_hook.py"]))

    def test_it_exits_zero_on_a_deeply_nested_payload(self) -> None:
        # RecursionError, not ValueError, and it is not an OSError either. The
        # depth is load-bearing: 400 levels decode fine on CPython, so an earlier
        # version of this test proved nothing. 10,000 is where json actually
        # blows its stack.
        nested = ("[" * 10_000 + "]" * 10_000).encode()
        with unittest.mock.patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(nested))):
            self.assertEqual(0, event_hook.main(["event_hook.py"]))

    def test_the_forwarder_refuses_a_non_loopback_target_without_connecting(self) -> None:
        # The reason the adapter imports notify_hook rather than writing its own
        # transport: this guard has one implementation.
        #
        # Asserting the return value alone proves nothing. With the guard removed
        # the call would attempt evil.example, fail to resolve, and return False
        # anyway. So this asserts no opener is ever built: the request must not be
        # attempted, not merely fail.
        with unittest.mock.patch.object(urllib.request, "build_opener") as opener:
            self.assertFalse(
                notify_hook.forward("http://evil.example/api/events/claude", b"{}", {"X-A": "b"})
            )
        opener.assert_not_called()

    def test_extra_headers_add_to_the_content_type_rather_than_replacing_it(self) -> None:
        # The server parses JSON, so an adapter that supplied a capability header
        # and thereby dropped Content-Type would post an unlabelled body.
        captured: list[Any] = []

        class Opener:
            def open(self, request: Any, timeout: float | None = None) -> Any:  # noqa: ARG002
                captured.append(request)
                return unittest.mock.MagicMock()

        with unittest.mock.patch.object(urllib.request, "build_opener", lambda *_a: Opener()):
            self.assertTrue(
                notify_hook.forward(
                    "http://127.0.0.1:4553/api/events/claude", b"{}", {"X-Cargento-Capability": "t"}
                )
            )
        headers = captured[0].headers
        self.assertEqual("application/json", headers["Content-type"])
        self.assertEqual("t", headers["X-cargento-capability"])
