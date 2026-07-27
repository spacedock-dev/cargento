# Cargento cross-platform analysis and plan (v2)

**Scope:** make `cargento/skills/cargento/server.py` (3,222 lines, stdlib-only, Python 3.11+) work on
Linux and Windows (native PowerShell/cmd, WSL2, Git Bash) as well as it does on macOS.

**Method:** static analysis of the repo, targeted web research on each harness's storage and each
platform's APIs, empirical verification of every claim that could be tested locally, then three
adversarial Codex reviews (code-correctness, platform-expertise, plan-feasibility). v1 had 21
findings; the review pass deleted 3 as wrong, materially corrected 8, and added 12 new ones. §8
records the disposition.

Line references are `cargento/skills/cargento/server.py` unless stated. Claims are tagged
**[verified]** (reproduced on this machine), **[documented]** (vendor/CPython docs), or
**[unconfirmed]** (needs a real box).

---

## 1. Headline

The single biggest risk is **silent false-negative discovery**: Cargento reports a clean dashboard
that simply omits the user's sessions. Every collector swallows its errors by design — a broken
harness store is skipped, never fatal (`:2376`) — which is correct robustness but means a
wrong path, an unreadable database, or an unescaped glob produces *zero sessions and no complaint*.
Most findings below funnel into that failure mode, and the plan's most valuable single deliverable
is therefore not a fix but `--diagnose`: a command that says where it looked and what happened.

Also note the most surprising result: **two of the worst bugs are not Windows bugs at all.** The
SQLite URI defect (§3.B) and the glob-metacharacter defect (§3.A5) both reproduce on macOS today.

---

## 2. Target support matrix

| Capability | macOS | Linux | Windows native | WSL2 |
|---|---|---|---|---|
| Harness discovery | works | must work | must work | must work (Linux-side stores) |
| Dashboard UI + `/api/data` | works | works | must work | must work (host browser) |
| Turn ETA / token rate | works | works | must work | must work |
| Task age from birthtime | works | mtime fallback | 3.12+ only (floor is 3.11) | mtime fallback |
| Popups — browser (tab open) | new | new | new | new |
| Popups — native (hook, no tab) | works | phase 6 | phase 6, experimental | phase 6, experimental |
| Documented start/stop commands | works | must work | must work | must work |

**Declared topology:** server and agents on the same side of the WSL boundary. Reading a
Windows-side store from inside WSL happens to work over `/mnt/c` but 9p latency and mtime
granularity make state detection unreliable — document as unsupported, not half-supported.

**Not promised:** "popups work everywhere." The honest exit criterion is *graceful degradation plus
a reported delivery status* — `notify-send` needs a graphical user D-Bus session, PowerShell toasts
need an interactive session and enabled WSL interop, and browser notifications need permission.

---

## 3. Findings

### A. Discovery — where Cargento looks

- **A1 [partly confirmed]** — Most harness roots are fixed `HOME` + POSIX suffix (`:44-58`).
  Two already honor XDG via `DATA_HOME` (`:41`): OpenCode and Goose. But sharing one `DATA_HOME`
  constant is still the wrong abstraction, because those two tools use *different* strategies off
  Linux — Goose's Windows store is org-scoped (`%APPDATA%\Block\goose\...`), OpenCode's is not.
- **A2 [documented]** — Relocation env vars are all ignored. Verified names: `CLAUDE_CONFIG_DIR`
  (relocates *every* `~/.claude` path), `CODEX_HOME`, `COPILOT_HOME`, `GOOSE_PATH_ROOT` (currently
  documented as unsupported at `SKILL.md:21`), and **`GEMINI_CLI_HOME`** — which creates `.gemini`
  *inside* the given directory, so the resolver must append, not substitute. *(v1 said
  `GEMINI_DATA_DIR`; that is a third-party tool's variable, not Gemini CLI's. Corrected.)* This is
  not Windows-specific: a Linux user with `CLAUDE_CONFIG_DIR` set sees zero Claude sessions today.
- **A3 [documented, corrected]** — Copilot's current default *is* `~/.copilot`, and older XDG
  locations are migrated into it at startup. v1's "honor XDG for Copilot" was stale. The real gap
  is `COPILOT_HOME`.
- **A4** — Discovery is single-candidate (`HARNESSES`, `:2309-2353`). `discovered: false` cannot
  distinguish "tool absent" from "looked in the wrong place."
- **A5 [verified — NEW, all platforms, silent total failure]** — Literal directory roots are
  interpolated straight into `glob()` patterns at ~11 sites (`:1021, 1295, 1311, 1479, 1788, 1835,
  1907, 1957, 2110, 2269, 2320-2350`). A home directory containing a glob metacharacter breaks
  discovery completely and silently. Reproduced locally:

  ```
  home = ".../A [Contractor]"
  glob(home + "/.claude/projects/*/*.jsonl")               -> []          # file exists
  glob(glob.escape(home) + "/.claude/projects/*/*.jsonl")  -> ['...jsonl'] # found
  ```

  `[` is legal in Windows account names and in POSIX paths. Fix: `glob.escape()` the literal root
  portion, or traverse with `os.scandir`. Also note `glob()` result order is unspecified, which
  makes equal-mtime "newest file wins" tie-breaks nondeterministic across platforms.

