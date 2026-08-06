"""Quota acquisition: the outbound fetch, the pushed-in receipts, and the cache.

Two sources fill one cache, and collectors read it back without caring which
filled it.

**The fetch** is the whole of Cargento's outbound network surface, and it is
bound by the "Usage quota reads" section of SECURITY.md: each request carries
the vendor's own OAuth token and nothing else, the token is never refreshed,
never written, never logged and never served, and at most one request per
vendor leaves every five minutes. A violation of any of those is a security
bug, not a defect. Diagnostics emitted here are fixed category words plus
exception type names for that reason — never a value read from a credential
source or a response.

Two vendors fetch: Claude and Cursor. Each gets its own credential reader,
endpoint and response parser, and its own pair of gates, so a vendor that is
slow or broken cannot delay or suppress the other's refresh. `FETCH_VENDORS`
is the whole list, and every endpoint in it is named in SECURITY.md.

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
from typing import TYPE_CHECKING, Any

from . import io as runtime_io
from . import records, sessions
from .config import primary_store

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import RuntimeConfig
    from .state import RuntimeState

    # One vendor's credential read plus its outbound request, shaped into
    # entries: (config, now, opener, runner) -> (entries, problem category).
    VendorReader = Callable[
        [RuntimeConfig, float, Callable[..., Any], Callable[..., Any]],
        tuple[list[dict[str, Any]], str | None],
    ]

# The endpoints this module may call, spelled exactly as SECURITY.md names
# them. A new vendor's endpoint must be named there before it is added here.
USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
USAGE_BETA_VALUE = "oauth-2025-04-20"
# Cursor's own CLI calls this RPC for its `/usage` command, against the
# backend its config records as `serverConfigCache.backendUrl`. Reached with a
# plain bearer header: no cookie, and no browser-session impersonation.
CURSOR_USAGE_ENDPOINT = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
# Where Claude Code keeps its OAuth credentials: a Keychain generic password
# on macOS, a JSON file beside the projects store everywhere else.
KEYCHAIN_SERVICE = "Claude Code-credentials"
CREDENTIALS_FILENAME = ".credentials.json"
# Cursor CLI keeps its session token in the macOS Keychain and nowhere else we
# have verified. Where it lands on Linux and Windows is deliberately not
# guessed: a wrong path would read some other file and call it a credential,
# so off macOS the reader reports no credential and Cursor stays out of the
# band. NOTE for SECURITY.md: Cursor stores the identical value under
# `cursor-refresh-token`, so this token can also mint sessions. It is sent as
# a bearer token and never exchanged.
CURSOR_KEYCHAIN_SERVICE = "cursor-access-token"
# The first Keychain read can raise a user-facing permission prompt, so the
# subprocess must be allowed to sit through a human answering it. On timeout
# the read fails as "unavailable" and the poll floor schedules the retry.
KEYCHAIN_TIMEOUT_SEC = 120.0
# Cursor reports money in integer cents. Naming the divisor keeps the unit
# visible: reading these as dollars overstates every figure a hundredfold,
# which a small balance hides rather than reveals.
CENTS_PER_UNIT = 100


def credentials_path(config: RuntimeConfig) -> str:
    """The harness's credential file, derived from the resolved projects store.

    Deriving from `claude.projects` keeps one source of truth for where the
    Claude home is: a `CLAUDE_CONFIG_DIR` override moves both together.
    """
    windows = config.platform_name == "win32"
    dirname = ntpath.dirname if windows else posixpath.dirname
    join = ntpath.join if windows else posixpath.join
    return join(dirname(primary_store(config, "claude.projects")), CREDENTIALS_FILENAME)


def _keychain_secret(
    runner: Callable[..., Any],
    service: str,
) -> tuple[str | None, str | None]:
    """(secret, problem category) from one macOS Keychain generic password.

    Shared by every vendor that keeps its credential there. The service name
    is the only thing that varies, and the secret is returned to the caller
    rather than logged: problem categories are fixed words plus exception type
    names precisely so that nothing read from the Keychain reaches diagnostics.
    """
    try:
        result = runner(
            ["/usr/bin/security", "find-generic-password", "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=KEYCHAIN_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"keychain {type(exc).__name__}"
    if result.returncode != 0 or not str(result.stdout).strip():
        return None, "keychain item unavailable"
    return str(result.stdout), None


def _read_token(
    config: RuntimeConfig,
    runner: Callable[..., Any],
) -> tuple[str | None, float | None, str | None]:
    """(access token, expiry epoch seconds, problem category).

    Problem categories are fixed words plus exception type names because they
    reach diagnostics; no value read from the Keychain or the file ever does.
    """
    if config.platform_name == "darwin":
        secret, problem = _keychain_secret(runner, KEYCHAIN_SERVICE)
        if problem:
            return None, None, problem
        raw = secret or ""
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
    """A reset stamp as epoch seconds: the endpoint has sent both shapes.

    The string branch defers to `records.iso_epoch`, so an offset-less stamp is
    read as UTC here exactly as it is everywhere else. It matters most on this
    path: a `resets_at` misread by the server's own UTC offset moves every reset
    countdown and, since A5 landed, the burn projection that fires off it. The
    live capture records all four `resets_at` fields arriving with an explicit
    `+00:00`, so the naive branch is a guard rather than the normal case.
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
        return float(raw)
    return records.iso_epoch(raw)


