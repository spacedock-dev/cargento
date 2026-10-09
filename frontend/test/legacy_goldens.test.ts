import { describe, expect, it } from 'vitest';
import { decode, encode, legacyHarness, legacyMode, seedSample } from './legacy_goldens';

/* The seam that stands in for the legacy page has to keep what a comparison reads, and has to refuse rather
   than guess. These tests need no golden file and no legacy code. */

const roundTrip = (value: unknown): unknown => decode(JSON.parse(JSON.stringify(encode(value))));

describe('the golden codec', () => {
  it('keeps the values a JSON round trip would hide', () => {
    expect(roundTrip(undefined)).toBeUndefined();
    expect(Number.isNaN(roundTrip(Number.NaN))).toBe(true);
    expect(Object.is(roundTrip(-0), -0)).toBe(true);
    expect(roundTrip(Number.POSITIVE_INFINITY)).toBe(Number.POSITIVE_INFINITY);
    expect(roundTrip(Number.NEGATIVE_INFINITY)).toBe(Number.NEGATIVE_INFINITY);
    expect(roundTrip(new Set([1, 'a']))).toEqual(new Set([1, 'a']));
    expect(roundTrip(new Map([['k', { v: 1 }]]))).toEqual(new Map([['k', { v: 1 }]]));
    expect(roundTrip(new Date(5))).toEqual(new Date(5));
    expect(roundTrip(/a\/b/giu)).toEqual(/a\/b/giu);
  });

  it('keeps an absent key apart from one that holds undefined, and a key named $', () => {
    const left = roundTrip({ a: undefined }) as Record<string, unknown>;
    expect('a' in left).toBe(true);
    expect('a' in (roundTrip({}) as Record<string, unknown>)).toBe(false);
    expect(roundTrip({ $: 'u', other: 1 })).toEqual({ $: 'u', other: 1 });
    expect(roundTrip([undefined, null, [Number.NaN]])).toHaveLength(3);
  });

  it('refuses a function in an answer, and takes one in an argument only by its source', () => {
    expect(() => encode(() => 1)).toThrow(/function/);
    expect(() => encode({ fn: () => 1 })).toThrow(/function/);
    expect(encode((line: number) => `from ${String(line)}`, true)).toEqual({
      $: 'fn',
      v: expect.stringContaining('from'),
    });
  });
});

describe('the seed sample', () => {
  it('is the first seeds and then the named witnesses past them, once each', () => {
    expect(seedSample(3, [2, 9, 9, 40])).toEqual([1, 2, 3, 9, 40]);
    expect(seedSample(2)).toEqual([1, 2]);
  });
});

describe.skipIf(legacyMode() !== 'replay')('replay', () => {
  it('never loads the legacy page, and fails with the name of a call that has no golden', () => {
    let loads = 0;
    const page = legacyHarness(
      'unit',
      () => {
        loads += 1;
        return { answer: (value: number) => value };
      },
      { pure: ['answer'] },
    );
    expect(() => page.answer(1)).toThrow(/No golden for unit\.answer/);
    expect(loads).toBe(0);
  });
});
