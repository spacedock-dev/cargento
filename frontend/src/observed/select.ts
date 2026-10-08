import type { BoardSnapshot } from '../store/board';
import { observe, type Observed } from './model';

const byBody = new WeakMap<object, Observed>();
const EMPTY: Observed = observe(null);

/* The model of the accepted body, computed once per body: a subscriber that selects it gets the same
   object back until the data is replaced, which `useSyncExternalStore` needs, and a poll that changed
   nothing costs nothing. Unread is the empty model, and callers say "unread" from the snapshot itself. */
export function observedFor(body: object | null): Observed {
  if (!body) return EMPTY;
  let cached = byBody.get(body);
  if (!cached) {
    cached = observe(body);
    byBody.set(body, cached);
  }
  return cached;
}

export function selectObserved(snapshot: BoardSnapshot): Observed {
  return observedFor(snapshot.data);
}
