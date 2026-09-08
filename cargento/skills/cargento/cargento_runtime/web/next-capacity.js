/* Capacity: the disclosure that gates the quota fetch, and the pace reading.

   Two things live here because they are one user-facing surface. The disclosure
   is what makes the fetch permissible at all, and the strip is what the fetch is
   for; splitting them across parts is how the disclosure went missing once
   already. SECURITY.md's "Usage quota reads" section is the contract for the
   first half and its "Consent and the off switch" paragraph is the promise this
   file keeps.

   The reading itself: a window publishes how much of its budget is spent and
   when it resets, and with its own length that is enough to say how much of its
   TIME is spent too. Both halves come from the vendor in one response, so the
   bar draws the budget as fill and the clock as a tick, and the gap between
   them is the whole reading. Nothing here composes a verdict. [DEC-12](docs/design-usage-quota.md#q-12) settled
   that: A9's single safe-to-start light was cancelled because every quota
   producer signals failure as an empty list, so a composed light reads "safe"
   exactly when Cargento can see nothing, and A5's burn projection produced five
   false greens across three review rounds, every one inside the binary verdict
   and none in the numbers. So the budget's end time and the window's reset time
   sit next to each other and the reader compares them. */

const NEXT_USAGE_CONSENT_KEY = "cargento.next.usage.consent";
/* Slots the strip considers, in order. `month` is here and can carry no pace,
   for the reason `quota.PACE_SLOTS` omits it: Cursor meters money over a
   billing cycle whose start it never publishes, so there is no elapsed fraction
   to read against, and a guessed cycle length would misplace the tick by up to
   three days. The row still shows the level it does have and prints the
   absence of the rest. */
const NEXT_CAPACITY_SLOTS = ["fiveH", "week", "month"];
const NEXT_CAPACITY_SLOT_LABELS = {fiveH: "5-hour", week: "weekly", month: "billing cycle"};
/* How many rows the strip shows before the rest go behind a disclosure. Three,
   matching NEXT_ATTENTION_INITIAL_SECTION_SIZE, because a reader scanning two
   surfaces should not have to learn two different "and N more" rules. */
const NEXT_CAPACITY_INITIAL_ROWS = 3;
/* Below this much of a window elapsed, a projection is arithmetic on almost no
   time: at 2% elapsed one point of drift moves the end time by hours. The row
   still shows it, and states the basis beside it, rather than withholding a
   figure the reader can weigh for themselves. */
const NEXT_CAPACITY_THIN_BASIS = 0.1;

/* Mirrors of `quota.MAX_SCOPED_LIMITS` and `quota.MODEL_LABEL_CAP_CHARS`,
   re-applied here rather than trusted: `usage` reaches the page as untrusted
   collector output, and every other published figure on this surface is
   re-validated at the boundary too. */
const NEXT_CAPACITY_MODEL_ROWS = 8;
const NEXT_CAPACITY_MODEL_LABEL_CHARS = 40;

