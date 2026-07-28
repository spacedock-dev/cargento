---
name: cargento
description: Open Cargento, a local agent-cartography dashboard for Claude Code, Codex, Gemini or Antigravity, Copilot, OpenCode, Cursor, Goose, and Droid sessions, with subagents, task progress, token rate, ETAs, and Claude input-wait notifications. Use for “open cargento” or “monitor agent progress”.
license: Apache-2.0
---

# Cargento

Cargento is an agnostic agent cartography and visualization tool: a local web dashboard mapping live coding-agent activity across **eight harnesses** on this machine — Claude Code, Codex, Gemini CLI / Antigravity CLI, GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, Factory Droid — each row badged with its harness. A "Discovered harnesses" strip at the top shows all supported harnesses; ones with local session data are green/enabled, others gray/disabled. A harness's sessions only appear if its data is discovered. Transcript-backed sessions appear even if they never called TaskCreate; Claude task files may also surface a task-only session when its transcript is unavailable. Per session: a live state badge, what it's doing right now, running subagents (named pills), a current-turn elapsed/ETA estimate with progress bar, a ⚠️ warning (with tooltip) when a request runs or is estimated ≥15 min, one row per tracked task, and the recent token output rate. Fires desktop notifications when a Claude session is blocked waiting on the human.

Store locations are resolved per platform, and the documented relocation variables are honored: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME` (the CLI creates `.gemini` inside it), and `COPILOT_HOME`. When one is set it is authoritative — no fallback to the default location. Run `--diagnose` to see every path searched.

Data sources (read-only, no external calls; all parsing is defensive — a broken harness store is skipped, never fatal):
- `~/.claude/projects/*/<session>.jsonl` — Claude transcript tails: session discovery, titles, token usage, pending AskUserQuestion detection
- Claude subagents, two generations: modern harnesses write each subagent as a top-level `~/.claude/projects/*/<uuid>.jsonl` whose records carry `agentName` + `teamName: "session-<parent prefix>"` — these fold into the parent session (named pill, freshness, output rate) and never appear as standalone sessions; legacy `<session-uuid>/subagents/agent-*.jsonl` + `.meta.json` files are still recognized (fresh mtime = running), including the `subagents/workflows/<run-id>/` directory a workflow fan-out nests its agents in. Agent writes count as parent activity in their own right, so a session parked on a long background workflow reads Working rather than Idle
- Spacedock workflows: a Claude session launched by Spacedock carries an `agentSetting` of `spacedock:first-officer` or `spacedock:ensign` in its first transcript records, which is how the role badge appears. A first officer also records its `spacedock status --boot` output — counted only when it arrives as command output, never as ordinary conversation text — which names each workflow directory and each entity-state directory absolutely. The ordered stage list comes from the workflow `README.md` frontmatter, and each entity's current stage from the `status` in its own state-file frontmatter; boot's `dispatchable` list is only a snapshot of what was ready to move at boot, so it fills in behind the state directory rather than standing in for it. Those two kinds of frontmatter are the only project files Cargento reads — see the repository's SECURITY.md for the contract, and `--no-spacedock` to disable it
- `~/.claude/tasks/<session-id>/N.json` — tracked task state (subject, status, activeForm); current bare-UUID and older `session-<id>` directories are supported
- `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — Codex. Line 1 (`session_meta`) gives identity + cwd; `thread_source: "subagent"` files are subagent threads (named by `agent_nickname`), grouped through `source.subagent.thread_spawn.parent_thread_id`; resumes dedupe to newest file per session
- `~/.gemini/tmp/<project>/chats/session-*.jsonl` — Gemini CLI main sessions (line 1: `sessionId`/`kind`/`directories`); `chats/<parentSessionId>/*.jsonl` are subagent recordings (linked by directory name). Flat messages and resumed-session `$set.messages` snapshots support `type: user|gemini` and per-message `tokens.output`. Legacy single-`.json` chat files are not parsed
- `~/.gemini/antigravity-cli/conversations/<session-id>.db` + `log/cli-*.log` — Antigravity CLI (`agy`) sessions. Per-conversation DB/WAL activity provides discovery and working/idle state; stable step-metadata protobuf fields provide output usage, prompt boundaries, and tool action/summary; CLI logs provide the workspace and latest prompt. Conversation content is not decoded
- `~/.copilot/session-state/<uuid>/events.jsonl` (+ legacy `history-session-state/`) — Copilot CLI typed events: `user.message`, `session.start` (`data.context.cwd`), `tool.execution_start`, `subagent.started/completed`, `session.task_complete`. Event `data` field names are de-facto, parsed defensively
- `~/.local/share/opencode/opencode*.db` (SQLite, read-only) — OpenCode: `session` table (`parent_id` links subagent/child sessions, `directory`, `title`, `time_updated` in epoch ms; archived sessions filtered), `session_message` for turns/prompts (message kind = the `type` column; prompt text in `data.text`). Busy/idle is not persisted — inferred from `time_updated` freshness
- `~/.cursor/chats/*/<chat-uuid>/store.db` (SQLite, read-only) — Cursor CLI: `meta` table holds hex-encoded JSON (session name, and a workspace path if one is recorded). Minimal support: discovery + working/idle via db/WAL mtime + title + project; no turn ETA (content is hex blobs). The payload is undocumented, so the workspace is read by trying several key spellings in order of trust and accepting a value — bare path or `file://` — only when it resolves to a directory that exists, since a wrong key would otherwise label the row confidently and wrongly; when none matches, the row reads `cursor` as it always did
- `~/.local/share/goose/sessions/sessions.db` (SQLite, read-only) — Goose v1.10.0+: `sessions` (`working_dir`, `updated_at` UTC, `session_type='subagent'` + `parent_session_id`; archived + infrastructure types `hidden/terminal/gateway/acp` filtered), `messages` (role, `created_timestamp`) for turns/prompts, `usage_ledger` for the token rate (`messages.tokens` is never written by goose). Per-session activity = `updated_at` column, not file mtime (shared DB) — a long single-message generation can briefly read Idle since `updated_at` only bumps on message insert. Legacy per-session `.jsonl` and the `GOOSE_PATH_ROOT` override are not supported
- `~/.factory/projects/<project>/<session-id>.jsonl` — Factory Droid: line 1 `session_start` (`id`, `sessionTitle`, `cwd`); messages are Anthropic-style blocks (`role`, `content[]`, `timestamp`)

