import { readBootstrap } from '../api/bootstrap';
import { createApiClient, type FetchLike } from '../api/client';
import type { FocusOutcome, SessionIdentity } from '../api/types';
import { createBoardStore } from '../store/board';
import { createContextLoader, type ContextScope } from './context';
import { createLiveTransport } from './live';
import { createPendingRegistry, type PendingToken } from './pending';
import type { Environment, TimerHandle, TransportStorage } from './ports';
import { createRefreshController, type DataOutcome, type RefreshSink } from './refresh';
import { createRevisionMemo } from './revision';

export interface RuntimeOptions {
  readonly fetch: FetchLike;
  readonly storage: TransportStorage;
  readonly env: Environment;
  /** `location.search` of the page. */
  readonly search: string;
  readonly doc: Pick<Document, 'querySelector'> | null;
  /** Where a consumer holds back painting (see `store/commit-gate`). Absent means paint at once. */
  readonly paint?: RefreshSink['paint'];
  readonly announce?: (key: string, sentence: string) => void;
}

/* The one place the board's resources are started and stopped. The store
   outlives a start/dispose cycle so a remounted view still has the last
   accepted board; every fetch, socket, timer and listener belongs to an
   `Owned` set created by `start` and torn down whole by `dispose`.

   Nothing in here issues a POST. Actions are the caller's explicit
   `client.post*` calls, so a reconnect, a poll, a store subscription or a
   remount cannot replay one. */
export function createBoardRuntime(options: RuntimeOptions) {
  const { env, storage } = options;
  const bootstrap = readBootstrap(options.search, options.doc);
  const client = createApiClient({ fetch: options.fetch });
  const store = createBoardStore({ now: env.clock.now });
  const revisions = createRevisionMemo();

  interface Owned {
    readonly refresh: ReturnType<typeof createRefreshController>;
    readonly context: ReturnType<typeof createContextLoader>;
    readonly live: ReturnType<typeof createLiveTransport>;
    readonly pending: ReturnType<typeof createPendingRegistry>;
  }

  let owned: Owned | null = null;
  let holders = 0;
  let teardown: TimerHandle | null = null;

  function create(): Owned {
    const pending = createPendingRegistry({
      clock: env.clock,
      onChange: () => store.setPending(pending.keys()),
      announce: options.announce ?? (() => undefined),
    });
    const sink: RefreshSink = {
      async fetchData(signal): Promise<DataOutcome> {
        const result = await client.getData({
          showAll: bootstrap.showAll,
          usage: storage.usageConsent() === 'granted',
          signal,
        });
        switch (result.kind) {
          case 'ok':
            return { kind: 'data', body: result.body, revision: result.revision };
          case 'http-error':
            return { kind: 'failed', failure: { kind: 'http-error', status: result.status } };
          case 'malformed':
            return { kind: 'failed', failure: { kind: 'malformed', status: result.status } };
          case 'network-error':
            return { kind: 'failed', failure: { kind: 'network-error' } };
          case 'aborted':
            return { kind: 'aborted' };
        }
      },
      manualInFlight: (active) => store.setManualRefreshing(active),
      accepted: (body, revision) => store.acceptData(body, revision),
      failed: (failure) => store.recordFailure(failure),
      paint: options.paint ?? (() => Promise.resolve()),
    };
    const refresh = createRefreshController({ sink, revisions });
    return {
      refresh,
      pending,
      context: createContextLoader({ client, store, storage }),
      live: createLiveTransport({
        env,
        storage,
        revisions,
        onWake: (revision) => refresh.wake(revision),
        onPoll: () => void refresh.poll(),
      }),
    };
  }

  function start(): void {
    if (owned) return;
    owned = create();
    owned.live.start();
  }

  function dispose(): void {
    if (teardown !== null) env.clock.clearTimeout(teardown);
    teardown = null;
    holders = 0;
    const closing = owned;
    owned = null;
    if (!closing) return;
    closing.live.dispose();
    closing.refresh.dispose();
    closing.context.dispose();
    closing.pending.dispose();
    store.setPending([]);
  }

  const pending = {
    start(key: string, busy: string, say = ''): PendingToken | null {
      const token = owned?.pending.start(key, busy, say) ?? null;
      if (token && owned) store.setPending(owned.pending.keys());
      return token;
    },
    end(key: string, token: PendingToken | null | undefined): boolean {
      const ended = owned?.pending.end(key, token) ?? false;
      if (ended && owned) store.setPending(owned.pending.keys());
      return ended;
    },
    has: (key: string): boolean => owned?.pending.has(key) ?? false,
  };

  return {
    store,
    client,
    bootstrap,
    pending,
    start,
    dispose,

    /* For a component effect. React's StrictMode runs effect, cleanup, effect
       on mount; teardown is deferred one tick so that sequence reuses the
       running owner instead of opening a second stream and reading twice. */
    acquire(): () => void {
      holders += 1;
      if (teardown !== null) env.clock.clearTimeout(teardown);
      teardown = null;
      start();
      let released = false;
      return () => {
        if (released) return;
        released = true;
        holders -= 1;
        if (holders > 0 || teardown !== null) return;
        teardown = env.clock.setTimeout(() => {
          teardown = null;
          if (holders === 0) dispose();
        }, 0);
      };
    },

    refresh: (flags: { readonly manual?: boolean } = {}): Promise<void> => owned?.refresh.refresh(flags) ?? Promise.resolve(),
    loadContext: (scope: ContextScope): void => owned?.context.load(scope),
    requestObserverSummary: (scope: ContextScope): Promise<void> => owned?.context.requestObserverSummary(scope) ?? Promise.resolve(),

    /** One explicit attempt. No capability sends nothing. */
    focus: (identity: SessionIdentity): Promise<FocusOutcome> =>
      client.focus({ identity, capability: bootstrap.focusCapability }),
  };
}

export type BoardRuntime = ReturnType<typeof createBoardRuntime>;

const SLOT = Symbol.for('cargento.board.runtime');

/* Module replacement re-runs the module that creates the runtime. The previous
   one is disposed here, before the replacement can start, so a hot update
   cannot leave two owners with a stream each. */
export function replaceRuntime(
  next: BoardRuntime,
  holder: Record<symbol, BoardRuntime | undefined> = globalThis as unknown as Record<symbol, BoardRuntime | undefined>,
): BoardRuntime {
  holder[SLOT]?.dispose();
  holder[SLOT] = next;
  return next;
}
