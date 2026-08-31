/* A quiet live session has no fresh evidence after one complete token-rate
   window. This uses the same measured ten-minute window as rate_window_sec,
   not the viewer clock or the 90-second collector working threshold. */
const NEXT_PROJECT_STALLED_SEC = 600;

function nextProjectPlans(sessions){
  const plans = new Map();
  let entityOrder = 0;
  for(const session of sessions){
    const spacedock = session && session.spacedock;
    const workflows = spacedock && Array.isArray(spacedock.workflows)
      ? spacedock.workflows
      : [];
    for(const strip of workflows){
      const name = String(strip && strip.workflow || "").trim();
      if(!name) continue;
      if(!plans.has(name)){
        plans.set(name, {
          name,
          goal: String(strip.goal || "").trim(),
          stages: [],
          stageNames: new Set(),
          entities: new Map(),
        });
      }
      const plan = plans.get(name);
      if(!plan.goal) plan.goal = String(strip.goal || "").trim();
      const stages = Array.isArray(strip.stages) ? strip.stages : [];
      for(const value of stages){
        const stage = String(value || "").trim();
        if(!stage || plan.stageNames.has(stage)) continue;
        plan.stageNames.add(stage);
        plan.stages.push(stage);
      }
      const entities = Array.isArray(strip.entities) ? strip.entities : [];
      for(const entity of entities){
        const slug = String(entity && entity.slug || "").trim();
        if(!slug) continue;
        const stage = String(entity.stage || "").trim();
        if(stage && !plan.stageNames.has(stage)){
          plan.stageNames.add(stage);
          plan.stages.push(stage);
        }
        const current = plan.entities.get(slug);
        const candidate = {
          slug,
          stage,
          cycle: String(entity.cycle || "").trim(),
          live: entity.live === true,
          session,
          order: current ? current.order : entityOrder++,
        };
        if(!current || (!current.live && candidate.live)) plan.entities.set(slug, candidate);
      }
    }
  }
  return [...plans.values()].map(plan => {
    const stageOrder = new Map(plan.stages.map((stage, index) => [stage, index]));
    const entities = [...plan.entities.values()].sort((left, right) => {
      const leftStage = stageOrder.has(left.stage) ? stageOrder.get(left.stage) : plan.stages.length;
      const rightStage = stageOrder.has(right.stage) ? stageOrder.get(right.stage) : plan.stages.length;
      return leftStage - rightStage || left.order - right.order;
    });
    return {name: plan.name, goal: plan.goal, stages: plan.stages, entities};
  });
}

function nextProjectEntityState(entity){
  if(!entity.live) return {label: "", unhealthy: false};
  if(entity.session.state === "needs_input"){
    return {label: "blocked on you", unhealthy: true};
  }
  const age = nextAgeSeconds(entity.session.last_activity);
  if(age != null && age >= NEXT_PROJECT_STALLED_SEC){
    return {label: `stalled ${nextFormatDuration(age)}`, unhealthy: true};
  }
  return {label: "", unhealthy: false};
}

function nextProjectEntityRow(entity, harnesses){
  const state = nextProjectEntityState(entity);
  const harness = String(entity.session.harness || "");
  const owner = entity.live ? (harnesses.get(harness) || harness) : "";
  const cycle = entity.cycle
    ? `<span class="next-project-plan-cycle">${esc(entity.cycle)}</span>`
    : "";
  const pending = entity.live ? "" : " next-project-plan-row--pending";
  const unhealthy = state.unhealthy ? " next-project-plan-row--unhealthy" : "";
  return `<div class="next-project-plan-row${pending}${unhealthy}" ` +
    `data-next-plan-entity="${esc(entity.slug)}" data-next-live="${entity.live}">` +
    nextStatusDot(entity.live ? "live" : "pending", "next-project-plan-glyph", entity.live) +
    `<span class="next-project-plan-step"><strong>${esc(entity.slug)}</strong>${cycle}` +
    `<small>${esc(entity.stage)}</small></span>` +
    `<span class="next-project-plan-owner">${esc(owner)}</span>` +
    `<span class="next-project-plan-state">${esc(state.label)}</span></div>`;
}

