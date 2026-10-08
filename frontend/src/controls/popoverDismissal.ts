/* A popover is a disclosure whose summary sits in a flex row beside other
   content, so its body floats out of flow and opening it moves nothing. It
   closes the way a menu does: Escape, a click outside, or focus moving on to
   another control. Anything else leaves it open, so a poll must not shut a body
   the reader is reading, and focus that goes nowhere (another window taking
   focus, or a redraw replacing the focused node) is not a departure. Accordions
   take none of this: they close only when the reader presses them.

   Installed once on the document rather than per popover, as the legacy page
   does, because Escape closes every open popover and returns focus to exactly
   one summary, which no single instance can decide. The selector is static; no
   key is ever interpolated into it. */
const OPEN_POPOVERS = 'details[data-ctl-popover][open]';

function openPopovers(doc: Document): HTMLDetailsElement[] {
  return [...doc.querySelectorAll<HTMLDetailsElement>(OPEN_POPOVERS)];
}

export function installPopoverDismissal(doc: Document): () => void {
  const onKeydown = (event: KeyboardEvent) => {
    if (event.key !== 'Escape') return;
    const open = openPopovers(doc);
    if (open.length === 0) return;
    for (const popover of open) popover.open = false;
    const target = event.target instanceof Node ? event.target : null;
    const owner = open.find((popover) => target !== null && popover.contains(target)) ?? open[0];
    owner?.querySelector<HTMLElement>(':scope > summary')?.focus();
    event.preventDefault();
  };
  const onClick = (event: MouseEvent) => {
    const target = event.target instanceof Node ? event.target : null;
    for (const popover of openPopovers(doc)) {
      if (!target || !popover.contains(target)) popover.open = false;
    }
  };
  const onFocusOut = (event: FocusEvent) => {
    const target = event.target instanceof Element ? event.target : null;
    const popover = target?.closest<HTMLDetailsElement>(OPEN_POPOVERS);
    const next = event.relatedTarget;
    if (!popover || !(next instanceof Node)) return;
    if (!popover.contains(next)) popover.open = false;
  };
  doc.addEventListener('keydown', onKeydown);
  doc.addEventListener('click', onClick);
  doc.addEventListener('focusout', onFocusOut);
  return () => {
    doc.removeEventListener('keydown', onKeydown);
    doc.removeEventListener('click', onClick);
    doc.removeEventListener('focusout', onFocusOut);
  };
}
