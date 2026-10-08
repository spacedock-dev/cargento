import { createHmac } from 'node:crypto';
import { isAbsolute, join } from 'node:path';

export function parseArguments(argv) {
  const options = { port: 4581, vitePort: 4582 };
  const names = { '--port': 'port', '--vite-port': 'vitePort', '--python': 'python' };
  const seen = new Set();
  for (let index = 0; index < argv.length; index += 2) {
    const name = names[argv[index]],
      value = argv[index + 1];
    if (!name || !value || seen.has(name))
      throw Error('Use only --python ABSOLUTE_PATH, --port PORT and --vite-port PORT.');
    seen.add(name);
    if (name === 'python') {
      if (!isAbsolute(value)) throw Error('--python requires an absolute executable path.');
      options.python = value;
    } else {
      if (!/^[1-9]\d{0,4}$/.test(value) || Number(value) > 65535)
        throw Error('Ports must be integers from 1 to 65535.');
      options[name] = Number(value);
    }
  }
  if (options.port === options.vitePort) throw Error('Python and Vite ports must differ.');
  return options;
}

export function isolatedEnvironment(scratch, ambient, platform = process.platform) {
  const result = {};
  if (platform === 'win32')
    for (const [name, value] of Object.entries(ambient)) {
      if (['SYSTEMROOT', 'WINDIR'].includes(name.toUpperCase())) result[name.toUpperCase()] = value;
    }
  Object.assign(result, {
    HOME: scratch,
    USERPROFILE: scratch,
    CARGENTO_HOME: join(scratch, 'state'),
    XDG_DATA_HOME: join(scratch, 'data'),
    APPDATA: join(scratch, 'roaming'),
    LOCALAPPDATA: join(scratch, 'local'),
    CLAUDE_CONFIG_DIR: join(scratch, 'claude'),
    CODEX_HOME: join(scratch, 'codex'),
    GEMINI_CLI_HOME: join(scratch, 'gemini'),
    COPILOT_HOME: join(scratch, 'copilot'),
    PI_CODING_AGENT_DIR: join(scratch, 'pi'),
    PI_CODING_AGENT_SESSION_DIR: join(scratch, 'pi-sessions'),
    PATH: join(scratch, 'no-executables'),
    PYTHONNOUSERSITE: '1',
    PYTHONUTF8: '1',
  });
  return result;
}

export function handshakeSignature(manifest, challenge) {
  const hex = (value, size) =>
    typeof value === 'string' && new RegExp(`^[0-9a-f]{${size}}$`).test(value);
  const origin = (value) =>
    typeof value === 'string' &&
    /^http:\/\/127\.0\.0\.1:[1-9]\d{0,4}$/.test(value) &&
    Number(new URL(value).port) <= 65535;
  if (
    !hex(manifest.nonce, 64) ||
    !hex(challenge, 64) ||
    !hex(manifest.vite_generation, 32) ||
    !hex(manifest.backend_generation, 32) ||
    !origin(manifest.python_origin) ||
    !origin(manifest.vite_origin) ||
    !Number.isSafeInteger(manifest.vite_pid) ||
    manifest.vite_pid < 1
  )
    throw Error('Invalid development handshake fields.');
  const message = [
    'cargento-vite-dev-v1',
    challenge,
    manifest.python_origin,
    manifest.vite_origin,
    manifest.vite_generation,
    manifest.backend_generation,
    String(manifest.vite_pid),
  ].join('\n');
  return createHmac('sha256', Buffer.from(manifest.nonce, 'hex'))
    .update(message, 'ascii')
    .digest('hex');
}
