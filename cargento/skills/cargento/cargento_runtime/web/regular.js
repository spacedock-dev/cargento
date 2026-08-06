function badge(key, active, name, tipSuffix){
  const h = own(HARNESS, key, null) ||
    {code:String(key||"?").slice(0,2).toUpperCase(), name:key};
  const label = name || h.name;
  const tileStyle = active
    ? "background:color-mix(in oklab,var(--accent) 22%,transparent);" +
      "border:1px solid color-mix(in oklab,var(--accent) 48%,transparent)"
    : "border:1px dashed var(--line2)";
  const on = active ? "var(--ink)" : "var(--ink3)";
  const inner = h.icon
    ? `<span class="bico" style="background:${on};-webkit-mask:url('${h.icon}') center/contain no-repeat;mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="bmono" style="color:${on}">${esc(h.code)}</span>`;
  return `<span class="hbadge"><span class="btile" style="${tileStyle}">${inner}</span>` +
         `<span class="htip">${esc(label)}${esc(tipSuffix || "")}</span></span>`;
}

function harnessStrip(harnesses){
  if(!harnesses || !harnesses.length) return "";
  const chips = harnesses.map(h => {
    const healthy = h.discovered && !h.error;
    const suffix = h.error ? " — collector error" : (h.discovered ? "" : " — no data");
    return badge(h.key, healthy, h.label, suffix);
  }).join("");
  return `<span class="hstrip-k">harnesses</span>${chips}`;
}

/* Everything both views must say the same way about the published token rate.
   The figure is a TRAILING MEAN over the server's `rate_window_sec` — at its
   shipped ten minutes it lags a burst by minutes — so no surface built on it may
   be worded as "now". Both views take the window from the payload rather than
   spelling a number into markup, so the wording tracks the arithmetic even when
   the server's window changes underneath it. The fallback is only for a payload
   that predates the field; the shipped server always sends it. */
const RATE_WINDOW_FALLBACK_SEC = 600;
function rateWindowSec(d){
  const v = d ? d.rate_window_sec : null;
  return (typeof v === "number" && isFinite(v) && v > 0) ? v : RATE_WINDOW_FALLBACK_SEC;
}
const rateWindowLabel = d => fmtDur(rateWindowSec(d)) + " mean";

/* Whether a rate carrying this harness's key is a measurement at all, read off
   the harness strip alone. Two facts on the strip row can answer no, and a
   surface that consults only the first calls the second a measured zero:

   - `reports_rate` false. Four of the ten harnesses read no token accounting, so
     their rows carry the same 0 a reporting harness sends for a session that
     generated nothing.
   - `error` set. The collector raised, so whatever the store might have said
     about this harness was never read. `discovered` is still true and
     `reports_rate` still says the harness does report a rate — it is a property
     of the harness, not of the attempt — and taking that promise at face value
     after the read failed is what rendered a failure as a measured zero.

   Both are stated per harness because a session row cannot carry the
   distinction: its 0 is the same 0 either way. `fallback` is the caller's only
   remaining evidence when the strip says nothing — a positive rate proves the
   collector reports one, and a zero stays unknown rather than being promoted to
   a measurement. */
function harnessRateKnown(h, fallback){
  if(!h) return fallback;
  if(h.error) return false;
  return typeof h.reports_rate === "boolean" ? h.reports_rate : fallback;
}

/* The same question about one session, which is the harness's answer plus the
   fallback for a payload whose strip does not carry the row. */
function rateKnown(d, sess){
  const fallback = !!(sess.rate_per_min && isFinite(sess.rate_per_min));
  for(const h of (d && d.harnesses) || []){
    if(h && h.key === sess.harness) return harnessRateKnown(h, fallback);
  }
  return fallback;
}

/* Whether the board's one output figure is a total or a floor, and the words for
   saying so. Two different holes make it a floor, and a surface that knows only
   the first presents the second as exact:

   - an active session whose harness takes no token measurement. It adds the same
     0 to `summary.rate_per_min` as a session that generated nothing, so the sum
     is the measured part of the board's output printed as all of it.
   - a discovered harness whose collector raised. It published no sessions at
     all, so it is missing from the sum and from every session count taken over
     it — a floor note that counts only active sessions therefore finds nothing
     wrong and prints an exact-looking total. The strip's `— collector error`
     badge discloses the failure, but a bare numeral beside it is still a claim
     the payload cannot make. A harness that failed to read is the strongest
     reason a total is a floor, not an exception to it.

   One function for both views, returning text rather than markup, because they
   spend it differently: the tile puts the line under its numeral, calm puts it
   in the footer beside the total. A reader switching modes with `c` must not be
   told the same total is a floor in one and a figure in the other, and wording
   kept separately in each view is wording that drifts. */
