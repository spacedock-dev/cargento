import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for its observed model and the two session parts that stand on it, as the
   differential tests ask for it. The answers are recorded in `frontend/test/golden/vitest`; see
   `frontend/test/legacy_goldens.ts`.

   One thing was replaced rather than run when the answers were recorded: `nextObservedHistory`, the
   workstream and delegation windows a project row carries. Those belong to the project step, which ports
   the workstream and delegation parts with their own oracle. A project's history keys are therefore
   dropped from the comparison (`PROJECT_HISTORY_KEYS`). */

export const PROJECT_HISTORY_KEYS = [
  'changes',
  'changeNoteText',
  'changeNoteKnown',
  'changeEmptyText',
  'changeEmptyKnown',
  'delegation',
  // Present only on this port's project object, as the room the project step fills.
  'history',
] as const;

export interface LegacySessions {
  /** Sets the page's `nextData` and `nextRoute`, the two globals its functions read. */
  setData(payload: unknown): void;
  call<T = unknown>(name: string, ...args: unknown[]): T;
}

/* A structural form that keeps what a JSON round trip would hide: `undefined` against absent, `NaN`,
   `-0`, and the order of an array (an object's key order is sorted away, since no reader sees it).
   Recorded answers are rebuilt by the codec rather than by the page, and a comparison reads them by shape,
   so equality is this canonical form rather than `toEqual`'s. */
export function canonical(value: unknown): unknown {
  if (value === undefined) return { $: 'undefined' };
  if (typeof value === 'number') {
    if (Number.isNaN(value)) return { $: 'NaN' };
    if (Object.is(value, -0)) return { $: '-0' };
    if (!Number.isFinite(value)) return { $: String(value) };
    return value;
  }
  if (Array.isArray(value)) return value.map(canonical);
  if (typeof value === 'object' && value !== null) {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort())
      out[key] = canonical((value as Record<string, unknown>)[key]);
    return out;
  }
  return value;
}

/* The first path at which two canonical values differ, or null. A failing test names where, which a
   500-line object diff does not. */
export function firstDifference(left: unknown, right: unknown, path = '$'): string | null {
  if (Object.is(left, right)) return null;
  if (Array.isArray(left) && Array.isArray(right)) {
    if (left.length !== right.length)
      return `${path}.length ${String(left.length)} != ${String(right.length)}`;
    for (let index = 0; index < left.length; index += 1) {
      const found = firstDifference(left[index], right[index], `${path}[${String(index)}]`);
      if (found) return found;
    }
    return null;
  }
  if (
    typeof left === 'object' &&
    left !== null &&
    typeof right === 'object' &&
    right !== null &&
    !Array.isArray(left) &&
    !Array.isArray(right)
  ) {
    const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
    for (const key of [...keys].sort()) {
      const a = (left as Record<string, unknown>)[key];
      const b = (right as Record<string, unknown>)[key];
      if (!(key in left))
        return `${path}.${key} missing on the left, right has ${JSON.stringify(b)?.slice(0, 80) ?? 'undefined'}`;
      if (!(key in right))
        return `${path}.${key} missing on the right, left has ${JSON.stringify(a)?.slice(0, 80) ?? 'undefined'}`;
      const found = firstDifference(a, b, `${path}.${key}`);
      if (found) return found;
    }
    return null;
  }
  return `${path}: ${JSON.stringify(left)?.slice(0, 120) ?? 'undefined'} != ${JSON.stringify(right)?.slice(0, 120) ?? 'undefined'}`;
}

/* ---- the removed page's VIEW functions, for the rendered-text differential ---- */

export interface LegacyViews extends LegacySessions {
  /** Whether the run minted a terminal-raise capability: the page reads it from a meta tag. */
  setFocusCapability(value: string): void;
  /** `nextSessionsView()` for `payload`. */
  sessionsHtml(payload: unknown): string;
  /** `nextSessionView(project, harness, sid)` for `payload`, the page being on that session's route. */
  sessionHtml(
    payload: unknown,
    route: { project: string; harness?: string; session: string; from?: string },
  ): string;
}

/* The wrappers are what a test loads. `setData` replaces the page's data whatever came before, so it names a
   slot instead of lengthening the history; the view methods set the data themselves. */
export function loadLegacySessions(): LegacySessions {
  return legacyHarness('sessions', {
    slots: { setData: 'data' },
  });
}

export function loadLegacyViews(): LegacyViews {
  return legacyHarness('views', {
    slots: {
      setData: 'data',
      setFocusCapability: 'capability',
      sessionsHtml: 'data',
      sessionHtml: 'data',
    },
  });
}
