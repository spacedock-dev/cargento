import { sessionHome, type RouteInput } from '../router/grammar';

/* The slice of a keydown the page's global shortcuts read, so the rule is testable without an event. */
export interface KeyEventLike {
  readonly key: string;
  readonly tagName: string;
  readonly isContentEditable?: boolean;
  readonly metaKey?: boolean;
  readonly ctrlKey?: boolean;
  readonly altKey?: boolean;
  readonly defaultPrevented?: boolean;
}

const FIELDS = ['input', 'select', 'textarea'];
const SHORTCUTS: Readonly<Record<string, RouteInput>> = {
  a: { view: 'attention', project: null, session: null },
  p: { view: 'projects', project: null, session: null },
  s: { view: 'sessions', project: null, session: null },
};

/* Where a key takes the reader, or null for a key that is not the page's. Escape goes where the
   crumb's last link goes: a session returns to the view it was opened from (or to its project, when
   it came from one and has one), and every other view returns to Sessions, the landing view.

   Skipped where the reader is typing, with a modifier held, or when another handler already took the
   key. That last case is Escape closing a popover, which must mean "close this" before it can mean
   "leave this view"; the legacy page ran the popover handler first and returned, and here the
   shortcut listener sits on the window so every document-level handler has run before it. */
export function shortcutTarget(event: KeyEventLike, route: RouteInput): RouteInput | null {
  if (event.metaKey || event.ctrlKey || event.altKey || event.defaultPrevented) return null;
  if (FIELDS.includes(event.tagName.toLowerCase()) || event.isContentEditable) return null;
  if (event.key === 'Escape') {
    const home = route.view === 'session' ? sessionHome(route) : 'sessions';
    if (home === 'projects' && route.project)
      return { view: 'project', project: route.project, session: null };
    return { view: home, project: null, session: null };
  }
  const letter = event.key.toLowerCase();
  return Object.hasOwn(SHORTCUTS, letter) ? (SHORTCUTS[letter] ?? null) : null;
}
