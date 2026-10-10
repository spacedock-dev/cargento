import { Button } from '../ui/button';
import { useState, type ReactNode } from 'react';
import { contextKey, exactIdentity } from '../api/identity';
import type { ProjectContext, SessionIdentity } from '../api/types';
import { useFocusKey } from '../controls/useFocusKey';
import { useDisplayed, useShell } from '../shell/context';
import { selectObserverModel, selectObserverRequest } from '../store/selectors';
import { heldFor, useConsent } from './held';
import './capacity.css';

/* The optional model goal summary, offered in the Console for one exact session. Three things are kept
   apart that one sentence could blur: an offer nothing has read ("not been read"), one that was read and is
   off for this run ("disabled"), and one that is on but has not been allowed by this reader. The consent is
   its own: quota consent does not authorize it, declining it is not a refusal of the server, and allowing
   it sends nothing. A request goes out only on the press of "Summarize this session", one at a time, for the
   exact session drawn, and the press names the disclosure the reader was SHOWN: if the offer the board holds
   now is not the one on screen, nothing is sent and the reader is told so, because an answer to one
   disclosure must not authorize another. Mounting, StrictMode's second effect, a poll, a reconnect and a
   route change draw this and send nothing. */

const ABSENT = 'Observer model availability has not been read.';
const DISABLED =
  'Observer model is disabled for this run. Start with --observer-model to offer optional goal summaries; --no-observer-model refuses them.';
const NO_SESSION = 'Select one exact session to request an optional model goal summary.';
const NO_DISCLOSURE = 'Observer disclosure is unavailable; model requests are withheld.';
/* Said when the press cannot be honoured as drawn. The first two are the page's own moving under the
   reader's hand, the third is the reader's own consent changing in another tab. */
const DISCLOSURE_CHANGED =
  'The observer model offer changed since this page was drawn, so nothing was sent; read it now and press again.';
const CONSENT_CHANGED =
  'Model summaries were turned off in another tab since this page was drawn, so nothing was sent.';

type Action = 'allow' | 'decline' | 'request';

export interface ObserverControlsProps {
  /** The stable project key the context is read by, which is not always the route's label. */
  readonly projectKey: string;
  /** The exact selected session, or null at project scope. A display id is not an identity. */
  readonly focus: SessionIdentity | null;
}

function Absence({ children }: { readonly children: string }) {
  return <p className="next-cockpit-empty">{children}</p>;
}

export function ObserverControls({ projectKey, focus }: ObserverControlsProps) {
  const { runtime, controls } = useShell();
  const consent = useConsent('observer');
  const identity = focus ? exactIdentity(focus) : null;
  const key = contextKey(projectKey, identity);
  const entry = useDisplayed((snapshot) => snapshot.contexts.get(key));
  /* Two primitives, not `selectObserverRequest`'s pair: a selector that builds an object returns a new one
     on every read, and a subscription over it would never settle. */
  const pending = useDisplayed((snapshot) => selectObserverRequest(snapshot, key).pending);
  const state = useDisplayed((snapshot) => selectObserverRequest(snapshot, key).state);
  const [refused, setRefused] = useState<string | null>(null);
  const allowRef = useFocusKey<HTMLButtonElement>(controls.focusLane, 'observer:allow', {
    fallback: 'observer:request',
  });
  const requestRef = useFocusKey<HTMLButtonElement>(controls.focusLane, 'observer:request');
  const declineRef = useFocusKey<HTMLButtonElement>(controls.focusLane, 'observer:decline');
  const model = selectObserverModel(entry);
  if (!model) return <Absence>{ABSENT}</Absence>;
  if (model.enabled !== true) return <Absence>{DISABLED}</Absence>;
  if (!identity) return <Absence>{NO_SESSION}</Absence>;
  const disclosure = String(model.disclosure || '');
  if (!disclosure) return <Absence>{NO_DISCLOSURE}</Absence>;

  const lane = heldFor(runtime).observer;
  const answer = (value: 'granted' | 'declined') => {
    setRefused(null);
    lane.answer(value);
  };
  /* The one place a model request starts. The board is read here, at the press, and compared with what is
     drawn: `requestObserverSummary` checks the same gates against the store, but a refusal there is silent,
     and a press that does nothing and says nothing is the worst answer to a consent. */
  const summarize = () => {
    setRefused(null);
    if (lane.read() !== 'granted') {
      setRefused(CONSENT_CHANGED);
      return;
    }
    const now: ProjectContext['observer_model'] | null = selectObserverModel(
      runtime.store.getSnapshot().contexts.get(key),
    );
    if (now?.enabled !== true || String(now.disclosure || '') !== disclosure) {
      setRefused(DISCLOSURE_CHANGED);
      return;
    }
    void runtime.requestObserverSummary({ projectKey, focus: identity });
  };
  const act = (action: Action) => {
    if (action === 'allow') answer('granted');
    else if (action === 'decline') answer('declined');
    else summarize();
  };
  const button = (action: Action, label: string, disabled = false) => (
    <Button
      ref={action === 'allow' ? allowRef : action === 'request' ? requestRef : declineRef}
      type="button"
      data-next-observer-action={action}
      data-next-focus={`observer:${action}`}
      disabled={disabled}
      onClick={() => act(action)}
    >
      {label}
    </Button>
  );
  let actions: ReactNode;
  if (consent === null) {
    actions = (
      <>
        {button('allow', 'Allow model summaries')}
        {button('decline', 'No thanks')}
      </>
    );
  } else if (consent === 'declined') {
    actions = button('allow', 'Allow model summaries');
  } else {
    actions = (
      <>
        {button('request', pending ? 'Request in progress' : 'Summarize this session', pending)}
        {button('decline', 'Turn off model summaries')}
      </>
    );
  }
  const status = pending
    ? 'The requested model summary is in progress.'
    : state === 'error'
      ? 'The summary request failed. Local analysis remains available.'
      : state === 'ready'
        ? 'The refresh returned. Model failures fall back to local analysis.'
        : consent === 'declined'
          ? 'Model summaries are off in this browser.'
          : 'Allowing summaries does not send a request. Use Summarize this session for each refresh.';
  const observed = (Array.isArray(entry?.data?.observers) ? entry.data.observers : []).find(
    (row) => row.harness === identity.harness && row.sid === identity.sid,
  );
  const goal = observed ? String(observed.goal || '').trim() : '';
  const modelStatus = observed?.model?.status;
  return (
    <section
      className="next-usage-consent"
      data-next-observer-consent=""
      aria-label="Observer model disclosure"
    >
      <p>{disclosure}</p>
      <p>
        Credential redaction does not remove private prose. Quota consent does not authorize this
        request.
      </p>
      <div className="next-usage-consent-actions">{actions}</div>
      <p role="status">{status}</p>
      {refused === null ? null : (
        <p data-next-observer-refused="" role="status">
          {refused}
        </p>
      )}
      {state === 'ready' ? (
        goal ? (
          <>
            <p>
              Observed goal: <span className="next-cockpit-source">{goal}</span>
            </p>
            {modelStatus ? (
              <p>
                Model status: <code>{modelStatus}</code>
              </p>
            ) : (
              <p>Model status was not published.</p>
            )}
          </>
        ) : (
          <p>No goal summary was published by this refresh.</p>
        )
      ) : null}
    </section>
  );
}
