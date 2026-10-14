import type { StorageBackend } from '../storage';
import { liveEstimateKey } from '../storage';
import { SAMPLE_HARNESS, SAMPLE_SID } from './ids';

/* The sample's own storage: in memory, so nothing the reader does in it reaches the real page's browser
   storage, and the live estimate starts on, as it would after the reader turned it on for a session. */
export function createSampleBackend(): () => StorageBackend {
  const data = new Map<string, string>([
    [liveEstimateKey({ harness: SAMPLE_HARNESS, sid: SAMPLE_SID }), '1'],
  ]);
  const backend: StorageBackend = {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => {
      data.set(key, value);
    },
    removeItem: (key) => {
      data.delete(key);
    },
  };
  return () => backend;
}
