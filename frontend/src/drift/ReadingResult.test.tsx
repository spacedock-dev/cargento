import { describe, expect, it } from 'vitest';
import { byAction, check, fact, json, mountDrift, press, textOf } from './testing';

const ASSESSMENT = {
  revision_read: 3,
  revision_read_at: 990,
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
      result: 'departure',
      cites: ['c1'],
      detail: 'It stopped running the tests.',
      clause: 'Ship the queue',
    },
    line_1: {
      result: 'consistent with the evidence read',
      cites: ['c2'],
      detail: '',
      clause: 'Tests pass',
    },
  },
};

const FACTS = [
  check('c1', 500, 'failed', { result_source: 'failed flag', summary: 'pytest -q' }),
  check('c2', 600, 'passed'),
];

const stored = (extra: Record<string, unknown> = {}) => ({
  annotation_assessment: ASSESSMENT,
  annotation_window_start: 100,
  annotation_reading_count: 1,
  ...extra,
});

describe('a stored reading', () => {
  it("says the answer, then each line by the list's own number, and never a check mark", async () => {
    const page = mountDrift({ session: stored(), facts: FACTS });
    await page.settle();
    await page.settle();
    const result = document.querySelector('[data-next-result]') as HTMLElement;
    expect(result).not.toBeNull();
    expect(textOf('.next-cockpit-result-headline')).toBe('Departs from your intent1 departure');
    const goal = document.querySelector('[data-next-result-goal]') as HTMLElement;
    expect(goal.getAttribute('data-next-result-state')).toBe('departs');
    expect(goal.textContent).toContain('Departs; evidence #1');
    const line = document.querySelector('.next-cockpit-result-lines li') as HTMLElement;
    expect(line.getAttribute('data-next-result-state')).toBe('consistent');
    expect(line.textContent).toContain('Consistent with #2');
    expect(result.textContent).not.toMatch(/[✓✔]/);
    // The numbers it names are rows on screen, and the one it cites is flagged.
    expect(document.querySelector('[data-next-entry="1"]')).not.toBeNull();
    expect(
      document.querySelector('[data-next-entry="1"] [data-next-entry-flag="cited"]'),
    ).not.toBeNull();
    expect(
      document.querySelector('[data-next-entry="2"] [data-next-entry-flag="cited"]'),
    ).toBeNull();
    // The press that stands in the button's place, inert or not, is Analyze again.
    expect(byAction('reading-ask')?.textContent).toBe('Analyze again');
  });

  it('withholds a verdict that cites nothing it can resolve, never softening it', async () => {
    const bad = {
      ...ASSESSMENT,
      criteria: {
        goal: { result: 'departure', cites: ['gone'], detail: 'x', clause: 'Ship the queue' },
      },
    };
    const page = mountDrift({
      session: stored({ annotation_assessment: bad }),
      facts: FACTS,
    });
    await page.settle();
    await page.settle();
    expect(textOf('.next-cockpit-result-line')).toBe("Can't tell");
    expect(document.querySelector('.next-cockpit-result-headline')).toBeNull();
    expect(document.querySelector('[data-next-result-goal]')?.textContent).toContain(
      'Nothing resolvable was cited',
    );
  });

  it('refuses a reading carrying a field this build does not know, and draws no verdict', async () => {
    const page = mountDrift({
      session: stored({ annotation_assessment: { ...ASSESSMENT, surprise: true } }),
      facts: FACTS,
    });
    await page.settle();
    await page.settle();
    expect(textOf('.next-cockpit-reading')).toContain('cannot read the reading it was given');
    expect(textOf('.next-cockpit-reading')).toContain('Unrecognised: surprise.');
    expect(document.querySelector('[data-next-result]')).toBeNull();
  });

  it('says a reading of earlier words is of earlier words, and offers Analyze again in the callout', async () => {
    const page = mountDrift({
      session: stored(),
      store: { revision: 4 },
      facts: FACTS,
    });
    await page.settle();
    await page.settle();
    const stale = document.querySelector('[data-next-result-stale]') as HTMLElement;
    expect(stale.getAttribute('data-next-result-stale')).toBe('intent');
    expect(stale.textContent).toContain('Your intent changed after this analysis.');
    expect(stale.textContent).toContain('This reading read revision 3. Revision 4 is current');
    expect(stale.querySelector('[data-next-cockpit-action="reading-ask"]')).not.toBeNull();
  });

  it('says new work arrived after the reading read, and what kind', async () => {
    const page = mountDrift({
      session: stored(),
      facts: [
        ...FACTS,
        check('c3', 1200, 'passed'),
        fact('m1', 1250, { type: 'agent_message', by: 'agent' }),
      ],
    });
    await page.settle();
    await page.settle();
    const stale = document.querySelector('[data-next-result-stale="work"]') as HTMLElement;
    expect(stale.textContent).toContain('New work since this analysis.');
    expect(textOf('.next-cockpit-result-stale + *, [data-next-result]')).toContain(
      '1 check, 1 message arrived since this analysis.',
    );
  });
});

describe('Not accurate', () => {
  it('derives its mark from the payload and never from the press', async () => {
    const page = mountDrift({
      session: stored(),
      facts: FACTS,
      routes: {
        '/api/annotate': () => json({ ok: true, outcome: 'untrusted', persisted: false }),
      },
    });
    await page.settle();
    await page.settle();
    const mark = byAction('not-accurate') as HTMLElement;
    expect(mark.getAttribute('aria-pressed')).toBe('false');
    await press(mark);
    await page.settle();
    const posts = page.state.requests.filter(
      (r) => r.method === 'POST' && r.path === '/api/annotate',
    );
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toMatchObject({
      harness: 'claude',
      sid: 's1',
      not_accurate: true,
      read_at: 1000,
    });
    // The store did not take it: still unmarked, and said so.
    expect(byAction('not-accurate')?.getAttribute('aria-pressed')).toBe('false');
    expect(textOf('.next-cockpit-result-foot')).toContain('Your mark was not saved.');
    // Marked on the board, it draws marked, and the sentence is the board's.
    await page.poll({
      ...(page.state.data as object),
      generated: 1100,
      sessions: [
        {
          ...(page.state.data as { sessions: object[] }).sessions[0],
          annotation_not_accurate: true,
        },
      ],
    });
    expect(byAction('not-accurate')?.getAttribute('aria-pressed')).toBe('true');
    expect(textOf('.next-cockpit-result-marked')).toBe('You marked this analysis not accurate.');
    // A level is not drawn from a reading marked not accurate.
    expect(document.querySelector('[data-next-drift-level]')).toBeNull();
  });
});
