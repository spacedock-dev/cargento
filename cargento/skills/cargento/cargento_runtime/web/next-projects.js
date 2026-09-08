function nextProjectProgress(sessions){
  const total = sessions.reduce((sum, session) => sum + Math.max(0, nextFiniteNumber(session.total)), 0);
  if(total <= 0) return "";
  const done = sessions.reduce((sum, session) => sum + Math.max(0, nextFiniteNumber(session.done)), 0);
  return `<progress class="next-project-progress-bar" value="${esc(Math.min(done, total))}" ` +
    `max="${esc(total)}" aria-label="${esc(done)} of ${esc(total)} tasks done"></progress>` +
    `<span>${esc(done)} of ${esc(total)} done</span>`;
}

function nextProjectValue(text, known, className = ""){
  return `<span class="next-project-value ${known ? "next-project-value--known" : "next-project-value--absent"} ${className}">${esc(text)}</span>`;
}

function nextProjectSessionLine(session){
  const route = nextRouteToken({view: "session", project: session.project,
    harness: session.harness, session: session.sid});
  return '<button type="button" class="next-project-session" data-next-project-session ' +
    `data-next-harness="${esc(session.harness)}" data-next-session="${esc(session.sid)}" ` +
    `data-next-route="${esc(route)}" data-next-focus="${esc(route)}">` +
    `<span class="next-project-dot next-project-tone--${esc(session.tone)}${session.isLive ? " next-project-dot--working" : ""}" ` +
    `role="img" aria-label="${esc(session.state)}"></span>` +
    `<span class="next-project-session-harness">${esc(session.harness)}</span>` +
    nextProjectValue(session.titleText, session.titleKnown, "next-project-session-title") +
    nextProjectValue(session.nowText, session.nowKnown, "next-project-session-now") +
    nextProjectValue(session.nextText, session.nextKnown, "next-project-session-next") + "</button>";
}

function nextProjectRow(project, history = false){
  const route = nextRouteToken({view: "project", project: project.key, session: null});
  const historyClass = history ? " next-project-row--history" : "";
  const historyAttr = history ? ' data-next-project-history="true"' : "";
  const identity = `<strong class="next-project-name">${esc(project.key)}</strong>`;
  const count = `<div class="next-project-summary">${esc(project.countLine)}</div>`;
  const shared = project.sharedLabelKnown
    ? `<div class="next-project-collision">${esc(project.sharedLabelText)}</div>` : "";
  const content = history ? identity + count :
    '<div class="next-project-project">' + identity +
    nextProjectValue(project.scopeText, project.scopeKnown, "next-project-scope") + count + shared +
    '</div><div class="next-project-sessions" aria-label="Observed sessions">' +
    project.sessions.map(nextProjectSessionLine).join("") + "</div>";
  return `<article class="next-project-row next-project-tone--${esc(project.tone)}${historyClass}" ` +
    `data-next-project-row data-next-project="${esc(project.key)}" data-next-route="${esc(route)}" ` +
    `data-next-focus="${esc(route)}" role="link" tabindex="0"${historyAttr}>` + content +
    '<span class="next-project-chevron" aria-hidden="true">›</span></article>';
}

function nextProjectGroup(kind, title, description, items, renderer, empty){
  const rows = items.map(renderer).join("");
  return `<section class="next-project-group next-project-group--${kind}" ` +
    `data-next-project-group="${kind}"><header><h2>${title}</h2>` +
    `<p>${description}</p></header><div class="next-projects-brief">` +
    `${rows || `<p class="next-projects-empty">${esc(empty)}</p>`}</div></section>`;
}

function nextProjectsView(model){
  const observed = model.activeProjects ? model : nextCurrentObserved();
  return '<p class="next-projects-note">sessions grouped by the label their harness publishes</p>' +
    nextProjectGroup(
      "active", "Active", "blocked on you ranks first · only source-backed sessions contribute claims",
      observed.activeProjects, project => nextProjectRow(project),
      "No project has active session evidence right now.",
    ) + nextProjectGroup(
      "history", "Recently observed", "identity stays reachable; operational claims lapse",
      observed.restProjects, project => nextProjectRow(project, true),
      "No recently observed project history in this payload.",
    );
}
