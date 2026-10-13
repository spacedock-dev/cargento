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

/* A copy of `value` without one key at any depth, and otherwise exactly as it was: undefined, NaN and
   Infinity survive, which a JSON round trip would lose and the recorded answers are keyed by. Used where this
   page has a field the retired page never had (docs/design-frontend-migration.md#held-to-recorded-answers). */
export function withoutKey(value: unknown, key: string): unknown {
  if (Array.isArray(value)) return value.map((item) => withoutKey(item, key));
  if (
    value !== null &&
    typeof value === 'object' &&
    Object.getPrototypeOf(value) === Object.prototype
  ) {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([name]) => name !== key)
        .map(([name, item]) => [name, withoutKey(item, key)]),
    );
  }
  return value;
}
