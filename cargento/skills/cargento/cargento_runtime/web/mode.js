/* ── calm mode ─────────────────────────────────────────────────────────────
   A second display of the same payload: one dense ledger row per session
   instead of a stack of cards. Every value it shows is derived from
   /api/data, so the two modes cannot disagree about what a session is
   doing. The switch is remembered in localStorage and bound to `c`. */
const DISPLAY_MODE_KEY = "cargento.displayMode";
const CALM_STALE_SEC = 7200;   // an idle session quiet this long is flagged "stale"

let displayMode = "regular";
try{
  const saved = localStorage.getItem(DISPLAY_MODE_KEY);
  if(saved === "calm" || saved === "regular") displayMode = saved;
}catch(e){ /* private mode, or a context with no storage — regular it is */ }

let calmSort = "attention";   /* attention | recent | repo | burn */
let calmStateOnly = null;     /* needs | work | idle */
let calmFlagOnly = false;
/* Rows are identified by sessKey(), the same (harness, sid) pair the rate
   buffers and the notification map use — dedupe_sessions keys on that pair, so
   a bare sid is not unique across harnesses. */
let calmOpenKey = null;       /* the one expanded row */
let calmCursorKey = null;     /* keyboard cursor */
let calmCopyNote = null;      /* {key, text} — transient label after copy id */
let calmScrollTop = 0;        /* ledger scroll survives the 5s re-render */
let calmRevealFocus = false;  /* scroll the cursor into view after this render */
let calmResetScroll = false;  /* re-filtered: the next render starts at the top */

function setDisplayMode(mode){
  if(mode !== "calm" && mode !== "regular" || mode === displayMode) return;
  displayMode = mode;
  try{ localStorage.setItem(DISPLAY_MODE_KEY, mode); }catch(e){ /* nothing to persist to */ }
  calmResetScroll = true;
  if(lastData) render(lastData);
}

