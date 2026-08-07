/* ── usage band ────────────────────────────────────────────────────────────
   Quota per harness, in both display modes. Everything here renders only when
   the payload carries a `usage` array. Sources feed it from disk (the Codex
   and Copilot collectors), from the network (the Claude and Cursor fetches, a
   configurable opt-out whose consent rides on the poll as the `usage=1`
   parameter — see refresh()), and from a harness pushing its own quota in
   (Antigravity). One entry per harness:
     {harness,                       // key into HARNESS, like a session's
      state,                        // "ok" | "expired"
      asOf,                         // epoch seconds of the snapshot or fetch
      fiveH: {pct, reset},          // integer percent, short reset text
      week:  {pct, reset},
      month: {pct, reset},
      models: [{label, pct, reset}], // per-model sub-limits of the weekly one
      used,                         // spend, preformatted
      today, cost}                  // optional extras, preformatted strings
   Every window slot is optional and a harness fills only the ones it has.
   The `burn` stat is the one figure on this band the payload does not carry:
   it is derived in the page from the percentages as they arrive — see the burn
   projection block below.
   `month` exists because Cursor meters money against a monthly billing cycle
   rather than a rolling window; borrowing `week` for it would put a wrong
   label on a real number, which is the one thing this band cannot afford.
   `models` is the one quota field that is not a named slot, and it is a list
   for the reason the slots are slots: a per-model sub-limit is labelled by the
   vendor, and there is no telling in advance how many arrive, so minting a
   `weekOpus` beside the others would put this table in the business of tracking
   another company's model line-up (quota.py argues the same from its end). Each
   row carries a label and a percentage. The label is vendor text — bounded to 40
   characters there, escaped here — and `reset`/`resetAt` are optional on these
   rows in a way they are not on the window slots: the recorded response carried
   no reset time for its scoped limit at all, so a per-model row can be a
   percentage with no countdown behind it.
   `used` carries spend, as money or as units. It stands alone for a harness
   that reports what it spent but not what it is allowed: Copilot bills in AI
   Units and keeps the entitlement server-side, so there is no denominator and
   therefore no bar and no percentage. It also accompanies a bar where both
   are known, because a percentage near zero does not say whether the plan is
   barely touched or the allowance is tiny. It is always shown when present,
   because a row whose only figure sits behind `configure` reads as broken.
   The disclosure modal opens once, the first time a payload carries
   `usage_fetch` — the capability flag the server raises exactly when a
   discovered harness's quota comes from the network fetcher. Until it is
   answered, no poll carries consent and nothing is fetched. */
const USAGE_OPEN_KEY = "cargento.usageOpen";        /* calm band visibility */
const USAGE_CFG_KEY = "cargento.usageCfg";          /* which stats are shown */
const USAGE_ENABLED_KEY = "cargento.usageEnabled";  /* the feature switch */
const USAGE_MODAL_KEY = "cargento.usageModalSeen";
const USAGE_STATS = [
  ["fiveH", "5h window"], ["week", "weekly window"], ["month", "monthly window"],
  ["models", "per-model limits"],
  ["burn", "burn projection"], ["today", "tokens today"], ["cost", "cost today"]];

let usageOpen = true;
let usageEnabled = true;
let usageModalSeen = false;
let usageCfgOpen = false;   /* the popover is transient, never persisted */
/* `month` defaults on for the same reason the window slots do: it is the only
   gauge Cursor has, and a row whose single figure is hidden reads as broken.
   `burn` stays off, and that is a decision rather than an omission. Its series
   is built in the page from the moment the tab opens (see the burn projection
   block), so for the first ten minutes of every session it has nothing to say
   and says so. A default-on row that reads "warming up" under every window on
   first load teaches the reader that the band is half-built; an opt-in one is
   asked for by someone who has read what it measures. Turning it on is one
   click in `configure`, and the samples accrue whether or not it is shown, so
   the switch is instant rather than the start of another wait.
   `models` defaults on, and it is the one default here argued from what the row
   is for rather than from what it costs. A weekly allowance can be spent per
   model, so Opus at 96% beside Sonnet at 31% is the difference between stopping
   work and switching model — and that comparison is only worth anything BEFORE
   the tighter of the two blocks you. Behind a switch nobody has flipped, it
   arrives after the fact, and showing a model only once it becomes the binding
   constraint is the same thing one step later. It is cheap in the way `burn` is
   not: these are levels the payload already carries, so the row has something
   true to say the first time it renders rather than a warm-up to sit through.
   And the field is absent rather than empty when an account has no sub-limits,
   so an account without them pays no rows for the default. */
let usageCfg = {fiveH: true, week: true, month: true, models: true, burn: false,
                today: false, cost: false};
try{
  if(localStorage.getItem(USAGE_OPEN_KEY) === "0") usageOpen = false;
  if(localStorage.getItem(USAGE_ENABLED_KEY) === "0") usageEnabled = false;
  if(localStorage.getItem(USAGE_MODAL_KEY) === "1") usageModalSeen = true;
  const savedCfg = JSON.parse(localStorage.getItem(USAGE_CFG_KEY));
  /* A torn or all-false value would blank every window; only adopt a saved
     config that still shows at least one stat. */
  if(savedCfg && typeof savedCfg === "object" &&
     USAGE_STATS.some(([k]) => savedCfg[k] === true)){
    /* Key by key, and only the keys the stored object actually carries, so a
       stat added after a reader last opened `configure` keeps its own default
       instead of being read off as false. Rewriting every key from the stored
       object was the old behaviour and it has one bad case: every default-on
       stat added from here on would ship switched off for exactly the readers
       who had used the popover, silently, which looks like the feature never
       landed. An unknown key in the stored object is ignored, because this loop
       walks the stats the page has rather than the ones it found. */
    for(const [k] of USAGE_STATS){
      if(Object.prototype.hasOwnProperty.call(savedCfg, k)) usageCfg[k] = savedCfg[k] === true;
    }
  }
}catch(e){ /* private mode, or a context with no storage — defaults hold */ }

