import type { ComponentPropsWithoutRef } from 'react';
import { useFieldMemory } from './useFieldMemory';

interface Memory {
  /** The field's exact identity (project, scope and kind, or harness, sid and field). Never a display id. */
  readonly memoryKey: string;
  readonly focusKey?: string;
  readonly focusFallback?: string;
}

/* Deliberately uncontrolled. Writing `value` back into a native editor, or
   replacing it, can erase its undo history even when its text looks identical,
   so the caller hands the words in once as `defaultValue` and reads them out
   through `onInput`.

   A different key is a different field, so the element is keyed by it: a node
   re-used for another session would carry the first session's caret, scroll and
   dragged size into the second. */
export function DraftTextarea({ memoryKey, ...rest }: Memory & ComponentPropsWithoutRef<'textarea'>) {
  return <DraftTextareaNode key={memoryKey} memoryKey={memoryKey} {...rest} />;
}

export function DraftInput({ memoryKey, ...rest }: Memory & ComponentPropsWithoutRef<'input'>) {
  return <DraftInputNode key={memoryKey} memoryKey={memoryKey} {...rest} />;
}

function DraftTextareaNode({ memoryKey, focusKey, focusFallback, ...rest }: Memory & ComponentPropsWithoutRef<'textarea'>) {
  const ref = useFieldMemory<HTMLTextAreaElement>(memoryKey, focusKey ?? null, focusFallback);
  return <textarea ref={ref} {...rest} />;
}

function DraftInputNode({ memoryKey, focusKey, focusFallback, ...rest }: Memory & ComponentPropsWithoutRef<'input'>) {
  const ref = useFieldMemory<HTMLInputElement>(memoryKey, focusKey ?? null, focusFallback);
  return <input ref={ref} {...rest} />;
}
