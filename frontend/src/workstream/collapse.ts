import { useSyncExternalStore } from 'react';
import type { WorkstreamStore } from '../storage';

/* The workstream panel's collapse: one reader-owned flag, shared by every project, that survives a reload
   (`cargento.next.workstream.collapsed`, raw `1` or `0`) and falls back to the tab when storage refuses. The
   storage family owns the key, its read-once rule and the memory-before-storage order; this only lets a
   view subscribe to it. The legacy unnamespaced storage is not adopted: this key, exactly. */
const holders = new WeakMap<object, ReturnType<typeof create>>();

function create(store: WorkstreamStore) {
  const listeners = new Set<() => void>();
  return {
    get: (): boolean => store.collapsed(),
    toggle(): void {
      store.setCollapsed(!store.collapsed());
      for (const listener of [...listeners]) listener();
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export function collapseFor(store: WorkstreamStore) {
  let held = holders.get(store);
  if (!held) {
    held = create(store);
    holders.set(store, held);
  }
  return held;
}

export function useCollapsed(store: WorkstreamStore): { collapsed: boolean; toggle: () => void } {
  const held = collapseFor(store);
  const collapsed = useSyncExternalStore(held.subscribe, held.get);
  return { collapsed, toggle: held.toggle };
}
