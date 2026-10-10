import { useEffect, useRef } from 'react';

const reapplied = new WeakMap<Document, Set<string>>();

/* Client rendering follows the browser's initial fragment pass. Re-run navigation only
   once this panel's target exists; beforematch still owns revealing the controlled panel.
   docs/design-shadcn-adoption.md#accordion-and-collapsible-layer */
export function useRevealFragment(identity: string) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const hash = window.location.hash;
      let id: string;
      try {
        id = decodeURIComponent(hash.slice(1));
      } catch {
        return;
      }
      const target = document.getElementById(id);
      if (!target || !ref.current?.contains(target)) return;
      const hashes = reapplied.get(document) ?? new Set<string>();
      const mark = JSON.stringify([identity, hash]);
      if (hashes.has(mark)) return;
      hashes.add(mark);
      reapplied.set(document, hashes);
      // An identical hash assignment is ignored after load. Replace the current
      // entry twice so navigation runs without adding a Back-button stop.
      history.replaceState(history.state, '', window.location.pathname + window.location.search);
      window.location.replace(hash);
    });
    return () => cancelAnimationFrame(frame);
  }, [identity]);
  return ref;
}
