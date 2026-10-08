import type { ReactNode } from 'react';
import { IntentPanel } from '../intent/IntentPanel';
import type { Row } from '../observed';

/* Where the Intent and drift panel sits beside the activity column. The panel is the Intent step's: the
   goal and outcome editor, the prompt menu, the later directions and the live monitor switch, with the
   Drift section's own body arriving through `drift` from the Analyze step. Until that step lands the
   section says so in a stated placeholder, so the page never reads as if there were nothing to say about
   drift, and keeps the heading a goal link puts focus on, so the one-step access from a Sessions row lands
   where the panel is.

   `children` are what the session page composes beneath the panel's own sections: the delegated-work line
   and the departures raised while the reader was away. They are drawn here once, never again by the panel. */
export function DriftSlot({
  session,
  payload,
  project,
  drift,
  children,
}: {
  readonly session: Row;
  readonly payload: Row;
  readonly project: string;
  readonly drift?: ReactNode;
  readonly children?: ReactNode;
}) {
  return (
    <IntentPanel
      session={session}
      payload={payload}
      project={project}
      {...(drift ? { drift } : {})}
    >
      {children}
    </IntentPanel>
  );
}
