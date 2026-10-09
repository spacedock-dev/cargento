import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for the stage conditions, steering bar and tripwires panel, as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export interface LegacySteering {
  readonly storage: Map<string, string>;
  /** A new page: no stage choice has been made. */
  reset(): void;
  setData(payload: unknown): void;
  setNotification(permission: string | null): void;
  setStageDraft(id: string, stage: string): void;
  /** `nextStageConditions(sessions)`, or the whole board's when `sessions` is null. */
  stageHtml(sessions: { harness: string; sid: string }[] | null): string;
  steerHtml(project: string, layout?: string): string;
  guardrailsHtml(project: string): string;
  /** The page's own rule reader, for the stored shapes an older build wrote. */
  readRules(project: string): unknown[];
}

export function loadLegacySteering(): LegacySteering {
  return legacyHarness('steering', {
    slots: { setData: 'data', setNotification: 'notification' },
    observe: ['stageHtml', 'steerHtml', 'guardrailsHtml', 'readRules'],
    reset: ['reset'],
    props: ['storage'],
  });
}
