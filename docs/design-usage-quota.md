# Design: the usage quota surface

Owner for how quota numbers reach the dashboard: the disk readers, the Claude and Cursor fetchers,
the consent path, and the exact response fields Cargento reads. The security boundaries themselves
live in SECURITY.md ("Usage quota reads"); this document records how the implementation satisfies
them and which alternatives were rejected. The module map is owned by
[design-runtime-architecture.md](design-runtime-architecture.md).

The decision record is DEC-1 (Linear DRC-4053): show quota per harness, Codex first from disk,
then Claude behind a configurable opt-out, with an opt-in sidecar as the fallback shape if the
opt-out proves wrong.

## Q-1: Five sources, one payload contract

A usage entry is the same shape whoever produced it:

```
{harness, state: "ok" | "expired", asOf,
 fiveH: {pct, reset, resetAt},              // a gauge: used out of a limit
 week: {pct, reset, resetAt},
 month: {pct, reset, resetAt},              // the same, for a billing cycle
 used}                                      // a figure: spend
```

Each window carries its reset twice, from one `sessions.reset_fields` call so the pair cannot drift:
`reset` is the wall-clock words and `resetAt` is the instant in epoch seconds. The page renders a
countdown from `resetAt` and keeps the words as the row's tooltip. Two reasons, one measured and one
about the reader. "Thu 02:00" with its glyph needs 92px in a 76px column, so it truncated to name
neither the day nor the hour; and the question a quota window raises is how long until the allowance
returns, which a wall-clock time makes the reader subtract by hand. Sending the instant rather than a
server-rendered countdown also keeps the figure true between polls instead of ageing by up to the poll
interval. Past its reset the page reads "due", which says the window has rolled without pretending to
know the new number.

Every window slot is optional, and a harness fills only the ones it genuinely has. That is the
whole reason `month` exists rather than Cursor borrowing `week`: the slot names are what the page
labels the bar, so a monthly cycle rendered as "wk" would put a wrong label on a correct number.

- Codex publishes from disk. The CLI writes a `rate_limits` snapshot beside every token count in
  its rollout files, so `collectors/codex.py` reads the newest one. Windows arrive as durations
  (`window_minutes`), so 300 minutes maps to `fiveH` and anything a day or longer to `week`, which
  keeps a weekly-only plan rendering.
- Claude publishes from the fetch cache. `quota.py` holds the token read, the outbound request, and
  the cache; `collectors/claude.py` only copies entries out of it.
- Cursor publishes from the same fetch cache under its own vendor key, and fills `month` plus
  `used`. See Q-8.
- Copilot publishes consumption from disk, and no gauge at all. See Q-6.
- Antigravity publishes from a pushed receipt, with no credential and no request. See Q-7.

`asOf` is epoch seconds of the moment the numbers were true: the snapshot's own timestamp for
Codex, the fetch time for Claude and Cursor, the newest contributing row for Copilot, the receipt
time for Antigravity. The page refuses to show a percentage without it.

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

## Q-8: Cursor meters money, so the honest gauge is spend over a billing cycle

From `POST https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage`, four fields
are consumed:

| Field | Used as |
|---|---|
| `planUsage.totalSpend` | Spend so far, in integer cents. |
| `planUsage.limit` | The included allowance, in integer cents. Zero, absent or non-numeric means a plan with no denominator, and then no bar is published at all. |
| `billingCycleEnd` | The reset stamp. A decimal string of epoch MILLIseconds, which is how protobuf's JSON mapping encodes int64. |
| `planUsage.*PercentUsed` | Read and deliberately discarded. See below. |

Two things about this payload are traps, and both were only caught by running against a live
install rather than reasoning from the field names.

**The money is cents.** On a Pro plan `limit` is 2000, meaning the $20.00 of included usage, and a
spend of 18 is $0.18. Reading these as dollars overstates everything a hundredfold, and a small
balance hides that rather than revealing it. Confirmed independently against
`GetAggregatedUsageEvents`, whose `totalCostCents` agreed to the cent. Note which test pins this:
the percentage cannot, because a ratio is unit-invariant, so only the rendered money can. That is
why `used` carries "$0.18 of $20.00" rather than the bar alone.

