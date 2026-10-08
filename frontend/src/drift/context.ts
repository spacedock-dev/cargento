import { createContext, useContext } from 'react';
import type { DriftModel } from './model';
import type { DriftCtx } from './state';

/* What the Drift section's parts read, assembled once per render by `DriftProvider`: the model every part
   draws from, and the shell's owners. */
export interface DriftValue {
  readonly ctx: DriftCtx;
  readonly model: DriftModel;
}

export const DriftContext = createContext<DriftValue | null>(null);

export function useDrift(): DriftValue {
  const value = useContext(DriftContext);
  if (!value) throw new Error('A Drift part was rendered outside the Drift provider.');
  return value;
}
