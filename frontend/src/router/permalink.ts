import { fragmentForRoute } from './grammar';

export interface SessionIdentityFields {
  readonly project?: string | null;
  readonly harness?: string | null;
  readonly sid?: string | null;
}

/* The absolute link to one session's page, for a reader to paste: this page's own address up to its
   fragment, then the exact session route. Everything before `#` is kept, `?all=1` included, because the
   pasted link should open the board the reader was looking at. It names the harness and the sid, never a
   display id, and carries no origin: a link someone else opens starts at Sessions. Empty when there is no
   sid, because there is nothing to open. */
export function sessionLink(href: string, session: SessionIdentityFields): string {
  const sid = String(session.sid ?? '');
  if (!sid) return '';
  const fragment = fragmentForRoute({
    view: 'session',
    project: String(session.project ?? ''),
    harness: String(session.harness ?? ''),
    session: sid,
  });
  const at = href.indexOf('#');
  return `${at < 0 ? href : href.slice(0, at)}${fragment}`;
}
