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
 models: [{label, pct, reset, resetAt}],    // sub-limits of the weekly one, one row per model
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

The pair is optional as well as paired, and a row can carry a percentage with no reset at all. That
is not hypothetical: the scoped element in the capture behind Q-2 published a per-model percentage
and no `resets_at`, so `_shape_window` and `_scoped_limit` both omit the pair rather than defaulting
it. Such a row prints an em dash where the countdown goes and says "resets at an unknown time" on the
hover. Both halves are deliberate. A blank column reads as a row still loading, and borrowing the
weekly countdown would put a figure on the row that this limit never published.

Every window slot is optional, and a harness fills only the ones it genuinely has. That is the
whole reason `month` exists rather than Cursor borrowing `week`: the slot names are what the page
labels the bar, so a monthly cycle rendered as "wk" would put a wrong label on a correct number.

`models` is the one quota field that is not a named slot, and it is a list for the same reason the
slots are slots. A per-model sub-limit is labelled by the vendor and arrives in a list of unknown
length, so no slot can hold it, and minting `weekOpus` and `weekSonnet` beside the others would put
this repository in the business of tracking another company's model line-up. Each row carries a
`label`, a `pct` on the same 0-to-100 scale as every bar in the band, and the same optional reset
pair. The label is the vendor's own display name, bounded to 40 characters on the way out and
guaranteed to differ from every other label in the list, because a per-model row has no other
identity to be told apart by. The list is absent rather than empty when there is nothing to say,
exactly like the window slots, and it is capped at eight rows. Only Claude fills it today, its rows
are sub-limits of `week` rather than a fourth horizon, and the page draws them directly under the
weekly bar they subdivide. Q-2 owns which elements of the response become one.

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
harness figure is summed from, with no second identity to reconcile.

That slice now ships, as a `consumption` string on every session row, and the design of it is one
question: what a row means when it has no figure. One reducer answers for both surfaces.
`_read_ledger` returns nothing at all unless it could read the window to its end, so a store that is
absent, unreadable, drifted, or longer than the row cap without the read reaching past the window's
far edge takes every session figure with it and the harness tile with them. Below that, a single row
that cannot be accounted for withdraws only what it would have fed: the tile's total always, because
a sum with an unknown addend is not a sum, and the figure of the session it names, if it names one.
On top of that, three readings and three different renderings:

- A figure is the session's own rows inside `window_hours`, formatted by the same function the
  harness tile uses, so one quantity cannot render two ways. It carries its unit as text
  ("6.43 AIU") rather than as a bare number, because AIU, tokens and dollars are three different
  quantities and a naked `consumption: 6.43` invites one axis through all of them.
- "0.00 AIU" is a measured zero: the window was read to its end, it covers this session, and it holds
  no row against it. It is shown unadorned, the same way the rate meter prints a real 0. Suppressing
  it is the one move that would make it indistinguishable from a harness that keeps no ledger, which
  is the distinction the extra bookkeeping exists for.
- None is no ledger for this harness at all, or a row naming this session that could not be accounted
  for, which knows there was spend and not how much. The page draws nothing for it: no label, no
  dash. Absence takes the "used" word away with it, so a metadata line with no figure claims nothing
  about spend, in the way a Claude row with no `via` claims nothing about whose quota it is on.

Two consequences that are easy to get backwards. A zero is a claim about coverage, so it is only
available for a session the window covers: an idle session older than the window is outside it
entirely, and one dragged back in by `?all=1` gets None rather than a zero that would report a
week of work as free. A session the window does not cover that *does* appear in the ledger keeps its
figure and gets the window named in the visible words ("used 2.10 AIU in the last 24h"), because that
number is the window's share and not the session's life, and the tooltip is the wrong place to keep
the difference. And the per-session figures need not add up to the tile's total: a ledger row naming
no session is real consumption, so it counts towards the harness figure and towards nobody's row. The
gap is honest, and the alternative, attributing such a row to some session, is worse than the gap.

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
fields per window are consumed. The shapes below are measured rather than inferred: two live
responses a day apart were recorded on 2026-08-06 and 2026-08-07 from macOS, on a subscription
account with extra-usage credits disabled, the second to test which fields hold still:
[`captures/claude/usage-endpoint-macos.jsonl`](captures/claude/usage-endpoint-macos.jsonl).

