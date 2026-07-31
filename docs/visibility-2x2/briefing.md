# Briefing: what a coding-agent user can see today

Factual substrate for scoring "how hard is it for a normal user to get quick access to
this information today". Neutral by intent: it records capability, not conclusions. Do
not treat anything here as an argument for a high or low score.

Where this briefing does not cover an item, reason from first principles about what a
user would actually do, and mark your confidence `low`.

## The user being modelled

A working developer running roughly 3 to 12 concurrent coding-agent sessions, in
terminal tabs or panes, across more than one harness. Competent with a shell. Not
running any custom monitoring of their own. "Quick access" means under about 30 seconds
of deliberate effort, starting from the moment they want to know.

## Per harness, what the user sees natively

**Claude Code.** A configurable status line. A `/usage` command reporting quota. A
`/context` command. Harness-generated session titles. Third-party status-line tools are
common; one of them, Barista, caches 5-hour and weekly quota percentages plus reset
times locally, so a user running it sees quota without asking. Claude Desktop displays
per-session indicator dots. Lifecycle hooks exist (`Notification`, `SessionEnd`) but a
normal user has not wired them up.

**Codex.** A native usage line in its TUI.

**Pi, Gemini CLI / Antigravity, GitHub Copilot CLI, OpenCode, Cursor CLI, Goose,
Factory Droid.** Each shows its own current session in its own terminal: the live
output, the current prompt, whatever it is printing. Quota display varies and is absent
on most. None is documented here as surfacing anything about *other* sessions.

## Cross-cutting facts

These hold for every harness in the list, and are the highest-confidence claims here:

- A session's own state is fully visible in its own terminal. The prompt it is blocked
  on, the file it is editing, the error it hit: all on screen, if you are looking at
  that pane.
- No harness displays anything about sessions other than the one in front of you. There
  is no native cross-session or cross-harness view.
- No harness estimates how long the current turn will take.
- No harness distinguishes a wedged agent from a productive one. Both keep emitting.
- No harness delivers a notification off the machine (no phone, no push).
- Quota, where shown at all, is shown as a current figure. No harness projects a burn
  rate forward or attributes consumption to a particular session.
- No harness retains queryable history across sessions about what the user did or how
  often they were interrupted.

## What a resourceful user could do unaided

Relevant because the axis asks what is *reachable*, not what is convenient. Weigh these
honestly: some are genuinely quick, others only sound quick.

- Cycle terminal tabs or panes by hand and read each one.
- `tmux list-panes` / `tmux list-windows` to enumerate panes, or `capture-pane` to dump
  a pane's visible content.
- `git status` inside a repository, and `gh pr list` for pull-request state.
- `ps` to see whether a process is alive.
- Read a harness's own session files on disk directly, if they know the paths.
- Write a small script. Assume a competent developer *could*, and judge whether a normal
  user actually *would* before scoring on that basis.

## What Cargento already derives

Listed only so you understand what an item is referring to, not as evidence that the
information is easy or hard for a user to get. Cargento is not something the user has.

Cross-harness session discovery; a live state badge (needs-input for Claude only,
working, idle); current activity; running subagents; a current-turn elapsed and ETA
estimate; a warning when a request runs 15 minutes or longer; tracked task rows; recent
token output rate; a stale flag at 2 hours idle; Spacedock workflow stage strips;
desktop notification when a Claude session blocks on the human.
