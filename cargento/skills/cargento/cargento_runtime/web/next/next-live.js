/* The next bundle needs its own lease. localStorage belongs to the origin, so
   sharing the default bundle's keys would let a preview tab demote the default
   page to its slow fallback poll. Two streams when both bundles are open cost
   one browser connection more, but keep either UI from starving the other. */
const NEXT_LEADER_KEY = "cargento.next.leader";
const NEXT_REVISION_KEY = "cargento.next.revision";
const NEXT_LEASE_RENEW_MS = 2000;
const NEXT_LEASE_STALE_MS = 6000;
const NEXT_FALLBACK_POLL_MS = 20000;
const NEXT_LEGACY_POLL_MS = 5000;
const NEXT_LIVE_SUPPORTED = typeof EventSource !== "undefined";
const NEXT_TAB_ID = Math.random().toString(36).slice(2) + "-" + Date.now();

let nextStreamSource = null;
let nextIsLeader = false;
let nextLastRevision = null;

function nextReadLease(){
  try{ return JSON.parse(localStorage.getItem(NEXT_LEADER_KEY)) || null; }
  catch(_error){ return null; }
}

function nextWriteLease(){
  try{
    localStorage.setItem(NEXT_LEADER_KEY, JSON.stringify({id: NEXT_TAB_ID, ts: Date.now()}));
  }catch(_error){
    /* Private browsing: storage cannot coordinate, so each tab leads itself. */
  }
}

function nextLeaseIsLive(lease){
  return !!lease && Date.now() - Number(lease.ts) < NEXT_LEASE_STALE_MS;
}

function nextElectLeader(){
  const lease = nextReadLease();
  /* A throttled leader can wake after a foreign claim has gone stale. It must
     still yield or two hidden tabs can keep streams while stomping the lease. */
  if(lease && lease.id !== NEXT_TAB_ID && (nextLeaseIsLive(lease) || nextIsLeader)){
    if(nextIsLeader) nextCloseStream();
    nextIsLeader = false;
    return;
  }
  nextWriteLease();
  nextIsLeader = true;
  nextOpenStream();
}

function nextOpenStream(){
  if(nextStreamSource || !NEXT_LIVE_SUPPORTED) return;
  try{
    nextStreamSource = new EventSource("/api/stream");
  }catch(_error){
    nextStreamSource = null;
    return;
  }
  nextStreamSource.addEventListener("error", () => {
    if(!nextStreamSource || nextStreamSource.readyState !== 2) return;
    nextCloseStream();
    nextIsLeader = false;
  });
  nextStreamSource.addEventListener("revision", event => {
    const revision = String(event && event.data || "");
    if(!revision || revision === nextLastRevision) return;
    nextLastRevision = revision;
    try{ localStorage.setItem(NEXT_REVISION_KEY, revision); }catch(_error){ /* no storage */ }
    refreshNext();
  });
}

function nextCloseStream(){
  if(!nextStreamSource) return;
  try{ nextStreamSource.close(); }catch(_error){ /* already gone */ }
  nextStreamSource = null;
}

function nextReleaseLease(){
  if(!nextIsLeader) return;
  try{ localStorage.removeItem(NEXT_LEADER_KEY); }catch(_error){ /* no storage */ }
}

function nextStartLive(){
  window.addEventListener("pagehide", nextReleaseLease);
  document.addEventListener("visibilitychange", () => {
    if(!document.hidden) nextElectLeader();
  });
  window.addEventListener("storage", event => {
    if(!event || event.key !== NEXT_REVISION_KEY) return;
    const revision = String(event.newValue || "");
    if(!revision || revision === nextLastRevision) return;
    nextLastRevision = revision;
    refreshNext();
  });

  renderNext();
  refreshNext();
  if(NEXT_LIVE_SUPPORTED){
    nextElectLeader();
    setInterval(nextElectLeader, NEXT_LEASE_RENEW_MS);
  }
  setInterval(
    refreshNext,
    NEXT_LIVE_SUPPORTED ? NEXT_FALLBACK_POLL_MS : NEXT_LEGACY_POLL_MS,
  );
}

nextStartLive();