function usagePresent(d){ return !!d && Array.isArray(d.usage); }

function usageStore(key, val){
  try{ localStorage.setItem(key, val); }catch(e){ /* nothing to persist to */ }
}

/* The same thresholds both design comps use: 90 is "act now", 70 is "worth a
   look", mapped onto the board's existing flag tones. */
function usageTone(pct){
  if(pct >= 90) return {ink: "var(--alert)", bar: "var(--alert)"};
  if(pct >= 70) return {ink: "var(--warnink)", bar: "var(--warn)"};
  return {ink: "var(--ink2)", bar: "var(--line2)"};
}

/* Every figure carries the moment it was true. A Codex snapshot is only as
   fresh as the last active turn, and a cached fetch is older than the page —
   a percentage with no timestamp would claim to be live. A bare time only
   says "today", so any older snapshot names its day, and past a week the
   date: "as of 05:29 PM" from four days ago is a lie of omission. */
function usageAsOf(u){
  const t = Number(u.asOf);
  if(!isFinite(t) || t <= 0) return "";
  const then = new Date(t*1000);
  const ref = new Date();
  const time = then.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  if(then.toDateString() === ref.toDateString()) return "as of " + time;
  if(ref - then < 6*86400*1000){
    return "as of " + then.toLocaleDateString([], {weekday: "short"}) + " " + time;
  }
  return "as of " + then.toLocaleDateString([], {month: "short", day: "numeric"});
}

/* A countdown, not a clock time. Two reasons, one measured and one about what
   the reader actually wants to know. "↺ Thu 02:00" needs 92px in a 76px column,
   so it rendered as "↺ Thu 02:…" and named neither the day nor the hour. And
   the question a quota window raises is "how long until I get it back", which a
   wall-clock time makes the reader work out by hand. The absolute time is not
   lost: it stays on the row as its tooltip.
   Built from `resetAt` (epoch seconds) so it stays true between polls, with the
   server's own words as the fallback if a producer sends no instant. */
function usageReset(w){
  const at = Number(w.resetAt);
  if(!isFinite(at) || at <= 0) return String(w.reset || "—");
  const left = at - nowSec();
  /* Past its reset means the window has rolled and this figure is the old one.
     "due" says that without pretending to know the new number. */
  if(left <= 0) return "due";
  if(left < 60) return "<1m";
  return usageSpan(left);
}

/* Two units at most, largest first: "1d 5h" and "2h 16m" both fit the column,
   and a third unit is noise at this precision. Truncated, never rounded up — a
   countdown that rounds up promises time the reader has not got. Shared with
   the burn projection so the two countdowns on a row read the same way. */
function usageSpan(left){
  const days = Math.floor(left / 86400);
  const hours = Math.floor((left % 86400) / 3600);
  const mins = Math.floor((left % 3600) / 60);
  if(days) return days + "d " + hours + "h";
  if(hours) return hours + "h " + mins + "m";
  return mins + "m";
}

/* ── burn projection ───────────────────────────────────────────────────────
   "How fast is this window filling, and when does it fill?" needs a derivative,
   and nothing in the payload carries one: every quota figure is a level. So the
   series is built here, in the page, as one bounded buffer per window — the
   same ring-buffer idiom the token sparkline uses (spark.js) rather than a
   second one.
   What this block deliberately does NOT do is call the race against the window's
   own reset. It did, and across three review rounds every defect found in it sat
   in that one binary verdict — "resets first" / "may fill first" — and never in
   the numbers underneath: the fitted rate and its error band came through a
   4,000-case randomised sweep with no false-safe reading at all. A composed claim
   over uncertain evidence fails toward the reassuring answer, and a row that says
   a window is safe when it is not is worse than a row that says nothing. So the
   quantities stay and the verdict is gone. The reader gets the rate, its
   uncertainty and when the wall arrives, and compares that against the ↺ reset
   countdown already rendered on the same row: two measured numbers side by side,
   and no product of them.
   A persisted series was considered and deliberately not built: it would need a
   server-side write path and a cache file for a signal whose whole value is the
   last hour. The price of deriving it here instead, from levels the payload
   publishes, is four costs that can each be stated on screen rather than assumed
   away. Each is a rendered state, not a silent fallback:

   - Warm-up. There is no history when a tab opens, and samples only accrue
     while a tab is open with usage on, because the quota fetch is driven by
     /api/data requests carrying the page's consent (http_api.py). So the signal
     is coldest at the exact moment the dashboard is opened to ask "can I start
     this now" — which is why that moment gets a sentence saying so. Until
     BURN_MIN_SAMPLES samples span BURN_MIN_SPAN_SEC the row reads "warming up"
     with its own count, and prints no figure at all: unknown and measured are
     different answers and only one of them is available at load.
   - Reload loss. The buffer dies with the page, and a reloaded tab is
     indistinguishable from a fresh one. That is precisely why a fresh one has
     to read as unmeasured — the alternative is a projection built from a
     just-emptied buffer.
   - Quantisation. The published pct is an integer and the server floors its
     quota fetch at 300s (config.usage_poll_floor_sec), so the difference of two
     samples carries up to a whole point of pure rounding. A measured rise of one
     point could be a true rise of anything from just above zero to just under
     two: 100% relative error, and at a 600s span it spans 0 to 12%/h. So a
     fitted rise this fit's own error bound cannot separate from the rounding is
     not published as a rate at all. It is published as a ceiling — the fastest
     slope the samples are consistent with — which is the one thing they do
     support. The bound is derived from the fit's own weights (burnFitError) and
     never from a fixed number of points, because how far the rounding can move
     the answer depends on how many samples the buffer holds. Above the floor a
     rate is printed, and it is printed with its own ± and with a wall that spans
     that ±, so nothing on the row reads sharper than the samples are.
   - Staleness. `asOf` is the moment the percentage was true, and nothing obliges
     it to advance. A stored Antigravity receipt keeps being served with a frozen
     `asOf` for up to window_hours after its harness stops (quota.py), and
     burnPush() drops a repeat of an `asOf` it already holds — so the buffer stops
     growing while the page goes on rendering. Left unbounded that republishes one
     fit forever: byte-identical burn rows three hours apart, next to a countdown
     still visibly ticking. So the newest sample's age is bounded against the
     viewer clock (BURN_STALE_SEC) and a frozen feed reads as unmeasured again.

   Samples are stamped with the payload's own `asOf` rather than the viewer
   clock: `asOf` is the moment the percentage was true, and a cached fetch is
   older than the poll that carried it. Stamping at receipt would compress a
   300s-old figure onto "now" and steepen the slope. So the fit lives entirely in
   payload time, and the viewer's clock is read for exactly two things, both of
   them facts about now rather than about the fit: how old the newest sample is,
   and how long the countdowns on screen have left. */
