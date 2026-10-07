#!/usr/bin/env node
// Production-page baseline. Dependencies: Node >=26, Python, an owned headless Chrome.
import {spawn} from 'node:child_process';
import {mkdtemp, mkdir, readFile, writeFile, rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {tmpdir, platform, arch, release, cpus} from 'node:os';
import {dirname, resolve, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';

const here = dirname(fileURLToPath(import.meta.url));
const help = `Usage: node scripts/frontend_baseline.mjs --output FILE [options]
  --chrome FILE       Chrome executable (or CARGENTO_BASELINE_CHROME)
  --python FILE       Python executable; default python3
  --port NUMBER       Owned backend port 4571..4599; default 4571, no fallback
  --samples NUMBER    Updates per healthy cohort; default 3
  --navigations NUMBER  Repeated sessions/projects/attention navigation; default 5
  --timeout-ms NUMBER Deadline per operation; default 15000
Synthetic cohorts: small=5, median=50, large=250, plus empty/unavailable states.
Only children started by this process and its temporary browser profile are cleaned.
No model calls, native focus, real session stores, or npm dependencies.
`;

function options(argv) {
  const result = {python: 'python3', chrome: process.env.CARGENTO_BASELINE_CHROME,
    port: 4571, samples: 3, navigations: 5, timeoutMs: 15000};
  const keys = {'--output': 'output', '--chrome': 'chrome', '--python': 'python',
    '--port': 'port', '--samples': 'samples', '--navigations': 'navigations', '--timeout-ms': 'timeoutMs'};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--help') { process.stdout.write(help); return null; }
    const key = keys[argv[i]];
    if (!key || !argv[i + 1] || argv[i + 1].startsWith('--')) throw Error(`Unknown/incomplete option ${argv[i]}`);
    result[key] = ['port', 'samples', 'navigations', 'timeoutMs'].includes(key) ? Number(argv[++i]) : argv[++i];
  }
  if (!result.output) throw Error('--output is required');
  if (!result.chrome) throw Error('--chrome or CARGENTO_BASELINE_CHROME is required');
  if (!Number.isInteger(result.port) || result.port < 4571 || result.port > 4599) throw Error('port must be 4571..4599');
  for (const key of ['samples', 'navigations', 'timeoutMs']) {
    if (!Number.isInteger(result[key]) || result[key] < 1 || result[key] > (key === 'timeoutMs' ? 120000 : 100)) {
      throw Error(`${key} is outside its bounded range`);
    }
  }
  if (Number(process.versions.node.split('.')[0]) < 26) throw Error('Node 26 or later is required');
  return result;
}

function lineQueue(stream) {
  const queue = [], waiting = [];
  const reader = createInterface({input: stream});
  reader.on('line', line => waiting.length ? waiting.shift()(line) : queue.push(line));
  return {
    async next(timeout) {
      if (queue.length) return queue.shift();
      return new Promise((resolve, reject) => {
        const consume = line => { clearTimeout(timer); resolve(line); };
        const timer = setTimeout(() => {
          const index = waiting.indexOf(consume);
          if (index >= 0) waiting.splice(index, 1);
          reject(Error('child readiness/control deadline exceeded'));
        }, timeout);
        waiting.push(consume);
      });
    },
    close() { reader.close(); },
  };
}

class CDP {
  constructor(socket, timeout) {
    this.socket = socket; this.timeout = timeout; this.pending = new Map(); this.nextId = 0; this.events = new Set();
    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (!message.id) {
        for (const listener of [...this.events]) listener(message);
        return;
      }
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id); clearTimeout(pending.timer);
      message.error ? pending.reject(Error(JSON.stringify(message.error))) : pending.resolve(message.result);
    });
    socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(Error('CDP closed')); }
      this.pending.clear();
    });
  }
  static async open(url, timeout) {
    const socket = new WebSocket(url);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { socket.close(); reject(Error('CDP connection deadline')); }, timeout);
      socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, {once: true});
      socket.addEventListener('error', () => { clearTimeout(timer); reject(Error('CDP connection failed')); }, {once: true});
    });
    return new CDP(socket, timeout);
  }
  call(method, params = {}, sessionId) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(Error(`CDP deadline: ${method}`)); }, this.timeout);
      this.pending.set(id, {resolve, reject, timer});
      this.socket.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
    });
  }
  event(method, sessionId) {
    return new Promise((resolve, reject) => {
      const listener = message => {
        if (message.method !== method || message.sessionId !== sessionId) return;
        this.events.delete(listener); clearTimeout(timer); resolve(message.params);
      };
      const timer = setTimeout(() => { this.events.delete(listener); reject(Error(`CDP event deadline: ${method}`)); }, this.timeout);
      this.events.add(listener);
    });
  }
  async evaluate(expression, sessionId) {
    const answer = await this.call('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true}, sessionId);
    if (answer.exceptionDetails) throw Error(answer.exceptionDetails.text + ': ' + JSON.stringify(answer.exceptionDetails.exception));
    return answer.result.value;
  }
}

