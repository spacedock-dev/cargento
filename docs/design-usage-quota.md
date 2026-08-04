# Design: the usage quota surface

Owner for how quota numbers reach the dashboard: the Codex disk reader, the Claude fetcher, the
consent path, and the exact response fields Cargento reads. The security boundaries themselves
live in SECURITY.md ("Usage quota reads"); this document records how the implementation satisfies
them and which alternatives were rejected. The module map is owned by
[design-runtime-architecture.md](design-runtime-architecture.md).

The decision record is DEC-1 (Linear DRC-4053): show quota per harness, Codex first from disk,
then Claude behind a configurable opt-out, with an opt-in sidecar as the fallback shape if the
opt-out proves wrong.

## Q-1: Three sources, one payload contract

A usage entry is the same shape whoever produced it:

```
{harness, state: "ok" | "expired", asOf,
 fiveH: {pct, reset}, week: {pct, reset},   // a gauge: used out of a limit
 used}                                     // a figure: spend with no limit
```

- Codex publishes from disk. The CLI writes a `rate_limits` snapshot beside every token count in
  its rollout files, so `collectors/codex.py` reads the newest one. Windows arrive as durations
  (`window_minutes`), so 300 minutes maps to `fiveH` and anything a day or longer to `week`, which
  keeps a weekly-only plan rendering.
- Claude publishes from the fetch cache. `quota.py` holds the token read, the one outbound
  request, and the cache; `collectors/claude.py` only copies entries out of it.
- Copilot publishes consumption from disk, and no gauge at all. See Q-6.

`asOf` is epoch seconds of the moment the numbers were true: the snapshot's own timestamp for
Codex, the fetch time for Claude, the newest contributing row for Copilot. The page refuses to show
a percentage without it.

## Q-6: A harness can report spend without reporting a limit

GitHub bills Copilot in AI Units, and the CLI records its own consumption per model request in
`session-store.db`'s `assistant_usage_events` table: `total_nano_aiu`, `request_multiplier`, the
token breakdown, and a `created_at` per row. That is real spend rather than an estimate, and reading
it needs no credential, so it ships under the original two invariants like the Codex tile.

The entitlement is the part that does not exist locally. GitHub keeps it server-side and the CLI
never writes it down, which was confirmed by searching every file under `~/.copilot`: `entitlement`
and `allowance` appear in none of them, though both are strings inside the CLI binary. So there is a
numerator and no denominator, and no honest percentage can be derived.

Hence `used`: a preformatted figure, rendered as a labelled row with no track and no percent sign,
because a bar implies a fraction of something. Three consequences worth stating:

- **It is always shown when present.** The extras (`burn`, `today`, `cost`) default to off in
  `usageCfg`, and a consumption-only entry whose single figure sat behind `configure` rendered as a
  harness name and a timestamp with no number, which reads as a broken row rather than a hidden
  setting. A contract test executes the page script and fails if the figure stops surviving the
  default config.
- **It is windowed on each row's own timestamp**, so the number answers "in the last
  `window_hours`" rather than "since however much session history happens to be retained", which
  would drift as old session directories accumulate or get cleaned.
- **Premium requests are the wrong target.** The survey behind DEC-1 described per-session
  premium-request estimates, but on an AI-Credits account `totalPremiumRequests` reads 0 while real
  spend flows through the AIU fields. The legacy counter is deliberately not read.

The alternative shapes considered were reusing the `today` extra and force-showing it for
window-less harnesses, which makes `usageCfg`'s meaning depend on the payload, and deriving a burn
rate to give the figure context, which is a heuristic over however few rows exist. A first-class
field says exactly what it is and needs neither.

## Q-2: The response fields Cargento reads

From `GET https://api.anthropic.com/api/oauth/usage` (with `anthropic-beta: oauth-2025-04-20`),
exactly three fields are consumed:

