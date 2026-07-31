---
name: cargento
description: Open Cargento, a local agent-cartography dashboard for Claude Code, Codex, Pi, Gemini or Antigravity, Copilot, OpenCode, Cursor, Goose, and Droid sessions, with subagents, task progress, token rate, ETAs, and Claude input-wait notifications. Use for “open cargento” or “monitor agent progress”.
license: Apache-2.0
---

# Cargento

Cargento is an agnostic agent cartography and visualization tool: a local web dashboard mapping live coding-agent activity across **nine harnesses** on this machine — Claude Code, Codex, Pi, Gemini CLI / Antigravity CLI, GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, Factory Droid — each row badged with its harness. A "Discovered harnesses" strip at the top shows all supported harnesses; ones with local session data are green/enabled, others gray/disabled. A harness's sessions only appear if its data is discovered. Transcript-backed sessions appear even if they never called TaskCreate; Claude task files may also surface a task-only session when its transcript is unavailable. Per session: a live state badge, what it's doing right now, running subagents (named pills), a current-turn elapsed/ETA estimate with progress bar, a ⚠️ warning (with tooltip) when a request runs or is estimated ≥15 min, one row per tracked task, and the recent token output rate. Fires desktop notifications when a Claude session is blocked waiting on the human. Two display modes render the same data — see Display modes below.

Store locations are resolved per platform, and the documented relocation variables are honored: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME` (the CLI creates `.gemini` inside it), `COPILOT_HOME`, `PI_CODING_AGENT_DIR`, and `PI_CODING_AGENT_SESSION_DIR`. When one is set it is authoritative — no fallback to the default location. Run `--diagnose` to see every path searched.

Data sources (read-only, no external calls; all parsing is defensive — a broken harness store is skipped, never fatal):
- `~/.claude/projects/*/<session>.jsonl` — Claude transcript tails: session discovery, titles, token usage, pending AskUserQuestion detection
- Claude subagents, two generations: modern harnesses write each subagent as a top-level `~/.claude/projects/*/<uuid>.jsonl` whose records carry `agentName` + `teamName: "session-<parent prefix>"` — these fold into the parent session (named pill, freshness, output rate) and never appear as standalone sessions; legacy `<session-uuid>/subagents/agent-*.jsonl` + `.meta.json` files are still recognized (fresh mtime = running), including the `subagents/workflows/<run-id>/` directory a workflow fan-out nests its agents in. A bare `agentName` from a top-level `--agent` launch has no parent relation and remains a standalone session; `agentSetting`, not `agentName`, supplies any Spacedock role. Agent writes count as parent activity in their own right, so a session parked on a long background workflow reads Working rather than Idle
- Spacedock workflows: a Claude session launched by Spacedock carries an `agentSetting` of `spacedock:first-officer` or `spacedock:ensign` in its first transcript records, which is how the role badge appears. A first officer also records its `spacedock status --boot` output — counted only when it arrives as command output, never as ordinary conversation text — which names each workflow directory and each entity-state directory absolutely. The ordered stage list comes from the workflow `README.md` frontmatter, and each entity's current stage from the `status` in its own state-file frontmatter; boot's `dispatchable` list is only a snapshot of what was ready to move at boot, so it fills in behind the state directory rather than standing in for it. Those two kinds of frontmatter are the only project files Cargento reads — see the repository's SECURITY.md for the contract, and `--no-spacedock` to disable it
- `~/.claude/tasks/<session-id>/N.json` — tracked task state (subject, status, activeForm); current bare-UUID and older `session-<id>` directories are supported
- `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — Codex. Line 1 (`session_meta`) gives identity + cwd; `thread_source: "subagent"` files are subagent threads (named by `agent_nickname`), grouped through `source.subagent.thread_spawn.parent_thread_id`; resumes dedupe to newest file per session
- `~/.pi/agent/sessions/--<encoded-cwd>--/<timestamp>_<uuid>.jsonl` — Pi v3. The default store is nested; a custom session store is flat and contains JSONL files directly. The last persisted leaf's ancestor path is active, so sibling branches are excluded from prompts, tools, output usage, and turns. The latest global `session_info` name is the title, including a later clear; `parentSession` means fork or clone, never a subagent. Assistant, tool-result, compaction, and branch-summary output usage feed the rate. Pi has no passive needs-input, Spacedock, or core-subagent signal.
- `~/.gemini/tmp/<project>/chats/session-*.jsonl` — Gemini CLI main sessions (line 1: `sessionId`/`kind`/`directories`); `chats/<parentSessionId>/*.jsonl` are subagent recordings (linked by directory name). Flat messages and resumed-session `$set.messages` snapshots support `type: user|gemini` and per-message `tokens.output`. Legacy single-`.json` chat files are not parsed
- `~/.gemini/antigravity-cli/conversations/<session-id>.db` + `cache/last_conversations.json` + `log/cli-*.log` — Antigravity CLI (`agy`) sessions. Per-conversation DB/WAL activity provides discovery and working/idle state; trajectory-metadata protobuf fields fold fresh subagents at every nesting depth into the root card with role/type labels, and descendant activity and output usage feed the root state and token rate; stable step-metadata fields provide prompt boundaries and tool action/summary; the cache supplies the primary workspace, with CLI logs as its fallback and as the latest-prompt source. Conversation content is not decoded
- `~/.copilot/session-state/<uuid>/events.jsonl` (+ legacy `history-session-state/`) — Copilot CLI typed events: `user.message`, `session.start` (`data.context.cwd`), `tool.execution_start`, `subagent.started/completed`, `session.task_complete`. Event `data` field names are de-facto, parsed defensively
- `~/.local/share/opencode/opencode*.db` (SQLite, read-only) — OpenCode: `session` table (`parent_id` links subagent/child sessions, `directory`, `title`, `time_updated` in epoch ms; archived sessions filtered), `session_message` for turns/prompts (message kind = the `type` column; prompt text in `data.text`). Busy/idle is not persisted — inferred from `time_updated` freshness
- `~/.cursor/chats/*/<chat-uuid>/store.db` (SQLite, read-only) — Cursor CLI: `meta` table holds hex-encoded JSON (session name, and a workspace path if one is recorded). Minimal support: discovery + working/idle via db/WAL mtime + title + project; no turn ETA (content is hex blobs). The payload is undocumented, so the workspace is read by trying several key spellings in order of trust and accepting a value — bare path or `file://` — only when it resolves to a directory that exists, since a wrong key would otherwise label the row confidently and wrongly; when none matches, the row reads `cursor` as it always did
- `~/.local/share/goose/sessions/sessions.db` (SQLite, read-only) — Goose v1.10.0+: `sessions` (`working_dir`, `updated_at` UTC, `session_type='subagent'` + `parent_session_id`; archived + infrastructure types `hidden/terminal/gateway/acp` filtered), `messages` (role, `created_timestamp`) for turns/prompts, `usage_ledger` for the token rate (`messages.tokens` is never written by goose). Per-session activity = `updated_at` column, not file mtime (shared DB) — a long single-message generation can briefly read Idle since `updated_at` only bumps on message insert. Legacy per-session `.jsonl` and the `GOOSE_PATH_ROOT` override are not supported
- `~/.factory/projects/<project>/<session-id>.jsonl` — Factory Droid: line 1 `session_start` (`id`, `sessionTitle`, `cwd`); messages are Anthropic-style blocks (`role`, `content[]`, `timestamp`)

