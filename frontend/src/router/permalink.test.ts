import { describe, expect, it } from 'vitest';
import { loadLegacyBoot } from './legacyBoot.test.helper';
import { sessionLink } from './permalink';

describe('a copied session link keeps the whole page address and names the exact session', () => {
  it('keeps the path and every query, ?all=1 included, and replaces only the fragment', () => {
    expect(sessionLink('http://127.0.0.1:4581/?all=1#n=sessions', { project: 'alpha/app', harness: 'claude', sid: 'shared-sid' })).toBe(
      'http://127.0.0.1:4581/?all=1#n=session:alpha%2Fapp:claude:shared-sid',
    );
    expect(sessionLink('http://127.0.0.1:4581/', { project: 'p', harness: 'codex', sid: 's' })).toBe('http://127.0.0.1:4581/#n=session:p:codex:s');
  });

  it('never carries the origin the sender came from, so a pasted link starts at Sessions', () => {
    expect(sessionLink('http://h/#n=session:p:claude:s&from=attention', { project: 'p', harness: 'claude', sid: 's' })).toBe(
      'http://h/#n=session:p:claude:s',
    );
  });

  it('encodes a colon in a part and keeps an empty project, which is a valid session project', () => {
    expect(sessionLink('http://h/', { project: '', harness: 'claude', sid: 'colon:sid' })).toBe('http://h/#n=session::claude:colon%3Asid');
  });

  it('is empty for a session with no sid, because there is nothing to open', () => {
    expect(sessionLink('http://h/', { project: 'p', harness: 'claude', sid: '' })).toBe('');
    expect(sessionLink('http://h/', { project: 'p', harness: 'claude' })).toBe('');
  });

  it('agrees with the legacy builder for every case above and for odd names', () => {
    const cases = [
      { project: 'alpha/app', harness: 'claude', sid: 'shared-sid' },
      { project: '', harness: 'codex', sid: 'x:y' },
      { project: 'a b&c', harness: '', sid: 'é' },
      { project: null, harness: 'claude', sid: 'one' },
    ];
    for (const href of ['http://127.0.0.1:4581/', 'http://127.0.0.1:4581/?all=1', 'http://127.0.0.1:4581/?all=1#n=attention', 'http://h/p?x=1#']) {
      const legacy = loadLegacyBoot(href);
      for (const session of cases) {
        expect(sessionLink(href, session), `${href} ${JSON.stringify(session)}`).toBe(legacy.link(session));
      }
    }
  });
});
