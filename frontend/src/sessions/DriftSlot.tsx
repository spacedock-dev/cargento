import { useEffect, useRef, type ReactNode } from 'react';
import { useShell } from '../shell/context';
import { goalFocusFor } from './heldState';

/* Where the Intent and drift panel sits beside the activity column. The panel belongs to the Intent step:
   it holds the goal and outcome editor, the reading and the departures. Until that step lands this draws a
   stated absence in its place, so the page never reads as if there were nothing to say about intent, and it
   keeps the heading a goal link puts focus on, so the one-step access from a Sessions row already lands
   where the panel will be.

   The request is consumed once, by the first panel drawn for the exact session it names. */
export function DriftSlot({
  harness,
  sid,
  children,
}: {
  readonly harness: string;
  readonly sid: string;
  readonly children?: ReactNode;
}) {
  const shell = useShell();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (goalFocusFor(shell.controls).take({ harness, sid })) heading.current?.focus();
  }, [shell, harness, sid]);
  return (
    <aside className="next-session-panel" data-next-session-panel="intent">
      <section className="next-session-intent-slot">
        <h2 id="next-session-intent-heading" ref={heading} tabIndex={-1}>
          Intent
        </h2>
        <p
          className="next-placeholder"
          data-next-placeholder="session-intent"
          data-next-owner="intent"
        >
          The Intent and drift panel is not available in the React interface yet. It arrives with a
          later migration step (the Intent log); the Python dashboard still serves it.
        </p>
        {children}
      </section>
    </aside>
  );
}
