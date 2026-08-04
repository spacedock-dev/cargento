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
      burn, today, cost}            // optional extras, preformatted strings
   Every window slot is optional and a harness fills only the ones it has.
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
  ["burn", "burn rate"], ["today", "tokens today"], ["cost", "cost today"]];

let usageOpen = true;
let usageEnabled = true;
let usageModalSeen = false;
let usageCfgOpen = false;   /* the popover is transient, never persisted */
/* `month` defaults on for the same reason the window slots do: it is the only
   gauge Cursor has, and a row whose single figure is hidden reads as broken. */
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
  const win = (label, w) => {
    if(!w || w.pct == null) return "";
    const pct = Math.max(0, Math.min(100, Math.round(Number(w.pct) || 0)));
    const tone = usageTone(pct);
    return `<div class="u-wrow"><span class="u-wlab">${label}</span>` +
      `<span class="cm-track"><span class="cm-fill" style="width:${pct}%;` +
      `background:${tone.bar}"></span></span>` +
      `<span class="u-pct" style="color:${tone.ink}">${pct}%</span>` +
      `<span class="u-reset" title="${esc(String(w.reset || ""))}">↺ ${esc(String(w.reset || "—"))}</span></div>`;
  };
  /* No bar and no percentage: there is no limit to be a fraction of. The
     label says "used" rather than a window name so it cannot be misread as a
     gauge that happens to be missing its track. */
  const usedRow = u.used == null
    ? ""
    : `<div class="u-wrow"><span class="u-wlab">used</span>` +
      `<span class="u-used">${esc(String(u.used))}</span></div>`;
  const wins = usedRow + (usageCfg.fiveH ? win("5h", u.fiveH) : "") +
    (usageCfg.week ? win("wk", u.week) : "") +
    (usageCfg.month ? win("mo", u.month) : "");
  const extras = [];
  if(usageCfg.burn && u.burn != null) extras.push(["burn", u.burn]);
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