function rateFloor(d){
  const active = ((d && d.sessions) || []).filter(x => x.active);
  const unseen = active.filter(x => !rateKnown(d, x));
  const failed = ((d && d.harnesses) || []).filter(h => h && h.error);
  if(!unseen.length && !failed.length) return {mark: "", line: "", tip: ""};
  const hname = (key, label) => own(HARNESS, key, {}).name || label || key;
  const parts = [], tips = [];
  if(unseen.length){
    const names = Array.from(new Set(unseen.map(x => hname(x.harness))));
    parts.push("no rate from " + unseen.length + " of " + active.length +
      " active session" + (active.length === 1 ? "" : "s"));
    tips.push(names.join(", ") + (names.length === 1 ? " reports" : " report") +
      " no token accounting, so what " + (names.length === 1 ? "its" : "their") +
      " sessions are burning is missing from this total — and is not zero.");
  }
  if(failed.length){
    const names = failed.map(h => hname(h.key, h.label));
    parts.push(failed.length + " harness" + (failed.length === 1 ? "" : "es") +
      " could not be read");
    tips.push(names.join(", ") + " failed to collect, so none of " +
      (names.length === 1 ? "its" : "their") +
      " sessions reached this total — unread, not idle.");
  }
  return {mark: "≥ ", line: parts.join(" · ") + " — a floor", tip: tips.join(" ")};
}

/* Which session is burning fastest — the one question this view answers with a
   marker rather than an order, because the card column's order is the server's
   and rate is a value that ticks; re-sorting cards on it would move them under
   the reader every poll for no gain.

   Scoped to the sessions that are working, which is exactly the set this view
   draws cards for. A session that stopped two minutes ago still carries a
   non-zero ten-minute mean, and pointing the reader at that one as the fastest
   would send them to an agent doing nothing.

   Rows whose rate is unknown are neither candidates nor losers: they leave the
   comparison and are counted, so the marker can say how much of the board it
   could not see. A tie keeps every row holding the maximum — picking one winner
   out of equal numbers is a claim the payload does not support.

   The answer is a property of the payload, not of the card being drawn, so it is
   computed once per payload and held. Every card in a column asks the same
   question of the same object, and each poll parses a fresh one, so object
   identity is the cache key: a new payload misses, a re-render of the one
   already on screen (`toggleIdle`, a mode switch) hits. Recomputing it per card
   walked the session list twice and re-scanned the harness strip for every
   session inside that, once per card, every five seconds. Holding the payload
   costs nothing: `lastData` already pins the same object for the whole poll. */
let burnLeadersFor = null;    // {d, leaders} for the last payload asked about
function burnLeaders(d){
  if(burnLeadersFor && burnLeadersFor.d === d) return burnLeadersFor.leaders;
  const working = ((d && d.sessions) || []).filter(x => x.state === "working" && x.active);
  const ranked = working.filter(x => rateKnown(d, x));
  const rateOf = x => (isFinite(x.rate_per_min) ? x.rate_per_min : 0) || 0;
  const racing = burnRacers(ranked, rateOf);
  const best = Math.max(0, ...racing.map(rateOf));
  const leaders = {
    keys: new Set(racing.filter(x => rateOf(x) === best).map(sessKey)),
    /* `ranked` stays the candidate count, not the racer count: it is what the
       marker's tooltip claims a maximum over, and the tooltip only renders where
       a marker does — which is nowhere unless there is a race. */
    best, ranked: ranked.length, unknown: working.length - ranked.length
  };
  burnLeadersFor = {d, leaders};
  return leaders;
}

