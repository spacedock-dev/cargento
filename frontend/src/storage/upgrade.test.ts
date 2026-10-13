import { describe, expect, it } from 'vitest';
import { fakeBackend } from '../../test/storage_backends';
import { createLegacyStorage, STORAGE_KEYS } from '.';
import { storageAccess } from './backend';

describe('a reader who upgraded', () => {
  it.each(Object.values(STORAGE_KEYS))(
    'keeps the saved value in %s without changing the old key',
    (key) => {
      const old = key.replace(/^compass/, 'cargento');
      const backend = fakeBackend({ [old]: 'saved' });
      const access = storageAccess(() => backend);
      expect(access.attempt((store) => store.getItem(key))).toEqual({ ok: true, value: 'saved' });
      access.attempt((store) => store.setItem(key, 'new'));
      expect(access.attempt((store) => store.getItem(key))).toEqual({ ok: true, value: 'new' });
      expect(backend.data.get(old)).toBe('saved');
      expect(storageAccess(() => fakeBackend()).attempt((store) => store.getItem(key))).toEqual({
        ok: true,
        value: null,
      });
    },
  );

  it('keeps saved browser permission while a new refusal takes precedence', () => {
    const backend = fakeBackend({ 'cargento.observer-model-consent.v1': 'granted' });
    const store = createLegacyStorage(() => backend);
    expect(store.observerConsent.get()).toBe('granted');
    store.observerConsent.set('declined');
    expect(store.observerConsent.get()).toBe('declined');
    expect(backend.data.get('cargento.observer-model-consent.v1')).toBe('granted');
  });

  it('keeps a cleared legacy setting off when the reader opens another tab', () => {
    const key = `${STORAGE_KEYS.liveEstimatePrefix}pi:one`;
    const old = key.replace(/^compass/, 'cargento');
    const backend = fakeBackend({ [old]: '1' });
    const access = storageAccess(() => backend);
    access.attempt((store) => store.removeItem(key));
    expect(storageAccess(() => backend).attempt((store) => store.getItem(key))).toEqual({
      ok: true,
      value: '',
    });
    expect(backend.data.get(old)).toBe('1');
  });
});
