# Codex, Claude Code, Antigravity, and Gemini CLI compatibility

The repository keeps one shared skill implementation for all clients. Platform-native wrappers are retained only when the platform owns the behavior.

| Surface | Codex | Claude Code | Antigravity / AGY | Gemini CLI | Repository contract |
|---|---|---|---|---|---|
| Package marker | `.codex-plugin/plugin.json` | `.claude-plugin/plugin.json` | `plugin.json` | `gemini-extension.json` | Each runtime receives its native root/manifest shape |
| Skills | `/skills` or `$cargento` | `/cargento:cargento` | Bundled plugin skills | Bundled extension skills | Shared `skills/cargento/SKILL.md` |
| Skill UI metadata | `agents/openai.yaml` | Ignored | Ignored | Ignored | Optional Codex presentation data beside the shared skill |
| MCP | Not used | Not used | Not used | Not used | Cargento reads local session stores directly; no MCP server is bundled |
| Hooks | None | None | None | None | The dashboard's optional Claude `Notification` hook is user-installed, never bundled (see SKILL.md) |
| Recurring runs | Invoke the skill one pass at a time | `/loop` may schedule repeated passes | Invoke the skill one pass at a time | Invoke the skill one pass at a time | The skill remains useful as a one-shot workflow |

## Platform-specific behavior

The dashboard server is stdlib-only Python 3.11+ (it uses `datetime.UTC`); it runs identically regardless of which harness launched it. The floor is also declared in `SKILL.md` and `pyproject.toml` — keep all three in lockstep.

| Capability | macOS | Linux | Windows | WSL2 |
|---|---|---|---|---|
| Harness discovery, dashboard, `/api/data` | yes | yes | yes | yes (Linux-side stores) |
| Turn ETA, token rate | yes | yes | yes | yes |
| Task age from file birthtime | yes | falls back to mtime | Python 3.12+ only | falls back to mtime |
| Needs-input popup, browser (tab open) | not needed | yes | yes | yes (host browser) |
| Needs-input popup, native (no tab) | yes (`osascript`) | not yet | not yet | not yet |

Exactly one layer delivers a given popup: the server where it has a native backend, the page otherwise. `/api/data` reports which as `native_notify`.

Other notes:

- Needs-input detection exists only for Claude Code sessions — other harnesses expose no equivalent signal in their local stores.
- Store locations resolve per platform, and `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME`, and `COPILOT_HOME` are honored. Run `server.py --diagnose` to see every path searched and what was found there.
- Supported WSL topology is server and agents on the same side of the boundary. Reading a Windows-side store from inside WSL works over `/mnt/c` but 9p latency and mtime granularity make state detection unreliable, so it is not supported.
- `sqlite3` is an optional stdlib module. On a build without it (some musl/Alpine images) OpenCode, Cursor and Goose report undiscovered; Antigravity still appears, since its discovery and state come from store mtime and CLI logs, but without a token rate or turn ETA.

## Validation

Run the repository contract checker plus the available native validators before opening a PR:

```bash
python3 -m pip install -r requirements-validation.txt
python3 scripts/validate_plugins.py
python3 -m unittest scripts/tests/test_validate_plugins.py
python3 -m unittest scripts/tests/test_bump_version.py
python3 -m unittest cargento/skills/cargento/tests/test_server.py
claude plugin validate . --strict
claude plugin validate ./cargento --strict
agy plugin validate ./cargento
```
