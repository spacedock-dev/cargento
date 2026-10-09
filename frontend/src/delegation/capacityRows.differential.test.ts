import { describe, expect, it } from 'vitest';
import { mulberry32, pick, type Rng } from '../observed/generate.test.helper';
import { canonical, firstDifference } from '../observed/legacy.test.helper';
import { loadLegacyCapacity } from '../capacity/legacy.test.helper';
import { capacityRows } from './capacityRows';

/* The order and the figures the Console's capacity panel draws are held to `nextCapacityRows`. Generated
   usage boards publish windows with and without a clock, a reset already in the past, a vendor clock ahead of
   ours, two vendors and an error entry, and the rows must agree in order and in every figure the panel
   prints. */
const legacy = loadLegacyCapacity();

const CASES = 300;
const SEEDS = CASES;
const chance = (rnd: Rng, p: number): boolean => rnd() < p;
const int = (rnd: Rng, low: number, high: number): number =>
  low + Math.floor(rnd() * (high - low + 1));

function windowOf(rnd: Rng, generated: number): Record<string, unknown> | null {
  if (chance(rnd, 0.25)) return null;
  const length = pick(rnd, [18000, 604800, 2592000, 0, null, -5]);
  const window: Record<string, unknown> = {
    pct: pick(rnd, [0, 3, 34, 88, 100, 120, 12.5, null, 'x']),
    windowSec: length,
    resetAt: pick(rnd, [
      generated + 600,
      generated + 3 * 3600,
      generated + 3 * 86400,
      generated - 60,
      generated + 20 * 86400,
      null,
    ]),
  };
  if (chance(rnd, 0.1)) delete window['windowSec'];
  return window;
}

function board(seed: number): Record<string, unknown> {
  const rnd = mulberry32(seed * 977 + 11);
  const generated = 1_800_000_000 + int(rnd, 0, 1000);
  const usage = Array.from({ length: int(rnd, 0, 3) }, () => {
    const entry: Record<string, unknown> = {
      harness: pick(rnd, ['claude', 'cursor', '', 'codex']),
      state: pick(rnd, ['ok', 'ok', 'ok', 'error']),
    };
    for (const slot of ['fiveH', 'week', 'month']) {
      const window = windowOf(rnd, generated);
      if (window) entry[slot] = window;
    }
    return entry;
  });
  const payload: Record<string, unknown> = { generated, usage };
  if (chance(rnd, 0.05)) delete payload['generated'];
  return payload;
}

describe('the capacity panel rows agree with the legacy page', () => {
  it(`over ${String(SEEDS)} generated boards`, () => {
    const failures: string[] = [];
    let rows = 0;
    let timed = 0;
    for (let seed = 1; seed <= SEEDS && failures.length < 3; seed += 1) {
      const payload = board(seed);
      const old = (legacy.rows(payload) ?? []).map((row) => ({
        harness: row['harness'],
        slot: row['slot'],
        pct: row['pct'],
        elapsed: row['elapsed'],
        paceRatio: row['paceRatio'],
        windowMinutesLeft: row['windowMinutesLeft'],
      }));
      const mine = capacityRows(payload);
      const found = firstDifference(canonical(old), canonical(mine));
      if (found) failures.push(`seed ${String(seed)}: ${found}`);
      rows += mine.length;
      timed += mine.filter((row) => row.windowMinutesLeft !== null).length;
    }
    expect(failures).toEqual([]);
    expect(rows).toBeGreaterThan(200);
    expect(timed).toBeGreaterThan(50);
  });
});
