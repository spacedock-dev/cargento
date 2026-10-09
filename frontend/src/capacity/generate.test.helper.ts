import { mulberry32, pick, type Rng } from '../observed/generate.test.helper';

/* Seeded usage boards for the capacity differential tests. The generator leans on what costs most when
   wrong: a window with no clock, a reset already in the past, a vendor clock ahead of ours, a budget exactly
   spent, a measured zero recent pace against an absent one, two entries for one vendor, a hostile or
   over-long model label, a fraction or a string where a level belongs, and a history with idle gaps. */
const chance = (rnd: Rng, p: number): boolean => rnd() < p;
const int = (rnd: Rng, low: number, high: number): number =>
  low + Math.floor(rnd() * (high - low + 1));

const LABELS = [
  'Opus',
  'Sonnet',
  '',
  '   ',
  '<b>x</b>',
  'ünï çødé',
  'z'.repeat(60),
  '  padded  ',
  5,
  null,
] as const;
const PROJECTS = ['alpha/app', 'beta/api', '', 'ünï/çødé'] as const;

function recentOf(rnd: Rng): unknown {
  if (chance(rnd, 0.35)) return undefined;
  if (chance(rnd, 0.05)) return 'later';
  if (chance(rnd, 0.05)) return null;
  const recent: Record<string, unknown> = {
    pctPerMin: pick(rnd, [0, 0.05, 0.4, 2, -1, null, 'x', 0.5]),
    samples: pick(rnd, [2, 3, 10, null, 1.5]),
    spanSec: pick(rnd, [1800, 600, 59, null, 0, 7200]),
  };
  if (chance(rnd, 0.1)) delete recent['pctPerMin'];
  return recent;
}

function windowOf(rnd: Rng, generated: number): Record<string, unknown> | null {
  if (chance(rnd, 0.2)) return null;
  if (chance(rnd, 0.03)) return [] as unknown as Record<string, unknown>;
  const window: Record<string, unknown> = {
    pct: pick(rnd, [0, 3, 8, 34, 50, 88, 100, 120, 12.5, null, 'x']),
    windowSec: pick(rnd, [18000, 604800, 2592000, 0, null, -5]),
    resetAt: pick(rnd, [
      generated + 600,
      generated + 3 * 3600,
      generated + 4.9 * 3600,
      generated + 3 * 86400,
      generated + 20 * 86400,
      generated + 30 * 86400 * 4,
      generated - 60,
      generated + 90000,
      null,
    ]),
  };
  const recent = recentOf(rnd);
  if (recent !== undefined) window['recent'] = recent;
  if (chance(rnd, 0.08)) delete window['windowSec'];
  return window;
}

function modelsOf(rnd: Rng): unknown {
  if (chance(rnd, 0.4)) return undefined;
  if (chance(rnd, 0.05)) return { not: 'a list' };
  return Array.from({ length: int(rnd, 0, 11) }, () =>
    chance(rnd, 0.05)
      ? null
      : { label: pick(rnd, LABELS), pct: pick(rnd, [0, 12, 71, 100, 4.5, '3', null]) },
  );
}

export interface CapacityCase {
  readonly payload: Record<string, unknown>;
  /** The harnesses the strip names, used to pick a selection that may or may not be published. */
  readonly keys: readonly string[];
}

export function genCapacity(seed: number): CapacityCase {
  const rnd = mulberry32(seed * 977 + 11);
  // A time of day anywhere in the day, so the clock words cross midnight and the week.
  const generated = 1_800_000_000 + int(rnd, 0, 86_399);
  const usage: Record<string, unknown>[] = Array.from({ length: int(rnd, 0, 3) }, () => {
    const entry: Record<string, unknown> = {
      harness: pick(rnd, ['claude', 'cursor', 'codex', '', 'claude']),
      state: pick(rnd, ['ok', 'ok', 'ok', 'error']),
      asOf: pick(rnd, [generated - 30, generated - 4000, null, 'x']),
    };
    for (const slot of ['fiveH', 'week', 'month']) {
      const window = windowOf(rnd, generated);
      if (window) entry[slot] = window;
    }
    const models = modelsOf(rnd);
    if (models !== undefined) entry['models'] = models;
    return entry;
  });
  if (chance(rnd, 0.05)) usage.push(null as unknown as Record<string, unknown>);
  const payload: Record<string, unknown> = { generated, usage };
  if (chance(rnd, 0.05)) delete payload['generated'];
  if (chance(rnd, 0.05)) payload['usage'] = 'none';
  if (chance(rnd, 0.6)) payload['usage_fetch'] = pick(rnd, [true, true, false, 'yes']);
  const harnesses = [
    { key: 'claude', label: pick(rnd, ['Claude Code', '', 'Claude <b>']) },
    { key: 'cursor', label: 'Cursor' },
  ];
  if (chance(rnd, 0.9)) payload['harnesses'] = harnesses;
  if (chance(rnd, 0.8)) {
    // Distinct sids so a project can reach the two-session floor, one of them sometimes shared across harnesses.
    const pool = Array.from({ length: int(rnd, 1, 6) }, (_, index) => ({
      harness: pick(rnd, ['claude', 'claude', 'cursor', 'codex']),
      sid: chance(rnd, 0.1) ? '' : `s${String(index)}`,
      project: pick(rnd, PROJECTS),
      // Seen but never working: the sessions the spread must count rather than drop.
      quiet: chance(rnd, 0.3),
    }));
    const history: unknown[] = [];
    for (let index = 0, count = int(rnd, 0, 60); index < count; index += 1) {
      const { quiet, ...who } = pick(rnd, pool);
      const record: Record<string, unknown> = {
        ...who,
        state: quiet ? 'idle' : pick(rnd, ['working', 'idle', 'working', 'needs_input', 'bogus']),
        last_activity: generated - rnd() * pick(rnd, [3600, 86400, 3 * 86400]),
      };
      if (chance(rnd, 0.04)) delete record['last_activity'];
      history.push(chance(rnd, 0.02) ? null : record);
    }
    payload['history'] = history;
  }
  const keys = usage.flatMap((entry) =>
    entry && typeof entry === 'object'
      ? ['fiveH', 'week', 'month'].map((slot) => `${String(entry['harness'] || '')}:${slot}`)
      : [],
  );
  return { payload, keys };
}
