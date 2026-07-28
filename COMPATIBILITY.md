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
The floor is restated in six other places across four files, which must all move together:
`README.md`, `CONTRIBUTING.md` (twice, in the prerequisites and in the `server.py` design
constraints), `cargento/skills/cargento/SKILL.md`, and `pyproject.toml` (`[tool.ruff] target-version`
and `[tool.mypy] python_version`). The documentation-matches-code test guards the `SKILL.md` copy.
The rest are on you.

| Capability | macOS | Linux | Windows | WSL2 |
|---|---|---|---|---|
| Harness discovery, dashboard, `/api/data` | yes | yes | yes | yes (Linux-side stores) |
| Turn ETA, token rate | yes | yes | yes | yes |
| Task age from file birthtime | yes | falls back to mtime | Python 3.12+ only | falls back to mtime |
| Needs-input popup, browser (tab open) | not needed | yes | yes | yes (host browser) |
| Needs-input popup, native (no tab) | yes (`osascript`) | not yet | not yet | not yet |

Exactly one layer delivers a given popup: the server where it has a native backend, the page otherwise. `/api/data` reports which as `native_notify`.

Notification delivery is best-effort by design, on every platform. The exit criterion is graceful degradation plus a reported delivery status, not a guarantee: browser notifications need the user's permission and an open tab, `notify-send` needs a graphical user D-Bus session, and a Windows toast needs an interactive session (and, from WSL, enabled interop). A backend that cannot deliver must no-op quietly, never raise.

Other notes:

- Needs-input detection exists only for Claude Code sessions. Other harnesses expose no equivalent signal in their local stores.
- Spacedock workflow detection likewise exists only for Claude Code sessions. It rests on an `agentSetting` in the first transcript records and on the first officer's boot output, both written by the Claude launch path. The Codex and Pi hosts record neither in a form a passive reader can use, so their sessions render exactly as before. The collector is shaped so a host can be added without touching the parsers.
- Store locations resolve per platform, and `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME`, and `COPILOT_HOME` are honored. Run `server.py --diagnose` to see every path searched and what was found there.
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

<!-- docs-synced-through: cadb707 (2026-07-28) -->
