/*
 * The board and the pages the Intent browser tests drive.
 *
 * `startIntentBoard` starts the REAL backend over `frontend/test/intent_backend.py`: the React page through
 * the development supervisor (Vite serves modules, Python serves the document and every /api route). It is
 * `startSessionsBoard` with the helper swapped, because that function names its helper.
 *
 * Nothing here reads a harness store, a model, a clipboard, a notification or a terminal. The transcripts the
 * helper writes live in the scratch tree the launcher points every harness at.
 */
import { join } from 'node:path';
import { startReactWorld } from './support/world.mjs';
import { REPOSITORY, freePorts } from './support/browser.mjs';

/** `{ react: { origin, dev, viteOrigin }, close }`. `close` stops exactly what was started here. */
export async function startIntentBoard({ root = REPOSITORY } = {}) {
  const helper = join(root, 'frontend/test/intent_backend.py');
  /* A sibling run can bind a port between the check that it is free and the bind itself, and then startup
     fails loudly rather than adopting someone else's listener. Try again on other ports, a few times. */
  const refused = [];
  for (let attempt = 0; ; attempt += 1) {
    const ports = await freePorts(2, refused);
    try {
      const dev = await startReactWorld({
        root,
        port: ports[0],
        vitePort: ports[1],
        backendHelper: helper,
      });
      return {
        react: { origin: dev.origin, viteOrigin: dev.viteOrigin, dev },
        close: () => dev.close(),
      };
    } catch (error) {
      refused.push(...ports);
      if (
        attempt >= 3 ||
        !/in use|EADDRINUSE|belongs to another|backend exited|readiness/i.test(
          String(error.message),
        )
      )
        throw error;
    }
  }
}

/* A request the page itself would make, made from outside it, so a test can set the store up (or move the
   board's revision) without driving a page. */
export async function call(origin, method, path, body) {
  const response = await fetch(origin + path, {
    method,
    ...(body
      ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : {}),
    signal: AbortSignal.timeout(15000),
  });
  const text = await response.text();
  try {
    return { status: response.status, body: JSON.parse(text) };
  } catch {
    return { status: response.status, body: text };
  }
}
