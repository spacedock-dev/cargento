import { nextNumber } from '../api/bootstrap';
import { pair, type Pair } from '../observed';
import {
  TAB_WINDOW,
  sessionKey as sessionKeyOf,
  windowLabel,
  transition,
  type Batch,
  type ProjectWindow,
  type WorkstreamEvent as StateEvent,
  type WorkstreamSample as Sample,
} from '../workstream/model';

/* Delegation is elapsed observed project time with at least one working session and no session in
   `needs_input`, divided by working-or-gated time. All-idle intervals count toward neither side, though they
   still prove that the window was observed. Each snapshot holds until the next one arrives, so the
   arithmetic follows wall time rather than poll count. A gate left open over lunch therefore counts lunch as
   human time and deliberately biases the delegation percentage DOWN: subtracting that gap would invent a
   period in which the project could proceed unaided. Transitions coalesced between polls remain unknowable
   in either direction.

   Ported from `next-delegation.js` and the delegation half of `nextObservedHistory`; the differential test
   holds every function here to the legacy page. */

export const MIN_WINDOW_SEC = 600;

/* The ceiling on a window this tab observed for itself, so the figure keeps meaning "recently". It is
   deliberately not applied to a window seeded from the store: retention there is the reader's own setting,
   and clamping a fourteen-day store to six hours would report six hours and call it the window the caption
   beside it names. */
export const MAX_WINDOW_SEC = 6 * 60 * 60;

export interface Range {
  readonly delegatedPct: number | null;
  readonly delegatedSec: number;
  readonly endedAt: number;
  readonly humanTurns: number;
  readonly observedSec: number;
  readonly rateFloor: boolean;
  readonly ratePerMin: number | null;
  readonly startedAt: number;
  readonly totalSec: number;
}

type Windowed = Pick<ProjectWindow, 'batches' | 'events'> &
  Partial<Pick<ProjectWindow, 'endedAt' | 'seeded' | 'startedAt'>>;

function humanTurns(
  events: readonly StateEvent[] | undefined,
  startedAt: number,
  endedAt: number,
): number {
  const ordered: { readonly at: number; readonly event: StateEvent }[] = [];
  for (const event of events ?? []) {
    const at = nextNumber(event?.at);
    if (at === null || at > endedAt || event.kind !== 'state') continue;
    ordered.push({ at, event });
  }
  // A stable sort, as the legacy one is, so equal stamps keep the order they were published in.
  ordered.sort((left, right) => left.at - right.at);

  let count = 0;
  const pendingIdleResumptions = new Set<string>();
  for (const entry of ordered) {
    const event = entry.event;
    const key = sessionKeyOf(event);
    const idleResumption = event.fromState === 'idle' && event.toState === 'working';
    const suppress = pendingIdleResumptions.has(key) && idleResumption;
    pendingIdleResumptions.delete(key);

    // One answer can surface as gate exit, then idle resumption, without a response ID.
    if (event.fromState === 'needs_input' && event.toState === 'idle') {
      pendingIdleResumptions.add(key);
    }
    if (entry.at < startedAt || suppress) continue;
    if (transition(event.fromState, event.toState).humanTurn) count += 1;
  }
  return count;
}

function batchesOf(window: Windowed | null | undefined): { at: number; rows: readonly Sample[] }[] {
  const batches: Batch[] = [];
  for (const batch of Array.isArray(window?.batches) ? window.batches : []) {
    const at = nextNumber(batch?.at);
    if (at === null) continue;
    batches.push({ at, rows: Array.isArray(batch?.rows) ? batch.rows : [] });
  }
  return batches;
}

export function rangeOf(window: Windowed, startedAt: number, endedAt: number): Range {
  const batches = batchesOf(window);
  let coveredSince: number | null = null;
  let delegatedSec = 0;
  let observedSec = 0;
  let rateArea = 0;
  let rateFloor = false;
  let rateMeasured = false;
  let rateSec = 0;
  let totalSec = 0;
  for (let index = 0; index + 1 < batches.length; index += 1) {
    const batch = batches[index];
    const next = batches[index + 1];
    if (!batch || !next) continue;
    const left = Math.max(startedAt, batch.at);
    const right = Math.min(endedAt, next.at);
    if (right <= left || batch.rows.length === 0) continue;
    if (coveredSince === null) coveredSince = left;
    const duration = right - left;
    observedSec += duration;
    const gated = batch.rows.some((sample) => sample.state === 'needs_input');
    const working = batch.rows.some((sample) => sample.state === 'working');
    if (!gated && !working) continue;
    totalSec += duration;
    if (gated) continue;
    delegatedSec += duration;
    let aggregateRate = 0;
    let batchMeasured = false;
    let batchUnknown = false;
    for (const sample of batch.rows) {
      const rate = nextNumber(sample.rate);
      if (sample.rateKnown === true && rate !== null) {
        aggregateRate += Math.max(0, rate);
        batchMeasured = true;
      } else {
        batchUnknown = true;
      }
    }
    rateArea += aggregateRate * duration;
    // Divided by the span that was measured, not by every delegated second. A seeded window carries no
    // token rate at all, so dividing by `delegatedSec` would spread one measured hour's area across
    // fourteen days and print a floor two orders of magnitude under the rate it was derived from.
    if (batchMeasured) rateSec += duration;
    rateMeasured = rateMeasured || batchMeasured;
    rateFloor = rateFloor || batchUnknown;
  }
  const actualStart = coveredSince === null ? startedAt : coveredSince;
  return {
    delegatedPct: totalSec > 0 ? (delegatedSec * 100) / totalSec : null,
    delegatedSec,
    endedAt,
    humanTurns: humanTurns(window.events, actualStart, endedAt),
    observedSec,
    rateFloor,
    ratePerMin: rateSec > 0 && rateMeasured ? rateArea / rateSec : null,
    startedAt: actualStart,
    totalSec,
  };
}

