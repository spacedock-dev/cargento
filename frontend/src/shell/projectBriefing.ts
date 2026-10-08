import { BriefingUnavailable } from '../controls/briefingUnavailable';
import type { ProjectRoute } from '../router/grammar';

export interface ProjectBriefing {
  /** Read only inside the press that copies it: a briefing is never built on a render. */
  readonly briefingText: () => string;
}

/* The project briefing belongs to the project view that builds it from the rows it draws. Until that
   view is migrated there is no briefing to copy, so the press says so rather than copying an empty
   string and calling it a briefing: the thrown BriefingUnavailable reaches the More menu as "Copy unavailable"
   and is announced as not available in the React interface yet. The
   project view replaces this hook; the menu and its cue are already the shared control's. */
export function useProjectBriefing(route: ProjectRoute): ProjectBriefing {
  void route;
  return {
    briefingText: () => {
      throw new BriefingUnavailable('The project briefing has not been migrated to the React interface.');
    },
  };
}
