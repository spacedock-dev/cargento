import assert from 'node:assert/strict';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
import { createDocument, readFonts, packageFrontend } from './package.mjs';
import { fileURLToPath } from 'node:url';
import { cp, mkdir, mkdtemp, rm, symlink, readFile, writeFile, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';

const root = fileURLToPath(new URL('../../', import.meta.url));

test('hostile JavaScript and CSS values remain exact embedded bytes', () => {
  const javascript =
    'const values=["</script>","<!--","<script","</head>",String.raw`</ScRiPt>`]; window.answer=values;';
  const css = ':root{--example:"</style>"}';
  const document = new JSDOM(createDocument(javascript, css)).window.document;
  const scripts = [...document.querySelectorAll('script')];
  assert.equal(scripts.length, 1);
  assert.equal(scripts[0].type, 'module');
  assert.equal(Buffer.from(scripts[0].src.split(',')[1], 'base64').toString(), javascript);
  assert.equal(
    Buffer.from(document.querySelector('link').href.split(',')[1], 'base64').toString(),
    css,
  );
  assert.equal(document.querySelectorAll('#root').length, 1);
  assert.equal(document.querySelectorAll('meta[name="cargento-focus"]').length, 0);
});

test('canonical font descriptors and all fifteen WOFF2 subsets are embedded', async () => {
  const fonts = await readFonts(root);
  assert.equal(fonts.provenance.length, 15);
  assert.equal(fonts.css.match(/@font-face/g).length, 15);
  assert.equal(fonts.css.match(/data:font\/woff2;base64,/g).length, 15);
  assert.equal(fonts.css.includes('{{CARGENTO_FONT_'), false);
  assert.equal(
    fonts.provenance.reduce((total, font) => total + font.bytes, 0),
    142840,
  );
});

test('production packaging includes full licenses and a matching document digest', async () => {
  const packed = await packageFrontend({ root, write: false });
  assert.equal(packed.metadata.format, 1);
  assert.equal(packed.metadata.frontend, 'react');
  assert.equal(packed.metadata.document.bytes, Buffer.byteLength(packed.document));
  assert.ok(packed.licenses.includes('MIT License'));
  assert.ok(packed.licenses.includes('SIL OPEN FONT LICENSE'));
  assert.ok(packed.metadata.provenance.packages.some((pkg) => pkg.name === 'react'));
  assert.ok(packed.metadata.provenance.packages.some((pkg) => pkg.name === 'react-dom'));
  assert.ok(packed.metadata.provenance.packages.some((pkg) => pkg.name === 'scheduler'));
  assert.equal(packed.document.includes('sourceMappingURL'), false);
  assert.equal(packed.document.includes('cargento-focus'), false);
});

async function copiedSource(prefix, use) {
  const copy = await mkdtemp(join(tmpdir(), prefix));
  try {
    for (const file of ['package.json', 'pnpm-lock.yaml', '.node-version', '.gitattributes'])
      await cp(join(root, file), join(copy, file));
    await cp(join(root, 'frontend'), join(copy, 'frontend'), { recursive: true });
    const web = 'cargento/skills/cargento/cargento_runtime/web';
    await mkdir(join(copy, web), { recursive: true });
    await cp(join(root, web), join(copy, web), { recursive: true });
    await symlink(
      join(root, 'node_modules'),
      join(copy, 'node_modules'),
      process.platform === 'win32' ? 'junction' : 'dir',
    );
    await use(copy, web);
  } finally {
    await rm(copy, { recursive: true, force: true });
  }
}

test('two clean builds in distinct paths and a plugin-version-only bump match', async () => {
  let first;
  await copiedSource('cargento-package-a-', async (copy) => {
    first = await packageFrontend({ root: copy, write: false });
  });
  await copiedSource('cargento-package-b-', async (copy) => {
    await mkdir(join(copy, 'cargento/.claude-plugin'), { recursive: true });
    await writeFile(join(copy, 'cargento/.claude-plugin/plugin.json'), '{"version":"99.99.99"}\n');
    const second = await packageFrontend({ root: copy, write: false });
    assert.deepEqual(second, first);
  });
});

test('check mode leaves tracked outputs untouched and rejects a stale artifact', async () => {
  await copiedSource('cargento-package-check-', async (copy, web) => {
    await packageFrontend({ root: copy });
    const file = join(copy, web, 'react.html');
    const before = await stat(file);
    await packageFrontend({ root: copy, check: true });
    assert.equal((await stat(file)).mtimeMs, before.mtimeMs);
    await writeFile(file, 'corrupt artifact\n');
    await assert.rejects(packageFrontend({ root: copy, check: true }), /stale tracked react.html/);
    assert.equal(await readFile(file, 'utf8'), 'corrupt artifact\n');
  });
});

test('a corrupt canonical font fails instead of silently falling back', async () => {
  await copiedSource('cargento-package-font-', async (copy, web) => {
    await writeFile(join(copy, web, 'fonts/space-grotesk-v22-latin.woff2.b64'), 'not-a-font');
    await assert.rejects(readFonts(copy), /invalid base64/);
  });
});

test('an actual autocrlf checkout preserves the served page and every candidate artifact', async () => {
  const temporary = await mkdtemp(join(tmpdir(), 'cargento-line-endings-'));
  try {
    const source = join(temporary, 'source'),
      checkout = join(temporary, 'checkout');
    await mkdir(source);
    await writeFile(
      join(source, '.gitattributes'),
      (await readFile(join(root, '.gitattributes'), 'utf8')) +
        '\n.autocrlf-control.txt text !eol\n',
    );
    await writeFile(join(source, '.autocrlf-control.txt'), 'control\n');
    const binaryControl = Buffer.from([0, 255, 13, 10, 0, 65, 10]);
    await writeFile(join(source, '.autocrlf-binary.bin'), binaryControl);
    await cp(join(root, 'cargento'), join(source, 'cargento'), {
      recursive: true,
      filter: (path) => !path.split(/[\\/]/).includes('__pycache__'),
    });
    const git = (...args) =>
      execFileSync(
        'git',
        [
          '-c',
          'core.hooksPath=' + join(temporary, 'empty-hooks'),
          '-c',
          'commit.gpgsign=false',
          ...args,
        ],
        { cwd: source, encoding: 'utf8', timeout: 10000, stdio: ['ignore', 'pipe', 'pipe'] },
      );
    await mkdir(join(temporary, 'empty-hooks'));
    git('init');
    git('add', '--', '.gitattributes', '.autocrlf-control.txt', '.autocrlf-binary.bin', 'cargento');
    git(
      '-c',
      'user.name=Frontend test',
      '-c',
      'user.email=frontend-test@example.invalid',
      'commit',
      '-m',
      'fixture',
    );
    git('-c', 'core.autocrlf=true', 'clone', '--no-local', source, checkout);
    assert.equal(await readFile(join(checkout, '.autocrlf-control.txt'), 'utf8'), 'control\r\n');
    assert.deepEqual(await readFile(join(checkout, '.autocrlf-binary.bin')), binaryControl);
    const python =
      process.env.CARGENTO_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    const digest = (directory) =>
      execFileSync(
        python,
        [
          '-c',
          'import sys,hashlib;sys.path.insert(0,sys.argv[1]);from cargento_runtime.web.page import load_frontend_page;print(hashlib.sha256(load_frontend_page()).hexdigest())',
          join(directory, 'cargento/skills/cargento'),
        ],
        { encoding: 'utf8', timeout: 10000 },
      ).trim();
    assert.equal(digest(source), digest(checkout));
    const web = 'cargento/skills/cargento/cargento_runtime/web';
    for (const name of ['react.html', 'react.integrity.json', 'react-licenses.txt']) {
      assert.deepEqual(
        await readFile(join(checkout, web, name)),
        await readFile(join(source, web, name)),
      );
    }
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});

for (const name of ['react.html', 'react.integrity.json', 'react-licenses.txt']) {
  test(`check mode rejects a BOM in ${name} without rewriting bytes`, async () => {
    await copiedSource('cargento-package-bom-', async (copy, web) => {
      await packageFrontend({ root: copy });
      const file = join(copy, web, name);
      const original = await readFile(file);
      const changed = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), original]);
      await writeFile(file, changed);
      const before = await stat(file);
      await assert.rejects(
        packageFrontend({ root: copy, check: true }),
        new RegExp('stale tracked ' + name.replaceAll('.', '\\.')),
      );
      assert.deepEqual(await readFile(file), changed);
      assert.equal((await stat(file)).mtimeMs, before.mtimeMs);
    });
  });
}
