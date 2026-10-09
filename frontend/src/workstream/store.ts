import { useSyncExternalStore } from 'react';
import type { BoardRuntime } from '../transport/runtime';
import { createWorkstream, type Workstream } from './model';

/* One tab buffer per runtime. It is fed by the board store, not by a view, because the legacy page
   observes every accepted payload from the first one: a project page opened ten minutes into the tab
   still lists the changes of those ten minutes, and the delegation figure beside it measures them.

   The subscription lives as long as the runtime and is never removed, which is the runtime's own
   lifetime (it and its store are collected together). An observation of a payload whose clock did not
   advance changes nothing, so a repeat (StrictMode, a store notification for the same body) is a no-op.

   `startWorkstream` is what the shell calls at construction; a view that reaches the buffer first starts
   it itself, which then holds the board as it is now and nothing earlier, and says so in the caption. */
const buffers = new WeakMap<object, Workstream>();

export function startWorkstream(runtime: Pick<BoardRuntime, 'store'>): Workstream {
  let buffer = buffers.get(runtime);
  if (!buffer) {
    const created = createWorkstream();
    buffer = created;
    buffers.set(runtime, created);
    const ingest = (): void => {
      const { data } = runtime.store.getSnapshot();
      if (data) created.observe(data);
    };
    ingest();
    runtime.store.subscribe(ingest);
  }
  return buffer;
}

/** The buffer's version, as a store snapshot, so a view redraws when evidence is added and not otherwise. */
export function useWorkstreamVersion(buffer: Workstream): number {
  return useSyncExternalStore(buffer.subscribe, buffer.version);
}
