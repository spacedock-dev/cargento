from __future__ import annotations

import http.client
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import mock

from cargento_runtime import claude_data, notifications, records

from .support import (
    HOOK_PATH,
    LegacyDashboardTestCase,
    collect_claude,
    dashboard,
    dashboard_hook,
    make_config,
    make_server,
    notify_handler,
    serve_until_closed,
)

if TYPE_CHECKING:
    import email.message


class CargentoServerTest(LegacyDashboardTestCase):
    def test_popup_caches_are_bounded_and_globally_rate_limited(self) -> None:
        with (
            mock.patch.object(dashboard, "MAX_CACHE_ENTRIES", 2),
            # session2 lands inside the 15s global floor and is dropped;
            # session3 lands after it and fires.
            mock.patch.object(dashboard.time, "time", side_effect=[100.0, 101.0, 120.0]),
        ):
            config, state = dashboard._legacy_runtime()
            fired: list[tuple[str, str]] = []

            def notifier(title: str, message: str) -> None:
                fired.append((title, message))

            for sid, detail in (("session1", "one"), ("session2", "two"), ("session3", "three")):
                notifications.maybe_popup(
                    config, state, sid, "needs_input", detail, popup_notifier=notifier
                )

        self.assertEqual(2, len(fired))
        self.assertLessEqual(len(dashboard._last_state), 2)
        self.assertLessEqual(len(dashboard._last_popup), 2)

    def test_hook_popups_respect_both_cooldown_floors(self) -> None:
        # Every existing cooldown test expires the floors first to isolate some
        # other rule, so the two floors themselves went unpinned. Distinct
        # messages here keep the repeat-suppression window out of the result.
        config, state = dashboard._legacy_runtime()
        fired: list[str] = []

        def payload(sid: str, message: str, now: float) -> dict[str, Any]:
            return notifications.handle_payload(
                config,
                state,
                {"session_id": sid, "message": message},
                now=now,
                popup_notifier=lambda _title, body: fired.append(body),
            )

        # Same session inside the 60s per-session cooldown, but past the 15s
        # global floor, so only the per-session rule can stop the second one.
        # A 1s gap here would prove nothing: the global floor would mask it.
        payload("aaaaaaaa", "permission one", 1000.0)
        payload("aaaaaaaa", "permission two", 1000.0 + config.global_popup_cooldown_sec + 1)
        self.assertEqual(["permission one"], fired)
        payload("aaaaaaaa", "permission three", 1000.0 + config.popup_cooldown_sec)
        self.assertEqual(["permission one", "permission three"], fired)

        # A different session has its own cooldown key, so only the 15s global
        # floor can stop it.
        fired.clear()
        base = 5000.0
        payload("bbbbbbbb", "b one", base)
        payload("cccccccc", "c one", base + 1)
        self.assertEqual(["b one"], fired)
        payload("dddddddd", "d one", base + config.global_popup_cooldown_sec)
        self.assertEqual(["b one", "d one"], fired)

    def test_hook_popup_runs_with_the_hook_lock_released(self) -> None:
        # hook_lock is a plain Lock. Notifying inside the critical section would
        # hold it for the notifier's whole duration -- up to osascript's 5s
        # timeout -- stalling every other hook POST and every collection.
        config, state = dashboard._legacy_runtime()
        held: list[bool] = []

        def notifier(_title: str, _message: str) -> None:
            acquired = state.hook_lock.acquire(blocking=False)
            held.append(acquired)
            if acquired:
                state.hook_lock.release()

        notifications.handle_payload(
            config,
            state,
            {"session_id": "eeeeeeee", "message": "permission needed"},
            now=9000.0,
            popup_notifier=notifier,
        )
        self.assertEqual([True], held, "popup fired while still holding hook_lock")

    def _post_notify(self, port: int, body: dict[str, Any]) -> bytes:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request(
            "POST",
            "/api/notify",
            body=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        self.assertEqual(200, response.status)
        data = response.read()
        conn.close()
        return data

    def test_notify_from_subagent_session_is_suppressed(self) -> None:
        # Subagent sessions emit Notification-hook events too (permission
        # prompts inside agents); they must not raise popups or hook state.
        now = dashboard.time.time()
        child_id = "cccc3333-0000-0000-0000-000000000000"
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            (proj / f"{child_id}.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "agentName": "helper",
                        "teamName": "session-aaaa1111",
                        "timestamp": dashboard.datetime.fromtimestamp(
                            now, dashboard.UTC
                        ).isoformat(),
                        "message": {"role": "user", "content": "x"},
                    }
                )
                + "\n"
            )
            # The store patch has to be in place BEFORE the server is built: the
            # application captures its config once, at construction, so a patch
            # applied afterwards would not reach the running instance.
            with mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")):
                httpd = make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with mock.patch.object(notifications, "notify_mac") as notify:
                    data = self._post_notify(
                        httpd.server_port,
                        {"session_id": child_id, "message": "permission"},
                    )
                self.assertIn(b"suppressed", data)
                notify.assert_not_called()
                with dashboard._lock:
                    self.assertNotIn(child_id[:8], dashboard._hook_notifs)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_notify_repeated_identical_message_popups_once(self) -> None:
        # Claude re-emits the same notification while a session stays blocked;
        # only the first within the suppression window may popup. A different
        # message from the same session still pops.
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def expire_cooldowns() -> None:
            with dashboard._lock:
                dashboard._last_popup["fedcba98"] = dashboard.time.time() - 120
                dashboard._last_popup["_global"] = dashboard.time.time() - 120

        try:
            with mock.patch.object(notifications, "notify_mac") as notify:
                self._post_notify(
                    httpd.server_port,
                    {"session_id": "fedcba98", "message": "permission needed"},
                )
                self.assertEqual(1, notify.call_count)
                expire_cooldowns()
                self._post_notify(
                    httpd.server_port,
                    {"session_id": "fedcba98", "message": "permission needed"},
                )
                self.assertEqual(1, notify.call_count)  # identical: suppressed
                expire_cooldowns()
                self._post_notify(
                    httpd.server_port,
                    {"session_id": "fedcba98", "message": "open question"},
                )
                self.assertEqual(2, notify.call_count)  # new message: pops
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_hook_without_marker_clears_on_newer_parsed_event(self) -> None:
        # Payloads without transcript_path (the documented curl simulation,
        # older Claude Code versions) get no user-event marker; they must
        # fall back to the parsed-timestamp rule instead of sticking forever.
        _config, state = dashboard._legacy_runtime()
        with dashboard._lock:
            dashboard._hook_notifs["cafe1234"] = {"ts": 1000.0, "message": "hi"}
        self.assertIsNotNone(notifications.current_hook(state, "cafe1234", None, 999.0))
        self.assertIsNone(notifications.current_hook(state, "cafe1234", None, 1001.0))
        with dashboard._lock:
            self.assertNotIn("cafe1234", dashboard._hook_notifs)

    def test_hook_does_not_mark_actively_working_session_blocked(self) -> None:
        # Claude Code emits "waiting for your input" notifications for
        # sessions that keep running via background tasks (live case
        # 936f2c2b). While the transcript still receives events, the session
        # reads Working; the hook only surfaces once the session goes quiet.
        now = dashboard.time.time()
        session_id = "dddd4444-0000-0000-0000-000000000000"

        def transcript(last_offset: float) -> str:
            iso_new = dashboard.datetime.fromtimestamp(now - last_offset, dashboard.UTC).isoformat()
            return (
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": session_id,
                        "uuid": "u-1",
                        "timestamp": dashboard.datetime.fromtimestamp(
                            now - 900, dashboard.UTC
                        ).isoformat(),
                        "message": {"role": "user", "content": "kick off reviews"},
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "system",
                        "sessionId": session_id,
                        "timestamp": iso_new,
                        "content": "background shell event",
                    }
                )
                + "\n"
            )

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            fp = proj / f"{session_id}.jsonl"

            def collect_with(last_offset: float) -> dict[str, Any]:
                fp.write_text(transcript(last_offset))
                with dashboard._lock:
                    dashboard._hook_notifs[session_id[:8]] = {
                        "ts": now - 60,
                        "message": "Claude is waiting for your input",
                        "user_event": "u-1",  # marker unchanged: hook uncleared
                    }
                with (
                    mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                    mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
                ):
                    sessions = collect_claude(now, 24, False)
                return next(s for s in sessions if s["session"] == session_id[:8])

            fresh = collect_with(5)  # events still flowing -> working
            self.assertEqual("working", fresh["state"])
            # NOTE: os.utime so mtime matches the stale story
            fp.write_text(transcript(600))
            old = now - 600
            dashboard.os.utime(fp, (old, old))
            with dashboard._lock:
                dashboard._hook_notifs[session_id[:8]] = {
                    "ts": now - 60,
                    "message": "Claude is waiting for your input",
                    "user_event": "u-1",
                }
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                sessions = collect_claude(now, 24, False)
            quiet = next(s for s in sessions if s["session"] == session_id[:8])
            self.assertEqual("needs_input", quiet["state"])

    def test_idle_nudge_pops_but_never_marks_session_blocked(self) -> None:
        # Claude Code emits "Claude is waiting for your input" after EVERY
        # completed turn. That is the dashboard's own definition of idle —
        # it may popup once as a nudge but must never flip a session to
        # needs_input. Permission prompts (different message) still do.
        now = dashboard.time.time()
        session_id = "ffff6666-0000-0000-0000-000000000000"
        old_iso = dashboard.datetime.fromtimestamp(now - 600, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            fp = proj / f"{session_id}.jsonl"
            fp.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": session_id,
                        "uuid": "u-1",
                        "timestamp": old_iso,
                        "message": {"role": "user", "content": "do the thing"},
                    }
                )
                + "\n"
            )
            old = now - 600
            dashboard.os.utime(fp, (old, old))
            httpd = make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with (
                    mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                    mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
                    mock.patch.object(notifications, "notify_mac") as notify,
                ):
                    # Idle nudge: pops once, no blocked state, no stored hook.
                    self._post_notify(
                        httpd.server_port,
                        {
                            "session_id": session_id,
                            "message": "Claude is waiting for your input",
                            "transcript_path": str(fp),
                        },
                    )
                    self.assertEqual(1, notify.call_count)
                    with dashboard._lock:
                        self.assertNotIn(session_id[:8], dashboard._hook_notifs)
                    sessions = collect_claude(now, 24, False)
                    target = next(s for s in sessions if s["session"] == session_id[:8])
                    self.assertEqual("idle", target["state"])

                    # A permission prompt still blocks when the session is quiet.
                    self._post_notify(
                        httpd.server_port,
                        {
                            "session_id": session_id,
                            "message": "Claude needs your permission to use Bash",
                            "transcript_path": str(fp),
                        },
                    )
                    sessions = collect_claude(now, 24, False)
                    target = next(s for s in sessions if s["session"] == session_id[:8])
                    self.assertEqual("needs_input", target["state"])
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_structured_notification_type_overrides_message_text(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch.object(notifications, "notify_mac") as notify:
                # Informational notifications neither block nor claim that
                # Claude is waiting on the human.
                self._post_notify(
                    httpd.server_port,
                    {
                        "session_id": "aaaa1111",
                        "hook_event_name": "Notification",
                        "notification_type": "auth_success",
                        "message": "Authentication successful",
                    },
                )
                self.assertEqual(0, notify.call_count)
                self.assertNotIn("aaaa1111", dashboard._hook_notifs)

                # Structured idle type wins even when the message is a
                # version/localization variant that lacks the old prefix, and
                # clears any older standing prompt for this session.
                with dashboard._lock:
                    dashboard._hook_notifs["bbbb2222"] = {
                        "ts": dashboard.time.time() - 60,
                        "message": "older permission prompt",
                    }
                    dashboard._last_state["bbbb2222"] = "needs_input"
                self._post_notify(
                    httpd.server_port,
                    {
                        "session_id": "bbbb2222",
                        "hook_event_name": "Notification",
                        "notification_type": "idle_prompt",
                        "message": "Your agent has finished its turn",
                    },
                )
                self.assertEqual(1, notify.call_count)
                self.assertNotIn("bbbb2222", dashboard._hook_notifs)
                self.assertNotIn("bbbb2222", dashboard._last_state)

                with dashboard._lock:
                    dashboard._last_popup["_global"] = dashboard.time.time() - 120

                # Structured permission type also wins over misleading text.
                self._post_notify(
                    httpd.server_port,
                    {
                        "session_id": "cccc3333",
                        "hook_event_name": "Notification",
                        "notification_type": "permission_prompt",
                        "message": "Claude is waiting for your input to approve Bash",
                    },
                )
                self.assertEqual(2, notify.call_count)
                self.assertIn("cccc3333", dashboard._hook_notifs)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_notification_disposition_covers_documented_types(self) -> None:
        expected = {
            "idle_prompt": (False, True),
            "permission_prompt": (True, True),
            "auth_success": (False, False),
            "elicitation_dialog": (True, True),
            "elicitation_complete": (False, False),
            "elicitation_response": (False, False),
            "agent_needs_input": (True, True),
            "agent_completed": (False, False),
        }
        for notification_type, disposition in expected.items():
            with self.subTest(notification_type=notification_type):
                self.assertEqual(
                    disposition,
                    notifications.notification_disposition(notification_type, "variant text"),
                )

    def test_elicitation_completion_clears_dialog_hook(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs["feed1234"] = {
                "ts": dashboard.time.time() - 30,
                "message": "MCP input requested",
            }
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            self._post_notify(
                httpd.server_port,
                {
                    "session_id": "feed1234",
                    "hook_event_name": "Notification",
                    "notification_type": "elicitation_complete",
                    "message": "MCP elicitation completed",
                },
            )
            with dashboard._lock:
                self.assertNotIn("feed1234", dashboard._hook_notifs)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_session_end_hook_clears_standing_permission_state(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs["deadbeef"] = {
                "ts": dashboard.time.time() - 60,
                "message": "permission needed",
            }
            dashboard._last_state["deadbeef"] = "needs_input"
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            data = self._post_notify(
                httpd.server_port,
                {
                    "session_id": "deadbeef-0000-0000-0000-000000000000",
                    "hook_event_name": "SessionEnd",
                    "reason": "prompt_input_exit",
                },
            )
            self.assertIn(b'"cleared":"session_end"', data)
            with dashboard._lock:
                self.assertNotIn("deadbeef", dashboard._hook_notifs)
                self.assertNotIn("deadbeef", dashboard._last_state)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_hook_block_uses_hook_time_and_inactive_sessions_are_idle(self) -> None:
        now = dashboard.time.time()
        session_id = "abcd1234-0000-0000-0000-000000000000"
        event_time = dashboard.datetime.fromtimestamp(now - 600, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "user-before-hook",
                        "timestamp": event_time,
                        "message": {"role": "user", "content": "run it"},
                    }
                )
                + "\n"
            )
            old = now - 600
            dashboard.os.utime(transcript, (old, old))
            hook_time = now - 45
            with dashboard._lock:
                dashboard._hook_notifs[session_id[:8]] = {
                    "ts": hook_time,
                    "message": "permission needed",
                    "user_event": "user-before-hook",
                }
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                active = collect_claude(now, 24, False)[0]
                inactive = collect_claude(now, 0.1, True)[0]

        self.assertEqual("needs_input", active["state"])
        self.assertEqual(hook_time, active["blocked_since"])
        self.assertEqual("idle", inactive["state"])

    def test_transcript_open_question_outranks_fresh_activity(self) -> None:
        now = dashboard.time.time()
        session_id = "face9999-0000-0000-0000-000000000000"
        question_time = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "sample"
            project.mkdir(parents=True)
            transcript = project / f"{session_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": question_time,
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "question-1",
                                    "name": "AskUserQuestion",
                                    "input": {},
                                }
                            ],
                        },
                    }
                )
                + "\n"
            )
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            ):
                session = collect_claude(now, 24, False)[0]

        self.assertEqual("needs_input", session["state"])
        self.assertEqual(records.parse_ts(question_time), session["blocked_since"])

    def test_background_task_flap_lifecycle_end_to_end(self) -> None:
        # Full lifecycle of the live 936f2c2b case, through the real notify
        # endpoint: a turn ends into background work, Claude re-emits
        # "waiting for your input" hooks, background events keep the
        # transcript active. The session must read Working steadily (no
        # needs_input flapping), clear the hook when the session self-resumes
        # with a new user record, and only surface needs_input once the
        # session is genuinely quiet with a standing hook.
        now = dashboard.time.time()
        session_id = "eeee5555-0000-0000-0000-000000000000"

        def iso(age: float) -> str:
            return str(dashboard.datetime.fromtimestamp(now - age, dashboard.UTC).isoformat())

        def user_rec(uuid: str, age: float, text: str) -> str:
            return (
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": session_id,
                        "uuid": uuid,
                        "timestamp": iso(age),
                        "message": {"role": "user", "content": text},
                    }
                )
                + "\n"
            )

        def system_rec(age: float) -> str:
            return (
                json.dumps(
                    {
                        "type": "system",
                        "sessionId": session_id,
                        "timestamp": iso(age),
                        "content": "background shell event",
                    }
                )
                + "\n"
            )

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-Users-test-repo"
            proj.mkdir(parents=True)
            fp = proj / f"{session_id}.jsonl"
            patches = (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
            )
            # Built inside the store patches: the application captures its config
            # once, at construction, so the POSTs this test makes must reach a
            # server that already knows about the temporary store.
            with patches[0], patches[1]:
                httpd = make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with patches[0], patches[1]:

                    def post_hook() -> None:
                        # Permission-kind message: idle nudges never block at
                        # all (see test_idle_nudge_pops_but_never_marks_...).
                        self._post_notify(
                            httpd.server_port,
                            {
                                "session_id": session_id,
                                "message": "Claude needs your permission to use Bash",
                                "transcript_path": str(fp),
                            },
                        )

                    def state() -> str:
                        result = collect_claude(now, 24, False)
                        return str(
                            next(s for s in result if s["session"] == session_id[:8])["state"]
                        )

                    # Turn ended; hook fires; background events keep flowing.
                    fp.write_text(user_rec("u-1", 300, "review the PRs") + system_rec(50))
                    post_hook()
                    self.assertEqual("working", state())

                    # More background events + a RE-POSTED identical hook:
                    # still working, poll after poll — no flapping.
                    fp.write_text(
                        user_rec("u-1", 300, "review the PRs") + system_rec(50) + system_rec(20)
                    )
                    post_hook()
                    self.assertEqual("working", state())
                    self.assertEqual("working", state())

                    # Background work completes; the session self-resumes with
                    # a NEW user record (task notification): hook must CLEAR.
                    fp.write_text(
                        user_rec("u-1", 300, "review the PRs")
                        + system_rec(50)
                        + user_rec("u-2", 10, "task-notification: reviews done")
                    )
                    self.assertEqual("working", state())
                    with dashboard._lock:
                        self.assertNotIn(session_id[:8], dashboard._hook_notifs)

                    # Final turn ends for real: standing hook + genuinely
                    # quiet transcript (old record timestamps AND old mtime)
                    # -> blocked on the human.
                    fp.write_text(
                        user_rec("u-1", 900, "review the PRs")
                        + system_rec(700)
                        + user_rec("u-2", 600, "task-notification: reviews done")
                    )
                    old = now - 600
                    dashboard.os.utime(fp, (old, old))
                    post_hook()
                    self.assertEqual("needs_input", state())
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)


