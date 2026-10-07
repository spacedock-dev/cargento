import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default defineConfig([
  globalIgnores(['node_modules/**', '.frontend-build/**', 'test-results/**', 'playwright-report/**']),
  {
    files: ['frontend/**/*.{ts,tsx}', 'vitest.config.ts', 'playwright.config.ts'],
    extends: [js.configs.recommended, tseslint.configs.strict],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    files: ['frontend/**/*.{ts,tsx}'],
    extends: [reactHooks.configs.flat.recommended, reactRefresh.configs.vite],
  },
  {
    files: ['eslint.config.js'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
]);
