import { readFile, readdir } from 'node:fs/promises';
import { join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import ts from 'typescript';
import { __unstable__loadDesignSystem } from 'tailwindcss';

const utilityTypes = await __unstable__loadDesignSystem('@theme { --spacing: 0.25rem; }');

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const RECORD = 'frontend/css-budget.json';
const RULE =
  'UTF-8 bytes after CRLF to LF normalization, including comments, of all CSS under frontend except the directive-only Tailwind entry. Strip only an outer @layer legacy wrapper. Inventory every path; added paths need prior base approval.';
const slashed = (path) => path.replaceAll('\\', '/');
export const cssBytes = (text) =>
  Buffer.byteLength(
    text.replaceAll('\r\n', '\n').replace(/^@layer legacy \{\n([\s\S]*)\}\n$/, '$1'),
  );
async function files(root, directory) {
  const found = [];
  for (const item of await readdir(join(root, directory), { withFileTypes: true })) {
    const path = `${directory}/${item.name}`;
    if (item.isDirectory()) found.push(...(await files(root, path)));
    else if (item.isFile()) found.push(path);
    else throw new Error(`Unsupported source entry ${path}`);
  }
  return found.sort();
}

export function scaleProblems(source, file = 'source.tsx') {
  // Scan strings, including cva recipes and conditional classes, rather than className alone.
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  const found = new Set();
  const visit = (node) => {
    if (
      ts.isStringLiteralLike(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node)
    ) {
      for (const token of node.text.split(/\s+/)) {
        const utility = token
          .split(/:(?![^[]*\])(?![^(]*\))/)
          .at(-1)
          .replace(/^!/, '')
          .replace(/!$/, '');
        if (
          /^text-(?:xs|sm|base|lg|xl|[2-9]xl)(?:\/.*)?$/.test(utility) ||
          // Tailwind resolves unhinted variables (including [--x]) as color. Let its pinned
          // compiler distinguish colors from signed lengths, keywords, math and size hints.
          (/^text-(?:\[|\()/.test(utility) &&
            utilityTypes
              .candidatesToCss([utility])
              .some((css) => /\bfont-size:/.test(css || ''))) ||
          /^(?:text|font)-\(length:/.test(utility) ||
          /^\[font-size:/.test(utility) ||
          /^rounded(?:-[trblse]{1,2})?-(?:xs|sm|md|lg|xl|[2-4]xl)$/.test(utility) ||
          /^(?:bg|text|border|ring|fill|stroke|shadow|outline|decoration|accent|caret|divide|from|via|to)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d+(?:\/.*)?$/.test(
            utility,
          )
        )
          found.add(token);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return [...found].sort();
}

export async function unusedUi(root) {
  const source = await files(root, 'frontend/src');
  const modules = new Set(
    source.filter((file) => /\.[cm]?[jt]sx?$/.test(file) && !/\.test\./.test(file)),
  );
  const visited = new Set();
  async function walk(file) {
    if (visited.has(file)) return;
    visited.add(file);
    const tree = ts.createSourceFile(
      file,
      await readFile(join(root, file), 'utf8'),
      ts.ScriptTarget.Latest,
      true,
    );
    const importedFiles = new Set();
    const visit = (node) => {
      if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
        const clause = ts.isImportDeclaration(node) ? node.importClause : node;
        const bindings = ts.isImportDeclaration(node) ? clause?.namedBindings : node.exportClause;
        const named = bindings && (ts.isNamedImports(bindings) || ts.isNamedExports(bindings));
        const onlyTypes =
          clause?.isTypeOnly ||
          (named &&
            !clause.name &&
            bindings.elements.length > 0 &&
            bindings.elements.every((item) => item.isTypeOnly));
        if (!onlyTypes && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier))
          importedFiles.add(node.moduleSpecifier.text);
      } else if (
        ts.isCallExpression(node) &&
        node.expression.kind === ts.SyntaxKind.ImportKeyword &&
        node.arguments[0] &&
        ts.isStringLiteralLike(node.arguments[0])
      ) {
        importedFiles.add(node.arguments[0].text);
      }
      ts.forEachChild(node, visit);
    };
    visit(tree);
    for (const fileName of importedFiles) {
      if (!fileName.startsWith('.') && !fileName.startsWith('@/')) continue;
      const base = fileName.startsWith('@/')
        ? `frontend/src/${fileName.slice(2)}`
        : slashed(relative(root, resolve(root, file, '..', fileName)));
      const target = [
        base,
        ...['.ts', '.tsx', '.js', '.jsx', '/index.ts', '/index.tsx'].map((suffix) => base + suffix),
      ].find((candidate) => modules.has(candidate));
      if (target) await walk(target);
    }
  }
  await walk('frontend/src/main.tsx');
  return [...modules]
    .filter((file) => file.startsWith('frontend/src/ui/') && !visited.has(file))
    .sort();
}

export function compareBase(record, base) {
  const problems = [];
  if (record.bytes > base.bytes)
    problems.push(`Hand-written CSS allowance rose: ${base.bytes} -> ${record.bytes}`);
  if (record.rule !== base.rule || record.files.some((file) => !base.files.includes(file)))
    problems.push('CSS counting rule or paths changed against the PR base');
  return problems;
}

export async function checkStyles(root = ROOT, base) {
  const record = JSON.parse(await readFile(join(root, RECORD), 'utf8'));
  const source = await files(root, 'frontend/src');
  const css = (await files(root, 'frontend')).filter(
    (file) => file.endsWith('.css') && file !== 'frontend/src/styles/tailwind.css',
  );
  const problems = [];
  if (record.rule !== RULE) problems.push('CSS counting rule differs from the gate');
  if (JSON.stringify(css) !== JSON.stringify(record.files))
    problems.push('CSS files differ from the counted paths');
  let bytes = 0;
  for (const file of css) bytes += cssBytes(await readFile(join(root, file), 'utf8'));
  if (bytes !== record.bytes)
    problems.push(`Hand-written CSS bytes differ: record ${record.bytes}, actual ${bytes}`);
  for (const file of source.filter((file) => /\.tsx?$/.test(file) && !/\.test\./.test(file))) {
    for (const token of scaleProblems(await readFile(join(root, file), 'utf8'), file))
      problems.push(`${file}: forbidden scale class ${token}`);
  }
  for (const file of await unusedUi(root))
    problems.push(`${file}: no importer reachable from the shipped entry`);
  // The only excluded sheet is the toolchain entry. Ordinary rules cannot be hidden there.
  const entry = (await readFile(join(root, 'frontend/src/styles/tailwind.css'), 'utf8')).replace(
    /\/\*[\s\S]*?\*\//g,
    '',
  );
  const directives = entry
    .replace(/@theme(?:\s+static)?\s*\{[^{}]*\}/g, '')
    // Variant bodies may wrap the slot in selectors, but cannot carry declarations.
    .replace(
      /@custom-variant\s+data-(?:open|closed)\s*\{\s*(?:@slot;|[^;{}@]+\{\s*@slot;\s*\})\s*\}/g,
      '',
    )
    .replace(/@custom-variant\s+(?:dark|data-open|data-closed)\s+\([^;{}]*\)\s*;/g, '')
    .replace(/@(?:layer|import|source)\s+(?:'[^']*'|"[^"]*"|[^;{}'"])+;/g, '')
    .trim();
  if (directives) problems.push('Tailwind entry contains a rule outside its theme and variants');
  if (base) {
    const git = (...args) =>
      execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    const paths = git('ls-tree', '-r', '--name-only', base, '--', 'frontend').trim().split('\n');
    // Bootstrap from the base's actual sheets, so introducing the record cannot bless growth.
    const previous = paths.includes(RECORD)
      ? JSON.parse(git('show', `${base}:${RECORD}`))
      : {
          rule: RULE,
          files: paths
            .filter((file) => file.endsWith('.css') && file !== 'frontend/src/styles/tailwind.css')
            .sort(),
        };
    if (previous.bytes === undefined)
      previous.bytes = previous.files.reduce(
        (sum, file) => sum + cssBytes(git('show', `${base}:${file}`)),
        0,
      );
    problems.push(...compareBase(record, previous));
  }
  return { bytes, problems };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length && (args.length !== 2 || args[0] !== '--base'))
    throw new Error('usage: node frontend/build/style-policy.mjs [--base SHA]');
  try {
    const result = await checkStyles(ROOT, args[1] || process.env.PR_BASE);
    console.log(`Hand-written CSS: ${result.bytes} bytes`);
    for (const problem of result.problems) console.error(problem);
    process.exitCode = result.problems.length ? 1 : 0;
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
