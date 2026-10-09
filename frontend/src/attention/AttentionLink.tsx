import type { MouseEvent, ReactNode } from 'react';
import { useControls } from '../controls';
import { useFocusKey } from '../controls/useFocusKey';
import { fragmentForRoute, type RouteInput } from '../router/grammar';
import { useNavigate } from '../shell/context';

/* A route link that registers with the focus lane under its subject's exact key. When a revision removes
   the subject the reader was on, focus falls to the section's heading (and from there to the title) rather
   than to the document: a keyboard reader on the third row of a queue is not dropped at the top of the page
   because the board moved. The href is the released fragment, so the link opens in a new tab and copies as
   a link; a plain click goes through the router, which stamps where the session was opened from. */
export function AttentionLink({
  route,
  focusKey,
  fallback,
  children,
}: {
  readonly route: RouteInput;
  readonly focusKey: string;
  readonly fallback: string;
  readonly children: ReactNode;
}) {
  const controls = useControls();
  const navigate = useNavigate();
  const ref = useFocusKey<HTMLAnchorElement>(controls.focusLane, focusKey, { fallback });
  const fragment = fragmentForRoute(route);
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    navigate(route);
  };
  return (
    <a ref={ref} href={fragment} data-next-route={fragment.slice(3)} onClick={onClick}>
      {children}
    </a>
  );
}
