/* The part of a native editor a redraw cannot rebuild from its text: where the
   caret sits (focused or not), how far the box has scrolled inside itself, and
   the size the reader dragged it to. Held by the field's own exact key, so a
   remount gets the same state back and another session's field never gets it.

   While a field's node persists, none of this is needed: React leaves an
   uncontrolled element alone and the browser keeps its caret, its scroll, its
   size and its undo history. Capture happens as the node is removed, restore as
   its replacement mounts. Undo history and an active composition are NOT held
   here and cannot be: they belong to the node, which is why a field that is being
   edited must be kept, never swapped (docs/design-reader-state.md,
   "The correction's native editor"). */
export const FIELD_MEMORY_LIMIT = 64;

interface FieldState {
  readonly selection: { readonly start: number; readonly end: number; readonly direction: 'forward' | 'backward' | 'none' } | null;
  readonly top: number;
  readonly left: number;
  readonly width: string;
  readonly height: string;
}

type Editable = HTMLInputElement | HTMLTextAreaElement;

function selectionOf(field: Editable): FieldState['selection'] {
  try {
    const { selectionStart: start, selectionEnd: end, selectionDirection } = field;
    if (start === null || end === null) return null;
    return { start, end, direction: selectionDirection ?? 'none' };
  } catch {
    // An input type with no selection API (number, email) throws on read in some engines.
    return null;
  }
}

/* Bounded like every other keyed map here: a tab stays open for hours and a
   board can carry hundreds of sessions, each with fields of its own. */
export function createFieldMemory(limit: number = FIELD_MEMORY_LIMIT) {
  const states = new Map<string, FieldState>();
  return {
    capture(key: string, field: Editable): void {
      states.delete(key);
      states.set(key, {
        selection: selectionOf(field),
        top: field.scrollTop,
        left: field.scrollLeft,
        width: field.style.width,
        height: field.style.height,
      });
      while (states.size > limit) {
        const [oldest] = states.keys();
        if (oldest === undefined) break;
        states.delete(oldest);
      }
    },
    /** Applies what was captured under `key` to a freshly mounted, unfocused field; a key never seen changes nothing. */
    restore(key: string, field: Editable): void {
      const state = states.get(key);
      if (!state) return;
      field.style.width = state.width;
      field.style.height = state.height;
      if (state.selection) {
        // Clamped, because the words this field holds now may be shorter than the ones it held.
        const length = field.value.length;
        try {
          field.setSelectionRange(Math.min(state.selection.start, length), Math.min(state.selection.end, length), state.selection.direction);
        } catch {
          /* no selection API on this input type */
        }
      }
      field.scrollTop = state.top;
      field.scrollLeft = state.left;
    },
    has: (key: string): boolean => states.has(key),
    forget(key: string): void {
      states.delete(key);
    },
    size: (): number => states.size,
  };
}

export type FieldMemory = ReturnType<typeof createFieldMemory>;
