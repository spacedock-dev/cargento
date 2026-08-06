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

That table was read from a live store on 2026-08-06 rather than taken from the CLI's documentation,
which does not describe it. Two facts from that read are worth keeping: it carries a `session_id`,
and those values matched the `session-state/<uuid>` directory names the Copilot collector already
publishes as a session id. So a per-session slice of AIU spend is available from the same rows the
harness figure is summed from, with no second identity to reconcile, which is what any future
per-session cost display would need and is the reason not to key one on anything else.

The entitlement is the part that does not exist locally. GitHub keeps it server-side and the CLI
never writes it down, which was confirmed by searching every file under `~/.copilot`: `entitlement`
and `allowance` appear in none of them, though both are strings inside the CLI binary. So there is a
numerator and no denominator, and no honest percentage can be derived.

Hence `used`: a preformatted figure, rendered as a labelled row with no track and no percent sign,
because a bar implies a fraction of something. Three consequences worth stating:

- **It is always shown when present.** The optional stats, the `today` and `cost` extras, and the
  page-derived `burn` projection of Q-9, default to off in `usageCfg`, and a consumption-only entry
  whose single figure sat behind `configure` rendered as a harness name and a timestamp with no
  number, which reads as a broken row rather than a hidden setting. A contract test executes the page
  script and fails if the figure stops surviving the default config.
- **It is windowed on each row's own timestamp**, so the number answers "in the last
  `window_hours`" rather than "since however much session history happens to be retained", which
  would drift as old session directories accumulate or get cleaned.
- **Premium requests are the wrong target.** The survey behind DEC-1 described per-session
  premium-request estimates, but on an AI-Credits account `totalPremiumRequests` reads 0 while real
  spend flows through the AIU fields. The legacy counter is deliberately not read.

The alternative shapes considered were reusing the `today` extra and force-showing it for
window-less harnesses, which makes `usageCfg`'s meaning depend on the payload, and deriving a rate
from the AIU rows so that the bare figure had some context, which is a heuristic over however few
rows the window happens to hold. A first-class field says exactly what it is and needs neither.

That second rejection is about **this** figure and nothing else, and being exact about it matters now
that Q-9 ships a derived rate. A projection needs three things: a level, a slope, and a ceiling to
run into. Copilot's spend has the first two and no third, so a rate attached to it would be a number
travelling towards nothing, the same missing denominator this whole section is about, dressed up as
a forecast. Q-9 fits its slope on a published percentage and projects when that percentage reaches
100, and it reads no `used` figure at all.

## Q-2: The response fields Cargento reads

From `GET https://api.anthropic.com/api/oauth/usage` (with `anthropic-beta: oauth-2025-04-20`), two
fields per window are consumed. The shapes below are measured rather than inferred: one live
response was recorded on 2026-08-06 from macOS, on a subscription account with extra-usage credits
disabled:
[`captures/claude/usage-endpoint-macos.jsonl`](captures/claude/usage-endpoint-macos.jsonl).

| Field | Used as |
|---|---|
| `five_hour.utilization`, `seven_day.utilization` | The window percentage, rounded and clamped to 0 to 100. Measured as a float already on a 0-to-100 percent scale, so the round is a rounding and not a conversion. |
| `five_hour.resets_at`, `seven_day.resets_at` | The reset stamp. Both shapes the endpoint has sent are accepted: epoch seconds, or an ISO-8601 string, which is what the capture carries. |
| `limits[]` | Documented here, not read. `_fetch_windows` shapes `five_hour` and `seven_day` and drops the rest of the body, so the per-model rows are ignored rather than parsed into something unpublished. Their shape is written out below, so the roadmap item that renders them (A3 on the Visibility board) starts from a measurement. |

Anything else in the response is ignored. The endpoint is undocumented for third parties, so the
parse is defensive throughout: a malformed body or a response with no recognizable window caches
an empty entry list and a one-word diagnostic, never an error tile.

