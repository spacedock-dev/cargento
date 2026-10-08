import { electionDecision, LEASE_RENEW_MS } from '../storage/lease';
import type { Environment, EventSourceLike, TimerHandle, TransportStorage } from './ports';
import type { RevisionMemo } from './revision';

export const FALLBACK_POLL_MS = 20_000;
export const UNCOORDINATED_POLL_MS = 5000;

export interface LiveDeps {
  readonly env: Environment;
  readonly storage: TransportStorage;
  readonly revisions: RevisionMemo;
  /** A newer revision was announced, by the stream or by another tab. */
  readonly onWake: (revision: string) => void;
  /** The boot read and the safety poll. */
  readonly onPoll: () => void;
}

/* One tab id, at most one EventSource per owner, and a leader chosen through a
   lease in shared storage. The released convergence behaviour is kept, not a
   claim of transactional never-two-stream election: a foreign lease makes a
   current leader yield even when stale, because a throttled leader can wake
   after a foreign claim has gone stale and two hidden tabs must not keep
   streams while stomping the lease. Where storage cannot coordinate, every tab
   leads itself. */
export function createLiveTransport(deps: LiveDeps) {
  const { env, storage, revisions } = deps;
  let source: EventSourceLike | null = null;
  let leader = false;
  let started = false;
  const teardown: (() => void)[] = [];

  function closeStream(): void {
    if (!source) return;
    const closing = source;
    source = null;
    try {
      closing.close();
    } catch {
      /* already gone */
    }
  }

  function openStream(): void {
    if (source || !env.streamSupported) return;
    let opened: EventSourceLike;
    try {
      opened = env.openStream();
    } catch {
      return;
    }
    source = opened;
    // Identity, not truthiness: a source this owner already closed must not act.
    opened.addEventListener('error', () => {
      if (source !== opened || opened.readyState !== 2) return;
      closeStream();
      leader = false;
    });
    opened.addEventListener('revision', (event) => {
      if (source !== opened) return;
      const revision = String(event.data || '');
      if (!revisions.advance(revision)) return;
      storage.writeRevision(revision);
      deps.onWake(revision);
    });
  }

  function elect(): void {
    const lease = storage.readLease();
    if (
      electionDecision({ lease, tabId: env.tabId, isLeader: leader, now: env.clock.now() }) ===
      'yield'
    ) {
      if (leader) closeStream();
      leader = false;
      return;
    }
    storage.writeLease({ id: env.tabId, ts: env.clock.now() });
    leader = true;
    openStream();
  }

  function releaseLease(): void {
    if (leader) storage.removeLease();
  }

  return {
    start(): void {
      if (started) return;
      started = true;
      teardown.push(env.onPageHide(releaseLease));
      teardown.push(env.onBecameVisible(elect));
      teardown.push(
        storage.subscribeRevision((revision) => {
          if (!revisions.advance(revision)) return;
          deps.onWake(revision);
        }),
      );
      deps.onPoll();
      elect();
      const timers: TimerHandle[] = [
        env.clock.setInterval(elect, LEASE_RENEW_MS),
        env.clock.setInterval(
          deps.onPoll,
          env.streamSupported ? FALLBACK_POLL_MS : UNCOORDINATED_POLL_MS,
        ),
      ];
      teardown.push(() => {
        for (const timer of timers) env.clock.clearInterval(timer);
      });
    },
    isLeader: (): boolean => leader,
    dispose(): void {
      if (!started) return;
      started = false;
      for (const undo of teardown.splice(0)) undo();
      closeStream();
      releaseLease();
      leader = false;
    },
  };
}

export type LiveTransport = ReturnType<typeof createLiveTransport>;
