import { mulberry32, pick, type Rng } from '../observed/generate.test.helper';

/* Seeded `tripwires` sections for the stage-condition differential: a board with the feature off, one whose
   source reads are off, an ambiguous workflow, a source with no generation, a rule whose source has gone, a
   rule saved against a stage the source no longer has, a tripped rule with and without a browser lane, and
   shapes a replaced file could hold. Every value is JSON-representable. */
const chance = (rnd: Rng, p: number): boolean => rnd() < p;
const int = (rnd: Rng, low: number, high: number): number =>
  low + Math.floor(rnd() * (high - low + 1));

const STAGES = ['plan', 'build', 'review', 'ship', 'ünï', ''] as const;
const HARNESSES = ['claude', 'codex'] as const;
const SIDS = ['s1', 's2', 'a:b'] as const;

export interface TripwireCase {
  readonly payload: Record<string, unknown>;
  readonly scope: { harness: string; sid: string }[] | null;
  readonly drafts: [string, string][];
  readonly notification: string | null;
}

export function genTripwires(seed: number): TripwireCase {
  const rnd = mulberry32(seed * 7907 + 29);
  const sources = Array.from({ length: int(rnd, 0, 3) }, (_, index) => ({
    id: `wf-${String(index)}`,
    workflow: pick(rnd, ['Ship the queue', '<b>Workflow</b>', 'ünï flow', '']),
    goal: pick(rnd, ['Drain the retry queue', '', 'Goal with "quotes" & <tags>']),
    // A workflow's stages are a set. Two options of one name would be selected by the page and by the
    // component differently (the last wins in markup, the first in a controlled list) and read the same.
    stages: [...new Set(Array.from({ length: int(rnd, 0, 4) }, () => pick(rnd, STAGES)))],
    generation: pick(rnd, [1, 1, 1, 0, null]),
    ambiguous: chance(rnd, 0.15),
    sessions: Array.from({ length: int(rnd, 0, 3) }, () => ({
      label: pick(rnd, ['alpha', 'beta', '']),
      harness: pick(rnd, HARNESSES),
      sid: pick(rnd, SIDS),
    })),
    entities: Array.from({ length: int(rnd, 0, 5) }, () => ({})),
    partial: chance(rnd, 0.3),
  }));
  const rules = [
    ...sources
      .filter(() => chance(rnd, 0.6))
      .map((source) => ruleFor(rnd, source.id, source.stages)),
    ...(chance(rnd, 0.25) ? [ruleFor(rnd, 'wf-gone', [])] : []),
  ];
  const tripwires: Record<string, unknown> = {
    enabled: chance(rnd, 0.9),
    sources,
    rules,
  };
  if (chance(rnd, 0.2)) tripwires['source_enabled'] = false;
  if (chance(rnd, 0.1)) tripwires['error'] = pick(rnd, ['The store is unreadable', '<i>bad</i>']);
  const payload: Record<string, unknown> = { generated: 1000, sessions: [], tripwires };
  if (chance(rnd, 0.1)) delete payload['tripwires'];
  if (chance(rnd, 0.25)) payload['native_notify'] = true;
  const scope = chance(rnd, 0.4)
    ? null
    : Array.from({ length: int(rnd, 0, 2) }, () => ({
        harness: pick(rnd, HARNESSES),
        sid: pick(rnd, SIDS),
      }));
  return {
    payload,
    scope,
    drafts: sources
      .filter(() => chance(rnd, 0.3))
      .map((source) => [source.id, pick(rnd, STAGES)] as [string, string]),
    notification: chance(rnd, 0.4) ? pick(rnd, ['granted', 'denied', 'default']) : null,
  };
}

function ruleFor(rnd: Rng, id: string, stages: readonly string[]): Record<string, unknown> {
  const rule: Record<string, unknown> = {
    id,
    workflow: pick(rnd, ['Ship the queue', 'Saved flow']),
    stage: chance(rnd, 0.8) && stages.length ? pick(rnd, stages) : pick(rnd, STAGES),
    state: pick(rnd, ['armed', 'tripped', 'unavailable']),
    available: chance(rnd, 0.75),
    revision: pick(rnd, ['r1', 'r2', '']),
    why: pick(rnd, ['Armed on the first sight', '', 'Entered review']),
    delivery_why: pick(rnd, ['Delivered by the server', '', 'Native lane is off']),
  };
  if (chance(rnd, 0.5)) {
    rule['trip'] = {
      before_observed_at: 1_700_000_000 + int(rnd, 0, 99999),
      observed_at: 1_700_100_000 + int(rnd, 0, 99999),
      source_written_at: 1_700_050_000 + int(rnd, 0, 99999),
    };
  }
  return rule;
}
