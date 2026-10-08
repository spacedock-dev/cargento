import type { StorageAccess } from './backend';
import { STORAGE_KEYS } from './keys';

export const USAGE_LOAD_LIMIT = 200;
export const USAGE_COUNT_MAX = 999999;

export type UsageCounts = Readonly<Record<string, number>>;

/**
 * The first two hundred entries by `Object.entries` order, counted before empty keys are dropped.
 * Plain-object assignment is deliberate: the legacy loader's `__proto__` entry is ignored the same way.
 */
export function decodeUsage(raw: string | null): Record<string, number> {
  const counts: Record<string, number> = {};
  try {
    const parsed: unknown = JSON.parse(raw || '{}');
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      for (const [key, value] of Object.entries(parsed).slice(0, USAGE_LOAD_LIMIT)) {
        const count = Math.floor(Number(value));
        if (key && count > 0) counts[key] = Math.min(count, USAGE_COUNT_MAX);
      }
    }
  } catch {
    // Ordering falls back to live state and name.
  }
  return counts;
}

export interface UsageStore {
  counts(): UsageCounts;
  /** Increments one label and writes the whole object; writes never bound the key count. */
  record(key: string): UsageCounts;
}

export function createUsageStore(access: StorageAccess): UsageStore {
  let counts: Record<string, number> | null = null;
  const loaded = (): Record<string, number> => {
    if (!counts) {
      const read = access.attempt((backend) => backend.getItem(STORAGE_KEYS.usage));
      counts = decodeUsage(read.ok ? read.value : null);
    }
    return counts;
  };
  return {
    counts: () => ({ ...loaded() }),
    record(key) {
      const usage = loaded();
      usage[key] = Math.min(USAGE_COUNT_MAX, (Number(usage[key]) || 0) + 1);
      access.attempt((backend) => {
        backend.setItem(STORAGE_KEYS.usage, JSON.stringify(usage));
      });
      return { ...usage };
    },
  };
}