Pi relocation: `PI_CODING_AGENT_SESSION_DIR` is an authoritative direct session-store override and takes precedence over `PI_CODING_AGENT_DIR`, Pi's global `sessionDir` setting, and the default. `PI_CODING_AGENT_DIR` relocates the configuration root; a relative global `sessionDir` resolves below it. A one-off Pi `--session-dir` and a project-local `.pi/settings.json` are not discoverable from this separate process. Set `PI_CODING_AGENT_SESSION_DIR` to the effective directory in either case.

## Session states

| State | Meaning | Derived from |
|---|---|---|
| **Needs input** (red, popup fired) | Claude is blocked on the human | pending `AskUserQuestion`/`ExitPlanMode` in transcript, or an actionable Notification-hook POST (permission prompt / MCP elicitation). Claude only — other harnesses have no needs-input detection |
| **Working** (blue) | Actively generating | transcript/subagent/DB activity within the last 90s; detail = in-progress task's activeForm, else running subagents, else last tool |
| **Idle** (gray) | Turn ended | anything else — "awaiting your message" |

## Display modes

A `display` switch at the top right toggles between two renderings of the same `/api/data` payload. The choice is remembered per browser (`localStorage`, key `cargento.displayMode`) and `c` toggles it from the keyboard. Nothing is filtered out of one mode and present in the other; the two never disagree about a session.

