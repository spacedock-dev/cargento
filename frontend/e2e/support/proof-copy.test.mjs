import assert from 'node:assert/strict';
import { test } from 'node:test';
import { copyProofPath } from './proof-copy.mjs';

test('scratch proof copies exclude result and cache directories on both path conventions', () => {
  for (const separator of [String.fromCharCode(92), '/']) {
    for (const directory of ['test-results', '__pycache__'])
      assert.equal(
        copyProofPath(['root', 'frontend', directory, 'capture.png'].join(separator)),
        false,
      );
    assert.equal(
      copyProofPath(['root', 'frontend', 'test-results-guide.mjs'].join(separator)),
      true,
    );
    assert.equal(copyProofPath(['root', 'frontend', 'src', 'main.tsx'].join(separator)), true);
  }
});
