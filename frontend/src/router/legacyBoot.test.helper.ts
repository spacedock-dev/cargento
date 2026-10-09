import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for the route grammar, as the differential tests ask for it. The answers
   are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. */

export interface LegacyBoot {
  parse(fragment: string): unknown;
  print(route: unknown): string;
  link(session: unknown): string;
}

export function loadLegacyBoot(href = 'http://127.0.0.1:4581/'): LegacyBoot {
  return legacyHarness(`boot:${href}`, {
    pure: ['parse', 'print', 'link'],
  });
}
