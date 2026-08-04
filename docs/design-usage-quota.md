# Design: the usage quota surface

Owner for how quota numbers reach the dashboard: the Codex disk reader, the Claude fetcher, the
consent path, and the exact response fields Cargento reads. The security boundaries themselves
live in SECURITY.md ("Usage quota reads"); this document records how the implementation satisfies
them and which alternatives were rejected. The module map is owned by
[design-runtime-architecture.md](design-runtime-architecture.md).

The decision record is DEC-1 (Linear DRC-4053): show quota per harness, Codex first from disk,
then Claude behind a configurable opt-out, with an opt-in sidecar as the fallback shape if the
opt-out proves wrong.

## Q-1: Two sources, one payload contract

A usage entry is the same shape whoever produced it:

```
{harness, state: "ok" | "expired", asOf,
 fiveH: {pct, reset}, week: {pct, reset}}
```

- Codex publishes from disk. The CLI writes a `rate_limits` snapshot beside every token count in
  its rollout files, so `collectors/codex.py` reads the newest one. Windows arrive as durations
  (`window_minutes`), so 300 minutes maps to `fiveH` and anything a day or longer to `week`, which
  keeps a weekly-only plan rendering.
- Claude publishes from the fetch cache. `quota.py` holds the token read, the one outbound
  request, and the cache; `collectors/claude.py` only copies entries out of it.

`asOf` is epoch seconds of the moment the numbers were true: the snapshot's own timestamp for
Codex, the fetch time for Claude. The page refuses to show a percentage without it.

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