**The payload's own percentage does not describe the included allowance.** With 18 cents of 2000
spent, `totalPercentUsed` reads 0.0521739, which is neither 0.9 (as a percent) nor 0.009 (as a
fraction). Its denominator is something else; 18/0.0521739 is 345, which points at the
bonus-inclusive pool the same response describes through `remainingBonus` and `bonusTooltip`, but
that was not confirmed and does not need to be. What matters is that spend over limit reproduces
Cursor's own `displayMessage` ("You've used 1% of your included usage") and the vendor's field does
not, so the arithmetic is done here and the field is ignored.

The credential is the macOS Keychain session token, and the endpoint is the one Cursor's own CLI
calls for its `/usage` command. Neither is documented for third parties, so the same defensive posture
as Claude's parse applies: an unusable spend figure, a malformed body, or an unreadable cycle end
each degrade to less display rather than to an error, and an unreadable cycle end still publishes the
percentage, because that figure is true without a reset.

macOS is the only supported platform, and this is a deliberate limit rather than an oversight. The
Keychain is macOS-only, and where the CLI persists this token on Linux and Windows is unverified.
Guessing a path would mean reading some other file and calling it a credential, so off macOS the
reader reports no credential source and Cursor stays out of the band. Installing the CLI on the
other two platforms is what unblocks them.

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
triggers nothing. `--no-usage` is the server-side override and acts in two places. At assembly, every
registry row that depends on the fetch simply gets no usage provider, so nothing reads the cache and
the `usage_fetch` capability flag (which wakes the modal) can never appear. At ingest,
`quota.receive_statusline` drops the quota fields of a pushed receipt before storing it. The second
gate is needed because assembly only stops publication: a pushed receipt arrives unsolicited, so
without it the flag would suppress display while the figures still sat in process memory. A contract test asserts
that for the whole set rather than for Claude alone, so a future fetch vendor wired in without the
gate fails there instead of quietly fetching under `--no-usage`.

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

Claude:

- macOS: the Keychain generic password with service `Claude Code-credentials`, read with
  `/usr/bin/security find-generic-password -w`.
- Everywhere else: `.credentials.json` beside the resolved `claude.projects` store, so a
  `CLAUDE_CONFIG_DIR` override moves both together.

Cursor: the Keychain generic password with service `cursor-access-token`, macOS only (Q-8). Both
vendors go through one `security` helper that takes the service name, so there is a single
subprocess call site to audit. It is service-scoped on both sides, and the test fake is scoped the
same way on purpose: a fake that answered every lookup with the same secret handed Claude's
credentials to Cursor's reader, which made Cursor fetch inside tests written for Claude alone.

Cursor's token is worth one extra sentence, recorded in SECURITY.md as well. It is stored under both
`cursor-access-token` and `cursor-refresh-token` as the identical value, so it can mint sessions and
is broader than Claude's quota-scoped token. The never-refresh rule below is what bounds it: the
value is only ever presented as a bearer token, so the extra capability is never exercised. A
narrower, user-created API key was considered and set aside because it needs setup and it is
unverified whether one authenticates this RPC at all.

Failures are deliberately not one bucket. An expired or rejected token (past `expiresAt`, or an
HTTP 401/403) publishes an `expired` entry, and the page renders the pointer at signing in again
in the harness. An unavailable token (denied Keychain prompt, missing file, malformed JSON) keeps
Claude out of the band entirely, because "sign in again" is wrong advice when the harness session
may be fine. Every failure surfaces in diagnostics as a fixed category word plus an exception
type name; no value read from a credential source or a response is ever interpolated.

## Q-7: A harness can hand its quota over, so nothing needs fetching

Antigravity keeps no quota on disk and its stored credential is not usable as a bearer token, so
neither the Codex approach nor the Claude one applies. What it does do is invoke a user-configured
command on every agent-state change and pipe it a JSON state payload, and that payload carries a
first-class `quota` object. Pointing that command at Cargento is the whole integration.

**No new script ships for this.** `notify_hook.py` was already a stdin-reading loopback forwarder
that validates its target, disables proxying, refuses redirects and always exits 0, with the URL as
its first argument. Nothing in it was ever Claude-specific, so the registration is:

```
python3 <skill-dir>/notify_hook.py http://127.0.0.1:4553/api/usage
```

