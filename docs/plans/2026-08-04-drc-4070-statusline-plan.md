# Plan: DRC-4070, Antigravity quota via the status-line payload

## Issue Summary

Antigravity pushes a JSON state payload, carrying a first-class `quota` object, to a user-configured
status-line command on every agent-state change. Read that instead of fetching anything: no
credential, no outbound request, both original invariants intact.

## Classification

**Type:** feature
**Priority:** Medium
**Status:** Todo (corrected from a wrong not-feasible verdict)
**Branch:** `feature/drc-4070-usage-fetcher-antigravity-quota-google-authority` (deleted after PR #77
was closed; a fresh one is needed, and the name should change since this is not a fetcher)

## The finding that collapses most of the plan

`notify_hook.py` is **payload-agnostic and already does this job**. It reads JSON on stdin, validates
the target is loopback, disables proxying, refuses redirects, POSTs, and always exits 0. The target
URL is `argv[1]`. A status-line registration is therefore:

```
python3 <skill-dir>/notify_hook.py http://127.0.0.1:4553/api/usage
```

Nothing about that script is Claude-specific. Its docstring names Claude hooks as the use case and
its module docstring explains it exists because the equivalent shell one-liner is not portable,
which is just as true for a status-line command.

That answers four of the seven open questions on the ticket at once:

| Question | Answer |
|---|---|
| One forwarder or two? | **One.** The existing script, invoked with a different URL. |
| POST or cache file? | **POST**, reusing an already-hardened path rather than writing a second one. |
| Where does the cache live, what shape? | **Nowhere on disk.** In-memory in `RuntimeState`, exactly like hook notification state. Cargento's written-paths contract does not change. |
| Install documentation? | One more line beside the existing optional-hooks section, pointing at the same script. |

What remains is server-side only.

## Current state

- `do_POST` (`http_api.py:267`) accepts exactly `/api/shutdown` and `/api/notify`, 404s everything
  else, and gates both behind `_local_ok()` (Host, Origin, `Sec-Fetch-Site`).
- `/api/notify` is the model to copy: `Content-Length` checked **before** the read against
  `config.notification_body_cap_bytes`, a defensive `json.loads` falling back to `{}`, a non-dict
  payload coerced to `{}`, then a handler that mutates in-memory state and returns a fixed wire
  format.
- `quota.py` owns the usage cache (`state.usage_fetch_cache`, `cached_entries`) and reads it back for
  `collectors/claude.py`. Its module docstring currently claims to be "the whole of Cargento's
  outbound network surface", which a pushed-inbound source makes untrue.
- `collectors/antigravity.py` exists with `discover`/`collect` and no `usage` provider.
- `HarnessSpec.usage_is_fetch` exists and is what raises the `usage_fetch` flag that wakes the
  disclosure modal.

## What to build

1. **`POST /api/usage`** in `do_POST`, mirroring `/api/notify`'s guards exactly: same pre-read
   length check against a config cap, same defensive parse, same `_local_ok()` gate, a fixed
   compact-JSON response.
2. **A receipt handler** that shapes the status-line payload's `quota` object into usage entries and
   stores them in a new `RuntimeState` field under its own lock, stamped with receipt time as
   `asOf`. Field names are snake_case here (`remaining_fraction`, `reset_time`,
   `reset_in_seconds`), unlike the camelCase RPC surface.
3. **`antigravity.usage()`** reading that state and nothing else. No network, no disk, so
   `--diagnose` stays clean by construction.
4. **Registry wiring** with `usage=antigravity.usage` and **`usage_is_fetch=False`**. This is the
   important one: it is not a fetch, so the disclosure modal must not fire for it. There is nothing
   to disclose, because the user installed the forwarder deliberately.
5. **Staleness**: drop entries older than the activity window, the way `codex.usage` drops old
   snapshots. The payload only arrives while `agy` runs, so a cached figure can be arbitrarily stale
   and the band must not present it as current.
6. **Docs**: SECURITY.md invariant 2 says "The one mutating endpoint is `POST /api/notify`" and must
   name two; `docs/design-usage-quota.md` gains the third source and this shape; SKILL.md gains the
   registration line.

## Acceptance criteria

1. Given a status-line POST carrying a `quota` object, when the band renders, then Antigravity shows
   its windows keyed `antigravity`.
