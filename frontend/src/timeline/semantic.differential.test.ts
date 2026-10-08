import { describe, expect, it } from 'vitest';
import { genCase } from './generate.test.helper';
import { legacyEmptyText, legacyRows, loadLegacyTimeline } from './legacy.test.helper';
import { buildRegistry, eventsForMode, historyEmptyText, readSemantic, type Delegation, type GraphMode } from './semantic';

/* Which events each mode keeps is what the reader's choice means, so it is held to the legacy file that
   decides it. Generated semantic payloads run through the real `projectSemanticTimeline` and through the
   port, and the two must draw the same events, in the same order, in the same lane, with the same "current"
   reading, in every mode and for a focused and an unfocused timeline. A failure names the seed. */
const legacy = loadLegacyTimeline();
const MODES: readonly GraphMode[] = ['active', 'all', 'decisions'];
const SEEDS = 500;

function mine(seed: number, mode: GraphMode) {
  const generated = genCase(seed);
  const model = readSemantic(generated.semantic);
  const registry = buildRegistry({
    model,
    delegations: generated.delegations as unknown as Delegation[],
    focus: generated.focus,
    ...(generated.origins ? { origins: generated.origins } : {}),
    fallbackSession: generated.fallbackSession,
  });
  const events = eventsForMode(model, registry, mode, generated.focus);
  return {
    model,
    rows: events.map((event) => ({
      eventId: event.eventId,
      kind: event.kind,
      lane: event.lane.key,
      current: event.lane.kind === 'task' ? String(event.lane.current) : null,
    })),
  };
}

function theirs(seed: number, mode: GraphMode) {
  const generated = genCase(seed);
  legacy.setScope('alpha', generated.fallbackSession || null);
  const html = legacy.timeline({ generated: 1000 }, generated.semantic, generated.delegations, generated.focus, generated.origins, { mode, controls: false });
  return { html, rows: legacyRows(html) };
}

describe('the events each activity mode keeps', () => {
  for (const mode of MODES) {
    it(`agree with the legacy timeline over ${String(SEEDS)} generated payloads in ${mode}`, () => {
      const failures: string[] = [];
      for (let seed = 1; seed <= SEEDS; seed += 1) {
        const old = theirs(seed, mode);
        const port = mine(seed, mode);
        if (JSON.stringify(old.rows) !== JSON.stringify(port.rows)) {
          failures.push(`seed ${String(seed)}\n legacy ${JSON.stringify(old.rows)}\n port   ${JSON.stringify(port.rows)}`);
        } else if (old.rows.length === 0) {
          const said = legacyEmptyText(old.html);
          const own = historyEmptyText(port.model, mode);
          if (said !== own.replace(/&/g, '&amp;')) failures.push(`seed ${String(seed)} empty text: ${String(said)} vs ${own}`);
        }
        if (failures.length >= 3) break;
      }
      expect(failures).toEqual([]);
    });
  }

  it('exercise every mode with and without rows, so the comparison is not vacuous', () => {
    const seen = { rows: 0, empty: 0, task: 0, direction: 0, decision: 0 };
    for (let seed = 1; seed <= SEEDS; seed += 1) {
      const rows = mine(seed, 'all').rows;
      if (rows.length) seen.rows += 1;
      else seen.empty += 1;
      if (rows.some((row) => row.lane.startsWith('task:'))) seen.task += 1;
      if (rows.some((row) => row.kind === 'direction')) seen.direction += 1;
      if (mine(seed, 'decisions').rows.some((row) => row.kind === 'decision')) seen.decision += 1;
    }
    expect(seen.rows).toBeGreaterThan(100);
    expect(seen.empty).toBeGreaterThan(5);
    expect(seen.task).toBeGreaterThan(50);
    expect(seen.direction).toBeGreaterThan(30);
    expect(seen.decision).toBeGreaterThan(30);
  });
});

describe('the activity filter agrees with the legacy filter', () => {
  it('resolves and stores per scope exactly as the legacy page does, including after a reload', () => {
    const scopes: [string, string | null][] = [['alpha', null], ['alpha', 'claude:s1'], ['beta', null], ['', null], ['beta', 'codex:s2']];
    legacy.storage.clear();
    legacy.reload();
    for (const [project, session] of scopes) {
      legacy.setScope(project, session);
      expect(legacy.resolveGraphMode()).toBe('active');
    }
    legacy.setScope('alpha', 'claude:s1');
    expect(legacy.setGraphMode('decisions')).toBe(true);
    legacy.setScope('beta', null);
    expect(legacy.setGraphMode('all')).toBe(true);
    legacy.setScope('beta', 'codex:s2');
    expect(legacy.setGraphMode('everything')).toBe(false);
    expect([...legacy.storage.entries()]).toEqual([['cargento.next.graph.mode', '{"alpha\\u0000claude:s1":"decisions","beta\\u0000":"all"}']]);
    legacy.reload();
    const after = scopes.map(([project, session]) => {
      legacy.setScope(project, session);
      return legacy.resolveGraphMode();
    });
    expect(after).toEqual(['active', 'decisions', 'all', 'active', 'active']);
  });
});
