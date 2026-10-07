import assert from 'node:assert/strict';
import { test } from 'node:test';
import { join } from 'node:path';
import { isolatedEnvironment, parseArguments, handshakeSignature } from './protocol.mjs';

test('isolates every store/data input and keeps only Windows loader locations', () => {
  const scratch = join(process.cwd(), 'synthetic-owned-root');
  const env = isolatedEnvironment(scratch, { SystemRoot: 'C:\\Windows', windir: 'C:\\Windows',
    HOME: '/real', CODEX_HOME: '/real/codex', APPDATA: '/real/data', OPENAI_API_KEY: 'synthetic',
    PATH: '/real/bin', __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS: 'evil.example' }, 'win32');
  assert.equal(env.SYSTEMROOT, 'C:\\Windows');
  assert.equal(env.WINDIR, 'C:\\Windows');
  for (const key of ['HOME', 'USERPROFILE', 'CARGENTO_HOME', 'XDG_DATA_HOME', 'LOCALAPPDATA',
    'APPDATA', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'GEMINI_CLI_HOME', 'COPILOT_HOME',
    'PI_CODING_AGENT_DIR', 'PI_CODING_AGENT_SESSION_DIR', 'PATH']) assert.ok(env[key].startsWith(scratch));
  assert.equal(env.OPENAI_API_KEY, undefined);
  assert.equal(env.__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS, undefined);
  assert.equal(isolatedEnvironment(scratch, { SystemRoot: 'C:\\Windows' }, 'darwin').SYSTEMROOT, undefined);
});

test('contributor arguments refuse origin/host widening and collisions', () => {
  assert.deepEqual(parseArguments(['--port', '4587', '--vite-port', '4588']), { port: 4587, vitePort: 4588 });
  for (const argv of [['--host', '0.0.0.0'], ['--vite-origin', 'http://evil.example'],
    ['--port', '4581', '--vite-port', '4581'], ['--port', '0'], ['--port', '4581x'],
    ['--port'], ['--python', 'relative-python'], ['--live-data']]) assert.throws(() => parseArguments(argv));
});

test('HMAC fixed cross-language vector binds challenge, both origins and both generations', () => {
  const manifest = { nonce: '00'.repeat(32), python_origin: 'http://127.0.0.1:4581',
    vite_origin: 'http://127.0.0.1:4582', vite_generation: '22'.repeat(16),
    backend_generation: '33'.repeat(16), vite_pid: 12345 };
  const signature = handshakeSignature(manifest, '11'.repeat(32));
  assert.equal(signature, '61b9ed2f5493ce89d676af21bc7bbd27f2e92313d95b629dd4bda7528d7cf9a4');
  assert.notEqual(handshakeSignature({ ...manifest, backend_generation: '44'.repeat(16) }, '11'.repeat(32)), signature);
  assert.throws(() => handshakeSignature(manifest, 'malformed'));
  assert.throws(() => handshakeSignature({ ...manifest, python_origin: 'http://evil.example' }, '11'.repeat(32)));
});