const BURN_MIN_SAMPLES = 3;
/* Two samples are one interval, and across a 300s interval a single one-point
   rounding step IS the entire measurement. Three samples span two intervals, so
   the fit has something to disagree with and one rounding step cannot own the
   answer. At the server's 300s floor that puts the first projection about ten
   minutes after the tab opens. */
const BURN_MIN_SPAN_SEC = 600;
/* A trailing hour. Older samples describe work that has since stopped, and the
   question is what the next hour looks like, not the last four. */
const BURN_HISTORY_SEC = 3600;
/* How old the newest sample may be before the fit stops being published at all,
   in seconds, measured against the viewer clock rather than against the rest of
   the buffer. Two arrival intervals at the server's own 300s quota floor
   (config.usage_poll_floor_sec): one missed refresh is jitter, two in a row is a
   feed that has stopped — a harness gone quiet, a receipt frozen on a dead `asOf`,
   a tab a suspended laptop took with it. It has to sit well under
   BURN_HISTORY_SEC, or a buffer can age out entirely while still holding samples
   enough to fit, which is precisely the state that kept republishing one hour-old
   slope three hours later. And it is deliberately not generous: a rate whose
   newest evidence is ten minutes old is not describing the next hour whichever
   way it points, so "nobody has measured this recently" is the true reading
   rather than a cautious one. */
const BURN_STALE_SEC = 600;
/* How many times its own worst-case error a fitted slope must clear before it
   is printed as a rate. At two, the relative error on the published rise is
   bounded at 50%, which is still coarse enough that every figure this row prints
   is marked as one — `~` for an estimate, `under` for a ceiling — and names its
   own ± in the tooltip. A multiple of the error rather than a fixed number of
   percentage points, because the error is not a constant: see burnFitError. At
   three samples the two work out to the same thing (a two-point rise over the
   span); past three, a fixed number of points quietly stops being a bound.
   It earns a second keep beyond legibility: at a factor of two the slow end of
   the band, slope − band, is still at least band and so still positive, which is
   what lets a resolved rate publish a wall with two finite ends. */
const BURN_RESOLUTION_FACTOR = 2;
/* The slots a projection is fitted over, and the whole of them. The per-model
   rows are deliberately not among them, so nothing samples them and no buffer is
   ever keyed on a model — the argument is in burnUnprojected(), which is what
   those rows render instead. */
const BURN_SLOTS = ["fiveH", "week", "month"];
/* "harness:slot" -> [{t, v, r}]: the instant, the percentage, and the reset
   instant the reading was taken under. */
const burnHistory = new Map();
const burnKey = (harness, slot) => harness + ":" + slot;

function burnPush(key, t, v, resetAt){
  let arr = burnHistory.get(key);
  if(!arr) burnHistory.set(key, arr = []);
  if(arr.length){
    const last = arr[arr.length - 1];
    if(t <= last.t) return;         /* the same fetch, re-rendered */
    /* Two independent signs of one event: the window rolled, or the vendor
       restated it. Either way the samples before it measure a window that no
       longer exists, and a slope fitted across the discontinuity is a fit over
       two separate allowances. Start again, and warm up again.
       A fall is the visible sign, and on its own it is not enough: it can only
       catch a roll whose new level sits BELOW the old one. A window that rolls
       and then climbs straight past where the last one stood never falls, so the
       buffer keeps both sides and the fit spans the gap — and the bias runs the
       wrong way, understating the new window's rate and pushing its wall out.
       The reset instant catches that case. Producers build `resetAt` from the
       vendor's own absolute reset time (sessions.reset_fields), so it holds still
       for the life of a window and a change in it really is a new allowance
       rather than sampling noise. */
    if(v < last.v || resetAt !== last.r) arr.length = 0;
  }
  arr.push({t, v, r: resetAt});
  const cutoff = t - BURN_HISTORY_SEC;
  while(arr.length && arr[0].t < cutoff) arr.shift();
}

/* Called once per payload from usageBody(), so the buffers fill whether or not
   the burn stat is switched on — turning it on is then instant instead of the
   start of another ten-minute wait. In the calm view a collapsed band does not
   render and so does not sample, which leaves a hole rather than a reset: the
   buffer survives the collapse, because the prune loop lives here and does not
   run while nothing is on screen. So a band reopened inside BURN_HISTORY_SEC
   lands one reading onto the old ones and fits across the gap.

   That is deliberate, and it is safe in the direction that matters. Both
   endpoints are readings that really happened, so the fit is a true trailing
   mean over its stated span — which the tooltip names — and a gap makes the
   projection *less* reassuring rather than more, because a step change the hole
   spans lands as a steeper slope. The newest reading is what BURN_STALE_SEC
   bounds, so a band reopened after the feed stopped reads `stale`, not a rate. */