### B. SQLite access

- **B1 [verified]** — Three sites build a URI by raw interpolation: `_sql_ro` (`:1950`),
  `_cursor_title` (`:2070`), `antigravity_step_activity` (`:1743`). SQLite percent-decodes the path.
  Reproduced on macOS today:

  ```
  file:/…/a%41b.db?mode=ro    -> OperationalError: unable to open database file
  file:/…/a%2541b.db?mode=ro  -> opens
  ```

  `?` and `#` are equally hazardous [documented]. On Windows the SQLite docs are explicit: convert
  every `\` to `/` and prepend `/` before a drive letter — `file:C:\Users\x\a.db` is invalid as
  written.
- **B1-fix caveat [documented]** — `urllib.request.pathname2url` is the right primitive but is *not*
  a drop-in: on POSIX a path with a leading `//` becomes a URI authority, and on Windows a UNC path
  becomes `file://server/share/...`, which SQLite rejects (authority must be empty or `localhost`).
  Verified locally: `\\server\share\x.db` → `file://server/share/x.db`. The builder needs its own
  tests for `%`, `?`, `#`, spaces, leading `//`, drive paths, and UNC.
- **B2 [documented — v1 WAS WRONG]** — v1 proposed giving `_sql_ro` the `immutable=1` fallback that
  `antigravity_step_activity` has. **Do not do this.** SQLite states that `immutable=1` on a
  database that is in fact changing can return incorrect results or `SQLITE_CORRUPT`. These are
  *live* agent databases. The existing antigravity code accepts that trade deliberately and
  documents it (`:1730-1735`); generalizing it would trade a discovery gap for a correctness bug.
  The right move is to diagnose why `mode=ro` fails (usually `-shm` creation) and report it, not to
  silently downgrade. Also, a retry ladder must wrap connect *and* first query — connection can
  succeed and the query then fail (`:1745-1754` already does this; `_sql_ro` callers do not).
- **B3 [documented — NEW]** — `import sqlite3` at module scope (`:27`). `sqlite3` is an *optional*
  stdlib module; minimal/musl/Alpine Python builds omit `_sqlite3`, so the whole server fails at
  import and even the JSONL-only harnesses become unavailable. Fix: lazy-import, mark the four
  DB-backed harnesses unavailable with a diagnostic.
- **B4 [documented — NEW]** — WAL requires shared memory coordination on one host. Roaming
  profiles, UNC/SMB homes, and OneDrive-synced directories can present inconsistent `db`/`-wal`/
  `-shm` triples. Detect and warn rather than reporting empty.

### C. Notifications

`notify_mac` (`:1095`) returns immediately off darwin. Two delivery paths depend on it: transcript
detection via `maybe_popup` (`:1144`, needs a polling tab) and hook POSTs (`:3197`, works with no
tab). Only the second genuinely requires an OS-native backend; the first can be served portably by
the browser's Notification API, since localhost is a secure context.

- **C1** — Linux needs `notify-send`; Windows needs a PowerShell toast; WSL needs to reach the host
  (`wsl-notify-send.exe`, else `powershell.exe`). All are new features, not defects — the current
  contract explicitly promises macOS-only (`SKILL.md:46`).
- **C2 [documented]** — None of these can be *guaranteed*: Windows toasts want a registered
  AppUserModelID and an interactive session; `notify-send` wants a graphical user bus; WSL interop
  can be disabled. Every backend must no-op-with-a-log, never raise.
- **C3 [corrected]** — v1 claimed a slow probe would stall the dashboard. Wrong: both call sites
  release `_lock` before invoking the subprocess (`:1147-1158`, `:3174-3197`) and the server is
  threaded. Startup-time backend selection is an optimization, not a correctness requirement.
- **C4 [NEW]** — Adding browser notifications creates **two owners for one transition** and will
  double-fire: `maybe_popup` runs *during* the `/api/data` collection that the page is about to
  render from. Ownership must be defined before either is built (see §4 D-3).
- **C5 [NEW]** — A PowerShell toast is built from XML. `notification_text` (`:121`) strips control
  characters but not `<`, `>`, `&`. Any backend must XML-escape and pass arguments via argv, never
  `shell=True` — and ruff `select = ALL` will demand a justified `S603`/`S607` suppression.

### D. Server lifecycle and operator commands

- **D1 [documented, fix corrected]** — `ThreadingHTTPServer` inherits `allow_reuse_address = 1`
  [verified locally]. On Windows `SO_REUSEADDR` lets a *second process bind an already-bound port*
  with indeterminate delivery. v1's fix (`allow_reuse_address = False`) is insufficient: it stops
  Cargento requesting reuse but does not stop anyone else hijacking. The real fix is
  `SO_EXCLUSIVEADDRUSE` set before `bind()` on Windows.
- **D2 [documented — NEW]** — Bind errors escape raw (`:3216`). Windows can return WinError 10013
  (access denied, firewall/policy) as well as address-in-use; these need distinct, actionable
  messages.
- **D3 [verified]** — Stop instructions (`SKILL.md:94`) are `lsof`-only. Absent on Windows and many
  minimal Linux images.
