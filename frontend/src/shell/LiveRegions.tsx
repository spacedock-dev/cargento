import { useEffect, useRef, type ReactNode } from 'react';
import { REGION_IDS, type Announcer, type RegionName } from './announcer';
import { AnnouncerContext, useAnnouncer } from './announcerContext';

export function AnnouncerProvider({ announcer, children }: { readonly announcer: Announcer; readonly children: ReactNode }) {
  return <AnnouncerContext value={announcer}>{children}</AnnouncerContext>;
}

const REGIONS: readonly { readonly name: RegionName; readonly role: 'status' | 'alert'; readonly live: 'polite' | 'assertive' }[] = [
  { name: 'attention', role: 'status', live: 'polite' },
  { name: 'copy', role: 'status', live: 'polite' },
  { name: 'raise', role: 'status', live: 'polite' },
  /* Two cue regions rather than one, because politeness cannot be changed reliably on a node already
     in the tree. The alert region carries the armed discard warning alone: after the first press focus
     returns to the same button, and a polite message queued behind whatever the redraw is saying can
     still be unspoken when the second press lands, and that press deletes every revision. */
  { name: 'cue', role: 'status', live: 'polite' },
  { name: 'alert', role: 'alert', live: 'assertive' },
];

function Region({ name, role, live }: (typeof REGIONS)[number]) {
  const announcer = useAnnouncer();
  const node = useRef<HTMLParagraphElement>(null);
  /* The node is registered from an effect, after the empty region is already in the document, and
     the region draws no children: React never writes its text, so a sentence the announcer wrote
     survives every render, and the region and its first message never arrive in one mutation. */
  useEffect(() => {
    const element = node.current;
    return element ? announcer.attach(name, element) : undefined;
  }, [announcer, name]);
  return <p ref={node} id={REGION_IDS[name]} className="next-visually-hidden" role={role} aria-live={live} aria-atomic="true" />;
}

/* Rendered once, beside the replaceable page and never inside it. */
export function LiveRegions() {
  return (
    <>
      {REGIONS.map((region) => (
        <Region key={region.name} {...region} />
      ))}
    </>
  );
}
