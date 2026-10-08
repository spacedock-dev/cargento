import { act, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  ROUTE,
  byAction,
  driftBoard,
  json,
  mountDrift,
  press,
  readingPosts,
  textOf,
} from './testing';

/* Nothing in the Drift section sends a request from a mount, a second mount under StrictMode, a poll, a
   reconnect, a route change, a hover, a focus or a keypress. The counts are requests the backend saw, by
   method and path, so a request the page forgot to mention is still counted. */
describe('Analyze starts only on a press', () => {
  it('sends no reading, cancel or correction POST from anything but a press', async () => {
    const page = mountDrift({ strict: true });
    await page.settle();
    await page.settle();
    expect(byAction('reading-ask')).not.toBeNull();
    for (const generated of [1100, 1200, 1300]) {
      await page.poll({ ...(page.state.data as object), generated });
    }
    const ask = byAction('reading-ask') as HTMLElement;
    await act(async () => {
      fireEvent.mouseOver(ask);
      fireEvent.mouseEnter(ask);
      fireEvent.focus(ask);
      fireEvent.keyDown(ask, { key: 'a' });
      fireEvent.keyDown(ask, { key: 'Enter' });
      fireEvent.keyUp(ask, { key: 'Enter' });
      fireEvent.pointerDown(ask);
    });
    await page.go('#n=intent');
    await page.go('#n=sessions');
    await page.go('#n=session:alpha%2Fapp:claude:s1');
    await page.back();
    await page.settle();
    expect(page.state.requests.filter((request) => request.method !== 'GET')).toEqual([]);
  });

  it('asks nothing of the model on a press that is refused, and says why where the press was', async () => {
    const page = mountDrift({ payload: { reading_check: 'failed' } });
    await page.settle();
    await page.settle();
    const ask = byAction('reading-ask') as HTMLElement;
    expect(ask.getAttribute('aria-disabled')).toBe('true');
    await press(ask);
    expect(readingPosts(page)).toEqual([]);
    expect(textOf('#next-cockpit-reading-refused')).toContain('not enabled in this build');
  });

  it('sends one request for one press and draws the job from the reply, however it is pressed', async () => {
    const page = mountDrift({
      routes: {
        '/api/reading': () => 'hold',
      },
    });
    await page.settle();
    await page.settle();
    const ask = byAction('reading-ask') as HTMLElement;
    await act(async () => {
      fireEvent.click(ask);
      fireEvent.click(ask);
      fireEvent.keyDown(ask, { key: 'Enter' });
      fireEvent.click(ask);
    });
    expect(readingPosts(page)).toHaveLength(1);
    const body = readingPosts(page)[0]?.body;
    expect(body).toMatchObject({
      harness: 'claude',
      sid: 's1',
      provider: 'claude',
      press: true,
      observer_model: 1,
      expected_revision: 3,
      model: 'm',
    });
    // A poll, a refresh and a route change while it is open send nothing more and retry nothing.
    await page.poll({ ...(page.state.data as object), generated: 1100 });
    await page.go('#n=sessions');
    await page.go('#n=session:alpha%2Fapp:claude:s1');
    expect(readingPosts(page)).toHaveLength(1);
    const job = { id: 'j1', phase: 'read', steps: [{ phase: 'read', text: 'Reading' }] };
    // The server publishes the job it started, so the board the refresh brings carries it.
    page.state.data = { ...(page.state.data as object), reading_jobs: { 'claude:s1': job } };
    await page.release('/api/reading', json({ ok: true, job }));
    await page.settle();
    expect(document.querySelector('[data-next-analyzing="j1"]')).not.toBeNull();
    expect(readingPosts(page)).toHaveLength(1);
  });

  it('draws the job from the reply until a board has drawn, then takes the board at its word', async () => {
    const job = { id: 'j7', phase: 'read', steps: [{ phase: 'read', text: 'Reading' }] };
    const page = mountDrift({ routes: { '/api/reading': () => json({ ok: true, job }) } });
    await page.settle();
    await page.settle();
    // The refresh the press follows with brings a board that does not hold the job, as a job that has
    // already ended would not: nothing stands over it.
    await press(byAction('reading-ask'));
    await page.settle();
    expect(document.querySelector('[data-next-analyzing]')).toBeNull();
    expect(byAction('reading-ask')).not.toBeNull();
    expect(readingPosts(page)).toHaveLength(1);
  });

  it('never retries a lost answer, and says it cannot confirm', async () => {
    const page = mountDrift({
      routes: { '/api/reading': () => new Response('not json', { status: 200 }) },
    });
    await page.settle();
    await page.settle();
    await press(byAction('reading-ask'));
    await page.settle();
    await page.advance(60_000);
    expect(readingPosts(page)).toHaveLength(1);
    expect(textOf('.next-session-drift-check')).toContain('Could not confirm the reading');
  });
});

