import type { DriftCtx } from './state';

/* A press asks for focus on a control once the card has drawn it. The ask is the press's, so it belongs to
   the page the press was made on: an answer that arrives while the reader is on another view asks for nothing,
   and an ask still waiting when the card goes is dropped with it (`DriftProvider`). Otherwise the next panel
   mounted would take it, and the reader returning to this page would find focus moved into a box they did not
   touch. */
export function requestFocus(ctx: DriftCtx, name: string): void {
  if (ctx.drift.mountedCount() > 0) ctx.intent.held.requestFocus(name);
}
