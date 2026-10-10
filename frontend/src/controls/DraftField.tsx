import type { ComponentPropsWithoutRef } from 'react';
import { Input } from '../ui/input';
import { Textarea, type TextareaProps } from '../ui/textarea';
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
export function DraftTextarea({
  memoryKey,
  ...rest
}: Memory & Omit<TextareaProps, 'value' | 'ref'>) {
  return <DraftTextareaNode key={memoryKey} memoryKey={memoryKey} {...rest} />;
}

export function DraftInput({
  memoryKey,
  ...rest
}: Memory & Omit<ComponentPropsWithoutRef<'input'>, 'value'>) {
  return <DraftInputNode key={memoryKey} memoryKey={memoryKey} {...rest} />;
}

function DraftTextareaNode({
  memoryKey,
  focusKey,
  focusFallback,
  ...rest
}: Memory & Omit<TextareaProps, 'value' | 'ref'>) {
  const ref = useFieldMemory<HTMLTextAreaElement>(memoryKey, focusKey ?? null, focusFallback);
  return <Textarea ref={ref} appearance="draft" {...rest} />;
}

function DraftInputNode({
  memoryKey,
  focusKey,
  focusFallback,
  ...rest
}: Memory & Omit<ComponentPropsWithoutRef<'input'>, 'value'>) {
  const ref = useFieldMemory<HTMLInputElement>(memoryKey, focusKey ?? null, focusFallback);
  return <Input ref={ref} {...rest} />;
}
