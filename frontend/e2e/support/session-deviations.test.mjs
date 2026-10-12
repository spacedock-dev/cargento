import assert from 'node:assert/strict';
import { test } from 'node:test';
import { normaliseSessionRecord } from './session-deviations.mjs';

test('session deviations preserve quoted titles and instructions', () => {
  const words = 'Fix ASSIGNMENT parsing';
  assert.deepEqual(
    normaliseSessionRecord(
      {
        title: words,
        saved: ['Copy session ID a'],
        metadata: { header: 'Copy link', text: words },
        groups: [{ rows: [{ text: `ASSIGNMENT · ${words}` }] }],
      },
      { instruction: words },
    ),
    {
      title: words,
      saved: ['Copy session ID a'],
      metadata: { header: 'Copy link', text: words },
      groups: [{ rows: [{ text: `Current task · ${words}` }] }],
    },
  );
});

test('a reader sees a published session age in the projected recorded header only', () => {
  const evidence = {
    generated: 1900000000,
    sessions: [
      { harness: 'claude', sid: 's1', project: 'alpha/app', started_at: 1900000000 - 23 * 3600 },
    ],
  };
  const record = {
    attrs: ['s1', 'idle', 'quiet', false],
    header: 'State: idleSyntheticclaude · s1 · 0 /m · alpha/appClaude Code · idle',
    metadata: { header: 'Same words' },
  };
  const projected = normaliseSessionRecord(record, evidence);
  assert.equal(
    projected.header,
    'State: idleSyntheticclaude · s1 · 0 /m · alpha/app · Started about 23h 0m agoClaude Code · idle',
  );
  assert.equal(projected.metadata.header, 'Same words');
  assert.equal(record.header.includes('Started about'), false);
  assert.equal(
    normaliseSessionRecord(record, {
      ...evidence,
      sessions: [{ ...evidence.sessions[0], started_at: null }],
    }).header.includes('Started about'),
    false,
  );
});
