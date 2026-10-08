import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

/* The legacy page's observed model and the two session parts that stand on it, run as the page runs
   them, for the differential tests. The legacy source is the oracle: the page stays the rollback while
   this one is built, so the port is held to what it computes, never to a description of it. Only the
   browser objects those files touch at load time are stubbed. Vitest runs from the repository root.

   One thing is replaced rather than run: `nextObservedHistory`, the workstream and delegation windows
   a project row carries. Those belong to the project step, which ports `next-workstream.js` and
   `next-delegation.js` with their own oracle; loading them here would test code this port does not
   hold. A project's history keys are therefore dropped from the comparison (`PROJECT_HISTORY_KEYS`). */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

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
  readonly sandbox: Record<string, unknown>;
  /** Sets the page's `nextData` and `nextRoute`, the two globals its functions read. */
  setData(payload: unknown): void;
  call<T = unknown>(name: string, ...args: unknown[]): T;
}

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

export function loadLegacySessions(href = 'http://127.0.0.1:4581/'): LegacySessions {
  const location = { href, search: '', hash: '#n=sessions' };
  const sandbox: Record<string, unknown> = {
    location,
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
  for (const file of ['next-boot.js', 'next-observed.js', 'next-sessions.js', 'next-session.js']) {
    vm.runInContext(read(file), sandbox, { filename: file });
  }
  // `let nextData` lives in next-chrome.js, which this harness does not load; the parts below read it.
  vm.runInContext('let nextData = null; let nextWorkstreamPayloadEvidence = () => ({});', sandbox);
  vm.runInContext('nextObservedHistory = () => ({});', sandbox);
  return {
    sandbox,
    setData(payload) {
      sandbox['__payload'] = payload;
      vm.runInContext('nextData = __payload;', sandbox);
    },
    call<T>(name: string, ...args: unknown[]): T {
      const fn = sandbox[name];
      if (typeof fn !== 'function') throw new Error(`The legacy page has no ${name}.`);
      return (fn as (...a: unknown[]) => T)(...args);
    },
  };
}

/* A structural form that keeps what a JSON round trip would hide: `undefined` against absent, `NaN`,
   `-0`, and the order of an array (an object's key order is sorted away, since no reader sees it).
   Objects built in the sandbox have the sandbox's prototypes, so equality cannot be `toEqual`'s. */
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

/* ---- the legacy VIEW functions, for the rendered-text differential ----

   `nextSessionsView` and `nextSessionView` build HTML from the parts above plus a handful of helpers that
   live in files this harness does not load whole (`next-cockpit.js` is half a megabyte of project and
   Intent code). Those helpers are lifted out of their own files as source text and run unchanged, so the
   code that runs is the page's, not a copy of it. What is stubbed is stubbed because its owner is a later
   step: the capacity strip, and the drift block beside the session page's activity column. */
function liftSource(file: string, names: readonly string[]): string {
  const text = read(file);
  const pieces: string[] = [];
  for (const name of names) {
    const fn = new RegExp(`\\nfunction ${name}\\(`).exec(text);
    const constant = new RegExp(`\\n(?:const|let) ${name}\\b`).exec(text);
    const start = fn?.index ?? constant?.index;
    if (start === undefined) throw new Error(`${file} declares no ${name}.`);
    const end = fn ? text.indexOf('\n}\n', start) + 3 : text.indexOf(';\n', start) + 2;
    if (end < start + 3) throw new Error(`Could not find the end of ${name} in ${file}.`);
    pieces.push(text.slice(start, end));
  }
  return pieces.join('\n');
}

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

export function loadLegacyViews(): LegacyViews {
  const base = loadLegacySessions();
  const { sandbox } = base;
  let capability = '';
  (sandbox['document'] as Record<string, unknown>)['querySelector'] = () =>
    capability ? { getAttribute: () => capability } : null;
  vm.runInContext(
    [
      'let nextRenderObserved = null;',
      'let nextRaiseInFlight = false;',
      'const nextPending = new Map();',
      'const nextCockpitDisclosureStates = new Map();',
      'const nextIntentChosenPrompts = new Map();',
      // The two stubs whose owner is a later step.
      'function nextCapacityView(){ return ""; }',
      // The panel, the activity list and the pill are the Intent step's; the record under the activity column
      // (how it landed, and where a raise is kept) is drawn from the observed model, so it runs for real.
      `function nextCockpitDriftBlock(group, session){
        const observed = nextCurrentObserved().sessions.find(row => nextSessionKey(row) === nextSessionKey(session) &&
          row.project === String(session.project == null ? "" : session.project));
        const record = nextData && nextData.annotate === true ? nextCockpitLanded(observed) + nextCockpitDeparturesKept() : "";
        return {panel: "", list: "", record, pill: "", count: null};
      }`,
      'function nextWorkstreamSnapshot(){ return {}; }',
      'function nextCockpitStoreUnreadable(){ return String(nextData && nextData.annotate_unreadable || ""); }',
      'function nextCockpitHeldKey(session, kind){ return kind + ":" + (session && session.sid); }',
    ].join('\n'),
    sandbox,
  );
  const lifted = [
    liftSource('next-chrome.js', [
      'nextRows',
      'nextCurrentObserved',
      'nextRouteToken',
      'nextSessionHome',
    ]),
    liftSource('next-controls.js', ['nextPendingHas', 'nextPendingAttrs', 'nextPendingLabel']),
    liftSource('next-project.js', ['NEXT_OUTCOME_LINES_MAX']),
    liftSource('next-cockpit.js', [
      'nextCockpitDisclosureAttr',
      'nextCockpitWhy',
      'nextCockpitHumanLabel',
      'NEXT_PROMPT_CHOSEN',
      'NEXT_PROMPT_SOURCES',
      'NEXT_READING_CLAIMS',
      'NEXT_READING_OUTCOME_LINE',
      'NEXT_READING_ASSESSMENT_KEYS',
      'nextReadingIsOutcomeLine',
      'nextReadingNamesConstraint',
      'nextIntentOpenedWithControl',
      'nextPromptCandidate',
      'nextIntentDraft',
      'nextIntentPromptChoices',
      'nextIntentChoicesSettled',
      'nextCockpitLanded',
      'nextCockpitDeparturesKept',
    ]),
  ].join('\n');
  // `nextCockpitContexts` is the project step's cache; an empty one is "no context loaded yet".
  vm.runInContext(
    `const nextCockpitContexts = new Map(); const nextIntentPromptLists = new Map();\n${lifted}`,
    sandbox,
    { filename: 'lifted-helpers.js' },
  );
  return {
    ...base,
    setFocusCapability(value) {
      capability = value;
    },
    sessionsHtml(payload) {
      base.setData(payload);
      return base.call<string>('nextSessionsView');
    },
    sessionHtml(payload, route) {
      base.setData(payload);
      sandbox['__route'] = route;
      vm.runInContext(
        'nextRoute = Object.assign({view: "session", project: "", session: ""}, __route);',
        sandbox,
      );
      return base.call<string>('nextSessionView', route.project, route.harness, route.session);
    },
  };
}
