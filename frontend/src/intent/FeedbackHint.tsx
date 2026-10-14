import { Popover as PopoverPrimitive } from '@base-ui/react/popover';
import { Icon } from '../ui/icons';
import { Popover, PopoverContent } from '../ui/popover';
import { feedbackSummary } from './sentences';

/* A press's answer as one short line and an info mark, the whole sentence in a popover that opens on hover
   and on a press, or Enter or Space from the keyboard (so a touch screen reaches it, which a tooltip does not). The sentence also stays in
   the page for a screen reader as the button's description, and the polite region announces it, so the popover
   is never the only copy of it. */
export function FeedbackHint({ id, message }: { readonly id: string; readonly message: string }) {
  const short = feedbackSummary(message);
  return (
    <>
      <span id={id} className="next-visually-hidden" data-next-action-feedback>
        {message}
      </span>
      <Popover>
        <PopoverPrimitive.Trigger
          openOnHover
          delay={120}
          type="button"
          aria-describedby={id}
          data-next-action-feedback-short
          className="next-cockpit-reading-why relative m-0 inline-flex before:absolute before:inset-x-0 before:-inset-y-[11px] before:content-['']  w-fit max-w-full cursor-help items-center gap-1 border-0 bg-transparent p-0 text-start underline decoration-dotted underline-offset-[3px]"
        >
          <Icon name="info" />
          <span>{short}</span>
        </PopoverPrimitive.Trigger>
        <PopoverContent align="start" side="bottom" aria-label={short}>
          {message}
        </PopoverContent>
      </Popover>
    </>
  );
}