**The percent scale is a capture-only finding.** No unit test can settle it, because a fixture
picks its own input scale: a suite written against a 0-to-1 fraction and one written against
0-to-100 both pass, and each proves only that the code agrees with its own fixture. The live
response is what fixes it, and it makes `_shape_window`'s round-and-clamp correct as written. Under
the other reading that same line publishes 1% for a window at 90%, and a band that reads
almost-empty while the allowance is nearly gone is the one failure this section exists to prevent.

**`limits[]` is the live per-model surface, and its shape is now measured rather than described.**
The capture records three elements whose key sets are identical: `group`, `is_active`, `kind`,
`percent`, `resets_at`, `scope`, `severity`. `percent` is an integer on the same 0-to-100 scale as
`utilization`. `kind` discriminates the rows as `session`, `weekly_all` and `weekly_scoped`; `group`
collapses those three into two, `session` and `weekly`. So `kind` can key a renderer and `group`
cannot: keying on `group` merges `weekly_all` with `weekly_scoped`, which are precisely the two rows
A3 has to label differently, and only `weekly_scoped` arrives without a `resets_at`. `severity` is
a vendor-computed enum of which only `normal` was observed, which makes it something to display
rather than something to branch on.

Two constraints fall out, and both belong to whoever renders these rather than to the parse:

- **A `weekly_scoped` element may arrive with no `resets_at`.** The scoped element in the capture is
  the per-model one: it names its model at `scope.model.display_name`, `scope.model.id` was null, so
  the display name is the only label available, and it carried a percentage with no countdown at
  all. The contract in Q-1 already allows a window with `pct` and no `resetAt`, and the page falls
  back to an em dash when neither the instant nor the words arrive, so nothing breaks. The decision
  left open is whether an em dash is the right thing to print for a window that genuinely has no
  reset, which is a choice to make deliberately rather than to inherit.
- **`seven_day_opus` and `seven_day_sonnet` are dead names on a subscription plan.** Both exist as
  top-level keys and both were null, as were three similarly named siblings. Per-model work written
  against those field names reads nothing and reports nothing, with no error to explain the silence.
  `limits[]` is where the per-model figures actually are.

The capture also pins two fields the parse still ignores on purpose. Each window carries
`limit_dollars`, `remaining_dollars` and `used_dollars`, all null on a subscription plan, so a
Claude `used` figure cannot be read from them. And `spend.used` is a minor-unit object
(`amount_minor`, `currency`, `exponent`) rather than a number: the Q-8 cents trap in self-describing
form, where the divisor is stated by the payload instead of having to be discovered. What the
exponent's value is on any given account is not written down here, because the capture records no
values at all, only that the field is there and integral. Whoever reads that object takes the
divisor from the object, which is the entire point of its being self-describing.

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

## Q-9: The burn projection is derived in the page, and states quantities rather than a verdict

"How fast is this window filling, and when does it fill?" needs a derivative, and nothing in the
payload carries one: every quota figure in Q-1 is a level. So the series is built in the page, one
bounded buffer per harness and window, using the same ring-buffer idiom the token sparkline already
uses rather than a second one. The constants and the code live in `web/usage.js` under "burn
projection"; what follows is why it is shaped this way, which is this document's half of it.

**What the row publishes is quantities, and nothing composed out of them.** A resolved reading
prints the fitted rate, the ± those samples support, and the interval in which the window reaches
100%. It does not say whether the reset gets there first. That was answered here once and the answer
was wrong five times over, so the comparison is left to the reader, who has this window's own reset
countdown (Q-1) on the same row: two measured figures side by side and no product of them. The
record is "The burn row's race verdict, built and then deleted" among the rejected alternatives, and
it is the part of this section to read before putting the verdict back. `burnRead` does not read
`resetAt` at all, the reset instant is the buffer's business, for the reason in the restart rule
below, and reading it a third time in the fit is what made the verdict possible.

**A persisted series was considered and deliberately not built.** Storing the samples would mean a
server-side write path and a cache file, for a signal whose whole value is the last hour. What that
buys is a projection that survives a reload, and the price is four costs that a page-local buffer
pays instead. Each one is *rendered* rather than assumed away, which is what makes the trade
acceptable: none of the four can turn into a confident reading of evidence that is not there.

