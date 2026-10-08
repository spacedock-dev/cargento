import type { MouseEvent, ReactNode } from 'react';
import { fragmentForRoute, type RouteInput } from '../router/grammar';
import { useNavigate } from './context';

export interface RouteLinkProps {
  readonly route: RouteInput;
  readonly className?: string;
  readonly children: ReactNode;
}

/* A link to a route that every producer of a route should use: it prints the canonical fragment as its
   `href`, so it opens in a new tab and copies as a link, and a plain click goes through the router, which
   stamps where a session was opened from. A modified click or a non-primary button is the browser's own. */
export function RouteLink({ route, className, children }: RouteLinkProps) {
  const navigate = useNavigate();
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(route);
  };
  return (
    <a href={fragmentForRoute(route)} {...(className ? { className } : {})} onClick={onClick}>
      {children}
    </a>
  );
}
