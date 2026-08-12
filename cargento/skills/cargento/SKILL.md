---
name: cargento
description: Open Cargento, a local agent-cartography dashboard for Claude Code, Codex, Pi, Gemini, Antigravity, Copilot, OpenCode, Cursor, Goose, and Droid sessions, with subagents, task progress, token rate, ETAs, and Claude input-wait notifications. Use for “open cargento” or “monitor agent progress”.
license: Apache-2.0
---

# Cargento

Cargento is an agnostic agent cartography and visualization tool: a local web dashboard mapping live coding-agent activity across **ten harnesses** on this machine — Claude Code, Codex, Pi, Gemini CLI, Antigravity CLI, GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, Factory Droid — each row badged with its harness. A "Discovered harnesses" strip at the top shows all supported harnesses; ones with local session data are green/enabled, others gray/disabled. A harness's sessions only appear if its data is discovered. Transcript-backed sessions appear even if they never called TaskCreate; Claude task files may also surface a task-only session when its transcript is unavailable. Per session: a live state badge, what it's doing right now, running subagents (named pills), a current-turn elapsed/ETA estimate with progress bar, a ⚠️ warning (with tooltip) when a request runs or is estimated ≥15 min, one row per tracked task, and the recent token output rate. Fires desktop notifications when a Claude session is blocked waiting on the human. Two display modes render the same data — see Display modes below.