function nextCapacityModels(raw){
  /* Per-model sub-limits as a label and a level, and deliberately nothing
     else. `quota._scoped_limits` publishes them with no `windowSec`, no
     `resetAt` and no `recent`, so every figure the rest of this file derives —
     elapsed, the tick, `paceRatio`, `endsAt` — is undefined for them, and
     borrowing the weekly row's clock would compose the reading [DEC-12](docs/design-usage-quota.md#q-12) refuses.
     A row with no usable label is dropped rather than published under a
     placeholder, on `_scoped_limit`'s reasoning: an unnamed bar beneath the
     weekly one reads as a second weekly figure disagreeing with the first. */
  if(!Array.isArray(raw)) return [];
  const models = [];
  for(const entry of raw){
    if(!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    /* An integer level, so a measured 0 is kept and a string or a fraction is
       refused rather than coerced into a percentage nobody published. */
    if(!Number.isInteger(entry.pct)) continue;
    const label = typeof entry.label === "string"
      ? entry.label.trim().slice(0, NEXT_CAPACITY_MODEL_LABEL_CHARS)
      : "";
    if(!label) continue;
    models.push({label, pct: entry.pct});
    if(models.length >= NEXT_CAPACITY_MODEL_ROWS) break;
  }
  return models;
}

function nextCapacityModelLine(row){
  /* A sub-line under the row it is a fraction OF, never a row of its own.
     Nothing here is keyed by the label: the container hangs off the row's
     `harness:slot`, which is what the row above already keys on, so a hostile
     label cannot reach a selector or collide with another row's key. */
  if(!row.models || !row.models.length) return "";
  return '<div class="next-capacity-models" data-next-capacity-models=' +
    `"${esc(row.harness)}:${esc(row.slot)}">` +
    "<small>WITHIN THIS WEEKLY BUDGET</small>" +
    row.models.map(model => '<span class="next-capacity-model">' +
      `<b>${esc(model.label)}</b> ${model.pct}%</span>`).join("") +
    "<i>Per-model sub-limits &middot; these publish no clock, so no pace and " +
    "no projected end</i></div>";
}

function nextCapacityDuration(seconds){
  /* `nextFormatDuration` answers null for anything it cannot format, and no
     sentence on this surface may print that. Callers guard the value first, so
     the fallback here is a backstop rather than a rendering path. */
  return nextFormatDuration(seconds) || "an unmeasured span";
}

/* The answer's in-memory tier, for a browser that refuses the write: a
   blocked-site-data profile, a hardened webview, an origin at quota. Without it
   every read re-derived from storage, so the banner re-rendered forever and both
   buttons were inert with no way to dismiss the thing. Storage is still
   consulted first, so a change made in another tab continues to win. */
let nextUsageConsentMemo = null;

// Held by window identity for the life of the tab; see [reader state](docs/design-reader-state.md#the-inventory).
let nextCapacitySelectedKey = "";

function nextUsageConsent(){
  /* Three states, not two. `null` is unanswered, and it is the state the
     disclosure exists for; a missing entry must never read as granted. */
  let raw = null;
  try{
    raw = localStorage.getItem(NEXT_USAGE_CONSENT_KEY);
  }catch(_error){
    /* A private window, or storage the browser refuses. Fall through to the
       memo, and if that is empty too the answer is unanswered, which withholds
       the fetch rather than performing one nobody agreed to. That is the
       direction this whole surface has to fail in. */
    raw = null;
  }
  if(raw === "granted" || raw === "declined") return raw;
  return nextUsageConsentMemo;
}

function nextSetUsageConsent(answer){
  const value = answer === "granted" ? "granted" : "declined";
  nextUsageConsentMemo = value;
  try{
    localStorage.setItem(NEXT_USAGE_CONSENT_KEY, value);
  }catch(_error){ /* held in the memo above; the answer lasts this page only */ }
}

function nextUsageFetchOffered(payload){
  /* The server raises this exactly when a discovered harness would fetch with a
     credential. A disk-read or pushed-receipt producer must not raise it, and a
     test in test_contracts holds that, because the disclosure would then be
     describing a request that never happens. */
  return !!(payload && payload.usage_fetch === true);
}

function nextUsageDisclosure(payload){
  if(!nextUsageFetchOffered(payload) || nextUsageConsent() !== null) return "";
  /* In flow, never a modal overlay. The board stays fully readable behind the
     answer, which is the shape [Q-3](docs/design-usage-quota.md#q-3) records: a
     disclosure read alongside the dashboard rather than in front of it. */
  return '<section class="next-usage-consent" data-next-usage-consent role="region"' +
    ' aria-label="Quota fetch disclosure">' +
    '<p><strong>Read your quota from the vendor?</strong> Cargento can show your Claude Code and ' +
    'Cursor windows. Doing it means reading the credential that harness already stored on this ' +
    'machine and sending it to that vendor, at most once every five minutes, to ask for your ' +
    'usage numbers and nothing else. The credential is never written, logged, or served, and no ' +
    'session content is sent.</p>' +
    '<div class="next-usage-consent-actions">' +
    '<button type="button" data-next-usage-answer="granted">Read my quota</button>' +
    '<button type="button" data-next-usage-answer="declined">No thanks</button>' +
    '</div>' +
    '<p class="next-usage-consent-note">Changeable later from this strip. ' +
    '<code>--no-usage</code> refuses it for a whole run whatever is stored here.</p>' +
    '</section>';
}

function nextUsageSwitch(payload){
  /* The "changed later" half of the contract's promise. Rendered only once the
     question has been answered, so the disclosure above and this control are
     never both on screen claiming the same decision. */
  if(!nextUsageFetchOffered(payload)) return "";
  const consent = nextUsageConsent();
  if(consent === null) return "";
  const granted = consent === "granted";
  return '<p class="next-usage-switch">' +
    `<span>Vendor quota fetch: <strong>${granted ? "on" : "off"}</strong></span>` +
    `<button type="button" data-next-usage-answer="${granted ? "declined" : "granted"}">` +
    `Turn ${granted ? "off" : "on"}</button>` +
    (granted ? "" : '<span class="next-usage-lapse">Windows above are the last cached read and will lapse.</span>') +
    "</p>";
}

function nextCapacityHarnessLabel(harness){
  const labels = nextHarnessLabels();
  const label = labels && labels.get ? labels.get(String(harness || "")) : "";
  return label || String(harness || "") || "Source not identified";
}

function nextCapacityWindow(entry, slot, generated){
  /* One published window as the row's own facts, or null when it carries no
     percentage. Everything derived here is named so the renderer cannot invent
     a figure the payload did not support:
       pct        the vendor's own level
       elapsed    null unless the window published both a length and a reset
       paceRatio  null unless elapsed is known and non-zero
       endsAt     null unless a pace is known and the budget is not already gone
     A null stays null all the way to the column, which prints its absence. */
  if(!entry || entry.state !== "ok") return null;
  const window = entry[slot];
  if(!window || typeof window !== "object" || Array.isArray(window)) return null;
  const pct = Number.isInteger(window.pct) ? window.pct : null;
  if(pct == null) return null;
  const windowSec = nextNumber(window.windowSec);
  const resetAt = nextNumber(window.resetAt);
  const remainingSec = resetAt == null ? null : resetAt - generated;
  let elapsed = null;
  /* A reset already in the past leaves the window UNTIMED, and that guard is
     the whole of what stops this surface publishing a false all-clear. A stale
     disk snapshot describes a window that has since rolled; clamping `elapsed`
     to 1 there made the pace look tiny, which made the projected end enormous,
     which rendered as "lasts, ~123% spare" — a reassurance over evidence that
     had expired, and more spare than there was budget left. That is the shape
     the [quota ruling](docs/design-usage-quota.md#q-12) records, so a passed reset removes the claim instead. The inner
     clamp still serves its other purpose: a vendor clock running ahead of ours
     puts `remainingSec` above `windowSec`, and pinning that to 0 keeps the tick
     on the bar. */
  if(windowSec != null && windowSec > 0 && remainingSec != null && remainingSec > 0){
    elapsed = Math.max(0, Math.min(1, (windowSec - remainingSec) / windowSec));
  }
  const recent = window.recent && typeof window.recent === "object" ? window.recent : null;
  const windowPacePerMin = elapsed != null && elapsed > 0 && windowSec != null && windowSec > 0
    ? pct / (elapsed * windowSec / 60)
    : null;
  /* The raw reading is kept beside the clamped one so a measured zero can be
     told from an absent one. They are different claims: "nothing was spent over
     the last half hour" is evidence, and the page must not print it as "not
     measured". */
  const recentRaw = recent ? nextNumber(recent.pctPerMin) : null;
  const recentPacePerMin = recentRaw == null ? null : Math.max(0, recentRaw);
  const left = Math.max(0, 100 - pct);
  const minutesAt = rate => (rate == null || rate <= 0 ? null : left / rate);
  const windowMinutesLeft = minutesAt(windowPacePerMin);
  return {
    harness: String(entry.harness || ""),
    slot,
    pct,
    elapsed,
    windowSec,
    resetAt,
    remainingSec,
    asOf: nextNumber(entry.asOf),
    thinBasis: elapsed != null && elapsed < NEXT_CAPACITY_THIN_BASIS,
    paceRatio: elapsed != null && elapsed > 0 ? pct / (elapsed * 100) : null,
    windowPacePerMin,
    recentPacePerMin,
    /* Measured at zero, as opposed to not measured at all. */
    recentFlat: recentRaw === 0,
    recentSamples: recent && Number.isInteger(recent.samples) ? recent.samples : null,
    recentSpanSec: recent ? nextNumber(recent.spanSec) : null,
    windowMinutesLeft,
    /* When the budget ends, as an instant on the payload's own clock rather
       than the browser's. Every other time figure on the board is anchored on
       `generated`, and mixing anchors makes two columns of the same row
       disagree by the age of the payload. */
    endsAt: windowMinutesLeft == null ? null : generated + windowMinutesLeft * 60,
    recentMinutesLeft: minutesAt(recentPacePerMin),
    left,
    /* Only on the weekly row, because that is the window they are sub-limits
       of. Hanging them under `fiveH` would make them a fraction of a figure
       they were never measured against. */
    models: slot === "week" ? nextCapacityModels(entry.models) : [],
  };
}

function nextCapacityRows(payload){
  const usage = payload && Array.isArray(payload.usage) ? payload.usage : [];
  const generated = nextNumber(payload && payload.generated);
  if(generated == null) return [];
  const rows = [];
  for(const entry of usage){
    for(const slot of NEXT_CAPACITY_SLOTS){
      const row = nextCapacityWindow(entry, slot, generated);
      if(row) rows.push(row);
    }
  }
  /* Ranked by when the budget ends, earliest first, because that is the binding
     constraint and it is not the largest percentage. A window at 34% used with
     12% elapsed runs dry before one at 88% used with 91% elapsed, and ranking on
     level would put them the wrong way round — which is the whole reason this
     surface exists rather than a sorted list of percentages. Windows that cannot
     be timed sort last, by level, and say why. */
  rows.sort((left, right) => {
    const leftEnd = left.windowMinutesLeft;
    const rightEnd = right.windowMinutesLeft;
    if(leftEnd != null && rightEnd != null && leftEnd !== rightEnd) return leftEnd - rightEnd;
    if(leftEnd != null && rightEnd == null) return -1;
    if(leftEnd == null && rightEnd != null) return 1;
    if(left.pct !== right.pct) return right.pct - left.pct;
    return left.harness.localeCompare(right.harness) || left.slot.localeCompare(right.slot);
  });
  return rows;
}

function nextCapacityClock(stamp, generated){
  /* Wall-clock words for an absolute instant, day-qualified for the reason
     `sessions.format_reset` is: a weekly window's budget can end days out, and
     an hour-of-day alone names the wrong day. Anchored on the payload's
     `generated` rather than on the browser clock, so this column and the
     countdown beside it cannot disagree by the age of the payload. */
  if(stamp == null || generated == null) return "";
  const at = new Date(stamp * 1000);
  const ref = new Date(generated * 1000);
  const hhmm = `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
  if(at.toDateString() === ref.toDateString()) return hhmm;
  const ahead = stamp - generated;
  if(ahead >= 0 && ahead < 7 * 86400){
    return `${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][at.getDay()]} ${hhmm}`;
  }
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][at.getMonth()]} ${String(at.getDate()).padStart(2, "0")}`;
}