- **D4 [documented, corrected]** — v1 proposed `python3 -m webbrowser` as "one command everywhere."
  It is not: **`python3` does not reliably exist on native Windows** (`py -3` / `python`). This
  same defect is in the *start* command at `SKILL.md:37` — the more important one.
- **D5 [verified — NEW]** — The backgrounding instruction ("append `&`", `SKILL.md:40`) is
  POSIX-only. PowerShell's `&` is the call operator; cmd needs `start "" /b`; PowerShell needs
  `Start-Process -PassThru`.
- **D6 [verified — NEW]** — The `Notification`-hook snippet (`SKILL.md:55-70`) is POSIX-shaped
  end-to-end: single-quote semantics, `/dev/null`, `|| true`, `--data-binary @-`. Fixing only the
  `curl` → `curl.exe` alias does not make it work. PowerShell 5.1 also lacks `||`. Best fix: ship a
  tiny stdlib forwarder script that reads stdin and POSTs, so the hook line is one interpreter
  invocation on every platform.
- **D7 [documented, corrected]** — v1 blamed cp1252 consoles for `print()` failures. Overstated:
  CPython uses Unicode console APIs since PEP 528. The real exposure is **redirected stdout** —
  which is exactly how the skill tells you to run the server. A failing diagnostic `print` inside
  `collect()`'s handler (`:2378`) escapes that handler. Use a guarded safe-writer, not an
  unconditional `sys.stdout.reconfigure` (which is unsafe when stdout has been replaced and changes
  macOS/Linux behavior too).
- **D8 [verified — NEW]** — IPv6 is internally inconsistent. `LOCAL_HOSTS` advertises `::1`/`[::1]`
  (`:3088`) but the socket is IPv4-only (`:3216`). And the Host parse is wrong for two forms:
  `"[::1]".rsplit(":",1)[0]` → `'[:'` → 403, and `LOCALHOST` → 403 despite DNS being
  case-insensitive. Low severity (browsers send a port), but it is dead code promising something
  the bind does not deliver.

### E. Text and timestamps

- **E1 [corrected]** — `open(fp)` with no encoding at `:1025` and `:1074` uses the locale default
  (cp1252 on Windows). v1 said one non-ASCII character kills the Claude collector. **Both halves
  were wrong.** (a) The likelier outcome is *silent mojibake* — most UTF-8 byte sequences decode
  fine as cp1252 into garbage; only sequences containing cp1252-undefined bytes (0x81, 0x8D, 0x8F,
  0x90, 0x9D) raise. (b) When it does raise, `UnicodeDecodeError` is a `ValueError` but not a
  `json.JSONDecodeError` [verified], so it escapes `:1028`/`:1076` — but `collect()` catches it
  (`:2376`), marks Claude errored for *that refresh*, and the next poll retries. Corrupted titles,
  not a dead harness. Fix is unchanged and still worth doing: `encoding="utf-8"`, catch
  `ValueError`.
- **E2 [verified — NEW]** — **Future timestamps never age out.** Every state test is
  `now - ts <= threshold`, which is trivially true for negative ages (`:1319-1434, 1778-1803,
  1864-1873, 1991-2006, 2178-2200`). A clock-skewed mtime — routine after a WSL2 host suspend, or
  from a cross-boundary copy — pins a session to **Working** for the whole duration of the skew and
  inflates the token rate. It also leaks into the UI: a future-dated turn start produced
  `pct: -144000`.
  **Corrected during implementation:** clamping the age at zero does *not* fix this — zero reads as
  "just now", which is still fresh. An implausibly future timestamp must be *rejected* so no
  activity is invented from it, with a small tolerance band clamped instead (sampling noise between
  `stat()` and the collection clock, and coarse filesystem write times, are not skew).
- **E3 [documented — NEW]** — NTFS last-write time is not fully updated while a writer holds the
  handle open. Working/Idle is almost entirely mtime-based, so an actively generating Windows
  session can read Idle. Mitigate by tracking size/WAL-size deltas between polls and preferring
  parsed event timestamps, with mtime as fallback.
- **E4 [documented — NEW]** — `st_birthtime` landed on Windows in CPython **3.12**; the advertised
  floor is 3.11 (`SKILL.md:40`). On 3.11/Windows, `getattr(st, "st_birthtime", st.st_mtime)`
  (`:1037`) silently degrades task ages. Either raise the Windows floor to 3.12 or document it.
- **E5 [documented — NEW]** — FAT/exFAT write time has 2-second resolution; network and translated
  filesystems can also coarsen it. Caches keyed on `(mtime_ns, size)` (`:368`, `:430`, `:2056`) can
  therefore serve stale titles after a same-size rewrite.

### F. Path-string semantics

- **F1 [unconfirmed]** — `HOME_PREFIX = HOME.replace("/", "-")` (`:76`) and `project_label`
  (`:153`) assume POSIX homes; on Windows the replacement is a no-op and rows would show the full
  encoded path. **Blocking unknown:** how Claude Code encodes a drive letter and backslashes into a
  `~/.claude/projects/` directory name is undocumented. The POSIX form (`/home/user/work/repo` →
  `-home-user-work-repo`) is confirmed. Do not guess — see §6.