export function metricOf(window: Windowed | null | undefined): Range {
  const endedAt = nextNumber(window?.endedAt);
  const retainedSince = nextNumber(window?.startedAt);
  if (endedAt === null || retainedSince === null || endedAt <= retainedSince) {
    return rangeOf(window ?? { batches: [], events: [] }, endedAt ?? 0, endedAt ?? 0);
  }
  const startedAt = window?.seeded
    ? retainedSince
    : Math.max(retainedSince, endedAt - MAX_WINDOW_SEC);
  return rangeOf(window as Windowed, startedAt, endedAt);
}

export function trendOf(window: Windowed | null | undefined): number | null {
  const endedAt = nextNumber(window?.endedAt);
  const retainedSince = nextNumber(window?.startedAt);
  const history = MAX_WINDOW_SEC * 2;
  if (endedAt === null || retainedSince === null || endedAt - retainedSince < history) return null;
  const current = rangeOf(window as Windowed, endedAt - MAX_WINDOW_SEC, endedAt);
  const previous = rangeOf(window as Windowed, endedAt - history, endedAt - MAX_WINDOW_SEC);
  if (
    current.observedSec < MAX_WINDOW_SEC ||
    previous.observedSec < MAX_WINDOW_SEC ||
    current.delegatedPct === null ||
    previous.delegatedPct === null
  )
    return null;
  return Math.round(current.delegatedPct - previous.delegatedPct);
}

export type DelegationFigure = {
  readonly pctText: string;
  readonly pctKnown: boolean;
  readonly pct: number | null;
  readonly trendDelta: number | null;
  readonly tpsText: string;
  readonly tpsKnown: boolean;
  readonly humanText: string;
  readonly humanKnown: true;
  readonly windowText: string;
  readonly windowKnown: true;
  readonly noteText: string;
  readonly noteKnown: boolean;
} & Pair<'trend'>;

/* What the rail prints. No floor on the percentage, deliberately: a ratio is not bounded below by partial
   data, because an interval nobody measured could have been delegated or human, so it moves the figure
   either way. The token rate does carry `≥`, because more readings can only add tokens. */
export function delegationFigure(window: ProjectWindow): DelegationFigure {
  const metric = metricOf(window);
  const known = metric.observedSec >= MIN_WINDOW_SEC && metric.delegatedPct !== null;
  const pct = known && metric.delegatedPct !== null ? Math.round(metric.delegatedPct) : null;
  const trend = trendOf(window);
  const label = !known && !window.seeded ? TAB_WINDOW : windowLabel(known ? metric : window);
  return {
    pctText: known ? `${String(pct)}%` : 'no figure yet',
    pctKnown: known,
    pct,
    ...pair(
      'trend',
      trend === null ? '' : `${trend > 0 ? '+' : ''}${String(trend)}`,
      'Two complete six-hour delegation readings are not available',
    ),
    trendDelta: trend,
    tpsText:
      metric.ratePerMin === null
        ? 'no token-rate figure'
        : `${metric.rateFloor ? '≥' : ''}${String(Math.round(metric.ratePerMin).toLocaleString('en-US'))} tok/m while delegated`,
    tpsKnown: metric.ratePerMin !== null,
    humanText: `${String(metric.humanTurns)} human ${metric.humanTurns === 1 ? 'turn' : 'turns'}`,
    humanKnown: true,
    windowText: label,
    windowKnown: true,
    noteText: known
      ? `Measured over observed working and needs-input intervals.${
          metric.rateFloor && metric.ratePerMin !== null
            ? ' ≥ because some sessions or intervals have no token-rate reading.'
            : ''
        }`
      : 'Waiting on one complete token-rate window.',
    noteKnown: known,
  };
}