function nextCapacityFill(row){
  if(row.paceRatio == null) return " unknown";
  if(row.paceRatio >= 1.5) return " crit";
  if(row.paceRatio >= 1) return " warn";
  return "";
}

function nextCapacityBar(row){
  const label = row.elapsed == null
    ? `${row.pct}% of budget used; this window publishes no clock`
    : `${row.pct}% of budget used, ${Math.round(row.elapsed * 100)}% of the window elapsed`;
  if(row.elapsed == null){
    return `<div class="next-capacity-noclock" role="img" aria-label="${esc(label)}"></div>`;
  }
  return `<div class="next-capacity-bar" role="img" aria-label="${esc(label)}">` +
    `<div class="next-capacity-fill${nextCapacityFill(row)}" style="width:${row.pct}%"></div>` +
    `<div class="next-capacity-tick" style="left:${(row.elapsed * 100).toFixed(2)}%"></div>` +
    "</div>";
}

function nextCapacityEnds(row, generated){
  /* A spent budget is a measurement, not a missing projection. Without its own
     branch it fell through to the clock, and zero minutes left prints the
     present minute, which reads as a deadline still ahead. */
  if(row.left === 0) return '<span class="next-capacity-spent">already spent</span>';
  if(row.windowMinutesLeft == null){
    return '<span class="next-capacity-absent">not projected</span>';
  }
  /* Stated on both verdicts, not only the alarming one. A reassurance resting
     on six minutes of a five-hour window is the half a reader acts on, and
     carrying the qualifier on the alarm alone means comfort is asserted with
     less evidence than concern. */
  const basis = row.thinBasis
    ? ` <em>on ${esc(nextCapacityDuration(row.elapsed * row.windowSec))}</em>`
    : "";
  /* The instant, in every projected shape. Where the budget outlasts the
     window this branch used to return the spare INSTEAD of the time, and that
     is the one place the column stopped being a quantity: observed in one
     render, `claude:fiveH` showed 12:15 while both weekly rows showed
     "lasts, ~N% spare", so the reader could not compare the budget's end with
     the reset that [DEC-12](docs/design-usage-quota.md#q-12) leaves them to adjudicate. The spare is worth saying
     — it is what the window turns over with — but as an annotation on the
     time, never as a replacement for it. */
  const spare = row.remainingSec != null && row.windowMinutesLeft * 60 >= row.remainingSec
    ? Math.max(0, Math.round(row.left - row.windowPacePerMin * (row.remainingSec / 60)))
    : null;
  const slack = spare == null
    ? ""
    : ` <span class="next-capacity-slack">&middot; ~${spare}% spare at reset</span>`;
  return `${esc(nextCapacityClock(row.endsAt, generated))}${basis}${slack}`;
}

