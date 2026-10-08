import type { StorageAccess } from './backend';
import { STORAGE_KEYS } from './keys';

export const LEASE_RENEW_MS = 2000;
export const LEASE_STALE_MS = 6000;

/**
 * A foreign or old record need not have the written shape. Anything truthy still counts as a
 * foreign owner, so its fields stay `unknown` and the validity check coerces like the legacy page.
 */
export interface Lease {
  readonly id: unknown;
  readonly ts: unknown;
}

export type ElectionDecision = 'lead' | 'yield';

export function createTabId(random: () => number = Math.random, now: number = Date.now()): string {
  return `${random().toString(36).slice(2)}-${now}`;
}

export function parseLease(raw: string | null): Lease | null {
  try {
    const parsed: unknown = JSON.parse(raw as string);
    if (!parsed) return null;
    const record = typeof parsed === 'object' ? (parsed as { id?: unknown; ts?: unknown }) : {};
    return { id: record.id, ts: record.ts };
  } catch {
    return null;
  }
}

export function leaseIsLive(lease: Lease | null, now: number): boolean {
  return !!lease && now - Number(lease.ts) < LEASE_STALE_MS;
}

/**
 * A throttled leader can wake after a foreign claim has gone stale and must still yield, or two
 * hidden tabs keep streams while overwriting the lease.
 */
export function electionDecision(input: {
  readonly lease: Lease | null;
  readonly tabId: string;
  readonly isLeader: boolean;
  readonly now: number;
}): ElectionDecision {
  const { lease, tabId, isLeader, now } = input;
  if (lease && lease.id !== tabId && (leaseIsLive(lease, now) || isLeader)) return 'yield';
  return 'lead';
}

export interface LeaseStore {
  read(): Lease | null;
  write(tabId: string, now: number): boolean;
  release(): boolean;
}

/** Unreadable storage reads as no lease and refuses writes, so each tab leads itself. */
export function createLeaseStore(access: StorageAccess): LeaseStore {
  return {
    read() {
      const read = access.attempt((backend) => backend.getItem(STORAGE_KEYS.leader));
      return read.ok ? parseLease(read.value) : null;
    },
    write: (tabId, now) =>
      access.attempt((backend) => {
        backend.setItem(STORAGE_KEYS.leader, JSON.stringify({ id: tabId, ts: now }));
      }).ok,
    release: () =>
      access.attempt((backend) => {
        backend.removeItem(STORAGE_KEYS.leader);
      }).ok,
  };
}
