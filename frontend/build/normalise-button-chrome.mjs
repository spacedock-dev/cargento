import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { normaliseButtonKey } from '../e2e/support/button-chrome.mjs';

export function normaliseButtonTable(table) {
  const instances = {};
  for (const [key, profile] of Object.entries(table.instances)) {
    const stable = normaliseButtonKey(key);
    if (Object.hasOwn(instances, stable))
      assert.deepEqual(
        table.profiles[instances[stable]],
        table.profiles[profile],
        `Button identity collision: ${stable}`,
      );
    else instances[stable] = profile;
  }
  return { ...table, instances };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const path = new URL('../e2e/button-chrome-reference.json', import.meta.url);
  const table = JSON.parse(await readFile(path, 'utf8'));
  const stable = normaliseButtonTable(table);
  const json = JSON.stringify(stable, null, 2).replace(
    /[\u0080-\uffff]/g,
    (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`,
  );
  await writeFile(path, `${json}\n`);
  console.log(
    `${Object.keys(table.instances).length} identities -> ${Object.keys(stable.instances).length}; profiles preserved`,
  );
}