class NotifyHookTest(unittest.TestCase):
    """The forwarder replaces a curl one-liner that only worked in POSIX shells."""

    HOOK = str(HOOK_PATH)

    def run_hook(self, payload: bytes, url: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.HOOK, *([url] if url else [])],
            input=payload.decode(),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_payload_reaches_a_running_server(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{httpd.server_port}/api/notify"
        try:
            with mock.patch.object(notifications, "notify_mac"):
                result = self.run_hook(
                    json.dumps(
                        {
                            "session_id": "abcd1234-0000-0000-0000-000000000000",
                            "message": "Claude needs permission",
                            "notification_type": "permission_prompt",
                        }
                    ).encode(),
                    url,
                )
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertEqual(0, result.returncode, result.stderr)
        # The server recorded the hook, which is the whole point of the script.
        self.assertIn("abcd1234", dashboard._hook_notifs)

    def test_never_fails_the_agent_that_invoked_it(self) -> None:
        # A hook that exits non-zero disturbs the session it reports on, and
        # "no dashboard running" is an ordinary state.
        cases = {
            "no server listening": (b'{"session_id":"x"}', "http://127.0.0.1:9/api/notify"),
            "malformed json": (b"{not json", None),
            "empty stdin": (b"", None),
            "not an object": (b"[1,2,3]", None),
        }
        for why, (payload, url) in cases.items():
            with self.subTest(why=why):
                self.assertEqual(0, self.run_hook(payload, url).returncode)

    def test_refuses_to_forward_off_loopback(self) -> None:
        # The script is wired into lifecycle hooks and sees prompts and session
        # ids; an edited settings file must not turn it into an exfiltration
        # path. A prefix check (startswith "http://localhost") accepted several
        # of these — the host is parsed instead.
        for url in (
            "https://evil.example/collect",
            "http://10.0.0.5:4553/api/notify",
            "file:///etc/passwd",
            "http://localhost.evil.com/collect",
            "http://127.0.0.1.evil.com/collect",
            "http://localhost@evil.com/collect",
            "http://[::1]@evil.com/collect",
            "https://127.0.0.1/collect",  # https is not what the server speaks
            "",
        ):
            with self.subTest(url=url):
                self.assertFalse(dashboard_hook.is_loopback_url(url))
                self.assertFalse(dashboard_hook.forward(url, b"{}"))

    def test_accepts_every_loopback_spelling(self) -> None:
        for url in (
            "http://127.0.0.1:4553/api/notify",
            "http://localhost:9999/api/notify",
            "http://[::1]:4553/api/notify",
        ):
            with self.subTest(url=url):
                self.assertTrue(dashboard_hook.is_loopback_url(url))

    def test_an_http_proxy_cannot_carry_the_payload_off_the_machine(self) -> None:
        # urllib's default opener honours http_proxy/HTTP_PROXY, which is
        # routine in corporate environments. A POST to 127.0.0.1 was handed to
        # the proxy instead, carrying prompts and session ids off the machine
        # and defeating the loopback check entirely.
        proxied: list[bytes] = []

        class Proxy(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                proxied.append(self.rfile.read(length))
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch.dict(
                os.environ,
                {
                    "http_proxy": f"http://127.0.0.1:{httpd.server_port}",
                    "HTTP_PROXY": f"http://127.0.0.1:{httpd.server_port}",
                },
            ):
                # Port 9 (discard) is not listening, so anything the proxy
                # receives can only have come from proxy routing.
                delivered = dashboard_hook.forward(
                    "http://127.0.0.1:9/api/notify", b'{"secret":"prompt text"}'
                )
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertEqual([], proxied, "payload was routed through the proxy")
        self.assertFalse(delivered)

    def test_does_not_follow_a_redirect_off_the_machine(self) -> None:
        # urllib follows redirects by default, and 307/308 preserve method and
        # body — so a hostile listener on the loopback port could otherwise
        # bounce the payload off this machine, defeating the check above.
        received: list[str] = []

        class Redirector(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                received.append(self.path)
                self.send_response(307)
                self.send_header("Location", "https://evil.example/collect")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirector)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_port}/api/notify"
            delivered = dashboard_hook.forward(url, b'{"session_id":"x"}')
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertEqual(["/api/notify"], received, "first request should still be sent")
        self.assertFalse(delivered, "a refused redirect must not report success")


class HookOrderingTest(unittest.TestCase):
    def setUp(self) -> None:
        # This class does not inherit CargentoServerTest's shared reset, and
        # these tests mutate process-wide hook state.
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_state.clear()
            dashboard._hook_generation.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()

    def test_session_end_is_not_undone_by_a_slow_notification(self) -> None:
        # Notification handling does transcript lookups outside the lock. A
        # SessionEnd arriving during one used to be silently overwritten when
        # the notification committed its now-stale state.
        started = threading.Event()
        release = threading.Event()

        def slow_lookup(*_args: object) -> bool:
            started.set()
            release.wait(timeout=5)
            return False

        def request(payload: dict[str, Any]) -> Any:
            return notify_handler(payload)

        session = "deadbeef-0000-0000-0000-000000000000"
        with (
            mock.patch.object(claude_data, "prefix_is_agent", slow_lookup),
            mock.patch.object(notifications, "notify_mac"),
        ):
            notification = request(
                {
                    "session_id": session,
                    "hook_event_name": "Notification",
                    "notification_type": "permission_prompt",
                    "message": "permission",
                }
            )
            thread = threading.Thread(target=notification.do_POST)
            thread.start()
            self.assertTrue(started.wait(timeout=5))
            request({"session_id": session, "hook_event_name": "SessionEnd"}).do_POST()
            release.set()
            thread.join(timeout=5)

        self.assertEqual({}, dashboard._hook_notifs, "SessionEnd was undone")

    def test_session_end_during_a_collection_neither_blocks_nor_pops(self) -> None:
        # The POST-side generation guard does not help a collection that
        # already read the hook. Without re-checking, an exited session was
        # still announced as blocked and burned the global popup cooldown.
        now = 1_700_000_000.0
        prefix = "abcdef12"
        with dashboard._lock:
            dashboard._hook_notifs[prefix] = {"ts": now, "message": "permission"}
        popups: list[Any] = []
        original = notifications.current_hook

        def session_ends_mid_collection(st: Any, pfx: str, event: str | None, ts: float) -> Any:
            hook = original(st, pfx, event, ts)
            with dashboard._lock:  # SessionEnd lands exactly here
                dashboard._hook_notifs.pop(pfx, None)
                dashboard._last_state.pop(pfx, None)
                dashboard._hook_generation[pfx] = dashboard._hook_generation.get(pfx, 0) + 1
            return hook

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / f"{prefix}-0000-0000-0000-000000000000.jsonl"
            transcript.write_text(json.dumps({"type": "user", "uuid": "u"}) + "\n")
            os.utime(transcript, (now - 200, now - 200))  # quiet, so the hook decides
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
                mock.patch.object(notifications, "current_hook", session_ends_mid_collection),
                mock.patch.object(notifications, "notify_mac", lambda *a: popups.append(a)),
            ):
                sessions = collect_claude(now, 24, True)

        self.assertEqual("idle", sessions[0]["state"], "exited session shown as blocked")
        self.assertEqual([], popups, "popped for a session that had already ended")

    def _collect_with_session_end_injected(
        self, *, at: str, records: list[dict[str, Any]], standing_hook: bool
    ) -> tuple[str, int]:
        """Run collect_claude with a SessionEnd landing at ``at``."""
        now = 1_700_000_000.0
        prefix = "abcdef12"
        if standing_hook:
            with dashboard._lock:
                dashboard._hook_notifs[prefix] = {"ts": now, "message": "permission"}
        popups: list[Any] = []

        def end_session() -> None:
            with dashboard._lock:
                dashboard._hook_notifs.pop(prefix, None)
                dashboard._last_state.pop(prefix, None)
                dashboard._hook_generation[prefix] = dashboard._hook_generation.get(prefix, 0) + 1

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / f"{prefix}-0000-0000-0000-000000000000.jsonl"
            transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            os.utime(transcript, (now - 300, now - 300))  # quiet, so state is decided above

            notif_patches: dict[str, Any] = {
                "notify_mac": lambda *a, **_k: popups.append(a),
            }
            data_patches: dict[str, Any] = {}
            if at == "analyze":
                real_analyze = claude_data.analyze_transcript

                def analyze(cfg: Any, st: Any, path: str) -> Any:
                    end_session()
                    return real_analyze(cfg, st, path)

                data_patches["analyze_transcript"] = analyze
            elif at == "popup":
                real_popup = notifications.maybe_popup

                def popup(*args: Any, **kwargs: Any) -> None:
                    end_session()
                    real_popup(*args, **kwargs)

                notif_patches["maybe_popup"] = popup

            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "tasks")),
                mock.patch.multiple(notifications, **notif_patches),
                # patch.multiple rejects an empty mapping, so re-patch the real
                # function when this variant does not intercept it.
                mock.patch.multiple(
                    claude_data,
                    **(data_patches or {"analyze_transcript": claude_data.analyze_transcript}),
                ),
            ):
                sessions = collect_claude(now, 24, True)
        return sessions[0]["state"], len(popups)

    ASK_USER_QUESTION: ClassVar[list[dict[str, Any]]] = [
        {
            "type": "assistant",
            "timestamp": "2023-11-14T00:00:00+00:00",
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "AskUserQuestion"}]},
        }
    ]
    PLAIN_USER: ClassVar[list[dict[str, Any]]] = [{"type": "user", "uuid": "u"}]

    def test_session_end_during_analysis_clears_a_transcript_detected_block(self) -> None:
        # The guard was sampled after analyze_transcript, which is the slow
        # part, and did not cover transcript-detected needs-input at all — so
        # an unanswered AskUserQuestion in a session the user had quit stayed
        # on screen and popped.
        state, popups = self._collect_with_session_end_injected(
            at="analyze", records=self.ASK_USER_QUESTION, standing_hook=False
        )
        self.assertEqual("idle", state)
        self.assertEqual(0, popups)

    def test_session_end_at_popup_time_suppresses_the_popup(self) -> None:
        # Checking the generation in the caller left a window before
        # maybe_popup took the lock. The state is a snapshot and may still read
        # blocked until the next refresh, but the popup is irreversible and
        # must not fire for a session that has exited.
        _state, popups = self._collect_with_session_end_injected(
            at="popup", records=self.PLAIN_USER, standing_hook=True
        )
        self.assertEqual(0, popups)

    def test_a_standing_hook_still_blocks_and_pops_when_nothing_races(self) -> None:
        state, popups = self._collect_with_session_end_injected(
            at="none", records=self.PLAIN_USER, standing_hook=True
        )
        self.assertEqual("needs_input", state)
        self.assertEqual(1, popups)

    def _race_against_slow_notification(self, second: dict[str, Any]) -> dict[str, Any]:
        """Start an actionable Notification, land ``second`` mid-flight."""
        started = threading.Event()
        release = threading.Event()

        def slow_lookup(*_args: object) -> bool:
            started.set()
            release.wait(timeout=5)
            return False

        def request(payload: dict[str, Any]) -> Any:
            return notify_handler(payload)

        session = "deadbeef-0000-0000-0000-000000000000"
        first = request(
            {
                "session_id": session,
                "hook_event_name": "Notification",
                "notification_type": "permission_prompt",
                "message": "NEEDS PERMISSION",
            }
        )
        with (
            mock.patch.object(claude_data, "prefix_is_agent", slow_lookup),
            mock.patch.object(notifications, "notify_mac"),
        ):
            thread = threading.Thread(target=first.do_POST)
            thread.start()
            self.assertTrue(started.wait(timeout=5))
            with mock.patch.object(claude_data, "prefix_is_agent", lambda *_a: False):
                request(second).do_POST()
            release.set()
            thread.join(timeout=5)
        return dict(dashboard._hook_notifs)

    def test_a_clearing_notification_does_not_drop_a_racing_permission_prompt(self) -> None:
        # Only SessionEnd means "this session is gone". agent_completed and
        # idle_prompt end one alert, not the session — invalidating on those
        # dropped an actionable prompt that merely overlapped a clearing one,
        # losing a real "Claude is blocked" signal.
        for kind in ("agent_completed", "idle_prompt", "elicitation_complete"):
            with self.subTest(kind=kind):
                self.setUp()
                survived = self._race_against_slow_notification(
                    {
                        "session_id": "deadbeef-0000-0000-0000-000000000000",
                        "hook_event_name": "Notification",
                        "notification_type": kind,
                        "message": "done",
                    }
                )
                self.assertIn("deadbeef", survived, f"{kind} dropped a permission prompt")

    def test_session_end_still_supersedes_a_racing_notification(self) -> None:
        survived = self._race_against_slow_notification(
            {"session_id": "deadbeef-0000-0000-0000-000000000000", "hook_event_name": "SessionEnd"}
        )
        self.assertEqual({}, survived, "SessionEnd was undone")

    def test_an_unraced_notification_still_records(self) -> None:
        session = "cafebabe-0000-0000-0000-000000000000"
        handler = notify_handler(
            {
                "session_id": session,
                "hook_event_name": "Notification",
                "notification_type": "permission_prompt",
                "message": "permission",
            }
        )
        with (
            mock.patch.object(claude_data, "prefix_is_agent", lambda *_a: False),
            mock.patch.object(notifications, "notify_mac"),
        ):
            handler.do_POST()
        self.assertIn("cafebabe", dashboard._hook_notifs)


