import { act, fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CUE_TTL_MS } from '../controls';
import { mountSessions, type AnswerScript } from './testing';

const NOW = 5000;
const ASK = { id: 'ask-1', harness: 'claude', session_id: 'one', project: 'p', question: 'Approve the plan?', options: ['Yes', 'No', 'Later'], age_sec: 90 };
const board = (sessions: unknown[], extra: Record<string, unknown> = {}) => ({ generated: NOW, sessions, ...extra });
const ONE = { harness: 'claude', sid: 'one', project: 'p', title: 'Retry queue', state: 'needs_input', blocked_since: NOW - 120 };
const ROUTE = '#n=session:p:claude:one';

async function open(data: unknown, options: { answer?: AnswerScript; hash?: string; strict?: boolean; focusCapability?: string } = {}) {
  const page = mountSessions({ hash: options.hash ?? ROUTE, data, ...options });
  await page.settle();
  return page;
}

const failure = () => document.querySelector('.next-session-answer-failure');

describe('answering a held request', () => {
  const asked = () => board([ONE], { ask: true, asks: [ASK] });

  it('shows every exact request in payload order, each with its options in order', async () => {
    await open(board([ONE], { ask: true, asks: [ASK, { ...ASK, id: 'ask-2', question: 'Second?', options: ['A', 'B'] }] }));
    const cards = [...document.querySelectorAll('[data-next-session-ask]')];
    expect(cards.map((card) => card.getAttribute('data-next-session-ask'))).toEqual(['ask-1', 'ask-2']);
    expect(cards.map((card) => within(card as HTMLElement).getAllByRole('button').map((button) => button.textContent))).toEqual([['Yes', 'No', 'Later'], ['A', 'B']]);
    expect(cards.map((card) => card.querySelector('.next-session-ask-question')?.textContent)).toEqual(['Approve the plan?', 'Second?']);
  });

  it('posts one numeric option index, never the option, and exactly once per press', async () => {
    const page = await open(asked());
    fireEvent.click(screen.getByRole('button', { name: 'No' }));
    await page.settle();
    const posts = page.posts();
    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatchObject({ method: 'POST', url: '/api/answer', body: { id: 'ask-1', index: 1 } });
    expect(Object.keys(posts[0]?.body as object).sort()).toEqual(['id', 'index']);
    expect(typeof (posts[0]?.body as { index: unknown }).index).toBe('number');
  });

  it('sends nothing on mount, under StrictMode, on a poll, or on a reconnect', async () => {
    const page = await open(asked());
    await page.poll(asked());
    await page.poll(asked());
    page.clock.advance(60_000);
    await page.settle();
    expect(page.posts()).toEqual([]);
  });

  it('answers a second press, while the first is in flight, with nothing, and shows the busy control', async () => {
    const page = await open(asked(), { answer: { kind: 'hold' } });
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
    await page.settle();
    const busy = document.querySelector('[data-next-answer-index="0"]');
    expect(busy?.getAttribute('aria-disabled')).toBe('true');
    expect(busy?.getAttribute('aria-busy')).toBe('true');
    expect(busy?.hasAttribute('data-next-pending')).toBe(true);
    expect(busy?.textContent).toContain('Sending…');
    fireEvent.click(document.querySelector('[data-next-answer-index="1"]') as Element);
    fireEvent.click(busy as Element);
    await page.settle();
    expect(page.posts()).toHaveLength(1);
    await page.release(new Response(JSON.stringify({ ok: true, answered: true }), { status: 200 }));
    expect(document.querySelector('[data-next-pending]')).toBeNull();
  });

  it('keeps the question when the server did not confirm, and says so', async () => {
    for (const answer of [{ kind: 'refuse' }, { kind: 'status', status: 500 }, { kind: 'not-json' }, { kind: 'offline' }] as const) {
      const page = await open(asked(), { answer });
      fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
      await page.settle();
      expect(failure()?.textContent).toBe('no confirmation came back — it may already have been answered');
      expect(document.querySelector('[data-next-session-ask="ask-1"]')).not.toBeNull();
      page.unmount();
    }
  });

  it('clears the failure sentence when a later press is confirmed, and retires the question only when the board stops carrying it', async () => {
    const page = await open(asked(), { answer: { kind: 'refuse' } });
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
    await page.settle();
    expect(failure()).not.toBeNull();
    page.state.answer = { kind: 'confirm' };
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
    await page.settle();
    expect(failure()).toBeNull();
    // The server confirmed, but the board still carries the request: the page does not guess it away.
    expect(document.querySelector('[data-next-session-ask="ask-1"]')).not.toBeNull();
    await page.poll(board([{ ...ONE, state: 'idle' }], { ask: true, asks: [] }));
    expect(document.querySelector('[data-next-session-ask]')).toBeNull();
    expect(document.querySelector('[data-next-session-section="ask"]')).toBeNull();
  });

  it('forgets a failure note once its request has left the board', async () => {
    const page = await open(asked(), { answer: { kind: 'refuse' } });
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
    await page.settle();
    await page.poll(board([ONE], { ask: true, asks: [] }));
    await page.poll(asked());
    expect(failure()).toBeNull();
  });

  it('sends nothing for a request with no id, and draws a request with no options as that', async () => {
    const page = await open(board([ONE], { ask: true, asks: [{ ...ASK, id: '' }] }));
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
    await page.settle();
    expect(page.posts()).toEqual([]);
    page.unmount();
    await open(board([ONE], { ask: true, asks: [{ ...ASK, options: [] }] }));
    expect(screen.getByText('No answer options were supplied.')).toBeInTheDocument();
  });

  it('attributes a request to the exact harness and sid, so the same sid elsewhere is not asked', async () => {
    const data = board(
      [
        { harness: 'claude', sid: 'one', project: 'p', title: 'Claude one', state: 'idle' },
        { harness: 'codex', sid: 'one', project: 'p', title: 'Codex one', state: 'idle' },
      ],
      { ask: true, asks: [{ ...ASK, harness: 'codex' }] },
    );
    await open(data, { hash: '#n=session:p:claude:one' });
    expect(document.querySelector('[data-next-session-section="ask"]')).toBeNull();
    expect(document.querySelector('.next-session-state')?.textContent).toBe('State: idle');
  });

  it('says a session holding a request needs input, and one that ended without a request is ended', async () => {
    await open(board([{ ...ONE, state: 'idle', ended_at: NOW - 30 }], { ask: true, asks: [ASK] }));
    expect(document.querySelector('.next-session-state')?.textContent).toBe('State: needs input');
    document.body.innerHTML = '';
    await open(board([{ ...ONE, state: 'working', ended_at: NOW - 30 }]));
    expect(document.querySelector('.next-session-state')?.textContent).toBe('State: ended');
    expect(document.querySelector('.next-session-detail-meta')?.textContent).toContain('ended 30s ago');
  });
});

