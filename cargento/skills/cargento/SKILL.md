---
name: cargento
description: Open Cargento, a local agent-cartography dashboard for Claude Code, Codex, Gemini or Antigravity, Copilot, OpenCode, Cursor, Goose, and Droid sessions, with subagents, task progress, token rate, ETAs, and Claude input-wait notifications. Use for “open cargento” or “monitor agent progress”.
license: Apache-2.0
---

# Cargento

Cargento is an agnostic agent cartography and visualization tool: a local web dashboard mapping live coding-agent activity across **eight harnesses** on this machine — Claude Code, Codex, Gemini CLI / Antigravity CLI, GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, Factory Droid — each row badged with its harness. A "Discovered harnesses" strip at the top shows all supported harnesses; ones with local session data are green/enabled, others gray/disabled. A harness's sessions only appear if its data is discovered. Transcript-backed sessions appear even if they never called TaskCreate; Claude task files may also surface a task-only session when its transcript is unavailable. Per session: a live state badge, what it's doing right now, running subagents (named pills), a current-turn elapsed/ETA estimate with progress bar, a ⚠️ warning (with tooltip) when a request runs or is estimated ≥15 min, one row per tracked task, and the recent token output rate. Fires macOS popup notifications when a Claude session is blocked waiting on the human.

Data sources (read-only, no external calls; all parsing is defensive — a broken harness store is skipped, never fatal):
- `~/.claude/projects/*/<session>.jsonl` — Claude transcript tails: session discovery, titles, token usage, pending AskUserQuestion detection
- Claude subagents, two generations: modern harnesses write each subagent as a top-level `~/.claude/projects/*/<uuid>.jsonl` whose records carry `agentName` + `teamName: "session-<parent prefix>"` — these fold into the parent session (named pill, freshness, output rate) and never appear as standalone sessions; legacy `<session-uuid>/subagents/agent-*.jsonl` + `.meta.json` files are still recognized (fresh mtime = running)
- `~/.claude/tasks/<session-id>/N.json` — tracked task state (subject, status, activeForm); current bare-UUID and older `session-<id>` directories are supported
- `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — Codex. Line 1 (`session_meta`) gives identity + cwd; `thread_source: "subagent"` files are subagent threads (named by `agent_nickname`), grouped through `source.subagent.thread_spawn.parent_thread_id`; resumes dedupe to newest file per session
- `~/.gemini/tmp/<project>/chats/session-*.jsonl` — Gemini CLI main sessions (line 1: `sessionId`/`kind`/`directories`); `chats/<parentSessionId>/*.jsonl` are subagent recordings (linked by directory name). Flat messages and resumed-session `$set.messages` snapshots support `type: user|gemini` and per-message `tokens.output`. Legacy single-`.json` chat files are not parsed
- `~/.gemini/antigravity-cli/conversations/<session-id>.db` + `log/cli-*.log` — Antigravity CLI (`agy`) sessions. Per-conversation DB/WAL activity provides discovery and working/idle state; stable step-metadata protobuf fields provide output usage, prompt boundaries, and tool action/summary; CLI logs provide the workspace and latest prompt. Conversation content is not decoded
- `~/.copilot/session-state/<uuid>/events.jsonl` (+ legacy `history-session-state/`) — Copilot CLI typed events: `user.message`, `session.start` (`data.context.cwd`), `tool.execution_start`, `subagent.started/completed`, `session.task_complete`. Event `data` field names are de-facto, parsed defensively
- `~/.local/share/opencode/opencode*.db` (SQLite, read-only) — OpenCode: `session` table (`parent_id` links subagent/child sessions, `directory`, `title`, `time_updated` in epoch ms; archived sessions filtered), `session_message` for turns/prompts (message kind = the `type` column; prompt text in `data.text`). Busy/idle is not persisted — inferred from `time_updated` freshness
- `~/.cursor/chats/*/<chat-uuid>/store.db` (SQLite, read-only) — Cursor CLI: `meta` table holds hex-encoded JSON (session name). Minimal support: discovery + working/idle via db/WAL mtime + title; no turn ETA (content is hex blobs)
- `~/.local/share/goose/sessions/sessions.db` (SQLite, read-only) — Goose v1.10.0+: `sessions` (`working_dir`, `updated_at` UTC, `session_type='subagent'` + `parent_session_id`; archived + infrastructure types `hidden/terminal/gateway/acp` filtered), `messages` (role, `created_timestamp`) for turns/prompts, `usage_ledger` for the token rate (`messages.tokens` is never written by goose). Per-session activity = `updated_at` column, not file mtime (shared DB) — a long single-message generation can briefly read Idle since `updated_at` only bumps on message insert. Legacy per-session `.jsonl` and the `GOOSE_PATH_ROOT` override are not supported
- `~/.factory/projects/<project>/<session-id>.jsonl` — Factory Droid: line 1 `session_start` (`id`, `sessionTitle`, `cwd`); messages are Anthropic-style blocks (`role`, `content[]`, `timestamp`)

## Session states

| State | Meaning | Derived from |
|---|---|---|
| **Needs input** (red, popup fired) | Claude is blocked on the human | pending `AskUserQuestion`/`ExitPlanMode` in transcript, or a Notification-hook POST (permission prompt / idle). Claude only — other harnesses have no needs-input detection |
| **Working** (blue) | Actively generating | transcript/subagent/DB activity within the last 90s; detail = in-progress task's activeForm, else running subagents, else last tool |
| **Idle** (gray) | Turn ended | anything else — "awaiting your message" |

## Start

Resolve `server.py` relative to this `SKILL.md` in the installed plugin, then run:

```bash
python3 <resolved-skill-directory>/server.py --port 4553
```

Stdlib-only, Python 3.11+, no dependencies. Run it in the background using your harness's background-execution option (or append `&` to the command), confirm it responds (`curl -s http://localhost:4553/api/data | head -c 200`), then open the UI:

