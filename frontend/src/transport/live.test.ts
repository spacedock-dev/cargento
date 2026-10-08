import { describe, expect, it, vi } from 'vitest';
import { createLiveTransport } from './live';
import { createRevisionMemo } from './revision';
import { createFakeClock, createFakeEnvironment, createFakeStorageHub } from './testing';

function tab(
  options: {
    hub?: ReturnType<typeof createFakeStorageHub>;
    clock?: ReturnType<typeof createFakeClock>;
    tabId?: string;
    streamSupported?: boolean;
  } = {},
) {
  const clock = options.clock ?? createFakeClock();
  const hub = options.hub ?? createFakeStorageHub();
  const env = createFakeEnvironment({
    clock,
    tabId: options.tabId ?? 'tab-a',
    streamSupported: options.streamSupported ?? true,
  });
  const storage = hub.forTab();
  const onWake = vi.fn<(revision: string) => void>();
  const onPoll = vi.fn();
  const revisions = createRevisionMemo();
  const live = createLiveTransport({ env, storage, revisions, onWake, onPoll });
  return { clock, hub, env, storage, onWake, onPoll, revisions, live };
}

describe('starting', () => {
  it('opens one stream, claims the lease and polls once', () => {
    const t = tab();
    t.live.start();
    expect(t.env.streamOpens()).toBe(1);
    expect(t.hub.lease).toEqual({ id: 'tab-a', ts: t.clock.now() });
    expect(t.onPoll).toHaveBeenCalledOnce();
    expect(t.live.isLeader()).toBe(true);
    expect(t.clock.activeTimers()).toBe(2);
    expect(t.env.listenerCount()).toBe(2);
    expect(t.hub.subscriberCount()).toBe(1);
  });

  it('is idempotent', () => {
    const t = tab();
    t.live.start();
    t.live.start();
    expect(t.env.streamOpens()).toBe(1);
    expect(t.onPoll).toHaveBeenCalledOnce();
    expect(t.clock.activeTimers()).toBe(2);
    expect(t.env.listenerCount()).toBe(2);
  });
});