function nextCapacityRow(row, generated, selected = false){
  const key = `${row.harness}:${row.slot}`;
  const slotLabel = NEXT_CAPACITY_SLOT_LABELS[row.slot] || row.slot;
  const length = row.windowSec == null ? "no stated length" : nextCapacityDuration(row.windowSec);
  const pace = row.paceRatio == null
    ? '<span class="next-capacity-absent">&mdash;</span>'
    : `${row.paceRatio.toFixed(1)}&times;`;
  const resets = row.remainingSec == null
    ? '<span class="next-capacity-absent">none published</span>'
    : esc(nextCapacityDuration(Math.max(0, row.remainingSec)));
  const usedInk = row.pct >= 80 ? " high" : (row.pct >= 50 ? " mid" : "");
  return '<div class="next-capacity-row" data-next-capacity-row=' +
    `"${esc(row.harness)}:${esc(row.slot)}" data-next-capacity-pick="${esc(key)}">` +
    '<div class="next-capacity-window">' +
    `<button type="button" data-next-capacity-pick="${esc(key)}" ` +
    `data-next-focus="capacity:${esc(key)}" aria-pressed="${selected}" ` +
    `aria-label="Read ${esc(nextCapacityHarnessLabel(row.harness))} ${esc(slotLabel)} window">` +
    `<b>${esc(nextCapacityHarnessLabel(row.harness))}</b>` +
    `<i>${esc(slotLabel)} &middot; ${esc(length)}</i></button></div>` +
    `<div class="next-capacity-pct${usedInk}"><small>USED</small>${row.pct}%</div>` +
    nextCapacityBar(row) +
    `<div class="next-capacity-pace${row.paceRatio != null && row.paceRatio > 1 ? " hot" : ""}">` +
    `<small>PACE</small>${pace}</div>` +
    '<div class="next-capacity-ends"><small>BUDGET ENDS</small>' +
    `${nextCapacityEnds(row, generated)}</div>` +
    `<div class="next-capacity-resets"><small>RESETS</small>${resets}</div>` +
    "</div>" +
    /* Outside the row element, not inside it: the row is a six-column grid and
       a nested block becomes a seventh cell. */
    nextCapacityModelLine(row);
}