/* Which of the rows a burn ordering was handed are in a race at all — all of
   them, or none. A board where every measured rate is zero has no fastest
   session: the candidates hold one number between them, so any order over them
   is arbitrary and any marker on one invents a winner. Nothing is dropped for
   being slow; either the set contains a race or it is not a ranking, and the
   caller says what it does with the rows in the second case.

   Both views ask this, of the rows each had already narrowed to the comparable
   ones — the regular view before it marks a card `fastest`, calm before it heads
   a group `fastest first`. Stated once because stating it twice is how the two
   views came to disagree about `fastest` twice: the first time on which rows may
   be compared, the second on whether a comparison of zeroes is one. Takes the
   numbers through an accessor, so neither view has to hand over its row shape. */
function burnRacers(rows, rateOf){
  return Math.max(0, ...rows.map(rateOf)) > 0 ? rows : [];
}

/* How many ranked rows the tile has room for. The cap belongs to the ranked rows
   alone. The unmeasured rows sort last by construction, so a cap taken over both
   groups cut them first, and the row the measured/unmeasured distinction exists
   to draw was the first thing dropped — on any machine running five
   rate-reporting harnesses, which is Claude plus Codex plus Pi plus Gemini plus
   Antigravity. The registry has exactly four harnesses that never report a rate,
   so keeping every unmeasured row still bounds the tile's height. */
const RATE_RANKED_MAX = 5;

function rateTile(d){
  const rate = d.summary.rate_per_min || 0;
  const total = (isFinite(rate) ? rate : 0).toLocaleString();
  const byH = {};
  /* Summed from the sessions the page can read a rate off, through the same
     `rateKnown` the cards use, so the tile and the card under it cannot disagree
     about which sessions were measured. */
  for(const x of d.sessions){
    if(!x.active || !rateKnown(d, x)) continue;
    if(x.rate_per_min && isFinite(x.rate_per_min)){
      byH[x.harness] = (byH[x.harness]||0) + x.rate_per_min;
    }
  }
  /* A discovered harness whose rate nobody measured used to draw a 0 bar next to
     the ones that do, which reads as "this harness is quiet" — for a harness that
     was never measured, or whose collector raised before it could be. It keeps its
     row either way — it is discovered, and hiding it would be a second kind of
     lie — but with a dash, no bar, and last place, so it is never compared
     against a real number. The predicate is `harnessRateKnown`, shared with the
     per-session one, because a strip row saying `reports_rate: true` alongside an
     `error` is exactly the case this row used to render as a measured zero. */
  const split = (d.harnesses || []).filter(h => h.discovered)
    .map(h => ({key:h.key, v:byH[h.key] || 0, err: !!h.error,
      known: harnessRateKnown(h, (byH[h.key] || 0) > 0)}));
  const shown = split.filter(r => r.known).sort((a,b) => b.v - a.v).slice(0, RATE_RANKED_MAX)
    .concat(split.filter(r => !r.known));
  const max = Math.max(1, ...shown.filter(r => r.known).map(r => r.v));
  const rows = shown.length ? `<div class="rate-rows">` + shown.map(r => {
    const v = isFinite(r.v) ? r.v : 0;
    const pct = r.known ? Math.max(v ? 4 : 0, Math.round(v * 100 / max)) : 0;
    /* Two ways to be unmeasured, and the dash must not blame the wrong one: a
       harness that reads no token accounting has no share to know, and one whose
       collector raised has a share nobody got to read. */
    const why = r.err
      ? "this harness could not be read, so its share is unknown — not zero"
      : "this harness reports no token rate, so its share is unknown";
    const tip = r.known ? "" : ` title="${esc(why)}"`;
    return `<div class="rrow"><span class="rrow-badge">${badge(r.key, true)}</span>` +
      `<span class="rrow-bar"><span class="rrow-fill" style="width:${pct}%"></span></span>` +
      `<span class="rrow-v"${tip}>${r.known ? v.toLocaleString() : "—"}</span></div>`;
  }).join("") + `</div>` : "";
  /* What the numeral is: a figure, or a floor. Everything else this change
     touched was taught to tell an absent measurement from a measured zero, and
     the number a reader takes at a glance is the one that must not be left to
     imply completeness. The `≥` carries it where the eye already is; the line
     under it says what is missing, and names the harnesses, so "a floor" is a
     quantity rather than a hedge. Exact when every active session reports a rate
     and every discovered harness was read, which is the common case. Both
     conditions come from `rateFloor`, shared with calm's footer. */
  const floor = rateFloor(d);
  const floorNote = floor.line
    ? `<div class="tile-sub" title="${esc(floor.tip)}">${esc(floor.line)}</div>`
    : "";
  return `<div class="tile"><div class="tile-top"><span class="tile-label">Output rate</span>` +
    `<span class="tile-cap">tok / min · ${esc(rateWindowLabel(d))}</span></div>` +
    `<div class="tile-val">${floor.mark}${total}</div>${floorNote}` +
    `${heroSpark(d)}${rows}</div>`;
}

