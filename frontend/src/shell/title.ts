import type { PayloadData } from '../api/types';
import type { Route } from '../router/grammar';
import { findSession, sessionTitle } from './derive';

/* One title per view, stable while the board refreshes: it changes only when the route does, or when
   the session it names publishes a different title. A session the board cannot find takes its own id,
   never a made-up name. */
export function documentTitle(route: Route, data: PayloadData | null): string {
  switch (route.view) {
    case 'attention':
      return 'Cargento — Attention';
    case 'projects':
      return 'Cargento — Projects';
    case 'sessions':
      return 'Cargento — Sessions';
    case 'intent':
      return 'Cargento — Intent log';
    case 'project':
      return `${route.project} — Cargento`;
    case 'session': {
      const session = findSession(data, route.project, route.harness, route.session);
      const title = session ? sessionTitle(session) : String(route.session || 'Session');
      return `${title} — ${route.project} — Cargento`;
    }
  }
}