- **F2 [confirmed, line corrected]** — `codex_meta` splits `agent_path` on a hardcoded `"/"` at
  **`:286`** (v1 said 285). On native Windows `os.path.basename` would handle both separators; the
  hardcoded `"/"` will not. One-line fix.
- **F3 [DELETED — v1 was wrong]** — v1 claimed `os.path.basename(cwd.rstrip(os.sep))` (`:1809`) is
  broken. On native Windows `os.path` *is* `ntpath` and already understands both separators, and
  the declared topology excludes reading foreign-shaped stores. A generic "split on both
  separators" helper would actively *regress* POSIX, where `\` is a legal filename character. No
  defect; no helper.
- **F4 [DELETED — v1 was wrong]** — v1 claimed the `commonpath` containment check (`:520`) needs
  `normcase`. Disproved locally: `ntpath.commonpath` already case-folds for comparison and returns
  the prefix in the first argument's casing, so `commonpath((root, path)) == root` holds under case
  differences. Confirmed independently by the code reviewer.
- **F5 [speculative, downgraded]** — Windows `MAX_PATH`. Claude's encoded project directories are
  long by construction, but nothing here demonstrates an overflow, modern Windows/Python support
  extended paths, and the relevant reads already `continue` on `OSError`. Documentation + one test,
  not code.

### G. Live-file access

- **G1 [corrected]** — Python's `open()` on Windows omits `FILE_SHARE_DELETE`, so while Cargento
  holds a transcript open the writing harness cannot rename or delete it. v1 proposed replacing
  `mmap` with chunked reads. **That fixes nothing** — a chunked loop holds the same handle for the
  same duration. Real options: a `ctypes` `CreateFileW` with `FILE_SHARE_DELETE` (heavy), or
  deliberately short reopen windows (cheap, partial). Be honest about which.
- **G2 [INVERTED — v1 had this backwards]** — v1 said Windows `mmap` + writer truncation causes an
  uncatchable crash and that POSIX was safe. It is the other way round. On Windows, truncation
  *fails while a view is mapped* (the writer errors). The classic uncatchable **`SIGBUS` on reading
  a mapped region past a truncation is the POSIX hazard** — meaning the three reverse-`mmap` scans
  (`:376-398`, `:438-462`, `:855-905`) carry that risk **on macOS and Linux today**. This reframes
  the work: it is not Windows hardening, it is an existing latent bug, and the fix (bounded chunked
  reverse reads, or reading into a stable buffer) should apply on every platform.

### H. Toolchain, CI, packaging

- **H1** — All three `quality-gate.yml` jobs are `ubuntu-latest`. No Windows or macOS execution in
  required CI.
- **H2 [confirmed, fix improved]** — `pyproject.toml` pins `[tool.mypy] platform = "darwin"` (:47)
  specifically so the `osascript` branch isn't "unreachable" on Linux runners. With
  `warn_unreachable = true`, adding literal `sys.platform` branches makes *each* platform run reject
  the others. v1's "run mypy three times" is a workaround. **Better:** push platform decisions into
  pure functions taking `platform_name: str` and an env mapping; runtime passes `sys.platform`,
  static analysis sees every branch. This also makes every backend unit-testable without mocking
  `sys.platform` — which matters for H3.
- **H3 [confirmed — NEW]** — Coverage headroom is ~1 point (measured baseline 71.0%, `fail_under =
  70`, and the threshold only ratchets up). Every new platform branch is dead code on the Ubuntu
  runner unless the pure-function design of H2 lets tests exercise it directly. This is a hard
  constraint on how notifications get written, not an afterthought.
- **H4 [corrected]** — v1 claimed a CRLF checkout breaks `ruff format --check`. Ruff's default
  `line-ending = "auto"` detects and preserves existing line endings, and the embedded linter
  imports `server.py` under universal newlines. `.gitattributes` is still worth adding as policy,
  but it is not a demonstrated gate failure and is not a prerequisite.
- **H5 [confirmed]** — `COMPATIBILITY.md` says "stdlib-only Python 3.8+"; `SKILL.md:40` and
  `pyproject.toml` say 3.11+, and the code uses `datetime.UTC` (3.11+). Straight doc bug.
- **H6 [confirmed — NEW]** — Release constraints: `version-guard.yml` fails any PR touching a
  version field and has **no label escape hatch**; the plugin *description* must stay byte-identical
  across five manifests (`AGENTS.md`); `release.yml` and `plugin-compatibility.yml` are Ubuntu-only.
  Any cross-platform claim that changes the description must change all five in one PR, without
  touching versions.

### I. Environment and packaging (Linux/WSL)

- **I1 [documented, softened]** — WSL2 `localhostForwarding` defaults on but is configurable off,
  and mirrored/NAT modes and corporate policy affect it. Probe, don't promise.
- **I2 [documented — NEW]** — Flatpak/Snap-installed harnesses: Flatpak may expose only a sandbox
  home; Snap's `home` interface excludes hidden directories like `.claude`/`.codex` outright. The
  dashboard finds nothing. Needs explicit-root support and documentation, not code heroics.
