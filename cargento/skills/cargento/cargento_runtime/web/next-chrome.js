let nextData = null;
let nextAttention = nextAttentionModel({});
let nextRefreshFailures = 0;
let nextRefreshInFlight = false;
let nextRefreshRequest = 0;
let nextLastRefreshSuccessAt = null;
let nextAttentionStatusElement = null;
let nextSessionCopyStatusElement = null;
let nextSessionRaiseStatusElement = null;
let nextRaiseInFlight = false;
const nextAttentionExpandedSections = new Set();

/* Which disclosures the reader has opened, one row of the inventory in
   docs/design-reader-state.md -- which is where the rule for what outlives a
   redraw lives, and why each lane holds a key rather than a node (DRC-4410).

   The list is closed, so an attribute the page never wrote cannot grow the
   set -- the same guard the section keys beside it get. */
const NEXT_DISCLOSURE_KEYS = ["attention-coverage", "session-source-coverage"];
const nextOpenDisclosures = new Set();

function nextDisclosureAttr(key, open){
  /* Emitted after the `class` attribute, never before it: two oracles slice the
     rendered page on the exact `<details class="...">` opening tag, and an
     attribute ahead of the class would hand them a wrong slice instead of
     failing (test_next_attention.py). */
  return open && typeof open.has === "function" && open.has(key) ? " open" : "";
}

// The row's own controls, keyed the way the control-state map keys them
// (docs/design-reader-state.md). The selector and the key function are the same
// pair the render and the stamp use; a third spelling would agree until one of
// them changed.
const NEXT_ROW_CONTROL_LANES = [
  ["[data-next-raise-session]", "nextRaiseSession", nextRaiseStateKey],
  ["[data-next-copy-session]", "nextCopySession", nextCopyStateKey],
];

function nextRowControlKey(app, active){
  for(const [selector, idKey, keyOf] of NEXT_ROW_CONTROL_LANES){
    for(const control of app.querySelectorAll(selector)){
      const dataset = control && control.dataset || {};
      if(!dataset[idKey]) continue;
      const inside = control === active ||
        (typeof control.contains === "function" && control.contains(active));
      if(inside) return keyOf(dataset);
    }
  }
  return "";
}

function nextFocusRowControl(app, key){
  for(const [selector, idKey, keyOf] of NEXT_ROW_CONTROL_LANES){
    for(const control of app.querySelectorAll(selector)){
      const dataset = control && control.dataset || {};
      if(!dataset[idKey] || keyOf(dataset) !== key) continue;
      if(typeof control.focus !== "function") return false;
      control.focus();
      return true;
    }
  }
  return false;
}

// Every focusable control that names itself, swept through ONE fixed selector
// and matched on its dataset. This replaced a growing per-control allowlist:
// the render had been found to discard reader state four times, and each fix
// added a lane of its own. A fifth was due for the <details> summaries, whose
// focus #288 knowingly left unrestored. This lane is what restores them, so the
// disclosure handler's older reason for declining to re-render is now stale and
// says so in place. The identity is never interpolated into a selector, which is
// what the hostile-key test in test_next_chrome.py exists to prove.
function nextFocusKey(app, active){
  for(const target of app.querySelectorAll("[data-next-focus]")){
    const key = String(target.dataset && target.dataset.nextFocus || "");
    if(!key) continue;
    const inside = target === active ||
      (typeof target.contains === "function" && target.contains(active));
    if(inside) return key;
  }
  return "";
}

function nextFocusNamed(app, key){
  for(const target of app.querySelectorAll("[data-next-focus]")){
    if(String(target.dataset && target.dataset.nextFocus || "") !== key) continue;
    if(typeof target.focus !== "function") return false;
    target.focus();
    // A draft input carries an offset as well as an identity. The lane's other
    // two elements are `<summary>`, where there is nothing to place, so this is
    // a no-op for them.
    nextControlsApplyCaret(target);
    return true;
  }
  return false;
}

