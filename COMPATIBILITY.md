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

- The dashboard server is stdlib-only Python 3.8+; it runs identically regardless of which harness launched it.
- Popup notifications use macOS `osascript`; on Linux the dashboard works but popups silently no-op, and completed-task ages/estimates degrade (no file birthtime).
- Needs-input detection exists only for Claude Code sessions — other harnesses expose no equivalent signal in their local stores.

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
