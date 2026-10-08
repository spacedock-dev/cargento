import { describe, expect, it } from 'vitest';
import {
  createViewportState,
  FOLLOW_THRESHOLD_PX,
  liveScrollTop,
  scrollMaximum,
  type TerminalGeometry,
  type ViewportLike,
} from './viewport';

/* A scroll container whose geometry the test sets, because jsdom lays nothing out. The setter clamps
   as a browser does, which is what lets "clamped to the real maximum" be observed rather than assumed. */
function container(scrollHeight: number, clientHeight: number, scrollTop = 0): ViewportLike {
  const state = { scrollHeight, clientHeight, top: scrollTop };
  return {
    get scrollHeight() {
      return state.scrollHeight;
    },
    get clientHeight() {
      return state.clientHeight;
    },
    get scrollTop() {
      return state.top;
    },
    set scrollTop(value: number) {
      state.top = Math.max(
        0,
        Math.min(value, Math.max(0, state.scrollHeight - state.clientHeight)),
      );
    },
  };
}

/* 24 rows of 20 px in a 340 px window with the host's 6 px insets either side. */
const GEOMETRY = (cursorY: number): TerminalGeometry => ({ rows: 24, cursorY, screenHeight: 480 });

describe('the viewport maths', () => {
  it('has a scroll maximum of content minus window, never negative', () => {
    expect(scrollMaximum({ scrollHeight: 492, clientHeight: 340 })).toBe(152);
    expect(scrollMaximum({ scrollHeight: 100, clientHeight: 340 })).toBe(0);
    expect(scrollMaximum({ scrollHeight: Number.NaN, clientHeight: 340 })).toBe(0);
  });

  it('follows the cursor row, not the unused rows below it, so short output stays readable', () => {
    const viewport = container(492, 340);
    // Cursor on row 1: bottom = 2 * 480/24 + 12 = 52, which fits the window, so the top stays at 0.
    expect(liveScrollTop(viewport, GEOMETRY(1))).toBe(0);
    // Cursor on row 22: bottom = 23 * 20 + 12 = 472, and 472 - 340 = 132 is below the 152 maximum.
    expect(liveScrollTop(viewport, GEOMETRY(22))).toBe(132);
  });

  it('never follows past the real scroll maximum', () => {
    const viewport = container(492, 340);
    expect(liveScrollTop(viewport, { rows: 24, cursorY: 23, screenHeight: 4800 })).toBe(152);
  });

  it('falls back to the maximum when the renderer has not measured itself', () => {
    const viewport = container(492, 340);
    expect(liveScrollTop(viewport, null)).toBe(152);
    expect(liveScrollTop(viewport, { rows: 0, cursorY: 0, screenHeight: 480 })).toBe(152);
    expect(liveScrollTop(viewport, { rows: 24, cursorY: 0, screenHeight: 0 })).toBe(152);
  });

  it('treats 2 px as still following and 3 px as having left', () => {
    expect(FOLLOW_THRESHOLD_PX).toBe(2);
    const viewport = container(492, 340, 0);
    const state = createViewportState();
    // With no measured cursor the live position is the 152 px maximum.
    for (const top of [152, 151, 150]) {
      viewport.scrollTop = top;
      state.onScroll(viewport, null);
      expect(state.follow(), `scrollTop ${String(top)}`).toBe(true);
    }
    viewport.scrollTop = 149;
    state.onScroll(viewport, null);
    expect(state.follow()).toBe(false);
  });
});

describe('the viewport state', () => {
  it('starts following at offset 0', () => {
    const state = createViewportState();
    expect(state.follow()).toBe(true);
    expect(state.scrollTop()).toBe(0);
  });

  it('reports whether a scroll changed the follow flag, so only a change reaches the screen', () => {
    const viewport = container(492, 340, 152);
    const state = createViewportState();
    viewport.scrollTop = 152;
    expect(state.onScroll(viewport, null)).toBe(false);
    viewport.scrollTop = 40;
    expect(state.onScroll(viewport, null)).toBe(true);
    viewport.scrollTop = 41;
    expect(state.onScroll(viewport, null)).toBe(false);
    expect(state.scrollTop()).toBe(41);
    expect(state.follow()).toBe(false);
  });

  it('restores a reader offset, clamped to the new maximum, when the viewport is rebuilt', () => {
    const first = container(492, 340);
    const state = createViewportState();
    first.scrollTop = 90;
    state.onScroll(first, null);
    expect(state.follow()).toBe(false);
    // A rebuilt scroll container with less content: the saved 90 is above its 60 maximum.
    const rebuilt = container(400, 340);
    state.bind(rebuilt, null);
    expect(rebuilt.scrollTop).toBe(60);
    expect(state.scrollTop()).toBe(60);
    // Clamping to the end is the live position, so the next scroll event reads as following again.
    state.onScroll(rebuilt, null);
    expect(state.follow()).toBe(true);
  });

  it('clamps by its own arithmetic, not only because a browser would, in a container that does not clamp', () => {
    // A plain object: assigning past the maximum sticks, as it does in jsdom and in any wrapper that forwards blindly.
    const raw: ViewportLike = { scrollTop: 0, scrollHeight: 400, clientHeight: 340 };
    const state = createViewportState();
    const reader = container(492, 340);
    reader.scrollTop = 90;
    state.onScroll(reader, null);
    state.bind(raw, null);
    expect(raw.scrollTop).toBe(60);
    expect(state.scrollTop()).toBe(60);
  });

  it('keeps a reader offset exactly while the maximum still allows it', () => {
    const viewport = container(492, 340);
    const state = createViewportState();
    viewport.scrollTop = 90;
    state.onScroll(viewport, null);
    const rebuilt = container(492, 340);
    state.bind(rebuilt, null);
    expect(rebuilt.scrollTop).toBe(90);
    expect(state.follow()).toBe(false);
  });

  it('goes to the live position when binding while following', () => {
    const viewport = container(492, 340);
    const state = createViewportState();
    state.bind(viewport, GEOMETRY(22));
    expect(viewport.scrollTop).toBe(132);
    expect(state.scrollTop()).toBe(132);
    expect(state.follow()).toBe(true);
  });

  it('resumes following on an explicit jump, even from a long way up', () => {
    const viewport = container(492, 340);
    const state = createViewportState();
    viewport.scrollTop = 10;
    state.onScroll(viewport, GEOMETRY(22));
    expect(state.follow()).toBe(false);
    state.jump(viewport, GEOMETRY(22));
    expect(state.follow()).toBe(true);
    expect(viewport.scrollTop).toBe(132);
    expect(state.scrollTop()).toBe(132);
  });

  it('resets to following at offset 0 for a newly opened terminal', () => {
    const viewport = container(492, 340);
    const state = createViewportState();
    viewport.scrollTop = 10;
    state.onScroll(viewport, null);
    state.reset();
    expect(state.follow()).toBe(true);
    expect(state.scrollTop()).toBe(0);
  });

  it('scrolls to live on new output only while following', () => {
    const viewport = container(492, 340);
    const state = createViewportState();
    expect(state.afterOutput(viewport, GEOMETRY(22))).toBe(true);
    expect(viewport.scrollTop).toBe(132);
    viewport.scrollTop = 10;
    state.onScroll(viewport, GEOMETRY(22));
    expect(state.afterOutput(viewport, GEOMETRY(23))).toBe(false);
    expect(viewport.scrollTop).toBe(10);
  });
});
