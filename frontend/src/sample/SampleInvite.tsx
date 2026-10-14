import { RouteLink } from '../shell/RouteLink';
import { SAMPLE_HARNESS, SAMPLE_PROJECT, SAMPLE_SID } from './ids';

/* How a new reader finds the sample: one quiet line above the Sessions list, with the link. It is its own
   component, outside the Sessions list, so the list stays exactly what the rows promise. */
export function SampleInvite() {
  return (
    <p className="mb-3 text-muted-foreground" data-sample-invite>
      New to Compass?{' '}
      <RouteLink
        route={{
          view: 'session',
          project: SAMPLE_PROJECT,
          harness: SAMPLE_HARNESS,
          session: SAMPLE_SID,
        }}
      >
        See a sample session (view only)
      </RouteLink>{' '}
      to learn what the Session page and Intent and drift show.
    </p>
  );
}