| Field | Used as |
|---|---|
| `five_hour.utilization`, `seven_day.utilization` | The window percentage, rounded and clamped to 0 to 100. Measured as a float already on a 0-to-100 percent scale, so the round is a rounding and not a conversion. |
| `five_hour.resets_at`, `seven_day.resets_at` | The reset stamp. Both shapes the endpoint has sent are accepted: epoch seconds, or an ISO-8601 string, which is what the capture carries. |
| `limits[].kind` | The discriminator. Only `weekly_scoped` elements become rows; `session` and `weekly_all` restate `five_hour` and `seven_day`, which stay canonical for those two windows. `group` is never read; see below for why it cannot be. |
| `limits[].scope.model.display_name` | The model row's label, bounded to 40 characters and required. `scope.model.id` was null in the capture, so the display name is the only label there is, and an element without a usable one is dropped rather than published unnamed. |
| `limits[].percent` | The model row's percentage. Measured as an *integer* on the same 0-to-100 scale as `utilization`, which is a float: the two go through one `_percent` reader so the rounding cannot diverge, but neither field is read by the other's name. |
| `limits[].resets_at` | The model row's reset stamp, when there is one. The scoped element in the capture carried none at all, so a per-model row can be a percentage with no countdown; missing stays missing. |
| `limits[].is_active`, `limits[].severity` | Present in the capture, deliberately unread. Neither has established semantics. `is_active` moves: the two recorded readings a day apart disagree about which element carries it, and a third observation during development showed a third arrangement, so it describes something that varies rather than the kind of limit. Only `severity: normal` has ever been observed, so publishing either would hand the page a field it cannot honestly render. |

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
the band has to label differently, and only `weekly_scoped` arrives without a `resets_at`.
`severity` is a vendor-computed enum of which only `normal` was observed, which makes it something
to display rather than something to branch on.

Two constraints fall out. The parse now honours the first; the second is a warning about where the
per-model figures are not:

- **A `weekly_scoped` element may arrive with no `resets_at`.** The scoped element in the capture is
  the per-model one: it names its model at `scope.model.display_name`, `scope.model.id` was null, so
  the display name is the only label available, and it carried a percentage with no countdown at
  all. The contract in Q-1 allows exactly that, and `_scoped_limit` omits the pair rather than
  defaulting it. What the page prints for such a row was decided rather than inherited: an em dash
  in the countdown column, with "resets at an unknown time" on the hover, so the row says it has no
  reset instead of implying one. The two alternatives were a blank column, which reads as a row
  still loading, and the weekly countdown borrowed down onto the model rows, which would print a
  figure this limit never published beside a percentage it did.
- **`seven_day_opus` and `seven_day_sonnet` are dead names on a subscription plan.** Both exist as
  top-level keys and both were null, as were three similarly named siblings. Per-model work written
  against those field names reads nothing and reports nothing, with no error to explain the silence.
  `limits[]` is where the per-model figures actually are.

**Publishing these rows was rejected once, and the reversal is recorded here rather than left in the
rejected list (2026-08-07).** The old entry was called "Publishing `limits[]` now" and it made two
arguments. The first was that the shape was unknown, and that half did not survive contact with a
response: it had been written from field names read around the endpoint rather than from anything
this repository had received, and the capture settled every one of them, including the two no amount
of reasoning would have produced. `percent` is an integer where `utilization` is a float, so one
reader for both is a decision rather than a tidy-up, and the scoped element carried no `resets_at` at
all. The second argument was that publishing would freeze a payload shape ahead of the renderer that
has to label the rows. That one expired differently: the parse and the renderer shipped in the same
change, so the shape was settled with its rendering rather than in front of it, and the missing reset
was the first thing decided rather than the thing inherited (see the bullet above). The entry is not
kept under "Rejected alternatives worth keeping rejected", because every other entry there describes
something Cargento does not do, and a heading that promises a standing rejection over an entry the
code has overtaken misleads any reader who skims the headings. What is worth carrying forward is the
sequence: prose about a payload was wrong in a way tests could not catch, and one recorded response
both settled it and changed the decision.

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

