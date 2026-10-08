import { useEffect, type ReactNode } from 'react';
import { ControlsContext, type Controls } from './kit';
import { installPopoverDismissal } from './popoverDismissal';

/* The shell builds `controls` once (`createControls`) and mounts this near the
   root. The effects arm the cue timers and the document-level popover handlers;
   each is idempotent and released on cleanup, so StrictMode's effect, cleanup,
   effect leaves exactly one of each. */
export function ControlsProvider({ controls, children }: { readonly controls: Controls; readonly children: ReactNode }) {
  useEffect(() => controls.activate(), [controls]);
  useEffect(() => installPopoverDismissal(document), []);
  return <ControlsContext value={controls}>{children}</ControlsContext>;
}
