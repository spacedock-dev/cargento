import type { StorageAccess } from './backend';
import { STORAGE_KEYS, sessionKey, type SessionIdentity } from './keys';

export function liveEstimateKey(session: SessionIdentity): string {
  return `${STORAGE_KEYS.liveEstimatePrefix}${sessionKey(session)}`;
}

export interface LiveEstimateStore {
  on(session: SessionIdentity): boolean;
  /** Off removes the key rather than writing a falsy value. Returns whether storage took it. */
  set(session: SessionIdentity, on: boolean): boolean;
}

export function createLiveEstimateStore(access: StorageAccess): LiveEstimateStore {
  const memory = new Map<string, boolean>();
  return {
    on(session) {
      const key = liveEstimateKey(session);
      const chosen = memory.get(key);
      if (chosen !== undefined) return chosen;
      const read = access.attempt((backend) => backend.getItem(key));
      return read.ok && read.value === '1';
    },
    set(session, on) {
      const key = liveEstimateKey(session);
      memory.set(key, on);
      return access.attempt((backend) => {
        if (on) backend.setItem(key, '1');
        else backend.removeItem(key);
      }).ok;
    },
  };
}

export interface WorkstreamStore {
  collapsed(): boolean;
  setCollapsed(collapsed: boolean): boolean;
}

export function createWorkstreamStore(access: StorageAccess): WorkstreamStore {
  // Read once, as the legacy module does at load; the toggle updates the tab before it tries to persist.
  let collapsed: boolean | null = null;
  return {
    collapsed() {
      if (collapsed === null) {
        const read = access.attempt((backend) => backend.getItem(STORAGE_KEYS.workstreamCollapsed));
        collapsed = read.ok && read.value === '1';
      }
      return collapsed;
    },
    setCollapsed(next) {
      collapsed = next;
      return access.attempt((backend) => {
        backend.setItem(STORAGE_KEYS.workstreamCollapsed, next ? '1' : '0');
      }).ok;
    },
  };
}

export interface CockpitProjectStore {
  /** A missing or empty label reads as null. */
  read(): string | null;
  write(label: string): boolean;
}

export function createCockpitProjectStore(access: StorageAccess): CockpitProjectStore {
  return {
    read() {
      const read = access.attempt((backend) => backend.getItem(STORAGE_KEYS.cockpitProject));
      return (read.ok && read.value) || null;
    },
    write: (label) =>
      access.attempt((backend) => {
        backend.setItem(STORAGE_KEYS.cockpitProject, String(label || ''));
      }).ok,
  };
}
