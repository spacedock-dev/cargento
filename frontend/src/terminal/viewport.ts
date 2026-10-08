/* The terminal viewport's scroll offset and follow flag, as a state machine over a scroll container.

   Ported from `projectTerminalBindViewport`, `projectTerminalLiveScrollTop` and their neighbours in the
   legacy `project.js`, which win over any prose. The reader-state row is "The prototype terminal viewport
   scroll offset" in docs/design-reader-state.md: the offset is kept, clamped to the real scroll maximum,
   and following live output resumes only by scrolling back to within 2 px of it or by Jump to live. */

/** Within this many pixels of the live position still counts as following. Measured against the legacy page, not chosen. */
export const FOLLOW_THRESHOLD_PX = 2;

/* The two 6 px insets of `.pc-terminal-screen`: following the cursor row has to keep both visible. */
const HOST_INSETS_PX = 12;

export interface ViewportLike {
  scrollTop: number;
  readonly scrollHeight: number;
  readonly clientHeight: number;
}

/** What the renderer has measured of itself, or null when it has not yet. */
export interface TerminalGeometry {
  readonly rows: number;
  readonly cursorY: number;
  /** The rendered height of the screen element, which is not the host's. */
  readonly screenHeight: number;
}

export function scrollMaximum(viewport: Pick<ViewportLike, 'scrollHeight' | 'clientHeight'>): number {
  const maximum = Number(viewport.scrollHeight || 0) - Number(viewport.clientHeight || 0);
  return Number.isFinite(maximum) ? Math.max(0, maximum) : 0;
}

/* Following unused rows of a tall pane hid short output above the window, so the live position is the
   cursor's row plus both host insets, not the end of the content. With no measurement it is the maximum. */
export function liveScrollTop(viewport: ViewportLike, geometry: TerminalGeometry | null): number {
  const maximum = scrollMaximum(viewport);
  if (!geometry || !geometry.rows || !geometry.screenHeight) return maximum;
  const bottom = ((geometry.cursorY + 1) * geometry.screenHeight) / geometry.rows + HOST_INSETS_PX;
  return Math.min(maximum, Math.max(0, Math.ceil(bottom - viewport.clientHeight)));
}

export function createViewportState() {
  let follow = true;
  let scrollTop = 0;

  const toLive = (viewport: ViewportLike, geometry: TerminalGeometry | null): void => {
    follow = true;
    viewport.scrollTop = liveScrollTop(viewport, geometry);
    scrollTop = viewport.scrollTop;
  };

  return {
    follow: (): boolean => follow,
    scrollTop: (): number => scrollTop,

    /** A terminal opened afresh follows live output from the top. */
    reset(): void {
      follow = true;
      scrollTop = 0;
    },

    /** Returns whether the follow flag changed, because only that reaches the screen (the Jump button). */
    onScroll(viewport: ViewportLike, geometry: TerminalGeometry | null): boolean {
      const before = follow;
      scrollTop = Number(viewport.scrollTop) || 0;
      follow = Math.abs(liveScrollTop(viewport, geometry) - scrollTop) <= FOLLOW_THRESHOLD_PX;
      return follow !== before;
    },

    /** A viewport element has been (re)built: follow live, or put the reader's offset back, clamped. */
    bind(viewport: ViewportLike, geometry: TerminalGeometry | null): void {
      if (follow) {
        toLive(viewport, geometry);
        return;
      }
      viewport.scrollTop = Math.min(scrollTop, scrollMaximum(viewport));
      scrollTop = viewport.scrollTop;
    },

    jump(viewport: ViewportLike, geometry: TerminalGeometry | null): void {
      toLive(viewport, geometry);
    },

    /** New output was written: keep up only while following. Returns whether it moved. */
    afterOutput(viewport: ViewportLike, geometry: TerminalGeometry | null): boolean {
      if (!follow) return false;
      toLive(viewport, geometry);
      return true;
    },
  };
}

export type ViewportState = ReturnType<typeof createViewportState>;
