// @vitest-environment node
/* The reasons a route can give a session, held between the producer and the stories. `reading_route.REASONS`
   is the closed set the server publishes as `reading_routes[harness].reason`; `drift.reasons.ts` holds a
   fixture for each, and `Drift.stories.tsx` builds one story per reason with `routeStory('<reason>')`. A
   reason added to the producer and not to the fixtures and the stories fails here, and so does a story for a
   reason the producer no longer has.

   The producer's list is read from its Python source, because nothing in this toolchain imports Python and
   the vocabulary fixture does not carry routes. The read fails closed: a source this file cannot parse is an
   error, never an empty set that agrees with an empty set. Every reason reaches the page with its own copy: a
   reason with no reader replaces Analyze with its note, and one with a reader says why that reader in "What
   is sent", so none is exempt. */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { REASON_CASES, routeFor } from './drift.reasons';

const source = readFileSync(
  new URL('../../compass/skills/compass/compass_runtime/reading_route.py', import.meta.url),
  'utf8',
);
const stories = readFileSync(new URL('./Drift.stories.tsx', import.meta.url), 'utf8');

const sorted = (values: Iterable<string>): string[] => [...values].sort();

/* `REASON_OWN_HARNESS = "own-harness"` and the tuple that lists the names. */
function producerReasons(): string[] {
  const values = new Map(
    [...source.matchAll(/^(REASON_[A-Z_]+) = "([a-z-]+)"$/gm)].map((m) => [m[1], m[2]] as const),
  );
  const tuple = /^REASONS = \(\n((?:\s+REASON_[A-Z_]+,\n)+)\)$/m.exec(source);
  if (!tuple?.[1]) throw new Error('reading_route.REASONS is not in the shape this guard reads');
  const names = [...tuple[1].matchAll(/REASON_[A-Z_]+/g)].map((m) => m[0]);
  return names.map((name) => {
    const value = values.get(name);
    if (!value) throw new Error(`${name} has no string value this guard can read`);
    return value;
  });
}

describe('the route reasons the stories cover', () => {
  it('reads a non-empty producer list', () => {
    expect(producerReasons().length).toBeGreaterThanOrEqual(8);
  });

  it('are the reasons the producer can publish, no more and no fewer', () => {
    expect(sorted(Object.keys(REASON_CASES))).toEqual(sorted(producerReasons()));
  });

  it('each have a story built for them, and no story is built for another', () => {
    const built = [...stories.matchAll(/routeStory\(\s*'([a-z-]+)',?\s*\)/g)].map(
      (m) => m[1] ?? '',
    );
    expect(sorted(built)).toEqual(sorted(producerReasons()));
    expect(new Set(built).size).toBe(built.length);
  });

  it('publish a route whose reader is named exactly when the fixture says it has one', () => {
    for (const [reason, found] of Object.entries(REASON_CASES)) {
      const route = routeFor(reason);
      expect(route['reason']).toBe(reason);
      expect(route['provider']).toBe(found.provider);
      expect(Boolean(route['disclosure'])).toBe(found.provider !== '');
    }
  });

  it('word each note as the producer does', () => {
    for (const fragment of [
      "This session's own harness reads it.",
      'This harness has no reading producer of its own',
      'checks are not qualified on this build',
      'CLI was not found on this machine',
      ', so no analysis can run for this session.',
      ', so {LABELS[other]} reads this session.',
    ]) {
      expect(source, fragment).toContain(fragment);
    }
  });
});
