import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { gunzipSync, gzipSync } from 'node:zlib';
import { afterAll, expect } from 'vitest';

/* Golden records of what the legacy page computes, so the React port stays held to the legacy page after the
   legacy page is gone.

   The differential tests run the real legacy functions in a `vm` beside the TypeScript port and compare the
   two over generated inputs. Every legacy loader is wrapped here, and the wrapper is the one place that
   decides whether the legacy code runs at all. `CARGENTO_LEGACY` picks the mode:

     replay (default)  The legacy code is not read and not run. Each answer comes from the golden file of the
                       test file that asks. A call with no recorded answer fails with the name of the call:
                       a changed generator, input or step has to be re-recorded, never passed silently.
     live              The legacy code runs, as it did before this seam existed, and every answer is checked
                       against the golden. A mismatch means the golden no longer says what the legacy page
                       says. `CARGENTO_LEGACY_STRICT=1` also fails a call the golden has no answer for, which
                       proves a golden is complete.
     record            The legacy code runs and the answers are written to
                       `frontend/test/golden/vitest/<test file>.json.gz`. Two different answers to one key fail
                       the run: the call depends on state the wrapper cannot see.

   Re-record, while the legacy code exists, from the repository root. Record whole test files, never with
   `-t`: a file's golden is rewritten from the calls that run, so a filtered run would drop the rest.

     CARGENTO_LEGACY=record pnpm exec vitest run <test files>
     CARGENTO_LEGACY=live CARGENTO_LEGACY_STRICT=1 pnpm exec vitest run <test files>   # the proof

   A key is a hash of what the legacy side was asked: the harness, the method, its arguments and the state
   the earlier calls left it in. State is tracked as a hash and never read back from the page, so a method has
   to say how it changes state (see `HarnessSpec`). The state returns to where the module left it at the
   start of every test, so a test filtered by name asks for the same keys as it does in a full run.

   The generators stay deterministic (fixed seeds) so replay finds the keys it recorded. How many cases each
   differential runs is a `CASES` constant in the test, not a setting of the recorder: the committed goldens
   hold a few dozen to a hundred generated cases per differential, plus the hand-built edge cases, because
   the migration's thousands of cases proved the port equal once and the goldens only have to keep it so.
   A rare state the first seeds miss is reached by a named witness seed (`seedSample`) rather than by a
   thousand more seeds. A callback handed to the legacy code stands in a key by its source text, so
   reformatting one is a re-record. The goldens were checked against a clock moved 400 days on: nothing in
   them reads the wall clock.

   Answers are stored through one codec in every mode, including `live` and `record`, so a test cannot pass
   against a value a golden could not hold. The codec keeps what a JSON round trip would hide (`undefined`,
   `NaN`, `-0`, the infinities, `Set`, `Map`, `Date`, `RegExp`) and refuses what it cannot keep (a function). */

export type LegacyMode = 'live' | 'record' | 'replay';

export function legacyMode(): LegacyMode {
  const raw = process.env['CARGENTO_LEGACY'] ?? 'replay';
  if (raw === 'live' || raw === 'record' || raw === 'replay') return raw;
  throw new Error(`CARGENTO_LEGACY must be replay, record or live, not "${raw}".`);
}

/* ---- the codec ---- */

const SPECIAL = new Map<string, number>([
  ['NaN', Number.NaN],
  ['Infinity', Number.POSITIVE_INFINITY],
  ['-Infinity', Number.NEGATIVE_INFINITY],
  ['-0', -0],
]);

function tag(value: unknown): string {
  return Object.prototype.toString.call(value).slice(8, -1);
}

/* `callbacks` is for an argument: a function the legacy code is handed (a label builder) cannot be stored, so
   its source stands for it in the key. It is never allowed in an answer. */
