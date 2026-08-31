let nextData = null;
let nextRefreshFailures = 0;
let nextRefreshInFlight = false;
let nextLastRefreshSuccessAt = null;

function nextRouteToken(route){
  return nextFragmentForRoute(route).slice(3);
}

function nextBreadcrumb(){
  if(NEXT_TOP_LEVEL_VIEWS.has(nextRoute.view)) return "";
  const attention = '<a class="next-crumb" href="#n=attention">Attention</a>';
  const projects = '<a class="next-crumb" href="#n=projects">Projects</a>';
  const project = esc(nextRoute.project);
  if(nextRoute.view === "project"){
    return `${attention}<span aria-hidden="true"> &gt; </span>${projects}` +
      `<span aria-hidden="true"> &gt; </span><span>${project}</span>`;
  }
  const projectRoute = nextRouteToken({view: "project", project: nextRoute.project});
  return `${attention}<span aria-hidden="true"> &gt; </span>${projects}` +
    `<span aria-hidden="true"> &gt; </span><a class="next-crumb" href="#n=${projectRoute}">${project}</a>` +
    `<span aria-hidden="true"> &gt; </span><span>${esc(nextRoute.session)}</span>`;
}

function nextPrimaryNavigation(){
  const links = [
    ["attention", "Attention"],
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
  const session = nextSessionFind(nextRoute.project, nextRoute.session);
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
  const summary = nextData && nextData.summary ? nextData.summary : {};
  const subagents = rows.reduce(
    (total, row) => total + (Array.isArray(row.subagents) ? row.subagents.length : 0),
    0,
  );
  return {
    gates: Number(summary.needs_input) || 0,
    running: Number(summary.working) || 0,
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

function renderNext(){
  const app = document.getElementById("app");
  if(!app) return;
  const counts = nextCounts();
  document.title = nextDocumentTitle();
  const gate = counts.gates > 0
    ? `<button type="button" class="next-gate" data-next-action="needs-input">${counts.gates} need you</button>`
    : "";
  const stalled = nextRefreshNotice();
  const breadcrumb = nextBreadcrumb();
  app.innerHTML = '<header class="next-header">' +
    '<div class="next-header-left">' +
    nextPrimaryNavigation() +
    (breadcrumb ? `<nav class="next-breadcrumb" aria-label="Breadcrumb">${breadcrumb}</nav>` : "") +
    "</div>" +
    '<div class="next-header-right">' +
    `<span class="next-running next-live">${nextStatusDot("live")} ${counts.running} running · ${counts.subagents} subagents</span>` +
    gate +
    '<details class="next-menu"><summary aria-label="More">···</summary>' +
    '<div class="next-menu-items">' +
    '<button type="button" data-next-action="dashboard">dashboard mode <kbd>d</kbd></button>' +
    "</div></details></div></header>" +
    stalled + nextViewBody(counts);
}

function navigateNext(route){
  const fragment = nextFragmentForRoute(route);
  nextRoute = nextRouteFromFragment(fragment);
  if(location.hash !== fragment) location.hash = fragment;
  renderNext();
}

document.addEventListener("click", event => {
  const routeTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-route]")
    : null;
  if(routeTarget && routeTarget.dataset.nextRoute){
    event.preventDefault();
    navigateNext(nextRouteFromFragment(`#n=${routeTarget.dataset.nextRoute}`));
    return;
  }
  const actionTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-action]")
    : null;
  if(!actionTarget) return;
  if(actionTarget.dataset.nextAction === "retry-refresh"){
    event.preventDefault();
    void refreshNext(true);
    return;
  }
  if(actionTarget.dataset.nextAction === "needs-input"){
    navigateNext({view: "attention", project: null, session: null});
  }
  if(actionTarget.dataset.nextAction === "dashboard") location.assign("/");
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
  }else if(String(event.key).toLowerCase() === "d"){
    event.preventDefault();
    location.assign("/");
  }
});

window.addEventListener("hashchange", () => {
  nextRoute = nextRouteFromFragment(location.hash);
  const fragment = nextFragmentForRoute(nextRoute);
  if(location.hash !== fragment) location.hash = fragment;
  renderNext();
});
