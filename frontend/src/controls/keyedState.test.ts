import { describe, expect, it, vi } from 'vitest';
import { createFakeClock } from '../transport/testing';
import { CUE_LIMIT, CUE_TTL_MS, createKeyedState, laneKey } from './keyedState';

function cues() {
  const clock = createFakeClock();
  const store = createKeyedState<'copied' | 'failed'>({
    clock,
    ttlMs: CUE_TTL_MS,
    limit: CUE_LIMIT,
  });
  return { clock, store };
}

describe('a keyed cue that outlives the node that drew it', () => {
  it('uses the legacy key shape: lane, harness and sid joined by NUL, never a display id', () => {
    expect(laneKey('copy', 'claude', 'abc')).toBe('copy\u0000claude\u0000abc');
    expect(laneKey('raise', undefined, undefined)).toBe('raise\u0000\u0000');
    expect(laneKey('copy', 'claude', 'abc')).not.toBe(laneKey('link', 'claude', 'abc'));
    expect(laneKey('copy', 'claude', 'abc')).not.toBe(laneKey('copy', 'codex', 'abc'));
  });

  it('reads back what was remembered and nothing for another key', () => {
    const { store } = cues();
    store.remember('a', 'copied');
    expect(store.read('a')).toBe('copied');
    expect(store.read('b')).toBeUndefined();
  });

  it('expires after thirty seconds and tells subscribers without a render being asked for', () => {
    const { store, clock } = cues();
    const listener = vi.fn();
    store.subscribe(listener);
    store.activate();
    store.remember('a', 'copied');
    listener.mockClear();
    clock.advance(CUE_TTL_MS - 1);
    expect(store.read('a')).toBe('copied');
    expect(listener).not.toHaveBeenCalled();
    clock.advance(1);
    expect(store.read('a')).toBeUndefined();
    expect(listener).toHaveBeenCalledOnce();
    expect(clock.activeTimers()).toBe(0);
  });

  it('reads an expired entry as absent even where nothing armed a timer', () => {
    const { store, clock } = cues();
    store.remember('a', 'failed');
    clock.advance(CUE_TTL_MS);
    expect(store.read('a')).toBeUndefined();
  });

  it('restarts the thirty seconds when the same key is remembered again', () => {
    const { store, clock } = cues();
    store.activate();
    store.remember('a', 'copied');
    clock.advance(20_000);
    store.remember('a', 'failed');
    clock.advance(20_000);
    expect(store.read('a')).toBe('failed');
    clock.advance(10_000);
    expect(store.read('a')).toBeUndefined();
  });

  it('keeps the newest thirty-two and evicts the oldest first', () => {
    const { store } = cues();
    for (let index = 0; index < CUE_LIMIT + 3; index += 1)
      store.remember(`k${String(index)}`, 'copied');
    expect(store.size()).toBe(CUE_LIMIT);
    expect(store.read('k0')).toBeUndefined();
    expect(store.read('k2')).toBeUndefined();
    expect(store.read('k3')).toBe('copied');
    store.remember('k3', 'failed');
    store.remember('extra', 'copied');
    expect(store.read('k3')).toBe('failed');
    expect(store.read('k4')).toBeUndefined();
  });

  it('holds a sticky entry with no expiry and no cap when configured so', () => {
    const clock = createFakeClock();
    const sticky = createKeyedState<'copied' | 'error'>({ clock, ttlMs: null, limit: null });
    sticky.activate();
    sticky.remember('project\n', 'copied');
    clock.advance(24 * 60 * 60 * 1000);
    expect(sticky.read('project\n')).toBe('copied');
    expect(clock.activeTimers()).toBe(0);
  });

  it('notifies subscribers once per remembered entry', () => {
    const { store } = cues();
    const listener = vi.fn();
    store.subscribe(listener);
    store.remember('a', 'copied');
    expect(listener).toHaveBeenCalledOnce();
  });

  it('stops its timer on deactivate and re-arms it on activate', () => {
    const { store, clock } = cues();
    store.activate();
    store.remember('a', 'copied');
    expect(clock.activeTimers()).toBe(1);
    store.deactivate();
    expect(clock.activeTimers()).toBe(0);
    store.activate();
    expect(clock.activeTimers()).toBe(1);
  });

  it('forgets one key or all of them', () => {
    const { store } = cues();
    store.remember('a', 'copied');
    store.remember('b', 'copied');
    store.forget('a');
    expect(store.read('a')).toBeUndefined();
    store.clear();
    expect(store.size()).toBe(0);
  });
});