function nextCapacityProspect(row, projectSpread){
  /* What the remaining budget buys, in the unit the decision is made in. Two
     measured paces rather than one fitted rate with a synthetic band: both ends
     are observations, and where they disagree that disagreement IS the
     uncertainty. Where only one is measured, one is stated and the other is
     named as absent.

     No concurrency beside it. "Measured while N agents were working" counted
     every working session on the machine, read at render, and stood as the
     provenance of one vendor's historical window average: observed reading 3 on
     the CODEX WEEKLY row while the three were Claude, Antigravity and Codex.
     Scoping the count to the row's harness fixes the vendor and not the clock —
     a count read now cannot describe a span already averaged — so the claim is
     withdrawn rather than narrowed, on the same rule as the recent pace below
     (history: commit 935558e). */
  const parts = [];
  if(row.windowMinutesLeft != null){
    parts.push(`<b>${esc(nextCapacityDuration(row.windowMinutesLeft * 60))}</b> at this window's ` +
      "average pace");
  }
  if(row.recentMinutesLeft != null){
    const span = row.recentSpanSec == null ? "" : ` (last ${nextCapacityDuration(row.recentSpanSec)})`;
    parts.push(`<b>${esc(nextCapacityDuration(row.recentMinutesLeft * 60))}</b> at the recent pace` +
      esc(span));
  }
  if(!parts.length) return "";
  const resets = row.remainingSec == null
    ? ""
    : ` Resets in <b>${esc(nextCapacityDuration(Math.max(0, row.remainingSec)))}</b>.`;
  const spread = projectSpread ? `<p>${projectSpread}</p>` : "";
  /* Three states, because two of them are evidence and only one is absence.
     Keying the caption on the derived minutes collapsed a measured zero into
     "no second reading yet", which the payload contradicts: the ring only
     publishes `recent` once two distinct readings support it. */
  let stale = "";
  if(row.recentMinutesLeft == null && row.asOf != null){
    stale = row.recentFlat
      ? "<small>Recent pace measured at zero: nothing spent across " +
        `${esc(nextCapacityDuration(row.recentSpanSec))} and ` +
        `${row.recentSamples} readings, so nothing is projected from it.</small>`
      : "<small>Recent pace not measured: no second reading yet from this vendor.</small>";
  }
  return '<div class="next-capacity-prospect">' +
    `<p><span class="next-capacity-scope">${esc(nextCapacityHarnessLabel(row.harness))} ` +
    `&middot; ${esc(NEXT_CAPACITY_SLOT_LABELS[row.slot] || row.slot)}</span></p>` +
    `<p>The remaining ${row.left}% buys ${parts.join(", or ")}.${resets}</p>` +
    spread +
    stale +
    "</div>";
}