Store locations are resolved per platform, and the documented relocation variables are honored: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME` (the CLI creates `.gemini` inside it; relocates the Antigravity store with it), `COPILOT_HOME`, `PI_CODING_AGENT_DIR`, and `PI_CODING_AGENT_SESSION_DIR`. When one is set it is authoritative — no fallback to the default location. Run `--diagnose` to see every path searched.

Data sources (read-only, no external calls; all parsing is defensive — a broken harness store is skipped, never fatal):
- `~/.claude/projects/*/<session>.jsonl` — Claude transcript tails: session discovery, titles, token usage, pending AskUserQuestion detection and the text of the question it is asking
- Claude subagents, two generations: modern harnesses write each subagent as a top-level `~/.claude/projects/*/<uuid>.jsonl` whose records carry `agentName` + `teamName: "session-<parent prefix>"` — these fold into the parent session (named pill, freshness, output rate) and never appear as standalone sessions; legacy `<session-uuid>/subagents/agent-*.jsonl` + `.meta.json` files are still recognized (fresh mtime = running), including the `subagents/workflows/<run-id>/` directory a workflow fan-out nests its agents in. A bare `agentName` from a top-level `--agent` launch has no parent relation and remains a standalone session; `agentSetting`, not `agentName`, supplies any Spacedock role. Agent writes count as parent activity in their own right, so a session parked on a long background workflow reads Working rather than Idle
- Spacedock workflows: a Claude session launched by Spacedock carries an `agentSetting` of `spacedock:first-officer` or `spacedock:ensign` in its first transcript records, which is how the role badge appears. A first officer also records its `spacedock status --boot` output — counted only when it arrives as command output, never as ordinary conversation text — which names each workflow directory and each entity-state directory absolutely. The ordered stage list comes from the workflow `README.md` frontmatter, and each entity's current stage from the `status` in its own state-file frontmatter; boot's `dispatchable` list is only a snapshot of what was ready to move at boot, so it fills in behind the state directory rather than standing in for it. Those two kinds of frontmatter are the only project files Cargento reads — see the repository's SECURITY.md for the contract, and `--no-spacedock` to disable it
- `~/.claude/tasks/<session-id>/N.json` — tracked task state (subject, status, activeForm); current bare-UUID and older `session-<id>` directories are supported
- `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — Codex. Line 1 (`session_meta`) gives identity + cwd; `thread_source: "subagent"` files are subagent threads (named by `agent_nickname`), grouped through `source.subagent.thread_spawn.parent_thread_id`; resumes dedupe to newest file per session
- `~/.pi/agent/sessions/--<encoded-cwd>--/<timestamp>_<uuid>.jsonl` — Pi v3. The default store is nested; a custom session store is flat and contains JSONL files directly. The last persisted leaf's ancestor path is active, so sibling branches are excluded from prompts, tools, output usage, and turns. The latest global `session_info` name is the title, including a later clear; `parentSession` means fork or clone, never a subagent. Assistant, tool-result, compaction, and branch-summary output usage feed the rate. Pi has no allowance of its own, so each row also names the authority it is spending, read from the newest entry on the active branch that carries one (an assistant message, or a `model_change` the user has switched to but not spent yet): it renders as `via Codex · gpt-5.6-sol`, and a provider with no harness of its own keeps its own name. A session that names no provider makes no claim rather than guessing from Pi's current default. Pi has no passive needs-input, Spacedock, or core-subagent signal.
- `~/.gemini/tmp/<project>/chats/session-*.jsonl` — Gemini CLI main sessions. Gemini CLI stopped serving consumer accounts in June 2026 and Antigravity CLI succeeds it there, but enterprise Code Assist and API-key use still write this store, so it is historical on a consumer machine — sessions read as idle and need `?all=1` to show — and live on an enterprise or API-key one (line 1: `sessionId`/`kind`/`directories`); `chats/<parentSessionId>/*.jsonl` are subagent recordings (linked by directory name). Flat messages and resumed-session `$set.messages` snapshots support `type: user|gemini` and per-message `tokens.output`. Legacy single-`.json` chat files are not parsed
- `~/.gemini/antigravity-cli/conversations/<session-id>.db` + `cache/last_conversations.json` + `log/cli-*.log` — Antigravity CLI (`agy`) sessions. Per-conversation DB/WAL activity provides discovery and working/idle state; trajectory-metadata protobuf fields fold fresh subagents at every nesting depth into the root card with role/type labels, and descendant activity and output usage feed the root state and token rate; stable step-metadata fields provide prompt boundaries and tool action/summary; the cache supplies the primary workspace, with CLI logs as its fallback and as the latest-prompt source. Conversation content is not decoded
- `~/.copilot/session-state/<uuid>/events.jsonl` (+ legacy `history-session-state/`) — Copilot CLI typed events: `user.message`, `session.start` (`data.context.cwd`), `tool.execution_start`, `subagent.started/completed/failed`, `session.task_complete`. A subagent's model comes off the same `subagent.started` object its name does, so the two are paired without a join, and all three subagent events are keyed on the `agentId` they share. Event `data` field names are de-facto, parsed defensively
- `~/.local/share/opencode/opencode*.db` (SQLite, read-only) — OpenCode: `session` table (`parent_id` links subagent/child sessions, `directory`, `title`, `time_updated` in epoch ms; archived sessions filtered), `session_message` for turns/prompts (message kind = the `type` column; prompt text in `data.text`). Busy/idle is not persisted — inferred from `time_updated` freshness
- `~/.cursor/chats/*/<chat-uuid>/store.db` (SQLite, read-only) — Cursor CLI: `meta` table holds hex-encoded JSON (session name, and a workspace path if one is recorded). Minimal support: discovery + working/idle via db/WAL mtime + title + project + the model of the newest message; no turn ETA (content is hex blobs). The model is `providerOptions.cursor.modelName`, found by following the chat's root blob to the message blobs it lists and reading a bounded slice of the newest few. Cursor writes its own codename there and it is published verbatim, since mapping it to a marketing name is a guess that would silently mislabel the next codename. Blobs are plaintext on every store measured, but the store carries an encryption key it is never asked for: where the bytes do not read, the session reports no model. The payload is undocumented, so the workspace is read by trying several key spellings in order of trust and accepting a value — bare path or `file://` — only when it resolves to a directory that exists, since a wrong key would otherwise label the row confidently and wrongly; when none matches, the row reads `cursor` as it always did
- `~/.local/share/goose/sessions/sessions.db` (SQLite, read-only) — Goose v1.10.0+: `sessions` (`working_dir`, `updated_at` UTC, `session_type='subagent'` + `parent_session_id`; archived + infrastructure types `hidden/terminal/gateway/acp` filtered), `messages` (role, `created_timestamp`) for turns/prompts, `usage_ledger` for the token rate (`messages.tokens` is never written by goose). Per-session activity = `updated_at` column, not file mtime (shared DB) — a long single-message generation can briefly read Idle since `updated_at` only bumps on message insert. Legacy per-session `.jsonl` and the `GOOSE_PATH_ROOT` override are not supported
- `~/.factory/projects/<project>/<session-id>.jsonl` — Factory Droid: line 1 `session_start` (`id`, `sessionTitle`, `cwd`); messages are Anthropic-style blocks (`role`, `content[]`, `timestamp`)

Pi relocation: `PI_CODING_AGENT_SESSION_DIR` is an authoritative direct session-store override and takes precedence over `PI_CODING_AGENT_DIR`, Pi's global `sessionDir` setting, and the default. `PI_CODING_AGENT_DIR` relocates the configuration root; a relative global `sessionDir` resolves below it. A one-off Pi `--session-dir` and a project-local `.pi/settings.json` are not discoverable from this separate process. Set `PI_CODING_AGENT_SESSION_DIR` to the effective directory in either case.

## Session states

