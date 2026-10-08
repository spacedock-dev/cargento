import { describe, expect, it, vi } from 'vitest';
import { createFakeClock } from '../transport/testing';
import {
  MAX_DEFERRED_COMMITS,
  MOTION_HOLD_MS,
  createCommitGate,
  createMotionHold,
} from './commit-gate';

function gateWith(held: { value: boolean }) {
  const commit = vi.fn<(payload: string) => void>();
  const gate = createCommitGate<string>({ isHeld: () => held.value, commit });
  return { gate, commit };
}

describe('commit gate for an open native choice', () => {
  it('commits at once when nothing holds the board', () => {
    const { gate, commit } = gateWith({ value: false });
    expect(gate.submit('a')).toBe('committed');
    expect(commit).toHaveBeenCalledExactlyOnceWith('a');
    expect(gate.hasPending()).toBe(false);
  });

  it('defers up to twelve consecutive background commits and keeps only the newest', () => {
    const held = { value: true };
    const { gate, commit } = gateWith(held);
    expect(MAX_DEFERRED_COMMITS).toBe(12);
    for (let attempt = 1; attempt <= 12; attempt += 1) {
      expect(gate.submit(`p${attempt}`), `attempt ${attempt}`).toBe('deferred');
    }
    expect(commit).not.toHaveBeenCalled();
    expect(gate.deferredCount()).toBe(12);
    expect(gate.release()).toBe(true);
    expect(commit).toHaveBeenCalledExactlyOnceWith('p12');
  });

  it('commits past the cap and does not re-arm it while the choice stays held', () => {
    const held = { value: true };
    const { gate, commit } = gateWith(held);
    for (let attempt = 1; attempt <= 12; attempt += 1) gate.submit(`p${attempt}`);
    expect(gate.submit('p13')).toBe('committed');
    expect(gate.submit('p14')).toBe('committed');
    expect(commit.mock.calls).toEqual([['p13'], ['p14']]);
    expect(gate.deferredCount()).toBe(12);
    expect(gate.hasPending()).toBe(false);
  });

  it('resets the count when the choice changes or blurs with a commit waiting', () => {
    const held = { value: true };
    const { gate, commit } = gateWith(held);
    for (let attempt = 1; attempt <= 5; attempt += 1) gate.submit(`p${attempt}`);
    gate.release();
    expect(commit).toHaveBeenCalledExactlyOnceWith('p5');
    expect(gate.deferredCount()).toBe(0);
    for (let attempt = 1; attempt <= 12; attempt += 1)
      expect(gate.submit(`q${attempt}`)).toBe('deferred');
  });

  it('does nothing on release when nothing was deferred', () => {
    const { gate, commit } = gateWith({ value: true });
    expect(gate.release()).toBe(false);
    expect(commit).not.toHaveBeenCalled();
  });

  it('resets the count and drops the deferral when an arrival finds nothing held', () => {
    const held = { value: true };
    const { gate, commit } = gateWith(held);
    for (let attempt = 1; attempt <= 3; attempt += 1) gate.submit(`p${attempt}`);
    held.value = false;
    expect(gate.submit('p4')).toBe('committed');
    expect(commit).toHaveBeenCalledExactlyOnceWith('p4');
    expect(gate.hasPending()).toBe(false);
    expect(gate.deferredCount()).toBe(0);
  });

  it('lets a manual or action commit bypass the hold', () => {
    const held = { value: true };
    const { gate, commit } = gateWith(held);
    gate.submit('p1');
    expect(gate.submit('manual', { manual: true })).toBe('committed');
    expect(commit).toHaveBeenCalledExactlyOnceWith('manual');
    expect(gate.hasPending()).toBe(false);
    expect(gate.deferredCount()).toBe(0);
  });
});

describe('disclosure motion hold', () => {
  function motion(reduced = false) {
    const clock = createFakeClock();
    const hold = createMotionHold({ clock, reducedMotion: () => reduced });
    return { clock, hold };
  }

  it('paints at once when no toggle is in flight', () => {
    const { hold } = motion();
    const paint = vi.fn();
    hold.paint(paint);
    expect(paint).toHaveBeenCalledOnce();
  });

  it('waits out a reader toggle and coalesces to the newest paint', () => {
    const { hold, clock } = motion();
    expect(MOTION_HOLD_MS).toBe(220);
    hold.noteToggle();
    const first = vi.fn();
    const newest = vi.fn();
    hold.paint(first);
    clock.advance(100);
    hold.paint(newest);
    expect(first).not.toHaveBeenCalled();
    clock.advance(119);
    expect(newest).not.toHaveBeenCalled();
    clock.advance(1);
    expect(first).not.toHaveBeenCalled();
    expect(newest).toHaveBeenCalledOnce();
    expect(clock.activeTimers()).toBe(0);
  });

  it('holds nothing under reduced motion', () => {
    const { hold } = motion(true);
    hold.noteToggle();
    const paint = vi.fn();
    hold.paint(paint);
    expect(paint).toHaveBeenCalledOnce();
  });

  it('drops a held paint and its timer on dispose', () => {
    const { hold, clock } = motion();
    hold.noteToggle();
    const paint = vi.fn();
    hold.paint(paint);
    hold.dispose();
    clock.advance(1000);
    expect(paint).not.toHaveBeenCalled();
    expect(clock.activeTimers()).toBe(0);
  });
});