- **Warm-up.** There is no history when a tab opens, and samples accrue only while a tab is open
  with usage on, because the fetch is driven by `/api/data` requests carrying the page's consent
  (Q-3), and in the calm view only while the band itself is open, since a collapsed band does not
  render and so does not sample. So the signal is coldest at the exact moment somebody opens the
  dashboard to ask "can I start this now", which is why that moment gets a sentence saying so. Until
  three samples span ten minutes the row reads "warming up" with its own count and prints no figure
  at all. Unknown and measured are different answers and only one of them is available at load. At
  the server's five-minute floor that puts the first projection about ten minutes after the tab
  opens. The count or the span can be the requirement still short, `asOf` advances as fast as its
  producer stamps it, not at the fetch floor, so the row names whichever one it is rather than
  printing "9 of 3".
- **Reload loss.** The buffer dies with the page, and a reloaded tab is indistinguishable from a
  fresh one. That is exactly why a fresh one has to read as unmeasured: the alternative is a
  projection fitted to a just-emptied buffer.
- **Quantisation.** The published `pct` is an integer and the fetch is floored at 300 seconds
  (`usage_poll_floor_sec`), so the difference of two samples carries up to a whole point of pure
  rounding. A measured rise of one point could be a true rise of anything from just above zero to
  just under two, 100% relative error, and across a ten-minute span that is a rate somewhere
  between 0 and 12%/h. So a rise this fit's own error bound cannot separate from the rounding is not
  published as a rate at all, only as a ceiling, and every figure that does print carries the bound
  it was fitted with. That bound is not a constant, and the error model below is where it, and
  everything keyed to it, is written down.
- **Staleness.** `asOf` is the moment the percentage was true, and nothing obliges it to advance. A
  stored Antigravity receipt keeps being served with a frozen `asOf` for up to `window_hours` after
  its harness stops (Q-7), and the buffer ignores a repeat of an `asOf` it already holds, so the
  samples stop arriving while the page goes on rendering. Left unbounded that republishes one fit
  forever: byte-identical burn rows hours apart, beside a countdown the reader can see ticking. So
  the newest sample's age is bounded against the viewer's clock at ten minutes (`BURN_STALE_SEC`, which is
  two arrival intervals at the 300-second fetch floor, because one missed refresh is jitter and two
  in a row is a feed that has stopped), and a frozen feed reads as unmeasured again, with the age on
  the row so the reader can tell a harness that went quiet ten minutes ago from one that stopped
  this morning. The bound is tested ahead of the count and the span, since it outranks them: a
  buffer holding one three-hour-old reading is not filling up slowly, it has stopped being fed, and
  counting it towards a threshold nothing is going to cross would print the wrong unknown.

  A window that reports no reset time at all used to be the fourth cost here, and it is not a cost
  any more. The capture in Q-2 carries a `weekly_scoped` limit with no `resets_at`, and
  `_shape_window` omits `resetAt` when the vendor sends none; with the race gone there is nothing in
  the reading that wanted the instant, so such a window now loses nothing from its projection rather
  than degrading to an unknown verdict
  (`test_a_window_with_no_reset_time_loses_nothing_from_the_projection`).

**Every reading names what kind of answer it is.** Nothing returns a bare number, because the caller
must not be able to mistake "we cannot tell" for one. There are five states and each has its own
words on the row: a window already at 100% ("window spent"), a feed whose newest reading is too old
to fit ("stale", with the age), a buffer still short of the count or the span ("warming up", with
whichever is short), a rise this span cannot resolve into a rate ("under 3%/h"), and a resolved
projection, which prints the rate then both ends of the wall interval separated by an en dash (the
exact literal is pinned by `test_a_projected_wall_is_published_as_the_interval_its_band_spans` and
shown in the skill body; it is not reproduced here because these docs hold no dashes in prose and a
verbatim copy would read as drift). They are tested in that order, and the first two placements
are decisions rather than accidents of code: a full window outranks even a frozen feed, because "the
wall is here" must never be buried under a note about staleness, and staleness outranks the count
and the span for the reason given above. Colour now reaches exactly one of them. A spent window
keeps the alert tone, because it is a level the payload published rather than anything inferred
here; every projection is dim however fast it reads, since a tone on a projection is the other half
of the verdict, a claim about what the number means for the reader, and the readings that used to
raise one are the readings the reviews found wrong. Both printed figures are marked as what they
are, `~` for an estimate and `under` for a ceiling, because "7.43%/h" off a handful of integer
samples would dress a few readings up as a measurement.