export function encode(value: unknown, callbacks = false): unknown {
  if (value === undefined) return { $: 'u' };
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (Object.is(value, -0)) return { $: 'n', v: '-0' };
    if (!Number.isFinite(value)) return { $: 'n', v: String(value) };
    return value;
  }
  if (typeof value === 'function' && callbacks) return { $: 'fn', v: String(value) };
  if (typeof value !== 'object') {
    throw new Error(`A golden cannot hold a ${typeof value}.`);
  }
  switch (tag(value)) {
    case 'Array':
      return (value as unknown[]).map((item) => encode(item, callbacks));
    case 'Set':
      return { $: 'set', v: [...(value as Set<unknown>)].map((item) => encode(item, callbacks)) };
    case 'Map':
      return {
        $: 'map',
        v: [...(value as Map<unknown, unknown>)].map(([key, item]) => [
          encode(key, callbacks),
          encode(item, callbacks),
        ]),
      };
    case 'Date':
      return { $: 'date', v: (value as Date).getTime() };
    case 'RegExp':
      return { $: 're', v: (value as RegExp).source, f: (value as RegExp).flags };
    case 'Object': {
      const out: Record<string, unknown> = {};
      for (const [key, item] of Object.entries(value)) out[key] = encode(item, callbacks);
      // A plain object that already has a `$` key would read back as a tagged value.
      return '$' in out ? { $: 'o', v: out } : out;
    }
    default:
      throw new Error(`A golden cannot hold a ${tag(value)}.`);
  }
}

export function decode(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(decode);
  if (typeof value !== 'object' || value === null) return value;
  const record = value as Record<string, unknown>;
  const marker = record['$'];
  if (typeof marker === 'string') {
    switch (marker) {
      case 'u':
        return undefined;
      case 'n':
        return SPECIAL.get(String(record['v']));
      case 'set':
        return new Set((record['v'] as unknown[]).map(decode));
      case 'map':
        return new Map(
          (record['v'] as [unknown, unknown][]).map(([k, v]) => [decode(k), decode(v)]),
        );
      case 'date':
        return new Date(record['v'] as number);
      case 're':
        return new RegExp(record['v'] as string, record['f'] as string);
      case 'o':
        // The fields of a plain object that had a `$` key of its own: read each as a field, not as a tag.
        return Object.fromEntries(
          Object.entries(record['v'] as Record<string, unknown>).map(([key, item]) => [
            key,
            decode(item),
          ]),
        );
      default:
        throw new Error(`An unknown golden tag "${marker}".`);
    }
  }
  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(record)) out[key] = decode(item);
  return out;
}

function digest(text: string): string {
  return createHash('sha1').update(text).digest('hex').slice(0, 12);
}

/* ---- the golden file of one test file ---- */

interface GoldenFile {
  readonly v: 1;
  /** key -> result digest. */
  readonly entries: Record<string, string>;
  /** result digest -> encoded result; one copy however many keys answer with it. */
  readonly results: Record<string, unknown>;
  /** digest -> a large subtree or string that results share, so a window that grows by one row costs one row. */
  readonly blobs: Record<string, unknown>;
}

// Smaller than this, a reference costs more than the copy it saves.
const BLOB_MIN = 160;

function intern(node: unknown, blobs: Map<string, unknown>): unknown {
  let out: unknown = node;
  if (Array.isArray(node)) out = node.map((item) => intern(item, blobs));
  else if (typeof node === 'object' && node !== null) {
    const copy: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(node)) copy[key] = intern(item, blobs);
    out = copy;
  } else if (typeof node !== 'string') return node;
  const text = JSON.stringify(out);
  if (text.length < BLOB_MIN) return out;
  const id = digest(text);
  blobs.set(id, out);
  return { $: 'ref', h: id };
}

function expand(node: unknown, blobs: ReadonlyMap<string, unknown>): unknown {
  if (Array.isArray(node)) return node.map((item) => expand(item, blobs));
  if (typeof node !== 'object' || node === null) return node;
  const record = node as Record<string, unknown>;
  if (record['$'] === 'ref') {
    const id = String(record['h']);
    if (!blobs.has(id)) throw new Error(`The golden file lacks the shared value ${id}.`);
    return expand(blobs.get(id), blobs);
  }
  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(record)) out[key] = expand(item, blobs);
  return out;
}

const GOLDEN_DIR = 'frontend/test/golden/vitest';

function testFile(): string {
  const worker = (globalThis as { __vitest_worker__?: { filepath?: string } }).__vitest_worker__;
  const path = worker?.filepath ?? expect.getState().testPath;
  if (!path) throw new Error('The golden seam could not tell which test file it serves.');
  return path;
}

function goldenPath(): string {
  const name = relative(resolve(process.cwd(), 'frontend/src'), testFile())
    .replaceAll('\\', '/')
    .replaceAll('/', '__');
  return resolve(process.cwd(), GOLDEN_DIR, `${name}.json.gz`);
}

