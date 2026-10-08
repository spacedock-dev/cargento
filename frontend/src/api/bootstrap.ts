import type { PayloadAsk, PayloadSession } from './types';

export const FOCUS_META_SELECTOR = 'meta[name="cargento-focus"]';

export interface Bootstrap {
  readonly showAll: boolean;
  /** Empty means the feature is off for this run: no focus request and no cue. */
  readonly focusCapability: string;
}

/* The capability arrives only in the served document, so it is read here and
   held by the caller for the process. It is never persisted and a 403 does not
   trigger a re-read: the page is the stale party, not the marker. */
function focusCapability(doc: Pick<Document, 'querySelector'> | null): string {
  if (!doc) return '';
  try {
    const value = doc.querySelector(FOCUS_META_SELECTOR)?.getAttribute('content');
    return typeof value === 'string' ? value.trim() : '';
  } catch {
    return '';
  }
}

export function readBootstrap(search: string, doc: Pick<Document, 'querySelector'> | null): Bootstrap {
  return { showAll: new URLSearchParams(search).get('all') === '1', focusCapability: focusCapability(doc) };
}

/* `usage=1` is the page's consent to the quota fetch riding along with a poll;
   the server fires no fetch without it, so it is sent only when consent is
   `granted`. The other query parameters of the page never reach the route. */
export function dataPath(options: { readonly showAll: boolean; readonly usage: boolean }): string {
  const params: string[] = [];
  if (options.showAll) params.push('all=1');
  if (options.usage) params.push('usage=1');
  return params.length ? `/api/data?${params.join('&')}` : '/api/data';
}

export function nextNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/* Coerces, and falls back to zero. Never use it to invent a measured counter. */
export function nextFiniteNumber(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

export interface RowCollection<Row> {
  /** False when the payload carried no such array, which is not an empty one. */
  readonly present: boolean;
  readonly rows: readonly Row[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function objectRows<Row>(payload: unknown, key: string): RowCollection<Row> {
  if (!isRecord(payload)) return { present: false, rows: [] };
  const rows = payload[key];
  if (!Array.isArray(rows)) return { present: false, rows: [] };
  return { present: true, rows: rows.filter(isRecord) as unknown as readonly Row[] };
}

export function payloadSessions(payload: unknown): RowCollection<PayloadSession> {
  return objectRows<PayloadSession>(payload, 'sessions');
}

export function payloadAsks(payload: unknown): RowCollection<PayloadAsk> {
  return objectRows<PayloadAsk>(payload, 'asks');
}
