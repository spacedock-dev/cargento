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

function nextProjectWorkflowDefinition(workflow){
  const name = String(workflow && workflow.workflow || "").trim();
  const goal = String(workflow && workflow.goal || "").trim();
  const stages = Array.isArray(workflow && workflow.stages)
    ? workflow.stages.map(value => String(value || "").trim()).filter(Boolean)
    : [];
  const goalLine = goal ? `<p>${esc(goal)}</p>` : "";
  const stagesLine = stages.length
    ? `<div class="next-project-workflow-stages"><span>DECLARED STAGES</span><strong>${esc(stages.join(" · "))}</strong></div>`
    : '<div class="next-project-workflow-stages"><span>DECLARED STAGES</span><strong>definition unavailable</strong></div>';
  return `<section class="next-project-workflow-definition" data-next-workflow-definition="${esc(name)}">` +
    `<header><span>PROJECT WORKFLOW</span><strong>${esc(name)}</strong>${goalLine}</header>${stagesLine}` +
    '<small>Observed by Spacedock project discovery; no live entity state is inferred.</small></section>';
}

function nextProjectWorkflowEvidence(discovery){
  const semantic = discovery && discovery.semantic || {};
  const workItems = Array.isArray(semantic.work_items) ? semantic.work_items : [];
  return workItems.some(item =>
    String(item && item.kind || "") === "workflow_item" ||
    String(item && item.work_item_id || "").startsWith("workflow:")
  );
}

function nextProjectEmptyState(context, observation){
  const spacedock = context.group.sessions.map(session => session.spacedock).filter(Boolean);
  const firstOfficer = spacedock.some(value => value.role === "first-officer");
  const ensign = spacedock.some(value => value.role === "ensign");
  const semanticEvidence = nextProjectWorkflowEvidence(observation);
  const discovery = observation && observation.workflow_discovery || {};
  const state = String(discovery.state || "loading");
  const reason = String(discovery.reason || "").trim();
  let prefix = "No live session plan was observed.";
  if(firstOfficer){
    prefix = "A first-officer attachment was observed, but it exposed no current plan.";
  }else if(ensign){
    prefix = "An ensign attachment was observed, but attachment metadata is not the project workflow definition.";
    if(semanticEvidence) prefix += " Workflow activity is present in the semantic timeline.";
  }else if(semanticEvidence){
    prefix = "Workflow activity is present in the semantic timeline, but no live session plan was observed.";
  }
  if(state === "none"){
    return `${prefix} Spacedock project discovery observed no commissioned workflow directories.`;
  }
  if(state === "unavailable"){
    return `${prefix} Project workflow definitions are unavailable${reason ? `: ${reason}` : "."}`;
  }
  if(state === "error"){
    return `${prefix} Project workflow discovery failed${reason ? `: ${reason}` : "."}`;
  }
  return `${prefix} Checking project workflow definitions…`;
}