function nextCaptureFocus(){
  const app = document.getElementById("app");
  const active = document.activeElement;
  if(!app || !active || typeof app.querySelectorAll !== "function") return null;
  // Returned INSTEAD of the container branches rather than alongside them, which
  // is the difference from `control` below. Measured: none of the four elements
  // this lane names sits inside a `[data-next-session]` or a
  // `[data-next-subject-key]`, so there is no container answer to fall back to
  // and nothing is lost by returning early. `control` is carried because a row
  // control genuinely is inside a row, and its row can end.
  const named = nextFocusKey(app, active);
  // Carried alongside whichever container the reader was in rather than instead
  // of it, so a control whose row has ended still falls back to the row's own
  // restoration (DRC-4396).
  const control = nextRowControlKey(app, active);
  if(named) return control ? {named, control} : {named};
  for(const session of app.querySelectorAll("[data-next-session]")){
    if(typeof session.contains !== "function" || !session.contains(active)) continue;
    const sid = String(session.dataset && session.dataset.nextSession || "");
      const harness = String(session.dataset && session.dataset.nextHarness || "");
      if(sid) return control ? {session: sid, harness, control} : {session: sid, harness};
  }
  for(const subject of app.querySelectorAll("[data-next-subject-key]")){
    if(typeof subject.contains !== "function" || !subject.contains(active)) continue;
    const key = String(subject.dataset && subject.dataset.nextSubjectKey || "");
    const section = nextAttentionSectionForKey(nextAttention, key);
    if(key && section) return control ? {key, section, control} : {key, section};
  }
  for(const toggle of app.querySelectorAll("[data-next-attention-toggle]")){
    if(typeof toggle.contains !== "function" || !toggle.contains(active)) continue;
    const section = String(toggle.dataset && toggle.dataset.nextAttentionToggle || "");
    if(section) return {section, disclosure: true};
  }
  return control ? {control} : null;
}

function nextRestoreFocus(snapshot, model){
  if(!snapshot) return;
  const app = document.getElementById("app");
  if(!app || typeof app.querySelectorAll !== "function") return;
  // Tried first and never last. The row branch below lands on the route link,
  // which is where a keyboard reader on a RAISE was being dropped on every
  // revision — and the live lane raises one whenever anything on the machine
  // moves (DRC-4396).
  if(snapshot.named && nextFocusNamed(app, snapshot.named)) return;
  if(snapshot.control && nextFocusRowControl(app, snapshot.control)) return;
  if(snapshot.session){
    for(const session of app.querySelectorAll("[data-next-session]")){
      if(String(session.dataset && session.dataset.nextSession || "") !== snapshot.session ||
        String(session.dataset && session.dataset.nextHarness || "") !== snapshot.harness){
        continue;
      }
      const route = typeof session.querySelector === "function"
        ? session.querySelector(".next-operation-route")
        : null;
      if(route && typeof route.focus === "function") route.focus();
      else if(typeof session.focus === "function") session.focus();
      return;
    }
    return;
  }
  if(!snapshot.section) return;
  if(snapshot.disclosure === true){
    for(const toggle of app.querySelectorAll("[data-next-attention-toggle]")){
      if(String(toggle.dataset && toggle.dataset.nextAttentionToggle || "") !== snapshot.section){
        continue;
      }
      if(typeof toggle.focus === "function") toggle.focus();
      return;
    }
  }
  if(snapshot.key){
  for(const subject of app.querySelectorAll("[data-next-subject-key]")){
    if(String(subject.dataset && subject.dataset.nextSubjectKey || "") !== snapshot.key) continue;
    const link = typeof subject.querySelector === "function" ? subject.querySelector("h3 a") : null;
    if(link && typeof link.focus === "function") link.focus();
    return;
  }
  }
  if(Array.isArray(model && model[snapshot.section]) && model[snapshot.section].length > 0){
    for(const section of app.querySelectorAll("[data-next-attention-section]")){
      if(String(section.dataset && section.dataset.nextAttentionSection || "") !== snapshot.section){
        continue;
      }
      const heading = typeof section.querySelector === "function" ? section.querySelector("h2") : null;
      if(heading && typeof heading.focus === "function") heading.focus();
      return;
    }
  }
  const title = typeof app.querySelector === "function" ? app.querySelector(".next-attention h1") : null;
  if(title && typeof title.focus === "function") title.focus();
}