A `stop` button sits beside the switch in both modes: the first activation arms it and keeps focus
there, and the second stops the server. `Enter` or `Space` on the focused button works like a click.
Anything unrelated you do first — `esc`, a click elsewhere, another control, another key —
disarms it. After it fires the page stops polling and says
Cargento was stopped, rather than showing the "stalled" banner that means the server went away on
its own.

- **regular** (default) — the card stack: hero tiles, the needs-input band, one card per working session, a collapsed idle list. The `Needs you` and `Working now` tiles break their count down per harness. Every working card draws the same parts in the same order, including a current-turn track — indeterminate when no past turn ran long enough to estimate against.
- **calm** — one dense ledger row per session in a fixed frame that scrolls internally, for boards with more sessions than fit as cards. Columns: state rail, harness, session title, `project · session id`, what it's doing, flag, `rate`, and `idle / wait`. `rate` is tokens per minute while working, with the current-turn progress bar beneath it, and a dash where the harness reports no token rate (matching the regular view, which omits the meter there); `idle / wait` is how long a blocked or idle session has been sitting. Each column carries one unit, so it can be compared down its own length, and is empty on the buckets it does not describe. Clicking a row expands it in place with the flag's explanation, the last prompt, tracked tasks, any Spacedock stage strips, the turn estimate, subagents, and `copy id`. When the project name is too long for its column the project is truncated, never the session id.

MCP tools appear under the service being called rather than their wire name — `Linear · list issues`, not the double-underscored triple the harness records. The full original string is in the row's tooltip.

Calm mode's own controls: the three state counts in the header filter by state, `order` sorts by `attention` (flagged and blocking states first, newest within each), `recent`, or `repo` (grouped, with a heading per project), and the `◆ N flagged` pill narrows to flagged rows. Keys: `j`/`k` or arrows move the cursor, `⏎` expands, `f` toggles the flagged filter, `c` switches mode, `esc` clears filters. Row order is stable across the 5-second refresh, so rows do not move under the cursor while you read.

Three flags appear in the `flag` column, and only these three — each is a signal the server actually detects, so no flag means nothing is known to be wrong:

| Flag | Meaning |
|---|---|
| **your call** (red) | Needs input. You are the blocker. |
| **long turn** (amber) | Working, and this request has run or is estimated to run ≥15 min (`LONG_TURN_WARN_SEC`) — the same signal as the regular view's ⚠️. |
| **stale** (gray) | Idle with no activity for ≥2h. Either it finished quietly and nobody read the result, or it is waiting on a reply that never came. |

## Start

Stdlib-only, Python 3.11+, no dependencies. Resolve `server.py` relative to this `SKILL.md` in the
installed plugin and start it detached, so it keeps running after this session ends:

```bash
python3 "<skill-dir>/server.py" --port 4553 --daemon
```

One line on every platform and in every shell — `--daemon` does the detaching itself, so no
backgrounding operator is involved. It prints the URL, the pid and the log path, and returns.
On native Windows `python3` is not a reliable spelling; use `python` (or `py -3`). Whichever
interpreter starts the server, reuse it for the commands below.

Drop `--daemon` to run it in the foreground instead, which is the easier shape for debugging: log
output goes to your terminal rather than to the log file.

Then open the UI:

```bash
python3 -m webbrowser -t http://127.0.0.1:4553/
```

Use `127.0.0.1`, not `localhost`: the server listens on IPv4 only, and on some systems `localhost`
resolves to `::1` first.

Tell the user the URL, that the page auto-refreshes every 5 seconds, that it keeps running until
stopped, and that popups require the server to be running. Completed-task ages/estimates degrade
where the filesystem exposes no birthtime (Linux, and Windows before Python 3.12).

If the port is busy the server explains that instead of dumping a traceback, and exits non-zero —
under `--daemon` too. Check whether a dashboard is already there before killing anything:

```bash
python3 "<skill-dir>/server.py" --port 4553 --status
```

`--status` reports one of three things, and never guesses: running (with pid and start time), not
running, or that the port belongs to some other process — in which case it changes nothing.

