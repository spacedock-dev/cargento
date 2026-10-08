import { disclosureKey } from '../controls/disclosureStore';

export interface RowScope {
  /** The route's project label, which keys every disclosure of the timeline. */
  readonly project: string;
  /** The focused session's compatibility key, or null at project scope, where no session is focused. */
  readonly session: string | null;
}

/* Every disclosure of the timeline is keyed by project, session (when focused) and its own name, so two
   projects, or two sessions of one, never share an open caveat. With no focused session the key carries
   the project alone, which is how the project-scope timeline keeps its own open state. */
export function timelineDisclosureKey(scope: RowScope, name: string): string {
  return disclosureKey({ project: scope.project, scope: scope.session, name });
}

export function timelineFocusKey(scope: RowScope, name: string): string {
  return `substrate:${scope.session ?? `project:${scope.project}`}\n${name}`;
}

