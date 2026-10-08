import { useEffect } from 'react';
import type { BoardRuntime } from './runtime';

/* Acquire on mount, release on unmount. The runtime defers teardown one tick,
   so StrictMode's effect, cleanup, effect reuses one owner. */
export function useBoardRuntime(runtime: BoardRuntime): void {
  useEffect(() => runtime.acquire(), [runtime]);
}