`POST /api/usage` mirrors `/api/notify` exactly: the same `_local_ok()` gate, the declared length
checked before any read, and a malformed or non-object body degraded to `{}` rather than raised.
Receipts live in memory beside the fetch cache under the same lock, so Cargento's two written paths
are unchanged and `--diagnose` stays free of side effects by construction.

Three decisions worth keeping:

- **The windows are named, not measured.** The payload keys its buckets `gemini-5h`,
  `gemini-weekly`, `3p-5h`, `3p-weekly`, so the mapping is a suffix match. Codex's approach of
  classifying by duration is unnecessary here, and a bucket matching neither suffix is dropped: an
  unknown future window is better absent than mislabelled as one of these two.
- **Two model families report the same two windows**, so each slot has two candidates, and the
  worse of the pair wins. The band exists to answer "am I about to run out", and the binding
  constraint is the honest number. The cost, accepted, is that the tile does not say which family
  the figure belongs to.
- **`remaining_fraction` is what is left, and the contract publishes what is used**, so it inverts.
  Worth stating because the payload observed on a fresh account reported `1` for every bucket,
  which renders 0% whether the arithmetic is right or wrong. The tests pin 0.4 and 0.0 instead.

The receipt is stamped and dropped past the activity window, like a Codex snapshot: it only arrives
while the harness runs, so a stored figure can be arbitrarily old and an empty band beats a
percentage whose window has itself reset. An unusable payload still stamps its arrival, so a harness
that stops reporting quota goes stale and drops out rather than showing its last figure forever.

The payload also carries an account email and a transcript path. Entries are therefore built field
by field rather than derived from the payload, and a test asserts no other field survives shaping.

`usage_is_fetch` stays `False` for this row. There is no outbound request to disclose, so the
first-run modal must not fire; the user installed the forwarder deliberately, which is the consent.
`--no-usage` still drops the provider, because a user turning usage off means the section, not just
its network half, and it also drops the quota fields at ingest so a receipt pushed while the flag is
set is not retained. The endpoint still answers 200: a status-line command must never see an error
from Cargento.

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

### Cursor's nicer-looking usage endpoint, and its two dead legacy ones

Three Cursor surfaces return HTTP 200 for an individual and were still rejected. Recorded because
each one looks like the right answer until it is checked.

`GET https://cursor.com/api/usage-summary` has by far the best shape: self-describing
(`individualUsage.plan.{used,limit,remaining}`), ISO-8601 dates instead of millisecond strings, and
an `onDemand` block. It rejects a bearer token with 401 and accepts only a forged
`WorkosCursorSessionToken` cookie, built as `{authId}::{accessToken}`, with `Origin` and `Referer`
spoofed for anything mutating. That is impersonating a browser session, which is a worse posture
than using the CLI's own bearer route, and it would put a cookie in the request where the contract
says the token and nothing else. Shape convenience does not buy that.

`GET https://api2.cursor.sh/auth/usage` and `GET https://cursor.com/api/usage` both answer 200, and
both answer in the retired premium-request model: every counter zero, `maxRequestUsage` null. Live
and meaningless on a usage-priced plan. This is precisely Copilot's `totalPremiumRequests` trap from
Q-6, met a second time in a different vendor, which is the argument for capturing a real payload
before writing any parser.

The Admin, Analytics and AI Code Tracking APIs are Cursor's only documented ones, and they are
org-scoped, with the latter two Enterprise-gated. `GetTeamSpend` answers 401 "Team ID is required".
Cargento serves individuals, so none of them qualify, exactly as the survey behind DEC-1 predicted.

### Rendering Cursor's monthly cycle in the weekly slot

The slot names are what the page prints next to the bar, so a billing cycle labelled "wk" is a wrong
label on a right number, in the one band whose entire value is being trustable. Adding a `month`
slot costs a `USAGE_STATS` entry, a default, one line in the renderer and a consent-copy sentence.
Extras-only (the Q-6 shape, `used` and no bar) was the other candidate and was rejected for the
opposite reason: Cursor publishes a real limit and a real reset, so suppressing the gauge would
throw away true information to avoid touching shared UI.

### Antigravity's fetch, attempted and not feasible (2026-08-04)

Scope note before the detail: it is the *fetch* that is rejected here. Antigravity quota does ship,
by reading what the CLI pushes to its own status-line command, which is Q-7. Nothing below was
wasted, but none of it is the reason the tile works today.

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
