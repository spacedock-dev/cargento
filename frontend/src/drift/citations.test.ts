import { describe, expect, it } from 'vitest';
import { citedIdsOf } from './citations';

describe('the ids a stored reading cites', () => {
  it('collects each id once, across every criterion', () => {
    expect(
      citedIdsOf({
        criteria: {
          goal: { cites: ['a', 'b'] },
          claims: { cites: ['b', 'c'] },
        },
      }),
    ).toEqual(['a', 'b', 'c']);
  });

  it('tolerates a reading with no criteria, a malformed row and an empty id', () => {
    expect(citedIdsOf(null)).toEqual([]);
    expect(citedIdsOf({})).toEqual([]);
    expect(citedIdsOf({ criteria: { goal: 'x', claims: { cites: 'nope' } } })).toEqual([]);
    expect(citedIdsOf({ criteria: { goal: { cites: ['', 'a'] } } })).toEqual(['a']);
  });
});
