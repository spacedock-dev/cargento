import { describe, expect, it } from 'vitest';
import { check, fact, mountDrift } from './testing';

/* The session's activity list reads newest first. The numbers are the oldest-first ones every "#<n>" and
   every citation names, so the column reads from the highest down to #1 and a reader opens on what just
   happened. Entries are numbered in time order whatever kind they are, so a check sits between the prompts
   either side of it rather than after all of them. */
const FACTS = [
  fact('p1', 900, { summary: 'First direction' }),
  check('c1', 910, 'passed'),
  fact('p2', 920, { summary: 'Second direction' }),
  fact('p3', 996, { summary: 'Newest direction' }),
];
const session = { annotation_goal_saved_at: 500, annotation_at: 500 };

describe('the session activity list', () => {
  it('reads newest first, each row keeping the number its time earned', async () => {
    const page = mountDrift({ facts: FACTS, session });
    await page.settle();
    await page.settle();
    const rows = [...document.querySelectorAll<HTMLElement>('[data-next-entry-id]')];
    expect(rows.map((row) => row.dataset['nextEntryId'])).toEqual(['p3', 'p2', 'c1', 'p1']);
    expect(rows.map((row) => row.dataset['nextEntry'])).toEqual(['4', '3', '2', '1']);
  });

  it('draws "Add to my intent" at rest, with nothing hiding it until the pointer arrives', async () => {
    const page = mountDrift({ facts: FACTS, session });
    await page.settle();
    await page.settle();
    const adds = [
      ...document.querySelectorAll<HTMLElement>('[data-next-cockpit-action="direction-add"]'),
    ];
    expect(adds.length).toBeGreaterThan(0);
    for (const add of adds) {
      expect(add.className).not.toMatch(/opacity-0|hover:opacity|group-hover/);
      expect(add.hidden).toBe(false);
    }
  });

  it('reads a check as one sentence and draws its notes at the right edge, as a flag is', async () => {
    const page = mountDrift({
      facts: [
        fact('p1', 900),
        check('c1', 910, '', { result_source: '', before_last_change: true }),
      ],
      session,
    });
    await page.settle();
    await page.settle();
    const row = document.querySelector<HTMLElement>('[data-next-entry-id="c1"]') as HTMLElement;
    const head = row.querySelector('.next-cockpit-work-head') as HTMLElement;
    expect(head.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      'Agent · check · ran, result not recorded · before the last change',
    );
    const notes = head.querySelector<HTMLElement>('[data-next-entry-notes]');
    expect(notes?.textContent).toBe('ran, result not recorded · before the last change');
    expect(notes?.className).toContain('ml-auto');
    expect(head.querySelector('.next-cockpit-work-actor')?.textContent).toBe('Agent');
    expect(head.querySelector('.next-cockpit-work-type')?.textContent).toBe('check');
  });
});
