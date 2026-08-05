#!/usr/bin/env python3
"""Forward a Claude Code hook payload to a running Cargento dashboard.

This exists because the equivalent shell one-liner is not portable. The
documented `curl` form relies on POSIX single-quoting, `/dev/null`, `|| true`,
and `--data-binary @-`: cmd.exe accepts none of that, and Windows PowerShell
5.1 both aliases `curl` to Invoke-WebRequest and has no `||`. One interpreter
invocation reading stdin behaves identically in every shell.

Usage in ~/.claude/settings.json (Notification and SessionEnd hooks):

    python3 <skill-dir>/notify_hook.py            # macOS, Linux, WSL, Git Bash
    python  <skill-dir>\\notify_hook.py           # Windows

Pass a URL as the first argument to target a non-default port.

Always exits 0. A hook that fails must never disturb the agent it is reporting
on, and "the dashboard is not running" is an ordinary state, not an error.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_URL = "http://127.0.0.1:4553/api/notify"
MAX_PAYLOAD_BYTES = 65536  # matches the server's own cap
TIMEOUT_SEC = 2
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_loopback_url(url: str) -> bool:
    """Whether ``url`` targets this machine over plain HTTP loopback.

    Parsed rather than prefix-matched. ``startswith("http://localhost")`` also
    accepts ``http://localhost.evil.com/`` and ``http://localhost@evil.com/``,
    which are entirely different hosts — that is the bypass this exists to
    prevent.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return parsed.scheme == "http" and (parsed.hostname or "") in LOOPBACK_HOSTS


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects.

    urllib follows them by default, and 307/308 preserve the method and body.
    A hostile or misconfigured listener on the loopback port could otherwise
    bounce a hook payload — which carries prompts and session ids — straight
    off this machine, defeating the loopback check above.
    """

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def forward(url: str, payload: bytes, headers: dict[str, str] | None = None) -> bool:
    """POST ``payload`` to ``url``. Returns whether it was delivered.

    ``headers`` adds to the content type rather than replacing it, and exists for
    the event adapter beside this file, which has to present a capability. The
    loopback and proxy guards below are the reason that adapter imports this
    function instead of writing its own: a header is the only thing about the
    request it needs to change.
    """
    if not is_loopback_url(url):
        # This script is wired into an agent's lifecycle hooks and receives
        # prompts and session ids. It must not become a way to ship those
        # somewhere else because a settings file was edited.
        return False
    request = urllib.request.Request(  # noqa: S310 — scheme/host checked above
        url,
        data=payload,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    # ProxyHandler({}) disables proxying entirely. Without it the default
    # opener honours http_proxy/HTTP_PROXY — routine in corporate environments
    # — and a POST to 127.0.0.1 is handed to the proxy instead, carrying
    # prompts and session ids off the machine. That defeats the whole point of
    # the loopback check above.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects)
    try:
        with opener.open(request, timeout=TIMEOUT_SEC):
            return True
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        # Dashboard not running, wrong port, mid-restart, or a malformed
        # response. HTTPException is not an OSError and urllib does not always
        # wrap it, so it is listed explicitly.
        return False


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else DEFAULT_URL
    try:
        payload = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES)
    except (OSError, ValueError, AttributeError):
        return 0  # no stdin (run interactively, or a harness that closes it)
    if not payload.strip():
        payload = b"{}"
    try:  # a malformed payload is the harness's problem, not worth forwarding
        json.loads(payload)
    except (ValueError, RecursionError):
        # RecursionError, not just ValueError: deeply nested JSON blows the
        # decoder's stack, and that escaped as a non-zero exit — exactly what
        # this script promises never to do.
        return 0
    # Last-resort guard. forward() already handles every failure it expects;
    # this catches the ones it does not, because a hook that raises would
    # surface as an error inside the very agent session it is reporting on.
    with contextlib.suppress(Exception):
        forward(url, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
