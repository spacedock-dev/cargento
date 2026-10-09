import { describe, expect, it } from 'vitest';
import { canonical, firstDifference } from '../observed/legacy.test.helper';
import { genWindow } from './generate.test.helper';
import { loadLegacyDelegation } from './legacy.test.helper';
import { windowLabel, type ProjectWindow } from '../workstream/model';
import { metricOf, trendOf, type Range } from './metric';

/* The arithmetic alone, over windows the replay would never produce on its own: batches with no rows, an end
   before the start, a stamp of the wrong type, a seeded and an unseeded window, a rate that is negative or
   known on some rows and not others. */
const legacy = loadLegacyDelegation();
const CASES = 300;
const SEEDS = CASES;

describe('delegation metric, trend and caption agree with the legacy page', () => {
  it(`over ${String(SEEDS)} generated windows`, () => {
    const failures: string[] = [];
    let trends = 0;
    let figures = 0;
    for (let seed = 1; seed <= SEEDS && failures.length < 3; seed += 1) {
      const window = genWindow(seed);
      const mine = window as unknown as ProjectWindow;
      const metric = firstDifference(
        canonical(legacy.metric(window)),
        canonical(metricOf(mine) satisfies Range),
      );
      const trend = legacy.trend(window);
      const label = legacy.label(window);
      if (metric) failures.push(`seed ${String(seed)} metric: ${metric}`);
      else if (trend !== trendOf(mine))
        failures.push(`seed ${String(seed)} trend: ${String(trend)} != ${String(trendOf(mine))}`);
      else if (label !== windowLabel(mine))
        failures.push(`seed ${String(seed)} label: ${label} != ${windowLabel(mine)}`);
      if (trend !== null) trends += 1;
      if (metricOf(mine).delegatedPct !== null) figures += 1;
    }
    expect(failures).toEqual([]);
    expect(trends).toBeGreaterThan(3);
    expect(figures).toBeGreaterThan(150);
  });
});