- **I3 [documented — NEW]** — systemd/headless: a *system* unit expands `~` to `/root`,
  `ProtectHome` blocks the stores, output is buffered, and `notify-send` has no user bus. Document
  a **user** unit and `ssh -L 4553:127.0.0.1:4553` for headless boxes.
- **I4 [documented — NEW]** — Defender/EDR/OneDrive hydration produce transient `PermissionError`
  and WinError 32/33 on rapid repeated opens. Today those become "harness has no sessions." Needs
  bounded retry plus a last-known-good result labeled "temporarily inaccessible."
- **I5 [corrected]** — v1 listed "Git Bash sets a different `HOME`" as a capture item. On native
  CPython, `ntpath.expanduser` ignores `HOME` and uses `USERPROFILE` [verified]. Only an MSYS-built
  Python behaves POSIX-ly. Mostly a non-issue.

### J. Adjacent, out of scope — recorded, not planned

- **J1** — Loopback is not a per-user boundary. Any other local account can `GET /api/data` and
  read every session's titles and prompts, or forge `POST /api/notify`. The Host/Origin checks
  defeat browser rebinding, not local processes. More acute on shared Linux hosts than on a
  personal Mac. A per-run bearer token in a `0600` file plus a random port would fix it. Real, but
  it is a security change, not a portability change — track separately.
- **J2** — Containers: `-p 127.0.0.1:4553:4553` cannot reach a server bound to the *container's*
  loopback. Would need `--bind`, which interacts with J1.
- **J3** — Fixed port 4553 permits one user's instance per network namespace.

---

## 4. Design decisions

**D-1 — Scan all viable roots; never pick one.** *(Revised: v1 selected the first matching
candidate at import.)* First-match regresses real users: a newly created store is invisible until
restart, an empty native directory can shadow populated legacy data, and users mid-migration lose
sessions. Instead keep an ordered **candidate list per harness**, scan every candidate that exists
on each collection pass, and dedupe by session id. An explicit env override is authoritative — and
if it is set but missing or unreadable, say so loudly rather than falling through. Claude needs two
related roots (`projects/`, `tasks/`) and Gemini needs two unrelated ones, so the unit is a
per-harness root *set*, not a single "root".

**D-2 — `--diagnose --json` is the primary deliverable.** One local command printing platform,
interpreter, every candidate considered, which existed, which were readable, and every collector
error. Users paste it into issues; it is the only realistic way to validate the Windows path table
without owning eight installs. No outbound telemetry. Keep verbose candidate data *out* of the
5-second `/api/data` response.

**D-3 — One owner per notification path.** Browser Notification API owns transcript-detected
transitions (the tab is already required for that path). Native backends own hook POSTs (no tab).
This eliminates double-firing by construction rather than by deduplication logic. `--notify` must
then state which owner it disables.

**D-4 — Platform logic lives in pure functions.** Every platform decision takes
`platform_name: str` + an env mapping and returns a value. Runtime passes `sys.platform`. This
satisfies mypy `warn_unreachable` on all platforms without the `platform = "darwin"` pin, and lets
Ubuntu CI execute the Windows branches — which is what keeps the coverage ratchet (H3) satisfiable.

**D-5 — Keep `notify_mac` as a thin alias.** Tests patch it by name (`test_server.py:48` and
several others). Renaming to `notify_desktop` without a compatibility wrapper churns the suite for
nothing.

**D-6 — Don't gate the whole effort on owning a Windows box.** *(Revised: v1's empirical checklist
was an open-ended external dependency.)* Ship with legacy paths always in the candidate list,
documented explicit overrides for every harness, and only those Windows defaults confirmed from
official docs or upstream source. Unconfirmed harnesses are marked "override required" rather than
guessed at. Synthetic fixture trees under the real `%TEMP%` on `windows-latest` give genuine
coverage of the I/O paths without any harness installed.

---

## 5. Phased plan

Phase 0 from v1 is gone: its exit condition was "CI is red," but `quality-gate` is a required check
that fails if any child fails (`quality-gate.yml:178`), so it was unmergeable by construction, and
it proposed tests for helpers that did not exist yet.

### Phase 1 — Mergeable CI foundation + core correctness — **DONE**
The CI and the fixes had to land together, because a Windows runner added before the SQLite fix is
just a red required check. Every item below is implemented, each with regression tests that were
confirmed to fail against the pre-fix behavior. Branch coverage rose 71.0% → 75.2%; the floor was
ratcheted to 74.

1. **Do not matrix the existing `test` job.** It is Bash-specific throughout: `\` line
   continuations (`:88`), `HAS=$(gh ...)`, `[ ... ]`, `>> "$GITHUB_OUTPUT"`, brace groups (`:100+`).
   On `windows-latest` the default shell is pwsh and all of it fails before Python runs. Three
   matrix children would also race on the same sticky PR comment and the same
   `coverage-${run_id}` artifact. Instead add a **separate `platform-tests` job** — checkout,
   setup-python, `python -m pip install`, `python -m unittest ...` — matrixed over
   ubuntu/macos/windows, and add it to the `quality-gate` aggregator's `needs`. Coverage stays
   Ubuntu-only so the ratchet stays meaningful. Use `python`, not `python3`.
2. SQLite URI builder with its own test matrix (`%`, `?`, `#`, space, leading `//`, drive, UNC),
   applied at `:1743`, `:1950`, `:2070`. **No `immutable=1` generalization** (B2).
