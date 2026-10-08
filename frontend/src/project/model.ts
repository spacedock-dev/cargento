import { useMemo } from 'react';
import { nextNumber } from '../api/bootstrap';
import { exactIdentity } from '../api/identity';
import type { SessionIdentity } from '../api/types';
import { selectObserved } from '../observed/select';
import type { Row } from '../observed/values';
import type { ProjectRoute } from '../router/grammar';
import { useDisplayed } from '../shell/context';
import type { BoardSnapshot } from '../store/board';
import { selectContextRead, type ContextRead } from '../store/selectors';
import { harnessLabels } from '../sessions/rows';
import { focusedSession, groupFor, stableKey, type ProjectGroup } from './group';
import {
  commandAttention,
  recoveryBriefing,
  type AttentionItem,
  type Briefing,
  type ContextEntryLike,
  type RecoveryEnv,
} from './recovery';
import { memoKey, type MemoKind } from '../storage';

/* Everything one project page is a function of, derived once per displayed board: the group (the
   observed model joined to the raw rows), the exact focused session, the project-scope context read and
   what the recovery strip and the briefing say about them. The views read it and never recompute it, so
   the strip, the More menu's briefing and the tabs cannot disagree about the project. */
export interface ProjectModel {
  readonly route: ProjectRoute;
  readonly group: ProjectGroup;
  readonly payload: Row;
  readonly generated: number | null;
  readonly harnesses: ReadonlyMap<string, string>;
  /** The unique repository key when the sessions agree on one, else the label: what storage and reads are keyed by. */
  readonly projectKey: string;
  /** The route's focused row, or null at project scope (and for a focus the board no longer holds). */
  readonly focus: Row | null;
  /** The focus as an exact harness and sid, or null: a session with no exact pair has no focused read to make. */
  readonly focusIdentity: SessionIdentity | null;
  readonly env: RecoveryEnv;
  /** The project-scope read, which the recovery strip and every tab but Decisions stand on. */
  readonly projectRead: ContextRead;
  /** The read of the scope the reader is looking at: the focused session's, or the project's. */
  readonly scopeRead: ContextRead;
  readonly attention: readonly AttentionItem[];
}

export function contextEntryOf(read: ContextRead): ContextEntryLike | undefined {
  const { entry } = read;
  return entry
    ? { data: (entry.data as Row | null) ?? null, error: entry.error, revision: entry.revision }
    : undefined;
}

export function buildProjectModel(
  snapshot: BoardSnapshot,
  route: ProjectRoute,
): ProjectModel | null {
  const data = snapshot.data;
  if (!data) return null;
  const group = groupFor(data, selectObserved(snapshot), route.project);
  if (!group) return null;
  const projectKey = stableKey(group);
  const focus = focusedSession(group, route.focus);
  const focusIdentity = focus ? exactIdentity(focus) : null;
  const projectRead = selectContextRead(snapshot, projectKey, null);
  const scopeRead = focusIdentity
    ? selectContextRead(snapshot, projectKey, focusIdentity)
    : projectRead;
  const payload = data as unknown as Row;
  const harnesses = harnessLabels(payload);
  const env: RecoveryEnv = {
    group,
    generated: nextNumber(payload['generated']),
    harnesses,
    entry: contextEntryOf(projectRead),
  };
  return {
    route,
    group,
    payload,
    generated: env.generated,
    harnesses,
    projectKey,
    focus,
    focusIdentity,
    env,
    projectRead,
    scopeRead,
    attention: commandAttention(env),
  };
}

const models = new WeakMap<BoardSnapshot, Map<string, ProjectModel | null>>();

/* One model per displayed snapshot and route, shared by every reader of it: the page, the header's More
   menu and the tabs all stand on the same object, and a poll that changed nothing returns the one they
   already have. */
export function projectModelFor(snapshot: BoardSnapshot, route: ProjectRoute): ProjectModel | null {
  const key = `${route.project}\n${route.focus ?? ''}`;
  let byRoute = models.get(snapshot);
  if (!byRoute) {
    byRoute = new Map();
    models.set(snapshot, byRoute);
  }
  if (byRoute.has(key)) return byRoute.get(key) ?? null;
  const built = buildProjectModel(snapshot, route);
  byRoute.set(key, built);
  return built;
}

export function useProjectModel(route: ProjectRoute): ProjectModel | null {
  const snapshot = useDisplayed((current) => current);
  return useMemo(() => projectModelFor(snapshot, route), [snapshot, route]);
}

/** The released memo key of one of this scope's two human notes. */
export function noteKey(
  model: Pick<ProjectModel, 'projectKey' | 'focusIdentity' | 'focus'>,
  kind: MemoKind,
): string {
  return memoKey(model.projectKey, model.focus ? compatIdentity(model) : null, kind);
}

function compatIdentity(
  model: Pick<ProjectModel, 'focus'>,
): { harness: string; sid: string; session?: string } | null {
  const row = model.focus;
  if (!row) return null;
  return {
    harness: String(row['harness'] || ''),
    sid: String(row['sid'] || ''),
    session: String(row['session'] || ''),
  };
}

/** The briefing as it reads now: the two browser-local notes are read here, at the press or the draw, never earlier. */
export function briefingOf(model: ProjectModel, read: (key: string) => string): Briefing {
  return recoveryBriefing({
    env: model.env,
    focus: model.focus,
    attention: model.attention,
    outcome: read(noteKey(model, 'outcome')),
    currentFocus: read(noteKey(model, 'focus')),
  });
}