def _epoch_millis(raw: Any) -> float | None:
    """A stamp as epoch seconds, given epoch milliseconds.

    Cursor sends these as decimal *strings*, which is how protobuf's JSON
    mapping encodes 64-bit integers, so `_epoch` cannot read them: it would try
    ISO parsing and fail. Rejected rather than trusted blindly, because a value
    already in seconds would otherwise be divided into 1970.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        try:
            raw = int(raw)
        except ValueError:
            return None
    if not isinstance(raw, (int, float)) or raw <= 0:
        return None
    return float(raw) / 1000.0


def _shape_window(now: float, raw: Any) -> dict[str, Any] | None:
    """One usage window mapped onto the payload contract, or nothing."""
    win = records.as_dict(raw)
    pct = win.get("utilization")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return None
    shaped: dict[str, Any] = {"pct": max(0, min(100, round(pct)))}
    resets = _epoch(win.get("resets_at"))
    if resets:
        shaped.update(sessions.reset_fields(now, resets))
    return shaped


def _expired_entry(now: float, harness: str) -> dict[str, Any]:
    return {"harness": harness, "state": "expired", "asOf": int(now)}


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
            return [_expired_entry(now, "claude")], None
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
        return [_expired_entry(now, "claude")], None
    return _fetch_windows(config, token or "", now, opener)


def _cents(amount: Any) -> int | None:
    """A non-negative integer cent amount, or nothing."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
        return None
    return int(amount)


def _money(cents: int) -> str:
    return f"${cents / CENTS_PER_UNIT:.2f}"


