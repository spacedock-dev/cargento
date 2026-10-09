import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for the semantic timeline and activity filter, as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export interface LegacyTimeline {
  readonly storage: Map<string, string>;
  /** `nextRoute` and `projectQuerySession`, the two globals the filter's scope reads. */
  setScope(project: string, session: string | null): void;
  reload(): void;
  /** Empties the `localStorage` the filter writes to, as a cleared browser would. */
  clearStorage(): void;
  timeline(
    data: unknown,
    model: unknown,
    delegations: unknown[],
    focus: unknown,
    origins: unknown[] | undefined,
    options: Record<string, unknown>,
  ): string;
  setGraphMode(mode: string): boolean;
  resolveGraphMode(options?: Record<string, unknown>): string;
}

export interface LegacyRow {
  readonly eventId: string;
  readonly kind: string;
  readonly lane: string;
  readonly current: string | null;
}

/* The rows a legacy timeline drew, in order. Attribute values are HTML-escaped by the page, and a fact id
   in these tests never carries a character that escapes. */
export function legacyRows(html: string): LegacyRow[] {
  const rows: LegacyRow[] = [];
  for (const match of html.matchAll(
    /<article class="pc-graph-row[^>]*data-lane-key="([^"]*)"[^>]*data-event-id="([^"]*)" data-semantic-kind="([^"]*)"([^>]*)>/g,
  )) {
    const attributes = match[4] ?? '';
    rows.push({
      eventId: match[2] ?? '',
      kind: match[3] ?? '',
      lane: match[1] ?? '',
      current: /data-task-current="([^"]*)"/.exec(attributes)?.[1] ?? null,
    });
  }
  return rows;
}

export function legacyEmptyText(html: string): string | null {
  return /<p class="pc-substrate-empty">([^<]*)<\/p>/.exec(html)?.[1] ?? null;
}

export function loadLegacyTimeline(): LegacyTimeline {
  return legacyHarness('timeline', {
    slots: { setScope: 'scope' },
    observe: ['timeline', 'resolveGraphMode'],
    props: ['storage'],
  });
}
