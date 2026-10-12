import { expect, it } from 'vitest';
import { createApiClient } from '../api/client';
import { contextKey } from '../api/identity';
import { createBoardStore } from '../store/board';
import { createRecordLoader } from './record';

it('a reader leaving a session aborts its request even when the network ignores cancellation', async () => {
  let signal: AbortSignal | null | undefined;
  const client = createApiClient({
    fetch: (_url, init) => {
      signal = init?.signal;
      return new Promise<Response>(() => undefined);
    },
  });
  const store = createBoardStore({ now: () => 0 });
  const loader = createRecordLoader({ client, store });
  const scope = { projectKey: '/one', focus: { harness: 'claude', sid: 'same' } };
  const leave = loader.open(scope);
  expect(signal?.aborted).toBe(false);
  leave();
  await Promise.resolve();
  expect(signal?.aborted).toBe(true);
  expect(store.getSnapshot().records.has(contextKey(scope.projectKey, scope.focus))).toBe(false);
  loader.dispose();
});

it('a reader opening identical session ids in different projects keeps their pages apart', async () => {
  const client = createApiClient({
    fetch: (url) => {
      const query = new URLSearchParams(url.split('?')[1]);
      return Promise.resolve(
        new Response(
          JSON.stringify({
            session: { harness: 'claude', sid: 'same' },
            entries: [],
            state: 'ok',
            next: query.get('project'),
            reached_start: false,
            bound: null,
            scanned_bytes: 0,
            kinds: ['user_message', 'agent_message'],
          }),
        ),
      );
    },
  });
  const store = createBoardStore({ now: () => 0 });
  const loader = createRecordLoader({ client, store });
  const focus = { harness: 'claude', sid: 'same' };
  const first = loader.open({ projectKey: '/one', focus });
  const second = loader.open({ projectKey: '/two', focus });
  await loader.more({ projectKey: '/one', focus });
  await loader.more({ projectKey: '/two', focus });
  expect(store.getSnapshot().records.get(contextKey('/one', focus))?.next).toBe('/one');
  expect(store.getSnapshot().records.get(contextKey('/two', focus))?.next).toBe('/two');
  first();
  await Promise.resolve();
  expect(store.getSnapshot().records.size).toBe(1);
  second();
  loader.dispose();
});
