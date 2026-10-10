import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { normaliseButtonKey } from '../e2e/support/button-chrome.mjs';
import { normaliseButtonTable } from './normalise-button-chrome.mjs';

const key = (name) => `next-project | next-activity-card | ${name} | | disabled=false hidden=false`;

test('elapsed seconds, minutes, hours and days cannot change a Button identity', () => {
  for (const [name, expected] of [
    ['codexIdle and recentlast active 52s ago', 'codexIdle and recentlast active <time> ago'],
    ['codexIdle and recentlast active 1m ago', 'codexIdle and recentlast active <time> ago'],
    [
      'Needs a decisionagent, 1m: Choose how to continue',
      'Needs a decisionagent, <time>: Choose how to continue',
    ],
    ['last active 52m ago', 'last active <time> ago'],
    ['in 3m', 'in <time>'],
    ['last active 2h ago', 'last active <time> ago'],
    ['last active 3d ago', 'last active <time> ago'],
    ['Retrylead4mchild1mfinished15m', 'Retrylead<time>child<time>finished<time>'],
    ['turn 1h 30m · 2m estimated remaining', 'turn <time> · <time> estimated remaining'],
    ['in 2 minutes · 1.5 seconds elapsed', 'in <time> · <time> elapsed'],
    ['Approve the retry plan?0s', 'Approve the retry plan?<time>'],
    ['Approve the retry plan?3s', 'Approve the retry plan?<time>'],
  ]) {
    assert.equal(normaliseButtonKey(key(name)), key(expected), name);
  }
});

test('normalising time preserves fixture counts, duration window names and identity attributes', () => {
  for (const name of [
    '2 reported blocks',
    '2 decisions',
    '3 sessions',
    '4 models',
    'Course1010 observed state changes',
    'Remove line 2',
    '1,234 /m',
    'Read Codex 5-hour window',
  ]) {
    assert.equal(normaliseButtonKey(key(name)), key(name));
  }
  const identity =
    'next-3m | ctl-4h | Read in 3m | data-control=5s aria-pressed=true | disabled=false hidden=false';
  assert.equal(
    normaliseButtonKey(identity),
    'next-3m | ctl-4h | Read in <time> | data-control=5s aria-pressed=true | disabled=false hidden=false',
  );
  assert.equal(normaliseButtonKey(key('Read in <time>')), key('Read in <time>'));
});

test('the offline table already uses stable identities without losing a chrome profile', async () => {
  const table = JSON.parse(
    await readFile(new URL('../e2e/button-chrome-reference.json', import.meta.url), 'utf8'),
  );
  for (const [identity, profile] of Object.entries(table.instances)) {
    assert.equal(normaliseButtonKey(identity), identity);
    assert.ok(table.profiles[profile]);
  }
  assert.equal(table.profiles.length, 24);
});

test('offline normalisation merges equal profiles and refuses collisions with different chrome', () => {
  const table = {
    commit: 'original',
    profiles: [{ color: 'red' }, { color: 'red' }, { color: 'blue' }],
    instances: { [key('last active 52s ago')]: 0, [key('last active 1m ago')]: 1 },
  };
  const stable = normaliseButtonTable(table);
  assert.deepEqual(stable.instances, { [key('last active <time> ago')]: 0 });
  assert.deepEqual(stable.profiles, table.profiles);
  assert.equal(stable.commit, 'original');
  assert.throws(
    () =>
      normaliseButtonTable({
        ...table,
        instances: { ...table.instances, [key('last active 2h ago')]: 2 },
      }),
    /Button identity collision/,
  );
});
