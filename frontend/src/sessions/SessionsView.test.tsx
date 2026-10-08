import { act, fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mountSessions } from './testing';

const NOW = 5000;
const board = (sessions: unknown[], extra: Record<string, unknown> = {}) => ({ generated: NOW, sessions, ...extra });

async function open(data: unknown, options: { strict?: boolean; hash?: string } = {}) {
  const page = mountSessions({ hash: options.hash ?? '#n=sessions', data, ...(options.strict === undefined ? {} : { strict: options.strict }) });
  await page.settle();
  return page;
}

const rows = (group: string) => [...document.querySelectorAll(`[data-next-operation-group="${group}"] article.next-operation-row`)].map((row) => `${row.getAttribute('data-next-harness')}/${row.getAttribute('data-next-session')}`);

describe('what the screen says when it has nothing to draw', () => {
  it('says the first payload has not arrived rather than drawing an empty board', async () => {
    mountSessions({ data: board([]), strict: false });
    expect(screen.getByText('The first payload has not arrived yet.')).toBeInTheDocument();
    expect(document.querySelector('[data-next-operation-group]')).toBeNull();
  });

  it('says the board published no session collection, which is not the same as no sessions', async () => {
    await open({ generated: NOW });
    expect(screen.getByText('The board published no session collection.')).toBeInTheDocument();
    expect(document.querySelector('[data-next-operation-group]')).toBeNull();
  });

  it('draws an empty collection as measured zeros with both groups saying they are empty', async () => {
    await open(board([]));
    expect(screen.getByText('No exact session has active evidence right now.')).toBeInTheDocument();
    expect(screen.getByText('No recent-history rows in this payload.')).toBeInTheDocument();
    expect([...document.querySelectorAll('[data-next-fleet-fact] strong')].map((node) => node.textContent)).toEqual(['0', '0', '0', '0']);
  });

  it('names a harness whose store could not be read, so its absence is not read as no sessions', async () => {
    await open(board([], { harnesses: [{ key: 'codex', label: 'Codex', error: 'denied' }, { key: 'claude', label: 'Claude Code' }] }));
    const note = document.querySelector('[data-next-source-gaps]');
    expect(note?.textContent).toContain('Codex: Harness source could not be read');
    expect(note?.textContent).not.toContain('Claude Code');
  });
});