| State | Meaning | Derived from |
|---|---|---|
| **Needs input** (red, popup fired) | Claude is blocked on the human | Best effort, never guaranteed, from three sources that cover different things rather than ranking cleanly. The bundled `PermissionRequest` hook is the main one for tool gates, seen directly for `ExitPlanMode` and in the wild for `AskUserQuestion`. An actionable Notification-hook POST is the *only* source for an MCP elicitation or a worker's permission or network request. A pending input tool seen in the transcript is an opportunistic extra, because Claude Code flushes that record on its own schedule and sometimes not until the gate has been answered. Claude only — other harnesses have no needs-input detection |
| **Working** (blue) | Actively generating | transcript/subagent/DB activity within the last 90s; detail = in-progress task's activeForm, else running subagents, else last tool |
| **Idle** (gray) | Turn ended | anything else — "awaiting your message" |

## Display modes

A `display` switch at the top right toggles between two renderings of the same `/api/data` payload. The choice is remembered per browser (`localStorage`, key `cargento.displayMode`) and `c` toggles it from the keyboard. Nothing is filtered out of one mode and present in the other; the two never disagree about a session.

A `stop` button sits beside the switch in both modes: the first activation arms it and keeps focus
there, and the second stops the server. `Enter` or `Space` on the focused button works like a click.
Anything unrelated you do first — `esc`, a click elsewhere, another control, another key —
disarms it. After it fires the page stops updating and says
Cargento was stopped, rather than showing the "stalled" banner that means the server went away on
its own.

- **regular** (default) — the card stack: hero tiles, the needs-input band, one card per working session, a collapsed idle list. The `Needs you` and `Working now` tiles break their count down per harness. Every working card draws the same parts in the same order, including a current-turn track — indeterminate when no past turn ran long enough to estimate against. The working session with the highest token rate carries a `fastest` pill, which reads `fastest known` while any working session on screen comes from a harness that reports no rate, since that is the strongest claim available with part of the board unmeasured; nothing is marked when no working session is generating, and a tie marks every session holding the maximum.
- **calm** — one dense ledger row per session in a fixed frame that scrolls internally, for boards with more sessions than fit as cards. Columns: state rail, harness, session title, `project · session id`, what it's doing, flag, `rate`, and `idle / wait`. `rate` is tokens per minute averaged over the server's rate window — a trailing mean, not a reading of this instant — with the current-turn progress bar beneath it, and a dash rather than a zero where the harness reports no token rate at all, which is the same distinction the regular view draws by printing `rate unknown` in place of the meter. It fills for working rows and nothing else, so the cell has three readings and one each: a number is a measurement including a real 0, a dash is a harness nobody measures, and an empty cell is a row that is not working, whose own headline number is the `idle / wait` beside it — how long a blocked or idle session has been sitting. Each column carries one unit, so it can be compared down its own length, and is empty on the buckets it does not describe. Clicking a row expands it in place with the flag's explanation, the last prompt, tracked tasks, any Spacedock stage strips, the turn estimate, subagents, and `copy id`. When the project name is too long for its column the project is truncated, never the session id.

MCP tools appear under the service being called rather than their wire name — `Linear · list issues`, not the double-underscored triple the harness records. The full original string is in the row's tooltip.

Calm mode's own controls: the three state counts in the header filter by state, `order` sorts by `attention` (flagged and blocking states first, newest within each), `recent`, `repo` (grouped, with a heading per project), or `fastest` (working rows only, highest token rate first, under a heading naming the window that rate is a mean over; nothing the ordering cannot rank is sorted to the bottom of the descending list as if it were the slowest, so rows whose harness reports no rate and rows that are not working each sit under a heading saying which of the two they are — a trailing mean still credits a session that stopped a minute ago, and leading with that row would send you to an agent doing nothing; and when every rate it can read is zero there is no race to rank, so those rows keep their own heading instead of being presented in an arbitrary order as a ranking), and the `◆ N flagged` pill narrows to flagged rows. Keys: `j`/`k` or arrows move the cursor, `⏎` expands, `f` toggles the flagged filter, `c` switches mode, `esc` clears filters. Row order is stable across a refresh in the first three orderings, so rows do not move under the cursor while you read; `fastest` is the deliberate exception, because it ranks on a number that changes and an order that could not change would not answer the question it was picked to answer.

Three flags appear in the `flag` column, and only these three — each is a signal the server actually detects, so no flag means nothing is known to be wrong:

| Flag | Meaning |
|---|---|
| **your call** (red) | Needs input. You are the blocker. |
| **long turn** (amber) | Working, and this request has run or is estimated to run ≥15 min (`LONG_TURN_WARN_SEC`) — the same signal as the regular view's ⚠️. |
| **stale** (gray) | Idle with no activity for ≥2h. Either it finished quietly and nobody read the result, or it is waiting on a reply that never came. |

## Usage and rate limits

