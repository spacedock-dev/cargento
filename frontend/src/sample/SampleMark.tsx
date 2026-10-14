import { Popover as PopoverPrimitive } from '@base-ui/react/popover';
import { useContext, type ReactNode } from 'react';
import { Icon } from '../ui/icons';
import { Popover, PopoverContent } from '../ui/popover';
import { TourContext } from './tourContext';
import { TOUR, TOUR_BY_ID } from './tour';

/* The numbered (i) marks of the sample session. Components that sit beside a noted part draw
   `<SampleMark id="..."/>`, which draws nothing outside the sample, so no other page changes. The popup
   opens on hover and on a press (Enter or Space from the keyboard), and the same words are in the banner's
   text legend, so a mark is never the only copy. */

export function SampleMark({ id }: { readonly id: string }) {
  const active = useContext(TourContext);
  const found = TOUR_BY_ID.get(id);
  if (!active || !found) return null;
  const { note, n } = found;
  return (
    <Popover>
      <PopoverPrimitive.Trigger
        openOnHover
        delay={120}
        type="button"
        data-sample-tour
        data-sample-mark={id}
        aria-label={`Tour ${String(n)} of ${String(TOUR.length)}: ${note.title}`}
        className="relative ml-2 inline-flex cursor-help items-center gap-1 rounded-full border border-solid border-[var(--accent)] bg-transparent px-[7px] py-0 align-middle text-label font-semibold leading-[20px] text-[var(--accent)] before:absolute before:inset-x-0 before:-inset-y-[12px] before:content-['']"
      >
        <Icon name="info" />
        <span>{String(n)}</span>
      </PopoverPrimitive.Trigger>
      <PopoverContent align="start" side="bottom" data-sample-tour>
        <strong className="block text-foreground">{`${String(n)}. ${note.title}`}</strong>
        <span className="mt-1 block text-muted-foreground">{note.body}</span>
      </PopoverContent>
    </Popover>
  );
}

/* A control with its mark beside it, in a row, so the mark does not take the full width of a column the
   control sits in. Outside the sample, or with no id, it is just the control. */
export function SampleBeside({
  id,
  children,
}: {
  readonly id: string;
  readonly children: ReactNode;
}) {
  const active = useContext(TourContext);
  if (!active || !TOUR_BY_ID.has(id)) return <>{children}</>;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {children}
      <SampleMark id={id} />
    </div>
  );
}
