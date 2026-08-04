/* Desktop notifications.
   Exactly one layer notifies for a given transition. The server fires an
   OS-level popup where it has a backend and reports that as `native_notify`;
   the page raises its own only when the server cannot. Without that split,
   macOS would pop twice for every blocked session. */
let notifyState = new Map();  /* harness:sid -> last state seen */
let notifyPrimed = false;     /* first payload only records: nothing is "new" yet */

function notifySupported(){ return typeof Notification !== "undefined"; }

function notifyPermission(){
  return notifySupported() ? (Notification.permission || "default") : "unsupported";
}

function browserNotifyOwns(d){ return !(d && d.native_notify) && notifySupported(); }

function requestNotifyPermission(){
  if(!notifySupported() || !Notification.requestPermission) return;
  /* Re-render so the control reflects the new permission. Both the callback
     and promise forms are handled; Safari still uses the callback. */
  const done = () => { if(lastData) render(lastData); };
  let result;
  try{ result = Notification.requestPermission(done); }catch(e){ return; }
  if(result && typeof result.then === "function") result.then(done, done);
}

function syncNotifications(d){
  const seen = new Map();
  const fire = browserNotifyOwns(d) && notifyPermission() === "granted";
  for(const s of d.sessions){
    const key = s.harness + ":" + s.sid;
    seen.set(key, s.state);
    if(!fire || !notifyPrimed) continue;
    /* Same rule the server uses: notify on the transition into needs_input,
       not for every refresh a session spends blocked. */
    if(!s.active || s.state !== "needs_input") continue;
    if(notifyState.get(key) === "needs_input") continue;
    try{
      new Notification("Claude is waiting on you",
        {body: "[" + s.project + "] " + (s.state_detail || "needs your input"),
         tag: key});  /* tag replaces a stale popup instead of stacking */
    }catch(e){ /* permission revoked mid-session, or a headless browser */ }
  }
  notifyState = seen;  /* sessions that disappeared stop being tracked */
  notifyPrimed = true;
}

function notifyControl(d){
  if(!browserNotifyOwns(d)) return "";
  const p = notifyPermission();
  if(p === "granted" || p === "unsupported") return "";
  if(p === "denied"){
    return ` · <span class="notify-note" title="Re-enable notifications for this ` +
      `site in your browser's settings to be alerted when a session needs you.">` +
      `notifications blocked</span>`;
  }
  return ` · <button type="button" class="notify-btn" onclick="requestNotifyPermission()">` +
    `Enable notifications</button>`;
}