function usageSample(d){
  if(!usagePresent(d)) return;
  const seen = new Set();
  for(const u of d.usage){
    const t = Number(u.asOf);
    /* No timestamp, no sample. A figure of unknown age placed at "now" bends
       the slope by however stale it was; every producer sends `asOf`. */
    if(!isFinite(t) || t <= 0) continue;
    for(const slot of BURN_SLOTS){
      const w = u[slot];
      if(!w || w.pct == null) continue;
      const v = Number(w.pct);
      if(!isFinite(v)) continue;
      const key = burnKey(u.harness, slot);
      seen.add(key);
      /* Every sample carries the reset instant it was taken under, so a roll is
         caught even when the new window's level does not fall below the old one.
         Normalised to null the same way burnRead() does it: a missing instant
         must compare equal to the next missing instant, and NaN never does. */
      const at = Number(w.resetAt);
      burnPush(key, t, Math.max(0, Math.min(100, v)),
               isFinite(at) && at > 0 ? at : null);
    }
  }
  /* Drop the buffers this payload no longer carries — a token that expired, a
     harness that went away — so the map cannot grow without bound. */
  for(const key of burnHistory.keys()) if(!seen.has(key)) burnHistory.delete(key);
}

/* Least squares over every retained sample rather than first-to-last, so one
   noisy endpoint cannot set the whole rate. Percent per second. */
function burnSlope(pts){
  const n = pts.length;
  let st = 0, sv = 0;
  for(const p of pts){ st += p.t; sv += p.v; }
  const mt = st / n, mv = sv / n;
  let num = 0, den = 0;
  for(const p of pts){
    num += (p.t - mt) * (p.v - mv);
    den += (p.t - mt) * (p.t - mt);
  }
  return den > 0 ? num / den : 0;
}

/* The largest error the integer samples can put on that slope, in percent per
   second. Every published pct is a whole number, so each sample sits within half
   a point of the truth. The least-squares slope is a fixed linear combination of
   the samples — slope = Σ wᵢ·vᵢ with wᵢ = (tᵢ − t̄)/Σ(tⱼ − t̄)² — so the worst the
   half-points can do is 0.5·Σ|wᵢ|, reached when every rounding error happens to
   take the sign of its own weight.
   Read as an error on the fitted RISE, that is 0.5·span·Σ|tᵢ − t̄|/Σ(tᵢ − t̄)²,
   and it is not a constant: one whole point at three samples, 1.2 at four, and
   climbing towards 1.5 as the buffer fills. BURN_HISTORY_SEC is an hour, so a tab
   left open for one normally holds a dozen samples — which is why "one point on
   the rise" is a three-sample special case and not a bound. Deriving it here
   instead means the resolution floor, the printed ceiling and the printed ± all
   move together with the buffer.
   No guard on the denominator: the caller has already established a span above
   BURN_MIN_SPAN_SEC, so the first and last stamps differ and the sum of squared
   deviations is positive. */
function burnFitError(pts){
  const n = pts.length;
  let st = 0;
  for(const p of pts) st += p.t;
  const mt = st / n;
  let dev = 0, den = 0;
  for(const p of pts){
    dev += Math.abs(p.t - mt);
    den += (p.t - mt) * (p.t - mt);
  }
  return 0.5 * dev / den;
}

/* One window's reading: a state naming what kind of answer this is. Nothing
   returns a bare number, because the caller must not be able to mistake "we
   cannot tell" for one.
     spent   already full — a level the payload published, not a projection
     stale   the newest reading is too old to describe now
     warmup  too few readings, or too short a span, to fit anything
     slow    a rise this span cannot resolve: a ceiling, not a rate
     proj    a resolved rate, its band, and the wall interval that band spans
   `slow` is not "idle": it means the rise is smaller than this span can resolve,
   so the reading is a ceiling rather than a rate.
   `w.resetAt` is not read here, and that absence is the point. It is the buffer's
   business — burnPush() watches it to notice a window rolling — and it is already
   on the row as the ↺ countdown. Reading it a third time here is what let this
   function multiply a rate by a deadline into a verdict, and the verdict is the
   one part of this signal that kept being wrong. */
