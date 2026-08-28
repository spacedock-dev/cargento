"use strict";
// A long-lived node process that runs page-JS checks for `PageJsHarness`.
//
// The harness used to spawn one node per check. Measured on macOS, node startup
// was 40ms of the 44ms a check cost, and the suite runs 425 of them — so the
// spawn, not the work, was the bill. Process creation is the operation macOS
// penalises hardest relative to Linux, which is why the macOS CI leg ran ~4.5x
// the Ubuntu one.
//
// Isolation is preserved by giving every check a fresh `vm` context rather than
// a fresh process: the page script declares everything it owns in the source it
// is handed, so a new context is a new set of globals. The page script uses no
// `require`, no `process` and no node module machinery, which is what makes a
// bare context enough.
//
// Framing, both directions: an ASCII byte length, a newline, then that many
// UTF-8 bytes. Length-prefixed rather than newline-delimited because check
// sources and rendered HTML both contain newlines.

const vm = require("node:vm");
const util = require("node:util");

// How long one check may run before the worker calls it hung. Under the
// process-per-check design a check that never settled ended when node's event
// loop drained; here nothing drains, so the deadline is what stops a broken
// test from hanging the suite. Generous enough that a slow CI runner never
// trips it.
const CHECK_TIMEOUT_MS = 30000;

let pending = Buffer.alloc(0);
let pump = Promise.resolve();

process.stdin.on("data", (chunk) => {
  pending = Buffer.concat([pending, chunk]);
  for (const source of takeRequests()) {
    // Serialised: checks share one process, and interleaving them would let a
    // timer from one land in another's context.
    pump = pump.then(() => runCheck(source)).then(reply);
  }
});
process.stdin.on("end", () => {
  pump.then(() => process.exit(0));
});

function takeRequests() {
  const out = [];
  for (;;) {
    const newline = pending.indexOf(10);
    if (newline < 0) return out;
    const length = Number.parseInt(pending.subarray(0, newline).toString("ascii"), 10);
    const start = newline + 1;
    if (pending.length < start + length) return out;
    out.push(pending.subarray(start, start + length).toString("utf8"));
    pending = pending.subarray(start + length);
  }
}

function reply(result) {
  const body = Buffer.from(JSON.stringify(result), "utf8");
  process.stdout.write(`${body.length}\n`);
  process.stdout.write(body);
}

// A bare `vm` context gets V8's built-ins (Object, JSON, Promise, Date...) but
// none of the globals the *host* supplies. In a browser those are platform
// globals the page may use freely, so the ones node also implements are handed
// through — the page reads `URL` and `URLSearchParams` today, and a check that
// picks up another web global should fail on its behaviour, not on its absence.
// Names node does not define are skipped rather than shimmed: a stub would let
// the page pass here and break in a browser.
const WEB_GLOBALS = [
  "URL",
  "URLSearchParams",
  "TextEncoder",
  "TextDecoder",
  "AbortController",
  "AbortSignal",
  "Event",
  "EventTarget",
  "Blob",
  "structuredClone",
  "atob",
  "btoa",
  "performance",
  "crypto",
  "Intl",
];

function hostGlobals() {
  const out = {};
  for (const name of WEB_GLOBALS) {
    if (typeof globalThis[name] !== "undefined") out[name] = globalThis[name];
  }
  return out;
}

async function runCheck(source) {
  const lines = [];
  // `console.log` is the harness's return channel, so it has to format the way
  // node's does: strings verbatim, everything else inspected.
  const write = (...args) =>
    lines.push(args.map((a) => (typeof a === "string" ? a : util.inspect(a))).join(" "));
  const context = vm.createContext({
    ...hostGlobals(),
    console: { log: write, info: write, debug: write, warn: write, error: write },
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    setImmediate,
    clearImmediate,
    queueMicrotask,
  });

  let timer;
  try {
    vm.runInContext(source, context, { filename: "page_test.js" });
    const deadline = new Promise((_resolve, reject) => {
      timer = setTimeout(
        () => reject(new Error(`page check did not settle within ${CHECK_TIMEOUT_MS}ms`)),
        CHECK_TIMEOUT_MS
      );
    });
    await Promise.race([context.__cargentoDone, deadline]);
    return { ok: true, out: lines.join("\n") };
  } catch (error) {
    // stdout still goes back: a check that logged before it threw is easier to
    // diagnose with both halves than with either.
    return { ok: false, out: lines.join("\n"), err: (error && error.stack) || String(error) };
  } finally {
    clearTimeout(timer);
  }
}
