import type { Clock, TimerHandle } from '../transport/ports';

/* A board that never repaints is a worse failure than a list that closes.
   Twelve consecutive deferrals is a minute at the uncoordinated poll and far
   longer than choosing from a list takes; past that the reader has left the
   control focused rather than used it, and the board catches up. */
export const MAX_DEFERRED_COMMITS = 12;

/* A disclosure eases for 200 ms (the CSS duration); a background commit that
   lands inside that window would snap the motion halfway. 220 leaves the frame
   after it. */
export const MOTION_HOLD_MS = 220;

export interface CommitGateOptions<T> {
  /** True while something the commit would destroy is mid-choice, such as an open native <select>. */
  readonly isHeld: () => boolean;
  readonly commit: (payload: T) => void;
  readonly maxDeferred?: number;
}

/* The store accepts data the moment it arrives; this decides when a consumer
   shows it. The count is of consecutive deferrals, not per poll, and it is NOT
   reset by a commit past the cap while the choice is still held: resetting
   there re-arms the cap, so the board would repaint once every thirteen polls
   instead of resuming. It clears only when the interaction ends (`release`
   with a commit waiting) or an arrival finds nothing held. */
export function createCommitGate<T>(options: CommitGateOptions<T>) {
  const max = options.maxDeferred ?? MAX_DEFERRED_COMMITS;
  let count = 0;
  let pending: { readonly payload: T } | null = null;
  return {
    submit(payload: T, flags: { readonly manual?: boolean } = {}): 'committed' | 'deferred' {
      if (!flags.manual && options.isHeld()) {
        if (count < max) {
          count += 1;
          pending = { payload };
          return 'deferred';
        }
        pending = null;
      } else {
        pending = null;
        count = 0;
      }
      options.commit(payload);
      return 'committed';
    },
    /** `change` and `blur`: the newest deferred payload commits once. */
    release(): boolean {
      const waiting = pending;
      if (!waiting) return false;
      pending = null;
      count = 0;
      options.commit(waiting.payload);
      return true;
    },
    hasPending: (): boolean => pending !== null,
    deferredCount: (): number => count,
  };
}

export type CommitGate<T> = ReturnType<typeof createCommitGate<T>>;

export interface MotionHoldOptions {
  readonly clock: Clock;
  readonly reducedMotion: () => boolean;
}

export function createMotionHold(options: MotionHoldOptions) {
  let until = 0;
  let held: { paint: () => void } | null = null;
  let timer: TimerHandle | null = null;
  return {
    noteToggle(): void {
      if (!options.reducedMotion()) until = options.clock.now() + MOTION_HOLD_MS;
    },
    /** A background paint. One that follows a reader's own action never goes through here. */
    paint(paint: () => void): void {
      const wait = until - options.clock.now();
      if (wait <= 0 && !held) {
        paint();
        return;
      }
      if (held) {
        held.paint = paint;
        return;
      }
      held = { paint };
      timer = options.clock.setTimeout(
        () => {
          const waiting = held;
          held = null;
          timer = null;
          waiting?.paint();
        },
        Math.max(0, wait),
      );
    },
    dispose(): void {
      if (timer !== null) options.clock.clearTimeout(timer);
      timer = null;
      held = null;
    },
  };
}

export type MotionHold = ReturnType<typeof createMotionHold>;
