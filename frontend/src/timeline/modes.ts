import { useCallback, useSyncExternalStore } from 'react';
import { useShell } from '../shell/context';
import { graphModeScope, type GraphMode, type GraphModeStore } from '../storage';

/* The timeline's activity filter as reader state: per project and, when a session is focused, per session,
   kept across a redraw, across navigating away and back, and across a reload.

   The persistence is the released `cargento.next.graph.mode` family in `../storage` (one JSON map, a NUL
   between project and session, no TTL, an old build's single empty key discarded on read). This file adds
   only what a component needs on top of it: a way to be told that a choice was made, because the storage
   codec is deliberately a plain store with nothing to subscribe to.

   Ported from `projectSetGraphMode`, `projectResolveGraphMode` and `projectGraphModeScope` in the legacy
   `project.js`. The scope is built in one place for the write and the read: a fix that namespaced the write
   and read a fallback from another scope passed half of "per project", and it is what let one project's
   choice appear on every other. */

export interface FilterScope {
  /** The route's project label. A project with no label is the empty string, a real project of its own. */
  readonly project: string;
  /** The focused session's compatibility key (`harness:sid`), or null at project scope. */
  readonly session: string | null;
}

export interface ResolveOptions extends FilterScope {
  /** A caller that pins the mode overrides the reader. The cockpit never does, because pinning also swaps the event source. */
  readonly mode?: GraphMode;
  /** What an untouched panel falls back to before the shared "active". The Decisions tab passes "decisions". */
  readonly defaultMode?: GraphMode;
}

export function createTimelineModes(store: GraphModeStore) {
  const listeners = new Set<() => void>();
  return {
    resolve(options: ResolveOptions): GraphMode {
      return store.resolve({
        scope: graphModeScope(options.project, options.session),
        ...(options.mode ? { mode: options.mode } : {}),
        ...(options.defaultMode ? { defaultMode: options.defaultMode } : {}),
      });
    },
    /* A mode outside the three is a no-op rather than a substitution. The legacy dispatcher collapsed
       everything that was not "all" to "active", so pressing Decisions selected Active and the only
       feedback was the wrong button lighting up. */
    set(scope: FilterScope, mode: GraphMode): boolean {
      if (!store.set(graphModeScope(scope.project, scope.session), mode)) return false;
      for (const listener of [...listeners]) listener();
      return true;
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export type TimelineModes = ReturnType<typeof createTimelineModes>;

/* One reactive layer per storage instance, so every reader in the document hears the same choice. */
const layers = new WeakMap<GraphModeStore, TimelineModes>();

export function modesOver(store: GraphModeStore): TimelineModes {
  let layer = layers.get(store);
  if (!layer) {
    layer = createTimelineModes(store);
    layers.set(store, layer);
  }
  return layer;
}

/* The mode and its setter for one scope. The mode is a string, so a subscriber that has not changed its
   answer is not redrawn, and an unrelated project's choice does not reach this one. */
export function useTimelineModeIn(modes: TimelineModes, options: ResolveOptions): readonly [GraphMode, (mode: GraphMode) => boolean] {
  const { project, session, mode: pinned, defaultMode } = options;
  const mode = useSyncExternalStore(modes.subscribe, () =>
    modes.resolve({ project, session, ...(pinned ? { mode: pinned } : {}), ...(defaultMode ? { defaultMode } : {}) }),
  );
  const set = useCallback((next: GraphMode) => modes.set({ project, session }, next), [modes, project, session]);
  return [mode, set];
}

export function useTimelineMode(options: ResolveOptions): readonly [GraphMode, (mode: GraphMode) => boolean] {
  return useTimelineModeIn(modesOver(useShell().runtime.storage.graphMode), options);
}
