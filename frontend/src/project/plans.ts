import { ageSeconds } from '../observed/values';
import { formatDuration } from '../shell/format';
import { field, fieldText, list, PROJECT_STALLED_SEC, record, text, type Row } from './raw';

/* The project's plan: Spacedock strips the working sessions published, rejoined by workflow name, with
   each entity's stage and whether it is live, and, where no session published one, the workflow
   definitions Spacedock project discovery observed on disk. A plan is what the strips say. Nothing here
   estimates, schedules or infers a stage that was not published, and the empty states say which part of
   the evidence was missing. Ported from `next-project.js`. */

export interface PlanEntity {
  readonly slug: string;
  readonly stage: string;
  readonly cycle: string;
  readonly live: boolean;
  /** The raw row of the session whose strip carried the entity. */
  readonly session: Row;
  readonly order: number;
}

export interface Plan {
  readonly name: string;
  readonly goal: string;
  readonly stages: readonly string[];
  readonly entities: readonly PlanEntity[];
}

/* Strips of one workflow name are one plan, whichever session published them. The goal is the first one
   published, the stages are the union in first-seen order, and an entity published twice keeps its first
   position and the live copy: a live row beats a pending one, and nothing else replaces a row. */
export function projectPlans(sessions: readonly Row[]): Plan[] {
  interface Building {
    name: string;
    goal: string;
    stages: string[];
    stageNames: Set<string>;
    entities: Map<string, PlanEntity>;
  }
  const plans = new Map<string, Building>();
  let entityOrder = 0;
  for (const session of sessions) {
    const spacedock = field(session, 'spacedock');
    const workflows = list(field(spacedock, 'workflows'));
    for (const strip of workflows) {
      const name = fieldText(strip, 'workflow').trim();
      if (!name) continue;
      let plan = plans.get(name);
      if (!plan) {
        plan = {
          name,
          goal: fieldText(strip, 'goal').trim(),
          stages: [],
          stageNames: new Set(),
          entities: new Map(),
        };
        plans.set(name, plan);
      }
      if (!plan.goal) plan.goal = fieldText(strip, 'goal').trim();
      for (const value of list(field(strip, 'stages'))) {
        const stage = text(value).trim();
        if (!stage || plan.stageNames.has(stage)) continue;
        plan.stageNames.add(stage);
        plan.stages.push(stage);
      }
      for (const entity of list(field(strip, 'entities'))) {
        const slug = fieldText(entity, 'slug').trim();
        if (!slug) continue;
        const stage = fieldText(entity, 'stage').trim();
        if (stage && !plan.stageNames.has(stage)) {
          plan.stageNames.add(stage);
          plan.stages.push(stage);
        }
        const current = plan.entities.get(slug);
        const candidate: PlanEntity = {
          slug,
          stage,
          cycle: fieldText(entity, 'cycle').trim(),
          live: field(entity, 'live') === true,
          session,
          order: current ? current.order : entityOrder++,
        };
        if (!current || (!current.live && candidate.live)) plan.entities.set(slug, candidate);
      }
    }
  }
  return [...plans.values()].map((plan) => {
    const stageOrder = new Map(plan.stages.map((stage, index) => [stage, index]));
    const entities = [...plan.entities.values()].sort((left, right) => {
      const leftStage = stageOrder.get(left.stage) ?? plan.stages.length;
      const rightStage = stageOrder.get(right.stage) ?? plan.stages.length;
      return leftStage - rightStage || left.order - right.order;
    });
    return { name: plan.name, goal: plan.goal, stages: plan.stages, entities };
  });
}

export interface EntityState {
  readonly label: string;
  readonly unhealthy: boolean;
}

/* Only a live entity can be unhealthy: blocked on the reader, or its session quiet past one complete
   token-rate window. A pending one has nothing to be wrong about yet. */
export function entityState(entity: PlanEntity, generated: number | null): EntityState {
  if (!entity.live) return { label: '', unhealthy: false };
  if (entity.session['state'] === 'needs_input')
    return { label: 'blocked on you', unhealthy: true };
  const age = ageSeconds(generated, entity.session['last_activity']);
  if (age !== null && age >= PROJECT_STALLED_SEC) {
    return { label: `stalled ${String(formatDuration(age))}`, unhealthy: true };
  }
  return { label: '', unhealthy: false };
}

