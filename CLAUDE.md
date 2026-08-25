@AGENTS.md

# Claude Code-specific notes

The shared repository instructions are imported above. The following notes apply only to Claude Code surfaces.

- The Claude manifest lives in `cargento/.claude-plugin/plugin.json`.
- Claude-only agent definitions may live in `cargento/agents/`, and Claude-only lifecycle hooks may live in `cargento/hooks/`, if ever added.
- `${CLAUDE_PLUGIN_ROOT}` is safe in Claude hook commands. Shared skill bodies must use portable resource resolution because Codex does not guarantee that variable there.
- Validate the marketplace and the plugin with `claude plugin validate <path> --strict`.
- Test a plugin session with `claude --plugin-dir ./cargento`.
- Claude Code discovers the canonical repository development skills directly from `.claude/skills/`.
  They are **not** part of the shipped plugin; the portability rules in `AGENTS.md` apply to
  `cargento/skills/` only. The shared instructions own their Codex aliases and pre-PR use.

## Running several agents at once

`AGENTS.md`'s **Parallel Work** section owns the hazards. These are the Claude Code mechanics for
hitting them.

- `isolation: "worktree"` on the `Agent` and `Workflow` tools is how a subagent gets its own
  checkout. Worktrees land under `.claude/worktrees/`, and `git worktree list` from the repository
  root is the fastest way to see who else is working.
- A worktree arrives on a generated `worktree-*` branch. An agent told to use a real branch name will
  usually rename in place, which leaves the generated branch behind. Delete those after removing the
  worktree, or `gh pr merge --delete-branch` fails on the branch a worktree still holds.
- **Subagents share the session scratchpad.** It is one directory for the session, not one per
  worktree, so two agents writing a commit message to the same path will overwrite each other.
  Namespace scratch files per branch, or write them inside the worktree.
- Give every parallel builder the contention list from `AGENTS.md` in its prompt. An agent that has
  not been told will report a loopback-port failure as a regression, and it reads convincingly.
- Prefer `Monitor` over polling for CI and for sibling completion, and check the event you act on is
  not from a run that predates a branch update. A monitor armed before an update will happily report
  the old run's green.
