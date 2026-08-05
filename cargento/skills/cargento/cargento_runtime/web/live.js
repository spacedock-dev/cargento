/* Live delivery: one SSE stream per browser, elected across tabs.

   One stream per *browser*, not per tab, and that is the whole point of the
   election. Browsers allow about six concurrent connections to one origin, and
   an EventSource holds one for the life of the tab. Six dashboard tabs would
   exhaust the pool, and the seventh tab's fetches would then queue forever
   rather than fail — so nothing would ever reject, no failure counter would
   fire, and the board would sit frozen behind a healthy-looking live dot.

   The lease is a localStorage key carrying a tab id and a timestamp. The holder
   renews it; everyone else watches it go stale and takes over. Followers learn
   about new revisions through a second key, because a storage event fires in
   every *other* tab, which is exactly the fan-out this needs and costs no
   connection at all.

   A slow poll runs regardless, as a safety net. No bug in the election or the
   stream may leave a dashboard frozen, and a poll that is twenty seconds apart
   is cheap insurance against one that never happens. */
const LEADER_KEY = "cargento.leader";
const REVISION_KEY = "cargento.revision";
const LEASE_RENEW_MS = 2000;
/* Three renewals. Two would call a leader dead for one missed tick under load. */
const LEASE_STALE_MS = 6000;
const FALLBACK_POLL_MS = 20000;
const LEGACY_POLL_MS = 5000;
const LIVE_SUPPORTED = typeof EventSource !== "undefined";
const TAB_ID = Math.random().toString(36).slice(2) + "-" + Date.now();

let refreshTimer = null;
let leaderTimer = null;
let streamSource = null;
let isLeader = false;
let lastRevision = null;

function readLease(){
  try{ return JSON.parse(localStorage.getItem(LEADER_KEY)) || null; }
  catch(e){ return null; }  /* absent, unparseable, or no storage at all */
}

function writeLease(){
  try{ localStorage.setItem(LEADER_KEY, JSON.stringify({id: TAB_ID, ts: Date.now()})); return true; }
  catch(e){ return false; }  /* private browsing: every tab leads itself */
}

function leaseIsLive(lease){
  return !!lease && Date.now() - Number(lease.ts) < LEASE_STALE_MS;
}

/* Claim or renew the lease. Called on load and on every renew tick, so a tab
   that starts as a follower becomes the leader the moment the holder stops
   renewing — a closed tab, a sleeping laptop, a crashed renderer. */
function electLeader(){
  if(serverStopped) return;
  const lease = readLease();
  /* Yield on any foreign lease that is either live or newer than our own claim.
     Checking only `leaseIsLive` was wrong: a tab throttled to one wake-up a
     minute (Chrome does this after five minutes hidden) reads a stale foreign
     lease, falls through to writeLease, and `if(!isLeader)` then suppresses the
     only demotion. Two hidden tabs stomp each other's lease forever and both
     keep a stream, which is precisely the connection exhaustion this module
     exists to prevent. */
  if(lease && lease.id !== TAB_ID && (leaseIsLive(lease) || isLeader)){
    if(isLeader) closeStream();
    isLeader = false;
    return;
  }
  writeLease();
  isLeader = true;
  /* Outside any `!isLeader` guard so a leader whose stream died reopens it. */
  openStream();
}

function openStream(){
  if(streamSource || !LIVE_SUPPORTED || serverStopped) return;
  try{ streamSource = new EventSource("/api/stream"); }
  catch(e){ streamSource = null; return; }  /* refused, or past the server's cap */
  /* A non-200 or wrong-content-type reply fails the connection permanently:
     readyState goes to CLOSED and the browser must not reconnect. That is
     exactly what a 503 past the server's client cap looks like, so without this
     the tab would hold a dead source, keep the lease, and never recover. */
  streamSource.addEventListener("error", () => {
    if(!streamSource || streamSource.readyState !== 2) return;  /* 2 = CLOSED */
    closeStream();
    isLeader = false;  /* let another tab try; this one retries on its next tick */
  });
  streamSource.addEventListener("revision", ev => {
    /* Ignored rather than acted on: EventSource replays its last id when it
       reconnects, so the first event after a drop is usually one already seen,
       and refetching for it would cost a request per reconnect. */
    const revision = String((ev && ev.data) || "");
    if(!revision || revision === lastRevision) return;
    lastRevision = revision;
    /* Followers hear this; the writing tab does not, which is what makes a
       storage key the right fan-out and not a loop. */
    try{ localStorage.setItem(REVISION_KEY, revision); }catch(e){ /* no storage */ }
    refresh();
  });
}

function closeStream(){
  if(!streamSource) return;
  try{ streamSource.close(); }catch(e){ /* already gone */ }
  streamSource = null;
}

/* Terminal: the stop control calls this, and nothing restarts it. */
function stopLive(){
  releaseLease();
  closeStream();
  if(leaderTimer !== null){ clearInterval(leaderTimer); leaderTimer = null; }
  if(refreshTimer !== null){ clearInterval(refreshTimer); refreshTimer = null; }
}

function releaseLease(){
  if(!isLeader) return;
  try{ localStorage.removeItem(LEADER_KEY); }catch(e){ /* no storage */ }
}

function startLive(){
  /* Handing the lease back makes takeover near-instant instead of costing the
     full stale window, and re-electing when a tab is shown narrows the window
     in which a throttled leader still holds one. */
  window.addEventListener("pagehide", releaseLease);
  document.addEventListener("visibilitychange", () => {
    if(!document.hidden) electLeader();
  });
  window.addEventListener("storage", ev => {
    if(serverStopped || !ev || ev.key !== REVISION_KEY) return;
    const revision = String(ev.newValue || "");
    if(!revision || revision === lastRevision) return;
    lastRevision = revision;
    refresh();
  });
  refresh();
  if(LIVE_SUPPORTED){
    electLeader();
    leaderTimer = setInterval(electLeader, LEASE_RENEW_MS);
  }
  /* Without EventSource there is no stream to fall back from, so the old
     cadence is the whole mechanism rather than a safety net. */
  refreshTimer = setInterval(refresh, LIVE_SUPPORTED ? FALLBACK_POLL_MS : LEGACY_POLL_MS);
}

startLive();
