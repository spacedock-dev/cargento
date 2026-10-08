import { nextNumber } from '../api/bootstrap';
import { observe } from '../observed';
import { harnessLabels } from '../sessions/rows';
import { groupFor, stableKey } from './group';
import { loadLegacyApp, type LegacyApp } from './legacy.test.helper';
import type { ContextEntryLike, RecoveryEnv } from './recovery';

/* One project of one board, set up on both pages: the legacy page with the board and the project-context
   read seeded as its loader would have stored them, and this port's group and environment from the same
   inputs. Shared by the differential tests so a case means the same thing in each. */

export type Variant = 'ready' | 'stale' | 'failed' | 'absent';

export function entryFor(
  variant: Variant,
  data: Record<string, unknown> | null,
): ContextEntryLike | undefined {
  if (variant === 'absent') return undefined;
  if (variant === 'failed') return { data: null, error: true, revision: 1 };
  if (!data) return { data: null, revision: 1 };
  return variant === 'stale' ? { data, error: true, revision: 1 } : { data, revision: 1 };
}

export const GROUP_SOURCE = `(() => {
  const model = nextCurrentObserved();
  const observed = model.projects.find(candidate => candidate.key === __label);
  if(!observed) return null;
  const sources = new Map(nextPayloadSessions(nextData).map(session => [nextSessionKey(session), session]));
  return {label: observed.key, sessions: observed.sessions.map(session =>
    sources.get(nextSessionKey(session))).filter(Boolean)};
})()`;

export interface Case {
  readonly app: LegacyApp;
  readonly board: Record<string, unknown>;
  readonly label: string;
  readonly variant: Variant;
  readonly legacyGroup: unknown;
  readonly env: RecoveryEnv;
  readonly entry: ContextEntryLike | undefined;
}

/* Both pages for one project of one board, in one context state. The legacy bridge the delegation lanes
   read their snapshot from is seeded with the same read, which the legacy page only has after the
   Decisions tab has drawn. */
export function arrange(
  board: Record<string, unknown>,
  context: Record<string, unknown> | null,
  label: string,
  variant: Variant,
): Case | null {
  const app = loadLegacyApp();
  app.setData(board);
  const legacyGroup = app.run<{ label: string; sessions: unknown[] } | null>(GROUP_SOURCE, {
    label,
  });
  if (!legacyGroup) return null;
  const group = groupFor(board, observe(board), label);
  if (!group)
    throw new Error(`the port has no project ${JSON.stringify(label)} the legacy page has`);
  const entry = entryFor(variant, context);
  const key = `${stableKey(group)}\n`;
  if (entry) {
    app.setContext(key, {
      data: entry.data,
      revision: 1,
      ...(entry.error ? { error: true as const } : {}),
    });
    app.run('projectContextByLabel[__key] = {state: "ready", data: __entry.data};', { key, entry });
  }
  const env: RecoveryEnv = {
    group,
    generated: nextNumber(board['generated']),
    harnesses: harnessLabels(board),
    entry,
  };
  return { app, board, label, variant, legacyGroup, env, entry };
}

export function labelsOf(board: Record<string, unknown>): string[] {
  const rows = Array.isArray(board['sessions'])
    ? (board['sessions'] as { project?: unknown }[])
    : [];
  return [...new Set(rows.map((row) => String(row.project == null ? '' : row.project)))];
}
