import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  usedSelectors,
  uncoveredRules,
  ruleIdentity,
  sourceRules,
  coverageProblems,
} from './css-coverage.mjs';

test('a declaration used in any world retains the whole rule', () => {
  const text = '.a { color: red; padding: 8px } .b { color: blue }';
  const used = [...usedSelectors([{ text, ranges: [{ start: 6, end: 16 }] }])];
  assert.deepEqual(used, ['|.a|color:red;padding:8px']);
  const record = { used, pseudoMatches: [], exceptions: {} };
  assert.deepEqual(
    uncoveredRules('sheet.css', text, record).map((rule) => rule.selector),
    ['.b'],
  );
});
test('adding a dead rule fails even when the rest of the sheet is covered', () => {
  const record = { used: ['|.a|color:red'], pseudoMatches: [], exceptions: {} };
  assert.deepEqual(uncoveredRules('sheet.css', '.a{color:red}', record), []);
  assert.equal(
    uncoveredRules('sheet.css', '.a{color:red}.dead-mutation{color:red}', record).length,
    1,
  );
});
test('a used cascade-layer container cannot certify its unused children', () => {
  const text = '@layer legacy {.dead{color:red}.used{color:blue}}';
  const start = text.indexOf('.used');
  assert.deepEqual(
    [
      ...usedSelectors([
        {
          text,
          ranges: [
            { start: 7, end: text.length },
            { start, end: text.length - 1 },
          ],
        },
      ]),
    ],
    ['|.used|color:blue'],
  );
});
test('pseudo base matches retain state rules; named exceptions are exact', () => {
  const text = '@media print {.a:hover {color:red}.b {color:blue}}';
  const [first, second] = sourceRules(text);
  const record = {
    used: [],
    pseudoMatches: ['.a:hover'],
    exceptions: { [ruleIdentity('sheet.css', second)]: 'Print output is outside the screen proof' },
  };
  assert.deepEqual(uncoveredRules('sheet.css', text, record), []);
  delete record.exceptions[ruleIdentity('sheet.css', second)];
  assert.deepEqual(uncoveredRules('sheet.css', text, record), [second]);
  assert.equal(first.context, '@media print');
});

test('the current sheets retain no uncovered rule or unexplained exception', async () => {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const record = JSON.parse(
    await readFile(new URL('../css-coverage.json', import.meta.url), 'utf8'),
  );
  assert.deepEqual(await coverageProblems(root, record), []);
});

test('a dead-rule mutation added to the current shell fails the coverage gate', async () => {
  const file = 'frontend/src/styles/shell.css';
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const record = JSON.parse(
    await readFile(new URL('../css-coverage.json', import.meta.url), 'utf8'),
  );
  const text = await readFile(`${root}${file}`, 'utf8');
  const dead = uncoveredRules(
    file,
    `${text}\n@layer legacy {.next-css-dead-mutation{color:red}}`,
    record,
  );
  assert.deepEqual(
    dead.map((rule) => rule.selector),
    ['.next-css-dead-mutation'],
  );
});
