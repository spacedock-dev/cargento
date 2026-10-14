import type { Route, SessionRoute } from '../router/grammar';

/* The one session that is a sample: an anonymized Claude Code session, read by a real stored reading,
   shipped inside the page so a new reader can see what the Session page and Intent and drift do without
   running an agent. `sample` is not a shape any real session id takes, so the route cannot collide with
   one. docs/design-sample-session.md owns the decision. */
export const SAMPLE_PROJECT = 'acme/dashboard';
export const SAMPLE_HARNESS = 'claude';
export const SAMPLE_SID = 'sample';

export const SAMPLE_FRAGMENT = `#n=session:${encodeURIComponent(SAMPLE_PROJECT)}:${SAMPLE_HARNESS}:${SAMPLE_SID}`;

export function isSampleRoute(route: Route): route is SessionRoute {
  return (
    route.view === 'session' &&
    route.project === SAMPLE_PROJECT &&
    route.session === SAMPLE_SID &&
    (route.harness === undefined || route.harness === SAMPLE_HARNESS)
  );
}