describe('a session that is not in the payload', () => {
  it('says the board has not arrived before the first payload, and never "not in the payload"', async () => {
    const page = mountSessions({ hash: ROUTE, data: board([ONE]), strict: false });
    expect(screen.getByText('The first payload has not arrived yet.')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('not in the current payload');
    await page.settle();
  });

  it('names an expired identity by its harness and sid, and offers the way back', async () => {
    await open(board([ONE], { window_hours: 24 }), { hash: '#n=session:p:claude:gone' });
    expect(screen.getByText('This session is not in the current payload.')).toBeInTheDocument();
    expect(screen.getByText('claude · gone')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View all sessions' })).toBeInTheDocument();
  });
});

describe('what the page says about what it could not see', () => {
  it('says why a fact is unmeasured instead of leaving a blank', async () => {
    await open(board([{ harness: 'cursor', sid: 'x', project: 'p', state: 'working' }]), { hash: '#n=session:p:cursor:x' });
    const text = document.body.textContent ?? '';
    expect(text).toContain('Title not published');
    expect(text).toContain('Harness does not report blocks');
    expect(text).toContain('Session facts: No stop or end observed · Git state was not measured');
  });

  it('draws the command-shape reports as off, with the sentence and the caveats behind one summary', async () => {
    await open(board([ONE]));
    const section = document.querySelector('[data-next-command-reports]');
    expect(section?.textContent).toContain('Command-shape reports: off');
    expect(section?.textContent).toContain('Command-shape reports are disabled for this run.');
    expect(section?.textContent).toContain('A shape match does not prove the action succeeded.');
  });

  it('lists a command report whose time is not a date without its time, where the page it ports would fail to draw at all', async () => {
    await open(board([{ ...ONE, command_reports: [{ label: 'rm -rf build', tool_name: 'Bash', timestamp: 'later' }, { label: 'ls', tool_name: 'Bash', timestamp: 1700000000 }] }], { irreversible_enabled: true }));
    const items = [...document.querySelectorAll('[data-next-command-reports] li')].map((item) => item.textContent);
    expect(items).toEqual(['Command shape reported: rm -rf buildBash', 'Command shape reported: lsBash · 2023-11-14T22:13:20.000Z']);
  });

  it('lists workers with their own state, counts only direct children in the heading, and says how many older ones were left out', async () => {
    await open(
      board([{ ...ONE, state: 'working', subagents: [{ name: 'lead' }, { name: 'idle one', active: false }, { name: 'child', parent: 'lead' }], subagents_omitted: 2 }]),
    );
    const block = document.querySelector('[data-next-session-subagents]');
    expect(block?.querySelector('span')?.textContent).toBe('1 RUNNING SUBAGENT · 1 WORKER RUNNING BENEATH');
    expect(block?.querySelectorAll('.next-session-subagent')).toHaveLength(3);
    expect(block?.querySelector('.next-session-subagents-omitted')?.textContent).toBe('+2 older finished workers omitted');
  });
});

describe('a row control’s confirmation belongs to the exact session and lasts thirty seconds', () => {
  const rows = () =>
    board([
      { harness: 'claude', sid: 'one', project: 'p', title: 'First', state: 'idle' },
      { harness: 'codex', sid: 'one', project: 'p', title: 'Second', state: 'idle' },
    ]);

  it('marks the pressed session’s copy control, keeps the cue across a poll, and clears it at thirty seconds', async () => {
    const page = await open(rows(), { hash: '#n=sessions' });
    const copy = (harness: string) => document.querySelector<HTMLButtonElement>(`article[data-next-harness="${harness}"] button[data-copy-kind="id"]`);
    await act(async () => {
      fireEvent.click(copy('claude') as Element);
    });
    await page.settle();
    expect(page.written).toEqual(['one']);
    expect(copy('claude')?.getAttribute('data-copy-state')).toBe('copied');
    expect(copy('codex')?.hasAttribute('data-copy-state')).toBe(false);
    const node = copy('claude');
    await page.poll(rows());
    expect(copy('claude')).toBe(node);
    expect(copy('claude')?.getAttribute('data-copy-state')).toBe('copied');
    await act(async () => {
      page.clock.advance(CUE_TTL_MS + 1);
    });
    expect(copy('claude')?.hasAttribute('data-copy-state')).toBe(false);
  });
});

describe('the raise control', () => {
  const data = board([{ ...ONE, focusable: true }]);

  it('draws only with a minted capability and a terminal the session reported, and as the primary control while a request waits', async () => {
    await open(data);
    expect(document.querySelector('.ctl-raise')).toBeNull();
    expect(document.querySelector('.next-session-reentry-clause')?.textContent).toContain('Terminal raise off');
    document.body.innerHTML = '';
    await open(data, { focusCapability: 'minted' });
    const raise = document.querySelector('.ctl-raise');
    expect(raise).not.toBeNull();
    expect(raise?.classList.contains('ctl-action--primary')).toBe(true);
    document.body.innerHTML = '';
    await open(board([{ ...ONE, focusable: false }]), { focusCapability: 'minted' });
    expect(document.querySelector('.ctl-raise')).toBeNull();
    expect(document.querySelector('.next-session-reentry-clause')?.textContent).toContain('No terminal to raise');
  });

  it('is not drawn for a session that is not waiting, where the header offers copy controls alone', async () => {
    await open(board([{ ...ONE, state: 'idle', focusable: true }]), { focusCapability: 'minted' });
    expect(document.querySelector('.ctl-raise')).toBeNull();
  });
});
