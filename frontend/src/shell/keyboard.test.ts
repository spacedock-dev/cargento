import { describe, expect, it } from 'vitest';
import { parseFragment } from '../router/grammar';
import { shortcutTarget, type KeyEventLike } from './keyboard';

const route = (fragment: string) => parseFragment(fragment);
const key = (value: string, extra: Partial<KeyEventLike> = {}): KeyEventLike => ({
  key: value,
  tagName: 'BODY',
  ...extra,
});
const top = (view: string) => ({ view, project: null, session: null });

describe('Escape walks up to where the reader came from', () => {
  it('returns every top-level view and a project page to Sessions', () => {
    for (const fragment of [
      '#n=attention',
      '#n=projects',
      '#n=intent',
      '#n=sessions',
      '#n=project:recce',
    ]) {
      expect(shortcutTarget(key('Escape'), route(fragment)), fragment).toEqual(top('sessions'));
    }
  });

  it('returns a session to the view it was opened from, and a pasted link to Sessions', () => {
    expect(shortcutTarget(key('Escape'), route('#n=session:p:claude:s&from=attention'))).toEqual(
      top('attention'),
    );
    expect(shortcutTarget(key('Escape'), route('#n=session:p:claude:s&from=intent'))).toEqual(
      top('intent'),
    );
    expect(shortcutTarget(key('Escape'), route('#n=session:p:claude:s&from=sessions'))).toEqual(
      top('sessions'),
    );
    expect(shortcutTarget(key('Escape'), route('#n=session:p:claude:s'))).toEqual(top('sessions'));
  });

  it('walks a session opened from a project up to that project, as the crumb’s last link does', () => {
    expect(shortcutTarget(key('Escape'), route('#n=session:alpha:claude:s&from=project'))).toEqual({
      view: 'project',
      project: 'alpha',
      session: null,
    });
    expect(shortcutTarget(key('Escape'), route('#n=session:alpha:claude:s&from=projects'))).toEqual(
      {
        view: 'project',
        project: 'alpha',
        session: null,
      },
    );
  });

  it('has no project page to walk up to for a session with no project label, so it goes to Projects', () => {
    expect(shortcutTarget(key('Escape'), route('#n=session::claude:s&from=projects'))).toEqual(
      top('projects'),
    );
  });
});

describe('a, p and s open the top-level views', () => {
  it.each([
    ['a', 'attention'],
    ['A', 'attention'],
    ['p', 'projects'],
    ['P', 'projects'],
    ['s', 'sessions'],
    ['S', 'sessions'],
  ])('%s opens %s', (letter, view) => {
    expect(shortcutTarget(key(letter), route('#n=intent'))).toEqual(top(view));
  });

  it('ignores every other key, including the retired dashboard key', () => {
    for (const letter of ['d', 'x', 'Enter', ' ', 'Tab', 'ArrowLeft']) {
      expect(shortcutTarget(key(letter), route('#n=intent')), letter).toBeNull();
    }
  });
});

describe('a shortcut never fires where the reader is typing or using a modifier', () => {
  it.each(['INPUT', 'SELECT', 'TEXTAREA', 'input'])('is ignored over a %s', (tagName) => {
    for (const k of ['a', 'p', 's', 'Escape'])
      expect(shortcutTarget(key(k, { tagName }), route('#n=intent')), `${tagName} ${k}`).toBeNull();
  });

  it('is ignored over editable content', () => {
    expect(shortcutTarget(key('a', { isContentEditable: true }), route('#n=intent'))).toBeNull();
  });

  it.each(['metaKey', 'ctrlKey', 'altKey'] as const)('is ignored with %s held', (modifier) => {
    for (const k of ['a', 'p', 's', 'Escape'])
      expect(shortcutTarget(key(k, { [modifier]: true }), route('#n=intent'))).toBeNull();
  });

  it('leaves a key another handler already took, such as Escape closing a popover', () => {
    expect(
      shortcutTarget(key('Escape', { defaultPrevented: true }), route('#n=session:p:claude:s')),
    ).toBeNull();
  });

  it('reads a capital letter as its lower case, which is how Shift types it', () => {
    expect(shortcutTarget(key('A'), route('#n=sessions'))).toEqual(top('attention'));
  });
});
