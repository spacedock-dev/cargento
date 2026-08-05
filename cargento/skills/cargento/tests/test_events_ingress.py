"""The event ingress: the route, the capability, the ceiling, and the adapter."""

from __future__ import annotations

import hmac
import io
import json
import os
import shutil
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
import statusline_hook
from cargento_runtime import events, http_api, lifecycle, observation, quota

from . import support

NOW = 1_700_000_000.0
# Sentinel for "send this run's real token", so the helper's default is not a
# string that reads like a hardcoded credential.
PRESENT = "<this run's capability>"
SESSION = "abcdef12-3456-7890-abcd-ef1234567890"
PREFIX = "abcdef12"
# Codex and Antigravity key on the whole 36-character id, unlike Claude.
CODEX_SESSION = "019fd197-19e4-77b2-913d-d16c3190bb52"
AGY_SESSION = "0e4c3a4d-1111-2222-3333-444455556666"
# A stand-in capability. Not a credential: the real one is minted per run and
# never written into a source file, which is what makes the noqa correct here.
AGY_TOKEN = "<antigravity capability>"  # noqa: S105


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
        # Every harness's table, not just Claude's: a name the server would refuse
        # is a name this adapter should never have sent.
        for harness, table in event_hook.EVENTS_BY_HARNESS.items():
            for native, normalized in table.items():
                with self.subTest(harness=harness, native=native):
                    self.assertIn(normalized, events.EVENT_NAMES)

    def test_a_notification_is_not_promoted_to_a_permission_overlay(self) -> None:
        # Claude Code can emit an input-waiting notification for a session that
        # then carries on running, so it stays standing hook state on the
        # /api/notify path rather than becoming an authoritative overlay.
        self.assertNotIn("Notification", event_hook.CLAUDE_EVENTS)
        self.assertIsNone(
            event_hook.envelope(
                {"hook_event_name": "Notification", "session_id": SESSION}, "claude"
            )
        )

    def test_an_explicit_permission_request_is_promoted(self) -> None:
        built = event_hook.envelope({"hook_event_name": "PermissionRequest", "session_id": SESSION})
        assert built is not None
        self.assertEqual("input_requested", built["event"])

    def test_precompact_is_not_mapped_and_postcompact_reconciles(self) -> None:
        self.assertNotIn("PreCompact", event_hook.CLAUDE_EVENTS)
        self.assertEqual("reconcile_required", event_hook.CLAUDE_EVENTS["PostCompact"])

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
                self.assertEqual(0, event_hook.main(["event_hook.py", "claude", "9999"]))
        self.assertEqual("http://127.0.0.1:9999/api/events/claude", forwarded[0][0])

    def test_a_nonsense_port_argument_falls_back_to_the_default(self) -> None:
        # A hook line someone edited by hand. Exiting non-zero here would surface
        # as an error inside the session, so the argument is best-effort.
        with (
            tempfile.TemporaryDirectory() as tmp,
            unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
            unittest.mock.patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{}"))),
        ):
            self.assertEqual(0, event_hook.main(["event_hook.py", "claude", "not-a-port"]))

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
                self.assertEqual(0, event_hook.main(["event_hook.py", "claude"]))
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
                self.assertEqual(0, event_hook.main(["event_hook.py", "claude"]))
        url, body, headers = forwarded[0]
        self.assertEqual("http://127.0.0.1:4553/api/events/claude", url)
        self.assertEqual({"X-Cargento-Capability": "the-token"}, headers)
        self.assertEqual("turn_stopped", json.loads(body)["event"])

    def test_it_exits_zero_when_stdin_is_absent(self) -> None:
        # A hook that fails must never disturb the agent it reports on.
        with unittest.mock.patch.object(sys, "stdin", SimpleNamespace(buffer=None)):
            self.assertEqual(0, event_hook.main(["event_hook.py", "claude"]))

    def test_it_exits_zero_on_a_deeply_nested_payload(self) -> None:
        # RecursionError, not ValueError, and it is not an OSError either. The
        # depth is load-bearing: 400 levels decode fine on CPython, so an earlier
        # version of this test proved nothing. 10,000 is where json actually
        # blows its stack.
        nested = ("[" * 10_000 + "]" * 10_000).encode()
        with unittest.mock.patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(nested))):
            self.assertEqual(0, event_hook.main(["event_hook.py", "claude"]))

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


