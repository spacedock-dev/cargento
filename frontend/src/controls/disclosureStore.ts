export function disclosureKey(parts: {
  readonly project: string | null;
  /** The scope, or `harness:sid` on a session page. Empty where the disclosure has none. */
  readonly scope: string | null;
  readonly name: string;
}): string {
  return [parts.project ?? '', parts.scope ?? '', parts.name].join('\n');
}

export interface DisclosureSnapshot {
  readonly open: boolean;
  readonly version: number;
}

const CLOSED: DisclosureSnapshot = { open: false, version: 0 };

/* The precedence and lifetime belong to docs/design-reader-state.md#disclosure-write-precedence. */
export function createDisclosureStore() {
  const states = new Map<string, DisclosureSnapshot>();
  const listeners = new Set<() => void>();
  const writes = new Set<(key: string) => void>();
  const versions = new Map<string, number>();
  let version = 0;
  let size = 0;
  const read = (key: string): DisclosureSnapshot => states.get(key) ?? CLOSED;
  return {
    read,
    version: (key: string): number => versions.get(key) ?? 0,
    isOpen: (key: string): boolean => read(key).open,
    set(key: string, value: boolean): void {
      const changed = read(key).open !== value;
      version += 1;
      versions.set(key, version);
      if (changed) {
        size += value ? 1 : -1;
        states.set(key, { open: value, version });
      }
      for (const listener of [...writes]) listener(key);
      if (changed) for (const listener of [...listeners]) listener();
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    watchWrites(listener: (key: string) => void): () => void {
      writes.add(listener);
      return () => {
        writes.delete(listener);
      };
    },
    size: (): number => size,
  };
}

export type DisclosureStore = ReturnType<typeof createDisclosureStore>;