/* The grid height-matches the two count tiles to the rate tile beside them,
   which left each with a big empty box under a single numeral. Spend it on the
   per-harness split of the very sessions the numeral counted — derived from the
   same list, so the breakdown can never disagree with the total. */
function countTile(label, sub, sessions, alert){
  const byH = new Map();
  for(const x of sessions) byH.set(x.harness, (byH.get(x.harness) || 0) + 1);
  const rows = Array.from(byH.entries())
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .slice(0, 4)
    .map(([key, n]) => {
      const name = own(HARNESS, key, {}).name || key;
      return `<div class="tile-brow">${badge(key, true)}` +
        `<span class="tile-bname">${esc(name)}</span>` +
        `<span class="tile-bnum">${n}</span></div>`;
    }).join("");
  const body = rows
    ? `<div class="tile-break">${rows}</div>`
    : `<div class="tile-none">${esc(sub.empty)}</div>`;
  const val = sessions.length && alert
    ? `<div class="tile-val alert">${sessions.length}</div>`
    : `<div class="tile-val">${sessions.length}</div>`;
  return `<div class="tile"><div class="tile-label">${esc(label)}</div>${val}` +
    `<div class="tile-sub">${esc(sub.line)}</div>${body}</div>`;
}

function sdWindow(stages, idx){
  if(stages.length <= 6 || idx < 0) return stages.slice(0, 6);
  const lo = Math.max(0, idx - 2), hi = Math.min(stages.length, idx + 3);
  const out = [];
  if(lo > 0){ out.push(stages[0]); if(lo > 1) out.push(null); }
  for(let k = lo; k < hi; k++) out.push(stages[k]);
  if(hi < stages.length){ if(hi < stages.length - 1) out.push(null); out.push(stages[stages.length - 1]); }
  return out;
}

const SD_SLUG_MAX = 22;   // matches the .sd-ent column width, in mono ch
const SD_SLUG_HEAD = 8;   // enough to tell one workflow's entities from another's

// Elide the MIDDLE of an over-long entity slug, never the tail. Entity slugs
// within a workflow share a long prefix and differ only at the end
// (`datarecce-recce-cloud-infra-pr-1573` vs `…-pr-1587`), so tail truncation
// renders two different entities as the same string.
function sdSlug(slug){
  if(slug.length <= SD_SLUG_MAX) return slug;
  const tail = SD_SLUG_MAX - SD_SLUG_HEAD - 1;
  return slug.slice(0, SD_SLUG_HEAD) + "…" + slug.slice(slug.length - tail);
}

function sdBlock(sess){
  const sd = sess.spacedock;
  if(!sd) return "";
  const wfs = sd.workflows || [];
  const role = sd.role === "first-officer" ? "first officer" : sd.role;
  if(!wfs.length){
    return `<div class="sd"><div><span class="sd-k">spacedock</span>` +
      `<span class="sd-role">${esc(role)}</span></div></div>`;
  }
  let rows = "";
  for(const wf of wfs){
    const stages = wf.stages || [];
    for(const ent of (wf.entities || [])){
      const idx = stages.indexOf(ent.stage);
      const spine = sdWindow(stages, idx).map(s => s === null
        ? `<span class="sd-gap">…</span>`
        : `<span class="${s === ent.stage && idx >= 0 ? "sd-cur" : "sd-st"}">${esc(s)}</span>`
      ).join(`<span class="sd-arr">→</span>`);
      rows += `<div class="sd-row"><span class="sd-ent${ent.live ? " sd-live" : ""}"` +
        ` title="${esc(ent.slug)}">${esc(sdSlug(ent.slug))}</span>` +
        (ent.cycle ? `<span class="sd-cyc">${esc(ent.cycle)}</span>` : "") +
        `<span class="sd-spine">${spine}</span></div>`;
    }
  }
  const names = wfs.map(w => w.workflow).join(" · ");
  return `<div class="sd"><div><span class="sd-k">spacedock ${esc(names)}</span>` +
    `<span class="sd-role">${esc(role)}</span></div>${rows}</div>`;
}