**The error model is this fit's own, and it moves with the sample count.** `burnFitError` takes the
worst thing ±0.5 of integer rounding can do to this particular least-squares slope, from the weights
of the samples actually held. Read as an error on the fitted rise that is one whole point at three
samples, 1.2 at four, and climbing towards 1.5 as the buffer fills, more samples over the same span
widen it rather than tightening it, so no constant can stand in for it. A dozen readings across 55
minutes carry ±1.5%/h where the three-sample expression would have printed ±1.1%/h and sold the
estimate as a third sharper than the samples support
(`test_the_burn_error_band_widens_as_the_buffer_fills` pins both figures, and the earlier drafts of
this section that stated the three-sample constant are how that would come back). Three things are
keyed to that bound rather than written down as numbers:

- **The gate.** A slope must clear twice the bound (`BURN_RESOLUTION_FACTOR`) before it prints as a
  rate, which is two points of rise at three samples and about 2.8 by twelve. Three samples is the
  warm-up minimum and not the ordinary case, the trailing hour of a tab left open holds about a
  dozen readings at the 300-second floor, so a fixed two-point gate there would publish as a rate a
  rise those samples cannot resolve.
- **The ceiling, for a rise under the gate.** The fitted slope plus the whole bound, never printed
  tighter than the gate it failed to clear, since a row whose claim is "this span cannot resolve a
  rise this small" cannot also report having measured a smaller one. It supports exactly one
  instant, the earliest the window could be full, and that is a bound in one direction only: the
  same samples are equally consistent with a slope of zero, which never fills at all. So the instant
  goes in the tooltip and not on the row, where a figure beside "under 3%/h" would read as a
  prediction with the half that says "possibly going nowhere" missing.
- **The wall, published as the interval its band spans.** Two sources of ± reach it. The slope's
  band gives the early end its fastest consistent slope and the late end its slowest, and the
  published level carries its own half point, an 89 is anything in 88.5 to 89.5, so the early end
  divides the least headroom consistent with that level and the late end the most. The half point is
  worth the arithmetic because at a slow slope it is minutes rather than seconds: at 3%/h it is 600
  seconds, which is why the early end is anchored at `level + 0.5` and not at the integer the row
  prints. A single "wall in 57m" was the other candidate and is the verdict's defect one layer out:
  it is exactly the input a reader needs for the comparison this row has stopped making, and handed
  over as a point it invites that comparison at a precision the fit has not got: at 16.8%/h ±4.8 the
  wall is anywhere from 43m to 1h 22m out, and "57m" against a reset 50m away reads as fine on
  evidence that says possibly not. The pessimistic end alone is the mirror of that failure, since a
  row that only ever names the earliest possible wall overstates every window it describes, and a
  signal that cries wolf is read as decoration inside a week. The interval states what is known and
  how well at once, which is the argument for keeping these numbers while dropping the verdict over
  them. Both ends collapse to one figure when they round the same, so a window about to fill does
  not read as vague.

**Samples are stamped with the payload's own `asOf`, not the viewer's clock.** `asOf` is the moment
the percentage was true, and a cached fetch is older than the poll that carried it; stamping at
receipt would compress a five-minute-old figure onto "now" and steepen the slope. The fit therefore
lives entirely in payload time, and the viewer's clock is read for exactly two things, both of them
facts about now rather than about the fit: how old the newest sample is (the staleness bound above),
and how long the intervals on screen have left, which is the clock the reset countdown in Q-1 reads.

