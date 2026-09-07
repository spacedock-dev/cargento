let nextNotifyState = new Map();
let nextNotifyPrimed = false;
let nextNotifiedAsks = new Set();

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
     two to match the branch below reintroduces that: design-needs-input.md N-13.

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
  const seen = new Map();
  const fire = nextBrowserNotifyOwns(payload) && nextNotifyPermission() === "granted";
  for(const session of nextPayloadSessions(payload)){
    const key = `${session.harness}:${session.sid}`;
    const edge = nextNotifyEdge(session, nextNotifyState.get(key));
    seen.set(key, session.state);
    if(!fire || !nextNotifyPrimed || !edge) continue;
    try{
      new Notification(`${nextNotifyHarnessLabel(payload, session.harness)} ${edge.title}`, {
        body: `[${session.project}] ${session.state_detail || edge.detail}`,
        tag: key,
      });
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
