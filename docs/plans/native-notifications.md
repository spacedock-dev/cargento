# Plan: native Linux/Windows/WSL notifications, and other open items

**Status:** unshipped. This is the only remaining work from the cross-platform effort, plus the
items that were deliberately deferred with a named condition for revisiting them.

Everything that shipped is documented in [`COMPATIBILITY.md`](../../COMPATIBILITY.md) (behavior) and
[`design-cross-platform.md`](../design-cross-platform.md) (rationale). Delete this file once its
contents ship or are dropped.

---

## 1. Native notification backends behind `--notify`

Today the server has one native backend, `osascript` on macOS; Linux and Windows fall back to the
browser Notification API, which only fires while a dashboard tab is open. The hook path
(`POST /api/notify`, which exists precisely to work with no tab) therefore delivers nothing on those
platforms.

Deliver: `notify-send` on Linux, `wsl-notify-send.exe` (falling back to `powershell.exe`) on WSL,
and a PowerShell toast on Windows — each behind `--notify`, each written as a pure selector function
per design decision D-4 so the Ubuntu runner can exercise it.

Three constraints on code that does not exist yet:

- **Toast XML is an injection surface.** `notification_text` strips control characters but not `<`,
  `>` or `&`. Any XML-shaped backend must XML-escape the message and pass arguments via argv, never
  through a shell. (Ruff's `select = ALL` will also demand a justified `S603`/`S607` suppression.)
- **Delivery can never be guaranteed.** Windows toasts want a registered AppUserModelID and an
  interactive session; `notify-send` wants a graphical user D-Bus session; WSL interop can be
  disabled by policy. The honest exit criterion is graceful degradation plus a *reported* delivery
  status — every backend must no-op-with-a-log, never raise. Ship it labeled experimental.
- **Latency is fine; holding the lock is not.** A backend that spawns a subprocess can block for
  hundreds of milliseconds, and all three of these are slower to start than `osascript`. That is
  safe only because the server is threaded and both dispatch sites invoke the notifier *after*
  releasing `_lock`. Never call a backend while holding it. Probing for an available backend at
  startup is therefore an optimization, not a correctness requirement — an earlier revision of this
  plan had that backwards.

Per D-3, `--notify` must state which owner it disables.

**Related gap:** idle nudges (`idle_prompt`) pop without marking the session blocked. macOS delivers
them; the page only notifies on a needs-input transition, so on Linux and Windows an idle nudge
produces no popup at all. Closing it needs a one-shot event channel in `/api/data` rather than a
state flag — worth doing alongside the native backends, not bolted onto the page.

## 2. Deferred, with the trigger that should revive them

- **NTFS last-write lag.** Windows does not fully update a file's last-write time while a writer
  holds the handle open. Working/Idle is largely mtime-based, so an actively generating Windows
  session could read Idle. The premise is documented by Microsoft but unverified here — whether it
  bites depends on how often each harness flushes and closes. Reshaping state detection across eight
  collectors on an unverified premise is exactly what D-6 forbids.
  **Revisit when:** a Windows user reports a session stuck on Idle while visibly generating, or
  `--diagnose` shows a growing store with a stale mtime. The fix is a size/WAL-size delta between
  polls, preferring parsed event timestamps with mtime as fallback.
- **WAL across a network or synced home.** SQLite's write-ahead log needs shared-memory coordination
  on a single host. Roaming profiles, UNC/SMB homes and cloud-synced directories can present
  inconsistent `db` / `-wal` / `-shm` triples, and the symptom is an empty harness. No detection
  exists; it should warn rather than report nothing.
- **Coarse filesystem timestamps.** FAT/exFAT write time has two-second resolution, and network or
  translated filesystems can coarsen it further. The title caches keyed on `(st_mtime_ns, st_size)`
  can therefore serve a stale title after a same-size rewrite. Unmitigated, low impact.

## 3. Adjacent, recorded but not planned

- **Containers and `--bind`.** `-p 127.0.0.1:4553:4553` cannot reach a server bound to the
  *container's* loopback, and the fixed port permits one instance per network namespace. Adding
  `--bind` is coupled to the loopback exposure documented in `SECURITY.md` — it is a security and
  deployment change, not a portability one, and the skill body currently says bluntly not to change
  the bind address.
- **Release gate.** `release.yml` is a single Ubuntu job with no `needs`, so a tag on a red `main`
  tip still releases. Either make it depend on the `quality-gate` status of the tagged commit, or
  say plainly in `AGENTS.md` that it does not. The current silent mismatch is the only unacceptable
  option.

## 4. Questions only a real machine can answer

`--diagnose` output from any Windows user substitutes for all four.

1. One Claude `~/.claude/projects/` directory name on native Windows, plus the working directory it
   came from — the only way to settle how a drive letter and backslashes are encoded.
2. Whether Codex writes `\` in `cwd` / `agent_path` on Windows.
3. Goose and OpenCode Windows store paths, confirmed against upstream source rather than blog posts.
4. Whether `cursor-agent` and Antigravity CLI ship native Windows builds at all. If they do not, the
   matrix says six harnesses on Windows rather than eight — a documentation outcome, not a failure.

## 5. Open maintainer decisions

- **The `platform = "darwin"` mypy pin.** Its stated justification is no longer true —
  `mypy --platform linux` passes clean on the current tree, because the remaining platform branch
  goes through `native_notifier(sys.platform)`, which mypy does not narrow. Delete the pin or write
  a true justification; leaving a false one invites a wrong conclusion.
- **The coverage ratchet.** The figures recorded in `pyproject.toml` predate the cross-platform
  test suite and understate real coverage substantially. Read the current number off an Ubuntu
  gate run and ratchet `fail_under` in a dedicated PR, so the move is visible on its own.
- **Undocumented store environment variables.** `XDG_DATA_HOME`, `LOCALAPPDATA` and `APPDATA` move
  real stores but are absent from `STORE_ENV_VARS`, so `--diagnose` reports "overrides: none" while
  they are in effect. Adding them makes the diagnostic honest, but the documentation-matches-code
  test then requires the skill body to mirror them — and D-6 argues against advertising an override
  whose upstream semantics are not documented. Decide before documenting them either way.
