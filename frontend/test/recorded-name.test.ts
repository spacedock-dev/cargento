import { describe, expect, it } from 'vitest';
import { recordedName } from './recorded-name';

describe('the recorded product-name projection', () => {
  it('projects name spellings and storage keys without changing the recorded object', () => {
    const before = {
      'cargento.next.revision': 'Cargento uses CARGENTO_HOME',
      other: [null, false, 42, 'unchanged'],
    };
    expect(recordedName(before)).toEqual({
      'compass.next.revision': 'Compass uses COMPASS_HOME',
      other: [null, false, 42, 'unchanged'],
    });
    expect(before['cargento.next.revision']).toBe('Cargento uses CARGENTO_HOME');
  });

  it('returns renamed encoded inputs to their recorded spelling for lookup hashes', () => {
    const encoded = { $: 'map', v: [['compass.next.leader', 'Compass uses COMPASS_HOME']] };
    expect(recordedName(encoded, true)).toEqual({
      $: 'map',
      v: [['cargento.next.leader', 'Cargento uses CARGENTO_HOME']],
    });
  });
});