| Field | Used as |
|---|---|
| `five_hour.utilization`, `seven_day.utilization` | The window percentage, rounded and clamped to 0 to 100. |
| `five_hour.resets_at`, `seven_day.resets_at` | The reset stamp. Both shapes the endpoint has sent are accepted: epoch seconds, or an ISO-8601 string. |
| `limits[]` | Acknowledged but not published. It carries per-model windows; the roadmap item that renders them (A3 on the Visibility board) decides their shape when it lands. Publishing unused data would widen the payload for nothing. |

Anything else in the response is ignored. The endpoint is undocumented for third parties, so the
parse is defensive throughout: a malformed body or a response with no recognizable window caches
an empty entry list and a one-word diagnostic, never an error tile.

## Q-3: Consent rides on the poll

The fetch trigger lives in `/api/data` handling, not in collection, and fires only for requests
carrying `usage=1`. The page sends that parameter exactly when the usage switch is on and the
first-run disclosure modal has been answered. Three contract clauses fall out of this placement
rather than being scheduled or checked:

1. "No polling while no dashboard page is connected": no request, no fetch.
2. "Disclosed before it acts": on first run the modal is up, no poll carries consent yet, and the
   first fetch follows the user's answer.
3. "`--diagnose` never triggers a fetch": diagnostics run `collect()`, and `collect()` only reads
   the cache.

The switch itself is browser state (`localStorage`), which the server cannot see except through
the request. That is why the parameter exists: a bare `curl /api/data` gets whatever is cached and
triggers nothing. `--no-usage` is the server-side override and acts earlier, at assembly: the
Claude registry row simply gets no usage provider, so nothing reads the cache and the
`usage_fetch` capability flag (which wakes the modal) can never appear.

## Q-4: The fetch never blocks a poller

`collect_json` holds the memo lock through collection, so a synchronous network call there would
stall every connected page behind a timeout. `quota.request_fetch` instead stamps an in-flight
marker and hands the work to a daemon thread; the triggering request is answered from the current
cache and the next 5-second poll picks up the result. The five-minute floor is a comparison
against the cache stamp, and the stamp is written on failure as well as success, so a missing
credential retries on the same cadence as a healthy fetch. That is the "never a retry storm"
posture in one mechanism.

The Keychain subprocess gets a deliberately long timeout (120 seconds) because the first read can
raise a user-facing permission prompt, and killing the prompt mid-answer would read as a denial.

## Q-5: Where the token comes from, and what a failure means

- macOS: the Keychain generic password with service `Claude Code-credentials`, read with
  `/usr/bin/security find-generic-password -w`.
- Everywhere else: `.credentials.json` beside the resolved `claude.projects` store, so a
  `CLAUDE_CONFIG_DIR` override moves both together.

Failures are deliberately not one bucket. An expired or rejected token (past `expiresAt`, or an
HTTP 401/403) publishes an `expired` entry, and the page renders the pointer at signing in again
in the harness. An unavailable token (denied Keychain prompt, missing file, malformed JSON) keeps
Claude out of the band entirely, because "sign in again" is wrong advice when the harness session
may be fine. Every failure surfaces in diagnostics as a fixed category word plus an exception
type name; no value read from a credential source or a response is ever interpolated.

## Rejected alternatives worth keeping rejected

### Refreshing an expired token

Claude Code rotates its own OAuth session. A second refresher racing it can invalidate the
harness's session from under it, which turns a dashboard nicety into a login outage. The contract
forbids it; the display-off-with-pointer behaviour is the whole answer.

### Fetching synchronously inside the request handler

Simplest to test, but `collect_json` single-flights collection under a lock, so one slow vendor
endpoint would freeze every open dashboard for the duration of the timeout, once every five
minutes. The background thread costs an in-flight flag and is otherwise invisible.

### A server-side polling loop

A timer that fetches every five minutes regardless of pages is less code than the consent
parameter, but it violates "no polling while no dashboard page is connected" the moment the last
tab closes, and it keeps a `--daemon` instance fetching overnight for nobody.

