import { isRecord, type Row } from '../observed';
import type { DriftCtx, Overlay } from './state';

/* What a reply told the page, laid over the board it answered against. The legacy page wrote a started job,
   the server's route and the policy into its current payload and let the next collection replace them. This
   page never mutates a board it was given: the same facts are held here, apply only while the board that was
   current when they were written is still the one on screen, and are gone once a newer board has drawn.

   Overlays are the reply's word for the interval before the board catches up; nothing here outlives that
   board, so a stale reply cannot stand against a fresher payload. */

export function overlaid(payload: Row, overlay: Overlay, displayedCount: number): Row {
  if (overlay.stamp < displayedCount) return payload;
  const jobs = Object.keys(overlay.jobs).length;
  const routes = Object.keys(overlay.routes).length;
  if (!jobs && !routes && !overlay.reading) return payload;
  const next: Record<string, unknown> = { ...payload };
  if (jobs) {
    next['reading_jobs'] = {
      ...(isRecord(payload['reading_jobs']) ? payload['reading_jobs'] : {}),
      ...overlay.jobs,
    };
  }
  if (routes) {
    next['reading_routes'] = {
      ...(isRecord(payload['reading_routes']) ? payload['reading_routes'] : {}),
      ...overlay.routes,
    };
  }
  if (overlay.reading) next['reading'] = overlay.reading;
  return next;
}

/* The accepted board with the overlay laid over it: the words a press acts on. */
export function currentPayload(ctx: DriftCtx): Row | null {
  const snapshot = ctx.shell.runtime.store.getSnapshot();
  if (!snapshot.data) return null;
  return overlaid(snapshot.data as unknown as Row, ctx.drift.getOverlay(), snapshot.acceptedCount);
}

/* The overlay as it stands for the accepted board: one written against an older board is empty. */
function current(ctx: DriftCtx): Overlay {
  const { overlay, count } = {
    overlay: ctx.drift.getOverlay(),
    count: ctx.shell.runtime.store.getSnapshot().acceptedCount,
  };
  return overlay.stamp === count ? overlay : { stamp: count, jobs: {}, routes: {}, reading: null };
}

/* The job a reply started or a cancel was accepted for, drawn now and replaced by the board. */
export function showJob(ctx: DriftCtx, key: string, job: Row): void {
  const base = current(ctx);
  ctx.drift.setOverlay({ ...base, jobs: { ...base.jobs, [key]: job } });
}

export function showRoute(ctx: DriftCtx, harness: string, route: Row): void {
  const base = current(ctx);
  ctx.drift.setOverlay({ ...base, routes: { ...base.routes, [harness]: route } });
}

export function showReading(ctx: DriftCtx, reading: Row): void {
  ctx.drift.setOverlay({ ...current(ctx), reading });
}