function nextAttentionAnnouncement(previous, current){
  if(!previous || !current || !previous.counts || !current.counts) return "";
  const keys = ["needs", "risk", "close", "next"];
  if(keys.every(key => previous.counts[key] === current.counts[key])) return "";
  const counts = current.counts;
  const parts = [];
  if(counts.needs) parts.push(`${counts.needs} need you`);
  if(counts.risk) parts.push(`${counts.risk} at risk`);
  if(counts.close) parts.push(`${counts.close} close the loop`);
  if(counts.next) parts.push(`${counts.next} coming next`);
  if(!parts.length) parts.push("0 need you", "0 at risk");
  return `Attention updated: ${parts.join(", ")}`;
}

function nextAttentionStatus(app){
  if(nextAttentionStatusElement) return nextAttentionStatusElement;
  if(!app || typeof app.insertAdjacentElement !== "function") return null;
  const status = document.createElement("p");
  status.id = "next-attention-status";
  status.className = "next-visually-hidden";
  status.role = "status";
  status.ariaLive = "polite";
  status.ariaAtomic = "true";
  if(typeof status.setAttribute === "function"){
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
  }
  app.insertAdjacentElement("afterend", status);
  nextAttentionStatusElement = status;
  return status;
}

function nextAnnounceAttention(message){
  if(!message) return;
  const status = nextAttentionStatus(document.getElementById("app"));
  if(status) status.textContent = message;
}

function nextSessionCopyStatus(app){
  if(nextSessionCopyStatusElement) return nextSessionCopyStatusElement;
  if(!app || typeof app.insertAdjacentElement !== "function") return null;
  const status = document.createElement("p");
  status.id = "next-session-copy-status";
  status.className = "next-visually-hidden";
  if(typeof status.setAttribute === "function"){
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
  }
  app.insertAdjacentElement("afterend", status);
  nextSessionCopyStatusElement = status;
  return status;
}

// The node the click found is not reliably the node the reader is looking at.
// `renderNext` replaces `#app` wholesale on every revision and on a bare interval,
// so a render landing while the action was outstanding orphans the target, and
// writing the answer only there leaves the live row still painting what it was
// painting when the render happened — until the next one, up to
// NEXT_FALLBACK_POLL_MS later, while the live region beside it already said the
// answer. So the state goes to the map, and the controls on the page are re-read
// from it: the same source, and the same result, as the next render (DRC-4392).
function nextStampControlStates(selector, attribute, keyOf){
  const app = document.getElementById("app");
  if(!app || typeof app.querySelectorAll !== "function") return;
  for(const control of app.querySelectorAll(selector)){
    const state = nextControlState(keyOf(control && control.dataset || {}));
    if(state){
      if(typeof control.setAttribute === "function") control.setAttribute(attribute, state);
    }else if(typeof control.removeAttribute === "function"){
      control.removeAttribute(attribute);
    }
  }
}

// One key for the click and for the render, derived from the control's own
// dataset either way. Two spellings of it would agree until one of them changed.
function nextCopyStateKey(dataset){
  return nextControlStateKey(
    dataset.nextCopyCommand ? "command" : "copy",
    dataset.nextCopyHarness,
    dataset.nextCopySession,
  );
}

function nextRaiseStateKey(dataset){
  return nextControlStateKey("raise", dataset.nextRaiseHarness, dataset.nextRaiseSession);
}

function nextCopyState(target, key, state){
  if(target && target.dataset) target.dataset.nextCopyState = state;
  nextRememberControlState(key, state);
  nextStampControlStates("[data-next-copy-session]", "data-next-copy-state", nextCopyStateKey);
}

