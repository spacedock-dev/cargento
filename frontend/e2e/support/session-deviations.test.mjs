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