export function unhealthyCount(plans: readonly Plan[], generated: number | null): number {
  return plans.reduce(
    (total, plan) =>
      total + plan.entities.filter((entity) => entityState(entity, generated).unhealthy).length,
    0,
  );
}

export interface WorkflowDefinition {
  readonly name: string;
  readonly goal: string;
  readonly stages: readonly string[];
}

export function workflowDefinition(workflow: unknown): WorkflowDefinition {
  return {
    name: fieldText(workflow, 'workflow').trim(),
    goal: fieldText(workflow, 'goal').trim(),
    stages: Array.isArray(field(workflow, 'stages'))
      ? (field(workflow, 'stages') as unknown[]).map((value) => text(value).trim()).filter(Boolean)
      : [],
  };
}

/** Whether the semantic timeline carries workflow activity: a work item of workflow kind or id. */
export function workflowEvidence(observation: Row | null): boolean {
  const semantic = record(field(observation, 'semantic'));
  return list(semantic['work_items']).some(
    (item) =>
      fieldText(item, 'kind') === 'workflow_item' ||
      fieldText(item, 'work_item_id').startsWith('workflow:'),
  );
}

export function discoveryOf(observation: Row | null): Row {
  return record(field(observation, 'workflow_discovery'));
}

/* The sentence for a project that has no live plan: what was and was not observed, in the order of how
   much evidence there was. An attachment is not a definition, and the sentence says so. */
export function planEmptyText(sessions: readonly Row[], observation: Row | null): string {
  const spacedock = sessions.map((session) => session['spacedock']).filter(Boolean);
  const firstOfficer = spacedock.some((value) => field(value, 'role') === 'first-officer');
  const ensign = spacedock.some((value) => field(value, 'role') === 'ensign');
  const semanticEvidence = workflowEvidence(observation);
  const discovery = discoveryOf(observation);
  const state = String(discovery['state'] || 'loading');
  const reason = String(discovery['reason'] || '').trim();
  let prefix = 'No live session plan was observed.';
  if (firstOfficer) {
    prefix = 'A first-officer attachment was observed, but it exposed no current plan.';
  } else if (ensign) {
    prefix =
      'An ensign attachment was observed, but attachment metadata is not the project workflow definition.';
    if (semanticEvidence) prefix += ' Workflow activity is present in the semantic timeline.';
  } else if (semanticEvidence) {
    prefix =
      'Workflow activity is present in the semantic timeline, but no live session plan was observed.';
  }
  if (state === 'none') {
    return `${prefix} Spacedock project discovery observed no commissioned workflow directories.`;
  }
  if (state === 'unavailable') {
    return `${prefix} Project workflow definitions are unavailable${reason ? `: ${reason}` : '.'}`;
  }
  if (state === 'error') {
    return `${prefix} Project workflow discovery failed${reason ? `: ${reason}` : '.'}`;
  }
  return `${prefix} Checking project workflow definitions…`;
}

export type PlanBlock =
  | { readonly kind: 'plans'; readonly plans: readonly Plan[] }
  | { readonly kind: 'definitions'; readonly workflows: readonly WorkflowDefinition[] }
  | { readonly kind: 'empty'; readonly text: string };

/* What the plan block shows: the live plans, else the definitions discovery observed, else why neither. */
export function planBlock(
  plans: readonly Plan[],
  sessions: readonly Row[],
  observation: Row | null,
): PlanBlock {
  if (plans.length) return { kind: 'plans', plans };
  const discovery = discoveryOf(observation);
  const workflows = list(discovery['workflows']);
  if (discovery['state'] === 'observed' && workflows.length) {
    return { kind: 'definitions', workflows: workflows.map(workflowDefinition) };
  }
  return { kind: 'empty', text: planEmptyText(sessions, observation) };
}

/** Whether the "Show project plan" disclosure is offered at all: some plan, definition or attachment. */
export function planOffered(
  plans: readonly Plan[],
  sessions: readonly Row[],
  observation: Row | null,
): boolean {
  const discovery = discoveryOf(observation);
  const discovered =
    discovery['state'] === 'observed' &&
    Array.isArray(discovery['workflows']) &&
    (discovery['workflows'] as unknown[]).length > 0;
  const attached = sessions.some((session) => Boolean(session['spacedock']));
  return plans.length > 0 || discovered || attached;
}
