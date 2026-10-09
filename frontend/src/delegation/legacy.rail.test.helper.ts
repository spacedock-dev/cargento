import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';
import { legacyHarness } from '../../test/legacy_goldens';

/* The legacy Console rail, run as the page runs it: `nextProjectRail` over `nextObserved`, with the
   workstream's tab memory behind the delegation figure. Only the browser objects the files touch at load
   time are stubbed, plus the page globals the rail reads (`nextData`, the raise flag and the document's
   focus-capability meta). Vitest runs from the repository root. */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

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

function buildLegacyRail(): LegacyRail {
  const storage = new Map<string, string>();
  let capability = '';
  const sandbox: Record<string, unknown> = {
    localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => void storage.set(key, value),
    },
    location: { href: 'http://127.0.0.1:4581/', search: '', hash: '' },
    history: { state: null, replaceState: () => undefined },
    document: {
      addEventListener: () => undefined,
      querySelector: () => (capability ? { getAttribute: () => capability } : null),
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
    'next-sessions.js',
    'next-session.js',
    'next-workstream.js',
    'next-delegation.js',
    'next-capacity.js',
    'next-controls.js',
    'next-notify.js',
  ]) {
    vm.runInContext(read(file), sandbox, { filename: file });
  }
  vm.runInContext(
    `let nextData = null; let nextRaiseInFlight = false; function renderNext(){}
     const nextCockpitAnnouncedCues = new Set(); function nextCockpitAnnounceCue(){}`,
    sandbox,
  );
  const run = (code: string) => vm.runInContext(code, sandbox);
  return {
    reset: () =>
      void run(
        `nextWorkstreamGroups = []; nextWorkstreamEntryCount = 0;
         nextWorkstreamPreviousSessions = new Map(); nextWorkstreamSeenAsks = new Map();
         nextWorkstreamLastGenerated = null; nextWorkstreamObservedSince = null;
         nextWorkstreamSeeded = false; nextWorkstreamSeededSince = new Map();
         nextControlsProjects = new Map(); nextData = null;`,
      ),
    observe(payload) {
      sandbox['__payload'] = payload;
      run('nextObserveWorkstream(__payload)');
    },
    setCapability(value) {
      capability = value;
    },
    projects(payload) {
      sandbox['__payload'] = payload;
      return run(
        'nextData = __payload; nextObserved(__payload, nextWorkstreamSnapshot()).projects.map(p => p.key)',
      ) as string[];
    },
    rail(payload, project) {
      sandbox['__payload'] = payload;
      sandbox['__project'] = project;
      return run(
        `nextData = __payload;
         (() => {
           const model = nextObserved(__payload, nextWorkstreamSnapshot());
           return nextProjectRail({payload: __payload, model,
             project: model.projects.find(p => p.key === __project)});
         })()`,
      ) as string;
    },
  };
}

export function loadLegacyRail(): LegacyRail {
  return legacyHarness('rail', buildLegacyRail, {
    observe: ['projects', 'rail'],
    slots: { setCapability: 'capability' },
    reset: ['reset'],
  });
}
