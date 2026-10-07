import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default defineConfig([
  globalIgnores(['node_modules/**', '.frontend-build/**', 'test-results/**', 'playwright-report/**']),
  {
    files: ['frontend/**/*.{ts,tsx,mts}', 'vitest.config.mts', 'playwright.config.ts'],
    extends: [js.configs.recommended, tseslint.configs.strict],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    files: ['frontend/**/*.{ts,tsx,mts}'],
    extends: [reactHooks.configs.flat.recommended, reactRefresh.configs.vite],
  },
  {
    files: ['eslint.config.mjs'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
]);
