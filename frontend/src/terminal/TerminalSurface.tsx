import { Button } from '../ui/button';
import { useEffect, useRef, useSyncExternalStore } from 'react';
import { nextFiniteNumber } from '../api/bootstrap';
import { compatSessKey, exactIdentity } from '../api/identity';
import type { SessionIdentity } from '../api/types';
import { Disclosure } from '../controls/Disclosure';
import { disclosureKey } from '../controls/disclosureStore';
import { useShell } from '../shell/context';
import { useBoardSelector } from '../store/hooks';
import type { TerminalOwner } from './owner';
import { absenceOf, originTitle, type OriginLookup } from './registration';
import { useTerminalOwner } from './useTerminalOwner';
import './terminal.css';

export interface TerminalSurfaceProps {
  /** The route's project, which scopes the registration recipe's open state. */
  readonly project: string;
  /** The focused session, by exact harness and sid. Never a display id and never inferred from cwd or time. */
  readonly identity: SessionIdentity;
}

/* The recipe is two acts, and written as one paragraph of running prose both flags wrap. It sits behind a
   shared disclosure rather than a bare `<details>`, because the board redraws on live data and a bare one
   snaps shut, losing the reader's place in a command. */
function RegistrationRecipe({
  project,
  scope,
}: {
  readonly project: string;
  readonly scope: string;
}) {
  return (
    <Disclosure
      disclosureKey={disclosureKey({ project, scope, name: 'terminal-registration' })}
      summary="How to register a terminal"
      focusKey={`substrate:${project}\n${scope}\nterminal-registration`}
    >
      <ol className="pc-substrate-steps">
        <li>
          Start the dashboard with <code>--interaction-origin-session harness:sid</code> and{' '}
          <code>--interaction-origin-registration-file PATH</code>.
        </li>
        <li>
          Run the registration client inside the tmux pane for this exact session with that file.
        </li>
      </ol>
      <p className="pc-substrate-empty">Output is read-only.</p>
    </Disclosure>
  );
}

function Absence({
  lookup,
  project,
  scope,
}: {
  readonly lookup: OriginLookup | undefined;
  readonly project: string;
  readonly scope: string;
}) {
  const absence = absenceOf(lookup);
  if (absence.checking) {
    return (
      <p className="pc-substrate-empty" role="status">
        {absence.message}
      </p>
    );
  }
  return (
    <div className="pc-terminal-absence">
      <p className="pc-substrate-empty">{absence.message}</p>
      {absence.serverReason ? (
        <p className="pc-substrate-empty">
          Server reason: <code>{absence.serverReason}</code>
        </p>
      ) : null}
      {absence.recipe ? <RegistrationRecipe project={project} scope={scope} /> : null}
    </div>
  );
}

function Title({
  lookup,
}: {
  readonly lookup: Extract<OriginLookup, { state: 'registered' | 'unavailable' }>;
}) {
  const title = originTitle(lookup.data.origin);
  if (title.complete !== null) return <strong>{title.complete}</strong>;
  return (
    <div className="pc-terminal-identity">
      {title.session ? <strong>{title.session}</strong> : <p>Tmux session name not published.</p>}
      {title.window !== null ? (
        <code>{`window ${title.window}`}</code>
      ) : (
        <p>Window index not published.</p>
      )}
      {title.pane !== null ? <code>{`pane ${title.pane}`}</code> : <p>Pane index not published.</p>}
    </div>
  );
}

function OpenTerminal({
  owner,
  lookup,
  terminalKey,
  follow,
}: {
  readonly owner: TerminalOwner;
  readonly lookup: Extract<OriginLookup, { state: 'registered' | 'unavailable' }>;
  readonly terminalKey: string;
  readonly follow: boolean;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  /* Attach on mount, detach on unmount, and nothing else: the terminal's lifetime is the owner's. The
     detach takes the screen out of this viewport and leaves the terminal, its socket and the reader's
     offset where they are, so navigating away and back finds the same screen. */
  useEffect(() => {
    const element = viewport.current;
    return element ? owner.attach(element, terminalKey) : undefined;
  }, [owner, terminalKey]);
  return (
    <aside className="pc-terminal" aria-label="Read-only terminal output">
      <div className="pc-terminal-bar">
        <Title lookup={lookup} />
        <span>read-only</span>
        <Button
          type="button"
          id="pc-terminal-jump"
          variant="terminal"
          hidden={follow}
          onClick={() => owner.jump()}
        >
          Jump to live
        </Button>
        <Button type="button" variant="terminal" onClick={() => owner.close()}>
          Close
        </Button>
      </div>
      {/* No React children: the retained screen is put in here by the owner, and React must never reconcile it away. */}
      <div id="pc-terminal-viewport" className="pc-terminal-viewport" ref={viewport} />
    </aside>
  );
}

/* The exact-session terminal section of a Console. It says what the bridge says: absent, refused and
   disabled each have their own sentence, and Open terminal appears only when the server reports this
   exact session registered. */
export function TerminalSurface({ project, identity }: TerminalSurfaceProps) {
  const owner = useTerminalOwner();
  const { runtime } = useShell();
  const snapshot = useSyncExternalStore(owner.subscribe, owner.getSnapshot);
  const revision = useBoardSelector(runtime.store, (board) =>
    nextFiniteNumber(board.data?.generated),
  );
  const { harness, sid } = identity;
  const key = compatSessKey({ harness, sid });

  /* A passive read of the registration, again when the board's revision advances. It is the only thing
     this component starts: opening is the reader's press. The owner makes the repeat under StrictMode a no-op. */
  useEffect(() => {
    owner.lookup({ harness, sid }, revision);
  }, [owner, harness, sid, revision]);

  const lookup = snapshot.lookups.get(key);
  let body;
  /* A terminal is matched to a session by its exact harness and sid and by nothing else: not its working
     directory, not how close in time two things happened, not its title. A row without both has no
     identity to match, so it is said so and nothing is asked. */
  if (!exactIdentity({ harness, sid })) {
    body = (
      <p className="pc-substrate-empty">
        This session published no exact identity, so no terminal can be matched to it.
      </p>
    );
  } else if (!lookup || lookup.state !== 'registered')
    body = <Absence lookup={lookup} project={project} scope={key} />;
  else if (snapshot.openKey !== key) {
    body = (
      <Button
        type="button"
        variant="terminal"
        className="my-[8px] mb-3"
        onClick={() => owner.open(key)}
      >
        Open terminal
      </Button>
    );
  } else
    body = (
      <OpenTerminal owner={owner} lookup={lookup} terminalKey={key} follow={snapshot.follow} />
    );

  return (
    <section className="next-cockpit-terminal" data-next-cockpit-terminal>
      <h2>EXACT SESSION TERMINAL</h2>
      {body}
    </section>
  );
}
