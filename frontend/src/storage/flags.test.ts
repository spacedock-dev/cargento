import { describe, expect, it } from 'vitest';
import { blockedBackend, fakeBackend, readOnlyBackend } from '../../test/storage_backends';
import { createLegacyStorage, liveEstimateKey, STORAGE_KEYS } from '.';

describe('live estimate family (cargento.next.live-estimate:)', () => {
  const session = { harness: 'claude', sid: 'a b:c' };

  it('keys on the unencoded harness:sid pair', () => {
    expect(liveEstimateKey(session)).toBe('cargento.next.live-estimate:claude:a b:c');
    expect(liveEstimateKey({ harness: 'codex', sid: 'a b:c' })).not.toBe(liveEstimateKey(session));
  });

  it('is on only for the raw word 1, and off removes the key', () => {
    const key = liveEstimateKey(session);
    const backend = fakeBackend();
    const { liveEstimate } = createLegacyStorage(() => backend);
    expect(liveEstimate.on(session)).toBe(false);
    liveEstimate.set(session, true);
    expect(backend.data.get(key)).toBe('1');
    liveEstimate.set(session, false);
    expect(backend.data.has(key)).toBe(false);
    for (const raw of ['0', 'true', 'on', '']) {
      const other = createLegacyStorage(() => fakeBackend({ [key]: raw }));
      expect(other.liveEstimate.on(session)).toBe(false);
    }
    expect(createLegacyStorage(() => fakeBackend({ [key]: '1' })).liveEstimate.on(session)).toBe(true);
  });

  it('lets the in-tab choice win over what storage later says', () => {
    const key = liveEstimateKey(session);
    const backend = fakeBackend();
    const { liveEstimate } = createLegacyStorage(() => backend);
    liveEstimate.set(session, false);
    backend.data.set(key, '1');
    expect(liveEstimate.on(session)).toBe(false);
  });

  it('keeps the switch for the tab when storage is blocked', () => {
    const { liveEstimate } = createLegacyStorage(() => blockedBackend());
    expect(liveEstimate.on(session)).toBe(false);
    expect(liveEstimate.set(session, true)).toBe(false);
    expect(liveEstimate.on(session)).toBe(true);
  });
});

describe('workstream collapse family (cargento.next.workstream.collapsed)', () => {
  const key = 'cargento.next.workstream.collapsed';

  it('is collapsed only for the raw word 1', () => {
    expect(Object.values(STORAGE_KEYS)).toContain(key);
    for (const [raw, expected] of [['1', true], ['0', false], ['true', false], ['', false]] as const) {
      expect(createLegacyStorage(() => fakeBackend({ [key]: raw })).workstream.collapsed()).toBe(expected);
    }
    expect(createLegacyStorage(() => fakeBackend()).workstream.collapsed()).toBe(false);
    expect(createLegacyStorage(() => blockedBackend()).workstream.collapsed()).toBe(false);
  });

  it('writes 1 or 0 and updates the tab before persisting', () => {
    const backend = fakeBackend();
    const { workstream } = createLegacyStorage(() => backend);
    expect(workstream.setCollapsed(true)).toBe(true);
    expect(backend.data.get(key)).toBe('1');
    workstream.setCollapsed(false);
    expect(backend.data.get(key)).toBe('0');
    const refused = createLegacyStorage(() => readOnlyBackend()).workstream;
    expect(refused.setCollapsed(true)).toBe(false);
    expect(refused.collapsed()).toBe(true);
  });

  it('reads storage once, as the legacy module does at load, then answers from the tab', () => {
    const backend = fakeBackend({ [key]: '1' });
    const { workstream } = createLegacyStorage(() => backend);
    expect(workstream.collapsed()).toBe(true);
    backend.data.set(key, '0');
    expect(workstream.collapsed()).toBe(true);
  });
});

describe('the twelve keys', () => {
  it('are spelled exactly as released', () => {
    expect(STORAGE_KEYS).toEqual({
      memoPrefix: 'cargento.cockpit.memo.v2:',
      graphMode: 'cargento.next.graph.mode',
      guardrailPrefix: 'cargento.next.guardrails.',
      leader: 'cargento.next.leader',
      liveEstimatePrefix: 'cargento.next.live-estimate:',
      revision: 'cargento.next.revision',
      usageConsent: 'cargento.next.usage.consent',
      workstreamCollapsed: 'cargento.next.workstream.collapsed',
      observerConsent: 'cargento.observer-model-consent.v1',
      cockpitProject: 'cargento.projectCockpitProject',
      goalPrefix: 'cargento.projectGoal.v1:',
      usage: 'cargento.projectUsage.v1',
    });
  });
});
