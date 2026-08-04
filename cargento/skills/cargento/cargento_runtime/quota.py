"""Quota acquisition: the outbound fetch, the pushed-in receipts, and the cache.

Two sources fill one cache, and collectors read it back without caring which
filled it.

**The fetch** is the whole of Cargento's outbound network surface, and it is
bound by the "Usage quota reads" section of SECURITY.md: the request carries
the vendor's own OAuth token and nothing else, the token is never refreshed,
never written, never logged and never served, and at most one request per
vendor leaves every five minutes. A violation of any of those is a security
bug, not a defect. Diagnostics emitted here are fixed category words plus
exception type names for that reason — never a value read from a credential
source or a response.

**The receipts** are the opposite direction and involve no credential at all.
A harness that publishes its own quota to a user-configured command can have
that forwarded to `POST /api/usage`, and `receive_statusline` shapes what
arrives. Antigravity works this way. Nothing here reaches the network, so the
receipt path is outside the fetch contract above, but it inherits the rule
that only derived scalars are published: the shaping code builds a fresh
entry rather than passing a payload through, because these payloads carry an
account email that must never reach `/api/data`.
"""

from __future__ import annotations

import copy
import json
import ntpath
import posixpath
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import io as runtime_io
from . import records, sessions
from .config import primary_store

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import RuntimeConfig
    from .state import RuntimeState

# The one endpoint this module may call, spelled exactly as SECURITY.md names
# it. A new vendor's endpoint must be named there before it is added here.
USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
USAGE_BETA_VALUE = "oauth-2025-04-20"
# Where Claude Code keeps its OAuth credentials: a Keychain generic password
# on macOS, a JSON file beside the projects store everywhere else.
KEYCHAIN_SERVICE = "Claude Code-credentials"
CREDENTIALS_FILENAME = ".credentials.json"
# The first Keychain read can raise a user-facing permission prompt, so the
# subprocess must be allowed to sit through a human answering it. On timeout
# the read fails as "unavailable" and the poll floor schedules the retry.
KEYCHAIN_TIMEOUT_SEC = 120.0


def credentials_path(config: RuntimeConfig) -> str:
    """The harness's credential file, derived from the resolved projects store.

    Deriving from `claude.projects` keeps one source of truth for where the
    Claude home is: a `CLAUDE_CONFIG_DIR` override moves both together.
    """
    windows = config.platform_name == "win32"
    dirname = ntpath.dirname if windows else posixpath.dirname
    join = ntpath.join if windows else posixpath.join
    return join(dirname(primary_store(config, "claude.projects")), CREDENTIALS_FILENAME)


