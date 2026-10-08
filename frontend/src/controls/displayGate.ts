import type { BoardSnapshot, BoardStore } from '../store/board';
import { createCommitGate, createMotionHold } from '../store/commit-gate';
import type { Clock } from '../transport/ports';

/* The fields a poll replaces. They reach a reader only through `paint`, so the
   two holds below can keep the old board on screen while the store has already
   accepted the new one. Everything else in a snapshot is the reader's own
   action state or a project-context read and is not held by an open list. */
type BoardLayer = Pick<
  BoardSnapshot,
  'data' | 'revision' | 'acceptedCount' | 'failures' | 'lastFailure' | 'lastSuccessAt' | 'firstBuild'
>;

function boardLayer(snapshot: BoardSnapshot): BoardLayer {
  return {
    data: snapshot.data,
    revision: snapshot.revision,
    acceptedCount: snapshot.acceptedCount,
    failures: snapshot.failures,
    lastFailure: snapshot.lastFailure,
    lastSuccessAt: snapshot.lastSuccessAt,
    firstBuild: snapshot.firstBuild,
  };
}

export interface DisplayGateOptions {
  readonly clock: Clock;
  readonly reducedMotion: () => boolean;
  /** An option list is open: a native <select> inside the page holds focus. */
  readonly isChoiceOpen: () => boolean;
}

/* What a reader is shown, as a view over the board store. The store accepts data
   the moment it arrives; this decides when a consumer shows it, with the two
   retained deferrals of docs/design-reader-state.md and nothing else:

   - An open <select> cannot be put back after a redraw (no key, no API reopens
     it), so a background paint waits while one holds focus: at most twelve in a
     row, then the board paints again, and `change` or `blur` catches up once.
     A manual refresh paints over an open list, because the reader pressed the
     thing that redraws.
   - A disclosure the reader just toggled eases for 200 ms; a background paint
     inside that window is held 220 ms and coalesced to the newest, and reduced
     motion holds nothing. The catch-up after a list closes is the reader's own
     moment, so it never waits for motion.

   Install `paint` as the runtime's paint option and `attach` the runtime's
   store. Nothing in here fetches, polls or opens a stream. */
export function createDisplayGate(options: DisplayGateOptions) {
  const listeners = new Set<() => void>();
  const outstanding = new Set<() => void>();
  let store: BoardStore | null = null;
  let displayed: BoardSnapshot | null = null;
  let board: BoardLayer | null = null;
  let releasing = false;

  const motion = createMotionHold({ clock: options.clock, reducedMotion: options.reducedMotion });

  function show(next: BoardSnapshot): void {
    displayed = next;
    for (const listener of [...listeners]) listener();
  }

  /* The board layer is carried over from what is already shown, so a change to
     anything else cannot smuggle a held poll onto the screen. */
  function showOthers(): void {
    if (!store || !board) return;
    show({ ...store.getSnapshot(), ...board });
  }

  function applyBoard(): void {
    if (!store) return;
    const snapshot = store.getSnapshot();
    board = boardLayer(snapshot);
    show(snapshot);
  }

  /* Every awaited paint a toggle is holding. The motion hold keeps only the
     newest paint function, so the older runs' waiters are released with it, not
     left pending behind a closure that was replaced. */
  const heldDones = new Set<() => void>();
  function paintHeld(): void {
    applyBoard();
    for (const done of [...heldDones]) done();
    heldDones.clear();
  }

  const gate = createCommitGate<() => void>({
    isHeld: options.isChoiceOpen,
    commit: (done) => {
      if (releasing) {
        applyBoard();
        done();
        return;
      }
      heldDones.add(done);
      motion.paint(paintHeld);
    },
  });

  return {
    /** The runtime's store. Returns the detach function. */
    attach(next: BoardStore): () => void {
      store = next;
      const initial = next.getSnapshot();
      board = boardLayer(initial);
      displayed = initial;
      let last = initial;
      const unsubscribe = next.subscribe(() => {
        const current = next.getSnapshot();
        const contextsChanged = current.contexts !== last.contexts;
        const othersChanged =
          contextsChanged ||
          current.manualRefreshing !== last.manualRefreshing ||
          current.observer !== last.observer ||
          current.pending !== last.pending;
        last = current;
        // A poll's own fields reach the reader only through `paint`.
        if (!othersChanged) return;
        if (contextsChanged) motion.paint(showOthers);
        else showOthers();
      });
      return () => {
        unsubscribe();
        if (store === next) store = null;
      };
    },

    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot(): BoardSnapshot {
      if (!displayed) throw new Error('The display gate has no store attached.');
      return displayed;
    },

    /* The runtime's `paint` option. Resolves when the result is shown, which a
       reader's own toggle can hold, or at once when an open list defers it. */
    paint(info: { readonly manual: boolean; readonly accepted: boolean }): Promise<void> {
      return new Promise<void>((resolve) => {
        const done = () => {
          outstanding.delete(done);
          resolve();
        };
        outstanding.add(done);
        if (gate.submit(done, { manual: info.manual }) === 'deferred') done();
      });
    },

    /** A reader's own disclosure toggle began. */
    noteToggle: (): void => motion.noteToggle(),

    /** `change` or `blur` on a select: the newest deferred paint is shown once. */
    releaseChoice(): boolean {
      releasing = true;
      try {
        return gate.release();
      } finally {
        releasing = false;
      }
    },

    hasPending: (): boolean => gate.hasPending(),
    deferredCount: (): number => gate.deferredCount(),

    dispose(): void {
      motion.dispose();
      heldDones.clear();
      for (const done of [...outstanding]) done();
      listeners.clear();
    },
  };
}

export type DisplayGate = ReturnType<typeof createDisplayGate>;

/** True while a native <select> inside `root` holds focus, which is when its option list may be open. */
export function choiceOpenIn(root: () => Element | null, doc: Document = document): boolean {
  const active = doc.activeElement;
  if (!active || active.tagName !== 'SELECT') return false;
  return root()?.contains(active) === true;
}

/* `change` as well as `blur`, because a keyboard selection commits without the
   list losing focus and the reader should see the board catch up then, not on the
   next poll. Capture, because `blur` does not bubble. */
export function installChoiceRelease(doc: Document, gate: Pick<DisplayGate, 'releaseChoice'>): () => void {
  const onChange = (event: Event) => {
    if (event.target instanceof HTMLSelectElement) gate.releaseChoice();
  };
  doc.addEventListener('change', onChange);
  doc.addEventListener('blur', onChange, true);
  return () => {
    doc.removeEventListener('change', onChange);
    doc.removeEventListener('blur', onChange, true);
  };
}
