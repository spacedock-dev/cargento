import assert from 'node:assert/strict';
import { test } from 'node:test';
import { projectChromeDifferences } from './project-chrome.mjs';

const row = (ratio = 1, kind = 'row', role = null) => ({
  key: 'surface',
  chrome: { color: 'rgb(205, 199, 180)' },
  inlineSize: { kind, ratio },
  role,
});
for (const invalid of [NaN, Infinity, -Infinity]) {
  for (const side of ['measured', 'expected']) {
    test(`${side} non-finite ratio ${invalid} fails`, () => {
      const actual = row(side === 'measured' ? invalid : 1);
      const expected = row(side === 'expected' ? invalid : 1);
      assert.equal(projectChromeDifferences([actual], { surface: expected }).length, 1);
    });
  }
}
test('row shrinkage fails even when every chrome property matches', () => {
  assert.equal(projectChromeDifferences([row(0.5)], { surface: row() }).length, 1);
  assert.deepEqual(projectChromeDifferences([row(0.99)], { surface: row() }), []);
});
test('text width tolerates font metrics without accepting a collapsed surface', () => {
  assert.deepEqual(projectChromeDifferences([row(1.1, 'text')], { surface: row(1, 'text') }), []);
  assert.equal(projectChromeDifferences([row(0.5, 'text')], { surface: row(1, 'text') }).length, 1);
});
test('a static message acquiring a live role fails', () => {
  assert.equal(projectChromeDifferences([row(1, 'row', 'status')], { surface: row() }).length, 1);
});
test('missing identities and changed ink fail', () => {
  assert.equal(projectChromeDifferences([row()], {}).length, 1);
  const changed = { ...row(), chrome: { color: 'rgb(255, 255, 255)' } };
  assert.equal(projectChromeDifferences([changed], { surface: row() }).length, 1);
});
