# Quota fetch security scope (DRC-4061)

This is the security contract for the usage quota fetch decided in DEC-1 (Linear DRC-4053),
written before the fetcher exists so the implementation PR is held to a published standard.
SECURITY.md describes shipped behaviour only, so the section lives here until the code lands.

The fetcher PR must do three things with this file: promote the section below into SECURITY.md
unchanged, apply the two intro amendments listed after it, and delete this file. The modal copy in
the visual design work (DRC-4062) quotes this section rather than paraphrasing it.

## The section, verbatim

The following lands in SECURITY.md between "Project reads (Spacedock stage strips)" and "Process
lifecycle". It contains no relative links on purpose, so it can move without rewriting.

---

## Usage quota reads (the quota fetcher)

One feature makes outbound network requests. When the usage feature is on, the server polls each
supported vendor's usage endpoint so the dashboard can show quota windows: how much of the 5-hour
and weekly limits is used and when they reset.

What is sent: the vendor's own OAuth access token, read from where the harness keeps it (the macOS
Keychain, or the harness's credential file on other platforms), carried in the request's
authorization header. Nothing else. No transcript content, no prompts, no paths, no project names,
no machine identifiers. What comes back is quota numbers: window utilization, reset times, and
per-limit entries. Session data never appears in either direction.

The endpoints, named exactly:

1. Anthropic (Claude Code, and any harness signed in with the same Claude subscription):
   `GET https://api.anthropic.com/api/oauth/usage` with the `anthropic-beta: oauth-2025-04-20`
   header.
2. Codex: no endpoint. Codex writes rate-limit snapshots into its own session files, and Cargento
   reads them from disk like every other store.

No other vendor is polled. A new vendor's endpoint must be named here before it ships. These
endpoints are not documented for third-party use: a vendor can change, break, or block them at any
time, and a failed poll means an empty tile, never a retry storm.

Token handling is read-only, one way, and never expands:

- The token is never refreshed. Refreshing from outside the harness can race the harness for its
  own session. An expired or rejected token switches that vendor's usage display off, marked with
  a pointer telling the user to sign in again in the harness itself.
- The token is never written to disk, never logged, and never served. `/api/data` and every other
  loopback endpoint must not carry it, in any form.
- Reading the token adds no write access anywhere. Harness stores stay read-only.

Consent and the off switch: the feature is on by default and disclosed before it acts. The first
time the dashboard opens with the feature available, a modal explains the token read and the
request above, and carries the switch that turns the feature off. The setting can be changed later
from the dashboard's configure panel, and `--no-usage` disables the feature for a run regardless
of the stored setting. With the feature off, Cargento's network surface is exactly the two
loopback-bound components described above, and nothing is fetched.

Polling posture: responses are cached, and at most one request per vendor is made every five
minutes. No polling happens while no dashboard page is connected. `--diagnose` never triggers a
fetch; its output stays a report of local paths only.

A violation of any boundary in this section is a security bug: a request carrying anything beyond
the token, a token reaching a log or a loopback response, a refresh attempt, an unlisted endpoint,
or a fetch with the feature off.

---

## Intro amendments that ride with the promotion

Two sentences elsewhere in SECURITY.md change in the same PR, and only these:

1. The Scope paragraph gains one sentence after "...and serves them over HTTP.": "When the usage
   feature is on, the server also makes one kind of outbound request, the quota poll described in
   Usage quota reads (the quota fetcher); it carries no session data."
2. Invariant 1 gains one clause at the end: "The quota poll is the single outbound exception, and
   it carries a vendor token out and quota numbers back, nothing else."

## What else the fetcher PR touches

- `SKILL.md` gains a `--no-usage` row in the flag table.
- The first-run modal ships in the same PR (DRC-4053 guardrail 3), with copy quoting this section.
- The response fields Cargento actually reads (window utilization, reset times, `limits[]`
  entries) are documented in the design doc that accompanies the implementation, not here; this
  section fixes what may travel, not the parse.
