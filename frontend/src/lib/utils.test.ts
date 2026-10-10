// @vitest-environment node
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { twMerge } from 'tailwind-merge';
import { describe, expect, it } from 'vitest';
import { cn } from './utils';

const entry = readFileSync(
  fileURLToPath(new URL('../styles/tailwind.css', import.meta.url)),
  'utf8',
);
const themeNames = (prefix: string) =>
  [...entry.matchAll(new RegExp(`--${prefix}-(?!\\*)([a-z0-9-]+):`, 'g'))].map((m) => m[1]);

describe('cn', () => {
  it('keeps a size class and a colour class together (unconfigured tailwind-merge does not)', () => {
    expect(twMerge('text-body', 'text-muted-foreground')).toBe('text-muted-foreground');
    expect(cn('text-body', 'text-muted-foreground')).toBe('text-body text-muted-foreground');
    expect(cn('text-label', 'text-primary')).toBe('text-label text-primary');
  });

  it('still resolves a real conflict, later wins', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4');
    expect(cn('text-body', 'text-head')).toBe('text-head');
    expect(cn('rounded-control', 'rounded-card')).toBe('rounded-card');
  });

  it('knows every type step and radius the theme declares', () => {
    for (const step of themeNames('text')) {
      expect(cn(`text-${step}`, 'text-primary'), step).toBe(`text-${step} text-primary`);
    }
    for (const radius of themeNames('radius')) {
      expect(cn(`rounded-${radius}`, 'rounded-control'), radius).toBe('rounded-control');
    }
    expect(themeNames('text').length).toBe(5);
    expect(themeNames('radius').length).toBe(4);
  });
});
