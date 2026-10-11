import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
const ui = resolve('frontend/src/ui') + '/';
const stories = resolve('frontend/stories') + '/';
const components = readdirSync(ui, { recursive: true, encoding: 'utf8' }).filter(
  (file) => file.endsWith('.tsx') && !file.includes('.test.'),
);
describe('Vendored component stories', () => {
  for (const file of components) {
    it(`${file} has a story with reader assertions`, () => {
      const source = readFileSync(`${stories}${file.replace('.tsx', '.stories.tsx')}`, 'utf8');
      expect(source).toMatch(/play:\s*(?:async|\w+)/);
      expect(source).toMatch(/\bexpect\(/);
      expect(source).toContain(`../src/ui/${file.replace('.tsx', '')}`);
    });
  }
  it('keeps stories outside the shipped stylesheet scan and CSS inventory', () => {
    const entry = readFileSync(resolve('frontend/src/styles/tailwind.css'), 'utf8');
    expect(entry).toContain('source(none)');
    expect(entry).not.toMatch(/@source[^;]*stories/);
    expect(readdirSync(stories).some((file) => file.endsWith('.css'))).toBe(false);
  });
});
