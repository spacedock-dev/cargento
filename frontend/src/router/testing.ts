/* Test double for the router's browser surface. Not imported by production code. */
import type { RouterEnvironment } from './router';

/* A history of fragments with the browser's two ways of writing one: assigning `location.hash`
   pushes an entry and queues a `hashchange`, `replaceState` rewrites the current entry and queues
   nothing. `back` and `forward` move the cursor and queue the event, as the browser does. */
export function fakeRouterEnvironment(initial: string) {
  const entries = [initial];
  let cursor = 0;
  const listeners = new Set<() => void>();
  let queued = 0;
  /* `assigned` is every `location.hash = ...` the router made, whether or not the browser would have pushed an
     entry for it: a router that assigns a hash it already shows relies on the browser to ignore it. */
  const calls = {
    push: [] as string[],
    replace: [] as string[],
    assigned: [] as string[],
    scroll: 0,
  };
  const env: RouterEnvironment = {
    getHash: () => entries[cursor] ?? '',
    setHash(fragment) {
      calls.assigned.push(fragment);
      if (fragment === entries[cursor]) return;
      entries.splice(cursor + 1);
      entries.push(fragment);
      cursor += 1;
      calls.push.push(fragment);
      queued += 1;
    },
    replaceHash(fragment) {
      entries[cursor] = fragment;
      calls.replace.push(fragment);
    },
    onHashChange(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    scrollToTop() {
      calls.scroll += 1;
    },
  };
  return {
    env,
    calls,
    entries: () => [...entries],
    cursor: () => cursor,
    listenerCount: () => listeners.size,
    /** The queued `hashchange` events, delivered. */
    flush() {
      while (queued > 0) {
        queued -= 1;
        for (const listener of [...listeners]) listener();
      }
    },
    back() {
      cursor -= 1;
      queued += 1;
    },
    forward() {
      cursor += 1;
      queued += 1;
    },
    /** A reader typing or pasting a fragment into the address bar. */
    type(fragment: string) {
      entries.splice(cursor + 1);
      entries.push(fragment);
      cursor += 1;
      queued += 1;
    },
  };
}
