/* Base UI dismisses one popup per Escape. The page-wide choice belongs to
   docs/design-reader-state.md#disclosure-write-precedence: close all, focus one
   trigger in document order, including when the event starts outside a popup. */
const popovers = new WeakMap<
  HTMLElement,
  { popup: () => HTMLElement | null; dismiss: () => void }
>();

export function registerPopoverEscape(
  trigger: HTMLElement,
  popup: () => HTMLElement | null,
  dismiss: () => void,
): () => void {
  popovers.set(trigger, { popup, dismiss });
  return () => {
    popovers.delete(trigger);
  };
}

export function installPopoverEscape(doc: Document): () => void {
  const onKeydown = (event: KeyboardEvent) => {
    if (event.key !== 'Escape') return;
    // A choice above a popover owns the first Escape; leave its containing disclosure open.
    if (doc.querySelector('[data-slot=select-trigger][aria-expanded=true]')) return;
    const open = [
      ...doc.querySelectorAll<HTMLElement>('[data-slot=popover-trigger][aria-expanded=true]'),
    ];
    if (open.length === 0) return;
    const target = event.target instanceof Node ? event.target : null;
    // A nested trigger will disappear with its parent's popup. Preserve the
    // event owner only among triggers that remain visible after all dismissals.
    const visible = open.filter(
      (trigger) => !open.some((other) => popovers.get(other)?.popup()?.contains(trigger)),
    );
    const owner =
      visible.find(
        (trigger) =>
          target !== null &&
          (trigger.contains(target) || popovers.get(trigger)?.popup()?.contains(target)),
      ) ?? visible[0];
    for (const trigger of open) popovers.get(trigger)?.dismiss();
    owner?.focus();
    event.preventDefault();
  };
  doc.addEventListener('keydown', onKeydown, true);
  return () => doc.removeEventListener('keydown', onKeydown, true);
}