function nextProjectPlanBlock(context){
  if(context.plans.length){
    return context.plans.map(plan => nextProjectPlan(plan, context.harnesses)).join("");
  }
  const observation = nextCockpitProjectObservation(context.group);
  const discovery = observation && observation.workflow_discovery || {};
  const workflows = Array.isArray(discovery.workflows) ? discovery.workflows : [];
  if(discovery.state === "observed" && workflows.length){
    return workflows.map(nextProjectWorkflowDefinition).join("");
  }
  return `<div class="next-project-detail-empty">${esc(nextProjectEmptyState(context, observation))}</div>`;
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

/* STATED GOAL is a list, not a field: zero to n rows, each with its own tag and
   its own source line. The reader's typed words are rows above the harness's,
   never merged with them, because "what I asked for" and "what the harness
   published" are different claims and one string cannot carry both.

   `annotation` is the focused session's, or null at project scope where there
   is no one session to have typed anything. The project-scope count line the
   design also draws is C4's subject (DRC-4023) and is deliberately not here. */
/* "revision 4 of 4", or "revision 20, 16 kept" once the store has started
   dropping the oldest.

   `revision` is a save counter that keeps climbing so a dropped revision reads
   as dropped, and `revision_count` is how many survive the store's bound. Read
   as "N of M" the pair goes arithmetically impossible the moment they diverge,
   which is a count that does not derive from the collection it describes. Past
   the bound the sentence names both numbers for what they are and says the
   older ones are gone, the way the work-evidence block names what it hid. */
function nextProjectRevisionLine(annotation){
  const revision = nextNumber(annotation && annotation.revision);
  const count = nextNumber(annotation && annotation.revision_count);
  if(revision == null || count == null || count <= 0) return "";
  const age = nextDurationSince(nextNumber(annotation && annotation.at));
  const typed = age == null ? "" : ` · typed ${age} ago`;
  return revision > count
    ? `revision ${revision}, ${count} kept${typed} · older revisions dropped`
    : `revision ${revision} of ${count}${typed}`;
}

function nextProjectGoalRow(tag, text, src, known = true){
  return '<div class="next-project-goal-row">' +
    `<span class="next-project-goal-tag">${esc(tag)}</span>` +
    nextProjectValue(text, known, "next-project-goal-text") +
    (src ? `<span class="next-project-goal-source">${esc(src)}</span>` : "") + '</div>';
}

/* The derived row's source line, with when the directive was observed
   (DRC-4509). It carried a source and no time, so a four-minute-old directive
   and a four-hour-old one read the same. The workflow arm publishes no stamp
   and says so rather than leaving the row looking fresh.

   `scope` is the focused session at session scope and the project otherwise.
   They are different claims: the project's goal is whichever session moved
   most recently, and pairing that with one session's typed words puts another
   session's directive under DERIVED FROM THE HARNESS. */
function nextProjectGoalDerivedSource(scope){
  if(!scope.known) return "";
  const age = scope.at == null ? null : nextDurationSince(scope.at);
  return `${scope.src} · ` +
    (age == null ? "observation time not published" : `observed ${age} ago`);
}

/* Whose derived goal this render is about. A focused session answers for
   itself; with none, the project answers for the group. */
function nextProjectGoalScope(project, focus){
  return focus
    ? {text: focus.ownGoalText, known: focus.ownGoalKnown, src: focus.ownGoalSrcText,
      at: focus.ownGoalAt}
    : {text: project.goalText, known: project.goalKnown, src: project.goalSrcText,
      at: project.goalAt};
}

function nextProjectGoal(project, annotation, focus){
  const scope = nextProjectGoalScope(project, focus);
  const source = scope.known
    ? '<span class="next-project-goal-source">' +
      `${esc(nextProjectGoalDerivedSource(scope))}</span>` : "";
  /* A count across the project's sessions, so it belongs to the project's
     render. Beside one session's typed words it answers a question the reader
     did not ask about a group they are not looking at. */
  const gap = !focus && project.goalGapKnown
    ? `<p class="next-project-goal-gap">${esc(project.goalGapText)}</p>` : "";
  const typed = annotation || null;
  const revision = nextProjectRevisionLine(typed);
  let rows = "";
  if(typed && typed.goal){
    rows += nextProjectGoalRow("YOUR WORDS · GOAL", typed.goal, revision);
  }
  if(typed && typed.output){
    rows += nextProjectGoalRow("YOUR WORDS · EXPECTED OUTPUT", typed.output, revision);
  }
  /* The binding sentence, not a decoration. A Claude row's session id is an
     eight-character prefix, so another session sharing it would share these
     words, and the reader is told rather than left to assume otherwise. */
  /* Only where there are words for it to be about. The sentence says another
     session sharing this prefix "would share these words", and with nothing
     typed, and on a run started with --no-annotations where nothing can be,
     it is a caveat about a binding that does not exist. */
  const binding = typed && typed.binding_why && (typed.goal || typed.output)
    ? `<p class="next-project-goal-gap">${esc(typed.binding_why)}</p>` : "";
  const derived = rows
    ? nextProjectGoalRow("DERIVED FROM THE HARNESS", scope.text,
        nextProjectGoalDerivedSource(scope), scope.known)
    : nextProjectValue(scope.text, scope.known, "next-project-goal-text");
  return '<section class="next-project-goal"><header><h2>STATED GOAL</h2>' +
    (rows ? "" : source) + '</header>' + rows + derived + binding + gap + '</section>';
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
    `<small>${esc(collapsed ? project.changeNoteText.split(" · ")[0] : project.changeNoteText)}</small></button></header>`;
  const rows = project.changes.map(change =>
    `<li class="next-project-change" data-next-workstream-event="${esc(change.kind)}">` +
    `<time>${esc(change.at)}</time>` +
    `<span class="next-project-change-dot${change.filled ? " next-project-change-dot--unattended" : ""}" ` +
    `role="img" aria-label="${change.filled ? "unattended" : "attended"}"></span>` +
    `<span>${esc(change.label)}</span><span class="next-project-change-harness">${esc(change.harness)}</span></li>`,
  ).join("");
  const body = collapsed ? "" : '<div id="next-project-changes">' + (rows ? `<ol>${rows}</ol>` :
    `<p class="next-workstream-empty">${esc(project.changeEmptyText)}</p>`) + '</div>';
  return `<section class="next-workstream"${collapsed ? " data-next-workstream-collapsed" : ""}>${header}${body}</section>`;
}

function nextProjectView(project){
  const model = nextCurrentObserved();
  const observed = model.projects.find(candidate => candidate.key === project);
  if(!observed){
    return '<div class="next-project-detail-empty"><p>Not present in the current payload.</p>' +
      '<a href="#n=projects" data-next-route="projects">View all projects</a></div>';
  }
  // The shared model omits Spacedock strips and published task totals. Keep the
  // shipped plan helpers on their original records until that interface carries them.
  const sources = new Map(nextPayloadSessions(nextData).map(session => [nextSessionKey(session), session]));
  const group = {label: observed.key, sessions: observed.sessions.map(session =>
    sources.get(nextSessionKey(session))).filter(Boolean)};
  const context = {model, project: observed, group, plans: nextProjectPlans(group.sessions), harnesses: nextHarnessLabels()};
  const focus = nextCockpitFocusedSession(group);
  if(nextRoute && nextRoute.focus && !focus){
    const root = {view:"project",project:group.label,focus:null,tab:nextRoute.tab || "now"};
    return `<article class="next-project-detail" data-next-project-detail="${esc(group.label)}">` +
      '<section class="next-cockpit-stale-session" data-next-cockpit-stale-session>' +
      '<span>SESSION FILTER</span><h1>Session filter is outside this payload window</h1>' +
      `<p>${esc(nextRoute.focus)}</p><a href="${esc(nextFragmentForRoute(root))}">` +
      'View project root</a></section></article>';
  }
  nextCockpitLoadContext(group, null);
  const observation = nextCockpitProjectObservation(group);
  const commandAttention = nextCockpitCommandAttention(group, observation);
  const multiSession = group.sessions.length > 1;
  const scopeNavigation = multiSession
    ? nextCockpitScopeTree(group, focus) + nextCockpitScopeSwitcher(group, focus) : "";
  return `<article class="next-project-detail" data-next-project-detail="${esc(group.label)}">` +
    nextProjectDetailHeader(context) +
    `<div class="next-cockpit-shell${multiSession ? "" : " next-cockpit-shell--single"}">` +
    scopeNavigation +
    '<div class="next-cockpit-content">' +
    nextProjectCockpit(context, observation, commandAttention) + '</div></div></article>';
}
