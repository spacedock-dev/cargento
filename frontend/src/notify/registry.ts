import type { BoardRuntime } from '../transport/runtime';
import { createNotifyHost, createNotifyOwner, type NotifyHost, type NotifyOwner } from './owner';

/* One owner per runtime, started by whichever component reaches it first and fed every accepted body from
   then on. The subscription lives as long as the runtime and is never removed, which is the runtime's own
   lifetime (it and its store are collected together), so StrictMode's second effect and a remount find
   the one that exists instead of making a second that would announce everything again.

   The leader question is the transport's: only the tab that holds the live stream raises a stage
   condition, so two open tabs do not both banner one. A runtime without `isLeader` (a test double) is
   never the leader, which raises no stage banner rather than one per tab. */
export type NotifyRuntime = Pick<BoardRuntime, 'store' | 'client'> & {
  readonly isLeader?: () => boolean;
};

export interface NotifyOptions {
  readonly host?: NotifyHost;
  readonly now?: () => number;
}

const owners = new WeakMap<object, NotifyOwner>();
const started = new WeakSet<object>();

/* The owner itself, inert until started: a component reads its control and permission from it while it
   renders, and creating it costs nothing and subscribes to nothing. */
export function notifyOwnerFor(runtime: NotifyRuntime, options: NotifyOptions = {}): NotifyOwner {
  const held = owners.get(runtime);
  if (held) return held;
  const owner = createNotifyOwner({
    host: options.host ?? createNotifyHost(),
    now: options.now ?? (() => Date.now()),
    postLane: async () =>
      (await runtime.client.postLane({ supported: true, permission: 'granted' })).kind === 'ok',
    isLeader: () => runtime.isLeader?.() ?? false,
  });
  owners.set(runtime, owner);
  return owner;
}

/* Starts feeding it every accepted body, once. A body the board already holds when this runs is the
   first one the owner sees, so it primes and raises nothing: arriving at a board is not a transition. */
export function startNotifications(
  runtime: NotifyRuntime,
  options: NotifyOptions = {},
): NotifyOwner {
  const owner = notifyOwnerFor(runtime, options);
  if (started.has(runtime)) return owner;
  started.add(runtime);
  let seen: unknown = null;
  const ingest = (): void => {
    const { data } = runtime.store.getSnapshot();
    if (!data || data === seen) return;
    seen = data;
    owner.sync(data);
  };
  ingest();
  runtime.store.subscribe(ingest);
  return owner;
}
