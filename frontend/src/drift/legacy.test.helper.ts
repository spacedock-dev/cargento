import { legacyHarness } from '../../test/legacy_goldens';
import type { LegacyIntent } from '../intent/legacy.test.helper';

/* What the removed page said, for the Drift code, as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export interface LegacyDrift extends LegacyIntent {
  /** Declares the named top-level functions and constants from `next-cockpit.js` that the page has not. */
  lift(names: readonly string[], file?: string): void;
}

export function loadLegacyDrift(): LegacyDrift {
  return legacyHarness('drift', {
    slots: {
      setData: 'data',
      setFocusCapability: 'capability',
      sessionsHtml: 'data',
      sessionHtml: 'data',
    },
  });
}