// One copy lane for both controls. The re-entry command reuses the session-id
// control's state attribute and its live region rather than bringing its own, so
// a reader who has learned one control has learned the other; the only thing that
// differs is which dataset key carries the payload and what the announcement calls
// it. Both share the same fallback: on a context with no `navigator.clipboard` the
// failure is announced and the value stays readable on the control's own title.
async function nextCopyToClipboard(target){
  const dataset = target && target.dataset || {};
  const command = String(dataset.nextCopyCommand || "");
  const sid = String(dataset.nextCopySession || "");
  const value = command || sid;
  const status = nextSessionCopyStatus(document.getElementById("app"));
  // Written to the element for the reader looking at it now, and to the module
  // map for the render that is about to replace it (DRC-4392). The two controls
  // share the lane and the live region but not the cue.
  const key = nextCopyStateKey(dataset);
  try{
    if(!value || typeof navigator === "undefined" || !navigator.clipboard ||
      typeof navigator.clipboard.writeText !== "function") throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(value);
    nextCopyState(target, key, "copied");
    if(status) status.textContent = command ? `Copied ${command}` : `Copied session ID ${sid}`;
  }catch(_error){
    nextCopyState(target, key, "failed");
    if(status){
      status.textContent = command
        ? "Re-entry command could not be copied"
        : "Session ID could not be copied";
    }
  }
}

function nextSessionRaiseStatus(app){
  if(nextSessionRaiseStatusElement) return nextSessionRaiseStatusElement;
  if(!app || typeof app.insertAdjacentElement !== "function") return null;
  const status = document.createElement("p");
  status.id = "next-session-raise-status";
  status.className = "next-visually-hidden";
  if(typeof status.setAttribute === "function"){
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
  }
  app.insertAdjacentElement("afterend", status);
  nextSessionRaiseStatusElement = status;
  return status;
}

// The six states the page can honestly tell apart, because the response is one
// boolean and nothing else: in flight, the boolean true, the boolean false, the
// rate ceiling, a stale capability, and a transport failure. There is no seventh.
// A declined lookup, an unknown session and a command that failed are the same
// false to a caller by contract, so the false wording covers all three rather
// than picking one.
//
// The ceiling wording names neither arm, because the server refuses on two and
// the page cannot tell which: `claim_focus` refuses while `_focus_inflight` is
// set OR when the last raise landed inside `focus_floor_sec`, and
// `release_focus` clears only the first. So a completed raise still holds the
// floor, and it is the arm the old wording did not name that fires in practice.
// Not because a raise is quick: nobody has measured `raise_terminal`'s total, and
// SECURITY.md's 6.1 ms median is one gap inside it — `list-clients` answering to
// `switch-client` being spawned — rather than the whole. It is because
// `nextRaiseInFlight` below refuses a same-tab repeat before it reaches the wire
// at all, so the in-flight arm needs a second tab while the floor is what an
// ordinary double-click hits (DRC-4390). Neither is the floor named: its length is
// `config.focus_floor_sec`'s to change.
//
// SENT and not RAISED. The boolean is the raise command's own exit status —
// `focus.raise_terminal` returns `switch-client`'s return code, and SECURITY.md
// says "true only when the raise command itself exited zero". DRC-4387 recorded a
// raise command exiting zero with nothing coming forward, and `focus.py` says a
// socket raise changes what a tmux client displays without bringing a GUI window
// forward. So the strong reading is unavailable and the announcement takes the
// weaker one.
const NEXT_RAISE_ANNOUNCEMENTS = new Map([
  ["sending", "Raise requested"],
  ["sent", "Raise sent; the terminal switched to this session. Its window may still be behind others."],
  ["declined", "No terminal was raised"],
  ["throttled", "Raise refused: another raise was too recent. Try again in a moment."],
  // The capability is minted per run and `/api/data` needs none, so a restart
  // leaves a board rendering fresh rows above a control that can only be refused,
  // and a reload is the whole remedy. Observed: page `1a6c12…` against server
  // `823939…`, 403 on every click until the tab was reloaded (DRC-4396).
  ["stale", "Raise refused: the dashboard restarted. Reload the page."],
  ["failed", "Raise could not be sent"],
]);

