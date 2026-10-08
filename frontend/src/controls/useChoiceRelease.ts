import { useEffect } from 'react';
import { installChoiceRelease, type DisplayGate } from './displayGate';

/* Document-level `change` and `blur` listeners, installed on mount and removed on
   cleanup; StrictMode's second effect leaves exactly one pair. */
export function useChoiceRelease(gate: DisplayGate): void {
  useEffect(() => installChoiceRelease(document, gate), [gate]);
}