function nextCapacityView(payload){
  const disclosure = nextUsageDisclosure(payload);
  const rows = nextCapacityRows(payload);
  if(!rows.length){
    nextCapacitySelectedKey = "";
    /* No panel, no placeholder. A machine whose harnesses publish no window has
       nothing withheld from it, and an empty strip reads as a fault. The
       disclosure can still stand alone: it is the reason there is no row yet. */
    return disclosure + nextUsageSwitch(payload);
  }
  const selected = rows.find(row => `${row.harness}:${row.slot}` === nextCapacitySelectedKey) || rows[0];
  const shown = rows.slice(0, NEXT_CAPACITY_INITIAL_ROWS);
  if(!shown.includes(selected)) shown[shown.length - 1] = selected;
  nextCapacitySelectedKey = `${selected.harness}:${selected.slot}`;
  const rest = rows.length - shown.length;
  /* Over the withheld rows only, which is what the sentence beside it claims.
     Counting across every row described the hidden ones with a total that
     included the visible ones. */
  const untimed = rows.filter(row => !shown.includes(row) && row.windowMinutesLeft == null).length;
  const more = rest > 0
    ? '<div class="next-capacity-row next-capacity-more"><i>' +
      `${rest} more ${rest === 1 ? "window" : "windows"}` +
      `${untimed ? `, ${untimed} of them not timed` : ""}</i></div>`
    : "";
  const generated = nextNumber(payload && payload.generated);
  /* Scoped to the harness whose budget the paragraph is about. Drawn across
     every harness it invited a division nobody measured: "the budget buys 50
     minutes" beside a median computed from a different vendor's sessions reads
     as one arithmetic when it is two unrelated ones. */
  const spread = nextCapacityProjectSpread(payload, selected.harness);
  return disclosure +
    '<section class="next-capacity" data-next-capacity aria-label="Capacity">' +
    /* Decorative: every cell below carries its own label, which is what keeps
       the narrow layout readable when this row is hidden. */
    '<div class="next-capacity-head" aria-hidden="true"><span>WINDOW</span><span>USED</span>' +
    '<span>BUDGET AGAINST CLOCK</span><span>PACE</span><span>BUDGET ENDS</span>' +
    '<span>RESETS</span></div>' +
    shown.map(row => nextCapacityRow(row, generated, row === selected)).join("") + more +
    nextCapacityProspect(selected, spread) +
    "</section>" +
    nextUsageSwitch(payload);
}

