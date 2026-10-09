/*
 * The recorded observations a browser proof holds the React page to.
 *
 * A parity proof used to serve one synthetic board to the previous interface and to the React page and compare
 * what a reader sees. That interface is gone, so what it said was recorded once into
 * `frontend/test/golden/e2e/<proof>.json` and the React page stays held to those observations. They are
 * fixtures of record: the page that produced them no longer exists, so a proof cannot re-record one. A
 * deliberate departure from a recorded observation is an edit to the proof that says so, and an entry in the
 * design record.
 *
 * A key is the step name plus its label. The stored value is JSON: `undefined` is `null`, so a proof sees one
 * shape however it was written. A key that is absent, a key read twice, and a stored key no run read all throw:
 * a changed step, input or label fails loudly instead of comparing nothing.
 *
 * The seam holds the recorded side only. React-side assertions stay in the proof.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

/* A recording was made in one zone and locale, so every run reads the same clock and locale: UTC and en-US, for
   the Python backends (`dev/protocol.mjs` carries it), the browsers (`BROWSER_CONTEXT`) and this process. */
process.env.TZ = 'UTC';
export const BROWSER_CONTEXT = { timezoneId: 'UTC', locale: 'en-US' };

const DEFAULT_DIRECTORY = fileURLToPath(new URL('../../test/golden/e2e/', import.meta.url));

/* Sorted keys all the way down, so that two equal inputs have one digest whatever order they were built in. */
function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stable(value[key])]),
    );
  return value;
}

/**
 * A short digest of an input, for a key. A generated payload belongs in the key as its digest, so a generator
 * that starts producing something else misses the golden instead of being compared with another input's.
 */
export function digest(value) {
  return createHash('sha256')
    .update(typeof value === 'string' ? value : JSON.stringify(stable(value)))
    .digest('hex')
    .slice(0, 12);
}

/** What a stored value looks like after a round trip, so a React-side value is compared in the same shape. */
export function jsonSafe(value) {
  return value === undefined ? null : JSON.parse(JSON.stringify(value));
}

/**
 * Volatile text out of a reading: loopback ports and ISO instants, anywhere inside the value. The recordings
 * were normalised the same way, so a React-side reading is compared in the same form.
 */
export function normalise(value) {
  if (typeof value === 'string')
    return value
      .replace(/127\.0\.0\.1:\d+/g, '127.0.0.1:PORT')
      .replace(
        /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?/g,
        'ISO-INSTANT',
      );
  if (Array.isArray(value)) return value.map(normalise);
  if (value && typeof value === 'object')
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, normalise(item)]));
  return value;
}

/**
 * `goldenFor(proofName)`. Call `golden.finish({ complete })` once at the end; `complete` is false when a step
 * failed or only some steps ran.
 *
 * `observe(key)`        the recorded observation for `key`. It throws when there is none, and when it is read twice.
 * `verify(key, value)`  assert that a React-side `value` equals the observation `key` (read earlier in this run),
 *                       with the key in the failure message.
 * `recorded(key)`       the stored observation without marking it read, or `undefined` when there is none.
 * `has(key)`            whether the golden file carries `key`.
 */
export function goldenFor(proofName) {
  const target = join(DEFAULT_DIRECTORY, `${proofName}.json`);
  const parsed = JSON.parse(readFileSync(target, 'utf8'));
  assert.equal(parsed.proof, proofName, `${target} belongs to another proof.`);
  const stored = new Map(Object.entries(parsed.observations));
  const seen = new Map();

  function observe(key) {
    if (seen.has(key)) throw new Error(`Golden key "${key}" was read twice in ${proofName}.`);
    if (!stored.has(key))
      throw new Error(
        `No golden for "${key}" in ${proofName}: a step, input or label changed, and the page that ` +
          'recorded the observations no longer exists.',
      );
    const value = stored.get(key);
    seen.set(key, value);
    return value;
  }

  return {
    observe,
    verify(key, value) {
      assert.ok(seen.has(key), `verify("${key}") before it was observed in ${proofName}.`);
      assert.deepEqual(jsonSafe(normalise(value)), seen.get(key), `${proofName}: ${key}`);
    },
    recorded: (key) => (stored.has(key) ? stored.get(key) : undefined),
    has: (key) => stored.has(key),
    /**
     * Every stored key must have been read. `complete: false` is a run of some steps only (`CARGENTO_E2E_STEPS`)
     * or one that failed: it checks nothing, because the steps that did not run cannot have read their keys.
     */
    finish({ complete = true } = {}) {
      if (!complete) return;
      const unread = [...stored.keys()].filter((key) => !seen.has(key));
      if (unread.length)
        throw new Error(
          `${proofName} never read ${unread.length} golden key(s): ${unread.slice(0, 5).join(', ')}. ` +
            'A step was removed or renamed.',
        );
    },
  };
}
