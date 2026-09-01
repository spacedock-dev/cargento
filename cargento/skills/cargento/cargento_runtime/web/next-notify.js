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

function nextSyncNotifications(payload){
  const seen = new Map();
  const fire = nextBrowserNotifyOwns(payload) && nextNotifyPermission() === "granted";
  for(const session of nextPayloadSessions(payload)){
    const key = `${session.harness}:${session.sid}`;
    seen.set(key, session.state);
    if(!fire || !nextNotifyPrimed) continue;
    if(!session.active || session.state !== "needs_input") continue;
    if(nextNotifyState.get(key) === "needs_input") continue;
    try{
      new Notification(`${nextNotifyHarnessLabel(payload, session.harness)} is waiting on you`, {
        body: `[${session.project}] ${session.state_detail || "needs your input"}`,
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
