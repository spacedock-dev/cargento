import { Alert } from '../ui/alert';
import type { Row } from '../observed';
import { useShell } from '../shell/context';
import { capLine, readingCap } from './route';

/* Shown only once the shared analysis budget is spent. Under the cap the count is noise, so nothing about it
   is drawn; at the cap the reader needs to know before pressing, wherever they are on the page, so it holds
   the top of the viewport. */
export function ReadingCapBanner({ payload }: { readonly payload: Row }) {
  const { clock } = useShell();
  const cap = readingCap(payload);
  if (!cap) return null;
  return (
    <Alert variant="reading-cap" data-next-reading-cap>
      {capLine(cap, clock.now())}
    </Alert>
  );
}
