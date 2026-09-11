let nextNotifyState = new Map();
let nextNotifyPrimed = false;
let nextNotifiedAsks = new Set();
const nextQuietNudgedAt = new Map();
// Match the native popup_repeat_suppress_sec precedent, not all native gates.
// A later real turn inside this per-tab window can also be suppressed.
const NEXT_QUIET_REPEAT_MS = 600 * 1000;

function nextNotifySupported(){
  return typeof Notification !== "undefined";
}

function nextNotifyPermission(){
  return nextNotifySupported() ? (Notification.permission || "default") : "unsupported";
}

function nextBrowserNotifyOwns(payload){
  return !(payload && payload.native_notify) && nextNotifySupported();
}

function nextRequestNotifyPermission(){
  if(!nextNotifySupported() || !Notification.requestPermission) return;
  const done = () => { if(nextData) renderNext(); };
  let result;
  try{
    result = Notification.requestPermission(done);
  }catch(_error){
    return;
  }
  if(result && typeof result.then === "function") result.then(done, done);
}

function nextNotifyHarnessLabel(payload, key){
  const row = ((payload && payload.harnesses) || []).find(harness => harness.key === key);
  return (row && row.label) || key;
}

function nextNotifyAskLabel(payload, key){
  const row = ((payload && payload.harnesses) || []).find(harness => harness.key === key);
  return (row && row.label) || "";
}

function nextNotifyAsks(payload, fresh){
  const first = fresh[0];
  const one = fresh.length === 1;
  const title = one
    ? `${nextNotifyAskLabel(payload, first.harness) || "An agent"} is asking you`
    : `${fresh.length} questions are waiting for your answer`;
  const projects = [...new Set(fresh.map(ask => ask.project).filter(Boolean))];
  const body = one
    ? `${first.question}${first.project ? ` · ${first.project}` : ""}`
    : (projects.length ? projects.join(" · ") : first.question);
  const tag = one ? `cargento-ask:${first.id}` : "cargento-ask";
  try{
    new Notification(title, {body, tag});
  }catch(_error){
    /* Permission can be revoked while a tab is open. */
  }
}

/* The two transitions worth interrupting a reader for, and the sentence each
   one earns. A gate is a request; a session falling quiet is not, so the two do
   not share a title — "is waiting on you" over a turn that merely stopped is a
   claim about intent that nothing here measured.

   They share the session's tag on purpose: a row that goes quiet and then asks
   a question should replace its own banner rather than stack a second one.

   WHAT THE QUIET NUDGE CAN AND CANNOT SEE. The native lane fires this off
   Claude's own `idle_prompt` hook event. The browser has no hook, only polled
   `state`, so this fires on the working→idle edge — which is the moment the row
   crosses `working_threshold_sec` without new activity, not the moment the
   harness declares itself idle. That makes it near-parity and not parity, and
   the simpler reading is taken deliberately: exact parity needs the
   notification `kind`, which `notifications.handle_payload` drops for the idle
   types, so buying it means a new published field for a nudge that is already
   right about the thing the reader cares about. The title says "has gone
   quiet", which is exactly what was observed, rather than borrowing the gate's
   stronger sentence. */
function nextNotifyEdge(session, previous){
  /* Ahead of the `active` gate deliberately, and it must stay there: the idle
     overlay publishes `active:false` alongside `state:"idle"`, so gating this
     edge on `active` refuses the one transition it exists to report — on the
     default install, since both shipped hook manifests declare `Stop`.
     `previous === "working"` is the liveness check instead. Reordering these
     two to match the branch below reintroduces that: [N-13](docs/design-needs-input.md#n-13).

     Only from `working`. An answered question also lands on idle, and the reader
     was standing right there when it did. An idle row seen for the first time
     is not a transition either — `previous` is undefined then. */
  if(session.state === "idle" && previous === "working"){
    return {title: "has gone quiet", detail: "awaiting your message"};
  }
  if(session.active !== true) return null;
  if(session.state === "needs_input" && previous !== "needs_input"){
    return {title: "is waiting on you", detail: "needs your input"};
  }
  return null;
}