// All observers hold primitive counts, never detached DOM references. Timer counts
// cover main-window JS timers, not browser-internal scheduler work. Instrumentation
// overhead is part of this baseline and must stay identical in later comparisons.
const instrumentation = `(() => {
  const b = window.__baseline = {requests: [], longTasks: [], removedNodes: 0,
    activeTimeouts: new Set(), activeIntervals: new Set(), sockets: new Set(),
    longTaskSupport: PerformanceObserver.supportedEntryTypes.includes('longtask')};
  const timeout = window.setTimeout.bind(window), clear = window.clearTimeout.bind(window);
  const interval = window.setInterval.bind(window), clearInterval = window.clearInterval.bind(window);
  window.setTimeout = (fn, ms, ...args) => {
    let id; const call = typeof fn === 'function' ? () => { b.activeTimeouts.delete(id); Reflect.apply(fn, window, args); } : fn;
    if (typeof fn !== 'function') b.stringTimers = true;
    id = timeout(call, ms); b.activeTimeouts.add(id); return id;
  };
  window.clearTimeout = id => { b.activeTimeouts.delete(id); b.activeIntervals.delete(id); clear(id); };
  window.setInterval = (fn, ms, ...args) => { const id = interval(fn, ms, ...args); b.activeIntervals.add(id); return id; };
  window.clearInterval = id => { b.activeIntervals.delete(id); b.activeTimeouts.delete(id); clearInterval(id); };
  if (b.longTaskSupport) new PerformanceObserver(list => {
    for (const item of list.getEntries()) b.longTasks.push({startMs: item.startTime, durationMs: item.duration});
  }).observe({type: 'longtask', buffered: true});
  new MutationObserver(records => {
    for (const record of records) for (const node of record.removedNodes) {
      b.removedNodes += 1 + (node.querySelectorAll ? node.querySelectorAll('*').length : 0);
    }
  }).observe(document, {subtree: true, childList: true});
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const url = new URL(typeof args[0] === 'string' ? args[0] : args[0].url, location.href);
    const startedMs = performance.now();
    const response = await nativeFetch(...args);
    if (url.pathname === '/api/data') response.clone().text().then(text => {
      const data = JSON.parse(text), fixture = data.baseline_fixture;
      if (fixture) b.requests.push({sequence: fixture.sequence, startedMs,
        responseMs: performance.now(), payloadBytes: new TextEncoder().encode(text).length,
        sessionCount: data.sessions.length, status: response.status});
    }).catch(error => { b.captureError = String(error); });
    return response;
  };
  const NativeSocket = window.WebSocket;
  window.WebSocket = class extends NativeSocket {
    constructor(...args) { super(...args); b.sockets.add(this); this.addEventListener('close', () => b.sockets.delete(this)); }
  };
  b.wait = (predicate, deadline) => new Promise((resolve, reject) => {
    const start = performance.now();
    function frame() {
      if (predicate()) requestAnimationFrame(() => requestAnimationFrame(() => resolve(performance.now())));
      else if (performance.now() - start > deadline) reject(Error('rendered marker deadline exceeded'));
      else requestAnimationFrame(frame);
    }
    frame();
  });
})()`;

async function stopChild(child) {
  if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
  await new Promise(resolve => {
    const timer = setTimeout(() => child.kill('SIGKILL'), 3000);
    child.once('exit', () => { clearTimeout(timer); resolve(); });
    // EOF lets Python close its server and TemporaryDirectory. Chrome has no
    // stdin control channel, so only that owned child receives SIGTERM now.
    if (child.stdin?.writable) child.stdin.end();
    else child.kill('SIGTERM');
  });
}

