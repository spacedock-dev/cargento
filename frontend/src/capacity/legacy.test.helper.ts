import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';
import { legacyHarness } from '../../test/legacy_goldens';

/* The legacy capacity strip and its consent, run as the page runs them, for the differential tests. The
   legacy source is the oracle: the page stays the rollback while this one is built, so the port is held to
   what it computes and not to a description of it. Only the browser objects the files touch at load time
   are stubbed, plus the page globals the strip reads (`nextData` for the harness labels). */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

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

function buildLegacyCapacity(): LegacyCapacity {
  const storage = new Map<string, string>();
  const sandbox: Record<string, unknown> = {
    localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => void storage.set(key, value),
    },
    location: { href: 'http://127.0.0.1:4581/', search: '', hash: '' },
    history: { state: null, replaceState: () => undefined },
    document: {
      addEventListener: () => undefined,
      querySelector: () => null,
      getElementById: () => null,
    },
    URLSearchParams,
    encodeURIComponent,
    decodeURIComponent,
    Date,
    Math,
    JSON,
    Number,
    String,
    Array,
    Object,
    Set,
    Map,
  };
  vm.createContext(sandbox);
  for (const file of ['next-boot.js', 'next-capacity.js'])
    vm.runInContext(read(file), sandbox, { filename: file });
  vm.runInContext('let nextData = null; function renderNext(){} function refreshNext(){}', sandbox);
  const run = <T>(code: string): T => vm.runInContext(code, sandbox) as T;
  const call = <T>(name: string, ...args: unknown[]): T => {
    const fn = sandbox[name];
    if (typeof fn !== 'function') throw new Error(`The legacy page has no ${name}.`);
    return (fn as (...a: unknown[]) => T)(...args);
  };
  const setConsent = (consent: LegacyConsent) => {
    storage.clear();
    run('nextUsageConsentMemo = null');
    if (consent) call('nextSetUsageConsent', consent);
  };
  return {
    rows: (payload) => call('nextCapacityRows', payload),
    models: (raw) => call('nextCapacityModels', raw),
    clock: (stamp, generated) => call('nextCapacityClock', stamp, generated),
    view(payload, state) {
      setConsent(state.consent);
      sandbox['__payload'] = payload;
      run('nextData = __payload');
      run(`nextCapacitySelectedKey = ${JSON.stringify(state.selected)}`);
      return call('nextCapacityView', payload);
    },
    rail(payload, consent) {
      setConsent(consent);
      return (
        call<string>('nextUsageDisclosure', payload) + call<string>('nextUsageSwitch', payload)
      );
    },
    spread(payload, harness) {
      return call('nextCapacityProjectSpread', payload, harness);
    },
    selected: () => run('nextCapacitySelectedKey'),
  };
}

export function loadLegacyCapacity(): LegacyCapacity {
  return legacyHarness('capacity', buildLegacyCapacity, {
    // `view` and `rail` set the consent and the data they draw from, so their answers depend on their
    // arguments alone; `view` also leaves the selection `selected()` reads.
    pure: ['rows', 'models', 'clock', 'view', 'rail', 'spread'],
    slots: { view: 'drawn' },
    observe: ['selected'],
  });
}
