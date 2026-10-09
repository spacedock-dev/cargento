import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';
import { legacyHarness } from '../../test/legacy_goldens';

/* The legacy page's workstream evidence store and delegation arithmetic, run as the page runs them, for the
   differential tests. The legacy source is the oracle: the page stays the rollback while this one is built,
   so the port is held to what it computes and not to a description of it. Only the browser objects those
   files touch at load time are stubbed. Vitest runs from the repository root. */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

export interface LegacyDelegation {
  readonly sandbox: Record<string, unknown>;
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

function buildLegacyDelegation(): LegacyDelegation {
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
  for (const file of [
    'next-boot.js',
    'next-observed.js',
    'next-workstream.js',
    'next-delegation.js',
  ]) {
    vm.runInContext(read(file), sandbox, { filename: file });
  }
  const call = <T>(name: string, ...args: unknown[]): T => {
    const fn = sandbox[name];
    if (typeof fn !== 'function') throw new Error(`The legacy page has no ${name}.`);
    return (fn as (...a: unknown[]) => T)(...args);
  };
  return {
    sandbox,
    reset: () =>
      void vm.runInContext(
        `nextWorkstreamGroups = []; nextWorkstreamEntryCount = 0;
         nextWorkstreamPreviousSessions = new Map(); nextWorkstreamSeenAsks = new Map();
         nextWorkstreamLastGenerated = null; nextWorkstreamObservedSince = null;
         nextWorkstreamSeeded = false; nextWorkstreamSeededSince = new Map();`,
        sandbox,
      ),
    observe: (payload) => call('nextObserveWorkstream', payload),
    window: (project) => call('nextWorkstreamProjectWindow', project),
    history: (project) => call('nextObservedHistory', project, call('nextWorkstreamSnapshot')),
    metric: (window) => call('nextDelegationMetric', window),
    trend: (window) => call('nextDelegationTrend', window),
    label: (window) => call('nextWorkstreamWindowLabel', window),
  };
}

export function loadLegacyDelegation(): LegacyDelegation {
  return legacyHarness('delegation', buildLegacyDelegation, {
    pure: ['metric', 'trend', 'label'],
    observe: ['window', 'history'],
    reset: ['reset'],
  });
}
