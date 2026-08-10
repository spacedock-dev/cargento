"""Notification classification, hook state, cooldowns and the native notifier."""

from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING, Any

from cargento_runtime import claude_data, records
from cargento_runtime import io as runtime_io
from cargento_runtime import state as runtime_state

if TYPE_CHECKING:
    from collections.abc import Callable

    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.state import RuntimeState


# Claude Code's Notification matcher values. ``idle_timeout`` is accepted as a
# compatibility alias, while current payloads use ``idle_prompt``.
# These three sets are deliberately not exhaustive: an unrecognised structured
# type stays actionable (see notification_disposition), so a type Claude Code
# adds tomorrow surfaces rather than disappearing.
#
# Four values below are observed rather than documented, and the distinction is
# worth keeping: Claude Code's own hook metadata advertises eight
# ``notification_type`` values, but its callers pass these four as well
# (measured on 2.1.226). Fail-visible treats all four as actionable, which is
# right for exactly one of them, ``worker_permission_prompt``, and wrong for the
# other three: ``computer_use_enter`` and its pair carry "Claude is using your
# computer", a status line rather than a question, and ``push_notification`` is
# the delivery wrapper rather than a prompt of its own. So classifying them
# explicitly is what stops an unknown-type default from deciding a user-facing
# band. Do not prune them back to the advertised list.
IDLE_NOTIFICATION_TYPES = {"idle_prompt", "idle_timeout"}


INFORMATIONAL_NOTIFICATION_TYPES = {
    "agent_completed",
    "auth_success",
    "computer_use_enter",  # observed: "Claude is using your computer"
    "computer_use_exit",  # observed: its pair
    "elicitation_complete",
    "elicitation_response",
    "push_notification",  # observed: the push wrapper, not a question of its own
}


ACTIONABLE_NOTIFICATION_TYPES = {
    "agent_needs_input",
    "elicitation_dialog",
    "permission_prompt",
    # observed: a leader raising a worker's tool or network request. It arrives on
    # the *leader's* session_id, so prefix_is_agent never fires and the parent row
    # is the one that shows it — which is also the row the human answers from.
    # The network half has no PermissionRequest behind it (that hook is
    # tool-scoped), so this is its only signal. See DRC-4121.
    "worker_permission_prompt",
}


# Narrower than "everything informational", on purpose. Clearing retires a
# standing hook, so a type earns a place here only by meaning "the thing that was
# waiting is over" — which is why ``auth_success`` has never been here, and why
# the newly classified informational types are not either. A status line
# ("Claude is using your computer") arriving while a permission prompt stands
# must leave that prompt standing.
CLEARING_NOTIFICATION_TYPES = IDLE_NOTIFICATION_TYPES | {
    "agent_completed",
    "elicitation_complete",
    "elicitation_response",
}


def normalized_notification_type(value: Any) -> str:
    """Return a normalized structured notification type, if present."""
    return value.strip().lower() if isinstance(value, str) and value.strip() else ""


def notification_disposition(notification_type: Any, message: str) -> tuple[bool, bool]:
    """Return ``(needs_input, popup)`` for a Notification-hook payload.

    Structured Claude Code payloads are authoritative. Text matching remains
    only as a compatibility fallback for older hooks that omitted
    ``notification_type``.
    """
    kind = normalized_notification_type(notification_type)
    if kind in IDLE_NOTIFICATION_TYPES:
        return (False, True)
    if kind in INFORMATIONAL_NOTIFICATION_TYPES:
        return (False, False)
    if kind in ACTIONABLE_NOTIFICATION_TYPES:
        return (True, True)
    if kind:
        return (True, True)  # future/unknown structured prompt: fail visible
    idle_nudge = message.strip().lower().startswith("claude is waiting for your input")
    return (not idle_nudge, True)


def native_notifier(platform_name: str) -> str:
    """Name of the OS-level notification backend for a platform, "" if none.

    Pure in ``platform_name`` so both branches run on every CI runner and mypy
    checks them all, rather than treating the non-host branch as unreachable
    (design decision D-4 in docs/design-cross-platform.md).

    The page reads this through ``/api/data`` to decide whether to raise its
    own browser notification. Exactly one layer notifies for a given
    transition: the server when it has a backend here, the browser when it does
    not. Linux and Windows have no backend yet (tracked in
    docs/plans/native-notifications.md) — so today the
    browser covers them and macOS behavior is unchanged.
    """
    return "osascript" if platform_name == "darwin" else ""