def _read_token(
    config: RuntimeConfig,
    runner: Callable[..., Any],
) -> tuple[str | None, float | None, str | None]:
    """(access token, expiry epoch seconds, problem category).

    Problem categories are fixed words plus exception type names because they
    reach diagnostics; no value read from the Keychain or the file ever does.
    """
    if config.platform_name == "darwin":
        try:
            result = runner(
                ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True,
                text=True,
                timeout=KEYCHAIN_TIMEOUT_SEC,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return None, None, f"keychain {type(exc).__name__}"
        if result.returncode != 0 or not str(result.stdout).strip():
            return None, None, "keychain item unavailable"
        raw = str(result.stdout)
    else:
        try:
            raw = runtime_io.read_prefix_bytes(
                credentials_path(config),
                max_bytes=config.usage_credentials_cap_bytes,
            ).decode("utf-8", "replace")
        except OSError:
            return None, None, "no credential file"
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, None, "malformed credentials"
    oauth = records.as_dict(records.as_dict(payload).get("claudeAiOauth"))
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token.strip():
        return None, None, "no oauth token"
    expires = oauth.get("expiresAt")
    expiry = (
        expires / 1000.0
        if isinstance(expires, (int, float)) and not isinstance(expires, bool) and expires > 0
        else None
    )
    return token, expiry, None


def _epoch(raw: Any) -> float | None:
    """A reset stamp as epoch seconds: the endpoint has sent both shapes."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
        return float(raw)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw).timestamp()
        except ValueError:
            return None
    return None


def _shape_window(now: float, raw: Any) -> dict[str, Any] | None:
    """One usage window mapped onto the payload contract, or nothing."""
    win = records.as_dict(raw)
    pct = win.get("utilization")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return None
    shaped: dict[str, Any] = {"pct": max(0, min(100, round(pct)))}
    resets = _epoch(win.get("resets_at"))
    if resets:
        shaped["reset"] = sessions.format_reset(now, resets)
    return shaped


def _expired_entry(now: float) -> dict[str, Any]:
    return {"harness": "claude", "state": "expired", "asOf": int(now)}


def _fetch_windows(
    config: RuntimeConfig,
    token: str,
    now: float,
    opener: Callable[..., Any],
) -> tuple[list[dict[str, Any]], str | None]:
    """The one outbound request, shaped into usage entries.

    The request is a GET with no body and exactly two headers of ours: the
    authorization carrying the token, and the beta header the endpoint
    requires. Anything more is a contract violation.
    """
    request = urllib.request.Request(
        USAGE_ENDPOINT,
        headers={"Authorization": f"Bearer {token}", "anthropic-beta": USAGE_BETA_VALUE},
    )
    try:
        with opener(request, timeout=config.usage_fetch_timeout_sec) as response:
            body = response.read(config.usage_response_cap_bytes)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            # A rejected token gets the same display as an expired one: off,
            # with the pointer at signing in again in the harness. Never a
            # refresh — that could race the harness for its own session.
            return [_expired_entry(now)], None
        return [], f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return [], type(exc).__name__
    try:
        payload = records.as_dict(json.loads(body))
    except ValueError:
        return [], "malformed response"
    entry: dict[str, Any] = {"harness": "claude", "state": "ok", "asOf": int(now)}
    for key, field_name in (("fiveH", "five_hour"), ("week", "seven_day")):
        shaped = _shape_window(now, payload.get(field_name))
        if shaped:
            entry[key] = shaped
    if "fiveH" not in entry and "week" not in entry:
        return [], "response carried no windows"
    return [entry], None


def _claude_entries(
    config: RuntimeConfig,
    now: float,
    opener: Callable[..., Any],
    runner: Callable[..., Any],
) -> tuple[list[dict[str, Any]], str | None]:
    token, expiry, problem = _read_token(config, runner)
    if problem:
        # No token is not "expired": a denied Keychain prompt or a missing
        # file means Claude stays absent from the band, because "sign in
        # again" would be the wrong advice.
        return [], problem
    if expiry is not None and expiry <= now:
        return [_expired_entry(now)], None
    return _fetch_windows(config, token or "", now, opener)


def fetch_claude_usage(
    config: RuntimeConfig,
    state: RuntimeState,
    *,
    clock: Callable[[], float] = time.time,
    opener: Callable[..., Any] = urllib.request.urlopen,
    runner: Callable[..., Any] = subprocess.run,
    diagnostic_sink: Callable[[str], object] = print,
) -> None:
    """One fetch, synchronous, ending in a cache write.

    A failure caches an empty entry list on purpose: the write stamps the
    attempt, and the poll floor reads that stamp, so a broken endpoint or a
    missing credential is retried on the same five-minute cadence as success,
    never in a storm.
    """
    now = clock()
    entries, note = _claude_entries(config, now, opener, runner)
    if note:
        runtime_io.diag(f"[claude] usage fetch: {note}", diagnostic_sink)
    with state.usage_fetch_lock:
        state.usage_fetch_cache["claude"] = {"ts": clock(), "entries": entries}


def _spawn_thread(run: Callable[[], None]) -> None:
    threading.Thread(target=run, daemon=True).start()


def request_fetch(
    config: RuntimeConfig,
    state: RuntimeState,
    *,
    clock: Callable[[], float] = time.time,
    opener: Callable[..., Any] = urllib.request.urlopen,
    runner: Callable[..., Any] = subprocess.run,
    diagnostic_sink: Callable[[str], object] = print,
    spawn: Callable[[Callable[[], None]], None] = _spawn_thread,
) -> bool:
    """Maybe start a background fetch; never block the caller on the network.

    This is the only entry point the serving path calls, and it holds every
    gate of the polling posture: nothing with the feature off, nothing while
    a fetch is already in flight, and nothing inside the five-minute floor of
    the last attempt. It is invoked only from `/api/data` requests that carry
    the page's consent, which is what makes "no polling while no dashboard
    page is connected" structural rather than scheduled.
    """
    if not config.usage_fetch_enabled:
        return False
    now = clock()
    with state.usage_fetch_lock:
        if "claude" in state.usage_fetch_inflight:
            return False
        cached = state.usage_fetch_cache.get("claude")
        if cached and now - cached["ts"] < config.usage_poll_floor_sec:
            return False
        state.usage_fetch_inflight.add("claude")

    def run() -> None:
        try:
            fetch_claude_usage(
                config,
                state,
                clock=clock,
                opener=opener,
                runner=runner,
                diagnostic_sink=diagnostic_sink,
            )
        finally:
            with state.usage_fetch_lock:
                state.usage_fetch_inflight.discard("claude")

    spawn(run)
    return True


def _detached(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries a caller cannot use to reach back into the cache.

    `dict(entry)` is not enough: every entry holds nested window dicts, and a
    shallow copy leaves those shared, so mutating a published `fiveH` would
    edit stored state. `deepcopy` is safe here because entries hold only the
    JSON scalars and dicts the shaping code built.
    """
    return [copy.deepcopy(entry) for entry in entries]


def cached_entries(state: RuntimeState) -> list[dict[str, Any]]:
    """The last fetch's entries, copied so a caller cannot mutate the cache."""
    with state.usage_fetch_lock:
        cached = state.usage_fetch_cache.get("claude")
        return _detached(cached["entries"]) if cached else []


# The status-line payload names its windows rather than describing them by
# length, so the mapping is a suffix match and nothing is inferred. A bucket
# matching neither suffix is dropped: an unknown future window is better
# absent than mislabelled as one of these two.
_RECEIPT_WINDOWS = (("-5h", "fiveH"), ("-weekly", "week"))


def _receipt_window(now: float, raw: Any) -> tuple[int, dict[str, Any]] | None:
    """One status-line bucket as (percent used, shaped window), or nothing."""
    bucket = records.as_dict(raw)
    remaining = bucket.get("remaining_fraction")
    if not isinstance(remaining, (int, float)) or isinstance(remaining, bool):
        return None
    # The payload reports what is LEFT; the contract publishes what is USED.
    pct = max(0, min(100, round((1.0 - float(remaining)) * 100)))
    shaped: dict[str, Any] = {"pct": pct}
    resets = _epoch(bucket.get("reset_time"))
    if resets:
        shaped["reset"] = sessions.format_reset(now, resets)
    return pct, shaped


def shape_statusline(payload: dict[str, Any], now: float) -> list[dict[str, Any]]:
    """Antigravity's status-line payload as usage entries, or nothing.

    A fresh entry is built field by field rather than derived from the payload,
    because the payload also carries an account email and a transcript path,
    and neither may reach ``/api/data``.

    Two model families report the same two windows (``gemini-*`` and ``3p-*``
    for third-party models), so each slot has two candidates. The worse of the
    pair wins: the band exists to answer "am I about to run out", and the
    binding constraint is the honest number to show. The cost is that the tile
    does not say which family it came from.
    """
    quota = records.as_dict(payload.get("quota"))
    if not quota:
        return []
    best: dict[str, tuple[int, dict[str, Any]]] = {}
    for key, raw in quota.items():
        # JSON object keys are always strings, so the suffix match is safe.
        slot = next((name for suffix, name in _RECEIPT_WINDOWS if key.endswith(suffix)), None)
        if slot is None:
            continue
        mapped = _receipt_window(now, raw)
        if mapped is None:
            continue
        current = best.get(slot)
        if current is None or mapped[0] > current[0]:
            best[slot] = mapped
    if not best:
        return []
    entry: dict[str, Any] = {"harness": "antigravity", "state": "ok", "asOf": int(now)}
    for slot, (_pct, shaped) in best.items():
        entry[slot] = shaped
    return [entry]


def receive_statusline(
    state: RuntimeState,
    payload: dict[str, Any],
    *,
    now: float,
) -> dict[str, Any]:
    """Store a pushed status-line receipt. Returns the endpoint's wire response.

    Storing an empty entry list on an unusable payload is deliberate: it stamps
    the arrival, so a harness that stops reporting quota goes stale and drops
    out of the band rather than showing whatever it last said forever.
    """
    entries = shape_statusline(payload, now)
    with state.usage_fetch_lock:
        state.usage_receipts["antigravity"] = {"ts": now, "entries": entries}
    return {"ok": True, "usage": len(entries)}


def receipt_entries(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
) -> list[dict[str, Any]]:
    """Pushed entries still inside the activity window, copied.

    The receipt only arrives while the harness runs, so a stored figure can be
    arbitrarily old. Dropping past the window matches the Codex tile: an empty
    band is more honest than a percentage whose window has itself reset.
    """
    with state.usage_fetch_lock:
        cached = state.usage_receipts.get("antigravity")
        if not cached:
            return []
        stamp, entries = cached["ts"], _detached(cached["entries"])
    if not sessions.is_fresh(config, now, stamp, window_hours * 3600):
        return []
    return entries
