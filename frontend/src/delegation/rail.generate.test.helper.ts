import { genPayload, mulberry32, pick, type Rng } from '../observed/generate.test.helper';

/* A board for the Console rail differential: the observed model's own generated payload (every shape a real
   board holds), given a clock the usage windows and the history can be placed against, and a stored history
   long enough that the delegation figure is sometimes known. A second payload follows it, a little later, so
   the figure is measured over time this tab observed as well as time it was told about. */
const chance = (rnd: Rng, p: number): boolean => rnd() < p;
const int = (rnd: Rng, low: number, high: number): number =>
  low + Math.floor(rnd() * (high - low + 1));

export interface RailCase {
  readonly first: Record<string, unknown>;
  readonly second: Record<string, unknown>;
  readonly capability: string;
}

type Row = Record<string, unknown>;

export function genRailCase(seed: number): RailCase {
  const rnd = mulberry32(seed * 6151 + 7);
  const base = 1_800_000_000 + int(rnd, 0, 86400);
  const payload = genPayload(seed, { wellFormed: true });
  payload['generated'] = base;
  // The usage windows genPayload placed against a clock of 1000, moved onto this one.
  for (const entry of Array.isArray(payload['usage']) ? (payload['usage'] as unknown[]) : []) {
    if (typeof entry !== 'object' || entry === null) continue;
    // An entry that names no harness has no key to join its window to, and the legacy rail throws on it
    // (`window.paceKnown` of undefined). The component draws it, with the absence said; its own test holds that.
    if (
      !(entry as Row)['harness'] ||
      String((entry as Row)['harness']).trim() !== (entry as Row)['harness']
    )
      (entry as Row)['harness'] = pick(rnd, ['claude', 'codex']);
    for (const slot of ['fiveH', 'week', 'month']) {
      const window = (entry as Row)[slot];
      if (
        typeof window === 'object' &&
        window !== null &&
        typeof (window as Row)['resetAt'] === 'number'
      )
        (window as Row)['resetAt'] = base + pick(rnd, [600, 3 * 3600, 3 * 86400, -60]);
    }
  }
  const sessions = (Array.isArray(payload['sessions']) ? payload['sessions'] : []) as Row[];
  // A sid with padding: the copy control names the trimmed one and the resume command the published one.
  for (const session of sessions)
    if (chance(rnd, 0.12)) session['sid'] = ` pad ${String(int(rnd, 0, 9))} `;
  const history: Row[] = [];
  if (chance(rnd, 0.75)) {
    const reach = pick(rnd, [3600, 4 * 3600, 20 * 3600, 3 * 86400]);
    for (const session of sessions) {
      const count = int(rnd, 1, 8);
      for (let index = 0; index < count; index += 1) {
        history.push({
          harness: session['harness'],
          sid: session['sid'],
          project: session['project'],
          state: pick(rnd, ['working', 'idle', 'needs_input', 'working']),
          last_activity: base - rnd() * reach,
        });
      }
    }
    payload['history'] = history;
  }
  const first = JSON.parse(JSON.stringify(payload)) as Row;
  // A later board: the clock advanced, some sessions changed state, and a stop landed.
  const step = pick(rnd, [30, 900, 3 * 3600, 8 * 3600]);
  const second = JSON.parse(JSON.stringify(payload)) as Row;
  second['generated'] = base + step;
  for (const session of (second['sessions'] as Row[]) ?? []) {
    if (chance(rnd, 0.4)) session['state'] = pick(rnd, ['working', 'idle', 'needs_input']);
    if (chance(rnd, 0.15)) session['finished_at'] = base + int(rnd, 1, step);
  }
  return { first, second, capability: chance(rnd, 0.6) ? 'cap-token' : '' };
}