function burnRead(key, w){
  /* Already full needs no history and no fit: the bar beside it reads 100%.
     Checked ahead of everything the buffer can say, so neither an empty buffer nor
     a frozen one can report an exhausted window as merely unmeasured. */
  const pct = Number(w && w.pct);
  if(isFinite(pct) && pct >= 100) return {state: "spent"};
  const pts = burnHistory.get(key) || [];
  const n = pts.length;
  const last = n ? pts[n - 1] : null;
  /* Age is measured from now, not from the rest of the buffer, and it is tested
     ahead of the count and the span because it outranks them: a buffer holding
     one three-hour-old reading is not filling up slowly, it has stopped being
     fed. Counting it toward a threshold nothing is going to cross would print
     "warming up" on a series that will never warm. */
  const age = last ? nowSec() - last.t : 0;
  if(last && age > BURN_STALE_SEC) return {state: "stale", age};
  const span = n > 1 ? last.t - pts[0].t : 0;
  if(n < BURN_MIN_SAMPLES || span < BURN_MIN_SPAN_SEC) return {state: "warmup", n, span};
  const level = isFinite(pct) ? Math.max(0, Math.min(100, pct)) : last.v;
  /* Non-negative by construction: burnPush() restarts the buffer on any fall, so
     a downward fit would mean a fit over one sample, which cannot get here. */
  const slope = Math.max(0, burnSlope(pts));
  /* The two figures every reading below rests on, both in percent per second:
     what the rounding can do to this particular fit, and the slope a rate has to
     clear before it is printed as one. */
  const band = burnFitError(pts);
  const floor = BURN_RESOLUTION_FACTOR * band;
  /* How much of the window is left to burn, and the same ±0.5 of integer
     rounding that gives the slope its band applies to this level too: a published
     89 is anything in 88.5 … 89.5. `head` is the least headroom consistent with
     it and `tail` the most, so the earliest wall is dated off the smaller. It is
     a whole half point, which at a slow rate is minutes of phantom headroom —
     the direction that matters, since the early end of the interval is the figure
     a reader acts on. Clamped at zero: a level within half a point of 100 has no
     headroom left to divide. Taking the worst of the level and the worst of the
     slope together is slightly conservative, because one rounding pattern
     produces both, and a marginally wider interval overstates the uncertainty
     rather than the safety. */
  const head = Math.max(0, 100 - level - 0.5);
  const tail = Math.max(0, 100 - level + 0.5);
  if(slope < floor){
    /* Below the resolution floor there is no rate to print, only a ceiling: the
       fastest slope these samples are consistent with, which is the fitted one
       plus its whole worst-case error. It is never printed tighter than the floor
       itself, since a row whose whole claim is "this span cannot resolve a rise
       this small" cannot in the same breath report having measured a smaller one.
       `soonest` is the only instant that ceiling supports — the earliest this
       window could be full — and it is a bound in one direction only, because
       these same samples are equally consistent with a slope of zero, which never
       fills at all. A one-ended bound is why it goes in the tooltip and not on
       the row: printed as a figure beside "under 3%/h" it would read as a
       prediction, and the missing half of the interval is the half that says the
       window may be going nowhere. */
    const ceiling = Math.max(slope + band, floor);
    return {state: "slow", span, ceilHour: ceiling * 3600,
            soonest: last.t + head / ceiling};
  }
  /* The wall is published as the interval its band spans rather than as the point
     estimate, and this is the judgement call the removal of the verdict leaves
     behind, so it is argued instead of asserted.
     A single "wall in 57m" is a quantity, and on its own terms defensible. But it
     is also the exact input a reader uses to make the comparison this row has
     just stopped making for them, and handed over as a point it invites that
     comparison at a precision the fit has not got: at 16.8%/h ±4.8 the wall is
     anywhere from 43m to 1h 22m out, and a reader given "57m" against a reset 50m
     away concludes "fine" from evidence that says "possibly not". Deleting the
     verdict and then feeding the reader a figure that reconstructs it in their
     head leaves the defect exactly where it was, one layer further out.
     The pessimistic end alone was the other candidate and is rejected as the
     mirror of the same failure: a row that only ever names the earliest possible
     wall overstates every window it describes, and a signal that cries wolf is
     read as decoration inside a week. The interval says what is known and how
     well at the same time, which is the whole argument for keeping these numbers
     while dropping the verdict over them.
     Both ends are finite by construction — see BURN_RESOLUTION_FACTOR — so this
     branch can divide by slope − band without a guard. */
  return {state: "proj", span, perHour: slope * 3600, bandHour: band * 3600,
          wallSoon: last.t + head / (slope + band),
          wallLate: last.t + tail / (slope - band)};
}

/* One decimal at most, and none at all past 10: the input is an integer sampled
   a few times, and "7.43%/h" would dress that up as a measurement. The bare
   figure, so each caller can say what kind of figure it is — `~` for an
   estimate, `under` for a ceiling, `±` for the band. */
function burnRate(perHour){
  const r = perHour >= 10 ? Math.round(perHour) : Math.round(perHour * 10) / 10;
  return r + "%/h";
}

function burnLeft(sec){
  if(!isFinite(sec) || sec <= 0) return "now";
  if(sec < 60) return "<1m";
  return usageSpan(sec);
}

/* The words for one reading: a short label for the row, and the whole story in
   the tooltip. One tone, and one reading earns it: `hot` for a window that is
   already full, which is a level the payload published rather than anything
   fitted here. Every projection is dim however fast it reads — a colour on a
   projection is the tone half of the verdict this row no longer delivers, and the
   readings that used to raise one are the readings the reviews found wrong. */
function burnWords(r){
  if(r.state === "spent"){
    return {text: "window spent", tone: "hot",
            title: "This window is already full. The wall is here, not ahead of you."};
  }
  if(r.state === "stale"){
    /* The age, not just the word: "stale" alone reads as a Cargento fault, and
       the number is what tells the reader whether their harness went quiet ten
       minutes ago or stopped this morning. */
    return {text: "stale · last reading " + fmtDur(r.age) + " ago", tone: "",
            title: "No projection: the newest quota reading for this window is " +
              fmtDur(r.age) + " old, so there is nothing current to fit. A rate is" +
              " published only while readings keep arriving, within " +
              fmtDur(BURN_STALE_SEC) + " of now — a harness that has stopped still has" +
              " its last figure served for hours, and fitting that would republish one" +
              " old slope beside a countdown that is still moving."};
  }
  if(r.state === "warmup"){
    /* Two requirements gate a projection, a count and a span, and either one can
       be the one still unmet — `asOf` advances as fast as its producer stamps it,
       not at the server's 300s fetch floor, so a tab can hold nine readings taken
       inside four minutes and still have nothing worth fitting. The headline names
       whichever requirement is actually short: "9 of 3" reads as a broken counter
       and sends the reader looking for the wrong bug. */
    const short = r.n < BURN_MIN_SAMPLES
      ? r.n + " of " + BURN_MIN_SAMPLES
      : fmtDur(r.span) + " of " + fmtDur(BURN_MIN_SPAN_SEC);
    return {text: "warming up · " + short, tone: "",
            title: "No projection yet: " + r.n + " reading" + (r.n === 1 ? "" : "s") +
              (r.span > 0 ? " over " + fmtDur(r.span) : "") + ", and a projection needs " +
              BURN_MIN_SAMPLES + " readings spanning " + fmtDur(BURN_MIN_SPAN_SEC) +
              ". Quota is" +
              " sampled only while this tab is open with usage on, and the readings are" +
              " lost on reload — so this is unknown, not clear."};
  }
  if(r.state === "slow"){
    /* A ceiling, never a rate: "under 12%/h" is what these samples support, and
       printing the fitted number instead would publish the rounding. */
    const ceiling = "under " + burnRate(r.ceilHour);
    return {text: ceiling, tone: "",
            title: "The rise over " + fmtDur(r.span) + " is too small for a span of" +
              " integer percentages to resolve, so the supported figure is a ceiling — " +
              ceiling + " — rather than a rate. Even at that ceiling this window would" +
              " not be full for another " + burnLeft(r.soonest - nowSec()) + ", and the" +
              " same readings are equally consistent with its not filling at all."};
  }
  const rate = "~" + burnRate(r.perHour);
  const soon = burnLeft(r.wallSoon - nowSec());
  const late = burnLeft(r.wallLate - nowSec());
  /* Both ends collapse onto one figure whenever they land in the same minute — a
     window that is about to fill does it, since half a point is gone inside the
     minute either way — and "<1m–<1m" would make a sharp reading look vague. */
  const one = soon === late;
  return {text: rate + " · wall " + (one ? soon : soon + "–" + late), tone: "",
          title: "At " + rate + " (±" + burnRate(r.bandHour) + ", the resolution this" +
            " span supports) this window reaches 100% " + (one
              ? "in about " + soon + ": both ends of the band round to the same figure"
              : "somewhere between " + soon + " and " + late + " from now") +
            ". Fitted over " + fmtDur(r.span) + " of readings taken in this tab. The ↺" +
            " countdown on this row is when the allowance comes back: the two figures are" +
            " stated separately rather than compared, because a rate known this coarsely" +
            " cannot settle which of them arrives first."};
}

