# Codex, Claude Code, Antigravity, and Gemini CLI compatibility

The repository keeps one shared skill implementation for all clients. Platform-native wrappers are retained only when the platform owns the behavior.

| Surface | Codex | Claude Code | Antigravity / AGY | Gemini CLI | Repository contract |
|---|---|---|---|---|---|
| Package marker | `.codex-plugin/plugin.json` | `.claude-plugin/plugin.json` | `plugin.json` | `../cargento-gemini/gemini-extension.json` | Each runtime receives its native root/manifest shape. Gemini's is a separate root: see Hooks below |
| Skills | `/skills` or `$cargento` | `/cargento:cargento` | Bundled plugin skills | **Not bundled** | Shared `skills/cargento/SKILL.md`. The Gemini extension root carries hooks only, so Gemini users launch the dashboard directly rather than through a skill |
| Skill UI metadata | `agents/openai.yaml` | Ignored | Ignored | Ignored | Optional Codex presentation data beside the shared skill |
| MCP | Not registered by the plugin; the user registers it themselves, and [`HOW_TO_USE.md`](HOW_TO_USE.md#register-the-mcp-server-in-codex) owns that procedure. Gate and hold measured attended on codex-cli 0.146.1 (`mcp-ask-gate-0.146.1`), and a round trip ran end to end there too, answered at index 1 (`ask-roundtrip-0.146.1`). A Codex ask arrives with no session id, so its card is answerable but does not attach to a session row | Registered: `mcpServers` in `.claude-plugin/plugin.json`. Gate and hold measured attended on 2.1.239 (`mcp-ask-gate-2.1.239`), and the plugin-declared path is measured too: loaded with `--plugin-dir`, it produces the tool `mcp__plugin_cargento_cargento__ask_operator`, and one round trip ran end to end through it, answered at index 0 (`ask-roundtrip-2.1.239`) | Not registered. Antigravity's MCP path takes a `serverUrl` only and cannot express a stdio server without a validator change | Not registered. The Gemini extension root carries hooks only, so there is no manifest surface for it | One stdio server, `cargento/skills/cargento/mcp_server.py`, serving one tool, `ask_operator`. Session data still comes from reading local stores; the server exists so a session can ask the reader a question and wait. Two kinds of capture, and they answer different questions: the gate and the hold in `docs/captures/{claude,codex}/mcp-ask-gate-*.jsonl`, the round trip and the decline paths in `docs/captures/{claude,codex}/ask-roundtrip-*.jsonl`. [`SECURITY.md`](SECURITY.md) owns the contract and the standing permission it needs, [`docs/design-ask-lane.md`](docs/design-ask-lane.md) the rejected alternatives |
| Hooks | `hooks/codex-hooks.json` | `hooks/hooks.json` | `hooks.json` | `../cargento-gemini/hooks/hooks.json` | Bundled per harness, each in the path that harness reads, each in that harness's own event vocabulary. The vocabularies do not overlap enough to share a file: a foreign event name is skipped with a warning on every session. `scripts/validate_plugins.py` fails the build on a foreign name or a foreign harness argument |
| Recurring runs | Invoke the skill one pass at a time | Invoke the skill one pass at a time; a scheduler plugin can repeat it | Invoke the skill one pass at a time | Invoke the skill one pass at a time | The skill remains useful as a one-shot workflow |

## Platform-specific behavior

This file owns the Python floor. The dashboard server is stdlib-only Python 3.11+, with
`datetime.UTC` setting the floor, and it runs identically regardless of which harness launched it.
`sqlite3.Connection.blobopen` holds it there too, since the Antigravity collector uses it to read
the last 64 bytes of a generation blob without materialising a row that can run past 700 KB.
The floor is restated in seven other places across five files, which must all move together:
`README.md`, `CONTRIBUTING.md` (twice, in the prerequisites and in the dashboard implementation
constraints), `cargento/skills/cargento/SKILL.md`, and `pyproject.toml` (`[tool.ruff] target-version`
and `[tool.mypy] python_version`), plus the Python 3.11 direct-launch smoke in
`.github/workflows/quality-gate.yml`. The documentation-matches-code test guards the `SKILL.md`
copy, and the runtime-floor job exercises the shipped entry point on Python 3.11. The rest are on
you.

| Capability | macOS | Linux | Windows | WSL2 |
|---|---|---|---|---|
| Harness discovery, dashboard, `/api/data` | yes | yes | yes | yes (Linux-side stores) |
| Pi nested and flat session stores | yes | yes | yes | yes (Linux-side stores) |
| Turn ETA, token rate | yes | yes | yes | yes |
| Task age from file birthtime | yes | falls back to mtime | Python 3.12+ only | falls back to mtime |
| Needs-input popup, browser (tab open) | only where the server did not (see below) | yes | yes | yes (host browser) |
| Needs-input popup, native (no tab) | yes (`osascript`) | not yet | not yet | not yet |
| Ask-lane popup, browser (tab open) | not needed | yes | yes | yes (host browser) |
| Ask-lane popup, native (no tab) | yes (`osascript`) | not yet | not yet | not yet |
| Claude quota token read (the usage fetch) | Keychain via `security`; the first read can prompt | credential file | credential file | credential file (Linux-side home) |
| Cursor quota token read (the usage fetch) | Keychain via `security`, service `cursor-access-token` | no (see below) | no (see below) | no (see below) |

At most one layer delivers a given popup: the server where it has a native backend, the page otherwise. `/api/data` reports which as `native_notify`. The split covers an arriving `ask_operator` question as well as a needs-input transition, which is why the ask rows above read the same way. It used to say exactly one, and that is no longer true in a single case: the page stands down on macOS because the server has a native backend, but the server only raises a needs-input popup from Claude's collector, so a gate on any other harness gets none there. The board, the band and the tile all still show it. The ask lane is unaffected and stays harness-independent.

Notification delivery is best-effort by design, on every platform. The exit criterion is graceful degradation plus a reported delivery status, not a guarantee: browser notifications need the user's permission and an open tab, `notify-send` needs a graphical user D-Bus session, and a Windows toast needs an interactive session (and, from WSL, enabled interop). A backend that cannot deliver must no-op quietly, never raise.

Verified by hand: on macOS, a `--daemon` server delivers the native notification with no browser tab
open at all, since the double-fork keeps the daemon in the user's own login session rather than
moving it to a new one, which is the main reason daemon mode is worth having. That confirms `osascript`
reported success, not that a banner was visibly displayed; Focus and Do Not Disturb can still
suppress on-screen display independently of whether the process is detached. See
[`docs/design-daemon.md`](docs/design-daemon.md) for how this was verified.

### `--daemon`, `--status`, `--stop`

`--daemon` detaches so the dashboard outlives the session that started it: a double-fork on POSIX,
a detached re-spawn on Windows (there is no `fork` there). Both bind the listening socket (or, on
Windows, wait for the re-spawned child to prove it bound, over `/api/health`, matching the answering
pid against the child's own so a dashboard already on that port cannot be mistaken for it) before reporting
success, so a busy port still fails loudly on every platform instead of silently in a log nobody was
told about.

The per-port state file and log live under `~/.cargento`, one layout on every platform;
`CARGENTO_HOME` is authoritative when nonblank, the same rule the harness store relocation variables
follow. Nothing ever removes or rotates the log, so `~/.cargento` accumulates one log file per port
indefinitely. See [`SECURITY.md`](SECURITY.md) for the written-paths contract.

Other notes:

- Needs-input detection reaches two harnesses of the ten. Claude Code has three sources; Codex has one, its bundled `PermissionRequest` hook, which was measured firing in an interactive session with the approval prompt still on screen. The other eight expose no signal a passive reader can use, so the payload declares the capability per harness and the page marks those rows rather than letting their silence read as an all-clear. Two per-harness limits ride with that: a Codex gate raises no popup on macOS, because only Claude's collector calls the native notifier and the browser layer stands down where a native one exists, though it does raise one on Linux and Windows where the page owns that lane; and a Codex row can say a gate is open without saying which, because the event envelope drops the tool name at the hook. The ask lane is a different mechanism and is not detection at all, so it does not follow that line: an `ask_operator` question is raised by the session itself over MCP, which means any harness that can register the stdio server can put a question on the board no matter what its store records. Which harnesses those are is the MCP row above.
- Turn-end events reach only the four harnesses with an event adapter, Claude Code, Codex, Antigravity and Gemini CLI, each through the hooks bundled for it, so only their rows can tell a session that finished and went unread from one still waiting on a reply that never came. The other six (Pi, Copilot, OpenCode, Cursor, Goose and Droid) are read by scanning their stores, and their rows say the answer cannot be known there rather than guessing at it. No collector may infer a completion.
- Spacedock workflow detection likewise exists only for Claude Code sessions. It rests on an `agentSetting` in the first transcript records and on the first officer's boot output, both written by the Claude launch path. Codex and Pi record neither in a form a passive reader can use. Pi forks and clones remain independent rows, not subagents.
- Loop detection, the run of failed tool calls behind a long turn's explanation, is also Claude Code only. Claude is the only harness that records whether a tool call failed, so every other row reads as not measured rather than as nothing failed, and none of them ever carries the signal. `cargento/skills/cargento/SKILL.md` owns what the signal means and which record each of the other harnesses is missing.
- Pi scans the nested default store under `~/.pi/agent/sessions` and a flat custom store. `PI_CODING_AGENT_SESSION_DIR` is the authoritative direct-store override and wins over `PI_CODING_AGENT_DIR`, the global `sessionDir` setting, and the default. `PI_CODING_AGENT_DIR` relocates the configuration root, including its global `settings.json`; a relative global `sessionDir` resolves there. A separate process cannot infer a one-off Pi `--session-dir` or a project-local `.pi/settings.json`, so expose the effective store with `PI_CODING_AGENT_SESSION_DIR` when either is in use.
- Store locations resolve per platform, and `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME`, `COPILOT_HOME`, `PI_CODING_AGENT_DIR`, and `PI_CODING_AGENT_SESSION_DIR` are honored. Run `server.py --diagnose` to see every path searched and what was found there.
- WSL2's `localhostForwarding` defaults on but can be switched off, and mirrored/NAT networking modes or corporate policy can also break host-browser access to `127.0.0.1:4553`. Probe before assuming; the fallback is `ssh -L` or a browser inside WSL.
- Supported WSL topology is server and agents on the same side of the boundary. Reading a Windows-side store from inside WSL works over `/mnt/c`, but 9p latency and mtime granularity make state detection unreliable, so it is not supported.
- `sqlite3` is an optional stdlib module. On a build without it (some musl/Alpine images) OpenCode, Cursor and Goose report undiscovered. Antigravity still appears, since its discovery and state come from store mtime and CLI logs, but without a token rate or turn ETA. Copilot also still appears, because it is discovered and read from JSONL events, but its `used` figure in the usage section is absent, since that figure comes from a SQLite store.
- Quota follows discovery, for every harness. A harness that is not discovered publishes no usage entry and, if it is one of the fetched ones, is never fetched for either. Two consequences are worth knowing because neither is obvious from the quota path itself: on a build with no `sqlite3` Cursor's quota is absent even though the fetch needs no SQLite, and a freshly installed Cursor CLI with no conversation yet is undiscovered, so its quota waits on the first chat. This is deliberate. The alternative is a quota tile for a harness the machine shows no other sign of using.
- Gemini CLI stopped serving consumer accounts (Google AI Pro, Google AI Ultra and the free individual tier) on 2026-06-18, and Antigravity CLI is the successor for those users. Enterprise Gemini Code Assist licences and API-key authentication were explicitly unaffected, so on a machine using either of those the CLI still runs and still writes `~/.gemini/tmp`. This file owns that distinction; it is restated in `README.md`, `cargento/skills/cargento/SKILL.md` and `docs/design-harness-registry.md` (H-2), which must move together. Gemini and Antigravity are two harness rows. Antigravity is the current consumer one, and the Gemini row reads `~/.gemini/tmp`: historical on a consumer machine, where its sessions read as idle and need `?all=1` to appear, and live on an enterprise or API-key one, where they appear like any other harness. `GEMINI_CLI_HOME` relocates both, since Antigravity's store sits inside the Gemini home.
- Cursor's quota tile is macOS-only. The Cursor CLI keeps its session token in the macOS Keychain, and where it persists that token on Linux and Windows has not been verified, so those platforms read no credential rather than a guessed path: Cursor's sessions still appear, only its usage entry is absent. Verifying the location on either platform is what lifts this, and it needs the CLI installed there. Every other harness's usage figure is platform-independent.

## Validation

The canonical pre-PR suite is in [AGENTS.md](AGENTS.md#pre-pr-checks). This file owns only the
native per-runtime validators. They run locally, because the CLIs are not available on stock CI
runners:

```bash
claude plugin validate ./cargento --strict
agy plugin validate ./cargento
```

<!-- docs-synced-through: 1d36dd9 (2026-08-23) -->
