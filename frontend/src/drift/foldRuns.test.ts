import { describe, expect, it } from 'vitest';
import { activityRow } from './activity.test.helper';
import { foldRuns, toolReportParts } from './workList';

const rows = () => [6, 5, 4, 3, 2, 1].map((n) => activityRow(n));
describe('a reader folds consecutive checks', () => {
  it('gets a fold at three checks and keeps a pair listed', () => {
    expect(foldRuns(rows().slice(0, 2)).map((item) => item.kind)).toEqual(['row', 'row']);
    expect(foldRuns(rows().slice(0, 3)).map((item) => item.kind)).toEqual(['run']);
  });
  it('always sees a failed check outside a fold, splitting the run', () => {
    const input = rows();
    input[3] = activityRow(3, { result: 'failed', resultSource: 'marker' });
    const items = foldRuns(input);
    expect(items.map((item) => item.kind)).toEqual(['run', 'row', 'row', 'row']);
    expect(items[1]).toEqual({ kind: 'row', row: input[3] });
  });
  it('always sees an earlier failure, a cited check, a finding entry and a written file', () => {
    for (const separator of [
      activityRow(3, { earlierFailed: true }),
      activityRow(3, {}, ['cited']),
      activityRow(3, { subject: 'file' }),
    ]) {
      const input = rows();
      input[3] = separator;
      expect(foldRuns(input).map((item) => item.kind)).toEqual(['run', 'row', 'row', 'row']);
    }
    expect(foldRuns(rows(), new Set(['c3'])).map((item) => item.kind)).toEqual([
      'run',
      'row',
      'row',
      'row',
    ]);
  });
  it('reads the counts, number range and newest to oldest times from the member rows', () => {
    const input = [
      activityRow(6, { result: 'passed', resultSource: 'flag' }),
      activityRow(5),
      activityRow(4, { beforeLastChange: true }),
    ];
    const item = foldRuns(input)[0];
    expect(item?.kind).toBe('run');
    if (item?.kind !== 'run') throw new Error('missing fold');
    expect(item.counts).toEqual({ passed: 1, failed: 0, unrecorded: 2 });
    expect(item.range).toBe('#4 to #6');
    expect(item.at).toBe('94s to 96s ago');
    expect(item.first).toBe(input[0]);
    expect(item.last).toBe(input[2]);
    expect(item.rows).toEqual(input);
    expect(foldRuns(input.map((row) => ({ ...row, at: '1m ago' })))[0]).toMatchObject({
      at: '1m ago',
    });
  });
  it('reads an unknown result as absence and retains the distinct reported result words', () => {
    for (const [result, resultSource, state, words] of [
      ['', '', 'unrecorded', 'Ran, result not recorded'],
      ['passed', 'flag', 'passed', 'Passed, as the tool reported'],
      ['passed', 'summary', 'passed', 'Passed, per its summary line'],
      ['failed', 'flag', 'failed', 'Failed, as the tool reported'],
      ['failed', 'summary', 'failed', 'Failed, per its summary line'],
      ['failed', 'marker', 'failed', 'Failed, per a failure line in its output'],
      ['passed', 'invented', 'unrecorded', 'Ran, result not recorded'],
    ] as const) {
      const parts = toolReportParts(activityRow(1, { result, resultSource }).entry);
      expect(parts.check).toMatchObject({ result: state, marks: [{ icon: state, words }] });
    }
  });
});
