import { describe, expect, it } from 'vitest';
import { canonical, firstDifference } from '../observed/legacy.test.helper';
import { genScenario } from './generate.test.helper';
import { loadLegacyDelegation } from './legacy.test.helper';
import { delegationFigure } from './metric';
import { createWorkstream, projectWindow } from '../workstream/model';

/* The tab's memory is held to the page's own. Generated boards (a stored history and a run of accepted
   payloads) go through the real `nextObserveWorkstream` and through `createEvidence`, and after every payload
   the window each project reads, and the delegation rows printed from it, must agree. A failure names the
   seed, the payload and the first path that differs. */
const legacy = loadLegacyDelegation();
const CASES = 12;
const SEEDS = CASES;

describe('the evidence store and the delegation rows agree with the legacy page', () => {
  it(`over ${String(SEEDS)} generated boards`, () => {
    const failures: string[] = [];
    let compared = 0;
    let known = 0;
    for (let seed = 1; seed <= SEEDS && failures.length < 3; seed += 1) {
      const scenario = genScenario(seed);
      legacy.reset();
      const evidence = createWorkstream();
      for (const [index, payload] of scenario.payloads.entries()) {
        legacy.observe(payload);
        evidence.observe(payload);
        for (const project of scenario.projects) {
          const window = projectWindow(project, evidence.snapshot());
          const theirs = legacy.window(project);
          const where = `seed ${String(seed)} payload ${String(index)} project ${JSON.stringify(project)}`;
          const window_ = firstDifference(canonical(theirs), canonical(window));
          if (window_) failures.push(`${where} window: ${window_}`);
          const figure = firstDifference(
            canonical(legacy.history(project)['delegation']),
            canonical(delegationFigure(window)),
          );
          if (figure) failures.push(`${where} figure: ${figure}`);
          compared += 1;
          if (delegationFigure(window).pctKnown) known += 1;
        }
        if (failures.length) break;
      }
    }
    expect(failures).toEqual([]);
    // The comparison is not vacuous: a good share of the windows reached a figure.
    expect(compared).toBeGreaterThan(300);
    expect(known).toBeGreaterThan(40);
  });
});
