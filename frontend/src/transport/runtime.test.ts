import { describe, expect, it } from 'vitest';
import type { FetchLike } from '../api/client';
import type { PayloadData } from '../api/types';
import { selectDataStatus, selectSessions } from '../store/selectors';
import { createBoardRuntime, replaceRuntime, type BoardRuntime } from './runtime';
import { createFakeClock, createFakeEnvironment, createFakeStorageHub, type FakeClock, type FakeStorageHub } from './testing';

const flush = async () => {
  for (let turn = 0; turn < 12; turn += 1) await Promise.resolve();
};

interface Backend {
  fetch: FetchLike;
  readonly requests: { readonly method: string; readonly url: string }[];
  generated: number;
  revision: string;
  respond: (url: string) => Response;
  gets(prefix?: string): number;
  posts(): number;
}

function backend(): Backend {
  const requests: { method: string; url: string }[] = [];
  const state: Backend = {
    requests,
    generated: 1,
    revision: '5.1',
    respond: () =>
      new Response(
        JSON.stringify({ generated: state.generated, build: 'b1', sessions: [{ harness: 'claude', sid: `s${String(state.generated)}` }] }),
        { status: 200, headers: { 'X-Cargento-Revision': state.revision } },
      ),
    fetch: (url, init) => {
      requests.push({ method: init?.method ?? 'GET', url });
      return Promise.resolve(state.respond(url));
    },
    gets: (prefix = '/api/data') => requests.filter((request) => request.method === 'GET' && request.url.startsWith(prefix)).length,
    posts: () => requests.filter((request) => request.method === 'POST').length,
  };
  return state;
}

function runtimeFor(options: { api?: Backend; clock?: FakeClock; hub?: FakeStorageHub; tabId?: string; search?: string; streamSupported?: boolean } = {}) {
  const api = options.api ?? backend();
  const clock = options.clock ?? createFakeClock();
  const hub = options.hub ?? createFakeStorageHub();
  const env = createFakeEnvironment({ clock, tabId: options.tabId ?? 'tab-a', streamSupported: options.streamSupported ?? true });
  const storage = hub.forTab();
  const runtime = createBoardRuntime({
    fetch: api.fetch,
    storage,
    env,
    search: options.search ?? '',
    doc: null,
  });
  return { api, clock, hub, env, storage, runtime };
}

describe('start and dispose', () => {
  it('reads once, opens one stream and accepts the body into the store', async () => {
    const { api, env, runtime } = runtimeFor();
    runtime.start();
    await flush();
    expect(api.gets()).toBe(1);
    expect(env.streamOpens()).toBe(1);
    const snapshot = runtime.store.getSnapshot();
    expect(snapshot.revision).toBe('5.1');
    expect(selectSessions(snapshot).rows).toHaveLength(1);
    expect(selectDataStatus(snapshot)).toBe('ready');
    runtime.dispose();
  });

  it('is idempotent: a second start is a no-op and a second dispose too', async () => {
    const { api, env, clock, runtime } = runtimeFor();
    runtime.start();
    runtime.start();
    await flush();
    expect(api.gets()).toBe(1);
    expect(env.openStreams()).toBe(1);
    runtime.dispose();
    runtime.dispose();
    expect(env.openStreams()).toBe(0);
    expect(clock.activeTimers()).toBe(0);
  });

  it('leaves no stream, timer, listener, subscription or lease behind', async () => {
    const { env, clock, hub, runtime } = runtimeFor();
    runtime.start();
    await flush();
    runtime.dispose();
    expect(env.openStreams()).toBe(0);
    expect(env.listenerCount()).toBe(0);
    expect(clock.activeTimers()).toBe(0);
    expect(hub.subscriberCount()).toBe(0);
    expect(hub.lease).toBeNull();
  });

  it('keeps one owner after repeated start and dispose cycles', async () => {
    const { env, clock, hub, runtime } = runtimeFor();
    for (let cycle = 0; cycle < 5; cycle += 1) {
      runtime.start();
      runtime.dispose();
    }
    runtime.start();
    await flush();
    expect(env.openStreams()).toBe(1);
    expect(env.listenerCount()).toBe(2);
    expect(clock.activeTimers()).toBe(2);
    expect(hub.subscriberCount()).toBe(1);
    expect(runtime.store.subscriberCount()).toBe(0);
    runtime.dispose();
  });

  it('keeps the accepted board across a dispose and a later start', async () => {
    const { runtime } = runtimeFor();
    runtime.start();
    await flush();
    const data = runtime.store.getSnapshot().data;
    runtime.dispose();
    expect(runtime.store.getSnapshot().data).toBe(data);
  });

  it('drops a read still in flight when disposed', async () => {
    const api = backend();
    let release: (response: Response) => void = () => undefined;
    const held: FetchLike = (url, init) => {
      api.requests.push({ method: init?.method ?? 'GET', url });
      return new Promise<Response>((resolve) => (release = resolve));
    };
    const clock = createFakeClock();
    const env = createFakeEnvironment({ clock });
    const runtime = createBoardRuntime({ fetch: held, storage: createFakeStorageHub().forTab(), env, search: '', doc: null });
    runtime.start();
    runtime.dispose();
    release(api.respond('/api/data'));
    await flush();
    expect(runtime.store.getSnapshot().data).toBeNull();
  });
});