function nextRaiseState(target, state){
  const dataset = target && target.dataset || {};
  if(target && target.dataset) target.dataset.nextRaiseState = state;
  nextRememberControlState(nextRaiseStateKey(dataset), state);
  nextStampControlStates("[data-next-raise-session]", "data-next-raise-state", nextRaiseStateKey);
  const status = nextSessionRaiseStatus(document.getElementById("app"));
  const message = NEXT_RAISE_ANNOUNCEMENTS.get(state);
  if(status && message) status.textContent = message;
}

// The controls already in the document when the click landed. The render
// functions read the same flag, so a revision arriving mid-raise draws them
// unavailable too; this is the arm no render covers, because a raise that
// completes between two renders would otherwise show nothing at all.
function nextRaiseControlsBusy(busy){
  const app = document.getElementById("app");
  if(!app || typeof app.querySelectorAll !== "function") return;
  for(const control of app.querySelectorAll("[data-next-raise-session]")){
    if(busy){
      if(typeof control.setAttribute === "function") control.setAttribute("aria-disabled", "true");
    }else if(typeof control.removeAttribute === "function"){
      control.removeAttribute("aria-disabled");
    }
  }
}

// The copy lane's shape, one route further: a state attribute on the control and
// one live region, so a reader who has learned the copy has learned this too. What
// differs is that this one leaves the machine, so it carries the capability the
// route demands and refuses to send a request without it.
async function nextRaiseTerminal(target){
  const dataset = target && target.dataset || {};
  const sid = String(dataset.nextRaiseSession || "");
  const harness = String(dataset.nextRaiseHarness || "");
  const capability = nextFocusCapability();
  // No capability is the feature off for this run, and no control renders then.
  // Reaching here means the document changed under the page, and a request that
  // could only be refused is not one to send — nor one to explain, because there
  // is no control the reader can have clicked to explain it on.
  if(!sid || !harness || !capability) return;
  // Split from those three deliberately. This arm is a control that did render,
  // that the reader did click, and that the page is refusing; silence there is
  // indistinguishable from a dead button. Folding it into the guard above wrote a
  // state on the no-capability path too, which is the regression the silent arm
  // exists to prevent (DRC-4390).
  if(nextRaiseInFlight){
    nextRaiseState(target, "throttled");
    return;
  }
  nextRaiseInFlight = true;
  nextRaiseControlsBusy(true);
  nextRaiseState(target, "sending");
  try{
    const response = await fetch("/api/focus", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Cargento-Capability": capability},
      body: JSON.stringify({harness, sid}),
    });
    // Two statuses are read before `ok`, and they are the two the reader can act
    // on from here: the ceiling says wait, and a refused capability says reload.
    // Every other refusal says something they cannot act on and takes the generic
    // wording.
    if(response && response.status === 429){
      nextRaiseState(target, "throttled");
      return;
    }
    if(response && response.status === 403){
      nextRaiseState(target, "stale");
      return;
    }
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
    const body = await response.json();
    nextRaiseState(target, body && body.focused === true ? "sent" : "declined");
  }catch(_error){
    nextRaiseState(target, "failed");
  }finally{
    nextRaiseInFlight = false;
    nextRaiseControlsBusy(false);
  }
}

function nextRouteToken(route){
  return nextFragmentForRoute(route).slice(3);
}

