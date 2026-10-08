import { useCallback } from 'react';
import type { FocusKeyOptions, FocusLane } from './focusLane';

/* A ref callback, so registration follows the node itself: attach on mount, and
   the returned cleanup runs when the node is removed, before the DOM forgets it. */
export function useFocusKey<T extends HTMLElement>(
  lane: FocusLane | null,
  key: string | null,
  options: FocusKeyOptions = {},
) {
  const { fallback } = options;
  return useCallback(
    (element: T | null) => {
      if (!lane || !key || !element) return undefined;
      return lane.register(key, element, fallback === undefined ? {} : { fallback });
    },
    [lane, key, fallback],
  );
}
