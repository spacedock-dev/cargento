import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for the Console rail (`nextProjectRail` over the observed workstream, with the tab's memory behind the delegation figure), as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export interface LegacyRail {
  reset(): void;
  /** `nextObserveWorkstream(payload)`: one accepted payload appended to the tab's memory. */
  observe(payload: unknown): void;
  setCapability(value: string): void;
  /** The project keys the model groups the payload into, in the order the page draws them. */
  projects(payload: unknown): string[];
  /** `nextProjectRail` for one project of the payload. */
  rail(payload: unknown, project: string): string;
}

export function loadLegacyRail(): LegacyRail {
  return legacyHarness('rail', {
    observe: ['projects', 'rail'],
    slots: { setCapability: 'capability' },
    reset: ['reset'],
  });
}
