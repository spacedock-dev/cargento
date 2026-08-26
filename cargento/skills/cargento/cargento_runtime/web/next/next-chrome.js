let nextData = null;
let nextOverviewTab = "projects";
let nextRefreshFailures = 0;

function nextRouteToken(route){
  return nextFragmentForRoute(route).slice(3);
}

function nextBreadcrumb(){
  const overview = nextRoute.view === "overview"
    ? "<span>Cargento | overview</span>"
    : '<button type="button" class="next-crumb" data-next-route="overview">Cargento | overview</button>';
  if(nextRoute.view === "overview") return overview;
  const project = esc(nextRoute.project);
  if(nextRoute.view === "project") return `${overview}<span aria-hidden="true"> &gt; </span><span>${project}</span>`;
  const projectRoute = esc(nextRouteToken({view: "project", project: nextRoute.project}));
  return `${overview}<span aria-hidden="true"> &gt; </span>` +
    `<button type="button" class="next-crumb" data-next-route="${projectRoute}">${project}</button>` +
    `<span aria-hidden="true"> &gt; </span><span>${esc(nextRoute.session)}</span>`;
}

function nextRows(){
  return nextData && Array.isArray(nextData.sessions) ? nextData.sessions : [];
}

function nextCounts(){
  const rows = nextRows();
  const summary = nextData && nextData.summary ? nextData.summary : {};
  const projects = new Set(rows.map(row => String(row.project || ""))).size;
  const subagents = rows.reduce(
    (total, row) => total + (Array.isArray(row.subagents) ? row.subagents.length : 0),
    0,
  );
  return {
    gates: Number(summary.needs_input) || 0,
    projects,
    running: Number(summary.working) || 0,
    sessions: rows.length,
    subagents,
  };
}

function nextWindowLabel(){
  if(!nextData || nextData.window_hours == null) return "in this payload window";
  return `in this ${esc(nextData.window_hours)}h window`;
}

function nextOverviewShell(counts){
  const projectsSelected = nextOverviewTab === "projects";
  return '<section class="next-overview" aria-label="Overview">' +
    '<div class="next-tabs-row"><div class="next-tabs" role="tablist">' +
    `<button type="button" role="tab" data-next-tab="projects" aria-selected="${projectsSelected}">projects</button>` +
    `<button type="button" role="tab" data-next-tab="sessions" aria-selected="${!projectsSelected}">sessions</button>` +
    "</div>" +
    `<div class="next-population">${counts.projects} projects · ${counts.sessions} sessions ` +
    `<span>${nextWindowLabel()}</span></div></div>` +
    `<section data-next-body="projects"${projectsSelected ? "" : " hidden"}>` +
    `${projectsSelected ? nextOverviewBody("projects") : ""}</section>` +
    `<section data-next-body="sessions"${projectsSelected ? " hidden" : ""}>` +
    `${projectsSelected ? "" : nextOverviewBody("sessions")}</section>` +
    "</section>";
}

function nextViewBody(counts){
  if(nextRoute.view === "overview") return nextOverviewShell(counts);
  return `<section data-next-view-body="${esc(nextRoute.view)}">` +
    `${nextDetailBody(nextRoute)}</section>`;
}

function renderNext(){
  const app = document.getElementById("app");
  if(!app) return;
  const counts = nextCounts();
  const gate = counts.gates > 0
    ? `<button type="button" class="next-gate" data-next-action="needs-input">${counts.gates} need you</button>`
    : "";
  const stalled = nextRefreshFailures >= 2
    ? '<div class="next-stalled" data-next-state="stalled" role="status">Refresh stalled</div>'
    : "";
  app.innerHTML = '<header class="next-header">' +
    `<nav class="next-breadcrumb" aria-label="Breadcrumb">${nextBreadcrumb()}</nav>` +
    '<div class="next-header-right">' +
    `<span class="next-running">● ${counts.running} running · ${counts.subagents} subagents</span>` +
    gate +
    '<details class="next-menu"><summary aria-label="More">···</summary>' +
    '<div class="next-menu-items">' +
    '<button type="button" data-next-action="projects">projects overview <kbd>p</kbd></button>' +
    '<button type="button" data-next-action="sessions">flat session list <kbd>s</kbd></button>' +
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

function nextSelectProjects(){
  nextOverviewTab = "projects";
  navigateNext({view: "overview", project: null, session: null});
}

function nextSelectSessions(){
  nextOverviewTab = "sessions";
  navigateNext({view: "overview", project: null, session: null});
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
  const tabTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-tab]")
    : null;
  if(tabTarget && ["projects", "sessions"].includes(tabTarget.dataset.nextTab)){
    nextOverviewTab = tabTarget.dataset.nextTab;
    renderNext();
    return;
  }
  const actionTarget = event.target && event.target.closest
    ? event.target.closest("[data-next-action]")
    : null;
  if(!actionTarget) return;
  if(actionTarget.dataset.nextAction === "projects") nextSelectProjects();
  if(["sessions", "needs-input"].includes(actionTarget.dataset.nextAction)) nextSelectSessions();
  if(actionTarget.dataset.nextAction === "dashboard") location.assign("/");
});

document.addEventListener("keydown", event => {
  const tag = event.target && String(event.target.tagName || "").toLowerCase();
  if(event.metaKey || event.ctrlKey || event.altKey) return;
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
      navigateNext({view: "overview", project: null, session: null});
    }
    return;
  }
  if(String(event.key).toLowerCase() === "p"){
    event.preventDefault();
    nextSelectProjects();
  }else if(String(event.key).toLowerCase() === "s"){
    event.preventDefault();
    nextSelectSessions();
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
