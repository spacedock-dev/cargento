import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers';
import 'vitest';

// Vitest 5 uses return/received parameters; jest-dom 7's /vitest entry still
// augments the former one-parameter Assertion interface. Use its standalone
// runtime matchers and Vitest's documented Matchers extension instead.
declare module 'vitest' {
  interface Matchers<R, T> {
    toBeInTheDocument: TestingLibraryMatchers<T, R>['toBeInTheDocument'];
    toBeVisible: TestingLibraryMatchers<T, R>['toBeVisible'];
  }
}
