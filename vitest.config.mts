import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['frontend/**/*.test.ts', 'frontend/**/*.test.tsx'],
    setupFiles: ['frontend/test/setup.ts'],
    maxWorkers: 2,
  },
});