## Session states

| State | Meaning | Derived from |
|---|---|---|
| **Needs input** (red, popup fired) | Claude is blocked on the human | pending `AskUserQuestion`/`ExitPlanMode` in transcript, or an actionable Notification-hook POST (permission prompt / MCP elicitation). Claude only — other harnesses have no needs-input detection |
| **Working** (blue) | Actively generating | transcript/subagent/DB activity within the last 90s; detail = in-progress task's activeForm, else running subagents, else last tool |
| **Idle** (gray) | Turn ended | anything else — "awaiting your message" |

## Start

Stdlib-only, Python 3.11+, no dependencies. Resolve `server.py` relative to this `SKILL.md` in the installed plugin, then start it in the background. Prefer your harness's own background-execution option; otherwise use the form for the shell you are in:

```bash
# macOS, Linux, WSL, Git Bash
python3 "<skill-dir>/server.py" --port 4553 &
```
```powershell
# Windows PowerShell — `&` is the call operator here, not backgrounding.
# The inner double quotes are deliberate: -ArgumentList joins the array with
# spaces without quoting it, so a skill directory containing a space would
# otherwise reach python as two arguments.
Start-Process -PassThru -WindowStyle Hidden python -ArgumentList '"<skill-dir>\server.py"','--port','4553'
```
```bat
:: Windows cmd
start "" /b python "<skill-dir>\server.py" --port 4553
```

`python3` is not a reliable spelling on native Windows — use `python` (or `py -3`) there. Whichever interpreter you start the server with, reuse it for the commands below.

