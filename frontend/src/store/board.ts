import type { PayloadData, ProjectContext } from '../api/types';

export type DataFailure =
  | { readonly kind: 'http-error'; readonly status: number }
  | { readonly kind: 'network-error' }
  | { readonly kind: 'malformed'; readonly status: number };

/* `data` and `error` are independent on purpose. A failed read over a loaded
   context keeps the previous data beside the new error, which a reader keying
   off `data` alone cannot tell from a clean resolve, so the five states are
   derived from both fields (`selectContextState`). */
export interface ContextEntry {
  readonly data: ProjectContext | null;
  readonly revision: number;
  readonly error: DataFailure | null;
}

export interface BoardSnapshot {
  /** The last accepted body, exactly as the server sent it. */
  readonly data: PayloadData | null;
  /** The `X-Cargento-Revision` of that body, or '' when it carried none. */
  readonly revision: string;
  readonly acceptedCount: number;
  /** Failed current reads since the last accepted body. */
  readonly failures: number;
  readonly lastFailure: DataFailure | null;
  readonly lastSuccessAt: number | null;
  readonly manualRefreshing: boolean;
  readonly firstBuild: string;
  readonly contexts: ReadonlyMap<string, ContextEntry>;
  readonly observer: {
    readonly requests: readonly string[];
    readonly states: ReadonlyMap<string, 'ready' | 'error'>;
  };
  readonly pending: readonly string[];
}

const INITIAL: BoardSnapshot = Object.freeze({
  data: null,
  revision: '',
  acceptedCount: 0,
  failures: 0,
  lastFailure: null,
  lastSuccessAt: null,
  manualRefreshing: false,
  firstBuild: '',
  contexts: new Map(),
  observer: { requests: [], states: new Map() },
  pending: [],
});

function sameList(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

/* An immutable snapshot replaced on every change and left alone otherwise, so
   `useSyncExternalStore` sees a stable identity while nothing happened. The
   store only holds what was accepted; when to SHOW it is `commit-gate`'s
   decision, so acceptance and paint stay separate. */
export function createBoardStore(deps: { readonly now: () => number }) {
  let snapshot: BoardSnapshot = INITIAL;
  const listeners = new Set<() => void>();

  function publish(next: BoardSnapshot): void {
    snapshot = next;
    for (const listener of [...listeners]) listener();
  }

  return {
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: (): BoardSnapshot => snapshot,
    subscriberCount: (): number => listeners.size,

    acceptData(body: PayloadData, revision: string): void {
      const build = typeof body.build === 'string' ? body.build : '';
      publish({
        ...snapshot,
        data: body,
        revision,
        acceptedCount: snapshot.acceptedCount + 1,
        failures: 0,
        lastFailure: null,
        lastSuccessAt: deps.now(),
        firstBuild: snapshot.firstBuild || build,
      });
    },

    recordFailure(failure: DataFailure): void {
      publish({ ...snapshot, failures: snapshot.failures + 1, lastFailure: failure });
    },

    setManualRefreshing(active: boolean): void {
      if (snapshot.manualRefreshing === active) return;
      publish({ ...snapshot, manualRefreshing: active });
    },

    setContext(key: string, entry: ContextEntry): void {
      const contexts = new Map(snapshot.contexts);
      contexts.set(key, entry);
      publish({ ...snapshot, contexts });
    },

    setObserverRequest(key: string, active: boolean): void {
      const has = snapshot.observer.requests.includes(key);
      if (has === active) return;
      const requests = active
        ? [...snapshot.observer.requests, key]
        : snapshot.observer.requests.filter((candidate) => candidate !== key);
      publish({ ...snapshot, observer: { ...snapshot.observer, requests } });
    },

    setObserverState(key: string, state: 'ready' | 'error'): void {
      const states = new Map(snapshot.observer.states);
      states.set(key, state);
      publish({ ...snapshot, observer: { ...snapshot.observer, states } });
    },

    setPending(keys: readonly string[]): void {
      if (sameList(snapshot.pending, keys)) return;
      publish({ ...snapshot, pending: [...keys] });
    },
  };
}

export type BoardStore = ReturnType<typeof createBoardStore>;