class NativeNotifierTest(unittest.TestCase):
    """Pure in platform_name, so both branches run on every runner rather than
    only the host's (design decision D-4 in docs/design-cross-platform.md)."""

    def test_backend_per_platform(self) -> None:
        self.assertEqual("osascript", notifications.native_notifier("darwin"))
        # No native backend yet on these (tracked in
        # docs/plans/native-notifications.md). Until then the
        # empty string tells the page to raise the notification itself.
        for platform_name in ("linux", "win32", "freebsd14", "cygwin"):
            with self.subTest(platform=platform_name):
                self.assertEqual("", notifications.native_notifier(platform_name))

    def test_notify_mac_is_a_no_op_without_a_backend(self) -> None:
        # The backend comes from config.platform_name, not ambient sys.platform.
        linux = make_config(platform_name="linux")
        with mock.patch("cargento_runtime.notifications.subprocess.run") as run:
            notifications.notify_mac(linux, "title", "message")
        run.assert_not_called()

    def test_api_data_reports_who_owns_popups(self) -> None:
        # The page reads this to decide whether to notify; if it went missing,
        # macOS would double-notify and Linux would notify not at all.
        with mock.patch.object(dashboard.sys, "platform", "darwin"):
            self.assertEqual("osascript", dashboard.collect(24, False)["native_notify"])
        with mock.patch.object(dashboard.sys, "platform", "win32"):
            self.assertEqual("", dashboard.collect(24, False)["native_notify"])