function nextSyncNotifications(payload){
  /* Reported from here because this runs on every payload, which is what makes
     the disagreement check above cheap to act on. */
  nextReportNotifyLane(payload);
  const seen = new Map();
  const now = Date.now();
  for(const [key, issuedAt] of nextQuietNudgedAt){
    if(now - issuedAt >= NEXT_QUIET_REPEAT_MS) nextQuietNudgedAt.delete(key);
  }
  const fire = nextBrowserNotifyOwns(payload) && nextNotifyPermission() === "granted";
  for(const session of nextPayloadSessions(payload)){
    const key = `${session.harness}:${session.sid}`;
    const edge = nextNotifyEdge(session, nextNotifyState.get(key));
    seen.set(key, session.state);
    if(!fire || !nextNotifyPrimed || !edge) continue;
    const quiet = session.state === "idle";
    if(quiet && nextQuietNudgedAt.has(key)) continue;
    try{
      new Notification(`${nextNotifyHarnessLabel(payload, session.harness)} ${edge.title}`, {
        body: `[${session.project}] ${session.state_detail || edge.detail}`,
        tag: key,
      });
      if(quiet) nextQuietNudgedAt.set(key, now);
    }catch(_error){
      /* Permission can be revoked while a tab is open. */
    }
  }

  const asks = payload && payload.ask && Array.isArray(payload.asks) ? payload.asks : [];
  const seenAsks = new Set();
  const fresh = [];
  for(const ask of asks){
    const id = String((ask && ask.id) || "");
    if(!id) continue;
    seenAsks.add(id);
    if(fire && !nextNotifiedAsks.has(id)) fresh.push(ask);
  }
  nextNotifiedAsks = seenAsks;
  if(fresh.length) nextNotifyAsks(payload, fresh);
  nextNotifyState = seen;
  nextNotifyPrimed = true;
}

function nextNotifyControl(payload){
  if(!payload || !nextBrowserNotifyOwns(payload)) return "";
  const permission = nextNotifyPermission();
  if(permission === "granted" || permission === "unsupported") return "";
  if(permission === "denied"){
    return '<span class="next-notify-note" title="Re-enable notifications for this site in ' +
      'your browser settings to be alerted when a session needs you.">notifications blocked</span>';
  }
  return '<button type="button" class="next-notify-button" ' +
    'data-next-action="enable-notifications">Enable notifications</button>';
}

/* Under
   [DEC-19](docs/design-reading-a-session.md#dec-19-the-page-may-report-a-lane-never-a-delivery)
   the page may report that a notification lane EXISTS in it, and may
   never report a delivery. So this posts two scalars about the tab, names no
   session, and is never sent per raise.

   Only a WORKING lane is reported. A tab reporting that it has no lane would
   say nothing true about the board: several tabs can be open, and this one
   being blocked says nothing about another that is not.

   WHEN IT RESENDS, and why it is not a load-time one-shot. The page has no way
   to know the server restarted, and a report that lives in the server's memory
   is gone when it does. So the condition is a DISAGREEMENT: this tab has a lane
   and the payload says none has been reported. That covers the first render,
   the permission grant (which re-renders), and a restart, without a heartbeat
   and without a token for the boot. Once the payload agrees, nothing is sent
   again. */
let nextLaneReportInFlight = false;
let nextLaneReportedThrough = 0;
let nextLaneReportedEver = false;
let nextLaneReportFailures = 0;
/* Three, then stop until something changes. A post only fails when the server
   is broken, and retrying one per poll against a broken server is the heartbeat
   this whole design exists to avoid. */
const NEXT_LANE_REPORT_ATTEMPTS = 3;

function nextLaneReportNeeded(payload){
  if(nextLaneReportInFlight) return false;
  if(!nextNotifySupported() || nextNotifyPermission() !== "granted") return false;
  if(payload && payload.browser_lane === true){
    nextLaneReportFailures = 0;
    return false;
  }
  if(nextLaneReportFailures >= NEXT_LANE_REPORT_ATTEMPTS) return false;
  /* A server that does not publish the key at all is one this page cannot read
     an answer from, so it gets one report and never a second. Treating a
     missing key as a disagreement is the same heartbeat by another route, and
     it is the likelier one: a page from this build against a server from an
     older one sees exactly that. */
  if(!(payload && Object.prototype.hasOwnProperty.call(payload, "browser_lane"))){
    return !nextLaneReportedEver;
  }
  /* Gated on the payload being NEWER than the one we last posted against. The
     page renders many times per collection, and the server's answer cannot
     appear until the next one, so without this every render between the post
     and the next payload posts again. That was the defect: the top-level key
     did not exist either, so `browser_lane` read `undefined` on every payload
     and the page reported on every render. `lane_reported_at` is then always
     "now", and every past raise renders the sentence saying the report arrived
     after it, which is the weakest one and says nothing at all. */
  const generated = Number(payload && payload.generated);
  return !Number.isFinite(generated) || generated > nextLaneReportedThrough;
}

function nextReportNotifyLane(payload){
  if(!nextLaneReportNeeded(payload)) return;
  const generated = Number(payload && payload.generated);
  nextLaneReportInFlight = true;
  const settle = ok => {
    nextLaneReportInFlight = false;
    if(ok){
      nextLaneReportFailures = 0;
      nextLaneReportedEver = true;
      if(Number.isFinite(generated)) nextLaneReportedThrough = generated;
    }else{
      nextLaneReportFailures += 1;
    }
  };
  try{
    fetch("/api/lane", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      /* Two scalars and nothing else. A session here would be refused with a
         400 by the route, which is deliberate on both sides. */
      body: JSON.stringify({supported: true, permission: "granted"}),
    }).then(response => settle(!!(response && response.ok)), () => settle(false));
  }catch(_error){
    settle(false);
  }
}