**A per-model row is not projected, and says so rather than sitting blank.** `BURN_SLOTS` is the
three window slots and nothing else, so nothing under `models` (Q-1) is ever sampled and no buffer is
keyed on a model. While the projection is on, those rows read "not projected" with the reason on the
hover, which is the sixth answer this block can give and the only one that is a property of the row
rather than of its samples. Printing something is the point: a model row sitting silent beneath a
weekly row that reads "~4%/h" is read as a limit that is not filling, and an absence that reads as
good news is the failure the rest of this section was rebuilt around. Two reasons nothing is fitted,
and both are about identity rather than arithmetic. The row's only identity is its label, and the
label is stable only while the vendor's set of names is: a second model whose name collides with the
first relabels both (`_distinct_labels`), so a key built from it can change under a series that is
still running. And the scoped element in the capture carried no reset instant, which is exactly the
input the restart rule above needs, so a per-model row is left with the fall in the percentage as its
only sign of a roll, and a limit that rolls and then climbs straight past where the old one stood
never falls. A fit spanning two allowances reads slower than the truth and pushes its wall out, which
is the reassuring direction, on a signal that has been observed once: one scoped row, on one account,
at one moment. The weekly window those rows subdivide has a projection of its own, immediately above
them, and that is where a reader gets a rate.

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

## Q-10: A capacity comparison is between authorities, inside one horizon, with its holes on screen

Board item A4, "capacity across subscriptions and harnesses" (Linear DRC-4007), asks for one
reading: Claude at 95%, Codex at 10%, so move the work to Codex and carry on. None of that
comparison exists today, and the part that is missing is not the integrations. Five of the ten
harness rows already publish quota into the band above. What has never been agreed is what those
figures mean placed side by side, and a comparison built without settling that does not skip the
question, it answers it silently in whatever way the first renderer happens to. So this section
settles it before anything is built: what the unit of comparison is, which authorities may enter
one, what Cargento refuses to compute, and what the surface says on a machine where it can compare
nothing. DEC-1's consent posture is unchanged by any of it.

### What each authority publishes, and when it is there

Six authorities are named in Cargento today, five of them with a reader, and the table below is the
whole of question one. It is not a closed list of what a user can spend. Pi supports twenty-odd
providers, most of them direct API keys with no Cargento presence at all, and a Gemini CLI session
on an enterprise Code Assist or API-key route is Google again, with nothing saying its allowance is
the one Antigravity's receipt reports. Those are absent from the table because nothing reads them,
which is itself one of the states question three has to render rather than hide.

| Authority | Harness rows spending it | What Cargento reads | There when |
|---|---|---|---|
| Anthropic | Claude Code, and any harness signed in to the same subscription | percent of a 5 hour and a 7 day rolling window (Q-2) | the store exists and the disclosure has been answered |
| OpenAI | Codex | percent per window, classified by the window's own length (Q-1) | Codex left a snapshot inside `window_hours` |
| Google | Antigravity | percent per named bucket, the worse of two model families (Q-7) | the user pointed the status line at `/api/usage` and the harness ran inside `window_hours` |
| Cursor | Cursor CLI | spend in cents against a monthly billing cycle, macOS only (Q-8) | the Keychain token reads and the disclosure has been answered |
| GitHub | Copilot CLI | AI Units consumed, with the entitlement nowhere on the machine (Q-6) | a usage row landed inside `window_hours` |
| Factory | Droid | nothing | never, so far as anything here knows |

