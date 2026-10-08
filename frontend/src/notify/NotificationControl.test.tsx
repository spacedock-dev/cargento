import { act, fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { attentionBoard } from '../../test/attention_boards';
import { mountShell } from '../shell/testing';

/* The notification control and the owner behind it, in the real shell with a SCRIPTED Notification: a
   class that records what it was asked to raise and what permission it was asked for. Nothing here can
   create a native notification, and every "nothing happened" below is a count read off that script. */

afterEach(() => {
  vi.unstubAllGlobals();
});

function script(permission: string, answer: 'granted' | 'denied' = 'granted') {
  const made: { title: string; body: string; tag: string }[] = [];
  const asked = { count: 0 };
  class Scripted {
    static permission = permission;
    static requestPermission = (done?: () => void) => {
      asked.count += 1;
      Scripted.permission = answer;
      done?.();
      return Promise.resolve(answer);
    };
    constructor(title: string, options: { body: string; tag: string }) {
      made.push({ title, body: options.body, tag: options.tag });
    }
  }
  vi.stubGlobal('Notification', Scripted);
  return { made, asked, Scripted };
}

const lanePosts = (page: { backend: { requests: { method: string; url: string }[] } }) =>
  page.backend.requests.filter((request) => request.url === '/api/lane');

async function open(data: unknown, options: { strict?: boolean; hash?: string } = {}) {
  const page = mountShell({
    hash: options.hash ?? '#n=attention',
    data,
    strict: options.strict ?? true,
  });
  await page.settle();
  return page;
}

async function revise(page: Awaited<ReturnType<typeof open>>, data: unknown) {
  page.backend.data = data;
  await act(async () => {
    await page.shell.runtime.refresh();
  });
  await page.settle();
}

describe('the header control', () => {
  it('offers to enable while the reader can still be asked, and asks nothing by itself', async () => {
    const api = script('default');
    const page = await open(attentionBoard({ asking: [] }));
    expect(screen.getByRole('button', { name: 'Enable notifications' })).toBeInTheDocument();
    await revise(page, attentionBoard({ generated: 1_000_025, asking: [] }));
    await page.go('#n=sessions');
    await page.go('#n=attention');
    expect(api.asked.count).toBe(0);
    expect(api.made).toEqual([]);
    expect(lanePosts(page)).toEqual([]);
  });

  it('opens the browser prompt once, on the press, then reports the lane once and hands focus back to the page', async () => {
    const api = script('default');
    const page = await open(attentionBoard({ asking: [] }));
    const button = screen.getByRole('button', { name: 'Enable notifications' });
    button.focus();
    fireEvent.click(button);
    await page.settle();
    expect(api.asked.count).toBe(1);
    expect(screen.queryByRole('button', { name: 'Enable notifications' })).toBeNull();
    const posts = lanePosts(page);
    expect(posts).toHaveLength(1);
    // The lane report is two scalars about this tab and names no session.
    expect(document.activeElement).toBe(
      document.querySelector('nav[aria-label="Primary"] [aria-current="page"]'),
    );
    expect(api.made).toEqual([]);
  });

  it('says notifications are blocked once the reader has refused, and offers nothing to press', async () => {
    script('denied');
    await open(attentionBoard({ asking: [] }));
    expect(screen.getByText('notifications blocked')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Enable notifications' })).toBeNull();
  });

  it('draws nothing where the browser has no Notification API, and the page still works', async () => {
    const page = await open(attentionBoard());
    expect(screen.queryByRole('button', { name: 'Enable notifications' })).toBeNull();
    expect(screen.queryByText('notifications blocked')).toBeNull();
    expect(page.container.querySelector('[data-next-view-body="attention"]')).not.toBeNull();
    expect(lanePosts(page)).toEqual([]);
  });

  it('draws nothing where the server’s own lane raises the banners, and raises none itself', async () => {
    const api = script('granted');
    const page = await open(attentionBoard({ nativeNotify: 'osascript', asking: [] }));
    expect(screen.queryByRole('button', { name: 'Enable notifications' })).toBeNull();
    await revise(
      page,
      attentionBoard({
        generated: 1_000_025,
        nativeNotify: 'osascript',
        asking: [],
        unowned: false,
        blocked: ['gate-1'],
      }),
    );
    expect(api.made).toEqual([]);
  });
});

describe('what raises a banner', () => {
  it('raises one banner for a gate that arrives after the first board, once, under StrictMode', async () => {
    const api = script('granted');
    const page = await open(attentionBoard({ asking: [], unowned: false, browserLane: true }));
    expect(api.made).toEqual([]);
    const next = attentionBoard({
      generated: 1_000_025,
      asking: [],
      unowned: false,
      blocked: ['gate-1'],
      browserLane: true,
    });
    await revise(page, next);
    expect(api.made).toHaveLength(1);
    expect(api.made[0]).toEqual({
      title: 'Claude Code is waiting on you',
      body: '[alpha/app] a prompt appeared',
      tag: 'claude:gate-1',
    });
    // The same board again, a poll and a route change raise nothing more.
    await revise(
      page,
      attentionBoard({
        generated: 1_000_050,
        asking: [],
        unowned: false,
        blocked: ['gate-1'],
        browserLane: true,
      }),
    );
    await page.go('#n=sessions');
    expect(api.made).toHaveLength(1);
  });

  it('raises nothing for the gates a board already held when the page opened', async () => {
    const api = script('granted');
    await open(
      attentionBoard({
        asking: [],
        unowned: false,
        blocked: ['gate-2', 'gate-3'],
        browserLane: true,
      }),
    );
    expect(api.made).toEqual([]);
  });

  it('raises one banner for the questions that arrive together, naming the count', async () => {
    const api = script('granted');
    await open(attentionBoard({ browserLane: true }));
    // Asks are the one thing a first board raises for: a question already waiting is still waiting.
    expect(api.made).toHaveLength(1);
    expect(api.made[0]?.title).toBe('6 questions are waiting for your answer');
    expect(api.made[0]?.tag).toBe('cargento-ask');
  });

  it('raises nothing without permission, and a revoked permission is not an error', async () => {
    const api = script('default');
    const page = await open(attentionBoard({ asking: [], unowned: false, browserLane: true }));
    await revise(
      page,
      attentionBoard({
        generated: 1_000_025,
        asking: [],
        unowned: false,
        blocked: ['gate-1'],
        browserLane: true,
      }),
    );
    expect(api.made).toEqual([]);
  });
});

describe('the lane report', () => {
  it('reports a granted tab once, when the board does not know of it, and again only after the board says it forgot', async () => {
    script('granted');
    const page = await open(attentionBoard({ asking: [] }));
    expect(lanePosts(page)).toHaveLength(1);
    // The board's answer arrives with a later payload: no further report once it agrees.
    await revise(
      page,
      attentionBoard({ generated: 1_000_025, asking: [], unowned: false, browserLane: true }),
    );
    await revise(
      page,
      attentionBoard({ generated: 1_000_050, asking: [], unowned: false, browserLane: true }),
    );
    expect(lanePosts(page)).toHaveLength(1);
    // A server that restarted and forgot is told again.
    await revise(
      page,
      attentionBoard({ generated: 1_000_075, asking: [], unowned: false, browserLane: false }),
    );
    expect(lanePosts(page)).toHaveLength(2);
  });

  it('reports nothing for a tab that has not been granted', async () => {
    script('default');
    const page = await open(attentionBoard({ asking: [] }));
    await revise(page, attentionBoard({ generated: 1_000_025, asking: [] }));
    expect(lanePosts(page)).toEqual([]);
  });
});
