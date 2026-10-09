import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';
import { legacyHarness } from '../../test/legacy_goldens';
import { buildLegacyViews, type LegacyViews } from '../observed/legacy.test.helper';

/* The legacy Intent code, run as the page runs it, for the differential tests. The legacy source is the
   oracle: the page stays the rollback while this one is built, so the port is held to what it computes.
   `next-intent.js` is loaded whole. `next-cockpit.js` is half a megabyte of project and Intent code, so
   its Intent functions are lifted out of it as source text and run unchanged; what is stubbed is stubbed
   because another step owns it. Vitest runs from the repository root. */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

/* One top-level `function name(...)` or `const|let name` declaration, as the text the file holds. A
   function ends at the first column-zero closing brace, a constant at the first line ending in `;` that
   is not inside a continued expression, which is why the declarations lifted here are written that way. */
export function liftSource(file: string, names: readonly string[]): string {
  const text = read(file);
  const pieces: string[] = [];
  for (const name of names) {
    const fn = new RegExp(`\\n(?:async )?function ${name}\\(`).exec(text);
    const constant = new RegExp(`\\n(?:const|let) ${name}\\b`).exec(text);
    const start = fn?.index ?? constant?.index;
    if (start === undefined) throw new Error(`${file} declares no ${name}.`);
    const end = fn ? text.indexOf('\n}\n', start) + 3 : text.indexOf(';\n', start) + 2;
    if (end < start + 3) throw new Error(`Could not find the end of ${name} in ${file}.`);
    pieces.push(text.slice(start, end));
  }
  return pieces.join('\n');
}

export interface LegacyIntent extends LegacyViews {
  /** Runs source in the page's own scope, for the `let` bindings a call cannot reach. */
  run<T = unknown>(source: string, bindings?: Record<string, unknown>): T;
}

export function buildLegacyIntent(): LegacyIntent {
  const views = buildLegacyViews();
  const { sandbox } = views;
  vm.runInContext(
    [
      'const NEXT_FALLBACK_POLL_MS = 20000;',
      liftSource('next-cockpit-compat.js', ['sessKey']),
      'function renderNext(){}',
      liftSource('next-project.js', [
        'nextProjectRevisionLine',
        'nextAnnotationDiscarded',
        'nextAnnotationLines',
        'nextOutcomeLineSource',
        'nextAnnotationDiscardStamp',
        'nextAnnotationDiscardAccount',
      ]),
      liftSource('next-cockpit.js', [
        'nextCockpitAnnotation',
        'NEXT_COCKPIT_HELD_UNSAFE',
        'nextCockpitHeldCap',
        'NEXT_COCKPIT_HELD_CAP',
        'NEXT_COCKPIT_LINES_FULL',
        'NEXT_INTENT_EDITED_ADD',
        'nextCockpitHeldDrafts',
        'nextCockpitHeldOrigins',
        'nextCockpitDirectionLines',
        // The real key, over the views harness's stub, which is not the page's spelling.
        'nextCockpitHeldKey',
        'nextCockpitSavedLines',
        'nextCockpitLinesDraft',
        'nextCockpitLinesOrigins',
        'nextCockpitLinesToSend',
        'nextCockpitLinesChanged',
        'nextCockpitGoalBaseline',
        'nextCockpitIntentChanges',
        'nextIntentChosenOverSaved',
        'nextIntentUnsaved',
        'nextIntentDrafted',
        'nextIntentAdoption',
        'nextCockpitDirectionTooLong',
        'nextCockpitDirectionWhy',
        'nextIntentNoDraftWhy',
        'nextCockpitLineSource',
        'nextDirectionLinesQuestion',
        'nextIntentPromptSelect',
        'nextIntentPromptOptions',
        'nextIntentPromptClip',
        'nextCockpitStableKey',
        'nextCockpitContextKey',
        'nextCockpitFactSessionKey',
        'NEXT_READING_WORK_BY_HARNESS',
        'nextReadingWorkOn',
        'NEXT_COCKPIT_WORK_ROWS',
        'nextCockpitWorkEntries',
        'nextCockpitWorkSource',
        'nextCockpitWorkAbsence',
        'nextCockpitEntryWindow',
        'nextCockpitEntryNumbering',
        'nextCockpitEntryNumbers',
        'nextReadingPersonAuthored',
        'nextCockpitBaselineAt',
        'nextCockpitLaterDirections',
        'nextCockpitConflictCandidates',
      ]),
      // The two closing sentences are owned by `next-boot.js`, already loaded; the view itself is whole.
      read('next-intent.js'),
    ].join('\n'),
    sandbox,
    { filename: 'intent-helpers.js' },
  );
  return {
    ...views,
    run<T>(source: string, bindings: Record<string, unknown> = {}): T {
      for (const [name, value] of Object.entries(bindings)) sandbox[`__${name}`] = value;
      return vm.runInContext(source, sandbox) as T;
    },
  };
}

export function loadLegacyIntent(): LegacyIntent {
  return legacyHarness('intent', buildLegacyIntent, {
    slots: {
      setData: 'data',
      setFocusCapability: 'capability',
      sessionsHtml: 'data',
      sessionHtml: 'data',
    },
  });
}
