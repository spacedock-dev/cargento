/* `active` is freshness — inside the display window — not "generating now", so
   filtering on it alone put every session the window still carries into GOING
   ON. One live Codex row read as eleven, ten of them idle and captioned
   "awaiting your message". The state is the only thing that says a session is
   doing something, and it is what the header count and the sessions view
   already read. */
function nextProjectGoingOnSessions(sessions){
  const gates = sessions.filter(session => session.state === "needs_input");
  const working = nextSessionWorkingOrder(
    sessions.filter(session => session.active === true && session.state === "working"),
  );
  return [...gates, ...working];
}

function nextProjectActivityCard(session, harnesses, project){
  const sid = String(session.sid || "");
  const harness = String(session.harness || "");
  const harnessLabel = harnesses.get(harness) || harness;
  const activity = String(session.state_detail || "");
  const detail = activity ? `${harnessLabel} · ${activity}` : harnessLabel;
  const title = String(session.title || session.last_prompt || project);
  const route = nextRouteToken({view: "session", project, session: sid});
  const gate = session.state === "needs_input";
  const blocked = gate ? " next-activity-card--blocked" : "";
  const live = gate ? "" : " next-live";
  const stateLabel = gate ? "needs input" : "working";
  const metric = nextSessionMetric(session);
  return `<button type="button" class="next-activity-card${blocked}${live}" ` +
    `data-next-going-on="${esc(sid)}" data-next-route="${esc(route)}">` +
    nextStatusDot(stateLabel, "next-activity-dot") +
    `<span class="next-activity-identity"><strong>${esc(title)}</strong>` +
    `<small>${esc(detail)}</small></span>` +
    `<span class="next-activity-metric">${esc(metric)}</span></button>`;
}

function nextProjectGoingOn(context){
  const cards = nextProjectGoingOnSessions(context.group.sessions).map(session =>
    nextProjectActivityCard(session, context.harnesses, context.group.label),
  ).join("");
  const body = cards || '<p class="next-activity-empty">' +
    "Nothing active or waiting on you in this project.</p>";
  return '<section class="next-project-activity" data-next-project-activity="going-on">' +
    '<h2>GOING ON</h2><div class="next-activity-cards">' + body + "</div></section>";
}

function nextProjectCompletedTasks(sessions){
  const completed = [];
  for(const session of sessions){
    if(session.harness !== "claude") continue;
    const tasks = Array.isArray(session.tasks) ? session.tasks : [];
    for(const task of tasks){
      if(task && task.status === "completed") completed.push(task);
    }
  }
  return completed;
}

function nextProjectDone(context){
  const rows = nextProjectCompletedTasks(context.group.sessions).map(task =>
    '<li><span class="next-activity-done-glyph" aria-label="completed">✓</span>' +
    `<span>${esc(task.subject || "")}</span></li>`,
  ).join("");
  const body = rows
    ? `<ul class="next-activity-done">${rows}</ul>`
    : '<p class="next-activity-empty">No completed tracked tasks in this payload.</p>';
  return '<section class="next-project-activity" data-next-project-activity="done">' +
    `<h2>DONE</h2>${body}</section>`;
}
