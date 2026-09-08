const NEXT_ACTIVITY_SUBAGENT_LIMIT = 6;

function nextProjectActivitySubagents(session){
  const subagents = Array.isArray(session.subagents) ? session.subagents : [];
  if(!subagents.length) return "";
  /* Ordered so the crew that is moving reads first: a lead with a finished
     teammate and six live lenses would otherwise spend the six-pill budget on
     work that has stopped. `filter` preserves order, so whatever order the
     collector published survives within each group -- which is mtime order only
     for the lead's own agents; classified children arrive in path order and
     their workers follow each one. */
  const ordered = [
    ...subagents.filter(nextSubagentIsLive),
    ...subagents.filter(subagent => !nextSubagentIsLive(subagent)),
  ];
  const rows = ordered.slice(0, NEXT_ACTIVITY_SUBAGENT_LIMIT).map((subagent, index) => {
    const elapsed = nextDurationSince(subagent && subagent.started_at);
    const measured = elapsed == null ? "" :
      `<span class="next-activity-subagent-elapsed">${elapsed}</span>`;
    const live = nextSubagentIsLive(subagent);
    return `<span class="next-activity-subagent${live ? "" : " next-activity-subagent--idle"}" ` +
      `role="listitem" data-next-activity-subagent="${index}">` +
      `<span class="next-activity-subagent-name">${esc(subagent && subagent.name || "subagent")}</span>` +
      `${measured}</span>`;
  }).join("");
  const remaining = subagents.length - NEXT_ACTIVITY_SUBAGENT_LIMIT;
  const more = remaining > 0 ?
    `<span class="next-activity-subagent-more" role="listitem">+${remaining} more</span>` : "";
  return '<span class="next-activity-subagents" role="list" aria-label="Subagents">' +
    `${rows}${more}</span>`;
}

function nextProjectActivityCard(session, project, source){
  const route = nextRouteToken({view: "session", project, harness: session.harness, session: session.sid});
  const stuck = session.stuckKnown ? `<span class="next-activity-stuck">stuck · ${esc(session.stuckText)}</span>` : "";
  const question = session.askKnown ? `<span class="next-activity-question">${esc(session.askText)}</span>` : "";
  const instruction = source ? nextInstructionLine(source, session.titleText, "next-activity-instruction", "span") : "";
  return `<button type="button" class="next-activity-card next-project-tone--${esc(session.tone)}" ` +
    `data-next-going-on="${esc(session.sid)}" data-next-route="${esc(route)}" data-next-focus="${esc(route)}">` +
    '<span class="next-activity-title">' +
    `<span class="next-project-dot next-project-tone--${esc(session.tone)}${session.isLive ? " next-project-dot--working" : ""}" ` +
    `role="img" aria-label="${esc(session.state)}"></span>` +
    nextProjectValue(session.titleText, session.titleKnown) + '</span>' + instruction +
    `<span class="next-activity-now"><span class="next-activity-harness">${esc(session.harness)} · </span>` +
    nextProjectValue(session.nowText, session.nowKnown) + '</span>' +
    `<span>next · ${nextProjectValue(session.nextText, session.nextKnown)}</span>` +
    `<span>turn · ${nextProjectValue(session.turnText, session.turnKnown)}</span>` + stuck + question +
    (session.isNeeds ? `<span class="next-activity-metric">${esc(session.waitedText)}</span>` :
      nextProjectValue(session.rateText, session.rateKnown, "next-activity-metric")) +
    nextProjectActivitySubagents(session) + '</button>';
}

function nextProjectGoingOn(context, commandAttention = []){
  const cards = context.project.sessions.filter(session => session.isLive || session.isNeeds || session.askKnown).map(session => {
    const source = context.group.sessions.find(candidate => nextSessionKey(candidate) === nextSessionKey(session));
    return nextProjectActivityCard(session, context.project.key, source);
  }).join("");
  const empty = commandAttention.length
    ? "No session currently running. Command attention remains above."
    : "Nothing observed running.";
  return '<section class="next-project-activity" data-next-project-activity="going-on">' +
    '<h2>GOING ON</h2><div class="next-activity-cards">' +
    (cards || `<p class="next-activity-empty">${empty}</p>`) + '</div></section>';
}

function nextProjectEndings(context){
  const cards = context.project.ended.map(session => {
    const route = nextRouteToken({view: "session", project: context.project.key,
      harness: session.harness, session: session.sid});
    const tone = session.tone;
    return `<button type="button" class="next-project-ending next-project-tone--${tone}" ` +
      `data-next-outcome="${esc(session.sid)}" data-next-route="${esc(route)}" data-next-focus="${esc(route)}">` +
      '<span class="next-project-ending-title">' +
      `<span class="next-project-ending-glyph" aria-hidden="true">${esc(session.outcomeGlyph)}</span>` +
      nextProjectValue(session.titleText, session.titleKnown) + '</span>' +
      nextProjectValue(session.outcomeText, session.outcomeKnown, "next-project-ending-outcome") +
      `<span>${esc(session.harness)} · git: ${nextProjectValue(session.gitText, session.gitKnown)}</span></button>`;
  }).join("");
  return '<section class="next-project-activity" data-next-project-activity="ended">' +
    '<h2>HOW THINGS ENDED</h2><div class="next-activity-cards">' +
    (cards || '<p class="next-activity-empty">No session in this project has been observed ending.</p>') + '</div></section>';
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
  const completed = nextProjectCompletedTasks(context.project.sessions);
  const progress = nextProjectProgress(context.group.sessions);
  const rows = completed.map(task =>
    '<li><span class="next-activity-done-glyph" aria-label="completed">✓</span>' +
    `<span>${esc(task.subject || "")}</span></li>`,
  ).join("");
  const body = rows
    ? `<ul class="next-activity-done">${rows}</ul>`
    : '<p class="next-activity-empty">No completed tracked tasks in this payload.</p>';
  return '<section class="next-project-activity" data-next-project-activity="done">' +
    `<h2>COMPLETED TASKS · ${completed.length}</h2>${progress}${body}</section>`;
}
