import vm from 'node:vm';
import { liftSource, loadLegacyIntent, type LegacyIntent } from '../intent/legacy.test.helper';

/* The legacy Drift code, run as the page runs it, for the differential tests. The Intent harness is the base
   (the page's observed record, the Intent drafts and the shared helpers); the reading, result, route and
   drift functions are lifted out of `next-cockpit.js` as source text and run unchanged. A name the base
   already declared is skipped, so a lift list can name everything a function needs without caring who
   brought it first. */
export interface LegacyDrift extends LegacyIntent {
  /** Declares the named top-level functions and constants from `next-cockpit.js` that the page has not. */
  lift(names: readonly string[], file?: string): void;
}

export function loadLegacyDrift(): LegacyDrift {
  const base = loadLegacyIntent();
  return {
    ...base,
    lift(names, file = 'next-cockpit.js') {
      const fresh = names.filter((name) => {
        try {
          return base.run<string>(`typeof ${name}`) === 'undefined';
        } catch {
          return false;
        }
      });
      if (!fresh.length) return;
      vm.runInContext(
        liftSource(file, fresh),
        (base as unknown as { sandbox: vm.Context }).sandbox,
        {
          filename: `lifted-drift-${fresh[0] ?? 'none'}.js`,
        },
      );
    },
  };
}
