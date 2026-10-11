import { describe, expect, it } from 'vitest';
import { instructionSourceDeviation, projectWordDeviation } from './projectWordDeviation';

describe('UI wording deviations preserve evidence', () => {
  it('renames only derived instruction source fields in the observed model', () => {
    expect(
      instructionSourceDeviation({
        sessions: [
          { ownGoalSrcText: 'claude · latest assignment', ownGoalText: 'latest assignment' },
        ],
        projects: [{ goalSrcText: 'codex · latest assignment', goalText: 'latest assignment' }],
        title: 'claude · latest assignment',
      }),
    ).toEqual({
      sessions: [
        { ownGoalSrcText: 'claude · latest instruction', ownGoalText: 'latest assignment' },
      ],
      projects: [{ goalSrcText: 'codex · latest instruction', goalText: 'latest assignment' }],
      title: 'claude · latest assignment',
    });
  });
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

  it('changes task labels and absences without rewriting quoted assignments or disclosure evidence', () => {
    const words = 'Evidence · assignment source; latest assignment; assignment unavailable';
    const value = {
      title: words,
      panel: words,
      strip: `Assignment evidence not published ${words} FO CONTINUES · Continue current assignment claude · latest assignment assignment unavailable`,
      disclosures: [
        { summary: 'Evidence · assignment source', body: words },
        {
          summary: 'Evidence · child handoff',
          body: `assignment unavailable · source assignment source unavailable · ${words}`,
        },
      ],
    };
    expect(projectWordDeviation(value, true, { instruction: words })).toEqual({
      title: words,
      panel: words,
      strip: `Task evidence not published ${words} FO CONTINUES · Continue current task claude · latest instruction task unavailable`,
      disclosures: [
        { summary: 'Evidence · task source', body: words },
        {
          summary: 'Evidence · child handoff',
          body: `task unavailable · source task source unavailable · ${words}`,
        },
      ],
    });
  });
});