def notify_mac(
    config: RuntimeConfig,
    title: Any,
    message: Any,
    *,
    diagnostic_sink: Callable[[str], None] = print,
) -> None:
    if not native_notifier(config.platform_name):
        return

    def esc(s: str) -> str:
        return str(s).replace("\\", "\\\\").replace('"', '\\"')

    safe_message = records.safe_text(message, 180)
    safe_title = records.safe_text(title, 60)
    script = (
        f'display notification "{esc(safe_message)}"'
        f' with title "{esc(safe_title)}" sound name "Glass"'
    )
    try:
        result = subprocess.run(  # noqa: S603 — fixed binary, esc()-sanitized args
            ["/usr/bin/osascript", "-e", script],
            timeout=5,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            runtime_io.diag(f"[notify] osascript failed: {detail[:300]}", diagnostic_sink)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        runtime_io.diag(f"[notify] osascript failed: {type(exc).__name__}: {exc}", diagnostic_sink)


def hook_generation(state: RuntimeState, prefix: str) -> int:
    """The current SessionEnd generation for a session prefix."""
    with state.hook_lock:
        return state.hook_generation.get(prefix, 0)


def current_hook(
    state: RuntimeState,
    prefix: str,
    last_user_event: str | None,
    last_event_ts: float,
) -> dict[str, Any] | None:
    """Return an uncleared hook notification for a session.

    Hooks with a user-event marker clear when the newest user record changes
    (clock-independent). Hooks without one (payloads lacking transcript_path:
    the documented curl simulation, older Claude Code versions) fall back to
    the parsed-timestamp rule so they cannot stick forever.
    """
    with state.hook_lock:
        hook = state.hook_notifications.get(prefix)
        if not hook:
            return None
        if "user_event" in hook:
            if last_user_event != hook["user_event"]:
                state.hook_notifications.pop(prefix, None)
                return None
        elif last_event_ts > hook["ts"]:
            state.hook_notifications.pop(prefix, None)
            return None
        return hook


# `/api/notify` is Claude's own hook forwarder: the payload shape is Claude
# Code's `Notification` hook and nothing else posts there. So this label is a
# property of the route rather than something to look up, and a second harness
# gets its own ingress rather than a `harness` field in this body that the server
# would then have to trust.
NOTIFY_HARNESS_LABEL = "Claude"


def waiting_title(harness_label: str) -> str:
    """The popup title for a harness that needs the human.

    One function rather than an f-string at each site, because the native
    notifier and the browser both render this sentence and they drifted apart the
    moment there was more than one harness able to raise it. The label is the
    registry's own display label, so a row badged Antigravity cannot produce a
    popup that says Claude.
    """
    return f"{harness_label} is waiting on you"


def maybe_popup(
    config: RuntimeConfig,
    state: RuntimeState,
    prefix: str,
    session_state: str,
    detail: str | None,
    *,
    harness_label: str,
    expect_generation: int | None = None,
    popup_notifier: Callable[[str, str], None],
) -> None:
    """Popup when a session transitions into a needs-input state.

    ``expect_generation`` is re-checked under the same lock that guards the
    last-session-state map. Checking it in the caller leaves a window in which a
    SessionEnd commits first, and this would then re-create the state it just
    cleared and fire a popup for a session that has already exited.

    ``harness_label`` is required rather than defaulted to Claude. A default would
    let a second harness's collector wire itself in and silently claim to be
    Claude, which is the failure this generalization exists to prevent, and the
    compiler cannot catch a wrong string but it can catch a missing argument.
    """
    now = time.time()
    with state.hook_lock:
        if (
            expect_generation is not None
            and state.hook_generation.get(prefix, 0) != expect_generation
        ):
            return
        prev = state.last_session_state.get(prefix)
        runtime_state.bounded_put(
            state.last_session_state, prefix, session_state, limit=config.max_cache_entries
        )
        if session_state != "needs_input" or prev == "needs_input":
            return
        if now - state.last_popup.get(prefix, 0) < config.popup_cooldown_sec:
            return
        if now - state.last_popup.get("_global", 0) < config.global_popup_cooldown_sec:
            return
        runtime_state.bounded_put(state.last_popup, prefix, now, limit=config.max_cache_entries)
        runtime_state.bounded_put(state.last_popup, "_global", now, limit=config.max_cache_entries)
    popup_notifier(waiting_title(harness_label), detail or f"Session {prefix} needs your input")


def clear_session(state: RuntimeState, config: RuntimeConfig, prefix: str) -> None:
    """Retire a session's standing hook state and bump its generation.

    Only SessionEnd does this, because only SessionEnd means "this session is
    gone". A clearing notification ends one alert, not the session.
    """
    with state.hook_lock:
        state.hook_notifications.pop(prefix, None)
        state.last_session_state.pop(prefix, None)
        runtime_state.bounded_put(
            state.hook_generation,
            prefix,
            state.hook_generation.get(prefix, 0) + 1,
            limit=config.max_cache_entries,
        )


def handle_payload(
    config: RuntimeConfig,
    state: RuntimeState,
    payload: dict[str, Any],
    *,
    now: float,
    popup_notifier: Callable[[str, str], None],
) -> dict[str, Any]:
    """Apply one Claude hook payload and return the response object.

    Every ordering rule lives here, not in the HTTP layer: SessionEnd
    retirement, the generation guard around the slow transcript lookups,
    subagent suppression, the clear/needs-input decision, and the three popup
    cooldowns. The caller only encodes the result.
    """
    session_id = payload.get("session_id")
    prefix = session_id[:8] if isinstance(session_id, str) else ""
    hook_event_name = payload.get("hook_event_name")
    if isinstance(hook_event_name, str) and hook_event_name.lower() == "sessionend":
        if prefix:
            clear_session(state, config, prefix)
        return {"ok": True, "cleared": "session_end"}

    raw_message = payload.get("message")
    message = records.safe_text(
        raw_message
        if isinstance(raw_message, str) and raw_message
        else "Claude is waiting for your input",
        500,
    )
    kind = normalized_notification_type(payload.get("notification_type"))
    needs_input, popup = notification_disposition(kind, message)
    # Sampled before the transcript lookups below, which are slow enough for a
    # SessionEnd to land in between and be silently undone.
    generation = hook_generation(state, prefix)
    # Subagent sessions also emit Notification-hook events (permission prompts
    # inside agents). They are not user-facing sessions — a popup about them is
    # noise the human cannot act on from the dashboard.
    if prefix and claude_data.prefix_is_agent(config, state, prefix):
        return {"ok": True, "suppressed": "subagent"}

    hook: dict[str, Any] = {"ts": now, "message": message}
    transcript_path = payload.get("transcript_path")
    if prefix and isinstance(transcript_path, str):
        found, user_event = claude_data.hook_user_event(config, state, transcript_path, prefix)
        if found:
            hook["user_event"] = user_event

    with state.hook_lock:
        if prefix and state.hook_generation.get(prefix, 0) != generation:
            # The session ended while this notification was being processed.
            return {"ok": True, "superseded": True}
        if prefix:
            clears_input = kind in CLEARING_NOTIFICATION_TYPES or (not kind and not needs_input)
            if clears_input:
                state.hook_notifications.pop(prefix, None)
                state.last_session_state.pop(prefix, None)
            elif needs_input:
                runtime_state.bounded_put(
                    state.hook_notifications, prefix, hook, limit=config.max_cache_entries
                )
        popup_key = prefix or "_anonymous"
        session_ready = now - state.last_popup.get(popup_key, 0) >= config.popup_cooldown_sec
        global_ready = now - state.last_popup.get("_global", 0) >= config.global_popup_cooldown_sec
        # Claude re-emits the same idle/permission notification for as long as
        # the session stays blocked; repeating the popup adds no information.
        # One popup per distinct message per session within the repeat window.
        prev_msg, prev_ts = state.last_popup_message.get(popup_key, ("", 0.0))
        repeat = message == prev_msg and now - prev_ts < config.popup_repeat_suppress_sec
        fire = popup and session_ready and global_ready and not repeat
        if fire:
            runtime_state.bounded_put(
                state.last_popup, popup_key, now, limit=config.max_cache_entries
            )
            runtime_state.bounded_put(
                state.last_popup, "_global", now, limit=config.max_cache_entries
            )
            runtime_state.bounded_put(
                state.last_popup_message, popup_key, (message, now), limit=config.max_cache_entries
            )
    if fire:
        popup_notifier(waiting_title(NOTIFY_HARNESS_LABEL), message)
    return {"ok": True}
