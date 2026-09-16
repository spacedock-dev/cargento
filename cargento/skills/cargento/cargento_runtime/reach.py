"""Off-machine nudge delivery: reaches the operator away from the desk.

DRC-4034. Implements the
[DEC-4](SECURITY.md#off-machine-nudges-reaching-the-operator-away-from-the-desk) ruling and the
non-negotiable security boundaries defined in SECURITY.md ("Off-machine nudges"):
1. Off until a URL exists. No default endpoint.
2. One destination: operator's webhook URL, follows no redirects, ignores proxies.
3. Strictly counts and states: needs_input and finished_unread only. Never any
   session name, project, path, title, or prompt text.
4. Throttled by cooldown interval, with a change in counts as trigger.
5. Credential protection: URL is never logged, echoed, or served.
6. Off switch: --no-reach disables the pathway regardless of stored settings.
"""

from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.sessions import Session
    from cargento_runtime.state import RuntimeState

REACH_TIMEOUT_SEC: Final[float] = 5.0
REACH_URL_ENV: Final[str] = "CARGENTO_REACH_URL"
REACH_URL_FILENAME: Final[str] = "reach_url"
REACH_URL_MAX_BYTES: Final[int] = 2048


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow redirects on reach webhook dispatch."""

    def redirect_request(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> urllib.request.Request | None:
        return None


def build_reach_opener() -> urllib.request.OpenerDirector:
    """Opener that ignores environment proxies and forbids redirects."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects)


def format_reach_payload(needs_input: int, finished_unread: int) -> bytes:
    """Format the off-machine nudge payload.

    SECURITY.md strictly forbids any field beyond these two counts.
    """
    payload = {
        "finished_unread": int(finished_unread),
        "needs_input": int(needs_input),
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def resolve_reach_url(config: RuntimeConfig) -> str | None:
    """Resolve the operator's webhook URL, or None if not configured or disabled."""
    if not config.reach_enabled:
        return None
    candidate = config.reach_url
    if not candidate:
        candidate = os.environ.get(REACH_URL_ENV)
    if not candidate:
        reach_file = os.path.join(config.state_home, REACH_URL_FILENAME)
        if os.path.isfile(reach_file):
            try:
                with open(reach_file, encoding="utf-8") as f:
                    candidate = f.read(REACH_URL_MAX_BYTES)
            except OSError:
                candidate = None
    if candidate:
        url = candidate.strip()
        if url.startswith(("http://", "https://")):
            return url
    return None


def count_reach_sessions(sessions: Iterable[Session]) -> tuple[int, int]:
    """Count sessions requiring human attention: (needs_input, finished_unread)."""
    needs_input = 0
    finished_unread = 0
    for s in sessions:
        if s.get("active") and s.get("state") == "needs_input":
            needs_input += 1
        elif not s.get("active") or s.get("state") == "done":
            finished_unread += 1
    return needs_input, finished_unread


def send_reach_nudge(
    config: RuntimeConfig,
    url: str,
    needs_input: int,
    finished_unread: int,
    *,
    opener: urllib.request.OpenerDirector | None = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Dispatch one nudge POST to the configured destination."""
    if not config.reach_enabled:
        return False
    payload = format_reach_payload(needs_input, finished_unread)
    req = urllib.request.Request(  # noqa: S310 - http(s) URL validated
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    op = opener or build_reach_opener()
    try:
        with op.open(req, timeout=REACH_TIMEOUT_SEC):
            return True
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
        # Never log the URL: the URL is a bearer credential
        diagnostic_sink(f"[reach] POST failed: {type(exc).__name__}")
        return False


def maybe_reach_nudge(
    config: RuntimeConfig,
    state: RuntimeState,
    sessions: Iterable[Session],
    *,
    now: float,
    opener: urllib.request.OpenerDirector | None = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Conditionally dispatch an off-machine nudge if counts changed and interval elapsed."""
    if not config.reach_enabled:
        return False
    url = resolve_reach_url(config)
    if not url:
        return False
    needs_input, finished_unread = count_reach_sessions(sessions)
    counts = (needs_input, finished_unread)
    with state.reach_lock:
        if needs_input == 0 and finished_unread == 0:
            state.last_reach_counts = (0, 0)
            return False
        if counts == state.last_reach_counts:
            return False
        if now - state.last_reach_time < config.reach_cooldown_sec:
            return False
        state.last_reach_time = now
        state.last_reach_counts = counts

    return send_reach_nudge(
        config,
        url,
        needs_input,
        finished_unread,
        opener=opener,
        diagnostic_sink=diagnostic_sink,
    )
