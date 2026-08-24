/* Desktop notifications.
   Exactly one layer notifies for a given transition. The server fires an
   OS-level popup where it has a backend and reports that as `native_notify`;
   the page raises its own only when the server cannot. Without that split,
   macOS would pop twice for every blocked session.

   A question a session registered (`d.asks`) is delivered by the same split,
   keyed on the ask id rather than on a transition: it has no prior state, and it
   leaves the payload for good once answered, withdrawn or expired. macOS silence
   here is not a bug to fix by dropping the browserNotifyOwns gate -- the server
   raised that one natively. */
let notifyState = new Map();  /* harness:sid -> last state seen */
let notifyPrimed = false;     /* first payload only records: nothing is "new" yet */
/* Ask ids already alerted, replaced wholesale from each payload the way
   notifyState is. A Set of ids and not an entry in notifyState because an ask has
   no state to transition through, and its session_id is the asking session's own
   -- a full uuid where a Claude row's sid is the 8-char prefix, and "" for every
   client that sets no session id -- so it is neither unique nor a key any row
   uses. Only the id is. */
let notifiedAsks = new Set();

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

/* The registry's display label for a harness key, falling back to the key.
   The title used to say "Claude" for every row, which was harmless while Claude
   was the only harness that could report needs-input and a lie the moment a
   second one could. The fallback is the key rather than a hardcoded name, so an
   unknown harness reads oddly instead of reading wrongly. */
function harnessLabel(d, key){
  const row = (d.harnesses || []).find(h => h.key === key);
  return (row && row.label) || key;
}

/* The registry's label for an ask's claimed harness, or "" -- never the key.
   harnessLabel above falls back to the key because a row's harness comes from a
   collector and is a registry key by construction. An ask's is written by the
   agent that registered it, and the shipped stdio server sends the literal
   "unknown" for every client but Claude Code, so a key fallback would title the
   common case "unknown is asking you". */
function askLabel(d, key){
  const row = ((d && d.harnesses) || []).find(h => h.key === key);
  return (row && row.label) || "";
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
      new Notification(harnessLabel(d, s.harness) + " is waiting on you",
        {body: "[" + s.project + "] " + (s.state_detail || "needs your input"),
         tag: key});  /* tag replaces a stale popup instead of stacking */
    }catch(e){ /* permission revoked mid-session, or a headless browser */ }
  }
  /* Guarded the way waitingQueue() guards it: syncNotifications runs before render()'s
     own `if(!app)` return, and several page tests feed payloads with no `ask`
     key, where an unguarded loop would throw inside render. */
  const asks = (d && d.ask && Array.isArray(d.asks)) ? d.asks : [];
  const seenAsks = new Set();
  const fresh = [];
  for(const a of asks){
    const id = String((a && a.id) || "");
    if(!id) continue;
    /* Bookkeeping before the guard, as the session loop does at `seen.set`:
       otherwise clicking "Enable notifications" (which re-renders) would dump a
       banner for every question already on the board. */
    seenAsks.add(id);
    if(fire && !notifiedAsks.has(id)) fresh.push(a);
  }
  notifiedAsks = seenAsks;  /* answered, withdrawn and expired ids stop being held */
  if(fresh.length) notifyAsks(d, fresh);
  notifyState = seen;  /* sessions that disappeared stop being tracked */
  notifyPrimed = true;
}

/* One notification per render pass, however many questions arrived in it:
   ask_max_pending is 16, this layer has no cooldown, and sixteen stacked banners
   is not something a reader can act on.

   No notifyPrimed gate, unlike the session loop. A gate recovers -- the row
   cycles out of needs_input and back -- while an ask id is registered once and
   nothing re-registers it, so a question pending when the page first paints has
   no later edge to notify on and would expire having alerted nobody. That is the
   reload, the restored tab, and opening the dashboard because an agent said it
   was about to ask. notifiedAsks alone is enough to stop a repeat. */
function notifyAsks(d, fresh){
  const a = fresh[0];
  const one = fresh.length === 1;
  /* The plural names no harness because several questions can come from several
     of them, and naming one lies about the rest. "An agent" must stay identical
     to notifications.ASK_HARNESS_FALLBACK; the asset contract test is what holds
     the two languages to one sentence. */
  const title = one ? (askLabel(d, a.harness) || "An agent") + " is asking you"
    : fresh.length + " questions are waiting for your answer";
  /* The plural body lists the projects rather than the questions, because
     ask_max_pending is 16 and sixteen questions do not fit a banner. Deduplicated,
     since a fan-out in one repository is the likeliest way to get several at once
     and repeating one path that many times says less than naming it once. Falls
     back to the first question when no ask carries a project at all: an empty
     banner body is worse than a partial one, and `project` is optional. */
  const projects = [...new Set(fresh.map(x => x.project).filter(Boolean))];
  const body = one ? a.question + (a.project ? " \u00b7 " + a.project : "")
    : (projects.length ? projects.join(" \u00b7 ") : a.question);
  /* Per-ask tag in the single case, because two pending questions are two
     independent alerts and a shared tag would have the second banner REPLACE the
     first, which nothing ever raises again. The plural shares one tag, so a later
     batch supersedes a count that is already stale. */
  const tag = one ? "cargento-ask:" + a.id : "cargento-ask";
  try{
    new Notification(title, {body: body, tag: tag});
  }catch(e){ /* permission revoked mid-session, or a headless browser */ }
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

