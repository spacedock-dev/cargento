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
      used,                         // spend, preformatted
      today, cost}                  // optional extras, preformatted strings
   Every window slot is optional and a harness fills only the ones it has.
   The `burn` stat is the one figure on this band the payload does not carry:
   it is derived in the page from the percentages as they arrive — see the burn
   projection block below.
   `month` exists because Cursor meters money against a monthly billing cycle
   rather than a rolling window; borrowing `week` for it would put a wrong
   label on a real number, which is the one thing this band cannot afford.
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
   the switch is instant rather than the start of another wait. */
let usageCfg = {fiveH: true, week: true, month: true, burn: false, today: false,
                cost: false};
try{
  if(localStorage.getItem(USAGE_OPEN_KEY) === "0") usageOpen = false;
  if(localStorage.getItem(USAGE_ENABLED_KEY) === "0") usageEnabled = false;
  if(localStorage.getItem(USAGE_MODAL_KEY) === "1") usageModalSeen = true;
  const savedCfg = JSON.parse(localStorage.getItem(USAGE_CFG_KEY));
  /* A torn or all-false value would blank every window; only adopt a saved
     config that still shows at least one stat. */
  if(savedCfg && typeof savedCfg === "object" &&
     USAGE_STATS.some(([k]) => savedCfg[k] === true)){
    for(const [k] of USAGE_STATS) usageCfg[k] = savedCfg[k] === true;
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
   "Is this window going to run out before it resets?" needs a derivative, and
   nothing in the payload carries one: every quota figure is a level. So the
   series is built here, in the page, as one bounded buffer per window — the
   same ring-buffer idiom the token sparkline uses (spark.js) rather than a
   second one. A persisted series was considered and deliberately not built: it
   would need a server-side write path and a cache file for a signal whose whole
   value is the last hour, and the price of not persisting is four costs that
   can each be stated on screen instead of assumed away. Each is a rendered
   state, not a silent fallback:

   - Warm-up. There is no history when a tab opens, and samples only accrue
     while a tab is open with usage on, because the quota fetch is driven by
     /api/data requests carrying the page's consent (http_api.py). So the signal
     is coldest at the exact moment the dashboard is opened to ask "can I start
     this now" — which is why that moment gets a sentence saying so. Until
     BURN_MIN_SAMPLES samples span BURN_MIN_SPAN_SEC the row reads "warming up"
     with its own count, never "resets first": unknown and clear are different
     answers and only one of them is true at load.
   - Reload loss. The buffer dies with the page, and a reloaded tab is
     indistinguishable from a fresh one. That is precisely why a fresh one has
     to read as unmeasured — the alternative is a projection built from a
     just-emptied buffer.
   - Quantisation. The published pct is an integer and the server floors its
     quota fetch at 300s (config.usage_poll_floor_sec), so the difference of two
     samples carries up to a whole point of pure rounding. A measured rise of one
     point could be a true rise of anything from just above zero to just under
     two: 100% relative error, and at a 600s span it spans 0 to 12%/h. So a total
     fitted rise under BURN_RESOLUTION_PCT is not published as a rate at all. It
     is published as a ceiling, which is the one thing the samples do support,
     and the ceiling is still enough to answer the question outright whenever
     even the fastest slope consistent with it resets in time.
   - No reset time. The live Claude capture carries a `weekly_scoped` limit with
     no `resets_at`, and `_shape_window` omits `resetAt` entirely when the
     vendor sends none. With no reset instant there is nothing to project
     against, so the verdict is unknown — not "resets first", which is what
     treating a missing instant as zero would render.

   Samples are stamped with the payload's own `asOf` rather than the viewer
   clock: `asOf` is the moment the percentage was true, and a cached fetch is
   older than the poll that carried it. Stamping at receipt would compress a
   300s-old figure onto "now" and steepen the slope. The verdict is therefore
   computed wholly in payload time; only the countdown shown to the reader comes
   off the viewer's clock, exactly as usageReset() does. */
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
/* The smallest total rise a printed rate may rest on, in whole percentage
   points. One point sits entirely inside the rounding of two integers; two bounds
   the relative error at 50%, which is still coarse enough that every figure this
   row prints is marked as one — `~` for an estimate, `under` for a ceiling — and
   names its own ± in the tooltip. */
const BURN_RESOLUTION_PCT = 2;
const BURN_SLOTS = ["fiveH", "week", "month"];
const burnHistory = new Map();      /* "harness:slot" -> [{t, v}] */
const burnKey = (harness, slot) => harness + ":" + slot;

function burnPush(key, t, v){
  let arr = burnHistory.get(key);
  if(!arr) burnHistory.set(key, arr = []);
  if(arr.length){
    const last = arr[arr.length - 1];
    if(t <= last.t) return;         /* the same fetch, re-rendered */
    /* A fall means the window rolled, or the vendor restated it. Either way the
       samples before the fall measure a window that no longer exists, and a
       slope fitted across the discontinuity would read as a steep decline into
       a wall that is never coming. Start again, and warm up again. */
    if(v < last.v) arr.length = 0;
  }
  arr.push({t, v});
  const cutoff = t - BURN_HISTORY_SEC;
  while(arr.length && arr[0].t < cutoff) arr.shift();
}

/* Called once per payload from usageBody(), so the buffers fill whether or not
   the burn stat is switched on — turning it on is then instant instead of the
   start of another ten-minute wait. In the calm view a collapsed band does not
   render and so does not sample, which is the honest boundary: nothing was on
   screen to go stale, and reopening it reads as warming up. */
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
      burnPush(key, t, Math.max(0, Math.min(100, v)));
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

/* One window's reading: a state naming what kind of answer this is, and a
   verdict naming which way the race goes. Nothing returns a bare number, because
   the caller must not be able to mistake "we cannot tell" for one.
     state    warmup | slow | proj | spent
     verdict  wall (fills first) | safe (resets first) | open (either) | noreset
   `slow` is not "idle": it means the rise is smaller than this span can resolve,
   so the reading is a ceiling rather than a rate. */
function burnRead(key, w){
  /* Already full needs no history and no fit: the bar beside it reads 100%.
     Checked first so a fresh buffer cannot report an exhausted window as
     something that is still warming up. */
  const pct = Number(w && w.pct);
  if(isFinite(pct) && pct >= 100) return {state: "spent"};
  const pts = burnHistory.get(key) || [];
  const n = pts.length;
  const span = n > 1 ? pts[n - 1].t - pts[0].t : 0;
  if(n < BURN_MIN_SAMPLES || span < BURN_MIN_SPAN_SEC) return {state: "warmup", n, span};
  const last = pts[n - 1];
  const level = isFinite(pct) ? Math.max(0, Math.min(100, pct)) : last.v;
  const at = Number(w.resetAt);
  /* A window can arrive with no reset instant at all, and then no rate answers
     the question — the verdict is unknown rather than favourable. */
  const resetAt = isFinite(at) && at > 0 ? at : null;
  /* Non-negative by construction: burnPush() restarts the buffer on any fall, so
     a downward fit would mean a fit over one sample, which cannot get here. */
  const slope = Math.max(0, burnSlope(pts));
  const wallFrom = rate => last.t + (100 - level) / rate;
  if(slope * span < BURN_RESOLUTION_PCT){
    /* Below the resolution floor there is no rate to print, only a ceiling. It
       still settles the race whenever even that ceiling resets in time, which is
       the common case for a window nobody is spending. */
    const ceiling = BURN_RESOLUTION_PCT / span;
    const verdict = resetAt == null ? "noreset"
      : (wallFrom(ceiling) >= resetAt ? "safe" : "open");
    return {state: "slow", span, ceilHour: ceiling * 3600, verdict, resetAt};
  }
  const wallAt = wallFrom(slope);
  /* ±1 whole point on the fitted rise is ±1/span on the slope. The reader is
     told this rather than left to assume the figure is sharper than it is. */
  const read = {state: "proj", span, perHour: slope * 3600,
                bandHour: 3600 / span, wallAt, resetAt};
  if(resetAt == null) return Object.assign(read, {verdict: "noreset"});
  if(wallAt < resetAt) return Object.assign(read, {verdict: "wall"});
  /* The reset wins, so the figure worth having is where the window gets to by
     then rather than a wall this rate does not reach. */
  return Object.assign(read, {verdict: "safe",
    atReset: Math.min(100, Math.round(level + slope * (resetAt - last.t)))});
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
   the tooltip. Two tones, and only these two earn one: `hot` when this window is
   projected to fill before it resets, `warn` when the samples cannot rule that
   out. Every other reading is dim, including the warm-up — an unknown that
   raises a colour is an unknown pretending to be a finding. */
function burnWords(r){
  if(r.state === "spent"){
    return {text: "window spent", tone: "hot",
            title: "This window is already full. The wall is here, not ahead of you."};
  }
  if(r.state === "warmup"){
    return {text: "warming up · " + r.n + " of " + BURN_MIN_SAMPLES, tone: "",
            title: "No projection yet: " + r.n + " reading" + (r.n === 1 ? "" : "s") +
              (r.span > 0 ? " over " + fmtDur(r.span) : "") + ", and a projection needs " +
              BURN_MIN_SAMPLES + " spanning " + fmtDur(BURN_MIN_SPAN_SEC) + ". Quota is" +
              " sampled only while this tab is open with usage on, and the readings are" +
              " lost on reload — so this is unknown, not clear."};
  }
  if(r.state === "slow"){
    /* A ceiling, never a rate: "under 12%/h" is what these samples support, and
       printing the fitted number instead would publish the rounding. */
    const ceiling = "under " + burnRate(r.ceilHour);
    const why = "The rise over " + fmtDur(r.span) + " is too small for a span of" +
      " integer percentages to resolve, so the supported figure is a ceiling — " +
      ceiling + " — rather than a rate.";
    if(r.verdict === "noreset"){
      return {text: ceiling + " · reset unknown", tone: "",
              title: why + " This window also reported no reset time, so there is" +
                " nothing to project it against."};
    }
    if(r.verdict === "safe"){
      return {text: ceiling + " · resets first", tone: "",
              title: why + " Even at that ceiling the window resets in " +
                burnLeft(r.resetAt - nowSec()) + ", before it could fill."};
    }
    return {text: ceiling + " · may fill first", tone: "warn",
            title: why + " That ceiling is not low enough to rule out filling before" +
              " the reset in " + burnLeft(r.resetAt - nowSec()) + ", so leave the tab" +
              " open and the figure sharpens."};
  }
  const rate = "~" + burnRate(r.perHour);
  const band = " The span resolves this to about ±" + burnRate(r.bandHour) +
    ". Fitted over " + fmtDur(r.span) + " of readings taken in this tab.";
  if(r.verdict === "noreset"){
    return {text: rate + " · reset unknown", tone: "warn",
            title: "At " + rate + " this window fills in about " +
              burnLeft(r.wallAt - nowSec()) + ", but the harness reported no reset time," +
              " so whether the reset gets there first cannot be answered." + band};
  }
  if(r.verdict === "wall"){
    const toWall = r.wallAt - nowSec();
    return {text: rate + " · wall in " + burnLeft(toWall), tone: "hot",
            title: "At " + rate + " this window is projected to reach 100% in about " +
              burnLeft(toWall) + ", which is " + burnLeft(r.resetAt - r.wallAt) +
              " before it resets." + band};
  }
  return {text: rate + " · resets first", tone: "",
          title: "At " + rate + " this window reaches about " + r.atReset +
            "% by the time it resets in " + burnLeft(r.resetAt - nowSec()) +
            ", so the reset arrives first." + band};
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
  const win = (label, slot, w) => {
    if(!w || w.pct == null) return "";
    const pct = Math.max(0, Math.min(100, Math.round(Number(w.pct) || 0)));
    const tone = usageTone(pct);
    return `<div class="u-wrow"><span class="u-wlab">${label}</span>` +
      `<span class="cm-track"><span class="cm-fill" style="width:${pct}%;` +
      `background:${tone.bar}"></span></span>` +
      `<span class="u-pct" style="color:${tone.ink}">${pct}%</span>` +
      /* The tooltip keeps the wall-clock time the countdown replaced, so the
         exact moment is still one hover away. */
      `<span class="u-reset" title="resets ${esc(String(w.reset || "at an unknown time"))}">` +
      `↺ ${esc(usageReset(w))}</span>` + burnRow(u.harness, slot, w) + `</div>`;
  };
  /* No bar and no percentage: there is no limit to be a fraction of. The
     label says "used" rather than a window name so it cannot be misread as a
     gauge that happens to be missing its track. */
  const usedRow = u.used == null
    ? ""
    : `<div class="u-wrow"><span class="u-wlab">used</span>` +
      `<span class="u-used">${esc(String(u.used))}</span></div>`;
  const wins = usedRow + (usageCfg.fiveH ? win("5h", "fiveH", u.fiveH) : "") +
    (usageCfg.week ? win("wk", "week", u.week) : "") +
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
  return `<div class="u-entry">${head}${wins}${tail}</div>`;
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

