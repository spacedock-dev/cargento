import { createRequire } from 'node:module';
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
const cssList: { space(value: string): string[] } = createRequire(import.meta.resolve('vite'))(
  'postcss',
).list;
const FONT_KEYWORDS = new Set([
  'inherit',
  'initial',
  'unset',
  'revert',
  'revert-layer',
  'caption',
  'icon',
  'menu',
  'message-box',
  'small-caption',
  'status-bar',
]);
function fontShorthandSize(value: string): string | undefined {
  if (FONT_KEYWORDS.has(value.toLowerCase())) return undefined;
  const terms = cssList.space(value);
  while (
    /^(?:normal|italic|oblique|small-caps|bold|bolder|lighter|[1-9]\d{0,2}|1000)$/i.test(
      terms[0] ?? '',
    )
  ) {
    const term = terms.shift();
    if (
      term?.toLowerCase() === 'oblique' &&
      /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:deg|grad|rad|turn)$/i.test(terms[0] ?? '')
    )
      terms.shift();
  }
  return terms[0]?.split('/')[0] ?? value;
}
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
  for (const match of text.matchAll(/(?<![-\w])(font-size|font)\s*:\s*([^;}]+)/g)) {
    const declaration = resolveValue((match[2] ?? '').trim().replace(/\s*!important$/, ''));
    const value = match[1] === 'font' ? fontShorthandSize(declaration) : declaration;
    if (value === undefined) continue;
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
    ['.dead{font:12px var(--sans)}', 'off-scale size 12px'],
    ['.dead{font:italic small-caps 600 12px/1.5 var(--sans)}', 'off-scale size 12px'],
    ['.dead{--bad-size:12px;font:var(--bad-size) var(--sans)}', 'off-scale size 12px'],
    ['.dead{color:var(--missing)}', 'undeclared variable --missing'],
    ['.dead{background:url(https://x.test/a.png)}', 'external asset'],
    ['@import url("a.css");', 'remaining import'],
    ['@media(prefers-color-scheme:light){.dead{color:white}}', 'dark scheme'],
    ['.dead{--a:var(--b);--b:var(--a);color:var(--a)}', 'cyclic variable --a'],
  ])('fails a compiled addition %s', (addition, reason) => {
    expect(builtProblems(css + addition)).toContain(reason);
  });
  it.each([
    '.dead{font:.8125rem var(--sans)}',
    '.dead{font:italic small-caps 600 .9375rem/1.5 "A Font",sans-serif}',
    '.dead{font:normal 1.125rem / 1.5 var(--sans)}',
    '.dead{font:oblique 10deg bold 1.5rem var(--sans)}',
    '.dead{font:2.125rem var(--sans)!important}',
    ...['label', 'body', 'value', 'head', 'hero'].map(
      (step) => `.dead{font:500 var(--fs-${step})/1.55 var(--sans)}`,
    ),
    '.dead{--font:italic var(--fs-body)/1.5 var(--sans);font:var(--font)}',
    ...[
      'inherit',
      'initial',
      'unset',
      'revert',
      'revert-layer',
      'caption',
      'icon',
      'menu',
      'message-box',
      'small-caption',
      'status-bar',
    ].map((keyword) => `.dead{font:${keyword}}`),
  ])('accepts an on-scale or system font shorthand %s', (addition) => {
    expect(builtProblems(css + addition)).toEqual([]);
  });
});
