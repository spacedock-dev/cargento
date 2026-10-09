import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';
import { legacyHarness } from '../../test/legacy_goldens';

/* The legacy page's route code, run as the page runs it, for the differential tests. `next-boot.js` is the
   oracle the port is held to, because the legacy page stays the rollback while this one is built. Only the
   browser objects the file touches are stubbed. Vitest runs from the repository root. */
function buildLegacyBoot(href: string) {
  const source = readFileSync(
    resolve(process.cwd(), 'cargento/skills/cargento/cargento_runtime/web/next-boot.js'),
    'utf8',
  );
  const location = { href, search: '', hash: '#n=sessions' };
  const sandbox: Record<string, unknown> = {
    location,
    history: { state: null, replaceState: () => undefined },
    URLSearchParams,
    encodeURIComponent,
    decodeURIComponent,
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return {
    location,
    parse: sandbox['nextRouteFromFragment'] as (fragment: string) => unknown,
    print: sandbox['nextFragmentForRoute'] as (route: unknown) => string,
    link: sandbox['nextSessionLink'] as (session: unknown) => string,
  };
}

export interface LegacyBoot {
  parse(fragment: string): unknown;
  print(route: unknown): string;
  link(session: unknown): string;
}

export function loadLegacyBoot(href = 'http://127.0.0.1:4581/'): LegacyBoot {
  return legacyHarness(`boot:${href}`, () => buildLegacyBoot(href), {
    pure: ['parse', 'print', 'link'],
  });
}