function nextCapacityProjectSpread(payload, harness){
  /* How long this harness's sessions have actually run in the project that
     consumed the most measured working time, from the state transitions the
     history store already keeps. The comparison is keyed on project and
     duration rather than on a prompt: sizing an unstarted task from its text
     was the issue's original mechanism and the part the board itself called the
     part nobody does well. A project's own past durations are a measurement,
     and publishing the spread with its count refuses to claim the next session
     will match.

     Scoped to one harness because the sentence above it is about one harness's
     budget, and a median drawn from another vendor's sessions invites a
     division nobody measured.

     Working time, not wall time. The store records what CHANGED, so a session's
     span is the sum of the intervals that OPENED with a `working` record and
     were closed by that session's next record. First-to-last would count every
     idle gap in between as run time: a session that worked ten minutes, sat
     overnight and worked ten more would read as fifteen hours. [NUI-11](docs/design-next-ui.md#nui-11) states
     the same rule for the same store, and a session's last record closes
     nothing, so a trailing `working` contributes no span and the figure is
     biased low rather than invented. */
  const history = payload && Array.isArray(payload.history) ? payload.history : [];
  if(!history.length) return "";
  const byKey = new Map();
  for(const record of history){
    const at = nextNumber(record && record.last_activity);
    const sid = String((record && record.sid) || "");
    const project = String((record && record.project) || "");
    const source = String((record && record.harness) || "");
    if(at == null || !sid || !project || source !== harness) continue;
    const key = sid;
    if(!byKey.has(key)) byKey.set(key, {project, records: []});
    byKey.get(key).records.push({at, state: String((record && record.state) || "")});
  }
  const byProject = new Map();
  const unmeasured = new Map();
  for(const session of byKey.values()){
    const ordered = session.records.sort((left, right) => left.at - right.at);
    let worked = 0;
    for(let i = 0; i < ordered.length - 1; i += 1){
      if(ordered[i].state === "working") worked += ordered[i + 1].at - ordered[i].at;
    }
    if(worked > 0){
      if(!byProject.has(session.project)) byProject.set(session.project, []);
      byProject.get(session.project).push(worked);
    }else{
      /* Observed, but with no closed working interval inside the retained
         window. Counted rather than dropped: silently excluding these made the
         range and the median describe a subset while "from N observed" named
         only that subset, so a project of long-running sessions read as a
         project of short ones. */
      unmeasured.set(session.project, (unmeasured.get(session.project) || 0) + 1);
    }
  }
  /* Selected on the SUM of a project's measured intervals, not on how many it
     has. This line sits under "The remaining N% buys ..." and exists to help
     the reader judge whether a project's typical session fits the budget left,
     so the project that consumed the most measured time is the one that
     answers it -- and a sum is a measurement where a tally of sessions is not.
     Counting was the first rule here, and it named a project of three short
     sessions over one that had run for hours.

     The two-session floor stays on the SELECTED project rather than filtering
     the candidates, so a project that leads on the strength of one session
     publishes nothing at all. A range of one is the figure this line must
     never print, and the runner-up is not an answer to which project worked
     most. */
  let best = null;
  for(const [project, list] of byProject){
    const worked = list.reduce((total, span) => total + span, 0);
    if(best == null || worked > best.worked) best = {project, list, worked};
  }
  if(best == null || best.list.length < 2) return "";
  const sorted = [...best.list].sort((a, b) => a - b);
  /* Averaged for an even count, because the floor index returns the upper of
     the two middles and for exactly two sessions that is the maximum: the row
     then printed the same figure as its own range end and called it a median. */
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  const held = unmeasured.get(best.project) || 0;
  const aside = held
    ? ` ${held} more ${held === 1 ? "session has" : "sessions have"} no closed working interval ` +
      `in the retained window and ${held === 1 ? "is" : "are"} not in that figure.`
    : "";
  return `Sessions in <b>${esc(best.project)}</b> have worked ` +
    `${esc(nextCapacityDuration(sorted[0]))} to ` +
    `${esc(nextCapacityDuration(sorted[sorted.length - 1]))}, median ` +
    `<b>${esc(nextCapacityDuration(median))}</b>, from ${sorted.length} observed.${aside}`;
}

function nextUsageAnswerTarget(event){
  return event.target && event.target.closest
    ? event.target.closest("[data-next-usage-answer]")
    : null;
}

document.addEventListener("click", event => {
  const target = event.target && event.target.closest
    ? event.target.closest("[data-next-capacity-pick]") : null;
  if(!target) return;
  const key = String(target.dataset.nextCapacityPick || "");
  if(!nextCapacityRows(nextData)
    .some(row => `${row.harness}:${row.slot}` === key)) return;
  event.preventDefault();
  nextCapacitySelectedKey = key;
  renderNext();
});

document.addEventListener("click", event => {
  const target = nextUsageAnswerTarget(event);
  if(!target) return;
  event.preventDefault();
  nextSetUsageConsent(String(target.dataset.nextUsageAnswer || ""));
  /* Re-render first so the answer is visibly recorded, then poll. Granting
     consent has to reach the server as a parameter on the next request, and
     without this refresh the first fetch would wait out the ordinary poll
     interval and the reader would think the answer did nothing. */
  renderNext();
  refreshNext(true);
});