A `Usage · rate limits` section appears when a machine has a harness whose quota Cargento can read. Five sources feed it. Codex writes rate-limit snapshots inside its own session files, and Cargento reads them the way it reads everything else — no network request, no credential. Claude quota comes from an outbound request: with the usage feature on, the server reads the harness's own OAuth token (the macOS Keychain — the first read can raise a permission prompt — or the credential file in the Claude home elsewhere) and polls Anthropic's usage endpoint, at most once per five minutes and only while a dashboard page is open. The token is never refreshed, written, logged, or served; the repository's SECURITY.md section "Usage quota reads" is the full contract. Machines with none of these show no section at all. Copilot is the third source and the odd one out: its CLI records what it spent in AI Units, per model request, in its own session store, but GitHub keeps the monthly entitlement server-side and the CLI never writes it down. So Copilot shows a `used` figure (AI Units consumed within the activity window, read from disk, no credential) and no bar or percentage, because there is no limit locally to be a fraction of.

Cursor is the fourth source, and the only one that meters money rather than requests. It is the second harness Cargento fetches for, reading the session token the Cursor CLI keeps in the macOS Keychain and calling the same usage RPC the CLI's own `/usage` command calls, under the identical gates as Claude's fetch. Its allowance runs on a monthly billing cycle, so it shows a `mo` bar with the cycle-end date plus a `used` figure carrying the money (`$0.18 of $20.00`), because a percentage near zero does not say whether the plan is barely touched or the allowance is small. Cursor's quota is macOS-only: elsewhere the token's location is unverified and Cargento reads no credential rather than guessing a path, so its sessions still appear and only the usage row is missing. A plan with no spending limit shows the money and no bar.

Antigravity is the fifth source and the only one needing a setup step, because it hands its quota over rather than storing it: it pipes a state payload, including quota, to whatever command its `statusLine` setting names. Point that at the dashboard and the tile fills with no credential read and no network request:

```json
"statusLine": {"command": "python3 <skill-dir>/notify_hook.py http://127.0.0.1:4553/api/usage", "enabled": true}
```

That is the same forwarder the Claude notification hooks use, with a different URL; it prints nothing, so the status line stays empty. Without it Antigravity simply shows no usage row. Quota only arrives while `agy` is running, so the figure carries its `as of` stamp and drops out once it ages past the activity window. Where two model families report the same window, the more consumed of the two is shown, since that is the limit you will hit first.

The first time the dashboard opens with the fetch available, a modal discloses exactly what is sent and carries the off switch. The feature is on by default; turning it off (in the modal or later under `configure ▾`) stops all fetching, and `--no-usage` disables it for a run regardless of the stored setting — the disk-read tiles (Codex, Copilot) stay either way. An expired or rejected token shows an exclamation and a note to sign in again in the harness itself, never stale numbers.

Per harness it shows whichever windows that harness actually has, as bars that count down to each reset (amber from 70% used, red from 90%; hover a row for the absolute reset time, and a window already past its reset reads `due`) and an `as of` timestamp: the 5-hour and weekly windows for Claude, Codex and Antigravity, and the monthly billing cycle for Cursor. A Codex snapshot is only as fresh as the last active turn and a fetched figure as fresh as the last fetch, so the stamp names its day when it is not from today. Codex snapshots older than the dashboard's activity window are dropped entirely; the section then reads "No quota data yet" rather than showing percentages whose windows have already reset. In regular mode the section sits between the tiles and the needs-input band; in calm mode it is a strip above the ledger, toggled by the `usage` chip or the `u` key. `configure ▾` picks which stats are shown, remembered per browser; the last remaining stat cannot be unchecked.

Claude's weekly allowance can be metered per model as well as in total. Where the account has such sub-limits, each one gets its own bar directly beneath the weekly bar it subdivides, labelled with the model's own name — all of them at once, since choosing between two models only helps before the tighter of the two stops you. They are on by default (`per-model limits` under `configure ▾`), and an account with none shows no rows and no placeholder rather than an empty section. Names are bounded before they are sent and the column is narrow, so a name too long for it is cut with the whole of it on hover. Anthropic does not always send a reset time for these: a row without one reads `↺ —` and says "resets at an unknown time" on hover, rather than borrowing the weekly countdown, which would put a figure on the row that this limit never published. The burn projection leaves them alone — with that stat on they read `not projected`, because a per-model row's only identity is the vendor's display name and it carries no reset instant to notice a rollover with, so a fitted rate could span two allowances and read slower than the truth. The weekly window they subdivide is the row that carries a rate.

