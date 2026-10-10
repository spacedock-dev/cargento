import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
test('the shipped sources satisfy the style policy', () => {
  const result = spawnSync(process.execPath, ['frontend/build/style-policy.mjs'], {
    cwd: root,
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
});

test('the scale scan rejects defaults and arbitrary type sizes with variants', async () => {
  const { scaleProblems } = await import('./style-policy.mjs');
  for (const token of [
    'text-sm',
    'hover:text-xl/6',
    'md:text-[14px]',
    'text-[length:var(--other)]',
    'rounded-lg',
    'bg-blue-500',
  ]) {
    assert.deepEqual(scaleProblems(`<div className="${token}" />`), [token]);
  }
  assert.deepEqual(
    scaleProblems(
      `<div className="text-body text-muted-foreground rounded-control text-center" />`,
    ),
    [],
  );
});

test('only components reachable from the shipped entry have importers', async () => {
  const { unusedUi } = await import('./style-policy.mjs');
  const copy = await mkdtemp(join(tmpdir(), 'cargento-ui-policy-'));
  try {
    await mkdir(join(copy, 'frontend/src/ui'), { recursive: true });
    await writeFile(
      join(copy, 'frontend/src/main.tsx'),
      'import { Used } from "@/ui/used"; import type { Orphan } from "@/ui/orphan"; Used();',
    );
    await writeFile(
      join(copy, 'frontend/src/ui/used.tsx'),
      'import "./helper"; export const Used = () => null;',
    );
    await writeFile(join(copy, 'frontend/src/ui/helper.ts'), 'export const helper = 1;');
    await writeFile(join(copy, 'frontend/src/ui/orphan.tsx'), 'export const Orphan = () => null;');
    await writeFile(join(copy, 'frontend/src/dead.tsx'), 'import "./ui/orphan";');
    assert.deepEqual(await unusedUi(copy), ['frontend/src/ui/orphan.tsx']);
  } finally {
    await rm(copy, { recursive: true, force: true });
  }
});

test('the PR cannot raise its CSS allowance even when its total matches', async () => {
  const { compareBase } = await import('./style-policy.mjs');
  const record = JSON.parse(await readFile(join(root, 'frontend/css-budget.json'), 'utf8'));
  assert.deepEqual(compareBase(record, record), []);
  assert.match(compareBase({ ...record, bytes: record.bytes + 1 }, record).join('\n'), /rose/);
  assert.match(
    compareBase(record, { ...record, files: record.files.slice(1) }).join('\n'),
    /counting/,
  );
  assert.deepEqual(compareBase({ ...record, bytes: record.bytes - 1 }, record), []);
});

test('the CSS count survives Windows checkout line endings and strips only the outer layer', async () => {
  const { cssBytes } = await import('./style-policy.mjs');
  assert.equal(
    cssBytes('@layer legacy {\r\n.a { color: red; }\r\n}\r\n'),
    Buffer.byteLength('.a { color: red; }\n'),
  );
  assert.equal(cssBytes('.a { color: red; }\n'), Buffer.byteLength('.a { color: red; }\n'));
});
