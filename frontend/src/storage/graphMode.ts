import type { StorageAccess } from './backend';
import { STORAGE_KEYS } from './keys';

export const GRAPH_MODES = ['active', 'all', 'decisions'] as const;
export type GraphMode = (typeof GRAPH_MODES)[number];

const isMode = (value: unknown): value is GraphMode => GRAPH_MODES.includes(value as GraphMode);

/**
 * Project always, session when one is focused. The NUL joiner makes the key shape decidable, which
 * is how `decodeGraphModes` retires an old build's single empty-key entry instead of reading it as a project.
 */
export function graphModeScope(project: string, session?: string | null): string {
  return `${project}\u0000${session ?? ''}`;
}

export function decodeGraphModes(raw: string | null): Map<string, GraphMode> {
  const modes = new Map<string, GraphMode>();
  try {
    const stored: unknown = JSON.parse(raw || 'null');
    if (!stored || typeof stored !== 'object') return modes;
    for (const [key, value] of Object.entries(stored)) {
      if (!isMode(value)) continue;
      if (key.split('\u0000').length !== 2) continue;
      modes.set(key, value);
    }
  } catch {
    // Unreadable storage leaves the tab with its own choices.
  }
  return modes;
}

export interface GraphModeStore {
  /** A caller-pinned mode overrides the reader, then the stored choice, then `defaultMode`, then active. */
  resolve(options: { readonly scope: string; readonly mode?: GraphMode; readonly defaultMode?: GraphMode }): GraphMode;
  set(scope: string, mode: GraphMode): boolean;
}

export function createGraphModeStore(access: StorageAccess): GraphModeStore {
  // Loaded once, as the legacy page does at start, and the whole map is written back on each choice.
  let modes: Map<string, GraphMode> | null = null;
  const loaded = (): Map<string, GraphMode> => {
    if (!modes) {
      const read = access.attempt((backend) => backend.getItem(STORAGE_KEYS.graphMode));
      modes = decodeGraphModes(read.ok ? read.value : null);
    }
    return modes;
  };
  return {
    resolve({ scope, mode, defaultMode }) {
      if (isMode(mode)) return mode;
      const stored = loaded().get(scope);
      if (isMode(stored)) return stored;
      return isMode(defaultMode) ? defaultMode : 'active';
    },
    set(scope, mode) {
      if (!isMode(mode)) return false;
      const map = loaded();
      map.set(scope, mode);
      access.attempt((backend) => {
        backend.setItem(STORAGE_KEYS.graphMode, JSON.stringify(Object.fromEntries(map)));
      });
      return true;
    },
  };
}
