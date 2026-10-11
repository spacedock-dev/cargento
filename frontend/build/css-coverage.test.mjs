import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
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

for (const [name, used, pseudoMatches, text, identity, covered] of [
  ['used', ['|.a|color:red'], [], '.a{color:red}', 'frontend/sheet.css||.a', true],
  ['pseudo matched', [], ['.a:hover'], '.a:hover{color:red}', 'frontend/sheet.css||.a:hover', true],
  ['unused', [], [], '.a{color:red}', 'frontend/sheet.css||.a', false],
])
  test(`${name} exception ${covered ? 'must be removed' : 'remains valid'}`, async (t) => {
    const repository = fileURLToPath(new URL('../../', import.meta.url));
    const directory = join(repository, 'docs/screenshots');
    await mkdir(directory, { recursive: true });
    const root = await mkdtemp(join(directory, 'css-coverage-fixture-'));
    t.after(() => rm(root, { recursive: true, force: true }));
    await mkdir(join(root, 'frontend'));
    await writeFile(
      join(root, 'frontend/css-budget.json'),
      JSON.stringify({ files: ['frontend/sheet.css'] }),
    );
    await writeFile(join(root, 'frontend/sheet.css'), text);
    const baseline = JSON.parse(
      await readFile(join(repository, 'frontend/css-coverage.json'), 'utf8'),
    );
    const problems = await coverageProblems(root, {
      runs: baseline.runs,
      used,
      pseudoMatches,
      exceptions: { [identity]: 'This state is outside the screen proof fixtures.' },
    });
    if (covered) {
      assert.equal(problems.length, 1);
      assert.match(problems[0], /remove.*frontend\/css-coverage\.json/i);
      assert.ok(problems[0].includes(identity));
    } else assert.deepEqual(problems, []);
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