Cargento writes two files, both under `~/.cargento` (relocatable with `CARGENTO_HOME`):
`cargento-<port>.json`, which records the running instance, and `cargento-<port>.log`, where a
detached server's output goes.

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
| `--port N` | Change port (default 4553; valid range 1–65535). If the port is busy, check `--status` first — a running dashboard may already be there; don't kill it blindly. |
| `--daemon` | Detach and keep running after the starting session exits. Prints the URL, pid and log path. |
| `--stop` | Stop the instance on `--port`, over `/api/shutdown` — the same path the UI's `stop` button uses. Returns once the port is free, so a restart on the same port works. |
| `--status` | Report whether Cargento is on `--port`: running, not running, or the port belongs to another process. Exits 0 only when running. |
| `--window-hours H` | Sessions idle longer than H hours are hidden (default 24) |
| `--diagnose` | Print where each harness's data was searched for and what was found there, then exit. Use this first whenever a harness the user expects is missing — collectors skip broken or absent stores silently, so a wrong path looks exactly like an idle machine. Add `--json` for machine-readable output. Reads local paths only; nothing is transmitted. |
| `--no-spacedock` | Do not read Spacedock workflow definitions. The role badge still shows, but the stage strips do not. |
| `http://127.0.0.1:4553/?all=1` | Show all sessions ever, including idle ones |
| `/api/data` | Raw JSON, same data as the UI |
| `/api/health` | Liveness and identity (pid, port, start time). Scans nothing, unlike `/api/data`. |
| `POST /api/shutdown` | Stop the server. Loopback-only, with the same origin checks as `/api/notify`. |

## Interpretation notes (share with the user if asked)

