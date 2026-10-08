import { mulberry32, pick, type Rng } from '../observed/generate.test.helper';

/* Payload sequences for the workstream differentials: a board that advances (or does not), with a history
   store behind it and the hostile shapes a replaced file or an older server could hold. Seeded, so a
   failing sequence is reproducible by number. Every value is JSON-representable. */
const chance = (rnd: Rng, p: number): boolean => rnd() < p;
const int = (rnd: Rng, low: number, high: number): number =>
  low + Math.floor(rnd() * (high - low + 1));

const PROJECTS = ['alpha/app', 'beta/api', '', 'ünï/çødé', 'gamma', 'alpha/app '] as const;
const HARNESSES = ['claude', 'codex', 'pi', '', 'ghost'] as const;
const SIDS = ['s1', 's2', 's3', 'colon:sid', 'ünï', 'x y', '0'] as const;
const STATES = ['working', 'idle', 'needs_input', 'bogus', '', null, 7] as const;

function genHistory(rnd: Rng, generated: number): unknown {
  if (chance(rnd, 0.15)) return pick(rnd, [undefined, null, 'x', 4, {}, []]);
  const count = int(rnd, 0, 14);
  const rows: unknown[] = [];
  for (let index = 0; index < count; index += 1) {
    if (chance(rnd, 0.06)) {
      rows.push(pick(rnd, [null, 'row', 3, [1]]));
      continue;
    }
    const row: Record<string, unknown> = {};
    if (!chance(rnd, 0.05)) row['sid'] = pick(rnd, SIDS);
    if (!chance(rnd, 0.1)) row['harness'] = pick(rnd, HARNESSES);
    if (!chance(rnd, 0.1)) row['project'] = pick(rnd, PROJECTS);
    const state = pick(rnd, STATES);
    if (state !== null) row['state'] = state;
    const at = chance(rnd, 0.08)
      ? pick(rnd, [null, 'soon', generated + 500, -3, 0])
      : generated - int(rnd, 1, 40_000) + (chance(rnd, 0.2) ? 0.5 : 0);
    row['last_activity'] = at;
    rows.push(row);
  }
  return rows;
}

function genSessions(rnd: Rng, generated: number): unknown[] {
  const count = int(rnd, 0, 6);
  const out: unknown[] = [];
  for (let index = 0; index < count; index += 1) {
    if (chance(rnd, 0.05)) {
      out.push(pick(rnd, [null, 'row', 3]));
      continue;
    }
    const row: Record<string, unknown> = {
      harness: pick(rnd, HARNESSES),
      sid: pick(rnd, SIDS),
      project: pick(rnd, PROJECTS),
      state: pick(rnd, STATES),
    };
    if (chance(rnd, 0.6)) row['rate_per_min'] = pick(rnd, [0, 1, 12.5, -2, null, 'fast', 1800]);
    if (chance(rnd, 0.3))
      row['finished_at'] = pick(rnd, [
        null,
        0,
        'never',
        generated - 3,
        generated - 200,
        generated + 4,
      ]);
    out.push(row);
  }
  return out;
}

function genAsks(rnd: Rng): unknown {
  if (chance(rnd, 0.1)) return pick(rnd, [undefined, 'x', {}]);
  const count = int(rnd, 0, 3);
  const out: unknown[] = [];
  for (let index = 0; index < count; index += 1) {
    out.push(
      chance(rnd, 0.1)
        ? null
        : {
            id: pick(rnd, ['a1', 'a2', 'a3', '', undefined, 7]),
            harness: pick(rnd, HARNESSES),
            session_id: pick(rnd, SIDS),
            project: pick(rnd, PROJECTS),
            question: pick(rnd, ['Which branch?', '', undefined, 'Ünï?']),
            age_sec: pick(rnd, [0, 5, 30, 4000, -1, null, 'old']),
          },
    );
  }
  return out;
}

function genHarnesses(rnd: Rng): unknown {
  if (chance(rnd, 0.1)) return pick(rnd, [undefined, 'x', {}]);
  return HARNESSES.filter(() => chance(rnd, 0.6)).map((key) => ({
    key,
    label: pick(rnd, ['Claude Code', '', '  ', undefined, 'Codex']),
    ...(chance(rnd, 0.5) ? { reports_rate: pick(rnd, [true, false, 'yes']) } : {}),
    ...(chance(rnd, 0.1) ? { error: 'unreadable' } : {}),
  }));
}

/* A run of payloads: mostly advancing by a poll, sometimes repeating a clock, going backwards or arriving
   with none. The first carries the history the tab seeds from; later ones carry it too, which the page
   reads only once. */
export function genSequence(seed: number): unknown[] {
  const rnd = mulberry32(seed);
  const length = int(rnd, 1, 6);
  let generated = 100_000;
  const out: unknown[] = [];
  for (let index = 0; index < length; index += 1) {
    generated += chance(rnd, 0.1) ? pick(rnd, [0, -30]) : int(rnd, 5, 600);
    const body: Record<string, unknown> = {
      sessions: genSessions(rnd, generated),
      asks: genAsks(rnd),
      harnesses: genHarnesses(rnd),
      history: genHistory(rnd, generated),
    };
    if (!chance(rnd, 0.05))
      body['generated'] = chance(rnd, 0.05) ? pick(rnd, ['soon', null]) : generated;
    out.push(chance(rnd, 0.03) ? pick(rnd, [null, 'x', 5, []]) : body);
  }
  return out;
}
