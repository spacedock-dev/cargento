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

const NEXT_ACTIVITY_SUBAGENT_LIMIT = 6;

function nextProjectActivitySubagents(session){
  const subagents = Array.isArray(session.subagents) ? session.subagents : [];
  if(!subagents.length) return "";
  const rows = subagents.slice(0, NEXT_ACTIVITY_SUBAGENT_LIMIT).map((subagent, index) => {
    const elapsed = nextDurationSince(subagent && subagent.started_at);
    const measured = elapsed == null ? "" :
      `<span class="next-activity-subagent-elapsed">${elapsed}</span>`;
    return `<span class="next-activity-subagent" role="listitem" ` +
      `data-next-activity-subagent="${index}">` +
      `<span class="next-activity-subagent-name">${esc(subagent && subagent.name || "subagent")}</span>` +
      `${measured}</span>`;
  }).join("");
  const remaining = subagents.length - NEXT_ACTIVITY_SUBAGENT_LIMIT;
  const more = remaining > 0 ?
    `<span class="next-activity-subagent-more" role="listitem">+${remaining} more</span>` : "";
  return '<span class="next-activity-subagents" role="list" aria-label="Subagents">' +
    `${rows}${more}</span>`;
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
  /* The same second line the session table and the detail header carry, from
     the same renderer, because a third copy of "when may this be shown" is a
     third chance to disagree with the runtime about it. Clipped to one line
     here and not wrapped as it is there: GOING ON is scanned rather than read,
     and a card that grows by two lines whenever the newest prompt is long
     pushes the next card off the fold. What is lost is the tail of a line
     already bounded at 140 characters; the label and age, which are what make
     the line survivable, are never in the part that clips. */
  const instruction = nextInstructionLine(session, title, "next-activity-instruction", "span");
  return `<button type="button" class="next-activity-card${blocked}${live}" ` +
    `data-next-going-on="${esc(sid)}" data-next-route="${esc(route)}">` +
    nextStatusDot(stateLabel, "next-activity-dot") +
    `<span class="next-activity-identity"><strong>${esc(title)}</strong>${instruction}` +
    `<small>${esc(detail)}</small>${nextProjectActivitySubagents(session)}</span>` +
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
    /* No harness allowlist: see the note in nextSessionTasks. DONE reads the
       published field, so a project whose only tracked work is a Codex plan
       stops reporting "No completed tracked tasks" over six finished ones. */
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