One of those stats is derived in the page rather than published by any harness. `burn projection`, off by default, fits a slope through each window's percentages as they arrive and prints what it measured and nothing composed out of it: the rate, the resolution that rate is known to, and the interval in which the window is projected to reach 100% — `~36%/h · wall 42m–47m`, with the ± in the tooltip. It does not say whether the reset gets there first. That comparison is yours to make against the `↺` countdown on the same row, because a slope fitted to a handful of integer readings cannot settle it, and a row that called the race called it wrongly in the reassuring direction. It is also built to say when it cannot answer at all, since the readings are taken only while a page is open with usage on (in calm mode, with the usage band open) and are lost on reload: it reads `warming up` until three readings span ten minutes, prints a ceiling (`under 3%/h`) instead of a rate while the rise is too small for whole percentages to resolve, and `stale`, with the age of the last reading, once nothing new has arrived for more than ten minutes — which is what a harness that has stopped pushing quota looks like. Only a window already at 100% is coloured: a colour on a projection would be the verdict the row deliberately does not give.

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

Tell the user the URL, that the page updates itself as sessions change, that it keeps running until
stopped, and that popups require the server to be running. Completed-task ages/estimates degrade
where the filesystem exposes no birthtime (Linux, and Windows before Python 3.12).

If the port is busy the server explains that instead of dumping a traceback, and exits non-zero —
under `--daemon` too. Check whether a dashboard is already there before killing anything:

```bash
python3 "<skill-dir>/server.py" --port 4553 --status
```

`--status` reports one of three things, and never guesses: running (with pid and start time), not
running, or that the port belongs to some other process — in which case it changes nothing.

The server writes two files, both under `~/.cargento` (relocatable with `CARGENTO_HOME`):
`cargento-<port>.json`, which records the running instance, and `cargento-<port>.log`, where a
detached server's output goes. If you wire up Antigravity's status line, `statusline_hook.py` keeps
one small memo per conversation in the same directory so a status line that fires many times a turn
posts once.

## Notifications

Three paths manage needs-input state, and two layers can deliver the popup. **Exactly one of them fires for any given transition**, so nobody is notified twice:

- **macOS** — the server fires `osascript display notification` (60s per-session cooldown plus a 15s global floor). This works with no browser tab open, which is what the lifecycle-hook path below needs.
- **Linux and Windows** — the server has no native backend yet, so the dashboard page raises a browser notification instead. `/api/data` reports which layer is active as `native_notify`. Browser notifications need permission: an "Enable notifications" button appears in the header when it has not been granted, and the header says so if the browser has blocked them. They only fire while a dashboard tab is open — so on these platforms the hook path below still delivers no popup when no tab is open.

Both layers notify on the *transition* into needs-input, not on every refresh a session spends blocked.

**Known gap:** idle nudges (`idle_prompt`) pop without marking the session blocked. The server delivers those on macOS, but the page only notifies on a needs-input transition — so on Linux and Windows an idle nudge produces no popup today. Closing it needs a one-shot event channel in `/api/data`; it is tracked alongside the native Linux and Windows backends rather than bolted on here.

1. **Transcript detection** — an open `AskUserQuestion` or `ExitPlanMode` flips the session to Needs input on the next collection, *when the record has reached disk*. Claude Code buffers it and may not write it until the gate is answered, so treat this as an opportunistic early signal rather than a source to rely on (an open dashboard tab is what drives collections, so keep one open). When the record is there, the row shows the question itself, or a plan's first line, rather than the tool's name; when it is not, the row still says a question is open but cannot say which. Both readings are normal for the same session. There is also a window of up to 90 seconds after a turn starts where a live event overlay reports Working and the question does not show at all, even though it was parsed.
2. **Lifecycle hooks** — `Notification` and `SessionEnd` hooks in user settings (`~/.claude/settings.json`) POSTing their payloads to `http://127.0.0.1:4553/api/notify`. Notifications cover permission prompts and idle waits, even with no browser tab open. The structured `notification_type` decides whether a notification is actionable. Idle nudges (`idle_prompt`, message "Claude is waiting for your input") pop once but never mark the session blocked; authentication, completion and computer-use status notifications do neither; permission prompts, MCP elicitation dialogs and a worker's permission or network request create Needs-input state. A type not on either list is treated as actionable, so a notification kind added upstream surfaces rather than disappearing. `SessionEnd` clears a standing hook when Claude exits cleanly. These hooks are NOT installed by the plugin — if the user wants path 2, offer to add them to their `~/.claude/settings.json`:

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

3. **Lifecycle events** — the plugin's own bundled hooks at `hooks/hooks.json`, so there is **nothing to add to a settings file**. They forward general lifecycle events to `/api/events/claude`: prompt submitted, turn stopped, permission requested, subagent started or stopped, tasks changed, compaction finished. Where path 2 sets one piece of side state, this drives the session's Working, Needs-input and Idle state directly, so the board reacts to a turn starting instead of waiting for the next scan.

   Nothing to install: enabling the plugin is enough. Note that a session's overlays are retired when it ends, which is correct and means a one-shot `claude -p` run shows no event-driven state by the time it exits.

   Only add the hooks by hand if the user runs `event_hook.py` outside the plugin, for instance against a checkout. In that case:

```json
"hooks": {
  "UserPromptSubmit": [
    {"matcher": "", "hooks": [{"type": "command", "command": "python3 \"<skill-dir>/event_hook.py\" claude", "async": true}]}
  ],
  "Stop": [
    {"matcher": "", "hooks": [{"type": "command", "command": "python3 \"<skill-dir>/event_hook.py\" claude", "async": true}]}
  ],
  "PermissionRequest": [
    {"matcher": "", "hooks": [{"type": "command", "command": "python3 \"<skill-dir>/event_hook.py\" claude", "async": true}]}
  ],
  "SessionEnd": [
    {"matcher": "", "hooks": [{"type": "command", "command": "python3 \"<skill-dir>/event_hook.py\" claude"}]}
  ]
}
```

The harness name is the first argument and is required. Pass a **port** second for a non-default instance: `python3 "<skill-dir>/event_hook.py" claude 9999`. Note that this differs from `notify_hook.py`, which takes a whole URL.

This path needs no configured secret. Each run of the dashboard generates its own capability and publishes it in its state file, which the hook reads; nothing is stored between runs. With no dashboard running the hook reads one small file and exits 0. A dashboard started with `--no-events` publishes no capability, so the hook stays silent.

### Codex

Codex sessions report through the **plugin's own bundled hooks** at `hooks/codex-hooks.json`, so there is nothing to add to a settings file. Codex asks the user to trust each hook once, and silently skips any hook it has not been asked about, so after installing the plugin tell the user to approve Cargento's hooks when Codex prompts. Until they do, Codex rows keep the same scan-only behaviour they have today.

Five events are registered, which is exactly what a real capture showed firing: `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `Stop` and `PostCompact`. `PreToolUse` fires too and is deliberately not used, because `PostToolUse` reports the same turn once the store has actually changed.

### Antigravity

Antigravity has two paths, and they do different jobs.

**Hooks are bundled with the plugin** (`hooks.json` at the plugin root), so nothing needs configuring for them. They fire after a tool step and after a model invocation, and they only tell the dashboard the store probably moved, which keeps an Antigravity row fresh without waiting for the next scan. They deliberately claim nothing about whether the agent is working or idle: Antigravity's hooks can fire several times in one turn, so treating them as turn boundaries would flap the row.

**Working and Idle state comes from the status line**, which cannot be plugin-bundled, so that half is opt-in. Point it at `statusline_hook.py`, which forwards both the quota figures and the lifecycle state:

```json
"statusLine": {"command": "python3 \"<skill-dir>/statusline_hook.py\"", "enabled": true}
```

Pass a port as the first argument for a non-default instance. This replaces the older `notify_hook.py <url>/api/usage` line, which still works and still feeds the quota band; the new script additionally drives Working state and sends the quota block *alone* rather than the whole status-line document, which carries the account email and the transcript path.

Two honest limits, both measured rather than assumed. Antigravity's status-line payload carries **no confirmation-pending field**, so an Antigravity row cannot report Needs input from this path and falls back to what the collector sees. And its conversation id is blank until a conversation exists, so the return to Idle often cannot be reported; the Working state carries a deadline and the collector decides again after it lapses.

Paths 2 and 3 are complementary and can both be installed. Keep `Notification` on `notify_hook.py`: Claude Code can emit an input-waiting notification for a session that then carries on running, so it stays revocable side state rather than an authoritative state change. `SessionEnd` is useful on both, which is why it appears twice above.

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
| `--no-usage` | For this run, never fetch vendor quota over the network and ignore quota a harness pushes in, regardless of the setting stored in the dashboard. Quota a harness writes into its own store (Codex, Copilot) still shows. |
| `--no-events` | For this run, do not accept lifecycle events: no event overlays, no coarse store probe, no capability published, and the fixed-interval scan keeps the board warm instead. The rollback switch if event acquisition misbehaves. |
| `http://127.0.0.1:4553/?all=1` | Show all sessions ever, including idle ones |
| `/api/data` | Raw JSON, same data as the UI |
| `/api/health` | Liveness and identity (pid, port, start time). Scans nothing, unlike `/api/data`. |
| `/api/overlays` | Diagnostic: the live event overlays behind each session's state, with their arrival order and timings, plus a record of every time an event overruled a session the dashboard had read as waiting. Use this when a row's state disagrees with what the agent is actually doing and you need to know whether an event said so or never arrived. Empty is a real answer. Absent under `--no-events`. |
| `/api/stream` | Server-sent events, one per new revision. This is what keeps an open page current, so it refetches when something changed rather than on a timer; one tab per browser holds the connection. A browser without `EventSource` falls back to polling. |
| `POST /api/shutdown` | Stop the server. Loopback-only, with the same origin checks as `/api/notify`. |
| `POST /api/usage` | Receive a harness's own quota, forwarded by its status-line command (see Usage and rate limits). Loopback-only, same origin checks. Stores in memory only. |