function nextBreadcrumb(){
  if(NEXT_TOP_LEVEL_VIEWS.has(nextRoute.view)) return "";
  const sessions = '<a class="next-crumb" href="#n=sessions">Sessions</a>';
  const projects = '<a class="next-crumb" href="#n=projects">Projects</a>';
  const project = esc(nextRoute.project);
  if(nextRoute.view === "project"){
    return `${sessions}<span aria-hidden="true"> &gt; </span>${projects}` +
      `<span class="next-breadcrumb-current-separator" aria-hidden="true"> &gt; </span>` +
      `<span aria-current="page">${project}</span>`;
  }
  const projectRoute = nextRouteToken({view: "project", project: nextRoute.project});
  const session = nextSessionFind(nextRoute.project, nextRoute.harness, nextRoute.session);
  const sessionLabel = session
    ? nextSessionTitle(session, nextSessionAsks(session))
    : "Session";
  return `${sessions}<span aria-hidden="true"> &gt; </span>${projects}` +
    `<span aria-hidden="true"> &gt; </span><a class="next-crumb" href="#n=${projectRoute}">${project}</a>` +
    `<span class="next-breadcrumb-current-separator" aria-hidden="true"> &gt; </span>` +
    `<span aria-current="page">${esc(sessionLabel)}</span>`;
}

function nextPrimaryNavigation(){
  /* Every member of `NEXT_TOP_LEVEL_VIEWS` gets an entry. Attention was absent
     here while the router, the document title and the `a` shortcut all knew
     about it, so it was a whole screen a reader could reach only by typing a
     fragment, pressing a key nothing advertises, or clicking the reported-blocks
     chip, which exists only while a block is reported. NUI-16 decided which
     route leads, not which routes are findable. Appended rather than placed
     first so the two entries a reader has already learned keep their positions. */
  const links = [
    ["projects", "Projects"],
    ["sessions", "Sessions"],
    ["attention", "Attention"],
  ].map(([view, label]) => {
    const current = nextRoute.view === view ? ' aria-current="page"' : "";
    return `<a href="#n=${view}"${current}>${label}</a>`;
  });
  return `<nav aria-label="Primary">${links.join("")}</nav>`;
}

function nextDocumentTitle(){
  if(nextRoute.view === "attention") return "Cargento — Attention";
  if(nextRoute.view === "projects") return "Cargento — Projects";
  if(nextRoute.view === "sessions") return "Cargento — Sessions";
  if(nextRoute.view === "project") return `${nextRoute.project} — Cargento`;
  const session = nextSessionFind(nextRoute.project, nextRoute.harness, nextRoute.session);
  const title = session
    ? nextSessionTitle(session, nextSessionAsks(session))
    : String(nextRoute.session || "Session");
  return `${title} — ${nextRoute.project} — Cargento`;
}

function nextRows(){
  return nextData && Array.isArray(nextData.sessions) ? nextData.sessions : [];
}

function nextCounts(){
  const rows = nextRows();
  const asks = nextOperationsAsks(rows);
  /* Only the ones moving. The chrome's figure is read as "how much is running
     right now", and the published list now also carries teammates that have
     finished and members that have not started — counting those would make the
     header lie in order to close a pill-level gap. The label says `running`
     for the same reason: under the bare word `subagents` a live-only count
     read as a total, so the header could print `0 subagents` above a detail
     panel listing two. */
  const subagents = rows.reduce(
    (total, row) => total + (Array.isArray(row.subagents)
      ? row.subagents.filter(nextSubagentIsLive).length
      : 0),
    0,
  );
  return {
    gates: rows.filter(row => nextOperationsIsBlocked(row, asks)).length,
    running: rows.filter(row => row.state === "working").length,
    subagents,
  };
}

function nextRefreshNotice(){
  if(nextRefreshFailures < 2) return "";
  const failures = nextRefreshFailures === 2
    ? "twice"
    : `${nextRefreshFailures} times`;
  let state = "No data has been received in this tab.";
  if(nextData){
    const elapsed = nextLastRefreshSuccessAt == null
      ? null
      : nextFormatDuration(Math.max(0, (Date.now() - nextLastRefreshSuccessAt) / 1000));
    const age = elapsed == null ? "" : ` Last updated ${elapsed} ago.`;
    state = `Displayed data may be stale.${age}`;
  }
  const retrySeconds = Math.max(1, Math.round(nextRefreshRetryMs() / 1000));
  const disabled = nextRefreshInFlight ? " disabled" : "";
  return '<div class="next-stalled" data-next-state="stalled" role="status">' +
    `<strong>Live refresh failed ${failures} in a row.</strong>` +
    `<span>${state} Retrying automatically every ${retrySeconds}s.</span>` +
    `<button type="button" data-next-action="retry-refresh"${disabled}>Retry now</button></div>`;
}

