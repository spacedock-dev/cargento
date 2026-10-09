import { mulberry32, pick, type Rng } from '../observed/generate.test.helper';

/* Seeded boards for the delegation differential tests. A scenario is a stored history and a sequence of
   accepted payloads, the two things the page's memory is built from. The generator leans on what costs most
   when wrong: a final stored record that closes a span, a session that leaves a gate and resumes through
   idle, one sid under two harnesses, a rate that is known for one harness and unknown for another, a clock
   that does not advance, steps wide enough to cross the ten-minute floor and the two six-hour readings, and
   fields of the wrong type. */
const chance = (rnd: Rng, p: number): boolean => rnd() < p;
const int = (rnd: Rng, low: number, high: number): number =>
  low + Math.floor(rnd() * (high - low + 1));

const PROJECTS = ['alpha/app', 'beta/api', '', 'ünï/çødé'] as const;
const HARNESSES = ['claude', 'codex', 'ghost', ''] as const;
const SIDS = ['s1', 's2', 'shared', 'a:b', '', 'x y'] as const;
const STATES = ['working', 'idle', 'needs_input', 'working', 'idle', 'bogus', ''] as const;
const QUESTIONS = ['Approve?', '', null, 'Run the suite?'] as const;

export interface Scenario {
  readonly start: number;
  readonly payloads: Record<string, unknown>[];
  readonly projects: readonly string[];
}

function harnessRows(rnd: Rng): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [
    { key: 'claude', label: 'Claude Code', reports_rate: chance(rnd, 0.7) },
  ];
  if (chance(rnd, 0.8)) {
    rows.push(
      chance(rnd, 0.3)
        ? { key: 'codex', label: 'Codex', error: 'unreadable' }
        : { key: 'codex', label: chance(rnd, 0.2) ? '' : 'Codex' },
    );
  }
  if (chance(rnd, 0.1)) rows.push({ key: 7, label: null });
  return rows;
}

function history(rnd: Rng, start: number): unknown[] | undefined {
  if (chance(rnd, 0.25)) return undefined;
  if (chance(rnd, 0.05)) return [] as unknown[];
  const entries: unknown[] = [];
  const count = int(rnd, 0, 40);
  const reach = pick(rnd, [3600, 4 * 3600, 20 * 3600, 3 * 86400, 14 * 86400]);
  for (let index = 0; index < count; index += 1) {
    const entry: Record<string, unknown> = {
      harness: pick(rnd, HARNESSES),
      sid: pick(rnd, SIDS),
      project: pick(rnd, PROJECTS),
      state: pick(rnd, STATES),
      last_activity: start - rnd() * reach,
    };
    if (chance(rnd, 0.04)) delete entry['last_activity'];
    if (chance(rnd, 0.04)) entry['last_activity'] = 'soon';
    if (chance(rnd, 0.03)) entry['last_activity'] = start + 500;
    if (chance(rnd, 0.03)) entry['sid'] = '';
    if (chance(rnd, 0.03)) delete entry['state'];
    entries.push(chance(rnd, 0.02) ? null : entry);
  }
  return entries;
}

