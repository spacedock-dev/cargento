# Codex, Claude Code, Antigravity, and Gemini CLI compatibility

The repository keeps one shared skill implementation for all clients. Platform-native wrappers are retained only when the platform owns the behavior.

| Surface | Codex | Claude Code | Antigravity / AGY | Gemini CLI | Repository contract |
|---|---|---|---|---|---|
| Package marker | `.codex-plugin/plugin.json` | `.claude-plugin/plugin.json` | `plugin.json` | `gemini-extension.json` | Each runtime receives its native root/manifest shape |
| Skills | `/skills` or `$cargento` | `/cargento:cargento` | Bundled plugin skills | Bundled extension skills | Shared `skills/cargento/SKILL.md` |
| Skill UI metadata | `agents/openai.yaml` | Ignored | Ignored | Ignored | Optional Codex presentation data beside the shared skill |
| MCP | Not used | Not used | Not used | Not used | Cargento reads local session stores directly; no MCP server is bundled |
| Hooks | None | None | None | None | The dashboard's optional Claude `Notification` and `SessionEnd` hooks are user-installed, never bundled (see [SKILL.md](cargento/skills/cargento/SKILL.md#notifications)) |
| Recurring runs | Invoke the skill one pass at a time | Invoke the skill one pass at a time; a scheduler plugin can repeat it | Invoke the skill one pass at a time | Invoke the skill one pass at a time | The skill remains useful as a one-shot workflow |

## Platform-specific behavior

This file owns the Python floor. The dashboard server is stdlib-only Python 3.11+, with
`datetime.UTC` setting the floor, and it runs identically regardless of which harness launched it.
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
| Needs-input popup, browser (tab open) | not needed | yes | yes | yes (host browser) |
| Needs-input popup, native (no tab) | yes (`osascript`) | not yet | not yet | not yet |

Exactly one layer delivers a given popup: the server where it has a native backend, the page otherwise. `/api/data` reports which as `native_notify`.

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

- Needs-input detection exists only for Claude Code sessions. Other harnesses expose no equivalent signal in their local stores.
- Spacedock workflow detection likewise exists only for Claude Code sessions. It rests on an `agentSetting` in the first transcript records and on the first officer's boot output, both written by the Claude launch path. Codex and Pi record neither in a form a passive reader can use. Pi forks and clones remain independent rows, not subagents.
- Pi scans the nested default store under `~/.pi/agent/sessions` and a flat custom store. `PI_CODING_AGENT_SESSION_DIR` is the authoritative direct-store override and wins over `PI_CODING_AGENT_DIR`, the global `sessionDir` setting, and the default. `PI_CODING_AGENT_DIR` relocates the configuration root, including its global `settings.json`; a relative global `sessionDir` resolves there. A separate process cannot infer a one-off Pi `--session-dir` or a project-local `.pi/settings.json`, so expose the effective store with `PI_CODING_AGENT_SESSION_DIR` when either is in use.
- Store locations resolve per platform, and `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME`, `COPILOT_HOME`, `PI_CODING_AGENT_DIR`, and `PI_CODING_AGENT_SESSION_DIR` are honored. Run `server.py --diagnose` to see every path searched and what was found there.
- WSL2's `localhostForwarding` defaults on but can be switched off, and mirrored/NAT networking modes or corporate policy can also break host-browser access to `127.0.0.1:4553`. Probe before assuming; the fallback is `ssh -L` or a browser inside WSL.
- Supported WSL topology is server and agents on the same side of the boundary. Reading a Windows-side store from inside WSL works over `/mnt/c`, but 9p latency and mtime granularity make state detection unreliable, so it is not supported.
- `sqlite3` is an optional stdlib module. On a build without it (some musl/Alpine images) OpenCode, Cursor and Goose report undiscovered. Antigravity still appears, since its discovery and state come from store mtime and CLI logs, but without a token rate or turn ETA.

## Validation

The canonical pre-PR suite is in [AGENTS.md](AGENTS.md#pre-pr-checks). This file owns only the
native per-runtime validators. They run locally, because the CLIs are not available on stock CI
runners:

```bash
claude plugin validate ./cargento --strict
agy plugin validate ./cargento
```

<!-- docs-synced-through: b6b4e66 (2026-07-30) -->