/* The two reasons `history.RESET_UNREADABLE` and `history.RESET_VERSION` publish,
   listed here so an unrecognised literal draws nothing: the field arrives from a
   file any local process could have replaced, and inventing a sentence about a
   reason this build does not know is how a tampered store gets to write header
   copy. */
const NEXT_HISTORY_RESET_REASONS = {
  unreadable: "The saved file could not be read.",
  version: "It was written by a different version of Cargento.",
};

function nextHistoryResetNotice(){
  const reason = nextData && typeof nextData.history_reset === "string"
    ? nextData.history_reset
    : "";
  const detail = Object.prototype.hasOwnProperty.call(NEXT_HISTORY_RESET_REASONS, reason)
    ? NEXT_HISTORY_RESET_REASONS[reason]
    : "";
  if(!detail) return "";
  /* Which reset it was, not merely that one happened. A corruption reset may be
     the reader's own disk while a version reset is ours, and one message for
     both would satisfy the contract's clause while losing the only thing it is
     there to tell them apart by (D1). */
  return '<div class="next-stalled" data-next-state="history-reset" role="status">' +
    "<strong>The saved history was reset.</strong>" +
    `<span>${esc(detail)} The rail and the delegation figure start from this tab.</span></div>`;
}

function renderNext(focus = nextCaptureFocus()){
  const app = document.getElementById("app");
  if(!app) return;
  // Before the assignment below discards the DOM, which is the ordering rule in
  // docs/design-reader-state.md and the reason a draft is read first: it is the
  // one lane that cannot be rebuilt from a key.
  nextControlsCaptureDrafts();
  const counts = nextCounts();
  document.title = nextDocumentTitle();
  const gateLabel = counts.gates === 1 ? "reported block" : "reported blocks";
  const subagentLabel = counts.subagents === 1 ? "subagent running" : "subagents running";
  const gate = counts.gates > 0
    ? `<button type="button" class="next-gate" data-next-action="needs-input">${counts.gates} ${gateLabel}</button>`
    : "";
  const notification = nextNotifyControl(nextData);
  const stalled = nextRefreshNotice() + nextHistoryResetNotice();
  const breadcrumb = nextBreadcrumb();
  app.innerHTML = '<header class="next-header">' +
    '<div class="next-header-left">' +
    nextPrimaryNavigation() +
    (breadcrumb ? `<nav class="next-breadcrumb" aria-label="Breadcrumb">${breadcrumb}</nav>` : "") +
    "</div>" +
    '<div class="next-header-right">' +
    `<span class="next-running next-live">${nextStatusDot("live")} ${counts.running} running · ${counts.subagents} ${subagentLabel}</span>` +
    gate + notification + "</div></header>" +
    stalled + nextViewBody(counts);
  nextAttentionStatus(app);
  nextRestoreFocus(focus, nextAttention);
}

function navigateNext(route){
  const fragment = nextFragmentForRoute(route);
  nextRoute = nextRouteFromFragment(fragment);
  if(location.hash !== fragment) location.hash = fragment;
  renderNext();
}

