import { createServer as createHttpServer } from 'node:http';
import { realpath } from 'node:fs/promises';
import { join, resolve, relative, isAbsolute } from 'node:path';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { handshakeSignature, parseArguments } from './protocol.mjs';
import { readFonts } from '../build/package.mjs';

let vite, manifest, dispatch;
let stopping;
async function stop() {
  if (stopping) return stopping;
  stopping = (async () => {
    if (vite) await vite.close();
    if (process.connected) process.disconnect();
  })();
  return stopping;
}

function refuse(res) { res.writeHead(403, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' }); res.end('Development origin refused.'); }
function exactHeader(req, name, value) {
  let count = 0;
  for (let index = 0; index < req.rawHeaders.length; index += 2) if (req.rawHeaders[index].toLowerCase() === name) count++;
  return count === 1 && req.headers[name] === value;
}

async function start(options) {
  if (vite || manifest) throw Error('Vite worker was already started.');
  parseArguments(['--port', String(options.pythonPort), '--vite-port', String(options.port)]);
  manifest = { nonce: options.nonce, python_origin: `http://127.0.0.1:${options.pythonPort}`,
    vite_origin: `http://127.0.0.1:${options.port}`, vite_generation: options.viteGeneration,
    backend_generation: options.backendGeneration, vite_pid: process.pid };
  handshakeSignature(manifest, '00'.repeat(32));
  const authority = `127.0.0.1:${options.port}`;
  const fontCss = (await readFonts(options.root)).css;
  const frontendRoot = await realpath(join(options.root, 'frontend'));
  const modulesRoot = await realpath(join(options.root, 'node_modules'));
  const cacheRoot = join(await realpath(options.scratch), '.vite-dev-cache');
  const allowedRoots = [frontendRoot, modulesRoot, cacheRoot];
  const confined = path => allowedRoots.some(root => {
    const tail = relative(root, path);
    return tail === '' || (tail !== '..' && !tail.startsWith('..' + (process.platform === 'win32' ? '\\' : '/')) && !isAbsolute(tail));
  });
  dispatch = createHttpServer(); // Never bound. Vite receives only admitted upgrade events.
  // Vite's first Windows realpath is the JS one, which keeps an 8.3 segment such as RUNNER~1, and it then refuses
  // every file under that spelling. Hand it the native canonical root this worker already admits against.
  vite = await createServer({ configFile: false, envFile: false, root: frontendRoot,
    plugins: [react(), { name: 'cargento-dev-origin', configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!exactHeader(req, 'host', authority) || req.method !== 'GET') return refuse(res);
        let path;
        try { path = new URL(req.url, manifest.vite_origin).pathname; } catch { return refuse(res); }
        if (path === '/__cargento_dev_handshake') {
          const challenge = req.headers['x-cargento-dev-challenge'];
          if (Object.hasOwn(req.headers, 'origin') || req.headers['x-cargento-dev-generation'] !== manifest.backend_generation ||
            typeof challenge !== 'string' || !/^[0-9a-f]{64}$/.test(challenge)) return refuse(res);
          const body = JSON.stringify({ format: 1, vite_generation: manifest.vite_generation,
            backend_generation: manifest.backend_generation, vite_pid: process.pid, signature: handshakeSignature(manifest, challenge) });
          res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(body); return;
        }
        if (!exactHeader(req, 'origin', manifest.python_origin) || path === '/' || path.endsWith('.html') ||
            ['document', 'iframe', 'frame'].includes(req.headers['sec-fetch-dest'])) return refuse(res);
        if (path === '/__cargento_dev_fonts.css') {
          res.writeHead(200, { 'Content-Type': 'text/css', 'Cache-Control': 'no-store',
            'Access-Control-Allow-Origin': manifest.python_origin }); res.end(fontCss); return;
        }
        // Vite's path allowlist alone does not confine directory symlinks.
        // Check the actual served file before any transform/static middleware.
        try {
          const decoded = decodeURIComponent(path);
          const fsPath = decoded.startsWith('/@fs/') ? decoded.slice(5) : null;
          const file = fsPath === null ? resolve(frontendRoot, '.' + decoded)
            : (fsPath.startsWith('/') || /^[A-Za-z]:[\\/]/.test(fsPath) ? fsPath : '/' + fsPath);
          if (!confined(file)) return refuse(res);
          try { if (!confined(await realpath(file))) return refuse(res); }
          catch (error) { if (!['ENOENT', 'ENOTDIR'].includes(error.code)) return refuse(res); }
        } catch { return refuse(res); }
        next();
      });
    } }], appType: 'custom', publicDir: false, cacheDir: cacheRoot,
    server: { host: '127.0.0.1', port: options.port, strictPort: true, allowedHosts: ['127.0.0.1'],
      origin: manifest.vite_origin, cors: { origin: manifest.python_origin }, open: false, forwardConsole: false,
      fs: { strict: true, allow: allowedRoots },
      ws: { server: dispatch, host: '127.0.0.1', clientPort: options.port, path: '__cargento_hmr', protocol: 'ws' } } });
  vite.httpServer.on('upgrade', (req, socket, head) => {
    let path;
    try { path = new URL(req.url, manifest.vite_origin).pathname; } catch { path = ''; }
    if (!exactHeader(req, 'host', authority) || !exactHeader(req, 'origin', manifest.python_origin) || path !== '/__cargento_hmr' ||
        !['vite-hmr', 'vite-ping'].includes(req.headers['sec-websocket-protocol'])) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'); return;
    }
    dispatch.emit('upgrade', req, socket, head);
  });
  await vite.listen();
  process.send({ type: 'ready', pid: process.pid, origin: manifest.vite_origin, generation: manifest.vite_generation });
}

process.on('message', async message => {
  try {
    if (message.type === 'start') await start(message);
    else if (message.type === 'backend-generation' && vite && /^[0-9a-f]{32}$/.test(message.generation)) {
      manifest.backend_generation = message.generation;
      process.send({ type: 'generation-ready', generation: message.generation });
    } else if (message.type === 'stop') await stop();
    else throw Error('Unexpected development worker message.');
  } catch (error) {
    if (process.connected) process.send({ type: 'error', message: error.message });
    await stop(); process.exitCode = 1;
  }
});
process.on('disconnect', stop);
process.on('SIGTERM', stop);
process.on('SIGINT', stop);