describe('a refusal is a state', () => {
  it('stops being said the moment the reader does what it asks', async () => {
    const page = mountDrift({ payload: { reading_check: 'failed' } });
    await page.settle();
    await page.settle();
    await press(byAction('reading-ask'));
    expect(textOf('#next-cockpit-reading-refused')).toContain('not enabled in this build');
    await page.poll({ ...(page.state.data as object), generated: 1100, reading_check: 'passed' });
    expect(document.querySelector('#next-cockpit-reading-refused')).toBeNull();
    expect(textOf('.next-session-drift-check')).not.toContain('not enabled in this build');
    expect(byAction('reading-ask')?.getAttribute('aria-disabled')).toBeNull();
  });
});

describe('consent and destination', () => {
  const unconsented = {
    reading: { providers: { claude: false }, words: {}, tool_output: {}, used: 0, limit: 10 },
  };

  it('asks before sending, names the receiver, and sends only on Allow', async () => {
    const page = mountDrift({
      payload: unconsented,
      routes: { '/api/reading': () => json({ ok: true, produced: false }) },
    });
    await page.settle();
    await page.settle();
    expect(textOf('.next-cockpit-reading-ask')).toContain('Analyze drift');
    await press(byAction('reading-ask'));
    expect(readingPosts(page)).toEqual([]);
    expect(textOf('.next-cockpit-reading-consent')).toContain(
      'Send this session to Claude Code for analysis?',
    );
    expect(textOf('.next-cockpit-reading-consent')).toContain('Your saved words.');
    // Not now: nothing was sent, allowed or recorded.
    await press(byAction('reading-not-now'));
    expect(readingPosts(page)).toEqual([]);
    expect(byAction('reading-ask')).not.toBeNull();
    await press(byAction('reading-ask'));
    await press(byAction('reading-allow'));
    await page.settle();
    expect(readingPosts(page)).toHaveLength(1);
    expect(readingPosts(page)[0]?.body).toMatchObject({
      allow: true,
      words_destination: 'api',
      tool_output: 'api',
    });
  });

  it('refuses with the stated reason, sending nothing more, when the destination moved since the draw', async () => {
    const page = mountDrift({
      payload: unconsented,
      routes: {
        '/api/reading': () => json({ ok: false, reason: 'destination-changed' }, 409),
      },
    });
    await page.settle();
    await page.settle();
    await press(byAction('reading-ask'));
    await press(byAction('reading-allow'));
    await page.settle();
    expect(readingPosts(page)).toHaveLength(1);
    expect(textOf('.next-session-drift-check')).toContain(
      'Where this session would be sent changed',
    );
    await page.advance(5_000);
    expect(readingPosts(page)).toHaveLength(1);
  });
});

describe('a press names the session by its exact harness and sid', () => {
  it('sends the codex pair for a codex session that shares its sid with a claude one', async () => {
    const codexRoute = { ...ROUTE, provider: 'codex', harness: 'codex', model: '' };
    const payload = driftBoard();
    const claudeRow = (payload.sessions as Record<string, unknown>[])[0] as Record<string, unknown>;
    const page = mountDrift({
      hash: '#n=session:alpha%2Fapp:codex:x%3Ay',
      payload: {
        sessions: [claudeRow, { ...claudeRow, harness: 'codex', sid: 'x:y', state: 'working' }],
        reading_routes: { claude: ROUTE, codex: codexRoute },
        reading: {
          providers: { claude: true, codex: true },
          words: { claude: true, codex: true },
          tool_output: { claude: ['api'], codex: ['api'] },
          used: 0,
          limit: 10,
        },
      },
      routes: { '/api/reading': () => json({ ok: true, produced: false }) },
    });
    await page.settle();
    await page.settle();
    await press(byAction('reading-ask'));
    await page.settle();
    expect(readingPosts(page)).toHaveLength(1);
    expect(readingPosts(page)[0]?.body).toMatchObject({
      harness: 'codex',
      sid: 'x:y',
      provider: 'codex',
    });
  });
});
