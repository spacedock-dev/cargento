import { describe, expect, it } from 'vitest';
import { formatDuration } from './format';

describe('a duration reads in its two largest units', () => {
  it.each([
    [0, '0s'],
    [59.9, '59s'],
    [60, '1m'],
    [3599, '59m'],
    [3600, '1h 0m'],
    [3661, '1h 1m'],
    [86399, '23h 59m'],
    [86400, '1d 0h'],
    [90061, '1d 1h'],
  ])('%s seconds is %s', (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });

  it('is null for what is not a duration, so a caller states an absence rather than a figure', () => {
    for (const value of [-1, Number.NaN, Number.POSITIVE_INFINITY, '5', null, undefined]) {
      expect(formatDuration(value)).toBeNull();
    }
  });
});