function nextProjectPlan(plan, harnesses){
  const goal = plan.goal ? `<p>${esc(plan.goal)}</p>` : "";
  const rows = plan.entities.map(entity => nextProjectEntityRow(entity, harnesses)).join("");
  return `<section class="next-project-plan" data-next-plan="${esc(plan.name)}">` +
    `<header><span>PLAN</span><strong>${esc(plan.name)}</strong>${goal}</header>` +
    `<div class="next-project-plan-rows">${rows}</div></section>`;
}

function nextProjectEmptyState(sessions){
  const spacedock = sessions.map(session => session.spacedock).filter(Boolean);
  if(spacedock.some(value => value.role === "first-officer")){
    return "A workflow exists, but nothing is fresh enough to show.";
  }
  if(spacedock.some(value => value.role === "ensign")){
    return "This worker's plan lives with its first officer.";
  }
  return "";
}

function nextProjectPlanBlock(context){
  const hasSpacedock = context.group.sessions.some(session => {
    const spacedock = session && session.spacedock;
    return spacedock && typeof spacedock === "object" && !Array.isArray(spacedock);
  });
  if(!hasSpacedock) return "";
  if(!context.plans.length){
    const empty = nextProjectEmptyState(context.group.sessions);
    return empty ? `<div class="next-project-detail-empty">${esc(empty)}</div>` : "";
  }
  return context.plans.map(plan => nextProjectPlan(plan, context.harnesses)).join("");
}

function nextProjectUnhealthyCount(plans){
  return plans.reduce(
    (total, plan) => total + plan.entities.filter(entity => nextProjectEntityState(entity).unhealthy).length,
    0,
  );
}

function nextProjectDetailHeader(context){
  const workflows = context.plans.map(plan =>
    `<span class="next-project-detail-workflow" title="${esc(plan.goal)}">${esc(plan.name)}</span>`,
  ).join("");
  const instruction = nextProjectInstruction(context.group.sessions);
  const last = instruction
    ? `<p class="next-project-detail-instruction">${instruction.kind === "assignment" ?
      "latest assignment" : "latest session context"} · ${esc(instruction.text)}</p>`
    : "";
  const collision = context.group.sessions.length >= 2
    ? `<p class="next-project-detail-collision" title="${esc(NEXT_DUPLICATE_LABEL_LIMIT)}">` +
      `${context.group.sessions.length} sessions share this label</p>`
    : "";
  let health = "";
  if(context.plans.length){
    const unhealthy = nextProjectUnhealthyCount(context.plans);
    const entityLabel = `${unhealthy} ${unhealthy === 1 ? "entity" : "entities"} unhealthy`;
    health = '<span class="next-project-detail-divider" aria-hidden="true">|</span>' +
      `<span>${esc(entityLabel)} — <span data-next-withheld>estimate withheld</span></span>`;
  }
  return '<header class="next-project-detail-header">' +
    `<div><span class="next-project-detail-label">project</span>` +
    `<h1 class="next-project-detail-name">${esc(context.group.label)}</h1>${workflows}</div>` +
    last + collision +
    '<div class="next-project-detail-status">' +
    `<span data-next-withheld>${nextWithheldLine("no estimate left", "no confidence")}</span>` +
    `${health}</div>` +
    '</header>';
}

function nextProjectView(project){
  const group = nextProjectGroups().find(candidate => candidate.label === project);
  if(!group){
    return '<div class="next-project-detail-empty"><p>Not present in the current payload.</p>' +
      '<a href="#n=projects" data-next-route="projects">View all projects</a></div>';
  }
  const context = {group, plans: nextProjectPlans(group.sessions), harnesses: nextHarnessLabels()};
  const plan = nextProjectPlanBlock(context);
  const planSection = plan ? `<div data-next-project-section="plan">${plan}</div>` : "";
  return `<article class="next-project-detail" data-next-project-detail="${esc(group.label)}">` +
    nextProjectDetailHeader(context) +
    '<div class="next-project-detail-layout">' +
    '<div class="next-project-detail-main" data-next-project-main>' +
    planSection +
    `<div data-next-project-section="going-on">${nextProjectGoingOn(context)}</div>` +
    `<div data-next-project-section="done">${nextProjectDone(context)}</div>` +
    `<div data-next-project-section="workstream">${nextProjectWorkstream(context)}</div></div>` +
    '<aside class="next-project-detail-rail" data-next-project-rail>' +
    `${nextProjectDelegation(context)}${nextProjectControls(context)}</aside>` +
    '</div></article>';
}
