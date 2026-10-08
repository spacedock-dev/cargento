import { describe, expect, it } from 'vitest';
import { byAction, fact, json, mountDrift, press, readingPosts, textOf } from './testing';

/* Keep my intent, where an analysis may start: one request to settle and read together, never carrying an
   Allow. Where an Allow is still owed it settles through `/api/annotate` and reads nothing. */
const LATER = fact('d1', 995, { summary: 'Do it the careful way' });
const routes = {
  '/api/direction': () => json({ ok: true, text: 'Do it the careful way', clipped: false }),
  '/api/annotate': () => json({ ok: true, outcome: 'stored', persisted: true, revision: 4 }),
  '/api/reading': () => json({ ok: true, settled: 'stored', job: { id: 'j9', steps: [] } }),
};
const session = { annotation_goal_saved_at: 500, annotation_at: 500 };

describe('Keep my intent and analyze', () => {
  it('settles and starts the analysis in one reading request, once', async () => {
    const page = mountDrift({
      facts: [LATER],
      session,
      routes: { ...routes, '/api/reading': () => 'hold' },
    });
    await page.settle();
    await page.settle();
    const keep = byAction('direction-keep') as HTMLElement;
    expect(keep.textContent).toBe('Keep my intent and analyze');
    expect(keep.classList.contains('next-action--primary')).toBe(true);
    await press(keep);
    await press(byAction('direction-keep'));
    await page.settle();
    expect(readingPosts(page)).toHaveLength(1);
    expect(readingPosts(page)[0]?.body).toMatchObject({
      provider: 'claude',
      press: true,
      observer_model: 1,
      settle_through: 995,
      expected_revision: 3,
    });
    expect(readingPosts(page)[0]?.body).not.toHaveProperty('allow');
    expect(
      page.state.requests.filter((r) => r.method === 'POST' && r.path === '/api/annotate'),
    ).toEqual([]);
  });

  it('only settles while an Allow is still owed, and leaves the Allow to the step that names the receiver', async () => {
    const page = mountDrift({
      facts: [LATER],
      session,
      routes,
      payload: {
        reading: { providers: { claude: false }, words: {}, tool_output: {}, used: 0, limit: 10 },
      },
    });
    await page.settle();
    await page.settle();
    expect(byAction('direction-keep')?.textContent).toBe('Keep my intent');
    await press(byAction('direction-keep'));
    await page.settle();
    expect(readingPosts(page)).toEqual([]);
    expect(
      page.state.requests.filter((r) => r.method === 'POST' && r.path === '/api/annotate'),
    ).toHaveLength(1);
    expect(textOf('.next-cockpit-direction-question')).toContain('Press Allow and analyze');
  });
});

describe('Keep during a held close', () => {
  it('settles and reads nothing where the board already says no reading can start, and learns that', async () => {
    const quiet = { ok: false, reason: 'idle-unknown', sentence: 'Not recorded.' };
    const page = mountDrift({ facts: [LATER], session, routes });
    await page.settle();
    await page.settle();
    expect(byAction('direction-keep')?.textContent).toBe('Keep my intent and analyze');
    await page.poll({
      ...(page.state.data as { sessions: object[] }),
      generated: 1100,
      sessions: [
        { ...(page.state.data as { sessions: object[] }).sessions[0], reading_eligibility: quiet },
      ],
    });
    // The close is held: the card still offers the analysis.
    expect(byAction('direction-keep')?.textContent).toBe('Keep my intent and analyze');
    await press(byAction('direction-keep'));
    await page.settle();
    expect(readingPosts(page)).toEqual([]);
    expect(
      page.state.requests.filter((r) => r.method === 'POST' && r.path === '/api/annotate'),
    ).toHaveLength(1);
    expect(byAction('direction-keep')?.textContent).toBe('Keep my intent');
  });
});