document.addEventListener("click", event => {
  const copyTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-copy-session],[data-next-copy-command]")
    : null;
  if(copyTarget){
    event.preventDefault();
    if(typeof event.stopPropagation === "function") event.stopPropagation();
    void nextCopyToClipboard(copyTarget);
    return;
  }
  const raiseTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-raise-session]")
    : null;
  if(raiseTarget){
    event.preventDefault();
    if(typeof event.stopPropagation === "function") event.stopPropagation();
    void nextRaiseTerminal(raiseTarget);
    return;
  }
  const routeTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-route]")
    : null;
  if(routeTarget && routeTarget.dataset.nextRoute){
    event.preventDefault();
    navigateNext(nextRouteFromFragment(`#n=${routeTarget.dataset.nextRoute}`));
    return;
  }
  const disclosureTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-attention-toggle]")
    : null;
  if(disclosureTarget){
    const section = String(disclosureTarget.dataset &&
      disclosureTarget.dataset.nextAttentionToggle || "");
    if(["needs", "risk", "close", "next"].includes(section)){
      event.preventDefault();
      if(nextAttentionExpandedSections.has(section)){
        nextAttentionExpandedSections.delete(section);
      }else{
        nextAttentionExpandedSections.add(section);
      }
      renderNext({section, disclosure: true});
    }
    return;
  }
  const summaryTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-disclosure]")
    : null;
  if(summaryTarget){
    const key = String(summaryTarget.dataset && summaryTarget.dataset.nextDisclosure || "");
    if(NEXT_DISCLOSURE_KEYS.includes(key)){
      /* Deliberately not prevented and deliberately not re-rendered. The
         browser's own toggle is what the reader sees, and it runs after this
         handler; recording the flip only teaches the next render what to
         re-emit. The older reason, that a re-render would replace the summary
         under a keyboard reader's focus with nothing to restore it, no longer
         holds: both summaries now carry a `data-next-focus` and the generic
         lane restores them. What stands is that re-rendering here would fight
         the browser's own toggle for no gain. */
      if(nextOpenDisclosures.has(key)) nextOpenDisclosures.delete(key);
      else nextOpenDisclosures.add(key);
    }
    return;
  }
  const actionTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-action]")
    : null;
  if(!actionTarget) return;
  if(actionTarget.dataset.nextAction === "enable-notifications"){
    event.preventDefault();
    nextRequestNotifyPermission();
    return;
  }
  if(actionTarget.dataset.nextAction === "retry-refresh"){
    event.preventDefault();
    void refreshNext(true);
    return;
  }
  if(actionTarget.dataset.nextAction === "needs-input"){
    navigateNext({view: "attention", project: null, session: null});
  }
});

document.addEventListener("keydown", event => {
  const tag = event.target && String(event.target.tagName || "").toLowerCase();
  if(event.metaKey || event.ctrlKey || event.altKey) return;
  const routeTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-route]")
    : null;
  const routeRole = routeTarget && routeTarget.getAttribute
    ? routeTarget.getAttribute("role")
    : "";
  if(routeRole === "link" && ["Enter", " ", "Spacebar"].includes(event.key)){
    event.preventDefault();
    navigateNext(nextRouteFromFragment(`#n=${routeTarget.dataset.nextRoute}`));
    return;
  }
  if(nextControlsHandleKeydown(event)) return;
  if(nextWorkstreamToggleTarget(event) && ["Enter", " ", "Spacebar"].includes(event.key)){
    event.preventDefault();
    nextWorkstreamToggle();
    return;
  }
  if(["input", "select", "textarea"].includes(tag)) return;
  if(event.key === "Escape"){
    if(nextRoute.view === "session"){
      event.preventDefault();
      navigateNext({view: "project", project: nextRoute.project, session: null});
    }else if(nextRoute.view === "project"){
      event.preventDefault();
      navigateNext({view: "attention", project: null, session: null});
    }
    return;
  }
  if(String(event.key).toLowerCase() === "a"){
    event.preventDefault();
    navigateNext({view: "attention", project: null, session: null});
  }else if(String(event.key).toLowerCase() === "p"){
    event.preventDefault();
    navigateNext({view: "projects", project: null, session: null});
  }else if(String(event.key).toLowerCase() === "s"){
    event.preventDefault();
    navigateNext({view: "sessions", project: null, session: null});
  }
});

window.addEventListener("hashchange", () => {
  nextRoute = nextRouteFromFragment(location.hash);
  const fragment = nextFragmentForRoute(nextRoute);
  if(location.hash !== fragment) location.hash = fragment;
  renderNext();
});
