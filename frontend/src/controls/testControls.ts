/* Test doubles for the controls kit. Not imported by production code. */
import type { FocusOutcome, SessionIdentity } from '../api/types';
import { createLegacyStorage, type StorageBackend } from '../storage';
import { fakeBackend, type FakeBackend } from '../../test/storage_backends';
import { createFakeClock } from '../transport/testing';
import { createControls, type ClipboardLike, type ControlsDeps } from './kit';

export interface TestControlsOptions {
  readonly clipboard?: 'ok' | 'rejects' | 'missing' | ClipboardLike;
  readonly focus?: ((identity: SessionIdentity) => Promise<FocusOutcome>) | null;
  readonly reducedMotion?: boolean;
  readonly backend?: StorageBackend;
  readonly noteToggle?: () => void;
}

export function testControls(options: TestControlsOptions = {}) {
  const clock = createFakeClock();
  const announced: { key: string; text: string }[] = [];
  const written: string[] = [];
  const backend = (options.backend ?? fakeBackend()) as FakeBackend;
  const legacy = createLegacyStorage(() => backend);
  const mode = options.clipboard ?? 'ok';
  const clipboard: ControlsDeps['clipboard'] =
    typeof mode === 'object'
      ? () => mode
      : mode === 'missing'
        ? () => null
        : () => ({
            writeText: (text: string) => {
              if (mode === 'rejects') return Promise.reject(new Error('denied'));
              written.push(text);
              return Promise.resolve();
            },
          });
  const raised: SessionIdentity[] = [];
  const focus: ControlsDeps['focus'] =
    options.focus === null
      ? undefined
      : (options.focus ??
        ((identity) => {
          raised.push(identity);
          return Promise.resolve('sent');
        }));
  const controls = createControls({
    clock,
    announce: (key, text) => announced.push({ key, text }),
    memo: legacy.memo,
    clipboard,
    ...(focus ? { focus } : {}),
    reducedMotion: () => options.reducedMotion === true,
    ...(options.noteToggle ? { noteToggle: options.noteToggle } : {}),
  });
  return { controls, clock, announced, written, raised, backend, legacy };
}
