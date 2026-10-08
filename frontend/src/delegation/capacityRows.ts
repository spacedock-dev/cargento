import { nextNumber } from '../api/bootstrap';
import { isRecord, type Row } from '../observed';

/* The quota windows the Console's CAPACITY panel draws, one row per published window, ranked by when the
   budget ends. This is the subset of `nextCapacityRows` the panel prints (the level, how much of the window
   has elapsed, the pace against it, and the order); the strip, the model sub-limits, the pacing prose and
   the consent belong to the capacity step, which owns the whole of `next-capacity.js`. The differential test
   holds this to the legacy function, so the two cannot rank differently. */
export const SLOTS = ['fiveH', 'week', 'month'] as const;
export type Slot = (typeof SLOTS)[number];

export const SLOT_LABELS: Readonly<Record<Slot, string>> = {
  fiveH: '5-hour',
  week: 'weekly',
  month: 'billing cycle',
};

export interface CapacityRailRow {
  readonly harness: string;
  readonly slot: Slot;
  readonly pct: number;
  /** null unless the window published both a length and a reset still ahead of the payload's clock. */
  readonly elapsed: number | null;
  /** null unless `elapsed` is known and non-zero. */
  readonly paceRatio: number | null;
  readonly windowMinutesLeft: number | null;
}

function windowRow(entry: unknown, slot: Slot, generated: number): CapacityRailRow | null {
  if (!isRecord(entry) || entry['state'] !== 'ok') return null;
  const window = entry[slot];
  if (!isRecord(window)) return null;
  const pct = window['pct'];
  if (typeof pct !== 'number' || !Number.isInteger(pct)) return null;
  const windowSec = nextNumber(window['windowSec']);
  const resetAt = nextNumber(window['resetAt']);
  const remainingSec = resetAt === null ? null : resetAt - generated;
  /* A reset already in the past leaves the window UNTIMED, and that guard is the whole of what stops this
     surface publishing a false all-clear: a stale disk snapshot describes a window that has since rolled,
     and clamping `elapsed` to 1 there made the pace look tiny and the projected end enormous. The inner
     clamp still serves its other purpose: a vendor clock running ahead of ours puts `remainingSec` above
     `windowSec`. */
  let elapsed: number | null = null;
  if (windowSec !== null && windowSec > 0 && remainingSec !== null && remainingSec > 0) {
    elapsed = Math.max(0, Math.min(1, (windowSec - remainingSec) / windowSec));
  }
  const windowPacePerMin =
    elapsed !== null && elapsed > 0 && windowSec !== null && windowSec > 0
      ? pct / ((elapsed * windowSec) / 60)
      : null;
  const left = Math.max(0, 100 - pct);
  return {
    harness: String(entry['harness'] || ''),
    slot,
    pct,
    elapsed,
    paceRatio: elapsed !== null && elapsed > 0 ? pct / (elapsed * 100) : null,
    windowMinutesLeft:
      windowPacePerMin === null || windowPacePerMin <= 0 ? null : left / windowPacePerMin,
  };
}

/* Ranked by when the budget ends, earliest first, because that is the binding constraint and it is not the
   largest percentage: a window at 34% used with 12% elapsed runs dry before one at 88% used with 91%
   elapsed. Windows that cannot be timed sort last, by level. */
export function capacityRows(payload: unknown): CapacityRailRow[] {
  const source = isRecord(payload) ? payload : ({} as Row);
  const usage = Array.isArray(source['usage']) ? source['usage'] : [];
  const generated = nextNumber(source['generated']);
  if (generated === null) return [];
  const rows: CapacityRailRow[] = [];
  for (const entry of usage) {
    for (const slot of SLOTS) {
      const row = windowRow(entry, slot, generated);
      if (row) rows.push(row);
    }
  }
  rows.sort((left, right) => {
    const leftEnd = left.windowMinutesLeft;
    const rightEnd = right.windowMinutesLeft;
    if (leftEnd !== null && rightEnd !== null && leftEnd !== rightEnd) return leftEnd - rightEnd;
    if (leftEnd !== null && rightEnd === null) return -1;
    if (leftEnd === null && rightEnd !== null) return 1;
    if (left.pct !== right.pct) return right.pct - left.pct;
    return left.harness.localeCompare(right.harness) || left.slot.localeCompare(right.slot);
  });
  return rows;
}