/* Rendered under its own window's row rather than as one figure per harness: a
   5h window and a weekly window fill at different rates and reset at different
   times, so a single per-harness projection would have to pick one silently. */
function burnRow(harness, slot, w){
  if(!usageCfg.burn) return "";
  const words = burnWords(burnRead(burnKey(harness, slot), w));
  return `<span class="u-burn${words.tone ? " " + words.tone : ""}"` +
    ` title="${esc(words.title)}">${esc(words.text)}</span>`;
}

/* What a per-model row puts in the burn slot, which is a sentence rather than a
   rate. Rendered only while the projection is switched on, and rendered rather
   than left blank: a model row sitting silent beneath a weekly row that reads
   "~4%/h · wall 2h 10m" is read as a limit that is not filling, and an absence
   that reads as good news is the failure the rest of this block was rebuilt to
   avoid. So the row says which of the three answers this is — measured, measured
   zero, or not measured — and this one is the third.
   Two reasons nothing is fitted, and both are about identity rather than about
   the arithmetic. A per-model row's only identity is the vendor's own display
   name: two rows can carry the same one, and a buffer keyed on it would then hold
   two series interleaved and publish the first row's slope on the second. And the
   recorded response carried no reset instant for its scoped limit at all, which
   is exactly the input burnPush() needs to notice a limit rolling — a fall is the
   only other sign, and a limit that rolls and then climbs straight past where the
   old one stood never falls. A fit would span two allowances and read SLOWER than
   the truth, pushing its wall out, which is the reassuring direction, on a signal
   nobody has yet watched move: one scoped row, on one account, at one moment. The
   weekly row above is the window these subdivide, it carries a reset instant, and
   it is projected — that is where a reader gets a rate. */
/* `parentShown` is whether the weekly row these subdivide is actually drawn: it
   can be switched off in `configure`, and an entry can carry `fiveH` and `models`
   with no `week` at all, since the fetch only bails when BOTH named windows are
   missing. The tooltip used to assert the parent was on screen unconditionally,
   which is a claim the reader can see is false in either of those states. */
function burnUnprojected(parentShown){
  if(!usageCfg.burn) return "";
  const why = "No rate is fitted to a per-model limit." +
    " Its only identity is the vendor's own display name, and the recorded response" +
    " carried no reset instant for it — without one, a limit that rolls and then" +
    " climbs past where the old one stood never falls, so a fitted rate would span" +
    " two allowances and read slower than the truth.";
  const parent = parentShown
    ? " The weekly window these subdivide has its own row in this tile, and that one is projected."
    : " The weekly window these subdivide is not on screen, so there is no projected row to read" +
      " them against.";
  return `<span class="u-burn" title="${esc(why + parent)}">not projected</span>`;
}

/* The label column is sized per entry rather than once in the stylesheet, and
   these are the three numbers that size it. A window row's label is two
   characters and a per-model row's is a model's display name, so one width for
   the whole band would spend the same 42px of every Codex, Copilot and Cursor bar
   to hold a name those harnesses never send. Instead each entry asks for what its
   own longest label needs, floored at the width the window labels already had and
   capped where the tile runs out — styles.css states both measurements and declares
   the default. Bars stay aligned inside a tile, because every row in it reads the
   one value; they no longer align across tiles, which is the cost of this and is
   the cheaper cost, since a bar is read against its own row's percentage and the
   other windows of its own harness, never against another harness's allowance.
   Lengths are counted in UTF-16 code units, which over-counts an astral pair and
   under-counts a combining mark. Both land inside the cap and the ellipsis, so the
   error shows up as a column a few pixels off rather than as text escaping it. */
const U_LAB_ADVANCE_PX = 7.11;
const U_LAB_MIN_PX = 30;
const U_LAB_MAX_CHARS = 10;

