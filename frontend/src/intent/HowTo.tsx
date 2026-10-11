import { compatSessKey } from '../api/identity';
import { Disclosure, disclosureKey } from '../controls';
import { readingRoute, routeRefusal } from '../drift/route';
import { STEER_HARNESSES, WORK_HARNESSES } from '../drift/sentences';
import { harnessLabels } from '../sessions/rows';
import { usePanel } from './useIntent';
import type { Row } from '../observed';

export function HowTo() {
  const { payload, session, project } = usePanel();
  return <IntentHowTo payload={payload} session={session} project={project} />;
}

export function IntentHowTo({
  payload,
  session,
  project,
}: {
  readonly payload: Row;
  readonly session: Row;
  readonly project: string;
}) {
  const harness = String(session['harness'] || '');
  const labels = harnessLabels(payload);
  const label = (key: string) =>
    labels.get(key) || ({ claude: 'Claude Code', pi: 'Pi' }[key] ?? key);
  const route = readingRoute(payload, session);
  const reader = route?.['provider']
    ? String(route['label'] || route['provider'])
    : routeRefusal(payload, session);
  const steer = STEER_HARNESSES.includes(harness)
    ? 'available here'
    : `${STEER_HARNESSES.map(label).join(' and ')} only`;
  return (
    <Disclosure
      disclosureKey={disclosureKey({
        project,
        scope: compatSessKey(session),
        name: 'intent-howto',
      })}
      summary="How Intent and drift works"
      variant="popover"
      focusKey={`intent-howto:${compatSessKey(session)}`}
    >
      <h3 className="text-body font-semibold">How Intent and drift works</h3>
      <p>1. Give the goal. Cargento drafts one from your first prompt; edit it if it is off.</p>
      <p>
        2. Press Analyze drift. It asks once to allow the reading and counts against a daily cap,
        both shown beside the button.
      </p>
      <p>
        3. Read where the work left your goal. On Claude Code you can copy a correction to steer the
        session back.
      </p>
      <p
        data-next-intent-howto-limit
      >{`Levels: ${WORK_HARNESSES.map(label).join(' and ')} only. Analyze: ${reader}${reader.endsWith('.') ? '' : '.'} Steer back: ${steer}. Cargento never writes into sessions.`}</p>
      <p>“Not enough recorded yet” is normal until you add an expected outcome line.</p>
    </Disclosure>
  );
}