class Goldens {
  private readonly entries = new Map<string, string>();
  private readonly results = new Map<string, unknown>();
  private readonly blobs = new Map<string, unknown>();
  private loaded = false;

  private load(): void {
    if (this.loaded) return;
    this.loaded = true;
    const path = goldenPath();
    if (legacyMode() === 'record' || !existsSync(path)) return;
    const file = JSON.parse(gunzipSync(readFileSync(path)).toString('utf8')) as GoldenFile;
    for (const [key, id] of Object.entries(file.entries)) this.entries.set(key, id);
    for (const [id, blob] of Object.entries(file.blobs)) this.blobs.set(id, blob);
    for (const [id, result] of Object.entries(file.results))
      this.results.set(id, expand(result, this.blobs));
  }

  has(key: string): boolean {
    this.load();
    return this.entries.has(key);
  }

  /** The recorded answer, as the codec holds it. */
  answer(key: string): string | undefined {
    this.load();
    const id = this.entries.get(key);
    return id === undefined ? undefined : JSON.stringify(this.results.get(id));
  }

  record(key: string, encoded: unknown): void {
    this.load();
    const text = JSON.stringify(encoded);
    const id = digest(text);
    const known = this.entries.get(key);
    if (known !== undefined && known !== id)
      throw new Error(
        `Two different legacy answers for one key (${key}): the call depends on state the golden seam cannot see. Declare how the method changes state in its HarnessSpec.`,
      );
    this.entries.set(key, id);
    this.results.set(id, encoded);
  }

  flush(): void {
    if (this.entries.size === 0) return;
    const path = goldenPath();
    const entries: Record<string, string> = {};
    for (const key of [...this.entries.keys()].sort())
      entries[key] = this.entries.get(key) as string;
    const used = new Set(Object.values(entries));
    const blobs = new Map<string, unknown>();
    const results: Record<string, unknown> = {};
    for (const id of [...used].sort()) results[id] = intern(this.results.get(id), blobs);
    const shared: Record<string, unknown> = {};
    for (const id of [...blobs.keys()].sort()) shared[id] = blobs.get(id);
    const file: GoldenFile = { v: 1, entries, results, blobs: shared };
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, gzipSync(Buffer.from(JSON.stringify(file)), { level: 9 }));
  }

  describe(): string {
    return relative(process.cwd(), goldenPath());
  }
}

const goldens = new Goldens();

// Registered at import, which happens while the test file is collected: a hook may not be added from a test.
if (legacyMode() === 'record') afterAll(() => goldens.flush());

/* ---- the wrapper ---- */

/** How a harness method treats the legacy page's state. A method not named is `append`. */
export interface HarnessSpec {
  /** Answers depend on the arguments alone (a pure method may also name a slot it overwrites). */
  readonly pure?: readonly string[];
  /** Answers depend on the state and leave it as it was. */
  readonly observe?: readonly string[];
  /** Replaces one named piece of state (`setData` replaces the data), whatever came before. */
  readonly slots?: Readonly<Record<string, string>>;
  /** Returns the page to its first state. */
  readonly reset?: readonly string[];
  /** Properties that read as a snapshot of the page's state. */
  readonly props?: readonly string[];
  /** Methods that return a promise. */
  readonly async?: readonly string[];
}

function currentTest(): string | undefined {
  return expect.getState().currentTestName;
}

