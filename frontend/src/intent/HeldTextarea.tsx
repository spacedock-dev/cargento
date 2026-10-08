import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
  type MutableRefObject,
} from 'react';
import { useFieldMemory } from '../controls/useFieldMemory';

/* A native editor the reader types into, held by the page and not by the node.

   Uncontrolled on purpose: React is handed the words once as `defaultValue` and never writes `value` back,
   because writing a native editor's value, or replacing the element, erases its undo history even when the
   text looks identical, and ends an input-method composition. The words the reader types reach the page's
   held state through `onEdit`, and the box keeps its own caret, selection, scroll, size, undo and
   composition across every redraw, route change and StrictMode double effect.

   Exactly one thing replaces the node: the page changed the words for a reason other than typing (Undo, a
   chosen prompt, Clear, a save landing, another tab's save arriving). It is told apart by comparing what the
   page says the box holds with what the node holds after every render, which a keystroke never makes differ
   because the handler updates the held words before React renders. The replacement is a new component
   under the same field-memory key, so the caret, scroll and dragged size come back, and focus returns to
   it if it had focus (the focus lane restores the same key). */
type Props = Omit<
  ComponentPropsWithoutRef<'textarea'>,
  'defaultValue' | 'value' | 'onInput' | 'ref'
> & {
  readonly memoryKey: string;
  readonly focusKey: string;
  /** What the page says the box holds right now. */
  readonly text: string;
  /** The reader's words as the node now holds them; returns the words the page kept. */
  readonly onEdit: (raw: string) => string;
};

/* The API value of a textarea has CRLF and CR normalised to LF, so the page's text is compared as the node
   would hold it. Without this a prompt with a carriage return would differ forever and replace the node on
   every render. */
const asNode = (text: string): string => text.replace(/\r\n?/g, '\n');

function Node({
  memoryKey,
  focusKey,
  initial,
  onEdit,
  nodeRef,
  ...rest
}: Omit<Props, 'text'> & {
  readonly initial: string;
  readonly nodeRef: MutableRefObject<HTMLTextAreaElement | null>;
}) {
  const memoryRef = useFieldMemory<HTMLTextAreaElement>(memoryKey, focusKey);
  const ref = useCallback(
    (element: HTMLTextAreaElement | null) => {
      nodeRef.current = element;
      return memoryRef(element);
    },
    [memoryRef, nodeRef],
  );
  return (
    <textarea
      ref={ref}
      defaultValue={initial}
      onInput={(event) => {
        const box = event.currentTarget;
        const kept = onEdit(box.value);
        /* Cut or scrubbed words are put back into the node, which is the one write to a native editor, as
           the legacy box does. */
        if (kept !== box.value) box.value = kept;
      }}
      {...rest}
    />
  );
}

export function HeldTextarea({ text, ...props }: Props) {
  const [view, setView] = useState({ epoch: 0, initial: text });
  const node = useRef<HTMLTextAreaElement | null>(null);
  const replaced = useRef<string | null>(null);
  useLayoutEffect(() => {
    const element = node.current;
    if (!element) return;
    if (element.value === asNode(text)) {
      replaced.current = null;
      return;
    }
    // A node that still differs from words it was just replaced with is the browser's own normalisation,
    // and replacing it again would loop.
    if (replaced.current === text) return;
    replaced.current = text;
    setView((held) => ({ epoch: held.epoch + 1, initial: text }));
  });
  return <Node key={view.epoch} initial={view.initial} nodeRef={node} {...props} />;
}
