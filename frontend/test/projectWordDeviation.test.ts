import { describe, expect, it } from 'vitest';
import { projectWordDeviation } from './projectWordDeviation';

describe('UI wording deviations preserve evidence', () => {
  it('preserves titles, instructions and saved words while changing project UI fields', () => {
    const words = 'Fix COMMAND parsing';
    expect(
      projectWordDeviation(
        {
          title: words,
          instruction: words,
          saved: words,
          strip: `COMMAND${words}Direction shown in assignment`,
          panel: words,
        },
        false,
        { instruction: words },
      ),
    ).toEqual({
      title: words,
      instruction: words,
      saved: words,
      strip: `Needs you${words}Direction shown in the current task`,
      panel: words,
    });
  });
});
