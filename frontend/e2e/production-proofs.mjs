/*
 * Runs the eleven parity proofs with the React side served as the shipped bundle
 * (`CARGENTO_E2E_BUNDLE=production`, see `support/world.mjs`), one at a time, and says which failed.
 *
 *   pnpm test:production:browser                  every proof
 *   pnpm test:production:browser --shard a | b    half of them
 *
 * Any other argument prints the usage and exits 2 before a proof starts: a typo in a CI command must not run all
 * eleven on every shard. pnpm passes what follows the script name through, so there is no `--` in the command.
 *
 * The shards are `production-shards.json`, balanced from measured production-mode wall times
 * (a: shell 170 s, project 152 s, capacity 173 s; b: the other eight, 479 s) so the two CI legs finish
 * together. A test pins that the shards are disjoint and together name every parity proof, so a proof
 * cannot fall between them. Every proof runs even after one fails, because the second failure is the one
 * a contributor would otherwise find a CI round later.
 */
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const shards = JSON.parse(
  readFileSync(new URL('./production-shards.json', import.meta.url), 'utf8'),
);
const usage = (reason) => {
  console.error(
    `${reason}\nUsage: production-proofs.mjs [--shard ${Object.keys(shards).join('|')}]`,
  );
  process.exit(2);
};
const args = process.argv.slice(2);
let wanted = null;
if (args.length === 2 && args[0] === '--shard') [, wanted] = args;
else if (args.length > 0) usage(`Unrecognised arguments: ${args.join(' ')}`);
if (wanted !== null && !Object.hasOwn(shards, wanted)) usage(`Unknown shard ${wanted}.`);

const scripts = wanted === null ? Object.values(shards).flat() : shards[wanted];
const root = fileURLToPath(new URL('../../', import.meta.url));
const failed = [];
for (const script of scripts) {
  const started = Date.now();
  console.log(`\n=== ${script} (production bundle) ===`);
  const result = spawnSync('pnpm', ['run', script], {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, CARGENTO_E2E_BUNDLE: 'production' },
  });
  const seconds = Math.round((Date.now() - started) / 1000);
  console.log(`=== ${script}: ${result.status === 0 ? 'ok' : 'FAILED'} in ${seconds}s ===`);
  if (result.status !== 0) failed.push(script);
}
if (failed.length) {
  console.error(`\nProduction bundle proofs failed: ${failed.join(', ')}`);
  process.exitCode = 1;
}
