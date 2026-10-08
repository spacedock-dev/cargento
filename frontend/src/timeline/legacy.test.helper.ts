import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

/* The legacy page's semantic timeline and activity filter, run as the page runs them, for the differential
   tests. The legacy source is the oracle: the page stays the rollback while this one is built, so the port
   is held to what `project.js` computes and not to a description of it. Only what the file touches at load
   time is stubbed: a Map-backed `localStorage` the filter writes to, the document, and the three helpers the
   cockpit's compatibility seam (`next-cockpit-compat.js`) supplies. Vitest runs from the repository root. */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

export interface LegacyTimeline {
  readonly storage: Map<string, string>;
  /** `nextRoute` and `projectQuerySession`, the two globals the filter's scope reads. */
  setScope(project: string, session: string | null): void;
  reload(): void;
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

export function loadLegacyTimeline(): LegacyTimeline {
  const storage = new Map<string, string>();
  const localStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => void storage.set(key, value),
    removeItem: (key: string) => void storage.delete(key),
  };
  const sandbox: Record<string, unknown> = {
    localStorage,
    location: { href: 'http://127.0.0.1:4581/', search: '', hash: '' },
    document: { addEventListener: () => undefined, getElementById: () => null },
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
    esc: (value: unknown) =>
      String(value == null ? '' : value).replace(
        /[&<>"']/g,
        (c) => `&#${String(c.charCodeAt(0))};`,
      ),
    sessKey: (session: { harness?: unknown; sid?: unknown; session?: unknown } | null) =>
      `${String(session?.harness || '')}:${String(session?.sid || session?.session || '')}`,
    fmtDur: (seconds: number) => `${String(Math.round(Number(seconds)))}s`,
  };
  vm.createContext(sandbox);
  const source = readFileSync(resolve(process.cwd(), WEB, 'project.js'), 'utf8');
  const load = () => vm.runInContext(source, sandbox, { filename: 'project.js' });
  load();
  return {
    storage,
    setScope(project, session) {
      sandbox['__project'] = project;
      sandbox['__session'] = session;
      vm.runInContext(
        'nextRoute = {view:"project", project:__project}; projectQuerySession = __session;',
        sandbox,
      );
    },
    reload() {
      // A reload is a new page: the module state is gone and only `localStorage` remains.
      vm.runInContext('projectGraphModeBySession.clear(); projectLoadGraphModes();', sandbox);
    },
    timeline(data, model, delegations, focus, origins, options) {
      const fn = sandbox['projectSemanticTimeline'] as (...args: unknown[]) => string;
      return fn(data, model, delegations, focus, origins, options);
    },
    setGraphMode: (mode) => (sandbox['projectSetGraphMode'] as (m: string) => boolean)(mode),
    resolveGraphMode: (options) =>
      (sandbox['projectResolveGraphMode'] as (o?: unknown) => string)(options),
  };
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
