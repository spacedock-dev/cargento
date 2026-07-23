@AGENTS.md

# Claude Code-specific notes

The shared repository instructions are imported above. The following notes apply only to Claude Code surfaces.

- The Claude manifest lives in `cargento/.claude-plugin/plugin.json`.
- Claude-only agent definitions may live in `cargento/agents/`, and Claude-only lifecycle hooks may live in `cargento/hooks/`, if ever added.
- `${CLAUDE_PLUGIN_ROOT}` is safe in Claude hook commands. Shared skill bodies must use portable resource resolution because Codex does not guarantee that variable there.
- Validate the marketplace and the plugin with `claude plugin validate <path> --strict`.
- Test a plugin session with `claude --plugin-dir ./cargento`.
