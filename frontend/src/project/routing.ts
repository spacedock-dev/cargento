import type { KeyboardEvent, MouseEvent } from 'react';
import { fragmentForRoute, type RouteInput } from '../router/grammar';
import { useNavigate } from '../shell/context';

/** The token a route prints after `#n=`: what the legacy page kept in `data-next-route`. */
export function routeToken(route: RouteInput): string {
  return fragmentForRoute(route).slice(3);
}

/* What a clickable row does with a click and with Enter or Space. The row is not an anchor, because it
   holds controls of its own, so it is a link by role and the router is told on a plain click only: a
   modified click is the browser's own, and a click inside a nested route target belongs to that target. */
export function useRouteTarget(route: RouteInput) {
  const navigate = useNavigate();
  return {
    onClick(event: MouseEvent<HTMLElement>) {
      if (event.defaultPrevented) return;
      event.preventDefault();
      event.stopPropagation();
      navigate(route);
    },
    onKeyDown(event: KeyboardEvent<HTMLElement>) {
      // Only the row itself: a nested button takes Enter and Space as its own click.
      if (event.target !== event.currentTarget) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (!['Enter', ' ', 'Spacebar'].includes(event.key)) return;
      event.preventDefault();
      navigate(route);
    },
  };
}
