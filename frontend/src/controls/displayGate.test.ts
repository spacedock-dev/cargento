import { describe, expect, it, vi } from 'vitest';
import { createBoardStore } from '../store/board';
import { MAX_DEFERRED_COMMITS, MOTION_HOLD_MS } from '../store/commit-gate';
import { createFakeClock } from '../transport/testing';
import { createDisplayGate } from './displayGate';

function setup(options: { reduced?: boolean } = {}) {
  const clock = createFakeClock();
  const held = { choice: false, reduced: options.reduced === true };
  const store = createBoardStore({ now: clock.now });
  const gate = createDisplayGate({
    clock,
    reducedMotion: () => held.reduced,
    isChoiceOpen: () => held.choice,
  });
  const detach = gate.attach(store);
  let generation = 0;
  /* The runtime's own order: the store accepts at once, then asks the consumer to paint. */
  const arrive = (flags: { manual?: boolean } = {}) => {
    generation += 1;
    store.acceptData({ generated: generation }, `1.${String(generation)}`);
    return gate.paint({ manual: flags.manual === true, accepted: true });
  };
  return {
    clock,
    held,
    store,
    gate,
    detach,
    arrive,
    shown: () => gate.getSnapshot().data?.generated ?? 0,
  };
}

describe("the display gate: acceptance is immediate, paint is the reader's to hold", () => {
  it('shows what the store held at attach, and nothing newer until a paint', async () => {
    const { shown, arrive, store } = setup();
    expect(shown()).toBe(0);
    const painted = arrive();
    expect(store.getSnapshot().acceptedCount).toBe(1);
    await painted;
    expect(shown()).toBe(1);
  });

  it('commits at once when nothing is held, and tells subscribers once', async () => {
    const { gate, arrive } = setup();
    const listener = vi.fn();
    gate.subscribe(listener);
    await arrive();
    expect(listener).toHaveBeenCalledOnce();
  });

  it('defers up to twelve background paints while a native select is open, then keeps painting without re-arming', async () => {
    const { held, arrive, shown, store, gate } = setup();
    held.choice = true;
    expect(MAX_DEFERRED_COMMITS).toBe(12);
    for (let attempt = 1; attempt <= MAX_DEFERRED_COMMITS; attempt += 1) {
      await arrive();
      expect(shown(), `attempt ${String(attempt)}`).toBe(0);
    }
    expect(store.getSnapshot().acceptedCount).toBe(12);
    expect(gate.hasPending()).toBe(true);
    await arrive();
    expect(shown()).toBe(13);
    await arrive();
    expect(shown()).toBe(14);
  });

  it('catches up exactly once, to the newest payload, when the list closes', async () => {
    const { held, arrive, shown, gate } = setup();
    held.choice = true;
    await arrive();
    await arrive();
    await arrive();
    const listener = vi.fn();
    gate.subscribe(listener);
    held.choice = false;
    expect(gate.releaseChoice()).toBe(true);
    expect(shown()).toBe(3);
    expect(listener).toHaveBeenCalledOnce();
    expect(gate.releaseChoice()).toBe(false);
    expect(listener).toHaveBeenCalledOnce();
    expect(gate.deferredCount()).toBe(0);
  });

  it('lets a manual refresh paint over an open list, and drops the deferral it answers', async () => {
    const { held, arrive, shown, gate } = setup();
    held.choice = true;
    await arrive();
    await arrive();
    await arrive({ manual: true });
    expect(shown()).toBe(3);
    expect(gate.hasPending()).toBe(false);
    expect(gate.releaseChoice()).toBe(false);
  });

  it("holds a background paint behind the reader's own toggle and coalesces to the newest", async () => {
    const { clock, arrive, shown, gate } = setup();
    gate.noteToggle();
    const first = arrive();
    clock.advance(100);
    const newest = arrive();
    expect(shown()).toBe(0);
    clock.advance(MOTION_HOLD_MS - 100);
    await Promise.all([first, newest]);
    expect(shown()).toBe(2);
  });

  it('holds nothing under reduced motion', async () => {
    const { arrive, shown, gate } = setup({ reduced: true });
    gate.noteToggle();
    await arrive();
    expect(shown()).toBe(1);
  });

  it('puts a manual refresh behind the toggle too, as the legacy page does, but never the catch-up on release', async () => {
    const { clock, held, arrive, shown, gate } = setup();
    held.choice = true;
    await arrive();
    gate.noteToggle();
    const manual = arrive({ manual: true });
    expect(shown()).toBe(0);
    clock.advance(MOTION_HOLD_MS);
    await manual;
    expect(shown()).toBe(2);

    await arrive();
    gate.noteToggle();
    held.choice = false;
    gate.releaseChoice();
    expect(shown()).toBe(3);
  });

  it('holds a project-context paint behind the toggle but not behind an open list', () => {
    const { clock, held, store, gate } = setup();
    held.choice = true;
    store.setContext('k', { data: null, revision: 1, error: null });
    expect(gate.getSnapshot().contexts.has('k')).toBe(true);
    gate.noteToggle();
    store.setContext('k2', { data: null, revision: 2, error: null });
    expect(gate.getSnapshot().contexts.has('k2')).toBe(false);
    clock.advance(MOTION_HOLD_MS);
    expect(gate.getSnapshot().contexts.has('k2')).toBe(true);
  });

  it("shows a reader's own action state (pending, manual refreshing) at once while an old board is held", async () => {
    const { held, store, arrive, shown, gate } = setup();
    held.choice = true;
    await arrive();
    store.setPending(['save:a']);
    store.setManualRefreshing(true);
    expect(gate.getSnapshot().pending).toEqual(['save:a']);
    expect(gate.getSnapshot().manualRefreshing).toBe(true);
    expect(shown()).toBe(0);
  });

  it('holds a failed read behind the same open list as a successful one', async () => {
    const { held, store, gate } = setup();
    await gate.paint({ manual: false, accepted: true });
    held.choice = true;
    store.recordFailure({ kind: 'network-error' });
    await gate.paint({ manual: false, accepted: false });
    expect(gate.getSnapshot().lastFailure).toBeNull();
    held.choice = false;
    gate.releaseChoice();
    expect(gate.getSnapshot().lastFailure).toEqual({ kind: 'network-error' });
  });

  it('resolves the awaited paint of a held run on dispose and clears its timer', async () => {
    const { clock, arrive, gate, detach } = setup();
    gate.noteToggle();
    const painted = arrive();
    detach();
    gate.dispose();
    await painted;
    expect(clock.activeTimers()).toBe(0);
  });

  it('stops following the store once detached', () => {
    const { store, gate, detach } = setup();
    detach();
    store.setPending(['x']);
    expect(gate.getSnapshot().pending).toEqual([]);
    expect(store.subscriberCount()).toBe(0);
  });
});
