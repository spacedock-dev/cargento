import { useSyncExternalStore } from 'react';
import type { BoardSnapshot, BoardStore } from './board';

/* The selector must return a stable value while the slice it reads is
   unchanged, which the memoised selectors in `./selectors` do. */
export function useBoardSelector<T>(
  store: BoardStore,
  selector: (snapshot: BoardSnapshot) => T,
): T {
  return useSyncExternalStore(store.subscribe, () => selector(store.getSnapshot()));
}