describe('lease election', () => {
  it('renews the lease every 2000 ms without opening a second stream', () => {
    const t = tab();
    t.live.start();
    const first = t.clock.now();
    t.clock.advance(2000);
    expect(t.hub.lease).toEqual({ id: 'tab-a', ts: first + 2000 });
    t.clock.advance(4000);
    expect(t.hub.writes.lease).toBe(4);
    expect(t.env.streamOpens()).toBe(1);
  });

  it('follows a live foreign lease and takes over once it is stale', () => {
    const hub = createFakeStorageHub();
    const t = tab({ hub });
    hub.lease = { id: 'other', ts: t.clock.now() };
    t.live.start();
    expect(t.env.streamOpens()).toBe(0);
    expect(t.live.isLeader()).toBe(false);
    t.clock.advance(5999);
    expect(t.env.streamOpens()).toBe(0);
    t.clock.advance(2);
    expect(t.live.isLeader()).toBe(true);
    expect(t.env.streamOpens()).toBe(1);
    expect(hub.lease?.id).toBe('tab-a');
  });

  it('makes a current leader yield to any foreign lease, even a stale one', () => {
    const hub = createFakeStorageHub();
    const t = tab({ hub });
    t.live.start();
    hub.lease = { id: 'other', ts: t.clock.now() - 60_000 };
    t.clock.advance(2000);
    expect(t.live.isLeader()).toBe(false);
    expect(t.env.openStreams()).toBe(0);
    expect(hub.lease?.id).toBe('other');
  });

  it('lets each tab lead itself when storage is unavailable', () => {
    const hub = createFakeStorageHub();
    hub.available = false;
    const a = tab({ hub, tabId: 'a' });
    const b = tab({ hub, tabId: 'b', clock: a.clock });
    a.live.start();
    b.live.start();
    expect(a.live.isLeader()).toBe(true);
    expect(b.live.isLeader()).toBe(true);
    expect(a.env.openStreams() + b.env.openStreams()).toBe(2);
  });

  it('converges two tabs on one stream', () => {
    const clock = createFakeClock();
    const hub = createFakeStorageHub();
    const a = tab({ hub, clock, tabId: 'a' });
    const b = tab({ hub, clock, tabId: 'b' });
    a.live.start();
    b.live.start();
    clock.advance(10_000);
    expect(a.env.openStreams() + b.env.openStreams()).toBe(1);
    expect(a.live.isLeader()).toBe(true);
    expect(b.live.isLeader()).toBe(false);
  });

  it('hands the stream to the follower after the leader leaves', () => {
    const clock = createFakeClock();
    const hub = createFakeStorageHub();
    const a = tab({ hub, clock, tabId: 'a' });
    const b = tab({ hub, clock, tabId: 'b' });
    a.live.start();
    b.live.start();
    a.env.firePageHide();
    expect(hub.lease).toBeNull();
    // The page is gone, so its timers go with it.
    a.live.dispose();
    clock.advance(2000);
    expect(b.live.isLeader()).toBe(true);
    expect(b.env.openStreams()).toBe(1);
  });

  it('re-elects when the page becomes visible', () => {
    const hub = createFakeStorageHub();
    const t = tab({ hub });
    hub.lease = { id: 'other', ts: t.clock.now() };
    t.live.start();
    expect(t.live.isLeader()).toBe(false);
    hub.lease = { id: 'other', ts: t.clock.now() - 10_000 };
    t.env.fireVisible();
    expect(t.live.isLeader()).toBe(true);
    expect(t.env.openStreams()).toBe(1);
  });

  it('releases its own lease on pagehide and not a foreign one', () => {
    const hub = createFakeStorageHub();
    const leader = tab({ hub });
    leader.live.start();
    leader.env.firePageHide();
    expect(hub.lease).toBeNull();

    const follower = tab({ hub, clock: leader.clock, tabId: 'b' });
    hub.lease = { id: 'other', ts: leader.clock.now() };
    follower.live.start();
    follower.env.firePageHide();
    expect(hub.lease?.id).toBe('other');
  });
});

describe('the stream', () => {
  it('keeps a CONNECTING source and closes, nulls and yields on CLOSED', () => {
    const t = tab();
    t.live.start();
    t.env.sources[0]?.fail(0);
    expect(t.env.openStreams()).toBe(1);
    expect(t.live.isLeader()).toBe(true);
    t.env.sources[0]?.fail(2);
    expect(t.env.openStreams()).toBe(0);
    expect(t.live.isLeader()).toBe(false);
  });

  it('reopens a closed source on the next election', () => {
    const t = tab();
    t.live.start();
    t.env.sources[0]?.fail(2);
    t.clock.advance(2000);
    expect(t.env.streamOpens()).toBe(2);
    expect(t.env.openStreams()).toBe(1);
    expect(t.live.isLeader()).toBe(true);
  });

  it('tolerates a constructor that throws and retries on the next election', () => {
    const t = tab();
    t.env.throwOnOpen = true;
    expect(() => t.live.start()).not.toThrow();
    expect(t.env.streamOpens()).toBe(0);
    t.env.throwOnOpen = false;
    t.clock.advance(2000);
    expect(t.env.openStreams()).toBe(1);
  });

  it('opens no stream and polls every 5 s where EventSource is unsupported', () => {
    const t = tab({ streamSupported: false });
    t.live.start();
    expect(t.env.streamOpens()).toBe(0);
    t.clock.advance(4999);
    expect(t.onPoll).toHaveBeenCalledTimes(1);
    t.clock.advance(1);
    expect(t.onPoll).toHaveBeenCalledTimes(2);
  });

  it('polls every 20 s as a safety net beside the stream', () => {
    const t = tab();
    t.live.start();
    t.clock.advance(19_999);
    expect(t.onPoll).toHaveBeenCalledTimes(1);
    t.clock.advance(1);
    expect(t.onPoll).toHaveBeenCalledTimes(2);
  });
});

