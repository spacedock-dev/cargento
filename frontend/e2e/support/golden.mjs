/*
 * The record/replay seam between a browser proof and the legacy page it used to be compared against.
 *
 * A parity proof serves one synthetic board to the legacy page and to the React page and compares what a
 * reader sees. The legacy page is being deleted, so what it said is recorded once into
 * `frontend/test/golden/e2e/<proof>.json` and the React page stays held to those observations.
 *
 * `CARGENTO_LEGACY` chooses the mode:
 *   replay (default)  the legacy backend is never started and no legacy page is opened; `observe` returns the
 *                     stored value. This is what contributors and CI run.
 *   live              the legacy code runs and `observe` returns what it says now. When a golden already
 *                     exists for the key, the live reading must equal it, which is how the recording is proved
 *                     against the legacy code while that code exists. Nothing is written.
 *                     `CARGENTO_LEGACY_STRICT=1` also fails a reading with no golden, which proves the
 *                     recording is complete.
 *   record            like live, and the readings are written to the golden file once the proof has finished
 *                     without a failure. A proof with a failed step, or a run of some steps only, leaves the file untouched.
 *
 * Re-record (only possible while the legacy code exists), on an idle machine, and do it three times into
 * scratch directories to keep only what agrees:
 *   CARGENTO_LEGACY=record CARGENTO_GOLDEN_DIR=<scratch> node frontend/e2e/<proof>.mjs
 *
 * A key is the step name plus its label. The stored value is JSON: `undefined` is `null` in every mode, so
 * a proof sees one shape whichever mode ran. A replayed key that is absent, a key read twice, and a stored
 * key no run read all throw: a changed step, input or label fails loudly instead of comparing nothing.
 *
 * The seam holds the legacy side only. React-side assertions stay in the proof, strict in every mode.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const MODES = ['replay', 'record', 'live'];
export const MODE = process.env.CARGENTO_LEGACY || 'replay';
if (!MODES.includes(MODE))
  throw new Error(`CARGENTO_LEGACY must be one of ${MODES.join(', ')}; it is "${MODE}".`);

/* `live` with this set also fails a reading the golden has no answer for, which proves a golden is complete. */
const STRICT = process.env.CARGENTO_LEGACY_STRICT === '1';

/** True when the legacy backend and page must be started. False in replay: start neither. */
export const LEGACY_LIVE = MODE !== 'replay';

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

/** What a stored value looks like after a round trip: the same in every mode. */
export function jsonSafe(value) {
  return value === undefined ? null : JSON.parse(JSON.stringify(value));
}

/**
 * Volatile text out of a reading: loopback ports, clock times, ISO instants, long digit runs that are epoch
 * stamps. Applied to strings anywhere inside the value. A proof that has run-specific ids of its own passes a
 * further `scrub` to `observe`.
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
 * `observe(key, readLegacy, { scrub })`  the legacy reading for `key`; `readLegacy` runs in live and record
 *                                       modes only. `scrub` maps the raw reading to its stable form.
 * `verify(key, value)`                  assert that a React-side `value` equals the legacy observation
 *                                       `key` (read or replayed earlier in this run), with the key in the
 *                                       failure message.
 * `recorded(key)`                       the stored observation without reading anything (replay and live
 *                                       when a golden exists), or `undefined` when there is none.
 * `has(key)`                            whether the golden file carries `key`.
 */
export function goldenFor(proofName, { directory = process.env.CARGENTO_GOLDEN_DIR } = {}) {
  const target = join(directory || DEFAULT_DIRECTORY, `${proofName}.json`);
  const stored = new Map();
  if (MODE !== 'record') {
    let text;
    try {
      text = readFileSync(target, 'utf8');
    } catch (error) {
      if (MODE === 'replay' || error.code !== 'ENOENT') throw error;
    }
    if (text !== undefined) {
      const parsed = JSON.parse(text);
      assert.equal(parsed.proof, proofName, `${target} belongs to another proof.`);
      for (const [key, value] of Object.entries(parsed.observations)) stored.set(key, value);
    }
  }
  const seen = new Map();

  async function observe(key, readLegacy, { scrub = (value) => value } = {}) {
    if (seen.has(key)) throw new Error(`Golden key "${key}" was read twice in ${proofName}.`);
    let value;
    if (MODE === 'replay') {
      if (!stored.has(key))
        throw new Error(
          `No golden for "${key}" in ${proofName}: a step, input or label changed. ` +
            'Re-record while the legacy code exists (see support/golden.mjs).',
        );
      value = stored.get(key);
    } else {
      value = jsonSafe(normalise(scrub(await readLegacy())));
      if (MODE === 'live' && stored.has(key))
        assert.deepEqual(
          value,
          stored.get(key),
          `The legacy code no longer says what the golden "${key}" in ${proofName} recorded.`,
        );
      else if (MODE === 'live' && STRICT)
        throw new Error(
          `No golden for "${key}" in ${proofName}, and CARGENTO_LEGACY_STRICT is set.`,
        );
    }
    seen.set(key, value);
    return value;
  }

  return {
    mode: MODE,
    live: LEGACY_LIVE,
    observe,
    verify(key, value) {
      assert.ok(seen.has(key), `verify("${key}") before it was observed in ${proofName}.`);
      assert.deepEqual(jsonSafe(normalise(value)), seen.get(key), `${proofName}: ${key}`);
    },
    recorded: (key) => (stored.has(key) ? stored.get(key) : undefined),
    has: (key) => stored.has(key),
    /**
     * Replay: every stored key must have been read. Record: write the file. `complete: false` is a run of
     * some steps only (`CARGENTO_E2E_STEPS`) or one that failed: it neither writes nor checks, because a
     * partial recording would drop the keys of the steps that did not run.
     */
    finish({ complete = true } = {}) {
      if (!complete) return;
      if (MODE === 'record') {
        mkdirSync(dirname(target), { recursive: true });
        const body = {
          proof: proofName,
          // Key order is kept as the proof built it, because a proof compares a replayed reading with a live one by
          // `JSON.stringify`. The step order is the proof's own, so a recording is still byte-stable.
          observations: Object.fromEntries(seen),
        };
        const scratch = `${target}.${process.pid}.tmp`;
        writeFileSync(scratch, `${JSON.stringify(body, null, 1)}\n`);
        renameSync(scratch, target);
        return;
      }
      if (MODE === 'replay') {
        const unread = [...stored.keys()].filter((key) => !seen.has(key));
        if (unread.length)
          throw new Error(
            `${proofName} never read ${unread.length} golden key(s): ${unread.slice(0, 5).join(', ')}. ` +
              'A step was removed or renamed; re-record while the legacy code exists.',
          );
      }
    },
  };
}
