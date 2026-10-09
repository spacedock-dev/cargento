import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for the project views, as the differential tests ask for it. The answers are
   recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. The recording ran the
   whole page in one context, because a project view stands on half the app (the observed model, the
   cockpit, the workstream, the timeline's helpers); the stage conditions and the steering bar were
   stubbed because their own owner draws them, and the cockpit's project-context fetch was replaced by a
   seeded cache, so no request left the recording. */

export interface LegacyApp {
  /** Replaces the page's `nextData`, and clears the render cache so the model is derived from it. */
  setData(payload: unknown): void;
  /** The page's route, as the fragment names it: `#n=project:alpha%2Fapp:course`. */
  setRoute(fragment: string): void;
  /** Seeds one project-context entry exactly as the cockpit's loader would have stored it. */
  setContext(key: string, entry: { data: unknown; revision: number; error?: true }): void;
  /** Feeds a payload to the page's tab workstream buffer, as `refreshNext` does for each accepted body. */
  observe(payload: unknown): void;
  /** Runs source in the page's own scope: the only way to read a `let` binding or call a lifted constant. */
  run<T = unknown>(source: string, bindings?: Record<string, unknown>): T;
  call<T = unknown>(name: string, ...args: unknown[]): T;
}

/* HTML as the page would insert it, parsed for the DOM a test then reads. A template, so a fragment that
   is not a document parses as written (a `<tr>` or a bare `<li>` keeps its tags). */
export function parseHtml(html: string): DocumentFragment {
  const template = document.createElement('template');
  template.innerHTML = html;
  return template.content;
}

export function loadLegacyApp(options: { storage?: Record<string, string> } = {}): LegacyApp {
  // The starting storage is part of what the page was asked, so it is part of the kind.
  return legacyHarness(`app:${JSON.stringify(options)}`, {
    slots: { setData: 'data', setRoute: 'route' },
  });
}