export function genScenario(seed: number): Scenario {
  const rnd = mulberry32(seed * 7919 + 17);
  const start = 1_800_000_000 + int(rnd, 0, 86400);
  const harnesses = harnessRows(rnd);
  const pool = Array.from({ length: int(rnd, 1, 5) }, () => ({
    harness: pick(rnd, HARNESSES),
    sid: pick(rnd, SIDS),
    project: pick(rnd, PROJECTS),
  }));
  const stored = history(rnd, start);
  const payloads: Record<string, unknown>[] = [];
  let at = start;
  const step = pick(rnd, [5, 30, 600, 1800, 3 * 3600, 7 * 3600]);
  const count = int(rnd, 1, chance(rnd, 0.3) ? 40 : 14);
  const states = new Map<number, string>();
  // A stop stamped ahead of the payload that carries it and published unchanged until the clock reaches it:
  // the case the guard on a repeated stamp exists for.
  const ahead = new Map<number, number>();
  for (let index = 0; index < count; index += 1) {
    if (index > 0) at += chance(rnd, 0.05) ? 0 : int(rnd, 1, step) * (chance(rnd, 0.03) ? -1 : 1);
    const sessions = pool.map((member, slot) => {
      if (chance(rnd, 0.25) || !states.has(slot)) states.set(slot, pick(rnd, STATES));
      const row: Record<string, unknown> = {
        ...member,
        state: states.get(slot),
        rate_per_min: chance(rnd, 0.6) ? int(rnd, 0, 4000) : chance(rnd, 0.2) ? -50 : null,
      };
      if (chance(rnd, 0.15)) row['finished_at'] = at - int(rnd, 0, 40);
      if (!ahead.has(slot) && chance(rnd, 0.12)) ahead.set(slot, at + int(rnd, 1, step * 2));
      if (ahead.has(slot) && chance(rnd, 0.9)) row['finished_at'] = ahead.get(slot);
      if (chance(rnd, 0.03)) row['rate_per_min'] = 'fast';
      if (chance(rnd, 0.03)) delete row['project'];
      return row;
    });
    if (chance(rnd, 0.08))
      sessions.push(sessions[0] ? { ...sessions[0], state: pick(rnd, STATES) } : {});
    const payload: Record<string, unknown> = {
      generated: at,
      sessions,
      harnesses,
      asks: chance(rnd, 0.35)
        ? Array.from({ length: int(rnd, 1, 3) }, () => ({
            id: `ask-${String(int(rnd, 1, 6))}`,
            harness: pick(rnd, HARNESSES),
            session_id: pick(rnd, SIDS),
            project: pick(rnd, PROJECTS),
            question: pick(rnd, QUESTIONS),
            age_sec: pick(rnd, [3, 400, -4, null, 'x']),
          }))
        : [],
    };
    if (stored !== undefined && index <= 1) payload['history'] = stored;
    if (chance(rnd, 0.03)) delete payload['generated'];
    if (chance(rnd, 0.03)) payload['sessions'] = 'none';
    payloads.push(payload);
  }
  return { start, payloads, projects: [...PROJECTS] };
}

/* A window the way `nextWorkstreamProjectWindow` hands it to the arithmetic, built directly so the
   functions are held across shapes the replay would not produce: batches with no rows, an end before the
   start, a missing stamp, a stamp of the wrong type and a window the store seeded. */
export function genWindow(seed: number): Record<string, unknown> {
  const rnd = mulberry32(seed * 104729 + 3);
  const endedAt = 1_800_000_000 + int(rnd, 0, 3600);
  const reach = pick(rnd, [300, 900, 7200, 6 * 3600, 13 * 3600, 30 * 3600, 3 * 86400]);
  const startedAt = endedAt - reach * (0.5 + rnd());
  const batches: Record<string, unknown>[] = [];
  const events: Record<string, unknown>[] = [];
  const count = int(rnd, 0, 60);
  let at = startedAt;
  for (let index = 0; index < count; index += 1) {
    at += (reach / Math.max(1, count)) * (0.2 + 1.6 * rnd());
    const rows = Array.from({ length: chance(rnd, 0.15) ? 0 : int(rnd, 1, 3) }, () => {
      const rate = chance(rnd, 0.5) ? int(rnd, 0, 3000) : null;
      const sign = chance(rnd, 0.05) ? -1 : 1;
      return {
        at,
        harness: pick(rnd, HARNESSES),
        kind: 'sample',
        project: 'p',
        rate: rate === null ? null : sign * rate,
        rateKnown: chance(rnd, 0.6),
        sid: pick(rnd, SIDS),
        state: pick(rnd, STATES),
      };
    });
    batches.push({ at: chance(rnd, 0.03) ? 'x' : at, rows });
    if (chance(rnd, 0.35)) {
      const from = pick(rnd, STATES);
      const to = pick(rnd, STATES);
      events.push({
        at: chance(rnd, 0.03) ? null : at - rnd() * 100,
        harness: pick(rnd, HARNESSES),
        kind: chance(rnd, 0.9) ? 'state' : 'ask',
        sid: pick(rnd, SIDS),
        fromState: from,
        toState: to,
        state: to,
        filled: true,
        label: 'x',
        project: 'p',
        right: 'y',
      });
    }
  }
  const window: Record<string, unknown> = {
    batches,
    endedAt: chance(rnd, 0.05) ? null : endedAt,
    events,
    samples: [],
    seeded: chance(rnd, 0.4),
    startedAt: chance(rnd, 0.05) ? null : startedAt,
  };
  if (chance(rnd, 0.03)) window['endedAt'] = startedAt - 5;
  return window;
}
