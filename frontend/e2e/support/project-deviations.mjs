import { renameProjectWords } from '../../test/projectWordDeviation.ts';

export function normaliseProjectContributors(record, evidence) {
  if (typeof record?.unbound !== 'string') return record;
  return {
    ...record,
    unbound: renameProjectWords(record.unbound, true, evidence, 'Latest instruction'),
  };
}