Confirm it responds, then open the UI:

```bash
curl -s http://127.0.0.1:4553/api/data | head -c 200
python3 -m webbrowser -t http://127.0.0.1:4553/
```

Use `127.0.0.1`, not `localhost`: the server listens on IPv4 only, and on some systems `localhost` resolves to `::1` first.

Tell the user the URL, that the page auto-refreshes every 5 seconds, and that popups require the server to be running. Completed-task ages/estimates degrade where the filesystem exposes no birthtime (Linux, and Windows before Python 3.12).

If the port is busy the server exits with an explanation rather than a traceback. Check whether a dashboard is already there (`curl -s http://127.0.0.1:4553/api/data`) before killing anything.

## Notifications

Two paths manage needs-input state, and two layers can deliver the popup. **Exactly one of them fires for any given transition**, so nobody is notified twice:

- **macOS** — the server fires `osascript display notification` (60s per-session cooldown plus a 15s global floor). This works with no browser tab open, which is what the lifecycle-hook path below needs.
- **Linux and Windows** — the server has no native backend yet, so the dashboard page raises a browser notification instead. `/api/data` reports which layer is active as `native_notify`. Browser notifications need permission: an "Enable notifications" button appears in the header when it has not been granted, and the header says so if the browser has blocked them. They only fire while a dashboard tab is open — so on these platforms the hook path below still delivers no popup when no tab is open.

Both layers notify on the *transition* into needs-input, not on every refresh a session spends blocked.

**Known gap:** idle nudges (`idle_prompt`) pop without marking the session blocked. The server delivers those on macOS, but the page only notifies on a needs-input transition — so on Linux and Windows an idle nudge produces no popup today. Closing it needs a one-shot event channel in `/api/data`; it is tracked alongside the native Linux and Windows backends rather than bolted on here.

1. **Transcript detection** — an open AskUserQuestion flips the session to Needs input on the next poll (the UI polling `/api/data` drives this; keep a dashboard tab open).
2. **Lifecycle hooks** — `Notification` and `SessionEnd` hooks in user settings (`~/.claude/settings.json`) POSTing their payloads to `http://127.0.0.1:4553/api/notify`. Notifications cover permission prompts and idle waits, even with no browser tab open. The structured `notification_type` decides whether a notification is actionable. Idle nudges (`idle_prompt`, message "Claude is waiting for your input") pop once but never mark the session blocked; authentication/completion notifications do neither; permission prompts and MCP elicitation dialogs create Needs-input state. `SessionEnd` clears a standing hook when Claude exits cleanly. These hooks are NOT installed by the plugin — if the user wants path 2, offer to add them to their `~/.claude/settings.json`:

Use the bundled `notify_hook.py` (next to `server.py`) rather than a `curl` one-liner. The one-liner is POSIX-only end to end — single-quoting, `/dev/null`, `|| true`, and `--data-binary @-` all fail in `cmd.exe`, and Windows PowerShell 5.1 aliases `curl` to `Invoke-WebRequest` and has no `||`. One interpreter invocation behaves the same in every shell, exits 0 even when the dashboard is not running, and refuses to POST anywhere but loopback.

```json
"hooks": {
  "Notification": [
    {"matcher": "", "hooks": [{"type": "command", "command": "python3 \"<skill-dir>/notify_hook.py\"", "async": true}]}
  ],
  "SessionEnd": [
    {"matcher": "", "hooks": [{"type": "command", "command": "python3 \"<skill-dir>/notify_hook.py\""}]}
  ]
}
```

On native Windows use `python` instead of `python3`, and a Windows path. Pass a URL as the first argument for a non-default port: `python3 "<skill-dir>/notify_hook.py" http://127.0.0.1:9999/api/notify`.

After adding it (or after any settings change that breaks it), tell the user to open `/hooks` once or restart Claude Code to reload hook config.

Simulate for testing:
```bash
echo '{"session_id":"<id>","message":"test"}' | python3 "<skill-dir>/notify_hook.py"
```