function usageEntry(u){
  const h = own(HARNESS, u.harness, null) ||
    {code: String(u.harness || "?").slice(0, 2).toUpperCase(), name: u.harness};
  const ico = h.icon
    ? `<span class="cm-ico" style="-webkit-mask:url('${h.icon}') center/contain no-repeat;` +
      `mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="cm-icot">${esc(h.code)}</span>`;
  const head = `<div class="u-hrow"><span class="cm-hcell">${ico}</span>` +
    `<span class="u-hname" title="${esc(h.name || u.harness)}">${esc(h.name || u.harness)}</span></div>`;
  /* An expired token shows no numbers at all: stale figures presented next to
     live ones read as live. The remedy belongs to the harness, so the note
     points there — Cargento never refreshes a token. */
  if(u.state === "expired"){
    return `<div class="u-entry">${head}` +
      `<div class="u-expired"><span class="u-excl" role="img" aria-label="attention">!</span>` +
      `<span>token expired — sign in again in ${esc(h.name || u.harness)}</span></div></div>`;
  }
  /* One gauge row. `label` arrives ready for the markup, because the window
     labels are literals here and a model's is vendor text that has to go through
     esc() first. `slot` names the burn buffer this row's readings feed, and null
     says this row is not sampled at all — see burnUnprojected(). `full` is the
     label before the column truncates it, for a label long enough to need the
     hover; the two-character window labels pass nothing and get no tooltip. */
  /* The weekly row is drawn only when the reader has it switched on AND the
     entry carries one. Per-model rows subdivide it, so they have to know: a
     sub-limit is still a real measured percentage without its parent on screen,
     and it still renders, but nothing may claim the parent is there to read it
     against. */
  const weekShown = !!(usageCfg.week && u.week && u.week.pct != null);
  const win = (label, slot, w, full) => {
    if(!w || w.pct == null) return "";
    const pct = Math.max(0, Math.min(100, Math.round(Number(w.pct) || 0)));
    const tone = usageTone(pct);
    return `<div class="u-wrow">` +
      `<span class="u-wlab"${full ? ` title="${esc(full)}"` : ""}>${label}</span>` +
      `<span class="cm-track"><span class="cm-fill" style="width:${pct}%;` +
      `background:${tone.bar}"></span></span>` +
      `<span class="u-pct" style="color:${tone.ink}">${pct}%</span>` +
      /* The tooltip keeps the wall-clock time the countdown replaced, so the
         exact moment is still one hover away. A per-model row can arrive with no
         reset at all, and then both halves say so: "↺ —" on the row and "resets
         at an unknown time" on the hover. A blank column would read as a row
         still loading, and a borrowed weekly countdown would be a figure this
         limit never published. */
      `<span class="u-reset" title="resets ${esc(String(w.reset || "at an unknown time"))}">` +
      `↺ ${esc(usageReset(w))}</span>` +
      (slot ? burnRow(u.harness, slot, w) : burnUnprojected(weekShown)) + `</div>`;
  };
  /* No bar and no percentage: there is no limit to be a fraction of. The
     label says "used" rather than a window name so it cannot be misread as a
     gauge that happens to be missing its track. */
  const usedRow = u.used == null
    ? ""
    : `<div class="u-wrow"><span class="u-wlab">used</span>` +
      `<span class="u-used">${esc(String(u.used))}</span></div>`;
  /* The per-model sub-limits, each a row of its own directly under the weekly bar
     they subdivide. Their own rows rather than a disclosure or a swap: choosing
     between two models means seeing both at once, and a row that only appears
     once its model becomes the tighter constraint appears too late to switch.
     Nothing here sorts or slices — the server already ordered these by label and
     bounded how many it sends, and a second opinion about row order is how two
     polls come to disagree about it. */
  const modelRows = [];
  let modelChars = 0;
  if(usageCfg.models && Array.isArray(u.models)){
    for(const m of u.models){
      /* No name, no row. An unlabelled bar under the weekly one reads as a second
         weekly figure disagreeing with the first, which is worse than the row's
         absence; quota.py drops the same case on its way out, for the same
         reason. A row with no percentage is dropped by win() itself, and the
         column is measured off the rows that survive both — a label whose row was
         never drawn must not widen the column it was going to sit in. */
      if(!m || typeof m.label !== "string" || !m.label) continue;
      const row = win(esc(m.label), null, m, m.label);
      if(!row) continue;
      modelChars = Math.max(modelChars, m.label.length);
      modelRows.push(row);
    }
  }
  const wins = usedRow + (usageCfg.fiveH ? win("5h", "fiveH", u.fiveH) : "") +
    (usageCfg.week ? win("wk", "week", u.week) : "") + modelRows.join("") +
    (usageCfg.month ? win("mo", "month", u.month) : "");
  const extras = [];
  if(usageCfg.today && u.today != null) extras.push(["today", u.today]);
  if(usageCfg.cost && u.cost != null) extras.push(["cost", u.cost]);
  const asOf = usageAsOf(u);
  const tail = (extras.length || asOf)
    ? `<div class="u-extras">` +
      extras.map(([k, v]) => `<span>${k} <b>${esc(String(v))}</b></span>`).join("") +
      (asOf ? `<span class="u-asof">${esc(asOf)}</span>` : "") + `</div>`
    : "";
  /* The label column, sized here and nowhere else — see the three constants
     above. Only a rendered model row can widen it, and an entry that has none
     carries no property at all rather than one restating the default: the
     stylesheet owns the width the window labels need, and a harness that never
     sends a model name should be able to change it there alone. */
  const lab = Math.ceil(Math.min(U_LAB_MAX_CHARS, modelChars) * U_LAB_ADVANCE_PX);
  const width = lab > U_LAB_MIN_PX ? ` style="--ulab:${lab}px"` : "";
  return `<div class="u-entry"${width}>${head}${wins}${tail}</div>`;
}