3. `glob.escape()` on literal roots at all ~11 sites (A5) + deterministic sort where a "newest
   wins" tie is possible.
4. `age()`/`is_fresh()` rejecting implausibly future timestamps (E2) — see the correction noted
   under E2; the originally planned clamp would have been a no-op.
5. `encoding="utf-8"` + `ValueError` handling at `:1025`, `:1074` (E1).
6. `diag()`, a diagnostic writer that cannot raise (D7).
7. `os.path.basename` instead of `rsplit("/")` at `:286` (F2).
8. Guarded `sqlite3` import; the four DB-backed harnesses report undiscovered rather than
   present-but-empty, and startup says why (B3).
9. `COMPATIBILITY.md` 3.8 → 3.11 (H5); `.gitattributes` as policy.

*Item 2 shipped with the runner because the Windows SQLite call sites would otherwise have failed
`test_antigravity_steps_supply_rate_action_and_turn_progress`,
`test_opencode_show_all_returns_every_session`, `test_cursor_sessions_discovered_with_title`, and
`test_goose_sessions_from_shared_db` on the very job being added.*

**Exit:** `platform-tests` green on all three OSes and required. *Pending first CI run on the PR —
the Windows and macOS runners have not yet executed this suite.*

### Phase 2 — Resolver + diagnostics — **DONE**
10. **Done.** Per-harness candidate sets and pure-function resolution (D-1, D-4). Scan-all
    de-duplication was *claimed* here before it existed: the collectors that append per store
    (OpenCode, Goose) emitted the same session twice when a migration left it in two places. Now
    collapsed by `(harness, sid)` in `collect()`, keeping the freshest copy.
11. **Done.** Verified env overrides: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `COPILOT_HOME`,
    `GEMINI_CLI_HOME` (which names a parent — `.gemini` is appended). **`GOOSE_PATH_ROOT` is not
    implemented**; an earlier revision of this section listed it as landed, which was wrong. Its
    semantics are not documented upstream, and D-6 says not to guess at an override that would
    break a working setup. `SKILL.md` continues to state it is unsupported.
12. **Done.** Confirmed Windows/XDG defaults only; everything else "override required."
13. **Done.** `--diagnose --json` (D-2). It now also reports store open/query failures the
    collectors swallow — without those, a corrupt database read as a healthy store with no
    sessions, which is the exact confusion the command exists to remove.
14. **Done.** Migration tests proving current macOS paths still resolve first-class.

**Exit:** every harness present on a box is discovered on all three OSes, and when it isn't, one
command says why.

### Phase 3 — Live-file safety — **DONE for 15/18, scoped down for 16, deferred for 17**
15. **Done.** `reverse_lines()` replaces the three reverse-`mmap` scans with bounded chunked reads
    on every platform — a latent POSIX `SIGBUS` fix (G2), not Windows-only. Measured on a 38 MB
    transcript with the match at the very start (worst case): title lookup 16 ms → 20 ms, turn
    context 149 ms → 154 ms. A naive port cost 44 ms; filtering whole chunks before splitting them
    into lines recovers most of the gap, because the per-line scan rather than the I/O dominates.
    Chunk size is irrelevant between 64 KiB and 4 MiB.
16. **Scoped down to the reporting half, deliberately.** The valuable part — distinguishing
    "no store here" from "store present but unreadable" — already exists in `--diagnose` from
    Phase 2 and is now pinned by a test. The *retry* half is dropped: the dashboard already
    re-reads every store every 5 seconds, so an in-request retry loop would duplicate the refresh
    cycle while blocking the response thread. A transient Defender or OneDrive lock self-heals on
    the next poll, and `--diagnose` explains it if it does not.
17. **Deferred, not dropped.** A size/WAL-delta activity signal would replace mtime as the
    freshness source so NTFS write-time lag cannot read as Idle (E3). The premise is documented by
    Microsoft but *unverified here*: whether it bites depends on how often each harness flushes and
    closes its handle. Reshaping state detection for all eight collectors on an unconfirmed premise
    is exactly what design decision D-6 says not to do. Revisit with evidence — a Windows user
    reporting a session stuck on Idle while visibly generating, or `--diagnose` output showing a
    growing store with a stale mtime.
18. **Done.** `FILE_SHARE_DELETE` limitation documented plainly in `SKILL.md` rather than papered
    over: Python cannot request that share mode, so reads are short and bounded but the window in
    which Cargento could make a harness's own rotation fail is small, not zero. The chunked reader
    shortens it; only native calls could close it.

### Phase 4 — Lifecycle, launcher, docs — **DONE**
19. **Done.** `SO_EXCLUSIVEADDRUSE` plus `allow_reuse_address = False` on Windows, since not asking
    to share a port is not the same as refusing to. `bind_error_message()` distinguishes
    EADDRINUSE/EACCES and their Windows codes (10048, and 10013 — which is what an in-use port
    reports *once* SO_EXCLUSIVEADDRUSE is set).
