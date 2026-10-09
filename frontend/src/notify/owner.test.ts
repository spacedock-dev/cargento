import { describe, expect, it } from 'vitest';
import { createBoardStore } from '../store/board';
import { createNotifyOwner, LANE_REPORT_ATTEMPTS, type NotifyHost } from './owner';
import { startNotifications } from './registry';

/* The rules a banner follows, named one at a time over a scripted host: when the first board primes
   rather than raises, who owns a stage condition, how long a session that keeps falling quiet is left
   alone, and when a lane report is sent, repeated and given up on. The legacy module's own tests are the
   oracle for the first three; `owner.differential.test` runs the whole module against this one. */

function harness(permission = 'granted') {
  const state = {
    permission,
    now: 0,
    leader: true,
    throwing: false,
    supported: true,
    answer: true,
  };
  const banners: { title: string; body: string; tag: string }[] = [];
  let posts = 0;
  const host: NotifyHost = {
    supported: () => state.supported,
    permission: () => (state.supported ? state.permission : 'unsupported'),
    request: () => undefined,
    create(title, options) {
      if (state.throwing) throw new Error('permission revoked');
      banners.push({ title, ...options });
    },
  };
  const owner = createNotifyOwner({
    host,
    now: () => state.now,
    postLane: () => {
      posts += 1;
      return Promise.resolve(state.answer);
    },
    isLeader: () => state.leader,
  });
  return { state, banners, owner, posts: () => posts };
}

const row = (state: string, sid = 's1', harnessKey = 'claude') => ({
  harness: harnessKey,
  sid,
  project: 'repo',
  state,
  active: state !== 'idle',
});

describe('a stage condition', () => {
  it('is primed, leader owned, and raised once per event id', () => {
    const { banners, owner, state } = harness();
    const rule = (id: string) => ({
      id: 'a'.repeat(64),
      event_id: `stage:${id}`,
      workflow: 'flow',
      why: 'Observed task change from build to review.',
    });
    const send = (rules: unknown[], native = '') =>
      owner.sync({ native_notify: native, sessions: [], tripwires: { enabled: true, rules } });
    const counts: number[] = [];
    send([rule('old')]);
    counts.push(banners.length);
    send([rule('new')]);
    counts.push(banners.length);
    send([rule('new')]);
    counts.push(banners.length);
    state.leader = false;
    send([rule('follower')]);
    counts.push(banners.length);
    state.leader = true;
    send([rule('follower')]);
    counts.push(banners.length);
    send([rule('native')], 'osascript');
    counts.push(banners.length);
    send([rule('rearmed')]);
    counts.push(banners.length);
    expect(counts).toEqual([0, 1, 1, 1, 1, 1, 2]);
    expect(banners.map((banner) => banner.tag)).toEqual(['stage:new', 'stage:rearmed']);
    expect(banners[0]?.body).toBe('flow: Observed task change from build to review.');
  });
});

describe('a session that keeps falling quiet', () => {
  it('is nudged once per ten minutes, never delaying a question', () => {
    const { banners, owner, state } = harness();
    const send = (seconds: number, sessions: unknown[], asks: unknown[] = []) => {
      state.now = seconds * 1000;
      owner.sync({
        native_notify: '',
        sessions,
        ask: true,
        asks,
        harnesses: [{ key: 'claude', label: 'Claude' }],
      });
      return banners.length;
    };
    const counts = [
      send(0, [row('working')]),
      send(0, [row('idle')]),
      send(100, [row('working')]),
      send(200, [row('idle')]),
      send(300, [row('working')]),
      send(400, [row('idle')]),
      send(599, [row('working')]),
      send(599.999, [row('idle')]),
      // A suppressed edge still updates what was observed.
      send(600, [row('idle')]),
      send(600, [row('working')]),
      // The inclusive boundary, after a new crossing.
      send(600, [row('idle')]),
    ];
    expect(counts).toEqual([0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2]);
    send(601, [row('working')]);
    send(602, [row('needs_input')], [{ id: 'ask', question: 'Ship?', harness: 'claude' }]);
    expect(banners.slice(2).map((banner) => banner.title)).toEqual([
      'Claude is waiting on you',
      'Claude is asking you',
    ]);
  });

  it('does not start the repeat floor for a nudge that was never raised', () => {
    const { banners, owner, state } = harness('denied');
    state.now = 1_000_000;
    const send = (session: string, native = '') =>
      owner.sync({ native_notify: native, sessions: [row(session, 'unissued')], asks: [] });
    send('working');
    send('idle');
    state.permission = 'granted';
    send('working', 'osascript');
    send('idle', 'osascript');
    state.throwing = true;
    send('working');
    send('idle');
    state.throwing = false;
    send('working');
    send('idle');
    send('working');
    send('idle');
    expect(banners.map((banner) => banner.title)).toEqual(['claude has gone quiet']);
  });
});

