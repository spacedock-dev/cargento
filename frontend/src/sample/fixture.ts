import raw from './session.fixture.json';

/* What the Session page asks the server for, answered once, in advance. Built by
   `scripts/build_sample_fixture.py` from a real server reading the anonymized session in
   `sample-session/`, never edited by hand. */
export interface SampleFixture {
  readonly board: Record<string, unknown>;
  readonly context: Record<string, unknown>;
  readonly prompts: Record<string, unknown>;
  readonly record: Record<string, unknown>;
  readonly correction: Record<string, unknown>;
}

export const SAMPLE_FIXTURE = raw as unknown as SampleFixture;
