import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { check, fact, json, mountDrift, press, textOf } from './testing';

/* A press reads a session's messages back to its window start, which can be further than the board's own
   record reaches. The page never loads a page by itself, so a reading citing an entry it does not hold has
   to say so, and say where the reader's own request resolves it. */

const path = '/api/session-record';
const ASSESSMENT = {
  revision_read: 1,
  revision_read_at: 90,
  window_start: 100,
  read_at: 1000,
  evidence_through: 1000,
  goal_source: 'typed',
  scope: 'last-turn',
  scope_text: 'Read up to its last turn.',
  stamp: 'model · m',
  cutoff: 'Evidence read to its end.',
  coverage: {
    tail_truncated: false,
    tail_start: null,
    unlisted: 0,
    unread_checks: 0,
    goal_source: 'typed',
  },
  criteria: {
    goal: {
      result: 'consistent with the evidence read',
      cites: ['early'],
      detail: '',
      clause: 'Keep the connection working',
    },
  },
};
const session = {
  annotation_assessment: ASSESSMENT,
  annotation_window_start: 100,
  annotation_reading_count: 1,
};
const FACTS = [check('c2', 600, 'passed')];
const recordBody = (extra: Record<string, unknown> = {}) => ({
  session: { harness: 'claude', sid: 's1' },
  entries: [fact('late', 900)],
  next: 'older',
  reached_start: false,
  bound: null,
  scanned_bytes: 1024,
  kinds: ['user_message', 'agent_message'],
  state: 'ok',
  ...extra,
});
const unloaded = () => document.querySelector('[data-next-unloaded]');

describe('a reading that cites an entry the page does not list', () => {
  it('says so, points at Show more, and stops saying it once the reader loads the entry', async () => {
    const page = mountDrift({
      session,
      facts: FACTS,
      routes: {
        [path]: (request) =>
          json(
            request.url.includes('before=')
              ? recordBody({
                  entries: [fact('early', 150, { type: 'agent_message', by: 'agent' })],
                  next: null,
                  reached_start: true,
                })
              : recordBody(),
          ),
      },
    });
    await page.settle();
    await page.settle();
    expect(unloaded()?.textContent).toBe(
      'This reading cites an entry that is not listed. Show more, under the list, may load it.',
    );
    // Nothing is loaded for the reader: the sentence leaves only once they ask.
    expect(page.gets(path)).toBe(1);
    await press(screen.getByRole('button', { name: 'Show 50 older entries' }));
    expect(page.gets(path)).toBe(2);
    expect(unloaded()).toBeNull();
    expect(textOf('[data-next-result-goal]')).not.toContain('Nothing resolvable was cited');
  });

  it('says nothing about loading when the record is already at its start', async () => {
    const page = mountDrift({
      session,
      facts: FACTS,
      routes: {
        [path]: () => json(recordBody({ entries: [], next: null, reached_start: true })),
      },
    });
    await page.settle();
    await page.settle();
    expect(unloaded()).toBeNull();
    expect(textOf('[data-next-result-goal]')).toContain('Nothing resolvable was cited');
  });

  it('counts several unloaded citations in one sentence', async () => {
    const many = {
      ...ASSESSMENT,
      criteria: { goal: { ...ASSESSMENT.criteria.goal, cites: ['early', 'earlier'] } },
    };
    const page = mountDrift({
      session: { ...session, annotation_assessment: many },
      facts: FACTS,
      routes: { [path]: () => json(recordBody()) },
    });
    await page.settle();
    await page.settle();
    expect(unloaded()?.textContent).toBe(
      'This reading cites 2 entries that are not listed. Show more, under the list, may load them.',
    );
  });
});

describe('the adopted-source note', () => {
  it('states the rule and does not claim this prompt reached it', async () => {
    const whole = {
      ...ASSESSMENT,
      goal_source: 'first-prompt',
      goal_source_at: 100,
      coverage: { ...ASSESSMENT.coverage, goal_source: 'whole' },
      criteria: { goal: { ...ASSESSMENT.criteria.goal, cites: ['c2'] } },
    };
    const page = mountDrift({
      session: { ...session, annotation_assessment: whole },
      facts: FACTS,
    });
    await page.settle();
    await page.settle();
    const text = document.body.textContent ?? '';
    expect(text).toContain(
      'The adopted source was found. Analyze reads at most the first 1,000 characters of any prompt.',
    );
    expect(text).not.toContain('Analyze read up to');
  });
});
