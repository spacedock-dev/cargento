import { fileURLToPath } from 'node:url';
import { storybookTest } from '@storybook/addon-vitest/vitest-plugin';
import { playwright } from '@vitest/browser-playwright';
import { defineConfig } from 'vitest/config';
import { storyGuard, storyResult } from '../storybook/guard.mts';

export default defineConfig({
  server: { host: '127.0.0.1' },
  test: {
    projects: [
      {
        plugins: [
          storybookTest({
            configDir: fileURLToPath(new URL('.', import.meta.url)),
            storybookUrl: 'http://127.0.0.1:6006',
          }),
        ],
        test: {
          name: 'storybook',
          maxWorkers: 1,
          fileParallelism: false,
          setupFiles: [fileURLToPath(new URL('./vitest.setup.ts', import.meta.url))],
          coverage: { enabled: false },
          browser: {
            enabled: true,
            api: { host: '127.0.0.1' },
            commands: { storyGuard, storyResult },
            screenshotDirectory: fileURLToPath(
              new URL('../../docs/screenshots/storybook', import.meta.url),
            ),
            headless: true,
            provider: playwright(),
            instances: [{ browser: 'chromium' }],
          },
        },
      },
    ],
  },
});
