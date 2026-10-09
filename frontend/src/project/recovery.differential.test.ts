import { describe, expect, it } from 'vitest';
import { nextNumber } from '../api/bootstrap';
import { observe } from '../observed';
import { canonical, firstDifference } from '../observed/legacy.test.helper';
import { harnessLabels } from '../sessions/rows';
import { genBoard, genContext } from './generate.test.helper';
import { arrange, entryFor, labelsOf, type Variant } from './arrange.test.helper';
import { groupFor, sessKey } from './group';
import {
  attentionCoverage,
  authorityVerb,
  commandAttention,
  recoveryBriefing,
  type RecoveryEnv,
} from './recovery';

/* The recovery briefing and everything it stands on (attention coverage, the command attention list, the
   children, the assignment, the latest direction and result, and the text the More menu copies), held to
   the real legacy functions over generated boards and project-context reads. */

const CASES = 40;
const SEEDS = CASES;

const VARIANTS: readonly Variant[] = ['ready', 'ready', 'stale', 'failed', 'absent'];

describe('the recovery briefing reads as the legacy briefing does', () => {
  it(`agrees on ${String(SEEDS)} generated boards, project by project and read by read`, () => {
    const failures: string[] = [];
    for (let seed = 1; seed <= SEEDS; seed += 1) {
      const board = genBoard(seed);
      const context = genContext(seed, board);
      const variant = VARIANTS[seed % VARIANTS.length] as Variant;
      for (const label of labelsOf(board)) {
        const made = arrange(board, context, label, variant);
        if (!made) continue;
        const { app, legacyGroup, env, entry } = made;
        const observation = entry?.data ?? null;
        const at = `seed ${String(seed)} ${variant} ${JSON.stringify(label)}`;
        const check = (name: string, left: unknown, right: unknown) => {
          const found = firstDifference(canonical(left), canonical(right));
          if (found) failures.push(`${at} ${name}: ${found}`);
        };
        try {
          check(
            'coverage',
            app.run('nextCockpitAttentionCoverage(__group, __observation)', {
              group: legacyGroup,
              observation,
            }),
            attentionCoverage(entry),
          );
          const legacyAttention = app.run<unknown[]>(
            'nextCockpitCommandAttention(__group, __observation)',
            { group: legacyGroup, observation },
          );
          const attention = commandAttention(env);
          check('attention', legacyAttention, attention);
          check(
            'verbs',
            legacyAttention.map((item) => app.run('nextCockpitAuthorityVerb(__item)', { item })),
            attention.map((item) => authorityVerb(item)),
          );
          // The focused scope and a pair of browser-local notes, so the briefing's optional lines are reached.
          const rows = env.group.sessions;
          const focus = seed % 3 === 0 && rows.length ? (rows[seed % rows.length] ?? null) : null;
          const notes =
            seed % 2 === 0
              ? { outcome: 'Land the queue', currentFocus: 'The drain' }
              : { outcome: '', currentFocus: '' };
          app.run(
            `nextCockpitMemoDrafts.clear();
             if(__notes.outcome) nextCockpitMemoDrafts.set(nextCockpitMemoKey(__group, __focus, "outcome"), __notes.outcome);
             if(__notes.currentFocus) nextCockpitMemoDrafts.set(nextCockpitMemoKey(__group, __focus, "focus"), __notes.currentFocus);`,
            { group: legacyGroup, focus, notes },
          );
          const legacyFocus = focus
            ? (app
                .run<unknown[]>('__group.sessions', { group: legacyGroup })
                .find((row) => sessKey(row as never) === sessKey(focus)) ?? null)
            : null;
          const legacyBriefing = app.run<Record<string, unknown>>(
            'nextCockpitRecoveryBriefing(__group, __focus, __observation, __attention)',
            { group: legacyGroup, focus: legacyFocus, observation, attention: legacyAttention },
          );
          const briefing = recoveryBriefing({
            env,
            focus,
            attention,
            outcome: notes.outcome,
            currentFocus: notes.currentFocus,
          });
          check('briefing', legacyBriefing, briefing);
        } catch (error) {
          failures.push(`${at}: threw ${String((error as Error).stack ?? error).slice(0, 400)}`);
        }
        if (failures.length >= 3) break;
      }
      if (failures.length >= 3) break;
    }
    expect(failures).toEqual([]);
  }, 300_000);

  it('reaches the states that make agreement mean something', () => {
    const seen = {
      captain: 0,
      fo: 0,
      incomplete: 0,
      unavailable: 0,
      assignmentFromState: 0,
      assignmentFromDirection: 0,
      returnedChild: 0,
      activeChild: 0,
      semanticResult: 0,
      sessionResult: 0,
      decisions: 0,
      noted: 0,
    };
    for (let seed = 1; seed <= SEEDS; seed += 1) {
      const board = genBoard(seed);
      const context = genContext(seed, board);
      for (const label of labelsOf(board)) {
        const group = groupFor(board, observe(board), label);
        if (!group) continue;
        const env: RecoveryEnv = {
          group,
          generated: nextNumber(board['generated']),
          harnesses: harnessLabels(board),
          entry: entryFor('ready', context),
        };
        const attention = commandAttention(env);
        const briefing = recoveryBriefing({
          env,
          focus: null,
          attention,
          outcome: seed % 2 ? 'x' : '',
          currentFocus: '',
        });
        if (attention.some((item) => item.owner === 'CAPTAIN')) seen.captain += 1;
        if (attention.some((item) => item.owner === 'FO')) seen.fo += 1;
        if (briefing.coverage.state === 'incomplete') seen.incomplete += 1;
        if (briefing.coverage.state === 'unavailable') seen.unavailable += 1;
        if (briefing.task.provenance === 'Exact workflow state') seen.assignmentFromState += 1;
        if (briefing.task.provenance === 'Exact operator direction')
          seen.assignmentFromDirection += 1;
        if (briefing.children.latestReturn) seen.returnedChild += 1;
        if (briefing.children.active.length) seen.activeChild += 1;
        if (briefing.latest.resultKind === 'semantic') seen.semanticResult += 1;
        if (briefing.latest.resultKind === 'session') seen.sessionResult += 1;
        if (briefing.decisions !== 'No captain decisions observed') seen.decisions += 1;
        if (briefing.outcome !== 'Not set') seen.noted += 1;
      }
    }
    for (const [name, count] of Object.entries(seen)) expect(count, name).toBeGreaterThan(0);
  });
});