describe('the lane report', () => {
  const payload = (generated: number, extra: Record<string, unknown> = {}) => ({
    generated,
    sessions: [],
    ...extra,
  });

  it('is sent once when the payload does not know of the lane, and not again for the same collection', async () => {
    const { owner, posts } = harness();
    owner.sync(payload(1, { browser_lane: false }));
    await Promise.resolve();
    await Promise.resolve();
    // The answer has settled, and the same collection read again reports nothing more.
    owner.sync(payload(1, { browser_lane: false }));
    owner.sync(payload(1, { browser_lane: false }));
    expect(posts()).toBe(1);
    // A newer collection that still says the lane is unknown is a disagreement, and is reported.
    owner.sync(payload(2, { browser_lane: false }));
    expect(posts()).toBe(2);
  });

  it('is never sent by a tab with no permission, and none is sent for a lane the payload already holds', () => {
    const denied = harness('default');
    denied.owner.sync(payload(1, { browser_lane: false }));
    expect(denied.posts()).toBe(0);
    const agreed = harness();
    agreed.owner.sync(payload(1, { browser_lane: true }));
    expect(agreed.posts()).toBe(0);
  });

  it('is sent once to a server that never publishes the key, because there is nothing to read an answer from', async () => {
    const { owner, posts } = harness();
    owner.sync(payload(1));
    await Promise.resolve();
    await Promise.resolve();
    owner.sync(payload(2));
    owner.sync(payload(3));
    expect(posts()).toBe(1);
  });

  it(`gives up after ${String(LANE_REPORT_ATTEMPTS)} refusals instead of reporting on every poll`, async () => {
    const { owner, posts, state } = harness();
    state.answer = false;
    for (let generated = 1; generated <= 8; generated += 1) {
      owner.sync(payload(generated, { browser_lane: false }));
      await Promise.resolve();
      await Promise.resolve();
    }
    expect(posts()).toBe(LANE_REPORT_ATTEMPTS);
  });
});

describe('the owner a runtime holds', () => {
  const fakeRuntime = () => {
    const store = createBoardStore({ now: () => 0 });
    const sent: unknown[] = [];
    const runtime = {
      store,
      client: {
        postLane: (body: unknown) => {
          sent.push(body);
          return Promise.resolve({ kind: 'ok' as const, status: 200, body: {}, revision: '' });
        },
      },
    } as unknown as Parameters<typeof startNotifications>[0];
    return { store, runtime, sent };
  };

  it('is one per runtime however often it is started, and sees each accepted body once', () => {
    const { store, runtime } = fakeRuntime();
    const first = startNotifications(runtime);
    const again = startNotifications(runtime);
    expect(again).toBe(first);
    expect(store.subscriberCount()).toBe(1);
  });

  it('reports the lane as two scalars that name no session', async () => {
    const { store, runtime, sent } = fakeRuntime();
    const state = { permission: 'granted' };
    startNotifications(runtime, {
      host: {
        supported: () => true,
        permission: () => state.permission,
        request: () => undefined,
        create: () => undefined,
      },
    });
    store.acceptData({ generated: 1, sessions: [{ harness: 'claude', sid: 's1' }] }, '7.1');
    await Promise.resolve();
    expect(sent).toEqual([{ supported: true, permission: 'granted' }]);
  });
});
