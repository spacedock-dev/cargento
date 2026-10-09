import { sessKey } from './group';
import { isRecord, list, text, type Row } from './raw';

/* The workers one session delegated to, as the delegated-work lanes publish them: the parent's reported
   hierarchy (or its flat subagent list), each joined by observer sid to the project context's child
   assignment snapshot for whatever the parent's own report left out. Ported from `projectDelegationLanes`.

   Two deliberate differences, both on input the legacy page would throw on or read by accident:
   - A member of the hierarchy, or a snapshot row, that is not a record is skipped. The legacy page reads a
     field off it and stops drawing; a port that stopped drawing is not parity worth having.
   - The snapshot is handed in by the caller. The strip, Now and Course pass the PROJECT-scope context read,
     where the legacy page reads a cache the Decisions tab happens to seed, so a lane drawn on Now had its
     snapshot only after the reader had visited another tab. The Decisions tab passes the selected scope's
     own read (a focused session's when one is selected), as the legacy page does. */
export interface Lane {
  readonly entity: string;
  readonly stage: string;
  readonly workflowBinding: string;
  readonly workItemId: string;
  /** The published liveness bit, as published: only `false` withholds the active mark. */
  readonly active: unknown;
  readonly parentSession: string;
  readonly observerSid: string;
  readonly worker: string;
  readonly assignment: string;
  readonly source: string;
  readonly relation: string;
  readonly depth: number;
  readonly at: number;
}

export function delegationLanes(
  session: Row | null | undefined,
  childAssignments: unknown,
): Lane[] {
  if (!session) return [];
  const reported = Array.isArray(session['subagent_hierarchy'])
    ? (session['subagent_hierarchy'] as unknown[])
    : Array.isArray(session['subagents'])
      ? (session['subagents'] as unknown[]).map((agent) =>
          Object.assign({ depth: 1, parent_name: null }, agent),
        )
      : [];
  const observed = list(childAssignments).filter(isRecord);
  const lanes: Lane[] = [];
  for (const agent of reported) {
    if (!isRecord(agent)) continue;
    const fallback: Row =
      observed.find(
        (row) => row['observer_sid'] && row['observer_sid'] === agent['observer_sid'],
      ) ?? {};
    lanes.push({
      entity: text(agent['workflow_entity'] || fallback['workflow_entity']),
      stage: text(agent['workflow_stage'] || fallback['workflow_stage']),
      workflowBinding: text(agent['workflow_binding'] || fallback['workflow_binding']),
      workItemId: text(agent['work_item_id'] || fallback['work_item_id']),
      active: agent['active'],
      parentSession: sessKey(session),
      observerSid: text(agent['observer_sid'] || fallback['observer_sid']),
      worker: String(agent['name'] || fallback['name'] || 'Ensign'),
      assignment: String(agent['assignment'] || fallback['assignment'] || 'assignment unavailable'),
      source: agent['assignment']
        ? String(agent['assignment_status'] || 'exact parent dispatch')
        : fallback['assignment']
          ? `${String(fallback['source'] || 'child observer snapshot')} · ${String(fallback['snapshot_status'] || 'derived')}`
          : 'assignment source unavailable',
      relation: agent['parent_name'] ? `child of ${String(agent['parent_name'])}` : 'direct child',
      depth: Math.max(1, Math.min(6, Number(agent['depth']) || 1)),
      at: Number(session['last_activity']) || 0,
    });
  }
  return lanes;
}
