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
  if(saved === "calm" || saved === "regular" || saved === "session") displayMode = saved;
}catch(e){ /* private mode, or a context with no storage — regular it is */ }

let calmSort = "attention";   /* attention | recent | repo | burn */
let calmStateOnly = null;     /* needs | work | idle */
let calmFlagOnly = false;
/* The trailing idle block starts clipped. Session-only, like regular mode's
   `idleExpanded`: a fresh page should open calm, and nothing else in calm mode
   persists either — `calmSort` does not. */
let calmIdleExpanded = false;
/* Rows are identified by sessKey(), the same (harness, sid) pair the rate
   buffers and the notification map use — dedupe_sessions keys on that pair, so
   a bare sid is not unique across harnesses. */
let calmOpenKey = null;       /* the one expanded row */
let calmCursorKey = null;     /* keyboard cursor */
let calmCopyNote = null;      /* {key, text} — transient label after copy id */
let calmScrollTop = 0;        /* ledger scroll survives the 5s re-render */
let calmRevealFocus = false;  /* scroll the cursor into view after this render */
let calmResetScroll = false;  /* re-filtered: the next render starts at the top */

/* The session view's target: a (harness, sid) key for the session to render.
   Persisted via the URL hash (`#session=<key>`) so the view is routable and
   shareable — a reload or a pasted link restores both the mode and the target.
   Set by clicking a session card or row, or by navigating to a URL with the
   hash; cleared when the view is left (which also clears the hash). */
let sessionViewKey = null;

/* ── URL hash routing for the session view ──────────────────────────────────
   The hash is the persistence layer for the session target: localStorage
   holds the display mode, the hash holds which session. On load, a
   `#session=<harness>:<sid>` hash restores the session view directly. The
   hashchange listener handles browser back/forward between the overview and
   a session view. */
let suppressHashChange = false;
try{
  const m = /session=([^&]+)/.exec(location.hash);
  if(m){
    sessionViewKey = decodeURIComponent(m[1]);
    displayMode = "session";
  }
}catch(e){ /* no location */ }

function syncSessionHash(){
  try{
    if(displayMode === "session" && sessionViewKey){
      const h = "#session=" + encodeURIComponent(sessionViewKey);
      if(location.hash !== h){
        suppressHashChange = true;
        location.hash = h;
      }
    } else if(location.hash && location.hash.indexOf("session=") >= 0){
      suppressHashChange = true;
      location.hash = "";
    }
  }catch(e){ /* no location */ }
}

if(typeof window !== "undefined" && window.addEventListener){
  window.addEventListener("hashchange", () => {
    if(suppressHashChange){ suppressHashChange = false; return; }
    try{
      const m = /session=([^&]+)/.exec(location.hash);
      if(m){
        const key = decodeURIComponent(m[1]);
        if(key !== sessionViewKey || displayMode !== "session"){
          sessionViewKey = key;
          displayMode = "session";
          try{ localStorage.setItem(DISPLAY_MODE_KEY, "session"); }catch(e){}
          calmResetScroll = true;
          if(lastData) render(lastData);
        }
      } else if(displayMode === "session"){
        sessionViewKey = null;
        displayMode = "regular";
        try{ localStorage.setItem(DISPLAY_MODE_KEY, "regular"); }catch(e){}
        calmResetScroll = true;
        if(lastData) render(lastData);
      }
    }catch(e){ /* no location */ }
  });
}

function setDisplayMode(mode){
  if(mode !== "calm" && mode !== "regular" && mode !== "session" || mode === displayMode) return;
  displayMode = mode;
  if(mode !== "session") sessionViewKey = null;
  try{ localStorage.setItem(DISPLAY_MODE_KEY, mode); }catch(e){ /* nothing to persist to */ }
  syncSessionHash();
  calmResetScroll = true;
  if(lastData) render(lastData);
}
