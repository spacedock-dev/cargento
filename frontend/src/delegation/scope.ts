import type { SessionIdentity } from '../api/types';

/* Whose words a panel is about: the project's, one session's, or not known. A session needs both halves of
   its identity, because a harness alone names no session and a sid alone names the wrong one under another
   harness. The detail is the harness's own label where the board published one. */
export type PanelScope =
  | { readonly kind: 'project'; readonly owner: 'project' }
  | { readonly kind: 'session'; readonly owner: string; readonly detail: string }
  | { readonly kind: 'unknown'; readonly owner: 'unknown' };

/* A published token as the page spells it: `-` and `_` read as spaces, the first letter raised. */
export function humanToken(value: unknown): string {
  const words = String(value || 'work')
    .replace(/[-_]+/g, ' ')
    .trim();
  return words ? (words[0] ?? '').toUpperCase() + words.slice(1) : 'Work';
}

export function consoleScope(
  focus: Partial<SessionIdentity> | null,
  labels: ReadonlyMap<string, string>,
): PanelScope {
  if (!focus) return { kind: 'project', owner: 'project' };
  const harness = String(focus.harness || '');
  const sid = String(focus.sid || '');
  if (!harness || !sid) return { kind: 'unknown', owner: 'unknown' };
  return {
    kind: 'session',
    owner: `${harness}:${sid}`,
    detail: labels.get(harness) || humanToken(harness),
  };
}