20. **Done.** POSIX/PowerShell/cmd forms for start, background, stop, and open;
    `python3 -m webbrowser` instead of `open`/`xdg-open`; `notify_hook.py` replaces the curl
    one-liner.
21. **Partly done, deliberately.** Host parsing fixed (bracketed authority, case folding, numeric
    port validation). Did **not** bind both loopbacks: that needs two listeners and two threads,
    with ambiguous behavior when one binds and the other does not. Instead the banner and every
    doc now say `127.0.0.1`, which removes the `localhost` → `::1` ambiguity outright.
22. **Done.** `SKILL.md` and `COMPATIBILITY.md` rewritten; `COMPATIBILITY.md` carries the per-OS
    matrix. No manifest descriptions changed, so no five-way sync was needed, and no version
    fields were touched.
23. **Done.** systemd user unit, `ssh -L`, Flatpak/Snap, and Windows long-path notes.

**Adversarial review (Codex) found four more, all fixed.** The serious one: `notify_hook.py` built
its opener with `urllib.request.build_opener()`, which honours `http_proxy`/`HTTP_PROXY` — routine
in corporate environments. A POST to `127.0.0.1` was handed to the proxy instead, carrying prompts
and session ids off the machine and defeating the loopback check completely. Reproduced, then fixed
with `ProxyHandler({})` and a regression test. Also: `http.client.HTTPException` is not an `OSError`
and escaped the handler; `normalize_host` validated the port only in the bracketed branch, so
`localhost:evil.example` reduced to `localhost`; and a failed `SO_EXCLUSIVEADDRUSE` was silently
suppressed, dropping the guarantee without saying so.

Two defects were caught before the review, by probing the new code directly: the loopback check used
`str.startswith`, which accepts `http://localhost.evil.com`, and `normalize_host` ignored everything
after `]`, so `[::1]evil.example` passed as loopback.

### Phase 5 — Browser notifications — **DONE**
24. **Done.** Notification API in `PAGE`, owning transcript transitions only (D-3). `/api/data`
    carries `native_notify`, the name of the server's OS backend, and the page raises its own
    notification only when that is empty — so macOS keeps its `osascript` popups unchanged, Linux
    and Windows gain notifications immediately, and nothing double-fires. `native_notifier()` is
    pure in `platform_name` (D-4), so both branches run on every CI runner. Permission affordance in
    the header: an "Enable notifications" button when permission is unset, a "notifications blocked"
    note when the browser has refused, nothing once granted or when the server owns delivery. Node
    DOM stubs gained a `Notification` recorder.

**Found while verifying in a real browser:** loading the dashboard returned **403**. Chrome labels
any navigation whose initiator was another origin `Sec-Fetch-Site: cross-site` — including a user
clicking a link to the dashboard — and `_local_ok()` rejected all of them. Pre-existing, unrelated
to notifications, and invisible to `curl` (which sends no Sec-Fetch headers) and to the Node page
tests (no HTTP layer). Top-level document navigations are now served: the initiating page cannot
read a cross-origin document, and the Host check still blocks DNS rebinding. Cross-site `fetch`,
XHR, iframes, subresources, and *all* POSTs stay blocked — a cross-site form submission is also a
"navigation", so POST never takes the relaxed path.

### Phase 6 — Native Linux/Windows/WSL notifications (experimental) — **L-XL, 1-2 weeks**
25. `notify-send` / `wsl-notify-send.exe` / PowerShell toast backends behind `--notify`, argv-only,
    XML-escaped (C5), each a pure selector function (D-4) so Ubuntu CI can cover them (H3).
    Labeled experimental; macOS `osascript` behavior regression-tested unchanged.

**Ordering note:** one reviewer argued for cutting Phase 6 from the first cross-platform release
entirely. Rejected — "seamless" is the stated goal. Accepted in sequencing: Phase 5 ships the
portable path first, and Phase 6 is explicitly experimental so the release does not hinge on
PowerShell AppID behavior.

**Release gate:** require the `platform-tests` matrix green on `main` before tagging. `release.yml`
stays Ubuntu-only; add the platform job as a dependency.

---

## 5b. Testing strategy

Three layers, in increasing cost:

- **Pure-function tests, everywhere.** `resolve_store_roots`, `sqlite_ro_uri`, `normalize_host`,
  `native_notifier`, `reuse_address_allowed`, `encoded_home_prefix`, `age`/`newest_plausible` all
  take the platform (or its inputs) as an argument, so the Linux runner checks the Windows and
  macOS branches too. This is design decision D-4, and it is also what keeps the coverage ratchet
  satisfiable as platform branches multiply.
- **Behavioural contracts, run natively on each runner.** A realistic store fixture for all nine
  stores, each asserted to: discover when present; read working when fresh and idle when stale;
  stay undiscovered *without an error* when absent; refuse to read working from a future-dated
  store; survive a corrupt store without taking the other harnesses down; and collapse to one row
  when the same session exists in two candidate roots. Every store is additionally built under ten
  hostile path components legal on all three platforms — glob metacharacters, `%`, non-ASCII,
  spaces, `#`, quotes. This layer exercises real NTFS, APFS and ext4 semantics; 218 tests now run
  on each of the three runners.