describe('StrictMode and acquire', () => {
  it('opens one stream and reads once across a double effect', async () => {
    const { api, env, clock, runtime } = runtimeFor();
    const releaseFirst = runtime.acquire();
    releaseFirst();
    const releaseSecond = runtime.acquire();
    clock.advance(0);
    await flush();
    expect(api.gets()).toBe(1);
    expect(env.streamOpens()).toBe(1);
    expect(env.openStreams()).toBe(1);
    releaseSecond();
    clock.advance(0);
    expect(env.openStreams()).toBe(0);
    expect(clock.activeTimers()).toBe(0);
  });

  it('ignores a release called twice and keeps the owner while another holder remains', async () => {
    const { env, clock, runtime } = runtimeFor();
    const a = runtime.acquire();
    const b = runtime.acquire();
    a();
    a();
    clock.advance(0);
    expect(env.openStreams()).toBe(1);
    b();
    clock.advance(0);
    expect(env.openStreams()).toBe(0);
  });
});

describe('HMR replacement', () => {
  it('disposes the previous runtime before the replacement starts', async () => {
    const api = backend();
    const clock = createFakeClock();
    const hub = createFakeStorageHub();
    const holder: Record<symbol, BoardRuntime | undefined> = {};
    const first = runtimeFor({ api, clock, hub, tabId: 'a' });
    replaceRuntime(first.runtime, holder);
    first.runtime.start();
    await flush();
    const second = runtimeFor({ api, clock, hub, tabId: 'a' });
    replaceRuntime(second.runtime, holder);
    second.runtime.start();
    await flush();
    expect(first.env.openStreams()).toBe(0);
    expect(second.env.openStreams()).toBe(1);
    expect(clock.activeTimers()).toBe(2);
    expect(hub.subscriberCount()).toBe(1);
    expect(api.posts()).toBe(0);
  });
});

describe('live updates', () => {
  it('refetches once for a newer stream revision and not for a repeat or an older one', async () => {
    const { api, env, runtime } = runtimeFor();
    runtime.start();
    await flush();
    api.generated = 2;
    api.revision = '5.2';
    env.sources[0]?.emit('revision', '5.2');
    await flush();
    expect(api.gets()).toBe(2);
    env.sources[0]?.emit('revision', '5.2');
    env.sources[0]?.emit('revision', '5.1');
    await flush();
    expect(api.gets()).toBe(2);
    expect(runtime.store.getSnapshot().revision).toBe('5.2');
    runtime.dispose();
  });

  it('does not refetch for a stream revision the last read already carried', async () => {
    const { api, env, runtime } = runtimeFor();
    runtime.start();
    await flush();
    env.sources[0]?.emit('revision', '5.1');
    await flush();
    expect(api.gets()).toBe(1);
    runtime.dispose();
  });

  it('polls every 20 s beside the stream and every 5 s without one', async () => {
    const withStream = runtimeFor();
    withStream.runtime.start();
    await flush();
    withStream.clock.advance(20_000);
    await flush();
    expect(withStream.api.gets()).toBe(2);
    withStream.runtime.dispose();

    const without = runtimeFor({ streamSupported: false });
    without.runtime.start();
    await flush();
    without.clock.advance(5000);
    await flush();
    expect(without.api.gets()).toBe(2);
    expect(without.env.streamOpens()).toBe(0);
    without.runtime.dispose();
  });

  it('survives a stream reconnect without refetching, replaying or duplicating', async () => {
    const { api, env, clock, runtime } = runtimeFor();
    runtime.start();
    await flush();
    env.sources[0]?.fail(0);
    env.sources[0]?.fail(2);
    clock.advance(2000);
    await flush();
    expect(env.streamOpens()).toBe(2);
    expect(env.openStreams()).toBe(1);
    expect(api.gets()).toBe(1);
    expect(api.posts()).toBe(0);
    runtime.dispose();
  });
});