describe('revisions', () => {
  it('wakes on a newer stream revision, remembers it and broadcasts it to other tabs only', () => {
    const clock = createFakeClock();
    const hub = createFakeStorageHub();
    const a = tab({ hub, clock, tabId: 'a' });
    const b = tab({ hub, clock, tabId: 'b' });
    a.live.start();
    b.live.start();
    a.env.sources[0]?.emit('revision', '7.2');
    expect(a.onWake).toHaveBeenCalledExactlyOnceWith('7.2');
    expect(a.revisions.get()).toBe('7.2');
    expect(hub.revision).toBe('7.2');
    expect(b.onWake).toHaveBeenCalledExactlyOnceWith('7.2');
    expect(b.revisions.get()).toBe('7.2');
    expect(hub.writes.revision).toBe(1);
  });

  it('ignores an empty, repeated or older stream revision', () => {
    const t = tab();
    t.live.start();
    const source = t.env.sources[0];
    source?.emit('revision', '');
    source?.emit('revision', undefined);
    source?.emit('revision', '7.2');
    source?.emit('revision', '7.2');
    source?.emit('revision', '7.1');
    expect(t.onWake).toHaveBeenCalledTimes(1);
    expect(t.hub.writes.revision).toBe(1);
  });

  it('ignores a revision this tab already fetched at', () => {
    const t = tab();
    t.live.start();
    t.revisions.advance('7.5');
    t.env.sources[0]?.emit('revision', '7.5');
    expect(t.onWake).not.toHaveBeenCalled();
    expect(t.hub.writes.revision).toBe(0);
  });

  it('treats a changed server start as newer', () => {
    const t = tab();
    t.live.start();
    t.revisions.advance('7.900');
    t.env.sources[0]?.emit('revision', '8.1');
    expect(t.onWake).toHaveBeenCalledExactlyOnceWith('8.1');
  });

  it('does not rebroadcast a revision that arrived from storage', () => {
    const hub = createFakeStorageHub();
    const follower = tab({ hub, tabId: 'b' });
    const other = hub.forTab();
    follower.live.start();
    other.writeRevision('7.9');
    other.writeRevision('7.9');
    expect(follower.onWake).toHaveBeenCalledExactlyOnceWith('7.9');
    expect(hub.writes.revision).toBe(2);
  });
});

describe('disposal', () => {
  it('closes only its own stream, releases its lease and removes every timer and listener', () => {
    const t = tab();
    t.live.start();
    t.live.dispose();
    expect(t.env.openStreams()).toBe(0);
    expect(t.hub.lease).toBeNull();
    expect(t.clock.activeTimers()).toBe(0);
    expect(t.env.listenerCount()).toBe(0);
    expect(t.hub.subscriberCount()).toBe(0);
  });

  it('leaves a foreign lease and a foreign stream alone', () => {
    const clock = createFakeClock();
    const hub = createFakeStorageHub();
    const a = tab({ hub, clock, tabId: 'a' });
    const b = tab({ hub, clock, tabId: 'b' });
    a.live.start();
    b.live.start();
    b.live.dispose();
    expect(hub.lease?.id).toBe('a');
    expect(a.env.openStreams()).toBe(1);
  });

  it('ignores events of a source it closed and does nothing after disposal', () => {
    const t = tab();
    t.live.start();
    const source = t.env.sources[0];
    t.live.dispose();
    source?.emit('revision', '9.9');
    source?.fail(2);
    t.clock.advance(60_000);
    expect(t.onWake).not.toHaveBeenCalled();
    expect(t.onPoll).toHaveBeenCalledTimes(1);
    expect(t.env.streamOpens()).toBe(1);
  });

  it('is idempotent and can start again as a fresh owner', () => {
    const t = tab();
    t.live.start();
    t.live.dispose();
    t.live.dispose();
    t.live.start();
    expect(t.env.openStreams()).toBe(1);
    expect(t.clock.activeTimers()).toBe(2);
    expect(t.env.listenerCount()).toBe(2);
  });
});
