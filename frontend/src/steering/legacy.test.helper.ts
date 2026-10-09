import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

/* The legacy page's stage conditions, steering bar and tripwires panel, run as the page runs them, for the
   differential tests. The legacy source is the oracle: the page stays the rollback while this one is built.
   Only the browser objects the files touch at load time are stubbed (a Map-backed `localStorage`, the
   document, and `Notification` when a test says the browser has one), plus `renderNext`, which the page's
   handlers call after changing state and which here has nothing to draw. Vitest runs from the repository
   root. */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

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
  for (const file of ['next-boot.js', 'next-notify.js', 'next-delegation.js', 'next-controls.js']) {
    vm.runInContext(read(file), sandbox, { filename: file });
  }
  vm.runInContext('let nextData = null; function renderNext(){}', sandbox);
  const run = (code: string) => vm.runInContext(code, sandbox);
  return {
    storage,
    reset() {
      run('nextStageDrafts.clear();');
    },
    setData(payload) {
      sandbox['__payload'] = payload;
      run('nextData = __payload;');
    },
    setNotification(permission) {
      if (permission === null) delete sandbox['Notification'];
      else sandbox['Notification'] = { permission };
    },
    setStageDraft(id, stage) {
      sandbox['__id'] = id;
      sandbox['__stage'] = stage;
      run('nextStageDrafts.set(__id, __stage);');
    },
    stageHtml(sessions) {
      sandbox['__sessions'] = sessions;
      return run('nextStageConditions(__sessions)') as string;
    },
    steerHtml(project, layout = 'next-steer--bar') {
      sandbox['__project'] = project;
      sandbox['__layout'] = layout;
      return run(
        'nextProjectSteer(__project, nextControlsProjectState(__project), __layout)',
      ) as string;
    },
    guardrailsHtml(project) {
      sandbox['__project'] = project;
      return run('nextProjectGuardrails(__project, nextControlsProjectState(__project))') as string;
    },
    readRules(project) {
      sandbox['__project'] = project;
      return run('nextControlsReadRules(__project)') as unknown[];
    },
  };
}
