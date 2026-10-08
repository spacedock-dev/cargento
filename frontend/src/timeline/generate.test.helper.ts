/* Seeded semantic payloads for the differential test. The generator forces the shapes that decide which
   events a mode keeps: work items that share a label across an unbound and a bound id, a head whose latest
   event is missing, a dispatch with and without a return, a node list that is absent as against empty, ties
   in time, a fact id repeated, a direction that is a near duplicate of a newer one, and fields of the wrong
   type. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const FACT_TYPES = [
  'user_message',
  'prepared_dispatch',
  'assignment',
  'work_birth',
  'work_result',
  'result',
  'final_output',
  'decision',
  'gate_decision',
  'observer_snapshot',
  'goal_shift',
  'stage_transition',
  'checkpoint',
  'progress_head',
  'tool_call',
];
const SUMMARIES = [
  'Add retry with backoff',
  'ok',
  'please add retry with backoff again',
  'pwd',
  'Correct the lane order',
  "can't see the panel",
  'keep going',
  'Fix dispatch authority',
  'Newest direction',
  'project-cockpit · review · approve',
  'Shape the cockpit',
  'Ship it',
];
const HARNESSES = ['codex', 'claude'];
const SIDS = ['a', 'b', 'c:d'];

export interface GeneratedCase {
  readonly semantic: Record<string, unknown>;
  readonly delegations: Record<string, unknown>[];
  readonly focus: { harness: string; sid: string; state: string } | null;
  readonly origins: { harness: string; sid: string }[] | undefined;
  readonly fallbackSession: string;
}

export function genCase(seed: number): GeneratedCase {
  const next = rng(seed * 7919 + 13);
  const int = (n: number) => Math.floor(next() * n);
  const pick = <T>(list: readonly T[]): T => list[int(list.length)] as T;
  const chance = (p: number) => next() < p;

  const itemCount = int(6);
  const items = Array.from({ length: itemCount }, (_, index) => {
    const kind = pick(['workflow_item', 'workflow_item', 'session_result', 'other']);
    const unbound = chance(0.3);
    return {
      work_item_id: `${unbound ? 'workflow-unbound' : 'workflow'}:item-${String(unbound ? index % 2 : index)}`,
      label: pick(['project-cockpit', 'item-a', 'Item A', 'dispatch-authority', '']),
      kind,
      source_bindings: chance(0.5)
        ? [{ source: 'task state', value: `/repo/.spacedock/explore:item-${String(index)}` }]
        : [],
    };
  });
  const itemIds = items.map((item) => item.work_item_id);

  const factCount = int(15);
  const facts: Record<string, unknown>[] = [];
  for (let index = 0; index < factCount; index += 1) {
    const hasSession = chance(0.7);
    const fact: Record<string, unknown> = {
      // The server stamps every fact with an id; the legacy builder throws on one without.
      fact_id: chance(0.05) ? 'dup' : `f${String(index)}`,
      at: chance(0.05) ? undefined : 100 + int(12),
      type: pick(FACT_TYPES),
      summary: pick(SUMMARIES),
    };
    if (chance(0.7) && itemIds.length)
      fact['work_item_id'] = chance(0.1) ? 'unknown-item' : pick(itemIds);
    if (hasSession) fact['source_session'] = { harness: pick(HARNESSES), sid: pick(SIDS) };
    if (chance(0.7))
      fact['evidence'] = {
        source: 'root transcript',
        confidence: pick(['exact', 'derived', 'exact']),
      };
    if (chance(0.3)) fact['current_state'] = true;
    if (chance(0.3)) fact['stage'] = pick(['shaping', 'review', 'build']);
    if (chance(0.2)) fact['target_stage'] = pick(['shaping', 'done']);
    if (chance(0.3))
      fact['source_kind'] = pick([
        'gate',
        'work_birth',
        'task_started',
        'retry',
        'failed_attempt',
        'child_assignment',
      ]);
    if (chance(0.3)) fact['scope'] = pick(['project', 'session', 'PROJECT']);
    if (chance(0.3)) fact['by'] = pick(['person:captain', 'agent']);
    if (chance(0.3)) fact['decision'] = pick(['approve', 'revise', 'hold', 'defer']);
    if (chance(0.3))
      fact['application_state'] = pick([
        'applied',
        'consumed',
        'pending',
        'unspent',
        'superseded',
        '',
        'weird',
      ]);
    if (chance(0.2))
      fact['contributor'] = { verified: chance(0.5), label: pick(['Worker One', '']) };
    if (chance(0.05)) fact['at'] = 'not-a-number';
    facts.push(fact);
  }
  const factIds = facts
    .map((fact) => fact['fact_id'])
    .filter((id): id is string => typeof id === 'string');
  const someFact = () => (factIds.length ? pick(factIds) : 'none');

  const heads = itemIds
    .filter(() => chance(0.6))
    .map((id) => ({
      work_item_id: id,
      status: pick(['prepared', 'outcome', 'decision', 'current stage', 'requested']),
      stage: pick(['shaping', 'review']),
      latest_meaningful_event: chance(0.1) ? 'missing' : someFact(),
    }));
  const intents = Array.from({ length: int(5) }, (_, index) => ({
    projection_id: `i${String(index)}`,
    // Gaps of seconds, minutes and ten minutes, so the near-duplicate window of fifteen minutes is crossed both ways.
    at: 100 + int(40) * pick([1, 60, 400]),
    summary: pick(SUMMARIES),
    derived_from: chance(0.1) ? 'nope' : someFact(),
  }));
  const steering = Array.from({ length: int(3) }, (_, index) => ({
    projection_id: `s${String(index)}`,
    at: 100 + int(40),
    summary: pick(SUMMARIES),
    derived_from: someFact(),
  }));
  const episodes = intents
    .filter(() => chance(0.5))
    .map((intent) => ({
      intent_id: intent.projection_id,
      adaptation_fact: someFact(),
      confidence: pick(['exact', 'derived', '']),
    }));
  const relations = Array.from({ length: int(6) }, () => {
    const key = `${pick(HARNESSES)}:${pick(SIDS)}`;
    const to = chance(0.8) && itemIds.length ? pick(itemIds) : 'zzz';
    return chance(0.6)
      ? {
          type: 'dispatches_to',
          from: `fo:${key}`,
          to: `task:${to}`,
          evidence_ref: someFact(),
          confidence: pick(['exact', 'derived']),
        }
      : {
          type: pick(['returns_to', 'retries', 'failed_attempt', 'other']),
          from: `task:${to}`,
          to: `fo:${key}`,
          evidence_ref: someFact(),
          confidence: pick(['exact', 'derived']),
        };
  });

  const activity: Record<string, unknown> = {};
  if (!chance(0.3))
    activity['nodes'] = Array.from({ length: int(4) }, () => ({
      kind: pick(['work', 'burst']),
      at: 100 + int(20),
      work_item_ids: itemIds.filter(() => chance(0.4)),
    }));
  if (chance(0.5))
    activity['history_nodes'] = Array.from({ length: int(3) }, () => ({
      kind: pick(['work', 'burst']),
      at: 100 + int(20),
      work_item_ids: itemIds.filter(() => chance(0.4)),
    }));
  if (chance(0.5)) activity['steering'] = steering;

  const semantic: Record<string, unknown> = {
    facts,
    work_items: items,
    relations,
    projections: {
      operator_intents: intents,
      trail_heads: heads,
      steering_episodes: episodes,
      activity,
    },
  };
  if (chance(0.7))
    semantic['history'] = {
      window_sec: pick([86400, 3600, 90, 45, 0]),
      reason: chance(0.1) ? 'The history store could not be read.' : undefined,
      events: chance(0.5)
        ? [
            {
              event_type: 'assignment',
              source_identity: 'codex:obs-1',
              work_binding: pick(itemIds.length ? itemIds : ['x']),
            },
          ]
        : [],
    };
  if (chance(0.05)) semantic['facts'] = 'not a list';

  const delegations = Array.from({ length: int(3) }, (_, index) => ({
    workItemId: chance(0.5) && itemIds.length ? pick(itemIds) : '',
    source: pick(['', 'derived']),
    workflowBinding: chance(0.5) ? '/repo/.spacedock/explore' : '',
    entity: chance(0.5) ? `item-${String(int(5))}` : '',
    observerSid: chance(0.5) ? 'obs-1' : '',
    worker: pick(['Copernicus', 'Aristotle', 'Curie']),
    at: 100 + int(30),
    assignment: 'Fix dispatch authority',
    parentSession: 'codex:a',
    __index: index,
  }));

  const focus = chance(0.5)
    ? { harness: pick(HARNESSES), sid: pick(SIDS), state: pick(['working', 'idle', 'needs_input']) }
    : null;
  const origins = chance(0.5)
    ? Array.from({ length: 1 + int(3) }, () => ({ harness: pick(HARNESSES), sid: pick(SIDS) }))
    : undefined;
  return { semantic, delegations, focus, origins, fallbackSession: chance(0.5) ? 'codex:a' : '' };
}
