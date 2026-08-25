function nextProjectInstruction(sessions){
  let chosen = null;
  for(const session of sessions){
    const text = String(session.last_prompt || session.title || "").trim();
    if(!text) continue;
    const at = nextFiniteNumber(session.last_activity);
    if(!chosen || at > chosen.at) chosen = {at, text};
  }
  return chosen ? chosen.text : "";
}

function nextProjectWorkflows(sessions){
  const found = [];
  const seen = new Set();
  for(const session of sessions){
    const spacedock = session.spacedock;
    const workflows = spacedock && Array.isArray(spacedock.workflows)
      ? spacedock.workflows
      : [];
    for(const item of workflows){
      const workflow = String(item && item.workflow || "").trim();
      const goal = String(item && item.goal || "").trim();
      if(!workflow && !goal) continue;
      const key = `${workflow}\n${goal}`;
      if(seen.has(key)) continue;
      seen.add(key);
      found.push({workflow: workflow || goal, goal});
    }
  }
  return found;
}

function nextProjectCell(group){
  const workflows = nextProjectWorkflows(group.sessions);
  const instruction = nextProjectInstruction(group.sessions);
  const chips = workflows.map(workflow =>
    `<span class="next-project-workflow" title="${esc(workflow.goal)}">` +
      `${esc(workflow.workflow)}</span>`,
  ).join("");
  const last = instruction
    ? `<div class="next-project-instruction">last instruction · ${esc(instruction)}</div>`
    : "";
  /* The old collision signal is live-only because it warns about concurrent
     writes. This table makes a grouping claim, so even two idle rows need the
     caveat that spark.js:222-232 deliberately withholds from them. */
  const collision = group.sessions.length >= 2
    ? `<div class="next-project-collision" title="${esc(NEXT_DUPLICATE_LABEL_LIMIT)}">` +
      `${group.sessions.length} sessions share this label</div>`
    : "";
  return `<strong class="next-project-name">${esc(group.label)}</strong>${chips}${last}${collision}`;
}

function nextProjectProgress(sessions){
  const total = sessions.reduce((sum, session) => sum + Math.max(0, nextFiniteNumber(session.total)), 0);
  if(total <= 0) return "";
  const done = sessions.reduce((sum, session) => sum + Math.max(0, nextFiniteNumber(session.done)), 0);
  return `<progress class="next-project-progress-bar" value="${esc(Math.min(done, total))}" ` +
    `max="${esc(total)}" aria-label="${esc(done)} of ${esc(total)} tasks done"></progress>` +
    `<span>${esc(done)} of ${esc(total)} done</span>`;
}

function nextProjectNow(sessions){
  if(sessions.some(session => session.state === "needs_input")){
    return '<span class="next-project-now next-project-now--blocked">● blocked</span>';
  }
  const running = sessions.filter(session => session.state === "working" && session.active).length;
  return running
    ? `<span class="next-project-now next-project-now--running">● ${running} running</span>`
    : "";
}

function nextProjectRow(group){
  const blocked = group.sessions.some(session => session.state === "needs_input");
  const route = nextRouteToken({view: "project", project: group.label, session: null});
  return `<tr class="next-project-row${blocked ? " next-project-row--blocked" : ""}" ` +
    `data-next-project-row data-next-project="${esc(group.label)}" data-next-route="${esc(route)}">` +
    `<td class="next-project-project">${nextProjectCell(group)}</td>` +
    `<td class="next-project-progress">${nextProjectProgress(group.sessions)}</td>` +
    `<td class="next-project-estimate" data-next-withheld>${nextWithheld("no estimate", "no confidence")}</td>` +
    `<td class="next-project-delegation" data-next-withheld>${nextWithheld("not measured")}</td>` +
    `<td class="next-project-current">${nextProjectNow(group.sessions)}</td></tr>`;
}

function nextProjectsView(){
  const rows = nextProjectGroups().map(nextProjectRow).join("");
  return '<div class="next-projects-table-wrap"><table class="next-projects-table">' +
    '<thead><tr><th scope="col">PROJECT</th><th scope="col">PROGRESS</th>' +
    '<th scope="col">ESTIMATE</th><th scope="col">DELEGATION</th><th scope="col">NOW</th>' +
    `</tr></thead><tbody>${rows}</tbody></table></div>`;
}