## Options

| Flag / URL | Effect |
|---|---|
| `--port N` | Change port (default 4553). If the port is busy, check `curl -s http://127.0.0.1:4553/api/data` first — a running dashboard may already be there; don't kill it blindly. |
| `--window-hours H` | Sessions idle longer than H hours are hidden (default 24) |
| `--diagnose` | Print where each harness's data was searched for and what was found there, then exit. Use this first whenever a harness the user expects is missing — collectors skip broken or absent stores silently, so a wrong path looks exactly like an idle machine. Add `--json` for machine-readable output. Reads local paths only; nothing is transmitted. |
| `--no-spacedock` | Do not read Spacedock workflow definitions. The role badge still shows, but the stage strips do not. |
| `http://127.0.0.1:4553/?all=1` | Show all sessions ever, including idle ones |
| `/api/data` | Raw JSON, same data as the UI |

## Interpretation notes (share with the user if asked)

- **Age** = time since the task file was created (birthtime where the platform has it — macOS, and Windows on Python 3.12+; elsewhere it falls back to mtime). For completed tasks it is creation → last update.
- **Output rate** = output tokens over the last 10 minutes. Generation rate, not billed input/cache tokens. Claude, Codex, Gemini CLI / Antigravity CLI, and Goose expose per-message or per-generation token data. Copilot, OpenCode, Cursor, and Droid sessions always contribute 0 to this tile (their stores do not expose usable live token totals).
- **Rate sparklines** (the trend under the Output rate number, and the mini one beside each working card's tok/min) trail the last 5 minutes and are client-side only: they start filling when the page opens, discard points that age out of the window, and reset on page reload. Hover or focus the tile sparkline for exact values.
- **"This request" ETA** = per-session current-turn estimate shown while Working. Estimated total = median of that session's past turns that lasted at least as long as the current one has so far. Turn boundaries: user prompt → last event before the next prompt (Claude, Gemini, Droid), explicit start/end events (Codex `task_started`/`task_complete`, Copilot `user.message`/`session.task_complete`), or DB message timestamps (OpenCode, Goose). JSONL harnesses use an incremental whole-file scanner (survives turns longer than the transcript tail). No ETA for Cursor. "running longer than recent turns" = no past turn was this long. Naive by design. A ⚠️ appears when elapsed or estimated total ≥ 15 min (`LONG_TURN_WARN_SEC`). Elapsed measures generation, not waiting: a mid-turn quiet stretch longer than 5 minutes (`TURN_GAP_RESET_SEC` — permission prompt, open question, sleep) re-anchors the clock at the post-gap event.
- **Est. remaining** (per tracked-task session) = average duration of that session's completed tasks × open task count. Naive by design; "no estimate" until a session has a completed task that took ≥30s.
- **Spacedock stage strip** = one line per in-flight entity, showing that workflow's stages in declaration order with the entity's current stage highlighted. A bold entity name means a worker for it is running now; a plain one is read from the entity's state file or, failing that, the boot snapshot. In flight means moving: an entity resting on the initial stage or a terminal one is left out unless boot called it dispatchable, so a queue of thirty waiting on `intake` does not crowd out the two being worked. Entities whose state file has not been touched inside the freshness window are history, not work, and are skipped — that is what keeps a long-retired workflow off the card of a first officer that merely discovered it. A long workflow is windowed around the current stage, with `…` standing in for the stages elided. An over-long entity name is elided in the **middle**, never the tail — entities in one workflow share a long prefix and differ only at the end — and hovering it shows the full slug. No strip appears when the boot output is outside the scanned head of a long transcript, when the workflow README cannot be read, or when its frontmatter uses a construct the reader does not model — it renders nothing rather than a guess.
- **Session title** = the harness's own generated title where it writes one (Claude records these, and they read like "Debug Spacedock workflow steps not displaying"), otherwise the session's first prompt. That fallback is cleaned up rather than shown raw: a slash command reads as `/plugin` instead of the markup the harness wrapped it in, a dispatched worker's prompt shows the instruction instead of the envelope, absolute paths collapse to their last segment so the path does not eat the whole line, and an over-long title is cut on a word boundary. Relative paths and URLs are left whole, because the repo and PR number in a link are the informative part. Nothing is summarized by a model, so no session text leaves the machine.
- **Project** = the last two segments of the session's working directory (`spacedock/subspace`), the same rule on every harness so one directory reads identically whichever agent opened it. Bare basename is not enough: sibling worktrees are routinely all named the same thing. Claude is the only harness whose store does not hand over a path — its `projects/` directory name encodes one with every separator replaced by `-`, which cannot be split back apart — so the real working directory is read from the transcript records, and a transcript too young to carry one falls back to that encoded name whole. Cursor reports its workspace when its store records one and the harness name otherwise.
- **Session id** = enough leading characters of the session's id to be unique among the rows it sits beside, at least 8. Codex hands out time-ordered ids, so agents launched together share a long prefix, and a fixed 8 characters showed several distinct sessions as one repeated row. The width grows only within the harness and project that actually collided, so a fan-out in one worktree does not lengthen the id of an unrelated session elsewhere.
- Task rows only exist for sessions where Claude used TaskCreate — the session state line is always live regardless. Summary tiles show "–" when no session has tracked tasks.

## Stop

```bash
# macOS, Linux, WSL (lsof is absent on many minimal images — fuser is the fallback)
lsof -ti tcp:4553 -sTCP:LISTEN | xargs kill
fuser -k 4553/tcp
```
```powershell
# Windows PowerShell
Get-NetTCPConnection -LocalPort 4553 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```
```bat
:: Windows cmd, typed at the prompt — inside a .bat file write %%a for %a.
:: Two literal findstr passes; findstr does not take a regex without /R.
for /f "tokens=5" %a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":4553"') do taskkill /PID %a /F
```

Match only *listening* sockets (`-sTCP:LISTEN`, `-State Listen`, `LISTENING`): without that filter these commands also match connected clients — including the browser's network process. Substitute the port the server was actually started on, and note the cmd form matches any port whose digits contain the string (`:4553` also matches `:45530`), so prefer the PowerShell form on Windows.

## Common mistakes

- The server binds to 127.0.0.1 only — do not "fix" it to 0.0.0.0; it exposes local session data.
- A harness the user expects is missing: run `--diagnose` before guessing. It distinguishes "no store here", "store present but unreadable", and "store read, no recent sessions" — the collectors cannot, because they skip unreadable stores silently by design.
- Headless Linux (no graphical session): `python3 -m webbrowser` and `notify-send` both need a desktop. Reach the dashboard over SSH with `ssh -L 4553:127.0.0.1:4553 <host>` and open it locally. If running it under systemd, use a **user** unit — a system unit expands `~` to `/root` and `ProtectHome` hides every harness store.
- Flatpak- or Snap-installed harnesses write inside their sandbox, and Snap's `home` interface excludes dotfiles like `.claude`. Cargento running outside the sandbox will not see them; `--diagnose` shows where it looked.
- Very long Windows paths: Claude's encoded project directory names are long by construction, and without `LongPathsEnabled` a store can exceed the 260-character limit. Those transcripts are skipped rather than crashing, so the symptom is missing sessions — `--diagnose` reports the root it scanned.
- On Windows, Cargento briefly holds a transcript open while reading it, and Python cannot request `FILE_SHARE_DELETE`. If a harness rotates that exact file in that window it may see a sharing violation. Reads are short and bounded, but the window is not zero; there is no way to close it from Python without native calls.
- A session stuck on "Needs input" after you already answered: the state clears on the next transcript event; `SessionEnd` clears it on a clean Claude exit; a server restart also clears hook-reported notifications (they're in-memory). An abrupt kill cannot be distinguished from a terminal left open at a prompt, so it clears only by a later transcript event or restart.
- After two missed refreshes, the live header changes to "stalled" and shows the last successful update — restart the server, no need to reload the page.
