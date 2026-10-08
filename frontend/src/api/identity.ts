import type { SessionIdentity } from './types';

interface IdentityFields {
  readonly harness?: unknown;
  readonly sid?: unknown;
  readonly session?: unknown;
}

/* The page's `sessKey`: the display id stands in only when a row has no sid.
   This is the key of the legacy-written families that name a session (memo,
   live-estimate) and of context cache keys, where the fallback is part of the
   released format. It is a map key, so it must never reach a request: use
   `exactIdentity` for that. */
export function compatSessKey(row: IdentityFields | null | undefined): string {
  return `${String(row?.harness || '')}:${String(row?.sid || row?.session || '')}`;
}

/* The pair an action may name. A display id or a half-empty pair is null,
   because a request built from one would address the wrong session or none. */
export function exactIdentity(row: IdentityFields | null | undefined): SessionIdentity | null {
  const harness = row?.harness;
  const sid = row?.sid;
  if (typeof harness !== 'string' || typeof sid !== 'string') return null;
  if (!harness.trim() || !sid.trim()) return null;
  return { harness, sid };
}

/* First colon only: a sid may itself contain colons. */
export function splitSessKey(key: string): SessionIdentity | null {
  const at = key.indexOf(':');
  if (at <= 0) return null;
  const sid = key.slice(at + 1);
  return sid ? { harness: key.slice(0, at), sid } : null;
}

export function stableProjectKey(group: {
  readonly label: string;
  readonly sessions: readonly { readonly project_key?: unknown }[];
}): string {
  const keys = new Set(
    group.sessions.map((session) => String(session.project_key || '')).filter(Boolean),
  );
  const [only] = keys;
  return keys.size === 1 && only !== undefined ? only : group.label;
}

export function contextKey(projectKey: string, focus: SessionIdentity | null): string {
  return `${projectKey}\n${focus ? compatSessKey(focus) : ''}`;
}