describe('the groups', () => {
  const data = board(
    [
      { harness: 'claude', sid: 'idle-new', project: 'p', state: 'idle', last_activity: NOW - 5 },
      { harness: 'claude', sid: 'work', project: 'p', state: 'working', active: true },
      { harness: 'codex', sid: 'gate', project: 'q', state: 'needs_input' },
      { harness: 'claude', sid: 'idle-old', project: 'p', state: 'idle', last_activity: NOW - 500 },
      { harness: 'claude', sid: 'done', project: 'p', state: 'working', active: true, ended_at: NOW - 20 },
    ],
    { annotate: true },
  );

  it('puts a blocked session first, then the working one, and sends an ended session to history even though its state still says working', async () => {
    await open(data);
    expect(rows('active')).toEqual(['codex/gate', 'claude/work']);
    // The lanes keep the working lane ahead of the idle one, and an ended row is no longer active, so it leads history.
    expect(rows('history')).toEqual(['claude/done', 'claude/idle-new', 'claude/idle-old']);
  });

  it('keeps one sid under two harnesses as two rows, each opening its own exact route', async () => {
    await open(
      board([
        { harness: 'claude', sid: 'shared', project: 'p', title: 'Claude one', state: 'idle' },
        { harness: 'codex', sid: 'shared', project: 'p', title: 'Codex one', state: 'idle' },
      ]),
    );
    const links = [...document.querySelectorAll('a.next-operation-route')].map((link) => link.getAttribute('href'));
    expect(links).toEqual(['#n=session:p:claude:shared', '#n=session:p:codex:shared']);
    expect(document.querySelectorAll('.next-operation-collision')).toHaveLength(2);
  });

  it('promotes a session holding a recorded departure over one that is only quiet, and does not call it running', async () => {
    const withDeparture = { harness: 'claude', sid: 'raised', project: 'p', state: 'idle', departures: [{ at: NOW - 60, revision: 1 }], annotation_revision: 1 };
    await open(board([{ harness: 'claude', sid: 'plain', project: 'p', state: 'idle' }, withDeparture], { annotate: true }));
    expect(rows('active')).toEqual(['claude/raised']);
    expect(document.querySelector('[data-next-session-drift-mark]')?.textContent).toBe('Drift · 1m ago');
    expect(document.querySelector('[data-next-fleet-fact="active"] strong')?.textContent).toBe('0');
  });

  it('says annotations are off, and the goal cell says so too, when the payload does not publish them', async () => {
    await open(board([{ harness: 'claude', sid: 'a', project: 'p', state: 'idle' }]));
    expect(document.querySelector('[data-next-operation-fact="goal"]')?.textContent).toBe('GOALAnnotations off');
  });

  it('names where the goal words came from, and links an empty goal to its session', async () => {
    const claude = { harness: 'claude', sid: 'typed', project: 'p', state: 'idle', annotation_goal: 'Ship the queue' };
    const drafted = { harness: 'claude', sid: 'drafted', project: 'p', state: 'idle', first_prompt: 'Do the thing', first_prompt_at: NOW - 100 };
    const empty = { harness: 'cursor', sid: 'empty', project: 'p', state: 'idle' };
    await open(board([claude, drafted, empty], { annotate: true }));
    const goal = (sid: string) => document.querySelector(`article[data-next-session="${sid}"] [data-next-operation-fact="goal"]`);
    expect(goal('typed')?.textContent).toBe('GOAL · YOUR WORDSShip the queue');
    expect(goal('drafted')?.textContent).toBe('GOAL · YOUR FIRST PROMPTDo the thing');
    expect(goal('empty')?.textContent).toBe('GOALAdd a goal');
    expect(goal('empty')?.querySelector('a')?.classList.contains('next-absence')).toBe(true);
  });

  it('says no session has been checked while checks are visible and none exists', async () => {
    await open(board([{ harness: 'claude', sid: 'a', project: 'p', state: 'idle' }], { annotate: true }));
    expect(screen.getByText('No session has been checked for drift yet; open one to check it.')).toBeInTheDocument();
    document.body.innerHTML = '';
    await open(board([{ harness: 'claude', sid: 'a', project: 'p', state: 'idle', departure_checked: true }], { annotate: true }));
    expect(screen.queryByText('No session has been checked for drift yet; open one to check it.')).toBeNull();
  });

  it('says who a held request is addressed to', async () => {
    await open(
      board(
        [
          { harness: 'claude', sid: 'a', project: 'p', state: 'idle' },
          { harness: 'claude', sid: 'b', project: 'p', state: 'idle', spacedock: { workflows: [] } },
        ],
        {
          ask: true,
          asks: [
            { id: '1', harness: 'claude', session_id: 'a', question: 'One?', options: ['y'] },
            { id: '2', harness: 'claude', session_id: 'b', question: 'Two?', options: ['y'] },
          ],
        },
      ),
    );
    const blocked = (sid: string) => document.querySelector(`article[data-next-session="${sid}"] [data-next-operation-fact="blocked"] small`)?.textContent;
    expect(blocked('a')).toBe('BLOCKED · NEEDS YOU');
    expect(blocked('b')).toBe('BLOCKED · CAPTAIN');
  });
});

