import { legacyHarness } from '../../test/legacy_goldens';
import type { LegacyViews } from '../observed/legacy.test.helper';

/* What the removed page said, for the Attention model, its text builders and its view, as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export interface LegacyAttention extends LegacyViews {
  /** `nextAttentionModel(payload)`. */
  model(payload: unknown): Record<string, unknown>;
  /** `nextAttentionAnnouncement(previous, current)` over two payloads. */
  announcement(previous: unknown, current: unknown): string;
  /** `nextAttentionView(model, expanded, open)` for `payload`, as the page assembles it. */
  attentionHtml(payload: unknown, expanded?: readonly string[], open?: readonly string[]): string;
}

export function loadLegacyAttention(): LegacyAttention {
  return legacyHarness('attention', {
    // The model and the announcement set the data they read, so their answers depend on their arguments alone.
    pure: ['model', 'announcement'],
    slots: {
      setData: 'data',
      model: 'data',
      attentionHtml: 'data',
      setFocusCapability: 'capability',
    },
  });
}
