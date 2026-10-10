import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/* The checks the embedded-source linter made of the previous page's stylesheet (balanced rules, no stray
   syntax) and the type floor that page's asset tests held, applied to the sheets the React build bundles.
   Biome does not read CSS here, so these are the only structural checks it gets. */
const ROOT = resolve(process.cwd(), 'frontend/src');

function sheets(directory = ROOT): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) return sheets(path);
    return name.endsWith('.css') ? [path] : [];
  });
}

/** The sheet with comments and string contents blanked, so a brace or quote inside either is not syntax. */
function stripped(css: string): string {
  return css
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, '""');
}

/** The sheet with comments removed and every string left as written, which is what a url() check has to read. */
function uncommented(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, ' ');
}

/** Every url() in a sheet whose target is not inline data or a fragment, quoted or not. */
export function externalUrls(css: string): string[] {
  const found: string[] = [];
  for (const match of uncommented(css).matchAll(/url\(\s*([^)]*)\)/g)) {
    const value = (match[1] ?? '')
      .trim()
      .replace(/^(["'])(.*)\1$/s, '$2')
      .trim();
    if (!value.startsWith('data:') && !value.startsWith('#')) found.push(value);
  }
  return found;
}

const files = sheets();

/** The custom properties a sheet declares, plus every one the components set through an inline style. */
function declaredProperties(): Set<string> {
  const declared = new Set<string>();
  for (const file of files)
    for (const match of stripped(readFileSync(file, 'utf8')).matchAll(/(--[\w-]+)\s*:/g))
      declared.add(match[1] as string);
  const walk = (directory: string): void => {
    for (const name of readdirSync(directory)) {
      const path = join(directory, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (/\.tsx?$/.test(name))
        for (const match of readFileSync(path, 'utf8').matchAll(/['"](--[\w-]+)['"]\s*:/g))
          declared.add(match[1] as string);
    }
  };
  walk(ROOT);
  return declared;
}

/* Used and never declared. None is held: a rule that names an undeclared custom property resolves to nothing, as
   the popover's shadow once did, so a new one fails here rather than joining this list. */
const TAILWIND_IMPORTS = [
  "@import 'tailwindcss/theme.css' layer(theme);",
  "@import 'tailwindcss/utilities.css' layer(utilities);",
];

const UNDECLARED: string[] = [];

// The five type steps of `styles/shell.css`, spelled as the rem values they hold.
const STEPS = ['0.8125rem', '0.9375rem', '1.125rem', '1.5rem', '2.125rem'];
const ALLOWED_SIZE = new RegExp(
  `^(?:var\\(--fs-(?:label|body|value|head|hero)\\)|inherit|100%|0|${STEPS.map((step) => step.replace('.', '\\.')).join('|')})$`,
);

describe('the bundled stylesheets', () => {
  it('finds the sheets the build bundles', () => {
    expect(files.length).toBeGreaterThanOrEqual(10);
    expect(files.some((file) => file.replaceAll('\\', '/').endsWith('styles/shell.css'))).toBe(
      true,
    );
  });

  it.each(files.map((file) => [relative(ROOT, file), file]))(
    '%s closes every rule and every parenthesis',
    (_name, file) => {
      const text = stripped(readFileSync(file as string, 'utf8'));
      let depth = 0;
      let parens = 0;
      for (const char of text) {
        if (char === '{') depth += 1;
        else if (char === '}') depth -= 1;
        else if (char === '(') parens += 1;
        else if (char === ')') parens -= 1;
        expect(depth).toBeGreaterThanOrEqual(0);
        expect(parens).toBeGreaterThanOrEqual(0);
      }
      expect(depth).toBe(0);
      expect(parens).toBe(0);
    },
  );

  it('asks for nothing outside the page: no import, no remote or relative url', () => {
    const offenders: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, 'utf8');
      /* The Tailwind entry names exactly two imports, both resolved by the build into the one stylesheet;
         the built CSS is checked for `@import` again by the package step. */
      const permitted =
        relative(ROOT, file).replaceAll('\\', '/') === 'styles/tailwind.css'
          ? TAILWIND_IMPORTS
          : [];
      const remaining = stripped(permitted.reduce((rest, line) => rest.replace(line, ''), text));
      if (/@import/.test(remaining)) offenders.push(`${relative(ROOT, file)}: @import`);
      for (const value of externalUrls(text))
        offenders.push(`${relative(ROOT, file)}: url(${value})`);
      if (/https?:\/\//.test(uncommented(text)))
        offenders.push(`${relative(ROOT, file)}: an absolute address`);
    }
    expect(offenders).toEqual([]);
  });

  it('reads a quoted url as it reads an unquoted one', () => {
    // The check once blanked strings before looking for url(), so a quoted relative target passed.
    expect(externalUrls('.a{background:url("a.png")}')).toEqual(['a.png']);
    expect(externalUrls(".a{background:url('a.png')}")).toEqual(['a.png']);
    expect(externalUrls('.a{background:url(a.png)}')).toEqual(['a.png']);
    expect(externalUrls('.a{background:url( "https://x.test/a.png" )}')).toEqual([
      'https://x.test/a.png',
    ]);
    expect(externalUrls('.a{background:url("data:image/svg+xml;utf8,<svg/>")}')).toEqual([]);
    expect(externalUrls('/* url(a.png) */ .a{color:red}')).toEqual([]);
  });

  it('uses no custom property that nothing declares', () => {
    const declared = declaredProperties();
    const used = new Set<string>();
    for (const file of files)
      for (const match of stripped(readFileSync(file, 'utf8')).matchAll(/var\(\s*(--[\w-]+)\s*\)/g))
        used.add(match[1] as string);
    expect([...used].filter((name) => !declared.has(name)).sort()).toEqual(UNDECLARED);
  });

  it('is dark only: no rule is keyed to the reader’s colour scheme', () => {
    const offenders = files.filter((file) =>
      /prefers-color-scheme/.test(stripped(readFileSync(file, 'utf8'))),
    );
    expect(offenders.map((file) => relative(ROOT, file))).toEqual([]);
    expect(stripped(readFileSync(join(ROOT, 'styles/shell.css'), 'utf8'))).toMatch(
      /color-scheme\s*:\s*dark/,
    );
  });

  it('sets every font size from the five steps, inherit, 100% or zero, never a pixel value', () => {
    const offenders: string[] = [];
    for (const file of files) {
      const text = stripped(readFileSync(file, 'utf8'));
      for (const match of text.matchAll(/(?<![-\w])font-size\s*:\s*([^;}]*)/g)) {
        const value = (match[1] ?? '').trim().replace(/\s*!important$/, '');
        if (!ALLOWED_SIZE.test(value)) offenders.push(`${relative(ROOT, file)}: ${value}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('keeps the type floor: no step below 13px is declared', () => {
    const shell = stripped(readFileSync(join(ROOT, 'styles/shell.css'), 'utf8'));
    const steps = [...shell.matchAll(/--fs-(\w+)\s*:\s*([\d.]+)rem/g)].map((match) => [
      match[1],
      Number(match[2]) * 16,
    ]);
    expect(steps.map(([name]) => name)).toEqual(['label', 'body', 'value', 'head', 'hero']);
    for (const [, pixels] of steps) expect(pixels).toBeGreaterThanOrEqual(13);
  });
});
