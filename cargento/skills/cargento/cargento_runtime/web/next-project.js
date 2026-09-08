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
  const project = context.project;
  const shared = project.sharedLabelKnown
    ? `<p class="next-project-detail-collision">${esc(project.sharedLabelText)}</p>` : "";
  return '<header class="next-project-detail-header">' +
    `<h1 class="next-project-detail-name">${esc(project.key)}</h1>` +
    nextProjectValue(project.scopeText, project.scopeKnown, "next-project-scope") +
    `<p class="next-project-detail-count">${esc(project.countLine)}</p>${shared}</header>`;
}

function nextProjectGoal(project){
  const source = project.goalKnown
    ? `<span class="next-project-goal-source">${esc(project.goalSrcText)}</span>` : "";
  const gap = project.goalGapKnown
    ? `<p class="next-project-goal-gap">${esc(project.goalGapText)}</p>` : "";
  return '<section class="next-project-goal"><header><h2>STATED GOAL</h2>' + source + '</header>' +
    nextProjectValue(project.goalText, project.goalKnown, "next-project-goal-text") + gap + '</section>';
}

function nextProjectPlanStatus(context){
  let health = "";
  if(context.plans.length){
    const unhealthy = nextProjectUnhealthyCount(context.plans);
    health = `<p>${unhealthy} ${unhealthy === 1 ? "entity" : "entities"} unhealthy — ` +
      '<span data-next-withheld>estimate withheld</span></p>';
  }
  return health ? '<div class="next-project-detail-status">' +
    '<span data-next-withheld>no estimate left · no confidence</span>' + health + '</div>' : "";
}

function nextProjectChanges(project){
  const collapsed = nextWorkstreamCollapsed;
  const route = nextRouteToken({view: "project", project: project.key, session: null});
  const header = '<header class="next-workstream-header">' +
    `<button type="button" data-next-workstream-toggle data-next-focus="${esc(route)}:changes" ` +
    `aria-expanded="${!collapsed}" aria-controls="next-project-changes">` +
    `<span>${collapsed ? "▸" : "▾"} OBSERVED STATE CHANGES</span>` +
    `<small>${esc(project.changeNoteText)}</small></button></header>`;
  const rows = project.changes.map(change =>
    '<li class="next-project-change">' +
    `<time>${esc(nextWorkstreamClock(change.at))}</time>` +
    `<span class="next-project-change-dot${change.filled ? " next-project-change-dot--unattended" : ""}" ` +
    `role="img" aria-label="${change.filled ? "unattended" : "attended"}"></span>` +
    `<span>${esc(change.label)}</span><span class="next-project-change-harness">${esc(change.harness)}</span></li>`,
  ).join("");
  const body = collapsed ? "" : '<div id="next-project-changes">' + (rows ? `<ol>${rows}</ol>` :
    `<p class="next-workstream-empty">${esc(project.changeNoteText)}</p>`) + '</div>';
  return `<section class="next-workstream"${collapsed ? " data-next-workstream-collapsed" : ""}>${header}${body}</section>`;
}

function nextProjectView(project){
  const model = nextObserved(nextData);
  const observed = model.projects.find(candidate => candidate.key === project);
  if(!observed){
    return '<div class="next-project-detail-empty"><p>Not present in the current payload.</p>' +
      '<a href="#n=projects" data-next-route="projects">View all projects</a></div>';
  }
  // The frozen model omits Spacedock strips and published task totals. Keep the
  // shipped plan helpers on their original records until that interface carries them.
  const sources = new Map(nextPayloadSessions(nextData).map(session => [nextSessionKey(session), session]));
  const group = {label: observed.key, sessions: observed.sessions.map(session =>
    sources.get(nextSessionKey(session))).filter(Boolean)};
  const context = {model, project: observed, group, plans: nextProjectPlans(group.sessions), harnesses: nextHarnessLabels()};
  const plan = nextProjectPlanBlock(context);
  const planSection = plan ? `<div data-next-project-section="plan">${nextProjectPlanStatus(context)}${plan}</div>` : "";
  return `<article class="next-project-detail" data-next-project-detail="${esc(observed.key)}">` +
    '<div class="next-project-detail-layout">' +
    '<div class="next-project-detail-main" data-next-project-main>' +
    nextProjectDetailHeader(context) + nextProjectGoal(observed) +
    '<div class="next-project-activity-grid">' + nextProjectGoingOn(context) +
    nextProjectEndings(context) + '</div>' +
    `<div data-next-project-section="workstream">${nextProjectChanges(observed)}</div>` +
    planSection + `<div data-next-project-section="done">${nextProjectDone(context)}</div></div>` +
    nextProjectRail(context) + '</div></article>';
}