async function run(o) {
  const report = {schema: 1, environment: {node: process.version, platform: platform(),
    release: release(), arch: arch(), cores: cpus().length}, options: {port: o.port,
    samples: o.samples, navigations: o.navigations}, methodology: {
    paint: 'Actual /api/data fetch start to two animation frames after the fixture title is rendered; a frame boundary proxy, not compositor presentation time.',
    updateTrigger: 'nextRefreshPoll(): the production background-poll path, including its focus/open-choice deferrals; no manual refresh bypass.',
    browserProfile: 'One fresh owned profile per invocation. Each cohort gets one new-document load per invocation; later cohorts share cache with earlier cohorts. Repeat invocations for independent profiles, not independent cold-cache cohorts.',
    observers: 'Main-window fetch/timer/WebSocket wrappers, primitive MutationObserver counts and long-task observer; identical instrumentation required for comparisons.',
    sockets: 'WebSocket instances only; TCP/socket descriptors are unavailable.',
    retention: 'Removed node observations and CDP DOM counters are trends, not proof of retained detached-node memory.',
    statePaint: 'Empty/unavailable have no unique sequence marker in production DOM; update-to-paint unavailable.',
  }, cohorts: [], editor: {status: 'unavailable', reason: 'not attempted'}, navigation: []};
  let backend, chrome, cdp, control, profile;
  let sequence = 1;
  try {
    report.sources = Object.fromEntries(await Promise.all([
      ['driver', fileURLToPath(import.meta.url)], ['fixture', join(here, 'frontend_baseline_fixture.py')],
    ].map(async ([name, path]) => {
      const content = await readFile(path);
      return [name, {sha256: createHash('sha256').update(content).digest('hex'), bytes: content.length}];
    })));
    backend = spawn(o.python, [join(here, 'frontend_baseline_fixture.py'), '--port', String(o.port)],
      {stdio: ['pipe', 'pipe', 'pipe'], cwd: resolve(here, '..')});
    backend.on('error', () => {});
    let backendErrors = '';
    backend.stderr.on('data', chunk => { backendErrors = (backendErrors + chunk).slice(-8000); });
    control = lineQueue(backend.stdout);
    const ready = JSON.parse(await control.next(o.timeoutMs));
    if (!ready.ready) throw Error('fixture did not become ready: ' + backendErrors);
    report.fixture = ready;
    const configure = async (cohort, state) => {
      backend.stdin.write(JSON.stringify({cohort, state, sequence: ++sequence}) + '\n');
      const ack = JSON.parse(await control.next(o.timeoutMs));
      if (!ack.ack || ack.sequence !== sequence) throw Error('fixture control refused: ' + JSON.stringify(ack));
      return ack;
    };
    profile = await mkdtemp(join(tmpdir(), 'cargento-baseline-chrome-'));
    chrome = spawn(o.chrome, ['--headless=new', '--remote-debugging-port=0',
      `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
      '--disable-background-networking', '--disable-component-update', '--disable-sync',
      '--disable-extensions', '--disable-default-apps', 'about:blank'], {stdio: ['ignore', 'ignore', 'pipe']});
    chrome.on('error', () => {});
    const debug = lineQueue(chrome.stderr);
    let endpoint;
    try {
      while (!endpoint) {
        const line = await debug.next(o.timeoutMs);
        endpoint = line.match(/DevTools listening on (ws:\/\/\S+)/)?.[1];
      }
    } finally { debug.close(); }
    cdp = await CDP.open(endpoint, o.timeoutMs);
    report.environment.chrome = await cdp.call('Browser.getVersion');
    const {targetId} = await cdp.call('Target.createTarget', {url: 'about:blank'});
    const {sessionId} = await cdp.call('Target.attachToTarget', {targetId, flatten: true});
    const call = (method, params) => cdp.call(method, params, sessionId);
    const evaluate = expression => cdp.evaluate(expression, sessionId);
    const poll = async () => {
      const available = await evaluate(`typeof nextRefreshPoll === 'function' ? (nextRefreshPoll(), true) : false`);
      if (!available) throw Error('Production background-poll adapter nextRefreshPoll() unavailable; implement an equivalent explicit poll adapter before comparing baselines');
    };
    await call('Page.enable'); await call('Runtime.enable');
    await call('Page.addScriptToEvaluateOnNewDocument', {source: instrumentation});
    const url = `http://127.0.0.1:${o.port}/`;
    const markerPaint = async seq => evaluate(`(async () => {
      const at = await __baseline.wait(() => __baseline.requests.some(r => r.sequence === ${seq}) &&
        document.body.innerText.includes(${JSON.stringify(`Baseline ${seq} session`)}), ${o.timeoutMs});
      const request = __baseline.requests.find(r => r.sequence === ${seq});
      return {...request, paintedMs: at, getToPaintMs: at - request.startedMs};
    })()`);
    const footprint = async () => ({...await call('Memory.getDOMCounters'),
      ...await evaluate(`(() => { const b=__baseline; return {removedNodeObservations:b.removedNodes,
        activeMainWindowTimeouts:b.stringTimers ? null : b.activeTimeouts.size,
        activeMainWindowIntervals:b.activeIntervals.size, activeWebSockets:b.sockets.size,
        tcpSockets:{status:'unavailable',reason:'CDP does not expose process TCP descriptors'},
        eventSourceConnections:{status:'unavailable',reason:'EventSource lifecycles are not instrumented'},
        retainedDetachedNodes:{status:'unavailable',reason:'DOM counters do not identify detached-node retention'},
        longTasks:b.longTaskSupport ? b.longTasks : {status:'unavailable',reason:'longtask unsupported'},
        captureError:b.captureError || null}; })()`)});
    for (const cohort of ['small', 'median', 'large']) {
      const first = await configure(cohort, 'healthy');
      const loaded = cdp.event('Page.loadEventFired', sessionId);
      await call('Page.navigate', {url}); await loaded;
      const paint = await markerPaint(first.sequence);
      const record = {cohort, fixture: first, firstRenderMs: paint.paintedMs,
        firstGetToPaint: paint, updates: [], states: []};
      for (let sample = 0; sample < o.samples; sample++) {
        const next = await configure(cohort, 'healthy');
        await poll();
        record.updates.push({trigger: 'nextRefreshPoll', ...await markerPaint(next.sequence)});
      }
      record.footprint = await footprint();
      for (const state of ['empty', 'unavailable']) {
        const next = await configure(cohort, state);
        await poll();
        const request = await evaluate(`(async()=>{await __baseline.wait(()=>__baseline.requests.some(r=>r.sequence===${next.sequence}),${o.timeoutMs});return __baseline.requests.find(r=>r.sequence===${next.sequence});})()`);
        record.states.push({state, trigger: 'nextRefreshPoll', request, updateToPaint: {status: 'unavailable',
          reason: 'No unique sequence marker rendered for this state'}, bodyText: await evaluate('document.body.innerText.slice(0,1500)')});
      }
      report.cohorts.push(record);
    }
    const restored = await configure('small', 'healthy');
    await poll(); await markerPaint(restored.sequence);
    const sessionHash = '#n=session:baseline-project:claude:b0000000';
    await evaluate(`location.hash=${JSON.stringify(sessionHash)}`);
    await evaluate(`__baseline.wait(()=>!!document.querySelector('textarea[data-next-cockpit-held-key]'),${o.timeoutMs})`);
    await evaluate(`(() => {const e=document.querySelector('textarea[data-next-cockpit-held-key]'); e.focus(); window.__baselineEditor=e;})()`);
    await call('Input.dispatchKeyEvent', {type: 'keyDown', key: 'End', code: 'End', windowsVirtualKeyCode: 35});
    await call('Input.dispatchKeyEvent', {type: 'keyUp', key: 'End', code: 'End', windowsVirtualKeyCode: 35});
    const keyboardEndApplied = await evaluate('__baselineEditor.selectionEnd===__baselineEditor.value.length');
    await call('Input.insertText', {text: 'Baseline native editor draft'});
    const before = await evaluate(`({value:__baselineEditor.value, start:__baselineEditor.selectionStart,
      end:__baselineEditor.selectionEnd, focused:document.activeElement===__baselineEditor})`);
    const updated = await configure('small', 'healthy');
    await poll(); await markerPaint(updated.sequence);
    const after = await evaluate(`(() => {const e=document.querySelector('textarea[data-next-cockpit-held-key]');return {
      value:e?.value,start:e?.selectionStart,end:e?.selectionEnd,focused:document.activeElement===e,
      sameNode:e===__baselineEditor};})()`);
    report.editor = {status: 'measured', trigger: 'nextRefreshPoll', before, after,
      draftRetained: after.value === before.value,
      focusRetained: before.focused && after.focused,
      selectionRetained: before.start === after.start && before.end === after.end,
      keyboardEndApplied,
      nativeTypingApplied: before.value.includes('Baseline native editor draft')};
    // Release the intentionally held node before DOM-retention trends are recorded.
    await evaluate('delete window.__baselineEditor');
    report.navigation.push({step: 0, ...await footprint()});
    for (let step = 1; step <= o.navigations; step++) {
      for (const route of ['projects', 'attention', 'sessions']) {
        await evaluate(`location.hash=${JSON.stringify('#n=' )}+${JSON.stringify(route)}`);
        await evaluate(`__baseline.wait(()=>[...document.querySelectorAll('[aria-current="page"]')].some(e=>e.textContent.toLowerCase().includes(${JSON.stringify(route)})),${o.timeoutMs})`);
      }
      report.navigation.push({step, ...await footprint()});
    }
  } catch (error) {
    report.fatal = String(error?.stack || error);
  } finally {
    cdp?.socket.close(); control?.close();
    await stopChild(chrome); await stopChild(backend);
    if (profile) await rm(profile, {recursive: true, force: true});
    await mkdir(dirname(resolve(o.output)), {recursive: true});
    await writeFile(resolve(o.output), JSON.stringify(report, null, 2) + '\n', {mode: 0o600});
  }
  if (report.fatal) throw Error(`Baseline incomplete; inspect ${resolve(o.output)}: ${report.fatal}`);
  process.stdout.write(JSON.stringify({output: resolve(o.output), cohorts: report.cohorts.length, editor: report.editor}) + '\n');
}

try { const o = options(process.argv.slice(2)); if (o) await run(o); }
catch (error) { process.stderr.write(String(error.message || error) + '\n'); process.exitCode = 1; }
