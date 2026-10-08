import type { ApiResult, InteractionOrigin } from '../api/types';

/* The registration read for one exact session: `GET /api/interaction/origin?harness=&sid=`. Ported from
   `projectTerminalLookup` and `projectTerminalAbsence` in the legacy `project.js`. What the server says is
   kept as it said it: an unknown reason is shown as a reason, never turned into a guess. */

export interface OriginCoordinates {
  readonly session_name?: string;
  readonly window_index?: string | number;
  readonly pane_index?: string | number;
}

export interface OriginData {
  readonly state?: string;
  readonly reason?: string;
  readonly origin?: OriginCoordinates;
  readonly origin_id_hint?: string;
}

export type OriginLookup =
  | { readonly state: 'loading'; readonly revision: number; readonly loading: true }
  | {
      readonly state: 'registered' | 'unavailable';
      readonly revision: number;
      /** A re-check of the next revision is in flight; the settled answer stays on screen meanwhile. */
      readonly loading: boolean;
      readonly data: OriginData;
    };

type Settled = Extract<OriginLookup, { state: 'registered' | 'unavailable' }>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function coordinate(value: unknown): string | number | undefined {
  return typeof value === 'string' || typeof value === 'number' ? value : undefined;
}

function dataOf(body: InteractionOrigin): OriginData {
  const raw: Record<string, unknown> = isRecord(body) ? body : {};
  const origin = isRecord(raw.origin) ? raw.origin : null;
  const window = coordinate(origin?.window_index);
  const pane = coordinate(origin?.pane_index);
  return {
    ...(typeof raw.state === 'string' ? { state: raw.state } : {}),
    ...(typeof raw.reason === 'string' ? { reason: raw.reason } : {}),
    ...(typeof raw.origin_id_hint === 'string' ? { origin_id_hint: raw.origin_id_hint } : {}),
    ...(origin
      ? {
          origin: {
            ...(typeof origin.session_name === 'string'
              ? { session_name: origin.session_name }
              : {}),
            ...(window !== undefined ? { window_index: window } : {}),
            ...(pane !== undefined ? { pane_index: pane } : {}),
          },
        }
      : {}),
  };
}

/* The answer to one read. A 404 is the bridge being off on this server, and the rest of the failures are
   a lookup that could not be made, because those two read differently to the person at the keyboard. An
   aborted read is the owner ending its own request and says nothing at all. */
export function settleLookup(
  result: ApiResult<InteractionOrigin>,
  revision: number,
): Settled | null {
  switch (result.kind) {
    case 'aborted':
      return null;
    case 'ok': {
      const data = dataOf(result.body);
      return {
        state: data.state === 'registered' ? 'registered' : 'unavailable',
        revision,
        loading: false,
        data,
      };
    }
    case 'http-error':
      return {
        state: 'unavailable',
        revision,
        loading: false,
        data: { reason: result.status === 404 ? 'bridge-disabled' : 'lookup-failed' },
      };
    default:
      return { state: 'unavailable', revision, loading: false, data: { reason: 'lookup-failed' } };
  }
}

/* The next lookup state, or null when no read should start: one is already in flight, or the settled answer
   already covers this revision. Both settled answers survive a re-check. Keeping `registered` alone and
   resetting `unavailable` to `loading` made a default bridge-off console flip from "bridge off" to "not read
   yet" on every poll, because the revision advances on every payload. */
export function beginLookup(
  current: OriginLookup | undefined,
  revision: number,
): OriginLookup | null {
  if (current && (current.loading || current.revision >= revision)) return null;
  if (current) return { ...current, revision, loading: true };
  return { state: 'loading', revision, loading: true };
}

const EXPLANATIONS: Readonly<Record<string, string>> = {
  'unregistered-origin': 'Terminal not registered for this session.',
  'bridge-disabled': 'The terminal bridge is disabled on this server.',
  'stale-registration': 'Terminal registration has expired.',
  'origin-disconnected': 'The registered tmux pane is disconnected.',
  'origin-mismatch': 'The registered tmux pane no longer matches its recorded identity.',
  'session-mismatch': 'The registered terminal belongs to another session.',
  'session-uncollected': 'This session is no longer in the server’s collected sessions.',
  'lookup-failed': 'Terminal registration could not be checked because the local request failed.',
};

/* Registering is a fix for these four and for no other reason: a disconnected pane or a lookup that failed
   is not cured by running the client again. */
const RECIPE_REASONS: readonly string[] = [
  'unregistered-origin',
  'bridge-disabled',
  'stale-registration',
  'session-mismatch',
];

export interface Absence {
  readonly checking: boolean;
  readonly message: string;
  /** The server's own word, only when this page has no sentence for it. */
  readonly serverReason: string | null;
  readonly recipe: boolean;
}

export function absenceOf(lookup: OriginLookup | undefined): Absence {
  if (!lookup || lookup.state === 'loading') {
    return {
      checking: true,
      message: 'Checking terminal registration for this exact session.',
      serverReason: null,
      recipe: false,
    };
  }
  const reason = lookup.data.reason ?? '';
  const known = EXPLANATIONS[reason];
  const message =
    known ??
    (reason
      ? 'The server refused terminal access.'
      : 'Terminal registration status was not published by the server.');
  return {
    checking: false,
    message,
    serverReason: reason && !known ? reason : null,
    recipe: RECIPE_REASONS.includes(reason),
  };
}

/* Four values, not two. The console's summary says "on" and "off" for a bridge it has read, "not read yet"
   for one it has not, and "per-session" with no session selected, because the bridge is a per-session
   registration: with nothing focused there is nothing whose bridge could be reported either way. `state`
   decides, never the `loading` flag beside it, which is true on every poll of a working console. */
export function bridgeReading(
  hasFocus: boolean,
  lookup: OriginLookup | undefined,
): boolean | null | 'per-session' {
  if (!hasFocus) return 'per-session';
  if (!lookup || lookup.state === 'loading') return null;
  return lookup.state === 'registered';
}

export interface OriginTitle {
  /** `session:window.pane`, only when all three are published. */
  readonly complete: string | null;
  readonly session: string | null;
  readonly window: string | null;
  readonly pane: string | null;
}

const published = (value: string | number | undefined): string | null =>
  value === undefined || value === null || value === '' ? null : String(value);

/* A zero is a coordinate: window 0 and pane 0 are real positions and must stay readable. */
export function originTitle(origin: OriginCoordinates | undefined): OriginTitle {
  const session = published(origin?.session_name);
  const window = published(origin?.window_index);
  const pane = published(origin?.pane_index);
  const complete =
    session && window !== null && pane !== null ? `${session}:${window}.${pane}` : null;
  return { complete, session, window, pane };
}