class CodexAdapterTest(unittest.TestCase):
    """Codex, whose mapping was measured rather than assumed."""

    def envelope(self, native: str, **extra: Any) -> dict[str, Any] | None:
        payload = {"hook_event_name": native, "session_id": CODEX_SESSION, **extra}
        return event_hook.envelope(payload, "codex")

    def test_the_id_is_carried_whole_with_no_truncation(self) -> None:
        # Codex keys on its own full session id, which the capture confirmed
        # against the rollout the same session wrote. Truncating it the way
        # Claude's is truncated would key on a row that does not exist.
        built = self.envelope("Stop")
        assert built is not None
        self.assertEqual(CODEX_SESSION, built["session_id"])

    def test_the_server_accepts_what_the_codex_adapter_sends(self) -> None:
        built = self.envelope("UserPromptSubmit", prompt="secret", cwd="/w/proj")
        assert built is not None
        parsed = events.parse("codex", built, arrival_seq=1, config=support.make_config(), now=NOW)
        assert isinstance(parsed, events.Event)
        self.assertEqual("turn_started", parsed.event)
        self.assertEqual(CODEX_SESSION, parsed.sid, "the sid must be the whole id")

    def test_the_captured_field_set_is_what_the_adapter_reads(self) -> None:
        # The real PostToolUse payload, by field name, from docs/captures. Nothing
        # but the allowlist survives, and the tool payload in particular does not.
        built = self.envelope(
            "PostToolUse",
            cwd="/w/proj",
            model="gpt-5",
            permission_mode="auto",
            tool_input={"command": "cat ~/.ssh/id_rsa"},
            tool_name="Bash",
            tool_response="secret output",
            tool_use_id="t1",
            transcript_path="/store/rollout.jsonl",
            turn_id="turn-1",
        )
        assert built is not None
        self.assertLessEqual(set(built), set(events.ALLOWED_FIELDS))
        self.assertNotIn("id_rsa", json.dumps(built))
        self.assertNotIn("gpt-5", json.dumps(built))

    def test_pretooluse_is_deliberately_not_forwarded(self) -> None:
        # It fires, and it means a tool is about to run. PostToolUse reports the
        # same turn once the store has actually changed, so forwarding both would
        # double every tool call for no gain.
        self.assertIsNone(self.envelope("PreToolUse"))

    def test_unmeasured_codex_hooks_are_not_mapped(self) -> None:
        # Codex documents subagent and permission hooks, and its config records
        # state keys for them, but the captured turn used neither so their payload
        # shape is unknown. They go in when a capture shows them.
        for native in ("SubagentStart", "SubagentStop", "PermissionRequest"):
            with self.subTest(native):
                self.assertIsNone(self.envelope(native))

    def test_a_codex_hook_posts_to_the_codex_route_with_the_codex_token(self) -> None:
        # Both halves, because both were hardcoded to Claude at one point and
        # neither the route nor the token was pinned for a second harness. A wrong
        # route 404s; a wrong token 403s. Either way the events vanish silently.
        payload = json.dumps({"hook_event_name": "Stop", "session_id": CODEX_SESSION}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cargento-4553.json").write_text(
                json.dumps({"capabilities": {"claude": "claude-token", "codex": "codex-token"}})
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
                self.assertEqual(0, event_hook.main(["event_hook.py", "codex"]))
        url, headers = forwarded[0]
        self.assertEqual("http://127.0.0.1:4553/api/events/codex", url)
        self.assertEqual({"X-Cargento-Capability": "codex-token"}, headers)

    def test_an_unknown_harness_forwards_nothing(self) -> None:
        self.assertIsNone(event_hook.envelope({"hook_event_name": "Stop"}, "goose"))

    def test_main_refuses_an_unknown_harness(self) -> None:
        with (
            unittest.mock.patch.object(event_hook, "_shared") as shared,
            unittest.mock.patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{}"))),
        ):
            self.assertEqual(0, event_hook.main(["event_hook.py", "goose"]))
        shared.assert_not_called()

    def test_the_bundled_codex_hooks_only_register_measured_events(self) -> None:
        # The shipped hooks file and the adapter's table have to agree: a hook
        # registered for an event the adapter drops runs a process for nothing,
        # and one the adapter maps but nothing registers never fires.
        bundled = json.loads(
            (Path(__file__).resolve().parents[3] / "hooks" / "codex-hooks.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(set(event_hook.CODEX_EVENTS), set(bundled["hooks"]))

    def test_the_bundled_claude_hooks_only_register_events_the_adapter_maps(self) -> None:
        # Same contract as the Codex file: a hook registered for an event the
        # adapter drops runs a process for nothing, and one the adapter maps but
        # nothing registers never fires. Claude registers every mapped name,
        # including the two the Codex capture could not reach.
        bundled = json.loads(
            (Path(__file__).resolve().parents[3] / "hooks" / "hooks.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(set(event_hook.CLAUDE_EVENTS), set(bundled["hooks"]))

    def test_the_bundled_claude_hooks_use_the_plugin_root_variable(self) -> None:
        bundled = json.loads(
            (Path(__file__).resolve().parents[3] / "hooks" / "hooks.json").read_text(
                encoding="utf-8"
            )
        )
        commands = {
            hook["command"]
            for groups in bundled["hooks"].values()
            for group in groups
            for hook in group["hooks"]
        }
        self.assertEqual(1, len(commands), "one command keeps one trust decision")
        command = next(iter(commands))
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)
        self.assertTrue(command.endswith(" claude"), command)

    def test_the_two_bundled_files_do_not_post_as_each_other(self) -> None:
        # The reason byte parity between them had to go. A mirrored file would
        # make one harness post to the other's route, where Claude's normalizer
        # would truncate a Codex id and match no row.
        root = Path(__file__).resolve().parents[3] / "hooks"
        claude = root.joinpath("hooks.json").read_text(encoding="utf-8")
        codex = root.joinpath("codex-hooks.json").read_text(encoding="utf-8")
        self.assertIn(" claude", claude)
        self.assertNotIn(" codex", claude)
        self.assertIn(" codex", codex)
        self.assertNotIn(" claude", codex)

    def test_the_bundled_hooks_name_the_harness_and_use_a_stable_path(self) -> None:
        # Codex records a trusted_hash over the hook definition, so a command that
        # interpolated a version or a port would re-prompt on every upgrade.
        bundled = json.loads(
            (Path(__file__).resolve().parents[3] / "hooks" / "codex-hooks.json").read_text(
                encoding="utf-8"
            )
        )
        commands = {
            hook["command"]
            for groups in bundled["hooks"].values()
            for group in groups
            for hook in group["hooks"]
        }
        self.assertEqual(1, len(commands), "one command for every event keeps one trust record")
        command = next(iter(commands))
        self.assertIn("event_hook.py", command)
        self.assertTrue(command.endswith(" codex"), command)
        self.assertIn("${PLUGIN_ROOT}", command)


class AntigravityAdapterTest(unittest.TestCase):
    """Antigravity, from 37 real status-line pushes across two sessions."""

    def payload(self, **overrides: Any) -> dict[str, Any]:
        # The captured field set. Values are stand-ins; the names are real.
        payload: dict[str, Any] = {
            "agent_state": "working",
            "conversation_id": AGY_SESSION,
            "session_id": AGY_SESSION,
            "cwd": "/w/proj",
            "email": "someone@example.com",
            "transcript_path": "/store/secret.jsonl",
            "plan_tier": "Google AI Ultra",
            "model": {"id": "Gemini 3.6 Flash (High)", "effort": "high"},
            "product": "antigravity",
            "quota": {"gemini-5h": {"remaining_fraction": 0.5}},
            "context_window": 200_000,
            "exceeds_200k_tokens": False,
            "sandbox": False,
            "terminal_width": 120,
            "vcs": "git",
            "version": "1.0",
            "workspace": "/w",
        }
        payload.update(overrides)
        return payload

    def test_working_and_idle_are_the_only_states_that_assert_anything(self) -> None:
        self.assertEqual("turn_started", (self.envelope_for("working") or {}).get("event"))
        self.assertEqual("turn_stopped", (self.envelope_for("idle") or {}).get("event"))

    def envelope_for(self, state: str) -> dict[str, Any] | None:
        return statusline_hook.envelope(self.payload(agent_state=state))

    def test_authenticating_asserts_nothing(self) -> None:
        # Observed in the capture. It says the CLI is talking to an auth service,
        # which is neither Working nor Idle, and mapping it either way would invent
        # a claim about the session.
        self.assertIsNone(self.envelope_for("authenticating"))

    def test_there_is_no_needs_input_mapping_because_there_is_no_signal(self) -> None:
        # tool_confirmation_pending does not exist in the payload. 37 pushes across
        # two sessions carried no confirmation field under any spelling, so a
        # permission wait is not observable here and must not be manufactured.
        self.assertNotIn("input_requested", set(statusline_hook.AGENT_STATES.values()))
        self.assertNotIn("tool_confirmation_pending", self.payload())

    def test_the_id_matches_what_the_collector_keys_on(self) -> None:
        built = self.envelope_for("working")
        assert built is not None
        self.assertEqual(AGY_SESSION, built["session_id"])
        parsed = events.parse(
            "antigravity", built, arrival_seq=1, config=support.make_config(), now=NOW
        )
        assert isinstance(parsed, events.Event)
        self.assertEqual(AGY_SESSION, parsed.sid)

    def test_conversation_id_is_preferred_over_session_id(self) -> None:
        # They held the same value in every capture. Preferring the durable one by
        # name means a future divergence resolves to the id the collector reads
        # rather than to whichever field was checked first.
        payload = self.payload(conversation_id=AGY_SESSION, session_id="f" * 36)
        self.assertEqual(AGY_SESSION, statusline_hook.conversation_id(payload))

    def test_session_id_is_the_fallback_when_conversation_id_is_absent(self) -> None:
        payload = self.payload()
        del payload["conversation_id"]
        self.assertEqual(AGY_SESSION, statusline_hook.conversation_id(payload))

    def test_a_short_id_is_refused(self) -> None:
        payload = self.payload(conversation_id="abc", session_id="abc")
        self.assertIsNone(statusline_hook.conversation_id(payload))

    def test_an_empty_id_yields_no_event_at_all(self) -> None:
        # Measured: 14 of 37 pushes carried a present-but-blank id, including ten
        # of the eleven idle ones. An event with no id cannot be keyed to a row, so
        # the adapter sends nothing rather than sending something unattachable.
        payload = self.payload(agent_state="idle", conversation_id="", session_id="")
        self.assertIsNone(statusline_hook.conversation_id(payload))
        self.assertIsNone(statusline_hook.envelope(payload))

    def test_working_is_reportable_and_idle_often_is_not(self) -> None:
        # The honest consequence of the finding above, pinned so a later change
        # cannot quietly assume Idle arrives reliably. The Working overlay's
        # deadline is what covers the missing transition.
        with_id = self.payload(agent_state="working")
        without = self.payload(agent_state="idle", conversation_id="", session_id="")
        self.assertIsNotNone(statusline_hook.envelope(with_id))
        self.assertIsNone(statusline_hook.envelope(without))

    def test_the_event_envelope_leaks_nothing(self) -> None:
        built = self.envelope_for("working")
        assert built is not None
        self.assertLessEqual(set(built), set(events.ALLOWED_FIELDS))
        rendered = json.dumps(built)
        for secret in ("someone@example.com", "secret.jsonl", "Google AI Ultra", "Gemini"):
            self.assertNotIn(secret, rendered)

    def test_the_usage_envelope_is_the_quota_block_and_nothing_else(self) -> None:
        # SECURITY.md: /api/usage does not need the account email or the whole
        # status-line document merely because it needs quota.
        usage = statusline_hook.usage_envelope(self.payload())
        self.assertEqual({"quota"}, set(usage or {}))
        self.assertNotIn("someone@example.com", json.dumps(usage))

    def test_the_minimal_usage_envelope_still_feeds_the_quota_band(self) -> None:
        # The regression this repo has already been warned about: a global minimal
        # envelope that kills the usage band silently. Shaped here, then run
        # through the server's own shaper to prove an entry still comes out.
        usage = statusline_hook.usage_envelope(
            self.payload(
                quota={
                    "gemini-5h": {"remaining_fraction": 0.25, "reset_time": "2026-08-04T14:16:36Z"},
                    "gemini-weekly": {
                        "remaining_fraction": 0.5,
                        "reset_time": "2026-08-04T14:16:36Z",
                    },
                }
            )
        )
        assert usage is not None
        entries = quota.shape_statusline(usage, NOW)
        self.assertEqual(1, len(entries), "the usage band lost its entry")
        self.assertEqual(75, entries[0]["fiveH"]["pct"])

    def test_no_quota_block_yields_no_usage_post(self) -> None:
        payload = self.payload()
        del payload["quota"]
        self.assertIsNone(statusline_hook.usage_envelope(payload))


class StatuslineDedupeTest(unittest.TestCase):
    """The status line fired 13 and 24 times for two short turns."""

    def payload(self, state: str = "working", quota: Any = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"agent_state": state, "conversation_id": AGY_SESSION}
        if quota is not None:
            payload["quota"] = quota
        return payload

    def test_an_unchanged_state_posts_nothing(self) -> None:
        event, _usage = statusline_hook.decide(self.payload(), {}, now=NOW)
        assert event is not None
        memo = statusline_hook.commit({}, event=event)
        again, _u2 = statusline_hook.decide(self.payload(), memo, now=NOW + 1)
        self.assertIsNone(again, "reposted the same state")

    def test_a_changed_state_posts_again(self) -> None:
        first, _u = statusline_hook.decide(self.payload("working"), {}, now=NOW)
        memo = statusline_hook.commit({}, event=first)
        event, _u2 = statusline_hook.decide(self.payload("idle"), memo, now=NOW + 1)
        assert event is not None
        self.assertEqual("turn_stopped", event["event"])

    def test_quota_is_forwarded_on_its_own_interval(self) -> None:
        # Independent of the state, because quota changes on its own schedule.
        quota_block = {"gemini-5h": {"remaining_fraction": 1.0}}
        _e, usage = statusline_hook.decide(self.payload(quota=quota_block), {}, now=NOW)
        self.assertIsNotNone(usage)
        memo = statusline_hook.commit({}, quota_at=NOW)
        _e2, usage2 = statusline_hook.decide(self.payload(quota=quota_block), memo, now=NOW + 1)
        self.assertIsNone(usage2, "reposted quota on the next render")
        _e3, usage3 = statusline_hook.decide(
            self.payload(quota=quota_block),
            memo,
            now=NOW + statusline_hook.QUOTA_INTERVAL_SEC + 1,
        )
        self.assertIsNotNone(usage3)

    def test_a_run_of_identical_pushes_costs_one_post(self) -> None:
        # The measured shape: 24 pushes, mostly repeating "working".
        memo: dict[str, Any] = {}
        posts = 0
        for i in range(24):
            event, _usage = statusline_hook.decide(self.payload(), memo, now=NOW + i)
            posts += event is not None
            memo = statusline_hook.commit(memo, event=event)
        self.assertEqual(1, posts)

    def test_the_memo_never_holds_anything_but_the_state_and_a_stamp(self) -> None:
        event, _u = statusline_hook.decide(
            self.payload(quota={"gemini-5h": {"remaining_fraction": 1.0}}), {}, now=NOW
        )
        memo = statusline_hook.commit({}, event=event, quota_at=NOW)
        self.assertLessEqual(set(memo), {"event", "quota_at"})

    def test_an_undelivered_event_is_not_recorded_as_delivered(self) -> None:
        # Found by mutation analysis, and it was a real bug. An event worth
        # sending but unsendable, because no dashboard had published a capability
        # yet, was recorded in the memo anyway. The next push deduped against it,
        # so once the dashboard appeared the row sat without its overlay until the
        # state happened to change again.
        event, _u = statusline_hook.decide(self.payload("working"), {}, now=NOW)
        assert event is not None
        memo = statusline_hook.commit({}, event=None, quota_at=NOW)
        self.assertNotIn("event", memo)
        again, _u2 = statusline_hook.decide(self.payload("working"), memo, now=NOW + 1)
        self.assertIsNotNone(again, "the undelivered event was never retried")

    def test_the_status_line_always_prints_and_always_exits_zero(self) -> None:
        # A status-line command that prints nothing blanks the user's status bar,
        # and one that exits non-zero gets auto-disabled after repeated failures.
        with (
            unittest.mock.patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{}"))),
            unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            code = statusline_hook.main(["statusline_hook.py"])
        self.assertEqual(0, code)
        self.assertTrue(out.getvalue().endswith("\n"))

    def test_a_malformed_push_still_exits_zero(self) -> None:
        with (
            unittest.mock.patch.object(
                sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{not json"))
            ),
            unittest.mock.patch("sys.stdout", new_callable=io.StringIO),
        ):
            self.assertEqual(0, statusline_hook.main(["statusline_hook.py"]))


class StatuslinePushTest(unittest.TestCase):
    """The dual-destination push, and the memo it keeps between renders."""

    def setUp(self) -> None:
        self.home = tempfile.mkdtemp(prefix="cargento-statusline-")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.env = unittest.mock.patch.dict(os.environ, {"CARGENTO_HOME": self.home})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.posts: list[tuple[str, Any, Any]] = []
        self.fake = SimpleNamespace(
            forward=lambda url, body, headers=None: self.posts.append(
                (url, json.loads(body), headers)
            )
        )

    def payload(self, **overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agent_state": "working",
            "conversation_id": AGY_SESSION,
            "session_id": AGY_SESSION,
            "email": "someone@example.com",
            "quota": {"gemini-5h": {"remaining_fraction": 0.5}},
        }
        payload.update(overrides)
        return payload

    def write_capability(self, token: str = AGY_TOKEN) -> None:
        Path(self.home, "cargento-4553.json").write_text(
            json.dumps({"capabilities": {"antigravity": token}})
        )

    def push(self, payload: dict[str, Any]) -> None:
        with unittest.mock.patch.object(statusline_hook, "_shared", lambda: self.fake):
            statusline_hook._push(payload, 4553)

    def test_one_push_reaches_both_destinations(self) -> None:
        self.write_capability()
        self.push(self.payload())
        routes = [url for url, _body, _headers in self.posts]
        self.assertEqual(
            [
                "http://127.0.0.1:4553/api/usage",
                "http://127.0.0.1:4553/api/events/antigravity",
            ],
            routes,
        )

    def test_the_usage_post_is_unauthenticated_and_the_event_post_is_not(self) -> None:
        # /api/usage has always been unauthenticated and its exposure is already
        # documented; a lifecycle overlay is more powerful and needs the token.
        self.write_capability()
        self.push(self.payload())
        usage, event = self.posts
        self.assertIsNone(usage[2])
        self.assertEqual({"X-Cargento-Capability": AGY_TOKEN}, event[2])

    def test_quota_still_reaches_the_band_with_no_capability(self) -> None:
        # The regression that would matter most: installing this script on a
        # dashboard that publishes no capability, or one run with --no-events, must
        # not silently kill the usage band the user already had.
        self.push(self.payload())
        self.assertEqual(["http://127.0.0.1:4553/api/usage"], [url for url, _b, _h in self.posts])
        self.assertEqual({"quota"}, set(self.posts[0][1]))

    def test_the_event_post_carries_no_account_email(self) -> None:
        self.write_capability()
        self.push(self.payload())
        self.assertNotIn("someone@example.com", json.dumps(self.posts))

    def test_a_second_identical_push_posts_nothing(self) -> None:
        self.write_capability()
        self.push(self.payload())
        self.posts.clear()
        self.push(self.payload())
        self.assertEqual([], self.posts, "reposted an unchanged state")

    def test_a_state_change_posts_the_event_again(self) -> None:
        self.write_capability()
        self.push(self.payload())
        self.posts.clear()
        self.push(self.payload(agent_state="idle"))
        self.assertEqual(
            ["http://127.0.0.1:4553/api/events/antigravity"],
            [url for url, _b, _h in self.posts],
        )

    def test_the_memo_survives_between_processes(self) -> None:
        # A status-line command is a fresh process on every render, so the memo has
        # to be on disk or the deduplication does nothing at all.
        self.write_capability()
        self.push(self.payload())
        memo = statusline_hook.read_memo(AGY_SESSION)
        self.assertEqual("turn_started", memo.get("event"))

    def test_the_memo_is_per_conversation(self) -> None:
        self.write_capability()
        other = "1111aaaa-2222-3333-4444-555566667777"
        self.push(self.payload())
        self.posts.clear()
        self.push(self.payload(conversation_id=other, session_id=other))
        self.assertIn(
            "http://127.0.0.1:4553/api/events/antigravity",
            [url for url, _b, _h in self.posts],
            "a second conversation was deduped against the first",
        )

    def test_a_push_with_no_id_posts_nothing_at_all(self) -> None:
        self.write_capability()
        self.push(self.payload(conversation_id="", session_id=""))
        self.assertEqual([], self.posts)

    def test_an_unreadable_memo_is_treated_as_empty(self) -> None:
        self.write_capability()
        Path(self.home, f"statusline-antigravity-{AGY_SESSION}.json").write_text("{not json")
        self.push(self.payload())
        self.assertTrue(self.posts, "a corrupt memo suppressed the push")

    def test_the_capability_is_read_per_port(self) -> None:
        self.write_capability()
        self.assertEqual(AGY_TOKEN, statusline_hook.capability(4553))
        self.assertIsNone(statusline_hook.capability(9999))

    def test_a_state_home_that_cannot_be_written_costs_a_duplicate_not_a_crash(self) -> None:
        self.write_capability()
        with unittest.mock.patch.object(os, "makedirs", side_effect=OSError("read only")):
            self.push(self.payload())
            self.posts.clear()
            self.push(self.payload())
        self.assertTrue(self.posts, "a failed memo write must not stop the next push")
