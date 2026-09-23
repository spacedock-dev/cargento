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
    nextSessionDot(session) +
    `<span class="next-project-session-harness">${esc(session.harness)}</span>` +
    nextProjectValue(session.titleText, session.titleKnown, "next-project-session-title") +
    nextProjectValue(session.nowText, session.nowKnown, "next-project-session-now") +
    nextProjectValue(session.nextText, session.nextKnown, "next-project-session-next") + "</button>";
}

/* The member lines an Active project row renders (DRC-4647). Blocked on you,
   then working, then any member carrying a risk, then quiet by most recent
   activity, then everything else, then ended. Blocked, working and risky
   members render even past the cap, because hiding one would bury what the
   row exists to show and what turned its rail colour; the rest fill up to
   NEXT_PROJECT_MEMBER_CAP and one count line names what is left. */
const NEXT_PROJECT_MEMBER_CAP = 5;

function nextProjectMembers(sessions, risky = []){
  const risks = new Set(risky.map(nextSessionKey));
  const rank = session => session.isNeeds || session.askKnown ? 0 : (session.isWorking ? 1 :
    (risks.has(nextSessionKey(session)) ? 1.5 : (session.isEnded ? 4 : (session.isQuiet ? 2 : 3))));
  const ordered = sessions.map((session, index) => ({session, index})).sort((a, b) =>
    rank(a.session) - rank(b.session) ||
    (rank(a.session) >= 2 ? (b.session.lastActivityAt || 0) - (a.session.lastActivityAt || 0) : 0) ||
    a.index - b.index).map(row => row.session);
  const pinned = ordered.filter(session => rank(session) < 2);
  const rest = ordered.filter(session => rank(session) >= 2);
  const shown = [...pinned, ...rest.slice(0, Math.max(0, NEXT_PROJECT_MEMBER_CAP - pinned.length))];
  return {shown, hidden: ordered.length - shown.length};
}

function nextProjectMoreLine(hidden, route){
  if(!hidden) return "";
  return `<button type="button" class="next-project-more" data-next-project-more ` +
    `data-next-route="${esc(route)}" data-next-focus="${esc(route)}">` +
    `${hidden} other ${hidden === 1 ? "session" : "sessions"}</button>`;
}

function nextProjectRow(project, history = false){
  const route = nextRouteToken({view: "project", project: project.key, session: null});
  const historyClass = history ? " next-project-row--history" : "";
  const historyAttr = history ? ' data-next-project-history="true"' : "";
  const identity = `<strong class="next-project-name">${esc(project.key)}</strong>`;
  const count = `<div class="next-project-summary">${esc(project.countLine)}</div>`;
  const shared = project.sharedLabelKnown
    ? `<div class="next-project-collision">${esc(project.sharedLabelText)}</div>` : "";
  const members = history ? null : nextProjectMembers(project.sessions, project.risky || []);
  const content = history ? identity + count :
    '<div class="next-project-project">' + identity +
    nextProjectValue(project.scopeText, project.scopeKnown, "next-project-scope") + count + shared +
    '</div><div class="next-project-sessions" aria-label="Observed sessions">' +
    members.shown.map(nextProjectSessionLine).join("") + nextProjectMoreLine(members.hidden, route) + "</div>";
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
  return nextStageConditions() + '<p class="next-projects-note">sessions grouped by the label their harness publishes</p>' +
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
