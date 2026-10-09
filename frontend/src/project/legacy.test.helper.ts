import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

/* The whole legacy page, loaded as the page loads it, for the project differential tests. Every script
   part runs in one context in the order the page assembles them (`page.APP_PARTS`), except the last, which
   starts the refresh loop. The project step ports a view that stands on half the app (the observed model,
   the cockpit, the workstream, the timeline's helpers), and lifting each function out by name would test
   copies; running the real files tests the page. Only the browser objects those files touch at load time
   are stubbed, and the two things another step owns are replaced by a one-line stub each: the stage
   conditions and the steering bar (their owner draws them), and the fetch the cockpit starts for its
   project context (a test seeds the cache it would fill, and no request leaves the sandbox).

   Vitest runs from the repository root. */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

/* page.APP_PARTS without `next-live.js`. */
const PARTS = [
  'next-boot.js',
  'next-observed.js',
  'next-attention.js',
  'next-notify.js',
  'next-cockpit-compat.js',
  'project.js',
  'next-chrome.js',
  'next-capacity.js',
  'next-sessions.js',
  'next-projects.js',
  'next-project.js',
  'next-intent.js',
  'next-activity.js',
  'next-session.js',
  'next-workstream.js',
  'next-delegation.js',
  'next-controls.js',
  'next-cockpit.js',
  'next-render.js',
] as const;

export interface LegacyApp {
  readonly sandbox: Record<string, unknown>;
  /** Replaces the page's `nextData`, and clears the render cache so the model is derived from it. */
  setData(payload: unknown): void;
  /** The page's route, as the fragment names it: `#n=project:alpha%2Fapp:course`. */
  setRoute(fragment: string): void;
  /** Seeds one project-context entry exactly as the cockpit's loader would have stored it. */
  setContext(key: string, entry: { data: unknown; revision: number; error?: true }): void;
  /** Feeds a payload to the page's tab workstream buffer, as `refreshNext` does for each accepted body. */
  observe(payload: unknown): void;
  /** Runs source in the page's own scope: the only way to read a `let` binding or call a lifted constant. */
  run<T = unknown>(source: string, bindings?: Record<string, unknown>): T;
  call<T = unknown>(name: string, ...args: unknown[]): T;
}

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

export function loadLegacyApp(options: { storage?: Record<string, string> } = {}): LegacyApp {
  const store = new Map<string, string>(Object.entries(options.storage ?? {}));
  const document = {
    addEventListener: () => undefined,
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: () => null,
    body: {},
    hidden: false,
    documentElement: {},
    createElement: () => ({}),
  };
  const sandbox: Record<string, unknown> = {
    location: { href: 'http://127.0.0.1:4581/', search: '', hash: '#n=projects' },
    history: { state: null, replaceState: () => undefined },
    document,
    localStorage: {
      getItem: (key: string) => (store.has(key) ? (store.get(key) as string) : null),
      setItem: (key: string, value: string) => void store.set(key, String(value)),
      removeItem: (key: string) => void store.delete(key),
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
    Intl,
    RegExp,
    Error,
    Promise,
    console,
    setTimeout: () => 0,
    clearTimeout: () => undefined,
    setInterval: () => 0,
    clearInterval: () => undefined,
    requestAnimationFrame: () => 0,
    navigator: {},
    matchMedia: () => ({ matches: false, addEventListener: () => undefined }),
    // A request the cockpit starts never answers, so a test that forgot to seed a context sees a pending one.
    fetch: () => new Promise(() => undefined),
  };
  sandbox['window'] = sandbox;
  sandbox['addEventListener'] = () => undefined;
  sandbox['removeEventListener'] = () => undefined;
  vm.createContext(sandbox);
  for (const part of PARTS) vm.runInContext(read(part), sandbox, { filename: part });
  const run = <T = unknown>(source: string, bindings: Record<string, unknown> = {}): T => {
    for (const [name, value] of Object.entries(bindings)) sandbox[`__${name}`] = value;
    return vm.runInContext(source, sandbox) as T;
  };
  // Owned by the steering step: drawn as nothing here, so a comparison reads only what this step draws.
  run(
    'nextStageConditions = () => ""; nextProjectSteer = () => ""; nextObserverModelControls = () => "";',
  );
  return {
    sandbox,
    setData(payload) {
      run('nextData = __payload; nextRenderObserved = null;', { payload });
    },
    setRoute(fragment) {
      run('nextRoute = nextRouteFromFragment(__fragment);', { fragment });
    },
    setContext(key, entry) {
      run('nextCockpitContexts.set(__key, __entry);', { key, entry });
    },
    observe(payload) {
      run('nextObserveWorkstream(__payload);', { payload });
    },
    run,
    call<T>(name: string, ...args: unknown[]): T {
      const fn = sandbox[name];
      if (typeof fn !== 'function') {
        // Top-level `function` declarations live on the context's global object, `const`s do not.
        return run<T>(`${name}(...__args)`, { args });
      }
      return (fn as (...a: unknown[]) => T)(...args);
    },
  };
}

/* HTML as the page would insert it, parsed for the DOM a test then reads. A template, so a fragment that
   is not a document parses as written (a `<tr>` or a bare `<li>` keeps its tags). */
export function parseHtml(html: string): DocumentFragment {
  const template = document.createElement('template');
  template.innerHTML = html;
  return template.content;
}
