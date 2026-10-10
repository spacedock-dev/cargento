import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '../ui/accordion';
import { useRevealFragment } from './useRevealFragment';
import {
  useCallback,
  useRef,
  useState,
  useId,
  type MouseEvent,
  type FocusEvent,
  type ReactNode,
  type SyntheticEvent,
} from 'react';
import { Popover, PopoverTrigger, PopoverContent } from '../ui/popover';
import { useControls } from './kit';
import { useFocusKey } from './useFocusKey';
import { useDisclosureState, useControlledDisclosureState } from './useDisclosureState';
import { registerPopoverEscape } from './popoverEscape';

export interface DisclosureProps {
  /** The reader-state identity: see `disclosureKey`. Changing it remounts, so a node never carries one key's state to another. */
  readonly disclosureKey: string;
  readonly summary: ReactNode;
  /** An accordion eases in flow; a popover floats out of flow beside its summary; a menu fades over the page. */
  readonly variant?: 'accordion' | 'popover' | 'menu';
  readonly className?: string;
  /** The summary's accessible name when its visible text is a glyph. */
  readonly summaryLabel?: string;
  /** Registers the summary with the focus lane. */
  readonly focusKey?: string;
  readonly children: ReactNode;
}

export function Disclosure(props: DisclosureProps) {
  if (props.variant === 'popover')
    return <PopoverDisclosure key={props.disclosureKey} {...props} />;
  return props.variant === 'menu' ? (
    <DisclosureNode key={props.disclosureKey} {...props} />
  ) : (
    <AccordionDisclosure key={props.disclosureKey} {...props} />
  );
}

function AccordionDisclosure({
  disclosureKey,
  summary,
  className,
  summaryLabel,
  focusKey,
  children,
}: DisclosureProps) {
  const controls = useControls();
  const open = useControlledDisclosureState(controls.disclosures, disclosureKey);
  const triggerRef = useFocusKey<HTMLButtonElement>(controls.focusLane, focusKey ?? null);
  const panelRef = useRevealFragment(disclosureKey);
  return (
    <Accordion
      className={className ? `ctl-disclosure ${className}` : 'ctl-disclosure'}
      data-open={open ? '' : undefined}
      multiple
      value={open ? [disclosureKey] : []}
      onValueChange={(value, detail) => {
        if (detail.reason === 'trigger-press') controls.noteToggle();
        controls.disclosures.set(disclosureKey, value.includes(disclosureKey));
      }}
    >
      <AccordionItem value={disclosureKey}>
        <AccordionTrigger
          ref={triggerRef}
          {...(summaryLabel ? { 'aria-label': summaryLabel } : {})}
        >
          {summary}
        </AccordionTrigger>
        <AccordionContent ref={panelRef} hiddenUntilFound>
          {children}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

function DisclosureNode({
  disclosureKey,
  summary,
  className,
  summaryLabel,
  focusKey,
  children,
}: DisclosureProps) {
  const controls = useControls();
  const { open, binding } = useDisclosureState(controls.disclosures, disclosureKey);
  const summaryRef = useFocusKey<HTMLElement>(controls.focusLane, focusKey ?? null);

  const detailsRef = useCallback(
    (node: HTMLDetailsElement) => {
      const detach = binding.attach(node);
      return () => {
        detach();
      };
    },
    [binding],
  );

  const onToggle = (event: SyntheticEvent<HTMLDetailsElement>) => {
    binding.toggle(event.nativeEvent);
  };

  const onSummaryClick = (event: MouseEvent<HTMLElement>) => {
    event.preventDefault();
    controls.noteToggle();
    const details = event.currentTarget.parentElement;
    if (!(details instanceof HTMLDetailsElement)) return;
    const opening = !details.open;
    controls.disclosures.set(disclosureKey, opening);
  };

  return (
    <details
      className={className ? `ctl-menu ${className}` : 'ctl-menu'}
      ref={detailsRef}
      open={open}
      onToggle={onToggle}
    >
      <summary
        ref={summaryRef}
        onClick={onSummaryClick}
        {...(summaryLabel ? { 'aria-label': summaryLabel } : {})}
      >
        {summary}
      </summary>
      {children}
    </details>
  );
}

function PopoverDisclosure({
  disclosureKey,
  summary,
  className,
  summaryLabel,
  focusKey,
  children,
}: DisclosureProps) {
  const controls = useControls();
  const open = useControlledDisclosureState(controls.disclosures, disclosureKey);
  const focusRef = useFocusKey<HTMLButtonElement>(controls.focusLane, focusKey ?? null);
  const popupRef = useRef<HTMLDivElement>(null);
  const triggerNode = useRef<HTMLButtonElement>(null);
  const [container, setContainer] = useState<HTMLElement | null>(null);
  const triggerId = useId();
  const triggerRef = useCallback(
    (node: HTMLButtonElement | null) => {
      if (!node) return;
      triggerNode.current = node;
      setContainer(node.closest<HTMLElement>('#app, #gallery') ?? node.parentElement);
      const releaseFocus = focusRef(node);
      const releaseEscape = registerPopoverEscape(
        node,
        () => popupRef.current,
        () => controls.disclosures.set(disclosureKey, false),
      );
      return () => {
        releaseEscape();
        releaseFocus?.();
      };
    },
    [controls, disclosureKey, focusRef],
  );
  // Base UI left a departure after window blur open in the Chromium proof.
  // A missing related target is window blur, not a departure within the page.
  const onBlur = (event: FocusEvent<HTMLElement>) => {
    const next = event.relatedTarget;
    if (!(next instanceof Node)) return;
    if (!popupRef.current?.contains(next) && !triggerNode.current?.contains(next))
      controls.disclosures.set(disclosureKey, false);
  };
  return (
    <Popover
      open={open}
      triggerId={triggerId}
      onOpenChange={(next, detail) => {
        // The document handler chooses one return target for all open popovers.
        if (detail.reason === 'escape-key') {
          detail.cancel();
          return;
        }
        if (detail.reason === 'trigger-press') controls.noteToggle();
        controls.disclosures.set(disclosureKey, next);
        if (!next || detail.reason !== 'trigger-press') return;
        const reduce = controls.reducedMotion();
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            if (!controls.disclosures.isOpen(disclosureKey)) return;
            popupRef.current?.scrollIntoView({
              block: 'nearest',
              behavior: reduce ? 'auto' : 'smooth',
            });
          }),
        );
      }}
    >
      <div
        data-slot="popover"
        data-open={open ? '' : undefined}
        className={
          className
            ? `ctl-disclosure ctl-disclosure--pop ${className}`
            : 'ctl-disclosure ctl-disclosure--pop'
        }
      >
        <PopoverTrigger
          id={triggerId}
          ref={triggerRef}
          onBlur={onBlur}
          {...(summaryLabel ? { 'aria-label': summaryLabel } : {})}
        >
          {summary}
        </PopoverTrigger>
      </div>
      {container ? (
        <PopoverContent
          container={container}
          ref={popupRef}
          onBlur={onBlur}
          initialFocus={false}
          finalFocus={false}
          aria-labelledby={triggerId}
        >
          {children}
        </PopoverContent>
      ) : null}
    </Popover>
  );
}
