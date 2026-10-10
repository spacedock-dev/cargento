import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '../ui/accordion';
import { useRevealFragment } from './useRevealFragment';
import { useCallback, type MouseEvent, type ReactNode, type SyntheticEvent } from 'react';
import { useControls } from './kit';
import { useFocusKey } from './useFocusKey';
import { useDisclosureState, useControlledDisclosureState } from './useDisclosureState';
import { registerPopoverDismissal } from './popoverDismissal';

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

const CLASS = {
  accordion: 'ctl-disclosure',
  popover: 'ctl-disclosure ctl-disclosure--pop',
  menu: 'ctl-menu',
} as const;

export function Disclosure(props: DisclosureProps) {
  return props.variant === 'popover' || props.variant === 'menu' ? (
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
  variant = 'accordion',
  className,
  summaryLabel,
  focusKey,
  children,
}: DisclosureProps) {
  const controls = useControls();
  const { open, binding } = useDisclosureState(controls.disclosures, disclosureKey);
  const summaryRef = useFocusKey<HTMLElement>(controls.focusLane, focusKey ?? null);
  const popover = variant === 'popover';

  const detailsRef = useCallback(
    (node: HTMLDetailsElement) => {
      const detach = binding.attach(node);
      const unregister = popover
        ? registerPopoverDismissal(node, () => controls.disclosures.set(disclosureKey, false))
        : () => undefined;
      return () => {
        unregister();
        detach();
      };
    },
    [binding, popover, controls, disclosureKey],
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
    if (!popover || !opening) return;
    /* Opening a popover scrolls the page just far enough to show all of it, once:
       a tall body would otherwise end below the window. Two frames, not a zero
       timeout: a scroll asked for before the opened body is laid out moves
       nothing (Chrome 156). Never on a redraw, which re-inserts it open without a press. */
    const reduce = controls.reducedMotion();
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        if (!details.open) return;
        details
          .querySelector('.ctl-disclosure-body')
          ?.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' });
      }),
    );
  };

  return (
    <details
      className={className ? `${CLASS[variant]} ${className}` : CLASS[variant]}
      ref={detailsRef}
      open={open}
      onToggle={onToggle}
      {...(popover ? { 'data-ctl-popover': '' } : {})}
    >
      <summary
        ref={summaryRef}
        onClick={onSummaryClick}
        {...(summaryLabel ? { 'aria-label': summaryLabel } : {})}
      >
        {summary}
      </summary>
      {popover ? <div className="ctl-disclosure-body">{children}</div> : children}
    </details>
  );
}
