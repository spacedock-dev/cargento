import { describe, expect, it } from 'vitest';
import { fakeBackend } from '../../test/storage_backends';
import {
  createLegacyStorage,
  goalKey,
  graphModeScope,
  guardrailKey,
  liveEstimateKey,
  memoKey,
} from '.';

const session = { harness: 'claude', sid: 'sid:1' };

/*
 * Legacy-valid values that a tidy-up on load would change: a 201-key usage object, sixty guardrails
 * with unusable rows among them, a graph map holding a retired entry, over-long text. Rollback
 * needs every one of them back unchanged, so reading must never write.
 */
function preloaded() {
  return fakeBackend({
    'cargento.projectUsage.v1': JSON.stringify(
      Object.fromEntries(Array.from({ length: 201 }, (_, i) => [`k${i}`, i + 1])),
    ),
    [guardrailKey('p')]: JSON.stringify([
      null,
      'plain',
      { text: '  padded  ', enabled: 0 },
      ...Array.from({ length: 60 }, (_, i) => `r${i}`),
    ]),
    'cargento.next.graph.mode': JSON.stringify({
      '': 'all',
      'p\u0000': 'decisions',
      'x\u0000y\u0000z': 'all',
    }),
    [memoKey('p', null, 'outcome')]: 'm'.repeat(700),
    [goalKey('p')]: '  untrimmed goal  ' + 'g'.repeat(800),
    'cargento.next.leader': '{"id":"someone","ts":"1"}',
    'cargento.next.revision': 'start.7',
    'cargento.next.usage.consent': 'garbled',
    'cargento.observer-model-consent.v1': 'granted',
    'cargento.next.workstream.collapsed': 'true',
    'cargento.projectCockpitProject': 'a project',
    [liveEstimateKey(session)]: '1',
  });
}

describe('reading storage', () => {
  it('writes nothing for any family, and leaves every raw value as legacy wrote it', () => {
    const backend = preloaded();
    const before = new Map(backend.data);
    const storage = createLegacyStorage(() => backend);

    storage.usage.counts();
    storage.guardrails.rules('p');
    storage.graphMode.resolve({ scope: graphModeScope('p', null) });
    storage.memo.read(memoKey('p', null, 'outcome'));
    storage.goal.read('p');
    storage.lease.read();
    storage.revision.read();
    storage.usageConsent.get();
    storage.observerConsent.get();
    storage.workstream.collapsed();
    storage.cockpitProject.read();
    storage.liveEstimate.on(session);
    // A poll or remount asks again; the second read must not write either.
    storage.usage.counts();
    storage.guardrails.rules('p');
    storage.graphMode.resolve({ scope: graphModeScope('p', null) });

    expect(backend.writes).toEqual([]);
    expect(new Map(backend.data)).toEqual(before);
  });

  it('keeps read-time normalisation in memory only', () => {
    const backend = preloaded();
    const storage = createLegacyStorage(() => backend);
    expect(Object.keys(storage.usage.counts())).toHaveLength(200);
    expect(storage.guardrails.rules('p')).toHaveLength(50);
    expect(storage.memo.read(memoKey('p', null, 'outcome'))).toHaveLength(500);
    expect(
      Object.keys(JSON.parse(backend.data.get('cargento.projectUsage.v1') ?? '{}') as object),
    ).toHaveLength(201);
    expect(backend.data.get(memoKey('p', null, 'outcome'))).toHaveLength(700);
  });
});