describe('several tabs', () => {
  it('opens one stream across two tabs and wakes the follower through storage', async () => {
    const api = backend();
    const clock = createFakeClock();
    const hub = createFakeStorageHub();
    const a = runtimeFor({ api, clock, hub, tabId: 'a' });
    const b = runtimeFor({ api, clock, hub, tabId: 'b' });
    a.runtime.start();
    b.runtime.start();
    await flush();
    clock.advance(4000);
    await flush();
    expect(a.env.openStreams() + b.env.openStreams()).toBe(1);
    const before = api.gets();
    api.generated = 2;
    api.revision = '5.2';
    a.env.sources[0]?.emit('revision', '5.2');
    await flush();
    expect(api.gets() - before).toBe(2);
    expect(a.runtime.store.getSnapshot().revision).toBe('5.2');
    expect(b.runtime.store.getSnapshot().revision).toBe('5.2');
    a.runtime.dispose();
    b.runtime.dispose();
  });
});

describe('failure states', () => {
  it('keeps the last accepted board when a later read fails, with the status explicit', async () => {
    const { api, clock, runtime } = runtimeFor();
    runtime.start();
    await flush();
    const accepted = runtime.store.getSnapshot().data;
    api.respond = () => new Response('<h1>403</h1>', { status: 403 });
    clock.advance(20_000);
    await flush();
    const snapshot = runtime.store.getSnapshot();
    expect(snapshot.data).toBe(accepted);
    expect(snapshot.failures).toBe(1);
    expect(snapshot.lastFailure).toEqual({ kind: 'http-error', status: 403 });
    expect(selectDataStatus(snapshot)).toBe('stale');
    api.respond = () => new Response(JSON.stringify({ generated: 3, sessions: [] }), { status: 200 });
    clock.advance(20_000);
    await flush();
    expect(runtime.store.getSnapshot().failures).toBe(0);
    runtime.dispose();
  });

  it('reports unavailable, not an empty healthy board, when the first read fails', async () => {
    const api = backend();
    api.respond = () => new Response('', { status: 503 });
    const { runtime } = runtimeFor({ api });
    runtime.start();
    await flush();
    expect(selectDataStatus(runtime.store.getSnapshot())).toBe('unavailable');
    expect(runtime.store.getSnapshot().data).toBeNull();
    runtime.dispose();
  });

  it('treats a network failure and a malformed body as failures with their own kinds', async () => {
    const down = backend();
    down.fetch = () => Promise.reject(new TypeError('offline'));
    const first = runtimeFor({ api: down });
    first.runtime.start();
    await flush();
    expect(first.runtime.store.getSnapshot().lastFailure).toEqual({ kind: 'network-error' });
    first.runtime.dispose();

    const bad = backend();
    bad.respond = () => new Response('<html>', { status: 200 });
    const second = runtimeFor({ api: bad });
    second.runtime.start();
    await flush();
    expect(second.runtime.store.getSnapshot().lastFailure).toEqual({ kind: 'malformed', status: 200 });
    second.runtime.dispose();
  });

  it('keeps a missing sessions field distinct from an empty one', async () => {
    const api = backend();
    api.respond = () => new Response(JSON.stringify({ generated: 1 }), { status: 200 });
    const { runtime } = runtimeFor({ api });
    runtime.start();
    await flush();
    expect(selectSessions(runtime.store.getSnapshot())).toEqual({ present: false, rows: [] });
    runtime.dispose();
  });

  it('flags a later build as reload-required while data keeps updating', async () => {
    const { api, clock, runtime } = runtimeFor();
    runtime.start();
    await flush();
    api.respond = () => new Response(JSON.stringify({ generated: 2, build: 'b2', sessions: [] }), { status: 200 });
    clock.advance(20_000);
    await flush();
    const snapshot = runtime.store.getSnapshot();
    expect(snapshot.firstBuild).toBe('b1');
    expect(snapshot.data?.build).toBe('b2');
    runtime.dispose();
  });
});

