// legacy-cargento: remove at 1.0.0
import { legacyStorageKey } from './keys';

/** The slice of `Storage` every family uses; a test double need implement nothing more. */
export interface StorageBackend {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** Called on every access: reading `localStorage` itself throws in a sandboxed frame or a blocked profile. */
export type BackendProvider = () => StorageBackend | null | undefined;

export type Attempt<T> = { readonly ok: true; readonly value: T } | { readonly ok: false };

export interface StorageAccess {
  attempt<T>(run: (backend: StorageBackend) => T): Attempt<T>;
}

export function browserBackend(): StorageBackend | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/**
 * A missing Storage object and a throwing one are the same outcome here: the caller falls back
 * to its in-tab memory, as every legacy family does, and learns that nothing was persisted.
 */
export function storageAccess(provider: BackendProvider): StorageAccess {
  return {
    attempt<T>(run: (backend: StorageBackend) => T): Attempt<T> {
      try {
        const backend = provider();
        if (!backend) return { ok: false };
        const reader: StorageBackend = {
          getItem: (key) => {
            const value = backend.getItem(key);
            if (value !== null) return value;
            // legacy-cargento: remove at 1.0.0
            if (key.startsWith('compass')) {
              const old = legacyStorageKey(key);
              if (old !== null) return backend.getItem(old);
            }
            return null;
          },
          setItem: (key, value) => backend.setItem(key, value),
          removeItem: (key) => {
            backend.removeItem(key);
            // legacy-cargento: remove at 1.0.0
            if (key.startsWith('compass')) {
              const old = legacyStorageKey(key);
              if (old !== null && backend.getItem(old) !== null) backend.setItem(key, '');
            }
          },
        };
        return { ok: true, value: run(reader) };
      } catch {
        return { ok: false };
      }
    },
  };
}