export function legacyHarness<T extends object>(
  kind: string,
  load: () => T,
  spec: HarnessSpec = {},
): T {
  const mode = legacyMode();
  const strict = process.env['CARGENTO_LEGACY_STRICT'] === '1';
  let real: T | null = null;
  const page = (): T => (real ??= load());

  const baseline = { chain: 'first', slots: {} as Record<string, string> };
  let chain = baseline.chain;
  let slots: Record<string, string> = {};
  let lastTest: string | undefined;

  const arrive = (): void => {
    const test = currentTest();
    if (test === lastTest) return;
    lastTest = test;
    // What setup left (module-level calls) is the state every test starts from.
    if (test !== undefined) {
      chain = baseline.chain;
      slots = { ...baseline.slots };
    }
  };
  const rebase = (): void => {
    if (currentTest() === undefined) {
      baseline.chain = chain;
      baseline.slots = { ...slots };
    }
  };
  const state = (): string =>
    digest(`${chain}|${JSON.stringify(slots, Object.keys(slots).sort())}`);

  const keyFor = (name: string, args: string, stateful: boolean): string =>
    digest(`${kind}|${name}|${args}|${stateful ? state() : ''}`);

  const answer = <R>(key: string, label: string, run: () => R): R => {
    if (mode === 'replay') {
      const stored = goldens.answer(key);
      if (stored === undefined)
        throw new Error(
          `No golden for ${kind}.${label} in ${goldens.describe()}. A generator, an input or a step changed: re-record while the legacy code exists (see frontend/test/legacy_goldens.ts).`,
        );
      return decode(JSON.parse(stored)) as R;
    }
    const encoded = encode(run());
    const text = JSON.stringify(encoded);
    if (mode === 'record') goldens.record(key, encoded);
    else {
      const stored = goldens.answer(key);
      if (stored === undefined) {
        if (strict) throw new Error(`The golden has no answer for ${kind}.${label}.`);
      } else if (stored !== text) {
        throw new Error(
          `The legacy page now answers ${kind}.${label} differently from its golden (${goldens.describe()}): ${text.slice(0, 160)} != ${stored.slice(0, 160)}`,
        );
      }
    }
    return decode(encoded) as R;
  };

  const pure = new Set(spec.pure);
  const observeOnly = new Set(spec.observe);
  const reset = new Set(spec.reset);
  const props = new Set(spec.props);
  const asyncMethods = new Set(spec.async);

  const invoke = (name: string, args: unknown[]): unknown => {
    arrive();
    const encodedArgs = JSON.stringify(encode(args, true));
    const isPure = pure.has(name);
    const stateful = !isPure;
    const key = keyFor(name, encodedArgs, stateful);
    const after = (): void => {
      const slot = spec.slots?.[name];
      if (reset.has(name)) {
        chain = baseline.chain;
        slots = { ...baseline.slots };
      } else if (slot !== undefined) slots = { ...slots, [slot]: digest(encodedArgs) };
      else if (isPure || observeOnly.has(name)) return;
      else chain = digest(`${chain}|${name}|${encodedArgs}`);
      rebase();
    };
    const run = (): unknown =>
      (page() as Record<string, (...a: unknown[]) => unknown>)[name]?.(...args);
    if (asyncMethods.has(name)) {
      if (mode === 'replay') {
        const result = answer(key, name, run);
        after();
        return Promise.resolve(result);
      }
      return (async () => {
        const pending = run();
        const result = await pending;
        const stored = answer(key, name, () => result);
        after();
        return stored;
      })();
    }
    const result = answer(key, name, () => {
      const value = run();
      if (
        value !== null &&
        typeof value === 'object' &&
        typeof (value as { then?: unknown }).then === 'function'
      )
        throw new Error(`${kind}.${name} returned a promise: list it under HarnessSpec.async.`);
      return value;
    });
    after();
    return result;
  };

  const snapshot = (name: string): unknown => {
    arrive();
    const key = keyFor(`prop:${name}`, '', true);
    return answer(key, `prop ${name}`, () => (page() as Record<string, unknown>)[name]);
  };

  return new Proxy({} as T, {
    get(_target, property) {
      if (typeof property !== 'string') return undefined;
      if (property === 'then') return undefined;
      if (props.has(property)) return snapshot(property);
      return (...args: unknown[]) => invoke(property, args);
    },
  });
}

/* ---- the number of generated cases ---- */

/** A differential's generated cases: the committed cap, or `envName` when the recorder or a developer asks. */
export function caseCount(cap: number, envName?: string): number {
  const asked = envName ? process.env[envName] : undefined;
  return asked === undefined || asked === '' ? cap : Number(asked);
}

/** The seeds a differential runs: 1..`cases`, then the `witnesses`, one seed each for a rare state the first
 *  seeds do not reach, found once by running the generator wide. Keeping them as named seeds lets the
 *  committed record stay small without losing the states the "agreement proves something" checks demand. */
export function seedSample(cases: number, witnesses: readonly number[] = []): number[] {
  const seeds = Array.from({ length: cases }, (_, index) => index + 1);
  for (const witness of witnesses)
    if (witness > cases && !seeds.includes(witness)) seeds.push(witness);
  return seeds;
}
