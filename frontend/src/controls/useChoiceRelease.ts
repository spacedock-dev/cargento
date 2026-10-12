import { useEffect } from 'react';
import { installChoiceRelease, type DisplayGate } from './displayGate';

/* One popup-state observer per mounted page, removed on cleanup. */
export function useChoiceRelease(gate: DisplayGate): void {
  useEffect(() => installChoiceRelease(document, gate), [gate]);
}
