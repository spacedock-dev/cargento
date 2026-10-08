import { payloadAsks, payloadSessions } from '../api/bootstrap';
import type { PayloadAsk, PayloadData, PayloadSession } from '../api/types';
import type { BoardSnapshot } from '../store/board';

/* The few figures the page's chrome reads, derived from the rows the views render. They are the
   chrome's slice of `nextObserved` in `next-observed.js`, not its port: the whole observed model
   (projects, risks, capacity, delegation) belongs to the views that draw it. Each rule here is the
   legacy rule, and the header-count test pins them against the legacy cases. */

export const TITLE_NOT_PUBLISHED = 'Title not published';

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

/* When a session id was observed to end, or null. Absence covers a SIGKILL, a harness with no event
   adapter and a session that predates this server run, so a row without a stamp is not known to be
   running and is never counted as though it were. */
function hasEnded(row: PayloadSession): boolean {
  const at = row.ended_at;
  return typeof at === 'number' && Number.isFinite(at) && at > 0;
}

/* The pair, not the sid alone: two harnesses can hold the same sid. */
function pairKey(harness: unknown, sid: unknown): string {
  return JSON.stringify([String(harness ?? ''), String(sid ?? '')]);
}

/* The one session an ask belongs to: its sid, and its harness when it names one, matching exactly
   one row. An ask that matches none or several is attributed to no session. */
function askOwner(sessions: readonly PayloadSession[], ask: PayloadAsk): PayloadSession | null {
  const sid = String(ask.session_id ?? '');
  if (!sid) return null;
  const harness = String(ask.harness ?? '');
  const matches = sessions.filter((row) => String(row.sid ?? '') === sid && (!harness || String(row.harness ?? '') === harness));
  return matches.length === 1 ? (matches[0] ?? null) : null;
}

export type HeaderCounts =
  /** No board has been accepted yet: nothing is known, and nothing may be claimed. */
  | { readonly state: 'unread' }
  /** A board arrived and carried no session collection, which is not the same as an empty one. */
  | { readonly state: 'absent' }
  | { readonly state: 'measured'; readonly gates: number; readonly running: number; readonly subagents: number };

const countsByBody = new WeakMap<object, HeaderCounts>();
/* One object, because a selector over an unread board is called on every render and must return what it
   returned last time or `useSyncExternalStore` sees a change that never ends. */
const UNREAD: HeaderCounts = Object.freeze({ state: 'unread' });

export function deriveHeaderCounts(data: PayloadData | null): HeaderCounts {
  if (!data) return UNREAD;
  const cached = countsByBody.get(data);
  if (cached) return cached;
  const collection = payloadSessions(data);
  let counts: HeaderCounts;
  if (!collection.present) {
    counts = { state: 'absent' };
  } else {
    const sessions = collection.rows;
    const asked = new Set<string>();
    for (const ask of data.ask === true ? payloadAsks(data).rows : []) {
      if (!text(ask.question)) continue;
      const owner = askOwner(sessions, ask);
      if (owner) asked.add(pairKey(owner.harness, owner.sid));
    }
    let gates = 0;
    let running = 0;
    let subagents = 0;
    for (const row of sessions) {
      const ended = hasEnded(row);
      if ((!ended && row.state === 'needs_input') || asked.has(pairKey(row.harness, row.sid))) gates += 1;
      if (!ended && row.state === 'working' && row.active === true) running += 1;
      const children = record(row)['subagents'];
      if (Array.isArray(children)) subagents += children.length;
    }
    counts = { state: 'measured', gates, running, subagents };
  }
  countsByBody.set(data, counts);
  return counts;
}

export function selectHeaderCounts(snapshot: BoardSnapshot): HeaderCounts {
  return deriveHeaderCounts(snapshot.data);
}

/* A session as a route names it: project exactly (an empty one included), sid, and the harness
   when the route carries one. More than one match is no match, so the released id-only form can
   never silently open an ambiguous wrong owner. */
export function findSession(
  data: PayloadData | null,
  project: string | null | undefined,
  harness: string | null | undefined,
  sid: string | null | undefined,
): PayloadSession | null {
  if (!data) return null;
  const projectKey = String(project ?? '');
  const harnessKey = String(harness ?? '');
  const sidKey = String(sid ?? '');
  const matches = payloadSessions(data).rows.filter(
    (row) =>
      String(row.project ?? '') === projectKey &&
      String(row.sid ?? '') === sidKey &&
      (!harnessKey || String(row.harness ?? '') === harnessKey),
  );
  return matches.length === 1 ? (matches[0] ?? null) : null;
}

/* The published title, or a sentence saying there is none. Never an invented one. */
export function sessionTitle(session: PayloadSession | null): string {
  return text(session?.title) || TITLE_NOT_PUBLISHED;
}

/* The two reasons the history store publishes, and nothing else: the field arrives from a file any
   local process could have replaced, so an unrecognised literal draws nothing rather than letting a
   tampered store write header copy. A closed list rather than a property lookup, so `toString` is no reason. */
const RESET_REASONS = ['unreadable', 'version'] as const;
export type HistoryResetReason = (typeof RESET_REASONS)[number];

export function historyResetReason(data: PayloadData | null): HistoryResetReason | null {
  const value = record(data)['history_reset'];
  return (RESET_REASONS as readonly unknown[]).includes(value) ? (value as HistoryResetReason) : null;
}

/* The span the board holds, in hours, or null when it did not say. */
export function windowHours(data: PayloadData | null): number | null {
  const value = record(data)['window_hours'];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
