import assert from 'node:assert/strict';
import { test } from 'node:test';
import { normaliseProjectContributors } from './project-deviations.mjs';

test('only contributor UI absences change while published task values stay exact', () => {
  const words = 'Inspect assignment unavailable and assignment source unavailable';
  assert.deepEqual(
    normaliseProjectContributors(
      {
        unbound: `assignment unavailable lead evidence assignment source unavailable ${words}`,
        rows: [{ text: words }],
        summary: words,
      },
      { assignment: words },
    ),
    {
      unbound: `task unavailable lead evidence task source unavailable ${words}`,
      rows: [{ text: words }],
      summary: words,
    },
  );
});