2. Given `remaining_fraction: 0.4`, then the published percentage is **60** (used, not remaining).
3. Given a receipt older than the activity window, then the entry is dropped rather than shown.
4. Given a payload that is malformed, non-dict, oversized, or missing `quota`, then the endpoint
   answers without raising and publishes nothing.
5. Given a non-loopback or cross-site POST, then `_local_ok()` rejects it exactly as for
   `/api/notify`.
6. Given this provider, then `usage_fetch` does **not** rise and the modal does not appear.
7. Given `--diagnose`, then no usage receipt is required and no network call occurs.
8. Nothing is written to disk: Cargento's two written paths are unchanged.

## VERIFIED: the real payload (captured 2026-08-04)

A temporary forwarder was registered as the status-line command, `agy -p` was run once, and the
settings file was restored byte-identically afterwards. 13 payloads arrived, 10 carrying quota.
The `quota` object, verbatim:

```json
{
  "3p-5h":         {"remaining_fraction": 1, "reset_time": "2026-08-04T14:16:36Z", "reset_in_seconds": 17999},
  "3p-weekly":     {"remaining_fraction": 1, "reset_time": "2026-08-11T09:16:36Z", "reset_in_seconds": 604799},
  "gemini-5h":     {"remaining_fraction": 1, "reset_time": "2026-08-04T14:16:36Z", "reset_in_seconds": 17999},
  "gemini-weekly": {"remaining_fraction": 1, "reset_time": "2026-08-11T09:16:36Z", "reset_in_seconds": 604799}
}
```

Four things this settles that the documentation could not:

1. **The keys are self-describing.** They end in `-5h` and `-weekly`, so they map onto `fiveH` and
   `week` by name. The plan's earlier idea of inferring window length from `reset_in_seconds`, the
   way `codex._usage_window` classifies by `window_minutes`, is unnecessary. Match on the suffix and
   ignore anything that matches neither, so an unknown future bucket is dropped rather than guessed.
2. **There are two families, not one:** `gemini-*` and `3p-*` (third-party models). The entry
   contract has two slots and the payload offers two candidates per slot, which the vendor docs
   never mentioned. **Decided: publish the worst of each pair** (`fiveH` = the higher used percentage
   of `gemini-5h` and `3p-5h`, `week` likewise), because the band exists to answer "am I about to run
   out" and the binding constraint is the honest one to show. The cost is that the tile does not say
   which family the number belongs to.
3. **Every fraction was `1` on this capture**, meaning nothing consumed. The inversion
   (`pct_used = round((1 - remaining_fraction) * 100)`) therefore has **not** been exercised against
   a non-trivial value: `1` renders 0% whether the arithmetic is right or wrong. The unit tests must
   cover fractions like 0.4 and 0.0 explicitly, and a fixture of 1 proves nothing.
4. **Useful siblings exist**: `plan_tier` (here `"Google AI Ultra"`) and a `context_window` block
   with `used_percentage`. Neither is needed for this issue; noting them so they are not rediscovered.

Also present: `email`. The captured file is deliberately not committed, and the receipt handler must
never publish that field, which the shaping code enforces by building a fresh entry rather than
passing the payload through.

## Decisions taken (2026-08-04)

| Question | Decision |
|---|---|
| `--no-usage` scope | **Suppresses all usage, receipts included.** One flag, one mental model. Its help text must be widened, since it currently promises only to stop network fetching. |
| Receipt handler location | **`quota.py`**, widening its docstring. It already owns the usage cache and the read-back collectors use, so one cache keeps one owner. Its current claim to be "the whole of Cargento's outbound network surface" becomes untrue and must be rewritten. |
| Verify before parsing | **Done**, see above. |
| Bucket mapping | **Worst of each pair**, per the capture section. |

## Risks and open questions

- **Frequency.** The status line fires on every state change, so this spawns an interpreter per
  event. That is the CLI's design and what other tools do, but the endpoint should be cheap and the
  handler must not do work proportional to anything.
- Independent of PR #78: `remaining_fraction` yields a true percentage, so this needs gauges rather
  than the `used` field, and does not wait on that PR.

## Proposed approach

The capture is done and every design question is decided, so this is now one PR: the `/api/usage`
endpoint, the receipt handler in `quota.py`, `antigravity.usage()`, registry wiring with
`usage_is_fetch=False`, the staleness drop, `--no-usage` covering receipts, tests, and the
SECURITY.md / SKILL.md / design-doc updates. No new user-facing script: `notify_hook.py` is the
forwarder, invoked with a different URL.