describe('a redraw leaves the reader’s place alone', () => {
  const data = board([
    { harness: 'claude', sid: 'a', project: 'p', title: 'Alpha', state: 'working', active: true },
    { harness: 'claude', sid: 'b', project: 'p', title: 'Beta', state: 'idle' },
  ]);

  it('keeps the row nodes, an open caveat and a focused link across a poll that changes the rows', async () => {
    const page = await open(data);
    const alpha = document.querySelector('article[data-next-session="a"]');
    const summary = screen.getByText('How rows are split');
    fireEvent.click(summary);
    const details = summary.closest('details') as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event('toggle'));
    (alpha?.querySelector('a.next-operation-route') as HTMLElement).focus();
    await page.poll(board([{ ...(data.sessions[0] as object), state_detail: 'now different' }, data.sessions[1]]));
    expect(document.querySelector('article[data-next-session="a"]')).toBe(alpha);
    expect((screen.getByText('How rows are split').closest('details') as HTMLDetailsElement).open).toBe(true);
    expect(document.activeElement).toBe(alpha?.querySelector('a.next-operation-route'));
  });

  it('opens a session by its exact route on a plain click, and leaves a modified click to the browser', async () => {
    const page = await open(data);
    const link = document.querySelector('article[data-next-session="b"] a.next-operation-route') as HTMLAnchorElement;
    fireEvent.click(link, { ctrlKey: true });
    expect(page.router.getRoute().view).toBe('sessions');
    fireEvent.click(link);
    await page.settle();
    expect(page.router.getRoute()).toMatchObject({ view: 'session', project: 'p', harness: 'claude', session: 'b', from: 'sessions' });
  });
});

describe('row control cues keep the newest thirty-two', () => {
  it('forgets the oldest cue once a thirty-third control has been pressed', async () => {
    const many = board(Array.from({ length: 34 }, (_, index) => ({ harness: 'claude', sid: `s${String(index).padStart(2, '0')}`, project: 'p', title: `T${String(index)}`, state: 'idle', last_activity: NOW - index })));
    const page = await open(many);
    for (let index = 0; index < 34; index += 1) {
      await act(async () => {
        fireEvent.click(document.querySelector(`article[data-next-session="s${String(index).padStart(2, '0')}"] button[data-copy-kind="id"]`) as Element);
      });
    }
    await page.settle();
    const marked = [...document.querySelectorAll('button[data-copy-state]')].map((button) => button.closest('article')?.getAttribute('data-next-session'));
    expect(marked).toHaveLength(32);
    expect(marked).not.toContain('s00');
    expect(marked).not.toContain('s01');
    expect(marked).toContain('s33');
  });
});

describe('the goal link opens the session at its goal', () => {
  it('lands focus on the session page’s Intent heading, once, and not on a later visit', async () => {
    const data = board([{ harness: 'cursor', sid: 'x', project: 'p', state: 'idle' }], { annotate: true });
    const page = await open(data);
    fireEvent.click(document.querySelector('a[data-next-goal-focus]') as Element);
    await page.settle();
    expect(page.router.getRoute().view).toBe('session');
    expect(document.activeElement?.id).toBe('next-session-intent-heading');
    await act(async () => {
      page.router.navigate({ view: 'sessions', project: null, session: null });
    });
    await page.settle();
    await act(async () => {
      page.router.navigate({ view: 'session', project: 'p', harness: 'cursor', session: 'x' });
    });
    await page.settle();
    expect(document.activeElement?.id).not.toBe('next-session-intent-heading');
  });
});

describe('the header counts and the screen are one reading of one payload', () => {
  it('reports the same running and blocked sessions in the header as the rows show', async () => {
    await open(
      board([
        { harness: 'claude', sid: 'a', project: 'p', state: 'working', active: true, subagents: [{}, {}] },
        { harness: 'claude', sid: 'b', project: 'p', state: 'needs_input' },
        { harness: 'claude', sid: 'c', project: 'p', state: 'working', active: true, ended_at: 5 },
      ]),
    );
    expect(document.querySelector('.next-running')?.textContent).toContain('1 running · 2 subagents observed');
    expect(document.querySelector('.next-gate')?.textContent).toBe('1 reported block');
    expect(document.querySelector('[data-next-fleet-fact="reported-blocks"] strong')?.textContent).toBe('1');
  });
});