function turnBlock(t){
  if(!t) return "";
  const warn = t.long ? `<span class="lwarn" tabindex="0" role="note"` +
    ` aria-label="${LONG_TURN_NOTE}">!` +
    `<span class="ltip">${LONG_TURN_NOTE}</span></span>` : "";
  const pct = (t.pct != null) ? `<span class="pct">${t.pct}%</span>` : "";
  /* Both shapes draw a track. A turn with no estimate used to drop the bar
     entirely, so two cards stacked in the same column had different anatomy and
     the reader had to work out which part was missing rather than reading it. */
  const bar = (t.pct != null)
    ? `<div class="turnbar"><span class="turnfill" style="width:${t.pct}%"></span></div>`
    : `<div class="turnbar" title="No past turn ran this long, so there is nothing` +
      ` to estimate against."><span class="turnfill indeterminate"></span></div>`;
  const eta = t.eta_h ? `~${esc(t.eta_h)} left (est)` : "running longer than recent turns";
  return `<div class="turn"><div class="turn-row">` +
    `<span class="turn-txt">this request · ${esc(t.elapsed_h)} elapsed · ${eta}</span>` +
    `<span class="turn-right">${warn}${pct}</span></div>${bar}</div>`;
}

/* Silent when the session tracks no tasks. The board already states once, above
   the fold, that nothing on it uses tracked tasks; repeating the negative on
   every card was a line of chrome per card that told the reader nothing. */
function taskBlock(sess){
  if(!sess.tasks || !sess.tasks.length) return "";
  const order = {in_progress:0, pending:1, completed:2};
  const STATUS = {in_progress:"In progress", pending:"Pending", completed:"Completed"};
  const tasks = [...sess.tasks].sort((a,b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));
  const rows = tasks.map(t => {
    const af = (t.status === "in_progress" && t.activeForm) ? `<div class="task-af">${esc(t.activeForm)}…</div>` : "";
    return `<div class="task"><span class="tstatus st-${esc(t.status)}">${STATUS[t.status] || esc(t.status)}</span>` +
      `<div class="task-body"><div class="task-subj">${esc(t.subject)}</div>${af}</div>` +
      `<div class="task-when">${esc(t.elapsed_h || "")}<br>${esc(t.updated_ago || "")}</div></div>`;
  }).join("");
  return `<div class="tasks">${rows}</div>`;
}

