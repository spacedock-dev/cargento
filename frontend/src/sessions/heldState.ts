import { useSyncExternalStore } from 'react';

/* Two small stores the session screens keep outside the rendered tree, because the board redraws on every
   revision and a value held by a node would go with it: the answer notes (what a failed answer said, by
   request) and the goal-focus request (a goal link was pressed, and the session page it opens is to put
   focus on the goal when it draws). Each is keyed by the owner it belongs to, so a second shell in a test
   or after a hot update never shares state with the first. */

export interface ValueStore<T> {
  get(): T;
  subscribe(listener: () => void): () => void;
}

function createStore<T>(initial: T) {
  let value = initial;
  const listeners = new Set<() => void>();
  return {
    get: (): T => value,
    set(next: T): void {
      if (Object.is(next, value)) return;
      value = next;
      for (const listener of [...listeners]) listener();
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export type AnswerNotes = ReturnType<typeof createAnswerNotes>;

/* What a request's last answer press said, held by the request's id until the board no longer carries the
   request. Only the failure sentence is kept: a confirmed answer retires the question and needs none. The
   map is replaced on every change, so a subscriber sees a new object and an unchanged one costs nothing. */
export function createAnswerNotes() {
  const store = createStore<ReadonlyMap<string, string>>(new Map());
  return {
    ...store,
    set(id: string, note: string): void {
      const next = new Map(store.get());
      next.set(id, note);
      store.set(next);
    },
    delete(id: string): void {
      if (!store.get().has(id)) return;
      const next = new Map(store.get());
      next.delete(id);
      store.set(next);
    },
    /** Forget the notes of requests the board no longer carries, so a note never outlives its question. */
    prune(live: ReadonlySet<string>): void {
      const kept = [...store.get()].filter(([id]) => live.has(id));
      if (kept.length !== store.get().size) store.set(new Map(kept));
    },
  };
}

const notesByOwner = new WeakMap<object, AnswerNotes>();

export function answerNotesFor(owner: object): AnswerNotes {
  let notes = notesByOwner.get(owner);
  if (!notes) {
    notes = createAnswerNotes();
    notesByOwner.set(owner, notes);
  }
  return notes;
}

export function useStore<T>(store: ValueStore<T>): T {
  return useSyncExternalStore(store.subscribe, store.get);
}

export interface GoalFocusTarget {
  readonly harness: string;
  readonly sid: string;
}

export type GoalFocus = ReturnType<typeof createGoalFocus>;

/* A press on a row's goal link opens the session and asks for focus on its goal. The request is
   consumed by the first panel that draws for that exact session, once, so a later visit to the page does
   not move focus unasked. */
export function createGoalFocus() {
  const store = createStore<GoalFocusTarget | null>(null);
  return {
    ...store,
    request(target: GoalFocusTarget): void {
      store.set({ harness: target.harness, sid: target.sid });
    },
    /** True exactly once for a pending request that names this session. */
    take(target: GoalFocusTarget): boolean {
      const held = store.get();
      if (!held || held.harness !== target.harness || held.sid !== target.sid) return false;
      store.set(null);
      return true;
    },
  };
}

const goalFocusByOwner = new WeakMap<object, GoalFocus>();

export function goalFocusFor(owner: object): GoalFocus {
  let focus = goalFocusByOwner.get(owner);
  if (!focus) {
    focus = createGoalFocus();
    goalFocusByOwner.set(owner, focus);
  }
  return focus;
}