**Two independent signs of a rolled window empty the buffer, and neither one is redundant.** A fall
in the percentage is the visible sign: the samples before a fall describe a window that no longer
exists, and a slope fitted across that discontinuity reads as a steep decline into a wall that is
never coming. A fall alone only catches a roll whose new level sits *below* the old one, though, and
a window that rolls and then climbs straight past where the last one stood never falls, the buffer
would keep both sides and fit one slope across two separate allowances, understating the new
window's rate and pushing its wall out. So every sample also carries the reset instant it was taken
under, and a change in that instant empties the buffer too. Producers build `resetAt` from the
vendor's own absolute reset time (`sessions.reset_fields`), so it holds still for the life of a
window and a change in it really is a new allowance rather than sampling noise. Either restart
returns the row to warming up, which is the only honest reading of a buffer holding one sample. Both
triggers are pinned separately
(`test_the_burn_series_ignores_a_replayed_reading_and_restarts_on_a_roll` and
`test_the_burn_series_restarts_when_the_reset_instant_moves`), because a draft that named only the
visible one is what left the second case unhandled.

**It is rendered under each window's own row, and it defaults to off.** A 5-hour window and a weekly
window fill at different rates and reset at different times, so one projection per harness would
have to pick one of them silently. Off by default is a decision rather than an omission: the series
starts empty every time a tab opens, so a default-on row would read "warming up" under every window
on first load and teach the reader that the band is half-built, whereas an opt-in row is asked for
by someone who has read what it measures. The buffers fill whether or not the stat is shown, so
turning it on is instant rather than the start of another ten-minute wait.

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

The per-model rows have no rendering yet. Part of the old argument was that their shape was unknown,
and that half has expired: the capture in Q-2 measures it. What remains is that publishing them
would freeze a payload shape ahead of the renderer that has to label them, and the scoped row's
missing `resets_at` is exactly the kind of thing a renderer should decide about rather than inherit
from whatever the first parse happened to emit. So the body is read for its two named windows only
and the measured shape is documented in Q-2.

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

### The burn row's race verdict, built and then deleted (2026-08-06)

Q-9's row used to end in a verdict on the race: `resets first` where the projection put the reset
ahead of the wall, `may fill first` where the samples could not rule filling out, `wall in 40m`
where they put the wall first, and `reset unknown` where there was nothing to race against. It was
the reading the row was built to give, a level and a slope are only interesting if they answer "can
I start this now", and it is gone. What survives is the arithmetic under it.

Three review rounds found five false-green defects in that verdict: a row telling the reader the
window is safe when its own evidence does not say so. All five were inside the verdict. None was in
the quantities. The last two were deleted rather than patched, because the deletion is the fix for
both:

- **The wall was anchored at the published integer** rather than at `level + 0.5`. `pct` is rounded,
  so a window printing 99 is anywhere up to 99.5 and the projection was handed half a point of
  headroom that may not exist. At a low slope that half point is most of the answer: at 3%/h it is
  600 seconds, and 600 seconds of phantom headroom is the margin `resets first` was being decided
  on. The half point itself was not the mistake and did not go away with the verdict: the wall
  interval Q-9 ships now takes it on its early end.
- **A row could read `resets first` while its own tooltip said the window reaches 100%.** The
  headline and the sentence under it were derived on different footings, and the reassuring one was
  the one in the headline.

The quantities stayed because they were never what failed. The fitted slope and its error band were
put through a 4,000-case randomised sweep across the levels, slopes, sample counts and reset
distances the row actually meets, and it returned no false-safe result. So the arithmetic held and
the last step did not, and that asymmetry is structural rather than a run of bad luck. A verdict has
to pick a side. The side that needs care is the pessimistic one, and every slip on the way to it (an
anchor half a point out, a bound read at the fit instead of at the top of its band, a stale
instant treated as a deadline, a branch reached before its guard) comes out as `resets first`. A
wrong number looks wrong. A wrong verdict looks like good news.

So the row states what was measured: the rate, the uncertainty on it, and the interval in which the
window is projected to fill. The reader compares that against the reset countdown Q-1 already puts
on the same row, and Cargento gives up the one bit it could not compute reliably while keeping every
figure the reader needs to compute it.

This is the judgement that killed A9 on the Visibility board, "a single safe-to-start light": a
verdict composed over uncertain evidence fails toward confident green, and a false green is worse
than no light. It is written down here because reintroducing it will look like an improvement rather
than a regression. A wall in 40 minutes printed beside a reset in 50 is asking to be collapsed into
one word, and that word is the defect.