Two rows in that table are absences of different kinds, and a comparison that treats them alike gets
question one wrong. GitHub publishes a numerator and no denominator, which is a measured fact:
`entitlement` and `allowance` appear in no file under `~/.copilot`, and Q-6 is the record of
looking. Factory publishes nothing that anyone here has looked for. Droid is not installed on the
machine this work was done against, so its store has never been read, and "Factory keeps no local
quota" is not a finding but the absence of one. Every field this document treats as measured
(Copilot's `total_nano_aiu`, Cursor's cents, Anthropic's `limits[]`) came from a live store or a
live response. The Antigravity attempt below is the reason to hold even a searched-for absence
loosely: its local forensics were thorough, and the number it concluded was out of reach ships
today, arriving by the pushed path in Q-7 instead. An absence found by looking can still be
overturned by a route nobody enumerated, so an absence nobody has looked for is worth nothing at
all, and Factory stays unmeasured in writing rather than written down as empty.

Anthropic's row also says something the other rows do not, and it decides the unit of comparison.
That percentage is the account's, not Claude Code's: SECURITY.md names the authority as "Claude
Code, and any harness signed in with the same Claude subscription", and `codex.usage` says the same
thing about its own snapshot, that the CLI reports account quota rather than per-session quota. So
per-harness headroom is not a quantity that exists anywhere. What exists is one allowance per
authority, which several harnesses may already be drawing on. The row of a comparison is therefore
the authority, and a harness appears as a route to one. A4's title says "across subscriptions and
harnesses"; the subscription is the thing being compared and the harness is how the reader reaches
it.

### Which authorities may enter, and what will not be computed

An authority enters a headroom comparison only when it publishes a fraction of a limit that
authority states itself. That admits Anthropic, OpenAI, Google and Cursor. It excludes GitHub, whose
figure is consumption with nothing to be consumption of, and Factory, which has not been read.
Copilot's `used` keeps its place on the band, where it is a measured quantity that names its own
unit and claims nothing further. Q-6's argument for that does not weaken with distance: an
entitlement inferred from observed spend, or from a plan name, would print as a percentage no reader
could tell apart from the four that were measured.

Percentages are compared inside one horizon and never across it. A percentage is a fraction of an
allowance over a period, and the period is half the quantity: 95% of a 5 hour window refills within
five hours, and 95% of a billing cycle may be three weeks from refilling. Both read "95% used" and
they answer different questions. The horizon classes are the payload's own slots from Q-1, `fiveH`,
`week` and `month`, so the class is read off the contract rather than being a second taxonomy that
can drift from it. A comparison names its class, and a class holding one authority is not published
as a comparison at all, because ranking a set of one manufactures a winner. Cursor has only a
`month`, so today it is comparable against nothing, and that is a true statement about Cursor rather
than a gap in the design.

Nothing is converted to make two rows comparable. No AI Units into a percentage, no dollars into a
percentage, no per-plan weighting that puts five subscriptions on one axis. Each of those needs a
number no authority publishes, an entitlement or a price or a plan equivalence, so it would be
invented here, and an invented percentage renders identically to a measured one. This is the rule
that already keeps Q-6's figure out of the burn projection, applied one layer out.

Cargento also does not name the harness to move to. It publishes each authority's percentage, the
horizon that percentage is over, and the authorities it could not read, and the reader picks. Two
reasons, and the second is the one that is easy to lose. A destination depends on facts Cargento
does not hold: whether the task needs a particular model, which tools and servers are wired into
that harness, whether the repository is even checked out where it runs. And a recommendation is a
verdict composed over inputs that can be missing, which is what killed A9 on the Visibility board
and what the burn row's deleted verdict is a worked example of. The failure mode is identical. A
wrong percentage looks wrong; "you have room on Codex" looks like good news.

### The authority most likely to be missing is the one being migrated to

This is the finding that shapes what the surface has to say, and it falls out of the table above
rather than out of any policy. Anthropic and Cursor are fetched, so they report while their harness
sits idle. OpenAI, Google and GitHub are read from what their harness wrote or pushed, and all three
drop out once the newest reading is older than `window_hours`, 24 hours by default: `codex.usage`
tests the snapshot's freshness, `quota.receipt_entries` tests the receipt's, and Copilot's sum only
counts rows inside the window. Usage is also read only for a discovered harness, so a harness that
has never run publishes nothing at all.

Put that beside A4's example. The harness at 95% is the one being used, which is the one that
certainly reports. The harness at 10% is the one not being used, which is the one whose figure most
easily is not there. So the case the feature exists for is the case where one side of the comparison
is structurally absent, and the naive rendering of an absent Codex row is that Codex is untouched,
which happens to be the answer the example wants and is not an answer the evidence gives.

Hence the rule that a comparison surface publishes the roster rather than the rows that answered.
Every authority in the table appears, and one with no percentage says which kind of nothing it has:
awaiting the disclosure, nothing inside the window, off this platform, no integration measured.
Three legible states rather than two, per authority. Absence being invisible is tolerable in the
band that ships today, where each tile is a claim about one harness and a missing tile claims
nothing; it is not tolerable in a comparison, which is a claim about a set, and where dropping the
unreadable rows leaves a picture that looks complete.

One of those states is already in the payload, which is why this is a discipline the band has rather
than a new one. Q-5 splits a rejected token, published as `state: "expired"` and rendered as a
pointer at signing in again, from an unreadable one, which keeps the harness out of the band
entirely, because "sign in again" is wrong advice when the harness session may be fine. That is the
same distinction between two kinds of nothing, made once per tile. A comparison owes it across the
whole roster at once.

### A passthrough harness has no capacity of its own, and that is a prerequisite

Three harness rows spend somebody else's allowance. DEC-1 records it in its own cost note: Goose,
OpenCode and Pi borrow their provider's quota, so one Anthropic fetch answers for every harness on
that subscription. Counting such a row as its own authority double counts one allowance, and the
error runs in the dangerous direction. A reader with one Anthropic subscription behind three harness
rows would be shown three hatches and have one.

What exists today is one third of the attribution needed. `base_session` declares `provider` and
`model` on every row at `None`, so the payload's shape does not depend on which collector filled it,
and only Pi populates them, because Pi is the one harness where the answer is not already the
harness name. Pi's values come from the assistant message that spent the tokens, or from a newer
`model_change`, and they carry the vendor's own unmapped id. D-5 in
[design-session-identity.md](design-session-identity.md) owns that decision and its rejected
alternatives. Goose and OpenCode read neither field, and whether their stores record one has not
been measured: neither harness is installed here, and this document's standing rule is that a
payload gets captured before a parser gets written.

So attribution for every passthrough harness, measured against a live store, is a precondition for
the comparison rather than a detail of it. Until a row names the authority its turns spend, that row
enters no total: it renders as a route Cargento cannot attribute, which is a third state again, and
not as its own authority and not folded into a guess. The obvious guess is available and is refused
below.

### On a fresh install the surface is a roster of reasons, and no comparison

Both fetch authorities sit behind the first-run disclosure. The page sends `usage=1` only once the
switch is on and the modal has been answered (Q-3), so until then nothing is fetched and Anthropic
and Cursor have no reading. The three local authorities need something to have arrived inside
`window_hours`. On a machine where nothing has run yet, that is every authority empty, and A4's
worked example has no side to it at all.

The decision is that this renders as the roster with a reason on each row and no comparison
published. An authority with no reading is never drawn as 0%, never as headroom, and never left out.
Nothing is ranked until two authorities in one horizon class each carry a measured percentage, and
below that the surface says what it is waiting for: the disclosure, for the two fetched rows, and a
turn in the harness for the local ones. The reader who answers the modal has Anthropic and Cursor a
poll later; Codex arrives the next time Codex runs.

That is a deliberately unimpressive first load, and it is the point. The alternative on identical
evidence is "Codex at 10%" printed beside an absent Anthropic row, which is a migration
recommendation assembled out of one reading and one silence.

## Q-11: Every row names the model it runs on, and a row that cannot read one says so

DRC-4117 promotes `model` from one harness's field to a slot on every session card. Six of the ten
harnesses fill it, each out of bytes its collector already reads, so the whole reading costs no new
file, no new query and no new connection. Four fill nothing, and that is the case the design is
built around.

| Harness | Session model | Subagent model |
|---|---|---|
| Claude | `message.model` on `type: "assistant"` records whose `isSidechain` is falsy, last write wins. The literal `<synthetic>` is rejected by value, never on the `isApiErrorMessage` flag beside it: 18 of the `<synthetic>` records measured carry that flag falsy. | The child's own transcript, under a second key, because the flag inverts there. Every `agent-*.jsonl` child is `isSidechain: true`, so the parent rule would read nothing. |
| Codex | `turn_context.payload.model`, last occurrence in file order, read inside `turns.scan_turns`. | The child rollout's own `turn_context`, read the same way. 198 of 364 rollouts measured are subagent threads and each carries its own. |
| Copilot | `assistant_usage_events.model` on the rows whose `agent_id` is SQL NULL, keyed `(session_id, agent_id)`, first hit in the SELECT's existing `ORDER BY id DESC`. Two extra columns on one statement that already ran. | `subagent.started`, then `data.model`, in `events.jsonl`. It is the same JSON object the label comes from, so the pair is correct by construction. |
| Antigravity | `gen_metadata.data`, protobuf field 1 then field 21, read as a 64-byte tail on the connection `_session_info` already opens. | The child's own conversation store, the same read. Each subagent owns a store, so each is measured rather than inherited. |
| Pi | The newest active-branch entry that carries one: an assistant message, or a `model_change` switched to and not yet spent. D-5 in [design-session-identity.md](design-session-identity.md) owns that reading. | Pi publishes no subagents. |
| Cursor | `providerOptions.cursor.modelName` inside the newest message blob, reached through the root blob's child list, both reads bounded by `substr` inside SQLite. | Cursor's subagents are published as peer top-level rows rather than under a parent, so there is no child list to carry one. Its own ticket. |
| Gemini, Goose, OpenCode, Droid | Not read. Whether these stores record a model has not been measured, and this document's standing rule is that a payload gets captured before a parser gets written. | Gemini, Goose and OpenCode publish a child element with `model` at null. Droid publishes no subagents. |

Nothing here is inferred. Not from a plan name, not from a token count, not from a timestamp join,
not from which quota bucket moved. A guessed model renders in the same type as a measured one, and
the reader has no way to tell them apart, which is the collapse the rest of this section exists to
prevent.

### Three states, because absence here is not a measurement

Q-6 gives consumption a vanishing clause: a row with no figure draws no label and no dash, and the
words are simply not there. `model` gets the opposite treatment, a slot that is always drawn, and
the difference between the two is the whole decision.

Consumption's absence is a fact about the harness. Nine harnesses keep no billing ledger, so a line
with no `used` in it is telling the truth about the world: there is nothing to report. Model's
absence is never a fact about the world. Every session runs on some model, so an unset value is only
a gap in Cargento's reading, and a blank slot is indistinguishable from a measurement. That is the
same argument the rate meter already settled, where an omitted meter left a blank corner reading as
zero and the fix was to print "rate unknown" instead.

So `authorityBit` has three states rather than two:

- provider and model both read: `via Codex · gpt-5.6-sol`, unchanged.
- model only: `model gpt-5`, where the bare value used to sit. The label is what gives the dash in
  the third state a referent, since a lone dash in a metadata line says nothing is missing in
  particular.
- neither: `model —`, with a tooltip naming the harness and saying the model is unknown rather than
  unset.

A fourth combination exists and is easy to miss: a provider read with no model, which happens on
every Pi session whose newest branch entry names an authority and no model. It renders
`via Codex · model —`. Letting the provider clause absorb the dash would reintroduce the two-state
collapse on exactly the rows that already have the most to say.

Four of ten harnesses report no model today, so the dash is the common case and not an edge. That
cost is accepted. It is the board disclosing what it does not know, and the mitigation is the
tooltip wording, never suppressing the dash: suppression is the single move that returns the field
to two states.

`idleRow` still draws no authority at all, and not by inheritance from the consumption rule. Its
written reason is that an idle session is spending nobody's quota, and a model is not quota spend,
so that reason had to be re-argued rather than reused. The one that holds is narrower: the idle
row's cell already truncates at a max width with an ellipsis, so appending to it silently swallows
what is appended.

### A subagent's model shows only where two readings disagree

A child's model is worth space on a card only where it is not the parent's. Repeating the parent's
model under every pill is noise on the surface with the least room for it, and the interesting fact
is a subagent running somewhere else.

**"Differs" is decided on two measured values, never on one measured against one absent.** Written
as `child !== parent`, the predicate is true whenever the parent is null, and a null parent is the
common case: four harnesses in ten report no model at all. That spelling would mark every measured
child as differing on all four and read as a finding. The rule requires both sides to be non-empty
strings and unequal, and it is stated once, in the frontend, because the card and the calm panel
both need it and a second copy is how two views come to disagree.

Equality is string equality. No case folding, no suffix stripping, no prefix matching. Two vendor
strings name the same model when they are the same string, and deciding otherwise is inference,
which renders identically to a reading.

The wire shape that carries this is `subagents: [{"name": str, "model": str | None}]`, with `model`
always present. Two cheaper shapes for it, a parallel map of only the differing children and a
suffix on the label, were dropped and are recorded under rejected alternatives below.

### `provider` stays Pi's alone, and `model` no longer is

`provider` answers "whose allowance is this burning", and nine harnesses answer it with their own
name. Pi is the one that does not, which is why D-5 gave it the field. Nothing in this work changes
that. Copilot's own vendor id is `github-copilot`, and filling the field with it would print "via
Copilot" beside a Copilot badge. Cursor's on-disk namespace is literally `cursor`, so filling it
would be a measurement rather than a guess and would still be noise. Codex's `turn_context` payload has no provider key at all, and
Antigravity's only vendor-adjacent fields are per-generation booleans and an opaque
`MODEL_PLACEHOLDER_*` enum, where reading "google" off the string "Gemini" is inference.

`model` is a different question with a different answer, which is why the two fields part company
here after arriving together.

### Two caps of 40 characters, two symbols, on purpose

`quota.MODEL_LABEL_CAP_CHARS` bounds a per-model usage row's label. `sessions.MODEL_CAP_CHARS`
bounds a session's or a subagent's model. They hold the same number and are deliberately not one
import.

The mechanical reason is that `quota.py` imports `sessions`, so importing back is a cycle. The real
reason is that they bound different requirements. Quota's cap is an input to a distinctness rule: a
per-model row has no identity but its label, so an elided label keeps a digest and two long names
sharing a prefix stay two rows (Q-1). A session row has one model and nothing to tell it apart from,
so it truncates and stops. The numbers agree by coincidence of purpose, and either may move without
the other.

Both are applied through `records.safe_text` at the collector, which is the one door a model string
comes through on its way to the payload. It is untrusted vendor text reaching the DOM, so it is
bounded there and escaped again at every render site.

### Antigravity rests on an observed serialization, and checks itself for it

Every other source in the table is a named field: a JSON key, or a column. Antigravity's is not.
`conversations/<sid>.db` has no model column anywhere in its schema, which is why an earlier
`PRAGMA table_info` survey concluded the harness does not report one. The value is inside the
protobuf blob in `gen_metadata.data`, at top-level field 1 then nested field 21, as the product
display name.

That is a weaker footing than a key, so the parse carries its own guard. Field 21 is the terminal
field of every blob observed, so the read is `SELECT substr(data,-64) FROM gen_metadata ORDER BY idx
DESC LIMIT 1`, and the parse is accepted only when the decoded string runs exactly to the last byte
of the tail. If a future Antigravity build appends a field, the length check fails and the session
reports no model rather than a wrong one. Verified on 15 of 15 readable stores on a live macOS
machine; two further stores hold zero `gen_metadata` rows, which is a session that never got a reply
and maps to the dash.

Field 19 on the same blob also carries a model id and is never preferred: it is an internal alias
(`gemini-pro-default`) where field 21 gives the name the product shows.

The 64-byte window is a privacy bound as well as a cost one. A 700-byte tail on the same row carries
verbatim system-prompt text, and widening the window buys nothing.

### What a failed reading withdraws

A failure withdraws exactly what it feeds. The Antigravity model read has its own exception handler
inside `_session_info`, so a store with no `gen_metadata` table still returns the parent id it was
opened for. A Copilot row whose model cell is unusable does not touch the consumption figure beside
it, does not set the ledger's measured flag, and does not skip the row; the two quantities are
withdrawn independently in both directions. A Claude transcript whose newest assistant record names
`<synthetic>` keeps the real model read before it, rather than having the sentinel overwrite it.

One residual is accepted and worth naming. `_read_ledger`'s truncation guard returns nothing for the
whole Copilot ledger when the window could not be read to its end, and the measured models go with
it. Those rows degrade to the dash, which is the honest reading, but it is a wider withdrawal than
the per-row rule above.

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

### Five shapes for a cross-authority comparison (2026-08-07)

Q-10 settles what comparing capacity across authorities means. These are the shapes that were
considered for it and are not being built. Each one is smaller than the rule that replaced it, which
is why they will be proposed again.

One normalized headroom score per authority, so that a percentage, a dollar figure and an AI Unit
count all land on a 0 to 100 axis. It needs an exchange rate between a subscription window and a
metered dollar and a unit whose entitlement is not published, and no authority publishes any of
those, so the rate would be chosen here. The number would then be a Cargento opinion rendered in the
same type as four measured percentages, and the reader would have no way to tell which was which.

Giving Copilot a denominator by inferring an entitlement from observed spend, or from the plan name,
so that GitHub can join the comparison instead of sitting out of it. This is Q-6's missing
denominator with a guess in the hole. The guess sets the percentage, so a wrong guess reads as
headroom, and a reader looking at five percentages cannot see that one of them was derived from an
assumption.

One axis holding a rolling window and a billing cycle together, on the grounds that both are
percentages of an allowance. They are, and the allowances refill on schedules a factor of about a
hundred and fifty apart: 95% of five hours is an inconvenience, and 95% of a monthly cycle in week
one is the month. Putting them side by side without naming the horizon invites the substitution the
numbers do not support, which is why Q-10 compares inside a horizon class and prints the class.

Comparing only the authorities that returned a figure, and leaving the rest off the surface, because
a row with nothing in it is noise. It is the opposite of noise here. The authorities that go absent
are the fetched ones before the disclosure is answered and the local ones outside `window_hours`,
which is to say the harness that has not been used lately, which is the harness A4 exists to send
work to. A comparison over the answering subset offers the reader capacity that was never measured,
and the reader cannot see the omission from the surface.

Naming a passthrough harness's authority from its configuration, so that Goose and OpenCode can be
folded into a total before per-session attribution exists. D-5 in
[design-session-identity.md](design-session-identity.md) already rejected this for Pi, where reading
`defaultProvider` would attribute today's default setting to an older session's history, and the
argument gets worse rather than better in a comparison: a misattributed row moves a real allowance's
percentage, and a row attributed to an authority it never spent invents capacity somewhere the
reader may already be at the ceiling. An unattributed row is published as unattributed.

### Cheaper shapes for the model slot (2026-08-07)

Q-11 settles how a model reaches the page. These three are smaller than what shipped, which is why
each will be proposed again.

A parallel map of only the children whose model differs from their parent's, alongside the existing
list of labels, so the subagent element never has to grow. Three things kill it and any one is
enough. Absence from such a map means either "matches the parent" or "not measured", which collapses
in the wire format the exact two facts this field exists to keep apart. There is no sound join key
to build it on: subagent labels are non-unique by construction, several collectors fall back to a
bare "subagent", so two unnamed children collide and one child's model gets attributed to its
sibling. Index-parallel arrays are worse, because the Claude collector sorts its children by
descending mtime after they are collected. Fixing the join means publishing a stable child id, which
is the shape change the map was meant to avoid.

Suffixing the model onto the label, `f"{label} · {model}"`, which is the cheapest option by call
site count and touches no frontend at all. It makes a subagent genuinely named `foo · gpt-5`
indistinguishable from a measurement, gives the model no tooltip of its own, and puts a rendering
decision in the collector where a later change to the separator has to be made in seven files. It is
a data-modelling lie that would have to be undone before anything else could be done with the value.

A model column in the calm ledger, on the grounds that calm is the dense view and a dense view
should carry the field. Calm needed zero code to show it: its row normalizer already copies `model`,
and its detail panel already calls the same renderer the card does, so the model arrives in the
panel for free. A column costs the ledger's fixed column count in two places and is guarded by a
hard assertion on the heading row, and it repeats an argument calm has already made twice about what
earns a column: one unit per column, so it can be compared down its own length. A model name is not
a quantity and compares against nothing.
