import { useLayoutEffect, useMemo, useSyncExternalStore } from 'react';
import type { DisclosureSnapshot, DisclosureStore } from './disclosureStore';

/* Native toggle is queued, while store writes can commit immediately. Keep the version of
   the native attribute change, not the version at event delivery. See
   docs/design-reader-state.md#disclosure-write-precedence. */
export function createDisclosureBinding(store: DisclosureStore, key: string) {
  let rendered = store.read(key);
  let observedVersion = store.version(key);
  let node: HTMLDetailsElement | null = null;
  let observer: MutationObserver | null = null;
  let native: DisclosureSnapshot | null = null;
  const capture = (records: MutationRecord[]) => {
    if (records.length && node && node.open !== rendered.open)
      native = { open: node.open, version: observedVersion };
  };
  const drain = () => capture(observer?.takeRecords() ?? []);
  return {
    read: () => store.read(key),
    subscribe(listener: () => void) {
      const unwatch = store.watchWrites((writtenKey) => {
        if (writtenKey !== key) return;
        drain();
        observedVersion = store.version(key);
        const snapshot = store.read(key);
        // React does not rewrite an unchanged prop after a native browser opening.
        if (node && snapshot.open === rendered.open && node.open !== snapshot.open) {
          node.open = snapshot.open;
          observer?.takeRecords();
        }
      });
      const unsubscribe = store.subscribe(listener);
      return () => {
        unwatch();
        unsubscribe();
      };
    },
    attach(element: HTMLDetailsElement) {
      node = element;
      observer = new MutationObserver(capture);
      observer.observe(element, { attributes: true, attributeFilter: ['open'] });
      return () => {
        observer?.disconnect();
        observer = null;
        node = null;
        native = null;
      };
    },
    commit(snapshot: DisclosureSnapshot) {
      if (snapshot.version === rendered.version) drain();
      else observer?.takeRecords();
      rendered = snapshot;
    },
    toggle(event: Event) {
      drain();
      const latest = store.read(key);
      const reported = 'newState' in event ? event.newState === 'open' : node?.open;
      const pending = native;
      native = null;
      if (reported === latest.open) return;
      if (!pending || pending.open !== reported || pending.version !== store.version(key)) return;
      store.set(key, pending.open);
    },
  };
}

export function useDisclosureState(store: DisclosureStore, key: string) {
  const binding = useMemo(() => createDisclosureBinding(store, key), [store, key]);
  const snapshot = useSyncExternalStore(binding.subscribe, binding.read);
  useLayoutEffect(() => binding.commit(snapshot), [binding, snapshot]);
  return { open: snapshot.open, binding };
}