class GlobUnderTest(unittest.TestCase):
    HOSTILE = "A [Contractor]"

    def test_notify_session_id_cannot_inject_a_glob_pattern(self) -> None:
        # The prefix reaches this glob straight from a POST body, so it must be
        # escaped rather than interpreted.
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            (projects / "proj").mkdir(parents=True)
            (projects / "proj" / "aaaaaaaa.jsonl").write_text(
                json.dumps({"type": "user", "agentName": "worker", "teamName": "session-bbbbbbbb"})
                + "\n"
            )
            with mock.patch.object(dashboard, "PROJECTS_DIR", str(projects)):
                config, state = dashboard._legacy_runtime()
                self.assertFalse(claude_data.prefix_is_agent(config, state, "[a-z]*"))
                config, state = dashboard._legacy_runtime()
                self.assertTrue(claude_data.prefix_is_agent(config, state, "aaaaaaaa"))


class InstalledContractCharacterizationTest(unittest.TestCase):
    """The installed executable contract that extraction must preserve."""

    def setUp(self) -> None:
        self._spacedock_enabled = dashboard.__dict__["SPACEDOCK_ENABLED"]
        self._server_started = dashboard.__dict__["SERVER_STARTED"]
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()
            dashboard._last_state.clear()
            dashboard._hook_generation.clear()
        with dashboard._collect_memo_lock:
            dashboard._collect_memo.clear()
        # Route-shape tests exercise successful /api/notify requests, but do
        # not assert native delivery. Execute the notification code while
        # keeping its osascript process off the host.
        original_run = dashboard.subprocess.run

        def run_without_native_delivery(*args: Any, **kwargs: Any) -> Any:
            command = args[0] if args else kwargs.get("args")
            if (
                isinstance(command, (list, tuple))
                and command
                and command[0] == "/usr/bin/osascript"
            ):
                return subprocess.CompletedProcess(command, 0)
            return original_run(*args, **kwargs)

        notify_patcher = mock.patch.object(
            dashboard.subprocess, "run", side_effect=run_without_native_delivery
        )
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)

    def tearDown(self) -> None:
        dashboard.__dict__["SPACEDOCK_ENABLED"] = self._spacedock_enabled
        dashboard.__dict__["SERVER_STARTED"] = self._server_started
        with dashboard._collect_memo_lock:
            dashboard._collect_memo.clear()

    @staticmethod
    def _response(
        port: int,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, email.message.Message, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def test_session_end_cannot_be_undone_by_a_slow_notification(self) -> None:
        httpd = make_server()
        thread = serve_until_closed(httpd)
        entered = threading.Event()
        release = threading.Event()
        notification: list[tuple[int, bytes]] = []

        def slow_lookup(*_: Any) -> tuple[bool, str]:
            entered.set()
            self.assertTrue(release.wait(timeout=5), "test did not release notification")
            return True, "user-event"

        def post_notification() -> None:
            code, _, body = self._response(
                httpd.server_port,
                "POST",
                "/api/notify",
                json.dumps(
                    {
                        "session_id": "12345678-session",
                        "message": "permission needed",
                        "transcript_path": "/slow.jsonl",
                    }
                ).encode(),
            )
            notification.append((code, body))

        try:
            with (
                mock.patch.object(claude_data, "hook_user_event", side_effect=slow_lookup),
                mock.patch.object(notifications, "notify_mac"),
            ):
                worker = threading.Thread(target=post_notification)
                worker.start()
                self.assertTrue(entered.wait(timeout=5), "notification did not begin")
                code, _, body = self._response(
                    httpd.server_port,
                    "POST",
                    "/api/notify",
                    b'{"session_id":"12345678-session","hook_event_name":"SessionEnd"}',
                )
                self.assertEqual(200, code)
                self.assertEqual({"ok": True, "cleared": "session_end"}, json.loads(body))
                release.set()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual([(200, b'{"ok":true,"superseded":true}')], notification)
            self.assertNotIn("12345678", dashboard._hook_notifs)
        finally:
            release.set()
            httpd.shutdown()
            thread.join(timeout=5)