### Storing the consent server-side

A POST endpoint writing the switch into server state would survive across browsers, but it makes
the dashboard's only persistent setting live in two places (localStorage drives the UI either
way), adds a mutating endpoint to a surface that deliberately has almost none, and still needs
the query parameter for the first-run case. The parameter alone is the smaller contract.

### Publishing `limits[]` now

The per-model rows have no rendering yet. Shipping them into `/api/data` early would freeze a
shape nobody has designed against; the parse point is marked and the field documented here
instead.

### Antigravity quota, attempted and not feasible (2026-08-04)

Antigravity is the Google authority, and it is the obvious second vendor: Cargento already reads
its sessions, and its CLI displays quota on a status line. It was attempted with the owner's
approval, against a live install, and it does not work. Recorded here at length because everything
about it looks promising until the last step, so the next person will otherwise repeat the work.

What checked out. The endpoint is real and pinned: the `agy` binary carries
`https://cloudcode-pa.googleapis.com` and the method `v1internal:retrieveUserQuota`, which is the
same method name the retired Gemini CLI used, so lineage and current binary agree. The refresher is
real too, and even throttles itself: `quota_manager.go` logs `doRefreshQuota: starting reload`,
`skipped (throttled)` and `skipped (not logged in)`. The credential's location is real: a macOS
Keychain generic-password item with service `gemini` and account `antigravity`.

Where it fails, on two independent grounds:

1. **The stored credential is not a usable token.** The Keychain item holds an opaque
   2246-character string: no `ya29.` or `1//` prefix, not a JWT, not base64, single segment, and
   containing none of `access_token`, `refresh_token`, `expiry`, `token_type` or `scope` as
   substrings. Presented as a bearer token it returns HTTP 401 with Google's own text, "Expected
   OAuth 2 access token, login cookie or other valid authentication credential". Three request
   bodies were tried (empty, absent, and constants-only metadata) and all three returned the same
   401, so the failure is authentication rather than request shape. Antigravity evidently keeps its
   credential in a proprietary form and mints access tokens in process. No `ya29.` token exists in
   any file under the Gemini home or the usual macOS and Linux config roots.
2. **Nothing is persisted to read instead.** A disk read was the preferred outcome, since it needs
   no credential and stays inside the original two invariants, and the binary's
   `retrieveUserQuotaSummaryCache` symbol made it look likely. Every file under
   `~/.gemini/antigravity-cli/` below 2 MB was searched for `remainingFraction`, `quotaInfo`,
   `minutesPerBucket`, `movingWindowSize`, `resetTime` and `userTier`. Zero matches. The logs record
   that a refresh happened, never what it returned. The cache is in memory.

The opt-in sidecar that DEC-1 kept as a fallback does not rescue this: a sidecar would meet the same
opaque credential. So the blocker is the credential format, not Cargento's architecture, and no
option in DEC-1 reaches it.

Two things learned that outlive the attempt. First, Google's quota shape is not this contract's
shape: the response model is bucketed and moving-window (`remainingFraction`, `minutesPerBucket`,
`movingWindowSize`, `bucketId`, `resetTime`, `hasQuotaUnavailabilityError`), so `remainingFraction`
is the inverse of Anthropic's `utilization` and windows are lengths rather than names, which would
make the mapping follow `codex._usage_window` rather than Claude's. Second, the Code Assist RPCs are
POSTs carrying a `ClientMetadata` body (`platform`, `ideType`, `ideVersion`, `pluginType`,
`pluginVersion`, `updateChannel`, `project`), so had authentication worked, there would have been a
real question about whether sending that breaks this document's own "no machine identifiers" clause.
Anyone revisiting this inherits that question unanswered.

Revisit only if Antigravity begins persisting quota to disk, or ships a documented local interface.
The endpoint and method above will still be correct; it is the credential that has to change.
