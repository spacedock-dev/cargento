import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for the capacity strip and its consent, as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export type LegacyConsent = 'granted' | 'declined' | null;

export interface LegacyCapacity {
  rows(payload: unknown): Record<string, unknown>[];
  models(raw: unknown): unknown;
  clock(stamp: unknown, generated: unknown): string;
  /** `nextCapacityView(payload)`: the disclosure, the strip and the switch, as the page draws them. */
  view(payload: unknown, state: { consent: LegacyConsent; selected: string }): string;
  /** `nextUsageDisclosure(payload) + nextUsageSwitch(payload)`: what the Console rail draws. */
  rail(payload: unknown, consent: LegacyConsent): string;
  spread(payload: unknown, harness: string): string;
  /** The selection the page holds after its last draw. */
  selected(): string;
}

export function loadLegacyCapacity(): LegacyCapacity {
  return legacyHarness('capacity', {
    // `view` and `rail` set the consent and the data they draw from, so their answers depend on their
    // arguments alone; `view` also leaves the selection `selected()` reads.
    pure: ['rows', 'models', 'clock', 'view', 'rail', 'spread'],
    slots: { view: 'drawn' },
    observe: ['selected'],
  });
}