```bash
open http://localhost:4553/    # Linux: xdg-open
```

Tell the user the URL, that the page auto-refreshes every 5 seconds, and that popups require the server to be running. Popup notifications are macOS-only (`osascript`); on Linux the dashboard works but popups silently no-op, and completed-task ages/estimates degrade (no file birthtime).

## Notifications

Two paths, both firing `osascript display notification` (60s per-session cooldown plus a 5s global floor):

1. **Transcript detection** — an open AskUserQuestion flips the session to Needs input on the next poll (the UI polling `/api/data` drives this; keep a dashboard tab open).
2. **Notification hook** — a `Notification` hook in user settings (`~/.claude/settings.json`) POSTing the hook payload to `http://127.0.0.1:4553/api/notify`. Covers permission prompts and idle waits, works even with no browser tab open. This hook is NOT installed by the plugin — if the user wants path 2, offer to add it to their `~/.claude/settings.json`:

```json
"hooks": {
  "Notification": [
    {"matcher": "", "hooks": [{"type": "command", "command": "curl -s -m 2 -X POST -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:4553/api/notify >/dev/null 2>&1 || true", "async": true}]}
  ]
}
```

After adding it (or after any settings change that breaks it), tell the user to open `/hooks` once or restart Claude Code to reload hook config.

Simulate for testing:
```bash
echo '{"session_id":"<id>","message":"test"}' | curl -s -X POST --data-binary @- http://127.0.0.1:4553/api/notify
```

## Options

| Flag / URL | Effect |
|---|---|
| `--port N` | Change port (default 4553). If the port is busy, check `curl -s localhost:4553/api/data` first — a running dashboard may already be there; don't kill it blindly. |
| `--window-hours H` | Sessions idle longer than H hours are hidden (default 24) |
| `http://localhost:4553/?all=1` | Show all sessions ever, including idle ones |
| `/api/data` | Raw JSON, same data as the UI |

## Interpretation notes (share with the user if asked)

- **Age** = time since the task file was created (macOS birthtime). For completed tasks it is creation → last update.
- **Output rate** = output tokens over the last 10 minutes. Generation rate, not billed input/cache tokens. Claude, Codex, Gemini CLI / Antigravity CLI, and Goose expose per-message or per-generation token data. Copilot, OpenCode, Cursor, and Droid sessions always contribute 0 to this tile (their stores do not expose usable live token totals).
- **Rate sparklines** (the trend under the Output rate number, and the mini one beside each working card's tok/min) trail the last 5 minutes and are client-side only: they start filling when the page opens, discard points that age out of the window, and reset on page reload. Hover or focus the tile sparkline for exact values.
- **"This request" ETA** = per-session current-turn estimate shown while Working. Estimated total = median of that session's past turns that lasted at least as long as the current one has so far. Turn boundaries: user prompt → last event before the next prompt (Claude, Gemini, Droid), explicit start/end events (Codex `task_started`/`task_complete`, Copilot `user.message`/`session.task_complete`), or DB message timestamps (OpenCode, Goose). JSONL harnesses use an incremental whole-file scanner (survives turns longer than the transcript tail). No ETA for Cursor. "running longer than recent turns" = no past turn was this long. Naive by design. A ⚠️ appears when elapsed or estimated total ≥ 15 min (`LONG_TURN_WARN_SEC`). Elapsed measures generation, not waiting: a mid-turn quiet stretch longer than 5 minutes (`TURN_GAP_RESET_SEC` — permission prompt, open question, sleep) re-anchors the clock at the post-gap event.
- **Est. remaining** (per tracked-task session) = average duration of that session's completed tasks × open task count. Naive by design; "no estimate" until a session has a completed task that took ≥30s.
- Task rows only exist for sessions where Claude used TaskCreate — the session state line is always live regardless. Summary tiles show "–" when no session has tracked tasks.

## Stop

```bash
lsof -ti tcp:4553 -sTCP:LISTEN | xargs kill
```

`-sTCP:LISTEN` matters: without it, lsof also matches connected clients (the browser's network process). Substitute the port the server was actually started on.

## Common mistakes

- The server binds to 127.0.0.1 only — do not "fix" it to 0.0.0.0; it exposes local session data.
- A session stuck on "Needs input" after you already answered: the state clears on the next transcript event; a server restart also clears hook-reported notifications (they're in-memory).
- After two missed refreshes, the live header changes to "stalled" and shows the last successful update — restart the server, no need to reload the page.
