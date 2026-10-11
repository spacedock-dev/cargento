import { compatSessKey } from '../api/identity';
import { Disclosure, disclosureKey } from '../controls';
import { LIVE_HARNESSES } from './liveMonitor';
import { LIVE_HINT } from '../drift/sentences';
import { DRIFT_SUBTITLE, INTENT_MEASURED } from './sentences';
import { TurnOff } from '../drift/ReadingControl';
import { DelegatedWorkLine } from '../sessions/DepartureParts';
import { Caveats, LaterDirections } from './Caveats';
import { ClearGoal } from './GoalField';
import { SavedStamp } from './IntentSection';
import { LiveMonitorSwitch } from './LiveMonitorSwitch';
import { usePanel } from './useIntent';
import { nextNumber } from '../api/bootstrap';

export function SessionMore() {
  const { session, payload, project } = usePanel();
  const scope = compatSessKey(session);
  const annotating = payload['annotate'] === true;
  const monitor = annotating && LIVE_HARNESSES.has(String(session['harness'] || ''));
  return (
    <div data-next-session-more>
      <Disclosure
        disclosureKey={disclosureKey({ project, scope, name: 'session-more' })}
        summary="More"
        focusKey={`session-more:${scope}`}
      >
        <div
          className="flex flex-col gap-2 [&_.next-session-drift-monitor]:mt-0"
          data-next-session-more-items
        >
          <div>
            <LiveMonitorSwitch />
            <p className="next-session-drift-sub text-body">{DRIFT_SUBTITLE}</p>
            {monitor ? <p className="next-cockpit-reading-why">{LIVE_HINT}</p> : null}
          </div>
          {annotating ? <Caveats /> : null}
          <div>
            <DelegatedWorkLine session={session} now={nextNumber(payload['generated'])} />
          </div>
          <TurnOff />
          <div>
            {annotating ? (
              <>
                <SavedStamp />
                <p className="next-cockpit-held-hint" data-next-intent-measured>
                  {INTENT_MEASURED}
                </p>
                <div className="flex">
                  <ClearGoal />
                </div>
              </>
            ) : null}
          </div>
          {annotating ? <LaterDirections /> : null}
        </div>
      </Disclosure>
    </div>
  );
}