- **Age** = time since the task file was created (birthtime where the platform has it — macOS, and Windows on Python 3.12+; elsewhere it falls back to mtime). For completed tasks it is creation → last update.
- **Output rate** = output tokens over the last 10 minutes. Generation rate, not billed input/cache tokens. Claude, Codex, Pi, Gemini CLI / Antigravity CLI, and Goose expose per-message or per-generation token data. Copilot, OpenCode, Cursor, and Droid sessions always contribute 0 to this tile (their stores do not expose usable live token totals).
- **Rate sparklines** (the trend under the Output rate number, and the mini one beside each working card's tok/min) trail the last 5 minutes and are client-side only: they start filling when the page opens, discard points that age out of the window, and reset on page reload. Hover or focus the tile sparkline for exact values.
- **"This request" ETA** = per-session current-turn estimate shown while Working. Estimated total = median of that session's past turns that lasted at least as long as the current one has so far. Turn boundaries: user prompt → last event before the next prompt (Claude, Gemini, Droid); active-branch user messages for Pi; explicit start/end events (Codex `task_started`/`task_complete`, Copilot `user.message`/`session.task_complete`); or DB message timestamps (OpenCode, Goose). JSONL harnesses use an incremental whole-file scanner (survives turns longer than the transcript tail). Pi retains the latest 50 completed durations. No ETA for Cursor. "running longer than recent turns" = no past turn was this long. Naive by design. A ⚠️ appears when elapsed or estimated total ≥ 15 min (`LONG_TURN_WARN_SEC`). Elapsed measures generation, not waiting: a mid-turn quiet stretch longer than 5 minutes (`TURN_GAP_RESET_SEC` — permission prompt, open question, sleep) re-anchors the clock at the post-gap event.
- **Est. remaining** (per tracked-task session) = average duration of that session's completed tasks × open task count. Naive by design; "no estimate" until a session has a completed task that took ≥30s.
- **Spacedock stage strip** = one line per in-flight entity, showing that workflow's stages in declaration order with the entity's current stage highlighted. A bold entity name means a worker for it is running now; a plain one is read from the entity's state file or, failing that, the boot snapshot. In flight means moving: an entity resting on the initial stage or a terminal one is left out unless boot called it dispatchable, so a queue of thirty waiting on `intake` does not crowd out the two being worked. Entities whose state file has not been touched inside the freshness window are history, not work, and are skipped — that is what keeps a long-retired workflow off the card of a first officer that merely discovered it. A long workflow is windowed around the current stage, with `…` standing in for the stages elided. An over-long entity name is elided in the **middle**, never the tail — entities in one workflow share a long prefix and differ only at the end — and hovering it shows the full slug. No strip appears when the boot output is outside the scanned head of a long transcript, when the workflow README cannot be read, or when its frontmatter uses a construct the reader does not model — it renders nothing rather than a guess.
- **Session title** = the harness's own generated title where it writes one (Claude records these, and they read like "Debug Spacedock workflow steps not displaying"), otherwise the session's first prompt. That fallback is cleaned up rather than shown raw: a slash command reads as `/plugin` instead of the markup the harness wrapped it in, a dispatched worker's prompt shows the instruction instead of the envelope, absolute paths collapse to their last segment so the path does not eat the whole line, and an over-long title is cut on a word boundary. Relative paths and URLs are left whole, because the repo and PR number in a link are the informative part. Nothing is summarized by a model, so no session text leaves the machine.
- **Project** = the last two segments of the session's working directory (`spacedock/subspace`), the same rule on every harness so one directory reads identically whichever agent opened it. Bare basename is not enough: sibling worktrees are routinely all named the same thing. Claude is the only harness whose store does not hand over a path — its `projects/` directory name encodes one with every separator replaced by `-`, which cannot be split back apart — so the real working directory is read from the transcript records, and a transcript too young to carry one falls back to that encoded name whole. Cursor reports its workspace when its store records one and the harness name otherwise.
- **Session id** = enough leading characters of the session's id to be unique among the rows it sits beside, at least 8. Codex hands out time-ordered ids, so agents launched together share a long prefix, and a fixed 8 characters showed several distinct sessions as one repeated row. The width grows only within the harness and project that actually collided, so a fan-out in one worktree does not lengthen the id of an unrelated session elsewhere.
- Task rows only exist for sessions where Claude used TaskCreate — the session state line is always live regardless. Summary tiles show "–" when no session has tracked tasks.
- **Calm-mode row order** is deliberately a function of nothing that changes on its own: state, then age, then the session id. A *working* session's last activity is by definition seconds old, so ordering working rows by age would sort them on which one happened to write last and reshuffle them every refresh — they sit level instead, ordered by id. A row therefore moves when its state changes, not because time passed. Same reason `/api/data` orders sessions by id rather than by last activity.

## Stop

```bash
python3 "<skill-dir>/server.py" --port 4553 --stop
```

Or activate `stop` twice in the dashboard header — click it, or use `Enter` or `Space` while it has
focus. The page cannot undo the stop, and an unrelated action in between counts as "no". Both the
button and the command use `POST /api/shutdown`. `--stop` waits for the port to come free before
reporting success, so you can start a fresh instance on the same port straight afterwards. It also
clears a state file left behind by a server that was killed,
and exits non-zero without touching anything if the port turns out to belong to another process.

**Last resort**, for a server wedged badly enough that it no longer answers HTTP. Match only
*listening* sockets — without that filter these also match connected clients, including the
browser's own network process:

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
for /f "tokens=5" %a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":4553"') do taskkill /PID %a /F
```

Substitute the port the server was actually started on. The cmd form matches any port whose digits
contain the string (`:4553` also matches `:45530`), so prefer the PowerShell form on Windows.

## Common mistakes

- The server binds to 127.0.0.1 only — do not "fix" it to 0.0.0.0; it exposes local session data.
- A harness the user expects is missing: run `--diagnose` before guessing. It distinguishes "no store here", "store present but unreadable", and "store read, no recent sessions" — the collectors cannot, because they skip unreadable stores silently by design.
- Headless Linux (no graphical session): `python3 -m webbrowser` and `notify-send` both need a desktop. Reach the dashboard over SSH with `ssh -L 4553:127.0.0.1:4553 <host>` and open it locally. If running it under systemd, use a **user** unit — a system unit expands `~` to `/root` and `ProtectHome` hides every harness store.
- Flatpak- or Snap-installed harnesses write inside their sandbox, and Snap's `home` interface excludes dotfiles like `.claude`. Cargento running outside the sandbox will not see them; `--diagnose` shows where it looked.
- Very long Windows paths: Claude's encoded project directory names are long by construction, and without `LongPathsEnabled` a store can exceed the 260-character limit. Those transcripts are skipped rather than crashing, so the symptom is missing sessions — `--diagnose` reports the root it scanned.
- On Windows, Cargento briefly holds a transcript open while reading it, and Python cannot request `FILE_SHARE_DELETE`. If a harness rotates that exact file in that window it may see a sharing violation. Reads are short and bounded, but the window is not zero; there is no way to close it from Python without native calls.
- A session stuck on "Needs input" after you already answered: the state clears on the next transcript event; `SessionEnd` clears it on a clean Claude exit; a server restart also clears hook-reported notifications (they're in-memory). An abrupt kill cannot be distinguished from a terminal left open at a prompt, so it clears only by a later transcript event or restart.
- After two missed refreshes, the live header changes to "stalled" and shows the last successful update — restart the server, no need to reload the page.
