let nextData = null;
let nextAttention = nextAttentionModel({});
let nextRefreshFailures = 0;
let nextRefreshInFlight = false;
let nextRefreshRequest = 0;
let nextLastRefreshSuccessAt = null;
let nextAttentionStatusElement = null;
let nextSessionCopyStatusElement = null;
const nextAttentionExpandedSections = new Set();

function nextCaptureFocus(){
  const app = document.getElementById("app");
  const active = document.activeElement;
  if(!app || !active || typeof app.querySelectorAll !== "function") return null;
  for(const session of app.querySelectorAll("[data-next-session]")){
    if(typeof session.contains !== "function" || !session.contains(active)) continue;
    const sid = String(session.dataset && session.dataset.nextSession || "");
      const harness = String(session.dataset && session.dataset.nextHarness || "");
      if(sid) return {session: sid, harness};
  }
  for(const subject of app.querySelectorAll("[data-next-subject-key]")){
    if(typeof subject.contains !== "function" || !subject.contains(active)) continue;
    const key = String(subject.dataset && subject.dataset.nextSubjectKey || "");
    const section = nextAttentionSectionForKey(nextAttention, key);
    if(key && section) return {key, section};
  }
  for(const toggle of app.querySelectorAll("[data-next-attention-toggle]")){
    if(typeof toggle.contains !== "function" || !toggle.contains(active)) continue;
    const section = String(toggle.dataset && toggle.dataset.nextAttentionToggle || "");
    if(section) return {section, disclosure: true};
  }
  return null;
}

function nextRestoreFocus(snapshot, model){
  if(!snapshot) return;
  const app = document.getElementById("app");
  if(!app || typeof app.querySelectorAll !== "function") return;
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

async function nextCopySessionId(target){
  const sid = String(target && target.dataset && target.dataset.nextCopySession || "");
  const status = nextSessionCopyStatus(document.getElementById("app"));
  try{
    if(!sid || typeof navigator === "undefined" || !navigator.clipboard ||
      typeof navigator.clipboard.writeText !== "function") throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(sid);
    target.dataset.nextCopyState = "copied";
    if(status) status.textContent = `Copied session ID ${sid}`;
  }catch(_error){
    target.dataset.nextCopyState = "failed";
    if(status) status.textContent = "Session ID could not be copied";
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
  const links = [
    ["projects", "Projects"],
    ["sessions", "Sessions"],
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
  const subagents = rows.reduce(
    (total, row) => total + (Array.isArray(row.subagents) ? row.subagents.length : 0),
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

function renderNext(focus = nextCaptureFocus()){
  const app = document.getElementById("app");
  if(!app) return;
  const counts = nextCounts();
  document.title = nextDocumentTitle();
  const gateLabel = counts.gates === 1 ? "reported block" : "reported blocks";
  const gate = counts.gates > 0
    ? `<button type="button" class="next-gate" data-next-action="needs-input">${counts.gates} ${gateLabel}</button>`
    : "";
  const notification = nextNotifyControl(nextData);
  const stalled = nextRefreshNotice();
  const breadcrumb = nextBreadcrumb();
  app.innerHTML = '<header class="next-header">' +
    '<div class="next-header-left">' +
    nextPrimaryNavigation() +
    (breadcrumb ? `<nav class="next-breadcrumb" aria-label="Breadcrumb">${breadcrumb}</nav>` : "") +
    "</div>" +
    '<div class="next-header-right">' +
    `<span class="next-running next-live">${nextStatusDot("live")} ${counts.running} running · ${counts.subagents} subagents</span>` +
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
    ? event.target.closest("[data-next-copy-session]")
    : null;
  if(copyTarget){
    event.preventDefault();
    if(typeof event.stopPropagation === "function") event.stopPropagation();
    void nextCopySessionId(copyTarget);
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
