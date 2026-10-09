import { legacyHarness } from '../../test/legacy_goldens';
import type { LegacyViews } from '../observed/legacy.test.helper';

/* What the removed page said, for the Intent code, as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export interface LegacyIntent extends LegacyViews {
  /** Runs source in the page's own scope, for the `let` bindings a call cannot reach. */
  run<T = unknown>(source: string, bindings?: Record<string, unknown>): T;
}

export function loadLegacyIntent(): LegacyIntent {
  return legacyHarness('intent', {
    slots: {
      setData: 'data',
      setFocusCapability: 'capability',
      sessionsHtml: 'data',
      sessionHtml: 'data',
    },
  });
}
