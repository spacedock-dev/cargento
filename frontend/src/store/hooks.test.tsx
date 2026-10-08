import { act, render } from '@testing-library/react';
import { StrictMode } from 'react';
import { describe, expect, it } from 'vitest';
import type { FetchLike } from '../api/client';
import { createBoardRuntime, type BoardRuntime } from '../transport/runtime';
import { useBoardRuntime } from '../transport/hooks';
import { createFakeClock, createFakeEnvironment, createFakeStorageHub } from '../transport/testing';
import { useBoardSelector } from './hooks';
import { selectDataStatus, selectSessions } from './selectors';

const flush = async () => {
  for (let turn = 0; turn < 12; turn += 1) await Promise.resolve();
};

function fixture() {
  const requests: { method: string; url: string }[] = [];
  const fetch: FetchLike = (url, init) => {
    requests.push({ method: init?.method ?? 'GET', url });
    return Promise.resolve(
      new Response(
        JSON.stringify({ generated: requests.length, sessions: [{ harness: 'claude', sid: 's' }] }),
        {
          status: 200,
          headers: { 'X-Cargento-Revision': `1.${String(requests.length)}` },
        },
      ),
    );
  };
  const clock = createFakeClock();
  const env = createFakeEnvironment({ clock });
  const runtime = createBoardRuntime({
    fetch,
    storage: createFakeStorageHub().forTab(),
    env,
    search: '',
    doc: null,
  });
  return { requests, clock, env, runtime };
}

function Rows({ runtime, onRender }: { runtime: BoardRuntime; onRender: () => void }) {
  useBoardRuntime(runtime);
  const sessions = useBoardSelector(runtime.store, selectSessions);
  const status = useBoardSelector(runtime.store, selectDataStatus);
  onRender();
  return <p>{`${status}:${String(sessions.rows.length)}`}</p>;
}

function Status({ runtime, onRender }: { runtime: BoardRuntime; onRender: () => void }) {
  const refreshing = useBoardSelector(runtime.store, (snapshot) => snapshot.manualRefreshing);
  onRender();
  return <p>{String(refreshing)}</p>;
}

describe('React subscriptions to the board', () => {
  it('opens one stream and reads once under StrictMode, then releases everything on unmount', async () => {
    const { requests, clock, env, runtime } = fixture();
    const view = render(
      <StrictMode>
        <Rows runtime={runtime} onRender={() => undefined} />
      </StrictMode>,
    );
    clock.advance(0);
    await act(flush);
    expect(requests.filter((request) => request.url.startsWith('/api/data'))).toHaveLength(1);
    expect(env.streamOpens()).toBe(1);
    expect(view.getByText('ready:1')).toBeVisible();
    view.unmount();
    clock.advance(0);
    expect(env.openStreams()).toBe(0);
    expect(clock.activeTimers()).toBe(0);
    expect(runtime.store.subscriberCount()).toBe(0);
  });

  it('issues no POST from mounting, remounting or live updates', async () => {
    const { requests, clock, env, runtime } = fixture();
    const first = render(<Rows runtime={runtime} onRender={() => undefined} />);
    await act(flush);
    first.unmount();
    clock.advance(0);
    const second = render(
      <StrictMode>
        <Rows runtime={runtime} onRender={() => undefined} />
      </StrictMode>,
    );
    await act(flush);
    env.sources.at(-1)?.emit('revision', '9.9');
    await act(flush);
    second.unmount();
    clock.advance(0);
    expect(requests.some((request) => request.method === 'POST')).toBe(false);
  });

  it('re-renders a subscriber only when the slice it selected changed', async () => {
    const { runtime } = fixture();
    let rowRenders = 0;
    let statusRenders = 0;
    render(
      <>
        <Rows runtime={runtime} onRender={() => (rowRenders += 1)} />
        <Status runtime={runtime} onRender={() => (statusRenders += 1)} />
      </>,
    );
    await act(flush);
    const rowsAfterLoad = rowRenders;
    const statusAfterLoad = statusRenders;
    act(() => runtime.store.setManualRefreshing(true));
    expect(statusRenders).toBe(statusAfterLoad + 1);
    expect(rowRenders).toBe(rowsAfterLoad);
    act(() => runtime.store.setPending(['a']));
    expect(rowRenders).toBe(rowsAfterLoad);
    expect(statusRenders).toBe(statusAfterLoad + 1);
  });
});
