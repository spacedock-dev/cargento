import { describe, expect, it, vi } from 'vitest';
import { createPendingRegistry, PENDING_BACKSTOP_MS, PENDING_BOUND_MS, PENDING_SAY_MS } from './pending';
import { createFakeClock } from './testing';

function setup() {
  const clock = createFakeClock();
  const onChange = vi.fn();
  const announce = vi.fn();
  const registry = createPendingRegistry({ clock, onChange, announce });
  return { clock, onChange, announce, registry };
}

describe('per-control pending work', () => {
  it('uses the released timings', () => {
    expect([PENDING_SAY_MS, PENDING_BOUND_MS, PENDING_BACKSTOP_MS]).toEqual([400, 15_000, 5_000]);
  });

  it('refuses a second press while the control is pending', () => {
    const { registry } = setup();
    const first = registry.start('save:a', 'Saving');
    expect(first).not.toBeNull();
    expect(registry.start('save:a', 'Saving')).toBeNull();
    expect(registry.has('save:a')).toBe(true);
    expect(registry.start('save:b', 'Saving')).not.toBeNull();
    expect(registry.keys()).toEqual(['save:a', 'save:b']);
  });

  it('ignores an empty key', () => {
    expect(setup().registry.start('', 'x')).toBeNull();
  });

  it('says the start sentence only after the cue delay, and not at all for a fast answer', () => {
    const { registry, clock, announce } = setup();
    const fast = registry.start('fast', 'Saving', 'Saving the line.');
    clock.advance(399);
    expect(announce).not.toHaveBeenCalled();
    registry.end('fast', fast);
    clock.advance(1000);
    expect(announce).not.toHaveBeenCalled();

    registry.start('slow', 'Saving', 'Saving the line.');
    clock.advance(400);
    expect(announce).toHaveBeenCalledOnce();
    expect(announce).toHaveBeenCalledWith('slow', 'Saving the line.');
  });

  it('says nothing for a control that supplies no sentence', () => {
    const { registry, clock, announce } = setup();
    registry.start('quiet', 'Saving');
    clock.advance(1000);
    expect(announce).not.toHaveBeenCalled();
  });

  it('aborts the request at the bound and clears the entry at the backstop', () => {
    const { registry, clock, onChange } = setup();
    const token = registry.start('save:a', 'Saving');
    expect(token?.signal.aborted).toBe(false);
    clock.advance(14_999);
    expect(token?.signal.aborted).toBe(false);
    clock.advance(1);
    expect(token?.signal.aborted).toBe(true);
    expect(registry.has('save:a')).toBe(true);
    clock.advance(4_999);
    expect(registry.has('save:a')).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
    clock.advance(1);
    expect(registry.has('save:a')).toBe(false);
    expect(onChange).toHaveBeenCalledOnce();
    expect(clock.activeTimers()).toBe(0);
  });

  it('lets a late completion end only its own token, never a replacement', () => {
    const { registry, clock } = setup();
    const old = registry.start('save:a', 'Saving');
    clock.advance(20_000);
    expect(registry.has('save:a')).toBe(false);
    const replacement = registry.start('save:a', 'Saving');
    expect(replacement).not.toBeNull();
    expect(registry.end('save:a', old)).toBe(false);
    expect(registry.has('save:a')).toBe(true);
    clock.advance(10_000);
    expect(replacement?.signal.aborted).toBe(false);
    expect(registry.end('save:a', replacement)).toBe(true);
    expect(registry.has('save:a')).toBe(false);
  });

  it('removes every timer of an entry when it ends', () => {
    const { registry, clock } = setup();
    const token = registry.start('save:a', 'Saving', 'Saving.');
    expect(clock.activeTimers()).toBe(3);
    registry.end('save:a', token);
    expect(clock.activeTimers()).toBe(0);
  });

  it('does not let an old backstop clear a replacement token', () => {
    const { registry, clock } = setup();
    const old = registry.start('save:a', 'Saving');
    registry.end('save:a', old);
    const replacement = registry.start('save:a', 'Saving');
    clock.advance(19_999);
    expect(registry.has('save:a')).toBe(true);
    expect(replacement?.signal.aborted).toBe(true);
  });

  it('disposes every timer and aborts only the requests it owns', () => {
    const { registry, clock, onChange, announce } = setup();
    const a = registry.start('a', 'Saving', 'Saving.');
    const b = registry.start('b', 'Saving', 'Saving.');
    const foreign = new AbortController();
    registry.dispose();
    expect(a?.signal.aborted).toBe(true);
    expect(b?.signal.aborted).toBe(true);
    expect(foreign.signal.aborted).toBe(false);
    expect(clock.activeTimers()).toBe(0);
    clock.advance(60_000);
    expect(onChange).not.toHaveBeenCalled();
    expect(announce).not.toHaveBeenCalled();
    expect(registry.keys()).toEqual([]);
    expect(registry.start('c', 'Saving')).toBeNull();
  });
});

/* The legacy `nextPendingEnd` deleted the pending cue's announced-sentence guard with the entry, "so the
   next press's start sentence is said again rather than suppressed as a repeat of this one". The registry
   owns the entry's life, so it owns telling the announcer to forget. */
describe('forgetting the start sentence when an entry ends', () => {
  function withForget() {
    const clock = createFakeClock();
    const announce = vi.fn();
    const forget = vi.fn();
    const registry = createPendingRegistry({ clock, onChange: vi.fn(), announce, forget });
    return { clock, announce, forget, registry };
  }

  it('forgets the key once, when the owning token ends the entry', () => {
    const { registry, clock, forget } = withForget();
    const token = registry.start('save:a', 'Saving', 'Saving.');
    clock.advance(400);
    expect(forget).not.toHaveBeenCalled();
    expect(registry.end('save:a', token)).toBe(true);
    expect(forget).toHaveBeenCalledOnce();
    expect(forget).toHaveBeenCalledWith('save:a');
  });

  it('forgets nothing when a token that no longer owns the entry tries to end it', () => {
    const { registry, forget } = withForget();
    const old = registry.start('save:a', 'Saving', 'Saving.');
    registry.end('save:a', old);
    forget.mockClear();
    registry.start('save:a', 'Saving', 'Saving.');
    expect(registry.end('save:a', old)).toBe(false);
    expect(registry.end('save:a', null)).toBe(false);
    expect(forget).not.toHaveBeenCalled();
  });

  it('forgets when the backstop clears a lost request', () => {
    const { registry, clock, forget } = withForget();
    registry.start('save:a', 'Saving', 'Saving.');
    clock.advance(PENDING_BOUND_MS + PENDING_BACKSTOP_MS);
    expect(forget).toHaveBeenCalledWith('save:a');
  });

  it('is optional: a registry built without it ends entries as before', () => {
    const { registry } = setup();
    const token = registry.start('save:a', 'Saving', 'Saving.');
    expect(registry.end('save:a', token)).toBe(true);
  });
});
