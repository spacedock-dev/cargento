import { describe, expect, it } from 'vitest';
import { blockedBackend, fakeBackend, readOnlyBackend } from '../../test/storage_backends';
import { createLegacyStorage, decodeGuardrails, guardrailKey, normalizeGuardrail } from '.';

describe('guardrail family (cargento.next.guardrails.)', () => {
  it('keys on the encoded project', () => {
    expect(guardrailKey('my project/é')).toBe('cargento.next.guardrails.my%20project%2F%C3%A9');
  });

  it('accepts the older plain-string rules as enabled', () => {
    expect(decodeGuardrails('["watch tests", {"text":"b","enabled":false}]')).toEqual([
      { enabled: true, text: 'watch tests' },
      { enabled: false, text: 'b' },
    ]);
  });

  it('disables only on an explicit false and drops empty or invalid rules', () => {
    const raw = JSON.stringify([
      { text: 'a', enabled: 0 },
      { text: 'b', enabled: null },
      { text: '   ' },
      { text: 5 },
      null,
      7,
      [],
      { enabled: true },
      { text: 'c', enabled: false },
    ]);
    expect(decodeGuardrails(raw)).toEqual([
      { enabled: true, text: 'a' },
      { enabled: true, text: 'b' },
      { enabled: false, text: 'c' },
    ]);
  });

  it('trims and cuts at 500 UTF-16 units, splitting a surrogate pair at the cut', () => {
    const rule = normalizeGuardrail('  ' + 'a'.repeat(499) + '😀 tail  ');
    expect(rule?.text).toHaveLength(500);
    expect(rule?.text.charCodeAt(499)).toBe(0xd83d);
    expect(normalizeGuardrail('x'.repeat(501))?.text).toHaveLength(500);
  });

  it('keeps the first fifty valid rules when more are stored', () => {
    const rules = [null, null, ...Array.from({ length: 60 }, (_, index) => `rule ${index}`)];
    const loaded = decodeGuardrails(JSON.stringify(rules));
    expect(loaded).toHaveLength(50);
    expect(loaded[0]?.text).toBe('rule 0');
    expect(loaded[49]?.text).toBe('rule 49');
  });

  it('reads corrupt JSON and non-arrays as no rules', () => {
    expect(decodeGuardrails('{not json')).toEqual([]);
    expect(decodeGuardrails('{"text":"a"}')).toEqual([]);
    expect(decodeGuardrails('"a"')).toEqual([]);
    expect(decodeGuardrails(null)).toEqual([]);
  });

  it('writes rules in the released JSON shape and keeps the last fifty when adding', () => {
    const backend = fakeBackend();
    const { guardrails } = createLegacyStorage(() => backend);
    const added = guardrails.add('p', '  first  ');
    expect(added.persisted).toBe(true);
    expect(backend.data.get(guardrailKey('p'))).toBe('[{"enabled":true,"text":"first"}]');
    for (let index = 0; index < 60; index += 1) guardrails.add('p', `r${index}`);
    const stored = JSON.parse(backend.data.get(guardrailKey('p')) ?? '[]') as { text: string }[];
    expect(stored).toHaveLength(50);
    expect(stored[0]?.text).toBe('r10');
    expect(stored[49]?.text).toBe('r59');
  });

  it('refuses an empty rule without touching storage', () => {
    const backend = fakeBackend();
    const { guardrails } = createLegacyStorage(() => backend);
    expect(guardrails.add('p', '   ').rules).toEqual([]);
    expect(backend.writes).toEqual([]);
  });

  it('toggles by index and persists, ignoring an index that names no rule', () => {
    const backend = fakeBackend({ [guardrailKey('p')]: '["a","b"]' });
    const { guardrails } = createLegacyStorage(() => backend);
    expect(guardrails.toggle('p', 1).rules).toEqual([
      { enabled: true, text: 'a' },
      { enabled: false, text: 'b' },
    ]);
    expect(backend.data.get(guardrailKey('p'))).toBe(
      '[{"enabled":true,"text":"a"},{"enabled":false,"text":"b"}]',
    );
    const before = backend.writes.length;
    expect(guardrails.toggle('p', 5).rules).toHaveLength(2);
    expect(guardrails.toggle('p', -1).rules).toHaveLength(2);
    expect(guardrails.toggle('p', 0.5).rules).toHaveLength(2);
    expect(backend.writes).toHaveLength(before);
  });

  it('serves later reads from tab memory so a failed write or read does not lose rules', () => {
    const { guardrails } = createLegacyStorage(() => readOnlyBackend());
    const change = guardrails.add('p', 'kept');
    expect(change.persisted).toBe(false);
    expect(guardrails.rules('p')).toEqual([{ enabled: true, text: 'kept' }]);
    const blocked = createLegacyStorage(() => blockedBackend()).guardrails;
    expect(blocked.rules('p')).toEqual([]);
    expect(blocked.add('p', 'still works').rules).toEqual([{ enabled: true, text: 'still works' }]);
  });

  it('does not hand out its internal array', () => {
    const { guardrails } = createLegacyStorage(() => fakeBackend());
    const first = guardrails.add('p', 'a').rules;
    guardrails.add('p', 'b');
    expect(first).toHaveLength(1);
  });
});
