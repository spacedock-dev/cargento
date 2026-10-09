import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for the workstream evidence store and delegation arithmetic, as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export interface LegacyDelegation {
  /** A new page: the tab's memory is empty again. */
  reset(): void;
  /** `nextObserveWorkstream(payload)`: one accepted payload appended to the tab's memory. */
  observe(payload: unknown): void;
  /** `nextWorkstreamProjectWindow(project)` over the tab's memory. */
  window(project: string): Record<string, unknown>;
  /** `nextObservedHistory(project, evidence)`: the rows the page prints. */
  history(project: string): Record<string, unknown>;
  metric(window: unknown): Record<string, unknown>;
  trend(window: unknown): number | null;
  label(window: unknown): string;
}

export function loadLegacyDelegation(): LegacyDelegation {
  return legacyHarness('delegation', {
    pure: ['metric', 'trend', 'label'],
    observe: ['window', 'history'],
    reset: ['reset'],
  });
}
