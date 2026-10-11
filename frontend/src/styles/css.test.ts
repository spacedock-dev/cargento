import { resolve } from 'node:path';
import { build } from 'vite';
import { beforeAll, describe, expect, it } from 'vitest';

// Compile the actual entry in memory: no packaged page or integrity receipt is rewritten.
let css = '';
beforeAll(async () => {
  const result = await build({
    configFile: resolve('frontend/vite.config.mts'),
    logLevel: 'silent',
    build: { write: false },
  });
  const outputs = Array.isArray(result) ? result : [result];
  for (const output of outputs) {
    if (!('output' in output)) throw new Error('Expected a completed CSS build');
    for (const asset of output.output)
      if (asset.type === 'asset' && asset.fileName.endsWith('.css')) css += String(asset.source);
  }
  expect(css.length).toBeGreaterThan(1000);
}, 30_000);

const clean = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, '');
export function externalUrls(text: string): string[] {
  return [...clean(text).matchAll(/url\(\s*([^)]*)\)/g)]
    .map((match) =>
      (match[1] ?? '')
        .trim()
        .replace(/^(["\x27])(.*)\1$/s, '$2')
        .trim(),
    )
    .filter((value) => !value.startsWith('data:') && !value.startsWith('#'));
}

const REM = /^(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)rem$/;
const STEPS = { label: 0.8125, body: 0.9375, value: 1.125, head: 1.5, hero: 2.125 };
export function builtProblems(input: string): string[] {
  const text = clean(input);
  const problems: string[] = [];
  const properties = new Map<string, string>();
  for (const match of text.matchAll(/(--[\w-]+)\s*:\s*([^;}]+)/g))
    properties.set(match[1] as string, (match[2] ?? '').trim());
  for (const match of text.matchAll(
    /@property\s+(--[\w-]+)\s*\{[^}]*initial-value\s*:\s*([^;}]+)/g,
  ))
    if (!properties.has(match[1] as string))
      properties.set(match[1] as string, (match[2] ?? '').trim());
  const resolveValue = (value: string, seen = new Set<string>()): string =>
    value.replace(
      /var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)/g,
      (_whole, name: string, fallback?: string) => {
        if (seen.has(name)) {
          problems.push(`cyclic variable ${name}`);
          return '';
        }
        const next = properties.get(name) ?? fallback;
        if (next === undefined) {
          problems.push(`undeclared variable ${name}`);
          return '';
        }
        return resolveValue(next, new Set([...seen, name]));
      },
    );
  // Follow references in declarations as well as in font sizes; a declared alias can still be broken.
  resolveValue(text);
  if (/@import\b/.test(text)) problems.push('remaining import');
  if (externalUrls(text).length || /https?:\/\//.test(text)) problems.push('external asset');
  if (
    /prefers-color-scheme/.test(text) ||
    !/color-scheme\s*:\s*dark(?:[;}])/.test(text) ||
    /color-scheme\s*:\s*(?!dark(?:[;}]))[^;}]+/.test(text)
  )
    problems.push('dark scheme');
  if (/--ctl-/.test(text)) problems.push('retired control alias');
  for (const [name, value] of Object.entries(STEPS))
    if (
      Number.parseFloat(properties.get(`--fs-${name}`) ?? '') !== value ||
      !REM.test(properties.get(`--fs-${name}`) ?? '') ||
      !properties.get(`--fs-${name}`)?.endsWith('rem')
    )
      problems.push(`type step ${name}`);
  const steps = [...properties.keys()].filter((name) => name.startsWith('--fs-')).sort();
  if (
    steps.join(',') !==
    Object.keys(STEPS)
      .map((name) => `--fs-${name}`)
      .sort()
      .join(',')
  )
    problems.push('type step inventory');
  for (const match of text.matchAll(/(?<![-\w])font-size\s*:\s*([^;}]+)/g)) {
    const value = resolveValue((match[1] ?? '').trim().replace(/\s*!important$/, ''));
    if (
      !['inherit', '100%', '0'].includes(value) &&
      !(REM.test(value) && Object.values(STEPS).includes(Number.parseFloat(value)))
    )
      problems.push(`off-scale size ${value}`);
  }
  if (!/body\{[^}]*font-size\s*:\s*var\(--fs-body\)/.test(text)) problems.push('body type');
  if (properties.get('--ink-absence') !== 'var(--ink2)') problems.push('absence ink');
  return [...new Set(problems)].sort();
}

describe('the compiled stylesheet', () => {
  it('keeps local assets, dark colours, resolved variables and the five type steps', () => {
    expect(builtProblems(css)).toEqual([]);
  });
  it('detects quoted external URLs', () => {
    expect(externalUrls('.a{background:url("https://x.test/a.png")} ')).toEqual([
      'https://x.test/a.png',
    ]);
    expect(externalUrls('.a{background:url(data:image/svg+xml;base64,AA==)}')).toEqual([]);
  });
  it.each([
    ['type step', /--fs-label:[^;}]+/, '--fs-label:.75rem', 'type step label'],
    ['body type', /body\{([^}]*?)font-size:var\(--fs-body\);?/, 'body{$1', 'body type'],
    ['colour', /--ink-absence:[^;}]+/, '--ink-absence:var(--missing-ink)', 'absence ink'],
    ['dark scheme', /color-scheme:dark/, 'color-scheme:light', 'dark scheme'],
    ['variable', /--ink2:[^;}]+/, '--ink2:var(--missing-ink)', 'undeclared variable --missing-ink'],
  ] as const)('fails a mutation removing %s', (_name, needle, replacement, reason) => {
    expect(css).toMatch(needle);
    expect(builtProblems(css.replace(needle, replacement))).toContain(reason);
  });
  it.each([
    ['.dead{--fs-extra:.75rem}', 'type step inventory'],
    ['.dead{font-size:12px}', 'off-scale size 12px'],
    ['.dead{color:var(--missing)}', 'undeclared variable --missing'],
    ['.dead{background:url(https://x.test/a.png)}', 'external asset'],
    ['@import url("a.css");', 'remaining import'],
    ['@media(prefers-color-scheme:light){.dead{color:white}}', 'dark scheme'],
    ['.dead{--a:var(--b);--b:var(--a);color:var(--a)}', 'cyclic variable --a'],
  ])('fails a compiled addition %s', (addition, reason) => {
    expect(builtProblems(css + addition)).toContain(reason);
  });
});
