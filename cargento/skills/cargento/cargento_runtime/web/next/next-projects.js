/* The filtered reading of the newest prompt, where the payload carries one.
   `instruction.text` with the "asked" label IS the newest genuine prompt: the
   injected harness shapes dropped, slash markup read back out, and the whole
   string through `safe_text`. `last_prompt` is the raw newest record on every
   harness but Codex, so on a Claude row the two are two readings of one prompt
   and this takes the filtered one. Measured over 2,931 local rows: 114 carry an
   "asked" line, 15 of those differ from `last_prompt`, and 2 have no
   `last_prompt` at all.

   Only that label. This cell renders "last instruction · …" with nowhere to put
   a label, and the other two labels are exactly the readings that need one:
   "agent" is an agent quoting itself and "earlier" says this is not the newest
   thing asked. Published bare they would be the claim
   `transcripts.instruction_from` refuses to make. */
function nextProjectInstructionText(session){
  const instruction = session && session.instruction;
  const labelled = instruction && typeof instruction === "object" &&
    !Array.isArray(instruction) && String(instruction.label || "") === "asked";
  const filtered = labelled
    ? String(instruction.text == null ? "" : instruction.text).trim()
    : "";
  return filtered || String(session.last_prompt || session.title || "").trim();
}

function nextProjectInstruction(sessions){
  let chosen = null;
  for(const session of sessions){
    const text = nextProjectInstructionText(session);
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
  if(running){
    return `<span class="next-project-now next-project-now--running">● ${running} running</span>`;
  }
  const statesKnown = sessions.length && sessions.every(session =>
    ["needs_input", "working", "idle"].includes(session.state),
  );
  return statesKnown
    ? '<span class="next-project-now next-project-now--idle">idle</span>'
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
