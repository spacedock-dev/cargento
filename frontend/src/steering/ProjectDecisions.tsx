import { useMemo } from 'react';
import { payloadSessions } from '../api/bootstrap';
import { compatSessKey, contextKey } from '../api/identity';
import type { SessionIdentity } from '../api/types';
import { delegationLanes } from '../project/lanes';
import { captainDecisionCounts, recoveryDecisions } from '../project/recovery';
import { useDisplayed } from '../shell/context';
import type { Row } from '../observed';
import { Timeline, type Delegation } from '../timeline';
import './steering.css';

export interface ProjectDecisionsProps {
  /** The route's project label, exactly: it scopes the activity filter and every disclosure. */
  readonly project: string;
  /** The stable project key the context is read by, which is not always the label. */
  readonly projectKey: string;
  /** The exact selected session, or null at project scope. `state` decides whether a final output is yet a result. */
  readonly focus: (SessionIdentity & { readonly state?: string }) | null;
}

/* The Decisions tab: how the recorded decisions have been applied, then the semantic timeline the activity
   filter chooses among. The timeline and its filter are the shared ones; this adds what is the tab's own, the
   one-line account of what became of the decisions and the workers a session delegated to.

   The summary reads the SAME context the timeline draws: the focused session's when one is selected, the
   project's otherwise. Reading the project's under a focused timeline would describe other decisions than the
   rows below it. */
export function ProjectDecisions({ project, projectKey, focus }: ProjectDecisionsProps) {
  const snapshot = useDisplayed((current) => current);
  const data = snapshot.data;
  const members = useMemo(
    () =>
      payloadSessions(data).rows.filter(
        (row) => String(row.project ?? '') === project,
      ) as unknown as readonly Row[],
    [data, project],
  );
  const identities = useMemo(
    () =>
      members.flatMap((row) =>
        row['harness'] && row['sid']
          ? [{ harness: String(row['harness']), sid: String(row['sid']) }]
          : [],
      ),
    [members],
  );
  const entry = snapshot.contexts.get(contextKey(projectKey, focus));
  const entryData = (entry?.data ?? null) as Row | null;
  const delegations = useMemo(() => {
    const observed = entryData?.['child_assignments'];
    const rows = focus
      ? members.filter((row) => compatSessKey(row) === compatSessKey(focus))
      : members;
    return rows.flatMap((row) => delegationLanes(row, observed)) as Delegation[];
  }, [members, entryData, focus]);
  const semantic = entryData?.['semantic'];
  const counts = semantic ? captainDecisionCounts(semantic) : null;
  const total = counts ? counts.pending + counts.unknown + counts.superseded + counts.applied : 0;
  return (
    <>
      {total ? (
        <p className="next-cockpit-decision-summary" data-next-cockpit-decision-summary>
          {`Decision application · ${recoveryDecisions(semantic)}`}
        </p>
      ) : null}
      <Timeline
        project={project}
        projectKey={projectKey}
        focus={focus}
        sessions={identities}
        delegations={delegations}
        defaultMode="decisions"
      />
    </>
  );
}
