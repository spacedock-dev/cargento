import { useSyncExternalStore } from 'react';
import type { BoardSnapshot } from '../store/board';
import type { DisplayGate } from './displayGate';

/* `useBoardSelector`, over what the reader is shown rather than what the store
   accepted. The selector must return a stable value while its slice is unchanged. */
export function useDisplayedSelector<T>(
  gate: DisplayGate,
  selector: (snapshot: BoardSnapshot) => T,
): T {
  return useSyncExternalStore(gate.subscribe, () => selector(gate.getSnapshot()));
}
