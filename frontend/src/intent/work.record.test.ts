import { describe, expect, it } from 'vitest';
import { EMPTY_RECORD, type RecordEntry } from '../store/board';
import { olderEntriesRemain, recordPastWindow } from './work';

const loaded: RecordEntry = { ...EMPTY_RECORD, status: 'loaded', pages: 1, next: 'older' };
const entry = (at: number) =>
  ({
    fact_id: `f${String(at)}`,
    at,
    type: 'user_message',
  }) as unknown as RecordEntry['entries'][number];

describe('whether Show more can still bring in older entries', () => {
  it('is said only once a page has loaded and older entries remain', () => {
    expect(olderEntriesRemain(loaded, 100)).toBe(true);
    expect(olderEntriesRemain(loaded, null)).toBe(true);
  });

  it.each(['idle', 'loading', 'error', 'stale', 'unsupported'] as const)(
    'is not said while the record is %s',
    (status) => {
      expect(olderEntriesRemain({ ...loaded, status }, 100)).toBe(false);
    },
  );

  it('is not said with no record at all', () => {
    expect(olderEntriesRemain(undefined, 100)).toBe(false);
  });

  it('is not said once the record has reached its start', () => {
    expect(olderEntriesRemain({ ...loaded, reachedStart: true, next: null }, 100)).toBe(false);
  });

  it('is not said once an entry from before the window opened is listed', () => {
    const past = { ...loaded, entries: [entry(500), entry(90)] };
    expect(recordPastWindow(past, 100)).toBe(true);
    expect(olderEntriesRemain(past, 100)).toBe(false);
    expect(olderEntriesRemain({ ...loaded, entries: [entry(500), entry(150)] }, 100)).toBe(true);
  });

  it('never treats an unknown window as passed', () => {
    expect(recordPastWindow({ ...loaded, entries: [entry(1)] }, null)).toBe(false);
    expect(recordPastWindow(undefined, 100)).toBe(false);
  });
});
