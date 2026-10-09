import { useFocusKey } from '../controls/useFocusKey';
import { useShell } from '../shell/context';
import { heldFor, useConsent, useUsageOffered } from './held';

/* The disclosure that gates the quota fetch, and the switch that changes the answer. SECURITY.md's "Usage
   quota reads" section is the contract and its "Consent and the off switch" paragraph is the promise this
   file keeps: the vendor numbers are asked for only after the reader has answered YES on this origin, and
   unanswered is not yes. `usage=1` rides a poll only when the transport reads `granted` from the same
   storage lane this writes (`transport/runtime`), so nothing here builds a request, and nothing here runs
   before a press: mounting, StrictMode's second effect, a poll and a reconnect read the answer and write
   nothing. */

const SWITCH_KEY = 'usage:switch';

/* Records the answer the reader pressed, then asks for the board again so the answer is visibly acted on:
   granting has to reach the server as a parameter on the next request, and without this refresh the first
   fetch would wait out the ordinary poll and the reader would think the answer did nothing. The refresh is a
   manual one, as the legacy page's was, so the header says it is reading. */
function useAnswer() {
  const { runtime } = useShell();
  return (value: 'granted' | 'declined') => {
    heldFor(runtime).usage.answer(value);
    void runtime.refresh({ manual: true });
  };
}

/** In flow, never a modal: the board stays fully readable behind the question. Nothing while it is answered or not offered. */
export function UsageDisclosure() {
  const offered = useUsageOffered();
  const consent = useConsent('usage');
  const answer = useAnswer();
  const { controls } = useShell();
  const grantRef = useFocusKey<HTMLButtonElement>(controls.focusLane, 'usage:answer-granted', {
    fallback: SWITCH_KEY,
  });
  const declineRef = useFocusKey<HTMLButtonElement>(controls.focusLane, 'usage:answer-declined', {
    fallback: SWITCH_KEY,
  });
  if (!offered || consent !== null) return null;
  return (
    <section
      className="next-usage-consent"
      data-next-usage-consent=""
      role="region"
      aria-label="Quota fetch disclosure"
    >
      <p>
        <strong>Read your quota from the vendor?</strong> Cargento can show your Claude Code and
        Cursor windows. Doing it means reading the credential that harness already stored on this
        machine and sending it to that vendor, at most once every five minutes, to ask for your
        usage numbers and nothing else. The credential is never written, logged, or served, and no
        session content is sent.
      </p>
      <div className="next-usage-consent-actions">
        <button
          ref={grantRef}
          type="button"
          className="next-action"
          data-next-usage-answer="granted"
          onClick={() => answer('granted')}
        >
          Read my quota
        </button>
        <button
          ref={declineRef}
          type="button"
          className="next-action"
          data-next-usage-answer="declined"
          onClick={() => answer('declined')}
        >
          No thanks
        </button>
      </div>
      <p className="next-usage-consent-note">
        Changeable later from this strip. <code>--no-usage</code> refuses it for a whole run
        whatever is stored here.
      </p>
    </section>
  );
}

/* The "changed later" half of the promise. Drawn only once the question has been answered, so the
   disclosure above and this control are never both on screen claiming the same decision. */
export function UsageSwitch() {
  const offered = useUsageOffered();
  const consent = useConsent('usage');
  const answer = useAnswer();
  const { controls } = useShell();
  const buttonRef = useFocusKey<HTMLButtonElement>(controls.focusLane, SWITCH_KEY);
  if (!offered || consent === null) return null;
  const granted = consent === 'granted';
  return (
    <p className="next-usage-switch">
      <span>
        Vendor quota fetch: <strong>{granted ? 'on' : 'off'}</strong>
      </span>
      <button
        ref={buttonRef}
        type="button"
        className="next-action"
        data-next-usage-answer={granted ? 'declined' : 'granted'}
        onClick={() => answer(granted ? 'declined' : 'granted')}
      >
        {`Turn ${granted ? 'off' : 'on'}`}
      </button>
      {granted ? null : (
        <span className="next-usage-lapse">
          Windows above are the last cached read and will lapse.
        </span>
      )}
    </p>
  );
}

/** What the Console rail draws under its windows: the question until it is answered, the switch after. */
export function RailUsage() {
  return (
    <>
      <UsageDisclosure />
      <UsageSwitch />
    </>
  );
}