function usageCfgPop(){
  if(!usageCfgOpen) return "";
  const shown = USAGE_STATS.filter(([k]) => usageCfg[k]).length;
  /* The master switch is the modal's off switch, reachable again later — the
     way back the disclosure promises. It is not part of the stats group and
     never locks. */
  const master = `<button type="button" class="u-cfg-row" data-calm="uon"` +
    ` aria-pressed="${usageEnabled}">` +
    `<span class="u-cfg-box${usageEnabled ? " on" : ""}">${usageEnabled ? "✓" : ""}</span>` +
    `usage on</button>`;
  const rows = USAGE_STATS.map(([k, label]) => {
    /* The last shown stat cannot be unchecked: a band with every stat hidden
       is indistinguishable from a broken one. */
    const locked = usageCfg[k] && shown <= 1;
    return `<button type="button" class="u-cfg-row${locked ? " locked" : ""}"` +
      ` data-calm="ustat" data-arg="${k}" aria-pressed="${!!usageCfg[k]}"` +
      `${locked ? ' aria-disabled="true"' : ""}>` +
      `<span class="u-cfg-box${usageCfg[k] ? " on" : ""}${locked ? " locked" : ""}">` +
      `${usageCfg[k] ? "✓" : ""}</span>${esc(label)}</button>`;
  }).join("");
  return `<div class="u-cfg"><span class="u-cfg-k">usage</span>${master}` +
    `<span class="u-cfg-k">show stats</span>${rows}</div>`;
}

function usageBody(d){
  if(!usageEnabled){
    return `<div class="u-note">usage is off — turn it back on under configure</div>`;
  }
  /* The one sampling point, so the burn buffers advance once per payload no
     matter which view is on screen. burnPush() ignores a repeat of a `asOf` it
     already holds, which is what makes a re-render from a UI action (usageAction
     re-renders lastData) harmless rather than a duplicated sample. */
  usageSample(d);
  if(!d.usage.length){
    return `<div class="u-note">No quota data yet. Harnesses that publish usage will appear here.</div>`;
  }
  return `<div class="u-grid">${d.usage.map(usageEntry).join("")}</div>`;
}

function usageSectionRegular(d){
  if(!usagePresent(d)) return "";
  return `<div class="usec"><div class="sec"><span class="sec-k">Usage · rate limits</span>` +
    `<span class="sec-rule"></span>` +
    `<button type="button" class="u-link${usageCfgOpen ? " on" : ""}" data-calm="ucfg"` +
    ` aria-expanded="${usageCfgOpen}">configure ▾</button></div>` +
    `<div class="u-panel">${usageBody(d)}</div>${usageCfgPop()}</div>`;
}

function usageBandCalm(d){
  if(!usagePresent(d) || !usageOpen) return "";
  return `<div class="u-band"><div class="u-band-head">` +
    `<span class="cm-k">usage · rate limits per harness</span><span class="cm-sp"></span>` +
    `<button type="button" class="u-link${usageCfgOpen ? " on" : ""}" data-calm="ucfg"` +
    ` aria-expanded="${usageCfgOpen}">configure ▾</button></div>` +
    usageBody(d) + usageCfgPop() + `</div>`;
}

/* First-run disclosure. The copy quotes the security contract (SECURITY.md,
   "Usage quota reads") — it must not promise anything the contract does not
   say. */
function usageModal(d){
  if(!usagePresent(d) || !d.usage_fetch || usageModalSeen) return "";
  return `<div class="u-overlay" role="dialog" aria-modal="true"` +
    ` aria-label="usage disclosure"><div class="u-modal">` +
    `<div class="u-modal-h">Show usage and rate limits?</div>` +
    `<p class="u-modal-p">Cargento can fetch each vendor's quota so the dashboard` +
    ` shows how much of your allowance is used and when it resets — the 5-hour and` +
    ` weekly windows, or the monthly billing period for a vendor that meters spend.</p>` +
    `<p class="u-modal-p">What is sent: the vendor's own OAuth access token, and` +
    ` nothing else. No transcript content, no prompts, no paths, no project names,` +
    ` no machine identifiers. What comes back is quota numbers. Session data never` +
    ` appears in either direction. The token is never refreshed, never written,` +
    ` never logged, and never served.</p>` +
    `<p class="u-modal-p">Usage is on by default. Turn it off here and nothing is` +
    ` fetched; turn it back on any time under configure.</p>` +
    `<div class="u-modal-acts">` +
    `<button type="button" class="u-primary" data-calm="umodal" data-arg="on">Keep usage on</button>` +
    `<button type="button" class="u-act" data-calm="umodal" data-arg="off">Turn it off</button>` +
    `</div></div></div>`;
}

function usageAction(act, arg){
  if(act === "usage"){
    usageOpen = !usageOpen; usageCfgOpen = false;
    usageStore(USAGE_OPEN_KEY, usageOpen ? "1" : "0");
  } else if(act === "ucfg"){
    usageCfgOpen = !usageCfgOpen;
  } else if(act === "uon"){
    usageEnabled = !usageEnabled;
    usageStore(USAGE_ENABLED_KEY, usageEnabled ? "1" : "0");
    /* Consent just changed; the next poll would carry it in 5s. Poll now so
       switching usage back on fills the band without the wait. */
    if(usageEnabled) refresh();
  } else if(act === "ustat"){
    if(!Object.prototype.hasOwnProperty.call(usageCfg, arg)) return true;
    const shown = USAGE_STATS.filter(([k]) => usageCfg[k]).length;
    if(usageCfg[arg] && shown <= 1) return true;  /* the last stat stays */
    usageCfg[arg] = !usageCfg[arg];
    usageStore(USAGE_CFG_KEY, JSON.stringify(usageCfg));
  } else if(act === "umodal"){
    usageModalSeen = true;
    usageStore(USAGE_MODAL_KEY, "1");
    if(arg === "off"){
      usageEnabled = false;
      usageStore(USAGE_ENABLED_KEY, "0");
    } else {
      /* "Keep usage on" is the first moment consent exists: poll right away
         so the first fetch starts now rather than on the next 5s tick. */
      refresh();
    }
  } else return false;
  if(lastData) render(lastData);
  return true;
}

