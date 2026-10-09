import { stableProjectKey } from '../api/identity';
import { compatSessKey } from '../api/identity';
import type { Observed, ObservedProject } from '../observed';
import { sessionKey, payloadSessionRows, asPayload, type Row } from '../observed/values';
import { fieldText, text } from './raw';

/* One project as the cockpit reads it: the observed group (the facts about each session) and the raw rows
   behind it (the published fields the observed model does not carry: Spacedock strips, task totals,
   delegation lanes, last output). The two travel together because the legacy views join them. */
export interface ProjectGroup {
  /** The published label, exactly: whitespace and the empty label are groups of their own. */
  readonly label: string;
  /** The raw rows, one per observed session, in the observed order. */
  readonly sessions: readonly Row[];
  readonly observed: ObservedProject;
}

/* The legacy join. The observed model omits the strips and totals, so the page looks each observed
   session up in a map keyed by its exact harness and sid and keeps what it finds. A key held by two rows
   maps to the LAST of them for both, which is the page's behaviour and is kept: a board that publishes
   one pair twice is malformed, and what it draws is not a thing to improve on the way through. */
export function groupFor(payload: unknown, model: Observed, label: string): ProjectGroup | null {
  const observed = model.projects.find((candidate) => candidate.key === label);
  if (!observed) return null;
  const sources = new Map<string, Row>(
    payloadSessionRows(asPayload(payload)).map((row) => [sessionKey(row), row]),
  );
  const sessions = observed.sessions
    .map((session) => sources.get(sessionKey(session as unknown as Row)))
    .filter((row): row is Row => row !== undefined);
  return { label: observed.key, sessions, observed };
}

/** The unique repository key when every keyed session agrees on one, otherwise the label. */
export function stableKey(group: Pick<ProjectGroup, 'label' | 'sessions'>): string {
  return stableProjectKey({
    label: group.label,
    sessions: group.sessions.map((row) => ({ project_key: row['project_key'] })),
  });
}

/** The compatibility key of a row: harness, a colon, and the sid (the display id when there is none). */
export const sessKey = compatSessKey;

/** "work" -> "Work": the page's word for a published token, with `-` and `_` read as spaces. */
export function humanLabel(value: unknown): string {
  const words = String(value || 'work')
    .replace(/[-_]+/g, ' ')
    .trim();
  return words ? (words[0] ?? '').toUpperCase() + words.slice(1) : 'Work';
}

/** The project's short name: its published name's last path segment, or the label's. */
export function scopeLabel(group: Pick<ProjectGroup, 'label' | 'sessions'>): string {
  const named = group.sessions.find((session) => fieldText(session, 'project_name').trim());
  const name = text(named?.['project_name']) || group.label;
  return String(name).split('/').filter(Boolean).pop() || 'Project';
}

/** The sessions this group's observed model counts as working: the ones the cockpit calls active. */
export function workingSessions(group: ProjectGroup): readonly Row[] {
  const keys = new Set(
    group.observed.working.map((session) => sessionKey(session as unknown as Row)),
  );
  return group.sessions.filter((session) => keys.has(sessionKey(session)));
}

/** The focused session of a project route: the row whose compatibility key is the route's focus. */
export function focusedSession(group: ProjectGroup, focus: string | null | undefined): Row | null {
  if (!focus) return null;
  return group.sessions.find((session) => sessKey(session) === focus) ?? null;
}