describe('request shape', () => {
  it('sends all=1 only for the exact query value', async () => {
    for (const [search, expected] of [
      ['?all=1', '/api/data?all=1'],
      ['?all=true', '/api/data'],
      ['?x=1&all=1', '/api/data?all=1'],
    ] as const) {
      const { api, runtime } = runtimeFor({ search });
      runtime.start();
      await flush();
      expect(api.requests[0]?.url, search).toBe(expected);
      runtime.dispose();
    }
  });

  it('adds usage=1 only while quota consent is granted', async () => {
    const { api, hub, storage, clock, runtime } = runtimeFor();
    runtime.start();
    await flush();
    storage.setUsageConsent('declined');
    clock.advance(20_000);
    await flush();
    storage.setUsageConsent('granted');
    clock.advance(20_000);
    await flush();
    expect(hub.usage).toBe('granted');
    expect(api.requests.map((request) => request.url)).toEqual(['/api/data', '/api/data', '/api/data?usage=1']);
    runtime.dispose();
  });
});

describe('actions are explicit', () => {
  it('issues no POST across start, polling, wakes, reconnects, StrictMode and disposal', async () => {
    const { api, env, clock, runtime } = runtimeFor();
    const release = runtime.acquire();
    clock.advance(0);
    env.sources[0]?.emit('revision', '5.2');
    env.sources[0]?.fail(2);
    clock.advance(60_000);
    await flush();
    release();
    clock.advance(0);
    expect(api.posts()).toBe(0);
    expect(api.requests.every((request) => request.url.startsWith('/api/data'))).toBe(true);
  });

  it('sends a focus request only when called and only with a capability', async () => {
    const api = backend();
    api.respond = (url) =>
      url === '/api/focus' ? new Response(JSON.stringify({ focused: true }), { status: 200 }) : backend().respond(url);
    const clock = createFakeClock();
    const env = createFakeEnvironment({ clock });
    const withCapability = createBoardRuntime({
      fetch: api.fetch,
      storage: createFakeStorageHub().forTab(),
      env,
      search: '',
      doc: documentWithFocus('cap'),
    });
    withCapability.start();
    await flush();
    expect(api.posts()).toBe(0);
    expect(await withCapability.focus({ harness: 'claude', sid: 's1' })).toBe('sent');
    expect(api.posts()).toBe(1);
    withCapability.dispose();

    const without = runtimeFor({ api: backend() });
    expect(await without.runtime.focus({ harness: 'claude', sid: 's1' })).toBe('unavailable');
    expect(without.api.posts()).toBe(0);
  });
});

describe('pending work', () => {
  it('mirrors pending keys into the store and clears every timer on dispose', async () => {
    const { clock, runtime } = runtimeFor();
    runtime.start();
    await flush();
    const token = runtime.pending.start('save:a', 'Saving');
    expect(runtime.store.getSnapshot().pending).toEqual(['save:a']);
    expect(runtime.pending.start('save:a', 'Saving')).toBeNull();
    runtime.pending.end('save:a', token);
    expect(runtime.store.getSnapshot().pending).toEqual([]);
    runtime.pending.start('save:b', 'Saving', 'Saving.');
    runtime.dispose();
    expect(clock.activeTimers()).toBe(0);
    expect(runtime.store.getSnapshot().pending).toEqual([]);
  });

  it('clears a lost request at the backstop and updates the store', async () => {
    const { clock, runtime } = runtimeFor();
    runtime.start();
    await flush();
    runtime.pending.start('save:a', 'Saving');
    clock.advance(20_000);
    expect(runtime.store.getSnapshot().pending).toEqual([]);
    runtime.dispose();
  });
});

describe('typed payload shape', () => {
  it('keeps fields the types do not name', async () => {
    const api = backend();
    const extra: PayloadData & { future_field?: number } = { generated: 1, sessions: [], future_field: 7 };
    api.respond = () => new Response(JSON.stringify(extra), { status: 200 });
    const { runtime } = runtimeFor({ api });
    runtime.start();
    await flush();
    expect(runtime.store.getSnapshot().data).toMatchObject({ future_field: 7 });
    runtime.dispose();
  });
});

function documentWithFocus(content: string): Pick<Document, 'querySelector'> {
  const page = document.implementation.createHTMLDocument('x');
  const meta = page.createElement('meta');
  meta.setAttribute('name', 'cargento-focus');
  meta.setAttribute('content', content);
  page.head.append(meta);
  return page;
}