def _cursor_entry(now: float, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Cursor's billing-period usage as one entry, or nothing.

    The percentage is computed from spend against the included limit rather
    than taken from the payload's own `totalPercentUsed`. That field's
    denominator is not the included allowance: on a $20 plan with 18 cents
    spent it reads 0.0521739, which is neither 0.9 (percent) nor 0.009
    (fraction). Spend over limit reproduces Cursor's own `displayMessage`
    ("You've used 1% of your included usage"), so it is the honest figure.

    Both amounts are integer cents. `used` carries the money as well, because
    a lone percentage near zero hides whether the plan is nearly untouched or
    the allowance is tiny.
    """
    plan = records.as_dict(payload.get("planUsage"))
    spend = _cents(plan.get("totalSpend"))
    if spend is None:
        return None
    entry: dict[str, Any] = {"harness": "cursor", "state": "ok", "asOf": int(now)}
    limit = _cents(plan.get("limit"))
    if limit:
        window: dict[str, Any] = {"pct": max(0, min(100, round(spend * 100 / limit)))}
        resets = _epoch_millis(payload.get("billingCycleEnd"))
        if resets:
            window.update(sessions.reset_fields(now, resets))
        entry["month"] = window
        entry["used"] = f"{_money(spend)} of {_money(limit)}"
    else:
        # An unlimited or limit-less plan spends without a denominator, so
        # there is nothing for a bar to be a fraction of. Same shape as
        # Copilot: the money, and no gauge pretending to be one.
        entry["used"] = _money(spend)
    return entry


def _cursor_token(
    config: RuntimeConfig,
    runner: Callable[..., Any],
) -> tuple[str | None, str | None]:
    """(session token, problem category) for Cursor.

    Only macOS is supported, because that is the only place the token's
    location has been verified. Elsewhere this reports no credential source,
    which keeps Cursor out of the band instead of advising a sign-in that would
    not help.
    """
    if config.platform_name != "darwin":
        return None, "no credential source on this platform"
    return _keychain_secret(runner, CURSOR_KEYCHAIN_SERVICE)


def _cursor_entries(
    config: RuntimeConfig,
    now: float,
    opener: Callable[..., Any],
    runner: Callable[..., Any],
) -> tuple[list[dict[str, Any]], str | None]:
    """Cursor's quota: one credential read and one outbound POST."""
    token, problem = _cursor_token(config, runner)
    if problem:
        return [], problem
    request = urllib.request.Request(
        CURSOR_USAGE_ENDPOINT,
        data=b"{}",
        headers={
            "Authorization": f"Bearer {(token or '').strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=config.usage_fetch_timeout_sec) as response:
            body = response.read(config.usage_response_cap_bytes)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            # Cursor answers a stale token with 401 and `actionRequired:
            # "login"`, so the remedy is the harness's, exactly as for Claude.
            return [_expired_entry(now, "cursor")], None
        return [], f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return [], type(exc).__name__
    return _cursor_parse(now, body)


def _cursor_parse(now: float, body: bytes) -> tuple[list[dict[str, Any]], str | None]:
    """One response body as entries, or a category naming why it was not."""
    try:
        payload = records.as_dict(json.loads(body))
    except ValueError:
        return [], "malformed response"
    entry = _cursor_entry(now, payload)
    if entry is None:
        return [], "response carried no plan usage"
    return [entry], None


# Every vendor the fetcher knows, paired with the reader that produces its
# entries. The gates in `request_fetch` are applied per vendor, so one slow or
# broken vendor cannot delay or suppress another's refresh.
FETCH_VENDORS: tuple[tuple[str, VendorReader], ...] = (
    ("claude", _claude_entries),
    ("cursor", _cursor_entries),
)


def fetch_usage(
    config: RuntimeConfig,
    state: RuntimeState,
    vendor: str,
    reader: VendorReader,
    *,
    clock: Callable[[], float] = time.time,
    opener: Callable[..., Any] = urllib.request.urlopen,
    runner: Callable[..., Any] = subprocess.run,
    diagnostic_sink: Callable[[str], object] = print,
) -> None:
    """One vendor's fetch, synchronous, ending in a cache write.

    A failure caches an empty entry list on purpose: the write stamps the
    attempt, and the poll floor reads that stamp, so a broken endpoint or a
    missing credential is retried on the same five-minute cadence as success,
    never in a storm.
    """
    now = clock()
    entries, note = reader(config, now, opener, runner)
    if note:
        runtime_io.diag(f"[{vendor}] usage fetch: {note}", diagnostic_sink)
    with state.usage_fetch_lock:
        state.usage_fetch_cache[vendor] = {"ts": clock(), "entries": entries}


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
    """Maybe start a background fetch per vendor; never block the caller.

    This is the only entry point the serving path calls, and it holds every
    gate of the polling posture: nothing with the feature off, nothing while
    a fetch is already in flight, and nothing inside the five-minute floor of
    the last attempt. It is invoked only from `/api/data` requests that carry
    the page's consent, which is what makes "no polling while no dashboard
    page is connected" structural rather than scheduled.

    The gates are per vendor, so Cursor still refreshes while a Claude fetch
    sits in flight, and a vendor whose endpoint is down cannot hold the others
    off. Returns whether *any* vendor started, which is all the caller uses.
    """
    if not config.usage_fetch_enabled:
        return False
    now = clock()
    started = False
    for vendor, reader in FETCH_VENDORS:
        with state.usage_fetch_lock:
            if vendor in state.usage_fetch_inflight:
                continue
            cached = state.usage_fetch_cache.get(vendor)
            if cached and now - cached["ts"] < config.usage_poll_floor_sec:
                continue
            state.usage_fetch_inflight.add(vendor)

        def run(vendor: str = vendor, reader: VendorReader = reader) -> None:
            # Bound as defaults, not closed over: every thread would otherwise
            # see the loop's final vendor and one cache key would take them all.
            try:
                fetch_usage(
                    config,
                    state,
                    vendor,
                    reader,
                    clock=clock,
                    opener=opener,
                    runner=runner,
                    diagnostic_sink=diagnostic_sink,
                )
            finally:
                with state.usage_fetch_lock:
                    state.usage_fetch_inflight.discard(vendor)

        spawn(run)
        started = True
    return started


def _detached(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries a caller cannot use to reach back into the cache.

    `dict(entry)` is not enough: every entry holds nested window dicts, and a
    shallow copy leaves those shared, so mutating a published `fiveH` would
    edit stored state. `deepcopy` is safe here because entries hold only the
    JSON scalars and dicts the shaping code built.
    """
    return [copy.deepcopy(entry) for entry in entries]


def cached_entries(state: RuntimeState, vendor: str) -> list[dict[str, Any]]:
    """One vendor's last fetch, copied so a caller cannot mutate the cache.

    The vendor is required rather than defaulted: a wrong default would quietly
    publish another vendor's numbers under this harness's name.
    """
    with state.usage_fetch_lock:
        cached = state.usage_fetch_cache.get(vendor)
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
        shaped.update(sessions.reset_fields(now, resets))
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
    config: RuntimeConfig | None = None,
) -> dict[str, Any]:
    """Store a pushed status-line receipt. Returns the endpoint's wire response.

    Storing an empty entry list on an unusable payload is deliberate: it stamps
    the arrival, so a harness that stops reporting quota goes stale and drops
    out of the band rather than showing whatever it last said forever.

    With server-side usage disabled the quota fields are dropped before storage,
    not rejected at the door: SECURITY.md promises nothing is retained with the
    feature off, and the response still reports success so a harness's status
    line never surfaces a Cargento error.
    """
    enabled = True if config is None else config.usage_fetch_enabled
    entries = shape_statusline(payload, now) if enabled else []
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