function workingCard(d, sess){
  const known = rateKnown(d, sess);
  const rate = known ? ((isFinite(sess.rate_per_min) ? sess.rate_per_min : 0) || 0) : null;
  const hist = sessRateHistory.get(sessKey(sess));
  /* No sparkline for a harness that reports no rate: the buffer still holds a
     point per poll for it, every one of them the 0 the payload sent, so the line
     would assert a measured silence. Where there is one, its title names two
     different windows, because they are two different windows — the number is a
     mean over the server's rate window, the line is the last five minutes of
     those means as this page received them. */
  const spark = (known && hist && hist.length > 1)
    ? `<span class="rate-spark" title="${rate.toLocaleString()} tok/min` +
      ` (${esc(rateWindowLabel(d))}) · line trails the last ${esc(fmtDur(SPARK_WINDOW_SEC))}">` +
      sparkSVG(hist, nowSec(), 84, 26, false) + `</span>`
    : "";
  /* Three outcomes, not two. A known figure prints — including a real 0, which
     says this request has produced nothing for the whole window and is worth
     knowing. An unknown one says so, because an omitted meter left a blank
     corner that reads as zero. */
  const rateMeter = !sess.active ? ""
    : known
      ? `<div class="rate-meter"><div class="rate-flex">${spark}` +
        `<div><div class="rate-num">${rate.toLocaleString()}</div>` +
        `<div class="rate-lab">tok / min</div></div></div>` +
        `<div class="rate-track"><span class="rate-live"></span></div></div>`
      : `<div class="rate-meter" title="${esc(own(HARNESS, sess.harness, {}).name || sess.harness)}` +
        ` reports no token accounting, so this session's burn is unknown — not zero.">` +
        `<div class="rate-num" style="color:var(--ink3)">—</div>` +
        `<div class="rate-lab">rate unknown</div></div>`;
  /* The marker itself. The label hedges when part of the board could not be
     compared: `fastest` claims a maximum over everything working, `fastest known`
     claims one only over the sessions that report a rate, which is the strongest
     claim available while a rate-less harness is on screen. The tooltip carries
     the window, because "fastest" invites reading as this instant. */
  const lead = burnLeaders(d);
  const leadTip = lead.best.toLocaleString() + " tok/min, the highest of the " + lead.ranked +
    " working session" + (lead.ranked === 1 ? "" : "s") + " that report a rate" +
    (lead.unknown ? ", with " + lead.unknown + " reporting none" : "") +
    " — measured as a " + rateWindowLabel(d) + ", not as this instant";
  const leadPill = lead.keys.has(sessKey(sess))
    ? `<span class="pill" title="${esc(leadTip)}"` +
      ` style="background:color-mix(in oklab,var(--accent) 10%,transparent);color:var(--accent-ink);` +
      `box-shadow:inset 0 0 0 1px color-mix(in oklab,var(--accent) 42%,transparent)">` +
      `${lead.unknown ? "fastest known" : "fastest"}</span>`
    : "";
  const bits = [];
  if(sess.total) bits.push(`${sess.done}/${sess.total} done · ${sess.progress_pct}%`);
  if(sess.eta_h) bits.push(`~${sess.eta_h} left`);
  const bitsLine = bits.length ? `<div class="card-bits">${esc(bits.join(" · "))}</div>` : "";
  const subs = (sess.subagents && sess.subagents.length)
    ? `<div class="subs"><span class="subs-k">subagents</span>` +
      sess.subagents.slice(0,6).map(a => `<span class="subpill"><span class="subdot"></span>${esc(a)}</span>`).join("") +
      (sess.subagents.length > 6 ? `<span class="subs-k">+${sess.subagents.length-6} more</span>` : "") +
      `</div>`
    : "";
  return `<div class="card"><div class="card-top"><div class="card-main">` +
    `<div class="card-headrow"><span class="pill pill-work"><span class="pill-dot"></span>Working</span>` +
    leadPill + badge(sess.harness, true) + `</div>` +
    `<div class="card-title">${esc(sess.title || sess.project)}</div>` +
    `<div class="card-meta">${esc(sess.project)} · ${esc(sess.session)}` +
    `${authorityMeta(sess)}</div>${bitsLine}` +
    `</div>${rateMeter}</div>` +
    `<div class="now"><span class="now-k">now</span>` +
    `<span title="${esc(sess.state_detail)}">${esc(humanTool(sess.state_detail))}</span></div>` +
    turnBlock(sess.turn) + subs + sdBlock(sess) + taskBlock(sess) + `</div>`;
}

function needRow(d, sess){
  const blocked = fmtDur(d.generated - (sess.blocked_since || sess.last_activity));
  return `<div class="need"><div style="min-width:0">` +
    `<div class="need-meta">${badge(sess.harness, true)}${esc(sess.project)} · ${esc(sess.session)}` +
    `${authorityMeta(sess)}</div>` +
    `<div class="need-title">${esc(sess.title || sess.last_prompt || sess.project)}</div>` +
    `<div class="need-detail" title="${esc(sess.state_detail)}">` +
    `${esc(humanTool(sess.state_detail))}</div></div>` +
    `<div style="flex:none"><div class="blocked-k">blocked</div><div class="blocked-v">${esc(blocked)}</div></div></div>`;
}

function idleRow(d, sess){
  const age = fmtDur(d.generated - sess.last_activity);
  const t = sess.total ? ` · ${sess.done}/${sess.total}` : "";
  return `<div class="idle-row"><span class="idle-dot"></span>${badge(sess.harness, false)}` +
    `<span class="idle-title">${esc(sess.title || sess.last_prompt || sess.project)}</span>` +
    /* No authority here on purpose. This cell already truncates at a max-width
       with an ellipsis, so appending would silently swallow it, and an idle
       session is spending nobody's quota. It shows where consumption is live:
       the working card, the needs-input row, and the calm detail panel. */
    `<span class="idle-proj">${esc(sess.project)} · ${esc(sess.session)}${t}</span>` +
    `<span class="idle-age">idle ${esc(age)}</span></div>`;
}

function toggleIdle(){ idleExpanded = !idleExpanded; if(lastData) render(lastData); }

