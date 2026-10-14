import { describe, expect, it } from 'vitest';
import { parseFragment } from '../router/grammar';
import { SAMPLE_FRAGMENT, isSampleRoute } from './ids';

describe('the sample session route', () => {
  it('is a session route the grammar reads back as the sample', () => {
    const route = parseFragment(SAMPLE_FRAGMENT);
    expect(route.view).toBe('session');
    expect(isSampleRoute(route)).toBe(true);
  });

  it('is not claimed by any other session, project or harness', () => {
    for (const fragment of [
      '#n=session:acme%2Fdashboard:claude:a1b2c3d4',
      '#n=session:other%2Fproject:claude:sample',
      '#n=session:acme%2Fdashboard:codex:sample',
      '#n=sessions',
      '#n=project:acme%2Fdashboard',
    ])
      expect(isSampleRoute(parseFragment(fragment))).toBe(false);
  });
});
