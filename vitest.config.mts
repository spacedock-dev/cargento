import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

/* Every legacy answer the goldens hold was formatted in one zone, so the zone is fixed rather than the desk's:
   a clock word or a day-qualified date read in another zone is a different string. Set here, before any worker
   starts, because a worker thread cannot change the process zone after it has begun. The locale is fixed for
   the same reason: the port and the legacy page both format with the default locale, and the goldens hold the
   en-US strings (measured: under de_DE a daily-limit sentence reads "15.1.2027, 08:00:00" against the
   recorded "1/15/2027, 8:00:00 AM"). */
process.env['TZ'] = 'UTC';
process.env['LC_ALL'] = 'en_US.UTF-8';
process.env['LANG'] = 'en_US.UTF-8';
process.env['LANGUAGE'] = 'en_US';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./frontend/src', import.meta.url)) } },
  test: {
    environment: 'jsdom',
    include: ['frontend/**/*.test.ts', 'frontend/**/*.test.tsx'],
    setupFiles: ['frontend/test/setup.ts'],
    maxWorkers: 2,
    // A hosted Windows runner took longer than the default five seconds on a generated-board test that
    // takes about one second here; a hang still ends, only later.
    testTimeout: 30_000,
    env: { TZ: 'UTC', LC_ALL: 'en_US.UTF-8', LANG: 'en_US.UTF-8' },
  },
});