## Interpretation notes (share with the user if asked)

- **A quiet row is not proof nothing is waiting.** Needs-input detection is best effort on every path, so a session sitting at a gate can read Working for a while before the red band appears. Absence of the band is not evidence that nothing is blocked. The band is worth acting on, but it is not proof either: an unrecognised notification type is deliberately treated as actionable so a new kind of prompt cannot vanish, and that same rule can raise the band for something that turns out not to need you.
- **Age** = time since the task file was created (birthtime where the platform has it — macOS, and Windows on Python 3.12+; elsewhere it falls back to mtime). For completed tasks it is creation → last update.
- **Output rate** = output tokens over the last 10 minutes. Generation rate, not billed input/cache tokens. Claude, Codex, Pi, Gemini CLI, Antigravity CLI, and Goose expose per-message or per-generation token data. Copilot, OpenCode, Cursor, and Droid expose no usable live token totals, so their sessions are missing from this tile rather than being zero in it. When one of them is active the number is prefixed `≥` and the line beneath counts the active sessions the total could not see, naming their harnesses on hover; a working card for such a session reads `rate unknown` in place of its meter, and in calm mode its `rate` cell is a dash. A discovered harness whose collector failed this scan makes the total a floor for the other reason — none of its sessions reached the sum at all — so the same line counts it, its row in the per-harness split reads a dash rather than a zero, and the harness strip badges it `collector error`. An absent measurement and a measured zero are different facts, and only the second one means the session is quiet.
- **Rate sparklines** (the trend under the Output rate number, and the mini one beside each working card's tok/min) trail the last 5 minutes and are client-side only: they start filling when the page opens, discard points that age out of the window, and reset on page reload. Hover or focus the tile sparkline for exact values.
- **Model** = which model the session is running on, drawn on the working card, the needs-input row, and the calm detail panel, beside the `via` clause where there is one. Six harnesses report it, each out of data the harness already writes: Claude, Codex, Pi, Antigravity CLI, Copilot, and Cursor. Gemini CLI, OpenCode, Goose, and Factory Droid record no model Cargento has found, and those rows read `model —` rather than leaving the slot empty. The dash is deliberate, and it is the opposite of the missing `used` clause below: a harness with no billing ledger genuinely has nothing to report, while every session runs on some model, so a blank slot there would be indistinguishable from a reading. Hover it for which harness the gap belongs to. Nothing is ever inferred, so a session whose store records no model reads as unknown rather than as the harness's default. A subagent pill carries a model of its own only when the child's and the parent's are both known and different, since a child running somewhere else is the fact worth the space; a child that matches its parent, or either side unread, shows the name alone.
- **Consumption** (`used 6.43 AIU`) = what one session charged to Copilot's own per-request billing ledger over the activity window, drawn on the working card, the needs-input row, and the calm detail panel. Regular mode's collapsed idle list carries an age and nothing else, and calm's panel opens on every row whatever its state, so an idle session's figure is a keystroke away rather than gone. Copilot is the only harness that keeps a billing ledger beside its sessions, so it is the only one that carries the clause, and a row without it shows neither a dash nor a zero: the words simply are not there, and a row that says nothing about spend claims nothing, the way a row with no `via` claims nothing about whose quota it is on. `used 0.00 AIU` is a measurement — the ledger was read to the far edge of the window and holds no charge against that session. A row whose own last event is older than the window (`?all=1` brings these back) names the window in the clause, `used 2.10 AIU in the last 24h`, because that is the window's share rather than everything the session ever spent; a session with no rows inside the window at all carries no figure rather than a zero it never earned. Two kinds of unreadable ledger cost different amounts. Where it could not be read to the end of the window at all, no Copilot row carries a figure and the harness's `used` tile goes with them. Where a single row is unreadable — an amount that is not a number, or a timestamp that places itself nowhere — the tile goes, because a sum with one unknown addend is not a sum, but only the session that row names loses its figure; its siblings keep theirs, because the loss is attributable and blacking out the whole harness would throw away real measurements to guard against one bad row. So a row showing a figure beside a tile showing none is a state the page can reach, and it means what it says: that session was measured and the harness total could not be. Nothing on the page reads as a zero that was never measured. AI Units are not dollars and the rate that converts them is not on this machine, so the figure is never converted, and never summed across harnesses.
- **"This request" ETA** = per-session current-turn estimate shown while Working. Estimated total = median of that session's past turns that lasted at least as long as the current one has so far. Turn boundaries: user prompt → last event before the next prompt (Claude, Gemini, Droid); active-branch user messages for Pi; explicit start/end events (Codex `task_started`/`task_complete`, Copilot `user.message`/`session.task_complete`); or DB message timestamps (OpenCode, Goose). JSONL harnesses use an incremental whole-file scanner (survives turns longer than the transcript tail). Pi retains the latest 50 completed durations. No ETA for Cursor. "running longer than recent turns" = no past turn was this long. Naive by design. A ⚠️ appears when elapsed or estimated total ≥ 15 min (`LONG_TURN_WARN_SEC`). Elapsed measures generation, not waiting: a mid-turn quiet stretch longer than 5 minutes (`TURN_GAP_RESET_SEC` — permission prompt, open question, sleep) re-anchors the clock at the post-gap event.
- **Est. remaining** (per tracked-task session) = average duration of that session's completed tasks × open task count. Naive by design; "no estimate" until a session has a completed task that took ≥30s.
- **Spacedock stage strip** = one line per in-flight entity, showing that workflow's stages in declaration order with the entity's current stage highlighted. A bold entity name means a worker for it is running now; a plain one is read from the entity's state file or, failing that, the boot snapshot. In flight means moving: an entity resting on the initial stage or a terminal one is left out unless boot called it dispatchable, so a queue of thirty waiting on `intake` does not crowd out the two being worked. Entities whose state file has not been touched inside the freshness window are history, not work, and are skipped — that is what keeps a long-retired workflow off the card of a first officer that merely discovered it. A long workflow is windowed around the current stage, with `…` standing in for the stages elided. An over-long entity name is elided in the **middle**, never the tail — entities in one workflow share a long prefix and differ only at the end — and hovering it shows the full slug. No strip appears when the boot output is outside the scanned head of a long transcript, when the workflow README cannot be read, or when its frontmatter uses a construct the reader does not model — it renders nothing rather than a guess.
- **Session title** = the harness's own generated title where it writes one (Claude records these, and they read like "Debug Spacedock workflow steps not displaying"), otherwise the session's first prompt. That fallback is cleaned up rather than shown raw: a slash command reads as `/plugin` instead of the markup the harness wrapped it in, a dispatched worker's prompt shows the instruction instead of the envelope, absolute paths collapse to their last segment so the path does not eat the whole line, and an over-long title is cut on a word boundary. Relative paths and URLs are left whole, because the repo and PR number in a link are the informative part. Nothing is summarized by a model, so no session text leaves the machine.
- **Project** = the last two segments of the session's working directory (`spacedock/subspace`), the same rule on every harness so one directory reads identically whichever agent opened it. Bare basename is not enough: sibling worktrees are routinely all named the same thing. Claude is the only harness whose store does not hand over a path — its `projects/` directory name encodes one with every separator replaced by `-`, which cannot be split back apart — so the real working directory is read from the transcript records, and a transcript too young to carry one falls back to that encoded name whole. Cursor reports its workspace when its store records one and the harness name otherwise.
- **Session id** = enough leading characters of the session's id to be unique among the rows it sits beside, at least 8. Codex hands out time-ordered ids, so agents launched together share a long prefix, and a fixed 8 characters showed several distinct sessions as one repeated row. The width grows only within the harness and project that actually collided, so a fan-out in one worktree does not lengthen the id of an unrelated session elsewhere.
- Task rows only exist for sessions where Claude used TaskCreate — the session state line is always live regardless. Summary tiles show "–" when no session has tracked tasks.
- **Calm-mode row order** is deliberately a function of nothing that changes on its own: state, then age, then the session id. A *working* session's last activity is by definition seconds old, so ordering working rows by age would sort them on which one happened to write last and reshuffle them every refresh — they sit level instead, ordered by id. A row therefore moves when its state changes, not because time passed. Same reason `/api/data` orders sessions by id rather than by last activity. The `fastest` ordering is the single exception and an opt-in one, because the question it was picked to answer is about a number that ticks.

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
- A session stuck on "Needs input" after you already answered: the state clears on the session's own next transcript write — its own, not a subagent's, since a background agent writing says nothing about whether you have answered. `SessionEnd` clears it on a clean Claude exit, and a server restart also clears hook-reported notifications (they're in-memory). An abrupt kill cannot be distinguished from a terminal left open at a prompt, so it clears only by a later transcript event or restart.
- After two missed refreshes, the live header changes to "stalled" and shows the last successful update — restart the server, no need to reload the page.
