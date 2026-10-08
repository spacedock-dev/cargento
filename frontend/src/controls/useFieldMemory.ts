import { useCallback, useLayoutEffect, useRef } from 'react';
import { useControls } from './kit';

/* Capture as the node leaves, restore as its replacement arrives. A layout
   effect, so the cleanup runs while the element is still attached and its
   selection and scroll are readable, and the restore lands before first paint.
   StrictMode runs the pair once more on mount: a capture of the unchanged node
   followed by a restore of the same values, which changes nothing. The element
   ref is merged with the focus lane's, so one node registers in both. */
export function useFieldMemory<T extends HTMLInputElement | HTMLTextAreaElement>(
  memoryKey: string | null,
  focusKey: string | null,
  fallback?: string,
) {
  const { fields, focusLane } = useControls();
  const element = useRef<T | null>(null);
  useLayoutEffect(() => {
    const field = element.current;
    if (!field || !memoryKey) return undefined;
    fields.restore(memoryKey, field);
    return () => fields.capture(memoryKey, field);
  }, [fields, memoryKey]);
  return useCallback(
    (node: T | null) => {
      element.current = node;
      if (!node || !focusKey) return undefined;
      return focusLane.register(focusKey, node, fallback === undefined ? {} : { fallback });
    },
    [focusLane, focusKey, fallback],
  );
}
