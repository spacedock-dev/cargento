import { describe, expect, it } from 'vitest';
import { json, mountDrift, byAction, press, readingPosts, textOf } from './testing';

/* What the Analyze and Keep card says about a press that did not start work, from the reading-feedback lane the
   Intent step writes: a refusal on an adopted prompt, the one place the reader learns the prompt moved. */
describe('the reading-feedback lane', () => {
  it('draws the sentence a stale adoption left, beside the control that was pressed', async () => {
    const page = mountDrift({
      store: { goal: '', lines: [], revision: 0 },
      session: { annotation_goal: '', annotation_revision: 0 },
      routes: {
        '/api/annotate': () => json({ ok: true, outcome: 'refused', persisted: false }),
      },
    });
    await page.settle();
    await page.settle();
    // The reader saves the drafted prompt from a page another tab has already moved on from.
    const save = byAction('held-save');
    expect(save).not.toBeNull();
    await press(save);
    await page.settle();
    expect(textOf('.next-session-drift-check')).toContain('The prompt or saved goal changed');
    expect(readingPosts(page)).toEqual([]);
  });
});