- **Documentation-matches-code.** The documented store paths, relocation variables, Python floor
  and loopback address are asserted against the implementation. Doc drift was found twice by
  review; this makes it a test failure instead.

**Mutation testing is how the suite is judged, not the test count.** A harness copies the repo,
breaks one behaviour, and runs the targeted test: 17/17 current mutations are caught. Four were
missed on the first run and exposed two genuinely weak assertions — de-duplication was tested as a
function but never as wired into `collect()`, and a discovery assertion could not fail. Any new
contract should be mutation-checked the same way before it is trusted.

**Still not covered, and honestly so:** nothing validates the *Windows store locations* against a
real Windows install, because that needs the eight harnesses actually installed there. The
resolver's Windows output is asserted as strings; whether those strings are where the tools really
write is what `--diagnose` output from a user settles (§6).

## 6. What still needs a real machine

Reduced from v1's blocking checklist to a *quality* gate, not a *ship* gate (D-6). Highest value
first:

1. One Claude `~/.claude/projects/` directory name on native Windows, plus the working directory it
   came from — the only way to settle F1.
2. Whether Codex writes `\` in `cwd`/`agent_path` on Windows (F2's scope).
3. Goose and OpenCode Windows store paths, confirmed against upstream source rather than blog posts.
4. Whether `cursor-agent` and Antigravity CLI ship native Windows builds at all. If not, the matrix
   says 6 harnesses on Windows, not 8 — a documentation outcome, not a failure.

`--diagnose` output from any Windows user substitutes for all four.

---

## 6b. Measured cost of the cross-platform work

Full `collect()` on a real tree (19 sessions in the default window, 2,546 with `?all=1`),
median of 9 warm runs, against `main`:

| view | main | this branch | delta |
|---|---|---|---|
| default window | 139.8 ms | 146.3 ms | +4.7% |
| `?all=1` | 159.7 ms | 173.7 ms | +8.8% |

Accepted. The cost buys multi-candidate discovery, clock-skew rejection, and de-duplication, and
the dashboard memoizes each collection for 2.5 s behind a 5 s refresh — so this is ~7 ms per
refresh on the default view. An earlier revision measured +8.5%/+12.8%; halving the freshness
traversal (see Phase 4's review notes) recovered most of it.

The reverse reader is separately *faster* than what it replaced on the case that matters: a 64 MB
single-record transcript went from 0.876 s to 0.047 s once fragment accumulation stopped being
quadratic.

## 7. Risks

- **R1 (highest)** — Silent false-negative discovery. Mitigated by scan-all candidates (D-1),
  `--diagnose` (D-2), and glob escaping (A5).
- **R2** — Coverage ratchet has ~1 point of headroom (H3). If platform branches aren't written as
  pure functions (D-4), Phase 6 cannot merge without a `coverage-exception` label.
- **R3** — Native toast delivery is not guaranteeable (C2). Accepted; Phase 5 is the reliable path.
- **R4** — Phase 3 touches the hottest read paths. Needs a before/after timing check on a large
  transcript; a chunked reverse scan can be slower than `mmap` if written naively.
- **R5** — Unconfirmed Windows paths (§6). Mitigated by candidate lists making each addition a
  one-line change.

---

## 8. Review disposition

Three adversarial Codex passes (code-correctness, platform-expertise, plan-feasibility).

**Rejected as wrong — removed from the plan (3):** F3 (`os.path` is `ntpath` on Windows; a
split-on-both helper would regress POSIX) · F4 (`ntpath.commonpath` already case-folds — disproved
locally before the review returned, and confirmed by it) · H4 (ruff `line-ending = "auto"` handles
CRLF).

**Materially corrected (8):** B2 (`immutable=1` would introduce a correctness bug — reversed) ·
G2 (`SIGBUS` hazard is POSIX, not Windows — inverted, and it makes this an existing macOS bug) ·
E1 (mojibake, not a dead collector) · D1 (needs `SO_EXCLUSIVEADDRUSE`, not just
`allow_reuse_address=False`) · D4 (`python3` isn't portable either) · D7 (redirected stdout, not
cp1252 consoles) · A2 (`GEMINI_CLI_HOME`, not `GEMINI_DATA_DIR`) · A3 (Copilot XDG is stale).

**Accepted as new, after verification (12):** A5 glob metacharacters **[reproduced]** · E2 future
timestamps **[reproduced]** · D8 Host-header parsing **[reproduced]** · B3 optional `sqlite3` ·
E3 NTFS mtime lag · E4 `st_birthtime` is 3.12+ on Windows · E5 coarse timestamps · D5/D6 shell
portability · I2/I3/I4 packaging and environment · C4 duplicate notification ownership ·
H3/H6 gate constraints.

**Structural changes accepted:** v1's Phase 0 deleted as unmergeable · matrix the *unittest* job,
never the coverage job · scan-all-candidates instead of first-match · pure platform functions
instead of `mypy --platform` runs · `--diagnose` instead of a blocking capture checklist.

**Rejected on scope:** cutting native notifications from the release (sequenced last instead) ·
bearer-token auth and `--bind` (real, but security/deployment work — recorded in §J).
